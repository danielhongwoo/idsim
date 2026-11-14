#!/usr/bin/env bash
# idsim 스택 운영 스크립트(호스트). 생성(tools/gen_compose.sh)과 docker compose 호출을 묶는다.
#
# 사용법
#   tools/sim_stack.sh up   [--stack k] [--fleet f] [--viz] [--infra-only] [--variant standalone|embedded] [--run-dir 경로]
#   tools/sim_stack.sh down [--stack k]
#   tools/sim_stack.sh logs [--stack k] [docker compose logs 인자...]
#   tools/sim_stack.sh ps   [--stack k]
#   tools/sim_stack.sh restart-ops [--stack k] [--vehicle N] [--build] [--force] [--run-dir 경로]
#   k는 --stack, 없으면 IDSIM_STACK_INDEX, 없으면 0. compose 프로젝트 이름은 idsim-<k>.
#
# up이 하는 일(인자 없는 up 한 번이 사용자 진입점이다)
#   1. 같은 프로젝트(idsim-<k>)가 떠 있으면 먼저 내린다(항상 down 뒤 up. 옛 모델이 남은 Gazebo에 px4가
#      다시 붙는 조용한 실패를 막는다).
#   2. tools/gen_compose.sh로 artifacts/runs/<실행 id>/에 compose.yaml, stack.json, world/<월드>.sdf(standalone)를 만든다.
#      아무것도 올리기 전에 생성된 월드 파일이 있고 <spherical_coordinates> 요소가 정확히 하나인지 본다(원점은 이 파일로만 들어간다).
#   3. stack.json의 startup.stages를 차례로 `up -d --wait`한다. 세 단계(standalone): 1단계(에이전트, gazebo),
#      2단계(px4-N), 3단계(bridge). embedded는 두 단계(에이전트, px4-1). standalone은 1단계 뒤
#      sim-base 1회성 컨테이너로 같은 GZ_PARTITION의 `gz model --list`에 이 스택의 모델(<모델>_N)이 없는지
#      확인하고(startup.model_precheck) 같은 파티션의 gz 서버가 하나뿐인지도 본다(scene/info 제공자 1, /clock 발행자 1). bridge는 px4-N이 healthy가 된 뒤에만 시작하므로 실패한 단계 번호가 원인을 가른다.
#   4. 노드 단계: stack.json의 startup.node_stages(standalone은 ops-N 전부, targets(표적이 있으면), sim-oracle이 한 단계)를 `up -d --wait`한다.
#      ops-N의 healthcheck는 Mission Executor 노드가 lifecycle active인지 본다(노드가 스스로 전이한다).
#      targets와 sim-oracle의 healthcheck는 각 노드가 만드는 표시 파일이다(sim-oracle은 sim-base 이미지에서 마운트한 sim_oracle.py를 돌리므로 ros_ws 빌드가 필요 없다).
#      --infra-only면 이 단계를 건너뛴다(Executor, 표적 어댑터, sim-oracle 없이 인프라만. 스모크와 측정 스크립트가 쓴다).
#      ros_ws/install/idsim_mission/이 없으면(표적이 있으면 ros_ws/install/idsim_sim/도) 아무것도 올리기 전에
#      안내와 함께 실패한다(tools/ros_ws.sh build). sim-oracle이 있으면 ros_ws/src/idsim_sim/scripts/sim_oracle.py가 없을 때도 같다.
#      embedded 변형에는 노드 단계가 없다.
#   5. --viz면 viz 프로필(gz-gui, foxglove, lichtblick)을 `up -d`로 붙인다(기다리지 않는다. healthcheck 없음).
#   6. 실패하면 unhealthy 또는 exited 서비스 이름을 한 줄로 찍고, 에이전트 로그의 "bind error"와 px4 로그의 "bind failed"를 찾아 보고하고 종료 코드 1.
#      노드 단계가 실패하면 ops-N, targets, sim-oracle의 로그 끝과 .State.Health.Log도 찍는다.
#      스택은 조사할 수 있게 그대로 두며 `tools/sim_stack.sh down`으로 내린다.
#   성공하면 실행 디렉터리의 절대 경로 한 줄을 stdout에 쓴다(안내는 stderr).
#
# restart-ops가 하는 일(개발 반복용. 떠 있는 스택은 그대로 두고 Mission Executor 컨테이너만 새 ros_ws/install로 다시 만든다)
#   ops-N은 저장소 전체를 bind mount하므로 ros_ws/install이 곧 코드다. 이미지는 바뀌지 않는다.
#   1. 실행 디렉터리를 --run-dir, 없으면 떠 있는 idsim-<k> 컨테이너의 compose 파일 label에서 찾는다.
#   2. --build면 tools/ros_ws.sh build를 먼저 한다(없으면 이미 빌드했다고 본다).
#   3. gazebo, px4-N, bridge가 running이어야 한다. 아니면 up을 먼저 하라고 하고 끝낸다.
#   4. 대상 기체(--vehicle N, 없으면 전부)가 지상 DISARMED(vehicle_status arming_state)인지 runner 1회성 컨테이너로 본다.
#      아니면 거부한다(공중이나 ARMED에서 Executor를 다시 띄우면 기체 상태가 새 노드와 어긋난다). --force면 건너뛴다.
#   5. `up -d --force-recreate --no-deps --wait ops-N`. healthcheck(lifecycle active)가 healthy가 될 때까지 기다린다.
#   그 뒤 tests/sitl/run_sitl.sh --attach <실행 디렉터리> -- -k <시나리오>로 시나리오를 돌린다.
#   스택에 있는 다른 서비스(px4, bridge, targets, sim-oracle)와 compose 파일은 건드리지 않으므로 생성기 출력과 무관하다.
#
# 환경변수: STACK_UP_TIMEOUT (단계별 up --wait 제한 초, 기본 240)

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }
say() { echo "sim_stack.sh: $*" >&2; }

[ "$#" -ge 1 ] || usage
cmd="$1"; shift
# --옵션=값 형식은 --옵션 값으로 펼친다(값 있는 옵션만)
_expanded=()
for _a in "$@"; do
  case "$_a" in
    --stack=*|--fleet=*|--variant=*|--run-dir=*|--vehicle=*) _expanded+=("${_a%%=*}" "${_a#*=}") ;;
    *) _expanded+=("$_a") ;;
  esac
done
set -- ${_expanded[@]+"${_expanded[@]}"}
stack="${IDSIM_STACK_INDEX:-0}"
fleet=""
viz=0
infra_only=0
vehicle=""
do_build=0
force=0
variant="standalone"
run_dir=""
rest=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --stack) stack="${2:?--stack 값}"; shift 2 ;;
    --fleet) fleet="${2:?--fleet 값}"; shift 2 ;;
    --variant) variant="${2:?--variant 값}"; shift 2 ;;
    --run-dir) run_dir="${2:?--run-dir 값}"; shift 2 ;;
    --vehicle) vehicle="${2:?--vehicle 값}"; shift 2 ;;
    --build) do_build=1; shift ;;
    --force) force=1; shift ;;
    --viz) viz=1; shift ;;
    --infra-only) infra_only=1; shift ;;
    -h|--help) usage ;;
    *) rest+=("$1"); shift ;;
  esac
done
case "$stack" in [0-9]) ;; *) say "스택 번호는 0-9: '${stack}'"; exit 2 ;; esac
project="idsim-${stack}"
up_timeout="${STACK_UP_TIMEOUT:-240}"

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
elif isinstance(d, bool):
    print("true" if d else "false")
elif isinstance(d, list):
    print(" ".join(str(x) for x in d))
else:
    print(d)' "$1" "$2"
}

stack_down() {
  # 파일 없이 프로젝트 이름으로 내린다(프로필 서비스 포함, 어느 실행 디렉터리에서 올렸든 같다)
  docker compose -p "$1" down --timeout 10 >&2
}

# 실패 진단: 에이전트 bind error, px4 bind failed
report_bind_errors() { # compose파일 stack.json
  local f="$1" sf="$2" found=0 svc
  if docker compose -f "$f" logs --no-color "$(sj "$sf" services.agent)" 2>/dev/null | grep -i "bind error"; then
    say "에이전트 포트 $(sj "$sf" stack.agent_port)/udp bind 실패. 다른 스택이나 프로세스가 쓰고 있다(다른 --stack을 쓰라)"
    found=1
  fi
  for svc in $(sj "$sf" services.px4); do
    if docker compose -f "$f" logs --no-color "$svc" 2>/dev/null | grep "bind failed"; then
      say "${svc}: MAVLink 포트 bind 실패(WARN  [mavlink] bind failed). 같은 스택 번호의 다른 스택이 떠 있는지 보라"
      found=1
    fi
  done
  [ "$found" -eq 1 ] || say "bind 오류는 찾지 못했다. 'tools/sim_stack.sh logs --stack ${stack}'로 로그를 보라"
}

# 노드 단계 실패 진단: ops-N, targets, sim-oracle 로그 끝과 healthcheck 기록(어느 전이가 왜 실패했는지는 노드의 ERROR 로그에 있다)
report_node_failure() { # compose파일 stack.json
  local f="$1" sf="$2" svc cid
  for svc in $(sj "$sf" services.ops) $(sj "$sf" services.targets) $(sj "$sf" services.sim_oracle); do
    say "---- ${svc} 로그 끝(80줄)"
    docker compose -f "$f" logs --no-color --tail 80 "$svc" >&2 2>&1 || true
    cid="$(docker compose -f "$f" ps -a -q "$svc" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      say "---- ${svc} healthcheck 기록(.State.Health.Log. 시작 -> 끝, 종료 코드, 출력)"
      docker inspect --format '{{range .State.Health.Log}}{{.Start}} -> {{.End}} exit={{.ExitCode}} {{.Output}}{{"\n"}}{{end}}' "$cid" >&2 || true
    fi
  done
}

# 1단계 뒤: 같은 파티션의 gz 서버에 이 스택의 모델이 이미 있는지 본다
model_precheck() { # stack.json
  local sf="$1" out models m
  out="$(docker run --rm --network host \
    -e GZ_PARTITION="$(sj "$sf" stack.gz_partition)" -e GZ_IP="$(sj "$sf" stack.gz_ip)" -e HOME=/tmp \
    "$(sj "$sf" images.sim_base)" gz model --list 2>&1)" || true
  printf '%s\n' "$out" > "$(dirname "$sf")/model_precheck.txt"
  if ! printf '%s\n' "$out" | grep -q "Available models"; then
    say "모델 사전 검사 실패: gz model --list 응답이 없다 ($(dirname "$sf")/model_precheck.txt)"
    return 1
  fi
  models="$(python3 -c 'import json,sys; print(" ".join(v["gz_model_name"] for v in json.load(open(sys.argv[1]))["vehicles"]))' "$sf")"
  for m in $models; do
    if printf '%s\n' "$out" | grep -qE "^[[:space:]]*-[[:space:]]+${m}[[:space:]]*$"; then
      say "모델 사전 검사 실패: px4를 올리기 전에 ${m}이 이미 있다(같은 GZ_PARTITION에 다른 gazebo가 떠 있다)"
      return 1
    fi
  done
  gz_unique_check "$sf" || return 1
  say "모델 사전 검사 통과: ${models} 없음, gz 서버 1개"
}

# 같은 파티션에 gz 서버가 정확히 하나인지 본다. 둘 이상이면 px4가 두 서버의 센서를 섞어 받아 timestamp error가 난다.
# 기준: scene/info 서비스의 provider(tcp://) 줄 수와 /clock 발행자 수가 각각 정확히 1
gz_unique_check() { # stack.json
  local sf="$1" world k svc_out clk_out n_prov n_pub
  world="$(sj "$sf" world.name)"
  k="$(sj "$sf" stack.index)"
  svc_out="$(docker run --rm --network host \
    -e GZ_PARTITION="$(sj "$sf" stack.gz_partition)" -e GZ_IP="$(sj "$sf" stack.gz_ip)" -e HOME=/tmp \
    "$(sj "$sf" images.sim_base)" gz service -i --service "/world/${world}/scene/info" 2>&1)" || true
  clk_out="$(docker run --rm --network host \
    -e GZ_PARTITION="$(sj "$sf" stack.gz_partition)" -e GZ_IP="$(sj "$sf" stack.gz_ip)" -e HOME=/tmp \
    "$(sj "$sf" images.sim_base)" gz topic -i -t /clock 2>&1)" || true
  printf '%s\n---\n%s\n' "$svc_out" "$clk_out" > "$(dirname "$sf")/model_precheck_gz.txt"
  n_prov="$(printf '%s\n' "$svc_out" | grep -c 'tcp://' || true)"
  # Publishers 절 아래 tcp:// 줄만 센다(Subscribers 절은 제외)
  n_pub="$(printf '%s\n' "$clk_out" | awk '/Publishers/{p=1;next} /Subscribers/{p=0} p&&/tcp:\/\//{n++} END{print n+0}')"
  if [ "$n_prov" -ne 1 ] || [ "$n_pub" -ne 1 ]; then
    say "gz 서버 검사 실패: scene/info provider ${n_prov}개, /clock 발행자 ${n_pub}개(각각 정확히 1이어야 한다)"
    say "같은 파티션 idsim-${k}에 다른 gz 서버가 있다. idsim-smoke 프로젝트나 수동 docker run을 내려라(응답: $(dirname "$sf")/model_precheck_gz.txt)"
    return 1
  fi
}

# unhealthy 또는 exited 서비스 이름을 한 줄로 찍는다
report_bad_services() { # compose파일
  local bad
  bad="$(docker compose -f "$1" ps -a --format json 2>/dev/null | python3 -c '
import json, sys
bad = []
for line in sys.stdin.read().splitlines():
    line = line.strip()
    if not line:
        continue
    items = json.loads(line)
    for d in items if isinstance(items, list) else [items]:
        if d.get("State") == "exited" or d.get("Health") == "unhealthy":
            bad.append("%s(%s)" % (d.get("Service"), d.get("Health") or d.get("State")))
print(" ".join(bad))' 2>/dev/null)" || bad=""
  if [ -n "$bad" ]; then say "문제 서비스: ${bad}"; else say "unhealthy 또는 exited 서비스는 없다(시간 초과일 수 있다)"; fi
}

do_up() {
  local existing sf f stage i n_stages n_node_stages world_rel world_file n_sc
  existing="$(docker ps -a -q --filter "label=com.docker.compose.project=${project}")"
  if [ -n "$existing" ]; then
    say "떠 있는 ${project}를 먼저 내린다"
    stack_down "$project"
  fi
  local gen=(--stack "$stack" --variant "$variant")
  [ -n "$fleet" ] && gen+=(--fleet "$fleet")
  [ -n "$run_dir" ] && gen+=(--run-dir "$run_dir")
  run_dir="$("${repo_root}/tools/gen_compose.sh" "${gen[@]}" | tail -n 1)"
  sf="${run_dir}/stack.json"
  f="${run_dir}/$(sj "$sf" run.compose_file)"
  [ "$(sj "$sf" stack.compose_project)" = "$project" ] || { say "stack.json 프로젝트가 ${project}가 아니다"; exit 1; }
  say "생성: ${f}"
  world_rel="$(sj "$sf" world.file)"
  if [ -n "$world_rel" ]; then
    world_file="${run_dir}/${world_rel}"
    [ -f "$world_file" ] || { say "생성된 월드 파일이 없다: ${world_file}"; exit 1; }
    n_sc="$(grep -o '<spherical_coordinates' "$world_file" | wc -l || true)"
    [ "$n_sc" = "1" ] || { say "월드 파일의 <spherical_coordinates>가 정확히 하나가 아니다(${n_sc}개): ${world_file}"; exit 1; }
  fi
  n_node_stages="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["startup"]["node_stages"]))' "$sf")"
  if [ "$infra_only" -eq 0 ] && [ "$n_node_stages" -gt 0 ] && [ ! -d "${repo_root}/ros_ws/install/idsim_mission" ]; then
    say "ros_ws/install/idsim_mission/이 없다. 노드 단계를 올릴 수 없다. 먼저 tools/ros_ws.sh build를 하라(Executor 없이 인프라만 올리려면 --infra-only)"
    exit 1
  fi
  if [ "$infra_only" -eq 0 ] && [ -n "$(sj "$sf" services.targets)" ] && [ ! -d "${repo_root}/ros_ws/install/idsim_sim" ]; then
    say "ros_ws/install/idsim_sim/이 없다. 표적 어댑터(targets)를 올릴 수 없다. 먼저 tools/ros_ws.sh build를 하라(인프라만 올리려면 --infra-only)"
    exit 1
  fi
  if [ "$infra_only" -eq 0 ] && [ -n "$(sj "$sf" services.sim_oracle)" ] && [ ! -f "${repo_root}/ros_ws/src/idsim_sim/scripts/sim_oracle.py" ]; then
    say "ros_ws/src/idsim_sim/scripts/sim_oracle.py가 없다. 정답 pose 공급자(sim-oracle)를 올릴 수 없다(인프라만 올리려면 --infra-only)"
    exit 1
  fi
  n_stages="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["startup"]["stages"]))' "$sf")"
  for ((i = 0; i < n_stages; i++)); do
    # shellcheck disable=SC2207  # 서비스 이름에는 공백이 없다
    stage=($(sj "$sf" "startup.stages.${i}"))
    say "단계 $((i + 1))/${n_stages}: up --wait ${stage[*]}"
    if ! docker compose -f "$f" up -d --wait --wait-timeout "$up_timeout" "${stage[@]}" >&2; then
      say "단계 $((i + 1))/${n_stages} 실패(${stage[*]})"
      report_bad_services "$f"
      report_bind_errors "$f" "$sf"
      docker compose -f "$f" ps -a >&2 || true
      say "스택은 그대로 두었다. 내리려면: tools/sim_stack.sh down --stack ${stack}"
      exit 1
    fi
    if [ "$i" -eq 0 ] && [ "$(sj "$sf" startup.model_precheck)" = "true" ]; then
      model_precheck "$sf" || { say "스택은 그대로 두었다. 내리려면: tools/sim_stack.sh down --stack ${stack}"; exit 1; }
    fi
  done
  if [ "$infra_only" -eq 1 ]; then
    say "--infra-only: 노드 단계(ops-N, targets, sim-oracle)를 올리지 않았다"
  else
    for ((i = 0; i < n_node_stages; i++)); do
      # shellcheck disable=SC2207  # 서비스 이름에는 공백이 없다
      stage=($(sj "$sf" "startup.node_stages.${i}"))
      say "노드 단계 $((i + 1))/${n_node_stages}: up --wait ${stage[*]}"
      if ! docker compose -f "$f" up -d --wait --wait-timeout "$up_timeout" "${stage[@]}" >&2; then
        say "노드 단계 $((i + 1))/${n_node_stages} 실패(${stage[*]})"
        report_bad_services "$f"
        report_node_failure "$f" "$sf"
        docker compose -f "$f" ps -a >&2 || true
        say "스택은 그대로 두었다. 내리려면: tools/sim_stack.sh down --stack ${stack}"
        exit 1
      fi
    done
  fi
  if [ "$viz" -eq 1 ]; then
    local vs
    vs="$(sj "$sf" services.profiles.viz)"
    if [ -z "$vs" ]; then
      say "이 변형(${variant})에는 viz 서비스가 없다"
    else
      [ -n "${DISPLAY:-}" ] || say "경고: DISPLAY가 비어 있다. gz-gui가 안내와 함께 끝난다"
      [ -n "${XAUTHORITY:-}" ] || say "경고: XAUTHORITY가 비어 있다. gz-gui가 안내와 함께 끝난다"
      # shellcheck disable=SC2086
      docker compose -f "$f" --profile viz up -d $vs >&2
      local lp fp
      lp="$(sj "$sf" stack.lichtblick_port)"
      fp="$(sj "$sf" stack.foxglove_port)"
      if [ -n "$lp" ] && [ -n "$fp" ]; then
        say "Lichtblick: http://127.0.0.1:${lp}/?ds=foxglove-websocket&ds.url=ws://127.0.0.1:${fp}"
      fi
    fi
  fi
  say "준비됨: ${project} (stack.json: ${sf})"
  say "QGC: tools/qgc.sh --stack ${stack}   내리기: tools/sim_stack.sh down --stack ${stack}"
  printf '%s\n' "$run_dir"
}

# 떠 있는 스택의 실행 디렉터리를 찾는다(--run-dir이 없을 때). compose 파일 label에서 얻는다.
find_run_dir() {
  local cid cf
  cid="$(docker ps -a -q --filter "label=com.docker.compose.project=${project}" | head -n 1)"
  [ -n "$cid" ] || return 1
  cf="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$cid")"
  [ -n "$cf" ] || return 1
  dirname "${cf%%,*}"
}

# 기체 하나가 지상 DISARMED인지 본다(runner 1회성 컨테이너로 vehicle_status 한 표본을 읽는다)
vehicle_on_ground() { # compose파일 기체이름(ops-N의 N)
  local f="$1" n="$2" out
  out="$(docker compose -f "$f" run --rm --no-deps -T runner bash -c \
    ". /opt/ros/\${ROS_DISTRO}/setup.sh; . /opt/idsim/ros_ws/install/setup.bash; \
     ROS_LOG_DIR=/tmp/hc timeout 15 ros2 topic echo --once --no-daemon --field arming_state /px4_${n}/fmu/out/vehicle_status_v1" 2>/dev/null | head -n 1 | tr -d '[:space:]')" || out=""
  case "$out" in
    1) return 0 ;;
    "") say "기체 ${n}: vehicle_status를 읽지 못했다(--force로 건너뛸 수 있다)"; return 1 ;;
    *) say "기체 ${n}: arming_state=${out}(1이 DISARMED). 지상 DISARMED가 아니다"; return 1 ;;
  esac
}

do_restart_ops() {
  local rd sf f svcs n s running bad=""
  if [ -n "$run_dir" ]; then rd="$run_dir"; else rd="$(find_run_dir)" || { say "떠 있는 ${project}를 찾지 못했다. 먼저 tools/sim_stack.sh up --stack ${stack}"; exit 1; }; fi
  sf="${rd}/stack.json"
  [ -f "$sf" ] || { say "${rd}에 stack.json이 없다"; exit 1; }
  f="${rd}/$(sj "$sf" run.compose_file)"
  [ "$(sj "$sf" stack.compose_project)" = "$project" ] || { say "stack.json 프로젝트가 ${project}가 아니다"; exit 1; }
  # shellcheck disable=SC2207
  svcs=($(sj "$sf" services.ops))
  [ "${#svcs[@]}" -gt 0 ] || { say "이 스택에는 ops 서비스가 없다(variant ${variant}나 --infra-only)"; exit 1; }
  if [ -n "$vehicle" ]; then
    case "$vehicle" in ''|*[!0-9]*) say "--vehicle은 기체 번호(정수): '${vehicle}'"; exit 2 ;; esac
    [[ " ${svcs[*]} " == *" ops-${vehicle} "* ]] || { say "ops-${vehicle}가 없다(있는 것: ${svcs[*]})"; exit 1; }
    svcs=("ops-${vehicle}")
  fi
  if [ "$do_build" -eq 1 ]; then
    say "tools/ros_ws.sh build"
    "${repo_root}/tools/ros_ws.sh" build >&2 || { say "빌드 실패. ops를 다시 띄우지 않았다"; exit 1; }
  fi
  [ -d "${repo_root}/ros_ws/install/idsim_mission" ] || { say "ros_ws/install/idsim_mission/이 없다. tools/ros_ws.sh build를 하라"; exit 1; }
  running="$(docker compose -f "$f" ps --status running --format '{{.Service}}')"
  for s in $(sj "$sf" services.gazebo) $(sj "$sf" services.px4) $(sj "$sf" services.bridge); do
    printf '%s\n' "$running" | grep -qx "$s" || bad="${bad} ${s}"
  done
  [ -z "$bad" ] || { say "running이 아닌 서비스:${bad}. 스택이 온전하지 않다. tools/sim_stack.sh up --stack ${stack}"; exit 1; }
  if [ "$force" -eq 0 ]; then
    for s in "${svcs[@]}"; do
      vehicle_on_ground "$f" "${s#ops-}" || { say "거부: ${s}를 다시 띄우지 않았다(기체를 착륙시키고 DISARMED를 기다리거나 --force)"; exit 1; }
    done
  fi
  say "다시 만든다: ${svcs[*]}"
  if ! docker compose -f "$f" up -d --force-recreate --no-deps --wait --wait-timeout "$up_timeout" "${svcs[@]}" >&2; then
    say "ops 재시작 실패"
    report_bad_services "$f"
    report_node_failure "$f" "$sf"
    exit 1
  fi
  say "준비됨: ${svcs[*]}"
  say "다음: tests/sitl/run_sitl.sh --stack ${stack} --attach ${rd} -- -k <시나리오>"
  printf '%s\n' "$rd"
}

case "$cmd" in
  up) do_up ;;
  restart-ops) do_restart_ops ;;
  down) stack_down "$project" ;;
  logs) docker compose -p "$project" logs "${rest[@]}" ;;
  ps) docker compose -p "$project" ps -a ;;
  *) usage ;;
esac
