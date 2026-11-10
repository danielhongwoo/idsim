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

cmake_minimum_required(VERSION 3.8)
project(idsim_interfaces)

# rosidl 전용 패키지다. 손으로 쓴 코드를 넣지 않고, 생성 코드가 대상이라 -Werror 같은 컴파일 옵션도 넣지 않는다.
# 필드와 상수를 바꾸면 test/golden/이 함께 바뀌어야 한다(계약 변경 절차를 따른다).

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GoToItem.msg"
  "msg/LoiterItem.msg"
  "msg/Mission.msg"
  "msg/MissionEvent.msg"
  "msg/MissionItem.msg"
  "msg/TakeoffItem.msg"
  "msg/TargetState.msg"
  "msg/TrackEntityItem.msg"
  "msg/VehicleState.msg"
  "msg/YawSetpoint.msg"
  "action/ExecuteMission.action"
  DEPENDENCIES builtin_interfaces geometry_msgs std_msgs)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  # ---- ament 린터: xmllint, lint_cmake, copyright. C++ 소스가 없어 cpplint는 넣지 않는다 ----
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_copyright REQUIRED)
  list(APPEND AMENT_LINT_AUTO_EXCLUDE ament_cmake_copyright)
  ament_lint_auto_find_test_dependencies()
  ament_copyright()

  # ---- 계약 테스트: type hash, 펼친 정의, 직접 정의 golden과 상수 검사 ----
  # 설치된 share와 `ros2 interface show`를 읽으므로 이 패키지의 환경 안에서 돈다.
  # golden은 소스 디렉터리(test/golden/)에서 읽는다. 갱신은 IDSIM_UPDATE_GOLDEN=1 (test/test_contract.py 머리말).
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_contract test/test_contract.py TIMEOUT 120)
endif()

ament_package()
