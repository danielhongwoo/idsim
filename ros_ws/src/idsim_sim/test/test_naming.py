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
"""target_id 검증과 토픽 조립의 사례 표 테스트.

사례는 C++ 쪽(idsim_common/test/test_target.cpp의 AcceptsValidIds, RejectsInvalidIds, RejectsEmbeddedNul)과
같다. Python에만 있는 함정(끝 줄바꿈, 문자열이 아닌 값)을 더했다.
"""

import pytest

from idsim_interfaces.msg import TargetState
from idsim_sim.naming import is_valid_target_id, target_id_error, target_state_topic

VALID = ["a", "car_1", "target", "t0", "a_", "x9_y8", "a" + "z" * 31]
INVALID = ["", "1car", "_car", "Car", "car-1", "car.1", "car 1", "/car", "car/1", "cAr", "ca\u00e9",
           "a" + "z" * 32, "car\0x",
           # Python에만 있는 것: re.match와 $는 끝 줄바꿈을 받아들인다
           "car\n", "car_1\n"]
NOT_STR = [None, 1, b"car", ["car"]]


@pytest.mark.parametrize("value", VALID)
def test_accepts_valid(value):
    assert is_valid_target_id(value)
    assert target_id_error(value) is None


@pytest.mark.parametrize("value", INVALID + NOT_STR)
def test_rejects_invalid(value):
    assert not is_valid_target_id(value)
    assert target_id_error(value)
    with pytest.raises(ValueError):
        target_state_topic(value)


def test_topic_from_message_constants():
    assert target_state_topic("car_1") == "/targets/car_1/state"
    assert target_state_topic("car_1") == f"{TargetState.TOPIC_PREFIX}/car_1/{TargetState.TOPIC_SUFFIX}"


@pytest.mark.parametrize("value", VALID)
def test_every_valid_id_gives_valid_topic(value):
    from rclpy.validate_full_topic_name import validate_full_topic_name

    assert validate_full_topic_name(target_state_topic(value))
