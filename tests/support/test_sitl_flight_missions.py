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

"""1b 비행 시나리오(F1-F4)의 시험 미션 YAML과 판정 상수의 대조(1b decisions.md 쟁점 5, 15).

미션은 로더(idsim_mission/mission_yaml.py)가 만든 MissionSpec(기본값이 채워진 뒤)으로 본다. 로더는 저장소 소스
경로에서 읽으므로 lint job의 pytest에서 돈다(sitl_missions 모듈 설명).
"""
import math

import pytest
import yaml

from tests.support import sitl_judge as sj
from tests.support import sitl_missions as sm
from tests.support import sitl_summary as ss

TYPE = {"TAKEOFF": sj.TYPE_TAKEOFF, "GOTO": sj.TYPE_GOTO, "TRACK_ENTITY": sj.TYPE_TRACK_ENTITY,
        "LOITER": sj.TYPE_LOITER, "RTL": sj.TYPE_RTL, "LAND": sj.TYPE_LAND}
FLIGHTS = [sid for sid in ss.SCENARIOS if sid in sm.FLIGHT_MISSIONS]


def _fleet():
    return yaml.safe_load(sm.SITL_FLEET.read_text(encoding="utf-8"))


def _types(spec):
    return [it.type for it in spec.items]


def test_flight_missions_cover_the_flight_scenarios_in_order():
    assert FLIGHTS == ["F1", "F2", "F3", "F4"]
    assert set(sm.FLIGHT_MISSIONS) == set(ss.ORACLE_SCENARIOS) == set(sm.FLIGHT_TERMINAL)


def test_loader_types_match_judge_constants():
    assert sm.mission_yaml().ITEM_TYPES == TYPE


@pytest.mark.parametrize("sid", FLIGHTS)
def test_time_rule(sid):
    """항목 timeout 합 + 마진이 비행당 상한(ROS 시각 3분)을 넘지 않는다(쟁점 15)."""
    spec = sm.load_flight(sid)
    assert sm.flight_wait_s(spec) <= sm.FLIGHT_LIMIT_S, (sid, sm.timeout_sum_s(spec))
    assert all(sm.duration_s(it.timeout) > 0 for it in spec.items)


def _farthest_aim_m(start, target, offset):
    """start에서 loop 궤적(꼭짓점 사이 직선) 위 setpoint 점(표적 + offset)까지의 최대 거리. 점에서 선분까지의
    거리는 선분 위에서 볼록이라 최댓값은 꼭짓점에 있다."""
    return max(math.dist(start, (w["x"] + offset[0], w["y"] + offset[1], w["z"] + offset[2]))
               for w in target["waypoints"])


@pytest.mark.parametrize("sid", FLIGHTS)
def test_track_timeout_covers_farthest_point(sid):
    """TRACK_ENTITY timeout >= 항목 시작점(직전 GOTO 목표)에서 loop 위 가장 먼 점을 따라잡는 시간 + 완료 마진."""
    spec = sm.load_flight(sid)
    targets = {t["id"]: t for t in _fleet()["targets"]}
    for i, it in enumerate(spec.items):
        if it.type != sj.TYPE_TRACK_ENTITY:
            continue
        prev = spec.items[i - 1]
        assert prev.type == sj.TYPE_GOTO, "TRACK_ENTITY 앞은 GOTO여야 시작점이 정해진다"
        t = targets[it.target_id]
        assert t["loop"] is True
        need = _farthest_aim_m(prev.position, t, it.offset) / sm.APPROACH_SPEED_MPS + sm.TRACK_COMPLETION_MARGIN_S
        assert sm.duration_s(it.timeout) >= need, (sid, i, need)


def test_target_speed_is_one_to_two_mps():
    """F2와 F4의 표적 속도는 1-2 m/s다(쟁점 15). 판정의 v는 stack.json targets에서 같은 함수로 낸다."""
    targets = _fleet()["targets"]
    used = {it.target_id for sid in FLIGHTS for it in sm.load_flight(sid).items if it.type == sj.TYPE_TRACK_ENTITY}
    assert used and used <= {t["id"] for t in targets}
    for t in targets:
        wps = t["waypoints"]
        speeds = [math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) / (b["t"] - a["t"])
                  for a, b in zip(wps, wps[1:])]
        assert 1.0 - 1e-9 <= min(speeds) and max(speeds) <= 2.0 + 1e-9, (t["id"], speeds)
    assert sj.target_speed_max(targets) == pytest.approx(2.0)


def test_event_counts_match_judge_constants():
    """m(GOTO와 TRACK_ENTITY 완료 사건 수)과 m_home(RTL 사건 수)은 시나리오에서 파생된 값이다(쟁점 5)."""
    specs = [sm.load_flight(sid) for sid in FLIGHTS]
    m = sum(1 for s in specs for t in _types(s) if t in (sj.TYPE_GOTO, sj.TYPE_TRACK_ENTITY))
    m_home = sum(1 for s in specs for t in _types(s) if t == sj.TYPE_RTL)
    assert (m, m_home) == (sj.M_EVENTS, sj.M_HOME)
    goto = sum(1 for s in specs for t in _types(s) if t == sj.TYPE_GOTO)
    track = sum(1 for s in specs for t in _types(s) if t == sj.TYPE_TRACK_ENTITY)
    assert (goto, track) == (7, 2)       # 부팅당 GOTO 7개, s_track 2개(쟁점 5)


@pytest.mark.parametrize("sid", FLIGHTS)
def test_acceptance_radius_matches_judge_constants(sid):
    """시험 미션의 acceptance_radius_m은 0.5 m 이상이고 R_JUDGE - b 이하다(반경의 숫자는 미션 YAML에만 적는다)."""
    assert sj.B_M is not None
    for it in sm.load_flight(sid).items:
        if it.type not in (sj.TYPE_GOTO, sj.TYPE_TRACK_ENTITY):
            continue
        assert sj.ACCEPTANCE_MIN_M - 1e-9 <= it.acceptance_radius_m <= sj.R_JUDGE_M - sj.B_M + 1e-9


def test_flight_scenarios_need_constants():
    """시나리오 목록(로컬과 CI가 같다)에 F1-F4가 있으면 b와 R_home이 정해져 있다(보정 상태는 머지되지 않는다)."""
    if set(ss.SCENARIOS) & set(ss.ORACLE_SCENARIOS):
        assert sj.B_M is not None and sj.R_HOME_M is not None
    if sj.B_M is not None:
        assert 0 < sj.B_M <= sj.B_MAX_M and round(sj.B_M / 0.05, 9) == round(sj.B_M / 0.05)
    if sj.R_HOME_M is not None:
        assert 0 < sj.R_HOME_M <= sj.R_HOME_MAX_M


def test_l_matches_fresh_age_formula():
    """L = target_fresh_age + Executor tick + 여유(쟁점 5). 노드의 실제 target_fresh_age는 gate가 대조한다."""
    assert sj.L_S == pytest.approx(sj.TARGET_FRESH_AGE_S + sj.EXECUTOR_TICK_S + sj.L_MARGIN_S)
    assert (sj.TARGET_FRESH_AGE_S, sj.EXECUTOR_TICK_S, sj.L_MARGIN_S) == (0.1, 0.05, 0.05)


@pytest.mark.parametrize("sid", FLIGHTS)
def test_start_and_terminal_shape(sid):
    """지상 시작 비행은 TAKEOFF로 시작하고 공중 시작(F3)은 아니다. 끝 상태가 지상이면 LAND나 RTL로 끝나고,
    공중 Hold이면 setpoint 항목으로 끝난다."""
    types = _types(sm.load_flight(sid))
    assert (types[0] == sj.TYPE_TAKEOFF) == (sid not in sm.AIR_START)
    if sm.FLIGHT_TERMINAL[sid] == sj.TERMINAL_LANDED_DISARMED:
        assert types[-1] in (sj.TYPE_LAND, sj.TYPE_RTL)
    else:
        assert types[-1] in (sj.TYPE_GOTO, sj.TYPE_TRACK_ENTITY)
    for sid2, prev in sm.AIR_START.items():
        assert sm.FLIGHT_TERMINAL[prev] == sj.TERMINAL_HOLD_AIRBORNE
        assert ss.SCENARIOS.index(prev) + 1 == ss.SCENARIOS.index(sid2)


def test_mission_ids_unique_and_valid():
    import re
    ids = [sm.load_flight(sid).mission_id for sid in FLIGHTS]
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", i) for i in ids)


def test_executor_tick_matches_node_source():
    """EXECUTOR_TICK_S가 노드의 tick 주기(mission_executor_node.hpp의 kTickPeriodNs 원문)와 같다(L의 식에 들어간다)."""
    import re
    hpp = (sm.REPO / "ros_ws" / "src" / "idsim_mission" / "include" / "idsim_mission" / "node"
           / "mission_executor_node.hpp").read_text(encoding="utf-8")
    m = re.findall(r"kTickPeriodNs\s*=\s*(\d+)LL", hpp)
    assert len(m) == 1, "kTickPeriodNs 정의를 하나 찾아야 한다"
    assert int(m[0]) == round(sj.EXECUTOR_TICK_S * 1e9)
