# Phase 1a 6번 작업 설계 토론: 결정

작성 2026-11-11, architect. 상태: 확정본이다(초안 `decisions-draft.md`를 대체한다). 여섯 담당자의 의견서(`opinion-px4.md`, `opinion-ros2.md`, `opinion-test.md`, `opinion-devops.md`, `opinion-sim.md`, `opinion-logging.md`)와 각 의견서 끝의 "재질문 답(2026-11-11)"을 반영했다. reviewer의 근거 검증(결론 조건부, 필수 M1-M6, 권고 R1-R7)도 반영했다(끝의 "reviewer 검증 반영"). 추가 실험(E1-E5)의 결과로 2번의 취소 분기와 K3-K5, 사용자 5를 다시 정했다("추가 실험" 절의 "결과와 처리"). 새 취소 분기에 대한 ops-service-engineer의 검토는 조건부 승인으로 끝났고 조건 셋(C1-C3)을 모두 받았다("ops 검토" 절의 "ops의 답과 처리", 2번의 "ops 검토로 더한 규칙", K13-K18). 사용자 결정 9항목은 2026-11-11에 모두 권고안으로 확정됐다("사용자 결정 항목" 절 끝의 "결정 결과"). 사용자 결정에 걸린 줄은 "사용자 N"으로 표시했다. 이 문서로 `docs/`, `progress.md`, 5단계 `decisions.md`, `.action` 주석을 고치지 않는다(작업 단위 H에서 고친다).

표기
- [실측 혼자]: 재질문 라운드의 값이다. 스택을 한 번에 한 담당자만 올렸다. 조건은 아래 "측정 조건".
- [실측 경합]: 첫 라운드의 값이다. 여섯 명이 같은 시간에 스택을 올렸다(load average 6-19, 4 vCPU). 시간 값은 결정의 근거로 쓰지 않고, PX4 timestamp(sim 시간) 차이로 잰 값과 동작의 유무(5/5, 0/5)만 쓴다.
- [소스]: PX4 v1.17.0 원문. [추정]: 실측이 없다. [미측정]: 잴 수 있지만 재지 않았다.
- "사용자 N": 범위, 비용, 정책이라 사용자가 정한다("사용자 결정 항목"의 번호).
- 넘김 항목 번호(A1, C27 등)는 `README.md`, 문항 번호(P4, R3 등)는 `questions.md`의 것이다.

## 측정 조건

| 담당 | 재질문 라운드의 조건 |
| --- | --- |
| px4 | 스택 k=1 하나. load1 1.39-4.71(5 s 간격 83표본). 스택이 아닌 ros-ws 컨테이너 하나(CPU 약 13%)와 다른 담당자의 단발 컨테이너가 오갔다. 회차마다 스택을 새로 올려 3회. 시간 값은 PX4 timestamp와 ROS 시각 축 |
| ros2 | 스택 없음. ros-ws 이미지에서 `--network none`, 도메인 97, C++ lifecycle 탐침. 시간 값은 1-3회 |
| sim | 스택 k=5 하나. 단독 602 s(load1 평균 4.44, 스택과 탐침 자신의 부하), 이어서 busy loop 4개의 부하 299 s(load1 평균 7.40). 부하는 CPU만 누른다(디스크와 메모리 압박 없음) |
| devops | 스택 k=4 하나. load1 0.4-2.6. Docker 29.1.3, Compose v5.5.1. 변형별 3회 |
| test | 스택 k=3 하나. 혼자 3회(r1-r3), 부하 2회(r4는 부하가 약해 참고, r5가 부하 값) |
| logging | 스택 k=6 하나를 순서대로 6회. load1 0.35-2.50. 비행은 `px4-commander takeoff`(2.5 m)와 `land` |

- "혼자"는 스택이 하나라는 뜻이다. 스택과 탐침 자신의 부하는 들어 있다.
- 미측정으로 남은 것: GitHub runner에서의 기동 시간, RTF, 이미지 받는 시간. 실제 Executor(탐침이 아닌)로 잰 값 전부.

## 충돌별 정리와 결정

### 1. setpoint timer와 타임아웃의 시계 (R1, P9, S1, T6)

근거
- ros2 R1 [실측 경합, 동작]: `/clock`이 멈추면 ROS 시각 timer는 한 번도 발화하지 않고, 재개 뒤 밀린 발화를 몰아 하지 않는다. wall timer는 멈춘 동안 같은 `Px4Timestamp`를 20 Hz로 계속 낸다.
- sim [실측 혼자, 단독 602 s / 부하 299 s]: bridge 뒤 `/clock` 도착 간격 최대 25.9 ms / 21.1 ms, p99 5.47 / 6.98 ms. sim 증가는 모든 메시지에서 4 ms(빠짐과 중복 없음). 20 ms를 넘은 끊김은 합쳐 2회이고 원인이 갈렸다. 단독의 25.9 ms는 전달 지연이다(Gazebo 발행 간격은 4.0 ms 그대로, 전달 지연 22.8 ms). 부하의 21.1 ms는 Gazebo 스텝 지연이다(발행 간격 17.1 ms. lockstep이라 PX4 시각도 같이 늦는다). ROS 시각 50 ms timer의 벽시계 간격 최대 67.7 / 70.3 ms, sim 간격 44-56 ms. setpoint timestamp의 묵음 최대 7.6 / 10.5 ms. `offboard_control_signal_lost` 참 0/1115, 0/554. RTF 0.9994 / 0.9981.
- px4 P9 [실측, sim 시간 축]: timestamp를 0.5 s, 0.9 s 묵게 보내면 10 s 동안 손실 없음(각 5/5). 1.1 s, 2.0 s는 매번 0.05-0.14 s 안에 손실 판정과 `nav_state` 18. [소스] 판정은 `now < timestamp + COM_OF_LOSS_T`이고 개수와 주기 조건은 없다.
- test T6 [실측]: `/clock`이 끊겼을 때 벽시계 timer(굳은 timestamp 반복)는 약 1 s 뒤, ROS 시각 timer(발행 0건)는 1.04 s 뒤 failsafe. `vehicle_status`로는 두 경우가 구별되지 않는다.
- 정정: 초안의 "끊김 최대 106 ms"는 [실측 경합] 1회이고 혼자와 CPU 부하 조건에서 재현되지 않았다. 그때 함께 돈 이미지 빌드의 디스크와 메모리 압박이 원인이라는 것은 [추정]이다. 초안의 "수신 지연 최대 0.176 s"는 수신 지연이 아니다(10번).

결정
- 20 Hz setpoint timer는 ROS 시각 timer다. 항목 `timeout`, Hold 확인, 단계별 타임아웃은 그 timer의 tick 안에서 `now()`와 시작 시각을 비교해 잰다(일회성 timer를 따로 두지 않는다).
- 이유: (1) 어느 시계든 `/clock` 경로가 1 s 넘게 끊기면 PX4가 failsafe로 간다는 결과는 같다. (2) Gazebo가 멈추거나 늦으면 PX4 시각도 같이 가므로 ROS 시각 timer만 PX4의 판정 시각과 같이 쉰다. (3) wall timer는 굳은 timestamp를 반복해 내는 경로를 만든다. (4) 여유: 끊김 최대 25.9 ms와 묵음 최대 10.5 ms는 손실 경계(0.9 s 넘게 묵어야 한다)의 1/35 이하다.
- 신선도와 타임아웃은 메시지를 받은 때의 ROS 시각으로 잰다. 메시지의 `timestamp`로 재지 않는다(상태 전이에서 나가는 `vehicle_status`의 `timestamp`는 수신 시각보다 152-196 ms 앞선다. 10번).
- ROS 시각의 역행(Gazebo 재기동으로 `/clock`이 뒤로 간다): tick이 "`now()`가 앞 tick의 값보다 작다"를 보면 수신 시각 기록을 모두 버리고(상태를 미수신으로 본다) 실행 중 goal은 ABORTED, LINK_LOST(`detail`에 원인)로 끝내며, 명령과 setpoint를 멈추고 스스로 deactivate해 재시도 loop로 돌아간다(5번의 불일치와 같은 경로). 경과 시간이 음수인 것을 "신선하다"로 읽지 않는다. 판정은 상태기의 입력(ROS 시각 ns)만 쓰므로 단위 테스트로 덮는다. ROS 시각 timer가 역행 뒤 어떻게 발화하는지는 [미측정]이고 작업 단위 D에서 ros2가 원형으로 확인한다.
- `/clock` 정지의 감지는 1 Hz wall timer 하나가 "ROS 시각이 벽시계 5 s 동안 늘지 않음"을 경고 로그로만 남긴다. goal 결과를 바꾸지 않는다. 이 wall timer(5번의 activate 재시도, 표식 갱신과 같은 timer다)는 `docs/architecture.md`의 "판정은 ROS 시각" 원칙의 예외다. 판정과 goal 결과에 쓰지 않는다는 조건과 함께 문서에 적는다(문서 반영 목록).
- clock thread 옵션은 기본(켬)을 유지한다. 전이 callback 안에서 기다리지 않는다(5번).
- `sitl` 판정 JSON에 그 실행의 `/clock` 벽시계 도착 간격 최대값을 진단 값으로 남긴다(판정에는 쓰지 않는다).
- 다시 여는 조건: runner나 다른 호스트에서 `/clock` 도착 끊김이 0.5 s를 넘는 일이 관측된다.

### 2. Offboard 밖의 setpoint 발행과 취소 규칙 (px4 1절, P4, P5, P6, C27)

근거
- px4 [소스]: `/fmu/in/trajectory_setpoint`는 uORB `trajectory_setpoint`로 그대로 들어가고, Hold와 Land에서는 FlightModeManager가 같은 토픽을 낸다. mc_pos_control과 land detector는 발행자를 가리지 않는다.
- px4 [실측]: LAND 명령 뒤 setpoint를 계속 내면 30 s 동안 `landed`가 참이 되지 않고 armed로 땅에 머문다(5/5). 끊으면 약 3.0 s 뒤 자동 disarm. failsafe Land(1회)와 Descend(1회)에서도 같다.
- px4 [실측]: failsafe Land 중 setpoint가 다시 신선해지면 명령 없이 Offboard로 돌아간다(5/5, 0.036-0.064 s).
- px4 [실측]: Offboard 호버 중 Hold는 5/5 첫 송신 ACCEPTED, `nav_state` 4까지 0.020-0.032 s. Hold 뒤 setpoint를 끊어도 8 s 동안 Hold 유지(5/5). failsafe Land 중 Hold도 받아들여져 하강이 멈춘다(5/5). 위치 무효(Descend)에서는 Hold가 모두 TEMPORARILY_REJECTED(1회).
- px4 [실측 혼자, 각 3회] 자기 NAV_LAND 하강 중(`nav_state` 18, `failsafe` 거짓)의 Hold.
  - 높이 2.49 m 통과 때: 3/3 ACCEPTED(1회 송신), `nav_state` 4까지 20-24 ms. 0.26-0.28 m 더 내려갔다가 돌아와 5 s 뒤 2.42-2.44 m. 착지 판정 신호는 모두 거짓, armed 유지. 그 뒤 NAV_LAND를 다시 보내면 정상 착지와 자동 disarm(3/3).
  - `ground_contact` 참, `landed` 거짓일 때: 3/3 ACCEPTED, `nav_state` 4까지 24-28 ms. 0.33-0.35 s에 `maybe_landed`, 0.67-0.69 s에 `landed`가 섰다가 1.47-1.49 s에 셋 다 거짓으로 돌아간다. 10 s 동안 자동 disarm 없음, `nav_state` 4, armed로 지면에 남는다. 그 뒤 NAV_LAND를 보내면 `landed`까지 1.42 s, disarm까지 3.43 s(3/3).
  - `landed`가 섰다가 풀린 경로는 [추정]이다(ULog의 추력 setpoint를 보지 않았다).
- px4 [실측 혼자, 3/3] 취소로 Hold가 되고 setpoint가 끊긴 뒤의 상태: `nav_state` 4, `arming_state` 2, `failsafe` 거짓, `pre_flight_checks_pass`, `xy_valid`, `z_valid` 참, `landed` 거짓, `failsafe_flags.offboard_control_signal_lost` 참. 그 상태에서 NAV_LAND(setpoint 없음, Offboard 없음): 3/3 첫 송신 ACCEPTED, `nav_state` 18까지 20-24 ms, 5 m에서 `landed`까지 9.15-9.23 s, disarm까지 11.16-11.24 s.
- 반대 근거는 없다. 5단계 쟁점 9의 "setpoint 발행을 유지한 채 Hold"는 Hold 확인 전까지만 맞다.

결정: setpoint 발행 규칙(Executor 설계 노트와 단위 테스트의 대상)
- goal이 없으면 Executor는 /fmu/in에 아무것도 내지 않는다(active 상태 포함).
- 발행 시작은 PREPARING의 한 곳이다(아래 PREPARING 순서 5). 첫 항목이 모드 명령 항목인 미션(1a에서는 `[LAND]`)은 goal 내내 setpoint를 내지 않는다.
- 발행 중단은 다음 중 먼저 오는 것이고, 같은 goal 안에서 다시 시작하지 않는다.
  1. Offboard에 들어간 뒤 `nav_state`가 14가 아닌 것을 확인(원인 무관: failsafe, 외부 모드 변경, 자기 명령).
  2. Hold 명령의 확인(ack ACCEPTED와 `nav_state` 4).
  3. Land 명령의 송신(취소 분기의 TAKEOFF 줄, disarm 거부 줄, LOITER의 방어 줄, Hold 확인 실패) 또는 확인(LAND 항목. ack ACCEPTED 또는 `nav_state` 18).
  4. 지상 취소의 disarm 확인(`arming_state` 1).
  5. LINK_LOST 판정.
  6. goal의 종료 전부.
- 모드 명령 항목 뒤에 setpoint 항목이 오는 미션의 Offboard 재진입은 1b에서 정한다. 1a 노드는 그런 순서를 받지 않는다(아래 "1a 노드가 받는 항목 순서").

결정: 취소 분기(5단계 쟁점 9의 잠정 규칙을 대체. 추가 실험 E1-E5의 결과로 2026-11-11에 다시 정했다. 정책이 바뀌는 줄은 사용자 5. ops-service-engineer가 조건부로 승인했고 조건은 아래 "ops 검토로 더한 규칙"에 넣었다). 위에서부터 먼저 맞는 줄을 쓴다.

가르는 기준은 PX4의 착지 판정 신호가 아니라 Executor 자신이 아는 것(실행 중인 항목과 그 단계)이다. 세 신호는 `landed` 참(지상)과 LOITER 줄의 방어 검사에만 쓴다.

| 취소 시점(Executor의 단계와 상태) | 판정 근거 | Executor 동작 | GoalStatus, `reason` | 근거 회차 |
| --- | --- | --- | --- | --- |
| 상태 미수신 | `vehicle_status`가 LINK_LOST 임계를 넘김 | 명령 없음, setpoint 중단 | ABORTED, LINK_LOST | 바뀌지 않음(5단계 쟁점 9) |
| failsafe 진행 중 | `failsafe` 참 | 모드 명령을 보내지 않는다. setpoint는 이미 멈춰 있다 | ABORTED, FAILSAFE | px4 P4. Hold는 받아들여지지만(5/5) 보내지 않는다(사용자 5의 (2)) |
| 지상, disarm(PREPARING의 arm 전 포함) | `landed` 참(신선), `arming_state` 1 | setpoint를 내던 중이면 멈춘다. 명령 없음 | CANCELED, NONE | E5: disarm 상태에서 setpoint를 멈춘 뒤 5 s 동안 `failsafe` 거짓 5/5 |
| `[LAND]` 미션에서 Land 명령을 보내기 전 | 첫 항목이 모드 명령 항목이고 아직 PREPARING. 기체는 시작 조건의 상태(armed, `nav_state` 4) | 명령 없음(setpoint는 처음부터 없다). 기체는 받은 상태 그대로 남는다 | CANCELED, NONE | 실측 없음. 명령을 보내지 않으므로 조건에서 바로 나온다 |
| 지상, armed(PREPARING의 arm 뒤, TAKEOFF 항목에서 `landed`가 아직 참인 동안) | `landed` 참(신선), `arming_state` 2 | setpoint를 그대로 유지한 채 비강제 disarm 1회. ack와 `arming_state` 1을 확인한 뒤 setpoint 중단 | CANCELED, NONE | E5 5/5(arm 직후), E4 1.75 s 6/6, px4 P5 (나) 5/5. 모두 ACCEPTED |
| 위 줄에서 disarm 거부 또는 미확인 | ack TEMPORARILY_REJECTED, 또는 ROS 시각 2 s 안에 `arming_state` 1 미확인 | 다시 보내지 않는다. setpoint는 그대로 둔다. 상태가 신선하면 아래 "TAKEOFF 항목 실행 중" 줄과 같이 Land 명령으로 끝낸다. 신선하지 않으면 LINK_LOST | 아래 줄의 결과, 또는 ABORTED, LINK_LOST | E4: 거부 12/12는 모두 세 신호 거짓. (가) 거부 뒤 Offboard 유지 6/6(`failsafe` 거짓). 같은 상태(지면 위, 세 신호 거짓, Offboard)의 NAV_LAND는 E3 (나) 9/9, `landed`가 참인 1.6 s에서도 3/3. 거부 직후에 곧바로 NAV_LAND를 이은 회차는 없다([미측정]. 두 실측의 조합이다) |
| TAKEOFF 항목 실행 중(도달 판정 전), `landed` 거짓 | 현재 항목이 TAKEOFF이고 도달 판정이 아직 서지 않음. `nav_state` 14, `failsafe` 거짓 | Hold를 보내지 않는다. Land 명령을 보내고 setpoint를 즉시 멈춘다. LAND 항목의 규칙으로 착륙을 끝낸다(disarm 확인까지) | CANCELED, NONE. 착륙을 끝내지 못하면 LAND 항목의 실패 결과(ABORTED) | Hold를 쓸 수 없는 근거: arm 뒤 1.6-2.5 s의 Hold는 지면 위 armed Hold 12/12(E3 (가)), disarm 거부 뒤의 Hold도 6/6(E4 (가)). 이 구간(arm 뒤 약 1.6 s부터 실제 이륙 3.10-3.40 s까지)은 세 신호가 모두 거짓이라 신호로 가를 수 없다. Land의 근거: E3 (나) 12/12(`landed` 1.46-1.51 s, disarm 3.47-3.53 s), 뜬 뒤 3.6 s(0.25-0.30 m)와 4.0 s(0.9 m) 6/6. 0.9 m보다 높은 상승 중의 NAV_LAND는 [미측정](5 m 호버에서는 실측) |
| LAND 항목 실행 중(Land 명령을 보낸 뒤. `[LAND]` 미션 포함) | 현재 항목이 LAND이고 Land 명령을 보냈다. `failsafe` 거짓 | 새 명령을 보내지 않는다. LAND 항목을 그대로 끝낸다(disarm 확인까지. 항목의 `timeout`과 실패 규칙도 그대로) | CANCELED, NONE. 끝내지 못하면 LAND 항목의 실패 결과(ABORTED) | Hold를 쓸 수 없는 근거: E1 하강 중 Hold는 0.3 m 이하 9회 중 8회 지면에 닿고 armed Hold로 남는다(iii). 세 신호는 12/12 한 번도 서지 않는다. Land의 근거: Hold 뒤 회복 NAV_LAND 36/36, Offboard 중 NAV_LAND 18/18이 착지와 disarm으로 끝났다 |
| LOITER 항목 실행 중(TAKEOFF 도달 판정 뒤), 세 신호 모두 거짓 | 현재 항목이 LOITER. `nav_state` 14, `failsafe` 거짓, `vehicle_land_detected` 신선, `ground_contact`, `maybe_landed`, `landed` 모두 거짓 | setpoint를 유지한 채 Hold 명령. 확인(ack ACCEPTED와 `nav_state` 4)되면 즉시 setpoint를 멈추고 끝낸다 | CANCELED, NONE | px4 P4 5/5(Offboard 호버, 첫 송신 ACCEPTED, 0.020-0.032 s), 재질문 3/3(Hold 뒤 상태). 뜬 기체의 Hold가 공중에 선 실측: 상승 중 0.25-0.30 m와 0.9 m 6/6(E3 보충), 하강 중 0.5 m 3/3(E1), 2.49 m 3/3(재질문) |
| LOITER 항목 실행 중, 세 신호 중 하나라도 참 | 위와 같고 셋 중 하나가 참 | Hold를 보내지 않는다. TAKEOFF 줄과 같이 Land 명령으로 끝낸다 | CANCELED, NONE. 끝내지 못하면 ABORTED | 재질문 (나) 3/3: 접지 뒤의 Hold는 지면 위 armed로 남는다. 정상 호버에서는 나오지 않는 줄이다(방어 검사) |
| Hold 확인 실패(LOITER 줄에서만 온다) | ack TEMPORARILY_REJECTED, 또는 ROS 시각 2 s 안에 `nav_state` 4 미확인 | Land 명령, setpoint 즉시 중단 | ABORTED, MODE_SWITCH_FAILED | 바뀌지 않음. 위치 무효에서 Hold 거부(1회, px4 P4) |

- 실험이 뒤집은 것([실측 혼자] 추가 실험. `opinion-px4.md` "추가 실험 답(E1-E5)"): 세 신호가 모두 거짓에서 시작한 Hold 33회 가운데 10 s 안에 신호가 선 회차는 0이다. 지면 위 armed Hold는 E1 0.3 m 이하 9회 중 8회(지면 접촉), E3 (가) 1.8-2.5 s 9/9(1.6 s의 3회도 같은 끝 상태), E4 (가) 6/6에서 나왔다. 그래서 "세 신호로 가르고 Hold 뒤 지켜본다"는 앞의 표는 지면 위 armed Hold를 막지 못한다. "결과의 처리" 둘째 줄에 해당한다.
- 관찰 창(2 s)을 없앤다. 창이 잡은 회차가 0이고(33회), 새 표에서 Hold가 남는 곳은 LOITER 항목뿐이다. Hold로 끝나는 CANCELED는 Hold 확인 즉시 나간다.
- 항목으로 가르는 이유: 지면 위와 공중을 가를 수 있는 것이 세 신호도 높이도 아니기 때문이다. 높이 임계는 쓰지 않는다. 지면 높이는 기준점의 drift만큼 틀리고(11-6. goal 직전 z와 착지 뒤 z의 차 최대 0.400 m), Hold가 공중에 선 가장 낮은 실측(0.25-0.30 m)과 같은 크기다. 항목과 단계는 Executor가 틀리지 않게 아는 값이고 단위 테스트에서 결정적이다.
- 잃는 것: TAKEOFF 상승 중과 LAND 하강 중에는 취소로 기체를 그 자리에 세울 수 없다. 높이 2.49 m와 0.5 m의 하강 중 Hold, 0.25 m 이상의 상승 중 Hold는 공중에 섰지만(12/12) 그 경계를 Executor가 알 방법이 없어 쓰지 않는다. 이 줄들의 CANCELED는 착륙과 disarm이 끝난 뒤에 나간다(5 m에서 `landed`까지 9.15-9.23 s, disarm까지 11.16-11.24 s. [실측 혼자] 3/3).
- 항목 전이와 취소가 같은 tick에 오면 전이 전의 항목으로 본다(TAKEOFF 도달 판정과 같은 tick의 취소는 TAKEOFF 줄이다). 단위 테스트 대상이다.
- TAKEOFF 줄과 disarm 거부 줄에서 시작한 착륙의 제한 시간은 노드 파라미터로 둔다(ROS 시각. 기본 45 s는 [추정]이고 5 m에서 disarm까지 11.24 s의 4배다. T3의 LAND `timeout`과 같은 값). 넘으면 ABORTED, ITEM_TIMEOUT. LAND 줄은 항목 자신의 `timeout`을 쓴다. 값은 px4가 작업 단위 C-2에서 확인한다.
- "지상"은 `vehicle_land_detected`가 신선하고 `landed`가 참인 것이다. `landed`는 arm 확인 뒤 1.596-1.812 s에 거짓이 되고(42회) 그때 기체는 아직 지면 위다. 그 뒤는 TAKEOFF 줄이 받는다.
- 지상 armed 취소에서 setpoint를 disarm 확인까지 유지하는 이유: 먼저 멈추면 disarm이 거부될 때 Offboard 손실 failsafe로 간다. [실측 혼자] E4 (나) 6/6: 거부 뒤 1.02-1.06 s에 `offboard_control_signal_lost`, 1.03-1.23 s에 `failsafe` 참과 Land. 끝은 지상 disarm이지만 failsafe를 거친다. 옛 규칙(먼저 멈춤)을 버린 근거다.
- CANCELED로 끝난 기체의 상태(계약 변경 목록 K5. 확정): 지상 disarm이거나, armed이고 Hold 모드(`nav_state` 4 확인)다. 5단계 쟁점 9의 "공중에 Hold로 남는다"를 고친다.
  - armed Hold로 끝나는 경우는 둘뿐이다. (1) LOITER 항목 실행 중의 취소. (2) `[LAND]` 미션에서 Land 명령을 보내기 전의 취소(기체는 미션을 받기 전부터 Hold였다).
  - "Hold 모드의 기체가 공중에 있다"는 불변식으로 적지 않는다. (1)이 공중 Hold로 끝난 것이 실측된 범위는 TAKEOFF 도달 판정 뒤의 Offboard 호버 5 m다(5/5, 3/3). 뜬 기체의 Hold가 공중에 선 가장 낮은 실측은 상승 중 0.25-0.30 m, 하강 중 0.5 m다. 호버 높이가 그보다 낮은 미션(`height_m`이 작은 경우)은 [미측정]이고, `height_m`이 `acceptance_m` 이하이면 도달 판정이 지면에서 선다(미해결 표의 "낮은 `height_m`"). (2)는 받은 상태 그대로다.
  - 어느 쪽이든 그 기체는 `[LAND]` 미션으로 내려진다(K7의 시작 조건: armed, `landed` 거짓, `nav_state` 4). Hold 뒤의 NAV_LAND는 공중에서든 지면 위에서든 36/36 착지와 disarm으로 끝났다(0.5 m 이하와 지면 위의 Hold에서 `landed`까지 1.41-2.42 s, disarm까지 3.42-4.43 s. 보충 6회는 더 높다).
- Hold 확인 타임아웃 기본값 2.0 s(ROS 시각, 노드 파라미터), 명령 재송신 0.5 s. 근거: 명령부터 `nav_state` 4까지 최대 0.032 s + `vehicle_status` 최대 간격 0.516 s의 약 4배. 두 값은 첫 라운드([실측 경합])의 것이고 ROS 시각 축이다. 재질문 기록에서도 `nav_state` 4까지 20-28 ms, 최대 간격 0.504-0.516 s였다. 추가 실험에서는 수신까지 20-208 ms였다(E3, E4).
- 강제 disarm은 쓰지 않는다(결정 (r) 유지).
- 측정의 한계: 추가 실험 가운데 세 회차(s3 T01, s3 T14, s1 T18)는 `battery_status` 발행 공백(8.0-8.2 s)과 겹쳤다. `failsafe`는 거짓이었고 결과가 같은 조건의 다른 회차와 같아 px4가 그대로 셌다(미해결 표의 "battery_simulator").

결정: ops 검토로 더한 규칙(2026-11-11. `opinion-ops.md`의 조건 C1-C3과 그 밖의 요청. 계약 변경 목록 K13-K18)
- 끝 상태(C1, K13). result 끝에 `uint8 end_state`를 더한다. Executor가 goal을 끝낼 때 확인한 기체 상태다.
  - 값: `END_STATE_UNKNOWN` 0(확인한 것이 없다. 계약이 약속하지 않는다), `END_STATE_GROUND_DISARMED` 1(`landed` 참을 본 뒤 `arming_state` 1을 확인하고 끝냈다), `END_STATE_ARMED_HOLD` 2(`arming_state` 2, `nav_state` 4, `failsafe` 거짓을 확인하고 끝냈다).
  - CANCELED: 0이 아니다. 취소 표의 줄별 값은 다음이다. 지상 disarm 줄 1. `[LAND]` 미션의 Land 명령 전 줄 2. 지상 armed 줄(disarm 확인) 1. disarm 거부 뒤 착륙으로 끝낸 줄 1. TAKEOFF 줄 1. LAND 줄 1. LOITER 줄(Hold 확인) 2. LOITER 방어 줄(착륙) 1.
  - SUCCEEDED: 0이 아니다. 1a의 두 항목 순서는 모두 LAND로 끝나므로 항상 1이다. 1b의 항목으로 끝나는 미션의 값은 1b에서 정한다(상수는 추가만 한다).
  - ABORTED: 약속이 아니라 끝내는 tick의 관측값이다. 식별 대조를 통과하기 전에 끝난 goal(INVALID_MISSION, VEHICLE_ID_MISMATCH, BUSY)과 LINK_LOST는 항상 0이다. 그 밖에는 끝내는 tick에 `vehicle_status`와 `vehicle_land_detected`가 신선하고 위 1 또는 2의 조건이 맞으면 그 값, 아니면 0이다. Hold 확인 실패(MODE_SWITCH_FAILED)는 Land 명령을 보낸 직후에 끝내므로 0이다. 이 줄의 세부(신선도, 조건의 순서)는 px4가 작업 단위 C-2에서 확정한다.
  - 이름에 AIR를 넣지 않는다. 2는 "Hold 모드의 기체가 공중에 있다"를 뜻하지 않는다(K5와 같다).
  - 근거(ops 의견 2. feedback, `last_item_index`, 텔레메트리로는 결정적으로 가르지 못한다): (1) feedback은 best effort이고 Fleet이 마지막으로 본 항목이 취소가 Executor에 닿은 tick의 항목과 다를 수 있다(TAKEOFF 도달 판정 직후의 취소). (2) `last_item_index`와 항목 종류가 같은데 끝 상태가 다른 쌍이 둘 있다: LOITER 줄(Hold)과 LOITER 방어 줄(착륙), `[LAND]` 미션의 Land 명령 전(Hold)과 뒤(착륙). (3) `VehicleState`는 5 Hz 참고 주기이고 result와 같은 시점의 값이 아니라 Fleet의 배분 판단이 도착 순서에 기댄다. Executor는 자기가 어느 줄로 끝냈는지 틀리지 않게 안다.
  - 11-5(`last_item_index`의 구분 필드 C22는 두지 않는다)는 그대로다. 이 필드는 다른 것이다(끝 상태).
  - `MissionEvent`의 종료 사건에는 6단계에서 싣지 않는다(미해결 표). 이유: 그 메시지의 필드를 정하는 소비자는 Phase 2의 기록물 인덱스이고(5단계 "고정 시점과 범위 구분") owner인 logging-engineer가 이 값의 필요를 말한 적이 없다. 소비자를 대지 못하는 필드는 넣지 않는다(5단계의 기준). `MissionEvent`는 Phase 2 완료에 고정되므로 그때 더해도 1a에 고정된 golden은 바뀌지 않는다.
- CANCELING 중의 이상 판정(C2, K14). 취소 처리 중에도 실행 중 이상 판정이 같은 순서로 매 tick 돈다(LINK_LOST -> FAILSAFE -> EXTERNAL_MODE_CHANGE). 걸리면 취소 처리를 그만두고 그 `reason`의 ABORTED로 끝낸다. 취소 표의 첫 두 줄(상태 미수신, failsafe)은 취소 시점만이 아니라 CANCELING 내내 적용된다. 자기가 보낸 Hold, Land, disarm에 따른 모드 변화와 착륙 뒤의 자동 disarm은 외부 변경이 아니다(LAND 항목과 같은 규칙). px4가 죽은 기체의 취소는 착륙 제한 시간이 아니라 LINK_LOST 임계(1.5 s)에서 끝난다.
- 취소 요청부터 result까지의 상한(C2, K15). Executor가 취소 요청을 받은 때부터 result를 내기까지의 ROS 시각은 "Hold 확인 제한 + disarm 확인 제한 + 착륙 제한"을 넘지 않는다(판정 tick 한 주기는 더 걸릴 수 있다). 착륙 제한은 LAND 항목 실행 중의 취소이면 그 항목의 `timeout`, 그 밖에는 취소 착륙의 제한 시간(노드 파라미터)이다. 기본값으로는 2 s + 2 s + 45 s다. 세 값은 노드 파라미터라 계약의 숫자가 아니고, 계약 문장은 "유한한 상한이 있고 그 구성이 이 셋이다"까지다. 줄별로는 더 짧다(LOITER 줄은 Hold 확인 제한, 지상 armed 줄은 disarm 확인 제한 + 착륙 제한, TAKEOFF와 LAND 줄은 착륙 제한). 상한은 ROS 시각이다. `/clock`이 멈추면 서지 않는다(미해결 표의 "Fleet의 취소 감시").
- 취소로 끝난 goal의 `last_item_index`와 `items_completed`(C3, K16). `last_item_index`는 취소 요청을 받은 tick에 실행 중이던 항목이다(같은 tick의 전이는 전이 전의 항목). `items_completed`에 그 항목을 세지 않는다. 취소로 시작한 착륙은 미션의 LAND 항목을 실행한 것이 아니다(TAKEOFF 줄로 착륙을 끝내도 `last_item_index`는 TAKEOFF의 번호다). LAND 항목 실행 중에 취소되어 그 항목을 끝까지 마친 경우에도 LAND를 세지 않는다. 그래서 CANCELED인 goal은 `items_completed`가 `item_count`보다 작다. PREPARING 중의 취소는 둘 다 0이다(지금 주석 그대로).
- CANCELING 중의 feedback(K17). 취소 처리 중에도 EXECUTING과 같은 방식으로 feedback을 낸다(`phase`는 PHASE_CANCELING. 주기는 계약이 아니다). `item_index`와 `item_type`은 취소 시점의 항목에 머문다(K16과 같다). `distance_valid`는 거짓이다. 이유: 취소 착륙의 남은 높이는 기준점의 drift(최대 0.400 m. 11-6)만큼 틀리고, Fleet이 필요로 하는 것은 "Executor가 살아서 처리 중"이라는 것뿐이다(ops 의견 3).
- 취소 요청의 수락(K17). 실행 중인 goal의 취소 요청은 조건 없이 받는다(`handle_cancel`은 항상 ACCEPT). 이미 취소 처리 중인 goal에 거듭 온 취소 요청은 실행에 영향을 주지 않는다. ops의 "거듭된 요청도 ACCEPT로 응답"은 그대로 받지 않는다. 이유: 거듭된 요청의 응답 코드는 `handle_cancel`이 아니라 action 계층이 정한다. CANCELING인 goal은 취소 대상에 들지 않아 ERROR_REJECTED가, 끝난 goal은 ERROR_GOAL_TERMINATED나 ERROR_UNKNOWN_GOAL_ID가 돌아올 것으로 본다([추정]. 실측은 ros2가 작업 단위 D에서 한다. 미해결 표). 계약 문장은 "거듭된 취소 요청은 실행을 바꾸지 않고, 요청한 쪽은 그 응답 코드를 실패로 다루지 않는다"로 둔다.
- goal이 끝난 뒤(K18). 어떤 GoalStatus로 끝나든 Executor는 그 goal로 비행제어에 setpoint도 명령도 더 내지 않는다(발행 규칙의 "goal이 없으면 /fmu/in에 아무것도 내지 않는다"와 6번의 계약 쪽 문장). ABORTED로 끝난 기체에 Executor가 뒤에서 개입하지 않는다는 것을 Fleet이 전제할 수 있다.
- 취소 처리 중의 MODE_SWITCH_FAILED(K14). 취소 요청 뒤에 ABORTED, MODE_SWITCH_FAILED로 끝났으면 Executor는 Land 명령을 보냈다(Hold 미확인 뒤의 Land, 또는 취소 착륙의 Land 명령 미확인). 착륙이 진행 중인지는 확인하지 않았고 `end_state`는 0이다. 취소가 없는 goal의 MODE_SWITCH_FAILED(PREPARING의 신호 유효와 Offboard 전환)는 이 뜻이 아니다.
- 받지 않거나 미룬 것: 1b에서 Hold 기체에 곧바로 GOTO를 주는 경우의 시작 조건 셋과 Phase 2 `VehicleState`의 필드 확인은 6단계의 결정이 아니다(미해결 표로 넘긴다).
- 단위 테스트 대상(px4, 작업 단위 C-2): 취소 표의 줄마다 `end_state`, GoalStatus별 규칙(CANCELED와 SUCCEEDED는 0이 아님, LINK_LOST는 0), CANCELING 중 이상 셋 각각의 ABORTED, 모든 취소 경로가 상한 안에 끝나는 것, 취소로 끝난 goal의 `last_item_index`와 `items_completed`, CANCELING 중 feedback의 `item_index`와 `distance_valid`, goal이 끝난 뒤 출력이 없는 것. 노드 층(ros2, 작업 단위 D): 상태기의 끝 상태 값과 `END_STATE_*`의 대응, 취소 요청의 수락과 거듭된 요청.

결정: PREPARING 순서(C18). px4의 (나) 순서를 쓴다.
1. 식별 대조(`vehicle_status` 수신과 `system_id`, `component_id` 일치). 명령은 여기까지 막는다.
2. 준비 확인: 상태 토픽 셋이 신선하고 `pre_flight_checks_pass`, `xy_valid`, `z_valid` 참, `failsafe` 거짓. 아니면 NOT_READY.
3. 첫 항목의 시작 조건. 아니면 PRECONDITION_FAILED.
   - TAKEOFF: `landed` 참.
   - LAND: `arming_state` 2, `landed` 거짓, `nav_state` 4(Hold).
4. 기준점: arm 직전의 `vehicle_local_position`(TAKEOFF의 "시작 위치").
5. setpoint 발행 시작(목표는 기준점).
6. 신호 유효 확인(`failsafe_flags.offboard_control_signal_lost` 거짓). 못 하면 MODE_SWITCH_FAILED.
7. Offboard 전환, ack와 `nav_state` 14 확인. 못 하면 MODE_SWITCH_FAILED.
8. arm, ack와 `arming_state` 2 확인. 못 하면 ARM_REJECTED. 이미 armed이고 지상이면 건너뛴다.
9. EXECUTING.
- 첫 항목이 모드 명령 항목(1a에서는 LAND)이면 4-8을 건너뛴다. 고르는 기준은 기체 상태가 아니라 항목 분류 함수(C19)의 결과다. 이유: [실측 혼자] Hold의 공중 기체에서는 `offboard_control_signal_lost`가 참(3/3)이라 6을 돌리면 MODE_SWITCH_FAILED로 잘못 끝난다. 분류로 고르면 단위 테스트에서 결정적이다.
- 첫 항목 LAND의 시작 조건을 `nav_state` 4로 묶는 이유: 14(Offboard)이면 누군가 setpoint를 내고 있고, setpoint가 들어오는 동안에는 착지 판정이 서지 않는다([실측] 5/5). 지상에서 `[LAND]`가 오면 `landed` 참이라 PRECONDITION_FAILED다([미측정]. 조건에서 바로 나오는 결과이고 PX4에 명령을 보내지 않으므로 실측 없이 정한다).
- 이 조건은 Hold가 아닌 모드로 공중에 남은 기체를 `[LAND]` 미션으로 내릴 수 없게 한다. 예: ABORTED, EXTERNAL_MODE_CHANGE로 끝난 기체. 그 기체를 내리는 방법은 1a 계약에 없다(모드를 바꾼 쪽의 몫이다). 1a에는 그 소비자가 없다. Phase 3의 Fleet이 필요로 하면 실측 뒤 조건을 넓힐 수 있고(좁히는 변경이 아니다) K7에 그렇게 적는다. ops-service-engineer의 소비자 검토를 작업 단위 D와 H의 검토에 넣는다.
- 순서의 이유: [실측] 두 순서의 시간 차이는 없고(각 5회, 모두 첫 송신 ACCEPTED), (가) 순서는 arm 뒤 전환이 실패하면 `COM_DISARM_PRFLT=-1`이라 무기한 지상 armed가 남는다. [소스] roadmap의 "최소 10회"는 v1.17.0에서 횟수 조건이 아니다(마지막 `offboard_control_mode`의 나이 조건).
- 이륙 전 실패는 armed이면 setpoint를 유지한 채 비강제 disarm을 보내 확인한 뒤 setpoint를 멈추고 끝낸다(지상 armed 취소와 같은 순서. 초안은 setpoint를 먼저 멈췄다. [실측 혼자] E5: 거부 0/5, disarm 확인 뒤 setpoint를 멈춰도 5 s 동안 failsafe 없음 5/5). disarm 상태이면 setpoint만 멈춘다.
- 단계별 타임아웃 기본값(노드 파라미터, ROS 시각): 상태 수신 대기 10 s, 신호 유효 2 s, 모드와 arm 확인 각 2 s.

결정: 항목별 판정
- TAKEOFF: `acceptance_m` 기본 0.3 m(11-6). 도달은 "`acceptance_m` 안에 ROS 시각 0.5 s 이상 연속(표본 10개 이상)"이다. `vehicle_local_position`이 50 Hz라 표본 10개는 0.2 s이고 0.5 s 조건이 실제로 정한다([실측 혼자] test). 상승 속도 필드는 두지 않는다([소스] `MPC_Z_VEL_MAX_UP` 3.0, [실측] 최대 2.54 m/s).
- LAND: Land 명령이 ROS 시각 2 s 안에 확인(ack ACCEPTED 또는 `nav_state` 18)되지 않으면 setpoint를 멈추고 ABORTED, MODE_SWITCH_FAILED다. 완료는 `arming_state` DISARMED의 연속 확인이고 `landed`는 중간 단계다. `landed` 참 뒤 ROS 시각 5 s(노드 파라미터) 안에 자동 disarm이 없으면 비강제 disarm을 보낸다. 그래도 안 되면 ITEM_TIMEOUT. 쟁점 9의 "(자동 disarm을 기다린다)"를 고친다(사용자 5). [실측 혼자] 자동 disarm은 `landed` 뒤 약 2.0 s에 왔다(3/3).
- 실행 중 이상: 판정 순서는 LINK_LOST(`vehicle_status` 미수신 ROS 시각 1.5 s, 노드 파라미터. ROS 시각의 역행도 여기다. 1번) -> FAILSAFE(`failsafe` 참) -> EXTERNAL_MODE_CHANGE(`failsafe` 거짓이고 `nav_state_user_intention`이 기대와 다르며 자기 요청이 아님. 외부 disarm 포함).
- NOT_READY와 PRECONDITION_FAILED의 조건표는 px4 P8의 표에 위 3번의 LAND 줄을 더한 것이다.
- `TYPE_LOITER`는 Offboard setpoint 유지(`nav_state` 14), `MODE_HOLD`는 PX4의 Hold(`nav_state` 4, Executor는 setpoint를 내지 않는다). LOITER 중의 `nav_state` 4는 외부 변경이다(C32).
- 단위 테스트 대상(px4): 취소 표의 모든 줄과 줄의 우선순위, 항목과 단계별 분기(PREPARING의 arm 전과 뒤, TAKEOFF의 `landed` 참과 거짓, LOITER, LAND, `[LAND]` 미션의 Land 송신 전과 뒤), 항목 전이와 취소가 같은 tick인 경우, LOITER 줄의 세 신호 조합, disarm 거부와 미확인 뒤의 Land(setpoint가 유지되는 것 포함), 취소 착륙의 제한 시간, 첫 항목 분류에 따른 PREPARING 두 경로, ROS 시각 역행.

결정: 1a 노드가 받는 항목 순서(임시 규칙. 계약 문장이 아니다)
- 1a 노드가 실행하는 순서는 둘이다: `[TAKEOFF, LOITER 0개 이상, LAND]`와 `[LAND]`. 그 밖의 순서는 계약상 유효하더라도 ABORTED, INVALID_MISSION으로 끝낸다. GOTO, TRACK_ENTITY, RTL이 든 미션(C23)과 같은 임시 동작이고 1b에서 푼다.
- 이유: 위의 발행 규칙, PREPARING, 취소 표가 이 두 순서만 덮는다. 첫 항목 LOITER는 시작 조건이 없다. `[LAND, TAKEOFF]`와 `[TAKEOFF, LAND, LOITER]`는 Offboard 재진입이 필요하다(1b). 마지막 항목이 setpoint 항목인 미션은 goal이 끝나 setpoint가 멈추면 Offboard 손실 failsafe로 간다. K7을 1a에 고정하는 것은 그 밖의 순서를 받지 않는다는 조건 아래에서다.
- 위치: 계약의 검증 규칙(C24. Fleet과 같이 쓸 함수)과 다른 함수에 둔다(ros2, 작업 단위 C-1). `detail`에 "1a에서 지원하지 않는 항목 순서"를 적는다.
- 단위 테스트(ros2): 통과 `[TAKEOFF, LAND]`, `[TAKEOFF, LOITER, LAND]`, `[TAKEOFF, LOITER, LOITER, LAND]`, `[LAND]`. 거부 `[LOITER, LAND]`, `[TAKEOFF]`, `[TAKEOFF, LOITER]`, `[LAND, TAKEOFF]`, `[LAND, LAND]`, `[TAKEOFF, LAND, LOITER]`, `[TAKEOFF, TAKEOFF, LAND]`.

### 3. 스택을 올리는 주체와 수명 (T1, D10, D7)

근거
- test T1 [실측]: `runner`에 docker 실행 파일이 없고 소켓 마운트도 없다.
- devops, test [실측 혼자]: `stack.sh up` 35.1-35.9 s(각 3회), 부하 아래 42.3 s(1회). `down` 20.7-21.1 s이고 전부가 bridge와 xrce-agent의 SIGKILL 대기다. 10번의 종료 신호 변경 뒤 `down` 0.78-0.85 s(3회). 탐침 비행 1회 약 42 sim s.
- devops D10: 소켓 마운트는 판정 컨테이너에 호스트 root 권한을 주는 것이라 반대. ros-ws에 docker CLI를 넣으면 이미지 key가 바뀐다.
- 반대 근거는 `docs/architecture.md` 281행의 문장뿐이고, 스모크는 이미 호스트 스크립트 구조다.

결정
- 호스트 진입 스크립트 `tests/sitl/run_sitl.sh`가 `tools/stack.sh up`으로 올리고 `compose run runner`의 pytest가 판정한다. pytest fixture는 스택을 올리지 않고 `stack.json`과 토픽으로 준비를 확인한다. `runner`에 docker 소켓을 주지 않는다.
- 소유: `run_sitl.sh`는 devops, pytest 코드와 fixture와 판정은 test. `stack.sh`는 up과 down만 재사용한다.
- 스택 수명: PR 시나리오 묶음은 한 스택(pytest 세션 하나)을 공유한다. 재기동 비용이 약 95 s에서 약 37 s로 줄어도 결론은 같다(시나리오 넷에 약 1.8분 차이). 시나리오 사이에 "지상(`landed` 참), disarm, failsafe 거짓, /fmu/in의 setpoint 수신 없음" 사전 조건 fixture를 두고(`nav_state`는 조건에 넣지 않는다. 지상 취소의 정상 끝 상태가 disarm, `nav_state` 14다. px4 P5 (나). 그 상태에서 다음 TAKEOFF goal의 PREPARING이 통과하는지는 [미측정]이고 로컬 SITL의 지상 취소 시나리오 뒤에 정상 비행을 이어 확인한다), 깨져 있으면 실패로 보고하고 뒤를 돌리지 않는다. 사전 조건은 healthcheck가 아니라 토픽으로 본다. 기체를 failsafe로 끝내는 시나리오와 `tests/px4_facts/`(9번)는 별도 스택이다.
- teardown 예산은 10번의 종료 신호 변경 뒤 15 s(벽시계)다(`mission-N`의 `stop_grace_period` 10 s + 여유 5 s). 변경 전에는 30 s다.
- `docs/architecture.md` 281행은 이 구조로 고친다(문서 반영 목록).
- teardown 순서와 신호 규칙은 test T7을, "3회 연속"의 정의와 기록은 T9를, 디렉터리는 T10을, 설정 해시 대조는 T11을 그대로 쓴다.

### 4. ROS 비의존 핵심을 6단계에 둘지 (R9, T5, roadmap 1b 1번)

근거
- ros2 R2 [실측 경합, 동작]: `handle_accepted` 안에서 미션을 끝까지 돌리면 timer가 약 3 s 막힌다(`COM_OF_LOSS_T` 초과). 그래서 노드는 어차피 tick 기반 상태기여야 한다. 상태기를 노드 안에 두느냐 밖에 두느냐의 차이이고 코드 양은 거의 같다.
- test T5: 실패 경로(NOT_READY, ARM_REJECTED, MODE_SWITCH_FAILED, PRECONDITION_FAILED, ITEM_TIMEOUT, 취소 분기)를 단위 층에 두려면 핵심이 6단계에 있어야 한다. SITL로 옮기면 시나리오 하나에 재기동 약 37 s와 비행 시간이 든다.
- 재질문으로 더해진 근거: 2번의 취소 분기(항목과 단계별 줄, 항목 전이와 같은 tick의 취소)와 PREPARING 두 경로는 SITL로 시점을 맞추기 어렵다(Hold 도착까지 20-30 ms의 경합). px4가 단위 테스트 대상으로 지목했다.
- 반대 근거: roadmap은 순수 상태기와 "전이 전부를 덮는 단위 테스트"를 1b 1번에 둔다. 6단계의 범위가 는다.

판단: 범위 변경이라 사용자가 정한다(사용자 2). 권고는 "구조만 당긴다"다. 아래와 작업 분할은 권고안이 채택된 경우다.
- `idsim_mission` 안에 rclcpp를 쓰지 않는 라이브러리를 둔다. 담는 것은 미션 검증(C24), 항목 분류(C19), TAKEOFF, LOITER, LAND와 취소의 상태기다. 입력은 ROS 시각(ns), 최신 PX4 관측 struct, 취소 요청이고 출력은 setpoint 목표, 보낼 명령, 종료 판정과 `reason`이다.
- 1b에 남는 것: GOTO, TRACK_ENTITY, RTL 상태와 전이 전부의 테스트. 상태기 입출력 struct는 내부 API이고 계약이 아니다.
- 검증 함수는 상태기와 다른 header에 둔다(C29. Fleet과의 공유 방식은 Phase 3).

결정: `idsim_mission`의 소유 분할(`file-ownership.md` 반영은 작업 단위 O. PR 4 전에 한다. PR 4-8 동안 "소유자가 아니면 고치지 않는다"를 파일로 판정할 수 있어야 한다)

| 부분 | 소유 | 검토와 승인 |
| --- | --- | --- |
| 패키지 골격(`CMakeLists.txt`, `package.xml`), 미션 검증, 항목 분류와 그 단위 테스트 | ros2-engineer | px4(분류), test |
| PX4 절차 상태기(PREPARING, TAKEOFF, LOITER, LAND의 실행, 취소 분기, 실행 중 이상 판정)와 그 단위 테스트. 패키지 안의 한 디렉터리로 모은다(`include`, `src`, `test` 각각의 `procedure/`. 이름은 골격을 만들 때 ros2가 확정) | px4-engineer | ros2, test |
| 상태기의 입출력 struct(관측, 명령, setpoint 목표, 종료 판정) | px4-engineer | 바꿀 때 ros2의 승인이 필요하다(노드가 채우고 읽는다) |
| 노드(lifecycle, 자기 전이, action 서버, `MissionEvent`, 식별 게이트, params, 표식 파일, 종료 처리)와 노드 층 테스트 | ros2-engineer | px4, ops(소비자 관점), test(C20, C21 승인) |
| Executor 설계 노트 | ros2-engineer. PX4 절차 절(발행 규칙, PREPARING, 취소 표)은 px4가 쓴다 | architect |

- CLAUDE.md 담당자 표의 px4 행("`idsim_mission`의 PX4 접점")과 맞는다. ros2 행에는 `idsim_mission`이 없다. CLAUDE.md는 사용자만 고치는 파일이므로 표의 변경은 사용자 9로 올린다. `file-ownership.md`의 반영은 그 결정을 기다리지 않는다.
- 사용자 2가 (나)이면 라이브러리를 나누지 않고 절차 코드를 노드 패키지 안의 클래스로 둔다. 소유의 경계(절차는 px4, 나머지는 ros2)는 같다.

### 5. activate 조건, 식별 게이트, healthcheck (R3, R5, P12, D3)

근거
- ros2 R3 [실측 경합, 동작]: 전이 callback 안에서 기다리면 executor가 막히고 clock thread 설정에 따라 결과가 바뀐다. 실패로 돌려주고 다시 시도하면 `/clock` 뒤에 성공한다.
- ros2 [실측, 스택 없음, C++ lifecycle 원형]
  - 같은 executor의 1 s wall timer 안에서 `activate()`를 부른다. on_activate가 FAILURE면 inactive로 돌아오고(0.1-0.3 ms) 다음 tick에 다시 시도한다. 실패를 넣은 실행 2회와 넣지 않은 15회 모두 막힘이나 교착이 없었다. 같은 timer에서 `deactivate()` 뒤 재시도 loop로 돌아가 다시 active가 된다(1회).
  - node interface로 만든 일반 publisher는 inactive에서도 전달된다(14건. `LifecyclePublisher`는 0건). `this->create_publisher`는 lifecycle 노드에서 `LifecyclePublisher`를 돌려주므로 쓰지 않는다.
  - SIGTERM이 오면 rclcpp 신호 처리기가 context를 닫고 spin이 돌아온다. 그 뒤의 `shutdown()`은 전이하지 않고 on_shutdown이 불리지 않는다. 소멸자도 부르지 않는다(rclcpp_lifecycle 28.1.22). on_shutdown이 불리는 길은 context의 pre-shutdown callback 하나였고, 그 callback은 신호 처리 thread에서 돈다. 그 안의 publish는 예외 없이 돌아왔지만 수신은 확인하지 않았다.
  - 컨테이너 PID 1 기준 `docker stop`: 실행 파일 직접 `exec`는 0.09-0.24 s에 종료 코드 0. `exec ros2 run`은 10.15-10.19 s 뒤 137(Python이 SIGTERM 처리기를 두지 않는다).
  - SIGKILL 뒤 표식은 남고, 컨테이너를 다시 시작하면 쓰기 계층이 그대로라 다음 기동에 이어진다. 생성자에서 지우면 configure 전에 사라진다(1회).
  - executor를 30 s 막아도 표식은 남아 `test -f`는 참이다. 1 Hz timer가 mtime을 갱신하면 막힌 동안 나이가 는다.
- devops [실측 혼자]
  - compose `tmpfs`의 마운트를 healthcheck 명령이 그대로 본다. 옵션 없는 tmpfs는 첫 기동에서 1777 root지만 같은 컨테이너를 다시 시작하면 755 root로 마운트되어 uid 1000이 쓰지 못하고 healthcheck가 계속 starting이다(2/2). `uid=,gid=,mode=`를 주면 재기동 뒤에도 그대로다(각 1회). 재기동 때 내용은 비워진다.
  - 판정 `test -n "$(find <표식> -newermt -5seconds)"`: 갱신을 멈추면 10.0 s 뒤 unhealthy(interval 2 s, retries 3), 재개 뒤 2.0 s 안에 healthy. 헬스 로그 기준 32-45 ms(대부분 docker exec 비용). `ros2` CLI healthcheck는 1.3-2.1 s[실측 경합]이고 참가자 하나를 만든다. 차이는 경합이 아니라 Python CLI 기동과 DDS 참가의 비용이다.
- px4 P12: `system_id`는 프로세스가 살아 있는 동안 바뀌지 않는다(불일치는 기다려도 풀리지 않는다). 미수신은 기다리면 풀린다.

결정
- activate 조건은 둘이다. `Px4Timestamp::now` 성공, `vehicle_status` 수신과 `verify` Match. 기다리지 않고 즉시 판정해 FAILURE를 돌려준다.
- 전이는 노드 실행 파일이 스스로 건다. `main`이 configure를 한 번, 벽시계 1 s wall timer가 inactive인 동안 activate를 다시 시도한다. 실패 이유는 로그 한 줄(같은 이유는 반복하지 않음), 불일치는 ERROR 수준이다. launch 파일과 별도 전이 프로세스를 두지 않는다. 외부의 `ros2 lifecycle set`은 막지 않는다.
- 설정 오류(노드 네임스페이스와 params의 불일치, params 없음, 타입 오류)는 on_configure FAILURE이고 다시 시도하지 않는다.
- 미수신과 불일치의 대응
  - activate 전: activate FAILURE(재시도). inactive에서 온 goal은 수락 뒤 ABORTED, NOT_READY(계약의 "식별 대조 미완 또는 불일치"와 같다).
  - active 뒤 미수신: lifecycle 전이를 하지 않는다. 접수 시점이면 NOT_READY, 실행 중이면 LINK_LOST.
  - active 뒤 불일치: 실행 중 goal은 ABORTED, LINK_LOST(`detail`에 원인), 명령과 setpoint를 멈추고 스스로 deactivate해 재시도 loop로 돌아간다. INTERNAL로 하지 않는 이유: 255는 Executor 자신의 오류이고, 이 경우는 "우리 기체의 상태가 오지 않는다"에 해당한다. ERROR 전이는 쓰지 않는다.
  - PX4 재기동은 따로 감지하지 않는다. 미수신으로 드러난다(실행 중이면 1.5 s 뒤 LINK_LOST. [실측 경합, n=4] px4 컨테이너 start부터 `vehicle_status` 첫 수신까지 5.5-6.7 s). 재기동한 PX4의 `system_id`는 같으므로 노드는 active로 남고 다음 goal은 PREPARING의 준비 확인부터 다시 본다.
  - 초안의 "`vehicle_status.timestamp`의 역행으로 PX4 재기동을 감지한다"는 버린다. 전제(px4 P12의 "재기동하면 hrt가 다시 작게 시작한다" [추정])가 틀렸다. [소스] `GZBridge.cpp` 331-346행: PX4의 시각은 callback마다 Gazebo의 sim 시각에 맞춰진다. [실측] reviewer: 부팅 뒤 첫 `vehicle_status.timestamp`는 17.4-18.5 s이고(0 근처가 아니다), 5290표본에서 역행 0건, 같은 값 3건이다. 그래서 px4만 재기동하면 `timestamp`는 이어지고, 역행은 Gazebo가 재기동할 때만 생기며 그때는 `/clock`도 함께 뒤로 간다. 그 경우는 1번의 ROS 시각 역행 규칙이 받는다.
- 실행 중 deactivate 요청은 FAILURE로 거부한다.
- 종료 처리: 노드는 context의 pre-shutdown callback 하나를 건다. callback은 `handle_accepted`와 같은 mutex를 잡고 "실행 중 goal을 ABORTED, INTERNAL로 끝낸다, 종료 사건을 낸다, setpoint를 멈춘다, 표식을 지운다"를 직접 한다(신호 thread에서 lifecycle `shutdown()`을 부르지 않는다. tick과 경합한다). 외부에서 건 shutdown 전이(on_shutdown)도 같은 함수를 부른다. spin이 돌아온 뒤에는 publish가 닿는다고 가정하지 않는다. 종료 사건과 result의 전달은 최선 노력이고, 닿지 않은 경우는 5단계 쟁점 8의 "종료 사건이 없는 접수는 결과 미상"으로 이미 덮인다. 초안의 "shutdown 전이에서 ..."를 이 문단으로 대체한다. 계약 문장이 아니라 Executor 설계 노트에 적는다. 이 안은 [추정]이다. [실측]은 callback 안에서 lifecycle `shutdown()`을 부른 3회뿐이고, mutex를 잡고 abort와 publish를 직접 하는 형태는 재지 않았다. 작업 단위 D에서 ros2가 원형으로 확인한다(신호 thread에서 abort와 publish가 돌아오는지, tick과의 교착이 없는지). 확인되지 않으면 "표식 삭제와 setpoint 중단만 하고 goal은 결과 미상으로 둔다"로 줄인다.
- 노드는 컴포넌트 클래스로 등록하고 실행은 작은 `main` 하나로 한다. executor는 `SingleThreadedExecutor`, 미션 진행은 20 Hz tick이다.
- 서비스: 기체마다 `mission-N`, `depends_on`은 `bridge`와 자기 `px4-N`(healthy), `startup.stages`의 넷째 단계. command는 install 아래 실행 파일의 직접 실행이다(`ros2 run`을 쓰지 않는다. 이미지 entrypoint의 `exec "$@"`를 거친다). `init`은 두지 않는다(rclcpp가 PID 1에서 SIGTERM을 받아야 pre-shutdown callback이 불린다). `stop_grace_period`는 기본 10 s. embedded 변형에는 만들지 않는다(생성기 단정). 실패하면 `stack.sh`가 `mission-N` 로그 끝 30줄을 찍는다. `STACK_UP_TIMEOUT`은 240 s 그대로.
- 스모크 S2-S5도 이 단계까지 올린다(결정 (k) 유지). S4 golden은 `fmu/` 아래만 담으므로 섞이지 않는다. 조건은 2번의 "goal이 없으면 /fmu/in에 내지 않는다"다. 스모크가 `ros_ws/install`을 요구하게 되는 것은 받아들인다(test의 승인은 구현 검토에서).
- `stack.sh up`의 install 부재 검사는 devops D4대로(생성 전에 검사, 종료 코드 1, 자동 빌드 없음). 빌드와 스택 가동을 막는 규칙은 두지 않는다.

결정: healthcheck는 표식 파일이다(초안의 잠정을 닫는다. `ros2 lifecycle get`으로 돌아갈 근거가 없다).
- 노드 규칙(ros2)
  1. 표식 경로는 노드 파라미터 `health_marker`(문자열)이고 비어 있으면 아무것도 쓰지 않는다. 노드는 컨테이너 구조를 알지 않는다.
  2. on_configure의 첫머리(`health_marker`를 선언하고 읽은 직후)에서 남은 표식을 지운다. 생성자에서는 지우지 않는다(params 선언이 on_configure라 생성자는 경로를 모른다. 6번). tmpfs는 컨테이너를 다시 시작할 때 비워지므로([실측] devops) 생성자에서 지우는 것과 결과가 같다.
  3. on_activate에서 쓰고 on_deactivate와 종료 처리에서 지운다.
  4. active 동안 1 Hz wall timer(재시도 timer와 같은 것. 1번의 예외 문장이 덮는다)가 mtime을 갱신한다.
- 생성기 규칙(devops)
  1. `mission-N`에 `tmpfs: ["/run/idsim:uid=<uid>,gid=<gid>,mode=0700"]`. uid와 gid는 `user`에 쓰는 값과 같은 원천이다.
  2. params에 `health_marker: /run/idsim/active`. 단정: `health_marker`가 tmpfs 대상 아래에 있다.
  3. healthcheck는 `test -n "$$(find <표식> -newermt -5seconds 2>/dev/null)"`, `interval 30s, timeout 5s, retries 3, start_period 60s, start_interval 2s`.
- 5 s의 근거: 갱신 주기 1 s의 5배이고, ROS 시각 timer의 벽시계 간격 최대 70.3 ms[실측 혼자, 부하]와는 두 자리 차이다.
- 이 판정은 재시작을 일으키지 않는다(compose 기본). 기동 순서와 `stack.sh`의 실패 보고, 실패 artifact의 Health 로그에만 쓰인다.
- 표식과 lifecycle 상태의 대조: `sitl` 세션 fixture가 `get_state` 서비스로 active를 한 번 확인한다(pytest는 이미 참가자라 추가 비용이 없다).

### 6. `vehicle_id`의 전달 (D1, D2, R4, 5단계 쟁점 1)

근거
- 5단계 결정: 생성기가 `stack.json` 기체 항목과 노드 params에 `vehicle_id`를 직접 싣는다. `idsim_common`의 함수는 변환이 아니라 대조를 한다.
- devops D1, D2 [실측]: golden diff는 `stack.json` 4개뿐. 네임스페이스는 command의 `-r __ns:=`로 준다.
- ros2 [실측, 스택 없음, C++ lifecycle 노드, 각 1회]: 정확한 FQN key의 params 파일은 `__ns`, `__node` remap과 함께 적용된다. key는 remap 뒤의 이름이어야 한다. 다른 기체의 파일과 파일 없음은 선언은 통과하고 읽기에서 `ParameterUninitializedException`이 나 configure FAILURE다. key `/**`는 적용되고 대조에서 걸린다. 정수 자리에 문자열을 주면 선언에서 `InvalidParameterTypeException`이다. 네임스페이스 `/a/b`와 `vehicle_id: a/b`는 단순 비교로는 통과한다.
- ros2는 R4(네임스페이스에서 `vehicle_id` 파생)를 철회했다. 값의 수가 같고, 파생을 두지 않으면 `idsim_common`이 이름 규칙을 해석하지 않는다.

결정(초안의 잠정을 닫는다. 반대 의견이 없다)
- `stack.json`: `vehicles[].vehicle_id`(필수, null 불가), `vehicles[].ros_params_file`, `schema` 1 유지, `generator.version` 3. 생성기 단정에 `vehicle_id == ns에서 앞 빗금을 뗀 값 == px4_ns`. 이 파생은 생성기 안에만 있다.
- params key: `vehicle_id`(문자열), `sysid`(정수), `health_marker`(문자열), `use_sim_time`. 점 접두사를 두지 않고 `stack.json`의 필드 이름과 같게 한다. `ns`는 싣지 않는다. 미션 노드의 조정 값은 패키지 기본값이고 생성기가 싣지 않는다.
- 노드 네임스페이스와 노드 이름은 생성기가 command의 `-r __ns:=`와 `-r __node:=`로 준다. params 파일의 노드 key는 그 둘로 만든 정확한 FQN이다(`/**`를 쓰지 않는다). key와 `__node`는 생성기 안의 같은 값에서 만든다.
- 선언은 on_configure에서 한다(생성자에서 하면 타입 오류가 예외로 프로세스를 끝낸다). 기본값 없이 타입만으로 선언한다.
- `idsim_common`의 추가(시그니처는 ros2의 재질문 답 그대로)
  - `vehicle.hpp`(rclcpp 없음): `VehicleId::parse`(비어 있지 않고 빗금이 없는 ROS 이름 토큰 하나. 정규화하지 않는다), `VehicleIdentity { VehicleId id; VehicleNamespace ns; SystemId sysid; }`, `namespace_matches(id, ns)`(`ns.str() == "/" + id.str()`만 본다. 변환 함수는 두지 않는다).
  - `vehicle_params.hpp`: `kVehicleIdParam`, `kSysidParam`, `declare_vehicle_identity(NodeBaseInterface &, NodeParametersInterface &, std::string * error)`. 예외를 내지 않고 실패하면 `nullopt`이다. interface 인자라 `rclcpp::Node`와 `LifecycleNode`를 둘 다 받는다.
  - 다중 토큰은 `VehicleId::parse`가 거부한다(C8).
  - 기존 테스트 둘(`test_vehicle.cpp`, `test_vehicle_command.cpp`)의 집합체 초기화를 고친다. 단위 테스트: 위 실측 표의 파일 기반 일곱 줄과 다중 토큰 거부.
  - `VehicleCommandBuilder`와 `verify`는 `id`를 쓰지 않는다. `MissionEvent.vehicle_id`와 goal의 `vehicle_id` 대조가 `id.str()`을 쓴다.
- 결정 (u)의 "params로 ns와 sysid를 받고"는 "네임스페이스는 `__ns`로, `vehicle_id`와 sysid는 params로"로 읽는다(문서 반영 목록).
- 파일 위치는 `artifacts/runs/<실행 id>/ros_params/<vehicle_id>.yaml`, 기체마다 하나.
- 생성기 단정: params 값에 `fmu/`가 없다. `px4-api` 검사 대상에 `ros_ws/src/**/*.yaml`을 더한다(B7).

### 7. bridge 설정 파일 (D9, S4)

결정(초안 그대로)
- 6단계에는 바꾸지 않는다(command 인자 `/clock` 유지). 1b에서 표적 경로를 정할 때 파일로 바꾸고, 그때의 기본 방향은 sim의 안(파생값이 없으면 `idsim_sim`의 고정 파일, 생성기는 마운트와 인자만)이다.
- 이유: 6단계의 소비자가 없고([소스] devops), 이득이 생기는 시점(금지 토픽 검사)이 1b이며, 표적 생산 방식 자체가 1b 착수 때 다시 정해진다. sim의 안은 [추정]이다. 결정 (a)의 "bridge 설정 파일 생성"은 1b에서 이 방향으로 다시 본다.
- 6단계에서 바뀌는 것은 bridge의 실행 방식뿐이다(10번의 종료 신호).

### 8. 기록: MCAP, 구독자 수 게이트, `MissionEvent` 발행자 (L1-L3, R2, R8)

근거
- logging L2 [실측]: MCAP 플러그인은 이미지에 있다. 6단계에 넣으면 기록물 경로와 이름, 기록 대상 목록, 소비자, 기록기와 Executor의 순서가 Phase 2 전에 굳는다.
- logging L3: 구독자 수 게이트는 관찰용 사본이 정본(action)의 수락을 좌우하게 만들고, 테스트의 구독만으로 참이 되어 기록기를 증명하지 못한다.
- ros2 [실측]: `LifecyclePublisher`는 inactive의 사건을 버린다. node interface로 만든 일반 publisher는 전달한다.
- logging [실측 혼자, 6회]: 비행 1회(부팅부터 stop까지 sim 43-46 s)의 ULog는 12.9-13.5 MB, gzip -6 뒤 3.7-3.9 MB(약 0.3). 비율은 sim 시간 1분당 17.8-18.0 MB다. 6개 모두 pyulog `file_corruption=False`, `dropouts=0`.
- logging [실측 혼자, 4/4]: Gazebo를 먼저 멈추거나(지상 disarm, 2회) hover 중 SIGKILL로 죽여도(2회) px4는 SIGTERM 뒤 0.09-0.10 s에 종료 코드 0으로 끝났고 ULog는 hrt가 멈춘 시점까지 온전했다.

결정
- `sitl` 실패 artifact에 MCAP을 넣지 않는다(Phase 2부터). 문장 변경은 사용자 3.
- Executor에 구독자 수 게이트를 넣지 않는다.
- `MissionEvent` 발행자는 일반 publisher이고 on_configure에서 `rclcpp::create_publisher`(node interface를 지역 변수로 받아 넘긴다)로 만든다. QoS는 `idsim_common/qos.hpp`에 더하는 `mission_event_qos()`(RELIABLE, VOLATILE, KEEP_LAST 10)이고 구독 쪽도 같은 함수를 쓴다. TRANSIENT_LOCAL로 바꾸지 않는다.
- 접수 사건은 `handle_accepted`에서 mutex를 잡은 뒤 판정 전에, 종료 사건은 result를 돌려주기 직전에 낸다. `goal_id`는 `get_goal_id()`의 16바이트를 그대로 옮긴다([실측] status의 UUID와 일치).
- 테스트는 result와 종료 사건의 도착 순서를 가정하지 않고 둘 다 기다린다. 구독 생성 -> 발행자 수 1 이상 -> `wait_for_server` -> goal -> 수락 직후 `get_result_async`의 순서를 쓴다. 접수 사건 누락은 재시도 없이 실패다([실측 경합] 확인 없이 1/30 유실, 확인하면 0/25. rclpy 가짜 서버 기준이라 실제 Executor로 다시 잰다).
- 실패 artifact: 실행 디렉터리 통째(`compose.yaml`, `stack.json`, `ros_params/`, `ros_log/`, ULog, 판정 JSON, `compose logs`), 컨테이너 종료 코드(px4, bridge, xrce-agent, `mission-N`), `mission-N`의 Health 로그. 순서는 logs 저장 -> down -> 올리기. 내리는 순서는 바꾸지 않는다(px4가 gazebo보다 먼저). 보관 7일. 크기는 sim 시간 2-3분에 ULog 36-54 MB, 압축 뒤 10-16 MB다.
- ULog 판독은 종료 코드와 함께 본다(파일만으로는 "정상으로 닫힘"과 "버퍼까지 쓴 뒤 끊김"을 가를 수 없다). 끝이 잘린 ULog는 실패가 아니라 "끝이 잘림"으로 표시한다. 이 규칙의 근거는 "Gazebo가 먼저 죽으면 잘린다"가 아니다(그 추정은 틀렸다. 10번). SIGKILL 같은 다른 경로에 대한 방어다.

### 9. failsafe 회귀 판정 (A8, T6, P9)

근거
- 1번 결정(ROS 시각 timer) 아래에서 bridge 정지 주입은 "발행 0건" 경로만 본다(test [실측]). 묵은 timestamp 경로를 타지 않는다.
- [소스] px4: `/fmu/in`의 timestamp는 `min(timestamp, hrt_absolute_time())`로 들어온다. 그래서 노드가 벽시계 timestamp를 싣는 회귀는 failsafe를 일으키지 않고 "항상 신선"으로 보인다. 주입으로는 이 회귀를 잡지 못한다.
- test [실측 혼자 r1-r3, 부하 r5] `offboard_control_mode`의 "수신 시 `SimClock` - `timestamp`": 중앙값 0 ms, p99 4-8 ms, 최대 4-12 ms, 음수 0건. 호버 구간과 비행 전체의 최대가 같다. 값은 `/clock`의 4 ms 양자화를 따른다.
- test [실측 혼자, 5회] 탐침이 유일한 발행자일 때: 0.5 s 묵음(실제 간격 0.548-0.552 s) 뒤 10 s 동안 손실 없음. 묵음을 이어 가면 0.992-1.044 s에 손실 flag, 1.028-1.172 s에 `nav_state` 18, 12.30-12.69 s에 disarm. 한 벌 22.3-22.7 sim s, 스택 올리고 내리기를 더해 벽시계 약 100 s.
- 정정: 초안의 "test의 0.2 s 기준은 수신 지연 0.176 s 때문에 여유가 없다"는 틀린 근거다. 0.176 s는 `vehicle_status`의 arm 전이 메시지 한 건이고 `offboard_control_mode`와 무관하다(10번). 그래도 통계는 초안대로 둔다. 이유는 아래.

결정: 회귀를 둘로 나눈다. Executor에 시험용 파라미터를 두지 않는다.
- (A) "Executor가 sim 시간 timestamp를 싣는다". PR마다, 정상 비행 안에서. 하네스가 `offboard_control_mode`를 구독만 하고 `timestamp`와 수신 시 `SimClock`의 차를 본다. 판정: goal 동안 받은 표본 전체(발행 시작부터 끝까지)의 중앙값 절댓값 0.1 s 이하, 최대 절댓값 0.5 s 이하, 표본 100개 이상(모자라면 판정 불가로 실패). 값의 이유: 잡으려는 회귀(벽시계 epoch, steady 시각, 멈춘 시계, 1 s 이상의 고정 차)는 몇 자리 차이라 어디에 두어도 잡히고, 0.5 s는 관측 최대 12 ms의 약 40배이면서 손실 판정 1 s보다 작다.
- (A') 스모크 S5에 `vehicle_status.timestamp`와 수신 시 ROS 시각의 차 판정을 같은 통계로 넣는다(`UXRCE_DDS_SYNCT`가 돌아가는 회귀). S5는 arm하지 않으므로 전이 메시지의 152-196 ms가 들어오지 않는다([실측 혼자] sim: arm 없는 구간 -8 - 8 ms). `sitl`의 비행에서는 `vehicle_status`에 이 통계를 걸지 않는다(최대 0.5 s가 전이의 196 ms 대비 약 2.5배 여유뿐이다).
- (B) "PX4가 그 timestamp로 손실을 판정한다". PX4의 사실이고 Executor와 무관하다. 저장소에 반복 가능한 시나리오로 둔다(초안의 잠정을 닫는다).
  - 위치는 `tests/px4_facts/`다. `tests/sitl`도 스모크도 아니다(스모크는 arm하지 않고 벽시계 기준이고, `tests/sitl`은 /fmu/in에 발행하지 않는다는 규칙을 디렉터리 경계로 지킨다). 진입은 `tests/px4_facts/run.sh`(호스트. `run_sitl.sh`와 같은 꼴)이고 판정은 `tests/support`의 `SimClock`과 판정 함수를 같이 쓴다. 소유는 test, 검토는 px4.
  - 내용: 하네스가 유일한 setpoint 발행자다. 0.5 s 묵음은 10 s 동안 손실 없음, 묵음을 이어 가면 ROS 시각 2 s 안에 손실과 `nav_state` 18, 그 뒤 착지와 disarm. 별도 스택.
  - 실행 시점: 로컬 전용이다. `PX4_TAG`, px4 파라미터 파일, `idsim_common`의 timestamp helper를 바꾸는 PR에서 돌리고 결과 요약을 PR 본문에 붙인다. CI에 올릴지는 사용자 8.
  - 규칙의 범위: "`tests/sitl`과 `tests/smoke`는 /fmu/in에 발행하지 않는다. /fmu/in 발행은 `tests/px4_facts/`만 한다". 탐침은 시작 전과 묵음 직전에 `offboard_control_mode`와 `trajectory_setpoint`의 발행자가 자신 하나인지 토픽으로 확인하고, 아니면 판정 불가로 끝낸다. 그 스택에서는 goal을 보내지 않으므로 Executor가 떠 있어도 발행하지 않는다([추정]. Executor 구현 뒤 확인). 명령 source는 하네스의 251/1이다.
  - 검사(제안): `tests/` 아래에서 /fmu/in 발행 이름을 만드는 함수(`tests/support/px4_names.py`의 발행용 함수 하나)를 부르는 파일은 `tests/px4_facts/`에만 있다. (A)의 구독은 다른 함수를 쓴다. 출처는 test 의견서의 제안이고 `tools/ci/`의 소유자인 devops의 답은 받지 않았다. 실수 방지 수준이다. 받을지는 devops가 작업 단위 P의 구현 검토에서 정하고, 받지 않으면 이 규칙은 검토로만 지킨다.
  - `px4-api` 검사의 예외는 필요 없다([소스] `tools/ci/lint.sh`의 대상은 `ros_ws/src`이고 `tests/`는 대상이 아니다).
  - Executor의 원칙("setpoint는 Executor만")과의 관계: `check_px4.py`와 같은 "PX4 사실 확인" 계열이고 Executor가 일하는 스택의 판정이 아니다.

### 10. 사실 정정

- "176 ms"(초안 1번, 9번, 측정 조건): 경합에 따른 수신 지연이 아니다. `vehicle_status`의 "수신 시 ROS 시각 - `timestamp`"가 상태 전이의 메시지에서만 크다. [실측 혼자] test: 최대가 매회 176-180 ms이고 모두 arm 전이의 메시지 한 건이다(5/5). px4 기록 40개를 reviewer가 다시 분석한 값은 전이 메시지에서 152-196 ms다(최대 196 ms는 첫 라운드 r5. ROS 시각 축의 차라 경합과 무관하다). failsafe 전이에서도 164 ms, 112 ms가 보였다(1회). 전이에서 나가는 `vehicle_status`가 앞 주기의 `timestamp`를 싣는 것으로 보인다([추정]. 소스 확인은 px4-engineer에게 넘긴다. 비차단). arm이 없는 구간은 -8 - 8 ms다(sim). `timestamp` 자체는 단조다([실측] reviewer: 5290표본에서 역행 0건). 영향을 받는 결정은 1번의 신선도 규칙과 9번의 (A')이고 각각 반영했다. arm 확인의 수신은 ack 뒤 약 0.16 s라 2 s 제한에는 영향이 없다.
- "106 ms"(초안 1번): [실측 경합] 1회의 값이고 혼자와 CPU 부하에서 재현되지 않았다(최대 25.9 ms). 1번의 여유 근거에서 뺐다.
- "약 10 MB/분"(px4의 ULog 크기): 분모 오류다. [실측] logging: 그 파일(266.5 MB)의 sim 길이는 922 s이고 비율은 17.3 MB/분이다. 비율은 실행과 경합에 무관하게 17-18 MB/분이고, 압축 뒤 약 0.3이다(초안의 "약 1/4"도 고친다).
- "Gazebo가 먼저 죽으면 px4가 SIGKILL되고 ULog가 잘린다"(logging의 앞선 추정): 틀렸다. [실측 혼자] 4/4에서 종료 코드 0이고 ULog는 온전했다. [소스]로는 hrt가 멈추면 shutdown worker와 logger가 진행하지 못해야 하는데 무엇이 진행시켰는지는 찾지 못했다. 원인은 px4-engineer에게 넘긴다(비차단. 결정은 실측을 쓴다). 한계: 각 2회.
- 종료 신호: [실측 혼자] devops, 변형별 3회.
  - bridge: PID 1이 `ros2 run`(Python)이면 SIGTERM과 SIGINT 둘 다 자식에게 가지 않는다. 실행 파일을 직접 두면 0.04-0.06 s에 종료 코드 0.
  - xrce-agent: `MicroXRCEAgent`가 PID 1이고 처리기가 없어 두 신호 모두 듣지 않는다. `init: true`면 0.04-0.06 s에 143.
  - `stop_signal: SIGINT`는 어느 쪽에도 효과가 없다. `init: true`만으로는 bridge가 정상 종료하지 않는다(Python만 죽는다).
  - 결정: bridge command를 실행 파일 직접 경로로 바꾸고(경로의 ROS 배포판 이름은 생성기가 `versions.env`의 `ROS_DISTRO`로 만든다), xrce-agent에 `init: true`를 준다. `stop_signal`은 넣지 않는다. 생성기 단정: ros-ws 이미지를 쓰는 본 스택 서비스의 command 첫 요소는 `/`로 시작하는 실행 파일이고 `ros2`가 아니다(healthcheck는 대상이 아니다), xrce-agent는 `init: true`. `down`은 20.8-21.1 s에서 0.78-0.85 s가 된다. 앞쪽 PR에 넣는다.
- 기동과 빌드: [실측 혼자] `stack.sh up` 35 s(초안의 41-44 s는 경합), 콜드 `tools/ros_ws.sh build` 42.0 s(초안의 94 s는 경합), 빌드 컨테이너 `memory.peak` 1851 MiB(페이지 cache 포함. 초안의 871 MiB는 `docker stats` 값이라 직접 비교하지 않는다), 호스트 available 최소 4459 MB.
- Lichtblick: 이미지 안의 Lichtblick은 1.30.0이다. "2.5.2"는 바탕 이미지 Caddy의 label이다(devops, sim 각각 [실측]). `versions.env`에는 `LICHTBLICK_IMAGE=ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:25333a8f...` 꼴로 고정한다. `docs/architecture.md` 106행과 progress.md 결정 기록(2026-11-06)의 표기를 고친다. foxglove_bridge 3.6.0은 `foxglove.sdk.v1`만 받는다([실측] 둘).
- GHCR: 이미지 넷이 이미 익명으로 조회된다(devops [실측]). README의 사용자 결정 후보 1과 D13은 닫는다. 패키지 visibility API로는 확인하지 못했으므로(토큰 권한) 사용자에게 사실만 알린다.
- B9: "`idsim_mission`이 두 header를 include하면 tidy가 본다"는 틀렸다(ros2 [실측]: 소비자에서는 `-isystem`과 설치 경로 때문에 보고되지 않는다). `idsim_common`에 공개 header 전부를 include하는 TU를 하나 두어 닫는다.
- roadmap의 "모드 전환 전 최소 10회"는 PX4 예제의 관례이고 v1.17.0의 조건이 아니다(px4 [소스]).

### 11. 그 밖의 충돌

11-1. `foxglove` 허용 목록의 표기
- 결정: 생성기가 `stack.json`의 기체 네임스페이스마다 줄을 만든다(기체 번호 규칙을 정규식에 넣지 않는다). 이 부분은 ros2 안 그대로다. PX4 토픽은 개별 이름을 적지 않고 접두사 한 줄 `^<ns>/fmu/(in|out)/`만 낸다. idsim 토픽은 이름으로 적는다(`^<ns>/mission_event$`, `^<ns>/execute_mission/_action/(status|feedback)$`). `/clock`은 넣지 않는다([실측] sim: 서버가 `time` capability로 시각을 보낸다). capabilities는 `[connectionGraph]`, 빈 허용 목록은 생성기가 거부한다. 단정 6종은 devops D6대로.
- 접두사만 쓰는 이유: ros2 안은 생성기에 PX4 토픽 이름(`vehicle_local_position` 등)과 version suffix 규칙을 리터럴로 두게 된다. 그것은 `docs/architecture.md`의 "PX4 토픽 이름은 `idsim_common`이 유일한 접근 경로"와 맞지 않고, 같은 이유로 layout 파일을 거부한 11-2와도 일관되지 않는다. 접두사는 메시지 이름도 버전도 담지 않으므로 `PX4_TAG`가 바뀌어도 고칠 것이 없다.
- 남는 예외: 생성기에 `fmu/(in|out)/` 접두사 리터럴 하나가 남는다. 원칙의 예외로 적는다(문서 반영 목록). 조건은 셋이다. (1) 읽기 전용 표시 필터에만 쓴다(`foxglove`는 clientPublish, services, parameters를 열지 않는다). (2) 생성기의 함수 한 곳에만 있고 생성기 단정이 "`fmu/` 문자열은 foxglove 허용 목록 밖의 산출물(params, command, environment)에 없다"를 본다(6번의 단정과 같은 것). (3) 노드와 테스트는 이 문자열을 쓰지 않는다.
- 넓어지는 것: 기체 네임스페이스의 `/fmu` 아래 토픽이 모두 화면의 목록에 보인다. foxglove_bridge가 client가 고른 토픽만 구독한다는 것은 [추정]이다. sim이 작업 단위 F의 실접속 확인에서 구독 수를 본다. 다르면(허용된 토픽을 모두 구독하면) 접두사를 `fmu/out/`과 `fmu/in/trajectory_setpoint` 수준으로 좁히는 대신 ros2 안으로 돌아가지 않고 architect에게 올린다.

11-2. Lichtblick 컨테이너와 layout 파일
- 결정(초안 그대로): 6단계에는 layout 파일을 저장소에 두지 않는다(기체 식별자와 접미사 붙은 토픽 이름이 `config/fleet.yaml`과 mapping 밖에 리터럴로 생긴다). 육안 확인 절차에 "Plot에 두 경로를 더한다"를 적는다. layout은 3대 화면이 필요해질 때 생성기 산출물로 다시 본다. 컨테이너 구성은 devops 안(command를 `caddy file-server --listen 127.0.0.1:<포트>`로, host 네트워크)이다.

11-3. `sitl` job에서 이미지 key가 없을 때
- 근거 [소스] devops: PR의 build job은 이미지를 올리지 않고(`push: false`) `--load`도 하지 않는다. 그래서 `needs: build`를 걸어도 받을 이미지가 없다. fork PR에는 쓰기 토큰이 없다. unit job은 key가 없으면 `build_images.py --mode load ros-ws`로 빌드한다([실측] PR run에서 544 s). main에 branch protection과 ruleset이 없다([실측]).
- 결정: 이미지별로 나눈다.
  1. ros-ws, xrce-agent의 key가 없으면 `sitl` job 안에서 `--mode load`로 빌드하고 진행한다. 6단계에서 바뀌는 이미지는 ros-ws뿐이라 그 PR 자신의 `sitl`이 실제 이미지로 판정된다. PR 권한(read)만 쓰므로 fork PR에서도 같다.
  2. px4, sim-base의 key가 없으면 빌드하지 않고 실패로 둔다. 건너뛰기로 두지 않는다(통과처럼 보인다). 메시지로 "로컬 `run_sitl.sh` 결과를 PR 본문에 붙이고, main 머지 뒤 main의 `sitl`이 판정한다"를 남긴다. 이유: px4 빌드만 15-20분[추정]이라 시간 한도 안에 들지 않는다.
  3. job `timeout-minutes`는 35(빌드 분기 약 9분 + 이미지 받기 + 테스트 단계 15분), 테스트 단계의 제한은 15분 그대로다.
  4. trigger: PR은 `pull_request`, main은 `workflow_run`(build 완료, 성공), 그리고 `workflow_dispatch`. main push에서 build와 동시에 돌면 새 key를 받지 못하기 때문이다. 초안 D7의 "main push"를 고친다.
  5. 받지 않는 안: PR에서 별도 이름공간에 push(fork에서 안 되고 오염 경로가 생긴다), `docker save`를 artifact로 넘기기(px4 3.07 GB. [미측정]).
- `sitl`을 필수 검사로 둘지는 사용자 7.

11-4. 취소된 기체를 내리는 방법
- 결정(초안의 잠정을 닫는다): `[LAND]` 하나짜리 미션을 action으로 보낸다. Executor는 Hold의 공중 기체에서 그 미션을 받는다(2번의 PREPARING. [실측 혼자] 3/3). 로컬 SITL의 공중 취소 시나리오는 같은 시나리오 안에서 `[LAND]` 미션을 이어 보내 기체를 내린다. teardown은 NAV_LAND를 직접 보내지 않는다(T7). 취소가 "지면 위 armed, Hold 모드"로 끝난 경우에도 같은 미션으로 내려진다([실측 혼자] 3/3. 2번).

11-5. `last_item_index`의 구분 필드(C22)
- 결정(초안 그대로): 두지 않는다. 1a의 미션에서 arm과 Offboard 진입 실패는 PREPARING에서만 나고, 구분을 읽는 소비자가 없다.

11-6. 고도의 독립 판정과 `acceptance_m`
- 근거 [실측 혼자] test, 8회: "goal 직전 z"와 "arm 시점 z"의 차는 최대 0.031 m(사이 0.92-0.97 sim s). arm 전 지상 z의 범위는 1 s 창 0.009-0.034 m, 10 s 창 0.191-0.243 m. goal 직전 z와 착지 뒤 z의 차는 최대 0.400 m다(px4의 "60 s에 최대 0.28 m"보다 크다). 정착 뒤 추종 오차 -0.097 - +0.031 m, overshoot 최대 0.031 m. arm에서 도달 판정까지 7.60-7.82 sim s(5회).
- 결정
  - 판정의 `z0`는 goal 전송 직전 0.5 sim s 안의 `z_valid` 표본 5개 이상의 중앙값이다. arm 시점을 쓰지 않는다(판정이 Executor의 단계에 기대게 된다).
  - `acceptance_m`은 0.3 m를 유지한다. 근거는 추종 오차 0.097 m와 기준점 차 0.031 m의 합 0.13 m에 2배 남짓의 여유다. 좌표계의 이동(0.28-0.40 m)은 Executor와 판정이 같은 좌표계를 쓰므로 들어가지 않는다. 0.3 m가 그 크기와 비슷한 것은 우연이고 그것을 덮는 값이 아니다.
  - 기준점의 잘못을 잡는 판정을 더한다: 하네스가 `trajectory_setpoint`를 구독만 하고, TAKEOFF 실행 중 setpoint의 z와 `z0 - height_m`의 차가 0.1 m 이하인지 본다. 0.1 m는 [추정]이고(기준점 차 0.031 m와 1 s 창 0.034 m에 여유) 실제 Executor로 다시 잰다. 값을 넓혀야 한다면 독립 기준의 오차로 설명되어야 한다. "TAKEOFF 실행 중"을 가르는 방법(feedback의 `phase`)은 test와 px4가 구현 검토에서 정한다.
  - 실제 지면 위 높이(Gazebo pose)의 판정은 6단계에 넣지 않는다(bridge 설정 파일이 1b이고, 허용값이 좌표계 이동을 더해야 해 판정 힘이 약하다).

## 근거로 닫은 그 밖의 결정

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| A5 모드 명령 | DO_SET_MODE 유지. builder 밖에서 만들지 않는다 | px4 P3 [소스], [실측] 5/5 |
| A9 신호 없는 Offboard 요청 | armed이면 TEMPORARILY_REJECTED, disarm이면 ACCEPTED. 모드 명령은 ack와 `nav_state`를 둘 다 확인한다 | px4 P2 [실측] 5/5 |
| A4, B3 source 값 | Executor 250/1, pytest 하네스 251/1, 손으로 보내는 CLI 252/1, `check_px4.py` 254/1. 금지: (대상 기체 sysid, 1), system 1-99, (255, 190), component 1000 이상, `from_external` 거짓. 기체가 달라도 Executor끼리는 같은 값. 상수는 `idsim_common` 한 곳에 둔다 | px4 P11 [소스], [실측] |
| B2 `from_external` | 주석의 근거 확인됨 | px4 P11 [소스] |
| C4 Hold에서 벗어나는 경로 | 위치 추정 무효, 외부 모드 명령, 자세 무효, disarm. 배터리, geofence, 바람, 비행 시간은 이 파라미터에서 꺼져 있거나 닿지 않는다 | px4 P10 [실측], [소스] |
| `SIM_BAT_MIN_PCT` | `sitl_params.env`에 50을 명시하고 S4 기대값에 넣는다. 반복 비행과 공유 스택이 이 값에 기대고 있다. 구현은 px4 | px4 P10 |
| A6, B4 setpoint helper | `idsim_common/px4_setpoint.hpp`의 `make_position_setpoint(Px4Timestamp, 로컬 NED 위치, yaw)`. position만 참, 나머지 NaN, 입력의 NaN과 무한대 거부. 상태 없는 함수이고 "언제 내는가"는 2번의 규칙으로 Executor가 지킨다 | ros2 R6 |
| R10 컨테이너 사이의 action | 맺어진다. 리스크 표의 행을 닫는다. `result_timeout`은 수락 직후 결과 요청으로 피한다 | ros2 [실측] 1회, test [실측] |
| R13 참가자 수 | 1대 7, 3대 13 예상. `MaxAutoParticipantIndex` 50에 여유. 표식 healthcheck는 참가자를 만들지 않는다 | ros2 [실측] |
| C11 이름 상수 | `.clang-tidy`에 `cert-err58-cpp`를 더한다. 이름 상수는 함수 안에서만 쓴다 | ros2 R11 [실측](`idsim_common` 0건). `.clang-tidy` 변경은 devops 검토 |
| R12 tidy 범위 | `idsim_mission`의 `test/`는 처음부터 tidy 대상. 기존 `idsim_common/test/`는 건수를 본 뒤 | ros2 [실측] |
| T2 시계 | `tests/support`의 `SimClock`(전용 노드, 전용 spin thread). 벽시계 상한은 안전망이고 걸리면 `ClockStalled` 예외(판정 실패와 구분). 상한은 "sim 타임아웃 / 0.25 + 30 s"(RTF 0.25는 [추정]이다. runner의 RTF는 [미측정]이고 첫 `sitl` 실행의 기록으로 다시 본다) | test [실측]. sim의 끊김 최대 25.9 ms로 바꿀 근거 없음 |
| T3 타임아웃 | 테스트 미션의 TAKEOFF `timeout` 30 s, LAND 45 s(ROS 시각). 판정 타임아웃은 항목 `timeout` 이상 | [실측 혼자] 도달 7.60-7.82 s(3.8배 여유), 5 m에서 disarm까지 11.16-11.24 s |
| T8 Python 이름 | `MESSAGE_VERSION`에서 접미사를 파생하는 함수를 `tests/support/px4_names.py`에 두고 golden과 비교하는 단위 테스트를 둔다. 표는 6단계가 쓰는 토픽만. 구독용 함수와 발행용 함수를 나눈다(9번) | test [실측] 65/65 |
| T5 층 배치 | PR마다 SITL: 정상 비행, BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION. 단위: 실패 경로와 취소 분기. 로컬 SITL: 공중 취소(뒤에 `[LAND]` 미션), 지상 취소. 로컬 전용 별도 스택: `tests/px4_facts/`. 범위의 확정은 사용자 1 | test T5와 재질문 답 |
| D5 이미지 | foxglove_bridge는 px4_ws 빌드 RUN 뒤의 별도 RUN, apt 버전은 고정하지 않고 S0이 `dpkg-query` 버전을 남긴다. 이미지 변경은 앞쪽 PR. 크기 증가는 사용자 4 | devops [실측] 49.6 MB |
| D7 `sitl` job의 틀 | trigger와 이미지 정책은 11-3. concurrency는 ref 단위, PR은 진행 중인 것을 취소. unit job과 빌드를 나눠 쓰지 않는다. 재시도는 수동 | devops |
| D11 lint, unit 이중 실행 | 6단계 범위 밖. 별도 PR | devops |
| S1 `/clock` 주기 | 낮추지 않는다. `PX4_SIM_SPEED_FACTOR`는 1a에서 쓰지 않는다 | sim [실측 혼자] bridge CPU 11%, RTF 0.998-0.999 |

## 5단계 계약에 반영할 변경 (작업 단위 H-1, H-2에서 반영)

바뀌는 필드와 상수는 K13 하나다(result 끝의 `end_state`와 `END_STATE_*` 셋. ops 조건 C1). 그 밖은 의미 문장과 주석이다. K13은 golden을 바꾸므로 작업 단위 H-1로 먼저 반영하고(아래 "K13의 반영 절차"), 나머지는 H-2에서 반영한다. H-2의 반영은 golden을 바꾸지 않을 것으로 본다([추정]. 주석만 바뀐다. 반영 때 계약 테스트로 확인한다).

5단계 `decisions.md` 쟁점 9

| 번호 | 지금 문장 | 바꿀 내용 | 근거 |
| --- | --- | --- | --- |
| K1 | 공중 취소는 "setpoint 발행을 유지한 채 Hold" | setpoint는 Hold가 확인될 때까지만 유지하고 확인되면 즉시 멈춘다 | 2번. [실측] 5/5(멈추지 않으면 착지 판정이 서지 않는다) |
| K2 | failsafe 동작 중의 취소는 Hold 확인 실패와 같은 경로(잠정) | 모드 명령을 보내지 않고 ABORTED, FAILSAFE. 잠정 표시를 지운다 | 2번. 사용자 5 |
| K3 | 지상 armed 취소는 disarm 확인 뒤 CANCELED(거부 때의 분기 없음) | setpoint를 내던 중이면 disarm 확인까지 유지한다. disarm이 거부되거나 2 s 안에 확인되지 않으면 다시 보내지 않고, 상태가 신선하면 착륙 절차(Land 명령, disarm 확인)로 끝낸 뒤 CANCELED, 아니면 LINK_LOST. 확정 | 2번. px4 P5 [실측], E5 5/5, E4 (가) 6/6(거부 뒤 Offboard 유지). 옛 규칙의 폐기 근거는 E4 (나) 6/6(failsafe를 거친다). 거부 직후의 NAV_LAND는 E3 (나)와의 조합이고 직접 잰 회차는 없다 |
| K4 | (없음) | 지상이 아닌 기체의 취소는 실행 중인 항목으로 가른다. TAKEOFF(도달 판정 전)와 LAND: Hold를 보내지 않고 착륙을 끝낸 뒤(disarm 확인) CANCELED. LOITER: Hold 확인 뒤 CANCELED(착지 판정 신호가 하나라도 서 있으면 착륙을 끝낸다). 착륙을 끝내지 못하면 ABORTED. 관찰 창은 두지 않는다. GOTO, TRACK_ENTITY, RTL 실행 중의 취소는 1b에서 정한다 | 2번. [실측 혼자] E1, E3, E4(지면 위 armed Hold 8/9, 12/12, 6/6. 신호가 선 회차 0/33). NAV_LAND 36/36, 18/18 |
| K5 | "CANCELED로 끝난 기체는 공중에서 Hold로 남는다" | CANCELED로 끝난 기체는 지상 disarm이거나 armed, Hold 모드다. armed Hold로 끝나는 것은 LOITER 실행 중의 취소와, 첫 항목이 LAND인 미션에서 Land 명령 전의 취소뿐이다. Hold 모드로 남은 기체를 내리는 것은 취소를 요청한 쪽의 책임이고 방법은 `[LAND]` 미션이다. "Hold 모드의 기체는 공중에 있다"는 적지 않는다. 확정 | K4, 11-4. "결과의 처리" 둘째 줄. 공중 Hold의 실측 범위는 2번 |
| K6 | "LAND와 RTL: 지상 판정 뒤 disarm 확인까지가 한 항목이다(자동 disarm을 기다린다)" | LAND: 지상 판정 뒤 정해진 시간 안에 자동 disarm이 없으면 비강제 disarm을 보내고, 그래도 안 되면 ITEM_TIMEOUT. Land 명령이 확인되지 않으면 MODE_SWITCH_FAILED. RTL의 문장은 1b에서 정한다 | 2번. 사용자 5 |
| K7 | (없음) | 첫 항목이 LAND인 미션의 시작 조건: armed, 지상 아님, 비행제어가 Hold 모드. 아니면 PRECONDITION_FAILED. 이 미션은 Offboard 진입과 arm을 하지 않고 setpoint를 내지 않는다. 조건은 뒤에 넓힐 수 있다(Hold가 아닌 모드로 공중에 남은 기체) | 2번. [실측 혼자] 3/3. 지상의 경우는 [미측정]. ops 소비자 검토(작업 단위 D, H) |
| K8 | TAKEOFF "시작 위치 위 `height_m`" | "시작 위치"는 arm 직전의 로컬 위치다. `acceptance_m` 기본값 0.3 m의 [추정]을 [실측]으로 | 2번, 11-6 |
| K9 | [추정] 두 줄(failsafe 진행 중의 Hold 동작, Hold 확인 타임아웃 값) | [실측]으로: failsafe Land 중의 Hold는 받아들여진다(5/5), 위치 무효에서는 거부된다(1회). 타임아웃 기본값 2.0 s. "취소의 분기는 잠정" 문장을 지운다 | px4 P4 |
| K10 | Hold에서 벗어나는 경로의 "아직 대조하지 않았다" | 대조 결과(C4)로 바꾼다 | px4 P10 |
| K11 | `reason`의 의미(세부 없음) | 실행 중 이상의 판정 순서(LINK_LOST -> FAILSAFE -> EXTERNAL_MODE_CHANGE). active 뒤의 식별 불일치와 ROS 시각의 역행은 LINK_LOST. PX4 재기동은 따로 감지하지 않고 상태 미수신(LINK_LOST)으로 드러난다. 신호 유효 확인 실패와 Land 명령 미확인은 MODE_SWITCH_FAILED. NOT_READY와 PRECONDITION_FAILED의 조건표 | 2번, 5번, 1번 |
| K12 | PREPARING의 순서(넘김) | 식별 대조 -> 준비 확인 -> 첫 항목의 시작 조건 -> (setpoint 항목이면) 기준점, setpoint 시작, 신호 유효, Offboard 전환, arm | 2번 |
| K13 | result에 끝 상태가 없다(11-5의 C22와는 다른 필드) | result 끝에 `uint8 end_state`와 상수 `END_STATE_UNKNOWN` 0, `END_STATE_GROUND_DISARMED` 1, `END_STATE_ARMED_HOLD` 2를 더한다. CANCELED와 SUCCEEDED는 0이 아니다(1a의 SUCCEEDED는 항상 1). ABORTED는 Executor가 끝낼 때 확인한 값이 있으면 싣고 없으면 0이며, 약속이 아니라 관측값이다. 2는 공중을 뜻하지 않는다 | 2번 "ops 검토로 더한 규칙". ops 조건 C1(의견 2) |
| K14 | 취소 처리 중의 이상 판정이 적혀 있지 않다 | 취소 처리 중(CANCELING)에도 LINK_LOST, FAILSAFE, EXTERNAL_MODE_CHANGE 판정이 실행 중과 같은 순서로 돌고, 걸리면 그 `reason`의 ABORTED다. 취소 요청 뒤의 MODE_SWITCH_FAILED는 Land 명령을 보냈다는 뜻이다(착륙의 결과는 확인하지 않았다) | 2번. ops 조건 C2(의견 3, 5) |
| K15 | 취소 요청부터 result까지의 시간이 적혀 있지 않다 | 상한이 있다: Hold 확인 제한 + disarm 확인 제한 + 착륙 제한(LAND 항목 실행 중이면 그 항목의 `timeout`, 그 밖에는 취소 착륙의 제한 시간)의 합을 넘지 않는다. ROS 시각이고 값은 노드 파라미터다(계약의 숫자가 아니다) | 2번. ops 조건 C2(의견 3) |
| K16 | `last_item_index` "끝날 때 실행 중이던 항목", `items_completed` "완료한 항목 수"(취소의 경우 없음) | 취소로 끝난 goal의 `last_item_index`는 취소 요청을 받았을 때 실행 중이던 항목이고 `items_completed`에 그 항목을 세지 않는다. 취소로 시작한 착륙은 미션의 LAND 항목 실행이 아니다 | 2번. ops 조건 C3 |
| K17 | "feedback 주기는 계약이 아니다"(취소 중의 feedback, 취소 요청의 수락 없음) | 취소 처리 중에도 feedback을 낸다(`phase` CANCELING, `item_index`와 `item_type`은 취소 시점의 항목, `distance_valid` 거짓). 실행 중인 goal의 취소 요청은 조건 없이 받는다. 거듭된 취소 요청은 실행을 바꾸지 않고, 요청한 쪽은 그 응답 코드를 실패로 다루지 않는다 | 2번. ops 의견 3. 거듭된 요청의 응답 코드는 [추정](ros2가 작업 단위 D에서 실측) |
| K18 | (없음) | goal이 끝난 뒤(SUCCEEDED, CANCELED, ABORTED 모두) Executor는 그 goal로 비행제어에 setpoint도 명령도 내지 않는다 | 2번의 발행 규칙. ops 의견 5 |

`ExecuteMission.action` 주석

| 번호 | 지금 주석 | 바꿀 내용 |
| --- | --- | --- |
| N1 | 취소 세 줄과 "(취소의 분기는 1a 고정 전까지 잠정이다.)" | K1-K5를 줄인 문장으로 바꾸고 잠정 줄을 지운다. 초안: "취소: LOITER 실행 중이면 Hold 모드를 확인한 뒤 CANCELED(확인되면 setpoint를 멈춘다). 확인되지 않으면 Land 명령 뒤 ABORTED(REASON_MODE_SWITCH_FAILED). TAKEOFF나 LAND 실행 중이면 Hold 대신 착륙을 끝낸 뒤 CANCELED. failsafe 동작 중이면 명령 없이 ABORTED(REASON_FAILSAFE). 지상에서 arm 상태이면 disarm을 확인한 뒤 CANCELED(거부되면 착륙 절차로 끝낸다). 취소 처리 중에도 실행 중 이상(LINK_LOST, FAILSAFE, EXTERNAL_MODE_CHANGE)은 ABORTED로 끝낸다." K15, K17, K18은 주석에 넣지 않고 `docs/interface.md`에 적는다 |
| N2 | `PHASE_PREPARING = 1  # 식별 대조, arm, Offboard 진입` | "식별 대조, 준비 확인, Offboard 진입, arm(첫 항목이 모드 명령 항목이면 뒤의 둘은 없다)" |
| N3 | `PHASE_CANCELING = 4  # 취소 요청 뒤 정리 중` | 그대로 둔다. 취소로 착륙을 끝내는 동안도 이 단계다(수십 초가 될 수 있다). 이 단계에서도 feedback을 낸다(K17. 문서는 7단계 `docs/interface.md`) |
| N4 | `REASON_*`의 주석 | 바꾸지 않는다. K11의 세부는 `docs/interface.md`에 적는다 |
| N5 | result의 끝이 `string detail` | `detail` 뒤에 더한다(H-1). 상수 셋과 필드 한 줄: `uint8 END_STATE_UNKNOWN = 0  # 확인한 것이 없다`, `uint8 END_STATE_GROUND_DISARMED = 1  # 지상 판정 뒤 disarm을 확인하고 끝냄`, `uint8 END_STATE_ARMED_HOLD = 2  # arm 상태와 Hold 모드를 확인하고 끝냄. 공중이라는 뜻이 아니다`, `uint8 end_state  # END_STATE_*. SUCCEEDED와 CANCELED이면 UNKNOWN이 아니다. ABORTED이면 끝낼 때 관측한 값이거나 UNKNOWN` |
| N6 | `uint32 items_completed  # 완료한 항목 수`, `uint32 last_item_index  # 끝날 때 실행 중이던 항목(0부터). 항목을 시작하기 전에 끝났으면 0` | `items_completed`: "완료한 항목 수. 취소된 항목은 세지 않는다". `last_item_index`: "끝날 때 실행 중이던 항목(0부터). 취소로 끝났으면 취소 요청을 받았을 때의 항목. 항목을 시작하기 전에 끝났으면 0"(H-2. 주석만) |

그 밖
- 5단계 쟁점 8의 `MissionEvent`: 바꾸지 않는다. "Executor가 죽거나 스택이 내려가면 접수 사건만 남는다"가 5번의 종료 처리(최선 노력)를 이미 덮는다. `end_state`는 싣지 않는다(2번 "ops 검토로 더한 규칙". Phase 2 초반에 logging-engineer와 정한다). 종료 사건과 result의 일치 단정(C20)의 대상 필드도 그대로다.
- `docs/architecture.md` 165행의 취소 문장은 K1-K5로 고친다.
- `C22`(`last_item_index`의 구분 필드)는 두지 않는다. result의 변경은 K13 하나다.

K13의 반영 절차(작업 단위 H-1. 5단계 쟁점 10과의 대조)
- 쟁점 10에 맞는다. (1) 필드를 끝에 더한다(기존 필드의 이름, 타입, 순서, 의미는 그대로). 이 규칙은 고정 뒤에도 허용되는 변경이다. (2) `ExecuteMission`은 1a 완료에 고정되므로 아직 고정 전이다. 사유는 "첫 소비자의 구현에서 드러난 문제"다: 6단계의 추가 실험으로 CANCELED의 끝 상태가 하나에서 둘로 갈렸고, 소비자(ops) 검토가 기존 필드로는 둘을 가를 수 없다는 것을 보였다. (3) 상수는 추가만이고 값 0은 `*_UNKNOWN`이다(상수 검사 4번의 규칙과 맞는다). (4) 예약 필드를 두지 않는다.
- 바뀌는 golden: `type_hashes.txt`의 `ExecuteMission`과 result를 품은 파생 타입 줄(`_Result`, `_GetResult`, `_GetResult_Response`, `_GetResult_Event` 등. 실제 목록은 갱신 결과로 확인한다), 펼친 정의 `golden/action/ExecuteMission.txt`, 직접 정의 `golden/direct/action/ExecuteMission.txt`. msg 쪽 golden은 하나도 바뀌지 않아야 한다(바뀌면 잘못이다). 직접 정의 golden이 바뀌므로 전파가 아니라 계약 변경으로 드러나는 것이 맞다.
- 갱신은 `tools/ros_ws.sh shell` 안에서 `IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces`로만 한다. 경고 "golden 갱신됨"에 찍힌 파일이 위 목록과 같은지 PR 본문에 적는다.
- 계약 테스트에 상수 검사를 더한다: `ExecuteMission` result의 `END_STATE_*` 집합 == {`END_STATE_UNKNOWN`: 0, `END_STATE_GROUND_DISARMED`: 1, `END_STATE_ARMED_HOLD`: 2}(`TYPE_*` 집합 검사와 같은 모양. 상수를 더하면 여기서 실패해 Executor와 Fleet의 대응을 함께 고치게 한다). 값 0과 접두사 안의 값 중복은 지금 있는 두 검사가 이미 본다.
- 쟁점 10이 계약 변경 PR에 요구하는 것: golden 갱신(이 PR), `docs/interface.md`(아직 없다. 7단계의 대상 목록에 K13-K18을 올린다), `progress.md` 결정 기록(호출한 쪽), proto와 replay fixture(해당 없음. action은 replay 입력이 아니고 proto는 Phase 3), architect 승인.
- 시점: H-1은 작업 단위 D(노드)보다 먼저 합친다. 노드가 result에 값을 채우려면 정의가 먼저 있어야 한다. 사용자 5의 (5)가 (나)나 (다)로 정해져도 끝 상태가 둘인 것은 같으므로 H-1은 그 결정을 기다리지 않는다. 취소 주석(N1)은 사용자 5에 걸려 있어 H-2에 남긴다.
- Phase 3의 proto에서는 result의 다섯째 필드이고(필드 번호 5) enum의 0은 `END_STATE_UNSPECIFIED`다(쟁점 10의 proto 규칙).

## 재질문에서 넘어온 미해결(비차단)

| 항목 | 내용 | 받는 쪽 | 시점 |
| --- | --- | --- | --- |
| `vehicle_status` 전이 메시지의 `timestamp` | 수신 시각보다 152-196 ms 앞서는 원인([소스]). 단조 여부는 닫혔다(reviewer [실측] 역행 0/5290) | px4 | 6단계 안, 비차단(이것에 달린 결정이 없다) |
| hrt가 멈춘 px4의 종료 | Gazebo가 먼저 죽어도 종료 코드 0, ULog 온전(4/4). [소스]로는 설명되지 않는다 | px4 | 6단계 안, 비차단 |
| px4 기동 중 139 | devops의 21회 중 1회. 같은 실행 디렉터리를 18회 다시 쓴 조건이고 재현 여부를 모른다 | px4 | 재현되면 장애 분석. `sitl` 기록에서 감시 |
| gazebo stop 5.2 s | 21회 중 1회(나머지는 0.2 s, 종료 코드 143) | sim | 알림만 |
| rclpy 탐침의 종료 코드 139 | px4 탐침에서 2회(시나리오 끝 뒤 rclpy 종료 중). 기록은 온전 | test | 하네스의 종료 순서(T7 3번)로 막고, `sitl`의 판정은 pytest 종료 코드와 junit을 함께 본다 |
| `landed`가 섰다가 풀리는 경로 | 닫힘. [실측, ULog] E1: Hold에서는 추력이 호버 근처로 남고 `in_descend`가 0.5 s 안에 거짓이 되어 `ground_contact`가 서지 않는다. [소스] `MulticopterLandDetector.cpp` `_get_ground_contact_state()`와 맞는다 | px4 | 닫힘 |
| 접수 사건 유실률, 첫 setpoint z의 0.1 m, `px4_facts` 스택에서 Executor가 발행하지 않는다는 것 | 실제 Executor가 생긴 뒤 다시 잰다 | test | 작업 단위 E, P |
| runner에서의 기동 시간, RTF, 이미지 받기 | [미측정] | devops | 첫 `sitl` 실행의 기록 |
| Phase 2에 Collector가 같은 프로세스에 합류할 때의 구조(A13) | 자기 전이(`main`의 configure 한 번과 재시도 timer)와 표식 파일 하나가 노드 둘에서도 맞는지 | ops(의견 ros2) | 작업 단위 D의 ops 검토 항목. 결정은 Phase 2 |
| 지상 취소 뒤(disarm, `nav_state` 14)의 다음 TAKEOFF goal | PREPARING이 통과하는지 [미측정] | test, px4 | 작업 단위 E의 로컬 지상 취소 시나리오 |
| ROS 시각 역행 때 ROS 시각 timer의 동작 | [미측정] | ros2 | 작업 단위 D |
| battery_simulator의 주기 실행 정지 | [실측] 7회(추가 실험의 시험 스택과 본 측정). `battery_status` 발행이 멈추고 5 s 뒤 `battery_unhealthy`, arm 거부 또는 spoolup 안이면 failsafe disarm(`latest_disarming_reason` 14). 앞선 라운드(r1-r5, r1-r3)에서는 0회. 원인은 [추정](hrt 주기 호출의 정지)이고 조건은 "몇 초 전의 arm-disarm"밖에 찾지 못했다. `sitl`의 NOT_READY, ARM_REJECTED 플래키 원인 후보 | px4(원인 규명. 장애 분석 절차), test(판정 실패 때 `battery_unhealthy`를 원인으로 따로 적기, 시나리오 사이의 arm-disarm 간격과 스택 재기동 여부), devops(`sitl` 실패 artifact에 `battery_status`가 든 ULog가 남는지, 재현 때 반증 실험) | 원인 규명은 작업 단위 E 전. 못 찾으면 E의 판정이 원인을 구분해 적는 것으로 진행하고 사용자 7을 다시 올릴 때 발생 횟수를 붙인다. 사용자 결정은 지금 필요 없다(아래 "알릴 것") |
| 낮은 `height_m`의 LOITER 취소 | `height_m`이 `acceptance_m` 이하이면 TAKEOFF 도달 판정이 지면에서 서고, 그 뒤 LOITER 중의 취소는 Hold 줄로 가 지면 위 armed Hold가 될 수 있다([추정]. E3 (가)의 상태와 같다). 호버가 0.5 m 아래인 Hold도 [미측정]. 기본 제안: 1a 임시 규칙으로 `height_m`의 하한을 둔다(값은 px4가 실측 범위에서 제안. 계약 문장이 아니다) | px4(값과 근거), ros2(임시 규칙의 위치. 항목 순서 규칙과 같은 함수) | 작업 단위 C. K5는 공중을 약속하지 않으므로 계약은 막지 않는다 |
| 취소 착륙의 제한 시간, disarm 거부 직후의 NAV_LAND | 제한 시간 기본 45 s는 [추정]. 거부 직후에 곧바로 NAV_LAND를 이은 회차는 없다(E4 (가)는 Hold를 거쳤다) | px4 | 작업 단위 C-2의 단위 테스트와 E의 로컬 지상 취소 시나리오 |
| `MissionEvent` 종료 사건의 끝 상태 | result의 `end_state`를 종료 사건에도 실을지. Jazzy rosbag2는 action result를 기록하지 않으므로 싣지 않으면 기록물에서 끝 상태를 알 수 없다. architect의 권고는 "인덱스가 표시하거나 거를 값이면 싣는다"다 | logging(소비자), architect, ops | Phase 2 초반(인덱스 prototype 때. `MissionEvent`의 고정 전) |
| 거듭된 취소 요청의 응답 코드 | CANCELING인 goal과 끝난 goal에 온 취소 요청에 action 계층이 무엇을 돌려주는지([추정] ERROR_REJECTED, ERROR_GOAL_TERMINATED 또는 ERROR_UNKNOWN_GOAL_ID) | ros2 | 작업 단위 D. 결과를 K17의 문장에 반영 |
| Fleet의 취소 감시 | 상한(K15)의 세 값은 Executor의 노드 파라미터다. Fleet이 그 값을 어디서 얻는지(Executor의 값을 리터럴로 베끼지 않는다)와, 감시 시간의 시계(`/clock`이 멈추면 ROS 시각의 상한은 서지 않는다) | ops, architect | Phase 3 설계 토론 |
| Hold 기체에 곧바로 주는 비행 미션 | 1b에서 armed Hold의 기체가 `[GOTO, ...]`를 받게 하려면 정할 것 셋(ops 의견 4). (1) 시작 조건: `arming_state` 2, `landed` 거짓, `nav_state` 4, `failsafe` 거짓, 위치 유효와, 공중임을 Executor가 확인할 근거(K5가 공중을 약속하지 않으므로 지면 위 armed Hold를 Executor가 막는다. Fleet은 판정하지 않는다). (2) PREPARING 경로: arm을 건너뛰고 현재 위치의 setpoint로 시작해 신호 유효와 Offboard 진입을 확인한다(Hold에서는 `offboard_control_signal_lost`가 참에서 시작한다. px4 실측 대상). (3) 기준점: arm 직전 위치가 없는 goal에서 좌표의 기준 | px4, ros2, ops, architect | 1b 설계 토론. 1a의 Fleet 쪽 첫 구현은 Hold 기체를 `[LAND]`로 내린 뒤 다시 배분한다 |
| `VehicleState`의 복귀 판정 필드 | ABORTED로 격리한 기체의 복귀 판정(지상 disarm의 지속)에 arm 상태, `landed`, 모드(Hold 여부)와 각 유효 flag가 필요하다(ops 의견 5). 지금 정의에는 `arming_state`, `flight_mode`, `failsafe`, `landed_valid`, `landed`가 있다. 모자란 것이 있는지는 Phase 2 스키마 검토에서 본다 | ops, architect | Phase 2(`VehicleState` 고정 전) |

## 추가 실험 (px4-engineer. 작업 단위 C-2의 취소 분기 구현 전)

목적: 2번 취소 표의 [미측정] 구간을 닫는다(reviewer M2). 묻는 것은 셋이다. (가) 세 신호가 모두 거짓인 낮은 높이의 Hold가 어떻게 끝나는가, (나) 관찰 창이 그것을 잡는가, (다) disarm이 거부된 뒤의 경로가 표대로 가는가.

공통 조건
- 스택 k=1 하나만 올린다("혼자"). load1을 5 s 간격으로 남긴다. 시간 값은 PX4 timestamp와 ROS 시각 축으로 적는다.
- 탐침은 재질문 때의 `probe/probe2.py`를 고쳐 쓴다. 명령 source는 하네스 값 251/1.
- 높이는 지면 기준이다. 지면 z는 그 회차의 "착지하고 disarm한 뒤의 z"로 잡고, "arm 직전의 z"도 함께 적는다(둘의 차가 0.4 m까지 났다. 11-6). 송신 시점은 "지면 z + 목표 높이를 지나는 첫 표본"이다.
- 회차마다 적는 것: 명령 송신 시각, ack와 그 시각, `nav_state` 전이 시각, 송신 시점의 z, vz, 세 신호(`ground_contact`, `maybe_landed`, `landed`), `nav_state`. 송신 뒤 10 s 동안의 z 최소와 10 s 뒤의 z, 세 신호 각각이 처음 참이 된 시각과 다시 거짓이 된 시각(송신 기준), `arming_state`, `failsafe`, `failsafe_flags.offboard_control_signal_lost`.
- 끝 상태를 셋으로 분류한다. (i) 공중 Hold: 10 s 동안 세 신호가 모두 거짓이고 z가 지면 위 0.05 m보다 높게 머문다. (ii) 신호가 섬: 10 s 안에 셋 중 하나가 참이 된다(처음 참이 된 시각을 적는다). (iii) 지면 위 armed: z가 지면에 닿았는데(지면 z의 0.05 m 안) 10 s 동안 세 신호가 모두 거짓이고 armed다.
- 회차 끝에 NAV_LAND를 보내 `landed`와 disarm까지의 시간을 적는다(11-4의 회복 경로 확인을 겸한다).
- 회차의 ULog를 남긴다. (iii)이나 "섰다가 풀림"이 나오면 추력 setpoint와 `vehicle_land_detected`의 세부 필드를 ULog에서 읽어 경로를 [소스]와 대조한다.
- 결과는 `opinion-px4.md` 끝에 "추가 실험 답" 절로 더하고 원자료 경로를 적는다. 표의 값에는 회차 수와 범위를 적는다.

문항

| 번호 | 시작 상태 | 하는 것 | 회차 | 답해야 하는 것 |
| --- | --- | --- | --- | --- |
| E1 | 5 m 호버에서 NAV_LAND로 하강 중(`nav_state` 18, `failsafe` 거짓, setpoint는 Land 확인 때 멈춤). 송신 시점에 세 신호가 모두 거짓인 것을 확인한다(아니면 그 회차는 따로 센다) | 지면 기준 높이 0.5, 0.3, 0.2, 0.1 m를 지날 때 DO_SET_MODE(Hold) 1회 | 높이마다 3회 이상(합 12회 이상) | 높이별 끝 상태의 분류(i, ii, iii)와 횟수. Hold 뒤 더 내려간 깊이. (ii)이면 신호가 처음 선 시각의 범위. 송신 시점에 신호가 이미 서 있던 회차의 높이 |
| E2 | E1과 같다 | E1의 (ii) 회차마다, 신호가 선 것을 본 직후 NAV_LAND를 다시 보낸다(관찰 창 규칙의 흉내). E1과 같은 회차에서 해도 된다 | E1의 (ii) 회차 전부 | Hold 확인부터 신호가 서기까지의 최대 시간(관찰 창 2 s 안인가). Land 재송신부터 `landed`, disarm까지의 시간 |
| E3 | 지상, Offboard, arm, TAKEOFF setpoint(기준점 위 5 m)를 20 Hz로 내는 중 | arm 확인 뒤 1.6, 1.8, 2.0, 2.5 s에 (가) Hold(setpoint를 유지하고 `nav_state` 4 확인 뒤 중단), (나) NAV_LAND(송신과 함께 setpoint 중단) | 시점과 변형마다 3회 이상(합 24회 이상) | 송신 시점의 세 신호와 높이. (가)의 끝 상태 분류와 신호가 선 시각. (나)에서 `landed`, disarm까지의 시간과 실패 여부. `landed`가 거짓이 된 뒤 `maybe_landed`, `ground_contact`가 거짓이 되는 순서와 시각 |
| E4 | E3과 같다 | arm 확인 뒤 1.7-1.9 s(`landed`가 거짓이 되는 부근)에 비강제 disarm 1회. 거부(TEMPORARILY_REJECTED)가 나온 회차를 모은다. 변형 (가) setpoint를 계속 낸다(새 규칙). 거부 뒤 그때의 세 신호로 Hold 또는 NAV_LAND를 보낸다. 변형 (나) disarm 송신과 함께 setpoint를 멈춘다(옛 규칙). 거부 뒤 명령 없이 10 s 본다 | 변형마다 거부 3회 이상이 모일 때까지 | disarm의 ack까지 걸린 시간(수락과 거부 각각). (가)에서 거부 뒤 `nav_state`와 `failsafe`(Offboard가 유지되는가), 이어 보낸 명령의 결과와 끝 상태. (나)에서 `offboard_control_signal_lost`와 `nav_state` 18까지의 시간, 끝 상태 |
| E5 | 지상, Offboard, arm 직후. setpoint 목표는 기준점(이륙 전. PREPARING과 TAKEOFF 사이의 상태) | setpoint를 계속 내는 채 비강제 disarm 1회 | 3회 이상 | ack, `arming_state` 1까지의 시간, disarm 뒤 `nav_state`. disarm 확인 뒤 setpoint를 멈추고 5 s 동안의 `failsafe`와 `nav_state` |

결과의 처리(미리 정한다)
- E1, E3 (가)의 모든 회차가 (i)이거나 "(ii)이고 신호가 Hold 확인 뒤 관찰 창 안에 섰다"이면: 취소 표를 그대로 확정한다. 관찰 창은 "관측한 최대 시간의 3배 이상"이 되게 다시 정한다(2 s보다 줄이지 않는다). K5에 "Hold 모드의 기체는 공중에 있다"를 더하고 2번의 [미측정]을 [실측]으로 바꾼다.
- (iii)이 한 번이라도 나오거나 신호가 관찰 창보다 늦게 서면: 관찰로는 가를 수 없다는 뜻이다. K5는 지금 문장("지상 disarm이거나 armed, Hold 모드")으로 확정한다. 분기는 px4, ops와 다시 정하고, 그때의 기본안은 "자기 Land 하강 중의 취소는 Hold를 보내지 않고 항상 착륙을 끝낸다"다(정책이 바뀌므로 사용자 5를 다시 올린다). 높이 임계는 쓰지 않는다.
- E4 (가)에서 Offboard가 유지되고 이어 보낸 명령이 표대로 끝나면 K3을 확정한다. 유지되지 않으면(거부 뒤 failsafe) 지상 armed 줄을 px4와 다시 정한다. E4 (나)는 옛 규칙을 버린 근거로 적는다.
- E5에서 disarm이 거부되면 PREPARING 실패 경로의 "비강제 disarm까지 하고 끝낸다"를 px4와 다시 정한다.
- 실험이 끝날 때까지 작업 단위 C-2는 취소 분기를 뺀 부분(PREPARING, TAKEOFF, LOITER, LAND, 실행 중 이상)부터 구현한다. 취소 분기의 구현과 작업 단위 H의 K3-K5 반영은 결과 뒤다.

결과와 처리(2026-11-11. 원문은 `opinion-px4.md`의 "추가 실험 답(E1-E5)")
- 조건: 스택 k=1 하나, load1 0.54-5.80(중앙값 3.73, 313표본). 본 측정 s1-s3과 보충 s4, s5. Hold와 disarm은 1회 송신.
- E1(12회): (i) 4, (iii) 8. 0.5 m는 (i) 3/3, 0.3 m는 (i) 1/3과 지면 접촉 2/3, 0.2 m와 0.1 m는 지면 접촉 6/6. Hold 뒤 0.26-0.29 m 더 내려간다. 세 신호는 12/12 서지 않았다. E2는 (ii)가 0회라 해당 회차가 없다.
- E3(24회 + 보충 12회): arm 뒤 1.6-2.5 s는 기체가 아직 지면 위다(실제 이륙은 3.10-3.40 s). (가) Hold는 지면 위 armed Hold 12/12. (나) NAV_LAND는 12/12 착지와 disarm. 보충: 3.6 s(0.25-0.30 m)와 4.0 s(0.9 m)의 Hold는 공중 Hold 6/6, NAV_LAND는 6/6 착지와 disarm.
- E4(18회): 1.75 s는 ACCEPTED 6/6, 1.85와 1.9 s는 TEMPORARILY_REJECTED 12/12(모두 세 신호 거짓). (가) 거부 뒤 Offboard 유지 6/6, 이어 보낸 Hold는 지면 위 armed Hold 6/6. (나) 거부 뒤 Offboard 손실 failsafe 6/6.
- E5(5회): 거부 0. disarm 뒤 setpoint를 멈춰도 failsafe 없음 5/5.
- 처리: 둘째 줄에 해당한다((iii)이 E1 8회, E3 (가) 9회(1.6 s의 3회도 같은 끝 상태), E4 (가) 6회). K5는 "지상 disarm이거나 armed, Hold 모드"로 확정했다. 분기는 px4의 의견(자기 Land 하강 중과 TAKEOFF 실행 중의 취소를 NAV_LAND로 끝낸다)을 받아 2번의 표로 다시 정했다. 관찰 창은 없앴다. K3은 확정했고 거부 뒤의 줄은 Hold가 아니라 Land로 바꿨다(거부 때는 항상 세 신호가 거짓이라 옛 표로는 지면 위 armed Hold가 된다). E5로 PREPARING 실패 경로는 그대로 둔다.
- 남은 것: ops-service-engineer의 검토(아래 "ops 검토" 절). 승인 전에는 작업 단위 C-2의 취소 분기를 2번의 표로 구현하되 계약 반영(H)은 하지 않는다. (2026-11-11 끝남: 조건부 승인. "ops의 답과 처리")

## ops 검토 (새 취소 분기. Phase 3 Fleet의 관점)

Fleet이 CANCELED를 받았을 때 알 수 있는 것(K4, K5의 풀이)
- CANCELED로 끝난 기체는 둘 중 하나다. (A) 지상 disarm. (B) armed, Hold 모드.
- (B)가 되는 것은 LOITER 실행 중에 취소했을 때와, `[LAND]` 미션이 Land 명령을 보내기 전에 취소했을 때뿐이다. TAKEOFF나 LAND 실행 중의 취소는 기체를 그 자리에 세우지 않고 착륙을 끝내므로 (A)다.
- (A)의 기체는 다음 `[TAKEOFF, ...]` 미션을 받을 수 있는 상태다(지상 취소 뒤의 다음 goal은 미해결 표의 [미측정] 항목). (B)의 기체는 Fleet이 `[LAND]` 미션으로 내려야 한다. 1a의 Executor는 (B)의 기체에 `[LAND]`만 받는다(`[TAKEOFF, ...]`는 PRECONDITION_FAILED).
- (ops 검토로 바뀜) result의 `end_state`가 (A)와 (B)를 가른다(K13). 검토 전의 문장은 "가르는 필드가 없고 Fleet이 feedback이나 텔레메트리로 가른다"였다.
- 취소 요청부터 CANCELED까지의 시간이 길어진다. LOITER 중이면 Hold 확인까지(수십 ms), TAKEOFF나 LAND 중이면 착륙과 disarm까지다(5 m에서 약 11 s. 높이에 비례). 그동안 `phase`는 CANCELING이고 둘째 goal은 BUSY다.
- 취소가 ABORTED로 끝날 수 있다: failsafe 진행 중(FAILSAFE), 상태 미수신(LINK_LOST), Hold 미확인(MODE_SWITCH_FAILED. Land 명령은 보냈다), 취소 착륙의 실패(ITEM_TIMEOUT 등). 이때 기체 상태는 계약이 약속하지 않는다.
- (B)의 기체가 공중에 있다는 것은 계약이 약속하지 않는다(실측 범위는 2번). Hold에서 벗어나는 경로는 C4다.

ops-service-engineer에게 묻는 것
1. TAKEOFF 실행 중의 취소가 "그 자리 Hold"가 아니라 "착륙한 뒤 CANCELED"가 되어도 Phase 3의 미션 재배분에 문제가 없는가. Fleet이 상승 중인 기체를 공중에 세워 둔 채 새 미션을 주어야 하는 경우가 있는가.
2. CANCELED가 (A)인지 (B)인지 result만으로 알아야 하는가. 필요하면 1a 고정 전에 result 끝에 필드를 더할 수 있다(직접 정의 golden이 바뀐다). feedback과 텔레메트리로 충분한가.
3. 취소 요청 뒤 result까지 수십 초가 걸릴 수 있다. Fleet의 취소 대기 시간과 그동안의 기체 상태 표시(CANCELING)에 필요한 것이 더 있는가.
4. (B)로 남은 기체를 `[LAND]` 미션으로만 내릴 수 있다(시작 조건: armed, 지상 아님, Hold). Fleet이 (B)의 기체에 곧바로 새 비행 미션(예: 1b의 GOTO)을 주어야 한다면 1b의 어떤 시작 조건이 필요한가.
5. 취소가 ABORTED로 끝난 기체(상태 미약속)를 Fleet이 어떻게 다룰 생각인가. 계약에 더 필요한 문장이 있는가.

ops의 답과 처리(2026-11-11. 원문은 `opinion-ops.md`)

결론은 조건부 승인이다. 항목으로 가르는 분기(사용자 5의 (5) (가))와 K5의 문장은 승인됐다. 조건 셋은 모두 받았고 받지 않은 것은 한 문장이다.

| ops의 요청 | 처리 | 반영한 곳 |
| --- | --- | --- |
| C1. result 끝에 끝 상태 필드 | 받는다. 이름과 값은 ops의 제안 그대로 `uint8 end_state`, `END_STATE_UNKNOWN` 0, `END_STATE_GROUND_DISARMED` 1, `END_STATE_ARMED_HOLD` 2. 2의 조건에 `failsafe` 거짓을 더했다(ABORTED의 관측값에서도 같은 뜻이 되게). golden이 바뀌므로 작업 단위 H-1로 먼저 한다 | 2번, K13, N5, "K13의 반영 절차" |
| C2. CANCELING 중의 이상 판정, 취소 요청부터 result까지의 상한 | 받는다 | 2번, K14, K15 |
| C3. 취소로 착륙을 끝낸 경우의 `last_item_index`, `items_completed` | 받는다. LAND 항목 실행 중의 취소도 그 항목을 세지 않는 것으로 넓혔다 | 2번, K16, N6 |
| CANCELING 중 feedback을 계속 낸다 | 받는다. `distance_valid`는 거짓으로 정했다 | 2번, K17, N3 |
| 활성 goal의 취소는 항상 ACCEPT, 거듭된 취소는 무시 | 앞은 받는다. 뒤는 "실행을 바꾸지 않는다"까지만 받는다. 거듭된 요청의 응답 코드는 action 계층이 정하고 ACCEPT가 아닐 것으로 본다([추정]. ros2 실측) | 2번, K17, 미해결 표 |
| ABORTED 뒤 그 goal로 /fmu/in에 아무것도 내지 않는다 | 받는다. 모든 종료로 넓혔다 | 2번, K18 |
| MODE_SWITCH_FAILED(Hold 미확인)는 "Land 명령을 보냈다"까지 | 받는다. 취소 요청 뒤의 MODE_SWITCH_FAILED 전부로 적었다(취소 착륙의 Land 미확인 포함) | 2번, K14 |
| `MissionEvent` 종료 사건의 끝 상태(비차단) | 6단계에서는 싣지 않는다. Phase 2 초반에 logging-engineer와 정한다 | 2번, 미해결 표 |
| 1b의 Hold 기체 GOTO 시작 조건 셋 | 1b 설계 토론으로 넘긴다 | 미해결 표 |
| Phase 2 `VehicleState` 필드(비차단) | Phase 2 스키마 검토로 넘긴다 | 미해결 표 |

- Fleet 쪽 설계로 적어 둘 것(계약 문장이 아니다. Phase 3): `AbortMission`은 취소 요청을 넘긴 즉시 돌려주고 미션을 "취소 중"으로 둔다. 취소 중과 ABORTED의 기체는 배분 대상이 아니다. ABORTED 기체는 격리하고, `END_STATE_GROUND_DISARMED`가 실려 왔거나 텔레메트리로 지상 disarm이 이어지면 되돌린다. (B)의 기체는 `[LAND]`로 내린 뒤 다시 배분한다. 상한을 넘기면 `END_STATE_UNKNOWN`의 ABORTED와 같게 다룬다.
- 재질문은 하지 않았다. 조건 셋이 px4의 취소 표와 부딪치는 곳이 없다(표의 줄과 동작은 그대로이고 result의 값과 문장만 는다). px4가 확인할 것은 2번의 단위 테스트 대상에 넣었다(ABORTED의 관측 규칙, 모든 취소 경로의 상한).

## 사용자 결정 항목 (최종 9개)

| 번호 | 항목(성격) | 선택지 | 권고와 이유 |
| --- | --- | --- | --- |
| 1 | `sitl` job의 시나리오 범위와 시간(범위, 대기 시간) | (가) PR마다 넷(정상 비행, BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION), 1회, 취소와 failsafe는 단위 테스트와 로컬. (나) 취소 둘을 PR에 더한다. (다) main 머지에서만 돌린다 | (가). 스택 부분은 이 호스트에서 약 1.5분이다(up 35 s + 비행 약 42 s + 즉시 끝나는 goal 셋 + down 1 s. [실측 혼자]의 합). 시간 한도는 테스트 단계 15분, job 전체 35분(ros-ws를 job 안에서 빌드하는 분기를 넣은 값. 초안의 25분에서 바뀜). `docs/architecture.md`의 "15분 이내"는 테스트 단계의 값으로 읽게 된다. 저장소가 공개라 표준 runner의 사용 시간은 과금되지 않는다([문서](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions). 저장소 PUBLIC은 devops [실측] `gh repo view`). runner의 값은 미측정이라 첫 실행 뒤 다시 알린다 |
| 2 | ROS 비의존 상태기를 6단계로 당긴다(범위. roadmap 1b 1번의 일부) | (가) 구조와 TAKEOFF, LOITER, LAND, 취소만 당긴다. (나) roadmap대로 1b에 둔다 | (가). 노드는 어차피 tick 기반 상태기여야 하고 코드 양이 거의 같다. 재질문으로 근거가 늘었다: 하강 중 취소의 분기와 `[LAND]` 미션의 PREPARING은 20-30 ms의 경합 구간이 있어 SITL로 시점을 맞추기 어렵고 단위 테스트로만 결정적으로 덮인다. (나)는 이 분기들을 검증 없이 1a 계약으로 고정하게 된다 |
| 3 | `sitl` 실패 artifact의 MCAP을 Phase 2로 미룬다(범위) | (가) 미룬다. (나) 6단계에 진단 전용으로 넣는다 | (가). 6단계에 넣으면 기록물 이름, 대상 목록, 기록기와 Executor의 순서가 Phase 2 설계 전에 굳는다. PX4 쪽 상태는 ULog에 있고 ULog는 비정상 종료 4/4에서도 온전했다(근거 보강). 크기는 실패 1회에 압축 뒤 10-16 MB다(18 MB/분, 압축 약 0.3으로 정정) |
| 4 | ros-ws 이미지에 foxglove_bridge(비용: 이미지 크기) | (가) 넣는다(49.6 MB 증가, 1.99 GB -> 2.05 GB, 실측). (나) `viz` 전용 이미지를 따로 만든다 | (가). 이미 `docs/architecture.md`의 이미지 표에 있는 구성이고 증가가 2.5%다. 이미지를 하나 더 두면 key와 build job이 는다. 재질문으로 바뀐 것 없음 |
| 5 | 취소 정책의 변경(5단계에서 "뒤집을 수 있음"으로 알린 것. 추가 실험 뒤 2026-11-11에 다시 씀. ops 조건부 승인, result에 `end_state` 필드 추가(golden 변경)) | 바뀌는 것 여섯. (1) Hold가 확인되면 setpoint를 즉시 멈춘다(기술적으로 필수). (2) failsafe 진행 중의 취소는 모드 명령 없이 ABORTED, FAILSAFE. (3) 지상 armed 취소는 setpoint를 유지한 채 비강제 disarm을 보내고, 거부되면 다시 보내지 않고 착륙 명령으로 끝낸다. (4) LAND 항목에서 지상 판정 뒤 정해진 시간 안에 자동 disarm이 없으면 비강제 disarm을 보낸다. (5) 새로: 취소의 처리를 실행 중인 항목으로 가른다. (가) TAKEOFF(목표 고도 도달 전)와 LAND 실행 중의 취소는 Hold로 세우지 않고 착륙을 끝낸 뒤 CANCELED, LOITER 실행 중의 취소만 Hold로 세우고 CANCELED. (나) LAND 실행 중만 착륙을 끝내고 TAKEOFF는 앞의 안(착지 판정 신호로 가름)대로 둔다. (다) 높이 임계로 가른다(예: 기준점 위 일정 높이 이상이면 Hold). (6) 새로: Hold로 남은 기체는 `[LAND]` 하나짜리 미션으로 내리고, 그 미션은 "armed, 지상 아님, Hold"에서만 시작한다. 5단계와 앞의 안에서 달라지는 것: "공중이면 Hold로 남김"이 "LOITER 중이면 Hold로 남김"으로 좁아지고, 신호를 2 s 지켜보는 절차가 없어진다 | 여섯 다 채택, (5)는 (가). 이유: 추가 실험에서 PX4의 착지 판정 신호는 지면 위와 공중을 가르지 못했다. 신호가 모두 꺼진 상태의 Hold 33회 가운데 뒤에 신호가 선 것은 0회였고, 그중 23회가 "지면 위에 armed, Hold 모드"로 남았다(착륙 하강 0.3 m 이하 9회 중 8회, arm 뒤 이륙 전 구간 15회 전부). arm 뒤 약 1.6 s부터 실제로 뜨는 3.1-3.4 s까지는 기체가 지면 위인데 신호가 모두 꺼져 있다. 착륙 명령은 어느 시점에서든 착지와 disarm으로 끝났다(54/54). (가)의 위험: 상승 중이나 하강 중의 기체를 취소로 그 자리에 세울 수 없다(세우려면 LOITER에 들어간 뒤 취소한다). 이 경우 CANCELED는 착륙이 끝난 뒤에 온다(5 m에서 약 11 s). 0.9 m보다 높은 상승 중의 착륙 명령은 재지 않았다(5 m 호버에서는 쟀다). (나)의 위험: 이륙 전 구간의 취소가 지면 위 armed Hold로 끝난다(실측 15/15). (다)의 위험: Executor의 높이 기준이 실제 지면과 최대 0.4 m 어긋나는데(실측) Hold가 공중에 선 가장 낮은 높이가 0.25-0.30 m라 여유를 크게 잡아야 하고, 그 값은 재지 않았다. 약속하는 것은 "CANCELED면 지상 disarm 아니면 armed Hold 모드"까지다. armed Hold로 남은 기체가 공중에 있다는 것은 5 m 호버에서만 쟀고 계약에는 적지 않는다. 어느 쪽이든 `[LAND]` 미션으로 내려진다(Hold 뒤의 착륙 명령 36/36). (6)의 이유: 실측으로 확인된 유일한 경로이고, 더 넓은 조건은 소비자(Fleet)가 생길 때 실측 뒤 넓힌다. 그때까지 Hold가 아닌 모드로 공중에 남은 기체(외부 모드 변경 뒤)를 내리는 방법은 계약에 없다. (2)는 원하면 "failsafe 중에도 Hold로 멈춘다"로 할 수 있다(PX4는 받아 준다, 5/5). ops-service-engineer(취소 계약의 소비자. Phase 3 Fleet의 관점)는 (5)의 (가)를 조건부로 승인했고 조건은 모두 받았다. 그 결과로 달라지는 것: 취소나 성공으로 끝난 뒤 기체가 지상 disarm인지 armed Hold 모드인지를 Fleet이 결과만으로 알 수 있게 `ExecuteMission`의 result 끝에 `end_state` 필드를 더한다(값: 모름 0, 지상 disarm 1, armed Hold 2). 이 추가로 5단계에서 만든 `ExecuteMission`의 golden(type hash, 펼친 정의, 직접 정의)이 바뀐다. 아직 고정 전(1a 완료에 고정)이고 끝에 더하는 변경이라 5단계의 변경 절차 안이다. (5)를 (나)나 (다)로 정해도 끝 상태가 둘인 것은 같아 이 필드는 넣는다. 함께 받은 조건: 취소 처리 중에도 연결 끊김, failsafe, 외부 모드 변경을 판정해 ABORTED로 끝내고, 취소 요청부터 결과까지의 시간에 상한을 둔다(기본값의 합 약 49 s) |
| 6 | 육안 확인의 장소(이 호스트는 SSH뿐이고 화면 세션이 없다) | (가) 호스트의 화면 세션에 직접 로그인해 gz-gui와 QGC를 보고, Lichtblick은 같은 화면이나 `ssh -L` tunnel로 본다. (나) 화면이 있는 다른 기계에서 스택을 통째로 돌린다. (다) 나눠서 한다: Lichtblick만 tunnel로 지금, gz-gui와 QGC는 화면이 준비될 때 | (가), 안 되면 (다). 호스트에 display manager는 떠 있다(sim [실측]: greeter만 있음). 메모리는 gz-gui, foxglove, lichtblick을 함께 올려도 스택 합 약 1 GB였다([실측], QGC는 미측정). Lichtblick의 browser 화면은 아무도 보지 못했으므로 Plot 확인은 사용자가 한다. 3단계의 육안 확인 2건도 같은 자리에서 한다. 재질문으로 바뀐 것 없음 |
| 7 | `sitl`을 필수 검사(required check)로 둔다(정책. 새 항목) | (가) 6단계에서는 필수로 두지 않는다(지금 main에는 branch protection이 없고 필수 검사가 하나도 없다). (나) `sitl`을 필수로 두고 px4, sim-base 이미지를 바꾸는 PR은 관리자가 우회한다. (다) lint와 unit만 필수로 둔다 | (가). runner에서의 시간과 flake율이 미측정이고(px4 기동 중 139가 21회 중 1회 관측됨), px4와 sim-base 이미지를 바꾸는 PR은 설계상 `sitl`이 실패한다(11-3). 필수로 두면 그 PR마다 우회 규칙이 필요하다. 1a 완료 때 `sitl` 실행 기록을 놓고 다시 올린다. (다)는 `sitl`과 무관하게 정할 수 있다 |
| 8 | `tests/px4_facts/`를 CI nightly로 돌린다(비용, 범위. 새 항목) | (가) 로컬 전용. `PX4_TAG`, px4 파라미터, timestamp helper를 바꾸는 PR에서 돌리고 결과를 PR 본문에 붙인다. (나) nightly job으로도 돌린다 | (가). 이 시나리오가 확인하는 것은 `PX4_TAG`에 묶인 사실이고 그 입력은 PR로만 바뀐다. nightly는 같은 입력을 되풀이한다. 비용은 1회 벽시계 약 100 s와 이미지 받기다(과금은 없지만 workflow 하나와 실패 알림이 는다). Phase 3에서 nightly(3대)를 만들 때 함께 넣을지 다시 본다 |
| 9 | CLAUDE.md 담당자 표에 `idsim_mission`의 소유를 적는다(에이전트 운영 규칙. CLAUDE.md는 사용자만 고친다. 새 항목) | (가) 표를 고친다. 문안: ros2-engineer 행의 소유 영역을 "`idsim_common`, `config/cyclonedds.xml`, `idsim_mission`(PX4 절차 상태기 제외)"로, px4-engineer 행의 소유 영역을 "`Dockerfile.px4`, SITL 파라미터, `idsim_mission`의 PX4 절차 상태기"로. 역할 칸은 그대로 둔다. (나) 표는 그대로 두고 `docs-for-agent/file-ownership.md`에만 적는다 | (가). 지금 표는 px4에게 "`idsim_mission`의 PX4 접점"만 주고 나머지(패키지 골격, 검증, 분류, 노드)의 소유자가 없다. CLAUDE.md는 모든 담당자가 세션마다 읽는 파일이라 두 파일이 다르면 CLAUDE.md 쪽으로 읽힌다. `file-ownership.md`의 반영(작업 단위 O)은 이 결정과 무관하게 PR 4 전에 한다. `tests/sitl/`과 `tests/px4_facts/`는 test-engineer 행의 `tests/`에 이미 들어 있어 표를 고칠 필요가 없다(`run_sitl.sh`만 devops이고 `file-ownership.md`에 적는다) |

결정 결과(2026-11-11, 사용자): 1-9 모두 권고안 (가)로 확정한다. 5는 여섯 다 채택하고 (5)는 (가) 실행 중인 항목으로 가르며, result에 `end_state`를 더한다. 6은 (가), 안 되면 (다). 9에 따라 CLAUDE.md 담당자 표의 ros2-engineer와 px4-engineer 행을 같은 날 고쳤다. 구현은 아직 시작하지 않았고, 다음 세션에서 `README.md`의 PR 순서대로 시작한다.

## 사용자에게 알릴 것 (결정은 했으나 뒤집을 수 있음)

- `docs/architecture.md`의 문장 넷을 고친다. (1) 281행 "pytest fixture가 `docker compose up --wait`로 스택을 올린다" -> 호스트 진입 스크립트가 올리고 `runner` 안의 pytest가 판정한다. (2) 106행 "Lichtblick 2.5" -> 1.30.0. (3) `sitl` job 설명의 MCAP(사용자 3). (4) 165행 취소 문장(사용자 5).
- GHCR 이미지는 이미 익명으로 받을 수 있다. "다음 작업 1"은 끝난 것으로 본다.
- 스모크 S2-S5가 운용 노드 서비스까지 올리게 되어 스모크 전에 `tools/ros_ws.sh build`가 필요해진다.
- 6단계에는 Lichtblick layout 파일을 저장소에 두지 않는다. bridge 설정 파일은 1b로 넘긴다.
- failsafe 회귀 판정은 "Executor의 timestamp가 `/clock`과 같은 축인지"를 PR마다 읽기 전용으로 본다. 묵은 timestamp의 주입은 로컬 전용 `tests/px4_facts/`가 한다. 이 디렉터리만 테스트에서 /fmu/in에 발행한다.
- healthcheck는 노드가 쓰는 표식 파일이다(확정). 운용 노드 서비스는 `ros2 run`이 아니라 실행 파일을 직접 실행한다.
- bridge와 xrce-agent의 종료 방식을 고쳐 `stack.sh down`이 약 21 s에서 약 1 s가 된다.
- 노드가 SIGTERM으로 끝날 때 실행 중 goal의 종료 사건과 result는 최선 노력이다(5단계 계약의 "결과 미상"으로 이미 덮인다).
- main의 `sitl`은 build workflow가 성공한 뒤에 돈다(`workflow_run`). px4나 sim-base 이미지를 바꾸는 PR의 `sitl`은 실패로 남고 로컬 결과를 PR 본문에 붙인다.
- `idsim_mission`의 소유를 ros2(패키지, 검증, 분류, 노드)와 px4(PX4 절차 상태기)로 나눈다. `file-ownership.md`에는 PR 4 전에 적는다(작업 단위 O). CLAUDE.md 표의 변경은 사용자 9다.
- 추가 실험 E1-E5가 끝났고 취소 분기를 다시 정했다(2번, 사용자 5). 계약 문장은 "CANCELED로 끝난 기체는 지상 disarm이거나 armed Hold 모드"로 확정이다. 관찰 창 2 s는 없앴다. ops-service-engineer의 검토는 조건부 승인으로 끝났고, 조건으로 `ExecuteMission`의 result 끝에 `end_state` 필드를 더한다(K13. `ExecuteMission`의 golden이 바뀐다. 사용자 5에 함께 적었다). `MissionEvent`에는 싣지 않고 Phase 2 초반에 다시 본다.
- SITL에서 PX4의 battery_simulator가 주기 실행을 멈추는 일이 추가 실험 중 7회 관측됐다(원인 미확인). arm 거부나 arm 직후 disarm으로 나타나 `sitl`의 플래키 원인이 될 수 있다. px4가 원인을 찾고 test와 devops가 판정과 artifact에서 구분되게 한다. 지금 사용자가 정할 것은 없다. 다만 사용자 7(`sitl`을 필수 검사로 두지 않는다)의 권고 근거가 하나 늘었고, 원인이 PX4 소스 수정이나 `PX4_TAG` 변경, 시나리오마다 스택 재기동(사용자 1의 시간)으로 이어지면 그때 올린다.
- 1a 노드는 `[TAKEOFF, LOITER 0개 이상, LAND]`와 `[LAND]`만 실행하고 그 밖의 순서는 INVALID_MISSION으로 끝낸다. GOTO 등과 같은 임시 동작이고 계약 문장이 아니다. 1b에서 푼다.
- PX4만 재기동한 것을 Executor가 따로 감지하지 않는다. 상태 미수신(LINK_LOST)으로 드러난다. Gazebo가 재기동해 `/clock`이 뒤로 가면 실행 중 goal은 LINK_LOST로 끝나고 노드는 activate를 다시 시도한다.
- 원칙의 예외 둘을 `docs/architecture.md`에 적는다. (1) 생성기의 foxglove 허용 목록에 `fmu/(in|out)/` 접두사 리터럴 하나(읽기 전용 표시 필터). (2) 운용 노드의 1 Hz wall timer(activate 재시도, 표식 갱신, `/clock` 정지 경고. 판정에 쓰지 않는다).
- 작업 단위 H를 둘로 나눴다. H-1(result의 `end_state` 정의와 golden)은 노드 구현(D) 전에, H-2(의미 문장과 주석, 문서)는 통합 테스트 뒤에 한다. 둘 다 ops-service-engineer의 승인이 조건이다. 취소 분기에 대한 ops의 조건부 승인은 받았다.

## 문서 반영 목록 (작업 단위 H-1, H-2. `file-ownership.md`만 O)

- 5단계 `decisions.md` 쟁점 9와 `ExecuteMission.action` 주석: 위 "5단계 계약에 반영할 변경"의 K1-K18, N1-N6. K13과 N5(필드, 상수, golden, 상수 검사)는 H-1, 나머지는 H-2. 7단계 `docs/interface.md`의 대상 목록에 K13-K18을 올린다.
- `docs/architecture.md`: 위 "알릴 것"의 문장 넷, 식별 절의 params 문장(네임스페이스는 `__ns`, `vehicle_id`와 sysid는 params), healthcheck(표식 파일)와 자기 전이, 운용 노드의 직접 실행, `sitl` job의 trigger와 이미지 정책, `tests/px4_facts/`, 원칙의 예외 둘(foxglove 허용 목록의 `fmu/(in|out)/` 접두사, 판정에 쓰지 않는 1 Hz wall timer), ROS 시각 역행의 처리.
- `docs/roadmap.md`: 1a 6번의 "모드 전환 전 최소 10회", 1b 1번의 범위(사용자 2가 채택되면), 리스크 표(컨테이너 사이 action 행 닫기).
- progress.md 결정 기록의 Lichtblick 버전, 결정 (u)의 읽는 법. 호출한 쪽이 갱신한다.
- `docs-for-agent/file-ownership.md`(작업 단위 H가 아니라 O. PR 4 전): `idsim_mission`의 분할(4번의 표), `tests/sitl/`(`run_sitl.sh`는 devops, 나머지는 test), `tests/px4_facts/`(test).
- 작업 단위 H의 승인: px4와 ops-service-engineer의 승인이 조건이다(검토만이 아니다). ops는 K1-K7(취소 계약과 `[LAND]` 미션)의 소비자다. ops는 K13-K18의 요청자이기도 하다. K3-K5에 대한 ops의 검토는 조건부 승인으로 끝났다("ops의 답과 처리"). 남은 승인은 H-1과 H-2의 PR에서 받는다.
- Executor 설계 노트(`idsim_mission` 안): setpoint 발행 규칙, PREPARING 순서, 취소 표, 자기 전이, deactivate 거부, 종료 처리, 표식 규칙, 구현 규칙(C9, C31), 이름 상수 규칙.

## 값의 갱신 (초안의 재측정 목록을 닫는다)

| 값 | 초안[실측 경합] | 확정[실측 혼자] | 쓰인 곳 |
| --- | --- | --- | --- |
| `/clock` 벽시계 도착 끊김 최대 | 106 ms | 25.9 ms(단독), 21.1 ms(부하) | 1번 |
| `vehicle_status.timestamp`와 수신 시 ROS 시각의 차 | 최소 -176 ms(경합 지연으로 봄) | arm 없는 구간 -8 - 8 ms. 전이 메시지 한 건씩 152-196 ms(test 5회는 176-180 ms. 경합과 무관) | 9번 (A'), 10번 |
| `offboard_control_mode.timestamp`와 수신 시 `SimClock`의 차 | 없음 | 중앙값 0, 최대 12 ms | 9번 (A) |
| ROS 시각 timer의 벽시계 간격 최대 | 69 ms, 157.6 ms | 67.7 ms(단독), 70.3 ms(부하) | 1번, 5번 |
| RTF | 0.988-0.998 | 0.998-0.999 | S1 |
| `stack.sh up` | 41-44 s | 35.1-35.9 s. 부하 42.3 s | 3번, 사용자 1 |
| `stack.sh down` | 20.7 s | 20.8-21.1 s. 종료 신호 변경 뒤 0.78-0.85 s | 3번, 10번 |
| 콜드 빌드 | 94 s, 871 MiB | 42.0 s, cgroup 최대 1851 MiB(cache 포함) | D4 |
| 표식 healthcheck | 미측정 | 32-45 ms(find 형태, docker exec 포함) | 5번 |
| ULog | 17.2-17.5 MB/분(지상), 압축 약 1/4 | 비행 1회 12.9-13.5 MB, 17.8-18.0 MB/분, 압축 약 0.3 | 8번, 사용자 3 |
| CLI healthcheck | 1.3-2.1 s | 다시 재지 않음(쓰지 않는다) | 5번 |

## reviewer 검증 반영 (2026-11-11)

결론은 조건부였다(필수 6, 권고 7). 모두 반영했고 받지 않은 것은 없다.

| 번호 | 지적 | 처리 | 고친 곳 |
| --- | --- | --- | --- |
| M1 | PX4 재기동을 `timestamp` 역행으로 감지한다는 전제가 틀렸다 | 감지를 버린다. PX4 재기동은 미수신(LINK_LOST)으로 드러난다. 역행이 실제로 생기는 Gazebo 재기동은 ROS 시각 역행 규칙이 받는다 | 1번, 5번, K11, 미해결 표 |
| M2 | "CANCELED면 공중 Hold이거나 지상 disarm"과 어긋나는 경로 셋 | 구조로 닫을 수 있는 둘은 규칙을 고쳤다((b) setpoint를 disarm 확인까지 유지, (c) 세 신호 검사와 관찰 창을 Offboard의 Hold에도 건다). 측정이 필요한 것은 실험(E1-E5)으로 보내고, 그때까지 K5를 측정이 받치는 문장으로 낮췄다 | 2번의 취소 표, K3-K5, 추가 실험, 사용자 5 |
| M3 | 1a 노드가 받는 항목 순서 | 임시 INVALID_MISSION 규칙과 단위 테스트 | 2번 |
| M4 | 표식을 지우는 시점의 모순 | on_configure 첫머리 | 5번 |
| M5 | 소유 반영 시점, CLAUDE.md, ops | `file-ownership.md`는 작업 단위 O(PR 4 전). CLAUDE.md 표는 사용자 9. H는 ops의 승인이 조건 | 4번, 사용자 9, 문서 반영 목록, `README.md` |
| M6 | 생성기의 `/fmu` 토픽 이름 리터럴 | 개별 이름을 버리고 접두사 한 줄. 남는 접두사 리터럴은 조건을 붙여 예외로 기록 | 11-1 |
| R1 | 종료 처리 채택안은 실측이 없다 | [추정]으로 적고 작업 단위 D에서 원형 확인. 안 되면 줄이는 안을 적었다 | 5번 |
| R2 | 1 Hz wall timer는 원칙의 예외 | 문서 반영 목록에 넣었다 | 1번, 5번 |
| R3 | 사전 조건 fixture와 지상 취소의 끝 상태 | `nav_state` 조건을 뺐다 | 3번 |
| R4 | `/clock` 역행의 처리 | 규칙 한 줄 | 1번 |
| R5 | 사용자 1의 링크, 사용자 5의 미측정 구간 | 둘 다 고쳤다 | 사용자 결정 항목 |
| R6 | 음차 | `decisions.md`, `README.md`, 의견서 여섯의 표기만 고쳤다(내용은 그대로) | 여덟 파일 |
| R7 | Collector 합류 때의 구조 | ops 검토 항목 | 미해결 표 |
| 표 (1) | 전이 메시지의 차 152-196 ms | 값과 (A')의 여유(약 2.5배)를 고쳤다 | 1번, 9번, 10번 |
| 표 (3) | ABORTED, EXTERNAL_MODE_CHANGE로 공중에 남은 기체 | K7에 "넓힐 수 있다"와 ops 검토 | 2번, K7 |
| 표 (4) | 발행 이름 함수 lint의 출처 | "제안"으로 낮췄다 | 9번 |
| 표기 | 0.032 s + 0.516 s의 출처, RTF 0.25 | 표시를 달았다 | 2번, T2 |

## 다음 절차

1. 추가 실험 E1-E5는 끝났고 architect가 2번, K3-K5, 사용자 5를 다시 정했다. ops-service-engineer의 검토도 끝났다(조건부 승인. 조건 C1-C3을 K13-K18로 받았다). K4, K5는 닫혔고 사용자 5는 문안을 고쳐 올린다.
2. (완료 2026-11-11) 사용자 결정 9항목 모두 권고안으로 확정.
3. 구현은 `README.md`의 작업 단위와 PR 순서를 따른다. H-1(`end_state` 정의와 golden)은 PR 5(노드) 전에 합친다.
4. 호출한 쪽이 px4-engineer에게 미해결 표의 셋(battery_simulator의 원인 규명, 낮은 `height_m`의 하한, 취소 착륙의 제한 시간)을, test와 devops에게 battery_simulator 항목의 대응을 보낸다.
