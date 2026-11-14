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

#include "idsim_mission/px4/outputs.hpp"

#include <optional>
#include <string>

#include "Eigen/Core"
#include "idsim_common/frames.hpp"
#include "idsim_common/px4_setpoint.hpp"

namespace idsim_mission::px4
{

core::SetpointOut apply_ground_offset(const core::SetpointOut & setpoint)
{
  core::SetpointOut out = setpoint;
  if (out.kind == core::SetpointKind::kGround) {
    out.z += kGroundSetpointOffsetDownM;
  }
  return out;
}

std::optional<SetpointMessages> to_setpoint_messages(
  const core::SetpointOut & setpoint, idsim_common::Px4Timestamp timestamp)
{
  const core::SetpointOut target = apply_ground_offset(setpoint);
  // velocity_valid가 false이면 nullopt를 넘겨 velocity가 NaN(feedforward 없음)이 된다. true이면
  // 세 성분 모두 유한해야 하고, 아니면 position_setpoint가 짝 전체를 거부한다.
  std::optional<Eigen::Vector3d> velocity;
  if (target.velocity_valid) {
    velocity = Eigen::Vector3d(target.velocity.x, target.velocity.y, target.velocity.z);
  }
  // wrap_pi는 비유한 값을 NaN으로 두므로 아래 position_setpoint가 거부한다.
  auto trajectory = idsim_common::px4::position_setpoint(
    timestamp, Eigen::Vector3d(target.x, target.y, target.z),
    idsim_common::frames::wrap_pi(target.yaw_ned), velocity);
  if (!trajectory) {
    return std::nullopt;
  }
  return SetpointMessages{idsim_common::px4::offboard_position_mode(timestamp), *trajectory};
}

px4_msgs::msg::VehicleCommand to_vehicle_command(
  core::CommandKind kind, const idsim_common::VehicleCommandBuilder & builder,
  idsim_common::Px4Timestamp timestamp)
{
  switch (kind) {
    case core::CommandKind::kSetModeOffboard:
      return builder.set_mode_offboard(timestamp);
    case core::CommandKind::kSetModeHold:
      return builder.set_mode_hold(timestamp);
    case core::CommandKind::kArm:
      return builder.arm(timestamp);
    case core::CommandKind::kDisarm:
      return builder.disarm(timestamp);  // 강제가 아닌 disarm
    case core::CommandKind::kNavLand:
      return builder.land(timestamp);
    case core::CommandKind::kNavRtl:
      return builder.rtl(timestamp);
  }
  // enum 밖의 값은 core가 만들지 않는다. 경고 없이 컴파일되도록 둔 도달 불가 경로.
  return builder.disarm(timestamp);
}

Px4Messages to_px4_messages(
  const core::StepOutput & out, const idsim_common::VehicleCommandBuilder & builder,
  const std::optional<idsim_common::Px4Timestamp> & stamp)
{
  Px4Messages msgs;
  if (!out.setpoint && out.commands.empty()) {
    return msgs;
  }
  if (!out.px4_timestamp_us) {
    msgs.error = "step output has setpoint or commands but no px4_timestamp_us; dropped all";
    return msgs;
  }
  if (!stamp) {
    msgs.error = "no Px4Timestamp made in this tick; dropped all";
    return msgs;
  }
  if (stamp->microseconds() != *out.px4_timestamp_us) {
    msgs.error = "Px4Timestamp of this tick (" + std::to_string(stamp->microseconds()) +
                 " us) differs from step output (" + std::to_string(*out.px4_timestamp_us) +
                 " us); dropped all";
    return msgs;
  }
  if (out.setpoint) {
    msgs.setpoint = to_setpoint_messages(*out.setpoint, *stamp);
    if (!msgs.setpoint) {
      msgs.error = "setpoint is not finite; dropped offboard_control_mode and trajectory_setpoint";
    }
  }
  msgs.commands.reserve(out.commands.size());
  for (const core::CommandKind kind : out.commands) {
    msgs.commands.push_back(to_vehicle_command(kind, builder, *stamp));
  }
  return msgs;
}

}  // namespace idsim_mission::px4
