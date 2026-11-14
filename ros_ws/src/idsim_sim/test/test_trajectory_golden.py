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
"""궤적 평가를 손 계산 golden 표(golden/trajectory_eval.csv)와 비교하고, stamp 규칙을 사례 표로 본다.

golden은 평가 함수로 만들지 않았다. 이 테스트도 기대값을 계산하지 않고 표의 값과만 비교한다.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from idsim_sim.trajectory import StampDecision, Trajectory, evaluate, stamp_decision

GOLDEN = Path(__file__).parent / "golden" / "trajectory_eval.csv"
TOL = 1e-9


def _load():
    trajs, rows = {}, []
    for lineno, line in enumerate(GOLDEN.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split(",")
        if cols[0] == "traj":
            _, name, start_s, loop, wps = cols
            pts = [[float(v) for v in wp.split()] for wp in wps.split(";")]
            trajs[name] = Trajectory.from_seconds(
                name, float(start_s), {"true": True, "false": False}[loop],
                [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], [p[3] for p in pts])
        elif cols[0] == "eval":
            _, name, t_s, *vals, note = cols
            t_ns = int(Decimal(t_s) * 1_000_000_000)
            rows.append(pytest.param(name, t_ns, [float(v) for v in vals], id=f"{lineno}-{name}-{t_s}"))
        else:
            raise AssertionError(f"{GOLDEN}:{lineno}: 모르는 줄 종류 {cols[0]!r}")
    return trajs, rows


TRAJS, ROWS = _load()


def test_golden_covers_required_cases():
    """완료 기준의 사례(시작 전, waypoint 정확히, loop 양쪽, 끝난 뒤 정지, 정지 구간)가 표에 있다."""
    assert {t.loop for t in TRAJS.values()} == {True, False}
    assert any(t.start_ns > 0 for t in TRAJS.values())
    assert len(ROWS) >= 20


@pytest.mark.parametrize("name, t_ns, want", ROWS)
def test_evaluate_matches_golden(name, t_ns, want):
    sample = evaluate(TRAJS[name], t_ns)
    got = list(sample.position) + list(sample.velocity)
    assert got == pytest.approx(want, abs=TOL)


# (직전 stamp, 지금, 기대). 직전 stamp보다 큰 t에서만 발행, 0은 내지 않음, 역행은 따로 구분
STAMP_CASES = [
    (None, 0, StampDecision.SKIP_ZERO),
    (None, 1, StampDecision.PUBLISH),
    (None, 4_000_000, StampDecision.PUBLISH),
    (4_000_000, 8_000_000, StampDecision.PUBLISH),
    (4_000_000, 4_000_001, StampDecision.PUBLISH),
    (4_000_000, 4_000_000, StampDecision.SKIP_SAME),
    (4_000_000, 3_999_999, StampDecision.SKIP_BACKWARD),
    (4_000_000, 0, StampDecision.SKIP_BACKWARD),
]


@pytest.mark.parametrize("prev_ns, now_ns, want", STAMP_CASES)
def test_stamp_decision(prev_ns, now_ns, want):
    assert stamp_decision(prev_ns, now_ns) is want


@pytest.mark.parametrize("t", [[0.0], [0.0, 0.0], [0.5, 1.0], [0.0, 2.0, 1.0]])
def test_trajectory_rejects_bad_times(t):
    with pytest.raises(ValueError):
        Trajectory.from_seconds("a", 0.0, False, t, [0.0] * len(t), [0.0] * len(t), [0.0] * len(t))


def test_module_does_not_import_rclpy():
    import subprocess
    import sys

    code = "import sys, idsim_sim.trajectory, idsim_sim.params, idsim_sim.ready; print('rclpy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "False"
