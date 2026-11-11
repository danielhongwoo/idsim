# 1a 6단계 의견서: px4-engineer

2026-11-11. 이륙-호버-착륙 노드(`idsim_mission`)와 통합 테스트의 PX4 인터페이스 부분. 구현은 하지 않았다.

근거 표기.

- [소스]: PX4 v1.17.0 태그 원문(raw.githubusercontent.com/PX4/PX4-Autopilot/v1.17.0/...에서 받은 파일). 파일과 행을 함께 적는다.
- [실측]: 아래 "실측 기록"의 실행. 스택 5에서 했고 횟수를 적는다.
- [추정]: 원문이나 실측이 없는 판단.

## 요약 (권고)

1. Offboard 진입 순서는 "EKF gate -> 20 Hz 발행 시작 -> 10개 이상 발행과 `failsafe_flags.offboard_control_signal_lost == false` -> DO_SET_MODE(Offboard) -> `nav_state == OFFBOARD` 3회 연속 -> arm -> `arming_state == ARMED` 3회 연속"이다. Offboard 먼저, arm 나중. [실측 4회]
2. EKF 수렴 판정은 `vehicle_local_position.xy_valid`가 아니라 `failsafe_flags`의 `local_position_invalid`, `local_altitude_invalid`, `global_position_invalid`, `home_position_invalid`가 모두 false인 것으로 한다. Commander가 실제로 쓰는 판정이다. [소스]
3. 새로 찾은 규칙: nav_state가 OFFBOARD가 아니면 `trajectory_setpoint`를 발행하지 않는다. `/fmu/in/trajectory_setpoint`는 PX4 안에서 FlightModeManager와 같은 uORB 토픽이라 Land와 Hold의 setpoint와 섞인다. 착륙 중에 발행을 계속하면 착지 뒤 60-90 s 동안 landed가 나오지 않았다. 멈추면 약 1 s 만에 나왔다. [소스, 실측 2회 대 2회]
4. 또 하나: offboard 손실 failsafe(Land) 중에 발행을 다시 시작하면 PX4가 모드 명령 없이 OFFBOARD로 돌아간다. 그래서 Executor가 failsafe를 감지하면 즉시 발행을 멈추고 ABORTED, FAILSAFE로 끝낸다. [소스, 실측 1회]
5. Hold 실험 결과: offboard 손실 failsafe 진행 중에도, NAV_LAND 착륙 중에도 Hold 명령은 ACCEPTED이고 첫 `vehicle_status`에서 AUTO_LOITER가 된다(`failsafe`는 false로 바뀐다). 5단계의 잠정 규칙("failsafe 중 취소는 Hold 확인 실패와 같은 경로")은 없애고 항상 Hold를 시도해 확인 결과로 가르기를 권한다. Hold 확인 타임아웃 기본값은 3.0 s(ROS 시각). [실측 각 1회, 소스]
6. TAKEOFF는 계약대로 Offboard position setpoint로 한다. LAND는 NAV_LAND이고, 완료는 `arming_state == DISARMED` 3회 연속(착륙 판정 뒤 자동 disarm)이다. 5 m 기준 실측: arm부터 고도 도달까지 6.2-7.6 s, NAV_LAND부터 disarm까지 10.9-11.1 s. [실측]
7. 넘김 4건은 모두 이 단계에서 닫을 수 있다. (4)는 이번 실측으로 닫혔다(시동 해제 상태의 신호 없는 Offboard 요청은 TEMPORARILY_REJECTED가 아니라 ACCEPTED이고 nav_state가 바로 OFFBOARD가 된다. 그 상태의 arm이 TEMPORARILY_REJECTED다).
8. SITL 파라미터는 바꾸지 않는다.

## 1. Offboard 진입 절차

### 1.1 시퀀스 (PHASE_PREPARING)

| 단계 | 동작 | 통과 조건 | 실패 시 |
| --- | --- | --- | --- |
| P0 | 식별 대조와 수신 확인 | `vehicle_status` 수신, `system_id` 대조 일치, `failsafe_flags`, `vehicle_local_position`, `vehicle_land_detected` 수신, `Px4Timestamp::now()` 성공(`/clock` 활성) | NOT_READY |
| P1 | 시작 조건 | 첫 항목이 TAKEOFF이고 `vehicle_land_detected.landed == true` | PRECONDITION_FAILED |
| P2 | EKF gate | `failsafe_flags`의 `local_position_invalid`, `local_altitude_invalid`, `global_position_invalid`, `home_position_invalid`가 모두 false | `ekf_ready_timeout`(기본 30 s) 넘으면 NOT_READY |
| P3 | 발행 시작 | 20 Hz로 `offboard_control_mode`(position만 true)와 `trajectory_setpoint`(TAKEOFF 목표점) | - |
| P4 | 신호 확인 | 발행 10개 이상 그리고 `failsafe_flags.offboard_control_signal_lost == false` | 2 s 넘으면 MODE_SWITCH_FAILED |
| P5 | 모드 전환 | DO_SET_MODE(1, 6). 0.5 s마다 재전송하며 `is_ack_for`가 맞는 ack를 기다린다. ack가 ACCEPTED가 아니면 실패. 그 뒤 `nav_state == 14(OFFBOARD)` 3회 연속 | `mode_confirm_timeout`(기본 3 s) 넘으면 MODE_SWITCH_FAILED |
| P6 | arm | ARM_DISARM(1). 재전송하며 ack 대기. TEMPORARILY_REJECTED는 `arm_timeout` 안에서 재시도. 그 뒤 `arming_state == 2(ARMED)` 3회 연속이고 nav_state가 여전히 OFFBOARD | `arm_timeout`(기본 5 s) 넘으면 ARM_REJECTED |

P6의 ARMED 확인 시점이 TAKEOFF 항목의 시작이다(항목 `timeout`이 여기서 흐르기 시작한다).

PREPARING 실패 정리: 발행을 멈춘다. arm된 채 지상이면 강제가 아닌 disarm을 보내고 확인한다(`COM_DISARM_PRFLT=-1`이라 PX4가 스스로 내리지 않는다).

### 1.2 근거

- Offboard 먼저인 이유. [소스] `UserModeIntention.cpp` 53-60행: 시동 해제 상태에서는 모드 변경이 항상 허용된다. arm 때 `modeCheck.cpp` 144-152행이 "현재 모드(Offboard)에 신호가 없으면 arm 거부"를 하므로, arm이 받아들여졌다는 것은 Offboard가 돌 수 있다는 뜻이다. arm을 먼저 하면 Hold에서 arm된 기체가 Offboard 전환 실패 시 지상에 arm된 채 남는다. PX4 공식 예제(https://docs.px4.io/main/en/ros2/offboard_control.html)도 모드 명령 뒤 arm이다. [실측] 4회 모두 이 순서로 통과.
- 왜 `xy_valid`가 아닌가. [소스] `estimatorCheck.cpp` 664-743행, 796-821행: Commander의 `local_position_invalid`는 `xy_valid`에 더해 `eph < COM_POS_FS_EPH`(기본 5 m), 1 s 유예, 시동 전 innovation 검사를 거친다. Offboard 신호 판정도 이 플래그를 쓴다(`offboardCheck.cpp`: position 모드면 `local_position_invalid`가 참일 때 신호 없음). `global_position_invalid`와 `home_position_invalid`를 함께 보는 이유는 취소 때 쓸 Hold가 global과 local 위치를 요구하기 때문이다(`mode_requirements.cpp` 110-123행). roadmap 리스크 표의 "`vehicle_local_position.xy_valid` 대기"는 이 표현으로 바꾸기를 권한다(architect).
- `pre_flight_checks_pass`를 gate로 쓰지 않는 이유. [소스] Commander가 "현재 nav_state로 arm할 수 있는가"로 계산한다. [실측] 착륙과 자동 disarm 뒤 nav_state가 OFFBOARD로 돌아가고(사용자 의도가 Offboard였기 때문. `UserModeIntention.cpp`의 `_nav_state_after_disarming`) 신호가 없으니 `pre_flight_checks_pass`가 false로 남는다. 다음 goal에서 이 값을 P2에 쓰면 늘 NOT_READY가 된다. 이 값은 P5 뒤에야 의미가 있고 P6의 arm 결과가 같은 정보를 준다.
- 10회 규칙. [실측] 첫 setpoint 뒤 12-24 ms에 `offboard_control_signal_lost`가 false가 됐다. 10회(0.5 s)는 PX4가 요구하는 값이 아니라 DDS 연결이 맺어지기 전의 손실을 흡수하는 여유다. 그래서 횟수와 플래그를 함께 본다.
- 3회 연속. [소스] `dds_topics.yaml`: `vehicle_status`는 rate_limit 5 Hz, Commander는 변경 시와 최소 500 ms마다 발행한다. 3회 연속은 0.4-1.0 s다. [실측] Offboard 확인 1.02 s, ARMED 확인 1.5 s.
- ack는 성공이 아니다. [실측] 시동 해제 상태의 신호 없는 Offboard 요청이 ACCEPTED였다. 그래서 성공 판정은 늘 `nav_state`와 `arming_state`로 한다(`vehicle_command.hpp` 머리 주석과 같다).
- 명령 재전송. [소스] `uxrce_dds_client/utilities.hpp`: /fmu/in 리더는 BEST_EFFORT다. 손실될 수 있으니 ack가 올 때까지 0.5 s마다 다시 보낸다. arm, 모드 명령은 같은 것을 여러 번 받아도 결과가 같다.

### 1.3 비행 중 감시 (setpoint 항목 실행 중)

`vehicle_status` 한 번이라도 다음이면 반응한다. 들어가는 확인은 3회 연속이지만 벗어남은 1회로 반응한다(PX4가 바뀔 때 바로 발행하고, 늦게 반응할수록 setpoint가 다른 모드와 섞인다).

| 관측 | 분류 | 동작 |
| --- | --- | --- |
| `nav_state != OFFBOARD`이고 `failsafe == true` | REASON_FAILSAFE | 발행 즉시 중단, ABORTED |
| `nav_state != OFFBOARD`이고 `failsafe == false`이고 `nav_state_user_intention != OFFBOARD` | REASON_EXTERNAL_MODE_CHANGE | 발행 즉시 중단, ABORTED |
| 공중에서 `arming_state == DISARMED` | REASON_FAILSAFE | ABORTED |
| `vehicle_status`가 `link_timeout`(기본 2 s, ROS 시각) 동안 없음 | REASON_LINK_LOST | 발행 중단, ABORTED |

[실측] offboard 손실 failsafe에서 `nav_state=18, nav_state_user_intention=14, failsafe=true`가 나왔다. 사용자 의도가 OFFBOARD로 남으므로 두 경우를 `nav_state_user_intention`으로 가를 수 있다.

LINK_LOST에서 발행을 멈추는 이유: 상태가 안 오는 것은 DDS 경로 문제일 가능성이 크고, 발행을 멈추면 PX4 쪽에서 `COM_OBL_RC_ACT=4`(Land)로 결정적으로 끝난다.

## 2. 이륙, 호버, 착륙

### 2.1 TAKEOFF: Offboard position setpoint (5단계 계약대로)

- 목표점: 항목 시작 위치(P3에서 읽은 `vehicle_local_position`의 x, y, z)에서 z만 `-height_m`. yaw는 `MODE_KEEP`이면 그때의 `heading`, `MODE_FIXED`면 ENU -> NED 변환값. yaw는 항상 유한값으로 보낸다(NaN yaw의 Offboard 동작은 [추정]으로 남기고 쓰지 않는다).
- 지상 setpoint를 먼저 보내지 않고 처음부터 목표점을 보낸다. [소스] `MulticopterPositionControl.cpp` 466-472행: Offboard에서 arm 상태이고 setpoint z가 현재 z보다 위면 바로 이륙 의도로 본다. 지상 높이를 setpoint로 주면 z 잡음(실측 +-0.1 m)으로 이륙 의도가 켜졌다 꺼졌다 할 수 있다.
- 상승 속도. 5단계에서 [추정]으로 남긴 것을 [소스]로 닫는다. Offboard에서는 `speed_up`이 `MPC_Z_VEL_MAX_UP`(기본 3 m/s)으로 덮어써지고(같은 파일 487-490행), 이륙 램프 `MPC_TKO_RAMP_T`(기본 3 s)와 `COM_SPOOLUP_TIME`이 앞에 붙는다. 수평은 `MPC_XY_VEL_MAX`(12 m/s). 메시지에 속도 필드가 없어도 된다.
- 도달 판정: `vehicle_local_position.z_valid`이고 `abs(z - z_target) < acceptance_m`. [실측] 5 m에서 오버슈트 -0.02 m(넘지 않음), 도달 뒤 5 s 동안 +-0.05 m 안. `acceptance_m` 0.3 m면 충분하다(5단계 넘김의 "[추정] 0.3 m 이상"을 실측으로 확인).
- 같은 파일 466-467행: `want_takeoff`는 `trajectory_setpoint.timestamp` + 1 s 안에서만 참이다. /fmu/in timestamp가 sim 시간으로 살아 있어야 이륙한다는 뜻이고, `UXRCE_DDS_SYNCT=0` 결정이 여기서도 필요하다.

### 2.2 LOITER: setpoint 유지

항목 시작 때의 setpoint(직전 TAKEOFF 목표점)를 그대로 `duration` 동안 발행한다. PX4 Hold 모드(AUTO_LOITER)가 아니다. 완료는 ROS 시각으로 `duration` 경과.

### 2.3 LAND: NAV_LAND 모드 명령

1. 발행을 유지한 채 NAV_LAND(21, param4-7 NaN)를 보낸다. [소스] `Commander.cpp` 1093-1110행: force로 항상 받아들여진다.
2. `nav_state == 18(AUTO_LAND)`를 처음 본 순간 `trajectory_setpoint`와 `offboard_control_mode` 발행을 멈춘다(3절의 이유). feedback은 PHASE_WAITING_MODE.
3. AUTO_LAND 3회 연속 확인. `mode_confirm_timeout` 안에 안 되면 MODE_SWITCH_FAILED.
4. 완료: `arming_state == DISARMED` 3회 연속. 그 전에 `vehicle_land_detected.landed`가 참이 된다. [소스] `Commander.cpp` 2285-2291행: 이륙한 뒤 착륙하면 `COM_DISARM_LAND`(기본 2 s) 뒤 자동 disarm. 대비책으로 `landed`가 참인 채 `COM_DISARM_LAND + 3 s` 동안 arm이면 강제가 아닌 disarm을 보낸다(지상 판정이 있으므로 받아들여진다).
5. [실측] 5 m에서 NAV_LAND -> landed 8.9-9.0 s, -> DISARMED 10.9-11.1 s(2회). 하강 0.7 m/s(`MPC_LAND_SPEED`).

판정에 `vehicle_status.latest_disarming_reason`을 쓰지 않는다. [실측] 착륙 자동 disarm에서 6이 왔다. [소스] 내부 enum(`events/enums.json`)에서 6은 `auto_disarm_land`인데 `VehicleStatus.msg`의 상수는 6을 `ARM_DISARM_REASON_SAFETY_BUTTON`으로 적고 있다. 메시지 상수가 내부 enum과 어긋난다. `detail` 문자열에 숫자로만 남긴다.

## 3. 발행 중단 규칙 (새로 찾은 것)

`trajectory_setpoint`는 nav_state가 OFFBOARD이거나 Offboard로 들어가는 중(P3-P6)일 때만 발행한다. 모드 명령(NAV_LAND, Hold)을 보낸 뒤 그 모드를 처음 본 순간 멈춘다.

- [소스] `FlightModeManager.hpp` 153행이 uORB `trajectory_setpoint`를 발행하고, `dds_topics.yaml`의 `/fmu/in/trajectory_setpoint`도 같은 uORB 토픽으로 들어간다. `MulticopterPositionControl.hpp` 107행의 구독은 하나라서 둘 중 마지막 값을 쓴다.
- [실측] NAV_LAND 착륙에서 발행을 유지한 2회(run1 최종 착륙, run2 L2)는 착지 뒤에도 `landed`가 60-90 s 동안 나오지 않았고 `ground_contact`만 오갔다. 발행을 멈춘 2회(run2 L1, run3)는 착지 뒤 약 1 s에 `landed`, 2 s 뒤 disarm.
- [실측] Hold 중 발행을 유지하고 setpoint를 북쪽 3 m, 위 3 m로 옮기자 기체가 x로 0.4 m 끌려갔다. 발행을 멈추자 0.05 m로 돌아왔다(run3).
- 이것은 5단계 취소 의미와 충돌하지 않는다. "setpoint 발행을 유지한 채 Hold 명령을 보내고 확인 뒤 CANCELED"에 "Hold를 처음 확인하면 발행을 멈춘다"를 더하면 된다. architect가 쟁점 9 문장과 `docs/interface.md`에 넣기를 요청한다.

## 4. 취소와 Hold 실험

### 4.1 실험 결과 (run1, 20261111-005636-k5)

| 경우 | 상황 | Hold ack | nav_state | 확인 시간 | 비고 |
| --- | --- | --- | --- | --- | --- |
| A | Offboard 호버 | 0(ACCEPTED) | 4 | 첫 status(약 12 ms), 3회 연속 1.01 s | 기준 |
| B | offboard 손실 failsafe(Land) 진행 중, 발행 중단 상태 | 0 | 4, `failsafe` false | 첫 status, 3회 연속 1.02 s | 하강 0.8 m 뒤 Hold. 이후 3 s 고도 유지 |
| B2 | offboard 손실 failsafe 중 발행만 재개(모드 명령 없음) | - | 14로 자동 복귀 | 0.07 s | 1.3절의 "즉시 중단" 근거 |
| C | NAV_LAND 착륙 중 | 0 | 4 | 3회 연속 1.03 s | 하강이 멈춘다 |
| D | 공중에서 강제가 아닌 disarm | 1(TEMPORARILY_REJECTED) | 변화 없음 | - | 지상 판정 아니면 거부 확인 |
| 4건 (4) | 시동 해제, 신호 없음, Offboard 요청 | 0 | 14 즉시, `pre_flight_checks_pass` false | - | 그 상태의 arm은 1(TEMPORARILY_REJECTED) |

offboard 손실 감지: 마지막 setpoint timestamp + 1.09 s에 nav_state 18. `COM_FAIL_ACT_T`(기본 5 s)의 Hold 지연은 없었다. [소스] `failsafe.cpp` 641행: 모드 폴백은 `allowUserTakeover(Always)`로 명시되어 `framework.cpp` 351-360행의 지연 설정 경로(Auto)를 지나지 않는다. 같은 이유로 모드 전환으로 사용자가 넘겨받을 수 있다(`framework.cpp` 504-519행). 실측 B와 맞는다.

### 4.2 Hold가 실패하는 경로 ([소스], 실측 없음)

- 위치 추정 무효: `UserModeIntention::change`가 arm 상태에서 `canRun(AUTO_LOITER)`를 보고 거부한다. ack가 TEMPORARILY_REJECTED이고 nav_state는 그대로다.
- 넘겨받기를 허용하지 않는 failsafe(Terminate, `UserTakeoverAllowed::Never`인 동작): 사용자 의도는 바뀌어 ack는 ACCEPTED일 수 있지만 nav_state는 failsafe 동작에 남는다. 그래서 ack가 아니라 nav_state로 확인해야 한다.
- 이 프로젝트의 파라미터에서 다른 failsafe 기본값 대조(5단계 넘김): `COM_LOW_BAT_ACT` 0(경고만), `GF_ACTION` 2(Hold)이지만 `GF_MAX_HOR_DIST`, `GF_MAX_VER_DIST`가 0이고 fence가 없어 걸리지 않음, `COM_FLT_TIME_MAX` -1(끔), `COM_WIND_MAX` -1(끔), `COM_FLTT_LOW_ACT` 0(없음). [소스] `commander_params.c`, `geofence_params.c`. 그러니 1a SITL에서 Hold를 막는 현실적 경로는 위치 무효와 비행 실패 감지(`fd_critical_failure`)뿐이다.

위치 무효 경우의 실측(pxh `failure gps off`, `SYS_FAILURE_EN=1` 필요)은 하지 않았다. 계약 분기에는 영향이 없다(아래 분기가 ack와 nav_state로 이미 덮는다). 필요하면 1a 7단계 전에 1회 한다.

### 4.3 취소 분기 권고 (쟁점 9 반영안)

- 공중 판정: `vehicle_land_detected.landed == false`. 지상 판정: true.
- 공중: 발행을 유지한 채 Hold 명령. ack가 TEMPORARILY_REJECTED이면 기다리지 않고 바로 Land 경로. AUTO_LOITER를 처음 보면 발행 중단, 3회 연속이면 CANCELED. `hold_confirm_timeout`(기본 3.0 s, ROS 시각) 안에 안 되면 NAV_LAND를 보내고 ABORTED, MODE_SWITCH_FAILED.
- failsafe 진행 중의 취소는 따로 다루지 않는다. 같은 Hold 시도를 하고 결과로 가른다(실측 B가 CANCELED 경로로 끝났다). 실제로는 1.3절 감시가 failsafe를 먼저 잡아 goal을 끝내므로 이 경우는 감지 전의 짧은 창에서만 생긴다.
- LAND 항목 중의 취소도 같은 Hold다(실측 C: 하강이 멈춘다). "착륙 중 취소는 착륙 계속"으로 바꿀지는 architect 결정. 나는 분기를 하나로 두는 쪽을 권한다. 취소한 쪽(Fleet, fixture)이 land 항목을 다시 보내면 된다.
- 지상, arm 상태: 발행을 유지한 채 강제가 아닌 disarm, DISARMED 3회 연속 뒤 발행 중단, CANCELED. disarm이 거부되거나 확인되지 않으면(이륙 램프가 막 시작돼 지상 판정이 풀린 경계) `mode_confirm_timeout` 뒤 ABORTED로 끝낸다. reason은 새 값을 만들지 않고 MODE_SWITCH_FAILED를 권한다(architect 결정). 발행을 끝까지 유지하는 이유: 지상에서 먼저 멈추면 offboard 손실 Land가 걸려 상태가 하나 더 생긴다.
- 지상, disarm 상태(PREPARING 중): 발행 중단, CANCELED.
- Hold 확인 3.0 s의 근거: ack 12-20 ms, nav_state 변화는 첫 status, 3회 연속 약 1.0 s, 재전송 2회(0.5 s 간격)를 더하면 2 s. 여유를 둬 3 s. 노드 파라미터라 계약은 아니다.

## 5. 넘김 4건 처리

| 건 | 처리 | 작업 단위 |
| --- | --- | --- |
| (1) source 값 표 | 아래 표. 그리고 `VehicleCommandBuilder` 생성 시 `source.system() == target.sysid`를 거부(ros2-engineer 구현, 단위 테스트 1건). 이렇게 하면 (대상 sysid, 1) 조합이 원천적으로 막힌다 | 6단계 `idsim_common` 소수 변경 + `idsim_mission` params |
| (2) position 플래그 고정 | setpoint 헬퍼가 `offboard_control_mode`의 position만 true, 나머지 6개 false. `trajectory_setpoint`는 position과 yaw만 유한값, velocity, acceleration, jerk, yawspeed는 NaN. position과 yaw가 유한값이 아니면 만들지 못하게(optional 반환). `Px4Timestamp` 인자 | 6단계, 헬퍼 위치는 ros2-engineer와 정함(아래 충돌 지점) |
| (3) `/clock` 지연과 `COM_OF_LOSS_T` 여유 | 실측으로 1차 확인했다. 정상 비행 4회에서 offboard 손실 오탐 없음. 노드 sim 시각 - `vehicle_status.timestamp`는 p50 0, p99 124 ms, 최대 180 ms(n 333). 여유는 1.0 - 0.05 - 0.18 = 약 0.77 s. 회귀 판정은 통합 테스트가 "setpoint 항목 동안 `failsafe`가 한 번도 true가 아니고 nav_state가 OFFBOARD를 벗어나지 않음"을 단정하는 것으로 둔다. "묵은 timestamp -> failsafe" 쪽은 아래 5.1 | 6단계 통합 테스트 |
| (4) 신호 없는 Offboard 요청 | 닫힘. 시동 해제면 ACCEPTED, nav_state 14 즉시. 그 상태에서 arm은 TEMPORARILY_REJECTED. arm 상태에서 신호 없는 요청은 [소스]로 TEMPORARILY_REJECTED(`canRun` 거부), 미실측 | 이번 의견서 |

source 값 표 (권고).

| 주체 | source_system | source_component | 비고 |
| --- | --- | --- | --- |
| `idsim_mission` Executor | 254 | 191 | MAVLink의 ONBOARD_COMPUTER 관례값 |
| SITL 통합 테스트 fixture(teardown 착륙, disarm) | 254 | 25 | MAVLink의 USER1 관례값. Executor와 ack가 섞이지 않는다 |
| 스모크 `check_px4.py` | 254 | 1 | 지금 값 유지 |

- 규칙: source_system은 어떤 기체 sysid(2-10)와도 같지 않다. 255(QGC 기본)와 190(PX4가 이 component의 거부를 콘솔에 찍는다. `Commander.cpp` 918행)은 쓰지 않는다. component 1000 이상은 이미 막혀 있다.
- Phase 3에서 Executor 여럿이 같은 (254, 191)을 써도 기체마다 ack 토픽이 달라 섞이지 않는다.
- 값은 `idsim_mission` params(생성기가 넣는 기본값이 아니라 노드 기본값)로 둔다. sysid처럼 파생값이 아니라 역할 상수다.

### 5.1 묵은 timestamp 회귀 판정 (1a 4단계 넘김)

`Px4Timestamp`는 과거 값을 만들 수 없어 노드 경로로는 시험할 수 없다. 두 안.

- 가. 통합 테스트 안에 별도 테스트로, rclpy가 timestamp를 `now - 2 s`로 넣은 `offboard_control_mode`를 20 Hz로 보내며 지상에서 Offboard 요청 뒤 arm이 TEMPORARILY_REJECTED인지 본다(비행 없이 수 초). 신호 판정이 timestamp를 보는지(`offboardCheck.cpp`의 `data_is_recent`)를 직접 확인한다.
- 나. 실측 기록으로만 두고 회귀 테스트는 만들지 않는다.

가를 권한다. 비행이 없어 싸고, SYNCT 설정이 실수로 1로 돌아가면(언더플로 클램프로 "지금"이 되어) 이 테스트가 실패한다. 다만 테스트 코드가 /fmu/in에 직접 발행하므로 lint `px4-api`와 부딪친다(충돌 지점 참고).

## 6. 토픽과 QoS, 파라미터

### 6.1 노드가 쓰는 토픽

발행(/fmu/in, 1a 허용 3개 그대로. 더할 것 없음).

| 토픽 | 용도 |
| --- | --- |
| `offboard_control_mode` | 20 Hz, position만 true |
| `trajectory_setpoint` | 20 Hz, 3절 규칙 |
| `vehicle_command` | arm, disarm, DO_SET_MODE(Offboard, Hold), NAV_LAND |

QoS는 `idsim_common::px4::px4_in_qos()`(BEST_EFFORT, VOLATILE). [소스] PX4 리더가 BEST_EFFORT, VOLATILE이라 맞는다.

구독(/fmu/out). QoS는 `px4_out_qos()`(BEST_EFFORT, VOLATILE). 발행자는 BEST_EFFORT, TRANSIENT_LOCAL, depth 1(골든)이라 맞는다. VOLATILE이라 연결 전의 묵은 ack를 받지 않는다.

| 토픽(골든 이름) | 쓰는 필드 | 발행 빈도 [소스] |
| --- | --- | --- |
| `vehicle_status_v1` | `nav_state`, `nav_state_user_intention`, `arming_state`, `failsafe`, `system_id`, `component_id`, `timestamp` | 변경 시와 500 ms마다, DDS 5 Hz 상한 |
| `vehicle_local_position_v1` | `x`, `y`, `z`, `heading`, `z_valid` | DDS 50 Hz 상한 |
| `vehicle_land_detected` | `landed` | 변경 시와 1 s마다, DDS 5 Hz 상한 |
| `failsafe_flags` | `local_position_invalid`, `local_altitude_invalid`, `global_position_invalid`, `home_position_invalid`, `offboard_control_signal_lost` | DDS 5 Hz 상한 |
| `vehicle_command_ack` | `command`, `result`, `target_system`, `target_component` | 명령마다 |

쓰지 않는 것: `vehicle_control_mode`, `vehicle_global_position`, `home_position_v1`, `estimator_status_flags`(필요한 판정은 `failsafe_flags`에 모여 있다).

nav_state 값(px4_msgs 상수를 쓴다): 4 AUTO_LOITER, 14 OFFBOARD, 18 AUTO_LAND. arming_state: 1 DISARMED, 2 ARMED.

### 6.2 SITL 파라미터

변경 없음. 상호작용만 정리한다.

- `COM_OBL_RC_ACT=4`: offboard 손실 -> 즉시 AUTO_LAND(지연 없음). 사용자 의도는 OFFBOARD로 남고 신호가 돌아오면 OFFBOARD로 복귀한다(B2). 이 복귀를 막는 파라미터는 v1.17.0에서 찾지 못했다([추정]). Executor 규칙(failsafe 감지 시 발행 중단)으로 결정적으로 만든다.
- `COM_OF_LOSS_T=1.0`: 20 Hz 발행과 실측 지연(최대 0.18 s)에 충분.
- `COM_DISARM_PRFLT=-1`: PREPARING 실패와 지상 취소에서 Executor가 disarm해야 하는 이유.
- `COM_DISARM_LAND` 기본 2 s: LAND 완료 판정의 일부.
- `COM_FAIL_ACT_T` 기본 5 s: offboard 손실에는 적용되지 않는다(4.1). 다른 failsafe(배터리 등)는 5 s Hold 뒤 동작인데 1a 파라미터에서 걸릴 경로가 없다.
- `px4-api` 검사 범위: 노드 params에는 네임스페이스(`px4_1`)만 들어가고 /fmu 문자열이 없다. remap yaml을 쓰지 않으면 범위 확장은 필요 없다.

## 7. 위험, 플래키 원인, 타임아웃

### 7.1 위험과 대응

| 위험 | 증상 | 대응 |
| --- | --- | --- |
| Offboard 아닌 모드에서 setpoint 발행 | 착륙 판정이 안 나 disarm 안 됨(실측), Hold 위치 끌림 | 3절 규칙. 통합 테스트가 LAND 완료 시간으로 잡는다 |
| failsafe 뒤 발행 재개 | 착륙 중 다시 Offboard로 올라감(실측) | 1.3절 즉시 중단 |
| 연속 미션의 시작 상태 | 착륙 뒤 nav_state가 OFFBOARD, `pre_flight_checks_pass` false | P2에서 그 값을 보지 않는다. 같은 스택에서 미션 3회를 이어 돌리면 드러난다 |
| EKF 준비 시간 | 스택 직후 arm 거부 | P2 gate. [실측] PX4 시작 후 "Ready for takeoff"까지 약 7.3 s(벽시계, 1배속), `stack.sh up --wait`가 끝날 때는 이미 준비됨. CI 4 vCPU는 [추정] 더 느리다 |
| DDS 연결 직후 손실 | 첫 명령, 첫 setpoint 유실 | 명령 재전송, 10개와 신호 플래그 동시 확인 |
| `/clock` 정지(bridge 종료) | `Px4Timestamp::now()` 정체 -> PX4가 손실 판정 -> Land | 원하는 동작이다. Executor는 `vehicle_status` 수신이 계속되면 failsafe로 끝난다 |
| `vehicle_status` 5 Hz 상한 | 짧은 상태를 놓침 | 들어감은 3회 연속, 벗어남은 1회 |
| sim 속도 저하 | 벽시계 타임아웃이 틀림 | 노드와 판정 타임아웃은 ROS 시각. lockstep이라 PX4 동작은 sim 시간에서 같다 |

### 7.2 타임아웃 권고 (ROS 시각)

노드 파라미터 기본값.

| 이름 | 값 | 근거 |
| --- | --- | --- |
| `ekf_ready_timeout` | 30 s | 실측 약 7 s의 4배 |
| `offboard_signal_timeout` | 2 s | 실측 0.5 s(10개) + 여유 |
| `mode_confirm_timeout` | 3 s | 실측 약 1.0 s + 재전송 2회 |
| `arm_timeout` | 5 s | 실측 1.5 s + TEMPORARILY_REJECTED 재시도 |
| `hold_confirm_timeout` | 3 s | 4.3절 |
| `link_timeout` | 2 s | `vehicle_status` 최소 2 Hz의 4주기 |
| `command_resend_period` | 0.5 s | check_px4.py와 같다 |

통합 테스트 미션 값(5 m 기준. 계약이 아니라 테스트 입력).

| 항목 | 값 | 실측 |
| --- | --- | --- |
| TAKEOFF timeout | 20 s | arm부터 도달 6.2-7.6 s(4회) |
| LOITER duration / timeout | 5 s / 10 s | - |
| LAND timeout | 30 s | NAV_LAND부터 disarm 10.9-11.1 s(2회) |

미션 전체는 약 3 + 7 + 5 + 11 = 26 s(sim)이므로 goal 결과 대기는 90 s(sim)를 권한다. 벽시계 상한은 스택 기동(약 35 s 실측)을 포함한 test-engineer 영역이다.

## 8. 테스트 판정에 쓸 토픽과 필드 (test-engineer에게)

- 목표 고도 도달: `vehicle_local_position_v1.z`(NED, 아래가 양)와 goal 전송 직전의 z 차이가 `-height_m +- acceptance_m`. `z_valid` 참일 때만.
- arm, disarm: `vehicle_status_v1.arming_state`(2 ARMED, 1 DISARMED), 3회 연속.
- 착륙: `vehicle_land_detected.landed` 참 뒤 `arming_state` DISARMED.
- 회귀 단정: 미션 동안 `vehicle_status_v1.failsafe`가 한 번도 true가 아니다. TAKEOFF와 LOITER 동안 nav_state 14.
- `/clock` 정렬: fixture가 `use_sim_time` 노드 시각 - `vehicle_status_v1.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s를 사전 조건으로 본다(진행 기록의 "S5에 넣을지" 항목은 S5가 아니라 6단계 fixture에 두기를 권한다. S5에는 use_sim_time PX4 수신 노드가 없다).
- teardown(취소 테스트 뒤): fixture가 source (254, 25)로 NAV_LAND를 보내고 DISARMED를 확인한다. `trajectory_setpoint`는 보내지 않는다.

## 9. 다른 담당자와 부딪칠 수 있는 지점

- ros2-engineer: (a) setpoint 헬퍼를 `idsim_common`에 둘지 `idsim_mission`에 둘지. 나는 /fmu/in 발행 API와 같은 곳(`idsim_common`)을 권한다. (b) `VehicleCommandBuilder`가 `source.system == target.sysid`를 거부하도록 생성 방식 변경(지금 생성자는 실패를 표현하지 못한다). (c) 발행 중단 규칙과 1회 반응이 노드 구조(timer와 상태 콜백의 관계)에 걸린다. (d) `failsafe_flags` 구독 추가.
- test-engineer: (a) "N회 연속"을 노드의 벗어남 감지에는 쓰지 않는다. (b) 5.1 가안은 테스트 코드가 /fmu/in에 직접 발행해 lint `px4-api`(`.py`도 검사)와 부딪친다. teardown 명령도 같다. `tests/` 아래 예외 경로를 둘지 정해야 한다. (c) `/clock` 정렬 판정의 위치(S5 대 fixture). (d) 같은 스택에서 3회 연속을 돌리면 두 번째부터 시작 상태가 OFFBOARD(시동 해제)라는 점.
- devops-engineer: 이미지와 SITL 파라미터 변경은 없다. 실패 시 `artifacts/runs/<id>/px4-1/log/`의 ULog 업로드가 sitl job에 필요하다. `Dockerfile.px4` 주석 수정은 이번에도 하지 않는다(이미지 key가 바뀐다).
- architect: 쟁점 9 문장 두 곳(잠정 규칙 삭제, "Hold 확인 뒤 발행 중단" 추가), LAND 중 취소의 분기, 지상 disarm 실패의 reason, roadmap 리스크 표의 EKF 판정 표현.

## 실측 기록

모든 실행은 스택 5(`tools/stack.sh up --stack 5`), 끝난 뒤 `tools/stack.sh down --stack 5`로 내렸다. `idsim-0`은 건드리지 않았다. 실측 스크립트는 저장소에 넣지 않았다(rclpy, `use_sim_time`, ros-ws runner에서 `docker compose ... --profile tools run --rm --no-deps -T runner bash -c "python3 -u - px4_1 2 [land|cold]"`로 표준 입력 실행, source (254, 191)).

| run id | 내용 | 주요 결과 |
| --- | --- | --- |
| 20261111-005636-k5 (1차) | 준비 판정, 넘김 (4), Offboard 진입, 5 m 이륙, Hold A/B/B2/C, 공중 disarm, 최종 착륙(발행 유지) | 1, 4절의 표. 최종 착륙은 발행 유지로 60 s 안에 landed 없음 |
| 20261111-005636-k5 (2차) | 이륙과 착륙 2회: L1 착륙 때 발행 중단, L2 유지 | L1: landed 8.9 s, disarm 10.9 s. L2: 90 s 동안 landed 없음 |
| 20261111-010537-k5 | 콜드 스타트 준비 시간, Hold 중 발행 유지와 setpoint 이동, 착륙(발행 중단) | runner 시작 시점(sim 33 s)에 이미 준비. Hold 끌림 0.4 m. landed 9.0 s, disarm 11.05 s |

실측의 한계: 경우마다 1-2회이고 이 호스트(16 vCPU, 1배속)에서만 했다. idsim-0 스택이 동시에 떠 있었다. CI 4 vCPU 조건은 재지 않았다.
