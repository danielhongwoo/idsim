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

"""PX4 원시 표본 기록기(rclpy, 구독만). ros-ws 컨테이너 안에서 쓴다.

이 모듈은 발행자를 만들지 않는다. 측정용 직접 송신(trajectory_setpoint 발행, source 254/1)은
px4_measure_pub.py에 분리했다(측정 전용). 시나리오가 이 모듈을 가져가도 setpoint를 발행할 수 없다.
decisions.md 쟁점 5의 "px4_raw 한 모듈만 발행자를 만든다. 허용은 offboard_control_mode와
vehicle_command(source 254/25 외 거부). 테스트는 trajectory_setpoint를 발행하지 않는다"에 맞는
시나리오용 발행자는 P4 시나리오 구현 때 이 모듈에 만든다(여기에는 없다).

판정 probe의 tick 모델(tick당 최신 표본 1개)과 따로, 구독 callback마다 표본을 쌓는다(KEEP_ALL 구독).
BEST_EFFORT 구독이라 "하나도 버리지 않는다"는 DDS가 이 노드에 전달한 표본에 대해서만 참이다.
전송 중 유실은 이 기록으로 알 수 없고, crosscheck.py가 ULog에만 있는 표본(ulog_only)으로 본다.
표본마다 PX4 timestamp, 받은 시점의 노드 ROS 시각(use_sim_time), 같은 시점에 마지막으로 본
/clock 값을 함께 남긴다. 판정 로직은 measure_judge.py(순수 코드)에 있다.

시간 규칙: 모든 대기는 노드의 sim 시각 기준이다. 벽시계는 /clock이 멈췄는지 보는 보호에만 쓴다
(ClockStalled).

토픽 이름 조립(topic_regex)은 임시다. P4의 px4_topic 모듈이 생기면 그쪽으로 바꾼다.
"""
import re
import time

from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock

from px4_msgs.msg import (
    VehicleCommandAck,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)

from tests.support import measure_judge as mj
from tests.support.receive import SpinThread, wait_for_topic

CLOCK_STALL_WALL_S = 15.0


class ClockStalled(Exception):
    """벽시계 CLOCK_STALL_WALL_S 동안 /clock이 전혀 늘지 않았다."""


def _qos_keep_all():
    return QoSProfile(history=HistoryPolicy.KEEP_ALL, reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def _qos_clock():
    return QoSProfile(depth=1000, reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def topic_regex(ns, direction, base):
    return "^/%s/fmu/%s/%s(_v[0-9]+)?$" % (re.escape(ns), direction, re.escape(base))


class Px4Raw:
    """한 기체의 원시 표본 기록(구독 전용)."""

    def __init__(self, ns, sysid, node_name="measure_px4_raw"):
        self.ns = ns
        self.sysid = int(sysid)
        self.node = Node(node_name, parameter_overrides=[Parameter("use_sim_time", value=True)])
        self.status = []      # StatusSample (수신 순서)
        self.landed = []      # LandedSample
        self.pos = []         # (recv_ros_us, x, y, z, heading, xy_valid, z_valid)
        self.acks = []        # dict(recv_ros_us, command, result, target_system)
        self.sends = []       # dict(kind, recv_ros_us, ts_us). 송신기가 채운다
        self._clock_us = 0
        self.topics = {}
        self._spin = None
        self._keep = []
        self._wall_last_change = time.monotonic()
        self._wall_last_clock = -1

    # --- 시작과 종료 ---------------------------------------------------

    def start(self, timeout_s=60.0):
        """토픽을 찾아 구독을 만들고 spin을 시작한다. 못 찾으면 RuntimeError(NO_PUBLISHER)."""
        n = self.node
        self._keep.append(n.create_subscription(Clock, "/clock", self._on_clock, _qos_clock()))
        found = {}
        for key, base in (("status", "vehicle_status"), ("landed", "vehicle_land_detected"),
                          ("pos", "vehicle_local_position"), ("ack", "vehicle_command_ack")):
            hit = wait_for_topic(n, topic_regex(self.ns, "out", base), timeout_s)
            if hit is None:
                raise RuntimeError("NO_PUBLISHER: %s 토픽을 %s s 안에 찾지 못함" % (base, timeout_s))
            found[key] = hit[0]
        self.topics = found
        qos = _qos_keep_all()
        self._keep.append(n.create_subscription(VehicleStatus, found["status"], self._on_status, qos))
        self._keep.append(n.create_subscription(VehicleLandDetected, found["landed"],
                                                self._on_landed, qos))
        self._keep.append(n.create_subscription(VehicleLocalPosition, found["pos"],
                                                self._on_pos, qos))
        self._keep.append(n.create_subscription(VehicleCommandAck, found["ack"], self._on_ack, qos))
        self._spin = SpinThread(n)
        self._spin.__enter__()

    def close(self):
        if self._spin is not None:
            self._spin.__exit__(None, None, None)
            self._spin = None
        self.node.destroy_node()

    # --- 시간 ----------------------------------------------------------

    def now_us(self):
        """노드의 ROS 시각(use_sim_time)을 us로. Px4Timestamp와 같은 축이다."""
        return self.node.get_clock().now().nanoseconds // 1000

    def clock_us(self):
        return self._clock_us

    def guard(self):
        """/clock이 벽시계 CLOCK_STALL_WALL_S 동안 늘지 않았으면 ClockStalled."""
        c = self._clock_us
        w = time.monotonic()
        if c != self._wall_last_clock:
            self._wall_last_clock = c
            self._wall_last_change = w
        elif w - self._wall_last_change > CLOCK_STALL_WALL_S:
            raise ClockStalled("/clock이 벽시계 %.0f s 동안 늘지 않음" % CLOCK_STALL_WALL_S)

    # --- callback ------------------------------------------------------

    def _on_clock(self, msg):
        self._clock_us = msg.clock.sec * 1_000_000 + msg.clock.nanosec // 1000

    def _on_status(self, m):
        self.status.append(mj.StatusSample(
            int(m.timestamp), self.now_us(), self._clock_us, int(m.arming_state),
            int(m.nav_state), bool(m.failsafe), int(m.nav_state_user_intention)))

    def _on_landed(self, m):
        self.landed.append(mj.LandedSample(int(m.timestamp), self.now_us(), bool(m.landed)))

    def _on_pos(self, m):
        self.pos.append((self.now_us(), float(m.x), float(m.y), float(m.z), float(m.heading),
                         bool(m.xy_valid), bool(m.z_valid)))

    def _on_ack(self, m):
        # ack에는 원 명령을 가리키는 필드가 없다. arm과 disarm(command 400)의 ack는 전송 시각으로 가른다.
        self.acks.append({
            "recv_ros_us": self.now_us(), "ts_us": int(m.timestamp), "command": int(m.command),
            "result": int(m.result), "result_param1": int(m.result_param1),
            "result_param2": int(m.result_param2), "target_system": int(m.target_system),
            "target_component": int(m.target_component), "from_external": bool(m.from_external)})

    # --- 조회 ----------------------------------------------------------

    def last_status(self):
        return self.status[-1] if self.status else None

    def last_landed(self):
        return self.landed[-1] if self.landed else None

    def last_pos(self):
        return self.pos[-1] if self.pos else None

    def acks_between(self, command, from_recv_us, to_recv_us=None):
        """수신 시각이 [from, to) 안인 command의 ack 결과 목록. 같은 command 번호(400: arm과 disarm)의
        ack는 전송 시각 구간으로 나눠 읽는다."""
        return [a["result"] for a in self.acks
                if a["command"] == int(command) and a["recv_ros_us"] >= from_recv_us
                and (to_recv_us is None or a["recv_ros_us"] < to_recv_us)]
