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

// Mission Executor 노드 껍질(lifecycle, 컴포넌트 idsim_mission::MissionExecutorNode).
// 결정: 1a 6단계 설계 결정(git 이력) 쟁점 2(실행 형태, 자기 전이), 쟁점 7
// (사건 QoS), 쟁점 10(타임아웃 파라미터). 구현 규칙은 패키지 README.md.
//
// - 상태기는 core::MissionRunner, PX4 변환은 px4/ 어댑터다. 이 노드는 구독, 발행, action 서버,
//   timer와 lifecycle만 맡는다.
// - 자기 전이: 생성자의 벽시계 일회 timer(0 ms)가 configure와 activate를 한 번씩 건다
//   (`lifecycle.self_start`, 기본 true, 읽기 전용). 실패하면 그 상태에 남고 고정 접두어
//   kStartFailedLogPrefix의 ERROR 로그 한 줄을 남긴다. 프로세스를 끝내지 않는다.
// - callback group은 MutuallyExclusive 하나에 PX4 구독, 20 Hz tick timer(노드 시계), action
//   서버를 모두 넣는다. goal 실행용 thread는 없다. context 종료 전 callback(다른 thread)과 겹칠 수
//   있어 goal 상태는 mutex로 지킨다.

#ifndef IDSIM_MISSION__NODE__MISSION_EXECUTOR_NODE_HPP_
#define IDSIM_MISSION__NODE__MISSION_EXECUTOR_NODE_HPP_

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include "idsim_common/vehicle_command.hpp"
#include "idsim_common/vehicle_params.hpp"
#include "idsim_interfaces/action/execute_mission.hpp"
#include "idsim_interfaces/msg/mission_event.hpp"
#include "idsim_mission/core/config.hpp"
#include "idsim_mission/core/mission_runner.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/node/conversion.hpp"
#include "idsim_mission/px4/clock_port.hpp"
#include "px4_msgs/msg/failsafe_flags.hpp"
#include "px4_msgs/msg/offboard_control_mode.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/vehicle_command_ack.hpp"
#include "px4_msgs/msg/vehicle_land_detected.hpp"
#include "px4_msgs/msg/vehicle_local_position.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "rclcpp_lifecycle/lifecycle_publisher.hpp"

namespace idsim_mission
{

// 자기 전이 실패 로그의 고정 접두어(devops-engineer가 grep한다).
inline constexpr const char * kStartFailedLogPrefix = "IDSIM_EXECUTOR_START_FAILED";

// 노드 파라미터 이름(생성기는 vehicle.*와 use_sim_time만 만든다. 나머지는 선언 기본값).
inline constexpr const char * kParamSelfStart = "lifecycle.self_start";
inline constexpr const char * kParamSourceSystem = "command_source.system";
inline constexpr const char * kParamSourceComponent = "command_source.component";

// 20 Hz tick(노드 시계).
inline constexpr std::int64_t kTickPeriodNs = 50000000LL;
// feedback 발행: phase나 항목이 바뀐 tick과 그 밖에는 10 tick(0.5 s)마다.
inline constexpr int kFeedbackEveryTicks = 10;
// on_activate의 첫 /clock 대기(벽시계 예외. 파라미터가 아니다).
inline constexpr std::int64_t kClockWaitNs = 2000000000LL;

class MissionExecutorNode : public rclcpp_lifecycle::LifecycleNode
{
public:
  using ExecuteMission = idsim_interfaces::action::ExecuteMission;
  using GoalHandle = rclcpp_action::ServerGoalHandle<ExecuteMission>;
  using CallbackReturn = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

  explicit MissionExecutorNode(const rclcpp::NodeOptions & options);
  ~MissionExecutorNode() override;

  MissionExecutorNode(const MissionExecutorNode &) = delete;
  MissionExecutorNode & operator=(const MissionExecutorNode &) = delete;
  MissionExecutorNode(MissionExecutorNode &&) = delete;
  MissionExecutorNode & operator=(MissionExecutorNode &&) = delete;

  CallbackReturn on_configure(const rclcpp_lifecycle::State & previous) override;
  CallbackReturn on_activate(const rclcpp_lifecycle::State & previous) override;
  CallbackReturn on_deactivate(const rclcpp_lifecycle::State & previous) override;
  CallbackReturn on_cleanup(const rclcpp_lifecycle::State & previous) override;
  CallbackReturn on_shutdown(const rclcpp_lifecycle::State & previous) override;
  CallbackReturn on_error(const rclcpp_lifecycle::State & previous) override;

  // 실행 중인 goal이 있는가(테스트와 진단용).
  bool goal_active() const;
  // 마지막 전이 실패의 이유(테스트와 진단용).
  std::string last_failure() const;

private:
  struct Publishers
  {
    rclcpp_lifecycle::LifecyclePublisher<px4_msgs::msg::OffboardControlMode>::SharedPtr mode;
    rclcpp_lifecycle::LifecyclePublisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr trajectory;
    rclcpp_lifecycle::LifecyclePublisher<px4_msgs::msg::VehicleCommand>::SharedPtr command;
    rclcpp_lifecycle::LifecyclePublisher<idsim_interfaces::msg::MissionEvent>::SharedPtr event;
  };
  struct Subscriptions
  {
    rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr status;
    rclcpp::Subscription<px4_msgs::msg::VehicleLandDetected>::SharedPtr land;
    rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr position;
    rclcpp::Subscription<px4_msgs::msg::FailsafeFlags>::SharedPtr flags;
    rclcpp::Subscription<px4_msgs::msg::VehicleCommandAck>::SharedPtr ack;
  };

  void self_start();
  CallbackReturn fail(const std::string & transition, const std::string & why);
  void declare_parameters();
  void create_entities(
    const idsim_common::VehicleParams & vehicle,
    const idsim_common::VehicleCommandBuilder & builder);
  void on_tick();
  rclcpp_action::GoalResponse handle_goal(
    const rclcpp_action::GoalUUID & uuid, const std::shared_ptr<const ExecuteMission::Goal> & goal);
  rclcpp_action::CancelResponse handle_cancel(const std::shared_ptr<GoalHandle> & goal_handle);
  void handle_accepted(const std::shared_ptr<GoalHandle> & goal_handle);
  // 종료 결과 하나로 사건과 result를 낸다. 사건의 stamp는 stamp(tick에서 정한 종료이면 그 tick의
  // 입력 시각). 호출자가 mutex를 잡고 있다.
  void finish(
    const std::shared_ptr<GoalHandle> & goal_handle, EventContext context,
    const core::Termination & term, const builtin_interfaces::msg::Time & stamp);
  // 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝낸다(종료, 오류). 호출자가 mutex를 잡고 있다.
  void abort_running_goal(const std::string & why);
  void select_ack();
  builtin_interfaces::msg::Time stamp_now();

  mutable std::mutex mutex_;
  std::optional<idsim_common::VehicleParams> vehicle_;
  std::string vehicle_error_;
  std::string vehicle_id_;
  std::string last_failure_;
  core::Config config_;
  std::optional<idsim_common::VehicleCommandBuilder> builder_;
  rclcpp::TimerBase::SharedPtr self_start_timer_;
  rclcpp::CallbackGroup::SharedPtr group_;
  Publishers pubs_;
  Subscriptions subs_;
  rclcpp::TimerBase::SharedPtr tick_timer_;
  rclcpp_action::Server<ExecuteMission>::SharedPtr action_server_;
  std::unique_ptr<px4::RosPx4ClockPort> clock_port_;
  std::optional<rclcpp::PreShutdownCallbackHandle> pre_shutdown_;

  core::Snapshot snapshot_;
  // AckCommand별 최신 하나. 크기는 AckCommand 값의 수다(kOther가 마지막 값).
  std::array<std::optional<core::AckSample>, static_cast<std::size_t>(core::AckCommand::kOther) + 1>
    acks_;
  std::uint64_t next_tick_{1};
  std::unique_ptr<core::MissionRunner> runner_;
  std::shared_ptr<GoalHandle> goal_;
  EventContext goal_context_;
  int ticks_since_feedback_{0};
  std::uint32_t last_feedback_item_{0};
  std::uint8_t last_feedback_phase_{0};
  bool self_start_{true};
};

}  // namespace idsim_mission

#endif  // IDSIM_MISSION__NODE__MISSION_EXECUTOR_NODE_HPP_
