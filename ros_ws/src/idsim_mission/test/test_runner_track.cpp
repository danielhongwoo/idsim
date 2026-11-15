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

// TRACK_ENTITY 항목, TARGET_LOST와 그 정리 입구, 속도 feedforward
// (docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 8, 13).
//
// - 칸은 transition_cells.tsv의 ITEM.TRACK_ENTITY 행, TRACK_ENTITY로 들어오는 네 행, 그리고
//   CLEANUP.TARGET_LOST.NONE의 입구다(정리 분기의 칸은 test_runner_cleanup_cells.cpp의 rig). 기호:
//   K는 TRACK_ENTITY 항목을 시작한 tick(지상 진입은 TAKEOFF_REACHED tick), K+n은 그 뒤 n번째 tick,
//   C는 공중 Offboard 진입의 OFFBOARD 3회 확인 tick(harness 기본값에서 14)이다.
// - port는 kAxis(점 (w.y, w.x, -w.z), 벡터 (v.y, v.x, -v.z))가 기본이다. track_entity_item()
//   기본값은 target_id "t1", offset world (0, 0, 5), 반경 0.5 m, timeout 10 s(200 tick),
//   MODE_KEEP이다.
// - 표적 기본값은 world 위치 (10, 20, 0), velocity_valid true, 속도 world (1, 0, 0)이고 tick마다 새
//   표본(stamp_ns = 그 tick의 now_ns)이다. 그래서 world 점 (10, 20, 5), 로컬 L = (20, 10, -5), 로컬
//   속도 (0, 1, 0)이다. 사례가 바꾸는 것만 적는다(harness target_hook).
// - 지상 진입은 [TAKEOFF(5 m, MODE_KEEP), TRACK_ENTITY, ...]이고 TAKEOFF 목표점은 (1, 2, -5), yaw
//   0.25다. 공중 진입은 start_in_air()(위치 (1, 2, -5), heading 0.25)다.
// - 시간 값은 Config 기본값이다: target_timeout 1.0 s(20 tick), target_fresh_age 0.1 s(2 tick).
//   표본이 없으면 항목 시작부터 경과가 target_timeout을 넘는 K+21이, 마지막 표본이 tick s이면
//   s+21이 TARGET_LOST다(초과. 쟁점 8).
// - 모든 사례가 port 호출 규율을 함께 단정한다: tick마다 점 변환 2회 이하(완료 tick에 다음 항목이
//   GOTO나 TRACK_ENTITY일 때만 2), 벡터 변환은 점 변환 이하. 속도 불변식(속도가 있으면 세 성분 모두
//   유한하고 그 tick의 끝 상태가 ITEM.TRACK_ENTITY)은 harness가 모든 step 뒤에 단정한다.

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

constexpr double kPi = 3.14159265358979323846;
constexpr std::uint64_t kTimeoutTicks = 200;   // track_entity_item() timeout 10 s
constexpr std::uint64_t kAirConfirmTick = 14;  // 공중 진입의 C(harness 기본값)
constexpr std::int64_t kMs = 1000000LL;

const std::vector<CommandKind> kNoCommands = {};
const std::vector<CommandKind> kHoldOnly = {CommandKind::kSetModeHold};
const std::vector<CommandKind> kLandOnly = {CommandKind::kNavLand};
const std::vector<CommandKind> kRtlOnly = {CommandKind::kNavRtl};
const std::vector<CommandKind> kDisarmOnly = {CommandKind::kDisarm};

const Vec3 kLocalL{20.0, 10.0, -5.0};
const Vec3 kLocalVelocity{0.0, 1.0, 0.0};

double distance_l() { return std::sqrt(425.0); }  // (1, 2, -5)에서 L까지

MissionSpec mission_of(const std::string & id, std::vector<ItemSpec> items)
{
  MissionSpec m;
  m.mission_id = id;
  m.items = std::move(items);
  return m;
}

// [TAKEOFF, TRACK_ENTITY, rest...].
MissionSpec ground_track_mission(const std::string & id, std::vector<ItemSpec> rest)
{
  MissionSpec m;
  m.mission_id = id;
  m.items = {takeoff_item(), track_entity_item()};
  for (ItemSpec & item : rest) {
    m.items.push_back(std::move(item));
  }
  return m;
}

void add_target(
  Harness & h, const std::string & id = "t1", Vec3 world = Vec3{10.0, 20.0, 0.0},
  Vec3 velocity = Vec3{1.0, 0.0, 0.0})
{
  TargetSample s;
  s.position = world;
  s.velocity_valid = true;
  s.velocity = velocity;
  h.world.targets[id] = s;
}

// tick n(절대 번호)에 표본을 주지 않는다.
void omit_target_when(Harness & h, std::function<bool(std::uint64_t)> omit)
{
  h.target_hook = [omit](
                    const std::string &, std::uint64_t tick,
                    const TargetSample & base) -> std::optional<TargetSample> {
    if (omit(tick)) {
      return std::nullopt;
    }
    return base;
  };
}

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

void land_and_disarm(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 20));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
}

// setpoint의 위치, yaw, 속도. velocity가 nullopt이면 속도 없음.
void expect_track_setpoint(
  const StepOutput & out, const Vec3 & pos, double yaw, std::optional<Vec3> velocity,
  const std::string & where)
{
  ASSERT_TRUE(out.setpoint.has_value()) << where;
  EXPECT_EQ(out.setpoint->kind, SetpointKind::kTarget) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->x, pos.x) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->y, pos.y) << where;
  EXPECT_DOUBLE_EQ(out.setpoint->z, pos.z) << where;
  EXPECT_NEAR(out.setpoint->yaw_ned, yaw, 1e-12) << where;
  EXPECT_EQ(out.setpoint->velocity_valid, velocity.has_value()) << where;
  if (velocity.has_value() && out.setpoint->velocity_valid) {
    EXPECT_DOUBLE_EQ(out.setpoint->velocity.x, velocity->x) << where;
    EXPECT_DOUBLE_EQ(out.setpoint->velocity.y, velocity->y) << where;
    EXPECT_DOUBLE_EQ(out.setpoint->velocity.z, velocity->z) << where;
  }
}

void expect_distance(const StepOutput & out, std::optional<double> distance, const std::string & w)
{
  ASSERT_TRUE(out.feedback.has_value()) << w;
  EXPECT_EQ(out.feedback->distance_valid, distance.has_value()) << w;
  if (distance.has_value()) {
    EXPECT_NEAR(out.feedback->distance_remaining_m, *distance, 1e-9) << w;
  }
}

// port 호출 규율: tick마다 점 변환 2회 이하, 벡터 변환은 점 변환 이하.
void expect_call_discipline(const Harness & h)
{
  for (std::uint64_t tick = 1; tick < h.tick_no; ++tick) {
    const int points = h.frame.point_calls_at(tick);
    EXPECT_LE(points, 2) << "tick " << tick;
    EXPECT_LE(h.frame.vector_calls_at(tick), points) << "tick " << tick;
  }
}

// 끝난 goal의 완료 수와 index, 호출 규율, 종료 불변식.
void expect_end(
  Harness & h, const std::string & reason, std::uint32_t completed, std::uint32_t last_index)
{
  const Termination term = termination_or_empty(h);
  EXPECT_EQ(term.items_completed, completed) << term.detail;
  EXPECT_EQ(term.last_item_index, last_index) << term.detail;
  expect_call_discipline(h);
  expect_terminated_once_as(h, reason);
}

// 지상 진입: TAKEOFF가 시작된 뒤 목표 고도에 둔다. 다음 tick이 K(TAKEOFF_REACHED)다. K를 돌려준다.
std::uint64_t prepare_track_start(Harness & h)
{
  h.frame.mode = FrameMode::kAxis;
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -5.0;
  EXPECT_TRUE(h.frame.point_calls.empty());
  EXPECT_EQ(h.frame.vector_calls, 0);
  return h.tick_no;
}

// K tick을 돌리고 TAKEOFF -> TRACK_ENTITY 칸을 단정한다.
void tick_track_start(Harness & h, std::uint64_t k)
{
  const std::size_t before = h.edges().size();
  h.tick();
  EXPECT_EQ(h.tick_no - 1, k);
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, "ITEM.TRACK_ENTITY", "-", {}, before);
  EXPECT_EQ(h.view().item_index, 1U);
}

std::uint64_t start_track(Harness & h)
{
  const std::uint64_t k = prepare_track_start(h);
  tick_track_start(h, k);
  return k;
}

// 공중 Offboard 진입에서 첫 항목이 시작될 때까지(C). C를 돌려준다.
std::uint64_t start_air_track(Harness & h)
{
  h.frame.mode = FrameMode::kAxis;
  h.start_in_air();
  const bool started = h.run_until([&h] { return h.view().stage == Stage::kItem; }, 100);
  EXPECT_TRUE(started);
  EXPECT_EQ(h.tick_no - 1, kAirConfirmTick);
  return h.tick_no - 1;
}

// K+1부터 K+last까지 tick한다. 각 tick 전에 prepare(n)을 부른다. index번째 항목이 이 tick에
// 끝났으면 그 offset을 돌려준다. 끝나지 않으면 0.
std::uint64_t run_track(
  Harness & h, std::uint64_t k, std::uint64_t last,
  const std::function<void(std::uint64_t)> & prepare = {}, std::uint32_t index = 1U)
{
  for (std::uint64_t n = h.tick_no - k; n <= last; ++n) {
    if (prepare) {
      prepare(n);
    }
    h.tick();
    if (h.view().stage != Stage::kItem || h.view().item_index != index) {
      return n;
    }
  }
  return 0;
}

// ---- 지상 진입의 정상 경로 ----

TEST(Track, GroundEntryReachesAndLands)
{
  Harness h(ground_track_mission("tl", {land_item()}));
  add_target(h);
  const std::uint64_t k = start_track(h);
  const StepOutput & first = out_at(h, k);
  expect_track_setpoint(first, kLocalL, 0.25, kLocalVelocity, "K");
  EXPECT_EQ(first.commands, kNoCommands);
  ASSERT_TRUE(first.feedback.has_value());
  EXPECT_EQ(first.feedback->item_index, 1U);
  EXPECT_EQ(first.feedback->item_type, item_type::kTrackEntity);
  EXPECT_EQ(first.feedback->phase, FeedbackPhase::kExecuting);
  expect_distance(first, distance_l(), "K");
  ASSERT_EQ(h.frame.point_calls.size(), 1U);
  EXPECT_EQ(h.frame.point_calls[0].tick, k);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.x, 10.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.y, 20.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[0].world.z, 5.0);
  ASSERT_EQ(h.frame.vector_inputs.size(), 1U);
  EXPECT_EQ(h.frame.vector_inputs[0].tick, k);
  EXPECT_DOUBLE_EQ(h.frame.vector_inputs[0].world.x, 1.0);
  EXPECT_DOUBLE_EQ(h.frame.vector_inputs[0].world.y, 0.0);
  EXPECT_DOUBLE_EQ(h.frame.vector_inputs[0].world.z, 0.0);
  at_target(h);
  for (std::uint64_t n = 1; n <= 2; ++n) {
    const std::size_t before = h.edges().size();
    const StepOutput out = h.tick();
    const std::string where = "K+" + std::to_string(n);
    EXPECT_EQ(h.edges().size(), before) << where;
    expect_track_setpoint(out, kLocalL, 0.25, kLocalVelocity, where);
    expect_distance(out, 0.0, where);
    EXPECT_EQ(h.frame.point_calls_at(k + n), 1) << where;
    EXPECT_EQ(h.frame.vector_calls_at(k + n), 1) << where;
  }
  const std::size_t before = h.edges().size();
  const StepOutput reach = h.tick();  // K+3
  expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
  EXPECT_EQ(reach.commands, kLandOnly);
  expect_track_setpoint(reach, kLocalL, 0.25, std::nullopt, "K+3");
  land_and_disarm(h);
  EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
  EXPECT_EQ(h.frame.vector_calls_from(k + 4), 0);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- 신선도와 feedforward ----

TEST(Track, FreshnessAndFeedforward)
{
  struct Case
  {
    const char * name;
    // 표본을 바꾼다(base는 stamp_ns = now_ns인 기본 표본).
    std::function<TargetSample(TargetSample)> sample;
    bool vector_none;
    bool fresh_with_velocity;  // 속도가 실린다
    std::uint64_t reached;     // 0이면 완료 없이 ITEM_TIMEOUT
  };
  const std::vector<Case> cases = {
    {"age 0.1 s is fresh",
     [](TargetSample s) {
       s.stamp_ns -= 100 * kMs;
       return s;
     },
     false, true, 3},
    {"age 0.15 s is not fresh",
     [](TargetSample s) {
       s.stamp_ns -= 150 * kMs;
       return s;
     },
     false, false, 0},
    {"velocity_valid false",
     [](TargetSample s) {
       s.velocity_valid = false;
       return s;
     },
     false, false, 3},
    {"vector transform gives no value", [](TargetSample s) { return s; }, true, false, 3},
    {"future stamp is age 0",
     [](TargetSample s) {
       s.stamp_ns += 200 * kMs;
       return s;
     },
     false, true, 3},
  };
  for (const Case & c : cases) {
    SCOPED_TRACE(c.name);
    Harness h(ground_track_mission("tf", {land_item()}));
    add_target(h);
    const auto change = c.sample;
    h.target_hook = [change](const std::string &, std::uint64_t, const TargetSample & base)
      -> std::optional<TargetSample> { return change(base); };
    if (c.vector_none) {
      h.frame.vector_hook = [](std::uint64_t, const Vec3 &) -> std::optional<Vec3> {
        return std::nullopt;
      };
    }
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    const std::uint64_t end = run_track(h, k, kTimeoutTicks);
    const std::uint64_t last = end == 0 ? kTimeoutTicks : end;
    for (std::uint64_t n = 0; n < last; ++n) {
      const std::string where = "K+" + std::to_string(n);
      const bool vector_called = c.fresh_with_velocity || c.vector_none;
      EXPECT_EQ(h.frame.vector_calls_at(k + n), vector_called ? 1 : 0) << where;
      expect_track_setpoint(
        out_at(h, k + n), kLocalL, 0.25,
        c.fresh_with_velocity ? std::optional<Vec3>(kLocalVelocity) : std::nullopt, where);
      if (n >= 1) {
        expect_distance(out_at(h, k + n), 0.0, where);
      }
    }
    if (c.reached != 0) {
      EXPECT_EQ(end, c.reached);
      expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
      land_and_disarm(h);
      expect_end(h, "SUCCEEDED/NONE", 3, 2);
    } else {
      EXPECT_EQ(end, kTimeoutTicks);
      expect_cell(
        h, "ITEM.TRACK_ENTITY", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
      ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
      EXPECT_EQ(
        termination_or_empty(h).detail, "item 1 (TRACK_ENTITY) timeout; cleanup: Hold confirmed");
      expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
    }
  }
}

TEST(Track, StaleTickBreaksTheRun)
{
  for (const bool sample_at_k4 : {false, true}) {
    SCOPED_TRACE(sample_at_k4 ? "sample at K+4" : "no sample K+2..K+4");
    Harness h(ground_track_mission("ts", {land_item()}));
    add_target(h);
    const std::uint64_t k = prepare_track_start(h);
    const std::uint64_t last_gap = sample_at_k4 ? k + 3 : k + 4;
    omit_target_when(
      h, [k, last_gap](std::uint64_t tick) { return tick >= k + 2 && tick <= last_gap; });
    tick_track_start(h, k);
    const std::size_t before = h.edges().size();
    const std::uint64_t end = run_track(h, k, kTimeoutTicks, [&h](std::uint64_t n) {
      if (n == 2) {
        at_target(h);
      }
    });
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
    if (sample_at_k4) {
      EXPECT_EQ(end, 4U);
    } else {
      EXPECT_EQ(end, 7U);
      // K+2(나이 0.05 s), K+3(0.1 s)은 신선, K+4(0.15 s)는 신선하지 않다.
      expect_track_setpoint(out_at(h, k + 2), kLocalL, 0.25, kLocalVelocity, "K+2");
      expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, kLocalVelocity, "K+3");
      expect_track_setpoint(out_at(h, k + 4), kLocalL, 0.25, std::nullopt, "K+4");
      expect_distance(out_at(h, k + 4), 0.0, "K+4");
      EXPECT_EQ(h.frame.vector_calls_at(k + 4), 0);
      EXPECT_EQ(h.frame.point_calls_at(k + 4), 1);
    }
    land_and_disarm(h);
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
}

TEST(Track, NoSampleAtStartHoldsThePreviousSetpoint)
{
  Harness h(ground_track_mission("tn", {land_item()}));
  add_target(h);
  std::uint64_t k = 0;  // 표적 표본은 K+10부터(그 전에는 한 번도 주지 않는다)
  omit_target_when(h, [&k](std::uint64_t tick) { return k == 0 || tick < k + 10; });
  k = prepare_track_start(h);
  at_target(h);
  tick_track_start(h, k);
  const std::size_t before = h.edges().size();
  const std::uint64_t end = run_track(h, k, kTimeoutTicks);
  EXPECT_EQ(end, 12U);
  expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
  for (std::uint64_t n = 0; n <= 9; ++n) {
    const std::string where = "K+" + std::to_string(n);
    expect_track_setpoint(out_at(h, k + n), Vec3{1.0, 2.0, -5.0}, 0.25, std::nullopt, where);
    expect_distance(out_at(h, k + n), std::nullopt, where);
    EXPECT_EQ(h.frame.point_calls_at(k + n), 0) << where;
    EXPECT_EQ(h.frame.vector_calls_at(k + n), 0) << where;
  }
  expect_track_setpoint(out_at(h, k + 10), kLocalL, 0.25, kLocalVelocity, "K+10");
  expect_distance(out_at(h, k + 10), 0.0, "K+10");
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- TARGET_LOST ----

TEST(Track, LostBeforeFirstSample)
{
  Harness h(ground_track_mission("tl0", {land_item()}));
  const std::uint64_t k = start_track(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), 21U);
  EXPECT_EQ(h.edges().size(), before + 2U);  // K+21의 두 기록뿐(K+20은 경과 1.0 s라 소실이 아니다)
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-", {}, before);
  expect_cell(
    h, "CLEANUP.TARGET_LOST.NONE", Event::kEnterAir, "CLEANUP.TARGET_LOST.AIR", "-", {}, before);
  const StepOutput & lost = out_at(h, k + 21);
  EXPECT_EQ(lost.commands, kHoldOnly);
  expect_track_setpoint(lost, Vec3{1.0, 2.0, -5.0}, 0.25, std::nullopt, "K+21");
  ASSERT_TRUE(lost.feedback.has_value());
  EXPECT_EQ(lost.feedback->phase, FeedbackPhase::kExecuting);
  const std::size_t hold_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(h.tick_no - 1, k + 24);
  expect_cell(
    h, "CLEANUP.TARGET_LOST.AIR", Event::kHoldConfirmed, "DONE", "ABORTED/TARGET_LOST", {},
    hold_before);
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 1 (TRACK_ENTITY) target 't1' lost: no valid sample since item start; cleanup: Hold "
    "confirmed");
  EXPECT_TRUE(h.frame.point_calls.empty());
  EXPECT_EQ(h.frame.vector_calls, 0);
  expect_end(h, "ABORTED/TARGET_LOST", 1, 1);
}

TEST(Track, LostAfterLastSample)
{
  Harness h(ground_track_mission("tl1", {land_item()}));
  add_target(h);
  const std::uint64_t k = prepare_track_start(h);
  omit_target_when(h, [k](std::uint64_t tick) { return tick > k + 5; });
  tick_track_start(h, k);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), 26U);
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-", {}, before);
  for (std::uint64_t n = 6; n <= 25; ++n) {
    const std::string where = "K+" + std::to_string(n);
    expect_track_setpoint(
      out_at(h, k + n), kLocalL, 0.25, n <= 7 ? std::optional<Vec3>(kLocalVelocity) : std::nullopt,
      where);
  }
  EXPECT_EQ(out_at(h, k + 26).commands, kHoldOnly);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 1 (TRACK_ENTITY) target 't1' lost: last valid sample older than target_timeout; "
    "cleanup: Hold confirmed");
  expect_end(h, "ABORTED/TARGET_LOST", 1, 1);
}

TEST(Track, SampleFromEarlierItemCountsForLoss)
{
  Harness h(mission_of(
    "tl2",
    {takeoff_item(), track_entity_item(), loiter_item(2, 10), track_entity_item(), land_item()}));
  add_target(h);
  std::uint64_t j = 0;
  h.target_hook = [&j](
                    const std::string &, std::uint64_t tick,
                    const TargetSample & base) -> std::optional<TargetSample> {
    if (j != 0 && tick > j) {
      return std::nullopt;
    }
    return base;
  };
  const std::uint64_t k = start_track(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
  j = k + 3;
  expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LOITER", "-", {}, before);
  const std::size_t loiter_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 3U; }, 100));
  const std::uint64_t m = h.tick_no - 1;
  EXPECT_EQ(m, j + 40);
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.TRACK_ENTITY", "-", {}, loiter_before);
  for (std::uint64_t tick = j + 1; tick < m; ++tick) {
    expect_track_setpoint(out_at(h, tick), kLocalL, 0.25, std::nullopt, "LOITER");
  }
  // m: j 표본의 L, 속도 없음(나이 2 s).
  expect_track_setpoint(out_at(h, m), kLocalL, 0.25, std::nullopt, "m");
  const std::size_t lost_before = h.edges().size();
  h.tick();  // m+1
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-", {}, lost_before);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail,
    "item 3 (TRACK_ENTITY) target 't1' lost: last valid sample older than target_timeout; "
    "cleanup: Hold confirmed");
  expect_end(h, "ABORTED/TARGET_LOST", 3, 3);
}

TEST(Track, TargetLostWinsOverItemTimeout)
{
  {
    SCOPED_TRACE("lost and timeout on the same tick");
    ItemSpec track = track_entity_item();
    track.timeout = seconds(2);
    Harness h(mission_of("tlt", {takeoff_item(), track, land_item()}));
    add_target(h);
    const std::uint64_t k = prepare_track_start(h);
    omit_target_when(h, [k](std::uint64_t tick) { return tick > k + 19; });
    tick_track_start(h, k);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, 100), 40U);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-",
      {Event::kItemTimeout}, before);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    for (const TransitionEdge & edge : h.edges()) {
      EXPECT_FALSE(edge.to.cause == CleanupCause::kItemTimeout && edge.to.stage == Stage::kCleanup);
    }
    expect_end(h, "ABORTED/TARGET_LOST", 1, 1);
  }
  {
    SCOPED_TRACE("timeout 1 s without samples times out first");
    ItemSpec track = track_entity_item();
    track.timeout = seconds(1);
    Harness h(mission_of("tlt1", {takeoff_item(), track, land_item()}));
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, 100), 20U);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    EXPECT_EQ(h.tick_no - 1, k + 23);
    for (const TransitionEdge & edge : h.edges()) {
      EXPECT_NE(edge.event, Event::kTargetLost);
    }
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "item 1 (TRACK_ENTITY) timeout (no frame transform since item start); cleanup: Hold "
      "confirmed");
    expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
  }
}

// ---- ITEM_TIMEOUT과 완료 ----

TEST(Track, ItemTimeout)
{
  Harness h(ground_track_mission("tt", {land_item()}));
  add_target(h);
  const std::uint64_t k = start_track(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), kTimeoutTicks);
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {}, before);
  for (std::uint64_t n = 0; n < kTimeoutTicks; ++n) {
    ASSERT_TRUE(out_at(h, k + n).setpoint.has_value());
    EXPECT_TRUE(out_at(h, k + n).setpoint->velocity_valid) << "K+" << n;
  }
  const StepOutput & end = out_at(h, k + kTimeoutTicks);
  EXPECT_EQ(end.commands, kHoldOnly);
  expect_track_setpoint(end, kLocalL, 0.25, std::nullopt, "K+200");
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  EXPECT_EQ(
    termination_or_empty(h).detail, "item 1 (TRACK_ENTITY) timeout; cleanup: Hold confirmed");
  expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
}

TEST(Track, TimeoutWinsOverThirdSampleOnSameTick)
{
  for (const std::uint64_t arrive : {198U, 197U}) {
    SCOPED_TRACE("arrive K+" + std::to_string(arrive));
    Harness h(ground_track_mission("tw", {land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    const std::uint64_t end = run_track(h, k, kTimeoutTicks, [&h, arrive](std::uint64_t n) {
      if (n == arrive) {
        at_target(h);
      }
    });
    if (arrive == 198U) {
      EXPECT_EQ(end, kTimeoutTicks);
      expect_cell(
        h, "ITEM.TRACK_ENTITY", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
        {Event::kTrackEntityReached}, before);
      EXPECT_EQ(out_at(h, k + kTimeoutTicks).commands, kHoldOnly);
      ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
      EXPECT_EQ(h.count_command(CommandKind::kNavLand), 0);
      expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
    } else {
      EXPECT_EQ(end, 199U);
      expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
    }
  }
}

TEST(Track, MovingTarget)
{
  Harness h(ground_track_mission("tm", {land_item()}));
  add_target(h);
  const std::uint64_t k = prepare_track_start(h);
  h.target_hook = [k](
                    const std::string &, std::uint64_t tick,
                    const TargetSample & base) -> std::optional<TargetSample> {
    TargetSample s = base;
    s.position.x = 10.0 + 0.05 * static_cast<double>(tick - k);
    return s;
  };
  tick_track_start(h, k);
  const std::size_t before = h.edges().size();
  const std::uint64_t end = run_track(h, k, kTimeoutTicks, [&h](std::uint64_t n) {
    move_to(h, 20.0, 10.0 + 0.05 * static_cast<double>(n), -5.0);
  });
  EXPECT_EQ(end, 3U);
  expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
  for (std::uint64_t n = 0; n <= 2; ++n) {
    const std::string where = "K+" + std::to_string(n);
    expect_track_setpoint(
      out_at(h, k + n), Vec3{20.0, 10.0 + 0.05 * static_cast<double>(n), -5.0}, 0.25,
      kLocalVelocity, where);
  }
  for (std::uint64_t n = 0; n <= 3; ++n) {
    const HarnessFramePort::PointCall & call = h.frame.point_calls[n];
    EXPECT_EQ(call.tick, k + n);
    EXPECT_DOUBLE_EQ(call.world.x, 10.0 + 0.05 * static_cast<double>(n));
  }
}

TEST(Track, MissingPointTransformBreaksTheRun)
{
  Harness h(ground_track_mission("tp", {land_item()}));
  add_target(h);
  const std::uint64_t k = prepare_track_start(h);
  h.frame.hook = [k](std::uint64_t tick, const Vec3 & w) -> std::optional<Vec3> {
    if (tick == k + 2) {
      return std::nullopt;
    }
    return HarnessFramePort::axis(w);
  };
  tick_track_start(h, k);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), 5U);
  expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
  const StepOutput & gap = out_at(h, k + 2);
  expect_track_setpoint(gap, kLocalL, 0.25, std::nullopt, "K+2");
  expect_distance(gap, std::nullopt, "K+2");
  EXPECT_EQ(h.frame.vector_calls_at(k + 2), 0);
  EXPECT_EQ(h.frame.point_calls_at(k + 2), 1);
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 3, 2);
}

// ---- port 호출 규율: 완료 tick에 다음 항목도 TRACK_ENTITY ----

TEST(FramePortCalls, TrackToTrackCallsTwiceOnCompletionTick)
{
  ItemSpec second = track_entity_item();
  second.track_entity.target_id = "t2";
  Harness h(mission_of("tt2", {takeoff_item(), track_entity_item(), second, land_item()}));
  add_target(h);
  add_target(h, "t2", Vec3{0.0, 0.0, 0.0});
  const std::uint64_t k = start_track(h);
  at_target(h);
  const std::size_t before = h.edges().size();
  EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
  const std::uint64_t j = k + 3;
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.TRACK_ENTITY", "-", {}, before);
  ASSERT_EQ(h.frame.point_calls_at(j), 2);
  EXPECT_EQ(h.frame.vector_calls_at(j), 2);
  const std::size_t last = h.frame.point_calls.size();
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 2].world.x, 10.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 2].world.y, 20.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 2].world.z, 5.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.x, 0.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.y, 0.0);
  EXPECT_DOUBLE_EQ(h.frame.point_calls[last - 1].world.z, 5.0);
  expect_track_setpoint(out_at(h, j), Vec3{0.0, 0.0, -5.0}, 0.25, kLocalVelocity, "j");
  move_to(h, 0.0, 0.0, -5.0);
  const std::size_t second_before = h.edges().size();
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 3U; }, 10));
  expect_cell(
    h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, second_before);
  land_and_disarm(h);
  expect_end(h, "SUCCEEDED/NONE", 4, 3);
}

// ---- yaw ----

TEST(Track, YawIsFixedAtItemStart)
{
  const double fixed = kPi / 2.0 - 0.3;
  {
    SCOPED_TRACE("MODE_FIXED");
    ItemSpec track = track_entity_item();
    track.track_entity.yaw.mode = yaw_mode::kFixed;
    track.track_entity.yaw.yaw_rad = 0.3;
    Harness h(mission_of("ty", {takeoff_item(), track, land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    run_track(h, k, 5);
    for (std::uint64_t n = 0; n <= 5; ++n) {
      expect_track_setpoint(
        out_at(h, k + n), kLocalL, fixed, kLocalVelocity, "K+" + std::to_string(n));
    }
  }
  {
    SCOPED_TRACE("MODE_FIXED, samples from K+5");
    ItemSpec track = track_entity_item();
    track.track_entity.yaw.mode = yaw_mode::kFixed;
    track.track_entity.yaw.yaw_rad = 0.3;
    Harness h(mission_of("ty5", {takeoff_item(), track, land_item()}));
    add_target(h);
    std::uint64_t k = 0;  // 표적 표본은 K+5부터
    omit_target_when(h, [&k](std::uint64_t tick) { return k == 0 || tick < k + 5; });
    k = prepare_track_start(h);
    tick_track_start(h, k);
    run_track(h, k, 6);
    for (std::uint64_t n = 0; n <= 4; ++n) {
      expect_track_setpoint(
        out_at(h, k + n), Vec3{1.0, 2.0, -5.0}, 0.25, std::nullopt, "K+" + std::to_string(n));
    }
    for (std::uint64_t n = 5; n <= 6; ++n) {
      expect_track_setpoint(
        out_at(h, k + n), kLocalL, fixed, kLocalVelocity, "K+" + std::to_string(n));
    }
  }
  {
    SCOPED_TRACE("TAKEOFF MODE_FIXED then TRACK_ENTITY MODE_KEEP");
    ItemSpec takeoff = takeoff_item();
    takeoff.takeoff.yaw.mode = yaw_mode::kFixed;
    takeoff.takeoff.yaw.yaw_rad = 1.0;
    Harness h(mission_of("tyk", {takeoff, track_entity_item(), land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    expect_track_setpoint(out_at(h, k), kLocalL, kPi / 2.0 - 1.0, kLocalVelocity, "K");
  }
}

// ---- 다음 항목 ----

TEST(Track, NextItems)
{
  {
    SCOPED_TRACE("LOITER");
    Harness h(ground_track_mission("tnl", {loiter_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LOITER", "-", {}, before);
    expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, std::nullopt, "K+3");
    ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 200));
    for (std::uint64_t tick = k + 4; tick < h.tick_no; ++tick) {
      expect_track_setpoint(out_at(h, tick), kLocalL, 0.25, std::nullopt, "LOITER");
    }
    EXPECT_EQ(h.frame.point_calls_from(k + 4), 0);
    EXPECT_EQ(h.frame.vector_calls_from(k + 4), 0);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
  {
    SCOPED_TRACE("RTL");
    Harness h(ground_track_mission("tnr", {rtl_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.RTL", "-", {}, before);
    EXPECT_EQ(out_at(h, k + 3).commands, kRtlOnly);
    expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, std::nullopt, "K+3");
    land_and_disarm(h);
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
  {
    SCOPED_TRACE("GOTO");
    Harness h(ground_track_mission("tng", {goto_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.GOTO", "-", {}, before);
    expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, std::nullopt, "K+3");
    EXPECT_EQ(h.frame.vector_calls_at(k + 3), 1);
    EXPECT_EQ(h.frame.point_calls_at(k + 3), 2);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 20));
    EXPECT_EQ(h.frame.vector_calls_from(k + 4), 0);
    expect_end(h, "SUCCEEDED/NONE", 3, 2);
  }
  {
    SCOPED_TRACE("last item goes to mission end");
    Harness h(ground_track_mission("tne", {}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "CLEANUP.MISSION_END.NONE", "-", {},
      before);
    EXPECT_EQ(out_at(h, k + 3).commands, kHoldOnly);
    expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, std::nullopt, "K+3");
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    EXPECT_EQ(h.tick_no - 1, k + 6);
    EXPECT_EQ(termination_or_empty(h).detail, "");
    expect_end(h, "SUCCEEDED/NONE", 2, 1);
  }
  {
    SCOPED_TRACE("GOTO then TRACK_ENTITY");
    Harness h(mission_of("tgt", {takeoff_item(), goto_item(), track_entity_item(), land_item()}));
    add_target(h);
    h.frame.mode = FrameMode::kAxis;
    h.drive_to_takeoff();
    h.world.landed = false;
    h.world.z = -5.0;
    const std::uint64_t k = h.tick_no;
    h.tick();
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 3U);
    expect_cell(h, "ITEM.GOTO", Event::kGotoReached, "ITEM.TRACK_ENTITY", "-", {}, before);
    expect_track_setpoint(out_at(h, k + 3), kLocalL, 0.25, kLocalVelocity, "K+3");
    EXPECT_EQ(h.frame.point_calls_at(k + 3), 2);
    EXPECT_EQ(h.frame.vector_calls_at(k + 3), 1);
  }
  {
    SCOPED_TRACE("LOITER then TRACK_ENTITY");
    Harness h(
      mission_of("tlt", {takeoff_item(), loiter_item(2, 10), track_entity_item(), land_item()}));
    add_target(h);
    h.frame.mode = FrameMode::kAxis;
    h.drive_to_loiter();
    const std::size_t before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 2U; }, 100));
    expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.TRACK_ENTITY", "-", {}, before);
    expect_track_setpoint(out_at(h, h.tick_no - 1), kLocalL, 0.25, kLocalVelocity, "LOITER end");
  }
}

// ---- 공중 Offboard 진입 ----

TEST(Track, AirEntry)
{
  {
    SCOPED_TRACE("[TRACK_ENTITY]");
    Harness h(mission_of("at", {track_entity_item()}));
    add_target(h);
    const std::size_t before = h.edges().size();
    const std::uint64_t c = start_air_track(h);
    expect_cell(
      h, "PREPARING.AIR_OFFBOARD_SEEN", Event::kOffboardConfirmed, "ITEM.TRACK_ENTITY", "-", {},
      before);
    for (std::uint64_t t = 1; t < c; ++t) {
      EXPECT_EQ(h.frame.point_calls_at(t), 0) << "tick " << t;
    }
    expect_track_setpoint(out_at(h, c), kLocalL, 0.25, kLocalVelocity, "C");
    at_target(h);
    const std::size_t reach_before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 10));
    EXPECT_EQ(h.tick_no - 1, c + 3);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "CLEANUP.MISSION_END.NONE", "-", {},
      reach_before);
    EXPECT_EQ(out_at(h, c + 3).commands, kHoldOnly);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    EXPECT_EQ(h.count_command(CommandKind::kArm), 0);
    EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
    expect_end(h, "SUCCEEDED/NONE", 1, 0);
  }
  {
    SCOPED_TRACE("[TRACK_ENTITY, LAND]");
    Harness h(mission_of("atl", {track_entity_item(), land_item()}));
    add_target(h);
    const std::uint64_t c = start_air_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 10));
    EXPECT_EQ(h.tick_no - 1, c + 3);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LAND", "-", {}, before);
    land_and_disarm(h);
    expect_end(h, "SUCCEEDED/NONE", 2, 1);
  }
  {
    SCOPED_TRACE("[LOITER, TRACK_ENTITY]");
    Harness h(mission_of("alt", {loiter_item(), track_entity_item()}));
    add_target(h);
    start_air_track(h);
    const std::size_t before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 200));
    expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.TRACK_ENTITY", "-", {}, before);
    expect_track_setpoint(out_at(h, h.tick_no - 1), kLocalL, 0.25, kLocalVelocity, "LOITER end");
  }
  {
    SCOPED_TRACE("precondition names TRACK_ENTITY");
    Harness h(mission_of("atp", {track_entity_item()}));
    add_target(h);
    h.frame.mode = FrameMode::kAxis;
    h.start_in_air();
    h.world.landed = true;
    h.tick();
    const std::string detail = termination_or_empty(h).detail;
    EXPECT_EQ(
      detail.rfind(
        "TRACK_ENTITY needs not landed, ARMED, nav_state and user intention AUTO_LOITER, no "
        "failsafe (",
        0),
      0U)
      << detail;
    expect_end(h, "ABORTED/PRECONDITION_FAILED", 0, 0);
  }
  {
    SCOPED_TRACE("no samples");
    Harness h(mission_of("at0", {track_entity_item()}));
    const std::uint64_t c = start_air_track(h);
    expect_track_setpoint(out_at(h, c), Vec3{1.0, 2.0, -5.0}, 0.25, std::nullopt, "C");
    const std::size_t before = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.view().stage != Stage::kItem; }, 30));
    EXPECT_EQ(h.tick_no - 1, c + 21);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-", {}, before);
    EXPECT_EQ(out_at(h, c + 21).commands, kHoldOnly);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    EXPECT_EQ(
      termination_or_empty(h).detail,
      "item 0 (TRACK_ENTITY) target 't1' lost: no valid sample since item start; cleanup: Hold "
      "confirmed");
    expect_end(h, "ABORTED/TARGET_LOST", 0, 0);
  }
}

// ---- 취소 ----

TEST(Track, Cancel)
{
  {
    SCOPED_TRACE("cancel in TRACK_ENTITY");
    Harness h(ground_track_mission("tc", {land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    h.cancel_sticky = true;
    EXPECT_EQ(run_track(h, k, kTimeoutTicks), 1U);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
    const StepOutput & cancel = out_at(h, k + 1);
    EXPECT_EQ(cancel.commands, kHoldOnly);
    expect_track_setpoint(cancel, kLocalL, 0.25, std::nullopt, "K+1");
    ASSERT_TRUE(cancel.feedback.has_value());
    EXPECT_EQ(cancel.feedback->phase, FeedbackPhase::kCanceling);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    expect_end(h, "CANCELED/NONE", 1, 1);
  }
  {
    SCOPED_TRACE("TARGET_LOST with cancel");
    Harness h(ground_track_mission("tcl", {land_item()}));
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_track(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 21; }), 21U);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTargetLost, "CLEANUP.TARGET_LOST.NONE", "-", {Event::kCancel},
      before);
    const std::size_t after = h.edges().size();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    for (std::size_t i = after; i < h.edges().size(); ++i) {
      EXPECT_NE(h.edges()[i].event, Event::kCancel);
    }
    expect_end(h, "ABORTED/TARGET_LOST", 1, 1);
  }
  {
    SCOPED_TRACE("ITEM_TIMEOUT with cancel");
    Harness h(ground_track_mission("tct", {land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_track(
        h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= kTimeoutTicks; }),
      kTimeoutTicks);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
      {Event::kCancel}, before);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    expect_end(h, "ABORTED/ITEM_TIMEOUT", 1, 1);
  }
  {
    SCOPED_TRACE("last TRACK_ENTITY reached with cancel");
    Harness h(ground_track_mission("tcr", {}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_track(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
    expect_cell(
      h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "CLEANUP.MISSION_END.NONE", "-",
      {Event::kCancel}, before);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    expect_end(h, "SUCCEEDED/NONE", 2, 1);
  }
  {
    SCOPED_TRACE("immediate end with cancel");
    Harness h(ground_track_mission("tci", {land_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_track(
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
      h, "ITEM.TRACK_ENTITY", Event::kMonitorModeExternal, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
      {Event::kCancel}, before);
    const StepOutput & end = out_at(h, k + 3);
    EXPECT_EQ(end.commands, kNoCommands);
    EXPECT_FALSE(end.setpoint.has_value());
    expect_end(h, "ABORTED/EXTERNAL_MODE_CHANGE", 1, 1);
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
    EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);
  }
  {
    SCOPED_TRACE("reached then cancel in the next item");
    Harness h(ground_track_mission("tcn", {loiter_item()}));
    add_target(h);
    const std::uint64_t k = start_track(h);
    at_target(h);
    const std::size_t before = h.edges().size();
    EXPECT_EQ(
      run_track(h, k, kTimeoutTicks, [&h](std::uint64_t n) { h.cancel_sticky = n >= 3; }), 3U);
    expect_cell(h, "ITEM.TRACK_ENTITY", Event::kTrackEntityReached, "ITEM.LOITER", "-", {}, before);
    expect_cell(h, "ITEM.LOITER", Event::kCancel, "CLEANUP.CANCEL.NONE", "-", {}, before);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
    expect_end(h, "CANCELED/NONE", 2, 2);
  }
}

// ---- 감시 표 ----

struct MonitorCase
{
  const char * name;
  Event event;
  const char * reason;
  std::vector<Event> also;
  bool with_target;           // 표적 표본을 tick마다 준다
  std::uint64_t last_target;  // 0이 아니면 이 offset 뒤로 표적 표본을 주지 않는다
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
  Harness h(ground_track_mission("tmon", {land_item()}));
  if (c.with_target) {
    add_target(h);
  }
  const std::uint64_t k = prepare_track_start(h);
  if (c.last_target != 0) {
    const std::uint64_t last = k + c.last_target;
    omit_target_when(h, [last](std::uint64_t tick) { return tick > last; });
  }
  tick_track_start(h, k);
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
  expect_cell(h, "ITEM.TRACK_ENTITY", c.event, "DONE", c.reason, c.also, before);
  const StepOutput & end = out_at(h, k + c.end);
  EXPECT_EQ(end.commands, c.commands);
  EXPECT_FALSE(end.setpoint.has_value());
  h.clock.fail = false;
  expect_end(h, c.reason, 1, 1);
}

std::function<bool(Harness &, std::uint64_t)> at(
  std::uint64_t when, std::function<void(Harness &)> f)
{
  return [when, f](Harness & h, std::uint64_t n) {
    if (n == when) {
      f(h);
    }
    return true;
  };
}

// 단일 행: K+3에 위치는 목표점 밖이고 표적은 신선하다(ITEM_TIMEOUT, 완료, TARGET_LOST가 거짓).
TEST(TrackMonitor, SingleRows)
{
  const std::vector<MonitorCase> cases = {
    {"rank 1",
     Event::kMonitorTimestampFailure,
     "ABORTED/INTERNAL",
     {},
     true,
     0,
     at(3, [](Harness & h) { h.clock.fail = true; }),
     3,
     kNoCommands},
    {"rank 2",
     Event::kMonitorIdentityMismatch,
     "ABORTED/INTERNAL",
     {},
     true,
     0,
     at(3, [](Harness & h) { h.world.identity = IdentityCheck::kMismatch; }),
     3,
     kDisarmOnly},
    {"rank 3",
     Event::kMonitorLinkLost,
     "ABORTED/LINK_LOST",
     {},
     true,
     0,
     [](Harness &, std::uint64_t) { return false; },
     40,
     kNoCommands},
    {"rank 4",
     Event::kMonitorDisarmedInAir,
     "ABORTED/FAILSAFE",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kDisarmed, false, NavMode::kOffboard, NavMode::kOffboard, false);
       }),
     3,
     kNoCommands},
    {"rank 5 external",
     Event::kMonitorDisarmedOnGround,
     "ABORTED/EXTERNAL_DISARM",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, false);
       }),
     3,
     kNoCommands},
    {"rank 5 failsafe",
     Event::kMonitorDisarmedOnGround,
     "ABORTED/FAILSAFE",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, true);
       }),
     3,
     kNoCommands},
    {"rank 6",
     Event::kMonitorModeFailsafe,
     "ABORTED/FAILSAFE",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kArmed, false, NavMode::kHold, NavMode::kHold, true);
       }),
     3,
     kNoCommands},
    {"rank 7",
     Event::kMonitorModeExternal,
     "ABORTED/EXTERNAL_MODE_CHANGE",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kArmed, false, NavMode::kRtl, NavMode::kRtl, false);
       }),
     3,
     kNoCommands},
    {"rank 8",
     Event::kMonitorModeDefensive,
     "ABORTED/FAILSAFE",
     {},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kArmed, false, NavMode::kOther, NavMode::kOffboard, false);
       }),
     3,
     kNoCommands},
    {"pair DISARMED in air and mode failsafe",
     Event::kMonitorDisarmedInAir,
     "ABORTED/FAILSAFE",
     {Event::kMonitorModeFailsafe},
     true,
     0,
     at(
       3,
       [](Harness & h) {
         set_status(h, Arming::kDisarmed, false, NavMode::kHold, NavMode::kHold, true);
       }),
     3,
     kNoCommands},
  };
  for (const MonitorCase & c : cases) {
    run_monitor_case(c);
  }
}

// setpoint 순서의 대표 행 넷과 TARGET_LOST, ITEM_TIMEOUT, 완료의 겹침. TARGET_LOST 대표는 표적
// 표본 없이 K+21(순위 3은 표본을 K+19까지 주고 status를 K까지 주어 소실과 끊김이 K+40에 함께 난다).
TEST(TrackMonitor, RepresentativeRowsOverTargetLostTimeoutAndCompletion)
{
  const std::uint64_t t = kTimeoutTicks;
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
  const std::vector<Event> lost = {Event::kTargetLost};
  const std::vector<Event> timeout = {Event::kItemTimeout};
  const std::vector<Event> reached = {Event::kTrackEntityReached};
  const auto clock_fail = [](Harness & h) { h.clock.fail = true; };
  const auto ground_disarm = [](Harness & h) {
    set_status(h, Arming::kDisarmed, true, NavMode::kOffboard, NavMode::kOffboard, false);
  };
  const auto rtl = [](Harness & h) {
    set_status(h, Arming::kArmed, false, NavMode::kRtl, NavMode::kRtl, false);
  };
  const std::vector<MonitorCase> cases = {
    {"lost rank 1", Event::kMonitorTimestampFailure, "ABORTED/INTERNAL", lost, false, 0,
     at(21, clock_fail), 21, kNoCommands},
    {"lost rank 3", Event::kMonitorLinkLost, "ABORTED/LINK_LOST", lost, true, 19,
     [](Harness &, std::uint64_t) { return false; }, 40, kNoCommands},
    {"lost rank 5", Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM", lost, false, 0,
     at(21, ground_disarm), 21, kNoCommands},
    {"lost rank 7", Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE", lost, false, 0,
     at(21, rtl), 21, kNoCommands},
    {"timeout rank 1", Event::kMonitorTimestampFailure, "ABORTED/INTERNAL", timeout, true, 0,
     at(t, clock_fail), t, kNoCommands},
    {"timeout rank 3", Event::kMonitorLinkLost, "ABORTED/LINK_LOST", timeout, true, 0,
     [t](Harness &, std::uint64_t n) { return n < t - 39; }, t, kNoCommands},
    {"timeout rank 5", Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM", timeout, true, 0,
     at(t, ground_disarm), t, kNoCommands},
    {"timeout rank 7", Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE", timeout, true,
     0, at(t, rtl), t, kNoCommands},
    {"reached rank 1", Event::kMonitorTimestampFailure, "ABORTED/INTERNAL", reached, true, 0,
     reach_and_at(3, clock_fail), 3, kNoCommands},
    {"reached rank 3", Event::kMonitorLinkLost, "ABORTED/LINK_LOST", reached, true, 0,
     [](Harness & h, std::uint64_t n) {
       if (n == 38) {
         at_target(h);
       }
       return false;
     },
     40, kNoCommands},
    {"reached rank 5", Event::kMonitorDisarmedOnGround, "ABORTED/EXTERNAL_DISARM", reached, true, 0,
     reach_and_at(3, ground_disarm), 3, kNoCommands},
    {"reached rank 7", Event::kMonitorModeExternal, "ABORTED/EXTERNAL_MODE_CHANGE", reached, true,
     0, reach_and_at(3, rtl), 3, kNoCommands},
  };
  for (const MonitorCase & c : cases) {
    run_monitor_case(c);
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
