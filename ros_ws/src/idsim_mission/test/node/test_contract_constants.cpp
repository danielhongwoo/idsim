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
// - 변환(conversion.hpp): 종료 결과 하나에서 만든 result와 사건이 같은 값. feedback stamp는
//   core::Feedback.stamp_ns 그대로. 표적 상태의 유효 표본 규칙(docs/interface.md "GoToItem과
//   TrackEntityItem").
// - core::is_valid_target_id와 idsim_common::TargetId::parse가 같은 사례 표에서 같은 답.
// - 비행 중 원점 변경 WARN의 판정(reference_changed_in_flight).

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <vector>

#include "builtin_interfaces/msg/time.hpp"
#include "idsim_common/frames.hpp"
#include "idsim_common/target.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_interfaces/msg/mission_item.hpp"
#include "idsim_interfaces/msg/target_state.hpp"
#include "idsim_interfaces/msg/yaw_setpoint.hpp"
#include "idsim_mission/core/config.hpp"
#include "idsim_mission/core/mission_validation.hpp"
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

TEST(Conversion, FeedbackStampIsCoreStamp)
{
  core::Feedback feedback;
  feedback.stamp_ns = 12345678901LL;
  feedback.item_index = 1;
  feedback.item_count = 3;
  feedback.phase = core::FeedbackPhase::kExecuting;
  const Feedback msg = to_feedback_msg(feedback);
  EXPECT_EQ(msg.stamp.sec, 12);
  EXPECT_EQ(msg.stamp.nanosec, 345678901U);
  EXPECT_EQ(msg.item_index, 1U);
  EXPECT_EQ(msg.item_count, 3U);
  EXPECT_EQ(msg.phase, Feedback::PHASE_EXECUTING);
}

TEST(Conversion, TimeMsgKeepsNanosecInRange)
{
  const builtin_interfaces::msg::Time zero = to_time_msg(0);
  EXPECT_EQ(zero.sec, 0);
  EXPECT_EQ(zero.nanosec, 0U);
  const builtin_interfaces::msg::Time whole = to_time_msg(5 * core::kNsPerSecond);
  EXPECT_EQ(whole.sec, 5);
  EXPECT_EQ(whole.nanosec, 0U);
  const builtin_interfaces::msg::Time negative = to_time_msg(-1);
  EXPECT_EQ(negative.sec, -1);
  EXPECT_EQ(negative.nanosec, 999999999U);
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

TEST(ContractConstants, TargetIdRuleMatchesIdsimCommon)
{
  const std::vector<std::string> cases = {"a",     "car_1",
                                          "z9_",   "a" + std::string(31, 'b'),
                                          "",      "a" + std::string(32, 'b'),
                                          "1car",  "_car",
                                          "Car-1", "car-1",
                                          "car/1", "car 1",
                                          "car.1", "cAr"};
  for (const std::string & text : cases) {
    EXPECT_EQ(core::is_valid_target_id(text), idsim_common::TargetId::parse(text).has_value())
      << "'" << text << "'";
  }
}

using TargetState = idsim_interfaces::msg::TargetState;

TargetState valid_target_state()
{
  TargetState msg;
  msg.header.frame_id = TargetState::FRAME_ID;
  msg.header.stamp.sec = 10;
  msg.header.stamp.nanosec = 500;
  msg.target_id = "car_1";
  msg.position.x = 1.0;
  msg.position.y = -2.0;
  msg.position.z = 3.0;
  msg.velocity_valid = true;
  msg.velocity.x = 0.5;
  msg.velocity.y = 0.25;
  msg.velocity.z = -0.125;
  return msg;
}

TEST(TargetSampleConversion, ValidSampleIsCopied)
{
  const std::optional<core::TargetSample> s =
    to_target_sample(valid_target_state(), "car_1", std::nullopt);
  ASSERT_TRUE(s.has_value());
  EXPECT_EQ(s->position.x, 1.0);
  EXPECT_EQ(s->position.y, -2.0);
  EXPECT_EQ(s->position.z, 3.0);
  EXPECT_TRUE(s->velocity_valid);
  EXPECT_EQ(s->velocity.x, 0.5);
  EXPECT_EQ(s->velocity.y, 0.25);
  EXPECT_EQ(s->velocity.z, -0.125);
  EXPECT_EQ(s->stamp_ns, 10000000500LL);
}

TEST(TargetSampleConversion, InvalidVelocityFieldsAreIgnoredWhenNotValid)
{
  TargetState msg = valid_target_state();
  msg.velocity_valid = false;
  msg.velocity.x = std::numeric_limits<double>::quiet_NaN();
  const std::optional<core::TargetSample> s = to_target_sample(msg, "car_1", std::nullopt);
  ASSERT_TRUE(s.has_value());
  EXPECT_FALSE(s->velocity_valid);
  EXPECT_EQ(s->velocity.x, 0.0);
}

TEST(TargetSampleConversion, PositionBoundIsInclusive)
{
  TargetState msg = valid_target_state();
  msg.position.x = core::kMaxContractCoordinateM;
  msg.position.y = -core::kMaxContractCoordinateM;
  EXPECT_TRUE(to_target_sample(msg, "car_1", std::nullopt).has_value());
}

TEST(TargetSampleConversion, InvalidSamplesAreDropped)
{
  struct Case
  {
    const char * name;
    void (*mutate)(TargetState &);
    std::optional<std::int64_t> last;
  };
  const std::vector<Case> cases = {
    {"other target_id", [](TargetState & m) { m.target_id = "car_2"; }, std::nullopt},
    {"frame_id", [](TargetState & m) { m.header.frame_id = "map"; }, std::nullopt},
    {"position nan",
     [](TargetState & m) { m.position.y = std::numeric_limits<double>::quiet_NaN(); },
     std::nullopt},
    {"position inf",
     [](TargetState & m) { m.position.z = std::numeric_limits<double>::infinity(); }, std::nullopt},
    {"position over bound", [](TargetState & m) { m.position.x = std::nextafter(1e5, 2e5); },
     std::nullopt},
    {"position under bound", [](TargetState & m) { m.position.y = -1e5 - 1.0; }, std::nullopt},
    {"valid velocity nan",
     [](TargetState & m) { m.velocity.z = std::numeric_limits<double>::quiet_NaN(); },
     std::nullopt},
    {"valid velocity inf",
     [](TargetState & m) { m.velocity.x = -std::numeric_limits<double>::infinity(); },
     std::nullopt},
    {"zero stamp",
     [](TargetState & m) {
       m.header.stamp.sec = 0;
       m.header.stamp.nanosec = 0;
     },
     std::nullopt},
    {"same stamp", [](TargetState &) {}, 10000000500LL},
    {"older stamp", [](TargetState &) {}, 10000000501LL},
  };
  for (const Case & c : cases) {
    TargetState msg = valid_target_state();
    c.mutate(msg);
    std::string why;
    EXPECT_FALSE(to_target_sample(msg, "car_1", c.last, &why).has_value()) << c.name;
    EXPECT_FALSE(why.empty()) << c.name;
  }
  // 직전 유효 표본보다 크면 받는다. 속도 크기에는 상한이 없다.
  TargetState msg = valid_target_state();
  msg.velocity.x = 1e30;
  EXPECT_TRUE(to_target_sample(msg, "car_1", 10000000499LL).has_value());
}

core::LandSample land(bool landed)
{
  core::LandSample sample;
  sample.landed = landed;
  return sample;
}

TEST(ReferenceChangedInFlight, WarnsOnlyWhenAirborneAndBothStampsKnown)
{
  // 비행 중(landed false)에 ref_timestamp가 바뀌면 WARN.
  EXPECT_TRUE(reference_changed_in_flight(land(false), 1000, 2000));
  // 같은 원점이면 없음.
  EXPECT_FALSE(reference_changed_in_flight(land(false), 1000, 1000));
  // 지상의 첫 원점 설정(직전 0)과 지상의 재설정은 없음.
  EXPECT_FALSE(reference_changed_in_flight(land(true), 0, 1000));
  EXPECT_FALSE(reference_changed_in_flight(land(true), 1000, 2000));
  // 비행 중이어도 직전이나 지금이 0이면(원점 없음) 없음.
  EXPECT_FALSE(reference_changed_in_flight(land(false), 0, 1000));
  EXPECT_FALSE(reference_changed_in_flight(land(false), 1000, 0));
  // 지상 판정 표본을 아직 받지 못했으면 비행 중으로 보지 않는다.
  EXPECT_FALSE(reference_changed_in_flight(std::nullopt, 1000, 2000));
}

}  // namespace
}  // namespace idsim_mission::test
