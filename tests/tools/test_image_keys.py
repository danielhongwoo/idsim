"""tools/ci/image_keys.py의 미러 키 제외와 build_images.py의 환경변수 우선 범위 테스트(초안 devops-engineer, 승인 test-engineer)."""
import os
import sys

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


def test_security_mirror_is_excluded_from_keys():
    v = _versions()
    assert "UBUNTU_APT_SECURITY_MIRROR" in v
    changed = dict(v, UBUNTU_APT_SECURITY_MIRROR="http://security.ubuntu.com/ubuntu")
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
