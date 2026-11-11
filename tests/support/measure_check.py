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

"""측정 기록의 교차 확인과 종료 코드 집계(순수 코드). measure.py와 crosscheck.py가 쓴다.

여기 있는 것: ROS 원시 표본과 ULog vehicle_status의 대조(check_row), ARMED 기준에 넣을 행의 선택과
ROS/ULog 합산(armed_rows, aggregate_armed), 종료 코드 집계(run_status, crosscheck_status).
입출력과 rclpy가 없어 tests/support의 단위 테스트가 SITL 없이 검증한다.

종료 코드: 0 통과, 1 FAIL 또는 위반 또는 불일치, 2 그 밖(입력 부족, 시도 수 부족, 인프라, ERROR).
"""
from tests.support import measure_judge as mj

# ARMED 기준(비OFFBOARD ARMED 표본 0개)에 합산할 항목. 어느 항목을 넣을지는 architect가 정한다
# (보류: 2a 포함 여부, armed 항목 인정). 바꾸기 쉽게 이 상수 하나로 둔다.
ARMED_SUM_ITEMS = ("2a", "3", "5", "armed")

CROSS_FIELDS = (("arming_state", "arming_state"), ("nav_state", "nav_state"),
                ("failsafe", "failsafe"), ("nav_state_user_intention", "intention"))


def armed_rows(rows, items=ARMED_SUM_ITEMS):
    """합산 대상 행만 고른다(2b처럼 ARMED 구간이 없는 행은 넣지 않는다)."""
    return [r for r in rows if r["item"] in items]


def _ulog_equal(key, ulog_val, ros_val):
    if key == "failsafe":
        return bool(ulog_val) == bool(ros_val)
    return int(ulog_val) == int(ros_val)


ARM_LOG_TEXT = "Armed by external command"


def ulog_arm_evidence(arm_ts, end_ts, ulog_by_ts, ulog_ts, logged):
    """ULog 기준 arm 수락 증거. A: arm 전송 Px4Timestamp 뒤의 ARMED 표본, B: logged message
    '[commander] Armed by external command'가 [arm_ts, end_ts] 안. 표본이 없는 것은 미수락의 증거가
    아니다(한 Commander 주기에 arm과 disarm이 처리되면 ARMED 표본이 나오지 않는다)."""
    a = any(arm_ts < t <= end_ts and int(ulog_by_ts[t]["arming_state"]) == mj.ARMING_STATE_ARMED
            for t in ulog_ts)
    b = any(arm_ts <= m["ts"] <= end_ts and ARM_LOG_TEXT in m["msg"] for m in logged)
    return {"A_armed_sample": a, "B_armed_log": b}


def final_verdict(row, evidence):
    """live 판정을 ULog 증거로 확정한다. (5)가 arm 수락 증거 미확인으로 INCONCLUSIVE였던 행만 바뀐다.

    돌려주는 (verdict, pending). pending은 증거가 끝내 없어 INCONCLUSIVE로 남은 경우다."""
    f = row["facts"]
    if row["item"] == "5" and row["verdict"] == "INCONCLUSIVE" and f is not None \
            and f["arm_evidence"] is False:
        if evidence["A_armed_sample"] or evidence["B_armed_log"]:
            return "PASS", False
        return "INCONCLUSIVE", True
    return row["verdict"], False


def check_row(row, raw_status, ulog_by_ts, ulog_ts, logged=()):
    """한 시도 행을 ULog와 대조한다. 대조 구간이 없는 행(ARMED 구간 없음, 측정 안 됨)은 None.

    row: measure_<item>.jsonl의 한 행(facts에 armed_window_ros_us, arm_send 필요. 없으면 KeyError).
    raw_status: 그 시도의 raw status 표본(dict, ts_us/recv_ros_us/...).
    ulog_by_ts: {timestamp: ULog 행}, ulog_ts: 정렬된 timestamp 목록.

    두 구간을 쓴다.
      위반 구간 [arm 전송의 Px4Timestamp, ARMED 구간 끝]: ULog 기준 비OFFBOARD ARMED를 센다.
      대조 구간 [arm 전송의 Px4Timestamp, max(ROS 마지막 표본의 ts, 정리 종료 시각)]: ROS 표본이 ULog에
        있는지, ULog에만 있는 표본(ROS 유실)이 있는지 본다. 정리 종료 시각은 ROS 수신 시각을
        PX4 timestamp 축의 근사로 쓴다(두 축은 같은 sim 시간이고 차이의 분포는 distribution_*.json).
    """
    f = row["facts"]
    if f is None or "armed_window_ros_us" not in f:
        return None
    lo_recv, win_recv = f["armed_window_ros_us"]
    lo_ts = f["arm_send"][1]
    end_recv = f["cleanup_end_ros_us"] if "cleanup_end_ros_us" in f else win_recv
    end_recv = max(end_recv, win_recv)
    ros = [s for s in raw_status if lo_recv <= s["recv_ros_us"] <= end_recv]
    ros_last_ts = max([s["ts_us"] for s in ros], default=lo_ts)
    wide_hi = max(ros_last_ts, end_recv)
    win_hi = max([s["ts_us"] for s in ros if s["recv_ros_us"] <= win_recv], default=lo_ts)
    win_hi = max(win_hi, win_recv)

    missing = 0
    mismatch = []
    for s in ros:
        u = ulog_by_ts.get(s["ts_us"])
        if u is None:
            missing += 1
            continue
        for ukey, rkey in CROSS_FIELDS:
            if not _ulog_equal(ukey, u[ukey], s[rkey]):
                mismatch.append({"ts_us": s["ts_us"], "field": ukey, "ulog": u[ukey], "ros": s[rkey]})
    ros_ts = {s["ts_us"] for s in ros}
    in_range = [t for t in ulog_ts if lo_ts <= t <= wide_hi]
    ulog_only = [t for t in in_range if t not in ros_ts]

    def armed_bad(ts_list):
        n = 0
        bad = []
        for t in ts_list:
            u = ulog_by_ts[t]
            if int(u["arming_state"]) == mj.ARMING_STATE_ARMED:
                n += 1
                if int(u["nav_state"]) != mj.NAV_STATE_OFFBOARD:
                    bad.append({"ts_us": t, "nav_state": u["nav_state"], "failsafe": u["failsafe"],
                                "intention": u["nav_state_user_intention"]})
        return n, bad

    n_armed, bad = armed_bad([t for t in in_range if t <= win_hi])
    _, bad_after = armed_bad([t for t in in_range if t > win_hi])
    gaps = [b - a for a, b in zip(in_range, in_range[1:])]
    evidence = ulog_arm_evidence(lo_ts, wide_hi, ulog_by_ts, ulog_ts, logged)
    verdict, pending = final_verdict(row, evidence)
    return {
        "final_verdict": verdict, "evidence_pending": pending, "arm_evidence_ulog": evidence,
        "item": row["item"], "attempt": row["attempt"], "ros_samples": len(ros),
        "ros_missing_in_ulog": missing, "ros_field_mismatch": mismatch,
        "ulog_samples_in_range": len(in_range), "ulog_only": len(ulog_only),
        "ulog_armed_samples": n_armed, "ulog_armed_non_offboard": len(bad),
        "ulog_armed_non_offboard_samples": bad,
        "ulog_armed_non_offboard_after_window": len(bad_after),
        "ulog_min_interval_ms": (min(gaps) / 1000.0) if gaps else None,
        "ts_range_us": [lo_ts, wide_hi], "violation_range_us": [lo_ts, win_hi],
    }


def row_status(res):
    """check_row 결과 하나의 종료 코드. error가 있으면 2(ULog를 못 읽음), 대조 이상은 1."""
    if "error" in res:
        return 2
    if res.get("evidence_pending"):
        return 2
    if (res["ros_missing_in_ulog"] > 0 or res["ulog_samples_in_range"] == 0
            or res["ros_field_mismatch"] or res["ulog_armed_non_offboard"] > 0
            or res["ulog_only"] > 0):
        return 1
    return 0


def aggregate_armed(entries, min_reached=10):
    """ROS와 ULog를 합산한 ARMED 기준.

    entries: [{"item", "class", "attempt", "armed3_reached", "ros_count", "ulog_count",
    "ulog_samples"}]. class는 judge의 CLASS_DIRECT/CLASS_EXECUTOR다.
    ulog_count가 None이면 ULog를 못 읽은 행이다(ROS 쪽 위반 수만 합산하고 unreadable로 센다).
    전체 ULog 표본 합이 0이면 대조가 비어 있었다는 뜻이라 passed를 false로 한다.
    """
    rows = []
    unreadable = 0
    ulog_total = 0
    for e in entries:
        if e["ulog_count"] is None:
            unreadable += 1
            n = e["ros_count"]
        else:
            n = e["ros_count"] + e["ulog_count"]
            ulog_total += e["ulog_samples"]
        rows.append({"item": e["item"], "class": e["class"], "armed3_reached": e["armed3_reached"],
                     "armed_non_offboard": n})
    crit = mj.judge_armed_criterion(rows, min_reached)
    crit["ulog_total_samples"] = ulog_total
    crit["n_ulog_unreadable"] = unreadable
    if ulog_total == 0:
        crit["passed"] = False
        for c in crit["classes"].values():
            c["passed"] = False
    by_item = {}
    for e, r in zip(entries, rows):
        d = by_item.setdefault(e["item"], {"rows": 0, "reached": 0, "ros": 0, "ulog": 0})
        d["rows"] += 1
        d["reached"] += 1 if e["armed3_reached"] else 0
        d["ros"] += e["ros_count"]
        d["ulog"] += 0 if e["ulog_count"] is None else e["ulog_count"]
    crit["by_item"] = by_item
    return crit


def crosscheck_status(results, crit):
    """crosscheck 전체의 종료 코드."""
    status = 0
    for r in results:
        status = max(status, row_status(r))
    if crit["violated"]:
        status = max(status, 1)
    if crit["ulog_total_samples"] == 0:
        status = max(status, 1)
    elif not crit["enough"]:
        status = max(status, 2)
    if not results:
        status = max(status, 2)
    return status


def run_status(rows, min_attempts, meta_ok=True, crit=None):
    """measure.py 한 실행의 종료 코드.

    rows: 모든 행(item, verdict 키). min_attempts: 항목의 최소 시도 수.
    행이 0개, ERROR/PRECONDITION 등 PASS와 FAIL이 아닌 행, 시도 수 부족, 메타 부족(commit
    unknown, image key null)은 2. FAIL이나 ARMED 위반이 하나라도 있으면 1이 2보다 앞선다.
    """
    if not rows:
        return 2
    status = 0 if meta_ok else 2
    fail = False
    for sub in sorted({r["item"] for r in rows}):
        rs = [r for r in rows if r["item"] == sub]
        n_pass = sum(1 for r in rs if r["verdict"] == "PASS")
        n_fail = sum(1 for r in rs if r["verdict"] == "FAIL")
        if n_fail:
            fail = True
        elif len(rs) < min_attempts or n_pass != len(rs):
            status = max(status, 2)
    if crit is not None and crit["violated"]:
        fail = True
    return 1 if fail else status
