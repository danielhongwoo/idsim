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

"""px4_topic과 골든 topics.txt의 양방향 일치. 골든은 tests/fixtures/px4/<PX4_TAG>/topics.txt다.

- 골든의 모든 줄(상대 토픽, 타입)에서 기본 이름과 접미사 판을 읽어 px4_topic이 같은 이름을 만드는지.
- 반대로 px4_topic이 만든 이름이 골든에 있는지(이름이 틀리면 여기서 걸린다).
- px4_msgs가 import되면(ros-ws 이미지) 실제 클래스의 MESSAGE_VERSION으로 같은 단정을 한 번 더 한다.
"""
import importlib
import re
from pathlib import Path

import pytest

from tests.support import golden
from tests.support.px4_topic import fmu_dir, message_version, px4_topic

_SUFFIX = re.compile(r"^(?P<base>.+?)(?:_v(?P<ver>\d+))?$")


REPO = Path(__file__).resolve().parents[2]


def _golden_lines():
    path = Path(golden.golden_dir(str(REPO), str(REPO / "docker" / "versions.env"))) / "topics.txt"
    lines = [ln.split() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [(rel, typ) for rel, typ in lines]


def _fake_cls(ver):
    return type("Fake", (), {"MESSAGE_VERSION": ver} if ver is not None else {})


def _split(rel):
    parts = rel.split("/")
    assert parts[0] == "fmu" and parts[1] in ("in", "out"), rel
    m = _SUFFIX.match(parts[2])
    return parts[1], m.group("base"), int(m.group("ver")) if m.group("ver") else None


def test_golden_is_not_empty():
    assert len(_golden_lines()) > 20


def test_every_golden_topic_is_reproduced():
    for rel, _ in _golden_lines():
        direction, base, ver = _split(rel)
        assert px4_topic("/px4_1", direction, base, _fake_cls(ver)) == "/px4_1/" + rel


def test_names_with_version_zero_have_no_suffix():
    assert px4_topic("/px4_1", "out", "failsafe_flags", _fake_cls(None)) == "/px4_1/" + fmu_dir("out") + "failsafe_flags"
    assert px4_topic("/px4_1", "in", "vehicle_command", _fake_cls(0)) == "/px4_1/" + fmu_dir("in") + "vehicle_command"
    assert px4_topic("/px4_2", "out", "vehicle_status", _fake_cls(1)) == "/px4_2/fmu/out/vehicle_status_v1"


def test_message_version_defaults_to_zero():
    assert message_version(object()) == 0
    assert message_version(_fake_cls(3)) == 3


def test_argument_checks():
    cls = _fake_cls(0)
    for bad in (("px4_1", "out", "x"), ("/px4_1/", "out", "x"), ("/px4_1", "sideways", "x"),
                ("/px4_1", "out", ""), ("/px4_1", "out", "a/b")):
        with pytest.raises(ValueError):
            px4_topic(bad[0], bad[1], bad[2], cls)


def test_real_px4_msgs_versions_match_golden():
    pytest.importorskip("px4_msgs")
    msgs = importlib.import_module("px4_msgs.msg")
    checked = 0
    for rel, typ in _golden_lines():
        if "/vehicle_status" not in rel and "/vehicle_command" not in rel and "/vehicle_local_position" not in rel:
            continue
        direction, base, ver = _split(rel)
        cls = getattr(msgs, typ.rsplit("/", 1)[1])
        assert px4_topic("/px4_1", direction, base, cls) == "/px4_1/" + rel
        checked += 1
    assert checked >= 3
