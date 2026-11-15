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

"""비행 단위 상태(1b decisions.md 쟁점 5, 15). 순수 코드다(rclpy 없음).

세션 하나에 Flights 하나를 두고 비행 시나리오(A, D, F1-F4)가 순서대로 넘겨받는다(tests/sitl/conftest.py의 session
fixture가 SitlSession.flights로 준다).
- 먼저 실패한 비행 시나리오가 있으면 뒤의 비행 시나리오는 실행하지 않고 UPSTREAM_FAILED로 실패한다(실패로 센다).
- 착륙 위치 판정의 기준점(그 비행의 이륙 직전 정답 위치)을 쥔다. 지상에서 시작하는 비행이 이륙 전에 정하고,
  공중에서 시작하는 비행(F3)은 앞 비행(F2)의 기준점을 이어받는다. 앞 비행이 이 세션에서 통과하지 않았으면
  PRECONDITION이다(F3만 따로 돌릴 수 없다).
"""
from tests.support import sitl_wait as sw


class Flights:
    def __init__(self):
        self.failed = None        # (시나리오, 분류)
        self.last_passed = None   # 마지막으로 통과한 비행 시나리오
        self.ref = None           # (x, y, z) world ENU
        self.ref_sid = None       # 기준점을 정한 비행

    def check_upstream(self, sid):
        if self.failed is not None:
            raise sw.SitlFailure(sw.UPSTREAM_FAILED, "앞 비행 시나리오 %s가 실패해(%s) %s를 실행하지 않았다"
                                 % (self.failed[0], self.failed[1], sid))

    def fail(self, sid, category):
        if self.failed is None:
            self.failed = (sid, category)

    def passed(self, sid):
        self.last_passed = sid

    def set_ref(self, sid, point):
        self.ref = tuple(point)
        self.ref_sid = sid

    def inherited_ref(self, sid, prev):
        """공중 시작 비행 sid가 앞 비행 prev의 기준점을 이어받는다. prev가 바로 앞에서 통과하지 않았으면 PRECONDITION."""
        if self.last_passed != prev or self.ref_sid != prev or self.ref is None:
            raise sw.SitlFailure(sw.PRECONDITION, "%s는 %s가 남긴 공중 Hold에서 시작한다. 이 세션에서 %s가 바로 앞에 통과하지 "
                                 "않았다(마지막 통과 %s). %s만 따로 돌릴 수 없다" % (sid, prev, prev, self.last_passed, sid))
        return self.ref
