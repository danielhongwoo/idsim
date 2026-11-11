# px4-engineer 검토: P3b 착수 전 승인 항목 다섯, 타임아웃과 재전송 주기 값 (2026-11-11)

다섯 항목 중 승인 2건(2, 5), 수정 조건부 3건(1, 3, 4)이다. 반대는 없다. 다만 5번의 "landed 뒤의 disarm은 지상 disarm"은 고정 규칙(아래 5번)이 없으면 틀린 판정을 낸다. 4번은 내용은 승인하되 문장 보강이 필요하다. 수정 조건 3건은 모두 문장만 고치면 된다.

확인은 두 가지로 했다.
- 소스: PX4 v1.17.0 태그 원문 대조(Commander.cpp, MulticopterPositionControl.cpp, Takeoff.cpp, MulticopterLandDetector.cpp, LandDetector.cpp, UserModeIntention.cpp, framework.h, framework.cpp).
- 실측: 스택 5, run id 20261111-030155-k5. 실측 스크립트는 당시 scratchpad의 임시 파일이라 저장소에 없다.

## 실측 요약 (run 20261111-030155-k5, 경우마다 1-3회, 16 vCPU 호스트, idsim-0 동시 가동)

| 경우 | 내용 | 결과 |
| --- | --- | --- |
| G x2 | OFFBOARD에서 처음부터 지상 setpoint를 보내며 arm. 기준점은 시작 위치이고 z는 시작 z + 0.5 m(NED, 땅 아래쪽), yaw는 현재 heading. 4 s 유지 뒤 강제가 아닌 disarm | 상승은 최대 0.05 m로 잡음 수준이다. landed는 계속 true. disarm ack는 ACCEPTED(1회는 ack 유실). DISARMED까지 4-12 ms |
| H x2 | TAKEOFF 목표점(5 m)으로 arm. 첫 ARMED 표본 뒤 1.5 s와 2.5 s에 지상 setpoint로 바꾸고 disarm | 바꾸는 순간 이미 landed false였다(높이 0.07 m 이하). disarm은 TEMPORARILY_REJECTED였고 3 s 뒤 재시도도 거부됐다. 지상 setpoint로 상승은 0.2 m 이하로 막혔지만 landed는 6 s 동안 돌아오지 않았다. 정리용 NAV_LAND를 보내자 3.4-3.5 s 뒤 disarm됐다 |
| K x1 | 목표점을 유지한 채 1.5 s에 disarm(reviewer가 우려한 경우) | disarm 거부, 4.2 m 상승. 우려가 실제로 일어남을 확인했다 |
| X2a x2 | 이륙 램프 중(첫 ARMED 뒤 1.3 s, 1.8 s)에 Hold를 보내고, 처음 관측한 순간 발행 중단, 12 s 관찰 | 1.3 s는 Hold 확인 시점에 landed true였고 0.16 s 뒤 false가 됐다. 둘 다 12 s 동안 landed false, ARMED, AUTO_LOITER였고 높이는 -0.11에서 0.06 m(사실상 지상)였다. 자동 disarm은 없었다. NAV_LAND를 보내자 disarm됐다 |
| X2b x1 | 0.5 m 호버에서 Hold | 12 s 동안 landed false, ARMED, 0.37-0.47 m에 머물렀다. NAV_LAND로 disarm됐다 |
| D x1 | 이미 DISARMED인 상태에서 disarm | ack ACCEPTED |

## 항목별 판정

### 1. ITEM_TIMEOUT 뒤 정리: 수정 조건부 승인

snapshot 분기(공중 Hold, 지상 arm이면 disarm, 지상 disarm이면 바로 끝)와 reason ITEM_TIMEOUT 유지는 승인한다. 조건은 넷이다.

(a) 지상 arm 분기는 3번의 지상 setpoint 규칙을 따른다. TAKEOFF가 timeout까지 땅을 못 떴다는 것은 사실상 이륙 의도가 켜지지 않은 경우다(timestamp 문제 등. MulticopterPositionControl.cpp 466-467). 이때는 Takeoff 상태가 ready_for_takeoff에 머물러 실측 G처럼 disarm이 바로 받아들여진다.

(b) "LAND이면 그대로 끝낸다"를 다음으로 바꾼다.
> LAND 항목의 ITEM_TIMEOUT: NAV_LAND 재전송을 멈춘다. 아직 발행 중이면(AUTO_LAND를 한 번도 관측하지 못함) 발행을 멈춘다. 그 뒤는 PX4의 offboard 손실 Land(COM_OBL_RC_ACT=4)가 내린다. Hold는 보내지 않는다. landed인 채 ARMED였으면 detail에 적는다.

(c) "ABORTED 뒤 기체 상태" 표에 한 줄을 더한다. 지면 바로 위에서 Hold로 끝난 ITEM_TIMEOUT 또는 CANCELED 기체는 ARMED, landed false인 채 지상이나 지면 근처에 머문다. 스스로 disarm되지 않는다(실측 X2a 2회, X2b 1회, 각 12 s). 이어 보낸 `[LAND]` 미션은 시작 조건(armed이고 landed false)을 통과하고 NAV_LAND로 disarm까지 간다(실측 5회).

(d) 아래 "추가로 발견한 문제" 1, 2(arm 전송 뒤의 경쟁, arm 재전송 중단)를 정리 절차 전체에 적용한다.

### 2. TAKEOFF 시작 조건(지상이고 DISARMED만): 승인

허용으로 바꿀 이유를 찾지 못했다. 보강 근거는 실측 H와 K다. arm 뒤 이륙 램프가 시작되면 높이 0.07 m에서도 landed가 false가 되고, 그 뒤로는 강제가 아닌 disarm이 거부된다(Commander.cpp 644-662). Takeoff 상태기는 rampup에서 뒤로 돌아가지 않는다(Takeoff.cpp 77-87). 남이 arm한 기체를 넘겨받으면 이 경계를 통제할 수 없다.

### 3. 지상 arm 취소 분기의 setpoint: 수정 조건부(문장 확정)

쟁점 3 M5의 "이 분기에서 유지하는 setpoint" 문단을 다음으로 바꾼다.
> 지상 arm 분기에 들어간 tick에 `trajectory_setpoint`를 "지상 setpoint"로 바꾼다. 지상 setpoint는 그 tick의 `vehicle_local_position` x, y, z에서 z만 +0.5 m(NED, 아래쪽)이고 yaw는 그 tick의 heading이다. position과 yaw만 유한값이고 나머지는 NaN이며, `offboard_control_mode`는 position만 true다(헬퍼 그대로). 20 Hz 발행을 유지한 채 disarm을 재전송한다. DISARMED 3회 연속이면 발행을 멈추고 CANCELED. 대기 중 landed가 false가 되면 공중 분기로 넘어가되, setpoint는 TAKEOFF 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다. Hold를 처음 관측하면 발행을 멈춘다. disarm의 TEMPORARILY_REJECTED ack는 그 자체로 실패가 아니다. landed true인 동안 재전송을 이어 간다.

근거.
- [소스] MulticopterPositionControl.cpp 466-472: 이륙 의도는 setpoint z < 현재 z일 때만 켜진다(엄격 비교). 같은 파일 504-520: 이륙 전이면 추력 0이다. 0.5 m는 z 잡음(+-0.1 m)의 5배 여유다.
- [실측] G에서 상승이 없었고 disarm까지 4-12 ms였다. K는 목표점을 유지하면 4.2 m 상승함을 보였다.
- 기각한 안: "발행을 멈춘 뒤 disarm". 마지막 setpoint timestamp + 1 s 동안 이륙 의도가 남는다(466-467). 그 뒤에는 offboard 손실 Land가 걸려 상태가 하나 더 생긴다.
- 같은 규칙을 지상 arm 정리 전부에 쓴다: PREPARING 실패, ITEM_TIMEOUT 지상 arm, 그리고 추가 문제 1의 경우.
- 0.5 m는 `src/px4/` 어댑터 상수로 두고 노드 파라미터로 만들지 않는다.

### 4. LAND 감시의 세 구간: 수정 조건부 승인

세 구간과 완료 우선 규칙은 승인한다. 근거는 둘이다.
- [소스] 정상 착륙에서 "ARMED인데 AUTO_LAND가 아닌" 표본은 나오지 않는다. 자동 disarm(Commander.cpp 1843 handleAutoDisarm, 675 onDisarm)이 같은 주기의 nav_state 계산(1866, 2369-2372)과 발행(1945)보다 앞서기 때문이다. 즉 DISARMED와 새 nav_state가 한 표본에 같이 온다.
- 대비책 disarm처럼 명령으로 내는 disarm은 nav_state 계산 뒤에 처리된다(1898). 그래서 "DISARMED + AUTO_LAND" 표본이 한 번 나온 다음 nav_state가 바뀐다. 두 경우 모두 완료 우선 규칙이 덮는다.

보강할 문장은 셋이다.
- (a) AUTO_LAND 확인(3회 연속)은 `failsafe` 값과 무관하게 `nav_state == AUTO_LAND`로 센다. offboard 손실 Land 중인 기체에 보낸 `[LAND]`, 흔들림 뒤 발행 중단으로 생긴 failsafe Land 모두 정상 경로다.
- (b) 확인 전 구간에서도 발행 규칙을 그대로 적용한다. OFFBOARD도 AUTO_LAND도 아닌 표본을 보면 발행을 멈추고 다시 켜지 않는다. 이탈 판정은 하지 않고 NAV_LAND 재전송과 `mode_confirm_timeout`만 이어 간다.
- (c) "DISARMED이고 landed"의 landed는 5번의 고정 규칙으로 읽는다.

### 5. 방어용 분류: 승인, 한 조건

X4의 분류(`failsafe` false이고 사용자 의도가 OFFBOARD인데 nav_state가 OFFBOARD가 아님 -> FAILSAFE)는 승인한다.
- [소스] framework.h 150: `inFailsafe`는 None과 Warn이 아닐 때 참이다.
- [소스] framework.cpp 684-690: None과 Warn에서는 nav_state가 사용자 의도와 같다.
- [소스] Commander.cpp 2369-2372, 2388.

"landed 뒤의 disarm은 지상 disarm"에는 조건 하나를 단다. 문장을 이렇게 바꾼다.
> disarm의 분류(지상 대 공중)는 처음 관측한 DISARMED 표본의 tick에, 그때까지 받은 최신 `landed` 값으로 정하고 고정한다. 뒤에 오는 `landed` 표본으로 바꾸지 않는다.

근거: [소스] MulticopterLandDetector.cpp 249, 287, 296(`return !_armed || ...`)와 318-320(LNDMC_TRIG_TIME/3 지연). 공중에서 disarm돼도 약 0.33 s 뒤 landed가 true로 바뀌어 발행된다. 그래서 고정하지 않으면 공중 disarm이 지상 disarm(CANCELED 또는 완료)으로 잘못 분류될 수 있다.

## 타임아웃 기본값과 명령 재전송 주기 (최종, ROS 시각, 노드 파라미터)

| 이름 | 값 | 근거 |
| --- | --- | --- |
| `ready_timeout` | 30 s | 준비까지 약 7 s의 4배, discovery 1.1 s 포함 |
| `offboard_signal_timeout` | 2 s | 10회 발행 0.5 s + 여유 |
| `mode_confirm_timeout` | 3 s | 3회 연속 약 1.0 s, 표본 1개 유실 시 1.5 s, 명령 1회 유실 0.5 s |
| `arm_timeout` | 5 s | ARMED 3회 연속 약 1.5 s + TEMPORARILY_REJECTED 재시도 |
| `hold_confirm_timeout` | 3 s | 4.3절 |
| 지상 disarm 확인(M5) | 3 s | `mode_confirm_timeout`을 그대로 쓴다. 실측 4-12 ms + 3회 연속 약 1.0 s. 이름을 따로 두려면 `disarm_confirm_timeout` 3 s(권고일 뿐 조건 아님) |
| `link_timeout` | 2 s | `vehicle_status` 최소 2 Hz의 4주기 |
| `land_disarm_fallback_delay` | 5 s | COM_DISARM_LAND 2 s + 3 s |
| `command_resend_period` | 0.5 s | [실측] 이번 run에서 ack 1건 유실 |
| 지상 setpoint z 오프셋 | +0.5 m | 어댑터 상수(파라미터 아님) |

재전송 규칙. 대기 중인 명령은 한 번에 하나다. 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 즉시 지운다. ack는 `command`와 `target`으로 맞춘다.

| 명령 | 0.5 s 재전송을 멈추는 때 | 거부 ack |
| --- | --- | --- |
| DO_SET_MODE(Offboard) | OFFBOARD 3회 연속, 타임아웃 | ACCEPTED가 아니면 MODE_SWITCH_FAILED |
| ARM | ARMED 3회 연속, 타임아웃, 취소나 실패를 정한 tick(즉시) | TEMPORARILY_REJECTED는 재시도, 그 밖의 거부는 ARM_REJECTED |
| Hold | AUTO_LOITER 3회 연속, 타임아웃 | 거부면 즉시 Land 경로 |
| NAV_LAND | AUTO_LAND 3회 연속, ITEM_TIMEOUT | force라 거부 없음(Commander.cpp 1093-1110) |
| DISARM | DISARMED 3회 연속, landed false로 분기 전환, 타임아웃 | TEMPORARILY_REJECTED여도 landed인 동안 재시도 |

같은 명령을 여러 번 받아도 결과가 같다. 이미 disarm된 기체에 보낸 disarm은 ACCEPTED다(Commander.cpp 640-642, 976-980, 실측 D).

## 전이 표에서 추가로 발견한 문제

1. arm을 보낸 뒤의 "지상 disarm이면 바로 끝"은 안전하지 않다.
   - 상황: P6에서 arm을 보냈고, 아직 처리되기 전이거나 status에 반영되기 전에 취소나 실패가 오면 snapshot은 DISARMED다.
   - 결과: "바로 끝"으로 발행을 멈추면 그 뒤 arm이 처리된다. 기체는 OFFBOARD에서 신호 없이 armed가 되고, offboard 손실 Land로 들어간다. 이륙 이력이 없으니 자동 disarm이 없어(Commander.cpp 2290, 2294, COM_DISARM_PRFLT=-1) 지상에 armed로 남는다(X3와 같은 상태).
   - 수정 문장: "이 goal에서 arm을 한 번이라도 보냈으면 지상 분기는 arming_state와 무관하게 disarm 분기(지상 setpoint + disarm + disarm 전송 뒤 받은 DISARMED 3회 연속)를 거친다."
   - 비용은 약 1 s다. disarm은 이미 DISARMED여도 ACCEPTED다.
2. arm 재전송은 취소나 실패를 정한 tick에 즉시 멈춘다. 위 표에 넣었다. 지금 문서에는 재전송을 멈추는 조건이 없다.
3. setpoint 항목 감시 표에 빈 칸이 있다: 지상에서 DISARMED.
   - 상황: TAKEOFF가 뜨기 전에 외부에서 disarm되면 nav_state는 OFFBOARD, `failsafe`는 false로 남는다. 어떤 행에도 걸리지 않아 ITEM_TIMEOUT(20 s)까지 발행이 이어진다.
   - 추가할 행: "DISARMED이고 (5번 규칙으로 고정한) landed가 true: `failsafe`면 FAILSAFE, 아니면 EXTERNAL_MODE_CHANGE. 발행 중단, ABORTED, detail에 disarm."
   - reason 이름은 architect가 정한다.
4. 지면 근접 Hold에 관한 [추정]은 실측과 반대다(쟁점 3 M3, 넘김 목록의 재실측 일부).
   - 이륙 중이나 0.5 m 이하에서 Hold하면 내려앉아 disarm되지 않는다. ARMED, landed false로 머문다(3회, 12 s).
   - 원인 [소스]: Hold는 하강 속도 setpoint가 없어 ground_contact가 서지 않는다(MulticopterLandDetector.cpp 229-236). reviewer의 지적이 맞았다.
   - 따라서 M3의 "지면 바로 위에서 취소되면 내려앉아 disarm될 수 있다"와 "`[LAND]`가 PRECONDITION_FAILED로 끝날 수 있다"는 이륙 단계에 대해서는 틀렸다. 이 경우 `[LAND]`는 정상적으로 착륙한다(실측 5회).
   - 아직 닫히지 않은 것: AUTO_LAND 하강 중 0.3 m 아래에서의 취소. 이 경우는 이미 ground_contact가 서 있을 수 있어 다르다. 넘김 목록의 필수 재실측으로 그대로 남긴다.
5. landed가 false인데 기체가 사실상 지상에 있는 상태가 있다.
   - 실측 H, X2a: position만 쓰는 Offboard나 Hold에서 이륙 램프 뒤 땅에 있어도 landed가 돌아오지 않는다.
   - 공중 판정(`landed == false`)은 "기체 높이"가 아니라 "PX4 착륙 판정"이라는 뜻이다. 문서의 "공중"을 "landed false"로 읽도록 용어 주석을 한 줄 다는 것을 권한다.
   - 분기 동작은 이것으로 맞다. 공중 분기의 Hold는 받아들여진다.
