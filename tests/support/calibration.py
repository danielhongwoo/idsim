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

"""b와 R_home의 보정 확인과 계산(1b decisions.md 쟁점 5, 사용자 결정 U18). 순수 코드다(표준 라이브러리만. lint job에서
단위 테스트가 돈다).

입력은 run_sitl.sh --repeat의 회차마다 남는 trace.jsonl(reach, track, landing 사건)과 verdict.json이다. 통과한 실행만
부팅으로 센다.
- b(U18): 상수로 받는다(기본 sitl_judge.B_M). 확인 조건은 "GOTO 도달 사건의 s = d_oracle(t_f) - acceptance_radius_m와
  TRACK_ENTITY 완료의 s_track = d_oracle(t_f) - acceptance_radius_m - v x L의 표본 전부가 b 이하"다. 쟁점 5의 정규
  허용한계(비중심 t의 k, mean + k x std)와 Shapiro-Wilk는 쓰지 않고 기록용으로만 낸다(분포를 다시 볼 때의 자료).
- 도달 확인: GOTO d3 전부가 R_JUDGE 안이고 TRACK_ENTITY d3 전부가 그 사건의 임계값(R_JUDGE + v x L) 안인가(판정과
  같은 기준).
- R_home(R4): RTL 착륙 수평 위치와 기준점의 거리. sigma_hat^2 = mean(R4^2) / 2, q = sqrt(-2 ln(0.005 / m_home)),
  f = sqrt(2n / chi2_0.05(2n)), R_home = ceil_0.05(q x f x sigma_hat). 표본 최댓값이 q x f x sigma_hat를 넘으면 기각.
  착륙 위치 벡터의 평균이 축마다 2 표준오차보다 크면 기록한다(기각 사유가 아니다). 판정 상수 R_HOME_M과 대조한다.
- 상한: b > 0.5 m 또는 R_home > 1 m는 올린다.
- 기록 전용: t_f 시점 기체 수평 속도(reach 사건의 speed_h_mps)와 d_h, s의 상관계수, 속도 구간별 사건 수와 평균.
"""
import math
from statistics import NormalDist

from tests.support import sitl_judge as sj

CONFIDENCE = 0.95
RUN_BUDGET = 0.005          # 실행당 실패 예산 1% 가운데 b(와 R_home)에 주는 몫
MIN_BOOTS = 30
SHAPIRO_MIN_P = 0.01
STEP_M = 0.05
_N = NormalDist()


def ceil_step(x, step=STEP_M):
    """step 단위로 올린다(부동소수 오차로 한 칸 더 올라가지 않게 1e-9를 뺀다)."""
    return round(math.ceil(x / step - 1e-9) * step, 10)


# --- 분포 함수(표준 라이브러리만) ---

def _chi2_logpdf(u, nu):
    return (nu / 2 - 1) * math.log(u) - u / 2 - (nu / 2) * math.log(2) - math.lgamma(nu / 2)


def nct_cdf(t, nu, delta, steps=4000):
    """비중심 t 분포 CDF. P(T <= t) = E_V[Phi(t sqrt(V / nu) - delta)], V ~ chi2(nu). Simpson 적분."""
    sd = math.sqrt(2 * nu)
    lo, hi = max(1e-12, nu - 20 * sd), nu + 20 * sd
    h = (hi - lo) / steps
    acc = 0.0
    for i in range(steps + 1):
        u = lo + i * h
        w = 1 if i in (0, steps) else (4 if i % 2 else 2)
        acc += w * _N.cdf(t * math.sqrt(u / nu) - delta) * math.exp(_chi2_logpdf(u, nu))
    return acc * h / 3


def nct_ppf(q, nu, delta):
    """비중심 t 분포의 q 분위수(이분법)."""
    lo, hi = delta - 10.0, delta * 3 + 50.0
    while nct_cdf(hi, nu, delta) < q:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if nct_cdf(mid, nu, delta) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def tolerance_k(n, m=sj.M_EVENTS, confidence=CONFIDENCE, budget=RUN_BUDGET):
    """정규 단측 허용계수 k(부팅 수 n, 사건 수 m). n이 2 미만이면 None."""
    if n < 2:
        return None
    zp = _N.inv_cdf(1 - budget / m)
    return nct_ppf(confidence, n - 1, zp * math.sqrt(n)) / math.sqrt(n)


def _gammainc_lower(a, x):
    """정규화 하부 불완전 감마 P(a, x)(급수와 연분수)."""
    if x <= 0:
        return 0.0
    if x < a + 1:
        term = s = 1.0 / a
        ap = a
        for _ in range(10000):
            ap += 1
            term *= x / ap
            s += term
            if abs(term) < abs(s) * 1e-15:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b, c, d = x + 1 - a, 1e300, 1 / (x + 1 - a)
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return 1 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_ppf(q, nu):
    """카이제곱 분포의 q 분위수(이분법)."""
    lo, hi = 0.0, nu + 50 * math.sqrt(2 * nu) + 50
    for _ in range(200):
        mid = (lo + hi) / 2
        if _gammainc_lower(nu / 2, mid / 2) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def rayleigh_qf(n, m_home=sj.M_HOME, budget=RUN_BUDGET, confidence=CONFIDENCE):
    """R_home의 q x f(부팅 수 n). q = sqrt(-2 ln(budget / m_home)), f = sqrt(2n / chi2_{1-confidence}(2n))."""
    q = math.sqrt(-2 * math.log(budget / m_home))
    f = math.sqrt(2 * n / chi2_ppf(1 - confidence, 2 * n))
    return q, f


def shapiro_wilk(x):
    """Shapiro-Wilk W와 p(Royston 1992 근사. n 12-5000). n이 12 미만이면 (None, None)."""
    n = len(x)
    if n < 12:
        return None, None
    xs = sorted(x)
    m = [_N.inv_cdf((i - 0.375) / (n + 0.25)) for i in range(1, n + 1)]
    mm = sum(v * v for v in m)
    u = 1 / math.sqrt(n)
    an = m[-1] / math.sqrt(mm) + 0.221157 * u - 0.147981 * u ** 2 - 2.07119 * u ** 3 + 4.434685 * u ** 4 \
        - 2.706056 * u ** 5
    an1 = m[-2] / math.sqrt(mm) + 0.042981 * u - 0.293762 * u ** 2 - 1.752461 * u ** 3 + 5.682633 * u ** 4 \
        - 3.582633 * u ** 5
    phi = (mm - 2 * m[-1] ** 2 - 2 * m[-2] ** 2) / (1 - 2 * an ** 2 - 2 * an1 ** 2)
    a = [v / math.sqrt(phi) for v in m]
    a[-1], a[-2], a[0], a[1] = an, an1, -an, -an1
    mean = sum(xs) / n
    ss = sum((v - mean) ** 2 for v in xs)
    if ss <= 0:
        return None, None
    w = min(1.0, sum(ai * xi for ai, xi in zip(a, xs)) ** 2 / ss)
    ln = math.log(n)
    mu = 0.0038915 * ln ** 3 - 0.083751 * ln ** 2 - 0.31082 * ln - 1.5861
    sigma = math.exp(0.0030302 * ln ** 2 - 0.082676 * ln - 0.4803)
    if w >= 1.0:
        return w, 1.0
    return w, 1 - _N.cdf((math.log(1 - w) - mu) / sigma)


# --- 집계 ---

SPEED_BINS_MPS = (0.0, 1.0, 2.0, 3.0, 4.0)     # 구간 [a, b), 마지막은 4 m/s 이상


def pearson(x, y):
    """표본 상관계수. 짝이 3개 미만이거나 분산이 0이면 None."""
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return None if sxx <= 0 or syy <= 0 else sxy / math.sqrt(sxx * syy)


def speed_relation(rows):
    """rows: [(속도 m/s, d_h, s)]. d_h와 속도의 상관, s와 속도의 상관, 속도 구간별 사건 수와 평균 s, 평균 d_h."""
    rows = [r for r in rows if r[0] is not None]
    bins = []
    edges = list(SPEED_BINS_MPS) + [math.inf]
    for a, b in zip(edges, edges[1:]):
        sel = [r for r in rows if a <= r[0] < b]
        bins.append({"from_mps": a, "to_mps": None if b == math.inf else b, "n": len(sel),
                     "mean_s": None if not sel else sum(r[2] for r in sel) / len(sel),
                     "mean_d_h": None if not sel else sum(r[1] for r in sel) / len(sel)})
    return {"n": len(rows), "corr_d_h_speed": pearson([r[0] for r in rows], [r[1] for r in rows]),
            "corr_s_speed": pearson([r[0] for r in rows], [r[2] for r in rows]),
            "speed": _stats([r[0] for r in rows]), "bins": bins, "status": "recorded_only"}

def _stats(v):
    n = len(v)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "max": None}
    mean = sum(v) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in v) / (n - 1)) if n > 1 else None
    return {"n": n, "mean": mean, "std": std, "max": max(v)}


def run_samples(trace_events):
    """한 실행의 trace 사건에서 표본을 모은다. 반환 dict:
    s, s_track(목록), r4([(r4, dx, dy)]), inexact(t_f exact가 아닌 TRACK_ENTITY 사건 수. 1a56d03 전의 trace가 섞였는지
    보는 표시), speed([(t_f 수평 속도, d_h, s)]), reach([(종류, d3, 임계값)])."""
    out = {"s": [], "s_track": [], "r4": [], "inexact": 0, "speed": [], "reach": []}
    for e in trace_events:
        k = e.get("kind")
        if k == "reach" and e.get("s") is not None:
            out["s"].append(e["s"])
            out["speed"].append((e.get("speed_h_mps"), e.get("d_h"), e["s"]))
            out["reach"].append(("GOTO", e["d3"], sj.R_JUDGE_M))
        elif k == "track" and e.get("s_track") is not None:
            out["s_track"].append(e["s_track"])
            out["inexact"] += 0 if e.get("t_f_exact", True) else 1
            out["reach"].append(("TRACK_ENTITY", e["d3"], e["threshold_m"]))
        elif k == "landing" and e.get("rtl") and e.get("r4_m") is not None:
            out["r4"].append((e["r4_m"], e["landing"][0] - e["ref"][0], e["landing"][1] - e["ref"][1]))
    return out


def calibrate(runs, b=sj.B_M, min_boots=MIN_BOOTS, r_home_const=sj.R_HOME_M):
    """runs: [(실행 id, verdict dict, trace 사건 목록)]. 통과한 실행만 부팅으로 센다. 결과 dict.
    accepted: 부팅 수 >= min_boots, s와 s_track 표본 전부 <= b, 도달 사건 전부 판정 반경 안, R4 허용한계 안,
    R_home 후보 <= 1 m, t_f가 정확하지 않은 사건 없음."""
    used, skipped = [], []
    acc = {"s": [], "s_track": [], "r4": [], "inexact": 0, "speed": [], "reach": []}
    shape = []
    for rid, verdict, events in runs:
        if not verdict.get("passed"):
            skipped.append(rid)
            continue
        x = run_samples(events)
        used.append(rid)
        shape.append((rid, len(x["s"]), len(x["s_track"]), len(x["r4"])))
        for key in ("s", "s_track", "r4", "speed", "reach"):
            acc[key] += x[key]
        acc["inexact"] += x["inexact"]
    n = len(used)
    gs, ts = _stats(acc["s"]), _stats(acc["s_track"])
    reasons = []
    if n < min_boots:
        reasons.append("부팅 수 %d < %d" % (n, min_boots))
    if acc["inexact"]:
        reasons.append("t_f가 정확하지 않은 TRACK_ENTITY 사건 %d개(옛 trace가 섞였다)" % acc["inexact"])
    over_s = [v for v in acc["s"] if v > b + 1e-12]
    over_t = [v for v in acc["s_track"] if v > b + 1e-12]
    if not acc["s"]:
        reasons.append("GOTO 표본이 없다")
    if over_s:
        reasons.append("GOTO s %d건이 b %.2f m를 넘는다(최대 %.4f)" % (len(over_s), b, max(over_s)))
    if over_t:
        reasons.append("s_track %d건이 b %.2f m를 넘는다(최대 %.4f)" % (len(over_t), b, max(over_t)))
    out_reach = [(kind, d3, thr) for kind, d3, thr in acc["reach"] if d3 > thr + 1e-12]
    if out_reach:
        reasons.append("판정 반경 밖 도달 사건 %d건(첫 사건 %s d3 %.4f > %.2f)" % (
            len(out_reach), out_reach[0][0], out_reach[0][1], out_reach[0][2]))
    goto_d3 = [d3 for kind, d3, _ in acc["reach"] if kind == "GOTO"]
    track_margin = [d3 - thr for kind, d3, thr in acc["reach"] if kind == "TRACK_ENTITY"]
    out = {"boots": n, "run_ids": used, "skipped_runs": skipped, "b": b, "m": sj.M_EVENTS, "m_home": sj.M_HOME,
           "goto": gs, "s_track": ts, "goto_over_b": len(over_s), "s_track_over_b": len(over_t),
           "track_t_f_inexact": acc["inexact"], "goto_d3_max": max(goto_d3) if goto_d3 else None,
           "track_d3_minus_threshold_max": max(track_margin) if track_margin else None,
           "reach_outside": len(out_reach), "goto_speed": speed_relation(acc["speed"]),
           "events_per_boot": [{"run_id": r, "goto": a, "track": c, "rtl": d} for r, a, c, d in shape
                               if (a, c, d) != (7, 2, 2)]}
    # 기록 전용: 쟁점 5의 정규 허용한계와 Shapiro-Wilk(U18로 판정에 쓰지 않는다)
    k = tolerance_k(n)
    w, p = shapiro_wilk(acc["s"])
    wt, pt = shapiro_wilk(acc["s_track"])
    normal = {"k": k, "shapiro_goto": {"w": w, "p": p}, "shapiro_s_track": {"w": wt, "p": pt}, "status": "recorded_only"}
    if k is not None and gs["std"] is not None:
        normal.update(goto_limit=gs["mean"] + k * gs["std"], b_normal=ceil_step(gs["mean"] + k * gs["std"]))
    if k is not None and ts["std"] is not None:
        normal.update(s_track_limit=ts["mean"] + k * ts["std"])
    out["normal_model"] = normal
    # R_home
    r4 = [r for r, _, _ in acc["r4"]]
    rh = None
    if n >= 1 and r4:
        q, f = rayleigh_qf(n)
        sigma = math.sqrt(sum(r * r for r in r4) / len(r4) / 2)
        rlim = q * f * sigma
        rh = ceil_step(rlim)
        bias = {}
        for axis, v in (("x", [a for _, a, _ in acc["r4"]]), ("y", [c for _, _, c in acc["r4"]])):
            st_ = _stats(v)
            se = None if st_["std"] is None else st_["std"] / math.sqrt(len(v))
            bias[axis] = {"mean": st_["mean"], "se": se,
                          "over_2se": se is not None and abs(st_["mean"]) > 2 * se}
        out.update(rtl_events=len(r4), r4_max=max(r4), sigma_hat=sigma, q=q, f=f, r_home_limit=rlim,
                   r_home_candidate=rh, landing_bias=bias,
                   r_home_matches_constant=r_home_const is not None and abs(rh - r_home_const) < 1e-9)
        if max(r4) > rlim:
            reasons.append("R4 최댓값 %.4f > 허용한계 %.4f" % (max(r4), rlim))
        if r_home_const is not None and max(r4) > r_home_const:
            reasons.append("R4 최댓값 %.4f > 판정 상수 R_home %.2f" % (max(r4), r_home_const))
    else:
        reasons.append("RTL 착륙 사건이 없다")
    if b > sj.B_MAX_M:
        reasons.append("b %.2f > 상한 %.2f m" % (b, sj.B_MAX_M))
    if rh is not None and rh > sj.R_HOME_MAX_M:
        reasons.append("R_home %.2f > 상한 %.2f m" % (rh, sj.R_HOME_MAX_M))
    out.update(b_over_max=b > sj.B_MAX_M, reject_reasons=reasons,
               accepted=not reasons, acceptance_radius_m=round(sj.R_JUDGE_M - b, 10))
    return out
