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

#include "idsim_mission/px4/frame_port.hpp"

#include <cmath>
#include <cstdint>
#include <optional>

#include "Eigen/Core"
#include "idsim_common/frames.hpp"
#include "idsim_mission/px4/inputs.hpp"

namespace idsim_mission::px4
{

std::optional<idsim_common::geo::LocalReference> local_reference_from_px4(
  const px4_msgs::msg::VehicleLocalPosition & msg)
{
  const double lat = msg.ref_lat;
  const double lon = msg.ref_lon;
  const auto alt = static_cast<double>(msg.ref_alt);
  if (!msg.xy_global || !msg.z_global) {
    return std::nullopt;
  }
  if (!std::isfinite(lat) || !std::isfinite(lon) || !std::isfinite(alt)) {
    return std::nullopt;
  }
  // PX4는 고도 원점이 없으면 ref_alt를 0으로 둔다. 0.0과의 정확한 비교가 의도다.
  if (alt == 0.0) {
    return std::nullopt;
  }
  return idsim_common::geo::LocalReference{lat, lon, alt};
}

LocalPositionInput to_local_position_input(
  const px4_msgs::msg::VehicleLocalPosition & msg, std::uint64_t received_tick)
{
  LocalPositionInput input;
  input.position = to_position_sample(msg, received_tick);
  input.reference = local_reference_from_px4(msg);
  input.ref_timestamp_us = msg.ref_timestamp;
  return input;
}

std::optional<core::Vec3> Px4FramePort::world_to_local(const core::Vec3 & world_enu) const
{
  if (!reference_) {
    return std::nullopt;
  }
  const Eigen::Vector3d ned = idsim_common::geo::world_enu_to_local_ned(
    origin_, *reference_, Eigen::Vector3d(world_enu.x, world_enu.y, world_enu.z));
  if (!ned.allFinite()) {
    return std::nullopt;
  }
  return core::Vec3{ned.x(), ned.y(), ned.z()};
}

core::Vec3 Px4FramePort::world_velocity_to_local(const core::Vec3 & world_enu) const
{
  const Eigen::Vector3d ned =
    idsim_common::frames::enu_to_ned(Eigen::Vector3d(world_enu.x, world_enu.y, world_enu.z));
  return core::Vec3{ned.x(), ned.y(), ned.z()};
}

}  // namespace idsim_mission::px4
