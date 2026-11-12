#!/usr/bin/env bash
# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# 이륙-호버-착륙 통합 테스트(시나리오 B, C, A, D, T)의 호스트 wrapper. 로컬과 CI(.github/workflows/sitl.yml)가 같은 명령을 쓴다.
#
# 사용법: tests/sitl/run_sitl.sh [--stack k] [--repeat N] [--attach <실행 디렉터리>] [-- pytest 인자...]
#   --stack k      스택 번호 0-9. 없으면 IDSIM_STACK_INDEX, 없으면 0
#   --repeat N     회마다 down 뒤 콜드 up으로 N번 돈다(회마다 실행 id가 다르다). 첫 실패에서 멈춘다(자동 재시도 없음)
#   --attach DIR   올리지도 내리지도 않고 이미 떠 있는 스택(DIR/compose.yaml)에 붙어 pytest와 수집만 한다
#                  (QGC와 Gazebo GUI 육안 확인, 디버깅). 산출물은 DIR/sitl-attach-<시각>/ 에 쓴다
#   --             이 뒤는 pytest에 그대로 넘긴다(예: -- -k test_b)
# 환경변수: SITL_PYTEST_TIMEOUT (pytest 전체의 벽시계 상한 초, 기본 900. CI timeout-minutes보다 짧게 둔다),
#           STACK_UP_TIMEOUT (sim_stack.sh up의 단계별 제한 초, 기본 240)
#
# 계약(.github/workflows/sitl.yml 머리 주석)
#   종료 코드  0 전체 통과, 1 시나리오, 정지 검사, ULog 교차 확인(비OFFBOARD ARMED) 실패, 2 사용법, 선행 조건, 스택 올리기(INFRA_UP), ULog 교차 확인 입력 없음
#   stdout     마지막 줄이 (마지막 회의) 실행 디렉터리 절대 경로 artifacts/runs/<실행 id>. 나머지는 모두 stderr
#   요약       GITHUB_STEP_SUMMARY가 있으면 단계별 초와 판정 구간 RTF를 표로 덧붙인다
#   산출물     <실행 디렉터리>/sitl/: junit.xml, trace.jsonl, verdict.json, summary.md, steps.tsv, raw_status_A.jsonl,
#              armed_a.json, crosscheck_a.json, rc.json(회차별 종료 코드), graph/(실패한 회의 노드, 토픽, QoS), ulog_check.txt, ps_before_stop.jsonl, stop_exit.txt, logs/<서비스>.log,
#              health_<서비스>.txt. 실행 디렉터리 안에는 compose.yaml, stack.json, params/, px4-N/log/*.ulg, ros_log/
#              --repeat이면 artifacts/sitl_repeat/<시각>-k<k>/ 에 repeat_summary.tsv, armed_criterion.json
#   소유       artifacts/runs/ 아래 파일은 모두 호스트 사용자 소유다(컨테이너를 호스트 uid:gid로 돌린다)
#
# 순서(회마다): sim_stack.sh up -> pytest(바깥 timeout) -> (Phase 2에 recorder 정지가 들어올 자리) -> stop 전 ps 기록,
#   compose stop -t 15 -> 종료 코드와 서비스 로그 수집 -> down. 중단돼도 trap으로 down이 돈다(--attach 제외).
# 스택은 tools/sim_stack.sh로만 올리고 내린다. 수집에만 docker compose ps/logs/stop과 inspect를 직접 쓴다.
# pytest를 다시 돌리는 재시도는 없다. 실패한 회의 증거는 그대로 남긴다.

set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root" || exit 2

say() { echo "run_sitl.sh: $*" >&2; }
usage() { sed -n '17,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }

k="${IDSIM_STACK_INDEX:-0}"
repeat=1
attach=""
pytest_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --stack) k="${2:?--stack 값}"; shift 2 ;;
    --stack=*) k="${1#*=}"; shift ;;
    --repeat) repeat="${2:?--repeat 값}"; shift 2 ;;
    --repeat=*) repeat="${1#*=}"; shift ;;
    --attach) attach="${2:?--attach 값}"; shift 2 ;;
    --attach=*) attach="${1#*=}"; shift ;;
    -h|--help) usage ;;
    --) shift; pytest_args=("$@"); break ;;
    *) say "모르는 인자: $1"; usage ;;
  esac
done
case "$k" in [0-9]) ;; *) say "스택 번호는 0-9: '${k}'"; exit 2 ;; esac
case "$repeat" in ''|*[!0-9]*|0) say "--repeat은 1 이상의 정수: '${repeat}'"; exit 2 ;; esac
if [ -n "$attach" ] && [ "$repeat" -ne 1 ]; then say "--attach는 --repeat과 함께 쓰지 않는다"; exit 2; fi

pytest_timeout="${SITL_PYTEST_TIMEOUT:-900}"
case "$pytest_timeout" in ''|*[!0-9]*) say "SITL_PYTEST_TIMEOUT은 정수 초: '${pytest_timeout}'"; exit 2 ;; esac

# 선행 조건: Executor 패키지가 빌드되어 있어야 한다(이 스크립트는 빌드하지 않는다)
if [ -z "$attach" ] && [ ! -d "${repo_root}/ros_ws/install/idsim_mission" ]; then
  say "ros_ws/install/idsim_mission/이 없다. 먼저 tools/ros_ws.sh build를 하라"
  exit 2
fi

up_done=0

# shellcheck disable=SC2329  # trap에서 불린다
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if [ "$up_done" -eq 1 ] && [ -z "$attach" ]; then
    say "정리: 스택 ${k}를 내린다"
    tools/sim_stack.sh down --stack "$k" >&2 || true
    up_done=0
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

now() { date +%s; }

# 한 회를 돈다. 결과는 전역 변수로 돌려준다: run_dir(절대), run_rc(0 통과, 1 실패, 2 INFRA_UP)
run_dir=""
run_rc=0
one_run() { # 회 번호
  local i="$1" ts run_id out_name compose steps="" t0 t1 rc fallback="" ops
  if [ -n "$attach" ]; then
    run_dir="$(cd "$attach" 2>/dev/null && pwd)" || { say "--attach 디렉터리가 없다: ${attach}"; run_rc=2; return; }
    [ -f "${run_dir}/compose.yaml" ] && [ -f "${run_dir}/stack.json" ] || {
      say "${run_dir}에 compose.yaml과 stack.json이 없다"; run_rc=2; return; }
    out_name="sitl-attach-$(date +%H%M%S)"
  else
    ts="$(date -u +%Y%m%d-%H%M%S)"
    run_id="${ts}-k${k}-sitl"
    [ "$repeat" -gt 1 ] && run_id="${run_id}-r${i}"
    run_dir="${repo_root}/artifacts/runs/${run_id}"
    out_name="sitl"
  fi
  case "$run_dir" in
    "${repo_root}"/*) ;;
    *) say "실행 디렉터리가 저장소 밖이다(runner가 /opt/idsim으로 마운트하는 범위 밖): ${run_dir}"; run_rc=2; return ;;
  esac
  local rel="${run_dir#"${repo_root}"/}"
  compose="${run_dir}/compose.yaml"

  if [ -z "$attach" ]; then
    say "== 회 ${i}/${repeat}: 스택 ${k} 올리기 (${run_id})"
    t0="$(now)"
    # 마지막 stdout 줄이 실행 디렉터리다. 안내는 stderr로 흐른다
    if ! STACK_UP_TIMEOUT="${STACK_UP_TIMEOUT:-240}" tools/sim_stack.sh up --stack "$k" --run-dir "$run_dir" >/dev/null; then
      up_done=1    # 일부 서비스가 떠 있을 수 있어 trap이 내리게 한다
      t1="$(now)"
      steps="up=$((t1 - t0))"
      say "스택 올리기 실패(INFRA_UP)"
      collect "$compose" "$run_dir" "$out_name" "" 
      fallback="INFRA_UP:tools/sim_stack.sh up이 실패했다(compose 로그는 ${out_name}/logs)"
      python3 tests/sitl/summarize.py run "$run_dir" --sitl-dir "$out_name" --steps "$steps" --fallback "$fallback" || true
      finish_summary "$run_dir" "$out_name" "$steps"
      run_rc=2
      return
    fi
    up_done=1
    t1="$(now)"
    steps="up=$((t1 - t0))"
  else
    say "== attach: ${run_dir} (출력 ${out_name})"
  fi

  mkdir -p "${run_dir}/${out_name}"
  say "pytest: runner 안에서 tests/sitl (바깥 timeout ${pytest_timeout} s)"
  t0="$(now)"
  # shellcheck disable=SC2016  # $1과 $@는 컨테이너 안의 bash가 푼다
  timeout --foreground -s INT -k 30 "$pytest_timeout" docker compose -f "$compose" run --rm --no-deps -T \
    -e IDSIM_SITL_OUT="$out_name" runner bash -c \
    'cd /opt/idsim && exec python3 -m pytest tests/sitl -p no:cacheprovider -ra --junitxml="$1" "${@:2}"' _ \
    "/opt/idsim/${rel}/${out_name}/junit.xml" ${pytest_args[@]+"${pytest_args[@]}"} >&2
  rc=$?
  t1="$(now)"
  steps="${steps:+${steps},}pytest=$((t1 - t0))"
  local pytest_rc="$rc"
  [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ] && say "pytest가 바깥 timeout ${pytest_timeout} s에 걸렸다(wrapper가 INT로 끊었다. 30 s 안에 안 끝나면 KILL)"
  # 실패 회의 graph snapshot(stop 전, 스택이 떠 있을 때): 노드, 토픽, 시나리오가 쓰는 토픽의 발행자/구독자 QoS
  [ "$pytest_rc" -ne 0 ] && graph_snapshot "$compose" "${run_dir}/${out_name}"

  # stop 전에 서비스 상태를 기록하고 running이 아닌 ops-N이 있으면 실패로 센다(정리 뒤에는 exit code 1이 정상이다)
  local stop_bad=0 cross_rc=0
  docker compose -f "$compose" ps -a --format json >"${run_dir}/${out_name}/ps_before_stop.jsonl" 2>/dev/null || true
  # shellcheck disable=SC2207  # 서비스 이름에는 공백이 없다
  ops=($(python3 - "${run_dir}/stack.json" <<'PY'
import json, sys
print(" ".join(json.load(open(sys.argv[1]))["services"].get("ops") or []))
PY
))
  if [ "${#ops[@]}" -gt 0 ]; then
    python3 tests/sitl/summarize.py ops-running "${run_dir}/${out_name}/ps_before_stop.jsonl" "${ops[@]}" || stop_bad=1
  fi

  t0="$(now)"
  if [ -z "$attach" ]; then
    # Phase 2에 recorder 정지가 들어올 자리
    say "compose stop -t 15 (ULog가 닫히는지 종료 코드를 남긴다)"
    docker compose -f "$compose" stop -t 15 >/dev/null 2>&1 || true
  fi
  collect "$compose" "$run_dir" "$out_name" "stop"
  t1="$(now)"
  steps="${steps},collect=$((t1 - t0))"

  if [ -z "$attach" ]; then
    t0="$(now)"
    tools/sim_stack.sh down --stack "$k" >&2 || true
    up_done=0
    t1="$(now)"
    steps="${steps},down=$((t1 - t0))"
  fi

  python3 tests/sitl/summarize.py ulog "$run_dir" --sitl-dir "$out_name" || true
  # 시나리오 A의 원시 표본과 ULog의 교차 확인. 종료 코드 1(ULog 기준 비OFFBOARD ARMED 표본)은 실행 실패,
  # 2(입력 없음)는 INFRA로 따로 센다
  python3 tests/sitl/crosscheck_a.py "$run_dir" --sitl-dir "$out_name" >&2
  local cross_rc=$?
  printf '%s\n' "$steps" | tr ',' '\n' | tr '=' '\t' >"${run_dir}/${out_name}/steps.tsv"
  python3 tests/sitl/summarize.py run "$run_dir" --sitl-dir "$out_name" --steps "$steps" \
    --fallback "NO_VERDICT:pytest가 verdict.json을 남기지 못했다(종료 코드 ${pytest_rc})"
  local summary_rc=$?
  finish_summary "$run_dir" "$out_name" "$steps"

  run_rc=0
  [ "$pytest_rc" -ne 0 ] && run_rc=1
  [ "$summary_rc" -ne 0 ] && run_rc=1
  [ "$stop_bad" -ne 0 ] && run_rc=1
  [ "$cross_rc" -eq 1 ] && run_rc=1
  if [ "$cross_rc" -ge 2 ]; then
    say "ULog 교차 확인 입력이 없다(INFRA)"
    [ "$run_rc" -eq 0 ] && run_rc=2
  fi
  printf '{"pytest": %s, "crosscheck": %s, "stop_check": %s, "final": %s}\n' "$pytest_rc" "$cross_rc" "$stop_bad" "$run_rc" \
    >"${run_dir}/${out_name}/rc.json"
  say "회 ${i}: pytest 종료 코드 ${pytest_rc}, ULog 교차 확인 ${cross_rc}, 정지 전 ops 상태 $([ "$stop_bad" -eq 0 ] && echo 정상 || echo 비정상), 결과 $([ "$run_rc" -eq 0 ] && echo 통과 || echo 실패)"
}

# 실패한 회의 graph snapshot. runner 안에서 ros2 CLI로 노드 목록, 토픽 목록과 시나리오가 쓰는 토픽의 발행자/구독자 QoS
# (ros2 topic info -v)를 sitl/graph/ 아래에 남긴다. 이미 실패한 회의 진단용이라 실패해도 넘어간다.
graph_snapshot() { # compose out_dir
  local compose="$1" out_dir="$2/graph"
  mkdir -p "$out_dir"
  say "실패한 회: graph snapshot을 ${out_dir#"${repo_root}"/}에 남긴다"
  # shellcheck disable=SC2016  # 컨테이너 안의 bash가 푼다
  timeout 150 docker compose -f "$compose" run --rm --no-deps -T runner bash -c '
    out="$1"; cd /opt/idsim
    ros2 node list --no-daemon > "$out/nodes.txt" 2>&1
    ros2 topic list -t --no-daemon > "$out/topics.txt" 2>&1
    pat="^/clock$|/mission_event$|/execute_mission/_action/|/fmu/out/(vehicle_status|vehicle_land_detected|vehicle_local_position|vehicle_command_ack|failsafe_flags)|/fmu/in/(vehicle_command|offboard_control_mode)"
    for t in $(awk "{print \$1}" "$out/topics.txt" | grep -E "$pat"); do
      ros2 topic info -v --no-daemon "$t" > "$out/info$(echo "$t" | tr / _).txt" 2>&1
    done' _ "/opt/idsim/${2#"${repo_root}"/}/graph" >/dev/null 2>&1 || say "graph snapshot이 끝나지 않았다(무시)"
}

# 서비스 종료 코드와 로그, healthcheck 기록을 모은다
collect() { # compose run_dir out_name stop|""
  local compose="$1" dir="$2" out="$3" svc cid out_dir
  out_dir="${dir}/${out}"
  mkdir -p "${out_dir}/logs"
  [ -f "$compose" ] || return 0
  docker compose -f "$compose" ps -a --format '{{.Service}} {{.State}} exit={{.ExitCode}}' >"${out_dir}/stop_exit.txt" 2>&1 || true
  for svc in $(docker compose -f "$compose" ps -a --services 2>/dev/null); do
    docker compose -f "$compose" logs --no-color --timestamps "$svc" >"${out_dir}/logs/${svc}.log" 2>&1 || true
    cid="$(docker compose -f "$compose" ps -a -q "$svc" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      docker inspect --format '{{range .State.Health.Log}}{{.Start}} -> {{.End}} exit={{.ExitCode}} {{.Output}}{{"\n"}}{{end}}' "$cid" \
        >"${out_dir}/health_${svc}.txt" 2>&1 || true
    fi
  done
}

# GITHUB_STEP_SUMMARY에 단계별 초와 RTF를 표로 덧붙인다
finish_summary() { # run_dir out_name steps
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  local dir="$1" out="$2" steps="$3" rtf
  rtf="$(python3 - "${dir}/${out}/verdict.json" <<'PY' 2>/dev/null || echo "-"
import json, sys
v = json.load(open(sys.argv[1]))
r = v.get("rtf") or {}
print("%s (ROS 시각 %s s / 벽시계 %s s)" % (r.get("rtf"), r.get("sim_s"), r.get("wall_s")))
PY
)"
  {
    echo "| sitl 단계 (${dir##*/}) | 초 |"
    echo "| --- | --- |"
    printf '%s\n' "$steps" | tr ',' '\n' | awk -F= '{printf "| %s | %s |\n", $1, $2}'
    echo "| 판정 구간 RTF | ${rtf} |"
  } >>"$GITHUB_STEP_SUMMARY"
}

group_ts="$(date -u +%Y%m%d-%H%M%S)"
group_dir="${repo_root}/artifacts/sitl_repeat/${group_ts}-k${k}"
verdicts=()
final_rc=0
last_dir=""
for ((i = 1; i <= repeat; i++)); do
  one_run "$i"
  last_dir="$run_dir"
  [ -f "${run_dir}/sitl/verdict.json" ] && verdicts+=("${run_dir}/sitl/verdict.json")
  if [ "$run_rc" -ne 0 ]; then
    final_rc="$run_rc"
    [ "$i" -lt "$repeat" ] && say "회 ${i}이 실패해 멈춘다(실패가 나오면 0부터 다시 센다. 재시도하지 않는다)"
    break
  fi
done

if [ -z "$attach" ] && [ "${#verdicts[@]}" -gt 0 ]; then
  python3 tests/sitl/summarize.py repeat --out "$group_dir" "${verdicts[@]}" >&2 || true
  say "회차 요약: ${group_dir}/repeat_summary.tsv"
fi

say "종료 코드 ${final_rc}. 실행 디렉터리: ${last_dir}"
[ -n "$last_dir" ] && printf '%s\n' "$last_dir"
exit "$final_rc"
