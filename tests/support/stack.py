"""stack.json 로더. 표준 라이브러리만 쓴다(JSON Schema 의존 없음).

stack.json은 tools/gen_compose.py가 artifacts/runs/<실행 id>/ 에 만드는 실행 시점의 단일 출처다.
이 모듈은 읽고 검사하고 접근자를 줄 뿐이며, 식별자(네임스페이스, 도메인, 포트, 서비스 이름)를
다시 계산하지 않는다. 계산 함수를 추가하지 말 것. 값이 필요하면 생성기에 필드를 요청한다.

사용 예(ros-ws 컨테이너, pytest):
  stack = load_from_env()                 # IDSIM_STACK_FILE
  for v in stack.vehicles: v.ns, v.sysid
  stack.ros_domain_id, stack.compose_project

스키마: schema 정수 하나. 아는 값(SUPPORTED_SCHEMAS)이 아니면 실패한다. 모르는 필드는 무시한다.
필수 필드의 키가 없으면 실패한다. "필수, null 가능" 필드는 키가 있고 값이 None이어야 한다.
경로 규칙: host_ 접두사 필드만 호스트 절대 경로(그대로 돌려줌). 나머지는 stack.json 디렉터리 기준
상대 경로이며 resolve()로 절대 경로가 된다.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "IDSIM_STACK_FILE"
SUPPORTED_SCHEMAS = frozenset({1})
# 생성기 판 3부터 stack.json에 노드 단계 key(vehicle_id, params_file, executor_node, run.params_dir,
# startup.node_stages, services.ops)가 있다. 판 3 이상이면 필수로 검사하고, 그보다 낮은 판은 읽기만 한다.
NODE_KEYS_MIN_GENERATOR_VERSION = 3
# 생성기 판 5부터 world template, 표적, 정답 pose 서비스, 기체별 기대 GPS key가 있다(Phase 1b 쟁점 2, 3, 5, 16).
# 판 5 이상이면 필수로 검사하고, 그보다 낮은 판은 읽기만 한다(접근자는 StackError).
WORLD_KEYS_MIN_GENERATOR_VERSION = 5


class StackError(Exception):
    """stack.json 로드, 검사, 조회 실패. 메시지에 파일 경로와 필드 경로를 넣는다."""


class StackLookupError(StackError, LookupError):
    """기체 조회 실패."""


# 필수 필드 명세. 값: 타입 튜플(리프) 또는 dict(하위 객체). NONE을 넣으면 null 허용.
_NONE = type(None)
_STR = (str,)
_INT = (int,)
_NSTR = (str, _NONE)
_STR_MAP = (dict,)

_SPEC = {
    "schema": _INT,
    "generated_at": _STR,
    "generator": {"script": _STR, "version": _INT, "git_commit": _NSTR, "git_dirty": (bool, _NONE)},
    "inputs": {
        "fleet": {"path": _STR, "sha256": _STR},
        "px4_params_file": {"path": _STR, "sha256": _STR},
        "versions_env": {"path": _STR, "sha256": _STR},
    },
    "run": {"id": _STR, "host_dir": _STR, "compose_file": _STR, "ros_log_dir": _STR},
    "user": {"uid": _INT, "gid": _INT},
    "variant": _STR,
    "px4": {"start": _STR},
    "stack": {
        "index": _INT, "compose_project": _STR, "ros_domain_id": _INT, "gz_partition": _STR,
        "gz_ip": _STR, "agent_port": _INT, "agent_port_hex": _STR, "mavlink_offset": _INT,
        "mavlink_gcs_remote": _INT, "foxglove_port": _INT, "lichtblick_port": _INT,
        "viz_bind": _STR,
        "dds": {"rmw_implementation": _STR, "cyclonedds_uri": _STR, "port_base": _INT,
                "port_last": _INT, "participant_index_max": _INT},
    },
    # world.origin은 값이 있을 때만 하위 키 검사(_check_world_origin)
    "world": {"name": _STR, "file": _NSTR, "origin": (dict, _NONE),
              "speed_factor": (int, float, _NONE)},
    "images": {"xrce_agent": _STR, "sim_base": _STR, "px4": _STR, "ros_ws": _STR,
               "lichtblick": _NSTR},
    "services": {
        "agent": _STR, "gazebo": _NSTR, "bridge": _NSTR, "px4": (list,), "runner": _STR,
        "gz_gui": _NSTR, "foxglove": _NSTR, "lichtblick": _NSTR, "profiles": (dict,),
    },
    "startup": {"stages": (list,), "model_precheck": (bool,)},
    "vehicles": (list,),
}

_VEHICLE_SPEC = {
    "id": _INT, "instance": _INT, "ns": _STR, "px4_ns": _STR, "sysid": _INT, "uxrce_key": _INT,
    "airframe": _STR, "autostart": _INT, "sim_model": _STR, "gz_model_name": _STR,
    "pose": {"x": (int, float), "y": (int, float), "z": (int, float), "yaw": (int, float)},
    "service": _STR,
    "mavlink": {"gcs_remote": _INT, "gcs_local": _INT, "api_remote": _INT, "api_local": _INT},
    "rootfs_dir": _STR, "ulog_dir": _STR, "host_rootfs_dir": _STR,
    "expected_params": _STR_MAP, "derived_params": _STR_MAP,
}

_ORIGIN_SPEC = {"lat": (int, float), "lon": (int, float), "alt": (int, float)}

# 생성기 판 3 이상에서 추가로 검사하는 key(Executor 노드 단계). embedded 변형에는 노드가 없어 null/빈 목록이다.
_V3_SPEC = {
    "run": {"params_dir": _NSTR},
    "startup": {"node_stages": (list,)},
    "services": {"ops": (list,)},
}
_V3_VEHICLE_SPEC = {"vehicle_id": _STR, "params_file": _NSTR, "executor_node": _NSTR}

# 생성기 판 5 이상에서 추가로 검사하는 key. world.file은 판 5부터 실행 디렉터리 기준 상대 경로
# ("world/<name>.sdf")이고 생성한 월드가 없는 embedded는 null이다. targets, services.targets,
# services.sim_oracle은 key가 항상 있고, 해당 서비스가 없는 구성에서는 null 또는 빈 목록이다.
_V5_SPEC = {
    "inputs": {"world_template": {"path": _STR, "sha256": _STR}},
    "world": {"template": _STR},
    "targets": (list,),
    "services": {"targets": _NSTR, "sim_oracle": _NSTR},
}
_V5_VEHICLE_SPEC = {"expect_gps": (dict, _NONE)}
_NUM = (int, float)
_TARGET_SPEC = {"id": _STR, "start_s": _NUM, "loop": (bool,), "waypoints": (list,)}
_WAYPOINT_SPEC = {"t": _NUM, "x": _NUM, "y": _NUM, "z": _NUM}


def _type_ok(value, types):
    if isinstance(value, bool):
        return bool in types
    if float in types and isinstance(value, int):
        return True
    return isinstance(value, types)


def _check(obj, spec, where):
    if not isinstance(obj, dict):
        raise StackError(f"{where}: 객체여야 한다")
    for key, sub in spec.items():
        here = f"{where}.{key}" if where else key
        if key not in obj:
            raise StackError(f"필수 필드 누락: {here}")
        if isinstance(sub, dict):
            _check(obj[key], sub, here)
        elif not _type_ok(obj[key], sub):
            names = "/".join(t.__name__ for t in sub)
            raise StackError(f"{here}: 타입 불일치(기대 {names}, 실제 {type(obj[key]).__name__})")


def _validate(data):
    if not isinstance(data, dict):
        raise StackError("최상위가 객체가 아니다")
    if "schema" not in data:
        raise StackError("필수 필드 누락: schema")
    sch = data["schema"]
    if isinstance(sch, bool) or not isinstance(sch, int) or sch not in SUPPORTED_SCHEMAS:
        raise StackError(f"지원하지 않는 schema: {sch!r} (지원: {sorted(SUPPORTED_SCHEMAS)})")
    _check(data, _SPEC, "")
    if data["world"]["origin"] is not None:
        _check(data["world"]["origin"], _ORIGIN_SPEC, "world.origin")
    for i, v in enumerate(data["vehicles"]):
        _check(v, _VEHICLE_SPEC, f"vehicles[{i}]")
        for name in ("expected_params", "derived_params"):
            for k, val in v[name].items():
                if not isinstance(val, str):
                    raise StackError(f"vehicles[{i}].{name}.{k}: 값은 문자열이어야 한다")
    if not data["vehicles"]:
        raise StackError("vehicles가 비어 있다")
    if data["generator"]["version"] >= NODE_KEYS_MIN_GENERATOR_VERSION:
        _check(data, _V3_SPEC, "")
        for i, v in enumerate(data["vehicles"]):
            _check(v, _V3_VEHICLE_SPEC, f"vehicles[{i}]")
        for i, st in enumerate(data["startup"]["node_stages"]):
            if not isinstance(st, list) or not all(isinstance(x, str) for x in st):
                raise StackError(f"startup.node_stages[{i}]: 문자열 배열이어야 한다")
        if not all(isinstance(x, str) for x in data["services"]["ops"]):
            raise StackError("services.ops: 문자열 배열이어야 한다")
    if not all(isinstance(s, str) for s in data["services"]["px4"]):
        raise StackError("services.px4: 문자열 배열이어야 한다")
    if data["generator"]["version"] >= WORLD_KEYS_MIN_GENERATOR_VERSION:
        _validate_v5(data)
    elif data["world"]["file"] is None:
        raise StackError("world.file: null은 생성기 판 5부터 허용한다")


def _validate_v5(data):
    _check(data, _V5_SPEC, "")
    for i, v in enumerate(data["vehicles"]):
        _check(v, _V5_VEHICLE_SPEC, f"vehicles[{i}]")
        if v["expect_gps"] is not None:
            _check(v["expect_gps"], _ORIGIN_SPEC, f"vehicles[{i}].expect_gps")
    # decisions: embedded(gazebo 서비스 없음)만 world.file과 expect_gps가 null이다(양방향)
    has_gazebo = data["services"]["gazebo"] is not None
    if (data["world"]["file"] is None) == has_gazebo:
        raise StackError("world.file: null은 gazebo 서비스가 없는 구성(embedded)에서만이고, "
                         "gazebo 서비스가 있으면 값이 있어야 한다")
    for i, v in enumerate(data["vehicles"]):
        if (v["expect_gps"] is None) == has_gazebo:
            raise StackError(f"vehicles[{i}].expect_gps: null은 gazebo 서비스가 없는 구성"
                             "(embedded)에서만이고, gazebo 서비스가 있으면 값이 있어야 한다")
    for i, t in enumerate(data["targets"]):
        _check(t, _TARGET_SPEC, f"targets[{i}]")
        for j, w in enumerate(t["waypoints"]):
            _check(w, _WAYPOINT_SPEC, f"targets[{i}].waypoints[{j}]")
    if (data["services"]["targets"] is None) != (not data["targets"]):
        raise StackError("services.targets: targets가 비었을 때만 null이어야 한다")


@dataclass(frozen=True)
class Vehicle:
    id: int
    instance: int
    ns: str            # "/px4_1" (앞 빗금 있음)
    px4_ns: str        # "px4_1" (빗금 없음)
    sysid: int         # MAV_SYS_ID, VehicleCommand.target_system
    uxrce_key: int
    airframe: str
    gz_model_name: str
    service: str       # compose 서비스 이름
    pose: dict         # x, y, z, yaw (Gazebo 월드 ENU, m, rad)
    mavlink: dict      # gcs_remote, gcs_local, api_remote, api_local
    rootfs_dir: str    # 상대 경로. Stack.resolve로 푼다
    ulog_dir: str      # 상대 경로
    host_rootfs_dir: str  # 호스트 절대 경로(컨테이너 안에서는 쓰지 않는다)
    expected_params: dict
    derived_params: dict
    raw: dict
    # 생성기 판 3 이상에서만 값이 있다(그보다 낮은 판은 None). executor_node와 params_file은 embedded에서 None이다
    vehicle_id: str = None   # 계약 식별자("px4_1"). action 이름 /<vehicle_id>/execute_mission
    params_file: str = None  # 실행 디렉터리 기준 상대 경로(params/ops-N.yaml)
    executor_node: str = None  # Executor 노드 FQN("/px4_1/mission_executor")
    # 생성기 판 5 이상에서만 값이 있다. {lat, lon, alt}(base_link 기준), embedded는 None
    expect_gps: dict = None


@dataclass(frozen=True)
class Stack:
    path: Path         # stack.json 절대 경로
    raw: dict
    vehicles: tuple

    # 상위 값 접근자. 모두 파일에 적힌 값을 그대로 돌려준다.
    @property
    def dir(self):
        return self.path.parent

    @property
    def schema(self):
        return self.raw["schema"]

    @property
    def run_id(self):
        return self.raw["run"]["id"]

    @property
    def variant(self):
        return self.raw["variant"]

    @property
    def compose_project(self):
        return self.raw["stack"]["compose_project"]

    @property
    def stack_index(self):
        return self.raw["stack"]["index"]

    @property
    def ros_domain_id(self):
        return self.raw["stack"]["ros_domain_id"]

    @property
    def gz_partition(self):
        return self.raw["stack"]["gz_partition"]

    @property
    def rmw_implementation(self):
        return self.raw["stack"]["dds"]["rmw_implementation"]

    @property
    def cyclonedds_uri(self):
        return self.raw["stack"]["dds"]["cyclonedds_uri"]

    @property
    def world_name(self):
        return self.raw["world"]["name"]

    @property
    def world_origin(self):
        """{lat, lon, alt} 또는 None(embedded 등 적용 주체가 없을 때)."""
        return self.raw["world"]["origin"]

    @property
    def speed_factor(self):
        return self.raw["world"]["speed_factor"]

    @property
    def services(self):
        """역할 -> 서비스 이름. null 가능한 역할은 None. px4는 문자열 배열."""
        return self.raw["services"]

    def service(self, role):
        """역할의 서비스 이름. null이면 StackError(이 구성에는 그 서비스가 없다)."""
        s = self.raw["services"].get(role)
        if s is None:
            raise StackError(f"{self.path}: 서비스 {role!r}이 없다(null 또는 모르는 역할)")
        return s

    @property
    def startup_stages(self):
        return self.raw["startup"]["stages"]

    # 생성기 판 3 이상의 key. 낮은 판이면 StackError(이 stack.json에는 노드 단계가 없다)
    def _need_node_keys(self):
        if self.generator_version < NODE_KEYS_MIN_GENERATOR_VERSION:
            raise StackError(
                f"{self.path}: 생성기 판 {self.generator_version}에는 노드 단계 key가 없다"
                f"(필요: {NODE_KEYS_MIN_GENERATOR_VERSION} 이상)")

    @property
    def generator_version(self):
        return self.raw["generator"]["version"]

    @property
    def git_commit(self):
        """생성 시점의 commit. 알 수 없으면 None."""
        return self.raw["generator"]["git_commit"]

    @property
    def git_dirty(self):
        """생성 시점의 작업 트리 변경 여부. 알 수 없으면 None."""
        return self.raw["generator"]["git_dirty"]

    @property
    def images(self):
        """이미지 참조(sim_base, px4, ros_ws, xrce_agent, lichtblick). 파일에 적힌 값 그대로."""
        return self.raw["images"]

    @property
    def node_stages(self):
        """노드 단계(서비스 이름 목록의 목록). embedded는 빈 목록."""
        self._need_node_keys()
        return self.raw["startup"]["node_stages"]

    @property
    def ops_services(self):
        """Executor 서비스 이름(ops-N) 목록. embedded는 빈 목록."""
        self._need_node_keys()
        return self.raw["services"]["ops"]

    @property
    def params_dir(self):
        """params 디렉터리의 절대 경로. embedded는 None."""
        self._need_node_keys()
        rel = self.raw["run"]["params_dir"]
        return None if rel is None else self.resolve(rel)

    def params_path(self, vehicle):
        """기체의 Executor params 파일 절대 경로. embedded는 None."""
        self._need_node_keys()
        return None if vehicle.params_file is None else self.resolve(vehicle.params_file)

    # 생성기 판 5 이상의 key. 낮은 판이면 StackError
    def _need_world_keys(self):
        if self.generator_version < WORLD_KEYS_MIN_GENERATOR_VERSION:
            raise StackError(
                f"{self.path}: 생성기 판 {self.generator_version}에는 월드와 표적 key가 없다"
                f"(필요: {WORLD_KEYS_MIN_GENERATOR_VERSION} 이상)")

    @property
    def world_template(self):
        """world template의 저장소 기준 상대 경로(world.template)."""
        self._need_world_keys()
        return self.raw["world"]["template"]

    @property
    def world_file(self):
        """생성한 월드 SDF의 절대 경로. 생성한 월드가 없는 embedded는 None."""
        self._need_world_keys()
        rel = self.raw["world"]["file"]
        return None if rel is None else self.resolve(rel)

    @property
    def targets(self):
        """표적 목록(각 {id, start_s, loop, waypoints[{t,x,y,z}]}). 없으면 빈 목록."""
        self._need_world_keys()
        return self.raw["targets"]

    @property
    def targets_service(self):
        """targets 서비스 이름. 표적이 없으면 None."""
        self._need_world_keys()
        return self.raw["services"]["targets"]

    @property
    def sim_oracle_service(self):
        """sim-oracle 서비스 이름. 없는 구성(embedded 등)이면 None."""
        self._need_world_keys()
        return self.raw["services"]["sim_oracle"]

    def vehicle_by_vehicle_id(self, vehicle_id):
        """계약 식별자("px4_1")로 기체를 찾는다."""
        for v in self.vehicles:
            if v.vehicle_id == vehicle_id:
                return v
        raise StackLookupError(
            f"vehicle_id {vehicle_id!r}이 없다: {[v.vehicle_id for v in self.vehicles]}")

    # 기체 조회
    def vehicle_by_id(self, vid):
        for v in self.vehicles:
            if v.id == vid:
                return v
        raise StackLookupError(f"기체 id {vid!r}이 없다: {[v.id for v in self.vehicles]}")

    def vehicle_by_ns(self, ns):
        """ns는 stack.json 표기 그대로 비교한다(예: "/px4_1"). 빗금을 보정하지 않는다."""
        for v in self.vehicles:
            if v.ns == ns:
                return v
        raise StackLookupError(f"기체 ns {ns!r}이 없다: {[v.ns for v in self.vehicles]}")

    @property
    def namespaces(self):
        return [v.ns for v in self.vehicles]

    # 경로
    def resolve(self, rel):
        """stack.json 디렉터리 기준 상대 경로를 절대 경로로 푼다. 절대 경로나 상위 탈출은 거부."""
        if os.path.isabs(rel):
            raise StackError(f"상대 경로여야 한다: {rel!r} (host_ 필드는 resolve 대상이 아니다)")
        full = Path(os.path.normpath(self.dir / rel))
        if full != self.dir and self.dir not in full.parents:
            raise StackError(f"stack.json 디렉터리 밖을 가리킨다: {rel!r}")
        return full

    @property
    def compose_file(self):
        return self.resolve(self.raw["run"]["compose_file"])

    @property
    def ros_log_dir(self):
        return self.resolve(self.raw["run"]["ros_log_dir"])

    def ulog_path(self, vehicle):
        return self.resolve(vehicle.ulog_dir)

    def rootfs_path(self, vehicle):
        return self.resolve(vehicle.rootfs_dir)

    @property
    def host_dir(self):
        """run.host_dir. 호스트 절대 경로(컨테이너 안에서는 존재하지 않을 수 있다)."""
        return Path(self.raw["run"]["host_dir"])


def _vehicle(d):
    return Vehicle(
        id=d["id"], instance=d["instance"], ns=d["ns"], px4_ns=d["px4_ns"], sysid=d["sysid"],
        uxrce_key=d["uxrce_key"], airframe=d["airframe"], gz_model_name=d["gz_model_name"],
        service=d["service"], pose=dict(d["pose"]), mavlink=dict(d["mavlink"]),
        rootfs_dir=d["rootfs_dir"], ulog_dir=d["ulog_dir"], host_rootfs_dir=d["host_rootfs_dir"],
        expected_params=dict(d["expected_params"]), derived_params=dict(d["derived_params"]),
        raw=d, vehicle_id=d.get("vehicle_id"), params_file=d.get("params_file"),
        executor_node=d.get("executor_node"),
        expect_gps=d.get("expect_gps"))


def loads(text, path="<string>"):
    """JSON 문자열에서 Stack을 만든다. path는 stack.json 위치(상대 경로 해석 기준)."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise StackError(f"{path}: JSON 파싱 실패: {e}") from e
    try:
        _validate(data)
    except StackError as e:
        raise StackError(f"{path}: {e}") from e
    return Stack(path=Path(os.path.abspath(path)), raw=data,
                 vehicles=tuple(_vehicle(v) for v in data["vehicles"]))


def load(path):
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise StackError(f"stack.json을 읽을 수 없다: {p}: {e}") from e
    return loads(text, str(p))


def load_from_env(environ=None):
    env = os.environ if environ is None else environ
    p = env.get(ENV_VAR)
    if not p:
        raise StackError(f"환경변수 {ENV_VAR}가 없다")
    return load(p)
