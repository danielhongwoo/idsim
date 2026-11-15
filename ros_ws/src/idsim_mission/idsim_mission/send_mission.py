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
"""send_mission <file> --vehicle <vehicle_id>: 미션 YAML을 ExecuteMission goal로 보내고 결과를 기다린다.

action 이름은 /<vehicle_id>/execute_mission(Mission.ACTION_NAME)이다. 로더(mission_yaml)는 구조만 보고, 계약
검증은 Executor가 한다. feedback과 result를 한 줄씩 출력하고, 종료 코드는 SUCCEEDED이면 0, 로더 오류이면 2,
그 밖(서버 없음, ABORTED, CANCELED, 결과 없음)은 1, 두 번째 Ctrl-C로 끊으면 130이다.
Ctrl-C 한 번은 goal을 취소하고 결과를 기다린다(goal 응답 전이면 응답을 받은 뒤 취소한다). 그러려고
rclpy의 signal handler를 쓰지 않는다(SignalHandlerOptions.NO. 기본 handler는 SIGINT에 context를 내려
취소와 결과를 받을 수 없다). 대신 모든 대기를 POLL_S(0.2 s) 간격으로 끊어 Ctrl-C가 그 안에 처리되게
한다. 서버가 응답하지 않아 대기가 끝나지 않으면 두 번째 Ctrl-C로 끊는다.
use_sim_time은 쓰지 않는다(벽시계는 서버 대기 상한과 Ctrl-C poll에만 쓰고 판정에 쓰지 않는다).
"""

import argparse
import sys

from idsim_mission.mission_yaml import MissionYamlError, load_mission, to_mission_msg

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_FILE = 2
EXIT_INTERRUPTED = 130
# Ctrl-C 응답용 벽시계 poll 간격(s)이고 판정이 아니다. SignalHandlerOptions.NO에서는 SIGINT가 executor의
# wait set을 깨우지 않으므로, 대기를 이 간격으로 끊어 Python에 돌아와야 KeyboardInterrupt를 받는다.
POLL_S = 0.2


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="send_mission", description=__doc__.splitlines()[0])
    parser.add_argument("file", help="mission YAML file")
    parser.add_argument("--vehicle", required=True, help="vehicle_id, e.g. px4_1")
    parser.add_argument("--server-timeout", type=float, default=10.0,
                        help="seconds to wait for the action server (default 10)")
    return parser.parse_args(argv)


def _wait(rclpy, node, future):
    """future가 끝날 때까지 POLL_S 간격으로 spin한다(상한 없음. Ctrl-C는 POLL_S 안에 올라온다)."""
    while not future.done():
        rclpy.spin_until_future_complete(node, future, timeout_sec=POLL_S)
    return future.result()


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        spec = load_mission(args.file)
    except (OSError, MissionYamlError) as e:
        print(f"send_mission: {args.file}: {e}", file=sys.stderr)
        return EXIT_BAD_FILE

    import rclpy
    from action_msgs.msg import GoalStatus
    from idsim_interfaces.action import ExecuteMission
    from idsim_interfaces.msg import Mission
    from rclpy.action import ActionClient
    from rclpy.signals import SignalHandlerOptions

    names = {
        GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
        GoalStatus.STATUS_ABORTED: "ABORTED",
        GoalStatus.STATUS_CANCELED: "CANCELED",
    }
    reasons = {getattr(ExecuteMission.Result, n): n for n in dir(ExecuteMission.Result)
               if n.startswith("REASON_")}

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node("send_mission")
    goal_sent = False
    try:
        action = f"/{args.vehicle}/{Mission.ACTION_NAME}"
        client = ActionClient(node, ExecuteMission, action)
        if not client.wait_for_server(timeout_sec=args.server_timeout):
            print(f"send_mission: action server {action} not ready", file=sys.stderr)
            return EXIT_FAILED
        goal = ExecuteMission.Goal()
        goal.vehicle_id = args.vehicle
        goal.mission = to_mission_msg(spec)

        def on_feedback(fb):
            f = fb.feedback
            dist = f"{f.distance_remaining_m:.2f} m" if f.distance_valid else "-"
            print(f"feedback item {f.item_index}/{f.item_count} type {f.item_type} "
                  f"phase {f.phase} distance {dist}", flush=True)

        print(f"send_mission: {spec.mission_id} ({len(spec.items)} items) -> {action}", flush=True)
        send = client.send_goal_async(goal, feedback_callback=on_feedback)
        goal_sent = True
        interrupted = False
        try:
            _wait(rclpy, node, send)
        except KeyboardInterrupt:
            # goal 응답을 받아야 취소할 수 있다.
            interrupted = True
            print("send_mission: waiting for the goal response to cancel (Ctrl-C again to stop)",
                  file=sys.stderr, flush=True)
            _wait(rclpy, node, send)
        handle = send.result()
        if handle is None or not handle.accepted:
            print("send_mission: goal not accepted", file=sys.stderr)
            return EXIT_FAILED
        result_future = handle.get_result_async()
        if not interrupted:
            try:
                _wait(rclpy, node, result_future)
            except KeyboardInterrupt:
                interrupted = True
        if interrupted:
            print("send_mission: canceling (Ctrl-C again to stop waiting)", file=sys.stderr,
                  flush=True)
            _wait(rclpy, node, handle.cancel_goal_async())
            _wait(rclpy, node, result_future)
        wrapped = result_future.result()
        if wrapped is None:
            print("send_mission: no result received", file=sys.stderr)
            return EXIT_FAILED
        r = wrapped.result
        print(f"result {names.get(wrapped.status, wrapped.status)} reason "
              f"{reasons.get(r.reason, r.reason)} items_completed {r.items_completed} "
              f"last_item_index {r.last_item_index} detail {r.detail!r}", flush=True)
        return EXIT_OK if wrapped.status == GoalStatus.STATUS_SUCCEEDED else EXIT_FAILED
    except KeyboardInterrupt:
        if goal_sent:
            print("send_mission: interrupted; goal state unknown", file=sys.stderr)
        else:
            print("send_mission: interrupted before sending the goal", file=sys.stderr)
        return EXIT_INTERRUPTED
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    sys.exit(main())
