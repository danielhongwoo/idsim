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

"""ExecuteMission action client와 mission_event 구독(통합 테스트용). rclpy는 필요할 때만 가져온다.

순서 규칙(필수. decisions.md 쟁점 7, [실측] P3a): mission_event 구독을 action client보다 먼저, 같은 node 객체
(같은 participant)에서 만든다. 순서를 어기면 ACCEPTED 사건이 빠진다(대조군 87/400. 새 프로세스 71/200,
새 노드 16/200). 구독 쪽 get_publisher_count() >= 1 gate는 사건 수신을 보장하지 않는다([실측] 누락 87건이 모두
이 조건을 만족했다). 수신을 받치는 것은 이 순서 규칙이다. 구조(순서와 같은 node)는 test_mission_client.py가
mock으로 고정한다. goal 응답이 accepted인데 ACCEPTED 사건이 없으면 EVENT_MISSING이며 재시도하지 않는다.
"""
from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw

EVENT_DEPTH = 200
ACTION_NAME = "execute_mission"   # ExecuteMission.ACTION_NAME. 네임스페이스는 /<vehicle_id>
EVENT_TOPIC = "mission_event"     # MissionEvent.TOPIC_NAME


def stamp_us(t):
    return int(t.sec) * 1_000_000 + int(t.nanosec) // 1000


def goal_hex(uuid_array):
    return bytes(bytearray(int(x) for x in uuid_array)).hex()


def event_rec(msg, recv_us):
    return sj.EventRec(
        recv_us=recv_us, stamp_us=stamp_us(msg.stamp), vehicle_id=msg.vehicle_id, mission_id=msg.mission_id,
        goal_id=goal_hex(msg.goal_id), status=int(msg.status), reason=int(msg.reason),
        item_count=int(msg.item_count), items_completed=int(msg.items_completed),
        last_item_index=int(msg.last_item_index), detail=msg.detail)


def feedback_rec(msg, recv_us):
    """msg: FeedbackMessage(goal_id, feedback)."""
    fb = msg.feedback
    return sj.FeedbackRec(
        recv_us=recv_us, goal_id=goal_hex(msg.goal_id.uuid), stamp_us=stamp_us(fb.stamp),
        item_index=int(fb.item_index), item_count=int(fb.item_count), item_type=int(fb.item_type),
        phase=int(fb.phase))


def result_rec(wrapped, recv_us):
    """wrapped: get_result_async().result()  (.status, .result)."""
    r = wrapped.result
    return sj.ResultRec(recv_us=recv_us, status=int(wrapped.status), reason=int(r.reason),
                        items_completed=int(r.items_completed), last_item_index=int(r.last_item_index),
                        detail=r.detail)


def _default_subscribe(node, msg_cls, topic, callback):
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    qos = QoSProfile(depth=EVENT_DEPTH, history=HistoryPolicy.KEEP_LAST,
                     reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    return node.create_subscription(msg_cls, topic, callback, qos)


def _default_client(node, action_cls, name):
    from rclpy.action import ActionClient
    return ActionClient(node, action_cls, name)


class GoalRun:
    """goal 하나의 기록. result와 feedback은 callback에서 채워진다."""

    def __init__(self, mission_id, vehicle_id_sent, item_count, sent_us):
        self.mission_id = mission_id
        self.vehicle_id_sent = vehicle_id_sent
        self.item_count = item_count
        self.sent_us = sent_us
        self.accepted = None
        self.goal_id = None
        self.handle = None
        self.result = None
        self.cancel_code = None
        self.feedbacks = []


class MissionClient:
    """node 하나에서 mission_event 구독을 먼저, action client를 그다음에 만든다."""

    def __init__(self, node, vehicle_id, now_us, event_cls=None, action_cls=None,
                 subscribe=_default_subscribe, make_client=_default_client):
        if event_cls is None or action_cls is None:
            from idsim_interfaces.action import ExecuteMission
            from idsim_interfaces.msg import MissionEvent
            event_cls = event_cls or MissionEvent
            action_cls = action_cls or ExecuteMission
        self.node = node
        self.vehicle_id = vehicle_id
        self._now_us = now_us
        self.events = []
        self.feedbacks = []
        self.runs = []
        self.event_topic = "/%s/%s" % (vehicle_id, EVENT_TOPIC)
        self.action_name = "/%s/%s" % (vehicle_id, ACTION_NAME)
        # 순서가 계약이다. 이 두 줄의 순서를 바꾸지 않는다(위 모듈 설명).
        self.event_sub = subscribe(node, event_cls, self.event_topic, self._on_event)
        self.client = make_client(node, action_cls, self.action_name)
        self._action_cls = action_cls

    # --- callback (spin 스레드) ---

    def _on_event(self, msg):
        self.events.append(event_rec(msg, self._now_us()))

    # --- gate ---

    def event_publisher_count(self):
        sub = self.event_sub
        if hasattr(sub, "get_publisher_count"):
            return sub.get_publisher_count()
        return self.node.count_publishers(self.event_topic)

    def server_ready(self):
        return self.client.server_is_ready()

    # --- goal ---

    def build_goal(self, vehicle_id, mission_id, items):
        """items: [dict(type=..., timeout_s=..., height_m=..., acceptance_m=..., duration_s=..., ...)]"""
        from builtin_interfaces.msg import Duration
        from idsim_interfaces.msg import Mission, MissionItem, YawSetpoint
        goal = self._action_cls.Goal()
        goal.vehicle_id = vehicle_id
        goal.mission = Mission()
        goal.mission.mission_id = mission_id
        for it in items:
            m = MissionItem()
            m.type = it["type"]
            m.timeout = _duration(Duration, it["timeout_s"])
            if it["type"] == MissionItem.TYPE_TAKEOFF:
                m.takeoff.height_m = float(it["height_m"])
                m.takeoff.acceptance_m = float(it["acceptance_m"])
                m.takeoff.yaw.mode = YawSetpoint.MODE_KEEP
            elif it["type"] == MissionItem.TYPE_LOITER:
                m.loiter.duration = _duration(Duration, it["duration_s"])
            elif it["type"] == MissionItem.TYPE_GOTO:
                m.go_to.position.x, m.go_to.position.y, m.go_to.position.z = (float(v) for v in it["position"])
                m.go_to.acceptance_radius_m = float(it["acceptance_m"])
                m.go_to.yaw.mode = YawSetpoint.MODE_KEEP
            goal.mission.items.append(m)
        return goal

    def send_goal(self, waiter, vehicle_id, mission_id, items, response_timeout_s=10.0):
        """goal을 보내 accepted 응답까지 기다린다. 이 goal의 GoalRun을 돌려준다(feedback과 result는 채워진다)."""
        goal = self.build_goal(vehicle_id, mission_id, items)
        run = GoalRun(mission_id, vehicle_id, len(items), self._now_us())
        self.runs.append(run)

        def on_feedback(msg):
            rec = feedback_rec(msg, self._now_us())
            run.feedbacks.append(rec)
            self.feedbacks.append(rec)

        fut = self.client.send_goal_async(goal, feedback_callback=on_feedback)
        waiter.wait_until(fut.done, response_timeout_s, "goal 응답")
        handle = fut.result()
        run.handle = handle
        run.accepted = bool(handle.accepted)
        if not run.accepted:
            return run
        run.goal_id = goal_hex(handle.goal_id.uuid)
        res_fut = handle.get_result_async()

        def on_result(f):
            run.result = result_rec(f.result(), self._now_us())

        res_fut.add_done_callback(on_result)
        return run

    def wait_result(self, waiter, run, timeout_s, what="result"):
        waiter.wait_until(lambda: run.result is not None, timeout_s, what)
        return run.result

    def cancel(self, waiter, run, response_timeout_s=10.0):
        fut = run.handle.cancel_goal_async()
        waiter.wait_until(fut.done, response_timeout_s, "cancel 응답")
        run.cancel_code = int(fut.result().return_code)
        return run.cancel_code

    def feedbacks_of(self, run):
        return [f for f in self.feedbacks if f.goal_id == run.goal_id]


def _duration(cls, seconds):
    d = cls()
    d.sec = int(seconds)
    d.nanosec = int(round((seconds - int(seconds)) * 1e9))
    return d


def require_server(waiter, client, timeout_s):
    try:
        waiter.wait_until(client.server_ready, timeout_s, "action server")
    except sw.SitlFailure as e:
        if e.category == sw.TIMEOUT_SIM:
            raise sw.SitlFailure(sw.SERVER_ABSENT, "action server가 ROS 시각 %.0f s 안에 준비되지 않았다" % timeout_s) from e
        raise
