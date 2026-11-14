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

// 지상 arm 진입의 arm 순서 불변식과 ack 대기 구간
// (docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 12). arm은 마지막
// DO_SET_MODE(Offboard 전환)를 보낸 tick보다 뒤의 tick에 받은 그 명령의 비거부 ack가
// 있고 OFFBOARD 3회 연속 확인이 된 tick에만 나간다. 확인 tick은 늘 ack 대기 상태
// PREPARING.OFFBOARD_ACK를 거친다.
//
// - 단위 테스트 다섯 사례(T1-T5)와 그 보조, 대기 중 같은 tick의 이탈과 timeout 대 유효 ack,
//   그리고 확인 tick이나 대기 중 tick에 취소가 겹친 경우의 출력을 단정한다. 대기 구간의
//   나머지 칸(식별 불일치, Px4Timestamp 실패, 무시된 취소 겹침)은 test_runner_flow_cells.cpp의
//   P5a 절이 덮는다.
// - 기본값: command_resend_period 0.5 s = 10 tick, mode_confirm_timeout 3.0 s = 60 tick.
// - P5 진입 tick을 S라 한다(SIGNAL_CONFIRMED, DO_SET_MODE 첫 전송). 가짜 PX4가 S의 전송에 낸 ack는
//   사례마다 지우고(ack 없이 시작) 테스트가 ack를 직접 준다. 표본은 feed로 준다(timestamp는 수신
//   시각 - 1 ms라 tick마다 는다).
// - 확인 뒤 거부 ack와 대기 중 이탈은 PX4 v1.17.0에서 재현하기 어려운 경로라 합성 ack와 합성
//   표본으로만 시험한다.

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

// P5에 들어간 tick(S)까지 간다. 가짜 PX4 반응을 끄고 S의 전송에 대한 ack를 지운다. S를 돌려준다.
// tick_no는 다음 tick 번호라 S = tick_no - 1이다.
std::uint64_t reach_offboard_without_ack(Harness & h)
{
  EXPECT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }, 400));
  h.auto_px4 = false;
  h.snapshot.ack.reset();
  return h.tick_no - 1;
}

Sample offboard_ground() { return disarmed(true, NavMode::kOffboard); }

Sample hold_ground()
{
  Sample s = disarmed(true, NavMode::kHold);
  s.intention = NavMode::kHold;
  return s;
}

// S+1부터 OFFBOARD 표본 셋으로 S+3에 확인해 ack 대기 상태에 둔다(ack 없음).
std::uint64_t reach_offboard_ack(Harness & h)
{
  const std::uint64_t s = reach_offboard_without_ack(h);
  h.feed({offboard_ground(), offboard_ground(), offboard_ground()});
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_FALSE(h.view().arm_sent);
  return s;
}

// 출력 from번째부터 끝까지 ARM, disarm, Hold가 없다.
void expect_no_arm_disarm_hold(const Harness & h, std::size_t from)
{
  for (std::size_t i = from; i < h.outputs().size(); ++i) {
    for (const CommandKind kind : h.outputs()[i].commands) {
      EXPECT_NE(kind, CommandKind::kArm) << "output " << i;
      EXPECT_NE(kind, CommandKind::kDisarm) << "output " << i;
      EXPECT_NE(kind, CommandKind::kSetModeHold) << "output " << i;
    }
  }
}

// ---- T1: 재전송 다음 tick 확인 ----

TEST(OffboardAck, ConfirmAfterResendArmsOnlyOnAckOfThatResend)
{
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  // S+1: S 전송의 ACCEPTED ack. S+8까지는 OFFBOARD가 아니다.
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  for (int i = 0; i < 8; ++i) {
    h.feed({hold_ground()});
  }
  ASSERT_EQ(h.tick_no, s + 9);
  // S+9, S+10: OFFBOARD 1, 2회. S+10에 재전송.
  h.feed({offboard_ground()});
  const StepOutput resend = h.feed({offboard_ground()})[0];
  EXPECT_EQ(resend.commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  // S+11: 확인. S+1의 ack는 S+10 재전송보다 앞이라 무효다.
  std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  EXPECT_TRUE(confirm.commands.empty());
  EXPECT_TRUE(confirm.setpoint.has_value());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_FALSE(h.view().arm_sent);
  // S+12: ack 없음. 아무 명령도 내지 않는다(재전송 없음).
  const StepOutput wait = h.feed({offboard_ground()})[0];
  EXPECT_TRUE(wait.commands.empty());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  // S+13: 재전송의 ack. 그 tick에 arm 하나.
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  before = h.edges().size();
  const StepOutput arm = h.feed({offboard_ground()})[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before);
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.view().prep, PrepStep::kArm);
  EXPECT_TRUE(h.view().arm_sent);
  EXPECT_EQ(h.tick_no, s + 14);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 1);
}

TEST(OffboardAck, AckReceivedOnResendTickIsNotValid)
{
  // 같은 tick에 받은 ack와 재전송은 ack가 먼저다(스냅숏은 tick 시작의 것). 그 ack는 그 재전송의
  // 것이 아니다(received_tick == 마지막 전송 tick은 무효).
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  for (int i = 0; i < 8; ++i) {
    h.feed({hold_ground()});
  }
  h.feed({offboard_ground()});
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  ASSERT_EQ(h.tick_no, s + 10);
  const StepOutput resend = h.feed({offboard_ground()})[0];
  EXPECT_EQ(resend.commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  const StepOutput confirm = h.feed({offboard_ground()})[0];
  EXPECT_TRUE(confirm.commands.empty());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  const StepOutput wait = h.feed({offboard_ground()})[0];
  EXPECT_TRUE(wait.commands.empty());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
}

TEST(OffboardAck, ValidAckBeforeConfirmArmsOnConfirmTick)
{
  // 1a 실측의 보통 경우: ack가 확인보다 먼저 와 있다. 확인 tick에 기록이 둘(CONFIRMED,
  // ACK_ACCEPTED)이고 그 tick에 arm 하나가 나간다(1a와 같은 tick).
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  h.feed({offboard_ground(), offboard_ground()});
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];
  ASSERT_EQ(h.edges().size(), before + 2);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before + 1);
  EXPECT_EQ(h.edges()[before].tick, s + 3);
  EXPECT_EQ(h.edges()[before + 1].tick, s + 3);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
}

// ---- T2: 확인 뒤 ack 없음 ----

TEST(OffboardAck, NoAckAfterConfirmTimesOutWithoutArm)
{
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  const std::size_t confirmed_outputs = h.outputs().size();
  while (h.tick_no < s + 60) {
    h.feed({offboard_ground()});
  }
  EXPECT_FALSE(h.runner().done());  // S+59
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  const std::size_t before = h.edges().size();
  h.feed({offboard_ground()});  // S+60: mode_confirm_timeout(P5 진입부터)
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  expect_no_arm_disarm_hold(h, 0);
  // 확인 tick(S+3) 뒤에는 DO_SET_MODE를 다시 보내지 않는다.
  for (std::size_t i = confirmed_outputs - 1; i < h.outputs().size(); ++i) {
    EXPECT_TRUE(h.outputs()[i].commands.empty()) << "output " << i;
  }
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("no DO_SET_MODE(OFFBOARD) ack"), std::string::npos) << detail;
  EXPECT_EQ(detail.find("not confirmed"), std::string::npos) << detail;
  EXPECT_EQ(detail.find("rejected"), std::string::npos) << detail;
  EXPECT_EQ(detail.find("left"), std::string::npos) << detail;
}

// ---- T3: 확인 뒤 거부 ack ----

TEST(OffboardAck, RejectedAckAfterConfirmFailsWithoutArm)
{
  // 합성 ack: DISARMED에서 DO_SET_MODE 거부는 TERMINATION뿐이다.
  Harness h(standard_mission());
  reach_offboard_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);
  const std::size_t before = h.edges().size();
  h.feed({offboard_ground()});
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {}, before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  expect_no_arm_disarm_hold(h, 0);
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(
    detail.find("DO_SET_MODE(OFFBOARD) rejected after OFFBOARD confirmed: TEMPORARILY_REJECTED"),
    std::string::npos)
    << detail;
}

TEST(OffboardAck, RejectedAckBeforeConfirmKeepsPreparingDetail)
{
  // 대조: 확인 전 거부는 1a 문자열 그대로다.
  Harness h(standard_mission());
  reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);
  h.feed({offboard_ground()});
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("DO_SET_MODE(OFFBOARD) rejected: "), std::string::npos) << detail;
  EXPECT_EQ(detail.find("after OFFBOARD confirmed"), std::string::npos) << detail;
}

// ---- T4: 대기 중 이탈 ----

TEST(OffboardAck, LeavingOffboardWhileWaitingFailsWithoutArm)
{
  // 합성 표본: 지상 DISARMED의 OFFBOARD는 다른 출처의 모드 변경으로만 빠진다.
  Harness h(standard_mission());
  reach_offboard_ack(h);
  const std::size_t end = h.outputs().size();
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({hold_ground()})[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardLeft, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  EXPECT_TRUE(out.commands.empty());  // 재전송도 없다
  expect_no_arm_disarm_hold(h, end);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("OFFBOARD left"), std::string::npos) << detail;
  EXPECT_EQ(detail.find("no DO_SET_MODE(OFFBOARD) ack"), std::string::npos) << detail;
}

TEST(OffboardAck, NonOffboardSampleNotNewerThanConfirmIsNotLeaving)
{
  // timestamp가 확인 표본 이하인 OFFBOARD 아닌 표본은 이탈이 아니다. 확인도 다시 세지 않는다.
  Harness h(standard_mission());
  reach_offboard_ack(h);
  ASSERT_TRUE(h.snapshot.status.has_value());
  const std::uint64_t confirm_us = h.snapshot.status->timestamp_us;
  Sample stale = hold_ground();
  stale.timestamp_us = confirm_us;
  Sample older = hold_ground();
  older.timestamp_us = confirm_us - 1;
  const std::vector<StepOutput> outs = h.feed({stale, older});
  EXPECT_FALSE(h.runner().done());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  for (const StepOutput & out : outs) {
    EXPECT_TRUE(out.commands.empty());
  }
  // 그 뒤의 ack에는 arm한다(확인 고정).
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  Sample still = hold_ground();
  still.timestamp_us = confirm_us;
  const StepOutput arm = h.feed({still})[0];
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.view().prep, PrepStep::kArm);
}

// ---- T5: ack 전 대기 중 취소 ----

TEST(OffboardAck, CancelWhileWaitingEndsCanceledWithoutDisarm)
{
  Harness h(standard_mission());
  reach_offboard_ack(h);
  const std::size_t end = h.outputs().size();
  const std::size_t before = h.edges().size();
  h.feed({offboard_ground()}, true);
  expect_cell(h, "PREPARING.OFFBOARD_ACK", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  expect_terminated_once_as(h, "CANCELED/NONE");
  expect_no_arm_disarm_hold(h, end);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  EXPECT_NE(
    termination_or_empty(h).detail.find("on ground and DISARMED, arm never sent"),
    std::string::npos);
}

// ---- 같은 tick의 취소(칸 명세 3.4) ----

TEST(OffboardAck, CancelOnConfirmTickWithoutAckSendsNothing)
{
  // 1a에서는 확인 tick에 arm을 보내 지상 arm 분기의 disarm을 거쳤다. 지금은 arm 전이라 아무것도
  // 보내지 않고 CANCELED.
  Harness h(standard_mission());
  reach_offboard_without_ack(h);
  h.feed({offboard_ground(), offboard_ground()});
  const std::size_t end = h.outputs().size();
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({offboard_ground()}, true)[0];
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(h, "PREPARING.OFFBOARD_ACK", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_TRUE(out.commands.empty());
  expect_terminated_once_as(h, "CANCELED/NONE");
  expect_no_arm_disarm_hold(h, end);
}

TEST(OffboardAck, CancelOnConfirmTickWithValidAckGoesToGroundDisarm)
{
  // arm 판정이 취소보다 먼저라 arm_sent가 true인 지상 arm 분기로 간다. 그 tick의 arm은 정리
  // 진입이 지워 나가지 않고 disarm 하나가 나간다(1a의 확인 tick 취소와 같은 출력).
  Harness h(standard_mission());
  reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  h.feed({offboard_ground(), offboard_ground()});
  const std::size_t end = h.outputs().size();
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({offboard_ground()}, true)[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before);
  expect_cell(h, "PREPARING.ARM", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_TRUE(h.view().arm_sent);
  EXPECT_EQ(h.view().branch, Branch::kGround);
  for (std::size_t i = end; i < h.outputs().size(); ++i) {
    EXPECT_FALSE(has_command(h.outputs()[i], CommandKind::kArm)) << "output " << i;
  }
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
}

TEST(OffboardAck, AckAndCancelSameTickWhileWaitingGoesToGroundDisarm)
{
  Harness h(standard_mission());
  reach_offboard_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({offboard_ground()}, true)[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before);
  expect_cell(h, "PREPARING.ARM", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_TRUE(h.view().arm_sent);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
}

// ---- 대기 중 같은 tick: 이탈과 timeout이 arm보다 먼저다(decisions.md 쟁점 12 같은 tick 문단) ----

TEST(OffboardAck, LeavingAndValidAckSameTickIsLeftWithoutArm)
{
  // 합성 표본: 유효 ack와 확인 표본보다 새로운 OFFBOARD 아닌 표본이 같은 tick.
  Harness h(standard_mission());
  reach_offboard_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({hold_ground()})[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardLeft, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  EXPECT_TRUE(out.commands.empty());
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_FALSE(h.view().arm_sent);
}

TEST(OffboardAck, TimeoutAndValidAckSameTickIsTimeoutWithoutArm)
{
  // 유효 ack가 mode_confirm_timeout tick(S+60)에 온다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  while (h.tick_no < s + 60) {
    h.feed({offboard_ground()});
  }
  ASSERT_FALSE(h.runner().done());
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({offboard_ground()})[0];
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  EXPECT_TRUE(out.commands.empty());
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_FALSE(h.view().arm_sent);
}

}  // namespace
}  // namespace idsim_mission::core::test
