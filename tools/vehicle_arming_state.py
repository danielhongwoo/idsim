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

"""기체 하나의 vehicle_status arming_state 한 표본을 읽어 숫자 한 줄로 쓴다.

tools/sim_stack.sh restart-ops가 runner 컨테이너 안에서 부른다. 네임스페이스는 IDSIM_STACK_FILE(stack.json)의
vehicles[].ns에서, 토픽 이름은 tests/support/px4_topic.py에서 얻는다(토픽 판과 /fmu 문자열을 여기에 쓰지 않는다).

사용법: python3 tools/vehicle_arming_state.py --vehicle N [--timeout 초]
종료 코드: 0 읽었다(stdout에 arming_state), 1 시간 안에 읽지 못했다, 2 인자나 stack.json 오류.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicle", type=int, required=True)
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    stack_file = os.environ.get("IDSIM_STACK_FILE", "")
    try:
        with open(stack_file, encoding="utf-8") as fh:
            vehicles = json.load(fh)["vehicles"]
        ns = next(v["ns"] for v in vehicles if v["id"] == args.vehicle)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print("stack.json에서 기체 %d의 ns를 얻지 못했다(IDSIM_STACK_FILE=%r): %r"
              % (args.vehicle, stack_file, exc), file=sys.stderr)
        return 2

    import rclpy
    from px4_msgs.msg import VehicleStatus

    from tests.support.px4_topic import px4_topic
    from tests.support.receive import receive_once

    topic = px4_topic(ns, "out", "vehicle_status", VehicleStatus)
    rclpy.init()
    node = rclpy.create_node("restart_ops_arming_probe")
    try:
        msg = receive_once(node, topic, VehicleStatus, args.timeout)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    if msg is None:
        print("%s에서 %.0f초 안에 표본을 받지 못했다" % (topic, args.timeout), file=sys.stderr)
        return 1
    print(int(msg.arming_state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
