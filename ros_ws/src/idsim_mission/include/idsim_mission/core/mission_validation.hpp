// Copyright 2026 Daniel Hongwoo Lee
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// 미션의 정적 검증과 goal 접수 직후의 즉시 판정(decisions.md 쟁점 3 M1, 쟁점 4).
//
// - validate_mission_contract: 계약(Mission, MissionItem 주석)의 규칙. 필드 검사 뒤에 순서
//   규칙(TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만)을 본다. 필드 검사에는 좌표 상한(GOTO
//   position과 TRACK_ENTITY offset의 각 성분 절댓값 kMaxContractCoordinateM 이하, 유한 검사 뒤. 1b
//   decisions.md 쟁점 8)과 TRACK_ENTITY target_id 형식(is_valid_target_id)이 든다. goal 접수
//   (screen_goal)와 MissionRunner 생성자가 이것을 부른다(runner는 계약 valid 미션을 모두 실행한다.
//   첫 항목이 LOITER, GOTO, TRACK_ENTITY이면 공중 Offboard 진입, 마지막이 setpoint 항목이면 공중
//   종료 단계). runner의 문구는 사용자에게 닿지 않는다(노드는 screen_goal이 먼저 끝낸다).
// - within_coordinate_bound: 계약 좌표 상한 술어. 미션 검증과 노드의 표적 표본 변환
//   (node/conversion.cpp)이 함께 쓴다(1b decisions.md 쟁점 8 "좌표 상한").

#ifndef IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_
#define IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_

#include <optional>
#include <string>

#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

// 계약 좌표 상한(m). GOTO position, TRACK_ENTITY offset, 유효 표적 표본 위치의 각 성분 절댓값이 이
// 값 이하(경계 포함)여야 한다. 1b decisions.md 쟁점 8 "좌표 상한"의 값이다. 올리는 쪽이 호환된다
// (받던 미션과 표본을 계속 받는다).
inline constexpr double kMaxContractCoordinateM = 1e5;

// 모든 성분의 절댓값이 kMaxContractCoordinateM 이하인가. 비교가 NaN과 inf에서 거짓이므로 비유한
// 성분도 거짓이다.
bool within_coordinate_bound(const Vec3 & v);

struct MissionCheck
{
  bool valid{false};
  std::string detail;  // valid가 false일 때 이유(항목 index와 필드 이름 포함)
};

// mission_id가 ^[a-z0-9][a-z0-9_-]{0,63}$인가.
bool is_valid_mission_id(const std::string & mission_id);

// target_id가 ^[a-z][a-z0-9_]{0,31}$인가(TargetState.target_id의 규칙). core는 idsim_common에
// 의존하지 않으므로 같은 규칙을 여기 둔다. idsim_common::TargetId::parse와 같은 답인지는
// test/node/test_contract_constants.cpp가 사례 표로 대조한다.
bool is_valid_target_id(const std::string & target_id);

MissionCheck validate_mission_contract(const MissionSpec & mission);

// handle_accepted의 즉시 판정. goal과 노드 자신의 상태만 본다. 순서는 VEHICLE_ID_MISMATCH ->
// INVALID_MISSION -> BUSY다(틀린 기체로 온 goal에 BUSY를 주면 Fleet이 다른 기체로 재시도해
// 설정 오류를 덮는다). 끝낼 goal이면 Termination(ABORTED, 완료 0, index 0), 실행할 goal이면
// nullopt. 이 경우들은 feedback 0건이다(M1).
std::optional<Termination> screen_goal(
  const std::string & goal_vehicle_id, const std::string & own_vehicle_id,
  const MissionSpec & mission, bool busy);

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_
