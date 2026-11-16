# tests/sitl

미션 통합 테스트(시나리오 B, C, A, D, F1, F2, F3, F4, T)다. 계약은 `docs/interface.md`에, 판정과 시나리오 규칙은 이 문서의 "시나리오와 판정", "b와 R_home 보정 확인" 절과 `tests/support/sitl_judge.py` 머리말에 있다. 소유는 test-engineer다.

## 실행

```
tests/sitl/run_sitl.sh [--stack k] [--repeat N] [--attach <실행 디렉터리>] [-- pytest 인자...]
```

- 스택은 호스트 wrapper가 `tools/sim_stack.sh up --fleet tests/sitl/fleet.yaml`로 올리고 내린다. `tests/sitl/fleet.yaml`은 sitl 전용 fleet 파일(기체 1을 (6, -3, 0)에 스폰, F2와 F4의 표적 `car_1`)이고 개발용 `config/fleet.yaml`과 따로 둔다.
- 로컬과 CI가 같은 시나리오 목록(`tests/support/sitl_summary.py`의 `SCENARIOS`)을 돈다. 목록에 F1-F4가 있으므로 판정 상수 b와 `R_home`이 정해져 있어야 한다(`tests/support/test_sitl_flight_missions.py`가 단정한다). pytest는 `runner`(ros-ws) 컨테이너 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증만 한다. 검증이 실패하면 skip이 아니라 오류다.
- `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다(`tools/ros_ws.sh build`).
- `--repeat N`은 회마다 down 뒤 콜드 up이다. 첫 실패에서 멈추고 재시도하지 않는다. "로컬 3회 연속 통과"는 같은 commit, 같은 이미지 key에서 `--repeat 3`이 세 회 모두 통과하는 것이다. 실패하면 0부터 다시 센다. `artifacts/sitl_repeat/<시각>-k<k>/`에 `repeat_summary.tsv`(실행 id, commit과 dirty, 이미지 key, 시나리오별 verdict, 시나리오 A 이정표별 ROS 시각 소요, RTF, 벽시계 소요, ARMED 표본 수, 유지 구간 편차 `hold_dev_*_m`, 단계별 종료 코드 `rc_*`)와 `armed_criterion.json`이 남는다.
- `-- -k test_b`처럼 일부 시나리오만 고르면 나머지가 빠지므로 `verdict.json`의 통과 조건(실행 목록의 시나리오 모두 passed)에 걸려 종료 코드 1로 끝난다. 디버깅 용도로만 쓴다. F3은 F2가 남긴 공중 Hold에서 시작하므로 따로 돌릴 수 없다(F2가 바로 앞에 통과하지 않았으면 `PRECONDITION`).
- `--attach DIR`은 올리지도 내리지도 않고 pytest와 수집만 한다(Gazebo GUI 육안 확인, 디버깅). 산출물은 `DIR/sitl-attach-<시각>/`에 쓴다.
- 종료 코드: 0 전체 통과, 1 시나리오나 정지 검사 실패(ULog 교차 확인 실패 포함), 2 사용법, 선행 조건, 스택 올리기(`INFRA_UP`) 실패, ULog 교차 확인의 입력 없음과 판정 불가. ULog 교차 확인 실패는 1, 입력 없음과 판정 불가(파싱 중 예외 포함)는 2다. stdout 마지막 줄은 실행 디렉터리다. 환경변수 `SITL_PYTEST_TIMEOUT`(기본 900 s)이 pytest 전체의 벽시계 상한이다.
- 이 디렉터리의 테스트는 lint job의 pytest(`tests/support`, `tests/tools`)가 수집하지 않는다. 시험 미션 YAML(`tests/sitl/missions/`)의 시간 합산과 판정 상수 대조(`tests/support/test_sitl_flight_missions.py`)는 lint job에서 돈다. 로더(`ros_ws/src/idsim_mission/idsim_mission/mission_yaml.py`)를 저장소 소스 경로에서 읽기 때문이다(`tests/support/sitl_missions.py`).
- `tests/support/test_sitl_constants.py`와 `test_px4_topic_names.py`는 `idsim_interfaces`와 `px4_msgs`가 있어야 돌아서 lint job에서는 건너뛴다. `run_sitl.sh`가 runner 안에서 `tests/sitl`과 함께 돌린다.

## 시나리오와 판정

한 스택에서 B, C, A, D, F1, F2, F3, F4, T 순서로 돈다. 판정 시간은 모두 ROS 시각이다. 판정 입력은 토픽에서만 읽는다(goal의 목표값과 `vehicle_local_position`, `vehicle_status`, `vehicle_land_detected`, `failsafe_flags`, `mission_event`, action의 feedback과 result). 노드가 낸 setpoint는 입력으로 쓰지 않는다. 판정 함수는 `tests/support/sitl_judge.py`(순수 코드)에 있다.

| 시나리오 | 내용 | 판정 필드 |
| --- | --- | --- |
| B | 무효 사례 8개(`tests/support/sitl_missions.py`의 `B_INVALID_CASES`: `[]`, 첫 항목이 아닌 TAKEOFF, `[LAND, GOTO]`, 가운데 RTL, `[RTL, GOTO]`, TRACK_ENTITY의 0 `offset`, 형식이 틀린 `target_id`, 기본값 TRACK_ENTITY 서브메시지)를 순서대로 | 사례마다 result ABORTED와 `REASON_INVALID_MISSION`, `detail`에 사례의 기대 조각(의도한 검사에서 거부됐는가. 문구는 계약이 아니다), 접수와 종료 사건 한 쌍(종료 사건 == result), feedback 0건. 첫 goal부터 끝(마지막 사례 뒤 5 s)까지 한 구간에서 ARMED 표본 없음. 거부가 아닌 결과는 그 사례에서 바로 실패하고 goal 취소와 비상 정리를 한다 |
| C | goal의 `vehicle_id`가 다른 값 | result ABORTED와 `REASON_VEHICLE_ID_MISMATCH`. 사건의 `vehicle_id`는 Executor 자신의 값. feedback 0건. 5 s 동안 ARMED 표본 없음 |
| A | `[TAKEOFF 5 m, LOITER 5 s, LAND]` | SUCCEEDED, `REASON_NONE`, `items_completed` 3. 사건 짝과 result 일치. 이정표 순서(goal 전송, 접수, ARMED, TAKEOFF 시작, 도달, LAND 시작, AUTO_LAND, DISARMED, result)가 테스트 노드 수신 시각으로 줄어들지 않음. LOITER 유지 5 s 이상과 고도 허용 0.5 m. TAKEOFF와 LOITER 동안 `failsafe`가 false이고 `nav_state`가 OFFBOARD. ARMED를 본 뒤의 AUTO_LAND, 그 뒤 DISARMED 3회 연속. OFFBOARD가 아닌 ARMED 표본 0개 |
| D | 도달 뒤 cancel, 이어서 `[LAND]` | cancel 응답 `ERROR_NONE`, CANCELED와 `REASON_NONE`. AUTO_LOITER 3회 연속, 그 뒤 5 s 동안 고도 변화 0.5 m 이하이고 ARMED, `landed` false. `[LAND]` 미션 SUCCEEDED, ARMED 뒤 AUTO_LAND, DISARMED 3회 연속, `landed` true |
| F1 | `missions/f1.yaml`: `[TAKEOFF 5 m, GOTO x 3, LAND]`(한 변 10 m) | 계약 판정: SUCCEEDED, 사건 짝, 항목 순서(feedback의 item_index와 type), ARMED -> AUTO_LAND -> DISARMED 3회, landed. 정답 판정: GOTO 완료마다 t_f의 정답 거리 1.0 m 안(`REACH_MISMATCH`), DISARMED 시점 정답 z와 이륙 직전 정답 z의 차의 절댓값이 0.3 m 안 |
| F2 | `missions/f2.yaml`: `[TAKEOFF, GOTO, TRACK_ENTITY]`(표적 `car_1`, 1-2 m/s) | SUCCEEDED, 항목 순서, 마지막 항목 뒤 AUTO_LOITER 3회와 5 s 동안 ARMED, landed false, 고도 유지(`HOLD_AIRBORNE`). 표적 접근: t_f의 정답 위치와 "보간한 표적 + offset"의 거리 1.0 m + v x L 안, 접근 구간의 표적 이동(`NO_TARGET_MOTION`) |
| F3 | `missions/f3.yaml`: `[GOTO, RTL]`(F2의 Hold에서 공중 시작) | 사전조건 공중 Hold. SUCCEEDED, 항목 순서, ARMED -> AUTO_RTL -> DISARMED 3회, landed. 착륙 수평 위치와 F2 이륙 직전 위치의 거리 R4가 `R_home`(0.20 m) 안 |
| F4 | `missions/f4.yaml`: `[TAKEOFF 5 m, GOTO x 2, TRACK_ENTITY, RTL]` | F1의 도달, F2의 표적 접근, F3의 RTL 착륙 판정(기준점은 F4 자신의 이륙 직전 위치) |
| T | 지상, Executor idle, `offboard_control_mode`(`position=true`) 20 Hz | timestamp가 현재이면 `offboard_control_signal_lost` false, `now - 2 s`이면 true, 다시 현재이면 false. 각 단계 3회 연속(서로 다른 timestamp), 단계마다 대기 상한 5 s. 내내 ARMED 표본 없음 |

- 시나리오마다 사전조건(지상, DISARMED 3회 연속. F3은 공중 Hold)을 단정하고 어긋나면 그 자리에서 `PRECONDITION`으로 실패한다.
- 비행 시나리오(A, D, F1-F4)가 실패하면 정리용 `[LAND]`를 한 번 시도하고(판정에 넣지 않는다) 뒤의 비행 시나리오는 실행하지 않고 `UPSTREAM_FAILED`(실패로 센다)다. 정리도 실패해 T의 사전조건이 맞지 않으면 T는 `PRECONDITION`이다.
- 판정은 계약 판정(계약 토픽과 PX4 토픽)과 정답 판정(SITL 전용 정답 pose `/sim/<vehicle_id>/pose`)으로 나뉜다. 정답 pose가 없으면 `ORACLE_ABSENT`, t_f를 감싸는 정답 표본 간격이 0.1 s를 넘으면 `ORACLE_STALE`이다. t_f는 다음 항목의 첫 feedback stamp이고, 공중 종료로 가는 마지막 setpoint 항목(F2의 TRACK_ENTITY)은 그 항목에서 거리를 실은 마지막 feedback 뒤의 첫 거리 없는 feedback stamp다. 노드는 그 완료 tick에 feedback을 바로 낸다(노드 테스트 `ExecutorNodeTest.FeedbackIsPublishedOnTheTickTheLastSetpointItemCompletes`). trace의 `flight_window`에 마지막 항목 t_f 앞뒤 feedback 간격(`last_item_feedback_gaps`)을 남긴다. gate의 `/clock` 정렬 중앙값과 최대는 `gate_ok` 사건과 `verdict.json` gate에 남는다. 판정 상수와 근거는 `tests/support/sitl_judge.py` 머리말에 있다.
- gate는 첫 goal 전에 정답 pose와 표적의 발행자와 첫 표본을 확인하고, `/targets/<id>/state` 발행자 QoS를 계약 상태 행(RELIABLE, VOLATILE)과 대조하며(다르면 `QOS_MISMATCH`), Executor 파라미터 `target_fresh_age`를 판정 상수 L의 전제(0.1 s)와 대조한다. 정답 pose, 표적, `target_fresh_age`의 문제는 그것이 필요한 F 시나리오에서 실패로 드러난다.
- 도달의 입력은 goal 직전의 `vehicle_local_position` z(`z_valid`)와 goal의 높이와 허용 오차다.
- gate(모든 시나리오 앞): `/clock` 수신, `mission_event` 발행자와 PX4 토픽 발행자, action server 준비, 기대 sysid의 `vehicle_status`, `/clock` 정렬(노드 시각 - `vehicle_status.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s). `mission_event` 구독은 action client보다 먼저 같은 node에서 만든다(`tests/support/mission_client.py`).
- 순서의 이유: 지상 거부 사례(B, C)는 비행 전에 둬서 비행 실패가 사전조건을 깨지 않게 한다. B의 ARMED 없음 단정은 한 구간에 한 번만 걸어 사례 수에 비례해 늘지 않는다. F2의 끝(공중)과 F3의 시작(공중)을 맞물려 이착륙 한 번을 줄이고, F4는 F3이 남긴 지상 DISARMED에서 시작한다. T는 지상 시나리오라 맨 뒤다. F1-F3은 경계 상황(공중 종료, 공중 시작)을 따로 보고 roadmap 목표의 미션 하나(이륙부터 착륙까지)는 F4가 그대로 돈다.
- 시간 규칙: 시나리오마다 항목 `timeout` 합 + 마진이 비행당 상한(ROS 시각 3분)을 넘지 않음을 `test_sitl_flight_missions.py`가 단정한다. RTF가 1 미만이면 `SITL_PYTEST_TIMEOUT`(벽시계)은 올려도 되고 판정의 ROS 시각 한도는 올리지 않는다. CI `sitl` job의 목표는 15분이다. 넘으면 겹치는 비행 구간(F1과 F4의 순회처럼 같은 판정을 두 비행이 보는 부분) -> 순회 waypoint 수 -> Hold 유지 시간 순으로 줄인다. 경계 상황을 보는 F2의 공중 종료와 F3의 공중 시작은 빼지 않는다. 그래도 넘으면 측정값과 함께 사용자에게 올린다. 판정 기준을 느슨하게 해서 줄이지 않는다.
- TRACK_ENTITY의 `timeout`은 표적 위상과 무관하게 잡는다. `loop` 표적의 위상은 앞 시나리오의 소요 시간에 따라 달라지므로, 항목 시작점(직전 GOTO 목표)에서 loop 궤적 위 가장 먼 점까지의 거리를 따라잡는 시간에 완료 마진을 더한 값으로 둔다. 같은 테스트가 `timeout`이 `tests/sitl/fleet.yaml`의 궤적에서 계산한 최원점 기준 값 이상임을 단정한다. 접근 속도와 마진의 값은 [추정]이고 근거는 미션 YAML 주석에 있다.
- verdict 분류: `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_SLOW`, `CLOCK_ABSENT`, `CLOCK_BACKWARD`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`, `UPSTREAM_FAILED`, `ORACLE_ABSENT`, `ORACLE_STALE`, `REACH_MISMATCH`, `NO_TARGET_MOTION`, `QOS_MISMATCH`. 대기마다 `wall_cap = ROS 시각 timeout x 3 + 10 s`를 두고, 넘으면 `/clock`이 벽시계 5 s 동안 진행하지 않았는지로 `CLOCK_STALLED`와 `CLOCK_SLOW`를 가른다. 배수를 올려 통과시키지 않는다.

## 산출물

`artifacts/runs/<실행 id>/` 아래. 실패하면 이 디렉터리 전체를, 성공하면 `sitl/junit.xml`, `sitl/trace.jsonl`, `sitl/summary.md`, `sitl/trace_ulog.json`을 CI가 올린다.

- `compose.yaml`, `stack.json`, `params/`, `px4-N/log/*.ulg`, `ros_log/`
- `sitl/`: `junit.xml`, `trace.jsonl`(gate, goal, 사건 판정, 이정표. 비행 시나리오는 `reach`, `track`(TRACK_ENTITY 완료의 도달 기록, 추종 오차, 신선하지 않은 tick), `landing`(R4, RTL 소요), `r1`, `hold_end`(F2), `air_start`(F3), `flight_window`), `verdict.json`(gate와 시나리오별 결과, RTF, 시나리오 A의 ARMED 기록, `recorded_only`), `trace_ulog.json`(ULog의 TRACK_ENTITY 구간 속도 feedforward와 z, F3 공중 시작의 DO_SET_MODE와 D. 기록 전용), `summary.md`, `steps.tsv`(단계별 벽시계 초, 서비스 종료 상태 `stop_exit_*`, ULog 끝 경계 `ulog`, 회차별 종료 코드 `rc_*` 줄), `raw_status_A.jsonl`, `raw_status_D.jsonl`, `armed_a.json`, `ps_before_stop.jsonl`(stop 전 서비스 상태), `logs/<서비스>.log`, `health_<서비스>.txt`(실패한 회나 unhealthy 서비스만), `crosscheck_a.json`

`recorded_only`의 이름: R1 EKF 원점과 기대 스폰 GPS의 차, R2 도달 사건(GOTO, TRACK_ENTITY 완료)의 정답 거리와 초과량(`d3`, `s`, `s_track` 등), R3 표적 age와 간격, `/clock` 간격, 상태 지연, 신선하지 않은 tick, 추종 오차, R4 RTL 착륙 수평 위치와 기준점의 거리. 판정에 쓰지 않는다.

## b와 R_home 보정 확인

`tests/sitl/calibrate.py <회차 디렉터리 또는 실행 디렉터리>... [--b 0.5] [--min-boots 30] [--out 파일]`이(`--min-boots`는 부팅 수 하한) `--repeat`의 회차마다 `trace.jsonl`(`reach`, `track`, `landing`)과 `verdict.json`을 읽는다(계산은 `tests/support/calibration.py`, 상수와 근거는 `tests/support/sitl_judge.py` 머리말). 통과한 실행만 부팅으로 센다. b는 상수로 받고(사용자 결정) 확인 조건은 GOTO s와 s_track 표본 전부가 b 이하인 것이다. 정규 허용한계(mean + k x std)와 Shapiro-Wilk는 기록으로만 낸다. 도달 사건이 모두 판정 반경 안인지, `R_home`의 Rayleigh 허용한계와 판정 상수 대조, 기록 전용인 t_f 수평 속도와 d_h, s의 관계도 낸다. 회차 디렉터리를 주면 그 안에 `calibration.json`을 쓴다. 종료 코드는 0 충족, 1 미충족, 2 입력 오류다.

- b는 0.5 m로 고정한다. 시험 미션 반경의 하한 0.5 m와 판정 반경 1.0 m 사이의 최대 여유이고 표본에서 추정한 값이 아니다. 도달 사건마다 부호 있는 초과량 `s = d_oracle(t_f) - acceptance_radius_m`을 재고(0으로 자르지 않는다), TRACK_ENTITY 완료는 표적 지연 항 때문에 분포가 달라 `s_track = d_oracle(t_f) - acceptance_radius_m - v x L`로 따로 잰다.
- 확인 조건: 부팅 30회 이상이고 `s`와 `s_track` 표본 전부가 b 이하여야 b를 적는다. 하나라도 넘거나 부팅이 모자라면 상수를 적지 않고 보정 결과(분포, `d_h`, `d_v`, 도달 속도, R1)를 들고 architect와 사용자에게 올린다. 반경을 줄이거나 판정을 넓혀서 맞추지 않는다. GOTO나 TRACK_ENTITY 항목, 표적 속도, 변 길이를 바꾸면 도달 속도가 달라지므로 보정을 다시 한다.
- 적은 뒤 통과와 실패를 보고 b를 바꾸지 않는다. CI에서 판정 반경을 넘는 사건이 나오면 b를 올리지 않고 architect에게 올린다. 먼저 시각 정렬을 본다: feedback stamp(`t_f`)와 완료 판정에 쓴 위치 표본의 시각이 어긋나 `s`에 도달 속도에 비례하는 항이 실리는지([추정]). 한 달에 2회를 넘게 나오면 b 0.5 m가 맞지 않는 것으로 보고 사용자에게 올린다. b는 0.5 m보다 클 수 없으므로(그 아래 반경에서는 Executor가 waypoint에서 정체할 위험이 커진다 [추정]) 올리는 길이 없다.
- `R_home`은 b와 따로 정한다. RTL 착륙점(PX4 home)과 기준점이 같은 물리 위치를 가리켜 사슬 오차가 없기 때문이다. RTL 착륙 수평 위치와 기준점의 거리 R4에 Rayleigh 허용한계를 쓴다: `sigma_hat^2 = mean(R4^2) / 2`, `R_home = ceil_0.05(q x f x sigma_hat)`, `q = sqrt(-2 ln(0.005 / m_home))`, `f = sqrt(2n / chi2_0.05(2n))`(n은 부팅 수, m_home은 RTL 사건 수). 재보정 조건: 시나리오의 RTL 사건 수가 바뀔 때(`test_sitl_flight_missions.py`가 깨져 알린다). 표본 최댓값이 허용한계를 넘으면 모형을 기각하고 상수를 정하지 않고 올린다. `R_home`이 1 m를 넘어도 올린다. 착륙 위치 평균 벡터가 2 표준오차보다 크면 기록한다(편향은 RMS에 들어가 보수적이라 기각 사유가 아니다).

유지 구간(A의 LOITER, D의 취소 뒤 유지)의 기준 고도로부터의 최대 편차는 통과한 회에도 `trace.jsonl`(`hold_deviation`), `verdict.json`(`hold_deviation_m`), `repeat_summary.tsv`(`hold_dev_*_m`)에 남는다. 항목별 임계값(A의 LOITER 0.4 m, D의 유지 0.25 m)을 넘으면 `summary.md`와 `armed_criterion.json`의 `hold_deviation_notes`에 note가 붙는다(판정 상수 0.5 m 재검토의 근거. 임계값은 `tests/support/sitl_summary.py`의 `HOLD_DEV_NOTE_M`).

## 시나리오 A의 ARMED 표본 기록

`vehicle_status` 원시 표본을 KEEP_ALL 구독의 별도 기록기(`px4_raw.Px4Raw`)로 받는다. 판정 probe의 tick 모델과 무관하다. `raw_status_A.jsonl`의 표본마다 `timestamp`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`, 수신 ROS 시각이 있다. goal 전송부터 TAKEOFF 시작(feedback `PHASE_EXECUTING`의 stamp)까지 ARMED 표본 수와 OFFBOARD가 아닌 ARMED 표본 수를 PX4 `timestamp` 축으로 세어 `armed_a.json`과 `verdict.json`에 적는다. OFFBOARD가 아닌 ARMED 표본이 한 건이라도 나오면 시나리오 A는 실패하고 architect에게 올린다. 부류별 기준(ARMED 3회 확인까지 간 실행 10회 이상에서 0개)의 판정은 `measure_judge.judge_armed_criterion`이고 `--repeat 10`의 `armed_criterion.json`에 나온다. 10회 중 0건은 실패율 95% 상한이 약 26%라는 뜻이다.

### ULog 교차 확인

값의 정본은 PX4이므로 실행이 끝나면 `crosscheck_a.py <실행 디렉터리>`가 `raw_status_A.jsonl`을 ULog의 `vehicle_status`와 대조한다(`measure_check.check_row` 재사용). 위반 구간은 goal 전송부터 TAKEOFF 시작 feedback의 stamp 뒤 0.5 s까지이고 비행 구간은 그 뒤 LAND 시작 feedback까지다. 결과는 `sitl/crosscheck_a.json`이다.

- 판정: ULog 기준 OFFBOARD가 아닌 ARMED 표본이 위반 구간(`ulog_armed_non_offboard`)이나 비행 구간(`ulog_flight_armed_non_offboard`)에 있으면 종료 코드 1이고 `run_sitl.sh`가 그 실행을 실패로 센다. 입력이 없으면(ULog나 원시 표본 없음) 종료 코드 2이고 INFRA로 따로 센다.
- 기록만 하는 것: `ros_missing_in_ulog`, `ros_field_mismatch`, `ulog_only`. `ulog_only`가 0이 아니면 `notes`에 적는다.
- `--repeat`의 `armed_criterion.json`은 `passed`(ROS 기록만)와 `passed_with_ulog`(모든 회의 교차 확인이 끝났고 ULog 기준 위반이 0건)를 둘 다 적고 `ulog_crosscheck`에 합계를 둔다.
