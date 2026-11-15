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


def _events(s_vals, st_vals, r4_vals, speed=2.0):
    ev = [{"kind": "reach", "s": v, "d_h": v + 0.5, "speed_h_mps": speed + v} for v in s_vals]
    ev += [{"kind": "track", "s_track": v, "t_f_exact": True} for v in st_vals]
    ev += [{"kind": "landing", "rtl": True, "r4_m": r, "landing": [r, 0.0, 0.2], "ref": [0.0, 0.0, 0.2]}
           for r in r4_vals]
    return ev


def _runs(n, failed=0):
    nd = NormalDist()
    runs = []
    for b in range(n):
        s = [0.1 + 0.03 * nd.inv_cdf((b * 7 + i + 0.5) / (7 * n)) for i in range(7)]
        st = [-0.5 + 0.05 * nd.inv_cdf((b * 2 + i + 0.5) / (2 * n)) for i in range(2)]
        r4 = [0.03 + 0.001 * ((b + i) % 5) for i in range(2)]
        runs.append(("r%d" % b, {"passed": True}, _events(s, st, r4)))
    runs += [("bad%d" % i, {"passed": False}, _events([5.0], [], [])) for i in range(failed)]
    return runs


def test_calibrate_accepts_well_behaved_samples():
    r = cal.calibrate(_runs(30, failed=1))
    assert r["boots"] == 30 and r["skipped_runs"] == ["bad0"] and r["goto"]["n"] == 210
    assert r["k"] == pytest.approx(4.237, abs=1e-3)
    assert r["b_candidate"] == cal.ceil_step(r["goto"]["mean"] + r["k"] * r["goto"]["std"])
    assert r["accepted"], r["reject_reasons"]
    assert r["acceptance_radius_m"] == pytest.approx(1.0 - r["b_candidate"])
    assert r["r_home_candidate"] == cal.ceil_step(r["q"] * r["f"] * r["sigma_hat"])
    assert not r["b_over_warn"] and not r["b_over_max"] and r["events_per_boot"] == []
    sp = r["goto_speed"]
    assert sp["corr_d_h_speed"] == pytest.approx(1.0) and sp["status"] == "recorded_only"
    assert sum(b["n"] for b in sp["bins"]) == 210


def test_calibrate_rejects_few_boots_and_flags_lines():
    r = cal.calibrate(_runs(5))
    assert not r["accepted"] and any("부팅 수" in x for x in r["reject_reasons"])
    big = [(rid, v, [dict(e, s=e["s"] + 0.4) if e["kind"] == "reach" else e for e in ev]) for rid, v, ev in _runs(30)]
    r = cal.calibrate(big)
    assert r["b_over_warn"] and r["b_candidate"] > sj.B_WARN_M


def test_speed_relation_bins():
    r = cal.speed_relation([(0.5, 0.6, 0.1), (1.5, 0.7, 0.2), (2.5, 0.8, 0.3), (None, 0.9, 0.4)])
    assert r["n"] == 3 and r["corr_s_speed"] == pytest.approx(1.0)
    assert [b["n"] for b in r["bins"]] == [1, 1, 1, 0, 0]
