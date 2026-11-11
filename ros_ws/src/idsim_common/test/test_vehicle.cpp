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

// 기체 식별 타입과 vehicle_status 대조. 순수 함수만 시험한다.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 5. VehicleId는
// docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 5.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <type_traits>

#include "idsim_common/vehicle.hpp"
#include "px4_msgs/msg/vehicle_status.hpp"

using idsim_common::IdentityCheck;
using idsim_common::SystemId;
using idsim_common::VehicleId;
using idsim_common::VehicleIdentity;
using idsim_common::VehicleNamespace;

static_assert(!std::is_default_constructible_v<VehicleNamespace>);
static_assert(!std::is_constructible_v<VehicleNamespace, std::string>);
static_assert(!std::is_default_constructible_v<SystemId>);
static_assert(!std::is_constructible_v<SystemId, int>);
static_assert(!std::is_constructible_v<SystemId, std::uint8_t>);
static_assert(!std::is_default_constructible_v<VehicleIdentity>);
static_assert(!std::is_default_constructible_v<VehicleId>);
static_assert(!std::is_constructible_v<VehicleId, std::string>);

TEST(VehicleNamespace, AcceptsAbsoluteNamespaces)
{
  for (const std::string ok : {"/px4_1", "/px4_9", "/fleet/px4_3", "/a"}) {
    std::string error;
    const auto ns = VehicleNamespace::parse(ok, &error);
    ASSERT_TRUE(ns.has_value()) << ok << ": " << error;
    EXPECT_EQ(ns->str(), ok);
  }
}

TEST(VehicleNamespace, RejectsInvalid)
{
  // 빈 문자열과 "/"(N=0 미지원), 상대 경로, 끝 빗금, rmw 규칙 위반.
  for (const std::string bad :
       {"", "/", "px4_1", "/px4_1/", "//px4_1", "/1px4", "/px4-1", "/px4 1", "/px4_1//x"}) {
    std::string error;
    EXPECT_FALSE(VehicleNamespace::parse(bad, &error).has_value()) << "'" << bad << "'";
    EXPECT_FALSE(error.empty()) << "'" << bad << "'";
  }
  // error 인자는 생략할 수 있다.
  EXPECT_FALSE(VehicleNamespace::parse("/").has_value());
}

TEST(SystemId, Range)
{
  EXPECT_FALSE(SystemId::make(0).has_value());
  EXPECT_FALSE(SystemId::make(-1).has_value());
  EXPECT_FALSE(SystemId::make(256).has_value());
  ASSERT_TRUE(SystemId::make(1).has_value());
  ASSERT_TRUE(SystemId::make(255).has_value());
  EXPECT_EQ(SystemId::make(1)->value(), 1);
  EXPECT_EQ(SystemId::make(255)->value(), 255);
}

namespace
{

VehicleIdentity identity(const char * ns, int sysid)
{
  return VehicleIdentity{*VehicleNamespace::parse(ns), *SystemId::make(sysid)};
}

px4_msgs::msg::VehicleStatus status(int system_id, int component_id)
{
  px4_msgs::msg::VehicleStatus s;
  s.system_id = static_cast<std::uint8_t>(system_id);
  s.component_id = static_cast<std::uint8_t>(component_id);
  return s;
}

}  // namespace

TEST(VehicleIdentity, Verify)
{
  const auto id = identity("/px4_1", 2);
  EXPECT_EQ(idsim_common::verify(id, status(2, 1)), IdentityCheck::Match);
  EXPECT_EQ(idsim_common::verify(id, status(3, 1)), IdentityCheck::SystemIdMismatch);
  EXPECT_EQ(idsim_common::verify(id, status(0, 1)), IdentityCheck::SystemIdMismatch);
  EXPECT_EQ(idsim_common::verify(id, status(2, 0)), IdentityCheck::ComponentIdMismatch);
  EXPECT_EQ(idsim_common::verify(id, status(2, 191)), IdentityCheck::ComponentIdMismatch);
  // 둘 다 틀리면 system id를 먼저 보고한다.
  EXPECT_EQ(idsim_common::verify(id, status(5, 7)), IdentityCheck::SystemIdMismatch);
  EXPECT_STREQ(idsim_common::to_string(IdentityCheck::Match), "Match");
  EXPECT_STREQ(idsim_common::to_string(IdentityCheck::SystemIdMismatch), "SystemIdMismatch");
  EXPECT_STREQ(idsim_common::to_string(IdentityCheck::ComponentIdMismatch), "ComponentIdMismatch");
}

TEST(VehicleId, AcceptsSingleToken)
{
  for (const std::string ok : {"px4_1", "px4_12", "a", "_x", "Px4_A"}) {
    std::string error;
    const auto id = VehicleId::parse(ok, &error);
    ASSERT_TRUE(id.has_value()) << ok << ": " << error;
    EXPECT_EQ(id->str(), ok);
  }
}

TEST(VehicleId, RejectsInvalid)
{
  // 빈 문자열, 앞 "/", 여러 토큰, 끝 빗금, rmw 노드 이름 규칙 위반(숫자 시작, '-', 공백, '~', '{').
  for (const std::string bad :
       {"", "/", "/px4_1", "px4_1/", "fleet/px4_1", "a/b", "1px4", "px4-1", "px4 1", "~px4",
        "{x}"}) {
    std::string error;
    EXPECT_FALSE(VehicleId::parse(bad, &error).has_value()) << "'" << bad << "'";
    EXPECT_FALSE(error.empty()) << "'" << bad << "'";
  }
  EXPECT_FALSE(VehicleId::parse("a/b").has_value());
}

TEST(VehicleId, MatchesNamespace)
{
  const auto id = VehicleId::parse("px4_1");
  ASSERT_TRUE(id.has_value());
  EXPECT_TRUE(id->matches(*VehicleNamespace::parse("/px4_1")));
  EXPECT_FALSE(id->matches(*VehicleNamespace::parse("/px4_2")));
  EXPECT_FALSE(id->matches(*VehicleNamespace::parse("/px4_11")));
  EXPECT_FALSE(id->matches(*VehicleNamespace::parse("/px4")));
  // 여러 토큰 네임스페이스는 마지막 토큰이 같아도 맞지 않는다(N이나 토큰을 해석하지 않는다).
  EXPECT_FALSE(id->matches(*VehicleNamespace::parse("/fleet/px4_1")));
  EXPECT_EQ(*id, *VehicleId::parse("px4_1"));
  EXPECT_NE(*id, *VehicleId::parse("px4_2"));
}
