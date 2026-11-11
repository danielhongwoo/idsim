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

// core::Px4ClockPort의 rclcpp 구현. 소유 px4-engineer.
//
// now_us()는 idsim_common::Px4Timestamp::now(clock)를 불러 성공하면 그 객체를 보관하고
// microseconds()를 돌려준다. 실패하면(sim 시간이 아닌 시계, /clock 수신 전) nullopt이고 보관한 값도
// 비운다. core는 tick마다 많아야 한 번 부른다.
//
// 노드(P3d)는 tick마다 step 전에 begin_tick()으로 보관값을 비우고, step 뒤에 stamp()를
// to_px4_messages에 넘긴다(outputs.hpp). 그러면 앞 tick의 timestamp가 이번 tick의 메시지에 실리는
// 일이 없다. clock은 노드 시계(*node.get_clock())이고 노드보다 오래 살지 않게 노드가 소유한다.

#ifndef IDSIM_MISSION__PX4__CLOCK_PORT_HPP_
#define IDSIM_MISSION__PX4__CLOCK_PORT_HPP_

#include <cstdint>
#include <optional>

#include "idsim_common/px4_timestamp.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "rclcpp/clock.hpp"

namespace idsim_mission::px4
{

class RosPx4ClockPort final : public core::Px4ClockPort
{
public:
  explicit RosPx4ClockPort(rclcpp::Clock & clock) : clock_(clock) {}

  std::optional<std::uint64_t> now_us() override;

  // 이 tick의 보관값을 비운다. step 전에 부른다.
  void begin_tick() { stamp_.reset(); }

  // 이 tick에 now_us()가 성공해 만든 값. 부르지 않았거나 실패했으면 nullopt.
  const std::optional<idsim_common::Px4Timestamp> & stamp() const { return stamp_; }

private:
  rclcpp::Clock & clock_;
  std::optional<idsim_common::Px4Timestamp> stamp_;
};

}  // namespace idsim_mission::px4

#endif  // IDSIM_MISSION__PX4__CLOCK_PORT_HPP_
