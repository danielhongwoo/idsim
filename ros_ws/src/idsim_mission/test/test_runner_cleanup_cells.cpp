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

// 정리 단계 칸의 파라미터화 하네스(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 13,
// B8b). 파라미터 하나가 칸 하나(정리 원인, 분기, 사건)이고, 본문은 그 칸의 to와 reason을 이
// runner의 전이 기록(expect_cell)과 종료 결과로 단정한다.
//
// 구조
// - CleanupRig는 세 단계로 칸에 닿는다. enter는 정리 원인마다 정해진 입구로 정리를 시작하고,
//   reach는 칸의 분기까지 몰고 가고, trigger는 칸의 사건을 일으킨다. 원인, 분기, 사건이 서로
//   독립이라 칸이 늘면 표에 한 줄을 더한다.
// - 원인의 입구(Cause)
//   kCancel: P5(OFFBOARD 확인 중)의 취소. arm을 보내기 전이라 "정리할 것 없음"까지 닿는다.
//   kItemTimeout: TAKEOFF(timeout 2 s)가 고도에 닿지 않아 ITEM_TIMEOUT.
//   kPrepModeSwitch: P5의 거부 ack(OFFBOARD_REJECTED). reason MODE_SWITCH_FAILED, arm을 보내기 전.
//   kPrepArm: P6의 첫 ARMED 표본 전 거부 ack(ARM_REJECTED). reason ARM_REJECTED, arm을 보냈다.
//   PREPARING 실패는 reason이 칸을 가르므로 원인을 둘로 나눈다(칸 목록의 from은 같은
//   CLEANUP.PREPARING_FAILURE).
// - 분기(Reach): kNone은 정리 첫 tick에 끝나는 칸이라 사건이 시작 표본을 정한다(표본 없음, 상태
//   끊김, 공중 DISARMED). kAir는 ARMED이고 landed false, kGround는 ARMED이고 landed true로
//   시작한다. kAirLand는 kAir에서 Hold 거부 ack로 Land 경로에 간 상태, kGroundAfterHoldFailure는
//   kAirLand에서 landed true로 지상 분기에 간 상태다(Hold 실패 표시가 남아 공중 재진입이 Land
//   경로가 된다).
// - 정리의 상한(12 s)은 분기 타임아웃(3 s)보다 길어 한 분기에 머물러서는 닿지 않는다. 상한 칸은
//   landed를 바꿔 분기를 나갔다 바로 다시 들어오기를 되풀이해(재진입이 분기 타이머를 다시 시작한다)
//   목표 분기에 있는 채 상한 tick을 맞는다. 상한 tick의 표본이 그 tick의 고르기를 정한다.
// - 기체 반응(auto_px4)은 입구 뒤에 끄고 표본을 직접 정한다. 외부 arm(P3-P5에 ARMED), 공중
//   DISARMED, 거부 ack, 첫 ARMED 표본보다 묵은 표본은 PX4 v1.17.0에서 재현하기 어려운 방어 경로라
//   합성 표본과 합성 ack로만 시험한다.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

enum class Cause : std::uint8_t
{
  kCancel,
  kItemTimeout,
  kPrepModeSwitch,
  kPrepArm,
};

enum class Reach : std::uint8_t
{
  kNone,
  kAir,
  kAirLand,
  kGround,
  kGroundAfterHoldFailure,
};

// 칸 하나. from은 원인과 분기에서 나온다(cleanup_state).
struct CleanupCell
{
  Cause cause;
  Reach reach;
  Event event;
  const char * to;
  const char * reason;
};

const char * cause_state(Cause cause)
{
  switch (cause) {
    case Cause::kCancel:
      return "CANCEL";
    case Cause::kItemTimeout:
      return "ITEM_TIMEOUT";
    case Cause::kPrepModeSwitch:
    case Cause::kPrepArm:
      return "PREPARING_FAILURE";
  }
  return "?";
}

const char * reach_state(Reach reach)
{
  switch (reach) {
    case Reach::kNone:
      return "NONE";
    case Reach::kAir:
      return "AIR";
    case Reach::kAirLand:
      return "AIR_LAND";
    case Reach::kGround:
    case Reach::kGroundAfterHoldFailure:
      return "GROUND";
  }
  return "?";
}

std::string cleanup_state(const CleanupCell & cell)
{
  return std::string("CLEANUP.") + cause_state(cell.cause) + "." + reach_state(cell.reach);
}

const char * cause_tag(Cause cause)
{
  switch (cause) {
    case Cause::kCancel:
      return "Cancel";
    case Cause::kItemTimeout:
      return "ItemTimeout";
    case Cause::kPrepModeSwitch:
      return "PrepModeSwitch";
    case Cause::kPrepArm:
      return "PrepArm";
  }
  return "Unknown";
}

const char * reach_tag(Reach reach)
{
  switch (reach) {
    case Reach::kNone:
      return "None";
    case Reach::kAir:
      return "Air";
    case Reach::kAirLand:
      return "AirLand";
    case Reach::kGround:
      return "Ground";
    case Reach::kGroundAfterHoldFailure:
      return "GroundAfterHoldFailure";
  }
  return "Unknown";
}

// 정리 첫 tick의 표본.
struct StartSample
{
  Arming arming{Arming::kArmed};
  bool landed{false};
  bool no_sample{false};  // vehicle_status를 한 번도 받지 않았다(P0)
  bool link_lost{false};  // 마지막 vehicle_status가 link_timeout 전이다
  bool stale_timestamp{false};  // timestamp가 첫 ARMED 표본보다 작다(감시 표가 쓰지 않는다)
};

// link_timeout(2 s) / tick(50 ms). 마지막 status 뒤 이 수만큼 지난 tick이 처음 끊긴 tick이다.
constexpr int kLinkTicks = 40;

class CleanupRig
{
public:
  explicit CleanupRig(Cause cause) : cause_(cause), h_(mission_for(cause)) {}

  Harness & h() { return h_; }

  void enter(Reach reach, Event event)
  {
    const StartSample start = start_for(reach, event);
    switch (cause_) {
      case Cause::kCancel:
        enter_cancel(start);
        break;
      case Cause::kItemTimeout:
        enter_item_timeout(start);
        break;
      case Cause::kPrepModeSwitch:
        enter_prep_mode_switch(start);
        break;
      case Cause::kPrepArm:
        enter_prep_arm(start);
        break;
    }
    h_.auto_samples = true;
    if (reach != Reach::kNone) {
      ASSERT_EQ(h_.view().stage, Stage::kCleanup);
    }
  }

  void reach(Reach reach)
  {
    switch (reach) {
      case Reach::kNone:
        return;
      case Reach::kAir:
        ASSERT_EQ(h_.view().branch, Branch::kAir);
        return;
      case Reach::kGround:
        ASSERT_EQ(h_.view().branch, Branch::kGround);
        return;
      case Reach::kAirLand:
        ASSERT_EQ(h_.view().branch, Branch::kAir);
        reject_hold();
        ASSERT_EQ(h_.view().branch, Branch::kAirLand);
        return;
      case Reach::kGroundAfterHoldFailure:
        ASSERT_EQ(h_.view().branch, Branch::kAir);
        reject_hold();
        ASSERT_EQ(h_.view().branch, Branch::kAirLand);
        h_.world.landed = true;
        h_.tick();
        ASSERT_EQ(h_.view().branch, Branch::kGround);
        ASSERT_TRUE(h_.view().hold_failed);
        return;
    }
  }

  void trigger(Event event, const std::string & reason)
  {
    switch (event) {
      case Event::kCleanupLinkLost:
        if (h_.view().stage == Stage::kCleanup) {
          // 분기 안의 상태 끊김: status 없이 link_timeout을 보낸다(분기 타임아웃 3 s보다 짧다).
          h_.auto_samples = false;
          for (int i = 0; i < kLinkTicks && !h_.runner().done(); ++i) {
            h_.step_only();
          }
        }
        return;
      case Event::kCleanupAirDisarm:
        if (h_.view().stage == Stage::kCleanup) {
          set_world(Arming::kDisarmed, false);
          h_.tick();
        }
        return;
      case Event::kCleanupNothingToDo:
        set_world(Arming::kDisarmed, true);
        h_.tick();
        return;
      case Event::kCleanupCap: {
        // 상한 tick의 고르기: 지상 분기이거나 기대 reason이 DISARM_FAILED(취소의 지상 상한)이면
        // landed true, 아니면 그 분기 그대로(공중).
        const bool on_ground =
          h_.view().branch == Branch::kGround || reason == "ABORTED/DISARM_FAILED";
        hold_branch_until_cap();
        set_world(Arming::kArmed, on_ground);
        h_.tick();
        ASSERT_FALSE(h_.outputs().empty());
        const std::vector<CommandKind> want = {
          on_ground ? CommandKind::kDisarm : CommandKind::kNavLand};
        EXPECT_EQ(h_.outputs().back().commands, want);
        return;
      }
      case Event::kStampUnavailable:
        h_.clock.fail = true;
        h_.tick();
        return;
      case Event::kEnterGround:
        set_world(Arming::kArmed, true);
        h_.tick();
        return;
      case Event::kEnterAir:
        set_world(Arming::kArmed, false);
        h_.tick();
        return;
      case Event::kHoldConfirmed:
        h_.world.nav = NavMode::kHold;
        h_.world.intention = NavMode::kHold;
        h_.run_until([this] { return h_.runner().done(); }, 10);
        return;
      case Event::kHoldRejected:
        reject_hold();
        return;
      case Event::kHoldTimeout:
        h_.run_until([this] { return h_.view().branch == Branch::kAirLand; }, 70);
        return;
      case Event::kLandPathModeObserved:
        h_.world.nav = NavMode::kLand;
        h_.world.intention = NavMode::kLand;
        h_.tick();
        return;
      case Event::kLandPathTimeout:
      case Event::kGroundDisarmTimeout:
        h_.run_until([this] { return h_.runner().done(); }, 70);
        return;
      case Event::kGroundDisarmConfirmed:
        set_world(Arming::kDisarmed, true);
        h_.run_until([this] { return h_.runner().done(); }, 10);
        return;
      default:
        // 정리 첫 tick에 끝나는 사건(표본 없음)은 enter가 이미 일으켰다.
        return;
    }
  }

private:
  static MissionSpec mission_for(Cause cause)
  {
    MissionSpec m = standard_mission();
    if (cause == Cause::kItemTimeout) {
      m.items[0] = takeoff_item(5.0, 2);
    }
    return m;
  }

  StartSample start_for(Reach reach, Event event) const
  {
    StartSample start;
    switch (reach) {
      case Reach::kNone:
        if (event == Event::kCleanupNoSample) {
          start.no_sample = true;
        } else if (event == Event::kCleanupLinkLost) {
          start.link_lost = true;
        } else if (event == Event::kCleanupAirDisarm) {
          start.arming = Arming::kDisarmed;
          start.landed = false;
          // ITEM_TIMEOUT은 감시 표가 같은 tick에 먼저 보므로, 정리만 보는 묵은 표본이어야 닿는다.
          start.stale_timestamp = cause_ == Cause::kItemTimeout;
        } else {
          ADD_FAILURE() << "no start sample for NONE " << event_name(event);
        }
        return start;
      case Reach::kGround:
        start.landed = true;
        return start;
      case Reach::kAir:
      case Reach::kAirLand:
      case Reach::kGroundAfterHoldFailure:
        return start;
    }
    return start;
  }

  void set_world(Arming arming, bool landed)
  {
    h_.world.arming = arming;
    h_.world.landed = landed;
    h_.world.nav = NavMode::kOffboard;
    h_.world.intention = NavMode::kOffboard;
    h_.world.failsafe = false;
  }

  // P5에 들어선 tick 뒤. SetModeOffboard에 가짜 PX4가 반응해 nav는 OFFBOARD다.
  void to_offboard()
  {
    ASSERT_TRUE(h_.run_until([this] { return h_.view().prep == PrepStep::kOffboard; }, 400));
    h_.auto_px4 = false;
  }

  // status 없이 tick을 보내 다음 tick이 처음 끊긴 tick이 되게 한다.
  void go_stale()
  {
    h_.auto_samples = false;
    for (int i = 0; i < kLinkTicks - 1; ++i) {
      h_.step_only();
    }
  }

  void mark_start() { cleanup_start_ns_ = h_.now_ns; }

  void enter_cancel(const StartSample & start)
  {
    if (start.no_sample) {
      // P0에서 표본을 하나도 받기 전의 취소.
      h_.auto_samples = false;
      h_.auto_px4 = false;
      mark_start();
      h_.step_only(true);
      return;
    }
    ASSERT_NO_FATAL_FAILURE(to_offboard());
    if (start.link_lost) {
      go_stale();
      mark_start();
      h_.step_only(true);
      return;
    }
    set_world(start.arming, start.landed);
    mark_start();
    h_.tick(true);
  }

  void enter_item_timeout(const StartSample & start)
  {
    ASSERT_NO_FATAL_FAILURE(h_.drive_to_takeoff());
    h_.auto_px4 = false;
    const std::int64_t timeout_at =
      h_.now_ns - kTickNs + h_.runner().mission().items[0].timeout.to_ns();
    while (h_.now_ns < timeout_at) {
      h_.tick();
    }
    mark_start();
    if (start.stale_timestamp) {
      Sample stale = disarmed(start.landed);
      stale.timestamp_us = 1;
      h_.feed({stale});
      return;
    }
    set_world(start.arming, start.landed);
    h_.tick();
  }

  void enter_prep_mode_switch(const StartSample & start)
  {
    ASSERT_NO_FATAL_FAILURE(to_offboard());
    if (start.link_lost) {
      go_stale();
      h_.push_ack(AckCommand::kSetMode, AckResult::kDenied);
      mark_start();
      h_.step_only();
      return;
    }
    set_world(start.arming, start.landed);
    h_.push_ack(AckCommand::kSetMode, AckResult::kDenied);
    mark_start();
    h_.tick();
  }

  void enter_prep_arm(const StartSample & start)
  {
    ASSERT_NO_FATAL_FAILURE(to_offboard());
    // 시작 표본을 P5에서 넣는다. arm을 처음 보낸 tick에 받은 표본은 첫 ARMED 표본이 아니므로(수신
    // tick이 arm 첫 전송 tick보다 커야 한다) ARMED여도 첫 ARMED 표본 전의 거부 ack가 닿는다.
    if (!start.link_lost) {
      set_world(start.arming, start.landed);
    }
    ASSERT_TRUE(h_.run_until([this] { return h_.view().prep == PrepStep::kArm; }, 100));
    h_.auto_samples = false;
    if (start.link_lost) {
      go_stale();
    }
    h_.push_ack(AckCommand::kArmDisarm, AckResult::kDenied);
    mark_start();
    h_.step_only();
  }

  void reject_hold()
  {
    h_.push_ack(AckCommand::kSetMode, AckResult::kDenied);
    h_.tick();
  }

  // 지금 분기에 있는 채 정리의 상한 직전 tick까지 간다. 분기 타임아웃(3 s = 60 tick) 전에 다른
  // 분기로 나갔다 바로 돌아와 분기 타이머를 다시 시작한다. 다음 tick이 상한 tick이다.
  void hold_branch_until_cap()
  {
    const Branch target = h_.view().branch;
    const bool target_landed = h_.world.landed;
    const std::int64_t cap_at = cleanup_start_ns_ + cleanup_cap_ns(h_.config().timeouts);
    const auto ticks_left = [this, cap_at] { return (cap_at - h_.now_ns) / kTickNs; };
    while (ticks_left() > 30) {
      h_.world.landed = !target_landed;
      h_.tick();
      ASSERT_NE(h_.view().branch, target);
      h_.world.landed = target_landed;
      h_.tick();
      ASSERT_EQ(h_.view().branch, target);
      for (int i = 0; i < 20 && ticks_left() > 0; ++i) {
        h_.tick();
      }
    }
    while (ticks_left() > 0) {
      h_.tick();
    }
    ASSERT_EQ(h_.view().branch, target);
    ASSERT_FALSE(h_.runner().done());
  }

  Cause cause_;
  Harness h_;
  std::int64_t cleanup_start_ns_{0};
};

class CleanupCellTest : public ::testing::TestWithParam<CleanupCell>
{
};

TEST_P(CleanupCellTest, ObservesCell)
{
  const CleanupCell & cell = GetParam();
  CleanupRig rig(cell.cause);
  ASSERT_NO_FATAL_FAILURE(rig.enter(cell.reach, cell.event));
  ASSERT_NO_FATAL_FAILURE(rig.reach(cell.reach));
  ASSERT_NO_FATAL_FAILURE(rig.trigger(cell.event, cell.reason));
  expect_cell(rig.h(), cleanup_state(cell), cell.event, cell.to, cell.reason);
  if (std::string(cell.to) == "DONE") {
    expect_terminated_once_as(rig.h(), cell.reason);
  } else {
    EXPECT_FALSE(rig.h().runner().done());
  }
}

std::string cell_test_name(const ::testing::TestParamInfo<CleanupCell> & info)
{
  return std::string(cause_tag(info.param.cause)) + "_" + reach_tag(info.param.reach) + "_" +
         event_name(info.param.event);
}

constexpr const char * kDone = "DONE";
constexpr const char * kMsf = "ABORTED/MODE_SWITCH_FAILED";
constexpr const char * kArmRej = "ABORTED/ARM_REJECTED";
constexpr const char * kItemTo = "ABORTED/ITEM_TIMEOUT";

// 1a 칸 목록(transition_cells.tsv)에서 B8 때 미덮임이던 정리 칸. 순서는 목록과 같다.
const CleanupCell kCleanupCells[] = {
  // 취소
  {Cause::kCancel, Reach::kNone, Event::kCleanupNoSample, kDone, "CANCELED/NONE"},
  {Cause::kCancel, Reach::kNone, Event::kCleanupLinkLost, kDone, "ABORTED/LINK_LOST"},
  {Cause::kCancel, Reach::kNone, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE"},
  {Cause::kCancel, Reach::kAir, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL"},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupLinkLost, kDone, "ABORTED/LINK_LOST"},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE"},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupNothingToDo, kDone, "CANCELED/NONE"},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupCap, kDone, "ABORTED/DISARM_FAILED"},
  {Cause::kCancel, Reach::kAirLand, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL"},
  {Cause::kCancel, Reach::kGround, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE"},
  {Cause::kCancel, Reach::kGround, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL"},
  // ITEM_TIMEOUT
  {Cause::kItemTimeout, Reach::kNone, Event::kCleanupAirDisarm, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAir, Event::kCleanupLinkLost, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAir, Event::kCleanupAirDisarm, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupCap, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kStampUnavailable, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kGround, Event::kCleanupAirDisarm, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kGround, Event::kStampUnavailable, kDone, kItemTo},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kEnterGround, "CLEANUP.ITEM_TIMEOUT.GROUND", "-"},
  {Cause::kItemTimeout, Reach::kGroundAfterHoldFailure, Event::kEnterAir,
   "CLEANUP.ITEM_TIMEOUT.AIR_LAND", "-"},
  {Cause::kItemTimeout, Reach::kAir, Event::kHoldRejected, "CLEANUP.ITEM_TIMEOUT.AIR_LAND", "-"},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kLandPathTimeout, kDone, kItemTo},
  // PREPARING 실패
  {Cause::kPrepModeSwitch, Reach::kNone, Event::kCleanupLinkLost, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kNone, Event::kCleanupAirDisarm, kDone, kMsf},
  {Cause::kPrepArm, Reach::kNone, Event::kCleanupLinkLost, kDone, kArmRej},
  {Cause::kPrepArm, Reach::kNone, Event::kCleanupAirDisarm, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupLinkLost, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAir, Event::kCleanupLinkLost, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupAirDisarm, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAir, Event::kCleanupAirDisarm, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupNothingToDo, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupCap, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kStampUnavailable, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAir, Event::kStampUnavailable, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupNothingToDo, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupCap, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupCap, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kStampUnavailable, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAirLand, Event::kStampUnavailable, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupLinkLost, kDone, kMsf},
  {Cause::kPrepArm, Reach::kGround, Event::kCleanupLinkLost, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupAirDisarm, kDone, kMsf},
  {Cause::kPrepArm, Reach::kGround, Event::kCleanupAirDisarm, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupCap, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kStampUnavailable, kDone, kMsf},
  {Cause::kPrepArm, Reach::kGround, Event::kStampUnavailable, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kEnterGround, "CLEANUP.PREPARING_FAILURE.GROUND",
   "-"},
  {Cause::kPrepModeSwitch, Reach::kGroundAfterHoldFailure, Event::kEnterAir,
   "CLEANUP.PREPARING_FAILURE.AIR_LAND", "-"},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldConfirmed, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldRejected, "CLEANUP.PREPARING_FAILURE.AIR_LAND",
   "-"},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldTimeout, "CLEANUP.PREPARING_FAILURE.AIR_LAND",
   "-"},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kLandPathModeObserved, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kLandPathTimeout, kDone, kMsf},
  {Cause::kPrepArm, Reach::kAirLand, Event::kLandPathModeObserved, kDone, kArmRej},
  {Cause::kPrepArm, Reach::kAirLand, Event::kLandPathTimeout, kDone, kArmRej},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kGroundDisarmConfirmed, kDone, kMsf},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kGroundDisarmTimeout, kDone, kMsf},
};

INSTANTIATE_TEST_SUITE_P(
  Cells, CleanupCellTest, ::testing::ValuesIn(kCleanupCells), cell_test_name);

}  // namespace
}  // namespace idsim_mission::core::test
