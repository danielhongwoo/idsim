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

"""sitl_summary 단위 테스트."""
from tests.support import measure_judge as mj
from tests.support import sitl_summary as ss


def verdict(passed=True, armed_non_offboard=0, armed3=True, run_id="r1", with_armed=True):
    scen = []
    for sid in ss.SCENARIOS:
        ok = passed or sid != "A"
        scen.append(ss.scenario_result(
            sid, "passed" if ok else "failed", None if ok else "TIMEOUT_SIM", None if ok else "m", 3.0, 4.0,
            {"accepted": 0.1, "armed": 1.0, "takeoff_start": 3.0} if sid == "A" else None))
    v = {"run_id": run_id, "git_commit": "abc", "git_dirty": False,
         "images": {"px4": "k1", "ros_ws": "k2", "sim_base": "k3"},
         "gate": {"ok": True}, "scenarios": scen, "rtf": {"rtf": 0.95, "sim_s": 95.0, "wall_s": 100.0}}
    if with_armed:
        v["armed_a"] = {"armed_samples": 4, "armed_non_offboard": armed_non_offboard, "armed3_reached": armed3}
    return v


def test_run_passed_needs_gate_and_all_five():
    assert ss.run_passed(verdict())
    assert not ss.run_passed(verdict(passed=False))
    v = verdict()
    v["gate"] = {"ok": False}
    assert not ss.run_passed(v)
    v = verdict()
    v["scenarios"] = v["scenarios"][:-1]       # T가 빠진 실행은 통과가 아니다
    assert not ss.run_passed(v)


def test_verdict_cell():
    v = verdict(passed=False)
    assert ss.verdict_cell(v, "B") == "PASS"
    assert ss.verdict_cell(v, "A") == "TIMEOUT_SIM"
    assert ss.verdict_cell({"scenarios": []}, "A") == "NONE"


def test_tsv_row_matches_header_width():
    assert len(ss.tsv_row(verdict())) == len(ss.tsv_header())
    row = dict(zip(ss.tsv_header(), ss.tsv_row(verdict(), wall_total_s=123.0)))
    assert row["verdict_A"] == "PASS" and row["A_armed_s"] == "1.000" and row["wall_s"] == "123.000"
    assert row["A_land_start_s"] == "-" and row["armed_a_samples"] == "4"


def test_armed_criterion_needs_ten_reached_runs():
    assert not ss.armed_criterion([verdict(run_id=str(i)) for i in range(9)])["passed"]
    ok = ss.armed_criterion([verdict(run_id=str(i)) for i in range(10)])
    assert ok["passed"] and ok["n_reached"] == 10 and ok["violation_total"] == 0


def test_armed_criterion_violation_fails_and_is_flagged():
    vs = [verdict(run_id=str(i)) for i in range(10)] + [verdict(armed_non_offboard=1, run_id="x")]
    c = ss.armed_criterion(vs)
    assert not c["passed"] and c["violated"] and c["violated_any_class"]


def test_armed_criterion_unmeasured_run_is_not_zero():
    vs = [verdict(run_id=str(i)) for i in range(10)] + [verdict(with_armed=False, run_id="u")]
    c = ss.armed_criterion(vs)
    assert c["n_unmeasured"] == 1 and c["n_reached"] == 10


def test_armed_criterion_run_without_armed3_is_not_counted():
    vs = [verdict(armed3=False, run_id=str(i)) for i in range(10)]
    assert ss.armed_criterion(vs)["n_reached"] == 0


def test_executor_class_is_scenario_a():
    rows = ss.armed_rows([verdict()])
    assert rows[0]["class"] == mj.CLASS_EXECUTOR == "scenario_a"


def test_summary_md_contains_table_and_failure_reason():
    md = ss.summary_md(verdict(passed=False), [("up", 100)])
    assert "TIMEOUT_SIM" in md and "| up | 100 |" in md and "실패" in md


def _ulog(*payload_sizes, extra=b""):
    import struct
    data = b"ULog\x01\x12\x35" + b"\x01" + b"\x00" * 8
    for n in payload_sizes:
        data += struct.pack("<HB", n, 0x4C) + b"\x00" * n
    return data + extra


def test_ulog_tail_check():
    assert ss.ulog_tail_check(_ulog(10, 20)) == {"ok": True, "truncated": False, "messages": 2, "bytes": 16 + 13 + 23}
    cut = ss.ulog_tail_check(_ulog(10, 20)[:-5])
    assert cut["ok"] and cut["truncated"] and cut["messages"] == 1
    assert ss.ulog_tail_check(_ulog(10, extra=b"\x01\x02"))["truncated"]
    assert not ss.ulog_tail_check(b"nope")["ok"]
