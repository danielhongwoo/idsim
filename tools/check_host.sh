#!/usr/bin/env bash
# 호스트 조건 점검: idsim을 빌드하고 돌릴 수 있는 호스트인지 읽기 전용으로 확인한다.
#
# 사용법: tools/check_host.sh [--offline] [--help]
#   --offline  외부 네트워크 검사(archive.ubuntu.com)를 건너뛴다
#
# 항목마다 OK, FAIL, WARN 접두사로 한 줄씩 출력한다.
#   FAIL: 고쳐야 빌드나 실행이 된다. 하나라도 있으면 종료 코드 1
#   WARN: 상황에 따라 문제가 될 수 있다. 종료 코드에는 영향이 없다
# sudo를 쓰지 않고 시스템을 바꾸지 않는다(조회만 한다).

set -uo pipefail

# 디스크: 이미지 5종 합 약 8.6GB(공유 레이어 중복 포함) + px4 builder 단계 7.7GB + buildkit 캐시 여유.
# 메모리: 개발 VM 31GB와 CI 러너 16GB에서 확인했다. 그 아래는 미실측이라 16GB 미만을 WARN으로 둔다.
MIN_DISK_GB=30
MIN_MEM_GB=16
MIRROR_URL="http://archive.ubuntu.com/ubuntu/dists/noble/Release"

offline=0
for arg in "$@"; do
  case "$arg" in
    --offline) offline=1 ;;
    -h | --help)
      sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "알 수 없는 인자: $arg (--help 참조)" >&2
      exit 2
      ;;
  esac
done

fails=0
ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
fail() {
  echo "FAIL $*"
  fails=$((fails + 1))
}

# (a) 아키텍처
arch="$(uname -m)"
if [ "$arch" = "x86_64" ]; then
  ok "아키텍처 x86_64"
else
  fail "아키텍처 $arch: 지원 호스트는 x86_64 Linux뿐이다"
fi

# (b) docker 명령과 데몬 접근
docker_ok=0
if ! command -v docker > /dev/null 2>&1; then
  fail "docker 명령이 없다. Docker Engine을 설치하라"
elif timeout 15 docker info > /dev/null 2>&1; then
  ok "docker 데몬 접근 가능"
  docker_ok=1
else
  fail "docker info 실패: 데몬이 실행 중이 아니거나 현재 사용자가 docker 그룹에 속하지 않는다. 그룹 추가는 sudo usermod -aG docker \$USER 뒤 다시 로그인"
fi

# (c) compose v2
if [ "$docker_ok" -eq 1 ] || command -v docker > /dev/null 2>&1; then
  cv="$(docker compose version --short 2> /dev/null || true)"
  case "$cv" in
    v2* | 2*) ok "docker compose $cv" ;;
    "") fail "docker compose 플러그인이 없다(compose v2 필요)" ;;
    *) fail "docker compose 버전 $cv: v2가 필요하다" ;;
  esac

  # (d) buildx
  if bv="$(docker buildx version 2> /dev/null)" && [ -n "$bv" ]; then
    ok "docker buildx: $bv"
  else
    fail "docker buildx 플러그인이 없다"
  fi
else
  fail "docker가 없어 compose와 buildx를 확인하지 못했다"
fi

# (e) python3. 호스트에서 도는 스크립트는 표준 라이브러리만 쓴다. 확인된 버전은 3.12이며 3.10 이상을 하한으로 둔다
if command -v python3 > /dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"
  else
    fail "python3 $(python3 -c 'import platform; print(platform.python_version())'): 3.10 이상이 필요하다(확인된 버전은 3.12)"
  fi
else
  fail "python3가 없다(3.10 이상 필요)"
fi

# (f) git, curl, sha256sum
for cmd in git curl sha256sum; do
  if command -v "$cmd" > /dev/null 2>&1; then
    ok "$cmd 있음"
  else
    fail "$cmd 가 없다"
  fi
done

# (f2) gh. PR 작업에만 필요하다
if command -v gh > /dev/null 2>&1; then
  ok "gh 있음"
else
  warn "gh(GitHub CLI)가 없다. PR을 올리거나 합칠 때만 필요하다"
fi

# (g) 디스크 여유: docker 데이터 루트가 있는 파일시스템
root_dir=""
if [ "$docker_ok" -eq 1 ]; then
  root_dir="$(docker info --format '{{.DockerRootDir}}' 2> /dev/null || true)"
fi
[ -n "$root_dir" ] || root_dir="/var/lib/docker"
probe="$root_dir"
while [ ! -d "$probe" ] && [ "$probe" != "/" ]; do probe="$(dirname "$probe")"; done
avail_kb="$(df -Pk "$probe" 2> /dev/null | awk 'NR==2 {print $4}')"
if [ -n "$avail_kb" ]; then
  avail_gb=$((avail_kb / 1024 / 1024))
  if [ "$avail_gb" -ge "$MIN_DISK_GB" ]; then
    ok "디스크 여유 ${avail_gb}GB ($root_dir)"
  else
    warn "디스크 여유 ${avail_gb}GB ($root_dir): ${MIN_DISK_GB}GB 이상을 권장한다(이미지 5종 약 8.5GB와 px4 빌드 캐시)"
  fi
else
  warn "디스크 여유를 확인하지 못했다($root_dir)"
fi

# (h) 메모리
mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2> /dev/null)"
if [ -n "$mem_kb" ]; then
  mem_gb=$(awk -v k="$mem_kb" 'BEGIN {printf "%.1f", k / 1024 / 1024}')
  if awk -v g="$mem_gb" -v m="$MIN_MEM_GB" 'BEGIN {exit !(g >= m * 0.95)}'; then
    ok "메모리 약 ${mem_gb}GB"
  else
    warn "메모리 약 ${mem_gb}GB: ${MIN_MEM_GB}GB(확인된 최소)보다 작다. 그 아래에서 PX4 빌드와 스택 실행은 미실측이다"
  fi
else
  warn "메모리를 확인하지 못했다"
fi

# (i) 화면
if [ -n "${DISPLAY:-}" ]; then
  ok "DISPLAY=$DISPLAY"
else
  warn "DISPLAY가 비어 있다. 화면 확인 도구(QGC, Gazebo GUI)를 쓰지 않으면 무시해도 된다"
fi

# (j) 포트 충돌 힌트
if command -v ss > /dev/null 2>&1; then
  ss_out="$(ss -ulnp 2> /dev/null || true)"
  conflict=0
  k="${IDSIM_STACK_INDEX:-0}"
  agent_port=$((8888 + k))
  for port in "$agent_port" 14550; do
    # ss -ulnp 출력에서 Local Address:Port는 4번째 열이다(5번째는 Peer)
    if printf '%s\n' "$ss_out" | awk -v p=":$port" '$4 ~ p"$" {f=1} END {exit !f}'; then
      warn "UDP 포트 $port 가 이미 쓰이고 있다. 스택 번호를 바꿔 실행하라(예: IDSIM_STACK_INDEX=1). 14550은 GCS 포트라 바뀌지 않을 수 있다"
      conflict=1
    fi
  done
  [ "$conflict" -eq 0 ] && ok "UDP ${agent_port}(에이전트, 스택 번호 ${k}), 14550(GCS) 사용 중이지 않음"
else
  warn "ss 명령이 없어 포트 충돌을 확인하지 못했다"
fi

# (k) 다른 compose 프로젝트(참고)
if [ "$docker_ok" -eq 1 ]; then
  projects="$(docker compose ls -q 2> /dev/null | paste -sd ' ' -)"
  if [ -n "$projects" ]; then
    echo "INFO 실행 중인 compose 프로젝트: $projects (ROS 도메인, Gazebo 파티션이 겹치는지 확인)"
  else
    echo "INFO 실행 중인 compose 프로젝트 없음"
  fi
fi

# (l) archive.ubuntu.com
if [ "$offline" -eq 1 ]; then
  echo "INFO --offline: archive.ubuntu.com 검사를 건너뜀"
elif command -v curl > /dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MIRROR_URL" 2> /dev/null || true)"
  if [ "$code" = "200" ]; then
    ok "archive.ubuntu.com 응답 200"
  else
    warn "archive.ubuntu.com 응답 ${code:-없음}: 콜드 빌드가 막힐 수 있다"
  fi
fi

echo
if [ "$fails" -gt 0 ]; then
  echo "결과: FAIL $fails 건"
  exit 1
fi
echo "결과: 통과(WARN은 위를 확인)"
