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


"""PX4 재실측 (2), (3), (5)와 ARMED 표본 기록(PX4 직접 명령)의 측정 실행기.

ros-ws runner 컨테이너 안에서 돈다(rclpy, px4_msgs 필요). 호스트에서는 run_measure.sh를 쓴다.
Executor 노드 없이 PX4에 직접 명령을 보낸다(측정 전용 발행자 tests/support/px4_measure_pub.py).
정리 분기의 선택과 종료는 tests/support/measure_judge.py의 CleanupModel이 decisions.md M3, M5, M6의
규칙 일부를 흉내 낸다. 판정 기준과 정본 문장은 measure_judge.py 머리와 decisions.md의 "넘김 목록"
px4-engineer 행이다.

  measure.py --item item2|item3|item5|armed [--attempts N] [--out-dir DIR]

항목
  item2  (2) 지상 setpoint 발행 중의 Hold. 시도마다 행 둘: 2a(Hold 확인과 정리 소요), 2b(Hold를 확인하고
         발행을 멈춘 뒤 landed가 true에 닿는지, 닿으면 그 상태에서 disarm).
  item3  (3) 이륙 직후의 지상 setpoint와 disarm. trigger는 첫 ARMED 표본이고, 그 시점 landed가 true인
         시도만 창 안이다(아니면 WINDOW_MISSED). Hold로 끝나면 60 s 관찰하고 HOLD_END로 둔다.
  item5  (5) arm 전송 직후(0-0.2 s sim)의 취소 경쟁. 주입 지연은 --delays를 시도 수만큼 돌려 쓴다.
  armed  PX4 직접 명령의 arm -> ARMED 3회 -> 이륙 -> NAV_LAND 구간의 vehicle_status 표본 기록. 첫 ARMED
         표본을 본 뒤 arm 재전송을 멈춘다. 시나리오 A(Executor 경유)의 대응이나 대체가 아니다. 시나리오 A는
         같은 Px4Raw 기록기와 judge를 P4 시나리오가 따로 쓴다.

기록(--out-dir, 기본 <실행 디렉터리>/measure/). 기존 파일이 있으면 덮어쓰지 않고 거부한다.
  measure_<item>.jsonl     시도마다 한 줄. 실패한 시도를 빼지 않고 재시도하지 않는다
  raw_<item>.jsonl         시도마다 vehicle_status, vehicle_land_detected, 위치, ack, 전송 원시 표본
  summary_<item>.txt       머리에 통과 기준과 실행 인자(실행 전에 기록), 아래에 결과
  distribution_<item>.json timestamp - Px4Timestamp 등 부호 있는 분포 (재실측 (5)의 요구)

종료 코드와 verdict의 뜻
  0  모든 시도 PASS이고 시도 수 충분.
  1  기준과 다른 관측(verdict FAIL, M3_CONTRADICTED)이나 ARMED 위반(어느 부류든)이 있음. 문서의 기대가
     반증됐다는 뜻이며 PX4 결함이라는 뜻이 아니다. 2보다 앞선다. M3_CONTRADICTED는 2b에서 landed가
     true에 닿은 경우로 M3 문장과 다른 관측이다(disarm 수락과 고도 변화는 facts에 기록).
  2  기계가 판정하지 않음: COND_NOT_REACHED, HOLD_END, INCONCLUSIVE, WINDOW_MISSED, PRECONDITION,
     ERROR, CLOCK_STALLED, 유효 시도(PASS, FAIL, M3_CONTRADICTED) 수 부족, 행 0개, commit unknown이나
     image key 없음, 처리하지 못한 예외.
(5)의 arm 수락 증거가 ROS 표본에 없으면 이 스크립트 단독의 행은 INCONCLUSIVE(ULog 교차 확인 전)이고
최종 PASS는 crosscheck.py 뒤에만 선언한다.

보증 범위: PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, landed 전환, 상승)만 본다. 정리 총 소요 9 s
기준은 측정용 모델의 소요이고 core의 소요를 보증하지 않는다. timeout은 모두 sim 시간(/clock)이고
벽시계는 /clock이 멈췄는지 보는 데만 쓴다.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import rclpy  # noqa: E402

from px4_msgs.msg import VehicleStatus  # noqa: E402

from tests.support import measure_check as mc  # noqa: E402
from tests.support import measure_judge as mj  # noqa: E402
from tests.support import stack as stk  # noqa: E402
from tests.support.px4_measure_pub import MeasureOnlyPublisher  # noqa: E402
from tests.support.px4_raw import ClockStalled, Px4Raw  # noqa: E402

US = mj.US

ITEMS = ("item2", "item3", "item5", "armed")
# 최소 시도 수는 measure_check.MIN_ATTEMPTS_BY_ITEM 한 곳에 있다(crosscheck.py도 같은 값을 쓴다)
MIN_ATTEMPTS = {"item2": mc.MIN_ATTEMPTS_BY_ITEM["2b"], "item3": mc.MIN_ATTEMPTS_BY_ITEM["3"],
                "item5": mc.MIN_ATTEMPTS_BY_ITEM["5"], "armed": mc.MIN_ATTEMPTS_BY_ITEM["armed"]}
DEFAULT_ATTEMPTS = dict(MIN_ATTEMPTS)
DELAY_RANGE_S = (0.0, 0.2)

STOP_ARM_RESEND_AFTER_FIRST_ARMED = True   # armed 항목: P6처럼 첫 ARMED 표본에서 arm 재전송을 멈춘다

CRITERIA = {
    "item2": [
        "(2a) 지상 setpoint(z +0.5 m) 발행 중 Hold 전송. AUTO_LOITER 표본을 처음 관측한 시각에 발행을 멈추고 "
        "(별도 필드), 전송 뒤 받은 서로 다른 timestamp의 AUTO_LOITER 3회 연속 시점을 종료로 본다. "
        "총 소요 9 s 미만은 종료 시각 기준이다. OFFBOARD가 아닌 ARMED 표본은 기록만 한다.",
        "(2b) Hold 확인 뒤 발행을 멈추고 landed가 true가 되는지 --observe-s(sim 초) 동안 본다. 닿으면 "
        "강제가 아닌 disarm을 보내 수락과 고도 변화를 facts에 기록하고 verdict는 M3_CONTRADICTED(종료 코드 1, "
        "M3 문장과 다른 관측이므로 architect에게 올린다). 닿지 못하면 관찰 중 모든 표본이 ARMED이고 "
        "AUTO_LOITER, landed 전환 0회, 고도 변화 0.2 m 이하인 한 COND_NOT_REACHED(종료 코드 2), 어긋나면 FAIL. "
        "관찰 구간이 60 s 미만이거나 표본 수가 모자라거나(vehicle_status 초당 1개, vehicle_land_detected "
        "초당 0.5개 미만) 마지막 표본이 관찰 끝에서 1 s(landed는 2 s) 넘게 지났으면 INCONCLUSIVE.",
        "시도 3회 모두 위 기준을 만족해야 통과한다. 3회는 실패율 95% 상한이 약 100%라 실패 없음의 증거가 아니다.",
    ],
    "item3": [
        "TAKEOFF 목표점으로 arm한 뒤 첫 ARMED 표본에서 landed가 true인 시도만 창 안이다(아니면 WINDOW_MISSED, "
        "통과로 세지 않음). 그 시점에 지상 setpoint로 바꾸고 disarm.",
        "mode_confirm_timeout(3 s) 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만, "
        "OFFBOARD가 아닌 ARMED 표본 0개(구간 끝 = min(ARMED 3회 확인, 정리 종료, 측정기의 첫 Hold 전송)), "
        "끝난 뒤 지상에 armed로 남지 않음.",
        "Hold로 끝나면(end_reason HOLD) 상승 0.2 m 이하, 총 소요 9 s 미만이고 --hold-observe-s(60) 동안 "
        "ARMED, AUTO_LOITER, landed false, 고도 변화 0.2 m 이하이면 HOLD_END(종료 코드 2), 어긋나면 FAIL, "
        "관찰이 60 s 미만이면 INCONCLUSIVE. TIMEOUT_GROUND, TIMEOUT_HOLD, LIMIT, DISARMED_AIR는 FAIL.",
        "시도 3회 모두 통과해야 통과한다. 3회는 실패율 95% 상한이 약 100%라 실패 없음의 증거가 아니다.",
    ],
    "item5": [
        "arm 전송 뒤 0-0.2 s(sim)에 지상 setpoint와 disarm. 지연은 --delays를 돌려 쓴다.",
        "mode_confirm_timeout(3 s) 안에 DISARMED 3회, 상승 0.2 m 이하, 정리 총 소요 9 s 미만, "
        "OFFBOARD가 아닌 ARMED 표본 0개(구간 끝은 (3)과 같다), 관찰(--tail-s)이 끝날 때까지 지상에 armed로 "
        "남지 않음. Hold로 끝나면 FAIL.",
        "arm 수락 증거: arm 전송 뒤 timestamp의 ARMED 표본(ROS 또는 ULog) 또는 ULog의 '[commander] Armed by "
        "external command'(arm 전송 뒤, 정리 종료 전). ROS ack는 증거가 아니다(arm과 disarm이 같은 command "
        "400이고 ack에 원 명령 필드가 없다). 증거가 없으면 INCONCLUSIVE. 이 스크립트 단독의 행은 ROS 표본이 "
        "없으면 'arm 수락 증거 미확인(ULog 교차 확인 전)'으로 남고 최종 PASS는 crosscheck.py 뒤에만 선언한다.",
        "유효 시도(PASS, FAIL)가 10회 이상이고 PASS가 10회 이상이어야 통과한다(10회 중 0건은 실패율 95% 상한 약 26%). "
        "INCONCLUSIVE는 유효 시도가 아니다.",
    ],
    "armed": [
        "PX4 직접 명령(Executor 없음). arm 전송부터 ARMED 3회 확인(= TAKEOFF 시작에 해당)까지, 그리고 ARMED 3회 "
        "확인부터 NAV_LAND 전송까지의 모든 vehicle_status 표본에서 OFFBOARD가 아닌 ARMED 표본이 0개. "
        "첫 ARMED 표본을 본 뒤 arm 재전송을 멈춘다(P6와 같은 자극).",
        "ARMED 3회 확인까지 간 시도가 10회 이상이고 그 전부에서 0개여야 통과한다. 한 건이라도 나오면 "
        "즉시 architect에게 올린다. 이것은 통계적 증명이 아니라 메커니즘의 반증 확인이다. 이 통과는 "
        "PX4 직접 부류의 통과이고 P4 머지 조건은 Executor 경유 부류(시나리오 A)의 통과가 따로 필요하다.",
    ],
}


class Precondition(Exception):
    """시도를 시작할 상태를 만들지 못했다(verdict PRECONDITION)."""


# ---------------------------------------------------------------------------
# 구동


class Rig:
    """Px4Raw(기록)와 MeasureOnlyPublisher(송신) 위의 제어 loop. 발행(20 Hz sim)과 대기를 한 곳에서 한다."""

    def __init__(self, raw, pub):
        self.raw = raw
        self.pub = pub
        self.sp = None           # (x, y, z, yaw) NED. None이면 발행하지 않는다
        self._last_pub = 0
        self.pub_count = 0

    def pump(self):
        self.raw.guard()
        now = self.raw.now_us()
        if self.sp is not None and now - self._last_pub >= 50_000:
            self.pub.publish_position(*self.sp)
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
            self.pub.publish_position(*sp)
            self._last_pub = self.raw.now_us()
            self.pub_count += 1

    def send(self, kind):
        return self.pub.send(kind)


def send_until(rig, kind, confirm, timeout_s, resend_s=mj.COMMAND_RESEND_S, idx=None):
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
        if now - start >= timeout_s * US:
            return False, first
        rig.pump()


def reset_vehicle(rig, timeout_s=60.0):
    """다음 시도의 시작 상태(DISARMED, landed true)를 만든다. 못 만들면 Precondition."""
    raw = rig.raw
    rig.sp = None
    last_land = None
    t_begin = raw.now_us()

    def ready():
        st, ld = raw.last_status(), raw.last_landed()
        return (st is not None and ld is not None and mj.is_disarmed(st) and ld.landed
                and st.recv_ros_us > t_begin)

    while True:
        if ready():
            return
        st = raw.last_status()
        now = raw.now_us()
        if st is not None and mj.is_armed(st) and (last_land is None or now - last_land >= 2 * US):
            rig.send("land")
            last_land = now
        if now - t_begin >= timeout_s * US:
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
    """지상 setpoint로 바꾸고 CleanupModel로 정리한다. 끝난 모델을 돌려준다.

    발행 중단은 모델이 알린다(publishing). Hold 첫 관측에서 멈추고, 종료는 모델의 end_reason 시점이다.
    """
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
        if not model.publishing:
            rig.sp = None
        if model.done:
            break
        rig.pump()
    rig.sp = None
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
    """arm 전송부터 (ARMED 3회 확인, end_us, cutoff_us 중 가장 이른 시각)까지의 ARMED 표본을 센다.

    cutoff_us는 첫 Hold 전송 시각이다. 그 뒤(end_us까지)의 비OFFBOARD ARMED는 정상 동작(Hold 모드)이라
    위반 구간 밖이고 armed_after_hold로 따로 센다.
    """
    samples = raw.status[idx_s:]
    armed3 = mj.armed_confirm_sample(samples, arm_recv)
    to = end_us if cutoff_us is None else min(end_us, cutoff_us)
    # 잘린 구간(첫 Hold 전송, 정리 종료) 안에서 ARMED 3회가 찬 경우만 도달로 센다
    reached = armed3 is not None and armed3.recv_ros_us <= to
    if reached:
        to = min(to, armed3.recv_ros_us)
    n_armed, bad = mj.armed_non_offboard(samples, arm_recv, to)
    after = 0
    if cutoff_us is not None and end_us > to:
        after = len(mj.armed_non_offboard(samples, to + 1, end_us)[1])
    return {
        "armed3_reached": reached,
        "armed3_ros_us": armed3.recv_ros_us if reached else None,
        "armed_window_ros_us": [arm_recv, to],
        "armed_samples": n_armed,
        "armed_non_offboard": len(bad),
        "armed_after_hold": after,
        "armed_non_offboard_samples": [
            {"ts_us": b.ts_us, "recv_ros_us": b.recv_ros_us, "nav_state": b.nav_state,
             "failsafe": b.failsafe, "intention": b.intention} for b in bad],
    }


def cleanup_facts(raw, model, arm_recv, ref_z, tail):
    seq = mj.branch_sequence(model.branch_log)
    armed_after, final_disarmed = tail
    first_disarm = next(((r, t) for k, r, t in model.sent_log if k == "disarm"), None)
    return {
        "end_reason": model.end_reason,
        "cleanup_start_ros_us": model.start_us,
        "cleanup_end_ros_us": model.end_us,
        "cleanup_total_s": model.elapsed_s,
        "cleanup_publish_stop_ros_us": model.publish_stop_us,
        "cleanup_publish_stop_s": model.publish_stop_elapsed_s,
        "branch_sequence": seq["sequence"],
        "branch_transitions": seq["transitions"],
        "branch_log": [[t, b] for t, b in model.branch_log],
        "landed_transitions_arm_to_end": mj.landed_transitions(raw.landed, arm_recv, model.end_us),
        "landed_transitions_cleanup": mj.landed_transitions(raw.landed, model.start_us, model.end_us),
        "first_disarm_send": first_disarm,
        "first_hold_send": next(((r, t) for k, r, t in model.sent_log if k == "hold"), None),
        "sent_log": [list(x) for x in model.sent_log],
        "climb_m": climb_m(raw, ref_z, arm_recv, model.end_us + 3 * US),
        "armed_after_end": armed_after,
        "final_disarmed": final_disarmed,
    }


def observe_facts(raw, start_us, z_ref, end_us):
    """관찰 구간 (start_us, end_us]의 사실. 명목 관찰 시간이 아니라 실제 표본으로 쓴다.

    span_s는 관찰 구간의 sim 길이, status_n과 landed_n은 구간 안 표본 수, *_age_s는 마지막 표본이
    관찰 끝에서 얼마나 지났는가(landed는 구간 앞의 표본까지 포함한 마지막 표본). 표본이 없으면
    all_armed_loiter와 landed_false는 참(공허)이고, 판정은 표본 조건(measure_judge._sampling_problem)
    이 INCONCLUSIVE로 막는다.
    """
    st = [x for x in raw.status if start_us < x.recv_ros_us <= end_us]
    ld = [x for x in raw.landed if start_us < x.recv_ros_us <= end_us]
    last_ld = [x for x in raw.landed if x.recv_ros_us <= end_us]
    all_st = [x for x in raw.status if x.recv_ros_us <= end_us]
    zs = [abs(q[3] - z_ref) for q in raw.pos if start_us < q[0] <= end_us]
    return {
        "span_s": (end_us - start_us) / US,
        "status_n": len(st),
        "landed_n": len(ld),
        "status_age_s": None if not st else (end_us - st[-1].recv_ros_us) / US,
        "landed_age_s": None if not last_ld else (end_us - last_ld[-1].recv_ros_us) / US,
        # 이웃 표본 사이 최대 간격(시작 가장자리 포함). PX4 timestamp 기준과 수신 시각 기준을 둘 다 남긴다.
        "status_gap_ts_s": mj.neighbor_gap_s([x.ts_us for x in all_st], start_us),
        "status_gap_recv_s": mj.neighbor_gap_s([x.recv_ros_us for x in all_st], start_us),
        "landed_gap_ts_s": mj.neighbor_gap_s([x.ts_us for x in last_ld], start_us),
        "landed_gap_recv_s": mj.neighbor_gap_s([x.recv_ros_us for x in last_ld], start_us),
        "all_armed_loiter": all(mj.is_armed(x) and x.nav_state == mj.NAV_STATE_AUTO_LOITER for x in st),
        "landed_transitions": mj.landed_transitions(raw.landed, start_us, end_us),
        "landed_false": all(not x.landed for x in ld),
        "dz_m": max(zs) if zs else None,
    }


def hold_observe_facts(raw, end_us, z_end):
    """Hold로 끝난 뒤의 관찰 사실(접두사 hold_observe_). observe_facts를 쓴다."""
    o = observe_facts(raw, end_us, z_end, raw.now_us())
    return {"hold_observe_span_s": o["span_s"], "hold_observe_status_n": o["status_n"],
            "hold_observe_landed_n": o["landed_n"], "hold_observe_status_age_s": o["status_age_s"],
            "hold_observe_landed_age_s": o["landed_age_s"],
            "hold_observe_status_gap_ts_s": o["status_gap_ts_s"],
            "hold_observe_status_gap_recv_s": o["status_gap_recv_s"],
            "hold_observe_landed_gap_ts_s": o["landed_gap_ts_s"],
            "hold_observe_landed_gap_recv_s": o["landed_gap_recv_s"],
            "hold_observe_all_armed_loiter": o["all_armed_loiter"],
            "hold_observe_landed_false": o["landed_false"], "hold_observe_dz_m": o["dz_m"]}


def ack_facts(raw, arm_recv, first_disarm_recv, first_hold_recv=None):
    """command 400의 ack를 전송 시각 구간으로 나눠 기록한다(arm과 disarm이 같은 command 번호다)."""
    arm_end = first_disarm_recv if first_disarm_recv is not None else first_hold_recv
    return {
        "arm_ack": raw.acks_between(400, arm_recv, arm_end),
        "disarm_ack": [] if first_disarm_recv is None else raw.acks_between(400, first_disarm_recv),
    }


# ---------------------------------------------------------------------------
# 항목별 시도


def nominal_injection(item, a, args):
    """시도 전에 정해지는 주입 조건. PRECONDITION/ERROR 행에도 남긴다."""
    if item == "item5":
        return {"item": "5", "delay_s_nominal": args.delays[a % len(args.delays)],
                "trigger": "arm 전송 + sim 지연"}
    if item == "item3":
        return {"item": "3", "trigger": "첫 ARMED 표본(그 시점 landed 최신값이 true인 시도만 창 안)"}
    if item == "item2":
        return {"item": "2a", "trigger": "첫 ARMED 뒤 첫 landed==false 표본"}
    return {"item": "armed", "trigger": "arm 전송 -> ARMED 3회 확인(= TAKEOFF 시작)"}


def first_hold_recv(model):
    f = model.first_send["hold"]
    return None if f is None else f[0]


def attempt_item5(rig, args, a):
    raw = rig.raw
    nominal = args.delays[a % len(args.delays)]
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    rig.sleep_sim(nominal)
    cancel_us = raw.now_us()
    ld = raw.last_landed()
    model = run_cleanup(rig, cancel_us)
    tail = observe_tail(rig, model.end_us, args.tail_s)
    f = cleanup_facts(raw, model, arm_recv, ref["z"], tail)
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us, cutoff_us=first_hold_recv(model)))
    fd = f["first_disarm_send"]
    f.update(ack_facts(raw, arm_recv, None if fd is None else fd[0], first_hold_recv(model)))
    # ROS 쪽 arm 수락 증거 A: arm 전송 뒤 timestamp의 ARMED 표본. ack는 증거가 아니다.
    # (ULog의 증거 A, B는 crosscheck.py가 확정한다)
    evidence = any(mj.is_armed(x) and x.ts_us > arm_ts and x.recv_ros_us > arm_recv
                   for x in raw.status[idx_s:])
    f.update({"arm_send": [arm_recv, arm_ts], "landed_at_cancel": None if ld is None else ld.landed,
              "arm_evidence": evidence})
    inj = {"item": "5", "delay_s_nominal": nominal, "delay_s_actual": (cancel_us - arm_recv) / US,
           "trigger": "arm 전송 + sim 지연", "arm_send_ros_us": arm_recv}
    return [("5", inj, f)]


def wait_first_armed(rig, idx_s, arm_recv, record):
    """arm을 0.5 s마다 다시 보내며 첫 ARMED 표본을 기다린다(arm_timeout 5 s). record에 표본과 시점 상태를 남긴다."""
    raw = rig.raw
    last = arm_recv
    t_start = raw.now_us()
    while True:
        for s in raw.status[idx_s:]:
            if mj.is_armed(s) and s.recv_ros_us > arm_recv:
                record["s"] = s
                record["landed"] = raw.last_landed()
                record["pos"] = raw.last_pos()
                return
        now = raw.now_us()
        if now - last >= mj.COMMAND_RESEND_S * US:
            rig.send("arm")
            last = now
        if now - t_start >= 5 * US:
            raise Precondition("ARMED 표본을 5 s 안에 보지 못함(arm ack %s)"
                               % raw.acks_between(400, arm_recv)[:5])
        rig.pump()


def attempt_item3(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    first = {}
    wait_first_armed(rig, idx_s, arm_recv, first)
    cancel_us = raw.now_us()
    landed_at_cancel = None if first["landed"] is None else first["landed"].landed
    model = run_cleanup(rig, cancel_us)
    hold_case = model.end_reason == "HOLD"
    z_end = raw.last_pos()[3]
    tail = observe_tail(rig, model.end_us, args.hold_observe_s if hold_case else args.tail_s)
    f = cleanup_facts(raw, model, arm_recv, ref["z"], tail)
    if hold_case:
        f.update(hold_observe_facts(raw, model.end_us, z_end))
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us, cutoff_us=first_hold_recv(model)))
    fd = f["first_disarm_send"]
    f.update(ack_facts(raw, arm_recv, None if fd is None else fd[0], first_hold_recv(model)))
    height = None if first["pos"] is None else ref["z"] - first["pos"][3]
    f.update({"arm_send": [arm_recv, arm_ts], "landed_at_cancel": landed_at_cancel,
              "height_at_cancel_m": height,
              "sim_s_first_armed_after_arm": (first["s"].recv_ros_us - arm_recv) / US})
    inj = {"item": "3", "trigger": "첫 ARMED 표본(그 시점 landed 최신값이 true인 시도만 창 안)",
           "arm_send_ros_us": arm_recv, "sim_s_arm_to_cancel": (cancel_us - arm_recv) / US}
    return [("3", inj, f)]


def attempt_item2(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    arm_recv, arm_ts = rig.send("arm")
    first = {}
    wait_first_armed(rig, idx_s, arm_recv, first)
    first_armed_us = first["s"].recv_ros_us

    def landed_false_after_armed():
        return any((not x.landed) and x.recv_ros_us >= first_armed_us for x in raw.landed)

    if not rig.wait(landed_false_after_armed, 10.0):
        raise Precondition("ARMED 뒤 10 s 안에 landed가 false가 되지 않음")
    cancel_us = raw.now_us()
    ld = raw.last_landed()
    height = ref["z"] - raw.last_pos()[3]
    model = run_cleanup(rig, cancel_us)       # landed false -> A 분기: 지상 setpoint 유지 + Hold
    hold_end = model.end_us
    f = cleanup_facts(raw, model, arm_recv, ref["z"], (False, False))
    f.update(armed_facts(raw, idx_s, arm_recv, model.end_us, cutoff_us=first_hold_recv(model)))
    f.update(ack_facts(raw, arm_recv, None, first_hold_recv(model)))
    f.update({"arm_send": [arm_recv, arm_ts], "height_at_cancel_m": height,
              "landed_at_cancel": None if ld is None else ld.landed,
              "sim_s_first_armed_to_cancel": (cancel_us - first_armed_us) / US})
    inj_a = {"item": "2a", "trigger": "첫 ARMED 뒤 첫 landed==false 표본", "arm_send_ros_us": arm_recv}
    rows = [("2a", inj_a, f)]

    # 2b: Hold 확인 뒤 발행 없음. landed 최신 표본이 true이면 강제가 아닌 disarm
    g = {"hold_end_ros_us": hold_end}
    if model.end_reason != "HOLD":
        g.update({"landed_true_seen": False, "disarm_confirmed": False, "dz_max_m": None,
                  "skipped": "2a가 Hold로 끝나지 않아 2b를 하지 않음(end_reason=%s)" % model.end_reason})
        return rows + [("2b", {"item": "2b", "trigger": "해당 없음"}, g)]
    z_hold = raw.last_pos()[3]
    seen_true = {}

    def landed_true():
        x = raw.last_landed()
        if x is not None and x.landed:
            seen_true["l"] = x
            return True
        return False

    got = rig.wait(landed_true, args.observe_s)
    obs = observe_facts(raw, hold_end, z_hold, raw.now_us())
    g.update({"landed_true_seen": got, "observe_s_nominal": args.observe_s,
              "landed_transitions_observe": obs["landed_transitions"],
              "observe_landed_transitions": obs["landed_transitions"]["count"],
              "observe_span_s": obs["span_s"], "observe_status_n": obs["status_n"],
              "observe_landed_n": obs["landed_n"], "observe_status_age_s": obs["status_age_s"],
              "observe_landed_age_s": obs["landed_age_s"],
              "observe_status_gap_ts_s": obs["status_gap_ts_s"],
              "observe_status_gap_recv_s": obs["status_gap_recv_s"],
              "observe_landed_gap_ts_s": obs["landed_gap_ts_s"],
              "observe_landed_gap_recv_s": obs["landed_gap_recv_s"],
              "observe_all_armed_loiter": obs["all_armed_loiter"]})
    if got:
        t_true = seen_true["l"].recv_ros_us
        conf = mj.ConsecutiveConfirm(mj.is_disarmed)
        ok, fdis = send_until(rig, "disarm", conf, mj.MODE_CONFIRM_TIMEOUT_S)
        end_now = raw.now_us()
        before = [abs(q[3] - z_hold) for q in raw.pos if hold_end <= q[0] < fdis[0]]
        after = [abs(q[3] - z_hold) for q in raw.pos if fdis[0] <= q[0] <= end_now]
        both = before + after
        g.update({"landed_true_ros_us": t_true, "landed_true_after_hold_s": (t_true - hold_end) / US,
                  "disarm_confirmed": ok, "first_disarm_send": fdis,
                  "disarm_ack": raw.acks_between(400, fdis[0]),
                  "dz_before_disarm_m": max(before) if before else None,
                  "dz_after_disarm_m": max(after) if after else None,
                  "dz_max_m": max(both) if both else None})
    else:
        g.update({"disarm_confirmed": False, "dz_max_m": obs["dz_m"]})
    return rows + [("2b", {"item": "2b", "trigger": "Hold 확인 뒤 landed 최신 표본이 true",
                           "hold_end_ros_us": hold_end}, g)]


def arm_until_armed3(rig, conf, idx_s, timeout_s=5.0):
    """arm을 0.5 s마다 보내다가 첫 ARMED 표본(수신이 첫 전송 뒤)을 보면 재전송을 멈추고(P6와 같은
    자극) ARMED 3회 확인을 계속 기다린다. 한도 timeout_s(item2/item3의 arm_timeout과 같은 5 s) 안에
    못 채우면 (False, 첫 전송)이다(중단 뒤 DISARMED로 돌아간 경우 포함)."""
    raw = rig.raw
    first = None
    last = None
    seen = False
    i = idx_s
    start = raw.now_us()
    while True:
        now = raw.now_us()
        resend_ok = not (STOP_ARM_RESEND_AFTER_FIRST_ARMED and seen)
        if first is None or (resend_ok and now - last >= mj.COMMAND_RESEND_S * US):
            recv, ts = rig.send("arm")
            if first is None:
                first = (recv, ts)
                conf.set_floor(ts, recv)
            last = now
        for x in raw.status[i:]:
            if mj.is_armed(x) and x.recv_ros_us > first[0]:
                seen = True
            if conf.feed(x):
                return True, first
        i = len(raw.status)
        if now - start >= timeout_s * US:
            return False, first
        rig.pump()


def attempt_armed(rig, args, a):
    raw = rig.raw
    ref = prepare(rig, args)
    idx_s = len(raw.status)
    conf = mj.ConsecutiveConfirm(mj.is_armed)
    ok, first = arm_until_armed3(rig, conf, idx_s)
    arm_recv, arm_ts = first
    end_us = conf.confirmed_at.recv_ros_us if ok else raw.now_us()
    f = armed_facts(raw, idx_s, arm_recv, end_us)
    f.update({"arm_send": [arm_recv, arm_ts], "arm_ack": raw.acks_between(400, arm_recv)})
    if not ok:
        e = Precondition("ARMED 3회 확인을 5 s 안에 채우지 못함(arm ack %s)" % f["arm_ack"])
        e.facts = f
        raise e
    # TAKEOFF 시작: 목표점 발행을 이어 가며 고도를 기다린다
    f["takeoff_start_ros_us"] = end_us
    target_z = ref["z"] - args.takeoff_alt + 0.5
    f["reached_altitude"] = rig.wait(lambda: raw.last_pos()[3] <= target_z, 30.0)
    # LAND: NAV_LAND를 보내 AUTO_LAND를 확인하고 발행을 멈춘 뒤 DISARMED를 기다린다
    land_conf = mj.ConsecutiveConfirm(lambda s: s.nav_state == mj.NAV_STATE_AUTO_LAND, n=1)
    lok, land_first = send_until(rig, "land", land_conf, mj.MODE_CONFIRM_TIMEOUT_S)
    rig.sp = None
    f["land_send"] = land_first
    f["flight_armed_non_offboard"] = len(
        mj.armed_non_offboard(raw.status[idx_s:], end_us + 1, land_first[0])[1])
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
    return [("armed", inj, f)]


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
    image_keys = json.loads(keys) if keys else None
    return {
        "run_id": st.run_id, "commit": commit, "dirty": dirty, "images": st.raw["images"],
        "image_keys": image_keys, "stack_json": str(st.path),
        "ok": commit not in (None, "", "unknown") and image_keys is not None,
    }


def write_extra_summary(fh, item, rows):
    """항목별 요약: 2b 회별 결과, (3)의 분기 순서와 복귀 시간, (5)의 ARMED 표본과 지연값별 유효 시도."""
    if item == "item2":
        cases = []
        for r in (x for x in rows if x["item"] == "2b"):
            f = r["facts"]
            if f is None:
                continue
            if "skipped" in f:
                cases.append("  시도 %d: 2b 하지 않음(%s)" % (r["attempt"], f["skipped"]))
            elif f["landed_true_seen"]:
                cases.append("  시도 %d: (나) landed true 뒤 disarm %s, 고도 변화 %s m"
                             % (r["attempt"], "확인" if f["disarm_confirmed"] else "미확인", f["dz_max_m"]))
            else:
                cases.append("  시도 %d: (가) landed true 미도달(%s)" % (r["attempt"], r["verdict"]))
        fh.write("2b 회별 결과:\n" + "\n".join(cases) + "\n")
        fh.write("(가) 미도달 %d회(COND_NOT_REACHED), (나) M3_CONTRADICTED %d회\n" % (
            sum(1 for r in rows if r["item"] == "2b" and r["verdict"] == "COND_NOT_REACHED"),
            sum(1 for r in rows if r["item"] == "2b" and r["verdict"] == "M3_CONTRADICTED")))
        if any(c.startswith("  시도") and "(나)" in c for c in cases):
            fh.write("!! (나)가 있다: M3 문장(Hold로 끝난 기체는 스스로 내려앉지 않는다)과 다르다. architect에게 올린다.\n")
    if item in ("item3", "item5"):
        from collections import Counter
        sub = "3" if item == "item3" else "5"
        rs = [r for r in rows if r["item"] == sub and r["facts"] and "branch_sequence" in r["facts"]]
        seqs = Counter(r["facts"]["branch_sequence"] for r in rs)
        fh.write("분기 순서별 회수: %s\n" % dict(seqs))
        back = []
        for r in rs:
            log = r["facts"]["branch_log"]
            ta = next((t for t, b in log if b == "A"), None)
            if ta is not None:
                tg = next((t for t, b in log if b == "G" and t > ta), None)
                back.append("시도 %d: %s" % (r["attempt"], "공중 분기 뒤 지상 복귀 %.3f s" % ((tg - ta) / US)
                                             if tg is not None else "공중 분기 뒤 지상 복귀 없음"))
        fh.write("공중 분기로 넘어간 회: %s\n" % (back if back else "없음"))
    if item == "item5":
        rs = [r for r in rows if r["item"] == "5" and r["facts"] and "armed_samples" in r["facts"]]
        fh.write("ARMED 표본이 1개 이상 보인 시도: %d / %d\n"
                 % (sum(1 for r in rs if r["facts"]["armed_samples"] >= 1), len(rs)))
        by = {}
        for r in (x for x in rows if x["item"] == "5"):
            d = r["injection"]["delay_s_nominal"] if r["injection"] else None
            e = by.setdefault(d, {"valid": 0, "all": 0})
            e["all"] += 1
            if r["verdict"] in mj.VALID_VERDICTS:
                e["valid"] += 1
        fh.write("지연값별 시도(유효 = PASS, FAIL. INCONCLUSIVE는 유효 시도가 아니다): %s\n" % json.dumps(
            {str(k): v for k, v in sorted(by.items(), key=lambda kv: (kv[0] is None, kv[0]))}))


def exit_code_of(verdict):
    return 1 if verdict in mj.EXIT1_VERDICTS else (0 if verdict == "PASS" else 2)


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--item", required=True, choices=ITEMS)
    ap.add_argument("--attempts", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--takeoff-alt", type=float, default=5.0, help="이륙 목표 높이(m)")
    ap.add_argument("--settle-s", type=float, default=3.0, help="시도 전 안정화(sim 초)")
    ap.add_argument("--tail-s", type=float, default=3.0, help="정리 뒤 관찰(sim 초). 0 거부")
    ap.add_argument("--observe-s", type=float, default=60.0, help="2b 관찰(sim 초)")
    ap.add_argument("--hold-observe-s", type=float, default=60.0,
                    help="(3)이 Hold로 끝났을 때의 관찰(sim 초)")
    ap.add_argument("--delays", default="0,0.05,0.1,0.15,0.2",
                    help="item5 주입 지연 목록(sim 초, 0-0.2 범위)")
    args = ap.parse_args(argv)
    try:
        args.delays = [float(x) for x in args.delays.split(",")]
    except ValueError:
        ap.error("--delays는 쉼표로 구분한 숫자여야 한다")
    if not args.delays or any(d < DELAY_RANGE_S[0] or d > DELAY_RANGE_S[1] for d in args.delays):
        ap.error("--delays는 %.1f-%.1f s 범위여야 한다: %s" % (DELAY_RANGE_S + (args.delays,)))
    if args.tail_s <= 0:
        ap.error("--tail-s는 0보다 커야 한다(정리 뒤 지상 armed 잔존을 보려면 관찰이 필요하다)")
    if args.observe_s <= 0 or args.hold_observe_s <= 0 or args.settle_s < 0 or args.takeoff_alt <= 0.5:
        ap.error("--observe-s, --settle-s, --takeoff-alt 값이 범위 밖이다")
    if args.attempts is None:
        args.attempts = DEFAULT_ATTEMPTS[args.item]
    if args.attempts < 1:
        ap.error("--attempts는 1 이상이어야 한다")
    return args


def args_record(args):
    return {"takeoff_alt": args.takeoff_alt, "settle_s": args.settle_s, "tail_s": args.tail_s,
            "observe_s": args.observe_s, "hold_observe_s": args.hold_observe_s, "delays": args.delays, "attempts": args.attempts}


def main(argv=None):
    args = parse_args(argv)
    st = stk.load_from_env()
    veh = st.vehicles[0]
    out = Path(args.out_dir) if args.out_dir else st.dir / "measure"
    out.mkdir(parents=True, exist_ok=True)
    meta = run_meta(st)
    item = args.item

    # 기록 덮어쓰기 금지: 같은 항목의 기록이 있으면 시작하지 않는다
    names = ["measure_%s.jsonl", "raw_%s.jsonl", "summary_%s.txt", "distribution_%s.json", "done_%s.json"]
    existing = [str(out / (n % item)) for n in names if (out / (n % item)).exists()]
    if existing:
        print("이미 있는 기록을 덮어쓰지 않는다: %s" % existing, file=sys.stderr)
        return 2

    # px4_msgs 상수가 judge의 값과 같은지 대조한다
    assert VehicleStatus.ARMING_STATE_ARMED == mj.ARMING_STATE_ARMED
    assert VehicleStatus.ARMING_STATE_DISARMED == mj.ARMING_STATE_DISARMED
    assert VehicleStatus.NAVIGATION_STATE_OFFBOARD == mj.NAV_STATE_OFFBOARD
    assert VehicleStatus.NAVIGATION_STATE_AUTO_LOITER == mj.NAV_STATE_AUTO_LOITER
    assert VehicleStatus.NAVIGATION_STATE_AUTO_LAND == mj.NAV_STATE_AUTO_LAND

    # 통과 기준과 실행 인자를 실행 전에 요약 머리에 적는다
    summary = out / ("summary_%s.txt" % item)
    with open(summary, "x") as fh:
        fh.write("# 재실측 %s 요약\n" % item)
        fh.write("run_id %s\ncommit %s dirty %s\nimages %s\nimage_keys %s\n"
                 % (meta["run_id"], meta["commit"], meta["dirty"], meta["images"], meta["image_keys"]))
        if not meta["ok"]:
            fh.write("!! commit unknown 또는 image key 없음. 종료 코드를 2로 끝낸다.\n")
        fh.write("판정 뜻: PASS(0) 기준을 만족한 관측. FAIL(1) 기준과 다른 관측이며 문서의 기대가 반증됐다는 "
                 "뜻이지 PX4 결함이라는 뜻이 아니다. 그 밖(2)은 기계가 판정하지 않음(COND_NOT_REACHED, HOLD_END, "
                 "INCONCLUSIVE, WINDOW_MISSED, PRECONDITION, ERROR, 시도 수 부족, 인프라).\n")
        fh.write("보증 범위: 이 측정은 PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, landed 전환, 상승)만 본다. "
                 "정리 총 소요 9 s 기준은 측정용 CleanupModel의 소요이고 core의 소요를 보증하지 않는다.\n")
        fh.write("실행 인자 %s\n" % json.dumps(args_record(args), sort_keys=True))
        fh.write("\n## 통과 기준 (실행 전에 기록)\n")
        for line in CRITERIA[item]:
            fh.write("- %s\n" % line)
        fh.write("- 정리 총 소요 9 s 미만(상한 12 s에 여유 3 s). 넘으면 상한을 올리지 않고 architect에게 올린다.\n")
        fh.write("- 계획한 시도 수 %d (기준의 최소 %d). 실패한 시도를 빼지 않고 재시도하지 않는다.\n"
                 % (args.attempts, MIN_ATTEMPTS[item]))
        fh.write("- 3회 시도의 실패율 95%% 상한은 약 100%%(3/n)다. 통과는 실패 없음의 증거가 아니다.\n")
        fh.write("- 판정 코드: tests/support/measure_judge.py. 정본: decisions.md 넘김 목록의 px4-engineer 행.\n")
        fh.write("- 이 측정은 Executor 없이 PX4에 직접 명령을 보낸다. 정리 모델은 measure_judge.CleanupModel.\n")

    rclpy.init()
    raw = Px4Raw(veh.px4_ns, veh.sysid)
    rows_all = []
    final_reset = "하지 않음(실행이 중단됨)"
    try:
        raw.start()
        pub = MeasureOnlyPublisher(raw, measure_only=True)
        rig = Rig(raw, pub)
        # /clock이 오기 전의 노드 시각은 0이다. 이 첫 대기만 벽시계로 잰다(sim 시간이 아직 없다).
        t_wall = time.monotonic()
        while not (raw.clock_us() > 0 and raw.now_us() > 0 and raw.last_status() is not None
                   and raw.last_landed() is not None and raw.last_pos() is not None):
            if time.monotonic() - t_wall > 60.0:
                raise RuntimeError("CLOCK_ABSENT 또는 PRECONDITION: /clock 또는 PX4 표본을 벽시계 60 s 안에 받지 못함")
            time.sleep(0.05)
        ulog_dir = st.ulog_path(veh)
        repo_root = Path(__file__).resolve().parents[3]
        with open(out / ("measure_%s.jsonl" % item), "x") as mfh, \
                open(out / ("raw_%s.jsonl" % item), "x") as rfh:
            for a in range(args.attempts):
                wall0 = time.monotonic()
                ros0 = raw.now_us()
                idx = (len(raw.status), len(raw.landed), len(raw.pos), len(raw.acks), len(raw.sends))
                judged = []
                err = None
                try:
                    facts_rows = ATTEMPTS[item](rig, args, a)
                    n_arm = sum(1 for x in raw.sends[idx[4]:] if x["kind"] == "arm")
                    for sub, inj, facts in facts_rows:
                        facts["arm_sends"] = n_arm
                        facts["stop_arm_resend_after_first_armed"] = (
                            STOP_ARM_RESEND_AFTER_FIRST_ARMED if sub == "armed" else None)
                        judged.append((sub, inj, facts, mj.judge_attempt(sub, facts)))
                except Precondition as e:
                    err = ("PRECONDITION", str(e), getattr(e, "facts", None))
                except ClockStalled as e:
                    err = ("CLOCK_STALLED", str(e), None)
                except Exception as e:       # 한 시도의 예외가 기록과 나머지 시도를 막지 않게 한다
                    err = ("ERROR", "%s: %s" % (type(e).__name__, e), {"traceback": traceback.format_exc()})
                ros1 = raw.now_us()
                rig.sp = None
                ulog = newest_ulog(ulog_dir)
                base = {
                    "run_id": meta["run_id"], "commit": meta["commit"], "dirty": meta["dirty"],
                    "images": meta["images"], "image_keys": meta["image_keys"], "attempt": a + 1,
                    "args": args_record(args),
                    "ros_start_us": ros0, "ros_end_us": ros1, "ros_elapsed_s": (ros1 - ros0) / US,
                    "wall_elapsed_s": round(time.monotonic() - wall0, 3),
                    "ulog": None if ulog is None else os.path.relpath(ulog, repo_root),
                }
                if err is not None:
                    f = err[2]
                    row = dict(base, item=nominal_injection(item, a, args)["item"], **{"class": mj.CLASS_DIRECT},
                               injection=nominal_injection(item, a, args), verdict=err[0],
                               inconclusive_kind="",
                               result=err[0], reasons=[err[1]], facts=f, exit_code=exit_code_of(err[0]),
                               armed3_reached=None if not f or "armed3_reached" not in f
                               else f["armed3_reached"],
                               armed_non_offboard=None if not f or "armed_non_offboard" not in f
                               else f["armed_non_offboard"])
                    jwrite(mfh, row)
                    rows_all.append(row)
                    if err[0] == "CLOCK_STALLED":
                        dump_raw(rfh, raw, a + 1, *idx)
                        break
                else:
                    for sub, inj, facts, v in judged:
                        has = "armed_window_ros_us" in facts
                        row = dict(base, item=sub, injection=inj, verdict=v.verdict, result=v.verdict,
                                   inconclusive_kind=v.kind, **{"class": mj.CLASS_DIRECT},
                                   reasons=v.reasons, facts=facts, exit_code=exit_code_of(v.verdict),
                                   armed3_reached=facts["armed3_reached"] if has else None,
                                   armed_non_offboard=facts["armed_non_offboard"] if has else None)
                        jwrite(mfh, row)
                        rows_all.append(row)
                dump_raw(rfh, raw, a + 1, *idx)
                print("attempt %d/%d %s" % (a + 1, args.attempts,
                                            [(r["item"], r["verdict"]) for r in rows_all
                                             if r["attempt"] == a + 1]), flush=True)
        # 마지막 시도 뒤 기체를 안전 상태(DISARMED, landed true)로 되돌린다(--keep이어도)
        try:
            reset_vehicle(rig)
            final_reset = "DISARMED, landed true"
        except (Precondition, ClockStalled) as e:
            final_reset = "실패: %s" % e
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
    with open(out / ("distribution_%s.json" % item), "x") as fh:
        json.dump(dist, fh, indent=1, sort_keys=True)
        fh.write("\n")

    subitems = sorted({r["item"] for r in rows_all})
    arm = mj.judge_armed_criterion(mc.armed_rows(rows_all))
    with open(summary, "a") as fh:
        fh.write("\n## 결과 (실행 뒤)\n")
        for sub in subitems:
            rs = [r for r in rows_all if r["item"] == sub]
            j = mj.judge_run(rs, MIN_ATTEMPTS[item])
            fh.write("%s: 시도 %d(유효 %d), PASS %d, 기준과 다른 관측(exit 1) %d, 그 밖 %d, 유효 시도 수 충분 %s, "
                     "전부 PASS %s, 실패율 95%% 상한 약 %s\n" % (
                         sub, j["n"], j["n_valid"], j["n_pass"], j["n_fail"], j["n_other"], j["enough"],
                         j["all_pass"], "-" if j["upper95_fail_rate"] is None
                         else "%.0f%%" % (100 * min(1.0, j["upper95_fail_rate"]))))
            for r in rs:
                if r["verdict"] != "PASS":
                    fh.write("  시도 %d %s: %s\n" % (r["attempt"], r["verdict"], "; ".join(r["reasons"])))
            tot = [r["facts"]["cleanup_total_s"] for r in rs
                   if r["facts"] and r["facts"].get("cleanup_total_s") is not None]
            if tot:
                fh.write("  정리 총 소요(s): min %.3f max %.3f\n" % (min(tot), max(tot)))
        write_extra_summary(fh, item, rows_all)
        fh.write("마지막 시도 뒤 기체 정리: %s\n" % final_reset)
        fh.write("ARMED 기준(이 실행, 부류별. 최상위는 px4_direct): %s\n" % json.dumps(arm, sort_keys=True))
        if arm["violated"]:
            fh.write("!! OFFBOARD가 아닌 ARMED 표본이 나왔다. 즉시 architect에게 올린다.\n")
    rc = mc.run_status(rows_all, MIN_ATTEMPTS[item], meta_ok=meta["ok"], crit=arm)
    with open(out / ("done_%s.json" % item), "x") as fh:
        json.dump({"rows": len(rows_all), "rc": rc, "meta_ok": meta["ok"], "final_reset": final_reset},
                  fh, sort_keys=True)
        fh.write("\n")
    return rc


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException:       # 처리하지 못한 예외는 2로 끝낸다
        traceback.print_exc()
        rc = 2
    sys.exit(rc)
