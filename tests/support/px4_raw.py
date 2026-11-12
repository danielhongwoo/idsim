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

"""PX4 원시 표본 기록기(구독)와 통합 테스트용 발행자 둘. ros-ws 컨테이너 안에서 쓴다.

기록기(Px4Raw)는 판정 probe의 tick 모델(tick당 최신 표본 1개)과 따로, 구독 callback마다 표본을 쌓는다
(KEEP_ALL 구독). BEST_EFFORT 구독이라 "하나도 버리지 않는다"는 DDS가 이 노드에 전달한 표본에 대해서만
참이다. 전송 중 유실은 이 기록으로 알 수 없고, crosscheck.py가 ULog에만 있는 표본(ulog_only)으로 본다.
표본마다 PX4 timestamp, 받은 시점의 노드 ROS 시각(use_sim_time), 같은 시점에 마지막으로 본 /clock 값을
함께 남긴다. 판정 로직은 measure_judge.py와 sitl_judge.py(순수 코드)에 있다.

발행자는 이 모듈에서 둘만 만든다(decisions.md 쟁점 8). 통합 테스트는 trajectory_setpoint를 발행하지 않는다.
  - OffboardSignal: offboard_control_mode(시나리오 T). context manager로만 만들고 끝나면 destroy한다.
  - EmergencyCommand: vehicle_command(비상 정리 전용). source가 (254, 25)가 아니면 생성을 거부하고,
    기대 sysid의 vehicle_status를 받아 대조한 뒤에만 발행한다.
측정 전용 직접 발행(trajectory_setpoint, source 254/1)은 px4_measure_pub.py에 분리했다.
이 모듈의 변경과 발행자, 명령 목록의 확장은 px4-engineer의 필수 승인 대상이다.

시간 규칙: 모든 대기는 노드의 sim 시각 기준이다. 벽시계는 /clock이 멈췄는지 보는 보호에만 쓴다
(ClockStalled. 시나리오는 sitl_wait.Waiter를 쓴다).

토픽 이름은 px4_topic.py가 만든다. topic_regex는 측정 스크립트(px4_measure_pub)가 버전 접미사를 가리지 않고
찾을 때 쓰는 정규식이다.
"""
import math
import re
import time

from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock

from px4_msgs.msg import (
    FailsafeFlags,
    OffboardControlMode,
    VehicleCommand,
    VehicleCommandAck,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)

from tests.support import measure_judge as mj
from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw
from tests.support.px4_topic import px4_topic
from tests.support.receive import SpinThread, wait_for_topic

EMERGENCY_SOURCE = (254, 25)    # 비상 정리 전용 발행자의 source(system, component). 측정기는 (254, 1)

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


def _qos_in():
    # 스모크 px4-in과 같다. fmu 입력 데이터 리더는 BEST_EFFORT, VOLATILE이다.
    return QoSProfile(depth=10, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


class Px4Raw:
    """한 기체의 원시 표본 기록(구독 전용)."""

    def __init__(self, ns, sysid, node_name="measure_px4_raw", with_flags=False):
        self.ns = ns                              # 측정 스크립트 표기("px4_1"). 빗금 유무는 가리지 않는다
        self.ns_abs = "/" + ns.strip("/")         # px4_topic 표기("/px4_1")
        self.sysid = int(sysid)
        self.with_flags = bool(with_flags)
        self.node = Node(node_name, parameter_overrides=[Parameter("use_sim_time", value=True)])
        self.status_sysids = {}   # vehicle_status.system_id -> 표본 수
        self.flags = []       # sitl_judge.FlagSample (with_flags일 때만)
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
        specs = [("status", "vehicle_status", VehicleStatus),
                 ("landed", "vehicle_land_detected", VehicleLandDetected),
                 ("pos", "vehicle_local_position", VehicleLocalPosition),
                 ("ack", "vehicle_command_ack", VehicleCommandAck)]
        if self.with_flags:
            specs.append(("flags", "failsafe_flags", FailsafeFlags))
        for key, base, cls in specs:
            name = px4_topic(self.ns_abs, "out", base, cls)
            hit = wait_for_topic(n, "^%s$" % re.escape(name), timeout_s)
            if hit is None:
                raise sw.SitlFailure(sw.NO_PUBLISHER, "%s 토픽을 %s s 안에 찾지 못함" % (name, timeout_s))
            found[key] = hit[0]
        self.topics = found
        qos = _qos_keep_all()
        self._keep.append(n.create_subscription(VehicleStatus, found["status"], self._on_status, qos))
        self._keep.append(n.create_subscription(VehicleLandDetected, found["landed"],
                                                self._on_landed, qos))
        self._keep.append(n.create_subscription(VehicleLocalPosition, found["pos"],
                                                self._on_pos, qos))
        self._keep.append(n.create_subscription(VehicleCommandAck, found["ack"], self._on_ack, qos))
        if self.with_flags:
            self._keep.append(n.create_subscription(FailsafeFlags, found["flags"], self._on_flags, qos))
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

    def _on_flags(self, m):
        self.flags.append(sj.FlagSample(int(m.timestamp), self.now_us(),
                                        bool(m.offboard_control_signal_lost)))

    def _on_status(self, m):
        sid = int(m.system_id)
        self.status_sysids[sid] = self.status_sysids.get(sid, 0) + 1
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

    def last_status_sysid_ok(self):
        """받은 vehicle_status 가운데 기대 sysid(self.sysid)의 표본이 있고 다른 sysid의 표본이 없는가."""
        return self.status_sysids.get(self.sysid, 0) > 0 and set(self.status_sysids) == {self.sysid}

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


# ---------------------------------------------------------------------------
# 발행자 둘(통합 테스트)


class OffboardSignal:
    """시나리오 T 전용 offboard_control_mode 발행자(position=true만). with 문으로만 쓴다.

    20 Hz(노드 시계 = sim 시각) timer가 timestamp를 `지금 - lag_s`로 채워 발행한다. lag_s를 바꿔
    현재 timestamp(0)와 묵은 timestamp(2 s)를 오간다. 끝나면 timer와 발행자를 destroy한다.
    발행 전에 발행자의 get_subscription_count() >= 1을 확인한다(없으면 NO_PUBLISHER).
    """

    PERIOD_S = 0.05

    def __init__(self, raw, waiter, subscriber_timeout_s=10.0):
        self._raw = raw
        self._waiter = waiter
        self._timeout = subscriber_timeout_s
        self._pub = None
        self._timer = None
        self.lag_s = 0.0
        self.published = 0

    def __enter__(self):
        n = self._raw.node
        name = px4_topic(self._raw.ns_abs, "in", "offboard_control_mode", OffboardControlMode)
        self._pub = n.create_publisher(OffboardControlMode, name, _qos_in())
        try:
            self._waiter.wait_until(lambda: self._pub.get_subscription_count() >= 1, self._timeout,
                                    "offboard_control_mode 구독자")
        except sw.SitlFailure as e:
            self._destroy()
            raise sw.SitlFailure(sw.NO_PUBLISHER, "offboard_control_mode 구독자가 없다(%s)" % e.message) from e
        self._timer = n.create_timer(self.PERIOD_S, self._tick)
        return self

    def __exit__(self, *exc):
        self._destroy()
        return False

    def _destroy(self):
        n = self._raw.node
        if self._timer is not None:
            n.destroy_timer(self._timer)
            self._timer = None
        if self._pub is not None:
            n.destroy_publisher(self._pub)
            self._pub = None

    def _tick(self):
        if self._pub is None:
            return
        m = OffboardControlMode()
        m.timestamp = max(0, self._raw.now_us() - int(self.lag_s * 1_000_000))
        m.position = True
        m.velocity = m.acceleration = m.attitude = False
        m.body_rate = m.thrust_and_torque = m.direct_actuator = False
        self._pub.publish(m)
        self.published += 1


class EmergencyCommand:
    """비상 정리 전용 vehicle_command 발행자. source가 (254, 25)가 아니면 생성을 거부한다.

    발행 전에 기록기가 받은 vehicle_status가 기대 sysid뿐인지 대조한다(아니면 RuntimeError).
    정상 경로(Executor)와 측정기(source 254/1)가 아닌 사람이 읽는 source로 남기려는 것이다.
    명령은 land와 disarm 둘뿐이다.
    """

    def __init__(self, raw, source_system, source_component, timeout_s=10.0):
        if (int(source_system), int(source_component)) != EMERGENCY_SOURCE:
            raise ValueError("비상 정리 발행자의 source는 %r이어야 한다(받은 값: %r)"
                             % (EMERGENCY_SOURCE, (source_system, source_component)))
        self._raw = raw
        name = px4_topic(raw.ns_abs, "in", "vehicle_command", VehicleCommand)
        self._pub = raw.node.create_publisher(VehicleCommand, name, _qos_in())
        self.sent = []

    def close(self):
        if self._pub is not None:
            self._raw.node.destroy_publisher(self._pub)
            self._pub = None

    def _cmd(self, command, *params):
        raw = self._raw
        if not raw.last_status_sysid_ok():
            raise RuntimeError("기대 sysid %d의 vehicle_status만 받았는지 대조에 실패했다(받은 sysid: %r)"
                               % (raw.sysid, raw.status_sysids))
        p = list(params) + [0.0] * (7 - len(params))
        m = VehicleCommand()
        m.timestamp = raw.now_us()
        m.command = int(command)
        m.param1, m.param2, m.param3, m.param4, m.param5, m.param6, m.param7 = (float(x) for x in p)
        m.target_system = raw.sysid
        m.target_component = 1
        m.source_system, m.source_component = EMERGENCY_SOURCE
        m.confirmation = 0
        m.from_external = True
        self._pub.publish(m)
        self.sent.append((int(command), m.timestamp))

    def land(self):
        nan = math.nan
        self._cmd(VehicleCommand.VEHICLE_CMD_NAV_LAND, 0.0, 0.0, 0.0, nan, nan, nan, nan)

    def disarm(self):
        self._cmd(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 0.0)
