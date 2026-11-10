// Px4Timestamp 생성 규칙. 노드 없이 rclcpp::Clock과 rcl의 ROS 시간 override로 시험한다.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 4.

#include <gtest/gtest.h>

#include <cstdint>
#include <type_traits>

#include "idsim_common/px4_timestamp.hpp"
#include "rcl/time.h"
#include "rclcpp/clock.hpp"

using idsim_common::Px4Timestamp;

namespace
{

// use_sim_time 노드가 /clock을 받은 상태를 흉내 낸다.
void activate_sim_time(rclcpp::Clock & clock, rcl_time_point_value_t nanoseconds)
{
  ASSERT_EQ(rcl_enable_ros_time_override(clock.get_clock_handle()), RCL_RET_OK);
  ASSERT_EQ(rcl_set_ros_time_override(clock.get_clock_handle(), nanoseconds), RCL_RET_OK);
}

}  // namespace

static_assert(!std::is_default_constructible_v<Px4Timestamp>);
static_assert(!std::is_constructible_v<Px4Timestamp, std::uint64_t>);
static_assert(!std::is_constructible_v<Px4Timestamp, rclcpp::Time>);

TEST(Px4Timestamp, RejectsRosClockWithoutSimTime)
{
  // use_sim_time이 꺼진 노드 시계: RCL_ROS_TIME이지만 값은 epoch 벽시계다.
  rclcpp::Clock clock(RCL_ROS_TIME);
  ASSERT_GT(clock.now().nanoseconds(), 0);
  EXPECT_FALSE(Px4Timestamp::now(clock).has_value());
}

TEST(Px4Timestamp, RejectsSystemAndSteadyClocks)
{
  rclcpp::Clock system_clock(RCL_SYSTEM_TIME);
  rclcpp::Clock steady_clock(RCL_STEADY_TIME);
  EXPECT_FALSE(Px4Timestamp::now(system_clock).has_value());
  EXPECT_FALSE(Px4Timestamp::now(steady_clock).has_value());
}

TEST(Px4Timestamp, RejectsZeroBeforeFirstClock)
{
  // /clock을 받기 전 use_sim_time 노드의 now()는 0이다.
  rclcpp::Clock clock(RCL_ROS_TIME);
  activate_sim_time(clock, 0);
  ASSERT_TRUE(clock.ros_time_is_active());
  EXPECT_FALSE(Px4Timestamp::now(clock).has_value());
  // 1 us 미만도 us로 바꾸면 0이므로 거부한다.
  activate_sim_time(clock, 999);
  EXPECT_FALSE(Px4Timestamp::now(clock).has_value());
}

TEST(Px4Timestamp, ConvertsActiveSimTimeToMicroseconds)
{
  rclcpp::Clock clock(RCL_ROS_TIME);
  activate_sim_time(clock, 77'780'123'456LL);
  const auto ts = Px4Timestamp::now(clock);
  ASSERT_TRUE(ts.has_value());
  EXPECT_EQ(ts->microseconds(), 77'780'123U);

  activate_sim_time(clock, 1000);
  const auto one = Px4Timestamp::now(clock);
  ASSERT_TRUE(one.has_value());
  EXPECT_EQ(one->microseconds(), 1U);
}
