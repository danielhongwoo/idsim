#!/usr/bin/env bash
# 스모크 단계 실행기. 호스트에서 실행한다.
#
# 사용법: tests/smoke/run_smoke.sh [--update-golden] <S0|S1|S1b|S2|S3|S4|S5>
#
# 골든이 없으면(처음 S4) --update-golden이 필요하다. --check는 골든이 없으면 실패한다.
#
# 스택 번호 하나에서 ROS_DOMAIN_ID, GZ_PARTITION, IDSIM_AGENT_PORT를 계산해 넘기며 compose 직접 실행은 지원하지 않는다.
#
# 하는 일
#   1. docker/versions.env를 읽고 스택 번호 k(IDSIM_STACK_INDEX, 기본 0)에서 ROS_DOMAIN_ID = 20 + k,
#      에이전트 포트 = 8888 + k, GZ_PARTITION = idsim-k를 계산한다. S0은 compose를 올리지 않고 이미지만 검사한다.
#   2. 단계에 맞는 프로필로 `compose up --wait --wait-timeout 240`을 한다 (S1은 healthcheck가 없어 직접 대기).
#   3. 단계별 판정을 실행한다. S1, S1b, S2, S3은 ros-ws 안의 check_px4.py(S3만 --arm), S4는 capture.sh와
#      tests.support.normalize(--update-golden이면 --update, 아니면 --check), S5는 /clock 증가를 본다. 모든 타임아웃은 벽시계다.
#   4. 실패하면 compose logs를 artifacts/smoke/<실행 id>/에 모으고 종료 코드 1로 끝낸다.
#   5. 성공과 실패 모두 마지막에 `compose down`을 한다.
#
# 환경변수
#   IDSIM_STACK_INDEX    스택 번호 k (기본 0)
#   IDSIM_RUN_ID         실행 id (기본: 현재 시각)
#   SMOKE_UP_TIMEOUT     up --wait 제한 시간 초 (기본 240)

set -euo pipefail

usage() {
  sed -n '2,7p' "$0" >&2
  exit 2
}

update_golden=0
if [ "${1:-}" = "--update-golden" ]; then
  update_golden=1
  shift
fi
[ $# -eq 1 ] || usage
stage="$1"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

set -a
# shellcheck disable=SC1091
. docker/versions.env
set +a

# 격리 규칙: 스택 번호 k 하나에서 세 값을 모두 계산한다 (다른 곳에서 계산하지 않는다)
k="${IDSIM_STACK_INDEX:-0}"
export IDSIM_ROS_DOMAIN_ID=$((20 + k))
export IDSIM_AGENT_PORT=$((8888 + k))
export IDSIM_GZ_PARTITION="idsim-${k}"
up_timeout="${SMOKE_UP_TIMEOUT:-240}"
run_id="${IDSIM_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
out_dir="artifacts/smoke/${run_id}/${stage}"
ulog_dir="${repo_root}/${out_dir}/ulog"
mkdir -p "$out_dir" "$ulog_dir"
export IDSIM_ULOG_HOST_DIR="$ulog_dir"

# 1단계 임시: 기체 식별자는 인스턴스 번호 N 하나에서 파생한다. 3단계 gen_compose.py가 대체한다.
n=1
export IDSIM_INSTANCE="$n"
ns="px4_${n}"
sysid=$((n + 1))
model="x500_${n}"
export IDSIM_PX4_ARGS="-d -i ${n}" IDSIM_PX4_NS="$ns" IDSIM_ULOG_SUBDIR="${n}/log"
check_timeout=60
wait_mode="healthy"
case "$stage" in
  S0)
    profile="embedded"; services=(); runner="smoke-embedded"; wait_mode="none" ;;
  S1)
    profile="embedded"; services=(xrce-agent px4-embedded); runner="smoke-embedded"
    export IDSIM_PX4_ARGS="-d" IDSIM_PX4_NS="" IDSIM_ULOG_SUBDIR="log"
    ns=""; sysid=1; wait_mode="log" ;;
  S1b)
    profile="embedded"; services=(xrce-agent px4-embedded); runner="smoke-embedded" ;;
  S2|S3|S4)
    profile="standalone"; services=(xrce-agent gazebo px4); runner="smoke" ;;
  S5)
    profile="standalone"; services=(xrce-agent gazebo px4 bridge); runner="smoke" ;;
  *) usage ;;
esac

compose() {
  docker compose -p idsim-smoke -f docker/compose.smoke.yaml --profile "$profile" "$@"
}

# ros-ws 컨테이너 안에서 명령을 한 번 실행한다. 모든 ROS 2 CLI는 --no-daemon으로 쓴다.
in_ros() {
  compose run --rm --no-deps -T "${run_env[@]}" "$runner" bash -c "$1"
}
run_env=()

# 이미지에 남긴 IDSIM_BUILD_* 값을 읽는다
image_env() {
  docker run --rm --entrypoint printenv "$1" "$2" 2>/dev/null || true
}

# S0: 이미지가 versions.env와 일치하고 필수 산출물이 있는지 본다
s0_fail=0
s0_expect() { # 이미지 변수이름 기대값
  local got
  got="$(image_env "$1" "IDSIM_BUILD_$2")"
  if [ "$got" = "$3" ]; then
    echo "ok   $1 IDSIM_BUILD_$2=$got"
  else
    echo "FAIL $1 IDSIM_BUILD_$2: 이미지 '${got}' != versions.env '$3' (이미지를 다시 빌드하라: docker buildx bake -f docker/docker-bake.hcl <타깃> --load)" >&2
    s0_fail=1
  fi
}
s0_run() { # 설명 이미지 bash명령
  if docker run --rm --entrypoint bash "$2" -c "$3" >"${out_dir}/s0_$(tr ' /' '__' <<<"$1").txt" 2>&1; then
    echo "ok   $2 $1"
  else
    echo "FAIL $2 $1 (${out_dir}/s0_$(tr ' /' '__' <<<"$1").txt)" >&2
    s0_fail=1
  fi
}
check_s0() {
  local gz_major
  case "$GZ_RELEASE" in
    harmonic) gz_major=8 ;;
    garden) gz_major=7 ;;
    *) echo "FAIL 알 수 없는 GZ_RELEASE: $GZ_RELEASE" >&2; return 1 ;;
  esac
  s0_expect idsim/ros-ws:local PX4_MSGS_REF "$PX4_MSGS_REF"
  s0_expect idsim/ros-ws:local PX4_ROS_COM_REF "$PX4_ROS_COM_REF"
  s0_expect idsim/xrce-agent:local XRCE_AGENT_TAG "$XRCE_AGENT_TAG"
  s0_expect idsim/px4:local PX4_TAG "$PX4_TAG"
  s0_expect idsim/sim-base:local GZ_RELEASE "$GZ_RELEASE"
  s0_expect idsim/sim-base:local PX4_GZ_MODELS_REF "$PX4_GZ_MODELS_REF"
  # shellcheck disable=SC2016
  s0_run "RMW_IMPLEMENTATION" idsim/ros-ws:local '[ "$(printenv RMW_IMPLEMENTATION)" = rmw_cyclonedds_cpp ]'
  s0_run "gz sim 버전" idsim/px4:local "gz sim --versions | grep -qE '^${gz_major}\\.'"
  # shellcheck disable=SC2016  # 컨테이너 안에서 전개해야 하므로 작은따옴표가 맞다
  s0_run "command -v px4" idsim/px4:local 'test "$(command -v px4)" = /opt/PX4-Autopilot/build/px4_sitl_default/bin/px4'
  s0_run "px4 필수 파일" idsim/px4:local \
    'cd /opt/PX4-Autopilot/build/px4_sitl_default && test -x bin/px4 && test -f etc/init.d-posix/rcS && test -f /opt/px4-gz/models/x500/model.sdf && test -f /opt/px4-gz/server.config && test -f /opt/px4-gz/server.idsim.config'
  s0_run "MicroXRCEAgent --help" idsim/xrce-agent:local 'MicroXRCEAgent --help 2>&1 | grep -q "^Usage"'  # --help는 종료 코드 1을 돌려주므로 출력으로 판정한다
  local img
  for img in ros-ws px4 sim-base xrce-agent; do
    docker run --rm --entrypoint bash "idsim/${img}:local" -c 'dpkg -l | grep gz-transport || echo "gz-transport 패키지 없음"' \
      >"${out_dir}/gz_transport_${img}.txt" 2>&1 || true
  done
  return "$s0_fail"
}

# 토픽 판정은 check_px4.py 한 곳에 둔다. ros-ws 컨테이너 안에서 /opt/idsim 기준으로 실행한다.
# 결과 JSON은 stdout이고 종료 코드 0/1이 판정이다.
check_px4() {
  local extra=("$@") args
  in_ros 'ros2 topic list -t --no-daemon --spin-time 10' >"${out_dir}/topic_list.txt" || true
  args="--system-id ${sysid} --timeout ${check_timeout} ${extra[*]}"
  [ -n "$ns" ] && args="--ns ${ns} ${args}"
  in_ros "cd /opt/idsim && python3 tests/smoke/check_px4.py ${args}" | tee "${out_dir}/check_px4.json"
}

# test-engineer의 tests.support.topic_info 호출. 종료 코드 0 통과, 1 판정 실패, 2 토픽 못 찾음.
topic_info() {
  in_ros "cd /opt/idsim && python3 -m tests.support.topic_info --ns ${ns} $*"
}

# px4 컨테이너 안의 pxh 명령 판정 (check_px4_pxh.py, 표준 라이브러리만). JSON은 stdout, 종료 코드 0/1/2.
check_pxh() {
  # 기대 파라미터는 config/px4/sitl_params.env의 PX4_PARAM_* 전부(단일 출처).
  local expect=() line
  while IFS= read -r line; do
    expect+=(--expect-param "${line#PX4_PARAM_}")
  done < <(grep -E '^PX4_PARAM_[A-Z0-9_]+=' config/px4/sitl_params.env)
  if [ "${#expect[@]}" -eq 0 ]; then
    echo "config/px4/sitl_params.env에 PX4_PARAM_ 항목이 없다" >&2
    return 1
  fi
  compose exec -T px4 python3 - --instance "$n" "${expect[@]}" <tests/smoke/check_px4_pxh.py >"${out_dir}/pxh_${n}.json"
}

# px4 서비스 로그를 모아 gz_bridge 오류 줄이 없는지 호스트에서 판정한다.
check_px4_log() {
  compose logs --no-color px4 >"${out_dir}/px4.log" 2>&1
  python3 tests/smoke/check_px4_pxh.py --log-file "${out_dir}/px4.log" >"${out_dir}/px4log_${n}.json"
}

# S1: healthcheck 대신 로그와 status 문자열을 직접 판정한다 (인스턴스 0).
wait_s1() {
  local deadline=$((SECONDS + up_timeout))
  until compose logs px4-embedded 2>&1 | grep -q 'Gazebo world is ready'; do
    [ "$SECONDS" -lt "$deadline" ] || { echo "FAIL: Gazebo world is ready 로그가 없다" >&2; return 1; }
    sleep 3
  done
  until compose exec -T px4-embedded px4-uxrce_dds_client status 2>&1 | grep -q 'Running, connected'; do
    [ "$SECONDS" -lt "$deadline" ] || { echo "FAIL: Running, connected 문자열이 없다" >&2; return 1; }
    sleep 3
  done
}

check_clock() {
  local a b
  a="$(in_ros 'timeout 15 ros2 topic echo --once --no-daemon /clock' | grep -E '^ *sec:' | head -1 | tr -dc '0-9')"
  sleep 3
  b="$(in_ros 'timeout 15 ros2 topic echo --once --no-daemon /clock' | grep -E '^ *sec:' | head -1 | tr -dc '0-9')"
  echo "clock sec: ${a} -> ${b}" | tee "${out_dir}/clock.txt"
  [ -n "$a" ] && [ -n "$b" ] && [ "$b" -gt "$a" ]
}

run_checks() {
  case "$stage" in
    S0)
      check_s0 ;;
    S1)
      check_px4 ;;
    S1b)
      check_px4
      topic_info "--regex '^/${ns}/fmu/out/vehicle_status(_v[0-9]+)?\$' --expect-publishers 1 --expect-type px4_msgs/msg/VehicleStatus --save ${out_dir}/s1b_topic_info" ;;
    S2)
      compose exec -T gazebo bash -c 'gz model --list' | tee "${out_dir}/gz_model_list.txt" | grep -q "$model" \
        || { echo "FAIL: gz model --list에 ${model}이 없다" >&2; return 1; }
      check_px4 && check_pxh && check_px4_log ;;
    S3)
      check_timeout=90
      check_px4 --arm
      topic_info "--regex '^/${ns}/fmu/in/trajectory_setpoint(_v[0-9]+)?\$' --expect-subscriptions 1 --save ${out_dir}/s3_topic_info" ;;
    S4)
      local mode="--check"
      [ "$update_golden" -eq 1 ] && mode="--update"
      run_env=(-e "IDSIM_BUILD_PX4_TAG=$(image_env idsim/px4:local IDSIM_BUILD_PX4_TAG)" \
               -e "IDSIM_BUILD_XRCE_AGENT_TAG=$(image_env idsim/xrce-agent:local IDSIM_BUILD_XRCE_AGENT_TAG)")
      check_pxh \
        && in_ros "cd /opt/idsim && tests/smoke/capture.sh --ns ${ns} ${out_dir}/ros" \
        && in_ros "cd /opt/idsim && python3 -m tests.support.normalize --raw ${out_dir}/ros --ns ${ns} ${mode}" ;;
    S5)
      check_clock
      in_ros 'dpkg -l | grep gz-transport' >"${out_dir}/gz_transport_ros_ws.txt" || true
      compose exec -T gazebo bash -c 'dpkg -l | grep gz-transport' >"${out_dir}/gz_transport_gazebo.txt" || true ;;
  esac
}

collect() {
  compose logs --no-color >"${out_dir}/compose.log" 2>&1 || true
  echo "로그와 산출물: ${out_dir} (ULog: ${out_dir}/ulog)" >&2
}

cleanup() {
  compose down --timeout 10 >/dev/null 2>&1 || true
}
trap cleanup EXIT

status=0
if [ "$wait_mode" = "none" ]; then
  :
elif [ "$wait_mode" = "log" ]; then
  compose up -d "${services[@]}" || status=1
  [ "$status" -eq 0 ] && { wait_s1 || status=1; }
else
  compose up -d --wait --wait-timeout "$up_timeout" "${services[@]}" || status=1
fi
if [ "$status" -eq 0 ]; then
  run_checks || status=1
fi

if [ "$status" -ne 0 ]; then
  collect
  echo "${stage}: 실패" >&2
  exit 1
fi
collect
echo "${stage}: 통과"
