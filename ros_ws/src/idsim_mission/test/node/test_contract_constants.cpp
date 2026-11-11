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

// core가 다시 적은 값과 생성된 메시지 상수, idsim_common 식의 교차 검사(노드는 만들지 않는다).
// - core::Reason 전수와 ExecuteMission result의 REASON_* (13, 14 포함). 상수가 늘면 깨지도록
//   kAllReasons의 길이도 단정한다.
// - item_type, yaw_mode, FeedbackPhase, event_status와 메시지 상수.
// - core의 enu_to_ned_yaw, wrap_pi와 idsim_common/frames의 같은 함수.
// - 변환(conversion.hpp): 종료 결과 하나에서 만든 result와 사건이 같은 값.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "idsim_common/frames.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_interfaces/msg/mission_item.hpp"
#include "idsim_interfaces/msg/yaw_setpoint.hpp"
#include "idsim_mission/core/rules.hpp"
#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"
#include "idsim_mission/node/conversion.hpp"

namespace idsim_mission::test
{
namespace
{

using Result = idsim_interfaces::action::ExecuteMission::Result;
using Feedback = idsim_interfaces::action::ExecuteMission::Feedback;
using MissionItem = idsim_interfaces::msg::MissionItem;
using MissionEvent = idsim_interfaces::msg::MissionEvent;
using YawSetpoint = idsim_interfaces::msg::YawSetpoint;

int v(core::Reason r) { return static_cast<int>(r); }

TEST(ContractConstants, ReasonsMatchMessage)
{
  EXPECT_EQ(v(core::Reason::kNone), Result::REASON_NONE);
  EXPECT_EQ(v(core::Reason::kInvalidMission), Result::REASON_INVALID_MISSION);
  EXPECT_EQ(v(core::Reason::kVehicleIdMismatch), Result::REASON_VEHICLE_ID_MISMATCH);
  EXPECT_EQ(v(core::Reason::kBusy), Result::REASON_BUSY);
  EXPECT_EQ(v(core::Reason::kNotReady), Result::REASON_NOT_READY);
  EXPECT_EQ(v(core::Reason::kArmRejected), Result::REASON_ARM_REJECTED);
  EXPECT_EQ(v(core::Reason::kModeSwitchFailed), Result::REASON_MODE_SWITCH_FAILED);
  EXPECT_EQ(v(core::Reason::kItemTimeout), Result::REASON_ITEM_TIMEOUT);
  EXPECT_EQ(v(core::Reason::kFailsafe), Result::REASON_FAILSAFE);
  EXPECT_EQ(v(core::Reason::kExternalModeChange), Result::REASON_EXTERNAL_MODE_CHANGE);
  EXPECT_EQ(v(core::Reason::kTargetLost), Result::REASON_TARGET_LOST);
  EXPECT_EQ(v(core::Reason::kLinkLost), Result::REASON_LINK_LOST);
  EXPECT_EQ(v(core::Reason::kPreconditionFailed), Result::REASON_PRECONDITION_FAILED);
  EXPECT_EQ(v(core::Reason::kDisarmFailed), Result::REASON_DISARM_FAILED);
  EXPECT_EQ(v(core::Reason::kExternalDisarm), Result::REASON_EXTERNAL_DISARM);
  EXPECT_EQ(v(core::Reason::kInternal), Result::REASON_INTERNAL);
  // 메시지에 REASON_*가 늘면 core::Reason과 kAllReasons(16)에도 더해야 한다. 이 단정이 그 신호다.
  EXPECT_EQ(core::kAllReasons.size(), 16U);
}

TEST(ContractConstants, ItemTypesYawPhasesStatuses)
{
  EXPECT_EQ(core::item_type::kTakeoff, MissionItem::TYPE_TAKEOFF);
  EXPECT_EQ(core::item_type::kGoTo, MissionItem::TYPE_GOTO);
  EXPECT_EQ(core::item_type::kTrackEntity, MissionItem::TYPE_TRACK_ENTITY);
  EXPECT_EQ(core::item_type::kLoiter, MissionItem::TYPE_LOITER);
  EXPECT_EQ(core::item_type::kRtl, MissionItem::TYPE_RTL);
  EXPECT_EQ(core::item_type::kLand, MissionItem::TYPE_LAND);
  EXPECT_EQ(core::yaw_mode::kKeep, YawSetpoint::MODE_KEEP);
  EXPECT_EQ(core::yaw_mode::kFixed, YawSetpoint::MODE_FIXED);
  EXPECT_EQ(static_cast<int>(core::FeedbackPhase::kPreparing), Feedback::PHASE_PREPARING);
  EXPECT_EQ(static_cast<int>(core::FeedbackPhase::kExecuting), Feedback::PHASE_EXECUTING);
  EXPECT_EQ(static_cast<int>(core::FeedbackPhase::kWaitingMode), Feedback::PHASE_WAITING_MODE);
  EXPECT_EQ(static_cast<int>(core::FeedbackPhase::kCanceling), Feedback::PHASE_CANCELING);
  EXPECT_EQ(core::event_status::kUnknown, MissionEvent::STATUS_UNKNOWN);
  EXPECT_EQ(core::event_status::kAccepted, MissionEvent::STATUS_ACCEPTED);
  EXPECT_EQ(core::event_status::kSucceeded, MissionEvent::STATUS_SUCCEEDED);
  EXPECT_EQ(core::event_status::kCanceled, MissionEvent::STATUS_CANCELED);
  EXPECT_EQ(core::event_status::kAborted, MissionEvent::STATUS_ABORTED);
}

TEST(CrossCheck, YawMatchesIdsimCommonFrames)
{
  for (int i = -800; i <= 800; ++i) {
    const double a = 0.01 * i;
    EXPECT_DOUBLE_EQ(core::enu_to_ned_yaw(a), idsim_common::frames::enu_to_ned_yaw(a)) << a;
    EXPECT_DOUBLE_EQ(core::wrap_pi(a), idsim_common::frames::wrap_pi(a)) << a;
  }
}

TEST(Conversion, ResultEqualsTerminalEvent)
{
  EventContext context;
  context.vehicle_id = "px4_1";
  context.mission_id = "m1";
  context.goal_id[0] = 7;
  context.item_count = 3;
  core::Termination term;
  term.status = core::Status::kAborted;
  term.reason = core::Reason::kExternalDisarm;
  term.items_completed = 1;
  term.last_item_index = 1;
  term.detail = "d";
  const Result result = to_result_msg(term);
  const MissionEvent event = terminal_event_msg(context, term);
  EXPECT_EQ(event.status, MissionEvent::STATUS_ABORTED);
  EXPECT_EQ(event.reason, result.reason);
  EXPECT_EQ(event.reason, Result::REASON_EXTERNAL_DISARM);
  EXPECT_EQ(event.items_completed, result.items_completed);
  EXPECT_EQ(event.last_item_index, result.last_item_index);
  EXPECT_EQ(event.detail, result.detail);
  EXPECT_EQ(event.item_count, 3U);
  EXPECT_EQ(event.vehicle_id, "px4_1");
  EXPECT_EQ(event.goal_id[0], 7);
  const MissionEvent accepted = accepted_event_msg(context);
  EXPECT_EQ(accepted.status, MissionEvent::STATUS_ACCEPTED);
  EXPECT_EQ(accepted.reason, Result::REASON_NONE);
  EXPECT_EQ(accepted.items_completed, 0U);
  EXPECT_TRUE(accepted.detail.empty());
}

TEST(Conversion, MissionFieldsAreCopied)
{
  idsim_interfaces::msg::Mission mission;
  mission.mission_id = "m1";
  MissionItem takeoff;
  takeoff.type = MissionItem::TYPE_TAKEOFF;
  takeoff.timeout.sec = 20;
  takeoff.takeoff.height_m = 5.0;
  takeoff.takeoff.acceptance_m = 0.3;
  takeoff.takeoff.yaw.mode = YawSetpoint::MODE_FIXED;
  takeoff.takeoff.yaw.yaw_rad = 0.5;
  MissionItem loiter;
  loiter.type = MissionItem::TYPE_LOITER;
  loiter.timeout.sec = 10;
  loiter.loiter.duration.sec = 5;
  loiter.loiter.duration.nanosec = 7;
  mission.items = {takeoff, loiter};
  const core::MissionSpec spec = to_mission_spec(mission);
  ASSERT_EQ(spec.items.size(), 2U);
  EXPECT_EQ(spec.mission_id, "m1");
  EXPECT_EQ(spec.items[0].type, core::item_type::kTakeoff);
  EXPECT_EQ(spec.items[0].timeout.sec, 20);
  EXPECT_DOUBLE_EQ(spec.items[0].takeoff.height_m, 5.0);
  EXPECT_DOUBLE_EQ(spec.items[0].takeoff.acceptance_m, 0.3);
  EXPECT_EQ(spec.items[0].takeoff.yaw.mode, core::yaw_mode::kFixed);
  EXPECT_DOUBLE_EQ(spec.items[0].takeoff.yaw.yaw_rad, 0.5);
  EXPECT_EQ(spec.items[1].loiter.duration.sec, 5);
  EXPECT_EQ(spec.items[1].loiter.duration.nanosec, 7U);
}

}  // namespace
}  // namespace idsim_mission::test
