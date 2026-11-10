// 음성 컴파일: /fmu/out 기술자(vehicle_status)로 create_publisher.
// 기대 문구 "publish only to /fmu/in".
// 이 파일은 EXCLUDE_FROM_ALL 타깃이며 neg_compile_publish_out 테스트가 빌드 실패를 확인한다.

#include "idsim_common/px4_io.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/node.hpp"

[[maybe_unused]] static const auto kInstantiate =
  &idsim_common::px4::create_publisher<idsim_common::px4::topics::VehicleStatus, rclcpp::Node>;
