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

# PX4 재실측 (2), (3), (5)와 ARMED 표본 기록의 호스트 실행기.
#
# 사용법: tests/sitl/measure/run_measure.sh [--stack k] [--attempts N] [--keep] <item>...
#   item: item2 (재실측 2), item3 (재실측 3), item5 (재실측 5), armed (PX4 직접 명령, Executor 없음), all
#   --attempts N   모든 item의 시도 수(기본: item2 3, item3 27, item5 10, armed 10). item3은 9의 배수만 받는다
#                  (지연값 아홉 개 x 3회). item3과 다른 item을 같이 돌릴 때는 쓰지 않는다
#   --keep         끝나도 스택을 내리지 않는다
#   스택 번호 기본값은 7(실험용). 0은 사용자 스택이라 IDSIM_MEASURE_ALLOW_STACK0=1 없이는 거부한다.
#   MEASURE_ARGS    measure.py에 그대로 넘길 인자(예: "--observe-s 20 --delays 0,0.1")
#
# 하는 일
#   1. tools/sim_stack.sh up으로 스택을 올린다(떠 있는 idsim-<k>는 먼저 내려진다).
#   2. item마다 runner 안에서 tests/sitl/measure/measure.py를 돌린다. 시도마다 한 줄이 쌓인다.
#   3. 스택을 compose stop -t 15로 멈추고(ULog가 닫히는지 보려고 서비스별 종료 코드를 stop_exit.txt에
#      남긴다) 호스트에서 crosscheck.py로 ULog의 vehicle_status와 교차 확인한다.
#   4. 스택을 내린다.
# 산출물은 artifacts/runs/<실행 id>/measure/ 아래다(실행 id 기본: <UTC 시각>-k<k>-measure, IDSIM_RUN_ID로 지정).
#   measure_<item>.jsonl, raw_<item>.jsonl, summary_<item>.txt, distribution_<item>.json,
#   crosscheck_<item>.json, armed_criterion.json, run_<item>.log, stop_exit.txt, compose.log
# 종료 코드: 0 모두 통과, 1 기준과 다른 관측(FAIL, ARMED 위반. 문서의 기대가 반증됐다는 뜻이며 PX4 결함이라는
#   뜻이 아니다. 2보다 앞선다), 2 기계가 판정하지 않음(COND_NOT_REACHED, HOLD_END, INCONCLUSIVE, WINDOW_MISSED,
#   PRECONDITION, 시도 수 부족, 인프라, 예상 밖의 종료 코드). 0은 PX4 직접 부류의 통과이며 P4 머지 조건은
#   Executor 경유 부류(시나리오 A)의 통과가 따로 필요하다.
# 이 스크립트는 판정을 느슨하게 만들지 않는다. 통과 기준은 summary_<item>.txt 머리와 measure.py에 있다.

set -uo pipefail

usage() { sed -n '15,/^$/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

k="${IDSIM_STACK_INDEX:-7}"
attempts=""
keep=0
items=()
while [ $# -gt 0 ]; do
  case "$1" in
    --stack) k="${2:?--stack 값}"; shift 2 ;;
    --attempts) attempts="${2:?--attempts 값}"; shift 2 ;;
    --keep) keep=1; shift ;;
    -h|--help) usage ;;
    item2|item3|item5|armed) items+=("$1"); shift ;;
    all) items+=(item3 item5 item2 armed); shift ;;
    *) usage ;;
  esac
done
[ "${#items[@]}" -gt 0 ] || usage
# 같은 item을 두 번 돌리면 기록이 섞이거나 덮어써지므로 거부한다(measure.py도 기존 기록을 거부한다)
if [ "$(printf '%s\n' "${items[@]}" | sort | uniq -d | wc -l)" -gt 0 ]; then
  echo "같은 item이 중복되었다: ${items[*]}" >&2
  exit 2
fi
case "$k" in [0-9]) ;; *) echo "스택 번호는 0-9: '${k}'" >&2; exit 2 ;; esac
if [ "$k" = "0" ] && [ "${IDSIM_MEASURE_ALLOW_STACK0:-}" != "1" ]; then
  echo "스택 0은 사용자 스택이다. 다른 번호를 쓰거나 IDSIM_MEASURE_ALLOW_STACK0=1을 준다" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root" || exit 2

set -a
# shellcheck disable=SC1091
. docker/versions.env
set +a

run_id="${IDSIM_RUN_ID:-$(date -u +%Y%m%d-%H%M%S)-k${k}-measure}"
run_rel="artifacts/runs/${run_id}"
run_dir="${repo_root}/${run_rel}"
out_rel="${run_rel}/measure"
out_dir="${repo_root}/${out_rel}"
project="idsim-${k}"

# 실행 시점의 commit, dirty, 이미지 key. 컨테이너에는 git이 없어 호스트에서 계산해 넘긴다.
git_commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then git_dirty=true; else git_dirty=false; fi
image_keys="$(python3 tools/ci/image_keys.py --format json 2>/dev/null || echo null)"

# 같은 실행 id의 measure/ 디렉터리에 기록이 있으면 스택을 올리기 전에 거부한다(부수 파일 덮어쓰기 방지)
if [ -n "$(ls -A "$out_dir" 2>/dev/null)" ]; then
  echo "이미 기록이 있다: ${out_rel}. 다른 IDSIM_RUN_ID를 쓴다" >&2
  exit 2
fi

compose() { docker compose -f "${run_dir}/compose.yaml" "$@"; }

# shellcheck disable=SC2329  # trap EXIT로 불린다
cleanup() {
  [ "$keep" -eq 1 ] || docker compose -p "$project" down --timeout 10 >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 주의: 이 스크립트는 tools/sim_stack.sh up으로 스택을 올린다. P4 뒤에는 up이 Executor(ops-N)도
# 띄우므로 Executor의 setpoint가 측정기의 직접 발행과 섞인다. P4 뒤에는 sim_stack.sh up --infra-only로
# 바꿔야 한다(--infra-only는 P4의 devops 작업에서 생긴다).
if ! STACK_UP_TIMEOUT="${STACK_UP_TIMEOUT:-240}" tools/sim_stack.sh up --stack "$k" --run-dir "$run_dir" >/dev/null; then
  echo "스택 올리기 실패(INFRA_UP). 로그는 tools/sim_stack.sh logs --stack ${k}" >&2
  exit 2
fi
mkdir -p "$out_dir"

status=0
fail=0
for item in "${items[@]}"; do
  args=(--item "$item" --out-dir "/opt/idsim/${out_rel}")
  [ -n "$attempts" ] && args+=(--attempts "$attempts")
  # shellcheck disable=SC2206  # MEASURE_ARGS는 공백으로 나뉜 인자다
  [ -n "${MEASURE_ARGS:-}" ] && args+=(${MEASURE_ARGS})
  echo "== ${item}: ${args[*]}" >&2
  compose run --rm --no-deps -T \
    -e IDSIM_GIT_COMMIT="$git_commit" -e IDSIM_GIT_DIRTY="$git_dirty" -e IDSIM_IMAGE_KEYS="$image_keys" \
    runner bash -c 'cd /opt/idsim && python3 tests/sitl/measure/measure.py "$@"' _ "${args[@]}" \
    2>&1 | tee "${out_dir}/run_${item}.log"
  rc="${PIPESTATUS[0]}"
  case "$rc" in 0|1|2) ;; *) echo "${item}: 예상 밖의 종료 코드 ${rc}를 2로 접는다" >&2; rc=2 ;; esac
  echo "${item}: measure.py 종료 코드 ${rc}" >&2
  [ "$rc" -eq 1 ] && fail=1
  [ "$rc" -gt "$status" ] && status="$rc"
done

# 스택을 멈춘다. ULog가 정상적으로 닫히는지(종료 코드 137이면 KILL) 서비스별로 남긴다.
compose stop -t 15 >/dev/null 2>&1 || true
compose ps -a --format '{{.Service}} {{.State}} exit={{.ExitCode}}' >"${out_dir}/stop_exit.txt" 2>&1 || true
compose logs --no-color >"${out_dir}/compose.log" 2>&1 || true
echo "서비스 종료 상태: ${out_rel}/stop_exit.txt" >&2

python3 tests/sitl/measure/crosscheck.py --measure-dir "$out_dir" --repo-root "$repo_root" \
  --items "$(IFS=,; echo "${items[*]}")" | tee "${out_dir}/crosscheck.log"
rc="${PIPESTATUS[0]}"
case "$rc" in 0|1|2) ;; *) echo "crosscheck: 예상 밖의 종료 코드 ${rc}를 2로 접는다" >&2; rc=2 ;; esac
# 최종 종료 코드는 crosscheck를 따른다. crosscheck는 ULog 증거로 확정한 최종 판정(예: (5)의 INCONCLUSIVE ->
# PASS)과 유효 시도 수, 메타, measure.py 완료 기록을 다시 평가한다. measure.py가 1을 낸 항목이 있으면 1이다.
if [ "$fail" -eq 1 ]; then status=1; else status="$rc"; fi

echo "산출물: ${out_rel} (종료 코드 ${status})" >&2
exit "$status"
