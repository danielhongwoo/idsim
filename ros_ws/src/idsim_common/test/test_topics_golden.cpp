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

// 기술자 목록과 PX4 골든(tests/fixtures/px4/<PX4_TAG>/topics.txt)의 양방향 일치,
// PX4_MSGS_REF 3곳 일치.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 2, 9.
// 골든 경로와 PX4_MSGS_REF는 CMake가 docker/versions.env에서 읽어 환경 변수로 넘긴다.

#include <gtest/gtest.h>

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include "idsim_common/px4_topics.hpp"
#include "px4_msgs/msg/detail/actuator_motors__traits.hpp"
#include "px4_msgs/msg/detail/actuator_servos__traits.hpp"
#include "px4_msgs/msg/detail/airspeed_validated__traits.hpp"
#include "px4_msgs/msg/detail/arming_check_reply__traits.hpp"
#include "px4_msgs/msg/detail/arming_check_request__traits.hpp"
#include "px4_msgs/msg/detail/battery_status__traits.hpp"
#include "px4_msgs/msg/detail/collision_constraints__traits.hpp"
#include "px4_msgs/msg/detail/config_overrides__traits.hpp"
#include "px4_msgs/msg/detail/distance_sensor__traits.hpp"
#include "px4_msgs/msg/detail/estimator_status_flags__traits.hpp"
#include "px4_msgs/msg/detail/failsafe_flags__traits.hpp"
#include "px4_msgs/msg/detail/fixed_wing_lateral_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/fixed_wing_longitudinal_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/gimbal_device_attitude_status__traits.hpp"
#include "px4_msgs/msg/detail/goto_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/home_position__traits.hpp"
#include "px4_msgs/msg/detail/landing_gear__traits.hpp"
#include "px4_msgs/msg/detail/lateral_control_configuration__traits.hpp"
#include "px4_msgs/msg/detail/longitudinal_control_configuration__traits.hpp"
#include "px4_msgs/msg/detail/manual_control_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/message_format_request__traits.hpp"
#include "px4_msgs/msg/detail/message_format_response__traits.hpp"
#include "px4_msgs/msg/detail/mode_completed__traits.hpp"
#include "px4_msgs/msg/detail/obstacle_distance__traits.hpp"
#include "px4_msgs/msg/detail/offboard_control_mode__traits.hpp"
#include "px4_msgs/msg/detail/onboard_computer_status__traits.hpp"
#include "px4_msgs/msg/detail/position_setpoint_triplet__traits.hpp"
#include "px4_msgs/msg/detail/register_ext_component_reply__traits.hpp"
#include "px4_msgs/msg/detail/register_ext_component_request__traits.hpp"
#include "px4_msgs/msg/detail/rover_attitude_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/rover_position_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/rover_rate_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/rover_speed_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/rover_steering_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/rover_throttle_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/sensor_combined__traits.hpp"
#include "px4_msgs/msg/detail/sensor_gps__traits.hpp"
#include "px4_msgs/msg/detail/sensor_optical_flow__traits.hpp"
#include "px4_msgs/msg/detail/telemetry_status__traits.hpp"
#include "px4_msgs/msg/detail/timesync_status__traits.hpp"
#include "px4_msgs/msg/detail/trajectory_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/transponder_report__traits.hpp"
#include "px4_msgs/msg/detail/unregister_ext_component__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_attitude__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_attitude_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_command__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_command_ack__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_control_mode__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_global_position__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_land_detected__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_local_position__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_odometry__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_rates_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_status__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_thrust_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/vehicle_torque_setpoint__traits.hpp"
#include "px4_msgs/msg/detail/vtol_vehicle_status__traits.hpp"
#include "px4_msgs/msg/detail/wind__traits.hpp"

namespace px4 = idsim_common::px4;

namespace
{

using Entry = std::pair<std::string, std::string>;  // (상대 토픽 이름, 타입 이름)

std::string require_env(const char * name)
{
  const char * value = std::getenv(name);
  return value == nullptr ? std::string() : std::string(value);
}

std::string fixture_dir()
{
  const std::string dir = require_env("IDSIM_PX4_FIXTURE_DIR");
  EXPECT_FALSE(dir.empty()) << "IDSIM_PX4_FIXTURE_DIR is not set (CMake passes it from "
                               "docker/versions.env; run through colcon test)";
  return dir;
}

std::set<Entry> descriptor_entries(std::size_t * count)
{
  std::set<Entry> out;
  *count = 0;
  px4::detail::for_each_topic([&out, count](auto topic) {
    using T = decltype(topic);
    ++*count;
    // 타입 문자열은 생성 코드가 광고하는 이름으로 만든다(매크로 문자열화를 쓰지 않는다).
    out.emplace(
      px4::detail::relative_topic_name<T>(), rosidl_generator_traits::name<typename T::Msg>());
  });
  return out;
}

std::string strip_version(const std::string & name)
{
  static const std::regex suffix("_v[0-9]+$");
  return std::regex_replace(name, suffix, "");
}

std::string describe(const std::set<Entry> & entries)
{
  std::ostringstream os;
  for (const auto & [name, type] : entries) {
    os << "  " << name << " " << type << " (base without suffix: " << strip_version(name) << ")\n";
  }
  return os.str();
}

std::string read_key(const std::string & path, const std::string & key, int * count)
{
  std::ifstream in(path);
  std::string line;
  std::string value;
  *count = 0;
  while (std::getline(in, line)) {
    if (line.rfind(key + "=", 0) == 0) {
      value = line.substr(key.size() + 1);
      ++*count;
    }
  }
  return value;
}

}  // namespace

TEST(TopicsGolden, DescriptorsMatchGoldenBothWays)
{
  const std::string dir = fixture_dir();
  ASSERT_FALSE(dir.empty());
  const std::string path = dir + "/topics.txt";
  std::ifstream in(path);
  ASSERT_TRUE(in.good()) << "cannot open " << path;

  std::set<Entry> golden;
  std::string line;
  int lines = 0;
  while (std::getline(in, line)) {
    if (line.empty()) {
      continue;
    }
    std::istringstream fields(line);
    std::string name;
    std::string type;
    std::string extra;
    fields >> name >> type;
    ASSERT_FALSE(name.empty() || type.empty() || (fields >> extra)) << "bad golden line: " << line;
    golden.emplace(name, type);
    ++lines;
  }
  ASSERT_GT(lines, 0) << path << " has no topics";
  ASSERT_EQ(golden.size(), static_cast<std::size_t>(lines)) << "duplicate lines in " << path;

  std::size_t count = 0;
  const std::set<Entry> ours = descriptor_entries(&count);
  EXPECT_EQ(ours.size(), count) << "two descriptors map to the same (name, type)";

  std::set<Entry> only_ours;
  std::set<Entry> only_golden;
  for (const auto & e : ours) {
    if (golden.count(e) == 0) {
      only_ours.insert(e);
    }
  }
  for (const auto & e : golden) {
    if (ours.count(e) == 0) {
      only_golden.insert(e);
    }
  }
  EXPECT_TRUE(only_ours.empty() && only_golden.empty())
    << "descriptor list and " << path << " differ.\n"
    << "only in descriptors (" << only_ours.size() << "):\n"
    << describe(only_ours) << "only in golden (" << only_golden.size() << "):\n"
    << describe(only_golden)
    << "Fix include/idsim_common/detail/px4_topic_list.inc (logical names are written without "
       "_vN).";
  std::cout << "descriptors=" << count << " golden=" << lines << std::endl;
}

// 매핑이 파생된 px4_msgs(이미지)와 비교 대상 골든이 같은 조합인지 본다.
TEST(TopicsGolden, Px4MsgsRefMatchesInThreePlaces)
{
  const std::string dir = fixture_dir();
  ASSERT_FALSE(dir.empty());
  int count = 0;
  const std::string golden_ref = read_key(dir + "/env.txt", "PX4_MSGS_REF", &count);
  ASSERT_EQ(count, 1) << dir << "/env.txt must have exactly one PX4_MSGS_REF line";
  const std::string versions_ref = require_env("IDSIM_PX4_MSGS_REF");
  const std::string image_ref = require_env("IDSIM_BUILD_PX4_MSGS_REF");

  const std::string summary = "\n  env.txt PX4_MSGS_REF          = '" + golden_ref +
                              "'\n  versions.env PX4_MSGS_REF     = '" + versions_ref +
                              "'\n  image IDSIM_BUILD_PX4_MSGS_REF = '" + image_ref + "'";
  ASSERT_FALSE(versions_ref.empty())
    << "IDSIM_PX4_MSGS_REF is not set (CMake passes it from docker/versions.env)" << summary;
  ASSERT_FALSE(image_ref.empty())
    << "IDSIM_BUILD_PX4_MSGS_REF is not set. Run inside the ros-ws image with "
       "tools/ros_ws.sh test"
    << summary;
  EXPECT_EQ(golden_ref, versions_ref) << summary;
  EXPECT_EQ(image_ref, versions_ref)
    << "the ros-ws image was built from a different px4_msgs; rebuild it or run inside the "
       "ros-ws image with tools/ros_ws.sh test"
    << summary;
}
