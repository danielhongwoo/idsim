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

// step()의 FramePort와 GOTO 항목(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 8, 12).
//
// - FramePort 호출 규율: 1a type 미션(TAKEOFF, LOITER, LAND, RTL)은 FramePort를 부르지 않는다
//   (decisions.md 쟁점 12). harness의 기본 port(kFail)가 모든 runner 사례에서 이를 함께 단정하고,
//   여기서는 진입 방식과 끝나는 길마다 한 번씩 끝까지 돌려 호출 수 0을 직접 단정한다.
// - GOTO 항목: 칸은 transition_cells.tsv의 ITEM.GOTO 행과 GOTO로 들어오는 세 행이다. 기호: K는 GOTO
//   항목을 시작한 tick(지상 진입은 TAKEOFF_REACHED tick), K+n은 그 뒤 n번째 tick, C는 공중 Offboard
//   진입의 OFFBOARD 3회 확인 tick(harness 기본값에서 14)이다.
// - port는 kAxis(world ENU -> 로컬 NED 축 치환, 원점 이동 없음)가 기본이고 사례가 바꾸는 것만
//   적는다. goto_item() 기본값은 world (10, 20, 5)라 로컬 L = (20, 10, -5), 반경 0.5 m, timeout
//   10 s(200 tick), MODE_KEEP이다. 둘째 GOTO는 world (0, 0, 5), L = (0, 0, -5).
// - 지상 진입은 [TAKEOFF(5 m, MODE_KEEP), GOTO, ...]이고 TAKEOFF 목표점은 (1, 2, -5), yaw 0.25다.
//   공중 진입은 start_in_air()(위치 (1, 2, -5), heading 0.25)다. 위치 표본은 tick마다 새
//   timestamp이고 xy_valid, z_valid는 true다(사례가 바꾸는 것만 적는다).

#include <gtest/gtest.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

void land_and_disarm(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 20));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
}

void expect_no_frame_calls(const Harness & h)
{
  EXPECT_TRUE(h.frame.point_calls.empty());
  EXPECT_EQ(h.frame.vector_calls, 0);
}

MissionSpec mission_of(const std::string & id, std::vector<ItemSpec> items)
{
  MissionSpec m;
  m.mission_id = id;
  m.items = std::move(items);
  return m;
}

// ---- FramePort 호출 규율(1a type 미션) ----

TEST(FramePortCalls, OneATypeMissionsNeverCallFramePort)
{
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND]");
    Harness h(standard_mission());
    h.drive_to_land();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LAND]");
    Harness h(land_only_mission());
    h.start_in_air();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER] (mission end)");
    Harness h(mission_of("tl", {takeoff_item(), loiter_item()}));
    h.drive_to_loiter();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 200));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[RTL]");
    Harness h(rtl_only_mission());
    h.start_in_air();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, RTL]");
    Harness h(mission_of("tr", {takeoff_item(), rtl_item()}));
    h.drive_to_takeoff();
    h.world.landed = false;
    h.world.z = h.view().setpoint.z;
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 100));
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LOITER] (air offboard entry)");
    Harness h(air_loiter_mission());
    h.start_in_air();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 400));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LOITER, LAND] (air offboard entry)");
    Harness h(air_loiter_land_mission());
    h.start_in_air();
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 400));
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND] cancel in LOITER");
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.cancel_sticky = true;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "CANCELED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND] TAKEOFF ITEM_TIMEOUT");
    Harness h(standard_mission());
    h.drive_to_takeoff();
    h.world.landed = false;
    h.world.z = -1.0;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 600));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
  }
}

// ---- GOTO 공통 ----

constexpr double kPi = 3.14159265358979323846;
constexpr std::uint64_t kTimeoutTicks = 200;   // goto_item() timeout 10 s
constexpr std::uint64_t kAirConfirmTick = 14;  // 공중 진입의 C(harness 기본값)
const Vec3 kSecondWorld{0.0, 0.0, 5.0};

const std::vector<CommandKind> kNoCommands = {};
const std::vector<CommandKind> kHoldOnly = {CommandKind::kSetModeHold};
const std::vector<CommandKind> kLandOnly = {CommandKind::kNavLand};
const std::vector<CommandKind> kDisarmOnly = {CommandKind::kDisarm};

double distance_l() { return std::sqrt(425.0); }  // (1, 2, -5)에서 L까지

const StepOutput & out_at(const Harness & h, std::uint64_t tick)
{
  static const StepOutput empty;
  const StepOutput * const out = output_of_tick(h, tick);
  return out != nullptr ? *out : empty;
}

void move_to(Harness & h, double x, double y, double z)
{
  h.world.x = x;
  h.world.y = y;
  h.world.z = z;
}

void at_target(Harness & h) { move_to(h, 20.0, 10.0, -5.0); }

void expect_setpoint(
  const StepOutput & out, double x, double y, double z, double yaw, const std::string & where)
{
  ASSERT_TRUE(out.setpoint.has_value()) << where;
  EXPECT_EQ(out.setpoint->kind, SetpointKind::kTarget) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->x, x) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->y, y) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->z, z) << where;
  EXPECT_NEAR(out.setpoint->yaw_ned, yaw, 1e-12) << where;
  EXPECT_FALSE(out.setpoint->velocity_valid) << where;
}

void expect_distance(const StepOutput & out, std::optional<double> distance, const std::string & w)
{
  ASSERT_TRUE(out.feedback.has_value()) << w;
  EXPECT_EQ(out.feedback->distance_valid, distance.has_value()) << w;
  if (distance.has_value()) {
    EXPECT_NEAR(out.feedback->distance_remaining_m, *distance, 1e-9) << w;
  }
}

// 지상 진입: TAKEOFF가 시작된 뒤 목표 고도에 둔다. 다음 tick이 K(TAKEOFF_REACHED)다. K를 돌려준다.
std::uint64_t prepare_goto_start(Harness & h)
{
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -5.0;
  EXPECT_TRUE(h.frame.point_calls.empty());
  return h.tick_no;
}

// K tick을 돌리고 TAKEOFF -> GOTO 칸을 단정한다.
void tick_goto_start(Harness & h, std::uint64_t k)
{
  const std::size_t before = h.edges().size();
  h.tick();
  EXPECT_EQ(h.tick_no - 1, k);
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, "ITEM.GOTO", "-", {}, before);
  EXPECT_EQ(h.view().item_index, 1U);
}

std::uint64_t start_goto(Harness & h)
{
  const std::uint64_t k = prepare_goto_start(h);
  tick_goto_start(h, k);
  return k;
}

// 공중 Offboard 진입에서 첫 항목이 시작될 때까지(C). C를 돌려준다.
std::uint64_t start_air_goto(Harness & h)
{
  h.start_in_air();
  const bool started = h.run_until([&h] { return h.view().stage == Stage::kItem; }, 100);
  EXPECT_TRUE(started);
  EXPECT_EQ(h.tick_no - 1, kAirConfirmTick);
  return h.tick_no - 1;
}

// K+1부터 K+last까지 tick한다. 각 tick 전에 prepare(n)을 부른다(n은 K로부터의 offset). GOTO 항목이
// 이 tick에 끝났으면(다른 항목이나 정리로 갔으면) 그 offset을 돌려준다. 끝나지 않으면 0.
std::uint64_t run_goto(
  Harness & h, std::uint64_t k, std::uint64_t last,
  const std::function<void(std::uint64_t)> & prepare = {}, bool cancel = false)
{
  for (std::uint64_t n = h.tick_no - k; n <= last; ++n) {
    if (prepare) {
      prepare(n);
    }
    h.tick(cancel);
    if (h.view().stage != Stage::kItem || h.view().item_index != 1U) {
      return n;
    }
  }
  return 0;
}

MissionSpec ground_goto_mission(const std::string & id, std::vector<ItemSpec> rest)
{
  MissionSpec m;
  m.mission_id = id;
  m.items = {takeoff_item(), goto_item()};
  for (ItemSpec & item : rest) {
    m.items.push_back(std::move(item));
  }
  return m;
}

// 끝난 goal의 완료 수와 index, 매 tick feedforward 없음, 종료 불변식.
void expect_end(
  Harness & h, const std::string & reason, std::uint32_t completed, std::uint32_t last_index)
{
  const Termination term = termination_or_empty(h);
  EXPECT_EQ(term.items_completed, completed) << term.detail;
  EXPECT_EQ(term.last_item_index, last_index) << term.detail;
  for (std::size_t i = 0; i < h.outputs().size(); ++i) {
    const StepOutput & out = h.outputs()[i];
    if (out.setpoint.has_value()) {
      EXPECT_FALSE(out.setpoint->velocity_valid) << "tick " << i + 1;
    }
  }
  EXPECT_EQ(h.frame.vector_calls, 0);
  expect_terminated_once_as(h, reason);
}

// ---- 지상 진입의 정상 경로 ----

TEST(Goto, GroundEntryReachesAndLands)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const StepOutput & first = out_at(h, k);
  expect_setpoint(first, 20.0, 10.0, -5.0, 0.25, "K");
  EXPECT_EQ(first.commands, kNoCommands);
  ASSERT_TRUE(first.feedback.has_value());
  EXPECT_EQ(first.feedback->item_index, 1U);
  EXPECT_EQ(first.feedback->item_type, item_type::kGoTo);
  EXPECT_EQ(first.feedback->phase, FeedbackPhase::kExecuting);
  expect_distance(first, distance_l(), "K");
  ASSERT_EQ(h.frame.point_calls.size(), 1U);
  EXPECT_EQ(h.frame.point_calls[0].tick, k);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.x, 10.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.y, 20.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.z, 5.0);
  for (std::uint64_t n = 1; n <= 4; ++n) {
    const StepOutput out = h.tick();
    const std::string where = "K+" + std::to_string(n);
    expect_setpoint(out, 20.0, 10.0, -5.0, 0.25, where);
    EXPECT_EQ(out.commands, kNoCommands) << where;
    expect_distance(out, distance_l(), where);
    EXPECT_EQ(h.frame.point_calls_at(k + n), 1) << where;
  }
  at_target(h);
  for (std::uint64_t n = 5; n <= 6; ++n) {
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();
    EXPECT_EQ(h.edges().size(), before) << "K+" << n;
    expect_distance(out, 0.0, "K+" + std::to_string(n));
  }
  const std::size_t before = h.edges().size();
  const StepOutput reach = h.tick();  // K+7
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
  EXPECT_EQ(reach.commands, kLandOnly);
  expect_setpoint(reach, 20.0, 10.0, -5.0, 0.25, "K+7");
  land_and_disarm(h);
  EXPECT_EQ(h.frame.point_calls_from(k + 8), 0);
  EXPECT_EQ(h.frame.point_calls.size(), 8U);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- 서로 다른 표본과 연속 ----

TEST(Goto, DistinctSamplesInARow)
{
  struct Case
  {
    const char * name;
    std::function<void(Harness &, std::uint64_t)> prepare;  // K+n 전에 부른다
    std::uint64_t reach;                                    // GOTO_REACHED의 offset
    std::uint64_t invalid_at;  // 그 tick의 feedback 거리가 무효(0이면 없음)
  };
  std::uint64_t saved_ts = 0;
  const std::vector<Case> cases = {
    {"same timestamp at K+6",
     [&saved_ts](Harness & h, std::uint64_t n) {
       if (n == 5) {
         at_target(h);
         saved_ts = h.default_timestamp_us();
       }
       h.world.position_timestamp_us =
         n == 6 ? std::optional<std::uint64_t>(saved_ts) : std::nullopt;
     },
     8, 0},
    {"xy_valid false at K+6",
     [](Harness & h, std::uint64_t n) {
       if (n == 5) {
         at_target(h);
       }
       h.world.xy_valid = n != 6;
     },
     9, 6},
    {"z_valid false at K+6",
     [](Harness & h, std::uint64_t n) {
       if (n == 5) {
         at_target(h);
       }
       h.world.z_valid = n != 6;
     },
     9, 6},
    {"outside at K+7",
     [](Harness & h, std::uint64_t n) {
       if (n >= 5) {
         at_target(h);
       }
       if (n == 7) {
         h.world.x = 20.6;
       }
     },
     10, 0},
    {"inside 0.25",
     [](Harness & h, std::uint64_t n) {
       if (n == 5) {
         move_to(h, 20.25, 10.0, -5.0);
       }
     },
     7, 0},
  };
  for (const Case & c : cases) {
    SCOPED_TRACE(c.name);
    Harness h(takeoff_goto_land_mission());
    h.frame.mode = FrameMode::kAxis;
    const std::uint64_t k = start_goto(h);
    const std::size_t before = h.edges().size();
    const std::uint64_t reached =
      run_goto(h, k, kTimeoutTicks, [&h, &c](std::uint64_t n) { c.prepare(h, n); });
    EXPECT_EQ(reached, c.reach);
    expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
    if (c.invalid_at != 0) {
      expect_distance(out_at(h, k + c.invalid_at), std::nullopt, "invalid sample tick");
    }
    land_and_disarm(h);
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
}

TEST(Goto, BoundaryDistanceIsNotReachedAndTimesOut)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  const std::uint64_t ended = run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) {
    if (n == 5) {
      move_to(h, 20.5, 10.0, -5.0);  // 거리가 정확히 0.5(엄격 부등호라 밖)
    }
  });
  EXPECT_EQ(ended, kTimeoutTicks);
  expect_cell(h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
  EXPECT_EQ(out_at(h, k + kTimeoutTicks).commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + kTimeoutTicks + 3);
  EXPECT_EQ(termination_or_empty(h).detail, "item 1 (GOTO) timeout; cleanup: Hold confirmed");
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
}

// 완료는 항목 시작 다음 tick부터 센다. 시작 tick K 전부터 목표점에 있어도 K의 표본은 세지 않아
// K+1, K+2, K+3의 세 표본으로 K+3에 끝난다.
TEST(Goto, CountingStartsOnTickAfterItemStart)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = prepare_goto_start(h);
  at_target(h);
  tick_goto_start(h, k);
  expect_distance(out_at(h, k), 0.0, "K");
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- 점 변환 값 없음 ----

TEST(Goto, WaitsForFirstTransformThenCounts)
{
  Harness h(takeoff_goto_land_mission());
  const std::uint64_t k = prepare_goto_start(h);
  h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
    if (tick < k + 10) {
      return std::nullopt;
    }
    return HarnessFramePort::axis(w);
  };
  at_target(h);
  tick_goto_start(h, k);
  for (std::uint64_t n = 0; n <= 9; ++n) {
    if (n > 0) {
      h.tick();
    }
    const StepOutput & out = out_at(h, k + n);
    const std::string where = "K+" + std::to_string(n);
    expect_setpoint(out, 1.0, 2.0, -5.0, 0.25, where);
    expect_distance(out, std::nullopt, where);
    EXPECT_EQ(h.frame.point_calls_at(k + n), 1) << where;
    EXPECT_EQ(h.view().item_index, 1U) << where;
  }
  const StepOutput first_value = h.tick();  // K+10
  expect_setpoint(first_value, 20.0, 10.0, -5.0, 0.25, "K+10");
  expect_distance(first_value, 0.0, "K+10");
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 12U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

TEST(Goto, MissingTransformBreaksTheRun)
{
  for (const bool gap : {true, false}) {
    SCOPED_TRACE(gap ? "no value at K+3" : "value every tick");
    Harness h(takeoff_goto_land_mission());
    const std::uint64_t k = prepare_goto_start(h);
    h.frame.hook = [k, gap](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
      if (gap && tick == k + 3) {
        return std::nullopt;
      }
      return HarnessFramePort::axis(w);
    };
    tick_goto_start(h, k);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_goto(h, k, kTimeoutTicks), gap ? 6U : 3U);
    expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
    if (gap) {
      expect_setpoint(out_at(h, k + 3), 20.0, 10.0, -5.0, 0.25, "K+3");
      expect_distance(out_at(h, k + 3), std::nullopt, "K+3");
    }
    land_and_disarm(h);
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
}

TEST(Goto, ItemTimeoutWithoutAnyTransform)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kNone;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), kTimeoutTicks);
  for (std::uint64_t n = 0; n < kTimeoutTicks; ++n) {
    const StepOutput & out = out_at(h, k + n);
    const std::string where = "K+" + std::to_string(n);
    expect_setpoint(out, 1.0, 2.0, -5.0, 0.25, where);
    EXPECT_EQ(out.commands, kNoCommands) << where;
  }
  const TransitionEdge * timeout =
    expect_cell(h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.NONE", Event::kEnterAir, "CLEANUP.ITEM_TIMEOUT.AIR", "-", {}, before);
  if (timeout != nullptr) {
    EXPECT_EQ(timeout->tick, k + kTimeoutTicks);
  }
  const StepOutput & end_tick = out_at(h, k + kTimeoutTicks);
  EXPECT_EQ(end_tick.commands, kHoldOnly);
  expect_setpoint(end_tick, 1.0, 2.0, -5.0, 0.25, "K+200");
  h.tick();  // K+201: AUTO_LOITER 표본
  EXPECT_FALSE(out_at(h, k + kTimeoutTicks + 1).setpoint.has_value());
  EXPECT_EQ(h.frame.point_calls_at(k + kTimeoutTicks + 1), 0);
  const std::size_t hold_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + kTimeoutTicks + 3);
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.AIR", Event::kHoldConfirmed, "DONE", "ABORTED/ITEM_TIMEOUT", {},
    hold_before);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 1 (GOTO) timeout (no frame transform since item start); cleanup: Hold confirmed");
  for (std::uint64_t n = kTimeoutTicks; n < kTimeoutTicks + 3; ++n) {
    const StepOutput & out = out_at(h, k + n);
    ASSERT_TRUE(out.feedback.has_value()) << n;
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kExecuting) << n;
    EXPECT_FALSE(out.feedback->distance_valid) << n;
  }
  EXPECT_EQ(h.frame.point_calls.size(), kTimeoutTicks + 1);
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
}

TEST(Goto, ItemTimeoutWithTransformHasNoSuffix)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), kTimeoutTicks);
  expect_cell(h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(detail, "item 1 (GOTO) timeout; cleanup: Hold confirmed");
  EXPECT_EQ(detail.rfind("item 1 (GOTO) timeout", 0), 0U);
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
}

// 처음 변환 값을 얻은 tick이 ITEM_TIMEOUT tick이나 취소 tick인 경우. 그 tick의 판정 앞에서 변환을
// 하므로 "변환 값을 얻었다"가 참이라 detail에 꼬리가 없고, setpoint는 그 tick에 GOTO 점으로 바뀐 채
// 정리 동안 유지된다(발행은 AUTO_LOITER 관측에서 멈춘다).
TEST(Goto, FirstTransformOnEndingTick)
{
  {
    SCOPED_TRACE("ITEM_TIMEOUT tick");
    Harness h(takeoff_goto_land_mission());
    const std::uint64_t k = prepare_goto_start(h);
    h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
      if (tick < k + kTimeoutTicks) {
        return std::nullopt;
      }
      return HarnessFramePort::axis(w);
    };
    tick_goto_start(h, k);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_goto(h, k, kTimeoutTicks), kTimeoutTicks);
    expect_cell(h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
    expect_setpoint(out_at(h, k + kTimeoutTicks - 1), 1.0, 2.0, -5.0, 0.25, "K+199");
    const StepOutput & end_tick = out_at(h, k + kTimeoutTicks);
    EXPECT_EQ(end_tick.commands, kHoldOnly);
    expect_setpoint(end_tick, 20.0, 10.0, -5.0, 0.25, "K+200");
    ASSERT_TRUE(h.run_until(
      [&h] {
        EXPECT_DOUBLE_EQ(h.view().setpoint.x, 20.0);
        EXPECT_DOUBLE_EQ(h.view().setpoint.y, 10.0);
        return h.runner().done();
      },
      10));
    EXPECT_EQ(h.frame.point_calls_from(k + kTimeoutTicks + 1), 0);
    EXPECT_EQ(termination_or_empty(h).detail, "item 1 (GOTO) timeout; cleanup: Hold confirmed");
    expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
  }
  {
    SCOPED_TRACE("cancel tick");
    Harness h(takeoff_goto_land_mission());
    const std::uint64_t k = prepare_goto_start(h);
    h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
      if (tick < k + 3) {
        return std::nullopt;
      }
      return HarnessFramePort::axis(w);
    };
    tick_goto_start(h, k);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
    expect_cell(h, "ITEM.GOTO", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
    const StepOutput & cancel = out_at(h, k + 3);
    EXPECT_EQ(cancel.commands, kHoldOnly);
    expect_setpoint(cancel, 20.0, 10.0, -5.0, 0.25, "K+3");
    ASSERT_TRUE(h.run_until(
      [&h] {
        EXPECT_DOUBLE_EQ(h.view().setpoint.x, 20.0);
        return h.runner().done();
      },
      10));
    EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
    expect_end(h, "CANCELED/NONE", 1, 1);
  }
}

// ---- 같은 tick의 만료와 완료(만료가 이긴다) ----

TEST(Goto, TimeoutWinsOverThirdSampleOnSameTick)
{
  for (const std::uint64_t from : {198U, 197U}) {
    SCOPED_TRACE(from);
    Harness h(takeoff_goto_land_mission());
    h.frame.mode = FrameMode::kAxis;
    const std::uint64_t k = start_goto(h);
    const std::size_t before = h.edges().size();
    const std::uint64_t ended = run_goto(h, k, kTimeoutTicks, [&h, from](std::uint64_t n) {
      if (n == from) {
        at_target(h);
      }
    });
    if (from == 198U) {
      EXPECT_EQ(ended, kTimeoutTicks);
      expect_cell(
        h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
        {Event::kGotoReached}, before);
      EXPECT_EQ(out_at(h, k + kTimeoutTicks).commands, kHoldOnly);
      for (const TransitionEdge & edge : h.edges()) {
        EXPECT_NE(state_key_name(edge.to), "ITEM.LAND");
      }
      ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
      EXPECT_EQ(h.tick_no - 1, k + kTimeoutTicks + 3);
      EXPECT_EQ(termination_or_empty(h).detail, "item 1 (GOTO) timeout; cleanup: Hold confirmed");
      EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
      expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
    } else {
      EXPECT_EQ(ended, kTimeoutTicks - 1);
      expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
      EXPECT_EQ(out_at(h, k + kTimeoutTicks - 1).commands, kLandOnly);
    }
  }
}

// ---- yaw ----

ItemSpec fixed_yaw(ItemSpec item, double yaw_rad)
{
  YawSpec & yaw = item.type == item_type::kTakeoff ? item.takeoff.yaw : item.go_to.yaw;
  yaw.mode = yaw_mode::kFixed;
  yaw.yaw_rad = yaw_rad;
  return item;
}

TEST(Goto, YawIsFixedAtItemStart)
{
  const double ned_03 = kPi / 2.0 - 0.3;  // enu_to_ned_yaw(0.3)
  const double ned_10 = kPi / 2.0 - 1.0;  // enu_to_ned_yaw(1.0)
  {
    SCOPED_TRACE("GOTO MODE_FIXED 0.3");
    Harness h(mission_of("yaw1", {takeoff_item(), fixed_yaw(goto_item(), 0.3), land_item()}));
    h.frame.mode = FrameMode::kAxis;
    const std::uint64_t k = start_goto(h);
    expect_setpoint(out_at(h, k), 20.0, 10.0, -5.0, ned_03, "K");
    expect_setpoint(h.tick(), 20.0, 10.0, -5.0, ned_03, "K+1");
  }
  {
    SCOPED_TRACE("GOTO MODE_FIXED 0.3, no value K..K+4");
    Harness h(mission_of("yaw2", {takeoff_item(), fixed_yaw(goto_item(), 0.3), land_item()}));
    const std::uint64_t k = prepare_goto_start(h);
    h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
      if (tick <= k + 4) {
        return std::nullopt;
      }
      return HarnessFramePort::axis(w);
    };
    tick_goto_start(h, k);
    for (std::uint64_t n = 0; n <= 6; ++n) {
      if (n > 0) {
        h.tick();
      }
      const std::string where = "K+" + std::to_string(n);
      if (n <= 4) {
        expect_setpoint(out_at(h, k + n), 1.0, 2.0, -5.0, 0.25, where);
      } else {
        expect_setpoint(out_at(h, k + n), 20.0, 10.0, -5.0, ned_03, where);
      }
    }
  }
  {
    SCOPED_TRACE("TAKEOFF MODE_FIXED 1.0, GOTO MODE_KEEP");
    Harness h(mission_of("yaw3", {fixed_yaw(takeoff_item(), 1.0), goto_item(), land_item()}));
    h.frame.mode = FrameMode::kAxis;
    const std::uint64_t k = start_goto(h);
    expect_setpoint(out_at(h, k), 20.0, 10.0, -5.0, ned_10, "K");
  }
  {
    SCOPED_TRACE("GOTO MODE_FIXED 0.3, then GOTO MODE_KEEP");
    Harness h(mission_of(
      "yaw4", {takeoff_item(), fixed_yaw(goto_item(), 0.3), goto_item(kSecondWorld), land_item()}));
    h.frame.mode = FrameMode::kAxis;
    const std::uint64_t k = start_goto(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
    expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.GOTO", "-", {}, before);
    EXPECT_EQ(h.view().item_index, 2U);
    expect_setpoint(out_at(h, k + 3), 0.0, 0.0, -5.0, ned_03, "second GOTO start");
  }
}

// ---- 매 tick 다시 변환 ----

TEST(Goto, TransformsEveryTick)
{
  Harness h(takeoff_goto_land_mission());
  const std::uint64_t k = prepare_goto_start(h);
  h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
    // K+3부터 기준이 북쪽으로 1 m 옮겨진 것처럼 로컬 x가 1 늘어난다.
    return HarnessFramePort::axis(w, tick >= k + 3 ? Vec3{1.0, 0.0, 0.0} : Vec3{});
  };
  tick_goto_start(h, k);
  const std::size_t before = h.edges().size();
  const std::uint64_t reached = run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) {
    if (n == 3) {
      move_to(h, 21.0, 10.0, -5.0);
    }
  });
  EXPECT_EQ(reached, 5U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
  for (std::uint64_t n = 0; n <= 2; ++n) {
    expect_setpoint(out_at(h, k + n), 20.0, 10.0, -5.0, 0.25, "K+" + std::to_string(n));
  }
  expect_setpoint(out_at(h, k + 3), 21.0, 10.0, -5.0, 0.25, "K+3");
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- 호출 규율: GOTO 완료 tick에 다음 항목도 GOTO ----

TEST(FramePortCalls, GotoToGotoCallsTwiceOnCompletionTick)
{
  Harness h(mission_of("gg", {takeoff_item(), goto_item(), goto_item(kSecondWorld), land_item()}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  const std::uint64_t j = k + 3;
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.GOTO", "-", {}, before);
  ASSERT_EQ(h.frame.point_calls_at(j), 2);
  const std::size_t last = h.frame.point_calls.size();
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 2].world.x, 10.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 2].world.y, 20.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.x, 0.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.y, 0.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.z, 5.0);
  expect_setpoint(out_at(h, j), 0.0, 0.0, -5.0, 0.25, "j");
  // 둘째 GOTO를 끝내고 LAND로 간다. 그 뒤(LAND와 끝)는 호출이 없다.
  move_to(h, 0.0, 0.0, -5.0);
  const std::size_t second = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 3U; }, 10));
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, second);
  const std::uint64_t land_start = h.tick_no - 1;
  land_and_disarm(h);
  EXPECT_EQ(h.frame.point_calls_from(land_start + 1), 0);
  // GOTO는 벡터 변환을 부르지 않는다.
  EXPECT_EQ(h.frame.vector_calls, 0);
  expect_end(h, "SUCCEEDED/NONE", 4, 3);
}

// ---- 다음 항목 ----

TEST(Goto, NextItemLoiterHoldsTheGotoPoint)
{
  Harness h(ground_goto_mission("gl", {loiter_item()}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LOITER", "-", {}, before);
  EXPECT_EQ(out_at(h, k + 3).commands, kNoCommands);
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 200));
  for (std::uint64_t t = k + 3; t < h.tick_no; ++t) {
    expect_setpoint(out_at(h, t), 20.0, 10.0, -5.0, 0.25, "tick " + std::to_string(t));
  }
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

TEST(Goto, NextItemRtl)
{
  Harness h(ground_goto_mission("gr", {rtl_item()}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.RTL", "-", {}, before);
  EXPECT_EQ(out_at(h, k + 3).commands, std::vector<CommandKind>{CommandKind::kNavRtl});
  land_and_disarm(h);
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

TEST(Goto, NextItemGotoThenMissionEnd)
{
  Harness h(ground_goto_mission("gg2", {goto_item(kSecondWorld)}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.GOTO", "-", {}, before);
  expect_setpoint(out_at(h, k + 3), 0.0, 0.0, -5.0, 0.25, "second GOTO start");
  move_to(h, 0.0, 0.0, -5.0);
  before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 10));
  EXPECT_EQ(h.tick_no - 1, k + 6);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "CLEANUP.MISSION_END.NONE", "-", {}, before);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

TEST(Goto, LastItemGotoGoesToMissionEnd)
{
  Harness h(ground_goto_mission("gend", {}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "CLEANUP.MISSION_END.NONE", "-", {}, before);
  expect_cell(
    h, "CLEANUP.MISSION_END.NONE", Event::kEnterAir, "CLEANUP.MISSION_END.AIR", "-", {}, before);
  const StepOutput & reach = out_at(h, k + 3);
  EXPECT_EQ(reach.commands, kHoldOnly);
  expect_setpoint(reach, 20.0, 10.0, -5.0, 0.25, "K+3");
  const std::size_t hold_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + 6);
  expect_cell(
    h, "CLEANUP.MISSION_END.AIR", Event::kHoldConfirmed, "DONE", "SUCCEEDED/NONE", {}, hold_before);
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  expect_end(h, "SUCCEEDED/NONE", 2, 1);
}

TEST(Goto, LoiterThenGotoChangesSetpointOnStartTick)
{
  Harness h(mission_of("lg", {takeoff_item(), loiter_item(), goto_item(), land_item()}));
  h.frame.mode = FrameMode::kAxis;
  h.drive_to_loiter();
  EXPECT_TRUE(h.frame.point_calls.empty());
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 2U; }, 200));
  const std::uint64_t k = h.tick_no - 1;
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.GOTO", "-", {}, before);
  expect_setpoint(out_at(h, k), 20.0, 10.0, -5.0, 0.25, "LOITER end tick");
  EXPECT_EQ(h.frame.point_calls.size(), 1U);
  EXPECT_EQ(h.frame.point_calls_at(k), 1);
}

// ---- 공중 Offboard 진입 ----

TEST(Goto, AirEntryGotoOnly)
{
  Harness h(air_goto_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::size_t before = h.edges().size();
  const std::uint64_t c = start_air_goto(h);
  for (std::uint64_t t = 1; t < c; ++t) {
    expect_setpoint(out_at(h, t), 1.0, 2.0, -5.0, 0.25, "tick " + std::to_string(t));
  }
  EXPECT_EQ(out_at(h, 11).commands, std::vector<CommandKind>{CommandKind::kSetModeOffboard});
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.GOTO", "-", {}, before);
  expect_setpoint(out_at(h, c), 20.0, 10.0, -5.0, 0.25, "C");
  ASSERT_EQ(h.frame.point_calls.size(), 1U);
  EXPECT_EQ(h.frame.point_calls[0].tick, c);
  at_target(h);
  const std::size_t reach_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 10));
  EXPECT_EQ(h.tick_no - 1, c + 3);
  expect_cell(
    h, "ITEM.GOTO", Event::kGotoReached, "CLEANUP.MISSION_END.NONE", "-", {}, reach_before);
  EXPECT_EQ(out_at(h, c + 3).commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, c + 6);
  EXPECT_EQ(termination_or_empty(h).detail, "");
  EXPECT_EQ(h.count_command(CommandKind::kSetModeOffboard), 1);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  expect_end(h, "SUCCEEDED/NONE", 1, 0);
}

TEST(Goto, AirEntryGotoThenLand)
{
  Harness h(mission_of("agl", {goto_item(), land_item()}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t c = start_air_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 10));
  EXPECT_EQ(h.tick_no - 1, c + 3);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LAND", "-", {}, before);
  EXPECT_EQ(out_at(h, c + 3).commands, kLandOnly);
  land_and_disarm(h);
  EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
  expect_end(h, "SUCCEEDED/NONE", 2, 1);
}

TEST(Goto, AirEntryLoiterThenGoto)
{
  Harness h(mission_of("alg", {loiter_item(), goto_item()}));
  h.frame.mode = FrameMode::kAxis;
  h.start_in_air();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kItem; }, 100));
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 200));
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.GOTO", "-", {}, before);
  expect_setpoint(out_at(h, h.tick_no - 1), 20.0, 10.0, -5.0, 0.25, "LOITER end tick");
}

TEST(Goto, AirEntryPreconditionNamesGoto)
{
  Harness h(air_goto_mission());
  h.frame.mode = FrameMode::kAxis;
  h.start_in_air();
  h.world.landed = true;
  h.tick();
  const std::string detail = termination_or_empty(h).detail;
  EXPECT_EQ(
    detail.rfind(
      "GOTO needs not landed, ARMED, nav_state and user intention AUTO_LOITER, no failsafe (", 0),
    0U)
    << detail;
  EXPECT_TRUE(h.frame.point_calls.empty());
  expect_end(h, "ABORTED/PRECONDITION_FAILED", 0, 0);
}

TEST(Goto, AirEntryWithoutTransformTimesOut)
{
  Harness h(air_goto_mission());
  h.frame.mode = FrameMode::kNone;
  const std::size_t before = h.edges().size();
  const std::uint64_t c = start_air_goto(h);
  expect_cell(
    h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.GOTO", "-", {}, before);
  expect_setpoint(out_at(h, c), 1.0, 2.0, -5.0, 0.25, "C");
  const std::size_t timeout_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 300));
  EXPECT_EQ(h.tick_no - 1, c + kTimeoutTicks);
  expect_cell(
    h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, timeout_before);
  EXPECT_EQ(out_at(h, c + kTimeoutTicks).commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, c + kTimeoutTicks + 3);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 0 (GOTO) timeout (no frame transform since item start); cleanup: Hold confirmed");
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 0, 0);
}

TEST(Goto, AirEntryTimeoutOnGroundDisarmedNothingToDo)
{
  Harness h(air_goto_mission());
  h.frame.mode = FrameMode::kAxis;
  h.hold_response = HoldResponse::kIgnore;
  const std::uint64_t c = start_air_goto(h);
  const std::size_t before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 300));
  EXPECT_EQ(h.tick_no - 1, c + kTimeoutTicks);
  expect_cell(h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
  EXPECT_EQ(out_at(h, c + kTimeoutTicks).commands, kHoldOnly);
  const std::size_t end_before = h.edges().size();
  const std::vector<StepOutput> outs = h.feed({disarmed(true)});  // C+201
  expect_cell(
    h, "CLEANUP.ITEM_TIMEOUT.AIR", Event::kCleanupNothingToDo, "DONE", "ABORTED/ITEM_TIMEOUT", {},
    end_before);
  ASSERT_EQ(outs.size(), 1U);
  EXPECT_EQ(outs[0].commands, kNoCommands);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 0 (GOTO) timeout; cleanup: on ground and DISARMED, arm never sent");
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 0, 0);
}

// ---- 취소 ----

TEST(Goto, CancelInGoto)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  const StepOutput & cancel = out_at(h, k + 3);
  EXPECT_EQ(cancel.commands, kHoldOnly);
  expect_setpoint(cancel, 20.0, 10.0, -5.0, 0.25, "K+3");
  ASSERT_TRUE(cancel.feedback.has_value());
  EXPECT_EQ(cancel.feedback->phase, FeedbackPhase::kCanceling);
  EXPECT_EQ(h.frame.point_calls_at(k + 3), 1);
  h.tick();  // K+4: AUTO_LOITER
  EXPECT_FALSE(out_at(h, k + 4).setpoint.has_value());
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + 6);
  expect_end(h, "CANCELED/NONE", 1, 1);
}

TEST(Goto, ItemTimeoutWithCancel)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(
    run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= kTimeoutTicks; }),
    kTimeoutTicks);
  expect_cell(
    h, "ITEM.GOTO", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {Event::kCancel},
    before);
  const std::size_t after = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + kTimeoutTicks + 3);
  for (std::size_t i = after; i < h.edges().size(); ++i) {
    EXPECT_NE(h.edges()[i].event, Event::kCancel);
  }
  for (std::uint64_t n = kTimeoutTicks; n <= kTimeoutTicks + 2; ++n) {
    ASSERT_TRUE(out_at(h, k + n).feedback.has_value());
    EXPECT_EQ(out_at(h, k + n).feedback->phase, FeedbackPhase::kExecuting);
  }
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
}

TEST(Goto, LastGotoReachedWithCancel)
{
  Harness h(ground_goto_mission("gc", {}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
  expect_cell(
    h, "ITEM.GOTO", Event::kGotoReached, "CLEANUP.MISSION_END.NONE", "-", {Event::kCancel}, before);
  const std::size_t after = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + 6);
  for (std::size_t i = after; i < h.edges().size(); ++i) {
    EXPECT_NE(h.edges()[i].event, Event::kCancel);
  }
  expect_end(h, "SUCCEEDED/NONE", 2, 1);
}

TEST(Goto, ImmediateEndWithCancel)
{
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(
    run_goto(
      h, k, kTimeoutTicks,
      [&h](std::uint64_t n) {
        if (n == 3) {
          h.auto_px4 = false;
          h.world.nav = NavMode::kRtl;
          h.world.intention = NavMode::kRtl;
          h.cancel_sticky = true;
        }
      }),
    3U);
  expect_cell(
    h, "ITEM.GOTO", Event::kMonitorModeExternal, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
    {Event::kCancel}, before);
  const StepOutput & end = out_at(h, k + 3);
  EXPECT_EQ(end.commands, kNoCommands);
  EXPECT_FALSE(end.setpoint.has_value());
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  expect_end(h, "ABORTED/EXTERNAL_MODE_CHANGE", 1, 1);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
}

TEST(Goto, ReachedThenCancelInNextItem)
{
  Harness h(ground_goto_mission("gcl", {loiter_item()}));
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_goto(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
  expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.LOITER", "-", {}, before);
  expect_cell(h, "ITEM.LOITER", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
  EXPECT_EQ(out_at(h, k + 3).commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_end(h, "CANCELED/NONE", 2, 2);
}

// ---- 감시 표 ----

struct MonitorCase
{
  const char * name;
  Event event;
  const char * reason;
  std::vector<Event> also;
  // offset n의 tick 전에 world와 clock을 바꾼다. status를 넣지 않으려면 false를 돌려준다.
  std::function<bool(Harness &, std::uint64_t)> prepare;
  std::uint64_t end;  // 끝나는 tick의 offset
  std::vector<CommandKind> commands;
};

void set_status(Harness & h, Arming arming, bool landed, NavMode nav, NavMode intention, bool fs)
{
  h.auto_px4 = false;
  h.world.arming = arming;
  h.world.landed = landed;
  h.world.nav = nav;
  h.world.intention = intention;
  h.world.failsafe = fs;
}

void run_monitor_case(const MonitorCase & c)
{
  SCOPED_TRACE(c.name);
  Harness h(takeoff_goto_land_mission());
  h.frame.mode = FrameMode::kAxis;
  const std::uint64_t k = start_goto(h);
  const std::size_t before = h.edges().size();
  for (std::uint64_t n = 1; n <= c.end; ++n) {
    const bool with_status = c.prepare(h, n);
    if (with_status) {
      h.tick();
    } else {
      h.push_world_samples_without_status();
      h.step_only();
    }
    if (h.runner().done()) {
      EXPECT_EQ(n, c.end);
      break;
    }
  }
  ASSERT_TRUE(h.runner().done());
  expect_cell(h, "ITEM.GOTO", c.event, "DONE", c.reason, c.also, before);
  const StepOutput & end = out_at(h, k + c.end);
  EXPECT_EQ(end.commands, c.commands);
  EXPECT_FALSE(end.setpoint.has_value());
  h.clock.fail = false;
  expect_end(h, c.reason, 1, 1);
}

// 단일 행: K+3에 위치는 목표점 밖(ITEM_TIMEOUT과 완료가 거짓). DISARMED 표본은 nav OFFBOARD로 두어
// 순위 6-8이 함께 맞지 않게 한다.
TEST(GotoMonitor, SingleRows)
{
  const auto at3 = [](std::function<void(Harness &)> f) {
    return [f](Harness & h, std::uint64_t n) {
      if (n == 3) {
        f(h);
      }
      return true;
    };
  };
  const std::vector<MonitorCase> cases = {
    {"rank 1",
     Event::kMonitorTimestampFailure,
     "ABORTED/INTERNAL",
     {},
     at3([](Harness & h) { h.clock.fail = true; }),
     3,
     kNoCommands},
    {"rank 2",
     Event::kMonitorIdentityMismatch,
     "ABORTED/INTERNAL",
     {},
     at3([](Harness & h) { h.world.identity = IdentityCheck::kMismatch; }),
     3,
     kDisarmOnly},
    {"rank 3",
     Event::kMonitorLinkLost,
     "ABORTED/LINK_LOST",
     {},
     [](Harness &, std::uint64_t) { return false; },
     40,
     kNoCommands},
    {"rank 4",
     Event::kMonitorDisarmedInAir,
     "ABORTED/FAILSAFE",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kDisarmed, false, NavMode::kOffboard, NavMode::kOffboard, false);
     }),
     3,
     kNoCommands},
    {"rank 5 external",
     Event::kMonitorDisarmedOnGround,
     "ABORTED/EXTERNAL_DISARM",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, false);
     }),
     3,
     kNoCommands},
    {"rank 5 failsafe",
     Event::kMonitorDisarmedOnGround,
     "ABORTED/FAILSAFE",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, true);
     }),
     3,
     kNoCommands},
    {"rank 6",
     Event::kMonitorModeFailsafe,
     "ABORTED/FAILSAFE",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kArmed, false, NavMode::kHold, NavMode::kHold, true);
     }),
     3,
     kNoCommands},
    {"rank 7",
     Event::kMonitorModeExternal,
     "ABORTED/EXTERNAL_MODE_CHANGE",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kArmed, false, NavMode::kRtl, NavMode::kRtl, false);
     }),
     3,
     kNoCommands},
    {"rank 8",
     Event::kMonitorModeDefensive,
     "ABORTED/FAILSAFE",
     {},
     at3([](Harness & h) {
       set_status(h, Arming::kArmed, false, NavMode::kOther, NavMode::kOffboard, false);
     }),
     3,
     kNoCommands},
    {"pair DISARMED in air and mode failsafe",
     Event::kMonitorDisarmedInAir,
     "ABORTED/FAILSAFE",
     {Event::kMonitorModeFailsafe},
     at3([](Harness & h) {
       set_status(h, Arming::kDisarmed, false, NavMode::kHold, NavMode::kHold, true);
     }),
     3,
     kNoCommands},
  };
  for (const MonitorCase & c : cases) {
    run_monitor_case(c);
  }
}

// setpoint 순서의 대표 행 넷과 ITEM_TIMEOUT, 완료의 겹침.
TEST(GotoMonitor, RepresentativeRowsOverItemTimeoutAndCompletion)
{
  const std::uint64_t t = kTimeoutTicks;
  const auto at = [](std::uint64_t when, std::function<void(Harness &)> f) {
    return [when, f](Harness & h, std::uint64_t n) {
      if (n == when) {
        f(h);
      }
      return true;
    };
  };
  const auto reach_and_at = [](std::uint64_t when, std::function<void(Harness &)> f) {
    return [when, f](Harness & h, std::uint64_t n) {
      if (n == 1) {
        at_target(h);
      }
      if (n == when) {
        f(h);
      }
      return true;
    };
  };
  const std::vector<Event> timeout = {Event::kItemTimeout};
  const std::vector<Event> reached = {Event::kGotoReached};
  const auto clock_fail = [](Harness & h) { h.clock.fail = true; };
  const auto ground_disarm = [](Harness & h) {
    set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, false);
  };
  const auto rtl = [](Harness & h) {
    set_status(h, Arming::kArmed, false, NavMode::kRtl, NavMode::kRtl, false);
  };
  const std::vector<MonitorCase> cases = {
    {"timeout rank 1", Event::kMonitorTimestampFailure, "ABORTED/INTERNAL", timeout,
     at(t, clock_fail), t, kNoCommands},
    {"timeout rank 3", Event::kMonitorLinkLost, "ABORTED/LINK_LOST", timeout,
     [t](Harness &, std::uint64_t n) { return n < t - 39; }, t, kNoCommands},
    {"timeout rank 5", Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM", timeout,
     at(t, ground_disarm), t, kNoCommands},
    {"timeout rank 7", Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE", timeout,
     at(t, rtl), t, kNoCommands},
    {"reached rank 1", Event::kMonitorTimestampFailure, "ABORTED/INTERNAL", reached,
     reach_and_at(3, clock_fail), 3, kNoCommands},
    {"reached rank 3", Event::kMonitorLinkLost, "ABORTED/LINK_LOST", reached,
     [](Harness & h, std::uint64_t n) {
       if (n == 38) {
         at_target(h);
       }
       return false;
     },
     40, kNoCommands},
    {"reached rank 5", Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM", reached,
     reach_and_at(3, ground_disarm), 3, kNoCommands},
    {"reached rank 7", Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE", reached,
     reach_and_at(3, rtl), 3, kNoCommands},
  };
  for (const MonitorCase & c : cases) {
    run_monitor_case(c);
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
