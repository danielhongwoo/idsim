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

"""b와 R_home 보정 집계(1b decisions.md 쟁점 5). 계산은 tests/support/calibration.py에 있다.

사용법: tests/sitl/calibrate.py <회차 디렉터리 또는 실행 디렉터리>... [--out 파일]
  회차 디렉터리: run_sitl.sh --repeat이 만드는 artifacts/sitl_repeat/<시각>-k<k>/(repeat_summary.tsv의 run_id로
  artifacts/runs/<run_id>/를 찾는다). 실행 디렉터리: artifacts/runs/<run_id>/(sitl/trace.jsonl, sitl/verdict.json).
출력: 표준 출력에 요약, --out(없으면 첫 회차 디렉터리의 calibration.json, 실행 디렉터리만 주면 표준 출력만)에 JSON.
종료 코드: 0 모형 검증 통과(상수를 정할 수 있다), 1 기각이나 부족(올린다), 2 입력 오류.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.support import calibration as cal  # noqa: E402


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
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    dirs, groups = run_dirs(a.paths)
    try:
        runs = [load(d) for d in dirs]
    except (OSError, ValueError) as e:
        print("calibrate: 입력을 읽지 못했다: %s" % e, file=sys.stderr)
        return 2
    r = cal.calibrate(runs)
    g, t = r["goto"], r["s_track"]
    lines = [
        "부팅 수 %d (제외한 실행 %d), m %d, m_home %d, k %s" % (r["boots"], len(r["skipped_runs"]), r["m"], r["m_home"],
                                                         _f(r["k"])),
        "GOTO s: 사건 %d, mean %s, std %s, max %s, 허용한계 %s, Shapiro-Wilk p %s" % (
            g["n"], _f(g["mean"]), _f(g["std"]), _f(g["max"]), _f(r.get("goto_limit")), _f(r["shapiro_goto"]["p"])),
        "s_track: 사건 %d(t_f exact가 아닌 사건 %d), mean %s, std %s, max %s, 허용한계 %s, Shapiro-Wilk p %s" % (
            t["n"], r["track_t_f_inexact"], _f(t["mean"]), _f(t["std"]), _f(t["max"]), _f(r.get("s_track_limit")),
            _f(r["shapiro_s_track"]["p"])),
        "b 후보 %s m (0.35 m 초과 %s, 0.5 m 초과 %s), 시험 미션 acceptance_radius_m = 1.0 - b = %s" % (
            _f(r.get("b_candidate"), "%.2f"), r["b_over_warn"], r["b_over_max"], _f(r["acceptance_radius_m"], "%.2f")),
        "R_home: RTL 사건 %s, R4 max %s, sigma_hat %s, q x f %s, 허용한계 %s, 후보 %s m" % (
            r.get("rtl_events", 0), _f(r.get("r4_max")), _f(r.get("sigma_hat")),
            _f(None if "q" not in r else r["q"] * r["f"]), _f(r.get("r_home_limit")),
            _f(r.get("r_home_candidate"), "%.2f")),
        "실행 id: %s" % ", ".join(r["run_ids"]),
    ]
    sp = r["goto_speed"]
    lines.append("기록(recorded_only) t_f 수평 속도: 사건 %d, 평균 %s m/s, 상관(d_h, 속도) %s, 상관(s, 속도) %s" % (
        sp["n"], _f(sp["speed"]["mean"]), _f(sp["corr_d_h_speed"]), _f(sp["corr_s_speed"])))
    lines += ["  속도 [%s, %s) m/s: 사건 %d, 평균 s %s, 평균 d_h %s" % (
        _f(b["from_mps"], "%.0f"), _f(b["to_mps"], "%.0f"), b["n"], _f(b["mean_s"]), _f(b["mean_d_h"]))
        for b in sp["bins"] if b["n"]]
    lines += ["표시: " + x for x in r["flags"]]
    lines += ["기각 또는 부족: " + x for x in r["reject_reasons"]] or ["모형 검증 통과"]
    print("\n".join(lines))
    out = Path(a.out) if a.out else (groups[0] / "calibration.json" if groups else None)
    if out is not None:
        out.write_text(json.dumps(r, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("calibrate: %s" % out, file=sys.stderr)
    return 0 if r["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
