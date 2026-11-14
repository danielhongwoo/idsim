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

// snapshot 헤더 타입의 기본값과 명령 묶음.
// 결정: decisions.md 쟁점 12(snapshot 헤더 표), 쟁점 8(SetpointOut 속도, TargetSample), 쟁점 4
// (FramePort). 기본값은 "모름/무효" 쪽이어야 한다. 어댑터나 노드가 채우지 않은 필드가 유효로
// 읽히지 않게 한다.

#include <gtest/gtest.h>

#include <optional>
#include <string>

#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{
namespace
{

TEST(Snapshot, SetpointOutHasNoVelocityByDefault)
{
  const SetpointOut sp;
  EXPECT_FALSE(sp.velocity_valid);
  EXPECT_EQ(sp.velocity.x, 0.0);
  EXPECT_EQ(sp.velocity.y, 0.0);
  EXPECT_EQ(sp.velocity.z, 0.0);
  EXPECT_EQ(sp.kind, SetpointKind::kTarget);
}

TEST(Snapshot, PositionSampleValidityDefaultsToFalse)
{
  const PositionSample p;
  EXPECT_EQ(p.timestamp_us, 0U);
  EXPECT_FALSE(p.xy_valid);
  EXPECT_FALSE(p.z_valid);
}

TEST(Snapshot, TargetSampleDefaults)
{
  const TargetSample t;
  EXPECT_FALSE(t.velocity_valid);
  EXPECT_EQ(t.stamp_ns, 0);
}

TEST(Snapshot, TargetsEmptyMeansNeverReceived)
{
  Snapshot s;
  EXPECT_TRUE(s.targets.empty());
  TargetSample t;
  t.position = Vec3{1.0, 2.0, 3.0};
  t.stamp_ns = 5;
  s.targets["t1"] = t;
  EXPECT_EQ(s.targets.count("t1"), 1U);
  EXPECT_EQ(s.targets.count("t2"), 0U);
}

TEST(Snapshot, NavRtlCommandNameAndAckGroup)
{
  EXPECT_STREQ(command_name(CommandKind::kNavRtl), "NAV_RTL");
  EXPECT_EQ(ack_command_of(CommandKind::kNavRtl), AckCommand::kNavRtl);
  // 다른 명령의 묶음은 그대로다.
  EXPECT_EQ(ack_command_of(CommandKind::kNavLand), AckCommand::kNavLand);
  EXPECT_NE(ack_command_of(CommandKind::kNavRtl), AckCommand::kOther);
}

// FramePort 계약의 모양(점 변환은 무효 기준에서 nullopt, 벡터는 늘 값). 실제 구현은 px4 어댑터다.
class FakeFramePort : public FramePort
{
public:
  explicit FakeFramePort(bool valid) : valid_(valid) {}

  std::optional<Vec3> world_to_local(const Vec3 & world_enu) const override
  {
    if (!valid_) {
      return std::nullopt;
    }
    return Vec3{world_enu.y, world_enu.x, -world_enu.z};
  }

  Vec3 world_velocity_to_local(const Vec3 & world_enu) const override
  {
    return Vec3{world_enu.y, world_enu.x, -world_enu.z};
  }

private:
  bool valid_;
};

TEST(Snapshot, FramePortInvalidReferenceGivesNoPoint)
{
  const FakeFramePort invalid(false);
  const FramePort & port = invalid;
  EXPECT_FALSE(port.world_to_local(Vec3{1.0, 2.0, 3.0}).has_value());
  const Vec3 v = port.world_velocity_to_local(Vec3{1.0, 2.0, 3.0});
  EXPECT_EQ(v.x, 2.0);
  EXPECT_EQ(v.y, 1.0);
  EXPECT_EQ(v.z, -3.0);
}

}  // namespace
}  // namespace idsim_mission::core
