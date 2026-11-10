"""tools/gen_compose.py 단위 테스트(초안 devops-engineer, 승인 test-engineer).

lint 잡의 python 이미지(PyYAML == versions.env의 LINT_PYYAML_VERSION, pytest)에서 저장소 루트를 작업
디렉터리로 `python3 -m pytest tests/tools`로 돈다. docker가 필요 없다(compose config 검사는 lint.sh의
compose-config 항목).

골든: tests/fixtures/gen_compose/<사례>/{fleet.yaml, compose.yaml, stack.json}. 사례의 fleet.yaml을 고정 인자
(GOLDEN_CTX)로 생성해 compose.yaml, stack.json과 바이트 단위로 비교한다. 골든 파일이 없으면 실패한다.
갱신은 --update-golden(저장소를 쓰기 가능하게 마운트한 환경에서):
  python3 -m pytest tests/tools --update-golden -p no:cacheprovider
diff는 리뷰에서 본다. 고정 인자 중 versions_env의 sha256만 상수로 둔다(도구 버전 줄을 고칠 때마다
골든이 바뀌지 않게). 나머지 입력 sha256은 실제 파일 값이다.
"""
import copy
import json
import os
import re

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
FIXED = {
    "uid": 1000,
    "gid": 1000,
    "generated_at": "2026-11-09T09:00:00Z",
    "git_commit": "0" * 40,
    "git_dirty": False,
    "versions_env_sha256": "0" * 64,
}

BASE_FLEET = {
    "schema": 1,
    "world": {
        "name": "default",
        "file": "/opt/px4-gz/worlds/default.sdf",
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
        },
        "params_env": PARAMS_ENV,
        "participant_index_max": PMAX,
    }


def gen(f=None, **ctx_kw):
    norm, warnings = gc.validate_fleet(copy.deepcopy(BASE_FLEET if f is None else f))
    compose, stack, more = gc.build(norm, make_ctx(**ctx_kw))
    return compose, stack, warnings + more


# ------------------------------------------------------------------ 골든
def _golden_outputs(case):
    k, variant = GOLDEN_CASES[case]
    rel = f"tests/fixtures/gen_compose/{case}/fleet.yaml"
    path = os.path.join(REPO, rel)
    norm, _ = gc.validate_fleet(gc.load_yaml(_read(path)))
    ctx = make_ctx(k=k, variant=variant, fleet_path=rel, fleet_sha=gc._sha256_file(path))
    compose, stack, _ = gc.build(norm, ctx)
    return gc.dump_compose(compose), gc.dump_stack(stack)


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden(case, request):
    case_dir = os.path.join(GOLDEN_DIR, case)
    assert os.path.isfile(os.path.join(case_dir, "fleet.yaml")), f"골든 입력 없음: {case_dir}/fleet.yaml"
    compose_text, stack_text = _golden_outputs(case)
    update = request.config.getoption("--update-golden", default=False)
    for name, text in (("compose.yaml", compose_text), ("stack.json", stack_text)):
        path = os.path.join(case_dir, name)
        if update:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            continue
        assert os.path.isfile(path), f"골든 없음: {path} (--update-golden으로 만든다)"
        assert _read(path) == text, f"골든 불일치: {path} (의도한 변경이면 --update-golden)"


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_golden_stack_loads_with_support_loader(case):
    """교차 테스트: 골든 stack.json을 tests.support.stack 로더가 받는다(test-engineer 합의)."""
    path = os.path.join(GOLDEN_DIR, case, "stack.json")
    s = stk.load(path)
    k, variant = GOLDEN_CASES[case]
    assert s.stack_index == k and s.variant == variant
    assert s.compose_project == f"idsim-{k}"
    assert [v.service for v in s.vehicles] == s.services["px4"]
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
    for name in ("bridge", "runner", "gz-gui"):
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
    assert list(s) == ["xrce-agent", "gazebo", "px4-1", "bridge", "runner", "gz-gui"]
    hc = s["gazebo"]["healthcheck"]["test"][1]
    assert hc == ('gz service -i --service /world/default/scene/info | grep -q "Service providers"'
                  " && test -f /tmp/idsim/ready")
    env = s["gazebo"]["environment"]
    assert (env["IDSIM_ORIGIN_LAT"], env["IDSIM_ORIGIN_LON"], env["IDSIM_ORIGIN_ALT"]) == ("37.5665", "126.978", "38")
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
    assert stack["startup"]["stages"] == [["xrce-agent", "gazebo"], ["px4-1", "bridge"]]


def test_origin_absent_gives_no_env_and_null():
    compose, stack, _ = gen(fleet(world__origin=DELETE))
    assert not any(k.startswith("IDSIM_ORIGIN") for k in compose["services"]["gazebo"]["environment"])
    assert stack["world"]["origin"] is None
    compose, stack, _ = gen(fleet(world__origin=None))
    assert stack["world"]["origin"] is None


def test_embedded_variant():
    compose, stack, warnings = gen(variant="embedded")
    s = compose["services"]
    assert set(s) == {"xrce-agent", "px4-1", "runner"}
    env = s["px4-1"]["environment"]
    assert env["HEADLESS"] == "1" and "PX4_GZ_STANDALONE" not in env
    assert s["px4-1"]["depends_on"] == {"xrce-agent": {"condition": "service_healthy"}}
    assert s["runner"]["depends_on"] == {"px4-1": {"condition": "service_healthy"}}
    assert stack["world"]["origin"] is None
    assert any("origin" in w for w in warnings)
    for role in ("gazebo", "bridge", "gz_gui", "foxglove", "lichtblick"):
        assert role in stack["services"] and stack["services"][role] is None
    assert stack["startup"] == {"stages": [["xrce-agent"], ["px4-1"]], "model_precheck": False}
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


def test_dump_compose_has_no_anchor_and_quotes_strings():
    text = gc.dump_compose(gen(three_vehicles())[0])
    assert "&id" not in text and "*id" not in text
    assert "restart: 'no'" in text


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
    pytest.param(fleet(schema=2), id="schema"),
    pytest.param(fleet(vehicles=[]), id="no-vehicles"),
    pytest.param(fleet(world__name="bad name"), id="world-name"),
    pytest.param(fleet(world__file="default.sdf"), id="world-file-relative"),
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
        gc.load_yaml("schema: 1\nschema: 1\n")


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
