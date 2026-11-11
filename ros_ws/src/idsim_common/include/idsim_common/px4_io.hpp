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

// PX4 토픽 공개 API. 기술자(idsim_common/px4_topics.hpp)를 받아 이름과 QoS를 고정한다.
//
// - topic_name: 구독 가능하거나 발행 허용된 기술자만 받는다.
// - create_subscription: /fmu/out 기술자만. QoS는 px4_out_qos().
// - create_publisher: /fmu/in이면서 Allowed인 기술자만. QoS는 px4_in_qos().
// 세 함수 모두 목록에 등록된 기술자만 받는다. NodeT는 rclcpp::Node와
// rclcpp_lifecycle::LifecycleNode 둘 다 된다.
// create_subscription과 create_publisher는 마지막 인자로 SubscriptionOptions, PublisherOptions를
// 받는다(callback group 지정용, 생략하면 기본값). 이름과 QoS는 options로 바꿀 수 없다.
// options를 별도 overload가 아니라 기본 인자로 둔 이유: 테스트가 함수 템플릿의 주소를 취해
// 인스턴스화를 확인하므로(양성 trait 테스트, 음성 컴파일 테스트) overload 집합이 되면
// 주소가 모호해진다.
//
// 이 차단은 실수 방지 수준이며 보안 경계가 아니다. rclcpp를 직접 부르거나 이름 문자열을 직접 쓰는
// 우회는 lint와 코드 리뷰로 잡는다.

#ifndef IDSIM_COMMON__PX4_IO_HPP_
#define IDSIM_COMMON__PX4_IO_HPP_

#include <string>
#include <utility>

#include "idsim_common/px4_topics.hpp"
#include "idsim_common/qos.hpp"
#include "idsim_common/vehicle.hpp"
#include "rclcpp/publisher_options.hpp"
#include "rclcpp/subscription_options.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace idsim_common::px4
{

template <class Topic>
inline constexpr bool is_subscribable_v =
  detail::is_registered_v<Topic> && Topic::direction == Direction::Out;

template <class Topic>
inline constexpr bool is_publishable_v =
  detail::is_registered_v<Topic> && Topic::direction == Direction::In &&
  Topic::publish == Publish::Allowed;

// 기체 네임스페이스를 붙인 전체 이름. 예: "/px4_1/fmu/out/vehicle_status_v1".
template <class Topic>
std::string topic_name(const VehicleNamespace & ns)
{
  static_assert(
    detail::is_registered_v<Topic>,
    "idsim_common: not a registered px4 topic descriptor; use idsim_common::px4::topics::*");
  static_assert(
    Topic::direction == Direction::Out || Topic::publish == Publish::Allowed,
    "idsim_common: this /fmu/in topic is restricted and has no public name");
  return detail::topic_name<Topic>(ns.str());
}

template <class Topic, class NodeT, class Callback>
auto create_subscription(
  NodeT & node, const VehicleNamespace & ns, Callback && callback,
  const rclcpp::SubscriptionOptions & options = rclcpp::SubscriptionOptions())
{
  static_assert(
    detail::is_registered_v<Topic>,
    "idsim_common: not a registered px4 topic descriptor; use idsim_common::px4::topics::*");
  static_assert(
    Topic::direction == Direction::Out, "idsim_common: subscribe only to /fmu/out descriptors");
  static_assert(
    rosidl_generator_traits::is_message<typename Topic::Msg>::value,
    "idsim_common: include the full px4_msgs/msg/<name>.hpp for this message type");
  return node.template create_subscription<typename Topic::Msg>(
    detail::topic_name<Topic>(ns.str()), px4_out_qos(), std::forward<Callback>(callback), options);
}

template <class Topic, class NodeT>
auto create_publisher(
  NodeT & node, const VehicleNamespace & ns,
  const rclcpp::PublisherOptions & options = rclcpp::PublisherOptions())
{
  static_assert(
    detail::is_registered_v<Topic>,
    "idsim_common: not a registered px4 topic descriptor; use idsim_common::px4::topics::*");
  static_assert(
    Topic::direction == Direction::In, "idsim_common: publish only to /fmu/in descriptors");
  static_assert(
    Topic::publish == Publish::Allowed,
    "idsim_common: publishing to this /fmu/in topic is restricted (see px4_topic_list.inc)");
  static_assert(
    rosidl_generator_traits::is_message<typename Topic::Msg>::value,
    "idsim_common: include the full px4_msgs/msg/<name>.hpp for this message type");
  return node.template create_publisher<typename Topic::Msg>(
    detail::topic_name<Topic>(ns.str()), px4_in_qos(), options);
}

}  // namespace idsim_common::px4

#endif  // IDSIM_COMMON__PX4_IO_HPP_
