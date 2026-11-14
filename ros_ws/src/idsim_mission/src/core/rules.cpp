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

#include "idsim_mission/core/rules.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iterator>
#include <limits>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace idsim_mission::core
{

namespace
{
constexpr double kPi = 3.14159265358979323846;
}  // namespace

int monitor_rank(MonitorRow row)
{
  const auto * const found = std::find(kMonitorRankOrder.begin(), kMonitorRankOrder.end(), row);
  if (found == kMonitorRankOrder.end()) {
    return 0;
  }
  return static_cast<int>(std::distance(kMonitorRankOrder.begin(), found)) + 1;
}

const char * monitor_row_name(MonitorRow row)
{
  switch (row) {
    case MonitorRow::kTimestampFailure:
      return "TimestampFailure";
    case MonitorRow::kIdentityMismatch:
      return "IdentityMismatch";
    case MonitorRow::kLinkLost:
      return "LinkLost";
    case MonitorRow::kDisarmedInAir:
      return "DisarmedInAir";
    case MonitorRow::kDisarmedOnGround:
      return "DisarmedOnGround";
    case MonitorRow::kModeFailsafe:
      return "ModeFailsafe";
    case MonitorRow::kModeExternal:
      return "ModeExternal";
    case MonitorRow::kModeDefensive:
      return "ModeDefensive";
  }
  return "Unknown";
}

bool monitor_row_matches(MonitorRow row, const MonitorInput & input)
{
  const StatusSample * const s = input.status;
  const bool have = s != nullptr;
  const bool disarmed = have && s->arming == Arming::kDisarmed;
  const bool off_mode = have && s->nav != NavMode::kOffboard;
  switch (row) {
    case MonitorRow::kTimestampFailure:
      return !input.timestamp_ok;
    case MonitorRow::kIdentityMismatch:
      return have && s->identity == IdentityCheck::kMismatch;
    case MonitorRow::kLinkLost:
      return !have || input.link_lost;
    case MonitorRow::kDisarmedInAir:
      return disarmed && !input.landed;
    case MonitorRow::kDisarmedOnGround:
      return disarmed && input.landed;
    case MonitorRow::kModeFailsafe:
      return off_mode && s->failsafe;
    case MonitorRow::kModeExternal:
      return off_mode && !s->failsafe && s->nav_user_intention != NavMode::kOffboard;
    case MonitorRow::kModeDefensive:
      return off_mode && !s->failsafe && s->nav_user_intention == NavMode::kOffboard;
  }
  return false;
}

Reason monitor_row_reason(MonitorRow row, const MonitorInput & input)
{
  switch (row) {
    case MonitorRow::kTimestampFailure:
    case MonitorRow::kIdentityMismatch:
      return Reason::kInternal;
    case MonitorRow::kLinkLost:
      return Reason::kLinkLost;
    case MonitorRow::kDisarmedInAir:
    case MonitorRow::kModeFailsafe:
    case MonitorRow::kModeDefensive:
      return Reason::kFailsafe;
    case MonitorRow::kDisarmedOnGround: {
      // 이 표본의 failsafe이거나 이 항목 실행 중 앞선 표본의 failsafe 이력. 이 표본의 nav_state는
      // 보지 않는다(decisions.md 쟁점 4 순위 5).
      const bool sample_failsafe = input.status != nullptr && input.status->failsafe;
      return sample_failsafe || input.failsafe_history ? Reason::kFailsafe
                                                       : Reason::kExternalDisarm;
    }
    case MonitorRow::kModeExternal:
      return Reason::kExternalModeChange;
  }
  return Reason::kInternal;
}

std::optional<MonitorVerdict> evaluate_monitor(const MonitorInput & input)
{
  std::vector<MonitorRow> matched;
  for (const MonitorRow row : kMonitorRankOrder) {
    if (monitor_row_matches(row, input)) {
      matched.push_back(row);
    }
  }
  if (matched.empty()) {
    return std::nullopt;
  }
  const MonitorRow row = matched.front();
  MonitorVerdict verdict;
  verdict.row = row;
  verdict.reason = monitor_row_reason(row, input);
  verdict.detail =
    "monitor rank " + std::to_string(monitor_rank(row)) + " " + monitor_row_name(row);
  if (row == MonitorRow::kIdentityMismatch && input.status != nullptr) {
    verdict.detail += ": " + input.status->identity_detail;
  }
  if (row == MonitorRow::kDisarmedOnGround) {
    verdict.detail += ": disarmed on ground (not sent by executor)";
  }
  verdict.matched = std::move(matched);
  return verdict;
}

MonitorDisarm monitor_row_disarm(MonitorRow row)
{
  switch (row) {
    case MonitorRow::kTimestampFailure:
    case MonitorRow::kDisarmedInAir:
    case MonitorRow::kDisarmedOnGround:
      return MonitorDisarm::kNever;
    case MonitorRow::kIdentityMismatch:
      return MonitorDisarm::kIfArmSent;
    case MonitorRow::kLinkLost:
    case MonitorRow::kModeFailsafe:
    case MonitorRow::kModeExternal:
    case MonitorRow::kModeDefensive:
      return MonitorDisarm::kIfNeverAirborne;
  }
  return MonitorDisarm::kNever;
}

bool monitor_sends_disarm(MonitorRow row, const MonitorDisarmInput & input)
{
  switch (monitor_row_disarm(row)) {
    case MonitorDisarm::kNever:
      return false;
    case MonitorDisarm::kIfArmSent:
      // vehicle_land_detected에는 식별 필드가 없어 남의 landed false 하나로 조건 2가 깨질 수 있다.
      return input.arm_sent;
    case MonitorDisarm::kIfNeverAirborne:
      // 한 번도 뜨지 않은 지상 arm만 PX4가 스스로 disarm하지 않는다(COM_DISARM_PRFLT=-1).
      return input.arm_sent && !input.landed_false_seen && input.landed_known && input.landed;
  }
  return false;
}

std::optional<EntryPlan> entry_plan(std::uint8_t first_item_type)
{
  switch (first_item_type) {
    case item_type::kTakeoff:
      return EntryPlan::kGroundArm;
    case item_type::kLand:
    case item_type::kRtl:
      return EntryPlan::kModeCommand;
    default:
      return std::nullopt;
  }
}

std::optional<ModeItemSpec> mode_item_spec(std::uint8_t type)
{
  ModeItemSpec spec;
  switch (type) {
    case item_type::kLand:
      spec.command = CommandKind::kNavLand;
      spec.mode = NavMode::kLand;
      spec.mode_name = "AUTO_LAND";
      spec.command_name = "NAV_LAND";
      spec.land_fallback = false;
      return spec;
    case item_type::kRtl:
      spec.command = CommandKind::kNavRtl;
      spec.mode = NavMode::kRtl;
      spec.mode_name = "AUTO_RTL";
      spec.command_name = "NAV_RETURN_TO_LAUNCH";
      spec.land_fallback = true;
      return spec;
    default:
      return std::nullopt;
  }
}

const char * cleanup_choice_name(CleanupChoice choice)
{
  switch (choice) {
    case CleanupChoice::kAir:
      return "Air";
    case CleanupChoice::kGround:
      return "Ground";
    case CleanupChoice::kAirDisarm:
      return "AirDisarm";
    case CleanupChoice::kEnd:
      return "End";
  }
  return "Unknown";
}

CleanupChoice select_cleanup(const CleanupInput & input)
{
  if (input.arming == Arming::kDisarmed) {
    if (input.disarm_class == DisarmClass::kAir) {
      return CleanupChoice::kAirDisarm;
    }
    // 이 goal에서 arm을 보낸 적이 있으면 arming_state와 무관하게 disarm 분기를 거친다
    // (arm 전송 뒤의 경쟁. decisions.md 쟁점 3 M5).
    return input.arm_sent || input.in_ground_branch ? CleanupChoice::kGround : CleanupChoice::kEnd;
  }
  return input.landed ? CleanupChoice::kGround : CleanupChoice::kAir;
}

void SampleCounter::reset()
{
  count_ = 0;
  last_timestamp_us_ = 0;
  has_last_ = false;
}

bool SampleCounter::observe(std::uint64_t timestamp_us, bool matches)
{
  if (has_last_ && timestamp_us <= last_timestamp_us_) {
    return false;
  }
  has_last_ = true;
  last_timestamp_us_ = timestamp_us;
  count_ = matches ? count_ + 1 : 0;
  return true;
}

bool is_after_disarm_send(
  const StatusSample & sample, std::uint64_t first_send_tick, std::uint64_t first_send_stamp_us)
{
  return sample.received_tick > first_send_tick && sample.timestamp_us > first_send_stamp_us;
}

void DisarmConfirm::begin(std::uint64_t first_send_tick)
{
  counter_.reset();
  first_send_tick_ = first_send_tick;
  first_send_stamp_us_ = 0;
  stamp_known_ = false;
}

void DisarmConfirm::set_first_stamp(std::uint64_t stamp_us)
{
  first_send_stamp_us_ = stamp_us;
  stamp_known_ = true;
}

void DisarmConfirm::observe(const StatusSample & sample)
{
  if (!stamp_known_ || !is_after_disarm_send(sample, first_send_tick_, first_send_stamp_us_)) {
    return;
  }
  counter_.observe(sample.timestamp_us, sample.arming == Arming::kDisarmed);
}

void LandedArmedFallback::reset() { *this = LandedArmedFallback{}; }

void LandedArmedFallback::observe(bool landed_and_armed, std::int64_t now_ns)
{
  if (!landed_and_armed) {
    known_ = false;
    return;
  }
  if (!known_) {
    known_ = true;
    since_ns_ = now_ns;
  }
}

bool LandedArmedFallback::due(std::int64_t now_ns, std::int64_t delay_ns) const
{
  return !sent_ && known_ && now_ns - since_ns_ >= delay_ns;
}

double wrap_pi(double angle)
{
  if (!std::isfinite(angle)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  double wrapped = std::fmod(angle + kPi, 2.0 * kPi);
  if (wrapped < 0.0) {
    wrapped += 2.0 * kPi;
  }
  wrapped -= kPi;
  if (wrapped >= kPi) {
    wrapped -= 2.0 * kPi;
  }
  return wrapped;
}

double enu_to_ned_yaw(double yaw_enu) { return wrap_pi(kPi / 2.0 - yaw_enu); }

}  // namespace idsim_mission::core
