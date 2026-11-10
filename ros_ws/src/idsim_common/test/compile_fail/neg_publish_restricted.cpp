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

// 음성 컴파일: Restricted /fmu/in 기술자(actuator_motors)로 create_publisher.
// 기대 문구 "publishing to this /fmu/in topic is restricted".

#include "idsim_common/px4_io.hpp"
#include "px4_msgs/msg/actuator_motors.hpp"
#include "rclcpp/node.hpp"

[[maybe_unused]] static const auto kInstantiate =
  &idsim_common::px4::create_publisher<idsim_common::px4::topics::ActuatorMotors, rclcpp::Node>;
