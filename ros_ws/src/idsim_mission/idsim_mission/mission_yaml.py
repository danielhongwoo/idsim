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
"""미션 YAML 로더(1b decisions.md 쟁점 14).

로더가 하는 일은 넷뿐이다. 구조 검사(모르는 key 거부, 같은 mapping 안의 중복 key 거부, 필수 key, 타입), 단위 변환(timeout_s, duration_s
-> builtin_interfaces/Duration, ns 반올림, 음수와 비유한 거부), 기본값 채움, mission_id(YAML 값 또는 파일
이름, 정규식 검사). 계약 검증(값의 범위, 항목 순서, 좌표 상한, target_id 형식 등)의 정본은 Executor의
goal 검증이고 여기서 다시 하지 않는다. 그래서 계약에 어긋나는 미션도 구조만 맞으면 Mission이 되고,
Executor가 INVALID_MISSION으로 끝낸다.

형식(좌표는 world ENU m, 각은 rad, 시간은 s)

    mission_id: f1-square        # 선택. 없으면 파일 이름(확장자 뺀 것)
    items:
      - type: TAKEOFF            # TAKEOFF, GOTO, TRACK_ENTITY, LOITER, RTL, LAND
        timeout_s: 20
        height_m: 5.0
        acceptance_m: 0.3
        yaw_rad: 0.0             # 선택. 있으면 MODE_FIXED, 없으면 MODE_KEEP
      - type: GOTO
        timeout_s: 30
        position: [10.0, 0.0, 5.0]
        acceptance_radius_m: 0.5
      - type: TRACK_ENTITY
        timeout_s: 60
        target_id: car_1
        offset: [0.0, 0.0, 5.0]
        acceptance_radius_m: 0.5
      - type: LOITER
        timeout_s: 10
        duration_s: 5
      - type: RTL
        timeout_s: 60
      - type: LAND
        timeout_s: 30

type마다 받는 key는 아래 ITEM_KEYS다. 기본값이 있는 key는 yaw_rad(TAKEOFF, GOTO, TRACK_ENTITY. 없으면
MODE_KEEP) 하나뿐이다. 허용 오차(acceptance_m, acceptance_radius_m)는 근거 있는 기본값이 없어 필수다. 수는 int나 float(bool은 아니다)를 받는다.

parse_mission과 load_mission은 순수 Python이다(rclpy와 메시지 패키지 없음). to_mission_msg만
idsim_interfaces를 import한다.
"""

import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

import yaml

MISSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
NS_PER_S = 1_000_000_000
# builtin_interfaces/Duration.sec는 int32다.
MAX_DURATION_SEC = 2**31 - 1

# MissionItem.TYPE_* 값(idsim_interfaces/msg/MissionItem.msg). test_mission_yaml.py가 메시지 상수와
# 대조한다.
ITEM_TYPES = {
    "TAKEOFF": 1,
    "GOTO": 2,
    "TRACK_ENTITY": 3,
    "LOITER": 4,
    "RTL": 5,
    "LAND": 6,
}

# type마다 (필수 key, 선택 key). type과 timeout_s는 모든 항목의 필수 key다.
ITEM_KEYS = {
    "TAKEOFF": ({"height_m", "acceptance_m"}, {"yaw_rad"}),
    "GOTO": ({"position", "acceptance_radius_m"}, {"yaw_rad"}),
    "TRACK_ENTITY": ({"target_id", "offset", "acceptance_radius_m"}, {"yaw_rad"}),
    "LOITER": ({"duration_s"}, set()),
    "RTL": (set(), set()),
    "LAND": (set(), set()),
}
MISSION_KEYS = {"mission_id", "items"}


class MissionYamlError(ValueError):
    """구조, 타입, 단위 변환, mission_id 오류. 메시지에 위치(items[i].key)를 담는다."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader 위에 두 규칙을 더한다. 한 mapping 안의 같은 key는 거부한다(safe_load는 뒤의 값으로
    덮는다). merge key(<<)도 거부한다(합쳐진 key와 중복 검사가 섞여 결과를 읽기 어렵다)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise MissionYamlError(
                    f"merge key '<<' is not allowed at line {key_node.start_mark.line + 1}")
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                continue  # hash할 수 없는 key는 SafeLoader가 오류로 낸다
            if duplicate:
                raise MissionYamlError(
                    f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(stream):
    """YAML 문서 하나를 읽는다. SafeLoader에 중복 key와 merge key 거부를 더한 것이다(_UniqueKeyLoader).
    YAML 문법과 생성 오류(yaml.YAMLError, 생성 중의 ValueError)는 MissionYamlError로 바꾼다."""
    try:
        return yaml.load(stream, Loader=_UniqueKeyLoader)
    except MissionYamlError:
        raise
    except (yaml.YAMLError, ValueError) as e:
        # ValueError: 생성 중의 int 변환(Python의 정수 자릿수 제한을 넘는 정수)과 UTF-8 해독 오류.
        raise MissionYamlError(f"YAML: {e}") from None


@dataclass(frozen=True)
class DurationSpec:
    sec: int
    nanosec: int


@dataclass(frozen=True)
class YawSpec:
    fixed: bool = False  # False면 MODE_KEEP(yaw_rad 0), True면 MODE_FIXED
    yaw_rad: float = 0.0


@dataclass
class ItemSpec:
    """메시지 하나와 같은 모양의 값. type에 해당하지 않는 필드는 메시지 기본값(0)이다."""

    type: int
    timeout: DurationSpec
    height_m: float = 0.0
    acceptance_m: float = 0.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    acceptance_radius_m: float = 0.0
    target_id: str = ""
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    duration: DurationSpec = DurationSpec(0, 0)
    yaw: YawSpec = field(default_factory=YawSpec)


@dataclass
class MissionSpec:
    mission_id: str
    items: list


def seconds_to_duration(value, where):
    """s -> Duration(ns 반올림). 음수, 비유한, int32 sec 초과는 거부한다."""
    seconds = _number(value, where)
    if isinstance(seconds, float) and not math.isfinite(seconds):
        raise MissionYamlError(f"{where}: must be finite (got {value!r})")
    if seconds < 0:
        raise MissionYamlError(f"{where}: must not be negative (got {value!r})")
    ns = round(seconds * NS_PER_S) if isinstance(seconds, float) else seconds * NS_PER_S
    sec, nanosec = divmod(int(ns), NS_PER_S)
    if sec > MAX_DURATION_SEC:
        raise MissionYamlError(f"{where}: too large for builtin_interfaces/Duration (got {value!r})")
    return DurationSpec(sec, nanosec)


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionYamlError(f"{where}: must be a number (got {value!r})")
    return value


def _float(value, where):
    """수 -> float. float 범위를 넘는 정수는 OverflowError가 아니라 MissionYamlError다."""
    number = _number(value, where)
    try:
        return float(number)
    except OverflowError:
        raise MissionYamlError(f"{where}: too large for float64 (got {value!r})") from None


def _vec3(value, where):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise MissionYamlError(f"{where}: must be a list of 3 numbers (got {value!r})")
    return tuple(_float(v, f"{where}[{i}]") for i, v in enumerate(value))


def _string(value, where):
    if not isinstance(value, str):
        raise MissionYamlError(f"{where}: must be a string (got {value!r})")
    return value


def _check_keys(data, required, optional, where):
    unknown = sorted(set(data) - required - optional)
    if unknown:
        raise MissionYamlError(f"{where}: unknown key(s) {', '.join(map(str, unknown))}")
    missing = sorted(required - set(data))
    if missing:
        raise MissionYamlError(f"{where}: missing key(s) {', '.join(missing)}")


def _parse_yaw(data, where):
    if "yaw_rad" not in data:
        return YawSpec()
    return YawSpec(fixed=True, yaw_rad=_float(data["yaw_rad"], f"{where}.yaw_rad"))


def parse_item(data, index):
    where = f"items[{index}]"
    if not isinstance(data, dict):
        raise MissionYamlError(f"{where}: must be a mapping (got {data!r})")
    if "type" not in data:
        raise MissionYamlError(f"{where}: missing key(s) type")
    name = data["type"]
    if not isinstance(name, str) or name not in ITEM_TYPES:
        raise MissionYamlError(
            f"{where}.type: must be one of {', '.join(ITEM_TYPES)} (got {name!r})")
    required, optional = ITEM_KEYS[name]
    _check_keys(data, required | {"type", "timeout_s"}, optional, where)
    item = ItemSpec(type=ITEM_TYPES[name],
                    timeout=seconds_to_duration(data["timeout_s"], f"{where}.timeout_s"))
    if name == "TAKEOFF":
        item.height_m = _float(data["height_m"], f"{where}.height_m")
        item.acceptance_m = _float(data["acceptance_m"], f"{where}.acceptance_m")
        item.yaw = _parse_yaw(data, where)
    elif name == "GOTO":
        item.position = _vec3(data["position"], f"{where}.position")
        item.acceptance_radius_m = _float(data["acceptance_radius_m"], f"{where}.acceptance_radius_m")
        item.yaw = _parse_yaw(data, where)
    elif name == "TRACK_ENTITY":
        item.target_id = _string(data["target_id"], f"{where}.target_id")
        item.offset = _vec3(data["offset"], f"{where}.offset")
        item.acceptance_radius_m = _float(data["acceptance_radius_m"], f"{where}.acceptance_radius_m")
        item.yaw = _parse_yaw(data, where)
    elif name == "LOITER":
        item.duration = seconds_to_duration(data["duration_s"], f"{where}.duration_s")
    return item


def parse_mission(data, default_mission_id: Optional[str] = None) -> MissionSpec:
    """YAML에서 읽은 값 -> MissionSpec. mission_id가 없으면 default_mission_id(보통 파일 이름)."""
    if not isinstance(data, dict):
        raise MissionYamlError(f"mission: must be a mapping (got {type(data).__name__})")
    _check_keys(data, {"items"}, {"mission_id"}, "mission")
    if "mission_id" in data:
        mission_id = _string(data["mission_id"], "mission_id")
    elif default_mission_id is not None:
        mission_id = default_mission_id
    else:
        raise MissionYamlError("mission_id: not set and no file name to use")
    if not MISSION_ID_RE.match(mission_id):
        raise MissionYamlError(
            f"mission_id: {mission_id!r} does not match {MISSION_ID_RE.pattern}")
    items = data["items"]
    if not isinstance(items, list):
        raise MissionYamlError(f"items: must be a list (got {items!r})")
    # 항목 수(1개 이상)는 계약 검증이 본다. 빈 목록도 Mission이 된다.
    return MissionSpec(mission_id, [parse_item(item, i) for i, item in enumerate(items)])


def load_mission(path) -> MissionSpec:
    """YAML 파일 -> MissionSpec. mission_id의 기본값은 파일 이름에서 확장자를 뺀 것이다.

    파일을 열 수 없으면 OSError, 그 밖의 로더 오류(YAML 문법, 구조, 타입, 단위 변환, mission_id)는 모두
    MissionYamlError다."""
    with open(path, encoding="utf-8") as f:
        data = load_yaml(f)  # UTF-8이 아닌 파일의 UnicodeDecodeError(ValueError)도 MissionYamlError다
    stem = os.path.splitext(os.path.basename(os.fspath(path)))[0]
    return parse_mission(data, stem)


def to_mission_msg(spec: MissionSpec):
    """MissionSpec -> idsim_interfaces/msg/Mission."""
    from builtin_interfaces.msg import Duration
    from idsim_interfaces.msg import Mission, MissionItem, YawSetpoint

    def duration(d):
        return Duration(sec=d.sec, nanosec=d.nanosec)

    def yaw(y, msg):
        msg.mode = YawSetpoint.MODE_FIXED if y.fixed else YawSetpoint.MODE_KEEP
        msg.yaw_rad = y.yaw_rad

    mission = Mission()
    mission.mission_id = spec.mission_id
    for item in spec.items:
        m = MissionItem()
        m.type = item.type
        m.timeout = duration(item.timeout)
        if item.type == MissionItem.TYPE_TAKEOFF:
            m.takeoff.height_m = item.height_m
            m.takeoff.acceptance_m = item.acceptance_m
            yaw(item.yaw, m.takeoff.yaw)
        elif item.type == MissionItem.TYPE_GOTO:
            m.go_to.position.x, m.go_to.position.y, m.go_to.position.z = item.position
            m.go_to.acceptance_radius_m = item.acceptance_radius_m
            yaw(item.yaw, m.go_to.yaw)
        elif item.type == MissionItem.TYPE_TRACK_ENTITY:
            m.track_entity.target_id = item.target_id
            m.track_entity.offset.x, m.track_entity.offset.y, m.track_entity.offset.z = item.offset
            m.track_entity.acceptance_radius_m = item.acceptance_radius_m
            yaw(item.yaw, m.track_entity.yaw)
        elif item.type == MissionItem.TYPE_LOITER:
            m.loiter.duration = duration(item.duration)
        mission.items.append(m)
    return mission
