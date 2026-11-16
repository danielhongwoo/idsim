#!/usr/bin/env python3
"""이미지 5종을 key 순서대로 빌드한다. build job과 로컬이 같은 코드를 쓴다.

모드
  load  로컬. 레지스트리를 보지 않고 bake --load로 docker에 올린다. 태그는 bake 파일 기본값
        (idsim/<이미지>:local 과 <REGISTRY>/<이미지>:<key>).
  pr    빌드만. key가 레지스트리에 있으면 건너뛰고, 없으면 레지스트리 캐시를 읽기만 하며 빌드한다.
        결과는 빌더 캐시에만 남는다(type=cacheonly). 포크 PR에는 쓰기 토큰이 없으므로 푸시하지 않는다.
  pull  빌드하지 않는다. 레지스트리의 <REGISTRY>/<이미지>:<key>를 받아 idsim/<이미지>:local로 태그한다.
        로그인 없이 익명으로 받는다(공개 패키지). 기본 대상은 스택이 쓰는 네 이미지(xrce-agent, sim-base,
        px4, ros-ws)이고 베이스(ros-base)는 받지 않는다. key가 레지스트리에 없으면 빌드하지 않고 실패한다.
        sitl job과 새 개발 PC가 쓴다. 이미지 PR이 main에 먼저 들어가 build job이 key를 올려야 받을 수 있다.
  push  main 전용. key가 있으면 건너뛰고, 없으면 빌드해 <REGISTRY>/<이미지>:<key>로 푸시하고
        <REGISTRY>/<이미지>:buildcache 에 레이어 캐시(mode=min)를 내보낸다.

플랫폼
  빌드 플랫폼은 호스트 아키텍처(platform.machine())로 정하고 --platform으로 바꿀 수 있다. 모든 모드에서 bake에
  --set *.platform=<플랫폼>을 주고 versions.env의 그 플랫폼 값(image_keys.PLATFORM_DEPENDENT_NAMES)을 넘긴다.
  key는 플랫폼과 무관하게 하나다(image_keys.py의 플랫폼 절). 한 태그 아래 플랫폼별 manifest가 묶일 수 있으므로
  key가 레지스트리에 있어도 그 플랫폼 이미지가 있다는 뜻은 아니다.
  - pull: 태그에 이 플랫폼의 manifest가 있는지 보고 없으면 받지 않고 실패한다(다른 플랫폼 이미지를 받아
    에뮬레이션으로 돌리지 않는다). docker pull에도 --platform을 준다.
  - pr, push: CI 플랫폼(linux/amd64)에서만 받는다. GHCR에는 amd64 이미지만 올린다.

베이스 해석
  베이스 key가 레지스트리에 있으면(원래 있었거나 이번 실행에서 푸시함) named context를
  docker-image://<REGISTRY>/<베이스>:<key> 로 바꿔 베이스를 다시 빌드하지 않는다. 없으면 bake 파일의
  target: context가 그대로 쓰여 같은 bake 호출 안에서 베이스도 빌드된다(pr, load 모드).
  push 모드에서는 베이스가 항상 먼저 푸시되므로 베이스를 다시 빌드하는 일이 없다.

사용법
  tools/ci/build_images.py --mode load                 # 로컬 전체
  tools/ci/build_images.py --mode load ros-ws          # 지정 이미지만 (베이스는 자동)
  tools/ci/build_images.py --mode pull                 # GHCR에서 네 이미지를 받아 idsim/<이미지>:local로 태그
  tools/ci/build_images.py --mode pull --dry-run       # 받을 참조만 확인(레지스트리 조회는 한다)
  tools/ci/build_images.py --mode pr --plan            # 무엇을 빌드할지만 판단 (GITHUB_OUTPUT에 need_build)
  tools/ci/build_images.py --mode push --dry-run       # 명령만 출력
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import image_keys  # noqa: E402

BAKE_FILE_REL = "docker/docker-bake.hcl"
# push 모드에서 이미지 하나를 빌드하기 전에 루트 파일시스템 여유가 이보다 적으면 빌더 캐시를 비운다.
# px4 빌더 단계가 약 7.7GB이고 압축과 푸시 중 임시 공간이 더 필요하므로 넉넉히 잡는다.
MIN_FREE_GIB = 25
# pull 모드의 기본 대상. 스택이 쓰는 이미지다(tools/gen_compose.py의 IMAGE_NAMES와 같다). 베이스는 받지 않는다.
PULL_IMAGES = ("xrce-agent", "sim-base", "px4", "ros-ws")
# 로컬 태그. docker-bake.hcl의 tags 첫 항목과 tools/gen_compose.py의 기본 이미지 접두사(idsim)와 tag(local)
LOCAL_PREFIX = "idsim"
LOCAL_TAG = "local"


def log(msg: str) -> None:
    print(msg, flush=True)


def in_github() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def group(title: str) -> None:
    if in_github():
        log(f"::group::{title}")
    else:
        log(f"==== {title}")


def endgroup() -> None:
    if in_github():
        log("::endgroup::")


def free_gib(path: str = "/") -> float:
    return shutil.disk_usage(path).free / (1 << 30)


def registry_has(ref: str, strict: bool = False) -> tuple[bool, str]:
    """(있음, 사유). 없음으로 판단할 수 있는 오류만 False로 돌려주고 그 밖의 오류는 중단한다.

    strict(push 모드)에서는 not found 계열만 "없음"으로 보고, 권한 거부(denied, 403)는 중단한다.
    로그인한 토큰으로 없는 패키지를 조회하면 GHCR는 not found를 준다(PR #1 실행에서 확인).
    권한 거부를 "없음"으로 보면 같은 key 태그를 다른 바이트의 이미지로 덮어쓸 수 있다.
    """
    proc = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", ref],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0:
        return True, "manifest 있음"
    err = (proc.stderr or proc.stdout).strip().splitlines()
    msg = err[-1] if err else f"exit {proc.returncode}"
    low = msg.lower()
    # 패키지가 아직 없거나 비공개인데 토큰이 읽기 권한이 없으면 GHCR는 not found 대신 denied를 준다.
    # 어느 쪽이든 "쓸 수 있는 이미지가 없다"로 보고 빌드한다(PR은 푸시하지 않으므로 안전).
    for word in ("not found", "manifest unknown", "name unknown"):
        if word in low:
            return False, msg
    for word in ("denied", "unauthorized", "403 forbidden"):
        if word in low:
            if strict:
                raise SystemExit(f"레지스트리 권한 거부(push 모드에서는 중단): {ref}: {msg}")
            return False, msg
    raise SystemExit(f"레지스트리 조회 실패(네트워크 등): {ref}: {msg}")


def write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def write_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def oci_labels() -> dict[str, str]:
    labels = {}
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    if server and repo:
        # GHCR가 패키지를 저장소에 연결하는 데 쓰는 라벨
        labels["org.opencontainers.image.source"] = f"{server}/{repo}"
    if sha:
        labels["org.opencontainers.image.revision"] = sha
    return labels


_INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)


def _imagetools(*args: str) -> str:
    proc = subprocess.run(["docker", "buildx", "imagetools", "inspect", *args],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        raise SystemExit(f"레지스트리 조회 실패: {args[-1]}: {err[-1] if err else proc.returncode}")
    return proc.stdout


def manifest_platforms(raw: dict, single_config=None) -> set[str]:
    """manifest(또는 index) JSON의 플랫폼 집합 (os/architecture, variant 제외). attestation(unknown/unknown)은 뺀다.

    단일 manifest는 플랫폼이 config에만 있으므로 single_config()가 돌려주는 image config로 읽는다.
    """
    if raw.get("mediaType") in _INDEX_TYPES or "manifests" in raw:
        out = set()
        for m in raw.get("manifests", []):
            p = m.get("platform") or {}
            if p.get("os") and p.get("os") != "unknown":
                out.add(f"{p['os']}/{p.get('architecture')}")
        return out
    cfg = single_config() if single_config else {}
    return {f"{cfg.get('os')}/{cfg.get('architecture')}"} if cfg.get("os") else set()


def registry_platforms(ref: str) -> set[str]:
    """레지스트리 태그가 가진 플랫폼 집합. 태그가 있다는 것은 registry_has로 먼저 확인한다."""
    raw = json.loads(_imagetools("--raw", ref))
    return manifest_platforms(raw, lambda: json.loads(_imagetools("--format", "{{json .Image}}", ref)))


def pull_images(targets: list[str], images, ref, platform: str, dry_run: bool, platforms_of=registry_platforms) -> int:
    """targets의 <REGISTRY>/<이미지>:<key>에서 platform 이미지를 받아 idsim/<이미지>:local로 태그한다.

    key가 없거나 그 태그에 platform manifest가 없는 이미지가 하나라도 있으면 아무것도 받지 않고 실패한다.
    """
    missing = []
    wrong_arch = []
    for n in targets:
        has, why = registry_has(ref(n))
        if not has:
            missing.append(f"{n} {images[n].key} ({why})")
            continue
        have = platforms_of(ref(n))
        if platform not in have:
            wrong_arch.append(f"{n} {images[n].key} (태그에 있는 플랫폼: {', '.join(sorted(have)) or '없음'})")
    if missing:
        log("레지스트리에 key가 없다. 이미지 PR을 먼저 main에 넣어 build job이 key를 올리게 하거나 --mode load로 빌드하라:")
        for m in missing:
            log(f"  {m}")
    if wrong_arch:
        log(f"레지스트리 태그에 {platform} 이미지가 없다. 다른 플랫폼 이미지를 에뮬레이션으로 돌리지 않는다. "
            f"--mode load로 이 호스트에서 빌드하라:")
        for m in wrong_arch:
            log(f"  {m}")
    if missing or wrong_arch:
        return 1
    results = []
    for n in targets:
        local = f"{LOCAL_PREFIX}/{n}:{LOCAL_TAG}"
        pull_cmd = ["docker", "pull", "--quiet", "--platform", platform, ref(n)]
        log("$ " + " ".join(pull_cmd))
        log(f"$ docker tag {ref(n)} {local}")
        t0 = time.monotonic()
        if not dry_run:
            for cmd in (pull_cmd, ["docker", "tag", ref(n), local]):
                proc = subprocess.run(cmd, check=False)
                if proc.returncode != 0:
                    log(f"::error::{n}: {' '.join(cmd[:2])} 실패 (exit {proc.returncode})" if in_github()
                        else f"{n}: {' '.join(cmd[:2])} 실패 (exit {proc.returncode})")
                    return proc.returncode
        results.append((n, f"{time.monotonic() - t0:.0f}s"))
    log("결과")
    for n, dt in results:
        log(f"  {n:<11} {images[n].key} PULL+TAG {dt}")
    write_summary(
        ["mode `pull`", "", "| 이미지 | key | 결과 | 시간 |", "| --- | --- | --- | --- |"]
        + [f"| {n} | `{images[n].key}` | PULL+TAG | {dt} |" for n, dt in results])
    return 0


def check_platform(mode: str, platform: str, versions: dict, environ) -> str | None:
    """플랫폼과 모드의 조합이 안 되면 사유를, 되면 None을 돌려준다. versions는 그 플랫폼의 값(effective_versions)."""
    if platform == image_keys.CI_PLATFORM:
        return None
    if mode in ("pr", "push"):
        return (f"{platform} 호스트는 {mode} 모드를 쓸 수 없다(CI와 GHCR는 {image_keys.CI_PLATFORM} 전용). "
                f"--mode load로 빌드하라")
    if mode == "pull":
        return None
    mirror = environ.get("UBUNTU_APT_MIRROR")
    if mirror and mirror != versions["UBUNTU_APT_MIRROR"]:
        return (f"{platform}에서는 UBUNTU_APT_MIRROR 환경변수({mirror})를 받지 않는다. Dockerfile의 미러 치환이 "
                f"archive/security 주소만 바꾸므로 arm64(ports) 이미지는 versions.env의 UBUNTU_APT_MIRROR_ARM64"
                f"({versions['UBUNTU_APT_MIRROR']})만 쓸 수 있다. 환경변수를 지우고 다시 실행하라")
    return None


def make_env(environ, versions: dict, keys: dict) -> dict:
    """bake에 넘길 환경. versions.env가 환경변수를 덮되, key에서 제외된 값(미러)만 미리 설정된 환경변수가 이긴다."""
    env = dict(environ)
    env.update(versions)
    for k in image_keys.KEY_EXCLUDED_ARGS:
        if environ.get(k):
            env[k] = environ[k]
    env.update(keys)
    return env


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="이미지 key 순서대로 bake 빌드")
    p.add_argument("--mode", choices=["load", "pr", "push", "pull"], required=True)
    p.add_argument("--plan", action="store_true", help="레지스트리 확인까지만 하고 빌드하지 않는다")
    p.add_argument("--dry-run", action="store_true", help="bake 명령(pull 모드는 docker pull과 tag)을 출력만 한다")
    p.add_argument("--platform", choices=image_keys.SUPPORTED_PLATFORMS, default=None,
                   help="빌드 플랫폼 (기본: 호스트 아키텍처)")
    p.add_argument("images", nargs="*", help="대상 이미지 (기본: 전체)")
    args = p.parse_args(argv)

    platform = args.platform or image_keys.host_platform()
    raw_versions = image_keys.read_versions(image_keys.VERSIONS_FILE)
    versions = image_keys.effective_versions(raw_versions, platform)
    images = image_keys.load_images()
    order = image_keys.compute(images, raw_versions)
    registry = versions["REGISTRY"]
    mode = args.mode
    why_not = check_platform(mode, platform, versions, os.environ)
    if why_not:
        log(f"::error::{why_not}" if in_github() else why_not)
        return 2

    if mode == "push" and in_github():
        repo = os.environ.get("GITHUB_REPOSITORY", "").lower()
        if registry.lower() != f"ghcr.io/{repo}":
            log(f"::warning::REGISTRY({registry})가 이 저장소(ghcr.io/{repo})가 아니다. 포크로 보고 푸시 없이 빌드만 한다.")
            mode = "pr"

    if mode == "pull":
        wanted = set(args.images) if args.images else set(PULL_IMAGES)
    else:
        wanted = set(args.images) if args.images else set(order)
    unknown = wanted - set(order)
    if unknown:
        p.error(f"모르는 이미지: {sorted(unknown)}")
    if mode != "pull":
        # 지정한 이미지의 베이스도 대상에 넣는다(pull은 완성된 이미지를 받으므로 베이스가 필요 없다)
        for n in list(wanted):
            b = images[n].base
            while b:
                wanted.add(b)
                b = images[b].base
    targets = [n for n in order if n in wanted]

    def ref(n: str) -> str:
        return f"{registry}/{n}:{images[n].key}"

    env = make_env(os.environ, versions, {images[n].env_name: images[n].key for n in order})

    log(f"mode={mode} platform={platform} registry={registry}")
    for n in targets:
        log(f"  {n:<11} key={images[n].key} base={images[n].base or '-'}")

    if mode == "pull":
        return pull_images(targets, images, ref, platform, args.dry_run)

    # 1. 레지스트리 확인
    available: set[str] = set()
    status: dict[str, str] = {}
    if mode == "load":
        for n in targets:
            status[n] = "BUILD (load 모드는 레지스트리를 보지 않음)"
    else:
        for n in targets:
            has, why = registry_has(ref(n), strict=(mode == "push"))
            if has:
                available.add(n)
                status[n] = f"SKIP key가 레지스트리에 있음 ({ref(n)})"
            else:
                status[n] = f"BUILD key 없음 ({why})"
    for n in targets:
        log(f"[plan] {n}: {status[n]}")
    to_build = [n for n in targets if n not in available]
    write_output("need_build", "true" if to_build else "false")
    write_output("build_list", " ".join(to_build))
    if args.plan:
        write_summary(
            ["| 이미지 | key | 판단 |", "| --- | --- | --- |"]
            + [f"| {n} | `{images[n].key}` | {status[n].split(' ')[0]} |" for n in targets])
        return 0

    # 2. 빌드
    results: list[tuple[str, str, str]] = []
    labels = oci_labels() if mode != "load" else {}
    for n in targets:
        if n in available:
            results.append((n, "SKIP", "-"))
            continue
        if mode == "push" and free_gib() < MIN_FREE_GIB:
            log(f"디스크 여유 {free_gib():.1f} GiB < {MIN_FREE_GIB} GiB, 빌더 캐시를 비운다")
            if not args.dry_run:
                subprocess.run(["docker", "buildx", "prune", "-af"], check=True)

        # 베이스 사슬: 베이스가 레지스트리에 없으면 같은 bake 호출에서 함께 빌드된다
        chain = [n]
        while images[chain[-1]].base and images[chain[-1]].base not in available:
            if mode == "push":
                raise SystemExit(f"{n}: 베이스 {images[chain[-1]].base}가 레지스트리에 없다 (push 순서 오류)")
            chain.append(images[chain[-1]].base)

        cmd = ["docker", "buildx", "bake", "-f", BAKE_FILE_REL, "--progress=plain", n]
        cmd += ["--set", f"*.platform={platform}"]
        for t in chain:
            base = images[t].base
            if base and base in available:
                for ctx in images[t].base_contexts:
                    cmd += ["--set", f"{t}.contexts.{ctx}=docker-image://{ref(base)}"]
            if mode != "load":
                cmd += ["--set", f"{t}.cache-from=type=registry,ref={registry}/{t}:buildcache"]
        if mode == "load":
            cmd.append("--load")
        else:
            cmd += ["--set", f"{n}.tags={ref(n)}"]
            for k, v in labels.items():
                cmd += ["--set", f"{n}.labels.{k}={v}"]
            if mode == "push":
                cmd += [
                    "--set",
                    f"{n}.cache-to=type=registry,ref={registry}/{n}:buildcache,mode=min,ignore-error=true",
                    "--push",
                ]
            else:
                cmd += ["--set", f"{n}.output=type=cacheonly"]

        group(f"build {n} ({' <- '.join(chain)})")
        log("$ " + " ".join(cmd))
        log(f"디스크 여유 {free_gib():.1f} GiB")
        t0 = time.monotonic()
        if not args.dry_run:
            proc = subprocess.run(cmd, cwd=image_keys.REPO_ROOT, env=env, check=False)
            if proc.returncode != 0:
                endgroup()
                log(f"::error::{n} 빌드 실패 (exit {proc.returncode})" if in_github()
                    else f"{n} 빌드 실패 (exit {proc.returncode})")
                return proc.returncode
        dt = time.monotonic() - t0
        log(f"{n}: {dt:.0f}초, 디스크 여유 {free_gib():.1f} GiB")
        endgroup()
        action = {"load": "BUILT+LOAD", "pr": "BUILT (푸시 없음)", "push": "BUILT+PUSH"}[mode]
        results.append((n, action, f"{dt:.0f}s"))
        if mode == "push":
            available.add(n)

    log("결과")
    for n, action, dt in results:
        log(f"  {n:<11} {images[n].key} {action} {dt}")
    write_summary(
        [f"mode `{mode}`", "", "| 이미지 | key | 결과 | 시간 |", "| --- | --- | --- | --- |"]
        + [f"| {n} | `{images[n].key}` | {a} | {dt} |" for n, a, dt in results])
    return 0


if __name__ == "__main__":
    sys.exit(main())
