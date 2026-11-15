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
준비 상태를 검증만 한다. 준비 검증(gate)이 실패하면 skip이 아니라 오류다(tests/sitl/README.md "실행").

노드 둘이 한 프로세스(한 participant)에 있다: Px4Raw의 노드(PX4 토픽, /clock)와 미션 노드(mission_event 구독,
action client, 1b의 정답 pose와 TargetState 구독). 미션 노드 안에서는 mission_event 구독이 action client보다 먼저
만들어진다(mission_client).

1b(tests/sitl/README.md "시나리오와 판정"): gate는 첫 goal 전에 정답 pose와 표적 발행자, 첫 표본을 확인하고, 표적 발행자의 QoS를
계약 상태 행과 대조하며(다르면 QOS_MISMATCH로 gate 실패), Executor의 target_fresh_age를 판정 상수와 대조한다.
정답 pose, 표적, target_fresh_age의 문제는 gate를 실패시키지 않고 기록해 두었다가 그것이 필요한 비행 시나리오가
시작할 때 실패시킨다(require_truth). 1a 시나리오는 정답 pose를 쓰지 않기 때문이다.
"""
import json
import time

from tests.support import mission_client as mcl
from tests.support import sitl_judge as sj
from tests.support import sitl_missions as sm
from tests.support import sitl_wait as sw
from tests.support.px4_raw import EmergencyCommand, Px4Raw
from tests.support.sitl_flight import Flights
from tests.support.sitl_trace import Trace

US = 1_000_000
CLOCK_DISCOVERY_WALL_S = 15.0    # 프로세스 시작 직후 첫 /clock 수신까지만 쓰는 벽시계 유예(Px4Raw.start가 쓴다)
GATE_SERVER_S = 30.0
GATE_STATUS_S = 20.0
GROUND_WAIT_S = 20.0
EMERGENCY_WAIT_S = 90.0
EMERGENCY_LAND_S = 15.0       # Land 재전송을 이어 가는 상한(AUTO_LAND 또는 DISARMED가 보일 때까지)
GATE_TRUTH_S = 20.0           # 정답 pose와 표적의 발행자, 첫 표본을 기다리는 ROS 시각 상한(gate)
PARAM_WAIT_S = 10.0           # Executor 파라미터 조회
CLEANUP_CANCEL_S = 30.0
CLEANUP_LAND_S = 60.0         # 정리용 [LAND] 결과 대기(LAND 항목 timeout 30 s + disarm 확인)
PARAMETER_DOUBLE = 3          # rcl_interfaces/ParameterType


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
        from tests.support.sim_truth import SimTruth
        self.truth = SimTruth(self.node, self.vehicle_id, [t["id"] for t in stack.targets], self.raw.now_us)
        self.truth_problems = {}  # 이름 -> 설명. 정답 pose, 표적, target_fresh_age(require_truth가 본다)
        self.flights = Flights()
        self.last_run = None      # 마지막으로 보낸 goal(실패 뒤 정리가 끝나지 않은 goal을 취소한다)
        self.r1 = None            # R1 기록(첫 1b 비행에서 한 번)
        self.r2 = []              # GOTO, TRACK_ENTITY 완료 사건의 정답 판정 기록
        self.r4 = []              # 착륙 판정 기록
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
        """goal 전 gate(tests/sitl/README.md "시나리오와 판정")와 /clock 정렬. 어긋나면 SitlFailure."""
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
        clock_align = sj.clock_alignment_stats(self.raw.status[-12:])
        self._need(lambda: self.raw.last_pos() is not None and self.raw.last_landed() is not None, GATE_STATUS_S,
                   "vehicle_local_position, vehicle_land_detected 표본", sw.PRECONDITION)
        truth = self._gate_truth()
        sim_s, wall_s = (self.raw.clock_us() - s0) / US, time.monotonic() - w0
        self.gate_info = {"sim_s": sim_s, "wall_s": wall_s, "truth": truth, "clock_alignment": clock_align}
        self.rtf_start = (self.raw.clock_us(), time.monotonic())
        self.trace.event("gate_ok", sim_s=sim_s, wall_s=round(wall_s, 3), clock_alignment=clock_align)

    def _gate_truth(self):
        """정답 pose, 표적, target_fresh_age를 첫 goal 전에 확인한다. 표적 발행자 QoS가 계약과 다르면 QOS_MISMATCH."""
        from tests.support.sim_truth import qos_contract_findings

        w, t = self.waiter, self.truth
        info = {"oracle_topic": t.oracle_topic, "targets": {}}
        if self.stack.sim_oracle_service is None:
            self.truth_problems["oracle"] = "stack.json에 sim-oracle 서비스가 없다(정답 pose 공급자 없음)"
        elif not w.wait_or_timeout(lambda: t.oracle_publishers() >= 1 and len(t.oracle) > 0, GATE_TRUTH_S,
                                   "정답 pose 발행자와 첫 표본"):
            self.truth_problems["oracle"] = "%s: ROS 시각 %.0f s 안에 발행자 %d, 표본 %d" % (
                t.oracle_topic, GATE_TRUTH_S, t.oracle_publishers(), len(t.oracle))
        info["oracle_samples"] = len(t.oracle)
        for tid, topic in sorted(t.target_topics.items()):
            ok = w.wait_or_timeout(lambda tid=tid: t.target_publishers(tid) >= 1 and len(t.targets[tid]) > 0,
                                   GATE_TRUTH_S, "표적 %s 발행자와 첫 표본" % tid)
            qos = t.target_publisher_qos(tid)
            info["targets"][tid] = {"topic": topic, "samples": len(t.targets[tid]), "publisher_qos": qos}
            if not ok:
                self.truth_problems["target:" + tid] = "%s: ROS 시각 %.0f s 안에 발행자 %d, 표본 %d" % (
                    topic, GATE_TRUTH_S, t.target_publishers(tid), len(t.targets[tid]))
            bad = qos_contract_findings(qos)
            if bad:
                raise sw.SitlFailure(sw.QOS_MISMATCH, "%s 발행자 QoS가 계약 상태 행(RELIABLE, VOLATILE)과 다르다: %s"
                                     % (topic, "; ".join(bad)))
        fresh, why = self._executor_double("target_fresh_age")
        info["target_fresh_age_s"] = fresh
        if fresh is None:
            self.truth_problems["fresh_age"] = "Executor 파라미터 target_fresh_age를 읽지 못했다(%s)" % why
        elif abs(fresh - sj.TARGET_FRESH_AGE_S) > 1e-9:
            self.truth_problems["fresh_age"] = ("Executor target_fresh_age %.3f s가 판정 상수의 전제 %.3f s와 다르다"
                                                "(L = target_fresh_age + tick + 여유. sitl_judge 머리말)"
                                                % (fresh, sj.TARGET_FRESH_AGE_S))
        info["problems"] = dict(self.truth_problems)
        self.trace.event("gate_truth", **info)
        return info

    def _executor_double(self, name):
        """Executor 노드의 double 파라미터 하나를 rcl_interfaces/GetParameters로 읽는다. 반환 (값 또는 None, 사유)."""
        from rcl_interfaces.srv import GetParameters

        node_name = self.vehicle.executor_node
        if not node_name:
            return None, "stack.json에 executor_node가 없다"
        cli = self.node.create_client(GetParameters, node_name + "/get_parameters")
        try:
            if not self.waiter.wait_or_timeout(cli.service_is_ready, PARAM_WAIT_S, "%s/get_parameters" % node_name):
                return None, "서비스가 준비되지 않았다"
            fut = cli.call_async(GetParameters.Request(names=[name]))
            if not self.waiter.wait_or_timeout(fut.done, PARAM_WAIT_S, "파라미터 %s 응답" % name):
                return None, "응답이 없다"
            vals = fut.result().values
            if len(vals) != 1 or vals[0].type != PARAMETER_DOUBLE:
                return None, "double 값이 아니다(%r)" % ([v.type for v in vals],)
            return float(vals[0].double_value), None
        finally:
            self.node.destroy_client(cli)

    def require_truth(self, scenario, target_ids=()):
        """1b 비행 시나리오의 사전조건: 정답 pose(없으면 ORACLE_ABSENT), 쓰는 표적, target_fresh_age 대조."""
        p = self.truth_problems
        if "oracle" in p:
            raise sw.SitlFailure(sw.ORACLE_ABSENT, "시나리오 %s: %s" % (scenario, p["oracle"]))
        for tid in target_ids:
            if tid not in self.truth.targets:
                raise sw.SitlFailure(sw.PRECONDITION, "시나리오 %s의 표적 %s가 stack.json targets에 없다" % (scenario, tid))
            if "target:" + tid in p:
                raise sw.SitlFailure(sw.NO_PUBLISHER, "시나리오 %s: %s" % (scenario, p["target:" + tid]))
        if target_ids and "fresh_age" in p:
            raise sw.SitlFailure(sw.PRECONDITION, "시나리오 %s: %s" % (scenario, p["fresh_age"]))

    def require_air_hold(self, scenario):
        """공중 시작의 사전조건: ARMED, landed false, AUTO_LOITER(Hold). 어긋나면 PRECONDITION."""
        st, ld = self.raw.last_status(), self.raw.last_landed()
        ok = (st is not None and st.arming_state == 2 and st.nav_state == 4 and ld is not None and not ld.landed)
        if not ok:
            raise sw.SitlFailure(sw.PRECONDITION, "시나리오 %s 사전조건(공중 Hold) 위반: status %s, landed %s" % (
                scenario, None if st is None else (st.arming_state, st.nav_state),
                None if ld is None else ld.landed))
        self.trace.event("precondition_ok", scenario=scenario, air=True)

    def record_r1(self):
        """R1(EKF 원점과 기대 스폰 GPS의 차)을 부팅마다 한 번 남긴다. 기록 전용(recorded_only)."""
        if self.r1 is not None:
            return
        ref, exp = self.raw.pos_ref, self.vehicle.expect_gps
        if ref is None or exp is None or not (ref[4] and ref[5]):
            self.trace.event("r1_unavailable", pos_ref=ref, expect_gps=exp)
            return
        self.r1 = dict(sj.r1_record(ref[1], ref[2], ref[3], exp), ref_timestamp=ref[6], status="recorded_only")
        self.trace.event("r1", **self.r1)

    def recorded_only(self):
        """verdict.json의 recorded_only 묶음(R1, R3, R2와 R4 요약). 판정에 쓰지 않는다."""
        t = self.truth
        ref = self.raw.pos_ref
        r1 = dict(self.r1) if self.r1 else None
        if r1 is not None and ref is not None and ref[6] != r1["ref_timestamp"]:
            r1["ref_timestamp_at_end"] = ref[6]          # EKF 원점이 실행 중 바뀌었다
        lag = [(s.recv_ros_us - s.ts_us) / US for s in self.raw.status]
        return {
            "R1": r1,
            "R3": {
                "target_age_s": {tid: sj.summary([(x.recv_us - x.stamp_us) / US for x in xs])
                                 for tid, xs in t.targets.items()},
                "target_interval_s": {tid: sj.summary([(b.stamp_us - a.stamp_us) / US for a, b in zip(xs, xs[1:])])
                                      for tid, xs in t.targets.items()},
                "clock_sim_step_s": sj.summary([d / US for d in t.clock_sim_steps_us]),
                "clock_wall_gap_s": sj.summary(t.clock_wall_gaps_s),
                "now_minus_status_timestamp_s": sj.summary(lag),
                "stale_ticks": [{"scenario": r["scenario"], "index": r["index"], **r["stale_ticks"]}
                                for r in self.r2 if "stale_ticks" in r],
                "tracking": [{"scenario": r["scenario"], "index": r["index"], **r.get("tracking", {})}
                             for r in self.r2 if r["type"] == "TRACK_ENTITY"],
                "status": "recorded_only"},
            "R2": [{k: r.get(k) for k in ("scenario", "index", "type", "d3", "d_h", "d_v", "s", "s_track", "gap_s",
                                          "t_f_exact", "speed_h_mps")} for r in self.r2],
            "R4": [{k: r.get(k) for k in ("scenario", "r4_m", "dz", "r_home_status")} for r in self.r4],
            "oracle": {"samples": len(t.oracle), "bad_frame": t.oracle_bad_frame,
                       "interval_s": sj.summary([(b.stamp_us - a.stamp_us) / US
                                                 for a, b in zip(t.oracle, t.oracle[1:])])},
            "target_bad_samples": dict(t.target_bad),
        }

    def cleanup_land(self):
        """비행 시나리오 실패 뒤의 정리(tests/sitl/README.md "시나리오와 판정"). 끝나지 않은 goal은 취소하고, 기체가 공중이면 정리용 [LAND] 미션을
        한 번 보낸다. 결과는 판정에 넣지 않는다. 그 뒤 비상 정리(최선 노력. 이미 지상이면 아무것도 하지 않는다)."""
        run = self.last_run
        try:
            if run is not None and run.accepted and run.handle is not None and run.result is None:
                self.mission.cancel(self.waiter, run)
                self.waiter.wait_or_timeout(lambda: run.result is not None, CLEANUP_CANCEL_S, "정리 전 취소 결과")
            st, ld = self.raw.last_status(), self.raw.last_landed()
            if st is not None and st.arming_state == 2 and not (ld is not None and ld.landed):
                r = self.mission.send_goal(self.waiter, self.vehicle_id, "cleanup-land", [sm.land_item()])
                if r.accepted:
                    self.waiter.wait_or_timeout(lambda: r.result is not None, CLEANUP_LAND_S, "정리 [LAND] 결과")
                self.trace.event("cleanup_land", accepted=r.accepted,
                                 result=None if r.result is None else [r.result.status, r.result.reason])
        except Exception as e:  # noqa: BLE001 정리는 최선 노력이고 원래 실패를 가리지 않는다
            self.trace.event("cleanup_land_failed", error=repr(e))
        finally:
            self.emergency_cleanup()

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
