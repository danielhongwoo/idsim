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

"""재실측 (3)의 대역(spoolup, 내부, 경계) 판별과 최종 판정(순수 코드).

ULog 표본으로 첫 ARMED 시각 t_A, rampup 시작 t_ramp, maybe_landed/landed가 false가 된 시각 t_ml/t_lf,
측정기가 처음 보낸 disarm이 처리된 시각 t_p와 그 결과 r_p를 구하고, t_p 기준으로 대역을 정한다. 입출력과 rclpy가
없어 tests/support의 단위 테스트가 SITL 없이 검증한다. crosscheck.py가 쓴다.

정본: decisions.md 쟁점 3 M5 "필수 재실측의 두 경로"와 넘김 목록 px4-engineer 행의 (3). 시간은 모두 PX4
timestamp(us)이고 SITL에서 4 ms 단위로 양자화된다.

정의
  t_A    arm 전송 뒤 첫 arming_state ARMED(2) vehicle_status의 timestamp
  t_ramp t_A 뒤 in_ground_effect가 true인 첫 vehicle_land_detected의 timestamp(없을 수 있다)
  t_ml, t_lf  t_A 뒤 maybe_landed, landed가 false인 첫 vehicle_land_detected의 timestamp
  t_p, r_p    측정기가 처음 보낸 disarm(vehicle_command 400, param1 0, timestamp == 보낸 Px4Timestamp)에 대응하는
              vehicle_command_ack의 timestamp(처리 시각)와 result. 대응은 timestamp의 크기가 아니라 ULog에 기록된
              command 400과 ack 400의 파일 순서(1:1)로 한다. arm과 그 재전송의 ack도 command 400이고 두 ack의
              timestamp가 같을 수 있다. 구간의 command 수와 ack 수가 다르면 대역을 정하지 않는다(ACK_COUNT).
  ld_p   timestamp가 t_p 이하인 마지막 vehicle_land_detected
대역(t_p 기준. 계획한 지연값과 무관)
  spoolup   t_ramp가 없거나 t_ramp > t_p, 그리고 ld_p.landed true
  inner     t_ramp <= t_p, t_p - t_A < T_lf - 0.10 s, ld_p.landed true
  boundary  t_ramp <= t_p 이고 (t_p - t_A >= T_lf - 0.10 s 또는 ld_p.landed false)
verdict(최종)
  PASS               spoolup/inner에서 분기 전환 없이 지상 DISARMED이고 r_p ACCEPTED, 기존 기준 만족.
                     boundary에서도 r_p ACCEPTED이고 분기 전환 없이 지상 DISARMED일 때만.
  M5_CONTRADICTED(1) 첫 disarm이 spoolup/inner에서 처리되었는데 r_p가 ACCEPTED가 아니거나 공중 분기로 간 회.
                     boundary에서 landed false 뒤 landed가 true로 돌아와 지상 DISARMED로 끝난 회(공중 -> 지상 복귀,
                     첫 disarm이 거부된 뒤 재전송이 받아들여진 회 포함). 판별은 ROS(branch_sequence의 A,
                     branch_transitions)와 ULog(t_lf 뒤 DISARMED 전의 landed true 표본) 둘 다.
  M5_INCONSISTENT(1) 첫 disarm의 수락 여부가 maybe_landed와 맞지 않음(일관성 검사. 첫 disarm에 대응한 ack에만).
  M3_CONTRADICTED(1) Hold 뒤 관찰에서 ULog에 landed true가 있음.
  HOLD_END(2)        boundary에서 Hold로 끝남(기계가 통과로 올리지 않는다. architect가 판정).
  WINDOW_MISSED      t_lf가 측정기 취소 전송 /clock 이하(자극이 성립하지 않은 회).
  INCONCLUSIVE(2)    Hold 뒤 관찰의 ULog 표본이 구간을 덮지 못함(HOLD_OBS), maybe_landed만 true(MAYBE_LANDED),
                     측정기가 disarm을 보내지 않음(NO_DISARM), 첫 disarm이 ULog에 없음(FIRST_DISARM_LOST),
                     command와 ack의 수가 다름(ACK_COUNT), 대응하는 ack 없음(NO_ACK), t_ramp 판별 불일치
                     (RAMP_MISMATCH), 대역을 정할 수 없음(BAND_UNKNOWN).
판정 순서(1이 2보다 앞서도록 정한 순서. 앞 단계가 이기고 px4-engineer 승인 대상이다)
  live FAIL(창과 무관한 기준) -> M3_CONTRADICTED -> 관찰 부족과 maybe_landed만 true(INCONCLUSIVE)
  -> WINDOW_MISSED -> 판정 불가(NO_DISARM, FIRST_DISARM_LOST, ACK_COUNT, NO_ACK, RAMP_MISMATCH, BAND_UNKNOWN)
  -> M5_INCONSISTENT -> 대역별 결과.
거부 로그('Disarming denied: not landed')는 판정에 쓰지 않고 유무와 ack와의 시각 차이만 기록한다.
"""
import bisect

from tests.support import measure_judge as mj

US = 1_000_000

# 근거 실행(T_lf를 정한 실행). 같은 image key가 아니면 실행을 거부한다(measure.py).
T_R_S = 1.0                       # COM_SPOOLUP_TIME
T_LF_REF = {
    "run_id": "20261112-011246-k5-measure",
    "image_keys": {"px4": "81678f535f7e4b05", "sim-base": "cd6a22462ff15990"},
    "n": 13,
    "min_s": 1.744,
    "max_s": 1.804,
    "takeoff_alt_m": 5.0,         # TAKEOFF 목표 높이(measure.py --takeoff-alt). 근거 실행과 같아야 한다
    "definition": "ULog vehicle_land_detected landed false timestamp - 첫 ARMED vehicle_status timestamp",
}
BOUNDARY_MARGIN_S = 0.10          # 내부/경계를 가르는 여유: T_lf - 0.10 s
INNER_FRACTIONS = (0.1, 0.3, 0.5, 0.7)
BOUNDARY_OFFSETS_S = (0.10, 0.05, 0.02)
SPOOLUP_DELAYS_S = (0.0, 0.5)
REPEATS = 3                       # 지연값마다 시도 수

# 실행 전에 고정한 (3)의 지연값(이 호스트). T_lf 최솟값 1.744 s에서 plan_item3_delays가 낸 값과 같다.
ITEM3_DELAYS_S = (0.0, 0.5, 1.074, 1.223, 1.372, 1.521, 1.644, 1.694, 1.724)

BAND_SPOOLUP = "spoolup"
BAND_INNER = "inner"
BAND_BOUNDARY = "boundary"
BANDS = (BAND_SPOOLUP, BAND_INNER, BAND_BOUNDARY)
MIN_VALID_BY_BAND = {BAND_SPOOLUP: 6, BAND_INNER: 10, BAND_BOUNDARY: 4}
MIN_VALID_PER_DELAY = 2           # spoolup과 inner만. 계획한 지연값마다

# 교차 확인 기준
RAMP_VS_TAKEOFF_US = 8_000        # takeoff_state 4와 t_ramp의 차이 상한
THRUST_FLOOR_S = 0.9              # 추력 바닥 중앙값을 구하는 구간(arm 뒤)
THRUST_MARGIN = 0.002
THRUST_BEFORE_US = 20_000         # 추력 하락 표본이 t_ramp 앞 20 ms 뒤 40 ms 안
THRUST_AFTER_US = 40_000
TAKEOFF_STATE_RAMPUP = 4

# Hold 뒤 관찰의 ULog 표본이 구간을 덮었는가(px4-engineer 승인 대상). vehicle_land_detected는 값이 바뀔 때와
# 미변경 시 1 Hz로 남는다(근거 실행: 60 s에 60-61개). 이웃 표본 사이(구간 앞 마지막 표본과 구간 끝 포함)의 최대
# 간격이 2 s(1 Hz 주기의 두 배)를 넘으면 덮지 못한 것이다. 표본이 하나도 없어도 덮지 못한 것이다.
HOLD_OBS_MAX_GAP_US = 2_000_000
# 마지막 command ack를 구간 끝(ros_end) 뒤로 얼마나 더 찾는가(끝 직전에 보낸 명령의 ack용)
ACK_SLACK_US = 500_000

# 일관성 검사
ACCEPT_AFTER_ML_US = 12_000       # ACCEPTED면 t_p <= t_ml + 12 ms
DENIED_LOG_NEAR_US = 4_000        # 거부 로그가 [t_p - 4 ms, t_p] 안인가(기록만 하고 판정에 쓰지 않는다)
RESULT_ACCEPTED = 0
RESULT_TEMP_REJECTED = 1
LOG_DENIED = "Disarming denied: not landed"
LOG_DISARMED = "Disarmed by external command"
LOG_ARMED = "Armed by external command"

ARMING_STATE_ARMED = 2
ARMING_STATE_DISARMED = 1
CMD_ARM_DISARM = 400


def plan_item3_delays(t_lf_min_s, t_r_s=T_R_S):
    """T_lf 최솟값에서 (3)의 지연 목록을 계산한다(ms 단위로 반올림). image key가 바뀌어 T_lf를 다시 정했을 때 쓴다.

    spoolup 0, 0.5 s / 내부 T_r + {0.1, 0.3, 0.5, 0.7} x (T_lf - T_r) / 경계 T_lf - {0.10, 0.05, 0.02} s.
    """
    inner = [round(t_r_s + f * (t_lf_min_s - t_r_s), 3) for f in INNER_FRACTIONS]
    edge = [round(t_lf_min_s - o, 3) for o in BOUNDARY_OFFSETS_S]
    return list(SPOOLUP_DELAYS_S) + inner + edge


def planned_band(delay_s):
    """계획한 지연값이 속한 대역(계획 기준. 실제 대역은 ULog의 t_p로 정한다)."""
    if delay_s in SPOOLUP_DELAYS_S:
        return BAND_SPOOLUP
    if delay_s >= ITEM3_DELAYS_S[-3]:
        return BAND_BOUNDARY
    return BAND_INNER


def parse_item3_delays(text):
    """--item3-delays 인자를 검증해 목록으로 돌려준다. 고정 목록의 값 아홉 개 전부를 중복 없이(순서는 자유) 받는다.

    ValueError에 사유를 담는다. 부분 목록은 받지 않는다(일부 지연값만의 실행은 받지 않는다). (3)은
    DELAY_RANGE_S(0-0.2 s, (5) 전용)를 쓰지 않고 이 고정 목록만 받는다.
    """
    try:
        vals = [float(x) for x in text.split(",")]
    except ValueError:
        raise ValueError("--item3-delays는 쉼표로 구분한 숫자여야 한다: %r" % text)
    bad = [v for v in vals if v not in ITEM3_DELAYS_S]
    if bad:
        raise ValueError("--item3-delays는 고정 목록 %s의 값만 받는다: 목록에 없음 %s"
                         % (list(ITEM3_DELAYS_S), bad))
    if len(set(vals)) != len(vals):
        raise ValueError("--item3-delays에 중복이 있다: %s" % vals)
    if set(vals) != set(ITEM3_DELAYS_S):
        raise ValueError("--item3-delays는 고정 목록 아홉 개를 모두 포함해야 한다(부분 목록은 받지 않는다): 빠진 값 %s"
                         % [v for v in ITEM3_DELAYS_S if v not in vals])
    return vals


def image_key_problem(image_keys, takeoff_alt_m=None):
    """근거 실행과 image key와 TAKEOFF 목표 높이가 같은가. 다르면 사유 문장, 같으면 None.

    비교하는 것은 PX4 동작을 정하는 px4와 sim-base의 key다(ros-ws는 보지 않는다. T_lf는 PX4 timestamp 사이의
    간격이라 PX4와 Gazebo로 정해진다). image_keys는 tools/ci/image_keys.py의 json 목록([{"image": 이름,
    "key": ...}]) 또는 None. takeoff_alt_m이 None이 아니면 근거 실행의 목표 높이와도 비교한다.
    """
    if not image_keys:
        return "image key가 없다(IDSIM_IMAGE_KEYS 없음). T_lf의 근거 실행과 같은 key인지 확인할 수 없다"
    have = {e["image"]: e["key"] for e in image_keys}
    diff = ["%s: 이 실행 %s, 근거 실행 %s" % (k, have.get(k), v)
            for k, v in sorted(T_LF_REF["image_keys"].items()) if have.get(k) != v]
    if takeoff_alt_m is not None and takeoff_alt_m != T_LF_REF["takeoff_alt_m"]:
        diff.append("TAKEOFF 목표 높이: 이 실행 %s m, 근거 실행 %s m" % (takeoff_alt_m, T_LF_REF["takeoff_alt_m"]))
    if diff:
        return ("image key 또는 TAKEOFF 목표 높이가 T_lf의 근거 실행(%s)과 다르다(%s). 같은 조건에서 armed item을 먼저 "
                "돌려 T_lf를 다시 정하고(crosscheck가 T_lf 표본과 계산한 지연 목록을 출력한다) measure_bands.py의 "
                "T_LF_REF와 ITEM3_DELAYS_S를 고친 뒤 실행한다. 고친 뒤에는 커밋하고 돌린다(dirty=true인 실행은 "
                "머지 조건으로 세지 않는다)" % (T_LF_REF["run_id"], "; ".join(diff)))
    return None


# ---------------------------------------------------------------------------
# ULog 표본 묶음


def _sorted_rows(rows):
    out = sorted(rows, key=lambda r: int(r["timestamp"]))
    return out, [int(r["timestamp"]) for r in out]


class UlogData:
    """read_topics 결과와 logged message를 timestamp로 찾을 수 있게 정렬해 둔 묶음.

    topics: {토픽: 행 목록}. 없는 토픽은 빈 목록이다. logged: ulog_min.read_logged의 결과.
    """

    NAMES = ("vehicle_status", "vehicle_land_detected", "vehicle_command_ack", "vehicle_command",
             "vehicle_thrust_setpoint", "takeoff_status", "actuator_armed", "vehicle_local_position")

    def __init__(self, topics, logged=()):
        self.rows = {}
        self.keys = {}
        for n in self.NAMES:
            self.rows[n], self.keys[n] = _sorted_rows(topics.get(n, []))
        self.logged = list(logged)
        # command 400과 ack 400의 대응은 파일 순서로 한다(timestamp 정렬이 아니다)
        self.cmd_file = list(topics.get("vehicle_command", []))
        self.ack_file = list(topics.get("vehicle_command_ack", []))

    def between(self, name, lo, hi, lo_incl=False, hi_incl=True):
        """name 토픽에서 timestamp가 (lo, hi]인 행(경계 포함 여부는 인자)."""
        k = self.keys[name]
        i = bisect.bisect_left(k, lo) if lo_incl else bisect.bisect_right(k, lo)
        j = bisect.bisect_right(k, hi) if hi_incl else bisect.bisect_left(k, hi)
        return self.rows[name][i:j]

    def last_at_or_before(self, name, t):
        k = self.keys[name]
        i = bisect.bisect_right(k, t)
        return self.rows[name][i - 1] if i else None


def t_lf_samples(ud):
    """ULog 전체의 T_lf 표본(초): 첫 ARMED vehicle_status 뒤 landed가 false가 된 첫 land_detected까지의 시간.

    arm 사건마다 하나이고, 그 arm이 DISARMED가 되거나 다음 arm이 오기 전에 landed false가 없으면 뺀다.
    T_lf를 정하거나 다시 정할 때(image key가 바뀐 경우) 쓴다.
    """
    vs = ud.rows["vehicle_status"]
    arms = []
    prev = None
    for v in vs:
        st = int(v["arming_state"])
        if st == ARMING_STATE_ARMED and prev != ARMING_STATE_ARMED:
            arms.append(int(v["timestamp"]))
        prev = st
    out = []
    for i, ta in enumerate(arms):
        nxt = arms[i + 1] if i + 1 < len(arms) else None
        dis = next((int(v["timestamp"]) for v in vs
                    if int(v["timestamp"]) > ta and int(v["arming_state"]) == ARMING_STATE_DISARMED), None)
        end = min(x for x in (nxt, dis) if x is not None) if (nxt or dis) else None
        for ld in ud.rows["vehicle_land_detected"]:
            t = int(ld["timestamp"])
            if t <= ta:
                continue
            if end is not None and t > end:
                break
            if not ld["landed"]:
                out.append((t - ta) / US)
                break
    return out


# ---------------------------------------------------------------------------
# 한 시도의 분석


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def thrust_drop(ud, t_a, hi):
    """추력 z가 'arm 뒤 0.9 s 바닥 중앙값 - 0.002' 아래로 내려간 첫 표본. (바닥, 표본 timestamp, 표본 수)."""
    rows = ud.between("vehicle_thrust_setpoint", t_a, hi)
    if not rows:
        return None, None, 0
    floor = _median([r["xyz"][2] for r in rows if int(r["timestamp"]) <= t_a + int(THRUST_FLOOR_S * US)])
    if floor is None:
        return None, None, len(rows)
    thr = floor - THRUST_MARGIN
    for r in rows:
        if r["xyz"][2] < thr:
            return floor, int(r["timestamp"]), len(rows)
    return floor, None, len(rows)


def ramp_check(t_ramp, t_p, takeoff4_ts, drop_ts, thrust_samples):
    """t_ramp 판별의 교차 확인. 사유 목록(빈 목록이면 일치).

    takeoff_state 4 표본이 있으면 t_ramp와 8 ms 안. 추력 하락 첫 표본은 t_ramp가 있으면
    [t_ramp - 20 ms, t_ramp + 40 ms] 안이고, t_ramp가 없는데 t_p 이전에 하락이 있으면 어긋난 것이다.
    takeoff_status는 1 s 간격이라 빠질 수 있어 없으면 확인하지 않는다. 추력 표본이 하나도 없으면 확인하지
    못한 것으로 기록만 한다(어긋남이 아니다).
    """
    problems = []
    if takeoff4_ts is not None:
        if t_ramp is None:
            problems.append("takeoff_state 4 표본이 있는데 in_ground_effect true가 없음")
        elif abs(takeoff4_ts - t_ramp) > RAMP_VS_TAKEOFF_US:
            problems.append("takeoff_state 4와 t_ramp 차이 %.1f ms > %.0f ms"
                            % ((takeoff4_ts - t_ramp) / 1000.0, RAMP_VS_TAKEOFF_US / 1000.0))
    if thrust_samples:
        if t_ramp is not None:
            if drop_ts is None:
                problems.append("t_ramp가 있는데 추력 하락 표본이 없음")
            elif not (t_ramp - THRUST_BEFORE_US <= drop_ts <= t_ramp + THRUST_AFTER_US):
                problems.append("추력 하락 표본이 t_ramp에서 %.1f ms (기준 -%.0f..+%.0f ms)"
                                % ((drop_ts - t_ramp) / 1000.0, THRUST_BEFORE_US / 1000.0,
                                   THRUST_AFTER_US / 1000.0))
        elif drop_ts is not None and t_p is not None and drop_ts <= t_p:
            problems.append("t_p 이전에 추력 하락이 있는데 in_ground_effect true가 없음")
    return problems


def consistency(r_p, t_p, t_ml):
    """첫 disarm의 수락 여부와 maybe_landed의 일관성. 사유 목록(빈 목록이면 일치).

    첫 disarm에 대응한 ack에만 적용한다(t_p가 없으면 부르지 않는다).
    ACCEPTED면 t_p <= t_ml + 12 ms. TEMPORARILY_REJECTED면 t_p >= t_ml. t_ml이 없으면(maybe_landed가 false가
    된 적 없음) ACCEPTED는 조건이 성립하고 REJECTED는 어긋난다. 그 밖의 result는 이 검사 대상이 아니다.
    거부 때의 logged message는 판정에 쓰지 않는다(analyze_row가 유무와 시각 차이만 기록한다).
    """
    problems = []
    if r_p == RESULT_ACCEPTED:
        if t_ml is not None and t_p > t_ml + ACCEPT_AFTER_ML_US:
            problems.append("ACCEPTED인데 t_p가 t_ml보다 %.1f ms 뒤 (기준 %.0f ms 이내)"
                            % ((t_p - t_ml) / 1000.0, ACCEPT_AFTER_ML_US / 1000.0))
    elif r_p == RESULT_TEMP_REJECTED:
        if t_ml is None or t_p < t_ml:
            problems.append("TEMPORARILY_REJECTED인데 t_p가 t_ml보다 앞(또는 t_ml 없음)")
    return problems


def hold_observation(ud, start, end):
    """Hold 뒤 관찰 구간 (start, end]의 ULog 전체 표본에서 landed true와 maybe_landed true를 센다.

    covered는 ULog 표본이 구간을 덮었는가다: 표본이 있고, 구간 앞의 마지막 표본(없으면 start)부터 구간 안 표본들과
    end까지 이웃 사이 최대 간격이 HOLD_OBS_MAX_GAP_US 이하.
    """
    rows = ud.between("vehicle_land_detected", start, end)
    prev = ud.last_at_or_before("vehicle_land_detected", start)
    times = [int(prev["timestamp"]) if prev is not None else start] + [int(r["timestamp"]) for r in rows] + [end]
    gap = max(b - a for a, b in zip(times, times[1:]))
    landed = [int(r["timestamp"]) for r in rows if r["landed"]]
    maybe = [int(r["timestamp"]) for r in rows if r["maybe_landed"] and not r["landed"]]
    return {"samples": len(rows), "max_gap_s": gap / US, "covered": bool(rows) and gap <= HOLD_OBS_MAX_GAP_US,
            "landed_true": len(landed), "maybe_landed_true_only": len(maybe),
            "first_landed_true_ts": landed[0] if landed else None,
            "first_maybe_landed_ts": maybe[0] if maybe else None}


def classify_band(t_a, t_ramp, t_p, ld_p, t_lf_ref_s=None):
    """t_p 기준 대역. (대역 또는 None, t_lf_below_ref 표시). ld_p가 없으면 대역을 정할 수 없다(None)."""
    ref = T_LF_REF["min_s"] if t_lf_ref_s is None else t_lf_ref_s
    if ld_p is None:
        return None, False
    landed = bool(ld_p["landed"])
    ramp_started = t_ramp is not None and t_ramp <= t_p
    if not ramp_started:
        return (BAND_SPOOLUP, False) if landed else (None, False)
    in_inner_time = (t_p - t_a) < int(round((ref - BOUNDARY_MARGIN_S) * US))
    if in_inner_time and landed:
        return BAND_INNER, False
    return BAND_BOUNDARY, bool(in_inner_time and not landed)


def _s(a, b):
    return None if a is None or b is None else (a - b) / US


def match_first_disarm(ud, arm_ts, hi, fd):
    """구간의 command 400과 ack 400을 파일 순서로 1:1 대응해 첫 disarm의 ack를 찾는다.

    fd: 측정기가 처음 보낸 disarm의 [recv_ros_us, Px4Timestamp] 또는 None.
    돌려주는 dict: n_cmd, n_ack, index(첫 disarm의 command 순번 또는 None), ack(대응한 ack 행 또는 None).
    command와 ack의 수가 다르면 ack는 None이다(대응을 믿을 수 없다).
    """
    cmds = [c for c in ud.cmd_file if int(c["command"]) == CMD_ARM_DISARM and arm_ts <= int(c["timestamp"]) <= hi]
    acks = [a for a in ud.ack_file
            if int(a["command"]) == CMD_ARM_DISARM and arm_ts <= int(a["timestamp"]) <= hi + ACK_SLACK_US]
    k = None
    if fd is not None:
        for i, c in enumerate(cmds):
            if int(c["timestamp"]) == fd[1] and float(c["param1"]) == 0.0:
                k = i
                break
    ack = acks[k] if (k is not None and len(cmds) == len(acks)) else None
    return {"n_cmd": len(cmds), "n_ack": len(acks), "index": k, "ack": ack, "acks": acks}


def analyze_row(row, ud, t_lf_ref_s=None):
    """(3)의 한 시도 행을 ULog로 분석한다. JSON으로 쓸 수 있는 dict를 돌려준다.

    row: measure_item3.jsonl의 행(facts.arm_send, facts.first_disarm_send, ros_end_us 필요).
    ud: UlogData. 오류가 있으면 {"error": 사유}.
    """
    f = row["facts"]
    arm_ts = f["arm_send"][1]
    hi = row["ros_end_us"]
    a = {"arm_ts": arm_ts, "window_hi": hi}
    t_a_row = next((r for r in ud.between("vehicle_status", arm_ts, hi)
                    if int(r["arming_state"]) == ARMING_STATE_ARMED), None)
    if t_a_row is None:
        a["error"] = "arm 전송 뒤 ARMED vehicle_status가 ULog에 없음"
        return a
    t_a = int(t_a_row["timestamp"])
    a["t_A"] = t_a
    ld = ud.between("vehicle_land_detected", t_a, hi)
    t_ramp = next((int(r["timestamp"]) for r in ld if r["in_ground_effect"]), None)
    t_ml = next((int(r["timestamp"]) for r in ld if not r["maybe_landed"]), None)
    t_lf = next((int(r["timestamp"]) for r in ld if not r["landed"]), None)
    t_dis = next((int(r["timestamp"]) for r in ud.between("vehicle_status", t_a, hi)
                  if int(r["arming_state"]) == ARMING_STATE_DISARMED), None)
    # landed가 false가 된 뒤 DISARMED 전에 true로 돌아온 표본(공중 -> 지상 복귀)
    returned = t_lf is not None and any(
        r["landed"] and int(r["timestamp"]) > t_lf and (t_dis is None or int(r["timestamp"]) < t_dis) for r in ld)
    fd = f.get("first_disarm_send")
    m = match_first_disarm(ud, arm_ts, hi, fd)
    a["first_disarm_sent"] = fd is not None
    a["first_disarm_lost"] = fd is not None and m["index"] is None
    a["n_cmd400"] = m["n_cmd"]
    a["n_ack400"] = m["n_ack"]
    a["ack_count_mismatch"] = m["n_cmd"] != m["n_ack"]
    a["first_disarm_index"] = m["index"]
    ack_p = m["ack"]
    t_p = None if ack_p is None else int(ack_p["timestamp"])
    r_p = None if ack_p is None else int(ack_p["result"])
    ld_p = None if t_p is None else ud.last_at_or_before("vehicle_land_detected", t_p)
    band, below = (None, False) if t_p is None else classify_band(t_a, t_ramp, t_p, ld_p, t_lf_ref_s)
    tk4 = next((int(r["timestamp"]) for r in ud.between("takeoff_status", t_a, hi, lo_incl=True)
                if int(r["takeoff_state"]) == TAKEOFF_STATE_RAMPUP), None)
    floor, drop_ts, n_thrust = thrust_drop(ud, t_a, hi)
    th_p = None if t_p is None else ud.last_at_or_before("vehicle_thrust_setpoint", t_p)
    denied = [mm["ts"] for mm in ud.logged if LOG_DENIED in mm["msg"]]
    disarmed_log = [mm["ts"] for mm in ud.logged if LOG_DISARMED in mm["msg"]]
    near = [t_p - x for x in denied if t_p is not None and abs(t_p - x) <= 100_000]
    cons = [] if t_p is None else consistency(r_p, t_p, t_ml)
    ramp_problems = ramp_check(t_ramp, t_p, tk4, drop_ts, n_thrust)
    aa = [r for r in ud.between("actuator_armed", arm_ts, hi) if r["armed"]]
    lp = ud.between("vehicle_local_position", t_a, t_p if t_p is not None else hi, lo_incl=True)
    a.update({
        "t_ramp": t_ramp, "t_ml": t_ml, "t_lf": t_lf, "t_p": t_p, "r_p": r_p, "t_disarmed": t_dis,
        "ulog_landed_returned": bool(returned),
        "ld_p": None if ld_p is None else {k: bool(ld_p[k]) for k in (
            "landed", "maybe_landed", "ground_contact", "in_ground_effect")},
        "band": band, "t_lf_below_ref": below,
        "t_lf_ref_s": T_LF_REF["min_s"] if t_lf_ref_s is None else t_lf_ref_s,
        "tp_minus_tA_s": _s(t_p, t_a), "tramp_minus_tA_s": _s(t_ramp, t_a),
        "tlf_minus_tA_s": _s(t_lf, t_a), "tml_minus_tA_s": _s(t_ml, t_a),
        "tp_minus_tlf_s": _s(t_p, t_lf), "tp_minus_tml_s": _s(t_p, t_ml),
        "ack400_in_file_order": [[int(r["timestamp"]) - t_a, int(r["result"])] for r in m["acks"]],
        "tp_not_before_ml": None if t_p is None or t_ml is None else t_p >= t_ml,
        "log_denied_near_tp": bool(near) and any(0 <= d <= DENIED_LOG_NEAR_US for d in near),
        "log_denied_dt_us": min(near, key=abs) if near else None,       # t_p - 로그 ts. 기록만 한다
        "log_disarmed_near_tp": t_p is not None and any(
            t_p - DENIED_LOG_NEAR_US <= x <= t_p + DENIED_LOG_NEAR_US for x in disarmed_log),
        "thrust_at_tp": None if th_p is None else float(th_p["xyz"][2]),
        "thrust_floor": floor, "thrust_drop_ts": drop_ts, "thrust_samples": n_thrust,
        "takeoff4_ts": tk4,
        "ramp_evidence": {"in_ground_effect_t_ramp_minus_tA_s": _s(t_ramp, t_a),
                          "takeoff_state4_minus_tA_s": _s(tk4, t_a),
                          "thrust_drop_minus_tA_s": _s(drop_ts, t_a)},
        "actuator_armed_minus_tA_s": _s(int(aa[0]["timestamp"]) if aa else None, t_a),
        "z_at_tp_m": None if not lp else float(lp[-1]["z"]),
        "z_min_to_tp_m": None if not lp else float(min(r["z"] for r in lp)),
        "consistency_problems": cons, "ramp_problems": ramp_problems,
    })
    # 창 밖: t_lf가 측정기 취소 전송 /clock 이하
    cancel = (row.get("injection") or {}).get("cancel_clock_us")
    if cancel is None and fd is not None:
        cancel = fd[1]
    a["cancel_clock_us"] = cancel
    a["window_missed"] = bool(t_lf is not None and cancel is not None and t_lf <= cancel)
    # Hold 뒤 관찰
    if f.get("end_reason") == "HOLD" and f.get("hold_observe_span_s") is not None:
        start = f["cleanup_end_ros_us"]
        a["hold_obs"] = hold_observation(ud, start, start + int(f["hold_observe_span_s"] * US))
    return a


# ---------------------------------------------------------------------------
# 최종 판정


def hold_landed_true(hold_obs):
    """Hold 뒤 관찰의 ULog 전체 표본에 landed true가 있으면 사유 문장, 없으면 None. (M3_CONTRADICTED, 1)"""
    if hold_obs is not None and hold_obs["landed_true"]:
        return "Hold 뒤 관찰의 ULog에 landed true %d개(처음 %s)" % (
            hold_obs["landed_true"], hold_obs["first_landed_true_ts"])
    return None


def hold_insufficient(hold_obs):
    """Hold 뒤 관찰을 판정할 수 없으면 (kind, 사유), 아니면 None. (INCONCLUSIVE, 2)

    ULog 표본이 관찰 구간을 덮지 못함(0개 포함, HOLD_OBS)이거나 maybe_landed만 true(MAYBE_LANDED. 기록만 하고
    기계가 판정하지 않는다).
    """
    if hold_obs is None:
        return "HOLD_OBS", "Hold 뒤 관찰 구간의 정보가 없어 ULog 표본이 구간을 덮었는지 알 수 없음"
    if not hold_obs["covered"]:
        return "HOLD_OBS", ("Hold 뒤 관찰의 ULog vehicle_land_detected 표본이 구간을 덮지 못함(표본 %d개, 이웃 최대 간격 "
                            "%.2f s > %.1f s)" % (hold_obs["samples"], hold_obs["max_gap_s"],
                                                 HOLD_OBS_MAX_GAP_US / US))
    if hold_obs["maybe_landed_true_only"]:
        return "MAYBE_LANDED", ("Hold 뒤 관찰의 ULog에 maybe_landed만 true인 표본 %d개(landed true 없음). 기록하고 "
                                "기계가 판정하지 않는다" % hold_obs["maybe_landed_true_only"])
    return None


def _ramp_text(an):
    e = an["ramp_evidence"]

    def v(x):
        return "없음" if x is None else "%.3f s" % x
    return "in_ground_effect %s, takeoff_state 4 %s, 추력 하락 %s (모두 t_A 기준)" % (
        v(e["in_ground_effect_t_ramp_minus_tA_s"]), v(e["takeoff_state4_minus_tA_s"]),
        v(e["thrust_drop_minus_tA_s"]))


def final_verdict_item3(row, an):
    """(3)의 한 시도의 최종 verdict. (verdict, 사유 목록, kind).

    live verdict(row["verdict"])는 ROS 표본으로 정한 것이고 대역은 ULog만 안다. 판정 순서(앞 단계가 이긴다):
      1 live FAIL(창과 무관한 기준)  2 M3_CONTRADICTED(Hold 뒤 관찰의 ULog landed true)
      3 관찰 부족과 maybe_landed만 true(INCONCLUSIVE)  4 WINDOW_MISSED
      5 판정 불가(NO_DISARM, FIRST_DISARM_LOST, ACK_COUNT, NO_ACK, RAMP_MISMATCH, BAND_UNKNOWN: INCONCLUSIVE)
      6 M5_INCONSISTENT  7 대역별 결과
    live가 PASS, HOLD_END, WINDOW_MISSED가 아니면(INCONCLUSIVE 등) 2만 ULog로 보고 live를 유지한다.
    live WINDOW_MISSED는 창과 무관한 기준을 모두 만족한 회이므로 끝난 방식(PASS 또는 HOLD_END)으로 되돌려
    ULog의 창 판정으로 다시 정한다(ROS 도착이 늦을 수 있어 landed 시점은 ULog가 정본이다).
    """
    live = row["verdict"]
    f = row["facts"]
    if live == "FAIL":
        return "FAIL", list(row["reasons"]), ""
    if "error" in an:
        return "INCONCLUSIVE", [an["error"]], "ULOG"
    hold = f.get("end_reason") == "HOLD"
    base = live
    if live == "WINDOW_MISSED":
        base = "HOLD_END" if hold else "PASS"
    why = hold_landed_true(an.get("hold_obs")) if hold else None
    if why is not None and base in ("PASS", "HOLD_END", "INCONCLUSIVE"):
        return "M3_CONTRADICTED", [why], ""
    if base not in ("PASS", "HOLD_END"):
        return live, list(row["reasons"]), row.get("inconclusive_kind", "")
    if hold:
        ins = hold_insufficient(an.get("hold_obs"))
        if ins is not None:
            return "INCONCLUSIVE", [ins[1]], ins[0]
    if an["window_missed"]:
        return "WINDOW_MISSED", ["t_lf %.3f s <= 취소 전송 /clock (t_A 기준 %.3f s). 창 밖" % (
            an["tlf_minus_tA_s"], (an["cancel_clock_us"] - an["t_A"]) / US)], ""
    if not an["first_disarm_sent"]:
        return "INCONCLUSIVE", ["측정기가 disarm을 보내지 않았다(첫 분기가 공중). 대역을 정할 수 없음"], "NO_DISARM"
    if an["first_disarm_lost"]:
        return "INCONCLUSIVE", ["first_disarm_lost: 측정기가 처음 보낸 disarm(param1 0)이 ULog vehicle_command에 없음"], \
            "FIRST_DISARM_LOST"
    if an["ack_count_mismatch"]:
        return "INCONCLUSIVE", ["구간의 command 400 %d개와 ack 400 %d개의 수가 다름. 순번 대응을 믿을 수 없음"
                                % (an["n_cmd400"], an["n_ack400"])], "ACK_COUNT"
    if an["t_p"] is None:
        return "INCONCLUSIVE", ["첫 disarm에 대응하는 ack가 ULog에 없음"], "NO_ACK"
    if an["ramp_problems"]:
        return "INCONCLUSIVE", ["t_ramp 판별 불일치: " + "; ".join(an["ramp_problems"]) + ". " + _ramp_text(an)], \
            "RAMP_MISMATCH"
    band = an["band"]
    if band is None:
        return "INCONCLUSIVE", ["대역을 정할 수 없음(ld_p 없음, 또는 rampup 전인데 landed false)"], "BAND_UNKNOWN"
    if an["consistency_problems"]:
        return "M5_INCONSISTENT", list(an["consistency_problems"]), ""
    ros_aerial = "A" in (f.get("branch_sequence") or "") or bool(f.get("branch_transitions", 0))
    aerial = ros_aerial or an["ulog_landed_returned"]
    accepted = an["r_p"] == RESULT_ACCEPTED
    if band in (BAND_SPOOLUP, BAND_INNER) or base == "PASS":
        # spoolup, 내부, 그리고 지상 DISARMED로 끝난 경계: 받아들여져 분기 전환 없이 끝나야 한다
        why = []
        if base == "HOLD_END":
            why.append("첫 disarm이 %s 대역에서 처리되었는데 Hold로 끝남" % band)
        if not accepted:
            why.append("첫 disarm이 %s 대역에서 처리되었는데 r_p=%s (ACCEPTED 아님)" % (band, an["r_p"]))
        if aerial:
            why.append("%s 대역에서 공중 분기를 거침(ROS 분기 순서 %s, 전환 %s회, ULog landed 복귀 %s)" % (
                band, f.get("branch_sequence"), f.get("branch_transitions"), an["ulog_landed_returned"]))
        if why:
            return "M5_CONTRADICTED", why, ""
        return "PASS", [], ""
    # 경계에서 Hold로 끝남
    if an["r_p"] not in (RESULT_ACCEPTED, RESULT_TEMP_REJECTED):
        return "INCONCLUSIVE", ["경계에서 r_p=%s (ACCEPTED, TEMPORARILY_REJECTED가 아님)" % an["r_p"]], "R_P_UNEXPECTED"
    return "HOLD_END", ["경계 대역에서 Hold로 끝남. 기계가 통과로 올리지 않는다(architect가 선후 기록으로 판정)"], ""


def final_verdict_2b(row, hold_obs):
    """(2)의 2b 최종 verdict(ULog 전체 표본 기준). live가 COND_NOT_REACHED일 때만 바뀐다: landed true가 ULog에
    있으면 M3_CONTRADICTED(1), ULog 표본이 관찰 구간을 덮지 못하면 INCONCLUSIVE(HOLD_OBS), maybe_landed만
    true이면 INCONCLUSIVE(MAYBE_LANDED). 그 밖은 live를 유지한다."""
    if row["verdict"] != "COND_NOT_REACHED":
        return row["verdict"], list(row["reasons"]), row.get("inconclusive_kind", "")
    why = hold_landed_true(hold_obs)
    if why is not None:
        return "M3_CONTRADICTED", [why], ""
    ins = hold_insufficient(hold_obs)
    if ins is not None:
        return "INCONCLUSIVE", [ins[1]], ins[0]
    return row["verdict"], list(row["reasons"]), ""


# ---------------------------------------------------------------------------
# 집계

VALID = ("PASS", "FAIL", "M3_CONTRADICTED", "M5_CONTRADICTED", "M5_INCONSISTENT")
EXCLUDED = ("WINDOW_MISSED",)


def _is_valid(verdict, band):
    return verdict in VALID or (verdict == "HOLD_END" and band == BAND_BOUNDARY)


def band_summary(rows, finals, analyses):
    """(3)의 대역별 집계. rows: item 3 행. finals: {(item, attempt): 최종 verdict}.
    analyses: {attempt: analyze_row 결과}.

    실제 대역(ULog t_p)별로 n, 유효(VALID와 경계의 HOLD_END), PASS, exit1(기준과 다른 관측), 제외(WINDOW_MISSED),
    공중 분기 회수(ROS 분기 순서에 A, 전환, 또는 ULog landed 복귀), 계획 지연값별 같은 수를 낸다. 최소치(spoolup 6,
    inner 10, boundary 4. spoolup과 inner는 계획한 지연값마다 그 대역의 유효 시도 2)를 채웠는지는 met로 둔다.
    대역을 정하지 못한 행은 unclassified에 센다. all_met는 세 대역의 최소치만 본다(PASS가 아닌 행은 따로 센다).
    """
    def blank():
        return {"n": 0, "valid": 0, "pass": 0, "exit1": 0, "excluded": 0, "aerial": 0, "hold_end": 0}

    by_band = {b: dict(blank(), by_delay={}) for b in BANDS}
    unclassified = blank()
    plan_ok = {}       # 계획 지연값 -> 계획 대역의 유효 시도 수
    for r in rows:
        v = finals.get((r["item"], r["attempt"]), r["verdict"])
        an = analyses.get(r["attempt"]) or {}
        band = an.get("band")
        delay = (r.get("injection") or {}).get("delay_s_nominal")
        facts = r.get("facts") or {}
        aerial = ("A" in (facts.get("branch_sequence") or "") or bool(facts.get("branch_transitions", 0))
                  or bool(an.get("ulog_landed_returned")))
        if band is None:
            targets = [unclassified]
        else:
            targets = [by_band[band], by_band[band]["by_delay"].setdefault(str(delay), blank())]
        for t in targets:
            t["n"] += 1
            t["valid"] += 1 if _is_valid(v, band) else 0
            t["pass"] += 1 if v == "PASS" else 0
            t["exit1"] += 1 if v in mj.EXIT1_VERDICTS else 0
            t["excluded"] += 1 if v in EXCLUDED else 0
            t["aerial"] += 1 if aerial else 0
            t["hold_end"] += 1 if v == "HOLD_END" else 0
        if band is not None and delay is not None and planned_band(delay) == band and _is_valid(v, band):
            plan_ok[delay] = plan_ok.get(delay, 0) + 1
    met = {}
    for b in BANDS:
        d = by_band[b]
        planned = [x for x in ITEM3_DELAYS_S if planned_band(x) == b]
        per_delay = {}
        if b != BAND_BOUNDARY:       # 계획한 지연값 전부. 돌리지 않은 지연값은 0이라 미달이다
            per_delay = {str(x): plan_ok.get(x, 0) for x in planned}
        ok_total = d["valid"] >= MIN_VALID_BY_BAND[b]
        ok_delay = all(n >= MIN_VALID_PER_DELAY for n in per_delay.values())
        d["min"] = MIN_VALID_BY_BAND[b]
        d["met_total"] = ok_total
        d["per_planned_delay_valid"] = per_delay
        d["met_per_delay"] = ok_delay
        d["met"] = ok_total and ok_delay
        met[b] = d["met"]
    bd = by_band[BAND_BOUNDARY]
    return {"bands": by_band, "unclassified": unclassified, "all_met": all(met.values()),
            "boundary_aerial_none": bd["valid"] >= 1 and bd["aerial"] == 0}


BOUNDARY_NO_AERIAL_TEXT = ("경계에서 공중 분기는 생기지 않았다(M5의 경계 문장이 실측으로 받쳐진 것은 아니다)")


def top_lines(summary):
    """요약 맨 위에 둘 대역별 충족 여부 줄 목록."""
    lines = ["대역별 충족 여부(최소 유효 시도: spoolup 6, 내부 10, 경계 4. spoolup과 내부는 계획한 지연값마다 2):"]
    names = {BAND_SPOOLUP: "spoolup", BAND_INNER: "내부", BAND_BOUNDARY: "경계"}
    for b in BANDS:
        d = summary["bands"][b]
        extra = ""
        if b != BAND_BOUNDARY:
            extra = ", 지연값별 유효 %s, 지연값별 충족 %s" % (d["per_planned_delay_valid"], d["met_per_delay"])
        bound = ""
        if d["valid"] and d["exit1"] == 0:
            bound = ", 무실패일 때 실패율 95%% 상한 %s" % mj.upper95_text(d["valid"])
        lines.append("  %s: %s (유효 %d/%d, n %d, PASS %d, 제외 %d, 공중 분기 %d%s%s)" % (
            names[b], "충족" if d["met"] else "미달", d["valid"], d["min"], d["n"], d["pass"], d["excluded"],
            d["aerial"], extra, bound))
    bd = summary["bands"][BAND_BOUNDARY]
    lines.append("  경계 유효 %d회(최소 %d %s), HOLD_END %d회는 architect 판정 대기" % (
        bd["valid"], bd["min"], "충족" if bd["met"] else "미달", bd["hold_end"]))
    u = summary["unclassified"]
    lines.append("  대역을 정하지 못한 행: %d(INCONCLUSIVE 등. 유효 시도가 아니다)" % u["n"])
    lines.append("  전체: %s" % ("세 대역 모두 충족" if summary["all_met"] else "미달이 있다(종료 코드 2)"))
    if summary["boundary_aerial_none"]:
        lines.append("  " + BOUNDARY_NO_AERIAL_TEXT)
    return lines


TOP_BEGIN = "## 대역 충족 여부 (crosscheck 뒤)"
TOP_END = "## 대역 충족 여부 끝"


def insert_top_block(text, lines):
    """요약 본문의 첫 줄(제목) 바로 뒤에 대역 충족 여부 절을 넣는다. 이미 있으면 떼고 새로 넣는다(--force 재실행)."""
    i = text.find(TOP_BEGIN)
    if i >= 0:
        j = text.find(TOP_END, i)
        if j >= 0:
            end = text.find("\n", j)
            text = text[:i].rstrip("\n") + "\n" + text[end + 1:] if end >= 0 else text[:i]
    head, nl, rest = text.partition("\n")
    block = "\n".join([TOP_BEGIN] + lines + [TOP_END])
    return head + nl + block + "\n" + rest


def delay_table_lines(rows, finals, analyses, reasons=None):
    """지연값별 t_p - t_A, t_ramp - t_A, t_lf - t_A, 대역, r_p, first_disarm_lost 표(요약에 붙인다).
    reasons({(item, 시도): 사유 목록})가 있으면 PASS가 아닌 행 아래에 사유를 붙인다."""
    out = ["지연값별 시도(t_A 기준 초. 첫 disarm과 landed false의 부호 있는 간격은 t_p - t_lf):"]
    for r in sorted(rows, key=lambda x: (((x.get("injection") or {}).get("delay_s_nominal") or 0), x["attempt"])):
        an = analyses.get(r["attempt"]) or {}
        inj = r.get("injection") or {}

        def g(k):
            v = an.get(k)
            return "-" if v is None else ("%.3f" % v if isinstance(v, float) else str(v))
        fin = finals.get((r["item"], r["attempt"]), r["verdict"])
        out.append("  시도 %2d 지연 %s(실제 %s) 대역 %s r_p %s t_p-t_A %s t_ramp-t_A %s t_lf-t_A %s t_p-t_lf %s "
                   "first_disarm_lost %s 최종 %s" % (
                       r["attempt"], inj.get("delay_s_nominal"),
                       "-" if inj.get("delay_s_actual") is None else "%.3f" % inj["delay_s_actual"],
                       an.get("band") or "-", g("r_p"), g("tp_minus_tA_s"), g("tramp_minus_tA_s"),
                       g("tlf_minus_tA_s"), g("tp_minus_tlf_s"), an.get("first_disarm_lost"), fin))
        if reasons and fin != "PASS":
            for why in reasons.get((r["item"], r["attempt"]), []):
                out.append("      사유: %s" % why)
    return out


def header_lines(delays, attempts, image_keys, takeoff_alt_m=None):
    """summary_item3.txt 머리(실행 전)에 적을 줄: 지연값 아홉 개, T_r, T_lf의 출처, 대역 정의."""
    have = {e["image"]: e["key"] for e in (image_keys or [])}
    ref = T_LF_REF
    per = attempts // len(delays) if delays else 0
    return [
        "지연값 %d개(sim 초, 첫 ARMED 표본의 PX4 timestamp 기준): %s. 지연값마다 %d회, 합 %d회, 라운드 로빈 순서. "
        "실행 전에 고정했고 결과를 보고 더하지 않는다. 다른 시도 수나 일부 지연값만의 실행은 받지 않는다."
        % (len(delays), ", ".join(str(x) for x in delays), per, attempts),
        "계산: spoolup 0, 0.5 / 내부 T_r + {0.1, 0.3, 0.5, 0.7} x (T_lf - T_r) / 경계 T_lf - {0.10, 0.05, 0.02}.",
        "T_r = %.1f s (COM_SPOOLUP_TIME. 이 프로젝트는 바꾸지 않는다)" % T_R_S,
        "T_lf = %.3f s (근거 실행 %s의 ULog %d개 표본의 최솟값, 최댓값 %.3f s). 정의: %s" % (
            ref["min_s"], ref["run_id"], ref["n"], ref["max_s"], ref["definition"]),
        "T_lf의 근거: image key %s, TAKEOFF 목표 높이 %s m. 이 실행: image key %s, TAKEOFF 목표 높이 %s m "
        "(같아야 실행한다)" % (ref["image_keys"], ref["takeoff_alt_m"], {k: have.get(k) for k in sorted(ref["image_keys"])},
                              takeoff_alt_m),
        "대역은 t_p(ULog로 본 첫 disarm의 처리 시각) 기준이다. 내부/경계 경계는 T_lf - %.2f s = %.3f s." % (
            BOUNDARY_MARGIN_S, ref["min_s"] - BOUNDARY_MARGIN_S),
    ]
