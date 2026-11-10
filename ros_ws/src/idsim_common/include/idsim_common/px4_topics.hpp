// PX4 uXRCE-DDS 토픽 기술자. 토픽 이름은 이 헤더의 기술자로만 얻는다.
//
// 기술자(topics::VehicleStatus 등)는 메시지 타입, 방향, 논리 이름, 발행 허용을 하나로 묶는다.
// 호출자는 셋 중 어느 것도 따로 고를 수 없다. 공개 API는 idsim_common/px4_io.hpp에 있다.
// detail 네임스페이스는 idsim_common과 그 테스트만 쓴다(lint가 다른 패키지의 사용을 막는다).
//
// 이 헤더는 메시지 구조체 헤더(detail/<name>__struct.hpp)만 include한다. 기술자를 쓰는 소비자는
// 자기가 쓰는 타입의 전체 헤더(px4_msgs/msg/<name>.hpp)를 include해야 한다. 빠뜨리면 px4_io.hpp의
// static_assert가 막는다.

#ifndef IDSIM_COMMON__PX4_TOPICS_HPP_
#define IDSIM_COMMON__PX4_TOPICS_HPP_

#include <cstdint>
#include <string>
#include <string_view>
#include <type_traits>

#include "px4_msgs/msg/detail/actuator_motors__struct.hpp"
#include "px4_msgs/msg/detail/actuator_servos__struct.hpp"
#include "px4_msgs/msg/detail/airspeed_validated__struct.hpp"
#include "px4_msgs/msg/detail/arming_check_reply__struct.hpp"
#include "px4_msgs/msg/detail/arming_check_request__struct.hpp"
#include "px4_msgs/msg/detail/battery_status__struct.hpp"
#include "px4_msgs/msg/detail/collision_constraints__struct.hpp"
#include "px4_msgs/msg/detail/config_overrides__struct.hpp"
#include "px4_msgs/msg/detail/distance_sensor__struct.hpp"
#include "px4_msgs/msg/detail/estimator_status_flags__struct.hpp"
#include "px4_msgs/msg/detail/failsafe_flags__struct.hpp"
#include "px4_msgs/msg/detail/fixed_wing_lateral_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/fixed_wing_longitudinal_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/gimbal_device_attitude_status__struct.hpp"
#include "px4_msgs/msg/detail/goto_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/home_position__struct.hpp"
#include "px4_msgs/msg/detail/landing_gear__struct.hpp"
#include "px4_msgs/msg/detail/lateral_control_configuration__struct.hpp"
#include "px4_msgs/msg/detail/longitudinal_control_configuration__struct.hpp"
#include "px4_msgs/msg/detail/manual_control_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/message_format_request__struct.hpp"
#include "px4_msgs/msg/detail/message_format_response__struct.hpp"
#include "px4_msgs/msg/detail/mode_completed__struct.hpp"
#include "px4_msgs/msg/detail/obstacle_distance__struct.hpp"
#include "px4_msgs/msg/detail/offboard_control_mode__struct.hpp"
#include "px4_msgs/msg/detail/onboard_computer_status__struct.hpp"
#include "px4_msgs/msg/detail/position_setpoint_triplet__struct.hpp"
#include "px4_msgs/msg/detail/register_ext_component_reply__struct.hpp"
#include "px4_msgs/msg/detail/register_ext_component_request__struct.hpp"
#include "px4_msgs/msg/detail/rover_attitude_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/rover_position_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/rover_rate_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/rover_speed_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/rover_steering_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/rover_throttle_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/sensor_combined__struct.hpp"
#include "px4_msgs/msg/detail/sensor_gps__struct.hpp"
#include "px4_msgs/msg/detail/sensor_optical_flow__struct.hpp"
#include "px4_msgs/msg/detail/telemetry_status__struct.hpp"
#include "px4_msgs/msg/detail/timesync_status__struct.hpp"
#include "px4_msgs/msg/detail/trajectory_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/transponder_report__struct.hpp"
#include "px4_msgs/msg/detail/unregister_ext_component__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_attitude__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_attitude_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_command__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_command_ack__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_control_mode__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_global_position__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_land_detected__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_local_position__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_odometry__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_rates_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_status__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_thrust_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/vehicle_torque_setpoint__struct.hpp"
#include "px4_msgs/msg/detail/vtol_vehicle_status__struct.hpp"
#include "px4_msgs/msg/detail/wind__struct.hpp"

namespace idsim_common::px4
{

// 토픽 방향. In은 /fmu/in(PX4가 구독), Out은 /fmu/out(PX4가 발행).
enum class Direction : std::uint8_t
{
  In,
  Out
};

// /fmu/in 발행 허용. Out 기술자는 모두 Restricted다.
enum class Publish : std::uint8_t
{
  Allowed,
  Restricted
};

namespace detail
{

// PX4 dds_topics.h.em과 같은 규칙: MESSAGE_VERSION 상수가 없으면 0.
template <class T, class = void>
struct msg_version : std::integral_constant<std::uint32_t, 0>
{
};

template <class T>
struct msg_version<T, std::void_t<decltype(T::MESSAGE_VERSION)>>
: std::integral_constant<std::uint32_t, T::MESSAGE_VERSION>
{
};

template <class T>
inline constexpr std::uint32_t msg_version_v = msg_version<T>::value;

// 이름 끝이 _v<숫자>인가. 논리 이름에 접미사를 직접 쓰는 실수를 막는다.
constexpr bool has_version_suffix(std::string_view name)
{
  std::size_t i = name.size();
  while (i > 0 && name[i - 1] >= '0' && name[i - 1] <= '9') {
    --i;
  }
  if (i == name.size() || i < 2) {
    return false;
  }
  return name[i - 1] == 'v' && name[i - 2] == '_';
}

// 기술자 목록(px4_topic_list.inc)에 있는 기술자만 true.
// 목록 밖에서 만든 같은 모양의 struct는 false.
template <class T>
struct is_registered : std::false_type
{
};

template <class T>
inline constexpr bool is_registered_v = is_registered<T>::value;

// 네임스페이스를 뺀 상대 이름. 예: "fmu/out/vehicle_status_v1".
template <class Topic>
std::string relative_topic_name()
{
  std::string name(Topic::direction == Direction::Out ? "fmu/out/" : "fmu/in/");
  name += Topic::base;
  if constexpr (msg_version_v<typename Topic::Msg> != 0) {
    name += "_v";
    name += std::to_string(msg_version_v<typename Topic::Msg>);
  }
  return name;
}

// 네임스페이스(절대 경로, 끝 빗금 없음)를 붙인 이름. 검증하지 않는다.
// 공개 API는 px4_io.hpp의 topic_name.
template <class Topic>
std::string topic_name(std::string_view ns)
{
  std::string name(ns);
  name += '/';
  name += relative_topic_name<Topic>();
  return name;
}

}  // namespace detail

// 기술자 정의. 목록 끝에서 #undef한다(목록 밖에서 매크로를 다시 써서 기술자를 등록하지 못하게).
#define IDSIM_PX4_TOPIC(NAME, MSG, DIR, BASE, PUB)                                             \
  namespace topics                                                                             \
  {                                                                                            \
  struct NAME                                                                                  \
  {                                                                                            \
    using Msg = MSG;                                                                           \
    static constexpr ::idsim_common::px4::Direction direction =                                \
      ::idsim_common::px4::Direction::DIR;                                                     \
    static constexpr std::string_view base = BASE;                                             \
    static constexpr ::idsim_common::px4::Publish publish = ::idsim_common::px4::Publish::PUB; \
    static_assert(                                                                             \
      !::idsim_common::px4::detail::has_version_suffix(base),                                  \
      "idsim_common: write the logical name without _v<N>; the suffix comes from "             \
      "MESSAGE_VERSION");                                                                      \
    static_assert(                                                                             \
      direction == ::idsim_common::px4::Direction::In ||                                       \
        publish == ::idsim_common::px4::Publish::Restricted,                                   \
      "idsim_common: /fmu/out descriptors must be Restricted");                                \
  };                                                                                           \
  } /* namespace topics. NOLINT(readability/namespace) */                                      \
  template <>                                                                                  \
  struct detail::is_registered<topics::NAME> : std::true_type                                  \
  {                                                                                            \
  };

#include "idsim_common/detail/px4_topic_list.inc"

#undef IDSIM_PX4_TOPIC

namespace detail
{

// 등록된 기술자 전체의 타입 목록. 테스트(골든 대조, trait 전수 검사)가 쓴다.
template <class... Ts>
struct type_list
{
};

struct list_end
{
};

#define IDSIM_PX4_TOPIC(NAME, MSG, DIR, BASE, PUB) topics::NAME,
using all_topics_with_end = type_list<
#include "idsim_common/detail/px4_topic_list.inc"  // NOLINT(build/include)
  list_end>;
#undef IDSIM_PX4_TOPIC

// f(T{})를 기술자마다 부른다. 기술자 struct는 빈 struct라 값으로 넘긴다.
template <class F, class... Ts>
void for_each_topic_impl(F && f, type_list<Ts...>)
{
  (
    [&f]() {
      if constexpr (!std::is_same_v<Ts, list_end>) {
        f(Ts{});
      }
    }(),
    ...);
}

template <class F>
void for_each_topic(F && f)
{
  for_each_topic_impl(f, all_topics_with_end{});
}

}  // namespace detail

}  // namespace idsim_common::px4

#endif  // IDSIM_COMMON__PX4_TOPICS_HPP_
