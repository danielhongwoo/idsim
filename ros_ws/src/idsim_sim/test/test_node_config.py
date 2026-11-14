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
"""노드의 시작 거부(설정 오류는 0이 아닌 종료)와 시작 뒤 파라미터 변경 거부. rclpy를 쓰지만 DDS 통신은 보지 않는다."""

import pytest
import rclpy
from rclpy.parameter import Parameter

from idsim_sim import target_adapter

GOOD_YAML = """/**:
  ros__parameters:
    use_sim_time: true
    publish_rate_hz: 20.0
    target_ids: [car_1]
    targets.car_1.start_s: 0.0
    targets.car_1.loop: false
    targets.car_1.t: [0.0, 10.0]
    targets.car_1.x: [1.0, 5.0]
    targets.car_1.y: [2.0, 2.0]
    targets.car_1.z: [0.0, 0.0]
"""


@pytest.mark.parametrize("args", [
    ["-p", "use_sim_time:=false"],
    ["-p", "use_sim_time:=true"],  # target_ids 없음
    ["-p", "use_sim_time:=true", "-p", "target_ids:=[Car]"],
])
def test_config_error_exits_nonzero(args):
    assert target_adapter.main(["target_adapter", "--ros-args", *args]) == target_adapter.EXIT_CONFIG_ERROR


def test_empty_array_exits_config_error(tmp_path):
    # 빈 배열 []은 rcl이 NOT_SET으로 넘겨 rclpy 자동 선언에서 ValueError가 난다. traceback(종료 코드 1)이 아니라 2
    params = tmp_path / "targets.yaml"
    params.write_text(GOOD_YAML.replace("targets.car_1.x: [1.0, 5.0]", "targets.car_1.x: []"))
    assert target_adapter.main(["target_adapter", "--ros-args", "--params-file", str(params)]) == \
        target_adapter.EXIT_CONFIG_ERROR


@pytest.fixture
def adapter(tmp_path):
    params = tmp_path / "targets.yaml"
    params.write_text(GOOD_YAML)
    context = rclpy.Context()
    rclpy.init(args=["target_adapter", "--ros-args", "--params-file", str(params)], context=context)
    node = None
    try:
        node = target_adapter.TargetAdapter(ready_path=str(tmp_path / "ready"), context=context)
        yield node
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown(context=context)


@pytest.mark.parametrize("param", [
    Parameter("use_sim_time", Parameter.Type.BOOL, False),
    Parameter("publish_rate_hz", Parameter.Type.DOUBLE, 5.0),
    Parameter("targets.car_1.start_s", Parameter.Type.DOUBLE, 3.0),
])
def test_rejects_param_change_after_start(adapter, param):
    before = adapter.get_parameter(param.name).value
    result = adapter.set_parameters([param])[0]
    assert not result.successful
    assert adapter.get_parameter(param.name).value == before
    assert adapter.get_parameter("use_sim_time").value is True
