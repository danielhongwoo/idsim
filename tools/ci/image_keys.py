#!/usr/bin/env python3
"""이미지 5종의 캐시 키를 계산한다. CI(build 잡)와 로컬에서 같은 결과를 낸다.

키는 이미지마다 다음을 순서대로 이어 붙인 텍스트의 SHA-256 앞 16자리다.
  1. 키 방식 이름 (SCHEME). 계산 방식을 바꾸면 이 값을 올려 모든 키를 바꾼다.
  2. 그 이미지 Dockerfile의 바이트 해시
  3. docker/docker-bake.hcl에서 그 이미지 target 블록과 상속하는 블록(_common)의 텍스트 해시
  4. Dockerfile이 COPY/ADD로 빌드 컨텍스트(docker/)에서 가져오는 파일의 해시
  5. docker/versions.env 중 그 Dockerfile이 ARG로 선언한 이름의 줄 (NAME=값)
  6. 베이스 이미지의 키 (bake contexts의 "target:<이름>"에서 읽는다)
베이스 키가 5번 전에 6번으로 들어가므로 ros-base가 바뀌면 sim-base, px4, ros-ws 키가 모두 바뀐다.
xrce-agent는 베이스 target이 없어 독립이다.

키에 들어가지 않는 것: UBUNTU_APT_MIRROR, UBUNTU_APT_SECURITY_MIRROR(KEY_EXCLUDED_ARGS).
키에 들어가지 않는 것(빌드 시점 외부 상태): apt 저장소의 패키지 버전, pip 인덱스, 브랜치 이름으로
받는 소스. 이것들이 바뀌어도 키는 그대로이며, 같은 키의 이미지는 레지스트리에 한 번만 올라간다.

사용법
  tools/ci/image_keys.py                  # "<이미지> <키>" 다섯 줄 (빌드 순서)
  tools/ci/image_keys.py --format env     # KEY_ROS_BASE=... (bake 변수 이름)
  tools/ci/image_keys.py --format json
  tools/ci/image_keys.py --explain px4    # 해시에 들어간 재료 출력
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field

SCHEME = "idsim-image-key-v1"
KEY_LEN = 16

# Dockerfile이 ARG로 선언해도 키에 넣지 않는 versions.env 이름. apt 미러다. ubuntu.sources가 이미지에 남아 바이트가 달라지나 런타임이 apt를 쓰지 않아 같은 이미지로 본다.
KEY_EXCLUDED_ARGS = {"UBUNTU_APT_MIRROR", "UBUNTU_APT_SECURITY_MIRROR"}

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKER_DIR = os.path.join(REPO_ROOT, "docker")
BAKE_FILE = os.path.join(DOCKER_DIR, "docker-bake.hcl")
VERSIONS_FILE = os.path.join(DOCKER_DIR, "versions.env")

# 빌드 순서의 우선순위. 의존 순서는 bake contexts에서 계산하고, 같은 단계 안에서는 이 순서를 따른다.
# px4(빌더 단계 7.7GB)를 마지막에 두어 앞 이미지들이 디스크가 넉넉할 때 끝나게 한다.
PREFERRED_ORDER = ["ros-base", "xrce-agent", "ros-ws", "sim-base", "px4"]


@dataclass
class Image:
    name: str
    dockerfile: str
    block_text: str
    inherits: list[str] = field(default_factory=list)
    # named context 이름 -> 베이스 target 이름
    base_contexts: dict[str, str] = field(default_factory=dict)
    key: str = ""
    material: list[str] = field(default_factory=list)

    @property
    def base(self) -> str | None:
        bases = sorted(set(self.base_contexts.values()))
        if len(bases) > 1:
            raise SystemExit(f"{self.name}: 베이스 target이 둘 이상이다: {bases}")
        return bases[0] if bases else None

    @property
    def env_name(self) -> str:
        return "KEY_" + re.sub(r"[^A-Z0-9]", "_", self.name.upper())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_versions(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if not m:
                raise SystemExit(f"{path}:{lineno}: NAME=값 형식이 아니다: {line}")
            out[m.group(1)] = m.group(2)
    return out


def parse_bake_blocks(text: str) -> dict[str, str]:
    """target "이름" { ... } 블록을 중괄호 깊이로 잘라 이름 -> 블록 텍스트로 돌려준다."""
    blocks: dict[str, str] = {}
    for m in re.finditer(r'^target\s+"([^"]+)"\s*\{', text, re.M):
        depth = 0
        i = m.end() - 1
        in_str = False
        while i < len(text):
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 1
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            raise SystemExit(f"{BAKE_FILE}: target {m.group(1)} 블록이 닫히지 않는다")
        blocks[m.group(1)] = text[m.start():i + 1]
    return blocks


def load_images() -> dict[str, Image]:
    with open(BAKE_FILE, encoding="utf-8") as f:
        blocks = parse_bake_blocks(f.read())
    images: dict[str, Image] = {}
    for name, block in blocks.items():
        if name.startswith("_"):
            continue
        m = re.search(r'^\s*dockerfile\s*=\s*"([^"]+)"', block, re.M)
        if not m:
            raise SystemExit(f"{BAKE_FILE}: target {name}에 dockerfile이 없다")
        img = Image(name=name, dockerfile=m.group(1), block_text=block)
        m = re.search(r"^\s*inherits\s*=\s*\[([^\]]*)\]", block, re.M)
        if m:
            img.inherits = re.findall(r'"([^"]+)"', m.group(1))
        for ctx, base in re.findall(r'"([^"]+)"\s*=\s*"target:([^"]+)"', block):
            img.base_contexts[ctx] = base
        images[name] = img
    for img in images.values():
        for parent in img.inherits:
            if parent not in blocks:
                raise SystemExit(f"{img.name}: 상속 대상 {parent} 블록이 없다")
            img.block_text = blocks[parent] + "\n" + img.block_text
        if img.base and img.base not in images:
            raise SystemExit(f"{img.name}: 베이스 target {img.base}가 bake 파일에 없다")
    return images


def build_order(images: dict[str, Image]) -> list[str]:
    rank = {n: i for i, n in enumerate(PREFERRED_ORDER)}
    done: list[str] = []
    pending = sorted(images, key=lambda n: (rank.get(n, len(rank)), n))
    while pending:
        for n in pending:
            base = images[n].base
            if base is None or base in done:
                done.append(n)
                pending.remove(n)
                break
        else:
            raise SystemExit(f"베이스 순환 의존: {pending}")
    return done


def dockerfile_instructions(text: str) -> list[str]:
    """줄 이어쓰기를 합친 명령 목록. heredoc 본문은 명령으로 취급하지 않는다."""
    out: list[str] = []
    cur = ""
    heredoc_end: str | None = None
    for raw in text.splitlines():
        if heredoc_end is not None:
            if raw.strip() == heredoc_end:
                heredoc_end = None
            continue
        line = raw.rstrip()
        if not cur and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.endswith("\\"):
            cur += line[:-1] + " "
            continue
        cur += line
        m = re.search(r"<<-?['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", cur)
        if m and re.match(r"\s*(RUN|COPY|ADD)\b", cur, re.I):
            heredoc_end = m.group(1)
        out.append(cur.strip())
        cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def context_sources(dockerfile_text: str) -> list[str]:
    """빌드 컨텍스트에서 가져오는 COPY/ADD 원본 경로 목록 (--from, heredoc 제외)."""
    sources: list[str] = []
    for ins in dockerfile_instructions(dockerfile_text):
        m = re.match(r"(COPY|ADD)\s+(.*)", ins, re.I)
        if not m:
            continue
        args = m.group(2)
        if "<<" in args:
            continue
        if args.lstrip().startswith("["):
            parts = json.loads(args)
        else:
            parts = args.split()
        flags = [p for p in parts if p.startswith("--")]
        if any(f.startswith("--from=") for f in flags):
            continue
        paths = [p for p in parts if not p.startswith("--")]
        for src in paths[:-1]:
            if re.match(r"[a-z]+://", src):
                raise SystemExit(f"URL을 가져오는 {m.group(1)}는 키에 넣을 수 없다: {src}")
            sources.append(src)
    return sources


def hash_context_path(src: str) -> list[str]:
    pattern = os.path.join(DOCKER_DIR, src)
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise SystemExit(f"빌드 컨텍스트에 {src}가 없다")
    lines = []
    for path in matches:
        files = [path]
        if os.path.isdir(path):
            files = sorted(
                os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs
            )
        for fp in files:
            with open(fp, "rb") as f:
                rel = os.path.relpath(fp, DOCKER_DIR)
                lines.append(f"file {rel} sha256 {sha256_bytes(f.read())}")
    return lines


def compute(images: dict[str, Image], versions: dict[str, str]) -> list[str]:
    order = build_order(images)
    for name in order:
        img = images[name]
        with open(os.path.join(DOCKER_DIR, img.dockerfile), "rb") as f:
            df_bytes = f.read()
        df_text = df_bytes.decode("utf-8")
        args = sorted(set(re.findall(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)", df_text, re.M)))
        mat = [
            f"scheme {SCHEME}",
            f"image {name}",
            f"dockerfile {img.dockerfile} sha256 {sha256_bytes(df_bytes)}",
            f"bake sha256 {sha256_bytes(img.block_text.encode('utf-8'))}",
        ]
        for src in context_sources(df_text):
            mat.extend(hash_context_path(src))
        for a in args:
            if a in versions and a not in KEY_EXCLUDED_ARGS:
                mat.append(f"env {a}={versions[a]}")
        if img.base:
            mat.append(f"base {img.base} {images[img.base].key}")
        img.material = mat
        img.key = sha256_bytes(("\n".join(mat) + "\n").encode("utf-8"))[:KEY_LEN]
    return order


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="이미지 캐시 키 계산")
    p.add_argument("--format", choices=["table", "env", "json"], default="table")
    p.add_argument("--explain", metavar="IMAGE", help="이 이미지의 해시 재료를 출력")
    args = p.parse_args(argv)

    images = load_images()
    order = compute(images, read_versions(VERSIONS_FILE))

    if args.explain:
        if args.explain not in images:
            p.error(f"모르는 이미지: {args.explain}")
        print("\n".join(images[args.explain].material))
        print(f"key {images[args.explain].key}")
        return 0
    if args.format == "env":
        for n in order:
            print(f"{images[n].env_name}={images[n].key}")
    elif args.format == "json":
        print(json.dumps(
            [{"image": n, "key": images[n].key, "base": images[n].base,
              "base_contexts": images[n].base_contexts} for n in order],
            indent=2))
    else:
        for n in order:
            base = images[n].base or "-"
            print(f"{n:<11} {images[n].key}  base={base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
