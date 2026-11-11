# PX4 재실측 측정 스크립트

`docs-for-agent/plan-1a-6-idsim-mission/decisions.md` 넘김 목록의 px4-engineer 행 중 재실측 (2), (3), (5)와, OFFBOARD가 아닌 ARMED 표본 기록(시나리오 A 대응)을 돌리는 도구다. 소유는 test-engineer, 절차의 필수 승인자는 px4-engineer다.

## 실행

```
tests/sitl/measure/run_measure.sh [--stack 7] [--attempts N] [--keep] item2|item3|item5|armed|all
```

- 스택 번호 기본값은 7(실험용). 0은 사용자 스택이라 거부한다.
- `item2` 재실측 (2), `item3` 재실측 (3), `item5` 재실측 (5), `armed` 시나리오 A에 대응하는 arm -> ARMED 3회 -> 이륙 시작 구간의 기록.
- 기본 시도 수: item2 3, item3 3, item5 10, armed 10. 통과 기준의 최소 시도 수와 같다.
- 본 측정에서 `all`은 item3, item5, item2, armed 순으로 한 스택에서 돈다.

## 구조

| 파일 | 역할 |
| --- | --- |
| `run_measure.sh` | 호스트. 스택 올리기, runner에서 `measure.py` 실행, 스택 멈추기, ULog 교차 확인, 내리기 |
| `measure.py` | runner 안. PX4에 직접 명령을 보내고 원시 표본을 기록, 시도마다 판정 |
| `crosscheck.py` | 호스트. 기록을 ULog의 `vehicle_status`와 대조하고 ARMED 기준을 합산 |
| `tests/support/measure_judge.py` | 판정 로직(순수 코드). 단위 테스트 `test_measure_judge.py` |
| `tests/support/px4_raw.py` | KEEP_ALL 구독 기록기와 직접 명령 송신기(rclpy) |
| `tests/support/ulog_min.py` | ULog에서 한 토픽만 읽는 최소 파서(이미지에 pyulog가 없다) |

## 기록

`artifacts/runs/<실행 id>/measure/` 아래.

- `measure_<item>.jsonl` 시도마다 한 줄. 필드: `run_id`, `commit`, `dirty`, `images`, `image_keys`, `attempt`, `item`(2a, 2b, 3, 5, armed), `injection`(주입 조건과 trigger), `verdict`/`result`, `reasons`, `ros_start_us`, `ros_end_us`, `ros_elapsed_s`, `wall_elapsed_s`, `exit_code`(0 PASS, 1 FAIL, 2 그 밖), `ulog`, `facts`(정리 총 소요, 분기 순서와 전환 횟수, landed 전환 횟수와 간격, ARMED 표본 수, 상승 등).
- `raw_<item>.jsonl` 시도마다 `vehicle_status`(timestamp, 받은 ROS 시각, 같은 시점의 `/clock`, arming_state, nav_state, failsafe, nav_state_user_intention), `vehicle_land_detected`, 위치, ack, 명령 전송의 원시 표본.
- `summary_<item>.txt` 머리에 통과 기준(실행 전에 기록), 아래에 결과.
- `distribution_<item>.json` 모든 `vehicle_status` 표본의 `timestamp - 받은 ROS 시각`, `timestamp - /clock`의 부호 있는 분포와, 명령 전송 뒤 처음 받은 표본의 `timestamp - Px4Timestamp` 분포.
- `crosscheck_<item>.json`, `armed_criterion.json` ULog 교차 확인과 ARMED 기준 합산.
- `stop_exit.txt` `compose stop -t 15` 뒤 서비스별 종료 코드(px4의 137은 KILL, ULog가 닫히지 않았을 수 있다).

## 규칙

- 실패한 시도를 기록에서 빼지 않고 재시도하지 않는다.
- 타임아웃과 지연은 `/clock` 기준이다. 벽시계는 `/clock`이 멈췄는지 보는 데만 쓴다.
- trigger는 sleep이 아니라 표본 이벤트다(첫 ARMED 표본, `landed` 표본, Hold 관측). 예외는 (5)의 주입 지연으로, arm 전송 뒤 sim 시간 0-0.2 s를 재는 값이며 입력 변수로 기록한다.
- 10회 중 0건은 실패율의 95% 상한이 약 26%라는 뜻이다. "10/10 통과"를 "플래키 없음"으로 쓰지 않는다.
- 정리 총 소요 9 s 미만을 넘는 실행이 있으면 상한을 올리지 않고 architect에게 올린다.
