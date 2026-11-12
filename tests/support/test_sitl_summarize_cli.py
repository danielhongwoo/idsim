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
