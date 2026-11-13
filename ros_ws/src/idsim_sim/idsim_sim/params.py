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
"""표적 어댑터 params 해석. rclpy를 import하지 않는 순수 함수다.

형식(decisions.md 쟁점 3, 생성기가 params/targets.yaml로 낸다)
    /**:
      ros__parameters:
        use_sim_time: true
        target_ids: [car_1, car_2]          # 문자열 배열, 1개 이상
        targets.car_1.start_s: 0.0         # double
        targets.car_1.loop: false          # bool
        targets.car_1.t: [0.0, 10.0]       # double 배열, 같은 길이 2개 이상, 0에서 시작해 엄격히 증가
        targets.car_1.x: [1.0, 5.0]        # double 배열(world ENU m)
        targets.car_1.y: [...]
        targets.car_1.z: [...]
        publish_rate_hz: 20.0              # 선택. 기본 20.0(계약 아님)
    ROS 2 파라미터는 구조체 배열을 담지 못해 평탄화한다. 실수는 모두 소수점 표기여야 한다(정수로 적으면
    INTEGER 계열로 읽혀 거부된다). YAML의 점(.)이 든 key는 그대로 파라미터 이름이 된다.

입력은 {파라미터 이름: (형 이름, 값)}이다. 형 이름은 rclpy Parameter.Type의 이름(BOOL, DOUBLE,
STRING_ARRAY, DOUBLE_ARRAY, ...)이고, 노드가 선언된 파라미터 전부를 이 형태로 넘긴다.
어기면 ConfigError(메시지는 사람이 읽는 이유 목록). 노드는 이것을 0이 아닌 종료로 바꾼다.
"""

from dataclasses import dataclass
import math

from idsim_sim.naming import target_id_error
from idsim_sim.trajectory import Trajectory, seconds_to_ns

DEFAULT_PUBLISH_RATE_HZ = 20.0
TARGET_FIELDS = ("start_s", "loop", "t", "x", "y", "z")
TARGETS_PREFIX = "targets."


class ConfigError(Exception):
    """params가 형식에 맞지 않는다."""


@dataclass(frozen=True)
class AdapterConfig:
    trajectories: tuple
    publish_rate_hz: float


def _finite(values):
    return all(isinstance(v, float) and math.isfinite(v) for v in values)


def parse_params(params):
    """params를 해석해 AdapterConfig를 돌려준다. 어기면 ConfigError."""
    errors = []

    def get(name, kind):
        item = params.get(name)
        if item is None:
            errors.append(f"{name}: 없다")
            return None
        got_kind, value = item
        if got_kind != kind:
            errors.append(f"{name}: 형이 {kind}여야 한다(받은 형 {got_kind}). 실수는 소수점 표기로 쓴다")
            return None
        return value

    use_sim_time = get("use_sim_time", "BOOL")
    if use_sim_time is False:
        errors.append("use_sim_time: true여야 한다(표적 stamp는 시뮬레이션 시간이다)")

    rate = DEFAULT_PUBLISH_RATE_HZ
    if "publish_rate_hz" in params:
        rate = get("publish_rate_hz", "DOUBLE")
        if rate is not None and not (math.isfinite(rate) and rate > 0.0):
            errors.append(f"publish_rate_hz: 양의 유한한 값이어야 한다: {rate!r}")

    ids = get("target_ids", "STRING_ARRAY")
    ids = list(ids) if ids is not None else []
    if "target_ids" in params and not ids:
        errors.append("target_ids: 비어 있다(표적이 없으면 targets 서비스를 만들지 않는다)")
    seen = set()
    for tid in ids:
        err = target_id_error(tid)
        if err:
            errors.append(f"target_ids: {err}")
        if tid in seen:
            errors.append(f"target_ids: 중복 {tid!r}")
        seen.add(tid)

    # targets. 아래의 모르는 이름(목록에 없는 id, 모르는 필드)은 오타일 수 있으므로 거부한다
    known = {f"{TARGETS_PREFIX}{tid}.{field}" for tid in ids for field in TARGET_FIELDS}
    for name in sorted(params):
        if name.startswith(TARGETS_PREFIX) and name not in known:
            errors.append(f"{name}: 모르는 파라미터(target_ids에 없는 id이거나 모르는 필드)")

    trajectories = []
    for tid in ids:
        if target_id_error(tid):
            continue
        base = f"{TARGETS_PREFIX}{tid}."
        start_s = get(base + "start_s", "DOUBLE")
        loop = get(base + "loop", "BOOL")
        arrays = {k: get(base + k, "DOUBLE_ARRAY") for k in ("t", "x", "y", "z")}
        if start_s is None or loop is None or any(v is None for v in arrays.values()):
            continue
        arrays = {k: [float(v) for v in vals] for k, vals in arrays.items()}
        before = len(errors)
        if not math.isfinite(start_s):
            errors.append(f"{base}start_s: 유한하지 않다")
        lengths = {k: len(v) for k, v in arrays.items()}
        if len(set(lengths.values())) != 1:
            errors.append(f"{base}t/x/y/z: 길이가 다르다 {lengths}")
        elif lengths["t"] < 2:
            errors.append(f"{base}t: waypoint가 2개 이상이어야 한다")
        if not all(_finite(v) for v in arrays.values()):
            errors.append(f"{base}t/x/y/z: 유한하지 않은 값이 있다")
        if len(errors) == before:
            t_ns = [seconds_to_ns(v) for v in arrays["t"]]
            if t_ns[0] != 0:
                errors.append(f"{base}t: 첫 값이 0이어야 한다: {arrays['t'][0]!r}")
            if any(b <= a for a, b in zip(t_ns, t_ns[1:])):
                errors.append(f"{base}t: 엄격히 증가해야 한다(ns 단위로 비교)")
            first = (arrays["x"][0], arrays["y"][0], arrays["z"][0])
            last = (arrays["x"][-1], arrays["y"][-1], arrays["z"][-1])
            if loop and first != last:
                errors.append(f"{base}loop: true이면 처음과 끝 waypoint가 같아야 한다({first} != {last})")
        if len(errors) == before:
            trajectories.append(Trajectory.from_seconds(tid, start_s, loop, arrays["t"], arrays["x"],
                                                        arrays["y"], arrays["z"]))

    if errors:
        raise ConfigError("\n".join(errors))
    return AdapterConfig(tuple(trajectories), float(rate))
