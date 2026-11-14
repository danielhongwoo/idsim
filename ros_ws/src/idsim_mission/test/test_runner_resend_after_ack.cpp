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

// 지상 arm 진입 밖의 재전송 경로는 비거부 ack를 받은 뒤에도 확인 표본이 오지 않으면 주기 재전송을
// 이어 간다(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 12 "명령과 ack의 유실": ack가
// 진행 조건인 상태는 지상 arm 진입 하나뿐이고, 나머지는 재전송하면서 주기 표본으로 진행한다).
//
// - 대상: mission_runner.cpp의 resend_due 호출 지점 중 지상 arm 진입(P5, P5a) 전용 helper를 거치지
//   않는 다섯 곳. P6 arm(prepare_arm_before_armed), 모드 명령 항목(step_mode_item. NAV_LAND,
//   NAV_RTL, 대비책 disarm), 정리의 지상 disarm(run_ground), 공중 Hold(run_air), Land 경로
//   (run_air_land).
// - 사례마다 명령을 처음 보낸 tick을 S라 한다. S+1, S+11, S+21(전송 다음 tick)에 그 명령 묶음의
//   비거부 ack(ACCEPTED, IN_PROGRESS)를 주고, 확인 표본은 주지 않는다. S+1..S+30의 출력에서 명령은
//   S+10, S+20, S+30에만 있고 그것은 같은 명령 하나다(command_resend_period 0.5 s = 10 tick).
//   이 구간의 timeout(arm_timeout 100 tick, mode_confirm_timeout과 hold_confirm_timeout 60 tick,
//   항목 timeout)은 차지 않는다.
// - 이 경로들에 지상 arm 진입 helper(유효 ack면 재전송 억제)를 잘못 쓰면 S+10부터 재전송이
//   나가지 않아 실패한다.
// - ack는 합성이다(가짜 PX4 반응을 끄고 테스트가 직접 준다). 기체 상태는 world로 고정한다.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

constexpr std::uint64_t kResendTicks = 10;  // command_resend_period 0.5 s
constexpr std::uint64_t kLastTick = 30;     // S+30까지 본다(재전송 세 번)

const std::vector<AckResult> & non_rejecting_results()
{
  static const std::vector<AckResult> results = {AckResult::kAccepted, AckResult::kInProgress};
  return results;
}

std::string result_label(AckResult result)
{
  return result == AckResult::kAccepted ? "ACCEPTED" : "IN_PROGRESS";
}

// 지금 막 끝난 tick(S = tick_no - 1)의 출력이 kind 하나인지 보고 S를 돌려준다.
std::uint64_t sent_tick(const Harness & h, CommandKind kind)
{
  const std::uint64_t s = h.tick_no - 1;
  const StepOutput * const out = output_of_tick(h, s);
  EXPECT_NE(out, nullptr);
  if (out != nullptr) {
    EXPECT_EQ(out->commands, std::vector<CommandKind>{kind}) << "send tick " << s;
  }
  return s;
}

// S+1..S+30을 진행한다. 전송 다음 tick(S+1, S+11, S+21)마다 그 명령 묶음의 ack(result)를 준다.
// 명령은 S+10, S+20, S+30에만 kind 하나로 있고 그 사이에 끝나지 않는다.
void expect_resends_after_ack(
  Harness & h, std::uint64_t s, CommandKind kind, AckCommand ack_command, AckResult result)
{
  ASSERT_FALSE(h.auto_px4);
  ASSERT_EQ(h.tick_no, s + 1);
  for (std::uint64_t k = 1; k <= kLastTick; ++k) {
    if (k % kResendTicks == 1) {
      h.push_ack(ack_command, result);
    }
    const StepOutput out = h.tick();
    ASSERT_FALSE(h.runner().done()) << "S+" << k << ": " << termination_or_empty(h).detail;
    if (k % kResendTicks == 0) {
      EXPECT_EQ(out.commands, std::vector<CommandKind>{kind}) << "S+" << k;
    } else {
      EXPECT_TRUE(out.commands.empty()) << "S+" << k;
    }
  }
}

// ---- P6 arm: 첫 ARMED 표본 전 ----

TEST(ResendAfterAck, ArmBeforeFirstArmed)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }, 400));
    const std::uint64_t s = sent_tick(h, CommandKind::kArm);
    h.auto_px4 = false;
    h.world.arming = Arming::kDisarmed;  // 가짜 PX4가 S의 arm에 반응한 것을 되돌린다
    expect_resends_after_ack(h, s, CommandKind::kArm, AckCommand::kArmDisarm, result);
    EXPECT_EQ(h.view().prep, PrepStep::kArm);
  }
}

// ---- 모드 명령 항목: 확인 전 NAV_LAND, NAV_RTL ----

TEST(ResendAfterAck, LandItemNavLandBeforeConfirm)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    h.drive_to_land();
    const std::uint64_t s = sent_tick(h, CommandKind::kNavLand);
    h.auto_px4 = false;
    h.world.nav = NavMode::kOffboard;  // AUTO_LAND 표본이 오지 않는다
    h.world.intention = NavMode::kOffboard;
    expect_resends_after_ack(h, s, CommandKind::kNavLand, AckCommand::kNavLand, result);
    EXPECT_FALSE(h.view().land_confirmed);
  }
}

TEST(ResendAfterAck, RtlItemNavRtlBeforeConfirm)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(takeoff_loiter_rtl_mission());
    h.rtl_response = RtlResponse::kIgnore;  // AUTO_RTL 표본이 오지 않는다
    h.drive_to_land();
    const std::uint64_t s = sent_tick(h, CommandKind::kNavRtl);
    h.auto_px4 = false;
    expect_resends_after_ack(h, s, CommandKind::kNavRtl, AckCommand::kNavRtl, result);
    EXPECT_FALSE(h.view().land_confirmed);
  }
}

// ---- 모드 명령 항목: 확인 뒤 대비책 disarm ----

TEST(ResendAfterAck, LandItemFallbackDisarm)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    h.drive_to_land();
    ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 5));
    h.world.landed = true;
    h.auto_px4 = false;  // DISARMED 표본이 오지 않는다
    ASSERT_TRUE(h.run_until([&h] { return h.count_command(CommandKind::kDisarm) == 1; }, 200));
    const std::uint64_t s = sent_tick(h, CommandKind::kDisarm);
    expect_resends_after_ack(h, s, CommandKind::kDisarm, AckCommand::kArmDisarm, result);
  }
}

// ---- 정리: 지상 disarm ----

TEST(ResendAfterAck, CleanupGroundDisarm)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    ASSERT_TRUE(h.run_until([&h] { return h.view().prep == PrepStep::kArm; }, 400));
    h.auto_px4 = false;
    h.world.arming = Arming::kArmed;  // DISARMED 표본이 오지 않는다
    h.tick(true);
    ASSERT_EQ(h.view().branch, Branch::kGround);
    const std::uint64_t s = sent_tick(h, CommandKind::kDisarm);
    expect_resends_after_ack(h, s, CommandKind::kDisarm, AckCommand::kArmDisarm, result);
    EXPECT_EQ(h.view().branch, Branch::kGround);
  }
}

// ---- 정리: 공중 Hold ----

TEST(ResendAfterAck, CleanupAirHold)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;  // AUTO_LOITER 표본이 오지 않는다
    h.tick(true);
    ASSERT_EQ(h.view().branch, Branch::kAir);
    const std::uint64_t s = sent_tick(h, CommandKind::kSetModeHold);
    expect_resends_after_ack(h, s, CommandKind::kSetModeHold, AckCommand::kSetMode, result);
    EXPECT_EQ(h.view().branch, Branch::kAir);
  }
}

// ---- 정리: Hold 실패 뒤 Land 경로 ----

TEST(ResendAfterAck, CleanupAirLandPath)
{
  for (const AckResult result : non_rejecting_results()) {
    SCOPED_TRACE(result_label(result));
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.auto_px4 = false;  // AUTO_LAND 표본이 오지 않는다
    h.tick(true);
    h.push_ack(AckCommand::kSetMode, AckResult::kDenied);
    h.tick();
    ASSERT_EQ(h.view().branch, Branch::kAirLand);
    const std::uint64_t s = sent_tick(h, CommandKind::kNavLand);
    expect_resends_after_ack(h, s, CommandKind::kNavLand, AckCommand::kNavLand, result);
    EXPECT_EQ(h.view().branch, Branch::kAirLand);
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
