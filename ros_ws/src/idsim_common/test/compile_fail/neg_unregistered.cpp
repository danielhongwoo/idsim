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

// 음성 컴파일: 목록 밖에서 만든 같은 모양의 기술자(Allowed /fmu/in)로 create_publisher.
// 기대 문구 "not a registered px4 topic descriptor".

#include <string_view>

#include "idsim_common/px4_io.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "rclcpp/node.hpp"

namespace
{

struct FakeVehicleCommand
{
  using Msg = px4_msgs::msg::VehicleCommand;
  static constexpr idsim_common::px4::Direction direction = idsim_common::px4::Direction::In;
  static constexpr std::string_view base = "vehicle_command";
  static constexpr idsim_common::px4::Publish publish = idsim_common::px4::Publish::Allowed;
};

}  // namespace

[[maybe_unused]] static const auto kInstantiate =
  &idsim_common::px4::create_publisher<FakeVehicleCommand, rclcpp::Node>;
