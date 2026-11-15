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

"""calibration(b와 R_home 보정 계산) 단위 테스트. 기준값은 decisions.md 쟁점 5의 [계산]과 scipy 1.11.4."""
import math
from statistics import NormalDist

import pytest

from tests.support import calibration as cal
from tests.support import sitl_judge as sj


def test_k_for_30_boots_is_4237():
    """부팅 30회, m = 9(신뢰 95%, 사건당 커버리지 1 - 0.005 / 9)의 비중심 t 허용계수가 4.237이다(쟁점 5)."""
    assert sj.M_EVENTS == 9
    assert round(cal.tolerance_k(30), 3) == 4.237


def test_k_other_sizes_and_small_n():
    # scipy.stats.nct.ppf(0.95, n - 1, z_p sqrt(n)) / sqrt(n)로 낸 값
    assert cal.tolerance_k(10) == pytest.approx(5.478092438, abs=1e-6)
    assert cal.tolerance_k(100) == pytest.approx(3.731050233, abs=1e-6)
    assert cal.tolerance_k(1) is None


def test_rayleigh_qf_for_30_boots_is_4080():
    """m_home = 2, 부팅 30회의 q x f가 4.080이다(쟁점 5)."""
    assert sj.M_HOME == 2
    q, f = cal.rayleigh_qf(30)
    assert q == pytest.approx(math.sqrt(-2 * math.log(0.0025)))
    assert round(q * f, 3) == 4.080
    assert cal.chi2_ppf(0.05, 60) == pytest.approx(43.18795845, abs=1e-6)


FIXED = [((i * 37) % 101) / 100.0 + (i % 7) * 0.03 for i in range(40)]


def test_shapiro_wilk_matches_scipy_reference():
    w, p = cal.shapiro_wilk(FIXED)
    assert w == pytest.approx(0.9704713821, abs=1e-5) and p == pytest.approx(0.3724536896, abs=1e-3)
    assert cal.shapiro_wilk(FIXED[:11]) == (None, None)
    assert cal.shapiro_wilk([1.0] * 20) == (None, None)


def test_shapiro_wilk_against_scipy_when_available():
    stats = pytest.importorskip("scipy.stats")
    nd = NormalDist()
    for n in (12, 30, 210):
        x = [nd.inv_cdf((i + 0.5) / n) + 0.1 * math.sin(i) for i in range(n)]
        w, p = cal.shapiro_wilk(x)
        r = stats.shapiro(x)
        assert w == pytest.approx(r.statistic, abs=1e-5) and p == pytest.approx(r.pvalue, abs=2e-3)


def test_ceil_step():
    assert cal.ceil_step(0.30) == 0.30
    assert cal.ceil_step(0.3000001) == 0.35
    assert cal.ceil_step(0.41) == 0.45


def _events(s_vals, st_vals, r4_vals, speed=2.0, acc=0.5):
    ev = [{"kind": "reach", "s": v, "d3": v + acc, "d_h": v + acc, "speed_h_mps": speed + v} for v in s_vals]
    ev += [{"kind": "track", "s_track": v, "d3": v + acc + 0.4, "threshold_m": 1.4, "t_f_exact": True}
           for v in st_vals]
    ev += [{"kind": "landing", "rtl": True, "r4_m": r, "landing": [r, 0.0, 0.2], "ref": [0.0, 0.0, 0.2]}
           for r in r4_vals]
    return ev


def _runs(n, failed=0, s_shift=0.0):
    nd = NormalDist()
    runs = []
    for b in range(n):
        s = [s_shift + 0.25 + 0.05 * nd.inv_cdf((b * 7 + i + 0.5) / (7 * n)) for i in range(7)]
        st = [-0.35 + 0.1 * nd.inv_cdf((b * 2 + i + 0.5) / (2 * n)) for i in range(2)]
        r4 = [0.03 + 0.001 * ((b + i) % 5) for i in range(2)]
        runs.append(("r%d" % b, {"passed": True}, _events(s, st, r4)))
    runs += [("bad%d" % i, {"passed": False}, _events([5.0], [], [])) for i in range(failed)]
    return runs


def test_calibrate_u18_all_samples_within_b():
    r = cal.calibrate(_runs(30, failed=1))
    assert r["boots"] == 30 and r["skipped_runs"] == ["bad0"] and r["goto"]["n"] == 210 and r["s_track"]["n"] == 60
    assert r["b"] == sj.B_M == 0.5 and r["acceptance_radius_m"] == pytest.approx(0.5)
    assert r["goto_over_b"] == 0 and r["s_track_over_b"] == 0 and r["reach_outside"] == 0
    assert r["accepted"], r["reject_reasons"]
    assert r["b_over_warn"] and not r["b_over_max"] and r["flags"]          # 0.5 > 0.35: PR 본문에 적는다
    # 정규 모형은 기록만 한다
    nm = r["normal_model"]
    assert nm["status"] == "recorded_only" and nm["k"] == pytest.approx(4.237, abs=1e-3)
    assert r["r_home_candidate"] == cal.ceil_step(r["q"] * r["f"] * r["sigma_hat"])
    sp = r["goto_speed"]
    assert sp["corr_d_h_speed"] == pytest.approx(1.0) and sum(x["n"] for x in sp["bins"]) == 210


def test_calibrate_rejects_sample_over_b_and_few_boots():
    r = cal.calibrate(_runs(30, s_shift=0.15))      # 위꼬리가 0.5를 넘는다
    assert not r["accepted"] and r["goto_over_b"] > 0
    assert any("GOTO s" in x for x in r["reject_reasons"])
    r = cal.calibrate(_runs(5))
    assert not r["accepted"] and any("부팅 수" in x for x in r["reject_reasons"])
    assert cal.calibrate(_runs(10), min_boots=10)["accepted"]


def test_calibrate_flags_inexact_t_f_and_r_home_const():
    runs = _runs(30)
    runs[0][2].append({"kind": "track", "s_track": -0.3, "d3": 0.6, "threshold_m": 1.4, "t_f_exact": False})
    r = cal.calibrate(runs)
    assert r["track_t_f_inexact"] == 1 and not r["accepted"]
    r = cal.calibrate(_runs(30), r_home_const=0.01)
    assert any("판정 상수 R_home" in x for x in r["reject_reasons"])


def test_speed_relation_bins():
    r = cal.speed_relation([(0.5, 0.6, 0.1), (1.5, 0.7, 0.2), (2.5, 0.8, 0.3), (None, 0.9, 0.4)])
    assert r["n"] == 3 and r["corr_s_speed"] == pytest.approx(1.0)
    assert [b["n"] for b in r["bins"]] == [1, 1, 1, 0, 0]
