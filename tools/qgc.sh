#!/usr/bin/env bash
# QGroundControl(GCS)을 호스트에서 직접 실행한다. compose 서비스가 아니며 판정, 스모크, CI와 무관한 개발자용 화면이다.
#
# docker/versions.env에 고정한 버전(QGC_VERSION)과 sha256(QGC_APPIMAGE_SHA256)의 AppImage를
# ${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/QGroundControl-x86_64.AppImage 에 받아 두고 실행한다.
# 없거나 sha256이 다르면 다시 받는다. 검증에 실패하면 파일을 지우고 종료 코드 1로 끝난다.
#
# 연결: PX4 SITL은 GCS 포트 14550(UDP, 모든 PX4 인스턴스 공통)으로 MAVLink를 보내고 QGC가 그 포트를 듣는다.
# 주의: COM_RC_IN_MODE=4라 QGC의 수동 모드와 가상 조이스틱은 쓸 수 없다. 모니터링과 ARM/TAKEOFF/LAND 명령용이다.
# 종료: Ctrl-C(INT)나 TERM을 받으면 QGC에 TERM을 보내 정상 종료(설정 저장)를 기다리고, 5초 안에 끝나지 않으면
#       SIGKILL로 끝낸다. 기체가 연결된 상태에서는 QGC가 종료 확인 대화상자를 띄워 멈출 수 있어 유예 뒤 KILL이 필요하다.
# AppImage는 static type2 런타임이라 libfuse2가 없어도 실행된다.
#
# 사용법: tools/qgc.sh [--download-only | --print-path | --help] [QGC 인자...]
#   --download-only  내려받아 검증만 하고 끝낸다
#   --print-path     캐시된 AppImage 경로를 출력한다(없으면 먼저 받는다)
#   그 외 인자는 QGC에 그대로 전달한다

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${repo_root}/docker/versions.env"

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

read_key() {
  # versions.env를 source하지 않고 키 하나만 읽는다
  local v
  v="$(grep -E "^$1=" "$env_file" | tail -n 1 | cut -d= -f2-)"
  [ -n "$v" ] || { echo "qgc.sh: ${env_file}에 $1 이 없다" >&2; exit 1; }
  printf '%s' "$v"
}

mode="run"
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  --download-only) mode="download"; shift ;;
  --print-path) mode="path"; shift ;;
esac

version="$(read_key QGC_VERSION)"
want_sha="$(read_key QGC_APPIMAGE_SHA256)"
dir="${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/${version}"
app="${dir}/QGroundControl-x86_64.AppImage"
url="https://github.com/mavlink/qgroundcontrol/releases/download/${version}/QGroundControl-x86_64.AppImage"

sha_ok() { [ -f "$1" ] && [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$want_sha" ]; }

ensure_app() {
  if sha_ok "$app"; then
    return 0
  fi
  mkdir -p "$dir"
  rm -f "$app"
  local tmp
  rm -f "${dir}"/.download.*
  tmp="$(mktemp "${dir}/.download.XXXXXX")"
  # 내려받는 중 Ctrl-C가 와도 임시 파일을 남기지 않는다
  trap 'rm -f "$tmp"; exit 130' INT TERM
  echo "qgc.sh: ${url} 을 내려받는다" >&2
  if ! curl -fsS -L -o "$tmp" "$url"; then
    rm -f "$tmp"
    echo "qgc.sh: 내려받기 실패" >&2
    exit 1
  fi
  if ! sha_ok "$tmp"; then
    rm -f "$tmp"
    echo "qgc.sh: sha256 불일치. 파일을 지웠다" >&2
    exit 1
  fi
  chmod +x "$tmp"
  mv -f "$tmp" "$app"
  trap - INT TERM
}

ensure_app

case "$mode" in
  download) echo "qgc.sh: 준비됨 ${app}" >&2; exit 0 ;;
  path) printf '%s\n' "$app"; exit 0 ;;
esac

# exec 대신 자식으로 띄운다. 신호 처리기에서 QGC에 TERM을 보내고 유예 뒤 KILL로 끝내기 위해서다.
# AppRun이 QGC 바이너리를 exec하므로 $child가 QGC 본체 PID다.
child=""
grace=5
# shellcheck disable=SC2329  # trap에서 호출된다
cleanup() {
  local sig="$1" i
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child" 2>/dev/null || true
    for ((i = 0; i < grace * 10; i++)); do
      kill -0 "$child" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL "$child" 2>/dev/null || true
  fi
  # 셸 관례: INT는 130, TERM은 143
  case "$sig" in TERM) exit 143 ;; *) exit 130 ;; esac
}
trap 'cleanup INT' INT
trap 'cleanup TERM' TERM

"$app" "$@" &
child=$!
rc=0
while kill -0 "$child" 2>/dev/null; do
  wait "$child" || rc=$?
  # 신호로 wait가 깨어난 경우 trap이 먼저 처리되므로 여기서는 자식이 끝난 경우만 남는다
done
exit "$rc"
