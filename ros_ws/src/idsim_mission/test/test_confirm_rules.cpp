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

// 순수 규칙: N회 연속 계수, "disarm 전송 뒤 받은 표본"의 기준, 정리 분기 고르기, yaw 변환.
// 결정: decisions.md "px4-engineer 승인 반영"(표본 기준), 쟁점 3 M3-M5, test-engineer 지시(교차표).
// 단위 테스트는 합성 timestamp만 검사한다. vehicle_status.timestamp와 Px4Timestamp의 실제 시계
// 관계는 재실측 (5)의 분포만 확인한다.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "idsim_mission/core/rules.hpp"
#include "idsim_mission/core/snapshot.hpp"

namespace idsim_mission::core::test
{
namespace
{

constexpr double kPi = 3.14159265358979323846;

TEST(SampleCounter, CountsDistinctMatchingSamples)
{
  SampleCounter c;
  EXPECT_TRUE(c.observe(100, true));
  EXPECT_TRUE(c.observe(200, true));
  EXPECT_EQ(c.count(), 2);
  // 같은 timestamp(같은 표본을 다시 봄)는 건너뛴다.
  EXPECT_FALSE(c.observe(200, true));
  EXPECT_EQ(c.count(), 2);
  // 줄어든 timestamp도 건너뛴다(되돌리지도 더하지도 않는다).
  EXPECT_FALSE(c.observe(150, false));
  EXPECT_EQ(c.count(), 2);
  EXPECT_TRUE(c.observe(300, true));
  EXPECT_EQ(c.count(), 3);
  // 맞지 않는 새 표본은 0으로 되돌린다.
  EXPECT_TRUE(c.observe(400, false));
  EXPECT_EQ(c.count(), 0);
  c.reset();
  EXPECT_TRUE(c.observe(50, true));
  EXPECT_EQ(c.count(), 1);
}

StatusSample sample(Arming arming, std::uint64_t ts, std::uint64_t tick)
{
  StatusSample s;
  s.arming = arming;
  s.timestamp_us = ts;
  s.received_tick = tick;
  return s;
}

TEST(AfterDisarmSend, BothConditionsRequired)
{
  // 첫 전송: tick 10, Px4Timestamp 1000 us.
  EXPECT_TRUE(is_after_disarm_send(sample(Arming::kDisarmed, 1001, 11), 10, 1000));
  // 전송 tick과 같거나 앞에 받은 표본은 timestamp가 뒤여도 세지 않는다.
  EXPECT_FALSE(is_after_disarm_send(sample(Arming::kDisarmed, 5000, 10), 10, 1000));
  EXPECT_FALSE(is_after_disarm_send(sample(Arming::kDisarmed, 5000, 9), 10, 1000));
  // timestamp가 같거나 앞선 표본은 뒤 tick에 받아도 세지 않는다(엄격 부등호).
  EXPECT_FALSE(is_after_disarm_send(sample(Arming::kDisarmed, 1000, 11), 10, 1000));
  EXPECT_FALSE(is_after_disarm_send(sample(Arming::kDisarmed, 999, 12), 10, 1000));
}

TEST(DisarmConfirm, IgnoresSamplesBeforeStampIsKnown)
{
  DisarmConfirm d;
  d.begin(10);
  d.observe(sample(Arming::kDisarmed, 2000, 11));
  EXPECT_EQ(d.count(), 0);
  d.set_first_stamp(1000);
  d.observe(sample(Arming::kDisarmed, 2100, 12));
  EXPECT_EQ(d.count(), 1);
}

TEST(DisarmConfirm, StaleDuplicateAndDecreasingSamplesAreNotCounted)
{
  DisarmConfirm d;
  d.begin(10);
  d.set_first_stamp(1000);
  d.observe(sample(Arming::kDisarmed, 900, 9));    // 전송 tick 전
  d.observe(sample(Arming::kDisarmed, 1000, 11));  // timestamp가 전송과 같음
  d.observe(sample(Arming::kDisarmed, 800, 12));   // timestamp가 앞섬
  EXPECT_EQ(d.count(), 0);
  d.observe(sample(Arming::kDisarmed, 1100, 13));
  d.observe(sample(Arming::kDisarmed, 1100, 14));  // 같은 표본을 다음 tick에 다시 봄
  EXPECT_EQ(d.count(), 1);
  d.observe(sample(Arming::kDisarmed, 1050, 15));  // 줄어듦
  EXPECT_EQ(d.count(), 1);
  d.observe(sample(Arming::kDisarmed, 1200, 16));
  d.observe(sample(Arming::kDisarmed, 1300, 17));
  EXPECT_EQ(d.count(), 3);
}

TEST(DisarmConfirm, LateArmRaceResetsCount)
{
  // 늦게 처리된 arm의 경합: [ARMED, DISARMED, DISARMED, ARMED]에서 계수가 되돌아간다.
  DisarmConfirm d;
  d.begin(10);
  d.set_first_stamp(1000);
  d.observe(sample(Arming::kArmed, 1100, 11));
  EXPECT_EQ(d.count(), 0);
  d.observe(sample(Arming::kDisarmed, 1200, 12));
  d.observe(sample(Arming::kDisarmed, 1300, 13));
  EXPECT_EQ(d.count(), 2);
  d.observe(sample(Arming::kArmed, 1400, 14));
  EXPECT_EQ(d.count(), 0);
  d.observe(sample(Arming::kDisarmed, 1500, 15));
  d.observe(sample(Arming::kDisarmed, 1600, 16));
  d.observe(sample(Arming::kDisarmed, 1700, 17));
  EXPECT_EQ(d.count(), 3);
}

TEST(DisarmConfirm, BeginResets)
{
  DisarmConfirm d;
  d.begin(10);
  d.set_first_stamp(1000);
  d.observe(sample(Arming::kDisarmed, 1100, 11));
  d.begin(20);
  EXPECT_EQ(d.count(), 0);
  EXPECT_FALSE(d.stamp_known());
  EXPECT_EQ(d.first_send_tick(), 20U);
}

// ---- 정리 분기 고르기: snapshot 유형 5종 ----
// 취소, ITEM_TIMEOUT, PREPARING 실패는 같은 select_cleanup을 쓰고 원인은 입력에 없다.
// 원인 축(3 x 3)은 상태기 수준의 test_runner_cleanup.cpp CauseCrossTable이 본다.

struct SnapshotKind
{
  const char * name;
  CleanupInput input;
  CleanupChoice expected;
};

std::vector<SnapshotKind> snapshot_kinds()
{
  std::vector<SnapshotKind> kinds;
  {
    SnapshotKind k{"AirArmed", {}, CleanupChoice::kAir};
    k.input.arming = Arming::kArmed;
    k.input.landed = false;
    k.input.arm_sent = true;
    kinds.push_back(k);
  }
  {
    SnapshotKind k{"AirDisarmed", {}, CleanupChoice::kAirDisarm};
    k.input.arming = Arming::kDisarmed;
    k.input.landed = false;
    k.input.disarm_class = DisarmClass::kAir;
    k.input.arm_sent = true;
    kinds.push_back(k);
  }
  {
    SnapshotKind k{"GroundArmed", {}, CleanupChoice::kGround};
    k.input.arming = Arming::kArmed;
    k.input.landed = true;
    k.input.arm_sent = true;
    kinds.push_back(k);
  }
  {
    // arm을 보낸 뒤 DISARMED snapshot. arming_state와 무관하게 disarm 분기(ITEM_TIMEOUT에서도).
    SnapshotKind k{"GroundDisarmedArmSent", {}, CleanupChoice::kGround};
    k.input.arming = Arming::kDisarmed;
    k.input.landed = true;
    k.input.disarm_class = DisarmClass::kGround;
    k.input.arm_sent = true;
    kinds.push_back(k);
  }
  {
    SnapshotKind k{"GroundDisarmedNoArm", {}, CleanupChoice::kEnd};
    k.input.arming = Arming::kDisarmed;
    k.input.landed = true;
    k.input.disarm_class = DisarmClass::kGround;
    k.input.arm_sent = false;
    kinds.push_back(k);
  }
  return kinds;
}

class SnapshotKindTable : public ::testing::TestWithParam<SnapshotKind>
{
};

TEST_P(SnapshotKindTable, Choice)
{
  EXPECT_EQ(select_cleanup(GetParam().input), GetParam().expected)
    << cleanup_choice_name(select_cleanup(GetParam().input));
}

INSTANTIATE_TEST_SUITE_P(
  Kinds, SnapshotKindTable, ::testing::ValuesIn(snapshot_kinds()),
  [](const ::testing::TestParamInfo<SnapshotKind> & info) { return std::string(info.param.name); });

TEST(SnapshotKindTableSize, Five) { EXPECT_EQ(snapshot_kinds().size(), 5U); }

TEST(SelectCleanup, GroundBranchStaysWhileDisarmedEvenWithoutArmSent)
{
  // [LAND] 미션처럼 arm을 보내지 않았어도, 이미 disarm 분기에 있으면 확인까지 그 분기에 남는다.
  CleanupInput in;
  in.arming = Arming::kDisarmed;
  in.landed = true;
  in.disarm_class = DisarmClass::kGround;
  in.arm_sent = false;
  in.in_ground_branch = true;
  EXPECT_EQ(select_cleanup(in), CleanupChoice::kGround);
}

TEST(SelectCleanup, FixedClassWinsOverLatestLanded)
{
  // disarm 분류는 처음 관측한 DISARMED의 tick에 고정한다. 뒤의 landed는 보지 않는다.
  CleanupInput air;
  air.arming = Arming::kDisarmed;
  air.landed = true;  // 0.33 s 뒤 landed가 true로 바뀌어도
  air.disarm_class = DisarmClass::kAir;
  air.arm_sent = true;
  EXPECT_EQ(select_cleanup(air), CleanupChoice::kAirDisarm);

  CleanupInput ground = air;
  ground.landed = false;
  ground.disarm_class = DisarmClass::kGround;
  EXPECT_EQ(select_cleanup(ground), CleanupChoice::kGround);
}

TEST(Yaw, EnuToNedMatchesFramesFormula)
{
  // idsim_common/frames의 enu_to_ned_yaw와 같은 식: wrap_pi(pi/2 - yaw_enu), [-pi, pi).
  EXPECT_NEAR(enu_to_ned_yaw(0.0), kPi / 2.0, 1e-12);    // 동 -> 90도
  EXPECT_NEAR(enu_to_ned_yaw(kPi / 2.0), 0.0, 1e-12);    // 북 -> 0
  EXPECT_NEAR(enu_to_ned_yaw(-kPi / 2.0), -kPi, 1e-12);  // 남 -> -pi
  EXPECT_NEAR(enu_to_ned_yaw(-kPi), -kPi / 2.0, 1e-12);  // 서 -> -90도
  EXPECT_DOUBLE_EQ(wrap_pi(kPi), -kPi);
  EXPECT_TRUE(std::isnan(wrap_pi(std::nan(""))));
}

}  // namespace
}  // namespace idsim_mission::core::test
