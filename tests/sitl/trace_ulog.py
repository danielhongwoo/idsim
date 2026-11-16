#!/usr/bin/env python3
# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""비행 시나리오의 ULog 기록을 sitl/trace_ulog.json으로 남긴다(호스트에서, compose stop 뒤. 기록 전용).

사용법: tests/sitl/trace_ulog.py <실행 디렉터리> [--sitl-dir sitl]
요약 로직은 tests/support/ulog_flight.py에 있다. 종료 코드: 0 기록함, 2 입력 없음이나 예외(run_sitl.sh는 종료 코드를
판정에 넣지 않는다). F1-F4가 돌지 않은 실행에서는 빈 목록을 쓴다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import ulog_flight  # noqa: E402
from tests.support import ulog_min  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--sitl-dir", default="sitl")
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    out = run / a.sitl_dir
    try:
        events = [json.loads(ln) for ln in (out / "trace.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        wanted = [e for e in events if e.get("kind") in ("flight_window", "air_start")]
        res = {"ulog": None, "track": [], "air_start": []}
        if wanted:
            ulog_dir = json.loads((run / "stack.json").read_text(encoding="utf-8"))["vehicles"][0]["ulog_dir"]
            ulogs = sorted(run.glob(ulog_dir + "/**/*.ulg"), key=lambda p: p.stat().st_mtime)
            if not ulogs:
                print("trace_ulog: ULog가 없다", file=sys.stderr)
                return 2
            topics = ulog_min.read_topics(str(ulogs[-1]), ulog_flight.TOPICS)
            res = dict(ulog_flight.build(wanted, topics), ulog=str(ulogs[-1].relative_to(run)))
        (out / "trace_ulog.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("trace_ulog: TRACK_ENTITY 구간 %d, 공중 시작 구간 %d" % (len(res["track"]), len(res["air_start"])),
              file=sys.stderr)
        return 0
    except Exception as e:  # noqa: BLE001 기록 전용이라 어떤 예외든 2로 접는다
        print("trace_ulog: 예외 %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
