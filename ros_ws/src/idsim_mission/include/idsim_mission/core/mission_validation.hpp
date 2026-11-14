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
// 검증 함수는 셋이고 모두 계약 검증을 먼저 부른다(1b decisions.md 쟁점 12 "미션 제한의 두 자리").
// - validate_mission_contract: 계약(Mission, MissionItem 주석)의 규칙. 필드 검사 뒤에 순서
//   규칙(TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만)을 본다. Phase 3에 Fleet이 같이
//   쓸 수 있게 1a 제한을 넣지 않는다.
// - validate_mission_1a_goal: 계약 + 1a 임시 제한(계약 문장이 아니다). type은 TAKEOFF, LOITER,
//   LAND만, 마지막은 LAND, 첫 항목은 TAKEOFF 또는 LAND(계약 순서 규칙과 합쳐 LAND로 시작하면
//   길이 1). goal 접수(screen_goal)가 쓴다. B9 동안 받는 미션 집합은 1a 그대로다.
// - validate_mission_runnable: 계약 + runner가 아직 실행하지 못하는 미션의 제한. type은
//   TAKEOFF, LOITER, LAND, RTL만, 첫 항목은 TAKEOFF, LAND, RTL. 마지막 항목은 계약 순서 규칙
//   말고는 제한하지 않는다(마지막이 setpoint 항목이면 공중 종료 단계로 끝난다).
//   MissionRunner 생성자가 쓴다. validate_mission_1a_goal이 받는 미션은 이것도 받는다. 문구는
//   사용자에게 닿지 않는다(노드는 screen_goal이 먼저 끝낸다).

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
