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

"""SITL 실행 기록(trace.jsonl). 한 줄이 JSON 하나다. 순수 코드(rclpy 없음)."""
import json
import time


class Trace:
    """줄마다 sim 시각(us), 벽시계 경과(s), 종류, 필드를 남긴다. 파일은 줄마다 flush한다."""

    def __init__(self, path, sim_us, wall=time.monotonic):
        self._fh = open(path, "a", encoding="ascii")
        self._sim_us = sim_us
        self._wall = wall
        self._w0 = wall()

    def event(self, kind, **fields):
        rec = {"sim_us": int(self._sim_us()), "wall_s": round(self._wall() - self._w0, 3), "kind": kind}
        rec.update(fields)
        self._fh.write(json.dumps(rec, ensure_ascii=True, sort_keys=True) + "\n")
        self._fh.flush()

    def close(self):
        if not self._fh.closed:
            self._fh.close()
