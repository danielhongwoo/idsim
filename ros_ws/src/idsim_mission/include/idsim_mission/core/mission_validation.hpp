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
// 검증은 두 층이다.
// - validate_mission_contract: 계약(Mission, MissionItem 주석)의 규칙. Phase 3에 Fleet이 같이
//   쓸 수 있게 1a 제한을 넣지 않는다.
// - validate_mission_1a_goal: 계약 + 1a 임시 제한(계약 문장이 아니다). type은 TAKEOFF, LOITER,
//   LAND만, 마지막은 LAND이고 LAND는 마지막에만, 첫 항목은 TAKEOFF 또는 LAND(그래서 LAND로
//   시작하면 길이 1). goal 접수(screen_goal)가 쓴다.
// - validate_mission_runnable: 계약 + runner가 아직 실행하지 못하는 미션의 제한. MissionRunner
//   생성자가 쓴다. validate_mission_1a_goal이 받는 미션은 이것도 받는다.

#ifndef IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_
#define IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_

#include <optional>
#include <string>

#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

struct MissionCheck
{
  bool valid{false};
  std::string detail;  // valid가 false일 때 이유(항목 index와 필드 이름 포함)
};

// mission_id가 ^[a-z0-9][a-z0-9_-]{0,63}$인가.
bool is_valid_mission_id(const std::string & mission_id);

MissionCheck validate_mission_contract(const MissionSpec & mission);
MissionCheck validate_mission_1a_goal(const MissionSpec & mission);
MissionCheck validate_mission_runnable(const MissionSpec & mission);

// handle_accepted의 즉시 판정. goal과 노드 자신의 상태만 본다. 순서는 VEHICLE_ID_MISMATCH ->
// INVALID_MISSION -> BUSY다(틀린 기체로 온 goal에 BUSY를 주면 Fleet이 다른 기체로 재시도해
// 설정 오류를 덮는다). 끝낼 goal이면 Termination(ABORTED, 완료 0, index 0), 실행할 goal이면
// nullopt. 이 경우들은 feedback 0건이다(M1).
std::optional<Termination> screen_goal(
  const std::string & goal_vehicle_id, const std::string & own_vehicle_id,
  const MissionSpec & mission, bool busy);

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__MISSION_VALIDATION_HPP_
