// 토픽 기술자의 방향과 발행 허용 trait 전수 검사, 허용 목록 명시 비교, msg_version 규칙.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 2.

#include <gtest/gtest.h>

#include <cstdint>
#include <functional>
#include <memory>
#include <set>
#include <string>
#include <string_view>

#include "idsim_common/px4_io.hpp"
#include "idsim_common/px4_topics.hpp"
#include "px4_msgs/msg/offboard_control_mode.hpp"
#include "px4_msgs/msg/trajectory_setpoint.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/node.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

namespace px4 = idsim_common::px4;
namespace topics = idsim_common::px4::topics;

namespace
{

// ---- msg_version 규칙: 상수가 없으면 0, 있으면 그 값 ----
struct NoVersion
{
};
struct VersionZero
{
  static constexpr std::uint32_t MESSAGE_VERSION = 0;
};
struct VersionThree
{
  static constexpr std::uint32_t MESSAGE_VERSION = 3;
};

static_assert(px4::detail::msg_version_v<NoVersion> == 0);
static_assert(px4::detail::msg_version_v<VersionZero> == 0);
static_assert(px4::detail::msg_version_v<VersionThree> == 3);
// px4_msgs 고정 커밋의 실제 값(opinion-px4.md P1).
static_assert(px4::detail::msg_version_v<px4_msgs::msg::VehicleStatus> == 1);
static_assert(px4::detail::msg_version_v<px4_msgs::msg::OffboardControlMode> == 0);
static_assert(px4::detail::msg_version_v<px4_msgs::msg::VehicleCommand> == 0);

static_assert(px4::detail::has_version_suffix("vehicle_status_v1"));
static_assert(px4::detail::has_version_suffix("x_v12"));
static_assert(!px4::detail::has_version_suffix("vehicle_status"));
static_assert(!px4::detail::has_version_suffix("vehicle_status_v"));
static_assert(!px4::detail::has_version_suffix("v1"));
static_assert(!px4::detail::has_version_suffix("rover_v"));
static_assert(!px4::detail::has_version_suffix(""));

// 목록 밖에서 만든 같은 모양의 struct. 등록되지 않았으므로 어떤 공개 API도 받지 않는다.
struct UnregisteredVehicleCommand
{
  using Msg = px4_msgs::msg::VehicleCommand;
  static constexpr px4::Direction direction = px4::Direction::In;
  static constexpr std::string_view base = "vehicle_command";
  static constexpr px4::Publish publish = px4::Publish::Allowed;
};

static_assert(px4::detail::is_registered_v<topics::VehicleCommand>);
static_assert(!px4::detail::is_registered_v<UnregisteredVehicleCommand>);
static_assert(!px4::is_publishable_v<UnregisteredVehicleCommand>);
static_assert(!px4::is_subscribable_v<UnregisteredVehicleCommand>);

static_assert(px4::is_publishable_v<topics::VehicleCommand>);
static_assert(px4::is_publishable_v<topics::OffboardControlMode>);
static_assert(px4::is_publishable_v<topics::TrajectorySetpoint>);
static_assert(!px4::is_publishable_v<topics::VehicleStatus>);
static_assert(!px4::is_publishable_v<topics::ActuatorMotors>);
static_assert(!px4::is_publishable_v<topics::VehicleCommandModeExecutor>);
static_assert(px4::is_subscribable_v<topics::VehicleStatus>);
static_assert(!px4::is_subscribable_v<topics::VehicleCommand>);

// ---- 양성: 공개 템플릿 본문을 노드 없이 인스턴스화한다(Node와 LifecycleNode) ----
using StatusCallback = std::function<void(std::shared_ptr<const px4_msgs::msg::VehicleStatus>)>;
[[maybe_unused]] const auto kPublisherNode =
  &px4::create_publisher<topics::VehicleCommand, rclcpp::Node>;
[[maybe_unused]] const auto kPublisherLifecycle =
  &px4::create_publisher<topics::TrajectorySetpoint, rclcpp_lifecycle::LifecycleNode>;
[[maybe_unused]] const auto kSubscriptionNode =
  &px4::create_subscription<topics::VehicleStatus, rclcpp::Node, StatusCallback>;
[[maybe_unused]] const auto kSubscriptionLifecycle =
  &px4::create_subscription<topics::VehicleStatus, rclcpp_lifecycle::LifecycleNode, StatusCallback>;

}  // namespace

TEST(TopicsTraits, PositiveInstantiation)
{
  EXPECT_NE(kPublisherNode, nullptr);
  EXPECT_NE(kPublisherLifecycle, nullptr);
  EXPECT_NE(kSubscriptionNode, nullptr);
  EXPECT_NE(kSubscriptionLifecycle, nullptr);
}

TEST(TopicsTraits, EveryDescriptorDirectionAndPublish)
{
  int count = 0;
  px4::detail::for_each_topic([&count](auto topic) {
    using T = decltype(topic);
    ++count;
    const std::string name(T::base);
    EXPECT_TRUE(px4::detail::is_registered_v<T>) << name;
    if constexpr (T::direction == px4::Direction::Out) {
      EXPECT_TRUE(px4::is_subscribable_v<T>) << name;
      EXPECT_FALSE(px4::is_publishable_v<T>) << name;
      EXPECT_EQ(T::publish, px4::Publish::Restricted) << name;
    } else {
      EXPECT_FALSE(px4::is_subscribable_v<T>) << name;
      EXPECT_EQ(px4::is_publishable_v<T>, T::publish == px4::Publish::Allowed) << name;
    }
    EXPECT_FALSE(px4::detail::has_version_suffix(T::base)) << name;
  });
  EXPECT_EQ(count, 65);
}

// Restricted -> Allowed 해제 절차의 (4). 기대 집합을 바꾸려면
// px4_topic_list.inc 머리말의 다섯 가지를
// 한 PR에 함께 둔다.
TEST(TopicsTraits, AllowListIsExactlyThree)
{
  std::set<std::string> allowed;
  px4::detail::for_each_topic([&allowed](auto topic) {
    using T = decltype(topic);
    if constexpr (px4::is_publishable_v<T>) {
      allowed.insert(std::string(T::base));
    }
  });
  const std::set<std::string> expected = {
    "offboard_control_mode", "trajectory_setpoint", "vehicle_command"};
  EXPECT_EQ(allowed, expected);
}

TEST(TopicsTraits, PublicTopicNames)
{
  const auto ns1 = idsim_common::VehicleNamespace::parse("/px4_1");
  const auto ns2 = idsim_common::VehicleNamespace::parse("/px4_2");
  ASSERT_TRUE(ns1.has_value());
  ASSERT_TRUE(ns2.has_value());
  EXPECT_EQ(px4::topic_name<topics::VehicleStatus>(*ns1), "/px4_1/fmu/out/vehicle_status_v1");
  EXPECT_EQ(
    px4::topic_name<topics::VehicleLocalPosition>(*ns1),
    "/px4_1/fmu/out/vehicle_local_position_v1");
  EXPECT_EQ(px4::topic_name<topics::VehicleCommandAck>(*ns1), "/px4_1/fmu/out/vehicle_command_ack");
  EXPECT_EQ(
    px4::topic_name<topics::VehicleGpsPosition>(*ns1), "/px4_1/fmu/out/vehicle_gps_position");
  EXPECT_EQ(px4::topic_name<topics::VehicleCommand>(*ns1), "/px4_1/fmu/in/vehicle_command");
  EXPECT_EQ(
    px4::topic_name<topics::OffboardControlMode>(*ns2), "/px4_2/fmu/in/offboard_control_mode");
  EXPECT_EQ(px4::topic_name<topics::TrajectorySetpoint>(*ns2), "/px4_2/fmu/in/trajectory_setpoint");
}

TEST(TopicsTraits, ModeCompletedHasBothDirections)
{
  // key는 (방향, 논리 이름)이다. 같은 논리 이름이 in과 out에 있다.
  EXPECT_EQ(topics::ModeCompletedIn::base, topics::ModeCompletedOut::base);
  EXPECT_EQ(px4::detail::relative_topic_name<topics::ModeCompletedIn>(), "fmu/in/mode_completed");
  EXPECT_EQ(px4::detail::relative_topic_name<topics::ModeCompletedOut>(), "fmu/out/mode_completed");
}
