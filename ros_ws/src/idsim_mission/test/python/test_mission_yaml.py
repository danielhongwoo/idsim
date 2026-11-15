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
"""mission_yaml 로더: YAML 파일 -> idsim_interfaces/msg/Mission(1b decisions.md 쟁점 14).

로더는 구조(중복 key 포함), 단위 변환, 기본값, mission_id만 본다. 계약 위반(빈 항목, 순서, 0 offset, target_id 형식)은
그대로 Mission이 되는 것도 확인한다(정본은 Executor의 goal 검증).
"""

import math

import pytest
from builtin_interfaces.msg import Duration
from idsim_interfaces.msg import MissionItem, YawSetpoint

from idsim_mission import mission_yaml as my

FULL = """\
mission_id: f4-combined
items:
  - type: TAKEOFF
    timeout_s: 20
    height_m: 5
    acceptance_m: 0.25
  - type: GOTO
    timeout_s: 30.5
    position: [10.0, -2, 5.0]
    acceptance_radius_m: 0.5
    yaw_rad: 1.5
  - type: TRACK_ENTITY
    timeout_s: 60
    target_id: car_1
    offset: [0.0, 0.0, 5.0]
    acceptance_radius_m: 0.75
  - type: LOITER
    timeout_s: 10
    duration_s: 1.0000000006
  - type: RTL
    timeout_s: 60
"""


def write(tmp_path, text, name="mission.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_item_type_values_match_message():
    for name, value in my.ITEM_TYPES.items():
        assert getattr(MissionItem, f"TYPE_{name}") == value


def test_full_mission_becomes_message(tmp_path):
    msg = my.to_mission_msg(my.load_mission(write(tmp_path, FULL)))
    assert msg.mission_id == "f4-combined"
    assert [i.type for i in msg.items] == [
        MissionItem.TYPE_TAKEOFF, MissionItem.TYPE_GOTO, MissionItem.TYPE_TRACK_ENTITY,
        MissionItem.TYPE_LOITER, MissionItem.TYPE_RTL]
    takeoff, go, track, loiter, rtl = msg.items
    assert takeoff.timeout == Duration(sec=20, nanosec=0)
    assert takeoff.takeoff.height_m == 5.0
    assert takeoff.takeoff.acceptance_m == 0.25
    assert takeoff.takeoff.yaw.mode == YawSetpoint.MODE_KEEP  # 기본값
    assert takeoff.takeoff.yaw.yaw_rad == 0.0
    assert go.timeout == Duration(sec=30, nanosec=500000000)
    assert (go.go_to.position.x, go.go_to.position.y, go.go_to.position.z) == (10.0, -2.0, 5.0)
    assert go.go_to.acceptance_radius_m == 0.5
    assert go.go_to.yaw.mode == YawSetpoint.MODE_FIXED
    assert go.go_to.yaw.yaw_rad == 1.5
    assert track.track_entity.target_id == "car_1"
    assert (track.track_entity.offset.x, track.track_entity.offset.y,
            track.track_entity.offset.z) == (0.0, 0.0, 5.0)
    assert track.track_entity.acceptance_radius_m == 0.75
    assert track.track_entity.yaw.mode == YawSetpoint.MODE_KEEP
    # ns 반올림(1.0000000006 s -> 1 s + 1 ns).
    assert loiter.loiter.duration == Duration(sec=1, nanosec=1)
    assert rtl.timeout == Duration(sec=60, nanosec=0)
    # type에 해당하지 않는 서브메시지는 메시지 기본값이다(계약: 나머지는 기본값).
    assert go.takeoff == MissionItem().takeoff
    assert go.track_entity == MissionItem().track_entity
    assert go.loiter == MissionItem().loiter
    assert rtl.go_to == MissionItem().go_to


def test_mission_id_defaults_to_file_name(tmp_path):
    path = write(tmp_path, "items:\n  - {type: LAND, timeout_s: 30}\n", name="f1_square.yaml")
    assert my.load_mission(path).mission_id == "f1_square"


def test_mission_id_regex(tmp_path):
    path = write(tmp_path, "items: []\n", name="F1.yaml")
    with pytest.raises(my.MissionYamlError, match="mission_id"):
        my.load_mission(path)
    with pytest.raises(my.MissionYamlError, match="mission_id"):
        my.parse_mission({"mission_id": "-a", "items": []})
    with pytest.raises(my.MissionYamlError, match="mission_id"):
        my.parse_mission({"mission_id": 7, "items": []})
    assert my.parse_mission({"mission_id": "a" * 64, "items": []}).mission_id == "a" * 64
    with pytest.raises(my.MissionYamlError, match="mission_id"):
        my.parse_mission({"mission_id": "a" * 65, "items": []})


def test_contract_violations_are_not_loader_errors():
    # 계약 검증은 Executor가 한다. 구조가 맞으면 Mission이 된다.
    cases = [
        {"mission_id": "b-empty", "items": []},
        {"mission_id": "b-land-goto", "items": [
            {"type": "LAND", "timeout_s": 30},
            {"type": "GOTO", "timeout_s": 10, "position": [1, 2, 3], "acceptance_radius_m": 1}]},
        {"mission_id": "b-track", "items": [
            {"type": "TRACK_ENTITY", "timeout_s": 10, "target_id": "Car-1", "offset": [0, 0, 0],
             "acceptance_radius_m": -1}]},
        {"mission_id": "b-zero", "items": [{"type": "LAND", "timeout_s": 0}]},
    ]
    for data in cases:
        msg = my.to_mission_msg(my.parse_mission(data))
        assert msg.mission_id == data["mission_id"]
        assert len(msg.items) == len(data["items"])


@pytest.mark.parametrize("data, match", [
    ([], "mission: must be a mapping"),
    ({"mission_id": "m"}, "missing key"),
    ({"mission_id": "m", "items": [], "extra": 1}, "unknown key"),
    ({"mission_id": "m", "items": {}}, "items: must be a list"),
    ({"mission_id": "m", "items": ["LAND"]}, r"items\[0\]: must be a mapping"),
    ({"mission_id": "m", "items": [{"timeout_s": 1}]}, r"items\[0\]: missing key\(s\) type"),
    ({"mission_id": "m", "items": [{"type": "HOVER", "timeout_s": 1}]}, r"items\[0\]\.type"),
    ({"mission_id": "m", "items": [{"type": 6, "timeout_s": 1}]}, r"items\[0\]\.type"),
    ({"mission_id": "m", "items": [{"type": "LAND"}]}, r"missing key\(s\) timeout_s"),
    ({"mission_id": "m", "items": [{"type": "LAND", "timeout_s": 1, "height_m": 5}]},
     r"items\[0\]: unknown key\(s\) height_m"),
    ({"mission_id": "m", "items": [{"type": "TAKEOFF", "timeout_s": 1}]},
     r"missing key\(s\) acceptance_m, height_m"),
    ({"mission_id": "m", "items": [{"type": "TAKEOFF", "timeout_s": 1, "height_m": 5}]},
     r"items\[0\]: missing key\(s\) acceptance_m"),
    ({"mission_id": "m", "items": [{"type": "TAKEOFF", "timeout_s": 1, "height_m": "5",
                                    "acceptance_m": 0.3}]},
     r"items\[0\]\.height_m: must be a number"),
    ({"mission_id": "m", "items": [{"type": "TAKEOFF", "timeout_s": 1, "height_m": True,
                                    "acceptance_m": 0.3}]},
     r"items\[0\]\.height_m: must be a number"),
    ({"mission_id": "m", "items": [{"type": "TAKEOFF", "timeout_s": 1, "height_m": 5,
                                    "acceptance_m": 0.3, "yaw": 1}]},
     r"unknown key\(s\) yaw"),
    ({"mission_id": "m", "items": [{"type": "GOTO", "timeout_s": 1, "position": [1, 2],
                                    "acceptance_radius_m": 1}]}, r"position: must be a list of 3"),
    ({"mission_id": "m", "items": [{"type": "GOTO", "timeout_s": 1, "position": [1, 2, "x"],
                                    "acceptance_radius_m": 1}]}, r"position\[2\]: must be a number"),
    ({"mission_id": "m", "items": [{"type": "TRACK_ENTITY", "timeout_s": 1, "target_id": 3,
                                    "offset": [0, 0, 1], "acceptance_radius_m": 1}]},
     r"target_id: must be a string"),
    ({"mission_id": "m", "items": [{"type": "LOITER", "timeout_s": 10}]}, r"missing key\(s\) duration_s"),
])
def test_structure_errors(data, match):
    with pytest.raises(my.MissionYamlError, match=match):
        my.parse_mission(data)


@pytest.mark.parametrize("value, match", [
    (-0.5, "must not be negative"),
    (-1, "must not be negative"),
    (math.inf, "must be finite"),
    (math.nan, "must be finite"),
    (2.0**31, "too large"),
    ("1", "must be a number"),
])
def test_timeout_conversion_errors(value, match):
    with pytest.raises(my.MissionYamlError, match=r"items\[0\]\.timeout_s: " + match):
        my.parse_mission({"mission_id": "m", "items": [{"type": "LAND", "timeout_s": value}]})


def test_duration_rounding():
    assert my.seconds_to_duration(0, "t") == my.DurationSpec(0, 0)
    assert my.seconds_to_duration(1.25, "t") == my.DurationSpec(1, 250000000)
    assert my.seconds_to_duration(0.1, "t") == my.DurationSpec(0, 100000000)
    assert my.seconds_to_duration(2**31 - 1, "t") == my.DurationSpec(2**31 - 1, 0)


def test_yaml_special_floats_reach_timeout_check(tmp_path):
    path = write(tmp_path, "mission_id: m\nitems:\n  - {type: LAND, timeout_s: .nan}\n")
    with pytest.raises(my.MissionYamlError, match="must be finite"):
        my.load_mission(path)


@pytest.mark.parametrize("text, line", [
    ("mission_id: a\nmission_id: b\nitems: []\n", 2),
    ("mission_id: m\nitems:\n  - type: LAND\n    timeout_s: 30\n    timeout_s: 60\n", 5),
    ("mission_id: m\nitems:\n  - {type: GOTO, timeout_s: 10, position: [1, 2, 3],\n"
     "     acceptance_radius_m: 1, acceptance_radius_m: 2}\n", 4),
])
def test_duplicate_keys_are_rejected(tmp_path, text, line):
    with pytest.raises(my.MissionYamlError, match=f"duplicate key .* at line {line}"):
        my.load_mission(write(tmp_path, text))


def test_same_key_in_different_items_is_not_duplicate(tmp_path):
    text = "mission_id: m\nitems:\n  - {type: LAND, timeout_s: 30}\n  - {type: LAND, timeout_s: 30}\n"
    assert len(my.load_mission(write(tmp_path, text)).items) == 2
