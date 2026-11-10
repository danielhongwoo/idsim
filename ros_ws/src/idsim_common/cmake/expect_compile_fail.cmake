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

# 음성 컴파일 테스트. 대상 타깃의 빌드가 실패하고, 출력에 기대 문구가 있어야 통과한다.
# 사용: cmake -DBUILD_DIR=<빌드 디렉터리> -DTARGET=<타깃> -DEXPECT_REGEX=<정규식> -P expect_compile_fail.cmake
foreach(var BUILD_DIR TARGET EXPECT_REGEX)
  if(NOT DEFINED ${var} OR "${${var}}" STREQUAL "")
    message(FATAL_ERROR "expect_compile_fail: ${var} is not set")
  endif()
endforeach()

execute_process(
  COMMAND ${CMAKE_COMMAND} --build ${BUILD_DIR} --target ${TARGET}
  RESULT_VARIABLE rc
  OUTPUT_VARIABLE out
  ERROR_VARIABLE err)
set(all "${out}${err}")

if(rc EQUAL 0)
  message(FATAL_ERROR "target ${TARGET} compiled but must not")
endif()
if(NOT all MATCHES "${EXPECT_REGEX}")
  message(FATAL_ERROR "target ${TARGET} failed for an unexpected reason (expected /${EXPECT_REGEX}/):\n${all}")
endif()
message(STATUS "target ${TARGET} failed as expected: /${EXPECT_REGEX}/")
