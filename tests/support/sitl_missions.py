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

"""통합 테스트가 보내는 미션 항목(dict)과 시나리오 B의 무효 사례 표. 순수 코드다(rclpy 없음).

항목 dict는 mission_client.MissionClient.build_goal의 입력이다. 사례마다 어기는 규칙은 하나이고, 나머지 항목과
필드는 계약 검증(validate_mission_contract)을 통과하는 값이다. 그래야 INVALID_MISSION이 의도한 규칙에서 나온다.
"""
from tests.support import sitl_judge as sj

TAKEOFF_M = 5.0
ACCEPTANCE_M = 0.3
TRACK_TARGET_ID = "car_1"   # 형식이 맞는 id. 있는지는 검증하지 않으므로(계약) 스택의 표적과 무관하다
BAD_TARGET_ID = "Car-1"     # ^[a-z][a-z0-9_]{0,31}$에 어긋나는 id(대문자와 하이픈)


def takeoff_item():
    return {"type": sj.TYPE_TAKEOFF, "timeout_s": 20.0, "height_m": TAKEOFF_M, "acceptance_m": ACCEPTANCE_M}


def loiter_item(duration_s=5.0, timeout_s=10.0):
    return {"type": sj.TYPE_LOITER, "timeout_s": timeout_s, "duration_s": duration_s}


def land_item():
    return {"type": sj.TYPE_LAND, "timeout_s": 30.0}


def rtl_item():
    return {"type": sj.TYPE_RTL, "timeout_s": 60.0}


def goto_item(position=(10.0, 0.0, 5.0)):
    return {"type": sj.TYPE_GOTO, "timeout_s": 10.0, "position": position, "acceptance_m": 1.0}


def track_item(offset=(0.0, 0.0, 5.0), target_id=TRACK_TARGET_ID):
    return {"type": sj.TYPE_TRACK_ENTITY, "timeout_s": 30.0, "target_id": target_id, "offset": offset,
            "acceptance_m": 1.0}


def default_sub_item(item_type, timeout_s=30.0):
    """type과 timeout만 채우고 서브메시지는 기본값으로 둔 항목."""
    return {"type": item_type, "timeout_s": timeout_s, "default_sub": True}


# 시나리오 B의 1b 무효 사례(decisions.md 쟁점 15). 이 순서로 보낸다. (mission_id, 걸리는 검사, 기대 detail 조각, 항목)
# 형식이 맞지만 없는 target_id는 계약상 유효하므로(TARGET_LOST로 드러난다) 넣지 않는다.
# detail 조각은 계약이 아니다(validate_mission_contract의 문구, mission_validation.cpp). 사례가 의도한 검사에서
# 거부되는지 보려고 기대는 것이므로, 문구가 바뀌면 이 표를 같이 고친다.
B_INVALID_CASES = (
    ("b-empty", "항목 1개 이상", "mission has no items", []),
    ("b-takeoff-not-first", "TAKEOFF는 첫 항목에만", "items[1].type TAKEOFF is allowed only as the first item",
     [goto_item(), takeoff_item()]),
    ("b-land-goto", "LAND는 마지막 항목에만", "items[0].type LAND is allowed only as the last item",
     [land_item(), goto_item()]),
    ("b-rtl-not-last", "RTL은 마지막 항목에만(가운데)", "items[1].type RTL is allowed only as the last item",
     [takeoff_item(), rtl_item(), land_item()]),
    ("b-rtl-first", "RTL은 마지막 항목에만(첫 항목)", "items[0].type RTL is allowed only as the last item",
     [rtl_item(), goto_item()]),
    ("b-track-zero-offset", "TRACK_ENTITY offset은 0 벡터가 아니다",
     "items[1].track_entity.offset must be finite and non-zero", [takeoff_item(), track_item(offset=(0.0, 0.0, 0.0))]),
    ("b-track-bad-target-id", "TRACK_ENTITY target_id 형식", "items[1].track_entity.target_id 'Car-1' does not match",
     [takeoff_item(), track_item(target_id=BAD_TARGET_ID)]),
    # 서브메시지가 모두 기본값이면 검사 순서상 첫 필드 검사(target_id 형식, 빈 문자열)에서 거부된다
    ("b-track-default", "기본값 TRACK_ENTITY 서브메시지(빈 target_id)",
     "items[1].track_entity.target_id '' does not match", [takeoff_item(), default_sub_item(sj.TYPE_TRACK_ENTITY)]),
)
