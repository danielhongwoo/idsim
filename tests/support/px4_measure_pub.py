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

"""측정 전용 PX4 직접 발행자. 시나리오와 판정 코드는 이 모듈을 가져가지 않는다.

PX4에 vehicle_command(source 254/1)와 offboard_control_mode, trajectory_setpoint를 직접 보낸다.
decisions.md 쟁점 8은 테스트 쪽 발행을 px4_raw 한 모듈의 offboard_control_mode와
vehicle_command(source 254/25)로 제한하고 테스트가 trajectory_setpoint를 발행하지 않는다고 정한다.
재실측은 Executor 없이 PX4의 반응을 보는 일이라 그 제한 밖의 발행이 필요해서 이 모듈로 분리했다.
그래서 생성자가 measure_only=True를 키워드로 요구한다(실수로 쓰지 못하게). 시나리오용 발행자는
여기에 만들지 않는다.

명령 필드는 idsim_common의 VehicleCommandBuilder와 같다(target_component 1, from_external true,
confirmation 0, timestamp는 sim 시각 us).
"""
import math

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand

from tests.support.px4_raw import topic_regex
from tests.support.receive import wait_for_topic

SOURCE_SYSTEM = 254
SOURCE_COMPONENT = 1
TARGET_COMPONENT = 1


def _qos_in():
    # check_px4.py와 같다. fmu 입력 데이터 리더는 BEST_EFFORT, VOLATILE이다.
    return QoSProfile(depth=10, history=HistoryPolicy.KEEP_LAST,
                      reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


class MeasureOnlyPublisher:
    """재실측 전용 발행자. raw는 Px4Raw(시각, sends 기록을 빌려 쓴다)."""

    def __init__(self, raw, *, measure_only, timeout_s=60.0):
        if measure_only is not True:
            raise ValueError("MeasureOnlyPublisher는 측정 전용이다: measure_only=True를 명시하라")
        self._raw = raw
        n = raw.node
        topics = {}
        for key, base in (("command", "vehicle_command"), ("offboard", "offboard_control_mode"),
                          ("setpoint", "trajectory_setpoint")):
            hit = wait_for_topic(n, topic_regex(raw.ns, "in", base), timeout_s)
            if hit is None:
                raise RuntimeError("NO_PUBLISHER: %s 구독자 토픽을 %s s 안에 찾지 못함" % (base, timeout_s))
            topics[key] = hit[0]
        self.topics = topics
        self._pub_cmd = n.create_publisher(VehicleCommand, topics["command"], _qos_in())
        self._pub_mode = n.create_publisher(OffboardControlMode, topics["offboard"], _qos_in())
        self._pub_sp = n.create_publisher(TrajectorySetpoint, topics["setpoint"], _qos_in())

    def _cmd(self, command, p1=0.0, p2=0.0, p3=0.0, p4=0.0, p5=0.0, p6=0.0, p7=0.0):
        m = VehicleCommand()
        m.timestamp = self._raw.now_us()
        m.command = int(command)
        m.param1, m.param2, m.param3 = float(p1), float(p2), float(p3)
        m.param4, m.param5, m.param6, m.param7 = float(p4), float(p5), float(p6), float(p7)
        m.target_system = self._raw.sysid
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
        rec = {"kind": kind, "recv_ros_us": self._raw.now_us(), "ts_us": int(m.timestamp)}
        self._raw.sends.append(rec)
        return rec["recv_ros_us"], rec["ts_us"]

    def publish_position(self, x, y, z, yaw):
        """offboard_control_mode(position만 true)와 trajectory_setpoint(NED, m와 rad)를 한 번 발행."""
        ts = self._raw.now_us()
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
