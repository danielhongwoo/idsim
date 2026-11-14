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

"""measure_check 단위 테스트(ROS 표본과 ULog의 대조). 합성 표본만 쓴다."""
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


def test_all_present_passes():
    u = [ul(1100), ul(1600), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert res["ulog_samples_in_range"] == 3 and res["ros_missing_in_ulog"] == 0


def test_partial_missing_in_ulog_is_failure():
    u = [ul(1100), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert res["ros_missing_in_ulog"] == 1


def test_field_mismatch_is_failure():
    u = [ul(1100), ul(1600, nav=LOI), ul(2100)]
    res = mc.check_row(row(), [ros(1100), ros(1600), ros(2100)], *index(u))
    assert {m["field"] for m in res["ros_field_mismatch"]} == {"nav_state", "nav_state_user_intention"}


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


def test_ulog_only_sample_alone_is_minimum_status_one():
    u = [ul(1100), ul(1550), ul(1600)]
    res = mc.check_row(row(), [ros(1100), ros(1600)], *index(u))
    assert res["ulog_only"] == 1 and res["ulog_armed_non_offboard"] == 0


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


def test_flight_window_nav_land_violation_from_ulog_is_counted():
    f = {"armed_window_ros_us": [1000, 2000], "arm_send": [1000, 1000], "land_send": [5000, 5000]}
    r = {"item": "armed", "attempt": 1, "verdict": "PASS", "facts": f}
    u = [ul(1100), ul(1600), ul(2100), ul(3000, nav=LOI), ul(4900, nav=LOI)]
    samples = [ros(t, nav=n) for t, n in ((1100, OFF), (1600, OFF), (2100, OFF), (3000, LOI), (4900, LOI))]
    res = mc.check_row(r, samples, *index(u))
    assert res["ulog_flight_armed_non_offboard"] == 2 and res["ulog_armed_non_offboard"] == 0
    # land_send가 없으면(3, 5, 2a) 구간 뒤 ARMED는 위반이 아니다
    f2 = {"armed_window_ros_us": [1000, 2000], "arm_send": [1000, 1000], "cleanup_end_ros_us": 5000}
    res2 = mc.check_row({"item": "3", "attempt": 1, "verdict": "PASS", "facts": f2}, samples, *index(u))
    assert res2["ulog_flight_armed_non_offboard"] == 0 and res2["ulog_armed_non_offboard_after_window"] == 2
