"""골든 파일 정규화, 읽기/쓰기, 비교. rclpy에 의존하지 않는다.

형식은 docs/smoke-test.md의 "산출물 위치와 골든 파일 형식" 절을 따른다.
"""
import os
import re

QOS_KEYS = ("reliability", "durability", "history", "depth")
ENV_KEYS = ("PX4_TAG", "PX4_MSGS_REF", "RMW_IMPLEMENTATION", "XRCE_AGENT_TAG")

_LIST_LINE = re.compile(r"^\s*(\S+)\s+\[([^\]\s]+)(?:,[^\]]*)?\]\s*$")
_SUFFIX = re.compile(r"_v\d+$")


def _strip_ns(topic, namespace):
    topic = topic.lstrip("/")
    ns = (namespace or "").strip("/")
    if ns:
        prefix = ns + "/"
        if not topic.startswith(prefix):
            return None
        topic = topic[len(prefix):]
    return topic


def normalize_topic_list(raw_text, namespace):
    """`ros2 topic list -t` 원문을 골든 topics.txt의 줄 목록으로 바꾼다.

    namespace 접두사를 떼고 fmu/ 아래만 남기며 "상대토픽 타입" 형태로 만든다.
    namespace가 비어 있지 않은데 접두사가 다른 토픽은 버린다.
    정렬은 LC_ALL=C sort와 같은 바이트 순서이고 중복은 제거한다.
    """
    out = set()
    for line in raw_text.splitlines():
        m = _LIST_LINE.match(line)
        if not m:
            continue
        rel = _strip_ns(m.group(1), namespace)
        if rel is None or not rel.startswith("fmu/"):
            continue
        out.add("%s %s" % (rel, m.group(2)))
    return sorted(out, key=lambda s: s.encode("ascii"))


def normalize_qos(raw_info_v_text):
    """`ros2 topic info -v` 원문에서 발행자 QoS 네 항목만 뽑는다.

    첫 번째 PUBLISHER 구간을 쓴다. 발행자가 없으면 ValueError.
    반환 값은 모두 문자열이다. depth는 정수 문자열이거나, 출력에 없으면 "UNKNOWN".
    """
    in_pub = False
    in_qos = False
    found = {}
    for line in raw_info_v_text.splitlines():
        s = line.strip()
        if s.startswith("Node name:"):
            if found and in_pub:
                break
            in_pub = False
            in_qos = False
        elif s.startswith("Endpoint type:"):
            in_pub = s.split(":", 1)[1].strip() == "PUBLISHER"
            in_qos = False
        elif in_pub and s.startswith("QoS profile:"):
            in_qos = True
        elif in_pub and in_qos and ":" in s:
            key, val = [p.strip() for p in s.split(":", 1)]
            if key == "Reliability":
                found["reliability"] = val
            elif key == "Durability":
                found["durability"] = val
            elif key.startswith("History"):
                m = re.match(r"^(\w+)(?:\s*\((\d+)\))?$", val)
                if key == "History (Depth)":
                    # Jazzy: "History (Depth): KEEP_LAST (5)" 또는 "UNKNOWN"
                    found["history"] = m.group(1) if m else val
                    found["depth"] = m.group(2) if m and m.group(2) else "UNKNOWN"
                else:
                    found["history"] = val
            elif key == "Depth":
                found["depth"] = val
    if not found:
        raise ValueError("발행자 QoS 구간을 찾지 못했다")
    missing = [k for k in ("reliability", "durability", "history") if k not in found]
    if missing:
        raise ValueError("QoS 항목 없음: %s" % ",".join(missing))
    found.setdefault("depth", "UNKNOWN")
    return {k: found[k] for k in QOS_KEYS}


def _qos_path(base, topic):
    return os.path.join(base, "qos", topic + ".txt")


def write_golden(dir, topics, qos_by_topic, env):
    """골든 디렉터리를 만든다. topics는 normalize_topic_list의 결과 줄 목록."""
    for k in ENV_KEYS:
        if k not in env:
            raise ValueError("env에 %s 없음" % k)
    os.makedirs(dir, exist_ok=True)
    lines = sorted(set(topics), key=lambda s: s.encode("ascii"))
    with open(os.path.join(dir, "topics.txt"), "w", newline="\n") as f:
        f.write("".join(l + "\n" for l in lines))
    for topic, qos in qos_by_topic.items():
        path = _qos_path(dir, topic)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="\n") as f:
            f.write("".join("%s=%s\n" % (k, qos[k]) for k in QOS_KEYS))
    with open(os.path.join(dir, "env.txt"), "w", newline="\n") as f:
        f.write("".join("%s=%s\n" % (k, env[k]) for k in ENV_KEYS))


def read_golden(dir):
    """(topics, qos_by_topic, env)를 돌려준다. 파일이 없으면 FileNotFoundError."""
    with open(os.path.join(dir, "topics.txt")) as f:
        topics = [l for l in f.read().splitlines() if l]
    qos_by_topic = {}
    qroot = os.path.join(dir, "qos")
    for root, _, files in os.walk(qroot):
        for name in files:
            if not name.endswith(".txt"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, qroot)[:-4].replace(os.sep, "/")
            qos_by_topic[rel] = _read_kv(full)
    return topics, qos_by_topic, _read_kv(os.path.join(dir, "env.txt"))


def _read_kv(path):
    d = {}
    with open(path) as f:
        for line in f.read().splitlines():
            if line:
                k, _, v = line.partition("=")
                d[k] = v
    return d


def read_versions_env(versions_env_path):
    d = {}
    with open(versions_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def golden_dir(repo_root, versions_env_path):
    """versions.env의 PX4_TAG로 tests/fixtures/px4/<tag>/ 경로를 계산한다."""
    tag = read_versions_env(versions_env_path).get("PX4_TAG")
    if not tag:
        raise ValueError("%s에 PX4_TAG 없음" % versions_env_path)
    return os.path.join(repo_root, "tests", "fixtures", "px4", tag)


def _base_name(name):
    return _SUFFIX.sub("", name)


def compare_subset(expected_pairs, golden_pairs):
    """expected_pairs가 golden_pairs의 부분집합인지 본다.

    각 인자는 (상대토픽, 타입) 쌍의 반복 가능 객체.
    반환: (missing, candidates). missing은 golden에 없는 쌍의 정렬된 목록.
    candidates는 {없는 쌍: [접미사를 뗀 기본 이름과 타입이 같은 golden 쌍]}.
    타입이 달라도 이름이 같으면 후보에 넣는다(타입 변경 확인용).
    """
    golden = {tuple(p) for p in golden_pairs}
    missing = sorted({tuple(p) for p in expected_pairs} - golden)
    candidates = {}
    for pair in missing:
        base = _base_name(pair[0])
        candidates[pair] = sorted(g for g in golden if _base_name(g[0]) == base)
    return missing, candidates


def parse_pairs(lines):
    """topics.txt 줄 목록을 (토픽, 타입) 쌍 목록으로 바꾼다."""
    return [tuple(l.split(None, 1)) for l in lines if l.strip()]
