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

#include "idsim_mission/core/transition.hpp"

#include <string>
#include <vector>

#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

namespace
{

const char * prep_name(PrepStep prep)
{
  switch (prep) {
    case PrepStep::kWaitReady:
      return "WAIT_READY";
    case PrepStep::kSignal:
      return "SIGNAL";
    case PrepStep::kOffboard:
      return "OFFBOARD";
    case PrepStep::kOffboardAck:
      return "OFFBOARD_ACK";
    case PrepStep::kArm:
      return "ARM";
  }
  return "UNKNOWN";
}

const char * cause_name(CleanupCause cause)
{
  switch (cause) {
    case CleanupCause::kCancel:
      return "CANCEL";
    case CleanupCause::kItemTimeout:
      return "ITEM_TIMEOUT";
    case CleanupCause::kPreparingFailure:
      return "PREPARING_FAILURE";
    case CleanupCause::kRtlFailure:
      return "RTL_FAILURE";
    case CleanupCause::kMissionEnd:
      return "MISSION_END";
  }
  return "UNKNOWN";
}

const char * branch_name(Branch branch)
{
  switch (branch) {
    case Branch::kNone:
      return "NONE";
    case Branch::kAir:
      return "AIR";
    case Branch::kAirLand:
      return "AIR_LAND";
    case Branch::kGround:
      return "GROUND";
    case Branch::kGroundWait:
      return "GROUND_WAIT";
  }
  return "UNKNOWN";
}

}  // namespace

const char * event_name(Event event)
{
  switch (event) {
    case Event::kInvalidMission:
      return "INVALID_MISSION";
    case Event::kPreparingIdentityMismatch:
      return "PREPARING_IDENTITY_MISMATCH";
    case Event::kReadyIdentityMismatch:
      return "READY_IDENTITY_MISMATCH";
    case Event::kPreconditionFailed:
      return "PRECONDITION_FAILED";
    case Event::kReadyTimeout:
      return "READY_TIMEOUT";
    case Event::kReadyTakeoff:
      return "READY_TAKEOFF";
    case Event::kReadyModeItem:
      return "READY_MODE_ITEM";
    case Event::kSignalTimeout:
      return "SIGNAL_TIMEOUT";
    case Event::kSignalConfirmed:
      return "SIGNAL_CONFIRMED";
    case Event::kOffboardRejected:
      return "OFFBOARD_REJECTED";
    case Event::kOffboardTimeout:
      return "OFFBOARD_TIMEOUT";
    case Event::kOffboardConfirmed:
      return "OFFBOARD_CONFIRMED";
    case Event::kOffboardAckAccepted:
      return "OFFBOARD_ACK_ACCEPTED";
    case Event::kOffboardLeft:
      return "OFFBOARD_LEFT";
    case Event::kArmRejected:
      return "ARM_REJECTED";
    case Event::kArmTimeout:
      return "ARM_TIMEOUT";
    case Event::kArmConfirmTimeout:
      return "ARM_CONFIRM_TIMEOUT";
    case Event::kArmConfirmed:
      return "ARM_CONFIRMED";
    case Event::kMonitorTimestampFailure:
      return "MONITOR_TIMESTAMP_FAILURE";
    case Event::kMonitorIdentityMismatch:
      return "MONITOR_IDENTITY_MISMATCH";
    case Event::kMonitorLinkLost:
      return "MONITOR_LINK_LOST";
    case Event::kMonitorDisarmedInAir:
      return "MONITOR_DISARMED_IN_AIR";
    case Event::kMonitorDisarmedOnGround:
      return "MONITOR_DISARMED_ON_GROUND";
    case Event::kMonitorModeFailsafe:
      return "MONITOR_MODE_FAILSAFE";
    case Event::kMonitorModeExternal:
      return "MONITOR_MODE_EXTERNAL";
    case Event::kMonitorModeDefensive:
      return "MONITOR_MODE_DEFENSIVE";
    case Event::kItemTimeout:
      return "ITEM_TIMEOUT";
    case Event::kTakeoffReached:
      return "TAKEOFF_REACHED";
    case Event::kLoiterElapsed:
      return "LOITER_ELAPSED";
    case Event::kModeItemIdentityMismatch:
      return "MODE_ITEM_IDENTITY_MISMATCH";
    case Event::kModeItemLinkLost:
      return "MODE_ITEM_LINK_LOST";
    case Event::kModeItemDisarmedInAir:
      return "MODE_ITEM_DISARMED_IN_AIR";
    case Event::kModeItemLeftMode:
      return "MODE_ITEM_LEFT_MODE";
    case Event::kModeItemRejected:
      return "MODE_ITEM_REJECTED";
    case Event::kModeItemModeTimeout:
      return "MODE_ITEM_MODE_TIMEOUT";
    case Event::kModeItemTimeout:
      return "MODE_ITEM_TIMEOUT";
    case Event::kModeItemDisarmConfirmed:
      return "MODE_ITEM_DISARM_CONFIRMED";
    case Event::kCancel:
      return "CANCEL";
    case Event::kCleanupNoSample:
      return "CLEANUP_NO_SAMPLE";
    case Event::kCleanupIdentityMismatch:
      return "CLEANUP_IDENTITY_MISMATCH";
    case Event::kCleanupLinkLost:
      return "CLEANUP_LINK_LOST";
    case Event::kCleanupAirDisarm:
      return "CLEANUP_AIR_DISARM";
    case Event::kCleanupNothingToDo:
      return "CLEANUP_NOTHING_TO_DO";
    case Event::kCleanupCap:
      return "CLEANUP_CAP";
    case Event::kEnterGround:
      return "ENTER_GROUND";
    case Event::kEnterAir:
      return "ENTER_AIR";
    case Event::kGroundDisarmTimeout:
      return "GROUND_DISARM_TIMEOUT";
    case Event::kGroundDisarmConfirmed:
      return "GROUND_DISARM_CONFIRMED";
    case Event::kHoldRejected:
      return "HOLD_REJECTED";
    case Event::kHoldTimeout:
      return "HOLD_TIMEOUT";
    case Event::kHoldConfirmed:
      return "HOLD_CONFIRMED";
    case Event::kLandPathModeObserved:
      return "LAND_PATH_MODE_OBSERVED";
    case Event::kLandPathTimeout:
      return "LAND_PATH_TIMEOUT";
    case Event::kStampUnavailable:
      return "STAMP_UNAVAILABLE";
  }
  return "UNKNOWN";
}

bool operator==(const StateKey & a, const StateKey & b)
{
  return a.stage == b.stage && a.prep == b.prep && a.cause == b.cause && a.branch == b.branch &&
         a.item_type == b.item_type && a.item_index == b.item_index;
}

bool operator!=(const StateKey & a, const StateKey & b) { return !(a == b); }

std::string state_key_name(const StateKey & key)
{
  switch (key.stage) {
    case Stage::kPreparing:
      return std::string("PREPARING.") + prep_name(key.prep);
    case Stage::kItem:
      return std::string("ITEM.") + item_type_name(key.item_type);
    case Stage::kCleanup:
      return std::string("CLEANUP.") + cause_name(key.cause) + "." + branch_name(key.branch);
    case Stage::kDone:
      return "DONE";
  }
  return "UNKNOWN";
}

std::string edge_reason_name(const TransitionEdge & edge)
{
  if (!edge.terminated) {
    return "-";
  }
  return std::string(status_name(edge.status)) + "/" + reason_name(edge.reason);
}

}  // namespace idsim_mission::core
