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

#include "idsim_mission/core/mission_validation.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>

namespace idsim_mission::core
{

namespace
{

constexpr double kPi = 3.14159265358979323846;
constexpr std::size_t kMissionIdMaxLength = 64;
constexpr std::uint32_t kNanosecPerSecond = 1000000000U;

bool lower_or_digit(char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }

bool positive_finite(double value) { return std::isfinite(value) && value > 0.0; }

bool finite(const Vec3 & v)
{
  return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z);
}

bool is_zero(const Vec3 & v) { return v.x == 0.0 && v.y == 0.0 && v.z == 0.0; }

bool is_zero(const Duration & d) { return d.sec == 0 && d.nanosec == 0; }

bool is_default(const YawSpec & y) { return y.mode == 0 && y.yaw_rad == 0.0; }

bool is_default(const TakeoffSpec & s)
{
  return s.height_m == 0.0 && s.acceptance_m == 0.0 && is_default(s.yaw);
}

bool is_default(const GoToSpec & s)
{
  return is_zero(s.position) && s.acceptance_radius_m == 0.0 && is_default(s.yaw);
}

bool is_default(const TrackEntitySpec & s)
{
  return s.target_id.empty() && is_zero(s.offset) && s.acceptance_radius_m == 0.0 &&
         is_default(s.yaw);
}

bool is_default(const LoiterSpec & s) { return is_zero(s.duration); }

std::string field(std::size_t index, const char * name)
{
  return "items[" + std::to_string(index) + "]." + name;
}

// 비어 있으면 통과.
std::string check_duration_positive(const Duration & d, const std::string & where)
{
  if (d.nanosec >= kNanosecPerSecond) {
    return where + ".nanosec must be < 1e9";
  }
  if (d.to_ns() <= 0) {
    return where + " must be > 0";
  }
  return {};
}

std::string check_yaw(const YawSpec & yaw, const std::string & where)
{
  if (yaw.mode == yaw_mode::kKeep) {
    if (yaw.yaw_rad != 0.0) {
      return where + ".yaw_rad must be 0 when mode is MODE_KEEP";
    }
    return {};
  }
  if (yaw.mode == yaw_mode::kFixed) {
    if (!std::isfinite(yaw.yaw_rad) || yaw.yaw_rad < -kPi || yaw.yaw_rad >= kPi) {
      return where + ".yaw_rad must be finite and in [-pi, pi)";
    }
    return {};
  }
  return where + ".mode must be MODE_KEEP or MODE_FIXED (got " + std::to_string(yaw.mode) + ")";
}

std::string check_unused(const ItemSpec & item, std::size_t index)
{
  if (item.type != item_type::kTakeoff && !is_default(item.takeoff)) {
    return field(index, "takeoff") + " must be default for type " + item_type_name(item.type);
  }
  if (item.type != item_type::kGoTo && !is_default(item.go_to)) {
    return field(index, "go_to") + " must be default for type " + item_type_name(item.type);
  }
  if (item.type != item_type::kTrackEntity && !is_default(item.track_entity)) {
    return field(index, "track_entity") + " must be default for type " + item_type_name(item.type);
  }
  if (item.type != item_type::kLoiter && !is_default(item.loiter)) {
    return field(index, "loiter") + " must be default for type " + item_type_name(item.type);
  }
  return {};
}

std::string check_used(const ItemSpec & item, std::size_t index)
{
  switch (item.type) {
    case item_type::kTakeoff: {
      const TakeoffSpec & s = item.takeoff;
      if (!positive_finite(s.height_m)) {
        return field(index, "takeoff.height_m") + " must be finite and > 0";
      }
      if (!positive_finite(s.acceptance_m)) {
        return field(index, "takeoff.acceptance_m") + " must be finite and > 0";
      }
      return check_yaw(s.yaw, field(index, "takeoff.yaw"));
    }
    case item_type::kGoTo: {
      const GoToSpec & s = item.go_to;
      if (!finite(s.position)) {
        return field(index, "go_to.position") + " must be finite";
      }
      if (!positive_finite(s.acceptance_radius_m)) {
        return field(index, "go_to.acceptance_radius_m") + " must be finite and > 0";
      }
      return check_yaw(s.yaw, field(index, "go_to.yaw"));
    }
    case item_type::kTrackEntity: {
      const TrackEntitySpec & s = item.track_entity;
      if (s.target_id.empty()) {
        return field(index, "track_entity.target_id") + " must not be empty";
      }
      if (!finite(s.offset) || is_zero(s.offset)) {
        return field(index, "track_entity.offset") + " must be finite and non-zero";
      }
      if (!positive_finite(s.acceptance_radius_m)) {
        return field(index, "track_entity.acceptance_radius_m") + " must be finite and > 0";
      }
      return check_yaw(s.yaw, field(index, "track_entity.yaw"));
    }
    case item_type::kLoiter: {
      std::string error =
        check_duration_positive(item.loiter.duration, field(index, "loiter.duration"));
      if (error.empty() && item.loiter.duration.to_ns() >= item.timeout.to_ns()) {
        error = field(index, "loiter.duration") + " must be shorter than timeout";
      }
      return error;
    }
    default:
      // RTL, LAND: 서브메시지가 없다.
      return {};
  }
}

std::string check_item(const ItemSpec & item, std::size_t index)
{
  if (!classify_item_type(item.type).has_value()) {
    return field(index, "type") + " is not a TYPE_* value (got " + std::to_string(item.type) + ")";
  }
  std::string error = check_duration_positive(item.timeout, field(index, "timeout"));
  if (!error.empty()) {
    return error;
  }
  error = check_unused(item, index);
  if (!error.empty()) {
    return error;
  }
  return check_used(item, index);
}

MissionCheck invalid(std::string detail)
{
  MissionCheck check;
  check.valid = false;
  check.detail = std::move(detail);
  return check;
}

bool supported_in_1a(std::uint8_t type)
{
  return type == item_type::kTakeoff || type == item_type::kLoiter || type == item_type::kLand;
}

bool supported_by_runner(std::uint8_t type)
{
  return supported_in_1a(type) || type == item_type::kRtl;
}

// 계약 + 1a 임시 제한. validate_mission_1a_goal이 쓴다.
MissionCheck check_1a_limits(const MissionSpec & mission)
{
  MissionCheck check = validate_mission_contract(mission);
  if (!check.valid) {
    return check;
  }
  const std::size_t count = mission.items.size();
  for (std::size_t i = 0; i < count; ++i) {
    const std::uint8_t type = mission.items[i].type;
    if (!supported_in_1a(type)) {
      return invalid(
        field(i, "type") + " " + item_type_name(type) +
        " is not supported in 1a (TAKEOFF, LOITER, LAND only)");
    }
  }
  if (mission.items.back().type != item_type::kLand) {
    return invalid("last item must be LAND in 1a (missions ending in the air are 1b)");
  }
  const std::uint8_t first = mission.items.front().type;
  if (first != item_type::kTakeoff && first != item_type::kLand) {
    return invalid("first item must be TAKEOFF or LAND in 1a");
  }
  return check;
}

}  // namespace

bool is_valid_mission_id(const std::string & mission_id)
{
  if (mission_id.empty() || mission_id.size() > kMissionIdMaxLength) {
    return false;
  }
  if (!lower_or_digit(mission_id.front())) {
    return false;
  }
  for (std::size_t i = 1; i < mission_id.size(); ++i) {
    const char c = mission_id[i];
    if (!lower_or_digit(c) && c != '_' && c != '-') {
      return false;
    }
  }
  return true;
}

MissionCheck validate_mission_contract(const MissionSpec & mission)
{
  if (!is_valid_mission_id(mission.mission_id)) {
    return invalid(
      "mission_id '" + mission.mission_id + "' does not match ^[a-z0-9][a-z0-9_-]{0,63}$");
  }
  if (mission.items.empty()) {
    return invalid("mission has no items");
  }
  const std::size_t count = mission.items.size();
  for (std::size_t i = 0; i < count; ++i) {
    std::string error = check_item(mission.items[i], i);
    if (!error.empty()) {
      return invalid(std::move(error));
    }
  }
  // 순서 규칙(1b decisions.md 쟁점 6). 필드 검사 뒤에 보므로 필드 오류의 detail은 그대로다.
  for (std::size_t i = 0; i < count; ++i) {
    const std::uint8_t type = mission.items[i].type;
    if (type == item_type::kTakeoff && i != 0) {
      return invalid(field(i, "type") + " TAKEOFF is allowed only as the first item");
    }
    if ((type == item_type::kLand || type == item_type::kRtl) && i + 1 != count) {
      return invalid(
        field(i, "type") + " " + item_type_name(type) + " is allowed only as the last item");
    }
  }
  MissionCheck ok;
  ok.valid = true;
  return ok;
}

MissionCheck validate_mission_1a_goal(const MissionSpec & mission)
{
  return check_1a_limits(mission);
}

MissionCheck validate_mission_runnable(const MissionSpec & mission)
{
  // 계약 + runner가 아직 실행하지 못하는 미션의 제한. 1b decisions.md 쟁점 12의 PR마다 푼다.
  MissionCheck check = validate_mission_contract(mission);
  if (!check.valid) {
    return check;
  }
  const std::size_t count = mission.items.size();
  for (std::size_t i = 0; i < count; ++i) {
    const std::uint8_t type = mission.items[i].type;
    if (!supported_by_runner(type)) {
      return invalid(
        field(i, "type") + " " + item_type_name(type) +
        " is not supported by the runner yet (TAKEOFF, LOITER, LAND, RTL only)");
    }
  }
  const std::uint8_t last = mission.items.back().type;
  if (last != item_type::kLand && last != item_type::kRtl) {
    return invalid(
      "last item must be LAND or RTL (missions ending in the air are not supported by the runner "
      "yet)");
  }
  const std::uint8_t first = mission.items.front().type;
  if (first != item_type::kTakeoff && first != item_type::kLand && first != item_type::kRtl) {
    return invalid("first item must be TAKEOFF, LAND or RTL");
  }
  return check;
}

std::optional<Termination> screen_goal(
  const std::string & goal_vehicle_id, const std::string & own_vehicle_id,
  const MissionSpec & mission, bool busy)
{
  Termination termination;
  termination.status = Status::kAborted;
  if (goal_vehicle_id != own_vehicle_id) {
    termination.reason = Reason::kVehicleIdMismatch;
    termination.detail =
      "goal vehicle_id '" + goal_vehicle_id + "' is not this executor '" + own_vehicle_id + "'";
    return termination;
  }
  MissionCheck check = validate_mission_1a_goal(mission);
  if (!check.valid) {
    termination.reason = Reason::kInvalidMission;
    termination.detail = std::move(check.detail);
    return termination;
  }
  if (busy) {
    termination.reason = Reason::kBusy;
    termination.detail = "another goal is executing";
    return termination;
  }
  return std::nullopt;
}

}  // namespace idsim_mission::core
