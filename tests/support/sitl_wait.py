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

"""SITL 통합 테스트의 대기와 벽시계 guard(순수 코드. rclpy 없음). docs/interface.md "시간 기준".

판정 시간은 모두 ROS 시각(/clock)이다. 이 모듈의 Waiter는 sim 시각 함수와 벽시계 함수를 받아서
대기마다 다음을 한다.
  - 대기를 시작할 때 /clock이 없으면(sim 시각이 None 또는 0 이하) CLOCK_ABSENT로 즉시 실패한다.
  - sim 시각이 뒤로 가면 CLOCK_BACKWARD로 즉시 실패한다.
  - sim 시각 경과가 timeout_s를 넘으면 TIMEOUT_SIM이다.
  - 벽시계가 wall_cap(= timeout_s x 3 + 10 s)을 넘기면 판정 대신 hang을 끊는다. 그때 /clock이 벽시계
    5 s 동안 진행하지 않았으면 CLOCK_STALLED, 진행은 했으면 CLOCK_SLOW다.
wall_cap은 판정을 느슨하게 하는 용도가 아니다. RTF가 약 0.33 아래로 내려가면 CLOCK_SLOW가 먼저 걸리고,
그때 배수를 올려 통과시키지 않고 architect에게 올린다. 벽시계 sleep은 폴링 간격에만 쓴다.
"""
import time

TIMEOUT_SIM = "TIMEOUT_SIM"
CLOCK_STALLED = "CLOCK_STALLED"
CLOCK_SLOW = "CLOCK_SLOW"
CLOCK_ABSENT = "CLOCK_ABSENT"
# 시각이 뒤로 가는 경우(Gazebo 재시작, /clock 발행자가 둘). 멈춤이나 느림과 원인이 달라 따로 분류한다(docs/interface.md "시간 기준").
CLOCK_BACKWARD = "CLOCK_BACKWARD"
NO_PUBLISHER = "NO_PUBLISHER"
SERVER_ABSENT = "SERVER_ABSENT"
EVENT_MISSING = "EVENT_MISSING"
EVENT_MISMATCH = "EVENT_MISMATCH"
PRECONDITION = "PRECONDITION"
WRONG_RESULT = "WRONG_RESULT"
INFRA_UP = "INFRA_UP"
# 비행 시나리오(tests/sitl/README.md "시나리오와 판정"). 앞 비행 시나리오가 실패해 실행하지 않은 비행 시나리오(실패로 센다)
UPSTREAM_FAILED = "UPSTREAM_FAILED"
# 정답 pose가 있어야 하는 실행에서 정답 pose가 없다 / t_f를 감싸는 정답 표본 간격이 상한을 넘는다
ORACLE_ABSENT = "ORACLE_ABSENT"
ORACLE_STALE = "ORACLE_STALE"
# t_f의 정답 거리가 판정 반경을 넘는다(GOTO는 R_JUDGE, TRACK_ENTITY는 R_JUDGE + v x L)
REACH_MISMATCH = "REACH_MISMATCH"
# TRACK_ENTITY 접근 구간에 표적이 움직이지 않았다(표적 접근 판정이 vacuous)
NO_TARGET_MOTION = "NO_TARGET_MOTION"
# 계약 토픽 발행자의 QoS가 계약 행과 다르다(/targets/*/state)
QOS_MISMATCH = "QOS_MISMATCH"

CATEGORIES = (TIMEOUT_SIM, CLOCK_STALLED, CLOCK_SLOW, CLOCK_ABSENT, CLOCK_BACKWARD, NO_PUBLISHER,
              SERVER_ABSENT, EVENT_MISSING, EVENT_MISMATCH, PRECONDITION, WRONG_RESULT, INFRA_UP,
              UPSTREAM_FAILED, ORACLE_ABSENT, ORACLE_STALE, REACH_MISMATCH, NO_TARGET_MOTION, QOS_MISMATCH)

WALL_CAP_FACTOR = 3.0
WALL_CAP_MARGIN_S = 10.0
STALL_WALL_S = 5.0
POLL_WALL_S = 0.02


class SitlFailure(Exception):
    """분류가 붙은 시나리오 실패. category는 CATEGORIES 중 하나다."""

    def __init__(self, category, message):
        super().__init__("%s: %s" % (category, message))
        self.category = category
        self.message = message


def wall_cap_s(timeout_s):
    """ROS 시각 timeout_s짜리 대기의 벽시계 상한."""
    return timeout_s * WALL_CAP_FACTOR + WALL_CAP_MARGIN_S


def raise_if(findings):
    """(분류, 설명) 목록이 비어 있지 않으면 첫 분류로 SitlFailure를 올린다. 설명은 모두 붙인다."""
    if findings:
        raise SitlFailure(findings[0][0], "; ".join(m for _, m in findings))


class Waiter:
    """sim 시각 기준 대기. sim_s() -> float(초) 또는 None, wall() -> float(초)."""

    def __init__(self, sim_s, wall=time.monotonic, sleep=time.sleep, poll_s=POLL_WALL_S):
        self._sim_s = sim_s
        self._wall = wall
        self._sleep = sleep
        self._poll_s = poll_s
        self.history = []   # (what, sim 경과 s, 벽시계 경과 s). RTF 기록용

    # --- 시각 -------------------------------------------------------

    def now(self):
        """현재 sim 시각(초). /clock이 없으면 CLOCK_ABSENT."""
        t = self._sim_s()
        if t is None or t <= 0:
            raise SitlFailure(CLOCK_ABSENT, "/clock을 받지 못했거나 sim 시각이 0 이하(%r)" % (t,))
        return t

    # --- 대기 -------------------------------------------------------

    def _loop(self, step, timeout_s, what, timeout_ok):
        """step()이 True를 돌려주면 끝난다. 반환: (sim 경과, 벽시계 경과, 시간 안에 끝났는지)."""
        t0 = self.now()
        w0 = self._wall()
        cap = wall_cap_s(timeout_s)
        last = t0
        last_change_wall = w0
        while True:
            if step():
                return self._done(what, t0, w0, True)
            t = self._sim_s()
            w = self._wall()
            if t is not None:
                if t < last:
                    raise SitlFailure(CLOCK_BACKWARD, "%s: sim 시각이 뒤로 갔다(%.3f -> %.3f)" % (what, last, t))
                if t > last:
                    last = t
                    last_change_wall = w
            if last - t0 >= timeout_s:
                if timeout_ok:
                    return self._done(what, t0, w0, False)
                raise SitlFailure(TIMEOUT_SIM, "%s: ROS 시각 %.1f s 안에 조건이 채워지지 않았다" % (what, timeout_s))
            if w - w0 > cap:
                if w - last_change_wall >= STALL_WALL_S:
                    raise SitlFailure(CLOCK_STALLED, "%s: /clock이 벽시계 %.0f s 동안 진행하지 않았다(대기 상한 %.0f s)"
                                      % (what, w - last_change_wall, cap))
                raise SitlFailure(CLOCK_SLOW, "%s: 벽시계 %.0f s가 지났는데 ROS 시각은 %.1f s만 갔다(상한 %.0f s, "
                                  "RTF %.2f). 배수를 올려 통과시키지 않는다" % (what, w - w0, last - t0, cap, (last - t0) / max(w - w0, 1e-9)))
            self._sleep(self._poll_s)

    def _done(self, what, t0, w0, ok):
        t = self._sim_s()
        sim_elapsed = (t if t is not None else t0) - t0
        wall_elapsed = self._wall() - w0
        self.history.append((what, sim_elapsed, wall_elapsed))
        return sim_elapsed, wall_elapsed, ok

    def wait_until(self, pred, timeout_s, what):
        """pred()가 참이 될 때까지 기다린다. ROS 시각 timeout_s 안에 못 채우면 TIMEOUT_SIM.

        반환: 걸린 sim 시간(초).
        """
        sim_elapsed, _, _ = self._loop(lambda: bool(pred()), timeout_s, what, timeout_ok=False)
        return sim_elapsed

    def wait_or_timeout(self, pred, timeout_s, what):
        """wait_until과 같지만 시간 초과를 예외로 올리지 않고 False를 돌려준다(그 뒤 판정은 호출자 몫)."""
        _, _, ok = self._loop(lambda: bool(pred()), timeout_s, what, timeout_ok=True)
        return ok

    def hold_for(self, duration_s, what, check=None):
        """ROS 시각 duration_s 동안 기다린다. check()가 있으면 폴링마다 부르고, 예외는 그대로 올린다."""
        def step():
            if check is not None:
                check()
            return False

        self._loop(step, duration_s, what, timeout_ok=True)

    def rtf(self):
        """지금까지 대기 기록 전체의 (sim 초, 벽시계 초, 비). 대기가 없으면 비는 None."""
        sim = sum(h[1] for h in self.history)
        wall = sum(h[2] for h in self.history)
        return sim, wall, (sim / wall if wall > 0 else None)
