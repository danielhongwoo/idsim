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

// 종료의 충돌 규칙(decisions.md 쟁점 3 "종료의 충돌 규칙"): 먼저 정해진 것이 이기고, 같은
// tick이면 ABORTED 사유, 완료, 취소 순이다. 종료 뒤의 cancel과 표본은 결과를 바꾸지 않는다.
// 그리고 Px4Timestamp 공급 실패(감시 표 순위 1 밖의 단계).

#include <gtest/gtest.h>

#include <cstddef>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

TEST(Conflict, ThirdDisarmedAndCancelSameTickIsSucceeded)
{
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.auto_px4 = false;
  h.feed({disarmed(true, NavMode::kLand), disarmed(true, NavMode::kLand)});
  const std::size_t before = h.edges().size();
  const std::vector<StepOutput> outs = h.feed({disarmed(true, NavMode::kLand)}, true);
  EXPECT_TRUE(outs[0].commands.empty());
  expect_cell(
    h, "ITEM.LAND", Event::kModeItemDisarmConfirmed, "DONE", "SUCCEEDED/NONE", {Event::kCancel},
    before);
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(Conflict, MonitorRowAndCancelSameTickIsTheRowsAbort)
{
  Harness h(standard_mission());
  h.drive_to_loiter();
  h.auto_px4 = false;
  Sample s = armed(NavMode::kHold);
  s.intention = NavMode::kHold;
  const std::size_t before = h.edges().size();
  const std::vector<StepOutput> outs = h.feed({s}, true);
  EXPECT_TRUE(outs[0].commands.empty());  // Hold를 보내지 않는다
  expect_cell(
    h, "ITEM.LOITER", Event::kMonitorModeExternal, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
    {Event::kCancel}, before);
  expect_terminated_once(h, Status::kAborted, Reason::kExternalModeChange);
}

TEST(Conflict, ItemTimeoutBeatsCompletionSameTick)
{
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -2.0;
  for (int i = 0; i < 399; ++i) {
    h.tick();
  }
  h.world.z = h.view().setpoint.z;  // 20.0 s tick에 도달도 함께
  h.tick();
  EXPECT_EQ(h.view().stage, Stage::kCleanup);
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
  EXPECT_EQ(h.view().item_index, 0U);
}

TEST(Conflict, CompletionThenCancelSameTickCancelsNextItem)
{
  // 항목 완료는 종료가 아니므로 같은 tick의 취소는 다음 항목에서 처리된다.
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  h.tick(true);
  EXPECT_EQ(h.view().item_index, 1U);
  EXPECT_EQ(h.view().stage, Stage::kCleanup);
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kCanceled, Reason::kNone);
  EXPECT_EQ(termination_or_empty(h).items_completed, 1U);
  EXPECT_EQ(termination_or_empty(h).last_item_index, 1U);
}

TEST(Conflict, CancelDuringPreparingFailureCleanupIsIgnored)
{
  // 정해진 tick이 기준이다. PREPARING 실패의 정리 중에 온 cancel은 원래 reason을 바꾸지 않는다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 200));
  h.cancel_sticky = true;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 10));
  expect_terminated_once(h, Status::kAborted, Reason::kArmRejected);
}

TEST(Conflict, CancelAfterTerminationIsIgnored)
{
  Harness h(standard_mission());
  h.world.identity = IdentityCheck::kMismatch;
  h.tick();
  ASSERT_TRUE(h.runner().done());
  const StepOutput after = h.tick(true);
  EXPECT_FALSE(after.termination.has_value());
  EXPECT_TRUE(after.commands.empty());
  expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
}

// ---- Px4Timestamp 공급 실패 ----

TEST(TimestampPort, FailureWhilePublishingInPreparingIsInternal)
{
  Harness h(standard_mission());
  h.tick();
  h.clock.fail = true;
  const StepOutput out = h.tick();
  EXPECT_FALSE(out.setpoint.has_value());
  EXPECT_TRUE(out.commands.empty());
  EXPECT_FALSE(out.px4_timestamp_us.has_value());
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
}

TEST(TimestampPort, FailureDuringItemTimeoutCleanupKeepsReason)
{
  Harness h(standard_mission());
  h.drive_to_takeoff();
  h.world.landed = false;
  h.world.z = -2.0;
  h.auto_px4 = false;
  ASSERT_TRUE(h.run_until([&h] { return h.view().stage == Stage::kCleanup; }, 500));
  h.clock.fail = true;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kItemTimeout);
  EXPECT_NE(termination_or_empty(h).detail.find("Px4Timestamp unavailable"), std::string::npos);
}

TEST(TimestampPort, NoQueryWhenNothingToEmit)
{
  // AUTO_LAND 확인 뒤 발행도 대기 명령도 없으면 port를 부르지 않고, 실패해도 goal을 끝내지 않는다.
  Harness h(standard_mission());
  h.drive_to_land();
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
  h.clock.fail = true;
  const int calls = h.clock.calls;
  for (int i = 0; i < 5; ++i) {
    const StepOutput out = h.tick();
    EXPECT_FALSE(out.termination.has_value());
  }
  EXPECT_EQ(h.clock.calls, calls);
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 5));
  expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
}

TEST(TimestampPort, FailureOnFinalDisarmDropsCommandKeepsResult)
{
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.auto_px4 = false;
  h.world.arming = Arming::kArmed;
  h.tick(true);
  for (int i = 0; i < 59; ++i) {
    h.tick();
  }
  h.clock.fail = true;
  const StepOutput end = h.tick();
  EXPECT_TRUE(end.commands.empty());
  expect_terminated_once(h, Status::kAborted, Reason::kDisarmFailed);
  const std::string & detail = termination_or_empty(h).detail;
  EXPECT_NE(detail.find("disarm not sent (Px4Timestamp unavailable)"), std::string::npos) << detail;
  EXPECT_EQ(detail.find("sent once"), std::string::npos) << detail;
}

TEST(TimestampPort, DetailSaysStateUnknownAfterActing)
{
  // 발행이나 명령을 한 뒤의 실패는 기체 상태를 모른다고 detail에 적는다.
  Harness h(standard_mission());
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }));
  h.clock.fail = true;
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
  EXPECT_NE(termination_or_empty(h).detail.find("vehicle state unknown"), std::string::npos);
}

}  // namespace
}  // namespace idsim_mission::core::test
