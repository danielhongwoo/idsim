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

// goal 하나의 상태기. 정본은 docs-for-agent/plan-1a-6-idsim-mission/decisions.md의 쟁점 4 전이 표와
// 쟁점 3의 취소 분기다. 전이 표와 이 상태기의 단위 테스트를 바꾸려면 px4-engineer가 필수
// 승인자다(docs-for-agent/file-ownership.md).
//
// 쓰는 법(노드, P3d)
// - screen_goal(mission_validation.hpp)을 통과한 goal마다 MissionRunner를 하나 만든다.
// - 20 Hz timer tick마다 step(TickInput, Snapshot, Px4ClockPort)을 한 번 부른다. 입력과 출력의
//   뜻은 snapshot.hpp 머리 주석에 있다.
// - 출력의 setpoint가 있으면 그 tick에 offboard_control_mode와 trajectory_setpoint를 발행하고,
//   commands를 순서대로 보내고, feedback이 있으면 publish_feedback, termination이 있으면 그 값으로
//   goal을 끝내고 종료 사건을 낸다(termination.hpp). termination은 정확히 한 번 나온다. 그 뒤의
//   step은 빈 출력이다(명령, 사건, 상태를 바꾸지 않는다).
// - 취소: handle_cancel은 받아들이고, 다음 tick부터 TickInput.cancel_requested를 true로 넘긴다.
//   core가 그 tick의 snapshot으로 분기를 고른다. 이미 정해진 종료가 있으면 취소는 결과를 바꾸지
//   않는다(종료의 충돌 규칙).

#ifndef IDSIM_MISSION__CORE__MISSION_RUNNER_HPP_
#define IDSIM_MISSION__CORE__MISSION_RUNNER_HPP_

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "idsim_mission/core/config.hpp"
#include "idsim_mission/core/rules.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/termination.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

struct TickInput
{
  std::uint64_t tick{0};  // 1부터 하나씩 는다(snapshot.hpp의 received_tick과 같은 번호)
  std::int64_t now_ns{0};  // 이 tick의 ROS 시각(노드 시계)
  bool cancel_requested{false};
};

struct Feedback
{
  std::uint32_t item_index{0};
  std::uint32_t item_count{0};
  std::uint8_t item_type{0};
  FeedbackPhase phase{FeedbackPhase::kPreparing};
  bool distance_valid{false};
  double distance_remaining_m{0.0};
};

struct StepOutput
{
  // 이 tick의 명령과 setpoint에 실을 PX4 timestamp. 명령이나 setpoint가 있을 때만 있다.
  std::optional<std::uint64_t> px4_timestamp_us;
  // 있으면 이 tick에 발행한다. 없으면 발행하지 않는다.
  std::optional<SetpointOut> setpoint;
  // 이 tick에 보낼 명령(대개 0개나 1개). 재전송도 여기에 나온다.
  std::vector<CommandKind> commands;
  std::optional<Feedback> feedback;
  std::optional<Termination> termination;
};

enum class Stage : std::uint8_t
{
  kPreparing,
  kItem,
  kCleanup,  // 취소, setpoint 항목의 ITEM_TIMEOUT, PREPARING 실패 뒤의 정리
  kDone,
};

// PREPARING(첫 항목이 TAKEOFF)의 단계. kWaitReady는 P0-P2, kSignal은 P3-P4.
enum class PrepStep : std::uint8_t
{
  kWaitReady,
  kSignal,
  kOffboard,
  kArm,
};

enum class CleanupCause : std::uint8_t
{
  kCancel,
  kItemTimeout,
  kPreparingFailure,
};

enum class Branch : std::uint8_t
{
  kNone,
  kAir,      // Hold를 보내고 AUTO_LOITER 확인
  kAirLand,  // Hold가 거부되거나 확인되지 않아 NAV_LAND
  kGround,   // 지상 setpoint + disarm
};

// 테스트와 로그용 읽기 전용 상태.
struct RunnerView
{
  Stage stage{Stage::kPreparing};
  PrepStep prep{PrepStep::kWaitReady};
  std::uint32_t item_index{0};
  std::uint32_t items_completed{0};
  bool publishing{false};
  SetpointOut setpoint;
  bool arm_sent{false};
  bool pending_active{false};
  CommandKind pending{CommandKind::kArm};
  CleanupCause cleanup_cause{CleanupCause::kCancel};
  Branch branch{Branch::kNone};
  DisarmClass disarm_class{DisarmClass::kUnknown};
  bool land_confirmed{false};
  bool failsafe_history{false};
};

class MissionRunner
{
public:
  // mission은 validate_mission을 통과한 것이어야 한다. 통과하지 않으면 첫 step에서 INTERNAL로
  // 끝낸다. accept_ns는 goal 접수 ROS 시각(ready_timeout의 기준).
  MissionRunner(MissionSpec mission, Config config, std::int64_t accept_ns);

  StepOutput step(const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock);

  bool done() const { return stage_ == Stage::kDone; }
  RunnerView view() const;
  const MissionSpec & mission() const { return mission_; }

private:
  struct Tick;
  struct AckView
  {
    bool fresh{false};
    AckResult result{AckResult::kAccepted};
  };
  struct Pending
  {
    bool active{false};
    CommandKind kind{CommandKind::kArm};
    std::uint64_t first_tick{0};
    std::int64_t first_ns{0};
    std::int64_t last_ns{0};
    bool has_ack{false};
    AckResult last_ack{AckResult::kAccepted};
  };
  struct LandState
  {
    std::int64_t first_send_ns{0};
    bool confirmed{false};
    bool mode_seen{false};
    bool nav_land_accepted{false};
    int mode_count{0};
    int disarm_count{0};
    std::uint64_t last_timestamp_us{0};
    bool has_last{false};
    bool landed_armed_known{false};
    std::int64_t landed_armed_since_ns{0};
    bool fallback_started{false};
  };
  enum class Outcome : std::uint8_t
  {
    kSuccess,     // Hold 확인, disarm 확인, 정리할 것 없음
    kHoldFailed,  // Hold가 안 되어 Land 경로로 끝남
    kDisarmFailed,
    kLinkLost,
    kAirDisarm,
  };

  // 단계별 처리
  void step_preparing(Tick & t);
  void prepare_wait_ready(Tick & t);
  void prepare_signal(Tick & t);
  void prepare_offboard(Tick & t);
  void prepare_arm(Tick & t);
  void start_signal(Tick & t);
  void start_item(Tick & t, std::uint32_t index);
  void complete_item(Tick & t);
  void step_item(Tick & t);
  void step_setpoint_item(Tick & t);
  void step_land(Tick & t);
  void land_item_timeout(Tick & t, bool landed);
  void begin_cleanup(Tick & t, CleanupCause cause, Reason reason, std::string detail);
  void step_cleanup(Tick & t);
  void enter_ground(Tick & t);
  void run_ground(Tick & t);
  void enter_air(Tick & t);
  void run_air(Tick & t);
  void enter_air_land(Tick & t, const std::string & why);
  void run_air_land(Tick & t);
  void finish(Tick & t, Outcome outcome, const std::string & what);
  void finalize(Tick & t);

  // 도구
  void apply_publish_rule(const Tick & t);
  SetpointOut ground_setpoint(const Tick & t) const;
  void send(Tick & t, CommandKind kind);
  void send_once(Tick & t, CommandKind kind);
  void clear_pending() { pending_.active = false; }
  void resend_due(Tick & t);
  AckView take_ack(const Tick & t);
  bool link_lost(const Tick & t) const;
  std::int64_t elapsed(const Tick & t, std::int64_t since_ns) const;
  bool query_stamp(Tick & t);
  void terminate(Tick & t, Termination termination);
  Termination aborted(Reason reason, std::string detail) const;
  Termination canceled(std::string detail) const;
  Termination succeeded() const;
  FeedbackPhase current_phase() const;
  Feedback make_feedback(const Tick & t) const;
  const ItemSpec & current_item() const { return mission_.items.at(item_index_); }
  std::string item_label() const;

  // 선언 순서는 clang-analyzer의 padding 검사가 권한 순서다(뜻으로 묶지 않았다).
  std::int64_t accept_ns_;  // goal 접수 ROS 시각
  std::int64_t item_start_ns_{0};
  std::uint64_t item_start_tick_{0};
  double takeoff_target_z_{0.0};
  std::int64_t signal_start_ns_{0};  // P3 발행 시작
  std::uint64_t signal_start_tick_{0};
  std::int64_t step_start_ns_{0};  // P5, P6 시작
  std::uint64_t last_ack_tick_{0};
  std::int64_t branch_first_ns_{0};  // 정리 분기의 첫 명령 시각
  SampleCounter counter_;            // OFFBOARD, ARMED, AUTO_LOITER 확인
  std::string cleanup_detail_;
  std::string land_path_why_;
  SetpointOut setpoint_;
  SetpointOut reference_;  // P3에서 읽은 위치(지상 setpoint의 대체값)
  Pending pending_;        // 대기 중인 명령은 한 번에 하나
  DisarmConfirm disarm_confirm_;
  MissionSpec mission_;
  LandState land_;
  Config config_;
  std::uint32_t item_index_{0};
  std::uint32_t items_completed_{0};
  std::uint32_t publish_count_{0};
  bool mission_valid_{false};
  Stage stage_{Stage::kPreparing};
  PrepStep prep_{PrepStep::kWaitReady};
  bool acted_{false};  // 발행이나 명령을 한 번이라도 했는가
  bool publishing_{false};
  bool arm_sent_{false};
  bool failsafe_history_{false};
  DisarmClass disarm_class_{DisarmClass::kUnknown};
  CleanupCause cause_{CleanupCause::kCancel};
  Reason cleanup_reason_{Reason::kNone};
  FeedbackPhase cleanup_phase_{FeedbackPhase::kCanceling};
  Branch branch_{Branch::kNone};
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__MISSION_RUNNER_HPP_
