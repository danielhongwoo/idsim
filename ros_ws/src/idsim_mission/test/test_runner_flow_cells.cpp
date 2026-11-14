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

// PREPARING과 항목 단계의 칸(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 13, B8b).
// 테스트 하나가 칸 하나를 덮고, 그 칸의 to와 reason을 이 runner의 전이 기록(expect_cell)과 종료
// 결과로 단정한다. 정리 단계의 칸은 test_runner_cleanup_cells.cpp의 파라미터화 하네스가 덮는다.
//
// - 무시된 취소의 대표 칸(그 tick에 goal을 바로 끝내는 사건과 CANCEL)은 취소가 이겼다면 나갔을
//   명령(Hold, disarm)이 그 tick과 그 뒤에 나가지 않음을 함께 단정한다(expect_no_cancel_commands).
//   취소는 끝나는 tick부터 계속 요청된다(cancel_sticky).
// - setpoint 항목의 tick 순서(감시 표 행 대 ITEM_TIMEOUT, 완료)는 대표 행 넷 x {TAKEOFF, LOITER} x
//   {ITEM_TIMEOUT, 완료}의 파라미터화 테스트다. 조건이 함께 참인 tick으로 시각을 옮겨 맞춘다.
// - 외부 arm, 공중 DISARMED, 거부 ack, 식별 불일치, 같은 timestamp의 반복 표본은 PX4 v1.17.0에서
//   재현하기 어려운 방어 경로라 합성 표본과 합성 ack로만 시험한다.

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

// 출력 from번째(끝나는 tick)부터 끝까지 Hold와 disarm이 없다.
void expect_no_cancel_commands(const Harness & h, std::size_t from)
{
  for (std::size_t i = from; i < h.outputs().size(); ++i) {
    for (const CommandKind kind : h.outputs()[i].commands) {
      EXPECT_NE(kind, CommandKind::kSetModeHold) << "output " << i;
      EXPECT_NE(kind, CommandKind::kDisarm) << "output " << i;
    }
  }
}

// P4(발행 시작 뒤 신호 확인 중). 가짜 PX4 반응을 끈다.
void reach_signal(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kSignal; }, 100));
  h.auto_px4 = false;
}

// P5(OFFBOARD 확인 중). SetModeOffboard에 가짜 PX4가 반응해 nav는 OFFBOARD다.
void reach_offboard(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kOffboard; }, 400));
  h.auto_px4 = false;
}

// P6에서 arm을 보낸 뒤, 첫 ARMED 표본 전(기체는 DISARMED 그대로).
void reach_arm(Harness & h)
{
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }, 100));
}

// P6에서 첫 ARMED 표본을 본 tick 뒤(지상, OFFBOARD).
void reach_first_armed(Harness & h)
{
  ASSERT_NO_FATAL_FAILURE(reach_arm(h));
  h.world.arming = Arming::kArmed;
  h.tick();
  ASSERT_TRUE(h.view().armed_seen);
  ASSERT_EQ(h.view().prep, PrepStep::kArm);
}

// ---- P0-P2 ----

TEST(FlowCells, InvalidMissionWithCancelSendsNothing)
{
  // 무효 미션의 첫 step(step_tick의 따로 된 호출 지점)과 취소. 취소는 무시되고 아무것도
  // 보내지 않는다.
  MissionSpec m;
  m.mission_id = "bad";
  m.items = {loiter_item()};
  Harness h(m);
  h.cancel_sticky = true;
  h.tick();
  expect_cell(
    h, "PREPARING.WAIT_READY", Event::kInvalidMission, "DONE", "ABORTED/INTERNAL",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  EXPECT_TRUE(h.commands().empty());
}

TEST(FlowCells, ReadyTimeoutWithCancelEndsNotReadyWithoutHoldOrDisarm)
{
  // px4-engineer 사례 1: WAIT_READY의 READY_TIMEOUT과 취소가 같은 tick이면 NOT_READY로 끝나고
  // Hold나 disarm이 나가지 않는다(NOT_READY는 기체에 아무것도 보내지 않은 goal에만 쓴다).
  Harness h(standard_mission());
  h.world.ekf_ready = false;
  h.tick();  // 표본은 다 있고 EKF gate를 기다린다
  h.now_ns = kStartNs + h.config().timeouts.ready_timeout_ns;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "PREPARING.WAIT_READY", Event::kReadyTimeout, "DONE", "ABORTED/NOT_READY", {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/NOT_READY");
  expect_no_cancel_commands(h, end);
  EXPECT_TRUE(h.commands().empty());
  for (const StepOutput & out : h.outputs()) {
    EXPECT_FALSE(out.setpoint.has_value());
  }
}

// ---- P3-P4 ----

TEST(FlowCells, SignalIdentityMismatchEndsInternal)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_signal(h));
  h.world.identity = IdentityCheck::kMismatch;
  h.tick();
  expect_cell(h, "PREPARING.SIGNAL", Event::kPreparingIdentityMismatch, "DONE", "ABORTED/INTERNAL");
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 0);  // arm을 보내기 전
}

TEST(FlowCells, SignalIdentityMismatchWithCancelSendsNoHoldOrDisarm)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_signal(h));
  h.world.identity = IdentityCheck::kMismatch;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "PREPARING.SIGNAL", Event::kPreparingIdentityMismatch, "DONE", "ABORTED/INTERNAL",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  expect_no_cancel_commands(h, end);
}

TEST(FlowCells, SignalCancelStartsCleanup)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_signal(h));
  h.tick(true);
  expect_cell(h, "PREPARING.SIGNAL", Event::kCancel, "CLEANUP.CANCEL.NONE", "-");
  // 지상 DISARMED이고 arm을 보낸 적이 없어 정리할 것이 없다.
  expect_terminated_once_as(h, "CANCELED/NONE");
}

TEST(FlowCells, SignalTimeoutWithCancelIsPreparingFailure)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_signal(h));
  h.world.signal_lost = true;
  const std::int64_t timeout_at =
    h.now_ns - kTickNs + h.config().timeouts.offboard_signal_timeout_ns;
  while (h.now_ns < timeout_at) {
    h.tick();
  }
  h.tick(true);
  expect_cell(
    h, "PREPARING.SIGNAL", Event::kSignalTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

// ---- P5 ----

TEST(FlowCells, OffboardCancelStartsCleanup)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  h.tick(true);
  expect_cell(h, "PREPARING.OFFBOARD", Event::kCancel, "CLEANUP.CANCEL.NONE", "-");
  expect_terminated_once_as(h, "CANCELED/NONE");
}

TEST(FlowCells, OffboardStampFailureEndsInternal)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  h.clock.fail = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(h, "PREPARING.OFFBOARD", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL");
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  EXPECT_TRUE(h.outputs()[end].commands.empty());
  EXPECT_FALSE(h.outputs()[end].setpoint.has_value());
}

TEST(FlowCells, OffboardRejectedWithCancelIsPreparingFailure)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  h.push_ack(AckCommand::kSetMode, AckResult::kDenied);
  h.tick(true);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(FlowCells, OffboardTimeoutWithCancelIsPreparingFailure)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  h.world.nav = NavMode::kOther;  // OFFBOARD를 확인하지 못한다
  const std::int64_t timeout_at = h.now_ns - kTickNs + h.config().timeouts.mode_confirm_timeout_ns;
  while (h.now_ns < timeout_at) {
    h.tick();
  }
  h.tick(true);
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kOffboardTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/MODE_SWITCH_FAILED");
}

TEST(FlowCells, OffboardIdentityMismatchWithCancelSendsNoHoldOrDisarm)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_offboard(h));
  h.world.identity = IdentityCheck::kMismatch;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "PREPARING.OFFBOARD", Event::kPreparingIdentityMismatch, "DONE", "ABORTED/INTERNAL",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  expect_no_cancel_commands(h, end);
}

// ---- P6 ----

TEST(FlowCells, ArmStampFailureBeforeArmedEndsInternal)
{
  // 첫 ARMED 표본 전(감시 표 밖)의 Px4Timestamp 실패. 뒤는 감시 표 순위 1이다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_arm(h));
  h.clock.fail = true;
  h.tick();
  expect_cell(h, "PREPARING.ARM", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL");
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
}

TEST(FlowCells, ArmRejectedWithCancelIsPreparingFailure)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_arm(h));
  h.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);
  h.tick(true);
  expect_cell(
    h, "PREPARING.ARM", Event::kArmRejected, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kPreparingFailure);
}

TEST(FlowCells, ArmTimeoutWithCancelIsPreparingFailure)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_arm(h));
  const std::int64_t timeout_at = h.now_ns - kTickNs + h.config().timeouts.arm_timeout_ns;
  while (h.now_ns < timeout_at) {
    h.tick();
  }
  h.tick(true);
  expect_cell(
    h, "PREPARING.ARM", Event::kArmTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kPreparingFailure);
}

TEST(FlowCells, ArmConfirmTimeoutWithCancelIsPreparingFailure)
{
  // 첫 ARMED 표본 뒤 확인 기한. 같은 timestamp의 표본이 되풀이되어(새 표본이 아니다) 3회 연속이
  // 차지 않는다. 감시 표는 그 표본을 그대로 쓰고(수신은 매 tick이라 끊기지 않는다) 어느 행에도
  // 맞지 않는다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_first_armed(h));
  ASSERT_TRUE(h.snapshot.status.has_value());
  const std::int64_t first_armed_ns = h.now_ns - kTickNs;
  Sample repeat = armed(NavMode::kOffboard, true);
  repeat.timestamp_us = h.snapshot.status->timestamp_us;
  const std::int64_t timeout_at = first_armed_ns + h.config().timeouts.mode_confirm_timeout_ns;
  while (h.now_ns < timeout_at) {
    h.feed({repeat});
  }
  h.feed({repeat}, true);
  expect_cell(
    h, "PREPARING.ARM", Event::kArmConfirmTimeout, "CLEANUP.PREPARING_FAILURE.NONE", "-",
    {Event::kCancel});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kPreparingFailure);
}

TEST(FlowCells, ArmDisarmedOnGroundWithFailsafeIsFailsafe)
{
  // 감시 표 순위 5에서 이 표본의 failsafe가 true이면 FAILSAFE.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_first_armed(h));
  h.world.arming = Arming::kDisarmed;
  h.world.failsafe = true;
  h.tick();
  expect_cell(h, "PREPARING.ARM", Event::kMonitorDisarmedOnGround, "DONE", "ABORTED/FAILSAFE");
  expect_terminated_once_as(h, "ABORTED/FAILSAFE");
}

TEST(FlowCells, ArmDisarmedOnGroundBeatsModeExternal)
{
  // 감시 표 행 쌍의 대표(DISARMED 행 대 모드 행).
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_first_armed(h));
  h.world.arming = Arming::kDisarmed;
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  h.tick();
  expect_cell(
    h, "PREPARING.ARM", Event::kMonitorDisarmedOnGround, "DONE", "ABORTED/EXTERNAL_DISARM",
    {Event::kMonitorModeExternal});
  expect_terminated_once_as(h, "ABORTED/EXTERNAL_DISARM");
}

TEST(FlowCells, ArmModeFailsafeWithCancelSendsDisarmOnce)
{
  // px4-engineer 사례 2: ARM(첫 ARMED 표본 뒤, 지상)의 MONITOR_MODE_FAILSAFE와 취소가 같은 tick이면
  // 감시 표의 disarm 1회만 나간다. 취소가 이겼다면 지상 분기의 disarm이 따로 나갔을 것이다. Hold는
  // 나가지 않는다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(reach_first_armed(h));
  ASSERT_EQ(h.count_command(CommandKind::kDisarm), 0);
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  h.world.failsafe = true;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "PREPARING.ARM", Event::kMonitorModeFailsafe, "DONE", "ABORTED/FAILSAFE", {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/FAILSAFE");
  EXPECT_EQ(h.outputs()[end].commands, std::vector<CommandKind>{CommandKind::kDisarm});
  EXPECT_EQ(h.count_command(CommandKind::kDisarm), 1);
  EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
}

// ---- TAKEOFF ----

TEST(FlowCells, TakeoffReachedStartsLand)
{
  MissionSpec m;
  m.mission_id = "takeoff_land";
  m.items = {takeoff_item(), land_item()};
  Harness h(m);
  ASSERT_NO_FATAL_FAILURE(h.drive_to_takeoff());
  h.world.landed = false;
  h.world.z = h.view().setpoint.z;
  h.tick();
  expect_cell(h, "ITEM.TAKEOFF", Event::kTakeoffReached, "ITEM.LAND", "-");
  EXPECT_EQ(h.view().item_index, 1U);
}

TEST(FlowCells, TakeoffTimeoutWithCancelIsItemTimeout)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_takeoff());
  h.auto_px4 = false;
  h.now_ns = h.now_ns - kTickNs + h.runner().mission().items[0].timeout.to_ns();
  h.tick(true);
  expect_cell(
    h, "ITEM.TAKEOFF", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-", {Event::kCancel});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
}

TEST(FlowCells, TakeoffDisarmedInAirBeatsModeFailsafe)
{
  // 감시 표 행 쌍의 대표(DISARMED 행 대 모드 행).
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_takeoff());
  h.auto_px4 = false;
  h.world.arming = Arming::kDisarmed;
  h.world.landed = false;
  h.world.nav = NavMode::kHold;
  h.world.failsafe = true;
  h.tick();
  expect_cell(
    h, "ITEM.TAKEOFF", Event::kMonitorDisarmedInAir, "DONE", "ABORTED/FAILSAFE",
    {Event::kMonitorModeFailsafe});
  expect_terminated_once_as(h, "ABORTED/FAILSAFE");
}

TEST(FlowCells, TakeoffModeExternalWithCancelSendsNoHoldOrDisarm)
{
  // 바로 끝내는 사건의 대표. 이륙한 뒤라(landed false 이력) 감시 표도 disarm을 보내지 않는다.
  // 취소가 이겼다면 공중 분기의 Hold가 나갔을 것이다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_takeoff());
  h.world.landed = false;
  h.world.z = -2.0;
  h.tick();
  h.auto_px4 = false;
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "ITEM.TAKEOFF", Event::kMonitorModeExternal, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE",
    {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/EXTERNAL_MODE_CHANGE");
  expect_no_cancel_commands(h, end);
}

// ---- LOITER ----

TEST(FlowCells, LoiterElapsedStartsNextLoiter)
{
  MissionSpec m;
  m.mission_id = "two_loiters";
  m.items = {takeoff_item(), loiter_item(), loiter_item(), land_item()};
  Harness h(m);
  ASSERT_NO_FATAL_FAILURE(h.drive_to_loiter());
  ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 2U; }, 200));
  expect_cell(h, "ITEM.LOITER", Event::kLoiterElapsed, "ITEM.LOITER", "-");
}

TEST(FlowCells, LoiterTimeoutWithElapsedIsItemTimeout)
{
  // duration < timeout(validate_mission)이라 한 tick 사이에 경과가 duration과 timeout을 함께 넘을
  // 때만(tick 간격이 벌어짐) ITEM_TIMEOUT에 닿는다. 같은 tick이면 ITEM_TIMEOUT이 완료를 이긴다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_loiter());
  h.auto_px4 = false;
  h.now_ns = h.now_ns - kTickNs + h.runner().mission().items[1].timeout.to_ns();
  h.tick();
  expect_cell(
    h, "ITEM.LOITER", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
    {Event::kLoiterElapsed});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
}

TEST(FlowCells, LoiterTimeoutWithCancelIsItemTimeout)
{
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_loiter());
  h.auto_px4 = false;
  h.now_ns = h.now_ns - kTickNs + h.runner().mission().items[1].timeout.to_ns();
  h.tick(true);
  expect_cell(
    h, "ITEM.LOITER", Event::kItemTimeout, "CLEANUP.ITEM_TIMEOUT.NONE", "-",
    {Event::kLoiterElapsed, Event::kCancel});
  EXPECT_EQ(h.view().cleanup_cause, CleanupCause::kItemTimeout);
}

// ---- LAND ----

TEST(FlowCells, LandStampFailureEndsInternal)
{
  // [LAND] 미션의 첫 tick: 항목을 시작해 NAV_LAND를 만들었지만 Px4Timestamp를 얻지 못한다.
  Harness h(land_only_mission());
  h.world.arming = Arming::kArmed;
  h.world.landed = false;
  h.world.z = -5.0;
  h.clock.fail = true;
  h.tick();
  expect_cell(h, "ITEM.LAND", Event::kStampUnavailable, "DONE", "ABORTED/INTERNAL");
  expect_terminated_once_as(h, "ABORTED/INTERNAL");
  EXPECT_TRUE(h.commands().empty());
}

TEST(FlowCells, LandLeftModeWithCancelSendsNoHoldOrDisarm)
{
  // 바로 끝내는 사건의 대표(실패). 취소가 이겼다면 공중 분기의 Hold가 나갔을 것이다.
  Harness h(standard_mission());
  ASSERT_NO_FATAL_FAILURE(h.drive_to_land());
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 10));
  h.auto_px4 = false;
  h.world.nav = NavMode::kHold;
  h.world.intention = NavMode::kHold;
  h.cancel_sticky = true;
  const std::size_t end = h.outputs().size();
  h.tick();
  expect_cell(
    h, "ITEM.LAND", Event::kLandLeftMode, "DONE", "ABORTED/EXTERNAL_MODE_CHANGE", {Event::kCancel});
  expect_terminated_once_as(h, "ABORTED/EXTERNAL_MODE_CHANGE");
  expect_no_cancel_commands(h, end);
}

// ---- setpoint 항목의 tick 순서: 감시 표 행 대 ITEM_TIMEOUT과 완료 ----

struct SetpointOrderCase
{
  std::uint8_t item;  // item_type::kTakeoff 또는 kLoiter
  Event row;          // 대표 행: 순위 1, 3, 5(지상 DISARMED), 7
  Event condition;    // kItemTimeout 또는 그 항목의 완료 사건
};

const char * row_reason(Event row)
{
  switch (row) {
    case Event::kMonitorTimestampFailure:
      return "ABORTED/INTERNAL";
    case Event::kMonitorLinkLost:
      return "ABORTED/LINK_LOST";
    case Event::kMonitorDisarmedOnGround:
      return "ABORTED/EXTERNAL_DISARM";
    case Event::kMonitorModeExternal:
      return "ABORTED/EXTERNAL_MODE_CHANGE";
    default:
      return "?";
  }
}

std::vector<SetpointOrderCase> setpoint_order_cases()
{
  std::vector<SetpointOrderCase> cases;
  for (const std::uint8_t item : {item_type::kTakeoff, item_type::kLoiter}) {
    const Event completion =
      item == item_type::kTakeoff ? Event::kTakeoffReached : Event::kLoiterElapsed;
    for (const Event row :
         {Event::kMonitorTimestampFailure, Event::kMonitorLinkLost, Event::kMonitorDisarmedOnGround,
          Event::kMonitorModeExternal}) {
      for (const Event condition : {Event::kItemTimeout, completion}) {
        cases.push_back({item, row, condition});
      }
    }
  }
  return cases;
}

class SetpointOrderCells : public ::testing::TestWithParam<SetpointOrderCase>
{
};

TEST_P(SetpointOrderCells, MonitorRowBeatsTimeoutAndCompletion)
{
  const SetpointOrderCase & c = GetParam();
  const bool takeoff = c.item == item_type::kTakeoff;
  Harness h(standard_mission());
  if (takeoff) {
    ASSERT_NO_FATAL_FAILURE(h.drive_to_takeoff());
  } else {
    ASSERT_NO_FATAL_FAILURE(h.drive_to_loiter());
  }
  // 항목을 시작한 tick에 마지막 status를 받았다. 그 tick부터 조건이 참이 되는 시각으로 옮긴다.
  const std::int64_t item_start = h.now_ns - kTickNs;
  const ItemSpec item = h.runner().mission().items[h.view().item_index];
  std::int64_t offset = item.timeout.to_ns();
  if (c.condition != Event::kItemTimeout) {
    // TAKEOFF 도달은 시각과 무관하므로 상태 끊김 행도 함께 맞도록 link_timeout 뒤로 둔다.
    offset = takeoff ? h.config().timeouts.link_timeout_ns : item.loiter.duration.to_ns();
  }
  h.auto_px4 = false;
  h.auto_samples = false;
  h.now_ns = item_start + offset;
  if (takeoff) {
    h.world.z = c.condition == Event::kTakeoffReached ? h.view().setpoint.z : -2.0;
  }
  h.world.arming = Arming::kArmed;
  h.world.nav = NavMode::kOffboard;
  h.world.intention = NavMode::kOffboard;
  h.world.failsafe = false;
  h.world.landed = false;
  switch (c.row) {
    case Event::kMonitorTimestampFailure:
      h.clock.fail = true;
      h.push_world_samples();
      break;
    case Event::kMonitorLinkLost:
      h.push_world_samples_without_status();
      break;
    case Event::kMonitorDisarmedOnGround:
      h.world.arming = Arming::kDisarmed;
      h.world.landed = true;
      h.push_world_samples();
      break;
    case Event::kMonitorModeExternal:
      h.world.nav = NavMode::kHold;
      h.world.intention = NavMode::kHold;
      h.push_world_samples();
      break;
    default:
      FAIL() << "unsupported row " << event_name(c.row);
  }
  h.step_only();
  std::vector<Event> also = {c.condition};
  if (!takeoff && c.condition == Event::kItemTimeout) {
    also.push_back(Event::kLoiterElapsed);  // duration < timeout이라 완료도 참이다
  }
  const std::string from = std::string("ITEM.") + item_type_name(c.item);
  expect_cell(h, from, c.row, "DONE", row_reason(c.row), also);
  expect_terminated_once_as(h, row_reason(c.row));
}

std::string setpoint_order_name(const ::testing::TestParamInfo<SetpointOrderCase> & info)
{
  return std::string(item_type_name(info.param.item)) + "_" + event_name(info.param.row) + "_" +
         event_name(info.param.condition);
}

INSTANTIATE_TEST_SUITE_P(
  Cells, SetpointOrderCells, ::testing::ValuesIn(setpoint_order_cases()), setpoint_order_name);

}  // namespace
}  // namespace idsim_mission::core::test
