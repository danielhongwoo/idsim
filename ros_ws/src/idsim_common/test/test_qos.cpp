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

// QoS 프로필 대조. 골든의 PX4 writer(qos/fmu/out/*.txt)와 PX4 reader(BE, VOL)에 대해 호환이고,
// RELIABLE reader와 TRANSIENT_LOCAL reader는 호환되지 않음을 본다. 노드를 만들지 않는다.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 3.

#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <string>

#include "idsim_common/px4_topics.hpp"
#include "idsim_common/qos.hpp"
#include "rclcpp/qos.hpp"

namespace px4 = idsim_common::px4;
namespace fs = std::filesystem;

namespace
{

const char * to_string(rclcpp::QoSCompatibility c)
{
  switch (c) {
    case rclcpp::QoSCompatibility::Ok:
      return "Ok";
    case rclcpp::QoSCompatibility::Warning:
      return "Warning";
    case rclcpp::QoSCompatibility::Error:
      return "Error";
  }
  return "Unknown";
}

rclcpp::QoS endpoint(rclcpp::ReliabilityPolicy reliability, rclcpp::DurabilityPolicy durability)
{
  rclcpp::QoS qos(rclcpp::KeepLast(1));
  qos.reliability(reliability).durability(durability);
  qos.liveliness(rclcpp::LivelinessPolicy::Automatic);
  return qos;
}

std::map<std::string, std::string> read_kv(const fs::path & path)
{
  std::map<std::string, std::string> out;
  std::ifstream in(path);
  std::string line;
  while (std::getline(in, line)) {
    const auto eq = line.find('=');
    if (eq != std::string::npos) {
      out[line.substr(0, eq)] = line.substr(eq + 1);
    }
  }
  return out;
}

}  // namespace

TEST(Qos, ProfileValues)
{
  for (const auto & qos : {px4::px4_out_qos(), px4::px4_in_qos()}) {
    EXPECT_EQ(qos.reliability(), rclcpp::ReliabilityPolicy::BestEffort);
    EXPECT_EQ(qos.durability(), rclcpp::DurabilityPolicy::Volatile);
    EXPECT_EQ(qos.history(), rclcpp::HistoryPolicy::KeepLast);
    EXPECT_EQ(qos.depth(), 5U);
    EXPECT_EQ(qos.liveliness(), rclcpp::LivelinessPolicy::Automatic);
  }
}

TEST(Qos, OutQosCompatibleWithEveryGoldenWriter)
{
  const char * dir_env = std::getenv("IDSIM_PX4_FIXTURE_DIR");
  ASSERT_NE(dir_env, nullptr) << "IDSIM_PX4_FIXTURE_DIR is not set (run through colcon test)";
  const fs::path dir = fs::path(dir_env) / "qos" / "fmu" / "out";
  ASSERT_TRUE(fs::is_directory(dir)) << dir;

  std::set<std::string> out_bases;
  px4::detail::for_each_topic([&out_bases](auto topic) {
    using T = decltype(topic);
    if constexpr (T::direction == px4::Direction::Out) {
      out_bases.insert(
        px4::detail::relative_topic_name<T>().substr(std::string("fmu/out/").size()));
    }
  });

  std::set<std::string> seen;
  for (const auto & file : fs::directory_iterator(dir)) {
    if (file.path().extension() != ".txt") {
      continue;
    }
    const std::string topic = file.path().stem().string();
    seen.insert(topic);
    const auto kv = read_kv(file.path());
    // 계약은 reliability와 durability뿐이다. history와 depth는 읽지 않는다.
    ASSERT_EQ(kv.count("reliability"), 1U) << file.path();
    ASSERT_EQ(kv.count("durability"), 1U) << file.path();
    const std::string & rel = kv.at("reliability");
    const std::string & dur = kv.at("durability");
    ASSERT_TRUE(rel == "BEST_EFFORT" || rel == "RELIABLE") << file.path() << ": " << rel;
    ASSERT_TRUE(dur == "TRANSIENT_LOCAL" || dur == "VOLATILE") << file.path() << ": " << dur;
    const auto writer = endpoint(
      rel == "BEST_EFFORT" ? rclcpp::ReliabilityPolicy::BestEffort
                           : rclcpp::ReliabilityPolicy::Reliable,
      dur == "TRANSIENT_LOCAL" ? rclcpp::DurabilityPolicy::TransientLocal
                               : rclcpp::DurabilityPolicy::Volatile);
    const auto result = rclcpp::qos_check_compatible(writer, px4::px4_out_qos());
    EXPECT_EQ(result.compatibility, rclcpp::QoSCompatibility::Ok)
      << topic << ": " << to_string(result.compatibility) << " '" << result.reason << "'";
  }
  EXPECT_FALSE(seen.empty()) << "no golden qos files in " << dir;
  // 골든 qos 파일은 /fmu/out 기술자와 1:1이다.
  EXPECT_EQ(seen, out_bases);
  std::cout << "golden writers checked=" << seen.size() << std::endl;
}

TEST(Qos, InQosCompatibleWithPx4Reader)
{
  // PX4 reader(/fmu/in): BEST_EFFORT, VOLATILE (uxrce_dds_client utilities.hpp).
  const auto reader =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::Volatile);
  const auto result = rclcpp::qos_check_compatible(px4::px4_in_qos(), reader);
  EXPECT_EQ(result.compatibility, rclcpp::QoSCompatibility::Ok)
    << to_string(result.compatibility) << " '" << result.reason << "'";
}

TEST(Qos, NegativeReliableReaderAgainstPx4Writer)
{
  const auto px4_writer =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::TransientLocal);
  const auto reader =
    endpoint(rclcpp::ReliabilityPolicy::Reliable, rclcpp::DurabilityPolicy::Volatile);
  EXPECT_EQ(
    rclcpp::qos_check_compatible(px4_writer, reader).compatibility,
    rclcpp::QoSCompatibility::Error);
}

TEST(Qos, NegativeTransientLocalReaderAgainstVolatileWriter)
{
  const auto writer =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::Volatile);
  const auto reader =
    endpoint(rclcpp::ReliabilityPolicy::BestEffort, rclcpp::DurabilityPolicy::TransientLocal);
  EXPECT_EQ(
    rclcpp::qos_check_compatible(writer, reader).compatibility, rclcpp::QoSCompatibility::Error);
}
