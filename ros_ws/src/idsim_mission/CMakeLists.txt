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
project(idsim_mission CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options(-Wall -Wextra -Wpedantic -Werror)

find_package(ament_cmake REQUIRED)

# ---- core: 검증, 분류, 상태기, 종료 결과. ROS와 PX4에 의존하지 않는다 ----
# 이 대상에는 어떤 패키지도 링크하지 않는다(px4_msgs, rclcpp, idsim_common 금지. decisions.md 쟁점 6).
# 어댑터(idsim_mission_px4, P3c)와 노드 껍질(P3d)은 별도 대상으로 이 위에 얹는다.
add_library(idsim_mission_core SHARED
  src/core/mission_runner.cpp
  src/core/mission_validation.cpp
  src/core/names.cpp
  src/core/rules.cpp
  src/core/termination.cpp)
target_include_directories(idsim_mission_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)

install(DIRECTORY include/ DESTINATION include/${PROJECT_NAME})
install(TARGETS idsim_mission_core
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)

if(BUILD_TESTING)
  # ---- ament 린터: xmllint, lint_cmake, cpplint, copyright만(idsim_common과 같다) ----
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_copyright REQUIRED)
  find_package(ament_cmake_cpplint REQUIRED)
  list(APPEND AMENT_LINT_AUTO_EXCLUDE ament_cmake_copyright ament_cmake_cpplint)
  ament_lint_auto_find_test_dependencies()
  ament_copyright()
  ament_cpplint()

  # ---- core 순수성: core 소스에 벽시계, rclcpp, px4_msgs 같은 의존이 없다 ----
  ament_add_test(core_purity
    GENERATE_RESULT_FOR_RETURN_CODE_ZERO
    COMMAND ${CMAKE_COMMAND}
      -DCORE_INCLUDE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/include/idsim_mission/core
      -DCORE_SRC_DIR=${CMAKE_CURRENT_SOURCE_DIR}/src/core
      -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/check_core_purity.cmake)

  # 검사기의 음성 시험: 금지 문자열마다 한 줄씩 심은 임시 파일(빌드 디렉터리)에서 그 수만큼 걸리고,
  # 주석 줄의 금지 문자열은 걸리지 않아야 한다.
  set(_purity_neg "${CMAKE_CURRENT_BINARY_DIR}/core_purity_negative")
  file(WRITE "${_purity_neg}/src/bad.cpp" "// rclcpp in a comment is allowed\n")
  foreach(_bad_line
      "auto a = std::chrono::steady_clock::now()"
      "clock_gettime(CLOCK_MONOTONIC, &ts)"
      "gettimeofday(&tv, nullptr)"
      "auto b = std::time(nullptr)"
      "std::this_thread::yield()"
      "auto c = std::getenv(name)"
      "#include <rclcpp/rclcpp.hpp>"
      "#include <px4_msgs/msg/vehicle_status.hpp>"
      "#include <idsim_common/vehicle.hpp>"
      "#include <idsim_interfaces/msg/mission.hpp>"
      "#include <builtin_interfaces/msg/time.hpp>")
    file(APPEND "${_purity_neg}/src/bad.cpp" "${_bad_line}\n")
  endforeach()
  file(WRITE "${_purity_neg}/include/ok.hpp" "// clean\n")
  ament_add_test(core_purity_negative
    GENERATE_RESULT_FOR_RETURN_CODE_ZERO
    COMMAND ${CMAKE_COMMAND}
      -DCORE_INCLUDE_DIR=${_purity_neg}/include
      -DCORE_SRC_DIR=${_purity_neg}/src
      -DEXPECT_VIOLATIONS=11
      -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/check_core_purity.cmake)

  # ---- core 단위 테스트. gtest와 core만 링크한다(노드와 DDS 참가자를 만들지 않는다) ----
  find_package(ament_cmake_gtest REQUIRED)
  set(_core_tests
    test_mission_validation
    test_termination
    test_monitor_table
    test_confirm_rules
    test_runner_preparing
    test_runner_items
    test_runner_land
    test_runner_cleanup
    test_runner_conflicts)
  foreach(_test ${_core_tests})
    ament_add_gtest(${_test} test/${_test}.cpp)
    target_link_libraries(${_test} idsim_mission_core)
  endforeach()
endif()

ament_package()
