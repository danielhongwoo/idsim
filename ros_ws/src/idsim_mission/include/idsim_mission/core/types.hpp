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

// core의 값 타입: reason, 종료 상태, 항목 type과 분류, feedback phase, 미션 명세.
//
// core는 ROS와 PX4에 의존하지 않는다(decisions.md 쟁점 6). 그래서 idsim_interfaces의 메시지를
// 쓰지 않고 같은 값을 여기에 다시 적는다. 값이 메시지 상수와 같은지는 노드 쪽 gtest(P3d)가
// 교차 검사한다(상수가 늘면 깨진다). MissionSpec은 ExecuteMission goal의 Mission을 필드 그대로
// 옮긴 것이고, 변환은 노드가 한다. 좌표와 yaw는 계약 그대로 world ENU다.

#ifndef IDSIM_MISSION__CORE__TYPES_HPP_
#define IDSIM_MISSION__CORE__TYPES_HPP_

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace idsim_mission::core
{

// ExecuteMission result의 REASON_*. 13, 14는 1a 6단계가 더한다(P3e가 메시지 상수를 더한다).
enum class Reason : std::uint8_t
{
  kNone = 0,
  kInvalidMission = 1,
  kVehicleIdMismatch = 2,
  kBusy = 3,
  kNotReady = 4,
  kArmRejected = 5,
  kModeSwitchFailed = 6,
  kItemTimeout = 7,
  kFailsafe = 8,
  kExternalModeChange = 9,
  kTargetLost = 10,
  kLinkLost = 11,
  kPreconditionFailed = 12,
  kDisarmFailed = 13,
  kExternalDisarm = 14,
  kInternal = 255,
};

inline constexpr std::array<Reason, 16> kAllReasons = {
  Reason::kNone,
  Reason::kInvalidMission,
  Reason::kVehicleIdMismatch,
  Reason::kBusy,
  Reason::kNotReady,
  Reason::kArmRejected,
  Reason::kModeSwitchFailed,
  Reason::kItemTimeout,
  Reason::kFailsafe,
  Reason::kExternalModeChange,
  Reason::kTargetLost,
  Reason::kLinkLost,
  Reason::kPreconditionFailed,
  Reason::kDisarmFailed,
  Reason::kExternalDisarm,
  Reason::kInternal,
};

// 사람이 읽는 이름(메시지 상수 이름에서 REASON_을 뺀 것). detail과 로그용.
const char * reason_name(Reason reason);

// goal의 끝난 상태. 정본은 action의 GoalStatus다.
enum class Status : std::uint8_t
{
  kSucceeded,
  kCanceled,
  kAborted,
};

inline constexpr std::array<Status, 3> kAllStatuses = {
  Status::kSucceeded, Status::kCanceled, Status::kAborted};

const char * status_name(Status status);

// MissionItem.TYPE_*. 0은 무효다.
namespace item_type
{
inline constexpr std::uint8_t kTakeoff = 1;
inline constexpr std::uint8_t kGoTo = 2;
inline constexpr std::uint8_t kTrackEntity = 3;
inline constexpr std::uint8_t kLoiter = 4;
inline constexpr std::uint8_t kRtl = 5;
inline constexpr std::uint8_t kLand = 6;
}  // namespace item_type

inline constexpr std::array<std::uint8_t, 6> kAllItemTypes = {
  item_type::kTakeoff, item_type::kGoTo, item_type::kTrackEntity,
  item_type::kLoiter,  item_type::kRtl,  item_type::kLand};

const char * item_type_name(std::uint8_t type);

// 항목 분류(5단계 넘김). setpoint 항목은 Offboard에서 setpoint를 발행하는 항목이고, 모드 명령
// 항목은 PX4 모드 명령을 보내고 모드 전이를 확인하는 항목이다. 모든 TYPE_*는 정확히 한 분류에
// 속한다. TYPE_*가 아니면 nullopt.
enum class ItemKind : std::uint8_t
{
  kSetpoint,
  kModeCommand,
};

std::optional<ItemKind> classify_item_type(std::uint8_t type);

// YawSetpoint.MODE_*. 0은 무효다.
namespace yaw_mode
{
inline constexpr std::uint8_t kKeep = 1;
inline constexpr std::uint8_t kFixed = 2;
}  // namespace yaw_mode

// ExecuteMission feedback의 PHASE_*.
enum class FeedbackPhase : std::uint8_t
{
  kPreparing = 1,
  kExecuting = 2,
  kWaitingMode = 3,
  kCanceling = 4,
};

// builtin_interfaces/Duration과 같은 필드. nanosec는 [0, 1e9)여야 한다(검증이 본다).
struct Duration
{
  std::int32_t sec{0};
  std::uint32_t nanosec{0};

  std::int64_t to_ns() const
  {
    return static_cast<std::int64_t>(sec) * 1000000000LL + static_cast<std::int64_t>(nanosec);
  }
};

struct Vec3
{
  double x{0.0};
  double y{0.0};
  double z{0.0};
};

struct YawSpec
{
  std::uint8_t mode{0};
  double yaw_rad{0.0};  // world ENU, MODE_FIXED일 때만
};

struct TakeoffSpec
{
  double height_m{0.0};
  double acceptance_m{0.0};
  YawSpec yaw;
};

struct GoToSpec
{
  Vec3 position;  // world ENU
  double acceptance_radius_m{0.0};
  YawSpec yaw;
};

struct TrackEntitySpec
{
  std::string target_id;
  Vec3 offset;  // world ENU
  double acceptance_radius_m{0.0};
  YawSpec yaw;
};

struct LoiterSpec
{
  Duration duration;
};

struct ItemSpec
{
  std::uint8_t type{0};
  Duration timeout;
  TakeoffSpec takeoff;
  GoToSpec go_to;
  TrackEntitySpec track_entity;
  LoiterSpec loiter;
};

struct MissionSpec
{
  std::string mission_id;
  std::vector<ItemSpec> items;
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__TYPES_HPP_
