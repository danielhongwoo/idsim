#!/usr/bin/env bash
# gazebo 서비스의 진입 스크립트 (sim-base 이미지, root로 실행).
#
# 하는 일
#   1. 월드 SDF의 <world name="...">이 IDSIM_WORLD_NAME과 같은지 검사한다. 다르면 종료 코드 1.
#   2. 월드 SDF에 spherical_coordinates 요소가 정확히 하나인지 검사한다. 아니면 종료 코드 1.
#      원점은 생성기가 SDF에 넣은 값으로만 들어간다(월드 로드 때 적용). 값이 fleet.yaml과
#      같은지는 생성기 단위 테스트가, 실제 적용은 px4 쪽 sensor_gps 좌표(스모크 S2)가 판정한다.
#   3. `gz sim -r -s <월드 파일>`을 자식 프로세스로 띄운다. exec하지 않는 이유는 서버가 뜬 뒤
#      준비 파일을 남겨야 하기 때문이다. TERM/INT를 받으면 자식에 TERM을 전달하고(5초 안에 안 끝나면
#      KILL) 함께 끝난다. 종료 코드는 TERM 143, INT 130.
#   4. /world/<이름>/scene/info 서비스가 응답할 때까지 기다린다(상한 60초).
#   5. 응답하면 준비 파일 /tmp/idsim/ready를 남긴다.
#   6. 그 뒤 자식을 기다리고 자식의 종료 코드로 끝난다.
#
# 입력 환경변수
#   IDSIM_WORLD_NAME   필수. 월드 이름. PX4_GZ_WORLD, healthcheck 경로와 같은 값(fleet.yaml world.name)
#   IDSIM_WORLD_FILE   필수. 생성기가 만든 월드 SDF의 컨테이너 안 절대 경로.
#                      compose는 /opt/idsim/world/<이름>.sdf를 준다(실행 디렉터리의 world/를
#                      /opt/idsim/world에 읽기 전용으로 마운트). 템플릿 worlds/idsim_base.sdf를
#                      직접 주면 spherical_coordinates가 없어 2단계에서 실패한다.
#   GZ_PARTITION       필수. 스택 격리용 gz-transport 파티션(idsim-<k>)
#   GZ_IP              선택(compose는 127.0.0.1을 준다)
#   GZ_SIM_SERVER_CONFIG_PATH, GZ_SIM_RESOURCE_PATH는 이미지 ENV 또는 compose가 주는 값을 그대로 쓴다.
#   월드 SDF에 월드 직속 plugin이 없어야 GZ_SIM_SERVER_CONFIG_PATH의 system plugin 목록이 적용된다
#   (생성기가 보장한다. 이 스크립트는 검사하지 않는다).
#
# healthcheck (compose 생성기가 그대로 쓴다. <이름>은 IDSIM_WORLD_NAME 값)
#     gz service -i --service /world/<이름>/scene/info | grep -q "Service providers" && test -f /tmp/idsim/ready
#   /tmp/idsim/ready: 월드 준비(scene/info 응답)가 끝났다는 표시. 컨테이너 안 고정 경로이며 시작할 때 지운다.

set -euo pipefail

readonly MARKER_DIR=/tmp/idsim
readonly READY_FILE="${MARKER_DIR}/ready"
readonly READY_TIMEOUT_S=60
readonly STOP_GRACE_S=5

log() { echo "[gz_server] $*"; }
err() { echo "[gz_server] ERROR: $*" >&2; }

child=""

# 자식 gz 서버에 TERM을 보내고 STOP_GRACE_S초 동안 끝나기를 기다린다.
# 그래도 살아 있으면 KILL한다(서버가 TERM을 무시해 wrapper가 멈추는 것을 막는다).
stop_child() {
  if [ -z "${child}" ] || ! kill -0 "${child}" 2>/dev/null; then
    return 0
  fi
  kill -TERM "${child}" 2>/dev/null || true
  local i
  for ((i = 0; i < STOP_GRACE_S * 10; i++)); do
    kill -0 "${child}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${child}" 2>/dev/null; then
    err "gz 서버가 ${STOP_GRACE_S}초 안에 끝나지 않아 KILL한다"
    kill -KILL "${child}" 2>/dev/null || true
  fi
  wait "${child}" 2>/dev/null || true
}

# shellcheck disable=SC2329  # trap에서 호출된다
on_signal() {
  log "$1 신호를 받아 gz 서버에 TERM을 전달한다"
  stop_child
  if [ "$1" = INT ]; then exit 130; fi
  exit 143
}

# 실패 시 서버를 내리고 종료 코드 1로 끝낸다.
fail() {
  err "$*"
  stop_child
  exit 1
}

# ---- 입력 검사 (서버를 띄우기 전) ----

[ -n "${IDSIM_WORLD_NAME:-}" ] || { err "IDSIM_WORLD_NAME이 비어 있다"; exit 1; }
[ -n "${IDSIM_WORLD_FILE:-}" ] || { err "IDSIM_WORLD_FILE이 비어 있다"; exit 1; }
[ -f "${IDSIM_WORLD_FILE}" ] || { err "월드 파일이 없다: ${IDSIM_WORLD_FILE}"; exit 1; }
[ -n "${GZ_PARTITION:-}" ] || { err "GZ_PARTITION이 비어 있다(스택 격리에 필요)"; exit 1; }

world="${IDSIM_WORLD_NAME}"

# SDF의 <world name="...">을 찾는다. 정확히 하나여야 한다.
# grep이 못 찾으면 종료 코드 1이므로 || true로 받고 개수로 판정한다.
# 한계(줄 단위 grep이라 생기는 것. 둘 다 거부 쪽으로 실패하므로 조용히 틀리지는 않는다)
# - 주석 안의 <world name=...>도 센다. 개수 검사에서 실패한다.
# - <world 와 name=이 여러 줄로 나뉜 요소(<world\n  name="...">)는 찾지 못해 0개로 실패한다.
#   월드 SDF는 <world name="..."> 한 줄로 쓴다.
sdf_names=()
while IFS= read -r line; do
  sdf_names+=("${line}")
done < <(grep -oE "<world[[:space:]]+([^>]*[[:space:]])?name=[\"'][^\"']*[\"']" "${IDSIM_WORLD_FILE}" \
  | sed -E "s/.*name=[\"']([^\"']*)[\"'].*/\1/" || true)
if [ "${#sdf_names[@]}" -ne 1 ]; then
  err "월드 파일에서 <world name=...> 요소를 정확히 하나 찾지 못했다(${#sdf_names[@]}개): ${IDSIM_WORLD_FILE}"
  exit 1
fi
if [ "${sdf_names[0]}" != "${world}" ]; then
  err "월드 이름 불일치: IDSIM_WORLD_NAME=${world}, SDF <world name>=${sdf_names[0]} (${IDSIM_WORLD_FILE})"
  exit 1
fi

# spherical_coordinates 요소가 정확히 하나여야 한다. 여는 태그를 센다(한 줄에 여럿이어도 각각 센다).
# 한계는 위 <world name> 검사와 같다(주석 안의 태그도 세므로 거부 쪽으로 실패한다).
# 못 찾으면 grep이 1로 끝나 pipefail과 set -e에 걸리므로 || true로 받는다.
n_sc="$({ grep -oE "<spherical_coordinates([[:space:]>/]|$)" "${IDSIM_WORLD_FILE}" || true; } | wc -l)"
if [ "${n_sc}" -ne 1 ]; then
  err "월드 파일에 spherical_coordinates 요소가 정확히 하나가 아니다(${n_sc}개): ${IDSIM_WORLD_FILE}." \
    "원점은 생성기가 월드 SDF에 넣는다(템플릿을 직접 열지 않는다)"
  exit 1
fi

rm -f "${READY_FILE}"

# ---- 서버 기동 ----

trap 'on_signal TERM' TERM
trap 'on_signal INT' INT

log "월드 ${world} (${IDSIM_WORLD_FILE}), GZ_PARTITION=${GZ_PARTITION}, GZ_IP=${GZ_IP:-}"
log "서버 설정 ${GZ_SIM_SERVER_CONFIG_PATH:-}"
gz sim -r -s "${IDSIM_WORLD_FILE}" &
child=$!
log "gz 서버 pid ${child}"

# ---- 월드 준비 대기 ----
# PX4 px4-rc.gzsim과 같은 판정. 파이프 대신 출력을 변수로 받아 pipefail과 SIGPIPE 함정을 피한다.
deadline=$((SECONDS + READY_TIMEOUT_S))
while :; do
  if ! kill -0 "${child}" 2>/dev/null; then
    rc=0
    wait "${child}" || rc=$?
    err "월드가 준비되기 전에 gz 서버가 끝났다(종료 코드 ${rc})"
    exit 1
  fi
  info="$(timeout 5 gz service -i --service "/world/${world}/scene/info" 2>&1 || true)"
  if [[ "${info}" == *"Service providers"* ]]; then
    log "월드 준비 완료: /world/${world}/scene/info"
    break
  fi
  if [ "${SECONDS}" -ge "${deadline}" ]; then
    fail "${READY_TIMEOUT_S}초 안에 /world/${world}/scene/info가 응답하지 않았다"
  fi
  sleep 1
done

# ---- 준비 파일 ----
# healthcheck는 scene/info 응답과 이 파일을 함께 본다.
mkdir -p "${MARKER_DIR}"
date -u +%Y-%m-%dT%H:%M:%SZ > "${READY_FILE}.tmp"
mv -f "${READY_FILE}.tmp" "${READY_FILE}"
log "준비 완료. 준비 파일 ${READY_FILE}"

# ---- 서버 종료까지 대기 ----
# 신호는 on_signal이 처리한다. 자식이 스스로 끝나면 그 종료 코드로 끝낸다.
rc=0
wait "${child}" || rc=$?
log "gz 서버 종료(종료 코드 ${rc})"
exit "${rc}"
