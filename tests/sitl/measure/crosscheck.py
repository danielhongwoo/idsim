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

"""측정 기록(measure_*.jsonl, raw_*.jsonl)을 ULog의 vehicle_status와 교차 확인한다.

호스트에서 표준 라이브러리만으로 돈다(rclpy, pyulog 불필요). run_measure.sh가 스택을 멈춘 뒤 부른다
(ULog는 닫힌 뒤에 읽는다. 닫히지 않았으면 마지막 메시지가 잘린 채로 읽는다).

  crosscheck.py --measure-dir <실행 디렉터리>/measure [--repo-root 저장소]

시도마다(armed_window_ros_us가 있는 행)
  - ROS 표본 중 구간 안의 것이 ULog에 같은 timestamp로 있고 arming_state, nav_state, failsafe,
    nav_state_user_intention이 같은가 (ros_missing_in_ulog, ros_field_mismatch)
  - ULog 구간 [arm 전송의 Px4Timestamp, 구간 끝 ROS 표본의 timestamp]의 표본 중 ROS가 못 받은 것
    (ulog_only)과, ULog 기준의 OFFBOARD가 아닌 ARMED 표본 수 (ulog_armed_non_offboard)
  - ULog vehicle_status의 최소 표본 간격(ulog_min_interval_ms). 200 ms 근처이면 ULog가 표본을
    솎아 기록하는 것이라 50 ms 안에 연달아 오는 표본을 못 본다는 뜻이다.
결과: crosscheck_<항목>.json, armed_criterion.json(모든 항목의 합산, ROS와 ULog 둘 다 0이어야 통과).
종료 코드: 0 위반 없음, 1 위반 또는 불일치, 2 입력 부족.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.support import measure_judge as mj  # noqa: E402
from tests.support import ulog_min  # noqa: E402

FIELDS = ("arming_state", "nav_state", "failsafe", "nav_state_user_intention")


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ulog_status(path, cache):
    if path not in cache:
        rows = ulog_min.read_topic(path, "vehicle_status")
        cache[path] = {int(r["timestamp"]): r for r in rows}, [int(r["timestamp"]) for r in rows]
    return cache[path]


def check_row(row, raw_status, ulog_by_ts, ulog_ts):
    """한 시도 행의 교차 확인 결과 dict. armed_window_ros_us가 없으면 None."""
    f = row.get("facts") or {}
    win = f.get("armed_window_ros_us")
    if not win or not f.get("arm_send"):
        return None
    lo_recv, hi_recv = win
    ros = [s for s in raw_status if lo_recv <= s["recv_ros_us"] <= hi_recv]
    lo_ts = f["arm_send"][1]
    hi_ts = max([s["ts_us"] for s in ros], default=lo_ts)
    missing = 0
    mismatch = []
    for s in ros:
        u = ulog_by_ts.get(s["ts_us"])
        if u is None:
            missing += 1
            continue
        for k, rk in (("arming_state", "arming_state"), ("nav_state", "nav_state"),
                      ("failsafe", "failsafe"), ("nav_state_user_intention", "intention")):
            if bool(u[k]) != bool(s[rk]) if k == "failsafe" else int(u[k]) != int(s[rk]):
                mismatch.append({"ts_us": s["ts_us"], "field": k, "ulog": u[k], "ros": s[rk]})
    ros_ts = {s["ts_us"] for s in ros}
    in_range = [t for t in ulog_ts if lo_ts <= t <= hi_ts]
    ulog_only = [t for t in in_range if t not in ros_ts]
    n_armed = 0
    bad = []
    for t in in_range:
        u = ulog_by_ts[t]
        if int(u["arming_state"]) == mj.ARMING_STATE_ARMED:
            n_armed += 1
            if int(u["nav_state"]) != mj.NAV_STATE_OFFBOARD:
                bad.append({"ts_us": t, "nav_state": u["nav_state"], "failsafe": u["failsafe"],
                            "intention": u["nav_state_user_intention"]})
    gaps = [b - a for a, b in zip(in_range, in_range[1:])]
    return {
        "item": row["item"], "attempt": row["attempt"], "ros_samples": len(ros),
        "ros_missing_in_ulog": missing, "ros_field_mismatch": mismatch,
        "ulog_samples_in_range": len(in_range), "ulog_only": len(ulog_only),
        "ulog_armed_samples": n_armed, "ulog_armed_non_offboard": len(bad),
        "ulog_armed_non_offboard_samples": bad,
        "ulog_min_interval_ms": (min(gaps) / 1000.0) if gaps else None,
        "ts_range_us": [lo_ts, hi_ts],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--measure-dir", required=True)
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    args = ap.parse_args(argv)
    mdir = Path(args.measure_dir)
    files = sorted(glob.glob(str(mdir / "measure_*.jsonl")))
    if not files:
        print("measure_*.jsonl이 없다: %s" % mdir, file=sys.stderr)
        return 2
    cache = {}
    all_rows = []
    status = 0
    for mf in files:
        item = os.path.basename(mf)[len("measure_"):-len(".jsonl")]
        rows = load_jsonl(mf)
        raw = load_jsonl(str(mdir / ("raw_%s.jsonl" % item)))
        by_attempt = {}
        for r in raw:
            if r["t"] == "status":
                by_attempt.setdefault(r["attempt"], []).append(r)
        results = []
        for row in rows:
            ulog = row.get("ulog")
            if not ulog:
                results.append({"item": row["item"], "attempt": row["attempt"], "error": "ulog 경로 없음"})
                status = max(status, 2)
                continue
            path = ulog if os.path.isabs(ulog) else os.path.join(args.repo_root, ulog)
            try:
                by_ts, ts_list = ulog_status(path, cache)
            except (OSError, ulog_min.UlogError) as e:
                results.append({"item": row["item"], "attempt": row["attempt"], "error": str(e)})
                status = max(status, 2)
                continue
            res = check_row(row, by_attempt.get(row["attempt"], []), by_ts, ts_list)
            if res is None:
                continue
            results.append(res)
            f = row.get("facts") or {}
            all_rows.append({
                "item": row["item"], "attempt": row["attempt"],
                "armed3_reached": bool(f.get("armed3_reached")),
                "armed_non_offboard": int(f.get("armed_non_offboard", 0)) + res["ulog_armed_non_offboard"],
                "ros_count": int(f.get("armed_non_offboard", 0)),
                "ulog_count": res["ulog_armed_non_offboard"],
            })
            if res["ros_field_mismatch"] or res["ulog_armed_non_offboard"]:
                status = max(status, 1)
        with open(mdir / ("crosscheck_%s.json" % item), "w") as fh:
            json.dump(results, fh, indent=1, sort_keys=True)
            fh.write("\n")
        for r in results:
            if "error" in r:
                print("crosscheck %s 시도 %s: %s" % (r["item"], r["attempt"], r["error"]))
            else:
                print("crosscheck %s 시도 %d: ROS %d개 중 ULog에 없음 %d, 필드 불일치 %d, ULog만 있는 표본 %d, "
                      "ULog 기준 비OFFBOARD ARMED %d, ULog 최소 간격 %s ms" % (
                          r["item"], r["attempt"], r["ros_samples"], r["ros_missing_in_ulog"],
                          len(r["ros_field_mismatch"]), r["ulog_only"], r["ulog_armed_non_offboard"],
                          r["ulog_min_interval_ms"]))
    crit = mj.judge_armed_criterion(all_rows)
    crit["note"] = ("armed_non_offboard 합산은 ROS 기록과 ULog 기록의 합이다. 시나리오 A와 재실측 (3), (5)를 "
                    "합산해도 되고 어느 쪽 실행인지는 PR 본문에 구분해 적는다.")
    crit["by_item"] = {}
    for r in all_rows:
        d = crit["by_item"].setdefault(r["item"], {"rows": 0, "reached": 0, "ros": 0, "ulog": 0})
        d["rows"] += 1
        d["reached"] += 1 if r["armed3_reached"] else 0
        d["ros"] += r["ros_count"]
        d["ulog"] += r["ulog_count"]
    with open(mdir / "armed_criterion.json", "w") as fh:
        json.dump(crit, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("ARMED 기준(합산): %s" % json.dumps({k: v for k, v in crit.items() if k != "note"},
                                              sort_keys=True))
    if crit["violated"]:
        print("!! OFFBOARD가 아닌 ARMED 표본이 나왔다. 즉시 architect에게 올린다.")
        status = max(status, 1)
    elif not crit["enough"]:
        status = max(status, 2)
    return status


if __name__ == "__main__":
    sys.exit(main())
