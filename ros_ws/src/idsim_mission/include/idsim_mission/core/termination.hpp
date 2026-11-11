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

// 종료 결과. goal 하나의 끝은 Termination 하나로 정하고, action result와 종료 사건
// (MissionEvent)은 둘 다 이 객체에서 만든다(종료 사건은 정확히 1건. decisions.md 쟁점 3 "종료의
// 충돌 규칙").
// 노드는 to_result와 to_terminal_event의 값을 메시지에 옮기기만 한다. 사건의 stamp, vehicle_id,
// mission_id, goal_id는 노드가 채운다.
//
// status와 reason의 대응(ExecuteMission result 주석): SUCCEEDED와 CANCELED이면 REASON_NONE,
// ABORTED이면 REASON_NONE이 아니다. 그래서 REASON_NONE이 아닌 reason은 ABORTED 하나에만
// 대응하고, REASON_NONE은 SUCCEEDED와 CANCELED에 대응한다.

#ifndef IDSIM_MISSION__CORE__TERMINATION_HPP_
#define IDSIM_MISSION__CORE__TERMINATION_HPP_

#include <cstdint>
#include <string>

#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

struct Termination
{
  Status status{Status::kAborted};
  Reason reason{Reason::kInternal};
  std::uint32_t items_completed{0};
  std::uint32_t last_item_index{0};  // 항목을 시작하기 전에 끝났으면 0
  std::string detail;
};

// status와 reason이 함께 쓰일 수 있는가(위 대응).
bool is_consistent(Status status, Reason reason);

// MissionEvent.STATUS_*. 값은 action_msgs/GoalStatus와 같다.
namespace event_status
{
inline constexpr std::uint8_t kUnknown = 0;
inline constexpr std::uint8_t kAccepted = 1;
inline constexpr std::uint8_t kSucceeded = 4;
inline constexpr std::uint8_t kCanceled = 5;
inline constexpr std::uint8_t kAborted = 6;
}  // namespace event_status

std::uint8_t event_status_code(Status status);

// ExecuteMission result의 필드.
struct ResultFields
{
  std::uint8_t reason{0};
  std::uint32_t items_completed{0};
  std::uint32_t last_item_index{0};
  std::string detail;
};

// MissionEvent에서 core가 정하는 필드.
struct EventFields
{
  std::uint8_t status{event_status::kUnknown};
  std::uint8_t reason{0};
  std::uint32_t item_count{0};
  std::uint32_t items_completed{0};
  std::uint32_t last_item_index{0};
  std::string detail;
};

ResultFields to_result(const Termination & termination);
EventFields to_terminal_event(const Termination & termination, std::uint32_t item_count);
// 접수 사건. reason은 REASON_NONE, 완료 수와 index는 0, detail은 빈 문자열.
EventFields accepted_event(std::uint32_t item_count);

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__TERMINATION_HPP_
