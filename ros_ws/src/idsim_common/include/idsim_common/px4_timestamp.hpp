// /fmu/in 메시지의 timestamp(us).
//
// SITL은 UXRCE_DDS_SYNCT=0이라 PX4가 /fmu/in timestamp를 보정 없이 쓴다. PX4 hrt는 Gazebo sim
// 시간이므로 idsim 노드는 sim 시간(use_sim_time 노드 시계)을 us로 넣어야 한다.
// 0을 보내면 PX4가 수신 시각으로 채우고, 벽시계 값은 min 클램프로 "지금"이 된다. 둘 다 묵은
// setpoint 판정을 조용히 끈다. 그래서 timestamp는 이 타입으로만 만들고, 생성 경로는 시계를 받는
// now() 하나다. rclcpp::Time 값만으로는 sim 시간인지 구분할 수 없다(구분 정보는 시계에만 있다).

#ifndef IDSIM_COMMON__PX4_TIMESTAMP_HPP_
#define IDSIM_COMMON__PX4_TIMESTAMP_HPP_

#include <cstdint>
#include <optional>

#include "rclcpp/clock.hpp"

namespace idsim_common
{

class Px4Timestamp
{
public:
  // clock이 RCL_ROS_TIME이고 ROS 시간 override가 활성(/clock 구독 중)이며 값이 1 us 이상일 때만
  // 성공한다. 그 외(벽시계 ROS 시계, RCL_SYSTEM_TIME, RCL_STEADY_TIME, /clock 수신 전 0)는 nullopt.
  // Node와 LifecycleNode 모두 *node.get_clock()을 넘긴다.
  static std::optional<Px4Timestamp> now(rclcpp::Clock & clock);

  std::uint64_t microseconds() const { return microseconds_; }

private:
  explicit Px4Timestamp(std::uint64_t microseconds) : microseconds_(microseconds) {}

  std::uint64_t microseconds_;
};

}  // namespace idsim_common

#endif  // IDSIM_COMMON__PX4_TIMESTAMP_HPP_
