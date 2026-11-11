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

// PREPARING(decisions.md 쟁점 4 P0-P6, 첫 항목이 LAND인 분기)와 PREPARING 실패의 정리(쟁점 3 M5
// 마지막 문단).

#include <gtest/gtest.h>

#include <cmath>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

TEST(Preparing, HappyPathOrder)
{
  Harness h(standard_mission());
  // P0-P3: 첫 tick에 준비가 끝나 TAKEOFF 목표점 발행을 시작한다.
  const StepOutput first = h.tick();
  ASSERT_TRUE(first.setpoint.has_value());
  EXPECT_EQ(first.setpoint->kind, SetpointKind::kTarget);
  EXPECT_DOUBLE_EQ(first.setpoint->x, 1.0);
  EXPECT_DOUBLE_EQ(first.setpoint->y, 2.0);
  EXPECT_DOUBLE_EQ(first.setpoint->z, -5.0);
  EXPECT_DOUBLE_EQ(first.setpoint->yaw_ned, 0.25);
  EXPECT_TRUE(first.commands.empty());
  ASSERT_TRUE(first.px4_timestamp_us.has_value());
  ASSERT_TRUE(first.feedback.has_value());
  EXPECT_EQ(first.feedback->phase, FeedbackPhase::kPreparing);
  EXPECT_EQ(first.feedback->item_index, 0U);
  EXPECT_EQ(first.feedback->item_count, 3U);
  EXPECT_EQ(first.feedback->item_type, item_type::kTakeoff);
  EXPECT_EQ(h.view().prep, PrepStep::kSignal);

  // P4: 발행 10회 뒤(10번째 발행 다음 tick) Offboard를 보낸다.
  for (int i = 2; i <= 10; ++i) {
    const StepOutput out = h.tick();
    EXPECT_TRUE(out.setpoint.has_value());
    EXPECT_TRUE(out.commands.empty()) << "tick " << i;
  }
  const StepOutput offboard = h.tick();
  EXPECT_EQ(offboard.commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  EXPECT_FALSE(h.view().arm_sent);

  // P5 -> P6 -> TAKEOFF.
  h.drive_to_takeoff();
  const std::vector<CommandKind> all = h.commands();
  ASSERT_EQ(all.size(), 2U);
  EXPECT_EQ(all[0], CommandKind::kSetModeOffboard);
  EXPECT_EQ(all[1], CommandKind::kArm);
  // 불변식: setpoint 항목이 시작될 때 이 goal에서 arm을 보낸 적이 있다.
  EXPECT_TRUE(h.view().arm_sent);
  EXPECT_FALSE(h.view().pending_active);
  EXPECT_TRUE(h.view().publishing);
}

TEST(Preparing, SignalNeedsFlagsReceivedAfterPublishStart)
{
  // P4의 신호 확인은 발행 시작 뒤에 받은 failsafe_flags로만 한다. flags가 더 오지 않으면
  // offboard_signal_timeout(2 s)에 MODE_SWITCH_FAILED. arm을 보내지 않았으므로 정리 없이 끝난다.
  Harness h(standard_mission());
  h.world.signal_lost = false;
  h.tick();
  h.auto_samples = false;
  for (int i = 0; i < 39; ++i) {
    h.push_status();
    h.step_only();
  }
  EXPECT_FALSE(h.runner().done());
  h.push_status();
  h.step_only();  // 발행 시작에서 2.0 s
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_NE(h.termination()->detail.find("offboard_signal_timeout"), std::string::npos);
  EXPECT_TRUE(h.commands().empty());
}

TEST(Preparing, ReadyTimeoutBoundaryAndFeedbackBeforeNotReady)
{
  // P2 EKF gate가 풀리지 않으면 ready_timeout(30 s, goal 접수부터)에 NOT_READY. M1: 그 앞에
  // PHASE_PREPARING feedback이 나갈 수 있다.
  Harness h(standard_mission());
  h.world.ekf_ready = false;
  for (int i = 0; i < 600; ++i) {
    const StepOutput out = h.tick();
    ASSERT_FALSE(out.termination.has_value()) << "tick " << i;
    ASSERT_TRUE(out.feedback.has_value());
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kPreparing);
    EXPECT_FALSE(out.setpoint.has_value());
  }
  h.tick();  // 접수에서 30.0 s
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
  EXPECT_NE(h.termination()->detail.find("EKF gate"), std::string::npos);
  EXPECT_TRUE(h.commands().empty());
}

TEST(Preparing, MissingTopicWaitsThenNotReady)
{
  Harness h(standard_mission());
  h.auto_samples = false;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 700));
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
  EXPECT_NE(h.termination()->detail.find("vehicle_status"), std::string::npos);
}

TEST(Preparing, IdentityMismatchIsImmediateNotReady)
{
  Harness h(standard_mission());
  h.world.identity = IdentityCheck::kMismatch;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
  EXPECT_NE(h.termination()->detail.find("expected sysid 2"), std::string::npos);
  EXPECT_TRUE(h.commands().empty());
}

TEST(Preparing, TakeoffNeedsLandedAndDisarmed)
{
  {
    Harness h(standard_mission());
    h.world.arming = Arming::kArmed;  // 지상 arm은 받지 않는다
    h.tick();
    expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  }
  {
    Harness h(standard_mission());
    h.world.landed = false;
    h.tick();
    expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  }
}

TEST(Preparing, LandFirstNeedsArmedAndNotLanded)
{
  {
    Harness h(land_only_mission());
    h.tick();  // 지상 DISARMED
    expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  }
  {
    Harness h(land_only_mission());
    h.world.arming = Arming::kArmed;  // 지상 arm
    h.tick();
    expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  }
}

TEST(Preparing, LandOnlyNeverPublishesAndSucceeds)
{
  // [LAND] 한 항목 미션: Offboard 진입과 arm을 하지 않고 setpoint를 한 번도 발행하지 않는다.
  Harness h(land_only_mission());
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.world.nav = NavMode::kHold;
  const StepOutput first = h.tick();
  EXPECT_EQ(h.view().stage, Stage::kItem);
  EXPECT_EQ(first.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 20));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
  EXPECT_FALSE(h.view().arm_sent);
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
  EXPECT_EQ(h.termination()->items_completed, 1U);
  EXPECT_EQ(h.termination()->last_item_index, 0U);
}

TEST(Preparing, OffboardRejectedAckIsModeSwitchFailed)
{
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }));
  h.auto_px4 = false;
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);
  h.tick();
  // arm을 보내지 않았고 지상 DISARMED라 정리 없이 끝난다.
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_NE(h.termination()->detail.find("rejected"), std::string::npos);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
}

TEST(Preparing, OffboardConfirmTimeoutWithResends)
{
  Harness h(standard_mission());
  h.auto_px4 = false;
  h.world.signal_lost = false;
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }));
  // Offboard는 들어간 tick에 한 번, 그 뒤 0.5 s마다. 3.0 s에 MODE_SWITCH_FAILED.
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 6);
}

TEST(Preparing, ArmTemporarilyRejectedRetries)
{
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;  // arm이 아직 처리되지 않았다
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  h.tick();
  EXPECT_FALSE(h.runner().done());
  for (int i = 0; i < 10; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.count_command(CommandKind::kArm), 2);  // 0.5 s 뒤 재전송
  h.world.arming = Arming::kArmed;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kItem; }, 10));
}

TEST(Preparing, ArmDeniedCleansUpWithGroundDisarm)
{
  // 방어 경로(합성 ack): v1.17.0의 ARM_DISARM은 ACCEPTED와 TEMPORARILY_REJECTED만 돌려준다.
  // 거부되면 ARM_REJECTED이고, arm을 보냈으므로 지상 setpoint + disarm으로 정리한다. reason은 유지.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);
  const StepOutput fail = h.tick();
  EXPECT_EQ(fail.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  ASSERT_TRUE(fail.setpoint.has_value());
  EXPECT_EQ(fail.setpoint->kind, SetpointKind::kGround);
  EXPECT_DOUBLE_EQ(fail.setpoint->z, 0.0);  // 그 tick의 위치. 어댑터가 +0.5 m를 더한다
  EXPECT_EQ(h.view().branch, Branch::kGround);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  expect_terminated_once(h, Status::kAborted, Reason::kArmRejected);
  EXPECT_NE(h.termination()->detail.find("cleanup: disarm confirmed"), std::string::npos)
    << h.termination()->detail;
}

TEST(Preparing, ArmTimeoutKeepsReasonWhenDisarmUnconfirmed)
{
  // arm_timeout -> ARM_REJECTED. 정리 중에 늦은 arm이 처리되어 기체가 ARMED로 남으면 disarm이
  // 확인되지 않는다. reason은 ARM_REJECTED를 유지하고 detail에 적는다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;  // arm이 처리되지 않는다
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 200));
  EXPECT_EQ(h.view().branch, Branch::kGround);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 10);  // 5 s 동안 0.5 s마다, 만료 tick에는 없음
  h.world.arming = Arming::kArmed;                    // 늦은 arm
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  expect_terminated_once(h, Status::kAborted, Reason::kArmRejected);
  EXPECT_NE(h.termination()->detail.find("arm_timeout"), std::string::npos);
  EXPECT_NE(h.termination()->detail.find("disarm not confirmed"), std::string::npos)
    << h.termination()->detail;
}

TEST(Preparing, IdentityMismatchAfterPublishingStartsStops)
{
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }));
  h.world.identity = IdentityCheck::kMismatch;
  const StepOutput out = h.tick();
  EXPECT_FALSE(out.setpoint.has_value());
  EXPECT_TRUE(out.commands.empty());
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
}

}  // namespace
}  // namespace idsim_mission::core::test
