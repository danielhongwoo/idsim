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

// px4_msgs VehicleCommand 빌더와 ack 매칭 술어.
//
// 빌더는 대상 기체(VehicleIdentity)와 송신자(CommandSource) 없이 만들 수 없고, 만드는 길은 make
// 하나다. make는 source.system()이 대상 sysid와 같으면 거부한다. 그러면 (대상 sysid, 1)처럼
// 송신자가 대상 autopilot 자신으로 보이는 조합이 원천적으로 막힌다(1a 6단계 쟁점 5,
// source 값 표). 고정 필드:
// target_component = 1, from_external = true(false면 PX4가 MAVLink로 재송출한다), confirmation = 0.
// timestamp는 Px4Timestamp 인자로만 받는다.
//
// ack ACCEPTED는 성공이 아니다. DO_SET_MODE는 base_mode 누락이나 시동 전 Offboard에서도 ACCEPTED다.
// 모드 전환 성공은 vehicle_status.nav_state로 확인한다(idsim_mission의 상태기). 그래서 여기에는
// "ACCEPTED = 성공" 헬퍼를 두지 않고 is_ack_for만 둔다.
//
// 검증 없는 raw(command, params)는 두지 않는다. 새 명령은 px4-engineer 승인 뒤 메서드로 더한다.

#ifndef IDSIM_COMMON__VEHICLE_COMMAND_HPP_
#define IDSIM_COMMON__VEHICLE_COMMAND_HPP_

#include <cstdint>
#include <optional>

#include "idsim_common/px4_timestamp.hpp"
#include "idsim_common/vehicle.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/vehicle_command_ack.hpp"

namespace idsim_common
{

// 명령 송신자. PX4는 ack를 target_system = source_system, target_component = source_component로
// 돌려준다. component 1000 이상은 PX4가 mode executor로 분류하므로 1-999만 허용한다.
class CommandSource
{
public:
  static std::optional<CommandSource> make(int system, int component);

  std::uint8_t system() const { return system_; }
  std::uint16_t component() const { return component_; }

private:
  CommandSource(std::uint8_t system, std::uint16_t component)
  : system_(system), component_(component)
  {
  }

  std::uint8_t system_;
  std::uint16_t component_;
};

class VehicleCommandBuilder
{
public:
  // source.system() == target.sysid.value()이면 nullopt.
  static std::optional<VehicleCommandBuilder> make(VehicleIdentity target, CommandSource source);

  // 400 COMPONENT_ARM_DISARM, param1 = 1. 강제 시동(21196)은 두지 않는다.
  px4_msgs::msg::VehicleCommand arm(Px4Timestamp timestamp) const;
  // 400 COMPONENT_ARM_DISARM, param1 = 0.
  px4_msgs::msg::VehicleCommand disarm(Px4Timestamp timestamp) const;
  // 176 DO_SET_MODE, param1 = 1(MAV_MODE_FLAG_CUSTOM_MODE_ENABLED), param2 = 6(OFFBOARD).
  px4_msgs::msg::VehicleCommand set_mode_offboard(Px4Timestamp timestamp) const;
  // 176 DO_SET_MODE, param1 = 1, param2 = 4(AUTO), param3 = 3(AUTO_LOITER).
  px4_msgs::msg::VehicleCommand set_mode_hold(Px4Timestamp timestamp) const;
  // 21 NAV_LAND, param1-3 = 0, param4-7 = NaN(현재 위치와 현재 yaw로 착륙).
  px4_msgs::msg::VehicleCommand land(Px4Timestamp timestamp) const;
  // 20 NAV_RETURN_TO_LAUNCH, param 모두 0.
  px4_msgs::msg::VehicleCommand rtl(Px4Timestamp timestamp) const;

  const VehicleIdentity & target() const { return target_; }
  const CommandSource & source() const { return source_; }

private:
  VehicleCommandBuilder(VehicleIdentity target, CommandSource source);

  px4_msgs::msg::VehicleCommand base(std::uint32_t command, Px4Timestamp timestamp) const;

  VehicleIdentity target_;
  CommandSource source_;
};

// ack가 cmd에 대한 응답인가: command가 같고 ack의 target이 cmd의 source다.
bool is_ack_for(
  const px4_msgs::msg::VehicleCommandAck & ack, const px4_msgs::msg::VehicleCommand & cmd);

}  // namespace idsim_common

#endif  // IDSIM_COMMON__VEHICLE_COMMAND_HPP_
