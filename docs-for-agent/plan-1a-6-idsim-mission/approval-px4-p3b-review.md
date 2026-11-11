# px4-engineer 확인: PR #23 반영 대조 결과 (2026-11-11, sonnet, 사용자 결정 U5)

요약: 다섯 항목 중 승인 3건(1, 2의 상수와 순위, 5), 수정 조건부 2건(2의 failsafe 가지, 4), 3은 승인에 문장 보강 하나다. 반대는 없다. 필수 재실측 여덟 항목은 빠진 것 셋을 더해야 한다. 수정은 모두 문장 수준이다. PX4 원문은 v1.17.0 태그를 받아 대조했다.

이전 보고의 정정: "지상 외부 disarm 뒤 nav_state가 OFFBOARD로 남는다"는 [소스 추정]이었다. 근거 소스는 UserModeIntention.cpp 78-84행(`_nav_state_after_disarming`은 arm을 막지 않는 모드면 갱신), 94-101행(onDisarm이 사용자 의도를 그 값으로 되돌림), framework.cpp 452-455행(disarm이면 action을 None으로)이다. OFFBOARD가 `modePreventsArming`에 걸리는지는 확인하지 못했으므로 실측 전에는 사실로 쓰지 않는다.

## 1. "disarm 전송 뒤 받은 표본" 기준: 승인, 문장 보강 둘

- [소스] `vehicle_status.timestamp`는 Commander.cpp 1943행 근처에서 publish 직전의 `hrt_absolute_time()`이다. SITL lockstep에서 sim 시간이라 Px4Timestamp와 같은 축이다.
- 더 강한 이유: arm과 disarm은 같은 `vehicle_command` 토픽의 FIFO이고 Commander는 사이클마다 하나씩 처리한다(Commander.cpp 1884-1898행). 늦게 도착한 arm이 disarm 뒤에 처리되는 일은 없다. 위험은 disarm 처리 전의 DISARMED 표본을 세는 것 하나이고, 그러려면 약 1 s 동안 arm이 처리되지 않아야 한다(표본 간격 약 0.5 s, 3회 연속). 노드 시계 지연 180 ms는 표본 하나 정도의 틈만 연다.
- 보강 1: "timestamp가 뒤"는 엄격 부등호(>)로 쓰고, 같은 timestamp의 표본이 두 번 오면 한 번만 센다. 3회 연속은 서로 다른 timestamp 3개다.
- 보강 2: [추정]을 "[소스] FIFO 순서 + 표본 간격 0.5 s"로 바꾸고 지연 분포는 재실측 (5)에서 기록한다.

## 2. REASON_EXTERNAL_DISARM = 14와 감시 표 순위: 상수와 순위 승인, 순위 5의 failsafe 가지 수정 조건부

- 상수 추가 승인. 내 제안(EXTERNAL_MODE_CHANGE)을 철회한다. 공중 모드 변화 뒤는 다음 TAKEOFF가 PRECONDITION_FAILED이고 지상 disarm 뒤는 TAKEOFF를 받을 수 있어 읽는 쪽의 다음 동작이 다르다.
- 순위 1-3 먼저, 4-5가 6-8보다 앞: 승인.
- 수정 조건(순위 5): 자동 disarm에서는 failsafe 가지가 거의 죽어 있다.
  - [소스] Commander.cpp 1843행 `handleAutoDisarm()`이 1866행 근처 `handleModeIntentionAndFailsafe()`보다 앞에서 disarm한다. 후자는 `state.armed = isArmed()`(2344행)로 읽고 framework.cpp 452-455행은 disarm이면 `Action::None`이다. 따라서 자동 disarm 사이클의 첫 DISARMED 표본은 `failsafe == false`이고 `nav_state`는 의도로 되돌아가 있다.
  - `failsafe == true`인 DISARMED 표본은 명령 disarm(핸들러가 1898행이라 같은 사이클 표본이 이전 failsafe를 가진다)에서만 나온다.
  - 결과: 지면 근처의 짧은 failsafe Land가 앞선 ARMED 표본에서 3회 연속을 못 채우고 자동 disarm으로 끝나면 EXTERNAL_DISARM으로 오분류된다.
  - 수정 문장(순위 5 reason 칸): "`failsafe == true`이거나, 이 항목 실행 중 `failsafe == true`이거나 `nav_state`가 OFFBOARD가 아닌 표본을 한 번이라도(3회 연속 미달이어도) 본 적이 있으면 FAILSAFE, 아니면 EXTERNAL_DISARM". "남는 경우" 문장은 이 규칙으로 바꾼다.
- EXTERNAL_DISARM 의미 문장에 "원인은 판정하지 않는다(외부 명령뿐 아니라 PX4 자체 disarm, kill 포함)"를 더한다.

## 3. 지상 setpoint는 발행 중일 때만 바꿈, 멈춘 발행은 다시 켜지 않음: 승인(보강 한 문장)

- [소스] MulticopterPositionControl.cpp 464-467행: 이륙 의도는 `flag_control_offboard_enabled`일 때만 `_setpoint.timestamp + 1 s` 안의 setpoint로 켜진다. 발행이 멈춘 이유가 전부 OFFBOARD가 아닌 표본 또는 AUTO_LAND 관측이므로 어긋나는 경우가 없다. 다시 켜면 위험하다(실측: offboard 손실 Land 중 발행 재개 0.07 s 만에 OFFBOARD 복귀).
- 발행이 멈춘 뒤 OFFBOARD에 머무는 유일한 경로는 LAND 항목의 ITEM_TIMEOUT이다.
- disarm 수락: Commander.cpp 644-662행. 강제가 아니면 `landed || maybe_landed`일 때 받는다. 노드의 `landed == true`는 수락 충분조건이다.
- 보강 문장: "발행이 멈춘 뒤에는 `trajectory_setpoint`를 바꾸지 않으므로 이륙 의도에 영향이 없다. 이 규칙은 '멈춘 발행은 항상 nav_state가 OFFBOARD가 아닌 것을 본 뒤'라는 불변식에 기댄다. LAND 항목의 ITEM_TIMEOUT처럼 OFFBOARD인 채 멈추는 경우는 이 규칙의 적용 대상이 아니다(지상 arm이면 offboard 손실 Land가 내린다)."

## 4. `[LAND]` 단독 미션의 ITEM_TIMEOUT 단서: 수정 조건부

- [소스] Commander.cpp 1093-1110행: NAV_LAND는 force라 사용자 의도가 즉시 AUTO_LAND로 바뀐다. Hold에 남는 것은 명령이 도착하지 않았을 때뿐이다. 1089-1091행 주석대로 Land를 못 쓰는 상태(위치 무효 등)면 DESCEND로 대체된다.
- AUTO_LAND를 못 본 채 ITEM_TIMEOUT까지 가려면 항목 timeout이 `mode_confirm_timeout`(3 s)보다 짧아야 한다.
- 수정 문장: "...AUTO_LAND를 관측하지 못한 채 ITEM_TIMEOUT이 되는 것은 항목 timeout이 `mode_confirm_timeout`보다 짧을 때뿐이다. 이때 NAV_LAND가 도착하지 않았다면 기체는 있던 모드(보통 Hold)에, 도착했다면 AUTO_LAND(위치가 무효면 DESCEND)로 PX4가 착륙을 이어 간다. 어느 쪽인지 `detail`에 적는다. AUTO_LAND를 확인한 뒤의 ITEM_TIMEOUT도 PX4가 착륙을 이어 간다."

## 5. 재전송 표: 승인

- NAV_LAND(LAND 항목), NAV_LAND(M4 Land 경로), DISARM(지상 arm 분기) 행이 맞다.
- DISARM(LAND 대비책) 별도 타임아웃 없이 항목 timeout이 상한: 승인. 강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 거부되므로(Commander.cpp 644-662행) 공중 기체를 끌 위험이 없다. 대비책 disarm은 `landed == true`이고 `land_disarm_fallback_delay`가 지난 뒤에만 시작한다는 조건을 구현 때 확인한다.
- 비조건: Hold 행의 "타임아웃"은 `hold_confirm_timeout`임을 적는다.

## 필수 재실측에 더할 셋

1. (4)에 failsafe Land 뒤 자동 disarm의 첫 DISARMED 표본 기록(`failsafe`, `nav_state`, `nav_state_user_intention`, `landed`). 명령 disarm(대비책)의 첫 표본도 함께.
2. (2)에 "Hold를 확인하고 발행을 멈춘 뒤 landed가 true인 상태에서 disarm" 3회(수락 여부, 고도 변화 0.2 m 이하).
3. (5)에 모든 `vehicle_status` 표본의 (timestamp, 노드가 받은 ROS 시각, 같은 시점의 /clock) 기록으로 `timestamp - Px4Timestamp` 지연 분포를 구한다.

권고: (3)의 이륙 직후 지상 setpoint와 disarm은 시각 제어(sleep)가 아니라 landed 표본에 맞춘 조건 trigger로 보낸다. 실측 스크립트는 px4 쪽에 두는 입장이다(소유는 test-engineer와 정한다).
