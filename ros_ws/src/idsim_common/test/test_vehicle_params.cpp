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

// vehicle params 해석. 순수 함수만 시험한다(노드를 만들지 않는다). declare_vehicle_params는
// 주소를 취해 Node와 LifecycleNode로 인스턴스화되는지만 본다.
// 결정: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 2, 5.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>

#include "idsim_common/vehicle_params.hpp"
#include "rclcpp/node.hpp"
#include "rclcpp/parameter_value.hpp"
#include "rclcpp_lifecycle/lifecycle_node.hpp"

using idsim_common::parse_vehicle_params;

namespace
{

[[maybe_unused]] const auto kDeclareNode = &idsim_common::declare_vehicle_params<rclcpp::Node>;
[[maybe_unused]] const auto kDeclareLifecycle =
  &idsim_common::declare_vehicle_params<rclcpp_lifecycle::LifecycleNode>;

void expect_rejected(
  const std::string & id, const std::string & ns, std::int64_t sysid, const std::string & key)
{
  std::string error;
  EXPECT_FALSE(parse_vehicle_params(id, ns, sysid, &error).has_value())
    << "'" << id << "' '" << ns << "' " << sysid;
  // 오류에 원인 key 이름이 들어간다.
  EXPECT_NE(error.find(key), std::string::npos) << error;
}

}  // namespace

TEST(VehicleParams, KeyNames)
{
  EXPECT_STREQ(idsim_common::kParamVehicleId, "vehicle.id");
  EXPECT_STREQ(idsim_common::kParamVehicleNs, "vehicle.ns");
  EXPECT_STREQ(idsim_common::kParamVehicleSysid, "vehicle.sysid");
}

TEST(VehicleParams, DeclareInstantiates)
{
  EXPECT_NE(kDeclareNode, nullptr);
  EXPECT_NE(kDeclareLifecycle, nullptr);
}

TEST(VehicleParams, ParsesValid)
{
  std::string error;
  const auto p = parse_vehicle_params("px4_1", "/px4_1", 2, &error);
  ASSERT_TRUE(p.has_value()) << error;
  EXPECT_EQ(p->id.str(), "px4_1");
  EXPECT_EQ(p->identity.ns.str(), "/px4_1");
  EXPECT_EQ(p->identity.sysid.value(), 2);
  EXPECT_TRUE(error.empty());

  const auto max = parse_vehicle_params("px4_9", "/px4_9", 255);
  ASSERT_TRUE(max.has_value());
  EXPECT_EQ(max->identity.sysid.value(), 255);
}

TEST(VehicleParams, RejectsInvalidValues)
{
  expect_rejected("", "/px4_1", 2, "vehicle.id");
  expect_rejected("/px4_1", "/px4_1", 2, "vehicle.id");
  expect_rejected("fleet/px4_1", "/fleet/px4_1", 2, "vehicle.id");
  expect_rejected("px4_1", "", 2, "vehicle.ns");
  expect_rejected("px4_1", "px4_1", 2, "vehicle.ns");
  expect_rejected("px4_1", "/", 2, "vehicle.ns");
  expect_rejected("px4_1", "/px4_1", 0, "vehicle.sysid");
  expect_rejected("px4_1", "/px4_1", -1, "vehicle.sysid");
  expect_rejected("px4_1", "/px4_1", 256, "vehicle.sysid");
  // int로 줄이면 2가 되는 값도 거부한다.
  expect_rejected("px4_1", "/px4_1", (std::int64_t{1} << 32) + 2, "vehicle.sysid");
}

TEST(VehicleParams, RejectsIdNamespaceMismatch)
{
  expect_rejected("px4_1", "/px4_2", 2, "vehicle.id");
  expect_rejected("px4_1", "/fleet/px4_1", 2, "vehicle.id");
}

TEST(VehicleParams, ErrorArgumentIsOptional)
{
  EXPECT_FALSE(parse_vehicle_params("px4_1", "/px4_2", 2).has_value());
}

TEST(VehicleParams, DeclaredValues)
{
  using idsim_common::detail::parse_vehicle_param_values;
  using rclcpp::ParameterValue;
  std::string error;
  const auto p = parse_vehicle_param_values(
    ParameterValue(std::string("px4_3")), ParameterValue(std::string("/px4_3")),
    ParameterValue(std::int64_t{4}), &error);
  ASSERT_TRUE(p.has_value()) << error;
  EXPECT_EQ(p->identity.sysid.value(), 4);

  // 기본값이 없어 params 파일이 주지 않으면 PARAMETER_NOT_SET이다. 누락 key를 오류에 적는다.
  error.clear();
  EXPECT_FALSE(parse_vehicle_param_values(
                 ParameterValue(std::string("px4_3")), ParameterValue(),
                 ParameterValue(std::int64_t{4}), &error)
                 .has_value());
  EXPECT_NE(error.find("vehicle.ns"), std::string::npos) << error;

  error.clear();
  EXPECT_FALSE(parse_vehicle_param_values(
                 ParameterValue(std::string("px4_3")), ParameterValue(std::string("/px4_3")),
                 ParameterValue(), &error)
                 .has_value());
  EXPECT_NE(error.find("vehicle.sysid"), std::string::npos) << error;

  // 타입이 다르면 거부한다(선언이 정적 타입이라 노드에서는 선언 단계에서 걸린다).
  error.clear();
  EXPECT_FALSE(parse_vehicle_param_values(
                 ParameterValue(std::string("px4_3")), ParameterValue(std::string("/px4_3")),
                 ParameterValue(std::string("4")), &error)
                 .has_value());
  EXPECT_FALSE(error.empty());

  // 값 해석 실패는 parse_vehicle_params의 오류를 그대로 준다.
  error.clear();
  EXPECT_FALSE(parse_vehicle_param_values(
                 ParameterValue(std::string("px4_3")), ParameterValue(std::string("/px4_4")),
                 ParameterValue(std::int64_t{4}), &error)
                 .has_value());
  EXPECT_NE(error.find("vehicle.id"), std::string::npos) << error;
}
