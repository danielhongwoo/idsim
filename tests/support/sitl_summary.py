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

"""SITL 실행의 verdict 구조와 회차 요약(순수 코드. 표준 라이브러리와 measure_judge만 쓴다).

pytest 쪽(tests/sitl/conftest.py)이 verdict.json을 쓰고, 호스트의 run_sitl.sh가 tests/sitl/summarize.py를 통해
이 모듈로 summary.md와 repeat_summary.tsv, ARMED 기준(Executor 경유 부류)을 만든다.
OFFBOARD가 아닌 ARMED 표본의 부류별 판정은 measure_judge.judge_armed_criterion을 그대로 쓴다.
"""
from tests.support import measure_judge as mj

SCENARIOS = ("B", "C", "A", "D", "T")     # 실행 순서(decisions.md 쟁점 9)
SCHEMA = 1
ARMED_MIN_REACHED = 10                    # 부류마다 ARMED 3회 확인까지 간 실행 10회 이상


def scenario_result(sid, outcome, category=None, message=None, sim_s=None, wall_s=None, milestones=None):
    return {"id": sid, "outcome": outcome, "category": category, "message": message, "sim_s": sim_s,
            "wall_s": wall_s, "milestones": milestones or {}}


def run_passed(verdict):
    """게이트가 통과하고 다섯 시나리오가 모두 passed인가. 하나라도 빠지면 실패다."""
    if not verdict.get("gate", {}).get("ok"):
        return False
    by_id = {s["id"]: s for s in verdict.get("scenarios", [])}
    return all(by_id.get(i, {}).get("outcome") == "passed" for i in SCENARIOS)


def verdict_cell(verdict, sid):
    """TSV 한 칸. 통과면 PASS, 아니면 분류(없으면 outcome), 기록이 없으면 NONE."""
    row = {s["id"]: s for s in verdict.get("scenarios", [])}.get(sid)
    if row is None:
        return "NONE"
    if row["outcome"] == "passed":
        return "PASS"
    return row.get("category") or row["outcome"].upper()


MILESTONE_COLUMNS = (
    ("A", "accepted"), ("A", "armed"), ("A", "takeoff_start"), ("A", "reached"), ("A", "loiter_start"),
    ("A", "land_start"), ("A", "auto_land"), ("A", "disarmed"), ("A", "result"),
)


def tsv_header():
    cols = ["run_id", "commit", "dirty", "image_px4", "image_ros_ws", "image_sim_base"]
    cols += ["verdict_" + s for s in SCENARIOS]
    cols += ["A_%s_s" % m for _, m in MILESTONE_COLUMNS]
    cols += ["rtf", "sim_s", "wall_s", "armed_a_samples", "armed_a_non_offboard", "armed_a_armed3"]
    return cols


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return "%.3f" % v
    return str(v)


def tsv_row(verdict, wall_total_s=None):
    """회차 요약 한 줄. 이정표는 시나리오 A의 goal 전송을 0으로 한 ROS 시각 소요(초)다."""
    images = verdict.get("images", {})
    ms = {s["id"]: s for s in verdict.get("scenarios", [])}.get("A", {}).get("milestones", {})
    rtf = verdict.get("rtf") or {}
    armed = verdict.get("armed_a") or {}
    cells = [verdict.get("run_id"), verdict.get("git_commit"), verdict.get("git_dirty"),
             images.get("px4"), images.get("ros_ws"), images.get("sim_base")]
    cells += [verdict_cell(verdict, s) for s in SCENARIOS]
    cells += [ms.get(m) for _, m in MILESTONE_COLUMNS]
    cells += [rtf.get("rtf"), rtf.get("sim_s"), wall_total_s if wall_total_s is not None else rtf.get("wall_s"),
              armed.get("armed_samples"), armed.get("armed_non_offboard"), armed.get("armed3_reached")]
    return [_fmt(c) for c in cells]


def armed_rows(verdicts):
    """회차마다 시나리오 A의 ARMED 기록을 measure_judge의 행 형식으로 바꾼다. 측정되지 않은 회는 None 값."""
    rows = []
    for v in verdicts:
        a = v.get("armed_a")
        measured = a is not None
        rows.append({
            "item": "A", "class": mj.CLASS_EXECUTOR, "verdict": "PASS" if run_passed(v) else "FAIL",
            "armed3_reached": bool(a and a.get("armed3_reached")),
            "armed_non_offboard": a["armed_non_offboard"] if measured else None,
        })
    return rows


def armed_criterion(verdicts, min_reached=ARMED_MIN_REACHED):
    """Executor 경유(시나리오 A) 부류의 ARMED 기준. 부류별 n_reached, 위반 수, passed.

    ROS 기록만의 판정이다. ULog와의 교차 확인(PX4가 정본)은 crosscheck_a.py가 따로 한다.
    """
    crit = mj.judge_armed_criterion(armed_rows(verdicts), min_reached)
    return crit["classes"].get(mj.CLASS_EXECUTOR) | {"violated_any_class": crit["violated_any_class"]}


def summary_md(verdict, step_seconds=None):
    """실행 하나의 summary.md. step_seconds: [(단계, 초)] 호스트 단계별 시간."""
    lines = ["# sitl 실행 요약", "",
             "- 실행 id: %s" % verdict.get("run_id"),
             "- commit: %s (dirty: %s)" % (verdict.get("git_commit"), verdict.get("git_dirty")),
             "- 이미지: %s" % ", ".join("%s=%s" % (k, v) for k, v in sorted(verdict.get("images", {}).items()) if v),
             "- 전체 결과: %s" % ("통과" if run_passed(verdict) else "실패"), ""]
    gate = verdict.get("gate", {})
    lines += ["## 시나리오", "", "| 시나리오 | 결과 | 분류 | ROS 시각 초 | 벽시계 초 | 설명 |", "| --- | --- | --- | --- | --- | --- |"]
    lines.append("| gate | %s | %s | %s | %s | %s |" % (
        "passed" if gate.get("ok") else "failed", gate.get("category") or "-", _fmt(gate.get("sim_s")),
        _fmt(gate.get("wall_s")), (gate.get("message") or "")[:200]))
    for s in verdict.get("scenarios", []):
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            s["id"], s["outcome"], s.get("category") or "-", _fmt(s.get("sim_s")), _fmt(s.get("wall_s")),
            (s.get("message") or "").replace("|", "/")[:200]))
    rtf = verdict.get("rtf")
    if rtf:
        lines += ["", "판정 구간 RTF: %s (ROS 시각 %s s / 벽시계 %s s)" % (
            _fmt(rtf.get("rtf")), _fmt(rtf.get("sim_s")), _fmt(rtf.get("wall_s")))]
    a = verdict.get("armed_a")
    if a:
        lines += ["", "시나리오 A ARMED 표본: %s개, OFFBOARD가 아닌 ARMED 표본 %s개, ARMED 3회 확인 %s" % (
            a.get("armed_samples"), a.get("armed_non_offboard"), a.get("armed3_reached"))]
    ms = {s["id"]: s for s in verdict.get("scenarios", [])}.get("A", {}).get("milestones", {})
    if ms:
        lines += ["", "## 시나리오 A 이정표(goal 전송 기준 ROS 시각 초)", "", "| 이정표 | 초 |", "| --- | --- |"]
        lines += ["| %s | %s |" % (k, _fmt(v)) for k, v in sorted(ms.items(), key=lambda kv: (kv[1] is None, kv[1]))]
    if step_seconds:
        lines += ["", "## 단계별 벽시계 시간", "", "| 단계 | 초 |", "| --- | --- |"]
        lines += ["| %s | %s |" % (n, s) for n, s in step_seconds]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ULog가 닫혔는가(compose stop -t 15 뒤)

_ULOG_MAGIC = b"ULog\x01\x12\x35"


def ulog_tail_check(data):
    """ULog 바이트가 메시지 경계에서 끝나는가. 끝이 잘렸으면 truncated=True(KILL로 끝났을 가능성).

    pyulog가 없는 호스트에서 쓰려고 헤더와 메시지 길이만 걷는다. 이것은 "파일이 메시지 경계에서 끝난다"만
    말하고 PX4가 정상 종료했다는 증거는 아니다(정상 종료는 서비스 종료 코드와 함께 본다).
    """
    import struct

    if data[:7] != _ULOG_MAGIC:
        return {"ok": False, "reason": "ULog header가 아니다", "messages": 0, "bytes": len(data)}
    pos, n = 16, 0
    while pos + 3 <= len(data):
        size, _ = struct.unpack_from("<HB", data, pos)
        if pos + 3 + size > len(data):
            return {"ok": True, "truncated": True, "messages": n, "bytes": len(data)}
        pos += 3 + size
        n += 1
    return {"ok": True, "truncated": pos != len(data), "messages": n, "bytes": len(data)}
