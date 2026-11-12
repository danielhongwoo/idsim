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

"""tests/sitl/summarize.py(run_sitl.sh가 부르는 호스트 쪽 요약 도구)의 단위 테스트."""
import importlib.util
import json
from pathlib import Path

from tests.support import sitl_summary as ss
from tests.support.test_sitl_summary import verdict

PATH = Path(__file__).resolve().parents[1] / "sitl" / "summarize.py"
spec = importlib.util.spec_from_file_location("sitl_summarize", PATH)
summarize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarize)


def write_verdict(run_dir, v, sitl="sitl"):
    d = run_dir / sitl
    d.mkdir(parents=True)
    (d / "verdict.json").write_text(json.dumps(v), encoding="utf-8")


def test_run_writes_utf8_summary_and_returns_pass(tmp_path):
    v = verdict()
    v["passed"] = True
    write_verdict(tmp_path, v)
    assert summarize.main(["run", str(tmp_path), "--steps", "up=100,pytest=200"]) == 0
    text = (tmp_path / "sitl" / "summary.md").read_text(encoding="utf-8")
    assert "통과" in text and "| pytest | 200 |" in text


def test_run_returns_failure_for_failed_verdict(tmp_path):
    v = verdict(passed=False)
    v["passed"] = False
    write_verdict(tmp_path, v)
    assert summarize.main(["run", str(tmp_path)]) == 1


def test_run_without_verdict_uses_fallback_category(tmp_path):
    assert summarize.main(["run", str(tmp_path), "--fallback", "INFRA_UP:올리기 실패"]) == 1
    text = (tmp_path / "sitl" / "summary.md").read_text(encoding="utf-8")
    assert "INFRA_UP" in text and "올리기 실패" in text


def test_run_passed_field_is_not_trusted_over_exitstatus(tmp_path):
    # pytest가 비정상 종료한 verdict(passed false)는 시나리오 표가 모두 통과여도 실패다
    v = verdict()
    v["passed"] = False
    write_verdict(tmp_path, v)
    assert summarize.main(["run", str(tmp_path)]) == 1


def test_repeat_writes_tsv_and_criterion(tmp_path):
    files = []
    for i in range(3):
        d = tmp_path / ("r%d" % i)
        write_verdict(d, verdict(run_id="r%d" % i))
        files.append(str(d / "sitl" / "verdict.json"))
    out = tmp_path / "group"
    assert summarize.main(["repeat", "--out", str(out)] + files) == 0
    lines = (out / "repeat_summary.tsv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and lines[0].split("\t") == ss.tsv_header()
    crit = json.loads((out / "armed_criterion.json").read_text(encoding="utf-8"))
    assert crit["n_reached"] == 3 and crit["passed"] is False      # 10회 미만은 통과가 아니다


def test_ops_running(tmp_path):
    ps = tmp_path / "ps.jsonl"
    ps.write_text('{"Service":"ops-1","State":"running"}\n{"Service":"bridge","State":"running"}\n', encoding="utf-8")
    assert summarize.main(["ops-running", str(ps), "ops-1"]) == 0
    ps.write_text('[{"Service":"ops-1","State":"exited"}]\n', encoding="utf-8")
    assert summarize.main(["ops-running", str(ps), "ops-1"]) == 1
    assert summarize.main(["ops-running", str(ps), "ops-2"]) == 1


def test_ulog_check_reports_truncation(tmp_path):
    log = tmp_path / "px4-1" / "log" / "d"
    log.mkdir(parents=True)
    import struct
    data = b"ULog\x01\x12\x35" + b"\x01" + b"\x00" * 8 + struct.pack("<HB", 4, 0x4C) + b"\x00" * 4
    (log / "a.ulg").write_bytes(data)
    (log / "b.ulg").write_bytes(data[:-2])
    assert summarize.main(["ulog", str(tmp_path)]) == 0
    text = (tmp_path / "sitl" / "ulog_check.txt").read_text(encoding="utf-8")
    assert "a.ulg bytes=" in text and "truncated=False" in text and "truncated=True" in text


def _crosscheck_module():
    p = Path(__file__).resolve().parents[1] / "sitl" / "crosscheck_a.py"
    sp = importlib.util.spec_from_file_location("sitl_crosscheck_a", p)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def test_crosscheck_unhandled_exception_is_infra_not_violation(tmp_path):
    cc = _crosscheck_module()
    sitl = tmp_path / "sitl"
    sitl.mkdir()
    (sitl / "armed_a.json").write_text('{"takeoff_start_seen": true}', encoding="utf-8")   # land_start 키가 없다
    (sitl / "raw_status_A.jsonl").write_text('{"timestamp": 1}\n', encoding="utf-8")        # 키가 모자란 표본 -> KeyError
    (tmp_path / "px4-1" / "log").mkdir(parents=True)
    (tmp_path / "px4-1" / "log" / "a.ulg").write_bytes(b"x")
    assert cc.main([str(tmp_path)]) == 2
    res = json.loads((sitl / "crosscheck_a.json").read_text(encoding="utf-8"))
    assert res["status"] == 2 and "KeyError" in res["reason"]


def test_crosscheck_missing_inputs_is_two(tmp_path):
    assert _crosscheck_module().main([str(tmp_path)]) == 2


def test_hold_deviation_is_recorded_and_noted(tmp_path):
    v = verdict()
    v["hold_deviation_m"] = {"A_loiter": 0.1, "D_hover": 0.31}
    assert ss.hold_notes(v) == ["D_hover 유지 구간 최대 편차 0.310 m > 0.25 m (판정 상수 0.5 m 재검토 근거)"]
    row = dict(zip(ss.tsv_header(), ss.tsv_row(v)))
    assert row["hold_dev_A_loiter_m"] == "0.100" and row["hold_dev_D_hover_m"] == "0.310"
    assert "note: D_hover" in ss.summary_md(v)
    v["passed"] = True
    write_verdict(tmp_path / "r", v)
    out = tmp_path / "g"
    assert summarize.main(["repeat", "--out", str(out), str(tmp_path / "r" / "sitl" / "verdict.json")]) == 0
    crit = json.loads((out / "armed_criterion.json").read_text(encoding="utf-8"))
    assert crit["hold_deviation_notes"][0][1].startswith("D_hover")
