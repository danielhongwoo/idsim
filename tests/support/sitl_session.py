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

"""SITL 통합 테스트의 세션(rclpy). ros-ws 컨테이너(runner) 안에서 이미 떠 있는 스택에 붙는다.

스택을 올리고 내리는 것은 호스트의 tests/sitl/run_sitl.sh다. 이 세션은 stack.json(IDSIM_STACK_FILE)을 읽고
준비 상태를 검증만 한다. 준비 검증(gate)이 실패하면 skip이 아니라 오류다(decisions.md 쟁점 1, 7).

노드 둘이 한 프로세스(한 participant)에 있다: Px4Raw의 노드(PX4 토픽, /clock)와 미션 노드(mission_event 구독,
action client). 미션 노드 안에서는 mission_event 구독이 action client보다 먼저 만들어진다(mission_client).
"""
import json
import time

from tests.support import mission_client as mcl
from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw
from tests.support.px4_raw import EmergencyCommand, Px4Raw
from tests.support.sitl_trace import Trace

US = 1_000_000
CLOCK_DISCOVERY_WALL_S = 15.0    # 프로세스 시작 직후 첫 /clock 수신까지만 쓰는 벽시계 유예(Px4Raw.start가 쓴다)
GATE_SERVER_S = 30.0
GATE_STATUS_S = 20.0
GROUND_WAIT_S = 20.0
EMERGENCY_WAIT_S = 90.0
EMERGENCY_LAND_S = 15.0       # Land 재전송을 이어 가는 상한(AUTO_LAND 또는 DISARMED가 보일 때까지)


class SitlSession:
    def __init__(self, stack, out_dir):
        import rclpy
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from tests.support.receive import SpinThread

        self.stack = stack
        self.vehicle = stack.vehicles[0]
        self.vehicle_id = self.vehicle.vehicle_id
        self.out_dir = out_dir
        self._rclpy = rclpy
        rclpy.init()
        self.raw = Px4Raw(self.vehicle.px4_ns, self.vehicle.sysid, node_name="sitl_px4_raw", with_flags=True)
        self.waiter = sw.Waiter(self._sim_s)
        self.trace = Trace(out_dir / "trace.jsonl", sim_us=self.raw.clock_us)
        self.node = Node("sitl_mission_client", parameter_overrides=[Parameter("use_sim_time", value=True)])
        self.mission = mcl.MissionClient(self.node, self.vehicle_id, self.raw.now_us)
        self._spin = SpinThread(self.node)
        self._started = False
        self.rtf_start = None
        self.milestones = {}
        self.gate_info = {}
        self.hold_dev = {}       # 유지 구간의 기준 고도로부터 최대 편차(m). A_loiter, D_hover
        self.armed_a = None      # 시나리오 A의 ARMED 표본 기록(armed_a.json과 같은 내용)

    # --- 시각 ---

    def _sim_s(self):
        c = self.raw.clock_us()
        return c / US if c > 0 else None

    def sim_us(self):
        return self.raw.now_us()

    # --- gate ---

    def start(self):
        """토픽을 찾고 구독을 만들어 spin을 시작한다. gate()가 이어서 준비 상태를 검증한다."""
        self.raw.start(waiter=self.waiter, clock_wall_grace_s=CLOCK_DISCOVERY_WALL_S)
        self._spin.__enter__()
        self._started = True

    def close(self):
        try:
            self.emergency_cleanup()
        finally:
            self.trace.close()
            if self._started:
                self._spin.__exit__(None, None, None)
            self.node.destroy_node()
            self.raw.close()
            if self._rclpy.ok():
                self._rclpy.shutdown()

    def gate(self):
        """goal 전 gate(decisions.md 쟁점 7)와 /clock 정렬(쟁점 9). 어긋나면 SitlFailure."""
        w = self.waiter
        w0 = time.monotonic()
        s0 = self.raw.clock_us()
        w.now()
        # 1. 맺어짐: 사건 발행자, PX4 토픽의 발행자(각 구독 객체의 get_publisher_count(). graph 조회가 아니다).
        #    사건 수신의 근거는 아니다(순서 규칙이 받친다)
        self._need(lambda: self.mission.event_publisher_count() >= 1, 20.0, "mission_event 발행자",
                   sw.NO_PUBLISHER)
        for key in sorted(self.raw.subs):
            self._need(lambda k=key: self.raw.subs[k].get_publisher_count() >= 1, 20.0,
                       "구독 %s의 발행자" % key, sw.NO_PUBLISHER)
        # 2. action server
        mcl.require_server(w, self.mission, GATE_SERVER_S)
        # 3. 기대 sysid의 vehicle_status 표본, 다른 sysid의 표본이 없다
        self._need(lambda: self.raw.status_sysids.get(self.raw.sysid, 0) >= 1, GATE_STATUS_S,
                   "sysid %d의 vehicle_status" % self.raw.sysid, sw.PRECONDITION)
        if not self.raw.last_status_sysid_ok():
            raise sw.SitlFailure(sw.PRECONDITION, "기대 sysid %d 밖의 vehicle_status가 왔다: %r"
                                 % (self.raw.sysid, self.raw.status_sysids))
        # 4. /clock 정렬(use_sim_time 노드 시각 - vehicle_status.timestamp)
        self._need(lambda: len(self.raw.status) >= sj.CLOCK_ALIGN_MIN_SAMPLES + 3, GATE_STATUS_S,
                   "정렬 판정용 vehicle_status 표본", sw.PRECONDITION)
        sw.raise_if(sj.clock_alignment_findings(self.raw.status[-12:]))
        self._need(lambda: self.raw.last_pos() is not None and self.raw.last_landed() is not None, GATE_STATUS_S,
                   "vehicle_local_position, vehicle_land_detected 표본", sw.PRECONDITION)
        sim_s, wall_s = (self.raw.clock_us() - s0) / US, time.monotonic() - w0
        self.gate_info = {"sim_s": sim_s, "wall_s": wall_s}
        self.rtf_start = (self.raw.clock_us(), time.monotonic())
        self.trace.event("gate_ok", sim_s=sim_s, wall_s=round(wall_s, 3))

    def _need(self, pred, timeout_s, what, category):
        try:
            self.waiter.wait_until(pred, timeout_s, what)
        except sw.SitlFailure as e:
            if e.category == sw.TIMEOUT_SIM:
                raise sw.SitlFailure(category, "%s: ROS 시각 %.0f s 안에 준비되지 않았다" % (what, timeout_s)) from e
            raise

    # --- 시나리오 공통 ---

    def require_ground_disarmed(self, scenario):
        """시나리오 사전조건: 지상, DISARMED N회 연속. 어긋나면 그 자리에서 PRECONDITION(앞 시나리오의 잔재를 숨기지 않는다)."""
        t0 = self.raw.now_us()
        self._need(lambda: sj.disarmed_confirmed(self.raw.status, t0) and sj.landed_confirmed(self.raw.landed, t0),
                   GROUND_WAIT_S, "시나리오 %s 사전조건(지상, DISARMED %d회 연속)" % (scenario, sj.N_CONSECUTIVE),
                   sw.PRECONDITION)
        self.trace.event("precondition_ok", scenario=scenario)

    def mark(self, scenario, name, t_us):
        """이정표(ROS 시각 us)를 남긴다. None이면 관측하지 못한 것이다."""
        self.milestones.setdefault(scenario, {})[name] = t_us
        self.trace.event("milestone", scenario=scenario, name=name, at_us=t_us)

    def record_hold_deviation(self, name, dev_m):
        """유지 구간의 최대 편차를 통과한 회에도 trace와 verdict에 남긴다(판정 상수 재검토의 근거)."""
        self.hold_dev[name] = None if dev_m is None else round(dev_m, 3)
        self.trace.event("hold_deviation", name=name, max_dev_m=self.hold_dev[name])

    def z_ref(self):
        """goal 직전의 기준 높이(NED z). z_valid인 마지막 표본."""
        for p in reversed(self.raw.pos):
            if p[6]:
                return p[3]
        raise sw.SitlFailure(sw.PRECONDITION, "z_valid인 vehicle_local_position 표본이 없다")

    def settle_events(self, run, expected=2, timeout_s=5.0):
        """result를 받은 뒤 이 goal의 사건이 expected개 도착하기를 기다린다. 못 채우면 그대로 두고 판정이 EVENT_MISSING으로 가른다."""
        self.waiter.wait_or_timeout(
            lambda: sum(1 for e in self.mission.events if e.goal_id == run.goal_id) >= expected, timeout_s,
            "mission_event 도착")

    def rtf(self):
        if self.rtf_start is None:
            return None
        sim = (self.raw.clock_us() - self.rtf_start[0]) / US
        wall = time.monotonic() - self.rtf_start[1]
        return {"sim_s": round(sim, 3), "wall_s": round(wall, 3), "rtf": round(sim / wall, 4) if wall > 0 else None}

    # --- 정리 ---

    def emergency_cleanup(self):
        """시나리오가 공중에 armed로 남겼으면 Land(source 254/25)를 보낸다. 최선 노력이다.

        Land는 AUTO_LAND 또는 DISARMED가 관측될 때까지 0.5 s(ROS 시각) 주기로 다시 보낸다(채널이 BEST_EFFORT라
        유실될 수 있다). 내려온 뒤에도 armed면 강제가 아닌 disarm을 보낸다. 강제 disarm(param2 21196)은 쓰지 않는다:
        공중에서는 거부되고 Land 뒤 지상에서만 의미가 있다.
        """
        raw = self.raw
        st, ld = raw.last_status(), raw.last_landed()
        if st is None or not st.arming_state == 2 or (ld is not None and ld.landed):
            return
        cmd = None
        try:
            cmd = EmergencyCommand(raw, 254, 25, waiter=self.waiter)
            self.trace.event("emergency_land")
            last = [None]

            def changed():
                s = raw.last_status()
                if s.arming_state != 2 or s.nav_state == 18:
                    return True
                now = raw.now_us()
                if last[0] is None or now - last[0] >= 500_000:
                    cmd.land()
                    last[0] = now
                return False

            self.waiter.wait_until(changed, EMERGENCY_LAND_S, "비상 Land 뒤 AUTO_LAND 또는 DISARMED")
            ok = self.waiter.wait_or_timeout(lambda: raw.last_status().arming_state != 2, EMERGENCY_WAIT_S,
                                             "비상 Land 뒤 DISARMED")
            if not ok:
                self.trace.event("emergency_disarm")
                cmd.disarm()
        except Exception as e:  # noqa: BLE001 정리는 최선 노력이고 원래 실패를 가리지 않는다
            self.trace.event("emergency_failed", error=str(e))
        finally:
            if cmd is not None:
                cmd.close()

    # --- 기록 ---

    def dump_raw_status(self, name, from_us):
        """vehicle_status 원시 표본(KEEP_ALL 기록기)을 JSONL로 남긴다. from_us 이후에 받은 표본만."""
        path = self.out_dir / name
        with open(path, "w", encoding="ascii") as fh:
            for s in self.raw.status:
                if s.recv_ros_us >= from_us:
                    fh.write(json.dumps({
                        "timestamp": s.ts_us, "arming_state": s.arming_state, "nav_state": s.nav_state,
                        "failsafe": s.failsafe, "nav_state_user_intention": s.intention,
                        "recv_ros_us": s.recv_ros_us, "clock_us": s.clock_us}, sort_keys=True) + "\n")
        return path
