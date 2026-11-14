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

// PX4 어댑터의 출력 쪽: core::StepOutput -> px4_msgs 메시지. 소유 px4-engineer.
//
// 노드(P3d)의 tick 처리 순서:
//   clock_port.begin_tick();
//   const auto out = runner.step(input, snapshot, clock_port);
//   const auto msgs = to_px4_messages(out, builder, clock_port.stamp());
//   if (!msgs.error.empty()) { RCLCPP_ERROR(...); }
//   if (msgs.setpoint) { mode_pub->publish(msgs.setpoint->mode);
//                        setpoint_pub->publish(msgs.setpoint->trajectory); }
//   for (const auto & cmd : msgs.commands) { command_pub->publish(cmd); }
// offboard_control_mode를 trajectory_setpoint보다 먼저 발행한다(PX4는 둘을 따로 받으므로 순서가
// 결과를 바꾸지는 않지만 한 tick의 짝을 같은 순서로 두면 기록을 읽기 쉽다).
//
// 출력 규칙(core/snapshot.hpp 머리 주석)
// - 명령과 setpoint는 같은 tick에 Px4ClockPort가 만든 Px4Timestamp 하나로 만든다. 그 값은
//   StepOutput.px4_timestamp_us와 같아야 한다. 다르거나 없으면 아무것도 내보내지 않고 error를
//   채운다(core 불변식 위반이라 노드 버그다).
// - setpoint는 position만 true인 offboard_control_mode와 trajectory_setpoint의 짝이다. kGround이면
//   z에 kGroundSetpointOffsetDownM을 더한다. yaw는 frames::wrap_pi로 [-pi, pi)에 넣는다(core가 이미
//   그 범위로 주므로 보통 그대로다). velocity_valid이면 velocity(로컬 NED, m/s)를
//   trajectory_setpoint.velocity에 싣고(feedforward), 아니면 velocity는 NaN이다.
//   offboard_control_mode는 velocity_valid와 무관하게 position만 true다. 위치, yaw, 또는 싣기로
//   한 velocity가 비유한이면 그 tick의 짝을 둘 다 버리고 error를 채운다. 명령은 그대로 내보낸다.
// - CommandKind -> VehicleCommandBuilder: kSetModeOffboard -> set_mode_offboard, kSetModeHold ->
//   set_mode_hold, kArm -> arm, kDisarm -> disarm(강제가 아님), kNavLand -> land, kNavRtl -> rtl.

#ifndef IDSIM_MISSION__PX4__OUTPUTS_HPP_
#define IDSIM_MISSION__PX4__OUTPUTS_HPP_

#include <optional>
#include <string>
#include <vector>

#include "idsim_common/px4_timestamp.hpp"
#include "idsim_common/vehicle_command.hpp"
#include "idsim_mission/core/mission_runner.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "px4_msgs/msg/offboard_control_mode.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"

namespace idsim_mission::px4
{

// 지상 setpoint 오프셋(m, NED +z = 아래쪽). 지상에 있는 기체에 현재 위치보다 0.5 m 아래를 주어
// 이륙 의도가 켜지지 않게 한다(decisions.md 쟁점 3 M5). PX4의 이륙 판정은 setpoint z가 현재 z보다
// 위일 때만 켜진다(MulticopterPositionControl). 값의 변경은 px4-engineer가 정한다. 노드 파라미터가
// 아니다.
inline constexpr double kGroundSetpointOffsetDownM = 0.5;

struct SetpointMessages
{
  px4_msgs::msg::OffboardControlMode mode;
  px4_msgs::msg::TrajectorySetpoint trajectory;
};

// 지상 오프셋을 적용한 PX4로 보낼 위치(NED). kTarget이면 그대로, kGround이면 z + 0.5.
core::SetpointOut apply_ground_offset(const core::SetpointOut & setpoint);

// SetpointOut 하나 -> 메시지 짝. 위치, yaw, 싣기로 한 velocity 중 비유한이 있으면 nullopt.
std::optional<SetpointMessages> to_setpoint_messages(
  const core::SetpointOut & setpoint, idsim_common::Px4Timestamp timestamp);

// CommandKind 하나 -> VehicleCommand.
px4_msgs::msg::VehicleCommand to_vehicle_command(
  core::CommandKind kind, const idsim_common::VehicleCommandBuilder & builder,
  idsim_common::Px4Timestamp timestamp);

struct Px4Messages
{
  std::optional<SetpointMessages> setpoint;
  std::vector<px4_msgs::msg::VehicleCommand> commands;  // StepOutput.commands 순서 그대로
  std::string error;  // 비어 있지 않으면 무엇을 왜 버렸는지(노드가 오류 로그로 남긴다)
};

// StepOutput 하나 -> 이 tick에 발행할 메시지. stamp는 이 tick의 Px4ClockPort가 만든 값
// (RosPx4ClockPort::stamp()). 출력할 것이 없으면 빈 값이다(stamp는 보지 않는다).
Px4Messages to_px4_messages(
  const core::StepOutput & out, const idsim_common::VehicleCommandBuilder & builder,
  const std::optional<idsim_common::Px4Timestamp> & stamp);

}  // namespace idsim_mission::px4

#endif  // IDSIM_MISSION__PX4__OUTPUTS_HPP_
