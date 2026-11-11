#!/usr/bin/env python3
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

"""PX4 재실측 (2), (3), (5)와 ARMED 표본 기록(시나리오 A 대응)의 측정 실행기.

ros-ws runner 컨테이너 안에서 돈다(rclpy, px4_msgs 필요). 호스트에서는 run_measure.sh를 쓴다.
Executor 노드 없이 PX4에 직접 명령을 보낸다. 정리 분기의 선택과 종료는
tests/support/measure_judge.py의 CleanupModel이 decisions.md M3, M5, M6의 규칙대로 흉내 낸다.
판정 기준과 정본 문장은 measure_judge.py 머리와 decisions.md의 "넘김 목록" px4-engineer 행이다.

  measure.py --item item2|item3|item5|armed [--attempts N] [--out-dir DIR]

항목
  item2  (2) 지상 setpoint 발행 중의 Hold. 시도마다 행 둘: 2a(Hold 확인과 정리 소요), 2b(Hold를 확인하고
         발행을 멈춘 뒤 landed가 true인 상태에서 disarm).
  item3  (3) 이륙 직후의 지상 setpoint와 disarm. trigger는 첫 ARMED 표본이고, 그 시점 landed가 true인
         시도만 창 안이다(아니면 WINDOW_MISSED).
  item5  (5) arm 전송 직후(0-0.2 s sim)의 취소 경쟁. 주입 지연은 --delays를 시도 수만큼 돌려 쓴다.
  armed  시나리오 A 대응. arm -> ARMED 3회 -> TAKEOFF 시작 구간의 모든 vehicle_status 표본 기록. 이어서
         이륙, NAV_LAND로 착륙. 실제 시나리오 A(Executor 경유)는 같은 Px4Raw와 judge를 쓴다.

기록(--out-dir, 기본 <실행 디렉터리>/measure/)
  measure_<item>.jsonl     시도마다 한 줄. 실패한 시도를 빼지 않고 재시도하지 않는다
  raw_<item>.jsonl         시도마다 vehicle_status, vehicle_land_detected, 위치, ack, 전송 원시 표본
  summary_<item>.txt       머리에 통과 기준(실행 전에 기록), 아래에 결과
  distribution_<item>.json timestamp - Px4Timestamp 등 부호 있는 분포 (재실측 (5)의 요구)

종료 코드: 0 모든 시도 통과이고 시도 수 충분, 1 FAIL이 있음, 2 그 밖(시도 수 부족, PRECONDITION,
WINDOW_MISSED, 인프라). 타임아웃은 모두 sim 시간(/clock)이다. 벽시계는 /clock이 멈췄는지 보는 데만 쓴다.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import rclpy  # noqa: E402

from px4_msgs.msg import VehicleStatus  # noqa: E402

from tests.support import measure_judge as mj  # noqa: E402
from tests.support import stack as stk  # noqa: E402
from tests.support.px4_raw import ClockStalled, Px4Raw  # noqa: E402

US = mj.US

ITEMS = ("item2", "item3", "item5", "armed")
DEFAULT_ATTEMPTS = {"item2": 3, "item3": 3, "item5": 10, "armed": 10}
MIN_ATTEMPTS = dict(DEFAULT_ATTEMPTS)

CRITERIA = {
    "item2": [
        "(2a) 지상 setpoint(z +0.5 m) 발행 중 Hold 전송, AUTO_LOITER 표본을 처음 관측한 순간 발행 중단: "
        "Hold를 관측(3회 모두), 정리 총 소요 9 s 미만. OFFBOARD가 아닌 ARMED 표본은 기록만 한다.",
        "(2b) Hold 확인 뒤 발행을 멈추고 landed가 true가 되면 강제가 아닌 disarm: DISARMED 3회 확인, "
        "고도 변화 0.2 m 이하. 관찰은 --observe-s(기본 60) sim 초. landed가 true가 되지 않으면 FAIL.",
        "시도 3회 모두 위 기준을 만족해야 통과한다.",
    ],
    "item3": [
        "TAKEOFF 목표점으로 arm한 뒤 첫 ARMED 표본에서 landed가 true인 시도만 창 안이다(아니면 WINDOW_MISSED, "
        "통과로 세지 않음). 그 시점에 지상 setpoint로 바꾸고 disarm.",
        "mode_confirm_timeout(3 s) 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만, "
        "OFFBOARD가 아닌 ARMED 표본 0개, 끝난 뒤 지상에 armed로 남지 않음.",
        "시도 3회 모두 통과해야 통과한다.",
    ],
    "item5": [
        "arm 전송 뒤 0-0.2 s(sim)에 지상 setpoint와 disarm. 지연은 --delays를 돌려 쓴다.",
        "mode_confirm_timeout(3 s) 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만, "
        "OFFBOARD가 아닌 ARMED 표본 0개, 관찰(--tail-s)이 끝날 때까지 지상에 armed로 남지 않음.",
        "시도 10회 이상 모두 통과해야 통과한다(10회 중 0건은 실패율 95% 상한 약 26%).",
    ],
    "armed": [
        "arm 전송부터 ARMED 3회 확인(= TAKEOFF 시작)까지의 모든 vehicle_status 표본에서 "
        "OFFBOARD가 아닌 ARMED 표본이 0개.",
        "ARMED 3회 확인까지 간 시도가 10회 이상이고 그 전부에서 0개여야 통과한다. 한 건이라도 나오면 "
        "즉시 architect에게 올린다. 이것은 통계적 증명이 아니라 메커니즘의 반증 확인이다.",
    ],
}


class Precondition(Exception):
    """시도를 시작할 상태를 만들지 못했다(verdict PRECONDITION)."""


# ---------------------------------------------------------------------------
# 구동


class Rig:
    """Px4Raw 위의 제어 루프. 발행(20 Hz sim)과 대기를 한 곳에서 한다."""

    def __init__(self, raw):
        self.raw = raw
        self.sp = None           # (x, y, z, yaw) NED. None이면 발행하지 않는다
        self._last_pub = 0
        self.pub_count = 0

    def pump(self):
        self.raw.guard()
        now = self.raw.now_us()
        if self.sp is not None and now - self._last_pub >= 50_000:
            self.raw.publish_position(*self.sp)
            self._last_pub = now
            self.pub_count += 1
        time.sleep(0.002)

    def wait(self, pred, timeout_s):
        """pred가 참이 될 때까지 sim 시간으로 timeout_s 기다린다. 참이면 True."""
        start = self.raw.now_us()
        while True:
            if pred():
                return True
            if self.raw.now_us() - start >= timeout_s * US:
                return False
            self.pump()

    def sleep_sim(self, s):
        self.wait(lambda: False, s)

    def set_sp(self, sp):
        self.sp = sp
        if sp is not None:
            self.raw.publish_position(*sp)
            self._last_pub = self.raw.now_us()
            self.pub_count += 1

    def send(self, kind):
        return self.raw.send(kind)


def send_until(rig, kind, confirm, timeout_s, resend_s=mj.COMMAND_RESEND_S, stop_pred=None,
               idx=None):
    """kind를 resend_s마다 보내며 confirm(ConsecutiveConfirm)이 찰 때까지 기다린다.

    첫 전송 값으로 confirm의 '전송 뒤에 받은' 기준을 정한다. (성공 여부, 첫 전송(recv, ts))를 돌려준다.
    """
    raw = rig.raw
    first = None
    last_send = None
    start = raw.now_us()
    i = len(raw.status) if idx is None else idx
    while True:
        now = raw.now_us()
        if last_send is None or now - last_send >= resend_s * US:
            recv, ts = rig.send(kind)
            if first is None:
                first = (recv, ts)
                confirm.set_floor(ts, recv)
            last_send = now
        for s in raw.status[i:]:
            if confirm.feed(s):
                return True, first
        i = len(raw.status)
        if stop_pred is not None and stop_pred():
            return False, first
        if now - start >= timeout_s * US:
            return False, first
        rig.pump()


def reset_vehicle(rig, timeout_s=60.0):
    """다음 시도의 시작 상태(DISARMED, landed true)를 만든다. 못 만들면 Precondition."""
    raw = rig.raw
    rig.sp = None
    last_land = None

    def ready():
        st, ld = raw.last_status(), raw.last_landed()
        return (st is not None and ld is not None and mj.is_disarmed(st) and ld.landed
                and st.recv_ros_us > t_begin)

    t_begin = raw.now_us()
    start = t_begin
    while True:
        if ready():
            return
        st = raw.last_status()
        now = raw.now_us()
        if st is not None and mj.is_armed(st) and (last_land is None or now - last_land >= 2 * US):
            rig.send("land")
            last_land = now
        if now - start >= timeout_s * US:
            raise Precondition("정리 후 DISARMED + landed true를 %.0f s 안에 만들지 못함" % timeout_s)
        rig.pump()


def prepare(rig, args):
    """시도 전 상태: 지상 disarm, 위치 유효, Offboard 확인. 지상 기준(ref)을 돌려준다."""
    raw = rig.raw
    reset_vehicle(rig)
    rig.sleep_sim(args.settle_s)
    if not rig.wait(lambda: raw.last_pos() is not None and raw.last_pos()[5] and raw.last_pos()[6]
                    and raw.last_pos()[0] > raw.now_us() - 500_000, 30.0):
        raise Precondition("vehicle_local_position이 유효하지 않거나 오래됨")
    p = raw.last_pos()
    ref = {"x": p[1], "y": p[2], "z": p[3], "heading": p[4]}
    rig.pub_count = 0
    rig.set_sp((ref["x"], ref["y"], ref["z"] - args.takeoff_alt, ref["heading"]))
    if not rig.wait(lambda: rig.pub_count >= 10, 5.0):
        raise Precondition("setpoint 발행 10회를 채우지 못함")
    conf = mj.ConsecutiveConfirm(lambda s: s.nav_state == mj.NAV_STATE_OFFBOARD)
    ok, _ = send_until(rig, "offboard", conf, mj.MODE_CONFIRM_TIMEOUT_S)
    if not ok:
        raise Precondition("OFFBOARD 3회 미확인")
    return ref


def ground_setpoint(raw):
    """지상 setpoint: 그 시점 vehicle_local_position의 x, y, z에서 z만 +0.5 m(NED 아래), yaw는 heading."""
    p = raw.last_pos()
    return (p[1], p[2], p[3] + mj.GROUND_SETPOINT_DZ_M, p[4])


def run_cleanup(rig, start_us):
    """지상 setpoint로 바꾸고 CleanupModel로 정리한다. 끝난 모델을 돌려준다."""
    raw = rig.raw
    rig.set_sp(ground_setpoint(raw))
    model = mj.CleanupModel(start_us)
    i = len(raw.status)
    while not model.done:
        for s in raw.status[i:]:
            model.on_status(s)
        i = len(raw.status)
        ld = raw.last_landed()
        for kind in model.step(raw.now_us(), True if ld is None else ld.landed):
            recv, ts = rig.send(kind)
            model.note_sent(kind, recv, ts)
        if model.done:
            break
        rig.pump()
    rig.sp = None      # 끝나면 발행을 멈춘다
    return model


def observe_tail(rig, end_us, tail_s):
    """정리가 끝난 뒤 tail_s(sim) 동안 관찰하고 (다시 ARMED가 나왔는가, 마지막이 DISARMED인가)를 돌려준다."""
    raw = rig.raw
    rig.sleep_sim(tail_s)
    after = [s for s in raw.status if s.recv_ros_us > end_us]
    st = raw.last_status()
    return any(mj.is_armed(s) for s in after), st is not None and mj.is_disarmed(st)


def climb_m(raw, ref_z, from_us, to_us):
    zs = [p[3] for p in raw.pos if from_us <= p[0] <= to_us]
    return None if not zs else max(0.0, ref_z - min(zs))


def armed_facts(raw, idx_s, arm_recv, end_us, cutoff_us=None):
    """arm 전송부터 (ARMED 3회 확인 또는 end_us 또는 cutoff_us) 중 가장 이른 시각까지의 ARMED 표본을 센다."""
    samples = raw.status[idx_s:]
    armed3 = mj.armed_confirm_sample(samples, arm_recv)
    to = end_us
    if cutoff_us is not None:
        to = min(to, cutoff_us)
    reached = armed3 is not None and armed3.recv_ros_us <= end_us
    if reached:
        to = min(to, armed3.recv_ros_us)
    n_armed, bad = mj.armed_non_offboard(samples, arm_recv, to)
    return {
        "armed3_reached": reached,
        "armed3_ros_us": armed3.recv_ros_us if reached else None,
        "armed_window_ros_us": [arm_recv, to],
        "armed_samples": n_armed,
        "armed_non_offboard": len(bad),
        "armed_non_offboard_samples": [
            {"ts_us": b.ts_us, "recv_ros_us": b.recv_ros_us, "nav_state": b.nav_state,
             "failsafe": b.failsafe, "intention": b.intention} for b in bad],
    }


def cleanup_facts(raw, model, arm_recv, ref_z, tail):
    seq = mj.branch_sequence(model.branch_log)
    lt = mj.landed_transitions(raw.landed, arm_recv, model.end_us)
    lt_cleanup = mj.landed_transitions(raw.landed, model.start_us, model.end_us)
    armed_after, final_disarmed = tail
    return {
        "end_reason": model.end_reason,
        "cleanup_start_ros_us": model.start_us,
        "cleanup_end_ros_us": model.end_us,
        "cleanup_total_s": model.elapsed_s,
        "branch_sequence": seq["sequence"],
        "branch_transitions": seq["transitions"],
        "branch_log": [[t, b] for t, b in model.branch_log],
        "landed_transitions_arm_to_end": lt,
        "landed_transitions_cleanup": lt_cleanup,
        "first_disarm_send": model.first_send["disarm"],
        "first_hold_send": model.first_send["hold"],
        "climb_m": climb_m(raw, ref_z, arm_recv, model.end_us + 3 * US),
        "armed_after_end": armed_after,
        "final_disarmed": final_disarmed,
    }


# ---------------------------------------------------------------------------
# 항목별 시도


def attempt_item5(rig, args, a):
    raw = rig.raw
    delays = args.delays
    delay = delays[a % len(delays)]
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    rig.sleep_sim(delay)
    cancel_us = raw.now_us()
    ld = raw.last_landed()
    model = run_cleanup(rig, cancel_us)
    tail = observe_tail(rig, model.end_us, args.tail_s)
    f = cleanup_facts(raw, model, arm_recv, ref["z"], tail)
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us))
    f.update({"arm_send": [arm_recv, arm_ts], "landed_at_cancel": None if ld is None else ld.landed,
              "arm_ack": [x["result"] for x in raw.acks_for(400, arm_recv)][:3]})
    inj = {"item": "5", "delay_s": delay, "trigger": "arm 전송 + sim 지연", "arm_send_ros_us": arm_recv}
    return [("5", inj, f)], idx_s


def attempt_item3(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    first = {}

    def first_armed():
        for s in raw.status[idx_s:]:
            if mj.is_armed(s) and s.recv_ros_us > arm_recv:
                first["s"] = s
                first["landed"] = raw.last_landed()
                first["z"] = raw.last_pos()
                return True
        return False

    last = arm_recv
    t_start = raw.now_us()
    while not first_armed():
        now = raw.now_us()
        if now - last >= mj.COMMAND_RESEND_S * US:
            rig.send("arm")
            last = now
        if now - t_start >= 5 * US:       # arm_timeout
            raise Precondition("ARMED 표본을 5 s 안에 보지 못함(arm ack %s)"
                               % [x["result"] for x in raw.acks_for(400, arm_recv)][:5])
        rig.pump()
    cancel_us = raw.now_us()
    landed_at_cancel = None if first["landed"] is None else first["landed"].landed
    model = run_cleanup(rig, cancel_us)
    tail = observe_tail(rig, model.end_us, args.tail_s)
    f = cleanup_facts(raw, model, arm_recv, ref["z"], tail)
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us))
    height = None if first["z"] is None else ref["z"] - first["z"][3]
    f.update({"arm_send": [arm_recv, arm_ts], "landed_at_cancel": landed_at_cancel,
              "height_at_cancel_m": height,
              "sim_s_first_armed_after_arm": (first["s"].recv_ros_us - arm_recv) / US,
              "arm_ack": [x["result"] for x in raw.acks_for(400, arm_recv)][:3]})
    inj = {"item": "3", "trigger": "첫 ARMED 표본(그 시점 landed 최신값이 true인 시도만 창 안)",
           "arm_send_ros_us": arm_recv}
    return [("3", inj, f)], idx_s


def attempt_item2(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    last = arm_recv
    t_start = raw.now_us()
    seen = {}

    def armed():
        for s in raw.status[idx_s:]:
            if mj.is_armed(s) and s.recv_ros_us > arm_recv:
                seen["armed"] = s
                return True
        return False

    while not armed():
        now = raw.now_us()
        if now - last >= mj.COMMAND_RESEND_S * US:
            rig.send("arm")
            last = now
        if now - t_start >= 5 * US:
            raise Precondition("ARMED 표본을 5 s 안에 보지 못함")
        rig.pump()
    first_armed_us = seen["armed"].recv_ros_us

    def landed_false_after_armed():
        return any((not x.landed) and x.recv_ros_us >= first_armed_us for x in raw.landed)

    if not rig.wait(landed_false_after_armed, 10.0):
        raise Precondition("ARMED 뒤 10 s 안에 landed가 false가 되지 않음")
    cancel_us = raw.now_us()
    p = raw.last_pos()
    height = ref["z"] - p[3]
    model = run_cleanup(rig, cancel_us)       # landed false -> A 분기: 지상 setpoint 유지 + Hold
    hold_end = model.end_us
    f = cleanup_facts(raw, model, arm_recv, ref["z"], (False, False))
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us, cutoff_us=cancel_us))
    f.update({"arm_send": [arm_recv, arm_ts], "height_at_cancel_m": height,
              "sim_s_first_armed_to_cancel": (cancel_us - first_armed_us) / US})
    inj_a = {"item": "2a", "trigger": "첫 ARMED 뒤 첫 landed==false 표본", "arm_send_ros_us": arm_recv}
    rows = [("2a", inj_a, f)]

    # 2b: Hold 확인 뒤 발행 없음. landed가 true가 되는 표본에서 강제가 아닌 disarm
    g = {"hold_end_ros_us": hold_end}
    if model.end_reason != "HOLD":
        g.update({"landed_true_seen": False, "disarm_confirmed": False, "dz_max_m": None,
                  "skipped": "2a가 Hold로 끝나지 않아 2b를 하지 않음(end_reason=%s)" % model.end_reason})
        return rows + [("2b", {"item": "2b", "trigger": "해당 없음"}, g)], idx_s
    z_hold = raw.last_pos()[3]
    seen_true = {}

    def landed_true():
        # Hold를 확인한 시점에 이미 true이면 바로 만족한다(최신 표본 기준)
        x = raw.last_landed()
        if x is not None and x.landed:
            seen_true["l"] = x
            return True
        return False

    got = rig.wait(landed_true, args.observe_s)
    lt = mj.landed_transitions(raw.landed, hold_end, raw.now_us())
    g.update({"landed_true_seen": got, "observe_s": args.observe_s,
              "landed_transitions_observe": lt})
    if got:
        t_true = seen_true["l"].recv_ros_us
        conf = mj.ConsecutiveConfirm(mj.is_disarmed)
        ok, first = send_until(rig, "disarm", conf, mj.MODE_CONFIRM_TIMEOUT_S)
        zs = [q[3] for q in raw.pos if q[0] >= hold_end]
        g.update({"landed_true_ros_us": t_true, "landed_true_after_hold_s": (t_true - hold_end) / US, "disarm_confirmed": ok,
                  "first_disarm_send": first,
                  "disarm_ack": [x["result"] for x in raw.acks_for(400, first[0])][:3],
                  "dz_max_m": max(abs(z - z_hold) for z in zs) if zs else None})
    else:
        g.update({"disarm_confirmed": False, "dz_max_m": None})
    return rows + [("2b", {"item": "2b", "trigger": "Hold 확인 뒤 landed 최신 표본이 true",
                           "hold_end_ros_us": hold_end}, g)], idx_s


def attempt_armed(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    conf = mj.ConsecutiveConfirm(mj.is_armed)
    ok, first = send_until(rig, "arm", conf, 5.0, idx=idx_s)
    arm_recv, arm_ts = first
    end_us = conf.confirmed_at.recv_ros_us if ok else raw.now_us()
    f = armed_facts(raw, idx_s, arm_recv, end_us)
    f.update({"arm_send": [arm_recv, arm_ts],
              "arm_ack": [x["result"] for x in raw.acks_for(400, arm_recv)][:3]})
    if not ok:
        raise_arm = Precondition("ARMED 3회 확인을 5 s 안에 채우지 못함(arm ack %s)" % f["arm_ack"])
        raise_arm.facts = f
        raise raise_arm
    # TAKEOFF 시작: 목표점 발행을 이어 가며 고도를 기다린다
    f["takeoff_start_ros_us"] = end_us
    target_z = ref["z"] - args.takeoff_alt + 0.5
    reached = rig.wait(lambda: raw.last_pos()[3] <= target_z, 30.0)
    f["reached_altitude"] = reached
    f["flight_armed_non_offboard_info"] = len(
        mj.armed_non_offboard(raw.status[idx_s:], end_us + 1, raw.now_us())[1])
    # LAND: NAV_LAND를 보내 AUTO_LAND를 확인하고 발행을 멈춘 뒤 DISARMED를 기다린다
    land_conf = mj.ConsecutiveConfirm(lambda s: s.nav_state == mj.NAV_STATE_AUTO_LAND, n=1)
    lok, _ = send_until(rig, "land", land_conf, mj.MODE_CONFIRM_TIMEOUT_S)
    rig.sp = None
    f["land_confirmed"] = lok
    dis = mj.ConsecutiveConfirm(mj.is_disarmed)
    t0 = raw.now_us()
    i = len(raw.status)

    def disarmed():
        nonlocal i
        for s in raw.status[i:]:
            if dis.feed(s):
                return True
        i = len(raw.status)
        return False

    f["landing_disarmed"] = rig.wait(disarmed, 90.0)
    f["landing_s"] = (raw.now_us() - t0) / US
    inj = {"item": "armed", "trigger": "arm 전송 -> ARMED 3회 확인(= TAKEOFF 시작)",
           "arm_send_ros_us": arm_recv}
    return [("armed", inj, f)], idx_s


ATTEMPTS = {"item2": attempt_item2, "item3": attempt_item3, "item5": attempt_item5,
            "armed": attempt_armed}


# ---------------------------------------------------------------------------
# 기록


def jwrite(fh, obj):
    fh.write(json.dumps(obj, ensure_ascii=True, sort_keys=True) + "\n")
    fh.flush()
    os.fsync(fh.fileno())


def dump_raw(fh, raw, attempt, i_s, i_l, i_p, i_a, i_c):
    for s in raw.status[i_s:]:
        jwrite(fh, {"attempt": attempt, "t": "status", "ts_us": s.ts_us, "recv_ros_us": s.recv_ros_us,
                    "clock_us": s.clock_us, "arming_state": s.arming_state, "nav_state": s.nav_state,
                    "failsafe": s.failsafe, "intention": s.intention})
    for s in raw.landed[i_l:]:
        jwrite(fh, {"attempt": attempt, "t": "landed", "ts_us": s.ts_us,
                    "recv_ros_us": s.recv_ros_us, "landed": s.landed})
    for p in raw.pos[i_p:]:
        jwrite(fh, {"attempt": attempt, "t": "pos", "recv_ros_us": p[0], "x": p[1], "y": p[2],
                    "z": p[3], "heading": p[4], "xy_valid": p[5], "z_valid": p[6]})
    for x in raw.acks[i_a:]:
        jwrite(fh, dict(x, attempt=attempt, t="ack"))
    for x in raw.sends[i_c:]:
        jwrite(fh, dict(x, attempt=attempt, t="send"))


def newest_ulog(ulog_dir):
    files = sorted(Path(ulog_dir).glob("**/*.ulg"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_meta(st):
    gen = st.raw["generator"]
    commit = os.environ.get("IDSIM_GIT_COMMIT") or gen.get("git_commit")
    dirty_env = os.environ.get("IDSIM_GIT_DIRTY")
    dirty = (dirty_env == "true") if dirty_env in ("true", "false") else gen.get("git_dirty")
    keys = os.environ.get("IDSIM_IMAGE_KEYS")
    return {
        "run_id": st.run_id, "commit": commit, "dirty": dirty, "images": st.raw["images"],
        "image_keys": json.loads(keys) if keys else None,
        "stack_json": str(st.path),
    }


def exit_code_of(verdict):
    return {"PASS": 0, "FAIL": 1}.get(verdict, 2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--item", required=True, choices=ITEMS)
    ap.add_argument("--attempts", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--takeoff-alt", type=float, default=5.0, help="이륙 목표 높이(m)")
    ap.add_argument("--settle-s", type=float, default=3.0, help="시도 전 안정화(sim 초)")
    ap.add_argument("--tail-s", type=float, default=3.0, help="정리 뒤 관찰(sim 초)")
    ap.add_argument("--observe-s", type=float, default=60.0, help="2b 관찰(sim 초)")
    ap.add_argument("--delays", default="0,0.05,0.1,0.15,0.2", help="item5 주입 지연 목록(sim 초)")
    args = ap.parse_args(argv)
    args.delays = [float(x) for x in args.delays.split(",")]
    if args.attempts is None:
        args.attempts = DEFAULT_ATTEMPTS[args.item]
    st = stk.load_from_env()
    veh = st.vehicles[0]
    out = Path(args.out_dir) if args.out_dir else st.dir / "measure"
    out.mkdir(parents=True, exist_ok=True)
    meta = run_meta(st)
    item = args.item

    # px4_msgs 상수가 judge의 값과 같은지 대조한다
    assert VehicleStatus.ARMING_STATE_ARMED == mj.ARMING_STATE_ARMED
    assert VehicleStatus.ARMING_STATE_DISARMED == mj.ARMING_STATE_DISARMED
    assert VehicleStatus.NAVIGATION_STATE_OFFBOARD == mj.NAV_STATE_OFFBOARD
    assert VehicleStatus.NAVIGATION_STATE_AUTO_LOITER == mj.NAV_STATE_AUTO_LOITER
    assert VehicleStatus.NAVIGATION_STATE_AUTO_LAND == mj.NAV_STATE_AUTO_LAND

    # 통과 기준을 실행 전에 요약 머리에 적는다
    summary = out / ("summary_%s.txt" % item)
    with open(summary, "w") as fh:
        fh.write("# 재실측 %s 요약\n" % item)
        fh.write("run_id %s\ncommit %s dirty %s\nimages %s\nimage_keys %s\n"
                 % (meta["run_id"], meta["commit"], meta["dirty"], meta["images"], meta["image_keys"]))
        fh.write("\n## 통과 기준 (실행 전에 기록)\n")
        for line in CRITERIA[item]:
            fh.write("- %s\n" % line)
        fh.write("- 정리 총 소요 9 s 미만(상한 12 s에 여유 3 s). 넘으면 상한을 올리지 않고 architect에게 올린다.\n")
        fh.write("- 계획한 시도 수 %d (기준의 최소 %d). 실패한 시도를 빼지 않고 재시도하지 않는다.\n"
                 % (args.attempts, MIN_ATTEMPTS[item]))
        fh.write("- 판정 코드: tests/support/measure_judge.py. 정본: decisions.md 넘김 목록의 px4-engineer 행.\n")
        fh.write("- 이 측정은 Executor 없이 PX4에 직접 명령을 보낸다. 정리 모델은 measure_judge.CleanupModel.\n")

    rclpy.init()
    raw = Px4Raw(veh.px4_ns, veh.sysid)
    rows_all = []
    status = 0
    try:
        raw.start()
        rig = Rig(raw)
        # /clock이 오기 전의 노드 시각은 0이다. 이 첫 대기만 벽시계로 잰다(sim 시간이 아직 없다).
        t_wall = time.monotonic()
        while not (raw.clock_us() > 0 and raw.now_us() > 0 and raw.last_status() is not None
                   and raw.last_landed() is not None and raw.last_pos() is not None):
            if time.monotonic() - t_wall > 60.0:
                raise RuntimeError("CLOCK_ABSENT 또는 PRECONDITION: /clock 또는 PX4 표본을 벽시계 60 s 안에 받지 못함")
            time.sleep(0.05)
        ulog_dir = st.ulog_path(veh)
        repo_root = Path(__file__).resolve().parents[3]
        with open(out / ("measure_%s.jsonl" % item), "w") as mfh, \
                open(out / ("raw_%s.jsonl" % item), "w") as rfh:
            for a in range(args.attempts):
                wall0 = time.monotonic()
                ros0 = raw.now_us()
                idx = (len(raw.status), len(raw.landed), len(raw.pos), len(raw.acks), len(raw.sends))
                facts_rows = []
                err = None
                try:
                    facts_rows, idx_s = ATTEMPTS[item](rig, args, a)
                except Precondition as e:
                    err = ("PRECONDITION", str(e), getattr(e, "facts", None))
                except ClockStalled as e:
                    err = ("CLOCK_STALLED", str(e), None)
                ros1 = raw.now_us()
                rig.sp = None
                ulog = newest_ulog(ulog_dir)
                base = {
                    "run_id": meta["run_id"], "commit": meta["commit"], "dirty": meta["dirty"],
                    "images": meta["images"], "image_keys": meta["image_keys"], "attempt": a + 1,
                    "ros_start_us": ros0, "ros_end_us": ros1, "ros_elapsed_s": (ros1 - ros0) / US,
                    "wall_elapsed_s": round(time.monotonic() - wall0, 3),
                    "ulog": None if ulog is None else os.path.relpath(ulog, repo_root),
                }
                if err is not None:
                    row = dict(base, item=item, injection=None, verdict=err[0], result=err[0],
                               reasons=[err[1]], facts=err[2], exit_code=exit_code_of(err[0]))
                    jwrite(mfh, row)
                    rows_all.append(row)
                    status = max(status, 2)
                    if err[0] == "CLOCK_STALLED":
                        dump_raw(rfh, raw, a + 1, *idx)
                        break
                else:
                    for sub, inj, facts in facts_rows:
                        v = mj.judge_attempt(sub, facts)
                        row = dict(base, item=sub, injection=inj, verdict=v.verdict, result=v.verdict,
                                   reasons=v.reasons, facts=facts, exit_code=exit_code_of(v.verdict),
                                   armed3_reached=facts.get("armed3_reached", False),
                                   armed_non_offboard=facts.get("armed_non_offboard", 0))
                        jwrite(mfh, row)
                        rows_all.append(row)
                dump_raw(rfh, raw, a + 1, *idx)
                print("attempt %d/%d %s" % (a + 1, args.attempts,
                                            [(r["item"], r["verdict"]) for r in rows_all
                                             if r["attempt"] == a + 1]), flush=True)
    finally:
        raw.close()
        rclpy.shutdown()

    # 분포(모든 vehicle_status 표본)와 요약
    dist = mj.status_offsets(raw.status)
    sends = {k: [(x["recv_ros_us"], x["ts_us"]) for x in raw.sends if x["kind"] == k]
             for k in ("arm", "disarm", "hold", "offboard", "land")}
    dist["ts_minus_px4timestamp_at_send"] = {
        k: {kk: vv for kk, vv in mj.deltas_vs_sends(raw.status, v).items() if kk != "values_us"}
        for k, v in sends.items()}
    dist["description"] = ("ts_minus_recv_ros_us, ts_minus_clock_us: 모든 vehicle_status 표본의 "
                           "PX4 timestamp에서 받은 ROS 시각, 같은 시점의 /clock을 뺀 값(us). "
                           "ts_minus_px4timestamp_at_send: 명령 전송 뒤 처음 받은 표본의 timestamp - Px4Timestamp(us).")
    with open(out / ("distribution_%s.json" % item), "w") as fh:
        json.dump(dist, fh, indent=1, sort_keys=True)
        fh.write("\n")

    subitems = sorted({r["item"] for r in rows_all})
    with open(summary, "a") as fh:
        fh.write("\n## 결과 (실행 뒤)\n")
        for sub in subitems:
            rs = [r for r in rows_all if r["item"] == sub]
            j = mj.judge_run(rs, MIN_ATTEMPTS[item])
            fh.write("%s: 시도 %d, PASS %d, FAIL %d, 그 밖 %d, 시도 수 충분 %s, 전부 PASS %s, "
                     "실패율 95%% 상한 약 %s\n" % (
                         sub, j["n"], j["n_pass"], j["n_fail"], j["n_other"], j["enough"],
                         j["all_pass"], "-" if j["upper95_fail_rate"] is None
                         else "%.0f%%" % (100 * min(1.0, j["upper95_fail_rate"]))))
            for r in rs:
                if r["verdict"] != "PASS":
                    fh.write("  시도 %d %s: %s\n" % (r["attempt"], r["verdict"], "; ".join(r["reasons"])))
            if sub in ("2a", "2b", "3", "5", "armed"):
                tot = [r.get("facts", {}).get("cleanup_total_s") for r in rs
                       if r.get("facts") and r["facts"].get("cleanup_total_s") is not None]
                if tot:
                    fh.write("  정리 총 소요(s): min %.3f max %.3f\n" % (min(tot), max(tot)))
        arm = mj.judge_armed_criterion([r for r in rows_all if "armed_non_offboard" in r])
        fh.write("ARMED 기준(이 실행): %s\n" % json.dumps(arm, sort_keys=True))
        if arm["violated"]:
            fh.write("!! OFFBOARD가 아닌 ARMED 표본이 나왔다. 즉시 architect에게 올린다.\n")
    any_fail = False
    for sub in subitems:
        rs = [r for r in rows_all if r["item"] == sub]
        j = mj.judge_run(rs, MIN_ATTEMPTS[item])
        if j["n_fail"]:
            any_fail = True
        elif not (j["enough"] and j["all_pass"]):
            status = max(status, 2)
    if any_fail:
        status = 1       # FAIL이 있으면 시도 수 부족 같은 2보다 앞선다
    return status


if __name__ == "__main__":
    sys.exit(main())
