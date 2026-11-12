#!/usr/bin/env python3
"""이미지 5종의 캐시 key를 계산한다. CI(build job)와 로컬에서 같은 결과를 낸다.

key는 이미지마다 다음을 순서대로 이어 붙인 텍스트의 SHA-256 앞 16자리다.
  1. key 방식 이름 (SCHEME). 계산 방식을 바꾸면 이 값을 올려 모든 key를 바꾼다.
  2. 이미지 이름 (image <이름>)
  3. 그 이미지 Dockerfile의 바이트 해시
  4. docker/docker-bake.hcl에서 그 이미지 target의 빌드 입력을 정규화한 텍스트 (아래 정규화 규칙).
     dockerfile, context, platforms, args, contexts만 넣는다. tags와 공백, 주석, 항목 순서는 넣지 않는다.
  5. Dockerfile이 COPY/ADD로 빌드 컨텍스트(docker/)에서 가져오는 파일의 해시
  6. docker/versions.env 중 그 Dockerfile이 ARG로 선언한 이름의 줄 (NAME=값)
  7. 베이스 이미지의 이름과 key (bake contexts의 "target:<이름>"에서 읽는다)
베이스 key가 7번으로 들어가므로 ros-base가 바뀌면 sim-base, px4, ros-ws key가 모두 바뀐다.
xrce-agent는 베이스 target이 없어 독립이다.

bake 정규화 규칙. 근거: key는 "같은 key면 같은 이미지"를 뜻해야 하므로 이미지 바이트에 영향을 주는
입력만 해시하고, 레지스트리 태그 같은 이름 붙이기와 표기 차이는 뺀다.
  - 대상: dockerfile, context, platforms, args, contexts. 부모(inherits) 값에 자식 값을 덮어 합친다.
    스칼라와 목록은 자식이 덮고, args와 contexts는 bake처럼 항목별로 합친다.
  - fail-closed: 알려진 속성(inherits, tags, 위 다섯) 밖의 속성, 보간(${...})이나 이스케이프가 든 값,
    문자열이 아닌 스칼라(context = VAR 같은 것), 중복 속성과 중복 항목은 말없이 버리지 않고 SystemExit로 멈춘다.
  - tags는 뺀다. 이미지 이름이지 내용이 아니다 (REGISTRY, KEY_* 변수도 tags에만 쓰인다).
  - 공백, 주석, 항목 순서는 뺀다. args와 contexts는 이름순으로 "이름=식" 한 줄씩 쓴다.
  - args에서 KEY_EXCLUDED_ARGS의 이름은 뺀다.
  - args의 식은 변수 이름 그대로 해시한다. 변수의 값은 6번(versions.env)이 따로 넣는다.

key에 들어가지 않는 것: UBUNTU_APT_MIRROR(KEY_EXCLUDED_ARGS).
key에 들어가지 않는 것(빌드 시점 외부 상태): apt 저장소의 패키지 버전, pip 인덱스, 태그가 가리키는
커밋. 이것들이 바뀌어도 key는 그대로이며, 같은 key의 이미지는 레지스트리에 한 번만 올라간다.

사용법
  tools/ci/image_keys.py                  # "<이미지> <key>" 다섯 줄 (빌드 순서)
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

SCHEME = "idsim-image-key-v2"
KEY_LEN = 16

# Dockerfile이 ARG로 선언해도 key에 넣지 않는 versions.env 이름. apt 미러다. ubuntu.sources가 이미지에 남아 바이트가 달라지나 런타임이 apt를 쓰지 않아 같은 이미지로 본다.
KEY_EXCLUDED_ARGS = {"UBUNTU_APT_MIRROR"}

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
    # 정규화한 bake 빌드 입력 (부모 값에 자식 값을 덮어 쓴 결과)
    bake_material: list[str] = field(default_factory=list)
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


# key에 넣는 bake 속성. tags는 이미지 내용이 아니므로 넣지 않는다.
BAKE_SCALAR_ATTRS = ("dockerfile", "context")
BAKE_LIST_ATTRS = ("platforms",)
BAKE_MAP_ATTRS = ("args", "contexts")
# 알려진 속성은 이것뿐이다. 이 밖의 속성(target, labels, secret, ...)은 이미지 바이트를 바꿀 수 있으므로
# 말없이 버리지 않고 멈춘다 (fail-closed).
BAKE_IGNORED_ATTRS = ("tags",)
BAKE_INHERITS_ATTR = "inherits"
BAKE_KNOWN_ATTRS = (
    BAKE_SCALAR_ATTRS + BAKE_LIST_ATTRS + BAKE_MAP_ATTRS + BAKE_IGNORED_ATTRS + (BAKE_INHERITS_ATTR,)
)

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
# 보간(${...}, %{...})과 이스케이프가 없는 문자열 리터럴
_PLAIN_STR = r'"(?:[^"\\$%]|\$(?!\{)|%(?!\{))*"'


def _strip_comments(body: str) -> str:
    out = []
    for line in body.splitlines():
        in_str = False
        i = 0
        while i < len(line):
            c = line[i]
            if in_str and c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = not in_str
            elif not in_str and (c == "#" or line.startswith("//", i)):
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def _scan_expr(s: str, i: int, comma_ends: bool, where: str) -> tuple[str, int]:
    """s[i:]에서 식 하나를 읽는다. 괄호 바깥의 줄바꿈(comma_ends면 쉼표도)에서 끝난다."""
    start = i
    depth = 0
    in_str = False
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
            if depth < 0:
                raise SystemExit(f"{where}: 괄호가 맞지 않는다: {s[start:i + 1].strip()}")
        elif depth == 0 and (c == "\n" or (comma_ends and c == ",")):
            break
        i += 1
    if in_str or depth:
        raise SystemExit(f"{where}: 문자열이나 괄호가 닫히지 않는다: {s[start:].strip()[:60]}")
    return s[start:i].strip(), i


def _parse_plain_str(expr: str, where: str) -> str:
    if not re.fullmatch(_PLAIN_STR, expr):
        raise SystemExit(
            f"{where}: 해석할 수 없는 값이다 (보간, 이스케이프, 문자열이 아닌 식은 지원하지 않는다): {expr}")
    return expr[1:-1]


def _parse_str_list(expr: str, where: str) -> list[str]:
    if not (expr.startswith("[") and expr.endswith("]")):
        raise SystemExit(f"{where}: 문자열 목록([...])이어야 한다: {expr}")
    inner = expr[1:-1]
    items = re.findall(_PLAIN_STR, inner)
    rest = re.sub(_PLAIN_STR, "", inner)
    if re.sub(r"[\s,]", "", rest):
        raise SystemExit(f"{where}: 목록에 해석할 수 없는 값이 있다: {expr}")
    return [it[1:-1] for it in items]


def _parse_map(expr: str, where: str) -> dict[str, str]:
    """맵을 이름 -> 식으로 돌려준다. 식은 변수 이름이거나 따옴표 붙은 단순 문자열이다."""
    if not (expr.startswith("{") and expr.endswith("}")):
        raise SystemExit(f"{where}: 맵({{...}})이어야 한다: {expr}")
    inner = expr[1:-1]
    entries: dict[str, str] = {}
    i = 0
    while True:
        m = re.compile(r"[\s,]*").match(inner, i)
        i = m.end()  # type: ignore[union-attr]
        if i >= len(inner):
            break
        km = re.compile(rf"({_IDENT}(?:[-.][A-Za-z0-9_]+)*|{_PLAIN_STR})\s*=(?!=)\s*").match(inner, i)
        if not km:
            raise SystemExit(f"{where}: 맵 항목을 읽을 수 없다: {inner[i:].strip()[:60]}")
        key = km.group(1)
        if key.startswith('"'):
            key = key[1:-1]
        value, i = _scan_expr(inner, km.end(), True, f"{where}.{key}")
        if not (re.fullmatch(_IDENT, value) or re.fullmatch(_PLAIN_STR, value)):
            raise SystemExit(
                f"{where}.{key}: 해석할 수 없는 값이다 (변수 이름이나 단순 문자열만 지원한다): {value}")
        if key in entries:
            raise SystemExit(f"{where}: 항목 {key}가 중복이다")
        entries[key] = value
    return entries


def parse_bake_attrs(block: str, name: str = "?") -> dict[str, object]:
    """target 블록 하나의 속성을 읽어 돌려준다. 모르는 것은 말없이 버리지 않고 SystemExit로 멈춘다.

    스칼라는 문자열, 목록은 문자열 리스트, 맵은 이름 -> 식 딕셔너리다. tags는 구조만 확인하고 버린다.
    """
    where0 = f"{BAKE_FILE}: target {name}"
    body = _strip_comments(block[block.index("{") + 1:block.rindex("}")])
    attrs: dict[str, object] = {}
    i = 0
    while True:
        m = re.compile(r"\s*").match(body, i)
        i = m.end()  # type: ignore[union-attr]
        if i >= len(body):
            break
        am = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)\s*=(?!=)").match(body, i)
        if not am:
            raise SystemExit(f"{where0}: 속성을 읽을 수 없다: {body[i:].strip().splitlines()[0][:60]}")
        attr = am.group(1)
        where = f"{where0}.{attr}"
        if attr not in BAKE_KNOWN_ATTRS:
            raise SystemExit(
                f"{where}: 지원하지 않는 속성이다. image_keys.py가 key 재료로 다루지 못하면 key가 "
                f"이미지 바이트와 어긋날 수 있다. 지원이 필요하면 image_keys.py에 추가한다")
        if attr in attrs:
            raise SystemExit(f"{where}: 속성이 중복이다")
        expr, i = _scan_expr(body, am.end(), False, where)
        if attr in BAKE_SCALAR_ATTRS:
            attrs[attr] = _parse_plain_str(expr, where)
        elif attr in BAKE_LIST_ATTRS or attr == BAKE_INHERITS_ATTR:
            attrs[attr] = _parse_str_list(expr, where)
        elif attr in BAKE_MAP_ATTRS:
            attrs[attr] = _parse_map(expr, where)
        # tags는 _scan_expr가 구조를 확인했으므로 버린다
    return attrs


def resolve_attrs(blocks: dict[str, str], name: str, _stack: tuple[str, ...] = ()) -> dict[str, object]:
    """상속을 bake처럼 합친다. 부모를 inherits 순서대로 합친 뒤 자신을 덮고, 맵은 항목별로 합친다."""
    if name in _stack:
        raise SystemExit(f"{BAKE_FILE}: 상속이 순환한다: {' -> '.join(_stack + (name,))}")
    if name not in blocks:
        raise SystemExit(f"{BAKE_FILE}: target {name} 블록이 없다 ({' -> '.join(_stack)}에서 상속)")
    own = parse_bake_attrs(blocks[name], name)
    merged: dict[str, object] = {}
    layers = [resolve_attrs(blocks, p, _stack + (name,)) for p in own.get(BAKE_INHERITS_ATTR, [])]  # type: ignore[union-attr]
    layers.append({k: v for k, v in own.items() if k != BAKE_INHERITS_ATTR})
    for layer in layers:
        for k, v in layer.items():
            if k in BAKE_MAP_ATTRS:
                merged[k] = {**merged.get(k, {}), **v}  # type: ignore[dict-item,union-attr]
            else:
                merged[k] = v
    return merged


def bake_material(blocks: dict[str, str], name: str) -> list[str]:
    merged = resolve_attrs(blocks, name)
    out: list[str] = []
    for a in BAKE_SCALAR_ATTRS:
        if a in merged:
            out.append(f"bake {a} {merged[a]}")
    for a in BAKE_LIST_ATTRS:
        if a in merged:
            out.append(f"bake {a} {','.join(sorted(merged[a]))}")  # type: ignore[arg-type]
    for a in BAKE_MAP_ATTRS:
        for k, v in sorted(merged.get(a, {}).items()):  # type: ignore[union-attr]
            if a == "args" and k in KEY_EXCLUDED_ARGS:
                continue
            out.append(f"bake {a} {k}={v}")
    return out


def load_images() -> dict[str, Image]:
    with open(BAKE_FILE, encoding="utf-8") as f:
        blocks = parse_bake_blocks(f.read())
    images: dict[str, Image] = {}
    for name in blocks:
        if name.startswith("_"):
            continue
        merged = resolve_attrs(blocks, name)
        if "dockerfile" not in merged:
            raise SystemExit(f"{BAKE_FILE}: target {name}에 dockerfile이 없다")
        img = Image(name=name, dockerfile=str(merged["dockerfile"]))
        img.inherits = parse_bake_attrs(blocks[name], name).get(BAKE_INHERITS_ATTR, [])  # type: ignore[assignment]
        for ctx, expr in merged.get("contexts", {}).items():  # type: ignore[union-attr]
            m = re.fullmatch(r'"target:([^"]+)"', expr)
            if m:
                img.base_contexts[ctx] = m.group(1)
        img.bake_material = bake_material(blocks, name)
        images[name] = img
    for img in images.values():
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
                raise SystemExit(f"URL을 가져오는 {m.group(1)}는 key에 넣을 수 없다: {src}")
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
        ]
        mat.extend(img.bake_material)
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
    p = argparse.ArgumentParser(description="이미지 캐시 key 계산")
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
