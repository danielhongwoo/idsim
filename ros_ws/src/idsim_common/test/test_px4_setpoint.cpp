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

// Offboard position setpoint 헬퍼의 필드 표와 비유한 거부. 노드를 만들지 않는다.
// 결정: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 5.
// 필드 값은 px4-engineer 의견서(git 이력) 넘김 표 (2).

#include <gtest/gtest.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>

#include "idsim_common/px4_setpoint.hpp"
#include "rcl/time.h"
#include "rclcpp/clock.hpp"

namespace px4 = idsim_common::px4;
using idsim_common::Px4Timestamp;

namespace
{

constexpr std::uint64_t kTimestampUs = 42'000'123;
constexpr double kInf = std::numeric_limits<double>::infinity();
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

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

void expect_all_nan(const std::array<float, 3> & v, const char * name)
{
  for (const float x : v) {
    EXPECT_TRUE(std::isnan(x)) << name;
  }
}

}  // namespace

TEST(Px4Setpoint, OffboardPositionModeFieldTable)
{
  const auto mode = px4::offboard_position_mode(timestamp());
  EXPECT_EQ(mode.timestamp, kTimestampUs);
  EXPECT_TRUE(mode.position);
  EXPECT_FALSE(mode.velocity);
  EXPECT_FALSE(mode.acceleration);
  EXPECT_FALSE(mode.attitude);
  EXPECT_FALSE(mode.body_rate);
  EXPECT_FALSE(mode.thrust_and_torque);
  EXPECT_FALSE(mode.direct_actuator);
}

TEST(Px4Setpoint, PositionSetpointFieldTable)
{
  const auto sp = px4::position_setpoint(timestamp(), Eigen::Vector3d(1.5, -2.25, -5.0), 0.5);
  ASSERT_TRUE(sp.has_value());
  EXPECT_EQ(sp->timestamp, kTimestampUs);
  // NED 그대로(축 치환 없음).
  EXPECT_EQ(sp->position[0], 1.5F);
  EXPECT_EQ(sp->position[1], -2.25F);
  EXPECT_EQ(sp->position[2], -5.0F);
  EXPECT_EQ(sp->yaw, 0.5F);
  expect_all_nan(sp->velocity, "velocity");
  expect_all_nan(sp->acceleration, "acceleration");
  expect_all_nan(sp->jerk, "jerk");
  EXPECT_TRUE(std::isnan(sp->yawspeed));
}

TEST(Px4Setpoint, PositionSetpointYawIsNotWrapped)
{
  const auto sp = px4::position_setpoint(timestamp(), Eigen::Vector3d::Zero(), 4.0);
  ASSERT_TRUE(sp.has_value());
  EXPECT_EQ(sp->yaw, 4.0F);
}

TEST(Px4Setpoint, PositionSetpointAcceptsFloatMax)
{
  const double max = static_cast<double>(std::numeric_limits<float>::max());
  const auto sp = px4::position_setpoint(timestamp(), Eigen::Vector3d(max, -max, 0.0), -max);
  ASSERT_TRUE(sp.has_value());
  EXPECT_EQ(sp->position[0], std::numeric_limits<float>::max());
  EXPECT_EQ(sp->position[1], -std::numeric_limits<float>::max());
  EXPECT_EQ(sp->yaw, -std::numeric_limits<float>::max());
}

TEST(Px4Setpoint, PositionSetpointRejectsNonFinite)
{
  const auto ts = timestamp();
  // FLT_MAX 바로 위의 double. 옛 구현은 이 값을 수용했다. 변환 전에 비교하므로 거부한다.
  const double above_max = std::nextafter(
    static_cast<double>(std::numeric_limits<float>::max()), std::numeric_limits<double>::max());
  for (const double bad : {kNaN, kInf, -kInf, 1e39, -1e39, above_max, -above_max}) {
    EXPECT_FALSE(px4::position_setpoint(ts, Eigen::Vector3d(bad, 0.0, -1.0), 0.0).has_value())
      << "x " << bad;
    EXPECT_FALSE(px4::position_setpoint(ts, Eigen::Vector3d(0.0, bad, -1.0), 0.0).has_value())
      << "y " << bad;
    EXPECT_FALSE(px4::position_setpoint(ts, Eigen::Vector3d(0.0, 0.0, bad), 0.0).has_value())
      << "z " << bad;
    EXPECT_FALSE(px4::position_setpoint(ts, Eigen::Vector3d(0.0, 0.0, -1.0), bad).has_value())
      << "yaw " << bad;
  }
}
