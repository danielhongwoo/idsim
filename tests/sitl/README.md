# tests/sitl

미션 통합 테스트(시나리오 B, C, A, D, F1, F2, F3, F4, T)다. 계약은 `docs/interface.md`, 1b 판정은 `docs-for-agent/plan-1b-mission-target/decisions.md` 쟁점 5, 15에 있다. 소유는 test-engineer다.

## 실행

```
tests/sitl/run_sitl.sh [--stack k] [--repeat N] [--scenarios all|ci] [--attach <실행 디렉터리>] [-- pytest 인자...]
```

- 스택은 호스트 wrapper가 `tools/sim_stack.sh up --fleet tests/sitl/fleet.yaml`로 올리고 내린다. `tests/sitl/fleet.yaml`은 sitl 전용 fleet 파일(기체 1을 (6, -3, 0)에 스폰, F2와 F4의 표적 `car_1`)이고 개발용 `config/fleet.yaml`과 따로 둔다.
- `--scenarios`는 실행 목록이다(`tests/support/sitl_summary.py`의 `SCENARIO_SETS`). 없으면 GitHub Actions에서는 `ci`, 그 밖에서는 `all`이다. 목록은 runner에 `IDSIM_SITL_SCENARIOS`로 넘어가고 목록 밖의 시나리오는 수집에서 빠진다. 판정 상수 b와 `R_home`이 빈 보정 상태(`tests/support/sitl_judge.py` 머리말)에서는 `ci` 목록에 F1-F4가 없다(로컬 `all`에서만 돈다). 상수가 빈 채 `CI_SCENARIOS`에 F1-F4를 넣으면 `tests/support/test_sitl_flight_missions.py`가 실패한다. pytest는 `runner`(ros-ws) 컨테이너 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증만 한다. 검증이 실패하면 skip이 아니라 오류다.
- `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다(`tools/ros_ws.sh build`).
- `--repeat N`은 회마다 down 뒤 콜드 up이다. 첫 실패에서 멈추고 재시도하지 않는다. "로컬 3회 연속 통과"는 같은 commit, 같은 이미지 key에서 `--repeat 3`이 세 회 모두 통과하는 것이다. 실패하면 0부터 다시 센다. `artifacts/sitl_repeat/<시각>-k<k>/`에 `repeat_summary.tsv`(실행 id, commit과 dirty, 이미지 key, 시나리오별 verdict, 시나리오 A 이정표별 ROS 시각 소요, RTF, 벽시계 소요, ARMED 표본 수, 유지 구간 편차 `hold_dev_*_m`, 단계별 종료 코드 `rc_*`)와 `armed_criterion.json`이 남는다.
- `-- -k test_b`처럼 일부 시나리오만 고르면 나머지가 빠지므로 `verdict.json`의 통과 조건(실행 목록의 시나리오 모두 passed)에 걸려 종료 코드 1로 끝난다. 디버깅 용도로만 쓴다. F3은 F2가 남긴 공중 Hold에서 시작하므로 따로 돌릴 수 없다(F2가 바로 앞에 통과하지 않았으면 `PRECONDITION`).
- `--attach DIR`은 올리지도 내리지도 않고 pytest와 수집만 한다(QGC와 Gazebo GUI 육안 확인, 디버깅). 산출물은 `DIR/sitl-attach-<시각>/`에 쓴다.
- 종료 코드: 0 전체 통과, 1 시나리오나 정지 검사 실패(ULog 교차 확인 실패 포함), 2 사용법, 선행 조건, 스택 올리기(`INFRA_UP`) 실패, ULog 교차 확인의 입력 없음과 판정 불가. ULog 교차 확인 실패는 1, 입력 없음과 판정 불가(파싱 중 예외 포함)는 2다. stdout 마지막 줄은 실행 디렉터리다. 환경변수 `SITL_PYTEST_TIMEOUT`(기본 900 s)이 pytest 전체의 벽시계 상한이다.
- 이 디렉터리의 테스트는 lint job의 pytest(`tests/support`, `tests/tools`)가 수집하지 않는다. 시험 미션 YAML(`tests/sitl/missions/`)의 시간 합산과 판정 상수 대조(`tests/support/test_sitl_flight_missions.py`)는 lint job에서 돈다. 로더(`ros_ws/src/idsim_mission/idsim_mission/mission_yaml.py`)를 저장소 소스 경로에서 읽기 때문이다(`tests/support/sitl_missions.py`).
- `tests/support/test_sitl_constants.py`와 `test_px4_topic_names.py`는 `idsim_interfaces`와 `px4_msgs`가 있어야 돌아서 lint job에서는 건너뛴다. `run_sitl.sh`가 runner 안에서 `tests/sitl`과 함께 돌린다.

## 시나리오와 판정

한 스택에서 B, C, A, D, F1, F2, F3, F4, T 순서로 돈다. 판정 시간은 모두 ROS 시각이다. 판정 입력은 토픽에서만 읽는다(goal의 목표값과 `vehicle_local_position`, `vehicle_status`, `vehicle_land_detected`, `failsafe_flags`, `mission_event`, action의 feedback과 result). 노드가 낸 setpoint는 입력으로 쓰지 않는다. 판정 함수는 `tests/support/sitl_judge.py`(순수 코드)에 있다.

| 시나리오 | 내용 | 판정 필드 |
| --- | --- | --- |
| B | 1b 무효 사례 8개(`tests/support/sitl_missions.py`의 `B_INVALID_CASES`: `[]`, 첫 항목이 아닌 TAKEOFF, `[LAND, GOTO]`, 가운데 RTL, `[RTL, GOTO]`, TRACK_ENTITY의 0 `offset`, 형식이 틀린 `target_id`, 기본값 TRACK_ENTITY 서브메시지)를 순서대로 | 사례마다 result ABORTED와 `REASON_INVALID_MISSION`, `detail`에 사례의 기대 조각(의도한 검사에서 거부됐는가. 문구는 계약이 아니다), 접수와 종료 사건 한 쌍(종료 사건 == result), feedback 0건. 첫 goal부터 끝(마지막 사례 뒤 5 s)까지 한 구간에서 ARMED 표본 없음. 거부가 아닌 결과는 그 사례에서 바로 실패하고 goal 취소와 비상 정리를 한다 |
| C | goal의 `vehicle_id`가 다른 값 | result ABORTED와 `REASON_VEHICLE_ID_MISMATCH`. 사건의 `vehicle_id`는 Executor 자신의 값. feedback 0건. 5 s 동안 ARMED 표본 없음 |
| A | `[TAKEOFF 5 m, LOITER 5 s, LAND]` | SUCCEEDED, `REASON_NONE`, `items_completed` 3. 사건 짝과 result 일치. 이정표 순서(goal 전송, 접수, ARMED, TAKEOFF 시작, 도달, LAND 시작, AUTO_LAND, DISARMED, result)가 테스트 노드 수신 시각으로 줄어들지 않음. LOITER 유지 5 s 이상과 고도 허용 0.5 m. TAKEOFF와 LOITER 동안 `failsafe`가 false이고 `nav_state`가 OFFBOARD. ARMED를 본 뒤의 AUTO_LAND, 그 뒤 DISARMED 3회 연속. OFFBOARD가 아닌 ARMED 표본 0개 |
| D | 도달 뒤 cancel, 이어서 `[LAND]` | cancel 응답 `ERROR_NONE`, CANCELED와 `REASON_NONE`. AUTO_LOITER 3회 연속, 그 뒤 5 s 동안 고도 변화 0.5 m 이하이고 ARMED, `landed` false. `[LAND]` 미션 SUCCEEDED, ARMED 뒤 AUTO_LAND, DISARMED 3회 연속, `landed` true |
| F1 | `missions/f1.yaml`: `[TAKEOFF 5 m, GOTO x 3, LAND]`(한 변 10 m) | 계약 판정: SUCCEEDED, 사건 짝, 항목 순서(feedback의 item_index와 type), ARMED -> AUTO_LAND -> DISARMED 3회, landed. 정답 판정: GOTO 완료마다 t_f의 정답 거리 1.0 m 안(`REACH_MISMATCH`), DISARMED 시점 정답 z가 이륙 직전 + 0.3 m 안 |
| F2 | `missions/f2.yaml`: `[TAKEOFF, GOTO, TRACK_ENTITY]`(표적 `car_1`, 1-2 m/s) | SUCCEEDED, 항목 순서, 마지막 항목 뒤 AUTO_LOITER 3회와 5 s 동안 ARMED, landed false, 고도 유지(`HOLD_AIRBORNE`). 표적 접근: t_f의 정답 위치와 "보간한 표적 + offset"의 거리 1.0 m + v x L 안, 접근 구간의 표적 이동(`NO_TARGET_MOTION`) |
| F3 | `missions/f3.yaml`: `[GOTO, RTL]`(F2의 Hold에서 공중 시작) | 사전조건 공중 Hold. SUCCEEDED, 항목 순서, ARMED -> AUTO_RTL -> DISARMED 3회, landed. 착륙 수평 위치와 F2 이륙 직전 위치의 거리 R4(보정 상태에서는 `recorded_only`) |
| F4 | `missions/f4.yaml`: `[TAKEOFF 5 m, GOTO x 2, TRACK_ENTITY, RTL]` | F1의 도달, F2의 표적 접근, F3의 RTL 착륙 판정(기준점은 F4 자신의 이륙 직전 위치) |
| T | 지상, Executor idle, `offboard_control_mode`(`position=true`) 20 Hz | timestamp가 현재이면 `offboard_control_signal_lost` false, `now - 2 s`이면 true, 다시 현재이면 false. 각 단계 3회 연속(서로 다른 timestamp), 단계마다 대기 상한 5 s. 내내 ARMED 표본 없음 |

- 시나리오마다 사전조건(지상, DISARMED 3회 연속. F3은 공중 Hold)을 단정하고 어긋나면 그 자리에서 `PRECONDITION`으로 실패한다.
- 비행 시나리오(A, D, F1-F4)가 실패하면 정리용 `[LAND]`를 한 번 시도하고(판정에 넣지 않는다) 뒤의 비행 시나리오는 실행하지 않고 `UPSTREAM_FAILED`(실패로 센다)다. 정리도 실패해 T의 사전조건이 맞지 않으면 T는 `PRECONDITION`이다.
- 1b 판정은 계약 판정(계약 토픽과 PX4 토픽)과 정답 판정(SITL 전용 정답 pose `/sim/<vehicle_id>/pose`)으로 나뉜다. 정답 pose가 없으면 `ORACLE_ABSENT`, t_f를 감싸는 정답 표본 간격이 0.1 s를 넘으면 `ORACLE_STALE`이다. t_f는 다음 항목의 첫 feedback stamp이고, 공중 종료로 가는 마지막 setpoint 항목(F2의 TRACK_ENTITY)은 거리를 싣지 않는 첫 feedback의 stamp(완료 tick보다 최대 0.5 s 늦다. trace의 `t_f_exact` false)다. 판정 상수와 근거는 `tests/support/sitl_judge.py` 머리말에 있다.
- gate는 첫 goal 전에 정답 pose와 표적의 발행자와 첫 표본을 확인하고, `/targets/<id>/state` 발행자 QoS를 계약 상태 행(RELIABLE, VOLATILE)과 대조하며(다르면 `QOS_MISMATCH`), Executor 파라미터 `target_fresh_age`를 판정 상수 L의 전제(0.1 s)와 대조한다. 정답 pose, 표적, `target_fresh_age`의 문제는 그것이 필요한 F 시나리오에서 실패로 드러난다.
- 도달의 입력은 goal 직전의 `vehicle_local_position` z(`z_valid`)와 goal의 높이와 허용 오차다.
- gate(모든 시나리오 앞): `/clock` 수신, `mission_event` 발행자와 PX4 토픽 발행자, action server 준비, 기대 sysid의 `vehicle_status`, `/clock` 정렬(노드 시각 - `vehicle_status.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s). `mission_event` 구독은 action client보다 먼저 같은 node에서 만든다(`tests/support/mission_client.py`).
- verdict 분류: `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_SLOW`, `CLOCK_ABSENT`, `CLOCK_BACKWARD`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`, `UPSTREAM_FAILED`, `ORACLE_ABSENT`, `ORACLE_STALE`, `REACH_MISMATCH`, `NO_TARGET_MOTION`, `QOS_MISMATCH`. 대기마다 `wall_cap = ROS 시각 timeout x 3 + 10 s`를 두고, 넘으면 `/clock`이 벽시계 5 s 동안 진행하지 않았는지로 `CLOCK_STALLED`와 `CLOCK_SLOW`를 가른다. 배수를 올려 통과시키지 않는다.

## 산출물

`artifacts/runs/<실행 id>/` 아래. 실패하면 이 디렉터리 전체를, 성공하면 `sitl/junit.xml`, `sitl/trace.jsonl`, `sitl/summary.md`를 CI가 올린다.

- `compose.yaml`, `stack.json`, `params/`, `px4-N/log/*.ulg`, `ros_log/`
- `sitl/`: `junit.xml`, `trace.jsonl`(gate, goal, 사건 판정, 이정표. 1b는 `reach`, `track`(R2, 추종 오차, 신선하지 않은 tick), `landing`(R4, RTL 소요), `r1`, `hold_end`(F2), `air_start`(F3), `flight_window`), `verdict.json`(gate와 시나리오별 결과, RTF, 시나리오 A의 ARMED 기록, `recorded_only`(R1, R3, R2와 R4 요약)), `trace_1b.json`(ULog의 TRACK_ENTITY 구간 속도 feedforward와 z, F3 공중 시작의 DO_SET_MODE와 D. 기록 전용), `summary.md`, `steps.tsv`(단계별 벽시계 초, 서비스 종료 상태 `stop_exit_*`, ULog 끝 경계 `ulog`, 회차별 종료 코드 `rc_*` 줄), `raw_status_A.jsonl`, `raw_status_D.jsonl`, `armed_a.json`, `ps_before_stop.jsonl`(stop 전 서비스 상태), `logs/<서비스>.log`, `health_<서비스>.txt`(실패한 회나 unhealthy 서비스만), `crosscheck_a.json`

## b와 R_home 보정 집계

`tests/sitl/calibrate.py <회차 디렉터리 또는 실행 디렉터리>... [--out 파일]`이 `--repeat`의 회차마다 `trace.jsonl`(`reach`, `track`, `landing`)과 `verdict.json`을 읽어 b와 `R_home` 후보를 낸다(계산은 `tests/support/calibration.py`, 정의는 `decisions.md` 쟁점 5). 통과한 실행만 부팅으로 센다. 출력은 부팅 수, GOTO 사건 수, mean(s), std(s), 최댓값, s_track의 사건 수, 평균, 표준편차, 최댓값, k, 두 Shapiro-Wilk p, b 후보와 0.35 m, 0.5 m 선 초과 표시, `R_home` 후보, 실행 id, 그리고 기록 전용인 t_f 수평 속도와 d_h, s의 관계다. 회차 디렉터리를 주면 그 안에 `calibration.json`을 쓴다. 종료 코드는 0 모형 검증 통과, 1 기각이나 부족, 2 입력 오류다.

유지 구간(A의 LOITER, D의 취소 뒤 유지)의 기준 고도로부터의 최대 편차는 통과한 회에도 `trace.jsonl`(`hold_deviation`), `verdict.json`(`hold_deviation_m`), `repeat_summary.tsv`(`hold_dev_*_m`)에 남는다. 항목별 임계값(A의 LOITER 0.4 m, D의 유지 0.25 m)을 넘으면 `summary.md`와 `armed_criterion.json`의 `hold_deviation_notes`에 note가 붙는다(판정 상수 0.5 m 재검토의 근거. 임계값은 `tests/support/sitl_summary.py`의 `HOLD_DEV_NOTE_M`).

## 시나리오 A의 ARMED 표본 기록

`vehicle_status` 원시 표본을 KEEP_ALL 구독의 별도 기록기(`px4_raw.Px4Raw`)로 받는다. 판정 probe의 tick 모델과 무관하다. `raw_status_A.jsonl`의 표본마다 `timestamp`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`, 수신 ROS 시각이 있다. goal 전송부터 TAKEOFF 시작(feedback `PHASE_EXECUTING`의 stamp)까지 ARMED 표본 수와 OFFBOARD가 아닌 ARMED 표본 수를 PX4 `timestamp` 축으로 세어 `armed_a.json`과 `verdict.json`에 적는다. OFFBOARD가 아닌 ARMED 표본이 한 건이라도 나오면 시나리오 A는 실패하고 architect에게 올린다. 부류별 기준(ARMED 3회 확인까지 간 실행 10회 이상에서 0개)의 판정은 `measure_judge.judge_armed_criterion`이고 `--repeat 10`의 `armed_criterion.json`에 나온다. 10회 중 0건은 실패율 95% 상한이 약 26%라는 뜻이다.

### ULog 교차 확인

값의 정본은 PX4이므로 실행이 끝나면 `crosscheck_a.py <실행 디렉터리>`가 `raw_status_A.jsonl`을 ULog의 `vehicle_status`와 대조한다(`measure_check.check_row` 재사용). 위반 구간은 goal 전송부터 TAKEOFF 시작 feedback의 stamp 뒤 0.5 s까지이고 비행 구간은 그 뒤 LAND 시작 feedback까지다. 결과는 `sitl/crosscheck_a.json`이다.

- 판정: ULog 기준 OFFBOARD가 아닌 ARMED 표본이 위반 구간(`ulog_armed_non_offboard`)이나 비행 구간(`ulog_flight_armed_non_offboard`)에 있으면 종료 코드 1이고 `run_sitl.sh`가 그 실행을 실패로 센다. 입력이 없으면(ULog나 원시 표본 없음) 종료 코드 2이고 INFRA로 따로 센다.
- 기록만 하는 것: `ros_missing_in_ulog`, `ros_field_mismatch`, `ulog_only`. `ulog_only`가 0이 아니면 `notes`에 적는다.
- `--repeat`의 `armed_criterion.json`은 `passed`(ROS 기록만)와 `passed_with_ulog`(모든 회의 교차 확인이 끝났고 ULog 기준 위반이 0건)를 둘 다 적고 `ulog_crosscheck`에 합계를 둔다.
