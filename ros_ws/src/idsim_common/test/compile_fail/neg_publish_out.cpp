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

// 음성 컴파일: /fmu/out 기술자(vehicle_status)로 create_publisher.
// 기대 문구 "publish only to /fmu/in".
// 이 파일은 EXCLUDE_FROM_ALL 타깃이며 neg_compile_publish_out 테스트가 빌드 실패를 확인한다.

#include "idsim_common/px4_io.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "rclcpp/node.hpp"

[[maybe_unused]] static const auto kInstantiate =
  &idsim_common::px4::create_publisher<idsim_common::px4::topics::VehicleStatus, rclcpp::Node>;
