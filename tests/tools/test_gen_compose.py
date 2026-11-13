"""tools/gen_compose.py 단위 테스트(초안 devops-engineer, 승인 test-engineer).

lint 잡의 python 이미지(PyYAML == versions.env의 LINT_PYYAML_VERSION, pytest)에서 저장소 루트를 작업
디렉터리로 `python3 -m pytest tests/tools`로 돈다. docker가 필요 없다(compose config 검사는 lint.sh의
compose-config 항목).

골든: tests/fixtures/gen_compose/<사례>/{fleet.yaml, compose.yaml, stack.json, params/ops-N.yaml}. 사례의
fleet.yaml을 고정 인자로 생성해 실행 디렉터리의 파일 전체(파일 집합과 바이트)와 비교한다. 골든 파일이 없거나
남는 파일이 있으면 실패한다. 빈 디렉터리(px4-N, ros_log/*)는 git이 추적하지 못하므로 render_dirs 테스트가 따로 본다.
갱신은 --update-golden(저장소를 쓰기 가능하게 마운트한 환경에서):
  python3 -m pytest tests/tools --update-golden -p no:cacheprovider
diff는 리뷰에서 본다. 고정 인자 중 versions_env의 sha256만 상수로 둔다(도구 버전 줄을 고칠 때마다
골든이 바뀌지 않게). 나머지 입력 sha256은 실제 파일 값이다.
"""
import copy
import hashlib
import json
import math
import os
import re
import xml.etree.ElementTree as ET

import pytest

from tests.support import stack as stk
from tools import gen_compose as gc

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GOLDEN_DIR = os.path.join(REPO, "tests", "fixtures", "gen_compose")
GOLDEN_CASES = {
    # 사례 이름: (k, variant)
    "1대-k0": (0, "standalone"),
    "1대-k3": (3, "standalone"),
    "3대-k0": (0, "standalone"),
    "embedded": (0, "embedded"),
}
HOST_REPO = "/work/idsim"
LICHTBLICK_IMAGE = "ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:" + "1" * 64
FIXED = {
    "uid": 1000,
    "gid": 1000,
    "generated_at": "2026-11-09T09:00:00Z",
    "git_commit": "0" * 40,
    "git_dirty": False,
    "versions_env_sha256": "0" * 64,
    "cyclonedds_xml_sha256": "0" * 64,
}

FIXTURE_TEMPLATE = "tests/fixtures/gen_compose/world_template.sdf"
REAL_TEMPLATE = "ros_ws/src/idsim_sim/worlds/idsim_base.sdf"

BASE_FLEET = {
    "schema": 2,
    "world": {
        "name": "default",
        "template": FIXTURE_TEMPLATE,
        "origin": {"lat": 37.5665, "lon": 126.978, "alt": 38},
        "speed_factor": None,
    },
    "vehicles": [{"id": 1, "airframe": "4001_gz_x500",
                  "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}, "px4_params": {}}],
    "targets": [],
    "px4": {"params_file": "config/px4/sitl_params.env", "start": "parallel"},
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


PARAMS_ENV = gc.parse_params_env(_read(os.path.join(REPO, "config/px4/sitl_params.env")))
PMAX = gc.parse_participant_max(_read(os.path.join(REPO, gc.CYCLONEDDS_REL)))


def fleet(**changes):
    """BASE_FLEET 사본을 고친다. 키는 __로 이은 경로(world__origin), 값이 DELETE면 그 키를 지운다."""
    f = copy.deepcopy(BASE_FLEET)
    for path, value in changes.items():
        keys = path.split("__")
        obj = f
        for key in keys[:-1]:
            obj = obj[int(key)] if key.isdigit() else obj[key]
        last = int(keys[-1]) if keys[-1].isdigit() else keys[-1]
        if value is DELETE:
            del obj[last]
        else:
            obj[last] = value
    return f


DELETE = object()


def three_vehicles():
    f = fleet()
    f["vehicles"] = [{"id": n, "airframe": "4001_gz_x500",
                      "pose": {"x": 0.0, "y": 4.0 * (n - 1), "z": 0.0, "yaw": 0.0}, "px4_params": {}}
                     for n in (1, 2, 3)]
    return f


def make_ctx(k=0, variant="standalone", run_id=None, fleet_path="config/fleet.yaml", fleet_sha="a" * 64):
    run_id = run_id or f"20261109-090000-k{k}"
    return {
        "k": k,
        "variant": variant,
        "uid": FIXED["uid"],
        "gid": FIXED["gid"],
        "run_id": run_id,
        "host_repo_root": HOST_REPO,
        "host_run_dir": f"{HOST_REPO}/artifacts/runs/{run_id}",
        "images": gc.resolve_images("local", None, None),
        "generated_at": FIXED["generated_at"],
        "git_commit": FIXED["git_commit"],
        "git_dirty": FIXED["git_dirty"],
        "inputs": {
            "fleet": {"path": fleet_path, "sha256": fleet_sha},
            "px4_params_file": {"path": "config/px4/sitl_params.env",
                                "sha256": gc._sha256_file(os.path.join(REPO, "config/px4/sitl_params.env"))},
            "versions_env": {"path": gc.VERSIONS_ENV_REL, "sha256": FIXED["versions_env_sha256"]},
            "cyclonedds_xml": {"path": gc.CYCLONEDDS_REL, "sha256": FIXED["cyclonedds_xml_sha256"]},
            "world_template": {"path": FIXTURE_TEMPLATE, "sha256": "b" * 64},
        },
        "params_env": PARAMS_ENV,
        "participant_index_max": PMAX,
        "lichtblick_image": LICHTBLICK_IMAGE,
    }


def gen(f=None, **ctx_kw):
    norm, warnings = gc.validate_fleet(copy.deepcopy(BASE_FLEET if f is None else f))
    compose, stack, more = gc.build(norm, make_ctx(**ctx_kw))
    return compose, stack, warnings + more


def gen_world(f=None, template=FIXTURE_TEMPLATE):
    """fleet의 월드 SDF 본문(build_world_sdf). 템플릿은 저장소 파일이다."""
    norm, _ = gc.validate_fleet(copy.deepcopy(BASE_FLEET if f is None else f))
    return gc.build_world_sdf(norm, _read(os.path.join(REPO, template)))


# ------------------------------------------------------------------ 골든
def _golden_build(case):
    k, variant = GOLDEN_CASES[case]
    rel = f"tests/fixtures/gen_compose/{case}/fleet.yaml"
    path = os.path.join(REPO, rel)
    norm, _ = gc.validate_fleet(gc.load_yaml(_read(path)))
    ctx = make_ctx(k=k, variant=variant, fleet_path=rel, fleet_sha=gc._sha256_file(path))
    ctx["inputs"]["world_template"]["sha256"] = gc._sha256_file(os.path.join(REPO, FIXTURE_TEMPLATE))
    compose, stack, _ = gc.build(norm, ctx)
    world_sdf = None if stack["world"]["file"] is None else gc.build_world_sdf(norm, _read(os.path.join(REPO, FIXTURE_TEMPLATE)))
    return compose, stack, world_sdf


def _golden_outputs(case):
    """{상대 경로: 본문}. 실행 디렉터리에 생기는 파일 전체(생성기의 render_files)."""
    return gc.render_files(*_golden_build(case))


def _golden_files(case_dir):
    """골든 디렉터리의 파일 집합(입력 fleet.yaml 제외). 상대 경로는 /로 쓴다."""
    out = set()
    for root, _, names in os.walk(case_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), case_dir).replace(os.sep, "/")
            if rel != "fleet.yaml":
                out.add(rel)
    return out


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden(case, request):
    case_dir = os.path.join(GOLDEN_DIR, case)
    assert os.path.isfile(os.path.join(case_dir, "fleet.yaml")), f"골든 입력 없음: {case_dir}/fleet.yaml"
    outputs = _golden_outputs(case)
    update = request.config.getoption("--update-golden", default=False)
    changed = []
    if update:
        # 내용이 바뀐 파일만 쓴다(git diff가 실제 변경만 보이게). 쓴 사례는 통과가 아니라 skip으로 표시한다
        for rel, text in sorted(outputs.items()):
            path = os.path.join(case_dir, rel)
            if not os.path.isfile(path) or _read(path) != text:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                changed.append(rel)
        for rel in sorted(_golden_files(case_dir) - set(outputs)):
            os.remove(os.path.join(case_dir, rel))
            changed.append(f"{rel}(삭제)")
        for root, dirs, names in os.walk(case_dir, topdown=False):
            if root != case_dir and not dirs and not names:
                os.rmdir(root)
        if changed:
            pytest.skip(f"골든 갱신: {case}/{', '.join(changed)} (git diff로 검토한다)")
        return
    assert _golden_files(case_dir) == set(outputs), \
        f"골든 파일 집합 불일치: 없음 {sorted(set(outputs) - _golden_files(case_dir))}, " \
        f"남음 {sorted(_golden_files(case_dir) - set(outputs))} (의도한 변경이면 --update-golden)"
    for rel, text in sorted(outputs.items()):
        assert _read(os.path.join(case_dir, rel)) == text, f"골든 불일치: {case}/{rel} (의도한 변경이면 --update-golden)"


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden_has_no_fmu_strings(case):
    """생성 파일 어디에도 /fmu 토픽 문자열이 없다(토픽 이름은 idsim_common 안에서만 쓴다)."""
    for rel, text in _golden_outputs(case).items():
        assert "fmu/" not in text, (case, rel)


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden_stack_loads_with_support_loader(case):
    """교차 테스트: 골든 stack.json을 tests.support.stack 로더가 받는다(test-engineer 합의)."""
    path = os.path.join(GOLDEN_DIR, case, "stack.json")
    s = stk.load(path)
    k, variant = GOLDEN_CASES[case]
    assert s.stack_index == k and s.variant == variant
    assert s.compose_project == f"idsim-{k}"
    assert [v.service for v in s.vehicles] == s.services["px4"]
    assert s.run_id == s.raw["run"]["id"] and s.compose_file.name == "compose.yaml"
    assert s.startup_stages == s.raw["startup"]["stages"]
    assert os.path.basename(s.raw["run"]["host_dir"]) == s.run_id
    if variant == "embedded":
        assert s.startup_stages[-1] == [s.vehicles[-1].service]
    else:
        px4 = [v.service for v in s.vehicles]
        assert s.startup_stages == [["xrce-agent", "gazebo"], px4, ["bridge"]]
    # 6단계 key: 기존 로더는 모르는 필드를 무시하고, 새 key는 원본 dict로 읽힌다
    for v in s.vehicles:
        assert v.raw["vehicle_id"] == v.ns[1:]
        if variant == "embedded":
            assert v.raw["params_file"] is None and v.raw["executor_node"] is None
            assert s.services["ops"] == [] and s.raw["startup"]["node_stages"] == []
        else:
            assert v.raw["params_file"] == f"params/ops-{v.id}.yaml"
            assert v.raw["executor_node"] == f"{v.ns}/mission_executor"
            assert s.services["ops"] == [f"ops-{x.id}" for x in s.vehicles]
            node = s.services["ops"] + (["targets"] if s.raw["targets"] else [])
            assert s.raw["startup"]["node_stages"] == [node]
            assert (s.raw["services"]["targets"] == "targets") == bool(s.raw["targets"])
            assert s.raw["run"]["params_dir"] == "params"
    assert [t["id"] for t in s.raw["targets"]] == (["target_a", "target_b"] if case == "3대-k0" else [])
    assert s.vehicle_by_ns(s.vehicles[0].ns) is s.vehicles[0]
    assert s.vehicles[0].ns == "/" + s.vehicles[0].px4_ns
    assert s.service("agent") == "xrce-agent" and s.service("runner") == "runner"
    for role in ("gazebo", "bridge", "gz_gui"):
        if variant == "embedded":
            with pytest.raises(stk.StackError):
                s.service(role)
        else:
            assert s.service(role)
    assert s.world_origin is None if variant == "embedded" else s.world_origin is not None
    for v in s.vehicles:
        assert all(isinstance(x, float) for x in v.pose.values())
    if s.world_origin is not None:
        assert all(isinstance(x, float) for x in s.world_origin.values())


# ------------------------------------------------------------------ 성질
ALL_GENERATED = [
    pytest.param(dict(), id="1대-k0"),
    pytest.param(dict(k=3), id="1대-k3"),
    pytest.param(dict(k=9), id="1대-k9"),
    pytest.param(dict(f=three_vehicles()), id="3대-k0"),
    pytest.param(dict(f=three_vehicles(), k=7), id="3대-k7"),
    pytest.param(dict(variant="embedded"), id="embedded"),
]


def _all_strings(obj):
    return list(gc._strings(obj))


@pytest.mark.parametrize("kw", ALL_GENERATED)
def test_properties(kw):
    k = kw.get("k", 0)
    compose, stack, _ = gen(**kw)
    services = compose["services"]
    text = gc.dump_compose(compose)
    assert compose["name"] == f"idsim-{k}"
    # host 네트워크, restart no
    for name, s in services.items():
        assert s["network_mode"] == "host", name
        assert s["restart"] == "no", name
    # viz 격리: 본 스택 서비스는 viz 서비스에 의존하지 않는다
    viz = {n for n, s in services.items() if "viz" in s.get("profiles", [])}
    for name, s in services.items():
        if name not in viz:
            assert not (viz & set(s.get("depends_on", {}))), name
    # ${...:?} 없음, 보간은 viz 서비스의 허용 목록뿐
    assert ":?" not in text
    for name, s in services.items():
        for t in _all_strings(s):
            for item in gc.interpolations(t):
                assert name in viz and item in gc.ALLOWED_INTERPOLATIONS, (name, t)
    # 에이전트: 16진수 포트, 도메인 없음
    agent = services["xrce-agent"]
    assert f"{8888 + k:04X}" in agent["healthcheck"]["test"][1]
    assert agent["command"] == ["udp4", "-p", str(8888 + k)]
    assert "environment" not in agent
    # 도메인 일치
    for name, s in services.items():
        env = s.get("environment") or {}
        if "ROS_DOMAIN_ID" in env:
            assert env["ROS_DOMAIN_ID"] == str(20 + k), name
        if "GZ_PARTITION" in env:
            assert env["GZ_PARTITION"] == f"idsim-{k}", name
    # px4-1..N 개수
    n = len(stack["vehicles"])
    assert sorted(x for x in services if x.startswith("px4-")) == [f"px4-{i}" for i in range(1, n + 1)]
    # 중첩 마운트 없음, 바인드는 긴 형식이고 원본 자동 생성 끔
    for name, s in services.items():
        targets = [v["target"] for v in s.get("volumes", [])]
        for a in targets:
            for b in targets:
                assert a == b or not b.startswith(a.rstrip("/") + "/"), (name, a, b)
        for v in s.get("volumes", []):
            assert v["type"] == "bind" and v["bind"]["create_host_path"] is False
    # px4: 볼륨은 rootfs/N 하나, 호스트 uid:gid, HOME=/tmp, MAVLink 오프셋
    for v in stack["vehicles"]:
        s = services[v["service"]]
        assert s["user"] == "1000:1000"
        assert s["environment"]["HOME"] == "/tmp"
        assert s["environment"]["IDSIM_MAVLINK_OFFSET"] == str(1000 * k)
        assert [x["target"] for x in s["volumes"]] == [f"{gc.PX4_ROOTFS}/{v['id']}"]
        assert not any(key.startswith("PX4_HOME_") for key in s["environment"])
        assert "MAV_SYS_ID" not in s["environment"]
    # 호스트에 쓰는 서비스만 사용자, agent와 gazebo는 root
    assert "user" not in agent
    if "gazebo" in services:
        assert "user" not in services["gazebo"]
    for name in ["bridge", "runner", "gz-gui"] + [f"ops-{i}" for i in range(1, n + 1)]:
        if name in services:
            assert services[name]["user"] == "1000:1000"
    # 러너는 tools 프로필, 단계에는 프로필 서비스가 없다
    assert services["runner"]["profiles"] == ["tools"]
    for stage in stack["startup"]["stages"]:
        for name in stage:
            assert not services[name].get("profiles")
    gc.assert_invariants(compose, stack)


def test_standalone_services_and_healthchecks():
    compose, stack, _ = gen()
    s = compose["services"]
    assert list(s) == ["xrce-agent", "gazebo", "px4-1", "bridge", "ops-1", "runner", "gz-gui", "foxglove", "lichtblick"]
    hc = s["gazebo"]["healthcheck"]["test"][1]
    assert hc == ('gz service -i --service /world/default/scene/info | grep -q "Service providers"'
                  " && test -f /tmp/idsim/ready")
    env = s["gazebo"]["environment"]
    assert env["IDSIM_WORLD_NAME"] == "default" and env["IDSIM_WORLD_FILE"] == "/opt/idsim/world/default.sdf"
    assert not [k for k in env if k.startswith("IDSIM_ORIGIN")]
    assert [(v["source"], v["target"], v["read_only"]) for v in s["gazebo"]["volumes"]] == [
        ("/work/idsim/ros_ws/src/idsim_sim", "/opt/idsim/sim", True),
        ("/work/idsim/artifacts/runs/20261109-090000-k0/world", "/opt/idsim/world", True)]
    assert s["px4-1"]["healthcheck"]["test"][1] == \
        "px4-uxrce_dds_client --instance 1 status | grep -q 'Running, connected'"
    assert s["px4-1"]["depends_on"] == {"xrce-agent": {"condition": "service_healthy"},
                                        "gazebo": {"condition": "service_healthy"}}
    assert s["px4-1"]["environment"]["PX4_GZ_STANDALONE"] == "1"
    b = s["bridge"]["healthcheck"]
    assert (b["interval"], b["start_interval"]) == ("30s", "5s") and "start_period" in b
    assert s["bridge"]["environment"]["ROS_LOG_DIR"].endswith("/ros_log/bridge")
    gui = s["gz-gui"]
    assert gui["ipc"] == "host" and "healthcheck" not in gui
    assert gui["depends_on"] == {"gazebo": {"condition": "service_healthy"}}
    assert gui["environment"]["DISPLAY"] == "${DISPLAY:-}"
    assert gui["environment"]["HOME"] == "/tmp/gz-home"
    assert {v["source"] for v in gui["volumes"]} >= {"${XAUTHORITY:-/dev/null}", "/tmp/.X11-unix"}
    for name in gc.GUI_PASS_ENV:
        assert gui["environment"][name] is None
    assert s["runner"]["environment"]["IDSIM_STACK_FILE"] == \
        "/opt/idsim/artifacts/runs/20261109-090000-k0/stack.json"
    assert stack["startup"]["stages"] == [["xrce-agent", "gazebo"], ["px4-1"], ["bridge"]]
    assert stack["startup"]["node_stages"] == [["ops-1"]]
    assert s["runner"]["depends_on"] == {"ops-1": {"condition": "service_healthy"}}


def test_viz_foxglove_and_lichtblick():
    compose, stack, _ = gen(f=three_vehicles(), k=2)
    s = compose["services"]
    fox, lb = s["foxglove"], s["lichtblick"]
    for svc in (fox, lb):
        assert svc["profiles"] == ["viz"] and "healthcheck" not in svc and svc["network_mode"] == "host"
    cmd = fox["command"]
    assert cmd[:4] == ["ros2", "run", "foxglove_bridge", "foxglove_bridge"]
    params = {a.partition(":=")[0]: a.partition(":=")[2] for a in cmd if ":=" in a}
    assert params["address"] == "127.0.0.1" and params["port"] == "8767"
    assert params["capabilities"] == "[connectionGraph]"
    assert params["topic_whitelist"] == "['^/px4_1/.*', '^/px4_2/.*', '^/px4_3/.*']"
    for key in ("client_topic_whitelist", "service_whitelist", "param_whitelist"):
        assert params[key] == "['^$$']"
    assert params["use_sim_time"] == "true" and "best_effort_qos_topic_whitelist" not in params
    assert fox["init"] is True and fox["user"] == "1000:1000"
    assert fox["depends_on"] == {"bridge": {"condition": "service_healthy"}}
    assert lb["image"] == LICHTBLICK_IMAGE and "user" not in lb and "depends_on" not in lb
    assert lb["command"] == ["caddy", "file-server", "--listen", "127.0.0.1:18082"]
    assert stack["services"]["foxglove"] == "foxglove" and stack["services"]["lichtblick"] == "lichtblick"
    assert stack["images"]["lichtblick"] == LICHTBLICK_IMAGE
    assert stack["services"]["profiles"]["viz"] == ["gz-gui", "foxglove", "lichtblick"]
    # 본 스택 서비스는 viz 서비스에 의존하지 않는다
    assert not {"foxglove", "lichtblick"} & {d for n, x in s.items() if n not in ("foxglove", "lichtblick", "gz-gui")
                                             for d in x.get("depends_on", {})}


def test_embedded_variant():
    compose, stack, warnings = gen(variant="embedded")
    s = compose["services"]
    assert set(s) == {"xrce-agent", "px4-1", "runner"}
    env = s["px4-1"]["environment"]
    assert env["HEADLESS"] == "1" and "PX4_GZ_STANDALONE" not in env
    assert s["px4-1"]["depends_on"] == {"xrce-agent": {"condition": "service_healthy"}}
    assert s["runner"]["depends_on"] == {"px4-1": {"condition": "service_healthy"}}
    assert stack["world"]["origin"] is None and stack["world"]["file"] is None
    assert stack["world"]["template"] == FIXTURE_TEMPLATE
    assert stack["vehicles"][0]["expect_gps"] is None
    assert any("origin" in w for w in warnings) and any("world.template" in w for w in warnings)
    for role in ("gazebo", "bridge", "gz_gui", "foxglove", "lichtblick"):
        assert role in stack["services"] and stack["services"][role] is None
    # 노드 서비스는 만들지 않는다(embedded에는 /clock bridge가 없다)
    assert stack["services"]["ops"] == []
    assert not [n for n in s if n.startswith("ops-")]
    assert gc.render_files(compose, stack).keys() == {"compose.yaml", "stack.json"}
    assert stack["startup"] == {"stages": [["xrce-agent"], ["px4-1"]], "node_stages": [],
                                "model_precheck": False}
    assert stack["services"]["profiles"] == {"tools": ["runner"], "viz": []}


def test_sequential_start_chains_px4():
    f = three_vehicles()
    f["px4"]["start"] = "sequential"
    compose, _, _ = gen(f)
    s = compose["services"]
    assert s["px4-2"]["depends_on"]["px4-1"] == {"condition": "service_healthy"}
    assert s["px4-3"]["depends_on"]["px4-2"] == {"condition": "service_healthy"}
    assert "px4-2" not in s["px4-1"]["depends_on"]
    compose, _, _ = gen(three_vehicles())
    assert "px4-1" not in compose["services"]["px4-2"]["depends_on"]
    assert set(compose["services"]["bridge"]["depends_on"]) == {"px4-1", "px4-2", "px4-3"}


def test_vehicle_derivations_and_params():
    f = three_vehicles()
    f["vehicles"][1]["px4_params"] = {"COM_OBL_RC_ACT": 1, "MPC_XY_VEL_MAX": 7.5}
    compose, stack, warnings = gen(f, k=2)
    v2 = stack["vehicles"][1]
    assert (v2["id"], v2["instance"], v2["ns"], v2["px4_ns"], v2["sysid"], v2["uxrce_key"]) == \
        (2, 2, "/px4_2", "px4_2", 3, 3)
    assert (v2["autostart"], v2["sim_model"], v2["gz_model_name"]) == (4001, "gz_x500", "x500_2")
    assert v2["mavlink"] == {"gcs_remote": 16550, "gcs_local": 20572, "api_remote": 16542, "api_local": 16582}
    assert v2["expected_params"]["COM_OBL_RC_ACT"] == "1"
    assert v2["expected_params"]["MPC_XY_VEL_MAX"] == "7.5"
    assert v2["derived_params"] == {"MAV_SYS_ID": "3", "UXRCE_DDS_KEY": "3",
                                    "UXRCE_DDS_DOM_ID": "22", "SYS_AUTOSTART": "4001"}
    env = compose["services"]["px4-2"]["environment"]
    assert env["PX4_PARAM_COM_OBL_RC_ACT"] == "1"
    assert env["PX4_GZ_MODEL_POSE"] == "0.0,4.0,0.0,0,0,0.0"
    assert any("COM_OBL_RC_ACT" in w for w in warnings)
    assert "PX4_PARAM_MPC_XY_VEL_MAX" not in compose["services"]["px4-1"]["environment"]


def test_port_plan_all_stacks_pairwise():
    ranges = gc.check_port_plan(PMAX)
    assert len(ranges) == 10 * (5 + 3 * 9)
    gc.check_port_plan(gc.PARTICIPANT_INDEX_LIMIT)
    with pytest.raises(gc.FleetError):
        gc.check_port_plan(gc.PARTICIPANT_INDEX_LIMIT + 1)
    assert PMAX == 50


def test_stack_json_matches_compose_and_formats():
    compose, stack, _ = gen(k=4)
    st = stack["stack"]
    assert (st["ros_domain_id"], st["agent_port"], st["agent_port_hex"]) == (24, 8892, "22BC")
    assert (st["mavlink_offset"], st["mavlink_gcs_remote"], st["foxglove_port"], st["lichtblick_port"]) == \
        (4000, 18550, 8769, 18084)
    assert (st["dds"]["port_base"], st["dds"]["port_last"]) == (13400, 13649)
    text = gc.dump_stack(stack)
    assert text.endswith("\n") and text.isascii()
    assert json.loads(text) == stack
    # 같은 입력이면 같은 출력
    assert gc.dump_compose(gen(k=4)[0]) == gc.dump_compose(compose)


@pytest.mark.parametrize("kw", ALL_GENERATED)
def test_dump_compose_round_trips(kw):
    """긴 문자열은 yamllint 줄 길이를 위해 접어 쓰므로, 다시 읽으면 원래 dict와 같아야 한다."""
    compose, _, _ = gen(**kw)
    assert gc.load_yaml(gc.dump_compose(compose)) == compose


def test_dump_compose_has_no_anchor_and_quotes_strings():
    text = gc.dump_compose(gen(three_vehicles())[0])
    assert "&id" not in text and "*id" not in text
    assert "restart: 'no'" in text


# ------------------------------------------------------------------ ops-N 성질(decisions.md 쟁점 2)
OPS_CASES = [
    pytest.param(dict(), id="1대-k0"),
    pytest.param(dict(k=9), id="1대-k9"),
    pytest.param(dict(f=three_vehicles()), id="3대-k0"),
    pytest.param(dict(f=three_vehicles(), k=7), id="3대-k7"),
]


@pytest.mark.parametrize("kw", OPS_CASES)
def test_resident_ros_ws_services_have_init(kw):
    """성질 1: 상주 ros-ws 서비스(bridge, ops-N)와 xrce-agent는 init: true. 1회 실행용 runner도 명시해서 init: true."""
    compose, stack, _ = gen(**kw)
    services = compose["services"]
    ros_ws = stack["images"]["ros_ws"]
    resident = [n for n, svc in services.items() if svc["image"] == ros_ws and not svc.get("profiles")]
    assert resident == ["bridge"] + stack["services"]["ops"]
    for name in resident + ["xrce-agent", "runner"]:
        assert services[name]["init"] is True, name


@pytest.mark.parametrize("kw", OPS_CASES)
def test_ops_stop_signal_and_grace(kw):
    """성질 2: ops-N은 SIGINT로 멈추고 유예 10 s. bridge 등 ros2 run 서비스에는 stop_signal을 두지 않는다."""
    compose, stack, _ = gen(**kw)
    for name in stack["services"]["ops"]:
        assert compose["services"][name]["stop_signal"] == "SIGINT", name
        assert compose["services"][name]["stop_grace_period"] == "10s", name
    for name, svc in compose["services"].items():
        if name not in stack["services"]["ops"]:
            assert "stop_signal" not in svc, name


@pytest.mark.parametrize("kw", OPS_CASES)
def test_ops_params_have_identity_only(kw):
    """성질 3: params는 /** 아래 use_sim_time과 vehicle.id, ns, sysid뿐이다. lifecycle. key와 튜닝 값이 없다."""
    compose, stack, _ = gen(**kw)
    files = gc.render_files(compose, stack, gen_world(kw.get("f")))
    for v in stack["vehicles"]:
        text = files[v["params_file"]]
        doc = gc.load_yaml(text)
        assert list(doc) == ["/**"] and list(doc["/**"]) == ["ros__parameters"]
        assert doc["/**"]["ros__parameters"] == {
            "use_sim_time": True, "vehicle.id": v["vehicle_id"], "vehicle.ns": v["ns"], "vehicle.sysid": v["sysid"]}
        assert "lifecycle" not in text.split("\n", 2)[2] and "command_source" not in text.split("\n", 2)[2]
        assert not [ln for ln in text.splitlines() if ln.lstrip().startswith("lifecycle.")]
    assert set(files) == {"compose.yaml", "stack.json", "world/default.sdf"} | {v["params_file"] for v in stack["vehicles"]}


@pytest.mark.parametrize("kw", OPS_CASES)
def test_ops_healthcheck_names_executor_node(kw):
    """성질 4: healthcheck의 노드 FQN, launch 인자 executor_name, stack.json executor_node가 한 상수에서 나온다."""
    compose, stack, _ = gen(**kw)
    for v in stack["vehicles"]:
        ops = compose["services"][f"ops-{v['id']}"]
        fqn = v["executor_node"]
        assert fqn == f"{v['ns']}/{gc.EXECUTOR_NODE_NAME}"
        assert gc.EXECUTOR_NODE_NAME == "mission_executor"
        probe = ops["healthcheck"]["test"][1]
        assert f"ros2 lifecycle get --no-daemon {fqn} " in probe
        assert probe.count(fqn) == 1 and "/px4_" not in probe.replace(fqn, "")
        assert f"executor_name:={gc.EXECUTOR_NODE_NAME}" in ops["command"]
        assert f"namespace:={v['ns']}" in ops["command"]
        hc = ops["healthcheck"]
        assert (hc["interval"], hc["timeout"], hc["retries"], hc["start_period"], hc["start_interval"]) == \
            ("10s", "10s", 2, "20s", "2s")
        assert "timeout 8 " in probe and "ROS_LOG_DIR=/tmp/hc" in probe and "cat /tmp/hc.out" in probe


def test_ops_service_details():
    compose, stack, _ = gen(f=three_vehicles(), k=2)
    s = compose["services"]
    assert list(s) == ["xrce-agent", "gazebo", "px4-1", "px4-2", "px4-3", "bridge", "ops-1", "ops-2", "ops-3",
                       "runner", "gz-gui", "foxglove", "lichtblick"]
    ops = s["ops-2"]
    assert ops["command"] == ["ros2", "launch", "idsim_mission", "vehicle_ops.launch.py", "namespace:=/px4_2",
                              "executor_name:=mission_executor",
                              "params_file:=/opt/idsim/artifacts/runs/20261109-090000-k2/params/ops-2.yaml"]
    assert ops["environment"]["ROS_LOG_DIR"].endswith("/ros_log/ops-2")
    assert ops["environment"]["ROS_DOMAIN_ID"] == "22" and "GZ_PARTITION" not in ops["environment"]
    assert ops["restart"] == "no" and ops["network_mode"] == "host"
    assert ops["depends_on"] == {"bridge": {"condition": "service_healthy"},
                                 "px4-2": {"condition": "service_healthy"}}
    assert s["runner"]["depends_on"] == {f"ops-{i}": {"condition": "service_healthy"} for i in (1, 2, 3)}
    assert stack["startup"]["node_stages"] == [["ops-1", "ops-2", "ops-3"]]
    assert stack["services"]["ops"] == ["ops-1", "ops-2", "ops-3"]
    for v in stack["vehicles"]:
        assert v["vehicle_id"] == v["ns"][1:] == v["px4_ns"]
        assert v["params_file"] == f"params/ops-{v['id']}.yaml"
    assert stack["run"]["params_dir"] == "params"
    assert stack["generator"]["version"] == 5


def test_render_dirs():
    compose, stack, _ = gen(f=three_vehicles())
    assert gc.render_dirs(compose, stack) == ["px4-1", "px4-2", "px4-3", "ros_log/bridge", "ros_log/ops-1",
                                              "ros_log/ops-2", "ros_log/ops-3", "ros_log/foxglove", "ros_log/runner"]
    compose, stack, _ = gen(variant="embedded")
    assert gc.render_dirs(compose, stack) == ["px4-1", "ros_log/runner"]


def test_assert_invariants_catches_ops_tampering():
    norm, _ = gc.validate_fleet(fleet())
    for mutate in (
        lambda c, st: c["services"]["ops-1"].update(init=False),
        lambda c, st: c["services"]["bridge"].pop("init"),
        lambda c, st: c["services"]["xrce-agent"].pop("init"),
        lambda c, st: c["services"]["runner"].pop("init"),
        lambda c, st: c["services"]["ops-1"].update(stop_signal="SIGTERM"),
        lambda c, st: c["services"]["ops-1"].update(stop_grace_period="30s"),
        lambda c, st: st["vehicles"][0].update(executor_node="/px4_1/other"),
        lambda c, st: st["vehicles"][0].update(vehicle_id="px4_2"),
        lambda c, st: c["services"]["runner"].update(depends_on={"bridge": {"condition": "service_healthy"}}),
        lambda c, st: st["startup"].update(node_stages=[]),
    ):
        compose, stack, _ = gc.build(norm, make_ctx())
        mutate(compose, stack)
        with pytest.raises(gc.FleetError, match="단정 실패"):
            gc.assert_invariants(compose, stack)


# ------------------------------------------------------------------ 거부
REJECT_FLEETS = [
    pytest.param(fleet(vehicles__0__id=0), id="id-0"),
    pytest.param(fleet(vehicles__0__id=10), id="id-10"),
    pytest.param(fleet(vehicles__0__id=True), id="id-bool"),
    pytest.param(fleet(world__origin={"lat": 37.0, "lon": 127.0}), id="origin-partial"),
    pytest.param(fleet(world__origin={"lat": 95.0, "lon": 127.0, "alt": 0}), id="origin-range"),
    pytest.param(fleet(world__origin={"lat": "37", "lon": 127.0, "alt": 0}), id="origin-str"),
    pytest.param(fleet(targets=[{"id": "t1"}]), id="targets-nonempty"),
    pytest.param(fleet(world__speed_factor=2.0), id="speed-factor"),
    pytest.param(fleet(stack={"index": 1}), id="unknown-top-stack"),
    pytest.param(fleet(viz={}), id="unknown-top-viz"),
    pytest.param(fleet(world__home={"lat": 1}), id="unknown-world-key"),
    pytest.param(fleet(vehicles__0__model="x500"), id="unknown-vehicle-key"),
    pytest.param(fleet(vehicles__0__namespace="/px4_1"), id="derived-key-namespace"),
    pytest.param(fleet(vehicles__0__pose__roll=0.0), id="unknown-pose-key"),
    pytest.param(fleet(vehicles__0__pose__yaw=DELETE), id="pose-missing"),
    pytest.param(fleet(px4__params=1), id="unknown-px4-key"),
    pytest.param(fleet(px4__start="random"), id="px4-start"),
    pytest.param(fleet(vehicles__0__airframe="4002_gz_x500_depth"), id="airframe"),
    pytest.param(fleet(schema=1), id="schema-1"),
    pytest.param(fleet(schema=3), id="schema-3"),
    pytest.param(fleet(schema=True), id="schema-bool"),
    pytest.param(fleet(vehicles=[]), id="no-vehicles"),
    pytest.param(fleet(world__name="bad name"), id="world-name"),
    pytest.param(fleet(world__file="/opt/px4-gz/worlds/default.sdf"), id="world-file-key"),
    pytest.param(fleet(world__origin=DELETE), id="origin-missing"),
    pytest.param(fleet(world__origin=None), id="origin-null"),
    pytest.param(fleet(world__origin=[1, 2, 3]), id="origin-list"),
    pytest.param(fleet(world__template=DELETE), id="template-missing"),
    pytest.param(fleet(world__template=None), id="template-null"),
    pytest.param(fleet(world__template="/abs/world.sdf"), id="template-absolute"),
    pytest.param(fleet(world__template="../world.sdf"), id="template-dotdot"),
    pytest.param(fleet(world__template="a/../../world.sdf"), id="template-dotdot-inner"),
    pytest.param(fleet(world__template="worlds/base.world"), id="template-not-sdf"),
    pytest.param(fleet(world__template="worlds//base.sdf"), id="template-empty-component"),
    pytest.param(fleet(world__template="worlds/ba se.sdf"), id="template-space"),
    pytest.param(fleet(vehicles__0__px4_params={"com_obl_rc_act": 1}), id="param-lowercase"),
    pytest.param(fleet(vehicles__0__px4_params={"A_VERY_LONG_PARAM_X": 1}), id="param-too-long"),
    pytest.param(fleet(vehicles__0__px4_params={"COM_OBL_RC_ACT": True}), id="param-bool"),
    pytest.param(fleet(vehicles__0__px4_params={"COM_OBL_RC_ACT": None}), id="param-null"),
    pytest.param(fleet(vehicles__0__px4_params={"COM_OBL_RC_ACT": "4 5"}), id="param-space"),
] + [pytest.param(fleet(vehicles__0__px4_params={p: 1}), id=f"forbidden-{p}") for p in gc.FORBIDDEN_PARAMS]


@pytest.mark.parametrize("f", REJECT_FLEETS)
def test_rejects(f):
    with pytest.raises(gc.FleetError):
        gc.validate_fleet(f)


def test_rejects_duplicate_id():
    f = three_vehicles()
    f["vehicles"][2]["id"] = 1
    with pytest.raises(gc.FleetError, match="중복"):
        gc.validate_fleet(f)


def test_pose_spacing_reject_and_warn():
    f = three_vehicles()
    f["vehicles"][1]["pose"]["y"] = 1.9
    with pytest.raises(gc.FleetError, match="간격"):
        gc.validate_fleet(f)
    f["vehicles"][1]["pose"]["y"] = 3.0
    _, warnings = gc.validate_fleet(f)
    assert any("간격" in w for w in warnings)
    _, warnings = gc.validate_fleet(three_vehicles())
    assert not warnings


@pytest.mark.parametrize("raw", ["10", "-1", "a", "", "01"])
def test_rejects_stack_index(raw):
    with pytest.raises(gc.FleetError):
        gc.stack_index(raw, {})


def test_stack_index_precedence():
    assert gc.stack_index(None, {}) == 0
    assert gc.stack_index(None, {"IDSIM_STACK_INDEX": "4"}) == 4
    assert gc.stack_index("2", {"IDSIM_STACK_INDEX": "4"}) == 2


@pytest.mark.parametrize("k", [-1, 10, True])
def test_build_rejects_k(k):
    norm, _ = gc.validate_fleet(fleet())
    ctx = make_ctx()
    ctx["k"] = k
    with pytest.raises(gc.FleetError):
        gc.build(norm, ctx)


def test_embedded_rejects_two_vehicles():
    norm, _ = gc.validate_fleet(three_vehicles())
    with pytest.raises(gc.FleetError, match="embedded"):
        gc.build(norm, make_ctx(variant="embedded"))


def test_run_dir_must_be_inside_repo():
    norm, _ = gc.validate_fleet(fleet())
    ctx = make_ctx()
    ctx["host_run_dir"] = "/tmp/run"
    with pytest.raises(gc.FleetError, match="저장소"):
        gc.build(norm, ctx)


def test_load_yaml_rejects_duplicate_keys():
    with pytest.raises(gc.FleetError, match="중복"):
        gc.load_yaml("schema: 2\nschema: 2\n")


@pytest.mark.parametrize("text", [
    "PX4_PARAM_MAV_SYS_ID=3\n",
    "PX4_PARAM_COM_OBL_RC_ACT=4 # 주석\n",
    "FOO=1\n",
    "# 주석만\n",
    "PX4_PARAM_A=1\nPX4_PARAM_A=2\n",
])
def test_params_env_rejects(text):
    with pytest.raises(gc.FleetError):
        gc.parse_params_env(text)


def test_image_overrides():
    imgs = gc.resolve_images("abc", "ghcr.io/o/idsim", ["px4=ghcr.io/o/idsim/px4:k1"])
    assert imgs["ros-ws"] == "ghcr.io/o/idsim/ros-ws:abc" and imgs["px4"] == "ghcr.io/o/idsim/px4:k1"
    with pytest.raises(gc.FleetError):
        gc.resolve_images("local", None, ["gateway=x"])


def test_no_user_lookup_in_repo_code():
    """저장소 코드는 사용자 이름을 조회하지 않는다(passwd에 없는 uid에서 깨진다)."""
    bad = re.compile(r"\b(import\s+(getpass|pwd)|from\s+(getpass|pwd)\s+import|getpwuid|getuser\()")
    for rel in ("tools/gen_compose.py",):
        assert not bad.search(_read(os.path.join(REPO, rel))), rel


def test_print_gcs_port(capsys):
    assert gc.main(["--print-gcs-port", "1"]) == 0
    assert capsys.readouterr().out.strip() == "15550"


# ------------------------------------------------------------------ run.host_dir 불변식(build 수준)
@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden_host_dir_invariant(case):
    k, variant = GOLDEN_CASES[case]
    rel = f"tests/fixtures/gen_compose/{case}/fleet.yaml"
    norm, _ = gc.validate_fleet(gc.load_yaml(_read(os.path.join(REPO, rel))))
    _, stack, _ = gc.build(norm, make_ctx(k=k, variant=variant, fleet_path=rel))
    run = stack["run"]
    assert run["host_dir"] == HOST_REPO + "/artifacts/runs/" + run["id"]
    assert os.path.basename(run["host_dir"]) == run["id"]


def test_build_rejects_basename_mismatch():
    norm, _ = gc.validate_fleet(fleet())
    ctx = make_ctx()
    ctx["run_id"] = "other-id"
    with pytest.raises(gc.FleetError, match="run id"):
        gc.build(norm, ctx)


@pytest.mark.parametrize("parent", [
    "",
    "/artifacts/x",
    "/artifacts/runs/a",
])
def test_build_rejects_wrong_parent(parent):
    norm, _ = gc.validate_fleet(fleet())
    ctx = make_ctx()
    ctx["host_run_dir"] = f"{HOST_REPO}{parent}/{ctx['run_id']}"
    with pytest.raises(gc.FleetError, match="artifacts/runs"):
        gc.build(norm, ctx)


def test_assert_invariants_catches_tampered_host_dir():
    norm, _ = gc.validate_fleet(fleet())
    compose, stack, _ = gc.build(norm, make_ctx())
    gc.assert_invariants(compose, stack)
    stack["run"]["host_dir"] = f"{HOST_REPO}/artifacts/runs/tampered"
    with pytest.raises(gc.FleetError):
        gc.assert_invariants(compose, stack)


def test_runner_stack_file_path_uses_run_id():
    compose, stack, _ = gen(run_id="abc-1")
    assert compose["services"]["runner"]["environment"]["IDSIM_STACK_FILE"] == \
        "/opt/idsim/artifacts/runs/abc-1/stack.json"
    assert stack["run"]["id"] == "abc-1"


# ------------------------------------------------------------------ generate(CLI) 수준
def _cli(tmp_path, *extra, out=True, k="0"):
    argv = ["--repo-root", REPO, "--host-repo-root", HOST_REPO, "--stack", k,
            "--generated-at", FIXED["generated_at"], "--uid", "1000", "--gid", "1000",
            "--git-commit", "0" * 40, "--git-dirty", "false"]
    out_dir = tmp_path / "out"
    if out:
        argv += ["--out-dir", str(out_dir)]
    return gc.main(argv + list(extra)), out_dir


def _stack_of(out_dir):
    with open(out_dir / "stack.json", encoding="utf-8") as f:
        return json.load(f)


def test_cli_run_dir_only(tmp_path, capsys):
    rd = f"{HOST_REPO}/artifacts/runs/myrun"
    rc, out = _cli(tmp_path, "--run-dir", rd)
    assert rc == 0 and capsys.readouterr().out.strip() == rd
    st = _stack_of(out)
    assert st["run"]["id"] == "myrun" and st["run"]["host_dir"] == rd


def test_cli_writes_params_and_log_dirs(tmp_path):
    rc, out = _cli(tmp_path, "--run-id", "tree")
    assert rc == 0
    assert sorted(os.listdir(out)) == ["compose.yaml", "params", "px4-1", "ros_log", "stack.json", "world"]
    assert os.listdir(out / "world") == ["default.sdf"]
    assert os.listdir(out / "params") == ["ops-1.yaml"]
    assert sorted(os.listdir(out / "ros_log")) == ["bridge", "foxglove", "ops-1", "runner"]
    assert _read(str(out / "params" / "ops-1.yaml")) == gc.render_ops_params(_stack_of(out)["vehicles"][0])


def test_cli_run_id_only(tmp_path):
    rc, out = _cli(tmp_path, "--run-id", "idonly")
    assert rc == 0
    st = _stack_of(out)
    assert st["run"]["id"] == "idonly"
    assert st["run"]["host_dir"] == f"{HOST_REPO}/artifacts/runs/idonly"


def test_cli_run_dir_and_id_match(tmp_path):
    rd = f"{HOST_REPO}/artifacts/runs/same"
    rc, out = _cli(tmp_path, "--run-dir", rd, "--run-id", "same")
    assert rc == 0 and _stack_of(out)["run"]["id"] == "same"


def test_cli_run_dir_and_id_mismatch_rejected(tmp_path, capsys):
    rd = f"{HOST_REPO}/artifacts/runs/aaa"
    rc, out = _cli(tmp_path, "--run-dir", rd, "--run-id", "bbb")
    assert rc == 1
    assert "gen_compose: 실패" in capsys.readouterr().err
    assert not out.exists() or not os.listdir(out)


def test_cli_default_run_id_pattern(tmp_path):
    rc, out = _cli(tmp_path, k="3")
    assert rc == 0
    st = _stack_of(out)
    assert re.fullmatch(r"[0-9]{8}-[0-9]{6}-k3", st["run"]["id"])
    assert os.path.basename(st["run"]["host_dir"]) == st["run"]["id"]


def test_cli_trailing_slash_run_dir(tmp_path):
    rc, out = _cli(tmp_path, "--run-dir", f"{HOST_REPO}/artifacts/runs/slash/")
    assert rc == 0
    st = _stack_of(out)
    assert st["run"]["id"] == "slash"
    assert st["run"]["host_dir"] == f"{HOST_REPO}/artifacts/runs/slash"


def test_cli_inputs_sha256_match_real_files(tmp_path):
    rc, out = _cli(tmp_path, "--run-id", "hash")
    assert rc == 0
    inputs = _stack_of(out)["inputs"]
    assert set(inputs) >= {"fleet", "versions_env", "px4_params_file", "cyclonedds_xml", "world_template"}
    assert inputs["world_template"]["path"] == _stack_of(out)["world"]["template"] == REAL_TEMPLATE
    for name in ("fleet", "versions_env", "px4_params_file", "cyclonedds_xml", "world_template"):
        real = hashlib.sha256(open(os.path.join(REPO, inputs[name]["path"]), "rb").read()).hexdigest()
        assert inputs[name]["sha256"] == real, name


# ------------------------------------------------------------------ 월드 SDF 생성(decisions.md 쟁점 2)
SDF_OPEN = '<?xml version="1.0" encoding="UTF-8"?>\n<sdf version="1.9">\n'


def _sdf(world_body, world_open='<world name="x">'):
    return f"{SDF_OPEN}  {world_open}\n{world_body}\n  </world>\n</sdf>\n"


def _world_children(text):
    root = ET.fromstring(text)
    return root, next(c for c in root if c.tag == "world")


def test_world_sdf_has_origin_name_and_keeps_comments():
    f = fleet(world__name="idsim_world", world__origin={"lat": 37.5665, "lon": 126.978, "alt": 38})
    text = gen_world(f)
    root, world = _world_children(text)
    assert world.get("name") == "idsim_world"
    scs = [c for c in world if c.tag == "spherical_coordinates"]
    assert len(scs) == 1 and world[-1] is scs[0]
    got = {c.tag: c.text for c in scs[0]}
    assert got == {"surface_model": "EARTH_WGS84", "world_frame_orientation": "ENU", "latitude_deg": "37.5665",
                   "longitude_deg": "126.978", "elevation": "38", "heading_deg": "0"}
    assert [c.tag for c in world if c.tag in ("plugin", "actor", "include")] == []
    assert "주석은 생성 결과에 그대로 남는다" in text and "생성기 golden 전용 월드 템플릿" in text
    assert text.isascii() is False  # 한글 주석이 그대로 남는다(문자 집합 규칙은 한글과 아스키)
    assert any(line.startswith('  <world name="idsim_world">') for line in text.splitlines())  # wrapper는 줄 단위로 읽는다
    assert 'name="fixture_placeholder"' not in text
    # 같은 입력이면 같은 출력
    assert gen_world(f) == text


def test_world_sdf_values_follow_fleet_origin():
    f = fleet(world__origin={"lat": -33.8688, "lon": 151.2093, "alt": 12.5})
    _, world = _world_children(gen_world(f))
    sc = next(c for c in world if c.tag == "spherical_coordinates")
    got = {c.tag: c.text for c in sc}
    assert (float(got["latitude_deg"]), float(got["longitude_deg"]), float(got["elevation"])) == (-33.8688, 151.2093, 12.5)
    assert got["heading_deg"] == "0" and got["world_frame_orientation"] == "ENU" and got["surface_model"] == "EARTH_WGS84"


@pytest.mark.parametrize("body, match", [
    pytest.param("    <plugin name='a' filename='b'/>", "plugin", id="plugin"),
    pytest.param("    <spherical_coordinates><latitude_deg>1</latitude_deg></spherical_coordinates>",
                 "spherical_coordinates", id="spherical"),
    pytest.param("    <actor name='t1'/>", "actor", id="actor"),
    pytest.param("    <include><uri>model://x</uri></include>", "include", id="include"),
])
def test_template_rejects_forbidden_world_children(body, match):
    with pytest.raises(gc.FleetError, match=match):
        gc.parse_world_template(_sdf(body))


@pytest.mark.parametrize("text, match", [
    pytest.param(SDF_OPEN + "</sdf>\n", "정확히 하나", id="no-world"),
    pytest.param(SDF_OPEN + '  <world name="a"/>\n  <world name="b"/>\n</sdf>\n', "정확히 하나", id="two-worlds"),
    pytest.param(SDF_OPEN + '  <model name="m"><world name="inner"/></model>\n</sdf>\n', "정확히 하나", id="nested-world"),
    pytest.param('<?xml version="1.0"?>\n<root><world name="a"/></root>\n', "sdf가 아니다", id="root"),
    pytest.param("<sdf><world name='a'>", "XML 파싱 실패", id="broken-xml"),
])
def test_template_rejects_bad_structure(text, match):
    with pytest.raises(gc.FleetError, match=match):
        gc.parse_world_template(text)


def test_template_allows_plugin_inside_model_but_not_world_level():
    """모델 안의 plugin은 월드 직속이 아니므로 거부하지 않는다(월드 직속만 server config를 무시하게 한다)."""
    gc.parse_world_template(_sdf("    <model name='m'><plugin name='a' filename='b'/></model>"))


def test_template_comments_are_preserved_in_output():
    text = gc.build_world_sdf(gc.validate_fleet(fleet())[0], _sdf("    <!-- 보존 -->\n    <gravity>0 0 -9.8</gravity>"))
    assert "<!-- 보존 -->" in text and text.count("<spherical_coordinates") == 1


def test_build_world_sdf_rejects_comment_with_forbidden_tag_text():
    """주석 안의 '<spherical_coordinates' 문자열은 wrapper의 줄 단위 grep이 세므로 생성기가 거부한다."""
    body = "    <!-- <spherical_coordinates> 예 -->\n    <gravity>0 0 -9.8</gravity>"
    with pytest.raises(gc.FleetError, match="단정 실패"):
        gc.build_world_sdf(gc.validate_fleet(fleet())[0], _sdf(body))


def test_check_world_sdf_catches_tampering():
    norm, _ = gc.validate_fleet(fleet())
    good = gc.build_world_sdf(norm, _read(os.path.join(REPO, FIXTURE_TEMPLATE)))
    gc.check_world_sdf(good, norm)
    for bad in (
        good.replace("<heading_deg>0<", "<heading_deg>5<"),
        good.replace("ENU", "NED"),
        good.replace("<latitude_deg>37.5665<", "<latitude_deg>37.5<"),
        good.replace('<world name="default">', '<world name="other">'),
        good.replace("</world>", "<plugin name='p' filename='f'/></world>"),
        good.replace("</world>", "<actor name='ghost'/></world>"),
        good.replace("</world>", "<dynamic_pose/></world>"),
    ):
        with pytest.raises(gc.FleetError, match="단정 실패"):
            gc.check_world_sdf(bad, norm)


def test_dynamic_pose_absent_everywhere_and_bridge_topic_set():
    compose, stack, _ = gen()
    assert not any("dynamic_pose" in t for t in _all_strings(compose))
    assert "dynamic_pose" not in gc.dump_compose(compose) and "dynamic_pose" not in gc.dump_stack(stack)
    assert "dynamic_pose" not in gen_world()
    cmd = compose["services"]["bridge"]["command"]
    assert cmd[:4] == ["ros2", "run", "ros_gz_bridge", "parameter_bridge"]
    assert set(cmd[4:]) == {"/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"} and len(cmd[4:]) == 1
    # 인자 집합이 바뀌면 불변식이 잡는다
    compose["services"]["bridge"]["command"].append("/model/x500_1/pose@geometry_msgs/msg/Pose[gz.msgs.Pose")
    with pytest.raises(gc.FleetError, match="bridge 토픽"):
        gc.assert_invariants(compose, stack)


def test_no_origin_env_and_invariants_catch_it():
    compose, stack, _ = gen()
    compose["services"]["gazebo"]["environment"]["IDSIM_ORIGIN_LAT"] = "37.5665"
    with pytest.raises(gc.FleetError, match="IDSIM_ORIGIN"):
        gc.assert_invariants(compose, stack)


def test_stack_json_world_and_v5_keys():
    _, stack, _ = gen()
    assert stack["generator"]["version"] == 5
    assert stack["world"] == {"name": "default", "template": FIXTURE_TEMPLATE, "file": "world/default.sdf",
                              "origin": {"lat": 37.5665, "lon": 126.978, "alt": 38.0}, "speed_factor": None}
    assert stack["inputs"]["world_template"] == {"path": FIXTURE_TEMPLATE, "sha256": "b" * 64}
    assert stack["targets"] == [] and stack["services"]["targets"] is None and stack["services"]["sim_oracle"] is None
    assert stack["vehicles"][0]["expect_gps"] == {"lat": 37.5665, "lon": 126.978, "alt": 38.24}


# ------------------------------------------------------------------ 기대 GPS(decisions.md 쟁점 16)
GZ_ORIGIN = {"lat": 37.5665, "lon": 126.978, "alt": 38}
# gz-math 7.7.0 SphericalCoordinates(EARTH_WGS84, 위도 37.5665, 경도 126.978, 고도 38, heading 0)의
# position_transform(LOCAL2 -> SPHERICAL) 값이다. sim-base 이미지(python3-gz-math7 7.7.0)에서 계산해 고정했다.
#   북 100 m (x 0, y 100):  위도 37.56740099050137, 경도 126.978
#   동 100 m (x 100, y 0):  위도 37.566499994574045, 경도 126.97913189404852
#   (6, -3) m:              위도 37.566472970264314, 경도 126.97806791361582
# 고도는 gz-math의 지구 곡률 때문에 100 m에서 약 0.8 mm 높게 나오는데, 생성기는 고도에 곡률을 넣지 않는다.
GZ_LOCAL2 = [
    pytest.param((0.0, 100.0), (37.56740099050137, 126.978), id="북100"),
    pytest.param((100.0, 0.0), (37.566499994574045, 126.97913189404852), id="동100"),
    pytest.param((6.0, -3.0), (37.566472970264314, 126.97806791361582), id="6_-3"),
]


@pytest.mark.parametrize("xy, ref", GZ_LOCAL2)
def test_expect_gps_matches_gz_math_local2(xy, ref):
    got = gc.expect_gps(GZ_ORIGIN, {"x": xy[0], "y": xy[1], "z": 0.0}, "4001_gz_x500")
    assert abs(got["lat"] - ref[0]) < 1e-8 and abs(got["lon"] - ref[1]) < 1e-8, (got, ref)


def test_expect_gps_altitude_and_yaw_independence():
    pose = {"x": 6.0, "y": -3.0, "z": 1.5, "yaw": 0.0}
    a = gc.expect_gps(GZ_ORIGIN, pose, "4001_gz_x500")
    assert a["alt"] == 38 + 1.5 + 0.24
    assert gc.expect_gps(GZ_ORIGIN, dict(pose, yaw=1.57), "4001_gz_x500") == a
    # 원점 pose는 원점 위경도에 센서 높이만 더한다
    assert gc.expect_gps(GZ_ORIGIN, {"x": 0.0, "y": 0.0, "z": 0.0}, "4001_gz_x500") == {
        "lat": 37.5665, "lon": 126.978, "alt": 38.24}


def test_expect_gps_east_north_and_inversion_distance():
    """동쪽 x는 경도, 북쪽 y는 위도에 들어간다. 기체 1의 (6, -3) 반전이면 13.4 m(= 2 x hypot(6, 3))."""
    g = gc.expect_gps(GZ_ORIGIN, {"x": 6.0, "y": -3.0, "z": 0.0}, "4001_gz_x500")
    assert g["lat"] < GZ_ORIGIN["lat"] and g["lon"] > GZ_ORIGIN["lon"]
    assert abs(2 * math.hypot(6, 3) - 13.416) < 0.01


def test_sensor_z_constants_and_cli(capsys):
    assert set(gc.AIRFRAME_SENSOR_Z_M) == set(gc.ALLOWED_AIRFRAMES)
    assert gc.main(["--print-sensor-z", "4001_gz_x500"]) == 0
    assert capsys.readouterr().out.strip() == "0.24"
    assert gc.main(["--print-sensor-z", "9999_none"]) == 1
    assert "센서 높이" in capsys.readouterr().err


def test_stack_expect_gps_per_vehicle():
    _, stack, _ = gen(f=three_vehicles())
    ys = [v["expect_gps"]["lat"] for v in stack["vehicles"]]
    assert ys == sorted(ys) and len(set(ys)) == 3
    assert {v["expect_gps"]["lon"] for v in stack["vehicles"]} == {126.978}


# ------------------------------------------------------------------ fleet schema 2
def test_schema_1_and_world_file_fail_with_new_key_hint():
    with pytest.raises(gc.FleetError, match="schema: 2"):
        gc.validate_fleet(fleet(schema=1))
    f = fleet()
    f["world"]["file"] = "/opt/px4-gz/worlds/default.sdf"
    with pytest.raises(gc.FleetError) as e:
        gc.validate_fleet(f)
    assert "모르는 key 'file'" in str(e.value) and "world.template" in str(e.value)


def test_origin_missing_fails_with_reason():
    with pytest.raises(gc.FleetError, match="world.origin: 필수"):
        gc.validate_fleet(fleet(world__origin=DELETE))


def test_real_template_and_fleet_generate_and_assert():
    """실제 템플릿과 config/fleet.yaml이 검증, 생성, 출력 단정까지 통과한다(golden이 아닌 단위 테스트)."""
    norm, _ = gc.validate_fleet(gc.load_yaml(_read(os.path.join(REPO, "config/fleet.yaml"))))
    assert norm["world"]["template"] == REAL_TEMPLATE
    text = gc.build_world_sdf(norm, _read(os.path.join(REPO, REAL_TEMPLATE)))
    _, world = _world_children(text)
    assert world.get("name") == norm["world"]["name"]
    assert len([c for c in world if c.tag == "spherical_coordinates"]) == 1
    assert not [c for c in world if c.tag in ("plugin", "actor", "include")]
    assert text.count("<spherical_coordinates") == 1 and "dynamic_pose" not in text
    # 템플릿 자신에는 월드 직속 금지 요소가 없다
    gc.parse_world_template(_read(os.path.join(REPO, REAL_TEMPLATE)))


def test_print_airframes_lists_registered(capsys):
    assert gc.main(["--print-airframes"]) == 0
    assert capsys.readouterr().out.split() == list(gc.AIRFRAME_SENSOR_Z_M)


# ------------------------------------------------------------------ targets(표적 스키마, 서비스, params)
def wp(t, x, y, z=3.0):
    return {"t": t, "x": x, "y": y, "z": z}


def tgt(**changes):
    """검증을 통과하는 표적 하나(기체 1은 원점). changes의 값이 DELETE이면 key를 지운다."""
    t = {"id": "target_a", "start_s": 0, "loop": False,
         "waypoints": [wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 20.0)]}
    for key, value in changes.items():
        if value is DELETE:
            del t[key]
        else:
            t[key] = value
    return t


def with_targets(*items, base=None):
    f = copy.deepcopy(BASE_FLEET if base is None else base)
    f["targets"] = list(items)
    return f


def test_targets_valid_is_normalized_to_float_in_fleet_order():
    norm, _ = gc.validate_fleet(with_targets(
        tgt(id="zeta", start_s=2, waypoints=[{"t": 0, "x": 10, "y": 0, "z": 0}, {"t": 4, "x": 10, "y": 8, "z": 2}]),
        tgt(id="alpha")))
    assert [t["id"] for t in norm["targets"]] == ["zeta", "alpha"]
    z = norm["targets"][0]
    assert z["start_s"] == 2.0 and isinstance(z["start_s"], float) and z["loop"] is False
    assert z["waypoints"][0] == {"t": 0.0, "x": 10.0, "y": 0.0, "z": 0.0}
    assert all(isinstance(v, float) for w in z["waypoints"] for v in w.values())


def test_targets_empty_list_and_non_list():
    assert gc.validate_fleet(with_targets())[0]["targets"] == []
    with pytest.raises(gc.FleetError, match="목록이어야"):
        gc.validate_fleet(fleet(targets=None))


STATIONARY_END = [wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 10.0), wp(20.0, 20.0, 0.0)]
TARGET_REJECTS = [
    pytest.param(tgt(id="Target"), "id: ", id="id-대문자"),
    pytest.param(tgt(id="1abc"), "id: ", id="id-숫자로-시작"),
    pytest.param(tgt(id="a" * 33), "id: ", id="id-33자"),
    pytest.param(tgt(id=5), "id: ", id="id-문자열-아님"),
    pytest.param(tgt(id="x500_1"), "기체 모델 이름 형식", id="id-기체-모델-이름"),
    pytest.param(tgt(id="x500_7"), "기체 모델 이름 형식", id="id-없는-기체-번호도-거부"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0)]), "2개 이상", id="waypoint-1개"),
    pytest.param(tgt(waypoints=[]), "2개 이상", id="waypoint-0개"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), wp(0.0, 20.0, 5.0)]), "엄격히 증가", id="t-같음"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 5.0), wp(9.0, 20.0, 6.0)]), "엄격히 증가", id="t-감소"),
    pytest.param(tgt(waypoints=[wp(1.0, 20.0, 0.0), wp(10.0, 20.0, 5.0)]), "첫 t는 0", id="첫-t-양수"),
    pytest.param(tgt(waypoints=[wp(-1.0, 20.0, 0.0), wp(10.0, 20.0, 5.0)]), "첫 t는 0", id="첫-t-음수"),
    pytest.param(tgt(loop=True, waypoints=[wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 10.0)]), "loop가 true", id="loop-끝-다름"),
    pytest.param(tgt(loop=True, waypoints=[wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 10.0), wp(20.0, 20.0, 0.0, 4.0)]),
                 "loop가 true", id="loop-z만-다름"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0, 0.0), wp(10.0, 20.0, 10.0, -0.5)]), "0 이상이어야", id="z-음수"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), wp(1.0, 20.0, 5.5)]), "수평 속도 5.500", id="수평-속도-초과"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0, 1.0), wp(2.0, 20.0, 0.0, 3.5)]), "수직 속도 1.250", id="수직-속도-초과"),
    pytest.param(tgt(waypoints=[wp(0.0, 1.0, 1.0), wp(10.0, 20.0, 20.0)]), "스폰 지점의 수평 거리", id="스폰-근처"),
    pytest.param(tgt(waypoints=[wp(0.0, 1.9, 0.0), wp(10.0, 20.0, 0.0)]), "스폰 지점의 수평 거리 1.90", id="스폰-1.9m"),
    pytest.param(tgt(start_s=-1), "start_s", id="start_s-음수"),
    pytest.param(tgt(start_s="0"), "start_s", id="start_s-문자열"),
    pytest.param(tgt(loop=1), "loop", id="loop-bool-아님"),
    pytest.param(tgt(start_s=DELETE), "필수 key가 없다.*start_s", id="start_s-없음"),
    pytest.param(tgt(loop=DELETE), "필수 key가 없다.*loop", id="loop-없음"),
    pytest.param(tgt(id=DELETE), "필수 key가 없다.*id", id="id-없음"),
    pytest.param(tgt(waypoints=DELETE), "필수 key가 없다.*waypoints", id="waypoints-없음"),
    pytest.param(dict(tgt(), speed=1), "모르는 key", id="모르는-key"),
    pytest.param(tgt(waypoints=[{"t": 0.0, "x": 20.0, "y": 0.0}, wp(10.0, 20.0, 5.0)]), "필수 key가 없다.*z", id="waypoint-z-없음"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), {"t": 10.0, "x": 20.0, "y": "5", "z": 3.0}]), "숫자가 아닌 값 y",
                 id="waypoint-값-문자열"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), dict(wp(10.0, 20.0, 5.0), v=1)]), "모르는 key", id="waypoint-모르는-key"),
    pytest.param(tgt(waypoints=[wp(0.0, 20.0, 0.0), wp(float("nan"), 20.0, 5.0)]), "숫자가 아닌 값 t", id="waypoint-nan"),
    pytest.param("target_a", "매핑이어야", id="항목-매핑-아님"),
]


@pytest.mark.parametrize("item, match", TARGET_REJECTS)
def test_targets_rejects(item, match):
    with pytest.raises(gc.FleetError, match=match):
        gc.validate_fleet(with_targets(item))


def test_targets_duplicate_id_rejected():
    with pytest.raises(gc.FleetError, match="중복"):
        gc.validate_fleet(with_targets(tgt(), tgt()))


def test_targets_speed_limits_are_inclusive():
    """상한과 같은 속도(수평 5 m/s, 수직 1 m/s)는 통과한다."""
    norm, _ = gc.validate_fleet(with_targets(tgt(waypoints=[wp(0.0, 20.0, 0.0, 0.0), wp(2.0, 26.0, 8.0, 2.0)])))
    assert len(norm["targets"]) == 1  # 수평 10/2 = 5, 수직 2/2 = 1
    with pytest.raises(gc.FleetError, match="수평 속도"):
        gc.validate_fleet(with_targets(tgt(waypoints=[wp(0.0, 20.0, 0.0), wp(2.0, 26.0, 8.1)])))


def test_targets_loop_closed_is_accepted():
    f = with_targets(tgt(loop=True, waypoints=[wp(0.0, 20.0, 0.0), wp(10.0, 20.0, 10.0), wp(20.0, 20.0, 0.0)]))
    assert gc.validate_fleet(f)[0]["targets"][0]["loop"] is True


def test_targets_spawn_check_uses_every_vehicle_horizontal_only():
    f = three_vehicles()  # 기체 y = 0, 4, 8
    f["targets"] = [tgt(waypoints=[wp(0.0, 0.0, 9.0, 30.0), wp(10.0, 20.0, 9.0, 30.0)])]  # 기체 3과 수평 1 m, 높이는 무관
    with pytest.raises(gc.FleetError, match="기체 3의 스폰"):
        gc.validate_fleet(f)
    f["targets"] = [tgt(waypoints=[wp(0.0, 0.0, 10.0, 0.0), wp(10.0, 20.0, 10.0, 0.0)])]  # 정확히 2 m는 통과
    assert gc.validate_fleet(f)[0]["targets"]


def test_targets_limits():
    many = [tgt(id=f"t{i}", waypoints=[wp(0.0, 20.0 + i, 0.0), wp(10.0, 20.0 + i, 10.0)]) for i in range(gc.TARGETS_MAX)]
    assert len(gc.validate_fleet(with_targets(*many))[0]["targets"]) == gc.TARGETS_MAX
    with pytest.raises(gc.FleetError, match="상한 32"):
        gc.validate_fleet(with_targets(*many, tgt(id="extra", waypoints=[wp(0.0, 90.0, 0.0), wp(10.0, 90.0, 5.0)])))
    n = gc.WAYPOINTS_MAX
    ok = [wp(float(i), 20.0, 0.1 * i, 0.0) for i in range(n)]
    assert len(gc.validate_fleet(with_targets(tgt(waypoints=ok)))[0]["targets"][0]["waypoints"]) == n
    with pytest.raises(gc.FleetError, match="상한 256"):
        gc.validate_fleet(with_targets(tgt(waypoints=ok + [wp(float(n), 20.0, 0.1 * n, 0.0)])))


def test_targets_error_reports_every_problem():
    with pytest.raises(gc.FleetError) as e:
        gc.validate_fleet(with_targets(tgt(id="Bad"), tgt(id="x500_1")))
    assert "targets[0].id" in str(e.value) and "targets[1].id" in str(e.value)


def test_targets_id_collides_with_template_names():
    norm, _ = gc.validate_fleet(with_targets(tgt(id="ground_plane")))
    real = _read(os.path.join(REPO, REAL_TEMPLATE))
    with pytest.raises(gc.FleetError, match="ground_plane.*이름과 같다"):
        gc.build_world_sdf(norm, real)
    light = _sdf('    <light name="lamp" type="point"/>')
    norm, _ = gc.validate_fleet(with_targets(tgt(id="lamp")))
    with pytest.raises(gc.FleetError, match="lamp.*이름과 같다"):
        gc.build_world_sdf(norm, light)


def target_fleet():
    return with_targets(
        tgt(id="target_a", start_s=0, loop=True,
            waypoints=[{"t": 0, "x": 20, "y": 0, "z": 3}, wp(10.0, 20.0, 20.0), wp(20.0, 20.0, 0.0)]),
        tgt(id="target_b", start_s=5.5, waypoints=[wp(0.0, -15.5, 12.25, 0.0), wp(8.0, -15.5, -3.75, 0.5)]))


def test_targets_service_details():
    compose, stack, _ = gen(f=target_fleet(), k=2)
    s = compose["services"]
    assert list(s) == ["xrce-agent", "gazebo", "px4-1", "bridge", "ops-1", "targets", "runner", "gz-gui", "foxglove",
                       "lichtblick"]
    t = s["targets"]
    assert t["command"] == ["ros2", "run", "idsim_sim", "target_adapter", "--ros-args", "--params-file",
                            "/opt/idsim/artifacts/runs/20261109-090000-k2/params/targets.yaml"]
    assert t["init"] is True and t["stop_signal"] == "SIGINT"
    assert t["depends_on"] == {"bridge": {"condition": "service_healthy"}}
    assert t["healthcheck"]["test"] == ["CMD-SHELL", "test -f /tmp/idsim/targets_ready"]
    assert t["network_mode"] == "host" and t["restart"] == "no" and "profiles" not in t
    ops = s["ops-1"]
    for key in ("image", "user", "volumes", "network_mode"):
        assert t[key] == ops[key]
    for key in ("RMW_IMPLEMENTATION", "CYCLONEDDS_URI", "ROS_DOMAIN_ID", "HOME"):
        assert t["environment"][key] == ops["environment"][key]
    assert t["environment"]["ROS_DOMAIN_ID"] == "22" and t["environment"]["ROS_LOG_DIR"].endswith("/ros_log/targets")
    assert "GZ_PARTITION" not in t["environment"]
    assert stack["services"]["targets"] == "targets"
    assert stack["startup"]["node_stages"] == [["ops-1", "targets"]]
    assert "targets" not in [n for stage in stack["startup"]["stages"] for n in stage]
    assert s["runner"]["depends_on"] == {n: {"condition": "service_healthy"} for n in ("ops-1", "targets")}
    assert [x["id"] for x in stack["targets"]] == ["target_a", "target_b"]
    assert stack["targets"][0]["waypoints"][0] == {"t": 0.0, "x": 20.0, "y": 0.0, "z": 3.0}
    assert stack["generator"]["version"] == gc.GENERATOR_VERSION


def test_targets_absent_makes_no_service_params_or_log_dir():
    compose, stack, _ = gen()
    assert "targets" not in compose["services"]
    assert stack["services"]["targets"] is None and stack["targets"] == []
    assert stack["startup"]["node_stages"] == [["ops-1"]]
    files = gc.render_files(compose, stack, gen_world())
    assert "params/targets.yaml" not in files
    assert "ros_log/targets" not in gc.render_dirs(compose, stack)


def test_targets_render_dirs_and_files_when_present():
    compose, stack, _ = gen(f=target_fleet())
    assert "ros_log/targets" in gc.render_dirs(compose, stack)
    assert "params/targets.yaml" in gc.render_files(compose, stack, "<world/>")


def test_targets_params_exact_text():
    _, stack, _ = gen(f=target_fleet())
    text = gc.render_targets_params(stack["targets"])
    assert text == (
        "# 생성 파일. tools/gen_compose.py가 config/fleet.yaml의 targets에서 만든다. 손으로 고치지 않는다.\n"
        "# 표적 궤적만 담는다. 발행 주기는 노드 선언 기본값을 쓴다.\n"
        "/**:\n"
        "  ros__parameters:\n"
        "    use_sim_time: true\n"
        '    target_ids: ["target_a", "target_b"]\n'
        "    targets.target_a.start_s: 0.0\n"
        "    targets.target_a.loop: true\n"
        "    targets.target_a.t: [0.0, 10.0, 20.0]\n"
        "    targets.target_a.x: [20.0, 20.0, 20.0]\n"
        "    targets.target_a.y: [0.0, 20.0, 0.0]\n"
        "    targets.target_a.z: [3.0, 3.0, 3.0]\n"
        "    targets.target_b.start_s: 5.5\n"
        "    targets.target_b.loop: false\n"
        "    targets.target_b.t: [0.0, 8.0]\n"
        "    targets.target_b.x: [-15.5, -15.5]\n"
        "    targets.target_b.y: [12.25, -3.75]\n"
        "    targets.target_b.z: [0.0, 0.5]\n")


def test_targets_params_parse_as_double_arrays_and_bool():
    yaml = pytest.importorskip("yaml")
    _, stack, _ = gen(f=target_fleet())
    doc = yaml.safe_load(gc.render_targets_params(stack["targets"]))
    p = doc["/**"]["ros__parameters"]
    assert p["use_sim_time"] is True and p["target_ids"] == ["target_a", "target_b"]
    for t in stack["targets"]:
        base = f"targets.{t['id']}."
        assert p[base + "loop"] is t["loop"] and isinstance(p[base + "start_s"], float)
        for key in gc.WAYPOINT_KEYS:
            arr = p[base + key]
            assert len(arr) == len(t["waypoints"]) and all(isinstance(v, float) for v in arr)
            assert arr == [w[key] for w in t["waypoints"]]


def test_targets_params_quote_ids_that_yaml_reads_as_non_strings():
    yaml = pytest.importorskip("yaml")
    f = with_targets(tgt(id="null"), tgt(id="true", waypoints=[wp(0.0, 30.0, 0.0), wp(10.0, 30.0, 5.0)]))
    _, stack, _ = gen(f=f)
    doc = yaml.safe_load(gc.render_targets_params(stack["targets"]))
    assert doc["/**"]["ros__parameters"]["target_ids"] == ["null", "true"]


def test_targets_embedded_warns_and_ignores():
    compose, stack, warnings = gen(f=target_fleet(), variant="embedded")
    assert stack["targets"] == [] and stack["services"]["targets"] is None
    assert "targets" not in compose["services"] and stack["startup"]["node_stages"] == []
    assert any("targets 2개를 무시" in w for w in warnings)
    _, _, none_warnings = gen(variant="embedded")
    assert not any("targets" in w for w in none_warnings)


def test_targets_invariants_catch_tampering():
    for mutate in (
        lambda c, st: c["services"]["targets"].update(init=False),
        lambda c, st: c["services"]["targets"].update(stop_signal="SIGTERM"),
        lambda c, st: c["services"]["targets"]["depends_on"].update({"px4-1": {"condition": "service_healthy"}}),
        lambda c, st: c["services"]["targets"]["healthcheck"].update(test=["CMD-SHELL", "true"]),
        lambda c, st: c["services"]["targets"].update(command=["true"]),
        lambda c, st: c["services"]["targets"].update(profiles=["viz"]),
        lambda c, st: st["startup"]["stages"][-1].append("targets"),
        lambda c, st: st["startup"].update(node_stages=[["ops-1"]]),
        lambda c, st: c["services"]["runner"]["depends_on"].pop("targets"),
        lambda c, st: st["services"].update(targets=None),
        lambda c, st: c["services"].pop("targets"),
        lambda c, st: st["targets"].append(dict(st["targets"][0])),
    ):
        compose, stack, _ = gen(f=target_fleet())
        mutate(compose, stack)
        with pytest.raises(gc.FleetError, match="단정 실패"):
            gc.assert_invariants(compose, stack)


def test_targets_stack_json_loads_with_support_loader(tmp_path):
    _, stack, _ = gen(f=target_fleet())
    path = tmp_path / "stack.json"
    path.write_text(gc.dump_stack(stack), encoding="utf-8")
    s = stk.load(str(path))
    assert s.targets_service == "targets" and [t["id"] for t in s.targets] == ["target_a", "target_b"]
    assert s.node_stages == [["ops-1", "targets"]]


# ------------------------------------------------------------------ targets의 Actor(월드 SDF)
def _actors(text):
    _, world = _world_children(text)
    return [c for c in world if c.tag == "actor"]


def _actor_points(actor):
    return [(w.findtext("time"), w.findtext("pose")) for w in actor.iter("waypoint")]


def test_actor_samples_by_hand():
    t = {"waypoints": [{"t": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}, {"t": 1.0, "x": 4.0, "y": 2.0, "z": 1.0},
                       {"t": 1.1, "x": 4.0, "y": 2.0, "z": 1.0}]}
    # 구간 1(1.0 s)은 0.25 s씩 4개, 구간 2(0.1 s, 정지)는 1개, 마지막 점 하나
    assert gc.actor_samples(t) == [
        (0.0, 0.0, 0.0, 0.0), (0.25, 1.0, 0.5, 0.25), (0.5, 2.0, 1.0, 0.5), (0.75, 3.0, 1.5, 0.75),
        (1.0, 4.0, 2.0, 1.0), (1.1, 4.0, 2.0, 1.0)]


def test_actor_samples_include_every_waypoint_and_respect_dt():
    t = {"waypoints": [{"t": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}, {"t": 0.3, "x": 1.0, "y": 0.0, "z": 0.0},
                       {"t": 2.0, "x": 1.0, "y": 5.0, "z": 0.0}]}
    samples = gc.actor_samples(t)
    times = [s[0] for s in samples]
    assert 0.3 in times and times[0] == 0.0 and times[-1] == 2.0
    assert all(b - a <= gc.ACTOR_SAMPLE_DT_S + 1e-9 and b > a for a, b in zip(times, times[1:]))
    # 정확히 0.25의 배수인 구간은 올림 오차로 한 개 더 나뉘지 않는다
    exact = gc.actor_samples({"waypoints": [{"t": 0.0, "x": 0.0, "y": 0.0, "z": 0.0},
                                            {"t": 0.5, "x": 1.0, "y": 0.0, "z": 0.0}]})
    assert [s[0] for s in exact] == [0.0, 0.25, 0.5]


def test_actor_element_shape_and_number_format():
    norm, _ = gc.validate_fleet(with_targets(
        tgt(id="target_a", start_s=2, loop=True,
            waypoints=[{"t": 0, "x": 20, "y": 0, "z": 3}, wp(0.5, 20.0, 1.0), wp(1.0, 20.0, 0.0)])))
    text = gc.build_world_sdf(norm, _read(os.path.join(REPO, FIXTURE_TEMPLATE)))
    (actor,) = _actors(text)
    assert actor.get("name") == "target_a" and [c.tag for c in actor] == ["pose", "link", "script"]
    assert actor.findtext("pose") == "0.000000 0.000000 0.000000 0.000000 0.000000 0.000000"
    link = actor.find("link")
    assert [c.tag for c in link] == ["visual"] and link.find("visual/geometry/sphere/radius").text == "0.3"
    assert [c.tag for c in actor.find("script")] == ["loop", "delay_start", "auto_start", "trajectory"]
    assert actor.findtext("script/loop") == "true" and actor.findtext("script/delay_start") == "2.000000"
    traj = actor.find("script/trajectory")
    assert traj.attrib == {"id": "0", "type": "idsim_target", "tension": "0.0"}
    pts = _actor_points(actor)
    assert pts[0] == ("0.000000", "20.000000 0.000000 3.000000 0.000000 0.000000 0.000000")  # 정수 입력도 6자리
    assert pts[-1][0] == "1.000000"
    assert not {el.tag for el in actor.iter()} & set(gc.ACTOR_FORBIDDEN_DESCENDANTS)
    assert "-0.000000" not in text
    assert text.count("<spherical_coordinates") == 1 and "dynamic_pose" not in text


def test_actor_negative_zero_is_written_as_zero():
    assert gc._f6(-0.0) == "0.000000" and gc._f6(-1e-9) == "0.000000" and gc._f6(-0.5) == "-0.500000"


def test_actors_follow_fleet_order_after_spherical_coordinates_and_keep_indent():
    norm, _ = gc.validate_fleet(with_targets(tgt(id="zeta"), tgt(id="alpha", waypoints=[wp(0.0, 30.0, 0.0), wp(4.0, 30.0, 4.0)])))
    text = gc.build_world_sdf(norm, _read(os.path.join(REPO, FIXTURE_TEMPLATE)))
    _, world = _world_children(text)
    tags = [c.tag for c in world]
    assert [c.get("name") for c in world if c.tag == "actor"] == ["zeta", "alpha"]
    assert tags.index("spherical_coordinates") < tags.index("actor")
    assert '\n    <actor name="zeta">\n      <pose>' in text and text.rstrip().endswith("</actor>\n  </world>\n</sdf>")


def test_actor_free_world_when_no_targets():
    text = gen_world()
    assert _actors(text) == [] and "<actor" not in text


def test_check_world_sdf_catches_actor_tampering():
    norm, _ = gc.validate_fleet(with_targets(tgt(id="target_a", loop=True,
                                                 waypoints=[wp(0.0, 20.0, 0.0), wp(2.0, 20.0, 10.0), wp(4.0, 20.0, 0.0)])))
    good = gc.build_world_sdf(norm, _read(os.path.join(REPO, FIXTURE_TEMPLATE)))
    for old, new, match in (
        ("<link name=\"link\">", "<link name=\"link\"><collision name=\"c\"/>", "금지 요소"),
        ("</script>", "<plugin name=\"p\" filename=\"f\"/></script>", "금지 요소"),
        ("<time>0.250000</time>", "<time>0.000000</time>", "엄격히 증가"),
        ("<time>0.250000</time>", "<time>0.900000</time>", "엄격히 증가|넘는다"),
        ("<loop>true</loop>", "<loop>false</loop>", "loop"),
        ("<delay_start>0.000000</delay_start>", "<delay_start>1.000000</delay_start>", "delay_start"),
        ("<pose>20.000000 10.000000 3.000000", "<pose>20.000000 10.000001 3.000000", "원래 waypoint"),
    ):
        assert old in good, old
        with pytest.raises(gc.FleetError, match=match):
            gc.check_world_sdf(good.replace(old, new, 1), norm)
