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

"""미션 통합 테스트: 시나리오 B, C, A, D, F1, F2, F3, F4, T(1a decisions.md 쟁점 9, 1b decisions.md 쟁점 15).
한 스택에서 이 순서로 돈다. 실행 목록(conftest의 IDSIM_SITL_SCENARIOS)에 없는 시나리오는 수집에서 빠진다.

판정 시간은 모두 ROS 시각이다. 계약 판정의 입력은 토픽에서만 읽는다(goal의 목표값과 vehicle_local_position,
vehicle_status, vehicle_land_detected, failsafe_flags, mission_event, action의 feedback과 result, TargetState).
노드가 낸 setpoint는 입력으로 쓰지 않는다. 1b 비행 시나리오(F1-F4)는 여기에 정답 판정(SITL 전용 정답 pose)을
더한다. 판정 함수는 tests/support/sitl_judge.py(순수 코드)에 있다.
각 시나리오 시작 전에 사전조건(지상, DISARMED N회 연속. F3은 공중 Hold)을 단정하고 어긋나면 그 자리에서 실패한다.
비행 시나리오(A, D, F1-F4)가 실패하면 정리용 [LAND]를 한 번 시도하고(판정에 넣지 않는다) 뒤의 비행 시나리오는
UPSTREAM_FAILED로 실패한다(flight()).
"""
import json
from contextlib import contextmanager

import pytest

from tests.support import measure_judge as mj
from tests.support import sitl_judge as sj
from tests.support import sitl_missions as sm
from tests.support import sitl_wait as sw

RESULT_WAIT_S = 90.0         # goal 결과 대기(ROS 시각)
US = 1_000_000

takeoff_item = sm.takeoff_item
loiter_item = sm.loiter_item
land_item = sm.land_item
TAKEOFF_M = sm.TAKEOFF_M
ACCEPTANCE_M = sm.ACCEPTANCE_M


def _accepted(s, run, mission_id, n_items):
    s.last_run = run
    s.trace.event("goal_sent", mission_id=mission_id, vehicle_id=run.vehicle_id_sent, accepted=run.accepted,
                  goal_id=run.goal_id, items=n_items)
    if not run.accepted:
        raise sw.SitlFailure(sw.WRONG_RESULT, "goal %s이 수락되지 않았다(즉시 ABORTED가 아니라 거절)" % mission_id)
    return run


def send(s, vehicle_id, mission_id, items):
    """goal을 보내 수락 응답까지 받는다. 수락하지 않으면 WRONG_RESULT(받는 쪽은 판단할 수 있는 goal을 모두 수락한다)."""
    return _accepted(s, s.mission.send_goal(s.waiter, vehicle_id, mission_id, items), mission_id, len(items))


def send_spec(s, spec):
    """미션 YAML을 로더로 읽은 MissionSpec을 보낸다(F1-F4)."""
    return _accepted(s, s.mission.send_spec(s.waiter, s.vehicle_id, spec), spec.mission_id, len(spec.items))


def goal_findings(s, run, *, terminal_status, reason, items_completed=None, vehicle_id=None, feedback_zero=False):
    """result, 사건 짝, (선택) feedback 0건의 판정 결과(목록)."""
    s.settle_events(run)
    own = vehicle_id or s.vehicle_id
    findings = sj.check_result(run.result, terminal_status, reason, items_completed)
    findings += sj.check_event_pair(
        s.mission.events, goal_id=run.goal_id, vehicle_id=own, mission_id=run.mission_id,
        item_count=run.item_count, terminal_status=terminal_status, result=run.result)
    if feedback_zero:
        findings += sj.check_no_feedback(s.mission.feedbacks, run.goal_id)
    s.trace.event("goal_checked", mission_id=run.mission_id, findings=[list(f) for f in findings])
    return findings


def check_goal(s, run, **kw):
    """goal_findings를 판정해 실패면 바로 올린다."""
    sw.raise_if(goal_findings(s, run, **kw))


def _category(exc):
    return exc.category if isinstance(exc, sw.SitlFailure) else "ERROR"


@contextmanager
def flight(s, sid):
    """비행 시나리오 한 번(1b decisions.md 쟁점 15). 앞 비행 시나리오가 실패했으면 실행하지 않고 UPSTREAM_FAILED다.
    실패하면 정리용 [LAND]를 한 번 시도하고(판정에 넣지 않는다) 뒤의 비행 시나리오를 막는다."""
    s.flights.check_upstream(sid)
    try:
        yield
    except BaseException as e:
        s.flights.fail(sid, _category(e))
        s.trace.event("flight_failed", scenario=sid, category=_category(e))
        s.cleanup_land()
        raise
    s.flights.passed(sid)


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
    """1b 무효 사례(sitl_missions.B_INVALID_CASES)를 순서대로 하나씩 보낸다. 사례마다 ABORTED, INVALID_MISSION,
    접수와 종료 사건, feedback 0건, detail의 기대 조각(의도한 검사에서 거부됐는가).
    첫 goal 전송부터 끝까지 한 구간에서 ARMED 표본 없음(끝에 일정 ROS 시간 유지).
    거부가 아닌 결과(feedback, ARMED, 다른 result)가 나오면 그 사례에서 바로 실패하고 goal 취소와 비상 정리를 한다."""
    s = session
    s.require_ground_disarmed("B")
    t0 = s.raw.now_us()

    def not_armed(floor=0):
        # 폴링 중에는 구간이 비어 있을 수 있으므로 표본 수 하한을 보지 않고, 끝에서 한 번 하한과 함께 본다
        sw.raise_if(sj.never_armed_findings(s.raw.status, t0, s.raw.now_us(), min_samples=floor))

    run = None
    try:
        for mission_id, rule, fragment, items in sm.B_INVALID_CASES:
            run = send(s, s.vehicle_id, mission_id, items)
            # result를 기다리되 feedback이나 ARMED가 먼저 오면 기다리지 않는다(거부가 아니면 바로 실패)
            s.waiter.wait_until(lambda r=run: r.result is not None or r.feedbacks
                                or sj.never_armed_findings(s.raw.status, t0, s.raw.now_us(), min_samples=0),
                                30.0, "B result %s" % mission_id)
            s.trace.event("b_case", mission_id=mission_id, rule=rule,
                          detail=run.result.detail if run.result is not None else None)
            check_goal(s, run, terminal_status=sj.STATUS_ABORTED, reason=sj.REASON_INVALID_MISSION, feedback_zero=True)
            sw.raise_if(sj.detail_findings(run.result, fragment))
            not_armed()
        s.waiter.hold_for(sj.DISARMED_HOLD_S, "B disarmed 유지", check=not_armed)
        not_armed(sj.MIN_STATUS_SAMPLES)
    except BaseException:
        try:
            if run is not None and run.handle is not None and run.result is None:
                s.mission.cancel(s.waiter, run)
        except Exception as e:                                   # B의 원래 실패를 가리지 않는다
            s.trace.event("b_cancel_failed", error=repr(e))
        finally:
            s.emergency_cleanup()
        raise


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

    def not_armed(floor=0):
        # 폴링 중에는 구간이 비어 있을 수 있으므로 표본 수 하한을 보지 않고, 끝에서 한 번 하한과 함께 본다
        sw.raise_if(sj.never_armed_findings(s.raw.status, t0, s.raw.now_us(), min_samples=floor))

    s.waiter.hold_for(sj.DISARMED_HOLD_S, "C disarmed 유지", check=not_armed)
    not_armed(sj.MIN_STATUS_SAMPLES)


def _record_armed_a(s, t_goal, run):
    """goal 전송부터 TAKEOFF 시작(feedback PHASE_EXECUTING의 stamp)까지의 ARMED 표본 기록과 회차 요약 필드.

    vehicle_status 원시 표본(KEEP_ALL 기록기)에서 센다. 노드의 tick 모델과 무관하다. 구간은 PX4 timestamp 축이다.
    TAKEOFF 시작을 보지 못한 실행은 지금까지를 구간으로 잡는다(그때 A는 이미 실패했다).
    구간 경계는 Executor stamp이고 PX4 hrt는 노드 ROS 시각보다 8-20 ms 크므로(docs/interface.md) 끝 경계
    end가 PX4 축에서 이르게 잡혀 TAKEOFF 직전 수십 ms의 ARMED 표본이 빠질 수 있다. 생길 수 있는 것은
    오탐이 아니라 미탐(armed_non_offboard 과소 집계, armed3_reached 거짓 false)이고, 여유가 약 1 s라
    위험이 작다. armed3_reached는 armed_criterion 집계에만 쓰이고 시나리오 판정에는 쓰이지 않는다.
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
    with flight(session, "A"):
        _scenario_a(session)


def _scenario_a(s):
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
    # 순서 비교는 모두 이 테스트 노드의 ROS 시계(수신 시각)로 한다. Executor stamp(accepted, feedback)와 PX4
    # timestamp는 다른 시계라 노드 사이에서 /clock 한 step(4 ms)까지 어긋나므로 섞지 않는다. 위 표의 값은 stamp다
    findings += sj.milestones_ordered([
        ("goal_sent", t_goal), ("accepted", acc.recv_us), ("armed", seq_ts.get("armed_recv_us")),
        ("takeoff_start", fb_take.recv_us), ("reached", reached), ("land_start", fb_land.recv_us),
        ("auto_land", seq_ts.get("land_recv_us")), ("disarmed", seq_ts.get("disarmed_recv_us")),
        ("result", run.result.recv_us)])
    if fb_loiter.stamp_us < fb_take.stamp_us:
        findings.append((sw.WRONG_RESULT, "LOITER가 TAKEOFF보다 먼저 시작했다"))
    held = (fb_land.stamp_us - fb_loiter.stamp_us) / US
    # feedback stamp와 Executor의 5 s 계시는 모두 tick 입력 시각(TickInput.now_ns) 기준이라 유지 시간은 정확히 5 s다
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
    with flight(s, "D"):
        t_start = raw.now_us()
        try:
            _scenario_d(s, raw)
        except BaseException:
            try:
                s.dump_raw_status("raw_status_D.jsonl", t_start)     # 실패 원인 분석용(ULog 대조)
            except Exception as e:                                   # D의 원래 실패를 가리지 않는다
                s.trace.event("dump_raw_status_failed", error=repr(e))
            raise


def _wait_d_reached(s, raw, run, z0, t_goal):
    """D의 고도 도달 대기. 도달 전에 goal result가 오면 기다리지 않고 실패시키고, 못 닿으면 원인 설명을 붙인다."""
    def reached():
        return sj.first_reached(raw.pos, z0, TAKEOFF_M, ACCEPTANCE_M, after_recv_us=t_goal) is not None

    try:
        s.waiter.wait_until(lambda: reached() or run.result is not None, 60.0, "D 고도 도달")
    except sw.SitlFailure as e:
        desc = sj.unreached_description(run.result, s.mission.feedbacks_of(run), raw.last_status())
        raise sw.SitlFailure(e.category, "%s (%s)" % (e.message, desc)) from e
    if not reached():
        raise sw.SitlFailure(sw.WRONG_RESULT, "D 고도 도달 전에 goal이 끝났다 (%s)" % sj.unreached_description(
            run.result, s.mission.feedbacks_of(run), raw.last_status()))


def _scenario_d(s, raw):
    s.require_ground_disarmed("D")
    z0 = s.z_ref()
    t_goal = raw.now_us()
    mission = [takeoff_item(), loiter_item(30.0, 40.0), land_item()]
    run = send(s, s.vehicle_id, "d-takeoff-cancel", mission)
    _wait_d_reached(s, raw, run, z0, t_goal)
    t_cancel = raw.now_us()
    code = s.mission.cancel(s.waiter, run)
    s.trace.event("cancel_sent", at_us=t_cancel, return_code=code)
    if code != 0:
        raise sw.SitlFailure(sw.WRONG_RESULT, "cancel 응답 return_code %d(0이 아니다)" % code)
    s.mission.wait_result(s.waiter, run, 30.0, "D cancel result")
    check_goal(s, run, terminal_status=sj.STATUS_CANCELED, reason=sj.REASON_NONE)

    # 표본이 늦게 도착할 수 있으므로 기준(AUTO_LOITER 3회 연속)은 그대로 두고 도착을 기다린다
    s.waiter.wait_until(lambda: not sj.cancel_hover_findings(raw.status, t_cancel)[0], 10.0,
                        "D 취소 뒤 AUTO_LOITER %d회 연속" % sj.N_CONSECUTIVE)
    findings, hit = sj.cancel_hover_findings(raw.status, t_cancel)
    sw.raise_if(findings)
    ref_z = raw.last_pos()[3]
    t_hold0 = raw.now_us()
    s.waiter.hold_for(sj.HOVER_HOLD_S, "D 고도 유지")
    t_hold1 = raw.now_us()
    hold = sj.altitude_hold_findings(raw.pos, t_hold0, t_hold1, ref_z)
    s.record_hold_deviation("D_hover", sj.altitude_max_deviation(raw.pos, t_hold0, t_hold1, ref_z))
    hold += sj.hover_state_findings(raw.status, raw.landed, t_hold0, t_hold1)
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


# ---------------------------------------------------------------------------
# 1b 비행 시나리오 F1-F4(1b decisions.md 쟁점 5, 15). 미션은 tests/sitl/missions/의 YAML(로더 형식)이다.

FLIGHT_SAMPLE_WAIT_S = 1.0        # result 뒤 늦게 도착하는 표본(vehicle_status, 정답 pose)을 기다리는 ROS 시각
HOLD_CONFIRM_WAIT_S = 10.0        # 공중 종료 뒤 AUTO_LOITER 3회 연속을 기다리는 상한(D의 취소 뒤와 같다)
TYPE_NAMES = {sj.TYPE_TAKEOFF: "TAKEOFF", sj.TYPE_GOTO: "GOTO", sj.TYPE_TRACK_ENTITY: "TRACK_ENTITY",
              sj.TYPE_LOITER: "LOITER", sj.TYPE_RTL: "RTL", sj.TYPE_LAND: "LAND"}


def _ekf_near(raw, t_us):
    """t에 가장 가까이 받은 vehicle_local_position(NED 로컬). S1-b 기록용(정답과 EKF를 나중에 대조한다)."""
    if not raw.pos:
        return None
    p = min(raw.pos, key=lambda p: abs(p[0] - t_us))
    return {"recv_us": p[0], "x": p[1], "y": p[2], "z": p[3], "xy_valid": p[5], "z_valid": p[6]}


def _target_age_at(samples, t_us):
    """t까지 받은 표적 표본 가운데 최신 stamp의 나이(s). TRACK_ENTITY 시작 때의 묵은 표본 기록용."""
    xs = [x for x in samples if x.recv_us <= t_us]
    return None if not xs else round((t_us - max(x.stamp_us for x in xs)) / sj.US, 4)


def _oracle_events(s, sid, spec, fbs, tf):
    """GOTO와 TRACK_ENTITY 완료마다 정답 판정을 하고 R2 기록을 trace에 남긴다. 반환 findings."""
    truth, raw = s.truth, s.raw
    out = []
    for i, it in enumerate(spec.items):
        if it.type not in (sj.TYPE_GOTO, sj.TYPE_TRACK_ENTITY):
            continue
        if i not in tf:
            out.append((sw.WRONG_RESULT, "항목 %d의 완료 시각 t_f를 feedback에서 읽지 못했다" % i))
            continue
        t_f, exact, lo = tf[i]
        if it.type == sj.TYPE_GOTO:
            f, rec = sj.reach_judge(truth.oracle, t_f, it.position, it.acceptance_radius_m)
        else:
            fb0 = sj.first_item_feedback(fbs, i)
            start = fb0.stamp_us if fb0 is not None else t_f
            targets = truth.targets.get(it.target_id, [])
            v = sj.target_speed_max([t for t in s.stack.targets if t["id"] == it.target_id])
            f, rec = sj.track_judge(truth.oracle, targets, start, t_f, it.offset, it.acceptance_radius_m, v)
            rec.update(tracking=sj.tracking_errors(truth.oracle, targets, it.offset, start, t_f),
                       stale_ticks=sj.stale_ticks(targets, start, t_f),
                       target_age_at_start_s=_target_age_at(targets, start), target_id=it.target_id)
        rec.update(scenario=sid, index=i, type=TYPE_NAMES[it.type], t_f_exact=exact, t_f_lo_us=lo,
                   ekf=_ekf_near(raw, t_f), findings=[list(x) for x in f])
        s.r2.append(rec)
        s.trace.event("reach" if it.type == sj.TYPE_GOTO else "track", **rec)
        out += f
    return out


def _landed_disarmed(s, sid, spec, run, t_goal, rtl):
    """LANDED_DISARMED 종료의 계약 판정(ARMED -> AUTO_LAND 또는 AUTO_RTL -> DISARMED 3회, landed)과 착륙 정답 판정."""
    raw = s.raw
    mode = sj.NAV_STATE_AUTO_RTL if rtl else mj.NAV_STATE_AUTO_LAND
    contract, seq_ts = sj.sequence_findings(raw.status, t_goal, mode_nav=mode)
    # 이륙 전의 landed 표본으로 vacuous하게 통과하지 않게 착륙 모드 표본 뒤에 받은 것만 센다
    if not sj.landed_confirmed(raw.landed, seq_ts.get("land_recv_us", raw.now_us())):
        contract.append((sw.WRONG_RESULT, "착륙 뒤 landed %d회 연속을 보지 못했다" % sj.N_CONSECUTIVE))
    s.trace.event("%s_land_sequence" % sid, findings=[list(f) for f in contract], **seq_ts)
    oracle = []
    if "land_ts" in seq_ts and "disarmed_ts" in seq_ts:
        first = next(x for x in raw.status if x.ts_us > seq_ts["land_ts"] and mj.is_disarmed(x))
        s.waiter.wait_until(lambda: raw.clock_us() >= first.ts_us + int(sj.ORACLE_MAX_GAP_S * sj.US) + 20_000,
                            5.0, "%s 정답 표본(DISARMED 뒤)" % sid)
        oracle, rec = sj.landing_judge(s.truth.oracle, first.ts_us, s.flights.ref, rtl)
        rec.update(scenario=sid, ref_sid=s.flights.ref_sid, findings=[list(x) for x in oracle])
        if rtl:
            fb_rtl = sj.first_item_feedback(s.mission.feedbacks_of(run), len(spec.items) - 1)
            landed_ts = next((x.ts_us for x in raw.landed if x.ts_us > seq_ts["land_ts"] and x.landed), None)
            start = fb_rtl.stamp_us if fb_rtl else None
            rec["rtl_timing_s"] = {k: (None if v is None or start is None else round((v - start) / sj.US, 3))
                                   for k, v in (("auto_rtl", seq_ts["land_ts"]), ("touchdown", landed_ts),
                                                ("disarmed", first.ts_us), ("disarm_confirmed", seq_ts["disarmed_ts"]))}
        s.r4.append(rec)
        s.trace.event("landing", **rec)
    return contract, oracle


def _hold_airborne(s, sid, tf_last_lo, t_goal):
    """HOLD_AIRBORNE 종료의 계약 판정: 마지막 항목 완료 뒤 AUTO_LOITER 3회 연속, 그 뒤 일정 ROS 시간 ARMED,
    landed false, 고도 유지. Hold 확인까지의 소요와 상태 구간을 trace에 남긴다(F2 trace)."""
    raw = s.raw
    after = tf_last_lo if tf_last_lo is not None else t_goal
    s.waiter.wait_or_timeout(lambda: not sj.cancel_hover_findings(raw.status, after)[0], HOLD_CONFIRM_WAIT_S,
                             "%s 공중 종료 뒤 AUTO_LOITER %d회 연속" % (sid, sj.N_CONSECUTIVE))
    findings, hit = sj.cancel_hover_findings(raw.status, after)
    if findings:
        return findings
    ref_z = raw.last_pos()[3]
    t0 = raw.now_us()
    s.waiter.hold_for(sj.HOVER_HOLD_S, "%s Hold 유지" % sid)
    t1 = raw.now_us()
    findings = sj.altitude_hold_findings(raw.pos, t0, t1, ref_z)
    findings += sj.hover_state_findings(raw.status, raw.landed, t0, t1)
    s.trace.event("hold_end", scenario=sid, hold_confirm_s=round((hit.recv_ros_us - after) / sj.US, 3),
                  max_dev_m=sj.altitude_max_deviation(raw.pos, t0, t1, ref_z),
                  nav_runs=sj.nav_runs(raw.status, after, raw.now_us()),
                  findings=[list(f) for f in findings])
    return findings


def _air_start_record(s, sid, run, t_goal):
    """공중 시작 구간(goal 전송부터 첫 항목 실행 시작까지)의 기록(F3 trace). DO_SET_MODE 전송 수와 D는 ULog에서
    trace_1b.py가 낸다."""
    raw, fbs = s.raw, s.mission.feedbacks_of(run)
    exe = next((f for f in sorted(fbs, key=lambda f: f.stamp_us) if f.phase == sj.PHASE_EXECUTING), None)
    prep = next((f for f in sorted(fbs, key=lambda f: f.stamp_us) if f.phase == sj.PHASE_PREPARING), None)
    end = exe.stamp_us if exe else raw.now_us()
    o0, o1 = sj.oracle_before(s.truth.oracle, t_goal), sj.oracle_before(s.truth.oracle, end)
    first_off = next((x for x in raw.status if x.ts_us >= t_goal and x.nav_state == mj.NAV_STATE_OFFBOARD), None)
    non_off_after = [x.ts_us for x in raw.status if first_off and first_off.ts_us < x.ts_us <= end
                     and x.nav_state != mj.NAV_STATE_OFFBOARD]
    s.trace.event("air_start", scenario=sid, goal_sent_us=t_goal, preparing_us=prep.stamp_us if prep else None,
                  executing_us=exe.stamp_us if exe else None,
                  preparing_s=None if not (prep and exe) else round((exe.stamp_us - prep.stamp_us) / sj.US, 3),
                  displacement_m=None if not (o0 and o1) else round(sj.distance_parts(
                      (o1.x, o1.y, o1.z), (o0.x, o0.y, o0.z))[0], 4),
                  first_offboard_ts=first_off.ts_us if first_off else None, non_offboard_after_first=non_off_after,
                  nav_runs=sj.nav_runs(raw.status, t_goal, end), status_interval_s=sj.status_intervals_s(
                      raw.status, t_goal, end))


def _fly(s, sid):
    spec = sm.load_flight(sid)
    terminal = sm.FLIGHT_TERMINAL[sid]
    types = [it.type for it in spec.items]
    rtl = types[-1] == sj.TYPE_RTL
    raw = s.raw
    s.require_truth(sid, sorted({it.target_id for it in spec.items if it.type == sj.TYPE_TRACK_ENTITY}))
    prev = sm.AIR_START.get(sid)
    if prev is None:
        s.require_ground_disarmed(sid)
        ref = sj.oracle_before(s.truth.oracle, raw.now_us())
        if ref is None:
            raise sw.SitlFailure(sw.ORACLE_ABSENT, "%s 이륙 직전 정답 표본이 없다" % sid)
        s.flights.set_ref(sid, (ref.x, ref.y, ref.z))
    else:
        s.flights.inherited_ref(sid, prev)
        s.require_air_hold(sid)
    s.trace.event("flight_ref", scenario=sid, ref=list(s.flights.ref), ref_sid=s.flights.ref_sid)
    s.record_r1()
    t_goal = raw.now_us()
    s.mark(sid, "goal_sent", t_goal)
    run = send_spec(s, spec)
    s.mission.wait_result(s.waiter, run, sm.flight_wait_s(spec), "%s result" % sid)
    s.waiter.hold_for(FLIGHT_SAMPLE_WAIT_S, "%s 표본 수신 여유" % sid)

    fbs = s.mission.feedbacks_of(run)
    tf = sj.item_completion_times(fbs, len(types))
    starts = {i: f.stamp_us for i in range(len(types)) for f in [sj.first_item_feedback(fbs, i)] if f is not None}
    s.trace.event("flight_window", scenario=sid, mission_id=spec.mission_id, goal_sent_us=t_goal,
                  types=[TYPE_NAMES[t] for t in types], item_start_us=starts,
                  t_f={i: list(v) for i, v in tf.items()}, result_recv_us=run.result.recv_us if run.result else None)
    if prev is not None:
        _air_start_record(s, sid, run, t_goal)
    if run.result is not None and run.result.reason == sj.REASON_TARGET_LOST:
        # TRACK_ENTITY 시작 때 묵은 표본으로 setpoint가 바뀐 뒤 TARGET_LOST까지의 이동량(progress의 B11 trace 항목)
        i = run.result.last_item_index
        o0 = sj.oracle_before(s.truth.oracle, starts.get(i, t_goal))
        o1 = sj.oracle_before(s.truth.oracle, run.result.recv_us)
        s.trace.event("target_lost_motion", scenario=sid, index=i, displacement_m=None if not (o0 and o1) else round(
            sj.distance_parts((o1.x, o1.y, o1.z), (o0.x, o0.y, o0.z))[0], 4))

    # 계약 판정
    contract = goal_findings(s, run, terminal_status=sj.STATUS_SUCCEEDED, reason=sj.REASON_NONE,
                             items_completed=len(types))
    contract += sj.item_order_findings(fbs, types, run.result.items_completed if run.result else 0)
    oracle = []
    if terminal == sj.TERMINAL_LANDED_DISARMED:
        c, oracle = _landed_disarmed(s, sid, spec, run, t_goal, rtl)
        contract += c
    else:
        last = tf.get(len(types) - 1)
        contract += _hold_airborne(s, sid, last[2] if last else None, t_goal)
    # 정답 판정. /clock이 마지막 t_f + 0.1 s를 지난 뒤 판정한다(뒤 표본이 아직 오지 않은 것을 STALE로 세지 않게)
    if tf:
        t_last = max(v[0] for v in tf.values())
        s.waiter.wait_until(lambda: raw.clock_us() >= t_last + int(sj.ORACLE_MAX_GAP_S * sj.US) + 20_000, 5.0,
                            "%s 정답 표본(t_f 뒤)" % sid)
    oracle = _oracle_events(s, sid, spec, fbs, tf) + oracle
    s.trace.event("flight_findings", scenario=sid, contract=[list(f) for f in contract],
                  oracle=[list(f) for f in oracle])
    sw.raise_if(contract + oracle)


@pytest.mark.scenario("F1")
def test_f1_waypoints_land(session):
    """[TAKEOFF 5 m, GOTO x 3, LAND]: waypoint 도달(정답 판정), 항목 순서, 착륙 후 disarm. b의 표본(R2)."""
    with flight(session, "F1"):
        _fly(session, "F1")


@pytest.mark.scenario("F2")
def test_f2_track_hold_airborne(session):
    """[TAKEOFF, GOTO, TRACK_ENTITY]: 표적 접근, 공중 종료의 SUCCEEDED와 Hold(HOLD_AIRBORNE). 기체를 공중 Hold로 남긴다."""
    with flight(session, "F2"):
        _fly(session, "F2")


@pytest.mark.scenario("F3")
def test_f3_air_start_rtl(session):
    """[GOTO, RTL]: F2가 남긴 Hold에서 공중 시작, RTL 완료(착륙 위치, disarm). R_home의 표본(R4)."""
    with flight(session, "F3"):
        _fly(session, "F3")


@pytest.mark.scenario("F4")
def test_f4_combined(session):
    """합친 미션 [TAKEOFF 5 m, GOTO x 2, TRACK_ENTITY, RTL]: 도달, 표적 접근, RTL 착륙 위치(R4), 착륙 후 disarm."""
    with flight(session, "F4"):
        _fly(session, "F4")


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
