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
