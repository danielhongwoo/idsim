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

"""PX4 재실측의 판정 로직. 표본 -> 통과 여부를 정하는 순수 코드(rclpy, 시계, 파일 입출력 없음).

tests/sitl/measure/measure.py(라이브)와 단위 테스트(tests/support/test_measure_judge.py)가
같은 함수를 쓴다. 시간은 모두 마이크로초 정수이고 sim 시간 축이다.

기준의 정본은 docs-for-agent/plan-1a-6-idsim-mission/decisions.md의 "넘김 목록" px4-engineer 행이다.
이 모듈의 상수는 그 문장을 옮긴 것이다. 기준을 바꾸려면 정본을 먼저 고친다(통과시키려고 느슨하게
바꾸지 않는다).

verdict와 종료 코드의 뜻
  PASS (0)               기준을 만족한 관측.
  FAIL (1)               기준과 다른 관측. 문서의 기대가 반증됐다는 뜻이며 PX4 결함이라는 뜻이 아니다.
  M3_CONTRADICTED (1)    2b에서 landed가 true에 닿음. M3 문장(Hold로 끝난 기체는 스스로 내려앉지 않는다)과
                         다른 관측이라 architect에게 올린다. disarm 수락과 고도 변화는 facts에 기록한다.
  그 밖 (2)              기계가 판정하지 않는다. COND_NOT_REACHED(조건에 닿지 못함: 2b에서 landed가
                         true에 닿지 않음), HOLD_END((3)이 전이 표에 있는 Hold 종료로 끝남), INCONCLUSIVE
                         (판정에 필요한 전제가 없음: 관찰 60 s 미만, arm 수락 증거 없음), WINDOW_MISSED,
                         PRECONDITION, ERROR, CLOCK_STALLED, 시도 수 부족, 인프라.
이 측정이 보증하는 범위는 PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, landed 전환, 상승)이다.
정리 총 소요 9 s 기준은 CleanupModel(측정용 모델)의 소요이고 core의 실제 소요를 보증하지 않는다.
"""
from dataclasses import dataclass, field

# px4_msgs/VehicleStatus 상수. measure.py가 시작할 때 px4_msgs 값과 같은지 대조한다.
ARMING_STATE_DISARMED = 1
ARMING_STATE_ARMED = 2
NAV_STATE_AUTO_LOITER = 4
NAV_STATE_OFFBOARD = 14
NAV_STATE_AUTO_LAND = 18

# 정리의 총 소요 통과 기준(s). 상한 12 s에 여유 3 s. 넘으면 상한을 올리지 않고 architect에게 올린다.
CLEANUP_LIMIT_S = 9.0
# 2b와 (3)의 Hold 종료 관찰 최소 시간(s). 이보다 짧으면 판정하지 않는다(INCONCLUSIVE).
OBSERVE_MIN_S = 60.0
# 관찰 판정에 필요한 표본 조건. 표본이 없는 관찰을 "상태 유지"로 읽지 않기 위한 하한이다.
# vehicle_status는 약 2 Hz(간격 0.5 s), vehicle_land_detected는 약 1 Hz(간격 1 s)로 나온다(trial4 실측).
OBSERVE_MAX_STATUS_AGE_S = 1.0      # 마지막 vehicle_status 표본이 관찰 끝에서 이 안이어야 한다
OBSERVE_MAX_LANDED_AGE_S = 2.0      # 마지막 vehicle_land_detected 표본도 같다
OBSERVE_MIN_STATUS_PER_S = 1.0      # 관찰 구간의 vehicle_status 표본 수 하한(초당)
OBSERVE_MIN_LANDED_PER_S = 0.5      # 관찰 구간의 vehicle_land_detected 표본 수 하한(초당)
# 이웃한 표본 사이의 최대 간격(s). 구간 가운데의 공백과 시작 가장자리를 함께 본다.
# 근거: PX4 v1.17.0 SITL, trial4/5 ULog 실측 중앙값 504 ms(vehicle_status)/1000 ms(vehicle_land_detected),
# 최대 508/1004 ms. PX4 버전을 올리면 다시 확인한다. PX4 timestamp 기준과 ROS 수신 시각 기준을 둘 다
# 계산하고 긴 쪽으로 판정한다(같은 timestamp 중복은 무시).
OBSERVE_MAX_STATUS_GAP_S = 2.0
OBSERVE_MAX_LANDED_GAP_S = 4.0

# 종료 코드 1로 읽는 verdict(기준과 다른 관측). M3_CONTRADICTED는 2b에서 landed가 true에 닿은 경우다.
EXIT1_VERDICTS = ("FAIL", "M3_CONTRADICTED")
# 자극이 성립하지 않아 시도 수에도 not-pass 집계에도 넣지 않는 verdict(행과 횟수는 기록하고 따로 적는다).
# WINDOW_MISSED는 (3)에서 취소 시점에 landed가 이미 false였던 회, ARM_NOT_ACCEPTED는 (5)에서 ULog 교차
# 확인 뒤에도 arm 수락 증거가 없는 회다(교차 확인 전의 live 행은 INCONCLUSIVE kind ARM_EVIDENCE로 2).
# 그 회에서 기준과 다른 관측(OFFBOARD가 아닌 ARMED 등)이 나오면 이 verdict가 아니라 FAIL이고 빼지 않는다.
EXCLUDED_VERDICTS = ("WINDOW_MISSED", "ARM_NOT_ACCEPTED")
# 시도 수로 세는 verdict. INCONCLUSIVE, COND_NOT_REACHED, HOLD_END, PRECONDITION 등은 기준에 대한
# 판정이 아니므로 세지 않고(not-pass로 집계해 종료 코드 2), EXCLUDED_VERDICTS는 세지도 집계하지도 않는다.
VALID_VERDICTS = ("PASS", "FAIL", "M3_CONTRADICTED")

# 아래 네 값(12, 3, 3, 0.5)은 idsim_mission의 노드 파라미터 기본값(core/config.hpp의 Timeouts:
# mode_confirm_timeout 3 s, hold_confirm_timeout 3 s, command_resend_period 0.5 s,
# 정리 상한 = hold_confirm_timeout + 3 x mode_confirm_timeout = 12 s)의 사본이다. 자동 동기화가
# 없다. config.hpp의 기본값이 바뀌면 여기도 고친다(측정 대상 기준이 어긋나지 않게).
CLEANUP_HARD_LIMIT_S = 12.0
MODE_CONFIRM_TIMEOUT_S = 3.0
HOLD_CONFIRM_TIMEOUT_S = 3.0
COMMAND_RESEND_S = 0.5
CONFIRM_SAMPLES = 3
# 상승 허용(m). (5)와 (2)의 "상승이 0.2 m 이하".
CLIMB_LIMIT_M = 0.2
# 지상 setpoint의 z offset(m, NED 아래쪽). decisions.md M5.
GROUND_SETPOINT_DZ_M = 0.5

US = 1_000_000


@dataclass(frozen=True)
class StatusSample:
    """vehicle_status 원시 표본 하나."""
    ts_us: int            # PX4 vehicle_status.timestamp
    recv_ros_us: int      # 받은 시점의 노드 ROS 시각(use_sim_time)
    clock_us: int         # 받은 시점에 마지막으로 본 /clock 메시지 값
    arming_state: int
    nav_state: int
    failsafe: bool
    intention: int        # nav_state_user_intention


@dataclass(frozen=True)
class LandedSample:
    """vehicle_land_detected 표본 하나."""
    ts_us: int
    recv_ros_us: int
    landed: bool


# ---------------------------------------------------------------------------
# 연속 N회 확인


class ConsecutiveConfirm:
    """서로 다른 timestamp의 표본 N개가 연속으로 predicate를 만족하는지 센다.

    decisions.md M5의 계수 규칙: 직전에 센 표본과 timestamp가 같으면 건너뛴다(더하지도 되돌리지도
    않는다). predicate를 만족하지 않는 표본은 계수를 0으로 되돌린다. timestamp가 줄어든 표본은
    세지 않는다. min_ts_us, min_recv_us가 있으면 timestamp가 min_ts_us보다 엄격히 크고 수신이
    min_recv_us보다 엄격히 뒤인 표본만 센다(전송 뒤에 받은 표본). 기준에 못 미친 표본은 계수에
    영향을 주지 않는다.
    """

    def __init__(self, predicate, n=CONFIRM_SAMPLES, min_ts_us=None, min_recv_us=None):
        self._pred = predicate
        self._n = n
        self._min_ts = min_ts_us
        self._min_recv = min_recv_us
        self._count = 0
        self._last_ts = None
        self.confirmed_at = None   # n번째 표본(StatusSample)

    @property
    def count(self):
        return self._count

    @property
    def done(self):
        return self.confirmed_at is not None

    def set_floor(self, min_ts_us, min_recv_us):
        """기준을 (처음 한 번만) 정한다. 이미 정했으면 바꾸지 않는다."""
        if self._min_ts is None and self._min_recv is None:
            self._min_ts = min_ts_us
            self._min_recv = min_recv_us

    def feed(self, s):
        if self.done:
            return True
        if self._min_ts is not None and not s.ts_us > self._min_ts:
            return False
        if self._min_recv is not None and not s.recv_ros_us > self._min_recv:
            return False
        if self._last_ts is not None:
            if s.ts_us == self._last_ts:
                return False
            if s.ts_us < self._last_ts:
                return False
        self._last_ts = s.ts_us
        if self._pred(s):
            self._count += 1
            if self._count >= self._n:
                self.confirmed_at = s
                return True
        else:
            self._count = 0
        return False


def is_armed(s):
    return s.arming_state == ARMING_STATE_ARMED


def is_disarmed(s):
    return s.arming_state == ARMING_STATE_DISARMED


def armed_confirm_sample(samples, after_recv_us, n=CONFIRM_SAMPLES):
    """after_recv_us 뒤에 받은 표본에서 ARMED n회 연속을 처음 채운 표본. 없으면 None."""
    c = ConsecutiveConfirm(is_armed, n=n, min_recv_us=after_recv_us)
    for s in samples:
        if c.feed(s):
            return c.confirmed_at
    return None


# ---------------------------------------------------------------------------
# OFFBOARD가 아닌 ARMED 표본


def armed_non_offboard(samples, from_us, to_us, time_of="recv"):
    """[from_us, to_us] 안의 표본에서 (ARMED 표본 수, OFFBOARD가 아닌 ARMED 표본 목록)을 돌려준다.

    time_of "recv"는 수신 ROS 시각, "ts"는 PX4 timestamp로 구간을 자른다(ULog 표본은 "ts").
    to_us가 None이면 끝을 열어 둔다.
    """
    n_armed = 0
    bad = []
    for s in samples:
        t = s.recv_ros_us if time_of == "recv" else s.ts_us
        if t < from_us or (to_us is not None and t > to_us):
            continue
        if s.arming_state == ARMING_STATE_ARMED:
            n_armed += 1
            if s.nav_state != NAV_STATE_OFFBOARD:
                bad.append(s)
    return n_armed, bad


# ---------------------------------------------------------------------------
# landed 전환과 분기


def landed_transitions(landed_samples, from_us, to_us):
    """구간 안의 landed 전환. 구간 시작 시점의 상태(그 전의 마지막 표본, 없으면 구간의 첫 표본)는 전환으로 세지 않는다.

    돌려주는 dict: initial(bool 또는 None), count, times_us(전환 시각, 수신 ROS 시각), intervals_s
    (이웃한 전환 사이 간격, 초).
    """
    prev = None
    times = []
    initial = None
    started = False
    for s in landed_samples:
        if s.recv_ros_us > from_us and not started:
            # 구간 시작 시점의 상태는 그 전의 마지막 표본이다(없으면 구간의 첫 표본)
            initial = prev
            started = True
        if to_us is not None and s.recv_ros_us > to_us:
            break
        if s.recv_ros_us > from_us:
            if prev is None:
                initial = s.landed
            elif s.landed != prev:
                times.append(s.recv_ros_us)
        prev = s.landed
    if not started and prev is not None:
        initial = prev
    intervals = [(b - a) / US for a, b in zip(times, times[1:])]
    return {"initial": initial, "count": len(times), "times_us": times, "intervals_s": intervals}


def branch_sequence(branch_log):
    """[(시각_us, 'G' 또는 'A'), ...]에서 이웃한 같은 분기를 합친 순서와 전환 횟수.

    G는 지상(landed true) 분기, A는 공중(landed false) 분기다.
    """
    seq = []
    for _, b in branch_log:
        if not seq or seq[-1] != b:
            seq.append(b)
    return {"sequence": "".join(seq), "transitions": max(0, len(seq) - 1)}


# ---------------------------------------------------------------------------
# 정리 모델. decisions.md M3, M5, M6의 규칙을 옮긴 것이다(측정용 독립 구현. core를 호출하지 않는다).


class CleanupModel:
    """취소 뒤 정리의 분기 선택과 종료 판정(decisions.md M3, M5, M6의 일부만 흉내 낸다).

    흉내 내는 것: 매 step 최신 landed로 분기를 다시 고른다(true면 G, false면 A).
      G: 지상 setpoint 발행 + 강제가 아닌 disarm 재전송, 첫 전송 뒤에 받은 DISARMED 3회 연속이면 끝.
      A: 지상 setpoint 발행 + Hold 재전송. AUTO_LOITER 표본을 처음 관측한 시각에 발행을 멈추고
         (publishing False, publish_stop_us), 3회 연속(전송 뒤에 받은 서로 다른 timestamp) 관측하면
         end_reason HOLD로 끝낸다. 총 소요는 이 끝 시각까지다.
      분기에 들어갈 때마다(G -> A -> G의 재진입 포함) 그 분기의 timeout 기준 시각, 확인 계수, 첫 전송
      기준(tick과 Px4Timestamp)을 새로 잡고 명령을 새로 보낸다. 이전 진입에서 센 표본은 이어지지 않는다.
      분기 timeout은 G가 mode_confirm_timeout, A가 hold_confirm_timeout이고 전체 상한(hard_limit)이 있다.
    한 step의 순서(M6): (1) 공중 DISARMED -> (2) 정리할 것 없음 -> (3) Hold 첫 관측으로 발행 중단
      -> (4) 상한 -> (5) 분기 실행(분기 timeout, 확인). 표본 하나로 정해지는 관측 (1)-(2)가 만료보다
      앞선다. (5)에서 만료와 확인이 겹치면 만료가 이긴다.
    흉내 내지 않는 것과 core/전이 표와 다른 점: (a) 입력은 tick이 아니라 약 2 ms 간격 polling이고 표본을
      수신 순서대로 먹인다(tick당 최신 표본 1개 모델이 아니다). (b) 상태 끊김(LINK_LOST), ack 거부 때의
      Land 경로, Hold 실패 뒤 공중 재진입(Land 경로), 상한 tick의 reason/명령 선택, 식별 불일치 종료가
      없다. (c) 정리의 소요는 이 모델의 소요이고 core의 소요가 아니다. end_reason은 core의 reason이
      아니다. 근거 범위는 PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, landed 전환, 상승)뿐이다.

    step(now_us, landed)이 돌려주는 동작은 "disarm", "hold" 문자열 목록이다(그 step에서 보낼 것).
    지상 setpoint 발행은 publishing이 참인 동안 계속이라 동작 목록에 넣지 않는다.
    """

    def __init__(self, start_us, mode_confirm_s=MODE_CONFIRM_TIMEOUT_S,
                 hold_confirm_s=HOLD_CONFIRM_TIMEOUT_S, hard_limit_s=CLEANUP_HARD_LIMIT_S,
                 resend_s=COMMAND_RESEND_S, arm_sent=True):
        self.start_us = start_us
        self._mode_us = int(mode_confirm_s * US)
        self._hold_us = int(hold_confirm_s * US)
        self._hard_us = int(hard_limit_s * US)
        self._resend_us = int(resend_s * US)
        self._arm_sent = arm_sent
        self.branch = None
        self._branch_since = None
        self.branch_log = []          # [(시각_us, 'G'|'A')]
        self._last_send = {"disarm": None, "hold": None}
        self.first_send = {"disarm": None, "hold": None}   # (recv_ros_us, ts_us)
        self._confirm = {}
        self.sent_log = []            # 전체 전송 기록 [(kind, recv_ros_us, ts_us)]. 분기 재진입에도 남는다
        # 명령 종류가 어느 확인기의 '전송 뒤' 기준을 정하는가
        self._floors = {"disarm": ("disarm",), "hold": ("hold", "hold_first")}
        self._reset_branch_state("disarm")
        self._reset_branch_state("hold")
        self._last_status = None
        self.publishing = True
        self.publish_stop_us = None
        self.end_reason = None
        self.end_us = None

    def _reset_branch_state(self, kind):
        """분기에 들어갈 때마다 그 분기의 확인 계수와 첫 전송 기준을 새로 잡는다(core의
        enter_ground, DisarmConfirm::begin과 같다). 이전 진입에서 센 표본과 보낸 전송은 이어지지 않는다."""
        self.first_send[kind] = None
        self._last_send[kind] = None
        if kind == "disarm":
            self._confirm["disarm"] = ConsecutiveConfirm(is_disarmed)
        else:
            self._confirm["hold"] = ConsecutiveConfirm(lambda s: s.nav_state == NAV_STATE_AUTO_LOITER)
            self._confirm["hold_first"] = ConsecutiveConfirm(
                lambda s: s.nav_state == NAV_STATE_AUTO_LOITER, n=1)

    # 입력
    def on_status(self, s):
        self._last_status = s
        for name, c in self._confirm.items():
            kind = "disarm" if name == "disarm" else "hold"
            # 명령을 보내기 전의 표본은 '전송 뒤에 받은' 기준에 못 미친다
            if self.first_send[kind] is not None:
                c.feed(s)

    def note_sent(self, kind, recv_ros_us, ts_us):
        """명령을 실제로 보낸 뒤 호출한다. 처음 보낸 값이 '전송 뒤에 받은' 기준이 된다."""
        self._last_send[kind] = recv_ros_us
        self.sent_log.append((kind, recv_ros_us, ts_us))
        if self.first_send[kind] is None:
            self.first_send[kind] = (recv_ros_us, ts_us)
            for name in self._floors[kind]:
                self._confirm[name].set_floor(ts_us, recv_ros_us)

    @property
    def done(self):
        return self.end_reason is not None

    @property
    def elapsed_s(self):
        return None if self.end_us is None else (self.end_us - self.start_us) / US

    @property
    def publish_stop_elapsed_s(self):
        return None if self.publish_stop_us is None else (self.publish_stop_us - self.start_us) / US

    def _finish(self, now_us, reason):
        self.end_reason = reason
        self.end_us = now_us
        if self.publishing:
            self.publishing = False
            self.publish_stop_us = now_us

    def step(self, now_us, landed):
        """최신 landed(bool)로 분기를 고르고, 이 step에서 보낼 명령 목록을 돌려준다."""
        if self.done:
            return []
        want = "G" if landed else "A"
        if want != self.branch:
            self.branch = want
            self._branch_since = now_us
            self.branch_log.append((now_us, want))
            self._reset_branch_state("disarm" if want == "G" else "hold")
        ls = self._last_status
        fresh = ls is not None and ls.recv_ros_us >= self.start_us
        # (1) 공중 DISARMED
        if self.branch == "A" and fresh and is_disarmed(ls):
            self._finish(now_us, "DISARMED_AIR")
            return []
        # (2) 정리할 것 없음: 지상 DISARMED이고 이 goal에서 arm을 보낸 적이 없다
        if self.branch == "G" and fresh and is_disarmed(ls) and not self._arm_sent:
            self._finish(now_us, "NOTHING_TO_CLEAN")
            return []
        # (3) Hold를 처음 관측하면 발행을 멈춘다(관측이 먼저, 종료는 3회 연속)
        if self.publishing and self._confirm["hold_first"].done:
            self.publishing = False
            self.publish_stop_us = now_us
        # (4) 상한
        if now_us - self.start_us >= self._hard_us:
            self._finish(now_us, "LIMIT")
            return []
        # (5) 분기 실행. 만료가 확인보다 앞선다.
        branch_limit = self._mode_us if self.branch == "G" else self._hold_us
        if now_us - self._branch_since >= branch_limit:
            self._finish(now_us, "TIMEOUT_GROUND" if self.branch == "G" else "TIMEOUT_HOLD")
            return []
        if self.branch == "G" and self._confirm["disarm"].done:
            self._finish(now_us, "DISARMED")
            return []
        if self.branch == "A" and self._confirm["hold"].done:
            self._finish(now_us, "HOLD")
            return []
        kind = "disarm" if self.branch == "G" else "hold"
        last = self._last_send[kind]
        if last is None or now_us - last >= self._resend_us:
            return [kind]
        return []


# ---------------------------------------------------------------------------
# 분포


def percentile(sorted_vals, p):
    """선형 보간 백분위(0-100). 빈 목록이면 None."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def signed_distribution(values):
    """부호 있는 값의 분포. 단위는 호출자가 정한다(us)."""
    v = sorted(values)
    return {
        "n": len(v),
        "min": v[0] if v else None,
        "p05": percentile(v, 5),
        "p50": percentile(v, 50),
        "p95": percentile(v, 95),
        "max": v[-1] if v else None,
        "n_negative": sum(1 for x in v if x < 0),
        "n_zero": sum(1 for x in v if x == 0),
        "n_positive": sum(1 for x in v if x > 0),
    }


def status_offsets(samples):
    """모든 표본의 (timestamp - 수신 ROS 시각)과 (timestamp - 같은 시점의 /clock)의 분포.

    양수는 PX4 timestamp가 노드 시각보다 앞선다는 뜻이다.
    """
    return {
        "ts_minus_recv_ros_us": signed_distribution([s.ts_us - s.recv_ros_us for s in samples]),
        "ts_minus_clock_us": signed_distribution([s.ts_us - s.clock_us for s in samples]),
    }


def deltas_vs_sends(samples, sends):
    """명령 전송마다 전송 뒤 처음 받은 표본의 timestamp - Px4Timestamp(us)를 모은다.

    sends: [(전송 직후 recv_ros_us, Px4Timestamp_us)]. samples는 수신 순서.
    돌려주는 것: {"values_us": [...], "distribution": {...}, "unmatched": 표본이 없던 전송 수}
    """
    vals = []
    unmatched = 0
    for recv, ts in sends:
        hit = next((s for s in samples if s.recv_ros_us > recv), None)
        if hit is None:
            unmatched += 1
        else:
            vals.append(hit.ts_us - ts)
    return {"values_us": vals, "distribution": signed_distribution(vals), "unmatched": unmatched}


# ---------------------------------------------------------------------------
# 시도 판정


@dataclass
class Verdict:
    ok: bool
    verdict: str                       # PASS, FAIL, 또는 plan의 분류(PRECONDITION 등)
    reasons: list = field(default_factory=list)
    # INCONCLUSIVE의 종류. "ARM_EVIDENCE"는 (5)의 arm 수락 증거 미확인(ULog 교차 확인에서 승격할 수
    # 있는 유일한 종류). 그 밖의 INCONCLUSIVE는 빈 문자열이고 승격하지 않는다.
    kind: str = ""


def median_z(pos, end_us, window_s=1.0, min_n=5):
    """지상 기준 높이: (end_us - window_s, end_us] 동안 vehicle_local_position z(NED, m)의 중앙값과 표본 수.

    pos: (수신 ROS 시각 us, x, y, z, ...) 목록. z 잡음이 0.1 m 수준이라 표본 하나를 기준으로 쓰면 상승
    0.2 m 기준의 여유가 절반으로 줄 수 있어서 중앙값을 쓴다. 표본이 min_n개 미만이면 (None, 표본 수)다.
    """
    zs = sorted(p[3] for p in pos if end_us - window_s * US < p[0] <= end_us)
    n = len(zs)
    if n < min_n:
        return None, n
    mid = n // 2
    return (zs[mid] if n % 2 else (zs[mid - 1] + zs[mid]) / 2.0), n


def neighbor_gap_s(times_us, start_us, end_us=None):
    """관찰 구간 (start_us, end_us]에서 이웃한 표본 사이의 최대 간격(s)과 그 수.

    times_us: 표본 시각 목록(PX4 timestamp 또는 ROS 수신 시각, 같은 시각 중복은 무시). PX4 timestamp 축으로
    부를 때도 start_us와 end_us는 ROS 수신 시각이다(둘은 같은 sim 시간 축이라는 근사이고 차이의 분포는
    distribution_*.json에 있다. 근사 오차는 수 ms 수준이라 초 단위 기준에는 영향이 없다). 시작 직전의
    마지막 표본이 있으면 구간 안으로 세어 첫 표본과의 간격을 시작 가장자리로 잰다. 없으면 start_us부터
    첫 표본까지를 잰다. 구간 안 표본이 없으면 None(간격을 말할 수 없다).
    """
    ts = sorted(set(t for t in times_us if end_us is None or t <= end_us))
    inside = [t for t in ts if t > start_us]
    if not inside:
        return None
    before = [t for t in ts if t <= start_us]
    seq = ([before[-1]] if before else [start_us]) + inside
    return max(b - a for a, b in zip(seq, seq[1:])) / US


def judge_cleanup_time(total_s, limit_s=CLEANUP_LIMIT_S):
    """정리의 총 소요가 limit_s 미만인가."""
    return total_s is not None and total_s < limit_s


def _sampling_problem(f, p):
    """관찰 구간의 표본이 판정에 충분한가. 부족하면 사유 문장, 충분하면 None.

    p는 사실 이름의 접두사("observe_" 또는 "hold_observe_"). 관찰 시간은 명목 인자가 아니라 실제 구간
    (관찰 시작부터 끝까지의 sim 시간)이고, 구간 안 표본 수와 마지막 표본의 나이를 함께 본다.
    """
    span = f[p + "span_s"]
    if span < OBSERVE_MIN_S:
        return "관찰 구간 %.1f s < %.0f s" % (span, OBSERVE_MIN_S)
    if f[p + "status_n"] < span * OBSERVE_MIN_STATUS_PER_S:
        return "vehicle_status 표본 %d개 < 초당 %.1f개 x %.0f s" % (
            f[p + "status_n"], OBSERVE_MIN_STATUS_PER_S, span)
    if f[p + "landed_n"] < span * OBSERVE_MIN_LANDED_PER_S:
        return "vehicle_land_detected 표본 %d개 < 초당 %.1f개 x %.0f s" % (
            f[p + "landed_n"], OBSERVE_MIN_LANDED_PER_S, span)
    for name, limit, label in (("status", OBSERVE_MAX_STATUS_GAP_S, "vehicle_status"),
                               ("landed", OBSERVE_MAX_LANDED_GAP_S, "vehicle_land_detected")):
        gts, grecv = f[p + name + "_gap_ts_s"], f[p + name + "_gap_recv_s"]
        if gts is None or grecv is None:
            return "%s 이웃 표본 간격을 구할 수 없음" % label
        if max(gts, grecv) > limit:
            return "%s 이웃 표본 간격 %.2f s(PX4 timestamp %.2f, 수신 %.2f) > %.1f s" % (
                label, max(gts, grecv), gts, grecv, limit)
    sa, la = f[p + "status_age_s"], f[p + "landed_age_s"]
    if sa is None or sa > OBSERVE_MAX_STATUS_AGE_S:
        return "마지막 vehicle_status 표본이 관찰 끝에서 %s s (기준 %.1f s 이내)" % (sa, OBSERVE_MAX_STATUS_AGE_S)
    if la is None or la > OBSERVE_MAX_LANDED_AGE_S:
        return "마지막 vehicle_land_detected 표본이 관찰 끝에서 %s s (기준 %.1f s 이내)" % (la, OBSERVE_MAX_LANDED_AGE_S)
    return None


def judge_attempt(item, f):
    """시도 하나를 판정한다. f는 측정 사실의 dict. item은 "2a", "2b", "3", "5", "armed".

    통과 기준(정본: decisions.md 넘김 목록의 px4-engineer 행)
      공통(3, 5, armed): OFFBOARD가 아닌 ARMED 표본이 0개(첫 Hold 전송 전까지). (2a)는 기록만 한다.
      3은 취소 시점에 landed가 true였어야 한다(landed 표본이 없으면 None이라 INCONCLUSIVE). false면 창을 놓친 회지만 창과 무관한 기준(위 3, 5의 기준과
          Hold 종료의 60 s 관찰)은 전부 적용하고, 위반이 있으면 FAIL, 관찰 표본이 모자라면 INCONCLUSIVE,
          모두 만족하면 WINDOW_MISSED(유효 시도에도 not-pass에도 넣지 않는다)
      2a: Hold(AUTO_LOITER 3회 연속)를 관측, 정리 총 소요 9 s 미만
      2b: landed가 true에 닿으면 M3_CONTRADICTED(exit 1. M3 문장과 다른 관측). disarm 수락과 고도 변화는
          facts에 그대로 기록한다. 닿지 못하면(관찰 --observe-s) 관찰 중 모든 표본이 ARMED이고
          AUTO_LOITER, landed 전환 0회, 고도 변화 0.2 m 이하인 한 COND_NOT_REACHED(exit 2), 어긋나면 FAIL
      3, 5: mode_confirm_timeout 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만,
            끝난 뒤 지상에 armed로 남은 상태 없음.
            (3)이 Hold로 끝나면(end_reason HOLD) 상승 0.2 m 이하와 총 소요 9 s 미만에 더해 60 s 동안
            ARMED, AUTO_LOITER, landed false, 고도 변화 0.2 m 이하이면 HOLD_END(exit 2), 어긋나면 FAIL.
            그 밖의 TIMEOUT_GROUND, TIMEOUT_HOLD, LIMIT, DISARMED_AIR는 FAIL이다.
            (5)가 Hold로 끝나면 FAIL이다. (5)는 arm 수락 증거(arm_evidence: arm 전송 뒤 timestamp의 ARMED
            표본)가 없으면 INCONCLUSIVE다(ack는 증거가 아니다. ULog 교차 확인에서 확정한다)
      armed: ARMED 3회 확인에 도달, ARMED 3회 확인부터 NAV_LAND 전송까지도 비OFFBOARD ARMED 0개
    관찰 판정(2b, (3)의 Hold)은 표본 조건(구간 길이, 표본 수, 마지막 표본의 나이)을 못 채우면
    INCONCLUSIVE다. 값이 없어 판정할 수 없는 경우(고도 변화 None)도 위반이 따로 없으면 INCONCLUSIVE다.
    필요한 키가 없으면 KeyError로 실패한다(측정 누락을 통과로 읽지 않는다).
    """
    reasons = []      # 기준과 다른 관측
    missing = []      # 값이 없어 판정할 수 없는 항목

    def need(cond, msg):
        if not cond:
            reasons.append(msg)

    def need_value(v, limit, label):
        if v is None:
            missing.append("%s 값이 없음" % label)
        elif v > limit:
            reasons.append("%s %s m (기준 %.1f m 이하)" % (label, v, limit))

    def fin():
        if reasons:
            return Verdict(False, "FAIL", reasons)
        if missing:
            return Verdict(False, "INCONCLUSIVE", missing)
        return Verdict(True, "PASS", [])

    # 창을 놓친 회((3)에서 취소 시점에 landed가 이미 false)는 자극이 성립하지 않은 회라 유효 시도에도
    # not-pass에도 넣지 않는다. 그러나 창과 무관한 기준은 전부 적용한다. 순서: 기준 위반이 하나라도 있으면
    # FAIL -> 위반이 없고 Hold로 끝났는데 관찰 표본이 하한 미달이거나 값이 없으면 INCONCLUSIVE ->
    # 아니면 WINDOW_MISSED. Hold 종료도 허용한다(지상에서 끝나면 끝난 뒤 ARMED 없음과 마지막 DISARMED여야 한다).
    # 취소 시점의 landed 표본이 없으면(landed_at_cancel None) 창을 놓쳤는지 알 수 없으므로 PASS도
    # WINDOW_MISSED도 아니고 위반이 없으면 INCONCLUSIVE다.
    missed = item == "3" and f["landed_at_cancel"] is False
    unknown = item == "3" and f["landed_at_cancel"] is None

    def unknown_verdict():
        return Verdict(False, "INCONCLUSIVE", ["취소 시점의 landed 표본이 없어 창 안인지 알 수 없음"])

    def missed_verdict():
        how = "Hold" if f["end_reason"] == "HOLD" else "지상 %s" % f["end_reason"]
        return Verdict(False, "WINDOW_MISSED", [
            "취소 시점에 landed가 이미 false(이륙 직후 창을 놓침). 끝난 방식 %s, 정리 총 소요 %s s, 상승 %s m, "
            "취소 시 높이 %s m" % (how, f["cleanup_total_s"], f["climb_m"], f["height_at_cancel_m"])])

    if item in ("3", "5", "armed"):
        need(f["armed_non_offboard"] == 0,
             "OFFBOARD가 아닌 ARMED 표본 %d개" % f["armed_non_offboard"])
    if item == "2a":
        need(f["end_reason"] == "HOLD", "Hold를 관측하지 못함(end_reason=%s)" % f["end_reason"])
        need(judge_cleanup_time(f["cleanup_total_s"]),
             "정리 총 소요 %s s (기준 %.1f s 미만)" % (f["cleanup_total_s"], CLEANUP_LIMIT_S))
        return fin()
    if item == "2b":
        if "skipped" in f:
            return Verdict(False, "INCONCLUSIVE", [f["skipped"]])
        if f["landed_true_seen"]:
            return Verdict(False, "M3_CONTRADICTED",
                           ["landed가 true에 닿음(Hold 뒤 %.1f s). M3 문장과 다르다. disarm 수락=%s, 고도 변화 %s m"
                            % (f["landed_true_after_hold_s"], f["disarm_confirmed"], f["dz_max_m"])])
        need(f["observe_all_armed_loiter"], "관찰 중 ARMED이고 AUTO_LOITER가 아닌 표본이 있음")
        need(f["observe_landed_transitions"] == 0,
             "관찰 중 landed 전환 %s회" % f["observe_landed_transitions"])
        need_value(f["dz_max_m"], CLIMB_LIMIT_M, "관찰 중 고도 변화")
        if reasons:
            return fin()
        if missing:
            return fin()
        prob = _sampling_problem(f, "observe_")
        if prob is not None:
            return Verdict(False, "INCONCLUSIVE", [prob])
        return Verdict(False, "COND_NOT_REACHED",
                       ["landed가 %.0f s 관찰 동안 true가 되지 않음(Hold, ARMED, 고도 변화 %.2f m)"
                        % (f["observe_span_s"], f["dz_max_m"])])
    if item in ("3", "5"):
        hold_case = item == "3" and f["end_reason"] == "HOLD"
        need_value(f["climb_m"], CLIMB_LIMIT_M, "상승")
        need(judge_cleanup_time(f["cleanup_total_s"]),
             "정리 총 소요 %s s (기준 %.1f s 미만)" % (f["cleanup_total_s"], CLEANUP_LIMIT_S))
        if hold_case:
            need(f["hold_observe_all_armed_loiter"], "Hold 관찰 중 ARMED이고 AUTO_LOITER가 아닌 표본이 있음")
            need(f["hold_observe_landed_false"], "Hold 관찰 중 landed가 true가 된 적이 있음")
            need_value(f["hold_observe_dz_m"], CLIMB_LIMIT_M, "Hold 관찰 중 고도 변화")
            if reasons or missing:
                return fin()
            prob = _sampling_problem(f, "hold_observe_")
            if prob is not None:
                return Verdict(False, "INCONCLUSIVE", [prob])
            if missed:
                return missed_verdict()
            if unknown:
                return unknown_verdict()
            return Verdict(False, "HOLD_END", ["Hold로 끝남(전이 표에 있는 종료). 60 s 동안 M3의 상태를 유지"])
        need(f["end_reason"] == "DISARMED",
             "DISARMED 3회 미확인(end_reason=%s)" % f["end_reason"])
        need(not f["armed_after_end"], "끝난 뒤 다시 ARMED 표본이 나옴(지상 armed로 남을 수 있음)")
        need(f["final_disarmed"], "관찰 끝에 DISARMED가 아님")
        if item == "5" and not reasons and not missing and not f["arm_evidence"]:
            return Verdict(False, "INCONCLUSIVE",
                           ["arm 수락 증거(전송 뒤 ARMED 표본 또는 ULog logged message)가 없음. ack는 증거가 아니다"],
                           kind="ARM_EVIDENCE")
        v = fin()
        if missed and v.verdict == "PASS":
            return missed_verdict()
        if unknown and v.verdict == "PASS":
            return unknown_verdict()
        return v
    if item == "armed":
        need(f["armed3_reached"], "ARMED 3회 확인에 도달하지 못함")
        need(f["flight_armed_non_offboard"] == 0,
             "ARMED 3회 확인부터 NAV_LAND 전송까지 OFFBOARD가 아닌 ARMED 표본 %d개"
             % f["flight_armed_non_offboard"])
        return fin()
    raise ValueError("알 수 없는 item: %r" % item)


def judge_run(item_rows, min_attempts, armed_reached_min=None):
    """한 항목의 시도 행 모음을 요약한다. 실패한 시도를 빼지 않는다.

    item_rows: 행 dict 목록(verdict, armed3_reached 키를 색인으로 읽는다. 없으면 KeyError).
    시도 수(n_valid)는 기준에 대한 판정이 있는 verdict(PASS, FAIL, M3_CONTRADICTED)만 센다.
    INCONCLUSIVE, COND_NOT_REACHED, HOLD_END, PRECONDITION 등은 유효 시도가 아니고, EXCLUDED_VERDICTS
    (WINDOW_MISSED, ARM_NOT_ACCEPTED)는 유효 시도도 not-pass도 아닌 제외된 회(n_excluded)다.
    돌려주는 dict: n, n_valid, n_pass, n_fail(exit 1 verdict), n_excluded, n_other, enough(n_valid >=
      min_attempts), all_pass(제외된 회를 뺀 모든 시도가 PASS), upper95_fail_rate(3/n_valid), armed3_reached
    """
    n = len(item_rows)
    n_valid = sum(1 for r in item_rows if r["verdict"] in VALID_VERDICTS)
    n_pass = sum(1 for r in item_rows if r["verdict"] == "PASS")
    n_fail = sum(1 for r in item_rows if r["verdict"] in EXIT1_VERDICTS)
    n_excl = sum(1 for r in item_rows if r["verdict"] in EXCLUDED_VERDICTS)
    reached = sum(1 for r in item_rows if r["armed3_reached"])
    out = {
        "n": n, "n_valid": n_valid, "n_pass": n_pass, "n_fail": n_fail, "n_excluded": n_excl,
        "n_other": n - n_pass - n_fail - n_excl,
        "enough": n_valid >= min_attempts, "all_pass": n - n_excl > 0 and n_pass == n - n_excl,
        "upper95_fail_rate": (3.0 / n_valid) if n_valid else None,
        "armed3_reached": reached,
    }
    if armed_reached_min is not None:
        out["armed3_enough"] = reached >= armed_reached_min
    return out


CLASS_DIRECT = "px4_direct"      # 측정 스크립트가 PX4에 직접 명령(Executor 없음)
CLASS_EXECUTOR = "scenario_a"    # 시나리오 A(Executor 경유)


def _class_summary(rows, min_reached):
    measured = [r for r in rows if r["armed_non_offboard"] is not None]
    # 2a 행은 ARMED 3회 확인에 가는 실행이 아니므로 n_reached에서 빼고 위반 수에는 남긴다
    reached = [r for r in measured
               if r["armed3_reached"] and r["item"] != "2a" and r["verdict"] != "WINDOW_MISSED"]
    bad_reached = [r for r in reached if r["armed_non_offboard"] != 0]
    total = sum(r["armed_non_offboard"] for r in measured)
    return {
        "n_rows": len(rows),
        "n_measured": len(measured),
        "n_unmeasured": len(rows) - len(measured),
        "n_reached": len(reached),
        "violation_total": total,
        "violated": total != 0,
        "enough": len(reached) >= min_reached,
        "passed": len(reached) >= min_reached and total == 0 and not bad_reached,
    }


def judge_armed_criterion(rows, min_reached=10):
    """OFFBOARD가 아닌 ARMED 표본 기준의 부류별 판정.

    rows: 합산 대상 시도 행(item, class, verdict, armed3_reached, armed_non_offboard 키를 색인으로 읽는다.
    없으면 KeyError). armed_non_offboard가 None인 행은 측정되지 않은 행(PRECONDITION 등)이라
    n_unmeasured로 따로 세고 0으로 읽지 않는다. 어느 행을 넣을지는 호출자가 정한다.
    부류(class): px4_direct(측정 스크립트의 PX4 직접 명령. 이 판정의 통과는 P4 머지 조건이 아니다)와
    scenario_a(Executor 경유. P4 머지 조건은 이 부류의 통과가 따로 필요하다). 부류마다
    n_reached, violation_total, passed를 낸다(classes). 최상위 필드는 px4_direct 부류의 값이다.
    ARMED 3회 확인까지 간 실행이 min_reached 이상이고 그 전부에서 0개여야 통과다. 2a 행은
    n_reached에서 빼고 violation_total에는 남긴다. WINDOW_MISSED 행도 n_reached를 채우지 않는다. 한 건이라도 나오면 violated이고 호출자가 그 즉시
    architect에게 올린다. ARMED 3회에 가지 못한 실행에서 나온 위반도 센다.
    """
    classes = {}
    for c in sorted({r["class"] for r in rows} | {CLASS_DIRECT}):
        classes[c] = _class_summary([r for r in rows if r["class"] == c], min_reached)
    out = dict(classes[CLASS_DIRECT])
    out["classes"] = classes
    out["violated_any_class"] = any(v["violated"] for v in classes.values())
    return out
