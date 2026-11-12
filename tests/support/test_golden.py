"""golden.py 단위 테스트. rclpy 없이 돈다.

아래 원문 예시는 ROS 2 Jazzy의 `ros2 topic list -t`와 `ros2 topic info -v`
출력 형식을 기억에 따라 만든 가정이다. 실제 출력은 S4 캡처로 확인해야 한다.
"""
import os

import pytest

from tests.support import golden
from tests.support.px4_topic import fmu_dir

IN, OUT = fmu_dir("in"), fmu_dir("out")   # 표본 문자열의 상대 토픽 접두

TOPIC_LIST = """\
/parameter_events [rcl_interfaces/msg/ParameterEvent]
/px4_1/@IN@offboard_control_mode [px4_msgs/msg/OffboardControlMode]
/px4_1/@OUT@vehicle_status_v4 [px4_msgs/msg/VehicleStatus]
/px4_1/@OUT@battery_status [px4_msgs/msg/BatteryStatus]
/px4_1/@OUT@Zeta [px4_msgs/msg/Zeta]
/px4_2/@OUT@vehicle_status_v4 [px4_msgs/msg/VehicleStatus]
/rosout [rcl_interfaces/msg/Log]
""".replace("@IN@", IN).replace("@OUT@", OUT)

INFO_V = """\
Type: px4_msgs/msg/VehicleStatus

Publisher count: 1

Node name: uxrce_dds_client
Node namespace: /px4_1
Topic type: px4_msgs/msg/VehicleStatus
Topic type hash: RIHS01_0000000000000000000000000000000000000000000000000000000000000000
Endpoint type: PUBLISHER
GID: 01.0f.aa.bb.cc.dd.00.00.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): KEEP_LAST (5)
  Durability: TRANSIENT_LOCAL
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

Subscription count: 1

Node name: probe
Node namespace: /
Topic type: px4_msgs/msg/VehicleStatus
Endpoint type: SUBSCRIPTION
QoS profile:
  Reliability: RELIABLE
  History (Depth): UNKNOWN
  Durability: VOLATILE
"""


def test_normalize_topic_list():
    got = golden.normalize_topic_list(TOPIC_LIST, "px4_1")
    assert got == [
        IN + "offboard_control_mode px4_msgs/msg/OffboardControlMode",
        OUT + "Zeta px4_msgs/msg/Zeta",
        OUT + "battery_status px4_msgs/msg/BatteryStatus",
        OUT + "vehicle_status_v4 px4_msgs/msg/VehicleStatus",
    ]
    assert all(l.startswith("fmu/") for l in got)
    assert not any("px4_2" in l or "rosout" in l for l in got)


def test_normalize_sorted_bytewise_and_slash_namespace():
    got = golden.normalize_topic_list(TOPIC_LIST, "/px4_1/")
    assert got == sorted(got, key=lambda s: s.encode())
    # 대문자는 소문자보다 앞선다(LC_ALL=C)
    assert got.index(OUT + "Zeta px4_msgs/msg/Zeta") < got.index(
        OUT + "battery_status px4_msgs/msg/BatteryStatus")
    assert got[0].startswith(IN)


def test_normalize_empty_namespace():
    raw = "/" + OUT + "a_v1 [px4_msgs/msg/A]\n/other [x/msg/X]\n"
    assert golden.normalize_topic_list(raw, "") == [OUT + "a_v1 px4_msgs/msg/A"]


def test_normalize_qos():
    assert golden.normalize_qos(INFO_V) == {
        "reliability": "BEST_EFFORT",
        "durability": "TRANSIENT_LOCAL",
        "history": "KEEP_LAST",
        "depth": "5",
    }


def test_normalize_qos_unknown_depth_and_no_publisher():
    raw = INFO_V.replace("KEEP_LAST (5)", "UNKNOWN")
    q = golden.normalize_qos(raw)
    assert q["history"] == "UNKNOWN" and q["depth"] == "UNKNOWN"
    with pytest.raises(ValueError):
        golden.normalize_qos("Type: a/msg/A\n\nPublisher count: 0\n")


def test_golden_roundtrip(tmp_path):
    topics = golden.normalize_topic_list(TOPIC_LIST, "px4_1")
    qos = {OUT + "vehicle_status_v4": golden.normalize_qos(INFO_V)}
    env = {"PX4_TAG": "v1.17.0", "PX4_MSGS_REF": "abc", "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
           "XRCE_AGENT_TAG": "v2.4.3"}
    d = str(tmp_path / "g")
    golden.write_golden(d, topics, qos, env)
    assert open(os.path.join(d, "topics.txt")).read().endswith("\n")
    t2, q2, e2 = golden.read_golden(d)
    assert (t2, q2, e2) == (topics, qos, env)
    with pytest.raises(ValueError):
        golden.write_golden(d, topics, qos, {"PX4_TAG": "x"})


def test_golden_dir(tmp_path):
    p = tmp_path / "versions.env"
    p.write_text('# c\nGZ_RELEASE=harmonic\nPX4_TAG="v1.17.0"\n')
    assert golden.golden_dir("/r", str(p)) == "/r/tests/fixtures/px4/v1.17.0"
    p.write_text("A=1\n")
    with pytest.raises(ValueError):
        golden.golden_dir("/r", str(p))


def test_compare_subset():
    gold = [(OUT + "vehicle_status_v4", "px4_msgs/msg/VehicleStatus"),
            (OUT + "battery_status", "px4_msgs/msg/BatteryStatus")]
    ok = [(OUT + "battery_status", "px4_msgs/msg/BatteryStatus")]
    assert golden.compare_subset(ok, gold) == ([], {})
    exp = [(OUT + "vehicle_status_v3", "px4_msgs/msg/VehicleStatus"),
           (OUT + "nothing", "px4_msgs/msg/N")]
    missing, cand = golden.compare_subset(exp, gold)
    assert missing == sorted(exp)
    assert cand[exp[0]] == [gold[0]]
    assert cand[exp[1]] == []


# ---- normalize CLI ----
from tests.support import normalize  # noqa: E402


def _raw(tmp_path):
    raw = tmp_path / "raw"
    (raw / "topic_info" / "fmu" / "out").mkdir(parents=True)
    (raw / "topic_info" / "fmu" / "in").mkdir(parents=True)
    (raw / "topic_list.txt").write_text(TOPIC_LIST)
    (raw / "topic_info" / "fmu" / "out" / "vehicle_status_v4.txt").write_text(INFO_V)
    (raw / "topic_info" / "fmu" / "in" / "offboard_control_mode.txt").write_text(
        "Type: a/msg/A\n\nPublisher count: 0\n")
    (raw / "env_raw.txt").write_text(
        "PX4_TAG=v1.17.0\nPX4_MSGS_REF=abc\nRMW_IMPLEMENTATION=rmw_cyclonedds_cpp\n"
        "XRCE_AGENT_TAG=v2.4.3\nSPEED=1\n")
    return str(raw)


def test_normalize_cli(tmp_path, capsys):
    raw, out = _raw(tmp_path), str(tmp_path / "g")
    assert normalize.main(["--raw", raw, "--ns", "px4_1", "--out", out]) == 0
    assert IN + "offboard_control_mode" in capsys.readouterr().err
    topics, qos, env = golden.read_golden(out)
    assert len(topics) == 4 and list(qos) == [OUT + "vehicle_status_v4"]
    assert list(env) == list(golden.ENV_KEYS)
    # 이미 있으면 실패
    assert normalize.main(["--raw", raw, "--ns", "px4_1", "--out", out]) == 1
    assert normalize.main(["--raw", raw, "--ns", "px4_1", "--out", out, "--update"]) == 0
    # check: 같으면 0, 다르면 1과 diff
    assert normalize.main(["--raw", raw, "--ns", "px4_1", "--out", out, "--check"]) == 0
    with open(os.path.join(out, "topics.txt"), "a") as f:
        f.write(OUT + "extra_v1 px4_msgs/msg/Extra\n")
    capsys.readouterr()
    assert normalize.main(["--raw", raw, "--ns", "px4_1", "--out", out, "--check"]) == 1
    assert "extra_v1" in capsys.readouterr().out
