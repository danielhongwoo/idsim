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

// 기체 식별 params(vehicle.id, vehicle.ns, vehicle.sysid)의 선언과 해석.
//
// 값의 출처는 생성기 하나다(stack.json에서 만든 params 파일의 "/**"). 노드는 이 세 key에 기본값을
// 두지 않는다. 누락, 타입 불일치, 해석 실패는 모두 nullopt와 error로 돌려주고, 노드는
// on_configure를 FAILURE로 끝낸다.
//
// - parse_vehicle_params: 순수 함수. 단위 테스트는 이것만 시험한다(노드를 만들지 않는다).
// - declare_vehicle_params: 노드에 세 key를 선언하고(정적 타입, read_only, 기본값 없음) 값을
//   parse_vehicle_params로 넘기는 얇은 함수. 노드 네임스페이스(get_namespace())와 vehicle.ns의
//   대조는 하지 않는다. 그것은 노드가 한다.

#ifndef IDSIM_COMMON__VEHICLE_PARAMS_HPP_
#define IDSIM_COMMON__VEHICLE_PARAMS_HPP_

#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>

#include "idsim_common/vehicle.hpp"
#include "rcl_interfaces/msg/parameter_descriptor.hpp"
#include "rclcpp/parameter_value.hpp"

namespace idsim_common
{

inline constexpr const char * kParamVehicleId = "vehicle.id";
inline constexpr const char * kParamVehicleNs = "vehicle.ns";
inline constexpr const char * kParamVehicleSysid = "vehicle.sysid";

struct VehicleParams
{
  VehicleId id;
  VehicleIdentity identity;
};

// id는 VehicleId::parse, ns는 VehicleNamespace::parse, sysid는 SystemId::make(1-255)를 통과해야
// 하고 id.matches(ns)여야 한다. 하나라도 틀리면 nullopt이고, error가 있으면 key 이름과
// 이유를 적는다.
std::optional<VehicleParams> parse_vehicle_params(
  const std::string & id, const std::string & ns, std::int64_t sysid,
  std::string * error = nullptr);

namespace detail
{

// 선언으로 받은 값 셋을 해석한다. 하나라도 미설정(PARAMETER_NOT_SET)이면 nullopt.
std::optional<VehicleParams> parse_vehicle_param_values(
  const rclcpp::ParameterValue & id, const rclcpp::ParameterValue & ns,
  const rclcpp::ParameterValue & sysid, std::string * error);

rcl_interfaces::msg::ParameterDescriptor vehicle_param_descriptor(const char * description);

}  // namespace detail

// NodeT는 rclcpp::Node와 rclcpp_lifecycle::LifecycleNode. 세 key는 한 번만 선언할 수 있어
// 두 번째 호출은 "already declared" 오류로 nullopt다. 노드 수명 동안 한 번만 부른다(생성자 권장).
// on_configure에서 부르면 재configure가 실패한다.
template <class NodeT>
std::optional<VehicleParams> declare_vehicle_params(NodeT & node, std::string * error = nullptr)
{
  try {
    const rclcpp::ParameterValue id = node.declare_parameter(
      kParamVehicleId, rclcpp::ParameterType::PARAMETER_STRING,
      detail::vehicle_param_descriptor("contract vehicle_id, e.g. px4_1"));
    const rclcpp::ParameterValue ns = node.declare_parameter(
      kParamVehicleNs, rclcpp::ParameterType::PARAMETER_STRING,
      detail::vehicle_param_descriptor("vehicle namespace, e.g. /px4_1"));
    const rclcpp::ParameterValue sysid = node.declare_parameter(
      kParamVehicleSysid, rclcpp::ParameterType::PARAMETER_INTEGER,
      detail::vehicle_param_descriptor("PX4 MAV_SYS_ID, 1-255"));
    return detail::parse_vehicle_param_values(id, ns, sysid, error);
  } catch (const std::runtime_error & e) {
    // rclcpp의 InvalidParameterTypeException(params 파일의 타입이 다름),
    // ParameterAlreadyDeclaredException 등.
    if (error != nullptr) {
      *error = std::string("cannot declare vehicle params: ") + e.what();
    }
    return std::nullopt;
  }
}

}  // namespace idsim_common

#endif  // IDSIM_COMMON__VEHICLE_PARAMS_HPP_
