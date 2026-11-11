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

// 사건 토픽 QoS의 값과 호환 대조. 노드를 만들지 않는다.
// 결정: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 5, 7.

#include <gtest/gtest.h>

#include "idsim_common/contract_qos.hpp"
#include "rclcpp/qos.hpp"

namespace
{

rclcpp::QoS endpoint(rclcpp::ReliabilityPolicy reliability, rclcpp::DurabilityPolicy durability)
{
  rclcpp::QoS qos(rclcpp::KeepLast(10));
  qos.reliability(reliability).durability(durability);
  qos.liveliness(rclcpp::LivelinessPolicy::Automatic);
  return qos;
}

}  // namespace

TEST(ContractQos, EventProfileValues)
{
  for (const auto & qos : {idsim_common::event_pub_qos(), idsim_common::event_sub_qos()}) {
    EXPECT_EQ(qos.reliability(), rclcpp::ReliabilityPolicy::Reliable);
    EXPECT_EQ(qos.durability(), rclcpp::DurabilityPolicy::Volatile);
    EXPECT_EQ(qos.history(), rclcpp::HistoryPolicy::KeepLast);
    EXPECT_EQ(qos.depth(), 10U);
    EXPECT_EQ(qos.liveliness(), rclcpp::LivelinessPolicy::Automatic);
  }
}

TEST(ContractQos, EventPubSubCompatible)
{
  const auto result =
    rclcpp::qos_check_compatible(idsim_common::event_pub_qos(), idsim_common::event_sub_qos());
  EXPECT_EQ(result.compatibility, rclcpp::QoSCompatibility::Ok) << result.reason;
}

TEST(ContractQos, BestEffortSubscriberMatchesButIsNotContract)
{
  // DDS로는 맞는다. 그러나 사건을 잃을 수 있어 계약 위반이다(구독은 event_sub_qos를 쓴다).
  const auto reader =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::Volatile);
  EXPECT_EQ(
    rclcpp::qos_check_compatible(idsim_common::event_pub_qos(), reader).compatibility,
    rclcpp::QoSCompatibility::Ok);
}

TEST(ContractQos, NegativeTransientLocalSubscriberAgainstEventPublisher)
{
  // MissionEvent는 VOLATILE이다. TRANSIENT_LOCAL 구독은 맺어지지 않는다.
  const auto reader =
    endpoint(rclcpp::ReliabilityPolicy::Reliable, rclcpp::DurabilityPolicy::TransientLocal);
  EXPECT_EQ(
    rclcpp::qos_check_compatible(idsim_common::event_pub_qos(), reader).compatibility,
    rclcpp::QoSCompatibility::Error);
}

TEST(ContractQos, NegativeEventSubscriberAgainstBestEffortPublisher)
{
  // 발행 쪽이 BEST_EFFORT로 바뀌면 RELIABLE 구독과 맺어지지 않는다.
  const auto writer =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::Volatile);
  EXPECT_EQ(
    rclcpp::qos_check_compatible(writer, idsim_common::event_sub_qos()).compatibility,
    rclcpp::QoSCompatibility::Error);
}
