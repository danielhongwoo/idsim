"""tools/ci/check_sim_topic.py(lint sim-topic)의 단위 테스트. 운용 패키지가 `/sim/` 토픽을 쓰면 잡는지 본다.

docker와 git이 필요 없다. lint.sh와 lint 워크플로의 연결은 문자열로 대조한다(실행은 lint.sh sim-topic).
"""
import os
import re
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "ci"))

import check_sim_topic as cst  # noqa: E402

TARGETS = [
    "ros_ws/src/idsim_common/src/a.cpp",
    "ros_ws/src/idsim_common/include/idsim_common/b.hpp",
    "ros_ws/src/idsim_common/include/idsim_common/detail/px4_topic_list.inc",
    "ros_ws/src/idsim_mission/launch/vehicle_ops.launch.py",
    "ros_ws/src/idsim_mission/config/params.yaml",
    "ros_ws/src/idsim_mission/launch/x.launch.xml",
    "ros_ws/src/idsim_telemetry/src/a.py",
    "ros_ws/src/idsim_fleet/src/a.cc",
    "gateway/src/main.rs",
    "gateway/config/gw.yml",
    "tests/fixtures/gen_compose/3대-k0/params/ops-2.yaml",
]
NOT_TARGETS = [
    "ros_ws/src/idsim_sim/scripts/sim_oracle.py",
    "ros_ws/src/idsim_sim/idsim_sim/oracle.py",
    "ros_ws/src/idsim_interfaces/msg/TargetState.msg",
    "ros_ws/src/idsim_mission/test/test_x.cpp",
    "ros_ws/src/idsim_common/test/geo_reference/gz_local2.py",
    "ros_ws/src/idsim_mission/test/params/p.yaml",
    "gateway/tests/it.rs",
    "ros_ws/src/idsim_mission/README.md",
    "ros_ws/src/idsim_mission/test/transition_cells.tsv",
    "tests/fixtures/gen_compose/3대-k0/params/targets.yaml",
    "tests/sitl/run.py",
    "ros_ws/src/idsim_missionx/src/a.cpp",
    "xgateway/src/main.rs",
]


@pytest.mark.parametrize("path", TARGETS)
def test_is_target(path):
    assert cst.is_target(path)


@pytest.mark.parametrize("path", NOT_TARGETS)
def test_is_not_target(path):
    assert not cst.is_target(path)


@pytest.mark.parametrize("line", [
    'create_subscription<PoseStamped>("/sim/px4_1/pose", 10, cb);',
    "topic = '/sim/' + vehicle_id + '/pose'",
    "remap: {from: pose, to: /sim/px4_1/pose}",
    "// /sim/ 토픽을 구독한다",
    "name: /px4_1/sim/pose",
])
def test_violations_found(line):
    assert cst.violations("x", f"ok\n{line}\nok\n") == [(2, line)]


@pytest.mark.parametrize("line", [
    "/simulation/x", "sim/px4_1/pose", "idsim_sim", "/sim", "target = '/targets/t1/state'", "",
])
def test_violations_not_found(line):
    assert cst.violations("x", f"{line}\n") == []


def _run(tmp_path, monkeypatch, files, capsys):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = cst.main(list(files))
    return rc, capsys.readouterr().out.splitlines()


def test_main_catches_each_operational_source_kind(tmp_path, monkeypatch, capsys):
    bad = '"/sim/px4_1/pose"\n'
    files = {
        "ros_ws/src/idsim_mission/src/node.cpp": bad,
        "ros_ws/src/idsim_common/include/idsim_common/x.hpp": bad,
        "ros_ws/src/idsim_mission/launch/vehicle_ops.launch.py": bad,
        "ros_ws/src/idsim_mission/config/p.yaml": bad,
        "gateway/src/main.rs": bad,
        "tests/fixtures/gen_compose/1대-k0/params/ops-1.yaml": bad,
    }
    rc, out = _run(tmp_path, monkeypatch, files, capsys)
    assert rc == 1
    assert out[-1] == "scanned=6"
    assert sorted(line.split(":")[0] for line in out[:-1]) == sorted(files)
    assert all(line.split(":")[1] == "1" for line in out[:-1])


def test_main_passes_clean_files_and_skips_excluded_ones(tmp_path, monkeypatch, capsys):
    files = {
        "ros_ws/src/idsim_mission/src/node.cpp": 'auto n = "/px4_1/fmu/out/x";\n',
        # 대상이 아닌 곳의 /sim/은 센다고 해서 실패하지 않는다(시뮬레이터 쪽, 테스트, 문서)
        "ros_ws/src/idsim_sim/scripts/sim_oracle.py": 'T = "/sim/px4_1/pose"\n',
        "ros_ws/src/idsim_mission/test/t.cpp": 'EXPECT_EQ(s.find("/sim/"), npos);\n',
        "ros_ws/src/idsim_mission/README.md": "/sim/ 토픽은 쓰지 않는다\n",
        "tests/fixtures/gen_compose/3대-k0/params/targets.yaml": "x: /sim/a\n",
    }
    rc, out = _run(tmp_path, monkeypatch, files, capsys)
    assert rc == 0 and out == ["scanned=1"]
    assert "PASS-NO-TARGETS" not in _read("tools/ci/lint.sh").split("check_sim_topic() {")[1].split("\n}\n")[0]


def test_main_with_no_targets_fails(tmp_path, monkeypatch, capsys):
    rc, out = _run(tmp_path, monkeypatch, {"tests/sitl/a.py": "x = '/sim/a'\n"}, capsys)
    assert rc == 1 and out[0] == "scanned=0" and "0개" in out[1]
    rc, out = _run(tmp_path, monkeypatch, {}, capsys)
    assert rc == 1 and out[0] == "scanned=0"


def test_repository_operational_packages_are_clean():
    """실제 저장소의 운용 패키지에 /sim/이 없다(lint가 CI에서 같은 것을 본다)."""
    scanned = 0
    for root in ("ros_ws/src", "gateway", "tests/fixtures/gen_compose"):
        for dirpath, _, names in os.walk(os.path.join(REPO, root)):
            for name in names:
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, REPO).replace(os.sep, "/")
                if cst.is_target(rel):
                    scanned += 1
                    with open(path, encoding="utf-8") as f:
                        assert cst.violations(rel, f.read()) == [], rel
    assert scanned > 0


def _read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


def test_lint_sh_and_workflow_wire_sim_topic():
    lint = _read("tools/ci/lint.sh")
    m = re.search(r"^all_checks=\((.*)\)$", lint, re.M)
    assert m and "sim-topic" in m.group(1).split()
    assert re.search(r"^\s+sim-topic\) check_sim_topic ;;$", lint, re.M)
    workflow = _read(".github/workflows/lint.yml")
    matrix = re.findall(r"^          - (\S+)$", workflow, re.M)
    assert matrix == m.group(1).split()
    # 후보 경로는 점검 대상의 접두어를 모두 덮는다
    for root in cst.OPERATIONAL_ROOTS:
        assert f"'{root}*'" in lint
    assert "'tests/fixtures/gen_compose/*/params/ops-*.yaml'" in lint
