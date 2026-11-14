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
#include "idsim_mission/core/transition.hpp"
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
  // 이 feedback이 나타내는 tick의 ROS 시각(그 tick의 TickInput.now_ns). core가 경과 시간을 잰
  // 시각과 같은 값이라, 노드가 발행 때 시계를 다시 읽어 찍으면 /clock 한 양자만큼 어긋날 수 있다.
  std::int64_t stamp_ns{0};
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

// Stage, PrepStep, CleanupCause, Branch는 transition.hpp에 있다(전이 관측의 상태 key).

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
  bool land_confirmed{false};  // 모드 명령 항목(LAND, RTL)의 확인 대상 모드를 확인했다
  bool failsafe_history{false};
  bool armed_seen{false};         // P6에서 첫 ARMED 표본을 봤다
  bool landed_false_seen{false};  // 첫 ARMED 표본 뒤에 landed false를 받은 적이 있다
  bool hold_failed{false};  // 이 정리에서 Hold가 한 번 실패했다(RTL 실패의 정리는 늘 false)
};

class MissionRunner
{
public:
  // mission은 validate_mission_runnable을 통과한 것이어야 한다. 통과하지 않으면 첫 step에서
  // INTERNAL로 끝낸다. accept_ns는 goal 접수 ROS 시각(ready_timeout의 기준). observer가 있으면
  // step마다 그 tick의 전이 기록을 넘긴다(transition.hpp. 테스트가 쓴다). 없으면 기록하지 않고
  // 동작은 같다.
  MissionRunner(
    MissionSpec mission, Config config, std::int64_t accept_ns,
    TransitionObserver * observer = nullptr);

  StepOutput step(const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock);

  bool done() const { return stage_ == Stage::kDone; }
  RunnerView view() const;
  const MissionSpec & mission() const { return mission_; }

private:
  // 단위 테스트가 닿지 않는 방어 경로(정리 첫 tick의 식별 불일치)를 합성하려고 둔다.
  friend class MissionRunnerTestAccess;
  // 지금 tick에 취소의 정리를 시작한다(step의 단계 처리 없이). MissionRunnerTestAccess만 부른다.
  StepOutput begin_cancel_without_stage(
    const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock);
  // 전이 관측의 untagged 검출을 시험하려고 둔다(TransitionTestAccess만 부른다). 한 tick 안에서
  // steps를 차례로(꼬리표 달기 또는 set_state) 한 뒤 그 tick의 기록을 넘긴다. 상태기의 단계 처리는
  // 하지 않는다.
  friend class TransitionTestAccess;
  struct TestStep
  {
    bool is_tag{false};
    Event event{Event::kCancel};  // is_tag일 때
    StateKey key;                 // is_tag가 아닐 때
  };
  StepOutput run_test_steps(
    const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock,
    const std::vector<TestStep> & steps);

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
    std::uint64_t last_send_tick{0};  // 첫 전송이나 마지막 재전송의 tick
    std::int64_t first_ns{0};
    std::int64_t last_ns{0};
    bool has_ack{false};
    AckResult last_ack{AckResult::kAccepted};
    // 마지막으로 받은 비거부 ack(ACCEPTED, IN_PROGRESS)의 received_tick. 없으면 0.
    std::uint64_t accepted_ack_tick{0};
  };
  struct ModeItemState
  {
    std::int64_t first_send_ns{0};
    bool confirmed{false};
    bool mode_seen{false};
    bool command_accepted{false};
    int mode_count{0};
    int disarm_count{0};
    std::uint64_t last_timestamp_us{0};
    bool has_last{false};
    LandedArmedFallback fallback;  // 확인 뒤의 대비책 disarm
  };
  enum class Outcome : std::uint8_t
  {
    kSuccess,     // Hold 확인, disarm 확인, 정리할 것 없음
    kHoldFailed,  // Hold가 안 되어 Land 경로로 끝남
    kDisarmFailed,
    kLinkLost,
    kAirDisarm,
    kCapGround,  // 정리의 상한에 지상에서 닿음(disarm 1회)
    kCapAir,     // 정리의 상한에 공중에서 닿음(NAV_LAND 1회)
  };

  // 단계별 처리. 전이를 일으키는 함수는 첫 인자로 사건 꼬리표를 받는다(transition.hpp).
  void step_tick(Tick & t);
  void step_preparing(Tick & t);
  void prepare_wait_ready(Tick & t);
  void prepare_signal(Tick & t);
  void prepare_offboard(Tick & t);
  void prepare_offboard_ack(Tick & t);
  // ack 대기에서 arm 조건의 ack가 있으면 arm을 보내고 P6으로 간다(decisions.md 쟁점 12 불변식).
  // arm을 보냈으면 true.
  bool arm_if_offboard_acked(Tick & t);
  // 마지막 DO_SET_MODE 전송 tick보다 뒤에 받은 비거부 ack가 있다(arm 조건과 재전송 억제가 같이
  // 쓴다).
  bool has_valid_offboard_ack() const;
  // 지상 arm 진입(P5, P5a) 전용: 유효 ack가 없을 때만 resend_due.
  void resend_offboard_until_acked(Tick & t);
  void prepare_arm(Tick & t);
  void prepare_arm_before_armed(Tick & t);
  // later는 감시 표 뒤에 볼 사건 가운데 이 tick에 참인 것(겹침 칸의 기록용. 판정에 쓰지 않는다).
  bool monitor_flight(Tick & t, const std::string & label, const std::vector<Event> & later);
  const StatusSample * monitored_status(const Tick & t);
  void end_by_monitor(
    Tick & t, const MonitorVerdict & verdict, const std::string & label,
    const std::vector<Event> & later);
  void start_signal(Event event, Tick & t);
  void enter_prep(Event event, Tick & t, PrepStep prep);
  void start_item(Event event, Tick & t, std::uint32_t index);
  void complete_item(Event event, Tick & t);
  void step_item(Tick & t);
  void step_setpoint_item(Tick & t);
  void step_mode_item(Tick & t, const ModeItemSpec & spec);
  void mode_item_timeout(Tick & t, const ModeItemSpec & spec, bool landed);
  void begin_cleanup(Event event, Tick & t, CleanupCause cause, Reason reason, std::string detail);
  void step_cleanup(Tick & t);
  bool cleanup_cap_reached(const Tick & t) const;
  void end_at_cleanup_cap(Tick & t, bool on_ground);
  void cleanup_with_untrusted_sample(Tick & t);
  void enter_ground(Event event, Tick & t);
  void run_ground(Tick & t);
  void enter_air(Event event, Tick & t);
  void run_air(Tick & t);
  void enter_air_land(Event event, Tick & t, const std::string & why);
  void run_air_land(Tick & t);
  void finish(Event event, Tick & t, Outcome outcome, const std::string & what);
  void finalize(Tick & t);

  // 도구
  void apply_publish_rule(const Tick & t);
  SetpointOut ground_setpoint(const Tick & t) const;
  void send(Tick & t, CommandKind kind);
  void send_once(Tick & t, CommandKind kind);
  // 보냈으면 true. Px4Timestamp를 만들 수 없으면 보내지 않고 false.
  bool send_final(Tick & t, CommandKind kind, std::string & detail);
  void clear_pending() { pending_.active = false; }
  void resend_due(Tick & t);
  AckView take_ack(const Tick & t);
  bool link_lost(const Tick & t) const;
  std::int64_t elapsed(const Tick & t, std::int64_t since_ns) const;
  bool query_stamp(Tick & t);
  void terminate(Event event, Tick & t, Termination termination);

  // 전이 관측(transition.hpp). observer_가 없으면 아무것도 하지 않는다.
  StateKey state_key() const;
  // 상태 key 성분(stage_, prep_, item_index_, cause_, branch_)의 유일한 쓰기 지점. 열린 기록 동안
  // 상태 key를 두 번째로 바꾸는 쓰기는 untagged가 된다(같은 값 쓰기는 세지 않는다).
  void set_state(Tick & t, const StateKey & next);
  // 사건 꼬리표를 단다. 열린 기록을 닫고(to는 지금 상태) from이 지금 상태인 기록을 연다. 같은
  // 사건의 기록이 열려 있고 그 뒤 상태가 바뀌지 않았으면 새로 열지 않고 also_true만 더한다(전이
  // 함수가 꼬리표를 넘겨 다른 전이 함수를 부를 때).
  void tag(Event event, Tick & t, const std::vector<Event> & also_true = {});
  void close_record(Tick & t);
  // 단계 처리가 이 tick에 PREPARING이나 ITEM을 떠나 무시된 취소를 떠난 기록의 also_true에 싣는다.
  void note_ignored_cancel(Tick & t);
  void flush_records(Tick & t);
  Termination aborted(Reason reason, std::string detail) const;
  Termination canceled(std::string detail) const;
  Termination succeeded() const;
  FeedbackPhase current_phase() const;
  Feedback make_feedback(const Tick & t) const;
  const ItemSpec & current_item() const { return mission_.items.at(item_index_); }
  std::string item_label() const;

  // 선언 순서는 clang-analyzer의 padding 검사가 권한 순서다(뜻으로 묶지 않았다).
  std::int64_t accept_ns_;         // goal 접수 ROS 시각
  TransitionObserver * observer_;  // 없으면 nullptr
  std::int64_t item_start_ns_{0};
  std::uint64_t item_start_tick_{0};
  double takeoff_target_z_{0.0};
  std::int64_t signal_start_ns_{0};  // P3 발행 시작
  std::uint64_t signal_start_tick_{0};
  std::int64_t step_start_ns_{0};  // P5, P6 시작(ack 대기는 P5의 것을 그대로 쓴다)
  // OFFBOARD 확인에 쓴 3번째 표본의 timestamp. ack 대기의 이탈 판정은 이보다 큰 표본만 본다.
  std::uint64_t offboard_confirm_timestamp_us_{0};
  std::uint64_t last_ack_tick_{0};
  std::int64_t branch_first_ns_{0};  // 정리 분기의 첫 명령 시각
  std::int64_t cleanup_start_ns_{0};  // 정리를 시작한 tick의 ROS 시각(정리의 상한 M6의 기준)
  std::uint64_t arm_first_tick_{0};  // P6에서 arm을 처음 보낸 tick
  std::int64_t first_armed_ns_{0};  // 첫 ARMED 표본을 본 tick의 ROS 시각(P6 확인 기한의 기준)
  std::uint64_t first_armed_tick_{0};
  std::uint64_t first_armed_timestamp_us_{0};  // 이보다 작은 timestamp의 표본은 판정에 쓰지 않는다
  // failsafe 이력(감시 표 순위 5)에 넣는 표본은 received_tick이 이 값보다 큰 것이다. P6과 TAKEOFF는
  // 한 구간(첫 ARMED 표본 포함)이고 그 뒤 항목은 항목이 시작된 뒤에 받은 표본부터다.
  std::uint64_t history_after_tick_{0};
  std::optional<StatusSample> trusted_status_;  // 감시 구간에서 판정에 쓰는 최신 vehicle_status
  SampleCounter counter_;                       // OFFBOARD, ARMED, AUTO_LOITER 확인
  std::string cleanup_detail_;
  std::string land_path_why_;
  std::string hold_failed_why_;  // 이 정리에서 Hold가 처음 실패한 이유
  SetpointOut setpoint_;
  SetpointOut reference_;  // P3에서 읽은 위치(지상 setpoint의 대체값)
  Pending pending_;        // 대기 중인 명령은 한 번에 하나
  DisarmConfirm disarm_confirm_;
  MissionSpec mission_;
  ModeItemState mode_item_;
  Config config_;
  std::uint32_t item_index_{0};
  std::uint32_t items_completed_{0};
  std::uint32_t publish_count_{0};
  bool mission_valid_{false};
  EntryPlan entry_plan_{EntryPlan::kGroundArm};  // 첫 항목 type에서 정한 진입 방식
  std::string invalid_detail_;  // mission_valid_가 false일 때 validate_mission_runnable의 detail
  Stage stage_{Stage::kPreparing};
  PrepStep prep_{PrepStep::kWaitReady};
  bool acted_{false};  // 발행이나 명령을 한 번이라도 했는가
  bool publishing_{false};
  bool arm_sent_{false};
  bool failsafe_history_{false};
  bool armed_seen_{false};
  bool landed_false_seen_{false};
  bool hold_failed_{false};
  bool hold_observed_{false};  // 정리 중 AUTO_LOITER 표본을 본 적이 있다
  DisarmClass disarm_class_{DisarmClass::kUnknown};
  CleanupCause cause_{CleanupCause::kCancel};
  Reason cleanup_reason_{Reason::kNone};
  FeedbackPhase cleanup_phase_{FeedbackPhase::kCanceling};
  Branch branch_{Branch::kNone};
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__MISSION_RUNNER_HPP_
