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

"""measure.py의 인자 검증 단위 테스트. rclpy와 px4_msgs는 가짜 모듈로 대신해 호스트에서 import한다."""
import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

from tests.support import measure_bands as mb

MEASURE = Path(__file__).resolve().parents[1] / "sitl" / "measure" / "measure.py"


@pytest.fixture(scope="module")
def measure():
    fakes = {name: mock.MagicMock() for name in (
        "rclpy", "rclpy.qos", "rclpy.node", "rclpy.executors", "rclpy.parameter",
        "px4_msgs", "px4_msgs.msg", "rosgraph_msgs", "rosgraph_msgs.msg", "builtin_interfaces",
        "builtin_interfaces.msg")}
    with mock.patch.dict(sys.modules, fakes):
        spec = importlib.util.spec_from_file_location("measure_under_test", MEASURE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod


def test_item3_default_is_nine_delays_times_three(measure):
    a = measure.parse_args(["--item", "item3"])
    assert a.item3_delays == list(mb.ITEM3_DELAYS_S)
    assert a.attempts == 27 == measure.DEFAULT_ATTEMPTS["item3"]


def test_item3_attempts_must_be_a_multiple_of_the_delay_count(measure):
    assert measure.parse_args(["--item", "item3", "--attempts", "18"]).attempts == 18
    with pytest.raises(SystemExit):
        measure.parse_args(["--item", "item3", "--attempts", "20"])
    assert measure.parse_args(["--item", "item3", "--item3-delays", "0,0.5", "--attempts", "4"]).attempts == 4


def test_item3_delays_only_from_the_fixed_list_and_item5_range_is_unchanged(measure):
    for bad in ("0.05", "0,3.0", "x"):
        with pytest.raises(SystemExit):
            measure.parse_args(["--item", "item3", "--item3-delays", bad])
    # (5)의 --delays는 0-0.2 범위 검증 그대로
    assert measure.parse_args(["--item", "item5", "--delays", "0,0.2"]).delays == [0.0, 0.2]
    with pytest.raises(SystemExit):
        measure.parse_args(["--item", "item5", "--delays", "0.5"])
    assert measure.DELAY_RANGE_S == (0.0, 0.2)


def test_item3_injection_records_nominal_delay_round_robin(measure):
    a = measure.parse_args(["--item", "item3"])
    got = [measure.nominal_injection("item3", i, a)["delay_s_nominal"] for i in range(18)]
    assert got == list(mb.ITEM3_DELAYS_S) * 2


def test_item3_criteria_text_names_every_delay_and_band(measure):
    text = "\n".join(measure.CRITERIA["item3"])
    for d in mb.ITEM3_DELAYS_S:
        assert str(d) in text
    for needle in ("spoolup", "M5_CONTRADICTED", "HOLD_END", "M3_CONTRADICTED"):
        assert needle in text
