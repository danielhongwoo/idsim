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

"""ULog에서 고른 토픽의 표본만 읽는 최소 parser. 표준 라이브러리만 쓴다.

호스트와 ros-ws, px4 이미지에 pyulog가 없어서 둔다. 읽는 것: header, F(형식), A(구독), D(데이터).
나머지 메시지는 건너뛴다. 파일이 닫히지 않아 마지막 메시지가 잘려 있으면 거기서 멈추고 그때까지
읽은 표본을 돌려준다. flag bit의 "추가 데이터 첨부"(append) 구간은 읽지 않는다.

ULog 형식: https://docs.px4.io/main/en/dev_log/ulog_file_format
"""
import struct

_MAGIC = b"ULog\x01\x12\x35"
_SCALARS = {
    "int8_t": "b", "uint8_t": "B", "int16_t": "h", "uint16_t": "H", "int32_t": "i",
    "uint32_t": "I", "int64_t": "q", "uint64_t": "Q", "float": "f", "double": "d",
    "bool": "?", "char": "c",
}


class UlogError(Exception):
    pass


def _parse_format(payload):
    name, _, body = payload.decode("ascii", "replace").partition(":")
    fields = []
    for item in body.split(";"):
        if not item:
            continue
        ftype, _, fname = item.partition(" ")
        count = 1
        if "[" in ftype:
            ftype, _, rest = ftype.partition("[")
            count = int(rest.rstrip("]"))
        fields.append((ftype, count, fname))
    return name, fields


def _size(formats, name):
    total = 0
    for ftype, count, _ in formats[name]:
        total += count * (struct.calcsize(_SCALARS[ftype]) if ftype in _SCALARS
                          else _size(formats, ftype))
    return total


def _decode(formats, name, data, off=0):
    """name 형식 하나를 풀어 (dict, 다음 offset)을 돌려준다. 배열은 목록, char 배열은 bytes."""
    out = {}
    for ftype, count, fname in formats[name]:
        if ftype in _SCALARS:
            code = _SCALARS[ftype]
            if ftype == "char":
                out[fname] = data[off:off + count]
                off += count
                continue
            vals = struct.unpack_from("<%d%s" % (count, code), data, off)
            off += struct.calcsize(code) * count
            out[fname] = vals[0] if count == 1 else list(vals)
        else:
            items = []
            for _ in range(count):
                item, off = _decode(formats, ftype, data, off)
                items.append(item)
            out[fname] = items[0] if count == 1 else items
    return out, off


def read_topics(path, wanted):
    """path의 ULog를 한 번 훑어 wanted({토픽: multi_id})의 표본을 {토픽: dict 목록}으로 읽는다.

    파일이 커서(수백 MB) 토픽마다 다시 읽지 않으려고 둔다. 구독이 없는 토픽은 빈 목록이다.
    """
    with open(path, "rb") as fh:
        buf = fh.read()
    if buf[:7] != _MAGIC:
        raise UlogError("ULog header가 아니다: %s" % path)
    pos = 16
    formats = {}
    msg_ids = {}          # msg_id -> 토픽 이름
    rows = {t: [] for t in wanted}
    sizes = {}            # 토픽 -> (전체 크기, padding을 뺀 최소 크기)
    while pos + 3 <= len(buf):
        size, mtype = struct.unpack_from("<HB", buf, pos)
        start = pos + 3
        if start + size > len(buf):
            break        # 잘린 마지막 메시지
        payload = buf[start:start + size]
        pos = start + size
        if mtype == 0x46:      # 'F'
            name, fields = _parse_format(payload)
            formats[name] = fields
        elif mtype == 0x41:    # 'A'
            mid, msg_id = struct.unpack_from("<BH", payload, 0)
            name = payload[3:].decode("ascii", "replace")
            if wanted.get(name) == mid:
                msg_ids[msg_id] = name
        elif mtype == 0x44:    # 'D'
            (msg_id,) = struct.unpack_from("<H", payload, 0)
            topic = msg_ids.get(msg_id)
            if topic is None:
                continue
            if topic not in formats:
                raise UlogError("형식 정의가 없다: %s" % topic)
            if topic not in sizes:
                full = _size(formats, topic)
                pad = formats[topic][-1] if formats[topic][-1][2].startswith("_padding") else None
                sizes[topic] = (full, full - (pad[1] if pad else 0))
            full, min_len = sizes[topic]
            # 끝의 _padding 필드는 파일에 기록되지 않는다. 0으로 채워 풀고 그보다 모자라면 건너뛴다.
            data = payload[2:]
            if len(data) < min_len:
                continue
            rows[topic].append(_decode(formats, topic, data.ljust(full, b"\0"))[0])
    return rows


def read_topic(path, topic, multi_id=0):
    """path의 ULog에서 topic(multi_id) 표본을 dict 목록으로 읽는다."""
    return read_topics(path, {topic: multi_id})[topic]
