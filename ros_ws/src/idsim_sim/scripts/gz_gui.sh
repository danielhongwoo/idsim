#!/usr/bin/env bash
# gz-gui 서비스(viz 프로필)의 진입 스크립트 (sim-base 이미지, 호스트 uid:gid로 실행).
#
# 이미 떠 있는 gazebo 서버(같은 GZ_PARTITION, GZ_IP)에 GUI 클라이언트만 붙인다.
# 실행 전에 X11 접속 조건을 점검하고, 빠졌으면 안내 메시지와 함께 종료 코드 1로 끝낸다.
#
# 점검
#   - DISPLAY가 비어 있지 않을 것. compose는 ${DISPLAY:-}를 넘긴다.
#   - XAUTHORITY(기본 /tmp/.Xauthority) 파일이 있고 비어 있지 않으며 읽을 수 있을 것.
#     compose는 ${XAUTHORITY:-/dev/null}:/tmp/.Xauthority:ro로 마운트하므로 호스트에 XAUTHORITY가
#     없으면 /dev/null(크기 0)이 들어와 여기서 걸린다.
#   - GUI 설정 파일을 읽을 수 있을 것(못 읽으면 gz가 경고만 내고 기본 설정으로 뜬다).
#   - HOME에 쓸 수 없으면 /tmp/gz-home을 만들어 HOME으로 쓴다(gz GUI는 ~/.gz에 설정을 쓴다).
#
# 입력 환경변수
#   DISPLAY, XAUTHORITY        X11 접속
#   GZ_PARTITION, GZ_IP        gazebo 서비스와 같은 값
#   IDSIM_GUI_CONFIG           GUI 설정 파일. 기본 /opt/idsim/sim/config/gui.config (idsim_sim 마운트)
#   IDSIM_GZ_GUI_ENGINE        GUI 렌더 엔진. 기본 ogre2
# 추가 인자는 gz sim -g 뒤에 그대로 붙는다.

set -euo pipefail

err() { echo "[gz_gui] ERROR: $*" >&2; }

xauth_file="${XAUTHORITY:-/tmp/.Xauthority}"

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
  exit 1
fi

gui_config="${IDSIM_GUI_CONFIG:-/opt/idsim/sim/config/gui.config}"
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

exec gz sim -g \
  --gui-config "${gui_config}" \
  --render-engine-gui "${IDSIM_GZ_GUI_ENGINE:-ogre2}" \
  "$@"
