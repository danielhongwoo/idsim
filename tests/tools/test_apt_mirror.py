"""Dockerfile의 apt 미러 치환과 검사 RUN 단계를 실제 셸로 돌려 보는 테스트.

run 42765345017(PR #11)에서 CI가 UBUNTU_APT_MIRROR를 archive.ubuntu.com으로 덮어쓰자 검사가 실패했다.
로컬 값(versions.env)과 CI 값(build-images.yml)을 모두 넣어 돌려 같은 실수를 빌드 전에 잡는다.
"""
import os
import re
import subprocess

import pytest
import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCES = "/etc/apt/sources.list.d/ubuntu.sources"
DOCKERFILES = ["docker/Dockerfile.ros-base", "docker/Dockerfile.xrce-agent"]

# ubuntu:24.04 이미지의 기본 ubuntu.sources
NOBLE_SOURCES = """Types: deb
URIs: http://archive.ubuntu.com/ubuntu/
Suites: noble noble-updates noble-backports
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""


def _mirror_run(dockerfile):
    """UBUNTU_APT_MIRROR를 쓰는 RUN 단계의 셸 명령을 꺼낸다(줄 이어 쓰기 결합)."""
    text = open(os.path.join(REPO, dockerfile), encoding="utf-8").read()
    joined = re.sub(r"\\\n", " ", text)
    runs = [ln[4:] for ln in joined.splitlines() if ln.startswith("RUN ") and "UBUNTU_APT_MIRROR" in ln]
    assert len(runs) == 1, f"{dockerfile}: 미러 RUN 단계가 1개가 아니다: {len(runs)}"
    assert SOURCES in runs[0]
    return runs[0]


def _local_mirror():
    for ln in open(os.path.join(REPO, "docker/versions.env"), encoding="utf-8"):
        if ln.startswith("UBUNTU_APT_MIRROR="):
            return ln.split("=", 1)[1].strip()
    raise AssertionError("versions.env에 UBUNTU_APT_MIRROR가 없다")


def _ci_mirrors():
    wf = yaml.safe_load(open(os.path.join(REPO, ".github/workflows/build-images.yml"), encoding="utf-8"))
    found = set()

    def walk(node):
        if isinstance(node, dict):
            env = node.get("env")
            if isinstance(env, dict) and "UBUNTU_APT_MIRROR" in env:
                found.add(str(env["UBUNTU_APT_MIRROR"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(wf)
    assert found, "build-images.yml에 UBUNTU_APT_MIRROR 덮어쓰기가 없다"
    return sorted(found)


def _run(cmd, mirror, sources, tmp_path):
    f = tmp_path / "ubuntu.sources"
    f.write_text(sources, encoding="utf-8")
    env = dict(os.environ, UBUNTU_APT_MIRROR=mirror)
    r = subprocess.run(["sh", "-c", cmd.replace(SOURCES, str(f))], env=env, capture_output=True, text=True)
    return r.returncode, f.read_text(encoding="utf-8")


MIRRORS = [("local", _local_mirror())] + [("ci", m) for m in _ci_mirrors()]


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
@pytest.mark.parametrize("label,mirror", MIRRORS)
def test_mirror_step_passes(dockerfile, label, mirror, tmp_path):
    rc, out = _run(_mirror_run(dockerfile), mirror, NOBLE_SOURCES, tmp_path)
    assert rc == 0, f"{label} 미러 {mirror}에서 실패"
    uris = [ln for ln in out.splitlines() if ln.startswith("URIs:")]
    assert uris == [f"URIs: {mirror.rstrip('/')}/"] * 2


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_mirror_step_rejects_unreplaced_line(dockerfile, tmp_path):
    # security 줄이 치환 패턴에 걸리지 않는 형태로 남으면 실패해야 한다
    sources = NOBLE_SOURCES.replace("http://security.ubuntu.com/ubuntu/", "http://security.ubuntu.com/ubuntu-ports/")
    rc, _ = _run(_mirror_run(dockerfile), _local_mirror(), sources, tmp_path)
    assert rc != 0


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_mirror_step_rejects_empty(dockerfile, tmp_path):
    rc, _ = _run(_mirror_run(dockerfile), "", NOBLE_SOURCES, tmp_path)
    assert rc != 0
