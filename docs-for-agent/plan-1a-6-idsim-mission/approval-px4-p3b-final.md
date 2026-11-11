# px4-engineer 확인: decisions.md "확인 예정" 네 항목과 C5, C2 (2026-11-11, sonnet, 사용자 결정)

PX4 v1.17.0 원문 대조, 새 실측 없음. 요약: 항목 1 승인(설명 정정 필요), 항목 2 승인(근거 보강), 항목 3 승인, 항목 4 수정 조건부(동작은 맞음, v1.17.0에서 해당 ack가 사실상 안 나온다는 사실을 적을 것). C5 문제 없음. C2 문제 없음, 설명 한 줄 보강. 반대 없음. "Commander" = src/modules/commander/Commander.cpp, "framework" = commander/failsafe/framework.cpp 또는 .h, "failsafe.cpp" = commander/failsafe/failsafe.cpp. 행 번호는 받은 파일 기준이고 이전 인용과 1-2행 차이가 날 수 있다.

## 항목 1. 순위 5 이력 문장: 승인

- 이 표는 OFFBOARD 이탈을 1회로 판정하므로 "OFFBOARD가 아닌 표본의 이력"은 죽은 조건이고 px4 원문(approval-px4-p3b-review.md 2번)이 틀렸다. architect 문장 그대로 승인.
- 설명 "살아 있는 경우는 둘"은 정정:
  - 이 표본의 failsafe가 true인 DISARMED는 명령 disarm 말고도 failsafe Action::Disarm에서 나온다(COM_OBL_RC_ACT=Disarm failsafe.cpp 321-322행, GCS 손실 Disarm 73-75행). Commander 2375-2377행이 `disarm(failsafe, true)`를 강제로 부르고 2388행 `_vehicle_status.failsafe = inFailsafe()`가 뒤에 와서 같은 주기 publish(1944-1945행)에 DISARMED와 failsafe true가 함께 실린다. framework.cpp 689행 `modeFromAction`은 Disarm에서 사용자 의도를 돌려주므로 nav_state는 OFFBOARD로 남는다. landed에 따라 순위 4 또는 5(FAILSAFE).
  - 앞선 표본에서 "OFFBOARD인 채 ARMED, failsafe true"는 v1.17.0에서 안 나온다(항목 2). 이력 가지는 이 PX4 버전에서 닿지 않는 방어 코드다. 문서에 "[소스]로는 닿지 않는 방어용"이라 적고, 이력 가지 테스트는 합성 표본으로만 가능하다고 적는다.
  - "덮지 못하는 경우"(짧은 failsafe Land에서 OFFBOARD 벗어난 ARMED 표본 없이 자동 disarm)도 실제로는 거의 없다. failsafe가 걸리는 주기에 nav_state와 failsafe가 바뀌어 vehicle_status가 즉시 publish되므로(1941-1945행 `nav_state_or_failsafe_changed`) 그 표본이 순위 6에서 goal을 끝낸다. 자동 disarm(COM_DISARM_LAND 2 s)은 그 뒤다. 덮지 못하는 것은 노드가 그 표본을 놓쳤을 때(수신 끊김, tick당 최신 1표본 모델에서 50 ms 안 연속 표본)뿐이다.
- 자동 disarm 첫 DISARMED 표본이 failsafe false라는 근거 재확인: Commander 1843행 handleAutoDisarm이 1866행 handleModeIntentionAndFailsafe보다 앞, 2346행 `state.armed = isArmed()`, framework.cpp 452-455행.
- 수정 문장(설명 불릿 대체): "이 표본의 failsafe가 true인 DISARMED는 명령 disarm과 failsafe Action::Disarm(COM_OBL_RC_ACT=Disarm, GCS 손실 Disarm. Commander 2375-2377행)에서 나온다. 앞선 표본의 failsafe 이력은 v1.17.0에서 OFFBOARD인 채로는 생기지 않으므로([소스]) 이 가지는 방어용이다."

## 항목 2. (ii) OFFBOARD + ARMED + failsafe true: 승인(표대로가 의도)

- v1.17.0 정상 상태에서 나오지 않는다. failsafe는 `inFailsafe()`(framework.h 150행, None과 Warn 제외). nav_state는 `modeFromAction(selectedAction, 사용자 의도)`(Commander 2371-2373행 근처, framework.cpp 670-700행). 사용자 의도(OFFBOARD)를 그대로 돌려주는 동작은 None, Warn, Disarm, Terminate뿐이다. None/Warn은 failsafe false, Terminate는 Commander 2379-2382행이 TERMINATION으로 덮고, Disarm은 같은 주기 강제 disarm으로 DISARMED 표본이 된다. Hold, RTL, Land, Descend, Fallback은 모드가 바뀐다.
- COM_FAIL_ACT_T(기본 5 s) 지연 중에는 `selected_action = Action::Hold`(framework.cpp 495-500행)라 nav_state AUTO_LOITER, failsafe true로 순위 6에 걸린다. failsafe 유예(`_defer_failsafes`, 483-487행)는 None, 사용자 takeover는 Warn(512-519행). 외부 mode 치환(ModeManagement.cpp 437-461행)은 OFFBOARD가 아니다.
- 만약 나왔다면 goal을 계속하는 것이 안전하다. 모드를 바꾸지 않는 failsafe이고, 발행을 멈추면 offboard 손실 failsafe를 스스로 유발한다. 다음 표본의 모드 이탈을 순위 6-8이 잡는다.
- 근거 보강: "[소스]로는 정상 상태에서 나오지 않는다(None과 Warn이 아니면 failsafe 동작이 모드를 바꾼다)"에 "예외는 Disarm(같은 주기에 DISARMED 표본)과 Terminate(nav_state TERMINATION)"를 더한다.
- 참고: offboard 손실 Land는 사용자 의도 자체를 AUTO_LAND로 바꾼다(failsafe.cpp 306-309행, Commander 2352-2356행). 순위 7/8의 사용자 의도 비교는 이 경로에서 순위 6이 먼저라 영향 없다.

## 항목 3. 지상 disarm 분기의 LINK_LOST: 승인

- 지상(landed true), 지상 setpoint라 상승 0.2 m 이하(G/H 실측). 발행 중단 뒤 offboard 손실 failsafe(COM_OBL_RC_ACT)는 지상이면 Land와 자동 disarm, 공중이면 하강. 위험 없음.
- 추가 disarm은 최선 노력. 강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 TRANSITION_DENIED(Commander 638-662행)라 공중 기체를 끄지 않는다. 강제(param2 == 21196)는 쓰지 않는다는 조건 유지.
- link_timeout 2 s < mode_confirm_timeout 3 s 순서 맞다. vehicle_status 최소 500 ms 주기(Commander 1941행)라 2 s는 4주기 부재. ROS 시각과 PX4 lockstep 시각의 비 전제는 공중 분기(M4)와 같다.

## 항목 4. DISARM의 그 밖의 거부 ack: 수정 조건부(동작 승인, 사실 한 줄)

- 동작(그 자리에서 끝내지 않고 landed인 동안 재전송, 타임아웃에 DISARM_FAILED, 마지막 ack를 detail, 판정은 arming_state)은 맞다.
- v1.17.0에서 유효한 ARM_DISARM(param1 0 또는 1)의 ack는 둘뿐이다: TRANSITION_DENIED면 TEMPORARILY_REJECTED, 그 밖은 ACCEPTED(Commander 969-980행). DENIED는 나오지 않는다. UNSUPPORTED는 param1이 잘못된 경우(752, 955-958행)뿐이고 보내지 않는다. 대상 불일치(746-749행)는 ack 없이 버려져 타임아웃이 처리한다.
- 수정 문장 추가: "[소스] v1.17.0의 ARM_DISARM 처리(Commander 969-980행)는 유효한 param1에 ACCEPTED와 TEMPORARILY_REJECTED만 돌려준다. 그 밖의 ack(DENIED, UNSUPPORTED 등)는 방어용이며 같은 규칙(재전송, 타임아웃에 종료)을 쓴다." 테스트는 합성 ack로만.
- ARM 행의 "그 밖의 거부는 ARM_REJECTED"도 v1.17.0에서는 ACCEPTED/TEMPORARILY_REJECTED만 나오므로(arm()의 DENIED도 TEMPORARILY_REJECTED로 매핑, Commander 549행) 같은 방어용이다.

## C5: 문제 없음

- 지상 DISARMED 3회째와 같은 tick의 취소는 SUCCEEDED가 맞다(이미 disarm).
- ABORTED 사유가 완료보다 앞서는 것이 안전하다(같은 tick에 landed false DISARMED(순위 4)와 완료 후보가 겹치면 분류 고정 규칙으로 FAILSAFE가 이겨야 공중 disarm이 성공으로 기록되지 않는다).
- 종료 뒤 cancel 무시는 부작용 없음. 전제: 종료 시점에 발행이 멈추고 명령 재전송이 지워져 있어야 한다.

## C2: 문제 없음, 설명 한 줄

- vehicle_status.timestamp는 publish 직전 hrt_absolute_time()(Commander 1944행)이라 단조 증가. 같음은 같은 표본 재관측, 줄어듦은 PX4 재시작이나 시계 되감김뿐.
- 전달 지연 동안 이미 publish된 표본이 "뒤" 조건을 만족할 수 있으나 그 표본이 DISARMED면 실제로 disarm 상태라 오판정이 아니다. 위험은 늦게 처리된 arm 하나인데 arm/disarm은 같은 vehicle_command FIFO이고 주기당 하나씩 처리(Commander 1884-1898행)되어 disarm 뒤 늦은 arm은 없다. 이 FIFO 논거를 C2 설명에 적어 "엄격히 뒤"가 방어층임을 분명히 한다.
- 3회 연속(서로 다른 timestamp 3개)은 표본 간격(변화 시 즉시, 이후 2 Hz) 기준 약 1 s로 mode_confirm_timeout 3 s 안.

## 재실측 (4) 메모

- 선택 항목 추가: failsafe Action::Disarm 경로(COM_OBL_RC_ACT=Disarm)의 DISARMED 표본에서 failsafe, nav_state가 예상(true, OFFBOARD)과 같은지. 현재 시작 파라미터가 Land면 닿지 않으므로 필수 아님.
