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

"""PX4 입력 발행자의 허용 목록 고정(decisions.md 쟁점 8). 소스를 정적으로 읽고 일부는 가짜 rclpy로 실행한다.

- px4_measure_pub.py: 발행자는 vehicle_command(source 254/1), offboard_control_mode, trajectory_setpoint 셋뿐이고
  명령은 arm, disarm, offboard, hold, land 다섯뿐이다. tests/sitl/measure/ 밖에서 가져가지 않는다.
- px4_raw.py: 발행자는 offboard_control_mode(context manager)와 vehicle_command(비상 정리, source 254/25)
  둘뿐이다. trajectory_setpoint는 발행하지 않는다.
허용 목록을 넓히는 변경은 이 테스트를 고쳐야 하므로 px4-engineer의 필수 승인 대상이 눈에 띈다.
"""
import ast
import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
SUPPORT = REPO / "tests" / "support"
MEASURE_PUB = SUPPORT / "px4_measure_pub.py"
RAW = SUPPORT / "px4_raw.py"
SKIP_DIRS = {".git", ".claude", "artifacts", "build", "install", "log", "__pycache__", "node_modules", "target"}


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _publisher_classes(tree):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "create_publisher":
            assert isinstance(n.args[0], ast.Name), "create_publisher의 첫 인자는 메시지 클래스 이름이어야 한다"
            out.append(n.args[0].id)
    return sorted(out)


def _px4_msgs_imports(tree):
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "px4_msgs.msg":
            names |= {a.name for a in n.names}
    return names


def _int_assign(tree, name):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return ast.literal_eval(n.value)
    raise AssertionError("%s 상수가 없다" % name)


def _find_class(tree, name):
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == name:
            return n
    raise AssertionError("%s 클래스가 없다" % name)


def _methods(cls):
    return {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}


# --- px4_measure_pub ---

def test_measure_pub_publishers_are_exactly_three():
    t = _tree(MEASURE_PUB)
    assert _publisher_classes(t) == ["OffboardControlMode", "TrajectorySetpoint", "VehicleCommand"]
    assert _px4_msgs_imports(t) == {"OffboardControlMode", "TrajectorySetpoint", "VehicleCommand"}


def test_measure_pub_publish_calls_use_only_its_three_publishers():
    t = _tree(MEASURE_PUB)
    recv = sorted(n.func.value.attr for n in ast.walk(t)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "publish")
    assert recv == ["_pub_cmd", "_pub_mode", "_pub_sp"]


def test_measure_pub_commands_are_exactly_five():
    cls = _find_class(_tree(MEASURE_PUB), "MeasureOnlyPublisher")
    send = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "send")
    kinds = set()
    for n in ast.walk(send):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "kind":
            for c in n.comparators:
                assert isinstance(c, ast.Constant)
                kinds.add(c.value)
    assert kinds == {"arm", "disarm", "offboard", "hold", "land"}
    assert _methods(cls) == {"__init__", "_cmd", "send", "publish_position"}


def test_measure_pub_source_is_254_1():
    t = _tree(MEASURE_PUB)
    assert _int_assign(t, "SOURCE_SYSTEM") == 254
    assert _int_assign(t, "SOURCE_COMPONENT") == 1


def test_measure_pub_requires_measure_only_flag():
    cls = _find_class(_tree(MEASURE_PUB), "MeasureOnlyPublisher")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    assert [a.arg for a in init.args.kwonlyargs][:1] == ["measure_only"]


def _code_files():
    for p in REPO.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".sh", ".yml", ".yaml", ".cpp", ".hpp", ".cmake", ".txt") \
                and not (set(p.relative_to(REPO).parts) & SKIP_DIRS):
            yield p


def _imports_measure_pub(text):
    """import 문(또는 importlib 경로 문자열)이 px4_measure_pub을 가리키는가. 주석과 docstring의 언급은 세지 않는다."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "px4_measure_pub" in text
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any("px4_measure_pub" in a.name for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and (
                "px4_measure_pub" in (n.module or "") or any(a.name == "px4_measure_pub" for a in n.names)):
            return True
        if isinstance(n, ast.Call) and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                           and "px4_measure_pub" in a.value for a in n.args):
            return True
    return False


def test_import_detector_catches_each_form():
    assert _imports_measure_pub("from tests.support.px4_measure_pub import MeasureOnlyPublisher")
    assert _imports_measure_pub("from tests.support import px4_measure_pub")
    assert _imports_measure_pub("import tests.support.px4_measure_pub as m")
    assert _imports_measure_pub("importlib.import_module('tests.support.px4_measure_pub')")
    assert not _imports_measure_pub('"""px4_measure_pub.py에 분리했다"""\nimport os')


def test_measure_pub_is_not_imported_outside_the_measure_directory():
    allowed_dirs = (REPO / "tests" / "sitl" / "measure",)
    allowed_files = {MEASURE_PUB, Path(__file__).resolve()}
    offenders = []
    for p in _code_files():
        if p.resolve() in allowed_files or any(d in p.parents for d in allowed_dirs):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if p.suffix == ".py":
            if _imports_measure_pub(text):
                offenders.append(str(p.relative_to(REPO)))
        elif "px4_measure_pub" in text:
            offenders.append(str(p.relative_to(REPO)))
    assert offenders == [], "측정 전용 발행 모듈을 tests/sitl/measure/ 밖에서 가져간다: %s" % offenders


def test_measure_pub_is_imported_somewhere_inside_measure():
    # 위 검사가 빈 검사가 아님을 확인한다(측정 스크립트가 실제로 가져간다)
    text = (REPO / "tests" / "sitl" / "measure" / "measure.py").read_text(encoding="utf-8")
    assert "px4_measure_pub" in text


# --- px4_raw ---

def test_raw_publishers_are_exactly_two_and_never_trajectory_setpoint():
    t = _tree(RAW)
    assert _publisher_classes(t) == ["OffboardControlMode", "VehicleCommand"]
    assert "TrajectorySetpoint" not in _px4_msgs_imports(t)
    code_names = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)} | \
        {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)}
    assert "TrajectorySetpoint" not in code_names


def test_raw_emergency_source_and_command_methods():
    t = _tree(RAW)
    assert _int_assign(t, "EMERGENCY_SOURCE") == (254, 25)
    cls = _find_class(t, "EmergencyCommand")
    public = {m for m in _methods(cls) if not m.startswith("_")}
    assert public == {"close", "land", "disarm"}


def test_raw_offboard_signal_is_a_context_manager_that_destroys():
    cls = _find_class(_tree(RAW), "OffboardSignal")
    assert {"__enter__", "__exit__", "_destroy"} <= _methods(cls)
    src = ast.get_source_segment(RAW.read_text(encoding="utf-8"), cls)
    assert "destroy_publisher" in src and "destroy_timer" in src


def test_fmu_strings_exist_only_in_the_allowed_helpers():
    # /fmu 문자열과 버전 접미사는 px4_topic.py와 px4_raw.py의 topic_regex에만 있다
    t = _tree(RAW)
    for fn in (n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)):
        has = any(isinstance(c, ast.Constant) and isinstance(c.value, str) and "fmu" in c.value
                  for c in ast.walk(fn))
        assert has == (fn.name == "topic_regex"), fn.name


@pytest.fixture(scope="module")
def raw_module():
    names = ("rclpy", "rclpy.qos", "rclpy.node", "rclpy.executors", "rclpy.parameter", "px4_msgs",
             "px4_msgs.msg", "rosgraph_msgs", "rosgraph_msgs.msg")
    fakes = {n: mock.MagicMock() for n in names}
    with mock.patch.dict(sys.modules, fakes):
        spec = importlib.util.spec_from_file_location("px4_raw_under_test", RAW)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod


def fake_raw(sysids):
    raw = mock.MagicMock()
    raw.ns = "px4_1"
    raw.ns_abs = "/px4_1"
    raw.sysid = 2
    raw.status_sysids = sysids
    raw.last_status_sysid_ok.return_value = set(sysids) == {2}
    raw.now_us.return_value = 1234
    return raw


def test_emergency_command_refuses_other_sources(raw_module):
    raw = fake_raw({2: 5})
    for src in ((254, 1), (255, 25), (1, 1), (0, 0)):
        with pytest.raises(ValueError):
            raw_module.EmergencyCommand(raw, *src)
    raw_module.EmergencyCommand(raw, 254, 25).close()


def test_emergency_command_checks_sysid_before_publishing(raw_module):
    bad = fake_raw({3: 5})
    c = raw_module.EmergencyCommand(bad, 254, 25)
    with pytest.raises(RuntimeError):
        c.land()
    with pytest.raises(RuntimeError):
        c.disarm()
    assert c.sent == []
    ok = fake_raw({2: 5})
    c = raw_module.EmergencyCommand(ok, 254, 25)
    c.land()
    c.disarm()
    assert len(c.sent) == 2
