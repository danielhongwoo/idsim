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

"""sitl_wait 단위 테스트. 가짜 sim 시계와 가짜 벽시계로 분류를 고정한다(rclpy 없음)."""
import pytest

from tests.support import sitl_wait as sw


class FakeWorld:
    """sleep 한 번에 벽시계가 poll만큼 가고, sim 시각은 rate만큼의 비율로 간다(rate 0이면 멈춤)."""

    def __init__(self, rate=1.0, start=100.0, poll=0.02):
        self.rate = rate
        self.sim = start
        self.wall_t = 1000.0
        self.poll = poll
        self.sim_hook = None

    def sim_s(self):
        return self.sim

    def wall(self):
        return self.wall_t

    def sleep(self, dt):
        self.wall_t += dt
        self.sim += dt * self.rate
        if self.sim_hook:
            self.sim_hook(self)

    def waiter(self):
        return sw.Waiter(self.sim_s, self.wall, self.sleep, self.poll)


def test_wall_cap_formula():
    assert sw.wall_cap_s(20) == 70.0
    assert sw.wall_cap_s(5) == 25.0


def test_wait_until_returns_when_condition_true():
    w = FakeWorld()
    n = {"v": 0}

    def pred():
        n["v"] += 1
        return n["v"] > 10

    elapsed = w.waiter().wait_until(pred, 5.0, "x")
    assert 0.1 < elapsed < 0.5


def test_timeout_sim():
    w = FakeWorld(rate=1.0)
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 2.0, "x")
    assert e.value.category == sw.TIMEOUT_SIM


def test_clock_absent_is_immediate():
    for v in (None, 0.0, -1.0):
        wd = sw.Waiter(lambda v=v: v, lambda: 0.0, lambda dt: None)
        with pytest.raises(sw.SitlFailure) as e:
            wd.wait_until(lambda: True, 5.0, "x")
        assert e.value.category == sw.CLOCK_ABSENT


def test_clock_backward_is_immediate():
    w = FakeWorld()

    def hook(world):
        if world.sim > 100.2:
            world.sim = 99.0

    w.sim_hook = hook
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 5.0, "x")
    assert e.value.category == sw.CLOCK_BACKWARD


def test_clock_stalled_classified_at_wall_cap():
    w = FakeWorld(rate=0.0)
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 5.0, "x")
    assert e.value.category == sw.CLOCK_STALLED
    assert w.wall_t - 1000.0 > sw.wall_cap_s(5.0)   # 상한 전에는 끊지 않는다


def test_clock_slow_when_clock_moves_but_slowly():
    # RTF 0.1: 5 s 대기의 상한 25 s 안에 sim 2.5 s만 간다 -> TIMEOUT_SIM보다 wall_cap이 먼저
    w = FakeWorld(rate=0.1)
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 5.0, "x")
    assert e.value.category == sw.CLOCK_SLOW
    assert "RTF" in e.value.message


def test_rtf_just_above_threshold_is_timeout_not_slow():
    # RTF 0.5: 5 s의 sim 대기에 벽시계 10 s -> 상한 25 s 안이라 TIMEOUT_SIM(판정 실패)이다
    w = FakeWorld(rate=0.5)
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 5.0, "x")
    assert e.value.category == sw.TIMEOUT_SIM


def test_stall_then_progress_is_slow_not_stalled():
    # 멈췄다가(4 s) 다시 가는 경우: 마지막 진행이 5 s 안이면 STALLED가 아니다
    w = FakeWorld(rate=0.0)
    w.wall_t = 1000.0

    def hook(world):
        elapsed = world.wall_t - 1000.0
        if elapsed > 24.0:
            world.rate = 0.1

    w.sim_hook = hook
    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().wait_until(lambda: False, 5.0, "x")
    assert e.value.category == sw.CLOCK_SLOW


def test_hold_for_runs_check_and_returns():
    w = FakeWorld()
    calls = []
    w.waiter().hold_for(1.0, "hold", check=lambda: calls.append(1))
    assert len(calls) > 10


def test_hold_for_propagates_check_failure():
    w = FakeWorld()

    def check():
        raise sw.SitlFailure(sw.WRONG_RESULT, "x")

    with pytest.raises(sw.SitlFailure) as e:
        w.waiter().hold_for(1.0, "hold", check=check)
    assert e.value.category == sw.WRONG_RESULT


def test_wait_or_timeout_returns_false():
    w = FakeWorld()
    assert w.waiter().wait_or_timeout(lambda: False, 0.5, "x") is False
    assert w.waiter().wait_or_timeout(lambda: True, 0.5, "x") is True


def test_rtf_history():
    w = FakeWorld(rate=0.5)
    wd = w.waiter()
    wd.hold_for(1.0, "a")
    sim, wall, rtf = wd.rtf()
    assert sim == pytest.approx(1.0, abs=0.05)
    assert rtf == pytest.approx(0.5, abs=0.05)


def test_raise_if():
    sw.raise_if([])
    with pytest.raises(sw.SitlFailure) as e:
        sw.raise_if([(sw.EVENT_MISSING, "a"), (sw.WRONG_RESULT, "b")])
    assert e.value.category == sw.EVENT_MISSING and "a; b" in e.value.message
