#!/usr/bin/env bash
# gazebo 서비스의 진입 스크립트 (sim-base 이미지, root로 실행).
#
# 하는 일
#   1. 월드 SDF의 <world name="...">이 IDSIM_WORLD_NAME과 같은지 검사한다. 다르면 종료 코드 1.
#   2. `gz sim -r -s <월드 파일>`을 자식 프로세스로 띄운다. exec하지 않는 이유는 서버가 뜬 뒤
#      원점을 설정해야 하기 때문이다. TERM/INT를 받으면 자식에 TERM을 전달하고(5초 안에 안 끝나면
#      KILL) 함께 끝난다. 종료 코드는 TERM 143, INT 130.
#   3. /world/<이름>/scene/info 서비스가 응답할 때까지 기다린다(상한 60초).
#   4. 원점 세 값(IDSIM_ORIGIN_LAT/LON/ALT)이 모두 있으면 /world/<이름>/set_spherical_coordinates를
#      한 번 호출한다. 응답이 `data: true`가 아니거나 타임아웃이면 서버를 내리고 종료 코드 1.
#      성공하면 표시 파일 /tmp/idsim/origin_set을 남긴다(내용: 월드, 좌표, UTC 시각).
#      주의: `data: true`는 요청을 받았다는 뜻일 뿐 적용 확인이 아니다. 실제 적용은 px4 쪽
#      sensor_gps 좌표로 판정한다(S2). 이 표시 파일도 호출 성공 기록 이상이 아니다.
#   5. 원점 단계가 끝나면(원점이 없어도) 준비 파일 /tmp/idsim/ready를 남긴다.
#   6. 그 뒤 자식을 기다리고 자식의 종료 코드로 끝난다.
#
# 입력 환경변수
#   IDSIM_WORLD_NAME   필수. 월드 이름. PX4_GZ_WORLD, healthcheck 경로와 같은 값(fleet.yaml world.name)
#   IDSIM_WORLD_FILE   필수. 월드 SDF 절대 경로(fleet.yaml world.file)
#   IDSIM_ORIGIN_LAT   선택. 위도(도). 세 값은 모두 주거나 모두 비워야 한다. 일부만 있으면 시작 전에 종료 코드 1
#   IDSIM_ORIGIN_LON   선택. 경도(도)
#   IDSIM_ORIGIN_ALT   선택. 고도(m)
#                      원점 값은 십진 표기 문자열이다(예: 37.5665, -12, 지수 표기 불가).
#                      생성기는 fleet.yaml 값을 문자열 그대로 넘긴다.
#   GZ_PARTITION       필수. 스택 격리용 gz-transport 파티션(idsim-<k>)
#   GZ_IP              선택(compose는 127.0.0.1을 준다)
#   GZ_SIM_SERVER_CONFIG_PATH, GZ_SIM_RESOURCE_PATH는 이미지 ENV 또는 compose가 주는 값을 그대로 쓴다.
#   세 원점 값이 모두 비어 있으면 월드 SDF의 <spherical_coordinates>가 그대로 쓰인다
#   (1b 커스텀 월드는 SDF에 원점을 넣고 이 값들을 비운다).
#
# healthcheck (compose 생성기가 그대로 쓴다. <이름>은 IDSIM_WORLD_NAME 값)
#   원점 유무와 무관하게 하나다.
#     gz service -i --service /world/<이름>/scene/info | grep -q "Service providers" && test -f /tmp/idsim/ready
#   /tmp/idsim/ready: 월드 준비와 원점 단계(원점이 없으면 건너뜀)가 끝났다는 표시.
#   /tmp/idsim/origin_set: 원점 설정 요청이 data: true로 수리된 경우에만 생긴다(내용은 좌표와 시각).
#   두 파일 모두 컨테이너 안 고정 경로이며 시작할 때 지운다.

set -euo pipefail

readonly MARKER_DIR=/tmp/idsim
readonly MARKER_FILE="${MARKER_DIR}/origin_set"
readonly READY_FILE="${MARKER_DIR}/ready"
readonly READY_TIMEOUT_S=60
readonly ORIGIN_CALL_TIMEOUT_MS=5000
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

# 원점: 세 값 모두 있거나 모두 없어야 한다.
lat="${IDSIM_ORIGIN_LAT:-}"
lon="${IDSIM_ORIGIN_LON:-}"
alt="${IDSIM_ORIGIN_ALT:-}"
set_origin=0
if [ -n "${lat}" ] || [ -n "${lon}" ] || [ -n "${alt}" ]; then
  if [ -z "${lat}" ] || [ -z "${lon}" ] || [ -z "${alt}" ]; then
    err "IDSIM_ORIGIN_LAT, IDSIM_ORIGIN_LON, IDSIM_ORIGIN_ALT는 모두 주거나 모두 비워야 한다 (lat='${lat}' lon='${lon}' alt='${alt}')"
    exit 1
  fi
  num_re='^-?[0-9]+(\.[0-9]+)?$'
  for pair in "LAT=${lat}" "LON=${lon}" "ALT=${alt}"; do
    if ! [[ "${pair#*=}" =~ ${num_re} ]]; then
      err "IDSIM_ORIGIN_${pair%%=*} 값이 십진수가 아니다: '${pair#*=}'"
      exit 1
    fi
  done
  if ! awk -v a="${lat}" -v o="${lon}" 'BEGIN { exit !(a >= -90 && a <= 90 && o >= -180 && o <= 180) }'; then
    err "원점 범위 밖: lat=${lat} (-90..90), lon=${lon} (-180..180)"
    exit 1
  fi
  set_origin=1
fi

rm -f "${MARKER_FILE}" "${READY_FILE}"

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

# ---- 원점 설정 ----
if [ "${set_origin}" -eq 1 ]; then
  log "원점 설정: lat=${lat} lon=${lon} alt=${alt}"
  rep="$(timeout $((ORIGIN_CALL_TIMEOUT_MS / 1000 + 5)) gz service -s "/world/${world}/set_spherical_coordinates" \
    --reqtype gz.msgs.SphericalCoordinates \
    --reptype gz.msgs.Boolean \
    --timeout "${ORIGIN_CALL_TIMEOUT_MS}" \
    --req "surface_model: EARTH_WGS84, latitude_deg: ${lat}, longitude_deg: ${lon}, elevation: ${alt}" 2>&1 || true)"
  if ! grep -Eq '^[[:space:]]*data:[[:space:]]*true[[:space:]]*$' <<<"${rep}"; then
    fail "set_spherical_coordinates 응답이 data: true가 아니다(타임아웃 포함). 응답: ${rep:-<없음>}"
  fi
  mkdir -p "${MARKER_DIR}"
  printf 'world=%s\nlat=%s\nlon=%s\nalt=%s\ntime_utc=%s\n' \
    "${world}" "${lat}" "${lon}" "${alt}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${MARKER_FILE}.tmp"
  mv -f "${MARKER_FILE}.tmp" "${MARKER_FILE}"
  log "원점 설정 요청 수리(data: true). 표시 파일 ${MARKER_FILE}"
else
  log "원점 값이 없어 월드 SDF의 spherical_coordinates를 그대로 쓴다"
fi

# ---- 준비 파일 ----
# healthcheck는 원점 유무와 무관하게 이 파일 하나를 본다.
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
