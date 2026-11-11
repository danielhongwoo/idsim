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

#include "idsim_common/vehicle_command.hpp"

#include <limits>
#include <utility>

namespace idsim_common
{

namespace
{

using px4_msgs::msg::VehicleCommand;

// px4_custom_mode.h
constexpr float kModeFlagCustomModeEnabled = 1.0F;
constexpr float kMainModeAuto = 4.0F;
constexpr float kMainModeOffboard = 6.0F;
constexpr float kSubModeAutoLoiter = 3.0F;

}  // namespace

std::optional<CommandSource> CommandSource::make(int system, int component)
{
  if (system < 1 || system > 255) {
    return std::nullopt;
  }
  if (component < 1 || component >= VehicleCommand::COMPONENT_MODE_EXECUTOR_START) {
    return std::nullopt;
  }
  return CommandSource(static_cast<std::uint8_t>(system), static_cast<std::uint16_t>(component));
}

VehicleCommandBuilder::VehicleCommandBuilder(VehicleIdentity target, CommandSource source)
: target_(std::move(target)), source_(source)
{
}

std::optional<VehicleCommandBuilder> VehicleCommandBuilder::make(
  VehicleIdentity target, CommandSource source)
{
  if (source.system() == target.sysid.value()) {
    return std::nullopt;
  }
  return VehicleCommandBuilder(std::move(target), source);
}

VehicleCommand VehicleCommandBuilder::base(std::uint32_t command, Px4Timestamp timestamp) const
{
  VehicleCommand cmd;
  cmd.timestamp = timestamp.microseconds();
  cmd.command = command;
  cmd.param1 = 0.0F;
  cmd.param2 = 0.0F;
  cmd.param3 = 0.0F;
  cmd.param4 = 0.0F;
  cmd.param5 = 0.0;
  cmd.param6 = 0.0;
  cmd.param7 = 0.0F;
  cmd.target_system = target_.sysid.value();
  cmd.target_component = kAutopilotComponentId;
  cmd.source_system = source_.system();
  cmd.source_component = source_.component();
  cmd.confirmation = 0;
  cmd.from_external = true;
  return cmd;
}

VehicleCommand VehicleCommandBuilder::arm(Px4Timestamp timestamp) const
{
  auto cmd = base(VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, timestamp);
  cmd.param1 = 1.0F;
  return cmd;
}

VehicleCommand VehicleCommandBuilder::disarm(Px4Timestamp timestamp) const
{
  return base(VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, timestamp);
}

VehicleCommand VehicleCommandBuilder::set_mode_offboard(Px4Timestamp timestamp) const
{
  auto cmd = base(VehicleCommand::VEHICLE_CMD_DO_SET_MODE, timestamp);
  cmd.param1 = kModeFlagCustomModeEnabled;
  cmd.param2 = kMainModeOffboard;
  return cmd;
}

VehicleCommand VehicleCommandBuilder::set_mode_hold(Px4Timestamp timestamp) const
{
  auto cmd = base(VehicleCommand::VEHICLE_CMD_DO_SET_MODE, timestamp);
  cmd.param1 = kModeFlagCustomModeEnabled;
  cmd.param2 = kMainModeAuto;
  cmd.param3 = kSubModeAutoLoiter;
  return cmd;
}

VehicleCommand VehicleCommandBuilder::land(Px4Timestamp timestamp) const
{
  auto cmd = base(VehicleCommand::VEHICLE_CMD_NAV_LAND, timestamp);
  cmd.param4 = std::numeric_limits<float>::quiet_NaN();
  cmd.param5 = std::numeric_limits<double>::quiet_NaN();
  cmd.param6 = std::numeric_limits<double>::quiet_NaN();
  cmd.param7 = std::numeric_limits<float>::quiet_NaN();
  return cmd;
}

VehicleCommand VehicleCommandBuilder::rtl(Px4Timestamp timestamp) const
{
  return base(VehicleCommand::VEHICLE_CMD_NAV_RETURN_TO_LAUNCH, timestamp);
}

bool is_ack_for(const px4_msgs::msg::VehicleCommandAck & ack, const VehicleCommand & cmd)
{
  return ack.command == cmd.command && ack.target_system == cmd.source_system &&
         ack.target_component == cmd.source_component;
}

}  // namespace idsim_common
