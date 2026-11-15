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

"""시나리오 B 사례 표의 모양을 고정한다. 계약 검증을 다시 구현하지 않고, 사례가 어기는 규칙 하나 밖의 항목이
필드 값으로 거부되지 않을 모양인지만 본다(사례가 의도한 규칙에서 INVALID_MISSION을 받게 하려는 것)."""
import math
import re

from tests.support import sitl_judge as sj
from tests.support import sitl_missions as sm

MISSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")     # docs/interface.md mission_id
TARGET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")          # docs/interface.md target_id


def _fields_ok(it):
    """항목의 필드가 계약 범위 안인가(서브메시지를 기본값으로 둔 항목은 False)."""
    if it.get("default_sub") or not it["timeout_s"] > 0:
        return False
    t = it["type"]
    if t == sj.TYPE_TAKEOFF:
        return it["height_m"] > 0 and it["acceptance_m"] > 0
    if t == sj.TYPE_LOITER:
        return 0 < it["duration_s"] < it["timeout_s"]
    if t == sj.TYPE_GOTO:
        return all(math.isfinite(v) and abs(v) <= 1e5 for v in it["position"]) and it["acceptance_m"] > 0
    if t == sj.TYPE_TRACK_ENTITY:
        return (TARGET_ID_RE.match(it["target_id"]) is not None and it["acceptance_m"] > 0
                and any(v != 0.0 for v in it["offset"]))
    return t in (sj.TYPE_RTL, sj.TYPE_LAND)


def _case(mission_id):
    return next(items for mid, _, _, items in sm.B_INVALID_CASES if mid == mission_id)


def test_mission_ids_are_valid_and_unique():
    ids = [mid for mid, _, _, _ in sm.B_INVALID_CASES]
    assert len(ids) == len(set(ids))
    assert all(MISSION_ID_RE.match(mid) for mid in ids)


def test_every_case_has_a_detail_fragment():
    assert all(isinstance(d, str) and d for _, _, d, _ in sm.B_INVALID_CASES)


def test_bad_target_id_fragment_names_the_id():
    assert ("'%s'" % sm.BAD_TARGET_ID) in next(d for mid, _, d, _ in sm.B_INVALID_CASES
                                               if mid == "b-track-bad-target-id")


def test_order_cases_have_only_well_formed_items():
    for mid in ("b-takeoff-not-first", "b-land-goto", "b-rtl-not-last", "b-rtl-first"):
        assert all(_fields_ok(it) for it in _case(mid)), mid


def test_order_cases_break_their_rule():
    types = {mid: [it["type"] for it in items] for mid, _, _, items in sm.B_INVALID_CASES}
    assert sj.TYPE_TAKEOFF in types["b-takeoff-not-first"][1:]
    assert types["b-land-goto"][0] == sj.TYPE_LAND and len(types["b-land-goto"]) > 1
    rtl_mid = types["b-rtl-not-last"]
    assert sj.TYPE_RTL in rtl_mid[1:-1]
    assert types["b-rtl-first"][0] == sj.TYPE_RTL and len(types["b-rtl-first"]) > 1


def test_field_cases_break_only_the_track_item():
    for mid in ("b-track-zero-offset", "b-track-bad-target-id", "b-track-default"):
        items = _case(mid)
        assert items[0]["type"] == sj.TYPE_TAKEOFF and _fields_ok(items[0])
        assert [it["type"] for it in items[1:]] == [sj.TYPE_TRACK_ENTITY]
        assert not _fields_ok(items[1])
    zero = _case("b-track-zero-offset")[1]
    assert zero["offset"] == (0.0, 0.0, 0.0)
    assert TARGET_ID_RE.match(zero["target_id"]) and zero["acceptance_m"] > 0
    assert _case("b-track-default")[1].get("default_sub") is True
    bad = _case("b-track-bad-target-id")[1]
    assert TARGET_ID_RE.match(bad["target_id"]) is None
    assert any(v != 0.0 for v in bad["offset"]) and bad["acceptance_m"] > 0


def test_empty_case_has_no_items():
    assert _case("b-empty") == []


def test_track_target_id_has_valid_format():
    assert TARGET_ID_RE.match(sm.TRACK_TARGET_ID)
