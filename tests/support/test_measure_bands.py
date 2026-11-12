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

"""measure_bands 단위 테스트((3)의 대역 판별, 최종 판정, 집계). 합성 ULog 표본만 쓴다."""
import pytest

from tests.support import measure_bands as mb
from tests.support import measure_check as mc
from tests.support import measure_judge as mj

T0 = 100_000_000          # t_A (us)
MS = 1000
S = 1_000_000


def ldr(ts, landed=True, ml=True, ige=False, gc=True):
    return {"timestamp": ts, "landed": landed, "maybe_landed": ml, "in_ground_effect": ige,
            "ground_contact": gc}


def ack(ts, result=0, command=400):
    return {"timestamp": ts, "command": command, "result": result}


def cmd(ts, p1=0.0):
    return {"timestamp": ts, "command": 400, "param1": p1}


def thrust_series(ramp_ts=None, until=2 * S):
    """arm 뒤 4 ms 간격 추력. 바닥 -0.001, ramp_ts 뒤 -0.01."""
    out = []
    t = T0
    while t < T0 + until:
        z = -0.01 if (ramp_ts is not None and t >= ramp_ts) else -0.001
        out.append({"timestamp": t, "xyz": [0.0, 0.0, z]})
        t += 4 * MS
    return out


def make_ud(land, acks, cmds, ramp=None, tk4="auto", logged=(), thrust_ramp="auto", thrust=True):
    topics = {
        "vehicle_status": [{"timestamp": T0 - 12 * MS, "arming_state": 1},
                           {"timestamp": T0, "arming_state": 2}],
        "vehicle_land_detected": [ldr(T0 - 500 * MS)] + land,
        "vehicle_command_ack": acks, "vehicle_command": cmds,
        "vehicle_thrust_setpoint": thrust_series(
            ramp + 12 * MS if thrust_ramp == "auto" and ramp is not None else
            (None if thrust_ramp == "auto" else thrust_ramp)) if thrust else [],
        "takeoff_status": ([{"timestamp": ramp, "takeoff_state": 4}]
                           if (tk4 == "auto" and ramp is not None) else
                           ([] if tk4 == "auto" or tk4 is None else [{"timestamp": tk4, "takeoff_state": 4}])),
        "actuator_armed": [{"timestamp": T0, "armed": True}],
        "vehicle_local_position": [{"timestamp": T0 + 100 * MS, "z": -0.2}],
    }
    return mb.UlogData(topics, logged)


def mkrow(fd_ts, delay, live="PASS", end="DISARMED", seq="G", trans=0, hold_span=None, ros_end=None,
          cancel=None, reasons=()):
    facts = {"arm_send": [T0 - 12 * MS, T0 - 12 * MS], "first_disarm_send": None if fd_ts is None else [0, fd_ts],
             "end_reason": end, "branch_sequence": seq, "branch_transitions": trans,
             "cleanup_end_ros_us": fd_ts + S if fd_ts else T0 + S}
    if hold_span is not None:
        facts["hold_observe_span_s"] = hold_span
    return {"item": "3", "attempt": 1, "verdict": live, "reasons": list(reasons), "inconclusive_kind": "",
            "facts": facts, "ros_end_us": ros_end or T0 + 10 * S,
            "injection": {"delay_s_nominal": delay, "cancel_clock_us": fd_ts if cancel is None else cancel}}


def spoolup_ud(r=0, extra_land=()):
    return make_ud(list(extra_land), [ack(T0, 0), ack(T0 + 24 * MS, r)], [cmd(T0 - 12 * MS, 1.0), cmd(T0 + 12 * MS)])


def inner_ud(r=0, delay_us=1235 * MS, p_off=13 * MS, t_ml=None, t_lf=None):
    ramp = T0 + 1016 * MS
    fd = T0 + delay_us
    land = [ldr(ramp, ige=True)]
    if t_ml is not None:
        land.append(ldr(T0 + t_ml, landed=t_lf is None, ml=False))
    if t_lf is not None:
        land.append(ldr(T0 + t_lf, landed=False, ml=False, ige=True))
    return make_ud(land, [ack(T0, 0), ack(fd + p_off, r)], [cmd(T0 - 12 * MS, 1.0), cmd(fd)], ramp=ramp)


# --- 지연 인자 -------------------------------------------------------------------


def test_fixed_delays_are_the_ones_computed_from_t_lf_ref():
    assert list(mb.ITEM3_DELAYS_S) == mb.plan_item3_delays(mb.T_LF_REF["min_s"])
    assert len(mb.ITEM3_DELAYS_S) == 9
    assert mb.ITEM3_DELAYS_S[:2] == (0.0, 0.5)
    assert mb.ITEM3_DELAYS_S[2:6] == (1.074, 1.223, 1.372, 1.521)
    assert mb.ITEM3_DELAYS_S[6:] == (1.644, 1.694, 1.724)


def test_planned_band():
    assert [mb.planned_band(d) for d in mb.ITEM3_DELAYS_S] == (
        ["spoolup"] * 2 + ["inner"] * 4 + ["boundary"] * 3)


def test_item3_accepts_only_the_fixed_list():
    assert mb.parse_item3_delays(",".join(str(x) for x in mb.ITEM3_DELAYS_S)) == list(mb.ITEM3_DELAYS_S)
    assert mb.parse_item3_delays("0,1.724") == [0.0, 1.724]
    for bad in ("0.05", "0,0.1", "2.0", "1.3", "-0.1"):       # (5)의 0-0.2 범위 값도 (3)에는 없다
        with pytest.raises(ValueError):
            mb.parse_item3_delays(bad)


def test_item3_delay_arg_rejects_garbage_duplicates_and_empty():
    for bad in ("a,b", "", "0,0", "0,,0.5"):
        with pytest.raises(ValueError):
            mb.parse_item3_delays(bad)


def test_image_key_must_match_reference():
    ok = [{"image": "px4", "key": "81678f535f7e4b05"}, {"image": "sim-base", "key": "cd6a22462ff15990"},
          {"image": "ros-ws", "key": "anything"}]
    assert mb.image_key_problem(ok) is None
    assert "px4" in mb.image_key_problem([{"image": "px4", "key": "dead"}, ok[1]])
    assert "armed" in mb.image_key_problem([{"image": "px4", "key": "dead"}, ok[1]])
    assert mb.image_key_problem(None) is not None
    assert mb.image_key_problem([]) is not None


# --- 대역 분류 -------------------------------------------------------------------


def test_classify_by_t_p_not_by_planned_delay():
    ref = 1.744
    ld_true = ldr(0)
    assert mb.classify_band(T0, None, T0 + 12 * MS, ld_true, ref) == ("spoolup", False)
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 500 * MS, ld_true, ref) == ("spoolup", False)   # ramp > t_p
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 1300 * MS, ld_true, ref) == ("inner", False)
    # 계획은 내부 지연(1.521)이었지만 첫 disarm이 늦게 처리되어 경계 시간대(>= 1.644)
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 1644 * MS, ld_true, ref) == ("boundary", False)
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 1643 * MS, ld_true, ref) == ("inner", False)
    # 반대로 계획은 spoolup(0.5)이었어도 늦게 처리되어 rampup 안이면 inner
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 1100 * MS, ld_true, ref)[0] == "inner"


def test_inner_time_with_landed_false_is_boundary_and_flagged():
    band, below = mb.classify_band(T0, T0 + 1016 * MS, T0 + 1500 * MS, ldr(0, landed=False, ml=False), 1.744)
    assert (band, below) == ("boundary", True)
    # 경계 시간대의 landed false는 플래그가 없다
    assert mb.classify_band(T0, T0 + 1016 * MS, T0 + 1700 * MS, ldr(0, landed=False, ml=False), 1.744) == (
        "boundary", False)


def test_unclassifiable_without_ld_or_with_landed_false_before_ramp():
    assert mb.classify_band(T0, None, T0 + 12 * MS, None, 1.744) == (None, False)
    assert mb.classify_band(T0, None, T0 + 12 * MS, ldr(0, landed=False), 1.744) == (None, False)


# --- ULog 분석 -------------------------------------------------------------------


def test_analyze_spoolup_row():
    row = mkrow(T0 + 12 * MS, 0.0)
    an = mb.analyze_row(row, spoolup_ud())
    assert an["t_A"] == T0 and an["t_p"] == T0 + 24 * MS and an["r_p"] == 0
    assert an["t_ramp"] is None and an["t_lf"] is None and an["t_ml"] is None
    assert an["band"] == "spoolup" and an["first_disarm_lost"] is False
    assert an["tp_minus_tA_s"] == pytest.approx(0.024)
    assert an["accepted_400_before_tp"] == 0     # t_A와 같은 timestamp의 arm ack는 t_p가 아니다
    assert an["ramp_problems"] == [] and an["consistency_problems"] == []
    assert an["thrust_at_tp"] == pytest.approx(-0.001)
    assert an["ld_p"]["landed"] is True


def test_arm_ack_at_t_a_is_not_the_first_disarm_ack():
    ud = spoolup_ud()
    assert mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), ud)["t_p"] == T0 + 24 * MS


def test_first_disarm_lost_when_command_missing_in_ulog():
    ud = make_ud([], [ack(T0, 0), ack(T0 + 520 * MS, 0)], [cmd(T0 - 12 * MS, 1.0), cmd(T0 + 512 * MS)])
    an = mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), ud)       # 보낸 ts T0+12 ms는 ULog에 없고 재전송만 있다
    assert an["first_disarm_lost"] is True
    # param1 1.0(arm)은 disarm으로 세지 않는다
    ud2 = make_ud([], [ack(T0, 0)], [cmd(T0 + 12 * MS, 1.0)])
    assert mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), ud2)["first_disarm_lost"] is True


def test_ramp_cross_checks_and_mismatch():
    ok = inner_ud()
    an = mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), ok)
    assert an["t_ramp"] == T0 + 1016 * MS and an["ramp_problems"] == []
    assert an["thrust_drop_ts"] == T0 + 1028 * MS and an["takeoff4_ts"] == T0 + 1016 * MS
    assert an["band"] == "inner"
    # takeoff_state 4가 t_ramp보다 9 ms 뒤
    bad_tk = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                     [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, tk4=T0 + 1025 * MS)
    assert any("takeoff_state 4" in p for p in mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), bad_tk)["ramp_problems"])
    # 8 ms는 허용
    ok8 = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                  [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, tk4=T0 + 1024 * MS)
    assert mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), ok8)["ramp_problems"] == []
    # 추력 하락이 t_ramp 뒤 41 ms
    late = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                   [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, thrust_ramp=T0 + 1057 * MS)
    assert any("추력 하락" in p for p in mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), late)["ramp_problems"])
    # 추력 하락이 t_ramp 앞 24 ms(4 ms 격자)
    early = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                    [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, thrust_ramp=T0 + 990 * MS)
    assert any("추력 하락" in p for p in mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), early)["ramp_problems"])
    # in_ground_effect 표본이 없는데 t_p 이전에 추력이 올랐다
    none_ramp = make_ud([], [ack(T0, 0), ack(T0 + 1248 * MS, 0)], [cmd(T0 + 1235 * MS)],
                        ramp=None, thrust_ramp=T0 + 1030 * MS, tk4=None)
    assert any("in_ground_effect" in p for p in mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), none_ramp)["ramp_problems"])
    # takeoff_state 4는 있는데 in_ground_effect true가 없다
    only_tk = make_ud([], [ack(T0, 0), ack(T0 + 24 * MS, 0)], [cmd(T0 + 12 * MS)], tk4=T0 + 1016 * MS)
    assert mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), only_tk)["ramp_problems"] != []


def test_missing_takeoff_status_and_missing_thrust_samples_are_not_mismatch():
    no_tk = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                    [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, tk4=None)
    assert mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), no_tk)["ramp_problems"] == []
    no_th = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                    [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, thrust=False)
    an = mb.analyze_row(mkrow(T0 + 1235 * MS, 1.223), no_th)
    assert an["ramp_problems"] == [] and an["thrust_samples"] == 0


def test_no_armed_sample_is_an_error():
    ud = mb.UlogData({"vehicle_status": [{"timestamp": T0, "arming_state": 1}]})
    an = mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), ud)
    assert "error" in an
    assert mb.final_verdict_item3(mkrow(T0 + 12 * MS, 0.0), an)[0] == "INCONCLUSIVE"


# --- 최종 판정 -------------------------------------------------------------------


def final(row, ud):
    return mb.final_verdict_item3(row, mb.analyze_row(row, ud))[0]


def test_spoolup_and_inner_pass():
    assert final(mkrow(T0 + 12 * MS, 0.0), spoolup_ud()) == "PASS"
    assert final(mkrow(T0 + 1235 * MS, 1.223), inner_ud()) == "PASS"


def test_inner_hold_is_m5_contradicted_exit1():
    row = mkrow(T0 + 1235 * MS, 1.223, live="HOLD_END", end="HOLD", seq="GA", trans=1, hold_span=60.0)
    v, why, _ = mb.final_verdict_item3(row, mb.analyze_row(row, inner_ud()))
    assert v == "M5_CONTRADICTED" and v in mj.EXIT1_VERDICTS
    assert any("공중 분기" in w for w in why)


def test_inner_g_a_g_is_m5_contradicted_even_though_it_ended_disarmed():
    row = mkrow(T0 + 1235 * MS, 1.223, live="PASS", end="DISARMED", seq="GAG", trans=2)
    assert final(row, inner_ud()) == "M5_CONTRADICTED"


def test_spoolup_not_accepted_is_m5_contradicted_but_consistency_does_not_apply_to_other_results():
    # DENIED(2)는 일관성 검사 대상이 아니고 첫 disarm이 spoolup에서 처리되었는데 ACCEPTED가 아니다
    row = mkrow(T0 + 12 * MS, 0.0)
    assert final(row, spoolup_ud(r=2)) == "M5_CONTRADICTED"


def test_boundary_ground_disarm_passes_and_boundary_hold_is_hold_end_exit2():
    # 경계 대역: t_p - t_A = 1.748 s, ACCEPTED, t_ml이 4 ms 뒤(t_p <= t_ml + 12 ms)
    ud = inner_ud(delay_us=1735 * MS, p_off=13 * MS, t_ml=1752 * MS)
    assert mb.analyze_row(mkrow(T0 + 1735 * MS, 1.724), ud)["band"] == "boundary"
    assert final(mkrow(T0 + 1735 * MS, 1.724), ud) == "PASS"
    # 경계에서 landed false가 먼저 나오고 거부 -> Hold
    land = [ldr(T0 + 1016 * MS, ige=True), ldr(T0 + 1744 * MS, landed=False, ml=False, ige=True)]
    rej = make_ud(land, [ack(T0, 0), ack(T0 + 1750 * MS, 1)], [cmd(T0 + 1735 * MS)], ramp=T0 + 1016 * MS,
                  logged=[{"level": 6, "ts": T0 + 1750 * MS, "msg": "[commander] Disarming denied: not landed\t"}])
    row = mkrow(T0 + 1735 * MS, 1.724, live="HOLD_END", end="HOLD", seq="GA", trans=1, hold_span=60.0)
    v, why, _ = mb.final_verdict_item3(row, mb.analyze_row(row, rej))
    assert v == "HOLD_END" and v not in mj.EXIT1_VERDICTS


def test_consistency_accepted_after_maybe_landed_plus_12ms_is_exit1():
    ud = inner_ud(delay_us=1735 * MS, p_off=13 * MS, t_ml=1735 * MS)     # t_ml 1735, t_p 1748 = t_ml + 13 ms
    assert final(mkrow(T0 + 1735 * MS, 1.724), ud) == "M5_INCONSISTENT"
    ok = inner_ud(delay_us=1735 * MS, p_off=13 * MS, t_ml=1736 * MS)      # t_p = t_ml + 12 ms는 허용
    assert final(mkrow(T0 + 1735 * MS, 1.724), ok) == "PASS"


def test_consistency_rejected_requires_maybe_landed_false_and_denied_log():
    land = [ldr(T0 + 1016 * MS, ige=True), ldr(T0 + 1744 * MS, landed=False, ml=False, ige=True)]
    log_ok = [{"level": 6, "ts": T0 + 1750 * MS - 4 * MS, "msg": "[commander] Disarming denied: not landed"}]
    mk = lambda t_p, logged: make_ud(land, [ack(T0, 0), ack(t_p, 1)], [cmd(T0 + 1735 * MS)],     # noqa: E731
                                     ramp=T0 + 1016 * MS, logged=logged)
    row = mkrow(T0 + 1735 * MS, 1.724, live="HOLD_END", end="HOLD", seq="GA", trans=1, hold_span=60.0)
    assert mb.final_verdict_item3(row, mb.analyze_row(row, mk(T0 + 1750 * MS, log_ok)))[0] == "HOLD_END"
    # 로그가 없다
    assert mb.final_verdict_item3(row, mb.analyze_row(row, mk(T0 + 1750 * MS, [])))[0] == "M5_INCONSISTENT"
    # 로그가 5 ms 앞이다
    late_log = [{"level": 6, "ts": T0 + 1745 * MS, "msg": "[commander] Disarming denied: not landed"}]
    assert mb.final_verdict_item3(row, mb.analyze_row(row, mk(T0 + 1750 * MS, late_log)))[0] == "M5_INCONSISTENT"
    # t_p가 t_ml보다 앞인데 거부됨(maybe_landed가 아직 true였다)
    assert mb.final_verdict_item3(row, mb.analyze_row(row, mk(T0 + 1740 * MS, [
        {"level": 6, "ts": T0 + 1740 * MS, "msg": "Disarming denied: not landed"}])))[0] == "M5_INCONSISTENT"
    # maybe_landed가 false가 된 적 없는데 거부됨
    never = make_ud([], [ack(T0, 0), ack(T0 + 24 * MS, 1)], [cmd(T0 + 12 * MS)],
                    logged=[{"level": 6, "ts": T0 + 24 * MS, "msg": "Disarming denied: not landed"}])
    assert final(mkrow(T0 + 12 * MS, 0.0), never) == "M5_INCONSISTENT"


def test_first_disarm_lost_is_inconclusive_exit2():
    ud = make_ud([], [ack(T0, 0), ack(T0 + 520 * MS, 0)], [cmd(T0 - 12 * MS, 1.0), cmd(T0 + 512 * MS)])
    v, _, kind = mb.final_verdict_item3(mkrow(T0 + 12 * MS, 0.0), mb.analyze_row(mkrow(T0 + 12 * MS, 0.0), ud))
    assert v == "INCONCLUSIVE" and kind == "FIRST_DISARM_LOST" and v not in mj.EXIT1_VERDICTS


def test_ramp_mismatch_is_inconclusive_exit2():
    bad = make_ud([ldr(T0 + 1016 * MS, ige=True)], [ack(T0, 0), ack(T0 + 1248 * MS, 0)],
                  [cmd(T0 + 1235 * MS)], ramp=T0 + 1016 * MS, thrust_ramp=T0 + 1100 * MS)
    row = mkrow(T0 + 1235 * MS, 1.223)
    v, why, kind = mb.final_verdict_item3(row, mb.analyze_row(row, bad))
    assert (v, kind) == ("INCONCLUSIVE", "RAMP_MISMATCH") and "t_ramp 판별 불일치" in why[0]


def test_consistency_failure_beats_inconclusive():
    # 첫 disarm 유실(2)이어도 ack 자체의 일관성 위반(1)이 앞선다
    ud = make_ud([], [ack(T0, 0), ack(T0 + 520 * MS, 1)], [cmd(T0 + 512 * MS)])
    assert final(mkrow(T0 + 12 * MS, 0.0), ud) == "M5_INCONSISTENT"


def test_window_missed_by_ulog_even_if_ros_said_ok_and_window_independent_checks_stay():
    # 취소 전송 /clock(= 첫 disarm ts)이 t_lf보다 뒤
    land = [ldr(T0 + 1016 * MS, ige=True), ldr(T0 + 1744 * MS, landed=False, ml=False, ige=True)]
    ud = make_ud(land, [ack(T0, 0), ack(T0 + 1760 * MS, 1)], [cmd(T0 + 1748 * MS)], ramp=T0 + 1016 * MS,
                 logged=[{"level": 6, "ts": T0 + 1760 * MS, "msg": "Disarming denied: not landed"}])
    row = mkrow(T0 + 1748 * MS, 1.724, live="PASS", end="DISARMED")
    assert final(row, ud) == "WINDOW_MISSED"
    # live가 FAIL(창과 무관한 기준 위반)이면 그대로 FAIL
    assert final(mkrow(T0 + 1748 * MS, 1.724, live="FAIL", reasons=["상승"]), ud) == "FAIL"
    # live WINDOW_MISSED인데 ULog는 창 안이면 끝난 방식(지상 DISARMED = PASS)으로 되돌린다
    assert final(mkrow(T0 + 12 * MS, 0.0, live="WINDOW_MISSED"), spoolup_ud()) == "PASS"


def test_hold_observation_landed_true_is_m3_contradicted_exit1_and_maybe_landed_only_is_exit2():
    base = [ldr(T0 + 1016 * MS, ige=True), ldr(T0 + 1744 * MS, landed=False, ml=False, ige=True)]
    cleanup_end = T0 + 3 * S
    row = mkrow(T0 + 1735 * MS, 1.724, live="HOLD_END", end="HOLD", seq="GA", trans=1, hold_span=60.0)
    row["facts"]["cleanup_end_ros_us"] = cleanup_end
    log = [{"level": 6, "ts": T0 + 1750 * MS, "msg": "Disarming denied: not landed"}]

    def ud_with(extra):
        return make_ud(base + extra, [ack(T0, 0), ack(T0 + 1750 * MS, 1)], [cmd(T0 + 1735 * MS)],
                       ramp=T0 + 1016 * MS, logged=log)
    landed_true = ud_with([ldr(cleanup_end + 30 * S, landed=True, ml=True)])
    v, _, _ = mb.final_verdict_item3(row, mb.analyze_row(row, landed_true))
    assert v == "M3_CONTRADICTED" and v in mj.EXIT1_VERDICTS
    maybe_only = ud_with([ldr(cleanup_end + 30 * S, landed=False, ml=True)])
    v, why, kind = mb.final_verdict_item3(row, mb.analyze_row(row, maybe_only))
    assert v == "INCONCLUSIVE" and kind == "MAYBE_LANDED" and "maybe_landed" in why[0]
    clean = ud_with([])
    assert mb.final_verdict_item3(row, mb.analyze_row(row, clean))[0] == "HOLD_END"
    # 관찰 구간 밖의 true는 보지 않는다(60 s 뒤)
    outside = ud_with([ldr(cleanup_end + 61 * S, landed=True, ml=True)])
    assert mb.final_verdict_item3(row, mb.analyze_row(row, outside))[0] == "HOLD_END"


def test_2b_hold_observation_from_ulog():
    row = {"verdict": "COND_NOT_REACHED", "reasons": ["x"], "inconclusive_kind": ""}
    ud = mb.UlogData({"vehicle_land_detected": [ldr(S, landed=False, ml=False), ldr(20 * S, landed=True)]})
    obs = mb.hold_observation(ud, 0, 60 * S)
    assert mb.final_verdict_2b(row, obs)[0] == "M3_CONTRADICTED"
    ud2 = mb.UlogData({"vehicle_land_detected": [ldr(S, landed=False, ml=False), ldr(20 * S, landed=False, ml=True)]})
    v, _, kind = mb.final_verdict_2b(row, mb.hold_observation(ud2, 0, 60 * S))
    assert (v, kind) == ("INCONCLUSIVE", "MAYBE_LANDED")
    ud3 = mb.UlogData({"vehicle_land_detected": [ldr(S, landed=False, ml=False)]})
    assert mb.final_verdict_2b(row, mb.hold_observation(ud3, 0, 60 * S))[0] == "COND_NOT_REACHED"
    # live가 이미 M3_CONTRADICTED이면 그대로
    assert mb.final_verdict_2b(dict(row, verdict="M3_CONTRADICTED"), None)[0] == "M3_CONTRADICTED"


def test_t_lf_samples_per_arm_event():
    topics = {"vehicle_status": [{"timestamp": 0, "arming_state": 1}, {"timestamp": 100, "arming_state": 2},
                                 {"timestamp": 400, "arming_state": 1}, {"timestamp": 1000, "arming_state": 2},
                                 {"timestamp": 1500, "arming_state": 2}],
              "vehicle_land_detected": [ldr(50), ldr(200), ldr(1800, landed=False)]}
    # 첫 arm은 disarm 전에 landed false가 없어 표본이 없다. 둘째는 800
    ud = mb.UlogData(topics)
    assert mb.t_lf_samples(ud) == [800 / S]


# --- 집계 ------------------------------------------------------------------------


def rows_for(plan):
    """plan: [(지연값, 계획 대역 안에서의 verdict)] -> (rows, finals, analyses). 실제 대역은 계획 대역과 같다."""
    rows, finals, an = [], {}, {}
    for i, (d, v, band) in enumerate(plan, 1):
        rows.append({"item": "3", "attempt": i, "verdict": "PASS", "injection": {"delay_s_nominal": d},
                     "facts": {"branch_sequence": "GA" if v in ("HOLD_END", "M5_CONTRADICTED") else "G"}})
        finals[("3", i)] = v
        an[i] = {"band": band}
    return rows, finals, an


def full_plan(verdict_boundary="PASS"):
    plan = []
    for d in mb.ITEM3_DELAYS_S:
        b = mb.planned_band(d)
        for _ in range(mb.REPEATS):
            plan.append((d, verdict_boundary if b == "boundary" else "PASS", b))
    return plan


def test_full_plan_meets_every_band():
    rows, finals, an = rows_for(full_plan())
    s = mb.band_summary(rows, finals, an)
    assert s["all_met"] is True
    assert [s["bands"][b]["valid"] for b in mb.BANDS] == [6, 12, 9]
    assert s["boundary_aerial_none"] is True
    assert "경계에서 공중 분기는 생기지 않았다(확인되지 않음)" in mb.top_lines(s)[-1]


def test_boundary_hold_counts_as_valid_but_enough_is_false_and_exit_is_2():
    rows, finals, an = rows_for(full_plan("HOLD_END"))
    s = mb.band_summary(rows, finals, an)
    assert s["bands"]["boundary"]["valid"] == 9 and s["bands"]["boundary"]["aerial"] == 9
    assert s["boundary_aerial_none"] is False
    all_rows = [{"item": "3", "attempt": r["attempt"], "verdict": "HOLD_END" if finals[("3", r["attempt"])] == "HOLD_END"
                 else "PASS", "injection": r["injection"]} for r in rows]
    summ = mc.final_summary(all_rows, finals, analyses=an)
    assert summ["3"]["enough"] is False and summ["3"]["n_exit1"] == 0
    ok = {"violated": False, "violated_any_class": False, "ulog_total_samples": 3, "enough": True}
    okrow = {"item": "3", "attempt": 1, "ros_missing_in_ulog": 0, "ulog_samples_in_range": 3,
             "ros_field_mismatch": [], "ulog_armed_non_offboard": 0, "ulog_flight_armed_non_offboard": 0,
             "ulog_only": 0, "evidence_pending": False}
    assert mc.crosscheck_status([okrow], ok, summary=summ) == 2


def test_full_pass_plan_gives_zero():
    rows, finals, an = rows_for(full_plan())
    all_rows = [{"item": "3", "attempt": r["attempt"], "verdict": "PASS", "injection": r["injection"]} for r in rows]
    summ = mc.final_summary(all_rows, finals, analyses=an)
    ok = {"violated": False, "violated_any_class": False, "ulog_total_samples": 3, "enough": True}
    okrow = {"item": "3", "attempt": 1, "ros_missing_in_ulog": 0, "ulog_samples_in_range": 3,
             "ros_field_mismatch": [], "ulog_armed_non_offboard": 0, "ulog_flight_armed_non_offboard": 0,
             "ulog_only": 0, "evidence_pending": False}
    assert summ["3"]["enough"] is True
    assert mc.crosscheck_status([okrow], ok, summary=summ) == 0


def test_below_minimum_per_band_is_not_enough_and_per_delay_minimum_is_checked():
    plan = [p for p in full_plan() if p[2] != "inner" or p[0] != 1.223]       # 내부 지연값 하나를 통째로 뺌
    rows, finals, an = rows_for(plan)
    s = mb.band_summary(rows, finals, an)
    assert s["bands"]["inner"]["valid"] == 9 and s["bands"]["inner"]["met"] is False
    assert s["bands"]["inner"]["per_planned_delay_valid"]["1.223"] == 0
    # 한 지연값이 1회뿐
    plan2 = full_plan()
    plan2 = [p for i, p in enumerate(plan2) if not (p[0] == 0.5 and i % 3 != 0 and p[2] == "spoolup")]
    s2 = mb.band_summary(*rows_for(plan2))
    assert s2["bands"]["spoolup"]["per_planned_delay_valid"]["0.5"] == 1 and s2["bands"]["spoolup"]["met"] is False
    # 합계 미달
    s3 = mb.band_summary(*rows_for([p for p in full_plan() if p[2] != "boundary"][:-2] + full_plan()[-3:-2]))
    assert s3["all_met"] is False


def test_actual_band_counts_not_planned_band():
    # 계획은 내부 지연(1.521)인데 실제 대역이 경계였던 회는 내부 유효 시도에 들어가지 않는다
    plan = full_plan()
    plan = [(d, v, "boundary" if d == 1.521 else b) for d, v, b in plan]
    s = mb.band_summary(*rows_for(plan))
    assert s["bands"]["inner"]["per_planned_delay_valid"]["1.521"] == 0
    assert s["bands"]["inner"]["met"] is False
    assert s["bands"]["boundary"]["valid"] == 12


def test_excluded_and_unclassified_rows_are_not_valid():
    plan = full_plan()
    rows, finals, an = rows_for(plan)
    finals[("3", 1)] = "WINDOW_MISSED"
    an[2] = {"band": None}
    finals[("3", 2)] = "INCONCLUSIVE"
    s = mb.band_summary(rows, finals, an)
    assert s["unclassified"]["n"] == 1
    assert s["bands"]["spoolup"]["excluded"] == 1 and s["bands"]["spoolup"]["valid"] == 4


def test_exit1_beats_exit2_for_m5_contradicted_with_shortage():
    plan = full_plan()[:5]
    rows, finals, an = rows_for(plan)
    finals[("3", 1)] = "M5_CONTRADICTED"
    all_rows = [{"item": "3", "attempt": r["attempt"], "verdict": finals[("3", r["attempt"])],
                 "injection": r["injection"]} for r in rows]
    summ = mc.final_summary(all_rows, finals, analyses=an)
    assert summ["3"]["n_exit1"] == 1 and summ["3"]["enough"] is False
    ok = {"violated": False, "violated_any_class": False, "ulog_total_samples": 3, "enough": False}
    okrow = {"item": "3", "attempt": 1, "ros_missing_in_ulog": 0, "ulog_samples_in_range": 3,
             "ros_field_mismatch": [], "ulog_armed_non_offboard": 0, "ulog_flight_armed_non_offboard": 0,
             "ulog_only": 0, "evidence_pending": False}
    assert mc.crosscheck_status([okrow], ok, summary=summ) == 1


def test_item3_without_ulog_analysis_is_never_enough():
    rows = [{"item": "3", "attempt": i, "verdict": "PASS", "injection": None} for i in range(1, 28)]
    assert mc.final_summary(rows, {})["3"]["enough"] is False


def test_new_verdicts_are_exit1_and_valid():
    for v in ("M5_CONTRADICTED", "M5_INCONSISTENT"):
        assert v in mj.EXIT1_VERDICTS and v in mj.VALID_VERDICTS
    assert "HOLD_END" not in mj.VALID_VERDICTS and "HOLD_END" not in mj.EXIT1_VERDICTS
    assert mc.run_status([{"item": "3", "verdict": "M5_CONTRADICTED"}], 3) == 1


# --- 요약 문장 -------------------------------------------------------------------


def test_top_block_is_inserted_after_title_and_replaced_on_rerun():
    s = mb.band_summary(*rows_for(full_plan()))
    text = "# 재실측 item3 요약\nrun_id x\n"
    once = mb.insert_top_block(text, mb.top_lines(s))
    assert once.splitlines()[0] == "# 재실측 item3 요약" and once.splitlines()[1] == mb.TOP_BEGIN
    twice = mb.insert_top_block(once, mb.top_lines(s))
    assert twice == once and twice.count(mb.TOP_BEGIN) == 1 and twice.endswith("run_id x\n")


def test_header_lines_carry_delays_and_sources():
    lines = mb.header_lines(list(mb.ITEM3_DELAYS_S), 27, [{"image": "px4", "key": "81678f535f7e4b05"}])
    text = "\n".join(lines)
    for d in mb.ITEM3_DELAYS_S:
        assert str(d) in text
    for needle in ("T_r = 1.0 s", "COM_SPOOLUP_TIME", mb.T_LF_REF["run_id"], "81678f535f7e4b05", "13", "1.744",
                   "합 27회"):
        assert needle in text


def test_delay_table_lines_have_all_fields():
    row = mkrow(T0 + 12 * MS, 0.0)
    an = mb.analyze_row(row, spoolup_ud())
    lines = mb.delay_table_lines([row], {("3", 1): "PASS"}, {1: an})
    assert "대역 spoolup" in lines[1] and "r_p 0" in lines[1] and "first_disarm_lost False" in lines[1]
    assert "t_p-t_A 0.024" in lines[1]


def test_texts_use_only_ascii_and_hangul():
    import re
    from pathlib import Path
    for name in ("measure_bands.py", "test_measure_bands.py"):
        txt = (Path(__file__).parent / name).read_text(encoding="utf-8")
        assert not re.search(r"[^\x00-\x7F가-힣]", txt), name
