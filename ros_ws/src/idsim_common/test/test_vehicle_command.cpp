// VehicleCommand 빌더의 필드 표와 ack 매칭 술어.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 6. 필드 값은 opinion-px4.md P3 표.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>

#include "idsim_common/vehicle_command.hpp"
#include "rcl/time.h"
#include "rclcpp/clock.hpp"

using idsim_common::CommandSource;
using idsim_common::Px4Timestamp;
using idsim_common::VehicleCommandBuilder;
using px4_msgs::msg::VehicleCommand;
using px4_msgs::msg::VehicleCommandAck;

static_assert(!std::is_default_constructible_v<VehicleCommandBuilder>);
static_assert(!std::is_default_constructible_v<CommandSource>);
static_assert(!std::is_constructible_v<CommandSource, int, int>);

namespace
{

constexpr std::uint64_t kTimestampUs = 123'456'789;

Px4Timestamp timestamp()
{
  rclcpp::Clock clock(RCL_ROS_TIME);
  if (
    rcl_enable_ros_time_override(clock.get_clock_handle()) != RCL_RET_OK ||
    rcl_set_ros_time_override(
      clock.get_clock_handle(), static_cast<rcl_time_point_value_t>(kTimestampUs) * 1000) !=
      RCL_RET_OK) {
    throw std::runtime_error("cannot set ROS time override");
  }
  return Px4Timestamp::now(clock).value();
}

VehicleCommandBuilder builder()
{
  return VehicleCommandBuilder(
    idsim_common::VehicleIdentity{
      *idsim_common::VehicleNamespace::parse("/px4_1"), *idsim_common::SystemId::make(2)},
    *CommandSource::make(254, 1));
}

struct Expected
{
  std::uint32_t command;
  float param1;
  float param2;
  float param3;
  float param4;  // NaN이면 NaN을 기대한다
  double param5;
  double param6;
  float param7;
};

void expect_param(double actual, double expected, const char * name)
{
  if (std::isnan(expected)) {
    EXPECT_TRUE(std::isnan(actual)) << name << "=" << actual;
  } else {
    EXPECT_EQ(actual, expected) << name;
  }
}

void expect_command(const VehicleCommand & cmd, const Expected & e)
{
  EXPECT_EQ(cmd.command, e.command);
  expect_param(cmd.param1, e.param1, "param1");
  expect_param(cmd.param2, e.param2, "param2");
  expect_param(cmd.param3, e.param3, "param3");
  expect_param(cmd.param4, e.param4, "param4");
  expect_param(cmd.param5, e.param5, "param5");
  expect_param(cmd.param6, e.param6, "param6");
  expect_param(cmd.param7, e.param7, "param7");
  // 고정 필드
  EXPECT_EQ(cmd.timestamp, kTimestampUs);
  EXPECT_EQ(cmd.target_system, 2);
  EXPECT_EQ(cmd.target_component, 1);
  EXPECT_EQ(cmd.source_system, 254);
  EXPECT_EQ(cmd.source_component, 1);
  EXPECT_EQ(cmd.confirmation, 0);
  EXPECT_TRUE(cmd.from_external);
}

constexpr float kNaNf = std::numeric_limits<float>::quiet_NaN();
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

}  // namespace

TEST(VehicleCommandBuilder, FieldTable)
{
  const auto b = builder();
  const auto ts = timestamp();
  SCOPED_TRACE("arm");
  expect_command(b.arm(ts), {400, 1.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  SCOPED_TRACE("disarm");
  expect_command(b.disarm(ts), {400, 0.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  SCOPED_TRACE("set_mode_offboard");
  expect_command(b.set_mode_offboard(ts), {176, 1.0F, 6.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  SCOPED_TRACE("set_mode_hold");
  expect_command(b.set_mode_hold(ts), {176, 1.0F, 4.0F, 3.0F, 0.0F, 0.0, 0.0, 0.0F});
  SCOPED_TRACE("land");
  expect_command(b.land(ts), {21, 0.0F, 0.0F, 0.0F, kNaNf, kNaN, kNaN, kNaNf});
  SCOPED_TRACE("rtl");
  expect_command(b.rtl(ts), {20, 0.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
}

TEST(VehicleCommandBuilder, CommandIdsMatchPx4Msgs)
{
  EXPECT_EQ(VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, 400);
  EXPECT_EQ(VehicleCommand::VEHICLE_CMD_DO_SET_MODE, 176);
  EXPECT_EQ(VehicleCommand::VEHICLE_CMD_NAV_LAND, 21);
  EXPECT_EQ(VehicleCommand::VEHICLE_CMD_NAV_RETURN_TO_LAUNCH, 20);
  EXPECT_EQ(VehicleCommand::COMPONENT_MODE_EXECUTOR_START, 1000);
}

TEST(CommandSource, Range)
{
  EXPECT_TRUE(CommandSource::make(254, 1).has_value());
  EXPECT_TRUE(CommandSource::make(1, 999).has_value());
  EXPECT_TRUE(CommandSource::make(255, 1).has_value());
  // component 1000 이상은 PX4가 mode executor로 분류한다.
  EXPECT_FALSE(CommandSource::make(254, 1000).has_value());
  EXPECT_FALSE(CommandSource::make(254, 65535).has_value());
  EXPECT_FALSE(CommandSource::make(254, 0).has_value());
  EXPECT_FALSE(CommandSource::make(0, 1).has_value());
  EXPECT_FALSE(CommandSource::make(256, 1).has_value());
  const auto s = CommandSource::make(10, 999);
  ASSERT_TRUE(s.has_value());
  EXPECT_EQ(s->system(), 10);
  EXPECT_EQ(s->component(), 999);
}

TEST(VehicleCommandBuilder, IsAckFor)
{
  const auto cmd = builder().arm(timestamp());
  VehicleCommandAck ack;
  ack.command = cmd.command;
  ack.result = VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED;
  ack.target_system = cmd.source_system;
  ack.target_component = cmd.source_component;
  EXPECT_TRUE(idsim_common::is_ack_for(ack, cmd));

  // result는 술어에 들어가지 않는다(ACCEPTED가 성공을 뜻하지 않는다).
  auto denied = ack;
  denied.result = VehicleCommandAck::VEHICLE_CMD_RESULT_DENIED;
  EXPECT_TRUE(idsim_common::is_ack_for(denied, cmd));

  auto other_command = ack;
  other_command.command = VehicleCommand::VEHICLE_CMD_DO_SET_MODE;
  EXPECT_FALSE(idsim_common::is_ack_for(other_command, cmd));

  auto other_system = ack;
  other_system.target_system = 1;
  EXPECT_FALSE(idsim_common::is_ack_for(other_system, cmd));

  auto other_component = ack;
  other_component.target_component = 2;
  EXPECT_FALSE(idsim_common::is_ack_for(other_component, cmd));

  // check_px4.py(source 254/1)와 다른 송신자의 ack는 섞이지 않는다.
  const auto mission_cmd =
    VehicleCommandBuilder(builder().target(), *CommandSource::make(1, 191)).arm(timestamp());
  EXPECT_FALSE(idsim_common::is_ack_for(ack, mission_cmd));
}
