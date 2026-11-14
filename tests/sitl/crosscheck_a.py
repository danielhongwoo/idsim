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
대조 로직은 tests/support/measure_check.check_row를 쓴다(ROS 표본이 ULog에 있는지,
필드가 같은지, ULog에만 있는 표본(ROS 유실)이 있는지, ULog 기준 OFFBOARD가 아닌 ARMED 표본 수).
  - 위반 구간: goal 전송부터 TAKEOFF 시작 feedback의 stamp 뒤 0.5 s까지(늦게 도착하는 표본을 덮는다)
  - 비행 구간: 그 뒤 LAND 시작 feedback까지(TAKEOFF와 LOITER 동안 OFFBOARD여야 한다)
사용법: tests/sitl/crosscheck_a.py <실행 디렉터리> [--sitl-dir sitl]
결과: <실행 디렉터리>/<sitl-dir>/crosscheck_a.json.
종료 코드: 0 통과, 1 ULog 기준 OFFBOARD가 아닌 ARMED 표본이 위반 구간(ulog_armed_non_offboard)이나 비행 구간
(ulog_flight_armed_non_offboard)에 있음(실행 실패), 2 판정 불가(입력 없음, 대조가 비어 있음: ULog 구간 표본 0개, ULog ARMED 표본 0개, ROS 표본이 ULog에서 하나도
확인되지 않음, 파싱 중 예외. run_sitl.sh가 INFRA로 따로 분류).
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
    """armed_a.json과 raw_status_A.jsonl로 check_row가 읽는 행을 만든다. 입력이 모자라면 (None, 이유).

    LAND 시작 feedback이 없으면(A가 앞에서 실패) 있는 이정표까지, 곧 위반 구간(goal 전송부터 TAKEOFF 시작 뒤
    0.5 s, TAKEOFF 시작을 못 봤으면 기록 시점)만 대조하고 비행 구간은 보지 않는다."""
    if "window_us" not in armed_a:
        return None, "armed_a.json에 window_us가 없다"
    lo, end_ts = armed_a["window_us"]
    facts = {"armed_window_ros_us": [lo, end_ts + WINDOW_SLACK_US], "arm_send": [lo, lo]}
    raw = [r for r in raw_status if r["recv_ros_us"] <= end_ts + WINDOW_SLACK_US]
    if "land_start_recv_us" in armed_a:
        land_recv, land_ts = armed_a["land_start_recv_us"], armed_a["land_start_stamp_us"]
        facts["land_send"] = [land_recv, land_ts]
        raw = [r for r in raw_status if r["recv_ros_us"] <= land_recv]
    row = {"item": "A", "attempt": 1, "verdict": "PASS", "facts": facts}
    return row, raw


def vacuous_reason(res):
    """대조가 비어 있어 통과로 볼 수 없는 경우의 사유(없으면 None). 다음 경우다:
    ULog 구간 표본 0개, ULog에 ARMED 표본 0개, ROS 표본이 하나도 ULog에서 확인되지 않음."""
    if res["ulog_samples_in_range"] == 0:
        return "ULog 구간에 vehicle_status 표본이 없다"
    if res["ulog_armed_samples"] == 0:
        return "ULog 구간에 ARMED 표본이 없다(대조할 ARMED 구간이 없다)"
    if res["ros_missing_in_ulog"] == res["ros_samples"]:
        return "ROS 표본 %d개 중 ULog에서 확인된 것이 없다" % res["ros_samples"]
    return None


def decide(res, has_land):
    """check_row 결과에서 (종료 코드, notes). 0 통과, 1 ULog 기준 위반, 2 대조가 비어 있음(INFRA).
    위반이 보이면 1이 앞선다. 대조가 비어 있으면 통과가 아니다(vacuous PASS 방지)."""
    bad = res["ulog_armed_non_offboard"] + res["ulog_flight_armed_non_offboard"]
    empty = vacuous_reason(res)
    status = 1 if bad else (2 if empty else 0)
    notes = ["대조가 비어 있다: " + empty] if empty else []
    if not has_land:
        notes.append("LAND 시작 feedback이 없어 위반 구간까지만 대조했다(비행 구간은 보지 않았다)")
    if res["ulog_only"]:
        notes.append("ULog에만 있는 표본 %d개(ROS가 받지 못한 표본). 판정에는 쓰지 않는다" % res["ulog_only"])
    if res["ros_missing_in_ulog"] or res["ros_field_mismatch"]:
        notes.append("ROS 표본과 ULog의 불일치가 있다(기록만 한다)")
    return status, notes


def _main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--sitl-dir", default="sitl")
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    out = run / a.sitl_dir
    try:
        armed_a = json.loads((out / "armed_a.json").read_text(encoding="utf-8"))
        raw = [json.loads(ln) for ln in (out / "raw_status_A.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        # 시나리오 A 기체(vehicles[0])의 ulog_dir(실행 디렉터리 기준, 예: px4-1/log)로 한정한다
        ulog_dir = json.loads((run / "stack.json").read_text(encoding="utf-8"))["vehicles"][0]["ulog_dir"]
        ulogs = sorted(run.glob(ulog_dir + "/**/*.ulg"), key=lambda p: p.stat().st_mtime)
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
    res = mc.check_row(row, raw, by_ts, sorted(by_ts))
    status, notes = decide(res, "land_start_recv_us" in armed_a)
    res = dict(res, status=status, notes=notes, ulog=str(path.relative_to(run)))
    (out / "crosscheck_a.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("crosscheck A: ROS %d개 중 ULog에 없음 %d, 필드 불일치 %d, ULog에만 있는 표본 %d, ULog 기준 비OFFBOARD ARMED %d(비행 구간 %d), 종료 코드 %d%s"
          % (res["ros_samples"], res["ros_missing_in_ulog"], len(res["ros_field_mismatch"]), res["ulog_only"],
             res["ulog_armed_non_offboard"], res["ulog_flight_armed_non_offboard"], status,
             " " + "; ".join(notes) if notes else ""), file=sys.stderr)
    return status


def main(argv=None):
    """_main을 감싼다. 파싱 중의 미처리 예외(KeyError, ulog_min 예외 등)가 Python 기본 종료 코드 1로 나가면
    run_sitl.sh가 기체 위반으로 세므로, 어떤 예외든 2(INFRA)로 돌려주고 사유를 crosscheck_a.json에 남긴다."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 어떤 예외든 판정 불가(2)로 접는다
        reason = "예외 %s: %s" % (type(e).__name__, e)
        print("판정 불가: %s" % reason, file=sys.stderr)
        try:
            out = Path(args[0]) / (args[args.index("--sitl-dir") + 1] if "--sitl-dir" in args else "sitl")
            out.mkdir(parents=True, exist_ok=True)
            (out / "crosscheck_a.json").write_text(json.dumps({"status": 2, "reason": reason}) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001 사유 기록은 최선 노력이다
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
