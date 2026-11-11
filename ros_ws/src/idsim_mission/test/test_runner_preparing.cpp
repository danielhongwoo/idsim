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
// 마지막 문단). P6에서 ARMED를 처음 관측한 뒤의 감시 표, arm 재전송 중단, 확인 기한, 같은 tick의
// 순서, failsafe 이력의 구간(쟁점 4 "P6에서 ARMED를 처음 관측한 뒤").

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
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

TEST(Preparing, NotReadyGoalHasSentNothing)
{
  // 불변식: NOT_READY로 끝난 goal은 setpoint와 명령을 한 건도 내지 않았다(P0 불일치,
  // ready_timeout).
  for (const bool mismatch : {true, false}) {
    Harness h(standard_mission());
    if (mismatch) {
      h.world.identity = IdentityCheck::kMismatch;
    } else {
      h.world.ekf_ready = false;
    }
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 700));
    expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
    for (const StepOutput & out : h.outputs()) {
      EXPECT_FALSE(out.setpoint.has_value());
      EXPECT_TRUE(out.commands.empty());
    }
  }
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
  EXPECT_NE(h.termination()->detail.find("arm_timeout: ARMED not observed"), std::string::npos);
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
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
}

// ---- 검토 보완 ----

TEST(Preparing, P1IsRecheckedWhileWaitingForEkf)
{
  // P2(EKF gate)를 기다리는 동안 누가 arm하면 PRECONDITION_FAILED. 지상 arm을 받지 않는다.
  Harness h(standard_mission());
  h.world.ekf_ready = false;
  for (int i = 0; i < 5; ++i) {
    h.tick();
  }
  EXPECT_FALSE(h.runner().done());
  h.world.arming = Arming::kArmed;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  EXPECT_TRUE(h.commands().empty());
}

TEST(Preparing, NonFinitePositionWaitsThenNotReady)
{
  // P3은 위치가 유한할 때까지 기다리고, ready_timeout에 NOT_READY. 발행을 시작하지 않는다.
  Harness h(standard_mission());
  h.world.z = std::nan("");
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 700));
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
  EXPECT_NE(h.termination()->detail.find("finite vehicle_local_position"), std::string::npos);
}

TEST(Preparing, NonFiniteHeadingWaitsOnlyForKeepYaw)
{
  {
    Harness h(standard_mission());  // MODE_KEEP
    h.world.heading = std::nan("");
    h.tick();
    EXPECT_EQ(h.view().prep, PrepStep::kWaitReady);
    h.world.heading = 0.5;
    h.tick();
    EXPECT_EQ(h.view().prep, PrepStep::kSignal);
    EXPECT_DOUBLE_EQ(h.view().setpoint.yaw_ned, 0.5);
  }
  {
    MissionSpec m = standard_mission();
    m.items[0].takeoff.yaw.mode = yaw_mode::kFixed;
    Harness h(m);
    h.world.heading = std::nan("");
    h.tick();
    EXPECT_EQ(h.view().prep, PrepStep::kSignal);
    EXPECT_TRUE(std::isfinite(h.view().setpoint.yaw_ned));
  }
}

TEST(Preparing, InProgressAckIsNotRejection)
{
  // ACCEPTED와 IN_PROGRESS가 아니면 거부다. IN_PROGRESS는 계속 기다린다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }));
  h.push_ack(AckCommand::kSetMode, AckResult::kInProgress);
  h.tick();
  EXPECT_FALSE(h.runner().done());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }, 10));
  h.push_ack(AckCommand::kArmDisarm, AckResult::kInProgress);
  h.tick();
  EXPECT_FALSE(h.runner().done());
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kItem; }, 10));
}

TEST(Preparing, IdentityMismatchAfterArmSentSendsOneDisarm)
{
  // M2: 첫 ARMED 표본 전, arm을 보낸 뒤의 식별 불일치. 정리 분기는 고르지 않지만 강제가 아닌
  // disarm을 한 번 보낸다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.world.identity = IdentityCheck::kMismatch;
  const StepOutput out = h.tick();
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_TRUE(out.px4_timestamp_us.has_value());
  EXPECT_FALSE(out.setpoint.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
  EXPECT_NE(h.termination()->detail.find("may remain armed"), std::string::npos);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 1);
}

TEST(Preparing, SetpointItemsStartAfterArmSent)
{
  // 불변식: setpoint 항목이 시작될 때 이 goal에서 arm을 보낸 적이 있다(TAKEOFF와 LOITER).
  // 그래서 1a에서 ITEM_TIMEOUT의 "지상 disarm이면 바로 끝" 분기에는 닿지 않는다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  EXPECT_EQ(h.view().item_index, 0U);
  EXPECT_TRUE(h.view().arm_sent);
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 5));
  EXPECT_TRUE(h.view().arm_sent);
}

// ---- P6에서 ARMED를 처음 관측한 뒤(decisions.md 쟁점 4 "P6에서 ARMED를 처음 관측한 뒤") ----

// arm을 처음 보낸 tick까지 간다. 그 tick의 가짜 PX4 반응으로 world는 ARMED다. 그 뒤의 표본은
// 테스트가 직접 준다.
void to_arm_sent(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  ASSERT_EQ(h.count_command(CommandKind::kArm), 1);
  h.auto_px4 = false;
}

// arm을 보낸 다음 tick에 첫 ARMED 표본(OFFBOARD, 지상)을 준다. 확인 1회째다.
void to_first_armed(Harness & h)
{
  to_arm_sent(h);
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, true)});
  ASSERT_FALSE(outs[0].termination.has_value());
  ASSERT_TRUE(h.view().armed_seen);
  ASSERT_EQ(h.view().stage, Stage::kPreparing);
  ASSERT_EQ(h.view().prep, PrepStep::kArm);
}

Sample mode_sample(NavMode nav, NavMode intention, bool failsafe, bool landed = true)
{
  Sample s = armed(nav, landed);
  s.intention = intention;
  s.failsafe = failsafe;
  return s;
}

// 감시 표의 행으로 P6에서 끝난 goal의 공통 단정: 정리 분기 없이 그 tick에 발행을 멈추고, 항목을
// 시작하기 전이므로 last_item_index와 items_completed가 0이다.
void expect_p6_monitor_end(
  Harness & h, const StepOutput & end, Reason reason, int rank, int disarms)
{
  ASSERT_TRUE(end.termination.has_value());
  EXPECT_FALSE(end.setpoint.has_value());
  EXPECT_EQ(end.termination->last_item_index, 0U);
  EXPECT_EQ(end.termination->items_completed, 0U);
  EXPECT_NE(end.termination->detail.find("preparing (arm confirm)"), std::string::npos)
    << end.termination->detail;
  EXPECT_NE(end.termination->detail.find("rank " + std::to_string(rank)), std::string::npos)
    << end.termination->detail;
  EXPECT_EQ(
    static_cast<int>(std::count(end.commands.begin(), end.commands.end(), CommandKind::kDisarm)),
    disarms);
  EXPECT_EQ(end.commands.size(), static_cast<std::size_t>(disarms));
  EXPECT_NE(h.view().stage, Stage::kCleanup);
  expect_terminated_once(h, Status::kAborted, reason);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
}

TEST(P6AfterArmed, ExternalModeAfterTwoConfirmsEndsWithoutWaitingForDeadline)
{
  // 확인 2회 뒤의 외부 모드 변경(순위 7): 확인 기한을 기다리지 않고 그 tick에 끝낸다. 지상이고
  // landed false를 본 적이 없으므로 강제가 아닌 disarm 1회.
  Harness h(standard_mission());
  to_first_armed(h);
  h.feed({armed(NavMode::kOffboard, true)});
  const std::vector<StepOutput> outs = h.feed({mode_sample(NavMode::kHold, NavMode::kHold, false)});
  expect_p6_monitor_end(h, outs[0], Reason::kExternalModeChange, 7, 1);
  EXPECT_NE(h.termination()->detail.find("may remain armed"), std::string::npos);
}

TEST(P6AfterArmed, FailsafeModeIsFailsafe)
{
  // failsafe로 OFFBOARD를 벗어난 표본(순위 6).
  Harness h(standard_mission());
  to_first_armed(h);
  const std::vector<StepOutput> outs =
    h.feed({mode_sample(NavMode::kLand, NavMode::kOffboard, true)});
  expect_p6_monitor_end(h, outs[0], Reason::kFailsafe, 6, 1);
}

TEST(P6AfterArmed, DefensiveRowIsFailsafe)
{
  // 방어 경로(합성 표본): failsafe 없이 사용자 의도가 OFFBOARD인 채 nav_state만 다른 표본(순위 8)은
  // v1.17.0 정상 상태에서 나오지 않는다.
  Harness h(standard_mission());
  to_first_armed(h);
  const std::vector<StepOutput> outs =
    h.feed({mode_sample(NavMode::kHold, NavMode::kOffboard, false)});
  expect_p6_monitor_end(h, outs[0], Reason::kFailsafe, 8, 1);
}

TEST(P6AfterArmed, FirstArmedSampleAlreadyNotOffboard)
{
  // 첫 ARMED 표본이 이미 OFFBOARD가 아니어도 첫 ARMED 표본이고, 그 tick에 감시 표가 끝낸다.
  Harness h(standard_mission());
  to_arm_sent(h);
  const std::vector<StepOutput> outs = h.feed({mode_sample(NavMode::kHold, NavMode::kHold, false)});
  EXPECT_TRUE(h.view().armed_seen);
  expect_p6_monitor_end(h, outs[0], Reason::kExternalModeChange, 7, 1);
}

TEST(P6AfterArmed, DisarmedInAirAndOnGround)
{
  // ARMED 뒤 DISARMED(순위 4, 5): 이미 DISARMED라 disarm을 보내지 않는다.
  {
    Harness h(standard_mission());
    to_first_armed(h);
    const std::vector<StepOutput> outs = h.feed({disarmed(false)});
    expect_p6_monitor_end(h, outs[0], Reason::kFailsafe, 4, 0);
  }
  {
    Harness h(standard_mission());
    to_first_armed(h);
    const std::vector<StepOutput> outs = h.feed({disarmed(true)});
    expect_p6_monitor_end(h, outs[0], Reason::kExternalDisarm, 5, 0);
  }
}

TEST(P6AfterArmed, LinkLostIsLinkLostWithGroundDisarm)
{
  // ARMED 뒤 vehicle_status가 link_timeout(2 s) 동안 없으면 순위 3. landed는 끊기기 전의 값(true).
  Harness h(standard_mission());
  to_first_armed(h);
  const std::vector<StepOutput> quiet = h.feed(std::vector<Sample>(39, no_new_sample()));
  for (const StepOutput & out : quiet) {
    ASSERT_FALSE(out.termination.has_value());
  }
  const std::vector<StepOutput> outs = h.feed({no_new_sample()});
  expect_p6_monitor_end(h, outs[0], Reason::kLinkLost, 3, 1);
}

TEST(P6AfterArmed, TimestampFailureIsInternalWithoutCommands)
{
  // 순위 1: 명령에 실을 시각이 없어 disarm을 보내지 않는다. 발행을 한 뒤라 기체 상태를 모른다.
  Harness h(standard_mission());
  to_first_armed(h);
  h.clock.fail = true;
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, true)});
  expect_p6_monitor_end(h, outs[0], Reason::kInternal, 1, 0);
  EXPECT_FALSE(outs[0].px4_timestamp_us.has_value());
  EXPECT_NE(h.termination()->detail.find("vehicle state unknown"), std::string::npos);
}

TEST(P6AfterArmed, IdentityMismatchSendsDisarmRegardlessOfLanded)
{
  // 순위 2: arm을 보냈으므로 landed와 이력을 보지 않고 disarm 1회.
  Harness h(standard_mission());
  to_first_armed(h);
  h.feed({armed(NavMode::kOffboard, false)});  // landed false를 본 이력
  h.world.identity = IdentityCheck::kMismatch;
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, false)});
  expect_p6_monitor_end(h, outs[0], Reason::kInternal, 2, 1);
}

TEST(P6AfterArmed, SamplesOlderThanFirstArmedAreNotJudged)
{
  // 첫 ARMED 표본보다 timestamp가 작은 표본은 감시 표에도 확인 계수에도 쓰지 않는다(합성 표본).
  {
    Harness h(standard_mission());
    to_first_armed(h);
    const std::uint64_t first_ts = h.snapshot.status->timestamp_us;
    Sample old_air_disarm = disarmed(false);
    old_air_disarm.timestamp_us = first_ts - 500;
    Sample old_hold = mode_sample(NavMode::kHold, NavMode::kHold, false);
    old_hold.timestamp_us = first_ts - 400;
    const std::vector<StepOutput> outs = h.feed({old_air_disarm, old_hold});
    EXPECT_FALSE(outs[0].termination.has_value());
    EXPECT_FALSE(outs[1].termination.has_value());
    EXPECT_EQ(h.view().prep, PrepStep::kArm);
    // 확인은 첫 ARMED 표본에 둘을 더해 3회. 묵은 표본은 계수를 0으로 되돌리지 않았다.
    h.feed({armed(NavMode::kOffboard, true), armed(NavMode::kOffboard, true)});
    EXPECT_EQ(h.view().stage, Stage::kItem);
  }
  {
    // 묵은 표본만 오면 직전에 쓴 표본의 수신 시각부터 link_timeout이 흘러 순위 3.
    Harness h(standard_mission());
    to_first_armed(h);
    Sample stale = armed(NavMode::kOffboard, true);
    stale.timestamp_us = h.snapshot.status->timestamp_us - 1;
    const std::vector<StepOutput> quiet = h.feed(std::vector<Sample>(39, stale));
    for (const StepOutput & out : quiet) {
      ASSERT_FALSE(out.termination.has_value());
    }
    const std::vector<StepOutput> outs = h.feed({stale});
    expect_p6_monitor_end(h, outs[0], Reason::kLinkLost, 3, 1);
  }
}

// ---- P6의 범위 고정 ----

TEST(P6Scope, DisarmedNonOffboardBeforeArmedDoesNotEnd)
{
  // ARMED를 보기 전의 DISARMED이고 OFFBOARD가 아닌 표본은 감시 표의 대상이 아니다.
  Harness h(standard_mission());
  to_arm_sent(h);
  Sample s = disarmed(true, NavMode::kHold);
  s.intention = NavMode::kHold;
  const std::vector<StepOutput> outs = h.feed(std::vector<Sample>(10, s));
  for (const StepOutput & out : outs) {
    EXPECT_FALSE(out.termination.has_value());
  }
  EXPECT_FALSE(h.view().armed_seen);
  EXPECT_EQ(h.view().prep, PrepStep::kArm);
}

TEST(P6Scope, ArmedSampleBeforeArmSendIsNotFirstObservation)
{
  // 합성 표본: arm을 보낸 tick 이전에 받은 ARMED 표본은 "처음 관측"이 아니다. arm 재전송이
  // 이어진다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;  // 누군가 arm한 표본이 OFFBOARD 확인 중에 온다
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }, 10));
  ASSERT_EQ(h.snapshot.status->arming, Arming::kArmed);
  h.feed(std::vector<Sample>(15, no_new_sample()));
  EXPECT_FALSE(h.view().armed_seen);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 2);
  EXPECT_FALSE(h.runner().done());
}

TEST(P6Scope, NoArmResendAfterFirstArmedAndDeadlineEndsWithArmRejected)
{
  // 첫 ARMED 표본 뒤 timestamp가 늘지 않는 표본만 오면(합성 표본) 확인 3회가 차지 않는다. 그
  // 시각부터 mode_confirm_timeout(3 s)에 ARM_REJECTED와 정리 분기. 그동안 arm 재전송은 없다.
  Harness h(standard_mission());
  to_arm_sent(h);
  Sample stuck = armed(NavMode::kOffboard, true);
  stuck.timestamp_us = h.default_timestamp_us();
  const std::vector<StepOutput> wait = h.feed(std::vector<Sample>(60, stuck));
  for (const StepOutput & out : wait) {
    ASSERT_FALSE(out.termination.has_value());
    EXPECT_TRUE(out.commands.empty());
  }
  EXPECT_EQ(h.view().stage, Stage::kPreparing);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 1);
  const std::vector<StepOutput> end = h.feed({stuck});  // 첫 ARMED 표본에서 3.0 s
  EXPECT_EQ(h.view().stage, Stage::kCleanup);
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kPreparingFailure);
  EXPECT_EQ(h.view().branch, Branch::kGround);
  EXPECT_EQ(end[0].commands, std::vector<CommandKind>{CommandKind::kDisarm});
  h.auto_px4 = true;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  expect_terminated_once(h, Status::kAborted, Reason::kArmRejected);
  EXPECT_NE(h.termination()->detail.find("ARMED observed"), std::string::npos)
    << h.termination()->detail;
  EXPECT_EQ(h.count_command(CommandKind::kArm), 1);
}

TEST(P6Scope, LateRejectAckOnFirstArmedTickIsIgnored)
{
  // 방어 경로(합성 ack): 첫 ARMED 표본과 같은 tick에 온 거부 ack는 보지 않는다(status를 먼저 보고
  // 대기 명령을 지운 뒤 ack를 읽는다).
  Harness h(standard_mission());
  to_arm_sent(h);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, true)});
  EXPECT_FALSE(outs[0].termination.has_value());
  EXPECT_EQ(h.view().stage, Stage::kPreparing);
  EXPECT_FALSE(h.view().pending_active);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);  // 그 뒤의 ARM ack도 보지 않는다
  h.feed({armed(NavMode::kOffboard, true), armed(NavMode::kOffboard, true)});
  EXPECT_EQ(h.view().stage, Stage::kItem);
}

// ---- P6의 확인 기한 ----

TEST(P6Deadline, LateAcceptanceConfirmsPastArmTimeout)
{
  // arm이 TEMPORARILY_REJECTED 재시도 끝에 늦게 받아들여짐: 첫 ARMED 표본이 arm 전송 뒤 4.2 s이고
  // 확인 3회째는 5.2 s(arm_timeout 뒤)다. 확인 기한은 첫 ARMED 표본부터라 TAKEOFF를 시작한다.
  Harness h(standard_mission());
  to_arm_sent(h);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  const std::vector<StepOutput> before = h.feed(std::vector<Sample>(83, disarmed(true)));
  for (const StepOutput & out : before) {
    ASSERT_FALSE(out.termination.has_value());
  }
  h.feed({armed(NavMode::kOffboard, true)});  // 4.2 s
  ASSERT_TRUE(h.view().armed_seen);
  const int arms = h.count_command(CommandKind::kArm);
  std::vector<Sample> sparse(9, no_new_sample());
  sparse.push_back(armed(NavMode::kOffboard, true));  // 4.7 s
  h.feed(sparse);
  EXPECT_EQ(h.view().stage, Stage::kPreparing);
  h.feed(sparse);  // 5.2 s: 확인 3회
  EXPECT_FALSE(h.runner().done());
  EXPECT_EQ(h.view().stage, Stage::kItem);
  EXPECT_EQ(h.count_command(CommandKind::kArm), arms);  // 첫 ARMED 뒤 재전송 없음
}

TEST(P6Deadline, FirstArmedOnArmTimeoutTickStartsDeadline)
{
  // 첫 ARMED 표본과 arm_timeout 만료가 같은 tick이면 표본 하나로 정해지는 관측이 앞이다.
  Harness h(standard_mission());
  to_arm_sent(h);
  h.feed(std::vector<Sample>(99, disarmed(true)));
  ASSERT_FALSE(h.runner().done());
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, true)});  // 5.0 s
  EXPECT_FALSE(outs[0].termination.has_value());
  EXPECT_EQ(h.view().stage, Stage::kPreparing);
  EXPECT_TRUE(h.view().armed_seen);
  h.feed({armed(NavMode::kOffboard, true), armed(NavMode::kOffboard, true)});
  EXPECT_EQ(h.view().stage, Stage::kItem);
}

TEST(P6Deadline, ArmTimeoutBeforeAnyArmedIsArmRejected)
{
  // 대조군: ARMED를 한 번도 보지 못하면 arm_timeout(5 s)에 ARM_REJECTED.
  Harness h(standard_mission());
  to_arm_sent(h);
  h.feed(std::vector<Sample>(99, disarmed(true)));
  ASSERT_EQ(h.view().stage, Stage::kPreparing);
  h.feed({disarmed(true)});
  EXPECT_EQ(h.view().stage, Stage::kCleanup);
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kPreparingFailure);
}

// ---- P6의 같은 tick ----

TEST(P6SameTick, MonitorRowBeatsConfirmDeadline)
{
  // 확인 기한 만료 tick에 감시 표의 행이 함께 맞으면 감시 표의 행이 이긴다(정리 없이 끝난다).
  Harness h(standard_mission());
  to_arm_sent(h);
  Sample stuck = armed(NavMode::kOffboard, true);
  stuck.timestamp_us = h.default_timestamp_us();
  h.feed(std::vector<Sample>(60, stuck));
  ASSERT_EQ(h.view().stage, Stage::kPreparing);
  const std::vector<StepOutput> outs = h.feed({mode_sample(NavMode::kHold, NavMode::kHold, false)});
  expect_p6_monitor_end(h, outs[0], Reason::kExternalModeChange, 7, 1);
}

TEST(P6SameTick, MonitorRowBeatsCancel)
{
  Harness h(standard_mission());
  to_first_armed(h);
  const std::vector<StepOutput> outs =
    h.feed({mode_sample(NavMode::kLand, NavMode::kOffboard, true)}, true);
  expect_p6_monitor_end(h, outs[0], Reason::kFailsafe, 6, 1);
}

// ---- failsafe 이력의 구간 ----

TEST(P6History, FailsafeHistorySpansP6AndTakeoff)
{
  // 방어 경로(합성 표본). P6의 ARMED 확인 구간과 TAKEOFF는 한 이력 구간이다(첫 ARMED 표본 포함).
  // P6에서 본 failsafe 이력으로 TAKEOFF 중 지상 DISARMED는 FAILSAFE다.
  Harness h(standard_mission());
  to_arm_sent(h);
  Sample first = armed(NavMode::kOffboard, true);
  first.failsafe = true;  // OFFBOARD이고 ARMED인 채 failsafe: 어느 행에도 맞지 않는다
  h.feed({first, armed(NavMode::kOffboard, true), armed(NavMode::kOffboard, true)});
  ASSERT_EQ(h.view().stage, Stage::kItem);
  EXPECT_TRUE(h.view().failsafe_history);
  const std::vector<StepOutput> outs = h.feed({armed(NavMode::kOffboard, true), disarmed(true)});
  EXPECT_FALSE(outs[0].termination.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
  EXPECT_NE(h.termination()->detail.find("rank 5"), std::string::npos);
}

}  // namespace
}  // namespace idsim_mission::core::test
