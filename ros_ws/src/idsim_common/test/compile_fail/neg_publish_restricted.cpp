// 음성 컴파일: Restricted /fmu/in 기술자(actuator_motors)로 create_publisher.
// 기대 문구 "publishing to this /fmu/in topic is restricted".

#include "idsim_common/px4_io.hpp"
#include "px4_msgs/msg/actuator_motors.hpp"
#include "rclcpp/node.hpp"

[[maybe_unused]] static const auto kInstantiate =
  &idsim_common::px4::create_publisher<idsim_common::px4::topics::ActuatorMotors, rclcpp::Node>;
