# 1a 6단계 이륙-호버-착륙 설계 토론: px4-engineer 의견

작성 2026-11-10, px4-engineer. 대상: `questions.md`의 공통 규칙과 px4-engineer 절(P1-P13). 저장소의 다른 파일은 고치지 않았다.

## 0. 근거와 실험 조건

근거 표기
- [실측]: 이 호스트(4 vCPU, 7GB)에서 스택 k=1(compose 프로젝트 `idsim-1`, 도메인 21, 기체 `px4_1`, MAV_SYS_ID 2)을 main 88afeda 저장소 그대로 올려 돌린 것. 같은 시각에 다른 담당자의 스택 k=5가 함께 떠 있었다(빌드와 GUI는 없음). RTF는 회차마다 0.989-1.000였다.
- [소스]: PX4 v1.17.0 원문. 사본은 GitHub raw(`raw.githubusercontent.com/PX4/PX4-Autopilot/v1.17.0/<경로>`)에서 받았고, 파일마다 git blob sha1(`sha1("blob <크기>\0" + 내용)`)을 v1.17.0 commit d6f12ad1의 tree 목록(`tree.json`, GitHub API `git/trees/d6f12ad1...?recursive=1`, truncated false)과 대조해 31개 파일 전부 일치했다. 행 번호는 그 사본 기준이다.
- [문서]: 링크를 적었다(2026-11-10 조회).
- [추정]: 실측이나 원문 확인이 없는 것.

실험 방법
- 탐침: scratchpad의 rclpy 노드 하나(`use_sim_time` 참, 저장소 밖). ros-ws 이미지의 `runner` 서비스를 `compose run --no-deps`로 띄우고 scratchpad를 마운트했다. 저장소 ros_ws는 빌드하지 않았다.
- 탐침은 `/px4_1/fmu/out/{vehicle_status_v1, vehicle_land_detected, vehicle_local_position_v1, vehicle_command_ack, failsafe_flags, battery_status_v1}`를 sensor_data QoS로 구독해 모두 JSONL로 남기고, `/px4_1/fmu/in/{offboard_control_mode, trajectory_setpoint, vehicle_command}`에 쓴다. setpoint는 벽시계 50 ms 주기(20 Hz) thread가 `OffboardControlMode(position=true)`와 `TrajectorySetpoint(position만, 나머지 NaN)`를 내고 timestamp는 ROS 시각(`/clock`) us에서 지정한 묵음만큼 뺀다. 명령은 source (254, 1), target (2, 1), `from_external` 참, ack가 올 때까지 0.5 s(벽시계)마다 재송신.
- 반복: 스택을 내리고 올리기를 5회(회차 r1-r5). 회차마다 boot 기록 -> m(OCM 1개 실험) -> a -> b -> c -> s1(묵음 0.5, 0.9, 1.1 s) -> s2(묵음 2.0 s)를 같은 스택에서 차례로 돌렸다. 회차 사이에는 `tools/stack.sh down/up --stack 1`. 이것과 별도로 r1 전에 같은 시나리오를 1회씩 시험 실행했다(값은 5회 분포에 넣지 않았고 정성 결과만 인용한다). 위치 무효 실험(P4 마)은 마지막에 따로 1회.
- 아래 시간 값은 따로 적지 않으면 PX4 timestamp(sim 시간 us, SYNCT=0이라 ROS 시각과 같은 축) 차이이고 "중앙값(범위 최소 ~ 최대, n=회수)"로 적는다. ROS 시각과 PX4 timestamp의 차는 수신 시점 기준 최소 -176, 중앙값 0, 최대 +4(회차별 값을 모음, n=5) ms였다(아래 P9).

## 1. 먼저 알릴 것: Offboard 밖에서 `TrajectorySetpoint`를 계속 내면 PX4 자체의 setpoint와 섞인다

계약과 구현 양쪽에 영향이 커서 앞에 적는다.

- [소스] uXRCE-DDS 클라이언트는 `/fmu/in/trajectory_setpoint`를 uORB `trajectory_setpoint`로 그대로 낸다(`src/modules/uxrce_dds_client/dds_topics.yaml` 158행). 같은 uORB 토픽을 Hold, Land 같은 내부 모드에서 FlightModeManager가 낸다(`src/modules/flight_mode_manager/FlightModeManager.cpp` 361행). mc_pos_control은 모드와 상관없이 그 토픽의 마지막 값을 쓰고(`MulticopterPositionControl.cpp` 438행), land detector도 그 토픽의 `velocity[2]`로 하강 중인지 본다(`MulticopterLandDetector.cpp` 225-230행). PX4는 발행자를 가리지 않는다.
- [실측] LAND 명령 뒤에도 setpoint(목표 고도 5 m)를 계속 내면 기체는 땅까지 내려오지만(명령부터 접지까지 7.428(범위 7.356 ~ 7.488, n=5) s) `landed`가 끝내 참이 되지 않고 armed로 땅에 머문다. 5회 모두 30 s(ROS 시각) 동안 착지 판정이 없었고, setpoint를 끊은 뒤 2.984(범위 2.964 ~ 3.040, n=5) s 만에 자동 disarm되었다. 같은 동안 `vehicle_land_detected.in_descend`와 `has_low_throttle`이 수십 ms 간격으로 참과 거짓을 오갔다(두 발행자가 번갈아 보이는 모습). 하강 속도 최대도 0.863(범위 0.806 ~ 0.972, n=5) m/s로 setpoint를 끊은 경우(0.740(범위 0.732 ~ 0.744, n=5) m/s)보다 컸다.
- [실측] Offboard 손실 failsafe(Land) 뒤에도 묵은 setpoint를 계속 내면 같은 일이 생겼다(시험 실행 1회: 접지 후 60 s 동안 armed, setpoint를 끊고 3 s 뒤 disarm). 위치 무효로 들어간 Descend에서도 같았다(P4 마: 접지 후 43 s 동안 armed, 끊고 3.0 s 뒤 disarm).
- [실측] Hold 중에 내는 setpoint가 Hold 위치와 같으면 겉으로 드러나지 않는다(P4 가: 3 s 동안 위치 변화 0.040(범위 0.030 ~ 0.052, n=5) m). 목표가 다르면 같은 섞임이 생긴다고 본다[추정].
- 결론: Executor는 `nav_state`가 OFFBOARD(14)가 아닌 것을 확인한 즉시 `TrajectorySetpoint`와 `OffboardControlMode` 발행을 멈춘다. 자기가 보낸 Hold, Land뿐 아니라 failsafe와 외부 모드 변경에서도 같다. 지금 쟁점 9의 "공중이면 setpoint 유지한 채 Hold 명령"은 "Hold가 확인될 때까지만 유지"로 좁혀야 한다. 이것은 setpoint helper(R6)와 노드 구조(R2)에 걸리는 규칙이다.
- 다른 결과(P4 라): 사용자 의도가 OFFBOARD로 남아 있는 failsafe 중에 setpoint가 다시 신선해지면 PX4가 명령 없이 Offboard로 돌아간다(0.052(범위 0.036 ~ 0.064, n=5) s). 멈추지 않고 다시 내기 시작하면 failsafe가 스스로 풀린다는 뜻이고, 이것도 "이탈 확인 즉시 멈춤"의 이유다.

---

## P1. Offboard 진입과 PREPARING 순서

[소스] 신호 유효 판정. `src/modules/commander/HealthAndArmingChecks/checks/offboardCheck.cpp` 40-65행: `offboard_control_signal_lost`는 기본 참이고, 마지막 `offboard_control_mode` 하나가 (가) 제어 flag 중 하나 이상이 참이고 (나) `hrt_absolute_time() < timestamp + COM_OF_LOSS_T`이면 거짓이 된다. position flag면 local position이 유효해야 한다. 개수나 주기 조건은 없다. `trajectory_setpoint`는 이 판정에 쓰이지 않는다.
[소스] 모드 전환 가능 조건. `UserModeIntention.cpp` 54-59행: disarm 상태에서는 모든 모드 전환을 허용하고(force 없이도), armed이면 `canRun(모드)`(모드 요구 조건. Offboard는 `mode_req_offboard_signal`, `ModeUtil/mode_requirements.cpp` 155-158행)를 본다. 시동은 `Commander.cpp` 549-620행에서 외부 명령이면 항상 사전 점검(`canArm(nav_state)`)을 돈다(`cmd.from_external || !forced`, 969행). 그래서 Offboard 상태의 시동은 신호가 유효해야 된다.
[문서] "최소 10회"의 출처는 PX4 ROS 2 예제 코드(https://docs.px4.io/main/en/ros2/offboard_control.html, `offboard_setpoint_counter_ == 10`, 100 ms timer)다. Offboard 모드 문서(https://docs.px4.io/main/en/flight_modes/offboard.html)는 "2Hz proof of life", "stream should be active before switching"만 적는다. v1.17.0에서 횟수 조건이 아니라 시간 조건이다.
[실측] m 시나리오(5회): armed(Hold) 상태에서 `OffboardControlMode` 1개만 보낸 뒤 0.1 s 뒤 DO_SET_MODE(Offboard). 5회 모두 ack ACCEPTED, `nav_state` 14(사용자 의도 14)로 바뀌었다가 약 1 s 뒤 18(사용자 의도 14, failsafe 참)로 떨어졌다. 횟수가 아니라 마지막 timestamp의 나이가 조건이라는 원문과 맞다.

[실측] 두 순서(각 5회, setpoint 발행 시작 1 s 뒤 첫 명령. 아래 "발행 시작부터"에는 이 1 s가 들어 있다)

| 항목 | (가) setpoint -> arm -> DO_SET_MODE | (나) setpoint -> DO_SET_MODE -> arm |
| --- | --- | --- |
| setpoint 시작부터 `nav_state` 14 | 1.052(범위 1.036 ~ 1.068, n=5) s | 1.036(범위 1.028 ~ 1.040, n=5) s |
| DO_SET_MODE 첫 송신부터 `nav_state` 14 | 0.028(범위 0.020 ~ 0.032, n=5) s | 0.028(범위 0.024 ~ 0.036, n=5) s |
| arm 첫 송신부터 `armed_time` | 0.016(범위 0.004 ~ 0.024, n=5) s | 0.012(범위 0.008 ~ 0.024, n=5) s |
| ack | 모두 첫 송신에 ACCEPTED, 재송신 없음 | 모두 첫 송신에 ACCEPTED, 재송신 없음 |

[실측] setpoint 시작부터 `failsafe_flags.offboard_control_signal_lost`가 거짓이 되기까지 수십 ms(시험 실행 16-64 ms)였다. setpoint를 끊은 뒤 참이 되기까지는 1.076(범위 0.976 ~ 1.084, n=5) s(COM_OF_LOSS_T 1.0 + Commander 점검 주기).

[실측] 부팅 뒤 준비 시각(스택 재기동 5회. ULog(SDLOG_MODE 2, 부팅부터 기록)의 `vehicle_status`, `vehicle_local_position`에서 읽었다. ULog 시작 시각 기준)

| 항목 | 값 |
| --- | --- |
| `z_valid` 참 | 0.076(범위 -0.004 ~ 0.108, n=5) s |
| `xy_valid` 참 | 1.188(범위 1.028 ~ 1.508, n=5) s |
| `pre_flight_checks_pass` 참 | 2.212(범위 2.056 ~ 2.564, n=5) s |
| px4 컨테이너 start부터 `pre_flight_checks_pass` 참 수신(벽시계, ROS 쪽) | 7.633(범위 7.469 ~ 7.801, n=4) s |
| px4 `healthy`(uxrce 연결)부터 `pre_flight_checks_pass` 참 수신(벽시계) | 2.579(범위 2.419 ~ 2.752, n=4) s |
| px4 `healthy`부터 bridge `healthy`(벽시계) | 8.908(범위 8.709 ~ 8.983, n=4) s |

뒤의 세 줄은 docker events가 남은 r2-r5(n=4)다. px4가 healthy가 된 순간에는 아직 준비 전일 수 있지만, 스택 `up --wait`가 끝나는 bridge healthy 때는 r2-r5 모두 이미 준비가 끝나 있었다. 운용 노드가 bridge 다음에 뜨면(D6) 보통 기다릴 일이 없다. 그래도 Executor는 준비 조건을 직접 확인한다.

의견
- PREPARING 순서(초안). (나)를 권한다.
  1. 식별 대조(P12): `vehicle_status` 수신과 `system_id` 일치. 명령은 여기까지 막는다.
  2. 준비 확인(P8의 NOT_READY 조건): `vehicle_status`, `vehicle_local_position`, `vehicle_land_detected`가 신선하고 `pre_flight_checks_pass`, `xy_valid`, `z_valid` 참, `failsafe` 거짓.
  3. 시작 조건(PRECONDITION_FAILED 조건): `landed` 참.
  4. 기준점 잡기: 지금 `vehicle_local_position`의 x, y, z를 TAKEOFF 시작 위치로 저장(P7).
  5. setpoint 발행 시작. 목표는 기준점 그대로(지상 위치). 목표 고도는 아직 주지 않는다.
  6. 신호 유효 확인: `failsafe_flags.offboard_control_signal_lost` 거짓을 받을 때까지(또는 발행 시작 뒤 ROS 시각 0.5 s 이상과 10회 이상 중 늦은 것). 앞의 것이 직접 근거이고 뒤의 것은 `failsafe_flags`를 구독하지 않을 때의 대체다.
  7. DO_SET_MODE(Offboard), ack ACCEPTED와 `nav_state` 14 확인. disarm 상태에서는 신호가 없어도 ACCEPTED라(P2) ack만으로는 6을 대신하지 못한다.
  8. arm, ack ACCEPTED와 `arming_state` 2 확인. 신호가 없으면 여기서 TEMPORARILY_REJECTED로 걸러진다.
  9. EXECUTING으로 넘어가 TAKEOFF 목표(기준점 z - `height_m`)를 setpoint에 넣는다.
- (나)를 고른 이유: (가)는 arm 뒤 Offboard 전환이 실패하면 지상 armed가 남는다. `COM_DISARM_PRFLT=-1`이고 이륙한 적이 없으면 착지 자동 disarm도 없어서(`Commander.cpp` 2285-2305행, `_have_taken_off_since_arming`) 무기한 armed다. (나)는 모드가 먼저 서고 arm이 마지막이라 실패한 단계 뒤에 치울 것이 적다. (나)에서 disarm하면 모드는 OFFBOARD로 남는다(P5 나, 다음 arm이 바로 Offboard).
- 단계별 타임아웃 기본값(노드 파라미터, ROS 시각). 실측 최대는 수십 ms이고 `vehicle_status`는 바뀔 때와 2 Hz로 나온다(최대 간격 0.508(범위 0.508 ~ 0.516, n=5) s, P13).
  - 상태 수신 대기(1, 2): 10 s. 스택이 healthy가 된 뒤에는 이미 준비되어 있으므로 길게 기다릴 이유가 없다.
  - 신호 유효 대기(6): 2 s.
  - 모드 확인(7), arm 확인(8): 각 2 s(상태 최대 간격의 약 4배). 명령 재송신 0.5 s.
- 실패 단계와 `reason`
  - 1의 미수신: NOT_READY(P12 충돌 예상 참조). 불일치: R5에서 정한다.
  - 2 미충족: NOT_READY. 3 미충족: PRECONDITION_FAILED.
  - 6 미충족: MODE_SWITCH_FAILED(Offboard에 들어갈 수 없음). 원인은 setpoint 경로이므로 `detail`에 적는다.
  - 7의 ack TEMPORARILY_REJECTED, ack 없음, 또는 `nav_state` 미확인: MODE_SWITCH_FAILED.
  - 8의 ack TEMPORARILY_REJECTED, DENIED, ack 없음, 또는 `arming_state` 미확인: ARM_REJECTED.
  - 실패 뒤 정리: setpoint 발행을 멈추고, armed이면 비강제 disarm(지상이라 받아들여진다, P5).

## P2. 신호 없는 Offboard 요청

[실측] c 시나리오(5회, 지상, setpoint 없음)

| 상태 | DO_SET_MODE(Offboard) ack | `nav_state`(사용자 의도) | 그 뒤 |
| --- | --- | --- | --- |
| disarm | 5회 모두 [0] | 4 -> 14 (14), failsafe 거짓, `pre_flight_checks_pass` 거짓 | 그 상태로 arm하면 ack 5회 모두 [1](TEMPORARILY_REJECTED) |
| arm(Hold) | 5회 모두 [1] | 4 그대로 | - |

[소스] disarm이면 `always_allow`(`UserModeIntention.cpp` 54-55행), armed이면 `canRun(OFFBOARD)`가 거짓이라 `TRANSITION_DENIED` -> TEMPORARILY_REJECTED(`Commander.cpp` 905-933행). A9는 "armed에서 TEMPORARILY_REJECTED"로 닫힌다.
[실측] armed에서 신호가 있어 ACCEPTED된 뒤에도 신호가 1 s 끊기면 `nav_state`가 18로 바뀐다(P1 m, P4 다).

의견: ack로 알 수 있는 것은 "그 순간 Commander가 사용자 의도를 바꿨다(armed이면 그 모드의 요구 조건이 그 순간 맞았다)"까지다. 실제로 그 모드로 비행 중인지, 그 뒤 failsafe로 바뀌었는지는 `vehicle_status.nav_state`와 `failsafe`로만 안다. 그래서 Executor는 모드 명령마다 ack와 `nav_state`를 둘 다 확인하고, 실행 중에는 `nav_state`를 계속 감시한다. disarm 상태의 ACCEPTED는 신호 유무를 말해 주지 않는다(builder 주석 "시동 전 Offboard에서도 ACCEPTED"가 실측으로 맞다).

## P3. DO_SET_MODE와 SET_NAV_STATE

[소스] `Commander.cpp` 800-946행. 둘 다 `_user_mode_intention.change(nav_state, getSourceFromCommand(cmd), ...)`로 같은 함수에 들어간다. 차이는 셋이다.
- DO_SET_MODE는 base_mode와 custom main/sub mode를 nav_state로 바꾸고, AUTO_LAND일 때만 `force`를 켠다(910행). SET_NAV_STATE는 param1을 nav_state로 그대로 쓰고 force가 없다.
- SET_NAV_STATE(100001)는 `VEHICLE_CMD_PX4_INTERNAL_START`(65537) 위의 PX4 내부 명령이다(`msg/versioned/VehicleCommand.msg` 112-114행). MAVLink에 대응 명령이 없고 MAVLink로 내보내지지 않는다(`streams/COMMAND_LONG.hpp`의 `px4_internal_cmd`).
- DO_SET_MODE는 QGC가 MAVLink로 보내는 것과 같은 경로다.
[실측] c 시나리오(5회): SET_NAV_STATE(14) disarm, SET_NAV_STATE(4) 공중, SET_NAV_STATE(14) 공중 모두 ACCEPTED이고 `nav_state`가 같은 지연으로 바뀌었다(5회 모두 [0], 5회 모두 [0]).

의견: DO_SET_MODE를 유지한다. 바꿀 이점이 없고, Land의 force와 MAVLink 도구(QGC, 로그 해석)와 같은 의미를 잃는다. builder의 param1 = 1(CUSTOM_MODE_ENABLED)이 빠지면 base_mode 분기로 가서 의도와 다른 모드가 될 수 있으니 builder 밖에서 DO_SET_MODE를 만들지 않는 지금 규칙도 그대로 둔다.

## P4. Hold 실험

[실측] (가) Offboard 호버 중 `set_mode_hold`(a, 5회): ack 5회 모두 [0](모두 첫 송신 ACCEPTED). 명령부터 `nav_state` 4까지 0.028(범위 0.020 ~ 0.032, n=5) s. 명령 뒤 3 s 동안 위치 변화 최대 0.040(범위 0.030 ~ 0.052, n=5) m.
[실측] (나) 이어서 setpoint를 끊음(a, 5회): `offboard_control_signal_lost`는 1.076(범위 0.976 ~ 1.084, n=5) s 뒤 참이 되지만 `nav_state`는 8 s 동안 4 그대로(5회 모두 [4]), `failsafe` 5회 모두 [false], 위치 변화 최대 0.047(범위 0.034 ~ 0.075, n=5) m. 신호 손실은 Hold에 영향이 없다.
[실측] (다) setpoint를 끊어 failsafe Land를 일으키고 2 s 뒤 `set_mode_hold`(b, 5회): 끊은 뒤 `nav_state` 18까지 1.080(범위 1.004 ~ 1.092, n=5) s, 그때 `failsafe` 참, `nav_state_user_intention` 14. Hold ack 5회 모두 [0], 명령부터 `nav_state` 4까지 0.028(범위 0.016 ~ 0.032, n=5) s, 그 뒤 `failsafe` 거짓, `nav_state_user_intention` 4, `failsafe_and_user_took_over` 거짓(5회 모두 {"failsafe": false, "nav_state_user_intention": 4, "failsafe_and_user_took_over": false}). 하강이 멈췄다(Hold 뒤 5 s 동안 z 변화 0.048(범위 0.038 ~ 0.059, n=5) m).
[실측] (라) failsafe Land 중 setpoint 재개(c, 5회): 재개만으로 명령 없이 `nav_state`가 14로 돌아왔다(0.052(범위 0.036 ~ 0.064, n=5) s). 그 뒤 Hold는 (가)와 같이 받아들여졌다(5회 모두 [0]).
[실측] (마) 위치 추정 무효: 1회(따로 올린 스택 k=1). `px4-failure gps off`는 gz SITL에서 지원되지 않았다("ERROR [failure] Timeout waiting for ack"). 대신 Offboard 호버(5 m) 중 `EKF2_GPS_CTRL`을 7에서 0으로 바꿔 GPS 융합을 끊었다. 4.2 s 뒤(`EKF2_NOAID_TOUT` 5 s 근처) `failsafe_flags`의 `local_position_invalid`, `local_position_invalid_relaxed`, `global_position_invalid`, `local_velocity_invalid`가 함께 섰고, 같은 순간 Offboard 신호도 무효가 되어(position flag는 위치 유효를 요구한다) `nav_state` 12(Descend, 사용자 의도 14, `failsafe` 참)로 바뀌었다. Land는 local position relaxed를 요구해서 못 들어가고 Descend로 내려간 것이다. 이 상태에서 DO_SET_MODE(Hold) 17회와 DO_SET_MODE(Offboard) 17회가 모두 TEMPORARILY_REJECTED였다. NAV_LAND는 ACCEPTED(force)였지만 `nav_state`는 12 그대로였다(사용자 의도 18, `failsafe_and_user_took_over` 참). Descend는 약 7 s 만에 땅에 닿았는데 setpoint를 계속 낸 43 s 동안 `landed`가 서지 않았고, setpoint를 끊자 1.0 s 뒤 `landed`, 다시 2.0 s 뒤 disarm되었다(1절과 같은 현상). disarm 뒤 `nav_state`는 14였다.

[소스] failsafe 중의 사용자 모드 요청
- Offboard 손실은 "mode fallback"이다(`failsafe/failsafe.cpp` 637-641행, `checkModeFallback` 659-680행). 사용자 의도(OFFBOARD)는 그대로 두고 동작만 COM_OBL_RC_ACT(Land)로 바꾸며 `allowUserTakeover(Always)`, `cannotBeDeferred`다. 그래서 COM_FAIL_ACT_T(5 s) 지연 Hold 없이 바로 Land가 된다(지연은 Auto 항목에만 걸린다, `framework.cpp` 351-361행, 495-500행).
- failsafe 동작 중 사용자 의도가 바뀌면 "user takeover"다(`framework.cpp` 502-528행). 허용 정도가 Always 또는 AlwaysModeSwitchOnly이고 동작이 Hold, RTL, Land, Descend 중 하나면 failsafe를 Warn으로 낮추고 새 모드를 따른다. 그 뒤 새 모드에 대해 fallback을 다시 본다(529-534행). Hold는 offboard 신호를 요구하지 않으므로 fallback이 없다.
- 신호가 돌아오면 fallback 조건이 사라져 동작이 지워지고 사용자 의도(OFFBOARD)로 돌아간다(`checkFailsafe`의 invalid -> valid 전이, `framework.cpp` 377행 이하). (라)의 실측이 이것이다.
- armed 상태의 Hold 전환은 `canRun(AUTO_LOITER)`를 본다. 멀티콥터 Hold는 angular velocity, attitude, global position, local position, local alt를 요구한다(`mode_requirements.cpp` 110-124행). 이것이 맞지 않으면 DO_SET_MODE(Hold)는 TEMPORARILY_REJECTED다. Land는 force라서 항상 받아들여지고(910행, `Commander.cpp` 1093-1108행), 실행 가능성은 failsafe 상태기가 다시 본다(Land는 local position relaxed와 local alt, 안 되면 Descend, `framework.cpp` 537-606행).

의견: 취소 분기 확정안

| 취소 시점의 상태 | 판정 근거 | Executor 동작 | GoalStatus, `reason` |
| --- | --- | --- | --- |
| 공중, 정상(Offboard) | `nav_state` 14, `failsafe` 거짓, `landed` 거짓 | setpoint를 유지한 채 DO_SET_MODE(Hold). ack ACCEPTED와 `nav_state` 4를 확인하면 즉시 setpoint 발행 중단 | CANCELED, NONE |
| 공중, failsafe 진행 중 | `failsafe` 참(또는 `nav_state` != 14이고 Executor가 요청한 것이 아님) | 모드 명령을 보내지 않는다. setpoint는 이미 멈춰 있어야 한다(1절) | ABORTED, FAILSAFE |
| 공중, Hold 확인 실패 | ack TEMPORARILY_REJECTED, 또는 타임아웃 안에 `nav_state` 4 미확인 | Land(NAV_LAND) 송신, setpoint 즉시 중단 | ABORTED, MODE_SWITCH_FAILED |
| 상태 미수신 | `vehicle_status`가 LINK_LOST 임계를 넘김 | 명령을 보내지 않는다(받을 수 없다). setpoint 중단 | ABORTED, LINK_LOST |

- failsafe 중에는 Hold를 보내지 않는 쪽을 권한다. PX4는 Hold로 failsafe를 덮어쓰게 허용하지만(실측 다), 그러면 미션 계층이 PX4의 안전 동작(지금은 Offboard 손실 Land, 나중에는 다른 failsafe도 같은 takeover 규칙)을 취소 요청 하나로 무르게 된다. 또 failsafe가 보이면 Executor는 취소 전에 이미 ABORTED(FAILSAFE)로 끝냈어야 하고, 취소는 그 경합일 뿐이다. 지금 잠정 규칙(failsafe 중 취소 = Hold 확인 실패와 같은 경로, 즉 Land)은 결과적으로 Land를 한 번 더 보낼 뿐이라 해롭지 않지만, 위 표처럼 명령 없이 FAILSAFE로 끝내는 것이 원인을 맞게 남긴다. 사용자에게 알릴 정책 변경 후보다(README의 사용자 결정 후보 7).
- Hold 확인 타임아웃 기본값: 2.0 s(노드 파라미터, ROS 시각). 실측 명령부터 `nav_state` 4까지 최대 0.032 s, 상태 발행 최대 간격 0.516 s이므로 그 합의 약 4배다. 그동안 setpoint를 유지하므로 Offboard 손실(1 s)과는 무관하다. 재송신 0.5 s 간격으로 최대 4회.
- 확인 실패 때 Land를 보내는 규칙은 맞다. Hold가 거부되는 원인은 위치 추정 무효뿐이고(P10), 그때 쓸 수 있는 것은 force인 Land(필요하면 PX4가 Descend로 낮춘다)다. 다만 Land를 보내는 순간 setpoint를 끊어야 한다(1절). 끊지 않으면 착지 판정이 나지 않는다.
- C32 구분: `TYPE_LOITER`는 Offboard setpoint를 같은 위치로 계속 내는 것이고 `nav_state`는 14다. Hold(`MODE_HOLD`, `nav_state` 4)는 PX4 navigator가 위치를 잡는 것이고 Executor는 setpoint를 내지 않는다. LOITER 항목 중에는 `nav_state` 4가 보이면 외부 변경이다.

## P5. 지상 취소와 disarm

[실측] 비강제 disarm(5회씩)

| 시점 | ack | 결과 | 그때 `vehicle_land_detected` |
| --- | --- | --- | --- |
| (가) Hold 모드 arm 1 s 뒤, 지상 | 5회 모두 [0] | DISARMED | landed 참 |
| (나) Offboard에서 arm 직후, TAKEOFF setpoint(5 m 위)를 내는 중 | 5회 모두 [0] | DISARMED. disarm 뒤 `nav_state`는 14(14(5회 모두)) | 5회 모두 {"landed": true, "maybe_landed": true, "ground_contact": true} |
| (다) LAND 하강 중 높이 1.5 m 아래부터 약 15 Hz로 연타 | `maybe_landed`가 서기 전까지 모두 TEMPORARILY_REJECTED, 선 뒤 첫 시도에 ACCEPTED | 접지 높이에서 DISARMED(-0.057(범위 -0.103 ~ -0.034, n=5) m) | 수락 때 5회 모두 {"landed": false, "maybe_landed": true, "ground_contact": true}, 마지막 거부 때 회차별 [{"landed": false, "maybe_landed": false, "ground_contact": true}, {"landed": false, "maybe_landed": true, "ground_contact": true}](한 회차는 탐침이 `maybe_landed` 참을 받은 뒤의 거부였다. 탐침과 Commander가 같은 표본을 보는 시점이 몇 ms 다르기 때문으로 본다[추정]) |

[실측] Offboard에서 TAKEOFF 목표를 준 채 arm한 뒤 `landed`가 거짓으로 바뀌기까지 1.808(범위 1.792 ~ 1.840, n=5) s(그때 높이 변화 -0.013(범위 -0.111 ~ 0.032, n=5) m, 아직 땅 위). 그 전에는 비강제 disarm이 된다.
[소스] `Commander.cpp` 638-660행: 비강제 disarm은 `landed || maybe_landed`(또는 지상 차량)일 때만 되고 아니면 `TRANSITION_DENIED`, ack는 TEMPORARILY_REJECTED(948-980행). `maybe_landed`는 `landed`보다 약 0.3 s 먼저 선다(P6).

의견
- Executor의 "지상" 판정: `vehicle_land_detected`가 신선하고 `landed` 참. `maybe_landed`만 참인 구간(약 0.3 s)은 지상으로 보지 않는다(보수 쪽). 두 판정이 다른 짧은 구간에서 취소가 오면 공중 분기로 가고, Hold가 받아들여지면 지면 근처 Hold가 된다. 해롭지 않다.
- 지상 취소: armed면 비강제 disarm, ack와 `arming_state` 1 확인 뒤 CANCELED, NONE. disarm이면 명령 없이 CANCELED, NONE. setpoint는 먼저 멈춘다.
- disarm이 거부(TEMPORARILY_REJECTED)되면 PX4가 지상으로 보지 않는다는 뜻이다(원문상 다른 거부 원인이 없다). 다시 보내지 말고 공중 분기(Hold)로 넘어간다. ack도 `arming_state` 변화도 타임아웃(2 s, ROS 시각) 안에 없으면 `vehicle_status`가 신선한지 보고, 신선하지 않으면 ABORTED, LINK_LOST, 신선한데 armed 그대로면 공중 분기로 넘어간다. 강제 disarm은 쓰지 않는다(결정 (r)).
- PREPARING이나 TAKEOFF 시작 직후(이륙 전) 실패하면 반드시 disarm까지 하고 끝낸다. 이륙한 적이 없으면 자동 disarm이 없다(P1).

## P6. LAND 항목

[소스] NAV_LAND는 Commander가 param을 하나도 읽지 않는다(`Commander.cpp` 1093-1108행, force로 AUTO_LAND 의도 설정). navigator `Land::on_activation`(`navigator/land.cpp`)은 현재 위치에 착륙 항목을 만들고 멀티콥터면 정지점을 앞으로 투영한다. navigator는 vehicle_command의 NAV_LAND param을 읽지 않는다. `VehicleCommand.msg` 16행의 "param4 yaw, 5-7 lat/lon/alt"는 MAVLink 정의를 옮긴 설명이고 v1.17.0의 이 경로에서는 쓰이지 않는다. builder의 "param4-7 NaN"은 MAVLink 의미로 "현재 값 사용"이고, v1.17.0에서는 어떤 값이어도 같다. 하강 속도는 MPC_LAND_ALT1 10 m 위에서 MPC_Z_V_AUTO_DN 1.5, MPC_LAND_ALT2 5 m 아래에서 MPC_LAND_SPEED 0.7 m/s이고 그 사이는 보간이다[문서](https://docs.px4.io/main/en/advanced_config/parameter_reference.html, MPC_LAND_ALT1, MPC_LAND_ALT2 설명).
[실측] 호버(5 m) 중 `land()`, setpoint를 명령 직후 끊음(a, 5회)

| 항목 | 값 |
| --- | --- |
| ack | 모두 첫 송신 ACCEPTED |
| 명령부터 `nav_state` 18 | 0.024(범위 0.024 ~ 0.028, n=5) s |
| 최대 하강 속도 | 0.740(범위 0.732 ~ 0.744, n=5) m/s, 마지막 1 m 평균 0.394(범위 0.388 ~ 0.411, n=5) m/s |
| `ground_contact` -> `maybe_landed` | 0.352(5회 모두) s |
| `maybe_landed` -> `landed` | 0.336(5회 모두) s |
| `landed` -> `arming_state` 1 | 2.016(범위 2.012 ~ 2.016, n=5) s |
| 명령부터 disarm | 10.9(범위 10.8 ~ 11.0, n=5) s |
| `latest_disarming_reason` | 6(5회 모두)(6 = `auto_disarm_land`, `src/lib/events/enums.json`) |
| disarm 뒤 `nav_state` | 4(5회 모두) |

[실측] `COM_DISARM_LAND`의 실제 값 2.0000(`px4-param show` 원문, 아래 P10). `LNDMC_TRIG_TIME` 1.0.
[실측] setpoint를 계속 냈을 때는 1절과 같이 착지 판정이 나지 않았다(c, 5회).
[실측] disarm 뒤 `nav_state`는 Land가 아니라 Land 전의 마지막 "시동을 막지 않는" 사용자 의도다(`UserModeIntention.cpp` `_nav_state_after_disarming`). a, b, c에서는 4였지만 (나) 순서에서 Land 없이 disarm하면 14로 남는다. 다음 미션이 시작 모드를 가정하면 안 된다.

의견
- land 완료 판정: `vehicle_status.arming_state` == DISARMED(1)를 "최신 상태 N회 연속"으로 본다. `vehicle_land_detected.landed` 참은 중간 단계(feedback용)다. `latest_disarming_reason`은 진단용으로 `detail`에 남긴다.
- setpoint 발행은 NAV_LAND ack ACCEPTED 또는 `nav_state` 18 확인 즉시 멈춘다. 확인이 늦어도 Land 명령 뒤 ROS 시각 2 s에 멈춘다(그 경우 Offboard 손실 failsafe Land가 같은 결과를 낸다).
- 자동 disarm이 오지 않을 때: `landed` 참을 확인한 뒤 ROS 시각 5 s(COM_DISARM_LAND 2.0 + 여유. 노드는 이 PX4 값을 리터럴로 품지 않고 자기 파라미터로 둔다) 안에 disarm되지 않으면 비강제 disarm을 보낸다(지상이라 받아들여진다). 그래도 안 되면 항목 `timeout`까지 기다린 뒤 ITEM_TIMEOUT. `landed`가 오지 않으면(setpoint를 멈추지 않은 경우가 실측된 유일한 원인) 항목 `timeout`으로 ITEM_TIMEOUT.

## P7. TAKEOFF 항목

[소스] Offboard에서 mc_pos_control은 상승 속도 제한을 `MPC_Z_VEL_MAX_UP`, 하강을 `MPC_Z_VEL_MAX_DN`으로 덮어쓴다(`MulticopterPositionControl.cpp` 464-491행). 이륙 램프(`MPC_TKO_RAMP_T`)와 `want_takeoff`(setpoint의 z가 현재보다 위이고 setpoint timestamp가 1 s 안)가 함께 걸린다(466-497행, 527-544행). 수평은 `MPC_XY_VEL_MAX`.
[실측] 이 스택의 값(`px4-param show`): `MPC_Z_VEL_MAX_UP` 3.0, `MPC_Z_VEL_MAX_DN` 1.5, `MPC_XY_VEL_MAX` 12.0, `MPC_TKO_RAMP_T` 3.0, `MPC_TKO_SPEED` 1.5(Offboard에서는 쓰이지 않는다), `MPC_ACC_UP_MAX` 4.0, `MPC_Z_V_AUTO_UP` 3.0.
[실측] 지상에서 상대 높이 5 m setpoint 하나(a, 5회. setpoint의 `velocity`는 NaN)

| 항목 | 값 |
| --- | --- |
| 최대 상승 속도 | 2.536(범위 2.532 ~ 2.546, n=5) m/s |
| overshoot | 0.020(범위 0.016 ~ 0.026, n=5) m |
| 목표 +-0.5 m 첫 진입 | 6.632(범위 6.612 ~ 6.700, n=5) s |
| 목표 +-0.3 m 첫 진입 | 7.596(범위 7.556 ~ 7.880, n=5) s |
| 목표 +-0.2 m 첫 진입 | 8.332(범위 8.232 ~ 8.780, n=5) s |
| 목표 +-0.1 m 첫 진입 | 9.792(범위 9.672 ~ 10.3, n=5) s |
| 첫 진입 뒤 다시 벗어난 회수(0.1, 0.2, 0.3, 0.5 m) | 0/5, 0/5, 0/5, 0/5 |
| 정착(+-0.3 m 진입 5 s 뒤부터) 30 s 동안 z 표준편차 | 0.009(범위 0.007 ~ 0.026, n=5) m |
| 같은 구간 z 최대 편차 | 0.026(범위 0.021 ~ 0.076, n=5) m |
| 같은 구간 수평 최대 편차(시작 위치 기준) | 0.051(범위 0.042 ~ 0.059, n=5) m |
| arm 전 지상 60 s 동안 z 범위 | 0.131(범위 0.064 ~ 0.276, n=5) m(표준편차 0.026(범위 0.015 ~ 0.058, n=5), 앞뒤 5 s 평균 차 0.083(범위 0.029 ~ 0.200, n=5)) |
| `vehicle_local_position` 수신 주기(ROS 쪽) | 50.0(범위 50.0 ~ 50.0, n=5) Hz |

"상승 속도 필드를 두지 않는다"(C6)의 근거는 이제 [소스]와 [실측]이다. 속도는 PX4 파라미터가 정하고, 필요하면 Executor가 setpoint의 velocity feedforward나 중간 목표로 낮출 수 있다(지금은 필요 없다).

의견
- `acceptance_m` 기본값 0.3 m. 호버 최대 편차의 약 4배이고 0.3 m 첫 진입 뒤 벗어난 적이 없다. 거리는 기준점에서 목표까지의 3차원 거리로 잰다(수평 편차도 0.06 m 안이라 z만 볼 때와 결과가 같다).
- 도달 판정: 표본 개수가 아니라 ROS 시각 지속 시간으로 정한다. "+-`acceptance_m` 안에 0.5 s 연속". 50 Hz에서 약 25개다. 수신 주기가 바뀌어도 의미가 같다. 개수로 정해야 하면 10회 연속(50 Hz에서 0.2 s).
- 기준점은 PREPARING 4단계, arm 직전의 `vehicle_local_position`(xy_valid, z_valid 참인 최신 표본)으로 잡는다. 노드 activate나 goal 수락 시점이 아니다. 지상에 서 있을 때 EKF z는 60 s 동안 최대 0.28 m 범위로 움직였고(위 표, 앞뒤 5 s 평균 차 최대 0.20 m) 비행 중의 판정은 같은 추정 좌표계에서 하므로, 기준점은 미션마다 그 항목 직전에 다시 잡는다. 이 drift가 `acceptance_m` 0.3 m에 가깝다는 점은 test(T3)의 "목표 고도 도달" 독립 판정(예: Gazebo 기체 pose)을 정할 때 고려해야 한다.
- 5 m 상승이 약 8 s이므로 통합 테스트의 TAKEOFF `timeout`은 30 s(ROS 시각)면 충분하다[추정, 높이 5 m 기준].

## P8. 지상과 공중의 판정

[소스] `vehicle_land_detected`(v1.17.0 `msg/versioned/VehicleLandDetected.msg`, `land_detector/MulticopterLandDetector.cpp`)
- `landed`: disarm이면 항상 참(296행 `!_armed || ...`). armed이면 `maybe_landed`가 `LNDMC_TRIG_TIME`/3 x 계수(1 또는 3) 동안 지속(316-321행).
- `maybe_landed`: disarm이면 참. armed이면 최소 추력, 자유낙하 아님, 회전 없음, `ground_contact` 지속(287-290행).
- `ground_contact`: 수직 속도 작음, 수평 이동 없음, 하강 의도 없음 또는 최소 추력(159-250행).
- `in_descend`는 `trajectory_setpoint.velocity[2]`에서 온다(225-230행). 1절의 섞임이 여기에 보인다.
[실측] arm 전: `landed`, `maybe_landed`, `ground_contact`, `at_rest` 모두 참. Offboard에서 TAKEOFF 목표를 준 채 arm한 뒤 `landed`는 1.808(범위 1.792 ~ 1.840, n=5) s, `ground_contact`는 1.816(범위 1.800 ~ 1.848, n=5) s 뒤 거짓이 되었다(높이는 아직 수 cm). 착지 때는 `ground_contact` -> `maybe_landed`(0.352(5회 모두) s 뒤) -> `landed`(다시 0.336(5회 모두) s 뒤) 순서.

의견: NOT_READY와 PRECONDITION_FAILED

| 조건 | 판정 |
| --- | --- |
| `vehicle_status` 미수신 또는 묵음(LINK_LOST 임계 초과) | NOT_READY |
| `vehicle_local_position` 또는 `vehicle_land_detected` 미수신, 묵음 | NOT_READY |
| `pre_flight_checks_pass` 거짓 | NOT_READY |
| `xy_valid` 또는 `z_valid` 거짓 | NOT_READY |
| `failsafe` 참 | NOT_READY |
| `nav_state` TERMINATION | NOT_READY |
| 위가 모두 맞고 `landed` 거짓(공중) | PRECONDITION_FAILED |
| 위가 모두 맞고 `landed` 참, armed | 시작한다. arm 단계는 건너뛴다(이미 armed면 arm ack는 ACCEPTED, `TRANSITION_NOT_CHANGED`, `Commander.cpp` 551행). 앞 미션이 남긴 지상 armed를 받아 준다 |

경계: NOT_READY는 "PX4가 아직 어떤 항목도 시작할 수 없거나 Executor가 판단할 정보가 없다", PRECONDITION_FAILED는 "PX4는 준비됐지만 이 항목의 시작 조건(TAKEOFF는 지상)이 아니다". 앞의 것은 기다리면 풀릴 수 있고 뒤의 것은 미션을 바꿔야 풀린다.

## P9. sim 시간 timestamp 경로의 failsafe 회귀

[소스] `/fmu/in` 역직렬화는 timestamp가 0이 아니면 `min(timestamp - time_offset, hrt_absolute_time())`(`Tools/msg/templates/ucdr/msg.h.em` 167-169행), SYNCT=0이라 offset 0. 판정은 P1의 `now < timestamp + COM_OF_LOSS_T`.
[실측] Offboard 호버(5 m) 중 setpoint timestamp를 ROS 시각보다 묵게(20 Hz 유지, 각 5회)

| 묵음 | `offboard_control_signal_lost` | 서기까지 | `nav_state` 18까지 |
| --- | --- | --- | --- |
| 0.5 s | 10 s 동안 한 번도 서지 않음(5회 모두 false) | - | - |
| 0.9 s | 10 s 동안 한 번도 서지 않음(5회 모두 false) | - | - |
| 1.1 s | 매번 섬 | 0.104(범위 0.076 ~ 0.136, n=5) s | 0.116(범위 0.088 ~ 0.148, n=5) s |
| 2.0 s | 매번 섬 | 0.076(범위 0.052 ~ 0.132, n=5) s | 0.088(범위 0.064 ~ 0.144, n=5) s |

[실측] failsafe Land 뒤 setpoint를 0.5 s 안에 멈췄을 때 멈춤부터 disarm까지 10.4(범위 10.2 ~ 10.5, n=5) s(1.1 s), 10.3(범위 10.3 ~ 10.4, n=5) s(2.0 s). 묵은 setpoint를 계속 내면 착지 판정이 나지 않는다(1절).
[실측] 정상 발행에서 PX4가 본 setpoint의 나이는 직접 잴 수 없었다. ULog는 `offboard_control_mode`를 기록하지만 기록되는 timestamp가 위의 `min(...)` 뒤 값이고 수신 시각이 따로 없다. 간접 값 둘. (1) `vehicle_status.timestamp - 수신 시 ROS 시각`이 최소 -176, 중앙값 0, 최대 +4(회차별 값을 모음, n=5) ms였다. 탐침이 본 ROS 시각은 모두 4 ms의 배수였다. (2) 묵음 2.0 s에서 손실이 서기까지 걸린 0.076(범위 0.052 ~ 0.132, n=5) s는 "다음 발행(최대 50 ms) + Commander 점검 주기 + `failsafe_flags` 발행"의 지연이고, 묵음 1.1 s에서 걸린 0.104(범위 0.076 ~ 0.136, n=5) s의 최솟값이 0.1 s보다 작으므로 정상 발행의 PX4 쪽 나이는 적어도 약 0.024 s다[추정, 이 역산]. 위의 (1)과 합치면 정상 나이는 수십 ms이고 COM_OF_LOSS_T 1.0 s에 대한 여유는 0.9 s 이상이다[추정]. 0.9 s 묵음이 5회 모두 정상이었던 것과 맞는다.

의견
- 회귀 판정 경계: "반드시 failsafe"는 묵음 1.5 s(서기까지 ROS 시각 2 s 안), "반드시 정상"은 묵음 0.5 s(10 s 동안 한 번도 서지 않음). 0.9 s도 실측상 정상이지만 남는 여유가 0.1 s보다 작아(정상 나이 수십 ms) CI 부하에서의 `/clock` 지연에 걸릴 수 있어 판정에 쓰지 않는다. 1.1 s는 경계 반대쪽으로 같은 정도만 떨어져 있어 같은 이유로 쓰지 않는다.
- 회귀 테스트는 failsafe를 확인한 뒤 setpoint를 멈춰야 착지와 disarm까지 간다(1절). 확인할 것은 `failsafe_flags.offboard_control_signal_lost` 참과 `vehicle_status.failsafe` 참, `nav_state` 18이다.
- S5에 `vehicle_status.timestamp - 수신 시 ROS 시각`의 판정을 넣는 데 찬성한다. 이 경로가 깨지는 경우(SYNCT가 1로 돌아감, 노드가 벽시계를 씀)는 차이가 수 s에서 수십 년이라 작은 상한으로 충분하다. 제안: 20개 표본의 중앙값 절댓값 0.1 s 이하, 최대 절댓값 0.5 s 이하(COM_OF_LOSS_T의 반). 실측 최소 -176 ms는 한 번의 수신 지연이라 최대 판정을 0.5 s로 둔다.

## P10. Hold와 반복 비행 중의 다른 failsafe

[실측] 이 스택의 `px4-param --instance 1 show` 원문(r1 전 스택, 1006행, scratchpad `px4exp/param_show_all.txt`)

| 분류 | 값 |
| --- | --- |
| 배터리 | `COM_LOW_BAT_ACT` 3, `BAT_LOW_THR` 0.15, `BAT_CRIT_THR` 0.07, `BAT_EMERGEN_THR` 0.05, `COM_ARM_BAT_MIN` -1, `COM_FLTT_LOW_ACT` 0 |
| 배터리 시뮬레이션 | `SIM_BAT_ENABLE` 1, `SIM_BAT_DRAIN` 60 s, `SIM_BAT_MIN_PCT` 50 |
| geofence | `GF_ACTION` 2, `GF_MAX_HOR_DIST` 0, `GF_MAX_VER_DIST` 0, `GF_SOURCE` 0, `GF_PREDICT` 0 |
| 바람 | `COM_WIND_MAX` -1, `COM_WIND_MAX_ACT` 0, `COM_WIND_WARN` -1 |
| 비행 시간 | `COM_FLT_TIME_MAX` -1 |
| 위치 정확도 | `COM_POS_LOW_EPH` -1, `COM_POS_LOW_ACT` 3, `COM_POS_FS_EPH` 5 |
| 링크 | `NAV_DLL_ACT` 0, `COM_RC_IN_MODE` 4, `NAV_RCL_ACT` 2, `COM_OF_LOSS_T` 1.0, `COM_OBL_RC_ACT` 4, `COM_FAIL_ACT_T` 5.0 |
| 착지, 시동 | `COM_DISARM_LAND` 2.0, `COM_DISARM_PRFLT` -1.0 |

[소스] `BatterySimulator.cpp` 79-101행: armed일 때만 `SIM_BAT_DRAIN`(60 s)에 걸쳐 줄고, disarm이면 1.0으로 돌아가며, `SIM_BAT_MIN_PCT`/100 아래로 내려가지 않는다. `failsafe.cpp` 542-605행: 바람은 `COM_WIND_MAX`가 음수면 꺼짐, 비행 시간은 `COM_FLT_TIME_MAX` 음수면 꺼짐, 위치 정확도는 Hold와 Mission에서만 보고 `COM_POS_LOW_EPH` 음수면 꺼짐, geofence는 거리 0이면 꺼짐(geofence 파일 없음), RC 손실은 `COM_RC_IN_MODE` 4면 검사하지 않음(493행), GCS 손실은 `NAV_DLL_ACT` 0이면 검사하지 않음(515행).
[실측] 배터리 잔량(5회): armed 동안 1분에 약 0.5씩 줄어 0.500(5회 모두)에서 멈췄고(최솟값), disarm하면 1.0 근처로 돌아왔다. 경고(`battery_warning`) 최댓값 0(5회 모두). `BAT_LOW_THR` 0.15에 닿을 수 없다.

의견: "Hold에서 벗어나는 경로"(이 SITL 파라미터에서 확인한 범위)
1. 위치 추정 무효(global position 또는 local position 또는 local alt). mode fallback으로 Land, 안 되면 Descend(P4 마).
2. 외부 모드 명령(QGC, 사람이 보내는 CLI, 다른 노드). PX4는 source를 가리지 않는다(P13).
3. 자세, 각속도 무효(Hold, Land, Descend 모두 못 하면 Terminate로 내려감. `framework.cpp` 537-606행). SITL에서 일어날 일은 없다고 본다[추정].
4. disarm(외부 명령, kill). 공중 비강제 disarm은 거부된다.
배터리, geofence, 바람, 비행 시간, RC 손실, GCS 손실, 위치 정확도는 이 값에서 꺼져 있거나 닿을 수 없다. Hold에는 시간 제한이 없다(`COM_HLDL_LOSS_T`는 고지연 링크용이다).
`sitl_params.env`에 더할 값은 없다. 배터리 failsafe를 막고 있는 것은 `SIM_BAT_MIN_PCT` 50인데 이것은 펌웨어 기본값이다([소스] `battery_simulator_params.c` 71행). PX4 버전을 올릴 때 이 기본값이 바뀌면 반복 실행이나 긴 Hold에서 배터리 failsafe(`COM_LOW_BAT_ACT` 3)가 생길 수 있으므로, 명시해 두는 것은 선택 사항으로 남긴다. 명시한다면 S4의 param 기대값에도 넣는다.

## P11. source 값 표

[실측] 비행마다 `vehicle_command_ack` 전부를 기록했다(a, b, c, m, s1, s2 x 5회). 받은 ack의 (target_system, target_component)는 탐침의 (254, 1)과 c의 외부 모드 실험 (255, 190)뿐이었다. PX4 내부 명령의 ack(target이 (2, 1))는 이 비행들에서 한 번도 나오지 않았다. ack의 `from_external`은 모두 거짓이었다(ack는 PX4가 만든 것이라서다). c 시나리오 한 번의 분포(키는 "target_system/target_component cmd=명령 res=결과", 값은 개수): 5회 모두 {"254/1 cmd=176 res=0": 4, "254/1 cmd=400 res=1": 1, "254/1 cmd=400 res=0": 3, "254/1 cmd=176 res=1": 1, "254/1 cmd=100001 res=0": 3, "255/190 cmd=176 res=0": 1, "254/1 cmd=21 res=0": 1}.
[소스] 내부 명령은 source를 자기 (MAV_SYS_ID, MAV_COMP_ID)로 채운다(Commander `send_vehicle_command`, `Commander.cpp` 179-182행. navigator `publish_vehicle_command`, `navigator_main.cpp` 1402-1409행, `from_external = false`). ack는 `target = cmd.source`(`Commander.cpp` 2677-2678행). 그래서 외부 송신자가 (기체 sysid, 1)을 source로 쓰면 PX4 내부 명령의 ack와 구별되지 않는다(B3). navigator가 착륙 중단(`land.cpp`의 DO_REPOSITION)이나 미션에서 명령을 내는 경우가 있다.
[소스] B2. `src/modules/mavlink/streams/COMMAND_LONG.hpp` 82-94행: uORB `vehicle_command` 중 `!from_external`이고 PX4 내부 명령 번호가 아니고 "target == 자기, source == target"이 아닌 것은 `MavlinkCommandSender`로 MAVLink에 내보낸다. 우리 명령은 target이 기체 자신이고 source가 다르므로 `from_external=false`면 MAVLink로 다시 나간다. builder 주석의 근거다.
[소스] `source_component >= 1000`(`COMPONENT_MODE_EXECUTOR_START`)이면 모드 변경의 출처를 ModeExecutor로 본다(`Commander.cpp` 1559-1563행). `from_external`이고 `source_component == 190`이면 모드 거부 사유를 출력한다(919행). 그 밖에 Commander는 source 값을 판정에 쓰지 않는다(`handle_command`는 target만 본다, 743-750행).

의견: 역할별 표(제안)

| 역할 | source_system | source_component | 비고 |
| --- | --- | --- | --- |
| Mission Executor | 250 | 1 | 모든 기체의 Executor가 같은 값을 써도 된다(아래) |
| pytest 하네스(`tests/support`) | 251 | 1 | 통합 테스트가 직접 보내는 명령(teardown disarm 등) |
| 손으로 보내는 CLI(진단 도구) | 252 | 1 | |
| `check_px4.py`(스모크 S3) | 254 | 1 | 지금 값 유지 |

금지 조합
- source가 (대상 기체의 MAV_SYS_ID, 1): PX4 내부 명령의 ack와 섞인다.
- source_system 1-99: 기체 sysid 대역(지금은 N+1 = 2-10. 기체가 늘어도 겹치지 않게 넓게 잡는다).
- source_system 255, source_component 190: QGC의 관례 값(QGC가 붙으면 ack가 섞이고, 190이면 Commander가 QGC로 보고 출력을 바꾼다).
- source_system 0, source_component 0, source_component >= 1000.
- `from_external` 거짓. target_system 0(브로드캐스트), target_component 0.
기체가 여럿일 때: ack는 기체마다 다른 네임스페이스 토픽(`/px4_N/fmu/out/vehicle_command_ack`)으로 오므로 Executor끼리 값이 같아도 섞이지 않는다. 같은 기체에 명령을 보내는 서로 다른 역할(Executor와 하네스)만 값이 달라야 한다. 표는 역할마다 system 값을 달리해 component가 같아도 구별되게 했다.

## P12. 식별 게이트

[실측] 회차 r2-r5(r1은 docker events 형식 오류로 빠짐)에서 docker events의 px4 `health_status: healthy`부터 탐침의 `vehicle_status` 첫 수신까지 1.084(범위 0.421 ~ 1.634, n=4) s(벽시계). px4 컨테이너 start부터 첫 수신까지 6.134(범위 5.482 ~ 6.682, n=4) s, start부터 healthy까지 5.049(범위 5.047 ~ 5.062, n=4) s(healthcheck interval 5 s라 그 단위로 끊긴다). 탐침은 xrce-agent 컨테이너가 생긴 직후부터 떠 있었다.
[소스] `vehicle_status.system_id`는 Commander 생성 때 MAV_SYS_ID에서 한 번 읽는다(`Commander.cpp` 721-724행). 프로세스가 살아 있는 동안 바뀌지 않는다.

의견
- 4단계 조건(명령만 막고 setpoint는 막지 않는다, 미수신이면 보류, 불일치면 오류)을 그대로 쓴다. 6단계 절차에서는 PREPARING 1단계가 게이트를 통과한 뒤에만 setpoint를 시작하므로, "setpoint를 막지 않는다"는 실행 중에 게이트가 다시 닫히는 경우(아래)에만 의미가 있다.
- 운용 노드가 bridge 다음에 뜨면(D6) 그때 PX4는 이미 `vehicle_status`를 내고 있다. 그래서 activate 때 첫 수신을 확인하는 것이 시간상 가능하다. 다만 activate에서 PX4를 기다리게 만들면 PX4가 늦게 뜨는 다른 시작 순서에서 실패가 된다.
- 실행 도중 불일치나 재부팅: `system_id`가 바뀌어 보이거나 `vehicle_status.timestamp`가 뒤로 가면(PX4 재시작, hrt가 다시 작게 시작한다[추정]) 같은 PX4와의 연결이 끊긴 것으로 본다. 명령을 멈추고, setpoint도 멈추고, goal은 ABORTED, LINK_LOST로 끝낸다. 재시작한 PX4는 disarm 상태로 뜨므로 공중이었다면 Gazebo에서 떨어진다. SITL에서만 생기는 경우다.
- 충돌 예상(R5, D3): 불일치를 activate 실패로 할지 goal NOT_READY로 할지는 PX4 쪽 사실로는 가르지 못한다. PX4 쪽 사실만 적는다. `system_id`는 설정 오류가 아니면 바뀌지 않으므로 기다려서 풀리는 일이 없다. 미수신은 기다리면 풀린다.

## P13. 실행 중 이상의 판정

[실측] 각 사례에서 `vehicle_status`가 보인 것(5회씩)

| 사례 | `nav_state` | `nav_state_user_intention` | `failsafe` |
| --- | --- | --- | --- |
| Offboard 손실 failsafe(setpoint 끊음) | 18 | 14(그대로) | 참 |
| 다른 source(255, 190)의 DO_SET_MODE(Hold). QGC가 MAVLink로 보내는 것과 같은 Commander 경로(`mavlink_receiver.cpp` 498, 543행이 `from_external` 참으로 같은 uORB 토픽에 낸다) | 4 | 4 | 거짓 |
| Executor 자신의 Hold | 4 | 4 | 거짓 |
| failsafe 중 사용자 Hold(takeover) | 4 | 4 | 거짓, `failsafe_and_user_took_over`도 거짓 |

QGC 자체로는 실험하지 못했다(이 호스트에서 QGC를 띄우지 않았다. 다른 담당자와 스택이 겹치는 것을 피했다). 위 둘째 줄이 같은 경로를 DDS로 흉내 낸 것이다. 외부 명령의 ack는 같은 `vehicle_command_ack` 토픽에 target (255, 190)으로 보이지만 MAVLink로 온 명령도 그런지는 확인하지 않았다[추정: 같은 uORB ack가 DDS로 나가므로 보일 것이다].
[실측] `vehicle_status` 수신 간격(ROS 쪽, 회차마다 a 비행 전체): 최대 0.508(범위 0.508 ~ 0.516, n=5) s(ROS 시각), 0.516(범위 0.514 ~ 0.695, n=5) s(벽시계). 바뀔 때는 바로, 바뀌지 않으면 약 2 Hz로 나온다.
[소스] `failsafe_flags`는 원인별 flag(`offboard_control_signal_lost`, `local_position_invalid`, `battery_warning` 등)를 담는다. `vehicle_status.failsafe`는 "failsafe 동작 중"이고, `nav_state_user_intention`은 사용자가 고른 모드다(`VehicleStatus.msg` 33, 101-103행).

의견: 세 사유의 판정 조건(Executor가 OFFBOARD를 기대하는 항목 실행 중)
- REASON_FAILSAFE: `vehicle_status.failsafe` 참. 원인은 `failsafe_flags`에서 골라 `detail`에 적는다(`offboard_control_signal_lost` 참이면 Executor 자신의 setpoint 경로 문제).
- REASON_EXTERNAL_MODE_CHANGE: `failsafe` 거짓이고 `nav_state_user_intention`이 기대(14)와 다르며, Executor가 그 변경을 요청하지 않았다(보낸 모드 명령이 없거나 그 명령의 목표와 다르다). 외부 disarm(`arming_state` 1, `latest_disarming_reason`이 4 `command_external`)도 여기에 넣는 것을 권한다.
- REASON_LINK_LOST: `vehicle_status`를 ROS 시각 1.5 s 동안 받지 못함(최대 간격 0.516 s의 약 3배). setpoint가 PX4에 닿지 않는 상황이면 PX4는 1 s 뒤 스스로 Land한다. 1.5 s는 그보다 늦지만 판정이 흔들리지 않는 값이다. Collector 신선도 임계와 Fleet 미수신 타임아웃은 이보다 커야 한다(5단계 ops 조건의 순서).
- 판정 순서: LINK_LOST(정보 없음) -> FAILSAFE -> EXTERNAL_MODE_CHANGE.

---

## 다른 담당자와 부딪칠 것으로 보이는 지점

- ros2(R6, R2): 1절의 "Offboard가 아니면 setpoint 발행 중단"은 setpoint helper나 Executor의 발행 loop가 `nav_state`를 알아야 한다는 뜻이다. helper를 상태 없는 함수로 두면 Executor가 지켜야 할 규칙이 되고, 단위 테스트로 단정해야 한다.
- test(T6, T7): 묵은 timestamp 회귀 판정은 failsafe를 확인한 뒤 setpoint를 멈춰야 teardown(착지, disarm)이 끝난다. 묵음 경계는 0.5 s(정상)와 1.5 s(failsafe)를 권한다.
- architect(쟁점 9): failsafe 중의 취소를 Hold 없이 ABORTED(FAILSAFE)로 하자는 안은 잠정 규칙(Land)과 다르다. "확인되면 setpoint 즉시 중단"도 `.action` 주석의 취소 문장에 들어가야 한다.
- test(T3): 도달 판정을 "N회 연속"보다 "ROS 시각 0.5 s 연속"으로 하자는 안.
- ops(LINK_LOST 임계 순서): Executor 1.5 s < Collector 신선도 < Fleet 미수신.
- logging(D11, L1): SDLOG_MODE 2의 ULog는 이 호스트에서 약 10 MB/분이었다(r1 전 스택 25분에 266 MB). CI artifact에 올리면 크기를 먼저 정해야 한다.
- ros2(R5): P12 불일치 처리.

## 실험하지 못한 것과 이유

- P13 QGC로 모드 변경: QGC를 띄우지 않았다(호스트 자원과 다른 담당자 스택과의 포트 겹침 회피). DDS로 같은 Commander 경로를 흉내 냈다.
- P9 정상 발행 setpoint의 PX4 쪽 나이: ULog에 수신 시각이 없어 직접 재지 못했다. `vehicle_status` 시각 차로 추정했다.
- P11 PX4 내부 명령 ack: 이 비행들에서 나오지 않아 실측 값이 없다. 원문으로만 적었다.
- P12 r1의 healthy 시각: docker events 형식 오류로 r1만 빠졌다(r2-r5, n=4).
- P4 (마): 1회만 했다. 위치 무효를 만드는 방법(`EKF2_GPS_CTRL` 0)이 실행 중 파라미터 변경이라 되돌리려면 스택을 다시 올려야 하고, 남은 시간 안에서 1회로 그쳤다. 결과가 원문(Hold의 위치 요구, Land의 Descend 강등)과 맞아서 반복의 가치가 낮다고 봤다.

---

## 재질문 답(2026-11-11)

측정 조건
- 스택은 px4 하나(k=1)만 올렸다. 시작 전 `docker ps`: idsim 스택 없음. 스택이 아닌 컨테이너 `awesome_ride`(ros-ws 이미지, ros2의 앞선 timer 탐침 r6. CPU 약 13%)가 내내 떠 있었다. 측정 중에 다른 담당자의 단발 컨테이너(`p7_*` 이름의 SIGTERM 실험, 이름 없는 ros-ws 컨테이너 여럿)가 오갔다. 다른 `idsim-N` compose 프로젝트는 없었다.
- load average(1분): 5 s 간격 83표본, 1.39-4.71(4 vCPU). 앞선 의견서의 6-19보다 낮지만 0은 아니다. 시간 값은 모두 PX4 timestamp와 ROS 시각(sim 시간) 축이다.
- 회차마다 스택을 새로 올리고 q2(재질문 2), q1(재질문 1) 순서로 3회. 두 시나리오 모두 앞부분은 같다: 지상 disarm -> setpoint 시작 -> Offboard -> arm -> 5 m 도달 -> 3 s 호버 -> Hold(취소 흉내) -> `nav_state` 4 확인 뒤 setpoint 중단 -> 5 s. 탐침은 scratchpad `probe/probe2.py`, 분석은 `probe/an2.py`, 기록은 `data/rq/r1-r3`.
- q2 종료 코드 139가 2회 있었다. 시나리오 끝(`scenario_end`, `exit` 기록) 뒤 rclpy 종료 중의 segfault이고 기록은 온전하다.

### 1. LAND 항목 실행 중의 취소(Hold)

[실측] 자기 NAV_LAND 하강 중(`nav_state` 18, `failsafe` 거짓) Hold, 각 3회.

| 시점 | ack | 첫 송신 기준 ack, `nav_state` 4 | Hold 시점 land flag | 그 뒤의 z(지면 기준, 위가 +) | 그 뒤의 land flag |
| --- | --- | --- | --- | --- | --- |
| (가) 높이 2.49 m 통과 | 3/3 ACCEPTED, 1회 송신 | 12-20 ms, 20-24 ms | 모두 거짓 | 5 s 동안 2.21-2.48 m, 5 s 뒤 2.42-2.44 m. 정지까지 0.26-0.28 m 더 내려갔다가 돌아온다 | 모두 거짓. arm 유지 |
| (나) `ground_contact` 참, `landed` 거짓 | 3/3 ACCEPTED, 1회 송신 | 16-20 ms, 24-28 ms | `ground_contact` 참 | 10 s 동안 -0.05-+0.08 m(지면) | 0.33-0.35 s에 `maybe_landed`, 0.67-0.69 s에 `landed` 참, 1.47-1.49 s에 셋 다 거짓으로 돌아감. 10 s 동안 자동 disarm 없음, `nav_state` 4, armed |

- (가)의 뒤에 다시 NAV_LAND를 보내면 정상 착지와 자동 disarm(3/3). (나)의 뒤에 NAV_LAND를 보내면 `landed`까지 1.42 s, disarm까지 3.43 s(3/3, `latest_disarming_reason` 6).
- [소스] `MulticopterLandDetector.cpp` `_get_ground_contact_state()`: `maybe_landed`와 `landed`가 서기 전까지 `ground_contact`는 "setpoint의 하강 속도가 `LNDMC_Z_VEL_MAX`의 1.1배 이상"(`_in_descend`)을 요구한다. Hold는 하강 속도를 내지 않는다. (나)에서 `landed`가 섰다가 풀린 정확한 경로(Hold의 setpoint가 착지 상태를 다시 깨는 것인지)는 ULog의 추력 setpoint를 보지 않아 확인하지 않았다[추정].
- 결론: (가) 공중에서는 Hold가 결정적으로 된다(하강 멈춤, 0.3 m 안의 처짐). (나) 지면 근처에서는 Hold가 "지면 위 armed Hold"로 끝나고 자동 disarm이 오지 않는다. 결정 (r)(강제 disarm 금지)과 앞선 `COM_DISARM_PRFLT`의 우려와 같은 종류의 끝 상태다.

의견(분기)
- LAND 항목 실행 중 취소: `vehicle_land_detected`가 신선하고 `ground_contact`, `maybe_landed`, `landed`가 모두 거짓이면 Hold를 보낸다. 확인되면 CANCELED, NONE(계약의 "공중이면 Hold" 그대로).
- 셋 중 하나라도 참이면 Hold를 보내지 않고 Land를 끝까지 둔다. disarm 확인 뒤 CANCELED, NONE. 착지 판정과 disarm 처리는 LAND 항목의 규칙(`landed` 뒤 5 s, 비강제 disarm, ITEM_TIMEOUT)을 그대로 쓴다. 이유: 이 구간의 Hold는 기체를 멈추는 게 아니라 착지를 무효로 만든다.
- 경합 보호: 판정과 Hold 도착 사이 약 20-30 ms에 `ground_contact`가 설 수 있다. Hold 확인 뒤 ROS 시각 2 s 안에 셋 중 하나가 참이 되면 NAV_LAND를 다시 보내고 위의 "Land를 끝까지" 경로로 간다. 결과는 같이 CANCELED, NONE.
- 높이(z) 문턱으로 가르지 않는다. 지면 높이는 기준점의 drift(60 s에 최대 0.28 m)만큼 틀리고, land detector가 PX4 자신의 판정이다.
- 단위 테스트 대상: 세 flag 조합과 경합 보호의 전이.

### 2. Hold 상태 공중 기체에 [LAND] 하나짜리 미션

[실측] 취소로 Hold가 되고 setpoint가 끊긴 뒤 5 s(3/3)의 상태: `nav_state` 4, `arming_state` 2, `failsafe` 거짓, `pre_flight_checks_pass` 참, `xy_valid`, `z_valid` 참, `landed` 거짓, `failsafe_flags.offboard_control_signal_lost` 참.
[실측] 그 상태에서 NAV_LAND(setpoint 없음, Offboard 없음): 3/3 첫 송신 ACCEPTED, ack 8-12 ms, `nav_state` 18까지 20-24 ms, 5 m에서 `landed`까지 9.15-9.23 s, disarm까지 11.16-11.24 s(`landed` 뒤 약 2.0 s, `latest_disarming_reason` 6). 실패와 재송신 없음.

의견(첫 항목이 TAKEOFF가 아닌 미션의 PREPARING)
- 1(식별 대조), 2(준비 확인: 상태 셋 신선, `pre_flight_checks_pass`, `xy_valid`, `z_valid` 참, `failsafe` 거짓)는 그대로 쓴다. Hold의 공중 기체에서 모두 참이었다(3/3).
- 3(시작 조건): LAND는 `arming_state` 2이고 `landed` 거짓이며 `nav_state` 4다. 아니면 PRECONDITION_FAILED. `nav_state` 4로 묶는 이유: 14(Offboard)이면 다른 누군가 setpoint를 내고 있는 것이고, setpoint가 계속 들어오면 착지 판정이 서지 않는다(1절 [실측] 5/5). 지상에서 `[LAND]`가 오는 경우(`landed` 참)는 실측하지 않았고 PRECONDITION_FAILED를 권한다.
- 4-8(기준점, setpoint 시작, 신호 유효, Offboard 전환, arm)은 모두 건너뛴다. 특히 6은 반드시 건너뛴다. Hold에서는 `offboard_control_signal_lost`가 참(3/3)이라 6을 돌리면 MODE_SWITCH_FAILED로 잘못 끝난다.
- 건너뛰는 조건은 "첫 항목이 모드 명령 항목(LAND)"이다. 1a의 미션에서 이 경우는 `[LAND]` 하나뿐이다. 상태로 고르지 않고 항목 분류(C19)로 고르면 단위 테스트에서 결정적이다.
- EXECUTING에서는 NAV_LAND를 보내고 LAND 항목 규칙(2 s 안에 ack ACCEPTED 또는 `nav_state` 18, 완료는 disarm 연속 확인)을 그대로 쓴다. setpoint는 goal 내내 내지 않는다(2번 결정의 발행 규칙과 맞는다).

## 추가 실험 답(E1-E5)

작성 2026-11-11, px4-engineer. 대상: `decisions.md` "추가 실험" 절. 저장소의 다른 파일은 고치지 않았다.

측정 조건
- 스택은 px4 하나(k=1)만 올렸다. 시작 전 `docker ps -a`는 비어 있었고, 측정 중 떠 있던 컨테이너는 `idsim-1-*` 넷과 탐침 컨테이너(`px4exp_e_*`)뿐이었다(5 s 간격 313표본). load average(1분) 0.54-5.80, 중앙값 3.73(4 vCPU, 7GB).
- 회차마다 스택을 새로 올렸다. 본 측정 s1-s3은 같은 계획(E1 4, E3 8, E4 6, E5 1회. 종류를 섞은 순서), s4는 E5 2회, s5는 E3 보충 12회. 스택마다 처음에 2 m 이륙과 착륙 1회로 지면 z를 잡았다. 모든 회차는 지상 disarm에서 시작해 지상 disarm으로 끝나고 끝의 z를 다음 회차의 송신 기준 지면 z로 쓴다. 표의 높이는 그 회차 자신의 "착지하고 disarm한 뒤의 z" 기준이다. arm 직전 z와의 차는 -0.054-+0.049 m였다.
- 탐침은 `probe/probe3.py`(probe2.py의 Probe 사용), 명령 source 251/1, `from_external` 참. Hold, disarm은 1회만 보낸다(재송신 없음). 그 밖의 명령은 0.5 s 재송신이고 모두 첫 송신에 ACCEPTED였다. setpoint는 PREPARING 순서대로 기준점 -> Offboard -> arm, arm 확인(ack와 `arming_state` 2 수신) 뒤 목표를 5 m 위로 바꾼다. 시각은 ROS 시각(sim 시간) 축이고 "arm 뒤 T s"는 탐침의 arm 확인 시각 기준이다. arm 확인은 PX4 `vehicle_status`의 arm 시각보다 0-200 ms 늦다(전이 메시지 수신 지연. 재질문의 미해결 항목과 같은 현상).
- `nav_state` 전이 시각은 탐침이 `vehicle_status`를 받은 시각이라 20-208 ms로 퍼진다. ack는 모두 8-24 ms.
- 배터리 문제(아래 "따로 알릴 것")로 첫 시도의 결과(o1)는 앞 8회까지만 참고로 보고 세지 않았다. 본 측정은 배터리 감시 스크립트를 함께 돌렸다.
- 원자료: scratchpad `data/ex/s1-s5/p.jsonl`, 회차별 표 `data/ex/rows_all.jsonl`(`probe/an3.py`), 요약 `data/ex/summary.txt`(`probe/sum3.py`), load `data/ex/load.txt`, 배터리 감시 `data/ex/s*/wd.log`. ULog는 `artifacts/runs/20261110-180933-k1`, `-181618-k1`, `-182302-k1`, `-182946-k1`, `-183237-k1`의 `px4-1/log/`(gitignore 경로. 지우기 전에 옮길 것). ULog 읽기는 `probe/ulog_ld.py`.

끝 상태 분류는 절의 정의를 글자 그대로 적용했다. (iii)은 둘로 나눠 적는다. iii-rest: 10 s 끝에도 지면 0.05 m 안. iii-touch: 지면 0.05 m 안까지 내려갔다가 10 s 끝에는 다시 0.05 m 위에 떠 있음.

### E1. NAV_LAND 하강 중 Hold(송신 시점 세 신호 모두 거짓 12/12)

[실측] 높이마다 3회, 합 12회. 송신 시점 vz 하강 0.70-0.72 m/s, `nav_state` 18, `failsafe` 거짓. Hold ack 12/12 ACCEPTED(12-24 ms).

| 목표 높이 | 송신 시점 높이 | 10 s 동안 높이 최소 | 10 s 뒤 높이 | 분류 |
| --- | --- | --- | --- | --- |
| 0.5 m | 0.49-0.54 m | 0.23-0.28 m | 0.46-0.52 m | (i) 3/3 |
| 0.3 m | 0.29-0.34 m | 0.015-0.078 m | 0.26-0.31 m | (i) 1/3, iii-touch 2/3 |
| 0.2 m | 0.14-0.21 m | -0.11 - -0.05 m | 0.10-0.19 m | iii-touch 3/3 |
| 0.1 m | 0.04-0.14 m | -0.10 - -0.02 m | 0.03-0.12 m | iii-rest 2/3, iii-touch 1/3 |

- Hold 뒤 더 내려간 깊이는 0.26-0.29 m(0.5 m, 0.3 m. 재질문의 2.49 m에서 0.26-0.28 m와 같다). 그보다 낮으면 지면에 닿는다.
- 12회 모두 10 s 동안 세 신호가 한 번도 서지 않았다. (ii)는 0회, 송신 시점에 신호가 이미 서 있던 회차도 0회다.
- `offboard_control_signal_lost`는 Hold 뒤 0.13-0.46 s에 참(12/12. setpoint는 Land 확인 때 이미 멈춤).
- 회복 NAV_LAND: 12/12 첫 송신 ACCEPTED, `landed`까지 1.45-2.42 s, disarm까지 3.46-4.43 s(`latest_disarming_reason` 6).
- [실측, ULog] 경로. 0.2 m 회차(s1 T08): Hold 뒤 추력 setpoint z는 -0.72 - -0.82(호버 추정 0.73)로 낮아지지 않았고 `has_low_throttle` 거짓, `in_descend`는 Hold 뒤 0.5 s 안에 거짓이 됐다. 위치 setpoint는 지면 아래로 0.1 m 들어갔다가 Hold 위치 쪽으로 천천히 올라가 기체가 지면에 닿은 뒤 다시 떴다(iii-touch). 0.1 m 회차(s1 T12): 같은 경로로 기체가 지면 위에 호버 근처 추력(0.67-0.70)으로 앉아 있다(iii-rest). [소스] `MulticopterLandDetector.cpp` `_get_ground_contact_state()`는 낮은 추력과 하강 setpoint를 요구하므로 Hold에서 `ground_contact`가 서지 않는 것과 맞는다.

### E2. 관찰 창 안의 Land 재송신

- E1의 (ii) 회차가 0회라 E2는 해당 회차가 없다. 재송신부터 `landed`, disarm까지의 시간은 재지 못했다(대신 10 s 뒤 회복 NAV_LAND의 값은 E1에 적었다).
- 세 신호가 모두 거짓인 상태에서 시작한 Hold는 E1, E3 (가), E4 (가), 보충을 합쳐 33회 중 어느 회차에서도 10 s 안에 신호가 서지 않았다. 관찰 창(2 s든 10 s든)은 "지면 위 armed Hold"를 한 번도 잡지 못했다.

### E3. Offboard TAKEOFF setpoint 중 Hold와 NAV_LAND

[실측] 시점과 변형마다 3회, 합 24회. 1.6-2.5 s의 모든 회차에서 기체는 아직 지면 위였다(송신 시점 높이 -0.03-+0.03 m). 같은 스택들의 E1 이륙에서 지면 0.05 m를 넘은 것은 arm 확인 뒤 3.10-3.40 s(12회)였다.

| arm 뒤 | 송신 시점 세 신호 | (가) Hold의 끝 상태 | (나) NAV_LAND: `landed`, disarm |
| --- | --- | --- | --- |
| 1.6 s | 모두 참 3/3(두 변형 모두) | 셋 다 Hold 뒤 0.016-0.064 s에 거짓이 되고 10 s 동안 거짓, 높이 -0.02-+0.02 m, armed. 지면 위 armed Hold 3/3 | 1.49 s, 3.49-3.50 s, 실패 0/3 |
| 1.8 s | 모두 거짓 3/3 | iii-rest 3/3 | 1.46-1.48 s, 3.47-3.48 s, 실패 0/3 |
| 2.0 s | 모두 거짓 3/3 | iii-rest 3/3 | 1.46-1.47 s, 3.47-3.48 s, 실패 0/3 |
| 2.5 s | 모두 거짓 3/3 | iii-rest 2/3, iii-touch 1/3(최대 0.089 m) | 1.48-1.51 s, 3.50-3.53 s, 실패 0/3 |

- (가) Hold ack 12/12 ACCEPTED(8-16 ms), `nav_state` 4 수신 20-64 ms. 12회 모두 송신 뒤 10 s 동안 거짓에서 참으로 선 신호가 없다.
- (나) ack 8-20 ms, `nav_state` 18 수신 20-64 ms. 지면 위 "모두 거짓"에서 시작한 9회는 `ground_contact` 0.78-0.84 s, `maybe_landed` 1.12-1.18 s, `landed` 1.46-1.51 s 순으로 섰다.
- 이륙 중 신호가 내려가는 순서와 시각: `landed`와 `maybe_landed`는 같은 표본에서 거짓이 되고(42/42) `ground_contact`는 같은 표본 또는 4-16 ms 뒤에 거짓이 된다. arm 확인 뒤 1.596-1.812 s(42회, E3과 E4). 그때 기체는 아직 지면 위다(높이 변화 0.03 m 안).
- 1.6 s의 Hold에서 신호가 곧 내려간 것은 Hold 때문이 아니라 자연히 내려가는 시각(1.6 s 부근)과 겹친 것으로 본다. ULog(s1 T01)에서 내려간 시각이 같은 스택의 다른 회차와 같았다[실측 1회, 해석은 추정].
- [실측, ULog] 지면 위 Hold의 경로(s1 T05, 1.8 s): Hold 뒤 위치 setpoint z가 현재 지면 위치로 바뀌고 추력 z는 -0.40 근처(호버 추정 약 0.73보다 낮음)에 머문다. `in_descend` 거짓이라 `ground_contact`가 다시 서지 않는다. 10 s 뒤 NAV_LAND를 보내면 1.41-1.44 s에 `landed`, 3.42-3.45 s에 disarm(12/12, 1.6-2.5 s).
- 보충(s5, 절 밖의 시점): 실제로 뜬 뒤의 Hold. arm 뒤 3.6 s(높이 0.25-0.30 m, 상승 1.0 m/s)는 0.69-0.71 m까지 올라갔다가 0.27-0.30 m에 선다. (i) 3/3. 4.0 s(높이 0.90-0.93 m)는 (i) 3/3, 10 s 뒤 0.96-1.03 m. 같은 시점의 NAV_LAND는 6/6 정상 착지와 disarm(3.6 s: `landed` 4.24-4.38 s, 4.0 s: 7.17-7.40 s).

### E4. arm 뒤 1.75-1.9 s 비강제 disarm

[실측] 시점 1.75, 1.85, 1.9 s, 변형마다 스택 셋에서 1회씩, 합 18회.
- 1.75 s: 송신 시점 세 신호 모두 참(6/6), ACCEPTED 6/6, ack와 `arming_state` 1 12-16 ms. disarm 뒤 `nav_state` 14.
- 1.85, 1.9 s: 세 신호 모두 거짓(12/12), TEMPORARILY_REJECTED 12/12(변형마다 6회), ack 8-24 ms. PX4 로그 "Disarming denied: not landed". 거부된 회차는 모두 송신 시점에 세 신호가 거짓이었다. 그래서 거부 뒤 "하나라도 참" 줄로 가는 경우는 나오지 않았다.
- (가) setpoint 유지: 거부 뒤 `nav_state` 14, `failsafe` 거짓, `offboard_control_signal_lost` 거짓으로 Offboard가 유지됐다(6/6). 세 신호가 거짓이라 표대로 Hold를 보냈고 6/6 ACCEPTED, `nav_state` 4 수신 184-200 ms. 끝 상태는 iii-rest 6/6(지면 위 armed, Hold, 10 s 동안 세 신호 거짓). 회복 NAV_LAND는 `landed` 1.42-1.44 s, disarm 3.43-3.45 s(6/6).
- (나) setpoint 중단: `offboard_control_signal_lost` 참 1.02-1.06 s, `nav_state` 18과 `failsafe` 참 1.03-1.23 s, `landed` 2.55-2.72 s, 자동 disarm 4.57-4.74 s(`latest_disarming_reason` 6). 끝 상태는 지상 disarm 6/6이지만 failsafe를 거친다.

### E5. 지상 Offboard arm 직후 setpoint 유지한 채 disarm

[실측] arm 확인 직후 4회(s1-s3, s4), arm 확인 0.3 s 뒤 1회(s4). 송신 시점 세 신호 모두 참.
- 5/5 ACCEPTED, ack 0-20 ms. `arming_state` 1 수신은 송신 뒤 164-184 ms(arm 직후 회차. PX4 timestamp로 armed였던 시간은 24 ms라 수신 지연이다), 0.3 s 회차는 12 ms.
- disarm 뒤 `nav_state` 14(5/5). setpoint를 멈춘 뒤 5 s 동안 `failsafe` 거짓, `nav_state` 14, `arming_state` 1(5/5). `offboard_control_signal_lost`는 0.04-0.46 s에 참이 되지만 disarm 상태라 failsafe 동작이 없다.

### 결과의 처리 중 해당하는 쪽

- E1, E3 (가): 두 번째 줄에 해당한다. (iii)이 나왔다. E1에서 0.3 m 이하 9회 중 8회, E3 (가)에서 1.8-2.5 s 9회 전부(1.6 s의 3회도 같은 끝 상태). 신호가 늦게 선 것이 아니라 아예 서지 않았다(33회 중 0회). 따라서 K5는 지금 문장("지상 disarm이거나 armed, Hold 모드")으로 확정하고, 분기는 px4, ops와 다시 정해야 한다.
- 다시 정할 때 px4 쪽 사실 둘.
  1. 기본안 "자기 Land 하강 중의 취소는 Hold를 보내지 않고 항상 착륙을 끝낸다"는 E1 결과로 받쳐진다. NAV_LAND는 어느 높이에서든 착지와 disarm으로 끝났다(Hold 뒤 회복 NAV_LAND 36/36: E1 12, E3 (가) 18(보충 포함), E4 (가) 6. Offboard 중 NAV_LAND 18/18: E3 (나) 12, 보충 6).
  2. 같은 문제가 TAKEOFF 항목의 이륙 전 구간에도 있다. arm 뒤 약 1.6 s(`landed`가 거짓이 되는 때)부터 실제로 뜨는 약 3.1-3.4 s까지는 기체가 지면 위인데 세 신호가 모두 거짓이라, 지금 표로는 Hold 줄로 가고 "지면 위 armed Hold"가 된다(E3 (가) 9/9, E4 (가) 6/6). 기본안은 자기 Land만 다루므로 이 구간이 남는다. 높이 임계를 쓰지 않는다면 px4의 의견은 "TAKEOFF 항목 실행 중의 취소도 NAV_LAND로 끝낸다"를 함께 올리는 것이다. 뜬 뒤(0.25 m 이상)의 Hold는 (i)이었지만(6/6) 그 경계를 신호로 가를 수 없다. 이것은 정책 변경이라 사용자 5에 함께 올린다[의견].
- 관찰 창 2 s: 재정할 근거가 생기지 않았다. 창이 잡은 회차가 0이므로 창은 "지면 위 armed Hold"를 막는 수단이 되지 못한다. 기본안이 채택되면 창은 Hold를 남기는 경로(위 분기에서 Hold가 살아남는 곳)에만 남는다.
- E4: (가)에서 Offboard가 유지되고(6/6) 이어 보낸 명령(Hold)도 표대로 받아들여졌다. K3의 "setpoint를 유지한 채 비강제 disarm, 거부되면 다시 보내지 않고 세 신호로 고른다"는 확정할 수 있다. 다만 거부되는 때는 항상 세 신호가 거짓이라 그 뒤가 Hold 줄이 되고 끝은 (iii)이다(6/6). 그러므로 거부 뒤의 줄도 위의 재정에 포함된다. (나)는 옛 규칙을 버린 근거다. 거부 뒤 1.0-1.2 s에 Offboard 손실 failsafe(`failsafe` 참, Land)로 간다(6/6).
- E5: 거부 0/5. PREPARING 실패 경로의 "비강제 disarm까지 하고 끝낸다"는 그대로 둔다. setpoint를 disarm 확인까지 유지하고 그 뒤 멈춰도 failsafe가 없다(5/5).

### 따로 알릴 것: SITL 배터리 시뮬레이터의 발행 정지

[실측] 측정 중 PX4 안의 `battery_status` 발행이 멈추는 일이 생겼다. 시험과 본 측정을 합쳐 7회(시험 스택 t0, t1에서 각 1회, 첫 시도 o1에서 1회, 본 측정 s1에서 1회, s3에서 3회(1회는 탐침이 끝난 뒤)). 앞선 의견서의 r1-r5와 재질문 r1-r3에서는 0회였다.
- 증상: ULog와 `listener battery_status`의 마지막 timestamp가 멈춘다. `battery_simulator status`는 running이고 `work_queue status`의 rate도 보이지만 perf의 cycle 수가 늘지 않는다(t1에서 3 s 간격 두 번 19650으로 같음, `system_power_simulator`도 같음). `gyro_fft`처럼 같은 hp_default에서 topic으로 깨는 항목은 계속 돈다. 5 s 뒤 `failsafe_flags.battery_unhealthy`가 참이 되고 "Preflight Fail: Battery unhealthy", arm 거부("Arming denied: Resolve system health failures first")가 된다. arm 직후(COM_SPOOLUP_TIME 안)에 참이 되면 "Disarmed by failsafe"(`latest_disarming_reason` 14)로 끊긴다(t0, o1에서 각 1회).
- [소스] `batteryCheck.cpp`: 배터리 발행이 5 s보다 오래되면 `battery_unhealthy`. `failsafe.cpp` 571행: spoolup 안이면 Disarm, 밖이면 Warn.
- 조건: 몇 초 전에 arm-disarm이 있었다는 것 말고는 공통점을 찾지 못했다. E5(arm 24 ms 뒤 disarm) 뒤 수 초 안에 3회 났지만 E5 뒤에 나지 않은 것도 6회이고, E5 없이 난 것도 4회다. 원인은 SITL의 hrt 주기 호출(`ScheduleOnInterval`)이 멈추는 것으로 보이나 확인하지 않았다[추정]. 재질문 미해결의 "hrt가 멈춘 px4의 종료"와 같은 계열인지도 모른다.
- 회복: PX4 셸의 `battery_simulator stop`, `start`로 발행이 돌아왔다(3/3). 본 측정은 1 s 간격 감시로 이것을 자동으로 했고, 발행 공백은 탐침 기준 8.0-8.2 s였다. 공백이 겹친 회차(s3 T01 E3 1.6 s (가), s3 T14 E3 2.5 s (나), s1 T18 E5)는 그동안 `pre_flight_checks_pass`가 거짓이 됐지만 `failsafe`는 거짓이었고 결과가 같은 조건의 다른 회차와 같아 그대로 셌다. 파라미터와 PX4 소스는 바꾸지 않았다.
- 영향: `sitl` 계층의 반복 비행에서 NOT_READY 또는 ARM_REJECTED로 나오는 플래키 원인이 된다. test(판정 시 `battery_unhealthy`를 원인으로 따로 적기), devops(재현 시 장애 분석)에 알린다. 회차마다 스택을 새로 올리면 영향이 그 회차에 그친다.
