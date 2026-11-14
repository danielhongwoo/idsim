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

"""SITL 판정이 공유하는 표본 형식과 순수 판정 함수(rclpy, 시계, 파일 입출력 없음).

sitl_judge, sitl_summary, px4_raw, tests/sitl이 쓴다. 시간은 모두 마이크로초 정수이고 sim 시간 축이다.
"""
from dataclasses import dataclass

# px4_msgs/VehicleStatus 상수.
ARMING_STATE_DISARMED = 1
ARMING_STATE_ARMED = 2
NAV_STATE_AUTO_LOITER = 4
NAV_STATE_OFFBOARD = 14
NAV_STATE_AUTO_LAND = 18

CONFIRM_SAMPLES = 3


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


CLASS_DIRECT = "px4_direct"      # 부류 이름. 현재 행은 모두 CLASS_EXECUTOR이고 CLASS_DIRECT 행은 없다
CLASS_EXECUTOR = "scenario_a"    # 시나리오 A(Executor 경유)


def _class_summary(rows, min_reached):
    measured = [r for r in rows if r["armed_non_offboard"] is not None]
    reached = [r for r in measured if r["armed3_reached"]]
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

    rows: 합산 대상 시도 행(class, armed3_reached, armed_non_offboard 키를 색인으로 읽는다.
    없으면 KeyError). armed_non_offboard가 None인 행은 측정되지 않은 행이라
    n_unmeasured로 따로 세고 0으로 읽지 않는다. 어느 행을 넣을지는 호출자가 정한다.
    부류(class)마다 n_reached, violation_total, passed를 낸다(classes). 호출자(sitl_summary)가 쓰는 행은
    scenario_a 부류뿐이고, 최상위 필드는 행이 없어도 항상 있는 px4_direct 부류의 값이다.
    ARMED 3회 확인까지 간 실행이 min_reached 이상이고 그 전부에서 0개여야 통과다. 한 건이라도 나오면
    violated이고 호출자가 그 즉시 architect에게 올린다. ARMED 3회에 가지 못한 실행에서 나온 위반도 센다.
    """
    classes = {}
    for c in sorted({r["class"] for r in rows} | {CLASS_DIRECT}):
        classes[c] = _class_summary([r for r in rows if r["class"] == c], min_reached)
    out = dict(classes[CLASS_DIRECT])
    out["classes"] = classes
    out["violated_any_class"] = any(v["violated"] for v in classes.values())
    return out
