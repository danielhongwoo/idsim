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

#include "idsim_common/vehicle_params.hpp"

#include <array>
#include <string>
#include <utility>

namespace idsim_common
{

namespace
{

void set_error(std::string * error, std::string message)
{
  if (error != nullptr) {
    *error = std::move(message);
  }
}

}  // namespace

std::optional<VehicleParams> parse_vehicle_params(
  const std::string & id, const std::string & ns, std::int64_t sysid, std::string * error)
{
  std::string reason;
  const auto vehicle_id = VehicleId::parse(id, &reason);
  if (!vehicle_id) {
    set_error(error, std::string(kParamVehicleId) + ": " + reason);
    return std::nullopt;
  }
  const auto vehicle_ns = VehicleNamespace::parse(ns, &reason);
  if (!vehicle_ns) {
    set_error(error, std::string(kParamVehicleNs) + ": " + reason);
    return std::nullopt;
  }
  // int로 줄이기 전에 범위를 본다(2^32 + 2 같은 값이 2로 접히지 않게).
  const auto vehicle_sysid =
    (sysid >= 1 && sysid <= 255) ? SystemId::make(static_cast<int>(sysid)) : std::nullopt;
  if (!vehicle_sysid) {
    set_error(
      error, std::string(kParamVehicleSysid) + ": out of range 1-255: " + std::to_string(sysid));
    return std::nullopt;
  }
  if (!vehicle_id->matches(*vehicle_ns)) {
    set_error(
      error, std::string(kParamVehicleId) + " '" + id + "' does not match " + kParamVehicleNs +
               " '" + ns + "' (expected ns == '/' + id)");
    return std::nullopt;
  }
  return VehicleParams{*vehicle_id, VehicleIdentity{*vehicle_ns, *vehicle_sysid}};
}

namespace detail
{

std::optional<VehicleParams> parse_vehicle_param_values(
  const rclcpp::ParameterValue & id, const rclcpp::ParameterValue & ns,
  const rclcpp::ParameterValue & sysid, std::string * error)
{
  const std::array<std::pair<const char *, const rclcpp::ParameterValue *>, 3> values = {{
    {kParamVehicleId, &id},
    {kParamVehicleNs, &ns},
    {kParamVehicleSysid, &sysid},
  }};
  for (const auto & [name, value] : values) {
    if (value->get_type() == rclcpp::ParameterType::PARAMETER_NOT_SET) {
      set_error(error, std::string(name) + ": not set (no default; the params file must set it)");
      return std::nullopt;
    }
  }
  if (
    id.get_type() != rclcpp::ParameterType::PARAMETER_STRING ||
    ns.get_type() != rclcpp::ParameterType::PARAMETER_STRING ||
    sysid.get_type() != rclcpp::ParameterType::PARAMETER_INTEGER) {
    set_error(error, "vehicle params have unexpected types");
    return std::nullopt;
  }
  return parse_vehicle_params(
    id.get<std::string>(), ns.get<std::string>(), sysid.get<std::int64_t>(), error);
}

rcl_interfaces::msg::ParameterDescriptor vehicle_param_descriptor(const char * description)
{
  rcl_interfaces::msg::ParameterDescriptor descriptor;
  descriptor.description = description;
  descriptor.read_only = true;
  return descriptor;
}

}  // namespace detail

}  // namespace idsim_common
