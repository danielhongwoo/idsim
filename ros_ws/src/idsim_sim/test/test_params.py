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
"""params 평탄화 형식의 해석과 거부 조건(decisions.md 쟁점 3)."""

import pytest

from idsim_sim.params import DEFAULT_PUBLISH_RATE_HZ, ConfigError, parse_params


def good():
    """생성기가 낼 형태. 표적 둘(loop true와 false)."""
    return {
        "use_sim_time": ("BOOL", True),
        "target_ids": ("STRING_ARRAY", ["car_1", "ring"]),
        "targets.car_1.start_s": ("DOUBLE", 0.0),
        "targets.car_1.loop": ("BOOL", False),
        "targets.car_1.t": ("DOUBLE_ARRAY", [0.0, 10.0]),
        "targets.car_1.x": ("DOUBLE_ARRAY", [1.0, 5.0]),
        "targets.car_1.y": ("DOUBLE_ARRAY", [2.0, 2.0]),
        "targets.car_1.z": ("DOUBLE_ARRAY", [0.0, 0.0]),
        "targets.ring.start_s": ("DOUBLE", 5.0),
        "targets.ring.loop": ("BOOL", True),
        "targets.ring.t": ("DOUBLE_ARRAY", [0.0, 2.0, 4.0]),
        "targets.ring.x": ("DOUBLE_ARRAY", [0.0, 1.0, 0.0]),
        "targets.ring.y": ("DOUBLE_ARRAY", [0.0, 0.0, 0.0]),
        "targets.ring.z": ("DOUBLE_ARRAY", [1.0, 1.0, 1.0]),
        # rclpy가 늘 선언하는 것. 해석은 targets. 밖의 모르는 이름을 무시한다
        "start_type_description_service": ("BOOL", True),
    }


def test_good_params():
    cfg = parse_params(good())
    assert [t.target_id for t in cfg.trajectories] == ["car_1", "ring"]
    assert cfg.publish_rate_hz == DEFAULT_PUBLISH_RATE_HZ == 20.0
    ring = cfg.trajectories[1]
    assert ring.loop and ring.start_ns == 5_000_000_000
    assert ring.times_ns == (0, 2_000_000_000, 4_000_000_000)
    assert ring.points[1] == (1.0, 0.0, 1.0)


def test_publish_rate_override():
    p = good()
    p["publish_rate_hz"] = ("DOUBLE", 50.0)
    assert parse_params(p).publish_rate_hz == 50.0


def _with(**changes):
    p = good()
    for key, value in changes.items():
        name = key.replace("__", ".")
        if value is None:
            p.pop(name)
        else:
            p[name] = value
    return p


BAD = {
    "use_sim_time_false": _with(use_sim_time=("BOOL", False)),
    "target_ids_missing": _with(target_ids=None),
    "target_ids_empty": _with(target_ids=("STRING_ARRAY", [])),
    "id_format": _with(target_ids=("STRING_ARRAY", ["car_1", "Ring"])),
    "id_duplicate": _with(target_ids=("STRING_ARRAY", ["car_1", "car_1"])),
    "field_missing": _with(targets__car_1__z=None),
    "start_missing": _with(targets__ring__start_s=None),
    "length_mismatch": _with(targets__car_1__x=("DOUBLE_ARRAY", [1.0, 5.0, 6.0])),
    "one_waypoint": _with(targets__car_1__t=("DOUBLE_ARRAY", [0.0]), targets__car_1__x=("DOUBLE_ARRAY", [1.0]),
                          targets__car_1__y=("DOUBLE_ARRAY", [2.0]), targets__car_1__z=("DOUBLE_ARRAY", [0.0])),
    "integer_array": _with(targets__car_1__t=("INTEGER_ARRAY", [0, 10])),
    "integer_start": _with(targets__car_1__start_s=("INTEGER", 0)),
    "loop_not_bool": _with(targets__car_1__loop=("STRING", "false")),
    "t_not_zero": _with(targets__car_1__t=("DOUBLE_ARRAY", [1.0, 10.0])),
    "t_not_increasing": _with(targets__car_1__t=("DOUBLE_ARRAY", [0.0, 0.0])),
    "t_nan": _with(targets__car_1__t=("DOUBLE_ARRAY", [0.0, float("nan")])),
    "loop_open": _with(targets__ring__x=("DOUBLE_ARRAY", [0.0, 1.0, 0.5])),
    "unknown_target": _with(targets__other__t=("DOUBLE_ARRAY", [0.0, 1.0])),
    "unknown_field": _with(targets__car_1__speed=("DOUBLE", 1.0)),
    "rate_zero": _with(publish_rate_hz=("DOUBLE", 0.0)),
    "rate_integer": _with(publish_rate_hz=("INTEGER", 20)),
}


@pytest.mark.parametrize("params", list(BAD.values()), ids=list(BAD))
def test_rejects(params):
    with pytest.raises(ConfigError):
        parse_params(params)
