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

#!/usr/bin/env python3
"""run_sitl.sh가 부르는 호스트 쪽 요약 도구(표준 라이브러리만). 판정 로직은 tests/support/sitl_summary.py에 있다.

  summarize.py run <실행 디렉터리> [--sitl-dir sitl] [--steps "단계=초,..."] [--fallback CATEGORY:메시지]
      verdict.json으로 summary.md를 쓴다. verdict.json이 없으면(pytest가 돌지 못함) --fallback의 분류로 실패 verdict를 만든다.
      종료 코드 0은 통과, 1은 실패.
  summarize.py repeat --out <디렉터리> <verdict.json>...
      repeat_summary.tsv와 armed_criterion.json(Executor 경유 부류)을 쓴다. 종료 코드는 항상 0이다(통과 여부는 회차의 종료 코드).
  summarize.py ulog <실행 디렉터리>
      px4-N/log/*.ulg가 메시지 경계에서 끝나는지 sitl/ulog_check.txt에 적는다.
  summarize.py ops-running <compose ps -a --format json 파일> <ops 서비스>...
      stop 전에 running이 아닌 ops-N이 있으면 종료 코드 1.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support import sitl_summary as ss  # noqa: E402


def load_verdict(run_dir, sitl_dir, fallback):
    p = Path(run_dir) / sitl_dir / "verdict.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    cat, _, msg = (fallback or "NO_VERDICT:verdict.json이 없다").partition(":")
    return {"schema": ss.SCHEMA, "run_id": Path(run_dir).name, "git_commit": None, "git_dirty": None, "images": {},
            "gate": {"ok": False, "category": cat, "message": msg}, "scenarios": [], "rtf": None, "armed_a": None}


def cmd_run(a):
    v = load_verdict(a.run_dir, a.sitl_dir, a.fallback)
    steps = [tuple(x.split("=", 1)) for x in a.steps.split(",") if "=" in x] if a.steps else None
    out = Path(a.run_dir) / a.sitl_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(ss.summary_md(v, steps), encoding="utf-8")
    return 0 if v.get("passed", ss.run_passed(v)) else 1


def cmd_repeat(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    verdicts = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.verdicts]
    with open(out / "repeat_summary.tsv", "w", encoding="utf-8") as fh:
        fh.write("\t".join(ss.tsv_header()) + "\n")
        for v, p in zip(verdicts, a.verdicts):
            f = Path(p).with_name("steps.tsv")
            rcs = ss.parse_rcs(f.read_text(encoding="utf-8")) if f.is_file() else None
            fh.write("\t".join(ss.tsv_row(v, rcs=rcs)) + "\n")
    crit = ss.armed_criterion(verdicts)
    cc = []
    for p in a.verdicts:
        f = Path(p).with_name("crosscheck_a.json")
        cc.append(json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None)
    crit["hold_deviation_notes"] = [(v.get("run_id"), n) for v in verdicts for n in ss.hold_notes(v)]
    crit["ulog_crosscheck"] = ss.ulog_crosscheck_totals(cc)
    crit["passed_with_ulog"] = bool(crit["passed"] and crit["ulog_crosscheck"]["n_checked"] == len(verdicts)
                                    and crit["ulog_crosscheck"]["ulog_violation_total"] == 0)
    crit["note"] = ("ROS 기록만의 판정이다. Executor 경유(scenario_a) 부류의 ARMED 3회 확인까지 간 실행이 10회 이상이고 "
                    "OFFBOARD가 아닌 ARMED 표본이 0개여야 통과다. passed는 ROS 기록만의 판정이고 passed_with_ulog는 모든 회의 ULog 교차 확인(crosscheck_a.py)에서 "
                    "ULog 기준 위반이 0건인 것까지 본다. "
                    "10회 중 0건은 실패율 95% 상한이 약 26%라는 뜻이며 플래키 없음의 증거가 아니다.")
    (out / "armed_criterion.json").write_text(json.dumps(crit, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    passed = sum(1 for v in verdicts if v.get("passed", ss.run_passed(v)))
    print("회차 %d, 통과 %d. ARMED 기준(scenario_a): 도달 %d회, 위반 %d건, 통과 %s, ULog 교차 확인 %d회 위반 %d건, ULog 포함 통과 %s" % (
        len(verdicts), passed, crit["n_reached"], crit["violation_total"], crit["passed"],
        crit["ulog_crosscheck"]["n_checked"], crit["ulog_crosscheck"]["ulog_violation_total"], crit["passed_with_ulog"]))
    for rid, n in crit["hold_deviation_notes"]:
        print("note: %s: %s" % (rid, n))
    return 0


def cmd_ulog(a):
    run = Path(a.run_dir)
    lines = []
    for p in sorted(run.glob("px4-*/log/**/*.ulg")):
        r = ss.ulog_tail_check(p.read_bytes())
        lines.append("%s bytes=%s messages=%s truncated=%s ok=%s" % (
            p.relative_to(run), r.get("bytes"), r.get("messages"), r.get("truncated"), r["ok"]))
    if not lines:
        lines.append("ulg 파일이 없다")
    out = run / a.sitl_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "ulog_check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), file=sys.stderr)
    return 0


def cmd_ops_running(a):
    states = {}
    for line in Path(a.ps_json).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        for d in item if isinstance(item, list) else [item]:
            states[d.get("Service")] = d.get("State")
    bad = [s for s in a.services if states.get(s) != "running"]
    if bad:
        print("stop 전에 running이 아닌 서비스: %s" % ", ".join("%s(%s)" % (s, states.get(s, "없음")) for s in bad),
              file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("run_dir")
    p.add_argument("--sitl-dir", default="sitl")
    p.add_argument("--steps", default="")
    p.add_argument("--fallback", default="")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("repeat")
    p.add_argument("--out", required=True)
    p.add_argument("verdicts", nargs="+")
    p.set_defaults(fn=cmd_repeat)
    p = sub.add_parser("ulog")
    p.add_argument("run_dir")
    p.add_argument("--sitl-dir", default="sitl")
    p.set_defaults(fn=cmd_ulog)
    p = sub.add_parser("ops-running")
    p.add_argument("ps_json")
    p.add_argument("services", nargs="*")
    p.set_defaults(fn=cmd_ops_running)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
