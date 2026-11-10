#!/usr/bin/env bash
# 스모크 S4 원문 수집 스크립트. ros-ws 컨테이너 안에서 실행한다.
#
# 사용법:
#   capture.sh [--ns NS] [--hz-seconds N] [--spin-time S] OUT_DIR
#
#   --ns NS          PX4 네임스페이스(빗금 없음, stack.json vehicles[].px4_ns, 예: px4_1).
#                    없으면 접두사 없음(인스턴스 0. 3단계부터 스모크는 쓰지 않는다).
#   --hz-seconds N   ros2 topic hz 측정 시간(초, 벽시계). 기본 30.
#   --spin-time S    --no-daemon 디스커버리 대기 시간(초). 기본 5.
#   OUT_DIR          원문을 쓸 디렉터리. run_smoke.sh S4는 artifacts/runs/<run_id>/smoke/ros
#                    (저장소 상대, 컨테이너 cwd /opt/idsim 기준).
#
# 하는 일은 원문 수집뿐이다. 골든 형식(topics.txt, qos/, env.txt) 생성은
# test-engineer 의 tests/support/normalize.py 가 맡고, run_smoke.sh 가 이 스크립트 뒤에 부른다.
#
# 출력(OUT_DIR 아래):
#   topic_list.txt            ros2 topic list -t --no-daemon 원문(전체 토픽)
#   topic_info/<rel>.txt      fmu/ 아래 토픽마다 ros2 topic info -v --no-daemon 원문
#   hz/<rel>.txt              주요 토픽의 ros2 topic hz --wall-time 원문
#   env_raw.txt               KEY=VALUE. 골든 env.txt 의 네 키와 측정 조건
#   capture.log               이 스크립트의 진행 기록
#   <rel> 은 네임스페이스를 뗀 상대 토픽, 예: fmu/out/vehicle_status_v1
#
# 환경변수:
#   IDSIM_BUILD_PX4_TAG, IDSIM_BUILD_PX4_MSGS_REF, IDSIM_BUILD_XRCE_AGENT_TAG
#                        이미지가 빌드 때 남긴 버전(필수). env_raw.txt 의 출처이며 versions.env 와 대조한다.
#   IDSIM_VERSIONS_ENV   versions.env 경로. 기본은 이 스크립트 기준 ../../docker/versions.env
#   CAPTURE_HZ_BASES     hz 를 잴 토픽 기본 이름(접미사 없이) 공백 목록. 기본값은 아래 DEFAULT_HZ_BASES

set -euo pipefail

readonly DEFAULT_HZ_BASES="vehicle_status vehicle_local_position vehicle_global_position \
vehicle_attitude vehicle_odometry sensor_combined vehicle_land_detected vehicle_control_mode \
battery_status failsafe_flags vehicle_gps_position"

usage() {
  sed -n '2,13p' "$0" >&2
  exit 2
}

die() {
  echo "capture.sh: $*" >&2
  exit 1
}

ns=""
hz_seconds=30
spin_time=5
out_dir=""

while [ $# -gt 0 ]; do
  case "$1" in
    --ns) [ $# -ge 2 ] || usage; ns="$2"; shift 2 ;;
    --hz-seconds) [ $# -ge 2 ] || usage; hz_seconds="$2"; shift 2 ;;
    --spin-time) [ $# -ge 2 ] || usage; spin_time="$2"; shift 2 ;;
    -h|--help) usage ;;
    -*) usage ;;
    *) [ -z "$out_dir" ] || usage; out_dir="$1"; shift ;;
  esac
done
[ -n "$out_dir" ] || usage

# 앞뒤 빗금은 떼고, 빈 값이면 네임스페이스 없음.
ns="${ns#/}"
ns="${ns%/}"
case "$ns" in
  ""|[a-zA-Z]*) ;;
  *) die "잘못된 네임스페이스: $ns" ;;
esac
case "$hz_seconds" in ''|*[!0-9]*) die "--hz-seconds 는 양의 정수: $hz_seconds" ;; esac
[ "$hz_seconds" -gt 0 ] || die "--hz-seconds 는 양의 정수: $hz_seconds"

if [ -n "$ns" ]; then
  prefix="/${ns}/"
else
  prefix="/"
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
versions_env="${IDSIM_VERSIONS_ENV:-${script_dir}/../../docker/versions.env}"
[ -r "$versions_env" ] || die "versions.env 를 읽을 수 없다: $versions_env"

command -v ros2 >/dev/null 2>&1 || die "ros2 가 PATH 에 없다. ROS 2 환경을 source 했는지 확인"
[ "${RMW_IMPLEMENTATION:-}" = "rmw_cyclonedds_cpp" ] \
  || die "RMW_IMPLEMENTATION 이 rmw_cyclonedds_cpp 가 아니다: ${RMW_IMPLEMENTATION:-<unset>}"

mkdir -p "$out_dir/topic_info" "$out_dir/hz"
log="$out_dir/capture.log"
: > "$log"

log() {
  echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$log" >&2
}

# versions.env 는 source 하지 않고 KEY=VALUE 줄만 읽는다(임의 코드 실행 방지).
# 따옴표 하나 짝은 벗긴다. 같은 키가 여러 번이면 마지막 값.
read_version() {
  local key="$1" val
  val="$(sed -n "s/^[[:space:]]*\(export[[:space:]]\+\)\{0,1\}${key}=//p" "$versions_env" | tail -n 1)"
  val="${val%%[[:space:]]#*}"
  val="${val#\"}"; val="${val%\"}"
  val="${val#\'}"; val="${val%\'}"
  printf '%s' "$val"
}

# env_raw.txt 의 버전 값은 실제로 돌고 있는 이미지가 빌드 때 남긴 ENV 에서 온다.
# PX4_MSGS_REF 는 ros-ws 이미지 자신의 IDSIM_BUILD_PX4_MSGS_REF 다.
# PX4_TAG, XRCE_AGENT_TAG 는 ros-ws 이미지에 없으므로 run_smoke.sh 가 px4, xrce-agent
# 컨테이너에서 IDSIM_BUILD_* 를 읽어 같은 이름의 환경변수로 넘긴다고 가정한다.
# 값이 없거나 versions.env 와 다르면 이미지와 저장소가 어긋난 것이므로 실패한다.
image_version() {
  local key="$1" img_val file_val
  img_val="$(printenv "IDSIM_BUILD_${key}" || true)"
  file_val="$(read_version "$key")"
  [ -n "$img_val" ] || die "환경변수 IDSIM_BUILD_${key} 가 없다(이미지 ENV 또는 run_smoke.sh 가 넘겨야 함)"
  [ -n "$file_val" ] || die "versions.env 에 ${key} 가 없다: $versions_env"
  [ "$img_val" = "$file_val" ] \
    || die "${key} 불일치: 이미지=$img_val versions.env=$file_val"
  printf '%s' "$img_val"
}

px4_tag="$(image_version PX4_TAG)"
px4_msgs_ref="$(image_version PX4_MSGS_REF)"
xrce_agent_tag="$(image_version XRCE_AGENT_TAG)"

# 1. env_raw.txt. 앞 네 줄은 골든 env.txt 의 키, 나머지는 측정 조건(골든 아님).
{
  echo "PX4_TAG=$px4_tag"
  echo "PX4_MSGS_REF=$px4_msgs_ref"
  echo "RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION"
  echo "XRCE_AGENT_TAG=$xrce_agent_tag"
  echo "CAPTURE_NS=$ns"
  echo "HZ_SECONDS=$hz_seconds"
  echo "HZ_TIME_BASE=wall"
  echo "HZ_QOS=sensor_data"
  echo "PX4_SIM_SPEED_FACTOR=${PX4_SIM_SPEED_FACTOR:-1}"
  echo "ROS_DISTRO=${ROS_DISTRO:-}"
  echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
  echo "CYCLONEDDS_URI=${CYCLONEDDS_URI:-}"
  echo "CAPTURED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$out_dir/env_raw.txt"
log "env_raw.txt 저장 (PX4_TAG=$px4_tag ns=${ns:-<없음>})"

# 2. 토픽 목록 원문.
ros2 topic list -t --no-daemon --spin-time "$spin_time" > "$out_dir/topic_list.txt" \
  || die "ros2 topic list 실패"
log "topic_list.txt 저장 ($(wc -l < "$out_dir/topic_list.txt") 줄)"

# 원문 한 줄 형식: "/px4_1/fmu/out/vehicle_status_v1 [px4_msgs/msg/VehicleStatus]"
# 이 네임스페이스의 fmu/ 아래 상대 이름만 뽑는다.
mapfile -t rel_topics < <(
  awk -v p="${prefix}fmu/" '
    index($1, p) == 1 { print substr($1, length(p) - 3) }
  ' "$out_dir/topic_list.txt" | LC_ALL=C sort -u
)
[ "${#rel_topics[@]}" -gt 0 ] || die "${prefix}fmu/ 아래 토픽이 없다. 에이전트 연결과 ROS_DOMAIN_ID 를 확인"
log "${prefix}fmu/ 아래 토픽 ${#rel_topics[@]} 개"

# 3. 토픽별 info -v 원문.
for rel in "${rel_topics[@]}"; do
  dest="$out_dir/topic_info/${rel}.txt"
  mkdir -p "$(dirname "$dest")"
  if ! ros2 topic info -v --no-daemon --spin-time "$spin_time" "${prefix}${rel}" > "$dest" 2>&1; then
    log "경고: info 실패 ${prefix}${rel}"
  fi
done
log "topic_info 저장"

# 4. 주요 토픽 hz. 기본 이름에 접미사 _v<N> 가 붙었을 수 있으므로 목록에서 찾는다.
#    ros2 topic hz 는 Jazzy 에서 sensor_data QoS 로 구독한다(ros2topic/verb/hz.py).
#    병렬로 돌려 전체 시간을 hz_seconds 로 묶는다. SIGINT 로 끝내야 출력이 남는다.
read -r -a hz_bases <<< "${CAPTURE_HZ_BASES:-$DEFAULT_HZ_BASES}"
pids=()
for base in "${hz_bases[@]}"; do
  found=""
  for rel in "${rel_topics[@]}"; do
    if [[ "$rel" =~ ^fmu/out/${base}(_v[0-9]+)?$ ]]; then
      found="$rel"
      break
    fi
  done
  if [ -z "$found" ]; then
    log "hz 건너뜀: fmu/out/${base} 없음"
    continue
  fi
  dest="$out_dir/hz/${found}.txt"
  mkdir -p "$(dirname "$dest")"
  PYTHONUNBUFFERED=1 timeout --signal=INT --kill-after=10 "$hz_seconds" \
    ros2 topic hz --wall-time "${prefix}${found}" > "$dest" 2>&1 &
  pids+=("$!")
done
log "hz ${#pids[@]} 개 측정 시작 (${hz_seconds}s, 벽시계)"
for pid in "${pids[@]}"; do
  # timeout 의 종료 코드 124 는 정상 종료다.
  wait "$pid" || true
done
log "hz 측정 끝"

# 5. 정규화(골든 형식 생성)는 여기서 하지 않는다. run_smoke.sh S4가 이 스크립트 다음에
#      python3 -m tests.support.normalize --raw <OUT_DIR> --ns <ns> --check|--update
#    를 부른다(입력: topic_list.txt, topic_info/<rel>.txt, env_raw.txt.
#    출력: tests/fixtures/px4/<PX4_TAG>/ 의 topics.txt, qos/<rel>.txt, env.txt).
#    골든 갱신은 run_smoke.sh --update-golden 일 때만 한다.

log "완료: $out_dir"
