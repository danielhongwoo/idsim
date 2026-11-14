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

"""sitl_judge 단위 테스트. 합성 표본으로 각 판정의 통과와 실패를 고정한다."""
import dataclasses

from tests.support import measure_judge as mj
from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw

US = 1_000_000


def st(ts, arming=mj.ARMING_STATE_ARMED, nav=mj.NAV_STATE_OFFBOARD, failsafe=False, recv=None):
    return mj.StatusSample(ts, ts + 20_000 if recv is None else recv, ts, arming, nav, failsafe, nav)


def ev(status, goal="g1", t=0, reason=0, vid="px4_1", mid="m1", count=3, done=0, last=0, detail=""):
    return sj.EventRec(t, t, vid, mid, goal, status, reason, count, done, last, detail)


def res(status=sj.STATUS_SUCCEEDED, reason=0, done=3, last=2, detail=""):
    return sj.ResultRec(10, status, reason, done, last, detail)


def cats(findings):
    return [c for c, _ in findings]


# --- result, 사건 ---

def test_check_result():
    assert sj.check_result(res(), sj.STATUS_SUCCEEDED, 0, 3) == []
    assert cats(sj.check_result(None, 4, 0)) == [sw.WRONG_RESULT]
    assert cats(sj.check_result(res(sj.STATUS_ABORTED, 1), 4, 0)) == [sw.WRONG_RESULT] * 2
    assert cats(sj.check_result(res(done=2), 4, 0, 3)) == [sw.WRONG_RESULT]


def good_events(result):
    return [ev(sj.STATUS_ACCEPTED, t=1),
            ev(result.status, t=5, reason=result.reason, done=result.items_completed,
               last=result.last_item_index, detail=result.detail)]


def pair(events, result=None, **kw):
    result = result or res()
    args = dict(goal_id="g1", vehicle_id="px4_1", mission_id="m1", item_count=3,
                terminal_status=result.status, result=result)
    args.update(kw)
    return sj.check_event_pair(events, **args)


def test_event_pair_ok():
    assert pair(good_events(res())) == []


def test_event_pair_ignores_other_goals():
    other = [ev(sj.STATUS_ACCEPTED, goal="old", vid="x"), ev(sj.STATUS_SUCCEEDED, goal="old")]
    assert pair(other + good_events(res())) == []


def test_event_pair_missing():
    r = res()
    assert cats(pair([good_events(r)[1]], r)) == [sw.EVENT_MISSING]
    assert cats(pair([good_events(r)[0]], r)) == [sw.EVENT_MISSING]
    assert cats(pair([], r)) == [sw.EVENT_MISSING] * 2


def test_event_pair_mismatch_cases():
    r = res()
    base = good_events(r)
    assert pair(base + [base[1]], r)[0][0] == sw.EVENT_MISMATCH          # 종료 사건 둘
    bad_v = [base[0], ev(r.status, t=5, vid="px4_9", done=3, last=2)]
    assert sw.EVENT_MISMATCH in cats(pair(bad_v, r))                     # 다른 기체 id
    bad_m = [base[0], ev(r.status, t=5, mid="zz", done=3, last=2)]
    assert sw.EVENT_MISMATCH in cats(pair(bad_m, r))
    differs = [base[0], ev(r.status, t=5, done=2, last=2)]
    assert sw.EVENT_MISMATCH in cats(pair(differs, r))                   # 종료 사건 != result
    back = [ev(sj.STATUS_ACCEPTED, t=9), ev(r.status, t=5, done=3, last=2)]
    assert sw.EVENT_MISMATCH in cats(pair(back, r))                      # stamp 거꾸로
    accepted_dirty = [ev(sj.STATUS_ACCEPTED, t=1, reason=3), base[1]]
    assert sw.EVENT_MISMATCH in cats(pair(accepted_dirty, r))
    assert sw.EVENT_MISMATCH in cats(pair(base, r, item_count=4))
    assert sw.EVENT_MISMATCH in cats(pair(base, r, terminal_status=sj.STATUS_ABORTED))


def test_no_feedback():
    fb = sj.FeedbackRec(1, "g1", 1, 0, 3, 1, 1)
    assert sj.check_no_feedback([], "g1") == []
    assert sj.check_no_feedback([fb], "other") == []
    assert cats(sj.check_no_feedback([fb], "g1")) == [sw.WRONG_RESULT]


# --- 사전조건 ---

def test_clock_alignment():
    good = [st(t * 200_000, recv=t * 200_000 + 30_000) for t in range(1, 11)]
    assert sj.clock_alignment_findings(good) == []
    assert cats(sj.clock_alignment_findings(good[:3])) == [sw.PRECONDITION]
    off = [st(t * 200_000, recv=t * 200_000 + 300_000) for t in range(1, 11)]   # 중앙값 0.3 s
    assert "중앙값" in sj.clock_alignment_findings(off)[0][1]
    spike = good[:9] + [st(5_000_000, recv=5_700_000)]
    f = sj.clock_alignment_findings(spike)
    assert len(f) == 1 and "최대" in f[0][1]


def test_disarmed_and_landed_confirmed():
    d = [st(i * 100_000, arming=mj.ARMING_STATE_DISARMED) for i in range(1, 5)]
    assert sj.disarmed_confirmed(d)
    assert not sj.disarmed_confirmed(d[:2])
    mixed = [d[0], st(250_000), d[2], d[3]]
    assert not sj.disarmed_confirmed(mixed)
    assert not sj.disarmed_confirmed(d, after_recv_us=d[-1].recv_ros_us)
    ls = [mj.LandedSample(i, i, True) for i in (1, 2, 3)]
    assert sj.landed_confirmed(ls)
    assert not sj.landed_confirmed([mj.LandedSample(1, 1, True), mj.LandedSample(2, 2, False),
                                    mj.LandedSample(3, 3, True)])


def test_flag_phase_confirmed_counts_distinct_timestamps():
    flags = [sj.FlagSample(100, 110, True), sj.FlagSample(100, 111, True), sj.FlagSample(200, 210, True)]
    assert not sj.flag_phase_confirmed(flags, 0, True)           # 같은 timestamp 중복은 세지 않는다
    flags.append(sj.FlagSample(300, 310, True))
    assert sj.flag_phase_confirmed(flags, 0, True)
    assert not sj.flag_phase_confirmed(flags, 0, False)
    assert not sj.flag_phase_confirmed(flags, 150, True)         # 기준 시각 뒤 표본만


# --- 이륙, 고도 ---

def pos(recv, z, valid=True):
    return (recv, 0.0, 0.0, z, 0.0, True, valid)


def test_reached_height_uses_goal_target_not_setpoint():
    assert sj.reached_height(-5.2, 0.0, 5.0, 0.3)
    assert sj.reached_height(-4.8, 0.0, 5.0, 0.3)
    assert not sj.reached_height(-4.6, 0.0, 5.0, 0.3)
    assert not sj.reached_height(-5.4, 0.0, 5.0, 0.3)


def test_first_reached_needs_valid_z_and_time():
    p = [pos(1, -1.0), pos(2, -5.0, valid=False), pos(3, -5.0), pos(4, -5.0)]
    assert sj.first_reached(p, 0.0, 5.0, 0.3) == 3
    assert sj.first_reached(p, 0.0, 5.0, 0.3, after_recv_us=3) == 4
    assert sj.first_reached(p[:2], 0.0, 5.0, 0.3) is None


def test_altitude_hold():
    p = [pos(i * US, -5.0 + 0.05 * (i % 2)) for i in range(6)]
    assert sj.altitude_hold_findings(p, 0, 5 * US, -5.0) == []
    sag = p + [pos(7 * US, -4.0)]
    assert cats(sj.altitude_hold_findings(sag, 0, 8 * US, -5.0)) == [sw.WRONG_RESULT]
    assert cats(sj.altitude_hold_findings([], 0, US, -5.0)) == [sw.WRONG_RESULT]


# --- 시나리오 A ---

def test_armed_window_counts_by_timestamp():
    s = [st(100, mj.ARMING_STATE_DISARMED), st(200), st(250, nav=mj.NAV_STATE_AUTO_LOITER), st(300), st(900)]
    w = sj.armed_window(s, 100, 300)
    assert w["armed_samples"] == 3 and w["armed_non_offboard"] == 1
    assert w["armed_non_offboard_samples"][0]["ts_us"] == 250
    assert sj.armed_window(s, 100, 150)["armed_samples"] == 0


def test_flight_window():
    ok = [st(100), st(200), st(300)]
    assert sj.flight_window_findings(ok, 100, 300) == []
    assert cats(sj.flight_window_findings([], 0, 1)) == [sw.WRONG_RESULT]
    f = sj.flight_window_findings([st(100), st(200, failsafe=True, nav=mj.NAV_STATE_AUTO_LAND)], 0, 300)
    assert len(f) == 2
    only_nav = sj.flight_window_findings([st(100), st(200, nav=mj.NAV_STATE_AUTO_LOITER)], 0, 300)
    assert len(only_nav) == 1 and "OFFBOARD" in only_nav[0][1]


def test_milestones_ordered():
    assert sj.milestones_ordered([("a", 1), ("b", 1), ("c", 5)]) == []
    assert "순서" in sj.milestones_ordered([("a", 5), ("b", 2)])[0][1]
    assert "관측되지" in sj.milestones_ordered([("a", 5), ("b", None)])[0][1]


def test_milestones_same_clock_tolerates_px4_ts_skew():
    # PX4 timestamp가 ROS /clock보다 4 ms 앞서도(/clock 지연) 수신 시각으로 비교하면 순서가 맞는다
    D = mj.ARMING_STATE_DISARMED
    land = mj.NAV_STATE_AUTO_LAND
    s = [st(100, D, recv=100), st(200, recv=200), st(300, nav=land, recv=300), st(400, D, nav=land, recv=400),
         st(500, D, nav=land, recv=500), st(600, D, nav=land, recv=596)]     # 마지막: PX4 stamp 600, ROS 수신 596
    f, m = sj.sequence_findings(s, 0)
    assert f == [] and m["disarmed_recv_us"] == 596
    result_recv = 597                            # PX4 stamp(600)와 섞어 비교하면 3 앞이라 위반으로 보이는 값
    assert result_recv < m["disarmed_ts"]
    assert sj.milestones_ordered([("auto_land", m["land_recv_us"]), ("disarmed", m["disarmed_recv_us"]),
                                  ("result", result_recv)]) == []
    # 실제 순서 위반(result가 3회 확인 수신보다 앞)은 여전히 잡는다
    bad = sj.milestones_ordered([("disarmed", m["disarmed_recv_us"]), ("result", 595)])
    assert len(bad) == 1 and "순서 위반" in bad[0][1]


def test_milestones_use_receiver_clock_for_executor_stamps():
    # Executor stamp(다른 노드 시계)가 테스트 노드의 goal_sent보다 4 ms 앞서 보여도 수신 시각끼리는 순서가 맞는다
    acc = dataclasses.replace(ev(sj.STATUS_ACCEPTED), recv_us=1004, stamp_us=996)
    goal_sent = 1000
    assert acc.stamp_us < goal_sent < acc.recv_us
    assert "순서 위반" in sj.milestones_ordered([("goal_sent", goal_sent), ("accepted", acc.stamp_us)])[0][1]
    assert sj.milestones_ordered([("goal_sent", goal_sent), ("accepted", acc.recv_us)]) == []


def test_unreached_description():
    res = sj.ResultRec(recv_us=1, status=sj.STATUS_ABORTED, reason=3, items_completed=0, last_item_index=0, detail="x")
    fb = sj.FeedbackRec(recv_us=1, goal_id="g", stamp_us=1, item_index=0, item_count=3, item_type=1,
                        phase=sj.PHASE_PREPARING)
    d = sj.unreached_description(res, [fb], st(100, mj.ARMING_STATE_DISARMED))
    assert "ABORTED" in d and "phase=1" in d and "arming_state=%d" % mj.ARMING_STATE_DISARMED in d
    d0 = sj.unreached_description(None, [], None)
    assert "result 없음" in d0 and "feedback 없음" in d0


def test_sequence_requires_armed_before_disarmed():
    D = mj.ARMING_STATE_DISARMED
    land = mj.NAV_STATE_AUTO_LAND
    good = [st(100, D), st(200), st(300, nav=land), st(400, nav=land), st(500, D, nav=land),
            st(600, D, nav=land), st(700, D, nav=land)]
    f, m = sj.sequence_findings(good, 0)
    assert f == [] and m["armed_ts"] < m["land_ts"] < m["disarmed_ts"]
    only_disarmed = [st(100 * i, D) for i in range(1, 6)]
    assert "ARMED 표본을 보지 못했다" in sj.sequence_findings(only_disarmed, 0)[0][0][1]
    no_land = [st(100), st(200), st(300, D), st(400, D), st(500, D)]
    assert "AUTO_LAND" in sj.sequence_findings(no_land, 0)[0][0][1]
    early_disarm = [st(100, D), st(200, D), st(250, D), st(300), st(400, nav=land)]
    assert sj.sequence_findings(early_disarm, 0)[0] != []        # DISARMED가 AUTO_LAND 앞이면 인정하지 않는다
    short = [st(100), st(200, nav=land), st(300, D, nav=land), st(400, D, nav=land)]
    assert "연속" in sj.sequence_findings(short, 0)[0][0][1]


def test_never_armed():
    D = mj.ARMING_STATE_DISARMED
    assert sj.never_armed_findings([st(i, D, recv=i) for i in (1, 2, 3)], 0, 10) == []
    f = sj.never_armed_findings([st(1, D, recv=1), st(2, D, recv=2), st(3, recv=3)], 0, 10)
    assert cats(f) == [sw.WRONG_RESULT] and "ARMED 표본이" in f[0][1]
    assert sj.never_armed_findings([st(20, D, recv=20)] + [st(i, D, recv=i) for i in (1, 2, 3)], 0, 10) == []   # 구간 밖


def test_never_armed_needs_samples_in_range():
    D = mj.ARMING_STATE_DISARMED
    f = sj.never_armed_findings([st(1, D, recv=1), st(2, D, recv=2)], 0, 10)
    assert cats(f) == [sw.WRONG_RESULT] and "표본이 2개뿐" in f[0][1]
    assert cats(sj.never_armed_findings([], 0, 10)) == [sw.WRONG_RESULT]
    assert sj.never_armed_findings([st(i, D, recv=i) for i in (1, 2, 3)], 0, 10) == []


def test_hover_state_needs_samples_and_whole_range():
    L = [mj.LandedSample(i, i, False) for i in (1, 2)]
    S = [st(i, recv=i) for i in (1, 2, 3)]
    assert sj.hover_state_findings(S, L, 0, 10) == []
    assert len(sj.hover_state_findings(S[:2], L, 0, 10)) == 1                      # 상태 표본 부족
    assert len(sj.hover_state_findings(S, L[:1], 0, 10)) == 1                      # landed 표본 부족
    assert len(sj.hover_state_findings(S[:2] + [st(3, mj.ARMING_STATE_DISARMED, recv=3)], L, 0, 10)) == 1
    assert len(sj.hover_state_findings(S, L + [mj.LandedSample(3, 3, True)], 0, 10)) == 1
    assert len(sj.hover_state_findings([], [], 0, 10)) == 2


def test_cancel_hover_confirmation():
    L = mj.NAV_STATE_AUTO_LOITER
    s = [st(100, nav=mj.NAV_STATE_OFFBOARD, recv=100), st(200, nav=L, recv=200), st(300, nav=L, recv=300),
         st(400, nav=L, recv=400)]
    f, hit = sj.cancel_hover_findings(s, 50)
    assert f == [] and hit.ts_us == 400
    f, hit = sj.cancel_hover_findings(s[:3], 50)
    assert hit is None and cats(f) == [sw.WRONG_RESULT]
    assert sj.cancel_hover_findings(s, 250)[1] is None            # 기준 시각 뒤 표본만


def test_altitude_max_deviation():
    p = [pos(1, -5.0), pos(2, -5.2), pos(3, -4.9, valid=False), pos(9, -3.0)]
    assert abs(sj.altitude_max_deviation(p, 0, 5, -5.0) - 0.2) < 1e-9
    assert sj.altitude_max_deviation(p, 20, 30, -5.0) is None
