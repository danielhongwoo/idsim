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

// LAND 항목(WAITING_MODE)의 세 구간 감시, 완료 우선 규칙, 대비책 disarm, LAND의 ITEM_TIMEOUT.
// 결정: decisions.md 쟁점 4 "LAND 항목의 감시", 항목 표의 LAND 행, LAND 항목의 ITEM_TIMEOUT.

#include <gtest/gtest.h>

#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

TEST(Land, ScenarioASucceedsAndStopsPublishingAtFirstAutoLand)
{
  Harness h(standard_mission());
  h.drive_to_land();
  // 다음 tick에 AUTO_LAND를 처음 관측한다. 그 tick부터 발행하지 않는다.
  const StepOutput first_land = h.tick();
  EXPECT_FALSE(first_land.setpoint.has_value());
  EXPECT_FALSE(h.view().publishing);
  ASSERT_TRUE(first_land.feedback.has_value());
  EXPECT_EQ(first_land.feedback->phase, FeedbackPhase::kWaitingMode);
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  EXPECT_FALSE(h.view().pending_active);  // NAV_LAND 재전송을 멈췄다
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 1);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  // 발행은 한 번 멈춘 뒤 다시 켜지지 않았다.
  bool seen_publish = false;
  bool stopped = false;
  for (const StepOutput & out : h.outputs()) {
    if (out.setpoint.has_value()) {
      EXPECT_FALSE(stopped);
      seen_publish = true;
    } else if (seen_publish) {
      stopped = true;
    }
  }
  EXPECT_TRUE(stopped);
}

TEST(Land, LeavingAutoLandWhileArmedAfterConfirm)
{
  for (const bool failsafe : {false, true}) {
    Harness h(standard_mission());
    h.drive_to_land();
    ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
    h.auto_px4 = false;
    Sample s = armed(NavMode::kHold);
    s.failsafe = failsafe;
    h.feed({s});
    expect_terminated_once(
      h, Status::kAborted, failsafe ? Reason::kFailsafe : Reason::kExternalModeChange);
  }
}

TEST(Land, FlappingBeforeConfirmIsNotDeparture)
{
  // 처음 관측과 3회 연속 사이의 흔들림: 계수만 0으로 되돌린다. 멈춘 발행은 다시 켜지 않는다.
  Harness h(standard_mission());
  h.drive_to_land();
  h.auto_px4 = false;
  const std::vector<StepOutput> outs = h.feed({
    armed(NavMode::kLand),
    armed(NavMode::kOffboard),
    armed(NavMode::kLand),
    armed(NavMode::kLand),
  });
  for (const StepOutput & out : outs) {
    EXPECT_FALSE(out.termination.has_value());
    EXPECT_FALSE(out.setpoint.has_value());
  }
  EXPECT_FALSE(h.view().land_confirmed);
  h.feed({armed(NavMode::kLand)});
  EXPECT_TRUE(h.view().land_confirmed);
  EXPECT_FALSE(h.runner().done());
}

TEST(Land, OtherModeBeforeConfirmStopsPublishingOnly)
{
  // 확인 전 구간: OFFBOARD도 AUTO_LAND도 아닌 표본은 발행만 멈추고 이탈로 보지 않는다.
  // NAV_LAND 재전송과 mode_confirm_timeout은 이어 간다.
  Harness h(standard_mission());
  h.drive_to_land();
  h.auto_px4 = false;
  Sample other = armed(NavMode::kOther);
  other.failsafe = true;  // offboard 손실 failsafe 같은 표본
  h.feed({other});
  EXPECT_FALSE(h.runner().done());
  EXPECT_FALSE(h.view().publishing);
  std::vector<Sample> seq(9, other);
  const std::vector<StepOutput> outs = h.feed(seq);
  EXPECT_TRUE(has_command(outs.back(), CommandKind::kNavLand));  // 0.5 s 재전송
  for (const StepOutput & out : outs) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
}

TEST(Land, DisarmedOnGroundCompletesWhateverNav)
{
  // 자동 disarm과 동시에 nav_state가 사용자 의도로 돌아가도 완료 계수가 우선한다.
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.auto_px4 = false;
  h.feed({disarmed(true, NavMode::kOffboard), disarmed(true, NavMode::kOther)});
  EXPECT_FALSE(h.runner().done());
  h.feed({disarmed(true, NavMode::kHold)});
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(Land, DisarmedNotLandedIsFailsafe)
{
  Harness h(standard_mission());
  h.drive_to_land();
  h.auto_px4 = false;
  h.feed({disarmed(false, NavMode::kLand)});
  expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
}

TEST(Land, DisarmClassIsFixedAtFirstDisarmed)
{
  // 첫 DISARMED 때 landed가 true이면, 뒤에 landed가 false인 표본이 와도 완료로 센다.
  {
    Harness h(standard_mission());
    h.drive_to_land();
    ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
    h.auto_px4 = false;
    h.feed(
      {disarmed(true, NavMode::kLand), disarmed(false, NavMode::kLand),
       disarmed(false, NavMode::kLand)});
    expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
  }
  // 반대: 첫 DISARMED 때 landed가 false이면 FAILSAFE이고 뒤의 landed true로 바뀌지 않는다.
  {
    Harness h(standard_mission());
    h.drive_to_land();
    h.auto_px4 = false;
    h.feed({disarmed(false, NavMode::kLand), disarmed(true, NavMode::kLand)});
    expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
  }
}

TEST(Land, ArmedSampleResetsDisarmCount)
{
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.auto_px4 = false;
  h.feed(
    {disarmed(true, NavMode::kLand), disarmed(true, NavMode::kLand), armed(NavMode::kLand, true),
     disarmed(true, NavMode::kLand), disarmed(true, NavMode::kLand)});
  EXPECT_FALSE(h.runner().done());
  h.feed({disarmed(true, NavMode::kLand)});
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(Land, ModeConfirmTimeoutBoundary)
{
  Harness h(standard_mission());
  h.drive_to_land();
  h.auto_px4 = false;
  h.world.nav = NavMode::kOffboard;  // NAV_LAND가 먹지 않는다
  // NAV_LAND는 LAND 시작 tick에 보냈다. 2.95 s까지 59 tick.
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  EXPECT_TRUE(h.view().publishing);  // OFFBOARD인 동안 발행 유지
  const StepOutput out = h.tick();
  EXPECT_FALSE(out.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 6);
}

TEST(Land, FallbackDisarmAfterDelayOnly)
{
  // 대비책: AUTO_LAND 확인 뒤 landed이고 ARMED인 채 land_disarm_fallback_delay(5 s)가 지나면
  // 강제가 아닌 disarm. 그 전에는 보내지 않는다.
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.world.landed = true;  // 자동 disarm이 오지 않는다
  h.tick();               // landed이고 ARMED를 처음 본 tick
  for (int i = 0; i < 99; ++i) {
    const StepOutput out = h.tick();
    EXPECT_TRUE(out.commands.empty()) << i;
  }
  const StepOutput fallback = h.tick();  // 5.0 s
  EXPECT_EQ(fallback.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(Land, FallbackDisarmResendsWhileRejected)
{
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.world.landed = true;
  h.auto_px4 = false;
  ASSERT_TRUE(h.run_until([&h] { return h.count_command(CommandKind::kDisarm) == 1; }, 200));
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  for (int i = 0; i < 10; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 2);
  EXPECT_FALSE(h.runner().done());
}

TEST(LandItemTimeout, ConfirmedButNeverDisarmed)
{
  // NAV_LAND와 대비책 disarm의 재전송을 멈추고 끝낸다. Hold는 보내지 않는다.
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.world.landed = true;
  h.auto_px4 = false;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 700));
  const StepOutput & last = h.outputs().back();
  EXPECT_TRUE(last.commands.empty());
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("AUTO_LAND was confirmed"), std::string::npos);
  EXPECT_NE(h.termination()->detail.find("landed and still ARMED"), std::string::npos);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
}

TEST(LandItemTimeout, TimerStartsAtPreviousItemEnd)
{
  // LAND의 timeout은 앞 항목이 끝난 tick부터 흐른다. 확인된 뒤 땅에 닿지 않는 경우.
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  // drive_to_land의 마지막 tick이 시작이고 확인까지 3 tick을 썼다. 30 s는 600 tick.
  for (int i = 0; i < 596; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
}

TEST(LandItemTimeout, LandOnlyNavLandNotArrived)
{
  // [LAND] 단독 미션에서 AUTO_LAND를 못 본 채 ITEM_TIMEOUT이 되는 것은 timeout이
  // mode_confirm_timeout보다 짧을 때뿐이다. detail에 어느 쪽인지 적는다.
  Harness h(land_only_mission(2));
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.auto_px4 = false;
  for (int i = 0; i < 40; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();  // 2.0 s
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(h.termination()->detail.find("AUTO_LAND not observed"), std::string::npos);
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
}

TEST(LandItemTimeout, LandOnlyNavLandAcceptedOrObserved)
{
  {
    Harness h(land_only_mission(2));
    h.world.arming = Arming::kArmed;
    h.world.landed = false;
    h.auto_px4 = false;
    h.tick();
    h.push_ack(AckCommand::kNavLand, AckResult::kAccepted);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
    EXPECT_NE(h.termination()->detail.find("NAV_LAND accepted"), std::string::npos);
  }
  {
    Harness h(land_only_mission(2));
    h.world.arming = Arming::kArmed;
    h.world.landed = false;
    h.auto_px4 = false;
    h.tick();
    h.feed({armed(NavMode::kLand), armed(NavMode::kHold)});
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
    EXPECT_NE(h.termination()->detail.find("observed but not confirmed"), std::string::npos);
  }
}

TEST(LandItemTimeout, StopsPublishingWhenStillOffboard)
{
  // 확인 전이고 아직 발행 중(OFFBOARD)에 ITEM_TIMEOUT이면 발행을 멈춘다(뒤는 offboard 손실 Land).
  MissionSpec m = standard_mission();
  m.items[2].timeout = seconds(2);
  Harness h(m);
  h.drive_to_land();
  h.auto_px4 = false;
  h.world.nav = NavMode::kOffboard;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_FALSE(h.outputs().back().setpoint.has_value());
  EXPECT_TRUE(h.outputs().back().commands.empty());
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
}

TEST(Land, LinkLostAndIdentityMismatch)
{
  {
    Harness h(standard_mission());
    h.drive_to_land();
    h.auto_samples = false;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_terminated_once(h, Status::kAborted, Reason::kLinkLost);
  }
  {
    Harness h(standard_mission());
    h.drive_to_land();
    h.world.identity = IdentityCheck::kMismatch;
    h.tick();
    expect_terminated_once(h, Status::kAborted, Reason::kInternal);
    EXPECT_NE(h.termination()->detail.find("expected sysid 2"), std::string::npos);
  }
}

// ---- 대비책 disarm의 부정 시험(px4-engineer N5-4) ----

TEST(Land, FallbackNotSentBeforeAutoLandConfirm)
{
  // AUTO_LAND 확인 전에는 landed이고 ARMED가 오래 이어져도 보내지 않는다. 확인 전 구간이 5 s를
  // 넘도록 mode_confirm_timeout을 늘린 설정으로 본다.
  Config config;
  config.timeouts.mode_confirm_timeout_ns = 10 * kNsPerSecond;
  Harness h(standard_mission(), config);
  h.drive_to_land();
  h.auto_px4 = false;
  h.world.nav = NavMode::kOffboard;
  h.world.landed = true;
  for (int i = 0; i < 160; ++i) {  // 8 s
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  EXPECT_FALSE(h.view().land_confirmed);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
}

TEST(Land, FallbackDelayRestartsWhenLandedDrops)
{
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.auto_px4 = false;
  h.world.landed = true;
  for (int i = 0; i < 60; ++i) {  // 3 s
    h.tick();
  }
  h.world.landed = false;
  h.tick();
  h.world.landed = true;
  h.tick();  // 지연이 여기서 다시 시작한다
  for (int i = 0; i < 99; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  const StepOutput out = h.tick();  // 다시 시작한 뒤 5.0 s
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kDisarm});
}

}  // namespace
}  // namespace idsim_mission::core::test
