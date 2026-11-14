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

#include "idsim_common/px4_setpoint.hpp"

#include <cmath>
#include <limits>

namespace idsim_common::px4
{

namespace
{

constexpr float kNaN = std::numeric_limits<float>::quiet_NaN();

}  // namespace

bool fits_float32(double value)
{
  return std::isfinite(value) &&
         std::fabs(value) <= static_cast<double>(std::numeric_limits<float>::max());
}

bool fits_float32(const Eigen::Vector3d & v)
{
  return fits_float32(v.x()) && fits_float32(v.y()) && fits_float32(v.z());
}

px4_msgs::msg::OffboardControlMode offboard_position_mode(Px4Timestamp timestamp)
{
  px4_msgs::msg::OffboardControlMode mode;
  mode.timestamp = timestamp.microseconds();
  mode.position = true;
  mode.velocity = false;
  mode.acceleration = false;
  mode.attitude = false;
  mode.body_rate = false;
  mode.thrust_and_torque = false;
  mode.direct_actuator = false;
  return mode;
}

std::optional<px4_msgs::msg::TrajectorySetpoint> position_setpoint(
  Px4Timestamp timestamp, const Eigen::Vector3d & position_ned, double yaw_ned,
  const std::optional<Eigen::Vector3d> & velocity_ned)
{
  if (!fits_float32(position_ned) || !fits_float32(yaw_ned)) {
    return std::nullopt;
  }
  if (velocity_ned.has_value() && !fits_float32(*velocity_ned)) {
    return std::nullopt;
  }
  px4_msgs::msg::TrajectorySetpoint sp;
  sp.timestamp = timestamp.microseconds();
  sp.position = {
    static_cast<float>(position_ned.x()), static_cast<float>(position_ned.y()),
    static_cast<float>(position_ned.z())};
  if (velocity_ned.has_value()) {
    sp.velocity = {
      static_cast<float>(velocity_ned->x()), static_cast<float>(velocity_ned->y()),
      static_cast<float>(velocity_ned->z())};
  } else {
    sp.velocity = {kNaN, kNaN, kNaN};
  }
  sp.acceleration = {kNaN, kNaN, kNaN};
  sp.jerk = {kNaN, kNaN, kNaN};
  sp.yaw = static_cast<float>(yaw_ned);
  sp.yawspeed = kNaN;
  return sp;
}

}  // namespace idsim_common::px4
