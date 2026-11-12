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

// 상태기 단위 테스트의 tick 열 헬퍼. PX4 없이 core만 쓴다.
//
// - Harness는 20 Hz tick(50 ms)을 흉내 낸다. tick()은 (1) 이번 tick에 새로 들어온 표본을 Snapshot에
//   넣고(received_tick = 이번 tick 번호) (2) step을 한 번 부르고 (3) 번호와 시각을 올린다.
// - feedback이 있는 tick마다 그 stamp_ns가 tick 입력 시각과 같은지 단정한다.
// - 표본의 timestamp는 합성 값이다. 기본은 "수신 시각 - 1 ms"(us)라 명령에 실린 Px4Timestamp(그
//   tick의 시각)보다 다음 tick의 표본이 늘 뒤다. 실제 시계 관계는 재실측 (5)만 확인한다.
// - auto_px4가 true이면 간단한 가짜 PX4가 명령에 반응한다(다음 tick의 표본에 보인다):
//   Offboard -> OFFBOARD, Hold -> HOLD, NAV_LAND -> LAND, ARM -> ARMED, DISARM -> landed이면
//   DISARMED. 반응을 끄고 tick 열(feed)로 표본을 직접 주는 테스트도 있다.
// - 방어 경로(PX4 v1.17.0에서 나오지 않는 조합과 ack)는 합성 표본과 합성 ack로만 시험한다.
//   해당 테스트에 그렇게 적는다.

#ifndef RUNNER_HARNESS_HPP_
#define RUNNER_HARNESS_HPP_

#include <gtest/gtest.h>

#include <algorithm>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "idsim_mission/core/config.hpp"
#include "idsim_mission/core/mission_runner.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core::test
{

inline constexpr std::int64_t kTickNs = 50000000LL;  // 20 Hz
inline constexpr std::int64_t kStartNs = 100 * kNsPerSecond;

inline Duration seconds(std::int32_t s)
{
  Duration d;
  d.sec = s;
  return d;
}

inline ItemSpec takeoff_item(double height = 5.0, std::int32_t timeout_s = 20)
{
  ItemSpec item;
  item.type = item_type::kTakeoff;
  item.timeout = seconds(timeout_s);
  item.takeoff.height_m = height;
  item.takeoff.acceptance_m = 0.3;
  item.takeoff.yaw.mode = yaw_mode::kKeep;
  return item;
}

inline ItemSpec loiter_item(std::int32_t duration_s = 5, std::int32_t timeout_s = 10)
{
  ItemSpec item;
  item.type = item_type::kLoiter;
  item.timeout = seconds(timeout_s);
  item.loiter.duration = seconds(duration_s);
  return item;
}

inline ItemSpec land_item(std::int32_t timeout_s = 30)
{
  ItemSpec item;
  item.type = item_type::kLand;
  item.timeout = seconds(timeout_s);
  return item;
}

// 시나리오 A의 미션: [TAKEOFF 5 m, LOITER 5 s, LAND].
inline MissionSpec standard_mission()
{
  MissionSpec m;
  m.mission_id = "m1";
  m.items = {takeoff_item(), loiter_item(), land_item()};
  return m;
}

// [LAND] 한 항목 미션.
inline MissionSpec land_only_mission(std::int32_t timeout_s = 30)
{
  MissionSpec m;
  m.mission_id = "land1";
  m.items = {land_item(timeout_s)};
  return m;
}

class FakeClock : public Px4ClockPort
{
public:
  std::optional<std::uint64_t> now_us() override
  {
    ++calls;
    if (fail) {
      return std::nullopt;
    }
    return static_cast<std::uint64_t>(now_ns / 1000);
  }

  std::int64_t now_ns{kStartNs};
  bool fail{false};
  int calls{0};
};

// 가짜 PX4가 보고하는 기체 상태.
struct World
{
  Arming arming{Arming::kDisarmed};
  NavMode nav{NavMode::kHold};
  NavMode intention{NavMode::kHold};
  bool failsafe{false};
  IdentityCheck identity{IdentityCheck::kMatch};
  bool landed{true};
  double x{1.0};
  double y{2.0};
  double z{0.0};
  double heading{0.25};
  bool z_valid{true};
  bool ekf_ready{true};
  bool signal_lost{true};
};

// tick 열의 한 칸: 이번 tick에 들어올 vehicle_status 표본(fresh가 false이면 새 표본 없음).
struct Sample
{
  Arming arming{Arming::kArmed};
  NavMode nav{NavMode::kOffboard};
  bool landed{false};
  bool failsafe{false};
  NavMode intention{NavMode::kOffboard};
  bool fresh{true};
  std::optional<std::uint64_t> timestamp_us;  // 없으면 수신 시각 - 1 ms
};

inline Sample armed(NavMode nav = NavMode::kOffboard, bool landed = false)
{
  Sample s;
  s.arming = Arming::kArmed;
  s.nav = nav;
  s.landed = landed;
  return s;
}

inline Sample disarmed(bool landed, NavMode nav = NavMode::kOffboard)
{
  Sample s;
  s.arming = Arming::kDisarmed;
  s.nav = nav;
  s.landed = landed;
  return s;
}

inline Sample no_new_sample()
{
  Sample s;
  s.fresh = false;
  return s;
}

class Harness
{
public:
  explicit Harness(MissionSpec mission, Config config = Config{})
  : config_(config), runner_(std::move(mission), config, kStartNs)
  {
  }

  // 이번 tick의 표본을 world에서 만든다(auto_samples가 true일 때).
  void push_world_samples()
  {
    push_status();
    LandSample land;
    land.landed = world.landed;
    land.received_tick = tick_no;
    snapshot.land = land;
    PositionSample pos;
    pos.x = world.x;
    pos.y = world.y;
    pos.z = world.z;
    pos.heading = world.heading;
    pos.z_valid = world.z_valid;
    pos.received_tick = tick_no;
    snapshot.position = pos;
    FlagsSample flags;
    flags.ekf_ready = world.ekf_ready;
    flags.offboard_signal_lost = world.signal_lost;
    flags.received_tick = tick_no;
    snapshot.flags = flags;
  }

  void push_status(std::optional<std::uint64_t> timestamp_us = std::nullopt)
  {
    StatusSample s;
    s.timestamp_us = timestamp_us.has_value() ? *timestamp_us : default_timestamp_us();
    s.received_tick = tick_no;
    s.received_ns = now_ns;
    s.identity = world.identity;
    if (world.identity == IdentityCheck::kMismatch) {
      s.identity_detail = "expected sysid 2 component 1, got sysid 3 component 1";
    }
    s.arming = world.arming;
    s.nav = world.nav;
    s.nav_user_intention = world.intention;
    s.failsafe = world.failsafe;
    snapshot.status = s;
  }

  void push_land(bool landed)
  {
    world.landed = landed;
    LandSample land;
    land.landed = landed;
    land.received_tick = tick_no;
    snapshot.land = land;
  }

  void push_ack(AckCommand command, AckResult result)
  {
    AckSample ack;
    ack.command = command;
    ack.result = result;
    ack.received_tick = tick_no;
    snapshot.ack = ack;
  }

  std::uint64_t default_timestamp_us() const
  {
    return static_cast<std::uint64_t>(now_ns / 1000) - 1000U;
  }

  // 한 tick. auto_samples가 true이면 world의 표본을 먼저 넣는다.
  StepOutput tick(bool cancel = false)
  {
    if (auto_samples) {
      push_world_samples();
    }
    return step_only(cancel);
  }

  // 표본을 넣지 않고 step만(표본은 테스트가 직접 넣었다).
  StepOutput step_only(bool cancel = false)
  {
    clock.now_ns = now_ns + (port_skew ? port_skew(tick_no) : 0);
    TickInput input;
    input.tick = tick_no;
    input.now_ns = now_ns;
    input.cancel_requested = cancel || cancel_sticky;
    StepOutput out = runner_.step(input, snapshot, clock);
    // 불변식: feedback의 stamp는 그 tick의 입력 시각이다(Px4ClockPort가 본 시각이 아니다).
    if (out.feedback.has_value()) {
      EXPECT_EQ(out.feedback->stamp_ns, input.now_ns) << "tick " << input.tick;
    }
    record(out);
    ++tick_no;
    now_ns += kTickNs;
    return out;
  }

  // tick 열: 칸마다 vehicle_status 표본 하나(또는 없음)와 landed를 넣고 step한다. 위치와 flags는
  // world 값으로 같이 넣는다.
  std::vector<StepOutput> feed(const std::vector<Sample> & seq, bool cancel = false)
  {
    std::vector<StepOutput> outs;
    const bool saved = auto_samples;
    auto_samples = false;
    for (const Sample & s : seq) {
      if (s.fresh) {
        world.arming = s.arming;
        world.nav = s.nav;
        world.intention = s.intention;
        world.failsafe = s.failsafe;
        world.landed = s.landed;
        push_world_samples();
        if (s.timestamp_us.has_value()) {
          push_status(s.timestamp_us);
        }
      }
      outs.push_back(step_only(cancel));
    }
    auto_samples = saved;
    return outs;
  }

  // 조건이 맞을 때까지 tick. 넘으면 실패.
  template <typename Pred>
  bool run_until(Pred pred, int max_ticks = 2000, bool cancel = false)
  {
    for (int i = 0; i < max_ticks; ++i) {
      if (pred()) {
        return true;
      }
      if (runner_.done()) {
        return pred();
      }
      tick(cancel);
    }
    return pred();
  }

  // 지상, DISARMED, 준비 완료에서 시작해 TAKEOFF 항목이 시작될 때까지(가짜 PX4가 반응한다).
  void drive_to_takeoff()
  {
    ASSERT_TRUE(run_until([this] { return view().stage == Stage::kItem; }, 400))
      << "TAKEOFF did not start";
    ASSERT_EQ(view().item_index, 0U);
  }

  // TAKEOFF 목표 고도에 도달시켜 LOITER가 시작될 때까지.
  void drive_to_loiter()
  {
    drive_to_takeoff();
    world.landed = false;
    world.z = view().setpoint.z;
    ASSERT_TRUE(run_until([this] { return view().item_index == 1U; }, 100));
  }

  // LOITER를 지나 LAND 항목이 시작될 때까지.
  void drive_to_land()
  {
    drive_to_loiter();
    ASSERT_TRUE(run_until([this] { return view().item_index == 2U; }, 400));
  }

  RunnerView view() const { return runner_.view(); }
  const MissionRunner & runner() const { return runner_; }
  MissionRunner & mutable_runner() { return runner_; }
  const Config & config() const { return config_; }

  // 지금까지의 출력
  const std::vector<StepOutput> & outputs() const { return outputs_; }
  int termination_count() const { return termination_count_; }
  const std::optional<Termination> & termination() const { return termination_; }

  // 지금까지 보낸 명령(재전송 포함)의 순서.
  std::vector<CommandKind> commands() const
  {
    std::vector<CommandKind> all;
    for (const StepOutput & out : outputs_) {
      all.insert(all.end(), out.commands.begin(), out.commands.end());
    }
    return all;
  }

  int count_command(CommandKind kind) const
  {
    const std::vector<CommandKind> all = commands();
    return static_cast<int>(std::count(all.begin(), all.end(), kind));
  }

  World world;
  Snapshot snapshot;
  FakeClock clock;
  std::uint64_t tick_no{1};
  std::int64_t now_ns{kStartNs};
  // Px4ClockPort가 보는 시각 - tick 입력 시각(ns). 노드에서 두 시각은 따로 읽혀 tick마다 0 또는
  // /clock 한 양자만큼 어긋날 수 있다. tick 번호를 받아 그 tick의 값을 돌려준다. 비어 있으면 0.
  std::function<std::int64_t(std::uint64_t)> port_skew;
  bool auto_samples{true};
  bool auto_px4{true};
  bool cancel_sticky{false};

private:
  void record(const StepOutput & out)
  {
    outputs_.push_back(out);
    if (out.termination.has_value()) {
      ++termination_count_;
      termination_ = out.termination;
    }
    if (auto_px4) {
      react(out);
    }
  }

  // 가짜 PX4. 명령의 효과는 다음 tick의 표본에 보인다.
  void react(const StepOutput & out)
  {
    if (out.setpoint.has_value()) {
      world.signal_lost = false;
    }
    for (const CommandKind kind : out.commands) {
      switch (kind) {
        case CommandKind::kSetModeOffboard:
          world.nav = NavMode::kOffboard;
          world.intention = NavMode::kOffboard;
          break;
        case CommandKind::kSetModeHold:
          world.nav = NavMode::kHold;
          world.intention = NavMode::kHold;
          break;
        case CommandKind::kNavLand:
          world.nav = NavMode::kLand;
          world.intention = NavMode::kLand;
          break;
        case CommandKind::kArm:
          world.arming = Arming::kArmed;
          break;
        case CommandKind::kDisarm:
          if (world.landed) {
            world.arming = Arming::kDisarmed;
          }
          break;
      }
    }
  }

  Config config_;
  MissionRunner runner_;
  std::vector<StepOutput> outputs_;
  int termination_count_{0};
  std::optional<Termination> termination_;
};

// 종료 결과 == 종료 사건: 한 Termination에서 만든 result와 사건의 필드가 같다.
inline void expect_result_equals_event(const Termination & term, std::uint32_t item_count)
{
  const ResultFields result = to_result(term);
  const EventFields event = to_terminal_event(term, item_count);
  EXPECT_EQ(event.status, event_status_code(term.status));
  EXPECT_EQ(event.reason, result.reason);
  EXPECT_EQ(event.items_completed, result.items_completed);
  EXPECT_EQ(event.last_item_index, result.last_item_index);
  EXPECT_EQ(event.detail, result.detail);
  EXPECT_EQ(event.item_count, item_count);
  EXPECT_EQ(result.reason, static_cast<std::uint8_t>(term.reason));
  EXPECT_EQ(result.items_completed, term.items_completed);
  EXPECT_EQ(result.last_item_index, term.last_item_index);
  EXPECT_EQ(result.detail, term.detail);
}

// 종료 결과의 불변식: 정확히 1건, status와 reason의 대응, result == 사건, 끝난 뒤의 step은 빈 출력.
inline void expect_terminated_once(Harness & h, Status status, Reason reason)
{
  ASSERT_EQ(h.termination_count(), 1);
  ASSERT_TRUE(h.termination().has_value());
  const Termination & term = *h.termination();
  EXPECT_EQ(term.status, status) << status_name(term.status) << " " << term.detail;
  EXPECT_EQ(term.reason, reason) << reason_name(term.reason) << " " << term.detail;
  EXPECT_TRUE(is_consistent(term.status, term.reason));
  EXPECT_TRUE(h.runner().done());
  // 하네스 불변식: 모든 시나리오에서 종료 결과 == 종료 사건.
  expect_result_equals_event(term, static_cast<std::uint32_t>(h.runner().mission().items.size()));
  // 종료 뒤의 step은 명령, setpoint, feedback, 종료를 내지 않는다(취소가 와도).
  for (int i = 0; i < 3; ++i) {
    const StepOutput after = h.tick(i == 1);
    EXPECT_TRUE(after.commands.empty());
    EXPECT_FALSE(after.setpoint.has_value());
    EXPECT_FALSE(after.feedback.has_value());
    EXPECT_FALSE(after.termination.has_value());
  }
  EXPECT_EQ(h.termination_count(), 1);
}

// 종료 결과. 종료가 없으면(앞선 단정이 실패한 경우) 빈 Termination을 돌려 역참조로 테스트
// 프로세스가 죽지 않게 한다. detail은 "<no termination>"이다.
inline const Termination & termination_or_empty(const Harness & h)
{
  static const Termination empty = [] {
    Termination t;
    t.detail = "<no termination>";
    return t;
  }();
  return h.termination().has_value() ? *h.termination() : empty;
}

inline bool has_command(const StepOutput & out, CommandKind kind)
{
  return std::find(out.commands.begin(), out.commands.end(), kind) != out.commands.end();
}

}  // namespace idsim_mission::core::test

#endif  // RUNNER_HARNESS_HPP_
