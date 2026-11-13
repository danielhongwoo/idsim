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

// idsim 계약 토픽(idsim_interfaces)의 QoS. PX4 토픽의 QoS는 qos.hpp에 있다.
//
// 상태 토픽(VehicleState, TargetState): 발행 RELIABLE, VOLATILE, 구독 BEST_EFFORT, VOLATILE.
// 둘 다 KEEP_LAST 5, liveliness Automatic(history와 depth는 구현 값이고 계약이 아니다).
// 구독이 BEST_EFFORT인 것은 라이브 발행자(RELIABLE)와 rosbag2 재생 발행자 어느 쪽과도 맞게 하려는
// 것이다. 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 3, 14.
//
// 사건 토픽(MissionEvent): RELIABLE, VOLATILE, KEEP_LAST 10, liveliness Automatic.
// VOLATILE인 이유: TRANSIENT_LOCAL이면 지난 실행의 사건이 새 구독자에게 현재 사건으로 보인다
// (1a 5단계 결정, 6단계 쟁점 7에서 유지). 그래서 TRANSIENT_LOCAL 구독은 이 발행과 맞지 않는다.
// 발행과 구독을 따로 두는 것은 한쪽만 바뀌는 일이 생겨도 부르는 곳을 바꾸지 않기 위해서다.
// 이 헤더는 idsim_interfaces에 의존하지 않는다(토픽 이름은 계약 메시지의 상수를 쓴다).

#ifndef IDSIM_COMMON__CONTRACT_QOS_HPP_
#define IDSIM_COMMON__CONTRACT_QOS_HPP_

#include "rclcpp/qos.hpp"

namespace idsim_common
{

// 상태 발행용. RELIABLE, VOLATILE, KEEP_LAST 5, liveliness Automatic.
// Python 발행자(표적 어댑터)는 이 함수를 쓰지 못하므로 같은 값을 다시 적는다.
rclcpp::QoS state_pub_qos();

// 상태 구독용. BEST_EFFORT, VOLATILE, KEEP_LAST 5, liveliness Automatic.
rclcpp::QoS state_sub_qos();

// 사건 발행용. RELIABLE, VOLATILE, KEEP_LAST 10, liveliness Automatic.
rclcpp::QoS event_pub_qos();

// 사건 구독용. 발행과 같은 값. BEST_EFFORT 구독도 맞기는 하지만 사건을 잃을 수 있어 계약 위반이다.
rclcpp::QoS event_sub_qos();

}  // namespace idsim_common

#endif  // IDSIM_COMMON__CONTRACT_QOS_HPP_
