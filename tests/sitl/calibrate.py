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

"""b와 R_home 보정 확인(tests/sitl/README.md "b와 R_home 보정 확인", U18). 계산은 tests/support/calibration.py에 있다.

사용법: tests/sitl/calibrate.py <회차 디렉터리 또는 실행 디렉터리>... [--b 0.5] [--min-boots 30] [--out 파일]
  회차 디렉터리: run_sitl.sh --repeat이 만드는 artifacts/sitl_repeat/<시각>-k<k>/(repeat_summary.tsv의 run_id로
  artifacts/runs/<run_id>/를 찾는다). 실행 디렉터리: artifacts/runs/<run_id>/(sitl/trace.jsonl, sitl/verdict.json).
  --b의 기본은 판정 상수 sitl_judge.B_M이다. --min-boots는 부팅 수 하한이다(기본 30).
출력: 표준 출력에 요약, --out(없으면 첫 회차 디렉터리의 calibration.json, 실행 디렉터리만 주면 표준 출력만)에 JSON.
종료 코드: 0 확인 조건 충족, 1 미충족(올린다), 2 입력 오류.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.support import calibration as cal  # noqa: E402
from tests.support import sitl_judge as sj  # noqa: E402


def run_dirs(paths):
    out, groups = [], []
    for p in map(Path, paths):
        tsv = p / "repeat_summary.tsv"
        if tsv.is_file():
            groups.append(p)
            with open(tsv, encoding="utf-8") as fh:
                out += [REPO / "artifacts" / "runs" / row["run_id"] for row in csv.DictReader(fh, delimiter="\t")]
        else:
            out.append(p)
    return out, groups


def load(d):
    sd = d / "sitl"
    verdict = json.loads((sd / "verdict.json").read_text(encoding="utf-8"))
    events = [json.loads(ln) for ln in (sd / "trace.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    return verdict.get("run_id", d.name), verdict, events


def _f(v, fmt="%.4f"):
    return "-" if v is None else fmt % v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--b", type=float, default=sj.B_M)
    ap.add_argument("--min-boots", type=int, default=cal.MIN_BOOTS)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    dirs, groups = run_dirs(a.paths)
    try:
        runs = [load(d) for d in dirs]
    except (OSError, ValueError) as e:
        print("calibrate: 입력을 읽지 못했다: %s" % e, file=sys.stderr)
        return 2
    r = cal.calibrate(runs, b=a.b, min_boots=a.min_boots)
    g, t, nm = r["goto"], r["s_track"], r["normal_model"]
    lines = [
        "부팅 수 %d (제외한 실행 %d), b %.2f m, 시험 미션 반경 1.0 - b = %.2f m" % (
            r["boots"], len(r["skipped_runs"]), r["b"], r["acceptance_radius_m"]),
        "GOTO s: 사건 %d, mean %s, std %s, max %s, b 초과 %d건" % (
            g["n"], _f(g["mean"]), _f(g["std"]), _f(g["max"]), r["goto_over_b"]),
        "s_track: 사건 %d(t_f exact가 아닌 사건 %d), mean %s, std %s, max %s, b 초과 %d건" % (
            t["n"], r["track_t_f_inexact"], _f(t["mean"]), _f(t["std"]), _f(t["max"]), r["s_track_over_b"]),
        "도달: GOTO d3 max %s(판정 반경 1.0), TRACK_ENTITY d3 - 임계 max %s, 반경 밖 %d건" % (
            _f(r["goto_d3_max"]), _f(r["track_d3_minus_threshold_max"]), r["reach_outside"]),
        "R_home: RTL 사건 %s, R4 max %s, sigma_hat %s, q x f %s, 허용한계 %s, 후보 %s m(판정 상수와 같음 %s)" % (
            r.get("rtl_events", 0), _f(r.get("r4_max")), _f(r.get("sigma_hat")),
            _f(None if "q" not in r else r["q"] * r["f"]), _f(r.get("r_home_limit")),
            _f(r.get("r_home_candidate"), "%.2f"), r.get("r_home_matches_constant")),
        "기록(정규 모형, 판정에 쓰지 않음): k %s, 허용한계 GOTO %s, s_track %s, Shapiro-Wilk p GOTO %s, s_track %s" % (
            _f(nm["k"]), _f(nm.get("goto_limit")), _f(nm.get("s_track_limit")), _f(nm["shapiro_goto"]["p"]),
            _f(nm["shapiro_s_track"]["p"])),
        "실행 id: %s" % ", ".join(r["run_ids"]),
    ]
    sp = r["goto_speed"]
    lines.append("기록(recorded_only) t_f 수평 속도: 사건 %d, 평균 %s m/s, 상관(d_h, 속도) %s, 상관(s, 속도) %s" % (
        sp["n"], _f(sp["speed"]["mean"]), _f(sp["corr_d_h_speed"]), _f(sp["corr_s_speed"])))
    lines += ["  속도 [%s, %s) m/s: 사건 %d, 평균 s %s, 평균 d_h %s" % (
        _f(x["from_mps"], "%.0f"), _f(x["to_mps"], "%.0f"), x["n"], _f(x["mean_s"]), _f(x["mean_d_h"]))
        for x in sp["bins"] if x["n"]]
    lines += ["미충족: " + x for x in r["reject_reasons"]] or ["확인 조건 충족"]
    print("\n".join(lines))
    out = Path(a.out) if a.out else (groups[0] / "calibration.json" if groups else None)
    if out is not None:
        out.write_text(json.dumps(r, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("calibrate: %s" % out, file=sys.stderr)
    return 0 if r["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
