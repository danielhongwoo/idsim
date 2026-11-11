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

# core 소스가 벽시계, rclcpp, px4_msgs 같은 ROS 의존을 쓰지 않는지 본다(decisions.md 쟁점 6 C1).
# 사용법: cmake -DCORE_INCLUDE_DIR=<dir> -DCORE_SRC_DIR=<dir> -P check_core_purity.cmake
# 링크는 CMake 대상이 막고(idsim_mission_core는 ROS 패키지를 링크하지 않는다), 이 검사는
# include와 시계 호출을 문자열로 막는다. 주석 줄은 보지 않는다(설명에 이름이 나올 수 있다).

if(NOT CORE_INCLUDE_DIR OR NOT CORE_SRC_DIR)
  message(FATAL_ERROR "CORE_INCLUDE_DIR and CORE_SRC_DIR are required")
endif()

set(_patterns
  "clock::now"
  "rclcpp"
  "px4_msgs"
  "idsim_common"
  "idsim_interfaces"
  "builtin_interfaces")

set(_files)
foreach(_dir "${CORE_INCLUDE_DIR}" "${CORE_SRC_DIR}")
  file(GLOB_RECURSE _found "${_dir}/*.hpp" "${_dir}/*.cpp")
  list(APPEND _files ${_found})
endforeach()

list(LENGTH _files _count)
if(_count EQUAL 0)
  message(FATAL_ERROR "no core source found under: ${CORE_INCLUDE_DIR} ${CORE_SRC_DIR}")
endif()

set(_bad 0)
foreach(_file ${_files})
  # 줄 단위로 나눈다. CMake 목록 문자(세미콜론, 대괄호, 역빗금)는 먼저 바꿔 둔다.
  file(READ "${_file}" _content)
  string(REPLACE "\\" "/" _content "${_content}")
  string(REPLACE ";" "," _content "${_content}")
  string(REPLACE "[" "(" _content "${_content}")
  string(REPLACE "]" ")" _content "${_content}")
  string(REPLACE "\n" ";" _lines "${_content}")
  set(_lineno 0)
  foreach(_line IN LISTS _lines)
    math(EXPR _lineno "${_lineno} + 1")
    string(REGEX MATCH "^[ \t]*//" _is_comment "${_line}")
    if(_is_comment)
      continue()
    endif()
    foreach(_pattern ${_patterns})
      string(FIND "${_line}" "${_pattern}" _pos)
      if(NOT _pos EQUAL -1)
        message(SEND_ERROR "${_file}:${_lineno}: forbidden in core: '${_pattern}'")
        set(_bad 1)
      endif()
    endforeach()
  endforeach()
endforeach()

if(_bad)
  message(FATAL_ERROR "core purity check failed")
endif()
message(STATUS "core purity: ${_count} files checked")
