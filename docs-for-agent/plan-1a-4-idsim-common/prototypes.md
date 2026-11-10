# 설계 토론 당시의 원형 코드 (참고용)

> 이 파일은 2026-11-10 설계 토론의 원문이다. 본문의 `/tmp/...scratchpad...` 경로와 `re/`, `ws/`, `exp/` 같은 실험 경로는 당시 작업 환경의 임시 파일이라 저장소에 없다. 실험 결과는 본문에 인용된 내용이 전부다.

저장소의 lint가 C++ 파일을 검사 대상으로 삼으므로 원형은 파일이 아니라 이 문서의 코드 블록으로 보존한다. 구현은 이 원형을 그대로 옮기지 말고 decisions.md를 계약으로 따른다(원형에는 reviewer가 지적한 미등록 기술자 우회가 열려 있다).

## ic_probe/cmake/expect_compile_fail.cmake

```cmake
# usage: cmake -DBUILD_DIR= -DTARGET= -DEXPECT_REGEX= -P expect_compile_fail.cmake
execute_process(COMMAND ${CMAKE_COMMAND} --build ${BUILD_DIR} --target ${TARGET}
  RESULT_VARIABLE rc OUTPUT_VARIABLE out ERROR_VARIABLE err)
set(all "${out}${err}")
if(rc EQUAL 0)
  message(FATAL_ERROR "target ${TARGET} compiled but must not")
endif()
if(NOT all MATCHES "${EXPECT_REGEX}")
  message(FATAL_ERROR "target ${TARGET} failed for an unexpected reason:\n${all}")
endif()
message(STATUS "target ${TARGET} failed as expected")
```

## ic_probe/CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.8)
project(ic_probe CXX)
set(CMAKE_CXX_STANDARD 17)
add_compile_options(-Wall -Wextra -Wpedantic -Werror)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(px4_msgs REQUIRED)
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_probe test/test_probe.cpp)
  target_include_directories(test_probe PRIVATE include)
  target_link_libraries(test_probe rclcpp::rclcpp rclcpp_lifecycle::rclcpp_lifecycle ${px4_msgs_TARGETS})
  set(re_VehicleStatus "publish only to /fmu/in")
  set(re_ActuatorMotors "publishing to this /fmu/in topic is restricted")
  set(re_VehicleCommand "publish only to /fmu/in")
  set(re_NoInclude "include the full px4_msgs")
  foreach(neg VehicleStatus ActuatorMotors VehicleCommand NoInclude)
    if(neg STREQUAL "NoInclude")
      add_library(neg_${neg} OBJECT EXCLUDE_FROM_ALL test/neg_noinclude.cpp)
    else()
      add_library(neg_${neg} OBJECT EXCLUDE_FROM_ALL test/neg_publish_out.cpp)
      target_compile_definitions(neg_${neg} PRIVATE NEG_TOPIC=${neg})
    endif()
    target_include_directories(neg_${neg} PRIVATE include)
    target_link_libraries(neg_${neg} rclcpp::rclcpp ${px4_msgs_TARGETS})
    ament_add_test(neg_publish_${neg} GENERATE_RESULT_FOR_RETURN_CODE_ZERO
      COMMAND ${CMAKE_COMMAND} -DBUILD_DIR=${CMAKE_BINARY_DIR} -DTARGET=neg_${neg}
        "-DEXPECT_REGEX=${re_${neg}}"
        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/expect_compile_fail.cmake)
  endforeach()
endif()
ament_package()
```

## ic_probe/include/ic/actuator_motors.hpp

```cpp
#pragma once
#include "ic/topic.hpp"
#include "px4_msgs/msg/detail/actuator_motors__struct.hpp"
namespace ic::topics { IC_TOPIC(ActuatorMotors, px4_msgs::msg::ActuatorMotors, In, "actuator_motors", Restricted) }
```

## ic_probe/include/ic/io.hpp

```cpp
#pragma once
#include <utility>
#include "rclcpp/qos.hpp"
#include "rosidl_runtime_cpp/traits.hpp"
#include "ic/topic.hpp"
namespace ic {
inline rclcpp::QoS px4_out_qos() { return rclcpp::QoS(rclcpp::KeepLast(5)).best_effort().durability_volatile(); }
inline rclcpp::QoS px4_in_qos() { return px4_out_qos(); }
template <class Topic> inline constexpr bool is_subscribable_v = Topic::direction == Direction::Out;
template <class Topic> inline constexpr bool is_publishable_v =
  Topic::direction == Direction::In && Topic::publish == Publish::Allowed;
template <class Topic, class NodeT, class Cb>
auto create_subscription(NodeT & node, std::string_view ns, Cb && cb) {
  static_assert(is_subscribable_v<Topic>, "idsim_common: subscribe only to /fmu/out descriptors");
  static_assert(rosidl_generator_traits::is_message<typename Topic::Msg>::value,
    "idsim_common: include the full px4_msgs/msg/<name>.hpp for this type");
  return node.template create_subscription<typename Topic::Msg>(topic_name<Topic>(ns), px4_out_qos(), std::forward<Cb>(cb));
}
template <class Topic, class NodeT>
auto create_publisher(NodeT & node, std::string_view ns) {
  static_assert(Topic::direction == Direction::In, "idsim_common: publish only to /fmu/in descriptors");
  static_assert(Topic::publish == Publish::Allowed, "idsim_common: publishing to this /fmu/in topic is restricted");
  static_assert(rosidl_generator_traits::is_message<typename Topic::Msg>::value,
    "idsim_common: include the full px4_msgs/msg/<name>.hpp for this type");
  return node.template create_publisher<typename Topic::Msg>(topic_name<Topic>(ns), px4_in_qos());
}
}  // namespace ic
```

## ic_probe/include/ic/topic.hpp

```cpp
#pragma once
#include <cstdint>
#include <string>
#include <string_view>
#include <type_traits>
namespace ic {
enum class Direction { In, Out };
enum class Publish { Allowed, Restricted };
namespace detail {
template <class T, class = void> struct msg_version : std::integral_constant<uint32_t, 0> {};
template <class T> struct msg_version<T, std::void_t<decltype(T::MESSAGE_VERSION)>>
  : std::integral_constant<uint32_t, T::MESSAGE_VERSION> {};
}  // namespace detail
template <class Topic> std::string topic_name(std::string_view ns) {
  std::string s(ns);
  s += Topic::direction == Direction::Out ? "/fmu/out/" : "/fmu/in/";
  s += Topic::base;
  if constexpr (detail::msg_version<typename Topic::Msg>::value != 0) {
    s += "_v" + std::to_string(detail::msg_version<typename Topic::Msg>::value);
  }
  return s;
}
}  // namespace ic
#define IC_TOPIC(NAME, MSG, DIR, BASE, PUB) \
  struct NAME { using Msg = MSG; static constexpr ::ic::Direction direction = ::ic::Direction::DIR; \
    static constexpr std::string_view base = BASE; static constexpr ::ic::Publish publish = ::ic::Publish::PUB; };
```

## ic_probe/include/ic/vehicle_command.hpp

```cpp
#pragma once
#include "ic/topic.hpp"
#include "px4_msgs/msg/detail/vehicle_command__struct.hpp"
namespace ic::topics { IC_TOPIC(VehicleCommand, px4_msgs::msg::VehicleCommand, In, "vehicle_command", Allowed) }
```

## ic_probe/include/ic/vehicle_status.hpp

```cpp
#pragma once
#include "ic/topic.hpp"
#include "px4_msgs/msg/detail/vehicle_status__struct.hpp"
namespace ic::topics { IC_TOPIC(VehicleStatus, px4_msgs::msg::VehicleStatus, Out, "vehicle_status", Restricted) }
```

## ic_probe/package.xml

```xml
<?xml version="1.0"?>
<package format="3">
  <name>ic_probe</name><version>0.0.0</version><description>probe</description>
  <maintainer email="probe@example.com">a</maintainer><license>none</license>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <depend>rclcpp</depend><depend>px4_msgs</depend><depend>rclcpp_lifecycle</depend>
  <test_depend>ament_cmake_gtest</test_depend>
  <export><build_type>ament_cmake</build_type></export>
</package>
```

## ic_probe/test/consumer_noinclude.cpp

```cpp
// consumer that does NOT include the full px4_msgs header; only ic descriptor (struct-only)
#include "rclcpp/rclcpp.hpp"
#include "ic/io.hpp"
#include "ic/vehicle_status.hpp"
void f(rclcpp::Node & n) {
  auto s = ic::create_subscription<ic::topics::VehicleStatus>(n, "/px4_1", [](std::shared_ptr<const px4_msgs::msg::VehicleStatus>) {});
}
```

## ic_probe/test/neg_noinclude.cpp

```cpp
#include "rclcpp/node.hpp"
#include "ic/io.hpp"
#include "ic/vehicle_status.hpp"
[[maybe_unused]] static auto p = &ic::create_subscription<ic::topics::VehicleStatus, rclcpp::Node,
  void (*)(std::shared_ptr<const px4_msgs::msg::VehicleStatus>)>;
```

## ic_probe/test/neg_publish_out.cpp

```cpp
#include "rclcpp/node.hpp"
#include "ic/io.hpp"
#include "ic/vehicle_status.hpp"
#include "ic/vehicle_command.hpp"
#include "ic/actuator_motors.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
#include "px4_msgs/msg/actuator_motors.hpp"
[[maybe_unused]] static auto p = &ic::create_publisher<ic::topics::NEG_TOPIC, rclcpp::Node>;
```

## ic_probe/test/test_probe.cpp

```cpp
#include <gtest/gtest.h>
#include "rclcpp/node.hpp"
#include "rclcpp/qos.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"
#include "ic/io.hpp"
#include "ic/vehicle_status.hpp"
#include "ic/vehicle_command.hpp"
#include "ic/actuator_motors.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"
#include "px4_msgs/msg/vehicle_command.hpp"
using namespace ic;
// positive: force instantiation without creating a node
[[maybe_unused]] static auto kPub = &create_publisher<topics::VehicleCommand, rclcpp::Node>;
[[maybe_unused]] static auto kPubL = &create_publisher<topics::VehicleCommand, rclcpp_lifecycle::LifecycleNode>;
static_assert(is_publishable_v<topics::VehicleCommand>);
static_assert(!is_publishable_v<topics::VehicleStatus>);
static_assert(!is_publishable_v<topics::ActuatorMotors>);
static_assert(is_subscribable_v<topics::VehicleStatus>);
TEST(Probe, Name) {
  EXPECT_EQ(topic_name<topics::VehicleStatus>("/px4_1"), "/px4_1/fmu/out/vehicle_status_v1");
  EXPECT_NE(kPub, nullptr);
}
static const char * res(rclcpp::QoSCompatibility c) {
  switch (c) { case rclcpp::QoSCompatibility::Ok: return "Ok"; case rclcpp::QoSCompatibility::Warning: return "Warning"; default: return "Error"; }
}
TEST(Probe, QosCompat) {
  rclcpp::QoS golden_writer(rclcpp::KeepLast(1));
  golden_writer.best_effort().transient_local();
  auto r = rclcpp::qos_check_compatible(golden_writer, px4_out_qos());
  printf("golden writer vs px4_out_qos: %s '%s'\n", res(r.compatibility), r.reason.c_str());
  EXPECT_EQ(r.compatibility, rclcpp::QoSCompatibility::Ok);
  auto r2 = rclcpp::qos_check_compatible(golden_writer, rclcpp::QoS(5).reliable());
  printf("golden writer vs reliable reader: %s '%s'\n", res(r2.compatibility), r2.reason.c_str());
  rclcpp::QoS vol_writer(1); vol_writer.best_effort().durability_volatile();
  auto r3 = rclcpp::qos_check_compatible(vol_writer, rclcpp::QoS(5).best_effort().transient_local());
  printf("volatile writer vs TL reader: %s '%s'\n", res(r3.compatibility), r3.reason.c_str());
  // PX4 reader for /fmu/in: BE VOLATILE KEEP_LAST
  rclcpp::QoS px4_reader(1); px4_reader.best_effort().durability_volatile();
  auto r4 = rclcpp::qos_check_compatible(px4_in_qos(), px4_reader);
  printf("px4_in_qos vs px4 reader: %s '%s'\n", res(r4.compatibility), r4.reason.c_str());
  EXPECT_EQ(r4.compatibility, rclcpp::QoSCompatibility::Ok);
  // system default liveliness etc
  rclcpp::QoS sd(rclcpp::KeepLast(1), rmw_qos_profile_system_default);
  auto r5 = rclcpp::qos_check_compatible(sd, px4_out_qos());
  {
    rclcpp::QoS w(1); w.best_effort().transient_local().liveliness(rclcpp::LivelinessPolicy::Automatic);
    auto rr = px4_out_qos(); rr.liveliness(rclcpp::LivelinessPolicy::Automatic);
    auto x = rclcpp::qos_check_compatible(w, rr);
    printf("golden writer(auto) vs px4_out_qos(auto): %s '%s'\n", res(x.compatibility), x.reason.c_str());
    auto y = rclcpp::qos_check_compatible(w, px4_out_qos());
    printf("golden writer(auto) vs px4_out_qos(sysdef): %s '%s'\n", res(y.compatibility), y.reason.c_str());
    auto z = rclcpp::qos_check_compatible(golden_writer, rr);
    printf("golden writer(sysdef) vs px4_out_qos(auto): %s '%s'\n", res(z.compatibility), z.reason.c_str());
    auto sd2 = rclcpp::SensorDataQoS();
    printf("SensorDataQoS liveliness=%d deadline=%lld lease=%lld\n", (int)sd2.liveliness(), (long long)sd2.deadline().nanoseconds(), (long long)sd2.liveliness_lease_duration().nanoseconds());
  }
  printf("system_default writer vs px4_out_qos: %s '%s'\n", res(r5.compatibility), r5.reason.c_str());
}
```

## .clang-format 시안 (re/cf/.clang-format)

```yaml
---
Language: Cpp
BasedOnStyle: Google

AccessModifierOffset: -2
AlignAfterOpenBracket: AlwaysBreak
BraceWrapping:
  AfterClass: true
  AfterFunction: true
  AfterNamespace: true
  AfterStruct: true
  AfterEnum: true
BreakBeforeBraces: Custom
ColumnLimit: 100
ConstructorInitializerIndentWidth: 0
ContinuationIndentWidth: 2
DerivePointerAlignment: false
PointerAlignment: Middle
ReflowComments: false
...
```
