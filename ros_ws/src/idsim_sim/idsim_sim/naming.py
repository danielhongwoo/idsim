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
"""target_id 검증과 표적 상태 토픽 이름 조립(발행 쪽). rclpy를 import하지 않는다.

규칙은 docs/interface.md "이름과 식별자"의 target_id(^[a-z][a-z0-9_]{0,31}$)이고, C++ 쪽은
idsim_common/target.hpp가 같은 규칙을 가진다. 토픽은 TargetState 상수로 조립한다
(TOPIC_PREFIX + "/" + target_id + "/" + TOPIC_SUFFIX). 결정: decisions.md 쟁점 3.
"""

import re

from idsim_interfaces.msg import TargetState

TARGET_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")


def target_id_error(value):
    """value가 target_id 규칙에 맞으면 None, 아니면 이유 문자열."""
    if not isinstance(value, str):
        return f"target_id는 문자열이어야 한다: {value!r}"
    # fullmatch를 쓴다. re.match와 '$'는 끝의 줄바꿈 하나를 받아들인다
    if TARGET_ID_RE.fullmatch(value) is None:
        return f"target_id가 ^[a-z][a-z0-9_]{{0,31}}$에 맞지 않는다: {value!r}"
    return None


def is_valid_target_id(value):
    """target_id 규칙에 맞는가."""
    return target_id_error(value) is None


def target_state_topic(target_id):
    """표적 상태 토픽의 절대 이름. 규칙에 맞지 않는 id는 ValueError."""
    error = target_id_error(target_id)
    if error is not None:
        raise ValueError(error)
    return f"{TargetState.TOPIC_PREFIX}/{target_id}/{TargetState.TOPIC_SUFFIX}"
