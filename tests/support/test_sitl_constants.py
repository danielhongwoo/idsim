# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""sitl_judge의 MissionEvent, ExecuteMission, MissionItem 상수가 생성 코드(.msg, .action)의 상수와 같은지 고정한다.

idsim_interfaces가 import되는 환경(ros-ws 이미지의 runner)에서만 돈다. lint job의 pytest에서는 건너뛴다.
"""
import pytest

from tests.support import sitl_judge as sj

msgs = pytest.importorskip("idsim_interfaces.msg")
actions = pytest.importorskip("idsim_interfaces.action")


def test_event_status_constants():
    ev = msgs.MissionEvent
    assert (sj.STATUS_ACCEPTED, sj.STATUS_SUCCEEDED, sj.STATUS_CANCELED, sj.STATUS_ABORTED) == (
        ev.STATUS_ACCEPTED, ev.STATUS_SUCCEEDED, ev.STATUS_CANCELED, ev.STATUS_ABORTED)


def test_reason_constants():
    r = actions.ExecuteMission.Result
    assert sj.REASON_NONE == r.REASON_NONE
    assert sj.REASON_INVALID_MISSION == r.REASON_INVALID_MISSION
    assert sj.REASON_VEHICLE_ID_MISMATCH == r.REASON_VEHICLE_ID_MISMATCH
    assert sj.REASON_TARGET_LOST == r.REASON_TARGET_LOST


def test_phase_and_item_type_constants():
    fb = actions.ExecuteMission.Feedback
    assert (sj.PHASE_PREPARING, sj.PHASE_EXECUTING) == (fb.PHASE_PREPARING, fb.PHASE_EXECUTING)
    it = msgs.MissionItem
    assert (sj.TYPE_TAKEOFF, sj.TYPE_GOTO, sj.TYPE_TRACK_ENTITY, sj.TYPE_LOITER, sj.TYPE_RTL, sj.TYPE_LAND) == (
        it.TYPE_TAKEOFF, it.TYPE_GOTO, it.TYPE_TRACK_ENTITY, it.TYPE_LOITER, it.TYPE_RTL, it.TYPE_LAND)


def test_names_come_from_generated_constants():
    assert msgs.MissionEvent.TOPIC_NAME == "mission_event"
    assert msgs.Mission.ACTION_NAME == "execute_mission"


def test_px4_nav_state_constants():
    """sitl_judge와 measure_judge의 nav_state 값이 px4_msgs VehicleStatus 상수와 같다(비행 시나리오의 AUTO_RTL 포함)."""
    px4 = pytest.importorskip("px4_msgs.msg")
    from tests.support import measure_judge as mj
    vs = px4.VehicleStatus
    assert sj.NAV_STATE_AUTO_RTL == vs.NAVIGATION_STATE_AUTO_RTL
    assert (mj.NAV_STATE_AUTO_LOITER, mj.NAV_STATE_OFFBOARD, mj.NAV_STATE_AUTO_LAND) == (
        vs.NAVIGATION_STATE_AUTO_LOITER, vs.NAVIGATION_STATE_OFFBOARD, vs.NAVIGATION_STATE_AUTO_LAND)


def test_target_state_names():
    """TargetState 토픽 이름 조립(sim_truth)이 쓰는 상수."""
    ts = msgs.TargetState
    assert (ts.TOPIC_PREFIX, ts.TOPIC_SUFFIX, ts.FRAME_ID) == ("/targets", "state", "world")
