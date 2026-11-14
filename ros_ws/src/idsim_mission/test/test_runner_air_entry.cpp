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

// 공중 Offboard 진입(첫 항목 LOITER. docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 7).
//
// - 사례 이름의 A1-A27은 B9 S4 칸 명세 7.1의 사례 번호다. 칸은 transition_cells.tsv의
//   PREPARING.AIR_SIGNAL, PREPARING.AIR_OFFBOARD, PREPARING.AIR_OFFBOARD_SEEN 행과, 공중 진입이
//   새로 닿는 기존 정리 칸이다.
// - 기호: P는 발행을 시작한 tick(READY_AIR_OFFBOARD), S는 DO_SET_MODE(OFFBOARD)를 처음 보낸
//   tick(SIGNAL_CONFIRMED)이다. 하네스 기본값에서 P = 1, S = P + 10이다(발행 10회가 P..P+9의
//   finalize에서 찬다). offboard_signal_timeout은 P+40, mode_confirm_timeout은 S+60이다.
// - 기본 미션은 [LOITER 5 s, timeout 10 s]이고 기체는 start_in_air()(ARMED, landed false, z -5,
//   AUTO_LOITER, 의도 AUTO_LOITER, failsafe false, heading 0.25)에서 시작한다.
// - 신호 없음 고정은 매 tick 전에 world.signal_lost = true로 한다(가짜 PX4는 setpoint가 나가면
//   신호를 켠다).
// - 이 goal은 arm을 보내지 않는다. 첫 항목 시작 전의 모든 tick에 ARM이 없고(view().arm_sent
//   false), 지상 ARMED 갈래(A23(e), A26) 말고는 DISARM도 없다.

#include <gtest/gtest.h>

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

constexpr std::uint64_t kP = 1;                  // 발행 시작 tick(하네스 기본값)
constexpr std::uint64_t kSignalTicks = 40;       // offboard_signal_timeout 2 s
constexpr std::uint64_t kModeConfirmTicks = 60;  // mode_confirm_timeout 3 s
constexpr std::uint64_t kResendTicks = 10;       // command_resend_period 0.5 s
constexpr std::uint64_t kLoiterTicks = 100;      // loiter_item() duration 5 s

const char * const kLabel = "preparing (air offboard entry)";

const std::vector<CommandKind> kNoCommands = {};
const std::vector<CommandKind> kHoldOnly = {CommandKind::kSetModeHold};
const std::vector<CommandKind> kOffboardOnly = {CommandKind::kSetModeOffboard};
const std::vector<CommandKind> kDisarmOnly = {CommandKind::kDisarm};

bool starts_with(const std::string & text, const std::string & prefix)
{
  return text.rfind(prefix, 0) == 0;
}

bool ends_with(const std::string & text, const std::string & suffix)
{
  return text.size() >= suffix.size() &&
         text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// 이번 tick 전에 신호 없음을 고정하고 한 tick.
StepOutput tick_without_signal(Harness & h, bool cancel = false)
{
  h.world.signal_lost = true;
  return h.tick(cancel);
}

// start_in_air() 뒤 P tick을 돌리고 READY_AIR_OFFBOARD 칸을 단정한다. P를 돌려준다.
std::uint64_t start_air(Harness & h)
{
  h.start_in_air();
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "PREPARING.WAIT_READY", Event::kReadyAirOffboard, "PREPARING.AIR_SIGNAL", "-", {}, before);
  EXPECT_EQ(h.view().prep, PrepStep::kAirSignal);
  EXPECT_EQ(h.tick_no - 1, kP);
  return kP;
}

// 지금까지의 출력에서 준비 단계(phase PREPARING)의 feedback은 item 0의 LOITER이고, ARM은 없다.
// disarm_allowed가 false이면 DISARM도 없다.
void expect_air_invariants(const Harness & h, bool disarm_allowed = false)
{
  EXPECT_FALSE(h.view().arm_sent);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  if (!disarm_allowed) {
    EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  }
  for (std::size_t i = 0; i < h.outputs().size(); ++i) {
    const StepOutput & out = h.outputs()[i];
    if (!out.feedback.has_value() || out.feedback->phase != FeedbackPhase::kPreparing) {
      continue;
    }
    EXPECT_EQ(out.feedback->item_index, 0U) << "tick " << i + 1;
    EXPECT_EQ(out.feedback->item_type, item_type::kLoiter) << "tick " << i + 1;
  }
}

// 준비 단계에서 끝난 goal: 완료 0, index 0(결과 표 4절).
void expect_prep_end(Harness & h, const std::string & reason)
{
  const Termination term = termination_or_empty(h);
  EXPECT_EQ(term.items_completed, 0U) << term.detail;
  EXPECT_EQ(term.last_item_index, 0U) << term.detail;
  expect_air_invariants(h, true);
  expect_terminated_once_as(h, reason);
}

const StepOutput & out_at(const Harness & h, std::uint64_t tick)
{
  static const StepOutput empty;
  const StepOutput * const out = output_of_tick(h, tick);
  return out != nullptr ? *out : empty;
}

// tick을 이번 tick 번호(h.tick_no)가 target이 될 때까지 돌린다(target 앞 tick까지). 중간에 끝나면
// 실패한다.
void tick_until(Harness & h, std::uint64_t target)
{
  while (h.tick_no < target) {
    h.tick();
    ASSERT_FALSE(h.runner().done())
      << "ended at tick " << h.tick_no - 1 << ": " << termination_or_empty(h).detail;
  }
}

void tick_until_without_signal(Harness & h, std::uint64_t target)
{
  while (h.tick_no < target) {
    tick_without_signal(h);
    ASSERT_FALSE(h.runner().done())
      << "ended at tick " << h.tick_no - 1 << ": " << termination_or_empty(h).detail;
  }
}

// ---- A1 정상 ----

TEST(AirEntry, A1_NormalEntryToLoiterAndMissionEnd)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  const StepOutput & first = out_at(h, p);
  ASSERT_TRUE(first.setpoint.has_value());
  EXPECT_EQ(first.setpoint->kind, SetpointKind::kTarget);
  EXPECT_DOUBLE_EQ(first.setpoint->x, 1.0);
  EXPECT_DOUBLE_EQ(first.setpoint->y, 2.0);
  EXPECT_DOUBLE_EQ(first.setpoint->z, -5.0);
  EXPECT_DOUBLE_EQ(first.setpoint->yaw_ned, 0.25);
  EXPECT_FALSE(first.setpoint->velocity_valid);
  EXPECT_TRUE(first.commands.empty());
  const std::uint64_t s = p + 10;
  for (std::uint64_t k = p + 1; k < s; ++k) {
    const StepOutput out = h.tick();
    EXPECT_TRUE(out.commands.empty()) << "tick " << k;
    ASSERT_TRUE(out.setpoint.has_value()) << "tick " << k;
    EXPECT_DOUBLE_EQ(out.setpoint->z, -5.0);
    EXPECT_EQ(h.view().prep, PrepStep::kAirSignal);
  }
  std::size_t before = h.edges().size();
  EXPECT_EQ(h.tick().commands, kOffboardOnly);
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kSignalConfirmed, "PREPARING.AIR_OFFBOARD", "-", {}, before);
  before = h.edges().size();
  EXPECT_TRUE(h.tick().commands.empty());  // S+1
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
    {}, before);
  EXPECT_TRUE(h.tick().commands.empty());  // S+2
  EXPECT_EQ(h.view().prep, PrepStep::kAirOffboardSeen);
  before = h.edges().size();
  const StepOutput confirm = h.tick();  // S+3
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.LOITER", "-", {}, before);
  EXPECT_TRUE(confirm.commands.empty());
  ASSERT_TRUE(confirm.setpoint.has_value());
  EXPECT_DOUBLE_EQ(confirm.setpoint->z, -5.0);
  ASSERT_TRUE(confirm.feedback.has_value());
  EXPECT_EQ(confirm.feedback->phase, FeedbackPhase::kExecuting);
  tick_until(h, s + 3 + kLoiterTicks);
  EXPECT_EQ(h.tick().commands, kHoldOnly);  // S+103: LOITER 완료, 종료 단계
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, s + 106);
  EXPECT_EQ(termination_or_empty(h).detail, "");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 1);
  expect_air_invariants(h);
  expect_terminated_once_as(h, "SUCCEEDED/NONE");
}

// ---- A2 다른 미션 ----

TEST(AirEntry, A2a_LoiterThenLand)
{
  Harness h(air_loiter_land_mission());
  h.start_in_air();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 400));
  EXPECT_EQ(out_at(h, h.tick_no - 1).commands, std::vector<CommandKind>{CommandKind::kNavLand});
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 10));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_FALSE(h.view().arm_sent);
  expect_terminated_once_as(h, "SUCCEEDED/NONE");
}

TEST(AirEntry, A2b_LoiterThenRtl)
{
  Harness h(air_loiter_rtl_mission());
  h.start_in_air();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 400));
  EXPECT_EQ(out_at(h, h.tick_no - 1).commands, std::vector<CommandKind>{CommandKind::kNavRtl});
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 10));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_FALSE(h.view().arm_sent);
  expect_terminated_once_as(h, "SUCCEEDED/NONE");
}

TEST(AirEntry, A2c_TwoLoiters)
{
  MissionSpec m;
  m.mission_id = "air4";
  m.items = {loiter_item(), loiter_item()};
  Harness h(m);
  h.start_in_air();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 400));
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 200));
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kMissionEnd);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  expect_terminated_once_as(h, "SUCCEEDED/NONE");
}

// ---- A3 시작 조건 ----

struct PreconditionCase
{
  const char * name;
  bool landed;
  Arming arming;
  NavMode nav;
  NavMode intention;
  bool failsafe;
  const char * values;
};

TEST(AirEntry, A3_PreconditionFailed)
{
  const std::string prefix =
    "LOITER needs not landed, ARMED, nav_state and user intention AUTO_LOITER, no failsafe (";
  const std::vector<PreconditionCase> cases = {
    {"landed", true, Arming::kArmed, NavMode::kHold, NavMode::kHold, false,
     "landed=true, arming=ARMED, nav_state=AUTO_LOITER, intention=AUTO_LOITER, failsafe=false"},
    {"disarmed", false, Arming::kDisarmed, NavMode::kHold, NavMode::kHold, false,
     "landed=false, arming=DISARMED, nav_state=AUTO_LOITER, intention=AUTO_LOITER, failsafe=false"},
    {"offboard", false, Arming::kArmed, NavMode::kOffboard, NavMode::kOffboard, false,
     "landed=false, arming=ARMED, nav_state=OFFBOARD, intention=OFFBOARD, failsafe=false"},
    {"intention_offboard", false, Arming::kArmed, NavMode::kHold, NavMode::kOffboard, false,
     "landed=false, arming=ARMED, nav_state=AUTO_LOITER, intention=OFFBOARD, failsafe=false"},
    {"rtl", false, Arming::kArmed, NavMode::kRtl, NavMode::kRtl, false,
     "landed=false, arming=ARMED, nav_state=AUTO_RTL, intention=AUTO_RTL, failsafe=false"},
    {"failsafe", false, Arming::kArmed, NavMode::kHold, NavMode::kHold, true,
     "landed=false, arming=ARMED, nav_state=AUTO_LOITER, intention=AUTO_LOITER, failsafe=true"},
  };
  for (const PreconditionCase & c : cases) {
    SCOPED_TRACE(c.name);
    Harness h(air_loiter_mission());
    h.start_in_air();
    h.world.landed = c.landed;
    h.world.arming = c.arming;
    h.world.nav = c.nav;
    h.world.intention = c.intention;
    h.world.failsafe = c.failsafe;
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();
    expect_cell(
      h, "PREPARING.WAIT_READY", Event::kPreconditionFailed, "DONE", "ABORTED/PRECONDITION_FAILED",
      {}, before);
    EXPECT_EQ(termination_or_empty(h).detail, prefix + c.values + ")");
    EXPECT_FALSE(out.setpoint.has_value());
    EXPECT_TRUE(out.commands.empty());
    expect_prep_end(h, "ABORTED/PRECONDITION_FAILED");
  }
}

// ---- A4 P2와 ready_timeout ----

TEST(AirEntry, A4_WaitsInP2UntilReadyTimeout)
{
  // ready_timeout 30 s는 goal 접수(kStartNs)부터라 601번째 tick에 찬다.
  const std::uint64_t timeout_tick = 601;
  struct Case
  {
    const char * name;
    const char * waiting;
  };
  for (const Case c :
       {Case{"ekf", "EKF gate (failsafe_flags position/altitude/home)"},
        Case{"heading", "finite heading"}, Case{"x", "finite vehicle_local_position"}}) {
    SCOPED_TRACE(c.name);
    Harness h(air_loiter_mission());
    h.start_in_air();
    const std::string name = c.name;
    if (name == "ekf") {
      h.world.ekf_ready = false;
    } else if (name == "heading") {
      h.world.heading = std::nan("");
    } else {
      h.world.x = std::nan("");
    }
    tick_until(h, timeout_tick);
    const std::size_t before = h.edges().size();
    h.tick();
    expect_cell(
      h, "PREPARING.WAIT_READY", Event::kReadyTimeout, "DONE", "ABORTED/NOT_READY", {}, before);
    EXPECT_EQ(
      termination_or_empty(h).detail, std::string("ready_timeout: waiting for ") + c.waiting);
    for (const StepOutput & out : h.outputs()) {
      EXPECT_FALSE(out.setpoint.has_value());
      EXPECT_TRUE(out.commands.empty());
    }
    expect_prep_end(h, "ABORTED/NOT_READY");
  }
}

TEST(AirEntry, A4d_ReadyOnTimeoutTickStillTimesOut)
{
  Harness h(air_loiter_mission());
  h.start_in_air();
  h.world.ekf_ready = false;
  tick_until(h, 601);
  h.world.ekf_ready = true;
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "PREPARING.WAIT_READY", Event::kReadyTimeout, "DONE", "ABORTED/NOT_READY", {}, before);
  EXPECT_EQ(termination_or_empty(h).detail, "ready_timeout: waiting for nothing");
  for (const TransitionEdge & edge : h.edges()) {
    EXPECT_NE(edge.event, Event::kReadyAirOffboard);
  }
  expect_prep_end(h, "ABORTED/NOT_READY");
}

// ---- A5 진입 setpoint 고정 ----

TEST(AirEntry, A5_EntrySetpointIsHeldThroughLoiter)
{
  Harness h(air_loiter_mission());
  h.start_in_air();
  h.world.heading = 3.5;
  const double yaw = wrap_pi(3.5);
  start_air(h);
  const std::uint64_t s = kP + 10;
  const std::uint64_t last = s + 3 + kLoiterTicks;
  while (h.tick_no <= last) {
    h.world.x += 0.1;
    h.world.heading += 0.05;
    h.tick();
    ASSERT_FALSE(h.runner().done());
  }
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kMissionEnd);
  for (std::uint64_t k = kP; k <= last; ++k) {
    const StepOutput & out = out_at(h, k);
    ASSERT_TRUE(out.setpoint.has_value()) << "tick " << k;
    EXPECT_DOUBLE_EQ(out.setpoint->x, 1.0) << "tick " << k;
    EXPECT_DOUBLE_EQ(out.setpoint->y, 2.0) << "tick " << k;
    EXPECT_DOUBLE_EQ(out.setpoint->z, -5.0) << "tick " << k;
    EXPECT_DOUBLE_EQ(out.setpoint->yaw_ned, yaw) << "tick " << k;
  }
  EXPECT_NEAR(yaw, -2.783, 1e-3);
}

// ---- A6, A7 신호 기한 ----

TEST(AirEntry, A6_SignalTimeoutCleansUpWithHold)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  for (std::uint64_t k = p + 1; k < p + kSignalTicks; ++k) {
    const StepOutput out = tick_without_signal(h);
    EXPECT_TRUE(out.commands.empty()) << "tick " << k;
    EXPECT_TRUE(out.setpoint.has_value()) << "tick " << k;
  }
  const std::size_t before = h.edges().size();
  const StepOutput timeout = tick_without_signal(h);  // P+40
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kSignalTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  EXPECT_EQ(timeout.commands, kHoldOnly);
  EXPECT_FALSE(timeout.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, p + 43);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "offboard_signal_timeout: offboard signal not confirmed (published 40); cleanup: Hold "
    "confirmed");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A7_SignalConfirmOnTimeoutTickLoses)
{
  {
    Harness h(air_loiter_mission());
    const std::uint64_t p = start_air(h);
    tick_until_without_signal(h, p + kSignalTicks);
    h.world.signal_lost = false;
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();  // P+40: 신호 있음이 처음이고 기한
    expect_cell(
      h, "PREPARING.AIR_SIGNAL", Event::kSignalTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
      before);
    EXPECT_FALSE(has_command(out, CommandKind::kSetModeOffboard));
    EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
  }
  {
    // 대조: P+39에 처음 신호 있음이면 P+39에 신호 확인.
    Harness h(air_loiter_mission());
    const std::uint64_t p = start_air(h);
    tick_until_without_signal(h, p + kSignalTicks - 1);
    h.world.signal_lost = false;
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();
    expect_cell(
      h, "PREPARING.AIR_SIGNAL", Event::kSignalConfirmed, "PREPARING.AIR_OFFBOARD", "-", {},
      before);
    EXPECT_EQ(out.commands, kOffboardOnly);
  }
}

// ---- A8, A9 먼저 본 OFFBOARD ----

TEST(AirEntry, A8_OffboardBeforeSetModeCleansUpWithHold)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 5);
  h.world.nav = NavMode::kOffboard;  // 다른 주체의 전환
  h.world.intention = NavMode::kOffboard;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // P+5
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kOffboardBeforeSetMode, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  ASSERT_TRUE(out.setpoint.has_value());
  EXPECT_DOUBLE_EQ(out.setpoint->z, -5.0);
  const StepOutput hold = h.tick();  // P+6: AUTO_LOITER 표본
  EXPECT_FALSE(hold.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, p + 8);
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_TRUE(starts_with(detail, "OFFBOARD before DO_SET_MODE")) << detail;
  EXPECT_TRUE(ends_with(detail, "; cleanup: Hold confirmed")) << detail;
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A9a_OffboardBeforeSetModeOnSignalConfirmTick)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 10);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S tick
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kOffboardBeforeSetMode, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kSignalConfirmed}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
}

TEST(AirEntry, A9b_OffboardBeforeSetModeOnSignalTimeoutTick)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until_without_signal(h, p + kSignalTicks);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  const std::size_t before = h.edges().size();
  tick_without_signal(h);
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kOffboardBeforeSetMode, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kSignalTimeout}, before);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_TRUE(starts_with(detail, "OFFBOARD before DO_SET_MODE")) << detail;
}

TEST(AirEntry, A9c_OffboardBeforeSetModeWithCancel)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 5);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kOffboardBeforeSetMode, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel}, before);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  for (std::size_t i = before; i < h.edges().size(); ++i) {
    EXPECT_NE(h.edges()[i].event, Event::kCancel);
  }
  for (std::uint64_t k = p + 5; k < h.tick_no - 1; ++k) {
    const StepOutput & out = out_at(h, k);
    ASSERT_TRUE(out.feedback.has_value());
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kPreparing) << "tick " << k;
  }
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

// ---- A10-A16 P5 ----

TEST(AirEntry, A10_LostSetModeIsResent)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  EXPECT_EQ(s, kP + 10);
  EXPECT_EQ(out_at(h, s).commands, kOffboardOnly);
  h.offboard_response = OffboardResponse::kAccept;
  tick_until(h, s + kResendTicks);
  EXPECT_EQ(h.tick().commands, kOffboardOnly);  // S+10
  std::size_t before = h.edges().size();
  h.tick();  // S+11
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
    {}, before);
  h.tick();
  before = h.edges().size();
  h.tick();  // S+13
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.LOITER", "-", {}, before);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
  expect_air_invariants(h);
}

TEST(AirEntry, A11a_SetModeRejected)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kReject;
  const std::uint64_t s = h.drive_to_air_offboard();
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+1
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, s + 4);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "DO_SET_MODE(OFFBOARD) rejected: TEMPORARILY_REJECTED; cleanup: Hold confirmed");
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A11b_RejectionWinsOverFirstOffboardSample)
{
  Harness h(air_loiter_mission());
  h.auto_offboard_ack = false;
  h.drive_to_air_offboard();  // 가짜 PX4가 S의 DO_SET_MODE를 받아 S+1 표본은 OFFBOARD
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+1
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {}, before);
  for (std::size_t i = before; i < h.edges().size(); ++i) {
    EXPECT_NE(h.edges()[i].event, Event::kOffboardFirstSample);
  }
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_TRUE(out.setpoint.has_value());
}

TEST(AirEntry, A12_LostRejectionIsCaughtOnResend)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + kResendTicks);
  h.offboard_response = OffboardResponse::kReject;
  EXPECT_EQ(h.tick().commands, kOffboardOnly);  // S+10
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+11
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "DO_SET_MODE(OFFBOARD) rejected: TEMPORARILY_REJECTED; cleanup: Hold confirmed");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A13_ModeConfirmTimeoutWithoutOffboard)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  for (std::uint64_t k = s + 1; k < s + kModeConfirmTicks; ++k) {
    const StepOutput out = h.tick();
    ASSERT_FALSE(h.runner().done());
    if ((k - s) % kResendTicks == 0) {
      EXPECT_EQ(out.commands, kOffboardOnly) << "S+" << k - s;
    } else {
      EXPECT_TRUE(out.commands.empty()) << "S+" << k - s;
    }
  }
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 6);
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, s + 63);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "mode_confirm_timeout: OFFBOARD not observed; cleanup: Hold confirmed");
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A14_FirstOffboardSampleOnTimeoutTick)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + kModeConfirmTicks);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
    {}, before);
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE",
    "-", {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_TRUE(out.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "mode_confirm_timeout: OFFBOARD observed but not confirmed; cleanup: Hold confirmed");
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A15_ThirdOffboardOnTimeoutTickLoses)
{
  {
    Harness h(air_loiter_mission());
    h.offboard_response = OffboardResponse::kIgnore;
    const std::uint64_t s = h.drive_to_air_offboard();
    tick_until(h, s + 58);
    h.world.nav = NavMode::kOffboard;
    h.world.intention = NavMode::kOffboard;
    std::size_t before = h.edges().size();
    h.tick();  // S+58
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
      {}, before);
    h.tick();
    before = h.edges().size();
    h.tick();  // S+60: 3회째와 기한
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE",
      "-", {}, before);
    for (const TransitionEdge & edge : h.edges()) {
      EXPECT_NE(state_key_name(edge.to), "ITEM.LOITER");
    }
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
  }
  {
    // 대조: S+57, S+58, S+59이면 S+59에 첫 항목 시작.
    Harness h(air_loiter_mission());
    h.offboard_response = OffboardResponse::kIgnore;
    const std::uint64_t s = h.drive_to_air_offboard();
    tick_until(h, s + 57);
    h.world.nav = NavMode::kOffboard;
    h.world.intention = NavMode::kOffboard;
    h.tick();
    h.tick();
    const std::size_t before = h.edges().size();
    h.tick();  // S+59
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.LOITER", "-", {}, before);
  }
}

TEST(AirEntry, A16_NoResendAfterFirstOffboardSample)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + 15);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  const std::uint64_t stamp = h.default_timestamp_us();
  std::size_t before = h.edges().size();
  h.tick();  // S+15
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
    {}, before);
  h.auto_samples = false;
  for (std::uint64_t k = s + 16; k < s + kModeConfirmTicks; ++k) {
    h.push_world_samples_without_status();
    h.push_status(stamp);  // 같은 표본이 다시 온다(수신은 신선)
    const StepOutput out = h.step_only();
    ASSERT_FALSE(h.runner().done()) << "S+" << k - s;
    EXPECT_TRUE(out.commands.empty()) << "S+" << k - s;
    EXPECT_TRUE(out.setpoint.has_value()) << "S+" << k - s;
  }
  h.push_world_samples_without_status();
  h.push_status(stamp);
  before = h.edges().size();
  const StepOutput timeout = h.step_only();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE",
    "-", {}, before);
  EXPECT_EQ(timeout.commands, kHoldOnly);
  h.auto_samples = true;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "mode_confirm_timeout: OFFBOARD observed but not confirmed; cleanup: Hold confirmed");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 2);
  for (std::uint64_t k = s + 1; k < s + 15; ++k) {
    EXPECT_EQ(out_at(h, k).commands.empty(), k != s + 10) << "S+" << k - s;
  }
}

// ---- A17, A18 면제 ----

enum class AirState
{
  kSignal,
  kOffboard,
};

// AIR_SIGNAL(신호 없음 고정)이나 AIR_OFFBOARD(DO_SET_MODE 무시)에 들어간다. AIR_OFFBOARD이면 S를,
// AIR_SIGNAL이면 0을 돌려준다.
std::uint64_t enter_state(Harness & h, AirState state)
{
  if (state == AirState::kSignal) {
    start_air(h);
    tick_without_signal(h);
    tick_without_signal(h);
    EXPECT_EQ(h.view().prep, PrepStep::kAirSignal);
    return 0;
  }
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  h.tick();
  EXPECT_EQ(h.view().prep, PrepStep::kAirOffboard);
  return s;
}

StepOutput tick_in(Harness & h, AirState state, bool cancel = false)
{
  return state == AirState::kSignal ? tick_without_signal(h, cancel) : h.tick(cancel);
}

TEST(AirEntry, A17_HoldIsExemptBeforeFirstOffboardSample)
{
  struct Case
  {
    const char * name;
    NavMode nav;
    NavMode intention;
    bool failsafe;
    Event event;  // kCancel이면 끝나지 않는다
    const char * reason;
  };
  const std::vector<Case> cases = {
    {"hold", NavMode::kHold, NavMode::kHold, false, Event::kCancel, ""},
    {"hold_intention_offboard", NavMode::kHold, NavMode::kOffboard, false, Event::kCancel, ""},
    {"rtl", NavMode::kRtl, NavMode::kRtl, false, Event::kMonitorModeExternal,
     "ABORTED/EXTERNAL_MODE_CHANGE"},
    {"other_intention_offboard", NavMode::kOther, NavMode::kOffboard, false,
     Event::kMonitorModeDefensive, "ABORTED/FAILSAFE"},
    {"hold_failsafe", NavMode::kHold, NavMode::kHold, true, Event::kMonitorModeFailsafe,
     "ABORTED/FAILSAFE"},
  };
  for (const AirState state : {AirState::kSignal, AirState::kOffboard}) {
    const std::string from =
      state == AirState::kSignal ? "PREPARING.AIR_SIGNAL" : "PREPARING.AIR_OFFBOARD";
    for (const Case & c : cases) {
      SCOPED_TRACE(from + " " + c.name);
      Harness h(air_loiter_mission());
      const std::uint64_t s = enter_state(h, state);
      h.world.nav = c.nav;
      h.world.intention = c.intention;
      h.world.failsafe = c.failsafe;
      const std::size_t before = h.edges().size();
      const StepOutput out = tick_in(h, state);
      if (c.event == Event::kCancel) {
        // 면제: 끝나지 않고 상태 key와 발행이 그대로다. AIR_OFFBOARD는 재전송 주기(S+10)를 넘겨
        // 그 tick의 명령이 DO_SET_MODE(OFFBOARD) 하나뿐인지 본다.
        const PrepStep prep = h.view().prep;
        EXPECT_TRUE(out.commands.empty());
        EXPECT_TRUE(out.setpoint.has_value());
        for (int i = 0; i < 12; ++i) {
          const std::uint64_t k = h.tick_no;
          const StepOutput o = tick_in(h, state);
          ASSERT_FALSE(h.runner().done()) << "tick " << k << ": " << termination_or_empty(h).detail;
          EXPECT_EQ(h.view().prep, prep) << "tick " << k;
          EXPECT_TRUE(o.setpoint.has_value()) << "tick " << k;
          if (state == AirState::kOffboard && k == s + kResendTicks) {
            EXPECT_EQ(o.commands, kOffboardOnly) << "S+10";
          } else {
            EXPECT_TRUE(o.commands.empty()) << "tick " << k;
          }
        }
        if (state == AirState::kOffboard) {
          EXPECT_GT(h.tick_no, s + kResendTicks);
        }
        continue;
      }
      expect_cell(h, from, c.event, "DONE", c.reason, {}, before);
      EXPECT_TRUE(out.commands.empty());
      EXPECT_FALSE(out.setpoint.has_value());
      expect_prep_end(h, c.reason);
    }
  }
}

TEST(AirEntry, A18_ExemptionEndsAtFirstOffboardSample)
{
  {
    Harness h(air_loiter_mission());
    h.drive_to_air_seen();         // S+1: O3
    h.world.nav = NavMode::kHold;  // 운용자 Hold
    h.world.intention = NavMode::kHold;
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();  // S+2
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kMonitorModeExternal, "DONE",
      "ABORTED/EXTERNAL_MODE_CHANGE", {}, before);
    EXPECT_EQ(
      termination_or_empty(h).detail, std::string(kLabel) + ": monitor rank 7 ModeExternal");
    EXPECT_TRUE(out.commands.empty());
    EXPECT_FALSE(out.setpoint.has_value());
    expect_prep_end(h, "ABORTED/EXTERNAL_MODE_CHANGE");
  }
  {
    Harness h(air_loiter_mission());
    h.drive_to_air_seen();
    h.world.nav = NavMode::kHold;
    h.world.intention = NavMode::kOffboard;
    const std::size_t before = h.edges().size();
    h.tick();
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kMonitorModeDefensive, "DONE", "ABORTED/FAILSAFE",
      {}, before);
    expect_prep_end(h, "ABORTED/FAILSAFE");
  }
}

// ---- A19 failsafe 이력 구간 ----

TEST(AirEntry, A19a_FailsafeHistoryInAirOffboardSeen)
{
  Harness h(air_loiter_mission());
  h.drive_to_air_offboard();
  h.world.failsafe = true;  // S+1: OFFBOARD이고 failsafe(어느 행에도 맞지 않는다)
  std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardFirstSample, "PREPARING.AIR_OFFBOARD_SEEN", "-",
    {}, before);
  h.world.failsafe = false;
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  before = h.edges().size();
  h.tick();  // S+2
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kMonitorDisarmedOnGround, "DONE", "ABORTED/FAILSAFE",
    {}, before);
  expect_prep_end(h, "ABORTED/FAILSAFE");
}

TEST(AirEntry, A19b_FailsafeHistoryCarriesIntoFirstItem)
{
  Harness h(air_loiter_mission());
  h.drive_to_air_seen();  // S+1
  h.world.failsafe = true;
  h.tick();  // S+2: OFFBOARD이고 failsafe
  h.world.failsafe = false;
  h.tick();  // S+3: 3회째
  ASSERT_EQ(h.view().stage, Stage::kItem);
  h.tick();
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "ITEM.LOITER", Event::kMonitorDisarmedOnGround, "DONE", "ABORTED/FAILSAFE", {}, before);
  expect_terminated_once_as(h, "ABORTED/FAILSAFE");
}

// ---- A20 감시 행 전부 ----

enum class MonitorState
{
  kSignal,
  kOffboard,
  kSeen,
};

struct MonitorCase
{
  const char * name;
  int rank;
  Event event;
  const char * reason;
};

// 상태에 들어간다. S나 P를 돌려준다(행 3의 끊김 기준).
std::uint64_t enter_monitor_state(Harness & h, MonitorState state)
{
  switch (state) {
    case MonitorState::kSignal:
      return start_air(h);
    case MonitorState::kOffboard:
      h.offboard_response = OffboardResponse::kIgnore;
      return h.drive_to_air_offboard();
    case MonitorState::kSeen: {
      const std::uint64_t s = h.drive_to_air_seen();
      return s + 1;
    }
  }
  return 0;
}

StepOutput tick_state(Harness & h, MonitorState state)
{
  return state == MonitorState::kSignal ? tick_without_signal(h) : h.tick();
}

TEST(AirEntry, A20_EveryMonitorRowInEveryAirState)
{
  const std::vector<MonitorCase> cases = {
    {"rank1", 1, Event::kMonitorTimestampFailure, "ABORTED/INTERNAL"},
    {"rank2", 2, Event::kMonitorIdentityMismatch, "ABORTED/INTERNAL"},
    {"rank3", 3, Event::kMonitorLinkLost, "ABORTED/LINK_LOST"},
    {"rank4", 4, Event::kMonitorDisarmedInAir, "ABORTED/FAILSAFE"},
    {"rank5", 5, Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM"},
    {"rank5_failsafe", 5, Event::kMonitorDisarmedOnGround, "ABORTED/FAILSAFE"},
    {"rank6", 6, Event::kMonitorModeFailsafe, "ABORTED/FAILSAFE"},
    {"rank7", 7, Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE"},
    {"rank7_hold", 7, Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE"},
    {"rank8", 8, Event::kMonitorModeDefensive, "ABORTED/FAILSAFE"},
    {"pair", 5, Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM"},
  };
  for (const MonitorState state :
       {MonitorState::kSignal, MonitorState::kOffboard, MonitorState::kSeen}) {
    const std::string from = state == MonitorState::kSignal     ? "PREPARING.AIR_SIGNAL"
                             : state == MonitorState::kOffboard ? "PREPARING.AIR_OFFBOARD"
                                                                : "PREPARING.AIR_OFFBOARD_SEEN";
    for (const MonitorCase & c : cases) {
      const std::string name = c.name;
      if (name == "rank7_hold" && state != MonitorState::kSeen) {
        continue;
      }
      SCOPED_TRACE(from + " " + name);
      Harness h(air_loiter_mission());
      const std::uint64_t base = enter_monitor_state(h, state);
      std::vector<Event> also;
      StepOutput out;
      std::size_t before = 0;
      if (name == "rank3") {
        // base 뒤 vehicle_status를 끊는다. base + 40에 link_timeout.
        h.auto_samples = false;
        while (h.tick_no < base + kSignalTicks) {
          if (state == MonitorState::kSignal) {
            h.world.signal_lost = true;
          }
          h.push_world_samples_without_status();
          h.step_only();
          ASSERT_FALSE(h.runner().done())
            << "tick " << h.tick_no - 1 << " " << termination_or_empty(h).detail;
        }
        if (state == MonitorState::kSignal) {
          h.world.signal_lost = true;
        }
        h.push_world_samples_without_status();
        before = h.edges().size();
        out = h.step_only();
      } else {
        if (name == "rank1") {
          h.clock.fail = true;
        } else if (name == "rank2") {
          h.world.identity = IdentityCheck::kMismatch;
        } else if (name == "rank4") {
          h.world.arming = Arming::kDisarmed;
          h.world.nav = NavMode::kOffboard;
          h.world.landed = false;
        } else if (name == "rank5" || name == "rank5_failsafe") {
          h.world.arming = Arming::kDisarmed;
          h.world.nav = NavMode::kOffboard;
          h.world.landed = true;
          h.world.failsafe = name == "rank5_failsafe";
        } else if (name == "rank6") {
          h.world.nav = state == MonitorState::kSeen ? NavMode::kOther : NavMode::kHold;
          h.world.failsafe = true;
        } else if (name == "rank7") {
          h.world.nav = NavMode::kRtl;
          h.world.intention = NavMode::kRtl;
        } else if (name == "rank7_hold") {
          h.world.nav = NavMode::kHold;
          h.world.intention = NavMode::kHold;
        } else if (name == "rank8") {
          h.world.nav = NavMode::kOther;
          h.world.intention = NavMode::kOffboard;
        } else if (name == "pair") {
          h.world.arming = Arming::kDisarmed;
          h.world.landed = true;
          h.world.nav = NavMode::kOther;
          h.world.intention = NavMode::kOther;
          also = {Event::kMonitorModeExternal};
        }
        before = h.edges().size();
        out = tick_state(h, state);
      }
      expect_cell(h, from, c.event, "DONE", c.reason, also, before);
      EXPECT_TRUE(out.commands.empty());
      EXPECT_FALSE(out.setpoint.has_value());
      if (c.rank == 1) {
        EXPECT_FALSE(out.px4_timestamp_us.has_value());
      }
      const std::string detail = termination_or_empty(h).detail;
      EXPECT_TRUE(
        starts_with(detail, std::string(kLabel) + ": monitor rank " + std::to_string(c.rank)))
        << detail;
      for (const TransitionEdge & edge : h.edges()) {
        EXPECT_NE(edge.event, Event::kPreparingIdentityMismatch);
      }
      expect_prep_end(h, c.reason);
    }
  }
}

// ---- A21 묵은 표본 ----

TEST(AirEntry, A21_StaleSampleIsNotMonitored)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t p_stamp = h.default_timestamp_us();  // P tick 표본의 timestamp
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + 5);
  Sample stale = disarmed(true);
  stale.timestamp_us = p_stamp - 1000U;
  h.feed({stale});  // S+5
  ASSERT_FALSE(h.runner().done()) << termination_or_empty(h).detail;
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  tick_until(h, s + kResendTicks);
  EXPECT_EQ(h.tick().commands, kOffboardOnly);  // S+10: 재전송 주기 그대로
  EXPECT_EQ(h.view().prep, PrepStep::kAirOffboard);
  EXPECT_FALSE(h.runner().done());
}

// ---- A22 P3 tick의 Px4Timestamp ----

TEST(AirEntry, A22a_StampFailureOnPublishStartTick)
{
  Harness h(air_loiter_mission());
  h.start_in_air();
  h.clock.fail = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();
  expect_cell(
    h, "PREPARING.WAIT_READY", Event::kReadyAirOffboard, "PREPARING.AIR_SIGNAL", "-", {}, before);
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {}, before);
  EXPECT_FALSE(out.setpoint.has_value());
  EXPECT_FALSE(out.px4_timestamp_us.has_value());
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "Px4Timestamp unavailable; vehicle state unknown, may remain armed on ground");
  expect_prep_end(h, "ABORTED/INTERNAL");
}

TEST(AirEntry, A22b_StampFailureAfterPublishStartIsMonitorRank1)
{
  Harness h(air_loiter_mission());
  start_air(h);
  h.clock.fail = true;
  const std::size_t before = h.edges().size();
  h.tick();
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kMonitorTimestampFailure, "DONE", "ABORTED/INTERNAL", {},
    before);
  expect_prep_end(h, "ABORTED/INTERNAL");
}

// ---- A23, A24 취소 ----

TEST(AirEntry, A23a_CancelInAirSignal)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 3);
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();
  expect_cell(h, "PREPARING.AIR_SIGNAL", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(out.feedback.has_value());
  EXPECT_EQ(out.feedback->phase, FeedbackPhase::kCanceling);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, p + 6);
  expect_prep_end(h, "CANCELED/NONE");
}

TEST(AirEntry, A23b_CancelInAirOffboard)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + 5);
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();
  expect_cell(h, "PREPARING.AIR_OFFBOARD", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, s + 8);
  expect_prep_end(h, "CANCELED/NONE");
}

TEST(AirEntry, A23c_CancelInAirOffboardSeen)
{
  Harness h(air_loiter_mission());
  const std::uint64_t s = h.drive_to_air_seen();
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+2
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  EXPECT_TRUE(out.setpoint.has_value());
  EXPECT_FALSE(h.tick().setpoint.has_value());  // S+3: AUTO_LOITER
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, s + 5);
  expect_prep_end(h, "CANCELED/NONE");
}

// 정리로 들어가는 사건과 취소: 그 사건이 이기고 취소는 무시된다.
void expect_cleanup_wins_over_cancel(Harness & h, std::size_t before)
{
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20, true));
  for (std::size_t i = before + 1; i < h.edges().size(); ++i) {
    EXPECT_NE(h.edges()[i].event, Event::kCancel);
  }
  for (std::size_t i = 0; i < h.outputs().size(); ++i) {
    const StepOutput & out = h.outputs()[i];
    if (out.feedback.has_value()) {
      EXPECT_NE(out.feedback->phase, FeedbackPhase::kCanceling) << "tick " << i + 1;
    }
  }
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

// 바로 끝내는 사건과 취소: 그 tick과 그 뒤에 Hold와 disarm이 나가지 않는다.
void expect_immediate_end_with_cancel(Harness & h, const StepOutput & out, const char * reason)
{
  EXPECT_TRUE(out.commands.empty());
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  expect_prep_end(h, reason);
}

TEST(AirEntry, A23d_SignalTimeoutWithCancel)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until_without_signal(h, p + kSignalTicks);
  const std::size_t before = h.edges().size();
  tick_without_signal(h, true);
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kSignalTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel}, before);
  expect_cleanup_wins_over_cancel(h, before);
}

TEST(AirEntry, A23d_MonitorRowWithCancelInAirSignal)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 5);
  h.world.failsafe = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick(true);
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kMonitorModeFailsafe, "DONE", "ABORTED/FAILSAFE",
    {Event::kCancel}, before);
  expect_immediate_end_with_cancel(h, out, "ABORTED/FAILSAFE");
}

TEST(AirEntry, A23d_RejectionWithCancel)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kReject;
  h.drive_to_air_offboard();
  const std::size_t before = h.edges().size();
  h.tick(true);  // S+1
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel}, before);
  expect_cleanup_wins_over_cancel(h, before);
}

TEST(AirEntry, A23d_ModeConfirmTimeoutWithCancelInAirOffboard)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + kModeConfirmTicks);
  const std::size_t before = h.edges().size();
  h.tick(true);
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel}, before);
  expect_cleanup_wins_over_cancel(h, before);
}

TEST(AirEntry, A23d_MonitorRowWithCancelInAirOffboard)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + 5);
  h.world.failsafe = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick(true);
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kMonitorModeFailsafe, "DONE", "ABORTED/FAILSAFE",
    {Event::kCancel}, before);
  expect_immediate_end_with_cancel(h, out, "ABORTED/FAILSAFE");
}

TEST(AirEntry, A23d_ModeConfirmTimeoutWithCancelInAirOffboardSeen)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + 58);
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  h.tick();  // S+58: 첫 OFFBOARD 표본
  h.tick();
  const std::size_t before = h.edges().size();
  h.tick(true);  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE",
    "-", {Event::kCancel}, before);
  expect_cleanup_wins_over_cancel(h, before);
}

TEST(AirEntry, A23d_MonitorRowWithCancelInAirOffboardSeen)
{
  Harness h(air_loiter_mission());
  h.drive_to_air_seen();
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick(true);  // S+2
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kMonitorModeExternal, "DONE",
    "ABORTED/EXTERNAL_MODE_CHANGE", {Event::kCancel}, before);
  expect_immediate_end_with_cancel(h, out, "ABORTED/EXTERNAL_MODE_CHANGE");
}

TEST(AirEntry, A23e_CancelOnGroundArmedUsesGroundBranch)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  h.world.landed = true;  // P+1부터 지상 ARMED(AUTO_LOITER 그대로)
  for (std::uint64_t k = p + 1; k < p + 3; ++k) {
    EXPECT_TRUE(h.tick().commands.empty()) << "tick " << k;
    ASSERT_FALSE(h.runner().done()) << termination_or_empty(h).detail;
  }
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // P+3
  expect_cell(h, "PREPARING.AIR_SIGNAL", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  expect_cell(
    h, "CLEANUP.CANCEL.NONE", Event::kEnterGround, "CLEANUP.CANCEL.GROUND", "-", {}, before);
  EXPECT_EQ(out.commands, kDisarmOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(out.feedback.has_value());
  EXPECT_EQ(out.feedback->phase, FeedbackPhase::kCanceling);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  expect_cell(
    h, "CLEANUP.CANCEL.GROUND", Event::kGroundDisarmConfirmed, "DONE", "CANCELED/NONE", {}, before);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  expect_prep_end(h, "CANCELED/NONE");
}

TEST(AirEntry, A24_CancelOnSetModeSendTick)
{
  Harness h(air_loiter_mission());
  const std::uint64_t p = start_air(h);
  tick_until(h, p + 10);
  h.cancel_sticky = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S
  expect_cell(
    h, "PREPARING.AIR_SIGNAL", Event::kSignalConfirmed, "PREPARING.AIR_OFFBOARD", "-", {}, before);
  expect_cell(h, "PREPARING.AIR_OFFBOARD", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out.commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 0);
  expect_prep_end(h, "CANCELED/NONE");
}

// ---- A25 ITEM_TIMEOUT 정리의 "정리할 것 없음" ----

// [LOITER(duration 5 s, timeout 6 s), LOITER]의 첫 LOITER에서 항목 시작 + 4.95 s의 tick까지 돌리고,
// 다음 tick의 시각을 항목 시작 + 6.0 s로 둔다(경과가 duration과 timeout을 함께 넘는다).
void drive_to_loiter_timeout_tick(Harness & h)
{
  h.drive_to_air_seen();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kItem; }, 10));
  const std::int64_t item_start_ns = h.now_ns - kTickNs;
  while (h.now_ns < item_start_ns + 99 * kTickNs + kTickNs) {
    h.tick();
    ASSERT_FALSE(h.runner().done());
  }
  h.now_ns = item_start_ns + 6 * kNsPerSecond;
}

MissionSpec loiter_timeout_mission()
{
  MissionSpec m;
  m.mission_id = "air5";
  m.items = {loiter_item(5, 6), loiter_item()};
  return m;
}

const char * const kItemTimeoutNothing =
  "item 0 (LOITER) timeout; cleanup: on ground and DISARMED, arm never sent";

TEST(AirEntry, A25a_ItemTimeoutWithStaleDisarmedSample)
{
  Harness h(loiter_timeout_mission());
  const std::uint64_t p_stamp = h.default_timestamp_us();
  ASSERT_NO_FATAL_FAILURE(drive_to_loiter_timeout_tick(h));
  Sample stale = disarmed(true);
  stale.timestamp_us = p_stamp - 1000U;
  const std::size_t before = h.edges().size();
  const std::vector<StepOutput> outs = h.feed({stale});
  expect_cell(
    h, "ITEM.LOITER", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
    {Event::kLoiterElapsed}, before);
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.NONE", Event::kCleanupNothingToDo, "DONE", "ABORTED/ITEM_TIMEOUT", {},
    before);
  EXPECT_EQ(termination_or_empty(h).detail, kItemTimeoutNothing);
  EXPECT_TRUE(outs.front().commands.empty());
  expect_air_invariants(h);
  expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
}

TEST(AirEntry, A25b_ItemTimeoutHoldThenDisarmedOnGround)
{
  Harness h(loiter_timeout_mission());
  h.hold_response = HoldResponse::kIgnore;
  ASSERT_NO_FATAL_FAILURE(drive_to_loiter_timeout_tick(h));
  h.tick();  // ITEM_TIMEOUT, 공중 분기
  ASSERT_EQ(h.view().branch, Branch::kAir);
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.AIR", Event::kCleanupNothingToDo, "DONE", "ABORTED/ITEM_TIMEOUT", {},
    before);
  EXPECT_EQ(termination_or_empty(h).detail, kItemTimeoutNothing);
  EXPECT_TRUE(out.commands.empty());
  expect_air_invariants(h);
  expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
}

TEST(AirEntry, A25c_ItemTimeoutLandPathThenDisarmedOnGround)
{
  Harness h(loiter_timeout_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  ASSERT_NO_FATAL_FAILURE(drive_to_loiter_timeout_tick(h));
  h.tick();  // ITEM_TIMEOUT, 공중 분기
  h.tick();  // Hold 거부 ack, Land 경로
  ASSERT_EQ(h.view().branch, Branch::kAirLand);
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.AIR_LAND", Event::kCleanupNothingToDo, "DONE", "ABORTED/ITEM_TIMEOUT",
    {}, before);
  EXPECT_TRUE(
    ends_with(termination_or_empty(h).detail, "cleanup: on ground and DISARMED, arm never sent"))
    << termination_or_empty(h).detail;
  EXPECT_TRUE(out.commands.empty());
  expect_air_invariants(h);
  expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
}

// ---- A26 실패 tick에 지상 ARMED ----

// kIgnore. S+1에 OFFBOARD 표본(O3), S+2..S+59는 S+1과 같은 timestamp의 표본, S+60에 새 OFFBOARD
// 표본이고 landed true(ARMED). S를 돌려준다.
std::uint64_t drive_seen_then_landed_on_timeout(Harness & h)
{
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  const std::uint64_t stamp = h.default_timestamp_us();
  h.tick();  // S+1
  h.auto_samples = false;
  while (h.tick_no < s + kModeConfirmTicks) {
    h.push_world_samples_without_status();
    h.push_status(stamp);
    h.step_only();
  }
  h.auto_samples = true;
  h.world.landed = true;
  return s;
}

TEST(AirEntry, A26a_TimeoutOnGroundArmedDisarms)
{
  Harness h(air_loiter_mission());
  const std::uint64_t s = drive_seen_then_landed_on_timeout(h);
  ASSERT_FALSE(h.runner().done());
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE",
    "-", {}, before);
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.NONE", Event::kEnterGround, "CLEANUP.PREPARING_FAILURE.GROUND",
    "-", {}, before);
  EXPECT_EQ(out.commands, kDisarmOnly);
  ASSERT_TRUE(out.setpoint.has_value());
  EXPECT_EQ(out.setpoint->kind, SetpointKind::kGround);
  EXPECT_DOUBLE_EQ(out.setpoint->x, h.world.x);
  EXPECT_DOUBLE_EQ(out.setpoint->z, h.world.z);
  EXPECT_DOUBLE_EQ(out.setpoint->yaw_ned, h.world.heading);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.GROUND", Event::kGroundDisarmConfirmed, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_TRUE(starts_with(
    termination_or_empty(h).detail,
    "mode_confirm_timeout: OFFBOARD observed but not confirmed; cleanup: "))
    << termination_or_empty(h).detail;
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  EXPECT_EQ(out_at(h, s + kModeConfirmTicks).commands, kDisarmOnly);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A26b_TimeoutOnGroundArmedDisarmNotConfirmed)
{
  Harness h(air_loiter_mission());
  h.disarm_response = CommandResponse::kIgnore;
  const std::uint64_t s = drive_seen_then_landed_on_timeout(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(h.tick().commands, kDisarmOnly);  // S+60
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
  EXPECT_EQ(h.tick_no - 1, s + 2 * kModeConfirmTicks);
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.GROUND", Event::kGroundDisarmTimeout, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(out_at(h, s + 2 * kModeConfirmTicks).commands, kDisarmOnly);
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("disarm not confirmed within mode_confirm_timeout"), std::string::npos)
    << detail;
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(AirEntry, A26c_TimeoutWithoutOffboardOnGroundArmed)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + kModeConfirmTicks);
  h.world.landed = true;
  const std::size_t before = h.edges().size();
  const StepOutput out = h.tick();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.NONE", Event::kEnterGround, "CLEANUP.PREPARING_FAILURE.GROUND",
    "-", {}, before);
  EXPECT_EQ(out.commands, kDisarmOnly);
  EXPECT_FALSE(out.setpoint.has_value());
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.GROUND", Event::kGroundDisarmConfirmed, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_TRUE(starts_with(
    termination_or_empty(h).detail, "mode_confirm_timeout: OFFBOARD not observed; cleanup: "))
    << termination_or_empty(h).detail;
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

// ---- A27 준비 단계 실패 정리의 "정리할 것 없음" ----

TEST(AirEntry, A27_PreparingFailureHoldThenDisarmedOnGround)
{
  Harness h(air_loiter_mission());
  h.offboard_response = OffboardResponse::kIgnore;
  h.hold_response = HoldResponse::kIgnore;
  const std::uint64_t s = h.drive_to_air_offboard();
  tick_until(h, s + kModeConfirmTicks);
  std::size_t before = h.edges().size();
  const StepOutput timeout = h.tick();  // S+60
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-", {},
    before);
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.NONE", Event::kEnterAir, "CLEANUP.PREPARING_FAILURE.AIR", "-", {},
    before);
  EXPECT_EQ(timeout.commands, kHoldOnly);
  EXPECT_FALSE(timeout.setpoint.has_value());
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  h.world.nav = NavMode::kOffboard;  // harness disarmed()의 기본값
  before = h.edges().size();
  const StepOutput out = h.tick();  // S+61
  expect_cell(
    h, "CLEANUP.PREPARING_FAILURE.AIR", Event::kCleanupNothingToDo, "DONE",
    "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "mode_confirm_timeout: OFFBOARD not observed; cleanup: on ground and DISARMED, arm never sent");
  EXPECT_TRUE(out.commands.empty());
  expect_prep_end(h, "ABORTED/MODE_SWITCH_FAILED");
}

}  // namespace
}  // namespace idsim_mission::core::test
