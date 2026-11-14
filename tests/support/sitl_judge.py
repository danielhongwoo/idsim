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

"""SITL 시나리오의 판정 함수(순수 코드. rclpy 없음). 라이브와 리플레이가 같은 코드를 쓴다.

입력은 기록 객체(EventRec, FeedbackRec, ResultRec)와 measure_judge의 표본(StatusSample, LandedSample), Px4Raw.pos의
튜플이다. 함수는 (분류, 설명) 목록을 돌려주고 비어 있으면 통과다. 예외를 올리지 않는다(올리는 것은
sitl_wait.raise_if). 판정 기준을 느슨하게 바꾸려면 근거와 함께 architect에게 올린다(decisions.md 쟁점 9).

기준 상수(허용 오차, N)는 decisions.md 쟁점 9가 정한 값이다. 이 파일에서 새로 정한 것은 아래 표시한 셋이다.
  HOVER_HOLD_TOL_M(0.5 m), HOVER_HOLD_S(5 s), DISARMED_HOLD_S(5 s). 값의 근거와 다시 보는 조건은 decisions.md
  쟁점 9에 있다(HOVER_HOLD_S는 Land로 내려가면 약 1.1 s에 0.5 m를 넘고 5 s 안에 3 m 넘게 내려간다는 ULog 실측).
  유지 구간의 최대 편차는 통과한 회에도 기록되고 note 임계값(sitl_summary.HOLD_DEV_NOTE_M)을 넘으면 note가 붙는다.
"""
from dataclasses import dataclass

from tests.support import measure_judge as mj
from tests.support import sitl_wait as sw

US = 1_000_000

# MissionEvent.status(= action_msgs/GoalStatus)
STATUS_ACCEPTED = 1
STATUS_SUCCEEDED = 4
STATUS_CANCELED = 5
STATUS_ABORTED = 6

# ExecuteMission.Result.reason
REASON_NONE = 0
REASON_INVALID_MISSION = 1
REASON_VEHICLE_ID_MISMATCH = 2

# ExecuteMission.Feedback.phase / MissionItem.type. 생성 코드 상수와 같은지는 test_sitl_constants.py가 고정한다
PHASE_PREPARING = 1
PHASE_EXECUTING = 2
TYPE_TAKEOFF = 1
TYPE_LOITER = 4
TYPE_LAND = 6

N_CONSECUTIVE = 3                # decisions.md 쟁점 9: N은 3(메시지 수)
CLOCK_ALIGN_MEDIAN_S = 0.1       # 쟁점 9: /clock 정렬
CLOCK_ALIGN_MAX_S = 0.5
CLOCK_ALIGN_MIN_SAMPLES = 5
HOVER_HOLD_TOL_M = 0.5           # 새로 정한 값. D의 "일정 시간 고도 유지"의 허용 하강량
HOVER_HOLD_S = 5.0               # 새로 정한 값. D의 유지 시간(ROS 시각)
DISARMED_HOLD_S = 5.0            # 새로 정한 값. B와 C의 "일정 ROS 시간 동안 disarmed 유지"


@dataclass(frozen=True)
class EventRec:
    recv_us: int
    stamp_us: int
    vehicle_id: str
    mission_id: str
    goal_id: str            # 16바이트의 16진 문자열
    status: int
    reason: int
    item_count: int
    items_completed: int
    last_item_index: int
    detail: str


@dataclass(frozen=True)
class FeedbackRec:
    recv_us: int
    goal_id: str
    stamp_us: int
    item_index: int
    item_count: int
    item_type: int
    phase: int


@dataclass(frozen=True)
class ResultRec:
    recv_us: int
    status: int             # GoalStatus
    reason: int
    items_completed: int
    last_item_index: int
    detail: str


@dataclass(frozen=True)
class FlagSample:
    """failsafe_flags 표본(offboard_control_signal_lost만)."""
    ts_us: int
    recv_ros_us: int
    lost: bool


STATUS_NAMES = {STATUS_ACCEPTED: "ACCEPTED", STATUS_SUCCEEDED: "SUCCEEDED", STATUS_CANCELED: "CANCELED",
                STATUS_ABORTED: "ABORTED"}


def _name(status):
    return STATUS_NAMES.get(status, str(status))


# ---------------------------------------------------------------------------
# result, 사건, feedback


def check_result(result, status, reason, items_completed=None):
    f = []
    if result is None:
        return [(sw.WRONG_RESULT, "result를 받지 못했다")]
    if result.status != status:
        f.append((sw.WRONG_RESULT, "result 상태 %s, 기대 %s" % (_name(result.status), _name(status))))
    if result.reason != reason:
        f.append((sw.WRONG_RESULT, "result reason %d, 기대 %d(detail: %s)" % (result.reason, reason, result.detail)))
    if items_completed is not None and result.items_completed != items_completed:
        f.append((sw.WRONG_RESULT, "items_completed %d, 기대 %d" % (result.items_completed, items_completed)))
    return f


def check_no_feedback(feedbacks, goal_id):
    mine = [x for x in feedbacks if x.goal_id == goal_id]
    if mine:
        return [(sw.WRONG_RESULT, "feedback이 %d건 왔다(0건이어야 한다): 첫 phase %d" % (len(mine), mine[0].phase))]
    return []


def check_event_pair(events, *, goal_id, vehicle_id, mission_id, item_count, terminal_status, result):
    """접수 사건 하나와 종료 사건 하나의 짝, 그리고 종료 사건 == result.

    events: 이 세션에서 받은 MissionEvent 전부. goal_id가 다른 사건은 보지 않는다(앞 goal의 사건).
    """
    mine = [e for e in events if e.goal_id == goal_id]
    acc = [e for e in mine if e.status == STATUS_ACCEPTED]
    term = [e for e in mine if e.status != STATUS_ACCEPTED]
    f = []
    if not acc:
        f.append((sw.EVENT_MISSING, "ACCEPTED 사건을 받지 못했다"))
    if not term:
        f.append((sw.EVENT_MISSING, "종료 사건을 받지 못했다"))
    if f:
        return f
    if len(acc) != 1 or len(term) != 1:
        return [(sw.EVENT_MISMATCH, "사건 수가 이상하다: ACCEPTED %d건, 종료 %d건" % (len(acc), len(term)))]
    a, t = acc[0], term[0]
    if a.recv_us > t.recv_us:
        f.append((sw.EVENT_MISMATCH, "ACCEPTED가 종료 사건보다 늦게 도착했다"))
    if a.stamp_us > t.stamp_us:
        f.append((sw.EVENT_MISMATCH, "사건 stamp가 거꾸로다(ACCEPTED %d > 종료 %d)" % (a.stamp_us, t.stamp_us)))
    for e, label in ((a, "ACCEPTED"), (t, "종료")):
        if e.vehicle_id != vehicle_id:
            f.append((sw.EVENT_MISMATCH, "%s 사건의 vehicle_id %r, Executor 자신의 값 %r이어야 한다"
                      % (label, e.vehicle_id, vehicle_id)))
        if e.mission_id != mission_id:
            f.append((sw.EVENT_MISMATCH, "%s 사건의 mission_id %r, 기대 %r" % (label, e.mission_id, mission_id)))
        if e.item_count != item_count:
            f.append((sw.EVENT_MISMATCH, "%s 사건의 item_count %d, 기대 %d" % (label, e.item_count, item_count)))
    if (a.reason, a.items_completed, a.last_item_index, a.detail) != (REASON_NONE, 0, 0, ""):
        f.append((sw.EVENT_MISMATCH, "ACCEPTED 사건의 reason/items_completed/last_item_index/detail이 "
                  "(0, 0, 0, '')이 아니다: %r" % ((a.reason, a.items_completed, a.last_item_index, a.detail),)))
    if t.status != terminal_status:
        f.append((sw.EVENT_MISMATCH, "종료 사건 상태 %s, 기대 %s" % (_name(t.status), _name(terminal_status))))
    if result is not None:
        got = (t.status, t.reason, t.items_completed, t.last_item_index, t.detail)
        want = (result.status, result.reason, result.items_completed, result.last_item_index, result.detail)
        if got != want:
            f.append((sw.EVENT_MISMATCH, "종료 사건 %r이 result %r와 다르다" % (got, want)))
    return f


# ---------------------------------------------------------------------------
# 사전조건


def clock_alignment_findings(status_samples):
    """use_sim_time 노드 시각 - vehicle_status.timestamp의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s."""
    if len(status_samples) < CLOCK_ALIGN_MIN_SAMPLES:
        return [(sw.PRECONDITION, "/clock 정렬을 볼 vehicle_status 표본이 %d개뿐이다(최소 %d)"
                 % (len(status_samples), CLOCK_ALIGN_MIN_SAMPLES))]
    d = sorted(abs(s.recv_ros_us - s.ts_us) / US for s in status_samples)
    med = d[len(d) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) / 2
    f = []
    if not med < CLOCK_ALIGN_MEDIAN_S:
        f.append((sw.PRECONDITION, "/clock 정렬: 중앙값 %.3f s(기준 < %.1f s)" % (med, CLOCK_ALIGN_MEDIAN_S)))
    if not d[-1] < CLOCK_ALIGN_MAX_S:
        f.append((sw.PRECONDITION, "/clock 정렬: 최대 %.3f s(기준 < %.1f s)" % (d[-1], CLOCK_ALIGN_MAX_S)))
    return f


def disarmed_confirmed(status_samples, after_recv_us=0, n=N_CONSECUTIVE):
    """after_recv_us 뒤에 받은 vehicle_status에서 DISARMED가 서로 다른 timestamp로 n회 연속인가."""
    c = mj.ConsecutiveConfirm(mj.is_disarmed, n=n, min_recv_us=after_recv_us)
    return any(c.feed(s) for s in status_samples)


def landed_confirmed(landed_samples, after_recv_us=0, n=N_CONSECUTIVE):
    """after_recv_us 뒤에 받은 vehicle_land_detected의 landed가 n회 연속 true인가(메시지 수)."""
    cnt = 0
    for s in landed_samples:
        if s.recv_ros_us <= after_recv_us:
            continue
        cnt = cnt + 1 if s.landed else 0
        if cnt >= n:
            return True
    return False


def flag_phase_confirmed(flags, after_recv_us, want_lost, n=N_CONSECUTIVE):
    """after_recv_us 뒤 failsafe_flags 표본에서 offboard_control_signal_lost == want_lost가 n회 연속인가.
    failsafe_flags는 5 Hz 상한이므로 서로 다른 timestamp의 표본으로 센다."""
    c = mj.ConsecutiveConfirm(lambda s: s.lost == want_lost, n=n, min_recv_us=after_recv_us)
    return any(c.feed(s) for s in flags)


# ---------------------------------------------------------------------------
# 이륙과 고도


def height_above(z_ned, z0_ned):
    """NED z(아래가 +)에서 기준 z0 위로의 높이(m)."""
    return z0_ned - z_ned


def reached_height(z_ned, z0_ned, height_m, acceptance_m):
    """goal의 목표 높이에 허용 오차 안으로 도달했는가. 입력은 vehicle_local_position이고 노드의 setpoint가 아니다."""
    return abs(height_above(z_ned, z0_ned) - height_m) <= acceptance_m


def first_reached(pos, z0_ned, height_m, acceptance_m, after_recv_us=0):
    """도달한 첫 표본의 수신 시각(us). pos는 Px4Raw.pos 튜플(recv, x, y, z, heading, xy_valid, z_valid)."""
    for p in pos:
        if p[0] > after_recv_us and p[6] and reached_height(p[3], z0_ned, height_m, acceptance_m):
            return p[0]
    return None


def altitude_max_deviation(pos, from_us, to_us, ref_z_ned):
    """[from_us, to_us] 안의 z_valid 표본이 기준 고도에서 벗어난 최대량(m). 표본이 없으면 None.
    통과한 회에도 남겨 판정 상수(HOVER_HOLD_TOL_M) 재검토의 근거로 쓴다."""
    inside = [abs(p[3] - ref_z_ned) for p in pos if from_us <= p[0] <= to_us and p[6]]
    return max(inside) if inside else None


def altitude_hold_findings(pos, from_us, to_us, ref_z_ned, tol_m=HOVER_HOLD_TOL_M):
    """[from_us, to_us] 안의 모든 표본이 ref 고도에서 tol_m 안인가. 표본이 없으면 실패."""
    inside = [p for p in pos if from_us <= p[0] <= to_us and p[6]]
    if not inside:
        return [(sw.WRONG_RESULT, "고도 유지 구간에 vehicle_local_position 표본이 없다")]
    worst = max(abs(p[3] - ref_z_ned) for p in inside)
    if worst > tol_m:
        return [(sw.WRONG_RESULT, "고도 유지 실패: 기준에서 최대 %.2f m 벗어났다(허용 %.2f m)" % (worst, tol_m))]
    return []


# ---------------------------------------------------------------------------
# 시나리오 A의 상태 판정


def armed_window(status, from_us, to_us):
    """from_us(arm 전송 이전의 goal 전송 시각)부터 to_us(TAKEOFF 시작 feedback의 stamp)까지의 ARMED 표본.

    PX4 timestamp 축으로 구간을 자른다(표본의 순서와 간격은 수신 시각이 아니라 timestamp로 읽는다).
    DISARMED 표본은 세지 않으므로 arm 전송 시각이 아니라 goal 전송 시각을 from으로 써도 개수가 같다.
    """
    n_armed, bad = mj.armed_non_offboard(status, from_us, to_us, time_of="ts")
    return {
        "armed_samples": n_armed,
        "armed_non_offboard": len(bad),
        "armed_non_offboard_samples": [
            {"ts_us": b.ts_us, "recv_ros_us": b.recv_ros_us, "nav_state": b.nav_state,
             "failsafe": b.failsafe, "intention": b.intention} for b in bad],
    }


def flight_window_findings(status, from_us, to_us):
    """TAKEOFF와 LOITER 동안(PX4 timestamp 기준 [from_us, to_us]) failsafe가 한 번도 true가 아니고 OFFBOARD인가."""
    inside = [s for s in status if from_us <= s.ts_us <= to_us]
    if not inside:
        return [(sw.WRONG_RESULT, "비행 구간에 vehicle_status 표본이 없다")]
    f = []
    fs = [s for s in inside if s.failsafe]
    if fs:
        f.append((sw.WRONG_RESULT, "비행 중 failsafe가 true인 표본이 %d개다(첫 표본 timestamp %d, nav_state %d)"
                  % (len(fs), fs[0].ts_us, fs[0].nav_state)))
    off = [s for s in inside if s.nav_state != mj.NAV_STATE_OFFBOARD]
    if off:
        f.append((sw.WRONG_RESULT, "TAKEOFF와 LOITER 중 OFFBOARD가 아닌 표본이 %d개다(첫 표본 timestamp %d, nav_state %d)"
                  % (len(off), off[0].ts_us, off[0].nav_state)))
    return f


def milestones_ordered(milestones):
    """[(이름, ROS 시각 us), ...]가 순서대로 줄어들지 않는가. 값이 None인 항목은 없는 것으로 보고 실패시킨다.

    모든 값은 같은 시계(ROS /clock)여야 한다. PX4 timestamp와 ROS 수신 시각은 /clock이 한 step(4 ms)까지
    늦을 수 있어 섞어 비교하면 정상 순서가 뒤집혀 보인다(docs/interface.md "시간 기준"). 허용 오차는 두지 않는다.
    PX4 표본의 이정표는 sequence_findings가 돌려주는 *_recv_us(수신 ROS 시각)를 쓴다.
    """
    f = []
    prev_name, prev = None, None
    for name, t in milestones:
        if t is None:
            f.append((sw.WRONG_RESULT, "이정표 %s가 관측되지 않았다" % name))
            continue
        if prev is not None and t < prev:
            f.append((sw.WRONG_RESULT, "이정표 순서 위반: %s(%d us)가 %s(%d us)보다 앞이다" % (name, t, prev_name, prev)))
        prev_name, prev = name, t
    return f


def sequence_findings(status, armed_after_us):
    """ARMED -> AUTO_LAND -> DISARMED의 순서(상태 표본의 timestamp 기준).

    ARMED를 본 뒤의 DISARMED여야 한다(시작 때 이미 DISARMED라 순서를 보지 않으면 vacuous하다).
    반환: (findings, {armed_ts, land_ts, disarmed_ts, armed_recv_us, land_recv_us, disarmed_recv_us}).
    *_ts는 PX4 timestamp(표 기록용), *_recv_us는 그 표본의 수신 ROS 시각이다. 다른 시계의 이정표와 순서를
    비교할 때는 *_recv_us를 쓴다. disarmed는 DISARMED 3회 연속을 확인한 표본이다.
    """
    armed = next((s for s in status if s.recv_ros_us > armed_after_us and mj.is_armed(s)), None)
    if armed is None:
        return [(sw.WRONG_RESULT, "ARMED 표본을 보지 못했다")], {}
    land = next((s for s in status if s.ts_us > armed.ts_us and s.nav_state == mj.NAV_STATE_AUTO_LAND), None)
    if land is None:
        return [(sw.WRONG_RESULT, "ARMED 뒤 AUTO_LAND를 보지 못했다")], {"armed_ts": armed.ts_us, "armed_recv_us": armed.recv_ros_us}
    c = mj.ConsecutiveConfirm(mj.is_disarmed, n=N_CONSECUTIVE, min_ts_us=land.ts_us)
    done = next((s for s in status if c.feed(s)), None)
    if done is None:
        return [(sw.WRONG_RESULT, "AUTO_LAND 뒤 DISARMED %d회 연속을 보지 못했다" % N_CONSECUTIVE)], \
            {"armed_ts": armed.ts_us, "land_ts": land.ts_us,
             "armed_recv_us": armed.recv_ros_us, "land_recv_us": land.recv_ros_us}
    return [], {"armed_ts": armed.ts_us, "land_ts": land.ts_us, "disarmed_ts": c.confirmed_at.ts_us,
                "armed_recv_us": armed.recv_ros_us, "land_recv_us": land.recv_ros_us,
                "disarmed_recv_us": c.confirmed_at.recv_ros_us}


def unreached_description(goal_result, feedbacks, last_status):
    """목표 고도에 닿지 못한 실패의 설명(원인 좁히기용). 판정은 하지 않는다.

    goal_result: ResultRec 또는 None. feedbacks: 이 goal의 FeedbackRec 목록. last_status: 마지막 vehicle_status 표본 또는 None.
    """
    parts = []
    if goal_result is None:
        parts.append("goal result 없음")
    else:
        parts.append("goal result status=%s reason=%d detail=%r" % (_name(goal_result.status), goal_result.reason,
                                                                  goal_result.detail))
    if feedbacks:
        fb = feedbacks[-1]
        parts.append("마지막 feedback item=%d phase=%d" % (fb.item_index, fb.phase))
    else:
        parts.append("feedback 없음")
    if last_status is None:
        parts.append("vehicle_status 없음")
    else:
        parts.append("마지막 vehicle_status arming_state=%d nav_state=%d failsafe=%s"
                     % (last_status.arming_state, last_status.nav_state, last_status.failsafe))
    return "; ".join(parts)


# 구간 안 표본 수 하한. "표본이 없어서 ARMED가 없다"는 통과가 아니다(vacuous 방지). 하한은 N_CONSECUTIVE(3)다:
# 구간은 5 s(ROS 시각)이고 vehicle_status는 최소 2 Hz([소스] 상태가 바뀌면 즉시, 아니면 주기 발행)라 10개 안팎이
# 오는데, 한 번의 유실과 늦은 도착을 견디면서 "구간을 덮었다"고 볼 최소치로 3을 둔다. vehicle_land_detected는
# 값이 바뀔 때와 1 Hz로만 나오므로([실측] measure_judge) 5 s 구간의 하한을 2로 둔다.
MIN_STATUS_SAMPLES = N_CONSECUTIVE
MIN_LANDED_SAMPLES = 2


def never_armed_findings(status, from_us, to_us, min_samples=MIN_STATUS_SAMPLES):
    """[from_us, to_us] 동안(수신 ROS 시각) ARMED 표본이 하나도 없는가(B, C, T의 "기체에 손대지 않음").
    구간 안의 vehicle_status가 min_samples개 미만이면 판정하지 못한 것이므로 실패다."""
    inside = [s for s in status if from_us <= s.recv_ros_us <= to_us]
    if len(inside) < min_samples:
        return [(sw.WRONG_RESULT, "ARMED 없음을 판정할 vehicle_status 표본이 %d개뿐이다(최소 %d)"
                 % (len(inside), min_samples))]
    armed = [s for s in inside if mj.is_armed(s)]
    if armed:
        return [(sw.WRONG_RESULT, "ARMED 표본이 %d개 나왔다(첫 표본 수신 %d us). 이 goal은 기체에 손대면 안 된다"
                 % (len(armed), armed[0].recv_ros_us))]
    return []


def hover_state_findings(status, landed, from_us, to_us):
    """D의 취소 뒤 유지 구간 전체에서 ARMED이고 landed가 false인가(수신 ROS 시각). 표본 수 하한을 둔다."""
    st = [s for s in status if from_us <= s.recv_ros_us <= to_us]
    ld = [x for x in landed if from_us <= x.recv_ros_us <= to_us]
    f = []
    if len(st) < MIN_STATUS_SAMPLES:
        f.append((sw.WRONG_RESULT, "유지 구간의 vehicle_status 표본이 %d개뿐이다(최소 %d)" % (len(st), MIN_STATUS_SAMPLES)))
    elif not all(mj.is_armed(s) for s in st):
        f.append((sw.WRONG_RESULT, "유지 구간에 ARMED가 아닌 vehicle_status 표본이 있다"))
    if len(ld) < MIN_LANDED_SAMPLES:
        f.append((sw.WRONG_RESULT, "유지 구간의 vehicle_land_detected 표본이 %d개뿐이다(최소 %d)" % (len(ld), MIN_LANDED_SAMPLES)))
    elif any(x.landed for x in ld):
        f.append((sw.WRONG_RESULT, "유지 구간에 landed가 true인 표본이 있다"))
    return f


def cancel_hover_findings(status, after_recv_us):
    """공중 취소 뒤 AUTO_LOITER 3회 연속(서로 다른 timestamp)을 보았는가. 반환: (findings, 확인한 세 번째 표본 또는 None)."""
    c = mj.ConsecutiveConfirm(lambda s: s.nav_state == mj.NAV_STATE_AUTO_LOITER, n=N_CONSECUTIVE,
                              min_recv_us=after_recv_us)
    hit = next((s for s in status if c.feed(s)), None)
    if hit is None:
        return [(sw.WRONG_RESULT, "취소 뒤 AUTO_LOITER %d회 연속을 보지 못했다" % N_CONSECUTIVE)], None
    return [], hit
