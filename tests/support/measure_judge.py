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
# 정리 상한(s). hold_confirm_timeout + 3 x mode_confirm_timeout의 기본값.
CLEANUP_HARD_LIMIT_S = 12.0
MODE_CONFIRM_TIMEOUT_S = 3.0
HOLD_CONFIRM_TIMEOUT_S = 3.0
COMMAND_RESEND_S = 0.5
CONFIRM_SAMPLES = 3
# 상승 허용(m). (5)와 (2)의 "상승이 0.2 m 이하".
CLIMB_LIMIT_M = 0.2
# 지상 setpoint의 z 오프셋(m, NED 아래쪽). decisions.md M5.
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
    """취소 뒤 정리의 분기 선택과 종료 판정.

    매 step에서 최신 landed로 분기를 다시 고른다(true면 G, false면 A).
    G: 지상 setpoint 발행 + 강제가 아닌 disarm 재전송, 전송 뒤에 받은 DISARMED 3회 연속이면 끝.
    A: 지상 setpoint 발행 + Hold 재전송, 전송 뒤에 받은 AUTO_LOITER 3회 연속이 아니라 "처음 관측한
       순간"(AUTO_LOITER 표본 1개) 발행을 멈추고 끝낸다(재실측 (2)의 정의).
    분기마다 타임아웃(G는 mode_confirm_timeout, A는 hold_confirm_timeout)을 분기에 들어갈 때마다
    다시 잡고, 전체 상한(hard_limit)이 있다. 같은 step에서 만료와 확인이 겹치면 만료가 이긴다.
    예외: 공중(A)에서 DISARMED를 보면 'DISARMED_AIR'로 끝낸다.

    step(now_us)이 돌려주는 동작은 "disarm", "hold" 문자열 목록이다(그 step에서 보낼 것). 발행(지상
    setpoint)은 끝나기 전까지 계속이라 동작 목록에 넣지 않는다.
    """

    def __init__(self, start_us, mode_confirm_s=MODE_CONFIRM_TIMEOUT_S,
                 hold_confirm_s=HOLD_CONFIRM_TIMEOUT_S, hard_limit_s=CLEANUP_HARD_LIMIT_S,
                 resend_s=COMMAND_RESEND_S):
        self.start_us = start_us
        self._mode_us = int(mode_confirm_s * US)
        self._hold_us = int(hold_confirm_s * US)
        self._hard_us = int(hard_limit_s * US)
        self._resend_us = int(resend_s * US)
        self.branch = None
        self._branch_since = None
        self.branch_log = []          # [(시각_us, 'G'|'A')]
        self._last_send = {"disarm": None, "hold": None}
        self.first_send = {"disarm": None, "hold": None}   # (recv_ros_us, ts_us)
        self._confirm = {"disarm": ConsecutiveConfirm(is_disarmed),
                         "hold": ConsecutiveConfirm(lambda s: s.nav_state == NAV_STATE_AUTO_LOITER,
                                                    n=1)}
        self._last_status = None
        self.end_reason = None
        self.end_us = None

    # 입력
    def on_status(self, s):
        self._last_status = s
        for kind, c in self._confirm.items():
            # 명령을 보내기 전의 표본은 '전송 뒤에 받은' 기준에 못 미친다
            if self.first_send[kind] is not None:
                c.feed(s)

    def note_sent(self, kind, recv_ros_us, ts_us):
        """명령을 실제로 보낸 뒤 호출한다. 처음 보낸 값이 '전송 뒤에 받은' 기준이 된다."""
        self._last_send[kind] = recv_ros_us
        if self.first_send[kind] is None:
            self.first_send[kind] = (recv_ros_us, ts_us)
            self._confirm[kind].set_floor(ts_us, recv_ros_us)

    @property
    def done(self):
        return self.end_reason is not None

    @property
    def elapsed_s(self):
        return None if self.end_us is None else (self.end_us - self.start_us) / US

    def _finish(self, now_us, reason):
        self.end_reason = reason
        self.end_us = now_us

    def step(self, now_us, landed):
        """최신 landed(bool)로 분기를 고르고, 이 step에서 보낼 명령 목록을 돌려준다."""
        if self.done:
            return []
        want = "G" if landed else "A"
        if want != self.branch:
            self.branch = want
            self._branch_since = now_us
            self.branch_log.append((now_us, want))
        kind = "disarm" if self.branch == "G" else "hold"
        # 종료 판정. 만료가 확인보다 앞선다.
        branch_limit = self._mode_us if self.branch == "G" else self._hold_us
        if now_us - self.start_us >= self._hard_us:
            self._finish(now_us, "LIMIT")
            return []
        if now_us - self._branch_since >= branch_limit:
            self._finish(now_us, "TIMEOUT_GROUND" if self.branch == "G" else "TIMEOUT_HOLD")
            return []
        if self._confirm["disarm"].done and self.branch == "G":
            self._finish(now_us, "DISARMED")
            return []
        if self._confirm["hold"].done and self.branch == "A":
            self._finish(now_us, "HOLD")
            return []
        if (self.branch == "A" and self._last_status is not None
                and is_disarmed(self._last_status)
                and self._last_status.recv_ros_us >= self.start_us):
            self._finish(now_us, "DISARMED_AIR")
            return []
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


def judge_cleanup_time(total_s, limit_s=CLEANUP_LIMIT_S):
    """정리의 총 소요가 limit_s 미만인가."""
    return total_s is not None and total_s < limit_s


def judge_attempt(item, f):
    """시도 하나를 판정한다. f는 측정 사실의 dict. item은 "2a", "2b", "3", "5", "armed".

    통과 기준(정본: decisions.md 넘김 목록의 px4-engineer 행)
      공통(3, 5, armed): OFFBOARD가 아닌 ARMED 표본이 0개. (2a)는 같은 구간을 기록만 한다.
      3은 취소 시점에 landed가 true였어야 한다(아니면 WINDOW_MISSED. 통과로 세지 않는다)
      2a: Hold를 mode 확인 시간 안에 관측, 정리 총 소요 9 s 미만
      2b: landed true에서 보낸 disarm이 받아들여지고(DISARMED 3회) 고도 변화 0.2 m 이하
      3, 5: mode_confirm_timeout 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만,
            끝난 뒤 지상에 armed로 남은 상태 없음
      armed: ARMED 3회 확인에 도달
    필요한 키가 없으면 KeyError로 실패한다(측정 누락을 통과로 읽지 않는다).
    """
    reasons = []

    def need(cond, msg):
        if not cond:
            reasons.append(msg)

    if item == "3" and not f["landed_at_cancel"]:
        # 창을 놓친 시도는 PX4의 실패가 아니라 측정이 닿지 않은 것이다. 통과로 세지 않는다.
        return Verdict(False, "WINDOW_MISSED", ["취소 시점에 landed가 이미 false(이륙 직후 창을 놓침)"])
    if item in ("3", "5", "armed"):
        need(f["armed_non_offboard"] == 0,
             "OFFBOARD가 아닌 ARMED 표본 %d개" % f["armed_non_offboard"])
    if item == "2a":
        need(f["end_reason"] == "HOLD", "Hold를 관측하지 못함(end_reason=%s)" % f["end_reason"])
        need(judge_cleanup_time(f["cleanup_total_s"]),
             "정리 총 소요 %s s (기준 %.1f s 미만)" % (f["cleanup_total_s"], CLEANUP_LIMIT_S))
    elif item == "2b":
        need(f["landed_true_seen"], "관찰 중 landed가 true가 되지 않음")
        need(f["disarm_confirmed"], "disarm 후 DISARMED 3회 미확인")
        need(f["dz_max_m"] is not None and f["dz_max_m"] <= CLIMB_LIMIT_M,
             "고도 변화 %s m (기준 %.1f m 이하)" % (f["dz_max_m"], CLIMB_LIMIT_M))
    elif item in ("3", "5"):
        need(f["end_reason"] == "DISARMED",
             "DISARMED 3회 미확인(end_reason=%s)" % f["end_reason"])
        need(f["climb_m"] is not None and f["climb_m"] <= CLIMB_LIMIT_M,
             "상승 %s m (기준 %.1f m 이하)" % (f["climb_m"], CLIMB_LIMIT_M))
        need(judge_cleanup_time(f["cleanup_total_s"]),
             "정리 총 소요 %s s (기준 %.1f s 미만)" % (f["cleanup_total_s"], CLEANUP_LIMIT_S))
        need(not f["armed_after_end"], "끝난 뒤 다시 ARMED 표본이 나옴(지상 armed로 남을 수 있음)")
        need(f["final_disarmed"], "관찰 끝에 DISARMED가 아님")
    elif item == "armed":
        need(f["armed3_reached"], "ARMED 3회 확인에 도달하지 못함")
    else:
        raise ValueError("알 수 없는 item: %r" % item)
    return Verdict(not reasons, "PASS" if not reasons else "FAIL", reasons)


def judge_run(item_rows, min_attempts, armed_reached_min=None):
    """한 항목의 시도 행 모음을 요약한다. 실패한 시도를 빼지 않는다.

    item_rows: 행 dict 목록(verdict, armed3_reached 키 사용). 돌려주는 dict
      n, n_pass, n_fail, n_other, enough(시도 수 >= min_attempts), all_pass,
      upper95_fail_rate(3/n. 0건일 때의 근사), armed3_reached(ARMED 3회 확인에 간 시도 수)
    """
    n = len(item_rows)
    n_pass = sum(1 for r in item_rows if r["verdict"] == "PASS")
    n_fail = sum(1 for r in item_rows if r["verdict"] == "FAIL")
    reached = sum(1 for r in item_rows if r.get("armed3_reached"))
    out = {
        "n": n, "n_pass": n_pass, "n_fail": n_fail, "n_other": n - n_pass - n_fail,
        "enough": n >= min_attempts, "all_pass": n > 0 and n_pass == n,
        "upper95_fail_rate": (3.0 / n) if n else None,
        "armed3_reached": reached,
    }
    if armed_reached_min is not None:
        out["armed3_enough"] = reached >= armed_reached_min
    return out


def judge_armed_criterion(rows, min_reached=10):
    """OFFBOARD가 아닌 ARMED 표본 기준의 합산 판정.

    rows: 시나리오 A와 재실측 (3), (5)의 시도 행(armed3_reached, armed_non_offboard 키).
    ARMED 3회 확인까지 간 실행이 min_reached 이상이고 그 전부에서 0개여야 통과다. 한 건이라도
    나오면 violated를 true로 하고 호출자가 그 즉시 architect에게 올린다. ARMED 3회에 가지 못한
    실행에서 나온 위반도 센다(violation_total).
    """
    reached = [r for r in rows if r.get("armed3_reached")]
    bad_reached = [r for r in reached if r["armed_non_offboard"] != 0]
    total = sum(r["armed_non_offboard"] for r in rows)
    return {
        "n_rows": len(rows),
        "n_reached": len(reached),
        "violation_total": total,
        "violated": total != 0,
        "enough": len(reached) >= min_reached,
        "passed": len(reached) >= min_reached and total == 0 and not bad_reached,
    }
