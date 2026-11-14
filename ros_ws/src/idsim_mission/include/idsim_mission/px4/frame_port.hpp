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

// PX4 어댑터의 좌표 기준 쪽: vehicle_local_position의 기준(ref_*) -> core::FramePort.
// 소유 px4-engineer.
//
// 대응의 정본은 core/snapshot.hpp 머리 주석의 FramePort 행이고, 결정은 decisions.md 쟁점 4다.
// - 기준 유효 술어는 local_reference_from_px4 하나에 둔다: xy_global과 z_global이 true,
//   ref_lat, ref_lon, ref_alt가 유한, ref_alt가 정확히 0.0이 아니다. PX4는 고도 원점이 없을 때
//   ref_alt에 NaN이 아니라 0을 내고 z_global은 위경도 원점만 본다(EKF2.cpp,
//   estimator_interface.h). 그래서 z_global이 true여도 ref_alt 0은 무효로 본다.
// - 기준은 그 tick의 Snapshot.position과 같은 표본에서 읽는다. 노드(P3d)는 vehicle_local_position
//   callback에서 to_local_position_input으로 둘을 한 번에 만들어 함께 보관하고, tick마다 그
//   기준으로 Px4FramePort를 만들어 step에 넘긴다. 예:
//
//     // callback
//     position_input_ = to_local_position_input(*msg, next_tick_);
//     snapshot_.position = position_input_->position;
//     // tick
//     const Px4FramePort frame(world_origin_, position_input_->reference);
//
//   비행 중 기준이 바뀌면(ref_timestamp_us가 달라지면) 노드가 WARN 한 줄을 남긴다(쟁점 4
//   "원점 변경").
// - 식은 idsim_common::geo::world_enu_to_local_ned(점)와 idsim_common::frames::enu_to_ned(벡터)다.
//   이 파일은 술어와 형 변환만 하고 식을 다시 쓰지 않는다.
//
// 순수 코드다(노드, 시계, DDS 없음).

#ifndef IDSIM_MISSION__PX4__FRAME_PORT_HPP_
#define IDSIM_MISSION__PX4__FRAME_PORT_HPP_

#include <cstdint>
#include <optional>

#include "idsim_common/geo.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"
#include "px4_msgs/msg/vehicle_local_position.hpp"

namespace idsim_mission::px4
{

// 기준 유효 술어(decisions.md 쟁점 4). 참이면 ref_lat, ref_lon(도), ref_alt(m, float32 -> double)를
// 돌려주고, 하나라도 어긋나면 nullopt.
std::optional<idsim_common::geo::LocalReference> local_reference_from_px4(
  const px4_msgs::msg::VehicleLocalPosition & msg);

// vehicle_local_position 표본 하나에서 만든 위치와 기준. 둘이 같은 표본에서 나왔음을 형으로 묶는다.
struct LocalPositionInput
{
  // to_position_sample과 같다.
  core::PositionSample position;
  // local_reference_from_px4와 같다.
  std::optional<idsim_common::geo::LocalReference> reference;
  // vehicle_local_position.ref_timestamp(us). 원점 변경 WARN에만 쓴다.
  std::uint64_t ref_timestamp_us{0};
};

LocalPositionInput to_local_position_input(
  const px4_msgs::msg::VehicleLocalPosition & msg, std::uint64_t received_tick);

// core::FramePort 구현. 한 tick의 기준(reference)과 params의 world.origin으로 만든다.
// - world_to_local: 기준이 없으면 nullopt. 기준이 있어도 입력이나 결과가 비유한이면 nullopt다
//   (비유한 setpoint는 어댑터 출력에서 짝째 버려져 발행이 끊기므로, core가 직전 setpoint를
//   유지하도록 값 없음으로 둔다).
// - world_velocity_to_local: 기준과 무관한 축 치환. 비유한 입력은 비유한 출력이다.
class Px4FramePort final : public core::FramePort
{
public:
  Px4FramePort(
    const idsim_common::geo::WorldOrigin & origin,
    const std::optional<idsim_common::geo::LocalReference> & reference)
  : origin_(origin), reference_(reference)
  {
  }

  std::optional<core::Vec3> world_to_local(const core::Vec3 & world_enu) const override;
  core::Vec3 world_velocity_to_local(const core::Vec3 & world_enu) const override;

  bool reference_valid() const { return reference_.has_value(); }

private:
  idsim_common::geo::WorldOrigin origin_;
  std::optional<idsim_common::geo::LocalReference> reference_;
};

}  // namespace idsim_mission::px4

#endif  // IDSIM_MISSION__PX4__FRAME_PORT_HPP_
