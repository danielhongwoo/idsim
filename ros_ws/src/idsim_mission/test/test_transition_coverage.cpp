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

// 전이 칸 목록(test/transition_cells.tsv)과 관측의 대조(decisions.md 쟁점 13).
//
// test_runner 실행 파일의 모든 상태기 테스트가 끝난 뒤 Environment::TearDown에서 단정한다.
// (1) 관측한 칸 집합 == "covered" 부류 (2) "impossible" 칸은 관측되지 않았다 (3) 목록에 없는 칸은
// 관측되지 않았다 (4) untagged 기록 0. Event 이름 집합 == 목록의 사건 집합과 파일 형식은 보통
// 테스트로 본다. --gtest_filter 등으로 일부만 돌리면 (1)-(4)를 건너뛰고 그 사실을 출력한다.
// 환경변수 IDSIM_TRANSITION_CELLS_DUMP에 경로를 주면 관측한 칸을 같은 형식(class는 covered)으로 그
// 경로에 쓴다(칸 목록의 diff를 만들 때 쓴다).
//
// 칸 목록 파일 형식: 탭으로 나눈 7열(from, event, to, reason, class, also_true, note). '#'으로
// 시작하는 줄과 빈 줄은 건너뛰고, 첫 데이터 줄은 머리줄이다. class는 covered(덮임),
// impossible(불가능. note에 이유), uncovered(미덮임)다. also_true는 겹침 칸에서 이긴 사건과 함께
// 참이던 사건 하나, 아니면 "-"다(한 기록에 함께 참이던 사건이 여럿이면 쌍마다 한 칸).

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "idsim_mission/core/transition.hpp"
#include "runner_harness.hpp"
#include "transition_recorder.hpp"

namespace idsim_mission::core::test
{
namespace
{

struct ListedCell
{
  std::string cls;
  std::string note;
  int line{0};
};

struct CellList
{
  std::map<Cell, ListedCell> cells;
  std::vector<std::string> errors;
};

std::vector<std::string> split(const std::string & text, char sep)
{
  std::vector<std::string> parts;
  std::string part;
  std::istringstream in(text);
  while (std::getline(in, part, sep)) {
    parts.push_back(part);
  }
  if (!text.empty() && text.back() == sep) {
    parts.emplace_back();
  }
  return parts;
}

CellList load_cells()
{
  CellList list;
  std::ifstream in(IDSIM_TRANSITION_CELLS);
  if (!in) {
    list.errors.push_back(std::string("cannot open ") + IDSIM_TRANSITION_CELLS);
    return list;
  }
  const std::vector<std::string> header = {"from", "event", "to", "reason",
                                           "class", "also_true", "note"};
  std::string line;
  int line_no = 0;
  bool header_seen = false;
  while (std::getline(in, line)) {
    ++line_no;
    if (line.empty() || line.front() == '#') {
      continue;
    }
    const std::vector<std::string> cols = split(line, '\t');
    const std::string where = "line " + std::to_string(line_no) + ": ";
    if (!header_seen) {
      header_seen = true;
      if (cols != header) {
        list.errors.push_back(where + "header must be: from event to reason class also_true note");
      }
      continue;
    }
    if (cols.size() != header.size()) {
      list.errors.push_back(where + "expected 7 tab-separated columns");
      continue;
    }
    Cell cell{cols[0], cols[1], cols[2], cols[3], cols[5]};
    ListedCell listed{cols[4], cols[6], line_no};
    if (listed.cls != "covered" && listed.cls != "impossible" && listed.cls != "uncovered") {
      list.errors.push_back(where + "class must be covered, impossible or uncovered");
    }
    if (listed.cls == "impossible" && (listed.note.empty() || listed.note == "-")) {
      list.errors.push_back(where + "impossible cell needs a reason in note");
    }
    if ((cell.to == "DONE") == (cell.reason == "-")) {
      list.errors.push_back(where + "reason must be <status>/<reason> exactly when to is DONE");
    }
    if (!list.cells.emplace(cell, listed).second) {
      list.errors.push_back(where + "duplicate cell");
    }
  }
  if (!header_seen) {
    list.errors.push_back("no header line");
  }
  return list;
}

std::set<std::string> enum_event_names()
{
  std::set<std::string> names;
  for (const Event event : kAllEvents) {
    names.insert(event_name(event));
  }
  return names;
}

TEST(TransitionCells, FileIsWellFormed)
{
  const CellList list = load_cells();
  for (const std::string & error : list.errors) {
    ADD_FAILURE() << IDSIM_TRANSITION_CELLS << " " << error;
  }
  EXPECT_FALSE(list.cells.empty());
}

TEST(TransitionCells, EventNamesMatchList)
{
  // Event enum의 이름 집합 == 목록의 사건 열 집합. 함께 참 열의 사건도 enum에 있어야 한다.
  const CellList list = load_cells();
  const std::set<std::string> names = enum_event_names();
  EXPECT_EQ(names.size(), kAllEvents.size()) << "event names must be distinct";
  for (std::size_t i = 0; i < kAllEvents.size(); ++i) {
    EXPECT_EQ(static_cast<std::size_t>(kAllEvents[i]), i) << "kAllEvents must follow Event values";
  }
  std::set<std::string> listed;
  for (const auto & [cell, info] : list.cells) {
    listed.insert(cell.event);
    if (cell.also_true != "-") {
      EXPECT_EQ(names.count(cell.also_true), 1U)
        << "line " << info.line << ": unknown event " << cell.also_true;
    }
  }
  for (const std::string & name : names) {
    EXPECT_EQ(listed.count(name), 1U) << "Event " << name << " has no cell in the list";
  }
  for (const std::string & name : listed) {
    EXPECT_EQ(names.count(name), 1U) << "listed event " << name << " is not in Event";
  }
}

TEST(TransitionCells, RecorderIsOnInThisExecutable)
{
  // 기록기는 Environment가 켠다. 꺼져 있으면 대조가 빈 관측으로 돈다.
  EXPECT_NE(active_transition_recorder(), nullptr);
}

// 기록기를 켜고 끈 두 실행의 tick별 출력이 같다(계측이 동작을 바꾸지 않는다). 시나리오는 정상
// 경로, 공중 취소(Hold), 지상 취소(arm 뒤 disarm), Px4Timestamp 실패다.
void expect_same_outputs(const Harness & on, const Harness & off)
{
  ASSERT_EQ(on.outputs().size(), off.outputs().size());
  for (std::size_t i = 0; i < on.outputs().size(); ++i) {
    const StepOutput & a = on.outputs()[i];
    const StepOutput & b = off.outputs()[i];
    EXPECT_EQ(a.px4_timestamp_us, b.px4_timestamp_us) << "tick " << i;
    EXPECT_EQ(a.commands, b.commands) << "tick " << i;
    ASSERT_EQ(a.setpoint.has_value(), b.setpoint.has_value()) << "tick " << i;
    if (a.setpoint.has_value()) {
      EXPECT_EQ(a.setpoint->kind, b.setpoint->kind) << "tick " << i;
      EXPECT_EQ(a.setpoint->x, b.setpoint->x) << "tick " << i;
      EXPECT_EQ(a.setpoint->y, b.setpoint->y) << "tick " << i;
      EXPECT_EQ(a.setpoint->z, b.setpoint->z) << "tick " << i;
      EXPECT_EQ(a.setpoint->yaw_ned, b.setpoint->yaw_ned) << "tick " << i;
    }
    ASSERT_EQ(a.feedback.has_value(), b.feedback.has_value()) << "tick " << i;
    if (a.feedback.has_value()) {
      EXPECT_EQ(a.feedback->stamp_ns, b.feedback->stamp_ns) << "tick " << i;
      EXPECT_EQ(a.feedback->item_index, b.feedback->item_index) << "tick " << i;
      EXPECT_EQ(a.feedback->phase, b.feedback->phase) << "tick " << i;
      EXPECT_EQ(a.feedback->distance_valid, b.feedback->distance_valid) << "tick " << i;
      EXPECT_EQ(a.feedback->distance_remaining_m, b.feedback->distance_remaining_m) << "tick " << i;
    }
    ASSERT_EQ(a.termination.has_value(), b.termination.has_value()) << "tick " << i;
    if (a.termination.has_value()) {
      EXPECT_EQ(a.termination->status, b.termination->status);
      EXPECT_EQ(a.termination->reason, b.termination->reason);
      EXPECT_EQ(a.termination->items_completed, b.termination->items_completed);
      EXPECT_EQ(a.termination->last_item_index, b.termination->last_item_index);
      EXPECT_EQ(a.termination->detail, b.termination->detail);
    }
  }
}

enum class Scenario
{
  kSuccess,
  kCancelAir,
  kCancelGround,
  kStampFailure,
};

void run_scenario(Harness & h, Scenario scenario)
{
  switch (scenario) {
    case Scenario::kSuccess:
      h.drive_to_land();
      h.tick();
      h.run_until([&h] { return h.view().land_confirmed; }, 10);
      h.world.landed = true;
      h.world.arming = Arming::kDisarmed;
      break;
    case Scenario::kCancelAir:
      h.drive_to_loiter();
      h.cancel_sticky = true;
      break;
    case Scenario::kCancelGround:
      h.run_until([&h] { return h.view().arm_sent; }, 400);
      h.cancel_sticky = true;
      break;
    case Scenario::kStampFailure:
      h.drive_to_takeoff();
      h.clock.fail = true;
      break;
  }
  h.run_until([&h] { return h.runner().done(); }, 600);
  h.tick();
}

TEST(TransitionObserver, RecorderDoesNotChangeOutputs)
{
  for (const Scenario scenario :
       {Scenario::kSuccess, Scenario::kCancelAir, Scenario::kCancelGround,
        Scenario::kStampFailure}) {
    SCOPED_TRACE(static_cast<int>(scenario));
    TransitionRecorder * const saved = active_transition_recorder();
    TransitionRecorder local;
    active_transition_recorder() = &local;
    Harness on(standard_mission());
    run_scenario(on, scenario);
    active_transition_recorder() = nullptr;
    Harness off(standard_mission());
    run_scenario(off, scenario);
    active_transition_recorder() = saved;
    EXPECT_TRUE(on.runner().done());
    EXPECT_FALSE(local.cells.empty());
    EXPECT_TRUE(local.untagged.empty());
    expect_same_outputs(on, off);
  }
}

class CoverageEnvironment : public ::testing::Environment
{
public:
  void SetUp() override { active_transition_recorder() = &recorder_; }

  void TearDown() override
  {
    active_transition_recorder() = nullptr;
    dump_observed();
    const ::testing::UnitTest & unit = *::testing::UnitTest::GetInstance();
    if (unit.test_to_run_count() != unit.total_test_count()) {
      std::cout << "[transition coverage] skipped: " << unit.test_to_run_count() << " of "
                << unit.total_test_count()
                << " tests selected (--gtest_filter or similar); the cell comparison needs all"
                << std::endl;
      return;
    }
    const CellList list = load_cells();
    if (!list.errors.empty()) {
      ADD_FAILURE() << "[transition coverage] cell list is malformed (see TransitionCells tests)";
      return;
    }
    // (4) untagged
    for (const std::string & u : recorder_.untagged) {
      ADD_FAILURE() << "[transition coverage] untagged state change: " << u;
    }
    // (2), (3), 관측했는데 uncovered로 적힌 칸
    for (const auto & [cell, test_name] : recorder_.cells) {
      const auto found = list.cells.find(cell);
      if (found == list.cells.end()) {
        ADD_FAILURE() << "[transition coverage] observed cell not in list (first seen in "
                      << test_name << "):\n" << cell_text(cell);
        continue;
      }
      if (found->second.cls == "impossible") {
        ADD_FAILURE() << "[transition coverage] impossible cell observed (line "
                      << found->second.line << ", first seen in " << test_name << "):\n"
                      << cell_text(cell);
      } else if (found->second.cls == "uncovered") {
        ADD_FAILURE() << "[transition coverage] cell listed as uncovered is observed (line "
                      << found->second.line << ", first seen in " << test_name
                      << "); change class to covered:\n" << cell_text(cell);
      }
    }
    // (1) covered 칸은 모두 관측되었다
    int covered = 0;
    int uncovered = 0;
    int impossible = 0;
    for (const auto & [cell, info] : list.cells) {
      if (info.cls == "covered") {
        ++covered;
        if (recorder_.cells.count(cell) == 0) {
          ADD_FAILURE() << "[transition coverage] covered cell not observed (line " << info.line
                        << "):\n" << cell_text(cell);
        }
      } else if (info.cls == "uncovered") {
        ++uncovered;
      } else {
        ++impossible;
      }
    }
    std::cout << "[transition coverage] cells: covered " << covered << ", impossible "
              << impossible << ", uncovered " << uncovered << "; observed "
              << recorder_.cells.size() << ", untagged " << recorder_.untagged.size()
              << std::endl;
  }

private:
  void dump_observed() const
  {
    const char * const path = std::getenv("IDSIM_TRANSITION_CELLS_DUMP");
    if (path == nullptr || *path == '\0') {
      return;
    }
    std::ofstream out(path);
    out << "from\tevent\tto\treason\tclass\talso_true\tnote\n";
    for (const auto & [cell, test_name] : recorder_.cells) {
      out << cell.from << '\t' << cell.event << '\t' << cell.to << '\t' << cell.reason
          << "\tcovered\t" << cell.also_true << '\t' << test_name << '\n';
    }
  }

  TransitionRecorder recorder_;
};

// gtest_main이 RUN_ALL_TESTS를 부르기 전에 등록된다. gtest가 소유하고 지운다.
::testing::Environment * const coverage_environment =
  ::testing::AddGlobalTestEnvironment(new CoverageEnvironment);

}  // namespace
}  // namespace idsim_mission::core::test
