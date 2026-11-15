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

"""sitl_flight.Flights와 sim_truth.qos_contract_findings 단위 테스트."""
import pytest

from tests.support import sitl_wait as sw
from tests.support.sim_truth import qos_contract_findings
from tests.support.sitl_flight import Flights


def test_upstream_failed_after_first_flight_failure():
    f = Flights()
    f.check_upstream("A")
    f.fail("A", sw.WRONG_RESULT)
    f.fail("D", sw.UPSTREAM_FAILED)               # 먼저 실패한 것만 남는다
    with pytest.raises(sw.SitlFailure) as e:
        f.check_upstream("F1")
    assert e.value.category == sw.UPSTREAM_FAILED and "A" in e.value.message


def test_air_start_inherits_ref_only_right_after_prev():
    f = Flights()
    f.set_ref("F2", (6.0, 7.0, 0.23))
    f.passed("F2")
    assert f.inherited_ref("F3", "F2") == (6.0, 7.0, 0.23)
    g = Flights()
    with pytest.raises(sw.SitlFailure) as e:
        g.inherited_ref("F3", "F2")               # F3만 따로 돌린 경우
    assert e.value.category == sw.PRECONDITION
    f.set_ref("F4", (6.0, 7.0, 0.23))
    with pytest.raises(sw.SitlFailure):
        f.inherited_ref("F3", "F2")


def test_qos_contract_findings():
    assert qos_contract_findings([("targets", "RELIABLE", "VOLATILE")]) == []
    assert qos_contract_findings([("targets", "BEST_EFFORT", "VOLATILE"), ("x", "RELIABLE", "TRANSIENT_LOCAL")]) == [
        "targets: BEST_EFFORT, VOLATILE", "x: RELIABLE, TRANSIENT_LOCAL"]
