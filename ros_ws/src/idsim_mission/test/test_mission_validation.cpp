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

// 미션 검증, TYPE_* 분류, goal 즉시 판정의 순서.
// 결정: docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 3 M1, 쟁점 4 "미션의 정적 검증".

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "idsim_mission/core/mission_validation.hpp"
#include "idsim_mission/core/types.hpp"
#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kPi = 3.14159265358979323846;

ItemSpec goto_item()
{
  ItemSpec item;
  item.type = item_type::kGoTo;
  item.timeout = seconds(10);
  item.go_to.position = Vec3{1.0, 2.0, 3.0};
  item.go_to.acceptance_radius_m = 0.5;
  item.go_to.yaw.mode = yaw_mode::kKeep;
  return item;
}

ItemSpec track_item()
{
  ItemSpec item;
  item.type = item_type::kTrackEntity;
  item.timeout = seconds(10);
  item.track_entity.target_id = "t1";
  item.track_entity.offset = Vec3{0.0, 0.0, 2.0};
  item.track_entity.acceptance_radius_m = 1.0;
  item.track_entity.yaw.mode = yaw_mode::kFixed;
  item.track_entity.yaw.yaw_rad = 0.5;
  return item;
}

ItemSpec rtl_item()
{
  ItemSpec item;
  item.type = item_type::kRtl;
  item.timeout = seconds(60);
  return item;
}

TEST(ItemClassification, EveryTypeIsInExactlyOneKind)
{
  // 모든 TYPE_*가 정확히 한 분류에 속한다(5단계 넘김).
  std::set<std::uint8_t> seen;
  int setpoint = 0;
  int mode_command = 0;
  for (const std::uint8_t type : kAllItemTypes) {
    EXPECT_TRUE(seen.insert(type).second) << "duplicate type " << int{type};
    const std::optional<ItemKind> kind = classify_item_type(type);
    ASSERT_TRUE(kind.has_value()) << int{type};
    if (*kind == ItemKind::kSetpoint) {
      ++setpoint;
    } else {
      ++mode_command;
    }
  }
  EXPECT_EQ(setpoint + mode_command, static_cast<int>(kAllItemTypes.size()));
  // 값은 1부터 6까지 빈칸 없이(메시지 상수와의 교차 검사는 노드 쪽 gtest, P3d).
  for (std::uint8_t v = 1; v <= 6; ++v) {
    EXPECT_EQ(seen.count(v), 1U) << int{v};
  }
}

TEST(ItemClassification, KindTable)
{
  EXPECT_EQ(classify_item_type(item_type::kTakeoff), ItemKind::kSetpoint);
  EXPECT_EQ(classify_item_type(item_type::kGoTo), ItemKind::kSetpoint);
  EXPECT_EQ(classify_item_type(item_type::kTrackEntity), ItemKind::kSetpoint);
  EXPECT_EQ(classify_item_type(item_type::kLoiter), ItemKind::kSetpoint);
  EXPECT_EQ(classify_item_type(item_type::kRtl), ItemKind::kModeCommand);
  EXPECT_EQ(classify_item_type(item_type::kLand), ItemKind::kModeCommand);
}

TEST(ItemClassification, NonTypesAreRejected)
{
  for (const int v : {0, 7, 8, 100, 255}) {
    EXPECT_FALSE(classify_item_type(static_cast<std::uint8_t>(v)).has_value()) << v;
  }
}

TEST(MissionId, Pattern)
{
  EXPECT_TRUE(is_valid_mission_id("a"));
  EXPECT_TRUE(is_valid_mission_id("0"));
  EXPECT_TRUE(is_valid_mission_id("m1_a-b"));
  EXPECT_TRUE(is_valid_mission_id(std::string(64, 'a')));
  EXPECT_FALSE(is_valid_mission_id(""));
  EXPECT_FALSE(is_valid_mission_id(std::string(65, 'a')));
  EXPECT_FALSE(is_valid_mission_id("_a"));
  EXPECT_FALSE(is_valid_mission_id("-a"));
  EXPECT_FALSE(is_valid_mission_id("A"));
  EXPECT_FALSE(is_valid_mission_id("a b"));
  EXPECT_FALSE(is_valid_mission_id("a.b"));
}

TEST(ValidateMission, StandardAndLandOnlyAreValid)
{
  EXPECT_TRUE(validate_mission(standard_mission()).valid);
  EXPECT_TRUE(validate_mission(land_only_mission()).valid);
  MissionSpec two;
  two.mission_id = "two";
  two.items = {takeoff_item(), land_item()};
  EXPECT_TRUE(validate_mission(two).valid);
}

struct ContractCase
{
  const char * name;
  std::function<void(MissionSpec &)> mutate;
  const char * expect_in_detail;
};

class ContractRejects : public ::testing::TestWithParam<ContractCase>
{
};

TEST_P(ContractRejects, IsInvalidWithFieldInDetail)
{
  MissionSpec m = standard_mission();
  GetParam().mutate(m);
  const MissionCheck contract = validate_mission_contract(m);
  EXPECT_FALSE(contract.valid);
  EXPECT_NE(contract.detail.find(GetParam().expect_in_detail), std::string::npos)
    << contract.detail;
  EXPECT_FALSE(validate_mission(m).valid);
}

INSTANTIATE_TEST_SUITE_P(
  Contract, ContractRejects,
  ::testing::Values(
    ContractCase{"BadMissionId", [](MissionSpec & m) { m.mission_id = "Bad"; }, "mission_id"},
    ContractCase{"NoItems", [](MissionSpec & m) { m.items.clear(); }, "no items"},
    ContractCase{"TypeZero", [](MissionSpec & m) { m.items[0].type = 0; }, "items[0].type"},
    ContractCase{"TypeSeven", [](MissionSpec & m) { m.items[1].type = 7; }, "items[1].type"},
    ContractCase{
      "TimeoutZero", [](MissionSpec & m) { m.items[0].timeout = Duration{}; }, "items[0].timeout"},
    ContractCase{
      "TimeoutNegative", [](MissionSpec & m) { m.items[2].timeout.sec = -1; }, "items[2].timeout"},
    ContractCase{
      "TimeoutNanosecTooLarge", [](MissionSpec & m) { m.items[2].timeout.nanosec = 1000000000U; },
      "items[2].timeout.nanosec"},
    ContractCase{
      "HeightZero", [](MissionSpec & m) { m.items[0].takeoff.height_m = 0.0; }, "takeoff.height_m"},
    ContractCase{
      "HeightNaN", [](MissionSpec & m) { m.items[0].takeoff.height_m = kNaN; }, "takeoff.height_m"},
    ContractCase{
      "AcceptanceNegative", [](MissionSpec & m) { m.items[0].takeoff.acceptance_m = -0.1; },
      "takeoff.acceptance_m"},
    ContractCase{
      "YawModeZero", [](MissionSpec & m) { m.items[0].takeoff.yaw.mode = 0; }, "takeoff.yaw.mode"},
    ContractCase{
      "YawKeepNonZero", [](MissionSpec & m) { m.items[0].takeoff.yaw.yaw_rad = 0.1; },
      "takeoff.yaw.yaw_rad"},
    ContractCase{
      "YawFixedPi",
      [](MissionSpec & m) {
        m.items[0].takeoff.yaw.mode = yaw_mode::kFixed;
        m.items[0].takeoff.yaw.yaw_rad = kPi;
      },
      "takeoff.yaw.yaw_rad"},
    ContractCase{
      "YawFixedNaN",
      [](MissionSpec & m) {
        m.items[0].takeoff.yaw.mode = yaw_mode::kFixed;
        m.items[0].takeoff.yaw.yaw_rad = kNaN;
      },
      "takeoff.yaw.yaw_rad"},
    ContractCase{
      "LoiterDurationZero", [](MissionSpec & m) { m.items[1].loiter.duration = Duration{}; },
      "loiter.duration"},
    ContractCase{
      "LoiterDurationEqualsTimeout",
      [](MissionSpec & m) { m.items[1].loiter.duration = m.items[1].timeout; }, "loiter.duration"},
    ContractCase{
      "UnusedTakeoffOnLand", [](MissionSpec & m) { m.items[2].takeoff.height_m = 1.0; },
      "items[2].takeoff"},
    ContractCase{
      "UnusedLoiterOnTakeoff", [](MissionSpec & m) { m.items[0].loiter.duration = seconds(1); },
      "items[0].loiter"},
    ContractCase{
      "UnusedGoToOnLoiter", [](MissionSpec & m) { m.items[1].go_to.acceptance_radius_m = 1.0; },
      "items[1].go_to"},
    ContractCase{
      "UnusedTrackOnLand", [](MissionSpec & m) { m.items[2].track_entity.target_id = "x"; },
      "items[2].track_entity"},
    ContractCase{
      "GoToNaN",
      [](MissionSpec & m) {
        m.items[0] = goto_item();
        m.items[0].go_to.position.y = kNaN;
      },
      "go_to.position"},
    ContractCase{
      "TrackZeroOffset",
      [](MissionSpec & m) {
        m.items[0] = track_item();
        m.items[0].track_entity.offset = Vec3{};
      },
      "track_entity.offset"},
    ContractCase{
      "TrackEmptyTarget",
      [](MissionSpec & m) {
        m.items[0] = track_item();
        m.items[0].track_entity.target_id.clear();
      },
      "track_entity.target_id"}),
  [](const ::testing::TestParamInfo<ContractCase> & info) { return std::string(info.param.name); });

TEST(ValidateMission, ContractAcceptsOtherTypesButExecutor1aDoesNot)
{
  // 계약은 GOTO, TRACK_ENTITY, RTL을 받는다. 1a 임시 제한이 거부한다.
  MissionSpec m;
  m.mission_id = "other";
  m.items = {takeoff_item(), goto_item(), track_item(), rtl_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid) << validate_mission_contract(m).detail;
  const MissionCheck check = validate_mission(m);
  EXPECT_FALSE(check.valid);
  EXPECT_NE(check.detail.find("not supported in 1a"), std::string::npos) << check.detail;
}

TEST(ValidateMission, LastItemMustBeLand)
{
  // U3: 공중에서 끝나는 미션은 1b. 1a는 INVALID_MISSION.
  MissionSpec m;
  m.mission_id = "air";
  m.items = {takeoff_item(), loiter_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid);
  const MissionCheck check = validate_mission(m);
  EXPECT_FALSE(check.valid);
  EXPECT_NE(check.detail.find("last item must be LAND"), std::string::npos) << check.detail;
}

TEST(ValidateMission, LandOnlyAsLast)
{
  MissionSpec m;
  m.mission_id = "ll";
  m.items = {land_item(), land_item()};
  EXPECT_FALSE(validate_mission(m).valid);
  m.items = {takeoff_item(), land_item(), loiter_item(), land_item()};
  EXPECT_FALSE(validate_mission(m).valid);
}

TEST(ValidateMission, FirstItemTakeoffOrLand)
{
  MissionSpec m;
  m.mission_id = "f";
  m.items = {loiter_item(), land_item()};
  const MissionCheck check = validate_mission(m);
  EXPECT_FALSE(check.valid);
  EXPECT_NE(check.detail.find("first item"), std::string::npos) << check.detail;
}

TEST(ValidateMission, TakeoffOnlyAsFirst)
{
  // 1a 임시 제한: TAKEOFF는 첫 항목에만 온다. 첫 항목이 아닌 TAKEOFF의 의미는 1b에서 정한다.
  MissionSpec m;
  m.mission_id = "tf";
  m.items = {takeoff_item(), loiter_item(), takeoff_item(), land_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid) << validate_mission_contract(m).detail;
  MissionCheck check = validate_mission(m);
  EXPECT_FALSE(check.valid);
  EXPECT_NE(check.detail.find("items[2].type"), std::string::npos) << check.detail;
  EXPECT_NE(check.detail.find("TAKEOFF is allowed only as the first item"), std::string::npos)
    << check.detail;

  m.items = {takeoff_item(), takeoff_item(), land_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid) << validate_mission_contract(m).detail;
  check = validate_mission(m);
  EXPECT_FALSE(check.valid);
  EXPECT_NE(check.detail.find("items[1].type"), std::string::npos) << check.detail;
  EXPECT_NE(check.detail.find("TAKEOFF is allowed only as the first item"), std::string::npos)
    << check.detail;

  // 첫 항목의 TAKEOFF는 그대로 받는다.
  m.items = {takeoff_item(), loiter_item(), loiter_item(), land_item()};
  EXPECT_TRUE(validate_mission(m).valid) << validate_mission(m).detail;
}

TEST(ScreenGoal, NonFirstTakeoffIsInvalidMission)
{
  MissionSpec m;
  m.mission_id = "tf";
  m.items = {takeoff_item(), loiter_item(), takeoff_item(), land_item()};
  const auto termination = screen_goal("v1", "v1", m, false);
  ASSERT_TRUE(termination.has_value());
  EXPECT_EQ(termination->status, Status::kAborted);
  EXPECT_EQ(termination->reason, Reason::kInvalidMission);
  EXPECT_NE(
    termination->detail.find("TAKEOFF is allowed only as the first item"), std::string::npos)
    << termination->detail;
}

TEST(ValidateMission, LandFirstMeansLengthOne)
{
  // LAND로 시작하면 LAND는 마지막에만 오므로 길이 1이다.
  MissionSpec m;
  m.mission_id = "lf";
  m.items = {land_item(), loiter_item()};
  EXPECT_FALSE(validate_mission(m).valid);
  m.items = {land_item()};
  EXPECT_TRUE(validate_mission(m).valid);
}

TEST(ScreenGoal, OrderIsIdThenInvalidThenBusy)
{
  MissionSpec invalid = standard_mission();
  invalid.items.clear();

  const std::optional<Termination> mismatch = screen_goal("px4_2", "px4_1", invalid, true);
  ASSERT_TRUE(mismatch.has_value());
  EXPECT_EQ(mismatch->reason, Reason::kVehicleIdMismatch);

  const std::optional<Termination> bad = screen_goal("px4_1", "px4_1", invalid, true);
  ASSERT_TRUE(bad.has_value());
  EXPECT_EQ(bad->reason, Reason::kInvalidMission);

  const std::optional<Termination> busy = screen_goal("px4_1", "px4_1", standard_mission(), true);
  ASSERT_TRUE(busy.has_value());
  EXPECT_EQ(busy->reason, Reason::kBusy);

  EXPECT_FALSE(screen_goal("px4_1", "px4_1", standard_mission(), false).has_value());

  for (const auto & term : {*mismatch, *bad, *busy}) {
    EXPECT_EQ(term.status, Status::kAborted);
    EXPECT_EQ(term.items_completed, 0U);
    EXPECT_EQ(term.last_item_index, 0U);
    EXPECT_FALSE(term.detail.empty());
    EXPECT_TRUE(is_consistent(term.status, term.reason));
  }
}

TEST(ScreenGoal, AirEndingMissionIsInvalidMission)
{
  MissionSpec m;
  m.mission_id = "air";
  m.items = {takeoff_item(), loiter_item()};
  const std::optional<Termination> term = screen_goal("px4_1", "px4_1", m, false);
  ASSERT_TRUE(term.has_value());
  EXPECT_EQ(term->reason, Reason::kInvalidMission);
}

TEST(MissionRunner, UnvalidatedMissionEndsInternalOnFirstStep)
{
  MissionSpec m = standard_mission();
  m.items.pop_back();
  Harness h(m);
  h.tick();
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
}

}  // namespace
}  // namespace idsim_mission::core::test
