"""ros2 topic info -v 원문 저장과 판정. rclpy 없이 ros2 CLI만 쓴다.

사용 예(저장소 루트, ros-ws 컨테이너의 /opt/idsim에서):
  python3 -m tests.support.topic_info --regex '<ns>/.*/vehicle_status(_v[0-9]+)?$' \
      --expect-publishers 1 --expect-type px4_msgs/msg/VehicleStatus --save DIR
종료 코드: 0 판정 통과, 1 판정 실패, 2 시간 안에 토픽을 찾지 못함.
"""
import argparse
import os
import re
import subprocess
import sys
import time

from tests.support import golden


def parse_topic_info(raw):
    """`ros2 topic info -v` 원문을 파싱한다.

    반환: {"type": str|None, "publisher_count": int, "subscription_count": int,
           "endpoints": [{"kind": "PUBLISHER"|"SUBSCRIPTION", "node": str, "type": str}]}
    개수 줄이 없으면 0으로 본다.
    """
    res = {"type": None, "publisher_count": 0, "subscription_count": 0, "endpoints": []}
    cur = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("Type:") and res["type"] is None:
            res["type"] = s.split(":", 1)[1].strip()
        elif s.startswith("Publisher count:"):
            res["publisher_count"] = int(s.split(":", 1)[1])
        elif s.startswith("Subscription count:"):
            res["subscription_count"] = int(s.split(":", 1)[1])
        elif s.startswith("Node name:"):
            cur = {"kind": None, "node": s.split(":", 1)[1].strip(), "type": None}
            res["endpoints"].append(cur)
        elif cur is not None and s.startswith("Topic type:"):
            cur["type"] = s.split(":", 1)[1].strip()
        elif cur is not None and s.startswith("Endpoint type:"):
            cur["kind"] = s.split(":", 1)[1].strip()
    return res


def find_topics(list_text, regex):
    """topic list -t 원문에서 정규식(re.search)에 맞는 (토픽, 타입) 목록."""
    pat = re.compile(regex)
    out = []
    for line in list_text.splitlines():
        m = re.match(r"^\s*(\S+)\s+\[([^\]\s,]+)", line)
        if m and pat.search(m.group(1)):
            out.append((m.group(1), m.group(2)))
    return sorted(out)


def judge(info, expect_publishers=None, expect_subscriptions=None, expect_type=None):
    """기대와 다른 항목의 설명 목록을 돌려준다. 비어 있으면 통과."""
    errs = []
    if expect_publishers is not None and info["publisher_count"] != expect_publishers:
        errs.append("Publisher count %d != %d" % (info["publisher_count"], expect_publishers))
    if expect_subscriptions is not None and info["subscription_count"] != expect_subscriptions:
        errs.append("Subscription count %d != %d"
                    % (info["subscription_count"], expect_subscriptions))
    if expect_type is not None and info["type"] != expect_type:
        errs.append("type %s != %s" % (info["type"], expect_type))
    return errs


def _run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, LC_ALL="C")).stdout


def run(args, runner=_run, clock=time.monotonic, sleep=time.sleep, out=sys.stdout):
    start = clock()
    while True:
        found = find_topics(runner(["ros2", "topic", "list", "-t", "--no-daemon"]), args.regex)
        if found:
            break
        if clock() - start >= args.timeout:
            print("토픽을 찾지 못함: %s" % args.regex, file=out)
            return 2
        sleep(1.0)
    rc = 0
    for topic, _ in found:
        # 발견 직후 엔드포인트 수가 덜 잡힐 수 있어 판정이 맞을 때까지 시간 안에서 재시도한다.
        # --no-daemon은 프로세스마다 탐색을 새로 하므로 list에서 본 토픽을 info가 아직 모를 수 있다
        # ("Unknown topic", 종료 코드 1). 이 실패도 같은 시간 안에서 재시도한다.
        while True:
            try:
                raw = runner(["ros2", "topic", "info", "-v", "--no-daemon", topic])
            except subprocess.CalledProcessError:
                if clock() - start >= args.timeout:
                    raise
                sleep(1.0)
                continue
            info = parse_topic_info(raw)
            errs = judge(info, args.expect_publishers, args.expect_subscriptions,
                         args.expect_type)
            if not errs or clock() - start >= args.timeout:
                break
            sleep(1.0)
        if args.save:
            rel = topic.lstrip("/")
            if args.ns:
                rel = golden._strip_ns(topic, args.ns) or rel
            path = os.path.join(args.save, rel + ".txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", newline="\n") as f:
                f.write(raw)
        print("%s %s pub=%d sub=%d %s" % (
            "PASS" if not errs else "FAIL", topic, info["publisher_count"],
            info["subscription_count"], "; ".join(errs)), file=out)
        if errs:
            rc = 1
    return rc


def main(argv=None):
    p = argparse.ArgumentParser(prog="tests.support.topic_info")
    p.add_argument("--regex", required=True, help="토픽 이름 정규식(re.search)")
    p.add_argument("--expect-publishers", type=int)
    p.add_argument("--expect-subscriptions", type=int)
    p.add_argument("--expect-type")
    p.add_argument("--save", help="원문 저장 디렉터리. 파일은 <토픽>.txt")
    p.add_argument("--ns", default="", help="저장 경로에서 뗄 네임스페이스")
    p.add_argument("--timeout", type=float, default=30.0, help="초(벽시계)")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
