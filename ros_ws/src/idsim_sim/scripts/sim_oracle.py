#!/usr/bin/env python3
# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""정답 pose 노드(sim-oracle). SITL 판정 전용이고 계약이 아니다(decisions.md 쟁점 5).

sim-base 이미지의 compose 서비스 sim-oracle이 이 파일을 마운트 경로에서 직접 실행한다(설치 대상이 아니다).
  python3 /opt/idsim/sim/scripts/sim_oracle.py [--ros-args ...]

하는 일
- gz-transport로 /world/<IDSIM_WORLD_NAME>/pose/info(gz.msgs.Pose_V)를 직접 구독한다. ros_gz_bridge와 /clock을
  쓰지 않고, dynamic_pose/info는 구독하지 않는다.
- IDSIM_ORACLE_VEHICLES("px4_1=x500_1 px4_2=x500_2")의 top-level model pose에 base_link 오프셋을 합성한다.
  p_bl = p_model + R_model * offset, 자세는 model 자세 그대로다. 오프셋은 시작할 때 sdformat14로 모델 SDF
  (GZ_SIM_RESOURCE_PATH에서 찾은 model://<이름에서 _N을 뗀 것>/model.sdf)를 해석해 얻는다. base_link가 model
  프레임에서 회전을 가지면 "자세는 model과 같다"는 전제가 깨지므로 시작을 거부한다.
- /sim/<vehicle_id>/pose(geometry_msgs/PoseStamped, frame_id "world", stamp는 pose/info header의 sim 시각)를
  낸다. 주기는 SceneBroadcaster의 pose/info 주기를 따른다(sim 시간 약 50 Hz). 기체마다 직전 발행보다 stamp가
  MIN_PERIOD_NS 이상 큰 표본만 내고, stamp 0과 역행은 내지 않는다.
- 준비 표시 파일 /tmp/idsim/oracle_ready: run()의 맨 앞(설정 해석 전)에서 지우고, 모든 기체의 pose를 한 번 이상 낸 순간 임시 파일 +
  rename으로 만든다(idsim_sim/ready.py 재사용. 내용은 기체마다 "<vehicle_id> <첫 stamp>" 한 줄).

모듈 수준에서는 표준 라이브러리와 idsim_sim.ready(표준 라이브러리만 쓴다)만 import한다. rclpy, gz, sdformat14,
geometry_msgs는 main 안에서 import한다. 그래서 순수 함수(이름 조립, 환경 변수 해석, 오프셋 합성, 발행 판단)는
gz 바인딩이 없는 ros-ws 이미지의 단위 테스트(test/test_sim_oracle.py)가 이 파일을 경로로 읽어 시험한다.

- 기체마다 stamp 역행에 들어갈 때 오류 로그를 한 번 남긴다(직전 stamp를 넘어 다시 발행하면 풀린다).

종료 코드: 설정 오류(환경 변수 누락과 형식, 모델 SDF를 찾지 못함, base_link 없음이나 회전 있음, 구독 실패)는 2,
pose/info 콜백의 예외(표시 파일 쓰기 실패, 잘못된 쿼터니언 등)는 오류 로그와 표시 파일 삭제 뒤 3,
SIGINT/SIGTERM 정상 종료는 0.
"""

import math
import os
import re
import sys
import traceback

# 마운트된 패키지 디렉터리(scripts/의 부모)를 path에 넣어 idsim_sim.ready를 쓴다. 설치된 idsim_sim이 있으면 같은 코드다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idsim_sim.ready import ReadyTracker, remove_ready_file, write_ready_file  # noqa: E402

EXIT_CONFIG_ERROR = 2
EXIT_RUNTIME_ERROR = 3
READY_PATH = "/tmp/idsim/oracle_ready"
ENV_WORLD_NAME = "IDSIM_WORLD_NAME"
ENV_VEHICLES = "IDSIM_ORACLE_VEHICLES"
ENV_RESOURCE_PATH = "GZ_SIM_RESOURCE_PATH"

SIM_TOPIC_PREFIX = "/sim"
ORACLE_TOPIC_SUFFIX = "pose"
POSE_INFO_SUFFIX = "pose/info"
FRAME_ID = "world"
BASE_LINK = "base_link"
# pose/info 표본 간격은 sim 시간 20 ms가 대부분이고 12-16 ms도 있다(실측). 그보다 짧은 간격만 걸러 상한을 100 Hz로 둔다.
MIN_PERIOD_NS = 10_000_000
# base_link 회전이 항등인지 볼 때의 허용(쿼터니언 성분)
IDENTITY_TOL = 1e-9

# tools/gen_compose.py의 WORLD_NAME_RE와 같다
WORLD_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
# vehicle_id는 ROS 이름 토큰 하나다. 내용(번호)은 해석하지 않는다(docs/interface.md "이름과 식별자")
VEHICLE_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# 기체 model 이름은 <모델>_<N>이다(생성기가 airframe에서 파생). 모델 SDF는 <모델>에서 찾는다
MODEL_NAME_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)_([1-9][0-9]*)")


class ConfigError(Exception):
    """설정 오류. main이 EXIT_CONFIG_ERROR로 끝낸다."""


def pose_info_topic(world_name):
    """구독할 gz 토픽. /world/<월드>/pose/info. dynamic_pose가 아니다."""
    if not isinstance(world_name, str) or WORLD_NAME_RE.fullmatch(world_name) is None:
        raise ConfigError(f"월드 이름이 ^[A-Za-z0-9_-]{{1,64}}$에 맞지 않는다: {world_name!r}")
    return f"/world/{world_name}/{POSE_INFO_SUFFIX}"


def oracle_pose_topic(vehicle_id):
    """정답 pose 토픽의 절대 이름 /sim/<vehicle_id>/pose. tests/support가 같은 사례 표로 따로 조립한다."""
    if not isinstance(vehicle_id, str) or VEHICLE_ID_RE.fullmatch(vehicle_id) is None:
        raise ConfigError(f"vehicle_id가 ROS 이름 토큰 하나가 아니다: {vehicle_id!r}")
    return f"{SIM_TOPIC_PREFIX}/{vehicle_id}/{ORACLE_TOPIC_SUFFIX}"


def model_base_name(model_name):
    """'x500_1' -> 'x500'. 모델 SDF를 찾을 이름."""
    m = MODEL_NAME_RE.fullmatch(model_name) if isinstance(model_name, str) else None
    if m is None:
        raise ConfigError(f"model 이름이 <모델>_<N> 형식이 아니다: {model_name!r}")
    return m.group(1)


def parse_vehicles(text):
    """IDSIM_ORACLE_VEHICLES 값 -> [(vehicle_id, model_name), ...](적힌 순서). 형식이 틀리면 ConfigError."""
    if text is None or not text.strip():
        raise ConfigError(f"{ENV_VEHICLES}가 비었다(예: 'px4_1=x500_1 px4_2=x500_2')")
    pairs = []
    for item in text.split():
        vid, sep, model = item.partition("=")
        if not sep:
            raise ConfigError(f"{ENV_VEHICLES} 항목이 <vehicle_id>=<model> 형식이 아니다: {item!r}")
        oracle_pose_topic(vid)
        model_base_name(model)
        pairs.append((vid, model))
    vids = [v for v, _ in pairs]
    models = [m for _, m in pairs]
    if len(set(vids)) != len(vids):
        raise ConfigError(f"{ENV_VEHICLES}에 vehicle_id가 중복된다: {text!r}")
    if len(set(models)) != len(models):
        raise ConfigError(f"{ENV_VEHICLES}에 model 이름이 중복된다: {text!r}")
    return pairs


def load_env(environ):
    """환경 변수 -> (월드 이름, 구독 토픽, [(vehicle_id, model), ...], 자원 경로 목록)."""
    world = environ.get(ENV_WORLD_NAME)
    if not world:
        raise ConfigError(f"{ENV_WORLD_NAME}가 비었다")
    topic = pose_info_topic(world)
    vehicles = parse_vehicles(environ.get(ENV_VEHICLES))
    paths = [p for p in environ.get(ENV_RESOURCE_PATH, "").split(":") if p]
    if not paths:
        raise ConfigError(f"{ENV_RESOURCE_PATH}가 비었다")
    return world, topic, vehicles, paths


def find_model_dir(name, resource_paths, isdir=os.path.isdir):
    """model://<name>을 자원 경로에서 앞에서부터 찾는다(gz와 같은 순서). 없으면 None."""
    for base in resource_paths:
        candidate = os.path.join(base, name)
        if isdir(candidate):
            return candidate
    return None


def quat_rotate(q, v):
    """단위 쿼터니언 q = (w, x, y, z)로 벡터 v를 회전한다. q는 정규화해서 쓰고 노름이 0이면 ValueError."""
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if not n > 0.0 or not math.isfinite(n):
        raise ValueError(f"쿼터니언 노름이 유한한 양수가 아니다: {q!r}")
    w, x, y, z = w / n, x / n, y / n, z / n
    vx, vy, vz = v
    # t = 2 * (q_vec x v), v' = v + w * t + q_vec x t
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def compose_base_link(p_model, q_model, offset):
    """p_bl = p_model + R(q_model) * offset. 자세는 q_model 그대로 돌려준다. 반환 (p_bl, q_model)."""
    r = quat_rotate(q_model, offset)
    return (p_model[0] + r[0], p_model[1] + r[1], p_model[2] + r[2]), tuple(q_model)


def check_offset_rotation(q):
    """base_link의 model 프레임 회전이 항등(부호 무관)이 아니면 ConfigError."""
    w, x, y, z = q
    if abs(abs(w) - 1.0) > IDENTITY_TOL or max(abs(x), abs(y), abs(z)) > IDENTITY_TOL:
        raise ConfigError(f"base_link가 model 프레임에서 회전을 가진다(자세를 model과 같게 둘 수 없다): {q!r}")


PUBLISH = "publish"
SKIP_ZERO = "skip_zero"  # stamp가 0 이하
SKIP_BACKWARD = "skip_backward"  # 직전 발행 stamp보다 작다(sim 시계 역행). 호출자가 역행에 들어갈 때 오류 로그를 남긴다
SKIP_SHORT = "skip_short"  # 직전 발행과 같거나 min_period_ns 미만 뒤


def stamp_decision(last_ns, stamp_ns, min_period_ns=MIN_PERIOD_NS):
    """기체 하나의 발행 판단. 위 네 값 가운데 하나."""
    if stamp_ns <= 0:
        return SKIP_ZERO
    if last_ns is None:
        return PUBLISH
    if stamp_ns < last_ns:
        return SKIP_BACKWARD
    if stamp_ns - last_ns < min_period_ns:
        return SKIP_SHORT
    return PUBLISH


def should_publish(last_ns, stamp_ns, min_period_ns=MIN_PERIOD_NS):
    """stamp 0은 내지 않고, 직전 발행 뒤로는 min_period_ns 이상 지난 표본만 낸다."""
    return stamp_decision(last_ns, stamp_ns, min_period_ns) == PUBLISH


def index_models(entries, names):
    """Pose_V 항목 [(name, pos, quat), ...]에서 names에 든 이름만 {name: (pos, quat)}로. 같은 이름이 둘 이상이면 제외하고
    그 이름을 두 번째 값(집합)으로 돌려준다(link 이름은 scope가 없어 겹칠 수 있다. top-level model 이름은 유일해야 한다)."""
    found = {}
    dup = set()
    for name, pos, quat in entries:
        if name not in names:
            continue
        if name in found:
            dup.add(name)
            continue
        found[name] = (pos, quat)
    for name in dup:
        del found[name]
    return found, dup


class OracleCore:
    """gz/rclpy 없는 처리 본체. step()이 표본 하나에서 낼 (vehicle_id, p_bl, q) 목록과 준비 완료 여부를 정한다."""

    def __init__(self, vehicles, offsets, min_period_ns=MIN_PERIOD_NS):
        """vehicles: [(vehicle_id, model), ...], offsets: {model: (x, y, z)}."""
        self._vehicles = list(vehicles)
        self._offsets = dict(offsets)
        self._models = {m for _, m in self._vehicles}
        self._last = {v: None for v, _ in self._vehicles}
        self._backward = {v: False for v, _ in self._vehicles}
        self._min_period_ns = min_period_ns
        self._ready = ReadyTracker([v for v, _ in self._vehicles])

    def step(self, stamp_ns, entries):
        """반환 (발행 목록 [(vehicle_id, p_bl, q)], 준비 완료면 [(vehicle_id, 첫 stamp)] 아니면 None, 중복 이름 집합,
        이번 표본에서 역행에 들어간 기체 [(vehicle_id, 직전 발행 stamp)]). 역행은 기체마다 들어갈 때 한 번만 알리고,
        직전 stamp를 넘어 다시 발행하면 풀린다(표적 어댑터와 같은 규칙)."""
        found, dup = index_models(entries, self._models)
        out = []
        ready = None
        backward = []
        for vid, model in self._vehicles:
            if model not in found:
                continue
            decision = stamp_decision(self._last[vid], stamp_ns, self._min_period_ns)
            if decision == SKIP_BACKWARD:
                if not self._backward[vid]:
                    backward.append((vid, self._last[vid]))
                self._backward[vid] = True
                continue
            if decision != PUBLISH:
                continue
            self._backward[vid] = False
            pos, quat = found[model]
            p_bl, q = compose_base_link(pos, quat, self._offsets[model])
            out.append((vid, p_bl, q))
            self._last[vid] = stamp_ns
            done = self._ready.record(vid, stamp_ns)
            if done is not None:
                ready = done
        return out, ready, dup, backward


class FatalOnError:
    """콜백 감싸기. 첫 예외에서 on_fatal(예외)을 한 번 부르고 그 뒤 호출은 아무것도 하지 않는다.

    gz-transport 콜백은 pybind11 스레드에서 불리므로 예외가 그 밖으로 나갈 때의 동작(프로세스 종료인지 삼켜지는지)에
    기대지 않는다. 여기서 잡아 프로세스를 0이 아닌 코드로 끝내게 해 조용히 발행만 멈추는 상태를 막는다.
    """

    def __init__(self, fn, on_fatal):
        self._fn = fn
        self._on_fatal = on_fatal
        self.failed = False

    def __call__(self, *args):
        if self.failed:
            return None
        try:
            return self._fn(*args)
        except Exception as e:  # noqa: BLE001 - 어떤 예외든 프로세스 종료로 바꾼다
            self.failed = True
            self._on_fatal(e)
            return None


def load_base_link_offset(model_dir):  # pragma: no cover - sdformat14는 sim-base에만 있다
    """모델 SDF에서 base_link의 model 프레임 기준 위치 (x, y, z)를 sdformat14로 얻는다."""
    import sdformat14

    resource_paths = [p for p in os.environ.get(ENV_RESOURCE_PATH, "").split(":") if p]

    def find(uri):
        prefix = "model://"
        if uri.startswith(prefix):
            found = find_model_dir(uri[len(prefix):], resource_paths)
            return found or ""
        return uri

    cfg = sdformat14.ParserConfig()
    cfg.set_find_callback(find)
    root = sdformat14.Root()
    path = os.path.join(model_dir, "model.sdf")
    try:
        root.load(path, cfg)
    except sdformat14.SDFErrorsException as e:
        raise ConfigError(f"모델 SDF를 해석하지 못했다: {path}: {e}") from e
    model = root.model()
    if model is None:
        raise ConfigError(f"모델 SDF에 model이 없다: {path}")
    link = model.link_by_name(BASE_LINK)
    if link is None:
        raise ConfigError(f"모델 SDF에 {BASE_LINK}가 없다: {path}")
    pose = link.semantic_pose().resolve("__model__")
    rot = pose.rot()
    check_offset_rotation((rot.w(), rot.x(), rot.y(), rot.z()))
    pos = pose.pos()
    return (pos.x(), pos.y(), pos.z())


def run(argv):  # pragma: no cover - gz와 rclpy가 있는 sim-base에서만 돈다
    # 재시작 때 옛 표시 파일이 남는 창을 인터프리터 기동 시간으로 줄이려고 무엇보다 먼저 지운다
    remove_ready_file(READY_PATH)
    try:
        world, topic, vehicles, paths = load_env(os.environ)
        offsets = {}
        for _, model in vehicles:
            base = model_base_name(model)
            model_dir = find_model_dir(base, paths)
            if model_dir is None:
                raise ConfigError(f"model://{base}를 {ENV_RESOURCE_PATH}={':'.join(paths)}에서 찾지 못했다")
            offsets[model] = load_base_link_offset(model_dir)
    except ConfigError as e:
        print(f"sim_oracle: 설정 오류: {e}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    import rclpy
    from geometry_msgs.msg import PoseStamped
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.transport13 import Node as GzNode
    from rclpy.executors import ExternalShutdownException
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

    rclpy.init(args=argv)
    node = rclpy.create_node("sim_oracle")
    log = node.get_logger()
    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10,
                     reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    pubs = {vid: node.create_publisher(PoseStamped, oracle_pose_topic(vid), qos) for vid, _ in vehicles}
    core = OracleCore(vehicles, offsets)
    for vid, model in vehicles:
        log.info(f"{model} -> {oracle_pose_topic(vid)}, base_link 오프셋 {offsets[model]}")
    warned_dup = set()
    exit_code = [0]

    def on_fatal(exc):
        # gz-transport 스레드. 표시 파일을 지우고 spin을 끝내 run이 EXIT_RUNTIME_ERROR를 돌려주게 한다
        log.error(f"pose/info 콜백에서 예외가 났다. 종료한다: {type(exc).__name__}: {exc}\n"
                  + "".join(traceback.format_exception(exc)))
        exit_code[0] = EXIT_RUNTIME_ERROR
        try:
            remove_ready_file(READY_PATH)
            rclpy.try_shutdown()
        except Exception:  # noqa: BLE001 - 정리에 실패해도 반드시 끝낸다
            os._exit(EXIT_RUNTIME_ERROR)

    def on_pose_v(msg):
        # gz-transport 스레드에서 불린다. 종료 중에는 내지 않는다
        if not rclpy.ok():
            return
        stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nsec
        entries = [(p.name, (p.position.x, p.position.y, p.position.z),
                    (p.orientation.w, p.orientation.x, p.orientation.y, p.orientation.z)) for p in msg.pose]
        out, ready, dup, backward = core.step(stamp_ns, entries)
        for name in dup - warned_dup:
            log.error(f"pose/info에 이름 {name}이 둘 이상이다. 그 기체의 표본을 내지 않는다")
            warned_dup.add(name)
        for vid, last_ns in backward:
            log.error(f"{vid}: pose/info stamp가 역행했다(직전 발행 {last_ns} ns, 지금 {stamp_ns} ns). "
                      "직전 stamp를 넘을 때까지 발행하지 않는다")
        for vid, p, q in out:
            m = PoseStamped()
            m.header.stamp.sec = msg.header.stamp.sec
            m.header.stamp.nanosec = msg.header.stamp.nsec
            m.header.frame_id = FRAME_ID
            m.pose.position.x, m.pose.position.y, m.pose.position.z = p
            m.pose.orientation.w, m.pose.orientation.x, m.pose.orientation.y, m.pose.orientation.z = q
            pubs[vid].publish(m)
        if ready is not None:
            write_ready_file(ready, READY_PATH)
            log.info(f"준비: {READY_PATH}")

    gz_node = GzNode()
    if not gz_node.subscribe(Pose_V, topic, FatalOnError(on_pose_v, on_fatal)):
        log.error(f"gz 토픽 구독 실패: {topic}")
        node.destroy_node()
        rclpy.try_shutdown()
        return EXIT_CONFIG_ERROR
    log.info(f"구독: {topic}")
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # 발행자를 없애기 전에 gz 콜백을 끊는다
        gz_node.unsubscribe(topic)
        node.destroy_node()
        rclpy.try_shutdown()
    return exit_code[0]


def main(argv=None):  # pragma: no cover
    # SIGINT와 SIGTERM은 rclpy.init이 설치하는 signal handler가 받아 spin을 끝낸다(정상 종료 0)
    return run(sys.argv if argv is None else argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
