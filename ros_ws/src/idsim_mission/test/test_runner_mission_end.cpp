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

// 공중 종료 단계(마지막 항목이 setpoint 항목인 미션. 1b decisions.md 쟁점 10, 쟁점 11, 쟁점 12
// "명령과 ack의 유실"). 사례 이름의 T 번호는 B9 S3 칸 명세 6.2절의 사례다.
//
// 표기: S는 마지막 setpoint 항목의 완료 tick(종료 단계 첫 tick), S+k는 그 뒤 k번째 tick(50 ms
// 간격). 시간 값은 core/config.hpp 기본값이다: hold_confirm_timeout 3 s(S+60), 정리의 상한
// 12 s(S+240), command_resend_period 0.5 s(10 tick), link_timeout 2 s(40 tick),
// land_disarm_fallback_delay 5 s(100 tick), mode_confirm_timeout 3 s(60 tick).
// 별도 표기가 없으면 미션은 [TAKEOFF, LOITER](LOITER 5 s)이고 S에 공중 OFFBOARD다. 지상 사례는
// [TAKEOFF] height 0.2, acceptance 0.3이라 landed true인 채 도달한다(이륙 이력 없음).
// Hold 거부 ack, 공중 DISARMED, 식별 불일치, 묵은 표본, 시각 건너뛰기는 PX4 v1.17.0 SITL에서
// 재현하기 어려운 경로라 합성 표본과 합성 ack로만 시험한다.

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

constexpr std::uint64_t kLoiterTicks = 100;  // LOITER 5 s

MissionSpec takeoff_loiter_mission()
{
  MissionSpec m;
  m.mission_id = "end2";
  m.items = {takeoff_item(), loiter_item()};
  return m;
}

MissionSpec takeoff_only_mission(double height = 5.0)
{
  MissionSpec m;
  m.mission_id = "end1";
  m.items = {takeoff_item(height)};
  return m;
}

// 다음에 돌 tick이 tick이 될 때까지 돈다(끝나면 멈춘다).
void run_to(Harness & h, std::uint64_t tick)
{
  while (h.tick_no < tick && !h.runner().done()) {
    h.tick();
  }
}

// 다음 tick 하나를 돈다. 기록이 나기 직전의 edges().size()를 돌려준다.
std::size_t tick_marked(Harness & h)
{
  const std::size_t before = h.edges().size();
  h.tick();
  return before;
}

struct EndStart
{
  std::uint64_t s{0};
  std::int64_t s_ns{0};   // S의 tick 입력 시각
  std::size_t before{0};  // S 직전의 edges().size()
};

// [TAKEOFF, LOITER]: LOITER 완료 tick(S)까지 돈다. 공중 OFFBOARD.
EndStart start_air_end(Harness & h, bool cancel = false)
{
  h.drive_to_loiter();
  EndStart st;
  st.s = h.tick_no - 1 + kLoiterTicks;
  run_to(h, st.s);
  st.s_ns = h.now_ns;
  st.before = h.edges().size();
  h.tick(cancel);
  return st;
}

// [TAKEOFF] height 5: 공중에서 목표 고도에 닿은 tick(S)까지.
EndStart start_air_takeoff_end(Harness & h, bool cancel = false)
{
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  EndStart st;
  st.s = h.tick_no;
  st.s_ns = h.now_ns;
  st.before = h.edges().size();
  h.tick(cancel);
  return st;
}

// [TAKEOFF] height 0.2: landed true인 채 도달한 tick(S)까지.
EndStart start_ground_end(Harness & h)
{
  h.drive_to_takeoff();
  EndStart st;
  st.s = h.tick_no;
  st.s_ns = h.now_ns;
  st.before = h.edges().size();
  h.tick();
  return st;
}

bool has_edge(const Harness & h, Event event, std::size_t from_index = 0)
{
  for (std::size_t i = from_index; i < h.edges().size(); ++i) {
    if (h.edges()[i].tagged && h.edges()[i].event == event) {
      return true;
    }
  }
  return false;
}

// [from, to] tick 가운데 kind를 보낸 tick.
std::vector<std::uint64_t> ticks_sending(
  const Harness & h, CommandKind kind, std::uint64_t from, std::uint64_t to)
{
  std::vector<std::uint64_t> ticks;
  for (std::uint64_t tick = from; tick <= to && tick <= h.outputs().size(); ++tick) {
    if (has_command(h.outputs()[tick - 1], kind)) {
      ticks.push_back(tick);
    }
  }
  return ticks;
}

std::vector<CommandKind> commands_at(const Harness & h, std::uint64_t tick)
{
  const StepOutput * out = output_of_tick(h, tick);
  return out != nullptr ? out->commands : std::vector<CommandKind>{};
}

bool setpoint_at(const Harness & h, std::uint64_t tick)
{
  const StepOutput * out = output_of_tick(h, tick);
  return out != nullptr && out->setpoint.has_value();
}

bool terminated_at(const Harness & h, std::uint64_t tick)
{
  const StepOutput * out = output_of_tick(h, tick);
  return out != nullptr && out->termination.has_value();
}

// 종료 단계의 feedback: phase EXECUTING, item_index N-1(decisions.md 쟁점 10 feedback 문단).
void expect_end_feedback(const Harness & h, std::uint64_t s)
{
  const auto last = static_cast<std::uint32_t>(h.runner().mission().items.size() - 1);
  for (std::uint64_t tick = s; tick <= h.outputs().size(); ++tick) {
    const StepOutput & out = h.outputs()[tick - 1];
    if (!out.feedback.has_value()) {
      continue;
    }
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kExecuting) << "tick " << tick;
    EXPECT_EQ(out.feedback->item_index, last) << "tick " << tick;
    EXPECT_FALSE(out.feedback->distance_valid) << "tick " << tick;
  }
}

// 종료 결과: reason 열 표기, detail, items_completed N, last_item_index N-1, feedback, 불변식.
void expect_end(
  Harness & h, std::uint64_t s, const std::string & reason, const std::string & detail)
{
  ASSERT_TRUE(h.termination().has_value()) << "expected " << reason;
  const Termination term = *h.termination();
  const auto n = static_cast<std::uint32_t>(h.runner().mission().items.size());
  EXPECT_EQ(term.detail, detail);
  EXPECT_EQ(term.items_completed, n);
  EXPECT_EQ(term.last_item_index, n - 1);
  expect_end_feedback(h, s);
  expect_terminated_once_as(h, reason);
}

const char kNone[] = "CLEANUP.MISSION_END.NONE";
const char kAir[] = "CLEANUP.MISSION_END.AIR";
const char kAirLand[] = "CLEANUP.MISSION_END.AIR_LAND";
const char kGroundWait[] = "CLEANUP.MISSION_END.GROUND_WAIT";
const char kCapPrefix[] = "mission end: cleanup cap reached (12000 ms), last branch ";

// ---- 공중 Hold ----

TEST(MissionEnd, T1AirHoldConfirmed)
{
  Harness h(takeoff_loiter_mission());
  const EndStart st = start_air_end(h);
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, kNone, "-", {}, st.before);
  expect_cell(h, kNone, Event::kEnterAir, kAir, "-", {}, st.before);
  EXPECT_EQ(commands_at(h, st.s), std::vector<CommandKind>{CommandKind::kSetModeHold});
  EXPECT_TRUE(setpoint_at(h, st.s));
  EXPECT_EQ(h.view().items_completed, 2U);
  h.tick();  // S+1: AUTO_LOITER 표본
  EXPECT_FALSE(setpoint_at(h, st.s + 1));
  EXPECT_TRUE(commands_at(h, st.s + 1).empty());
  run_to(h, st.s + 3);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 3));
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 1);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
}

TEST(MissionEnd, T2TakeoffOnlyMission)
{
  Harness h(takeoff_only_mission());
  const EndStart st = start_air_takeoff_end(h);
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, kNone, "-", {}, st.before);
  expect_cell(h, kNone, Event::kEnterAir, kAir, "-", {}, st.before);
  EXPECT_EQ(commands_at(h, st.s), std::vector<CommandKind>{CommandKind::kSetModeHold});
  run_to(h, st.s + 4);
  EXPECT_TRUE(terminated_at(h, st.s + 3));
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
  EXPECT_EQ(h.termination()->items_completed, 1U);
  EXPECT_EQ(h.termination()->last_item_index, 0U);
}

TEST(MissionEnd, T3HoldResentAfterAcceptedAck)
{
  // 진행은 표본으로 하고 ack는 거부 판정에만 쓴다(쟁점 12). ACCEPTED ack로 재전송이 멈추지 않는다.
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 1);
  h.push_ack(AckCommand::kSetMode, AckResult::kAccepted);
  run_to(h, st.s + 60);
  const std::size_t before = tick_marked(h);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kSetModeHold, st.s, st.s + 60),
    (std::vector<std::uint64_t>{st.s, st.s + 10, st.s + 20, st.s + 30, st.s + 40, st.s + 50}));
  expect_cell(h, kAir, Event::kHoldTimeout, kAirLand, "-", {}, before);
}

TEST(MissionEnd, T4OneLostHoldIsResent)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.hold_response = HoldResponse::kAccept;
  run_to(h, st.s + 13);
  const std::size_t before = tick_marked(h);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kSetModeHold, st.s, st.s + 13),
    (std::vector<std::uint64_t>{st.s, st.s + 10}));
  expect_cell(h, kAir, Event::kHoldConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 13));
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
}

// ---- Hold 실패: Land 경로 ----

TEST(MissionEnd, T5AirRejectedThenLandObserved)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  const EndStart st = start_air_end(h);
  std::size_t before = tick_marked(h);  // S+1: 거부 ack
  expect_cell(h, kAir, Event::kHoldRejected, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 1), std::vector<CommandKind>{CommandKind::kNavLand});
  EXPECT_TRUE(setpoint_at(h, st.s + 1));
  EXPECT_TRUE(h.view().hold_failed);
  before = tick_marked(h);  // S+2: AUTO_LAND
  expect_cell(
    h, kAirLand, Event::kLandPathModeObserved, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_FALSE(setpoint_at(h, st.s + 2));
  expect_end(
    h, st.s, "ABORTED/MODE_SWITCH_FAILED",
    "mission end: Hold rejected: TEMPORARILY_REJECTED; Land sent, AUTO_LAND observed");
}

TEST(MissionEnd, T6LostRejectAckIsCaughtOnResend)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.hold_response = HoldResponse::kReject;
  run_to(h, st.s + 11);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldRejected, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 11), std::vector<CommandKind>{CommandKind::kNavLand});
  run_to(h, st.s + 13);
  expect_end(
    h, st.s, "ABORTED/MODE_SWITCH_FAILED",
    "mission end: Hold rejected: TEMPORARILY_REJECTED; Land sent, AUTO_LAND observed");
}

TEST(MissionEnd, T7AirTimeoutThenLandTimeout)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 60);
  std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 60), std::vector<CommandKind>{CommandKind::kNavLand});
  run_to(h, st.s + 120);
  before = tick_marked(h);
  expect_cell(
    h, kAirLand, Event::kLandPathTimeout, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kNavLand, st.s, st.s + 120),
    (std::vector<std::uint64_t>{
      st.s + 60, st.s + 70, st.s + 80, st.s + 90, st.s + 100, st.s + 110}));
  for (std::uint64_t tick = st.s; tick < st.s + 120; ++tick) {
    EXPECT_TRUE(setpoint_at(h, tick)) << "tick " << tick;
  }
  EXPECT_FALSE(setpoint_at(h, st.s + 120));
  expect_end(
    h, st.s, "ABORTED/MODE_SWITCH_FAILED",
    "mission end: Hold not confirmed within hold_confirm_timeout; Land sent, AUTO_LAND not "
    "confirmed");
}

// ---- 만료가 이긴다(쟁점 10 A2의 두 쌍) ----

TEST(MissionEnd, T8HoldTimeoutBeatsThirdHoldSample)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 58);
  h.world.nav = NavMode::kHold;  // S+58, S+59, S+60 공중 AUTO_LOITER
  run_to(h, st.s + 60);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 60), std::vector<CommandKind>{CommandKind::kNavLand});
  EXPECT_FALSE(terminated_at(h, st.s + 60));
  EXPECT_FALSE(has_edge(h, Event::kHoldConfirmed, st.before));
}

TEST(MissionEnd, T8ContrastThirdHoldSampleBeforeTimeout)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 57);
  h.world.nav = NavMode::kHold;
  run_to(h, st.s + 59);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
}

TEST(MissionEnd, T9CapBeatsThirdHoldSample)
{
  Harness h(takeoff_loiter_mission());
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 3);  // S+1, S+2 공중 AUTO_LOITER
  h.now_ns = st.s_ns + 12 * kNsPerSecond;
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(h.outputs().back().commands, std::vector<CommandKind>{CommandKind::kNavLand});
  EXPECT_FALSE(has_edge(h, Event::kHoldTimeout, st.before));
  EXPECT_FALSE(has_edge(h, Event::kHoldConfirmed, st.before));
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail.rfind(std::string(kCapPrefix) + "air (Hold)", 0), 0U) << detail;
  EXPECT_NE(
    detail.find("; Hold was observed and publishing stopped, vehicle stays in Hold if NAV_LAND is "
                "lost"),
    std::string::npos)
    << detail;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

// ---- 지상 대기 ----

TEST(MissionEnd, T10GroundEndWithFallbackDisarm)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = start_ground_end(h);
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, kNone, "-", {}, st.before);
  expect_cell(h, kNone, Event::kEnterAir, kAir, "-", {}, st.before);
  EXPECT_EQ(commands_at(h, st.s), std::vector<CommandKind>{CommandKind::kSetModeHold});
  h.tick();  // S+1: AUTO_LOITER landed true
  EXPECT_FALSE(setpoint_at(h, st.s + 1));
  run_to(h, st.s + 60);
  std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kGroundWait, "-", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 60).empty());
  run_to(h, st.s + 160);
  h.tick();
  EXPECT_EQ(commands_at(h, st.s + 160), std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_TRUE(ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 159).empty());
  h.tick();  // S+161: DISARMED 표본, 대기 명령 지움
  EXPECT_FALSE(h.view().pending_active);
  run_to(h, st.s + 163);
  before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 163));
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 6);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 1);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T11AutoDisarmWhileWaitingForHold)
{
  Harness h(takeoff_loiter_mission());
  h.drive_to_loiter();
  const std::uint64_t s = h.tick_no - 1 + kLoiterTicks;
  run_to(h, s);
  h.world.landed = true;  // S에 착지(이륙 이력 있음)
  const std::size_t start = tick_marked(h);
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, kNone, "-", {}, start);
  run_to(h, s + 20);
  h.world.arming = Arming::kDisarmed;  // S+20부터 PX4 자동 disarm 흉내
  h.tick();                            // S+20: 첫 지상 DISARMED, 대기 명령 지움
  EXPECT_FALSE(h.view().pending_active);
  run_to(h, s + 22);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kSetModeHold, s, s + 22),
    (std::vector<std::uint64_t>{s, s + 10}));
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  expect_end(h, s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T12GroundRejectThenAirReentry)
{
  Harness h(takeoff_only_mission(0.2));
  h.hold_response = HoldResponse::kReject;
  const EndStart st = start_ground_end(h);
  std::size_t before = tick_marked(h);  // S+1
  expect_cell(h, kAir, Event::kHoldRejected, kGroundWait, "-", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 1).empty());
  const StepOutput * out = output_of_tick(h, st.s + 1);
  ASSERT_NE(out, nullptr);
  ASSERT_TRUE(out->setpoint.has_value());
  EXPECT_EQ(out->setpoint->kind, SetpointKind::kGround);
  EXPECT_EQ(out->setpoint->x, h.world.x);
  EXPECT_EQ(out->setpoint->y, h.world.y);
  run_to(h, st.s + 5);
  for (std::uint64_t tick = st.s + 2; tick <= st.s + 4; ++tick) {
    const StepOutput * o = output_of_tick(h, tick);
    ASSERT_NE(o, nullptr);
    ASSERT_TRUE(o->setpoint.has_value()) << "tick " << tick;
    EXPECT_EQ(o->setpoint->kind, SetpointKind::kGround) << "tick " << tick;
  }
  h.world.landed = false;  // S+5: ARMED OFFBOARD landed false
  before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kEnterAir, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 5), std::vector<CommandKind>{CommandKind::kNavLand});
  ASSERT_TRUE(h.outputs().back().setpoint.has_value());
  EXPECT_EQ(h.outputs().back().setpoint->kind, SetpointKind::kGround);
  before = tick_marked(h);  // S+6: AUTO_LAND
  expect_cell(
    h, kAirLand, Event::kLandPathModeObserved, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  expect_end(
    h, st.s, "ABORTED/MODE_SWITCH_FAILED",
    "mission end: Hold rejected: TEMPORARILY_REJECTED; air re-entered after Hold failure; Land "
    "sent, AUTO_LAND observed");
}

// T10 경로(지상 Hold 수락, Hold 기한으로 지상 대기)를 S+160 직전까지. disarm 반응은 끈다.
EndStart drive_ground_wait(Harness & h, std::uint64_t until_offset)
{
  h.disarm_response = CommandResponse::kIgnore;
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + until_offset);
  return st;
}

TEST(MissionEnd, T13FallbackFailsAndCapEnds)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 161);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kAccepted);
  run_to(h, st.s + 171);
  h.push_ack(AckCommand::kArmDisarm, AckResult::kTemporarilyRejected);
  run_to(h, st.s + 240);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 239),
    (std::vector<std::uint64_t>{
      st.s + 160, st.s + 170, st.s + 180, st.s + 190, st.s + 200, st.s + 210, st.s + 220,
      st.s + 230}));
  EXPECT_EQ(commands_at(h, st.s + 240), std::vector<CommandKind>{CommandKind::kDisarm});
  expect_end(
    h, st.s, "ABORTED/MODE_SWITCH_FAILED",
    std::string(kCapPrefix) +
      "ground (wait for disarm); disarm sent once, not confirmed; vehicle may remain armed on "
      "ground");
}

TEST(MissionEnd, T14CapBeatsThirdGroundDisarmed)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 238);
  h.world.arming = Arming::kDisarmed;  // S+238, S+239, S+240
  run_to(h, st.s + 240);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 240), std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_FALSE(has_edge(h, Event::kGroundDisarmConfirmed, st.before));
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(MissionEnd, T14ContrastThirdGroundDisarmedBeforeCap)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 237);
  h.world.arming = Arming::kDisarmed;  // S+237, S+238, S+239
  run_to(h, st.s + 239);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T15GroundDisarmedOnHoldTimeoutTick)
{
  // 규칙 R: 분류가 지상인 tick은 hold_confirm_timeout을 보지 않는다(쟁점 10 A2).
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + 58);
  h.world.arming = Arming::kDisarmed;  // S+58, S+59, S+60 DISARMED landed
  h.tick();
  EXPECT_FALSE(h.view().pending_active);
  run_to(h, st.s + 60);
  const std::size_t before = tick_marked(h);
  ASSERT_EQ(h.edges().size(), before + 1);
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_FALSE(has_edge(h, Event::kHoldTimeout, st.before));
  EXPECT_TRUE(commands_at(h, st.s + 60).empty());
  EXPECT_FALSE(setpoint_at(h, st.s + 60));
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T16LandPathCapInAir)
{
  Harness h(takeoff_only_mission(0.2));
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = drive_ground_wait(h, 235);
  h.world.landed = false;  // S+235: ARMED landed false
  std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kEnterAir, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 235), std::vector<CommandKind>{CommandKind::kNavLand});
  run_to(h, st.s + 240);
  before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 240), std::vector<CommandKind>{CommandKind::kNavLand});
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail.rfind(std::string(kCapPrefix) + "air (Land path)", 0), 0U) << detail;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(MissionEnd, T16ContrastLandPathCapOnGround)
{
  Harness h(takeoff_only_mission(0.2));
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = drive_ground_wait(h, 235);
  h.world.landed = false;
  run_to(h, st.s + 237);
  h.world.landed = true;  // S+237부터 ARMED landed true
  run_to(h, st.s + 240);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 240), std::vector<CommandKind>{CommandKind::kDisarm});
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail.rfind(std::string(kCapPrefix) + "air (Land path)", 0), 0U) << detail;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(MissionEnd, T17aLandPathGroundDisarmed)
{
  // 쟁점 10 A1: Land 경로에서 AUTO_LAND를 보기 전에 지상 DISARMED 3회면 SUCCEEDED.
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 3);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+3, S+4, S+5
  run_to(h, st.s + 5);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kNavLand, st.s, st.s + 5), std::vector<std::uint64_t>{st.s + 1});
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T17aWaitingCommandIsClearedOnFirstGroundDisarmed)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 3);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  h.tick();  // S+3
  EXPECT_FALSE(h.view().pending_active);
  h.world.arming = Arming::kArmed;  // 쟁점 11의 전제 밖: 다시 ARMED. 지운 재전송은 되살리지 않는다
  run_to(h, st.s + 12);
  EXPECT_TRUE(ticks_sending(h, CommandKind::kNavLand, st.s + 2, st.s + 11).empty());
}

TEST(MissionEnd, T17bLandPathGroundDisarmedOnLandTimeoutTick)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 59);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+59, S+60, S+61(Land 경로 기한 tick)
  h.tick();
  EXPECT_FALSE(h.view().pending_active);
  run_to(h, st.s + 61);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_FALSE(has_edge(h, Event::kLandPathTimeout, st.before));
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

// ---- 상태 끊김 ----

TEST(MissionEnd, T18aLinkLostInAir)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.auto_samples = false;  // S 뒤 표본 없음
  run_to(h, st.s + 40);
  EXPECT_FALSE(h.runner().done());
  const std::size_t before = tick_marked(h);  // S+40
  expect_cell(h, kAir, Event::kCleanupLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 40).empty());
  expect_end(h, st.s, "ABORTED/LINK_LOST", "mission end: vehicle_status lost");
}

TEST(MissionEnd, T18bLinkLostOnLandPath)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.tick();  // S+1: Land 경로
  h.auto_samples = false;
  run_to(h, st.s + 41);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kCleanupLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 41).empty());
  expect_end(h, st.s, "ABORTED/LINK_LOST", "mission end: vehicle_status lost");
}

TEST(MissionEnd, T18cLinkLostInGroundWaitBeforeFallback)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 61);
  h.auto_samples = false;  // 마지막 신뢰 표본 S+60
  run_to(h, st.s + 100);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kCleanupLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 100).empty());
  expect_end(h, st.s, "ABORTED/LINK_LOST", "mission end: vehicle_status lost");
}

TEST(MissionEnd, T18dLinkLostInGroundWaitAfterFallback)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 161);
  h.auto_samples = false;  // 마지막 신뢰 표본 S+160
  run_to(h, st.s + 200);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kCleanupLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 200), std::vector<CommandKind>{CommandKind::kDisarm});
  expect_end(
    h, st.s, "ABORTED/LINK_LOST",
    "mission end: vehicle_status lost during ground wait; disarm sent once, not confirmed; vehicle "
    "may remain armed on ground");
}

// ---- 공중 DISARMED ----

void expect_air_disarm(Harness & h, const EndStart & st, const std::string & from)
{
  h.world.arming = Arming::kDisarmed;
  h.world.landed = false;
  const std::size_t before = tick_marked(h);
  expect_cell(h, from, Event::kCleanupAirDisarm, "DONE", "ABORTED/FAILSAFE", {}, before);
  EXPECT_TRUE(h.outputs().back().commands.empty());
  expect_end(h, st.s, "ABORTED/FAILSAFE", "mission end: disarmed while not landed");
}

TEST(MissionEnd, T19AirDisarmInAir)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  expect_air_disarm(h, st, kAir);
}

TEST(MissionEnd, T19AirDisarmOnLandPath)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.tick();
  expect_air_disarm(h, st, kAirLand);
}

TEST(MissionEnd, T19AirDisarmInGroundWait)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 61);
  expect_air_disarm(h, st, kGroundWait);
}

// ---- Px4Timestamp 실패 ----

const char kStampDetail[] =
  "mission end: Px4Timestamp unavailable; vehicle state unknown, may remain armed on ground";

TEST(MissionEnd, T20StampFailureInAir)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.clock.fail = true;  // S+1: 발행 tick
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 1).empty());
  EXPECT_FALSE(setpoint_at(h, st.s + 1));
  h.clock.fail = false;
  expect_end(h, st.s, "ABORTED/INTERNAL", kStampDetail);
}

TEST(MissionEnd, T20StampFailureOnLandPath)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 11);
  h.clock.fail = true;  // S+11: NAV_LAND 재전송 tick
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 11).empty());
  h.clock.fail = false;
  expect_end(h, st.s, "ABORTED/INTERNAL", kStampDetail);
}

TEST(MissionEnd, T20StampFailureInGroundWait)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 170);
  h.clock.fail = true;  // S+170: 대비책 재전송 tick
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 170).empty());
  h.clock.fail = false;
  expect_end(h, st.s, "ABORTED/INTERNAL", kStampDetail);
}

TEST(MissionEnd, T20StampFailureOnFirstTickIsMonitorRow)
{
  // 첫 tick(S)은 감시 표가 같은 tick에 먼저 시각을 묻는다
  // (CLEANUP.MISSION_END.NONE STAMP_UNAVAILABLE impossible의 근거).
  Harness h(takeoff_loiter_mission());
  h.drive_to_loiter();
  const std::uint64_t s = h.tick_no - 1 + kLoiterTicks;
  run_to(h, s);
  h.clock.fail = true;
  const std::size_t before = tick_marked(h);
  expect_cell(
    h, "ITEM.LOITER", Event::kMonitorTimestampFailure, "DONE", "ABORTED/INTERNAL",
    {Event::kLoiterElapsed}, before);
  EXPECT_FALSE(has_edge(h, Event::kEnterAir, before));
  h.clock.fail = false;
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
}

// ---- 취소 ----

void expect_cancel_ignored(Harness & h, const EndStart & st)
{
  run_to(h, st.s + 4);
  EXPECT_TRUE(terminated_at(h, st.s + 3));
  EXPECT_FALSE(has_edge(h, Event::kCancel, st.before));
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
}

TEST(MissionEnd, T21aCancelOnLoiterCompletionTick)
{
  Harness h(takeoff_loiter_mission());
  h.drive_to_loiter();
  const std::uint64_t s = h.tick_no - 1 + kLoiterTicks;
  run_to(h, s);
  h.cancel_sticky = true;  // S부터 계속 취소
  EndStart st;
  st.s = s;
  st.before = h.edges().size();
  h.tick();
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, kNone, "-", {Event::kCancel}, st.before);
  expect_cancel_ignored(h, st);
}

TEST(MissionEnd, T21bCancelOnTakeoffReachedTick)
{
  Harness h(takeoff_only_mission());
  const EndStart st = start_air_takeoff_end(h, true);
  h.cancel_sticky = true;
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, kNone, "-", {Event::kCancel}, st.before);
  expect_cancel_ignored(h, st);
}

TEST(MissionEnd, T21cCancelDuringMissionEnd)
{
  Harness h(takeoff_loiter_mission());
  const EndStart st = start_air_end(h);
  h.tick();
  h.cancel_sticky = true;  // S+2부터
  expect_cancel_ignored(h, st);
}

// ---- 마지막 항목의 겹침(기존 칸) ----

TEST(MissionEnd, T22aLastLoiterCompletionAndItemTimeout)
{
  Harness h(takeoff_loiter_mission());
  h.drive_to_loiter();
  const std::int64_t loiter_start_ns = h.now_ns - kTickNs;
  h.now_ns = loiter_start_ns + 10 * kNsPerSecond;  // LOITER timeout 10 s, duration 5 s
  const std::size_t before = tick_marked(h);
  expect_cell(
    h, "ITEM.LOITER", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
    {Event::kLoiterElapsed}, before);
  h.run_until([&h] { return h.runner().done(); }, 600);
  for (const TransitionEdge & edge : h.edges()) {
    EXPECT_NE(edge.to.cause, CleanupCause::kMissionEnd) << state_key_name(edge.to);
  }
  EXPECT_EQ(termination_or_empty(h).reason, Reason::kItemTimeout);
}

TEST(MissionEnd, T22bLastTakeoffReachedAndExternalMode)
{
  Harness h(takeoff_only_mission());
  h.drive_to_takeoff();
  h.auto_px4 = false;
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  const std::size_t before = tick_marked(h);
  expect_cell(
    h, "ITEM.TAKEOFF", Event::kMonitorModeExternal, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
    {Event::kTakeoffReached}, before);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  expect_terminated_once_as(h, "ABORTED/EXTERNAL_MODE_CHANGE");
}

// ---- 식별 불일치 ----

TEST(MissionEnd, T23aMismatchedHoldSamplesAreNotCounted)
{
  Harness h(takeoff_loiter_mission());
  const EndStart st = start_air_end(h);
  h.world.identity = IdentityCheck::kMismatch;  // S+1..S+3: 식별 불일치 AUTO_LOITER
  run_to(h, st.s + 4);
  EXPECT_FALSE(h.runner().done());
  h.world.identity = IdentityCheck::kMatch;  // S+4..S+6
  run_to(h, st.s + 6);
  EXPECT_FALSE(h.runner().done());
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "");
}

TEST(MissionEnd, T23bMismatchedAirSampleInGroundWaitDoesNotReenterAir)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 61);
  h.world.identity = IdentityCheck::kMismatch;
  h.world.landed = false;
  const std::size_t before = tick_marked(h);  // S+61
  EXPECT_FALSE(has_edge(h, Event::kEnterAir, before));
  EXPECT_TRUE(commands_at(h, st.s + 61).empty());
  EXPECT_FALSE(h.runner().done());
  EXPECT_EQ(h.view().branch, Branch::kGroundWait);
}

TEST(MissionEnd, T23cOnlyMismatchedSamplesInAir)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.world.identity = IdentityCheck::kMismatch;  // S+1부터
  run_to(h, st.s + 60);
  EXPECT_FALSE(has_edge(h, Event::kCleanupLinkLost, st.before));
  std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kAirLand, "-", {}, before);
  run_to(h, st.s + 120);
  before = tick_marked(h);
  expect_cell(
    h, kAirLand, Event::kLandPathTimeout, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_FALSE(has_edge(h, Event::kCleanupLinkLost, st.before));
  h.world.identity = IdentityCheck::kMatch;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(MissionEnd, T23dMismatchedTicksKeepFallbackBase)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_ground_wait(h, 100);
  h.world.identity = IdentityCheck::kMismatch;  // S+100..S+102
  run_to(h, st.s + 103);
  h.world.identity = IdentityCheck::kMatch;
  run_to(h, st.s + 160);
  h.world.identity = IdentityCheck::kMismatch;  // S+160
  h.tick();
  h.world.identity = IdentityCheck::kMatch;
  h.tick();  // S+161
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 161),
    std::vector<std::uint64_t>{st.s + 161});
}

TEST(MissionEnd, T23eMismatchWhileClassifiedGround)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 8);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+8, S+9
  run_to(h, st.s + 10);
  h.world.identity = IdentityCheck::kMismatch;  // S+10: Hold 재전송 예정 tick
  h.tick();
  EXPECT_FALSE(terminated_at(h, st.s + 10));
  EXPECT_TRUE(commands_at(h, st.s + 10).empty());
  h.world.identity = IdentityCheck::kMatch;  // S+11
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

// ---- 묵은 표본 ----

TEST(MissionEnd, T24aStaleDisarmedSampleIsIgnored)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.tick();  // S+1
  const RunnerView v = h.view();
  Sample stale = disarmed(true);
  stale.timestamp_us = 1;  // 첫 ARMED 표본보다 작다
  h.feed({stale});
  EXPECT_FALSE(terminated_at(h, st.s + 2));
  EXPECT_EQ(h.view().publishing, v.publishing);
  EXPECT_EQ(h.view().pending_active, v.pending_active);
  EXPECT_EQ(h.view().disarm_class, DisarmClass::kUnknown);
  EXPECT_TRUE(setpoint_at(h, st.s + 2));
}

TEST(MissionEnd, T24bStaleSampleDoesNotCount)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 5);
  Sample stale = disarmed(true);
  stale.timestamp_us = 1;
  h.feed({disarmed(true), disarmed(true), stale});  // S+5, S+6, S+7
  EXPECT_FALSE(terminated_at(h, st.s + 7));
  const std::size_t before = h.edges().size();
  h.feed({disarmed(true)});  // S+8
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T25LastLoiterAutoDisarmBeforeCompletion)
{
  // 지면 높이 마지막 목표에서 착지와 PX4 자동 disarm이 완료보다 먼저면 감시 표 순위 5다.
  Harness h(takeoff_loiter_mission());
  h.drive_to_loiter();
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  const std::size_t before = tick_marked(h);
  expect_cell(
    h, "ITEM.LOITER", Event::kMonitorDisarmedOnGround, "DONE", "ABORTED/EXTERNAL_DISARM", {},
    before);
  for (const TransitionEdge & edge : h.edges()) {
    EXPECT_NE(edge.to.cause, CleanupCause::kMissionEnd) << state_key_name(edge.to);
  }
  expect_terminated_once_as(h, "ABORTED/EXTERNAL_DISARM");
}

// ---- 규칙 R(분류 지상 동안의 분기 판정. 쟁점 10 A2) ----

TEST(MissionEnd, T26DisarmedAutoLandSamplesAreNotLandObserved)
{
  // ARMED AUTO_LAND 표본이면 Y9(LAND_PATH_MODE_OBSERVED)가 되는 대조는 T5가 덮는다.
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kReject;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 3);
  const std::size_t before = h.edges().size();
  h.feed({disarmed(true, NavMode::kLand), disarmed(true, NavMode::kLand)});  // S+3, S+4
  EXPECT_FALSE(has_edge(h, Event::kLandPathModeObserved, before));
  EXPECT_FALSE(h.runner().done());
  h.feed({disarmed(true, NavMode::kLand)});  // S+5
  expect_cell(h, kAirLand, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T27aGroundDisarmedAcrossHoldTimeout)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 59);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+59, S+60, S+61
  run_to(h, st.s + 61);
  EXPECT_FALSE(has_edge(h, Event::kHoldTimeout, st.before));
  EXPECT_FALSE(terminated_at(h, st.s + 60));
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T27bGroundDisarmedAcrossLandTimeoutThenLinkLost)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 119);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+119, S+120(Land 경로 기한)
  run_to(h, st.s + 121);
  EXPECT_FALSE(has_edge(h, Event::kLandPathTimeout, st.before));
  h.auto_samples = false;  // 마지막 신뢰 표본 S+120
  run_to(h, st.s + 160);
  EXPECT_FALSE(h.runner().done());
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAirLand, Event::kCleanupLinkLost, "DONE", "ABORTED/LINK_LOST", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 160).empty());
  expect_terminated_once_as(h, "ABORTED/LINK_LOST");
}

TEST(MissionEnd, T27cCapWhileClassifiedGroundSendsDisarm)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  run_to(h, st.s + 59);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+59, S+60
  run_to(h, st.s + 61);
  h.now_ns = st.s_ns + 12 * kNsPerSecond;
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(h.outputs().back().commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_FALSE(has_edge(h, Event::kGroundDisarmConfirmed, st.before));
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail.rfind(std::string(kCapPrefix) + "air (Hold)", 0), 0U) << detail;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(MissionEnd, T28aRejectAckWhileClassifiedGroundIsDropped)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + 5);
  h.world.arming = Arming::kDisarmed;  // S+5, S+6, S+7
  h.tick();
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);  // S+6
  const std::size_t at6 = tick_marked(h);
  EXPECT_FALSE(has_edge(h, Event::kHoldRejected, at6));
  EXPECT_TRUE(commands_at(h, st.s + 6).empty());
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, T28bDroppedAckAndClearedHoldStayGoneAfterRearm)
{
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + 5);
  h.world.arming = Arming::kDisarmed;  // S+5, S+6
  h.tick();
  h.push_ack(AckCommand::kSetMode, AckResult::kTemporarilyRejected);  // S+6
  h.tick();
  h.world.arming = Arming::kArmed;  // S+7부터 ARMED landed AUTO_LOITER
  run_to(h, st.s + 60);
  EXPECT_FALSE(has_edge(h, Event::kHoldRejected, st.before));
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kGroundWait, "-", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 60).empty());
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 1);
}

TEST(MissionEnd, T29CapOnMismatchedTickWhileClassifiedGround)
{
  Harness h(takeoff_loiter_mission());
  h.hold_response = HoldResponse::kIgnore;
  const EndStart st = start_air_end(h);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+1, S+2
  run_to(h, st.s + 3);
  h.world.identity = IdentityCheck::kMismatch;
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.now_ns = st.s_ns + 12 * kNsPerSecond;
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kCleanupCap, "DONE", "ABORTED/MODE_SWITCH_FAILED", {}, before);
  EXPECT_EQ(h.outputs().back().commands, std::vector<CommandKind>{CommandKind::kDisarm});
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail.rfind(std::string(kCapPrefix) + "air (Hold)", 0), 0U) << detail;
  h.world.identity = IdentityCheck::kMatch;
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

// ---- 지상 대기의 대비책 기준 시각과 확인 함수(B9 S3 최종 검토 보강) ----
// 칸 명세 2.2(지상 DISARMED 계수, 규칙 R), 2.3 순서 3과 끝 문단(이어짐 갱신, 진입 tick의 관측), D7,
// D12. 칸은 기존 칸(A13r, G8, G10, Y11)만 쓴다.

// T10 경로(지상 Hold 수락, Hold 기한으로 S+60에 지상 대기)를 S+60까지 돈다.
// drive_ground_wait와 달리 S+60 tick까지 실행해 A13r를 단정하고, disarm 반응을 끄지 않는다.
EndStart drive_into_ground_wait(Harness & h)
{
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + 60);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kGroundWait, "-", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 60).empty());
  return st;
}

TEST(MissionEnd, GroundDisarmedSamplesRestartFallbackBase)
{
  // 지상 대기 중 지상 DISARMED 표본이 ARMED, landed의 이어짐을 끊는다(순서 3, D12). S+100, S+101의
  // 지상 DISARMED 2회는 3회 전이라 끝나지 않고, S+102의 ARMED가 분류를 미정으로 되돌리며 계수를
  // 0으로 만든다(규칙 R). 대비책의 기준은 S+60이 아니라 S+102이고 disarm은 S+202에 나간다.
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_into_ground_wait(h);
  run_to(h, st.s + 100);
  h.world.arming = Arming::kDisarmed;  // S+100, S+101 지상 DISARMED
  h.tick();
  EXPECT_EQ(h.view().disarm_class, DisarmClass::kGround);
  h.tick();
  EXPECT_FALSE(terminated_at(h, st.s + 100));
  EXPECT_FALSE(terminated_at(h, st.s + 101));
  EXPECT_FALSE(h.runner().done());
  h.world.arming = Arming::kArmed;  // S+102부터 ARMED landed(쟁점 11의 전제 밖)
  h.tick();
  EXPECT_EQ(h.view().disarm_class, DisarmClass::kUnknown);
  EXPECT_EQ(h.view().branch, Branch::kGroundWait);
  EXPECT_FALSE(h.runner().done());
  run_to(h, st.s + 202);
  h.tick();
  EXPECT_TRUE(ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 201).empty());
  EXPECT_EQ(commands_at(h, st.s + 202), std::vector<CommandKind>{CommandKind::kDisarm});
  // 대비책 뒤의 지상 DISARMED는 전송 tick(S+202)보다 뒤의 S+203, S+204, S+205로 센다.
  run_to(h, st.s + 205);
  const std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 205));
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 1);
  EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, GroundDisarmedCountRestartsAfterArmed)
{
  // 규칙 R: 분류 지상 뒤 ARMED가 다시 오면 지상 DISARMED 계수는 0이다. S+100, S+101, S+103의
  // 지상 DISARMED는 이어진 3회가 아니라 끝나지 않는다. 이어짐은 S+103에 다시 끊기고 S+104가
  // 기준이다.
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = drive_into_ground_wait(h);
  run_to(h, st.s + 100);
  h.world.arming = Arming::kDisarmed;  // S+100, S+101
  run_to(h, st.s + 102);
  h.world.arming = Arming::kArmed;  // S+102
  h.tick();
  EXPECT_EQ(h.view().disarm_class, DisarmClass::kUnknown);
  h.world.arming = Arming::kDisarmed;  // S+103
  h.tick();
  EXPECT_EQ(h.view().disarm_class, DisarmClass::kGround);
  EXPECT_FALSE(terminated_at(h, st.s + 103));
  EXPECT_FALSE(h.runner().done());
  h.world.arming = Arming::kArmed;  // S+104부터
  run_to(h, st.s + 205);
  EXPECT_FALSE(has_edge(h, Event::kGroundDisarmConfirmed, st.before));
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 204),
    std::vector<std::uint64_t>{st.s + 204});
  EXPECT_FALSE(h.runner().done());
}

TEST(MissionEnd, FallbackDisarmConfirmKeptOnLandPath)
{
  // 쟁점 10: 대비책 disarm을 보낸 뒤 Land 경로로 옮겨도 확인 함수(DisarmConfirm)로 센다(2.2, D7).
  // S+160 대비책 disarm(무시), S+162 G8, S+165-S+167 지상 DISARMED. 세는 표본은 모두 전송 tick보다
  // 뒤 tick의 것이다.
  Harness h(takeoff_only_mission(0.2));
  h.land_response = CommandResponse::kIgnore;
  const EndStart st = drive_ground_wait(h, 160);
  h.tick();  // S+160
  EXPECT_EQ(commands_at(h, st.s + 160), std::vector<CommandKind>{CommandKind::kDisarm});
  run_to(h, st.s + 162);
  h.world.landed = false;  // S+162: ARMED landed false
  std::size_t before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kEnterAir, kAirLand, "-", {}, before);
  EXPECT_EQ(commands_at(h, st.s + 162), std::vector<CommandKind>{CommandKind::kNavLand});
  run_to(h, st.s + 165);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;  // S+165, S+166, S+167
  h.tick();
  EXPECT_FALSE(h.view().pending_active);
  h.tick();
  EXPECT_FALSE(h.runner().done());
  before = tick_marked(h);  // S+167
  expect_cell(h, kAirLand, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 167));
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 167),
    std::vector<std::uint64_t>{st.s + 160});
  EXPECT_EQ(
    ticks_sending(h, CommandKind::kNavLand, st.s, st.s + 167),
    std::vector<std::uint64_t>{st.s + 162});
  EXPECT_FALSE(has_edge(h, Event::kLandPathTimeout, st.before));
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

TEST(MissionEnd, GroundWaitEnteredOnMismatchedTick)
{
  // D12: 지상 대기에 들어간 tick이 식별 불일치면 그 tick에 관측하지 않고, 다음 식별이 맞는
  // ARMED, landed tick이 대비책 기준이다. 진입은 AIR의 hold_confirm_timeout(표본이 필요 없는 판정,
  // 2.3 순서 2와 7)이고 그 tick의 최신 landed가 true라 지상 대기로 간다.
  Harness h(takeoff_only_mission(0.2));
  const EndStart st = start_ground_end(h);
  run_to(h, st.s + 60);
  h.world.identity = IdentityCheck::kMismatch;  // S+60: 식별 불일치 ARMED landed
  std::size_t before = tick_marked(h);
  expect_cell(h, kAir, Event::kHoldTimeout, kGroundWait, "-", {}, before);
  EXPECT_TRUE(commands_at(h, st.s + 60).empty());
  h.world.identity = IdentityCheck::kMatch;  // S+61부터: 기준 S+61
  run_to(h, st.s + 161);
  h.tick();
  EXPECT_TRUE(ticks_sending(h, CommandKind::kDisarm, st.s, st.s + 160).empty());
  EXPECT_EQ(commands_at(h, st.s + 161), std::vector<CommandKind>{CommandKind::kDisarm});
  run_to(h, st.s + 164);
  before = tick_marked(h);
  expect_cell(h, kGroundWait, Event::kGroundDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {}, before);
  EXPECT_TRUE(terminated_at(h, st.s + 164));
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 1);
  expect_end(h, st.s, "SUCCEEDED/NONE", "ended on ground");
}

}  // namespace
}  // namespace idsim_mission::core::test
