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
"""measure_judge 단위 테스트. 합성 표본만 쓰고 SITL과 rclpy가 필요 없다."""
import pytest

from tests.support import measure_judge as mj


def st(ts, recv, arming=mj.ARMING_STATE_ARMED, nav=mj.NAV_STATE_OFFBOARD, clock=None,
       failsafe=False, intention=mj.NAV_STATE_OFFBOARD):
    return mj.StatusSample(ts, recv, recv if clock is None else clock, arming, nav, failsafe,
                           intention)


# --- ConsecutiveConfirm ---------------------------------------------------


def test_confirm_three_distinct_timestamps():
    c = mj.ConsecutiveConfirm(mj.is_armed)
    assert not c.feed(st(1, 1))
    assert not c.feed(st(2, 2))
    assert c.feed(st(3, 3))
    assert c.confirmed_at.ts_us == 3


def test_confirm_same_timestamp_is_skipped_not_reset():
    c = mj.ConsecutiveConfirm(mj.is_armed)
    c.feed(st(1, 1))
    c.feed(st(1, 2))      # 같은 표본을 다시 봄: 더하지도 되돌리지도 않는다
    assert c.count == 1
    c.feed(st(2, 3))
    assert c.feed(st(3, 4))


def test_confirm_non_matching_resets():
    c = mj.ConsecutiveConfirm(mj.is_armed)
    c.feed(st(1, 1))
    c.feed(st(2, 2))
    c.feed(st(3, 3, arming=mj.ARMING_STATE_DISARMED))
    assert c.count == 0
    c.feed(st(4, 4))
    c.feed(st(5, 5))
    assert c.feed(st(6, 6))


def test_confirm_decreasing_timestamp_not_counted():
    c = mj.ConsecutiveConfirm(mj.is_armed)
    c.feed(st(10, 1))
    c.feed(st(5, 2))
    assert c.count == 1


def test_confirm_floor_requires_strictly_later_ts_and_recv():
    c = mj.ConsecutiveConfirm(mj.is_armed, min_ts_us=100, min_recv_us=50)
    c.feed(st(100, 60))     # ts가 같다: 세지 않음
    c.feed(st(101, 50))     # 수신이 같다: 세지 않음
    assert c.count == 0
    c.feed(st(101, 51))
    c.feed(st(102, 52))
    assert c.feed(st(103, 53))


def test_confirm_floor_set_once():
    c = mj.ConsecutiveConfirm(mj.is_armed)
    c.set_floor(100, 100)
    c.set_floor(1, 1)
    c.feed(st(50, 150))
    assert c.count == 0


def test_armed_confirm_sample_after():
    samples = [st(1, 1), st(2, 2), st(3, 3), st(4, 4), st(5, 5)]
    assert mj.armed_confirm_sample(samples, 0).ts_us == 3
    assert mj.armed_confirm_sample(samples, 2).ts_us == 5
    assert mj.armed_confirm_sample(samples, 3) is None


# --- OFFBOARD가 아닌 ARMED ------------------------------------------------


def test_armed_non_offboard_counts_only_armed_outside_offboard():
    samples = [
        st(1, 1, arming=mj.ARMING_STATE_DISARMED, nav=mj.NAV_STATE_AUTO_LOITER),
        st(2, 2, nav=mj.NAV_STATE_OFFBOARD),
        st(3, 3, nav=mj.NAV_STATE_AUTO_LOITER),
        st(4, 4, nav=mj.NAV_STATE_AUTO_LAND),
    ]
    n, bad = mj.armed_non_offboard(samples, 0, None)
    assert n == 3 and [b.ts_us for b in bad] == [3, 4]


def test_armed_non_offboard_window_bounds_are_inclusive():
    samples = [st(1, 10, nav=0), st(2, 20, nav=0), st(3, 30, nav=0)]
    n, bad = mj.armed_non_offboard(samples, 20, 30)
    assert n == 2 and len(bad) == 2
    n, bad = mj.armed_non_offboard(samples, 11, 29)
    assert n == 1


def test_armed_non_offboard_window_by_px4_timestamp():
    samples = [st(100, 1, nav=0), st(200, 2, nav=0)]
    n, _ = mj.armed_non_offboard(samples, 150, None, time_of="ts")
    assert n == 1


def test_armed_non_offboard_zero_is_empty_pass_flag():
    # 표본이 없어도 0개다. 빈 채 통과하지 않게 판정은 judge_armed_criterion이 ARMED 3회 도달 수를 본다.
    assert mj.armed_non_offboard([], 0, None) == (0, [])


# --- 실행 요약 ------------------------------------------------------------


def row(reached=False, bad=0, cls=mj.CLASS_DIRECT):
    return {"armed3_reached": reached, "armed_non_offboard": bad, "class": cls}


def test_armed_criterion_needs_ten_reached_and_zero_violations():
    rows = [row(reached=True)] * 10 + [row(reached=False)] * 5
    r = mj.judge_armed_criterion(rows)
    assert r["passed"] and r["n_reached"] == 10 and not r["violated"]


def test_armed_criterion_nine_reached_is_empty_pass_not_allowed():
    rows = [row(reached=True)] * 9 + [row(reached=False)] * 20
    r = mj.judge_armed_criterion(rows)
    assert not r["passed"] and not r["enough"] and not r["violated"]


def test_armed_criterion_single_violation_fails_even_when_not_reached():
    rows = [row(reached=True)] * 12 + [row(reached=False, bad=1)]
    r = mj.judge_armed_criterion(rows)
    assert r["violated"] and not r["passed"] and r["violation_total"] == 1


def test_armed_criterion_is_judged_per_class():
    rows = ([row(reached=True)] * 10
            + [row(reached=True, cls=mj.CLASS_EXECUTOR)] * 4)
    r = mj.judge_armed_criterion(rows)
    assert r["passed"]                                       # 최상위는 PX4 직접 부류
    assert r["classes"][mj.CLASS_DIRECT]["n_reached"] == 10
    ex = r["classes"][mj.CLASS_EXECUTOR]
    assert ex["n_reached"] == 4 and not ex["enough"] and not ex["passed"]
    rows = [row(reached=True)] * 10 + [row(reached=True, cls=mj.CLASS_EXECUTOR, bad=1)] * 10
    r = mj.judge_armed_criterion(rows)
    assert r["passed"] and not r["classes"][mj.CLASS_EXECUTOR]["passed"] and r["violated_any_class"]


def test_armed_criterion_without_direct_rows_still_has_direct_class_entry():
    r = mj.judge_armed_criterion([row(reached=True, cls=mj.CLASS_EXECUTOR)] * 10)
    assert r["n_reached"] == 0 and not r["passed"]
    assert r["classes"][mj.CLASS_EXECUTOR]["passed"]


def test_judge_armed_criterion_missing_key_raises():
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed3_reached": True, "class": "px4_direct"}])
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed_non_offboard": 0, "class": "px4_direct"}])


def test_judge_armed_criterion_missing_class_raises():
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed3_reached": True, "armed_non_offboard": 0}])


def test_armed_criterion_unmeasured_rows_are_not_read_as_zero():
    rows = [row(reached=True)] * 10 + [row(reached=None, bad=None)]
    r = mj.judge_armed_criterion(rows)
    assert r["n_unmeasured"] == 1 and r["n_measured"] == 10 and r["passed"]
