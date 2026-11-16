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

// 노드 껍질의 배선 테스트(PX4 없이, 한 프로세스). docs/interface.md "ExecuteMission", "계약 토픽
// QoS".
// - lifecycle.self_start 대조군 쌍: 같은 spin 횟수에서 true는 active, false는 unconfigured.
// - 직접 건 configure, activate. params 누락(vehicle.*, world.origin.*), world.origin 범위 밖,
//   use_sim_time false, target_fresh_age >= target_timeout의 configure 실패.
// - goal 실행 중 deactivate 거부, on_shutdown이 실행 중 goal을 ABORTED, REASON_INTERNAL로 끝내고
//   종료 사건을 낸다.
// - 배선: 가짜 PX4 발행자로 정상 한 경로(TAKEOFF, LOITER, LAND -> SUCCEEDED)와 무효 한 경로
//   (무효 사례인 TRACK_ENTITY의 0 offset -> INVALID_MISSION. tests/sitl/README.md "시나리오와
//   판정"). 사건은 ACCEPTED가 앞이고 종료 사건은 1건이며 result와 같은 값.
// - 좌표: world.origin과 같은 기준을 내는 가짜 PX4에서 GOTO의 world ENU 점이 로컬 NED setpoint로
//   나간다(진짜 Px4FramePort 배선).
// - target_timeout, target_fresh_age를 주지 않으면 core 기본값(1.0 s, 0.1 s)이다.
// - TARGET_LOST: 표적 표본을 끊으면 TRACK_ENTITY가 TARGET_LOST로 끝나고, Hold를 보낸 뒤 Hold가
//   관측될 때까지 setpoint 발행이 이어지며 관측 뒤에는 멈춘다(가짜 PX4가 Hold 반영을 늦춘다).
// - 표적 구독 수명: goal 접수 때 TRACK_ENTITY target_id마다 /targets/<id>/state 구독이 생기고
//   goal이 끝나면 없어진다. 다음 goal 접수 때 Snapshot.targets만 비고 status와 land는 남는다.
// - rclcpp_action에서 cancel을 받아들인 goal을 abort로 끝낼 수 있는지(docs/interface.md "종료의
//   충돌 규칙"의 rclcpp_action 허용 확인).
// - PREPARING 중 취소의 CANCELED, 실행 중 두 번째 goal의 BUSY, 종료 때의 disarm 한 번(arm 뒤 1개,
//   arm 전 0개).
// - 전체 취소(goal id 미지정, async_cancel_all_goals): 실행 중 goal은 handle_cancel을 거쳐 취소
//   분기(공중 -> Hold)로 CANCELED가 되고, 실행 중 goal이 없으면 아무 일도 일어나지 않는다.
// 시계: 별도 thread가 /clock을 발행한다(on_activate의 2 s 대기는 파라미터가 아니다). 사건 구독은
// action client보다 먼저, 같은 노드에서 만든다(docs/interface.md "MissionEvent").

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "action_msgs/srv/cancel_goal.hpp"
#include "idsim_common/contract_qos.hpp"
#include "idsim_common/px4_io.hpp"
#include "idsim_common/qos.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_interfaces/msg/target_state.hpp"
#include "idsim_mission/node/mission_executor_node.hpp"
#include "lifecycle_msgs/msg/state.hpp"
#include "px4_msgs/msg/failsafe_flags.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/vehicle_command_ack.hpp"
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
// 노드 테스트의 world.origin(config/fleet.yaml의 기본 원점과 같은 값).
constexpr double kOriginLat = 37.5665;
constexpr double kOriginLon = 126.9780;
constexpr double kOriginAlt = 38.0;

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

std::vector<rclcpp::Parameter> origin_params()
{
  return {
    rclcpp::Parameter(kParamOriginLat, kOriginLat),
    rclcpp::Parameter(kParamOriginLon, kOriginLon),
    rclcpp::Parameter(kParamOriginAlt, kOriginAlt),
  };
}

// origin은 world.origin.* 값들이다(기본은 origin_params()). extra는 그 밖에 더할 파라미터다.
std::shared_ptr<MissionExecutorNode> make_executor(
  bool self_start, bool with_vehicle = true, bool use_sim_time = true,
  const std::string & name = "mission_executor",
  const std::vector<rclcpp::Parameter> & origin = origin_params(),
  const std::vector<rclcpp::Parameter> & extra = {})
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
  params.insert(params.end(), origin.begin(), origin.end());
  params.insert(params.end(), extra.begin(), extra.end());
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
// Offboard 전환(DO_SET_MODE, param2 6)에 반응할 때는 ACCEPTED ack도 낸다(target은 명령의 source).
// 지상 arm 진입은 그 ack가 있어야 arm을 보낸다(docs/interface.md "준비 단계").
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
    ack_ = node->create_publisher<px4_msgs::msg::VehicleCommandAck>(
      idsim_common::px4::topic_name<topics::VehicleCommandAck>(ns), qos);
    command_ = node->create_subscription<px4_msgs::msg::VehicleCommand>(
      idsim_common::px4::topic_name<topics::VehicleCommand>(ns), qos,
      [this](const px4_msgs::msg::VehicleCommand::ConstSharedPtr msg) { on_command(*msg); });
    setpoint_ = node->create_subscription<px4_msgs::msg::TrajectorySetpoint>(
      idsim_common::px4::topic_name<topics::TrajectorySetpoint>(ns), qos,
      [this](const px4_msgs::msg::TrajectorySetpoint::ConstSharedPtr msg) {
        got_setpoint_ = true;
        ++setpoints_;
        setpoint_x_ = msg->position[0];
        setpoint_y_ = msg->position[1];
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
    if (hold_due_ns_ != 0 && now >= hold_due_ns_ && nav_ != VS::NAVIGATION_STATE_AUTO_LOITER) {
      nav_ = VS::NAVIGATION_STATE_AUTO_LOITER;
      setpoints_at_hold_seen_ = setpoints_;
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
    if (global_ref) {
      // world.origin과 같은 기준(로컬 NED 원점 = world ENU 원점).
      pos.xy_global = true;
      pos.z_global = true;
      pos.ref_timestamp = 1000000;
      pos.ref_lat = kOriginLat;
      pos.ref_lon = kOriginLon;
      pos.ref_alt = static_cast<float>(kOriginAlt);
    }
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
  int holds() const { return holds_; }
  // 첫 Hold 명령의 timestamp(노드 시계, ns). 없으면 0.
  std::int64_t first_hold_stamp_ns() const { return first_hold_stamp_ns_; }
  bool landed() const { return landed_; }
  std::uint8_t nav_state() const { return nav_; }
  float setpoint_x() const { return setpoint_x_; }
  float setpoint_y() const { return setpoint_y_; }
  float setpoint_z() const { return setpoint_z_; }
  // true면 vehicle_local_position에 world.origin과 같은 전역 기준을 싣는다.
  bool global_ref{false};
  // 0보다 크면 Hold 명령을 이 시간(sim ns) 뒤에 반영한다.
  std::int64_t hold_delay_ns{0};
  int setpoints() const { return setpoints_; }
  int setpoints_at_hold_sent() const { return setpoints_at_hold_sent_; }
  int setpoints_at_hold_seen() const { return setpoints_at_hold_seen_; }
  bool react_offboard{
    true};  // false면 Offboard 요청에 반응하지 않고 ack도 내지 않는다(P5에 머문다)
  // true면 Offboard ack 뒤에 core가 모르는 command(DO_REPOSITION)의 ack도 같은 target으로 낸다.
  bool ack_other_command{false};

private:
  void on_command(const px4_msgs::msg::VehicleCommand & cmd)
  {
    using VC = px4_msgs::msg::VehicleCommand;
    using VS = px4_msgs::msg::VehicleStatus;
    ++commands_;
    if (cmd.command == VC::VEHICLE_CMD_COMPONENT_ARM_DISARM && cmd.param1 == 0.0F) {
      ++disarms_;
    }
    // Hold = AUTO(param2 4) + AUTO_LOITER(param3 3). 다른 AUTO sub mode는 세지 않는다.
    if (cmd.command == VC::VEHICLE_CMD_DO_SET_MODE && cmd.param2 == 4.0F && cmd.param3 == 3.0F) {
      ++holds_;
      if (first_hold_stamp_ns_ == 0) {
        // 노드가 명령에 실은 timestamp(us, 노드 시계). 가짜 PX4가 받은 때의 벽시계 지연은 들어가지
        // 않는다.
        first_hold_stamp_ns_ = static_cast<std::int64_t>(cmd.timestamp) * 1000;
      }
    }
    if (cmd.command == VC::VEHICLE_CMD_DO_SET_MODE && cmd.param2 == 6.0F) {
      ++offboards_;
      if (react_offboard) {
        nav_ = VS::NAVIGATION_STATE_OFFBOARD;
        px4_msgs::msg::VehicleCommandAck ack;
        ack.timestamp = static_cast<std::uint64_t>(clock_.now_ns() / 1000);
        ack.command = cmd.command;
        ack.result = px4_msgs::msg::VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED;
        ack.target_system = cmd.source_system;
        ack.target_component = cmd.source_component;
        ack_->publish(ack);
        if (ack_other_command) {
          ack.command = VC::VEHICLE_CMD_DO_REPOSITION;
          ack_->publish(ack);
        }
      }
    } else if (cmd.command == VC::VEHICLE_CMD_DO_SET_MODE && cmd.param2 == 4.0F) {
      if (hold_delay_ns <= 0) {
        nav_ = VS::NAVIGATION_STATE_AUTO_LOITER;
      } else if (hold_due_ns_ == 0) {
        // 첫 Hold 명령에서 hold_delay_ns 뒤에 AUTO_LOITER를 내기 시작한다(step).
        hold_due_ns_ = clock_.now_ns() + hold_delay_ns;
        setpoints_at_hold_sent_ = setpoints_;
      }
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
  rclcpp::Publisher<px4_msgs::msg::VehicleCommandAck>::SharedPtr ack_;
  rclcpp::Subscription<px4_msgs::msg::VehicleCommand>::SharedPtr command_;
  rclcpp::Subscription<px4_msgs::msg::TrajectorySetpoint>::SharedPtr setpoint_;
  std::uint8_t nav_{px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER};
  bool armed_{false};
  bool landed_{true};
  float z_{0.0F};
  float setpoint_x_{0.0F};
  float setpoint_y_{0.0F};
  float setpoint_z_{0.0F};
  bool got_setpoint_{false};
  int setpoints_{0};
  int setpoints_at_hold_sent_{-1};
  int setpoints_at_hold_seen_{-1};
  std::int64_t hold_due_ns_{0};
  std::int64_t land_start_ns_{0};
  std::int64_t last_publish_ns_{0};
  int commands_{0};
  int disarms_{0};
  int offboards_{0};
  int holds_{0};
  std::int64_t first_hold_stamp_ns_{0};
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

TEST_F(ExecutorNodeTest, ConfigureFailsWithoutValidWorldOrigin)
{
  struct Case
  {
    const char * name;
    std::vector<rclcpp::Parameter> origin;
    const char * expect;
  };
  const std::vector<Case> cases = {
    {"missing", {}, "world.origin.lat is not set"},
    {"alt missing",
     {rclcpp::Parameter(kParamOriginLat, kOriginLat),
      rclcpp::Parameter(kParamOriginLon, kOriginLon)},
     "world.origin.alt is not set"},
    {"lat out of range",
     {rclcpp::Parameter(kParamOriginLat, 90.5), rclcpp::Parameter(kParamOriginLon, kOriginLon),
      rclcpp::Parameter(kParamOriginAlt, kOriginAlt)},
     "world.origin.lat must be finite and in [-90, 90]"},
    {"lon out of range",
     {rclcpp::Parameter(kParamOriginLat, kOriginLat), rclcpp::Parameter(kParamOriginLon, -180.5),
      rclcpp::Parameter(kParamOriginAlt, kOriginAlt)},
     "world.origin.lon must be finite and in [-180, 180]"},
    {"alt not finite",
     {rclcpp::Parameter(kParamOriginLat, kOriginLat),
      rclcpp::Parameter(kParamOriginLon, kOriginLon),
      rclcpp::Parameter(kParamOriginAlt, std::nan(""))},
     "world.origin.alt must be finite"},
    {"lat not double",
     {rclcpp::Parameter(kParamOriginLat, 37), rclcpp::Parameter(kParamOriginLon, kOriginLon),
      rclcpp::Parameter(kParamOriginAlt, kOriginAlt)},
     "cannot declare world.origin"},
  };
  for (const Case & c : cases) {
    auto node = make_executor(false, true, true, "mission_executor", c.origin);
    EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_UNCONFIGURED) << c.name;
    EXPECT_NE(node->last_failure().find(c.expect), std::string::npos)
      << c.name << ": " << node->last_failure();
  }
  // 경계값은 받는다.
  auto edge = make_executor(
    false, true, true, "mission_executor",
    {rclcpp::Parameter(kParamOriginLat, -90.0), rclcpp::Parameter(kParamOriginLon, 180.0),
     rclcpp::Parameter(kParamOriginAlt, -10.0)});
  EXPECT_EQ(edge->configure().id(), State::PRIMARY_STATE_INACTIVE) << edge->last_failure();
}

TEST_F(ExecutorNodeTest, TargetParametersDefaultToCoreValues)
{
  // 파라미터를 주지 않으면 core/config.hpp의 기본값(target_timeout 1.0 s, target_fresh_age 0.1 s).
  auto node = make_executor(false);
  const core::Timeouts defaults;
  EXPECT_EQ(defaults.target_timeout_ns, 1000000000LL);
  EXPECT_EQ(defaults.target_fresh_age_ns, 100000000LL);
  EXPECT_EQ(node->get_parameter("target_timeout").as_double(), 1.0);
  EXPECT_EQ(node->get_parameter("target_fresh_age").as_double(), 0.1);
  EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_INACTIVE) << node->last_failure();
}

TEST_F(ExecutorNodeTest, ConfigureFailsWhenTargetFreshAgeIsNotShorterThanTimeout)
{
  auto node = make_executor(
    false, true, true, "mission_executor", origin_params(),
    {rclcpp::Parameter("target_fresh_age", 1.0), rclcpp::Parameter("target_timeout", 1.0)});
  EXPECT_EQ(node->configure().id(), State::PRIMARY_STATE_UNCONFIGURED);
  EXPECT_NE(node->last_failure().find("target_fresh_age"), std::string::npos)
    << node->last_failure();
}

// action client와 사건 구독. 구독을 client보다 먼저, 같은 노드에서 만든다(docs/interface.md
// "MissionEvent").
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
    options.feedback_callback =
      [this](GoalHandle::SharedPtr, const std::shared_ptr<const ExecuteMission::Feedback> & fb) {
        ++feedback_;
        feedbacks_.push_back(*fb);
        last_phase_ = fb->phase;
        last_item_ = fb->item_index;
        if (fb->phase == ExecuteMission::Feedback::PHASE_CANCELING) {
          ++canceling_feedback_;
        }
      };
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
  std::vector<ExecuteMission::Feedback> feedbacks_;
  std::uint8_t last_phase_{0};
  std::uint32_t last_item_{0};
  int canceling_feedback_{0};

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

TEST_F(ExecutorNodeTest, AckOfOtherCommandIsKeptWithoutBreakingTheGoal)
{
  // core가 모르는 command의 ack(AckCommand::kOther)도 묶음별 최신 하나로 둔다. 대기 중인 명령의
  // 묶음이 아니므로 core에는 가지 않고 goal은 그대로 끝난다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  px4.ack_other_command = true;
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
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::SUCCEEDED);
  EXPECT_EQ(state_of(node), State::PRIMARY_STATE_ACTIVE);
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
  // 무효 사례: TRACK_ENTITY의 0 offset(tests/sitl/README.md "시나리오와 판정" 시나리오 B).
  ExecuteMission::Goal goal = standard_goal();
  MissionItem track = item(MissionItem::TYPE_TRACK_ENTITY, 10);
  track.track_entity.target_id = "car_1";
  track.track_entity.acceptance_radius_m = 1.0;
  track.track_entity.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  goal.mission.items.insert(goal.mission.items.begin() + 1, track);
  client.send(goal);
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(10), nullptr));
  spin_until([&] { return client.events().size() >= 2; }, std::chrono::seconds(2), nullptr);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_INVALID_MISSION);
  EXPECT_EQ(
    client.result_.result->detail, "items[1].track_entity.offset must be finite and non-zero");
  EXPECT_EQ(client.feedback_, 0);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_ABORTED);
  EXPECT_EQ(client.events()[0].item_count, 4U);
  // 무효 미션에는 표적 구독을 만들지 않는다.
  EXPECT_TRUE(node->target_subscriptions().empty());
}

MissionItem goto_item(double east, double north, double up)
{
  MissionItem go = item(MissionItem::TYPE_GOTO, 60);
  go.go_to.position.x = east;
  go.go_to.position.y = north;
  go.go_to.position.z = up;
  go.go_to.acceptance_radius_m = 0.5;
  go.go_to.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  return go;
}

TEST_F(ExecutorNodeTest, GotoSetpointGoesThroughFramePort)
{
  // 기준이 world.origin과 같으므로 world ENU (3, 4, 5)는 로컬 NED 약 (4, 3, -5)다(원점에서 5 m 안의
  // 곡률 차는 1 mm보다 작다). 진짜 Px4FramePort가 아니면 GOTO setpoint가 나가지 않는다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  px4.global_ref = true;
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return state_of(node) == State::PRIMARY_STATE_ACTIVE &&
             client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), &px4));
  ExecuteMission::Goal goal = standard_goal();
  goal.mission.items = {
    goal.mission.items[0], goto_item(3.0, 4.0, 5.0), item(MissionItem::TYPE_LAND, 30)};
  client.send(goal);
  ASSERT_TRUE(spin_until(
    [&] {
      return std::fabs(px4.setpoint_x() - 4.0F) < 0.01F &&
             std::fabs(px4.setpoint_y() - 3.0F) < 0.01F;
    },
    std::chrono::seconds(40), &px4))
    << "setpoint " << px4.setpoint_x() << " " << px4.setpoint_y() << " " << px4.setpoint_z()
    << " item " << client.last_item_;
  EXPECT_NEAR(px4.setpoint_z(), -5.0F, 0.01F);
  EXPECT_EQ(client.last_item_, 1U);
  EXPECT_EQ(node->shutdown().id(), State::PRIMARY_STATE_FINALIZED);
}

TEST_F(ExecutorNodeTest, FeedbackIsPublishedOnTheTickTheLastSetpointItemCompletes)
{
  // [TAKEOFF, GOTO]. GOTO 목표는 가짜 PX4가 내는 위치(로컬 NED (1, 2, -5) = world ENU (2, 1, 5))라
  // 곧 완료되고 공중 종료 단계로 들어간다. 그 tick은 항목(1)과 phase(EXECUTING)가 그대로지만
  // 항목이 완료됐으므로 feedback이 바로 나간다. 종료 단계는 들어가는 tick에 Hold를 보내므로, 거리가
  // 없는 첫 항목 1 feedback의 stamp는 첫 Hold 명령의 timestamp와 같은 tick의 값이다(주기 feedback만
  // 있으면 최대 10 tick 늦다). 비교는 같은 tick 안의 두 노드 시계 읽기 차(보통 /clock 양자 하나)를
  // 보고, 가짜 PX4가 명령을 받은 때의 벽시계 지연은 들어가지 않는다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  px4.global_ref = true;
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return state_of(node) == State::PRIMARY_STATE_ACTIVE &&
             client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), &px4));
  ExecuteMission::Goal goal = standard_goal();
  goal.mission.items = {goal.mission.items[0], goto_item(2.0, 1.0, 5.0)};
  client.send(goal);
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(40), &px4))
    << "item " << client.last_item_ << " phase " << static_cast<int>(client.last_phase_);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::SUCCEEDED);
  EXPECT_EQ(client.result_.result->items_completed, 2U);
  ASSERT_GT(px4.first_hold_stamp_ns(), 0);
  // 항목 1에서 거리가 있던 feedback 뒤의 첫 거리 없는 feedback(종료 단계의 첫 feedback).
  const ExecuteMission::Feedback * end_stage = nullptr;
  bool seen_valid = false;
  for (const ExecuteMission::Feedback & fb : client.feedbacks_) {
    if (fb.item_index != 1U) {
      continue;
    }
    if (fb.distance_valid) {
      seen_valid = true;
    } else if (seen_valid) {
      end_stage = &fb;
      break;
    }
  }
  ASSERT_TRUE(seen_valid);
  ASSERT_NE(end_stage, nullptr);
  EXPECT_EQ(end_stage->phase, ExecuteMission::Feedback::PHASE_EXECUTING);
  const std::int64_t stamp_ns = rclcpp::Time(end_stage->stamp).nanoseconds();
  // feedback stamp는 그 tick의 input.now_ns, Hold timestamp는 같은 tick의 step 안에서
  // Px4Timestamp::now로 노드 시계를 따로 읽은 값이다. 그 차(보통 /clock 양자 하나)를 본다.
  // 다음 주기 tick의 feedback이면 차가 한 tick(50 ms) 가까이 되므로 반 tick을 경계로 둔다.
  const std::int64_t diff_ns = px4.first_hold_stamp_ns() - stamp_ns;
  EXPECT_LT(std::llabs(diff_ns), kTickPeriodNs / 2)
    << "feedback stamp " << stamp_ns << " hold timestamp " << px4.first_hold_stamp_ns();
}

TEST_F(ExecutorNodeTest, TargetLostKeepsPublishingUntilHoldIsObserved)
{
  // [TAKEOFF, TRACK_ENTITY car_1]. 표적은 기체에서 먼 곳(world (50, 50, 0))이라 완료되지 않는다.
  // TRACK_ENTITY 실행에 들어간 뒤 표적 발행을 끊으면 target_timeout(1 s) 뒤 TARGET_LOST이고 공중
  // 정리로 Hold를 보낸다. 가짜 PX4는 Hold를 1 s(sim) 늦게 반영한다. 그 동안 setpoint 발행이
  // 이어지고, Hold가 관측된 뒤에는 멈춘다.
  auto node = make_executor(true);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  px4.global_ref = true;
  px4.hold_delay_ns = 1000000000LL;
  auto target_pub = test_node->create_publisher<idsim_interfaces::msg::TargetState>(
    "/targets/car_1/state", idsim_common::state_pub_qos());
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      return state_of(node) == State::PRIMARY_STATE_ACTIVE &&
             client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1;
    },
    std::chrono::seconds(10), &px4));
  ExecuteMission::Goal goal = standard_goal();
  MissionItem track = item(MissionItem::TYPE_TRACK_ENTITY, 60);
  track.track_entity.target_id = "car_1";
  track.track_entity.offset.z = 5.0;
  track.track_entity.acceptance_radius_m = 0.5;
  track.track_entity.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  goal.mission.items = {goal.mission.items[0], track};
  client.send(goal);
  const auto publish_target = [&] {
    idsim_interfaces::msg::TargetState msg;
    msg.header.frame_id = idsim_interfaces::msg::TargetState::FRAME_ID;
    msg.header.stamp = rclcpp::Time(clock_->now_ns());
    msg.target_id = "car_1";
    msg.position.x = 50.0;
    msg.position.y = 50.0;
    target_pub->publish(msg);
  };
  ASSERT_TRUE(spin_until(
    [&] {
      publish_target();
      return client.last_item_ == 1U &&
             client.last_phase_ == ExecuteMission::Feedback::PHASE_EXECUTING && !px4.landed();
    },
    std::chrono::seconds(40), &px4))
    << "item " << client.last_item_ << " phase " << static_cast<int>(client.last_phase_);
  ASSERT_EQ(px4.holds(), 0);
  // 표본이 실제로 도착해 유효 표본으로 들어갔다(소실 원인이 "받은 적 없음"이 아니게).
  ASSERT_EQ(node->snapshot().targets.count("car_1"), 1U);
  // 표적 발행을 끊는다. result를 처음 본 때의 setpoint 수를 적는다.
  int at_result = -1;
  ASSERT_TRUE(spin_until(
    [&] {
      if (client.has_result_ && at_result < 0) {
        at_result = px4.setpoints();
      }
      return client.has_result_;
    },
    std::chrono::seconds(20), &px4));
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_TARGET_LOST);
  // 원인은 "끊긴 표본"이다(core/mission_runner.cpp의 TARGET_LOST detail 앞부분).
  EXPECT_EQ(
    client.result_.result->detail.find(
      "item 1 (TRACK_ENTITY) target 'car_1' lost: last valid sample older than target_timeout"),
    0U)
    << client.result_.result->detail;
  EXPECT_GE(px4.holds(), 1);
  ASSERT_GE(px4.setpoints_at_hold_sent(), 0);
  ASSERT_GE(px4.setpoints_at_hold_seen(), 0);
  // Hold 명령에서 Hold 반영까지 1 s(sim, tick 20개) 동안 발행이 이어졌다.
  EXPECT_GE(px4.setpoints_at_hold_seen() - px4.setpoints_at_hold_sent(), 10);
  // 가짜 PX4가 AUTO_LOITER를 내기 시작한 뒤에는 노드가 그 표본을 볼 때까지(표본 간격 20 ms와 tick
  // 50 ms. 많아야 tick 2-3개)만 발행하고 멈춘다. Hold 확인(3 표본)과 result까지 더 나가지 않는다.
  EXPECT_GE(at_result - px4.setpoints_at_hold_seen(), 0);
  EXPECT_LE(at_result - px4.setpoints_at_hold_seen(), 3)
    << "at_result " << at_result << " at_hold_seen " << px4.setpoints_at_hold_seen();
  EXPECT_FALSE(node->goal_active());
  EXPECT_TRUE(node->target_subscriptions().empty());
  // goal이 끝난 뒤에는 발행이 없다.
  spin_until([] { return false; }, std::chrono::seconds(1), &px4);
  const int after_result = px4.setpoints();
  spin_until([] { return false; }, std::chrono::seconds(1), &px4);
  EXPECT_EQ(px4.setpoints(), after_result);
}

TEST_F(ExecutorNodeTest, TargetSubscriptionLivesWithGoalAndOnlyTargetsAreCleared)
{
  // 준비 단계에 머물도록 Offboard에 반응하지 않는 가짜 PX4와 긴 timeout을 쓴다.
  const std::vector<rclcpp::Parameter> slow = {
    rclcpp::Parameter("ready_timeout", 1000.0),
    rclcpp::Parameter("offboard_signal_timeout", 1000.0),
    rclcpp::Parameter("mode_confirm_timeout", 1000.0),
    rclcpp::Parameter("link_timeout", 500.0),
  };
  auto node = make_executor(true, true, true, "mission_executor", origin_params(), slow);
  auto test_node = std::make_shared<rclcpp::Node>("test_client");
  Client client(test_node);
  FakePx4 px4(test_node, *clock_);
  px4.react_offboard = false;
  const std::string topic = "/targets/car_1/state";
  auto target_pub = test_node->create_publisher<idsim_interfaces::msg::TargetState>(
    topic, idsim_common::state_pub_qos());
  executor_->add_node(node->get_node_base_interface());
  executor_->add_node(test_node);
  ASSERT_TRUE(spin_until(
    [&] {
      const core::Snapshot snap = node->snapshot();
      return client.client()->action_server_is_ready() &&
             test_node->count_publishers("/px4_1/mission_event") >= 1 && snap.status.has_value() &&
             snap.land.has_value();
    },
    std::chrono::seconds(10), &px4));
  EXPECT_TRUE(node->target_subscriptions().empty());
  EXPECT_EQ(test_node->count_subscribers(topic), 0U);

  ExecuteMission::Goal goal = standard_goal();
  MissionItem track = item(MissionItem::TYPE_TRACK_ENTITY, 30);
  track.track_entity.target_id = "car_1";
  track.track_entity.offset.z = 5.0;
  track.track_entity.acceptance_radius_m = 1.0;
  track.track_entity.yaw.mode = idsim_interfaces::msg::YawSetpoint::MODE_KEEP;
  // 같은 표적이 두 번 나와도 구독은 하나다.
  goal.mission.items = {goal.mission.items[0], track, track, item(MissionItem::TYPE_LAND, 30)};
  client.send(goal);
  ASSERT_TRUE(spin_until(
    [&] { return node->goal_active() && client.handle_ != nullptr; }, std::chrono::seconds(10),
    &px4));
  EXPECT_EQ(node->target_subscriptions(), std::vector<std::string>{"car_1"});
  ASSERT_TRUE(spin_until(
    [&] { return test_node->count_subscribers(topic) == 1U; }, std::chrono::seconds(10), &px4));
  std::int32_t sec = 1;
  ASSERT_TRUE(spin_until(
    [&] {
      idsim_interfaces::msg::TargetState msg;
      msg.header.frame_id = idsim_interfaces::msg::TargetState::FRAME_ID;
      msg.header.stamp.sec = sec++;
      msg.target_id = "car_1";
      msg.position.x = 10.0;
      target_pub->publish(msg);
      return node->snapshot().targets.count("car_1") == 1;
    },
    std::chrono::seconds(10), &px4));

  client.client()->async_cancel_goal(client.handle_);
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(20), &px4));
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::CANCELED);
  EXPECT_TRUE(node->target_subscriptions().empty());
  EXPECT_TRUE(spin_until(
    [&] { return test_node->count_subscribers(topic) == 0U; }, std::chrono::seconds(10), &px4));

  // 다음 goal 접수: 표적 표본만 비고 PX4 표본은 남는다. 가짜 PX4는 더 발행하지 않는다(남은
  // status와 land는 접수 전에 받은 것이다).
  Client next(test_node);
  ASSERT_TRUE(spin_until(
    [&] { return next.client()->action_server_is_ready(); }, std::chrono::seconds(10), nullptr));
  ASSERT_EQ(node->snapshot().targets.count("car_1"), 1U);
  next.send(goal);
  ASSERT_TRUE(spin_until([&] { return node->goal_active(); }, std::chrono::seconds(10), nullptr));
  const core::Snapshot snap = node->snapshot();
  EXPECT_TRUE(snap.targets.empty());
  EXPECT_TRUE(snap.status.has_value());
  EXPECT_TRUE(snap.land.has_value());
  EXPECT_TRUE(snap.position.has_value());
  EXPECT_EQ(node->target_subscriptions(), std::vector<std::string>{"car_1"});
  EXPECT_EQ(node->shutdown().id(), State::PRIMARY_STATE_FINALIZED);
  EXPECT_TRUE(node->target_subscriptions().empty());
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

// ---- 준비 중 취소, 두 번째 goal, 종료 때 disarm ----

TEST_F(ExecutorNodeTest, CancelInPreparingIsCanceled)
{
  // PX4 표본 없이 PREPARING(P0)에 둔 goal을 취소하면 바로 CANCELED,
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
  // arm을 보낸 뒤의 종료는 강제가 아닌 disarm을 정확히 한 번 보낸다.
  run(true, [](const FakePx4 & px4) { return px4.armed(); }, 1, "may remain armed");
}

TEST_F(ShutdownDisarmTest, BeforeArmSendsNoDisarm)
{
  // P3-P5(arm 전)의 종료는 disarm을 보내지 않는다.
  run(false, [](const FakePx4 & px4) { return px4.offboards() >= 1; }, 0, nullptr);
}

// ---- 전체 취소(goal id 미지정) ----

class CancelAllTest : public ExecutorNodeTest
{
protected:
  using CancelResponse = action_msgs::srv::CancelGoal::Response;

  // async_cancel_all_goals를 보내고 응답이 올 때까지 spin한다. 응답이 없으면 nullptr.
  CancelResponse::SharedPtr cancel_all(Client & client, FakePx4 * px4)
  {
    CancelResponse::SharedPtr response;
    client.client()->async_cancel_all_goals(
      [&response](const CancelResponse::SharedPtr & r) { response = r; });
    spin_until([&] { return response != nullptr; }, std::chrono::seconds(10), px4);
    return response;
  }
};

TEST_F(CancelAllTest, RunningGoalIsCanceledThroughCancelBranch)
{
  // 공중의 LOITER 항목 중에 goal id 없이 전체 취소를 보낸다.
  // (a) 응답의 goals_canceling에 실행 중 goal이 들어 있다. rclcpp_action 서버는 전체 취소를
  //     goal마다 handle_cancel로 묻고 ACCEPT한 goal만 응답에 남기므로 handle_cancel이 불렸다.
  // (b) 그 뒤 PHASE_CANCELING feedback이 온다(tick이 is_canceling을 core의 취소 분기로 넘겼다).
  // (c) 공중 분기: Hold를 보내고 Hold 확인 뒤 CANCELED, REASON_NONE. disarm은 보내지 않고 기체는
  //     ARMED, landed false인 AUTO_LOITER에 남는다. 종료 사건은 result와 같다.
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
  // LOITER를 길게 두어 취소가 LAND 항목과 겹치지 않게 한다.
  ExecuteMission::Goal goal = standard_goal();
  goal.mission.items[1].loiter.duration.sec = 60;
  goal.mission.items[1].timeout.sec = 120;
  client.send(goal);
  ASSERT_TRUE(spin_until(
    [&] {
      return client.handle_ != nullptr && client.last_item_ == 1U &&
             client.last_phase_ == ExecuteMission::Feedback::PHASE_EXECUTING && !px4.landed();
    },
    std::chrono::seconds(40), &px4))
    << "item " << client.last_item_ << " phase " << static_cast<int>(client.last_phase_);
  ASSERT_TRUE(node->goal_active());
  ASSERT_EQ(client.canceling_feedback_, 0);
  ASSERT_EQ(px4.holds(), 0);
  const int disarms_before = px4.disarms();

  const CancelResponse::SharedPtr response = cancel_all(client, &px4);
  ASSERT_NE(response, nullptr);
  EXPECT_EQ(response->return_code, CancelResponse::ERROR_NONE);
  ASSERT_EQ(response->goals_canceling.size(), 1U);
  EXPECT_EQ(response->goals_canceling[0].goal_id.uuid, client.handle_->get_goal_id());

  ASSERT_TRUE(spin_until(
    [&] { return client.has_result_ && client.events().size() >= 2; }, std::chrono::seconds(20),
    &px4));
  EXPECT_GE(client.canceling_feedback_, 1);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::CANCELED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_NONE);
  EXPECT_EQ(client.result_.result->last_item_index, 1U);
  EXPECT_GE(px4.holds(), 1);
  EXPECT_EQ(px4.disarms() - disarms_before, 0);
  EXPECT_TRUE(px4.armed());
  EXPECT_FALSE(px4.landed());
  EXPECT_EQ(px4.nav_state(), px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_CANCELED);
  EXPECT_FALSE(node->goal_active());
}

TEST_F(CancelAllTest, WithoutRunningGoalDoesNothingAndNextGoalRuns)
{
  // 실행 중 goal이 없을 때의 전체 취소: 취소된 goal이 없고, 사건과 PX4 명령이 나가지 않는다.
  // 그 뒤에 보낸 goal은 정상 경로로 SUCCEEDED가 된다.
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

  const CancelResponse::SharedPtr response = cancel_all(client, &px4);
  ASSERT_NE(response, nullptr);
  EXPECT_TRUE(response->goals_canceling.empty());
  // 취소할 goal이 없으면 handle_cancel이 불리지 않고 응답은 ERROR_NONE에 빈 목록이다
  // (rclcpp_action은 대상 goal이 하나 이상인데 모두 거절됐을 때만 ERROR_REJECTED로 바꾼다).
  EXPECT_EQ(response->return_code, CancelResponse::ERROR_NONE);
  spin_count(50);
  EXPECT_FALSE(node->goal_active());
  EXPECT_TRUE(client.events().empty());
  EXPECT_EQ(px4.commands(), 0);

  client.send(standard_goal());
  ASSERT_TRUE(spin_until([&] { return client.has_result_; }, std::chrono::seconds(40), &px4))
    << "events " << client.events().size() << " commands " << px4.commands();
  spin_until([&] { return client.events().size() >= 2; }, std::chrono::seconds(2), &px4);
  EXPECT_EQ(client.result_.code, rclcpp_action::ResultCode::SUCCEEDED);
  EXPECT_EQ(client.result_.result->reason, ExecuteMission::Result::REASON_NONE);
  EXPECT_EQ(client.result_.result->items_completed, 3U);
  EXPECT_EQ(client.canceling_feedback_, 0);
  expect_events_match_result(client.events(), client.result_, MissionEvent::STATUS_SUCCEEDED);
  EXPECT_FALSE(node->goal_active());
}

}  // namespace
}  // namespace idsim_mission::test
