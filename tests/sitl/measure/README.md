# PX4 재실측 측정 스크립트

`docs-for-agent/plan-1a-6-idsim-mission/decisions.md` 넘김 목록의 px4-engineer 행 중 재실측 (2), (3), (5)와, OFFBOARD가 아닌 ARMED 표본 기록(`armed` 항목)을 돌리는 도구다. 소유는 test-engineer, 절차의 필수 승인자는 px4-engineer다.

이 측정은 Executor 없이 PX4에 직접 명령을 보낸다(PX4 직접 부류). 시나리오 A(Executor 경유)의 대응이나 대체가 아니다. 통과해도 P4 머지 조건은 Executor 경유 부류의 통과가 따로 필요하다.

## 실행

```
tests/sitl/measure/run_measure.sh [--stack 7] [--attempts N] [--keep] item2|item3|item5|armed|all
```

- 스택 번호 기본값은 7(실험용). 0은 사용자 스택이라 거부한다.
- `item2` 재실측 (2), `item3` 재실측 (3), `item5` 재실측 (5), `armed` PX4 직접 명령의 arm -> ARMED 3회 -> 이륙 -> 착륙 구간 기록.
- 기본 시도 수: item2 3, item3 3, item5 10, armed 10. 통과 기준의 최소 시도 수와 같다.
- `all`은 item3, item5, item2, armed 순으로 한 스택에서 돈다. 같은 item을 두 번 주면 거부하고, 기존 기록 파일이 있으면 덮어쓰지 않고 거부한다.
- `--keep`을 주면 끝나도 스택을 내리지 않는다. 마지막 시도 뒤 기체가 Hold 상태로 armed인 채 남아 있을 수 있다(2b, (3)이 Hold로 끝난 경우).
- 추가 인자: `MEASURE_ARGS="--observe-s 60 --hold-observe-s 60 --delays 0,0.05,0.1,0.15,0.2 --takeoff-alt 5 --tail-s 3 --settle-s 3"`. `--delays`는 0-0.2 s 범위만, `--tail-s`는 0보다 커야 한다.
- 이 스크립트는 `tools/sim_stack.sh up`으로 스택을 올린다. P4 뒤에는 `up`이 Executor도 띄워 setpoint가 섞이므로 `sim_stack.sh up --infra-only`로 바꿔야 한다.

## 종료 코드와 verdict

- 0: 모든 시도 PASS이고 시도 수 충분.
- 1: 기준과 다른 관측(verdict `FAIL`, ARMED 위반). 문서의 기대가 반증됐다는 뜻이며 PX4 결함이라는 뜻이 아니다. 2보다 앞선다.
- 2: 기계가 판정하지 않음. `COND_NOT_REACHED`(2b에서 `landed`가 true에 닿지 못함), `HOLD_END`((3)이 Hold로 끝남), `INCONCLUSIVE`(관찰 60 s 미만, (5)의 arm 수락 증거 미확인), `WINDOW_MISSED`, `PRECONDITION`, `ERROR`, `CLOCK_STALLED`, 시도 수 부족, 인프라, 처리하지 못한 예외.

## 구조

| 파일 | 역할 |
| --- | --- |
| `run_measure.sh` | 호스트. 스택 올리기, runner에서 `measure.py` 실행, 스택 멈추기, ULog 교차 확인, 내리기 |
| `measure.py` | runner 안. 시도를 돌리고 시도마다 판정 |
| `crosscheck.py` | 호스트. 기록을 ULog의 `vehicle_status`와 대조하고 (5)의 arm 수락 증거를 확정하고 ARMED 기준을 부류별로 합산 |
| `tests/support/measure_judge.py` | 판정 로직(순수 코드)과 정리 모델 `CleanupModel`. 단위 테스트 `test_measure_judge.py` |
| `tests/support/measure_check.py` | ULog 대조, ARMED 합산, 종료 코드 집계(순수 코드). 단위 테스트 `test_measure_check.py` |
| `tests/support/px4_raw.py` | KEEP_ALL 구독 기록기(구독 전용) |
| `tests/support/px4_measure_pub.py` | 측정 전용 발행자(`measure_only=True` 필수). 시나리오는 가져가지 않는다 |
| `tests/support/ulog_min.py` | ULog에서 한 토픽과 logged message를 읽는 최소 parser(이미지에 pyulog가 없다) |

### 정리 모델이 흉내 내는 것

`CleanupModel`은 decisions.md M3, M5, M6의 일부만 옮긴 측정용 모델이고 core를 호출하지 않는다.

- 흉내 내는 것: 매 step 최신 `landed`로 지상(G)/공중(A) 분기를 다시 고름, 분기에 들어갈 때마다(G -> A -> G 포함) 타임아웃 기준 시각과 확인 계수와 첫 전송 기준을 새로 잡고 명령을 새로 보냄, 지상은 강제가 아닌 disarm 재전송과 DISARMED 3회 연속, 공중은 Hold 재전송과 AUTO_LOITER 첫 관측에서 발행 중단 후 3회 연속에서 종료, 분기 타임아웃과 전체 상한 12 s, M6의 한 step 순서(공중 DISARMED, 정리할 것 없음, 상한, 분기 실행).
- 흉내 내지 않는 것: 상태 끊김(LINK_LOST), ack 거부 때의 Land 경로, Hold 실패 뒤 공중 재진입, 상한 tick에서의 reason과 명령 선택, 식별 불일치 종료. 입력은 tick이 아니라 약 2 ms polling이다.
- 그래서 근거 범위는 PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, `landed` 전환, 상승)이다. 정리 총 소요 9 s 기준은 이 모델의 소요이고 core의 소요를 보증하지 않는다.
- 모델의 타임아웃 상수 3, 3, 12, 0.5 s는 `idsim_mission` 노드 파라미터 기본값(`core/config.hpp`)의 사본이다. 자동으로 동기화되지 않는다.

## 기록

`artifacts/runs/<실행 id>/measure/` 아래.

- `measure_<item>.jsonl` 시도마다 한 줄. 필드: `run_id`, `commit`, `dirty`, `images`, `image_keys`, `attempt`, `item`(2a, 2b, 3, 5, armed), `class`(px4_direct), `args`(실행 인자), `injection`(조건과 trigger, (5)는 명목 지연과 실제 지연), `verdict`/`result`, `reasons`, `ros_start_us`, `ros_end_us`, `ros_elapsed_s`, `wall_elapsed_s`, `exit_code`(0 PASS, 1 FAIL, 2 그 밖), `ulog`, `facts`. 측정되지 않은 값은 0이나 false가 아니라 `null`이다.
- `raw_<item>.jsonl` 시도마다 `vehicle_status`(`timestamp`, 받은 ROS 시각, 같은 시점의 `/clock`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`), `vehicle_land_detected`, 위치, ack(`timestamp`, `result`, `result_param1/2`, `from_external`, `target_component` 포함), 명령 전송의 원시 표본. 구독은 BEST_EFFORT이므로 "하나도 버리지 않는다"는 노드가 받은 표본에 대해서만 참이다. 전송 중 유실은 `crosscheck.py`의 ULog 대조(`ulog_only`)로 본다.
- `summary_<item>.txt` 머리에 판정 뜻, 보증 범위, 실행 인자, 통과 기준(실행 전에 기록), 아래에 결과와 항목별 요약(2b 회별 결과, 분기 순서별 회수, (5)의 ARMED 표본과 지연값별 유효 시도).
- `distribution_<item>.json` 모든 `vehicle_status` 표본의 `timestamp - 받은 ROS 시각`, `timestamp - /clock`의 부호 있는 분포와, 명령 전송 뒤 처음 받은 표본의 `timestamp - Px4Timestamp` 분포.
- `crosscheck_<item>.json`, `armed_criterion.json` ULog 교차 확인과 ARMED 기준의 부류별 합산(`classes`: `px4_direct`, `scenario_a`).
- `stop_exit.txt` `compose stop -t 15` 뒤 서비스별 종료 코드(px4의 137은 KILL, ULog가 닫히지 않았을 수 있다).

## 규칙

- 실패한 시도를 기록에서 빼지 않고 재시도하지 않는다. 판정을 느슨하게 바꾸지 않는다.
- 타임아웃과 지연은 `/clock` 기준이다. 벽시계는 `/clock`이 멈췄는지 보는 데만 쓴다.
- trigger는 sleep이 아니라 표본 이벤트다(첫 ARMED 표본, `landed` 표본, Hold 관측). 예외는 (5)의 주입 지연으로, arm 전송 뒤 sim 시간 0-0.2 s를 재는 입력 변수이며 명목 값과 실제 값을 기록한다.
- 10회 중 0건은 실패율의 95% 상한이 약 26%라는 뜻이다. 3회는 상한이 약 100%다. "10/10 통과"를 "플래키 없음"으로 쓰지 않는다.
- 정리 총 소요 9 s 미만을 넘는 실행이 있으면 상한을 올리지 않고 architect에게 올린다.
- (5)의 arm 수락 증거는 ROS ack가 아니다(arm과 disarm이 같은 command 400이고 ack에 원 명령 필드가 없다). 증거 A는 arm 전송 뒤 timestamp의 ARMED 표본(ROS 또는 ULog), 증거 B는 ULog의 `[commander] Armed by external command`다. 최종 PASS는 `crosscheck.py` 뒤에만 선언한다.
