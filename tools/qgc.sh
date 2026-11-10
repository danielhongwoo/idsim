#!/usr/bin/env bash
# QGroundControl(GCS)을 호스트에서 직접 실행한다. compose 서비스가 아니며 판정, 스모크, CI와 무관한 개발자용 화면이다.
#
# docker/versions.env에 고정한 버전(QGC_VERSION)과 sha256(QGC_APPIMAGE_SHA256)의 AppImage를
# ${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/QGroundControl-x86_64.AppImage 에 받아 두고 실행한다.
# 없거나 sha256이 다르면 다시 받는다. 검증에 실패하면 파일을 지우고 종료 코드 1로 끝난다.
#
# 연결: 스택 k의 PX4 SITL은 GCS 포트 14550 + 1000k(UDP, 스택 안 모든 인스턴스 공통)로 MAVLink를 보낸다.
#   실행 전에 QGC 설정 파일(${XDG_CONFIG_HOME:-$HOME/.config}/QGroundControl/QGroundControl.ini)의
#   [AutoConnect] udpListenPort를 그 포트로 고친다. QGC v5의 자동 연결 UDP 링크가 이 값으로 듣는다
#   (v5.1.5 소스 src/Settings/AutoConnect.SettingsGroup.json의 udpListenPort, 기본 14550). 포트 식은
#   tools/gen_compose.py의 상수가 유일한 출처이며 --print-gcs-port로 받는다(호스트 python3 표준 라이브러리).
#   --stack을 주지 않아도 k(IDSIM_STACK_INDEX, 없으면 0)의 포트로 맞춘다. MAV_SYS_ID가 스택 간에 같으므로
#   QGC 하나는 한 번에 한 스택만 본다.
# 주의: COM_RC_IN_MODE=4라 QGC의 수동 모드와 가상 조이스틱은 쓸 수 없다. 모니터링과 ARM/TAKEOFF/LAND 명령용이다.
# 종료: Ctrl-C(INT)나 TERM을 받으면 QGC에 TERM을 보내 정상 종료(설정 저장)를 기다리고, 5초 안에 끝나지 않으면
#       SIGKILL로 끝낸다. 기체가 연결된 상태에서는 QGC가 종료 확인 대화상자를 띄워 멈출 수 있어 유예 뒤 KILL이 필요하다.
# AppImage는 static type2 런타임이라 libfuse2가 없어도 실행된다.
#
# 사용법: tools/qgc.sh [--stack k] [--download-only | --print-path | --help] [QGC 인자...]
#   --stack k        스택 k(0-9)의 GCS 포트로 QGC 자동 연결 UDP 포트를 맞춘다
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
stack="${IDSIM_STACK_INDEX:-0}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --download-only) mode="download"; shift ;;
    --print-path) mode="path"; shift ;;
    --stack=*) stack="${1#--stack=}"; shift ;;
    --stack) stack="${2:-}"; shift 2 || { echo "qgc.sh: --stack 값이 없다" >&2; exit 2; } ;;
    *) break ;;
  esac
done

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

# QGC 자동 연결 UDP 포트를 스택 k의 GCS 포트로 맞춘다. 설정 파일의 다른 줄은 건드리지 않는다.
gcs_port="$(python3 "${repo_root}/tools/gen_compose.py" --print-gcs-port "$stack")" \
  || { echo "qgc.sh: 스택 번호는 0-9: '${stack}'" >&2; exit 2; }
ini="${XDG_CONFIG_HOME:-$HOME/.config}/QGroundControl/QGroundControl.ini"
if pgrep -x QGroundControl > /dev/null 2>&1 || pgrep -f 'QGroundControl-x86_64.AppImage' > /dev/null 2>&1; then
  echo "qgc.sh: 경고: QGroundControl이 이미 떠 있다. 이 편집은 QGC가 종료할 때 설정을 다시 써서 덮어쓸 수 있다(추정, 미실측). 기존 QGC를 닫고 다시 실행하라" >&2
fi
mkdir -p "$(dirname "$ini")"
python3 - "$ini" "$gcs_port" <<'PY'
import os
import sys

path, port = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
out, in_sec, seen_sec, done = [], False, False, False
for line in lines:
    s = line.strip()
    if s.startswith("[") and s.endswith("]"):
        if in_sec and not done:
            out.append("udpListenPort=" + port)
            done = True
        in_sec = s == "[AutoConnect]"
        seen_sec = seen_sec or in_sec
    elif in_sec and s.split("=", 1)[0].strip() == "udpListenPort":
        if not done:
            out.append("udpListenPort=" + port)
            done = True
        continue
    out.append(line)
if not done:
    if not seen_sec:
        if out and out[-1].strip():
            out.append("")
        out.append("[AutoConnect]")
    out.append("udpListenPort=" + port)
tmp = path + ".idsim-tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
os.replace(tmp, path)
PY
echo "qgc.sh: 스택 ${stack}, GCS UDP ${gcs_port}를 듣는다 (${ini} [AutoConnect] udpListenPort)" >&2
echo "qgc.sh: QGC 설정의 udpListenPort를 ${gcs_port}로 바꿨다. 스크립트가 끝나도 되돌리지 않는다. 기본으로 돌리려면 --stack 없이 다시 실행" >&2

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
