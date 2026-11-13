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

// TargetId 검증과 표적 상태 토픽 이름 조립. 노드를 만들지 않는다.
// 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 3, 14. 규칙은 docs/interface.md
// "이름과 식별자"의 target_id(^[a-z][a-z0-9_]{0,31}$).

#include <gtest/gtest.h>

#include <string>

#include "idsim_common/target.hpp"
#include "idsim_interfaces/msg/target_state.hpp"
#include "rmw/validate_full_topic_name.h"

using idsim_common::TargetId;

namespace
{

bool valid_full_topic(const std::string & name)
{
  int result = RMW_TOPIC_VALID;
  std::size_t index = 0;
  return rmw_validate_full_topic_name(name.c_str(), &result, &index) == RMW_RET_OK &&
         result == RMW_TOPIC_VALID;
}

}  // namespace

TEST(TargetId, AcceptsValidIds)
{
  const std::string max_len = "a" + std::string(31, 'z');
  for (const std::string id : {"a", "car_1", "target", "t0", "a_", "x9_y8", max_len.c_str()}) {
    const auto parsed = TargetId::parse(id);
    ASSERT_TRUE(parsed.has_value()) << id;
    EXPECT_EQ(parsed->str(), id);
  }
}

TEST(TargetId, RejectsInvalidIds)
{
  const std::string too_long = "a" + std::string(32, 'z');
  for (const std::string id :
       {"", "1car", "_car", "Car", "car-1", "car.1", "car 1", "/car", "car/1", "cAr", "ca\xc3\xa9",
        too_long.c_str()}) {
    std::string error;
    EXPECT_FALSE(TargetId::parse(id, &error).has_value()) << id;
    EXPECT_FALSE(error.empty()) << id;
  }
}

TEST(TargetId, RejectsEmbeddedNul)
{
  EXPECT_FALSE(TargetId::parse(std::string("car\0x", 5)).has_value());
}

TEST(TargetId, Equality)
{
  EXPECT_EQ(*TargetId::parse("car_1"), *TargetId::parse("car_1"));
  EXPECT_NE(*TargetId::parse("car_1"), *TargetId::parse("car_2"));
}

TEST(TargetStateTopic, AssemblesFromMessageConstants)
{
  using idsim_interfaces::msg::TargetState;
  const auto id = *TargetId::parse("car_1");
  const std::string topic = idsim_common::target_state_topic(id);
  EXPECT_EQ(topic, "/targets/car_1/state");
  EXPECT_EQ(
    topic,
    std::string(TargetState::TOPIC_PREFIX) + "/car_1/" + std::string(TargetState::TOPIC_SUFFIX));
  EXPECT_TRUE(valid_full_topic(topic)) << topic;
}

TEST(TargetStateTopic, EveryValidIdGivesValidTopic)
{
  for (const std::string & id :
       {std::string("a"), "a" + std::string(31, '9'), std::string("z_9_")}) {
    const std::string topic = idsim_common::target_state_topic(*TargetId::parse(id));
    EXPECT_TRUE(valid_full_topic(topic)) << topic;
  }
}
