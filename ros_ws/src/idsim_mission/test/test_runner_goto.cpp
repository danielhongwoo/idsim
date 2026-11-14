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

// step()의 FramePort와 GOTO 항목(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 8, 12).
//
// - FramePort 호출 규율: 1a type 미션(TAKEOFF, LOITER, LAND, RTL)은 FramePort를 부르지 않는다
//   (decisions.md 쟁점 12). harness의 기본 port(kFail)가 모든 runner 사례에서 이를 함께 단정하고,
//   여기서는 진입 방식과 끝나는 길마다 한 번씩 끝까지 돌려 호출 수 0을 직접 단정한다.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "runner_harness.hpp"

namespace idsim_mission::core::test
{
namespace
{

void land_and_disarm(Harness & h)
{
  ASSERT_TRUE(h.run_until([&h] { return h.view().land_confirmed; }, 20));
  h.world.landed = true;
  h.world.arming = Arming::kDisarmed;
  ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
}

void expect_no_frame_calls(const Harness & h)
{
  EXPECT_TRUE(h.frame.point_calls.empty());
  EXPECT_EQ(h.frame.vector_calls, 0);
}

MissionSpec mission_of(const std::string & id, std::vector<ItemSpec> items)
{
  MissionSpec m;
  m.mission_id = id;
  m.items = std::move(items);
  return m;
}

// ---- FramePort 호출 규율(1a type 미션) ----

TEST(FramePortCalls, OneATypeMissionsNeverCallFramePort)
{
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND]");
    Harness h(standard_mission());
    h.drive_to_land();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LAND]");
    Harness h(land_only_mission());
    h.start_in_air();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER] (mission end)");
    Harness h(mission_of("tl", {takeoff_item(), loiter_item()}));
    h.drive_to_loiter();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 200));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[RTL]");
    Harness h(rtl_only_mission());
    h.start_in_air();
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, RTL]");
    Harness h(mission_of("tr", {takeoff_item(), rtl_item()}));
    h.drive_to_takeoff();
    h.world.landed = false;
    h.world.z = h.view().setpoint.z;
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 100));
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LOITER] (air offboard entry)");
    Harness h(air_loiter_mission());
    h.start_in_air();
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 400));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[LOITER, LAND] (air offboard entry)");
    Harness h(air_loiter_land_mission());
    h.start_in_air();
    ASSERT_TRUE(h.run_until([&h] { return h.view().item_index == 1U; }, 400));
    land_and_disarm(h);
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "SUCCEEDED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND] cancel in LOITER");
    Harness h(standard_mission());
    h.drive_to_loiter();
    h.cancel_sticky = true;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 100));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "CANCELED/NONE");
  }
  {
    SCOPED_TRACE("[TAKEOFF, LOITER, LAND] TAKEOFF ITEM_TIMEOUT");
    Harness h(standard_mission());
    h.drive_to_takeoff();
    h.world.landed = false;
    h.world.z = -1.0;
    ASSERT_TRUE(h.run_until([&h] { return h.runner().done(); }, 600));
    expect_no_frame_calls(h);
    expect_terminated_once_as(h, "ABORTED/ITEM_TIMEOUT");
  }
}

}  // namespace
}  // namespace idsim_mission::core::test
