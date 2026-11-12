#!/usr/bin/env bash
# lint job의 검사를 실행한다. GitHub Actions의 lint 워크플로와 로컬이 같은 명령을 쓴다.
#
# 사용법: tools/ci/lint.sh <검사>... | all
#   검사: charset shellcheck ruff hadolint actionlint yamllint pytest compose-config
#         clang-format px4-api cargo
#   clang-tidy와 ament_lint는 compile_commands.json과 ROS 헤더가 필요해서 여기에 없다. unit job의 tools/ros_ws.sh ci 안에서 돈다.
#
# 대상 파일은 git이 추적하거나 무시 목록에 없는 새 파일이다(git ls-files -co --exclude-standard).
# 그래서 로컬의 artifacts/, __pycache__/ 같은 무시 대상은 보지 않고 CI 체크아웃과 같은 파일을 본다.
# 도구는 docker/versions.env의 LINT_* 이미지로 실행한다(호스트에 린터 설치가 필요 없다).
#
# 검사마다 마지막 줄에 결과를 한 줄 남긴다. 로그에서 다음 넷을 구분하기 위해서다.
#   RESULT <검사>: PASS (N files)              대상이 있었고 검사를 통과
#   RESULT <검사>: PASS-NO-TARGETS (0 files)   대상 파일이 없어 검사 없이 통과 (GitHub notice로도 남김)
#   RESULT <검사>: FAIL ...                    검사 실패
#   RESULT <검사>: FAIL-NOT-WIRED (N files)    대상 파일이 생겼는데 아직 검사를 연결하지 않음. 조용히 넘어가지 않도록 실패시킨다
# 검사를 건너뛰는(실행하지 않는) 경로는 두지 않는다.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

set -a
# shellcheck disable=SC1091
. docker/versions.env
set +a

in_github() { [ "${GITHUB_ACTIONS:-}" = "true" ]; }

result() {
  # result <검사> <상태> <설명>
  echo "RESULT $1: $2 $3"
  if in_github; then
    case "$2" in
      PASS-NO-TARGETS) echo "::notice title=lint $1::대상 파일 0개. 검사 없이 통과(건너뜀 아님)" ;;
      FAIL-NOT-WIRED) echo "::error title=lint $1::대상 파일이 생겼으나 검사가 아직 연결되지 않았다. tools/ci/lint.sh에서 연결하라" ;;
      FAIL) echo "::error title=lint $1::$3" ;;
    esac
  fi
}

# list_files <pathspec>... : 대상 파일을 NUL 없이 줄 단위로 출력 (경로에 줄바꿈이 없다고 가정)
list_files() {
  # core.quotepath=off: 한글 경로를 8진수 이스케이프 없이 그대로 받는다(아니면 [ -f ]에서 빠진다)
  git -c core.quotepath=off ls-files -co --exclude-standard -- "$@" | sort -u | while IFS= read -r f; do
    [ -f "$f" ] && printf '%s\n' "$f"
  done
}

drun() {
  # drun <이미지> [docker run 추가 인자...] -- <명령...>
  local image="$1"; shift
  local extra=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do extra+=("$1"); shift; done
  shift
  docker run --rm -v "${repo_root}:/src:ro" -w /src "${extra[@]}" "$image" "$@"
}

check_charset() {
  local files
  mapfile -t files < <(list_files .)
  if [ "${#files[@]}" -eq 0 ]; then result charset PASS-NO-TARGETS "(0 files)"; return 0; fi
  local out rc=0
  # CLAUDE.md의 검사 명령과 같은 패턴. \x{AC00}-\x{D7A3}를 쓰려면 UTF-8 로캘이 필요하다.
  out="$(LC_ALL=C.UTF-8 grep -nP '[^\x00-\x7F\x{AC00}-\x{D7A3}]' -- "${files[@]}")" || rc=$?
  if [ "$rc" -eq 1 ]; then result charset PASS "(${#files[@]} files)"; return 0; fi
  [ -n "$out" ] && printf '%s\n' "$out"
  result charset FAIL "완성형 한글과 아스키 밖의 문자 (grep exit ${rc})"
  return 1
}

check_shellcheck() {
  local files
  # *.sh와 확장자 없는 셸 스크립트(명시 목록). px4-rc.mavlink는 px4 rcS가 source하는 sh 파일이다
  mapfile -t files < <(list_files '*.sh' 'docker/px4/px4-rc.mavlink')
  if [ "${#files[@]}" -eq 0 ]; then result shellcheck PASS-NO-TARGETS "(0 files)"; return 0; fi
  if drun "$LINT_SHELLCHECK_IMAGE" --network none -- "${files[@]}"; then
    result shellcheck PASS "(${#files[@]} files)"
  else
    result shellcheck FAIL "shellcheck 위반"; return 1
  fi
}

check_ruff() {
  local files
  mapfile -t files < <(list_files '*.py')
  if [ "${#files[@]}" -eq 0 ]; then result ruff PASS-NO-TARGETS "(0 files)"; return 0; fi
  # 설정은 저장소 루트 ruff.toml
  if drun "$LINT_RUFF_IMAGE" --network none -- check --no-cache --output-format concise "${files[@]}"; then
    result ruff PASS "(${#files[@]} files)"
  else
    result ruff FAIL "ruff 위반"; return 1
  fi
}

# 파일별 임시 예외. 소유자가 고치면 줄을 지운다. 규칙 자체는 .hadolint.yaml에서 켜져 있다.
hadolint_file_ignores() {
  case "$1" in
    # px4-engineer 소유. DL3013 pip 버전 미고정(비결정 빌드 요소), SC2010 ls | grep. 2026-11-06 보고, 수정 대기
    docker/Dockerfile.px4) echo "DL3013 SC2010" ;;
  esac
}

check_hadolint() {
  local files
  mapfile -t files < <(list_files '*Dockerfile*')
  if [ "${#files[@]}" -eq 0 ]; then result hadolint PASS-NO-TARGETS "(0 files)"; return 0; fi
  local f failed=0 rule args
  for f in "${files[@]}"; do
    args=(hadolint --config /src/.hadolint.yaml)
    for rule in $(hadolint_file_ignores "$f"); do
      echo "hadolint: ${f}: 임시 예외 ${rule}"
      args+=(--ignore "$rule")
    done
    drun "$LINT_HADOLINT_IMAGE" --network none -- "${args[@]}" "$f" || failed=1
  done
  if [ "$failed" -eq 0 ]; then
    result hadolint PASS "(${#files[@]} files)"
  else
    result hadolint FAIL "hadolint 위반"; return 1
  fi
}

check_actionlint() {
  local files
  mapfile -t files < <(list_files '.github/workflows/*.yml' '.github/workflows/*.yaml')
  if [ "${#files[@]}" -eq 0 ]; then result actionlint PASS-NO-TARGETS "(0 files)"; return 0; fi
  # 이미지에 포함된 shellcheck로 run: 블록도 검사한다
  if drun "$LINT_ACTIONLINT_IMAGE" --network none -- -no-color "${files[@]}"; then
    result actionlint PASS "(${#files[@]} files)"
  else
    result actionlint FAIL "actionlint 위반"; return 1
  fi
}

check_yamllint() {
  local files
  mapfile -t files < <(list_files '*.yml' '*.yaml' '.yamllint')
  if [ "${#files[@]}" -eq 0 ]; then result yamllint PASS-NO-TARGETS "(0 files)"; return 0; fi
  # 작은따옴표 안의 $0, $@는 컨테이너 안 sh가 펼친다(의도된 것)
  # shellcheck disable=SC2016
  if drun "$LINT_PYTHON_IMAGE" -e PIP_DISABLE_PIP_VERSION_CHECK=1 -- sh -c \
      'pip install --no-cache-dir -q --root-user-action=ignore "yamllint==$0" && yamllint --strict -c .yamllint.yaml "$@"' \
      "$LINT_YAMLLINT_VERSION" "${files[@]}"; then
    result yamllint PASS "(${#files[@]} files)"
  else
    result yamllint FAIL "yamllint 위반"; return 1
  fi
}

check_pytest() {
  # rclpy 없이 도는 단위 테스트만(tests/support, tests/tools). rclpy가 필요한 테스트는 ros-ws 이미지 안의
  # unit job(이후 단계) 몫이다. 생성기 테스트를 위해 ros-ws와 같은 PyYAML(LINT_PYYAML_VERSION, S0이 대조)을 설치한다.
  local files
  mapfile -t files < <(list_files 'tests/support/test_*.py' 'tests/tools/test_*.py')
  if [ "${#files[@]}" -eq 0 ]; then result pytest PASS-NO-TARGETS "(0 files)"; return 0; fi
  # 저장소는 읽기 전용으로 마운트하므로 캐시와 바이트코드를 쓰지 않는다
  # shellcheck disable=SC2016
  if drun "$LINT_PYTHON_IMAGE" -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PYTHONDONTWRITEBYTECODE=1 -- sh -c \
      'pip install --no-cache-dir -q --root-user-action=ignore "pytest==$0" "pyyaml==$1" && python3 -m pytest tests/support tests/tools -q -p no:cacheprovider' \
      "$LINT_PYTEST_VERSION" "$LINT_PYYAML_VERSION"; then
    result pytest PASS "(${#files[@]} files)"
  else
    result pytest FAIL "pytest 실패"; return 1
  fi
}

check_compose_config() {
  # 생성기 골든 compose를 docker compose config -q로 검사한다(viz, tools 프로필 포함, DISPLAY와 XAUTHORITY 미설정).
  # 꺼진 프로필도 보간되므로 viz 서비스의 ${X:?} 같은 실수가 여기서 잡힌다. 골든의 호스트 저장소 경로
  # /work/idsim을 이 체크아웃 경로로 바꿔 env_file이 실제로 있게 한다(바인드 원본 존재는 config가 보지 않는다).
  local files
  mapfile -t files < <(list_files 'tests/fixtures/gen_compose/*/compose.yaml')
  if [ "${#files[@]}" -eq 0 ]; then result compose-config PASS-NO-TARGETS "(0 files)"; return 0; fi
  local tmp f failed=0
  tmp="$(mktemp -d)"
  for f in "${files[@]}"; do
    sed "s#/work/idsim#${repo_root}#g" "$f" > "${tmp}/compose.yaml"
    if env -u DISPLAY -u XAUTHORITY docker compose -f "${tmp}/compose.yaml" --profile viz --profile tools config -q; then
      echo "ok   ${f}"
    else
      echo "FAIL ${f}"
      failed=1
    fi
  done
  rm -rf "$tmp"
  if [ "$failed" -eq 0 ]; then
    result compose-config PASS "(${#files[@]} files)"
  else
    result compose-config FAIL "docker compose config 실패"; return 1
  fi
}

cpp_specs=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx')

check_clang_format() {
  # 스타일은 저장소 루트 .clang-format 하나다. 파일이 없으면 clang-format이 조용히 LLVM 기본 스타일을 쓰므로
  # --style=file:<경로>로 명시하고, 대상이 있는데 설정이 없으면 실패시킨다.
  local files
  mapfile -t files < <(list_files "${cpp_specs[@]}")
  if [ "${#files[@]}" -eq 0 ]; then result clang-format PASS-NO-TARGETS "(0 files)"; return 0; fi
  if [ ! -f .clang-format ]; then
    printf '  %s\n' "${files[@]}"
    result clang-format FAIL "C++ 파일이 있는데 저장소 루트에 .clang-format이 없다"
    return 1
  fi
  # ros-ws에 설치되는 clang-format-<LLVM_MAJOR>과 major가 같아야 로컬 컨테이너와 CI의 결과가 일치한다
  if [ "${LINT_CLANG_FORMAT_VERSION%%.*}" != "$LLVM_MAJOR" ]; then
    result clang-format FAIL "LINT_CLANG_FORMAT_VERSION(${LINT_CLANG_FORMAT_VERSION})의 major가 LLVM_MAJOR(${LLVM_MAJOR})와 다르다"
    return 1
  fi
  # 작은따옴표 안의 $0, $@는 컨테이너 안 sh가 펼친다(의도된 것)
  # shellcheck disable=SC2016
  if drun "$LINT_PYTHON_IMAGE" -e PIP_DISABLE_PIP_VERSION_CHECK=1 -- sh -c \
      'pip install --no-cache-dir -q --root-user-action=ignore "clang-format==$0" \
        && clang-format --version \
        && clang-format --dry-run --Werror --style=file:/src/.clang-format "$@"' \
      "$LINT_CLANG_FORMAT_VERSION" "${files[@]}"; then
    result clang-format PASS "(${#files[@]} files)"
  else
    result clang-format FAIL "clang-format 위반 또는 설치 실패"; return 1
  fi
}

check_px4_api() {
  # /fmu 토픽 이름과 idsim_common 내부 이름은 idsim_common 안에서만 쓴다(1a 4단계 쟁점 2, git 이력).
  # 다른 패키지가 문자열을 직접 쓰면 공개 API의 발행 허용 목록을 우회한다. 실수 방지 수준이며 보안 경계가 아니다.
  # 대상은 ros_ws/src 아래 idsim_common 밖의 C++ 파일, .py 파일(launch 포함), yaml 파일(params, remap)과
  # 생성기 golden의 params 파일, tests/sitl/과 tests/support/ 아래의 .py, yaml 파일이다(decisions 쟁점 8).
  # tests/ 쪽 예외는 파일 이름으로만 둔다: tests/support/px4_raw.py, tests/support의 측정 전용 발행 모듈(이름은 아래 measure_pub),
  # 이름에 px4_topic이 든 파일(px4_topic.py, test_px4_topic_names.py). 토픽 이름을 다른 모듈에서 얻어 검사에 안 걸린다는 사실에는 기대지 않는다.
  # 예외 파일이 사라지면 목록이 낡은 것이므로 실패시킨다.
  # 측정 전용 모듈 이름을 한 덩어리 문자열로 쓰면 "측정 모듈은 measure/ 밖에서 가져가지 않는다"는 pytest의 문자열 검사가 이 파일을 걸므로 둘로 나눠 적는다
  local measure_pub="px4_measure" files=() f exc_raw=0 exc_pub=0 exc_topic=0
  while IFS= read -r f; do
    case "$f" in
      ros_ws/src/idsim_common/*) ;;
      tests/support/px4_raw.py) exc_raw=1 ;;
      "tests/support/${measure_pub}_pub.py") exc_pub=1 ;;
      tests/sitl/*px4_topic*|tests/support/*px4_topic*) exc_topic=1 ;;
      *) files+=("$f") ;;
    esac
  done < <(list_files 'ros_ws/src/*.py' 'ros_ws/src/*.yaml' 'ros_ws/src/*.yml' 'tests/fixtures/gen_compose/*/params/*.yaml' \
    'tests/sitl/*.py' 'tests/sitl/*.yaml' 'tests/sitl/*.yml' 'tests/support/*.py' 'tests/support/*.yaml' 'tests/support/*.yml' \
    "${cpp_specs[@]/#/ros_ws/src/}")
  if [ $((exc_raw + exc_pub + exc_topic)) -ne 3 ]; then
    result px4-api FAIL "예외 파일이 없다(px4_raw.py=${exc_raw}, measure_pub=${exc_pub}, px4_topic 파일=${exc_topic}). lint.sh의 예외 목록을 고친다"
    return 1
  fi
  if [ "${#files[@]}" -eq 0 ]; then result px4-api PASS-NO-TARGETS "(0 files)"; return 0; fi
  local out rc=0
  out="$(grep -nF -e 'fmu/in/' -e 'fmu/out/' -e 'detail::topic_name' -e 'idsim_common::px4::detail' \
    -e 'px4::detail::' -e 'detail::relative_topic_name' -e 'detail::for_each_topic' -- "${files[@]}")" || rc=$?
  if [ "$rc" -eq 1 ]; then result px4-api PASS "(${#files[@]} files)"; return 0; fi
  [ -n "$out" ] && printf '%s\n' "$out"
  result px4-api FAIL "idsim_common 밖에서 /fmu 토픽 문자열 또는 px4 detail 이름(px4::detail, detail::relative_topic_name, detail::for_each_topic) 사용 (grep exit ${rc})"
  return 1
}

# 아직 대상 코드가 없는 검사. 대상이 0개면 PASS-NO-TARGETS, 생기면 FAIL-NOT-WIRED로 연결을 강제한다.
not_wired() {
  local name="$1"; shift
  local files
  mapfile -t files < <(list_files "$@")
  if [ "${#files[@]}" -eq 0 ]; then result "$name" PASS-NO-TARGETS "(0 files)"; return 0; fi
  printf '  %s\n' "${files[@]}"
  result "$name" FAIL-NOT-WIRED "(${#files[@]} files)"
  return 1
}

# cargo fmt --check, cargo clippy -D warnings: gateway/ 크레이트가 생기면 연결
check_cargo() { not_wired cargo 'Cargo.toml'; }

all_checks=(charset shellcheck ruff hadolint actionlint yamllint pytest compose-config clang-format px4-api cargo)

run_check() {
  case "$1" in
    charset) check_charset ;;
    shellcheck) check_shellcheck ;;
    ruff) check_ruff ;;
    hadolint) check_hadolint ;;
    actionlint) check_actionlint ;;
    yamllint) check_yamllint ;;
    pytest) check_pytest ;;
    compose-config) check_compose_config ;;
    clang-format) check_clang_format ;;
    px4-api) check_px4_api ;;
    cargo) check_cargo ;;
    *) echo "모르는 검사: $1 (가능: ${all_checks[*]} all)" >&2; return 2 ;;
  esac
}

[ "$#" -ge 1 ] || { sed -n '2,6p' "$0" >&2; exit 2; }
if [ "$1" = "all" ]; then set -- "${all_checks[@]}"; fi

failed=()
for c in "$@"; do
  echo "==== lint ${c}"
  run_check "$c" || failed+=("$c")
done
if [ "${#failed[@]}" -gt 0 ]; then
  echo "실패한 검사: ${failed[*]}" >&2
  exit 1
fi
