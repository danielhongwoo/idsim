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

// 전이 기록기(decisions.md 쟁점 13). test_runner 실행 파일에서는 test_transition_coverage.cpp의
// Environment가 기록기를 켜고, Harness가 만드는 MissionRunner가 모두 여기에 기록한다. 다른 실행
// 파일에서는 꺼져 있어(nullptr) runner가 기록하지 않는다.

#ifndef TRANSITION_RECORDER_HPP_
#define TRANSITION_RECORDER_HPP_

#include <gtest/gtest.h>

#include <map>
#include <string>
#include <tuple>
#include <vector>

#include "idsim_mission/core/transition.hpp"

namespace idsim_mission::core::test
{

// 칸: (from, 사건, to, reason, 함께 참이던 사건). 문자열은 칸 목록 파일의 열과 같은 표기다.
struct Cell
{
  std::string from;
  std::string event;
  std::string to;
  std::string reason;
  std::string also_true;

  bool operator<(const Cell & other) const
  {
    return std::tie(from, event, to, reason, also_true) <
           std::tie(other.from, other.event, other.to, other.reason, other.also_true);
  }
  bool operator==(const Cell & other) const
  {
    return !(*this < other) && !(other < *this);
  }
};

inline std::string cell_text(const Cell & c)
{
  return c.from + "\t" + c.event + "\t" + c.to + "\t" + c.reason + "\t" + c.also_true;
}

inline std::string current_test_name()
{
  const ::testing::TestInfo * const info =
    ::testing::UnitTest::GetInstance()->current_test_info();
  if (info == nullptr) {
    return "<outside test>";
  }
  return std::string(info->test_suite_name()) + "." + info->name();
}

class TransitionRecorder : public TransitionObserver
{
public:
  void on_edge(const TransitionEdge & edge) override
  {
    if (!edge.tagged) {
      untagged.push_back(
        current_test_name() + " tick " + std::to_string(edge.tick) + ": " +
        state_key_name(edge.from) + " -> " + state_key_name(edge.to));
      return;
    }
    // 겹침 칸은 (이긴 사건, 함께 참이던 사건) 쌍이다. 함께 참이던 사건이 여럿이면 쌍마다 한 칸이다.
    Cell cell;
    cell.from = state_key_name(edge.from);
    cell.event = event_name(edge.event);
    cell.to = state_key_name(edge.to);
    cell.reason = edge_reason_name(edge);
    // 칸마다 처음 관측한 테스트를 남긴다(목록과 다를 때의 진단용).
    if (edge.also_true.empty()) {
      cell.also_true = "-";
      cells.emplace(cell, current_test_name());
      return;
    }
    for (const Event also : edge.also_true) {
      cell.also_true = event_name(also);
      cells.emplace(cell, current_test_name());
    }
  }

  std::map<Cell, std::string> cells;
  std::vector<std::string> untagged;
};

// 켜져 있으면 기록기, 아니면 nullptr.
inline TransitionRecorder *& active_transition_recorder()
{
  static TransitionRecorder * recorder = nullptr;
  return recorder;
}

}  // namespace idsim_mission::core::test

#endif  // TRANSITION_RECORDER_HPP_
