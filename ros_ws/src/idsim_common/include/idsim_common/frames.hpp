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

// 좌표계 변환. PX4(NED 지구, FRD 동체) <-> ROS(ENU 지구, FLU 동체).
//
// px4_ros_com frame_transforms를 래핑하지 않고 직접 구현한다. 벡터는 축 치환과 부호만 쓰므로
// NaN은 그 축에만 남는다(TrajectorySetpoint는 NaN을 "제어하지 않음"으로 쓴다).
// 원점 이동(월드 ENU <-> 기체 로컬 NED)은 다루지 않는다. 1b에서 원점을 받는 별도 함수로 더한다.
//
// 관례
// - NED: x 북, y 동, z 아래. ENU: x 동, y 북, z 위. 벡터 (n, e, d) <-> (e, n, -d).
// - FRD: x 앞, y 오른쪽, z 아래. FLU: x 앞, y 왼쪽, z 위. 벡터 (f, r, d) <-> (f, -r, -d).
// - PX4 쿼터니언은 Hamilton, 배열 순서 (w, x, y, z), FRD 동체 -> NED 지구 회전(q_ned_frd).
//   ROS 쪽은 FLU 동체 -> ENU 지구 회전(q_enu_flu) = R_enu_ned * q_ned_frd * R_frd_flu.
// - yaw: NED yaw는 북 0, 시계방향 양. ENU yaw는 동 0, 반시계방향 양.
//   yaw_enu = wrap_pi(pi/2 - yaw_ned)이고 역변환도 같은 식이다. 결과는 [-pi, pi).

#ifndef IDSIM_COMMON__FRAMES_HPP_
#define IDSIM_COMMON__FRAMES_HPP_

#include <array>

#include "Eigen/Geometry"

namespace idsim_common::frames
{

// 지구 좌표 벡터(위치, 속도, 가속도).
Eigen::Vector3d ned_to_enu(const Eigen::Vector3d & ned);
Eigen::Vector3d enu_to_ned(const Eigen::Vector3d & enu);

// 동체 좌표 벡터(각속도, 동체 속도 등).
Eigen::Vector3d frd_to_flu(const Eigen::Vector3d & frd);
Eigen::Vector3d flu_to_frd(const Eigen::Vector3d & flu);

// 자세. q_ned_frd(PX4) <-> q_enu_flu(ROS).
Eigen::Quaterniond px4_to_ros_orientation(const Eigen::Quaterniond & q_ned_frd);
Eigen::Quaterniond ros_to_px4_orientation(const Eigen::Quaterniond & q_enu_flu);

// 각을 [-pi, pi)로 감는다. NaN과 무한대는 NaN이 된다.
double wrap_pi(double angle);

// yaw 스칼라. NaN은 NaN으로 남는다.
double ned_to_enu_yaw(double yaw_ned);
double enu_to_ned_yaw(double yaw_enu);

// 대각 분산(position_variance 등). 축 치환만 하고 부호는 바꾸지 않는다.
// 동체 축 FRD <-> FLU는 부호만 바뀌므로 분산이 그대로다(함수를 두지 않는다).
Eigen::Vector3d ned_to_enu_variance(const Eigen::Vector3d & variance_ned);
Eigen::Vector3d enu_to_ned_variance(const Eigen::Vector3d & variance_enu);

// px4_msgs 배열 어댑터. 벡터는 float[3], 쿼터니언은 float[4] (w, x, y, z).
Eigen::Vector3d to_eigen(const std::array<float, 3> & v);
std::array<float, 3> to_px4_array(const Eigen::Vector3d & v);
Eigen::Quaterniond to_eigen_quaternion(const std::array<float, 4> & q);
std::array<float, 4> to_px4_array(const Eigen::Quaterniond & q);

}  // namespace idsim_common::frames

#endif  // IDSIM_COMMON__FRAMES_HPP_
