#!/usr/bin/env python3
"""스모크 S2, S4의 PX4 쪽 판정(pxh 명령과 PX4 로그). 담당: px4-engineer.

check_px4.py(ros-ws, 토픽 판정)와 나눈 이유: pxh 모듈 명령(px4-commander 등)은
PX4 서버와 같은 컨테이너 안에서만 동작한다(서버 소켓이 컨테이너의 /tmp에 있다).
표준 라이브러리만 쓰므로 px4 컨테이너와 호스트 어디서나 python3로 돈다.

두 가지 모드가 있고 한 번에 하나만 쓴다.

1) --instance N : px4 컨테이너 안에서 실행. 다음을 판정하고 원문을 모은다.
   commander_check  "px4-commander --instance N check" 출력에 "Preflight check: OK"
   param_<이름>     "px4-param --instance N show <이름>"의 값이 기대값과 같음.
                    기대값은 --expect-param 이름=값 (여러 번). 기본은
                    COM_OBL_RC_ACT=4, COM_RC_IN_MODE=4
   param_show_all   "px4-param --instance N show" 전체 출력이 비어 있지 않음(원문 저장용)
   ver_all          "px4-ver --instance N all" 출력이 비어 있지 않음(원문 저장용)
   원문은 JSON의 raw 아래에 넣는다. IDSIM_BUILD_PX4_TAG 환경변수도 기록한다.

2) --log-file PATH : 호스트에서 실행. compose logs로 받은 PX4 로그에서 다음을 판정한다.
   gz_bridge_errors     gz_bridge 관련 오류 줄이 없음
   mavlink_bind_failed  "WARN  [mavlink] bind failed" 줄이 없음. 같은 호스트의 다른
                        스택과 MAVLink 포트가 겹치면 PX4는 이 경고만 내고 그 링크 없이
                        계속 돈다(docker/px4/px4-rc.mavlink의 IDSIM_MAVLINK_OFFSET 참조).
   PX4 로그는 컨테이너 stdout이라 컨테이너 안에서는 읽을 수 없기 때문이다.

결과는 JSON 한 덩어리로 stdout에 쓴다. 모두 통과하면 종료 코드 0, 판정 실패는 1,
인자 오류는 2(argparse).
"""
import argparse
import json
import os
import re
import subprocess
import sys

CMD_TIMEOUT_S = 15.0

DEFAULT_EXPECT = ["COM_OBL_RC_ACT=4", "COM_RC_IN_MODE=4"]

# gz_bridge 오류로 보는 줄. PX4 v1.17.0 px4-rc.gzsim과 gz_bridge 모듈의 오류 출력.
GZ_ERROR_PATTERNS = [
    r"ERROR\s+\[gz_bridge\]",
    r"ERROR\s+\[init\]\s+gz_bridge failed",
    r"ERROR\s+\[init\]\s+Timed out waiting for Gazebo world",
]

# MAVLink UDP 포트 bind 실패. PX4 v1.17.0 mavlink 모듈의 경고
# "WARN  [mavlink] bind failed: Address already in use".
MAVLINK_BIND_PATTERNS = [
    r"WARN\s+\[mavlink\]\s+bind failed",
]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class Report:
    def __init__(self, mode, **meta):
        self.data = {"mode": mode, "checks": [], "raw": {}}
        self.data.update(meta)

    def check(self, name, ok, **detail):
        self.data["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    def ok(self):
        return bool(self.data["checks"]) and all(c["ok"] for c in self.data["checks"])

    def emit(self):
        self.data["ok"] = self.ok()
        json.dump(self.data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        sys.stdout.flush()


def run_pxh(argv):
    """모듈 명령을 실행해 (종료 코드, stdout+stderr 문자열)을 돌려준다.

    PX4 클라이언트의 종료 코드는 판정 결과를 반영하지 않는 경우가 있어
    (uxrce_dds_client status 등) 판정은 출력 문자열로 한다. 코드는 기록만 한다.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=CMD_TIMEOUT_S, check=False)
        out = proc.stdout.decode("utf-8", errors="replace")
        return proc.returncode, ANSI_RE.sub("", out)
    except FileNotFoundError as exc:
        return 127, "not found: %s" % exc
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace")
        return 124, ANSI_RE.sub("", out) + "\n(timeout %.0fs)" % CMD_TIMEOUT_S


def server_down(out):
    return "PX4 server not running" in out


def parse_param_value(out, name):
    """param show 출력 "x + NAME [a,b] : VALUE" 에서 VALUE 문자열을 찾는다."""
    m = re.search(r"\b%s\s+\[\d+,\d+\]\s*:\s*(\S+)" % re.escape(name), out)
    return m.group(1) if m else None


def same_value(got, want):
    try:
        return float(got) == float(want)
    except (TypeError, ValueError):
        return got == want


def mode_pxh(args):
    n = str(args.instance)
    report = Report("pxh", instance=args.instance,
                    build_px4_tag=os.environ.get("IDSIM_BUILD_PX4_TAG"))

    rc, out = run_pxh(["px4-commander", "--instance", n, "check"])
    report.data["raw"]["commander_check"] = out
    report.check("commander_check", "Preflight check: OK" in out and not server_down(out),
                 rc=rc, expect="Preflight check: OK")

    for item in args.expect_param:
        name, _, want = item.partition("=")
        rc, out = run_pxh(["px4-param", "--instance", n, "show", name])
        got = parse_param_value(out, name)
        report.check("param_" + name, got is not None and same_value(got, want),
                     rc=rc, expected=want, received=got, line=out.strip())

    rc, out = run_pxh(["px4-param", "--instance", n, "show"])
    report.data["raw"]["param_show_all"] = out
    report.check("param_show_all", bool(out.strip()) and not server_down(out), rc=rc)

    rc, out = run_pxh(["px4-ver", "--instance", n, "all"])
    report.data["raw"]["ver_all"] = out
    report.check("ver_all", bool(out.strip()) and not server_down(out), rc=rc)

    return report


def mode_log(args):
    report = Report("log", log_file=args.log_file)
    try:
        with open(args.log_file, "rb") as f:
            text = ANSI_RE.sub("", f.read().decode("utf-8", errors="replace"))
    except OSError as exc:
        report.check("gz_bridge_errors", False, error=str(exc))
        report.check("mavlink_bind_failed", False, error=str(exc))
        return report
    pat = re.compile("|".join(GZ_ERROR_PATTERNS))
    hits = [line for line in text.splitlines() if pat.search(line)]
    report.check("gz_bridge_errors", not hits and bool(text.strip()),
                 lines=hits, patterns=GZ_ERROR_PATTERNS, log_empty=not text.strip())
    bind_re = re.compile("|".join(MAVLINK_BIND_PATTERNS))
    bind_hits = [line for line in text.splitlines() if bind_re.search(line)]
    report.check("mavlink_bind_failed", not bind_hits and bool(text.strip()),
                 lines=bind_hits, patterns=MAVLINK_BIND_PATTERNS, log_empty=not text.strip())
    return report


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--instance", type=int,
                   help="PX4 인스턴스 번호(px4 -i N의 N). px4 컨테이너 안에서 실행")
    g.add_argument("--log-file",
                   help="compose logs로 받은 PX4 로그 파일. 호스트에서 실행")
    p.add_argument("--expect-param", action="append", metavar="NAME=VALUE",
                   help="파라미터 기대값. 여러 번 줄 수 있다. 기본 %s" % " ".join(DEFAULT_EXPECT))
    args = p.parse_args(argv)
    if args.expect_param is None:
        args.expect_param = list(DEFAULT_EXPECT)
    for item in args.expect_param:
        if "=" not in item or not item.split("=", 1)[0]:
            p.error("--expect-param must be NAME=VALUE: %r" % item)
    if args.instance is not None and args.instance < 0:
        p.error("--instance must be >= 0")
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = mode_pxh(args) if args.instance is not None else mode_log(args)
    report.emit()
    return 0 if report.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
