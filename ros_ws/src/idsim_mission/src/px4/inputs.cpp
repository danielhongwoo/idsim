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

#include "idsim_mission/px4/inputs.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace idsim_mission::px4
{

namespace
{

using px4_msgs::msg::VehicleCommand;
using px4_msgs::msg::VehicleCommandAck;
using px4_msgs::msg::VehicleStatus;

}  // namespace

core::NavMode nav_mode_from_px4(std::uint8_t nav_state)
{
  switch (nav_state) {
    case VehicleStatus::NAVIGATION_STATE_OFFBOARD:
      return core::NavMode::kOffboard;
    case VehicleStatus::NAVIGATION_STATE_AUTO_LOITER:
      return core::NavMode::kHold;
    case VehicleStatus::NAVIGATION_STATE_AUTO_LAND:
      return core::NavMode::kLand;
    case VehicleStatus::NAVIGATION_STATE_AUTO_RTL:
      return core::NavMode::kRtl;
    default:
      return core::NavMode::kOther;
  }
}

core::Arming arming_from_px4(std::uint8_t arming_state)
{
  return arming_state == VehicleStatus::ARMING_STATE_ARMED ? core::Arming::kArmed
                                                           : core::Arming::kDisarmed;
}

core::AckCommand ack_command_from_px4(std::uint32_t command)
{
  switch (command) {
    case VehicleCommand::VEHICLE_CMD_DO_SET_MODE:
      return core::AckCommand::kSetMode;
    case VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM:
      return core::AckCommand::kArmDisarm;
    case VehicleCommand::VEHICLE_CMD_NAV_LAND:
      return core::AckCommand::kNavLand;
    case VehicleCommand::VEHICLE_CMD_NAV_RETURN_TO_LAUNCH:
      return core::AckCommand::kNavRtl;
    default:
      return core::AckCommand::kOther;
  }
}

core::AckResult ack_result_from_px4(std::uint8_t result)
{
  switch (result) {
    case VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED:
      return core::AckResult::kAccepted;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED:
      return core::AckResult::kTemporarilyRejected;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_DENIED:
      return core::AckResult::kDenied;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_UNSUPPORTED:
      return core::AckResult::kUnsupported;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_FAILED:
      return core::AckResult::kFailed;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_IN_PROGRESS:
      return core::AckResult::kInProgress;
    case VehicleCommandAck::VEHICLE_CMD_RESULT_CANCELLED:
      return core::AckResult::kCancelled;
    default:
      return core::AckResult::kOther;
  }
}

bool ekf_ready(const px4_msgs::msg::FailsafeFlags & flags)
{
  return !flags.local_position_invalid && !flags.local_altitude_invalid &&
         !flags.global_position_invalid && !flags.home_position_invalid;
}

core::StatusSample to_status_sample(
  const px4_msgs::msg::VehicleStatus & msg, const idsim_common::VehicleIdentity & identity,
  Received received)
{
  core::StatusSample sample;
  sample.timestamp_us = msg.timestamp;
  sample.received_tick = received.tick;
  sample.received_ns = received.ns;
  const idsim_common::IdentityCheck check = idsim_common::verify(identity, msg);
  if (check == idsim_common::IdentityCheck::Match) {
    sample.identity = core::IdentityCheck::kMatch;
  } else {
    sample.identity = core::IdentityCheck::kMismatch;
    sample.identity_detail =
      std::string("vehicle_status identity mismatch (") + idsim_common::to_string(check) +
      "): expected system_id " + std::to_string(identity.sysid.value()) + " component_id " +
      std::to_string(idsim_common::kAutopilotComponentId) + ", got system_id " +
      std::to_string(msg.system_id) + " component_id " + std::to_string(msg.component_id);
  }
  sample.arming = arming_from_px4(msg.arming_state);
  sample.nav = nav_mode_from_px4(msg.nav_state);
  sample.nav_user_intention = nav_mode_from_px4(msg.nav_state_user_intention);
  sample.failsafe = msg.failsafe;
  return sample;
}

core::LandSample to_land_sample(
  const px4_msgs::msg::VehicleLandDetected & msg, std::uint64_t received_tick)
{
  core::LandSample sample;
  sample.landed = msg.landed;
  sample.received_tick = received_tick;
  return sample;
}

core::PositionSample to_position_sample(
  const px4_msgs::msg::VehicleLocalPosition & msg, std::uint64_t received_tick)
{
  core::PositionSample sample;
  sample.timestamp_us = msg.timestamp;  // timestamp_sample이 아니다(snapshot.hpp 머리 주석)
  sample.x = static_cast<double>(msg.x);
  sample.y = static_cast<double>(msg.y);
  sample.z = static_cast<double>(msg.z);
  sample.heading = static_cast<double>(msg.heading);
  sample.xy_valid = msg.xy_valid;
  sample.z_valid = msg.z_valid;
  sample.received_tick = received_tick;
  return sample;
}

core::FlagsSample to_flags_sample(
  const px4_msgs::msg::FailsafeFlags & msg, std::uint64_t received_tick)
{
  core::FlagsSample sample;
  sample.ekf_ready = ekf_ready(msg);
  sample.offboard_signal_lost = msg.offboard_control_signal_lost;
  sample.received_tick = received_tick;
  return sample;
}

std::optional<core::AckSample> to_ack_sample(
  const px4_msgs::msg::VehicleCommandAck & msg, const idsim_common::CommandSource & source,
  std::uint64_t received_tick)
{
  if (msg.target_system != source.system() || msg.target_component != source.component()) {
    return std::nullopt;
  }
  core::AckSample sample;
  sample.command = ack_command_from_px4(msg.command);
  sample.result = ack_result_from_px4(msg.result);
  sample.received_tick = received_tick;
  return sample;
}

}  // namespace idsim_mission::px4
