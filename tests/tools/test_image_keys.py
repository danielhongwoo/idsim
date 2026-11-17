"""tools/ci/image_keys.py의 미러 key 제외와 build_images.py의 환경변수 우선 범위 테스트(초안 devops-engineer, 승인 test-engineer)."""
import json
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
    # CI는 두 플랫폼 모두 빌드하고 push한다(각자 native runner). 모드로 막는 조합은 없다
    for mode in ("load", "pr", "push", "pull", "merge"):
        assert build_images.check_platform(mode, AMD64, amd, {}) is None
        assert build_images.check_platform(mode, ARM64, arm, {}) is None
    # arm64는 미러 환경변수 덮어쓰기를 받지 않는다(같은 값과 빈 값은 받는다). CI의 pr, push 모드도 같다
    for mode in ("load", "pr", "push"):
        assert "UBUNTU_APT_MIRROR" in build_images.check_platform(
            mode, ARM64, arm, {"UBUNTU_APT_MIRROR": "http://archive.ubuntu.com/ubuntu"})
        assert build_images.check_platform(
            mode, ARM64, arm, {"UBUNTU_APT_MIRROR": arm["UBUNTU_APT_MIRROR"]}) is None
        assert build_images.check_platform(mode, ARM64, arm, {"UBUNTU_APT_MIRROR": ""}) is None


# registry 흉내. tags: 참조 -> 플랫폼 집합. registry_has와 registry_platforms를 이것으로 바꾼다.
def _fake_registry(monkeypatch, tags):
    monkeypatch.setattr(build_images, "registry_has",
                        lambda ref, strict=False: (ref in tags, "manifest 있음" if ref in tags else "not found"))
    monkeypatch.setattr(build_images, "registry_platforms", lambda ref: set(tags[ref]))


def _outputs(tmp_path, monkeypatch):
    out = tmp_path / "github_output"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("UBUNTU_APT_MIRROR", raising=False)

    def read():
        d = dict(line.split("=", 1) for line in out.read_text().splitlines())
        out.write_text("")
        return d
    return read


def _refs():
    keys = _keys(_versions())
    reg = _versions()["REGISTRY"]
    return keys, reg, (lambda n: f"{reg}/{n}:{keys[n]}"), (lambda n, arch: f"{reg}/{n}:{keys[n]}-{arch}")


def test_locate_prefers_key_tag_then_platform_tag(monkeypatch):
    tags = {"r/a:k": {AMD64}, "r/a:k-arm64": {ARM64}, "r/b:k": {AMD64, ARM64}, "r/c:k-arm64": {AMD64}}
    _fake_registry(monkeypatch, tags)
    assert build_images.locate("r/a:k", "r/a:k-amd64", AMD64, False)[0] == "r/a:k"
    # key 태그에 arm64가 없으면(이 구조 이전에 올린 amd64 전용 index) 플랫폼 태그를 쓴다
    assert build_images.locate("r/a:k", "r/a:k-arm64", ARM64, False)[0] == "r/a:k-arm64"
    assert build_images.locate("r/b:k", "r/b:k-arm64", ARM64, False)[0] == "r/b:k"
    found, why = build_images.locate("r/x:k", "r/x:k-arm64", ARM64, False)
    assert found is None and "플랫폼 태그 없음" in why
    # 플랫폼 태그에 다른 플랫폼이 올라가 있으면 멈춘다
    with pytest.raises(SystemExit, match="다른 플랫폼"):
        build_images.locate("r/c:k", "r/c:k-arm64", ARM64, False)


def test_build_images_plan_is_per_platform(tmp_path, monkeypatch, capsys):
    # GHCR의 key 태그가 amd64 전용 index뿐이면: amd64는 전부 건너뛰고 arm64는 전부 빌드한다
    read = _outputs(tmp_path, monkeypatch)
    keys, reg, ref, pref = _refs()
    _fake_registry(monkeypatch, {ref(n): {AMD64} for n in keys})
    assert build_images.main(["--mode", "pr", "--plan", "--platform", AMD64]) == 0
    assert read()["need_build"] == "false"
    assert build_images.main(["--mode", "pr", "--plan", "--platform", ARM64]) == 0
    o = read()
    assert o["need_build"] == "true"
    assert o["build_list"].split() == list(image_keys.compute(image_keys.load_images(), _versions()))
    # arm64 플랫폼 태그가 올라간 뒤(merge 전)에는 arm64도 건너뛴다
    _fake_registry(monkeypatch, {**{ref(n): {AMD64} for n in keys}, **{pref(n, "arm64"): {ARM64} for n in keys}})
    assert build_images.main(["--mode", "push", "--plan", "--platform", ARM64]) == 0
    assert read()["need_build"] == "false"
    capsys.readouterr()


def _bake_lines(out):
    return [line for line in out.splitlines() if line.startswith("$ docker buildx bake")]


def test_build_images_push_uses_platform_tags_and_caches(tmp_path, monkeypatch, capsys):
    # 새 key: 플랫폼마다 플랫폼 태그로 push하고, 자식은 같은 실행에서 push한 자기 플랫폼의 베이스를 context로 쓴다
    _outputs(tmp_path, monkeypatch)
    keys, reg, ref, pref = _refs()
    _fake_registry(monkeypatch, {})
    for platform in (AMD64, ARM64):
        arch = platform.split("/")[1]
        assert build_images.main(["--mode", "push", "--dry-run", "--platform", platform]) == 0
        bake = _bake_lines(capsys.readouterr().out)
        assert len(bake) == len(keys)
        for line in bake:
            n = line.split()[7]
            assert f"--set {n}.tags={pref(n, arch)} " in line and "--push" in line
            assert f"{n}.cache-to=type=registry,ref={reg}/{n}:buildcache-{arch}," in line
            assert f"cache-from=type=registry,ref={reg}/{n}:buildcache-{arch}" in line
            # key 태그와 다른 플랫폼의 태그, cache는 쓰지 않는다
            assert f"{ref(n)} " not in line and not line.endswith(ref(n))
            other = "arm64" if arch == "amd64" else "amd64"
            assert other not in line.replace(f"*.platform=linux/{arch}", "")
        px4 = next(line for line in bake if line.split()[7] == "px4")
        assert f"=docker-image://{pref('sim-base', arch)} " in px4


def test_build_images_push_context_uses_key_tag_when_it_has_platform(tmp_path, monkeypatch, capsys):
    _outputs(tmp_path, monkeypatch)
    keys, reg, ref, pref = _refs()
    _fake_registry(monkeypatch, {ref("ros-base"): {AMD64, ARM64}})
    assert build_images.main(["--mode", "push", "--dry-run", "--platform", ARM64, "ros-ws"]) == 0
    (line,) = _bake_lines(capsys.readouterr().out)
    assert f"=docker-image://{ref('ros-base')} " in line


def test_build_images_pr_never_pushes(tmp_path, monkeypatch, capsys):
    _outputs(tmp_path, monkeypatch)
    _fake_registry(monkeypatch, {})
    for platform in (AMD64, ARM64):
        assert build_images.main(["--mode", "pr", "--dry-run", "--platform", platform]) == 0
        out = capsys.readouterr().out
        assert "cache-to" not in out and "--push" not in out and "output=type=cacheonly" in out


def test_build_images_pr_load_loads_built_and_pulls_skipped(tmp_path, monkeypatch, capsys):
    # ros-ws만 없으면: ros-ws는 docker 저장소에 올리고, 나머지 스택 이미지는 찾은 참조에서 받아 태그한다
    _outputs(tmp_path, monkeypatch)
    keys, reg, ref, pref = _refs()
    tags = {ref(n): {AMD64} for n in keys if n != "ros-ws"}
    tags[pref("px4", "arm64")] = {ARM64}
    _fake_registry(monkeypatch, tags)
    pulled = []
    monkeypatch.setattr(build_images, "pull_images",
                        lambda targets, images, r, platform, dry_run:
                        pulled.append(([r(n) for n in targets], platform)) or 0)
    assert build_images.main(["--mode", "pr", "--load", "--dry-run", "--platform", AMD64]) == 0
    (line,) = _bake_lines(capsys.readouterr().out)
    assert " ros-ws " in line and "ros-ws.output=type=docker" in line and "ros-ws.tags=" not in line
    assert pulled == [([ref("xrce-agent"), ref("sim-base"), ref("px4")], AMD64)]
    # arm64: px4만 플랫폼 태그에 있다. 베이스(ros-base)는 docker 저장소에 올리지 않는다
    pulled.clear()
    assert build_images.main(["--mode", "pr", "--load", "--dry-run", "--platform", ARM64]) == 0
    bake = _bake_lines(capsys.readouterr().out)
    assert [(line.split()[7], "output=type=docker" in line) for line in bake] == [
        ("ros-base", False), ("xrce-agent", True), ("ros-ws", True), ("sim-base", True)]
    assert pulled == [([pref("px4", "arm64")], ARM64)]
    with pytest.raises(SystemExit):
        build_images.main(["--mode", "load", "--load"])


def test_plan_merge_never_makes_half_index():
    tags = {
        # amd64만 가진 key 태그 + arm64 플랫폼 태그 -> 기존 key 태그(그 index)를 원본에 넣어 병합
        "r/a:k": {AMD64}, "r/a:k-arm64": {ARM64},
        # 새 key, 두 플랫폼 태그 -> 플랫폼 태그 둘로 병합
        "r/b:k-amd64": {AMD64}, "r/b:k-arm64": {ARM64},
        # 이미 완성
        "r/c:k": {AMD64, ARM64},
    }
    # 원본은 판단한 시점의 digest로 고정한다(<repo>@<digest>). 흉내: 태그 r/a:k의 digest는 sha256:r/a:k
    has = lambda r: r in tags  # noqa: E731
    digest = lambda r: "sha256:" + r  # noqa: E731
    plats = lambda r: tags[r.split("@sha256:", 1)[1]]  # noqa: E731
    ref = lambda n: f"r/{n}:k"  # noqa: E731
    pref = lambda n, p: f"r/{n}:k-{p.split('/')[1]}"  # noqa: E731
    kw = dict(platforms_of=plats, has=has, digest_of=digest)
    plans, missing = build_images.plan_merge(["a", "b", "c"], ref, pref, **kw)
    assert missing == []
    assert plans == [("a", {AMD64}, ["r/a@sha256:r/a:k", "r/a@sha256:r/a:k-arm64"]),
                     ("b", set(), ["r/b@sha256:r/b:k-amd64", "r/b@sha256:r/b:k-arm64"]),
                     ("c", {AMD64, ARM64}, [])]
    assert build_images.pin("localhost:5055/t/img:k-arm64", "sha256:1") == "localhost:5055/t/img@sha256:1"
    # arm64 job이 실패해 플랫폼 태그가 없으면 빠진 것으로 잡힌다
    del tags["r/b:k-arm64"]
    _, missing = build_images.plan_merge(["a", "b", "c"], ref, pref, **kw)
    assert missing == ["b: linux/arm64 이미지 없음 (r/b:k-arm64)"]


def test_merge_images_creates_nothing_when_any_platform_is_missing(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(build_images, "plan_merge", lambda *a: ([("a", set(), ["r/a:k-amd64"])], ["b: x"]))
    ran = []
    monkeypatch.setattr(build_images.subprocess, "run", lambda *a, **k: ran.append(a))
    assert build_images.merge_images(["a", "b"], None, None, dry_run=False) == 1
    assert ran == [] and "하나도 바꾸지 않는다" in capsys.readouterr().out


def test_merge_images_checks_digests_kept(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(build_images, "plan_merge",
                        lambda *a: ([("a", {AMD64}, ["r/a@sha256:1i", "r/a@sha256:2i"])], []))
    ran = []

    class P:
        returncode = 0
    monkeypatch.setattr(build_images.subprocess, "run", lambda cmd, **k: ran.append(cmd) or P())
    digests = iter([{AMD64: "sha256:1"}, {AMD64: "sha256:1", ARM64: "sha256:2"}])
    seen = []
    monkeypatch.setattr(build_images, "platform_digests", lambda ref: seen.append(ref) or next(digests))
    assert build_images.merge_images(["a"], lambda n: "r/a:k", None, dry_run=False) == 0
    assert ran == [["docker", "buildx", "imagetools", "create", "-t", "r/a:k", "r/a@sha256:1i", "r/a@sha256:2i"]]
    # 병합 전 digest는 고정한 원본에서, 병합 뒤 digest는 key 태그에서 읽는다
    assert seen == ["r/a@sha256:1i", "r/a:k"]
    # 이미 있던 amd64의 digest가 바뀌면 멈춘다
    digests = iter([{AMD64: "sha256:1"}, {AMD64: "sha256:9", ARM64: "sha256:2"}])
    with pytest.raises(SystemExit, match="digest가 바뀐 플랫폼"):
        build_images.merge_images(["a"], lambda n: "r/a:k", None, dry_run=False)


def test_ci_matrix_matches_workflows():
    # lint를 뺀 workflow의 runner matrix가 image_keys.CI_MATRIX와 같아야 한다(runner 목록의 유일한 정의)
    import yaml
    assert {m["arch"] for m in image_keys.CI_MATRIX} == {p.split("/")[1] for p in image_keys.SUPPORTED_PLATFORMS}
    wf_dir = os.path.join(REPO, ".github", "workflows")
    want = [(m["arch"], m["runner"]) for m in image_keys.CI_MATRIX]
    seen = {}
    for name in ("build-images.yml", "unit.yml", "sitl.yml"):
        with open(os.path.join(wf_dir, name), encoding="utf-8") as f:
            wf = yaml.safe_load(f)
        for job_id, job in wf["jobs"].items():
            if job.get("runs-on") != "${{ matrix.runner }}":
                continue
            include = job["strategy"]["matrix"]["include"]
            assert [(m["arch"], m["runner"]) for m in include] == want, (name, job_id)
            # matrix.apt_mirror를 쓰는 job은 모든 항목에 apt_mirror가 있고 CI_MATRIX와 같아야 한다
            uses_mirror = "matrix.apt_mirror" in json.dumps(job)
            for m, c in zip(include, image_keys.CI_MATRIX):
                if uses_mirror:
                    assert m.get("apt_mirror") == c["apt_mirror"], (name, job_id, m)
                else:
                    assert "apt_mirror" not in m, (name, job_id)
            seen[name] = job_id
    assert set(seen) == {"build-images.yml", "unit.yml", "sitl.yml"}


def test_build_images_dry_run_sets_platform_and_same_key(capsys, monkeypatch):
    monkeypatch.delenv("UBUNTU_APT_MIRROR", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    envs = []
    real_make_env = build_images.make_env
    monkeypatch.setattr(build_images, "make_env", lambda *a: envs.append(real_make_env(*a)) or envs[-1])
    v = _versions()
    key = _keys(v)["xrce-agent"]
    for platform in (AMD64, ARM64):
        rc = build_images.main(["--mode", "load", "--dry-run", "--platform", platform, "xrce-agent"])
        out = capsys.readouterr().out
        assert rc == 0 and f"--set *.platform={platform}" in out and f"key={key}" in out
    # bake에 넘기는 미러는 그 플랫폼의 값이다
    assert envs[0]["UBUNTU_APT_MIRROR"] == v["UBUNTU_APT_MIRROR"]
    assert envs[1]["UBUNTU_APT_MIRROR"] == v["UBUNTU_APT_MIRROR_ARM64"]


def test_build_images_main_pull_wires_platform(capsys, monkeypatch):
    # main의 pull 경로가 --platform을 pull_images까지 넘기고, 태그에 그 플랫폼이 없으면 실패한다
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(build_images, "registry_has", lambda ref, strict=False: (True, "manifest 있음"))
    monkeypatch.setattr(build_images, "registry_platforms", lambda ref: {AMD64})
    seen = []
    real_pull = build_images.pull_images
    monkeypatch.setattr(build_images, "pull_images",
                        lambda targets, images, ref, platform, dry_run:
                        seen.append(platform) or real_pull(targets, images, ref, platform, dry_run,
                                                           platforms_of=build_images.registry_platforms))
    assert build_images.main(["--mode", "pull", "--platform", ARM64, "--dry-run", "px4"]) == 1
    assert seen == [ARM64] and "linux/arm64 이미지가 없다" in capsys.readouterr().out


def test_manifest_platforms():
    index = {"mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [
        {"platform": {"os": "linux", "architecture": "amd64"}},
        {"platform": {"os": "linux", "architecture": "arm64", "variant": "v8"}},
        {"platform": {"os": "unknown", "architecture": "unknown"}},
    ]}
    assert build_images.manifest_platforms(index) == {AMD64, ARM64}
    single = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "config": {}}
    assert build_images.manifest_platforms(single, lambda: {"os": "linux", "architecture": "amd64"}) == {AMD64}
    assert build_images.manifest_platforms(single, lambda: {"os": "linux", "architecture": "arm64"}) == {ARM64}
    # attestation만 있는 index, 플랫폼을 읽지 못한 단일 manifest는 빈 집합이다
    only_att = {"mediaType": "application/vnd.oci.image.index.v1+json",
                "manifests": [{"platform": {"os": "unknown", "architecture": "unknown"}}]}
    assert build_images.manifest_platforms(only_att) == set()
    assert build_images.manifest_platforms(single, lambda: {}) == set()


def test_pull_accepts_single_arm64_manifest_on_arm64(monkeypatch, capsys):
    class Done:
        returncode = 0
    monkeypatch.setattr(build_images, "registry_has", lambda ref, strict=False: (True, "manifest 있음"))
    calls = []
    monkeypatch.setattr(build_images.subprocess, "run", lambda cmd, **k: calls.append(cmd) or Done())
    images = image_keys.load_images()
    image_keys.compute(images, _versions())
    rc = build_images.pull_images(["px4"], images, lambda n: f"r/{n}:{images[n].key}", ARM64, False,
                                  platforms_of=lambda ref: {ARM64})
    assert rc == 0 and calls[0][:5] == ["docker", "pull", "--quiet", "--platform", ARM64]


def test_pull_rejects_tag_with_no_platforms(monkeypatch, capsys):
    rc, out, calls = _pull(monkeypatch, capsys, AMD64, set())
    assert rc == 1 and "태그에 있는 플랫폼: 없음" in out and not calls


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
    # 태그에 다른 플랫폼 이미지만 있으면 받지 않는다(emulation으로 돌리지 않는다)
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


def test_dockerfiles_have_no_arch_literals():
    # CI는 amd64만 빌드하므로 Dockerfile에 아키텍처 literal이 생기면 arm64(로컬)만 조용히 깨진다.
    # 아키텍처는 dpkg --print-architecture 등 빌드 시점 값으로 얻는다. 주석 줄은 보지 않는다
    import re
    pat = re.compile(r"amd64|x86_64|aarch64|arm64")
    for img in image_keys.load_images().values():
        path = os.path.join(image_keys.DOCKER_DIR, img.dockerfile)
        with open(path, encoding="utf-8") as f:
            bad = [f"{img.dockerfile}:{i}: {line.strip()}" for i, line in enumerate(f, 1)
                   if not line.lstrip().startswith("#") and pat.search(line)]
        assert not bad, bad
