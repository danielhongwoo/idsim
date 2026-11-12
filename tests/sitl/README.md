# tests/sitl

이륙-호버-착륙 통합 테스트(시나리오 B, C, A, D, T)와 PX4 재실측 스크립트(`measure/`)다. 설계와 계약은 `docs-for-agent/plan-1a-6-idsim-mission/decisions.md`(쟁점 1, 7-11)에 있다. 소유는 test-engineer다.

## 실행

```
tests/sitl/run_sitl.sh [--stack k] [--repeat N] [--attach <실행 디렉터리>] [-- pytest 인자...]
```

- 스택은 호스트 wrapper가 `tools/sim_stack.sh`로 올리고 내린다. pytest는 `runner`(ros-ws) 컨테이너 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증만 한다. 검증이 실패하면 skip이 아니라 오류다.
- `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다(`tools/ros_ws.sh build`).
- `--repeat N`은 회마다 down 뒤 콜드 up이다. 첫 실패에서 멈추고 재시도하지 않는다. "로컬 3회 연속 통과"는 같은 commit, 같은 이미지 key에서 `--repeat 3`이 세 회 모두 통과하는 것이다. 실패하면 0부터 다시 센다. `artifacts/sitl_repeat/<시각>-k<k>/`에 `repeat_summary.tsv`(실행 id, commit과 dirty, 이미지 key, 시나리오별 verdict, 시나리오 A 이정표별 ROS 시각 소요, RTF, 벽시계 소요, ARMED 표본 수)와 `armed_criterion.json`이 남는다.
- `-- -k test_b`처럼 일부 시나리오만 고르면 나머지가 빠지므로 `verdict.json`의 통과 조건(다섯 시나리오 모두 passed)에 걸려 종료 코드 1로 끝난다. 디버깅 용도로만 쓴다.
- `--attach DIR`은 올리지도 내리지도 않고 pytest와 수집만 한다(QGC와 Gazebo GUI 육안 확인, 디버깅). 산출물은 `DIR/sitl-attach-<시각>/`에 쓴다.
- 종료 코드: 0 전체 통과, 1 시나리오나 정지 검사 실패(ULog 교차 확인 실패 포함), 2 사용법, 선행 조건, 스택 올리기(`INFRA_UP`) 실패, ULog 교차 확인의 입력 없음과 판정 불가. ULog 교차 확인 실패는 1, 입력 없음과 판정 불가(파싱 중 예외 포함)는 2다. stdout 마지막 줄은 실행 디렉터리다. 환경변수 `SITL_PYTEST_TIMEOUT`(기본 900 s)이 pytest 전체의 벽시계 상한이다.
- 이 디렉터리의 테스트는 lint job의 pytest(`tests/support`, `tests/tools`)가 수집하지 않는다.

## 시나리오와 판정

한 스택에서 B, C, A, D, T 순서로 돈다. 판정 시간은 모두 ROS 시각이다. 판정 입력은 토픽에서만 읽는다(goal의 목표값과 `vehicle_local_position`, `vehicle_status`, `vehicle_land_detected`, `failsafe_flags`, `mission_event`, action의 feedback과 result). 노드가 낸 setpoint는 입력으로 쓰지 않는다. 판정 함수는 `tests/support/sitl_judge.py`(순수 코드)에 있다.

| 시나리오 | 내용 | 판정 필드 |
| --- | --- | --- |
| B | GOTO가 든 미션 | result ABORTED와 `REASON_INVALID_MISSION`. 접수와 종료 사건 한 쌍(종료 사건 == result). feedback 0건. goal 뒤 5 s 동안 ARMED 표본 없음 |
| C | goal의 `vehicle_id`가 다른 값 | result ABORTED와 `REASON_VEHICLE_ID_MISMATCH`. 사건의 `vehicle_id`는 Executor 자신의 값. feedback 0건. 5 s 동안 ARMED 표본 없음 |
| A | `[TAKEOFF 5 m, LOITER 5 s, LAND]` | SUCCEEDED, `REASON_NONE`, `items_completed` 3. 사건 짝과 result 일치. 이정표 순서(goal 전송, 접수, ARMED, TAKEOFF 시작, 도달, LAND 시작, AUTO_LAND, DISARMED, result)가 ROS 시각으로 줄어들지 않음. LOITER 유지 5 s 이상과 고도 허용 0.5 m. TAKEOFF와 LOITER 동안 `failsafe`가 false이고 `nav_state`가 OFFBOARD. ARMED를 본 뒤의 AUTO_LAND, 그 뒤 DISARMED 3회 연속. OFFBOARD가 아닌 ARMED 표본 0개 |
| D | 도달 뒤 cancel, 이어서 `[LAND]` | cancel 응답 `ERROR_NONE`, CANCELED와 `REASON_NONE`. AUTO_LOITER 3회 연속, 그 뒤 5 s 동안 고도 변화 0.5 m 이하이고 ARMED, `landed` false. `[LAND]` 미션 SUCCEEDED, ARMED 뒤 AUTO_LAND, DISARMED 3회 연속, `landed` true |
| T | 지상, Executor idle, `offboard_control_mode`(`position=true`) 20 Hz | timestamp가 현재이면 `offboard_control_signal_lost` false, `now - 2 s`이면 true, 다시 현재이면 false. 각 단계 3회 연속(서로 다른 timestamp), 단계마다 대기 상한 5 s. 내내 ARMED 표본 없음 |

- 시나리오마다 사전조건(지상, DISARMED 3회 연속)을 단정하고 어긋나면 그 자리에서 `PRECONDITION`으로 실패한다.
- 도달의 입력은 goal 직전의 `vehicle_local_position` z(`z_valid`)와 goal의 높이와 허용 오차다.
- gate(모든 시나리오 앞): `/clock` 수신, `mission_event` 발행자와 PX4 토픽 발행자, action server 준비, 기대 sysid의 `vehicle_status`, `/clock` 정렬(노드 시각 - `vehicle_status.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s). `mission_event` 구독은 action client보다 먼저 같은 node에서 만든다(`tests/support/mission_client.py`).
- verdict 분류: `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_SLOW`, `CLOCK_ABSENT`, `CLOCK_BACKWARD`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`. 대기마다 `wall_cap = ROS 시각 timeout x 3 + 10 s`를 두고, 넘으면 `/clock`이 벽시계 5 s 동안 진행하지 않았는지로 `CLOCK_STALLED`와 `CLOCK_SLOW`를 가른다. 배수를 올려 통과시키지 않는다.

## 산출물

`artifacts/runs/<실행 id>/` 아래. 실패하면 이 디렉터리 전체를, 성공하면 `sitl/junit.xml`, `sitl/trace.jsonl`, `sitl/summary.md`를 CI가 올린다.

- `compose.yaml`, `stack.json`, `params/`, `px4-N/log/*.ulg`, `ros_log/`
- `sitl/`: `junit.xml`, `trace.jsonl`(gate, goal, 사건 판정, 이정표), `verdict.json`(gate와 시나리오별 결과, RTF, 시나리오 A의 ARMED 기록), `summary.md`, `steps.tsv`(단계별 벽시계 초, 서비스 종료 상태 `stop_exit_*`, ULog 끝 경계 `ulog`, 회차별 종료 코드 `rc_*` 줄), `raw_status_A.jsonl`, `armed_a.json`, `ps_before_stop.jsonl`(stop 전 서비스 상태), `logs/<서비스>.log`, `health_<서비스>.txt`(실패한 회나 unhealthy 서비스만), `crosscheck_a.json`

유지 구간(A의 LOITER, D의 취소 뒤 유지)의 기준 고도로부터의 최대 편차는 통과한 회에도 `trace.jsonl`(`hold_deviation`), `verdict.json`(`hold_deviation_m`), `repeat_summary.tsv`(`hold_dev_*_m`)에 남는다. 항목별 임계값(A의 LOITER 0.4 m, D의 유지 0.25 m)을 넘으면 `summary.md`와 `armed_criterion.json`의 `hold_deviation_notes`에 note가 붙는다(판정 상수 0.5 m 재검토의 근거. 임계값은 `tests/support/sitl_summary.py`의 `HOLD_DEV_NOTE_M`).

## 시나리오 A의 ARMED 표본 기록

`vehicle_status` 원시 표본을 KEEP_ALL 구독의 별도 기록기(`px4_raw.Px4Raw`)로 받는다. 판정 probe의 tick 모델과 무관하다. `raw_status_A.jsonl`의 표본마다 `timestamp`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`, 수신 ROS 시각이 있다. goal 전송부터 TAKEOFF 시작(feedback `PHASE_EXECUTING`의 stamp)까지 ARMED 표본 수와 OFFBOARD가 아닌 ARMED 표본 수를 PX4 `timestamp` 축으로 세어 `armed_a.json`과 `verdict.json`에 적는다. OFFBOARD가 아닌 ARMED 표본이 한 건이라도 나오면 시나리오 A는 실패하고 architect에게 올린다. 부류별 기준(ARMED 3회 확인까지 간 실행 10회 이상에서 0개)의 판정은 `measure_judge.judge_armed_criterion`이고 `--repeat 10`의 `armed_criterion.json`에 나온다. 10회 중 0건은 실패율 95% 상한이 약 26%라는 뜻이다.

### ULog 교차 확인

값의 정본은 PX4이므로 실행이 끝나면 `crosscheck_a.py <실행 디렉터리>`가 `raw_status_A.jsonl`을 ULog의 `vehicle_status`와 대조한다(`measure_check.check_row` 재사용). 위반 구간은 goal 전송부터 TAKEOFF 시작 feedback의 stamp 뒤 0.5 s까지이고 비행 구간은 그 뒤 LAND 시작 feedback까지다. 결과는 `sitl/crosscheck_a.json`이다.

- 판정: ULog 기준 OFFBOARD가 아닌 ARMED 표본이 위반 구간(`ulog_armed_non_offboard`)이나 비행 구간(`ulog_flight_armed_non_offboard`)에 있으면 종료 코드 1이고 `run_sitl.sh`가 그 실행을 실패로 센다. 입력이 없으면(ULog나 원시 표본 없음) 종료 코드 2이고 INFRA로 따로 센다.
- 기록만 하는 것: `ros_missing_in_ulog`, `ros_field_mismatch`, `ulog_only`. `ulog_only`가 0이 아니면 `notes`에 적는다.
- `--repeat`의 `armed_criterion.json`은 `passed`(ROS 기록만)와 `passed_with_ulog`(모든 회의 교차 확인이 끝났고 ULog 기준 위반이 0건)를 둘 다 적고 `ulog_crosscheck`에 합계를 둔다.

## 측정 스크립트

`measure/`는 Executor 없이 PX4에 직접 명령을 보내는 PX4 재실측 도구다(사용법은 `measure/README.md`). `tests/support/px4_measure_pub.py`는 이 디렉터리 밖에서 가져가지 않는다(pytest가 검사한다).
