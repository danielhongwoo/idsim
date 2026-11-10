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
