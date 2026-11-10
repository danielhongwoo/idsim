#include "idsim_common/vehicle.hpp"

#include <string>
#include <utility>

#include "rmw/validate_namespace.h"

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

std::optional<VehicleNamespace> VehicleNamespace::parse(
  const std::string & text, std::string * error)
{
  if (text.empty()) {
    set_error(error, "vehicle namespace is empty");
    return std::nullopt;
  }
  if (text == "/") {
    set_error(error, "vehicle namespace must not be the root namespace '/'");
    return std::nullopt;
  }
  if (text.front() != '/') {
    set_error(error, "vehicle namespace must be absolute (start with '/'): '" + text + "'");
    return std::nullopt;
  }
  if (text.back() == '/') {
    set_error(error, "vehicle namespace must not end with '/': '" + text + "'");
    return std::nullopt;
  }
  int result = RMW_NAMESPACE_VALID;
  std::size_t index = 0;
  if (rmw_validate_namespace(text.c_str(), &result, &index) != RMW_RET_OK) {
    set_error(error, "rmw_validate_namespace failed for '" + text + "'");
    return std::nullopt;
  }
  if (result != RMW_NAMESPACE_VALID) {
    const char * reason = rmw_namespace_validation_result_string(result);
    set_error(
      error, "invalid vehicle namespace '" + text + "': " +
               (reason != nullptr ? reason : "unknown") + " (index " + std::to_string(index) + ")");
    return std::nullopt;
  }
  return VehicleNamespace(text);
}

std::optional<SystemId> SystemId::make(int value)
{
  if (value < 1 || value > 255) {
    return std::nullopt;
  }
  return SystemId(static_cast<std::uint8_t>(value));
}

IdentityCheck verify(const VehicleIdentity & identity, const px4_msgs::msg::VehicleStatus & status)
{
  if (status.system_id != identity.sysid.value()) {
    return IdentityCheck::SystemIdMismatch;
  }
  if (status.component_id != kAutopilotComponentId) {
    return IdentityCheck::ComponentIdMismatch;
  }
  return IdentityCheck::Match;
}

const char * to_string(IdentityCheck result)
{
  switch (result) {
    case IdentityCheck::Match:
      return "Match";
    case IdentityCheck::SystemIdMismatch:
      return "SystemIdMismatch";
    case IdentityCheck::ComponentIdMismatch:
      return "ComponentIdMismatch";
  }
  return "Unknown";
}

}  // namespace idsim_common
