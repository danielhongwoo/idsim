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

// PX4 어댑터 출력 쪽: StepOutput -> px4_msgs, 그리고 RosPx4ClockPort. 노드와 DDS 참가자를
// 만들지 않는다. Px4Timestamp는 rclcpp::Clock과 rcl의 ROS 시간 override로 만든다(idsim_common의
// test_px4_timestamp.cpp와 같은 방법).

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>
#include <vector>

#include "idsim_common/px4_timestamp.hpp"
#include "idsim_common/vehicle.hpp"
#include "idsim_common/vehicle_command.hpp"
#include "idsim_mission/core/mission_runner.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/px4/clock_port.hpp"
#include "idsim_mission/px4/outputs.hpp"
#include "rcl/time.h"
#include "rclcpp/clock.hpp"

namespace idsim_mission::px4::test
{
namespace
{

using core::CommandKind;
using core::SetpointKind;
using core::SetpointOut;
using core::StepOutput;
using idsim_common::Px4Timestamp;
using px4_msgs::msg::VehicleCommand;

constexpr std::uint64_t kStampUs = 42'000'123;
constexpr double kPi = 3.14159265358979323846;
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kInf = std::numeric_limits<double>::infinity();

void set_ros_time(rclcpp::Clock & clock, std::uint64_t us)
{
  if (
    rcl_enable_ros_time_override(clock.get_clock_handle()) != RCL_RET_OK ||
    rcl_set_ros_time_override(
      clock.get_clock_handle(), static_cast<rcl_time_point_value_t>(us) * 1000) != RCL_RET_OK) {
    throw std::runtime_error("cannot set ROS time override");
  }
}

Px4Timestamp stamp_at(std::uint64_t us)
{
  rclcpp::Clock clock(RCL_ROS_TIME);
  set_ros_time(clock, us);
  return Px4Timestamp::now(clock).value();
}

idsim_common::VehicleCommandBuilder builder()
{
  return idsim_common::VehicleCommandBuilder::make(
           idsim_common::VehicleIdentity{
             idsim_common::VehicleNamespace::parse("/px4_1").value(),
             idsim_common::SystemId::make(2).value()},
           idsim_common::CommandSource::make(254, 1).value())
    .value();
}

SetpointOut setpoint(SetpointKind kind, double x, double y, double z, double yaw)
{
  SetpointOut sp;
  sp.kind = kind;
  sp.x = x;
  sp.y = y;
  sp.z = z;
  sp.yaw_ned = yaw;
  return sp;
}

bool same_float(double a, double b) { return (std::isnan(a) && std::isnan(b)) || a == b; }

// VehicleCommand의 모든 필드를 NaN을 같게 보고 비교한다(land의 param4-7이 NaN이라 ==를 못 쓴다).
void expect_same_command(const VehicleCommand & a, const VehicleCommand & b)
{
  EXPECT_EQ(a.timestamp, b.timestamp);
  EXPECT_EQ(a.command, b.command);
  EXPECT_TRUE(same_float(a.param1, b.param1));
  EXPECT_TRUE(same_float(a.param2, b.param2));
  EXPECT_TRUE(same_float(a.param3, b.param3));
  EXPECT_TRUE(same_float(a.param4, b.param4));
  EXPECT_TRUE(same_float(a.param5, b.param5));
  EXPECT_TRUE(same_float(a.param6, b.param6));
  EXPECT_TRUE(same_float(a.param7, b.param7));
  EXPECT_EQ(a.target_system, b.target_system);
  EXPECT_EQ(a.target_component, b.target_component);
  EXPECT_EQ(a.source_system, b.source_system);
  EXPECT_EQ(a.source_component, b.source_component);
  EXPECT_EQ(a.confirmation, b.confirmation);
  EXPECT_EQ(a.from_external, b.from_external);
}

// ---- 지상 오프셋 ----

TEST(Px4Outputs, GroundOffsetConstant) { EXPECT_DOUBLE_EQ(kGroundSetpointOffsetDownM, 0.5); }

TEST(Px4Outputs, GroundOffsetOnlyForGroundKind)
{
  const SetpointOut target = setpoint(SetpointKind::kTarget, 1.0, 2.0, -0.2, 0.3);
  const SetpointOut t = apply_ground_offset(target);
  EXPECT_DOUBLE_EQ(t.z, -0.2);
  EXPECT_DOUBLE_EQ(t.x, 1.0);
  EXPECT_DOUBLE_EQ(t.y, 2.0);
  EXPECT_DOUBLE_EQ(t.yaw_ned, 0.3);

  const SetpointOut ground = setpoint(SetpointKind::kGround, 1.0, 2.0, -0.2, 0.3);
  const SetpointOut g = apply_ground_offset(ground);
  EXPECT_DOUBLE_EQ(g.z, -0.2 + 0.5);  // NED +z = 아래쪽
  EXPECT_DOUBLE_EQ(g.x, 1.0);
  EXPECT_DOUBLE_EQ(g.y, 2.0);
  EXPECT_DOUBLE_EQ(g.yaw_ned, 0.3);
}

TEST(Px4Outputs, GroundSetpointMessageCarriesOffset)
{
  const auto msgs =
    to_setpoint_messages(setpoint(SetpointKind::kGround, 3.0, -4.0, -0.1, 1.0), stamp_at(kStampUs));
  ASSERT_TRUE(msgs.has_value());
  EXPECT_FLOAT_EQ(msgs->trajectory.position[2], static_cast<float>(-0.1 + 0.5));
  EXPECT_FLOAT_EQ(msgs->trajectory.position[0], 3.0F);
  EXPECT_FLOAT_EQ(msgs->trajectory.position[1], -4.0F);
}

// ---- setpoint 짝 ----

TEST(Px4Outputs, TargetSetpointMessages)
{
  const auto msgs = to_setpoint_messages(
    setpoint(SetpointKind::kTarget, 1.0, 2.0, -5.0, -1.25), stamp_at(kStampUs));
  ASSERT_TRUE(msgs.has_value());
  const auto & mode = msgs->mode;
  EXPECT_EQ(mode.timestamp, kStampUs);
  EXPECT_TRUE(mode.position);
  EXPECT_FALSE(mode.velocity);
  EXPECT_FALSE(mode.acceleration);
  EXPECT_FALSE(mode.attitude);
  EXPECT_FALSE(mode.body_rate);
  EXPECT_FALSE(mode.thrust_and_torque);
  EXPECT_FALSE(mode.direct_actuator);

  const auto & tr = msgs->trajectory;
  EXPECT_EQ(tr.timestamp, kStampUs);
  EXPECT_FLOAT_EQ(tr.position[0], 1.0F);
  EXPECT_FLOAT_EQ(tr.position[1], 2.0F);
  EXPECT_FLOAT_EQ(tr.position[2], -5.0F);
  EXPECT_FLOAT_EQ(tr.yaw, -1.25F);
  for (const float v : tr.velocity) {
    EXPECT_TRUE(std::isnan(v));
  }
  EXPECT_TRUE(std::isnan(tr.yawspeed));
}

TEST(Px4Outputs, YawIsWrappedToMinusPiPi)
{
  // core는 [-pi, pi)로 주지만, 범위 밖 값이 와도 PX4에는 감은 값이 간다.
  const auto msgs = to_setpoint_messages(
    setpoint(SetpointKind::kTarget, 0.0, 0.0, -1.0, 1.5 * kPi), stamp_at(kStampUs));
  ASSERT_TRUE(msgs.has_value());
  EXPECT_NEAR(msgs->trajectory.yaw, -0.5 * kPi, 1e-6);
}

TEST(Px4Outputs, NonFiniteSetpointIsRejected)
{
  const Px4Timestamp ts = stamp_at(kStampUs);
  for (const double bad : {kNaN, kInf, -kInf}) {
    EXPECT_FALSE(to_setpoint_messages(setpoint(SetpointKind::kTarget, bad, 0, -1, 0), ts));
    EXPECT_FALSE(to_setpoint_messages(setpoint(SetpointKind::kTarget, 0, bad, -1, 0), ts));
    EXPECT_FALSE(to_setpoint_messages(setpoint(SetpointKind::kTarget, 0, 0, bad, 0), ts));
    EXPECT_FALSE(to_setpoint_messages(setpoint(SetpointKind::kTarget, 0, 0, -1, bad), ts));
    EXPECT_FALSE(to_setpoint_messages(setpoint(SetpointKind::kGround, 0, 0, bad, 0), ts));
  }
}

// ---- 명령 대응 ----

TEST(Px4Outputs, CommandKindMapsToBuilderMethod)
{
  const auto b = builder();
  const Px4Timestamp ts = stamp_at(kStampUs);
  expect_same_command(
    to_vehicle_command(CommandKind::kSetModeOffboard, b, ts), b.set_mode_offboard(ts));
  expect_same_command(to_vehicle_command(CommandKind::kSetModeHold, b, ts), b.set_mode_hold(ts));
  expect_same_command(to_vehicle_command(CommandKind::kArm, b, ts), b.arm(ts));
  expect_same_command(to_vehicle_command(CommandKind::kDisarm, b, ts), b.disarm(ts));
  expect_same_command(to_vehicle_command(CommandKind::kNavLand, b, ts), b.land(ts));
}

TEST(Px4Outputs, CommandKindFieldsAndAckGroup)
{
  const auto b = builder();
  const Px4Timestamp ts = stamp_at(kStampUs);
  struct Row
  {
    CommandKind kind;
    std::uint32_t command;
  };
  const Row rows[] = {
    {CommandKind::kSetModeOffboard, VehicleCommand::VEHICLE_CMD_DO_SET_MODE},
    {CommandKind::kSetModeHold, VehicleCommand::VEHICLE_CMD_DO_SET_MODE},
    {CommandKind::kArm, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM},
    {CommandKind::kDisarm, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM},
    {CommandKind::kNavLand, VehicleCommand::VEHICLE_CMD_NAV_LAND},
  };
  for (const Row & row : rows) {
    const VehicleCommand cmd = to_vehicle_command(row.kind, b, ts);
    EXPECT_EQ(cmd.command, row.command) << core::command_name(row.kind);
    EXPECT_EQ(cmd.timestamp, kStampUs);
    EXPECT_EQ(cmd.target_system, 2);
    EXPECT_EQ(cmd.source_system, 254);
    EXPECT_EQ(cmd.source_component, 1);
  }
}

TEST(Px4Outputs, DisarmIsNotForced)
{
  const VehicleCommand cmd =
    to_vehicle_command(CommandKind::kDisarm, builder(), stamp_at(kStampUs));
  EXPECT_FLOAT_EQ(cmd.param1, 0.0F);
  // 강제 disarm은 param2 = 21196이다. 쓰지 않는다.
  EXPECT_FLOAT_EQ(cmd.param2, 0.0F);
}

TEST(Px4Outputs, ArmIsNotForced)
{
  const VehicleCommand cmd = to_vehicle_command(CommandKind::kArm, builder(), stamp_at(kStampUs));
  EXPECT_FLOAT_EQ(cmd.param1, 1.0F);
  EXPECT_FLOAT_EQ(cmd.param2, 0.0F);
}

// ---- StepOutput 하나 ----

TEST(Px4Outputs, EmptyStepOutputNeedsNoStamp)
{
  const Px4Messages msgs = to_px4_messages(StepOutput{}, builder(), std::nullopt);
  EXPECT_FALSE(msgs.setpoint.has_value());
  EXPECT_TRUE(msgs.commands.empty());
  EXPECT_TRUE(msgs.error.empty());
}

TEST(Px4Outputs, SetpointAndCommandsInOrder)
{
  StepOutput out;
  out.px4_timestamp_us = kStampUs;
  out.setpoint = setpoint(SetpointKind::kTarget, 0, 0, -2, 0);
  out.commands = {CommandKind::kSetModeHold, CommandKind::kDisarm};
  const Px4Messages msgs = to_px4_messages(out, builder(), stamp_at(kStampUs));
  EXPECT_TRUE(msgs.error.empty()) << msgs.error;
  ASSERT_TRUE(msgs.setpoint.has_value());
  EXPECT_EQ(msgs.setpoint->mode.timestamp, kStampUs);
  EXPECT_EQ(msgs.setpoint->trajectory.timestamp, kStampUs);
  ASSERT_EQ(msgs.commands.size(), 2U);
  EXPECT_EQ(msgs.commands[0].command, VehicleCommand::VEHICLE_CMD_DO_SET_MODE);
  EXPECT_EQ(msgs.commands[1].command, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM);
  for (const auto & cmd : msgs.commands) {
    EXPECT_EQ(cmd.timestamp, kStampUs);
  }
}

TEST(Px4Outputs, MissingStampDropsEverything)
{
  StepOutput out;
  out.px4_timestamp_us = kStampUs;
  out.setpoint = setpoint(SetpointKind::kTarget, 0, 0, -2, 0);
  out.commands = {CommandKind::kArm};
  const Px4Messages msgs = to_px4_messages(out, builder(), std::nullopt);
  EXPECT_FALSE(msgs.setpoint.has_value());
  EXPECT_TRUE(msgs.commands.empty());
  EXPECT_FALSE(msgs.error.empty());
}

TEST(Px4Outputs, MissingPx4TimestampInOutputDropsEverything)
{
  StepOutput out;
  out.commands = {CommandKind::kArm};
  const Px4Messages msgs = to_px4_messages(out, builder(), stamp_at(kStampUs));
  EXPECT_TRUE(msgs.commands.empty());
  EXPECT_FALSE(msgs.error.empty());
}

TEST(Px4Outputs, StampMismatchDropsEverything)
{
  StepOutput out;
  out.px4_timestamp_us = kStampUs;
  out.setpoint = setpoint(SetpointKind::kTarget, 0, 0, -2, 0);
  out.commands = {CommandKind::kArm};
  const Px4Messages msgs = to_px4_messages(out, builder(), stamp_at(kStampUs + 50'000));
  EXPECT_FALSE(msgs.setpoint.has_value());
  EXPECT_TRUE(msgs.commands.empty());
  EXPECT_FALSE(msgs.error.empty());
}

TEST(Px4Outputs, NaNSetpointDropsPairButKeepsCommands)
{
  StepOutput out;
  out.px4_timestamp_us = kStampUs;
  out.setpoint = setpoint(SetpointKind::kGround, kNaN, 0, -2, 0);
  out.commands = {CommandKind::kDisarm};
  const Px4Messages msgs = to_px4_messages(out, builder(), stamp_at(kStampUs));
  EXPECT_FALSE(msgs.setpoint.has_value());
  ASSERT_EQ(msgs.commands.size(), 1U);
  EXPECT_EQ(msgs.commands[0].command, VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM);
  EXPECT_FALSE(msgs.error.empty());
}

// ---- RosPx4ClockPort ----

TEST(Px4ClockPort, SimTimeGivesStampAndKeepsIt)
{
  rclcpp::Clock clock(RCL_ROS_TIME);
  set_ros_time(clock, kStampUs);
  RosPx4ClockPort port(clock);
  port.begin_tick();
  EXPECT_FALSE(port.stamp().has_value());
  const std::optional<std::uint64_t> us = port.now_us();
  ASSERT_TRUE(us.has_value());
  EXPECT_EQ(*us, kStampUs);
  ASSERT_TRUE(port.stamp().has_value());
  EXPECT_EQ(port.stamp()->microseconds(), kStampUs);

  port.begin_tick();
  EXPECT_FALSE(port.stamp().has_value()) << "begin_tick clears the previous tick's stamp";
}

TEST(Px4ClockPort, FailureClearsStamp)
{
  rclcpp::Clock clock(RCL_ROS_TIME);
  set_ros_time(clock, kStampUs);
  RosPx4ClockPort port(clock);
  ASSERT_TRUE(port.now_us().has_value());
  // /clock이 끊겨 override가 꺼진 것처럼: ROS 시계가 벽시계로 돌아가면 실패한다.
  ASSERT_EQ(rcl_disable_ros_time_override(clock.get_clock_handle()), RCL_RET_OK);
  EXPECT_FALSE(port.now_us().has_value());
  EXPECT_FALSE(port.stamp().has_value());
}

TEST(Px4ClockPort, NonSimClockFails)
{
  rclcpp::Clock system_clock(RCL_SYSTEM_TIME);
  RosPx4ClockPort port(system_clock);
  EXPECT_FALSE(port.now_us().has_value());
  EXPECT_FALSE(port.stamp().has_value());
}

TEST(Px4ClockPort, StampFeedsOutputs)
{
  // 노드의 tick 순서 그대로: begin_tick -> (core가 now_us) -> to_px4_messages(stamp()).
  rclcpp::Clock clock(RCL_ROS_TIME);
  set_ros_time(clock, kStampUs);
  RosPx4ClockPort port(clock);
  port.begin_tick();
  core::Px4ClockPort & as_core = port;
  StepOutput out;
  out.px4_timestamp_us = as_core.now_us();
  out.commands = {CommandKind::kSetModeOffboard};
  const Px4Messages msgs = to_px4_messages(out, builder(), port.stamp());
  EXPECT_TRUE(msgs.error.empty()) << msgs.error;
  ASSERT_EQ(msgs.commands.size(), 1U);
  EXPECT_EQ(msgs.commands[0].timestamp, kStampUs);
}

}  // namespace
}  // namespace idsim_mission::px4::test
