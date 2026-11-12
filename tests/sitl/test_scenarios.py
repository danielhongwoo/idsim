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

"""이륙-호버-착륙 통합 테스트: 시나리오 B, C, A, D, T(decisions.md 쟁점 9). 한 스택에서 이 순서로 돈다.

판정 시간은 모두 ROS 시각이다. 판정 입력은 토픽에서만 읽는다(goal의 목표값과 vehicle_local_position,
vehicle_status, vehicle_land_detected, failsafe_flags, mission_event, action의 feedback과 result).
노드가 낸 setpoint는 입력으로 쓰지 않는다. 판정 함수는 tests/support/sitl_judge.py(순수 코드)에 있다.
각 시나리오 시작 전에 사전조건(지상, DISARMED N회 연속)을 단정하고 어긋나면 그 자리에서 실패한다.
"""
import json

import pytest

from tests.support import measure_judge as mj
from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw

TAKEOFF_M = 5.0
ACCEPTANCE_M = 0.3
RESULT_WAIT_S = 90.0         # goal 결과 대기(ROS 시각)
US = 1_000_000


def takeoff_item():
    return {"type": sj.TYPE_TAKEOFF, "timeout_s": 20.0, "height_m": TAKEOFF_M, "acceptance_m": ACCEPTANCE_M}


def loiter_item(duration_s=5.0, timeout_s=10.0):
    return {"type": sj.TYPE_LOITER, "timeout_s": timeout_s, "duration_s": duration_s}


def land_item():
    return {"type": sj.TYPE_LAND, "timeout_s": 30.0}


def goto_item():
    return {"type": 2, "timeout_s": 10.0, "position": (10.0, 0.0, 5.0), "acceptance_m": 1.0}


def send(s, vehicle_id, mission_id, items):
    """goal을 보내 수락 응답까지 받는다. 수락하지 않으면 WRONG_RESULT(받는 쪽은 판단할 수 있는 goal을 모두 수락한다)."""
    run = s.mission.send_goal(s.waiter, vehicle_id, mission_id, items)
    s.trace.event("goal_sent", mission_id=mission_id, vehicle_id=vehicle_id, accepted=run.accepted,
                  goal_id=run.goal_id, items=len(items))
    if not run.accepted:
        raise sw.SitlFailure(sw.WRONG_RESULT, "goal %s이 수락되지 않았다(즉시 ABORTED가 아니라 거절)" % mission_id)
    return run


def check_goal(s, run, *, terminal_status, reason, items_completed=None, vehicle_id=None, feedback_zero=False):
    """result, 사건 짝, (선택) feedback 0건을 한 번에 판정한다."""
    s.settle_events(run)
    own = vehicle_id or s.vehicle_id
    findings = sj.check_result(run.result, terminal_status, reason, items_completed)
    findings += sj.check_event_pair(
        s.mission.events, goal_id=run.goal_id, vehicle_id=own, mission_id=run.mission_id,
        item_count=run.item_count, terminal_status=terminal_status, result=run.result)
    if feedback_zero:
        findings += sj.check_no_feedback(s.mission.feedbacks, run.goal_id)
    s.trace.event("goal_checked", mission_id=run.mission_id, findings=[list(f) for f in findings])
    sw.raise_if(findings)


def mission_a(loiter_s=5.0):
    return [takeoff_item(), loiter_item(loiter_s, loiter_s + 5.0), land_item()]


def first_feedback(fbs, item_type):
    """항목의 첫 feedback. TAKEOFF와 LOITER는 PHASE_EXECUTING이고, LAND는 모드 명령 항목이라 PHASE_WAITING_MODE로
    시작한다(모드 전이 확인 대기). 그래서 LAND는 phase를 가리지 않는다."""
    return next((f for f in fbs if f.item_type == item_type
                 and (item_type == sj.TYPE_LAND or f.phase == sj.PHASE_EXECUTING)), None)


# ---------------------------------------------------------------------------


@pytest.mark.scenario("B")
def test_b_invalid_mission(session):
    """GOTO가 든 미션: ABORTED, INVALID_MISSION. 접수와 종료 사건. feedback 0건. 일정 ROS 시간 disarmed 유지."""
    s = session
    s.require_ground_disarmed("B")
    t0 = s.raw.now_us()
    run = send(s, s.vehicle_id, "b-invalid-goto", [goto_item()])
    s.mission.wait_result(s.waiter, run, 30.0, "B result")
    check_goal(s, run, terminal_status=sj.STATUS_ABORTED, reason=sj.REASON_INVALID_MISSION, feedback_zero=True)

    def not_armed():
        sw.raise_if(sj.never_armed_findings(s.raw.status, t0, s.raw.now_us()))

    s.waiter.hold_for(sj.DISARMED_HOLD_S, "B disarmed 유지", check=not_armed)
    not_armed()


@pytest.mark.scenario("C")
def test_c_vehicle_id_mismatch(session):
    """goal의 vehicle_id가 다른 값: ABORTED, VEHICLE_ID_MISMATCH. 사건의 vehicle_id는 Executor 자신의 값. feedback 0건."""
    s = session
    s.require_ground_disarmed("C")
    t0 = s.raw.now_us()
    other = "px4_999"
    assert other != s.vehicle_id
    run = send(s, other, "c-id-mismatch", mission_a())
    s.mission.wait_result(s.waiter, run, 30.0, "C result")
    check_goal(s, run, terminal_status=sj.STATUS_ABORTED, reason=sj.REASON_VEHICLE_ID_MISMATCH,
               vehicle_id=s.vehicle_id, feedback_zero=True)

    def not_armed():
        sw.raise_if(sj.never_armed_findings(s.raw.status, t0, s.raw.now_us()))

    s.waiter.hold_for(sj.DISARMED_HOLD_S, "C disarmed 유지", check=not_armed)
    not_armed()


def _record_armed_a(s, t_goal, run):
    """goal 전송부터 TAKEOFF 시작(feedback PHASE_EXECUTING의 stamp)까지의 ARMED 표본 기록과 회차 요약 필드.

    vehicle_status 원시 표본(KEEP_ALL 기록기)에서 센다. 노드의 tick 모델과 무관하다. 구간은 PX4 timestamp 축이다.
    TAKEOFF 시작을 보지 못한 실행은 지금까지를 구간으로 잡는다(그때 A는 이미 실패했다).
    """
    raw = s.raw
    fb = first_feedback(s.mission.feedbacks_of(run), sj.TYPE_TAKEOFF) if run.goal_id else None
    end = fb.stamp_us if fb is not None else raw.now_us()
    w = sj.armed_window(raw.status, t_goal, end)
    armed3 = mj.armed_confirm_sample(raw.status, t_goal)
    w.update({"armed3_reached": armed3 is not None and armed3.ts_us <= end, "window_us": [t_goal, end],
              "takeoff_start_seen": fb is not None, "class": mj.CLASS_EXECUTOR})
    s.armed_a = w
    path = s.dump_raw_status("raw_status_A.jsonl", t_goal)
    (s.out_dir / "armed_a.json").write_text(json.dumps(w, indent=1, sort_keys=True) + "\n", encoding="ascii")
    s.trace.event("armed_a", **{k: v for k, v in w.items() if k != "armed_non_offboard_samples"}, raw=path.name)
    return w


@pytest.mark.scenario("A")
def test_a_normal_flight(session):
    """[TAKEOFF 5 m, LOITER 5 s, LAND] 콜드 상태. 이정표의 순서와 ROS 시각 단조 증가, 사건 짝과 result 일치,
    TAKEOFF와 LOITER 동안 failsafe 없음과 OFFBOARD."""
    s = session
    raw = s.raw
    s.require_ground_disarmed("A")
    z0 = s.z_ref()
    t_goal = raw.now_us()
    s.mark("A", "goal_sent", t_goal)
    run = send(s, s.vehicle_id, "a-takeoff-loiter-land", mission_a())
    try:
        s.mission.wait_result(s.waiter, run, RESULT_WAIT_S, "A result")
        s.waiter.hold_for(1.0, "A 표본 수신 여유")      # 늦게 도착하는 vehicle_status를 기다린다
    finally:
        armed = _record_armed_a(s, t_goal, run)
    if armed["armed_non_offboard"]:
        raise sw.SitlFailure(
            sw.WRONG_RESULT, "OFFBOARD가 아닌 ARMED 표본이 %d개 나왔다(ARMED 표본 %d개). P6의 1회 판정을 "
            "architect에게 올린다: %s" % (armed["armed_non_offboard"], armed["armed_samples"],
                                          armed["armed_non_offboard_samples"]))

    check_goal(s, run, terminal_status=sj.STATUS_SUCCEEDED, reason=sj.REASON_NONE, items_completed=3)

    fbs = s.mission.feedbacks_of(run)
    fb_take = first_feedback(fbs, sj.TYPE_TAKEOFF)
    fb_loiter = first_feedback(fbs, sj.TYPE_LOITER)
    fb_land = first_feedback(fbs, sj.TYPE_LAND)
    missing = [n for n, f in (("TAKEOFF", fb_take), ("LOITER", fb_loiter), ("LAND", fb_land)) if f is None]
    if missing:
        raise sw.SitlFailure(sw.WRONG_RESULT, "항목 feedback을 보지 못했다: %s" % missing)
    acc = next(e for e in s.mission.events if e.goal_id == run.goal_id and e.status == sj.STATUS_ACCEPTED)
    reached = sj.first_reached(raw.pos, z0, TAKEOFF_M, ACCEPTANCE_M, after_recv_us=t_goal)
    seq, seq_ts = sj.sequence_findings(raw.status, t_goal)

    for name, val in (("accepted", acc.stamp_us), ("takeoff_start", fb_take.stamp_us), ("reached", reached),
                      ("loiter_start", fb_loiter.stamp_us), ("land_start", fb_land.stamp_us),
                      ("armed", seq_ts.get("armed_ts")), ("auto_land", seq_ts.get("land_ts")),
                      ("disarmed", seq_ts.get("disarmed_ts")), ("result", run.result.recv_us)):
        s.mark("A", name, val)
    findings = list(seq)
    findings += sj.milestones_ordered([
        ("goal_sent", t_goal), ("accepted", acc.stamp_us), ("armed", seq_ts.get("armed_ts")),
        ("takeoff_start", fb_take.stamp_us), ("reached", reached), ("land_start", fb_land.stamp_us),
        ("auto_land", seq_ts.get("land_ts")), ("disarmed", seq_ts.get("disarmed_ts")),
        ("result", run.result.recv_us)])
    if fb_loiter.stamp_us < fb_take.stamp_us:
        findings.append((sw.WRONG_RESULT, "LOITER가 TAKEOFF보다 먼저 시작했다"))
    held = (fb_land.stamp_us - fb_loiter.stamp_us) / US
    if held < 5.0 - 1e-3:
        findings.append((sw.WRONG_RESULT, "LOITER 유지 시간 %.3f s < 5 s" % held))
    loiter_recv = fb_loiter.recv_us
    land_recv = fb_land.recv_us
    findings += sj.altitude_hold_findings(raw.pos, loiter_recv, land_recv, z0 - TAKEOFF_M)
    s.record_hold_deviation("A_loiter", sj.altitude_max_deviation(raw.pos, loiter_recv, land_recv, z0 - TAKEOFF_M))
    findings += sj.flight_window_findings(raw.status, fb_take.stamp_us, fb_land.stamp_us)
    # ULog 교차 확인(crosscheck_a.py)이 비행 구간의 끝으로 쓴다
    armed.update(land_start_recv_us=fb_land.recv_us, land_start_stamp_us=fb_land.stamp_us)
    (s.out_dir / "armed_a.json").write_text(json.dumps(armed, indent=1, sort_keys=True) + "\n", encoding="ascii")
    s.trace.event("scenario_a_findings", findings=[list(f) for f in findings], held_s=held)
    sw.raise_if(findings)


@pytest.mark.scenario("D")
def test_d_cancel_in_air_then_land_only_mission(session):
    """고도 도달 뒤 cancel: CANCELED와 REASON_NONE, AUTO_LOITER 3회 연속, 일정 시간 고도 유지.
    이어서 [LAND] 한 항목 미션: SUCCEEDED와 DISARMED."""
    s = session
    raw = s.raw
    try:
        _scenario_d(s, raw)
    except BaseException:
        s.emergency_cleanup()
        raise


def _scenario_d(s, raw):
    s.require_ground_disarmed("D")
    z0 = s.z_ref()
    t_goal = raw.now_us()
    mission = [takeoff_item(), loiter_item(30.0, 40.0), land_item()]
    run = send(s, s.vehicle_id, "d-takeoff-cancel", mission)
    s.waiter.wait_until(
        lambda: sj.first_reached(raw.pos, z0, TAKEOFF_M, ACCEPTANCE_M, after_recv_us=t_goal) is not None,
        60.0, "D 고도 도달")
    t_cancel = raw.now_us()
    code = s.mission.cancel(s.waiter, run)
    s.trace.event("cancel_sent", at_us=t_cancel, return_code=code)
    if code != 0:
        raise sw.SitlFailure(sw.WRONG_RESULT, "cancel 응답 return_code %d(0이 아니다)" % code)
    s.mission.wait_result(s.waiter, run, 30.0, "D cancel result")
    check_goal(s, run, terminal_status=sj.STATUS_CANCELED, reason=sj.REASON_NONE)

    findings, hit = sj.cancel_hover_findings(raw.status, t_cancel)
    sw.raise_if(findings)
    ref_z = raw.last_pos()[3]
    t_hold0 = raw.now_us()
    s.waiter.hold_for(sj.HOVER_HOLD_S, "D 고도 유지")
    hold = sj.altitude_hold_findings(raw.pos, t_hold0, raw.now_us(), ref_z)
    s.record_hold_deviation("D_hover", sj.altitude_max_deviation(raw.pos, t_hold0, raw.now_us(), ref_z))
    last = raw.last_status()
    if last.arming_state != mj.ARMING_STATE_ARMED:
        hold.append((sw.WRONG_RESULT, "취소 뒤 유지 구간에서 기체가 ARMED가 아니다"))
    if any(x.landed for x in raw.landed if x.recv_ros_us > t_hold0):
        hold.append((sw.WRONG_RESULT, "취소 뒤 유지 구간에서 landed가 true였다"))
    s.trace.event("cancel_hover", confirmed_ts=hit.ts_us, ref_z=ref_z, findings=[list(f) for f in hold])
    sw.raise_if(hold)

    t_goal2 = raw.now_us()
    run2 = send(s, s.vehicle_id, "d-land-only", [land_item()])
    s.mission.wait_result(s.waiter, run2, 60.0, "D [LAND] result")
    s.waiter.hold_for(1.0, "D 표본 수신 여유")
    check_goal(s, run2, terminal_status=sj.STATUS_SUCCEEDED, reason=sj.REASON_NONE, items_completed=1)
    seq, seq_ts = sj.sequence_findings(raw.status, t_goal2)
    s.trace.event("d_land_sequence", findings=[list(f) for f in seq], **seq_ts)
    sw.raise_if(seq)
    s.waiter.wait_until(lambda: raw.last_landed().landed, 5.0, "D [LAND] 뒤 landed true")


@pytest.mark.scenario("T")
def test_t_stale_offboard_timestamp(session):
    """지상, 비행 없음, Executor idle. offboard_control_mode(position=true)를 20 Hz로 발행한다.
    timestamp가 현재이면 offboard_control_signal_lost false, now - 2 s이면 true, 다시 현재이면 false."""
    from tests.support.px4_raw import OffboardSignal

    s = session
    raw = s.raw
    s.require_ground_disarmed("T")
    t0 = raw.now_us()
    with OffboardSignal(raw, s.waiter) as sig:
        for lag, want_lost in ((0.0, False), (2.0, True), (0.0, False)):
            sig.lag_s = lag
            t = raw.now_us()
            s.trace.event("t_phase", lag_s=lag, want_lost=want_lost, at_us=t)
            s.waiter.wait_until(lambda: sj.flag_phase_confirmed(raw.flags, t, want_lost), 5.0,
                                "T 신호 손실 %s %d회 연속(timestamp lag %.0f s)" % (want_lost, sj.N_CONSECUTIVE, lag))
        s.trace.event("t_published", count=sig.published)
    sw.raise_if(sj.never_armed_findings(raw.status, t0, raw.now_us()))
