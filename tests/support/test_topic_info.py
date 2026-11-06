"""topic_info.py 단위 테스트. ros2 출력 형식은 Jazzy 기준 가정(test_golden.py 참조)."""
import argparse
import io

from tests.support import topic_info
from tests.support.test_golden import INFO_V, TOPIC_LIST


def test_parse():
    r = topic_info.parse_topic_info(INFO_V)
    assert r["type"] == "px4_msgs/msg/VehicleStatus"
    assert (r["publisher_count"], r["subscription_count"]) == (1, 1)
    assert [e["kind"] for e in r["endpoints"]] == ["PUBLISHER", "SUBSCRIPTION"]


def test_find_and_judge():
    f = topic_info.find_topics(TOPIC_LIST, r"/fmu/out/vehicle_status(_v\d+)?$")
    assert f == [("/px4_1/fmu/out/vehicle_status_v4", "px4_msgs/msg/VehicleStatus"),
                 ("/px4_2/fmu/out/vehicle_status_v4", "px4_msgs/msg/VehicleStatus")]
    info = topic_info.parse_topic_info(INFO_V)
    assert topic_info.judge(info, 1, 1, "px4_msgs/msg/VehicleStatus") == []
    assert len(topic_info.judge(info, 2, None, "x/msg/X")) == 2


def _args(**kw):
    d = dict(regex=r"px4_1/fmu/out/vehicle_status", expect_publishers=1,
             expect_subscriptions=None, expect_type=None, save=None, ns="", timeout=0.0)
    d.update(kw)
    return argparse.Namespace(**d)


def _runner(cmd):
    return TOPIC_LIST if cmd[2] == "list" else INFO_V


def test_run_codes(tmp_path):
    out = io.StringIO()
    assert topic_info.run(_args(save=str(tmp_path), ns="px4_1"), runner=_runner, out=out) == 0
    assert (tmp_path / "fmu/out/vehicle_status_v4.txt").read_text() == INFO_V
    assert topic_info.run(_args(expect_publishers=2), runner=_runner, out=out) == 1
    assert topic_info.run(_args(regex="nomatch"), runner=_runner, out=out) == 2
