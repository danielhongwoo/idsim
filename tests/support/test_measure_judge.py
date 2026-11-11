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

US = mj.US


def st(ts, recv, arming=mj.ARMING_STATE_ARMED, nav=mj.NAV_STATE_OFFBOARD, clock=None,
       failsafe=False, intention=mj.NAV_STATE_OFFBOARD):
    return mj.StatusSample(ts, recv, recv if clock is None else clock, arming, nav, failsafe,
                           intention)


def ld(recv, landed):
    return mj.LandedSample(recv, recv, landed)


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


# --- landed 전환과 분기 ---------------------------------------------------


def test_landed_transitions_initial_not_counted():
    ls = [ld(0, True), ld(1 * US, True), ld(2 * US, False), ld(5 * US, True), ld(6 * US, True)]
    r = mj.landed_transitions(ls, 0, None)
    assert r["initial"] is True and r["count"] == 2
    assert r["times_us"] == [2 * US, 5 * US]
    assert r["intervals_s"] == [3.0]


def test_landed_transitions_window():
    ls = [ld(0, True), ld(1 * US, False), ld(3 * US, True)]
    r = mj.landed_transitions(ls, 2 * US, 4 * US)
    assert r["initial"] is False
    assert r["count"] == 1
    r = mj.landed_transitions(ls, 10 * US, None)
    assert r["initial"] is True and r["count"] == 0     # 구간에 표본이 없으면 마지막 상태를 이어 받는다
    assert mj.landed_transitions([], 0, None)["initial"] is None


def test_branch_sequence_collapses_repeats():
    log = [(1, "G"), (2, "G"), (3, "A"), (4, "G")]
    assert mj.branch_sequence(log) == {"sequence": "GAG", "transitions": 2}
    assert mj.branch_sequence([]) == {"sequence": "", "transitions": 0}


# --- CleanupModel ---------------------------------------------------------


def run_model(m, events, end_us):
    """events: {recv_us: ('status', StatusSample) 또는 ('landed', bool)}. 10 ms 간격으로 step한다."""
    landed = True
    sent = []
    t = m.start_us
    while t <= end_us and not m.done:
        ev = events.get(t)
        for e in ([] if ev is None else ev):
            if e[0] == "landed":
                landed = e[1]
            else:
                m.on_status(e[1])
        for kind in m.step(t, landed):
            sent.append((t, kind))
            m.note_sent(kind, t, t)
        t += 10_000
    return sent


def test_cleanup_ground_disarmed_three_confirms():
    m = mj.CleanupModel(0)
    events = {
        100_000: [("status", st(150_000, 100_000, arming=mj.ARMING_STATE_DISARMED))],
        600_000: [("status", st(650_000, 600_000, arming=mj.ARMING_STATE_DISARMED))],
        1_100_000: [("status", st(1_150_000, 1_100_000, arming=mj.ARMING_STATE_DISARMED))],
    }
    sent = run_model(m, events, 5 * US)
    assert m.end_reason == "DISARMED"
    assert m.end_us == 1_100_000
    assert [k for _, k in sent][0] == "disarm"
    assert [t for t, _ in sent] == [0, 500_000, 1_000_000]   # 0.5 s 간격 재전송
    assert mj.judge_cleanup_time(m.elapsed_s)


def test_cleanup_disarmed_before_send_floor_not_counted():
    m = mj.CleanupModel(1 * US)
    # 전송 전에 받은 DISARMED는 세지 않는다. 첫 전송 tick은 start_us다.
    m.on_status(st(10, 0, arming=mj.ARMING_STATE_DISARMED))
    m.step(1 * US, True)
    m.note_sent("disarm", 1 * US, 1_000_050)
    m.on_status(st(1_000_050, 1_000_100, arming=mj.ARMING_STATE_DISARMED))   # ts가 전송 값과 같다
    m.on_status(st(1_000_060, 1_000_100, arming=mj.ARMING_STATE_DISARMED))
    assert m._confirm["disarm"].count == 1


def test_cleanup_ground_timeout_when_never_confirmed():
    m = mj.CleanupModel(0)
    sent = run_model(m, {}, 20 * US)
    assert m.end_reason == "TIMEOUT_GROUND"
    assert m.end_us == 3 * US
    assert len(sent) == 6        # 0, 0.5, ... 2.5
    assert not mj.judge_cleanup_time(None)


def test_cleanup_air_branch_sends_hold_and_ends_on_first_loiter():
    m = mj.CleanupModel(0)
    events = {
        0: [("landed", False)],
        700_000: [("status", st(700_100, 700_000, nav=mj.NAV_STATE_AUTO_LOITER))],
    }
    sent = run_model(m, events, 5 * US)
    assert m.end_reason == "HOLD"
    assert {k for _, k in sent} == {"hold"}
    assert m.end_us == 700_000
    assert mj.branch_sequence(m.branch_log)["sequence"] == "A"


def test_cleanup_branch_flip_resets_branch_timer_and_logs_order():
    m = mj.CleanupModel(0)
    events = {
        0: [("landed", True)],
        2 * US: [("landed", False)],       # 지상 분기 2 s -> 공중 분기
        4 * US: [("landed", True)],        # 공중 분기 2 s -> 지상 분기
    }
    run_model(m, events, 10 * US)
    assert [b for _, b in m.branch_log] == ["G", "A", "G", ]
    # 지상 분기는 들어갈 때마다 타이머를 새로 잡으므로 4 s + 3 s = 7 s에 끝난다
    assert m.end_reason == "TIMEOUT_GROUND"
    assert m.end_us == 7 * US
    assert mj.branch_sequence(m.branch_log)["transitions"] == 2
    assert mj.judge_cleanup_time(m.elapsed_s)


def test_cleanup_hard_limit_beats_branch_timer():
    m = mj.CleanupModel(0, mode_confirm_s=100.0, hold_confirm_s=100.0)
    run_model(m, {}, 20 * US)
    assert m.end_reason == "LIMIT"
    assert m.end_us == 12 * US
    assert not mj.judge_cleanup_time(m.elapsed_s)


def test_cleanup_expiry_beats_confirm_in_same_step():
    m = mj.CleanupModel(0)
    m.step(0, True)
    m.note_sent("disarm", 0, 1)
    for i, t in enumerate((1000, 2000, 3000)):
        m.on_status(st(10 + i, t, arming=mj.ARMING_STATE_DISARMED))
    m.step(3 * US, True)           # 확인이 이미 찼지만 이 step은 분기 만료 시각이다
    assert m.end_reason == "TIMEOUT_GROUND"


def test_cleanup_disarmed_in_air_ends_with_air_reason():
    m = mj.CleanupModel(0)
    m.step(0, False)
    m.note_sent("hold", 0, 1)
    m.on_status(st(5, 10, arming=mj.ARMING_STATE_DISARMED))
    m.step(20, False)
    assert m.end_reason == "DISARMED_AIR"


# --- 분포 -----------------------------------------------------------------


def test_signed_distribution_keeps_sign_mix():
    d = mj.signed_distribution([-3, -1, 0, 2, 4])
    assert d["n"] == 5 and d["min"] == -3 and d["max"] == 4
    assert (d["n_negative"], d["n_zero"], d["n_positive"]) == (2, 1, 2)
    assert d["p50"] == 0


def test_signed_distribution_empty():
    d = mj.signed_distribution([])
    assert d["n"] == 0 and d["min"] is None and d["p50"] is None


def test_status_offsets_uses_both_references():
    s = [st(1000, 900, clock=1100), st(2000, 2100, clock=2000)]
    o = mj.status_offsets(s)
    assert o["ts_minus_recv_ros_us"]["n_negative"] == 1
    assert o["ts_minus_recv_ros_us"]["n_positive"] == 1
    assert o["ts_minus_clock_us"]["n_negative"] == 1
    assert o["ts_minus_clock_us"]["n_zero"] == 1


def test_deltas_vs_sends_first_sample_after_send_and_unmatched():
    samples = [st(1100, 1000), st(1600, 1500)]
    r = mj.deltas_vs_sends(samples, [(900, 880), (1000, 990), (1500, 1480), (9000, 8990)])
    # 900 뒤 첫 표본은 recv 1000(ts 1100), 1000 뒤는 recv 1500(ts 1600), 1500 뒤는 없음
    assert r["values_us"] == [1100 - 880, 1600 - 990]
    assert r["unmatched"] == 2


# --- 시도 판정 ------------------------------------------------------------


def good3():
    return {"landed_at_cancel": True, "armed_non_offboard": 0, "end_reason": "DISARMED", "climb_m": 0.05,
            "cleanup_total_s": 1.2, "armed_after_end": False, "final_disarmed": True}


def test_judge_attempt_3_pass_and_each_fail_reason():
    assert mj.judge_attempt("3", good3()).ok
    for key, val in [("armed_non_offboard", 1), ("end_reason", "TIMEOUT_GROUND"),
                     ("climb_m", 0.21), ("cleanup_total_s", 9.0), ("armed_after_end", True),
                     ("final_disarmed", False)]:
        f = good3()
        f[key] = val
        v = mj.judge_attempt("3", f)
        assert not v.ok and v.verdict == "FAIL" and v.reasons, key


def test_judge_attempt_3_window_missed_is_not_pass_and_not_fail():
    f = good3()
    f["landed_at_cancel"] = False
    v = mj.judge_attempt("3", f)
    assert not v.ok and v.verdict == "WINDOW_MISSED"


def test_judge_attempt_climb_boundary_is_inclusive_and_time_boundary_exclusive():
    f = good3()
    f["climb_m"] = 0.2
    assert mj.judge_attempt("5", f).ok
    f["cleanup_total_s"] = 8.999
    assert mj.judge_attempt("5", f).ok
    f["cleanup_total_s"] = 9.0
    assert not mj.judge_attempt("5", f).ok


def test_judge_attempt_missing_fact_raises_instead_of_passing():
    f = good3()
    del f["climb_m"]
    with pytest.raises(KeyError):
        mj.judge_attempt("3", f)


def test_judge_attempt_2a_and_2b():
    f = {"end_reason": "HOLD", "cleanup_total_s": 0.8, "armed_non_offboard": 0}
    assert mj.judge_attempt("2a", f).ok
    f["armed_non_offboard"] = 3        # (2a)는 기록만 하고 판정하지 않는다
    assert mj.judge_attempt("2a", f).ok
    f["end_reason"] = "TIMEOUT_HOLD"
    assert not mj.judge_attempt("2a", f).ok
    g = {"landed_true_seen": True, "disarm_confirmed": True, "dz_max_m": 0.1}
    assert mj.judge_attempt("2b", g).ok
    g["landed_true_seen"] = False
    assert not mj.judge_attempt("2b", g).ok
    g = {"landed_true_seen": True, "disarm_confirmed": True, "dz_max_m": 0.3}
    assert not mj.judge_attempt("2b", g).ok


def test_judge_attempt_armed():
    assert mj.judge_attempt("armed", {"armed_non_offboard": 0, "armed3_reached": True}).ok
    assert not mj.judge_attempt("armed", {"armed_non_offboard": 0, "armed3_reached": False}).ok
    assert not mj.judge_attempt("armed", {"armed_non_offboard": 2, "armed3_reached": True}).ok


def test_judge_attempt_unknown_item():
    with pytest.raises(ValueError):
        mj.judge_attempt("9", {})


# --- 실행 요약 ------------------------------------------------------------


def row(verdict="PASS", reached=False, bad=0):
    return {"verdict": verdict, "armed3_reached": reached, "armed_non_offboard": bad}


def test_judge_run_counts_failed_and_other_attempts():
    rows = [row("PASS")] * 8 + [row("FAIL"), row("PRECONDITION")]
    r = mj.judge_run(rows, 10)
    assert r["n"] == 10 and r["n_pass"] == 8 and r["n_fail"] == 1 and r["n_other"] == 1
    assert r["enough"] and not r["all_pass"]
    assert r["upper95_fail_rate"] == pytest.approx(0.3)


def test_judge_run_not_enough_attempts():
    r = mj.judge_run([row()] * 9, 10)
    assert not r["enough"] and r["all_pass"]


def test_judge_run_empty():
    r = mj.judge_run([], 10)
    assert r["n"] == 0 and not r["all_pass"] and r["upper95_fail_rate"] is None


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
