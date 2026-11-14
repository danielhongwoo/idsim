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
"""준비 표시 파일. rclpy를 import하지 않는다.

healthcheck는 `test -f /tmp/idsim/targets_ready`다(decisions.md 쟁점 3). 노드는 시작 때 파일을 지우고,
모든 표적이 stamp > 0으로 한 번 이상 발행된 순간 임시 파일에 쓴 뒤 rename으로 원자적으로 만든다.
내용은 표적마다 한 줄 "<target_id> <첫 stamp 초>.<ns 9자리>"이고 target_ids 순서다.
정답 pose 노드(scripts/sim_oracle.py)도 같은 함수로 /tmp/idsim/oracle_ready를 만든다(id 자리에 vehicle_id).
"""

import os

READY_PATH = "/tmp/idsim/targets_ready"


def remove_ready_file(path=READY_PATH):
    """있으면 지운다."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def format_stamp(stamp_ns):
    sec, nsec = divmod(stamp_ns, 1_000_000_000)
    return f"{sec}.{nsec:09d}"


def write_ready_file(first_stamps, path=READY_PATH):
    """first_stamps: [(target_id, 첫 stamp ns), ...]. 임시 파일 + rename."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="ascii") as f:
        for tid, stamp_ns in first_stamps:
            f.write(f"{tid} {format_stamp(stamp_ns)}\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class ReadyTracker:
    """표적별 첫 발행 stamp를 모아 모두 모인 순간을 한 번 알린다."""

    def __init__(self, target_ids):
        self._order = list(target_ids)
        self._first = {}
        self._done = False

    def record(self, target_id, stamp_ns):
        """발행 하나를 기록한다. 모든 표적이 처음 모인 호출에서만 [(id, 첫 stamp), ...]를, 아니면 None."""
        if stamp_ns <= 0:
            raise ValueError("stamp는 0보다 커야 한다")
        self._first.setdefault(target_id, stamp_ns)
        if self._done or len(self._first) < len(self._order):
            return None
        self._done = True
        return [(tid, self._first[tid]) for tid in self._order]
