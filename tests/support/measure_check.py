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

"""측정 기록의 교차 확인과 종료 코드 집계(순수 코드). measure.py와 crosscheck.py가 쓴다.

여기 있는 것: ROS 원시 표본과 ULog vehicle_status의 대조(check_row), ARMED 기준에 넣을 행의 선택과
ROS/ULog 합산(armed_rows, aggregate_armed), 종료 코드 집계(run_status, crosscheck_status).
입출력과 rclpy가 없어 tests/support의 단위 테스트가 SITL 없이 검증한다.

종료 코드: 0 통과, 1 기준과 다른 관측(FAIL, M3_CONTRADICTED, ARMED 위반(어느 부류든), 대조 불일치),
2 그 밖(입력 부족, 유효 시도 수 부족, 인프라, ERROR, 판정하지 않는 verdict). 1이 2보다 앞선다.
"""
from tests.support import measure_judge as mj

# ARMED 기준(비OFFBOARD ARMED 표본 0개)에 합산할 항목(architect 결정). 2a는 위반 수에는 넣지만
# n_reached에서는 judge_armed_criterion이 뺀다. armed 항목은 PX4 직접 부류로 넣는다. 바꾸기 쉽게
# 이 상수 하나로 둔다.
ARMED_SUM_ITEMS = ("2a", "3", "5", "armed")

# 항목별 최소 시도 수(PASS 기준 횟수). measure.py와 crosscheck.py가 같은 값을 쓴다.
MIN_ATTEMPTS_BY_ITEM = {"2a": 3, "2b": 3, "3": 3, "5": 10, "armed": 10}

CROSS_FIELDS = (("arming_state", "arming_state"), ("nav_state", "nav_state"),
                ("failsafe", "failsafe"), ("nav_state_user_intention", "intention"))


def armed_rows(rows, items=ARMED_SUM_ITEMS):
    """합산 대상 행만 고른다(2b처럼 ARMED 구간이 없는 행은 넣지 않는다)."""
    return [r for r in rows if r["item"] in items]


def _ulog_equal(key, ulog_val, ros_val):
    if key == "failsafe":
        return bool(ulog_val) == bool(ros_val)
    return int(ulog_val) == int(ros_val)


ARM_LOG_TEXT = "Armed by external command"


def ulog_arm_evidence(arm_ts, end_ts, ulog_by_ts, ulog_ts, logged):
    """ULog 기준 arm 수락 증거. A: arm 전송 Px4Timestamp 뒤의 ARMED 표본, B: logged message
    '[commander] Armed by external command'가 [arm_ts, end_ts] 안. 표본이 없는 것은 미수락의 증거가
    아니다(한 Commander 주기에 arm과 disarm이 처리되면 ARMED 표본이 나오지 않는다)."""
    a = any(arm_ts < t <= end_ts and int(ulog_by_ts[t]["arming_state"]) == mj.ARMING_STATE_ARMED
            for t in ulog_ts)
    b = any(arm_ts <= m["ts"] <= end_ts and ARM_LOG_TEXT in m["msg"] for m in logged)
    return {"A_armed_sample": a, "B_armed_log": b}


def final_verdict(row, evidence, consistent=True):
    """live 판정을 ULog 증거로 확정한다. (5)가 arm 수락 증거 미확인으로 INCONCLUSIVE였던 행만 바뀐다.

    돌려주는 (verdict, pending).
      증거 있음(A 또는 B) + 대조 일치: ("PASS", False)
      대조 불일치(consistent False): ("INCONCLUSIVE", True). 증거가 있어도 올리지 않고 row_status가 1로 본다.
      대조 일치 + 증거가 끝내 없음: ("ARM_NOT_ACCEPTED", False). 자극이 성립하지 않은 회라 시도 수에도
        not-pass 집계에도 넣지 않는다(최종 판정 단계에서만. measure.py 단독의 증거 미확인은 2다).
    """
    # 증거 미확인으로 INCONCLUSIVE가 된 행만 승격한다. 값이 없어서(예: climb_m None) INCONCLUSIVE인
    # 행은 증거가 있어도 승격하지 않는다.
    if row["item"] == "5" and row["verdict"] == "INCONCLUSIVE" and row["inconclusive_kind"] == "ARM_EVIDENCE":
        if not consistent:
            return "INCONCLUSIVE", True
        if evidence["A_armed_sample"] or evidence["B_armed_log"]:
            return "PASS", False
        return "ARM_NOT_ACCEPTED", False
    return row["verdict"], False


def check_row(row, raw_status, ulog_by_ts, ulog_ts, logged=()):
    """한 시도 행을 ULog와 대조한다. 대조 구간이 없는 행(ARMED 구간 없음, 측정 안 됨)은 None.

    row: measure_<item>.jsonl의 한 행(facts에 armed_window_ros_us, arm_send 필요. 없으면 KeyError).
    raw_status: 그 시도의 raw status 표본(dict, ts_us/recv_ros_us/...).
    ulog_by_ts: {timestamp: ULog 행}, ulog_ts: 정렬된 timestamp 목록.

    두 구간을 쓴다.
      위반 구간 [arm 전송의 Px4Timestamp, ARMED 구간 끝]: ULog 기준 비OFFBOARD ARMED를 센다.
      대조 구간 [arm 전송의 Px4Timestamp, max(ROS 마지막 표본의 ts, 정리 종료 시각, NAV_LAND 전송 시각)]:
        ROS 표본이 ULog에 있는지, ULog에만 있는 표본(ROS 유실)이 있는지 본다. 종료 시각은 ROS 수신
        시각을 PX4 timestamp 축의 근사로 쓴다(두 축은 같은 sim 시간이고 차이의 분포는 distribution_*.json).
    armed 항목(facts에 land_send)은 ARMED 3회 확인부터 NAV_LAND 전송까지(위반 구간 뒤)의 ULog 비OFFBOARD
    ARMED도 위반으로 센다(ulog_flight_armed_non_offboard).
    """
    f = row["facts"]
    if f is None or "armed_window_ros_us" not in f:
        return None
    lo_recv, win_recv = f["armed_window_ros_us"]
    lo_ts = f["arm_send"][1]
    end_recv = f["cleanup_end_ros_us"] if "cleanup_end_ros_us" in f else win_recv
    end_recv = max(end_recv, win_recv)
    has_flight = "land_send" in f and f["land_send"] is not None
    if has_flight:
        end_recv = max(end_recv, f["land_send"][0])
    ros = [s for s in raw_status if lo_recv <= s["recv_ros_us"] <= end_recv]
    ros_last_ts = max([s["ts_us"] for s in ros], default=lo_ts)
    wide_hi = max(ros_last_ts, end_recv)
    win_hi = max([s["ts_us"] for s in ros if s["recv_ros_us"] <= win_recv], default=lo_ts)
    win_hi = max(win_hi, win_recv)

    missing = 0
    mismatch = []
    for s in ros:
        u = ulog_by_ts.get(s["ts_us"])
        if u is None:
            missing += 1
            continue
        for ukey, rkey in CROSS_FIELDS:
            if not _ulog_equal(ukey, u[ukey], s[rkey]):
                mismatch.append({"ts_us": s["ts_us"], "field": ukey, "ulog": u[ukey], "ros": s[rkey]})
    ros_ts = {s["ts_us"] for s in ros}
    in_range = [t for t in ulog_ts if lo_ts <= t <= wide_hi]
    ulog_only = [t for t in in_range if t not in ros_ts]

    def armed_bad(ts_list):
        n = 0
        bad = []
        for t in ts_list:
            u = ulog_by_ts[t]
            if int(u["arming_state"]) == mj.ARMING_STATE_ARMED:
                n += 1
                if int(u["nav_state"]) != mj.NAV_STATE_OFFBOARD:
                    bad.append({"ts_us": t, "nav_state": u["nav_state"], "failsafe": u["failsafe"],
                                "intention": u["nav_state_user_intention"]})
        return n, bad

    n_armed, bad = armed_bad([t for t in in_range if t <= win_hi])
    _, bad_after = armed_bad([t for t in in_range if t > win_hi])
    flight = len(bad_after) if has_flight else 0
    gaps = [b - a for a, b in zip(in_range, in_range[1:])]
    evidence = ulog_arm_evidence(lo_ts, wide_hi, ulog_by_ts, ulog_ts, logged)
    consistent = not (missing > 0 or not in_range or mismatch or bad or flight or ulog_only)
    verdict, pending = final_verdict(row, evidence, consistent)
    return {
        "final_verdict": verdict, "evidence_pending": pending, "arm_evidence_ulog": evidence,
        "item": row["item"], "attempt": row["attempt"], "ros_samples": len(ros),
        "ros_missing_in_ulog": missing, "ros_field_mismatch": mismatch,
        "ulog_samples_in_range": len(in_range), "ulog_only": len(ulog_only),
        "ulog_armed_samples": n_armed, "ulog_armed_non_offboard": len(bad),
        "ulog_armed_non_offboard_samples": bad,
        "ulog_armed_non_offboard_after_window": len(bad_after),
        "ulog_flight_armed_non_offboard": flight,
        "ulog_min_interval_ms": (min(gaps) / 1000.0) if gaps else None,
        "ts_range_us": [lo_ts, wide_hi], "violation_range_us": [lo_ts, win_hi],
    }


def row_status(res):
    """check_row 결과 하나의 종료 코드. 순서: (1) error(ULog를 못 읽음)는 2, (2) 대조 이상(ROS 표본이
    ULog에 없음, ULog 구간 표본 0개, 필드 불일치, ULog 기준 비OFFBOARD ARMED, ULog에만 있는 표본)은 1,
    (3) 그 뒤에야 arm 수락 증거 미확인(evidence_pending)을 2로 본다. 그래서 대조가 어긋난 행은 증거
    미확인보다 먼저 1로 보고된다."""
    if "error" in res:
        return 2
    if (res["ros_missing_in_ulog"] > 0 or res["ulog_samples_in_range"] == 0
            or res["ros_field_mismatch"] or res["ulog_armed_non_offboard"] > 0
            or res["ulog_flight_armed_non_offboard"] > 0 or res["ulog_only"] > 0):
        return 1
    if res["evidence_pending"]:
        return 2
    return 0


def aggregate_armed(entries, min_reached=10):
    """ROS와 ULog를 합산한 ARMED 기준.

    entries: [{"item", "class", "verdict", "attempt", "armed3_reached", "ros_count", "ulog_count",
    "ulog_samples"}]. class는 judge의 CLASS_DIRECT/CLASS_EXECUTOR다.
    ros_count가 None이면 측정되지 않은 행이다(0으로 읽지 않고 unmeasured로 센다).
    ulog_count가 None이면 ULog를 못 읽은 행이다(ROS 쪽 위반 수만 합산하고 unreadable로 센다).
    ULog를 못 읽은 행이나 측정 안 된 행이 있거나 전체 ULog 표본 합이 0이면(대조가 비어 있었다는 뜻)
    passed는 false다.
    """
    rows = []
    unreadable = 0
    ulog_total = 0
    for e in entries:
        if e["ros_count"] is None:
            n = None
        elif e["ulog_count"] is None:
            unreadable += 1
            n = e["ros_count"]
        else:
            n = e["ros_count"] + e["ulog_count"]
            ulog_total += e["ulog_samples"]
        rows.append({"item": e["item"], "class": e["class"], "verdict": e["verdict"],
                     "armed3_reached": e["armed3_reached"], "armed_non_offboard": n})
    crit = mj.judge_armed_criterion(rows, min_reached)
    crit["ulog_total_samples"] = ulog_total
    crit["n_ulog_unreadable"] = unreadable
    if ulog_total == 0 or unreadable or crit["n_unmeasured"]:
        crit["passed"] = False
        for c in crit["classes"].values():
            c["passed"] = False
    by_item = {}
    for e in entries:
        d = by_item.setdefault(e["item"], {"rows": 0, "reached": 0, "ros": 0, "ulog": 0})
        d["rows"] += 1
        d["reached"] += 1 if e["armed3_reached"] else 0
        d["ros"] += e["ros_count"] or 0
        d["ulog"] += e["ulog_count"] or 0
    crit["by_item"] = by_item
    return crit


def final_summary(rows, finals, min_by_item=MIN_ATTEMPTS_BY_ITEM):
    """crosscheck 뒤 최종 판정(final_verdict) 기준의 항목별 요약.

    rows: measure 행(item, attempt, injection, verdict). finals: {(item, attempt): 최종 verdict}.
    항목마다 n, n_valid(PASS, FAIL, M3_CONTRADICTED만. INCONCLUSIVE 등은 유효 시도가 아니다), n_pass,
    n_excluded(자극이 성립하지 않은 회: WINDOW_MISSED, ARM_NOT_ACCEPTED. 행과 횟수는 기록하지만 유효 시도에도
    n_not_pass에도 넣지 않는다), n_not_pass(최종 verdict가 PASS도 제외도 아닌 행 수), n_exit1,
    by_verdict(최종 verdict별 횟수), enough(n_pass >= 최소 시도 수 그리고 n_not_pass == 0),
    by_delay((5)의 명목 지연값별 n, n_valid, n_pass, n_excluded)를 낸다. 판정 안 된 행이 하나라도 있으면
    PASS 횟수를 채워도 enough가 아니다(종료 코드 2). 시도 수는 실행 전에 정하고 결과를 보고 더하지 않는다.
    2b는 (가) 미도달(COND_NOT_REACHED)과 (나) M3_CONTRADICTED를 case_ga, case_na로 따로 센다.
    """
    out = {}
    for r in rows:
        sub = r["item"]
        v = finals.get((sub, r["attempt"]), r["verdict"])
        d = out.setdefault(sub, {"n": 0, "n_valid": 0, "n_pass": 0, "n_excluded": 0, "n_not_pass": 0,
                                 "n_exit1": 0, "by_verdict": {}, "by_delay": {}})
        d["n"] += 1
        d["by_verdict"][v] = d["by_verdict"].get(v, 0) + 1
        excluded = v in mj.EXCLUDED_VERDICTS
        d["n_excluded"] += 1 if excluded else 0
        d["n_not_pass"] += 0 if (v == "PASS" or excluded) else 1
        valid = v in mj.VALID_VERDICTS
        d["n_valid"] += 1 if valid else 0
        d["n_pass"] += 1 if v == "PASS" else 0
        d["n_exit1"] += 1 if v in mj.EXIT1_VERDICTS else 0
        if sub == "5" and r["injection"] is not None:
            e = d["by_delay"].setdefault(str(r["injection"]["delay_s_nominal"]),
                                         {"n": 0, "n_valid": 0, "n_pass": 0, "n_excluded": 0})
            e["n"] += 1
            e["n_excluded"] += 1 if excluded else 0
            e["n_valid"] += 1 if valid else 0
            e["n_pass"] += 1 if v == "PASS" else 0
    for sub, d in out.items():
        d["min"] = min_by_item[sub]
        d["enough"] = d["n_pass"] >= d["min"] and d["n_not_pass"] == 0
        if sub == "2b":
            d["case_ga"] = d["by_verdict"].get("COND_NOT_REACHED", 0)
            d["case_na"] = d["by_verdict"].get("M3_CONTRADICTED", 0)
    return out


def item_problems(requested, rows_by_item, done_items):
    """요청한 item마다 행과 완료 기록(done_<item>.json)이 있는가. 없는 item의 사유 목록을 돌려준다.

    requested: 요청 item 이름 목록(item2 등). rows_by_item: {item 이름: 행 수}. done_items: 완료 기록이
    있는 item 이름 집합. measure.py가 기록을 만들기 전에 죽은 item도 여기서 드러난다."""
    out = []
    for it in requested:
        if rows_by_item.get(it, 0) == 0:
            out.append("%s: 기록(measure_%s.jsonl)이 없거나 행이 0개" % (it, it))
        if it not in done_items:
            out.append("%s: 완료 기록(done_%s.json)이 없음" % (it, it))
    return out


REQUIRED_ROW_KEYS = ("inconclusive_kind", "class", "args")


def rows_schema_problems(rows):
    """crosscheck가 읽는 행에 필요한 키가 있는가. 없는 키 목록의 사유 문장(없으면 빈 목록).

    trial5 이전에 만든 기록은 inconclusive_kind 같은 키가 없어 crosscheck가 읽을 수 없다. KeyError로 죽는
    대신 사유와 함께 종료 코드 2로 끝내기 위한 검사다."""
    out = []
    for r in rows:
        miss = [k for k in REQUIRED_ROW_KEYS if k not in r]
        if miss:
            out.append("행(item %s, 시도 %s)에 키 %s가 없다. 이 판의 measure.py가 만든 기록이 아니다"
                       % (r.get("item"), r.get("attempt"), miss))
    return out


def meta_ok(rows):
    """행의 commit과 image key가 있는가(commit unknown이나 image key null이면 False)."""
    return bool(rows) and all(r["commit"] not in (None, "", "unknown") and r["image_keys"] is not None
                              for r in rows)


def crosscheck_status(results, crit, summary=None, meta=True, done=True):
    """crosscheck 전체의 종료 코드. 1이 2보다 앞선다.

    1: 행 대조 이상, ARMED 위반(어느 부류든 violated_any_class), ULog 표본 합 0, 최종 판정이 FAIL이나
       M3_CONTRADICTED인 시도.
    2: 결과 0개, ULog를 못 읽음, (5)의 증거 미확인, 항목별 PASS 횟수 부족(summary), ARMED 3회 도달 실행
       부족, commit unknown이나 image key 없음(meta False), measure.py의 완료 기록 없음(done False).
    """
    fail = False
    other = False
    for r in results:
        st = row_status(r)
        fail = fail or st == 1
        other = other or st == 2
    if crit["violated_any_class"]:
        fail = True
    if crit["ulog_total_samples"] == 0:
        fail = True
    elif not crit["enough"]:
        other = True
    if summary is not None:
        for d in summary.values():
            if d["n_exit1"]:
                fail = True
            elif not d["enough"]:
                other = True
    if not results or not meta or not done:
        other = True
    return 1 if fail else (2 if other else 0)


def run_status(rows, min_attempts, meta_ok=True, crit=None):
    """measure.py 한 실행의 종료 코드.

    rows: 모든 행(item, verdict 키). min_attempts: 항목의 최소 시도 수(유효 시도 기준).
    행이 0개, PASS와 FAIL이 아닌 verdict(COND_NOT_REACHED, HOLD_END, INCONCLUSIVE,
    PRECONDITION, ERROR 등), 유효 시도 수 부족, 메타 부족(commit unknown, image key null)은 2.
    EXCLUDED_VERDICTS 중 WINDOW_MISSED(measure.py 안에서 정해지는 자극 불성립)는 유효 시도에도 not-pass에도
    넣지 않는다. (5)의 증거 미확인 INCONCLUSIVE는 ULog 교차 확인 전이라 여기서는 2다(제외는 crosscheck의
    최종 판정 단계에서만).
    FAIL, M3_CONTRADICTED, ARMED 위반(violated_any_class, 어느 부류든)이 하나라도 있으면 1이 2보다 앞선다.
    """
    if not rows:
        return 2
    status = 0 if meta_ok else 2
    fail = False
    for sub in sorted({r["item"] for r in rows}):
        rs = [r for r in rows if r["item"] == sub and r["verdict"] != "WINDOW_MISSED"]
        n_pass = sum(1 for r in rs if r["verdict"] == "PASS")
        n_valid = sum(1 for r in rs if r["verdict"] in mj.VALID_VERDICTS)
        if any(r["verdict"] in mj.EXIT1_VERDICTS for r in rs):
            fail = True
        elif n_valid < min_attempts or n_pass != len(rs):
            status = max(status, 2)
    if crit is not None and crit["violated_any_class"]:
        fail = True
    return 1 if fail else status


FINAL_SECTION_MARKER = "## 최종 판정 (crosscheck 뒤)"


def final_section(rows, finals, summary):
    """crosscheck 뒤 summary_<item>.txt에 덧붙일 최종 판정 절의 줄 목록.

    rows: 그 item 파일의 measure 행. finals: {(item, attempt): 최종 verdict}. summary: final_summary 결과.
    measure.py 단독 판정(행의 verdict)과 최종 판정이 다른 행을 따로 적는다."""
    lines = [FINAL_SECTION_MARKER,
             "아래가 최종 판정이다. 위 '결과' 절은 crosscheck 전 measure.py 단독 판정이다(final_summary.json과 같은 값)."]
    subs = sorted({r["item"] for r in rows})
    for sub in subs:
        d = summary[sub]
        if d["n_valid"] and d["n_exit1"] == 0:
            bound = ", 무실패일 때 실패율 95%% 상한 %s" % mj.upper95_text(d["n_valid"])
        else:
            bound = ""
        lines.append("%s: 시도 %d, 유효 %d, PASS %d(최소 %d), 제외(자극 불성립) %d, PASS가 아닌 행 %d, "
                     "기준과 다른 관측 %d, 유효 시도 수 충분 %s, verdict별 %s%s" % (
                         sub, d["n"], d["n_valid"], d["n_pass"], d["min"], d["n_excluded"], d["n_not_pass"],
                         d["n_exit1"], d["enough"], dict(sorted(d["by_verdict"].items())), bound))
        if d["by_delay"]:
            lines.append("  지연값별: %s" % dict(sorted(d["by_delay"].items())))
    diff = [r for r in rows if finals.get((r["item"], r["attempt"]), r["verdict"]) != r["verdict"]]
    if diff:
        lines.append("measure.py 단독 판정과 다른 행:")
        for r in sorted(diff, key=lambda r: (r["item"], r["attempt"])):
            lines.append("  %s 시도 %d: %s -> %s" % (
                r["item"], r["attempt"], r["verdict"], finals[(r["item"], r["attempt"])]))
    else:
        lines.append("measure.py 단독 판정과 다른 행: 없음")
    return lines


def append_final_section(text, lines):
    """요약 본문에 최종 판정 절을 덧붙인다. 이미 있는 절은 떼고 새로 붙인다(--force 재실행에서 중복 방지)."""
    i = text.find("\n" + FINAL_SECTION_MARKER)
    if i >= 0:
        text = text[:i]
    return text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"
