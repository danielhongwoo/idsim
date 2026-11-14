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
// - 유효 ack가 없는 동안의 DO_SET_MODE 재전송(P5부터 arm 전까지, 확인 tick 포함): 재전송이나
//   그 ack의 유실 회복, 유효 ack의 재전송 억제, 주기가 찬 tick의 확인, 실패, 취소, 앞선 전송의
//   늦은 ack를 단정한다.
// - 기본값: command_resend_period 0.5 s = 10 tick, mode_confirm_timeout 3.0 s = 60 tick.
// - P5 진입 tick을 S라 한다(SIGNAL_CONFIRMED, DO_SET_MODE 첫 전송). 가짜 PX4가 S의 전송에 낸 ack는
//   사례마다 지우고(ack 없이 시작) 테스트가 ack를 직접 준다. 표본은 feed로 준다(timestamp는 수신
//   시각 - 1 ms라 tick마다 는다).
// - 확인 뒤 거부 ack와 대기 중 이탈은 PX4 v1.17.0에서 재현하기 어려운 경로라 합성 ack와 합성
//   표본으로만 시험한다.

#include <gtest/gtest.h>

#include <algorithm>
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

// tick first..last의 출력에서 명령은 resend_ticks의 tick에만 있고 그것은 DO_SET_MODE 하나다.
void expect_resends_only_at(
  const Harness & h, std::uint64_t first, std::uint64_t last,
  const std::vector<std::uint64_t> & resend_ticks)
{
  for (std::uint64_t tick = first; tick <= last; ++tick) {
    const StepOutput * const out = output_of_tick(h, tick);
    if (out == nullptr) {
      return;
    }
    const bool due =
      std::find(resend_ticks.begin(), resend_ticks.end(), tick) != resend_ticks.end();
    if (due) {
      EXPECT_EQ(out->commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard})
        << "tick " << tick;
    } else {
      EXPECT_TRUE(out->commands.empty()) << "tick " << tick;
    }
  }
}

// 같은 표본을 tick last까지(포함) 준다.
void feed_through(Harness & h, const Sample & sample, std::uint64_t last)
{
  while (h.tick_no <= last) {
    h.feed({sample});
  }
}

// ---- T1: 재전송 다음 tick 확인 ----

TEST(OffboardAck, ConfirmAfterResendArmsOnlyOnAckOfThatResend)
{
  // S 전송의 ack가 없다(있으면 유효 ack라 S+10 재전송이 나가지 않는다). S+8까지는 OFFBOARD가
  // 아니다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  for (int i = 0; i < 8; ++i) {
    h.feed({hold_ground()});
  }
  ASSERT_EQ(h.tick_no, s + 9);
  // S+9, S+10: OFFBOARD 1, 2회. S+10에 재전송.
  h.feed({offboard_ground()});
  const StepOutput resend = h.feed({offboard_ground()})[0];
  EXPECT_EQ(resend.commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  // S+11: 확인. 유효 ack가 없고 재전송 주기(기준 S+10)는 차지 않았다.
  std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];
  ASSERT_EQ(h.edges().size(), before + 1);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  EXPECT_TRUE(confirm.commands.empty());
  EXPECT_TRUE(confirm.setpoint.has_value());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_FALSE(h.view().arm_sent);
  // S+12: ack 없음. 주기가 차지 않아 명령이 없다.
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

TEST(OffboardAck, AckOnResendDueTickSuppressesResend)
{
  // 재전송 주기가 찬 tick(S+10)에 받은 비거부 ack는 판정 시점의 마지막 전송(S)보다 뒤라 유효이고,
  // ack 판정이 재전송보다 앞이라 그 tick의 재전송을 막는다(received_tick == 마지막 전송 tick인
  // ack는 이 순서에서 생기지 않는다).
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  for (int i = 0; i < 8; ++i) {
    h.feed({hold_ground()});
  }
  h.feed({offboard_ground()});
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  ASSERT_EQ(h.tick_no, s + 10);
  const StepOutput due = h.feed({offboard_ground()})[0];
  EXPECT_TRUE(due.commands.empty());
  EXPECT_EQ(h.view().prep, PrepStep::kOffboard);
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];  // S+11
  ASSERT_EQ(h.edges().size(), before + 2);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before + 1);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
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
  // 확인(S+3) 뒤 유효 ack가 없는 동안 주기마다 재전송하고, 그래도 없으면 S+60에 끝난다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  feed_through(h, offboard_ground(), s + 59);
  EXPECT_FALSE(h.runner().done());  // S+59
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  const std::size_t before = h.edges().size();
  h.feed({offboard_ground()});  // S+60: mode_confirm_timeout(P5 진입부터)
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  expect_no_arm_disarm_hold(h, 0);
  // S+10..S+50에 하나씩. S+60은 주기가 찼지만 timeout이 재전송보다 앞이라 명령이 없다.
  expect_resends_only_at(h, s + 3, s + 60, {s + 10, s + 20, s + 30, s + 40, s + 50});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 6);
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

// ---- 유효 ack가 없는 동안의 재전송(decisions.md 쟁점 12 "명령과 ack의 유실") ----
// 단위 테스트에서 재전송의 유실과 그 ack의 유실은 core 입력이 같다(ack가 오지 않음).

TEST(OffboardAck, LostResendBeforeConfirmRecoversByNextResend)
{
  // CI 재현: S, S+10 전송의 ack가 없고 S+20 재전송이 유실되었다. S+21에 확인된 뒤에도 주기마다
  // 재전송하고, S+30 재전송의 ack로 arm한다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  feed_through(h, hold_ground(), s + 18);
  feed_through(h, offboard_ground(), s + 20);
  const std::size_t before = h.edges().size();
  h.feed({offboard_ground()});  // S+21: 확인
  ASSERT_EQ(h.edges().size(), before + 1);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  EXPECT_EQ(h.edges()[before].tick, s + 21);
  feed_through(h, offboard_ground(), s + 30);
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_FALSE(h.view().arm_sent);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before_arm = h.edges().size();
  const StepOutput arm = h.feed({offboard_ground()})[0];  // S+31
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before_arm);
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  expect_resends_only_at(h, s + 1, s + 30, {s + 10, s + 20, s + 30});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 4);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 1);
  EXPECT_FALSE(h.runner().done());
}

TEST(OffboardAck, CiInputArmsOnFirstAckWithoutResend)
{
  // CI 입력 그대로: S 전송의 ACCEPTED ack가 S+1에 온다. 그 뒤로 재전송이 없어 S+20 유실은 생기지
  // 않고, 확인 tick에 arm한다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  feed_through(h, hold_ground(), s + 18);
  feed_through(h, offboard_ground(), s + 20);
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];  // S+21
  ASSERT_EQ(h.edges().size(), before + 2);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before + 1);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kArm});
  expect_resends_only_at(h, s + 1, s + 20, {});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
}

TEST(OffboardAck, LostAckOfWaitingResendArmsOnNextPeriod)
{
  // 확인(S+3) 뒤 S+10 재전송의 ack가 유실되고 S+20 재전송의 ack(S+21)로 arm한다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  feed_through(h, offboard_ground(), s + 20);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput arm = h.feed({offboard_ground()})[0];  // S+21
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before);
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  expect_resends_only_at(h, s + 4, s + 20, {s + 10, s + 20});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 3);
}

class ValidAckBeforeLongConfirm : public ::testing::TestWithParam<AckResult>
{
};

TEST_P(ValidAckBeforeLongConfirm, ValidAckStopsResendAndArmsOnConfirmTick)
{
  // 확인 전에 받은 비거부 ack(ACCEPTED, IN_PROGRESS)가 있으면 S+10, S+20에도 재전송하지 않고
  // 확인 tick(S+25)에 arm한다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, GetParam());
  feed_through(h, hold_ground(), s + 22);
  feed_through(h, offboard_ground(), s + 24);
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];  // S+25
  ASSERT_EQ(h.edges().size(), before + 2);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before + 1);
  EXPECT_EQ(h.edges()[before].tick, s + 25);
  EXPECT_EQ(h.edges()[before + 1].tick, s + 25);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kArm});
  expect_resends_only_at(h, s + 1, s + 24, {});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
}

INSTANTIATE_TEST_SUITE_P(
  OffboardAck, ValidAckBeforeLongConfirm,
  ::testing::Values(AckResult::kAccepted, AckResult::kInProgress));

TEST(OffboardAck, ConfirmOnResendDueTickWithoutAckResendsOnly)
{
  // 확인 tick(S+10)이 재전송 주기가 찬 tick이고 유효 ack가 없다. 기록은 CONFIRMED 하나이고
  // 그 tick에 DO_SET_MODE 하나만 나간다(arm 없음). 그 재전송 뒤의 ack(S+11)로 arm한다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  feed_through(h, hold_ground(), s + 7);
  feed_through(h, offboard_ground(), s + 9);
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];  // S+10
  ASSERT_EQ(h.edges().size(), before + 1);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  EXPECT_EQ(h.view().prep, PrepStep::kOffboardAck);
  EXPECT_FALSE(h.view().arm_sent);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before_arm = h.edges().size();
  const StepOutput arm = h.feed({offboard_ground()})[0];  // S+11
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before_arm);
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
}

TEST(OffboardAck, ConfirmOnResendDueTickWithAckArmsWithoutResend)
{
  // 확인 tick(S+10)이 재전송 주기가 찬 tick이고 그 tick에 유효 ack를 받았다. arm만 나간다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  feed_through(h, hold_ground(), s + 7);
  feed_through(h, offboard_ground(), s + 9);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput confirm = h.feed({offboard_ground()})[0];  // S+10
  ASSERT_EQ(h.edges().size(), before + 2);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before + 1);
  EXPECT_EQ(confirm.commands, std::vector<CommandKind>{CommandKind::kArm});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
}

enum class WaitingEnd : std::uint8_t
{
  kLeft,
  kCancel,
  kIdentityMismatch,
  kStampFailure,
  kRejectedAck,
};

class WaitingEndOnResendDueTick : public ::testing::TestWithParam<WaitingEnd>
{
};

TEST_P(WaitingEndOnResendDueTick, SendsNoResend)
{
  // 대기 중 재전송 주기가 찬 tick(S+10)에 끝나는 사건이 오면 그 tick의 재전송은 나가지 않는다
  // (실패 판정이 재전송보다 앞이고, 취소는 정리 진입이 지운다).
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  feed_through(h, offboard_ground(), s + 9);
  const std::size_t before = h.edges().size();
  StepOutput out;
  switch (GetParam()) {
    case WaitingEnd::kLeft:
      out = h.feed({hold_ground()})[0];
      expect_cell(
        h, "PREPARING.OFFBOARD_ACK", Event::kOffboardLeft, "CLEANUP.PREPARING_FAILURE.NONE", "-",
        {}, before);
      expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
      break;
    case WaitingEnd::kCancel:
      out = h.feed({offboard_ground()}, true)[0];
      expect_cell(
        h, "PREPARING.OFFBOARD_ACK", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
      expect_terminated_once_as(h, "CANCELED/NONE");
      break;
    case WaitingEnd::kIdentityMismatch:
      h.world.identity = IdentityCheck::kMismatch;
      out = h.feed({offboard_ground()})[0];
      expect_cell(
        h, "PREPARING.OFFBOARD_ACK", Event::kPreparingIdentityMismatch, "DONE", "ABORTED/INTERNAL",
        {}, before);
      expect_terminated_once_as(h, "ABORTED/INTERNAL");
      break;
    case WaitingEnd::kStampFailure:
      h.clock.fail = true;
      out = h.feed({offboard_ground()})[0];
      expect_cell(
        h, "PREPARING.OFFBOARD_ACK", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {},
        before);
      expect_terminated_once_as(h, "ABORTED/INTERNAL");
      EXPECT_FALSE(out.setpoint.has_value());
      break;
    case WaitingEnd::kRejectedAck:
      h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);
      out = h.feed({offboard_ground()})[0];
      expect_cell(
        h, "PREPARING.OFFBOARD_ACK", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE",
        "-", {}, before);
      expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
      break;
  }
  EXPECT_EQ(h.edges().empty() ? 0U : h.edges().back().tick, s + 10);
  EXPECT_TRUE(out.commands.empty());
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  expect_no_arm_disarm_hold(h, 0);
}

INSTANTIATE_TEST_SUITE_P(
  OffboardAck, WaitingEndOnResendDueTick,
  ::testing::Values(
    WaitingEnd::kLeft, WaitingEnd::kCancel, WaitingEnd::kIdentityMismatch,
    WaitingEnd::kStampFailure, WaitingEnd::kRejectedAck));

TEST(OffboardAck, ConfirmTickCancelOnResendDueTickSendsNothing)
{
  // 주기가 찬 확인 tick(S+10)에 유효 ack가 없고 취소가 겹친다. 재전송은 정리 진입이 지운다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  feed_through(h, hold_ground(), s + 7);
  feed_through(h, offboard_ground(), s + 9);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.feed({offboard_ground()}, true)[0];  // S+10
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardConfirmed, "PREPARING.OFFBOARD_ACK", "-", {}, before);
  expect_cell(h, "PREPARING.OFFBOARD_ACK", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_TRUE(out.commands.empty());
  expect_terminated_once_as(h, "CANCELED/NONE");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  expect_no_arm_disarm_hold(h, 0);
}

TEST(OffboardAck, ValidAckBeforeConfirmThenModeLostTimesOutWithoutResend)
{
  // 유효 ack(S+1) 뒤 OFFBOARD가 확인되지 않으면 재전송 없이 S+60에 P5의 timeout으로 끝난다(다른
  // 주체가 바꾼 모드를 다시 덮지 않는다). 1a에서는 주기마다 재전송해 DO_SET_MODE가 6회였다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_without_ack(h);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  feed_through(h, hold_ground(), s + 59);
  EXPECT_FALSE(h.runner().done());
  const std::size_t before = h.edges().size();
  h.feed({hold_ground()});  // S+60
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  expect_resends_only_at(h, s + 1, s + 60, {});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("mode_confirm_timeout: OFFBOARD not confirmed"), std::string::npos)
    << detail;
}

TEST(OffboardAck, LateAckOfEarlierSendIsReadAsValid)
{
  // 알려진 열화. S+12의 ack는 S 전송의 것이고 지연이 12 tick(0.6 s, 주기와 두 배 사이)이다. core는
  // 이것을 S+10 재전송의 ack와 가르지 못해 유효로 읽고 arm한다. PX4 queue에서 arm 앞에 S+10의
  // DO_SET_MODE 하나가 남을 수 있다(decisions.md 쟁점 12가 허용한 열화). 단정하는 것은 현재
  // 동작이지 바람직한 동작이 아니다.
  Harness h(standard_mission());
  const std::uint64_t s = reach_offboard_ack(h);
  feed_through(h, offboard_ground(), s + 11);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  const std::size_t before = h.edges().size();
  const StepOutput arm = h.feed({offboard_ground()})[0];  // S+12
  expect_cell(
    h, "PREPARING.OFFBOARD_ACK", Event::kOffboardAckAccepted, "PREPARING.ARM", "-", {}, before);
  EXPECT_EQ(arm.commands, std::vector<CommandKind>{CommandKind::kArm});
  expect_resends_only_at(h, s + 4, s + 11, {s + 10});
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
}

}  // namespace
}  // namespace idsim_mission::core::test
