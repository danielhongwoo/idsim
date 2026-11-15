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

"""SITL 정답 pose와 표적 상태의 기록기(rclpy). ros-ws 컨테이너(runner) 안에서 쓴다. 1b decisions.md 쟁점 5.

정답 pose(/sim/<vehicle_id>/pose)는 SITL 전용이고 계약이 아니다. TargetState(/targets/<id>/state)는 계약 토픽이다.
판정 로직은 sitl_judge.py(순수 코드)의 정답 판정 절에 있고 이 모듈은 표본만 쌓는다(callback마다 하나).

QoS 짝(발행 -> 구독)
  /sim/<vehicle_id>/pose  sim_oracle.py RELIABLE, VOLATILE, KEEP_LAST 10 -> 여기 RELIABLE, VOLATILE, KEEP_LAST
                          ORACLE_DEPTH. 약 50 Hz라 depth를 크게 두어 spin이 밀려도 표본을 버리지 않는다.
  /targets/<id>/state     표적 어댑터(계약 상태 행 RELIABLE, VOLATILE) -> 여기 계약 상태 구독 행 BEST_EFFORT,
                          VOLATILE에 KEEP_LAST TARGET_DEPTH(Executor와 같은 reliability로 받는다).
  /clock                  R3의 /clock 간격 기록 전용(BEST_EFFORT). 판정 시각은 Px4Raw의 /clock과 노드 시계가 쓴다.
구독은 gate(첫 goal 전)에서 발행자와 첫 표본을 확인한다(sitl_session).
"""
import time

from tests.support import sitl_judge as sj

ORACLE_DEPTH = 2000
TARGET_DEPTH = 200
CLOCK_DEPTH = 1000


def _stamp_us(t):
    return int(t.sec) * 1_000_000 + int(t.nanosec) // 1000


class SimTruth:
    """한 기체의 정답 pose와 표적들의 TargetState 기록. node는 미션 노드(같은 participant)다."""

    def __init__(self, node, vehicle_id, target_ids, now_us):
        from geometry_msgs.msg import PoseStamped
        from idsim_interfaces.msg import TargetState
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from rosgraph_msgs.msg import Clock

        self.node = node
        self._now_us = now_us
        self.oracle_topic = sj.oracle_pose_topic(vehicle_id)
        self.oracle = []          # sj.OracleSample(수신 순서)
        self.oracle_bad_frame = 0
        self.targets = {tid: [] for tid in target_ids}     # id -> [sj.TargetSample]
        self.target_bad = {tid: 0 for tid in target_ids}   # frame_id나 target_id가 다른 표본 수
        self.target_topics = {tid: "%s/%s/%s" % (TargetState.TOPIC_PREFIX, tid, TargetState.TOPIC_SUFFIX)
                              for tid in target_ids}
        self._target_frame = TargetState.FRAME_ID
        self.clock_sim_steps_us = []   # 이어 받은 /clock 값의 차
        self.clock_wall_gaps_s = []    # 이어 받은 /clock 수신 사이의 벽시계 간격
        self._last_clock = None
        rel = QoSProfile(depth=ORACLE_DEPTH, history=HistoryPolicy.KEEP_LAST,
                         reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
        best = QoSProfile(depth=TARGET_DEPTH, history=HistoryPolicy.KEEP_LAST,
                          reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        clk = QoSProfile(depth=CLOCK_DEPTH, history=HistoryPolicy.KEEP_LAST,
                         reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)
        self.oracle_sub = node.create_subscription(PoseStamped, self.oracle_topic, self._on_oracle, rel)
        self.target_subs = {
            tid: node.create_subscription(TargetState, topic, lambda m, tid=tid: self._on_target(tid, m), best)
            for tid, topic in self.target_topics.items()}
        self.clock_sub = node.create_subscription(Clock, "/clock", self._on_clock, clk)

    # --- callback ---

    def _on_oracle(self, m):
        if m.header.frame_id != "world":
            self.oracle_bad_frame += 1
            return
        p = m.pose.position
        self.oracle.append(sj.OracleSample(_stamp_us(m.header.stamp), self._now_us(), float(p.x), float(p.y),
                                           float(p.z)))

    def _on_target(self, tid, m):
        if m.header.frame_id != self._target_frame or m.target_id != tid:
            self.target_bad[tid] += 1
            return
        p, v = m.position, m.velocity
        self.targets[tid].append(sj.TargetSample(
            _stamp_us(m.header.stamp), self._now_us(), float(p.x), float(p.y), float(p.z),
            bool(m.velocity_valid), float(v.x), float(v.y), float(v.z)))

    def _on_clock(self, m):
        c = _stamp_us(m.clock)
        w = time.monotonic()
        if self._last_clock is not None:
            self.clock_sim_steps_us.append(c - self._last_clock[0])
            self.clock_wall_gaps_s.append(w - self._last_clock[1])
        self._last_clock = (c, w)

    # --- 조회 ---

    def oracle_publishers(self):
        return self.oracle_sub.get_publisher_count()

    def target_publishers(self, tid):
        return self.target_subs[tid].get_publisher_count()

    def target_publisher_qos(self, tid):
        """표적 토픽 발행자마다 (노드 이름, reliability 이름, durability 이름). graph 조회다."""
        out = []
        for info in self.node.get_publishers_info_by_topic(self.target_topics[tid]):
            q = info.qos_profile
            out.append((info.node_name, q.reliability.name, q.durability.name))
        return out


def qos_contract_findings(pub_qos):
    """계약 상태 행(발행 RELIABLE, VOLATILE. docs/interface.md "계약 토픽 QoS")과 다른 발행자의 설명 목록."""
    return ["%s: %s, %s" % (n, r, d) for n, r, d in pub_qos if (r, d) != ("RELIABLE", "VOLATILE")]
