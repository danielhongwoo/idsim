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

- px4_raw.py: 발행자는 offboard_control_mode(context manager)와 vehicle_command(비상 정리, source 254/25)
  둘뿐이다. trajectory_setpoint는 발행하지 않는다.
- tests/smoke/check_px4.py: tests/smoke에서 /fmu/in에 쓰는 곳은 이 파일의 --arm 경로 하나뿐이다. 발행자는 vehicle_command
  하나이고 명령은 ARM_DISARM(arm, disarm)뿐이다. tests/smoke는 lint px4-api 범위 밖이라 이 테스트가 유일한 고정이다.
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
RAW = SUPPORT / "px4_raw.py"
SMOKE = REPO / "tests" / "smoke"
SMOKE_PUB = SMOKE / "check_px4.py"


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
    raw.node.create_publisher.return_value.get_subscription_count.return_value = 1
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


def test_emergency_command_waits_for_a_subscriber(raw_module):
    raw = fake_raw({2: 5})
    raw.node.create_publisher.return_value.get_subscription_count.return_value = 0
    c = raw_module.EmergencyCommand(raw, 254, 25)
    with pytest.raises(raw_module.sw.SitlFailure) as e:
        c.land()
    assert e.value.category == "NO_PUBLISHER" and c.sent == []
    raw.node.create_publisher.return_value.get_subscription_count.return_value = 1
    c.land()
    assert len(c.sent) == 1


def test_emergency_command_constants_are_land_and_plain_disarm():
    cls = _find_class(_tree(RAW), "EmergencyCommand")
    consts = set()
    for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("land", "disarm")):
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_cmd":
                first = n.args[0]
                assert isinstance(first, ast.Attribute)
                consts.add(first.attr)
                if fn.name == "disarm":      # 강제 disarm(param2)을 넣지 않는다: 인자는 command와 param1 하나
                    assert len(n.args) == 2
    assert consts == {"VEHICLE_CMD_NAV_LAND", "VEHICLE_CMD_COMPONENT_ARM_DISARM"}


def test_raw_first_clock_wait_is_the_only_wall_clock_wait(raw_module):
    # 통합 테스트의 벽시계 대기는 첫 /clock 유예 하나뿐이다(decisions.md 쟁점 10)
    raw = raw_module.Px4Raw("px4_1", 2)
    with pytest.raises(raw_module.sw.SitlFailure) as e:
        raw.wait_first_clock(0.05)
    assert e.value.category == "CLOCK_ABSENT"
    raw._clock_us = 1
    raw.wait_first_clock(0.05)


# --- tests/smoke/check_px4.py (--arm) ---

def _smoke_py():
    files = sorted(SMOKE.glob("*.py"))
    assert SMOKE_PUB in files
    return files


def test_smoke_only_check_px4_publishes_or_imports_px4_msgs():
    # 스모크의 다른 스크립트로 새 발행자가 생기면 여기서 깨진다(필요하면 이 테스트에 명시적으로 허용을 추가한다)
    for p in _smoke_py():
        t = _tree(p)
        calls = [n for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("create_publisher", "publish", "create_client", "create_service")]
        if p == SMOKE_PUB:
            continue
        assert calls == [], "%s: 발행/서비스 호출이 있다" % p.name
        assert _px4_msgs_imports(t) == set(), "%s: px4_msgs를 가져온다" % p.name


def test_smoke_shell_has_no_topic_pub():
    for p in sorted(SMOKE.glob("*.sh")):
        text = p.read_text(encoding="utf-8")
        assert "topic pub" not in text and "topic.pub" not in text, p.name
        assert "service call" not in text and "action send_goal" not in text, p.name


def test_smoke_check_px4_publisher_is_exactly_vehicle_command():
    t = _tree(SMOKE_PUB)
    assert _publisher_classes(t) == ["VehicleCommand"]
    assert _px4_msgs_imports(t) & {"TrajectorySetpoint", "OffboardControlMode"} == set()
    assert not any(isinstance(n, ast.Name) and n.id in ("TrajectorySetpoint", "OffboardControlMode")
                   for n in ast.walk(t))
    pubs = [n for n in ast.walk(t)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "publish"]
    assert len(pubs) == 1, "publish 호출은 send_until_ack 안의 하나뿐이어야 한다"


def _attr_stores(tree, attr):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == attr
            and isinstance(n.ctx, ast.Store)]


def test_smoke_check_px4_command_is_only_arm_disarm():
    t = _tree(SMOKE_PUB)
    # (a) .command 대입은 파일 전체에서 하나이고 make_command 안에 있다(다른 함수나 모듈 수준 대입 금지)
    mk = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "make_command")
    stores = _attr_stores(t, "command")
    assert len(stores) == 1, "파일 전체에서 .command 대입은 하나뿐이어야 한다"
    assert stores[0] in set(ast.walk(mk)), ".command 대입은 make_command 안에 있어야 한다"
    assigns = [n for n in ast.walk(mk) if isinstance(n, ast.Assign) and stores[0] in n.targets]
    assert len(assigns) == 1
    v = assigns[0].value
    assert isinstance(v, ast.Attribute) and v.attr == "VEHICLE_CMD_COMPONENT_ARM_DISARM" \
        and isinstance(v.value, ast.Name) and v.value.id == "VehicleCommand"
    # (b) VEHICLE_CMD_* 속성 참조는 파일 전체에서 ARM_DISARM(VehicleCommand)과 ack 판정용 RESULT_ACCEPTED(VehicleCommandAck)뿐이다
    refs = sorted({(ast.unparse(n.value), n.attr) for n in ast.walk(t)
                   if isinstance(n, ast.Attribute) and n.attr.startswith("VEHICLE_CMD_")})
    assert refs == [("VehicleCommand", "VEHICLE_CMD_COMPONENT_ARM_DISARM"),
                    ("VehicleCommandAck", "VEHICLE_CMD_RESULT_ACCEPTED")], refs
    # 문자열로 우회하지 못하게 setattr/getattr/vars 호출과 __dict__ 접근을 막는다
    assert not [n for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("setattr", "getattr", "vars", "exec", "eval")]
    assert not [n for n in ast.walk(t) if isinstance(n, ast.Attribute) and n.attr == "__dict__"]
    # VehicleCommand 객체는 make_command에서만 만들고, 생성자에 인자를 주지 않는다(keyword로 command/param2를 넣는 우회 차단)
    ctors = [n for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "VehicleCommand"]
    assert len(ctors) == 1 and ctors[0] in set(ast.walk(mk))
    assert ctors[0].args == [] and ctors[0].keywords == [], "VehicleCommand()는 인자 없이 만든다"
    # 호출부는 param1만 바꾼다: 강제 disarm용 param2를 쓰지 않는다(대입, keyword 인자 모두)
    assert _attr_stores(t, "param2") == []
    assert not [k for n in ast.walk(t) if isinstance(n, ast.Call) for k in n.keywords
                if k.arg in ("param2", "command")]
    assert not [n for n in ast.walk(t) if isinstance(n, ast.Constant) and n.value in ("param2", "command")]


def test_smoke_check_px4_source_is_254_1():
    t = _tree(SMOKE_PUB)
    assert _int_assign(t, "SOURCE_SYSTEM") == 254
    assert _int_assign(t, "SOURCE_COMPONENT") == 1


def test_smoke_check_px4_publishes_only_under_arm_flag():
    # create_publisher는 run_arm_checks 안에만 있고, run_arm_checks 호출은 모두 args.arm 가드 아래에 있다.
    # 가드 밖으로 나오면 기본 실행이 /fmu/in에 쓴다.
    t = _tree(SMOKE_PUB)
    fn = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "run_arm_checks")
    inside = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
              and isinstance(c.func, ast.Attribute) and c.func.attr == "create_publisher"]
    assert len(inside) == 1
    calls = [c for c in ast.walk(t) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Name) and c.func.id == "run_arm_checks"]
    assert len(calls) == 1
    guarded = [c for n in ast.walk(t) if isinstance(n, ast.If) and ast.unparse(n.test) == "args.arm"
               for c in ast.walk(n) if c is calls[0]]
    assert len(guarded) == 1, "run_arm_checks 호출이 if args.arm 아래에 있어야 한다"
