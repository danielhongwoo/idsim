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

// PX4 uXRCE-DDS 토픽의 QoS. PX4 계약을 이 두 함수에만 둔다.
//
// 계약은 reliability와 durability다. PX4 writer(/fmu/out)는 BEST_EFFORT, TRANSIENT_LOCAL이고
// PX4 reader(/fmu/in)는 BEST_EFFORT, VOLATILE이다. 둘 다 BEST_EFFORT, VOLATILE 쪽과 호환된다.
// history와 depth는 계약이 아니다(골든의 depth=1은 rmw가 원격 엔드포인트에 보여 주는 값이다).
// liveliness는 qos_check_compatible이 Warning을 내지 않도록 Automatic을 명시한다
// (DDS 기본값과 같다).

#ifndef IDSIM_COMMON__QOS_HPP_
#define IDSIM_COMMON__QOS_HPP_

#include "rclcpp/qos.hpp"

namespace idsim_common::px4
{

// /fmu/out 구독용. BEST_EFFORT, VOLATILE, KEEP_LAST 5, liveliness Automatic.
// TRANSIENT_LOCAL 구독은 쓰지 않는다(에이전트가 늦게 붙은 reader에 이력을 주지 않음을 실측했다).
rclcpp::QoS px4_out_qos();

// /fmu/in 발행용. BEST_EFFORT, VOLATILE, KEEP_LAST 5, liveliness Automatic.
rclcpp::QoS px4_in_qos();

}  // namespace idsim_common::px4

#endif  // IDSIM_COMMON__QOS_HPP_
