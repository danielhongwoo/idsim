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

#include "idsim_mission/node/mission_executor_node.hpp"

#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include "idsim_common/contract_qos.hpp"
#include "idsim_common/px4_io.hpp"
#include "idsim_common/px4_timestamp.hpp"
#include "idsim_mission/core/mission_validation.hpp"
#include "idsim_mission/px4/inputs.hpp"
#include "idsim_mission/px4/outputs.hpp"
#include "lifecycle_msgs/msg/state.hpp"
#include "rclcpp_components/register_node_macro.hpp"

namespace idsim_mission
{

namespace
{

namespace topics = idsim_common::px4::topics;

rcl_interfaces::msg::ParameterDescriptor read_only(const char * description)
{
  rcl_interfaces::msg::ParameterDescriptor d;
  d.description = description;
  d.read_only = true;
  return d;
}

std::int64_t seconds_to_ns(double seconds)
{
  return static_cast<std::int64_t>(std::llround(seconds * 1e9));
}

double ns_to_seconds(std::int64_t ns) { return static_cast<double>(ns) / 1e9; }

std::size_t ack_index(core::AckCommand command) { return static_cast<std::size_t>(command); }

}  // namespace

MissionExecutorNode::MissionExecutorNode(const rclcpp::NodeOptions & options)
: rclcpp_lifecycle::LifecycleNode("mission_executor", options)
{
  declare_parameters();
  // context 종료(SIGINT 등) 직전에 실행 중인 goal을 ABORTED로 끝내고 사건을 낸다. 이 callback은
  // executor와 다른 thread에서 돌 수 있어 mutex로 지킨다.
  pre_shutdown_ = get_node_base_interface()->get_context()->add_pre_shutdown_callback([this]() {
    const std::lock_guard<std::mutex> lock(mutex_);
    abort_running_goal("context shutdown");
  });
  if (self_start_) {
    // 벽시계 일회 timer: /clock이 오기 전에도 전이를 시도한다(판정에 쓰지 않는 trigger).
    self_start_timer_ = create_wall_timer(std::chrono::milliseconds(0), [this]() { self_start(); });
  }
}

MissionExecutorNode::~MissionExecutorNode()
{
  if (pre_shutdown_.has_value()) {
    get_node_base_interface()->get_context()->remove_pre_shutdown_callback(*pre_shutdown_);
  }
}

void MissionExecutorNode::declare_parameters()
{
  vehicle_ = idsim_common::declare_vehicle_params(*this, &vehicle_error_);
  if (vehicle_.has_value()) {
    vehicle_id_ = vehicle_->id.str();
  }
  self_start_ = declare_parameter<bool>(
    kParamSelfStart, true,
    read_only("configure and activate by itself once after construction (tests set false)"));
  const core::Timeouts defaults;
  core::Timeouts & t = config_.timeouts;
  const auto seconds = [this](const char * name, std::int64_t default_ns, const char * what) {
    return seconds_to_ns(
      declare_parameter<double>(name, ns_to_seconds(default_ns), read_only(what)));
  };
  t.ready_timeout_ns =
    seconds("ready_timeout", defaults.ready_timeout_ns, "s, P0 and P2 limit from goal accept");
  t.offboard_signal_timeout_ns =
    seconds("offboard_signal_timeout", defaults.offboard_signal_timeout_ns, "s, P4 limit");
  t.mode_confirm_timeout_ns =
    seconds("mode_confirm_timeout", defaults.mode_confirm_timeout_ns, "s, mode or disarm confirm");
  t.arm_timeout_ns = seconds("arm_timeout", defaults.arm_timeout_ns, "s, P6 limit");
  t.hold_confirm_timeout_ns =
    seconds("hold_confirm_timeout", defaults.hold_confirm_timeout_ns, "s, Hold confirm limit");
  t.link_timeout_ns =
    seconds("link_timeout", defaults.link_timeout_ns, "s, vehicle_status absence limit");
  t.land_disarm_fallback_delay_ns = seconds(
    "land_disarm_fallback_delay", defaults.land_disarm_fallback_delay_ns,
    "s, landed and armed time before fallback disarm");
  t.command_resend_period_ns =
    seconds("command_resend_period", defaults.command_resend_period_ns, "s, command resend");
  declare_parameter<int>(kParamSourceSystem, 254, read_only("VehicleCommand source_system"));
  declare_parameter<int>(kParamSourceComponent, 191, read_only("VehicleCommand source_component"));
}

void MissionExecutorNode::self_start()
{
  self_start_timer_->cancel();  // 0 ms 벽시계 timer는 취소하지 않으면 계속 다시 돈다
  const rclcpp_lifecycle::State & configured = configure();
  if (configured.id() != lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE) {
    RCLCPP_ERROR(
      get_logger(), "%s: configure failed, state %s: %s", kStartFailedLogPrefix,
      configured.label().c_str(), last_failure().c_str());
    return;
  }
  const rclcpp_lifecycle::State & activated = activate();
  if (activated.id() != lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
    RCLCPP_ERROR(
      get_logger(), "%s: activate failed, state %s: %s", kStartFailedLogPrefix,
      activated.label().c_str(), last_failure().c_str());
  }
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::fail(
  const std::string & transition, const std::string & why)
{
  {
    const std::lock_guard<std::mutex> lock(mutex_);
    last_failure_ = transition + ": " + why;
  }
  RCLCPP_ERROR(get_logger(), "%s failed: %s", transition.c_str(), why.c_str());
  return CallbackReturn::FAILURE;
}

std::string MissionExecutorNode::last_failure() const
{
  const std::lock_guard<std::mutex> lock(mutex_);
  return last_failure_;
}

bool MissionExecutorNode::goal_active() const
{
  const std::lock_guard<std::mutex> lock(mutex_);
  return runner_ != nullptr;
}

// ---- lifecycle ----

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_configure(
  const rclcpp_lifecycle::State & /*previous*/)
{
  if (!vehicle_.has_value()) {
    return fail("configure", "vehicle params: " + vehicle_error_);
  }
  if (!get_parameter("use_sim_time").as_bool()) {
    return fail("configure", "use_sim_time must be true");
  }
  const std::string ns = get_namespace();
  if (ns != vehicle_->identity.ns.str()) {
    return fail(
      "configure",
      "node namespace '" + ns + "' is not vehicle.ns '" + vehicle_->identity.ns.str() + "'");
  }
  const core::Timeouts & t = config_.timeouts;
  for (const std::int64_t v :
       {t.ready_timeout_ns, t.offboard_signal_timeout_ns, t.mode_confirm_timeout_ns,
        t.arm_timeout_ns, t.hold_confirm_timeout_ns, t.link_timeout_ns,
        t.land_disarm_fallback_delay_ns, t.command_resend_period_ns}) {
    if (v <= 0) {
      return fail("configure", "timeouts and periods must be > 0");
    }
  }
  const std::optional<idsim_common::CommandSource> source = idsim_common::CommandSource::make(
    static_cast<int>(get_parameter(kParamSourceSystem).as_int()),
    static_cast<int>(get_parameter(kParamSourceComponent).as_int()));
  if (!source.has_value()) {
    return fail("configure", "invalid command_source");
  }
  builder_ = idsim_common::VehicleCommandBuilder::make(vehicle_->identity, *source);
  if (!builder_.has_value()) {
    return fail("configure", "command_source.system must differ from vehicle.sysid");
  }
  if (t.link_timeout_ns >= t.mode_confirm_timeout_ns) {
    // 지상 disarm 분기는 link_timeout이 mode_confirm_timeout보다 짧다는 전제로 정했다
    // (decisions.md 쟁점 3 M5 "지상 disarm 분기의 상태 끊김과 거부 ack").
    RCLCPP_WARN(
      get_logger(), "link_timeout (%.3f s) is not shorter than mode_confirm_timeout (%.3f s)",
      ns_to_seconds(t.link_timeout_ns), ns_to_seconds(t.mode_confirm_timeout_ns));
  }
  // 정리의 상한(decisions.md 쟁점 3 M6)은 노드 파라미터가 아니라 파생값이라 계산값을 남긴다.
  RCLCPP_INFO(
    get_logger(), "cleanup cap %.3f s (hold_confirm_timeout + 3 x mode_confirm_timeout)",
    ns_to_seconds(core::cleanup_cap_ns(t)));
  create_entities(*vehicle_, *builder_);
  return CallbackReturn::SUCCESS;
}

void MissionExecutorNode::create_entities(
  const idsim_common::VehicleParams & vehicle, const idsim_common::VehicleCommandBuilder & builder)
{
  const idsim_common::VehicleNamespace & ns = vehicle.identity.ns;
  const idsim_common::VehicleIdentity identity = vehicle.identity;
  const idsim_common::CommandSource source = builder.source();
  group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  rclcpp::SubscriptionOptions sub_options;
  sub_options.callback_group = group_;
  const auto received = [this]() {
    return px4::Received{next_tick_, get_clock()->now().nanoseconds()};
  };
  // 구독 callback은 최신 표본 하나와 받은 tick, ROS 시각만 저장한다.
  subs_.status = idsim_common::px4::create_subscription<topics::VehicleStatus>(
    *this, ns,
    [this, identity, received](const px4_msgs::msg::VehicleStatus::ConstSharedPtr & msg) {
      const std::lock_guard<std::mutex> lock(mutex_);
      snapshot_.status = px4::to_status_sample(*msg, identity, received());
    },
    sub_options);
  subs_.land = idsim_common::px4::create_subscription<topics::VehicleLandDetected>(
    *this, ns,
    [this](const px4_msgs::msg::VehicleLandDetected::ConstSharedPtr & msg) {
      const std::lock_guard<std::mutex> lock(mutex_);
      snapshot_.land = px4::to_land_sample(*msg, next_tick_);
    },
    sub_options);
  subs_.position = idsim_common::px4::create_subscription<topics::VehicleLocalPosition>(
    *this, ns,
    [this](const px4_msgs::msg::VehicleLocalPosition::ConstSharedPtr & msg) {
      const std::lock_guard<std::mutex> lock(mutex_);
      snapshot_.position = px4::to_position_sample(*msg, next_tick_);
    },
    sub_options);
  subs_.flags = idsim_common::px4::create_subscription<topics::FailsafeFlags>(
    *this, ns,
    [this](const px4_msgs::msg::FailsafeFlags::ConstSharedPtr & msg) {
      const std::lock_guard<std::mutex> lock(mutex_);
      snapshot_.flags = px4::to_flags_sample(*msg, next_tick_);
    },
    sub_options);
  // ack는 한 tick에 여럿 올 수 있다(PX4 쪽 큐 4). command 묶음별 최신 하나를 두고 tick마다
  // 대기 중인 명령의 묶음을 core에 넘긴다(select_ack).
  subs_.ack = idsim_common::px4::create_subscription<topics::VehicleCommandAck>(
    *this, ns,
    [this, source](const px4_msgs::msg::VehicleCommandAck::ConstSharedPtr & msg) {
      const std::lock_guard<std::mutex> lock(mutex_);
      const std::optional<core::AckSample> ack = px4::to_ack_sample(*msg, source, next_tick_);
      if (ack.has_value()) {
        acks_.at(ack_index(ack->command)) = ack;
      }
    },
    sub_options);
  pubs_.mode = idsim_common::px4::create_publisher<topics::OffboardControlMode>(*this, ns);
  pubs_.trajectory = idsim_common::px4::create_publisher<topics::TrajectorySetpoint>(*this, ns);
  pubs_.command = idsim_common::px4::create_publisher<topics::VehicleCommand>(*this, ns);
  // 사건 토픽은 상대 이름(노드 네임스페이스 /<vehicle_id> 아래).
  pubs_.event = create_publisher<idsim_interfaces::msg::MissionEvent>(
    idsim_interfaces::msg::MissionEvent::TOPIC_NAME, idsim_common::event_pub_qos());
  clock_port_ = std::make_unique<px4::RosPx4ClockPort>(*get_clock());
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_activate(
  const rclcpp_lifecycle::State & /*previous*/)
{
  // 첫 /clock을 벽시계로 2 s 기다린다(판정이 아니라 hang 방지. 파라미터가 아니다). 그동안의
  // /clock은 TimeSource의 clock thread가 받는다.
  if (!get_clock()->wait_until_started(
        rclcpp::Duration::from_nanoseconds(kClockWaitNs),
        get_node_base_interface()->get_context())) {
    return fail("activate", "no /clock within 2 s");
  }
  if (!idsim_common::Px4Timestamp::now(*get_clock()).has_value()) {
    return fail("activate", "Px4Timestamp unavailable (sim time not active)");
  }
  pubs_.mode->on_activate();
  pubs_.trajectory->on_activate();
  pubs_.command->on_activate();
  pubs_.event->on_activate();
  tick_timer_ = rclcpp::create_timer(
    get_node_base_interface(), get_node_timers_interface(), get_clock(),
    rclcpp::Duration::from_nanoseconds(kTickPeriodNs), [this]() { on_tick(); }, group_);
  // action 서버는 active에서만 있다(client의 server_is_ready가 active의 근거가 된다). on_error 뒤에
  // 남은 옛 서버는 새 서버를 만들기 전에 지운다(같은 이름의 서버가 겹치지 않게).
  action_server_.reset();
  action_server_ = rclcpp_action::create_server<ExecuteMission>(
    this, idsim_interfaces::msg::Mission::ACTION_NAME,
    [this](
      const rclcpp_action::GoalUUID & uuid,
      const std::shared_ptr<const ExecuteMission::Goal> & goal) { return handle_goal(uuid, goal); },
    [this](const std::shared_ptr<GoalHandle> & goal_handle) { return handle_cancel(goal_handle); },
    [this](const std::shared_ptr<GoalHandle> & goal_handle) { handle_accepted(goal_handle); },
    rcl_action_server_get_default_options(), group_);
  return CallbackReturn::SUCCESS;
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_deactivate(
  const rclcpp_lifecycle::State & /*previous*/)
{
  if (goal_active()) {
    return fail("deactivate", "a goal is executing");
  }
  action_server_.reset();
  if (tick_timer_ != nullptr) {
    tick_timer_->cancel();
  }
  tick_timer_.reset();
  pubs_.mode->on_deactivate();
  pubs_.trajectory->on_deactivate();
  pubs_.command->on_deactivate();
  pubs_.event->on_deactivate();
  return CallbackReturn::SUCCESS;
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_cleanup(
  const rclcpp_lifecycle::State & /*previous*/)
{
  const std::lock_guard<std::mutex> lock(mutex_);
  subs_ = Subscriptions{};
  pubs_ = Publishers{};
  clock_port_.reset();
  builder_.reset();
  snapshot_ = core::Snapshot{};
  acks_ = {};
  return CallbackReturn::SUCCESS;
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_shutdown(
  const rclcpp_lifecycle::State & /*previous*/)
{
  const std::lock_guard<std::mutex> lock(mutex_);
  abort_running_goal("executor shutdown");
  // action 서버는 남겨 둔다. 지운 goal의 result 요청에 답해야 하고, 그 뒤에 온 goal은
  // handle_accepted가 즉시 ABORTED로 끝낸다. 서버는 소멸자에서 없어진다.
  if (tick_timer_ != nullptr) {
    tick_timer_->cancel();
  }
  tick_timer_.reset();
  return CallbackReturn::SUCCESS;
}

MissionExecutorNode::CallbackReturn MissionExecutorNode::on_error(
  const rclcpp_lifecycle::State & /*previous*/)
{
  const std::lock_guard<std::mutex> lock(mutex_);
  abort_running_goal("executor error");
  // unconfigured로 돌아가므로 on_cleanup처럼 비운다. 다음 configure가 구독과 발행자를 새로 만든다.
  // action 서버는 남겨 둔다(끝낸 goal의 result 요청). 다음 on_activate가 새로 만들기 전에 지운다.
  if (tick_timer_ != nullptr) {
    tick_timer_->cancel();
  }
  tick_timer_.reset();
  subs_ = Subscriptions{};
  pubs_ = Publishers{};
  clock_port_.reset();
  builder_.reset();
  snapshot_ = core::Snapshot{};
  acks_ = {};
  return CallbackReturn::SUCCESS;
}

// ---- action ----

rclcpp_action::GoalResponse MissionExecutorNode::handle_goal(
  const rclcpp_action::GoalUUID & /*uuid*/,
  const std::shared_ptr<const ExecuteMission::Goal> & /*goal*/)
{
  // 거절은 쓰지 않는다. 받을 수 없는 goal은 받아들인 뒤 즉시 ABORTED로 끝낸다.
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse MissionExecutorNode::handle_cancel(
  const std::shared_ptr<GoalHandle> & /*goal_handle*/)
{
  // 분기는 다음 tick에 core가 고른다(is_canceling).
  return rclcpp_action::CancelResponse::ACCEPT;
}

void MissionExecutorNode::handle_accepted(const std::shared_ptr<GoalHandle> & goal_handle)
{
  const std::lock_guard<std::mutex> lock(mutex_);
  const std::shared_ptr<const ExecuteMission::Goal> goal = goal_handle->get_goal();
  EventContext context;
  context.stamp = stamp_now();
  context.vehicle_id = vehicle_id_;
  context.mission_id = goal->mission.mission_id;
  context.goal_id = goal_handle->get_goal_id();
  context.item_count = static_cast<std::uint32_t>(goal->mission.items.size());
  // on_error 뒤에는 발행자가 없을 수 있다(그 goal은 아래에서 즉시 ABORTED로 끝난다).
  if (pubs_.event != nullptr) {
    RCLCPP_DEBUG(
      get_logger(), "goal accepted, mission_event subscriptions: %zu",
      pubs_.event->get_subscription_count());
    pubs_.event->publish(accepted_event_msg(context));
  }

  core::MissionSpec spec = to_mission_spec(goal->mission);
  std::optional<core::Termination> screened =
    core::screen_goal(goal->vehicle_id, vehicle_id_, spec, runner_ != nullptr);
  if (
    !screened.has_value() &&
    get_current_state().id() != lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE) {
    // 종료(on_shutdown) 뒤에도 서버가 남아 있는 동안 온 goal.
    core::Termination term;
    term.status = core::Status::kAborted;
    term.reason = core::Reason::kInternal;
    term.detail = "executor is not active";
    screened = term;
  }
  if (screened.has_value()) {
    finish(goal_handle, context, *screened);
    return;
  }
  runner_ = std::make_unique<core::MissionRunner>(
    std::move(spec), config_, get_clock()->now().nanoseconds());
  goal_ = goal_handle;
  goal_context_ = context;
  ticks_since_feedback_ = 0;
  last_feedback_item_ = 0;
  last_feedback_phase_ = 0;
}

void MissionExecutorNode::finish(
  const std::shared_ptr<GoalHandle> & goal_handle, EventContext context,
  const core::Termination & term)
{
  context.stamp = stamp_now();
  if (pubs_.event != nullptr) {
    pubs_.event->publish(terminal_event_msg(context, term));
  }
  auto result = std::make_shared<ExecuteMission::Result>(to_result_msg(term));
  switch (term.status) {
    case core::Status::kSucceeded:
      goal_handle->succeed(result);
      return;
    case core::Status::kCanceled:
      if (goal_handle->is_canceling()) {
        goal_handle->canceled(result);
      } else {
        goal_handle->abort(result);
      }
      return;
    case core::Status::kAborted:
      goal_handle->abort(result);
      return;
  }
}

void MissionExecutorNode::abort_running_goal(const std::string & why)
{
  if (runner_ == nullptr || goal_ == nullptr) {
    return;
  }
  const core::RunnerView view = runner_->view();
  core::Termination term;
  term.status = core::Status::kAborted;
  term.reason = core::Reason::kInternal;
  term.items_completed = view.items_completed;
  term.last_item_index = view.stage == core::Stage::kPreparing ? 0 : view.item_index;
  term.detail = why;
  if (view.arm_sent) {
    // 지상 arm 뒤 이륙 전이면 자동 disarm이 없다(COM_DISARM_PRFLT=-1). 강제가 아닌 disarm을 한 번
    // 보낸다. 공중이면 PX4가 거부하고, vehicle_command는 target_system 주소라 다른 기체에 닿지
    // 않는다.
    const std::optional<idsim_common::Px4Timestamp> stamp =
      idsim_common::Px4Timestamp::now(*get_clock());
    if (
      pubs_.command != nullptr && pubs_.command->is_activated() && builder_.has_value() &&
      stamp.has_value()) {
      pubs_.command->publish(builder_->disarm(*stamp));
      term.detail += "; disarm sent once, not confirmed; vehicle may remain armed on ground";
    } else {
      term.detail += "; disarm could not be sent, vehicle state unknown";
    }
  }
  if (goal_->is_active()) {
    finish(goal_, goal_context_, term);
  }
  runner_.reset();
  goal_.reset();
}

// ---- tick ----

void MissionExecutorNode::select_ack()
{
  snapshot_.ack.reset();
  const core::RunnerView view = runner_->view();
  if (view.pending_active) {
    snapshot_.ack = acks_.at(ack_index(core::ack_command_of(view.pending)));
  }
}

void MissionExecutorNode::on_tick()
{
  const std::lock_guard<std::mutex> lock(mutex_);
  const std::uint64_t tick = next_tick_++;
  if (runner_ == nullptr || goal_ == nullptr || !builder_.has_value()) {
    return;
  }
  const idsim_common::VehicleCommandBuilder & builder = *builder_;
  select_ack();
  core::TickInput input;
  input.tick = tick;
  input.now_ns = get_clock()->now().nanoseconds();
  input.cancel_requested = goal_->is_canceling();
  clock_port_->begin_tick();
  const core::StepOutput out = runner_->step(input, snapshot_, *clock_port_);
  const px4::Px4Messages msgs = px4::to_px4_messages(out, builder, clock_port_->stamp());
  if (!msgs.error.empty()) {
    RCLCPP_ERROR(get_logger(), "px4 output dropped: %s", msgs.error.c_str());
  }
  if (msgs.setpoint.has_value()) {
    pubs_.mode->publish(msgs.setpoint->mode);
    pubs_.trajectory->publish(msgs.setpoint->trajectory);
  }
  for (const px4_msgs::msg::VehicleCommand & command : msgs.commands) {
    pubs_.command->publish(command);
  }
  if (out.feedback.has_value()) {
    const auto phase = static_cast<std::uint8_t>(out.feedback->phase);
    const bool changed =
      phase != last_feedback_phase_ || out.feedback->item_index != last_feedback_item_;
    if (changed || ++ticks_since_feedback_ >= kFeedbackEveryTicks) {
      goal_->publish_feedback(
        std::make_shared<ExecuteMission::Feedback>(to_feedback_msg(*out.feedback, stamp_now())));
      ticks_since_feedback_ = 0;
      last_feedback_phase_ = phase;
      last_feedback_item_ = out.feedback->item_index;
    }
  }
  if (out.termination.has_value()) {
    finish(goal_, goal_context_, *out.termination);
    runner_.reset();
    goal_.reset();
  }
}

builtin_interfaces::msg::Time MissionExecutorNode::stamp_now() { return get_clock()->now(); }

}  // namespace idsim_mission

RCLCPP_COMPONENTS_REGISTER_NODE(idsim_mission::MissionExecutorNode)
