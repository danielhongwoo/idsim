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

"""ulog_min 단위 테스트. 합성 ULog 파일을 만들어 읽는다."""
import struct

import pytest

from tests.support import ulog_min


def msg(mtype, payload):
    return struct.pack("<HB", len(payload), mtype) + payload


def build(rows, truncate=0, extra_topic=True):
    fmt = "vehicle_status:uint64_t timestamp;uint8_t arming_state;uint8_t[2] pair;bool failsafe;"
    out = b"ULog\x01\x12\x35" + b"\x01" + struct.pack("<Q", 0)
    out += msg(0x42, b"\x00" * 40)
    out += msg(0x46, fmt.encode())
    if extra_topic:
        out += msg(0x46, b"other:uint64_t timestamp;float x;")
        out += msg(0x41, struct.pack("<BH", 0, 7) + b"other")
    out += msg(0x41, struct.pack("<BH", 0, 3) + b"vehicle_status")
    for ts, arm, pair, fs in rows:
        out += msg(0x44, struct.pack("<H", 3) + struct.pack("<QBBB?", ts, arm, pair[0], pair[1], fs))
        if extra_topic:
            out += msg(0x44, struct.pack("<H", 7) + struct.pack("<Qf", ts, 1.5))
    return out[:len(out) - truncate] if truncate else out


def test_reads_only_requested_topic(tmp_path):
    p = tmp_path / "a.ulg"
    p.write_bytes(build([(100, 2, (14, 14), False), (200, 1, (4, 4), True)]))
    rows = ulog_min.read_topic(str(p), "vehicle_status")
    assert [r["timestamp"] for r in rows] == [100, 200]
    assert rows[0]["arming_state"] == 2 and rows[0]["pair"] == [14, 14]
    assert rows[1]["failsafe"] is True


def test_truncated_last_message_is_dropped(tmp_path):
    p = tmp_path / "b.ulg"
    p.write_bytes(build([(100, 2, (14, 14), False), (200, 1, (4, 4), True)], truncate=5,
                        extra_topic=False))
    rows = ulog_min.read_topic(str(p), "vehicle_status")
    assert [r["timestamp"] for r in rows] == [100]


def test_bad_magic_raises(tmp_path):
    p = tmp_path / "c.ulg"
    p.write_bytes(b"not a ulog file at all")
    with pytest.raises(ulog_min.UlogError):
        ulog_min.read_topic(str(p), "vehicle_status")


def test_trailing_padding_is_not_in_file(tmp_path):
    fmt = b"t:uint64_t timestamp;uint8_t a;uint8_t[3] _padding0;"
    out = b"ULog\x01\x12\x35" + b"\x01" + struct.pack("<Q", 0) + msg(0x42, b"\x00" * 40)
    out += msg(0x46, fmt) + msg(0x41, struct.pack("<BH", 0, 1) + b"t")
    out += msg(0x44, struct.pack("<H", 1) + struct.pack("<QB", 7, 9))     # padding 3바이트 없음
    p = tmp_path / "d.ulg"
    p.write_bytes(out)
    rows = ulog_min.read_topic(str(p), "t")
    assert rows[0]["timestamp"] == 7 and rows[0]["a"] == 9


def build_multi(truncate=0):
    """토픽 둘(vehicle_status multi 0과 1, other multi 0)이 섞인 합성 ULog."""
    out = b"ULog\x01\x12\x35" + b"\x01" + struct.pack("<Q", 0) + msg(0x42, b"\x00" * 40)
    out += msg(0x46, b"vehicle_status:uint64_t timestamp;uint8_t arming_state;")
    out += msg(0x46, b"other:uint64_t timestamp;float x;")
    out += msg(0x41, struct.pack("<BH", 0, 1) + b"vehicle_status")
    out += msg(0x41, struct.pack("<BH", 1, 2) + b"vehicle_status")      # multi_id 1
    out += msg(0x41, struct.pack("<BH", 0, 3) + b"other")
    out += msg(0x44, struct.pack("<H", 1) + struct.pack("<QB", 10, 1))
    out += msg(0x44, struct.pack("<H", 2) + struct.pack("<QB", 11, 9))
    out += msg(0x44, struct.pack("<H", 3) + struct.pack("<Qf", 12, 2.5))
    out += msg(0x44, struct.pack("<H", 1) + struct.pack("<QB", 20, 2))
    out += msg(0x44, struct.pack("<H", 3) + struct.pack("<Qf", 21, 3.5))
    return out[:len(out) - truncate] if truncate else out


def test_read_topics_reads_several_topics_in_one_pass_and_filters_multi_id(tmp_path):
    p = tmp_path / "f.ulg"
    p.write_bytes(build_multi())
    got = ulog_min.read_topics(str(p), {"vehicle_status": 0, "other": 0, "absent": 0})
    assert [r["timestamp"] for r in got["vehicle_status"]] == [10, 20]       # multi_id 1(11)은 빠진다
    assert [r["x"] for r in got["other"]] == [2.5, 3.5]
    assert got["absent"] == []
    only1 = ulog_min.read_topics(str(p), {"vehicle_status": 1})
    assert [r["arming_state"] for r in only1["vehicle_status"]] == [9]


def test_read_topics_truncated_and_bad_magic(tmp_path):
    p = tmp_path / "g.ulg"
    p.write_bytes(build_multi(truncate=3))
    got = ulog_min.read_topics(str(p), {"vehicle_status": 0, "other": 0})
    assert [r["timestamp"] for r in got["other"]] == [12]                    # 마지막 other 표본은 잘렸다
    assert [r["timestamp"] for r in got["vehicle_status"]] == [10, 20]
    bad = tmp_path / "h.ulg"
    bad.write_bytes(b"nope" * 10)
    with pytest.raises(ulog_min.UlogError):
        ulog_min.read_topics(str(bad), {"vehicle_status": 0})


def test_read_topic_equals_read_topics_single(tmp_path):
    p = tmp_path / "i.ulg"
    p.write_bytes(build_multi())
    assert ulog_min.read_topic(str(p), "other") == ulog_min.read_topics(str(p), {"other": 0})["other"]
