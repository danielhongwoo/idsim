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

// PX4 어댑터 좌표 기준 쪽: vehicle_local_position의 기준 -> core::FramePort(decisions.md 쟁점 4).
// 기준 유효 술어의 칸마다 한 사례, 같은 표본에서 위치와 기준을 함께 만드는지, 식은
// idsim_common::geo와 frames에 위임하는지 본다. 노드와 DDS 참가자를 만들지 않는다.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>

#include "Eigen/Core"
#include "idsim_common/frames.hpp"
#include "idsim_common/geo.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"
#include "idsim_mission/px4/frame_port.hpp"
#include "idsim_mission/px4/inputs.hpp"

namespace idsim_mission::px4::test
{
namespace
{

using core::Vec3;
using idsim_common::geo::LocalReference;
using idsim_common::geo::WorldOrigin;
using px4_msgs::msg::VehicleLocalPosition;

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kInf = std::numeric_limits<double>::infinity();
constexpr float kNaNF = std::numeric_limits<float>::quiet_NaN();
constexpr float kInfF = std::numeric_limits<float>::infinity();

// decisions.md 쟁점 4 근거의 계산 예와 같은 위도.
constexpr double kLat = 37.57;
constexpr double kLon = 126.98;
constexpr float kAlt = 30.0F;  // float32로 정확히 표현되는 값

WorldOrigin origin() { return WorldOrigin{kLat, kLon, static_cast<double>(kAlt)}; }

// 기준이 유효한 표본. 기준은 world 원점과 같다.
VehicleLocalPosition valid_msg()
{
  VehicleLocalPosition msg;
  msg.timestamp = 5'000'000;
  msg.x = 1.0F;
  msg.y = 2.0F;
  msg.z = -3.0F;
  msg.heading = 0.5F;
  msg.xy_valid = true;
  msg.z_valid = true;
  msg.xy_global = true;
  msg.z_global = true;
  msg.ref_timestamp = 1'234'567;
  msg.ref_lat = kLat;
  msg.ref_lon = kLon;
  msg.ref_alt = kAlt;
  return msg;
}

// ---- 기준 유효 술어 ----

TEST(Px4FramePort, ValidReferenceIsRead)
{
  const std::optional<LocalReference> ref = local_reference_from_px4(valid_msg());
  ASSERT_TRUE(ref.has_value());
  EXPECT_DOUBLE_EQ(ref->lat_deg, kLat);
  EXPECT_DOUBLE_EQ(ref->lon_deg, kLon);
  EXPECT_DOUBLE_EQ(ref->alt_m, 30.0);
}

TEST(Px4FramePort, GlobalFlagsBothRequired)
{
  for (const bool xy : {false, true}) {
    for (const bool z : {false, true}) {
      VehicleLocalPosition msg = valid_msg();
      msg.xy_global = xy;
      msg.z_global = z;
      EXPECT_EQ(local_reference_from_px4(msg).has_value(), xy && z) << xy << " " << z;
    }
  }
}

TEST(Px4FramePort, NonFiniteReferenceIsInvalid)
{
  for (const double bad : {kNaN, kInf, -kInf}) {
    VehicleLocalPosition msg = valid_msg();
    msg.ref_lat = bad;
    EXPECT_FALSE(local_reference_from_px4(msg).has_value()) << "ref_lat " << bad;
    msg = valid_msg();
    msg.ref_lon = bad;
    EXPECT_FALSE(local_reference_from_px4(msg).has_value()) << "ref_lon " << bad;
  }
  for (const float bad : {kNaNF, kInfF, -kInfF}) {
    VehicleLocalPosition msg = valid_msg();
    msg.ref_alt = bad;
    EXPECT_FALSE(local_reference_from_px4(msg).has_value()) << "ref_alt " << bad;
  }
}

TEST(Px4FramePort, ZeroRefAltWithZGlobalIsInvalid)
{
  // K3 창: 위경도 원점은 잡혔고(z_global true) 고도 원점이 아직 없어 PX4가 ref_alt를 0으로 둔 표본.
  VehicleLocalPosition msg = valid_msg();
  msg.ref_alt = 0.0F;
  ASSERT_TRUE(msg.xy_global && msg.z_global);
  EXPECT_FALSE(local_reference_from_px4(msg).has_value());
  msg.ref_alt = -0.0F;  // -0.0 == 0.0
  EXPECT_FALSE(local_reference_from_px4(msg).has_value());
}

TEST(Px4FramePort, ZeroIsSpecialOnlyForExactAltitudeZero)
{
  // 0 규칙은 ref_alt를 정확히 0.0과 비교한다. 0에 가까운 고도와 위경도 0은 유효하다.
  VehicleLocalPosition msg = valid_msg();
  msg.ref_alt = 0.001F;
  EXPECT_TRUE(local_reference_from_px4(msg).has_value());
  msg.ref_alt = -5.0F;  // 해수면 아래 원점
  EXPECT_TRUE(local_reference_from_px4(msg).has_value());
  msg = valid_msg();
  msg.ref_lat = 0.0;
  msg.ref_lon = 0.0;
  EXPECT_TRUE(local_reference_from_px4(msg).has_value());
}

// ---- 같은 표본에서 위치와 기준 ----

TEST(Px4FramePort, PositionInputComesFromOneSample)
{
  const VehicleLocalPosition msg = valid_msg();
  const LocalPositionInput in = to_local_position_input(msg, 9);
  const core::PositionSample expected = to_position_sample(msg, 9);
  EXPECT_EQ(in.position.timestamp_us, expected.timestamp_us);
  EXPECT_DOUBLE_EQ(in.position.x, expected.x);
  EXPECT_DOUBLE_EQ(in.position.y, expected.y);
  EXPECT_DOUBLE_EQ(in.position.z, expected.z);
  EXPECT_DOUBLE_EQ(in.position.heading, expected.heading);
  EXPECT_EQ(in.position.xy_valid, expected.xy_valid);
  EXPECT_EQ(in.position.z_valid, expected.z_valid);
  EXPECT_EQ(in.position.received_tick, 9U);
  ASSERT_TRUE(in.reference.has_value());
  EXPECT_DOUBLE_EQ(in.reference->lat_deg, kLat);
  EXPECT_EQ(in.ref_timestamp_us, 1'234'567U);
}

TEST(Px4FramePort, PositionInputKeepsPositionWhenReferenceInvalid)
{
  // 기준이 무효여도 위치 표본은 그대로 만든다(core가 위치 유효를 따로 본다).
  VehicleLocalPosition msg = valid_msg();
  msg.ref_alt = 0.0F;
  const LocalPositionInput in = to_local_position_input(msg, 2);
  EXPECT_FALSE(in.reference.has_value());
  EXPECT_DOUBLE_EQ(in.position.x, 1.0);
  EXPECT_TRUE(in.position.xy_valid);
}

// ---- Px4FramePort ----

TEST(Px4FramePort, NoReferenceGivesNoPointButVelocityStillMaps)
{
  const Px4FramePort frame(origin(), std::nullopt);
  const core::FramePort & port = frame;
  EXPECT_FALSE(frame.reference_valid());
  EXPECT_FALSE(port.world_to_local(Vec3{0.0, 0.0, 0.0}).has_value());
  const Vec3 v = port.world_velocity_to_local(Vec3{1.0, 2.0, 3.0});
  EXPECT_DOUBLE_EQ(v.x, 2.0);   // north <- ENU y
  EXPECT_DOUBLE_EQ(v.y, 1.0);   // east <- ENU x
  EXPECT_DOUBLE_EQ(v.z, -3.0);  // down <- -up
}

TEST(Px4FramePort, PointDelegatesToGeo)
{
  // 기준을 원점에서 떨어뜨려 놓고, 결과가 geo::world_enu_to_local_ned와 비트 단위로 같은지 본다.
  VehicleLocalPosition msg = valid_msg();
  msg.ref_lat = kLat + 0.001;
  msg.ref_lon = kLon - 0.002;
  msg.ref_alt = 31.5F;
  const std::optional<LocalReference> ref = local_reference_from_px4(msg);
  ASSERT_TRUE(ref.has_value());
  const Px4FramePort frame(origin(), ref);
  const core::FramePort & port = frame;
  for (const Vec3 & p : {Vec3{0.0, 0.0, 0.0}, Vec3{6.0, -3.0, 0.0}, Vec3{-120.0, 45.0, 12.5}}) {
    const std::optional<Vec3> got = port.world_to_local(p);
    ASSERT_TRUE(got.has_value());
    const Eigen::Vector3d want =
      idsim_common::geo::world_enu_to_local_ned(origin(), *ref, Eigen::Vector3d(p.x, p.y, p.z));
    EXPECT_DOUBLE_EQ(got->x, want.x());
    EXPECT_DOUBLE_EQ(got->y, want.y());
    EXPECT_DOUBLE_EQ(got->z, want.z());
  }
}

TEST(Px4FramePort, KnownValuesAtSameOrigin)
{
  // decisions.md 쟁점 4 근거의 계산(gz-math 7.7.0 LOCAL2와 PX4 MapProjection 식): 위도 37.57도에서
  // world 동쪽 100 m는 로컬 99.763 m, 북쪽 100 m는 100.186 m. 평행 이동 근사와는 약 20 cm 다르다.
  const Px4FramePort frame(origin(), local_reference_from_px4(valid_msg()));
  const std::optional<Vec3> east = frame.world_to_local(Vec3{100.0, 0.0, 0.0});
  ASSERT_TRUE(east.has_value());
  EXPECT_NEAR(east->y, 99.763, 1e-3);
  EXPECT_NEAR(east->x, 0.0, 1e-2);
  const std::optional<Vec3> north = frame.world_to_local(Vec3{0.0, 100.0, 0.0});
  ASSERT_TRUE(north.has_value());
  EXPECT_NEAR(north->x, 100.186, 1e-3);
  EXPECT_NEAR(north->y, 0.0, 1e-6);
  const std::optional<Vec3> up = frame.world_to_local(Vec3{0.0, 0.0, 10.0});
  ASSERT_TRUE(up.has_value());
  EXPECT_NEAR(up->z, -10.0, 1e-6);  // NED 아래쪽이 +
}

TEST(Px4FramePort, NonFinitePointGivesNoValue)
{
  const Px4FramePort frame(origin(), local_reference_from_px4(valid_msg()));
  for (const double bad : {kNaN, kInf, -kInf}) {
    EXPECT_FALSE(frame.world_to_local(Vec3{bad, 0.0, 0.0}).has_value());
    EXPECT_FALSE(frame.world_to_local(Vec3{0.0, bad, 0.0}).has_value());
    EXPECT_FALSE(frame.world_to_local(Vec3{0.0, 0.0, bad}).has_value());
  }
}

TEST(Px4FramePort, VelocityDelegatesToFramesAndIgnoresReference)
{
  const Vec3 v_enu{1.25, -0.5, 0.75};
  const Eigen::Vector3d want = idsim_common::frames::enu_to_ned(Eigen::Vector3d(1.25, -0.5, 0.75));
  VehicleLocalPosition far = valid_msg();
  far.ref_lat = kLat + 1.0;
  far.ref_alt = 500.0F;
  for (const std::optional<LocalReference> & ref :
       {local_reference_from_px4(valid_msg()), local_reference_from_px4(far),
        std::optional<LocalReference>{}}) {
    const Vec3 got = Px4FramePort(origin(), ref).world_velocity_to_local(v_enu);
    EXPECT_DOUBLE_EQ(got.x, want.x());
    EXPECT_DOUBLE_EQ(got.y, want.y());
    EXPECT_DOUBLE_EQ(got.z, want.z());
  }
}

}  // namespace
}  // namespace idsim_mission::px4::test
