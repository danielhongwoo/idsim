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

// options의 qos_overriding_options가 PX4 QoS를 바꾸지 못하는지 본다.
//
// 이 파일만 노드를 만든다(QoS 덮어쓰기는 노드 파라미터 경로라 노드 없이는 확인할 수 없다).
// 통신은 하지 않는다. tools/ros_ws.sh는 --network none, ROS_DOMAIN_ID=99로 돌린다.
// 결정: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 5, PR #20 px4-engineer 검토 C1.

#include <gtest/gtest.h>

#include <memory>
#include <string>

#include "idsim_common/px4_io.hpp"
#include "idsim_common/px4_topics.hpp"
#include "idsim_common/qos.hpp"
#include "px4_msgs/msg/offboard_control_mode.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/rclcpp.hpp"

namespace px4 = idsim_common::px4;
namespace topics = idsim_common::px4::topics;

namespace
{

class Px4IoNode : public ::testing::Test
{
protected:
  static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
  static void TearDownTestSuite() { rclcpp::shutdown(); }
};

void expect_same_qos(const rclcpp::QoS & actual, const rclcpp::QoS & expected)
{
  EXPECT_EQ(actual.reliability(), expected.reliability());
  EXPECT_EQ(actual.durability(), expected.durability());
  EXPECT_EQ(actual.history(), expected.history());
  EXPECT_EQ(actual.depth(), expected.depth());
}

}  // namespace

TEST_F(Px4IoNode, QosOverridingOptionsAreIgnored)
{
  const auto ns = idsim_common::VehicleNamespace::parse("/px4_1");
  ASSERT_TRUE(ns.has_value());
  const std::string out_topic = px4::topic_name<topics::VehicleStatus>(*ns);
  const std::string in_topic = px4::topic_name<topics::OffboardControlMode>(*ns);

  // 덮어쓰기가 켜지면 RELIABLE, depth 1이 되도록 파라미터를 미리 준다.
  rclcpp::NodeOptions node_options;
  node_options.parameter_overrides({
    {"qos_overrides." + out_topic + ".subscription.reliability", "reliable"},
    {"qos_overrides." + out_topic + ".subscription.depth", 1},
    {"qos_overrides." + in_topic + ".publisher.reliability", "reliable"},
    {"qos_overrides." + in_topic + ".publisher.depth", 1},
  });
  auto node = std::make_shared<rclcpp::Node>("px4_io_qos_probe", node_options);

  rclcpp::SubscriptionOptions sub_options;
  sub_options.qos_overriding_options = rclcpp::QosOverridingOptions::with_default_policies();
  rclcpp::PublisherOptions pub_options;
  pub_options.qos_overriding_options = rclcpp::QosOverridingOptions::with_default_policies();

  auto sub = px4::create_subscription<topics::VehicleStatus>(
    *node, *ns, [](std::shared_ptr<const px4_msgs::msg::VehicleStatus>) {}, sub_options);
  auto pub = px4::create_publisher<topics::OffboardControlMode>(*node, *ns, pub_options);

  expect_same_qos(sub->get_actual_qos(), px4::px4_out_qos());
  expect_same_qos(pub->get_actual_qos(), px4::px4_in_qos());

  // PX4 토픽의 qos_overrides.* 파라미터가 선언되지 않았다. rclcpp가 스스로 만드는
  // qos_overrides./parameter_events.* 는 이 함수와 무관하므로 /fmu/가 든 이름만 본다.
  const auto listed = node->list_parameters({}, 0);
  for (const auto & name : listed.names) {
    if (name.rfind("qos_overrides.", 0) == 0) {
      EXPECT_EQ(name.find("/fmu/"), std::string::npos) << name;
    }
  }
  EXPECT_FALSE(node->has_parameter("qos_overrides." + out_topic + ".subscription.reliability"));
  EXPECT_FALSE(node->has_parameter("qos_overrides." + in_topic + ".publisher.reliability"));
}
