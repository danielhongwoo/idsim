"""stack.py 단위 테스트. 예시 JSON은 스키마 초안(ros2-engineer, 2026-11-09)의 6.1, 6.2절 그대로다."""
import json
from pathlib import Path

import pytest

from tests.support import stack as stk

K0_STANDALONE = r'''{
  "generated_at": "2026-11-09T09:00:00Z",
  "generator": {
    "git_commit": "4a09524000000000000000000000000000000000",
    "git_dirty": false,
    "script": "tools/gen_compose.py",
    "version": 1
  },
  "images": {
    "lichtblick": null,
    "px4": "idsim/px4:local",
    "ros_ws": "idsim/ros-ws:local",
    "sim_base": "idsim/sim-base:local",
    "xrce_agent": "idsim/xrce-agent:local"
  },
  "inputs": {
    "fleet": {
      "path": "config/fleet.yaml",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "px4_params_file": {
      "path": "config/px4/sitl_params.env",
      "sha256": "20f48202767f80e6126fc0548dd7effa3d4197a27c894f772ba6c46dac9ff31a"
    },
    "versions_env": {
      "path": "docker/versions.env",
      "sha256": "96778161ff35a05bc39200d241068ccd0e9ef78f8ddd284290b795cb90f24ad5"
    }
  },
  "px4": {
    "start": "parallel"
  },
  "run": {
    "compose_file": "compose.yaml",
    "host_dir": "/home/daniel/idsim/artifacts/runs/20261109-090000-k0",
    "id": "20261109-090000-k0",
    "ros_log_dir": "ros_log"
  },
  "schema": 1,
  "services": {
    "agent": "xrce-agent",
    "bridge": "bridge",
    "foxglove": null,
    "gazebo": "gazebo",
    "gz_gui": "gz-gui",
    "lichtblick": null,
    "profiles": {
      "tools": ["runner"],
      "viz": ["gz-gui"]
    },
    "px4": ["px4-1"],
    "runner": "runner"
  },
  "stack": {
    "agent_port": 8888,
    "agent_port_hex": "22B8",
    "compose_project": "idsim-0",
    "dds": {
      "cyclonedds_uri": "file:///opt/idsim/config/cyclonedds.xml",
      "participant_index_max": 50,
      "port_base": 12400,
      "port_last": 12649,
      "rmw_implementation": "rmw_cyclonedds_cpp"
    },
    "foxglove_port": 8765,
    "gz_ip": "127.0.0.1",
    "gz_partition": "idsim-0",
    "index": 0,
    "lichtblick_port": 18080,
    "mavlink_gcs_remote": 14550,
    "mavlink_offset": 0,
    "ros_domain_id": 20,
    "viz_bind": "127.0.0.1"
  },
  "startup": {
    "model_precheck": true,
    "stages": [
      ["xrce-agent", "gazebo"],
      ["px4-1"],
      ["bridge"]
    ]
  },
  "user": {
    "gid": 1000,
    "uid": 1000
  },
  "variant": "standalone",
  "vehicles": [
    {
      "airframe": "4001_gz_x500",
      "autostart": 4001,
      "derived_params": {
        "MAV_SYS_ID": "2",
        "SYS_AUTOSTART": "4001",
        "UXRCE_DDS_DOM_ID": "20",
        "UXRCE_DDS_KEY": "2"
      },
      "expected_params": {
        "COM_DISARM_PRFLT": "-1.0",
        "COM_OBL_RC_ACT": "4",
        "COM_OF_LOSS_T": "1.0",
        "COM_RC_IN_MODE": "4",
        "NAV_DLL_ACT": "0",
        "SDLOG_MODE": "2"
      },
      "gz_model_name": "x500_1",
      "host_rootfs_dir": "/home/daniel/idsim/artifacts/runs/20261109-090000-k0/px4-1",
      "id": 1,
      "instance": 1,
      "mavlink": {
        "api_local": 14581,
        "api_remote": 14541,
        "gcs_local": 18571,
        "gcs_remote": 14550
      },
      "ns": "/px4_1",
      "pose": {
        "x": 0.0,
        "y": 0.0,
        "yaw": 0.0,
        "z": 0.0
      },
      "px4_ns": "px4_1",
      "rootfs_dir": "px4-1",
      "service": "px4-1",
      "sim_model": "gz_x500",
      "sysid": 2,
      "ulog_dir": "px4-1/log",
      "uxrce_key": 2
    }
  ],
  "world": {
    "file": "/opt/px4-gz/worlds/default.sdf",
    "name": "default",
    "origin": {
      "alt": 38.0,
      "lat": 37.5665,
      "lon": 126.978
    },
    "speed_factor": null
  }
}
'''

K1_EMBEDDED = r'''{
  "generated_at": "2026-11-09T09:00:05Z",
  "generator": {
    "git_commit": "4a09524000000000000000000000000000000000",
    "git_dirty": false,
    "script": "tools/gen_compose.py",
    "version": 1
  },
  "images": {
    "lichtblick": null,
    "px4": "idsim/px4:local",
    "ros_ws": "idsim/ros-ws:local",
    "sim_base": "idsim/sim-base:local",
    "xrce_agent": "idsim/xrce-agent:local"
  },
  "inputs": {
    "fleet": {
      "path": "config/fleet.yaml",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "px4_params_file": {
      "path": "config/px4/sitl_params.env",
      "sha256": "20f48202767f80e6126fc0548dd7effa3d4197a27c894f772ba6c46dac9ff31a"
    },
    "versions_env": {
      "path": "docker/versions.env",
      "sha256": "96778161ff35a05bc39200d241068ccd0e9ef78f8ddd284290b795cb90f24ad5"
    }
  },
  "px4": {
    "start": "parallel"
  },
  "run": {
    "compose_file": "compose.yaml",
    "host_dir": "/home/daniel/idsim/artifacts/runs/20261109-090005-k1",
    "id": "20261109-090005-k1",
    "ros_log_dir": "ros_log"
  },
  "schema": 1,
  "services": {
    "agent": "xrce-agent",
    "bridge": null,
    "foxglove": null,
    "gazebo": null,
    "gz_gui": null,
    "lichtblick": null,
    "profiles": {
      "tools": ["runner"],
      "viz": []
    },
    "px4": ["px4-1"],
    "runner": "runner"
  },
  "stack": {
    "agent_port": 8889,
    "agent_port_hex": "22B9",
    "compose_project": "idsim-1",
    "dds": {
      "cyclonedds_uri": "file:///opt/idsim/config/cyclonedds.xml",
      "participant_index_max": 50,
      "port_base": 12650,
      "port_last": 12899,
      "rmw_implementation": "rmw_cyclonedds_cpp"
    },
    "foxglove_port": 8766,
    "gz_ip": "127.0.0.1",
    "gz_partition": "idsim-1",
    "index": 1,
    "lichtblick_port": 18081,
    "mavlink_gcs_remote": 15550,
    "mavlink_offset": 1000,
    "ros_domain_id": 21,
    "viz_bind": "127.0.0.1"
  },
  "startup": {
    "model_precheck": false,
    "stages": [
      ["xrce-agent"],
      ["px4-1"]
    ]
  },
  "user": {
    "gid": 1000,
    "uid": 1000
  },
  "variant": "embedded",
  "vehicles": [
    {
      "airframe": "4001_gz_x500",
      "autostart": 4001,
      "derived_params": {
        "MAV_SYS_ID": "2",
        "SYS_AUTOSTART": "4001",
        "UXRCE_DDS_DOM_ID": "21",
        "UXRCE_DDS_KEY": "2"
      },
      "expected_params": {
        "COM_DISARM_PRFLT": "-1.0",
        "COM_OBL_RC_ACT": "4",
        "COM_OF_LOSS_T": "1.0",
        "COM_RC_IN_MODE": "4",
        "NAV_DLL_ACT": "0",
        "SDLOG_MODE": "2"
      },
      "gz_model_name": "x500_1",
      "host_rootfs_dir": "/home/daniel/idsim/artifacts/runs/20261109-090005-k1/px4-1",
      "id": 1,
      "instance": 1,
      "mavlink": {
        "api_local": 15581,
        "api_remote": 15541,
        "gcs_local": 19571,
        "gcs_remote": 15550
      },
      "ns": "/px4_1",
      "pose": {
        "x": 0.0,
        "y": 0.0,
        "yaw": 0.0,
        "z": 0.0
      },
      "px4_ns": "px4_1",
      "rootfs_dir": "px4-1",
      "service": "px4-1",
      "sim_model": "gz_x500",
      "sysid": 2,
      "ulog_dir": "px4-1/log",
      "uxrce_key": 2
    }
  ],
  "world": {
    "file": "/opt/px4-gz/worlds/default.sdf",
    "name": "default",
    "origin": null,
    "speed_factor": null
  }
}
'''


def _write(tmp_path, text, sub="artifacts/runs/20261109-090000-k0"):
    d = tmp_path / sub
    d.mkdir(parents=True)
    p = d / "stack.json"
    p.write_text(text, encoding="utf-8")
    return p


def _mutate(text, fn):
    d = json.loads(text)
    fn(d)
    return json.dumps(d)


def test_load_standalone(tmp_path):
    s = stk.load(_write(tmp_path, K0_STANDALONE))
    assert s.schema == 1 and s.variant == "standalone"
    assert (s.run_id, s.compose_project, s.ros_domain_id) == ("20261109-090000-k0", "idsim-0", 20)
    assert (s.stack_index, s.gz_partition) == (0, "idsim-0")
    assert s.rmw_implementation == "rmw_cyclonedds_cpp"
    assert s.cyclonedds_uri.startswith("file://")
    assert s.world_name == "default" and s.speed_factor is None
    assert s.world_origin == {"lat": 37.5665, "lon": 126.978, "alt": 38.0}
    assert s.service("gazebo") == "gazebo" and s.services["px4"] == ["px4-1"]
    assert s.startup_stages == [["xrce-agent", "gazebo"], ["px4-1"], ["bridge"]]
    assert s.namespaces == ["/px4_1"]
    v = s.vehicles[0]
    assert (v.id, v.instance, v.ns, v.px4_ns, v.sysid) == (1, 1, "/px4_1", "px4_1", 2)
    assert (v.service, v.gz_model_name, v.pose["yaw"]) == ("px4-1", "x500_1", 0.0)
    assert v.expected_params["COM_DISARM_PRFLT"] == "-1.0"
    assert v.derived_params["MAV_SYS_ID"] == "2"
    assert v.mavlink["gcs_local"] == 18571


def test_load_embedded(tmp_path):
    s = stk.load(_write(tmp_path, K1_EMBEDDED, "artifacts/runs/20261109-090005-k1"))
    assert s.variant == "embedded" and s.compose_project == "idsim-1" and s.ros_domain_id == 21
    assert s.world_origin is None
    assert s.services["gazebo"] is None and s.services["bridge"] is None
    with pytest.raises(stk.StackError, match="gazebo"):
        s.service("gazebo")
    assert s.vehicles[0].ns == "/px4_1" and s.vehicles[0].sysid == 2


def test_vehicle_lookup(tmp_path):
    s = stk.load(_write(tmp_path, K0_STANDALONE))
    assert s.vehicle_by_id(1) is s.vehicles[0]
    assert s.vehicle_by_ns("/px4_1") is s.vehicles[0]
    with pytest.raises(stk.StackLookupError):
        s.vehicle_by_id(2)
    # 빗금을 보정하지 않는다(식별자 변형 금지)
    with pytest.raises(LookupError):
        s.vehicle_by_ns("px4_1")


def test_resolve_paths(tmp_path):
    p = _write(tmp_path, K0_STANDALONE)
    s = stk.load(p)
    d = p.parent
    assert s.dir == d
    assert s.ros_log_dir == d / "ros_log"
    assert s.compose_file == d / "compose.yaml"
    v = s.vehicles[0]
    assert s.ulog_path(v) == d / "px4-1" / "log"
    assert s.rootfs_path(v) == d / "px4-1"
    # host_ 필드는 풀지 않고 그대로
    assert v.host_rootfs_dir.startswith("/home/daniel/")
    assert str(s.host_dir).endswith("20261109-090000-k0")
    with pytest.raises(stk.StackError):
        s.resolve("/etc/passwd")
    with pytest.raises(stk.StackError):
        s.resolve("../other")


def test_resolve_same_in_other_mount(tmp_path):
    # 호스트와 컨테이너가 다른 마운트 지점이어도 같은 상대 경로가 그대로 동작한다
    a = stk.load(_write(tmp_path / "a", K0_STANDALONE))
    b = stk.load(_write(tmp_path / "b", K0_STANDALONE))
    assert a.ulog_path(a.vehicles[0]).relative_to(a.dir) == b.ulog_path(b.vehicles[0]).relative_to(b.dir)


def test_load_from_env(tmp_path):
    p = _write(tmp_path, K0_STANDALONE)
    s = stk.load_from_env({stk.ENV_VAR: str(p)})
    assert s.run_id == "20261109-090000-k0"
    with pytest.raises(stk.StackError, match=stk.ENV_VAR):
        stk.load_from_env({})


@pytest.mark.parametrize("path", [
    ["run", "id"], ["stack", "ros_domain_id"], ["stack", "dds", "cyclonedds_uri"],
    ["world", "origin"], ["world", "speed_factor"], ["generator", "git_commit"],
    ["services", "gazebo"], ["images", "lichtblick"], ["startup", "model_precheck"],
    ["vehicles", 0, "ns"], ["vehicles", 0, "sysid"], ["vehicles", 0, "pose", "yaw"],
    ["vehicles", 0, "expected_params"], ["user", "uid"], ["generated_at"],
])
def test_missing_key_fails_even_if_nullable(path):
    def drop(d):
        for k in path[:-1]:
            d = d[k]
        del d[path[-1]]
    with pytest.raises(stk.StackError, match="필수 필드 누락"):
        stk.loads(_mutate(K0_STANDALONE, drop), "x/stack.json")


def test_missing_origin_subkey_fails():
    def drop(d):
        del d["world"]["origin"]["lat"]
    with pytest.raises(stk.StackError, match="world.origin.lat"):
        stk.loads(_mutate(K0_STANDALONE, drop))


def test_null_allowed_fields():
    def nulls(d):
        d["generator"]["git_commit"] = None
        d["generator"]["git_dirty"] = None
        d["images"]["lichtblick"] = None
        d["world"]["speed_factor"] = None
        d["services"]["foxglove"] = None
    s = stk.loads(_mutate(K0_STANDALONE, nulls))
    assert s.raw["generator"]["git_commit"] is None


def test_null_not_allowed_fields():
    def nul(d):
        d["stack"]["ros_domain_id"] = None
    with pytest.raises(stk.StackError, match="ros_domain_id"):
        stk.loads(_mutate(K0_STANDALONE, nul))


def test_type_mismatch():
    def s2i(d):
        d["stack"]["agent_port"] = "8888"
    with pytest.raises(stk.StackError, match="agent_port"):
        stk.loads(_mutate(K0_STANDALONE, s2i))

    def b2i(d):
        d["vehicles"][0]["sysid"] = True
    with pytest.raises(stk.StackError, match="sysid"):
        stk.loads(_mutate(K0_STANDALONE, b2i))

    def numparam(d):
        d["vehicles"][0]["expected_params"]["NAV_DLL_ACT"] = 0
    with pytest.raises(stk.StackError, match="NAV_DLL_ACT"):
        stk.loads(_mutate(K0_STANDALONE, numparam))


@pytest.mark.parametrize("val", [0, 2, "1", None, True, 1.0])
def test_schema_mismatch(val):
    def setv(d):
        d["schema"] = val
    with pytest.raises(stk.StackError, match="schema"):
        stk.loads(_mutate(K0_STANDALONE, setv), "p/stack.json")


def test_schema_missing_and_error_has_path():
    def drop(d):
        del d["schema"]
    with pytest.raises(stk.StackError, match="p/stack.json"):
        stk.loads(_mutate(K0_STANDALONE, drop), "p/stack.json")


def test_unknown_fields_ignored():
    def add(d):
        d["future_top"] = {"a": 1}
        d["stack"]["new_field"] = 7
        d["vehicles"][0]["new_vehicle_field"] = "x"
        d["world"]["origin"]["datum"] = "wgs84"
    s = stk.loads(_mutate(K0_STANDALONE, add))
    assert s.ros_domain_id == 20 and s.vehicles[0].raw["new_vehicle_field"] == "x"


def test_bad_json_and_unreadable(tmp_path):
    with pytest.raises(stk.StackError, match="JSON"):
        stk.loads("{", "p/stack.json")
    with pytest.raises(stk.StackError, match="읽을 수 없다"):
        stk.load(tmp_path / "none.json")
    with pytest.raises(stk.StackError):
        stk.loads("[]")


def test_empty_vehicles_rejected():
    def clear(d):
        d["vehicles"] = []
    with pytest.raises(stk.StackError, match="vehicles"):
        stk.loads(_mutate(K0_STANDALONE, clear))


# --- 생성기 판 3의 노드 단계 key. 생성기 골든(실제 생성기 출력)으로 읽는다 ---

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gen_compose"


def _golden(name):
    return stk.load(GOLDEN_DIR / name / "stack.json")


def test_node_keys_standalone_golden():
    s = _golden("1대-k0")
    v = s.vehicles[0]
    assert s.generator_version >= 3
    assert v.vehicle_id == "px4_1"
    assert v.executor_node == "/px4_1/mission_executor"
    assert v.params_file == "params/ops-1.yaml"
    assert s.ops_services == ["ops-1"]
    assert s.node_stages == [["ops-1"]]
    assert s.params_dir == s.dir / "params"
    assert s.params_path(v) == s.dir / "params" / "ops-1.yaml"
    assert s.vehicle_by_vehicle_id("px4_1") is v
    assert s.images["ros_ws"]
    assert s.git_commit == s.raw["generator"]["git_commit"]


def test_node_keys_three_vehicles_golden():
    s = _golden("3대-k0")
    assert [v.vehicle_id for v in s.vehicles] == ["px4_1", "px4_2", "px4_3"]
    assert s.ops_services == ["ops-1", "ops-2", "ops-3"]
    assert [s.params_path(v).name for v in s.vehicles] == ["ops-1.yaml", "ops-2.yaml", "ops-3.yaml"]
    with pytest.raises(stk.StackLookupError):
        s.vehicle_by_vehicle_id("px4_9")


def test_node_keys_embedded_golden_is_empty():
    s = _golden("embedded")
    v = s.vehicles[0]
    assert v.vehicle_id == "px4_1"
    assert v.executor_node is None and v.params_file is None
    assert s.ops_services == [] and s.node_stages == []
    assert s.params_dir is None and s.params_path(v) is None


def test_node_keys_required_from_generator_v3():
    d = json.loads((GOLDEN_DIR / "1대-k0" / "stack.json").read_text(encoding="utf-8"))
    for drop in (lambda x: x["vehicles"][0].pop("vehicle_id"),
                 lambda x: x["vehicles"][0].pop("executor_node"),
                 lambda x: x["vehicles"][0].pop("params_file"),
                 lambda x: x["run"].pop("params_dir"),
                 lambda x: x["startup"].pop("node_stages"),
                 lambda x: x["services"].pop("ops")):
        e = json.loads(json.dumps(d))
        drop(e)
        with pytest.raises(stk.StackError, match="필수 필드 누락"):
            stk.loads(json.dumps(e), "x/stack.json")


def test_node_keys_absent_in_old_generator_fail_on_access(tmp_path):
    s = stk.load(_write(tmp_path, K0_STANDALONE))
    assert s.generator_version == 1
    assert s.vehicles[0].vehicle_id is None
    for attr in ("ops_services", "node_stages", "params_dir"):
        with pytest.raises(stk.StackError, match="노드 단계 key가 없다"):
            getattr(s, attr)


# --- 생성기 판 5: world template, 표적, sim_oracle, expect_gps. 예시 JSON을 판 5 모양으로 고쳐 쓴다 ---

_TARGET = {"id": "t1", "start_s": 0.0, "loop": True,
           "waypoints": [{"t": 0.0, "x": 1, "y": 2.5, "z": 3.0}, {"t": 10.0, "x": 4.0, "y": 5.0, "z": 3.0}]}


def _v5(d, standalone=True, targets=()):
    d["generator"]["version"] = 5
    # 판 3의 노드 단계 key도 판 5에서는 필수다
    d["run"]["params_dir"] = "params" if standalone else None
    d["startup"]["node_stages"] = [["ops-1"]] if standalone else []
    d["services"]["ops"] = ["ops-1"] if standalone else []
    for i, v in enumerate(d["vehicles"]):
        v["vehicle_id"] = f"px4_{i + 1}"
        v["params_file"] = f"params/ops-{i + 1}.yaml" if standalone else None
        v["executor_node"] = f"/px4_{i + 1}/mission_executor" if standalone else None
    d["inputs"]["world_template"] = {"path": "ros_ws/src/idsim_sim/worlds/idsim_base.sdf",
                                     "sha256": "b" * 64}
    d["world"]["template"] = "ros_ws/src/idsim_sim/worlds/idsim_base.sdf"
    d["world"]["file"] = "world/default.sdf" if standalone else None
    d["targets"] = [json.loads(json.dumps(t)) for t in targets]
    d["services"]["targets"] = "targets" if targets else None
    d["services"]["sim_oracle"] = "sim-oracle" if standalone else None
    for v in d["vehicles"]:
        v["expect_gps"] = ({"lat": 47.397, "lon": 8.5456, "alt": 488.1} if standalone else None)


def _v5_text(base=K0_STANDALONE, **kw):
    return _mutate(base, lambda d: _v5(d, **kw))


def test_v5_standalone_ok(tmp_path):
    s = stk.load(_write(tmp_path, _v5_text(targets=[_TARGET])))
    assert s.world_template.endswith("idsim_base.sdf")
    assert s.world_file == s.dir / "world" / "default.sdf"
    assert s.targets[0]["id"] == "t1"
    assert s.targets_service == "targets" and s.sim_oracle_service == "sim-oracle"
    assert s.vehicles[0].expect_gps == {"lat": 47.397, "lon": 8.5456, "alt": 488.1}


def test_v5_no_targets_ok(tmp_path):
    s = stk.load(_write(tmp_path, _v5_text()))
    assert s.targets == [] and s.targets_service is None


def test_v5_embedded_nulls_ok(tmp_path):
    s = stk.load(_write(tmp_path, _v5_text(K1_EMBEDDED, standalone=False)))
    assert s.world_file is None and s.sim_oracle_service is None
    assert s.vehicles[0].expect_gps is None


@pytest.mark.parametrize("path", [
    ("inputs", "world_template"), ("world", "template"), ("targets",),
    ("services", "targets"), ("services", "sim_oracle"), ("vehicles", 0, "expect_gps"),
    ("inputs", "world_template", "sha256"),
])
def test_v5_missing_key_fails(path):
    def drop(d):
        _v5(d)
        o = d
        for k in path[:-1]:
            o = o[k]
        del o[path[-1]]
    with pytest.raises(stk.StackError, match="필수 필드 누락"):
        stk.loads(_mutate(K0_STANDALONE, drop), "x/stack.json")


def test_v5_keys_not_required_below_v5():
    def v4(d):
        _v5(d)
        for k in ("targets",):
            del d[k]
        del d["world"]["template"]
        d["generator"]["version"] = 4
    s = stk.loads(_mutate(K0_STANDALONE, v4))
    assert s.generator_version == 4
    for attr in ("world_template", "world_file", "targets", "targets_service", "sim_oracle_service"):
        with pytest.raises(stk.StackError, match="월드와 표적 key가 없다"):
            getattr(s, attr)


def test_v4_world_file_null_rejected():
    def bad(d):
        _v5(d)
        d["generator"]["version"] = 4
        d["world"]["file"] = None
    with pytest.raises(stk.StackError, match="world.file"):
        stk.loads(_mutate(K0_STANDALONE, bad))


@pytest.mark.parametrize("mut,match", [
    (lambda d: d["world"].__setitem__("template", None), "world.template"),
    (lambda d: d.__setitem__("targets", {}), "targets"),
    (lambda d: d["targets"][0].__setitem__("loop", 1), r"targets\[0\].loop"),
    (lambda d: d["targets"][0].__setitem__("start_s", "0"), r"targets\[0\].start_s"),
    (lambda d: d["targets"][0]["waypoints"][1].__setitem__("x", None), r"waypoints\[1\].x"),
    (lambda d: d["targets"][0].pop("waypoints"), r"targets\[0\].waypoints"),
    (lambda d: d["services"].__setitem__("sim_oracle", 3), "sim_oracle"),
    (lambda d: d["vehicles"][0]["expect_gps"].__setitem__("lat", "47"), "expect_gps.lat"),
    (lambda d: d["vehicles"][0]["expect_gps"].pop("alt"), "expect_gps.alt"),
    (lambda d: d["vehicles"][0].__setitem__("expect_gps", []), "expect_gps"),
    (lambda d: d["services"].__setitem__("targets", None), "services.targets"),
    (lambda d: d["world"].__setitem__("file", None), "world.file"),
    (lambda d: d["vehicles"][0].__setitem__("expect_gps", None), r"vehicles\[0\].expect_gps"),
])
def test_v5_type_errors(mut, match):
    def f(d):
        _v5(d, targets=[_TARGET])
        mut(d)
    with pytest.raises(stk.StackError, match=match):
        stk.loads(_mutate(K0_STANDALONE, f))


def test_v5_services_targets_without_targets_rejected():
    def f(d):
        _v5(d)
        d["services"]["targets"] = "targets"
    with pytest.raises(stk.StackError, match="services.targets"):
        stk.loads(_mutate(K0_STANDALONE, f))


def test_v5_embedded_with_world_file_rejected():
    def f(d):
        _v5(d, standalone=False)
        d["world"]["file"] = "world/default.sdf"
    with pytest.raises(stk.StackError, match="world.file"):
        stk.loads(_mutate(K1_EMBEDDED, f))


def test_v5_embedded_with_expect_gps_rejected():
    def f(d):
        _v5(d, standalone=False)
        d["vehicles"][0]["expect_gps"] = {"lat": 1.0, "lon": 2.0, "alt": 3.0}
    with pytest.raises(stk.StackError, match=r"vehicles\[0\].expect_gps"):
        stk.loads(_mutate(K1_EMBEDDED, f))


def test_v5_standalone_second_vehicle_expect_gps_null_rejected():
    def f(d):
        _v5(d)
        d["vehicles"].append(json.loads(json.dumps(d["vehicles"][0])))
        d["vehicles"][1]["expect_gps"] = None
    with pytest.raises(stk.StackError, match=r"vehicles\[1\].expect_gps"):
        stk.loads(_mutate(K0_STANDALONE, f))


# --- 판 5 golden 값 단정(실제 생성기 출력) ---

def test_v5_golden_standalone_one_vehicle():
    s = _golden("1대-k0")
    assert s.generator_version == 5
    assert s.world_template.endswith("world_template.sdf")
    assert s.world_file == s.dir / "world" / "default.sdf"
    assert s.targets == [] and s.targets_service is None and s.sim_oracle_service is None
    assert s.vehicles[0].expect_gps == {"lat": 37.5665, "lon": 126.978, "alt": 38.24}


def test_v5_golden_standalone_three_vehicles():
    s = _golden("3대-k0")
    gps = [v.expect_gps for v in s.vehicles]
    assert all(g is not None for g in gps)
    assert all(g["lon"] == 126.978 for g in gps)
    assert len({g["lat"] for g in gps}) == 3
    assert s.world_file == s.dir / "world" / "default.sdf"


def test_v5_golden_embedded():
    s = _golden("embedded")
    assert s.world_file is None
    assert s.vehicles[0].expect_gps is None
    assert isinstance(s.world_template, str)
    assert s.targets == [] and s.sim_oracle_service is None


@pytest.mark.parametrize("name", ["1대-k0", "3대-k0", "embedded"])
@pytest.mark.parametrize("drop", [("world", "template"), ("targets",), ("services", "sim_oracle"),
                                  ("vehicles", 0, "expect_gps")])
def test_v5_golden_key_removed_fails(name, drop):
    d = json.loads((GOLDEN_DIR / name / "stack.json").read_text(encoding="utf-8"))
    o = d
    for k in drop[:-1]:
        o = o[k]
    del o[drop[-1]]
    with pytest.raises(stk.StackError, match="필수 필드 누락"):
        stk.loads(json.dumps(d), "x/stack.json")
