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

"""측정 기록(measure_*.jsonl, raw_*.jsonl)을 ULog의 vehicle_status와 교차 확인한다.

호스트에서 표준 라이브러리만으로 돈다(rclpy, pyulog 불필요). run_measure.sh가 스택을 멈춘 뒤 부른다
(ULog는 닫힌 뒤에 읽는다. 닫히지 않았으면 마지막 메시지가 잘린 채로 읽는다).

  crosscheck.py --measure-dir <실행 디렉터리>/measure [--repo-root 저장소] [--items item3,item5,...] [--force]

--items는 요청한 item 목록이다(run_measure.sh가 넘긴다). item마다 행(measure_<item>.jsonl)과 완료 기록
(done_<item>.json)이 없으면 종료 코드 2다(measure.py가 기록을 만들기 전에 죽은 item도 드러난다). 생략하면
있는 파일로 목록을 정한다. 이 스크립트가 만드는 파일(crosscheck_<item>.json, armed_criterion.json,
final_summary.json, 최종 판정 절이 붙은 summary_<item>.txt)이 이미 있으면 --force 없이는 덮어쓰지 않고 거부한다(종료 코드 2).

시도마다(armed_window_ros_us가 있는 행). 대조 로직은 tests/support/measure_check.py(단위 테스트)다.
  - ROS 표본이 ULog에 같은 timestamp로 있고 arming_state, nav_state, failsafe,
    nav_state_user_intention이 같은가 (ros_missing_in_ulog, ros_field_mismatch)
  - ULog 구간의 표본 중 ROS가 못 받은 것(ulog_only)과 ULog 기준의 OFFBOARD가 아닌 ARMED 표본 수.
    위반 구간의 끝은 측정기의 ARMED 구간 끝(min(ARMED 3회 확인, 정리 종료, 첫 Hold 전송))과 같고,
    대조 구간의 끝은 정리 종료 시각까지 넓혀 ROS 누락을 ULog가 잡게 한다.
  - ULog 표본 간격의 최소값(ulog_min_interval_ms)
  - (5): arm 수락 증거를 ULog에서 확정한다(증거 A: arm 전송 뒤 timestamp의 ARMED 표본, 증거 B: logged
    message '[commander] Armed by external command'). ROS ack는 증거가 아니다. 증거가 확인되면
    INCONCLUSIVE였던 (5) 행의 최종 판정이 PASS가 되고(final_verdict), 끝내 없으면 INCONCLUSIVE로 남는다.
  - 최종 판정(final_verdict) 기준의 항목별 유효 시도 수(전체와 (5)의 지연값별)와 PASS 횟수가 최소 시도
    수 이상인가(final_summary.json). INCONCLUSIVE는 유효 시도가 아니다.
  - (3): 시도마다 ULog로 t_A, t_ramp, t_ml, t_lf, t_p, r_p를 구하고 대역(spoolup, 내부, 경계)과 최종 verdict를 정한다
    (tests/support/measure_bands.py. 정의와 규칙은 README의 "(3)의 대역과 판정"). bands_item3.json에 시도마다 분석을
    남기고, summary_item3.txt 맨 위에 대역별 충족 여부를 둔다. 2b와 (3)의 Hold 뒤 60 s 관찰은 ULog 전체 표본으로
    본다(landed true는 M3_CONTRADICTED, maybe_landed만 true는 INCONCLUSIVE).
  - 각 ULog의 T_lf 표본(첫 ARMED 뒤 landed false까지) 수, 최솟값, 최댓값과 그 최솟값으로 계산한 (3)의 지연 목록을
    출력한다(image key가 바뀌어 T_lf를 다시 정할 때 쓴다).
  - 각 ULog 안의 '[commander] Armed by external command' 줄 총수를 출력한다.
결과: crosscheck_<항목>.json, armed_criterion.json(부류별), final_summary.json, 끝에 요약 줄.
summary_<item>.txt가 있으면 끝에 '최종 판정' 절을 덧붙인다(crosscheck 뒤 최종 verdict 기준).

종료 코드: 0 PX4 직접 부류의 통과(ULog 표본이 실제로 대조됨), 1 위반 또는 불일치 또는 대조가 비어 있음
(어느 부류든 ARMED 위반, 최종 판정 FAIL, M3_CONTRADICTED, M5_CONTRADICTED, M5_INCONSISTENT 포함), 2 입력 부족 또는 ULog를 못 읽음 또는
(5)의 증거 미확인 또는 PASS 횟수 부족 또는 ARMED 3회 도달 실행 부족 또는 commit/image key 없음 또는
measure.py 완료 기록(done_<항목>.json) 없음 또는 이 판 이전의 기록(필요한 키가 없음). 자극이 성립하지
않은 회((3)의 WINDOW_MISSED, ULog 교차 확인 뒤에도 arm 수락 증거가 없는 (5)의 ARM_NOT_ACCEPTED)는 유효 시도에도
not-pass에도 넣지 않고 항목별((5)는 지연값별)로 따로 센다(final_summary.json). 그 회에서 기준과 다른 관측이
나오면 빼지 않고 1이다. run_measure.sh의 최종 종료 코드는 이 값을 따른다. 이 통과는
PX4 직접 부류의 통과이며 P4 머지 조건은 Executor 경유 부류(시나리오 A)의 통과가 따로 필요하다.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.support import measure_bands as mb  # noqa: E402
from tests.support import measure_check as mc  # noqa: E402
from tests.support import ulog_min  # noqa: E402


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_ulog(path, cache):
    """ULog 한 파일을 한 번만 읽는다(수백 MB). (vehicle_status {ts: 행}, 정렬된 ts 목록, logged message,
    measure_bands.UlogData)를 돌려준다. 모든 multi_id는 0이다."""
    if path not in cache:
        topics = ulog_min.read_topics(path, {n: 0 for n in mb.UlogData.NAMES})
        by_ts = {int(r["timestamp"]): r for r in topics["vehicle_status"]}
        logged = ulog_min.read_logged(path)
        cache[path] = (by_ts, sorted(by_ts), logged, mb.UlogData(topics, logged))
    return cache[path]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--measure-dir", required=True)
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--items", default=None, help="요청한 item 목록(쉼표 구분)")
    ap.add_argument("--force", action="store_true", help="기존 crosscheck 산출 파일을 덮어쓴다")
    args = ap.parse_args(argv)
    mdir = Path(args.measure_dir)
    files = sorted(glob.glob(str(mdir / "measure_*.jsonl")))
    requested = args.items.split(",") if args.items else [
        os.path.basename(f)[len("measure_"):-len(".jsonl")] for f in files]
    outputs = [mdir / ("crosscheck_%s.json" % it) for it in requested]
    outputs += [mdir / "armed_criterion.json", mdir / "final_summary.json"]
    outputs += [mdir / ("bands_%s.json" % it) for it in requested if it == "item3"]
    existing = [str(o) for o in outputs if o.exists()]
    for it in requested:       # 최종 판정 절이 이미 붙은 요약도 덮어쓰기와 같다
        sp = mdir / ("summary_%s.txt" % it)
        if sp.exists() and mc.FINAL_SECTION_MARKER in sp.read_text():
            existing.append(str(sp))
    if existing and not args.force:
        print("이미 있는 산출 파일을 덮어쓰지 않는다(--force로 허용): %s" % existing, file=sys.stderr)
        return 2
    if not files:
        print("measure_*.jsonl이 없다: %s" % mdir, file=sys.stderr)
        for line in mc.item_problems(requested, {}, set()):
            print(line, file=sys.stderr)
        return 2
    cache = {}
    entries = []
    all_results = []
    all_rows = []
    finals = {}
    rows_by_item = {}
    rows_by_name = {}
    done_items = set()
    analyses = {}          # item 3: {시도 번호: measure_bands.analyze_row}
    reasons = {}           # {(item, 시도 번호): 최종 verdict의 사유}
    for mf in files:
        item = os.path.basename(mf)[len("measure_"):-len(".jsonl")]
        rows = load_jsonl(mf)
        schema = mc.rows_schema_problems(rows)
        if schema:
            for line in schema[:5]:
                print(line, file=sys.stderr)
            print("%s: 이 판 이전의 기록은 crosscheck가 읽을 수 없다(종료 코드 2)" % mf, file=sys.stderr)
            return 2
        all_rows.extend(rows)
        rows_by_item[item] = len(rows)
        rows_by_name[item] = rows
        if (mdir / ("done_%s.json" % item)).exists():
            done_items.add(item)
        raw = load_jsonl(str(mdir / ("raw_%s.jsonl" % item)))
        by_attempt = {}
        for r in raw:
            if r["t"] == "status":
                by_attempt.setdefault(r["attempt"], []).append(r)
        results = []
        for row in rows:
            f = row["facts"]
            measurable = f is not None and "armed_window_ros_us" in f
            ulog = row["ulog"]
            res = None
            err = None
            if not ulog:
                err = "ulog 경로 없음"
            else:
                path = ulog if os.path.isabs(ulog) else os.path.join(args.repo_root, ulog)
                try:
                    by_ts, ts_list, logged, ud = load_ulog(path, cache)
                except (OSError, ulog_min.UlogError) as e:
                    err = str(e)
                else:
                    res = mc.check_row(row, by_attempt.get(row["attempt"], []), by_ts, ts_list, logged)
                    if row["item"] == "3" and f is not None and "arm_send" in f:
                        an = mb.analyze_row(row, ud)
                        analyses[row["attempt"]] = an
                        fv, why, kind = mb.final_verdict_item3(row, an)
                        finals[("3", row["attempt"])] = fv
                        reasons[("3", row["attempt"])] = why
                    elif row["item"] == "2b" and f is not None and "hold_end_ros_us" in f \
                            and f.get("observe_span_s") is not None:
                        start = f["hold_end_ros_us"]
                        obs = mb.hold_observation(ud, start, start + int(f["observe_span_s"] * mb.US))
                        fv, why, kind = mb.final_verdict_2b(row, obs)
                        finals[("2b", row["attempt"])] = fv
                        reasons[("2b", row["attempt"])] = why
                        row["hold_obs_ulog"] = obs
            if err is not None:
                results.append({"item": row["item"], "attempt": row["attempt"], "error": err})
            elif res is not None:
                results.append(res)
                if (row["item"], row["attempt"]) not in finals:     # (3)의 최종 판정은 대역 분석이 정한다
                    finals[(row["item"], row["attempt"])] = res["final_verdict"]
            if row["item"] in mc.ARMED_SUM_ITEMS:
                if measurable:
                    entries.append({
                        "item": row["item"], "class": row["class"], "verdict": row["verdict"],
                        "attempt": row["attempt"], "armed3_reached": bool(f["armed3_reached"]),
                        "ros_count": f["armed_non_offboard"],
                        "ulog_count": None if res is None else (
                            res["ulog_armed_non_offboard"] + res["ulog_flight_armed_non_offboard"]),
                        "ulog_samples": 0 if res is None else res["ulog_samples_in_range"]})
                else:       # 측정되지 않은 행(PRECONDITION, ERROR 등)은 0으로 읽지 않고 unmeasured로 센다
                    entries.append({
                        "item": row["item"], "class": row["class"], "verdict": row["verdict"],
                        "attempt": row["attempt"], "armed3_reached": False, "ros_count": None,
                        "ulog_count": None, "ulog_samples": 0})
        with open(mdir / ("crosscheck_%s.json" % item), "w") as fh:
            json.dump(results, fh, indent=1, sort_keys=True)
            fh.write("\n")
        all_results.extend(results)
        for r in results:
            if "error" in r:
                print("crosscheck %s 시도 %s: %s" % (r["item"], r["attempt"], r["error"]))
            else:
                print("crosscheck %s 시도 %d: ROS %d개 중 ULog에 없음 %d, 필드 불일치 %d, ULog 구간 표본 %d, "
                      "ULog만 있는 표본 %d, ULog 기준 비OFFBOARD ARMED %d(구간 뒤 %d), ULog 최소 간격 %s ms, "
                      "최종 판정 %s%s" % (
                          r["item"], r["attempt"], r["ros_samples"], r["ros_missing_in_ulog"],
                          len(r["ros_field_mismatch"]), r["ulog_samples_in_range"], r["ulog_only"],
                          r["ulog_armed_non_offboard"], r["ulog_armed_non_offboard_after_window"],
                          r["ulog_min_interval_ms"], r["final_verdict"],
                          "(증거 미확인)" if r["evidence_pending"] else ""))
    for path, (_, _, logged, ud) in sorted(cache.items()):
        n_armed_log = sum(1 for m in logged if mc.ARM_LOG_TEXT in m["msg"])
        print("ULog %s: '%s' 줄 %d개" % (os.path.relpath(path, args.repo_root), mc.ARM_LOG_TEXT, n_armed_log))
        tlf = mb.t_lf_samples(ud)
        if tlf:
            print("ULog %s: T_lf 표본 %d개, 최솟값 %.3f s, 최댓값 %.3f s. 이 최솟값으로 계산한 (3)의 지연 목록 %s"
                  % (os.path.relpath(path, args.repo_root), len(tlf), min(tlf), max(tlf),
                     mb.plan_item3_delays(min(tlf))))
    problems = mc.item_problems(requested, rows_by_item, done_items)
    for line in problems:
        print("요청한 항목의 기록이 없다: %s" % line)
    done = not problems
    crit = mc.aggregate_armed(entries)
    summary = mc.final_summary(all_rows, finals, analyses=analyses if analyses else None)
    if analyses:
        item3_rows = [r for r in all_rows if r["item"] == "3"]
        with open(mdir / "bands_item3.json", "w") as fh:
            json.dump({"t_lf_ref": mb.T_LF_REF, "delays_s": list(mb.ITEM3_DELAYS_S),
                       "attempts": {str(a): dict(an, final_verdict=finals.get(("3", a)),
                                                 final_reasons=reasons.get(("3", a), []))
                                    for a, an in sorted(analyses.items())},
                       "summary": summary["3"].get("bands")}, fh, indent=1, sort_keys=True)
            fh.write("\n")
        for r in sorted(item3_rows, key=lambda x: x["attempt"]):
            an = analyses.get(r["attempt"])
            if an is not None:
                print("대역 (3) 시도 %d: 지연 %s 대역 %s t_p-t_A %s r_p %s 최종 %s %s" % (
                    r["attempt"], (r.get("injection") or {}).get("delay_s_nominal"), an.get("band"),
                    an.get("tp_minus_tA_s"), an.get("r_p"), finals.get(("3", r["attempt"])),
                    "; ".join(reasons.get(("3", r["attempt"]), []))))
        for line in mb.top_lines(summary["3"]["bands"]):
            print(line)
    with open(mdir / "final_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")
    for sub_item, d in sorted(summary.items()):
        print("최종 %s: 시도 %d, 유효 %d, PASS %d%s, 제외(자극 불성립) %d, PASS가 아닌 행 %d, "
              "기준과 다른 관측 %d, verdict별 %s%s%s" % (
            sub_item, d["n"], d["n_valid"], d["n_pass"],
            "(대역별 최소는 아래 대역별 충족 여부)" if d.get("bands") else "(최소 %d)" % d["min"],
            d["n_excluded"], d["n_not_pass"],
            d["n_exit1"],
            json.dumps(d["by_verdict"], sort_keys=True),
            ", (가) 미도달 %d회, (나) M3_CONTRADICTED %d회" % (d["case_ga"], d["case_na"])
            if "case_ga" in d else "",
            ", 지연값별 %s" % json.dumps(d["by_delay"], sort_keys=True) if d["by_delay"] else ""))
    for it, item_rows in rows_by_name.items():
        sp = mdir / ("summary_%s.txt" % it)
        if sp.exists():       # measure.py가 만든 요약이 있으면 최종 판정 절을 덧붙인다
            lines = mc.final_section(item_rows, finals, summary)
            if it == "item3" and analyses:
                lines = lines + mb.delay_table_lines([r for r in item_rows if r["item"] == "3"], finals,
                                                     analyses, reasons)
            text = mc.append_final_section(sp.read_text(), lines)
            if it == "item3" and analyses:
                text = mb.insert_top_block(text, mb.top_lines(summary["3"]["bands"]))
            sp.write_text(text)
    crit["note"] = ("이 통과는 PX4 직접 명령 부류(px4_direct)의 통과다. P4 머지 조건은 Executor 경유 부류"
                    "(scenario_a)의 통과가 따로 필요하다. armed_non_offboard 합산은 ROS 기록과 ULog 기록의 합이고 "
                    "2a 행은 n_reached에서 빠지고 violation_total에는 남는다.")
    with open(mdir / "armed_criterion.json", "w") as fh:
        json.dump(crit, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("ARMED 기준(px4_direct 부류가 최상위): %s" % json.dumps(
        {k: v for k, v in crit.items() if k not in ("note", "by_item")}, sort_keys=True))
    if crit["violated_any_class"]:
        print("!! OFFBOARD가 아닌 ARMED 표본이 나왔다. 즉시 architect에게 올린다.")
    print("주의: 위 통과는 PX4 직접 부류다. P4 머지 조건은 Executor 경유 부류의 통과가 따로 필요하다.")
    return mc.crosscheck_status(all_results, crit, summary=summary, meta=mc.meta_ok(all_rows),
                                done=done)


if __name__ == "__main__":
    sys.exit(main())
