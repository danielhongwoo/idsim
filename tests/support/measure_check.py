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

"""ROS 원시 표본과 ULog vehicle_status의 교차 확인(순수 코드). tests/sitl/crosscheck_a.py가 쓴다.

입출력과 rclpy가 없어 tests/support의 단위 테스트가 SITL 없이 검증한다.
"""
from tests.support import measure_judge as mj

CROSS_FIELDS = (("arming_state", "arming_state"), ("nav_state", "nav_state"),
                ("failsafe", "failsafe"), ("nav_state_user_intention", "intention"))


def _ulog_equal(key, ulog_val, ros_val):
    if key == "failsafe":
        return bool(ulog_val) == bool(ros_val)
    return int(ulog_val) == int(ros_val)


def check_row(row, raw_status, ulog_by_ts, ulog_ts):
    """한 시도 행을 ULog와 대조한다. 대조 구간이 없는 행(ARMED 구간 없음, 측정 안 됨)은 None.

    row: 시도 한 행(facts에 armed_window_ros_us, arm_send 필요. 없으면 KeyError).
    raw_status: 그 시도의 raw status 표본(dict, ts_us/recv_ros_us/...).
    ulog_by_ts: {timestamp: ULog 행}, ulog_ts: 정렬된 timestamp 목록.

    두 구간을 쓴다.
      위반 구간 [arm 전송의 Px4Timestamp, ARMED 구간 끝]: ULog 기준 비OFFBOARD ARMED를 센다.
      대조 구간 [arm 전송의 Px4Timestamp, max(ROS 마지막 표본의 ts, 정리 종료 시각, NAV_LAND 전송 시각)]:
        ROS 표본이 ULog에 있는지, ULog에만 있는 표본(ROS 유실)이 있는지 본다. 종료 시각은 ROS 수신
        시각을 PX4 timestamp 축의 근사로 쓴다(두 축은 같은 sim 시간이고 두 축의 차이는 이 함수가 따로 보지 않는다).
    facts에 land_send가 있으면 ARMED 3회 확인부터 NAV_LAND 전송까지(위반 구간 뒤)의 ULog 비OFFBOARD
    ARMED도 위반으로 센다(ulog_flight_armed_non_offboard).
    """
    f = row["facts"]
    if f is None or "armed_window_ros_us" not in f:
        return None
    lo_recv, win_recv = f["armed_window_ros_us"]
    lo_ts = f["arm_send"][1]
    end_recv = f["cleanup_end_ros_us"] if "cleanup_end_ros_us" in f else win_recv
    end_recv = max(end_recv, win_recv)
    has_flight = "land_send" in f and f["land_send"] is not None
    if has_flight:
        end_recv = max(end_recv, f["land_send"][0])
    ros = [s for s in raw_status if lo_recv <= s["recv_ros_us"] <= end_recv]
    ros_last_ts = max([s["ts_us"] for s in ros], default=lo_ts)
    wide_hi = max(ros_last_ts, end_recv)
    win_hi = max([s["ts_us"] for s in ros if s["recv_ros_us"] <= win_recv], default=lo_ts)
    win_hi = max(win_hi, win_recv)

    missing = 0
    mismatch = []
    for s in ros:
        u = ulog_by_ts.get(s["ts_us"])
        if u is None:
            missing += 1
            continue
        for ukey, rkey in CROSS_FIELDS:
            if not _ulog_equal(ukey, u[ukey], s[rkey]):
                mismatch.append({"ts_us": s["ts_us"], "field": ukey, "ulog": u[ukey], "ros": s[rkey]})
    ros_ts = {s["ts_us"] for s in ros}
    in_range = [t for t in ulog_ts if lo_ts <= t <= wide_hi]
    ulog_only = [t for t in in_range if t not in ros_ts]

    def armed_bad(ts_list):
        n = 0
        bad = []
        for t in ts_list:
            u = ulog_by_ts[t]
            if int(u["arming_state"]) == mj.ARMING_STATE_ARMED:
                n += 1
                if int(u["nav_state"]) != mj.NAV_STATE_OFFBOARD:
                    bad.append({"ts_us": t, "nav_state": u["nav_state"], "failsafe": u["failsafe"],
                                "intention": u["nav_state_user_intention"]})
        return n, bad

    n_armed, bad = armed_bad([t for t in in_range if t <= win_hi])
    _, bad_after = armed_bad([t for t in in_range if t > win_hi])
    flight = len(bad_after) if has_flight else 0
    gaps = [b - a for a, b in zip(in_range, in_range[1:])]
    return {
        "item": row["item"], "attempt": row["attempt"], "ros_samples": len(ros),
        "ros_missing_in_ulog": missing, "ros_field_mismatch": mismatch,
        "ulog_samples_in_range": len(in_range), "ulog_only": len(ulog_only),
        "ulog_armed_samples": n_armed, "ulog_armed_non_offboard": len(bad),
        "ulog_armed_non_offboard_samples": bad,
        "ulog_armed_non_offboard_after_window": len(bad_after),
        "ulog_flight_armed_non_offboard": flight,
        "ulog_min_interval_ms": (min(gaps) / 1000.0) if gaps else None,
        "ts_range_us": [lo_ts, wide_hi], "violation_range_us": [lo_ts, win_hi],
    }
