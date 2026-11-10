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
