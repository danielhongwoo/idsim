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

#include <cstdint>
#include <optional>

#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

const char * reason_name(Reason reason)
{
  switch (reason) {
    case Reason::kNone:
      return "NONE";
    case Reason::kInvalidMission:
      return "INVALID_MISSION";
    case Reason::kVehicleIdMismatch:
      return "VEHICLE_ID_MISMATCH";
    case Reason::kBusy:
      return "BUSY";
    case Reason::kNotReady:
      return "NOT_READY";
    case Reason::kArmRejected:
      return "ARM_REJECTED";
    case Reason::kModeSwitchFailed:
      return "MODE_SWITCH_FAILED";
    case Reason::kItemTimeout:
      return "ITEM_TIMEOUT";
    case Reason::kFailsafe:
      return "FAILSAFE";
    case Reason::kExternalModeChange:
      return "EXTERNAL_MODE_CHANGE";
    case Reason::kTargetLost:
      return "TARGET_LOST";
    case Reason::kLinkLost:
      return "LINK_LOST";
    case Reason::kPreconditionFailed:
      return "PRECONDITION_FAILED";
    case Reason::kDisarmFailed:
      return "DISARM_FAILED";
    case Reason::kExternalDisarm:
      return "EXTERNAL_DISARM";
    case Reason::kInternal:
      return "INTERNAL";
  }
  return "UNKNOWN";
}

const char * status_name(Status status)
{
  switch (status) {
    case Status::kSucceeded:
      return "SUCCEEDED";
    case Status::kCanceled:
      return "CANCELED";
    case Status::kAborted:
      return "ABORTED";
  }
  return "UNKNOWN";
}

const char * item_type_name(std::uint8_t type)
{
  switch (type) {
    case item_type::kTakeoff:
      return "TAKEOFF";
    case item_type::kGoTo:
      return "GOTO";
    case item_type::kTrackEntity:
      return "TRACK_ENTITY";
    case item_type::kLoiter:
      return "LOITER";
    case item_type::kRtl:
      return "RTL";
    case item_type::kLand:
      return "LAND";
    default:
      return "INVALID";
  }
}

std::optional<ItemKind> classify_item_type(std::uint8_t type)
{
  switch (type) {
    case item_type::kTakeoff:
    case item_type::kGoTo:
    case item_type::kTrackEntity:
    case item_type::kLoiter:
      return ItemKind::kSetpoint;
    case item_type::kRtl:
    case item_type::kLand:
      return ItemKind::kModeCommand;
    default:
      return std::nullopt;
  }
}

const char * ack_result_name(AckResult result)
{
  switch (result) {
    case AckResult::kAccepted:
      return "ACCEPTED";
    case AckResult::kTemporarilyRejected:
      return "TEMPORARILY_REJECTED";
    case AckResult::kDenied:
      return "DENIED";
    case AckResult::kUnsupported:
      return "UNSUPPORTED";
    case AckResult::kFailed:
      return "FAILED";
    case AckResult::kInProgress:
      return "IN_PROGRESS";
    case AckResult::kCancelled:
      return "CANCELLED";
    case AckResult::kOther:
      return "OTHER";
  }
  return "UNKNOWN";
}

bool is_rejection(AckResult result)
{
  return result != AckResult::kAccepted && result != AckResult::kInProgress;
}

const char * command_name(CommandKind kind)
{
  switch (kind) {
    case CommandKind::kSetModeOffboard:
      return "DO_SET_MODE(OFFBOARD)";
    case CommandKind::kSetModeHold:
      return "DO_SET_MODE(HOLD)";
    case CommandKind::kArm:
      return "ARM";
    case CommandKind::kDisarm:
      return "DISARM";
    case CommandKind::kNavLand:
      return "NAV_LAND";
    case CommandKind::kNavRtl:
      return "NAV_RTL";
  }
  return "UNKNOWN";
}

AckCommand ack_command_of(CommandKind kind)
{
  switch (kind) {
    case CommandKind::kSetModeOffboard:
    case CommandKind::kSetModeHold:
      return AckCommand::kSetMode;
    case CommandKind::kArm:
    case CommandKind::kDisarm:
      return AckCommand::kArmDisarm;
    case CommandKind::kNavLand:
      return AckCommand::kNavLand;
    case CommandKind::kNavRtl:
      return AckCommand::kNavRtl;
  }
  return AckCommand::kOther;
}

}  // namespace idsim_mission::core
