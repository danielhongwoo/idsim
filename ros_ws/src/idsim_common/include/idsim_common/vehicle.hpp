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

// 기체 식별. 네임스페이스와 MAVLink system id를 강타입으로 두고 vehicle_status와 대조한다.
//
// idsim_common은 기체 번호 N에서 아무것도 계산하지 않는다(N+1 공식을 두지 않는다).
// 노드는 stack.json에서 생성된 params로 ns와 sysid를 받고, 이 헤더의 verify로 PX4가 실제로
// 쓰는 vehicle_status.system_id, component_id와 대조한다. 아직 vehicle_status를 받지 못한
// "미수신" 상태는 호출자가 표현한다(verify를 부르지 않는다).

#ifndef IDSIM_COMMON__VEHICLE_HPP_
#define IDSIM_COMMON__VEHICLE_HPP_

#include <cstdint>
#include <optional>
#include <string>
#include <utility>

#include "px4_msgs/msg/detail/vehicle_status__struct.hpp"

namespace idsim_common
{

// 기체 네임스페이스. 예: "/px4_1". /px4_N 형태나 N은 해석하지 않는다.
class VehicleNamespace
{
public:
  // 절대 경로, 끝 빗금 없음, 비어 있지 않고 "/"가 아니며 rmw_validate_namespace를 통과해야 한다.
  // 실패하면 nullopt이고, error가 있으면 이유를 적는다.
  static std::optional<VehicleNamespace> parse(
    const std::string & text, std::string * error = nullptr);

  const std::string & str() const { return value_; }

  bool operator==(const VehicleNamespace & other) const { return value_ == other.value_; }
  bool operator!=(const VehicleNamespace & other) const { return value_ != other.value_; }

private:
  explicit VehicleNamespace(std::string value) : value_(std::move(value)) {}

  std::string value_;
};

// MAVLink system id. 1-255. 0(브로드캐스트)은 만들 수 없다.
class SystemId
{
public:
  static std::optional<SystemId> make(int value);

  std::uint8_t value() const { return value_; }

  bool operator==(const SystemId & other) const { return value_ == other.value_; }
  bool operator!=(const SystemId & other) const { return value_ != other.value_; }

private:
  explicit SystemId(std::uint8_t value) : value_(value) {}

  std::uint8_t value_{0};
};

// PX4 autopilot의 MAVLink component id(MAV_COMP_ID_AUTOPILOT1).
inline constexpr std::uint8_t kAutopilotComponentId = 1;

struct VehicleIdentity
{
  VehicleNamespace ns;
  SystemId sysid;
};

enum class IdentityCheck : std::uint8_t
{
  Match,
  SystemIdMismatch,
  ComponentIdMismatch
};

// vehicle_status.system_id가 identity.sysid와 같고 component_id가 kAutopilotComponentId인지 본다.
// 둘 다 틀리면 SystemIdMismatch를 돌려준다.
IdentityCheck verify(const VehicleIdentity & identity, const px4_msgs::msg::VehicleStatus & status);

const char * to_string(IdentityCheck result);

}  // namespace idsim_common

#endif  // IDSIM_COMMON__VEHICLE_HPP_
