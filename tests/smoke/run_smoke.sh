#!/usr/bin/env bash
# 스모크 단계 실행기. 호스트에서 실행한다.
#
# 사용법: tests/smoke/run_smoke.sh [--update-golden] [--stack k] <S0|S1b|S2|S3|S4|S5>
#
# 골든이 없으면(처음 S4) --update-golden이 필요하다. --check는 골든이 없으면 실패한다.
# S1(인스턴스 0)은 3단계부터 지원하지 않는다(2026-11-06 1회 통과 기록으로 남긴다).
#
# 하는 일
#   1. 스택 번호 k(--stack, 없으면 IDSIM_STACK_INDEX, 없으면 0)와 변형(S1b는 embedded, 나머지 standalone)으로
#      tools/stack.sh up을 부른다. stack.sh가 tools/gen_compose.sh로 artifacts/runs/<실행 id>/에 compose.yaml과
#      stack.json을 만들고, 떠 있는 idsim-<k>를 내린 뒤 세 단계(에이전트와 gazebo, px4-N, bridge)로 up --wait 하며(standalone은 1단계 뒤에
#      모델 잔존 사전 검사와 gz 서버 유일성 검사), 실패하면 에이전트 bind error와 px4 bind failed를 보고한다. S0은 스택을 올리지 않는다.
#   2. 판정에 쓰는 식별자(네임스페이스, system id, 모델 이름, 원점, 기대 파라미터, 서비스 이름)는 모두
#      stack.json에서 읽는다(python3 표준 라이브러리). 이 스크립트는 식별자를 계산하지 않는다.
#   3. 단계별 판정. S1b, S2, S3은 ros-ws 안의 check_px4.py(S3만 --arm), S2는 모델 유일성, gz 서버 유일성, pxh 판정,
#      PX4 로그(gz_bridge 오류, MAVLink bind failed), S4는 capture.sh와 tests.support.normalize
#      (--update-golden이면 --update, 아니면 --check), S5는 /clock 발행자 1과 증가. 모든 타임아웃은 벽시계다.
#      run_checks는 || 문맥에서 불리므로 set -e가 꺼져 있다. 판정 명령은 반드시 &&로 잇는다(빠뜨리면 실패가 삼켜진다).
#      아직 판정할 수 없는 항목은 pending()으로 남기고, 마지막 줄에 "통과 (미판정 N건 PENDING)"으로 나타난다.
#   4. 산출물(판정 JSON, compose 로그, ULog)은 실행 디렉터리 artifacts/runs/<실행 id>/ 아래에 남는다.
#      판정 결과와 로그는 그 안의 smoke/, ULog는 px4-N/log/다. 모든 파일은 호스트 사용자 소유다.
#   5. 성공과 실패 모두 마지막에 스택을 내린다.
#
# 환경변수
#   IDSIM_STACK_INDEX    스택 번호 k (기본 0, --stack이 우선)
#   IDSIM_RUN_ID         실행 id (기본: <UTC 시각>-k<k>-<단계>)
#   SMOKE_UP_TIMEOUT     단계별 up --wait 제한 시간 초 (기본 240)

set -euo pipefail

usage() {
  sed -n '2,7p' "$0" >&2
  exit 2
}

update_golden=0
k="${IDSIM_STACK_INDEX:-0}"
while [ $# -gt 1 ]; do
  case "$1" in
    --update-golden) update_golden=1; shift ;;
    --stack) k="${2:?}"; shift 2 ;;
    *) usage ;;
  esac
done
[ $# -eq 1 ] || usage
stage="$1"
case "$k" in [0-9]) ;; *) echo "스택 번호는 0-9: '${k}'" >&2; exit 2 ;; esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

set -a
# shellcheck disable=SC1091
. docker/versions.env
set +a

variant="standalone"
case "$stage" in
  S0) ;;
  S1) echo "S1(인스턴스 0)은 3단계부터 지원하지 않는다. 진단은 S1b(embedded)를 쓴다" >&2; exit 2 ;;
  S1b) variant="embedded" ;;
  S2|S3|S4|S5) ;;
  *) usage ;;
esac

run_id="${IDSIM_RUN_ID:-$(date -u +%Y%m%d-%H%M%S)-k${k}-$(tr '[:upper:]' '[:lower:]' <<<"$stage")}"
run_rel="artifacts/runs/${run_id}"
run_dir="${repo_root}/${run_rel}"
out_rel="${run_rel}/smoke"
out_dir="${repo_root}/${out_rel}"
project="idsim-${k}"
check_timeout=60

# stack.json 값 읽기(표준 라이브러리). 목록은 공백으로 잇고 null은 빈 문자열로 쓴다.
sj() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("schema") != 1:
    sys.exit("stack.json schema가 1이 아니다: %r" % d.get("schema"))
for k in sys.argv[2].split("."):
    d = d[int(k)] if k.isdigit() else d[k]
if d is None:
    print("")
elif isinstance(d, list):
    print(" ".join(str(x) for x in d))
elif isinstance(d, dict):
    print(" ".join("%s=%s" % kv for kv in sorted(d.items())))
else:
    print(d)' "${run_dir}/stack.json" "$1"
}

compose() {
  docker compose -f "${run_dir}/compose.yaml" "$@"
}

# ros-ws runner 컨테이너 안에서 명령을 한 번 실행한다(호스트 uid:gid, 작업 디렉터리 /opt/idsim).
# 모든 ROS 2 CLI는 --no-daemon으로 쓴다.
in_ros() {
  compose run --rm --no-deps -T "${run_env[@]}" "$runner" bash -c "$1"
}
run_env=()

# 이미지에 남긴 IDSIM_BUILD_* 값을 읽는다
image_env() {
  docker run --rm --entrypoint printenv "$1" "$2" 2>/dev/null || true
}

# S0: 이미지가 versions.env와 일치하고 필수 산출물이 있는지 본다. 스택을 올리지 않는다.
s0_fail=0
s0_expect() { # 이미지 변수이름 기대값
  local got
  got="$(image_env "$1" "IDSIM_BUILD_$2")"
  if [ "$got" = "$3" ]; then
    echo "ok   $1 IDSIM_BUILD_$2=$got"
  else
    echo "FAIL $1 IDSIM_BUILD_$2: 이미지 '${got}' != versions.env '$3' (이미지를 다시 빌드하라: python3 tools/ci/build_images.py --mode load <이미지>)" >&2
    s0_fail=1
  fi
}
s0_run() { # 설명 이미지 bash명령
  local log
  log="${out_dir}/s0_$(tr ' /' '__' <<<"$1").txt"
  if docker run --rm --entrypoint bash "$2" -c "$3" >"$log" 2>&1; then
    echo "ok   $2 $1"
  else
    echo "FAIL $2 $1 (${log})" >&2
    s0_fail=1
  fi
}
check_s0() {
  local gz_major img py
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
  # 생성기(ros-ws의 PyYAML)와 lint 잡의 단위 테스트(LINT_PYYAML_VERSION)가 같은 PyYAML을 쓰는지
  py="$(docker run --rm --entrypoint python3 idsim/ros-ws:local -c 'import yaml; print(yaml.__version__)' 2>/dev/null || true)"
  if [ "$py" = "$LINT_PYYAML_VERSION" ]; then
    echo "ok   idsim/ros-ws:local PyYAML=$py"
  else
    echo "FAIL idsim/ros-ws:local PyYAML '${py}' != versions.env LINT_PYYAML_VERSION '${LINT_PYYAML_VERSION}'" >&2
    s0_fail=1
  fi
  # shellcheck disable=SC2016
  s0_run "RMW_IMPLEMENTATION" idsim/ros-ws:local '[ "$(printenv RMW_IMPLEMENTATION)" = rmw_cyclonedds_cpp ]'
  s0_run "gz sim 버전" idsim/px4:local "gz sim --versions | grep -qE '^${gz_major}\\.'"
  # shellcheck disable=SC2016  # 컨테이너 안에서 전개해야 하므로 작은따옴표가 맞다
  s0_run "command -v px4" idsim/px4:local 'test "$(command -v px4)" = /opt/PX4-Autopilot/build/px4_sitl_default/bin/px4'
  # shellcheck disable=SC2016
  s0_run "px4-rc.mavlink idsim" idsim/px4:local 'test "$(command -v px4-rc.mavlink)" = /opt/idsim/px4/init.d-posix/px4-rc.mavlink'
  s0_run "px4 필수 파일" idsim/px4:local \
    'cd /opt/PX4-Autopilot/build/px4_sitl_default && test -x bin/px4 && test -f etc/init.d-posix/rcS && test -f /opt/px4-gz/models/x500/model.sdf && test -f /opt/px4-gz/server.config && test -f /opt/px4-gz/server.idsim.config'
  s0_run "MicroXRCEAgent --help" idsim/xrce-agent:local 'MicroXRCEAgent --help 2>&1 | grep -q "^Usage"'  # --help는 종료 코드 1을 돌려주므로 출력으로 판정한다
  for img in ros-ws px4 sim-base xrce-agent; do
    docker run --rm --entrypoint bash "idsim/${img}:local" -c 'dpkg -l | grep gz-transport || echo "gz-transport 패키지 없음"' \
      >"${out_dir}/gz_transport_${img}.txt" 2>&1 || true
  done
  return "$s0_fail"
}

# 토픽 판정은 check_px4.py 한 곳에 둔다. ros-ws 컨테이너 안에서 /opt/idsim 기준으로 실행한다.
# 결과 JSON은 stdout이고 종료 코드 0/1이 판정이다.
check_px4() {
  local args
  in_ros 'ros2 topic list -t --no-daemon --spin-time 10' >"${out_dir}/topic_list.txt" || true
  args="--ns ${px4_ns} --system-id ${sysid} --timeout ${check_timeout} $*"
  in_ros "cd /opt/idsim && python3 tests/smoke/check_px4.py ${args}" | tee "${out_dir}/check_px4.json"
}

# 아직 판정하지 못한 항목을 남긴다. stderr, 산출물(pending.txt), 마지막 줄 세 곳에 나타나므로 조용히 지나가지 않는다.
# origin_args가 $(...) 안에서 불리므로 변수 대신 파일에 쌓는다.
pending() {
  echo "PENDING $*" >&2
  echo "$*" >>"${out_dir}/pending.txt"
}

# 원점 판정 인자 --expect-origin LAT LON ALT. 원점이 없으면(embedded이거나 fleet.yaml에 origin이 없음) 넘기지 않는다.
origin_args() {
  local lat lon alt
  lat="$(sj world.origin.lat 2>/dev/null || true)"
  [ -n "$lat" ] || return 0
  lon="$(sj world.origin.lon)"
  alt="$(sj world.origin.alt)"
  echo "--expect-origin ${lat} ${lon} ${alt}"
}

# test-engineer의 tests.support.topic_info 호출. 종료 코드 0 통과, 1 판정 실패, 2 토픽 못 찾음.
topic_info() {
  in_ros "cd /opt/idsim && python3 -m tests.support.topic_info --ns ${px4_ns} $*"
}

# px4 컨테이너 안의 pxh 명령 판정 (check_px4_pxh.py, 표준 라이브러리만). JSON은 stdout, 종료 코드 0/1/2.
check_pxh() {
  # 기대 파라미터는 stack.json의 vehicles[0].expected_params(공통 파일 + 기체별 값을 생성기가 합친 것)와
  # derived_params(MAV_SYS_ID, UXRCE_DDS_KEY, UXRCE_DDS_DOM_ID, SYS_AUTOSTART. 1대에서는 간접 판정이 없다)
  local expect=() kv
  for kv in $(sj vehicles.0.expected_params) $(sj vehicles.0.derived_params); do
    expect+=(--expect-param "$kv")
  done
  if [ "${#expect[@]}" -eq 0 ]; then
    echo "stack.json에 expected_params가 없다" >&2
    return 1
  fi
  compose exec -T "$px4_svc" python3 - --instance "$instance" "${expect[@]}" <tests/smoke/check_px4_pxh.py \
    >"${out_dir}/pxh_${instance}.json"
}

# px4 서비스 로그에서 gz_bridge 오류와 MAVLink bind failed가 없는지 호스트에서 판정한다.
check_px4_log() {
  compose logs --no-color "$px4_svc" >"${out_dir}/${px4_svc}.log" 2>&1
  python3 tests/smoke/check_px4_pxh.py --log-file "${out_dir}/${px4_svc}.log" >"${out_dir}/px4log_${instance}.json"
}

# 모델 유일성: gazebo에 이 기체의 모델이 정확히 하나 있다(옛 모델 부착이나 중복 스폰이 아님)
check_model_unique() {
  local n
  compose exec -T "$gazebo_svc" gz model --list >"${out_dir}/gz_model_list.txt" 2>&1 || true
  n="$(grep -cE "^[[:space:]]*-[[:space:]]+${model}[[:space:]]*$" "${out_dir}/gz_model_list.txt" || true)"
  echo "model ${model}: ${n}개" | tee "${out_dir}/model_unique.txt"
  [ "$n" = "1" ] || { echo "FAIL: gz model --list에 ${model}이 정확히 하나가 아니다(${n}개)" >&2; return 1; }
}

# 같은 파티션에 다른 gz 서버가 없다: scene/info 서비스 제공자(tcp:// 줄)와 /clock 발행자가 각각 정확히 하나
check_single_gz_server() {
  local world part n_svc n_pub
  world="$(sj world.name)"
  part="$(sj stack.gz_partition)"
  compose exec -T "$gazebo_svc" gz service -i --service "/world/${world}/scene/info" >"${out_dir}/gz_scene_info.txt" 2>&1 || true
  compose exec -T "$gazebo_svc" gz topic -i -t /clock >"${out_dir}/gz_clock_info.txt" 2>&1 || true
  n_svc="$(grep -c 'tcp://' "${out_dir}/gz_scene_info.txt" || true)"
  # Publishers 절 아래 tcp:// 줄만 센다(Subscribers 절은 제외)
  n_pub="$(awk '/Publishers/{p=1;next} /Subscribers/{p=0} p&&/tcp:\/\//{n++} END{print n+0}' "${out_dir}/gz_clock_info.txt")"
  echo "gz 서버: scene/info 제공자 ${n_svc}, /clock 발행자 ${n_pub}" | tee "${out_dir}/gz_single_server.txt"
  if [ "$n_svc" != "1" ] || [ "$n_pub" != "1" ]; then
    echo "FAIL: 같은 파티션 ${part}에 다른 gz 서버가 있다. idsim-smoke 프로젝트나 수동 docker run을 내려라" >&2
    return 1
  fi
}

# 생성 시점의 cyclonedds.xml 해시(stack.json inputs.cyclonedds_xml.sha256)와 지금 파일을 대조한다.
# 런타임 컨테이너는 /opt/idsim 마운트의 현재 파일을 읽으므로 다르면 참가자 간 DDS 설정이 섞인 상태다.
# 다르면 0을 돌려주고 보고 줄을 stdout에 쓴다(두 호출처가 같은 줄을 쓴다).
dds_config_changed() {
  local want have
  want="$(sj inputs.cyclonedds_xml.sha256)"
  have="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "${repo_root}/config/cyclonedds.xml")"
  [ "$want" != "$have" ] || return 1
  echo "생성 뒤 cyclonedds.xml이 바뀌었다. bridge와 판정 참가자의 DDS 설정이 다르다"
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
    S1b)
      check_px4 \
        && topic_info "--regex '^/${px4_ns}/fmu/out/vehicle_status(_v[0-9]+)?\$' --expect-publishers 1 --expect-type px4_msgs/msg/VehicleStatus --save ${out_rel}/s1b_topic_info" ;;
    S2)
      local origin
      origin="$(origin_args)"
      # shellcheck disable=SC2086  # origin은 공백으로 나뉜 인자 넷이다
      check_model_unique && check_single_gz_server && check_px4 $origin && check_pxh && check_px4_log ;;
    S3)
      check_timeout=90
      check_px4 --arm \
        && topic_info "--regex '^/${px4_ns}/fmu/in/trajectory_setpoint(_v[0-9]+)?\$' --expect-subscriptions 1 --save ${out_rel}/s3_topic_info" ;;
    S4)
      local mode="--check"
      [ "$update_golden" -eq 1 ] && mode="--update"
      run_env=(-e "IDSIM_BUILD_PX4_TAG=$(image_env "$(sj images.px4)" IDSIM_BUILD_PX4_TAG)" \
               -e "IDSIM_BUILD_XRCE_AGENT_TAG=$(image_env "$(sj images.xrce_agent)" IDSIM_BUILD_XRCE_AGENT_TAG)")
      check_pxh \
        && in_ros "cd /opt/idsim && tests/smoke/capture.sh --ns ${px4_ns} ${out_rel}/ros" \
        && in_ros "cd /opt/idsim && python3 -m tests.support.normalize --raw ${out_rel}/ros --ns ${px4_ns} ${mode}" ;;
    S5)
      # 정보 수집(gz-transport 버전)은 실패해도 판정에 넣지 않으므로 먼저 하고, 마지막 명령이 판정이 되게 한다
      in_ros 'dpkg -l | grep gz-transport' >"${out_dir}/gz_transport_ros_ws.txt" || true
      compose exec -T "$gazebo_svc" bash -c 'dpkg -l | grep gz-transport' >"${out_dir}/gz_transport_gazebo.txt" || true
      topic_info "--regex '^/clock\$' --expect-publishers 1 --expect-type rosgraph_msgs/msg/Clock --save ${out_rel}/s5_topic_info" \
        && check_clock ;;
  esac
}

collect() {
  [ -f "${run_dir}/compose.yaml" ] || return 0
  if [ "$stage" != "S0" ] && [ -f "${run_dir}/stack.json" ]; then
    dds_config_changed >&2 || true
  fi
  compose logs --no-color >"${out_dir}/compose.log" 2>&1 || true
  if grep -i "bind error" "${out_dir}/compose.log" | grep -i "xrce-agent" >/dev/null 2>&1; then
    echo "에이전트 bind error: $(grep -i 'bind error' "${out_dir}/compose.log" | head -1)" >&2
  fi
  if grep -q "bind failed" "${out_dir}/compose.log"; then
    echo "px4 MAVLink bind failed: $(grep 'bind failed' "${out_dir}/compose.log" | head -1)" >&2
  fi
  echo "로그와 산출물: ${run_rel} (판정: ${out_rel}, ULog: ${run_rel}/px4-N/log)" >&2
}

cleanup() {
  [ "$stage" = "S0" ] || docker compose -p "$project" down --timeout 10 >/dev/null 2>&1 || true
}
trap cleanup EXIT

status=0
if [ "$stage" = "S0" ]; then
  mkdir -p "$out_dir"
  check_s0 || status=1
else
  SMOKE_UP_TIMEOUT="${SMOKE_UP_TIMEOUT:-240}"
  if STACK_UP_TIMEOUT="$SMOKE_UP_TIMEOUT" tools/stack.sh up --stack "$k" --variant "$variant" --run-dir "$run_dir" >/dev/null; then
    mkdir -p "$out_dir"
    runner="$(sj services.runner)"
    gazebo_svc="$(sj services.gazebo)"
    px4_svc="$(sj vehicles.0.service)"
    px4_ns="$(sj vehicles.0.px4_ns)"
    instance="$(sj vehicles.0.instance)"
    sysid="$(sj vehicles.0.sysid)"
    model="$(sj vehicles.0.gz_model_name)"
    if dds_config_changed >&2; then
      status=1
    else
      run_checks || status=1
    fi
  else
    mkdir -p "$out_dir"
    status=1
  fi
fi

if [ "$status" -ne 0 ]; then
  collect
  echo "${stage}: 실패" >&2
  exit 1
fi
collect
if [ -s "${out_dir}/pending.txt" ]; then
  echo "${stage}: 통과 (미판정 $(wc -l <"${out_dir}/pending.txt")건 PENDING, ${out_rel}/pending.txt)"
else
  echo "${stage}: 통과"
fi
