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

"""tests/sitl의 pytest 설정. 스택은 호스트의 run_sitl.sh가 올렸고, 여기서는 붙어서 검증만 한다.

환경: IDSIM_STACK_FILE(stack.json 경로), IDSIM_SITL_OUT(실행 디렉터리 아래 출력 디렉터리 이름, 기본 sitl).
산출물(<실행 디렉터리>/<출력 디렉터리>/): junit.xml(run_sitl.sh가 --junitxml로 지정), trace.jsonl, verdict.json,
raw_status_A.jsonl, armed_a.json. verdict.json의 구조는 tests/support/sitl_summary.py가 읽는다.
이 디렉터리의 테스트는 tests/support의 단위 테스트(lint job의 pytest)가 수집하지 않는다.
"""
import json
import os
import time
from pathlib import Path

import pytest

from tests.support import sitl_summary as ss
from tests.support import sitl_wait as sw
from tests.support import stack as stk

_STATE = {"session": None, "gate_error": None, "results": {}, "t0": {}, "out": None, "rtf": None}


def _out_dir(stack):
    d = stack.dir / os.environ.get("IDSIM_SITL_OUT", "sitl")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _category(exc):
    if isinstance(exc, sw.SitlFailure):
        return exc.category
    return "ERROR"


@pytest.fixture(scope="session")
def session():
    from tests.support.sitl_session import SitlSession

    stack = stk.load_from_env()
    out = _out_dir(stack)
    _STATE["out"] = out
    s = SitlSession(stack, out)
    _STATE["session"] = s
    wall0 = time.monotonic()
    try:
        s.start()
        s.gate()
    except BaseException as e:
        _STATE["gate_error"] = {"ok": False, "category": _category(e), "message": str(e)[:500],
                                "sim_s": None, "wall_s": round(time.monotonic() - wall0, 3)}
        s.close()
        raise
    yield s
    s.close()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    marker = item.get_closest_marker("scenario")
    if marker is None:
        return
    sid = marker.args[0]
    s = _STATE["session"]
    if rep.when == "setup" and rep.passed and s is not None:
        _STATE["t0"][sid] = (s.raw.clock_us(), time.monotonic())
    if rep.when == "call" or (rep.when == "setup" and not rep.passed):
        exc = call.excinfo.value if call.excinfo else None
        sim_s = wall_s = None
        if s is not None and sid in _STATE["t0"]:
            c0, w0 = _STATE["t0"][sid]
            sim_s, wall_s = round((s.raw.clock_us() - c0) / 1e6, 3), round(time.monotonic() - w0, 3)
        ms = {}
        if s is not None and sid in s.milestones:
            # 이정표는 시나리오 A의 goal 전송을 0으로 한 ROS 시각 소요(초)로 남긴다
            base = s.milestones[sid].get("goal_sent")
            ms = {k: (None if v is None or base is None else round((v - base) / 1e6, 3))
                  for k, v in s.milestones[sid].items() if k != "goal_sent"}
        if rep.passed:
            row = ss.scenario_result(sid, "passed", sim_s=sim_s, wall_s=wall_s, milestones=ms)
        elif rep.skipped:
            row = ss.scenario_result(sid, "skipped", message=str(rep.longrepr)[:300])
        else:
            row = ss.scenario_result(sid, "failed", category=_category(exc), message=str(exc)[:500] if exc else None,
                                     sim_s=sim_s, wall_s=wall_s, milestones=ms)
        _STATE["results"][sid] = row
        if s is not None and _STATE["gate_error"] is None:
            _STATE["rtf"] = s.rtf()      # 판정 구간 RTF: 첫 gate 통과부터 마지막으로 끝난 시나리오까지


def pytest_sessionfinish(session, exitstatus):
    s = _STATE["session"]
    out = _STATE["out"]
    if out is None:
        return
    stack = stk.load_from_env()
    gate = _STATE["gate_error"] or {"ok": s is not None and bool(s.gate_info), "category": None, "message": None,
                                    **(s.gate_info if s else {})}
    verdict = {
        "schema": ss.SCHEMA, "run_id": stack.run_id, "stack_index": stack.stack_index,
        "git_commit": stack.git_commit, "git_dirty": stack.git_dirty,
        "images": {k: v for k, v in stack.images.items() if v}, "gate": gate,
        "scenarios": [_STATE["results"][i] for i in ss.SCENARIOS if i in _STATE["results"]],
        "rtf": _STATE["rtf"],
        "armed_a": getattr(s, "armed_a", None) if s is not None else None,
        "exitstatus": int(exitstatus),
    }
    verdict["passed"] = ss.run_passed(verdict) and int(exitstatus) == 0
    Path(out / "verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n", encoding="ascii")


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(id): 시나리오 이름(B, C, A, D, T). verdict.json의 행 이름")
