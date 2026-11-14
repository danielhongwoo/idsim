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

// 상태기 구현. 표의 행과 이 파일의 대응은 README.md "전이 표와 구현의 대응"에 있다.
//
// 한 tick 안의 판정 순서(decisions.md 쟁점 3 "종료의 충돌 규칙"을 전이에도 같게 쓴다)
// 1. 그 단계의 실패(감시 표, 상태 끊김, 거부 ack, 타임아웃 만료)
// 2. 확인과 완료(N회 연속, 도달, 경과)
// 3. 취소(실패나 완료로 끝나지 않았고 정리 중이 아닐 때만)
// 4. 출력 마무리(timestamp, setpoint, feedback)
// 정리 중의 순서는 따로 있다(쟁점 3 M6): 상태 끊김 -> 공중 DISARMED -> 정리할 것 없음 -> 정리의
// 상한 -> 그 분기의 실행. step_cleanup 머리 주석.

#include "idsim_mission/core/mission_runner.hpp"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "idsim_mission/core/mission_validation.hpp"
#include "idsim_mission/core/transition.hpp"

namespace idsim_mission::core
{

struct MissionRunner::Tick
{
  Tick(
    const TickInput & in, const Snapshot & snapshot, Px4ClockPort & clock_port, StepOutput & output)
  : input(in), clock(clock_port), out(output)
  {
    status = snapshot.status.has_value() ? &*snapshot.status : nullptr;
    land = snapshot.land.has_value() ? &*snapshot.land : nullptr;
    position = snapshot.position.has_value() ? &*snapshot.position : nullptr;
    flags = snapshot.flags.has_value() ? &*snapshot.flags : nullptr;
    ack = snapshot.ack.has_value() ? &*snapshot.ack : nullptr;
  }

  const TickInput & input;
  Px4ClockPort & clock;
  StepOutput & out;
  const StatusSample * status{nullptr};
  const LandSample * land{nullptr};
  const PositionSample * position{nullptr};
  const FlagsSample * flags{nullptr};
  const AckSample * ack{nullptr};
  bool stamp_queried{false};
  bool stamp_ok{false};
  std::uint64_t stamp_us{0};
  // 전이 관측(observer가 있을 때만 쓴다). checkpoint는 마지막으로 닫은 기록의 to(처음은 tick 시작).
  std::vector<TransitionEdge> edges;
  TransitionEdge open_edge;
  bool open{false};
  int open_changes{0};  // 열린 기록 동안 상태 key를 바꾼 쓰기 수
  StateKey checkpoint;
};

namespace
{

bool position_finite(const PositionSample & p)
{
  return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z);
}

const char * arming_name(Arming arming) { return arming == Arming::kArmed ? "ARMED" : "DISARMED"; }

Event monitor_event(MonitorRow row)
{
  switch (row) {
    case MonitorRow::kTimestampFailure:
      return Event::kMonitorTimestampFailure;
    case MonitorRow::kIdentityMismatch:
      return Event::kMonitorIdentityMismatch;
    case MonitorRow::kLinkLost:
      return Event::kMonitorLinkLost;
    case MonitorRow::kDisarmedInAir:
      return Event::kMonitorDisarmedInAir;
    case MonitorRow::kDisarmedOnGround:
      return Event::kMonitorDisarmedOnGround;
    case MonitorRow::kModeFailsafe:
      return Event::kMonitorModeFailsafe;
    case MonitorRow::kModeExternal:
      return Event::kMonitorModeExternal;
    case MonitorRow::kModeDefensive:
      return Event::kMonitorModeDefensive;
  }
  return Event::kMonitorTimestampFailure;
}

bool in_flow_stage(Stage stage) { return stage == Stage::kPreparing || stage == Stage::kItem; }

}  // namespace

MissionRunner::MissionRunner(
  MissionSpec mission, Config config, std::int64_t accept_ns, TransitionObserver * observer)
: accept_ns_(accept_ns), observer_(observer), mission_(std::move(mission)), config_(config)
{
  MissionCheck check = validate_mission_runnable(mission_);
  mission_valid_ = check.valid;
  invalid_detail_ = std::move(check.detail);
  if (mission_valid_) {
    // validate_mission_runnable이 첫 항목을 진입 방식이 있는 type으로 둔다.
    const std::optional<EntryPlan> plan = entry_plan(mission_.items.front().type);
    mission_valid_ = plan.has_value();
    entry_plan_ = plan.value_or(EntryPlan::kGroundArm);
  }
}

RunnerView MissionRunner::view() const
{
  RunnerView v;
  v.stage = stage_;
  v.prep = prep_;
  v.item_index = item_index_;
  v.items_completed = items_completed_;
  v.publishing = publishing_;
  v.setpoint = setpoint_;
  v.arm_sent = arm_sent_;
  v.pending_active = pending_.active;
  v.pending = pending_.kind;
  v.cleanup_cause = cause_;
  v.branch = branch_;
  v.disarm_class = disarm_class_;
  v.land_confirmed = mode_item_.confirmed;
  v.failsafe_history = failsafe_history_;
  v.armed_seen = armed_seen_;
  v.landed_false_seen = landed_false_seen_;
  v.hold_failed = hold_failed_;
  return v;
}

StepOutput MissionRunner::step(
  const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock)
{
  StepOutput out;
  if (stage_ == Stage::kDone) {
    return out;
  }
  Tick t(input, snapshot, clock, out);
  t.checkpoint = state_key();
  step_tick(t);
  flush_records(t);
  return out;
}

void MissionRunner::step_tick(Tick & t)
{
  if (!mission_valid_) {
    terminate(
      Event::kInvalidMission, t,
      aborted(
        Reason::kInternal, "mission did not pass validate_mission_runnable: " + invalid_detail_));
    if (t.input.cancel_requested) {
      note_ignored_cancel(t);
    }
    return;
  }
  const bool in_flow_at_start = in_flow_stage(stage_);
  switch (stage_) {
    case Stage::kPreparing:
      step_preparing(t);
      break;
    case Stage::kItem:
      step_item(t);
      break;
    case Stage::kCleanup:
      step_cleanup(t);
      break;
    case Stage::kDone:
      break;
  }
  // 취소는 실패와 완료 뒤에 본다. 정리 중(취소, ITEM_TIMEOUT, PREPARING 실패, RTL 실패)이면
  // 무시한다.
  if (t.input.cancel_requested && (stage_ == Stage::kPreparing || stage_ == Stage::kItem)) {
    begin_cleanup(Event::kCancel, t, CleanupCause::kCancel, Reason::kNone, "");
  } else if (t.input.cancel_requested && in_flow_at_start) {
    note_ignored_cancel(t);
  }
  finalize(t);
}

StepOutput MissionRunner::run_test_steps(
  const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock,
  const std::vector<TestStep> & steps)
{
  StepOutput out;
  Tick t(input, snapshot, clock, out);
  t.checkpoint = state_key();
  for (const TestStep & step : steps) {
    if (step.is_tag) {
      tag(step.event, t);
    } else {
      set_state(t, step.key);
    }
  }
  flush_records(t);
  return out;
}

StepOutput MissionRunner::begin_cancel_without_stage(
  const TickInput & input, const Snapshot & snapshot, Px4ClockPort & clock)
{
  StepOutput out;
  if (stage_ == Stage::kDone) {
    return out;
  }
  Tick t(input, snapshot, clock, out);
  t.checkpoint = state_key();
  begin_cleanup(Event::kCancel, t, CleanupCause::kCancel, Reason::kNone, "");
  finalize(t);
  flush_records(t);
  return out;
}

// ---- PREPARING ----

void MissionRunner::step_preparing(Tick & t)
{
  if (
    prep_ != PrepStep::kWaitReady && !armed_seen_ && t.status != nullptr &&
    t.status->identity == IdentityCheck::kMismatch) {
    // 발행을 시작한 뒤, 첫 ARMED 표본 전의 식별 불일치(decisions.md 쟁점 3 M2). 입력을 믿을 수
    // 없으므로 정리 분기를 고르지 않는다. arm을 보냈으면 강제가 아닌 disarm을 한 번 보낸다.
    // vehicle_command는 target_system으로 주소가 정해져 status의 식별과 무관하고, 강제가 아닌
    // disarm은 공중에서 거부되므로 공중 기체를 끄지 않는다. 이륙 이력이 없으면 자동 disarm이 없다.
    // reason은 INTERNAL이다. NOT_READY는 기체에 아무것도 보내지 않은 goal에만 쓴다(P0-P2).
    // 첫 ARMED 표본 뒤는 감시 표 순위 2다(prepare_arm).
    std::string detail =
      "vehicle_status identity mismatch during preparing: " + t.status->identity_detail;
    if (arm_sent_) {
      send_final(t, CommandKind::kDisarm, detail);
    }
    terminate(Event::kPreparingIdentityMismatch, t, aborted(Reason::kInternal, detail));
    return;
  }
  switch (prep_) {
    case PrepStep::kWaitReady:
      prepare_wait_ready(t);
      break;
    case PrepStep::kSignal:
      prepare_signal(t);
      break;
    case PrepStep::kOffboard:
      prepare_offboard(t);
      break;
    case PrepStep::kOffboardAck:
      prepare_offboard_ack(t);
      break;
    case PrepStep::kArm:
      prepare_arm(t);
      break;
  }
}

void MissionRunner::prepare_wait_ready(Tick & t)
{
  const ItemSpec & first = mission_.items.front();
  const bool takeoff_first = entry_plan_ == EntryPlan::kGroundArm;
  const StatusSample * const s = t.status;
  // P0: 식별 불일치가 확정되면 그 tick에 NOT_READY.
  if (s != nullptr && s->identity == IdentityCheck::kMismatch) {
    terminate(
      Event::kReadyIdentityMismatch, t,
      aborted(Reason::kNotReady, "vehicle_status identity mismatch: " + s->identity_detail));
    return;
  }
  std::string waiting;
  if (s == nullptr) {
    waiting = "vehicle_status";
  } else if (link_lost(t)) {
    waiting = "fresh vehicle_status";
  } else if (t.land == nullptr) {
    waiting = "vehicle_land_detected";
  } else if (t.position == nullptr) {
    waiting = "vehicle_local_position";
  } else if (t.flags == nullptr) {
    waiting = "failsafe_flags";
  }
  if (waiting.empty() && s != nullptr && t.land != nullptr && t.flags != nullptr) {
    // P1: 시작 조건. P0을 통과한 tick마다 다시 본다.
    const bool landed = t.land->landed;
    const bool armed = s->arming == Arming::kArmed;
    const bool start_ok = takeoff_first ? (landed && !armed) : (!landed && armed);
    if (!start_ok) {
      const std::string need =
        std::string(item_type_name(first.type)) +
        (takeoff_first ? " needs landed and DISARMED" : " needs not landed and ARMED");
      terminate(
        Event::kPreconditionFailed, t,
        aborted(
          Reason::kPreconditionFailed, need + " (landed=" + (landed ? "true" : "false") +
                                         ", arming=" + arming_name(s->arming) + ")"));
      return;
    }
    // P2: EKF gate. TAKEOFF는 P3이 목표점을 만들 위치 값도 유한해야 한다.
    const bool position_ok = t.position != nullptr && position_finite(*t.position);
    const bool heading_ok = t.position != nullptr && std::isfinite(t.position->heading);
    const bool needs_heading = first.takeoff.yaw.mode == yaw_mode::kKeep;
    if (!t.flags->ekf_ready) {
      waiting = "EKF gate (failsafe_flags position/altitude/home)";
    } else if (takeoff_first && !position_ok) {
      waiting = "finite vehicle_local_position";
    } else if (takeoff_first && needs_heading && !heading_ok) {
      waiting = "finite heading";
    }
  }
  if (elapsed(t, accept_ns_) >= config_.timeouts.ready_timeout_ns) {
    terminate(
      Event::kReadyTimeout, t,
      aborted(
        Reason::kNotReady,
        "ready_timeout: waiting for " + (waiting.empty() ? std::string("nothing") : waiting)));
    return;
  }
  if (!waiting.empty()) {
    return;
  }
  if (takeoff_first) {
    start_signal(Event::kReadyTakeoff, t);
  } else {
    start_item(Event::kReadyModeItem, t, 0);
  }
}

void MissionRunner::start_signal(Event event, Tick & t)
{
  // P3: 목표점은 이 tick의 위치에서 z만 -height_m. yaw는 항상 유한값(MODE_KEEP이면 지금 heading).
  const PositionSample * const p = t.position;
  if (p == nullptr) {
    return;
  }
  const TakeoffSpec & spec = mission_.items.front().takeoff;
  const double yaw =
    spec.yaw.mode == yaw_mode::kFixed ? enu_to_ned_yaw(spec.yaw.yaw_rad) : wrap_pi(p->heading);
  // TAKEOFF와 지상 setpoint는 속도를 싣지 않는다(decisions.md 쟁점 8).
  reference_ = SetpointOut{SetpointKind::kGround, p->x, p->y, p->z, yaw, false, Vec3{}};
  setpoint_ =
    SetpointOut{SetpointKind::kTarget, p->x, p->y, p->z - spec.height_m, yaw, false, Vec3{}};
  takeoff_target_z_ = setpoint_.z;
  publishing_ = true;
  acted_ = true;
  publish_count_ = 0;
  signal_start_ns_ = t.input.now_ns;
  signal_start_tick_ = t.input.tick;
  enter_prep(event, t, PrepStep::kSignal);
}

void MissionRunner::enter_prep(Event event, Tick & t, PrepStep prep)
{
  tag(event, t);
  StateKey next = state_key();
  next.prep = prep;
  set_state(t, next);
}

void MissionRunner::prepare_signal(Tick & t)
{
  // P4: 발행 10회 이상이고 발행 시작 뒤에 받은 failsafe_flags가 신호 있음.
  if (elapsed(t, signal_start_ns_) >= config_.timeouts.offboard_signal_timeout_ns) {
    begin_cleanup(
      Event::kSignalTimeout, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      "offboard_signal_timeout: offboard signal not confirmed (published " +
        std::to_string(publish_count_) + ")");
    return;
  }
  const bool signal_ok = t.flags != nullptr && t.flags->received_tick > signal_start_tick_ &&
                         !t.flags->offboard_signal_lost;
  if (publish_count_ >= kOffboardSignalMinPublishes && signal_ok) {
    enter_prep(Event::kSignalConfirmed, t, PrepStep::kOffboard);
    step_start_ns_ = t.input.now_ns;
    counter_.reset();
    send(t, CommandKind::kSetModeOffboard);
  }
}

void MissionRunner::prepare_offboard(Tick & t)
{
  // P5: DO_SET_MODE(Offboard)를 유효 ack가 없는 동안 재전송하며 OFFBOARD 3회 연속. 확인되면 ack
  // 대기(P5a)로 간다.
  const AckView ack = take_ack(t);
  if (t.status != nullptr) {
    counter_.observe(t.status->timestamp_us, t.status->nav == NavMode::kOffboard);
  }
  if (ack.fresh && is_rejection(ack.result)) {
    begin_cleanup(
      Event::kOffboardRejected, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      std::string("DO_SET_MODE(OFFBOARD) rejected: ") + ack_result_name(ack.result));
    return;
  }
  if (elapsed(t, step_start_ns_) >= config_.timeouts.mode_confirm_timeout_ns) {
    begin_cleanup(
      Event::kOffboardTimeout, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      "mode_confirm_timeout: OFFBOARD not confirmed");
    return;
  }
  if (counter_.count() >= kConfirmSamples && t.status != nullptr) {
    // 확인을 고정하고 ack 대기로 간다(decisions.md 쟁점 12). 대기 명령(DO_SET_MODE)은 남겨 노드가
    // 그 묶음의 ack를 계속 넘기게 한다. 이 tick의 거부 ack와 timeout은 위에서 봤고, 확인 표본이
    // OFFBOARD라 이탈은 없으므로 arm 조건을 이어서 보고, arm하지 않았으면 유효 ack가 없을 때 주기
    // 재전송을 본다.
    offboard_confirm_timestamp_us_ = t.status->timestamp_us;
    enter_prep(Event::kOffboardConfirmed, t, PrepStep::kOffboardAck);
    if (arm_if_offboard_acked(t)) {
      return;
    }
  }
  resend_offboard_until_acked(t);
}

void MissionRunner::prepare_offboard_ack(Tick & t)
{
  // P5a: OFFBOARD 확인 뒤 마지막 DO_SET_MODE 전송 뒤의 ack를 기다린다. 계수는 보지 않고(확인 고정),
  // 유효 ack가 없는 동안 command_resend_period마다 재전송하며 새 timeout은 없다
  // (mode_confirm_timeout은 P5 진입부터). 같은 tick의 순서는 거부 ack -> mode_confirm_timeout ->
  // 이탈 -> arm -> 재전송이고, 식별 불일치는 step_preparing이 먼저 보며 취소는 단계 처리 뒤다.
  // 실패는 모두 arm 전이라 disarm을 보내지 않는다.
  const AckView ack = take_ack(t);
  if (ack.fresh && is_rejection(ack.result)) {
    begin_cleanup(
      Event::kOffboardRejected, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      std::string("DO_SET_MODE(OFFBOARD) rejected after OFFBOARD confirmed: ") +
        ack_result_name(ack.result));
    return;
  }
  if (elapsed(t, step_start_ns_) >= config_.timeouts.mode_confirm_timeout_ns) {
    begin_cleanup(
      Event::kOffboardTimeout, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      "mode_confirm_timeout: OFFBOARD confirmed but no DO_SET_MODE(OFFBOARD) ack after last send");
    return;
  }
  // 이탈: 식별이 맞고 timestamp가 확인 표본보다 큰 OFFBOARD 아닌 표본 하나. arming과 failsafe는
  // 보지 않는다. 확인을 풀어 다시 세지 않고 arm 없이 실패한다(fail-closed).
  const StatusSample * const s = t.status;
  if (
    s != nullptr && s->identity == IdentityCheck::kMatch &&
    s->timestamp_us > offboard_confirm_timestamp_us_ && s->nav != NavMode::kOffboard) {
    begin_cleanup(
      Event::kOffboardLeft, t, CleanupCause::kPreparingFailure, Reason::kModeSwitchFailed,
      "OFFBOARD left before DO_SET_MODE(OFFBOARD) ack: vehicle_status nav_state not OFFBOARD");
    return;
  }
  if (arm_if_offboard_acked(t)) {
    return;
  }
  resend_offboard_until_acked(t);
}

bool MissionRunner::has_valid_offboard_ack() const
{
  // 유효 ack: 대기 명령(DO_SET_MODE) 묶음의 비거부 ack이고 마지막 전송 tick보다 뒤의 tick에 받았다.
  // 같은 tick에 받은 ack는 그 tick의 전송보다 앞이다(snapshot은 tick 시작의 것).
  return pending_.accepted_ack_tick > pending_.last_send_tick;
}

void MissionRunner::resend_offboard_until_acked(Tick & t)
{
  // 지상 arm 진입(P5, P5a) 전용. 유효 ack가 없을 때만 주기 재전송한다(decisions.md 쟁점 12 "명령과
  // ack의 유실"). 유효 ack를 무효로 만드는 것은 그 뒤의 재전송뿐이라 한 번 유효가 된 ack는 arm이나
  // 실패까지 유효하다.
  if (has_valid_offboard_ack()) {
    return;
  }
  resend_due(t);
}

bool MissionRunner::arm_if_offboard_acked(Tick & t)
{
  if (!has_valid_offboard_ack()) {
    return false;
  }
  clear_pending();
  enter_prep(Event::kOffboardAckAccepted, t, PrepStep::kArm);
  step_start_ns_ = t.input.now_ns;
  counter_.reset();
  send(t, CommandKind::kArm);
  arm_sent_ = true;
  arm_first_tick_ = t.input.tick;
  return true;
}

void MissionRunner::prepare_arm(Tick & t)
{
  // P6(decisions.md 쟁점 4 P6 행과 "P6에서 ARMED를 처음 관측한 뒤").
  if (!armed_seen_) {
    // 첫 ARMED 표본: 식별 대조가 맞고 수신 tick이 arm 첫 전송 tick보다 큰 ARMED 표본
    // (nav_state가 OFFBOARD가 아니어도 해당한다). 표본 하나로 정해지는 관측이라 같은 tick의
    // arm_timeout 만료보다 앞이다.
    const StatusSample * const s = t.status;
    const bool first_armed = s != nullptr && s->identity == IdentityCheck::kMatch &&
                             s->arming == Arming::kArmed && s->received_tick > arm_first_tick_;
    if (!first_armed) {
      prepare_arm_before_armed(t);
      return;
    }
    armed_seen_ = true;
    first_armed_ns_ = t.input.now_ns;
    first_armed_tick_ = t.input.tick;
    first_armed_timestamp_us_ = s->timestamp_us;
    history_after_tick_ = t.input.tick - 1;  // 첫 ARMED 표본을 이력에 넣는다
    failsafe_history_ = false;
    landed_false_seen_ = false;
    trusted_status_.reset();
    counter_.reset();
    // arm 재전송을 멈추고 대기 명령을 지운다. 그 뒤의 ARM ack는 보지 않는다(같은 tick에 온 늦은
    // 거부 ack 포함. status를 먼저 보고 대기 명령을 지운 뒤라 take_ack가 받지 않는다).
    clear_pending();
  }
  // 같은 tick의 순서: 감시 표(순위 1-8) -> 확인 기한 -> 확인(3회 연속) -> 취소(step).
  if (monitor_flight(t, "preparing (arm confirm)", {})) {
    return;
  }
  if (trusted_status_.has_value()) {
    // 감시 표를 지난 표본은 ARMED이고 OFFBOARD다(OFFBOARD이고 ARMED인 채 failsafe인 방어용 표본도
    // 같은 조건으로 센다).
    counter_.observe(
      trusted_status_->timestamp_us,
      trusted_status_->arming == Arming::kArmed && trusted_status_->nav == NavMode::kOffboard);
  }
  if (elapsed(t, first_armed_ns_) >= config_.timeouts.mode_confirm_timeout_ns) {
    begin_cleanup(
      Event::kArmConfirmTimeout, t, CleanupCause::kPreparingFailure, Reason::kArmRejected,
      "ARMED observed but ARMED in OFFBOARD not confirmed within mode_confirm_timeout");
    return;
  }
  if (counter_.count() >= kConfirmSamples) {
    start_item(Event::kArmConfirmed, t, 0);
  }
}

void MissionRunner::prepare_arm_before_armed(Tick & t)
{
  // 첫 ARMED 표본 전: arm을 재전송한다. TEMPORARILY_REJECTED는 arm_timeout 안에서 재시도하고, 그
  // 밖의 거부 ack(방어용)와 arm_timeout(arm을 처음 보낸 시각부터)은 ARM_REJECTED다. LINK_LOST
  // 판정은 두지 않는다(그 구간의 기체는 DISARMED다).
  const AckView ack = take_ack(t);
  if (ack.fresh && ack.result != AckResult::kTemporarilyRejected && is_rejection(ack.result)) {
    begin_cleanup(
      Event::kArmRejected, t, CleanupCause::kPreparingFailure, Reason::kArmRejected,
      std::string("ARM rejected: ") + ack_result_name(ack.result));
    return;
  }
  if (elapsed(t, step_start_ns_) >= config_.timeouts.arm_timeout_ns) {
    begin_cleanup(
      Event::kArmTimeout, t, CleanupCause::kPreparingFailure, Reason::kArmRejected,
      "arm_timeout: ARMED not observed");
    return;
  }
  resend_due(t);
}

// ---- 비행 중 감시(P6의 첫 ARMED 표본부터 setpoint 항목이 끝날 때까지) ----

const StatusSample * MissionRunner::monitored_status(const Tick & t)
{
  // 감시 구간에서 판정에 쓰는 vehicle_status. 식별이 어긋난 표본은 그대로 넘긴다(순위 2).
  // timestamp가 첫 ARMED 표본보다 작은 표본은 판정에 쓰지 않고 직전에 쓴 표본을 다시 본다(그래서
  // 순위 3의 link_timeout은 그 표본의 수신 시각부터 흐른다).
  const StatusSample * const s = t.status;
  if (s != nullptr && s->identity == IdentityCheck::kMismatch) {
    return s;
  }
  if (s == nullptr || s->timestamp_us < first_armed_timestamp_us_) {
    return trusted_status_.has_value() ? &*trusted_status_ : nullptr;
  }
  trusted_status_ = *s;
  return &*trusted_status_;
}

bool MissionRunner::monitor_flight(
  Tick & t, const std::string & label, const std::vector<Event> & later)
{
  // 비행 중 감시 표(rules.hpp). 순위 1을 보려고 timestamp를 판정 맨 앞에서 묻는다. 끝냈으면 true.
  MonitorInput monitor;
  monitor.timestamp_ok = query_stamp(t);
  const StatusSample * const s = monitored_status(t);
  monitor.status = s;
  monitor.landed = t.land != nullptr ? t.land->landed : true;
  monitor.link_lost =
    s == nullptr || t.input.now_ns - s->received_ns >= config_.timeouts.link_timeout_ns;
  monitor.failsafe_history = failsafe_history_;
  // 지상 disarm 1회의 조건 2: 첫 ARMED 표본을 본 tick부터(그 tick 포함) 받은 landed가 false인 적이
  // 있는가. goal 동안 유지하고 항목이 바뀌어도 지우지 않는다.
  if (t.land != nullptr && t.land->received_tick >= first_armed_tick_ && !t.land->landed) {
    landed_false_seen_ = true;
  }
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(monitor);
  if (verdict.has_value()) {
    end_by_monitor(t, *verdict, label, later);
    return true;
  }
  // 순위 5의 이력: 이력 구간 안에서 받은 표본의 failsafe만 남긴다. 지금 표본은 판정 뒤에 넣는다.
  if (s != nullptr && s->received_tick > history_after_tick_ && s->failsafe) {
    failsafe_history_ = true;
  }
  return false;
}

void MissionRunner::end_by_monitor(
  Tick & t, const MonitorVerdict & verdict, const std::string & label,
  const std::vector<Event> & later)
{
  // 감시 표의 행으로 끝낸다. 정리 분기에 들어가지 않고 그 tick에 발행을 멈춘다. P6과 setpoint
  // 항목이 같이 쓴다. disarm을 보내는 행이면 확인 없이 한 번만 보낸다(끝나는 tick의 명령은 늘
  // 하나다).
  const Event event = monitor_event(verdict.row);
  if (observer_ != nullptr) {
    std::vector<Event> also_true;
    for (const MonitorRow row : verdict.matched) {
      if (row != verdict.row) {
        also_true.push_back(monitor_event(row));
      }
    }
    also_true.insert(also_true.end(), later.begin(), later.end());
    tag(event, t, also_true);
  }
  t.out.commands.clear();
  clear_pending();
  std::string detail = label + ": " + verdict.detail;
  MonitorDisarmInput disarm;
  disarm.arm_sent = arm_sent_;
  disarm.landed_false_seen = landed_false_seen_;
  disarm.landed_known = t.land != nullptr;
  disarm.landed = t.land != nullptr && t.land->landed;
  if (monitor_sends_disarm(verdict.row, disarm)) {
    send_final(t, CommandKind::kDisarm, detail);
  }
  if (verdict.row == MonitorRow::kTimestampFailure && acted_) {
    detail += "; vehicle state unknown, may remain armed on ground";
  }
  terminate(event, t, aborted(verdict.reason, detail));
}

// ---- 항목 ----

void MissionRunner::start_item(Event event, Tick & t, std::uint32_t index)
{
  tag(event, t);
  StateKey next = state_key();
  next.stage = Stage::kItem;
  next.item_index = index;
  set_state(t, next);
  item_start_ns_ = t.input.now_ns;
  item_start_tick_ = t.input.tick;
  if (index != 0 || !armed_seen_) {
    // P6에서 넘어온 첫 항목(TAKEOFF)은 P6의 ARMED 확인 구간과 한 이력 구간이다.
    failsafe_history_ = false;
    history_after_tick_ = t.input.tick;
  }
  const std::optional<ModeItemSpec> spec = mode_item_spec(current_item().type);
  if (spec.has_value()) {
    mode_item_ = ModeItemState{};
    mode_item_.first_send_ns = t.input.now_ns;
    send(t, spec->command);
  }
}

void MissionRunner::complete_item(Event event, Tick & t)
{
  ++items_completed_;
  const std::uint32_t next = item_index_ + 1;
  if (next >= mission_.items.size()) {
    // validate_mission_runnable이 마지막을 LAND나 RTL로 두므로 setpoint 항목에서는 닿지 않는다.
    terminate(event, t, succeeded());
    return;
  }
  start_item(event, t, next);
}

void MissionRunner::step_item(Tick & t)
{
  const std::optional<ModeItemSpec> spec = mode_item_spec(current_item().type);
  if (spec.has_value()) {
    step_mode_item(t, *spec);
  } else {
    step_setpoint_item(t);
  }
}

void MissionRunner::step_setpoint_item(Tick & t)
{
  // 감시 표를 먼저 본다(같은 tick이면 감시 표의 행이 ITEM_TIMEOUT과 완료를 이긴다). 그 뒤는
  // ITEM_TIMEOUT -> 완료다. 셋의 조건은 상태를 바꾸지 않는 식이라 먼저 계산해 겹침 칸에 싣는다.
  const ItemSpec & item = current_item();
  const bool timed_out = elapsed(t, item_start_ns_) >= item.timeout.to_ns();
  bool completed = false;
  Event completion = Event::kLoiterElapsed;
  if (item.type == item_type::kTakeoff) {
    // validate_mission_runnable이 부르는 계약 순서 규칙이 TAKEOFF를 첫 항목에만 두므로
    // takeoff_target_z_는 이 항목의 목표다.
    const PositionSample * const p = t.position;
    completed = p != nullptr && p->z_valid && std::isfinite(p->z) &&
                std::abs(p->z - takeoff_target_z_) < item.takeoff.acceptance_m;
    completion = Event::kTakeoffReached;
  } else if (item.type == item_type::kLoiter) {
    completed = elapsed(t, item_start_ns_) >= item.loiter.duration.to_ns();
  }
  std::vector<Event> later;
  if (observer_ != nullptr) {
    if (timed_out) {
      later.push_back(Event::kItemTimeout);
    }
    if (completed) {
      later.push_back(completion);
    }
  }
  if (monitor_flight(t, item_label(), later)) {
    return;
  }
  if (timed_out) {
    if (completed) {
      tag(Event::kItemTimeout, t, {completion});
    }
    begin_cleanup(
      Event::kItemTimeout, t, CleanupCause::kItemTimeout, Reason::kItemTimeout,
      item_label() + " timeout");
    return;
  }
  if (completed) {
    complete_item(completion, t);
  }
}

void MissionRunner::step_mode_item(Tick & t, const ModeItemSpec & spec)
{
  // 모드 명령 항목(LAND, RTL)의 한 tick. 판정 순서는 LAND 1a 그대로이고, RTL은 확인 전 거부 ack와
  // mode_confirm_timeout에서 Land fallback(RTL 실패의 정리)으로 간다(1b decisions.md 쟁점 9).
  apply_publish_rule(t);
  const StatusSample * const s = t.status;
  if (s != nullptr && s->identity == IdentityCheck::kMismatch) {
    terminate(
      Event::kModeItemIdentityMismatch, t,
      aborted(
        Reason::kInternal,
        item_label() + ": vehicle_status identity mismatch: " + s->identity_detail));
    return;
  }
  if (s == nullptr || link_lost(t)) {
    terminate(
      Event::kModeItemLinkLost, t,
      aborted(Reason::kLinkLost, item_label() + ": vehicle_status lost"));
    return;
  }
  const bool landed = t.land != nullptr && t.land->landed;
  if (!mode_item_.has_last || s->timestamp_us > mode_item_.last_timestamp_us) {
    mode_item_.has_last = true;
    mode_item_.last_timestamp_us = s->timestamp_us;
    if (s->nav == spec.mode) {
      mode_item_.mode_seen = true;
    }
    if (s->arming == Arming::kDisarmed) {
      // 어느 구간에서든 DISARMED이고 landed이면 nav_state가 무엇이든 완료 계수가 우선한다.
      // landed는 처음 관측한 DISARMED 표본의 tick에 고정한다.
      if (disarm_class_ == DisarmClass::kUnknown) {
        disarm_class_ = landed ? DisarmClass::kGround : DisarmClass::kAir;
      }
      if (disarm_class_ == DisarmClass::kAir) {
        terminate(
          Event::kModeItemDisarmedInAir, t,
          aborted(Reason::kFailsafe, item_label() + ": disarmed while not landed"));
        return;
      }
      ++mode_item_.disarm_count;
    } else {
      disarm_class_ = DisarmClass::kUnknown;
      mode_item_.disarm_count = 0;
      if (!mode_item_.confirmed) {
        // 확인 전: 이탈 판정을 하지 않는다. 확인 대상 모드는 failsafe와 무관하게 센다.
        mode_item_.mode_count = s->nav == spec.mode ? mode_item_.mode_count + 1 : 0;
        if (mode_item_.mode_count >= kConfirmSamples) {
          mode_item_.confirmed = true;
          clear_pending();
        }
      } else if (s->nav != spec.mode) {
        // 확인 뒤: ARMED인 동안 확인 대상 모드를 벗어나면 이탈.
        terminate(
          Event::kModeItemLeftMode, t,
          aborted(
            s->failsafe ? Reason::kFailsafe : Reason::kExternalModeChange,
            item_label() + ": left " + spec.mode_name + " while ARMED"));
        return;
      }
    }
  }
  const AckView ack = take_ack(t);
  const bool command_ack = ack.fresh && pending_.active && pending_.kind == spec.command;
  if (command_ack && ack.result == AckResult::kAccepted) {
    mode_item_.command_accepted = true;
  }
  if (spec.land_fallback && command_ack && is_rejection(ack.result)) {
    // 확인 전에만 닿는다(확인하면 대기 명령을 지운다. 확인 뒤의 대기 명령은 대비책 disarm이다).
    begin_cleanup(
      Event::kModeItemRejected, t, CleanupCause::kRtlFailure, Reason::kModeSwitchFailed,
      item_label() + ": " + spec.command_name + " rejected: " + ack_result_name(ack.result));
    return;
  }
  if (
    !mode_item_.confirmed &&
    elapsed(t, mode_item_.first_send_ns) >= config_.timeouts.mode_confirm_timeout_ns) {
    const std::string detail =
      item_label() + ": mode_confirm_timeout: " + spec.mode_name + " not confirmed";
    if (spec.land_fallback) {
      begin_cleanup(
        Event::kModeItemModeTimeout, t, CleanupCause::kRtlFailure, Reason::kModeSwitchFailed,
        detail);
      return;
    }
    terminate(Event::kModeItemModeTimeout, t, aborted(Reason::kModeSwitchFailed, detail));
    return;
  }
  if (elapsed(t, item_start_ns_) >= current_item().timeout.to_ns()) {
    mode_item_timeout(t, spec, landed);
    return;
  }
  if (mode_item_.disarm_count >= kConfirmSamples) {
    terminate(Event::kModeItemDisarmConfirmed, t, succeeded());
    return;
  }
  // 대비책: landed이고 ARMED인 채 land_disarm_fallback_delay가 지나면 강제가 아닌 disarm.
  // 확인 대상 모드를 확인한 뒤에만 보낸다(대기 중인 명령은 한 번에 하나다).
  // 이어짐은 매 tick 그 tick의 표본으로 갱신한다(같은 표본을 다시 본 tick도).
  mode_item_.fallback.observe(s->arming == Arming::kArmed && landed, t.input.now_ns);
  if (
    mode_item_.confirmed &&
    mode_item_.fallback.due(t.input.now_ns, config_.timeouts.land_disarm_fallback_delay_ns)) {
    mode_item_.fallback.mark_sent();
    send(t, CommandKind::kDisarm);
    return;
  }
  resend_due(t);
}

void MissionRunner::mode_item_timeout(Tick & t, const ModeItemSpec & spec, bool landed)
{
  // 그 항목의 명령과 대비책 disarm의 재전송을 멈추고, 아직 발행 중이면 발행을 멈춘다. Hold는
  // 보내지 않고 Land fallback도 거치지 않는다. 뒤는 PX4가 내린다(offboard 손실 Land, 또는 이미
  // 확인 대상 모드).
  const std::string mode = spec.mode_name;
  const std::string command = spec.command_name;
  std::string detail = item_label() + " timeout";
  if (mode_item_.confirmed) {
    detail += "; " + mode + " was confirmed, PX4 continues " +
              (spec.mode == NavMode::kLand ? "landing" : "RTL");
  } else if (mode_item_.mode_seen) {
    detail += "; " + mode + " observed but not confirmed";
  } else if (mode_item_.command_accepted) {
    detail += "; " + command + " accepted but " + mode + " not observed";
  } else {
    detail += "; " + mode + " not observed (" + command +
              " may not have arrived, vehicle may stay in its mode)";
  }
  if (t.status != nullptr && t.status->arming == Arming::kArmed && landed) {
    detail += "; landed and still ARMED";
  }
  terminate(Event::kModeItemTimeout, t, aborted(Reason::kItemTimeout, detail));
}

// ---- 정리(취소, ITEM_TIMEOUT, PREPARING 실패, RTL 실패) ----

void MissionRunner::begin_cleanup(
  Event event, Tick & t, CleanupCause cause, Reason reason, std::string detail)
{
  tag(event, t);
  // 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 지운다(arm 재전송은 이 tick에 멈춘다).
  t.out.commands.clear();
  clear_pending();
  cleanup_phase_ = cause == CleanupCause::kCancel ? FeedbackPhase::kCanceling : current_phase();
  StateKey next = state_key();
  next.stage = Stage::kCleanup;
  next.cause = cause;
  next.branch = Branch::kNone;
  set_state(t, next);
  cleanup_reason_ = reason;
  cleanup_detail_ = std::move(detail);
  cleanup_start_ns_ = t.input.now_ns;
  hold_failed_ = false;
  hold_observed_ = false;
  step_cleanup(t);
}

void MissionRunner::step_cleanup(Tick & t)
{
  // 한 tick의 순서(decisions.md 쟁점 3 M6): (1) 상태 끊김 (2) 공중 DISARMED (3) 정리할 것 없음
  // (4) 정리의 상한 (5) 그 분기의 실행(분기 타임아웃, 확인). (1)-(3)은 표본 하나로 정해지는
  // 관측이라 상한보다 앞이고, (4)가 (5)보다 앞이라 상한 tick의 확인 표본은 세지 않는다.
  const StatusSample * const s = t.status;
  if (s == nullptr || t.land == nullptr || (!acted_ && link_lost(t))) {
    // 아무것도 하지 않았고 판단할 표본도 없다.
    publishing_ = false;
    clear_pending();
    finish(Event::kCleanupNoSample, t, Outcome::kSuccess, "nothing to clean up");
    return;
  }
  if (s->identity == IdentityCheck::kMismatch) {
    cleanup_with_untrusted_sample(t);
    return;
  }
  apply_publish_rule(t);
  if (s->arming == Arming::kDisarmed) {
    if (disarm_class_ == DisarmClass::kUnknown) {
      disarm_class_ = t.land->landed ? DisarmClass::kGround : DisarmClass::kAir;
    }
  } else {
    disarm_class_ = DisarmClass::kUnknown;
  }
  if (s->nav == NavMode::kHold) {
    hold_observed_ = true;
  }
  CleanupInput input;
  input.arming = s->arming;
  input.landed = t.land->landed;
  input.disarm_class = disarm_class_;
  input.arm_sent = arm_sent_;
  input.in_ground_branch = branch_ == Branch::kGround;
  const CleanupChoice choice = select_cleanup(input);

  if (link_lost(t)) {
    // (1) 상태 끊김. 발행을 멈추고, 지상 disarm 분기였으면 disarm을 한 번 더 보낸 뒤 끝낸다.
    publishing_ = false;
    clear_pending();
    if (choice == CleanupChoice::kGround) {
      std::string what = "vehicle_status lost during ground disarm; disarm not confirmed";
      send_final(t, CommandKind::kDisarm, what);
      finish(Event::kCleanupLinkLost, t, Outcome::kLinkLost, what);
    } else {
      finish(Event::kCleanupLinkLost, t, Outcome::kLinkLost, "vehicle_status lost");
    }
    return;
  }
  if (choice == CleanupChoice::kAirDisarm) {
    // (2)
    publishing_ = false;
    clear_pending();
    finish(Event::kCleanupAirDisarm, t, Outcome::kAirDisarm, "disarmed while not landed");
    return;
  }
  if (choice == CleanupChoice::kEnd) {
    // (3)
    publishing_ = false;
    clear_pending();
    finish(
      Event::kCleanupNothingToDo, t, Outcome::kSuccess, "on ground and DISARMED, arm never sent");
    return;
  }
  if (cleanup_cap_reached(t)) {
    // (4)
    end_at_cleanup_cap(t, choice == CleanupChoice::kGround);
    return;
  }
  // (5)
  if (choice == CleanupChoice::kGround) {
    if (branch_ != Branch::kGround) {
      enter_ground(Event::kEnterGround, t);
      return;
    }
    run_ground(t);
    return;
  }
  if (branch_ != Branch::kAir && branch_ != Branch::kAirLand) {
    enter_air(Event::kEnterAir, t);
    return;
  }
  if (branch_ == Branch::kAir) {
    run_air(t);
  } else {
    run_air_land(t);
  }
}

bool MissionRunner::cleanup_cap_reached(const Tick & t) const
{
  return elapsed(t, cleanup_start_ns_) >= cleanup_cap_ns(config_.timeouts);
}

void MissionRunner::end_at_cleanup_cap(Tick & t, bool on_ground)
{
  // 정리의 상한 tick(M6): 발행을 멈추고 대기 중인 명령을 지운 뒤 명령 하나를 보내고 끝낸다.
  // 지상이면 강제가 아닌 disarm, 공중이면 NAV_LAND. NAV_LAND의 force는 모드 가용성 검사를
  // 우회하지만 TEMPORARILY_REJECTED 경로가 남아 있고 그 조건은 미확인이다. LAND 항목과 Land 경로의
  // NAV_LAND는 거부 ack로 끝내지 않고 mode_confirm_timeout으로 끝낸다. 상한 tick의 NAV_LAND는
  // ack를 기다리지 않고 이 tick에 끝내므로 거부되거나 유실되면 기체는 그 전 모드로 남는다.
  // Px4Timestamp 공급이 실패하면 명령을 버리고 결과는 유지한다(send_final).
  const char * last_branch = "none";
  switch (branch_) {
    case Branch::kNone:
      break;
    case Branch::kAir:
      last_branch = "air (Hold)";
      break;
    case Branch::kAirLand:
      last_branch = "air (Land path)";
      break;
    case Branch::kGround:
      last_branch = "ground (disarm)";
      break;
  }
  publishing_ = false;
  clear_pending();
  t.out.commands.clear();
  tag(Event::kCleanupCap, t);
  std::string what = "cleanup cap reached (" +
                     std::to_string(cleanup_cap_ns(config_.timeouts) / 1000000) +
                     " ms), last branch " + last_branch;
  if (on_ground) {
    send_final(t, CommandKind::kDisarm, what);
    finish(Event::kCleanupCap, t, Outcome::kCapGround, what);
    return;
  }
  const bool sent = send_final(t, CommandKind::kNavLand, what);
  if (hold_observed_) {
    // 발행한 적이 있으면 Hold를 처음 관측한 tick에 발행을 멈췄다(발행 규칙). NAV_LAND를 보내지
    // 못했으면 Hold로 남는다.
    what +=
      publish_count_ > 0 ? "; Hold was observed and publishing stopped" : "; Hold was observed";
    what += sent ? ", vehicle stays in Hold if NAV_LAND is lost" : ", vehicle stays in Hold";
  }
  finish(Event::kCleanupCap, t, Outcome::kCapAir, what);
}

void MissionRunner::cleanup_with_untrusted_sample(Tick & t)
{
  // 정리 중의 식별 불일치(decisions.md 쟁점 3 M2). 이 표본은 발행 규칙, 분기 고르기, 확인 계수에
  // 쓰지 않는다. 남의 기체의 DISARMED나 Hold로 정리를 끝내지 않기 위해서다. 이미 정해진 분기는
  // 유지하고 그 분기의 타임아웃이나 정리의 상한이 끝낸다. 분기가 정해지기 전(정리의 첫 tick)이면
  // 고를 수 없으므로 끝낸다.
  const std::string what = "vehicle_status identity mismatch during cleanup: " +
                           (t.status != nullptr ? t.status->identity_detail : std::string());
  if (branch_ == Branch::kNone) {
    publishing_ = false;
    clear_pending();
    std::string detail = what;
    if (arm_sent_) {
      send_final(t, CommandKind::kDisarm, detail);
    }
    terminate(
      Event::kCleanupIdentityMismatch, t,
      cause_ == CleanupCause::kCancel
        ? aborted(Reason::kInternal, "cancel: " + detail)
        : aborted(cleanup_reason_, cleanup_detail_ + "; cleanup: " + detail));
    return;
  }
  if (cleanup_cap_reached(t)) {
    // 상한 tick의 표본이 식별 불일치이면 다시 고르지 않고 직전까지의 분기로 정한다.
    end_at_cleanup_cap(t, branch_ == Branch::kGround);
    return;
  }
  t.status = nullptr;
  switch (branch_) {
    case Branch::kGround:
      run_ground(t);
      return;
    case Branch::kAir:
      run_air(t);
      return;
    case Branch::kAirLand:
      run_air_land(t);
      return;
    case Branch::kNone:
      return;
  }
}

void MissionRunner::enter_ground(Event event, Tick & t)
{
  // 재실측 (2), (3)이 바꿀 수 있는 곳(README.md). 지상 arm 분기에 들어간 tick에 발행 중이면
  // setpoint를 지상 setpoint로 바꾼다. 이미 멈춘 발행은 다시 켜지 않고 disarm만 보낸다.
  tag(event, t);
  StateKey next = state_key();
  next.branch = Branch::kGround;
  set_state(t, next);
  if (publishing_) {
    setpoint_ = ground_setpoint(t);
  }
  clear_pending();
  send(t, CommandKind::kDisarm);
  disarm_confirm_.begin(t.input.tick);
  branch_first_ns_ = t.input.now_ns;
}

void MissionRunner::run_ground(Tick & t)
{
  take_ack(t);
  if (t.status != nullptr) {
    disarm_confirm_.observe(*t.status);
  }
  if (elapsed(t, branch_first_ns_) >= config_.timeouts.mode_confirm_timeout_ns) {
    const std::string last_ack = pending_.has_ack ? ack_result_name(pending_.last_ack) : "none";
    publishing_ = false;
    clear_pending();
    std::string what =
      "disarm not confirmed within mode_confirm_timeout (last DISARM ack: " + last_ack + ")";
    send_final(t, CommandKind::kDisarm, what);
    finish(Event::kGroundDisarmTimeout, t, Outcome::kDisarmFailed, what);
    return;
  }
  if (disarm_confirm_.count() >= kConfirmSamples) {
    publishing_ = false;
    clear_pending();
    finish(Event::kGroundDisarmConfirmed, t, Outcome::kSuccess, "disarm confirmed");
    return;
  }
  resend_due(t);
}

void MissionRunner::enter_air(Event event, Tick & t)
{
  // 재실측 (2)가 바꿀 수 있는 곳(README.md). 지금 발행 중인 setpoint(지상 분기에서 넘어왔으면 지상
  // setpoint)를 TAKEOFF 목표점으로 되돌리지 않고 유지한 채 Hold를 보낸다.
  if (cause_ == CleanupCause::kRtlFailure) {
    // RTL 실패의 정리는 Hold를 거치지 않고 Land 경로다(1b decisions.md 쟁점 9). Hold 실패 표시보다
    // 먼저 본다. 기준 시각은 들어간 시각이다.
    enter_air_land(
      event, t,
      branch_ == Branch::kGround ? "RTL not confirmed; air re-entered after ground branch"
                                 : "RTL not confirmed");
    return;
  }
  if (hold_failed_) {
    // 이 정리에서 Hold가 한 번 실패했으면 공중 재진입은 Land 경로다(decisions.md 쟁점 3 M4). 기준
    // 시각은 다시 들어간 시각이다.
    enter_air_land(event, t, hold_failed_why_ + "; air re-entered after Hold failure");
    return;
  }
  tag(event, t);
  StateKey next = state_key();
  next.branch = Branch::kAir;
  set_state(t, next);
  clear_pending();
  counter_.reset();
  send(t, CommandKind::kSetModeHold);
  branch_first_ns_ = t.input.now_ns;
}

void MissionRunner::run_air(Tick & t)
{
  const AckView ack = take_ack(t);
  if (t.status != nullptr) {
    counter_.observe(
      t.status->timestamp_us,
      t.status->arming == Arming::kArmed && t.status->nav == NavMode::kHold);
  }
  if (ack.fresh && is_rejection(ack.result)) {
    enter_air_land(
      Event::kHoldRejected, t, std::string("Hold rejected: ") + ack_result_name(ack.result));
    return;
  }
  if (elapsed(t, branch_first_ns_) >= config_.timeouts.hold_confirm_timeout_ns) {
    enter_air_land(Event::kHoldTimeout, t, "Hold not confirmed within hold_confirm_timeout");
    return;
  }
  if (counter_.count() >= kConfirmSamples) {
    publishing_ = false;
    clear_pending();
    finish(Event::kHoldConfirmed, t, Outcome::kSuccess, "Hold confirmed");
    return;
  }
  resend_due(t);
}

void MissionRunner::enter_air_land(Event event, Tick & t, const std::string & why)
{
  tag(event, t);
  StateKey next = state_key();
  next.branch = Branch::kAirLand;
  set_state(t, next);
  if (cause_ != CleanupCause::kRtlFailure) {
    // Hold 분기에서 온 Land 경로다. RTL 실패의 정리는 Hold를 보낸 적이 없으므로 Hold 실패 표시를
    // 세우지 않는다(공중 재진입이 Land 경로인 것은 원인으로 정해진다).
    if (!hold_failed_) {
      hold_failed_why_ = why;  // 재진입 문구가 쌓이지 않게 처음 실패한 이유만 남긴다
    }
    hold_failed_ = true;
  }
  land_path_why_ = why;
  clear_pending();
  send(t, CommandKind::kNavLand);
  branch_first_ns_ = t.input.now_ns;
}

void MissionRunner::run_air_land(Tick & t)
{
  take_ack(t);
  if (t.status != nullptr && t.status->nav == NavMode::kLand) {
    publishing_ = false;
    clear_pending();
    finish(
      Event::kLandPathModeObserved, t, Outcome::kHoldFailed,
      land_path_why_ + "; Land sent, AUTO_LAND observed");
    return;
  }
  if (elapsed(t, branch_first_ns_) >= config_.timeouts.mode_confirm_timeout_ns) {
    publishing_ = false;
    clear_pending();
    finish(
      Event::kLandPathTimeout, t, Outcome::kHoldFailed,
      land_path_why_ + "; Land sent, AUTO_LAND not confirmed");
    return;
  }
  resend_due(t);
}

void MissionRunner::finish(Event event, Tick & t, Outcome outcome, const std::string & what)
{
  if (cause_ != CleanupCause::kCancel) {
    // ITEM_TIMEOUT, PREPARING 실패, RTL 실패: reason은 원래 것을 유지하고 정리 결과는 detail에만
    // 적는다.
    terminate(event, t, aborted(cleanup_reason_, cleanup_detail_ + "; cleanup: " + what));
    return;
  }
  switch (outcome) {
    case Outcome::kSuccess:
      terminate(event, t, canceled(what));
      return;
    case Outcome::kHoldFailed:
      terminate(event, t, aborted(Reason::kModeSwitchFailed, "cancel: " + what));
      return;
    case Outcome::kDisarmFailed:
      terminate(event, t, aborted(Reason::kDisarmFailed, "cancel: " + what));
      return;
    case Outcome::kLinkLost:
      terminate(event, t, aborted(Reason::kLinkLost, "cancel: " + what));
      return;
    case Outcome::kAirDisarm:
      terminate(event, t, aborted(Reason::kFailsafe, "cancel: " + what));
      return;
    case Outcome::kCapGround:
      terminate(event, t, aborted(Reason::kDisarmFailed, "cancel: " + what));
      return;
    case Outcome::kCapAir:
      terminate(event, t, aborted(Reason::kModeSwitchFailed, "cancel: " + what));
      return;
  }
}

// ---- 출력 ----

void MissionRunner::finalize(Tick & t)
{
  if (stage_ == Stage::kDone) {
    // 끝나는 tick에 남은 명령(끝내기 전에 한 번 더 보내는 disarm)만 내보낸다.
    if (!t.out.commands.empty()) {
      if (query_stamp(t)) {
        t.out.px4_timestamp_us = t.stamp_us;
      } else {
        t.out.commands.clear();
      }
    }
    return;
  }
  if (publishing_ || !t.out.commands.empty()) {
    if (!query_stamp(t)) {
      t.out.commands.clear();
      const bool keep_reason = stage_ == Stage::kCleanup && cause_ != CleanupCause::kCancel;
      // 명령을 만들 수 없으므로 기체 상태를 모른다(decisions.md 쟁점 4 "Px4Timestamp 공급이 실패한
      // tick").
      const std::string what =
        std::string("Px4Timestamp unavailable") +
        (acted_ ? "; vehicle state unknown, may remain armed on ground" : "");
      terminate(
        Event::kStampUnavailable, t,
        keep_reason ? aborted(cleanup_reason_, cleanup_detail_ + "; " + what)
                    : aborted(Reason::kInternal, what));
      return;
    }
    t.out.px4_timestamp_us = t.stamp_us;
    if (
      stage_ == Stage::kCleanup && branch_ == Branch::kGround &&
      disarm_confirm_.first_send_tick() == t.input.tick && !disarm_confirm_.stamp_known()) {
      disarm_confirm_.set_first_stamp(t.stamp_us);
    }
    if (publishing_) {
      t.out.setpoint = setpoint_;
      ++publish_count_;
    }
  }
  t.out.feedback = make_feedback(t);
}

Feedback MissionRunner::make_feedback(const Tick & t) const
{
  Feedback f;
  f.stamp_ns = t.input.now_ns;
  f.item_count = static_cast<std::uint32_t>(mission_.items.size());
  f.item_index = item_index_;
  f.item_type = current_item().type;
  f.phase = stage_ == Stage::kCleanup ? cleanup_phase_ : current_phase();
  if (stage_ == Stage::kItem && current_item().type == item_type::kTakeoff) {
    const PositionSample * const p = t.position;
    if (p != nullptr && p->z_valid && std::isfinite(p->z)) {
      f.distance_valid = true;
      f.distance_remaining_m = std::abs(p->z - takeoff_target_z_);
    }
  }
  return f;
}

FeedbackPhase MissionRunner::current_phase() const
{
  if (stage_ == Stage::kPreparing) {
    return FeedbackPhase::kPreparing;
  }
  return mode_item_spec(current_item().type).has_value() ? FeedbackPhase::kWaitingMode
                                                         : FeedbackPhase::kExecuting;
}

// ---- 도구 ----

void MissionRunner::apply_publish_rule(const Tick & t)
{
  // 발행 규칙: Offboard로 들어가는 중(P3-P6)이 아니면 nav_state가 OFFBOARD일 때만 발행한다.
  // OFFBOARD가 아닌 표본을 보면 멈추고 다시 켜지 않는다(Hold, AUTO_LAND의 처음 관측 포함).
  if (publishing_ && t.status != nullptr && t.status->nav != NavMode::kOffboard) {
    publishing_ = false;
  }
}

SetpointOut MissionRunner::ground_setpoint(const Tick & t) const
{
  // 그 tick의 위치에서 z 그대로(어댑터가 지상 오프셋을 더한다), yaw는 그 tick의 heading.
  // 위치가 유한하지 않으면 P3에서 읽은 위치를 쓴다.
  SetpointOut ground = reference_;
  ground.kind = SetpointKind::kGround;
  ground.yaw_ned = setpoint_.yaw_ned;
  const PositionSample * const p = t.position;
  if (p != nullptr && position_finite(*p)) {
    ground.x = p->x;
    ground.y = p->y;
    ground.z = p->z;
    if (std::isfinite(p->heading)) {
      ground.yaw_ned = wrap_pi(p->heading);
    }
  }
  return ground;
}

void MissionRunner::send(Tick & t, CommandKind kind)
{
  pending_ = Pending{};
  pending_.active = true;
  pending_.kind = kind;
  pending_.first_tick = t.input.tick;
  pending_.last_send_tick = t.input.tick;
  pending_.first_ns = t.input.now_ns;
  pending_.last_ns = t.input.now_ns;
  t.out.commands.push_back(kind);
  acted_ = true;
}

bool MissionRunner::send_final(Tick & t, CommandKind kind, std::string & detail)
{
  // 끝나는 tick에 확인 없이 한 번 보내는 명령. 이 tick의 Px4Timestamp를 먼저 물어, 만들 수 없으면
  // 명령을 버리고 그 사실을 detail에 적는다(결과는 유지한다).
  const std::string name = kind == CommandKind::kNavLand ? "NAV_LAND" : "disarm";
  if (!query_stamp(t)) {
    detail += "; " + name + " not sent (Px4Timestamp unavailable); vehicle state unknown";
    if (kind == CommandKind::kDisarm) {
      detail += ", may remain armed on ground";
    }
    return false;
  }
  send_once(t, kind);
  detail += "; " + name + " sent once, not confirmed";
  if (kind == CommandKind::kDisarm) {
    detail += "; vehicle may remain armed on ground";
  }
  return true;
}

void MissionRunner::send_once(Tick & t, CommandKind kind)
{
  t.out.commands.push_back(kind);
  acted_ = true;
}

void MissionRunner::resend_due(Tick & t)
{
  if (!pending_.active) {
    return;
  }
  if (t.input.now_ns - pending_.last_ns >= config_.timeouts.command_resend_period_ns) {
    pending_.last_ns = t.input.now_ns;
    pending_.last_send_tick = t.input.tick;
    t.out.commands.push_back(pending_.kind);
  }
}

MissionRunner::AckView MissionRunner::take_ack(const Tick & t)
{
  // 대기 중인 명령의 ack만 받는다. command 묶음이 같고, 그 명령을 처음 보낸 tick 뒤에 받았고,
  // 아직 처리하지 않은 표본이어야 한다.
  AckView view;
  const AckSample * const a = t.ack;
  if (a == nullptr || !pending_.active) {
    return view;
  }
  if (a->received_tick <= pending_.first_tick || a->received_tick == last_ack_tick_) {
    return view;
  }
  if (a->command != ack_command_of(pending_.kind)) {
    return view;
  }
  last_ack_tick_ = a->received_tick;
  pending_.has_ack = true;
  pending_.last_ack = a->result;
  if (!is_rejection(a->result)) {
    pending_.accepted_ack_tick = a->received_tick;
  }
  view.fresh = true;
  view.result = a->result;
  return view;
}

bool MissionRunner::link_lost(const Tick & t) const
{
  return t.status == nullptr ||
         t.input.now_ns - t.status->received_ns >= config_.timeouts.link_timeout_ns;
}

std::int64_t MissionRunner::elapsed(const Tick & t, std::int64_t since_ns) const
{
  return t.input.now_ns - since_ns;
}

bool MissionRunner::query_stamp(Tick & t)
{
  if (!t.stamp_queried) {
    t.stamp_queried = true;
    const std::optional<std::uint64_t> now = t.clock.now_us();
    if (now.has_value()) {
      t.stamp_ok = true;
      t.stamp_us = *now;
    }
  }
  return t.stamp_ok;
}

void MissionRunner::terminate(Event event, Tick & t, Termination termination)
{
  tag(event, t);
  StateKey next = state_key();
  next.stage = Stage::kDone;
  set_state(t, next);
  publishing_ = false;
  clear_pending();
  t.out.termination = std::move(termination);
}

// ---- 전이 관측(transition.hpp) ----

StateKey MissionRunner::state_key() const
{
  StateKey key;
  key.stage = stage_;
  key.prep = prep_;
  key.cause = cause_;
  key.branch = branch_;
  key.item_index = item_index_;
  key.item_type = item_index_ < mission_.items.size() ? mission_.items[item_index_].type : 0;
  return key;
}

void MissionRunner::set_state(Tick & t, const StateKey & next)
{
  // item_type은 item_index에서 나오므로 쓰는 다섯 성분만 견준다.
  const bool changes = next.stage != stage_ || next.prep != prep_ || next.cause != cause_ ||
                       next.branch != branch_ || next.item_index != item_index_;
  if (observer_ != nullptr && t.open && changes) {
    // 꼬리표 하나는 상태 key를 한 번까지만 바꾼다. 두 번째 변경은 앞 기록의 to에 넣지 않고(앞
    // 기록은 이 변경 직전의 상태 key로 닫는다) 꼬리표 없는 변경으로 남긴다(다음 close_record가
    // untagged로 낸다).
    if (t.open_changes >= 1) {
      close_record(t);
    } else {
      ++t.open_changes;
    }
  }
  stage_ = next.stage;
  prep_ = next.prep;
  cause_ = next.cause;
  branch_ = next.branch;
  item_index_ = next.item_index;
}

void MissionRunner::tag(Event event, Tick & t, const std::vector<Event> & also_true)
{
  if (observer_ == nullptr) {
    return;
  }
  if (t.open && t.open_edge.event == event && state_key() == t.open_edge.from) {
    for (const Event e : also_true) {
      t.open_edge.also_true.push_back(e);
    }
    return;
  }
  close_record(t);
  t.open_edge = TransitionEdge{};
  t.open_edge.tick = t.input.tick;
  t.open_edge.event = event;
  t.open_edge.also_true = also_true;
  t.open_edge.from = state_key();
  t.open = true;
  t.open_changes = 0;
}

void MissionRunner::close_record(Tick & t)
{
  if (observer_ == nullptr) {
    return;
  }
  const StateKey now = state_key();
  TransitionEdge edge;
  if (t.open) {
    edge = t.open_edge;
    t.open = false;
  } else if (now != t.checkpoint) {
    edge.tick = t.input.tick;
    edge.tagged = false;
    edge.from = t.checkpoint;
  } else {
    return;
  }
  edge.to = now;
  if (now.stage == Stage::kDone && t.out.termination.has_value()) {
    edge.terminated = true;
    edge.status = t.out.termination->status;
    edge.reason = t.out.termination->reason;
  }
  // also_true를 kAllEvents 순서로 두고 중복을 없앤다(칸 비교가 순서에 묶이지 않게).
  std::vector<Event> sorted;
  for (const Event e : kAllEvents) {
    for (const Event a : edge.also_true) {
      if (a == e && a != edge.event) {
        sorted.push_back(e);
        break;
      }
    }
  }
  edge.also_true = sorted;
  t.edges.push_back(edge);
  t.checkpoint = now;
}

void MissionRunner::note_ignored_cancel(Tick & t)
{
  if (observer_ == nullptr) {
    return;
  }
  close_record(t);
  for (auto it = t.edges.rbegin(); it != t.edges.rend(); ++it) {
    if (in_flow_stage(it->from.stage) && !in_flow_stage(it->to.stage)) {
      it->also_true.push_back(Event::kCancel);
      return;
    }
  }
}

void MissionRunner::flush_records(Tick & t)
{
  if (observer_ == nullptr) {
    return;
  }
  close_record(t);
  for (const TransitionEdge & edge : t.edges) {
    observer_->on_edge(edge);
  }
}

Termination MissionRunner::aborted(Reason reason, std::string detail) const
{
  Termination term;
  term.status = Status::kAborted;
  term.reason = reason;
  term.items_completed = items_completed_;
  term.last_item_index = stage_ == Stage::kPreparing ? 0 : item_index_;
  term.detail = std::move(detail);
  return term;
}

Termination MissionRunner::canceled(std::string detail) const
{
  Termination term = aborted(Reason::kNone, std::move(detail));
  term.status = Status::kCanceled;
  return term;
}

Termination MissionRunner::succeeded() const
{
  Termination term;
  term.status = Status::kSucceeded;
  term.reason = Reason::kNone;
  term.items_completed = static_cast<std::uint32_t>(mission_.items.size());
  term.last_item_index = static_cast<std::uint32_t>(mission_.items.size() - 1);
  return term;
}

std::string MissionRunner::item_label() const
{
  return "item " + std::to_string(item_index_) + " (" + item_type_name(current_item().type) + ")";
}

}  // namespace idsim_mission::core
