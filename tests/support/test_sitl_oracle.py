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

"""1b 판정 함수(sitl_judge의 1b 계약 판정과 정답 판정 절) 단위 테스트. 순수 코드."""
import pytest

from tests.support import sitl_judge as sj
from tests.support import sitl_wait as sw

US = 1_000_000

# 정답 pose 토픽 이름의 사례 표. idsim_sim/test/test_sim_oracle.py의 ORACLE_TOPIC_CASES, ORACLE_TOPIC_INVALID와
# 같은 표다(발행 쪽과 import로 공유하지 않는다. 1b decisions.md 쟁점 5). 한쪽을 바꾸면 다른 쪽도 바꾼다.
ORACLE_TOPIC_CASES = [
    ("px4_1", "/sim/px4_1/pose"),
    ("px4_2", "/sim/px4_2/pose"),
    ("px4_9", "/sim/px4_9/pose"),
]
ORACLE_TOPIC_INVALID = ["", "/px4_1", "px4_1/", "px4/1", "1px4", "px4-1", "px4 1", "px4_1\n", None, 1]


@pytest.mark.parametrize("vehicle_id, topic", ORACLE_TOPIC_CASES)
def test_oracle_pose_topic(vehicle_id, topic):
    assert sj.oracle_pose_topic(vehicle_id) == topic


@pytest.mark.parametrize("vehicle_id", ORACLE_TOPIC_INVALID)
def test_oracle_pose_topic_rejects(vehicle_id):
    with pytest.raises(ValueError):
        sj.oracle_pose_topic(vehicle_id)


def OS(t_s, x, y=0.0, z=0.0):
    return sj.OracleSample(int(t_s * US), int(t_s * US) + 1000, x, y, z)


def T(t_s, x, y=0.0, z=0.0, recv_lag_s=0.01):
    return sj.TargetSample(int(t_s * US), int((t_s + recv_lag_s) * US), x, y, z)


def cats(findings):
    return [c for c, _ in findings]


# --- 보간과 ORACLE_ABSENT, ORACLE_STALE ---

def test_oracle_at_interpolates_between_samples():
    f, p, gap = sj.oracle_at([OS(1.0, 0.0), OS(1.02, 2.0)], int(1.01 * US))
    assert f == [] and p[0] == pytest.approx(1.0) and gap == pytest.approx(0.02)


def test_oracle_at_exact_sample():
    f, p, gap = sj.oracle_at([OS(1.0, 0.0), OS(1.02, 2.0)], int(1.02 * US))
    assert f == [] and p[0] == 2.0 and gap == 0.0


def test_oracle_absent_and_stale():
    assert cats(sj.oracle_at([], 10)[0]) == [sw.ORACLE_ABSENT]
    # 감싸는 표본이 없다(외삽하지 않는다)
    assert cats(sj.oracle_at([OS(1.0, 0.0)], int(1.5 * US))[0]) == [sw.ORACLE_STALE]
    assert cats(sj.oracle_at([OS(1.0, 0.0)], int(0.5 * US))[0]) == [sw.ORACLE_STALE]
    # 앞뒤 간격 0.1 s 초과
    f, p, gap = sj.oracle_at([OS(1.0, 0.0), OS(1.11, 1.0)], int(1.05 * US))
    assert cats(f) == [sw.ORACLE_STALE] and p is None and gap == pytest.approx(0.11)
    # 0.1 s 정확히는 통과
    assert sj.oracle_at([OS(1.0, 0.0), OS(1.1, 1.0)], int(1.05 * US))[0] == []


# --- GOTO 도달 ---

def test_reach_judge_records_signed_excess():
    goal = (10.0, 0.0, 5.0)
    oracle = [OS(1.0, 10.3, 0.0, 5.4), OS(1.02, 10.3, 0.0, 5.4)]
    f, rec = sj.reach_judge(oracle, int(1.01 * US), goal, 0.5)
    assert f == []
    assert rec["d3"] == pytest.approx(0.5) and rec["d_h"] == pytest.approx(0.3) and rec["d_v"] == pytest.approx(0.4)
    assert rec["s"] == pytest.approx(0.0, abs=1e-9) and rec["s_pos"] == pytest.approx(0.0, abs=1e-9)
    f, rec = sj.reach_judge([OS(1.0, 10.1), OS(1.02, 10.1)], int(1.01 * US), (10.0, 0.0, 0.0), 0.5)
    assert rec["s"] == pytest.approx(-0.4) and rec["s_pos"] == 0.0     # 부호 있는 초과량은 0으로 자르지 않는다


def test_reach_judge_mismatch_beyond_r_judge():
    oracle = [OS(1.0, 11.01), OS(1.02, 11.01)]
    f, rec = sj.reach_judge(oracle, int(1.01 * US), (10.0, 0.0, 0.0), 0.5)
    assert cats(f) == [sw.REACH_MISMATCH] and rec["d3"] == pytest.approx(1.01)
    assert sj.reach_judge([OS(1.0, 11.0), OS(1.02, 11.0)], int(1.01 * US), (10.0, 0.0, 0.0), 0.5)[0] == []


def test_reach_judge_propagates_oracle_problems():
    assert cats(sj.reach_judge([], 1, (0, 0, 0), 0.5)[0]) == [sw.ORACLE_ABSENT]


# --- 표적 접근 ---

def _moving_target(t0, t1, v=2.0, dt=0.05):
    out, t = [], t0
    while t <= t1 + 1e-9:
        out.append(T(t, v * t))
        t += dt
    return out


def test_track_judge_uses_interpolated_target_plus_offset():
    targets = _moving_target(0.0, 5.0)
    t_f = int(3.01 * US)
    # 표적은 t_f에 x = 6.02, setpoint 점은 (6.02, 0, 5). 정답은 그 점에서 1.3 m 떨어져 있다(임계 1.0 + 2 x 0.2 = 1.4)
    oracle = [OS(3.0, 6.02 + 1.3, 0.0, 5.0), OS(3.02, 6.02 + 1.3, 0.0, 5.0)]
    f, rec = sj.track_judge(oracle, targets, int(1.0 * US), t_f, (0.0, 0.0, 5.0), 0.5, v_max=2.0)
    assert f == [], f
    assert rec["threshold_m"] == pytest.approx(1.4) and rec["d3"] == pytest.approx(1.3)
    assert rec["s_track"] == pytest.approx(1.3 - 0.5 - 0.4)
    oracle = [OS(3.0, 6.02 + 1.45, 0.0, 5.0), OS(3.02, 6.02 + 1.45, 0.0, 5.0)]
    f, _ = sj.track_judge(oracle, targets, int(1.0 * US), t_f, (0.0, 0.0, 5.0), 0.5, v_max=2.0)
    assert cats(f) == [sw.REACH_MISMATCH]


def test_track_judge_no_target_motion():
    still = [T(t / 20.0, 1.0) for t in range(0, 100)]
    oracle = [OS(3.0, 1.0, 0.0, 5.0), OS(3.02, 1.0, 0.0, 5.0)]
    f, rec = sj.track_judge(oracle, still, int(1.0 * US), int(3.01 * US), (0.0, 0.0, 5.0), 0.5, v_max=2.0)
    assert cats(f) == [sw.NO_TARGET_MOTION] and rec["target_travel_m"] == 0.0


def test_track_judge_does_not_extrapolate_target():
    targets = _moving_target(0.0, 3.0)          # t_f 3.01 s를 감싸는 표본이 없다
    oracle = [OS(3.0, 6.0, 0.0, 5.0), OS(3.02, 6.0, 0.0, 5.0)]
    f, _ = sj.track_judge(oracle, targets, int(1.0 * US), int(3.01 * US), (0.0, 0.0, 5.0), 0.5, v_max=2.0)
    assert cats(f) == [sw.WRONG_RESULT]


def test_tracking_errors_and_target_speed():
    targets = _moving_target(0.0, 2.0)
    oracle = [OS(t / 50.0, 2.0 * t / 50.0, 0.0, 5.2) for t in range(0, 100)]
    r = sj.tracking_errors(oracle, targets, (0.0, 0.0, 5.0), 0, 2 * US)
    assert r["d3"]["max"] == pytest.approx(0.2, abs=1e-3) and r["d_v"]["mean"] == pytest.approx(0.2, abs=1e-6)
    tg = [{"id": "a", "start_s": 0.0, "loop": False, "waypoints": [
        {"t": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}, {"t": 5.0, "x": 10.0, "y": 0.0, "z": 0.0},
        {"t": 11.0, "x": 10.0, "y": 6.0, "z": 0.0}]}]
    assert sj.target_speed_max(tg) == pytest.approx(2.0)


# --- 착륙 ---

def test_landing_judge_rtl_recorded_only_without_r_home():
    ref = (6.0, 7.0, 0.227)
    oracle = [OS(50.0, 6.4, 7.3, 0.23), OS(50.02, 6.4, 7.3, 0.23)]
    f, rec = sj.landing_judge(oracle, int(50.01 * US), ref, rtl=True, r_home=None)
    assert f == [] and rec["r_home_status"] == "recorded_only" and rec["r4_m"] == pytest.approx(0.5)
    f, rec = sj.landing_judge(oracle, int(50.01 * US), ref, rtl=True, r_home=0.45)
    assert cats(f) == [sw.WRONG_RESULT] and rec["r_home_status"] == "checked"
    f, rec = sj.landing_judge(oracle, int(50.01 * US), ref, rtl=False)
    assert f == [] and "r4_m" not in rec


def test_landing_judge_z_both_sides():
    """DISARMED 시점 정답 z와 이륙 직전 정답 z의 차의 절댓값이 0.3 m 안이다(위와 아래 모두)."""
    ref = (0.0, 0.0, 0.227)
    high = [OS(50.0, 0.0, 0.0, 0.6), OS(50.02, 0.0, 0.0, 0.6)]
    f, rec = sj.landing_judge(high, int(50.01 * US), ref, rtl=False)
    assert cats(f) == [sw.WRONG_RESULT] and rec["dz"] == pytest.approx(0.373)
    low = [OS(50.0, 0.0, 0.0, -0.1), OS(50.02, 0.0, 0.0, -0.1)]
    f, rec = sj.landing_judge(low, int(50.01 * US), ref, rtl=False)
    assert cats(f) == [sw.WRONG_RESULT] and rec["dz"] == pytest.approx(-0.327)
    edge = [OS(50.0, 0.0, 0.0, 0.227 - 0.29), OS(50.02, 0.0, 0.0, 0.227 - 0.29)]
    assert sj.landing_judge(edge, int(50.01 * US), ref, rtl=False)[0] == []


def test_landing_judge_uses_r_home_constant_by_default():
    assert sj.R_HOME_M == 0.20
    ref = (0.0, 0.0, 0.227)
    far = [OS(50.0, 0.25, 0.0, 0.227), OS(50.02, 0.25, 0.0, 0.227)]
    f, rec = sj.landing_judge(far, int(50.01 * US), ref, rtl=True)
    assert cats(f) == [sw.WRONG_RESULT] and rec["r_home_status"] == "checked"


def test_last_item_feedback_gaps():
    fbs = [FB(9.05, 0, sj.TYPE_TRACK_ENTITY, count=1), FB(9.55, 0, sj.TYPE_TRACK_ENTITY, count=1),
           FB(9.80, 0, sj.TYPE_TRACK_ENTITY, valid=False, count=1),
           FB(10.30, 0, sj.TYPE_TRACK_ENTITY, valid=False, count=1)]
    assert sj.last_item_feedback_gaps(fbs, 1) == {"prev_valid_s": 0.25, "next_invalid_s": 0.5}
    assert sj.last_item_feedback_gaps(fbs[:2], 1) is None


def test_clock_alignment_stats():
    from tests.support import measure_judge as mj
    st = [mj.StatusSample(1000, 1000 + d, 0, 1, 4, False, 0) for d in (0, 4000, 8000)]
    assert sj.clock_alignment_stats(st) == {"median_s": 0.004, "max_s": 0.008, "n": 3}
    assert sj.clock_alignment_stats([]) is None


# --- t_f, 항목 순서 ---

def FB(stamp_s, idx, typ, valid=True, phase=sj.PHASE_EXECUTING, count=3):
    return sj.FeedbackRec(recv_us=int(stamp_s * US) + 500, goal_id="g", stamp_us=int(stamp_s * US), item_index=idx,
                          item_count=count, item_type=typ, phase=phase, distance_valid=valid, distance_m=1.0)


def test_item_completion_times_exact_and_last_item():
    fbs = [FB(1.0, 0, sj.TYPE_TAKEOFF), FB(5.0, 1, sj.TYPE_GOTO), FB(5.5, 1, sj.TYPE_GOTO),
           FB(9.05, 2, sj.TYPE_TRACK_ENTITY), FB(9.55, 2, sj.TYPE_TRACK_ENTITY),
           FB(10.05, 2, sj.TYPE_TRACK_ENTITY, valid=False), FB(10.55, 2, sj.TYPE_TRACK_ENTITY, valid=False)]
    t = sj.item_completion_times(fbs, 3)
    assert t[0] == (5 * US, True, 5 * US)
    assert t[1] == (int(9.05 * US), True, int(9.05 * US))
    assert t[2] == (int(10.05 * US), True, int(10.05 * US))


def test_item_completion_times_last_item_skips_transient_invalid():
    """실행 중 일시적인 distance_valid 거짓은 완료가 아니다. 마지막 참 뒤의 첫 거짓이 완료 tick이다."""
    fbs = [FB(1.0, 0, sj.TYPE_GOTO, count=1), FB(1.5, 0, sj.TYPE_GOTO, valid=False, count=1),
           FB(2.0, 0, sj.TYPE_GOTO, count=1), FB(2.35, 0, sj.TYPE_GOTO, valid=False, count=1),
           FB(2.85, 0, sj.TYPE_GOTO, valid=False, count=1)]
    assert sj.item_completion_times(fbs, 1) == {0: (int(2.35 * US), True, int(2.35 * US))}


def test_item_completion_times_last_item_not_done():
    fbs = [FB(1.0, 0, sj.TYPE_GOTO, count=1), FB(1.5, 0, sj.TYPE_GOTO, count=1)]
    assert sj.item_completion_times(fbs, 1) == {}


def test_item_order_findings():
    types = [sj.TYPE_TAKEOFF, sj.TYPE_GOTO, sj.TYPE_LAND]
    ok = [FB(1.0, 0, sj.TYPE_TAKEOFF), FB(2.0, 1, sj.TYPE_GOTO), FB(3.0, 2, sj.TYPE_LAND, phase=3)]
    assert sj.item_order_findings(ok, types, 3) == []
    back = ok + [FB(4.0, 1, sj.TYPE_GOTO)]
    assert cats(sj.item_order_findings(back, types, 3)) == [sw.WRONG_RESULT]
    wrong_type = [FB(1.0, 0, sj.TYPE_TAKEOFF), FB(2.0, 1, sj.TYPE_TRACK_ENTITY)]
    assert sj.item_order_findings(wrong_type, types, 1)
    skipped = [FB(1.0, 0, sj.TYPE_TAKEOFF), FB(3.0, 2, sj.TYPE_LAND, phase=3)]
    assert sj.item_order_findings(skipped, types, 3)
    assert sj.item_order_findings([], types, 0)


# --- 기록 도구 ---

def test_stale_ticks_counts_grid_points_without_fresh_sample():
    targets = [T(t / 20.0, 0.0, recv_lag_s=0.01) for t in range(0, 20)]      # 0-0.95 s, 20 Hz
    r = sj.stale_ticks(targets, int(0.1 * US), int(0.9 * US))
    assert r["stale"] == 0 and r["ticks"] == 17
    gap = [x for x in targets if not 0.3 <= x.stamp_us / US <= 0.6]
    r = sj.stale_ticks(gap, int(0.1 * US), int(0.9 * US))
    assert r["stale"] > 0 and all(a is None or a > 0.1 for a in r["stale_ages_s"])


def test_r1_record():
    exp = {"lat": 37.5665, "lon": 126.978, "alt": 38.24}
    r = sj.r1_record(37.5665 + 1e-5, 126.978, 38.0, exp)
    assert r["r1_h_m"] == pytest.approx(1.112, abs=1e-3) and r["r1_v_m"] == pytest.approx(-0.24)


def test_summary_and_quantile():
    s = sj.summary([float(i) for i in range(1, 1001)])
    assert (s["n"], s["p50"], s["p99"], s["p999"], s["max"]) == (1000, 500.0, 990.0, 999.0, 1000.0)
    assert sj.summary([])["n"] == 0
