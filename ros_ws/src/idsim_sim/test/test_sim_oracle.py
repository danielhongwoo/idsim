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
"""정답 pose 노드(scripts/sim_oracle.py)의 순수 함수.

scripts/는 설치 대상이 아니고 sim-base 컨테이너에서 마운트로 돈다(decisions.md 쟁점 3, 5). 그래서 이 테스트는
소스 트리의 파일을 경로로 읽는다(importlib). ros-ws 이미지에는 gz 바인딩과 sdformat14가 없으므로, 모듈 수준
import가 rclpy, gz, sdformat14, geometry_msgs 없이 되는지도 따로 본다. 오프셋 합성의 기대값은 손으로 계산했다
(합성 함수로 기대값을 만들지 않는다).
"""

import importlib.util
import math
import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sim_oracle.py"


def _load():
    spec = importlib.util.spec_from_file_location("sim_oracle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


so = _load()

H = math.sqrt(0.5)  # cos 45도 = sin 45도


def test_module_imports_without_ros_or_gz():
    # rclpy, gz, sdformat14, geometry_msgs를 막은 새 인터프리터에서 모듈을 읽고 순수 함수 하나를 부른다
    code = (
        "import sys\n"
        "for name in ('rclpy', 'gz', 'gz.transport13', 'gz.msgs10', 'sdformat14', 'geometry_msgs'):\n"
        "    sys.modules[name] = None\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('sim_oracle', {str(SCRIPT)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "assert m.oracle_pose_topic('px4_1') == '/sim/px4_1/pose'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


# 구독 토픽: /pose/info로 끝나고 dynamic_pose가 없다(decisions.md 쟁점 2, 5)
@pytest.mark.parametrize("world, topic", [
    ("default", "/world/default/pose/info"),
    ("idsim_base", "/world/idsim_base/pose/info"),
    ("w-1", "/world/w-1/pose/info"),
])
def test_pose_info_topic(world, topic):
    got = so.pose_info_topic(world)
    assert got == topic
    assert got.endswith("/pose/info")
    assert "dynamic_pose" not in got


def test_subscribed_topic_from_env_has_no_dynamic_pose():
    _, topic, _, _ = so.load_env({"IDSIM_WORLD_NAME": "default", "IDSIM_ORACLE_VEHICLES": "px4_1=x500_1",
                                  "GZ_SIM_RESOURCE_PATH": "/opt/px4-gz/models"})
    assert topic == "/world/default/pose/info"
    assert "dynamic_pose" not in topic


def test_no_dynamic_pose_in_source_constants():
    # 구독 토픽을 조립하는 상수 어디에도 dynamic_pose가 없다
    assert so.POSE_INFO_SUFFIX == "pose/info"
    assert "dynamic_pose" not in so.POSE_INFO_SUFFIX


@pytest.mark.parametrize("world", ["", "a/b", "w orld", "w\n", "x" * 65, None, "dynamic_pose/info/.."])
def test_pose_info_topic_rejects(world):
    with pytest.raises(so.ConfigError):
        so.pose_info_topic(world)


# 정답 pose 토픽 이름 조립 사례 표. tests/support의 조립과 같은 표를 쓴다(decisions.md 쟁점 5)
ORACLE_TOPIC_CASES = [
    ("px4_1", "/sim/px4_1/pose"),
    ("px4_2", "/sim/px4_2/pose"),
    ("px4_9", "/sim/px4_9/pose"),
]
ORACLE_TOPIC_INVALID = ["", "/px4_1", "px4_1/", "px4/1", "1px4", "px4-1", "px4 1", "px4_1\n", None, 1]


@pytest.mark.parametrize("vehicle_id, topic", ORACLE_TOPIC_CASES)
def test_oracle_pose_topic(vehicle_id, topic):
    from rclpy.validate_full_topic_name import validate_full_topic_name

    assert so.oracle_pose_topic(vehicle_id) == topic
    assert validate_full_topic_name(topic)


@pytest.mark.parametrize("vehicle_id", ORACLE_TOPIC_INVALID)
def test_oracle_pose_topic_rejects(vehicle_id):
    with pytest.raises(so.ConfigError):
        so.oracle_pose_topic(vehicle_id)


# 환경 변수 IDSIM_ORACLE_VEHICLES 해석
@pytest.mark.parametrize("text, expected", [
    ("px4_1=x500_1", [("px4_1", "x500_1")]),
    ("px4_1=x500_1 px4_2=x500_2", [("px4_1", "x500_1"), ("px4_2", "x500_2")]),
    ("  px4_2=x500_2\tpx4_1=x500_1 \n", [("px4_2", "x500_2"), ("px4_1", "x500_1")]),
])
def test_parse_vehicles(text, expected):
    assert so.parse_vehicles(text) == expected


@pytest.mark.parametrize("text", [
    None, "", "   ",
    "px4_1",  # = 없음
    "px4_1=", "=x500_1",
    "px4_1=x500", "px4_1=x500_0", "px4_1=x500_01", "px4_1=_1",
    "/px4_1=x500_1",
    "px4_1=x500_1 px4_1=x500_2",  # vehicle_id 중복
    "px4_1=x500_1 px4_2=x500_1",  # model 중복
    "px4_1=x500_1,px4_2=x500_2",
])
def test_parse_vehicles_rejects(text):
    with pytest.raises(so.ConfigError):
        so.parse_vehicles(text)


@pytest.mark.parametrize("model, base", [("x500_1", "x500"), ("x500_12", "x500"), ("my_quad_3", "my_quad")])
def test_model_base_name(model, base):
    assert so.model_base_name(model) == base


@pytest.mark.parametrize("env", [
    {"IDSIM_ORACLE_VEHICLES": "px4_1=x500_1", "GZ_SIM_RESOURCE_PATH": "/m"},
    {"IDSIM_WORLD_NAME": "default", "GZ_SIM_RESOURCE_PATH": "/m"},
    {"IDSIM_WORLD_NAME": "default", "IDSIM_ORACLE_VEHICLES": "px4_1=x500_1"},
    {"IDSIM_WORLD_NAME": "default", "IDSIM_ORACLE_VEHICLES": "px4_1=x500_1", "GZ_SIM_RESOURCE_PATH": "::"},
])
def test_load_env_rejects_missing(env):
    with pytest.raises(so.ConfigError):
        so.load_env(env)


def test_load_env():
    world, topic, vehicles, paths = so.load_env({
        "IDSIM_WORLD_NAME": "default", "IDSIM_ORACLE_VEHICLES": "px4_1=x500_1 px4_2=x500_2",
        "GZ_SIM_RESOURCE_PATH": "/opt/px4-gz/models:/opt/px4-gz/worlds"})
    assert world == "default"
    assert topic == "/world/default/pose/info"
    assert vehicles == [("px4_1", "x500_1"), ("px4_2", "x500_2")]
    assert paths == ["/opt/px4-gz/models", "/opt/px4-gz/worlds"]


def test_find_model_dir_order():
    dirs = {"/b/x500", "/c/x500"}
    assert so.find_model_dir("x500", ["/a", "/b", "/c"], isdir=dirs.__contains__) == "/b/x500"
    assert so.find_model_dir("x500", ["/a"], isdir=dirs.__contains__) is None


# 오프셋 합성 golden. 쿼터니언은 (w, x, y, z). 기대값은 회전을 손으로 적용한 것이다.
# - yaw 90도: x -> y, y -> -x, z -> z
# - roll 90도: y -> z, z -> -y
# - pitch 90도: z -> x, x -> -z
# - (1,1,1)축 120도(q = (0.5, 0.5, 0.5, 0.5)): x -> y, y -> z, z -> x
COMPOSE_GOLDEN = [
    # p_model, q_model, offset, p_bl
    ((6.0, -3.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.24), (6.0, -3.0, 0.24)),
    ((6.0, -3.0, -0.013), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.24), (6.0, -3.0, 0.227)),
    ((1.0, 2.0, 3.0), (H, 0.0, 0.0, H), (0.0, 0.0, 0.24), (1.0, 2.0, 3.24)),
    ((1.0, 2.0, 3.0), (H, 0.0, 0.0, H), (0.1, 0.0, 0.24), (1.0, 2.1, 3.24)),
    ((1.0, 2.0, 3.0), (H, 0.0, 0.0, H), (0.0, 0.1, 0.0), (0.9, 2.0, 3.0)),
    ((1.0, 2.0, 3.0), (H, H, 0.0, 0.0), (0.0, 0.0, 0.24), (1.0, 1.76, 3.0)),
    ((1.0, 2.0, 3.0), (H, 0.0, H, 0.0), (0.0, 0.0, 0.24), (1.24, 2.0, 3.0)),
    ((1.0, 2.0, 3.0), (H, 0.0, H, 0.0), (0.5, 0.0, 0.0), (1.0, 2.0, 2.5)),
    ((0.0, 0.0, 0.0), (0.5, 0.5, 0.5, 0.5), (0.1, 0.2, 0.3), (0.3, 0.1, 0.2)),
    # 뒤집힌 부호의 쿼터니언은 같은 회전이다
    ((0.0, 0.0, 0.0), (-0.5, -0.5, -0.5, -0.5), (0.1, 0.2, 0.3), (0.3, 0.1, 0.2)),
    # 정규화되지 않은 쿼터니언(노름 2)도 같은 회전으로 쓴다
    ((1.0, 2.0, 3.0), (2 * H, 0.0, 0.0, 2 * H), (0.1, 0.0, 0.24), (1.0, 2.1, 3.24)),
    # yaw 180도(q = (0, 0, 0, 1)): x -> -x, y -> -y
    ((-2.0, 4.0, 0.5), (0.0, 0.0, 0.0, 1.0), (0.1, 0.2, 0.24), (-2.1, 3.8, 0.74)),
]


@pytest.mark.parametrize("p_model, q_model, offset, p_bl", COMPOSE_GOLDEN)
def test_compose_base_link_golden(p_model, q_model, offset, p_bl):
    got_p, got_q = so.compose_base_link(p_model, q_model, offset)
    assert got_p == pytest.approx(p_bl, abs=1e-12)
    assert got_q == q_model  # 자세는 model 그대로


@pytest.mark.parametrize("q", [(0.0, 0.0, 0.0, 0.0), (math.nan, 0.0, 0.0, 0.0), (math.inf, 0.0, 0.0, 1.0)])
def test_compose_rejects_bad_quaternion(q):
    with pytest.raises(ValueError):
        so.compose_base_link((0.0, 0.0, 0.0), q, (0.0, 0.0, 0.24))


@pytest.mark.parametrize("q", [(1.0, 0.0, 0.0, 0.0), (-1.0, 0.0, 0.0, 0.0)])
def test_offset_rotation_identity_ok(q):
    so.check_offset_rotation(q)


@pytest.mark.parametrize("q", [(H, 0.0, 0.0, H), (1.0 - 1e-6, 1e-3, 0.0, 0.0)])
def test_offset_rotation_rejects(q):
    with pytest.raises(so.ConfigError):
        so.check_offset_rotation(q)


# 발행 판단
@pytest.mark.parametrize("last, stamp, expected", [
    (None, 0, False),
    (None, -1, False),
    (None, 1, True),
    (1_000_000_000, 1_020_000_000, True),
    (1_000_000_000, 1_010_000_000, True),   # 정확히 MIN_PERIOD_NS
    (1_000_000_000, 1_009_999_999, False),
    (1_000_000_000, 1_000_000_000, False),  # 같은 stamp
    (1_000_000_000, 999_000_000, False),    # 역행
])
def test_should_publish(last, stamp, expected):
    assert so.MIN_PERIOD_NS == 10_000_000
    assert so.should_publish(last, stamp) is expected


def _entry(name, x, y, z, q=(1.0, 0.0, 0.0, 0.0)):
    return (name, (x, y, z), q)


def test_index_models_excludes_duplicates_and_links():
    entries = [_entry("ground_plane", 0, 0, 0), _entry("x500_1", 1, 2, 3), _entry("base_link", 0, 0, 0.24),
               _entry("x500_2", 4, 5, 6), _entry("x500_2", 7, 8, 9)]
    found, dup = so.index_models(entries, {"x500_1", "x500_2", "x500_3"})
    assert found == {"x500_1": ((1, 2, 3), (1.0, 0.0, 0.0, 0.0))}
    assert dup == {"x500_2"}


def test_core_step_ready_and_rate():
    core = so.OracleCore([("px4_1", "x500_1"), ("px4_2", "x500_2")],
                         {"x500_1": (0.0, 0.0, 0.24), "x500_2": (0.0, 0.0, 0.24)})
    # stamp 0: 내지 않는다
    out, ready, _, _ = core.step(0, [_entry("x500_1", 6, -3, 0), _entry("x500_2", -2, 4, 0)])
    assert out == [] and ready is None
    # 기체 2가 아직 스폰되지 않았다
    out, ready, _, _ = core.step(20_000_000, [_entry("x500_1", 6, -3, -0.013), _entry("base_link", 0, 0, 0.24)])
    assert [(v, p) for v, p, _ in out] == [("px4_1", pytest.approx((6.0, -3.0, 0.227)))]
    assert ready is None
    # 너무 짧은 간격의 기체 1은 내지 않고, 기체 2의 첫 표본에서 준비가 된다
    out, ready, _, _ = core.step(25_000_000, [_entry("x500_1", 6, -3, 0), _entry("x500_2", -2, 4, 0)])
    assert [v for v, _, _ in out] == ["px4_2"]
    assert ready == [("px4_1", 20_000_000), ("px4_2", 25_000_000)]
    # 준비는 한 번만 알린다
    out, ready, _, _ = core.step(45_000_000, [_entry("x500_1", 6, -3, 0), _entry("x500_2", -2, 4, 0)])
    assert [v for v, _, _ in out] == ["px4_1", "px4_2"]
    assert ready is None
    # 역행 표본은 내지 않는다
    out, _, _, _ = core.step(30_000_000, [_entry("x500_1", 6, -3, 0), _entry("x500_2", -2, 4, 0)])
    assert out == []


def test_core_skips_duplicate_model_names():
    core = so.OracleCore([("px4_1", "x500_1")], {"x500_1": (0.0, 0.0, 0.24)})
    out, ready, dup, _ = core.step(20_000_000, [_entry("x500_1", 0, 0, 0), _entry("x500_1", 1, 1, 1)])
    assert out == [] and ready is None and dup == {"x500_1"}


@pytest.mark.parametrize("last, stamp, expected", [
    (None, 0, "skip_zero"),
    (None, 5, "publish"),
    (100_000_000, 99_999_999, "skip_backward"),
    (100_000_000, 100_000_000, "skip_short"),
    (100_000_000, 105_000_000, "skip_short"),
    (100_000_000, 110_000_000, "publish"),
    (100_000_000, 0, "skip_zero"),
])
def test_stamp_decision(last, stamp, expected):
    assert so.stamp_decision(last, stamp) == expected


def test_core_reports_backward_once_per_entry():
    core = so.OracleCore([("px4_1", "x500_1"), ("px4_2", "x500_2")],
                         {"x500_1": (0.0, 0.0, 0.24), "x500_2": (0.0, 0.0, 0.24)})
    both = [_entry("x500_1", 0, 0, 0), _entry("x500_2", 1, 1, 0)]
    core.step(1_000_000_000, both)
    # 역행에 들어가는 표본에서 두 기체를 한 번씩 알린다
    out, _, _, backward = core.step(900_000_000, both)
    assert out == [] and backward == [("px4_1", 1_000_000_000), ("px4_2", 1_000_000_000)]
    # 역행이 이어져도 다시 알리지 않는다
    out, _, _, backward = core.step(950_000_000, both)
    assert out == [] and backward == []
    # 직전 stamp와 같은 표본은 역행이 아니고 역행 상태도 풀지 않는다
    out, _, _, backward = core.step(1_000_000_000, both)
    assert out == [] and backward == []
    # 직전 stamp를 넘어 다시 발행하면 풀리고, 그 뒤의 역행은 다시 알린다
    out, _, _, backward = core.step(1_020_000_000, both)
    assert [v for v, _, _ in out] == ["px4_1", "px4_2"] and backward == []
    _, _, _, backward = core.step(1_000_000_000, [_entry("x500_1", 0, 0, 0)])
    assert backward == [("px4_1", 1_020_000_000)]


def test_core_raises_on_bad_quaternion():
    # 콜백 안의 예외는 FatalOnError가 잡아 프로세스를 끝낸다(삼키지 않는다)
    core = so.OracleCore([("px4_1", "x500_1")], {"x500_1": (0.0, 0.0, 0.24)})
    with pytest.raises(ValueError):
        core.step(20_000_000, [_entry("x500_1", 0, 0, 0, q=(0.0, 0.0, 0.0, 0.0))])


def test_fatal_on_error_calls_once_and_stops():
    calls = []
    fatal = []

    def fn(x):
        calls.append(x)
        if x == 2:
            raise OSError("쓰기 실패")
        return x * 10

    wrapped = so.FatalOnError(fn, fatal.append)
    assert wrapped(1) == 10
    assert wrapped(2) is None
    assert wrapped(3) is None  # 실패 뒤에는 부르지 않는다
    assert calls == [1, 2]
    assert len(fatal) == 1 and isinstance(fatal[0], OSError)
    assert wrapped.failed


def test_exit_codes_distinct():
    assert so.EXIT_CONFIG_ERROR == 2
    assert so.EXIT_RUNTIME_ERROR == 3


def test_ready_path():
    assert so.READY_PATH == "/tmp/idsim/oracle_ready"
