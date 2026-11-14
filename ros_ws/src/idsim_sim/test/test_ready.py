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
"""준비 표시 파일과 첫 발행 추적."""

import pytest

from idsim_sim.ready import ReadyTracker, remove_ready_file, write_ready_file


def test_tracker_reports_once_when_all_published():
    tr = ReadyTracker(["b", "a"])
    assert tr.record("a", 5) is None
    assert tr.record("a", 9) is None
    assert tr.record("b", 12) == [("b", 12), ("a", 5)]
    assert tr.record("b", 20) is None


def test_tracker_rejects_zero_stamp():
    with pytest.raises(ValueError):
        ReadyTracker(["a"]).record("a", 0)


def test_write_is_atomic_and_content(tmp_path):
    path = tmp_path / "idsim" / "targets_ready"
    write_ready_file([("car_1", 12_004_000_000), ("ring", 12_004_000_001)], str(path))
    assert path.read_text(encoding="ascii") == "car_1 12.004000000\nring 12.004000001\n"
    assert not (tmp_path / "idsim" / "targets_ready.tmp").exists()


def test_remove(tmp_path):
    path = tmp_path / "targets_ready"
    remove_ready_file(str(path))  # 없어도 된다
    path.write_text("x")
    remove_ready_file(str(path))
    assert not path.exists()
