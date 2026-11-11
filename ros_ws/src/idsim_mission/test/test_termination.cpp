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

// status와 reason의 전수 대응표, reason 값, 종료 결과 == 종료 사건.
// 결정: decisions.md 담당자별 구현 지시(test-engineer, ros2-engineer).
// core의 reason 값과 생성된 메시지 상수 값의 교차 검사는 노드 쪽 gtest(P3d)에 둔다.

#include <gtest/gtest.h>

#include <cstdint>
#include <set>
#include <string>
#include <vector>

#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"
#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

struct ReasonRow
{
  Reason reason;
  int value;
  const char * name;
  bool aborted_only;  // true: ABORTED에만 대응. false: SUCCEEDED와 CANCELED에 대응(REASON_NONE)
};

// ExecuteMission.action result의 REASON_* 전수(13, 14는 6단계가 더한다).
const std::vector<ReasonRow> & reason_table()
{
  static const std::vector<ReasonRow> table = {
    {Reason::kNone, 0, "NONE", false},
    {Reason::kInvalidMission, 1, "INVALID_MISSION", true},
    {Reason::kVehicleIdMismatch, 2, "VEHICLE_ID_MISMATCH", true},
    {Reason::kBusy, 3, "BUSY", true},
    {Reason::kNotReady, 4, "NOT_READY", true},
    {Reason::kArmRejected, 5, "ARM_REJECTED", true},
    {Reason::kModeSwitchFailed, 6, "MODE_SWITCH_FAILED", true},
    {Reason::kItemTimeout, 7, "ITEM_TIMEOUT", true},
    {Reason::kFailsafe, 8, "FAILSAFE", true},
    {Reason::kExternalModeChange, 9, "EXTERNAL_MODE_CHANGE", true},
    {Reason::kTargetLost, 10, "TARGET_LOST", true},
    {Reason::kLinkLost, 11, "LINK_LOST", true},
    {Reason::kPreconditionFailed, 12, "PRECONDITION_FAILED", true},
    {Reason::kDisarmFailed, 13, "DISARM_FAILED", true},
    {Reason::kExternalDisarm, 14, "EXTERNAL_DISARM", true},
    {Reason::kInternal, 255, "INTERNAL", true},
  };
  return table;
}

TEST(ReasonTable, CoversEveryReasonOnce)
{
  ASSERT_EQ(reason_table().size(), kAllReasons.size());
  std::set<int> values;
  for (std::size_t i = 0; i < kAllReasons.size(); ++i) {
    EXPECT_EQ(reason_table()[i].reason, kAllReasons[i]);
    EXPECT_TRUE(values.insert(static_cast<int>(kAllReasons[i])).second);
  }
}

TEST(ReasonTable, ValuesAndNames)
{
  for (const ReasonRow & row : reason_table()) {
    EXPECT_EQ(static_cast<int>(row.reason), row.value) << row.name;
    EXPECT_STREQ(reason_name(row.reason), row.name);
  }
}

TEST(ReasonTable, EveryReasonMapsToItsStatusesExactly)
{
  // REASON_NONE이 아닌 reason은 ABORTED 하나에만, REASON_NONE은 SUCCEEDED와 CANCELED에만.
  for (const ReasonRow & row : reason_table()) {
    int consistent = 0;
    for (const Status status : kAllStatuses) {
      const bool ok = is_consistent(status, row.reason);
      if (ok) {
        ++consistent;
      }
      if (row.aborted_only) {
        EXPECT_EQ(ok, status == Status::kAborted) << row.name << " " << status_name(status);
      } else {
        EXPECT_EQ(ok, status != Status::kAborted) << row.name << " " << status_name(status);
      }
    }
    EXPECT_EQ(consistent, row.aborted_only ? 1 : 2) << row.name;
  }
}

TEST(EventStatus, Codes)
{
  // MissionEvent.STATUS_*와 action_msgs/GoalStatus의 같은 이름과 같은 값.
  EXPECT_EQ(event_status::kAccepted, 1);
  EXPECT_EQ(event_status_code(Status::kSucceeded), 4);
  EXPECT_EQ(event_status_code(Status::kCanceled), 5);
  EXPECT_EQ(event_status_code(Status::kAborted), 6);
}

TEST(TerminalEvent, EqualsResultForEveryReason)
{
  for (const ReasonRow & row : reason_table()) {
    for (const Status status : kAllStatuses) {
      if (!is_consistent(status, row.reason)) {
        continue;
      }
      Termination term;
      term.status = status;
      term.reason = row.reason;
      term.items_completed = 2;
      term.last_item_index = 2;
      term.detail = std::string("detail ") + row.name;
      expect_result_equals_event(term, 3);
    }
  }
}

TEST(AcceptedEvent, Fields)
{
  const EventFields event = accepted_event(3);
  EXPECT_EQ(event.status, event_status::kAccepted);
  EXPECT_EQ(event.reason, 0);
  EXPECT_EQ(event.item_count, 3U);
  EXPECT_EQ(event.items_completed, 0U);
  EXPECT_EQ(event.last_item_index, 0U);
  EXPECT_TRUE(event.detail.empty());
}

TEST(TerminalEvent, EqualsResultInRunnerScenarios)
{
  // 상태기가 낸 종료 결과로 result와 사건을 만들면 같다(정상 착륙, 취소, NOT_READY).
  {
    Harness h(standard_mission());
    h.drive_to_land();
    h.world.landed = true;
    h.world.arming = Arming::kDisarmed;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 50));
    expect_terminated_once(h, Status::kSucceeded, Reason::kNone);
    EXPECT_EQ(h.termination()->items_completed, 3U);
    EXPECT_EQ(h.termination()->last_item_index, 2U);
    expect_result_equals_event(*h.termination(), 3);
  }
  {
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.tick(true);
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_terminated_once(h, Status::kCanceled, Reason::kNone);
    EXPECT_EQ(h.termination()->items_completed, 1U);
    EXPECT_EQ(h.termination()->last_item_index, 1U);
    expect_result_equals_event(*h.termination(), 3);
  }
  {
    Harness h(standard_mission());
    h.world.ekf_ready = false;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 700));
    expect_terminated_once(h, Status::kAborted, Reason::kNotReady);
    EXPECT_EQ(h.termination()->items_completed, 0U);
    EXPECT_EQ(h.termination()->last_item_index, 0U);
    expect_result_equals_event(*h.termination(), 3);
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
