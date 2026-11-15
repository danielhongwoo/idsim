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

"""ulog_1b(1b ULog 기록 요약) 단위 테스트."""
import math

from tests.support import ulog_1b as u

NAN = math.nan


def _topics():
    tsp = [{"timestamp": t, "velocity": [2.0, 0.0, NAN] if t >= 1_000_000 else [NAN, NAN, NAN],
            "position": [0.0, 0.0, -5.0]} for t in range(0, 3_000_000, 100_000)]
    vlps = [{"timestamp": t, "vx": 2.0, "vy": 0.0, "z": -5.0} for t in range(0, 3_000_000, 100_000)]
    vlp = [{"timestamp": t, "z": -5.1} for t in range(0, 3_000_000, 100_000)]
    cmds = [{"timestamp": 10_000_000, "command": 176, "source_system": 254, "source_component": 191},
            {"timestamp": 10_500_000, "command": 176, "source_system": 254, "source_component": 191},
            {"timestamp": 10_600_000, "command": 400, "source_system": 254, "source_component": 191}]
    st = [{"timestamp": 9_900_000, "nav_state": 4}, {"timestamp": 10_200_000, "nav_state": 4},
          {"timestamp": 10_400_000, "nav_state": 14}, {"timestamp": 10_900_000, "nav_state": 4},
          {"timestamp": 11_400_000, "nav_state": 14}]
    return {"trajectory_setpoint": tsp, "vehicle_local_position_setpoint": vlps, "vehicle_local_position": vlp,
            "vehicle_command": cmds, "vehicle_status": st}


def test_track_window_counts_feedforward():
    r = u.track_window(_topics(), 1_000_000, 2_000_000)
    assert r["trajectory_setpoint"]["n"] == 11 and r["trajectory_setpoint"]["velocity_finite"] == 11
    assert r["vehicle_local_position_setpoint"]["speed_xy"]["mean"] == 2.0
    assert r["setpoint_z"]["mean"] == -5.0 and r["local_z"]["mean"] == -5.1
    r = u.track_window(_topics(), 0, 500_000)
    assert r["trajectory_setpoint"]["velocity_finite"] == 0


def test_air_start_window():
    r = u.air_start_window(_topics(), 9_800_000, 12_000_000)
    assert r["do_set_mode"]["count"] == 2 and r["do_set_mode"]["source"] == [(254, 191)]
    assert r["first_offboard_ts"] == 10_400_000 and r["D_s"] == 0.4
    assert r["nav_between"] == [4] and r["non_offboard_after_first"] == [(10_900_000, 4)]
    assert r["status_interval_s"]["n"] == 4


def test_build_uses_trace_windows():
    events = [{"kind": "flight_window", "scenario": "F2", "types": ["TAKEOFF", "GOTO", "TRACK_ENTITY"],
               "item_start_us": {"2": 1_000_000}, "t_f": {"2": [2_000_000, False, 1_500_000]}, "result_recv_us": 3},
              {"kind": "air_start", "scenario": "F3", "goal_sent_us": 9_800_000, "executing_us": 12_000_000}]
    r = u.build(events, _topics())
    assert [t["window_us"] for t in r["track"]] == [[1_000_000, 2_000_000]]
    assert r["air_start"][0]["do_set_mode"]["count"] == 2
