// 음성 컴파일: 메시지 전체 헤더(px4_msgs/msg/vehicle_status.hpp) 없이 create_subscription.
// 기술자 헤더는 구조체 헤더만 include하므로 is_message가 false다.
// 기대 문구 "include the full px4_msgs".

#include <functional>
#include <memory>

#include "idsim_common/px4_io.hpp"
#include "rclcpp/node.hpp"

using StatusCallback = std::function<void(std::shared_ptr<const px4_msgs::msg::VehicleStatus>)>;

[[maybe_unused]] static const auto kInstantiate = &idsim_common::px4::create_subscription<
  idsim_common::px4::topics::VehicleStatus, rclcpp::Node, StatusCallback>;
