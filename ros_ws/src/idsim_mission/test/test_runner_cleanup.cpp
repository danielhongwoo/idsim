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

// 정리 분기: 취소(쟁점 3 M3-M5), setpoint 항목의 ITEM_TIMEOUT(쟁점 4), 분기 내부(Hold 확인,
// Land 경로, 지상 disarm 확인), 지상 disarm 분기의 LINK_LOST와 거부 ack(C4).
// 고르기의 교차표는 test_confirm_rules.cpp, PREPARING 실패의 정리는
// test_runner_preparing.cpp에 있다.
// 지상 setpoint 발행 중의 Hold와 이륙 직후의 지상 setpoint + disarm은 실측이 없는 경로다(필수
// 재실측 (2), (3)). 여기의 단정은 표대로이고 재실측 결과로 바뀔 수 있다.

#include <gtest/gtest.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

// ---- 취소: 공중 ----

TEST(CancelAir, HoldConfirmedIsCanceled)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  const StepOutput c = h.tick(true);
  EXPECT_EQ(c.commands, std::vector<CommandKind>{CommandKind::kSetModeHold});
  EXPECT_TRUE(c.setpoint.has_value());  // Hold를 관측하기 전에는 발행을 유지한다
  ASSERT_TRUE(c.feedback.has_value());
  EXPECT_EQ(c.feedback->phase, FeedbackPhase::kCanceling);
  EXPECT_EQ(h.view().branch, Branch::kAir);
  const StepOutput seen = h.tick();  // Hold를 처음 관측
  EXPECT_FALSE(seen.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  EXPECT_EQ(h.termination()->items_completed, 1U);
  EXPECT_EQ(h.termination()->last_item_index, 1U);
}

TEST(CancelAir, HoldRejectedGoesToLandPath)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.tick(true);
  h.push_ack(AckCommand::kSetMode, AckResult::kDenied);
  const StepOutput land = h.tick();
  EXPECT_EQ(land.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  EXPECT_EQ(h.view().branch, Branch::kAirLand);
  EXPECT_TRUE(land.setpoint.has_value());  // 아직 OFFBOARD
  h.world.nav = NavMode::kLand;
  const StepOutput end = h.tick();  // AUTO_LAND를 처음 관측한 tick에 끝난다
  EXPECT_FALSE(end.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_NE(h.termination()->detail.find("Hold rejected"), std::string::npos);
}

TEST(CancelAir, HoldTimeoutThenLandNotConfirmed)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.tick(true);
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.view().branch, Branch::kAir);
  h.tick();  // hold_confirm_timeout 3.0 s
  EXPECT_EQ(h.view().branch, Branch::kAirLand);
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  const StepOutput end = h.tick();  // mode_confirm_timeout 3.0 s
  EXPECT_FALSE(end.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 6);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 6);
}

// ---- 취소: 지상 ----

TEST(CancelGround, ArmedOnGroundDisarmsWithGroundSetpoint)
{
  // PREPARING(P6) 중 취소: arm 재전송은 그 tick에 멈추고, 지상 setpoint + disarm.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  const StepOutput c = h.tick(true);
  EXPECT_EQ(c.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  ASSERT_TRUE(c.setpoint.has_value());
  EXPECT_EQ(c.setpoint->kind, SetpointKind::kGround);
  EXPECT_DOUBLE_EQ(c.setpoint->x, 1.0);
  EXPECT_DOUBLE_EQ(c.setpoint->y, 2.0);
  EXPECT_DOUBLE_EQ(c.setpoint->z, 0.0);
  EXPECT_DOUBLE_EQ(c.setpoint->yaw_ned, 0.25);
  EXPECT_EQ(h.view().branch, Branch::kGround);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 1);
}

TEST(CancelGround, DisarmedButArmSentStillGoesThroughDisarm)
{
  // arm을 보낸 직후 snapshot이 아직 DISARMED여도 바로 끝내지 않고 disarm 확인을 거친다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  const StepOutput c = h.tick(true);
  EXPECT_FALSE(c.termination.has_value());
  EXPECT_EQ(c.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  // 첫 disarm 전송 tick의 표본은 세지 않는다. 다음 tick부터 셋.
  h.tick();
  h.tick();
  EXPECT_FALSE(h.runner().done());
  h.tick();
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
}

TEST(CancelGround, BeforeActingEndsImmediately)
{
  // 지상 DISARMED이고 이 goal에서 arm을 보낸 적이 없으면 바로 CANCELED.
  Harness h(standard_mission());
  h.world.ekf_ready = false;
  h.tick();
  const StepOutput c = h.tick(true);
  EXPECT_TRUE(c.commands.empty());
  EXPECT_FALSE(c.setpoint.has_value());
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  EXPECT_TRUE(h.commands().empty());
}

TEST(CancelGround, GroundToAirKeepsGroundSetpointAndSendsHold)
{
  // 재실측 (2)가 바꿀 수 있는 경로. 대기 중 landed가 false가 되면 공중 분기로 넘어가되 TAKEOFF
  // 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  h.world.landed = false;
  const StepOutput air = h.tick();
  EXPECT_EQ(air.commands, std::vector<CommandKind>{CommandKind::kSetModeHold});
  ASSERT_TRUE(air.setpoint.has_value());
  EXPECT_EQ(air.setpoint->kind, SetpointKind::kGround);
  EXPECT_EQ(h.view().branch, Branch::kAir);
  h.world.nav = NavMode::kHold;
  const StepOutput seen = h.tick();
  EXPECT_FALSE(seen.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
}

TEST(CancelGround, HoldSeenThenLandedDisarmsWithoutRestartingPublish)
{
  // Hold를 관측해 발행을 멈춘 뒤 landed가 true가 되면 지상 분기로 간다. 멈춘 발행은 다시 켜지
  // 않고 disarm만 보낸다.
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.tick(true);
  h.tick();  // Hold 관측, 발행 중단
  EXPECT_FALSE(h.view().publishing);
  const std::size_t from = h.outputs().size();
  h.world.landed = true;
  const StepOutput g = h.tick();
  EXPECT_EQ(h.view().branch, Branch::kGround);
  EXPECT_EQ(g.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_FALSE(g.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  for (std::size_t i = from; i < h.outputs().size(); ++i) {
    EXPECT_FALSE(h.outputs()[i].setpoint.has_value());
  }
}

TEST(CancelGround, DisarmFailedBoundaryAndFinalResend)
{
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);  // 첫 disarm
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  const StepOutput end = h.tick();                                          // 첫 전송 + 3.0 s
  EXPECT_EQ(end.commands, std::vector<CommandKind>{CommandKind::kDisarm});  // 끝내기 전 한 번 더
  EXPECT_TRUE(end.px4_timestamp_us.has_value());
  EXPECT_FALSE(end.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kDisarmFailed);
  EXPECT_NE(h.termination()->detail.find("may remain armed"), std::string::npos);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 7);  // 첫 1 + 재전송 5 + 마지막 1
}

TEST(CancelGround, StaleDisarmedSamplesDoNotConfirm)
{
  // timestamp가 첫 전송의 Px4Timestamp보다 뒤가 아닌 DISARMED 표본만 오면 확인되지 않는다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  const std::uint64_t send_stamp = static_cast<std::uint64_t>(h.now_ns / 1000);
  h.tick(true);
  std::vector<Sample> stale;
  for (int i = 0; i < 60; ++i) {
    Sample s = disarmed(true, NavMode::kOffboard);
    s.timestamp_us = send_stamp - static_cast<std::uint64_t>(i % 2);  // 같거나 앞섬
    stale.push_back(s);
  }
  h.feed(stale);
  expect_terminated_once(h, Status::kAborted, Reason::kDisarmFailed);
}

TEST(CancelGround, LinkLostDuringGroundDisarm)
{
  // C4: 지상 disarm 분기에서 vehicle_status가 link_timeout(2 s) 동안 없으면 발행을 멈추고 disarm을
  // 한 번 더 보낸 뒤 ABORTED, LINK_LOST. mode_confirm_timeout(3 s)보다 먼저다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);
  h.auto_samples = false;
  for (int i = 0; i < 39; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  const StepOutput end = h.tick();
  EXPECT_EQ(end.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_FALSE(end.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kLinkLost);
}

TEST(CancelGround, DeniedDisarmAckKeepsRetrying)
{
  // C4. 방어 경로(합성 ack): v1.17.0의 ARM_DISARM은 DENIED를 돌려주지 않는다. 거부 ack는 종류와
  // 무관하게 그 자리에서 끝내지 않고 landed인 동안 재전송하며, 타임아웃에 끝나며 detail에 적는다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);
  h.tick();
  EXPECT_FALSE(h.runner().done());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  expect_terminated_once(h, Status::kAborted, Reason::kDisarmFailed);
  EXPECT_NE(h.termination()->detail.find("DENIED"), std::string::npos);
}

// ---- 취소: LAND 항목과 [LAND] 미션 ----

TEST(CancelLand, AfterOneOrTwoAutoDisarmSamplesGoesThroughDisarm)
{
  // (1) LAND가 자동 disarm으로 막 끝나려는 시점(DISARMED 1-2회)의 취소는 disarm 분기를 거쳐
  // CANCELED. 발행은 이미 멈췄으므로 지상 setpoint를 새로 켜지 않는다.
  for (const int seen : {1, 2}) {
    Harness h(standard_mission());
    h.drive_to_land();
    ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
    h.auto_px4 = false;
    h.feed(std::vector<Sample>(static_cast<std::size_t>(seen), disarmed(true, NavMode::kLand)));
    const std::vector<StepOutput> c = h.feed({no_new_sample()}, true);
    EXPECT_EQ(c[0].commands, std::vector<CommandKind>{CommandKind::kDisarm}) << seen;
    EXPECT_FALSE(c[0].setpoint.has_value());
    EXPECT_EQ(h.view().branch, Branch::kGround);
    const std::vector<StepOutput> rest = h.feed(
      {disarmed(true, NavMode::kLand), disarmed(true, NavMode::kLand),
       disarmed(true, NavMode::kLand)});
    for (const StepOutput & out : rest) {
      EXPECT_FALSE(out.setpoint.has_value());
    }
    expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  }
}

TEST(CancelLand, LandOnlyAirborneHoldsWithoutPublishing)
{
  Harness h(land_only_mission());
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.tick();
  const StepOutput c = h.tick(true);
  EXPECT_EQ(c.commands, std::vector<CommandKind>{CommandKind::kSetModeHold});
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
}

TEST(CancelLand, LandOnlyOnGroundDisarmedEndsImmediately)
{
  // [LAND] 미션은 arm을 보내지 않는다. 지상 DISARMED로 보이면 바로 CANCELED.
  Harness h(land_only_mission());
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.tick();
  h.auto_px4 = false;
  h.feed({disarmed(true, NavMode::kLand)});
  ASSERT_FALSE(h.runner().done());
  h.feed({no_new_sample()}, true);
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
}

// ---- 취소 중의 규칙 ----

TEST(Canceling, IgnoresMonitorTableAndItemTimeout)
{
  // CANCELING 중에는 감시 표를 쓰지 않고 분기만 본다. 항목 timeout이 지나도 취소 경로로 끝난다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -2.0;
  for (int i = 0; i < 390; ++i) {
    h.tick();
  }
  h.auto_px4 = false;
  h.tick(true);  // TAKEOFF 시작에서 19.55 s
  Sample failsafe_land = armed(NavMode::kLand);
  failsafe_land.failsafe = true;  // 감시 표라면 순위 6
  const std::vector<StepOutput> outs = h.feed(std::vector<Sample>(59, failsafe_land));
  for (const StepOutput & out : outs) {
    EXPECT_FALSE(out.termination.has_value());
  }
  h.feed({failsafe_land});  // hold_confirm_timeout -> Land 경로
  EXPECT_EQ(h.view().branch, Branch::kAirLand);
  h.feed({failsafe_land});  // AUTO_LAND 관측
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
}

TEST(Canceling, DisarmInHoldWindowClassIsFixed)
{
  // Hold 확인 창에서 본 DISARMED: 첫 표본의 landed로 분류를 고정한다.
  {
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;
    h.tick(true);
    h.feed({disarmed(false, NavMode::kHold), disarmed(true, NavMode::kHold)});
    expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
  }
  {
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;
    h.tick(true);
    h.feed({disarmed(true, NavMode::kHold)});
    EXPECT_EQ(h.view().branch, Branch::kGround);
    h.feed(
      {disarmed(false, NavMode::kHold), disarmed(false, NavMode::kHold),
       disarmed(false, NavMode::kHold)});
    expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  }
}

// ---- setpoint 항목의 ITEM_TIMEOUT ----

void to_takeoff_timeout(Harness & h, bool landed)
{
  h.drive_to_takeoff();
  h.world.landed = landed;
  h.world.z = landed ? 0.0 : -2.0;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 500));
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
}

TEST(TakeoffTimeout, AirHoldConfirmed)
{
  Harness h(standard_mission());
  to_takeoff_timeout(h, false);
  const StepOutput & first = h.outputs().back();
  EXPECT_EQ(first.commands, std::vector<CommandKind>{CommandKind::kSetModeHold});
  ASSERT_TRUE(first.feedback.has_value());
  EXPECT_EQ(first.feedback->phase, FeedbackPhase::kExecuting);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("Hold confirmed"), std::string::npos);
}

TEST(TakeoffTimeout, HoldNotConfirmedSendsLand)
{
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.auto_px4 = false;
  h.world.landed = false;
  h.world.z = -2.0;
  ASSERT_TRUE(h.run_until([&h] { return h.view().branch == Branch::kAirLand; }, 500));
  h.world.nav = NavMode::kLand;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("Land sent"), std::string::npos);
}

TEST(TakeoffTimeout, GroundArmedDisarms)
{
  Harness h(standard_mission());
  to_takeoff_timeout(h, true);
  const StepOutput & first = h.outputs().back();
  EXPECT_EQ(first.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  ASSERT_TRUE(first.setpoint.has_value());
  EXPECT_EQ(first.setpoint->kind, SetpointKind::kGround);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("disarm confirmed"), std::string::npos);
}

TEST(TakeoffTimeout, CancelDuringCleanupIsIgnored)
{
  Harness h(standard_mission());
  to_takeoff_timeout(h, false);
  h.auto_px4 = false;
  h.world.nav = NavMode::kOffboard;  // Hold가 먹지 않는다
  h.cancel_sticky = true;
  ASSERT_TRUE(h.run_until([&h] { return h.view().branch == Branch::kAirLand; }, 100));
  h.world.nav = NavMode::kLand;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
}

TEST(TakeoffTimeout, GroundDisarmLinkLostKeepsReason)
{
  // C4: 정리 중의 LINK_LOST는 원래 reason(ITEM_TIMEOUT)을 유지하고 detail에 적는다.
  Harness h(standard_mission());
  to_takeoff_timeout(h, true);
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.auto_samples = false;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_EQ(h.outputs().back().commands, std::vector<CommandKind>{CommandKind::kDisarm});
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("vehicle_status lost"), std::string::npos);
}

TEST(TakeoffTimeout, ReasonStaysItemTimeoutInEveryBranch)
{
  // 공중 Hold 성공, Hold 불확인 뒤 Land, 지상 disarm 성공, 지상 disarm 실패: reason은 모두
  // ITEM_TIMEOUT이고 detail만 다르다.
  std::vector<std::string> details;
  {
    Harness h(standard_mission());
    to_takeoff_timeout(h, false);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    details.push_back(h.termination()->detail);
    EXPECT_EQ(h.termination()->reason, Reason::kItemTimeout);
  }
  {
    Harness h(standard_mission());
    to_takeoff_timeout(h, true);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    details.push_back(h.termination()->detail);
    EXPECT_EQ(h.termination()->reason, Reason::kItemTimeout);
  }
  {
    Harness h(standard_mission());
    to_takeoff_timeout(h, true);
    h.auto_px4 = false;
    h.world.arming = Arming::kArmed;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    details.push_back(h.termination()->detail);
    EXPECT_EQ(h.termination()->reason, Reason::kItemTimeout);
  }
  ASSERT_EQ(details.size(), 3U);
  EXPECT_NE(details[0], details[1]);
  EXPECT_NE(details[1], details[2]);
  EXPECT_NE(details[2].find("disarm not confirmed"), std::string::npos);
}

// ---- 검토 보완(px4-engineer N2, N5, test-engineer B1, B4) ----

TEST(CancelGround, GroundSetpointFallsBackWhenPositionNotFinite)
{
  // 지상 setpoint의 위치가 유한하지 않으면 P3에서 읽은 위치, heading이 유한하지 않으면 그때의
  // setpoint yaw를 쓴다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.world.x = std::nan("");
  h.world.y = 7.0;
  h.world.heading = std::nan("");
  const StepOutput c = h.tick(true);
  ASSERT_TRUE(c.setpoint.has_value());
  EXPECT_EQ(c.setpoint->kind, SetpointKind::kGround);
  EXPECT_DOUBLE_EQ(c.setpoint->x, 1.0);
  EXPECT_DOUBLE_EQ(c.setpoint->y, 2.0);
  EXPECT_DOUBLE_EQ(c.setpoint->z, 0.0);
  EXPECT_DOUBLE_EQ(c.setpoint->yaw_ned, 0.25);
}

TEST(CancelAir, LinkLostDuringHold)
{
  // 공중 분기의 LINK_LOST: 발행을 멈추고 ABORTED, LINK_LOST. disarm은 보내지 않는다.
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.tick(true);
  h.auto_samples = false;
  for (int i = 0; i < 39; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  const StepOutput end = h.tick();
  EXPECT_TRUE(end.commands.empty());
  EXPECT_FALSE(end.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kLinkLost);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
}

TEST(CancelAir, HoldInProgressAckIsNotRejection)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.tick(true);
  h.push_ack(AckCommand::kSetMode, AckResult::kInProgress);
  h.tick();
  EXPECT_EQ(h.view().branch, Branch::kAir);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
}

TEST(UntrustedSample, NotCountedForGroundDisarm)
{
  // N2: 정리 중 식별이 어긋난 표본은 분기 고르기와 확인 계수에 쓰지 않는다. 남의 기체의
  // DISARMED로 CANCELED가 되지 않고, 분기의 타임아웃이 끝낸다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);
  ASSERT_EQ(h.view().branch, Branch::kGround);
  h.world.identity = IdentityCheck::kMismatch;
  h.world.arming = Arming::kDisarmed;
  h.world.landed = false;  // 고르기에 쓰였다면 공중 분기로 갔다
  for (int i = 0; i < 59; ++i) {
    h.tick();
    ASSERT_EQ(h.view().branch, Branch::kGround);
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kDisarmFailed);
}

TEST(UntrustedSample, NotCountedForHold)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.tick(true);
  h.world.identity = IdentityCheck::kMismatch;
  h.world.nav = NavMode::kHold;
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.view().branch, Branch::kAir);
  EXPECT_TRUE(h.view().publishing);  // 어긋난 표본으로 발행을 멈추지도 않는다
  h.tick();                          // hold_confirm_timeout -> Land 경로
  EXPECT_EQ(h.view().branch, Branch::kAirLand);
  h.world.nav = NavMode::kLand;
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_NE(h.termination()->detail.find("AUTO_LAND not confirmed"), std::string::npos);
}

TEST(TakeoffTimeout, DisarmedSnapshotAfterArmReselectsGroundDisarm)
{
  // B1. arm을 보낸 뒤 DISARMED snapshot을 ITEM_TIMEOUT의 정리가 만나면 disarm 분기를 거친다.
  // 만료 tick에 이미 DISARMED이면 감시 표 순위 4-5가 먼저 끝내므로(아래 교차표 칸 6), 정리가
  // 시작된 뒤(공중 Hold 대기 중) 지상 DISARMED를 만나는 경로로 시험한다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.auto_px4 = false;
  h.world.landed = false;
  h.world.z = -2.0;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 500));
  EXPECT_EQ(h.view().branch, Branch::kAir);
  const std::vector<StepOutput> g = h.feed({disarmed(true)});
  EXPECT_EQ(h.view().branch, Branch::kGround);
  EXPECT_EQ(g[0].commands, std::vector<CommandKind>{CommandKind::kDisarm});
  ASSERT_TRUE(g[0].setpoint.has_value());
  EXPECT_EQ(g[0].setpoint->kind, SetpointKind::kGround);
  h.feed({disarmed(true), disarmed(true), disarmed(true)});
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("disarm confirmed"), std::string::npos);
}

// ---- 교차표의 원인 축(상태기 수준. B4): (취소, ITEM_TIMEOUT, PREPARING 실패) x
// (공중 ARMED, 지상 ARMED, 지상 DISARMED이고 arm 보냄) ----

void to_prepare_arm(Harness & h, Arming arming, bool landed)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = arming;
  h.world.landed = landed;
}

void to_takeoff(Harness & h, bool landed)
{
  h.drive_to_takeoff();
  h.auto_px4 = false;
  h.world.landed = landed;
  h.world.z = landed ? 0.0 : -2.0;
}

struct CauseCell
{
  const char * name;
  std::function<void(Harness &)> start;  // 정리가 시작되는 tick까지
  bool reached_cleanup;
  Branch branch;
  CleanupCause cause;
  Status status;
  Reason reason;
};

std::vector<CauseCell> cause_cells()
{
  const auto run_to_cleanup = [](Harness & h) {
    ASSERT_TRUE(
      h.run_until([&h] { return h.runner().done() || h.view().stage == Stage::kCleanup; }, 500));
  };
  const auto deny_arm = [](Harness & h) {
    h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);  // 방어 경로(합성 ack)
    h.tick();
  };
  return {
    {"Cancel_AirArmed",
     [](Harness & h) {
       h.drive_to_loiter();
       h.auto_px4 = false;
       h.tick(true);
     },
     true, Branch::kAir, CleanupCause::kCancel, Status::kCanceled, Reason::kNone},
    {"Cancel_GroundArmed",
     [](Harness & h) {
       to_prepare_arm(h, Arming::kArmed, true);
       h.tick(true);
     },
     true, Branch::kGround, CleanupCause::kCancel, Status::kCanceled, Reason::kNone},
    {"Cancel_GroundDisarmedArmSent",
     [](Harness & h) {
       to_prepare_arm(h, Arming::kDisarmed, true);
       h.tick(true);
     },
     true, Branch::kGround, CleanupCause::kCancel, Status::kCanceled, Reason::kNone},
    {"ItemTimeout_AirArmed",
     [run_to_cleanup](Harness & h) {
       to_takeoff(h, false);
       run_to_cleanup(h);
     },
     true, Branch::kAir, CleanupCause::kItemTimeout, Status::kAborted, Reason::kItemTimeout},
    {"ItemTimeout_GroundArmed",
     [run_to_cleanup](Harness & h) {
       to_takeoff(h, true);
       run_to_cleanup(h);
     },
     true, Branch::kGround, CleanupCause::kItemTimeout, Status::kAborted, Reason::kItemTimeout},
    // 닿지 않는 칸: 만료 tick의 snapshot이 지상 DISARMED이면 감시 표 순위 5가 먼저 goal을 끝내
    // 정리가 시작되지 않는다. 정리 뒤에 DISARMED를 만나는 경로는 위 B1 시험이 덮는다.
    {"ItemTimeout_GroundDisarmedArmSent",
     [](Harness & h) {
       to_takeoff(h, true);
       for (int i = 0; i < 399; ++i) {
         h.tick();
       }
       h.world.arming = Arming::kDisarmed;
       h.tick();
     },
     false, Branch::kNone, CleanupCause::kCancel, Status::kAborted, Reason::kExternalDisarm},
    {"PreparingFailure_AirArmed",
     [deny_arm](Harness & h) {
       to_prepare_arm(h, Arming::kArmed, false);
       deny_arm(h);
     },
     true, Branch::kAir, CleanupCause::kPreparingFailure, Status::kAborted, Reason::kArmRejected},
    {"PreparingFailure_GroundArmed",
     [deny_arm](Harness & h) {
       to_prepare_arm(h, Arming::kArmed, true);
       deny_arm(h);
     },
     true, Branch::kGround, CleanupCause::kPreparingFailure, Status::kAborted,
     Reason::kArmRejected},
    {"PreparingFailure_GroundDisarmedArmSent",
     [deny_arm](Harness & h) {
       to_prepare_arm(h, Arming::kDisarmed, true);
       deny_arm(h);
     },
     true, Branch::kGround, CleanupCause::kPreparingFailure, Status::kAborted,
     Reason::kArmRejected},
  };
}

class CauseCrossTable : public ::testing::TestWithParam<CauseCell>
{
};

TEST_P(CauseCrossTable, BranchAndResult)
{
  const CauseCell & cell = GetParam();
  Harness h(standard_mission());
  cell.start(h);
  if (cell.reached_cleanup) {
    ASSERT_EQ(h.view().stage, Stage::kCleanup) << cell.name;
    EXPECT_EQ(h.view().branch, cell.branch);
    EXPECT_EQ(h.view().cleanup_cause, cell.cause);
    // 가짜 PX4가 반응하게 두면 분기가 확인되어 끝난다.
    h.auto_px4 = true;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  }
  expect_terminated_once(h, cell.status, cell.reason);
}

INSTANTIATE_TEST_SUITE_P(
  CauseBySnapshot, CauseCrossTable, ::testing::ValuesIn(cause_cells()),
  [](const ::testing::TestParamInfo<CauseCell> & info) { return std::string(info.param.name); });

TEST(CauseCrossTableSize, ThreeByThree) { EXPECT_EQ(cause_cells().size(), 9U); }

}  // namespace
}  // namespace idsim_mission::core::test
