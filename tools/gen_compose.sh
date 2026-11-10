#!/usr/bin/env bash
# tools/gen_compose.py의 호스트 진입점. 생성기를 ros-ws 컨테이너 안에서 돌린다(호스트에 PyYAML이 필요 없다).
#
# 사용법: tools/gen_compose.sh [--stack k] [--fleet f] [--variant standalone|embedded] [--run-id id]
#                              [--run-dir 경로] [--image-tag t | --registry r] [그 밖의 gen_compose.py 인자...]
#   --run-dir를 주지 않으면 <저장소>/artifacts/runs/<run-id>. 실행 디렉터리는 <저장소>/artifacts/runs/<run-id>여야 한다.
#   --run-dir만 주면 run-id는 그 마지막 요소가 된다(어긋나면 생성기가 거부한다).
#   성공하면 실행 디렉터리의 호스트 절대 경로 한 줄을 stdout에 쓴다(경고는 stderr).
#
# 컨테이너 조건
#   --user <호스트 uid:gid>  만드는 파일(compose.yaml, stack.json, px4-N/, ros_log/)이 호스트 사용자 소유가 된다
#   --network none           생성기는 네트워크를 쓰지 않는다
#   -e CYCLONEDDS_URI=        생성기는 DDS를 쓰지 않으며 rmw 초기화를 피하려고 비운다
#   저장소는 /opt/idsim에 읽기 전용, 실행 디렉터리만 /out에 쓰기로 마운트한다(중첩 아님: /out은 저장소 마운트 밖)
# git 커밋과 dirty 여부는 호스트에서 계산해 넘긴다(컨테이너에는 uid가 달라 safe.directory 문제가 있다).
# 이미지 태그는 --image-tag(기본 local)에서 ros-ws 이미지도 고른다.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --옵션=값 형식은 --옵션 값으로 펼친다(값 있는 옵션만)
args=()
for a in "$@"; do
  case "$a" in
    --stack=*|--run-id=*|--run-dir=*|--image-tag=*|--registry=*|--fleet=*|--variant=*) args+=("${a%%=*}" "${a#*=}") ;;
    *) args+=("$a") ;;
  esac
done
stack="${IDSIM_STACK_INDEX:-0}"
run_id=""
run_dir=""
image_tag="local"
registry=""
pass=()
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  a="${args[$i]}"
  next="${args[$((i + 1))]:-}"
  case "$a" in
    --stack) stack="$next"; i=$((i + 2)); continue ;;
    --run-id) run_id="$next"; i=$((i + 2)); continue ;;
    --run-dir) run_dir="$next"; i=$((i + 2)); continue ;;
    --image-tag) image_tag="$next"; i=$((i + 2)); continue ;;
    --registry) registry="$next"; i=$((i + 2)); continue ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
  pass+=("$a")
  i=$((i + 1))
done

case "$stack" in
  [0-9]) ;;
  *) echo "gen_compose.sh: 스택 번호는 0-9: '${stack}'" >&2; exit 2 ;;
esac
if [ -z "$run_id" ] && [ -n "$run_dir" ]; then
  run_id="$(basename "$run_dir")"
elif [ -z "$run_id" ]; then
  run_id="$(date -u +%Y%m%d-%H%M%S)-k${stack}"
fi
if [ -z "$run_dir" ]; then
  run_dir="${repo_root}/artifacts/runs/${run_id}"
fi
created_dir=0
if [ ! -e "$run_dir" ]; then created_dir=1; fi
mkdir -p "$run_dir"
run_dir="$(cd "$run_dir" && pwd)"
# 생성에 실패했고 우리가 만든 디렉터리가 비어 있으면 지운다
cleanup() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$created_dir" -eq 1 ] && [ -d "$run_dir" ]; then
    rmdir "$run_dir" 2>/dev/null || true
  fi
}
trap cleanup EXIT
case "$run_dir/" in
  "${repo_root}/"*) ;;
  *) echo "gen_compose.sh: 실행 디렉터리는 저장소(${repo_root}) 안이어야 한다: ${run_dir}" >&2; exit 2 ;;
esac

git_args=()
if command -v git >/dev/null 2>&1 && commit="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null)"; then
  git_args+=(--git-commit "$commit")
  if [ -n "$(git -C "$repo_root" status --porcelain 2>/dev/null)" ]; then
    git_args+=(--git-dirty true)
  else
    git_args+=(--git-dirty false)
  fi
fi

image_prefix="idsim"
reg_args=()
if [ -n "$registry" ]; then
  image_prefix="${registry%/}"
  reg_args+=(--registry "$registry")
fi

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --network none \
  -e CYCLONEDDS_URI= \
  -e HOME=/tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/opt/idsim:ro" \
  -v "${run_dir}:/out" \
  "${image_prefix}/ros-ws:${image_tag}" \
  python3 /opt/idsim/tools/gen_compose.py \
  --repo-root /opt/idsim \
  --host-repo-root "$repo_root" \
  --run-dir "$run_dir" \
  --out-dir /out \
  --run-id "$run_id" \
  --stack "$stack" \
  --uid "$(id -u)" --gid "$(id -g)" \
  --image-tag "$image_tag" \
  "${reg_args[@]}" \
  "${git_args[@]}" \
  "${pass[@]}"
