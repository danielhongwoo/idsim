#!/usr/bin/env bash
# ros_ws(ROS 2 패키지)의 빌드와 테스트 진입점. 호스트에 ROS가 없다는 전제로 ros-ws 컨테이너 안에서 돈다.
# unit 워크플로(.github/workflows/unit.yml)는 `ci`만 부르고, 로컬도 같은 명령을 쓴다.
#
# 사용법: tools/ros_ws.sh <명령> [--image-tag t | --registry r] [colcon 인자...]
#   build   colcon build (RelWithDebInfo, compile_commands.json 생성)
#   test    build 뒤 colcon test --return-code-on-test-failure, colcon test-result, ament 패키지마다 테스트 1건 이상 단정
#   tidy    build 뒤 clang-tidy (.clang-tidy, 각 패키지의 src/ 아래 C++ 소스가 대상)
#   ci      build -> test -> tidy 를 한 번씩 (CI와 같은 순서)
#   clean   ros_ws/build, install, log 삭제
#   shell   같은 조건의 대화형 bash
#   명령 뒤의 나머지 인자는 build와 test에서 colcon에 그대로 넘긴다(예: --packages-select idsim_common).
#   이미지는 idsim/ros-ws:<태그>(기본 local), --registry를 주면 <r>/ros-ws:<태그> (gen_compose.sh와 같은 의미).
#
# 컨테이너 조건
#   --user <호스트 uid:gid>  build, install, log가 호스트 사용자 소유라 호스트에서 지울 수 있다
#   --network none          빌드와 단위 테스트에 네트워크가 필요 없고, 같은 호스트의 스택(도메인 20 + k)과 섞이지 않는다
#   -e CYCLONEDDS_URI=      이미지 기본값(저장소 설정 파일)을 비운다. 단위 테스트는 DDS 설정에 기대지 않는다
#   -e ROS_DOMAIN_ID=99     스택 범위(20-29) 밖. --network none이 빠진 실행을 위한 이중 잠금
#   -e HOME=/tmp/idsim-home passwd에 없는 uid여도 되도록 쓸 수 있는 홈을 준다
#   저장소는 /opt/idsim에 쓰기로 마운트한다(install의 절대 경로가 스택의 마운트 경로와 같아야 한다)
# 실행 전에 이미지의 IDSIM_BUILD_* 값을 docker/versions.env와 대조해 다르면 중단한다(옛 이미지로 빌드하는 실수 방지).
# 단계마다 걸린 초를 출력하고, GITHUB_STEP_SUMMARY가 있으면 표로 덧붙인다.
#
# 환경변수: IDSIM_JOBS (colcon과 clang-tidy 병렬 수, 기본 min(코어 수, 4))

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
say() { echo "ros_ws.sh: $*" >&2; }
usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }

[ "$#" -ge 1 ] || usage
cmd="$1"; shift
case "$cmd" in
  build|test|tidy|ci|clean|shell) ;;
  -h|--help) usage ;;
  *) say "모르는 명령: ${cmd}"; usage ;;
esac

# --옵션=값 형식은 --옵션 값으로 펼친다
args=()
for a in "$@"; do
  case "$a" in
    --image-tag=*|--registry=*) args+=("${a%%=*}" "${a#*=}") ;;
    *) args+=("$a") ;;
  esac
done
image_tag="local"
registry=""
pass=()
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  a="${args[$i]}"
  case "$a" in
    --image-tag) image_tag="${args[$((i + 1))]:?--image-tag 값}"; i=$((i + 2)); continue ;;
    --registry) registry="${args[$((i + 1))]:?--registry 값}"; i=$((i + 2)); continue ;;
    -h|--help) usage ;;
  esac
  pass+=("$a")
  i=$((i + 1))
done
image_prefix="idsim"
if [ -n "$registry" ]; then image_prefix="${registry%/}"; fi
image="${image_prefix}/ros-ws:${image_tag}"

ros_ws_dir="${repo_root}/ros_ws"

# 테스트를 일부러 두지 않는 ament 패키지(공백 구분). test의 패키지별 1건 이상 단정에서 빠진다. 지금은 비어 있다.
no_test_packages=()

warn_running_stack() {
  # 스택이 떠 있는 동안 install을 바꾸면 실행 중인 노드의 .so가 바뀐다(경고만 한다)
  if command -v docker >/dev/null 2>&1 \
      && docker compose ls --quiet 2>/dev/null | grep -q '^idsim-'; then
    say "경고: idsim 스택이 떠 있다. install을 바꾸면 실행 중인 노드에 영향을 줄 수 있다 (tools/stack.sh down)"
  fi
}

if [ "$cmd" = "clean" ]; then
  warn_running_stack
  rm -rf "${ros_ws_dir}/build" "${ros_ws_dir}/install" "${ros_ws_dir}/log"
  say "삭제: ros_ws/build, ros_ws/install, ros_ws/log"
  exit 0
fi

# 이미지 존재와 버전 대조. 이미지의 IDSIM_BUILD_<이름>은 versions.env의 <이름>과 같아야 한다.
# LLVM_MAJOR는 이 스크립트가 쓰는 도구(clang-tidy)의 버전이라 이미지에 반드시 있어야 한다.
check_image() {
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    say "이미지 ${image}가 없다. python3 tools/ci/build_images.py --mode load ros-ws"
    exit 1
  fi
  local env_dump bad=0 line name want got
  env_dump="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$image")"
  if ! grep -q '^IDSIM_BUILD_LLVM_MAJOR=' <<<"$env_dump"; then
    say "이미지에 IDSIM_BUILD_LLVM_MAJOR가 없다(clang 도구 이전의 옛 이미지). ros-ws를 다시 빌드하라: python3 tools/ci/build_images.py --mode load ros-ws"
    exit 1
  fi
  while IFS= read -r line; do
    case "$line" in IDSIM_BUILD_*=*) ;; *) continue ;; esac
    name="${line%%=*}"; name="${name#IDSIM_BUILD_}"; got="${line#*=}"
    want="$(grep -m1 "^${name}=" "${repo_root}/docker/versions.env" | cut -d= -f2- || true)"
    if [ "$want" != "$got" ]; then
      say "이미지 ${name}=${got} 이지만 versions.env는 ${want:-<없음>}: ros-ws를 다시 빌드하라 (python3 tools/ci/build_images.py --mode load ros-ws)"
      bad=1
    fi
  done <<<"$env_dump"
  [ "$bad" -eq 0 ] || exit 1
}

jobs="${IDSIM_JOBS:-}"
if [ -z "$jobs" ]; then
  jobs="$(nproc)"
  if [ "$jobs" -gt 4 ]; then jobs=4; fi
fi

mkdir -p "${ros_ws_dir}"

# ros_in <bash 스크립트> [인자...] : 컨테이너에서 스크립트를 실행한다. 인자는 스크립트의 $1...
# entrypoint가 ROS와 px4 underlay(와 기존 install)를 읽은 뒤 실행한다.
ros_in() {
  local script="$1"; shift
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --network none \
    -e HOME=/tmp/idsim-home \
    -e CYCLONEDDS_URI= \
    -e ROS_DOMAIN_ID=99 \
    -e IDSIM_JOBS="$jobs" \
    -e IDSIM_NO_TEST_PACKAGES="${no_test_packages[*]}" \
    -v "${repo_root}:/opt/idsim" \
    -w /opt/idsim/ros_ws \
    "$image" \
    bash -c "set -euo pipefail; mkdir -p \"\$HOME\"; ${script}" ros_ws "$@"
}

if [ "$cmd" = "shell" ]; then
  check_image
  exec docker run --rm -it \
    --user "$(id -u):$(id -g)" \
    --network none \
    -e HOME=/tmp/idsim-home \
    -e CYCLONEDDS_URI= \
    -e ROS_DOMAIN_ID=99 \
    -e IDSIM_JOBS="$jobs" \
    -v "${repo_root}:/opt/idsim" \
    -w /opt/idsim/ros_ws \
    "$image" bash
fi

# 단계별 시간 기록
timing_names=()
timing_secs=()
step() {
  # step <이름> <함수> [인자...]
  local name="$1"; shift
  local t0 t1 rc=0
  echo "==== ros_ws ${name}"
  t0="$(date +%s)"
  # 주의: "$@" || rc=$? 문맥에서는 do_* 함수 안의 errexit(set -e)가 꺼진다.
  # 그러므로 do_* 안의 명령은 실패가 다음 명령으로 넘어가지 않게 &&로 잇거나 명시적으로 return/exit 한다.
  "$@" || rc=$?
  t1="$(date +%s)"
  timing_names+=("$name")
  timing_secs+=("$((t1 - t0))")
  echo "STEP ${name}: $((t1 - t0))초 (exit ${rc})"
  return "$rc"
}
write_summary() {
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  {
    echo "### tools/ros_ws.sh ${cmd}"
    echo ""
    echo "| 단계 | 초 |"
    echo "| --- | --- |"
    local n
    for n in "${!timing_names[@]}"; do echo "| ${timing_names[$n]} | ${timing_secs[$n]} |"; done
  } >>"$GITHUB_STEP_SUMMARY"
}
trap write_summary EXIT

do_build() {
  # colcon build는 실패하면 종료 코드가 0이 아니다. -DCMAKE_EXPORT_COMPILE_COMMANDS는 colcon이 build/compile_commands.json으로 합친다.
  # 경고를 오류로 바꾸는 옵션(-Werror)은 패키지 CMakeLists가 정한다. 로컬과 CI의 결과가 달라지지 않게 여기서는 넣지 않는다.
  # 작은따옴표 안의 $는 컨테이너 안 bash가 펼친다(의도된 것)
  # shellcheck disable=SC2016
  ros_in '
    colcon list -n | sed "s/^/package: /"
    colcon build \
      --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
      --event-handlers console_cohesion+ --parallel-workers "$IDSIM_JOBS" "$@"' "${pass[@]}"
}

do_test() {
  # 함정 둘(opinion-devops E6, E7)
  #  1. colcon test는 테스트가 실패해도 0을 돌려준다 -> --return-code-on-test-failure
  #  2. colcon test-result는 빌드가 실패했거나 패키지가 하나도 없어도 "0 tests"로 0을 돌려준다 -> ament 패키지별 1건 이상 단정(검사할 패키지가 0개여도 실패)
  #     colcon test-result는 build/ 전체의 결과 XML을 읽는다. 이전 실행의 결과가 남아 있으면 이번에 0건이 돌아도
  #     그 수가 잡히므로(--packages-select 오타로 확인), 테스트 전에 이전 결과를 지운다.
  # 재시도는 두지 않는다(단위 층은 결정적이어야 한다).
  # 작은따옴표 안의 $는 컨테이너 안 bash가 펼친다(의도된 것)
  # shellcheck disable=SC2016
  ros_in '
    rm -rf build/*/test_results build/*/Testing
    colcon test --return-code-on-test-failure --event-handlers console_cohesion+ \
      --parallel-workers "$IDSIM_JOBS" "$@"
    result="$(colcon test-result --verbose)" || { printf "%s\n" "$result"; echo "colcon test-result: 실패 또는 오류가 있다" >&2; exit 1; }
    printf "%s\n" "$result"
    total="$(sed -n "s/^Summary: \([0-9][0-9]*\) tests.*/\1/p" <<<"$result" | tail -n 1)"
    if [ -z "$total" ]; then echo "colcon test-result 요약 줄을 읽지 못했다" >&2; exit 1; fi
    # 패키지마다 결과 1건 이상. 대상은 colcon list가 정한다(--packages-* 선택 인자를 그대로 넘긴다).
    sel=(); grab=0
    for a in "$@"; do
      case "$a" in
        --packages-select|--packages-skip|--packages-up-to|--packages-above|--packages-select-regex|--packages-skip-regex|--packages-select-build-failed|--packages-skip-build-finished|--packages-skip-test-passed|--packages-select-test-failures|--packages-skip-up-to|--packages-skip-by-dep|--packages-ignore|--packages-ignore-regex) sel+=("$a"); grab=1 ;;
        --*) grab=0 ;;
        *) if [ "$grab" -eq 1 ]; then sel+=("$a"); fi ;;
      esac
    done
    bad=0; npkg=0
    while IFS=$(printf "\t") read -r pkg _ ptype; do
      case "$ptype" in "(ros.ament_"*) ;; *) continue ;; esac
      for skip in $IDSIM_NO_TEST_PACKAGES; do [ "$skip" = "$pkg" ] && continue 2; done
      npkg=$((npkg + 1))
      n="$(colcon test-result --test-result-base "build/${pkg}" 2>/dev/null | sed -n "s/^Summary: \([0-9][0-9]*\) tests.*/\1/p" | tail -n 1 || true)"
      echo "tests ${pkg}: ${n:-0}"
      if [ "${n:-0}" -le 0 ]; then
        echo "패키지 ${pkg}의 테스트 결과가 0건이다. 테스트 누락, 수집 실패, package.xml 오류를 확인하라(의도한 것이면 ros_ws.sh의 no_test_packages에 적는다)" >&2
        bad=1
      fi
    done < <(colcon list "${sel[@]}")
    if [ "$npkg" -eq 0 ]; then echo "검사할 ament 패키지가 없다(선택 인자 또는 COLCON_IGNORE 확인)" >&2; exit 1; fi
    if [ "$bad" -ne 0 ]; then exit 1; fi
    echo "tests: ${total}"' "${pass[@]}"
}

do_tidy() {
  # 대상은 각 패키지의 src/ 아래 C++ 소스다. include/ 헤더는 소스가 끌어올 때 .clang-tidy의 HeaderFilterRegex로 검사한다.
  # test/는 처음에는 대상이 아니다(gtest 매크로 때문). 설정은 저장소 루트 .clang-tidy.
  # 작은따옴표 안의 $는 컨테이너 안 bash가 펼친다(의도된 것)
  # shellcheck disable=SC2016
  ros_in '
    test -f /opt/idsim/.clang-tidy || { echo "저장소 루트에 .clang-tidy가 없다" >&2; exit 1; }
    test -f build/compile_commands.json || { echo "ros_ws/build/compile_commands.json이 없다(C++ 패키지가 없거나 build가 안 됐다)" >&2; exit 1; }
    tool="run-clang-tidy-${IDSIM_BUILD_LLVM_MAJOR}"
    command -v "$tool" >/dev/null || { echo "${tool}이 이미지에 없다" >&2; exit 1; }
    regex="^/opt/idsim/ros_ws/src/[^/]+/src/.*\.(cpp|cc|cxx)\$"
    count="$(python3 -c "
import json, re, sys
rx = re.compile(sys.argv[1])
print(sum(1 for e in json.load(open(\"build/compile_commands.json\")) if rx.search(e[\"file\"])))" "$regex")"
    if [ "$count" -eq 0 ]; then
      echo "RESULT clang-tidy: PASS-NO-TARGETS (0 files)"
      exit 0
    fi
    echo "clang-tidy 대상 ${count}개"
    "$tool" -p build -j "$IDSIM_JOBS" -quiet -warnings-as-errors="*" "$regex"
    echo "RESULT clang-tidy: PASS (${count} files)"'
}

check_image
case "$cmd" in
  build) warn_running_stack; step build do_build ;;
  test) warn_running_stack; step build do_build; step test do_test ;;
  tidy) warn_running_stack; step build do_build; step tidy do_tidy ;;
  ci) step build do_build; step test do_test; step tidy do_tidy ;;
esac
