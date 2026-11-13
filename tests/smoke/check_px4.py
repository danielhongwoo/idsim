#!/usr/bin/env python3
"""스모크 embedded, px4-out, px4-in의 PX4 쪽 토픽 판정. 담당: px4-engineer.

ros-ws 컨테이너 안에서 실행한다(px4_msgs, rclpy 필요). 판정 기준은
docs/smoke-test.md를 따른다.

사용법
  check_px4.py --ns px4_1 --system-id 2 --timeout 30   # embedded, px4-out
  check_px4.py --ns px4_1 --system-id 2 --timeout 60 --arm   # px4-in
  check_px4.py --ns px4_1 --system-id 2 --timeout 60 \
      --expect-origin 37.56647297 126.978067914 38.24  # px4-out (원점 판정 추가)

판정 항목
  status_topic     ros2 topic list에서 ^/(<ns>/)?fmu/out/vehicle_status(_v[0-9]+)?$
                   에 맞는 토픽이 정확히 하나, 타입 px4_msgs/msg/VehicleStatus
  status_received  sensor_data QoS로 1회 이상 수신, timestamp가 0이 아님
  timestamp_rises  다시 받은 메시지의 timestamp가 앞의 것보다 큼
  system_id        vehicle_status.system_id가 기대값과 같음
  (--expect-origin일 때 px4-out)
  gps_topic        ^/(<ns>/)?fmu/out/vehicle_gps_position(_v[0-9]+)?$ 에 맞는 토픽이
                   정확히 하나, 타입 px4_msgs/msg/SensorGps
  gps_origin       fix_type >= 3(3D)인 메시지 ORIGIN_SAMPLES개의 위도/경도/고도가
                   기대 원점과 수평 ORIGIN_TOL_H_M, 수직 ORIGIN_TOL_V_M 안(최대 오차로 판정)
  (--arm일 때 px4-in)
  arm_ack          VEHICLE_CMD_COMPONENT_ARM_DISARM(param1 1.0) 발행 후
                   vehicle_command_ack.result 0(ACCEPTED)
  armed_hold       arming_state가 ARMING_STATE_ARMED로 N회 연속
  disarm_ack       같은 명령 param1 0.0 발행 후 ack result 0
  disarmed_hold    arming_state가 ARMING_STATE_DISARMED로 N회 연속

결과는 JSON 한 덩어리로 stdout에 쓴다. 모두 통과하면 종료 코드 0, 아니면 1.
앞 항목이 실패하면 뒤 항목은 실행하지 않는다(skipped로 남긴다).

타임아웃은 벽시계이며 --timeout은 전체 예산이다. 각 단계는 남은 시간만 쓴다.

PX4 쪽 사실 (v1.17.0 소스 기준)
- uxrce_dds_client의 /fmu/in 데이터 리더는 BEST_EFFORT, VOLATILE이다
  (src/modules/uxrce_dds_client/utilities.hpp). sensor_data QoS 발행자로 맞는다.
  손실될 수 있으므로 명령은 ack가 올 때까지 주기적으로 다시 보낸다.
- Commander는 target_system이 자기 system_id(MAV_SYS_ID = 인스턴스 + 1)이거나 0,
  target_component가 자기 component_id(1)이거나 0인 명령만 처리한다
  (src/modules/commander/Commander.cpp handle_command).
- 시동은 사전 점검(EKF 수렴, home 등)이 끝나기 전에는
  VEHICLE_CMD_RESULT_TEMPORARILY_REJECTED(1)로 거부된다. 그래서 시간 안에서 재시도한다.
- 부팅 직후 모드는 Hold(AUTO_LOITER)이며 수동 조종 입력 없이 시동된다.
- 원점 판정 토픽. uORB sensor_gps는 DDS로 나가지 않고, 센서 모듈이 고른(단일 수신기면
  그대로 통과시킨) vehicle_gps_position이 fmu/out/vehicle_gps_position(SensorGps)으로
  나간다(tests/fixtures/px4/v1.17.0/topics.txt). gz 경로에서 이 값은 gz navsat 센서
  값을 gz_bridge가 옮긴 것이며 EKF를 거치지 않는다. vehicle_global_position(EKF 추정)과
  home_position(시동 등에서 다시 설정됨)보다 "월드 원점이 적용되었는가"에 직접적이다.
- --expect-origin의 기대값은 호출하는 쪽이 주는 기체별 base_link(GNSS 센서) 위치다.
  생성기가 world.origin과 스폰 pose로 계산해 stack.json vehicles[].expect_gps에 싣는다.
  고도는 world.origin.alt + 스폰 z + 센서 높이(x500은 0.24 m)이므로 센서 높이가 기대값에
  이미 들어 있다. 이 스크립트는 스폰 pose나 센서 높이를 보정하지 않고 받은 값과만 비교한다.
  다대 비교는 호출하는 쪽이 기체(vehicles[i])마다 이 스크립트를 따로 부른다.
"""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import rclpy  # noqa: E402
from rclpy.qos import qos_profile_sensor_data  # noqa: E402

from px4_msgs.msg import (  # noqa: E402
    SensorGps,
    VehicleCommand,
    VehicleCommandAck,
    VehicleStatus,
)

from tests.support.receive import (  # noqa: E402
    SpinThread,
    hold_state,
    receive_once,
    wait_for_topic,
)

STATUS_TYPE = "px4_msgs/msg/VehicleStatus"
COMMAND_TYPE = "px4_msgs/msg/VehicleCommand"
ACK_TYPE = "px4_msgs/msg/VehicleCommandAck"
GPS_TYPE = "px4_msgs/msg/SensorGps"

# 명령 재전송 간격(초, 벽시계). ack를 기다리는 동안 이 간격으로 다시 보낸다.
RESEND_S = 0.5
# PX4 autopilot의 component_id. Commander가 0 또는 이 값만 받는다.
TARGET_COMPONENT = 1
# 명령 발신자 식별. GCS 관례값(255, 190)과 겹치지 않게 임의로 둔다.
SOURCE_SYSTEM = 254
SOURCE_COMPONENT = 1

# 원점 판정 허용 오차. 기대값은 기체별 base_link(GNSS 센서) 위치이므로 오차는 잡음만 남는다.
# 실측 1(스모크 px4-out, 기체 1을 (6, -3)에 스폰, 3D fix 표본 10): 수평 최대 0.051 m,
# 수직 최대 0.063 m.
# 실측 2(같은 구성, 90초 2666개): 수평 최대 0.070 m, 고도 38.098-38.338 m. 기대 고도 38.24 m
# 기준 수직 최대 약 0.14 m(38.24 - 38.098 = 0.142).
# 잡음 출처는 Gazebo x500 NavSat가 아니라(model.sdf에 noise 요소 없음) PX4 GZBridge의
# 1차 Gauss-Markov 잡음이다(PX4 소스 src/modules/simulation/gz_bridge/GZBridge.cpp
# 680-711행, addGpsNoise).
# 수평 0.5 m는 실측 2 최대의 약 7배, 수직 1.0 m는 약 7배다(실측 1 기준 약 10배, 약 16배).
# 원점 소수 다섯째 자리(약 1.1 m) 차이를 잡는다.
# 기체 1의 (6, -3) 오프셋 때문에 원점 미적용(약 6.7 m)이거나 x/y 반전(약 13 m)이어도 0.5 m를 크게 넘는다.
# 원점이 아예 적용되지 않으면 기본 월드(취리히, 47.398, 8.546) 값이 나와 수천 km 차이다.
ORIGIN_TOL_H_M = 0.5
ORIGIN_TOL_V_M = 1.0
# 판정에 쓰는 3D fix 메시지 수. 최대 오차로 판정한다.
ORIGIN_SAMPLES = 10
# WGS84 장반경(m). 오차가 작을 때의 국소 평면 근사에 쓴다.
EARTH_RADIUS_M = 6378137.0


def topic_regex(ns, direction, base):
    """^/(<ns>/)?fmu/<direction>/<base>(_v[0-9]+)?$ 형태의 정규식.

    ns가 비어 있으면 접두사 없는 토픽만 맞는다.
    """
    prefix = "/" + re.escape(ns) if ns else ""
    return "^%s/fmu/%s/%s(_v[0-9]+)?$" % (prefix, direction, re.escape(base))


class Deadline:
    """전체 벽시계 예산."""

    def __init__(self, total_s):
        self._end = time.monotonic() + total_s

    def left(self):
        return max(0.0, self._end - time.monotonic())


class Report:
    def __init__(self, args):
        self.data = {
            "ns": args.ns,
            "expected_system_id": args.system_id,
            "timeout_s": args.timeout,
            "arm": args.arm,
            "topics": {},
            "checks": [],
        }
        # 인자가 없을 때 출력이 이전과 같도록 키를 넣지 않는다
        if args.expect_origin is not None:
            lat, lon, alt = args.expect_origin
            self.data["expected_origin"] = {"lat": lat, "lon": lon, "alt": alt}

    def check(self, name, ok, **detail):
        self.data["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    def skip(self, *names):
        for name in names:
            self.data["checks"].append({"name": name, "ok": False, "detail": {"skipped": True}})

    def ok(self):
        return bool(self.data["checks"]) and all(c["ok"] for c in self.data["checks"])

    def emit(self):
        self.data["ok"] = self.ok()
        json.dump(self.data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        sys.stdout.flush()


def find_unique_topic(node, regex, expected_type, deadline, report, check_name):
    """정규식에 맞는 토픽이 정확히 하나이고 타입이 맞으면 그 이름, 아니면 None."""
    hit = wait_for_topic(node, regex, deadline.left())
    if hit is None:
        report.check(check_name, False, regex=regex, reason="no matching topic")
        return None
    pat = re.compile(regex)
    matches = sorted(
        (name, list(types)) for name, types in node.get_topic_names_and_types()
        if pat.search(name)
    )
    name, types = matches[0]
    ok = len(matches) == 1 and types == [expected_type]
    report.check(check_name, ok, regex=regex, matches=matches, expected_type=expected_type)
    return name if ok else None


def make_command(node, target_system, param1):
    msg = VehicleCommand()
    # PX4 ROS 2 offboard 예제와 같이 노드 시각(마이크로초)을 넣는다.
    msg.timestamp = node.get_clock().now().nanoseconds // 1000
    msg.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
    msg.param1 = float(param1)
    msg.target_system = int(target_system)
    msg.target_component = TARGET_COMPONENT
    msg.source_system = SOURCE_SYSTEM
    msg.source_component = SOURCE_COMPONENT
    msg.confirmation = 0
    msg.from_external = True
    return msg


def send_until_ack(node, pub, ack_topic, cmd_factory, deadline):
    """명령을 RESEND_S마다 보내며 ARM_DISARM에 대한 ack result 0을 기다린다.

    (accepted, 받은 result 목록) 을 돌려준다.
    """
    results = []
    accepted = {"v": False}

    def on_ack(msg):
        if msg.command != VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM:
            return
        results.append(int(msg.result))
        if msg.result == VehicleCommandAck.VEHICLE_CMD_RESULT_ACCEPTED:
            accepted["v"] = True

    sub = node.create_subscription(VehicleCommandAck, ack_topic, on_ack, qos_profile_sensor_data)
    try:
        with SpinThread(node):
            while not accepted["v"] and deadline.left() > 0.0:
                pub.publish(cmd_factory())
                end = time.monotonic() + min(RESEND_S, deadline.left())
                while not accepted["v"] and time.monotonic() < end:
                    time.sleep(0.02)
    finally:
        node.destroy_subscription(sub)
    return accepted["v"], results


def run_status_checks(node, args, deadline, report):
    """embedded, px4-out 공통. 성공하면 vehicle_status 토픽 이름, 실패하면 None."""
    status_topic = find_unique_topic(
        node, topic_regex(args.ns, "out", "vehicle_status"), STATUS_TYPE,
        deadline, report, "status_topic")
    report.data["topics"]["vehicle_status"] = status_topic
    if status_topic is None:
        report.skip("status_received", "timestamp_rises", "system_id")
        return None

    first = receive_once(node, status_topic, VehicleStatus, deadline.left())
    if not report.check("status_received", first is not None and first.timestamp != 0,
                        timestamp=None if first is None else int(first.timestamp)):
        report.skip("timestamp_rises", "system_id")
        return None

    second = receive_once(node, status_topic, VehicleStatus, deadline.left())
    ts2 = None if second is None else int(second.timestamp)
    report.check("timestamp_rises", second is not None and ts2 > int(first.timestamp),
                 first=int(first.timestamp), second=ts2)

    latest = second if second is not None else first
    ok = report.check("system_id", int(latest.system_id) == args.system_id,
                      received=int(latest.system_id), expected=args.system_id,
                      arming_state=int(latest.arming_state),
                      nav_state=int(latest.nav_state),
                      pre_flight_checks_pass=bool(latest.pre_flight_checks_pass))
    if not report.ok():
        return None
    return status_topic if ok else None


def origin_error_m(lat, lon, alt, exp_lat, exp_lon, exp_alt):
    """(수평 오차 m, 수직 오차 m). 수평은 기대 위도 기준 국소 평면 근사."""
    dn = math.radians(lat - exp_lat) * EARTH_RADIUS_M
    de = math.radians(lon - exp_lon) * EARTH_RADIUS_M * math.cos(math.radians(exp_lat))
    return math.hypot(dn, de), abs(alt - exp_alt)


def collect_gps_fixes(node, topic, n, timeout_s):
    """fix_type >= 3D인 SensorGps를 n개까지 모은다. (모은 목록, 받은 전체 수)."""
    fixes = []
    total = {"n": 0}

    def cb(msg):
        total["n"] += 1
        if len(fixes) < n and msg.fix_type >= SensorGps.FIX_TYPE_3D:
            fixes.append((float(msg.latitude_deg), float(msg.longitude_deg),
                          float(msg.altitude_msl_m), int(msg.fix_type)))

    sub = node.create_subscription(SensorGps, topic, cb, qos_profile_sensor_data)
    try:
        with SpinThread(node):
            end = time.monotonic() + timeout_s
            while len(fixes) < n and time.monotonic() < end:
                time.sleep(0.05)
    finally:
        node.destroy_subscription(sub)
    return list(fixes), total["n"]


def run_origin_checks(node, args, deadline, report):
    """px4-out. vehicle_gps_position이 기대 GNSS 위치(기체별 base_link)를 보고하는지."""
    gps_topic = find_unique_topic(
        node, topic_regex(args.ns, "out", "vehicle_gps_position"), GPS_TYPE,
        deadline, report, "gps_topic")
    report.data["topics"]["vehicle_gps_position"] = gps_topic
    if gps_topic is None:
        report.skip("gps_origin")
        return

    exp_lat, exp_lon, exp_alt = args.expect_origin
    fixes, received = collect_gps_fixes(node, gps_topic, ORIGIN_SAMPLES, deadline.left())
    detail = {
        "expected": {"lat": exp_lat, "lon": exp_lon, "alt": exp_alt},
        "tol_horizontal_m": ORIGIN_TOL_H_M,
        "tol_vertical_m": ORIGIN_TOL_V_M,
        "samples_wanted": ORIGIN_SAMPLES,
        "samples_3d_fix": len(fixes),
        "messages_received": received,
    }
    if len(fixes) < ORIGIN_SAMPLES:
        detail["reason"] = "not enough 3D fix messages"
        if fixes:
            lat, lon, alt, _ = fixes[-1]
            detail["last"] = {"lat": lat, "lon": lon, "alt_msl": alt}
        report.check("gps_origin", False, **detail)
        return

    errs = [origin_error_m(lat, lon, alt, exp_lat, exp_lon, exp_alt)
            for lat, lon, alt, _ in fixes]
    worst_h = max(e[0] for e in errs)
    worst_v = max(e[1] for e in errs)
    lat, lon, alt, fix_type = fixes[-1]
    detail.update({
        "last": {"lat": lat, "lon": lon, "alt_msl": alt, "fix_type": fix_type},
        "max_horizontal_m": round(worst_h, 3),
        "max_vertical_m": round(worst_v, 3),
    })
    report.check("gps_origin", worst_h <= ORIGIN_TOL_H_M and worst_v <= ORIGIN_TOL_V_M,
                 **detail)


def run_arm_checks(node, args, deadline, report, status_topic):
    """px4-in. 시동, 유지 확인, 시동 끄기, 복귀 확인."""
    names = ("command_topic", "ack_topic", "arm_ack", "armed_hold", "disarm_ack", "disarmed_hold")

    cmd_topic = find_unique_topic(
        node, topic_regex(args.ns, "in", "vehicle_command"), COMMAND_TYPE,
        deadline, report, "command_topic")
    if cmd_topic is None:
        report.skip(*names[1:])
        return
    ack_topic = find_unique_topic(
        node, topic_regex(args.ns, "out", "vehicle_command_ack"), ACK_TYPE,
        deadline, report, "ack_topic")
    if ack_topic is None:
        report.skip(*names[2:])
        return
    report.data["topics"]["vehicle_command"] = cmd_topic
    report.data["topics"]["vehicle_command_ack"] = ack_topic

    pub = node.create_publisher(VehicleCommand, cmd_topic, qos_profile_sensor_data)

    accepted, results = send_until_ack(
        node, pub, ack_topic, lambda: make_command(node, args.system_id, 1.0), deadline)
    if not report.check("arm_ack", accepted, results=results):
        report.skip(*names[3:])
        return

    armed = hold_state(
        node, status_topic, VehicleStatus,
        lambda m: m.arming_state == VehicleStatus.ARMING_STATE_ARMED,
        args.hold, deadline.left())
    report.check("armed_hold", armed, n_consecutive=args.hold)

    # armed_hold가 실패해도 시동 끄기는 시도한다. 기체를 시동 상태로 남기지 않기 위함.
    # 끄기 단계에는 남은 예산이 없어도 최소 시간을 준다.
    off_deadline = Deadline(max(deadline.left(), args.disarm_grace))
    accepted, results = send_until_ack(
        node, pub, ack_topic, lambda: make_command(node, args.system_id, 0.0), off_deadline)
    if not report.check("disarm_ack", accepted, results=results):
        report.skip("disarmed_hold")
        return

    disarmed = hold_state(
        node, status_topic, VehicleStatus,
        lambda m: m.arming_state == VehicleStatus.ARMING_STATE_DISARMED,
        args.hold, off_deadline.left())
    report.check("disarmed_hold", disarmed, n_consecutive=args.hold)


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ns", default="",
                   help="PX4 네임스페이스(앞뒤 빗금 없이). 비우면 접두사 없음")
    p.add_argument("--system-id", type=int, required=True,
                   help="기대 vehicle_status.system_id. 인스턴스 N이면 N+1")
    p.add_argument("--timeout", type=float, required=True,
                   help="전체 벽시계 예산(초)")
    p.add_argument("--arm", action="store_true",
                   help="px4-in 시동/시동 끄기 왕복 판정을 추가로 실행")
    p.add_argument("--hold", type=int, default=3,
                   help="상태 유지 판정의 연속 수신 횟수. 기본 3")
    p.add_argument("--disarm-grace", type=float, default=10.0,
                   help="예산이 바닥나도 시동 끄기에 주는 최소 시간(초). 기본 10")
    p.add_argument("--expect-origin", type=float, nargs=3, metavar=("LAT", "LON", "ALT"),
                   default=None,
                   help="px4-out 원점 판정. 기체의 base_link(GNSS 센서) 기대 위치(도, 도, m)로 "
                        "stack.json vehicles[].expect_gps이며 고도에 센서 높이가 들어 있다. "
                        "다대는 기체마다 따로 부른다")
    args = p.parse_args(argv)
    args.ns = args.ns.strip("/")
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = Report(args)
    deadline = Deadline(args.timeout)

    rclpy.init()
    node = rclpy.create_node("idsim_check_px4")
    try:
        status_topic = run_status_checks(node, args, deadline, report)
        if args.expect_origin is not None:
            if status_topic is None:
                report.skip("gps_topic", "gps_origin")
            else:
                run_origin_checks(node, args, deadline, report)
        if args.arm:
            if status_topic is None:
                report.skip("command_topic", "ack_topic", "arm_ack", "armed_hold",
                            "disarm_ack", "disarmed_hold")
            else:
                run_arm_checks(node, args, deadline, report, status_topic)
    except Exception as exc:  # 판정 코드 자체의 오류도 JSON으로 남긴다
        report.check("internal_error", False, error="%s: %s" % (type(exc).__name__, exc))
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

    report.emit()
    return 0 if report.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
