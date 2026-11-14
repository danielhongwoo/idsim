#!/usr/bin/env python3
"""config/fleet.yaml -> <run-dir>/{compose.yaml, stack.json, params/ops-N.yaml}. 담당: devops-engineer.

설계는 docs/architecture.md의 "기체 식별과 설정의 단일 출처"와 "Docker Compose 실행 환경 설계" 절,
stack.json 형식은 tests/support/stack.py(로더)와 같은 schema 1을 따른다. fleet.yaml의 schema는 2다.

ros-ws 컨테이너 안에서 실행한다(PyYAML 6.0.1). 호스트 진입점은 tools/gen_compose.sh다.
구조
  - 핵심은 순수 함수다: validate_fleet(dict) -> dict, build(fleet, ctx) -> (compose, stack, 경고),
    render_files(compose, stack) -> {상대 경로: 본문}(만드는 파일의 유일한 목록), render_dirs(...) -> 빈 디렉터리 목록.
    파일을 읽거나 쓰지 않으며 단위 테스트(tests/tools/test_gen_compose.py)가 이 함수를 직접 부른다.
  - PyYAML은 읽기(load_yaml)와 쓰기(dump_compose)에만 쓴다. 모듈을 불러올 때는 yaml을 import하지 않으므로
    --print-gcs-port와 --print-agent-port는 호스트의 표준 라이브러리 python3로도 돈다(tools/qgc.sh가 쓴다).
  - 사용자 이름을 조회하지 않는다(getpass, pwd 금지). uid, gid는 숫자 인자로만 받는다.

기준값(스택 번호 k, 기체 번호 N)은 이 파일의 상수가 유일한 출처다. fleet.yaml에는 적을 수 없다.

사용법(컨테이너 안. 보통은 tools/gen_compose.sh가 부른다)
  gen_compose.py --host-repo-root /home/u/idsim [--fleet config/fleet.yaml] [--stack k]
                 [--variant standalone|embedded] [--run-id ID] [--run-dir 호스트경로] [--out-dir 쓰기경로]
                 [--uid U --gid G] [--image-tag local | --registry R] [--image 이름=참조]...
                 [--generated-at 2026-11-09T09:00:00Z] [--git-commit SHA] [--git-dirty true|false]
  gen_compose.py --print-gcs-port k     # QGC가 들을 GCS 포트(14550 + 1000k)만 출력
  gen_compose.py --print-agent-port k   # 에이전트 UDP 포트(8888 + k)만 출력
  gen_compose.py --print-airframes          # 센서 높이가 등록된 airframe 목록(스모크 S0가 돈다)
  gen_compose.py --print-sensor-z AIRFRAME  # airframe의 GNSS 센서 높이(m)만 출력(스모크 S0가 모델 SDF와 대조한다)
종료 코드: 0 성공, 1 검증 실패(stderr에 이유), 2 인자 오류.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- 기준값(생성기 상수)
SCHEMA = 1  # stack.json의 schema
FLEET_SCHEMA = 2  # fleet.yaml의 schema
GENERATOR_VERSION = 5
GENERATOR_SCRIPT = "tools/gen_compose.py"

STACK_MIN, STACK_MAX = 0, 9
VEHICLE_MIN, VEHICLE_MAX = 1, 9
ROS_DOMAIN_BASE = 20
AGENT_PORT_BASE = 8888
FOXGLOVE_PORT_BASE = 8765
LICHTBLICK_PORT_BASE = 18080
MAVLINK_OFFSET_STEP = 1000
MAVLINK_GCS_REMOTE = 14550
MAVLINK_GCS_LOCAL = 18570
MAVLINK_API_REMOTE = 14540
MAVLINK_API_LOCAL = 14580
EPHEMERAL_PORT_MIN = 32768
DDS_PORT_BASE = 7400
DDS_DOMAIN_GAIN = 250
DDS_UNICAST_OFFSET = 11  # 참가자 i의 유니캐스트 데이터 포트 = PB + DG x D + 11 + 2i
PARTICIPANT_INDEX_LIMIT = 64
GZ_IP = "127.0.0.1"
VIZ_BIND = "127.0.0.1"
# foxglove_bridge 읽기 전용 설정. capabilities에서 clientPublish, services, parameters를 뺀다.
# 아무것과도 맞지 않는 정규식으로 클라이언트 발행, 서비스, 파라미터 허용 목록을 비운다.
FOXGLOVE_CAPABILITIES = "[connectionGraph]"
FOXGLOVE_DENY_ALL = "['^$$']"  # compose 보간에서 $$는 리터럴 $
RMW = "rmw_cyclonedds_cpp"

# ops-N(기체별 Mission Executor 컨테이너). 노드 이름의 출처는 이 상수 하나다. launch 파일과 노드 소스는
# 이름을 직접 적지 않는다(launch는 인자로 받고, 노드 기본 이름은 단위 테스트용이다).
EXECUTOR_NODE_NAME = "mission_executor"
OPS_LAUNCH_PKG = "idsim_mission"
OPS_LAUNCH_FILE = "vehicle_ops.launch.py"
PARAMS_DIR = "params"
OPS_STOP_SIGNAL = "SIGINT"
OPS_STOP_GRACE = "10s"
# lifecycle get 한 번의 상한. docker exec 한 번이 3.0-4.5 s 걸린다(decisions.md 쟁점 2 실측)
OPS_PROBE_TIMEOUT_S = 8

SPACING_REJECT_M = 2.0
SPACING_WARN_M = 4.0

# targets(표적 어댑터). 궤적 정의의 출처는 fleet.yaml의 targets 하나이고, 생성기가 정규화한 값을 월드 SDF의 Actor,
# params/targets.yaml, stack.json의 targets에 낸다(decisions.md 쟁점 1, 3).
TARGETS_SERVICE = "targets"
# ros2 run <패키지> <실행 이름>. 실행 이름의 출처는 이 상수 하나다(idsim_sim 패키지의 console_scripts가 같은 이름을 만든다)
TARGET_ADAPTER_PKG = "idsim_sim"
TARGET_ADAPTER_EXEC = "target_adapter"
TARGETS_PARAMS_FILE = f"{PARAMS_DIR}/targets.yaml"
TARGETS_READY_FILE = "/tmp/idsim/targets_ready"
# sim-oracle(SITL 전용 정답 pose 공급자, decisions.md 쟁점 5). sim-base 이미지에 마운트한 idsim_sim/scripts/sim_oracle.py를 돌린다.
# standalone이면 표적과 무관하게 항상 만들고 embedded에는 없다.
ORACLE_SERVICE = "sim-oracle"
ORACLE_SCRIPT = "scripts/sim_oracle.py"  # SIM_PKG_IN_CONTAINER 기준
ORACLE_READY_FILE = "/tmp/idsim/oracle_ready"
TARGET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}\Z")
TARGET_KEYS = ("id", "start_s", "loop", "waypoints")
WAYPOINT_KEYS = ("t", "x", "y", "z")
TARGETS_MAX = 32
WAYPOINTS_MAX = 256
TARGET_SPEED_XY_MAX_MPS = 5.0
TARGET_SPEED_Z_MAX_MPS = 1.0
TARGET_SPEED_EPS = 1e-9  # 상한과 같은 속도는 통과시키는 부동소수점 여유
TARGET_SPAWN_CLEAR_M = 2.0  # t=0 위치와 기체 스폰의 최소 수평 거리
TARGET_COORD_XY_MAX_M = 10000.0  # |x|, |y| 상한(모든 waypoint)
TARGET_COORD_Z_MAX_M = 1000.0
TARGET_START_S_MAX = 86400.0
# 시간 규칙은 정수 ms에서 판정한다(T = round(t x 1000)). gz-sim이 <time>을 int ms로 바꿔 map의 key로 쓰기 때문이다.
TARGET_GAP_MIN_MS = 100  # 인접 waypoint의 T 차 하한
TARGETS_LENGTH_SUM_MAX_MS = 2400000  # 표적마다 마지막 T를 더한 합의 상한이자 T 하나의 상한(start_s와 끝 정지 꼬리는 넣지 않는다)
# Gazebo Actor(화면 확인용. 표적 위치의 원천은 아니다). 요소의 형태와 값은 sim-engineer가 정한다(B6 Actor 명세 판 2).
ACTOR_SAMPLE_DT_MS = 250  # waypoint 표본 간격 상한(ms). 잠정, M4 육안 확인 뒤 확정
ACTOR_TAIL_STEP_MS = 250  # loop false 꼬리의 첫 점이 마지막 점 뒤 얼마인가(접선을 0으로 만든다)
ACTOR_HOLD_MS = 86400000  # loop false 꼬리의 둘째 점(시뮬레이션 시간 1일 뒤)
ACTOR_SPHERE_RADIUS_M = "0.3"
ACTOR_MATERIAL = (("ambient", "1 0 0 1"), ("diffuse", "1 0 0 1"), ("emissive", "0.6 0 0 1"))
ACTOR_TRAJECTORY_TYPE = "idsim_target"  # skin이 없어 어떤 animation과도 대응하지 않는 이름표
ACTOR_FORBIDDEN_DESCENDANTS = ("plugin", "skin", "animation", "collision")

# 이미지 레이아웃(컨테이너 안 경로). 이미지가 바뀌면 여기와 Dockerfile을 함께 고친다.
REPO_IN_CONTAINER = "/opt/idsim"
CYCLONEDDS_IN_CONTAINER = "/opt/idsim/config/cyclonedds.xml"
CYCLONEDDS_URI = f"file://{CYCLONEDDS_IN_CONTAINER}"
SIM_PKG_REL = "ros_ws/src/idsim_sim"
SIM_PKG_IN_CONTAINER = "/opt/idsim/sim"
PX4_ROOTFS = "/opt/PX4-Autopilot/build/px4_sitl_default/rootfs"
PX4_GZ_MODELS = "/opt/px4-gz/models"
PX4_GZ_WORLDS = "/opt/px4-gz/worlds"
WORLD_IN_CONTAINER = "/opt/idsim/world"  # 실행 디렉터리의 world/를 gazebo 서비스에 읽기 전용으로 마운트
WORLD_DIR = "world"  # 실행 디렉터리 안의 생성 월드 디렉터리
GZ_SERVER_CONFIG = "/opt/px4-gz/server.idsim.config"
GZ_RESOURCE_PATH = "/opt/px4-gz/models:/opt/px4-gz/worlds"
GZ_READY_FILE = "/tmp/idsim/ready"
X11_SOCKET_DIR = "/tmp/.X11-unix"
XAUTH_IN_CONTAINER = "/tmp/.Xauthority"

IMAGE_NAMES = ("xrce-agent", "sim-base", "px4", "ros-ws")
VERSIONS_ENV_REL = "docker/versions.env"
CYCLONEDDS_REL = "config/cyclonedds.xml"

# airframe 허용 목록. 이름에서 SYS_AUTOSTART, PX4_SIM_MODEL, Gazebo 모델 이름이 파생된다.
ALLOWED_AIRFRAMES = ("4001_gz_x500",)
# airframe별 GNSS 센서(base_link 기준 NavSat)의 지면 위 높이(m). x500 모델 SDF의 base_link 높이와 같아야 하고,
# 스모크 images 단계(S0)가 sim-base 안의 모델과 --print-sensor-z 출력을 대조한다.
AIRFRAME_SENSOR_Z_M = {"4001_gz_x500": 0.24}
# WGS84 타원체(expect_gps의 국소 근사)
WGS84_A_M = 6378137.0
WGS84_E2 = 0.00669437999014
# bridge 명령행의 토픽 인자. 1b의 bridge는 /clock 하나만 넘긴다(표적과 정답 pose는 bridge를 거치지 않는다).
BRIDGE_TOPIC_ARGS = ("/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",)
# 템플릿 world 직속에 있으면 거부하는 요소(plugin은 server config를 무시하게 하고, 나머지는 생성기가 넣는다)
WORLD_FORBIDDEN_CHILDREN = ("plugin", "spherical_coordinates", "actor", "include")
# 템플릿 world 직속에서 이름(name 속성)이 Gazebo 엔티티 이름이 되는 요소. 표적 id와 겹치면 거부한다
TEMPLATE_NAMED_CHILDREN = ("model", "actor", "light")
TEMPLATE_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+\.sdf\Z")
# fleet.yaml에서 거부하는 식별 파라미터. PX4가 -i N과 환경에서 스스로 정한다.
FORBIDDEN_PARAMS = ("MAV_SYS_ID", "UXRCE_DDS_KEY", "UXRCE_DDS_DOM_ID", "UXRCE_DDS_AG_IP", "SYS_AUTOSTART")
PARAM_NAME_RE = re.compile(r"^[A-Z0-9_]{1,16}\Z")
PARAM_VALUE_RE = re.compile(r"^[^\s'\"#]+\Z")
WORLD_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
PATH_SAFE_RE = re.compile(r"^/[A-Za-z0-9_./@+-]*\Z")

# viz 서비스에만 허용하는 compose 보간. 이 밖의 ${...}와 $는 출력에 남으면 안 된다.
ALLOWED_INTERPOLATIONS = ("${DISPLAY:-}", "${XAUTHORITY:-/dev/null}")
# gz-gui에 이름만 통과시키는 환경변수(호스트에 있으면 그 값, 없으면 넘기지 않는다)
GUI_PASS_ENV = ("IDSIM_GZ_GUI_ENGINE", "QSG_RENDER_LOOP", "vblank_mode")

FLEET_KEYS = {"schema", "world", "vehicles", "targets", "px4"}
WORLD_KEYS = {"name", "template", "origin", "speed_factor"}
ORIGIN_KEYS = ("lat", "lon", "alt")
VEHICLE_KEYS = {"id", "airframe", "pose", "px4_params"}
POSE_KEYS = ("x", "y", "z", "yaw")
PX4_KEYS = {"params_file", "start"}
PX4_START = ("parallel", "sequential")
VARIANTS = ("standalone", "embedded")


class FleetError(Exception):
    """fleet.yaml 또는 생성 인자 검증 실패. 메시지는 사람이 읽는 이유 목록이다."""


# ---------------------------------------------------------------- 파생 규칙
def ros_domain(k):
    return ROS_DOMAIN_BASE + k


def agent_port(k):
    return AGENT_PORT_BASE + k


def mavlink_offset(k):
    return MAVLINK_OFFSET_STEP * k


def gcs_remote_port(k):
    return MAVLINK_GCS_REMOTE + mavlink_offset(k)


def vehicle_mavlink(k, n):
    o = mavlink_offset(k)
    return {
        "gcs_remote": MAVLINK_GCS_REMOTE + o,
        "gcs_local": MAVLINK_GCS_LOCAL + o + n,
        "api_remote": MAVLINK_API_REMOTE + o + n,
        "api_local": MAVLINK_API_LOCAL + o + n,
    }


def dds_ports(k, participant_max):
    """(도메인 범위 시작, 도메인 범위 끝, 실사용 끝). 실사용 끝은 인덱스 participant_max의 데이터 포트."""
    base = DDS_PORT_BASE + DDS_DOMAIN_GAIN * ros_domain(k)
    return base, base + DDS_DOMAIN_GAIN - 1, base + DDS_UNICAST_OFFSET + 2 * participant_max


def split_airframe(airframe):
    """'4001_gz_x500' -> (4001, 'gz_x500', 'x500')."""
    num, _, sim_model = airframe.partition("_")
    return int(num), sim_model, sim_model[len("gz_"):]


def port_ranges(k, participant_max, ids=range(VEHICLE_MIN, VEHICLE_MAX + 1)):
    """스택 k가 쓰는 포트 구간 목록 [(이름, 시작, 끝)]. 프로토콜과 무관하게 값이 겹치지 않아야 한다."""
    dlo, _, dhi = dds_ports(k, participant_max)
    out = [
        (f"k{k} dds", dlo, dhi),
        (f"k{k} agent", agent_port(k), agent_port(k)),
        (f"k{k} foxglove", FOXGLOVE_PORT_BASE + k, FOXGLOVE_PORT_BASE + k),
        (f"k{k} lichtblick", LICHTBLICK_PORT_BASE + k, LICHTBLICK_PORT_BASE + k),
        (f"k{k} gcs_remote", gcs_remote_port(k), gcs_remote_port(k)),
    ]
    for n in ids:
        m = vehicle_mavlink(k, n)
        for name in ("gcs_local", "api_remote", "api_local"):
            out.append((f"k{k} N{n} {name}", m[name], m[name]))
    return out


def check_port_plan(participant_max):
    """k 0-9, N 1-9를 모두 동시에 올린다고 보고 포트 구간이 서로 겹치지 않음을 단정한다."""
    if participant_max > PARTICIPANT_INDEX_LIMIT:
        raise FleetError(f"MaxAutoParticipantIndex {participant_max} > {PARTICIPANT_INDEX_LIMIT}: "
                         "DDS 포트가 이웃 스택의 MAVLink 포트와 겹친다")
    ranges = []
    for k in range(STACK_MIN, STACK_MAX + 1):
        ranges.extend(port_ranges(k, participant_max))
    ranges.sort(key=lambda r: (r[1], r[2]))
    for a, b in zip(ranges, ranges[1:]):
        if b[1] <= a[2]:
            raise FleetError(f"포트 충돌: {a[0]} {a[1]}-{a[2]} 와 {b[0]} {b[1]}-{b[2]}")
    hi = max(r[2] for r in ranges)
    if hi >= EPHEMERAL_PORT_MIN:
        raise FleetError(f"포트 {hi}가 임시 포트 범위({EPHEMERAL_PORT_MIN} 이상)에 들어간다")
    return ranges


# ---------------------------------------------------------------- fleet.yaml 검증
def _is_number(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:  # 400자리 정수는 float로 바꿀 수 없다
        return False


def _decimal_str(v):
    """숫자를 지수 표기 없는 십진 문자열로. gz_server.sh와 PX4_GZ_MODEL_POSE가 지수 표기를 받지 않는다."""
    if isinstance(v, int):
        return str(v)
    s = repr(float(v))
    if "e" in s or "E" in s:
        s = f"{v:.12f}".rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def _param_value_str(name, v, where, errors):
    if isinstance(v, bool) or v is None or isinstance(v, (list, dict)):
        errors.append(f"{where}.{name}: 값은 숫자 또는 공백 없는 문자열이어야 한다(bool, null, 목록 불가): {v!r}")
        return None
    if isinstance(v, float) and not math.isfinite(v):
        errors.append(f"{where}.{name}: 유한한 숫자가 아니다: {v!r}")
        return None
    s = str(v) if not isinstance(v, str) else v
    if not PARAM_VALUE_RE.match(s):
        errors.append(f"{where}.{name}: 값에 공백, 따옴표, #을 쓸 수 없다: {s!r}")
        return None
    return s


def _check_param_name(name, where, errors):
    if not isinstance(name, str) or not PARAM_NAME_RE.match(name):
        errors.append(f"{where}: 파라미터 이름 형식 위반(^[A-Z0-9_]{{1,16}}$): {name!r}")
        return False
    if name in FORBIDDEN_PARAMS:
        errors.append(f"{where}: 식별 파라미터 {name}는 적을 수 없다(PX4가 -i N에서 정한다)")
        return False
    return True


def _unknown_keys(obj, allowed, where, errors):
    for key in obj:
        if key not in allowed:
            errors.append(f"{where}: 모르는 key {key!r} (허용: {', '.join(sorted(allowed))})")


def _vehicle_model_name_re():
    """허용 airframe의 기체 모델 이름 형식(x500_N). 표적 id가 같으면 Actor와 기체 모델의 이름이 겹친다."""
    models = sorted({split_airframe(af)[2] for af in ALLOWED_AIRFRAMES})
    return re.compile(r"^(%s)_[0-9]+\Z" % "|".join(re.escape(m) for m in models))


def _validate_targets(raw, posed_vehicles, errors):
    """targets 목록을 검사해 정규화한다(fleet.yaml의 순서 그대로. 숫자는 모두 float). 오류는 errors에 더하고 정규화 값을 돌려준다.

    네 key(id, start_s, loop, waypoints)와 waypoint의 {t, x, y, z}는 모두 필수이고 기본값이 없다.
    거부: id 형식과 중복, 기체 모델 이름(x500_N 형식)과 같은 id, waypoint 2개 미만, t 비증가, 첫 t가 0이 아님,
    ms로 반올림한 시각이 2400000 ms를 넘는 waypoint, 인접 waypoint의 T 차가 100 ms 미만(T = round(t x 1000)), loop인데 처음과 끝이 다름,
    z < 0, 좌표 범위(|x|, |y| 10000 m, z 1000 m)와 start_s(86400 s) 상한 초과, 구간 속도 상한 초과(수평, 수직),
    t=0 위치가 기체 스폰과 수평 2 m 안, 개수 상한 초과, 표적마다 마지막 T를 더한 합이 2400000 ms 초과.
    합에는 waypoint 형식이 맞고 t가 엄격히 증가하며 모든 waypoint에 T가 만들어진 표적을 모두 넣는다(다른 규칙으로 거부된
    표적도 넣는다. 형식이 틀린 표적은 빠진다). 템플릿 최상위 <model>, <actor>, <light> 이름과의 충돌은
    템플릿을 읽는 build_world_sdf가 거부한다.
    """
    if not isinstance(raw, list):
        errors.append("targets: 목록이어야 한다(표적이 없으면 [])")
        return []
    if len(raw) > TARGETS_MAX:
        errors.append(f"targets: 표적이 {len(raw)}개다(상한 {TARGETS_MAX})")
    model_re = _vehicle_model_name_re()
    out, seen, lengths = [], set(), []
    for i, t in enumerate(raw):
        where = f"targets[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{where}: 매핑이어야 한다")
            continue
        _unknown_keys(t, set(TARGET_KEYS), where, errors)
        missing = [key for key in TARGET_KEYS if key not in t]
        if missing:
            errors.append(f"{where}: 필수 key가 없다(기본값 없음): {', '.join(missing)}")
        ok = not missing
        tid = t.get("id")
        if "id" in t:
            if not isinstance(tid, str) or not TARGET_ID_RE.match(tid):
                errors.append(f"{where}.id: ^[a-z][a-z0-9_]{{0,31}}$ 형식이어야 한다: {tid!r}")
                ok = False
            elif tid in seen:
                errors.append(f"{where}.id: {tid!r}가 중복된다")
                ok = False
            else:
                seen.add(tid)
                if model_re.match(tid):
                    errors.append(f"{where}.id: {tid!r}는 기체 모델 이름 형식({model_re.pattern})이다. "
                                  "Actor와 기체 모델의 이름이 겹친다")
                    ok = False
        start_s = t.get("start_s")
        if "start_s" in t:
            if not _is_number(start_s) or not 0 <= start_s <= TARGET_START_S_MAX:
                errors.append(f"{where}.start_s: 0 이상 {TARGET_START_S_MAX:.0f} 이하의 숫자여야 한다: {start_s!r}")
                ok = False
        loop = t.get("loop")
        if "loop" in t and not isinstance(loop, bool):
            errors.append(f"{where}.loop: true 또는 false여야 한다: {loop!r}")
            ok = False
        wps = t.get("waypoints")
        norm_wps = None
        if "waypoints" in t:
            norm_wps = _validate_waypoints(wps, where, errors)
            if norm_wps is None:
                ok = False
            else:
                n0 = len(errors)
                times = _check_times(norm_wps, where, errors)
                if times is not None:
                    lengths.append((i, times[-1]))
                ok = ok and len(errors) == n0
                if ok:
                    ok = _check_trajectory(norm_wps, loop is True, where, errors)
                if ok:
                    for v in posed_vehicles:
                        d = math.hypot(norm_wps[0]["x"] - v["pose"]["x"], norm_wps[0]["y"] - v["pose"]["y"])
                        if d < TARGET_SPAWN_CLEAR_M:
                            errors.append(f"{where}: t=0 위치와 기체 {v['id']}의 스폰 지점의 수평 거리 {d:.2f} m < "
                                          f"{TARGET_SPAWN_CLEAR_M} m")
                            ok = False
        if ok:
            out.append({"id": tid, "start_s": float(start_s), "loop": loop, "waypoints": norm_wps})
    if sum(ms for _, ms in lengths) > TARGETS_LENGTH_SUM_MAX_MS:
        errors.append(
            f"targets: 궤적 길이(마지막 waypoint의 t를 ms로 반올림한 값)의 합 {_ms_str(sum(ms for _, ms in lengths))} s가 상한 "
            f"{_ms_str(TARGETS_LENGTH_SUM_MAX_MS)} s를 넘는다. 표적별 길이: "
            + ", ".join(f"targets[{i}] {_ms_str(ms)} s" for i, ms in lengths))
    return out


def _validate_waypoints(wps, where, errors):
    """waypoints의 형식을 검사해 정규화한다(숫자는 float). 형식 위반이 있으면 None."""
    if not isinstance(wps, list):
        errors.append(f"{where}.waypoints: 목록이어야 한다")
        return None
    if len(wps) > WAYPOINTS_MAX:
        errors.append(f"{where}.waypoints: {len(wps)}개다(상한 {WAYPOINTS_MAX})")
    if len(wps) < 2:
        errors.append(f"{where}.waypoints: 2개 이상이어야 한다: {len(wps)}개")
    out, good = [], len(wps) <= WAYPOINTS_MAX and len(wps) >= 2
    for j, w in enumerate(wps):
        wwhere = f"{where}.waypoints[{j}]"
        if not isinstance(w, dict):
            errors.append(f"{wwhere}: {{t, x, y, z}} 매핑이어야 한다")
            good = False
            continue
        _unknown_keys(w, set(WAYPOINT_KEYS), wwhere, errors)
        missing = [key for key in WAYPOINT_KEYS if key not in w]
        bad = [key for key in WAYPOINT_KEYS if key in w and not _is_number(w[key])]
        if missing:
            errors.append(f"{wwhere}: 필수 key가 없다(기본값 없음): {', '.join(missing)}")
        if bad:
            errors.append(f"{wwhere}: 숫자가 아닌 값 {', '.join(bad)}")
        if missing or bad or any(key not in WAYPOINT_KEYS for key in w):
            good = False
            continue
        out.append({key: float(w[key]) for key in WAYPOINT_KEYS})
    return out if good else None


def _ms_str(ms):
    """정수 ms를 초 단위 소수 3자리 문자열로(예: 250 -> 0.250). 음수도 받는다."""
    sign = "-" if ms < 0 else ""
    return f"{sign}{abs(ms) // 1000}.{abs(ms) % 1000:03d}"


def _check_times(wps, where, errors):
    """형식이 맞는 waypoints의 시간 규칙. 위반은 errors에 더한다.

    x = t x 1000.0에서 t < 0이면 T를 만들지 않는다(첫 t 0과 엄격한 증가 규칙이 거부한다). x가
    TARGETS_LENGTH_SUM_MAX_MS + 0.5를 넘으면 T를 만들지 않고 그 waypoint를 거부한다(round가 이 범위에서만 돌아
    1e308 같은 값의 OverflowError가 없고, 합 규칙과 같은 상수와 영역이다). 그 밖은 T = round(x)다.
    길이 합에 넣을 수 있으면(t가 엄격히 증가하고 모든 waypoint에 T가 있음) 정수 ms T의 목록을, 아니면 None을 돌려준다.
    """
    ms = []
    for j, w in enumerate(wps):
        x = w["t"] * 1000.0
        if x < 0:
            ms.append(None)
        elif x > TARGETS_LENGTH_SUM_MAX_MS + 0.5:
            errors.append(f"{where}.waypoints[{j}].t: ms로 반올림한 시각이 {TARGETS_LENGTH_SUM_MAX_MS} ms를 넘는다: "
                          f"{w['t']!r}")
            ms.append(None)
        else:
            ms.append(round(x))
    if wps[0]["t"] != 0:
        errors.append(f"{where}.waypoints[0].t: 첫 t는 0이어야 한다: {wps[0]['t']!r}")
    increasing = True
    for j in range(1, len(wps)):
        if wps[j]["t"] <= wps[j - 1]["t"]:
            errors.append(f"{where}.waypoints[{j}].t: 엄격히 증가해야 한다: {wps[j - 1]['t']!r} 다음 {wps[j]['t']!r}")
            increasing = False
        elif None not in (ms[j - 1], ms[j]) and ms[j] - ms[j - 1] < TARGET_GAP_MIN_MS:
            errors.append(f"{where}.waypoints[{j}].t: 인접 waypoint의 시간 차 {ms[j] - ms[j - 1]} ms < {TARGET_GAP_MIN_MS} ms"
                          f"(T = round(t x 1000): {ms[j - 1]}, {ms[j]})")
    return ms if increasing and None not in ms else None


def _check_trajectory(wps, loop, where, errors):
    """형식과 시간 규칙을 통과한 waypoints의 궤적 규칙. 어기면 errors에 더하고 False."""
    n0 = len(errors)
    for j, w in enumerate(wps):
        if w["z"] < 0 or w["z"] > TARGET_COORD_Z_MAX_M:
            errors.append(f"{where}.waypoints[{j}].z: 0 이상 {TARGET_COORD_Z_MAX_M:.0f} m 이하여야 한다: {w['z']!r}")
        for key in ("x", "y"):
            if abs(w[key]) > TARGET_COORD_XY_MAX_M:
                errors.append(f"{where}.waypoints[{j}].{key}: |{key}|가 {TARGET_COORD_XY_MAX_M:.0f} m를 넘는다: {w[key]!r}")
    if len(errors) > n0:
        return False
    for j in range(1, len(wps)):
        a, b = wps[j - 1], wps[j]
        dt = b["t"] - a["t"]
        vxy = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt
        vz = abs(b["z"] - a["z"]) / dt
        if vxy > TARGET_SPEED_XY_MAX_MPS + TARGET_SPEED_EPS:
            errors.append(f"{where}.waypoints[{j}]: 구간 수평 속도 {vxy:.3f} m/s > {TARGET_SPEED_XY_MAX_MPS} m/s")
        if vz > TARGET_SPEED_Z_MAX_MPS + TARGET_SPEED_EPS:
            errors.append(f"{where}.waypoints[{j}]: 구간 수직 속도 {vz:.3f} m/s > {TARGET_SPEED_Z_MAX_MPS} m/s")
    if loop and any(wps[0][key] != wps[-1][key] for key in ("x", "y", "z")):
        errors.append(f"{where}: loop가 true이면 처음과 끝 waypoint의 x, y, z가 같아야 한다")
    return len(errors) == n0


def target_length_ms(target):
    """표적의 궤적 길이(정수 ms). 마지막 waypoint의 T다. start_s와 끝 정지 꼬리는 넣지 않는다."""
    return round(target["waypoints"][-1]["t"] * 1000)


def targets_length_sum_ms(targets):
    return sum(target_length_ms(t) for t in targets)


def validate_fleet(fleet):
    """fleet dict를 검사하고 정규화한 dict와 경고 목록을 돌려준다. 실패하면 FleetError.

    정규화 결과: {"world": {name, template, origin({lat,lon,alt} 숫자), speed_factor None},
                  "vehicles": [{id, airframe, pose{x,y,z,yaw} float, px4_params{이름: 문자열}}] (id 순),
                  "targets": [{id, start_s, loop, waypoints[{t,x,y,z}]}] (fleet.yaml 순서, 숫자는 float), "px4": {params_file, start}}
    """
    errors, warnings = [], []
    if not isinstance(fleet, dict):
        raise FleetError("fleet.yaml 최상위가 매핑이 아니다")
    _unknown_keys(fleet, FLEET_KEYS, "fleet", errors)
    for key in sorted(FLEET_KEYS):
        if key not in fleet:
            errors.append(f"fleet: 필수 key {key!r}가 없다")
    if errors:
        raise FleetError("\n".join(errors))

    if fleet["schema"] != FLEET_SCHEMA or isinstance(fleet["schema"], bool):
        errors.append(f"schema: {FLEET_SCHEMA}이어야 한다(월드 템플릿은 world.template이다): {fleet['schema']!r}")

    # world
    world = fleet["world"]
    out_world = {"name": None, "template": None, "origin": None, "speed_factor": None}
    if not isinstance(world, dict):
        errors.append("world: 매핑이어야 한다")
    else:
        _unknown_keys(world, WORLD_KEYS, "world", errors)
        if "file" in world:
            errors.append("world.file: 없어진 key다. 저장소 기준 월드 템플릿 경로 world.template을 쓴다(fleet schema 2)")
        name = world.get("name")
        if not isinstance(name, str) or not WORLD_NAME_RE.match(name):
            errors.append(f"world.name: ^[A-Za-z0-9_-]{{1,64}}$ 형식이어야 한다: {name!r}")
        out_world["name"] = name
        template = world.get("template")
        if (not isinstance(template, str) or not TEMPLATE_PATH_RE.match(template) or os.path.isabs(template)
                or ".." in template.split("/") or "." in template.split("/") or "" in template.split("/")):
            errors.append(f"world.template: 저장소 기준 상대 경로의 .sdf 파일이어야 한다(절대 경로와 ..은 거부): {template!r}")
        out_world["template"] = template
        origin = world.get("origin")
        if origin is None:
            errors.append("world.origin: 필수다. {lat, lon, alt}를 적어야 한다")
        elif not isinstance(origin, dict):
            errors.append("world.origin: {lat, lon, alt} 매핑이어야 한다")
        else:
            _unknown_keys(origin, set(ORIGIN_KEYS), "world.origin", errors)
            missing = [key for key in ORIGIN_KEYS if key not in origin]
            if missing:
                errors.append(f"world.origin: lat, lon, alt 셋을 모두 적어야 한다(빠짐: {', '.join(missing)})")
            else:
                vals = {key: origin[key] for key in ORIGIN_KEYS}
                bad = [key for key, v in vals.items() if not _is_number(v)]
                if bad:
                    errors.append(f"world.origin: 숫자가 아닌 값: {', '.join(bad)}")
                elif not (-90 <= vals["lat"] <= 90 and -180 <= vals["lon"] <= 180):
                    errors.append(f"world.origin: 위도 -90-90, 경도 -180-180 범위 밖: {vals}")
                else:
                    out_world["origin"] = vals
        if world.get("speed_factor") is not None:
            errors.append("world.speed_factor: 1a, 1b에서는 null이어야 한다(배속 기제는 Phase 3에서 정한다)")

    # px4
    px4 = fleet["px4"]
    out_px4 = {"params_file": None, "start": None}
    if not isinstance(px4, dict):
        errors.append("px4: 매핑이어야 한다")
    else:
        _unknown_keys(px4, PX4_KEYS, "px4", errors)
        pf = px4.get("params_file")
        if not isinstance(pf, str) or not pf or os.path.isabs(pf) or ".." in pf.split("/"):
            errors.append(f"px4.params_file: 저장소 기준 상대 경로여야 한다: {pf!r}")
        out_px4["params_file"] = pf
        st = px4.get("start")
        if st not in PX4_START:
            errors.append(f"px4.start: {' 또는 '.join(PX4_START)}이어야 한다: {st!r}")
        out_px4["start"] = st

    # vehicles
    vehicles = fleet["vehicles"]
    out_vehicles = []
    if not isinstance(vehicles, list) or not vehicles:
        errors.append("vehicles: 기체가 하나 이상인 목록이어야 한다")
        vehicles = []
    seen = set()
    for i, v in enumerate(vehicles):
        where = f"vehicles[{i}]"
        if not isinstance(v, dict):
            errors.append(f"{where}: 매핑이어야 한다")
            continue
        _unknown_keys(v, VEHICLE_KEYS, where, errors)
        vid = v.get("id")
        if isinstance(vid, bool) or not isinstance(vid, int) or not VEHICLE_MIN <= vid <= VEHICLE_MAX:
            errors.append(f"{where}.id: {VEHICLE_MIN}-{VEHICLE_MAX} 정수여야 한다: {vid!r}")
            vid = None
        elif vid in seen:
            errors.append(f"{where}.id: {vid}가 중복된다")
        else:
            seen.add(vid)
        af = v.get("airframe")
        if af not in ALLOWED_AIRFRAMES:
            errors.append(f"{where}.airframe: 허용 목록({', '.join(ALLOWED_AIRFRAMES)})에 없다: {af!r}")
        pose = v.get("pose")
        out_pose = None
        if not isinstance(pose, dict):
            errors.append(f"{where}.pose: {{x, y, z, yaw}} 매핑이어야 한다")
        else:
            _unknown_keys(pose, set(POSE_KEYS), f"{where}.pose", errors)
            missing = [key for key in POSE_KEYS if key not in pose]
            bad = [key for key in POSE_KEYS if key in pose and not _is_number(pose[key])]
            if missing:
                errors.append(f"{where}.pose: 빠진 key {', '.join(missing)}")
            elif bad:
                errors.append(f"{where}.pose: 숫자가 아닌 값 {', '.join(bad)}")
            else:
                out_pose = {key: float(pose[key]) for key in POSE_KEYS}
        params = v.get("px4_params", {})
        out_params = {}
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errors.append(f"{where}.px4_params: 매핑이어야 한다")
            params = {}
        for pname, pval in params.items():
            if _check_param_name(pname, f"{where}.px4_params", errors):
                s = _param_value_str(pname, pval, f"{where}.px4_params", errors)
                if s is not None:
                    out_params[pname] = s
        out_vehicles.append({"id": vid, "airframe": af, "pose": out_pose, "px4_params": out_params})

    # 간격 (수평 거리. 기체는 지면에 스폰된다)
    posed = [v for v in out_vehicles if v["id"] is not None and v["pose"] is not None]
    for a_i, a in enumerate(posed):
        for b in posed[a_i + 1:]:
            d = math.hypot(a["pose"]["x"] - b["pose"]["x"], a["pose"]["y"] - b["pose"]["y"])
            if d < SPACING_REJECT_M:
                errors.append(f"vehicles: 기체 {a['id']}와 {b['id']}의 수평 간격 {d:.2f} m < {SPACING_REJECT_M} m")
            elif d < SPACING_WARN_M:
                warnings.append(f"기체 {a['id']}와 {b['id']}의 수평 간격 {d:.2f} m < {SPACING_WARN_M} m")

    # targets(기체 검증 뒤. t=0 위치를 기체 스폰과 비교한다)
    out_targets = _validate_targets(fleet["targets"], posed, errors)

    if errors:
        raise FleetError("\n".join(errors))
    out_vehicles.sort(key=lambda v: v["id"])
    return {"world": out_world, "vehicles": out_vehicles, "targets": out_targets, "px4": out_px4}, warnings


def parse_params_env(text, where="px4.params_file"):
    """PX4_PARAM_<이름>=<값> 줄만 있는 env 파일을 {이름: 값}으로. 주석(#)과 빈 줄은 건너뛴다."""
    out, errors = {}, []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^PX4_PARAM_([^=]*)=(.*)\Z", s)
        if not m:
            errors.append(f"{where}:{lineno}: PX4_PARAM_<이름>=<값> 형식이 아니다: {s!r}")
            continue
        name, val = m.group(1), m.group(2)
        if _check_param_name(name, f"{where}:{lineno}", errors):
            if not PARAM_VALUE_RE.match(val):
                errors.append(f"{where}:{lineno}: 값에 공백, 따옴표, #을 쓸 수 없다: {val!r}")
            elif name in out:
                errors.append(f"{where}:{lineno}: {name}가 두 번 나온다")
            else:
                out[name] = val
    if errors:
        raise FleetError("\n".join(errors))
    if not out:
        raise FleetError(f"{where}: PX4_PARAM_ 항목이 없다")
    return out


def parse_participant_max(xml_text):
    """cyclonedds.xml의 MaxAutoParticipantIndex 값(정수)."""
    root = ET.fromstring(xml_text)
    found = [el.text for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "MaxAutoParticipantIndex"]
    if len(found) != 1 or not (found[0] or "").strip().isdigit():
        raise FleetError(f"{CYCLONEDDS_REL}: MaxAutoParticipantIndex가 정확히 하나의 정수여야 한다: {found}")
    return int(found[0].strip())


# ---------------------------------------------------------------- 월드 SDF 생성과 기대 GPS
def _tag(el):
    return el.tag if isinstance(el.tag, str) else None  # 주석과 처리 명령은 tag가 함수다


def _parse_sdf(text, where):
    """XML 본문을 주석을 보존해서 읽는다."""
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        return ET.fromstring(text, parser=parser)
    except ET.ParseError as e:
        raise FleetError(f"{where}: XML 파싱 실패: {e}") from e


def parse_world_template(text, where="world.template"):
    """월드 템플릿 본문을 읽고(주석 보존) 거부 조건을 검사한 뒤 루트 요소를 돌려준다. 어기면 FleetError.

    거부: 루트가 sdf가 아님, <world>가 정확히 하나가 아님(sdf 직속), 월드 직속 plugin, spherical_coordinates,
    actor, include. 월드 직속 plugin이 있으면 gz-sim이 GZ_SIM_SERVER_CONFIG_PATH의 system plugin 목록을
    통째로 무시하고, include된 모델의 월드 수준 plugin은 생성기가 볼 수 없다.
    """
    root = _parse_sdf(text, where)
    errors = []
    if root.tag != "sdf":
        errors.append(f"{where}: 루트 요소가 sdf가 아니다: {root.tag!r}")
    all_worlds = [el for el in root.iter() if _tag(el) == "world"]
    worlds = [el for el in root if _tag(el) == "world"]
    if len(all_worlds) != 1 or len(worlds) != 1:
        errors.append(f"{where}: <world>가 sdf 직속으로 정확히 하나여야 한다(전체 {len(all_worlds)}개, 직속 {len(worlds)}개)")
    else:
        for child in worlds[0]:
            if _tag(child) in WORLD_FORBIDDEN_CHILDREN:
                errors.append(f"{where}: 월드 직속 <{child.tag}>는 둘 수 없다")
    if errors:
        raise FleetError("\n".join(errors))
    return root


def _f6(v):
    """Actor 요소의 실수 표기: 고정 소수점 6자리, 지수 표기 없음, -0은 0."""
    out = format(v, ".6f")
    return "0.000000" if out == "-0.000000" else out


def actor_samples(target, dt_ms=ACTOR_SAMPLE_DT_MS):
    """표적 궤적을 간격 dt_ms 이하로 촘촘히 나눈 표본 [(T_ms, x, y, z)]. T는 start_s 기준 정수 ms다.

    원래 waypoint 시각은 T = round(t x 1000)이고, 구간마다 n = ceil(구간 길이 / dt_ms)개(최소 1)로 나눠
    표본 시각 T_i + (구간 길이 x j) // n(정수 연산)에 선형 보간한다. 원래 waypoint는 모두 정확히 들어간다.
    정지 구간도 같은 규칙이다. 끝 정지 꼬리는 여기에 넣지 않는다(actor_tail). Gazebo Actor는 spline이라
    꺾이는 점 앞뒤에서 TargetState와 어긋난다(화면 확인용).
    """
    wps = target["waypoints"]
    ms = [round(w["t"] * 1000) for w in wps]
    out = []
    for i in range(len(wps) - 1):
        a, b, span = wps[i], wps[i + 1], ms[i + 1] - ms[i]
        n = max(1, -(-span // dt_ms))
        for j in range(n):
            at = ms[i] + (span * j) // n
            r = (at - ms[i]) / span
            out.append((at, *(a[key] + (b[key] - a[key]) * r for key in WAYPOINT_KEYS[1:])))
    last = wps[-1]
    out.append((ms[-1], last["x"], last["y"], last["z"]))
    return out


def actor_tail(target):
    """loop false 표적의 끝 정지 두 점 [(T_ms, x, y, z)], loop true는 빈 목록.

    gz-sim 8.15.0 렌더링은 <loop>false</loop>인 Actor에서 delay_start가 0이면 끝나지 않는 루프에 빠지고,
    0보다 크면 첫 waypoint에서 움직이지 않는다. 그래서 <loop>는 항상 true이고 정지는 마지막 점 뒤 같은 위치의 두 점(250 ms 뒤, 86400 s 뒤)으로 나타낸다. 첫 점은 마지막 점의
    Catmull-Rom 접선을 0으로 만든다. 표본 간격 규칙(sampler)을 지나지 않고 두 점을 그대로 더한다.
    """
    if target["loop"]:
        return []
    last = target["waypoints"][-1]
    t_last = round(last["t"] * 1000)
    return [(t_last + step, last["x"], last["y"], last["z"]) for step in (ACTOR_TAIL_STEP_MS, ACTOR_HOLD_MS)]


def _indent_tree(node, indent, step="  "):
    """node 아래를 줄 단위로 들여쓴다(indent는 node 자신의 들여쓰기, 앞의 줄바꿈 포함). tail은 호출하는 쪽이 정한다."""
    if len(node):
        node.text = indent + step
        for child in node:
            _indent_tree(child, indent + step, step)
            child.tail = indent + step
        node[-1].tail = indent


def build_actor(target, indent):
    """표적 하나의 <actor> 요소(B6 Actor 명세 판 2). 이름은 target_id 그대로다.

    link 하나에 visual 하나(충돌 없음, 물리 대상 아님)와 script 궤적뿐이고 plugin, skin, animation은 없다.
    actor pose는 0이고 waypoint pose가 world ENU 절대 좌표다(자세는 0). start_s는 delay_start로만 쓴다.
    <loop>는 항상 true이고 loop false는 끝 정지 꼬리(actor_tail)로 나타낸다.
    """
    zero = "0.000000"
    actor = ET.Element("actor", name=target["id"])

    def sub(parent, tag, text=None, **attrib):
        el = ET.SubElement(parent, tag, **attrib)
        if text is not None:
            el.text = text
        return el

    sub(actor, "pose", " ".join([zero] * 6))
    link = sub(actor, "link", name="link")
    visual = sub(link, "visual", name="visual")
    sub(sub(sub(visual, "geometry"), "sphere"), "radius", ACTOR_SPHERE_RADIUS_M)
    material = sub(visual, "material")
    for tag, val in ACTOR_MATERIAL:
        sub(material, tag, val)
    script = sub(actor, "script")
    sub(script, "loop", "true")
    sub(script, "delay_start", format(target["start_s"], ".3f"))
    sub(script, "auto_start", "true")
    traj = sub(script, "trajectory", id="0", type=ACTOR_TRAJECTORY_TYPE, tension="0.0")
    for t, x, y, z in actor_samples(target) + actor_tail(target):
        point = sub(traj, "waypoint")
        sub(point, "time", _ms_str(t))
        sub(point, "pose", " ".join([_f6(x), _f6(y), _f6(z), zero, zero, zero]))
    _indent_tree(actor, indent)
    return actor


def build_world_sdf(fleet_norm, template_text):
    """템플릿에 <world name>과 <spherical_coordinates>(world.origin, heading 0, ENU)를 넣은 월드 SDF 본문.

    표적마다 <actor>(build_actor)를 spherical_coordinates 뒤에 fleet.yaml 순서대로 넣는다.
    출력을 다시 파싱해 구성 보장을 단정한다(어기면 FleetError, 생성기 버그): spherical_coordinates 정확히 하나,
    월드 직속 plugin 0, actor 이름 집합 = 표적 id 집합, actor 안의 plugin, skin, animation, collision 없음,
    script와 loop true, 표본 시각(정수 ms)과 간격, 원래 waypoint의 포함, loop false의 끝 정지 꼬리, dynamic_pose 없음.
    Actor를 만들기 전에 궤적 길이의 합을 다시 본다.
    """
    world = fleet_norm["world"]
    root = parse_world_template(template_text)
    el = next(c for c in root if _tag(c) == "world")
    taken = {c.get("name") for c in el if _tag(c) in TEMPLATE_NAMED_CHILDREN and c.get("name")}
    clash = sorted(t["id"] for t in fleet_norm["targets"] if t["id"] in taken)
    if clash:
        raise FleetError(f"targets: id {', '.join(clash)}가 월드 템플릿 최상위 <model>, <actor>, <light>의 이름과 같다"
                         "(Actor 이름이 target_id라 정답 pose와 GUI가 다른 엔티티를 보게 된다)")
    total = targets_length_sum_ms(fleet_norm["targets"])
    if total > TARGETS_LENGTH_SUM_MAX_MS:
        raise FleetError(f"targets: 궤적 길이의 합 {_ms_str(total)} s가 상한 {_ms_str(TARGETS_LENGTH_SUM_MAX_MS)} s를 넘는다")
    el.set("name", world["name"])
    # 마지막 자식 뒤에 넣고, 템플릿의 들여쓰기(자식 들여쓰기 = world.text, 닫는 들여쓰기 = 마지막 자식의 tail)를 따른다
    child_indent = el.text if el.text and not el.text.strip() else "\n    "
    close_indent = el[-1].tail if len(el) and el[-1].tail and not el[-1].tail.strip() else "\n  "
    inner_indent = child_indent + "  "
    sc = ET.Element("spherical_coordinates")
    origin = world["origin"]
    for tag, val in (("surface_model", "EARTH_WGS84"), ("world_frame_orientation", "ENU"),
                     ("latitude_deg", _decimal_str(origin["lat"])), ("longitude_deg", _decimal_str(origin["lon"])),
                     ("elevation", _decimal_str(origin["alt"])), ("heading_deg", "0")):
        sub = ET.SubElement(sc, tag)
        sub.text = val
        sub.tail = inner_indent
    sc[-1].tail = child_indent
    sc.text = inner_indent
    added = [sc] + [build_actor(t, child_indent) for t in fleet_norm["targets"]]
    for node in added:
        node.tail = child_indent
    added[-1].tail = close_indent
    if len(el):
        el[-1].tail = child_indent
    else:
        el.text = child_indent
    el.extend(added)
    text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    check_world_sdf(text, fleet_norm)
    return text


TIME_TEXT_RE = re.compile(r"^[0-9]+\.[0-9]{3}\Z")


def _check_actor(actor, target):
    """생성된 <actor> 하나의 단정. 문제 문장의 목록을 돌려준다."""
    name, problems = target["id"], []
    bad = sorted({el.tag for el in actor.iter() if _tag(el) in ACTOR_FORBIDDEN_DESCENDANTS})
    if bad:
        problems.append(f"actor {name}: 금지 요소 {bad}가 있다")
    if actor.find("script") is None:
        return problems + [f"actor {name}: <script>가 없다(gz-sim 렌더링이 궤적 길이 0에서 끝나지 않는 루프에 빠진다)"]
    if [el.text for el in actor.findall("script/loop")] != ["true"]:
        problems.append(f"actor {name}: <loop>가 정확히 하나의 true가 아니다(false이면 delay_start 0에서 gz-sim 렌더링이 끝나지 않고, 0보다 크면 첫 waypoint에서 움직이지 않는다)")
    if actor.findtext("script/delay_start") != format(target["start_s"], ".3f"):
        problems.append(f"actor {name}: delay_start가 start_s와 다르다")
    points = [(w.findtext("time"), w.findtext("pose")) for w in actor.iter("waypoint")]
    if not points:
        return problems + [f"actor {name}: waypoint가 없다"]
    if not all(t and TIME_TEXT_RE.match(t) for t, _ in points):
        return problems + [f"actor {name}: waypoint 시각이 소수 3자리 비음수 수가 아니다"]
    times = [int(t.replace(".", "")) for t, _ in points]
    if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])):
        problems.append(f"actor {name}: waypoint 시각이 0에서 시작해 엄격히 증가하지 않는다")
    body, tail = len(actor_samples(target)), len(actor_tail(target))
    if len(points) != body + tail:
        problems.append(f"actor {name}: waypoint가 {len(points)}개다(궤적 부분 {body} + 꼬리 {tail}이어야 한다)")
    gaps = [b - a for a, b in zip(times, times[1:])]
    if tail:
        gaps = gaps[:-1]  # 꼬리의 마지막 구간(86400 s 정지)은 예외다
        if len(points) >= 3 and len({p for _, p in points[-3:]}) != 1:
            problems.append(f"actor {name}: loop false인데 마지막 세 점의 위치가 같지 않다")
        t_last = round(target["waypoints"][-1]["t"] * 1000)
        if len(times) >= 2 and times[-2] != t_last + ACTOR_TAIL_STEP_MS:
            problems.append(f"actor {name}: 꼬리 첫 점의 시각 {times[-2]} ms != 마지막 waypoint + {ACTOR_TAIL_STEP_MS} ms")
        want_end = t_last + ACTOR_HOLD_MS
        if times[-1] != want_end:
            problems.append(f"actor {name}: 마지막 시각 {times[-1]} ms != 마지막 waypoint + {ACTOR_HOLD_MS} ms")
    elif abs(times[-1] - round(target["waypoints"][-1]["t"] * 1000)) > 0:
        problems.append(f"actor {name}: 마지막 시각 {times[-1]} ms가 표적의 마지막 T와 다르다")
    if any(g < TARGET_GAP_MIN_MS or g > ACTOR_SAMPLE_DT_MS for g in gaps):
        problems.append(f"actor {name}: 인접 waypoint 시각 차가 {TARGET_GAP_MIN_MS}-{ACTOR_SAMPLE_DT_MS} ms 밖이다")
    present = set(points)
    zero = "0.000000"
    for w in target["waypoints"]:
        want = (_ms_str(round(w["t"] * 1000)), " ".join([_f6(w["x"]), _f6(w["y"]), _f6(w["z"]), zero, zero, zero]))
        if want not in present:
            problems.append(f"actor {name}: 원래 waypoint {want}가 표본에 없다")
    return problems


def check_world_sdf(text, fleet_norm):
    """생성된 월드 SDF를 다시 읽어 구성 보장을 단정한다. 어기면 FleetError."""
    world, origin = fleet_norm["world"], fleet_norm["world"]["origin"]
    problems = []
    root = _parse_sdf(text, "생성된 월드")
    el = next(c for c in root if _tag(c) == "world")
    if el.get("name") != world["name"]:
        problems.append(f"world name {el.get('name')!r} != {world['name']!r}")
    # wrapper(gz_server.sh)는 줄 단위로 grep한다. 여는 태그와 name이 한 줄에 있고 주석 안에 같은 문자열이 없어야 한다
    if text.count("<world ") != 1 or not any(line.lstrip().startswith("<world name=") for line in text.splitlines()):
        problems.append("<world name=...>가 한 줄에 정확히 한 번이 아니다")
    if text.count("<spherical_coordinates") != 1:
        problems.append(f"'<spherical_coordinates' 문자열이 {text.count('<spherical_coordinates')}번 나온다(정확히 1)")
    scs = [c for c in el if _tag(c) == "spherical_coordinates"]
    if len(scs) != 1:
        problems.append(f"world 직속 spherical_coordinates가 {len(scs)}개다(정확히 1)")
    else:
        got = {c.tag: (c.text or "").strip() for c in scs[0]}
        want = {"surface_model": "EARTH_WGS84", "world_frame_orientation": "ENU", "heading_deg": "0"}
        for key, val in want.items():
            if got.get(key) != val:
                problems.append(f"spherical_coordinates.{key}={got.get(key)!r} != {val!r}")
        for key, field in (("latitude_deg", "lat"), ("longitude_deg", "lon"), ("elevation", "alt")):
            try:
                same = float(got[key]) == float(origin[field])
            except (KeyError, ValueError):
                same = False
            if not same:
                problems.append(f"spherical_coordinates.{key}={got.get(key)!r} != world.origin.{field}={origin[field]!r}")
    if [c for c in el if _tag(c) == "plugin"]:
        problems.append("world 직속 plugin이 있다")
    actors = sorted(c.get("name") for c in el if _tag(c) == "actor")
    if actors != sorted(t["id"] for t in fleet_norm["targets"]):
        problems.append(f"actor 이름 집합 {actors} != 표적 id 집합")
    by_name = {c.get("name"): c for c in el if _tag(c) == "actor"}
    for t in fleet_norm["targets"]:
        if t["id"] in by_name:
            problems.extend(_check_actor(by_name[t["id"]], t))
    if "dynamic_pose" in text:
        problems.append("dynamic_pose 문자열이 있다")
    if problems:
        raise FleetError("월드 SDF 단정 실패(버그):\n" + "\n".join(problems))


def expect_gps(origin, pose, airframe):
    """스폰 pose의 GNSS 센서(base_link) 기대 위경도와 고도. 스모크 S2의 기대값이다(운용 변환이 아니다).

    원점 위도에서 계산한 WGS84 곡률 반지름의 국소 근사다. world ENU의 x는 동쪽, y는 북쪽이다.
    고도 = world.origin.alt + 스폰 z + 센서 높이. 센서 오프셋이 수직뿐이라 yaw와 무관하다.
    gz-math LOCAL2와 원점에서 100 m 안에서 1e-8 도(약 1 mm) 안으로 맞는다(단위 테스트가 고정한다).
    """
    lat0, lon0 = math.radians(origin["lat"]), math.radians(origin["lon"])
    w = 1.0 - WGS84_E2 * math.sin(lat0) ** 2
    m_radius = WGS84_A_M * (1.0 - WGS84_E2) / w ** 1.5  # 자오선 곡률 반지름
    n_radius = WGS84_A_M / math.sqrt(w)  # 묘유선 곡률 반지름
    lat = lat0 + pose["y"] / m_radius
    lon = lon0 + pose["x"] / (n_radius * math.cos(lat0))
    return {"lat": round(math.degrees(lat), 9), "lon": round(math.degrees(lon), 9),
            "alt": round(origin["alt"] + pose["z"] + AIRFRAME_SENSOR_Z_M[airframe], 6)}


# ---------------------------------------------------------------- compose와 stack.json 구조
def _bind(source, target, read_only):
    # 긴 형식. create_host_path를 끄므로 없는 원본 경로를 dockerd가 root 소유로 만들지 않고 실패한다.
    return {"type": "bind", "source": source, "target": target, "read_only": read_only,
            "bind": {"create_host_path": False}}


def _healthy(*names):
    return {n: {"condition": "service_healthy"} for n in names}


def _base(image):
    return {"image": image, "network_mode": "host", "restart": "no"}


def oracle_vehicles(vehicle_out):
    """IDSIM_ORACLE_VEHICLES 값: 공백으로 이은 `<vehicle_id>=<gz 모델 이름>`(px4_1=x500_1 px4_2=x500_2)."""
    return " ".join(f"{v['vehicle_id']}={v['gz_model_name']}" for v in vehicle_out)


def oracle_command():
    """sim-oracle의 bash -c 본문. ROS 환경을 읽고 sim-base의 python3으로 마운트된 sim_oracle.py를 실행한다."""
    return f". /opt/ros/$${{ROS_DISTRO}}/setup.sh && exec python3 {SIM_PKG_IN_CONTAINER}/{ORACLE_SCRIPT}"


def ops_healthcheck(fqn):
    """ops-N의 healthcheck 명령. lifecycle 상태가 active로 시작하면 통과한다.

    /opt/ros/<distro>/setup.sh만 읽는다(workspace overlay와 로그인 셸 없음). 출력을 버리지 않으므로
    .State.Health.Log에 `unconfigured [1]` 같은 상태가 남는다. $$는 compose에서 리터럴 $다.
    """
    return (". /opt/ros/$${ROS_DISTRO}/setup.sh; "
            f"ROS_LOG_DIR=/tmp/hc timeout {OPS_PROBE_TIMEOUT_S} ros2 lifecycle get --no-daemon {fqn} > /tmp/hc.out 2>&1; "
            "cat /tmp/hc.out; grep -q '^active' /tmp/hc.out")


def build(fleet_norm, ctx):
    """정규화된 fleet(validate_fleet 결과)와 생성 인자 ctx에서 (compose dict, stack dict, 경고 목록).

    ctx key: k, variant, uid, gid, run_id, host_repo_root, host_run_dir, images{xrce-agent, sim-base, px4,
    ros-ws}, lichtblick_image, generated_at, git_commit, git_dirty, inputs{fleet, px4_params_file, versions_env, cyclonedds_xml: {path, sha256}},
    params_env{이름: 값}, participant_index_max.
    """
    warnings = []
    k, variant = ctx["k"], ctx["variant"]
    if isinstance(k, bool) or not isinstance(k, int) or not STACK_MIN <= k <= STACK_MAX:
        raise FleetError(f"스택 번호 k는 {STACK_MIN}-{STACK_MAX}: {k!r}")
    if variant not in VARIANTS:
        raise FleetError(f"variant는 {', '.join(VARIANTS)} 중 하나: {variant!r}")
    for key in ("uid", "gid"):
        if isinstance(ctx[key], bool) or not isinstance(ctx[key], int) or ctx[key] < 0:
            raise FleetError(f"{key}는 0 이상 정수: {ctx[key]!r}")
    if not RUN_ID_RE.match(ctx["run_id"]):
        raise FleetError(f"run id 형식 위반(^[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}$): {ctx['run_id']!r}")
    repo, run_dir = ctx["host_repo_root"], ctx["host_run_dir"]
    for name, p in (("host-repo-root", repo), ("run-dir", run_dir)):
        if not PATH_SAFE_RE.match(p) or p != os.path.normpath(p):
            raise FleetError(f"{name}는 공백 없는 정규화된 절대 경로여야 한다: {p!r}")
    run_rel = os.path.relpath(run_dir, repo)
    if run_rel == "." or run_rel.startswith(".."):
        raise FleetError(f"run-dir({run_dir})는 저장소({repo}) 안에 있어야 한다(ros-ws의 /opt/idsim 마운트로 보인다)")
    if os.path.dirname(run_dir) != f"{repo}/artifacts/runs":
        raise FleetError(f"run-dir({run_dir})의 부모는 저장소 아래 {repo}/artifacts/runs여야 한다")
    if os.path.basename(run_dir) != ctx["run_id"]:
        raise FleetError(f"run-dir의 마지막 요소({os.path.basename(run_dir)})가 run id({ctx['run_id']})와 다르다")
    pmax = ctx["participant_index_max"]
    check_port_plan(pmax)

    vehicles = fleet_norm["vehicles"]
    world = fleet_norm["world"]
    if variant == "embedded":
        if len(vehicles) != 1:
            raise FleetError(f"embedded 변형은 기체 1대만 허용한다: {len(vehicles)}대")
        warnings.append("embedded 변형에는 원점을 적용하는 gazebo 서비스가 없어 world.origin을 무시한다(stack.json에 null)")
        warnings.append(f"embedded 변형의 PX4는 이미지의 {PX4_GZ_WORLDS}/{world['name']}.sdf를 연다. "
                        f"world.template({world['template']})은 월드를 만들지 않는다")
    standalone = variant == "standalone"
    if not standalone and fleet_norm["targets"]:
        warnings.append(f"embedded 변형에는 표적 어댑터와 월드 생성이 없어 targets {len(fleet_norm['targets'])}개를 무시한다"
                        "(stack.json의 targets는 빈 목록)")
    targets = fleet_norm["targets"] if standalone else []
    origin = world["origin"] if standalone else None
    world_file_rel = f"{WORLD_DIR}/{world['name']}.sdf" if standalone else None
    if "world_template" not in ctx["inputs"]:
        raise FleetError("ctx.inputs에 world_template {path, sha256}가 없다")
    images = ctx["images"]
    user = f"{ctx['uid']}:{ctx['gid']}"
    domain = ros_domain(k)
    partition = f"idsim-{k}"
    aport = agent_port(k)
    aport_hex = f"{aport:04X}"
    project = f"idsim-{k}"
    run_in_container = f"{REPO_IN_CONTAINER}/{run_rel}"
    sim_pkg_host = f"{repo}/{SIM_PKG_REL}"
    params_file_host = f"{repo}/{fleet_norm['px4']['params_file']}"
    sequential = fleet_norm["px4"]["start"] == "sequential"
    gz_env = {"GZ_PARTITION": partition, "GZ_IP": GZ_IP}
    ros_env = {
        "RMW_IMPLEMENTATION": RMW,
        "CYCLONEDDS_URI": CYCLONEDDS_URI,
        "ROS_DOMAIN_ID": str(domain),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/tmp",
    }

    services = {}

    # xrce-agent: root. ROS_DOMAIN_ID를 주지 않는다(도메인은 PX4 client가 세션 생성 때 넘긴다).
    services["xrce-agent"] = dict(_base(images["xrce-agent"]), **{
        "command": ["udp4", "-p", str(aport)],
        # PID 1은 SIGTERM을 버린다(기본 처리기가 없다). init이 신호를 넘겨 compose down이 유예 끝까지 기다리지 않게 한다
        "init": True,
        "healthcheck": {
            # /proc/net/udp의 local_address 열에서 포트(16진수, 생성기가 계산)를 찾는다
            "test": ["CMD-SHELL", f'grep -qE "^ *[0-9]+: [0-9A-F]+:{aport_hex} " /proc/net/udp'],
            "interval": "5s", "timeout": "5s", "retries": 6, "start_period": "10s",
        },
    })

    if standalone:
        genv = dict(gz_env)
        genv.update({
            "GZ_SIM_SERVER_CONFIG_PATH": GZ_SERVER_CONFIG,
            "GZ_SIM_RESOURCE_PATH": GZ_RESOURCE_PATH,
            "IDSIM_WORLD_NAME": world["name"],
            "IDSIM_WORLD_FILE": f"{WORLD_IN_CONTAINER}/{world['name']}.sdf",
        })
        services["gazebo"] = dict(_base(images["sim-base"]), **{
            # root로 실행한다(호스트에 쓰지 않는다). wrapper 계약: ros_ws/src/idsim_sim/scripts/gz_server.sh 머리 주석
            "environment": genv,
            "command": [f"{SIM_PKG_IN_CONTAINER}/scripts/gz_server.sh"],
            "volumes": [_bind(sim_pkg_host, SIM_PKG_IN_CONTAINER, True),
                        _bind(f"{run_dir}/{WORLD_DIR}", WORLD_IN_CONTAINER, True)],
            "healthcheck": {
                "test": ["CMD-SHELL",
                         f'gz service -i --service /world/{world["name"]}/scene/info | grep -q "Service providers"'
                         f" && test -f {GZ_READY_FILE}"],
                "interval": "5s", "timeout": "5s", "retries": 6, "start_period": "90s",
            },
            "depends_on": _healthy("xrce-agent"),
        })

    vehicle_out = []
    prev = None
    for v in vehicles:
        n = v["id"]
        autostart, sim_model, model = split_airframe(v["airframe"])
        svc = f"px4-{n}"
        p = v["pose"]
        env = {
            "HOME": "/tmp",
            "PX4_SYS_AUTOSTART": str(autostart),
            "PX4_SIM_MODEL": sim_model,
            "PX4_GZ_WORLD": world["name"],
            "PX4_GZ_MODELS": PX4_GZ_MODELS,
            "PX4_GZ_MODEL_POSE": ",".join(_decimal_str(x) for x in (p["x"], p["y"], p["z"], 0, 0, p["yaw"])),
            "PX4_UXRCE_DDS_NS": f"px4_{n}",
            "PX4_UXRCE_DDS_PORT": str(aport),
            "ROS_DOMAIN_ID": str(domain),
            "IDSIM_MAVLINK_OFFSET": str(mavlink_offset(k)),
        }
        env.update(gz_env)
        if standalone:
            env["PX4_GZ_STANDALONE"] = "1"
        else:
            env["HEADLESS"] = "1"
        for pname, pval in sorted(v["px4_params"].items()):
            env[f"PX4_PARAM_{pname}"] = pval
            if pname in ctx["params_env"] and ctx["params_env"][pname] != pval:
                warnings.append(f"기체 {n}: px4_params.{pname}={pval}가 공통 파일 값 {ctx['params_env'][pname]}을 덮는다")
        deps = _healthy("xrce-agent", "gazebo") if standalone else _healthy("xrce-agent")
        if sequential and prev is not None:
            deps[prev] = {"condition": "service_healthy"}
        services[svc] = dict(_base(images["px4"]), **{
            "user": user,
            "working_dir": PX4_ROOTFS,
            "env_file": [params_file_host],
            "environment": env,
            # -d: 대화형 셸 없이 데몬으로. 작업 디렉터리 rootfs/N은 실행 디렉터리의 px4-N(중첩 마운트 금지)
            "command": ["px4", "-d", "-i", str(n)],
            "volumes": [_bind(f"{run_dir}/px4-{n}", f"{PX4_ROOTFS}/{n}", False)],
            "healthcheck": {
                "test": ["CMD-SHELL", f"px4-uxrce_dds_client --instance {n} status | grep -q 'Running, connected'"],
                "interval": "5s", "timeout": "5s", "retries": 6,
                "start_period": "45s" if standalone else "90s",
            },
            "depends_on": deps,
        })
        prev = svc
        vid = f"px4_{n}"
        expected = dict(ctx["params_env"])
        expected.update(v["px4_params"])
        vehicle_out.append({
            "id": n,
            "instance": n,
            "ns": f"/px4_{n}",
            "px4_ns": f"px4_{n}",
            "vehicle_id": vid,
            "params_file": f"{PARAMS_DIR}/ops-{n}.yaml" if standalone else None,
            "executor_node": f"/{vid}/{EXECUTOR_NODE_NAME}" if standalone else None,
            "sysid": n + 1,
            "uxrce_key": n + 1,
            "airframe": v["airframe"],
            "autostart": autostart,
            "sim_model": sim_model,
            "gz_model_name": f"{model}_{n}",
            "pose": dict(p),
            "expect_gps": expect_gps(world["origin"], p, v["airframe"]) if standalone else None,
            "service": svc,
            "mavlink": vehicle_mavlink(k, n),
            "rootfs_dir": f"px4-{n}",
            "ulog_dir": f"px4-{n}/log",
            "host_rootfs_dir": f"{run_dir}/px4-{n}",
            "expected_params": expected,
            "derived_params": {
                "MAV_SYS_ID": str(n + 1),
                "UXRCE_DDS_KEY": str(n + 1),
                "UXRCE_DDS_DOM_ID": str(domain),
                "SYS_AUTOSTART": str(autostart),
            },
        })
    px4_services = [v["service"] for v in vehicle_out]
    ops_services = [f"ops-{v['id']}" for v in vehicle_out] if standalone else []

    def ros_ws_service(log_name, extra_env=None):
        env = dict(ros_env)
        env["ROS_LOG_DIR"] = f"{run_in_container}/ros_log/{log_name}"
        env.update(extra_env or {})
        return dict(_base(images["ros-ws"]), **{
            "user": user,
            "environment": env,
            # 저장소 전체 하나만(설정 파일을 따로 겹쳐 마운트하지 않는다). 실행 디렉터리가 이 아래에 있다
            "volumes": [_bind(repo, REPO_IN_CONTAINER, False)],
        })

    if standalone:
        bridge = ros_ws_service("bridge", gz_env)
        bridge.update({
            "command": ["ros2", "run", "ros_gz_bridge", "parameter_bridge", *BRIDGE_TOPIC_ARGS],
            "healthcheck": {
                "test": ["CMD-SHELL", ". /opt/ros/$${ROS_DISTRO}/setup.sh && "
                         "ROS_LOG_DIR=/tmp/hc timeout 4 ros2 topic echo --once --no-daemon /clock > /dev/null"],
                # start_period 동안은 start_interval 5초로, 그 뒤로는 30초마다(디스커버리 소음 줄이기)
                "interval": "30s", "timeout": "5s", "retries": 3,
                "start_period": "60s", "start_interval": "5s",
            },
            "init": True,
            "depends_on": _healthy(*px4_services),
        })
        services["bridge"] = bridge

        # ops-N: 기체마다 Mission Executor 컨테이너 하나. 전이는 노드가 스스로 건다(lifecycle.self_start).
        # healthcheck가 active를 확인하고, 시작 순서의 마지막 단계(startup.node_stages)에서 올린다.
        for v in vehicle_out:
            n = v["id"]
            ops = ros_ws_service(f"ops-{n}")
            ops.update({
                "command": ["ros2", "launch", OPS_LAUNCH_PKG, OPS_LAUNCH_FILE,
                            f"namespace:={v['ns']}",
                            f"executor_name:={EXECUTOR_NODE_NAME}",
                            f"params_file:={run_in_container}/{v['params_file']}"],
                "init": True,
                "stop_signal": OPS_STOP_SIGNAL,
                "stop_grace_period": OPS_STOP_GRACE,
                "healthcheck": {
                    "test": ["CMD-SHELL", ops_healthcheck(v["executor_node"])],
                    "interval": "10s", "timeout": "10s", "retries": 2,
                    "start_period": "20s", "start_interval": "2s",
                },
                "depends_on": _healthy("bridge", v["service"]),
            })
            services[f"ops-{n}"] = ops

        # targets: 표적 어댑터 하나가 모든 표적을 발행한다. 표적이 없으면 서비스와 params를 만들지 않는다.
        # ops-N과 같은 노드 단계에서 병렬로 올리고 서로 기다리지 않는다. 준비 판정은 노드가 만드는 표시 파일이다.
        if targets:
            tsvc = ros_ws_service(TARGETS_SERVICE)
            tsvc.update({
                "command": ["ros2", "run", TARGET_ADAPTER_PKG, TARGET_ADAPTER_EXEC, "--ros-args",
                            "--params-file", f"{run_in_container}/{TARGETS_PARAMS_FILE}"],
                "init": True,
                "stop_signal": OPS_STOP_SIGNAL,
                "healthcheck": {
                    "test": ["CMD-SHELL", f"test -f {TARGETS_READY_FILE}"],
                    "interval": "10s", "timeout": "5s", "retries": 2,
                    "start_period": "20s", "start_interval": "2s",
                },
                "depends_on": _healthy("bridge"),
            })
            services[TARGETS_SERVICE] = tsvc

        # sim-oracle: SITL 전용 정답 pose 공급자(sim-base 이미지). gz-transport로 pose/info를 직접 구독하므로 bridge를 거치지 않는다.
        # 모델이 스폰된 뒤라야 준비 조건이 성립하므로 gazebo와 px4-N 전부를 기다린다. 노드 단계에서 ops-N, targets와 병렬로 올린다.
        oenv = dict(ros_env)
        oenv.update(gz_env)
        oenv.update({
            "ROS_LOG_DIR": f"{run_in_container}/ros_log/{ORACLE_SERVICE}",
            "IDSIM_WORLD_NAME": world["name"],
            "IDSIM_ORACLE_VEHICLES": oracle_vehicles(vehicle_out),
        })
        services[ORACLE_SERVICE] = dict(_base(images["sim-base"]), **{
            "user": user,
            "environment": oenv,
            # ROS 환경은 /opt/ros의 setup.sh만 읽는다. $$는 compose에서 리터럴 $다
            "command": ["bash", "-c", oracle_command()],
            "init": True,
            "volumes": [_bind(sim_pkg_host, SIM_PKG_IN_CONTAINER, True),
                        _bind(f"{repo}/{CYCLONEDDS_REL}", CYCLONEDDS_IN_CONTAINER, True),
                        _bind(f"{run_dir}/ros_log/{ORACLE_SERVICE}", f"{run_in_container}/ros_log/{ORACLE_SERVICE}", False)],
            "healthcheck": {
                "test": ["CMD-SHELL", f"test -f {ORACLE_READY_FILE}"],
                "interval": "10s", "timeout": "5s", "retries": 2,
                "start_period": "20s", "start_interval": "2s",
            },
            "depends_on": _healthy("gazebo", *px4_services),
        })
    node_services = ops_services + ([TARGETS_SERVICE] if targets else []) + ([ORACLE_SERVICE] if standalone else [])

    runner = ros_ws_service("runner", {"IDSIM_STACK_FILE": f"{run_in_container}/stack.json"})
    runner.update({
        # 1회 실행용(compose run). 인자 없는 up --wait가 기다리지 않도록 프로필 tools에 둔다
        "profiles": ["tools"],
        # 상주는 아니지만 PID 1인 pytest가 wrapper의 SIGTERM을 버리지 않게 init을 둔다
        "init": True,
        "working_dir": REPO_IN_CONTAINER,
        "command": ["true"],
        "depends_on": _healthy(*node_services) if standalone else _healthy(px4_services[0]),
    })
    services["runner"] = runner

    if standalone:
        genv = dict(gz_env)
        genv.update({
            "HOME": "/tmp/gz-home",
            "DISPLAY": "${DISPLAY:-}",
            "XAUTHORITY": XAUTH_IN_CONTAINER,
        })
        for name in GUI_PASS_ENV:
            genv[name] = None
        services["gz-gui"] = dict(_base(images["sim-base"]), **{
            "profiles": ["viz"],
            "user": user,
            "ipc": "host",
            "environment": genv,
            "command": [f"{SIM_PKG_IN_CONTAINER}/scripts/gz_gui.sh"],
            "volumes": [
                _bind(X11_SOCKET_DIR, X11_SOCKET_DIR, True),
                _bind("${XAUTHORITY:-/dev/null}", XAUTH_IN_CONTAINER, True),
                _bind(sim_pkg_host, SIM_PKG_IN_CONTAINER, True),
            ],
            # viz -> 본 스택 방향 의존은 허용한다. healthcheck는 두지 않는다
            "depends_on": _healthy("gazebo"),
        })

        # foxglove: 읽기 전용 WebSocket(127.0.0.1:8765+k). 기체 토픽만 내보낸다(/clock은 250 Hz라 뺀다).
        # best_effort_qos_topic_whitelist는 쓰지 않는다(PX4 토픽 구독이 BEST_EFFORT로 맺어지는지는 P5에서 확인).
        fox = ros_ws_service("foxglove")
        wl = "[" + ", ".join(f"'^/{v['vehicle_id']}/.*'" for v in vehicle_out) + "]"
        fox.update({
            "command": ["ros2", "run", "foxglove_bridge", "foxglove_bridge", "--ros-args",
                        "-p", f"address:={VIZ_BIND}",
                        "-p", f"port:={FOXGLOVE_PORT_BASE + k}",
                        "-p", f"capabilities:={FOXGLOVE_CAPABILITIES}",
                        "-p", f"topic_whitelist:={wl}",
                        "-p", f"client_topic_whitelist:={FOXGLOVE_DENY_ALL}",
                        "-p", f"service_whitelist:={FOXGLOVE_DENY_ALL}",
                        "-p", f"param_whitelist:={FOXGLOVE_DENY_ALL}",
                        "-p", "use_sim_time:=true",
                        "-p", "remote_access:=false",
                        "-p", "sysinfo:=false"],
            "profiles": ["viz"],
            "init": True,
            "depends_on": _healthy("bridge"),
        })
        services["foxglove"] = fox
        # lichtblick: 정적 파일 서버. 이미지 기본 명령은 모든 인터페이스에 열므로 덮는다. root(entrypoint가 이미지 안 파일을 고쳐 쓴다)
        services["lichtblick"] = dict(_base(ctx["lichtblick_image"]), **{
            "profiles": ["viz"],
            "command": ["caddy", "file-server", "--listen", f"{VIZ_BIND}:{LICHTBLICK_PORT_BASE + k}"],
        })

    compose = {"name": project, "services": services}

    profiles = {"tools": ["runner"], "viz": ["gz-gui", "foxglove", "lichtblick"] if standalone else []}
    dlo, dhi, _ = dds_ports(k, pmax)
    stack = {
        "schema": SCHEMA,
        "generated_at": ctx["generated_at"],
        "generator": {"script": GENERATOR_SCRIPT, "version": GENERATOR_VERSION,
                      "git_commit": ctx["git_commit"], "git_dirty": ctx["git_dirty"]},
        "inputs": ctx["inputs"],
        "run": {"id": ctx["run_id"], "host_dir": run_dir, "compose_file": "compose.yaml", "ros_log_dir": "ros_log",
                "params_dir": PARAMS_DIR if standalone else None},
        "user": {"uid": ctx["uid"], "gid": ctx["gid"]},
        "variant": variant,
        "px4": {"start": fleet_norm["px4"]["start"]},
        "stack": {
            "index": k,
            "compose_project": project,
            "ros_domain_id": domain,
            "gz_partition": partition,
            "gz_ip": GZ_IP,
            "agent_port": aport,
            "agent_port_hex": aport_hex,
            "mavlink_offset": mavlink_offset(k),
            "mavlink_gcs_remote": gcs_remote_port(k),
            "foxglove_port": FOXGLOVE_PORT_BASE + k,
            "lichtblick_port": LICHTBLICK_PORT_BASE + k,
            "viz_bind": VIZ_BIND,
            "dds": {"rmw_implementation": RMW, "cyclonedds_uri": CYCLONEDDS_URI,
                    "port_base": dlo, "port_last": dhi, "participant_index_max": pmax},
        },
        "world": {
            "name": world["name"],
            "template": world["template"],
            "file": world_file_rel,
            "origin": None if origin is None else {key: float(origin[key]) for key in ORIGIN_KEYS},
            "speed_factor": None,
        },
        "images": {"xrce_agent": images["xrce-agent"], "sim_base": images["sim-base"],
                   "px4": images["px4"], "ros_ws": images["ros-ws"],
                   "lichtblick": ctx["lichtblick_image"] if standalone else None},
        "services": {
            "agent": "xrce-agent",
            "gazebo": "gazebo" if standalone else None,
            "bridge": "bridge" if standalone else None,
            "px4": px4_services,
            "ops": ops_services,
            "runner": "runner",
            "gz_gui": "gz-gui" if standalone else None,
            "targets": TARGETS_SERVICE if targets else None,
            "sim_oracle": ORACLE_SERVICE if standalone else None,
            "foxglove": "foxglove" if standalone else None,
            "lichtblick": "lichtblick" if standalone else None,
            "profiles": profiles,
        },
        "startup": {
            "stages": [["xrce-agent", "gazebo"], px4_services, ["bridge"]] if standalone
            else [["xrce-agent"], px4_services],
            "node_stages": [node_services] if standalone else [],
            "model_precheck": standalone,
        },
        "targets": targets,
        "vehicles": vehicle_out,
    }
    assert_invariants(compose, stack)
    return compose, stack, warnings


# ---------------------------------------------------------------- 실행 디렉터리 내용
PARAMS_HEADER = (
    "# 생성 파일. tools/gen_compose.py가 만든다. 손으로 고치지 않는다.\n"
    "# 식별값만 담는다. 타임아웃, 주기, command_source.*, lifecycle.self_start는 노드 선언 기본값을 쓴다.\n"
)


def render_ops_params(vehicle):
    """ops-N의 params 파일 본문. /** 아래에 use_sim_time과 vehicle.* 셋뿐이다(손으로 쓴 YAML, PyYAML 불필요)."""
    return (PARAMS_HEADER
            + "/**:\n"
            + "  ros__parameters:\n"
            + "    use_sim_time: true\n"
            + f"    vehicle.id: {vehicle['vehicle_id']}\n"
            + f"    vehicle.ns: {vehicle['ns']}\n"
            + f"    vehicle.sysid: {vehicle['sysid']}\n")


TARGETS_PARAMS_HEADER = (
    "# 생성 파일. tools/gen_compose.py가 config/fleet.yaml의 targets에서 만든다. 손으로 고치지 않는다.\n"
    "# 표적 궤적만 담는다. 발행 주기는 노드 선언 기본값을 쓴다.\n"
)


def _float_str(v):
    """params의 double 표기. 정수로 적은 값도 소수점이 있어야 ROS 파라미터가 double로 읽는다."""
    return _decimal_str(float(v))


def render_targets_params(targets):
    """targets 서비스(표적 어댑터)의 params 파일 본문. 평탄화 형식이다(decisions.md 쟁점 3).

    ROS 2 파라미터가 구조체 배열을 담지 못해 target_ids와 targets.<id>.{start_s, loop, t, x, y, z}로 편다.
    실수는 모두 소수점 표기, id는 큰따옴표로 감싼다(YAML이 true, null 같은 낱말을 문자열이 아닌 값으로 읽지 않게).
    """
    lines = [TARGETS_PARAMS_HEADER.rstrip("\n"),
             "/**:",
             "  ros__parameters:",
             "    use_sim_time: true",
             "    target_ids: [" + ", ".join(f'"{t["id"]}"' for t in targets) + "]"]
    for t in targets:
        base = f"    targets.{t['id']}."
        lines.append(f"{base}start_s: {_float_str(t['start_s'])}")
        lines.append(f"{base}loop: {'true' if t['loop'] else 'false'}")
        for key in WAYPOINT_KEYS:
            lines.append(f"{base}{key}: [" + ", ".join(_float_str(w[key]) for w in t["waypoints"]) + "]")
    return "\n".join(lines) + "\n"


def render_files(compose, stack, world_sdf=None):
    """실행 디렉터리에 만드는 파일 {상대 경로: 본문}. 생성 파일의 유일한 목록이다(golden 비교도 이 함수를 쓴다).

    world_sdf는 build_world_sdf의 결과다. stack.json의 world.file이 있으면(standalone) 필수이고 없으면(embedded) None이다.
    """
    files = {"compose.yaml": dump_compose(compose), "stack.json": dump_stack(stack)}
    wfile = stack["world"]["file"]
    if (wfile is None) != (world_sdf is None):
        raise FleetError(f"world.file={wfile!r}인데 world_sdf가 {'없다' if world_sdf is None else '있다'}")
    if wfile is not None:
        files[wfile] = world_sdf
    for v in stack["vehicles"]:
        if v["params_file"] is not None:
            files[v["params_file"]] = render_ops_params(v)
    if stack["services"]["targets"] is not None:
        files[TARGETS_PARAMS_FILE] = render_targets_params(stack["targets"])
    return files


def render_dirs(compose, stack):
    """실행 디렉터리에 빈 채로 만드는 디렉터리. px4 rootfs는 실행마다 새로 만들고, ros_log는 서비스별 하위를 호스트 사용자 소유로 만든다."""
    dirs = [v["rootfs_dir"] for v in stack["vehicles"]]
    logs = ["bridge"] + [f"ops-{v['id']}" for v in stack["vehicles"]] + [TARGETS_SERVICE, ORACLE_SERVICE, "foxglove", "runner"]
    dirs += [f"ros_log/{name}" for name in logs if name in compose["services"]]
    return dirs


# ---------------------------------------------------------------- 생성 직전 단정
def service_profiles(svc):
    return set(svc.get("profiles") or [])


def bind_targets(svc):
    return [vol["target"] for vol in svc.get("volumes", [])]


def interpolations(text):
    """compose 보간 대상 목록. $$는 리터럴이라 빼고 남은 ${...}와 맨 $를 돌려준다."""
    t = text.replace("$$", "")
    found = re.findall(r"\$\{[^}]*\}", t)
    rest = re.sub(r"\$\{[^}]*\}", "", t)
    if "$" in rest:
        found.append("$")
    return found


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, val in obj.items():
            yield from _strings(key)
            yield from _strings(val)
    elif isinstance(obj, list):
        for val in obj:
            yield from _strings(val)


def assert_invariants(compose, stack):
    """compose와 stack.json이 설계 규칙을 지키는지 단정한다. 어기면 FleetError(생성기 버그)."""
    problems = []
    services = compose["services"]
    viz = {name for name, s in services.items() if "viz" in service_profiles(s)}
    for name, s in services.items():
        if s.get("network_mode") != "host":
            problems.append(f"{name}: network_mode가 host가 아니다")
        if s.get("restart") != "no":
            problems.append(f"{name}: restart가 no가 아니다")
        if "viz" not in service_profiles(s):
            bad = viz & set(s.get("depends_on", {}))
            if bad:
                problems.append(f"{name}: viz 서비스 {sorted(bad)}에 의존한다")
        for dep in s.get("depends_on", {}):
            if dep not in services:
                problems.append(f"{name}: 없는 서비스 {dep}에 의존한다")
        targets = bind_targets(s)
        for a in targets:
            for b in targets:
                if a != b and (b + "/").startswith(a.rstrip("/") + "/"):
                    problems.append(f"{name}: 중첩 바인드 마운트 {a} 안에 {b}")
        if len(targets) != len(set(targets)):
            problems.append(f"{name}: 같은 대상에 두 번 마운트")
        for text in _strings(s):
            for item in interpolations(text):
                if item not in ALLOWED_INTERPOLATIONS or name not in viz:
                    problems.append(f"{name}: 허용되지 않은 보간 {item!r} in {text!r}")
    # 교차 검사: stack.json의 값이 compose와 같다
    st = stack["stack"]
    if compose["name"] != st["compose_project"]:
        problems.append("compose name과 stack.compose_project가 다르다")
    agent = services["xrce-agent"]
    if agent["command"][-1] != str(st["agent_port"]) or st["agent_port_hex"] not in agent["healthcheck"]["test"][1]:
        problems.append("에이전트 포트가 stack.json과 다르다")
    if "environment" in agent and "ROS_DOMAIN_ID" in agent["environment"]:
        problems.append("에이전트에 ROS_DOMAIN_ID가 있다")
    if stack["services"]["px4"] != [v["service"] for v in stack["vehicles"]]:
        problems.append("services.px4와 vehicles[].service 순서가 다르다")
    for v in stack["vehicles"]:
        s = services.get(v["service"])
        if s is None:
            problems.append(f"compose에 {v['service']}가 없다")
            continue
        env = s["environment"]
        want = {"ROS_DOMAIN_ID": str(st["ros_domain_id"]), "GZ_PARTITION": st["gz_partition"],
                "PX4_UXRCE_DDS_NS": v["px4_ns"], "PX4_UXRCE_DDS_PORT": str(st["agent_port"]),
                "IDSIM_MAVLINK_OFFSET": str(st["mavlink_offset"]), "PX4_SYS_AUTOSTART": str(v["autostart"]),
                "PX4_SIM_MODEL": v["sim_model"]}
        for key, val in want.items():
            if env.get(key) != val:
                problems.append(f"{v['service']}: {key}={env.get(key)!r} != stack.json {val!r}")
        if s["command"] != ["px4", "-d", "-i", str(v["instance"])]:
            problems.append(f"{v['service']}: 명령이 인스턴스 {v['instance']}와 다르다")
        if [vol["source"] for vol in s["volumes"]] != [v["host_rootfs_dir"]]:
            problems.append(f"{v['service']}: 볼륨이 host_rootfs_dir 하나가 아니다")
        if set(v["expected_params"]) & set(v["derived_params"]):
            problems.append(f"{v['service']}: expected_params와 derived_params가 겹친다")
    for role in ("gazebo", "bridge", "runner", "gz_gui"):
        name = stack["services"][role]
        if name is not None and name not in services:
            problems.append(f"services.{role}={name}가 compose에 없다")
    for name in ("gazebo", "bridge"):
        if name in services and services[name]["environment"].get("GZ_PARTITION") != st["gz_partition"]:
            problems.append(f"{name}: GZ_PARTITION이 stack.json과 다르다")
    if os.path.basename(stack["run"]["host_dir"]) != stack["run"]["id"]:
        problems.append("run.host_dir의 마지막 요소가 run.id와 다르다")
    # 월드: 원점은 생성된 월드 SDF로만 들어간다. gazebo는 실행 디렉터리의 world/를 읽기 전용으로 받아 그 파일을 연다
    wname, wfile = stack["world"]["name"], stack["world"]["file"]
    if (wfile is None) != (stack["services"]["gazebo"] is None):
        problems.append("world.file이 null인 것과 gazebo 서비스가 없는 것이 일치하지 않는다")
    if wfile is not None:
        gz = services["gazebo"]
        genv = gz["environment"]
        if wfile != f"{WORLD_DIR}/{wname}.sdf":
            problems.append(f"world.file {wfile!r} != {WORLD_DIR}/{wname}.sdf")
        if genv.get("IDSIM_WORLD_FILE") != f"{WORLD_IN_CONTAINER}/{wname}.sdf" or genv.get("IDSIM_WORLD_NAME") != wname:
            problems.append("gazebo의 IDSIM_WORLD_FILE, IDSIM_WORLD_NAME이 stack.json world와 다르다")
        if [k for k in genv if k.startswith("IDSIM_ORIGIN")]:
            problems.append("gazebo에 IDSIM_ORIGIN_*가 있다(원점은 월드 SDF로만 넣는다)")
        if ([(v["source"], v["target"], v["read_only"]) for v in gz["volumes"] if v["target"] == WORLD_IN_CONTAINER]
                != [(f"{stack['run']['host_dir']}/{WORLD_DIR}", WORLD_IN_CONTAINER, True)]):
            problems.append("gazebo의 world 볼륨이 실행 디렉터리 world/의 읽기 전용 마운트가 아니다")
        if tuple(services["bridge"]["command"][4:]) != BRIDGE_TOPIC_ARGS:
            problems.append(f"bridge 토픽 인자가 {BRIDGE_TOPIC_ARGS}가 아니다: {services['bridge']['command'][4:]}")
    for v in stack["vehicles"]:
        if (v["expect_gps"] is None) != (wfile is None):
            problems.append(f"{v['service']}: expect_gps가 null인 것과 embedded 변형이 일치하지 않는다")
    if (stack["services"]["targets"] is None) != (not stack["targets"]):
        problems.append("services.targets가 null인 것과 targets가 빈 것이 일치하지 않는다")
    if stack["variant"] == "embedded" and stack["targets"]:
        problems.append("embedded 변형인데 targets가 비어 있지 않다")
    if len(stack["targets"]) > TARGETS_MAX or any(len(t["waypoints"]) > WAYPOINTS_MAX for t in stack["targets"]):
        problems.append("표적 또는 waypoint 개수가 상한을 넘는다")
    if targets_length_sum_ms(stack["targets"]) > TARGETS_LENGTH_SUM_MAX_MS:
        problems.append("targets의 궤적 길이 합이 상한을 넘는다")
    if len({t["id"] for t in stack["targets"]}) != len(stack["targets"]):
        problems.append("targets의 id가 중복된다")
    tname = stack["services"]["targets"]
    if (TARGETS_SERVICE in services) != (tname is not None) or (tname is not None and tname != TARGETS_SERVICE):
        problems.append("targets 서비스와 services.targets가 일치하지 않는다")
    if tname is not None and TARGETS_SERVICE in services:
        tsvc = services[TARGETS_SERVICE]
        cmd = tsvc.get("command", [])
        if (cmd[:6] != ["ros2", "run", TARGET_ADAPTER_PKG, TARGET_ADAPTER_EXEC, "--ros-args", "--params-file"]
                or len(cmd) != 7 or not cmd[6].startswith("/") or not cmd[6].endswith(f"/{TARGETS_PARAMS_FILE}")):
            problems.append(f"targets: command가 stack.json과 다르다: {cmd}")
        if set(tsvc.get("depends_on", {})) != {"bridge"}:
            problems.append("targets: depends_on이 bridge 하나가 아니다")
        if tsvc.get("stop_signal") != OPS_STOP_SIGNAL:
            problems.append(f"targets: stop_signal이 {OPS_STOP_SIGNAL}가 아니다")
        if tsvc.get("healthcheck", {}).get("test") != ["CMD-SHELL", f"test -f {TARGETS_READY_FILE}"]:
            problems.append("targets: healthcheck가 표시 파일 검사가 아니다")
        if service_profiles(tsvc):
            problems.append("targets: 프로필 서비스다")
        if any(TARGETS_SERVICE in stage for stage in stack["startup"]["stages"]):
            problems.append("targets가 인프라 단계(startup.stages)에 있다")
    # sim-oracle: standalone이면 항상 있고 embedded에는 없다
    oname = stack["services"]["sim_oracle"]
    if (oname is None) != (stack["variant"] == "embedded") or (oname is not None and oname != ORACLE_SERVICE):
        problems.append("services.sim_oracle이 variant와 맞지 않는다(standalone은 sim-oracle, embedded는 null)")
    if (ORACLE_SERVICE in services) != (oname is not None):
        problems.append("sim-oracle 서비스와 services.sim_oracle이 일치하지 않는다")
    if ORACLE_SERVICE in services:
        osvc = services[ORACLE_SERVICE]
        oenv = osvc.get("environment", {})
        odeps = osvc.get("depends_on", {})
        run_in = f"{REPO_IN_CONTAINER}/artifacts/runs/{stack['run']['id']}"
        if osvc.get("image") != stack["images"]["sim_base"]:
            problems.append("sim-oracle: 이미지가 sim-base가 아니다")
        if osvc.get("user") != f"{stack['user']['uid']}:{stack['user']['gid']}":
            problems.append("sim-oracle: user가 호스트 uid:gid가 아니다")
        if osvc.get("init") is not True:
            problems.append("sim-oracle: init: true가 아니다")
        if set(odeps) != {"gazebo", *stack["services"]["px4"]} or any(d.get("condition") != "service_healthy" for d in odeps.values()):
            problems.append("sim-oracle: depends_on이 gazebo와 px4-N 전부의 healthy가 아니다")
        if osvc.get("command") != ["bash", "-c", oracle_command()]:
            problems.append(f"sim-oracle: command가 sim_oracle.py 실행이 아니다: {osvc.get('command')}")
        for key, val in (("GZ_PARTITION", st["gz_partition"]), ("GZ_IP", st["gz_ip"]), ("RMW_IMPLEMENTATION", RMW),
                         ("CYCLONEDDS_URI", CYCLONEDDS_URI), ("ROS_DOMAIN_ID", str(st["ros_domain_id"])),
                         ("IDSIM_WORLD_NAME", stack["world"]["name"]), ("ROS_LOG_DIR", f"{run_in}/ros_log/{ORACLE_SERVICE}"),
                         ("IDSIM_ORACLE_VEHICLES", oracle_vehicles(stack["vehicles"]))):
            if oenv.get(key) != val:
                problems.append(f"sim-oracle: {key}={oenv.get(key)!r} != {val!r}")
        if [k for k in oenv if k.startswith("IDSIM_ORIGIN")]:
            problems.append("sim-oracle에 IDSIM_ORIGIN_*가 있다(원점은 월드 SDF로만 넣는다)")
        host = stack["run"]["host_dir"]
        vols = sorted((v["source"], v["target"], v["read_only"]) for v in osvc.get("volumes", []))
        want = sorted([(f"{host.rsplit('/artifacts/runs/', 1)[0]}/{SIM_PKG_REL}", SIM_PKG_IN_CONTAINER, True),
                       (f"{host.rsplit('/artifacts/runs/', 1)[0]}/{CYCLONEDDS_REL}", CYCLONEDDS_IN_CONTAINER, True),
                       (f"{host}/ros_log/{ORACLE_SERVICE}", f"{run_in}/ros_log/{ORACLE_SERVICE}", False)])
        if vols != want:
            problems.append(f"sim-oracle: 볼륨이 idsim_sim(읽기 전용), cyclonedds.xml 파일 하나(읽기 전용), ros_log/sim-oracle(쓰기)이 아니다: {vols}")
        if osvc.get("healthcheck", {}).get("test") != ["CMD-SHELL", f"test -f {ORACLE_READY_FILE}"]:
            problems.append("sim-oracle: healthcheck가 표시 파일 검사가 아니다")
        if service_profiles(osvc):
            problems.append("sim-oracle: 프로필 서비스다")
        if any(ORACLE_SERVICE in stage for stage in stack["startup"]["stages"]):
            problems.append("sim-oracle이 인프라 단계(startup.stages)에 있다")
    if any("dynamic_pose" in text for text in _strings(compose)):
        problems.append("compose에 dynamic_pose 문자열이 있다(정답 pose는 bridge를 거치지 않는다)")
    wt = stack["inputs"].get("world_template")
    if not isinstance(wt, dict) or wt.get("path") != stack["world"]["template"] or not wt.get("sha256"):
        problems.append("inputs.world_template {path, sha256}가 없거나 world.template과 다르다")
    for v in stack["vehicles"]:
        if v["host_rootfs_dir"] != f"{stack['run']['host_dir']}/{v['rootfs_dir']}" or v["rootfs_dir"] != f"px4-{v['instance']}":
            problems.append(f"{v['service']}: host_rootfs_dir이 run.host_dir/px4-N이 아니다")
    # init: 상주 ros-ws 서비스(프로필 없음)와 xrce-agent는 PID 1이 신호를 버리지 않게 init을 둔다
    ros_ws_image = stack["images"]["ros_ws"]
    for name, svc in services.items():
        resident_ros_ws = svc.get("image") == ros_ws_image and not service_profiles(svc)
        if (resident_ros_ws or name in ("xrce-agent", "runner")) and svc.get("init") is not True:
            problems.append(f"{name}: 상주 서비스인데 init: true가 아니다")
    ops_names = stack["services"]["ops"]
    for v in stack["vehicles"]:
        vid = v["vehicle_id"]
        if not vid or vid != v["ns"][1:] or "/" in vid:
            problems.append(f"{v['service']}: vehicle_id {vid!r}가 ns {v['ns']!r}에서 앞의 /를 뗀 토큰 하나가 아니다")
        if v["params_file"] is None:
            if v["executor_node"] is not None or ops_names:
                problems.append(f"{v['service']}: params_file 없이 executor_node나 ops 서비스가 있다")
            continue
        if v["executor_node"] != f"{v['ns']}/{EXECUTOR_NODE_NAME}":
            problems.append(f"{v['service']}: executor_node {v['executor_node']!r}가 ns와 노드 이름 상수에서 나온 값이 아니다")
        name = f"ops-{v['id']}"
        ops = services.get(name)
        if ops is None or name not in ops_names:
            problems.append(f"{name}가 compose 또는 services.ops에 없다")
            continue
        if ops.get("stop_signal") != OPS_STOP_SIGNAL or ops.get("stop_grace_period") != OPS_STOP_GRACE:
            problems.append(f"{name}: stop_signal, stop_grace_period가 {OPS_STOP_SIGNAL}, {OPS_STOP_GRACE}가 아니다")
        if ops["healthcheck"]["test"][1] != ops_healthcheck(v["executor_node"]):
            problems.append(f"{name}: healthcheck의 노드 이름이 stack.json executor_node와 다르다")
        cmd = ops["command"]
        if (cmd[:6] != ["ros2", "launch", OPS_LAUNCH_PKG, OPS_LAUNCH_FILE, f"namespace:={v['ns']}",
                        f"executor_name:={EXECUTOR_NODE_NAME}"]
                or not cmd[6].startswith("params_file:=/") or not cmd[6].endswith(f"/{v['params_file']}")):
            problems.append(f"{name}: command가 stack.json과 다르다: {cmd}")
        if set(ops.get("depends_on", {})) != {"bridge", v["service"]}:
            problems.append(f"{name}: depends_on이 bridge와 {v['service']}가 아니다")
    if ops_names:
        node_names = ops_names + ([tname] if tname is not None else []) + ([oname] if oname is not None else [])
        if set(services["runner"].get("depends_on", {})) != set(node_names):
            problems.append("runner의 depends_on이 ops 서비스 전부, targets(있으면), sim-oracle이 아니다")
        if stack["startup"]["node_stages"] != [node_names]:
            problems.append("startup.node_stages가 [ops 서비스 전부, targets(있으면), sim-oracle]이 아니다")
    elif stack["startup"]["node_stages"]:
        problems.append("ops 서비스가 없는데 startup.node_stages가 비어 있지 않다")
    for name in ops_names:
        if name not in services:
            problems.append(f"services.ops의 {name}가 compose에 없다")
    cyc = stack["inputs"].get("cyclonedds_xml")
    if not isinstance(cyc, dict) or not cyc.get("path") or not cyc.get("sha256"):
        problems.append("inputs.cyclonedds_xml {path, sha256}가 없다")
    elif CYCLONEDDS_URI != f"file://{REPO_IN_CONTAINER}/{cyc['path']}":
        problems.append("inputs.cyclonedds_xml.path가 CYCLONEDDS_URI와 다르다")
    for stage in stack["startup"]["stages"]:
        for name in stage:
            if name not in services or service_profiles(services[name]):
                problems.append(f"startup 단계의 {name}가 없거나 프로필 서비스다")
    if problems:
        raise FleetError("생성기 단정 실패(버그):\n" + "\n".join(problems))


# ---------------------------------------------------------------- 파일 입출력 (PyYAML은 여기서만)
def load_yaml(text):
    """YAML을 읽는다. 중복 key는 거부한다(PyYAML 기본은 뒤 값으로 조용히 덮는다)."""
    import yaml

    class StrictLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in keys:
                raise FleetError(f"중복 key {key!r} ({key_node.start_mark})")
            keys.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    try:
        return yaml.load(text, Loader=StrictLoader)  # noqa: S506 (SafeLoader 파생)
    except yaml.YAMLError as e:
        raise FleetError(f"YAML 파싱 실패: {e}") from e


COMPOSE_HEADER = (
    "# 생성 파일. tools/gen_compose.py가 config/fleet.yaml에서 만든다. 손으로 고치지 않는다.\n"
    "# 값의 출처와 실행 시점 식별자는 같은 디렉터리의 stack.json에 있다.\n"
)


def dump_compose(compose):
    import yaml

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

        def increase_indent(self, flow=False, indentless=False):
            # 목록도 들여쓴다(yamllint indentation 규칙과 같은 모양)
            return super().increase_indent(flow, False)

    body = yaml.dump(compose, Dumper=Dumper, sort_keys=False, default_flow_style=False,
                     allow_unicode=False, width=150)
    return COMPOSE_HEADER + body


def dump_stack(stack):
    return json.dumps(stack, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise FleetError(f"파일을 읽지 못했다: {path} ({e.strerror})") from e


def _repo_rel(path, repo_root):
    full = os.path.normpath(os.path.join(repo_root, path))
    rel = os.path.relpath(full, repo_root)
    if rel.startswith(".."):
        raise FleetError(f"{path}: 저장소({repo_root}) 밖의 파일이다")
    return full, rel


def parse_versions_value(text, name):
    """versions.env에서 NAME=값 한 줄의 값. 없거나 공백이 있으면 FleetError."""
    for line in text.splitlines():
        key, sep, val = line.partition("=")
        if sep and key == name:
            if not val or any(c.isspace() for c in val) or "$" in val:
                raise FleetError(f"{VERSIONS_ENV_REL}: {name} 값이 잘못됐다: {val!r}")
            return val
    raise FleetError(f"{VERSIONS_ENV_REL}에 {name}이 없다")


def resolve_images(image_tag, registry, overrides):
    prefix = registry.rstrip("/") if registry else "idsim"
    images = {n: f"{prefix}/{n}:{image_tag}" for n in IMAGE_NAMES}
    for item in overrides or []:
        name, sep, ref = item.partition("=")
        if not sep or name not in images or not ref or any(c.isspace() for c in ref) or "$" in ref:
            raise FleetError(f"--image는 <{'|'.join(IMAGE_NAMES)}>=<참조> 형식: {item!r}")
        images[name] = ref
    return images


def stack_index(arg, environ):
    raw = arg if arg is not None else environ.get("IDSIM_STACK_INDEX", "0")
    if raw == "" or not re.fullmatch(r"[0-9]", str(raw)):
        raise FleetError(f"스택 번호 k는 {STACK_MIN}-{STACK_MAX} 한 자리 정수: {raw!r}")
    return int(raw)


def generate(args, environ=os.environ):
    """CLI 동작 전체. 출력 디렉터리에 compose.yaml, stack.json, px4-N/, ros_log/<서비스>/를 만든다."""
    repo_root = os.path.abspath(args.repo_root)
    k = stack_index(args.stack, environ)
    fleet_abs, fleet_rel = _repo_rel(args.fleet, repo_root)
    fleet_norm, warnings = validate_fleet(load_yaml(_read(fleet_abs)))
    template_abs, template_rel = _repo_rel(fleet_norm["world"]["template"], repo_root)
    template_text = _read(template_abs)
    parse_world_template(template_text, template_rel)
    params_abs, params_rel = _repo_rel(fleet_norm["px4"]["params_file"], repo_root)
    params_env = parse_params_env(_read(params_abs), params_rel)
    versions_abs = os.path.join(repo_root, VERSIONS_ENV_REL)
    pmax = parse_participant_max(_read(os.path.join(repo_root, CYCLONEDDS_REL)))
    lichtblick_image = parse_versions_value(_read(versions_abs), "LICHTBLICK_IMAGE")

    now = datetime.datetime.now(datetime.timezone.utc)
    generated_at = args.generated_at or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", generated_at):
        raise FleetError(f"--generated-at은 RFC 3339 UTC 초 단위(...Z): {generated_at!r}")
    host_repo = os.path.normpath(args.host_repo_root)
    if args.run_id:
        run_id = args.run_id
    elif args.run_dir:
        run_id = os.path.basename(os.path.normpath(args.run_dir))
    else:
        run_id = f"{now.strftime('%Y%m%d-%H%M%S')}-k{k}"
    host_run = os.path.normpath(args.run_dir) if args.run_dir else f"{host_repo}/artifacts/runs/{run_id}"
    git_dirty = {"true": True, "false": False, None: None}[args.git_dirty]
    ctx = {
        "k": k,
        "variant": args.variant,
        "uid": os.getuid() if args.uid is None else args.uid,
        "gid": os.getgid() if args.gid is None else args.gid,
        "run_id": run_id,
        "host_repo_root": host_repo,
        "host_run_dir": host_run,
        "images": resolve_images(args.image_tag, args.registry, args.image),
        "generated_at": generated_at,
        "git_commit": args.git_commit or None,
        "git_dirty": git_dirty,
        "inputs": {
            "fleet": {"path": fleet_rel, "sha256": _sha256_file(fleet_abs)},
            "px4_params_file": {"path": params_rel, "sha256": _sha256_file(params_abs)},
            "versions_env": {"path": VERSIONS_ENV_REL, "sha256": _sha256_file(versions_abs)},
            "cyclonedds_xml": {"path": CYCLONEDDS_REL, "sha256": _sha256_file(os.path.join(repo_root, CYCLONEDDS_REL))},
            "world_template": {"path": template_rel, "sha256": _sha256_file(template_abs)},
        },
        "params_env": params_env,
        "participant_index_max": pmax,
        "lichtblick_image": lichtblick_image,
    }
    compose, stack, more = build(fleet_norm, ctx)
    warnings.extend(more)
    world_sdf = build_world_sdf(fleet_norm, template_text) if stack["world"]["file"] is not None else None
    files = render_files(compose, stack, world_sdf)

    out = os.path.abspath(args.out_dir or host_run)
    if os.path.isdir(out) and os.listdir(out):
        raise FleetError(f"출력 디렉터리가 비어 있지 않다: {out} (px4 rootfs는 실행마다 새로 만든다)")
    os.makedirs(out, exist_ok=True)
    for rel in render_dirs(compose, stack):
        os.makedirs(os.path.join(out, rel), exist_ok=False)
    for rel, text in files.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return host_run, warnings


def parse_args(argv):
    default_repo = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--print-gcs-port", metavar="K", help="스택 K의 GCS 포트만 출력하고 끝낸다(PyYAML 불필요)")
    p.add_argument("--print-agent-port", metavar="K", help="스택 K의 에이전트 UDP 포트만 출력하고 끝낸다(PyYAML 불필요)")
    p.add_argument("--print-sensor-z", metavar="AIRFRAME",
                   help="airframe의 GNSS 센서 높이(m)만 출력하고 끝낸다(PyYAML 불필요)")
    p.add_argument("--print-airframes", action="store_true",
                   help="센서 높이가 등록된 airframe 목록을 한 줄에 하나씩 출력하고 끝낸다(PyYAML 불필요)")
    p.add_argument("--repo-root", default=default_repo, help="저장소 경로(이 프로세스가 읽는 쪽, 기본: 스크립트 위)")
    p.add_argument("--fleet", default="config/fleet.yaml", help="저장소 기준 fleet 파일")
    p.add_argument("--stack", help="스택 번호 k 0-9 (없으면 IDSIM_STACK_INDEX, 없으면 0)")
    p.add_argument("--variant", choices=VARIANTS, default="standalone")
    p.add_argument("--run-id", help="실행 id (기본: --run-dir의 마지막 요소, 둘 다 없으면 <UTC YYYYmmdd-HHMMSS>-k<k>)")
    p.add_argument("--host-repo-root", help="호스트에서 본 저장소 절대 경로(compose 바인드 마운트 원본)")
    p.add_argument("--run-dir", help="호스트에서 본 실행 디렉터리, <host-repo-root>/artifacts/runs/<run-id>여야 한다(기본 <host-repo-root>/artifacts/runs/<run-id>)")
    p.add_argument("--out-dir", help="이 프로세스가 파일을 쓸 경로(기본 --run-dir). 컨테이너에서는 /out")
    p.add_argument("--uid", type=int)
    p.add_argument("--gid", type=int)
    p.add_argument("--image-tag", default="local")
    p.add_argument("--registry", help="이미지 접두사(기본 idsim). 예: ghcr.io/<소유자>/idsim")
    p.add_argument("--image", action="append", metavar="NAME=REF", help="이미지 하나를 직접 지정(CI key 태그)")
    p.add_argument("--generated-at")
    p.add_argument("--git-commit")
    p.add_argument("--git-dirty", choices=("true", "false"))
    args = p.parse_args(argv)
    if (args.print_gcs_port is None and args.print_agent_port is None and args.print_sensor_z is None and not args.print_airframes
            and not args.host_repo_root):
        p.error("--host-repo-root가 필요하다(tools/gen_compose.sh가 넘긴다)")
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.print_gcs_port is not None:
            print(gcs_remote_port(stack_index(args.print_gcs_port, {})))
            return 0
        if args.print_agent_port is not None:
            print(agent_port(stack_index(args.print_agent_port, {})))
            return 0
        if args.print_airframes:
            print("\n".join(AIRFRAME_SENSOR_Z_M))
            return 0
        if args.print_sensor_z is not None:
            if args.print_sensor_z not in AIRFRAME_SENSOR_Z_M:
                raise FleetError(f"airframe {args.print_sensor_z!r}의 센서 높이가 없다(허용: {', '.join(AIRFRAME_SENSOR_Z_M)})")
            print(AIRFRAME_SENSOR_Z_M[args.print_sensor_z])
            return 0
        host_run, warnings = generate(args)
    except FleetError as e:
        print(f"gen_compose: 실패\n{e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"gen_compose: 경고: {w}", file=sys.stderr)
    print(host_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
