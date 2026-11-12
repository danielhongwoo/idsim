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

// PX4 어댑터 입력 쪽: px4_msgs -> core 표본. 대응표의 정본은 core/snapshot.hpp 머리 주석이다.
// enum 매핑은 값 범위 전체(uint8은 0-255)를 돌려 표 밖의 값이 kOther(arming은 kDisarmed)로 가는지
// 본다. 노드와 DDS 참가자를 만들지 않는다.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <string>

#include "idsim_common/vehicle.hpp"
#include "idsim_common/vehicle_command.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/px4/inputs.hpp"

namespace idsim_mission::px4::test
{
namespace
{

using core::AckCommand;
using core::AckResult;
using core::Arming;
using core::IdentityCheck;
using core::NavMode;
using px4_msgs::msg::FailsafeFlags;
using px4_msgs::msg::VehicleCommand;
using px4_msgs::msg::VehicleCommandAck;
using px4_msgs::msg::VehicleLandDetected;
using px4_msgs::msg::VehicleLocalPosition;
using px4_msgs::msg::VehicleStatus;

constexpr int kTargetSysid = 2;
constexpr int kSourceSystem = 254;
constexpr int kSourceComponent = 1;

idsim_common::VehicleIdentity identity()
{
  return idsim_common::VehicleIdentity{
    idsim_common::VehicleNamespace::parse("/px4_1").value(),
    idsim_common::SystemId::make(kTargetSysid).value()};
}

idsim_common::CommandSource source()
{
  return idsim_common::CommandSource::make(kSourceSystem, kSourceComponent).value();
}

VehicleStatus status_msg()
{
  VehicleStatus msg;
  msg.timestamp = 12'345'678;
  msg.system_id = kTargetSysid;
  msg.component_id = idsim_common::kAutopilotComponentId;
  msg.arming_state = VehicleStatus::ARMING_STATE_ARMED;
  msg.nav_state = VehicleStatus::NAVIGATION_STATE_OFFBOARD;
  msg.nav_state_user_intention = VehicleStatus::NAVIGATION_STATE_AUTO_LOITER;
  msg.failsafe = true;
  return msg;
}

FailsafeFlags ready_flags()
{
  FailsafeFlags flags;  // 기본값은 모두 false
  return flags;
}

// ---- nav_state 전수 ----

TEST(Px4Inputs, NavStateMapsOnlyOffboardLoiterLandAllOthersAreOther)
{
  const std::map<int, NavMode> mapped{
    {VehicleStatus::NAVIGATION_STATE_OFFBOARD, NavMode::kOffboard},
    {VehicleStatus::NAVIGATION_STATE_AUTO_LOITER, NavMode::kHold},
    {VehicleStatus::NAVIGATION_STATE_AUTO_LAND, NavMode::kLand},
  };
  for (int v = 0; v <= 255; ++v) {
    const auto it = mapped.find(v);
    const NavMode expected = it == mapped.end() ? NavMode::kOther : it->second;
    EXPECT_EQ(nav_mode_from_px4(static_cast<std::uint8_t>(v)), expected) << "nav_state " << v;
  }
}

TEST(Px4Inputs, NavStateNumericValuesMatchPx4V117)
{
  // 상수 이름으로 비교하지만, px4_msgs가 바뀌어 값이 움직이면 알아차리게 한 번 고정한다.
  EXPECT_EQ(VehicleStatus::NAVIGATION_STATE_AUTO_LOITER, 4);
  EXPECT_EQ(VehicleStatus::NAVIGATION_STATE_DESCEND, 12);
  EXPECT_EQ(VehicleStatus::NAVIGATION_STATE_OFFBOARD, 14);
  EXPECT_EQ(VehicleStatus::NAVIGATION_STATE_AUTO_LAND, 18);
}

TEST(Px4Inputs, DescendIsNotLand)
{
  // 위치가 무효일 때 NAV_LAND는 DESCEND로 대체된다. AUTO_LAND 확인으로 세지 않는다.
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_DESCEND), NavMode::kOther);
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_AUTO_PRECLAND), NavMode::kOther);
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_AUTO_RTL), NavMode::kOther);
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_AUTO_TAKEOFF), NavMode::kOther);
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_TERMINATION), NavMode::kOther);
  EXPECT_EQ(nav_mode_from_px4(VehicleStatus::NAVIGATION_STATE_POSCTL), NavMode::kOther);
}

TEST(Px4Inputs, NavStateAndUserIntentionUseTheSameTable)
{
  for (int v = 0; v <= 255; ++v) {
    VehicleStatus msg = status_msg();
    msg.nav_state = static_cast<std::uint8_t>(v);
    msg.nav_state_user_intention = static_cast<std::uint8_t>(v);
    const core::StatusSample s = to_status_sample(msg, identity(), Received{1, 0});
    EXPECT_EQ(s.nav, nav_mode_from_px4(static_cast<std::uint8_t>(v))) << v;
    EXPECT_EQ(s.nav_user_intention, s.nav) << v;
  }
}

// ---- arming_state 전수 ----

TEST(Px4Inputs, ArmingOnlyArmedIsArmed)
{
  for (int v = 0; v <= 255; ++v) {
    const Arming expected =
      v == VehicleStatus::ARMING_STATE_ARMED ? Arming::kArmed : Arming::kDisarmed;
    EXPECT_EQ(arming_from_px4(static_cast<std::uint8_t>(v)), expected) << "arming_state " << v;
  }
  EXPECT_EQ(arming_from_px4(VehicleStatus::ARMING_STATE_DISARMED), Arming::kDisarmed);
}

// ---- ack result 전수 ----

TEST(Px4Inputs, AckResultAllValues)
{
  const std::map<int, AckResult> mapped{
    {VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED, AckResult::kAccepted},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED, AckResult::kTemporarilyRejected},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_DENIED, AckResult::kDenied},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_UNSUPPORTED, AckResult::kUnsupported},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_FAILED, AckResult::kFailed},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_IN_PROGRESS, AckResult::kInProgress},
    {VehicleCommandAck::VEHICLE_CMD_RESULT_CANCELLED, AckResult::kCancelled},
  };
  ASSERT_EQ(mapped.size(), 7U);  // px4_msgs의 result 0-6
  for (int v = 0; v <= 255; ++v) {
    const auto it = mapped.find(v);
    const AckResult expected = it == mapped.end() ? AckResult::kOther : it->second;
    EXPECT_EQ(ack_result_from_px4(static_cast<std::uint8_t>(v)), expected) << "result " << v;
  }
}

TEST(Px4Inputs, AckResultRejectionFollowsCoreRule)
{
  // ACCEPTED와 IN_PROGRESS만 거부가 아니다(decisions.md 쟁점 4 "명령 재전송 규칙").
  // 해석은 core의 is_rejection이 한다.
  for (int v = 0; v <= 255; ++v) {
    const bool not_rejection = v == VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED ||
                               v == VehicleCommandAck::VEHICLE_CMD_RESULT_IN_PROGRESS;
    EXPECT_EQ(core::is_rejection(ack_result_from_px4(static_cast<std::uint8_t>(v))), !not_rejection)
      << "result " << v;
  }
}

// ---- ack command 묶음 ----

TEST(Px4Inputs, AckCommandGroups)
{
  const std::map<std::uint32_t, AckCommand> mapped{
    {VehicleCommand::VEHICLE_CMD_DO_SET_MODE, AckCommand::kSetMode},
    {VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, AckCommand::kArmDisarm},
    {VehicleCommand::VEHICLE_CMD_NAV_LAND, AckCommand::kNavLand},
  };
  // VehicleCommand 상수는 uint16 범위다. 그 전부와 범위 밖 몇 값을 본다.
  for (std::uint32_t v = 0; v <= 0xFFFFU; ++v) {
    const auto it = mapped.find(v);
    const AckCommand expected = it == mapped.end() ? AckCommand::kOther : it->second;
    ASSERT_EQ(ack_command_from_px4(v), expected) << "command " << v;
  }
  EXPECT_EQ(
    ack_command_from_px4(0x10000U + VehicleCommand::VEHICLE_CMD_NAV_LAND), AckCommand::kOther);
  EXPECT_EQ(ack_command_from_px4(std::numeric_limits<std::uint32_t>::max()), AckCommand::kOther);
  // 어댑터의 묶음이 core의 ack_command_of와 같다.
  EXPECT_EQ(
    ack_command_from_px4(VehicleCommand::VEHICLE_CMD_DO_SET_MODE),
    core::ack_command_of(core::CommandKind::kSetModeOffboard));
  EXPECT_EQ(
    ack_command_from_px4(VehicleCommand::VEHICLE_CMD_DO_SET_MODE),
    core::ack_command_of(core::CommandKind::kSetModeHold));
  EXPECT_EQ(
    ack_command_from_px4(VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM),
    core::ack_command_of(core::CommandKind::kArm));
  EXPECT_EQ(
    ack_command_from_px4(VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM),
    core::ack_command_of(core::CommandKind::kDisarm));
  EXPECT_EQ(
    ack_command_from_px4(VehicleCommand::VEHICLE_CMD_NAV_LAND),
    core::ack_command_of(core::CommandKind::kNavLand));
}

// ---- vehicle_command_ack 표본 ----

TEST(Px4Inputs, AckForThisExecutorIsKept)
{
  VehicleCommandAck msg;
  msg.command = VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM;
  msg.result = VehicleCommandAck::VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED;
  msg.target_system = kSourceSystem;
  msg.target_component = kSourceComponent;
  const std::optional<core::AckSample> ack = to_ack_sample(msg, source(), 7);
  ASSERT_TRUE(ack.has_value());
  EXPECT_EQ(ack->command, AckCommand::kArmDisarm);
  EXPECT_EQ(ack->result, AckResult::kTemporarilyRejected);
  EXPECT_EQ(ack->received_tick, 7U);
}

TEST(Px4Inputs, AckForAnotherSenderIsDropped)
{
  VehicleCommandAck msg;
  msg.command = VehicleCommand::VEHICLE_CMD_DO_SET_MODE;
  msg.result = VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED;

  msg.target_system = kSourceSystem + 1;
  msg.target_component = kSourceComponent;
  EXPECT_FALSE(to_ack_sample(msg, source(), 1).has_value()) << "other system";

  msg.target_system = kSourceSystem;
  msg.target_component = kSourceComponent + 1;
  EXPECT_FALSE(to_ack_sample(msg, source(), 1).has_value()) << "other component";

  msg.target_system = 0;
  msg.target_component = 0;
  EXPECT_FALSE(to_ack_sample(msg, source(), 1).has_value()) << "broadcast";

  // 대상 autopilot 자신(target sysid, 1)으로 돌아온 ack도 이 Executor 것이 아니다.
  msg.target_system = kTargetSysid;
  msg.target_component = idsim_common::kAutopilotComponentId;
  EXPECT_FALSE(to_ack_sample(msg, source(), 1).has_value()) << "autopilot itself";
}

// ---- failsafe_flags와 ekf_ready 술어 ----

TEST(Px4Inputs, EkfReadyWhenFourInvalidFlagsAreFalse) { EXPECT_TRUE(ekf_ready(ready_flags())); }

TEST(Px4Inputs, EkfNotReadyWhenAnyOfFourIsTrue)
{
  bool FailsafeFlags::*const fields[] = {
    &FailsafeFlags::local_position_invalid,
    &FailsafeFlags::local_altitude_invalid,
    &FailsafeFlags::global_position_invalid,
    &FailsafeFlags::home_position_invalid,
  };
  for (bool FailsafeFlags::*const field : fields) {
    FailsafeFlags flags = ready_flags();
    flags.*field = true;
    EXPECT_FALSE(ekf_ready(flags));
    EXPECT_FALSE(to_flags_sample(flags, 1).ekf_ready);
  }
}

TEST(Px4Inputs, EkfReadyIgnoresOtherFlags)
{
  // _relaxed 변형과 그 밖의 flag는 술어에 들지 않는다.
  FailsafeFlags flags = ready_flags();
  flags.local_position_invalid_relaxed = true;
  flags.global_position_invalid_relaxed = true;
  flags.local_velocity_invalid = true;
  flags.attitude_invalid = true;
  flags.offboard_control_signal_lost = true;
  flags.manual_control_signal_lost = true;
  flags.gcs_connection_lost = true;
  EXPECT_TRUE(ekf_ready(flags));
}

TEST(Px4Inputs, FlagsSampleCarriesOffboardSignalLost)
{
  FailsafeFlags flags = ready_flags();
  flags.offboard_control_signal_lost = true;
  core::FlagsSample s = to_flags_sample(flags, 9);
  EXPECT_TRUE(s.ekf_ready);
  EXPECT_TRUE(s.offboard_signal_lost);
  EXPECT_EQ(s.received_tick, 9U);

  flags.offboard_control_signal_lost = false;
  s = to_flags_sample(flags, 10);
  EXPECT_FALSE(s.offboard_signal_lost);
}

// ---- vehicle_status 표본과 식별 ----

TEST(Px4Inputs, StatusSampleFields)
{
  const core::StatusSample s = to_status_sample(status_msg(), identity(), Received{5, 250'000'000});
  EXPECT_EQ(s.timestamp_us, 12'345'678U);
  EXPECT_EQ(s.received_tick, 5U);
  EXPECT_EQ(s.received_ns, 250'000'000);
  EXPECT_EQ(s.identity, IdentityCheck::kMatch);
  EXPECT_TRUE(s.identity_detail.empty());
  EXPECT_EQ(s.arming, Arming::kArmed);
  EXPECT_EQ(s.nav, NavMode::kOffboard);
  EXPECT_EQ(s.nav_user_intention, NavMode::kHold);
  EXPECT_TRUE(s.failsafe);

  VehicleStatus msg = status_msg();
  msg.failsafe = false;
  msg.arming_state = VehicleStatus::ARMING_STATE_DISARMED;
  const core::StatusSample d = to_status_sample(msg, identity(), Received{6, 0});
  EXPECT_FALSE(d.failsafe);
  EXPECT_EQ(d.arming, Arming::kDisarmed);
}

TEST(Px4Inputs, StatusSystemIdMismatch)
{
  VehicleStatus msg = status_msg();
  msg.system_id = kTargetSysid + 1;
  const core::StatusSample s = to_status_sample(msg, identity(), Received{1, 0});
  EXPECT_EQ(s.identity, IdentityCheck::kMismatch);
  EXPECT_NE(s.identity_detail.find("expected system_id 2 component_id 1"), std::string::npos)
    << s.identity_detail;
  EXPECT_NE(s.identity_detail.find("got system_id 3 component_id 1"), std::string::npos)
    << s.identity_detail;
  // 불일치 표본도 다른 필드는 채운다(버릴지는 core가 정한다).
  EXPECT_EQ(s.timestamp_us, msg.timestamp);
  EXPECT_EQ(s.nav, NavMode::kOffboard);
  EXPECT_EQ(s.arming, Arming::kArmed);
}

TEST(Px4Inputs, StatusComponentIdMismatch)
{
  VehicleStatus msg = status_msg();
  msg.component_id = 191;
  const core::StatusSample s = to_status_sample(msg, identity(), Received{1, 0});
  EXPECT_EQ(s.identity, IdentityCheck::kMismatch);
  EXPECT_NE(s.identity_detail.find("got system_id 2 component_id 191"), std::string::npos)
    << s.identity_detail;
}

TEST(Px4Inputs, StatusZeroSystemIdIsMismatch)
{
  // 초기화되지 않은 메시지(system_id 0)는 어떤 기체와도 맞지 않는다.
  VehicleStatus msg = status_msg();
  msg.system_id = 0;
  msg.component_id = 0;
  EXPECT_EQ(to_status_sample(msg, identity(), Received{1, 0}).identity, IdentityCheck::kMismatch);
}

// ---- vehicle_land_detected ----

TEST(Px4Inputs, LandSample)
{
  VehicleLandDetected msg;
  msg.landed = true;
  msg.maybe_landed = false;
  core::LandSample s = to_land_sample(msg, 3);
  EXPECT_TRUE(s.landed);
  EXPECT_EQ(s.received_tick, 3U);

  // landed만 본다(maybe_landed, ground_contact는 core가 쓰지 않는다).
  msg.landed = false;
  msg.maybe_landed = true;
  msg.ground_contact = true;
  s = to_land_sample(msg, 4);
  EXPECT_FALSE(s.landed);
}

// ---- vehicle_local_position과 NaN ----

TEST(Px4Inputs, PositionSampleFields)
{
  VehicleLocalPosition msg;
  msg.x = 1.5F;
  msg.y = -2.25F;
  msg.z = -10.0F;
  msg.heading = -3.0F;
  msg.z_valid = true;
  const core::PositionSample s = to_position_sample(msg, 11);
  EXPECT_DOUBLE_EQ(s.x, 1.5);
  EXPECT_DOUBLE_EQ(s.y, -2.25);
  EXPECT_DOUBLE_EQ(s.z, -10.0);
  EXPECT_DOUBLE_EQ(s.heading, static_cast<double>(-3.0F));
  EXPECT_TRUE(s.z_valid);
  EXPECT_EQ(s.received_tick, 11U);
}

TEST(Px4Inputs, PositionNaNPassesThrough)
{
  // PX4는 무효 추정에 NaN을 싣는다. 어댑터는 바꾸지 않는다(core가 P3에서 기다린다).
  VehicleLocalPosition msg;
  msg.x = std::numeric_limits<float>::quiet_NaN();
  msg.y = std::numeric_limits<float>::quiet_NaN();
  msg.z = std::numeric_limits<float>::quiet_NaN();
  msg.heading = std::numeric_limits<float>::quiet_NaN();
  msg.z_valid = false;
  const core::PositionSample s = to_position_sample(msg, 1);
  EXPECT_TRUE(std::isnan(s.x));
  EXPECT_TRUE(std::isnan(s.y));
  EXPECT_TRUE(std::isnan(s.z));
  EXPECT_TRUE(std::isnan(s.heading));
  EXPECT_FALSE(s.z_valid);

  msg.x = std::numeric_limits<float>::infinity();
  EXPECT_TRUE(std::isinf(to_position_sample(msg, 1).x));
}

}  // namespace
}  // namespace idsim_mission::px4::test
