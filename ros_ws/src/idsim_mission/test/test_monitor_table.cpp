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

// 비행 중 감시 표(decisions.md 쟁점 4 "비행 중 감시"). 순위는 재실측 (4) 전까지 잠정이다.
// - 순위마다 한 건(표 주도, 테스트 이름에 순위). 표의 행 수와 parametrize 수가 같다.
// - 같은 tick 동률: 동시에 맞을 수 있는 행 쌍 전부(1-3은 서로와 모든 행, 4-5끼리와 6-8끼리는 배타).
// - 순위 5의 failsafe 가지와 nav_state를 보지 않는다는 것.
// - OFFBOARD이고 ARMED인 채 failsafe가 true인 표본은 어느 행에도 맞지 않는다.
// - 감시 표로 끝낼 때의 disarm 1회 술어(8행 전수 x 입력 조합 전수).
// 상태기 안에서의 같은 판정(엇갈림, 이력의 항목 경계)은 test_runner_items.cpp에 있다.

#include <gtest/gtest.h>

#include <algorithm>
#include <cstddef>
#include <initializer_list>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "idsim_mission/core/rules.hpp"
#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core::test
{
namespace
{

// 아무 행도 맞지 않는 기준 입력: timestamp 성공, 식별 일치, 상태 신선, ARMED, OFFBOARD,
// failsafe 없음.
struct Probe
{
  StatusSample status;
  MonitorInput input;

  Probe()
  {
    status.identity = IdentityCheck::kMatch;
    status.arming = Arming::kArmed;
    status.nav = NavMode::kOffboard;
    status.nav_user_intention = NavMode::kOffboard;
    status.failsafe = false;
    input.timestamp_ok = true;
    input.landed = false;
    input.link_lost = false;
    input.failsafe_history = false;
  }

  // 이 행이 맞도록 입력을 바꾼다. 서로 배타가 아닌 행은 함께 적용해도 둘 다 맞는다.
  void apply(MonitorRow row)
  {
    switch (row) {
      case MonitorRow::kTimestampFailure:
        input.timestamp_ok = false;
        break;
      case MonitorRow::kIdentityMismatch:
        status.identity = IdentityCheck::kMismatch;
        status.identity_detail = "expected sysid 2, got 3";
        break;
      case MonitorRow::kLinkLost:
        input.link_lost = true;
        break;
      case MonitorRow::kDisarmedInAir:
        status.arming = Arming::kDisarmed;
        input.landed = false;
        break;
      case MonitorRow::kDisarmedOnGround:
        status.arming = Arming::kDisarmed;
        input.landed = true;
        break;
      case MonitorRow::kModeFailsafe:
        status.nav = NavMode::kLand;
        status.failsafe = true;
        break;
      case MonitorRow::kModeExternal:
        status.nav = NavMode::kHold;
        status.nav_user_intention = NavMode::kHold;
        status.failsafe = false;
        break;
      case MonitorRow::kModeDefensive:
        status.nav = NavMode::kHold;
        status.nav_user_intention = NavMode::kOffboard;
        status.failsafe = false;
        break;
    }
  }

  MonitorInput get()
  {
    MonitorInput in = input;
    in.status = &status;
    return in;
  }
};

// ---- 순위마다 한 건 ----

struct RowCase
{
  int rank;
  MonitorRow row;
  Reason reason;
  const char * name;
};

// decisions.md 쟁점 4 감시 표의 여덟 행. 순위 5는 이 표본의 failsafe와 이력이 없을 때.
const std::vector<RowCase> & row_table()
{
  static const std::vector<RowCase> table = {
    {1, MonitorRow::kTimestampFailure, Reason::kInternal, "Rank1_TimestampFailure"},
    {2, MonitorRow::kIdentityMismatch, Reason::kInternal, "Rank2_IdentityMismatch"},
    {3, MonitorRow::kLinkLost, Reason::kLinkLost, "Rank3_LinkLost"},
    {4, MonitorRow::kDisarmedInAir, Reason::kFailsafe, "Rank4_DisarmedInAir"},
    {5, MonitorRow::kDisarmedOnGround, Reason::kExternalDisarm, "Rank5_DisarmedOnGround"},
    {6, MonitorRow::kModeFailsafe, Reason::kFailsafe, "Rank6_ModeFailsafe"},
    {7, MonitorRow::kModeExternal, Reason::kExternalModeChange, "Rank7_ModeExternal"},
    {8, MonitorRow::kModeDefensive, Reason::kFailsafe, "Rank8_ModeDefensive"},
  };
  return table;
}

class MonitorRowTest : public ::testing::TestWithParam<RowCase>
{
};

TEST_P(MonitorRowTest, MatchesAloneWithReason)
{
  const RowCase & c = GetParam();
  EXPECT_EQ(monitor_rank(c.row), c.rank);
  Probe p;
  p.apply(c.row);
  const MonitorInput in = p.get();
  for (const MonitorRow other : kMonitorRankOrder) {
    EXPECT_EQ(monitor_row_matches(other, in), other == c.row)
      << c.name << " vs " << monitor_row_name(other);
  }
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(in);
  ASSERT_TRUE(verdict.has_value());
  EXPECT_EQ(verdict->row, c.row);
  EXPECT_EQ(verdict->reason, c.reason) << reason_name(verdict->reason);
  EXPECT_NE(verdict->detail.find("rank " + std::to_string(c.rank)), std::string::npos)
    << verdict->detail;
}

INSTANTIATE_TEST_SUITE_P(
  Table, MonitorRowTest, ::testing::ValuesIn(row_table()),
  [](const ::testing::TestParamInfo<RowCase> & info) { return std::string(info.param.name); });

TEST(MonitorTable, RowCountMatchesParametrize)
{
  EXPECT_EQ(kMonitorRankOrder.size(), 8U);
  EXPECT_EQ(row_table().size(), kMonitorRankOrder.size());
  for (std::size_t i = 0; i < row_table().size(); ++i) {
    EXPECT_EQ(row_table()[i].row, kMonitorRankOrder[i]);
  }
}

TEST(MonitorTable, NothingMatchesOnHealthySample)
{
  Probe p;
  EXPECT_FALSE(evaluate_monitor(p.get()).has_value());
}

TEST(MonitorTable, MissingStatusIsLinkLost)
{
  MonitorInput in;
  in.status = nullptr;
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(in);
  ASSERT_TRUE(verdict.has_value());
  EXPECT_EQ(verdict->row, MonitorRow::kLinkLost);
}

TEST(MonitorTable, OffboardArmedFailsafeEndsNothing)
{
  // 방어 경로(합성 표본): PX4 v1.17.0에서 OFFBOARD이고 ARMED인 채 failsafe가 true인 표본은 나오지
  // 않는다. 나와도 goal을 끝내지 않는다(decisions.md 쟁점 4 "비행 중 감시" 표 아래 문단).
  Probe p;
  p.status.failsafe = true;
  EXPECT_FALSE(evaluate_monitor(p.get()).has_value());
}

// ---- 같은 tick 동률(표 주도) ----

bool exclusive(MonitorRow a, MonitorRow b)
{
  auto in = [](MonitorRow r, std::initializer_list<MonitorRow> set) {
    for (const MonitorRow s : set) {
      if (s == r) {
        return true;
      }
    }
    return false;
  };
  const auto disarm = {MonitorRow::kDisarmedInAir, MonitorRow::kDisarmedOnGround};
  const auto mode = {
    MonitorRow::kModeFailsafe, MonitorRow::kModeExternal, MonitorRow::kModeDefensive};
  return (in(a, disarm) && in(b, disarm)) || (in(a, mode) && in(b, mode));
}

struct TieCase
{
  MonitorRow higher;
  MonitorRow lower;
};

std::vector<TieCase> tie_table()
{
  std::vector<TieCase> table;
  for (std::size_t i = 0; i < kMonitorRankOrder.size(); ++i) {
    for (std::size_t j = i + 1; j < kMonitorRankOrder.size(); ++j) {
      if (!exclusive(kMonitorRankOrder[i], kMonitorRankOrder[j])) {
        table.push_back({kMonitorRankOrder[i], kMonitorRankOrder[j]});
      }
    }
  }
  return table;
}

class MonitorTieTest : public ::testing::TestWithParam<TieCase>
{
};

TEST_P(MonitorTieTest, HigherRankWins)
{
  const TieCase & c = GetParam();
  Probe p;
  p.apply(c.lower);
  p.apply(c.higher);
  const MonitorInput in = p.get();
  ASSERT_TRUE(monitor_row_matches(c.higher, in));
  ASSERT_TRUE(monitor_row_matches(c.lower, in));
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(in);
  ASSERT_TRUE(verdict.has_value());
  EXPECT_EQ(verdict->row, c.higher);
  // matched는 맞는 행 전부를 순위 순서로 담는다(전이 관측의 겹침 칸. decisions.md 1b 쟁점 13).
  const std::vector<MonitorRow> & m = verdict->matched;
  ASSERT_FALSE(m.empty());
  EXPECT_EQ(m.front(), c.higher);
  EXPECT_NE(std::find(m.begin(), m.end(), c.higher), m.end());
  EXPECT_NE(std::find(m.begin(), m.end(), c.lower), m.end());
  for (std::size_t i = 1; i < m.size(); ++i) {
    EXPECT_LT(monitor_rank(m[i - 1]), monitor_rank(m[i]));
  }
}

INSTANTIATE_TEST_SUITE_P(
  Pairs, MonitorTieTest, ::testing::ValuesIn(tie_table()),
  [](const ::testing::TestParamInfo<TieCase> & info) {
    return "Rank" + std::to_string(monitor_rank(info.param.higher)) + "_" +
           monitor_row_name(info.param.higher) + "_Over_Rank" +
           std::to_string(monitor_rank(info.param.lower)) + "_" +
           monitor_row_name(info.param.lower);
  });

TEST(MonitorTable, TiePairCount)
{
  // 8행에서 28쌍. 배타 쌍은 4-5 한 쌍과 6-8 세 쌍이다.
  EXPECT_EQ(tie_table().size(), 24U);
}

TEST(MonitorTable, ExclusiveRowsNeverMatchTogether)
{
  for (const MonitorRow a : kMonitorRankOrder) {
    for (const MonitorRow b : kMonitorRankOrder) {
      if (a == b || !exclusive(a, b)) {
        continue;
      }
      Probe p;
      p.apply(a);
      p.apply(b);
      const MonitorInput in = p.get();
      EXPECT_FALSE(monitor_row_matches(a, in) && monitor_row_matches(b, in))
        << monitor_row_name(a) << " " << monitor_row_name(b);
    }
  }
}

// ---- 순위 5 ----

TEST(MonitorRank5, SampleFailsafeIsFailsafe)
{
  // 이 표본의 failsafe가 true인 지상 DISARMED(명령 disarm, failsafe 동작 Disarm)는 FAILSAFE.
  Probe p;
  p.apply(MonitorRow::kDisarmedOnGround);
  p.status.failsafe = true;
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(p.get());
  ASSERT_TRUE(verdict.has_value());
  EXPECT_EQ(verdict->row, MonitorRow::kDisarmedOnGround);
  EXPECT_EQ(verdict->reason, Reason::kFailsafe);
}

TEST(MonitorRank5, HistoryFailsafeIsFailsafe)
{
  // 방어 경로(합성 표본): 앞선 표본의 failsafe 이력은 v1.17.0에서 OFFBOARD인 채로는 생기지 않는다.
  Probe p;
  p.apply(MonitorRow::kDisarmedOnGround);
  p.input.failsafe_history = true;
  const std::optional<MonitorVerdict> verdict = evaluate_monitor(p.get());
  ASSERT_TRUE(verdict.has_value());
  EXPECT_EQ(verdict->reason, Reason::kFailsafe);
}

TEST(MonitorRank5, NavStateOfThisSampleIsNotRead)
{
  // 지상 DISARMED 표본의 nav_state가 OFFBOARD가 아니어도(모드 행이 함께 맞아도) 순위 5의 결과는
  // 같다. failsafe가 false이고 이력이 없으면 EXTERNAL_DISARM.
  for (const NavMode nav : {NavMode::kOffboard, NavMode::kHold, NavMode::kLand, NavMode::kOther}) {
    for (const NavMode intention : {NavMode::kOffboard, NavMode::kHold}) {
      Probe p;
      p.apply(MonitorRow::kDisarmedOnGround);
      p.status.nav = nav;
      p.status.nav_user_intention = intention;
      const std::optional<MonitorVerdict> verdict = evaluate_monitor(p.get());
      ASSERT_TRUE(verdict.has_value());
      EXPECT_EQ(verdict->row, MonitorRow::kDisarmedOnGround);
      EXPECT_EQ(verdict->reason, Reason::kExternalDisarm);
    }
  }
}

// ---- 감시 표로 끝낼 때의 disarm 1회(decisions.md 쟁점 4 표 아래 "지상 disarm 1회") ----

struct DisarmRuleCase
{
  MonitorRow row;
  MonitorDisarm rule;
};

const std::vector<DisarmRuleCase> & disarm_rule_table()
{
  // 순위 1, 4, 5는 보내지 않는다. 순위 2는 arm을 보냈으면 조건 없이, 순위 3, 6, 7, 8은 조건 셋.
  static const std::vector<DisarmRuleCase> table = {
    {MonitorRow::kTimestampFailure, MonitorDisarm::kNever},
    {MonitorRow::kIdentityMismatch, MonitorDisarm::kIfArmSent},
    {MonitorRow::kLinkLost, MonitorDisarm::kIfNeverAirborne},
    {MonitorRow::kDisarmedInAir, MonitorDisarm::kNever},
    {MonitorRow::kDisarmedOnGround, MonitorDisarm::kNever},
    {MonitorRow::kModeFailsafe, MonitorDisarm::kIfNeverAirborne},
    {MonitorRow::kModeExternal, MonitorDisarm::kIfNeverAirborne},
    {MonitorRow::kModeDefensive, MonitorDisarm::kIfNeverAirborne},
  };
  return table;
}

TEST(MonitorDisarm, RuleOfEveryRow)
{
  ASSERT_EQ(disarm_rule_table().size(), kMonitorRankOrder.size());
  for (std::size_t i = 0; i < kMonitorRankOrder.size(); ++i) {
    EXPECT_EQ(disarm_rule_table()[i].row, kMonitorRankOrder[i]);
    EXPECT_EQ(monitor_row_disarm(kMonitorRankOrder[i]), disarm_rule_table()[i].rule)
      << monitor_row_name(kMonitorRankOrder[i]);
  }
}

TEST(MonitorDisarm, PredicateOverAllInputs)
{
  // 8행 x 입력 16조합(arm_sent, landed_false_seen, landed_known, landed) 전수.
  for (const DisarmRuleCase & c : disarm_rule_table()) {
    for (int bits = 0; bits < 16; ++bits) {
      MonitorDisarmInput in;
      in.arm_sent = (bits & 1) != 0;
      in.landed_false_seen = (bits & 2) != 0;
      in.landed_known = (bits & 4) != 0;
      in.landed = (bits & 8) != 0;
      bool expected = false;
      switch (c.rule) {
        case MonitorDisarm::kNever:
          expected = false;
          break;
        case MonitorDisarm::kIfArmSent:
          expected = in.arm_sent;
          break;
        case MonitorDisarm::kIfNeverAirborne:
          expected = in.arm_sent && !in.landed_false_seen && in.landed_known && in.landed;
          break;
      }
      EXPECT_EQ(monitor_sends_disarm(c.row, in), expected)
        << monitor_row_name(c.row) << " bits " << bits;
    }
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
