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

"""PX4 토픽 이름 조립(Python 쪽 정본). /fmu 문자열과 버전 접미사는 이 모듈과 px4_raw.py 밖에 쓰지 않는다.

C++의 idsim_common이 하는 일과 같다. 메시지 클래스의 MESSAGE_VERSION이 0보다 크면 이름에 _v<N>을 붙인다.
MESSAGE_VERSION이 없거나 0이면 접미사가 없다. 골든 topics.txt와의 양방향 일치는
test_px4_topic_names.py가 고정한다. rclpy와 px4_msgs를 가져오지 않는다(메시지 클래스는 호출하는 쪽이 준다).
"""

DIRECTIONS = ("in", "out")


def fmu_dir(direction):
    """네임스페이스를 뗀 상대 토픽의 접두("fmu/in/" 또는 "fmu/out/"). 골든과 스모크 도구의 단위 테스트가
    표본 문자열을 만들 때 쓴다(이 모듈 밖에 /fmu 문자열을 쓰지 않으려고 둔다)."""
    if direction not in DIRECTIONS:
        raise ValueError("direction은 in 또는 out: %r" % (direction,))
    return "fmu/%s/" % direction


def message_version(msg_cls):
    """메시지 클래스의 MESSAGE_VERSION. 없으면 0."""
    return int(getattr(msg_cls, "MESSAGE_VERSION", 0))


def px4_topic(ns, direction, base, msg_cls):
    """네임스페이스, 방향(in/out), 기본 이름, 메시지 클래스로 토픽 전체 이름을 만든다.

    예: px4_topic("/px4_1", "out", "vehicle_status", VehicleStatus) -> "/px4_1/fmu/out/vehicle_status_v1".
    ns는 stack.json 표기 그대로(앞 빗금 있음, 끝 빗금 없음)여야 한다.
    """
    if direction not in DIRECTIONS:
        raise ValueError("direction은 in 또는 out: %r" % (direction,))
    if not ns.startswith("/") or ns.endswith("/"):
        raise ValueError("ns는 앞 빗금이 있고 끝 빗금이 없어야 한다: %r" % (ns,))
    if not base or "/" in base:
        raise ValueError("base는 빗금 없는 이름이어야 한다: %r" % (base,))
    ver = message_version(msg_cls)
    suffix = "_v%d" % ver if ver > 0 else ""
    return "%s/fmu/%s/%s%s" % (ns, direction, base, suffix)
