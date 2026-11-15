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

"""1b 비행 시나리오의 ULog 기록(기록 전용. 판정에 쓰지 않는다). 순수 코드다(표준 라이브러리만).

trace.jsonl의 구간(flight_window, air_start 사건. ROS 시각 us)으로 ULog 표본을 잘라 요약한다. SITL lockstep에서
PX4 hrt는 노드 ROS 시각보다 8-20 ms 크다(docs/interface.md "시간 기준")라 구간 경계는 그만큼 흐리다.
  - TRACK_ENTITY 구간: trajectory_setpoint의 velocity(Executor가 실은 속도 feedforward)와
    vehicle_local_position_setpoint의 vx, vy(PX4 속도 setpoint로 전달되었는가. progress의 B11 trace 항목),
    setpoint z와 vehicle_local_position z(R5의 수직).
  - 공중 시작 구간(F3): DO_SET_MODE 전송 수와 시각, 첫 DO_SET_MODE에서 첫 OFFBOARD 표본까지(D), 그 사이 표본의
    nav_state, 첫 OFFBOARD 표본 뒤 OFFBOARD가 아닌 표본, vehicle_status 표본 간격(쟁점 7의 "공중 시작" 항목).
"""
import math

US = 1_000_000
VEHICLE_CMD_DO_SET_MODE = 176
NAV_STATE_OFFBOARD = 14
TOPICS = {"trajectory_setpoint": 0, "vehicle_local_position_setpoint": 0, "vehicle_local_position": 0,
          "vehicle_command": 0, "vehicle_status": 0}


def _summary(values):
    v = sorted(values)
    if not v:
        return {"n": 0, "mean": None, "max": None, "min": None}
    return {"n": len(v), "mean": round(sum(v) / len(v), 4), "max": round(v[-1], 4), "min": round(v[0], 4)}


def _within(rows, lo, hi):
    return [r for r in rows if lo <= int(r["timestamp"]) <= hi]


def _finite(*vals):
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


def track_window(topics, lo, hi):
    """TRACK_ENTITY 구간 [lo, hi](us)의 속도 feedforward와 z 요약."""
    tsp = _within(topics.get("trajectory_setpoint", []), lo, hi)
    vlps = _within(topics.get("vehicle_local_position_setpoint", []), lo, hi)
    vlp = _within(topics.get("vehicle_local_position", []), lo, hi)
    ff = [r["velocity"] for r in tsp if _finite(r["velocity"][0], r["velocity"][1])]
    sp = [(r["vx"], r["vy"]) for r in vlps if _finite(r["vx"], r["vy"])]
    zs = [r["position"][2] for r in tsp if _finite(r["position"][2])]
    lz = [r["z"] for r in vlp if _finite(r["z"])]
    return {
        "trajectory_setpoint": {"n": len(tsp), "velocity_finite": len(ff),
                                "speed_xy": _summary([math.hypot(v[0], v[1]) for v in ff])},
        "vehicle_local_position_setpoint": {"n": len(vlps), "vxvy_finite": len(sp),
                                            "speed_xy": _summary([math.hypot(a, b) for a, b in sp])},
        "setpoint_z": _summary(zs), "local_z": _summary(lz),
    }


def air_start_window(topics, lo, hi):
    """공중 시작 구간 [lo, hi](us)의 DO_SET_MODE와 vehicle_status 요약."""
    cmds = [r for r in _within(topics.get("vehicle_command", []), lo, hi)
            if int(r["command"]) == VEHICLE_CMD_DO_SET_MODE]
    st = sorted(_within(topics.get("vehicle_status", []), lo, hi), key=lambda r: int(r["timestamp"]))
    first_cmd = int(cmds[0]["timestamp"]) if cmds else None
    first_off = next((r for r in st if first_cmd is not None and int(r["timestamp"]) >= first_cmd
                      and int(r["nav_state"]) == NAV_STATE_OFFBOARD), None)
    between = [int(r["nav_state"]) for r in st if first_cmd is not None and first_off is not None
               and first_cmd <= int(r["timestamp"]) < int(first_off["timestamp"])]
    after = [(int(r["timestamp"]), int(r["nav_state"])) for r in st if first_off is not None
             and int(r["timestamp"]) > int(first_off["timestamp"]) and int(r["nav_state"]) != NAV_STATE_OFFBOARD]
    ts = [int(r["timestamp"]) for r in st]
    return {
        "do_set_mode": {"count": len(cmds), "ts_us": [int(r["timestamp"]) for r in cmds],
                        "source": sorted({(int(r["source_system"]), int(r["source_component"])) for r in cmds})},
        "first_offboard_ts": None if first_off is None else int(first_off["timestamp"]),
        "D_s": None if first_off is None else round((int(first_off["timestamp"]) - first_cmd) / US, 4),
        "nav_between": between, "non_offboard_after_first": after,
        "status_interval_s": _summary([(b - a) / US for a, b in zip(ts, ts[1:])]),
    }


def build(trace_events, topics):
    """trace.jsonl 사건 목록과 ULog 표본으로 trace_1b.json 본문을 만든다."""
    out = {"track": [], "air_start": []}
    for ev in trace_events:
        if ev.get("kind") == "flight_window":
            starts = {int(k): v for k, v in (ev.get("item_start_us") or {}).items()}
            tf = {int(k): v for k, v in (ev.get("t_f") or {}).items()}
            for i, typ in enumerate(ev.get("types", [])):
                if typ == "TRACK_ENTITY" and i in starts:
                    hi = tf[i][0] if i in tf else ev.get("result_recv_us") or starts[i]
                    out["track"].append({"scenario": ev["scenario"], "index": i, "window_us": [starts[i], hi],
                                         **track_window(topics, starts[i], hi)})
        elif ev.get("kind") == "air_start":
            lo, hi = ev["goal_sent_us"], ev.get("executing_us") or ev["goal_sent_us"]
            out["air_start"].append({"scenario": ev["scenario"], "window_us": [lo, hi],
                                     **air_start_window(topics, lo, hi)})
    return out
