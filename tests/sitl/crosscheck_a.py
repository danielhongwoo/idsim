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

"""시나리오 A의 vehicle_status 원시 표본을 ULog와 교차 확인한다(호스트에서, compose stop 뒤).

값의 정본은 PX4이므로 ROS로 받은 원시 표본(sitl/raw_status_A.jsonl)을 ULog의 vehicle_status와 대조한다.
대조 로직은 측정 스크립트와 같은 tests/support/measure_check.check_row를 쓴다(ROS 표본이 ULog에 있는지,
필드가 같은지, ULog에만 있는 표본(ROS 유실)이 있는지, ULog 기준 OFFBOARD가 아닌 ARMED 표본 수).
  - 위반 구간: goal 전송부터 TAKEOFF 시작 feedback의 stamp 뒤 0.5 s까지(늦게 도착하는 표본을 덮는다)
  - 비행 구간: 그 뒤 LAND 시작 feedback까지(TAKEOFF와 LOITER 동안 OFFBOARD여야 한다)
사용법: tests/sitl/crosscheck_a.py <실행 디렉터리> [--sitl-dir sitl]
결과: <실행 디렉터리>/<sitl-dir>/crosscheck_a.json.
종료 코드: 0 통과, 1 ULog 기준 OFFBOARD가 아닌 ARMED 표본이 위반 구간(ulog_armed_non_offboard)이나 비행 구간
(ulog_flight_armed_non_offboard)에 있음(실행 실패), 2 판정 불가(입력 없음. run_sitl.sh가 INFRA로 따로 분류).
ros_missing_in_ulog, ros_field_mismatch, ulog_only는 기록만 하고 판정에서 뺀다. ulog_only가 0이 아니면 notes에 적는다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import measure_check as mc  # noqa: E402
from tests.support import ulog_min  # noqa: E402

WINDOW_SLACK_US = 500_000


def build_row(armed_a, raw_status):
    """armed_a.json과 raw_status_A.jsonl로 check_row가 읽는 행을 만든다. 입력이 모자라면 (None, 이유)."""
    if not armed_a.get("takeoff_start_seen"):
        return None, "TAKEOFF 시작 feedback을 보지 못했다"
    if "land_start_recv_us" not in armed_a:
        return None, "LAND 시작 feedback을 보지 못했다"
    lo, end_ts = armed_a["window_us"]
    land_recv, land_ts = armed_a["land_start_recv_us"], armed_a["land_start_stamp_us"]
    row = {"item": "A", "attempt": 1, "verdict": "PASS", "facts": {
        "armed_window_ros_us": [lo, end_ts + WINDOW_SLACK_US], "arm_send": [lo, lo],
        "land_send": [land_recv, land_ts]}}
    raw = [r for r in raw_status if r["recv_ros_us"] <= land_recv]
    return row, raw


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--sitl-dir", default="sitl")
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    out = run / a.sitl_dir
    try:
        armed_a = json.loads((out / "armed_a.json").read_text(encoding="utf-8"))
        raw = [json.loads(ln) for ln in (out / "raw_status_A.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        ulogs = sorted(run.glob("px4-*/log/**/*.ulg"), key=lambda p: p.stat().st_mtime)
    except OSError as e:
        print("입력을 읽지 못했다: %s" % e, file=sys.stderr)
        return 2
    if not ulogs:
        print("ULog가 없다", file=sys.stderr)
        return 2
    rows = [{"ts_us": r["timestamp"], "recv_ros_us": r["recv_ros_us"], "arming_state": r["arming_state"],
             "nav_state": r["nav_state"], "failsafe": r["failsafe"], "intention": r["nav_state_user_intention"]}
            for r in raw]
    row, raw = build_row(armed_a, rows)
    why = raw
    if row is None:
        print("판정 불가: %s" % why, file=sys.stderr)
        (out / "crosscheck_a.json").write_text(json.dumps({"status": 2, "reason": why}) + "\n", encoding="utf-8")
        return 2
    path = ulogs[-1]
    topics = ulog_min.read_topics(str(path), {"vehicle_status": 0})
    by_ts = {int(r["timestamp"]): r for r in topics["vehicle_status"]}
    res = mc.check_row(row, raw, by_ts, sorted(by_ts), ulog_min.read_logged(str(path)))
    bad = res["ulog_armed_non_offboard"] + res["ulog_flight_armed_non_offboard"]
    status = 1 if bad else 0
    notes = []
    if res["ulog_only"]:
        notes.append("ULog에만 있는 표본 %d개(ROS가 받지 못한 표본). 판정에는 쓰지 않는다" % res["ulog_only"])
    if res["ros_missing_in_ulog"] or res["ros_field_mismatch"]:
        notes.append("ROS 표본과 ULog의 불일치가 있다(기록만 한다)")
    res = dict(res, status=status, notes=notes, ulog=str(path.relative_to(run)))
    (out / "crosscheck_a.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("crosscheck A: ROS %d개 중 ULog에 없음 %d, 필드 불일치 %d, ULog에만 있는 표본 %d, ULog 기준 비OFFBOARD ARMED %d(비행 구간 %d), 종료 코드 %d%s"
          % (res["ros_samples"], res["ros_missing_in_ulog"], len(res["ros_field_mismatch"]), res["ulog_only"],
             res["ulog_armed_non_offboard"], res["ulog_flight_armed_non_offboard"], status,
             " " + "; ".join(notes) if notes else ""), file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
