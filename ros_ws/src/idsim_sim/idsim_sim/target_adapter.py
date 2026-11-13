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
"""표적 어댑터 노드. fleet 파일의 궤적 정의(params)를 노드 시계에서 평가해 TargetState를 발행한다.

실행: ros2 run idsim_sim target_adapter --ros-args --params-file <실행 디렉터리>/params/targets.yaml
결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 1, 3.

- Gazebo를 구독하지 않는다. 표적 위치의 원천은 params이고 Gazebo Actor는 화면 확인용이다.
- 노드 하나가 모든 표적을 발행한다(표적별 publisher). 토픽은 /targets/<target_id>/state(절대 이름).
- QoS: RELIABLE, VOLATILE, KEEP_LAST 5(계약 상태 행. C++ contract_qos.hpp와 같은 값을 다시 적는다).
- timer 콜백에서 읽은 노드 시계 시각 t를 stamp로 쓰고 위치와 속도를 같은 t에서 계산한다. 직전 stamp보다
  큰 t에서만 발행하고 0은 내지 않는다. 역행은 오류 로그를 남긴다(역행 상태에 들어갈 때 한 번).
- 준비 표시 파일 /tmp/idsim/targets_ready(ready.py). 시작 때 지운다.
- 설정 오류(use_sim_time false, params 누락, 길이 불일치, id 형식 등)는 종료 코드 2로 끝낸다.
"""

import sys

from builtin_interfaces.msg import Time
from geometry_msgs.msg import Point, Vector3
from idsim_interfaces.msg import TargetState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from idsim_sim.naming import target_state_topic
from idsim_sim.params import ConfigError, parse_params
from idsim_sim.ready import READY_PATH, ReadyTracker, remove_ready_file, write_ready_file
from idsim_sim.trajectory import NS_PER_S, StampDecision, evaluate, stamp_decision

NODE_NAME = "target_adapter"
EXIT_CONFIG_ERROR = 2

# 계약 상태 행(docs/interface.md, idsim_common contract_qos.hpp): 발행 RELIABLE, VOLATILE. 구현 값 KEEP_LAST 5
STATE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


def stamp_msg(stamp_ns):
    sec, nanosec = divmod(stamp_ns, NS_PER_S)
    return Time(sec=sec, nanosec=nanosec)


class _Target:
    def __init__(self, trajectory, publisher):
        self.trajectory = trajectory
        self.publisher = publisher
        self.last_stamp_ns = None
        self.backward = False


class TargetAdapter(Node):
    def __init__(self, ready_path=READY_PATH):
        super().__init__(NODE_NAME, automatically_declare_parameters_from_overrides=True)
        raw = {name: (p.type_.name, p.value) for name, p in self.get_parameters_by_prefix("").items()}
        config = parse_params(raw)  # ConfigError는 main이 종료 코드로 바꾼다
        self._ready_path = ready_path
        self._targets = []
        for traj in config.trajectories:
            topic = target_state_topic(traj.target_id)
            self._targets.append(_Target(traj, self.create_publisher(TargetState, topic, STATE_QOS)))
            self.get_logger().info(
                f"표적 {traj.target_id}: {topic}, waypoint {len(traj.times_ns)}개, loop {traj.loop}")
        self._ready = ReadyTracker([t.trajectory.target_id for t in self._targets])
        self._timer = self.create_timer(1.0 / config.publish_rate_hz, self._tick)
        self.get_logger().info(f"표적 {len(self._targets)}개, 주기 {config.publish_rate_hz} Hz")

    def _tick(self):
        now_ns = self.get_clock().now().nanoseconds
        for target in self._targets:
            decision = stamp_decision(target.last_stamp_ns, now_ns)
            if decision is StampDecision.SKIP_BACKWARD:
                if not target.backward:
                    self.get_logger().error(
                        f"{target.trajectory.target_id}: 시계가 역행했다(직전 stamp {target.last_stamp_ns} ns, "
                        f"지금 {now_ns} ns). 직전 stamp를 넘을 때까지 발행하지 않는다")
                target.backward = True
                continue
            if decision is not StampDecision.PUBLISH:
                continue
            target.backward = False
            sample = evaluate(target.trajectory, now_ns)
            msg = TargetState()
            msg.header.stamp = stamp_msg(now_ns)
            msg.header.frame_id = TargetState.FRAME_ID
            msg.target_id = target.trajectory.target_id
            msg.position = Point(x=sample.position[0], y=sample.position[1], z=sample.position[2])
            msg.velocity_valid = True
            msg.velocity = Vector3(x=sample.velocity[0], y=sample.velocity[1], z=sample.velocity[2])
            target.publisher.publish(msg)
            target.last_stamp_ns = now_ns
            firsts = self._ready.record(target.trajectory.target_id, now_ns)
            if firsts is not None:
                write_ready_file(firsts, self._ready_path)
                self.get_logger().info(f"모든 표적 발행 시작. 표시 파일 {self._ready_path}")


def main(argv=None):
    remove_ready_file(READY_PATH)
    rclpy.init(args=argv)
    node = None
    try:
        try:
            node = TargetAdapter()
        except ConfigError as e:
            rclpy.logging.get_logger(NODE_NAME).fatal(f"params 오류로 시작하지 않는다:\n{e}")
            return EXIT_CONFIG_ERROR
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
