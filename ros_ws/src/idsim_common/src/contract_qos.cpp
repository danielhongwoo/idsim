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

#include "idsim_common/contract_qos.hpp"

namespace idsim_common
{

namespace
{

rclcpp::QoS event_qos()
{
  rclcpp::QoS qos(rclcpp::KeepLast(10));
  qos.reliable().durability_volatile().liveliness(rclcpp::LivelinessPolicy::Automatic);
  return qos;
}

}  // namespace

rclcpp::QoS event_pub_qos() { return event_qos(); }

rclcpp::QoS event_sub_qos() { return event_qos(); }

}  // namespace idsim_common
