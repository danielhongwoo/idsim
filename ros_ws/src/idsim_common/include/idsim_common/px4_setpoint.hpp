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

// Offboard position setpoint 헬퍼. offboard_control_mode와 trajectory_setpoint는
// 이 두 함수로만 만든다.
//
// 1a는 position 제어만 쓴다(1a 4단계 넘김 (2)는 git 이력, 6단계 쟁점 5). 고정하는 필드:
// - offboard_control_mode: position = true, 나머지 여섯 flag(velocity, acceleration, attitude,
//   body_rate, thrust_and_torque, direct_actuator) = false.
// - trajectory_setpoint: position(NED, m)과 yaw(NED, rad)는 유한값. acceleration, jerk, yawspeed는
//   NaN("제어하지 않음"). velocity는 속도 feedforward 인자가 없으면 NaN, 있으면 그 값(NED, m/s).
//   yaw는 항상 유한값으로 보낸다(NaN yaw의 Offboard 동작은 확인하지 않았다).
// - 속도 feedforward(1b TRACK_ENTITY, plan-1b-mission-target decisions.md 쟁점 8, 14): PX4 위치
//   제어는 position과 함께 온 유한한 velocity를 feedforward로 더한다(mc_pos_control/
//   PositionControl/PositionControl.cpp _positionControl 125-137행). _inputValid(222-247행)는
//   vx, vy가 둘 다 유한이거나 둘 다 NaN이어야 한다고 요구한다. 세 성분을 한 번에 검사하는
//   이유 중 하나다. 속도를 실어도
//   offboard_control_mode는 position만 true 그대로다. 속도 크기는 자르지 않는다(한계는 PX4 위치
//   제어가 적용한다). 언제 싣는가(표본이 신선하고 velocity_valid)는 상태기가 정한다.
// timestamp는 Px4Timestamp 인자로만 받는다(sim 시간 us).
//
// 좌표는 기체 로컬 NED다(PX4가 소비하는 좌표). ENU 값은 호출자가 frames.hpp로 바꿔서 넘긴다.
// 언제 발행하는가(nav_state가 OFFBOARD이거나 Offboard로 들어가는 중일 때만)는 idsim_mission의
// 상태기가 정한다.

#ifndef IDSIM_COMMON__PX4_SETPOINT_HPP_
#define IDSIM_COMMON__PX4_SETPOINT_HPP_

#include <optional>

#include "Eigen/Core"
#include "idsim_common/px4_timestamp.hpp"
#include "px4_msgs/msg/offboard_control_mode.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"

namespace idsim_common::px4
{

// position만 true인 offboard_control_mode.
px4_msgs::msg::OffboardControlMode offboard_position_mode(Px4Timestamp timestamp);

// position_ned(m)와 yaw_ned(rad)가 유한하고 float 범위(절댓값 FLT_MAX 이하) 안일 때만 값을
// 돌려준다. yaw는 wrap하지 않는다. 호출자(상태기)가 frames::wrap_pi로 [-pi, pi)에 넣는다.
// velocity_ned(m/s)가 없으면 velocity는 NaN이다. 있으면 세 성분 모두 같은 검사(유한, float 범위)를
// 통과해야 하고, 하나라도 어긋나면 setpoint 전체가 nullopt다(일부 축만 NaN으로 보내지 않는다).
// acceleration, jerk, yawspeed는 NaN.
std::optional<px4_msgs::msg::TrajectorySetpoint> position_setpoint(
  Px4Timestamp timestamp, const Eigen::Vector3d & position_ned, double yaw_ned,
  const std::optional<Eigen::Vector3d> & velocity_ned = std::nullopt);

}  // namespace idsim_common::px4

#endif  // IDSIM_COMMON__PX4_SETPOINT_HPP_
