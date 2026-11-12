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

// 계약 메시지(idsim_interfaces) <-> core 값 타입의 변환. 노드 껍질만 쓴다. 순수 함수다.
//
// - goal의 Mission -> core::MissionSpec: 필드를 그대로 옮긴다(좌표와 yaw는 계약 그대로 world ENU).
// - core::Termination -> ExecuteMission result와 종료 MissionEvent: 둘 다 같은 Termination에서
//   core::to_result, core::to_terminal_event로 만든다(종료 결과 == 종료 사건).
// - core::Feedback -> ExecuteMission feedback. stamp는 core::Feedback.stamp_ns(그 tick의 입력
//   시각)다.
// 사건의 stamp는 노드 시계의 ROS 시각이고 호출자가 넘긴다. tick에서 정한 종료의 사건은 그 tick의
// 입력 시각을 넘긴다.

#ifndef IDSIM_MISSION__NODE__CONVERSION_HPP_
#define IDSIM_MISSION__NODE__CONVERSION_HPP_

#include <array>
#include <cstdint>
#include <string>

#include "builtin_interfaces/msg/time.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_mission/core/mission_runner.hpp"
#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission
{

using GoalId = std::array<std::uint8_t, 16>;

core::MissionSpec to_mission_spec(const idsim_interfaces::msg::Mission & mission);

idsim_interfaces::action::ExecuteMission::Result to_result_msg(const core::Termination & term);

// 사건에서 노드가 정하는 필드.
struct EventContext
{
  builtin_interfaces::msg::Time stamp;
  std::string vehicle_id;
  std::string mission_id;
  GoalId goal_id{};
  std::uint32_t item_count{0};
};

idsim_interfaces::msg::MissionEvent accepted_event_msg(const EventContext & context);
idsim_interfaces::msg::MissionEvent terminal_event_msg(
  const EventContext & context, const core::Termination & term);

// ROS 시각(ns)을 메시지 시각으로. nanosec은 [0, 1e9)이고 음수 시각은 sec를 내린다.
builtin_interfaces::msg::Time to_time_msg(std::int64_t ns);

idsim_interfaces::action::ExecuteMission::Feedback to_feedback_msg(const core::Feedback & feedback);

}  // namespace idsim_mission

#endif  // IDSIM_MISSION__NODE__CONVERSION_HPP_
