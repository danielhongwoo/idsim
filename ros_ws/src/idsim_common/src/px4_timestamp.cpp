#include "idsim_common/px4_timestamp.hpp"

namespace idsim_common
{

std::optional<Px4Timestamp> Px4Timestamp::now(rclcpp::Clock & clock)
{
  // 순서가 중요하다. ros_time_is_active()는 RCL_ROS_TIME이 아닌 시계에서 예외를 던진다.
  if (clock.get_clock_type() != RCL_ROS_TIME) {
    return std::nullopt;
  }
  if (!clock.ros_time_is_active()) {
    return std::nullopt;
  }
  const std::int64_t nanoseconds = clock.now().nanoseconds();
  if (nanoseconds < 1000) {
    return std::nullopt;
  }
  return Px4Timestamp(static_cast<std::uint64_t>(nanoseconds) / 1000U);
}

}  // namespace idsim_common
