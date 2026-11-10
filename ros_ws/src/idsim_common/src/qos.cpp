#include "idsim_common/qos.hpp"

namespace idsim_common::px4
{

namespace
{

rclcpp::QoS px4_qos()
{
  rclcpp::QoS qos(rclcpp::KeepLast(5));
  qos.best_effort().durability_volatile().liveliness(rclcpp::LivelinessPolicy::Automatic);
  return qos;
}

}  // namespace

rclcpp::QoS px4_out_qos() { return px4_qos(); }

rclcpp::QoS px4_in_qos() { return px4_qos(); }

}  // namespace idsim_common::px4
