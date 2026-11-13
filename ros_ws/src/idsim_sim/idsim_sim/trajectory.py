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
"""표적 궤적 평가와 stamp 단조 규칙. rclpy를 import하지 않는 순수 함수다.

결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 1(보간), 쟁점 3(stamp).

궤적 의미(쟁점 1)
- t는 노드 시계(ROS 시각, ns 정수). tau = t - start_s.
- tau < 0: 첫 waypoint에 정지(속도 0 벡터).
- 구간 직선 보간이고 속도는 구간 기울기다. waypoint 시각 정확히에서는 다음 구간 값이다(구간은 [t_i, t_{i+1})).
- loop true: tau를 마지막 waypoint 시각으로 나눈 나머지로 평가한다(처음과 끝 waypoint가 같다는 전제).
- loop false: tau >= 마지막 시각이면 마지막 waypoint에 정지(속도 0 벡터).
- 정지 구간(두 점이 같은 구간)의 속도는 0 벡터다.
- 시각 비교는 모두 ns 정수로 한다. waypoint 시각과 start_s는 round(s * 1e9) ns로 바꿔 둔다.
"""

from bisect import bisect_right
from dataclasses import dataclass
import enum
import math

NS_PER_S = 1_000_000_000
ZERO3 = (0.0, 0.0, 0.0)


def seconds_to_ns(value):
    """초(float)를 가장 가까운 ns 정수로."""
    return int(round(value * NS_PER_S))


@dataclass(frozen=True)
class Trajectory:
    """정규화된 표적 궤적 하나. 검증은 params 해석(params.py)이 끝낸 뒤라고 본다."""

    target_id: str
    start_ns: int
    loop: bool
    times_ns: tuple
    points: tuple  # ((x, y, z), ...) world ENU m

    @classmethod
    def from_seconds(cls, target_id, start_s, loop, t, x, y, z):
        """params와 같은 형태(초 단위 t 배열, 좌표 배열)에서 만든다."""
        times = tuple(seconds_to_ns(v) for v in t)
        points = tuple((float(a), float(b), float(c)) for a, b, c in zip(x, y, z, strict=True))
        if len(times) != len(points) or len(times) < 2:
            raise ValueError(f"{target_id}: waypoint는 2개 이상이고 t와 좌표의 길이가 같아야 한다")
        if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError(f"{target_id}: t는 0에서 시작해 엄격히 증가해야 한다(ns 단위로 비교)")
        if not all(math.isfinite(v) for p in points for v in p):
            raise ValueError(f"{target_id}: 좌표가 유한하지 않다")
        return cls(target_id, seconds_to_ns(start_s), bool(loop), times, points)


@dataclass(frozen=True)
class Sample:
    """한 시각의 표적 상태. velocity_valid는 이 생산자에서 항상 true다."""

    position: tuple
    velocity: tuple


def evaluate(traj, t_ns):
    """시각 t_ns(ns 정수)에서 궤적을 평가한다."""
    tau = t_ns - traj.start_ns
    times, points = traj.times_ns, traj.points
    if tau < 0:
        return Sample(points[0], ZERO3)
    end = times[-1]
    if traj.loop:
        tau %= end
    elif tau >= end:
        return Sample(points[-1], ZERO3)
    i = bisect_right(times, tau) - 1  # times[i] <= tau < times[i + 1]
    t0, t1 = times[i], times[i + 1]
    p0, p1 = points[i], points[i + 1]
    frac = (tau - t0) / (t1 - t0)
    dt_s = (t1 - t0) / NS_PER_S
    position = tuple(a + (b - a) * frac for a, b in zip(p0, p1))
    velocity = tuple((b - a) / dt_s for a, b in zip(p0, p1))
    return Sample(position, velocity)


class StampDecision(enum.Enum):
    """표적 하나의 이번 tick 발행 여부."""

    PUBLISH = "publish"
    SKIP_ZERO = "skip_zero"  # 첫 /clock 전(now == 0). 0을 내지 않는다
    SKIP_SAME = "skip_same"  # 직전 stamp와 같다(/clock 정지)
    SKIP_BACKWARD = "skip_backward"  # 직전 stamp보다 작다(/clock 역행). 호출자가 오류 로그를 남긴다


def stamp_decision(prev_ns, now_ns):
    """직전 발행 stamp(prev_ns, 없으면 None)와 지금 시각(now_ns)에서 발행 여부를 정한다.

    직전 stamp보다 큰 t에서만 발행하고 0 이하는 내지 않는다(쟁점 3).
    """
    if prev_ns is None:
        return StampDecision.PUBLISH if now_ns > 0 else StampDecision.SKIP_ZERO
    if now_ns > prev_ns:
        return StampDecision.PUBLISH
    if now_ns == prev_ns:
        return StampDecision.SKIP_SAME
    return StampDecision.SKIP_BACKWARD
