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
"""send_mission._wait: 끝나지 않는 future를 POLL_S 간격으로 끊어 spin하고, Ctrl-C를 그대로 올린다.

가짜 rclpy(spin_until_future_complete만 있는 객체)와 가짜 future로 본다. DDS와 노드를 만들지 않는다.
"""

import pytest

from idsim_mission import send_mission


class FakeFuture:
    def __init__(self, done_after_calls):
        self.done_after_calls = done_after_calls  # None이면 끝나지 않는다
        self.calls = 0

    def done(self):
        return self.done_after_calls is not None and self.calls >= self.done_after_calls

    def result(self):
        return "result" if self.done() else None


class FakeRclpy:
    def __init__(self, interrupt_on_call=None):
        self.calls = []
        self.interrupt_on_call = interrupt_on_call

    def spin_until_future_complete(self, node, future, timeout_sec=None):
        self.calls.append((node, timeout_sec))
        future.calls += 1
        if self.interrupt_on_call is not None and len(self.calls) == self.interrupt_on_call:
            raise KeyboardInterrupt


def test_poll_interval_is_short():
    assert 0.0 < send_mission.POLL_S <= 0.5


def test_wait_spins_with_poll_timeout_until_done():
    rclpy = FakeRclpy()
    future = FakeFuture(done_after_calls=5)
    assert send_mission._wait(rclpy, "node", future) == "result"
    assert rclpy.calls == [("node", send_mission.POLL_S)] * 5


def test_wait_does_not_spin_when_already_done():
    rclpy = FakeRclpy()
    future = FakeFuture(done_after_calls=0)
    assert send_mission._wait(rclpy, "node", future) == "result"
    assert rclpy.calls == []


def test_keyboard_interrupt_in_spin_propagates():
    # 끝나지 않는 future에서도 세 번째 poll의 Ctrl-C가 _wait 밖으로 나온다.
    rclpy = FakeRclpy(interrupt_on_call=3)
    future = FakeFuture(done_after_calls=None)
    with pytest.raises(KeyboardInterrupt):
        send_mission._wait(rclpy, "node", future)
    assert rclpy.calls == [("node", send_mission.POLL_S)] * 3
