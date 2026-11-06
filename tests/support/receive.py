"""rclpy 판정 보조. 라이브와 리플레이가 같은 코드를 쓴다.

판정 노드는 전용 스레드 executor에서 spin하고, 호출 스레드는 시계 함수로
타임아웃을 잰다. clock은 초 단위 float를 돌려주는 함수이며 기본은 벽시계다.
/clock 기반 시계는 나중에 주입한다.
"""
import re
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data

_POLL_S = 0.05


class SpinThread:
    """노드를 전용 스레드 executor에서 spin한다. with 문으로 쓴다."""

    def __init__(self, node):
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(node)
        self._node = node
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._executor.shutdown()
        self._thread.join(timeout=5.0)
        self._executor.remove_node(self._node)
        return False


def _wait(pred, timeout_s, clock):
    start = clock()
    while True:
        if pred():
            return True
        if clock() - start >= timeout_s:
            return False
        time.sleep(_POLL_S)


def wait_for_topic(node, regex, timeout_s, clock=time.monotonic):
    """topic list에서 정규식에 맞는 첫 토픽을 찾아 (이름, 타입 목록)을 돌려준다.

    timeout_s 안에 없으면 None. 노드는 이미 spin 중이어도 되고 아니어도 된다.
    """
    pat = re.compile(regex)
    hit = []

    def check():
        for name, types in node.get_topic_names_and_types():
            if pat.search(name):
                hit.append((name, list(types)))
                return True
        return False

    return hit[0] if _wait(check, timeout_s, clock) else None


def receive_once(node, topic, msg_type, timeout_s, qos=qos_profile_sensor_data,
                 clock=time.monotonic):
    """topic에서 메시지 하나를 받아 돌려준다. 시간 안에 못 받으면 None."""
    got = []
    sub = node.create_subscription(msg_type, topic, got.append, qos)
    try:
        with SpinThread(node):
            _wait(lambda: bool(got), timeout_s, clock)
    finally:
        node.destroy_subscription(sub)
    return got[0] if got else None


def hold_state(node, topic, msg_type, predicate, n_consecutive, timeout_s,
               qos=qos_profile_sensor_data, clock=time.monotonic):
    """predicate(msg)가 연속 n_consecutive개 메시지에서 참이면 True.

    거짓 메시지가 나오면 연속 횟수를 0으로 되돌린다. 시간 안에 못 채우면 False.
    """
    state = {"n": 0, "ok": False}
    lock = threading.Lock()

    def cb(msg):
        with lock:
            if state["ok"]:
                return
            state["n"] = state["n"] + 1 if predicate(msg) else 0
            if state["n"] >= n_consecutive:
                state["ok"] = True

    sub = node.create_subscription(msg_type, topic, cb, qos)
    try:
        with SpinThread(node):
            _wait(lambda: state["ok"], timeout_s, clock)
    finally:
        node.destroy_subscription(sub)
    return state["ok"]
