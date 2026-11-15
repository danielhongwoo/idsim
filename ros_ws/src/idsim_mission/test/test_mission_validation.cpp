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
// 결정: docs/interface.md "수락 정책", "미션 정의".

#include <gtest/gtest.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <utility>
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

MissionSpec mission_of_track(const std::string & target_id)
{
  MissionSpec m;
  m.mission_id = "track";
  ItemSpec track = track_item();
  track.track_entity.target_id = target_id;
  m.items = {takeoff_item(), track, land_item()};
  return m;
}

TEST(ValidateMission, StandardAndLandOnlyAreValid)
{
  EXPECT_TRUE(validate_mission_contract(standard_mission()).valid);
  EXPECT_TRUE(validate_mission_contract(land_only_mission()).valid);
  MissionSpec two;
  two.mission_id = "two";
  two.items = {takeoff_item(), land_item()};
  EXPECT_TRUE(validate_mission_contract(two).valid);
}

TEST(ValidateMission, TargetIdRule)
{
  // ^[a-z][a-z0-9_]{0,31}$(TargetState.target_id). idsim_common::TargetId::parse와의 대조는
  // test/node/test_contract_constants.cpp.
  EXPECT_TRUE(is_valid_target_id("a"));
  EXPECT_TRUE(is_valid_target_id("car_1"));
  EXPECT_TRUE(is_valid_target_id("a" + std::string(31, '9')));
  EXPECT_FALSE(is_valid_target_id(""));
  EXPECT_FALSE(is_valid_target_id("a" + std::string(32, '9')));
  EXPECT_FALSE(is_valid_target_id("1car"));
  EXPECT_FALSE(is_valid_target_id("_car"));
  EXPECT_FALSE(is_valid_target_id("Car"));
  EXPECT_FALSE(is_valid_target_id("car-1"));
  EXPECT_FALSE(is_valid_target_id("car/1"));
  MissionSpec m = mission_of_track("Car-1");
  const MissionCheck check = validate_mission_contract(m);
  EXPECT_FALSE(check.valid);
  EXPECT_EQ(
    check.detail, "items[1].track_entity.target_id 'Car-1' does not match ^[a-z][a-z0-9_]{0,31}$");
}

TEST(ValidateMission, CoordinateBoundPredicate)
{
  // 미션 검증과 노드의 표적 표본 변환이 함께 쓰는 술어(docs/interface.md "GoToItem과
  // TrackEntityItem").
  EXPECT_EQ(kMaxContractCoordinateM, 1e5);
  EXPECT_TRUE(within_coordinate_bound(Vec3{1e5, -1e5, 0.0}));
  EXPECT_FALSE(within_coordinate_bound(Vec3{std::nextafter(1e5, 2e5), 0.0, 0.0}));
  EXPECT_FALSE(within_coordinate_bound(Vec3{0.0, -1e5 - 1.0, 0.0}));
  EXPECT_FALSE(within_coordinate_bound(Vec3{0.0, 0.0, kNaN}));
  EXPECT_FALSE(within_coordinate_bound(Vec3{std::numeric_limits<double>::infinity(), 0.0, 0.0}));
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

// 계약 좌표 상한(docs/interface.md "GoToItem과 TrackEntityItem"): GOTO position과 TRACK_ENTITY
// offset의 각 성분 절댓값이 1e5 m 이하(경계 포함). 유한 검사 뒤에 보므로 NaN의 detail은 그대로다.
TEST(ValidateMissionContract, CoordinateBound)
{
  const double above = std::nextafter(1e5, std::numeric_limits<double>::infinity());
  const auto single = [](const ItemSpec & item) {
    MissionSpec m;
    m.mission_id = "bound";
    m.items = {item};
    return m;
  };
  for (int axis = 0; axis < 3; ++axis) {
    const auto set = [axis](Vec3 & v, double value) {
      (axis == 0 ? v.x : axis == 1 ? v.y : v.z) = value;
    };
    for (const double ok : {1e5, -1e5}) {
      ItemSpec g = goto_item();
      set(g.go_to.position, ok);
      EXPECT_TRUE(validate_mission_contract(single(g)).valid)
        << "goto axis " << axis << " " << ok << ": " << validate_mission_contract(single(g)).detail;
      ItemSpec t = track_item();
      set(t.track_entity.offset, ok);
      EXPECT_TRUE(validate_mission_contract(single(t)).valid)
        << "track axis " << axis << " " << ok << ": "
        << validate_mission_contract(single(t)).detail;
    }
    for (const double bad : {above, -above}) {
      ItemSpec g = goto_item();
      set(g.go_to.position, bad);
      MissionCheck check = validate_mission_contract(single(g));
      EXPECT_FALSE(check.valid) << "goto axis " << axis;
      EXPECT_EQ(check.detail, "items[0].go_to.position components must be within [-1e5, 1e5] m");
      ItemSpec t = track_item();
      set(t.track_entity.offset, bad);
      check = validate_mission_contract(single(t));
      EXPECT_FALSE(check.valid) << "track axis " << axis;
      EXPECT_EQ(
        check.detail, "items[0].track_entity.offset components must be within [-1e5, 1e5] m");
    }
  }
  // 1e5 m보다 크고 1e6 m 이하인 값도 상한 밖이다.
  for (const double bad : {5e5, -5e5}) {
    ItemSpec g = goto_item();
    g.go_to.position.x = bad;
    EXPECT_EQ(
      validate_mission_contract(single(g)).detail,
      "items[0].go_to.position components must be within [-1e5, 1e5] m");
    ItemSpec t = track_item();
    t.track_entity.offset.y = bad;
    EXPECT_EQ(
      validate_mission_contract(single(t)).detail,
      "items[0].track_entity.offset components must be within [-1e5, 1e5] m");
  }
  // NaN은 유한 검사의 detail(검사 순서).
  ItemSpec g = goto_item();
  g.go_to.position.x = kNaN;
  EXPECT_EQ(validate_mission_contract(single(g)).detail, "items[0].go_to.position must be finite");
  ItemSpec t = track_item();
  t.track_entity.offset.y = kNaN;
  EXPECT_EQ(
    validate_mission_contract(single(t)).detail,
    "items[0].track_entity.offset must be finite and non-zero");
  // 상한을 넘는 둘째 항목.
  MissionSpec two;
  two.mission_id = "bound";
  ItemSpec far = goto_item();
  far.go_to.position.z = -2e5;
  two.items = {goto_item(), far};
  EXPECT_EQ(
    validate_mission_contract(two).detail,
    "items[1].go_to.position components must be within [-1e5, 1e5] m");
  far = track_item();
  far.track_entity.offset.x = 2e5;
  two.items = {goto_item(), far};
  EXPECT_EQ(
    validate_mission_contract(two).detail,
    "items[1].track_entity.offset components must be within [-1e5, 1e5] m");
  // goal 접수는 계약 검증의 문장을 그대로 낸다.
  ItemSpec goal_item = goto_item();
  goal_item.go_to.position = Vec3{2e5, 0.0, 5.0};
  const std::optional<Termination> term = screen_goal("px4_1", "px4_1", single(goal_item), false);
  ASSERT_TRUE(term.has_value());
  EXPECT_EQ(term->status, Status::kAborted);
  EXPECT_EQ(term->reason, Reason::kInvalidMission);
  EXPECT_EQ(term->detail, "items[0].go_to.position components must be within [-1e5, 1e5] m");
  // TAKEOFF height_m에는 상한이 없다.
  ItemSpec high = takeoff_item();
  high.takeoff.height_m = 1e30;
  EXPECT_TRUE(validate_mission_contract(single(high)).valid)
    << validate_mission_contract(single(high)).detail;
}

TEST(ScreenGoal, AcceptsGotoTrackEntityAndRtl)
{
  // goal 접수는 계약 검증만 한다(docs/interface.md "준비 단계". B10에서 1a 제한을 지웠다).
  MissionSpec m;
  m.mission_id = "other";
  m.items = {takeoff_item(), goto_item(), track_item(), rtl_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid) << validate_mission_contract(m).detail;
  EXPECT_FALSE(screen_goal("px4_1", "px4_1", m, false).has_value());
}

TEST(ValidateMission, LandOnlyAsLast)
{
  MissionSpec m;
  m.mission_id = "ll";
  m.items = {land_item(), land_item()};
  EXPECT_FALSE(validate_mission_contract(m).valid);
  m.items = {takeoff_item(), land_item(), loiter_item(), land_item()};
  EXPECT_FALSE(validate_mission_contract(m).valid);
}

TEST(ValidateMission, TakeoffOnlyAsFirst)
{
  // 계약: TAKEOFF는 첫 항목에만 온다(docs/interface.md "미션 정의").
  MissionSpec m;
  m.mission_id = "tf";
  m.items = {takeoff_item(), loiter_item(), takeoff_item(), land_item()};
  EXPECT_FALSE(validate_mission_contract(m).valid);
  EXPECT_NE(
    validate_mission_contract(m).detail.find(
      "items[2].type TAKEOFF is allowed only as the first item"),
    std::string::npos)
    << validate_mission_contract(m).detail;

  m.items = {takeoff_item(), takeoff_item(), land_item()};
  EXPECT_FALSE(validate_mission_contract(m).valid);
  EXPECT_NE(
    validate_mission_contract(m).detail.find(
      "items[1].type TAKEOFF is allowed only as the first item"),
    std::string::npos)
    << validate_mission_contract(m).detail;

  // 첫 항목의 TAKEOFF는 그대로 받는다.
  m.items = {takeoff_item(), loiter_item(), loiter_item(), land_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid) << validate_mission_contract(m).detail;
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

std::string order_name(const MissionSpec & m)
{
  std::string name;
  for (const ItemSpec & item : m.items) {
    name += name.empty() ? "" : ",";
    name += item_type_name(item.type);
  }
  return name;
}

MissionSpec mission_of(std::vector<ItemSpec> items)
{
  MissionSpec m;
  m.mission_id = "order";
  m.items = std::move(items);
  return m;
}

TEST(ValidateMissionContract, OrderRule)
{
  // docs/interface.md "미션 정의", "준비 단계".
  struct Case
  {
    std::vector<ItemSpec> items;
    const char * detail;
  };
  const std::vector<Case> rejects = {
    {{takeoff_item(), takeoff_item(), land_item()},
     "items[1].type TAKEOFF is allowed only as the first item"},
    {{takeoff_item(), loiter_item(), takeoff_item(), land_item()},
     "items[2].type TAKEOFF is allowed only as the first item"},
    {{land_item(), loiter_item()}, "items[0].type LAND is allowed only as the last item"},
    {{rtl_item(), land_item()}, "items[0].type RTL is allowed only as the last item"},
    {{takeoff_item(), rtl_item(), loiter_item()},
     "items[1].type RTL is allowed only as the last item"},
  };
  for (const Case & c : rejects) {
    const MissionSpec m = mission_of(c.items);
    const MissionCheck check = validate_mission_contract(m);
    EXPECT_FALSE(check.valid) << order_name(m);
    EXPECT_EQ(check.detail, c.detail) << order_name(m);
  }
  const std::vector<std::vector<ItemSpec>> accepts = {
    {rtl_item()},
    {takeoff_item(), rtl_item()},
    {takeoff_item(), goto_item(), track_item(), rtl_item()},
  };
  for (const auto & items : accepts) {
    const MissionSpec m = mission_of(items);
    const MissionCheck check = validate_mission_contract(m);
    EXPECT_TRUE(check.valid) << order_name(m) << ": " << check.detail;
  }
}

TEST(ValidateMissionContract, FieldErrorWinsOverOrderViolation)
{
  // 순서 규칙은 모든 항목의 필드 검사 뒤에 본다.
  MissionSpec m = mission_of({land_item(), takeoff_item()});
  m.items[1].takeoff.height_m = 0.0;
  const MissionCheck check = validate_mission_contract(m);
  EXPECT_FALSE(check.valid);
  EXPECT_EQ(check.detail, "items[1].takeoff.height_m must be finite and > 0");
}

TEST(ScreenGoal, OrderViolationDetailIsContractWording)
{
  // goal 접수에서 바뀌는 것은 순서를 어긴 미션의 detail뿐이다(status, reason은 그대로).
  struct Case
  {
    std::vector<ItemSpec> items;
    const char * detail;
  };
  const std::vector<Case> cases = {
    {{takeoff_item(), loiter_item(), takeoff_item(), land_item()},
     "items[2].type TAKEOFF is allowed only as the first item"},
    {{takeoff_item(), land_item(), loiter_item(), land_item()},
     "items[1].type LAND is allowed only as the last item"},
    {{goto_item(), takeoff_item(), land_item()},
     "items[1].type TAKEOFF is allowed only as the first item"},
    {{rtl_item(), land_item()}, "items[0].type RTL is allowed only as the last item"},
    {{takeoff_item(), rtl_item(), land_item()},
     "items[1].type RTL is allowed only as the last item"},
    {{land_item(), takeoff_item()}, "items[0].type LAND is allowed only as the last item"},
  };
  for (const Case & c : cases) {
    const MissionSpec m = mission_of(c.items);
    const std::optional<Termination> term = screen_goal("px4_1", "px4_1", m, false);
    ASSERT_TRUE(term.has_value()) << order_name(m);
    EXPECT_EQ(term->status, Status::kAborted) << order_name(m);
    EXPECT_EQ(term->reason, Reason::kInvalidMission) << order_name(m);
    EXPECT_EQ(term->detail, c.detail) << order_name(m);
  }
}

TEST(ValidateMission, LandFirstMeansLengthOne)
{
  // LAND로 시작하면 LAND는 마지막에만 오므로 길이 1이다.
  MissionSpec m;
  m.mission_id = "lf";
  m.items = {land_item(), loiter_item()};
  EXPECT_FALSE(validate_mission_contract(m).valid);
  m.items = {land_item()};
  EXPECT_TRUE(validate_mission_contract(m).valid);
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

TEST(ScreenGoal, MalformedTargetIdIsInvalidMission)
{
  // 시나리오 B의 "형식이 틀린 target_id"(tests/sitl/README.md "시나리오와 판정"). 형식이 맞지만
  // 없는 표적은 접수된다(TARGET_LOST로 드러난다).
  const std::optional<Termination> term =
    screen_goal("px4_1", "px4_1", mission_of_track("car-1"), false);
  ASSERT_TRUE(term.has_value());
  EXPECT_EQ(term->reason, Reason::kInvalidMission);
  EXPECT_NE(term->detail.find("track_entity.target_id 'car-1'"), std::string::npos) << term->detail;
  EXPECT_FALSE(
    screen_goal("px4_1", "px4_1", mission_of_track("no_such_target"), false).has_value());
}

TEST(MissionRunner, UnvalidatedMissionEndsInternalOnFirstStep)
{
  // 계약 순서 규칙을 어긴 미션(LAND가 마지막이 아니다). runner는 첫 step에서 INTERNAL로 끝낸다.
  MissionSpec m;
  m.mission_id = "order";
  m.items = {takeoff_item(), land_item(), loiter_item()};
  Harness h(m);
  h.tick();
  ASSERT_TRUE(h.termination().has_value());
  const MissionCheck check = validate_mission_contract(m);
  ASSERT_FALSE(check.valid);
  EXPECT_EQ(
    h.termination()->detail, "mission did not pass validate_mission_contract: " + check.detail);
  EXPECT_EQ(
    h.termination()->detail,
    "mission did not pass validate_mission_contract: items[1].type LAND is allowed only as the "
    "last item");
  expect_terminated_once(h, Status::kAborted, Reason::kInternal);
}

// 항목 type 여섯으로 만든 길이 4 이하의 모든 순서(6 + 36 + 216 + 1296 = 1554개)에서 goal 접수가
// 받는 미션과 runner(계약)가 받는 미션이 같다.
// 필드는 type마다 유효한 기본값이라 계약의 필드 검사는 늘 통과하고, 순서와 type만 갈린다.
std::vector<MissionSpec> all_orders_up_to_four()
{
  const std::vector<ItemSpec> items = {takeoff_item(), goto_item(), track_item(),
                                       loiter_item(),  rtl_item(),  land_item()};
  std::vector<MissionSpec> missions;
  std::vector<std::vector<std::size_t>> layer = {{}};
  for (std::size_t length = 1; length <= 4; ++length) {
    std::vector<std::vector<std::size_t>> next;
    for (const auto & prefix : layer) {
      for (std::size_t k = 0; k < items.size(); ++k) {
        std::vector<std::size_t> order = prefix;
        order.push_back(k);
        MissionSpec m;
        m.mission_id = "order";
        for (const std::size_t index : order) {
          m.items.push_back(items[index]);
        }
        missions.push_back(m);
        next.push_back(order);
      }
    }
    layer = std::move(next);
  }
  return missions;
}

TEST(ScreenGoal, AcceptsExactlyWhatContractAccepts)
{
  const std::vector<MissionSpec> missions = all_orders_up_to_four();
  ASSERT_EQ(missions.size(), 1554U);
  int accepted = 0;
  for (const MissionSpec & m : missions) {
    const bool contract = validate_mission_contract(m).valid;
    const std::optional<Termination> term = screen_goal("px4_1", "px4_1", m, false);
    EXPECT_EQ(!term.has_value(), contract) << order_name(m);
    if (term.has_value()) {
      EXPECT_EQ(term->reason, Reason::kInvalidMission) << order_name(m);
      EXPECT_EQ(term->detail, validate_mission_contract(m).detail) << order_name(m);
    }
    accepted += contract ? 1 : 0;
  }
  // TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만 오는 순서 266개.
  EXPECT_EQ(accepted, 266);
}

}  // namespace
}  // namespace idsim_mission::core::test
