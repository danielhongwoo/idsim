#!/usr/bin/env python3
"""스모크 골든과 원시 산출물에서 docs/interface.md 용 PX4 토픽 표를 만든다.

입력
  골든 디렉터리 (tests/fixtures/px4/<PX4_TAG>/, docs/smoke-test-phase1a.md 형식)
    topics.txt          한 줄에 "<상대 토픽> <타입>"
    qos/<상대 토픽>.txt  reliability, durability, history, depth 네 줄(발행자 값)
    env.txt             PX4_TAG, PX4_MSGS_REF, RMW_IMPLEMENTATION, XRCE_AGENT_TAG
  원시 산출물 디렉터리 (tests/smoke/capture.sh 의 OUT_DIR)
    hz/<상대 토픽>.txt   ros2 topic hz --wall-time 원문
    env_raw.txt         측정 조건(KEY=VALUE)

출력
  stdout 으로 마크다운. docs/interface.md 초안에 붙여 넣는다.
  측정 주기는 계약이 아니라 참고값이며 측정 조건을 함께 적는다.

사용법
  tools/to_interface.py --artifacts artifacts/runs/<run_id>/smoke/ros [--golden DIR]
  (<run_id>는 run_smoke.sh S4 실행의 id, 예: 20261110-003348-k0-s4)
  --golden 을 주지 않으면 docker/versions.env 의 PX4_TAG 로 경로를 계산한다.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_ENV_KEYS = ("PX4_TAG", "PX4_MSGS_REF", "RMW_IMPLEMENTATION", "XRCE_AGENT_TAG")
QOS_KEYS = ("reliability", "durability", "history", "depth")

TOPIC_RE = re.compile(r"^fmu/(in|out)/[a-z0-9_]+$")
TYPE_RE = re.compile(r"^px4_msgs/msg/[A-Za-z0-9]+$")
# ros2 topic hz 출력: "average rate: 50.000" 다음 줄 "\tmin: 0.019s max: 0.021s std dev: 0.00050s window: 51"
RATE_RE = re.compile(r"^average rate:\s*([0-9.]+)\s*$")
STATS_RE = re.compile(
    r"^\s*min:\s*([0-9.]+)s\s+max:\s*([0-9.]+)s\s+std dev:\s*([0-9.]+)s\s+window:\s*(\d+)\s*$"
)


class InputError(Exception):
    """입력 파일이 없거나 형식이 틀렸다."""


@dataclass
class HzResult:
    rate_hz: float
    min_s: float | None
    max_s: float | None
    window: int | None


def read_kv(path: Path) -> dict[str, str]:
    """KEY=VALUE, "KEY: VALUE", "KEY VALUE" 줄을 읽는다. 빈 줄, # 주석, 줄 끝 " #" 주석은 무시."""
    if not path.is_file():
        raise InputError(f"파일이 없다: {path}")
    out: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = re.sub(r"\s+#.*$", "", raw).strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:|\s)\s*(.*)$", line)
        if not m:
            raise InputError(f"{path}:{lineno}: KEY=VALUE 형식이 아니다: {raw!r}")
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[m.group(1)] = value
    return out


def golden_dir_from_versions() -> Path:
    versions = REPO_ROOT / "docker" / "versions.env"
    tag = read_kv(versions).get("PX4_TAG", "")
    if not tag:
        raise InputError(f"{versions} 에 PX4_TAG 가 없다")
    return REPO_ROOT / "tests" / "fixtures" / "px4" / tag


def read_topics(golden: Path) -> list[tuple[str, str]]:
    path = golden / "topics.txt"
    if not path.is_file():
        raise InputError(f"골든 topics.txt 가 없다: {path}")
    topics: list[tuple[str, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        parts = raw.split()
        if len(parts) != 2 or not TOPIC_RE.match(parts[0]) or not TYPE_RE.match(parts[1]):
            raise InputError(
                f"{path}:{lineno}: '<fmu/(in|out)/이름> px4_msgs/msg/<Type>' 형식이 아니다: {raw!r}"
            )
        topics.append((parts[0], parts[1]))
    if not topics:
        raise InputError(f"골든 topics.txt 가 비어 있다: {path}")
    return topics


def read_qos(golden: Path, rel: str) -> dict[str, str] | None:
    path = golden / "qos" / f"{rel}.txt"
    if not path.is_file():
        return None
    kv = {k.lower(): v for k, v in read_kv(path).items()}
    missing = [k for k in QOS_KEYS if k not in kv]
    if missing:
        raise InputError(f"{path}: 키가 없다: {', '.join(missing)}")
    return kv


def read_hz(artifacts: Path, rel: str) -> HzResult | None | str:
    """측정 파일이 없으면 None, 있는데 수신이 없으면 "none", 있으면 마지막 보고값."""
    path = artifacts / "hz" / f"{rel}.txt"
    if not path.is_file():
        return None
    result: HzResult | None = None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        m = RATE_RE.match(line)
        if not m:
            continue
        min_s = max_s = None
        window = None
        if i + 1 < len(lines):
            s = STATS_RE.match(lines[i + 1])
            if s:
                min_s, max_s, window = float(s.group(1)), float(s.group(2)), int(s.group(4))
        result = HzResult(float(m.group(1)), min_s, max_s, window)
    return result if result is not None else "none"


def fmt_qos(qos: dict[str, str] | None) -> str:
    if qos is None:
        return "-"
    return f"{qos['reliability']}, {qos['durability']}, {qos['history']}({qos['depth']})"


def fmt_hz(hz: HzResult | None | str) -> str:
    if hz is None:
        return "-"
    if hz == "none":
        return "수신 없음"
    assert isinstance(hz, HzResult)
    text = f"{hz.rate_hz:.1f} Hz"
    if hz.min_s is not None and hz.max_s is not None and hz.window is not None:
        text += f" (간격 {hz.min_s * 1000:.0f}-{hz.max_s * 1000:.0f} ms, n={hz.window})"
    return text


def direction(rel: str) -> str:
    return "PX4 -> ROS 2" if rel.startswith("fmu/out/") else "ROS 2 -> PX4"


def render(golden: Path, artifacts: Path) -> str:
    if not golden.is_dir():
        raise InputError(f"골든 디렉터리가 없다: {golden}")
    if not artifacts.is_dir():
        raise InputError(f"원시 산출물 디렉터리가 없다: {artifacts}")
    if not (artifacts / "hz").is_dir():
        raise InputError(f"hz 측정 디렉터리가 없다: {artifacts / 'hz'}")

    env = read_kv(golden / "env.txt")
    missing = [k for k in GOLDEN_ENV_KEYS if not env.get(k)]
    if missing:
        raise InputError(f"{golden / 'env.txt'}: 키가 없다: {', '.join(missing)}")
    cond = read_kv(artifacts / "env_raw.txt")
    for key in GOLDEN_ENV_KEYS:
        if cond.get(key) and cond[key] != env[key]:
            raise InputError(
                f"골든과 원시 산출물의 {key} 가 다르다: 골든={env[key]} 원시={cond[key]}"
            )

    topics = read_topics(golden)
    known = {rel for rel, _ in topics}
    hz_dir = artifacts / "hz"
    for path in sorted(hz_dir.rglob("*.txt")):
        rel = path.relative_to(hz_dir).as_posix()[: -len(".txt")]
        if rel not in known:
            print(f"to_interface.py: 경고: 골든에 없는 hz 토픽 {rel}", file=sys.stderr)

    rows = []
    for rel, typ in topics:
        qos = read_qos(golden, rel)
        if qos is None and rel.startswith("fmu/out/"):
            raise InputError(f"발행자 QoS 골든이 없다: {golden / 'qos' / (rel + '.txt')}")
        rows.append(
            f"| `{rel}` | {direction(rel)} | `{typ}` | {fmt_qos(qos)} | {fmt_hz(read_hz(artifacts, rel))} |"
        )

    ns = cond.get("CAPTURE_NS", "")
    speed = cond.get("PX4_SIM_SPEED_FACTOR", "1")
    seconds = cond.get("HZ_SECONDS", "?")
    time_base = "벽시계" if cond.get("HZ_TIME_BASE", "wall") == "wall" else cond["HZ_TIME_BASE"]
    hz_qos = cond.get("HZ_QOS", "sensor_data")

    out = [
        f"## PX4 토픽 ({env['PX4_TAG']})",
        "",
        f"- PX4 `{env['PX4_TAG']}`, px4_msgs `{env['PX4_MSGS_REF']}`, "
        f"uXRCE-DDS Agent `{env['XRCE_AGENT_TAG']}`, rmw `{env['RMW_IMPLEMENTATION']}`",
        "- 토픽 이름은 네임스페이스를 뗀 상대 이름이다. 실제 이름은 `/px4_<N>/` 접두사가 붙는다.",
        "- 이름의 `_v<N>` 접미사는 태그마다 바뀔 수 있다. 노드는 이 표의 이름을 쓰지 않고 `idsim_common` 매핑으로만 얻는다.",
        "- QoS 열은 reliability, durability, history(depth) 순이다. out 토픽은 에이전트 발행자 값이고, in 토픽은 골든에 값이 있을 때만 적는다.",
        "",
        "| 토픽 | 방향 | 타입 | 발행자 QoS | 측정 주기 (참고값) |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
        "측정 주기는 계약이 아니라 참고값이다. 측정 조건: "
        f"PX4 `{env['PX4_TAG']}`, 네임스페이스 `{ns or '없음'}`, "
        f"`ros2 topic hz --wall-time` {seconds}초({time_base}), 구독 QoS `{hz_qos}`, "
        f"`PX4_SIM_SPEED_FACTOR={speed}`, 여러 토픽 병렬 측정. "
        "\"-\" 는 측정하지 않은 토픽이다.",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--golden", type=Path, help="골든 디렉터리 (기본: versions.env 의 PX4_TAG)")
    parser.add_argument("--artifacts", type=Path, required=True, help="capture.sh 의 출력 디렉터리")
    args = parser.parse_args(argv)
    try:
        golden = args.golden if args.golden is not None else golden_dir_from_versions()
        sys.stdout.write(render(golden, args.artifacts))
    except InputError as exc:
        print(f"to_interface.py: 오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
