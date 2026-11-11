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

"""measure_check 단위 테스트(ULog 대조, ARMED 합산, 종료 코드). 합성 표본만 쓴다."""
import pytest

from tests.support import measure_check as mc
from tests.support import measure_judge as mj

ARMED = mj.ARMING_STATE_ARMED
DIS = mj.ARMING_STATE_DISARMED
OFF = mj.NAV_STATE_OFFBOARD
LOI = mj.NAV_STATE_AUTO_LOITER


def ros(ts, recv=None, arming=ARMED, nav=OFF):
    return {"ts_us": ts, "recv_ros_us": ts if recv is None else recv, "arming_state": arming,
            "nav_state": nav, "failsafe": False, "intention": nav}


def ul(ts, arming=ARMED, nav=OFF, failsafe=False):
    return {"timestamp": ts, "arming_state": arming, "nav_state": nav, "failsafe": failsafe,
            "nav_state_user_intention": nav}


def index(rows):
    by = {r["timestamp"]: r for r in rows}
    return by, sorted(by)


def row(window=(1000, 3000), end=None, arm_ts=1000, item="5"):
    f = {"armed_window_ros_us": list(window), "arm_send": [window[0], arm_ts]}
    if end is not None:
        f["cleanup_end_ros_us"] = end
    return {"item": item, "attempt": 1, "verdict": "PASS", "facts": f}


def test_empty_ulog_is_a_failure_not_a_pass():
    samples = [ros(1100), ros(1600), ros(2100)]
    res = mc.check_row(row(), samples, *index([]))
    assert res["ulog_samples_in_range"] == 0 and res["ros_missing_in_ulog"] == 3
    assert mc.row_status(res) == 1


def test_all_present_passes():
    u = [ul(1100), ul(1600), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert mc.row_status(res) == 0
    assert res["ulog_samples_in_range"] == 3 and res["ros_missing_in_ulog"] == 0


def test_partial_missing_in_ulog_is_failure():
    u = [ul(1100), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert res["ros_missing_in_ulog"] == 1 and mc.row_status(res) == 1


def test_field_mismatch_is_failure():
    u = [ul(1100), ul(1600, nav=LOI), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert {m["field"] for m in res["ros_field_mismatch"]} == {"nav_state", "nav_state_user_intention"}
    assert mc.row_status(res) == 1


def test_failsafe_mismatch_compares_as_bool():
    u = [ul(1100, failsafe=1)]
    res = mc.check_row(row(), [ros(1100)], *index(u))
    assert [m["field"] for m in res["ros_field_mismatch"]] == ["failsafe"]


def test_violation_only_in_ulog_is_caught():
    # ROS는 3개 모두 OFFBOARD로 봤지만 ULog에는 ROS가 못 받은 비OFFBOARD ARMED 표본이 있다
    u = [ul(1100), ul(1550, nav=LOI), ul(1600), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert res["ulog_only"] == 1
    assert res["ulog_armed_non_offboard"] == 1
    assert mc.row_status(res) == 1


def test_ulog_only_sample_alone_is_minimum_status_one():
    u = [ul(1100), ul(1550), ul(1600)]
    res = mc.check_row(row(), [ros(1100), ros(1600)], *index(u))
    assert res["ulog_only"] == 1 and res["ulog_armed_non_offboard"] == 0
    assert mc.row_status(res) == 1


def test_range_is_widened_to_cleanup_end_to_catch_dropped_ros_samples():
    # 구간 끝 이후(정리 종료 3000까지)에 ROS가 못 받은 ULog 표본이 있으면 잡는다
    u = [ul(1100), ul(1600), ul(2700)]
    narrow = mc.check_row(row(window=(1000, 1600)), [ros(1100), ros(1600)], *index(u))
    wide = mc.check_row(row(window=(1000, 1600), end=3000), [ros(1100), ros(1600)], *index(u))
    assert narrow["ulog_only"] == 0
    assert wide["ulog_only"] == 1


def test_violation_after_window_is_recorded_separately_not_as_violation():
    # ARMED 구간 뒤(Hold 이후)의 AUTO_LOITER ARMED는 위반 구간 밖이다
    u = [ul(1100), ul(1600), ul(2700, nav=LOI)]
    res = mc.check_row(row(window=(1000, 1600), end=3000), [ros(1100), ros(1600)], *index(u))
    assert res["ulog_armed_non_offboard"] == 0
    assert res["ulog_armed_non_offboard_after_window"] == 1


def test_row_without_window_is_skipped_and_missing_key_raises():
    assert mc.check_row({"item": "2b", "attempt": 1, "facts": {"x": 1}}, [], *index([])) is None
    assert mc.check_row({"item": "5", "attempt": 1, "facts": None}, [], *index([])) is None
    with pytest.raises(KeyError):
        mc.check_row({"item": "5", "attempt": 1}, [], *index([]))
    with pytest.raises(KeyError):
        mc.check_row({"item": "5", "attempt": 1, "facts": {"armed_window_ros_us": [1, 2]}}, [],
                     *index([]))


def test_row_status_error_is_two():
    assert mc.row_status({"item": "5", "attempt": 1, "error": "ulog를 못 읽음"}) == 2


# --- 합산 -----------------------------------------------------------------


def entry(item="3", reached=True, ros=0, ulog=0, samples=5, cls=mj.CLASS_DIRECT):
    return {"item": item, "class": cls, "attempt": 1, "armed3_reached": reached, "ros_count": ros,
            "ulog_count": ulog, "ulog_samples": samples}


def test_aggregate_passes_with_ten_reached_and_nonempty_ulog():
    c = mc.aggregate_armed([entry() for _ in range(10)])
    assert c["passed"] and c["ulog_total_samples"] == 50 and not c["violated"]


def test_aggregate_all_ulog_empty_is_not_passed():
    c = mc.aggregate_armed([entry(samples=0) for _ in range(12)])
    assert not c["passed"] and c["ulog_total_samples"] == 0


def test_aggregate_unreadable_ulog_still_adds_ros_violations():
    c = mc.aggregate_armed([entry() for _ in range(10)] + [entry(ros=2, ulog=None)])
    assert c["violated"] and c["violation_total"] == 2 and c["n_ulog_unreadable"] == 1


def test_aggregate_sums_ros_and_ulog_counts():
    c = mc.aggregate_armed([entry(ros=1, ulog=2)] + [entry() for _ in range(10)])
    assert c["violation_total"] == 3 and not c["passed"]
    assert c["by_item"]["3"]["ros"] == 1 and c["by_item"]["3"]["ulog"] == 2


def test_armed_rows_excludes_2b_so_n_rows_is_not_inflated():
    rows = [{"item": "2a"}, {"item": "2b"}, {"item": "3"}, {"item": "5"}, {"item": "armed"}]
    assert [r["item"] for r in mc.armed_rows(rows)] == ["2a", "3", "5", "armed"]
    assert [r["item"] for r in mc.armed_rows(rows, items=("3",))] == ["3"]


# --- 종료 코드 ------------------------------------------------------------


def r(item, verdict):
    return {"item": item, "verdict": verdict}


def test_run_status_zero_rows_is_two():
    assert mc.run_status([], 3) == 2


def test_run_status_all_pass_enough_is_zero():
    assert mc.run_status([r("3", "PASS")] * 3, 3) == 0


def test_run_status_not_enough_is_two():
    assert mc.run_status([r("3", "PASS")] * 2, 3) == 2


def test_run_status_other_verdicts_are_two_and_fail_wins():
    assert mc.run_status([r("3", "PASS")] * 2 + [r("3", "ERROR")], 3) == 2
    assert mc.run_status([r("3", "PASS")] * 2 + [r("3", "WINDOW_MISSED")], 3) == 2
    assert mc.run_status([r("3", "FAIL"), r("3", "ERROR")], 3) == 1


def test_run_status_arm_violation_is_one_even_if_all_pass():
    crit = {"violated": True}
    assert mc.run_status([r("3", "PASS")] * 3, 3, crit=crit) == 1


def test_run_status_meta_missing_is_two():
    assert mc.run_status([r("3", "PASS")] * 3, 3, meta_ok=False) == 2


def test_crosscheck_status_aggregation():
    ok = {"item": "5", "attempt": 1, "ros_missing_in_ulog": 0, "ulog_samples_in_range": 3,
          "ros_field_mismatch": [], "ulog_armed_non_offboard": 0, "ulog_only": 0}
    good = {"violated": False, "ulog_total_samples": 3, "enough": True}
    assert mc.crosscheck_status([ok], good) == 0
    assert mc.crosscheck_status([ok], dict(good, enough=False)) == 2
    assert mc.crosscheck_status([ok], dict(good, ulog_total_samples=0)) == 1
    assert mc.crosscheck_status([ok], dict(good, violated=True)) == 1
    assert mc.crosscheck_status([dict(ok, ulog_samples_in_range=0)], good) == 1
    assert mc.crosscheck_status([{"item": "5", "attempt": 1, "error": "x"}], good) == 2
    assert mc.crosscheck_status([], good) == 2


# --- (5) arm 수락 증거: ULog에서 확정 ----------------------------------------


def row5(verdict="INCONCLUSIVE", evidence=False):
    r = row(item="5")
    r["verdict"] = verdict
    r["facts"]["arm_evidence"] = evidence
    return r


def logged(ts, text="[commander] Armed by external command\t"):
    return {"level": 6, "ts": ts, "msg": text}


def test_ulog_evidence_a_armed_sample_after_arm_ts():
    u = [ul(1100)]
    res = mc.check_row(row5(), [ros(1100)], *index(u))
    assert res["arm_evidence_ulog"]["A_armed_sample"] and res["final_verdict"] == "PASS"
    assert mc.row_status(res) == 0


def test_ulog_evidence_a_requires_ts_strictly_after_arm_send():
    u = [ul(1000, arming=DIS), ul(1000)]
    ev = mc.ulog_arm_evidence(1000, 3000, *index([ul(1000)]), [])
    assert not ev["A_armed_sample"]
    assert u


def test_ulog_evidence_b_armed_log_without_armed_sample():
    u = [ul(1100, arming=DIS)]
    res = mc.check_row(row5(), [ros(1100, arming=DIS)], *index(u), logged=[logged(1050)])
    assert not res["arm_evidence_ulog"]["A_armed_sample"]
    assert res["arm_evidence_ulog"]["B_armed_log"] and res["final_verdict"] == "PASS"


def test_ulog_evidence_b_log_outside_range_does_not_count():
    u = [ul(1100, arming=DIS)]
    res = mc.check_row(row5(), [ros(1100, arming=DIS)], *index(u),
                       logged=[logged(900), logged(9000), logged(1500, "[commander] Disarmed")])
    assert res["final_verdict"] == "INCONCLUSIVE" and res["evidence_pending"]
    assert mc.row_status(res) == 2


def test_ack_only_is_not_evidence_inconclusive_stays():
    # arm_evidence False(ROS 표본 없음), ULog에도 A, B 없음 -> 확정하지 않는다
    u = [ul(1100, arming=DIS)]
    res = mc.check_row(row5(), [ros(1100, arming=DIS)], *index(u))
    assert res["final_verdict"] == "INCONCLUSIVE"


def test_final_verdict_does_not_touch_other_rows():
    assert mc.final_verdict(row5(verdict="PASS", evidence=True),
                            {"A_armed_sample": False, "B_armed_log": False}) == ("PASS", False)
    assert mc.final_verdict(row5(verdict="FAIL"), {"A_armed_sample": True,
                                                  "B_armed_log": True}) == ("FAIL", False)
    r = row(item="3")
    assert mc.final_verdict(r, {"A_armed_sample": False, "B_armed_log": False}) == ("PASS", False)
