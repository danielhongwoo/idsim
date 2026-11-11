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

#include "idsim_mission/node/conversion.hpp"

#include <cstdint>
#include <string>

namespace idsim_mission
{

namespace
{

core::Duration to_duration(const builtin_interfaces::msg::Duration & d)
{
  core::Duration out;
  out.sec = d.sec;
  out.nanosec = d.nanosec;
  return out;
}

core::YawSpec to_yaw(const idsim_interfaces::msg::YawSetpoint & y)
{
  core::YawSpec out;
  out.mode = y.mode;
  out.yaw_rad = y.yaw_rad;
  return out;
}

core::Vec3 to_vec3(double x, double y, double z)
{
  core::Vec3 out;
  out.x = x;
  out.y = y;
  out.z = z;
  return out;
}

idsim_interfaces::msg::MissionEvent base_event(const EventContext & context)
{
  idsim_interfaces::msg::MissionEvent event;
  event.stamp = context.stamp;
  event.vehicle_id = context.vehicle_id;
  event.mission_id = context.mission_id;
  event.goal_id = context.goal_id;
  event.item_count = context.item_count;
  return event;
}

void copy_fields(const core::EventFields & fields, idsim_interfaces::msg::MissionEvent & event)
{
  event.status = fields.status;
  event.reason = fields.reason;
  event.item_count = fields.item_count;
  event.items_completed = fields.items_completed;
  event.last_item_index = fields.last_item_index;
  event.detail = fields.detail;
}

}  // namespace

core::MissionSpec to_mission_spec(const idsim_interfaces::msg::Mission & mission)
{
  core::MissionSpec spec;
  spec.mission_id = mission.mission_id;
  spec.items.reserve(mission.items.size());
  for (const auto & item : mission.items) {
    core::ItemSpec out;
    out.type = item.type;
    out.timeout = to_duration(item.timeout);
    out.takeoff.height_m = item.takeoff.height_m;
    out.takeoff.acceptance_m = item.takeoff.acceptance_m;
    out.takeoff.yaw = to_yaw(item.takeoff.yaw);
    out.go_to.position =
      to_vec3(item.go_to.position.x, item.go_to.position.y, item.go_to.position.z);
    out.go_to.acceptance_radius_m = item.go_to.acceptance_radius_m;
    out.go_to.yaw = to_yaw(item.go_to.yaw);
    out.track_entity.target_id = item.track_entity.target_id;
    out.track_entity.offset =
      to_vec3(item.track_entity.offset.x, item.track_entity.offset.y, item.track_entity.offset.z);
    out.track_entity.acceptance_radius_m = item.track_entity.acceptance_radius_m;
    out.track_entity.yaw = to_yaw(item.track_entity.yaw);
    out.loiter.duration = to_duration(item.loiter.duration);
    spec.items.push_back(out);
  }
  return spec;
}

idsim_interfaces::action::ExecuteMission::Result to_result_msg(const core::Termination & term)
{
  const core::ResultFields fields = core::to_result(term);
  idsim_interfaces::action::ExecuteMission::Result result;
  result.reason = fields.reason;
  result.items_completed = fields.items_completed;
  result.last_item_index = fields.last_item_index;
  result.detail = fields.detail;
  return result;
}

idsim_interfaces::msg::MissionEvent accepted_event_msg(const EventContext & context)
{
  idsim_interfaces::msg::MissionEvent event = base_event(context);
  copy_fields(core::accepted_event(context.item_count), event);
  return event;
}

idsim_interfaces::msg::MissionEvent terminal_event_msg(
  const EventContext & context, const core::Termination & term)
{
  idsim_interfaces::msg::MissionEvent event = base_event(context);
  copy_fields(core::to_terminal_event(term, context.item_count), event);
  return event;
}

idsim_interfaces::action::ExecuteMission::Feedback to_feedback_msg(
  const core::Feedback & feedback, const builtin_interfaces::msg::Time & stamp)
{
  idsim_interfaces::action::ExecuteMission::Feedback msg;
  msg.stamp = stamp;
  msg.item_index = feedback.item_index;
  msg.item_count = feedback.item_count;
  msg.item_type = feedback.item_type;
  msg.phase = static_cast<std::uint8_t>(feedback.phase);
  msg.distance_valid = feedback.distance_valid;
  msg.distance_remaining_m = feedback.distance_remaining_m;
  return msg;
}

}  // namespace idsim_mission
