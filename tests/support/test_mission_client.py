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

"""mission_client 단위 테스트. DDS 효과(ACCEPTED 누락 87/400)는 단위로 재현되지 않으므로 구조만 고정한다.

고정하는 것: mission_event 구독이 action client보다 먼저, 같은 node 객체로 만들어진다. 이름과 메시지 변환.
효과는 decisions.md 쟁점 7의 0/400 실측과 시나리오의 EVENT_MISSING 분류가 받친다.
"""
from types import SimpleNamespace as NS

import pytest

from tests.support import mission_client as mc
from tests.support import sitl_wait as sw


class FakeNode:
    def count_publishers(self, topic):
        return 1


def make(calls):
    node = FakeNode()

    def subscribe(n, cls, topic, cb):
        calls.append(("subscription", n, topic))
        return NS(get_publisher_count=lambda: 2)

    def client(n, cls, name):
        calls.append(("client", n, name))
        return NS(server_is_ready=lambda: True)

    return node, mc.MissionClient(node, "px4_1", lambda: 123, event_cls=object, action_cls=object,
                                  subscribe=subscribe, make_client=client)


def test_subscription_is_created_before_client_on_the_same_node():
    calls = []
    node, c = make(calls)
    assert [k for k, _, _ in calls] == ["subscription", "client"]
    assert calls[0][1] is node and calls[1][1] is node
    assert calls[0][2] == "/px4_1/mission_event"
    assert calls[1][2] == "/px4_1/execute_mission"
    assert c.event_publisher_count() == 2
    assert c.server_ready()


def test_event_publisher_count_falls_back_to_graph_query():
    node = FakeNode()
    c = mc.MissionClient(node, "px4_1", lambda: 0, event_cls=object, action_cls=object,
                         subscribe=lambda n, cls, t, cb: object(),
                         make_client=lambda n, cls, name: NS(server_is_ready=lambda: False))
    assert c.event_publisher_count() == 1
    assert not c.server_ready()


def test_event_and_feedback_conversion():
    t = NS(sec=3, nanosec=500_000_000)
    ev = NS(stamp=t, vehicle_id="px4_1", mission_id="m", goal_id=list(range(16)), status=4, reason=0,
            item_count=3, items_completed=3, last_item_index=2, detail="")
    rec = mc.event_rec(ev, 99)
    assert rec.stamp_us == 3_500_000 and rec.recv_us == 99
    assert rec.goal_id == bytes(range(16)).hex()
    fb = NS(goal_id=NS(uuid=list(range(16))), feedback=NS(stamp=t, item_index=1, item_count=3, item_type=4, phase=2))
    f = mc.feedback_rec(fb, 5)
    assert f.goal_id == rec.goal_id and f.item_index == 1 and f.phase == 2
    r = mc.result_rec(NS(status=5, result=NS(reason=0, items_completed=1, last_item_index=1, detail="d")), 7)
    assert (r.status, r.items_completed, r.detail) == (5, 1, "d")


class Fut:
    def __init__(self, value=None, done=True):
        self._v = value
        self._d = done
        self._cbs = []

    def done(self):
        return self._d

    def result(self):
        return self._v

    def add_done_callback(self, cb):
        cb(self)


class StepWaiter:
    """pred가 참이 되는 즉시 돌려주는 가짜 Waiter."""

    def wait_until(self, pred, timeout_s, what):
        assert pred(), what


def test_send_goal_records_run_and_result(monkeypatch):
    uuid = list(range(16))
    handle = NS(accepted=True, goal_id=NS(uuid=uuid),
                get_result_async=lambda: Fut(NS(status=4, result=NS(
                    reason=0, items_completed=3, last_item_index=2, detail=""))))
    client = NS(server_is_ready=lambda: True,
                send_goal_async=lambda goal, feedback_callback: Fut(handle))
    c = mc.MissionClient(FakeNode(), "px4_1", lambda: 50, event_cls=object, action_cls=object,
                         subscribe=lambda *a: object(), make_client=lambda *a: client)
    monkeypatch.setattr(c, "build_goal", lambda vid, mid, items: object())
    run = c.send_goal(StepWaiter(), "px4_1", "m1", [{}, {}, {}])
    assert run.accepted and run.goal_id == bytes(uuid).hex() and run.item_count == 3
    assert c.wait_result(StepWaiter(), run, 5).status == 4


def test_rejected_goal_has_no_result_future(monkeypatch):
    handle = NS(accepted=False)
    client = NS(server_is_ready=lambda: True, send_goal_async=lambda goal, feedback_callback: Fut(handle))
    c = mc.MissionClient(FakeNode(), "px4_1", lambda: 0, event_cls=object, action_cls=object,
                         subscribe=lambda *a: object(), make_client=lambda *a: client)
    monkeypatch.setattr(c, "build_goal", lambda *a: object())
    run = c.send_goal(StepWaiter(), "px4_1", "m", [])
    assert run.accepted is False and run.goal_id is None


def test_require_server_maps_timeout_to_server_absent():
    class W:
        def wait_until(self, pred, t, what):
            raise sw.SitlFailure(sw.TIMEOUT_SIM, "x")

    with pytest.raises(sw.SitlFailure) as e:
        mc.require_server(W(), NS(server_ready=lambda: False), 5.0)
    assert e.value.category == sw.SERVER_ABSENT
