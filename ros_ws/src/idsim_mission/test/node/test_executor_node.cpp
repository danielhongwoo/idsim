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

// 노드 껍질의 배선 테스트(PX4 없이, 한 프로세스). decisions.md 쟁점 2, 7과 test-engineer 지시.
// - lifecycle.self_start 대조군 쌍: 같은 spin 횟수에서 true는 active, false는 unconfigured.
// - 직접 건 configure, activate. params 누락과 use_sim_time false의 configure 실패.
// - goal 실행 중 deactivate 거부, on_shutdown이 실행 중 goal을 ABORTED, REASON_INTERNAL로 끝내고
//   종료 사건을 낸다.
// - 배선: 가짜 PX4 발행자로 정상 한 경로(TAKEOFF, LOITER, LAND -> SUCCEEDED)와 무효 한 경로
//   (GOTO -> INVALID_MISSION). 사건은 ACCEPTED가 앞이고 종료 사건은 1건이며 result와 같은 값.
// - rclcpp_action에서 cancel을 받아들인 goal을 abort로 끝낼 수 있는지(decisions.md 쟁점 3 "종료의
//   충돌 규칙"의 rclcpp_action 허용 확인).
// - PREPARING 중 취소의 CANCELED, 실행 중 두 번째 goal의 BUSY, 종료 때의 disarm 한 번(arm 뒤 1개,
//   arm 전 0개. px4-engineer P3d-1).
// 시계: 별도 thread가 /clock을 발행한다(on_activate의 2 s 대기는 파라미터가 아니다). 사건 구독은
// action client보다 먼저, 같은 노드에서 만든다(쟁점 7 순서 규칙).

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "idsim_common/contract_qos.hpp"
#include "idsim_common/px4_io.hpp"
#include "idsim_common/qos.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_mission/node/mission_executor_node.hpp"
#include "lifecycle_msgs/msg/state.hpp"
#include "px4_msgs/msg/failsafe_flags.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/vehicle_land_detected.hpp"
#include "px4_msgs/msg/vehicle_local_position.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rosgraph_msgs/msg/clock.hpp"

namespace idsim_mission::test
{
namespace
{

using ExecuteMission = idsim_interfaces::action::ExecuteMission;
using MissionEvent = idsim_interfaces::msg::MissionEvent;
using MissionItem = idsim_interfaces::msg::MissionItem;
using lifecycle_msgs::msg::State;
namespace topics = idsim_common::px4::topics;

constexpr std::int64_t kStartSimNs = 1000LL * 1000000000LL;

// /clock 발행 thread. 벽시계 1 ms마다 sim 시간을 2 ms 올린다(RTF 약 2).
class ClockThread
{
public:
  ClockThread()
  {
    node_ = std::make_shared<rclcpp::Node>("test_clock");
    pub_ = node_->create_publisher<rosgraph_msgs::msg::Clock>("/clock", rclcpp::ClockQoS());
    thread_ = std::thread([this]() {
      while (running_) {
        rosgraph_msgs::msg::Clock msg;
        msg.clock = rclcpp::Time(sim_ns_.load());
        pub_->publish(msg);
        sim_ns_ += 2000000;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
      }
    });
  }
  ~ClockThread()
  {
    running_ = false;
    thread_.join();
  }
  ClockThread(const ClockThread &) = delete;
  ClockThread & operator=(const ClockThread &) = delete;

  std::int64_t now_ns() const { return sim_ns_.load(); }

private:
  rclcpp::Node::SharedPtr node_;
  rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr pub_;
  std::atomic<std::int64_t> sim_ns_{kStartSimNs};
  std::atomic<bool> running_{true};
  std::thread thread_;
};

std::shared_ptr<MissionExecutorNode> make_executor(
  bool self_start, bool with_vehicle = true, bool use_sim_time = true,
  const std::string & name = "mission_executor")
{
  std::vector<rclcpp::Parameter> params = {
    rclcpp::Parameter("use_sim_time", use_sim_time),
    rclcpp::Parameter(kParamSelfStart, self_start),
  };
  if (with_vehicle) {
    params.emplace_back("vehicle.id", "px4_1");
    params.emplace_back("vehicle.ns", "/px4_1");
    params.emplace_back("vehicle.sysid", 2);
  }
  rclcpp::NodeOptions options;
  options.parameter_overrides(params);
  options.arguments({"--ros-args", "-r", "__ns:=/px4_1", "-r", "__node:=" + name});
  options.use_global_arguments(false);
  return std::make_shared<MissionExecutorNode>(options);
}

std::uint8_t state_of(const std::shared_ptr<MissionExecutorNode> & node)
{
  return node->get_current_state().id();
}

// 가짜 PX4: 명령에 반응하고 /fmu/out 표본을 낸다. 실제 PX4의 판정을 흉내 내지 않는다(배선만 본다).
class FakePx4
{
public:
  FakePx4(const rclcpp::Node::SharedPtr & node, const ClockThread & clock)
  : node_(node), clock_(clock)
  {
    const auto ns = *idsim_common::VehicleNamespace::parse("/px4_1");
    const rclcpp::QoS qos = idsim_common::px4::px4_out_qos();
    status_ = node->create_publisher<px4_msgs::msg::VehicleStatus>(
      idsim_common::px4::topic_name<topics::VehicleStatus>(ns), qos);
    land_ = node->create_publisher<px4_msgs::msg::VehicleLandDetected>(
      idsim_common::px4::topic_name<topics::VehicleLandDetected>(ns), qos);
    position_ = node->create_publisher<px4_msgs::msg::VehicleLocalPosition>(
      idsim_common::px4::topic_name<topics::VehicleLocalPosition>(ns), qos);
    flags_ = node->create_publisher<px4_msgs::msg::FailsafeFlags>(
      idsim_common::px4::topic_name<topics::FailsafeFlags>(ns), qos);
    command_ = node->create_subscription<px4_msgs::msg::VehicleCommand>(
      idsim_common::px4::topic_name<topics::VehicleCommand>(ns), qos,
      [this](const px4_msgs::msg::VehicleCommand::ConstSharedPtr msg) { on_command(*msg); });
    setpoint_ = node->create_subscription<px4_msgs::msg::TrajectorySetpoint>(
      idsim_common::px4::topic_name<topics::TrajectorySetpoint>(ns), qos,
      [this](const px4_msgs::msg::TrajectorySetpoint::ConstSharedPtr msg) {
        got_setpoint_ = true;
        setpoint_z_ = msg->position[2];
      });
  }

  // 20 ms(sim)마다 표본을 낸다.
  void step()
  {
    const std::int64_t now = clock_.now_ns();
    if (now - last_publish_ns_ < 20000000) {
      return;
    }
    last_publish_ns_ = now;
    using VS = px4_msgs::msg::VehicleStatus;
    if (armed_ && nav_ == VS::NAVIGATION_STATE_OFFBOARD && setpoint_z_ < z_ - 0.1F) {
      z_ = setpoint_z_;
      landed_ = false;
    }
    if (armed_ && nav_ == VS::NAVIGATION_STATE_AUTO_LAND && now - land_start_ns_ > 1000000000) {
      z_ = 0.0F;
      landed_ = true;
      armed_ = false;
    }
    const auto us = static_cast<std::uint64_t>(now / 1000);
    VS status;
    status.timestamp = us;
    status.nav_state = nav_;
    status.nav_state_user_intention = nav_;
    status.arming_state = armed_ ? VS::ARMING_STATE_ARMED : VS::ARMING_STATE_DISARMED;
    status.failsafe = false;
    status.system_id = 2;
    status.component_id = 1;
    status_->publish(status);
    px4_msgs::msg::VehicleLandDetected land;
    land.timestamp = us;
    land.landed = landed_;
    land_->publish(land);
    px4_msgs::msg::VehicleLocalPosition pos;
    pos.timestamp = us;
    pos.x = 1.0F;
    pos.y = 2.0F;
    pos.z = z_;
    pos.heading = 0.0F;
    pos.z_valid = true;
    pos.xy_valid = true;
    position_->publish(pos);
    px4_msgs::msg::FailsafeFlags flags;
    flags.timestamp = us;
    flags.offboard_control_signal_lost = !got_setpoint_;
    flags_->publish(flags);
  }

  bool armed() const { return armed_; }
  int commands() const { return commands_; }
  int disarms() const { return disarms_; }
  int offboards() const { return offboards_; }
  bool react_offboard{true};  // false면 Offboard 요청에 반응하지 않는다(P5에 머문다)

private:
  void on_command(const px4_msgs::msg::VehicleCommand & cmd)
  {
    using VC = px4_msgs::msg::VehicleCommand;
    using VS = px4_msgs::msg::VehicleStatus;
    ++commands_;
    if (cmd.command == VC::VEHICLE_CMD_COMPONENT_ARM_DISARM && cmd.param1 == 0.0F) {
      ++disarms_;
    }
    if (cmd.command == VC::VEHICLE_CMD_DO_SET_MODE && cmd.param2 == 6.0F) {
      ++offboards_;
      if (react_offboard) {
        nav_ = VS::NAVIGATION_STATE_OFFBOARD;
      }
    } else if (cmd.command == VC::VEHICLE_CMD_DO_SET_MODE && cmd.param2 == 4.0F) {
      nav_ = VS::NAVIGATION_STATE_AUTO_LOITER;
    } else if (cmd.command == VC::VEHICLE_CMD_COMPONENT_ARM_DISARM && cmd.param1 == 1.0F) {
      armed_ = true;
    } else if (cmd.command == VC::VEHICLE_CMD_COMPONENT_ARM_DISARM && cmd.param1 == 0.0F) {
      if (landed_) {
        armed_ = false;
      }
    } else if (cmd.command == VC::VEHICLE_CMD_NAV_LAND) {
      nav_ = VS::NAVIGATION_STATE_AUTO_LAND;
      land_start_ns_ = clock_.now_ns();
    }
  }

  rclcpp::Node::SharedPtr node_;
  const ClockThread & clock_;
  rclcpp::Publisher<px4_msgs::msg::VehicleStatus>::SharedPtr status_;
  rclcpp::Publisher<px4_msgs::msg::VehicleLandDetected>::SharedPtr land_;
  rclcpp::Publisher<px4_msgs::msg::VehicleLocalPosition>::SharedPtr position_;
  rclcpp::Publisher<px4_msgs::msg::FailsafeFlags>::SharedPtr flags_;
  rclcpp::Subscription<px4_msgs::msg::VehicleCommand>::SharedPtr command_;
  rclcpp::Subscription<px4_msgs::msg::TrajectorySetpoint>::SharedPtr setpoint_;
  std::uint8_t nav_{px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER};
  bool armed_{false};
  bool landed_{true};
  float z_{0.0F};
  float setpoint_z_{0.0F};
  bool got_setpoint_{false};
  std::int64_t land_start_ns_{0};
  std::int64_t last_publish_ns_{0};
  int commands_{0};
  int disarms_{0};
  int offboards_{0};
};

class ExecutorNodeTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }

  void SetUp() override
  {
    clock_ = std::make_unique<ClockThread>();
    executor_ = std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
  }

  void TearDown() override
  {
    executor_.reset();
    clock_.reset();
  }

  // pred가 참이 될 때까지 spin(벽시계 상한). 매 회 가짜 PX4가 있으면 표본을 낸다.
  bool spin_until(const std::function<bool()> & pred, std::chrono::seconds limit, FakePx4 * px4)
  {
    const auto deadline = std::chrono::steady_clock::now() + limit;
    while (std::chrono::steady_clock::now() < deadline) {
      if (pred()) {
        return true;
      }
      executor_->spin_some(std::chrono::milliseconds(5));
      if (px4 != nullptr) {
        px4->step();
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return pred();
  }

  void spin_count(int count)
  {
    for (int i = 0; i < count; ++i) {
      executor_->spin_some(std::chrono::milliseconds(5));
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  std::unique_ptr<ClockThread> clock_;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
};

TEST_F(ExecutorNodeTest, SelfStartPair)
{
  // 대조군 쌍: 같은 executor, 같은 spin 횟수. true는 active, false는 unconfigured.
  auto on = make_executor(true, true, true, "executor_on");
  auto off = make_executor(false, true, true, "executor_off");
  executor_->add_node(on->get_node_base_interface());
  executor_->add_node(off->get_node_base_interface());
  ASSERT_TRUE(spin_until(
    [&on] { return state_of(on) == State::PRIMARY_STATE_ACTIVE; }, std::chrono::seconds(10),
    nullptr))
    << on->last_failure();
  spin_count(20);
  EXPECT_EQ(state_of(on), State::PRIMARY_STATE_ACTIVE);
  EXPECT_EQ(state_of(off), State::PRIMARY_STATE_UNCONFIGURED);
}

TEST_F(ExecutorNodeTest, DirectConfigureAndActivate)
{
  auto node = make_executor(false);
  executor_->add_node(node->get_node_base_interface());
  EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_INACTIVE) << node->last_failure();
  EXPECT_EQ(node->activate().id(), State::PRIMARY_STATE_ACTIVE) << node->last_failure();
  EXPECT_EQ(node->deactivate().id(), State::PRIMARY_STATE_INACTIVE);
  EXPECT_EQ(node->cleanup().id(), State::PRIMARY_STATE_UNCONFIGURED);
}

TEST_F(ExecutorNodeTest, ConfigureFailsWithoutVehicleParamsOrSimTime)
{
  {
    auto node = make_executor(false, false);
    EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_UNCONFIGURED);
    EXPECT_NE(node->last_failure().find("vehicle params"), std::string::npos)
      << node->last_failure();
  }
  {
    auto node = make_executor(false, true, false);
    EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_UNCONFIGURED);
    EXPECT_NE(node->last_failure().find("use_sim_time"), std::string::npos);
  }
}

// action client와 사건 구독. 구독을 client보다 먼저, 같은 노드에서 만든다(쟁점 7).
class Client
{
public:
  explicit Client(const rclcpp::Node::SharedPtr & node)
  {
    events_sub_ = node->create_subscription<MissionEvent>(
      "/px4_1/mission_event", idsim_common::event_sub_qos(),
      [this](const MissionEvent::ConstSharedPtr msg) {
        const std::lock_guard<std::mutex> lock(mutex_);
        events_.push_back(*msg);
      });
    client_ = rclcpp_action::create_client<ExecuteMission>(node, "/px4_1/execute_mission");
  }

  rclcpp_action::Client<ExecuteMission>::SharedPtr client() const { return client_; }

  std::vector<MissionEvent> events() const
  {
    const std::lock_guard<std::mutex> lock(mutex_);
    return events_;
  }

  void send(const ExecuteMission::Goal & goal)
  {
    rclcpp_action::Client<ExecuteMission>::SendGoalOptions options;
    options.goal_response_callback = [this](const GoalHandle::SharedPtr & handle) {
      handle_ = handle;
    };
    options.feedback_callback = [this](GoalHandle::SharedPtr, const auto &) { ++feedback_; };
    options.result_callback = [this](const GoalHandle::WrappedResult & result) {
      result_ = result;
      has_result_ = true;
    };
    client_->async_send_goal(goal, options);
  }

  using GoalHandle = rclcpp_action::ClientGoalHandle<ExecuteMission>;
  GoalHandle::SharedPtr handle_;
  GoalHandle::WrappedResult result_;
  bool has_result_{false};
  int feedback_{0};

private:
  mutable std::mutex mutex_;
  std::vector<MissionEvent> events_;
  rclcpp::Subscription<MissionEvent>::SharedPtr events_sub_;
  rclcpp_action::Client<ExecuteMission>::SharedPtr client_;
};

MissionItem item(std::uint8_t type, std::int32_t timeout_s)
{
  MissionItem it;
  it.type = type;
  it.timeout.sec = timeout_s;
  return it;
}

ExecuteMission::Goal standard_goal()
{
  ExecuteMission::Goal goal;
  goal.vehicle_id = "px4_1";
  goal.mission.mission_id = "wiring";
  MissionItem takeoff = item(MissionItem::TYPE_TAKEOFF, 20);
  takeoff.takeoff.height_m = 5.0;
  takeoff.takeoff.acceptance_m = 0.3;
  takeoff.takeoff.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  MissionItem loiter = item(MissionItem::TYPE_LOITER, 5);
  loiter.loiter.duration.sec = 1;
  goal.mission.items = {takeoff, loiter, item(MissionItem::TYPE_LAND, 30)};
  return goal;
}

void expect_events_match_result(
  const std::vector<MissionEvent> & events, const Client::GoalHandle::WrappedResult & result,
  std::uint8_t terminal_status)
{
  ASSERT_EQ(events.size(), 2U);
  EXPECT_EQ(events[0].status, MissionEvent::STATUS_ACCEPTED);
  EXPECT_EQ(events[1].status, terminal_status);
  EXPECT_EQ(events[0].goal_id, events[1].goal_id);
  EXPECT_EQ(events[1].goal_id, result.goal_id);
  EXPECT_EQ(events[1].vehicle_id, "px4_1");
  EXPECT_EQ(events[1].reason, result.result->reason);
  EXPECT_EQ(events[1].items_completed, result.result->items_completed);
  EXPECT_EQ(events[1].last_item_index, result.result->last_item_index);
  EXPECT_EQ(events[1].detail, result.result->detail);
}

TEST_F(ExecutorNodeTest, WiringNormalPathSucceeds)
{
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return state_of(node) == State::PRIMARY_STATE_ACTIVE &&
             client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), &px4));
  client.send(standard_goal());
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(40), &px4))
    << "events " << client.events().size() << " commands " << px4.commands();
  spin_until([&] { return client.events().size() >= 2; }, std::chrono::seconds(2), &px4);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::SUCCEEDED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_NONE);
  EXPECT_EQ(client.result_.result->items_completed, 3U);
  EXPECT_GT(client.feedback_, 0);
  EXPECT_FALSE(px4.armed());
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_SUCCEEDED);
  EXPECT_FALSE(node->goal_active());
}

TEST_F(ExecutorNodeTest, WiringInvalidMissionAbortsWithoutFeedback)
{
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), nullptr));
  ExecuteMission::Goal goal = standard_goal();
  MissionItem go = item(MissionItem::TYPE_GOTO, 10);
  go.go_to.acceptance_radius_m = 1.0;
  go.go_to.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  goal.mission.items.insert(goal.mission.items.begin() + 1, go);
  client.send(goal);
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(10), nullptr));
  spin_until([&] { return client.events().size() >= 2; }, std::chrono::seconds(2), nullptr);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_INVALID_MISSION);
  EXPECT_EQ(client.feedback_, 0);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_ABORTED);
  EXPECT_EQ(client.events()[0].item_count, 4U);
}

TEST_F(ExecutorNodeTest, DeactivateRejectedDuringGoalAndShutdownAborts)
{
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), nullptr));
  // PX4 표본이 없으므로 goal은 PREPARING(P0)에서 기다린다.
  client.send(standard_goal());
  ASSERT_TRUE(spin_until([&] { return node->goal_active(); }, std::chrono::seconds(10), nullptr));
  EXPECT_EQ(node->deactivate().id(), State::PRIMARY_STATE_ACTIVE);
  EXPECT_TRUE(node->goal_active());
  EXPECT_EQ(node->shutdown().id(), State::PRIMARY_STATE_FINALIZED);
  EXPECT_FALSE(node->goal_active());
  ASSERT_TRUE(spin_until(
    [&] { return client.has_result_ && client.events().size() >= 2; }, std::chrono::seconds(10),
    nullptr));
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_INTERNAL);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_ABORTED);
}

class CanceledGoalEndTest : public ExecutorNodeTest
{
protected:
  // cancel을 받아들인 goal을 succeed(true) 또는 abort(false)로 끝내고 client가 받은 code를
  // 돌려준다.
  rclcpp_action::ResultCode end_canceled_goal(bool succeed)
  {
    // 종료의 충돌 규칙은 cancel을 받아들인 goal을 ABORTED나 SUCCEEDED로 끝낼 수 있어야 한다.
    // rclcpp_action이 이를 허용하는지 본다(노드와 무관한 서버 하나).
    auto server_node = std::make_shared<rclcpp::Node>("test_server");
    std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> held;
    auto server = rclcpp_action::create_server<ExecuteMission>(
      server_node, "/test/execute_mission",
      [](const rclcpp_action::GoalUUID &, std::shared_ptr<const ExecuteMission::Goal>) {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      },
      [](std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>>) {
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [&held](std::shared_ptr<rclcpp_action::ServerGoalHandle<ExecuteMission>> h) { held = h; });
    auto client_node = std::make_shared<rclcpp::Node>("test_cancel_client");
    auto client =
      rclcpp_action::create_client<ExecuteMission>(client_node, "/test/execute_mission");
    executor_->add_node(server_node);
    executor_->add_node(client_node);
    if (!spin_until(
          [&] { return client->action_server_is_ready(); }, std::chrono::seconds(10), nullptr)) {
      return rclcpp_action::ResultCode::UNKNOWN;
    }
    rclcpp_action::ClientGoalHandle<ExecuteMission>::SharedPtr handle;
    bool done = false;
    rclcpp_action::ResultCode code = rclcpp_action::ResultCode::UNKNOWN;
    rclcpp_action::Client<ExecuteMission>::SendGoalOptions options;
    options.goal_response_callback = [&handle](const auto & h) { handle = h; };
    options.result_callback = [&](const auto & r) {
      code = r.code;
      done = true;
    };
    client->async_send_goal(standard_goal(), options);
    if (!spin_until(
          [&] { return handle != nullptr && held != nullptr; }, std::chrono::seconds(10),
          nullptr)) {
      return rclcpp_action::ResultCode::UNKNOWN;
    }
    client->async_cancel_goal(handle);
    if (!spin_until([&] { return held->is_canceling(); }, std::chrono::seconds(10), nullptr)) {
      return rclcpp_action::ResultCode::UNKNOWN;
    }
    if (succeed) {
      held->succeed(std::make_shared<ExecuteMission::Result>());
    } else {
      held->abort(std::make_shared<ExecuteMission::Result>());
    }
    spin_until([&] { return done; }, std::chrono::seconds(10), nullptr);
    return code;
  }
};

TEST_F(CanceledGoalEndTest, AbortIsAllowed)
{
  EXPECT_EQ(end_canceled_goal(false), rclcpp_action::ResultCode::ABORTED);
}

TEST_F(CanceledGoalEndTest, SucceedIsAllowed)
{
  EXPECT_EQ(end_canceled_goal(true), rclcpp_action::ResultCode::SUCCEEDED);
}

// ---- P3d 검토 보완 ----

TEST_F(ExecutorNodeTest, CancelInPreparingIsCanceled)
{
  // test-engineer N1: PX4 표본 없이 PREPARING(P0)에 둔 goal을 취소하면 바로 CANCELED,
  // REASON_NONE이고 CANCELED 종료 사건이 result와 같다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), nullptr));
  client.send(standard_goal());
  ASSERT_TRUE(spin_until(
    [&] { return node->goal_active() && client.handle_ != nullptr; }, std::chrono::seconds(10),
    nullptr));
  client.client()->async_cancel_goal(client.handle_);
  ASSERT_TRUE(spin_until(
    [&] { return client.has_result_ && client.events().size() >= 2; }, std::chrono::seconds(10),
    nullptr));
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::CANCELED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_NONE);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_CANCELED);
  EXPECT_FALSE(node->goal_active());
}

TEST_F(ExecutorNodeTest, SecondGoalIsBusy)
{
  // 실행 중에 온 두 번째 goal: ACCEPTED 사건 뒤 즉시 ABORTED, REASON_BUSY. 첫 goal은 계속된다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client first(test_node);
  Client second(test_node);
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return second.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), nullptr));
  first.send(standard_goal());
  ASSERT_TRUE(spin_until([&] { return node->goal_active(); }, std::chrono::seconds(10), nullptr));
  second.send(standard_goal());
  ASSERT_TRUE(spin_until(
    [&] { return second.has_result_ && second.events().size() >= 3; }, std::chrono::seconds(10),
    nullptr));
  EXPECT_EQ(second.result_.code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(second.result_.result->reason, ExecuteMission::Result::REASON_BUSY);
  EXPECT_EQ(second.feedback_, 0);
  EXPECT_FALSE(first.has_result_);
  EXPECT_TRUE(node->goal_active());
  // 사건: 첫 goal ACCEPTED, 둘째 goal ACCEPTED, 둘째 goal ABORTED(BUSY) 순서.
  std::vector<MissionEvent> busy;
  for (const MissionEvent & e : second.events()) {
    if (e.goal_id == second.result_.goal_id) {
      busy.push_back(e);
    }
  }
  expect_events_match_result(busy, second.result_, MissionEvent::STATUS_ABORTED);
  const std::vector<MissionEvent> all = second.events();
  EXPECT_EQ(all[0].status, MissionEvent::STATUS_ACCEPTED);
  EXPECT_NE(all[0].goal_id, second.result_.goal_id);
}

class ShutdownDisarmTest : public ExecutorNodeTest
{
protected:
  // goal을 시작해 until이 참일 때 shutdown하고, 그 뒤 PX4가 받은 disarm 수와 detail을 본다.
  void run(
    bool react_offboard, const std::function<bool(const FakePx4 &)> & until, int expected_disarms,
    const char * expected_detail)
  {
    auto node = make_executor(true);
    auto test_node = std::make_shared<rclcpp::Node>("test_client");
    Client client(test_node);
    FakePx4 px4(test_node, *clock_);
    px4.react_offboard = react_offboard;
    executor_->add_node(node->get_node_base_interface());
    executor_->add_node(test_node);
    ASSERT_TRUE(spin_until(
      [&] {
        return client.client()->action_server_is_ready() &&
               test_node->count_publishers("/px4_1/mission_event") >= 1;
      },
      std::chrono::seconds(10), &px4));
    client.send(standard_goal());
    ASSERT_TRUE(spin_until([&] { return until(px4); }, std::chrono::seconds(20), &px4));
    ASSERT_TRUE(node->goal_active());
    const int before = px4.disarms();
    EXPECT_EQ(node->shutdown().id(), State::PRIMARY_STATE_FINALIZED);
    ASSERT_TRUE(spin_until(
      [&] { return client.has_result_ && client.events().size() >= 2; }, std::chrono::seconds(10),
      &px4));
    spin_count(50);
    EXPECT_EQ(px4.disarms() - before, expected_disarms);
    EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_INTERNAL);
    if (expected_detail != nullptr) {
      EXPECT_NE(client.result_.result->detail.find(expected_detail), std::string::npos)
        << client.result_.result->detail;
    } else {
      EXPECT_EQ(client.result_.result->detail.find("disarm"), std::string::npos)
        << client.result_.result->detail;
    }
    expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_ABORTED);
  }
};

TEST_F(ShutdownDisarmTest, AfterArmSendsOneDisarm)
{
  // px4-engineer P3d-1: arm을 보낸 뒤의 종료는 강제가 아닌 disarm을 정확히 한 번 보낸다.
  run(true, [](const FakePx4 & px4) { return px4.armed(); }, 1, "may remain armed");
}

TEST_F(ShutdownDisarmTest, BeforeArmSendsNoDisarm)
{
  // P3-P5(arm 전)의 종료는 disarm을 보내지 않는다.
  run(false, [](const FakePx4 & px4) { return px4.offboards() >= 1; }, 0, nullptr);
}

}  // namespace
}  // namespace idsim_mission::test
