"""tools/ci/image_keys.py의 미러 key 제외와 build_images.py의 환경변수 우선 범위 테스트(초안 devops-engineer, 승인 test-engineer)."""
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "ci"))

import build_images  # noqa: E402
import image_keys  # noqa: E402


def _keys(versions):
    images = image_keys.load_images()
    image_keys.compute(images, versions)
    return {n: i.key for n, i in images.items()}


def _versions():
    return image_keys.read_versions(image_keys.VERSIONS_FILE)


def test_mirror_is_excluded_from_keys():
    v = _versions()
    assert "UBUNTU_APT_MIRROR" in v
    changed = dict(v, UBUNTU_APT_MIRROR="http://archive.ubuntu.com/ubuntu")
    assert _keys(v) == _keys(changed)


def test_other_versions_still_change_keys():
    v = _versions()
    changed = dict(v, ROS_DISTRO="other")
    assert _keys(v)["ros-base"] != _keys(changed)["ros-base"]


def test_env_override_only_for_excluded_args():
    versions = {"UBUNTU_APT_MIRROR": "http://kr/", "ROS_DISTRO": "jazzy"}
    environ = {"UBUNTU_APT_MIRROR": "http://archive/", "ROS_DISTRO": "evil"}
    env = build_images.make_env(environ, versions, {"KEY_X": "k"})
    assert env["UBUNTU_APT_MIRROR"] == "http://archive/"
    assert env["ROS_DISTRO"] == "jazzy"
    assert env["KEY_X"] == "k"


def test_versions_win_when_env_unset():
    env = build_images.make_env({}, {"UBUNTU_APT_MIRROR": "http://kr/"}, {})
    assert env["UBUNTU_APT_MIRROR"] == "http://kr/"


def _keys_with_bake(tmp_path, monkeypatch, transform):
    with open(image_keys.BAKE_FILE, encoding="utf-8") as f:
        text = f.read()
    bake = tmp_path / "docker-bake.hcl"
    bake.write_text(transform(text), encoding="utf-8")
    monkeypatch.setattr(image_keys, "BAKE_FILE", str(bake))
    return _keys(_versions())


def _material(name):
    images = image_keys.load_images()
    return images[name].bake_material


def _sub(text, old, new):
    """치환 대상이 원문에 있고 치환 뒤 텍스트가 실제로 바뀌었음을 단정한다."""
    assert old in text, old
    out = text.replace(old, new)
    assert out != text, old
    return out


def test_bake_tags_and_whitespace_do_not_change_keys(tmp_path, monkeypatch):
    base = _keys(_versions())

    def edit(t):
        t = _sub(t, "idsim/px4:local", "idsim/px4:renamed")
        t = _sub(t, "  tags = [", "\n\n      tags    =   [")
        t = _sub(t, "PX4_TAG           = PX4_TAG", "PX4_TAG=PX4_TAG   # 주석")
        return t + "\n# 끝 주석\n"

    assert _keys_with_bake(tmp_path, monkeypatch, edit) == base


def test_bake_args_and_dockerfile_change_keys(tmp_path, monkeypatch):
    base = _keys(_versions())
    args = _keys_with_bake(
        tmp_path, monkeypatch,
        lambda t: _sub(t, "LLVM_MAJOR      = LLVM_MAJOR", "LLVM_MAJOR      = ROS_DISTRO"))
    assert args["ros-ws"] != base["ros-ws"]
    assert args["ros-base"] == base["ros-base"]
    assert args["px4"] == base["px4"]
    dockerfile = _keys_with_bake(
        tmp_path, monkeypatch,
        lambda t: _sub(t, '"Dockerfile.xrce-agent"', '"Dockerfile.ros-base"'))
    assert dockerfile["xrce-agent"] != base["xrce-agent"]


# fail-closed: 정규화가 모르는 입력을 말없이 버리면 key가 이미지와 어긋난다. 멈추거나 재료에 넣어야 한다.

def _stops(tmp_path, monkeypatch, transform, match):
    with pytest.raises(SystemExit, match=match):
        _keys_with_bake(tmp_path, monkeypatch, transform)


def test_unknown_attr_target_stops(tmp_path, monkeypatch):
    # 경우 (a): 멀티스테이지 target은 이미지 바이트를 바꾼다
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, 'dockerfile = "Dockerfile.px4"', 'dockerfile = "Dockerfile.px4"\n  target = "builder"'),
           r"target px4\.target: 지원하지 않는 속성")


def test_unknown_attr_labels_stops(tmp_path, monkeypatch):
    # 경우 (b): labels는 이미지 config를 바꾼다
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, 'dockerfile = "Dockerfile.px4"', 'dockerfile = "Dockerfile.px4"\n  labels = { a = "b" }'),
           r"target px4\.labels: 지원하지 않는 속성")


def test_inherited_map_merges_per_entry(tmp_path, monkeypatch):
    # 경우 (c): _common의 args 항목이 자식 args에 덮여 사라지면 안 된다 (bake는 항목별로 합친다)
    base = _keys(_versions())
    changed = _keys_with_bake(
        tmp_path, monkeypatch,
        lambda t: _sub(t, 'context   = "docker"\n', 'context   = "docker"\n  args = { EXTRA = "1" }\n'))
    for name in base:
        assert changed[name] != base[name], name
    assert "bake args EXTRA=\"1\"" in _material("px4")


def test_child_map_entries_override_parent_entry(tmp_path, monkeypatch):
    text = (
        'target "_p" {\n  args = { A = X, B = Y }\n}\n'
        'target "c" {\n  inherits = ["_p"]\n  dockerfile = "d"\n  args = { B = Z, C = W }\n}\n')
    blocks = image_keys.parse_bake_blocks(text)
    assert image_keys.bake_material(blocks, "c") == [
        "bake dockerfile d", "bake args A=X", "bake args B=Z", "bake args C=W"]


def test_nested_inherits_is_resolved():
    text = (
        'target "_g" {\n  context = "x"\n}\n'
        'target "_p" {\n  inherits = ["_g"]\n  platforms = ["linux/amd64"]\n}\n'
        'target "c" {\n  inherits = ["_p"]\n  dockerfile = "d"\n}\n')
    blocks = image_keys.parse_bake_blocks(text)
    assert image_keys.bake_material(blocks, "c") == [
        "bake dockerfile d", "bake context x", "bake platforms linux/amd64"]


def test_inherits_cycle_stops():
    blocks = image_keys.parse_bake_blocks(
        'target "a" {\n  inherits = ["b"]\n}\ntarget "b" {\n  inherits = ["a"]\n}\n')
    with pytest.raises(SystemExit, match="순환"):
        image_keys.bake_material(blocks, "a")


def test_interpolation_in_arg_stops(tmp_path, monkeypatch):
    # 경우 (d): "${PX4_TAG}"의 첫 }에서 맵이 잘려 뒤 항목이 사라지던 경우
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, "PX4_TAG           = PX4_TAG\n", 'PX4_TAG           = "${PX4_TAG}"\n    ZZZ = PX4_GZ_MODELS_REF\n'),
           r"\.args\.PX4_TAG: 해석할 수 없는 값")


def test_interpolation_in_scalar_and_list_stops(tmp_path, monkeypatch):
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, 'dockerfile = "Dockerfile.px4"', 'dockerfile = "Dockerfile.${PX4_TAG}"'),
           r"target px4\.dockerfile: 해석할 수 없는 값")
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, 'context   = "docker"\n', 'context   = "docker"\n  platforms = ["linux/${ARCH}"]\n'),
           r"target [\w-]+\.platforms: 목록에 해석할 수 없는 값")


def test_interpolation_in_tags_is_still_ignored(tmp_path, monkeypatch):
    # tags의 보간은 원래 있던 것이고 key에 들어가지 않는다. 보간 부분을 바꿔도 멈추지 않고 key가 같아야 한다
    base = _keys(_versions())
    changed = _keys_with_bake(
        tmp_path, monkeypatch,
        lambda t: _sub(t, '"${REGISTRY}/px4:', '"${OTHER}/px4:'))
    assert changed == base


def test_non_string_scalar_stops(tmp_path, monkeypatch):
    # 경우 (e): context = VAR 처럼 문자열이 아닌 스칼라가 조용히 빠지던 경우
    _stops(tmp_path, monkeypatch,
           lambda t: _sub(t, 'context   = "docker"', "context   = CTX"),
           r"target [\w-]+\.context: 해석할 수 없는 값")


def test_complex_map_value_stops():
    blocks = image_keys.parse_bake_blocks(
        'target "c" {\n  dockerfile = "d"\n  args = { A = upper(X) }\n}\n')
    with pytest.raises(SystemExit, match=r"target c\.args\.A: 해석할 수 없는 값"):
        image_keys.bake_material(blocks, "c")


def test_unbalanced_value_stops():
    blocks = image_keys.parse_bake_blocks(
        'target "c" {\n  dockerfile = "d"\n  platforms = ["a"\n}\n')
    with pytest.raises(SystemExit, match="문자열이나 괄호가 닫히지 않는다"):
        image_keys.bake_material(blocks, "c")


def test_duplicate_attr_and_entry_stop():
    blocks = image_keys.parse_bake_blocks(
        'target "c" {\n  dockerfile = "d"\n  dockerfile = "e"\n}\n')
    with pytest.raises(SystemExit, match=r"target c\.dockerfile: 속성이 중복이다"):
        image_keys.bake_material(blocks, "c")
    blocks = image_keys.parse_bake_blocks(
        'target "c" {\n  dockerfile = "d"\n  args = { A = X, A = Y }\n}\n')
    with pytest.raises(SystemExit, match=r"target c\.args: 항목 A가 중복이다"):
        image_keys.bake_material(blocks, "c")


def test_multiline_list_and_trailing_commas_parse():
    blocks = image_keys.parse_bake_blocks(
        'target "c" {\n  dockerfile = "d"\n  platforms = [\n    "linux/amd64",\n    "linux/arm64",\n  ]\n}\n')
    assert image_keys.bake_material(blocks, "c")[1] == "bake platforms linux/amd64,linux/arm64"



# 플랫폼: 같은 Dockerfile과 bake 파일이 linux/amd64(CI, GHCR)와 linux/arm64(로컬)를 빌드하고 key는 하나다.

ARM64 = "linux/arm64"
AMD64 = "linux/amd64"


def test_keys_do_not_depend_on_host(monkeypatch):
    # 같은 commit이면 amd64 Linux와 arm64 Mac에서 key가 같아야 한다
    v = _versions()
    seen = []
    for machine in ("x86_64", "aarch64", "arm64"):
        monkeypatch.setattr(image_keys._platform, "machine", lambda m=machine: m)
        seen.append(_keys(v))
    assert seen[0] == seen[1] == seen[2]


def test_key_material_has_no_platform():
    images = image_keys.load_images()
    image_keys.compute(images, _versions())
    for img in images.values():
        assert not [x for x in img.material if "platforms" in x or "linux/" in x], img.name


def test_every_platform_has_all_values():
    v = _versions()
    assert set(image_keys.SUPPORTED_PLATFORMS) >= {AMD64, ARM64}
    for platform in image_keys.SUPPORTED_PLATFORMS:
        eff = image_keys.effective_versions(v, platform)
        for name in image_keys.PLATFORM_DEPENDENT_NAMES:
            assert eff[name] == v[name + image_keys.PLATFORM_SUFFIX[platform]]
    assert image_keys.effective_versions(v, ARM64)["UBUNTU_APT_MIRROR"] == v["UBUNTU_APT_MIRROR_ARM64"]
    assert image_keys.effective_versions(v, AMD64)["UBUNTU_APT_MIRROR"] == v["UBUNTU_APT_MIRROR"]


def test_missing_platform_value_stops_everywhere():
    # 한 플랫폼의 줄이라도 없으면 어느 호스트에서든 key 계산과 빌드 인자 준비가 멈춘다
    v = _versions()
    for name in image_keys.PLATFORM_DEPENDENT_NAMES:
        for suf in image_keys.PLATFORM_SUFFIX.values():
            broken = {k: x for k, x in v.items() if k != name + suf}
            with pytest.raises(SystemExit, match=name + suf):
                _keys(broken)
            for platform in image_keys.SUPPORTED_PLATFORMS:
                with pytest.raises(SystemExit, match=name + suf):
                    image_keys.effective_versions(broken, platform)


def test_platform_dependent_arg_puts_all_values_in_key(monkeypatch):
    # 미러가 아닌 플랫폼별 ARG가 생기면 두 플랫폼 값이 모두 key에 들어간다(arm64 값만 바꿔도 key가 바뀐다)
    monkeypatch.setattr(image_keys, "PLATFORM_DEPENDENT_NAMES", ("UBUNTU_IMAGE",))
    v = dict(_versions(), UBUNTU_IMAGE_ARM64="ubuntu:x@sha256:" + "a" * 64)
    base = _keys(v)
    changed = _keys(dict(v, UBUNTU_IMAGE_ARM64="ubuntu:x@sha256:" + "b" * 64))
    assert changed["xrce-agent"] != base["xrce-agent"] and changed["ros-base"] != base["ros-base"]


def test_mirror_values_of_all_platforms_are_excluded_from_keys():
    v = _versions()
    changed = dict(v, UBUNTU_APT_MIRROR_ARM64="http://example.invalid/ubuntu-ports")
    assert _keys(v) == _keys(changed)


def test_host_platform_mapping():
    assert image_keys.host_platform("x86_64") == AMD64
    assert image_keys.host_platform("AMD64") == AMD64
    assert image_keys.host_platform("arm64") == ARM64
    assert image_keys.host_platform("aarch64") == ARM64
    with pytest.raises(SystemExit, match="지원하지 않는 호스트 아키텍처"):
        image_keys.host_platform("ppc64le")
    with pytest.raises(SystemExit, match="지원하지 않는 플랫폼"):
        image_keys.effective_versions(_versions(), "linux/riscv64")


def test_build_images_platform_and_mode():
    v = _versions()
    amd = image_keys.effective_versions(v, AMD64)
    arm = image_keys.effective_versions(v, ARM64)
    for mode in ("load", "pr", "push", "pull"):
        assert build_images.check_platform(mode, AMD64, amd, {}) is None
    for mode in ("load", "pull"):
        assert build_images.check_platform(mode, ARM64, arm, {}) is None
    for mode in ("pr", "push"):
        assert "쓸 수 없다" in build_images.check_platform(mode, ARM64, arm, {})
    # arm64는 미러 환경변수 덮어쓰기를 받지 않는다(같은 값은 받는다)
    assert "UBUNTU_APT_MIRROR" in build_images.check_platform(
        "load", ARM64, arm, {"UBUNTU_APT_MIRROR": "http://archive.ubuntu.com/ubuntu"})
    assert build_images.check_platform(
        "load", ARM64, arm, {"UBUNTU_APT_MIRROR": arm["UBUNTU_APT_MIRROR"]}) is None


def test_build_images_dry_run_sets_platform_and_same_key(capsys, monkeypatch):
    monkeypatch.delenv("UBUNTU_APT_MIRROR", raising=False)
    key = _keys(_versions())["xrce-agent"]
    for platform in (AMD64, ARM64):
        rc = build_images.main(["--mode", "load", "--dry-run", "--platform", platform, "xrce-agent"])
        out = capsys.readouterr().out
        assert rc == 0 and f"--set *.platform={platform}" in out and f"key={key}" in out


def test_manifest_platforms():
    index = {"mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [
        {"platform": {"os": "linux", "architecture": "amd64"}},
        {"platform": {"os": "linux", "architecture": "arm64", "variant": "v8"}},
        {"platform": {"os": "unknown", "architecture": "unknown"}},
    ]}
    assert build_images.manifest_platforms(index) == {AMD64, ARM64}
    single = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "config": {}}
    assert build_images.manifest_platforms(single, lambda: {"os": "linux", "architecture": "amd64"}) == {AMD64}


def _pull(monkeypatch, capsys, platform, have):
    monkeypatch.setattr(build_images, "registry_has", lambda ref, strict=False: (True, "manifest 있음"))
    calls = []
    monkeypatch.setattr(build_images.subprocess, "run", lambda *a, **k: calls.append(a) or None)
    images = image_keys.load_images()
    image_keys.compute(images, _versions())
    rc = build_images.pull_images(["px4"], images, lambda n: f"r/{n}:{images[n].key}", platform, False,
                                  platforms_of=lambda ref: have)
    return rc, capsys.readouterr().out, calls


def test_pull_rejects_tag_without_host_platform(monkeypatch, capsys):
    # 태그에 다른 플랫폼 이미지만 있으면 받지 않는다(에뮬레이션으로 돌리지 않는다)
    rc, out, calls = _pull(monkeypatch, capsys, ARM64, {AMD64})
    assert rc == 1 and "linux/arm64 이미지가 없다" in out and "--mode load" in out and not calls


def test_pull_passes_platform_to_docker_pull(monkeypatch, capsys):
    class Done:
        returncode = 0
    monkeypatch.setattr(build_images, "registry_has", lambda ref, strict=False: (True, "manifest 있음"))
    calls = []
    monkeypatch.setattr(build_images.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done())
    images = image_keys.load_images()
    image_keys.compute(images, _versions())
    rc = build_images.pull_images(["px4"], images, lambda n: f"r/{n}:{images[n].key}", AMD64, False,
                                  platforms_of=lambda ref: {AMD64, ARM64})
    assert rc == 0
    assert calls[0][:5] == ["docker", "pull", "--quiet", "--platform", AMD64]
