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

// PX4 어댑터의 입력 쪽: px4_msgs 표본 -> core::Snapshot의 각 표본. 소유 px4-engineer.
//
// 대응표의 정본은 core/snapshot.hpp 머리 주석이다. 이 파일은 그 표를 함수로 옮긴 것이다. PX4 enum
// 값은 숫자가 아니라 px4_msgs의 상수 이름으로 비교한다.
//
// 모두 순수 함수다(노드, 시계, DDS 없음). 노드(P3d)의 구독 callback이 표본을 받으면 그 callback이
// 지금의 "다음 step tick 번호"와 노드 시계 ROS 시각을 Received로 넘겨 이 함수를 부르고, 결과를
// Snapshot의 해당 optional에 덮어쓴다(토픽마다 최신 하나). 예:
//
//   snapshot.status = to_status_sample(*msg, identity, Received{next_tick, now_ns});
//   snapshot.flags = to_flags_sample(*msg, next_tick);
//   if (auto ack = to_ack_sample(*msg, source, next_tick)) { snapshot.ack = *ack; }
//
// 비유한 값(NaN): vehicle_local_position의 x, y, z, heading은 PX4가 무효일 때 NaN을
// 싣는다. 어댑터는 그 값을 바꾸지 않고 double NaN으로 넘긴다(core가 P3에서 유한할 때까지
// 기다리고 지상 setpoint는 대체값을 쓴다. README "표에 없어 구현에서 정한 것" 5번, 16번).
// 다른 입력 필드에는 부동소수가 없다.

#ifndef IDSIM_MISSION__PX4__INPUTS_HPP_
#define IDSIM_MISSION__PX4__INPUTS_HPP_

#include <cstdint>
#include <optional>

#include "idsim_common/vehicle.hpp"
#include "idsim_common/vehicle_command.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "px4_msgs/msg/failsafe_flags.hpp"
#include "px4_msgs/msg/vehicle_command_ack.hpp"
#include "px4_msgs/msg/vehicle_land_detected.hpp"
#include "px4_msgs/msg/vehicle_local_position.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"

namespace idsim_mission::px4
{

// 표본을 받은 때. tick은 "그 표본을 처음 볼 수 있는 step의 tick 번호", ns는 노드 시계 ROS 시각
// (snapshot.hpp의 received_tick, received_ns 정의).
struct Received
{
  std::uint64_t tick{0};
  std::int64_t ns{0};
};

// ---- enum 해석(전수 시험 대상) ----

// nav_state와 nav_state_user_intention에 같이 쓴다. OFFBOARD -> kOffboard, AUTO_LOITER -> kHold,
// AUTO_LAND -> kLand, 그 밖(DESCEND, AUTO_RTL, TERMINATION, 정의되지 않은 값 포함) -> kOther.
// DESCEND를 kLand로 접지 않는다: 위치가 무효일 때 NAV_LAND가 DESCEND로 대체되며, 그것은 AUTO_LAND
// 확인이 아니다(PX4 Commander.cpp의 NAV_LAND 처리. decisions.md 쟁점 4 `[LAND]` 단서와 같은 동작).
core::NavMode nav_mode_from_px4(std::uint8_t nav_state);

// ARMING_STATE_ARMED이면 kArmed, 그 밖의 모든 값은 kDisarmed.
core::Arming arming_from_px4(std::uint8_t arming_state);

// VEHICLE_CMD_DO_SET_MODE -> kSetMode, VEHICLE_CMD_COMPONENT_ARM_DISARM -> kArmDisarm,
// VEHICLE_CMD_NAV_LAND -> kNavLand, 그 밖 -> kOther.
core::AckCommand ack_command_from_px4(std::uint32_t command);

// VEHICLE_CMD_RESULT_* 0-6을 이름 그대로, 그 밖 -> kOther.
core::AckResult ack_result_from_px4(std::uint8_t result);

// EKF 준비 술어(decisions.md 쟁점 4 P2): local_position_invalid, local_altitude_invalid,
// global_position_invalid, home_position_invalid가 모두 false. _relaxed 변형은 보지 않는다.
bool ekf_ready(const px4_msgs::msg::FailsafeFlags & flags);

// ---- 표본 변환 ----

// identity는 idsim_common::verify로 대조한다. 불일치면 kMismatch와 identity_detail(기대값과 받은
// system_id, component_id). 불일치 표본도 다른 필드는 그대로 채워 돌려준다(버릴지는 core가 정한다).
core::StatusSample to_status_sample(
  const px4_msgs::msg::VehicleStatus & msg, const idsim_common::VehicleIdentity & identity,
  Received received);

core::LandSample to_land_sample(
  const px4_msgs::msg::VehicleLandDetected & msg, std::uint64_t received_tick);

// x, y, z, heading은 float32 -> double 그대로(NaN 유지). z_valid 그대로.
core::PositionSample to_position_sample(
  const px4_msgs::msg::VehicleLocalPosition & msg, std::uint64_t received_tick);

core::FlagsSample to_flags_sample(
  const px4_msgs::msg::FailsafeFlags & msg, std::uint64_t received_tick);

// ack의 target_system, target_component가 source와 같을 때만 값이 있다. 아니면 nullopt(다른
// 송신자, 예를 들면 테스트의 px4_raw나 QGC의 명령에 대한 ack. 버린다).
std::optional<core::AckSample> to_ack_sample(
  const px4_msgs::msg::VehicleCommandAck & msg, const idsim_common::CommandSource & source,
  std::uint64_t received_tick);

}  // namespace idsim_mission::px4

#endif  // IDSIM_MISSION__PX4__INPUTS_HPP_
