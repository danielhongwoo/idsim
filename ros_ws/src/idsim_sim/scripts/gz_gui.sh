#!/usr/bin/env bash
# gz-gui 서비스(viz 프로필)의 진입 스크립트 (sim-base 이미지, 호스트 uid:gid로 실행).
#
# 이미 떠 있는 gazebo 서버(같은 GZ_PARTITION, GZ_IP)에 GUI 클라이언트만 붙인다.
# 화면 방식은 둘이다.
#   host     호스트 X11에 창을 띄운다. 실행 전에 X11 접속 조건을 점검하고, 빠졌으면 안내 메시지와
#            함께 종료 코드 1로 끝낸다. 점검을 통과하면 gz sim -g로 exec한다.
#   virtual  컨테이너 안의 가상 X 화면(Xvnc)에 띄우고 noVNC(websockify)로 브라우저에 보인다.
#            호스트 X11이 없는 호스트(Mac 등)에서 쓴다.
# IDSIM_GZ_GUI_DISPLAY=auto(기본)는 DISPLAY가 비어 있지 않고 Xauthority 파일을 읽을 수 있고 비어 있지
# 않으면 host, 아니면 virtual을 고른다. 조건은 호스트 X11이 있느냐뿐이다(OS로 나누지 않는다).
#
# host 방식의 점검
#   - DISPLAY가 비어 있지 않을 것. compose는 ${DISPLAY:-}를 넘긴다.
#   - Xauthority 파일(마운트 지점 /tmp/.Xauthority 고정, 스크립트가 XAUTHORITY로 내보낸다)이 있고 비어 있지 않으며 읽을 수 있을 것.
#     compose는 ${XAUTHORITY:-/dev/null}:/tmp/.Xauthority:ro로 마운트하므로 호스트에 XAUTHORITY가
#     없으면 /dev/null(크기 0)이 들어와 여기서 걸린다.
# 두 방식 공통
#   - GUI 설정 파일을 읽을 수 있을 것(못 읽으면 gz가 경고만 내고 기본 설정으로 뜬다).
#   - HOME에 쓸 수 없으면 /tmp/gz-home을 만들어 HOME으로 쓴다(gz GUI는 ~/.gz에 설정을 쓴다).
#
# virtual 방식
#   - Xvnc :<IDSIM_GZ_GUI_VDISPLAY>를 GUI 설정 파일의 <window> 크기로 띄운다. 창 관리자가 없으므로
#     gz 창은 그 크기로 화면 왼쪽 위(0,0)에 뜨고, 화면 크기를 창 크기와 같게 해야 창이 화면을 채운다.
#     client(noVNC)의 화면 크기 변경 요청은 받지 않는다(-AcceptSetDesktopSize=0). 브라우저에서는
#     resize=scale로 축소, 확대해 본다.
#   - X는 TCP로 열지 않는다(-nolisten tcp). 마운트된 /tmp/.X11-unix에는 파일 socket을 만들지 못하고
#     (관찰: 소유자가 root가 아니면 "Owner of /tmp/.X11-unix should be set to root", root 소유 0755
#     읽기 전용이면 "Mode ... should be set to 1777" 뒤 "failed to bind listener") abstract socket
#     (@/tmp/.X11-unix/X<번호>)으로만 연다. gz는 그 abstract socket으로 붙는다. host network에서는
#     abstract socket이 호스트, 다른 스택과 공유되므로 번호는 compose가 스택마다 나눠 주고, 접속은
#     컨테이너 안에서 만든 MIT-MAGIC-COOKIE로 제한한다. cookie는 argv에 드러나지 않게 stdin으로 넣는다.
#   - VNC도 TCP로 열지 않는다(-rfbport -1). 컨테이너 안의 unix socket(0600)에만 열고 websockify가
#     --unix-target으로 붙는다. TCP로 여는 것은 websockify의 127.0.0.1:<IDSIM_GZ_GUI_WEB_PORT>(noVNC
#     HTTP와 WebSocket) 하나다(관찰: host netns에 5900대, 6000대 LISTEN 없음).
#   - VNC 비밀번호는 없다(-SecurityTypes None). 웹 포트가 127.0.0.1에만 열린다는 전제다. 그 호스트에
#     로그인한 사용자는 누구나 화면을 보고 조작할 수 있다. 원격 호스트라면 ssh -L로 포트를 넘겨 보는
#     방법이 있다(확인하지 않았다).
#   - Xvnc, websockify, gz GUI 셋 중 하나가 끝나면 나머지를 끝내고 스크립트도 끝난다. 먼저 끝난 것은
#     wait -n -p가 돌려준 pid로 가린다. SIGTERM, SIGINT를 받으면 trap이 셋에 TERM을 보내고(5초 안에 안
#     끝나면 KILL) 끝낸다. 스크립트가 PID 1이어도(compose에 init이 없다) trap으로 신호를 받는다.
#     trap은 main이 virtual 방식을 고른 직후에 건다. 그 앞(bash 시작과 방식 선택, 수 ms)에 온 TERM은
#     PID 1이 버리므로 docker stop이 유예 뒤 KILL로 끝난다. host 방식은 trap 없이 gz로 exec한다.
#     종료 코드: gz GUI가 먼저 끝나면 그 코드, Xvnc나 websockify가 먼저 끝나면 1, TERM 143, INT 130.
#
# 입력 환경변수
#   DISPLAY                    host 방식의 X11 접속(XAUTHORITY는 스크립트가 /tmp/.Xauthority로 정한다)
#   GZ_PARTITION, GZ_IP        gazebo 서비스와 같은 값
#   IDSIM_GZ_GUI_DISPLAY       auto(기본, 비어 있어도 auto), host, virtual
#   IDSIM_GZ_GUI_WEB_PORT      virtual 방식의 noVNC 포트(127.0.0.1). 기본 6080. compose가 6080 + k를 넣는다
#   IDSIM_GZ_GUI_VDISPLAY      virtual 방식의 X display 번호. 기본 90. compose가 90 + k를 넣는다
#   IDSIM_GUI_CONFIG           GUI 설정 파일. 기본 /opt/idsim/sim/config/gui.config (idsim_sim 마운트)
#   IDSIM_GZ_GUI_ENGINE        GUI 렌더 엔진. 기본 ogre2
# 추가 인자는 gz sim -g 뒤에 그대로 붙는다.
#
# 이 파일을 source하면 함수만 정의하고 main은 돌지 않는다(test/test_gz_gui.py가 방식 선택을 시험한다).

set -euo pipefail

err() { echo "[gz_gui] ERROR: $*" >&2; }
log() { echo "[gz_gui] $*" >&2; }

# 마운트 지점은 /tmp/.Xauthority 고정이다. compose env에 의존하지 않고 여기서 XAUTHORITY를 정한다.
# 호스트 경로(XAUTHORITY=/run/user/...)가 그대로 넘어와도 컨테이너 안에는 그 파일이 없으므로 덮어쓴다.
# XAUTHORITY 없이 exec하면 Xlib이 HOME/.Xauthority를 찾아 인증에 실패한다(실측).
readonly xauth_file=/tmp/.Xauthority
readonly novnc_web=/usr/share/novnc

# virtual 방식의 신호 상태. on_signal이 쓰고 run_virtual이 읽는다.
term_rc=0
pids=()

# select_display_mode <요청> <DISPLAY 값> <Xauthority 파일>
# 고른 방식(host 또는 virtual)을 stdout에 쓴다. 요청 값이 잘못되면 안내를 남기고 1을 돌려준다.
select_display_mode() {
  local request="${1:-}" display="${2:-}" xauth="${3:-}"
  case "${request}" in
    "" | auto)
      if [ -n "${display}" ] && [ -r "${xauth}" ] && [ -s "${xauth}" ]; then
        echo host
      else
        echo virtual
      fi
      ;;
    host | virtual)
      echo "${request}"
      ;;
    *)
      err "IDSIM_GZ_GUI_DISPLAY=${request} 는 auto, host, virtual 중 하나가 아니다."
      return 1
      ;;
  esac
}

# gui_window_geometry <GUI 설정 파일>
# <window> 안의 <width>, <height>를 "<가로>x<세로>"로 쓴다. 둘 중 하나라도 없으면 1을 돌려준다.
gui_window_geometry() {
  local block width height
  block="$(sed -n '/<window>/,/<\/window>/p' "$1")"
  width="$(sed -n 's:.*<width>[[:space:]]*\([0-9][0-9]*\)[[:space:]]*</width>.*:\1:p' <<<"${block}" | head -n 1)"
  height="$(sed -n 's:.*<height>[[:space:]]*\([0-9][0-9]*\)[[:space:]]*</height>.*:\1:p' <<<"${block}" | head -n 1)"
  if [ -z "${width}" ] || [ -z "${height}" ]; then
    return 1
  fi
  echo "${width}x${height}"
}

# host 방식의 X11 접속 조건 점검. 빠졌으면 안내 메시지와 함께 종료 코드 1로 끝낸다.
check_host_x11() {
  if [ -z "${DISPLAY:-}" ]; then
    err "DISPLAY가 비어 있다. 호스트 셸에서 DISPLAY를 내보낸 뒤 다시 올려라(예: export DISPLAY=:0)."
    exit 1
  fi

  if [ -e "${xauth_file}" ] && [ ! -r "${xauth_file}" ]; then
    err "Xauthority 파일(${xauth_file})을 uid $(id -u)가 읽을 수 없다(보통 0600)."
    err "컨테이너를 그 파일 소유자(호스트 사용자)의 uid:gid로 실행하라."
    exit 1
  fi

  if [ ! -s "${xauth_file}" ]; then
    err "Xauthority 파일(${xauth_file})이 없거나 비어 있다."
    err "호스트 셸에서 XAUTHORITY를 내보낸 뒤 다시 올려라. compose는 \${XAUTHORITY:-/dev/null}을 마운트한다."
    err "GNOME Wayland(Xwayland)라면 로그인마다 이름이 바뀌는 파일을 쓴다:"
    err "  export XAUTHORITY=\$(ls /run/user/\$(id -u)/.mutter-Xwaylandauth.* | head -n 1)"
    err "호스트 X11 없이 브라우저로 보려면 IDSIM_GZ_GUI_DISPLAY=virtual(또는 auto)로 올려라."
    exit 1
  fi
}

# on_signal <종료 코드>: virtual 방식의 TERM, INT trap(main이 건다). 전역 term_rc에 종료 코드를 기록하고
# 이미 띄운 자식(전역 pids)에 TERM을 보낸다. trap 문자열로만 불리므로 shellcheck가 호출을 찾지 못한다.
# shellcheck disable=SC2329
on_signal() {
  term_rc="$1"
  if [ "${#pids[@]}" -gt 0 ]; then
    kill -TERM "${pids[@]}" 2>/dev/null || true
  fi
}

# virtual 방식. Xvnc, websockify, gz GUI를 자식으로 띄우고 하나가 끝나거나 신호를 받으면 모두 끝낸다.
run_virtual() {
  local gui_config="$1"
  shift
  local vdisplay="${IDSIM_GZ_GUI_VDISPLAY:-90}" port="${IDSIM_GZ_GUI_WEB_PORT:-6080}" geometry
  if ! [[ "${vdisplay}" =~ ^[0-9]{1,4}$ ]]; then
    err "IDSIM_GZ_GUI_VDISPLAY=${vdisplay} 는 X display 번호(0-9999)가 아니다."
    exit 1
  fi
  if ! [[ "${port}" =~ ^[0-9]{1,5}$ ]] || [ "${port}" -lt 1 ] || [ "${port}" -gt 65535 ]; then
    err "IDSIM_GZ_GUI_WEB_PORT=${port} 는 포트 번호(1-65535)가 아니다."
    exit 1
  fi
  if ! geometry="$(gui_window_geometry "${gui_config}")"; then
    err "GUI 설정 파일(${gui_config})의 <window>에서 <width>, <height>를 찾지 못했다(가상 화면 크기로 쓴다)."
    exit 1
  fi
  if [ ! -f "${novnc_web}/vnc.html" ]; then
    err "${novnc_web}/vnc.html이 없다. sim-base 이미지에 novnc가 들어 있는지 확인하라."
    exit 1
  fi

  local rundir
  rundir="$(mktemp -d /tmp/gz-gui-virtual.XXXXXX)"
  local sock="${rundir}/vnc.sock" cookie="${rundir}/Xauthority"
  # 빈 파일을 먼저 만들어 xauth의 "file does not exist" 경고를 없앤다(rundir은 0700).
  : >"${cookie}"
  # cookie 값이 xauth의 argv(ps, /proc/<pid>/cmdline)에 드러나지 않게 명령을 stdin으로 준다.
  xauth -q -f "${cookie}" source - <<<"add :${vdisplay} MIT-MAGIC-COOKIE-1 $(mcookie)"
  # 같은 컨테이너가 재시작되면 지난 Xvnc의 lock 파일이 남아 "already active"로 거부된다.
  # 이 컨테이너 안에서 이 번호를 쓰는 X 서버는 이 스크립트가 띄운 것뿐이다.
  rm -f "/tmp/.X${vdisplay}-lock"

  local xvnc_pid ws_pid gz_pid
  # TERM, INT trap(on_signal)은 main이 이미 걸었다. 신호를 받으면 종료 코드를 기록하고 이미 띄운 자식에
  # TERM을 보낸다. 자식이 끝나므로 wait -n이 어느 시점에 시작되든 돌아온다. 자식을 띄우기 전이나 띄운
  # 직후와 pid를 기록하기 전 사이에 온 신호는 아래의 term_rc 확인이 잡는다. 정리는 아래 한곳에서 한다.
  if [ "${term_rc}" -ne 0 ]; then
    rm -rf "${rundir}"
    log "신호를 받아 끝낸다."
    exit "${term_rc}"
  fi

  Xvnc ":${vdisplay}" \
    -geometry "${geometry}" -depth 24 \
    -desktop "idsim gz-gui" \
    -auth "${cookie}" -nolisten tcp \
    -rfbport -1 -rfbunixpath "${sock}" -rfbunixmode 0600 \
    -SecurityTypes None \
    -AcceptSetDesktopSize=0 &
  xvnc_pid=$!
  pids+=("${xvnc_pid}")

  # Xvnc는 X listen socket을 연 뒤 VNC unix socket을 만든다. 그 socket이 생기면 준비된 것으로 본다.
  local i
  for ((i = 0; i < 100; i++)); do
    [ -S "${sock}" ] && break
    if ! kill -0 "${xvnc_pid}" 2>/dev/null || [ "${term_rc}" -ne 0 ]; then
      break
    fi
    sleep 0.1
  done
  if [ "${term_rc}" -ne 0 ] || [ ! -S "${sock}" ]; then
    [ "${term_rc}" -ne 0 ] || err "Xvnc :${vdisplay}가 뜨지 못했다(바로 끝났거나 10초 안에 준비되지 않았다). 같은 번호를 다른 스택이나 호스트의 X 서버가 쓰고 있지 않은지 확인하라."
    kill -TERM "${xvnc_pid}" 2>/dev/null || true
    wait "${xvnc_pid}" 2>/dev/null || true
    rm -rf "${rundir}"
    if [ "${term_rc}" -ne 0 ]; then
      log "신호를 받아 끝낸다."
      exit "${term_rc}"
    fi
    exit 1
  fi

  websockify --web "${novnc_web}" --unix-target="${sock}" "127.0.0.1:${port}" &
  ws_pid=$!
  pids+=("${ws_pid}")

  # XDG_RUNTIME_DIR이 없으면 Qt가 경고를 남기고 /tmp/runtime-<사용자>를 만든다. 0700인 rundir을 준다.
  DISPLAY=":${vdisplay}" XAUTHORITY="${cookie}" XDG_RUNTIME_DIR="${rundir}" gz sim -g \
    --gui-config "${gui_config}" \
    --render-engine-gui "${IDSIM_GZ_GUI_ENGINE:-ogre2}" \
    "$@" &
  gz_pid=$!
  pids+=("${gz_pid}")

  log "가상 화면 :${vdisplay} (${geometry}). 브라우저 주소: http://127.0.0.1:${port}/vnc.html?autoconnect=1&resize=scale"

  # 셋 중 하나가 끝나거나 trap한 신호가 오면 wait -n이 돌아온다. 끝난 자식의 pid는 done_pid에 온다
  # (신호로 깨어나면 비어 있다). 신호가 이미 와 있으면 기다리지 않는다.
  local rc=0 done_pid=""
  if [ "${term_rc}" -eq 0 ]; then
    wait -n -p done_pid "${pids[@]}" || rc=$?
  fi
  trap '' TERM INT

  local exit_rc
  if [ "${term_rc}" -ne 0 ]; then
    log "신호를 받아 끝낸다."
    exit_rc="${term_rc}"
  elif [ "${done_pid:-}" = "${gz_pid}" ]; then
    log "gz GUI가 끝났다(종료 코드 ${rc})."
    exit_rc="${rc}"
  elif [ "${done_pid:-}" = "${xvnc_pid}" ]; then
    err "Xvnc가 먼저 끝났다(종료 코드 ${rc})."
    exit_rc=1
  elif [ "${done_pid:-}" = "${ws_pid}" ]; then
    err "websockify가 먼저 끝났다(종료 코드 ${rc}). 포트 127.0.0.1:${port}를 다른 프로세스가 쓰고 있지 않은지 확인하라."
    exit_rc=1
  else
    err "끝난 자식을 가리지 못했다(wait 종료 코드 ${rc})."
    exit_rc=1
  fi

  # gz GUI부터 끝내고(X 연결이 끊기기 전에 스스로 내려가게) 나머지를 끝낸다.
  stop_children "${gz_pid}" "${ws_pid}" "${xvnc_pid}"
  rm -rf "${rundir}"
  exit "${exit_rc}"
}

# stop_children <pid>...: TERM을 보내고 최대 5초 기다린 뒤 남은 것은 KILL한다.
# gz sim -g는 기동 초기(시작 뒤 약 1초)에 받은 TERM에 끝나지 않는 경우가 있다. 관찰 두 가지:
#   - 시작 1초 뒤 gz에만 TERM을 보내고 2초 뒤 생존을 본 시험에서 8회 중 3회 살아 있었다. 그때 TERM은
#     ruby의 handler에 잡혀 있고 주 스레드는 C++ 쪽 futex에서 기다린다. TERM을 다시 보내도 같다.
#   - docker stop 시간을 잰 시험(시작 0.3-8초 뒤 stop)에서는 31회 중 2회가 5초대(5.15, 5.18초)였고,
#     둘 다 시작 1.0초 뒤 stop이었다(1.0초 시험 11회 중 2회. 31회 중 15회는 TERM을 1초마다 다시 보내던
#     변형으로 쟀고 5.15초가 그쪽이다). 나머지는 0.15-0.86초다.
# 그 경우는 5초 뒤 KILL로 끝나며 docker stop의 기본 유예 10초 안이다.
stop_children() {
  local pid alive i
  for pid in "$@"; do
    kill -TERM "${pid}" 2>/dev/null || true
  done
  for ((i = 0; i < 50; i++)); do
    alive=0
    for pid in "$@"; do
      kill -0 "${pid}" 2>/dev/null && alive=1
    done
    [ "${alive}" -eq 0 ] && break
    sleep 0.1
  done
  for pid in "$@"; do
    if kill -0 "${pid}" 2>/dev/null; then
      err "pid ${pid}가 TERM 뒤 5초 안에 끝나지 않아 KILL한다."
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

main() {
  local mode
  mode="$(select_display_mode "${IDSIM_GZ_GUI_DISPLAY:-auto}" "${DISPLAY:-}" "${xauth_file}")" || exit 1

  # virtual 방식은 스크립트가 PID 1로 남아 자식을 거두므로 여기서 바로 trap을 건다. 이 뒤의 설정 파일
  # 확인, mktemp, xauth 중에 온 신호도 term_rc에 남아 run_virtual이 끝낸다. host 방식은 gz로 exec하므로
  # 걸지 않는다(지금까지와 같다).
  if [ "${mode}" = virtual ]; then
    trap 'on_signal 143' TERM
    trap 'on_signal 130' INT
  fi

  if [ "${mode}" = host ]; then
    export XAUTHORITY="${xauth_file}"
    check_host_x11
  fi

  local gui_config="${IDSIM_GUI_CONFIG:-/opt/idsim/sim/config/gui.config}"
  # gz는 --gui-config 파일을 못 읽으면 경고만 내고 기본 설정(WorldControl 포함)으로 뜬다.
  # 일시정지 버튼이 조용히 돌아오는 것을 막기 위해 여기서 먼저 확인한다.
  if [ ! -r "${gui_config}" ]; then
    err "GUI 설정 파일(${gui_config})이 없거나 읽을 수 없다. idsim_sim 마운트(/opt/idsim/sim)를 확인하라."
    exit 1
  fi

  if [ -z "${HOME:-}" ] || [ ! -d "${HOME}" ] || [ ! -w "${HOME}" ]; then
    mkdir -p /tmp/gz-home
    export HOME=/tmp/gz-home
  fi

  if [ "${mode}" = host ]; then
    log "화면 방식: host (DISPLAY=${DISPLAY})"
    exec gz sim -g \
      --gui-config "${gui_config}" \
      --render-engine-gui "${IDSIM_GZ_GUI_ENGINE:-ogre2}" \
      "$@"
  fi

  log "화면 방식: virtual"
  if [ -n "${DISPLAY:-}" ] && [ "${IDSIM_GZ_GUI_DISPLAY:-auto}" = auto ]; then
    log "DISPLAY(${DISPLAY})는 있지만 Xauthority 파일(${xauth_file})이 없거나 비어 있거나 읽을 수 없어 virtual을 골랐다."
    log "호스트 X11에 띄우려면 호스트 셸에서 XAUTHORITY를 내보내라(IDSIM_GZ_GUI_DISPLAY=host로 올리면 점검 안내가 나온다)."
  fi
  run_virtual "${gui_config}" "$@"
}

# source되었으면 return이 성공하고 main을 건너뛴다. 직접 실행되면 return이 실패해 main을 부른다.
if ! (return 0 2>/dev/null); then
  main "$@"
fi
