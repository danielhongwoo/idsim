cmake_minimum_required(VERSION 3.8)
project(idsim_common CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options(-Wall -Wextra -Wpedantic -Werror)

find_package(ament_cmake REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(px4_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(rmw REQUIRED)
find_package(rosidl_runtime_cpp REQUIRED)

add_library(${PROJECT_NAME} SHARED
  src/frames.cpp
  src/px4_timestamp.cpp
  src/qos.cpp
  src/vehicle.cpp
  src/vehicle_command.cpp)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
target_link_libraries(${PROJECT_NAME} PUBLIC
  Eigen3::Eigen
  ${px4_msgs_TARGETS}
  rclcpp::rclcpp
  rmw::rmw
  rosidl_runtime_cpp::rosidl_runtime_cpp)

install(DIRECTORY include/ DESTINATION include/${PROJECT_NAME})
install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(eigen3_cmake_module Eigen3 px4_msgs rclcpp rclcpp_lifecycle rmw rosidl_runtime_cpp)

if(BUILD_TESTING)
  # ---- ament 린터: xmllint, lint_cmake, cpplint만. uncrustify, copyright, cppcheck는 쓰지 않는다 ----
  # cpplint의 legal/copyright는 라이선스 결정 전까지 끈다.
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_cpplint REQUIRED)
  list(APPEND AMENT_LINT_AUTO_EXCLUDE ament_cmake_cpplint)
  ament_lint_auto_find_test_dependencies()
  ament_cpplint(FILTERS "-legal/copyright")

  # ---- 골든 경로: 태그와 px4_msgs 커밋은 docker/versions.env에서만 읽는다 ----
  set(IDSIM_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." CACHE PATH "idsim repository root (holds docker/versions.env)")
  get_filename_component(_idsim_repo_root "${IDSIM_REPO_ROOT}" ABSOLUTE)
  set(_idsim_versions_env "${_idsim_repo_root}/docker/versions.env")
  if(NOT EXISTS "${_idsim_versions_env}")
    message(FATAL_ERROR "versions.env not found: ${_idsim_versions_env} (set -DIDSIM_REPO_ROOT=<repository root>)")
  endif()
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_idsim_versions_env}")

  function(idsim_read_version key out_var)
    file(STRINGS "${_idsim_versions_env}" _lines REGEX "^${key}=")
    list(LENGTH _lines _count)
    if(NOT _count EQUAL 1)
      message(FATAL_ERROR "${_idsim_versions_env}: expected exactly one '${key}=' line, found ${_count}")
    endif()
    string(REGEX REPLACE "^${key}=" "" _value "${_lines}")
    string(STRIP "${_value}" _value)
    if(_value STREQUAL "")
      message(FATAL_ERROR "${_idsim_versions_env}: '${key}' is empty")
    endif()
    set(${out_var} "${_value}" PARENT_SCOPE)
  endfunction()

  idsim_read_version(PX4_TAG _idsim_px4_tag)
  idsim_read_version(PX4_MSGS_REF _idsim_px4_msgs_ref)
  set(_idsim_fixture_dir "${_idsim_repo_root}/tests/fixtures/px4/${_idsim_px4_tag}")
  if(NOT IS_DIRECTORY "${_idsim_fixture_dir}")
    message(FATAL_ERROR "PX4 golden fixture directory not found: ${_idsim_fixture_dir}")
  endif()
  set(_idsim_golden_env
    "IDSIM_PX4_FIXTURE_DIR=${_idsim_fixture_dir}"
    "IDSIM_PX4_MSGS_REF=${_idsim_px4_msgs_ref}")

  # ---- 단위 테스트. 노드와 DDS 참가자를 만들지 않는다 ----
  find_package(ament_cmake_gtest REQUIRED)
  find_package(geometry_msgs REQUIRED)
  find_package(px4_ros_com REQUIRED)
  find_package(rcl REQUIRED)
  find_package(sensor_msgs REQUIRED)

  ament_add_gtest(test_frames test/test_frames.cpp)
  target_link_libraries(test_frames ${PROJECT_NAME})
  # px4_ros_com frame_transforms는 차등 비교 기준(oracle)으로만 쓴다.
  target_include_directories(test_frames SYSTEM PRIVATE ${px4_ros_com_INCLUDE_DIRS})
  target_link_libraries(test_frames px4_ros_com::frame_transforms ${geometry_msgs_TARGETS} ${sensor_msgs_TARGETS})

  ament_add_gtest(test_topics_traits test/test_topics_traits.cpp)
  target_link_libraries(test_topics_traits ${PROJECT_NAME} rclcpp_lifecycle::rclcpp_lifecycle)

  ament_add_gtest(test_topics_golden test/test_topics_golden.cpp ENV ${_idsim_golden_env})
  target_link_libraries(test_topics_golden ${PROJECT_NAME})

  ament_add_gtest(test_qos test/test_qos.cpp ENV ${_idsim_golden_env})
  target_link_libraries(test_qos ${PROJECT_NAME})

  ament_add_gtest(test_px4_timestamp test/test_px4_timestamp.cpp)
  target_link_libraries(test_px4_timestamp ${PROJECT_NAME} rcl::rcl)

  ament_add_gtest(test_vehicle test/test_vehicle.cpp)
  target_link_libraries(test_vehicle ${PROJECT_NAME})

  ament_add_gtest(test_vehicle_command test/test_vehicle_command.cpp)
  target_link_libraries(test_vehicle_command ${PROJECT_NAME})

  # ---- 음성 컴파일 테스트: 빌드가 실패하고 기대한 static_assert 문구가 나와야 통과 ----
  # 타깃은 EXCLUDE_FROM_ALL이라 colcon build에서는 컴파일하지 않고, 테스트가 cmake --build로 부른다.
  set(_neg_publish_out_regex "publish only to /fmu/in descriptors")
  set(_neg_publish_restricted_regex "publishing to this /fmu/in topic is restricted")
  set(_neg_missing_full_header_regex "include the full px4_msgs/msg/<name>.hpp")
  set(_neg_unregistered_regex "not a registered px4 topic descriptor")
  foreach(_neg publish_out publish_restricted missing_full_header unregistered)
    add_library(neg_${_neg} OBJECT EXCLUDE_FROM_ALL test/compile_fail/neg_${_neg}.cpp)
    target_link_libraries(neg_${_neg} ${PROJECT_NAME})
    ament_add_test(neg_compile_${_neg}
      GENERATE_RESULT_FOR_RETURN_CODE_ZERO
      COMMAND ${CMAKE_COMMAND}
        -DBUILD_DIR=${CMAKE_BINARY_DIR}
        -DTARGET=neg_${_neg}
        "-DEXPECT_REGEX=${_neg_${_neg}_regex}"
        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/expect_compile_fail.cmake
      TIMEOUT 300)
    set_tests_properties(neg_compile_${_neg} PROPERTIES RESOURCE_LOCK idsim_common_build_dir)
  endforeach()
endif()

ament_package()
