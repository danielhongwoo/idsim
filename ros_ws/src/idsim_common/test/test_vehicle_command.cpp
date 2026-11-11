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

// VehicleCommand 빌더의 필드 표와 ack 매칭 술어.
// 결정: 1a 4단계 idsim_common 설계 결정(git 이력) 쟁점 6.
// 필드 값은 px4-engineer 의견서(git 이력) P3 표.
// make의 source == target 거부: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 5.

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
// 공개 생성자가 없다. 만드는 길은 make 하나다.
static_assert(
  !std::is_constructible_v<VehicleCommandBuilder, idsim_common::VehicleIdentity, CommandSource>);
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

idsim_common::VehicleIdentity target()
{
  return idsim_common::VehicleIdentity{
    *idsim_common::VehicleNamespace::parse("/px4_1"), *idsim_common::SystemId::make(2)};
}

VehicleCommandBuilder builder()
{
  auto b = VehicleCommandBuilder::make(target(), *CommandSource::make(254, 1));
  if (!b) {
    throw std::runtime_error("VehicleCommandBuilder::make rejected source 254/1");
  }
  return *b;
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
  {
    SCOPED_TRACE("arm");
    expect_command(b.arm(ts), {400, 1.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  }
  {
    SCOPED_TRACE("disarm");
    expect_command(b.disarm(ts), {400, 0.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  }
  {
    SCOPED_TRACE("set_mode_offboard");
    expect_command(b.set_mode_offboard(ts), {176, 1.0F, 6.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  }
  {
    SCOPED_TRACE("set_mode_hold");
    expect_command(b.set_mode_hold(ts), {176, 1.0F, 4.0F, 3.0F, 0.0F, 0.0, 0.0, 0.0F});
  }
  {
    SCOPED_TRACE("land");
    expect_command(b.land(ts), {21, 0.0F, 0.0F, 0.0F, kNaNf, kNaN, kNaN, kNaNf});
  }
  {
    SCOPED_TRACE("rtl");
    expect_command(b.rtl(ts), {20, 0.0F, 0.0F, 0.0F, 0.0F, 0.0, 0.0, 0.0F});
  }
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

  // check_px4.py(source 254/1)와 Executor(source 254/191)의 ack는 섞이지 않는다.
  const auto mission =
    VehicleCommandBuilder::make(builder().target(), *CommandSource::make(254, 191));
  ASSERT_TRUE(mission.has_value());
  EXPECT_FALSE(idsim_common::is_ack_for(ack, mission->arm(timestamp())));

  // system이 다른 송신자도 섞이지 않는다.
  const auto other = VehicleCommandBuilder::make(builder().target(), *CommandSource::make(1, 191));
  ASSERT_TRUE(other.has_value());
  EXPECT_FALSE(idsim_common::is_ack_for(ack, other->arm(timestamp())));
}

TEST(VehicleCommandBuilder, MakeRejectsSourceSystemEqualToTarget)
{
  // 대상 sysid 2. source system 2는 component와 무관하게 거부한다.
  EXPECT_FALSE(VehicleCommandBuilder::make(target(), *CommandSource::make(2, 1)).has_value());
  EXPECT_FALSE(VehicleCommandBuilder::make(target(), *CommandSource::make(2, 191)).has_value());
  // source 값 표(1a 6단계 쟁점 4)의 세 주체는 모두 받아들인다.
  for (const int component : {191, 25, 1}) {
    const auto b = VehicleCommandBuilder::make(target(), *CommandSource::make(254, component));
    ASSERT_TRUE(b.has_value()) << component;
    EXPECT_EQ(b->source().system(), 254);
    EXPECT_EQ(b->source().component(), component);
    EXPECT_EQ(b->target().sysid.value(), 2);
  }
  // 대상이 254이면 source 254는 거부된다(규칙은 값이 아니라 같음으로 정해진다).
  const idsim_common::VehicleIdentity target_254{
    *idsim_common::VehicleNamespace::parse("/px4_253"), *idsim_common::SystemId::make(254)};
  EXPECT_FALSE(VehicleCommandBuilder::make(target_254, *CommandSource::make(254, 191)).has_value());
}
