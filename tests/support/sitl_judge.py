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

1b 판정(1b decisions.md 쟁점 5, 15)은 두 부분으로 나눈다. 함수 수준에서 섞지 않는다.
  계약 판정: 계약 토픽과 PX4 토픽(mission_event, feedback, result, vehicle_status, vehicle_land_detected,
    vehicle_local_position, TargetState)만 쓴다. 이 파일의 "계약 판정" 절.
  정답 판정: SITL 전용 정답 pose(/sim/<vehicle_id>/pose)를 쓴다. 이 파일의 "정답 판정" 절. 정답 pose가 있어야 하는
    실행에서 없으면 ORACLE_ABSENT로 실패하고 조용히 건너뛰지 않는다. 테스트는 원점 변환을 다시 구현하지 않는다.

1b 판정 상수(정한 곳은 1b decisions.md 쟁점 5)
  R_JUDGE_M 1.0 m: waypoint와 TRACK_ENTITY 완료의 판정 반경(U14). t_f(Executor가 항목을 완료로 넘긴 tick의 stamp)에서
    정답 pose와 목표의 3차원 거리가 이 안이어야 한다(아니면 REACH_MISMATCH).
  B_M, R_HOME_M: 비어 있다(None). 두 상수가 빈 상태가 보정 상태이고 따로 스위치나 환경 변수를 두지 않는다.
    보정 상태에서 바뀌는 것은 R_HOME_M에 기대는 RTL 착륙 수평 위치 단정 하나이고 R4 값과 함께 recorded_only로
    남긴다. 나머지 판정은 그대로 실패로 센다. 시험 미션의 acceptance_radius_m은 보정 값 CALIBRATION_ACCEPTANCE_M
    (0.5 m)이다. 값은 로컬 부팅 30회 이상의 R2, R4에서 정하고 근거(부팅 수, 사건 수, mean(s), std(s), 최댓값,
    s_track 통계, k, Shapiro-Wilk p, 실행 id)와 함께 이 머리말에 적는다(README의 두 커밋 절차의 (나)).
  L_S 0.2 s = target_fresh_age 0.1 s + Executor tick 0.05 s + 여유 0.05 s. 표적 접근의 임계값은 R_JUDGE_M + v x L_S이고
    v는 시나리오 표적 속도의 최댓값(stack.json targets의 구간 속도 최댓값)이다. L_S는 TRACK_ENTITY의 속도 feedforward를
    전제로 하고, PX4가 setpoint를 반영하는 지연을 약 한 tick으로 본 것은 [추정]이다(F2, F4 trace의 R3로 확인한다).
    노드의 target_fresh_age는 gate가 Executor 파라미터를 읽어 TARGET_FRESH_AGE_S와 대조한다.
  ORACLE_MAX_GAP_S 0.1 s: t_f를 감싸는 정답 표본 둘의 간격 상한. 넘으면 ORACLE_STALE.
  LAND_Z_TOL_M 0.3 m: 착륙 뒤 DISARMED 시점의 정답 z가 그 비행의 이륙 직전 정답 z + 이 값 안.
  M_EVENTS 9, M_HOME 2: b와 R_HOME_M을 쓰는 사건 수(GOTO와 TRACK_ENTITY 완료, RTL). 시나리오에서 파생된 값이고
    test_sitl_flight_missions.py가 시나리오 미션과 대조한다. 시나리오를 바꾸면 k와 q x f를 다시 계산한다.
  NO_TARGET_MOTION_MIN_M 0.5 m: 새로 정한 값. TRACK_ENTITY 접근 구간(항목 시작부터 t_f)의 표적 이동 거리 하한.
    시나리오 표적은 1-2 m/s로 쉬지 않고 움직이고 접근은 1 s보다 길어서 정상이면 이 값을 크게 넘는다. 표적이 멈춘
    채 지나간 접근(표적 접근 판정이 vacuous한 경우)만 가른다.
"""
import bisect
import math
import re
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
REASON_TARGET_LOST = 10

# ExecuteMission.Feedback.phase / MissionItem.type. 생성 코드 상수와 같은지는 test_sitl_constants.py가 고정한다
PHASE_PREPARING = 1
PHASE_EXECUTING = 2
TYPE_TAKEOFF = 1
TYPE_GOTO = 2
TYPE_TRACK_ENTITY = 3
TYPE_LOITER = 4
TYPE_RTL = 5
TYPE_LAND = 6

N_CONSECUTIVE = 3                # decisions.md 쟁점 9: N은 3(메시지 수)
CLOCK_ALIGN_MEDIAN_S = 0.1       # 쟁점 9: /clock 정렬
CLOCK_ALIGN_MAX_S = 0.5
CLOCK_ALIGN_MIN_SAMPLES = 5
HOVER_HOLD_TOL_M = 0.5           # 새로 정한 값. D의 "일정 시간 고도 유지"의 허용 하강량
HOVER_HOLD_S = 5.0               # 새로 정한 값. D의 유지 시간(ROS 시각)
DISARMED_HOLD_S = 5.0            # 새로 정한 값. B와 C의 "일정 ROS 시간 동안 disarmed 유지"

# vehicle_status.nav_state(px4_msgs). measure_judge에 없는 것만. 생성 코드 상수와 같은지는 test_px4_topic_names.py가 고정한다
NAV_STATE_AUTO_RTL = 5

# 1b 판정 상수(머리말 참고)
R_JUDGE_M = 1.0
B_M = None                       # 보정 상태(비어 있음)
R_HOME_M = None                  # 보정 상태(비어 있음)
CALIBRATION_ACCEPTANCE_M = 0.5   # 보정 실행의 시험 미션 acceptance_radius_m
B_MAX_M = 0.5                    # b의 상한(넘으면 올린다)
B_WARN_M = 0.35                  # [추정] 경고선(넘으면 PR 본문에 적는다)
R_HOME_MAX_M = 1.0               # R_HOME_M의 상한(넘으면 올린다)
TARGET_FRESH_AGE_S = 0.1         # Executor 파라미터 target_fresh_age의 기대값(gate가 실행 중인 노드와 대조)
EXECUTOR_TICK_S = 0.05           # Executor tick(mission_executor_node.hpp kTickPeriodNs)
L_MARGIN_S = 0.05
L_S = 0.2                        # = TARGET_FRESH_AGE_S + EXECUTOR_TICK_S + L_MARGIN_S(단위 테스트가 대조)
ORACLE_MAX_GAP_S = 0.1
LAND_Z_TOL_M = 0.3
M_EVENTS = 9
M_HOME = 2
NO_TARGET_MOTION_MIN_M = 0.5     # 새로 정한 값(머리말)

# 종료 유형(1b decisions.md 쟁점 5). 판정은 이 값으로 매개변수화하고 SUCCEEDED => disarm을 가정하지 않는다
TERMINAL_LANDED_DISARMED = "LANDED_DISARMED"
TERMINAL_HOLD_AIRBORNE = "HOLD_AIRBORNE"


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
    distance_valid: bool = False
    distance_m: float = float("nan")


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


def detail_findings(result, fragment):
    """result.detail에 fragment가 들어 있는가. detail 문구는 계약이 아니다(무효 사례가 의도한 검사에서 걸렸는지 보는 용도)."""
    if result is None:
        return [(sw.WRONG_RESULT, "result를 받지 못했다")]
    if fragment not in result.detail:
        return [(sw.WRONG_RESULT, "result detail %r에 기대 조각 %r이 없다(다른 검사에서 거부됨)" % (result.detail, fragment))]
    return []


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
    """TAKEOFF와 LOITER 동안(PX4 timestamp 기준 [from_us, to_us]) failsafe가 한 번도 true가 아니고 OFFBOARD인가.

    구간 경계는 Executor의 stamp다. 같은 순간에 PX4 hrt는 노드 ROS 시각보다 8-20 ms 크므로
    (docs/interface.md) 경계는 PX4 축에서 실제보다 최대 수십 ms 이르다. 시작 쪽에 들어오는 표본은
    ARMED 확인 뒤의 OFFBOARD 표본이라 오탐이 되지 않고, 끝 쪽은 LAND 시작 직전 표본이 빠질 뿐이다.
    """
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


NAV_NAMES = {mj.NAV_STATE_AUTO_LAND: "AUTO_LAND", NAV_STATE_AUTO_RTL: "AUTO_RTL",
             mj.NAV_STATE_AUTO_LOITER: "AUTO_LOITER", mj.NAV_STATE_OFFBOARD: "OFFBOARD"}


def sequence_findings(status, armed_after_us, mode_nav=mj.NAV_STATE_AUTO_LAND):
    """ARMED -> mode_nav(기본 AUTO_LAND, RTL 항목이면 AUTO_RTL) -> DISARMED의 순서(상태 표본의 timestamp 기준).

    ARMED를 본 뒤의 DISARMED여야 한다(시작 때 이미 DISARMED라 순서를 보지 않으면 vacuous하다).
    반환: (findings, {armed_ts, land_ts, disarmed_ts, armed_recv_us, land_recv_us, disarmed_recv_us}).
    *_ts는 PX4 timestamp(표 기록용), *_recv_us는 그 표본의 수신 ROS 시각이다. 다른 시계의 이정표와 순서를
    비교할 때는 *_recv_us를 쓴다. disarmed는 DISARMED 3회 연속을 확인한 표본이다.
    """
    armed = next((s for s in status if s.recv_ros_us > armed_after_us and mj.is_armed(s)), None)
    if armed is None:
        return [(sw.WRONG_RESULT, "ARMED 표본을 보지 못했다")], {}
    mode = NAV_NAMES.get(mode_nav, str(mode_nav))
    land = next((s for s in status if s.ts_us > armed.ts_us and s.nav_state == mode_nav), None)
    if land is None:
        return [(sw.WRONG_RESULT, "ARMED 뒤 %s를 보지 못했다" % mode)], {"armed_ts": armed.ts_us, "armed_recv_us": armed.recv_ros_us}
    c = mj.ConsecutiveConfirm(mj.is_disarmed, n=N_CONSECUTIVE, min_ts_us=land.ts_us)
    done = next((s for s in status if c.feed(s)), None)
    if done is None:
        return [(sw.WRONG_RESULT, "%s 뒤 DISARMED %d회 연속을 보지 못했다" % (mode, N_CONSECUTIVE))], \
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


# ---------------------------------------------------------------------------
# 1b 계약 판정(계약 토픽과 PX4 토픽만. 정답 pose를 쓰지 않는다)


def item_completion_times(feedbacks, item_count):
    """항목마다 Executor가 완료로 넘긴 시각 t_f를 feedback에서 읽는다. 반환 {index: (t_f_us, exact, lo_us)}.

    feedbacks: 이 goal의 FeedbackRec. 노드는 phase나 항목이 바뀐 tick에 바로, 그 밖에는 0.5 s마다 feedback을 낸다.
    - 마지막이 아닌 항목 i: 항목 i + 1의 첫 feedback stamp. 항목이 바뀐 tick의 입력 시각이므로 완료 tick 그 자체다
      (exact True, lo_us = t_f_us).
    - 마지막 항목 i(공중 종료로 가는 setpoint 항목, F2의 TRACK_ENTITY): 완료 tick에 항목과 phase가 바뀌지 않아 바로
      나가는 feedback이 없다. 그 항목에서 distance_valid가 참인 마지막 feedback 뒤의 첫 distance_valid 거짓 feedback
      (종료 단계는 거리를 싣지 않는다)의 stamp를 t_f로 쓰고 exact False로 둔다. lo_us는 직전 참 feedback의 stamp이고
      참 완료 시각은 (lo_us, t_f_us] 안에 있고 그 폭은 최대 0.5 s다. 판정은 상한 쪽 t_f로 하고 기준(반경)은 바꾸지
      않는다. 노드가 종료 단계에 들어간 tick에 feedback을 내면 exact가 된다(ros2-engineer에게 요청할 사항).
    완료를 보지 못한 항목은 넣지 않는다.
    """
    fbs = sorted(feedbacks, key=lambda f: f.stamp_us)
    out = {}
    for i in range(item_count - 1):
        nxt = next((f for f in fbs if f.item_index == i + 1), None)
        if nxt is not None:
            out[i] = (nxt.stamp_us, True, nxt.stamp_us)
    last = item_count - 1
    mine = [f for f in fbs if f.item_index == last]
    valid = [k for k, f in enumerate(mine) if f.distance_valid]
    if valid and valid[-1] + 1 < len(mine):
        lo = mine[valid[-1]]
        hi = mine[valid[-1] + 1]
        out[last] = (hi.stamp_us, False, lo.stamp_us)
    return out


def item_order_findings(feedbacks, item_types, completed):
    """항목 순서(계약 판정). feedback의 item_index가 stamp 순으로 줄어들지 않고, item_type이 미션의 그 항목 type과
    같으며, item_count가 미션 길이이고, 완료한 항목(0..completed-1)과 끝 항목이 모두 한 번 이상 보였는가.

    item_types: 미션 항목의 MissionItem.TYPE_* 목록. completed: result.items_completed.
    """
    fbs = sorted(feedbacks, key=lambda f: f.stamp_us)
    f = []
    if not fbs:
        return [(sw.WRONG_RESULT, "feedback을 하나도 받지 못했다")]
    prev = -1
    for x in fbs:
        if x.item_count != len(item_types):
            f.append((sw.WRONG_RESULT, "feedback item_count %d, 미션 길이 %d" % (x.item_count, len(item_types))))
            break
        if x.item_index < prev:
            f.append((sw.WRONG_RESULT, "feedback item_index가 줄었다(%d -> %d)" % (prev, x.item_index)))
            break
        if x.item_index >= len(item_types) or x.item_type != item_types[x.item_index]:
            f.append((sw.WRONG_RESULT, "feedback item %d의 type %d, 미션은 %r" % (x.item_index, x.item_type,
                                                                              item_types[x.item_index:x.item_index + 1])))
            break
        prev = x.item_index
    seen = {x.item_index for x in fbs}
    want = set(range(min(completed, len(item_types))))
    missing = sorted(want - seen)
    if missing:
        f.append((sw.WRONG_RESULT, "완료한 항목 %s의 feedback을 보지 못했다" % missing))
    return f


def first_item_feedback(feedbacks, index):
    """항목 index의 첫 feedback(stamp 순). 없으면 None."""
    return next((f for f in sorted(feedbacks, key=lambda f: f.stamp_us) if f.item_index == index), None)


def nav_runs(status, from_us, to_us):
    """[from_us, to_us](PX4 timestamp) 안 표본의 (arming_state, nav_state) 연속 구간 [(arming, nav, 첫 ts, 표본 수)].
    trace 기록용(F2 끝의 Hold와 F3 진입 구간)."""
    out = []
    for s in status:
        if not from_us <= s.ts_us <= to_us:
            continue
        key = (s.arming_state, s.nav_state)
        if out and out[-1][:2] == key:
            out[-1][3] += 1
        else:
            out.append([key[0], key[1], s.ts_us, 1])
    return [tuple(r) for r in out]


def status_intervals_s(status, from_us, to_us):
    """구간 안 vehicle_status 표본의 timestamp 간격(s) 요약. trace 기록용."""
    ts = sorted({s.ts_us for s in status if from_us <= s.ts_us <= to_us})
    return summary([(b - a) / US for a, b in zip(ts, ts[1:])])


# ---------------------------------------------------------------------------
# 1b 정답 판정(SITL 전용 정답 pose /sim/<vehicle_id>/pose. decisions.md 쟁점 5)


@dataclass(frozen=True)
class OracleSample:
    """정답 pose 표본(geometry_msgs/PoseStamped). stamp는 Gazebo pose/info의 sim 시각, 위치는 world ENU의 base_link 원점."""
    stamp_us: int
    recv_us: int
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class TargetSample:
    """TargetState 표본. stamp는 그 상태가 유효한 시각, 위치는 world ENU."""
    stamp_us: int
    recv_us: int
    x: float
    y: float
    z: float
    velocity_valid: bool = False
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0


# 정답 pose 토픽 이름. 발행하는 idsim_sim/scripts/sim_oracle.py와 각자 조립하고 공유 상수를 두지 않는다(쟁점 5).
# 같은 사례 표(test_sitl_oracle.py ORACLE_TOPIC_CASES, ORACLE_TOPIC_INVALID)로 양쪽이 따로 단위 테스트한다.
ORACLE_TOPIC_PREFIX = "/sim"
ORACLE_TOPIC_SUFFIX = "pose"
_VEHICLE_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def oracle_pose_topic(vehicle_id):
    """정답 pose 토픽의 절대 이름 /sim/<vehicle_id>/pose. vehicle_id가 ROS 이름 토큰 하나가 아니면 ValueError."""
    if not isinstance(vehicle_id, str) or _VEHICLE_ID_RE.fullmatch(vehicle_id) is None:
        raise ValueError("vehicle_id가 ROS 이름 토큰 하나가 아니다: %r" % (vehicle_id,))
    return "%s/%s/%s" % (ORACLE_TOPIC_PREFIX, vehicle_id, ORACLE_TOPIC_SUFFIX)


def _bracket(samples, t_us, keys=None):
    """stamp 오름차순으로 정렬한 표본에서 t를 감싸는 (앞, 뒤). stamp가 t와 같은 표본이 있으면 (그 표본, 그 표본).
    한쪽이 없으면 그 쪽이 None이다. 외삽하지 않는다. keys는 미리 만든 stamp 목록(여러 번 부를 때)."""
    if keys is None:
        keys = [x.stamp_us for x in samples]
    i = bisect.bisect_left(keys, t_us)
    if i < len(samples) and keys[i] == t_us:
        return samples[i], samples[i]
    before = samples[i - 1] if i > 0 else None
    after = samples[i] if i < len(samples) else None
    return before, after


def _lerp(a, b, t_us):
    if a.stamp_us == b.stamp_us:
        return (a.x, a.y, a.z)
    w = (t_us - a.stamp_us) / (b.stamp_us - a.stamp_us)
    return (a.x + w * (b.x - a.x), a.y + w * (b.y - a.y), a.z + w * (b.z - a.z))


def oracle_at(oracle, t_us, max_gap_s=ORACLE_MAX_GAP_S):
    """정답 위치를 t에서 앞뒤 표본으로 선형 보간한다. 반환 (findings, (x, y, z) 또는 None, 앞뒤 간격 s 또는 None).

    정답 표본이 하나도 없으면 ORACLE_ABSENT, t를 감싸는 표본이 없거나 앞뒤 간격이 max_gap_s를 넘으면 ORACLE_STALE.
    호출하는 쪽은 /clock이 t + max_gap_s를 지난 뒤 부른다(뒤 표본이 아직 오지 않은 것을 STALE로 세지 않게).
    """
    if not oracle:
        return [(sw.ORACLE_ABSENT, "정답 pose 표본이 하나도 없다")], None, None
    xs = sorted(oracle, key=lambda o: o.stamp_us)
    a, b = _bracket(xs, t_us)
    if a is None or b is None:
        return [(sw.ORACLE_STALE, "t=%d us를 감싸는 정답 표본이 없다(앞 %s, 뒤 %s)"
                 % (t_us, a.stamp_us if a else None, b.stamp_us if b else None))], None, None
    gap = (b.stamp_us - a.stamp_us) / US
    if gap > max_gap_s:
        return [(sw.ORACLE_STALE, "t=%d us를 감싸는 정답 표본 간격 %.3f s > %.1f s" % (t_us, gap, max_gap_s))], None, gap
    return [], _lerp(a, b, t_us), gap


def oracle_before(oracle, t_us):
    """stamp가 t 이하인 마지막 정답 표본(지상 정지 중의 기준점). 없으면 None."""
    xs = [o for o in oracle if o.stamp_us <= t_us]
    return max(xs, key=lambda o: o.stamp_us) if xs else None


def distance_parts(p, q):
    """(3차원 거리, 수평 거리, 수직 성분 p.z - q.z). p, q는 (x, y, z)."""
    dh = math.hypot(p[0] - q[0], p[1] - q[1])
    dv = p[2] - q[2]
    return math.hypot(dh, dv), dh, dv


def reach_judge(oracle, t_f_us, goal, acceptance_m, r_judge=R_JUDGE_M):
    """GOTO 도달의 정답 판정. t_f의 정답 위치와 world 목표의 3차원 거리가 r_judge 안인가(아니면 REACH_MISMATCH).

    반환 (findings, 기록). 기록은 trace의 R2 항목이다: t_f, d3, d_h, d_v, 정답 표본 간격, 부호 있는 초과량
    s = d3 - acceptance_m(0으로 자르지 않는다)와 보고용 max(0, s).
    """
    f, p, gap = oracle_at(oracle, t_f_us)
    rec = {"t_f_us": t_f_us, "goal": list(goal), "acceptance_m": acceptance_m, "gap_s": gap}
    if f:
        return f, rec
    d3, dh, dv = distance_parts(p, goal)
    s = d3 - acceptance_m
    rec.update(oracle=[round(v, 4) for v in p], d3=round(d3, 4), d_h=round(dh, 4), d_v=round(dv, 4),
               s=round(s, 4), s_pos=round(max(0.0, s), 4))
    if d3 > r_judge:
        return [(sw.REACH_MISMATCH, "t_f의 정답 거리 %.3f m > 판정 반경 %.2f m(수평 %.3f, 수직 %.3f)"
                 % (d3, r_judge, dh, dv))], rec
    return [], rec


def target_at(targets, t_us):
    """t를 감싸는 두 TargetState 표본에서 표적 위치를 선형 보간한다(외삽하지 않는다). 반환 ((x, y, z), 간격 s) 또는 (None, None)."""
    xs = sorted(targets, key=lambda x: x.stamp_us)
    a, b = _bracket(xs, t_us)
    if a is None or b is None:
        return None, None
    return _lerp(a, b, t_us), (b.stamp_us - a.stamp_us) / US


def target_travel_m(targets, from_us, to_us):
    """[from_us, to_us](stamp) 안 표적 표본이 첫 표본에서 가장 멀어진 거리(m). 표본이 둘 미만이면 0."""
    xs = sorted((x for x in targets if from_us <= x.stamp_us <= to_us), key=lambda x: x.stamp_us)
    if len(xs) < 2:
        return 0.0
    p0 = (xs[0].x, xs[0].y, xs[0].z)
    return max(distance_parts((x.x, x.y, x.z), p0)[0] for x in xs)


def track_judge(oracle, targets, start_us, t_f_us, offset, acceptance_m, v_max, l_s=L_S, r_judge=R_JUDGE_M):
    """TRACK_ENTITY 완료(표적 접근)의 정답 판정. 판정은 수신한 TargetState만 본다(정의에서 다시 계산하지 않는다).

    t_f의 정답 위치와 "t_f를 감싸는 두 TargetState에서 보간한 표적 위치 + offset"(Executor의 setpoint 점)의
    3차원 거리가 r_judge + v_max x l_s 안인가(아니면 REACH_MISMATCH). 항목 시작부터 t_f까지 표적이 움직였는가
    (아니면 NO_TARGET_MOTION). 기록은 s_track = d3 - acceptance_m - v_max x l_s(GOTO 표본에 섞지 않는다).
    """
    f, p, gap = oracle_at(oracle, t_f_us)
    thr = r_judge + v_max * l_s
    travel = target_travel_m(targets, start_us, t_f_us)
    rec = {"t_f_us": t_f_us, "start_us": start_us, "offset": list(offset), "acceptance_m": acceptance_m,
           "v_max": v_max, "l_s": l_s, "threshold_m": round(thr, 4), "gap_s": gap, "target_travel_m": round(travel, 3)}
    if travel < NO_TARGET_MOTION_MIN_M:
        f = f + [(sw.NO_TARGET_MOTION, "접근 구간에 표적이 %.3f m만 움직였다(하한 %.2f m)" % (travel, NO_TARGET_MOTION_MIN_M))]
    if p is None:
        return f, rec
    tgt, tgap = target_at(targets, t_f_us)
    if tgt is None:
        return f + [(sw.WRONG_RESULT, "t_f를 감싸는 TargetState 표본이 없다(외삽하지 않는다)")], rec
    aim = (tgt[0] + offset[0], tgt[1] + offset[1], tgt[2] + offset[2])
    d3, dh, dv = distance_parts(p, aim)
    s_track = d3 - acceptance_m - v_max * l_s
    rec.update(oracle=[round(v, 4) for v in p], target=[round(v, 4) for v in tgt], aim=[round(v, 4) for v in aim],
               target_gap_s=tgap, d3=round(d3, 4), d_h=round(dh, 4), d_v=round(dv, 4), s_track=round(s_track, 4))
    if d3 > thr:
        f = f + [(sw.REACH_MISMATCH, "TRACK_ENTITY t_f의 정답 거리 %.3f m > %.2f m + %.2f m/s x %.2f s(수평 %.3f, 수직 %.3f)"
                  % (d3, r_judge, v_max, l_s, dh, dv))]
    return f, rec


def tracking_errors(oracle, targets, offset, from_us, to_us):
    """[from_us, to_us]의 정답 표본 시각마다 표적을 보간한 setpoint 점까지의 거리(R3의 추종 오차, R5의 수직 성분). 기록 전용.
    표적 표본이 감싸지 않는 시각은 건너뛴다(외삽하지 않는다)."""
    xs = sorted(targets, key=lambda x: x.stamp_us)
    keys = [x.stamp_us for x in xs]
    d3s, dvs = [], []
    for o in oracle:
        if not from_us <= o.stamp_us <= to_us:
            continue
        a, b = _bracket(xs, o.stamp_us, keys)
        if a is None or b is None:
            continue
        t = _lerp(a, b, o.stamp_us)
        d3, _, dv = distance_parts((o.x, o.y, o.z), (t[0] + offset[0], t[1] + offset[1], t[2] + offset[2]))
        d3s.append(d3)
        dvs.append(dv)
    return {"d3": summary(d3s), "d_v": summary(dvs), "abs_d_v": summary([abs(v) for v in dvs])}


def target_speed_max(targets):
    """stack.json targets(각 {id, start_s, loop, waypoints[{t,x,y,z}]})의 구간 속도(3차원) 최댓값(m/s). 없으면 0."""
    v = 0.0
    for t in targets:
        wps = t["waypoints"]
        for a, b in zip(wps, wps[1:]):
            dt = b["t"] - a["t"]
            if dt > 0:
                v = max(v, math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) / dt)
    return v


def landing_judge(oracle, t_disarmed_us, ref, rtl, r_home=R_HOME_M, z_tol=LAND_Z_TOL_M):
    """착륙 후 disarm의 정답 판정. ref는 그 비행의 이륙 직전 정답 위치(x, y, z).

    DISARMED 시점의 정답 z가 ref z + z_tol 안인가(아니면 WRONG_RESULT). RTL이면 착륙 수평 위치와 ref의 거리 R4를
    재고, r_home이 정해져 있으면 그 안인가(아니면 WRONG_RESULT). r_home이 빈 보정 상태에서는 R4를 recorded_only로
    남기고 실패로 세지 않는다. 반환 (findings, 기록).
    """
    f, p, gap = oracle_at(oracle, t_disarmed_us)
    rec = {"t_disarmed_us": t_disarmed_us, "ref": [round(v, 4) for v in ref], "gap_s": gap, "rtl": bool(rtl)}
    if f:
        return f, rec
    dz = p[2] - ref[2]
    rec.update(landing=[round(v, 4) for v in p], dz=round(dz, 4))
    if dz > z_tol:
        f.append((sw.WRONG_RESULT, "DISARMED 시점의 정답 z가 이륙 직전보다 %.3f m 높다(허용 %.2f m)" % (dz, z_tol)))
    if rtl:
        r4 = math.hypot(p[0] - ref[0], p[1] - ref[1])
        rec["r4_m"] = round(r4, 4)
        if r_home is None:
            rec["r_home_status"] = "recorded_only"
        else:
            rec["r_home_status"] = "checked"
            rec["r_home_m"] = r_home
            if r4 > r_home:
                f.append((sw.WRONG_RESULT, "RTL 착륙 수평 위치가 이륙 직전 위치에서 %.3f m(R_home %.2f m)" % (r4, r_home)))
    return f, rec


# ---------------------------------------------------------------------------
# 기록(recorded_only) 도구


EARTH_RADIUS_M = 6371000.0


def r1_record(ref_lat, ref_lon, ref_alt, expect):
    """R1: EKF 원점(vehicle_local_position ref_lat, ref_lon, ref_alt)과 기대 스폰 GPS(stack.json expect_gps, base_link)의 차.
    기록 전용이다(b의 입력이 아니다). 수평은 반지름 6371 km 구면의 국소 평면 근사로 잰다(수 m 차에서 mm 아래 오차).
    판정에 쓰지 않으므로 "테스트는 원점 변환을 다시 구현하지 않는다"의 대상이 아니다."""
    lat0 = math.radians(expect["lat"])
    dn = math.radians(ref_lat - expect["lat"]) * EARTH_RADIUS_M
    de = math.radians(ref_lon - expect["lon"]) * EARTH_RADIUS_M * math.cos(lat0)
    return {"r1_h_m": round(math.hypot(dn, de), 4), "r1_v_m": round(ref_alt - expect["alt"], 4),
            "dn_m": round(dn, 4), "de_m": round(de, 4)}


def quantile(sorted_vals, q):
    """오름차순 목록의 q 분위수(nearest-rank). 비었으면 None."""
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, math.ceil(q * len(sorted_vals)) - 1))
    return sorted_vals[k]


def summary(values):
    """기록용 요약: n, mean, p50, p99, p999, max(값이 없으면 n 0과 None)."""
    v = sorted(values)
    if not v:
        return {"n": 0, "mean": None, "p50": None, "p99": None, "p999": None, "max": None}
    return {"n": len(v), "mean": round(sum(v) / len(v), 4), "p50": round(quantile(v, 0.5), 4),
            "p99": round(quantile(v, 0.99), 4), "p999": round(quantile(v, 0.999), 4), "max": round(v[-1], 4)}


def stale_ticks(targets, from_us, to_us, period_us=int(EXECUTOR_TICK_S * US), fresh_age_s=TARGET_FRESH_AGE_S):
    """R3의 신선하지 않은 tick: [from_us, to_us]를 Executor tick 주기 격자로 나눠 격자 시각마다 그때까지 받은
    (수신 시각 기준) 마지막 TargetState의 나이(격자 시각 - stamp)를 잰다. Executor의 tick이 아니라 이 테스트
    노드의 수신으로 본 근사다(기록 전용). 반환 {ticks, stale, ratio, stale_ages_s(앞 20개)}."""
    xs = sorted(targets, key=lambda x: x.recv_us)
    recv = [x.recv_us for x in xs]
    newest = []                      # 수신 순서로 i번째까지 받은 표본의 최신 stamp
    for x in xs:
        newest.append(max(x.stamp_us, newest[-1]) if newest else x.stamp_us)
    ticks = stale = 0
    ages = []
    t = from_us
    while t <= to_us:
        i = bisect.bisect_right(recv, t)
        ticks += 1
        age = None if i == 0 else (t - newest[i - 1]) / US
        if age is None or age > fresh_age_s:
            stale += 1
            if len(ages) < 20:
                ages.append(None if age is None else round(age, 4))
        t += period_us
    return {"ticks": ticks, "stale": stale, "ratio": (stale / ticks) if ticks else None, "stale_ages_s": ages}
