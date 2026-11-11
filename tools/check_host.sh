#!/usr/bin/env bash
# 호스트 조건 점검: idsim을 빌드하고 돌릴 수 있는 호스트인지 읽기 전용으로 확인한다.
#
# 사용법: tools/check_host.sh [--offline] [--help]
#   --offline  외부 네트워크 검사(versions.env의 UBUNTU_APT_MIRROR)를 건너뛴다
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
VERSIONS_ENV="$(dirname "$0")/../docker/versions.env"
# 이미지 빌드가 쓰는 apt 미러 (환경변수가 있으면 그 값, 없으면 versions.env)
MIRROR_BASE="${UBUNTU_APT_MIRROR:-$(sed -n 's/^UBUNTU_APT_MIRROR=//p' "$VERSIONS_ENV" 2> /dev/null | head -n 1)}"
MIRROR_BASE="${MIRROR_BASE%/}"
MIRROR_URL="${MIRROR_BASE}/dists/noble/Release"
MIRROR_HOST="${MIRROR_BASE#*://}"
MIRROR_HOST="${MIRROR_HOST%%/*}"

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
  # 생성 compose의 bridge healthcheck가 start_interval을 쓴다. Docker 문서상 Engine 25.0(API 1.44)부터 지원.
  # 하한은 문서 근거이며 실측은 29.1.3(Compose 2.40.3)뿐이다. 그 아래에서는 healthcheck가 거부되거나 무시될 수 있다.
  sv="$(docker version --format '{{.Server.Version}}' 2> /dev/null || true)"
  sv_major="${sv%%.*}"
  if [ -z "$sv" ] || ! [ "$sv_major" -eq "$sv_major" ] 2> /dev/null; then
    warn "Docker Engine 버전을 읽지 못했다('${sv}'). 25.0 이상이 필요하다(healthcheck start_interval)"
  elif [ "$sv_major" -ge 25 ]; then
    ok "Docker Engine $sv (25.0 이상, healthcheck start_interval 지원)"
  else
    warn "Docker Engine $sv: 25.0 미만이다. 생성 compose의 healthcheck start_interval이 동작하지 않을 수 있다"
  fi
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

# (i) 화면. gz-gui(viz 프로필)는 DISPLAY와 XAUTHORITY 파일을 읽기 전용으로 받는다
if [ -n "${DISPLAY:-}" ]; then
  ok "DISPLAY=$DISPLAY"
else
  warn "DISPLAY가 비어 있다. 화면 확인 도구(QGC, Gazebo GUI)를 쓰지 않으면 무시해도 된다"
fi
if [ -n "${XAUTHORITY:-}" ] && [ -s "${XAUTHORITY}" ] && [ -r "${XAUTHORITY}" ]; then
  ok "XAUTHORITY=$XAUTHORITY"
elif [ -n "${XAUTHORITY:-}" ]; then
  warn "XAUTHORITY 파일($XAUTHORITY)이 없거나 비어 있거나 읽을 수 없다. Gazebo GUI가 X 서버 인증에 실패한다"
else
  warn "XAUTHORITY가 비어 있다. Gazebo GUI(tools/sim_stack.sh up --viz)를 쓰려면 내보내라. GNOME Wayland: export XAUTHORITY=\$(ls /run/user/\$(id -u)/.mutter-Xwaylandauth.* | head -n 1)"
fi

# (j) 포트 충돌 힌트
if command -v ss > /dev/null 2>&1; then
  ss_out="$(ss -ulnp 2> /dev/null || true)"
  conflict=0
  k="${IDSIM_STACK_INDEX:-0}"
  case "$k" in [0-9]) ;; *) warn "IDSIM_STACK_INDEX '$k'가 0-9가 아니다. 0으로 본다"; k=0 ;; esac
  # 포트 식의 출처는 tools/gen_compose.py 상수 하나다. 저장소 밖에서 돌아 생성기를 못 찾으면 이 검사를 건너뛴다
  gen_py="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2> /dev/null && pwd)/gen_compose.py"
  agent_port=""
  gcs_port=""
  if [ -f "$gen_py" ] && command -v python3 > /dev/null 2>&1; then
    agent_port="$(python3 "$gen_py" --print-agent-port "$k" 2> /dev/null || true)"
    gcs_port="$(python3 "$gen_py" --print-gcs-port "$k" 2> /dev/null || true)"
  fi
  if [ -z "$agent_port" ] || [ -z "$gcs_port" ]; then
    warn "tools/gen_compose.py를 찾지 못해 포트 충돌을 확인하지 못했다(저장소 밖에서 실행했거나 python3가 없다)"
    agent_port=""
    gcs_port=""
  fi
  for port in $agent_port $gcs_port; do
    # ss -ulnp 출력에서 Local Address:Port는 4번째 열이다(5번째는 Peer)
    if printf '%s\n' "$ss_out" | awk -v p=":$port" '$4 ~ p"$" {f=1} END {exit !f}'; then
      warn "UDP 포트 $port 가 이미 쓰이고 있다. 스택 번호를 바꿔 실행하라(예: tools/sim_stack.sh up --stack 1). GCS 포트는 QGC가 듣는 중이면 정상이다"
      conflict=1
    fi
  done
  [ "$conflict" -eq 0 ] && [ -n "$agent_port" ] && ok "UDP ${agent_port}(에이전트), ${gcs_port}(GCS) 사용 중이지 않음 (스택 번호 ${k})"
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

# (l) apt 미러
if [ "$offline" -eq 1 ]; then
  echo "INFO --offline: apt 미러(${MIRROR_HOST}) 검사를 건너뜀"
elif command -v curl > /dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MIRROR_URL" 2> /dev/null || true)"
  if [ "$code" = "200" ]; then
    ok "apt 미러 ${MIRROR_HOST} 응답 200"
  else
    warn "apt 미러 ${MIRROR_HOST} 응답 ${code:-없음}: 콜드 빌드가 막힐 수 있다"
  fi
fi

echo
if [ "$fails" -gt 0 ]; then
  echo "결과: FAIL $fails 건"
  exit 1
fi
echo "결과: 통과(WARN은 위를 확인)"
