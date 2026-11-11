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


def loiter(ts, recv):
    return st(ts, recv, nav=mj.NAV_STATE_AUTO_LOITER)


def test_cleanup_air_branch_stops_publishing_at_first_loiter_and_ends_at_third():
    m = mj.CleanupModel(0)
    events = {
        0: [("landed", False)],
        700_000: [("status", loiter(700_100, 700_000))],
        1_200_000: [("status", loiter(1_200_100, 1_200_000))],
        1_700_000: [("status", loiter(1_700_100, 1_700_000))],
    }
    sent = run_model(m, events, 5 * US)
    assert {k for _, k in sent} == {"hold"}
    assert m.publish_stop_us == 700_000          # 첫 관측에서 발행 중단
    assert m.end_reason == "HOLD"
    assert m.end_us == 1_700_000                 # 종료와 총 소요는 3회 연속 시점
    assert m.elapsed_s == 1.7
    assert not m.publishing
    assert mj.branch_sequence(m.branch_log)["sequence"] == "A"


def test_cleanup_hold_same_timestamp_not_counted_and_non_loiter_resets():
    m = mj.CleanupModel(0)
    m.step(0, False)
    m.note_sent("hold", 0, 1)
    m.on_status(loiter(10, 10))
    m.on_status(loiter(10, 20))                  # 같은 timestamp: 건너뜀
    assert m._confirm["hold"].count == 1
    m.on_status(st(30, 30, nav=mj.NAV_STATE_OFFBOARD))
    assert m._confirm["hold"].count == 0


def test_cleanup_hold_sample_before_send_is_not_a_confirmation():
    m = mj.CleanupModel(0)
    m.on_status(loiter(5, 5))                    # 전송 전 표본
    m.step(10, False)
    m.note_sent("hold", 10, 10)
    m.step(20, False)
    assert m.publishing and m.publish_stop_us is None


def test_cleanup_publishing_stays_true_when_ground_branch_without_hold():
    m = mj.CleanupModel(0)
    run_model(m, {}, 1 * US)
    assert m.publishing and m.publish_stop_us is None


def test_cleanup_end_stops_publishing():
    m = mj.CleanupModel(0)
    run_model(m, {}, 20 * US)
    assert m.end_reason == "TIMEOUT_GROUND" and not m.publishing
    assert m.publish_stop_us == m.end_us


def test_cleanup_disarmed_air_beats_expiry_in_same_tick():
    # 공중 분기의 timeout(3 s)이 되는 tick에 DISARMED 표본이 이미 있으면 관측이 먼저다(M6 순서)
    m = mj.CleanupModel(0)
    m.step(0, False)
    m.note_sent("hold", 0, 1)
    m.on_status(st(100, 100, arming=mj.ARMING_STATE_DISARMED))
    m.step(3 * US, False)
    assert m.end_reason == "DISARMED_AIR"


def test_cleanup_nothing_to_clean_when_arm_never_sent():
    m = mj.CleanupModel(0, arm_sent=False)
    m.on_status(st(100, 100, arming=mj.ARMING_STATE_DISARMED))
    m.step(200, True)
    assert m.end_reason == "NOTHING_TO_CLEAN"
    m2 = mj.CleanupModel(0, arm_sent=True)
    m2.on_status(st(100, 100, arming=mj.ARMING_STATE_DISARMED))
    assert m2.step(200, True) == ["disarm"]      # arm을 보냈으면 disarm 분기를 거친다


def test_cleanup_nothing_to_clean_beats_hard_limit():
    m = mj.CleanupModel(0, arm_sent=False)
    m.on_status(st(100, 100, arming=mj.ARMING_STATE_DISARMED))
    m.step(12 * US, True)
    assert m.end_reason == "NOTHING_TO_CLEAN"


def test_cleanup_branch_flip_resets_branch_timer_and_logs_order():
    m = mj.CleanupModel(0)
    events = {
        0: [("landed", True)],
        2 * US: [("landed", False)],       # 지상 분기 2 s -> 공중 분기
        4 * US: [("landed", True)],        # 공중 분기 2 s -> 지상 분기
    }
    run_model(m, events, 10 * US)
    assert [b for _, b in m.branch_log] == ["G", "A", "G", ]
    # 지상 분기는 들어갈 때마다 timer를 새로 잡으므로 4 s + 3 s = 7 s에 끝난다
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


def test_cleanup_reentering_ground_resets_disarm_count_and_floor():
    m = mj.CleanupModel(0)
    m.step(0, True)
    m.note_sent("disarm", 0, 10)
    # 첫 지상 분기에서 DISARMED 2개, 그 뒤 ARMED 표본(공중 분기가 DISARMED_AIR로 바로 끝나지 않게)
    m.on_status(st(100, 100, arming=mj.ARMING_STATE_DISARMED))
    m.on_status(st(200, 200, arming=mj.ARMING_STATE_DISARMED))
    assert m._confirm["disarm"].count == 2
    m.on_status(st(250, 250))
    m.step(300, False)                       # A 분기
    m.step(400, True)                        # G 재진입
    assert m.first_send["disarm"] is None    # 첫 전송 기준을 새로 잡는다
    assert m._confirm["disarm"].count == 0
    assert m.step(400, True) == ["disarm"]   # disarm을 새로 보낸다
    m.note_sent("disarm", 400, 1000)
    # 재진입 전송 전에 받은 표본(ts 200)이나 전송 값(ts 1000) 이하인 표본은 세지 않는다
    m.on_status(st(900, 450, arming=mj.ARMING_STATE_DISARMED))
    m.on_status(st(1000, 460, arming=mj.ARMING_STATE_DISARMED))
    assert m._confirm["disarm"].count == 0
    for i, ts in enumerate((1100, 1200, 1300)):
        m.on_status(st(ts, 500 + i, arming=mj.ARMING_STATE_DISARMED))
    m.step(600, True)
    assert m.end_reason == "DISARMED"
    assert [k for k, _, _ in m.sent_log] == ["disarm", "disarm"]


def test_cleanup_disarmed_received_in_air_branch_does_not_confirm_on_return():
    m = mj.CleanupModel(0)
    m.step(0, True)
    m.note_sent("disarm", 0, 10)
    m.step(100, False)                       # A 분기
    m.note_sent("hold", 100, 110)
    for i, ts in enumerate((200, 300, 400)):
        m.on_status(st(ts, ts, arming=mj.ARMING_STATE_DISARMED))   # A 분기 중 받은 DISARMED 3개
    m.step(450, True)                        # G 복귀 step. 공중 DISARMED 관측은 A에서만 본다
    assert m.end_reason != "DISARMED"
    assert m._confirm["disarm"].count == 0


def test_cleanup_reentering_air_resets_hold_state():
    m = mj.CleanupModel(0)
    m.step(0, False)
    m.note_sent("hold", 0, 10)
    m.on_status(loiter(100, 100))
    m.step(150, True)                        # G
    m.step(200, False)                       # A 재진입
    assert m.first_send["hold"] is None and m._confirm["hold"].count == 0
    assert m._confirm["hold_first"].count == 0


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
            "cleanup_total_s": 1.2, "armed_after_end": False, "final_disarmed": True,
            "arm_evidence": True}


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


def b2(**kw):
    """2b 사실. 기본은 landed가 true에 닿지 못한 60 s 관찰(조건과 표본 조건 만족)."""
    f = {"landed_true_seen": False, "observe_span_s": 60.0, "observe_status_n": 120,
         "observe_landed_n": 60, "observe_status_age_s": 0.3, "observe_landed_age_s": 0.5,
         "observe_status_gap_ts_s": 0.51, "observe_status_gap_recv_s": 0.52,
         "observe_landed_gap_ts_s": 1.01, "observe_landed_gap_recv_s": 1.02,
         "observe_all_armed_loiter": True, "observe_landed_transitions": 0, "dz_max_m": 0.05}
    f.update(kw)
    return f


def test_judge_attempt_2a():
    f = {"end_reason": "HOLD", "cleanup_total_s": 0.8, "armed_non_offboard": 0}
    assert mj.judge_attempt("2a", f).ok
    f["armed_non_offboard"] = 3        # (2a)는 기록만 하고 판정하지 않는다
    assert mj.judge_attempt("2a", f).ok
    f["end_reason"] = "TIMEOUT_HOLD"
    assert not mj.judge_attempt("2a", f).ok


def test_judge_2b_landed_true_reached_is_m3_contradicted_even_if_disarm_ok():
    g = {"landed_true_seen": True, "landed_true_after_hold_s": 4.0, "disarm_confirmed": True,
         "dz_max_m": 0.1}
    v = mj.judge_attempt("2b", g)
    assert v.verdict == "M3_CONTRADICTED" and not v.ok
    assert "M3 문장과 다르다" in v.reasons[0] and "True" in v.reasons[0]
    for kw in ({"disarm_confirmed": False}, {"dz_max_m": 0.3}, {"dz_max_m": None}):
        assert mj.judge_attempt("2b", dict(g, **kw)).verdict == "M3_CONTRADICTED"
    assert "M3_CONTRADICTED" in mj.EXIT1_VERDICTS and "M3_CONTRADICTED" in mj.VALID_VERDICTS


def test_judge_2b_cond_not_reached_when_state_matches_after_60s():
    v = mj.judge_attempt("2b", b2())
    assert v.verdict == "COND_NOT_REACHED" and not v.ok


def test_judge_2b_cond_not_reached_requires_conditions_else_fail():
    for key, val in [("observe_all_armed_loiter", False), ("observe_landed_transitions", 1),
                     ("dz_max_m", 0.21)]:
        v = mj.judge_attempt("2b", b2(**{key: val}))
        assert v.verdict == "FAIL", (key, val)
    assert mj.judge_attempt("2b", b2(dz_max_m=0.2)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(dz_max_m=None)).verdict == "INCONCLUSIVE"     # 값 없음은 FAIL이 아니다


def test_judge_2b_short_observation_is_inconclusive():
    assert mj.judge_attempt("2b", b2(observe_span_s=59.9)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_span_s=60.0)).verdict == "COND_NOT_REACHED"
    # 어긋나는 관측은 관찰이 짧아도 FAIL이다
    assert mj.judge_attempt("2b", b2(observe_span_s=10, observe_landed_transitions=2)).verdict == "FAIL"


def test_judge_2b_observation_without_samples_is_not_state_held():
    # 표본이 없는 관찰을 M3 상태 유지로 읽지 않는다
    empty = dict(observe_status_n=0, observe_landed_n=0, observe_status_age_s=None,
                 observe_landed_age_s=None)
    assert mj.judge_attempt("2b", b2(**empty)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_status_n=59)).verdict == "INCONCLUSIVE"     # 60 s x 1.0/s 미만
    assert mj.judge_attempt("2b", b2(observe_status_n=60)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_landed_n=29)).verdict == "INCONCLUSIVE"     # 60 s x 0.5/s 미만
    assert mj.judge_attempt("2b", b2(observe_landed_n=30)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_status_age_s=1.01)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_status_age_s=1.0)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_landed_age_s=2.01)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_landed_age_s=None)).verdict == "INCONCLUSIVE"


def test_judge_2b_skipped_is_inconclusive():
    v = mj.judge_attempt("2b", {"skipped": "2a가 Hold로 끝나지 않음"})
    assert v.verdict == "INCONCLUSIVE"


def hold3(**kw):
    f = good3()
    f.update({"end_reason": "HOLD", "hold_observe_span_s": 60.0, "hold_observe_status_n": 120,
              "hold_observe_landed_n": 60, "hold_observe_status_age_s": 0.3,
              "hold_observe_landed_age_s": 0.5, "hold_observe_status_gap_ts_s": 0.51,
              "hold_observe_status_gap_recv_s": 0.52, "hold_observe_landed_gap_ts_s": 1.01,
              "hold_observe_landed_gap_recv_s": 1.02, "hold_observe_all_armed_loiter": True,
              "hold_observe_landed_false": True, "hold_observe_dz_m": 0.05})
    f.update(kw)
    return f


def test_judge_3_hold_end_when_m3_state_held_for_60s():
    v = mj.judge_attempt("3", hold3())
    assert v.verdict == "HOLD_END" and not v.ok
    assert "기준표 밖" not in v.reasons[0] and "전이 표에 있는" in v.reasons[0]


def test_judge_3_hold_end_conditions_violated_is_fail():
    for key, val in [("hold_observe_all_armed_loiter", False), ("hold_observe_landed_false", False),
                     ("hold_observe_dz_m", 0.21), ("climb_m", 0.21), ("cleanup_total_s", 9.0),
                     ("armed_non_offboard", 1)]:
        v = mj.judge_attempt("3", hold3(**{key: val}))
        assert v.verdict == "FAIL", (key, val)


def test_judge_3_hold_end_missing_values_are_inconclusive_not_fail():
    assert mj.judge_attempt("3", hold3(hold_observe_dz_m=None)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("3", hold3(climb_m=None)).verdict == "INCONCLUSIVE"
    # 위반이 같이 있으면 FAIL이 앞선다
    assert mj.judge_attempt("3", hold3(climb_m=None, hold_observe_dz_m=0.5)).verdict == "FAIL"


def test_judge_3_hold_end_short_or_empty_observation_is_inconclusive():
    assert mj.judge_attempt("3", hold3(hold_observe_span_s=59.0)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("3", hold3(hold_observe_status_n=0, hold_observe_status_age_s=None)
                            ).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("3", hold3(hold_observe_landed_n=0)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("3", hold3(hold_observe_status_age_s=1.5)).verdict == "INCONCLUSIVE"


def test_judge_3_other_end_reasons_stay_fail():
    for reason in ("TIMEOUT_GROUND", "TIMEOUT_HOLD", "LIMIT", "DISARMED_AIR"):
        v = mj.judge_attempt("3", dict(good3(), end_reason=reason))
        assert v.verdict == "FAIL", reason


def test_judge_5_hold_end_is_fail():
    f = dict(good3(), end_reason="HOLD")
    assert mj.judge_attempt("5", f).verdict == "FAIL"


def test_judge_5_no_arm_evidence_is_inconclusive_when_everything_else_ok():
    v = mj.judge_attempt("5", dict(good3(), arm_evidence=False))
    assert v.verdict == "INCONCLUSIVE" and not v.ok
    assert "ack는 증거가 아니다" in v.reasons[0] and "ACCEPTED" not in v.reasons[0]
    assert v.kind == "ARM_EVIDENCE"
    assert mj.judge_attempt("5", dict(good3(), climb_m=None)).kind == ""       # 값 없음 INCONCLUSIVE는 종류가 다르다
    # 다른 위반이 있으면 FAIL이 앞선다
    assert mj.judge_attempt("5", dict(good3(), arm_evidence=False, climb_m=0.5)).verdict == "FAIL"
    assert mj.judge_attempt("5", good3()).verdict == "PASS"


def test_judge_5_missing_arm_evidence_key_raises():
    f = good3()
    del f["arm_evidence"]
    with pytest.raises(KeyError):
        mj.judge_attempt("5", f)


def test_judge_attempt_armed():
    ok = {"armed_non_offboard": 0, "armed3_reached": True, "flight_armed_non_offboard": 0}
    assert mj.judge_attempt("armed", ok).ok
    assert not mj.judge_attempt("armed", dict(ok, armed3_reached=False)).ok
    assert not mj.judge_attempt("armed", dict(ok, armed_non_offboard=2)).ok
    assert not mj.judge_attempt("armed", dict(ok, flight_armed_non_offboard=1)).ok
    bad = dict(ok)
    del bad["flight_armed_non_offboard"]
    with pytest.raises(KeyError):
        mj.judge_attempt("armed", bad)


def test_judge_attempt_unknown_item():
    with pytest.raises(ValueError):
        mj.judge_attempt("9", {})


# --- 실행 요약 ------------------------------------------------------------


def row(verdict="PASS", reached=False, bad=0, item="3", cls=mj.CLASS_DIRECT):
    return {"verdict": verdict, "armed3_reached": reached, "armed_non_offboard": bad,
            "item": item, "class": cls}


def test_judge_run_counts_failed_and_other_attempts():
    rows = [row("PASS")] * 8 + [row("FAIL"), row("PRECONDITION")]
    r = mj.judge_run(rows, 10)
    assert r["n"] == 10 and r["n_pass"] == 8 and r["n_fail"] == 1 and r["n_other"] == 1
    assert r["n_valid"] == 9 and not r["enough"] and not r["all_pass"]     # PRECONDITION은 유효 시도가 아니다
    assert r["upper95_fail_rate"] == pytest.approx(3 / 9)


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


def test_armed_criterion_2a_rows_are_not_counted_as_reached_but_violations_stay():
    rows = [row(reached=True)] * 9 + [row(reached=True, item="2a")] * 5
    r = mj.judge_armed_criterion(rows)
    assert r["n_reached"] == 9 and not r["passed"]
    rows = [row(reached=True)] * 10 + [row(reached=True, item="2a", bad=2)]
    r = mj.judge_armed_criterion(rows)
    assert r["n_reached"] == 10 and r["violation_total"] == 2 and r["violated"] and not r["passed"]


def test_armed_criterion_is_judged_per_class():
    rows = ([row(reached=True)] * 10
            + [row(reached=True, cls=mj.CLASS_EXECUTOR, item="armed")] * 4)
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


# --- 경계와 누락 ----------------------------------------------------------


def test_judge_2b_dz_boundary_and_none():
    assert mj.judge_attempt("2b", b2(dz_max_m=0.2)).verdict == "COND_NOT_REACHED"   # 0.2는 이하
    assert mj.judge_attempt("2b", b2(dz_max_m=0.2001)).verdict == "FAIL"
    v = mj.judge_attempt("2b", b2(dz_max_m=None))
    assert v.verdict == "INCONCLUSIVE" and any("고도 변화" in r for r in v.reasons)


def test_judge_2a_cleanup_time_boundary_and_none():
    f = {"end_reason": "HOLD", "cleanup_total_s": 9.0}
    assert not mj.judge_attempt("2a", f).ok                  # 9.0은 실패(미만이어야 함)
    assert mj.judge_attempt("2a", dict(f, cleanup_total_s=8.999)).ok
    assert not mj.judge_attempt("2a", dict(f, cleanup_total_s=None)).ok


def test_judge_climb_none_is_inconclusive_for_3_and_5():
    for item in ("3", "5"):
        f = good3()
        f["climb_m"] = None
        v = mj.judge_attempt(item, f)
        assert v.verdict == "INCONCLUSIVE" and any("상승" in r for r in v.reasons)


def test_judge_item5_failure_reasons_are_separate():
    for key, val, word in [("end_reason", "TIMEOUT_GROUND", "DISARMED 3회"),
                           ("climb_m", 0.5, "상승"), ("cleanup_total_s", 10.0, "정리 총 소요"),
                           ("armed_after_end", True, "다시 ARMED"),
                           ("final_disarmed", False, "관찰 끝"),
                           ("armed_non_offboard", 2, "OFFBOARD")]:
        f = good3()
        f[key] = val
        v = mj.judge_attempt("5", f)
        assert not v.ok
        assert len(v.reasons) == 1 and word in v.reasons[0], (key, v.reasons)


def test_judge_armed_criterion_missing_key_raises():
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed3_reached": True, "item": "3", "class": "px4_direct"}])
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed_non_offboard": 0, "item": "3", "class": "px4_direct"}])


def test_judge_armed_criterion_missing_class_or_item_raises():
    with pytest.raises(KeyError):
        mj.judge_armed_criterion([{"armed3_reached": True, "armed_non_offboard": 0, "item": "3"}])


def test_judge_run_missing_key_raises():
    with pytest.raises(KeyError):
        mj.judge_run([{"verdict": "PASS"}], 1)


def test_armed_criterion_unmeasured_rows_are_not_read_as_zero():
    rows = [row(reached=True)] * 10 + [row(reached=None, bad=None)]
    r = mj.judge_armed_criterion(rows)
    assert r["n_unmeasured"] == 1 and r["n_measured"] == 10 and r["passed"]


def test_judge_run_valid_attempts_exclude_inconclusive_and_count_exit1_verdicts():
    rows = ([row("PASS", item="5")] * 8 + [row("INCONCLUSIVE", item="5")] * 2
            + [row("M3_CONTRADICTED", item="2b")])
    r = mj.judge_run(rows, 10)
    assert r["n_valid"] == 9 and r["n_fail"] == 1 and not r["enough"]
    r = mj.judge_run([row("PASS")] * 10 + [row("INCONCLUSIVE")] * 5, 10)
    assert r["enough"] and not r["all_pass"]


def test_armed_criterion_window_missed_rows_do_not_fill_n_reached():
    rows = [row(reached=True)] * 9 + [row("WINDOW_MISSED", reached=True)] * 5
    r = mj.judge_armed_criterion(rows)
    assert r["n_reached"] == 9 and not r["passed"]
    rows = [row(reached=True)] * 10 + [row("WINDOW_MISSED", reached=True, bad=1)]
    r = mj.judge_armed_criterion(rows)
    assert r["n_reached"] == 10 and r["violation_total"] == 1 and not r["passed"]


# --- 이웃 표본 간격 -----------------------------------------------------------


def test_neighbor_gap_middle_gap():
    t = [100 * US, 100 * US + 500_000, 103 * US + 500_000]
    assert mj.neighbor_gap_s(t, 99 * US + 900_000) == pytest.approx(3.0)       # 가운데 공백 3 s


def test_neighbor_gap_start_edge_uses_last_sample_before_start():
    # 시작 직전 표본이 있으면 그것을 구간 안으로 세어 첫 표본과의 간격을 잰다
    t = [10 * US, 14 * US, 14 * US + 500_000]
    assert mj.neighbor_gap_s(t, 13 * US) == pytest.approx(4.0)
    # 시작 직전 표본이 없으면 start부터 첫 표본까지
    assert mj.neighbor_gap_s([14 * US, 14 * US + 500_000], 11 * US) == pytest.approx(3.0)


def test_neighbor_gap_duplicates_ignored_and_empty_is_none():
    t = [1 * US, 1 * US, 1 * US + 500_000, 1 * US + 500_000]
    assert mj.neighbor_gap_s(t, 0) == pytest.approx(1.0)                # start 0 -> 첫 표본 1 s
    assert mj.neighbor_gap_s([], 0) is None
    assert mj.neighbor_gap_s([1 * US], 2 * US) is None                  # 구간 안 표본이 없다
    assert mj.neighbor_gap_s([1 * US, 5 * US], 0, end_us=3 * US) == pytest.approx(1.0)   # end 뒤는 무시


def test_judge_gap_limits_status_2s_and_landed_4s_use_longer_axis():
    assert mj.judge_attempt("2b", b2()).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_status_gap_ts_s=2.0)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_status_gap_ts_s=2.01)).verdict == "INCONCLUSIVE"
    # ROS 수신 쪽만 긴 간격도 걸린다
    assert mj.judge_attempt("2b", b2(observe_status_gap_recv_s=2.5)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_landed_gap_ts_s=4.0)).verdict == "COND_NOT_REACHED"
    assert mj.judge_attempt("2b", b2(observe_landed_gap_ts_s=4.01)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_landed_gap_recv_s=4.5)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("2b", b2(observe_status_gap_ts_s=None)).verdict == "INCONCLUSIVE"


def test_judge_gap_limits_apply_to_hold_end_too():
    assert mj.judge_attempt("3", hold3()).verdict == "HOLD_END"
    assert mj.judge_attempt("3", hold3(hold_observe_status_gap_recv_s=3.0)).verdict == "INCONCLUSIVE"
    assert mj.judge_attempt("3", hold3(hold_observe_landed_gap_ts_s=5.0)).verdict == "INCONCLUSIVE"
