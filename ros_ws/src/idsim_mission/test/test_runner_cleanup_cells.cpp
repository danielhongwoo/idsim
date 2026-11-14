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
// runner의 전이 기록(expect_cell)과 종료 결과로 단정하고, 그 칸의 기록이 난 tick의 명령을 1a 표대로
// 단정한다(CleanupCell::sent).
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
//   kRtlFailure: 공중 ARMED Hold에서 시작한 [RTL]의 NAV_RTL 거부 ack(S+1, 합성). reason
//   MODE_SWITCH_FAILED, arm을 보내지 않았다. 공중이면 Hold 없이 Land 경로라 kAirLand가 정리 첫
//   tick에 닿고, Hold 실패 표시는 끝까지 서지 않는다(1b decisions.md 쟁점 9).
// - 분기(Reach): kNone은 정리 첫 tick에 끝나는 칸이라 사건이 시작 표본을 정한다(표본 없음, 상태
//   끊김, 공중 DISARMED). kAir는 ARMED이고 landed false, kGround는 ARMED이고 landed true로
//   시작한다. kAirLand는 kAir에서 Hold 거부 ack로 Land 경로에 간 상태, kGroundAfterHoldFailure는
//   kAirLand에서 landed true로 지상 분기에 간 상태다(Hold 실패 표시가 남아 공중 재진입이 Land
//   경로가 된다).
// - 정리의 상한(12 s)은 분기 타임아웃(3 s)보다 길어 한 분기에 머물러서는 닿지 않는다. 상한 칸은
//   landed를 바꿔 분기를 나갔다 바로 다시 들어오기를 되풀이해(재진입이 분기 타이머를 다시 시작한다)
//   목표 분기에 있는 채 상한 tick을 맞는다. 상한 tick의 표본이 그 tick의 고르기를 정하므로 그
//   표본의 landed를 칸의 입력(cap_on_ground)으로 따로 둔다. 머무는 tick 수는 분기 타임아웃과 tick
//   주기에서 파생한다(BranchTicks).
// - 명령 단정(sent): 칸의 기록이 난 tick의 commands가 정확히 그 값이다. 관측으로 끝나는 칸(표본
//   없음, 상태 끊김, 공중 DISARMED, 정리할 것 없음, Hold 확인, AUTO_LAND 관측, Land 경로 만료, 지상
//   disarm 확인)은 명령이 없고, 지상으로 고른 tick의 상태 끊김과 지상 disarm 만료는 끝내기 전
//   disarm 1회, 상한은 지상이면 disarm 1회이고 공중이면 NAV_LAND 1회, Px4Timestamp 실패는 명령과
//   setpoint를 버린다. 분기 전이는 들어간 분기의 첫 명령(지상 disarm, Land 경로 NAV_LAND)이다. Hold
//   거부와 Hold 만료는 NAV_LAND가 그 tick에 처음 나가고(앞에는 없다) 그 시점(거부 ack의 tick, Hold
//   첫 전송부터 hold_confirm_timeout)도 단정한다. DONE 칸은 끝나는 tick에 setpoint가 없고, 끝난
//   뒤의 tick에 명령이 없다(expect_terminated_once).
// - 기체 반응(auto_px4)은 입구 뒤에 끄고 표본을 직접 정한다. 외부 arm(P3-P5에 ARMED), 공중
//   DISARMED, 거부 ack, 첫 ARMED 표본보다 묵은 표본은 PX4 v1.17.0에서 재현하기 어려운 방어 경로라
//   합성 표본과 합성 ack로만 시험한다.
// - 묵은 표본 칸(CLEANUP.ITEM_TIMEOUT.NONE CLEANUP_AIR_DISARM): PX4의 vehicle_status timestamp는
//   한 번의 PX4 부팅 안에서는 단조라 그 안에서는 나오지 않는다. 그래도 impossible이 아니다.
//   core는 vehicle_status timestamp의 단조를 전제로 두지 않고, 첫 ARMED 표본보다 작은 timestamp의
//   표본을 감시 구간에서만 거르고 정리에서는 그대로 쓰는 동작을 스스로 정의한다
//   (mission_runner.cpp의 monitored_status, README
//   "표에 없어 구현에서 정한 것" 6). 단조는 core 밖(PX4)의 사실이라 "불가능"의 근거가 아니므로
//   방어 경로로 덮는다.

#include <gtest/gtest.h>

#include <algorithm>
#include <cstddef>
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
  kRtlFailure,
};

enum class Reach : std::uint8_t
{
  kNone,
  kAir,
  kAirLand,
  kGround,
  kGroundAfterHoldFailure,
};

// 칸의 기록이 난 tick에 나가는 명령(정리 칸은 그 tick에 많아야 하나다).
enum class Sent : std::uint8_t
{
  kNothing,
  kDisarm,
  kNavLand,
};

// 칸 하나. from은 원인과 분기에서 나온다(cleanup_state). sent는 기대 명령이고, cap_on_ground는
// 입력이다(상한 tick 표본의 landed. CLEANUP_CAP 칸에만 쓴다).
struct CleanupCell
{
  Cause cause;
  Reach reach;
  Event event;
  const char * to;
  const char * reason;
  Sent sent;
  bool cap_on_ground{false};
};

std::vector<CommandKind> commands_of(Sent sent)
{
  switch (sent) {
    case Sent::kNothing:
      return {};
    case Sent::kDisarm:
      return {CommandKind::kDisarm};
    case Sent::kNavLand:
      return {CommandKind::kNavLand};
  }
  return {};
}

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
    case Cause::kRtlFailure:
      return "RTL_FAILURE";
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
    case Cause::kRtlFailure:
      return "RtlFailure";
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

// 시간 값을 tick 수로. 정리의 tick 열은 시각을 건너뛰지 않으므로 tick 수가 곧 경과다.
int ticks_of(std::int64_t ns) { return static_cast<int>(ns / kTickNs); }

// 분기에 머무는 tick 수(hold_branch_until_cap). 분기 타임아웃 중 짧은 것(Hold 확인과 Land 경로,
// 지상 disarm 확인)보다 짧게 머물러야 분기 사건이 나지 않는다. 다시 들어온 뒤 stay만큼 머물고,
// 상한까지 남은 tick이 tail 이하이면 그대로 상한 tick까지 간다(가장 긴 머묾은 stay + tail).
struct BranchTicks
{
  int timeout;
  int stay;
  int tail;
};

BranchTicks branch_ticks(const Timeouts & t)
{
  BranchTicks b{};
  b.timeout = ticks_of(std::min(t.hold_confirm_timeout_ns, t.mode_confirm_timeout_ns));
  b.stay = b.timeout / 3;
  b.tail = b.timeout / 2;
  return b;
}

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
      case Cause::kRtlFailure:
        enter_rtl_failure(start);
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
        if (cause_ == Cause::kRtlFailure) {
          // RTL 실패의 공중 진입은 바로 Land 경로다.
          ASSERT_EQ(h_.view().branch, Branch::kAirLand);
          return;
        }
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

  // 칸의 사건을 일으킨다. 정리 첫 tick에 끝나는 칸(분기 NONE)은 enter가 이미 일으켰다.
  void trigger(const CleanupCell & cell)
  {
    if (cell.reach == Reach::kNone) {
      return;
    }
    ASSERT_EQ(h_.view().stage, Stage::kCleanup)
      << "not in cleanup before " << event_name(cell.event);
    const BranchTicks b = branch_ticks(h_.config().timeouts);
    switch (cell.event) {
      case Event::kCleanupLinkLost:
        // 분기 안의 상태 끊김: status 없이 link_timeout을 보낸다(분기 타임아웃보다 짧다).
        h_.auto_samples = false;
        for (int i = 0; i < link_ticks() && !h_.runner().done(); ++i) {
          h_.step_only();
        }
        return;
      case Event::kCleanupAirDisarm:
        set_world(Arming::kDisarmed, false);
        h_.tick();
        return;
      case Event::kCleanupNothingToDo:
        set_world(Arming::kDisarmed, true);
        h_.tick();
        return;
      case Event::kCleanupCap:
        // 상한 tick의 표본(ARMED, landed = cap_on_ground)이 그 tick의 고르기를 정한다.
        ASSERT_NO_FATAL_FAILURE(hold_branch_until_cap());
        set_world(Arming::kArmed, cell.cap_on_ground);
        h_.tick();
        return;
      case Event::kStampUnavailable:
        h_.clock.fail = true;
        h_.tick();
        // [RTL]은 발행하지 않으므로 Px4Timestamp는 명령(재전송)이 있는 tick에만 묻는다.
        for (int i = 0;
             i < ticks_of(h_.config().timeouts.command_resend_period_ns) && !h_.runner().done();
             ++i) {
          h_.tick();
        }
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
        h_.run_until([this] { return h_.runner().done(); }, kConfirmSamples + 1);
        return;
      case Event::kHoldRejected:
        reject_hold();
        return;
      case Event::kHoldTimeout:
        h_.run_until([this] { return h_.view().branch == Branch::kAirLand; }, b.timeout + 1);
        return;
      case Event::kLandPathModeObserved:
        h_.world.nav = NavMode::kLand;
        h_.world.intention = NavMode::kLand;
        h_.tick();
        return;
      case Event::kLandPathTimeout:
      case Event::kGroundDisarmTimeout:
        h_.run_until([this] { return h_.runner().done(); }, b.timeout + 1);
        return;
      case Event::kGroundDisarmConfirmed:
        set_world(Arming::kDisarmed, true);
        h_.run_until([this] { return h_.runner().done(); }, kConfirmSamples + 1);
        return;
      default:
        ADD_FAILURE() << "no trigger for " << event_name(cell.event) << " in a branch";
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
    if (cause == Cause::kRtlFailure) {
      m = rtl_only_mission();
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
          // ITEM_TIMEOUT은 감시 표가, RTL 실패는 모드 명령 항목 처리가 같은 tick에 먼저 보므로,
          // 정리만 보는 묵은 표본이어야 닿는다.
          start.stale_timestamp = cause_ == Cause::kItemTimeout || cause_ == Cause::kRtlFailure;
        } else if (event == Event::kCleanupNothingToDo) {
          start.arming = Arming::kDisarmed;
          start.landed = true;
        } else if (event == Event::kEnterGround) {
          start.landed = true;
        } else if (event == Event::kEnterAir) {
          start.landed = false;
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
    for (int i = 0; i < link_ticks() - 1; ++i) {
      h_.step_only();
    }
  }

  void mark_start() { cleanup_start_ns_ = h_.now_ns; }

  // 마지막 status 뒤 이 수만큼 지난 tick이 처음 끊긴 tick이다.
  int link_ticks() const { return ticks_of(h_.config().timeouts.link_timeout_ns); }

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

  void enter_rtl_failure(const StartSample & start)
  {
    // S: 공중 ARMED Hold에서 [RTL]을 시작하고 NAV_RTL을 보낸다. S+1(묵은 표본이면 S+2)에 거부
    // ack와 시작 표본.
    h_.start_in_air();
    h_.auto_px4 = false;
    h_.tick();
    ASSERT_EQ(h_.view().stage, Stage::kItem);
    if (start.stale_timestamp) {
      // 모드 명령 항목이 처리한 표본이 있어야 그보다 묵은 표본을 건너뛴다(S에는 처리하지 않는다).
      h_.tick();
      h_.push_ack(AckCommand::kNavRtl, AckResult::kTemporarilyRejected);
      mark_start();
      Sample stale = disarmed(start.landed);
      stale.timestamp_us = 1;
      h_.feed({stale});
      return;
    }
    h_.push_ack(AckCommand::kNavRtl, AckResult::kTemporarilyRejected);
    mark_start();
    set_world(start.arming, start.landed);
    h_.tick();
  }

  void reject_hold()
  {
    h_.push_ack(AckCommand::kSetMode, AckResult::kDenied);
    h_.tick();
  }

  // 지금 분기에 있는 채 정리의 상한 직전 tick까지 간다. 분기 타임아웃 전에 다른 분기로 나갔다 바로
  // 돌아와 분기 타이머를 다시 시작한다. 다음 tick이 상한 tick이다.
  void hold_branch_until_cap()
  {
    const BranchTicks b = branch_ticks(h_.config().timeouts);
    ASSERT_LT(b.stay + b.tail + 1, b.timeout) << "branch stay must be shorter than its timeout";
    const Branch target = h_.view().branch;
    const bool target_landed = h_.world.landed;
    const std::int64_t cap_at = cleanup_start_ns_ + cleanup_cap_ns(h_.config().timeouts);
    const auto ticks_left = [this, cap_at] { return (cap_at - h_.now_ns) / kTickNs; };
    while (ticks_left() > b.tail) {
      h_.world.landed = !target_landed;
      h_.tick();
      ASSERT_NE(h_.view().branch, target);
      h_.world.landed = target_landed;
      h_.tick();
      ASSERT_EQ(h_.view().branch, target);
      for (int i = 0; i < b.stay && ticks_left() > 0; ++i) {
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

// Hold 분기에 들어간 기록(ENTER_AIR -> AIR) 중 edges()의 end 앞에서 마지막 것.
const TransitionEdge * last_air_entry(const Harness & h, std::size_t end)
{
  for (std::size_t i = end; i > 0; --i) {
    const TransitionEdge & edge = h.edges()[i - 1];
    if (edge.tagged && edge.event == Event::kEnterAir && edge.to.branch == Branch::kAir) {
      return &edge;
    }
  }
  return nullptr;
}

TEST_P(CleanupCellTest, ObservesCell)
{
  const CleanupCell & cell = GetParam();
  CleanupRig rig(cell.cause);
  const Harness & h = rig.h();
  ASSERT_NO_FATAL_FAILURE(rig.enter(cell.reach, cell.event));
  ASSERT_NO_FATAL_FAILURE(rig.reach(cell.reach));
  // 분기 NONE의 칸은 enter가 일으켰으므로 처음부터, 그 밖은 trigger 뒤의 기록에서만 찾는다.
  const std::size_t mark = cell.reach == Reach::kNone ? 0 : h.edges().size();
  ASSERT_NO_FATAL_FAILURE(rig.trigger(cell));
  const TransitionEdge * const edge =
    expect_cell(h, cleanup_state(cell), cell.event, cell.to, cell.reason, {}, mark);
  ASSERT_NE(edge, nullptr);
  const StepOutput * const out = output_of_tick(h, edge->tick);
  ASSERT_NE(out, nullptr);
  // 그 tick의 명령은 1a 표대로 정확히 이것이다.
  EXPECT_EQ(out->commands, commands_of(cell.sent)) << "tick " << edge->tick;
  const bool done = std::string(cell.to) == "DONE";
  if (done) {
    EXPECT_FALSE(out->setpoint.has_value()) << "tick " << edge->tick;
  }
  if (cell.event == Event::kHoldRejected || cell.event == Event::kHoldTimeout) {
    // NAV_LAND는 이 tick에 처음 나간다.
    for (std::uint64_t tick = 1; tick < edge->tick; ++tick) {
      const StepOutput * const before = output_of_tick(h, tick);
      ASSERT_NE(before, nullptr);
      EXPECT_FALSE(has_command(*before, CommandKind::kNavLand)) << "tick " << tick;
    }
    const TransitionEdge * const entry = last_air_entry(h, mark);
    ASSERT_NE(entry, nullptr);
    if (cell.event == Event::kHoldRejected) {
      // 거부 ack는 Hold를 처음 보낸 다음 tick에 받았다.
      EXPECT_EQ(edge->tick, entry->tick + 1);
    } else {
      // Hold를 처음 보낸 tick부터 hold_confirm_timeout.
      const StepOutput * const sent = output_of_tick(h, entry->tick);
      ASSERT_NE(sent, nullptr);
      ASSERT_TRUE(sent->feedback.has_value());
      ASSERT_TRUE(out->feedback.has_value());
      EXPECT_EQ(
        out->feedback->stamp_ns - sent->feedback->stamp_ns,
        h.config().timeouts.hold_confirm_timeout_ns);
    }
  }
  if (cell.cause == Cause::kRtlFailure) {
    // RTL 실패의 정리는 Hold를 보내지 않으므로 Hold 실패 표시가 서지 않는다.
    EXPECT_FALSE(h.view().hold_failed);
    EXPECT_EQ(h.count_command(CommandKind::kSetModeHold), 0);
  }
  if (done) {
    expect_terminated_once_as(rig.h(), cell.reason);
  } else {
    EXPECT_FALSE(h.runner().done());
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

// 1a 칸 목록(transition_cells.tsv)에서 B8 때 미덮임이던 정리 칸. 순서는 목록과 같다. 열은 원인,
// 분기, 사건, to, reason, 그 tick의 기대 명령, (상한 칸만) 상한 tick 표본의 landed다.
const CleanupCell kCleanupCells[] = {
  // 취소
  {Cause::kCancel, Reach::kNone, Event::kCleanupNoSample, kDone, "CANCELED/NONE", Sent::kNothing},
  {Cause::kCancel, Reach::kNone, Event::kCleanupLinkLost, kDone, "ABORTED/LINK_LOST",
   Sent::kNothing},
  {Cause::kCancel, Reach::kNone, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE",
   Sent::kNothing},
  {Cause::kCancel, Reach::kAir, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL",
   Sent::kNothing},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupLinkLost, kDone, "ABORTED/LINK_LOST",
   Sent::kNothing},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE",
   Sent::kNothing},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupNothingToDo, kDone, "CANCELED/NONE",
   Sent::kNothing},
  {Cause::kCancel, Reach::kAirLand, Event::kCleanupCap, kDone, "ABORTED/DISARM_FAILED",
   Sent::kDisarm, true},
  {Cause::kCancel, Reach::kAirLand, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL",
   Sent::kNothing},
  {Cause::kCancel, Reach::kGround, Event::kCleanupAirDisarm, kDone, "ABORTED/FAILSAFE",
   Sent::kNothing},
  {Cause::kCancel, Reach::kGround, Event::kStampUnavailable, kDone, "ABORTED/INTERNAL",
   Sent::kNothing},
  // ITEM_TIMEOUT
  {Cause::kItemTimeout, Reach::kNone, Event::kCleanupAirDisarm, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAir, Event::kCleanupLinkLost, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAir, Event::kCleanupAirDisarm, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kCleanupCap, kDone, kItemTo, Sent::kNavLand, false},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kStampUnavailable, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kGround, Event::kCleanupAirDisarm, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kGround, Event::kStampUnavailable, kDone, kItemTo, Sent::kNothing},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kEnterGround, "CLEANUP.ITEM_TIMEOUT.GROUND", "-",
   Sent::kDisarm},
  {Cause::kItemTimeout, Reach::kGroundAfterHoldFailure, Event::kEnterAir,
   "CLEANUP.ITEM_TIMEOUT.AIR_LAND", "-", Sent::kNavLand},
  {Cause::kItemTimeout, Reach::kAir, Event::kHoldRejected, "CLEANUP.ITEM_TIMEOUT.AIR_LAND", "-",
   Sent::kNavLand},
  {Cause::kItemTimeout, Reach::kAirLand, Event::kLandPathTimeout, kDone, kItemTo, Sent::kNothing},
  // PREPARING 실패
  {Cause::kPrepModeSwitch, Reach::kNone, Event::kCleanupLinkLost, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kNone, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kNone, Event::kCleanupLinkLost, kDone, kArmRej, Sent::kDisarm},
  {Cause::kPrepArm, Reach::kNone, Event::kCleanupAirDisarm, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupLinkLost, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAir, Event::kCleanupLinkLost, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAir, Event::kCleanupAirDisarm, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupNothingToDo, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kCleanupCap, kDone, kMsf, Sent::kNavLand, false},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kStampUnavailable, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAir, Event::kStampUnavailable, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupNothingToDo, kDone, kMsf,
   Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kCleanupCap, kDone, kMsf, Sent::kNavLand, false},
  {Cause::kPrepArm, Reach::kAirLand, Event::kCleanupCap, kDone, kArmRej, Sent::kNavLand, false},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kStampUnavailable, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAirLand, Event::kStampUnavailable, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupLinkLost, kDone, kMsf, Sent::kDisarm},
  {Cause::kPrepArm, Reach::kGround, Event::kCleanupLinkLost, kDone, kArmRej, Sent::kDisarm},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kGround, Event::kCleanupAirDisarm, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kCleanupCap, kDone, kMsf, Sent::kDisarm, true},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kStampUnavailable, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kGround, Event::kStampUnavailable, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kEnterGround, "CLEANUP.PREPARING_FAILURE.GROUND",
   "-", Sent::kDisarm},
  {Cause::kPrepModeSwitch, Reach::kGroundAfterHoldFailure, Event::kEnterAir,
   "CLEANUP.PREPARING_FAILURE.AIR_LAND", "-", Sent::kNavLand},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldConfirmed, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldRejected, "CLEANUP.PREPARING_FAILURE.AIR_LAND",
   "-", Sent::kNavLand},
  {Cause::kPrepModeSwitch, Reach::kAir, Event::kHoldTimeout, "CLEANUP.PREPARING_FAILURE.AIR_LAND",
   "-", Sent::kNavLand},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kLandPathModeObserved, kDone, kMsf,
   Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kAirLand, Event::kLandPathTimeout, kDone, kMsf, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAirLand, Event::kLandPathModeObserved, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepArm, Reach::kAirLand, Event::kLandPathTimeout, kDone, kArmRej, Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kGroundDisarmConfirmed, kDone, kMsf,
   Sent::kNothing},
  {Cause::kPrepModeSwitch, Reach::kGround, Event::kGroundDisarmTimeout, kDone, kMsf, Sent::kDisarm},
  // RTL 실패(S2). 칸 목록의 CLEANUP.RTL_FAILURE.* covered 19칸이다.
  {Cause::kRtlFailure, Reach::kNone, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kNone, Event::kCleanupNothingToDo, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kNone, Event::kEnterGround, "CLEANUP.RTL_FAILURE.GROUND", "-",
   Sent::kDisarm},
  {Cause::kRtlFailure, Reach::kNone, Event::kEnterAir, "CLEANUP.RTL_FAILURE.AIR_LAND", "-",
   Sent::kNavLand},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kCleanupLinkLost, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kCleanupNothingToDo, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kCleanupCap, kDone, kMsf, Sent::kNavLand, false},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kStampUnavailable, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kEnterGround, "CLEANUP.RTL_FAILURE.GROUND", "-",
   Sent::kDisarm},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kLandPathModeObserved, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kAirLand, Event::kLandPathTimeout, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kGround, Event::kCleanupLinkLost, kDone, kMsf, Sent::kDisarm},
  {Cause::kRtlFailure, Reach::kGround, Event::kCleanupAirDisarm, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kGround, Event::kCleanupCap, kDone, kMsf, Sent::kDisarm, true},
  {Cause::kRtlFailure, Reach::kGround, Event::kStampUnavailable, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kGround, Event::kEnterAir, "CLEANUP.RTL_FAILURE.AIR_LAND", "-",
   Sent::kNavLand},
  {Cause::kRtlFailure, Reach::kGround, Event::kGroundDisarmConfirmed, kDone, kMsf, Sent::kNothing},
  {Cause::kRtlFailure, Reach::kGround, Event::kGroundDisarmTimeout, kDone, kMsf, Sent::kDisarm},
};

INSTANTIATE_TEST_SUITE_P(
  Cells, CleanupCellTest, ::testing::ValuesIn(kCleanupCells), cell_test_name);

}  // namespace
}  // namespace idsim_mission::core::test
