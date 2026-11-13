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
"""노드의 시작 거부(설정 오류는 0이 아닌 종료). rclpy를 쓰지만 DDS 통신은 보지 않는다."""

import pytest

from idsim_sim import target_adapter


@pytest.mark.parametrize("args", [
    ["-p", "use_sim_time:=false"],
    ["-p", "use_sim_time:=true"],  # target_ids 없음
    ["-p", "use_sim_time:=true", "-p", "target_ids:=[Car]"],
])
def test_config_error_exits_nonzero(args):
    assert target_adapter.main(["target_adapter", "--ros-args", *args]) == target_adapter.EXIT_CONFIG_ERROR
