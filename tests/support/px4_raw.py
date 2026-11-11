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

"""PX4 원시 표본 기록기와 직접 명령 송신기(rclpy). ros-ws 컨테이너 안에서 쓴다.

판정 probe의 tick 모델(tick당 최신 표본 1개)과 따로, 구독 콜백마다 표본을 하나도 버리지 않고
쌓는다(KEEP_ALL 구독). 표본마다 PX4 timestamp, 받은 시점의 노드 ROS 시각(use_sim_time), 같은 시점에
마지막으로 본 /clock 값을 함께 남긴다. 판정 로직은 measure_judge.py(순수 코드)에 있다.

시간 규칙: 모든 대기는 노드의 sim 시각 기준이다. 벽시계는 /clock이 멈췄는지 보는 보호에만 쓴다
(ClockStalled).

명령 송신은 idsim_common의 VehicleCommandBuilder와 같은 필드를 채운다(target_component 1,
from_external true, confirmation 0, timestamp는 sim 시각 us). 측정용 직접 송신이라 Executor를 거치지
않는다. 송신자(source) 값은 check_px4.py와 같은 254/1이다.
"""
import math
import re
import threading
import time

from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rosgraph_msgs.msg import Clock

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleCommandAck,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)

from tests.support import measure_judge as mj
from tests.support.receive import SpinThread, wait_for_topic

SOURCE_SYSTEM = 254
SOURCE_COMPONENT = 1
TARGET_COMPONENT = 1
CLOCK_STALL_WALL_S = 15.0


class ClockStalled(Exception):
    """벽시계 CLOCK_STALL_WALL_S 동안 /clock이 전혀 늘지 않았다."""


def _qos_keep_all():
    return QoSProfile(history=HistoryPolicy.KEEP_ALL, reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def _qos_clock():
    return QoSProfile(depth=1000, reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def _qos_in():
    # check_px4.py와 같다. /fmu/in 데이터 리더는 BEST_EFFORT, VOLATILE이다.
    return QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def topic_regex(ns, direction, base):
    return "^/%s/fmu/%s/%s(_v[0-9]+)?$" % (re.escape(ns), direction, re.escape(base))


class Px4Raw:
    """한 기체의 원시 표본 기록과 직접 명령 송신."""

    def __init__(self, ns, sysid, node_name="measure_px4_raw"):
        self.ns = ns
        self.sysid = int(sysid)
        self.node = Node(node_name, parameter_overrides=[Parameter("use_sim_time", value=True)])
        self._lock = threading.Lock()
        self.status = []      # StatusSample (수신 순서)
        self.landed = []      # LandedSample
        self.pos = []         # (recv_ros_us, x, y, z, heading, xy_valid, z_valid)
        self.acks = []        # dict(recv_ros_us, command, result)
        self.sends = []       # dict(kind, recv_ros_us, ts_us)
        self._clock_us = 0
        self._clock_n = 0
        self.topics = {}
        self._spin = None
        self._wall_last_change = time.monotonic()
        self._wall_last_clock = -1

    # --- 시작과 종료 ---------------------------------------------------

    def start(self, timeout_s=60.0):
        """토픽을 찾아 구독과 발행자를 만들고 spin을 시작한다. 못 찾으면 RuntimeError(NO_PUBLISHER)."""
        n = self.node
        clock_sub = n.create_subscription(Clock, "/clock", self._on_clock, _qos_clock())
        self._keep = [clock_sub]
        found = {}
        for key, direction, base in (
                ("status", "out", "vehicle_status"), ("landed", "out", "vehicle_land_detected"),
                ("pos", "out", "vehicle_local_position"), ("ack", "out", "vehicle_command_ack"),
                ("command", "in", "vehicle_command"), ("offboard", "in", "offboard_control_mode"),
                ("setpoint", "in", "trajectory_setpoint")):
            hit = wait_for_topic(n, topic_regex(self.ns, direction, base), timeout_s)
            if hit is None:
                raise RuntimeError("NO_PUBLISHER: %s 토픽을 %s s 안에 찾지 못함" % (base, timeout_s))
            found[key] = hit[0]
        self.topics = found
        keep = self._keep
        keep.append(n.create_subscription(VehicleStatus, found["status"], self._on_status,
                                          _qos_keep_all()))
        keep.append(n.create_subscription(VehicleLandDetected, found["landed"], self._on_landed,
                                          _qos_keep_all()))
        keep.append(n.create_subscription(VehicleLocalPosition, found["pos"], self._on_pos,
                                          _qos_keep_all()))
        keep.append(n.create_subscription(VehicleCommandAck, found["ack"], self._on_ack,
                                          _qos_keep_all()))
        self._pub_cmd = n.create_publisher(VehicleCommand, found["command"], _qos_in())
        self._pub_mode = n.create_publisher(OffboardControlMode, found["offboard"], _qos_in())
        self._pub_sp = n.create_publisher(TrajectorySetpoint, found["setpoint"], _qos_in())
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

    # --- 콜백 ----------------------------------------------------------

    def _on_clock(self, msg):
        self._clock_us = msg.clock.sec * 1_000_000 + msg.clock.nanosec // 1000
        self._clock_n += 1

    def _on_status(self, m):
        s = mj.StatusSample(int(m.timestamp), self.now_us(), self._clock_us, int(m.arming_state),
                            int(m.nav_state), bool(m.failsafe), int(m.nav_state_user_intention))
        self.status.append(s)

    def _on_landed(self, m):
        self.landed.append(mj.LandedSample(int(m.timestamp), self.now_us(), bool(m.landed)))

    def _on_pos(self, m):
        self.pos.append((self.now_us(), float(m.x), float(m.y), float(m.z), float(m.heading),
                         bool(m.xy_valid), bool(m.z_valid)))

    def _on_ack(self, m):
        self.acks.append({"recv_ros_us": self.now_us(), "command": int(m.command),
                          "result": int(m.result), "target_system": int(m.target_system)})

    # --- 송신 ----------------------------------------------------------

    def _cmd(self, command, p1=0.0, p2=0.0, p3=0.0, p4=0.0, p5=0.0, p6=0.0, p7=0.0):
        m = VehicleCommand()
        m.timestamp = self.now_us()
        m.command = int(command)
        m.param1, m.param2, m.param3 = float(p1), float(p2), float(p3)
        m.param4, m.param5, m.param6, m.param7 = float(p4), float(p5), float(p6), float(p7)
        m.target_system = self.sysid
        m.target_component = TARGET_COMPONENT
        m.source_system = SOURCE_SYSTEM
        m.source_component = SOURCE_COMPONENT
        m.confirmation = 0
        m.from_external = True
        return m

    def send(self, kind):
        """kind: arm, disarm, offboard, hold, land. (전송 직후 recv_ros_us, Px4Timestamp us)를 돌려준다."""
        nan = math.nan
        if kind == "arm":
            m = self._cmd(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
        elif kind == "disarm":
            m = self._cmd(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 0.0)
        elif kind == "offboard":
            m = self._cmd(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
        elif kind == "hold":
            m = self._cmd(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 4.0, 3.0)
        elif kind == "land":
            m = self._cmd(VehicleCommand.VEHICLE_CMD_NAV_LAND, 0.0, 0.0, 0.0, nan, nan, nan, nan)
        else:
            raise ValueError(kind)
        self._pub_cmd.publish(m)
        rec = {"kind": kind, "recv_ros_us": self.now_us(), "ts_us": int(m.timestamp)}
        self.sends.append(rec)
        return rec["recv_ros_us"], rec["ts_us"]

    def publish_position(self, x, y, z, yaw):
        """offboard_control_mode(position만 true)와 trajectory_setpoint(NED, m와 rad)를 한 번 발행."""
        ts = self.now_us()
        mode = OffboardControlMode()
        mode.timestamp = ts
        mode.position = True
        mode.velocity = mode.acceleration = mode.attitude = False
        mode.body_rate = mode.thrust_and_torque = mode.direct_actuator = False
        sp = TrajectorySetpoint()
        sp.timestamp = ts
        sp.position = [float(x), float(y), float(z)]
        sp.yaw = float(yaw)
        sp.velocity = [math.nan] * 3
        sp.acceleration = [math.nan] * 3
        sp.jerk = [math.nan] * 3
        sp.yawspeed = math.nan
        self._pub_mode.publish(mode)
        self._pub_sp.publish(sp)

    # --- 조회 ----------------------------------------------------------

    def last_status(self):
        return self.status[-1] if self.status else None

    def last_landed(self):
        return self.landed[-1] if self.landed else None

    def last_pos(self):
        return self.pos[-1] if self.pos else None

    def acks_for(self, command, after_recv_us):
        return [a for a in self.acks if a["command"] == int(command)
                and a["recv_ros_us"] >= after_recv_us]
