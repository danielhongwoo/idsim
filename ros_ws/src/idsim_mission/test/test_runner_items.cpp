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

// setpoint 항목(TAKEOFF, LOITER)과 상태기 안의 비행 중 감시(decisions.md 쟁점 4 "항목", "비행 중
// 감시"). 순위마다 한 건, 엇갈려 시작하는 경우, 순위 5 이력의 항목 경계, disarm 분류의 고정.
// 감시 표의 행 순위는 재실측 (4) 전까지 잠정이다.

#include <gtest/gtest.h>

#include <functional>
#include <string>
#include <vector>

#include "idsim_mission/core/rules.hpp"
#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

constexpr double kPi = 3.14159265358979323846;

TEST(Takeoff, TargetIsStartPositionMinusHeightWithKeepYaw)
{
  Harness h(standard_mission());
  h.drive_to_takeoff();
  const SetpointOut sp = h.view().setpoint;
  EXPECT_EQ(sp.kind, SetpointKind::kTarget);
  EXPECT_DOUBLE_EQ(sp.x, 1.0);
  EXPECT_DOUBLE_EQ(sp.y, 2.0);
  EXPECT_DOUBLE_EQ(sp.z, -5.0);
  EXPECT_DOUBLE_EQ(sp.yaw_ned, 0.25);
}

TEST(Takeoff, FixedYawIsConvertedToNed)
{
  MissionSpec m = standard_mission();
  m.items[0].takeoff.yaw.mode = yaw_mode::kFixed;
  m.items[0].takeoff.yaw.yaw_rad = 0.0;  // world ENU 동쪽
  Harness h(m);
  h.tick();
  EXPECT_NEAR(h.view().setpoint.yaw_ned, kPi / 2.0, 1e-12);
}

TEST(Takeoff, CompletesInsideAcceptanceOnly)
{
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -4.6;  // 0.4 m 남음 > 0.3
  for (int i = 0; i < 5; ++i) {
    const StepOutput out = h.tick();
    ASSERT_TRUE(out.feedback.has_value());
    EXPECT_EQ(out.feedback->phase, FeedbackPhase::kExecuting);
    EXPECT_TRUE(out.feedback->distance_valid);
    EXPECT_NEAR(out.feedback->distance_remaining_m, 0.4, 1e-9);
  }
  EXPECT_EQ(h.view().item_index, 0U);
  h.world.z = -4.75;
  h.tick();
  EXPECT_EQ(h.view().item_index, 1U);
  EXPECT_EQ(h.view().items_completed, 1U);
}

TEST(Loiter, KeepsSetpointAndEndsAfterDuration)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  const SetpointOut held = h.view().setpoint;
  // LOITER는 앞 항목이 끝난 tick에 시작하고 5 s(100 tick) 뒤에 끝난다.
  for (int i = 0; i < 99; ++i) {
    const StepOutput out = h.tick();
    ASSERT_TRUE(out.setpoint.has_value());
    EXPECT_DOUBLE_EQ(out.setpoint->z, held.z);
    EXPECT_TRUE(out.commands.empty());
  }
  EXPECT_EQ(h.view().item_index, 1U);
  const StepOutput end = h.tick();
  EXPECT_EQ(h.view().item_index, 2U);
  EXPECT_EQ(end.commands, std::vector<CommandKind>{CommandKind::kNavLand});
  // LAND에 들어간 tick에는 아직 OFFBOARD라 발행을 유지한다.
  EXPECT_TRUE(end.setpoint.has_value());
}

TEST(ItemTimeout, TakeoffTimerStartsAtArmConfirm)
{
  // TAKEOFF의 timeout(20 s)은 P6의 ARMED 확인 tick부터 흐른다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -2.0;  // 도달하지 않는다
  // 시작 tick은 이미 지났다. 시작에서 19.95 s까지 399 tick.
  for (int i = 0; i < 399; ++i) {
    h.tick();
  }
  EXPECT_EQ(h.view().stage, Stage::kItem);
  h.tick();  // 20.0 s
  EXPECT_EQ(h.view().stage, Stage::kCleanup);
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
}

// ---- 상태기 안의 감시 표: 순위마다 한 건 ----

struct RunnerRowCase
{
  const char * name;
  std::function<void(Harness &)> inject;
  Reason reason;
  int rank;
};

std::vector<RunnerRowCase> runner_rows()
{
  return {
    {"Rank1_TimestampFailure", [](Harness & h) { h.clock.fail = true; }, Reason::kInternal, 1},
    {"Rank2_IdentityMismatch", [](Harness & h) { h.world.identity = IdentityCheck::kMismatch; },
     Reason::kInternal, 2},
    {"Rank3_LinkLost",
     [](Harness & h) {
       // vehicle_status만 끊는다. 마지막 수신에서 2 s.
       h.auto_samples = false;
       for (int i = 0; i < 39; ++i) {
         h.step_only();
       }
       ASSERT_FALSE(h.runner().done());
     },
     Reason::kLinkLost, 3},
    {"Rank4_DisarmedInAir", [](Harness & h) { h.world.arming = Arming::kDisarmed; },
     Reason::kFailsafe, 4},
    {"Rank5_DisarmedOnGround",
     [](Harness & h) {
       h.world.arming = Arming::kDisarmed;
       h.world.landed = true;
     },
     Reason::kExternalDisarm, 5},
    {"Rank6_ModeFailsafe",
     [](Harness & h) {
       h.world.nav = NavMode::kLand;
       h.world.intention = NavMode::kLand;
       h.world.failsafe = true;
     },
     Reason::kFailsafe, 6},
    {"Rank7_ModeExternal",
     [](Harness & h) {
       h.world.nav = NavMode::kHold;
       h.world.intention = NavMode::kHold;
     },
     Reason::kExternalModeChange, 7},
    // 방어 경로(합성 표본): failsafe 없이 사용자 의도가 OFFBOARD인 채 nav_state만 다른 표본은
    // v1.17.0 정상 상태에서 나오지 않는다.
    {"Rank8_ModeDefensive",
     [](Harness & h) {
       h.world.nav = NavMode::kHold;
       h.world.intention = NavMode::kOffboard;
     },
     Reason::kFailsafe, 8},
  };
}

class RunnerMonitorRow : public ::testing::TestWithParam<RunnerRowCase>
{
};

TEST_P(RunnerMonitorRow, EndsGoalAndStopsPublishing)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  GetParam().inject(h);
  const StepOutput out = h.tick();
  ASSERT_TRUE(out.termination.has_value()) << GetParam().name;
  EXPECT_FALSE(out.setpoint.has_value());
  EXPECT_TRUE(out.commands.empty());
  EXPECT_NE(
    out.termination->detail.find("rank " + std::to_string(GetParam().rank)), std::string::npos)
    << out.termination->detail;
  EXPECT_EQ(out.termination->last_item_index, 1U);
  EXPECT_EQ(out.termination->items_completed, 1U);
  expect_terminated_once(h, Status::kAborted, GetParam().reason);
}

INSTANTIATE_TEST_SUITE_P(
  Table, RunnerMonitorRow, ::testing::ValuesIn(runner_rows()),
  [](const ::testing::TestParamInfo<RunnerRowCase> & info) {
    return std::string(info.param.name);
  });

TEST(RunnerMonitor, RowCountMatchesTable)
{
  EXPECT_EQ(runner_rows().size(), kMonitorRankOrder.size());
}

TEST(RunnerMonitor, SameTickTieGoesToHigherRank)
{
  // 공중 DISARMED(순위 4)와 failsafe 모드 이탈(순위 6)이 한 표본에 함께 맞으면 순위 4.
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  h.world.nav = NavMode::kLand;
  h.world.failsafe = true;
  const StepOutput out = h.tick();
  ASSERT_TRUE(out.termination.has_value());
  EXPECT_NE(out.termination->detail.find("rank 4"), std::string::npos);
  expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
}

TEST(RunnerMonitor, StaggeredFirstRowWins)
{
  // 엇갈려 시작: 이 tick에 순위 7만 맞아 goal이 끝나고, 다음 tick의 순위 4 표본은 효과가 없다.
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  const std::vector<StepOutput> outs = h.feed({
    [] {
      Sample s = armed(NavMode::kHold);
      s.intention = NavMode::kHold;
      return s;
    }(),
    disarmed(false, NavMode::kHold),
    disarmed(true, NavMode::kHold),
  });
  ASSERT_TRUE(outs[0].termination.has_value());
  EXPECT_FALSE(outs[1].termination.has_value());
  EXPECT_FALSE(outs[2].termination.has_value());
  EXPECT_TRUE(outs[1].commands.empty());
  EXPECT_FALSE(outs[1].feedback.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kExternalModeChange);
}

TEST(RunnerMonitor, OffboardArmedFailsafeDoesNotEndGoal)
{
  // 방어 경로(합성 표본): OFFBOARD이고 ARMED인 채 failsafe가 true인 표본은 v1.17.0에서 나오지
  // 않는다. 나와도 goal을 끝내지 않고 발행을 계속한다(멈추면 offboard 손실을 스스로 일으킨다).
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.world.failsafe = true;
  for (int i = 0; i < 10; ++i) {
    const StepOutput out = h.tick();
    EXPECT_FALSE(out.termination.has_value());
    EXPECT_TRUE(out.setpoint.has_value());
  }
  EXPECT_TRUE(h.view().failsafe_history);
}

TEST(RunnerMonitor, Rank5HistoryIsPerItem)
{
  // 방어 경로(합성 표본). TAKEOFF에서 본 failsafe 이력은 LOITER로 넘어오지 않는다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.failsafe = true;
  h.tick();
  EXPECT_TRUE(h.view().failsafe_history);
  h.world.failsafe = false;
  h.tick();
  h.world.z = h.view().setpoint.z;
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 5));
  h.tick();
  EXPECT_FALSE(h.view().failsafe_history);
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  h.world.landed = true;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kExternalDisarm);
}

TEST(RunnerMonitor, Rank5HistoryWithinItemIsFailsafe)
{
  // 방어 경로(합성 표본). 같은 항목 안의 앞선 표본에서 failsafe를 봤으면 지상 DISARMED는 FAILSAFE.
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  h.feed({[] {
    Sample s = armed();
    s.failsafe = true;
    return s;
  }()});
  h.feed({disarmed(true)});
  expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
  EXPECT_NE(h.termination()->detail.find("rank 5"), std::string::npos);
}

TEST(RunnerMonitor, DisarmClassIsFixedAtFirstDisarmed)
{
  // 첫 DISARMED 때 landed가 false이면 FAILSAFE이고, 뒤에 landed가 true가 되어도 바뀌지 않는다.
  {
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;
    h.feed({disarmed(false), disarmed(true), disarmed(true)});
    expect_terminated_once(h, Status::kAborted, Reason::kFailsafe);
  }
  // 반대: 첫 DISARMED 때 landed가 true이면 지상 disarm으로 고정된다.
  {
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;
    h.feed({disarmed(true), disarmed(false), disarmed(false)});
    expect_terminated_once(h, Status::kAborted, Reason::kExternalDisarm);
  }
}

TEST(RunnerMonitor, NavStateOfGroundDisarmedSampleIsNotRead)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  Sample s = disarmed(true, NavMode::kOther);
  s.intention = NavMode::kOther;
  h.feed({s});
  expect_terminated_once(h, Status::kAborted, Reason::kExternalDisarm);
}

}  // namespace
}  // namespace idsim_mission::core::test
