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

"""통합 테스트가 보내는 미션: 시나리오 B의 무효 사례 표와 비행 시나리오(F1-F4)의 미션 YAML. 순수 코드다(rclpy 없음).

항목 dict는 미션 YAML 로더(idsim_mission/mission_yaml.py, 형식의 정본은 그 모듈 docstring)의 항목 형식 그대로다.
type은 이름(TAKEOFF, GOTO, ...)이고 key는 로더의 ITEM_KEYS다. mission_client가 로더의 parse_mission과
to_mission_msg로 goal을 만든다. 예외 하나: default_sub가 참인 항목은 로더가 만들 수 없는 "서브메시지가 모두
기본값"(yaw.mode 0 포함)인 항목이고, mission_client가 로더 출력의 그 서브메시지를 기본값으로 되돌린다.

로더의 import 위치: lint job의 pytest(tests/support)에는 ROS와 idsim_mission 설치가 없다. 로더의 parse_mission,
load_mission은 순수 Python(PyYAML)이므로 저장소의 소스 파일을 경로로 읽는다(mission_yaml()). runner(ros-ws)
안에서도 같은 소스를 읽는다(같은 commit이고 저장소가 /opt/idsim에 마운트된다). 그래서 시간 합산 단정
(test_sitl_flight_missions.py)은 lint job에서 돈다.

시나리오 B의 사례마다 어기는 규칙은 하나이고, 나머지 항목과 필드는 계약 검증(validate_mission_contract)을 통과하는
값이다. 그래야 INVALID_MISSION이 의도한 규칙에서 나온다.
"""
import importlib.util
import sys
from pathlib import Path

from tests.support import sitl_judge as sj

REPO = Path(__file__).resolve().parents[2]
LOADER_PATH = REPO / "ros_ws" / "src" / "idsim_mission" / "idsim_mission" / "mission_yaml.py"
MISSIONS_DIR = REPO / "tests" / "sitl" / "missions"
SITL_FLEET = REPO / "tests" / "sitl" / "fleet.yaml"

# 비행 시나리오와 미션 파일(tests/sitl/missions/). 끝 상태는 sitl_judge.TERMINAL_*(README "시나리오와 판정"의 표)
FLIGHT_MISSIONS = {"F1": "f1.yaml", "F2": "f2.yaml", "F3": "f3.yaml", "F4": "f4.yaml"}
FLIGHT_TERMINAL = {"F1": sj.TERMINAL_LANDED_DISARMED, "F2": sj.TERMINAL_HOLD_AIRBORNE,
                   "F3": sj.TERMINAL_LANDED_DISARMED, "F4": sj.TERMINAL_LANDED_DISARMED}
# 공중에서 시작하는 시나리오와 그 기준점을 넘겨주는 앞 비행(F3은 F2가 남긴 Hold에서 시작한다)
AIR_START = {"F3": "F2"}

# 시간 규칙(README "시나리오와 판정"): 비행마다 항목 timeout 합 + FLIGHT_MARGIN_S가 FLIGHT_LIMIT_S(ROS 시각 3분)를 넘지 않는다.
# FLIGHT_MARGIN_S는 새로 정한 값이다. 항목 timeout에 들지 않는 구간, 곧 준비 단계(식별, Offboard 진입, arm.
# 시나리오 A에서 goal 전송부터 TAKEOFF 시작까지 약 5 s)와 종료 단계(공중 종료의 Hold 확인, 착륙 뒤 disarm 확인과
# 대비책 지연 5 s)에 여유를 더한 [추정]이다. 판정은 이 합을 goal 결과 대기의 ROS 시각 상한으로 쓴다.
FLIGHT_LIMIT_S = 180.0
FLIGHT_MARGIN_S = 30.0
# TRACK_ENTITY timeout의 하한(README "시나리오와 판정"): 항목 시작점(직전 GOTO 목표)에서 loop 궤적 위 가장 먼 점까지의 거리를
# APPROACH_SPEED_MPS로 따라잡는 시간 + TRACK_COMPLETION_MARGIN_S. 둘 다 새로 정한 [추정]이다. 접근 속도는 표적
# 최고 속도 2 m/s에서 기체가 적어도 그만큼 더 빨리 다가간다고 본 보수적 값이다(Offboard 위치 setpoint의 수평
# 속도 상한 MPC_XY_VEL_MAX 기본 12 m/s보다 훨씬 작다). 완료 마진은 접근 뒤 반경 안 3표본 확인과 모서리에서의
# 추종 오차 회복을 덮는다.
APPROACH_SPEED_MPS = 2.0
TRACK_COMPLETION_MARGIN_S = 10.0

# 시나리오 B와 시나리오 A, D의 항목 값
TAKEOFF_M = 5.0
ACCEPTANCE_M = 0.3
TRACK_TARGET_ID = "car_1"   # 형식이 맞는 id. 있는지는 검증하지 않으므로(계약) 스택의 표적과 무관하다
BAD_TARGET_ID = "Car-1"     # ^[a-z][a-z0-9_]{0,31}$에 어긋나는 id(대문자와 하이픈)

_LOADER = {}


def mission_yaml():
    """미션 YAML 로더 모듈(idsim_mission/mission_yaml.py)을 저장소 소스 경로에서 읽는다(위 모듈 설명)."""
    if "m" not in _LOADER:
        spec = importlib.util.spec_from_file_location("idsim_sitl_mission_yaml", LOADER_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod        # dataclass가 모듈을 찾는다
        spec.loader.exec_module(mod)
        _LOADER["m"] = mod
    return _LOADER["m"]


def load_flight(sid):
    """비행 시나리오의 미션 YAML을 로더로 읽은 MissionSpec(기본값이 채워진 뒤)."""
    return mission_yaml().load_mission(MISSIONS_DIR / FLIGHT_MISSIONS[sid])


def duration_s(d):
    """로더의 DurationSpec -> 초."""
    return d.sec + d.nanosec / 1e9


def timeout_sum_s(spec):
    """MissionSpec의 항목 timeout 합(초)."""
    return sum(duration_s(it.timeout) for it in spec.items)


def flight_wait_s(spec):
    """goal 결과를 기다리는 ROS 시각 상한: 항목 timeout 합 + FLIGHT_MARGIN_S."""
    return timeout_sum_s(spec) + FLIGHT_MARGIN_S


def type_name(type_value):
    """MissionItem.TYPE_* 값 -> 로더의 이름."""
    return {v: k for k, v in mission_yaml().ITEM_TYPES.items()}[type_value]


def takeoff_item():
    return {"type": "TAKEOFF", "timeout_s": 20.0, "height_m": TAKEOFF_M, "acceptance_m": ACCEPTANCE_M}


def loiter_item(duration_s=5.0, timeout_s=10.0):
    return {"type": "LOITER", "timeout_s": timeout_s, "duration_s": duration_s}


def land_item():
    return {"type": "LAND", "timeout_s": 30.0}


def rtl_item():
    return {"type": "RTL", "timeout_s": 60.0}


def goto_item(position=(10.0, 0.0, 5.0)):
    return {"type": "GOTO", "timeout_s": 10.0, "position": list(position), "acceptance_radius_m": 1.0}


def track_item(offset=(0.0, 0.0, 5.0), target_id=TRACK_TARGET_ID):
    return {"type": "TRACK_ENTITY", "timeout_s": 30.0, "target_id": target_id, "offset": list(offset),
            "acceptance_radius_m": 1.0}


def default_sub_item(item_type, timeout_s=30.0):
    """type과 timeout만 채우고 서브메시지는 기본값으로 둔 항목(로더 형식 밖. mission_client가 처리한다)."""
    return {"type": item_type, "timeout_s": timeout_s, "default_sub": True}


# 시나리오 B의 무효 사례(README "시나리오와 판정"). 이 순서로 보낸다. (mission_id, 걸리는 검사, 기대 detail 조각, 항목)
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
     "items[1].track_entity.target_id '' does not match", [takeoff_item(), default_sub_item("TRACK_ENTITY")]),
)
