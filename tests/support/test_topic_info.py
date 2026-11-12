"""topic_info.py 단위 테스트. ros2 출력 형식은 Jazzy 기준 가정(test_golden.py 참조)."""
import argparse
import io
import subprocess

import pytest

from tests.support import topic_info
from tests.support.px4_topic import fmu_dir
from tests.support.test_golden import INFO_V, TOPIC_LIST

OUT = fmu_dir("out")


def test_parse():
    r = topic_info.parse_topic_info(INFO_V)
    assert r["type"] == "px4_msgs/msg/VehicleStatus"
    assert (r["publisher_count"], r["subscription_count"]) == (1, 1)
    assert [e["kind"] for e in r["endpoints"]] == ["PUBLISHER", "SUBSCRIPTION"]


def test_find_and_judge():
    f = topic_info.find_topics(TOPIC_LIST, "/" + OUT + r"vehicle_status(_v\d+)?$")
    assert f == [("/px4_1/" + OUT + "vehicle_status_v4", "px4_msgs/msg/VehicleStatus"),
                 ("/px4_2/" + OUT + "vehicle_status_v4", "px4_msgs/msg/VehicleStatus")]
    info = topic_info.parse_topic_info(INFO_V)
    assert topic_info.judge(info, 1, 1, "px4_msgs/msg/VehicleStatus") == []
    assert len(topic_info.judge(info, 2, None, "x/msg/X")) == 2


def _args(**kw):
    d = dict(regex="px4_1/" + OUT + "vehicle_status", expect_publishers=1,
             expect_subscriptions=None, expect_type=None, save=None, ns="", timeout=0.0)
    d.update(kw)
    return argparse.Namespace(**d)


def _runner(cmd):
    return TOPIC_LIST if cmd[2] == "list" else INFO_V


def test_run_codes(tmp_path):
    out = io.StringIO()
    assert topic_info.run(_args(save=str(tmp_path), ns="px4_1"), runner=_runner, out=out) == 0
    assert (tmp_path / (OUT + "vehicle_status_v4.txt")).read_text() == INFO_V
    assert topic_info.run(_args(expect_publishers=2), runner=_runner, out=out) == 1
    assert topic_info.run(_args(regex="nomatch"), runner=_runner, out=out) == 2


def test_global_topic_without_ns_prefix(tmp_path):
    """/clock처럼 네임스페이스 밖 토픽도 --ns가 있어도 저장 경로가 이름 그대로가 된다."""
    clock_list = "/clock [rosgraph_msgs/msg/Clock]\n"
    clock_info = INFO_V.replace("px4_msgs/msg/VehicleStatus", "rosgraph_msgs/msg/Clock")
    runner = lambda cmd: clock_list if cmd[2] == "list" else clock_info  # noqa: E731
    out = io.StringIO()
    args = _args(regex="^/clock$", expect_type="rosgraph_msgs/msg/Clock", save=str(tmp_path), ns="px4_1")
    assert topic_info.run(args, runner=runner, out=out) == 0
    assert (tmp_path / "clock.txt").read_text() == clock_info


def test_info_unknown_topic_is_retried():
    calls = {"info": 0}
    t = {"now": 0.0}

    def runner(cmd):
        if cmd[2] == "list":
            return TOPIC_LIST
        calls["info"] += 1
        if calls["info"] < 3:
            raise subprocess.CalledProcessError(1, cmd)
        return INFO_V

    def sleep(dt):
        t["now"] += dt

    rc = topic_info.run(_args(timeout=10.0), runner=runner, clock=lambda: t["now"],
                        sleep=sleep, out=io.StringIO())
    assert rc == 0 and calls["info"] == 3


def test_info_unknown_topic_raises_after_timeout():
    def runner(cmd):
        if cmd[2] == "list":
            return TOPIC_LIST
        raise subprocess.CalledProcessError(1, cmd)

    with pytest.raises(subprocess.CalledProcessError):
        topic_info.run(_args(timeout=0.0), runner=runner, out=io.StringIO())
