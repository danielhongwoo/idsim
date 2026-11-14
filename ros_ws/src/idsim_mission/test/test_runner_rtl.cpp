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

// RTL 항목, 진입 방식(EntryPlan)의 모드 명령 갈래, RTL 실패의 Land fallback(RTL_FAILURE 정리).
// 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 9, 12, 13.
//
// S는 RTL 항목을 시작한 tick(NAV_RTL 첫 전송)이다. 시간 값은 core/config.hpp 기본값이다
// (mode_confirm_timeout 3 s = 60 tick, command_resend_period 0.5 s = 10 tick).
//
// 쟁점 9의 미정 경계 둘(RTL 확인과 mode_confirm_timeout이 같은 tick, 확인 tick에 온 거부 ack)은
// 어느 쪽으로도 단정하지 않는다. 확인 3회째 표본은 만료 전 tick에, 거부 ack는 확인 전 tick에 둔다.
// 거부 ack와 공중 DISARMED 표본의 겹침 같은 합성 ack 사례는 PX4 v1.17.0에서 재현하기 어려운 방어
// 경로라 합성 표본과 합성 ack로만 시험한다.

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "idsim_mission/core/rules.hpp"
#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

constexpr int kModeConfirmTicks = 60;  // mode_confirm_timeout 3 s
constexpr int kResendTicks = 10;       // command_resend_period 0.5 s

// 공중 ARMED Hold에서 [RTL]을 시작해 S tick까지 돌린다. S를 돌려준다.
std::uint64_t start_rtl(Harness & h)
{
  h.start_in_air();
  const std::uint64_t s = h.tick_no;
  h.tick();
  EXPECT_EQ(h.view().stage, Stage::kItem);
  const StepOutput * const out = output_of_tick(h, s);
  if (out != nullptr) {
    EXPECT_EQ(out->commands, std::vector<CommandKind>{CommandKind::kNavRtl});
  }
  return s;
}

// 다음 tick이 target이 될 때까지 돌린다(끝나면 멈춘다).
void run_to_tick(Harness & h, std::uint64_t target)
{
  while (h.tick_no < target && !h.runner().done()) {
    h.tick();
  }
}

// [TAKEOFF, LOITER, RTL]에서 RTL 항목이 시작될 때까지. S를 돌려준다.
std::uint64_t drive_to_rtl(Harness & h)
{
  h.drive_to_land();
  EXPECT_EQ(h.runner().mission().items[h.view().item_index].type, item_type::kRtl);
  return h.tick_no - 1;
}

// RTL 실패의 정리 동안 tick마다: Hold 실패 표시가 없고, feedback은 WAITING_MODE와 RTL이다.
void expect_rtl_failure_tick(const Harness & h, const StepOutput & out)
{
  EXPECT_FALSE(h.view().hold_failed);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  if (out.feedback.has_value()) {
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kWaitingMode);
    EXPECT_EQ(out.feedback->item_type, item_type::kRtl);
  }
}

bool starts_with(const std::string & text, const std::string & prefix)
{
  return text.rfind(prefix, 0) == 0;
}

// ---- 진입 방식과 type별 값 ----

TEST(EntryPlan, DerivedFromFirstItemType)
{
  EXPECT_EQ(entry_plan(item_type::kTakeoff), EntryPlan::kGroundArm);
  EXPECT_EQ(entry_plan(item_type::kLand), EntryPlan::kModeCommand);
  EXPECT_EQ(entry_plan(item_type::kRtl), EntryPlan::kModeCommand);
  EXPECT_EQ(entry_plan(item_type::kLoiter), EntryPlan::kAirOffboard);
  EXPECT_FALSE(entry_plan(item_type::kGoTo).has_value());
  EXPECT_FALSE(entry_plan(item_type::kTrackEntity).has_value());
}

TEST(EntryPlan, ModeItemSpecPerType)
{
  const std::optional<ModeItemSpec> land = mode_item_spec(item_type::kLand);
  ASSERT_TRUE(land.has_value());
  EXPECT_EQ(land->command, CommandKind::kNavLand);
  EXPECT_EQ(land->mode, NavMode::kLand);
  EXPECT_FALSE(land->land_fallback);
  const std::optional<ModeItemSpec> rtl = mode_item_spec(item_type::kRtl);
  ASSERT_TRUE(rtl.has_value());
  EXPECT_EQ(rtl->command, CommandKind::kNavRtl);
  EXPECT_EQ(rtl->mode, NavMode::kRtl);
  EXPECT_EQ(std::string(rtl->mode_name), "AUTO_RTL");
  EXPECT_EQ(std::string(rtl->command_name), "NAV_RETURN_TO_LAUNCH");
  EXPECT_TRUE(rtl->land_fallback);
  for (const std::uint8_t type : {item_type::kTakeoff, item_type::kLoiter, item_type::kGoTo}) {
    EXPECT_FALSE(mode_item_spec(type).has_value()) << int{type};
  }
}

TEST(EntryPlan, RtlPreconditionIsSameAsLand)
{
  // [RTL]의 시작 조건은 [LAND]와 같다(landed가 아니고 ARMED). 지상 DISARMED이면
  // PRECONDITION_FAILED.
  Harness h(rtl_only_mission());
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kPreconditionFailed);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "RTL needs not landed and ARMED (landed=true, arming=DISARMED)");
  EXPECT_TRUE(h.commands().empty());
}

TEST(EntryPlan, RtlWaitsForEkfGate)
{
  Harness h(rtl_only_mission());
  h.start_in_air();
  h.world.ekf_ready = false;
  for (int i = 0; i < 5; ++i) {
    const StepOutput out = h.tick();
    EXPECT_TRUE(out.commands.empty());
  }
  EXPECT_EQ(h.view().stage, Stage::kPreparing);
  h.world.ekf_ready = true;
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(h, "PREPARING.WAIT_READY", Event::kReadyModeItem, "ITEM.RTL", "-", {}, before);
}

// ---- RTL 항목 ----

TEST(Rtl, RtlOnlySucceeds)
{
  // T1. 공중 ARMED Hold에서 [RTL]. S+3에 AUTO_RTL 확인, 착지 뒤 DISARMED 3회로 성공.
  Harness h(rtl_only_mission());
  const std::uint64_t s = start_rtl(h);
  expect_cell(h, "PREPARING.WAIT_READY", Event::kReadyModeItem, "ITEM.RTL", "-");
  run_to_tick(h, s + 3);
  EXPECT_FALSE(h.view().land_confirmed);
  h.tick();  // S+3
  EXPECT_TRUE(h.view().land_confirmed);
  EXPECT_FALSE(h.view().pending_active);
  for (int i = 0; i < 2 * kResendTicks; ++i) {
    h.tick();
  }
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  h.world.nav = NavMode::kHold;
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_cell(h, "ITEM.RTL", Event::kModeItemDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
  EXPECT_EQ(termination_or_empty(h).items_completed, 1U);
  EXPECT_EQ(h.count_command(CommandKind::kNavRtl), 1);  // 확인 뒤 재전송 없음
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
    if (out.feedback.has_value()) {
      EXPECT_EQ(out.feedback->phase, FeedbackPhase::kWaitingMode);
      EXPECT_EQ(out.feedback->item_type, item_type::kRtl);
    }
  }
}

TEST(Rtl, TakeoffLoiterRtlStopsPublishingAtFirstAutoRtl)
{
  // T2. LOITER 뒤 RTL. S에는 setpoint가 있고 S+1(첫 AUTO_RTL 표본)부터 없다.
  Harness h(takeoff_loiter_rtl_mission());
  const std::uint64_t s = drive_to_rtl(h);
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.RTL", "-");
  const StepOutput * const at_s = output_of_tick(h, s);
  ASSERT_NE(at_s, nullptr);
  EXPECT_EQ(at_s->commands, std::vector<CommandKind>{CommandKind::kNavRtl});
  EXPECT_TRUE(at_s->setpoint.has_value());
  const StepOutput first_rtl = h.tick();  // S+1
  EXPECT_FALSE(first_rtl.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  h.world.nav = NavMode::kOffboard;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
  EXPECT_EQ(termination_or_empty(h).items_completed, 3U);
  for (std::uint64_t tick = s + 1; tick <= h.outputs().size(); ++tick) {
    EXPECT_FALSE(output_of_tick(h, tick)->setpoint.has_value()) << "tick " << tick;
  }
}

TEST(Rtl, TakeoffThenRtl)
{
  // T3. TAKEOFF 도달 tick에 RTL을 시작한다.
  MissionSpec m;
  m.mission_id = "rtl2";
  m.items = {takeoff_item(), rtl_item()};
  Harness h(m);
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 100));
  const TransitionEdge * const edge =
    expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, "ITEM.RTL", "-", {}, before);
  ASSERT_NE(edge, nullptr);
  const StepOutput * const out = output_of_tick(h, edge->tick);
  ASSERT_NE(out, nullptr);
  EXPECT_EQ(out->commands, std::vector<CommandKind>{CommandKind::kNavRtl});
  EXPECT_TRUE(out->setpoint.has_value());
}

TEST(Rtl, RejectedInAirFallsBackToLand)
{
  // T4. RTL이 거부되면 기체는 OFFBOARD로 남는다. Hold 없이 Land 경로, 발행은 AUTO_LAND 관측까지.
  Harness h(takeoff_loiter_rtl_mission());
  h.rtl_response = RtlResponse::kReject;
  const std::uint64_t s = drive_to_rtl(h);
  const std::size_t before = h.edges().size();
  const StepOutput reject = h.tick();  // S+1
  expect_cell(h, "ITEM.RTL", Event::kModeItemRejected, "CLEANUP.RTL_FAILURE.NONE", "-", {}, before);
  expect_cell(
    h, "CLEANUP.RTL_FAILURE.NONE", Event::kEnterAir, "CLEANUP.RTL_FAILURE.AIR_LAND", "-", {},
    before);
  EXPECT_EQ(reject.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  EXPECT_TRUE(reject.setpoint.has_value());
  expect_rtl_failure_tick(h, reject);
  const std::size_t land_before = h.edges().size();
  const StepOutput observed = h.tick();  // S+2: 첫 AUTO_LAND 표본
  EXPECT_FALSE(observed.setpoint.has_value());
  expect_cell(
    h, "CLEANUP.RTL_FAILURE.AIR_LAND", Event::kLandPathModeObserved, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, land_before);
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(
    detail,
    "item 2 (RTL): NAV_RETURN_TO_LAUNCH rejected: TEMPORARILY_REJECTED; cleanup: RTL not "
    "confirmed; Land sent, AUTO_LAND observed");
  EXPECT_NE(detail.find("; cleanup: RTL not confirmed"), std::string::npos);
  EXPECT_NE(detail.find("; Land sent, AUTO_LAND observed"), std::string::npos);
  EXPECT_FALSE(h.view().hold_failed);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  for (std::uint64_t tick = 1; tick <= s; ++tick) {
    EXPECT_FALSE(has_command(*output_of_tick(h, tick), CommandKind::kNavLand)) << tick;
  }
}

TEST(Rtl, RejectionRangeIsEveryRejectingResult)
{
  // T4 보조. is_rejection 전부가 Land fallback이고 IN_PROGRESS는 정리로 가지 않는다(합성 ack).
  for (const AckResult result :
       {AckResult::kTemporarilyRejected, AckResult::kDenied, AckResult::kUnsupported,
        AckResult::kFailed, AckResult::kCancelled, AckResult::kOther}) {
    Harness h(takeoff_loiter_rtl_mission());
    h.rtl_response = RtlResponse::kIgnore;
    drive_to_rtl(h);
    h.push_ack(AckCommand::kNavRtl, result);
    h.tick();
    EXPECT_EQ(h.view().stage, Stage::kCleanup) << ack_result_name(result);
    EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kRtlFailure) << ack_result_name(result);
    EXPECT_EQ(h.view().branch, Branch::kAirLand) << ack_result_name(result);
    EXPECT_FALSE(h.view().hold_failed);
  }
  Harness h(takeoff_loiter_rtl_mission());
  h.rtl_response = RtlResponse::kIgnore;
  drive_to_rtl(h);
  h.push_ack(AckCommand::kNavRtl, AckResult::kInProgress);
  h.tick();
  EXPECT_EQ(h.view().stage, Stage::kItem);
  // 다른 명령 묶음의 거부 ack는 보지 않는다.
  h.push_ack(AckCommand::kNavLand, AckResult::kDenied);
  h.tick();
  EXPECT_EQ(h.view().stage, Stage::kItem);
}

TEST(Rtl, ModeConfirmTimeoutFallsBackToLand)
{
  // T5. 기체가 NAV_RTL에 반응하지 않는다. S+59까지 10 tick마다 재전송, S+60에 Land fallback.
  Harness h(rtl_only_mission());
  h.auto_px4 = false;
  const std::uint64_t s = start_rtl(h);
  run_to_tick(h, s + kModeConfirmTicks);
  EXPECT_FALSE(h.runner().done());
  EXPECT_EQ(h.view().stage, Stage::kItem);
  EXPECT_EQ(h.count_command(CommandKind::kNavRtl), kModeConfirmTicks / kResendTicks);
  for (std::uint64_t tick = s + 1; tick < s + kModeConfirmTicks; ++tick) {
    const bool resend = (tick - s) % kResendTicks == 0;
    EXPECT_EQ(has_command(*output_of_tick(h, tick), CommandKind::kNavRtl), resend) << tick;
  }
  const std::size_t before = h.edges().size();
  const StepOutput timeout = h.tick();  // S+60
  expect_cell(
    h, "ITEM.RTL", Event::kModeItemModeTimeout, "CLEANUP.RTL_FAILURE.NONE", "-", {}, before);
  EXPECT_EQ(timeout.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  expect_rtl_failure_tick(h, timeout);
  const std::size_t land_before = h.edges().size();
  for (int i = 0; i < kModeConfirmTicks - 1; ++i) {
    expect_rtl_failure_tick(h, h.tick());
  }
  EXPECT_FALSE(h.runner().done());
  h.tick();  // S+120
  expect_cell(
    h, "CLEANUP.RTL_FAILURE.AIR_LAND", Event::kLandPathTimeout, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, land_before);
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 0 (RTL): mode_confirm_timeout: AUTO_RTL not confirmed; cleanup: RTL not confirmed; "
    "Land sent, AUTO_LAND not confirmed");
  EXPECT_FALSE(h.view().hold_failed);
}

TEST(Rtl, GroundBranchThenAirReentryIsLandPath)
{
  // 지상 분기를 거쳐 공중으로 돌아가면 다시 Land 경로다. 정리 결과의 문구 전체를 단정한다.
  Harness h(rtl_only_mission());
  h.rtl_response = RtlResponse::kReject;
  start_rtl(h);
  h.auto_px4 = false;
  h.tick();  // S+1: 거부 ack, AIR_LAND
  ASSERT_EQ(h.view().branch, Branch::kAirLand);
  h.world.landed = true;
  StepOutput out = h.tick();
  ASSERT_EQ(h.view().branch, Branch::kGround);
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  h.world.landed = false;
  const std::size_t before = h.edges().size();
  out = h.tick();
  expect_cell(
    h, "CLEANUP.RTL_FAILURE.GROUND", Event::kEnterAir, "CLEANUP.RTL_FAILURE.AIR_LAND", "-", {},
    before);
  EXPECT_EQ(out.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  expect_rtl_failure_tick(h, out);
  h.world.nav = NavMode::kLand;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 0 (RTL): NAV_RETURN_TO_LAUNCH rejected: TEMPORARILY_REJECTED; cleanup: RTL not "
    "confirmed; air re-entered after ground branch; Land sent, AUTO_LAND observed");
  EXPECT_FALSE(h.view().hold_failed);
}

TEST(Rtl, LeavingAutoRtlAfterConfirm)
{
  // T6. 확인 뒤 ARMED인 채 AUTO_RTL 이탈. 명령 없이 끝낸다.
  for (const bool failsafe : {false, true}) {
    Harness h(rtl_only_mission());
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + 4);
    ASSERT_TRUE(h.view().land_confirmed);
    h.auto_px4 = false;
    Sample left = armed(NavMode::kHold);
    left.failsafe = failsafe;
    const std::size_t before = h.edges().size();
    const std::vector<StepOutput> outs = h.feed({left});
    EXPECT_TRUE(outs.back().commands.empty());
    const char * reason = failsafe ? "ABORTED/FAILSAFE" : "ABORTED/EXTERNAL_MODE_CHANGE";
    expect_cell(h, "ITEM.RTL", Event::kModeItemLeftMode, "DONE", reason, {}, before);
    expect_terminated_once_as(h, reason);
    EXPECT_EQ(termination_or_empty(h).detail, "item 0 (RTL): left AUTO_RTL while ARMED");
  }
}

TEST(Rtl, FlappingBeforeConfirmIsNotDeparture)
{
  // T7. 확인 전의 흔들림은 계수만 0으로 되돌린다.
  Harness h(rtl_only_mission());
  h.auto_px4 = false;
  start_rtl(h);
  const std::vector<StepOutput> outs = h.feed(
    {armed(NavMode::kRtl), armed(NavMode::kRtl), armed(NavMode::kHold), armed(NavMode::kRtl),
     armed(NavMode::kRtl)});
  for (const StepOutput & out : outs) {
    EXPECT_FALSE(out.termination.has_value());
  }
  EXPECT_FALSE(h.view().land_confirmed);
  h.feed({armed(NavMode::kRtl)});
  EXPECT_TRUE(h.view().land_confirmed);
  EXPECT_FALSE(h.runner().done());
}

TEST(Rtl, CompletionIgnoresNav)
{
  // T8. RTL 착지 뒤 disarm 때 nav_state가 사용자 의도로 돌아가도 이탈이 아니라 완료다.
  Harness h(rtl_only_mission());
  const std::uint64_t s = start_rtl(h);
  run_to_tick(h, s + 4);
  ASSERT_TRUE(h.view().land_confirmed);
  h.auto_px4 = false;
  h.feed(
    {disarmed(true, NavMode::kOffboard), disarmed(true, NavMode::kOffboard),
     disarmed(true, NavMode::kOffboard)});
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(Rtl, ImmediateEndings)
{
  // T9. 공중 DISARMED, 식별 불일치, 상태 끊김, Px4Timestamp 실패.
  {
    Harness h(rtl_only_mission());
    start_rtl(h);
    h.auto_px4 = false;
    const std::size_t before = h.edges().size();
    h.feed({disarmed(false, NavMode::kRtl)});
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemDisarmedInAir, "DONE", "ABORTED/FAILSAFE", {}, before);
    expect_terminated_once_as(h, "ABORTED/FAILSAFE");
    EXPECT_EQ(termination_or_empty(h).detail, "item 0 (RTL): disarmed while not landed");
  }
  {
    Harness h(rtl_only_mission());
    start_rtl(h);
    h.world.identity = IdentityCheck::kMismatch;
    const std::size_t before = h.edges().size();
    h.tick();
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemIdentityMismatch, "DONE", "ABORTED/INTERNAL", {}, before);
    expect_terminated_once_as(h, "ABORTED/INTERNAL");
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "item 0 (RTL): vehicle_status identity mismatch: expected sysid 2 component 1, got sysid 3 "
      "component 1");
  }
  {
    Harness h(rtl_only_mission());
    start_rtl(h);
    h.auto_samples = false;
    const std::size_t before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_cell(h, "ITEM.RTL", Event::kModeItemLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
    expect_terminated_once_as(h, "ABORTED/LINK_LOST");
    EXPECT_EQ(termination_or_empty(h).detail, "item 0 (RTL): vehicle_status lost");
  }
  {
    // 재전송 tick(S+10)에 Px4Timestamp를 만들 수 없으면 명령을 버리고 끝낸다.
    Harness h(rtl_only_mission());
    h.rtl_response = RtlResponse::kIgnore;
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + kResendTicks);
    h.clock.fail = true;
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();
    EXPECT_TRUE(out.commands.empty());
    expect_cell(h, "ITEM.RTL", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {}, before);
    expect_terminated_once_as(h, "ABORTED/INTERNAL");
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "Px4Timestamp unavailable; vehicle state unknown, may remain armed on ground");
  }
}

TEST(Rtl, ItemTimeoutWordingWithoutFallback)
{
  // T10. 항목 timeout(2 s = 40 tick)은 명령 없이 ITEM_TIMEOUT. Land fallback을 거치지 않는다.
  struct Case
  {
    const char * name;
    RtlResponse response;
    bool accepted_ack;
    bool observed_once;
    bool landed_at_timeout;
    const char * tail;
  };
  const std::vector<Case> cases = {
    {"confirmed", RtlResponse::kAccept, false, false, false,
     "; AUTO_RTL was confirmed, PX4 continues RTL"},
    {"confirmed_landed", RtlResponse::kAccept, false, false, true,
     "; AUTO_RTL was confirmed, PX4 continues RTL; landed and still ARMED"},
    {"observed", RtlResponse::kIgnore, false, true, false, "; AUTO_RTL observed but not confirmed"},
    {"accepted", RtlResponse::kIgnore, true, false, false,
     "; NAV_RETURN_TO_LAUNCH accepted but AUTO_RTL not observed"},
    {"nothing", RtlResponse::kIgnore, false, false, false,
     "; AUTO_RTL not observed (NAV_RETURN_TO_LAUNCH may not have arrived, vehicle may stay in its "
     "mode)"},
  };
  for (const Case & c : cases) {
    SCOPED_TRACE(c.name);
    Harness h(rtl_only_mission(2));
    h.rtl_response = c.response;
    const std::uint64_t s = start_rtl(h);
    if (c.accepted_ack) {
      h.push_ack(AckCommand::kNavRtl, AckResult::kAccepted);
    }
    if (c.observed_once) {
      h.world.nav = NavMode::kRtl;
      h.tick();
      h.world.nav = NavMode::kHold;
    }
    run_to_tick(h, s + 40);
    if (c.landed_at_timeout) {
      h.world.landed = true;
    }
    EXPECT_FALSE(h.runner().done());
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();  // S+40
    EXPECT_TRUE(out.commands.empty());
    expect_cell(h, "ITEM.RTL", Event::kModeItemTimeout, "DONE", "ABORTED/ITEM_TIMEOUT", {}, before);
    expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
    EXPECT_EQ(termination_or_empty(h).detail, std::string("item 0 (RTL) timeout") + c.tail);
    EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  }
}

TEST(Rtl, FallbackDisarmAfterLandedArmed)
{
  // T11. 확인 뒤 landed이고 ARMED인 채 5 s면 강제가 아닌 disarm 1회, 그 뒤 재전송. 그 단계의 거부
  // ack(DISARM, NAV_RTL)는 정리로 가지 않는다.
  Harness h(rtl_only_mission());
  const std::uint64_t s = start_rtl(h);
  run_to_tick(h, s + 4);
  ASSERT_TRUE(h.view().land_confirmed);
  h.auto_px4 = false;
  h.world.landed = true;
  const std::uint64_t landed_tick = h.tick_no;
  run_to_tick(h, landed_tick + 100);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  const StepOutput first = h.tick();
  EXPECT_EQ(first.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  h.tick();
  h.push_ack(AckCommand::kNavRtl, AckResult::kTemporarilyRejected);
  h.tick();
  EXPECT_EQ(h.view().stage, Stage::kItem);
  run_to_tick(h, landed_tick + 100 + kResendTicks);
  const StepOutput resend = h.tick();
  EXPECT_EQ(resend.commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_EQ(h.view().stage, Stage::kItem);
}

TEST(Rtl, SameTickOrder)
{
  // T12 (b), (c). 확인과 만료, 확인 tick의 거부 ack는 미정이라 단정하지 않는다(머리 주석).
  {
    // (b) 거부 ack와 mode_confirm_timeout이 같은 tick: 거부가 이긴다(detail은 거부 문구).
    Harness h(rtl_only_mission());
    h.rtl_response = RtlResponse::kIgnore;
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + kModeConfirmTicks);
    h.push_ack(AckCommand::kNavRtl, AckResult::kTemporarilyRejected);
    const std::size_t before = h.edges().size();
    h.tick();
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemRejected, "CLEANUP.RTL_FAILURE.NONE", "-", {}, before);
    h.world.nav = NavMode::kLand;
    h.tick();
    expect_terminated_once(h, Status::kAborted, Reason::kModeSwitchFailed);
    EXPECT_TRUE(starts_with(
      termination_or_empty(h).detail,
      "item 0 (RTL): NAV_RETURN_TO_LAUNCH rejected: TEMPORARILY_REJECTED; cleanup: RTL not "
      "confirmed"));
  }
  {
    // (c) 거부 ack와 공중 DISARMED 표본이 같은 tick: 공중 DISARMED가 이긴다.
    Harness h(rtl_only_mission());
    h.auto_px4 = false;
    start_rtl(h);
    h.push_ack(AckCommand::kNavRtl, AckResult::kTemporarilyRejected);
    const std::size_t before = h.edges().size();
    h.feed({disarmed(false, NavMode::kHold)});
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemDisarmedInAir, "DONE", "ABORTED/FAILSAFE", {}, before);
    expect_terminated_once_as(h, "ABORTED/FAILSAFE");
    EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
  }
}

TEST(Rtl, CancelSendsHold)
{
  // T15. [RTL] 확인 뒤 취소는 1a 취소 그대로 Hold를 보낸다.
  Harness h(rtl_only_mission());
  const std::uint64_t s = start_rtl(h);
  run_to_tick(h, s + 4);
  ASSERT_TRUE(h.view().land_confirmed);
  const std::size_t before = h.edges().size();
  const StepOutput cancel = h.tick(true);
  expect_cell(h, "ITEM.RTL", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  expect_cell(h, "CLEANUP.CANCEL.NONE", Event::kEnterAir, "CLEANUP.CANCEL.AIR", "-", {}, before);
  EXPECT_EQ(cancel.commands, std::vector<CommandKind>{CommandKind::kSetModeHold});
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
}

TEST(Rtl, CancelOverlaps)
{
  // T16. 정리로 들어가는 사건과 같은 tick의 취소는 무시한다(R12, R13). 바로 끝내는 사건의 대표
  // (R14 실패, R15 성공)는 Hold와 disarm을 그 tick과 그 뒤에 보내지 않는다.
  {
    Harness h(rtl_only_mission());
    h.rtl_response = RtlResponse::kReject;
    start_rtl(h);
    const std::size_t before = h.edges().size();
    h.tick(true);  // S+1: 거부 ack
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemRejected, "CLEANUP.RTL_FAILURE.NONE", "-", {Event::kCancel},
      before);
    EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kRtlFailure);
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  }
  {
    Harness h(rtl_only_mission());
    h.auto_px4 = false;
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + kModeConfirmTicks);
    const std::size_t before = h.edges().size();
    h.tick(true);  // S+60
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemModeTimeout, "CLEANUP.RTL_FAILURE.NONE", "-", {Event::kCancel},
      before);
    EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kRtlFailure);
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  }
  {
    Harness h(rtl_only_mission());
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + 4);
    h.auto_px4 = false;
    const std::size_t before = h.edges().size();
    const std::vector<StepOutput> outs = h.feed({armed(NavMode::kHold)}, true);
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemLeftMode, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
      {Event::kCancel}, before);
    EXPECT_TRUE(outs.back().commands.empty());
    expect_terminated_once_as(h, "ABORTED/EXTERNAL_MODE_CHANGE");
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
    EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  }
  {
    Harness h(rtl_only_mission());
    const std::uint64_t s = start_rtl(h);
    run_to_tick(h, s + 4);
    h.auto_px4 = false;
    h.feed({disarmed(true, NavMode::kRtl), disarmed(true, NavMode::kRtl)});
    const std::size_t before = h.edges().size();
    const std::vector<StepOutput> outs = h.feed({disarmed(true, NavMode::kRtl)}, true);
    expect_cell(
      h, "ITEM.RTL", Event::kModeItemDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {Event::kCancel},
      before);
    EXPECT_TRUE(outs.back().commands.empty());
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
    EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  }
}

// ---- LAND는 1a 그대로 ----

TEST(LandUnchanged, RejectedAckDoesNotEndLand)
{
  // T13. [LAND]의 NAV_LAND 거부 ack는 보지 않는다. 재전송을 이어 가고 S+60에 MODE_SWITCH_FAILED.
  Harness h(land_only_mission());
  h.start_in_air();
  h.auto_px4 = false;
  const std::uint64_t s = h.tick_no;
  h.tick();
  h.push_ack(AckCommand::kNavLand, AckResult::kTemporarilyRejected);
  h.tick();  // S+1
  EXPECT_EQ(h.view().stage, Stage::kItem);
  run_to_tick(h, s + kModeConfirmTicks);
  EXPECT_FALSE(h.runner().done());
  const std::size_t before = h.edges().size();
  h.tick();  // S+60
  expect_cell(
    h, "ITEM.LAND", Event::kModeItemModeTimeout, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
  for (const CommandKind kind : h.commands()) {
    EXPECT_EQ(kind, CommandKind::kNavLand);
  }
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), kModeConfirmTicks / kResendTicks);
}

TEST(LandUnchanged, WordingIsByteIdenticalTo1a)
{
  // T14. LAND의 문구는 1a 문자열 그대로다.
  {
    Harness h(land_only_mission());
    h.tick();
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "LAND needs not landed and ARMED (landed=true, arming=DISARMED)");
  }
  {
    Harness h(land_only_mission());
    h.start_in_air();
    ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 10));
    h.auto_px4 = false;
    h.feed({armed(NavMode::kHold)});
    EXPECT_EQ(termination_or_empty(h).detail, "item 0 (LAND): left AUTO_LAND while ARMED");
  }
  {
    Harness h(land_only_mission());
    h.start_in_air();
    h.auto_px4 = false;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "item 0 (LAND): mode_confirm_timeout: AUTO_LAND not confirmed");
  }
  const std::vector<std::string> tails = {
    "; AUTO_LAND was confirmed, PX4 continues landing",
    "; AUTO_LAND observed but not confirmed",
    "; NAV_LAND accepted but AUTO_LAND not observed",
    "; AUTO_LAND not observed (NAV_LAND may not have arrived, vehicle may stay in its mode)",
  };
  for (std::size_t i = 0; i < tails.size(); ++i) {
    SCOPED_TRACE(i);
    Harness h(land_only_mission(2));
    h.start_in_air();
    h.auto_px4 = i == 0;
    h.tick();
    if (i == 1) {
      h.feed({armed(NavMode::kLand), armed(NavMode::kHold)});
    } else if (i == 2) {
      h.push_ack(AckCommand::kNavLand, AckResult::kAccepted);
    }
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    EXPECT_EQ(termination_or_empty(h).detail, "item 0 (LAND) timeout" + tails[i]);
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
