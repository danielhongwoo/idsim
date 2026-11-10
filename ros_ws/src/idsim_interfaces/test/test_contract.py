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
"""idsim_interfaces 계약 테스트.

정의가 바뀌면 이 테스트가 실패해서 계약 변경이 PR에서 드러난다. golden은 세 종류다.

- type hash (test/golden/type_hashes.txt): 설치된 type description의 RIHS01. 필드의 이름, 타입, 순서가
  바뀌면 달라진다. 중첩 타입의 변경이 그것을 담은 타입에도 번진다.
- 펼친 정의 (test/golden/<msg|action>/<Type>.txt): `ros2 interface show --no-comments` 출력(줄 끝에 남는
  주석 흔적은 지운다). hash가 잡지 못하는 상수 값 변경, 상수 추가, 기본값 변경을 잡는다. 중첩 타입을
  펼치므로 여기에도 번진다.
- 직접 정의 (test/golden/direct/<msg|action>/<Type>.txt): 그 파일의 직접 필드와 상수만. 중첩 타입은
  타입 이름만 남으므로 번지지 않는다. "고정"의 판정 단위다.

읽는 법: 고정된 파일의 직접 정의 golden이 다르면 고정된 계약의 변경이다. type hash나 펼친 정의만 다르면
중첩 타입에서 온 전파다.

golden 갱신(자동으로 하지 않는다. 계약 변경 절차를 거친 뒤에만):
    tools/ros_ws.sh shell
    colcon build --packages-select idsim_interfaces
    IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces
"""
import difflib
import importlib
import json
import os
import pathlib
import re
import subprocess

import pytest
from ament_index_python.packages import get_package_share_directory

PACKAGE = "idsim_interfaces"
MESSAGES = (
    "GoToItem",
    "LoiterItem",
    "Mission",
    "MissionEvent",
    "MissionItem",
    "TakeoffItem",
    "TargetState",
    "TrackEntityItem",
    "VehicleState",
    "YawSetpoint",
)
ACTIONS = ("ExecuteMission",)
INTERFACES = tuple(("msg", n) for n in MESSAGES) + tuple(("action", n) for n in ACTIONS)
INTERFACE_IDS = [f"{kind}/{name}" for kind, name in INTERFACES]

GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"
UPDATE = os.environ.get("IDSIM_UPDATE_GOLDEN") == "1"
UPDATE_HINT = (
    "의도한 계약 변경이면 변경 절차를 거친 뒤 golden을 갱신한다: "
    "tools/ros_ws.sh shell 안에서 IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces"
)
KIND_HINT = {
    "type hash": "필드의 이름, 타입, 순서가 바뀌었거나 중첩 타입에서 번진 변경이다",
    "펼친 정의": "상수나 기본값이 바뀌었거나 중첩 타입에서 번진 변경이다",
    "직접 정의": "이 파일의 직접 필드나 상수가 바뀌었다. 고정된 파일이면 고정된 계약의 변경이다",
}

INTEGER_TYPES = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "byte", "char"}
ROS_NAME_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONSTANT = re.compile(r"^(\S+) ([A-Z][A-Z0-9_]*) = (.+)$")
_ACTION_SECTIONS = ("Goal", "Result", "Feedback")


def share_dir():
    return pathlib.Path(get_package_share_directory(PACKAGE))


def check_golden(kind, relpath, actual):
    """golden과 비교한다. 다르면 종류, diff, 갱신 방법을 적어 실패한다."""
    path = GOLDEN_DIR / relpath
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    if not path.exists():
        pytest.fail(f"{kind} golden이 없다: test/golden/{relpath}\n{UPDATE_HINT}", pytrace=False)
    expected = path.read_text(encoding="utf-8")
    if expected == actual:
        return
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"golden/{relpath}",
            tofile="현재 정의",
        )
    )
    pytest.fail(
        f"{kind} golden이 다르다: test/golden/{relpath}\n{KIND_HINT[kind]}\n{diff}\n{UPDATE_HINT}",
        pytrace=False,
    )


def _strip_comment(line):
    """문자열 상수 밖의 '#'부터 줄 끝까지를 지운다."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        elif ch == "#" and not in_string:
            return line[:i]
    return line


def direct_definition(kind, name):
    """설치된 원문에서 주석과 빈 줄을 빼고 공백을 정규화한 직접 정의."""
    source = (share_dir() / kind / f"{name}.{kind}").read_text(encoding="utf-8")
    lines = []
    for raw in source.splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if "=" in line:
            left, right = line.split("=", 1)
            line = " ".join(left.split()) + " = " + right.strip()
        else:
            line = " ".join(line.split())
        lines.append(line)
    return "\n".join(lines) + "\n"


def constants_of(kind, name):
    """직접 정의의 상수를 [(구역, 타입, 이름, 값 원문)]으로 돌려준다. msg의 구역은 None이다."""
    result = []
    section = 0
    for line in direct_definition(kind, name).splitlines():
        if line == "---":
            section += 1
            continue
        m = _CONSTANT.match(line)
        if m:
            where = _ACTION_SECTIONS[section] if kind == "action" else None
            result.append((where, m.group(1), m.group(2), m.group(3)))
    return result


def python_class(kind, name, section=None):
    cls = getattr(importlib.import_module(f"{PACKAGE}.{kind}"), name)
    return getattr(cls, section) if section else cls


def all_constants():
    for kind, name in INTERFACES:
        for section, ctype, cname, raw in constants_of(kind, name):
            yield kind, name, section, ctype, cname, raw


def test_installed_interfaces_match_list():
    """설치된 정의 파일의 집합이 이 테스트의 목록과 같다(새 파일이 golden 없이 들어오지 못한다)."""
    for kind, names in (("msg", MESSAGES), ("action", ACTIONS)):
        installed = sorted(p.stem for p in (share_dir() / kind).glob(f"*.{kind}"))
        assert installed == sorted(names), f"{kind} 목록이 다르다. test_contract.py의 목록과 golden을 함께 고친다"


def test_no_stale_golden_files():
    """목록에 없는 타입의 golden이 남아 있지 않다."""
    if UPDATE:
        return
    expected = {"type_hashes.txt"}
    for kind, name in INTERFACES:
        expected.add(f"{kind}/{name}.txt")
        expected.add(f"direct/{kind}/{name}.txt")
    actual = {p.relative_to(GOLDEN_DIR).as_posix() for p in GOLDEN_DIR.rglob("*") if p.is_file()}
    assert actual == expected


def test_type_hash_golden():
    hashes = {}
    for kind, name in INTERFACES:
        data = json.loads((share_dir() / kind / f"{name}.json").read_text(encoding="utf-8"))
        for entry in data["type_hashes"]:
            type_name, value = entry["type_name"], entry["hash_string"]
            if not type_name.startswith(f"{PACKAGE}/"):
                continue
            assert hashes.setdefault(type_name, value) == value, f"{type_name}의 hash가 파일마다 다르다"
    for kind, name in INTERFACES:
        assert f"{PACKAGE}/{kind}/{name}" in hashes
    actual = "".join(f"{t} {hashes[t]}\n" for t in sorted(hashes))
    check_golden("type hash", "type_hashes.txt", actual)


@pytest.mark.parametrize(("kind", "name"), INTERFACES, ids=INTERFACE_IDS)
def test_expanded_definition_golden(kind, name):
    out = subprocess.run(
        ["ros2", "interface", "show", "--no-comments", f"{PACKAGE}/{kind}/{name}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout
    assert out.strip(), "ros2 interface show 출력이 비었다"
    # --no-comments는 줄 끝 주석의 '#'과 그 앞의 정렬 공백을 남긴다. 주석의 정렬이 golden을 바꾸지 않게 지운다.
    # 들여쓰기(중첩 깊이)는 그대로 둔다.
    lines = [_strip_comment(line).rstrip() for line in out.splitlines()]
    check_golden("펼친 정의", f"{kind}/{name}.txt", "".join(f"{line}\n" for line in lines if line.strip()))


@pytest.mark.parametrize(("kind", "name"), INTERFACES, ids=INTERFACE_IDS)
def test_direct_definition_golden(kind, name):
    check_golden("직접 정의", f"direct/{kind}/{name}.txt", direct_definition(kind, name))


def test_constants_match_generated_python():
    """원문에서 읽은 상수가 생성된 Python 타입의 값과 같다(아래 상수 검사가 원문을 믿어도 된다)."""
    count = 0
    for kind, name, section, ctype, cname, raw in all_constants():
        value = getattr(python_class(kind, name, section), cname)
        if ctype == "string":
            assert json.dumps(value) == raw, f"{name}.{cname}"
        else:
            assert value == int(raw), f"{name}.{cname}"
        count += 1
    assert count > 0


def test_mission_item_type_set():
    """TYPE_*를 더하면 여기서 실패한다. 항목 분류와 검증(idsim_mission)을 함께 고쳐야 한다."""
    types = {c: int(raw) for _, _, c, raw in constants_of("msg", "MissionItem") if c.startswith("TYPE_")}
    assert types == {
        "TYPE_TAKEOFF": 1,
        "TYPE_GOTO": 2,
        "TYPE_TRACK_ENTITY": 3,
        "TYPE_LOITER": 4,
        "TYPE_RTL": 5,
        "TYPE_LAND": 6,
    }


def test_zero_valued_constants_mean_unknown_or_none():
    """값 0은 "모름 또는 무효"다. 기본 생성된 메시지가 유효한 enum 값이 되지 않는다."""
    bad = [
        f"{name}.{cname}"
        for _, name, _, ctype, cname, raw in all_constants()
        if ctype in INTEGER_TYPES and int(raw) == 0 and not cname.endswith(("_UNKNOWN", "_NONE"))
    ]
    assert not bad, f"값 0인 상수는 *_UNKNOWN 또는 *_NONE이어야 한다: {bad}"


def test_enum_values_unique_within_prefix():
    """같은 접두사(ARMING_, MODE_, ...)의 상수 값은 겹치지 않는다."""
    seen = {}
    for _, name, section, ctype, cname, raw in all_constants():
        if ctype not in INTEGER_TYPES:
            continue
        key = (name, section, cname.split("_", 1)[0], int(raw))
        assert key not in seen, f"{name}: {cname}와 {seen[key]}의 값이 같다"
        seen[key] = cname


def test_name_constants():
    vehicle_state = python_class("msg", "VehicleState")
    target_state = python_class("msg", "TargetState")
    mission = python_class("msg", "Mission")
    mission_event = python_class("msg", "MissionEvent")
    for token in (
        vehicle_state.TOPIC_NAME,
        mission_event.TOPIC_NAME,
        mission.ACTION_NAME,
        target_state.TOPIC_SUFFIX,
        target_state.FRAME_ID,
    ):
        assert ROS_NAME_TOKEN.match(token), f"ROS 이름 토큰이 아니다: {token!r}"
    prefix = target_state.TOPIC_PREFIX
    assert prefix.startswith("/") and ROS_NAME_TOKEN.match(prefix[1:]), prefix
    names = [vehicle_state.TOPIC_NAME, mission_event.TOPIC_NAME, mission.ACTION_NAME]
    assert len(set(names)) == len(names), "기체 네임스페이스 아래의 이름이 겹친다"


def test_frame_id_is_shared():
    assert python_class("msg", "VehicleState").FRAME_ID == python_class("msg", "TargetState").FRAME_ID


def test_mission_event_status_matches_goal_status():
    """기록물에서 _action/status와 바로 대조되도록 값이 같다. 타입은 다르다(GoalStatus는 int8)."""
    from action_msgs.msg import GoalStatus

    statuses = [(c, int(raw)) for _, _, c, raw in constants_of("msg", "MissionEvent") if c.startswith("STATUS_")]
    assert statuses
    for cname, value in statuses:
        assert getattr(GoalStatus, cname) == value, cname
