# 1a 6단계 idsim_mission 설계 결정 (architect, 2026-11-11)

입력: px4-engineer 의견서(git 이력)(스택 5 실측), ros2-engineer 의견서(git 이력)(스택 6 실측), test-engineer 의견서(git 이력)(실측 없음), devops-engineer 의견서(git 이력)(조회만), 충돌 지점 재질문 답 다섯 건(px4, ros2, test, devops, logging. 아래 "재질문 결과 요약"). reviewer 검증(조건부. 필수 7건, 권고 10건)과 사용자 결정 3건(2026-11-11, 호출한 쪽이 전달)을 반영한 확정본이다. 무엇이 바뀌었는지는 "확정 개정 요약"에 있다. 구현은 이 문서를 따른다. `docs/`와 코드는 이 문서로 고치지 않았다. 반영할 곳은 "문서 반영 목록"에 있다. `progress.md`는 호출한 쪽이 갱신한다.

2026-11-11에 px4-engineer의 P3b 착수 전 승인 검토(px4-engineer P3b 착수 전 승인 검토(git 이력). 승인 2건, 수정 조건부 3건, 반대 없음, 실측 run 20261111-030155-k5)를 반영했다. 바뀐 곳과 계약, golden, 상수에 주는 영향은 "px4-engineer 승인 반영"에 있다. 그 반영(PR #21)에 대한 reviewer 검증(조건부. 필수 5건, 권고 6건)과 사용자 결정 2건을 같은 날 다시 반영했다("PR #21 reviewer 검증 반영"). 이 개정에서 상수 `REASON_EXTERNAL_DISARM = 14`가 더해졌다. 그 개정(PR #23)에 대한 px4-engineer 확인(px4-engineer PR #23 반영 확인(git 이력). 승인 3건, 수정 조건부 2건, 반대 없음)과 reviewer 검증(조건부. 필수 3건)도 반영했다("PR #23 검토 반영"). 같은 날 P3a 실험 결과(P3a 실행 확인 결과(git 이력))가 쟁점 2의 전제(컨테이너 autostart)를 깨서 쟁점 2를 다시 결정했다("P3a 결과 반영"). 그 재결정에 대한 devops-engineer 의견(devops-engineer 쟁점 2 재결정 검토(git 이력). 반대 없음, 조건 다섯)과 reviewer 최종 확인(조건부. 필수 3건)도 반영했다("쟁점 2 재결정의 검토 반영"). 이어서 ros2-engineer의 timer 확인과 test-engineer의 조건부 승인(test-engineer P3 조건부 승인(git 이력). 선결 C1-C6)을 반영했다("확인 예정의 처리"). 마지막으로 px4-engineer가 남은 네 항목을 확인했고(px4-engineer 최종 확인(git 이력). 반대 없음) 그 결과를 반영해 확인 예정을 모두 닫았다. 감시 표의 순위만 재실측 (4) 전까지 잠정이다.

## 확정 개정 요약 (2026-11-11)

사용자 결정(호출한 쪽이 전달. 셋 다 architect 권고안)
- U1: 시나리오 D(공중 취소)와 `[LAND]` 한 항목 미션을 1a 필수에 넣는다.
- U2: `sitl`은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외, 옛 실행 취소)와 main push. lint와 unit의 trigger도 `pull_request` + `push: main`으로 맞춘다(P0).
- U3(reviewer가 올림): 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작은 1b로 미룬다. 1a 노드는 INVALID_MISSION으로 끝낸다. 5단계 사용자 결정 1의 "1a 완료에 `ExecuteMission`" 고정 범위에서 이 조각을 뺀 것으로 기록한다.

reviewer 필수 7건의 처리

| 번호 | 지적 | 처리 | 위치 |
| --- | --- | --- | --- |
| 1 | 공중에서 끝나는 미션을 미루는 것은 사용자 결정 1의 범위 변경이다 | U3으로 확정. 문서 반영 목록에 roadmap 16행, 31행과 architecture.md 고정 시점 문장을 더했다 | 계약 변경 절, 문서 반영 목록 |
| 2 | LAND 감시: 자동 disarm과 동시에 `nav_state`가 AUTO_LAND를 떠나 1회 이탈 규칙이 정상 착륙을 EXTERNAL_MODE_CHANGE로 끝낼 수 있다 | LAND의 모드 이탈 판정은 ARMED인 동안만 적용한다. DISARMED이고 landed이면 완료 계수가 우선한다. px4-engineer 승인 대상(2026-11-11 승인, 보강 셋 반영) | 쟁점 4 |
| 3 | M5의 의미 넓히기와 "상수는 나중에 더하면 된다"의 모순 | (나)를 골랐다. 고정 전인 지금 상수 `REASON_DISARM_FAILED = 13`을 더한다. REASON_MODE_SWITCH_FAILED의 의미는 넓히지 않는다 | 계약 변경 절 M5 |
| 4 | 지면 근접 취소(X2)의 "계속 내려앉아 disarm"은 확인된 사실이 아니다 | [추정]으로 내렸다. CANCELED 뒤 이어 보낸 `[LAND]`가 PRECONDITION_FAILED가 될 수 있음을 적었다. 7단계 고정 전 필수 재실측을 넘김 목록에 넣었다. 2026-11-11 실측으로 이륙 단계와 0.5 m 호버에서는 내려앉지 않음이 확인되어 문장을 고쳤다("px4-engineer 승인 반영") | 쟁점 3 M3, 넘김 목록 |
| 5 | 시간 추정에 실측이 없다 | P4 완료 기준에 15분과 RTF 0.7 기준, 넘으면 판정을 느슨하게 하지 않고 올린다. U2 기록에 미실측 표시. `wall_cap`과 RTF의 관계 | 쟁점 10, 11, README.md |
| 6 | 의견서의 음차 | devops-engineer 의견서(git 이력) 55, 152행과 ros2-engineer 의견서(git 이력) 99행의 "키"를 key로 고쳤다(내용은 그대로) | 의견서 |
| 7 | file-ownership.md 반영 목록의 누락 | snapshot 헤더, 패키지 `test/`, `px4_raw.py`의 px4 필수 승인, 전이 표와 타임아웃 기본값의 승인자를 더했다 | 문서 반영 목록 |

reviewer 권고 10건의 처리: 모두 받았다.

| 번호 | 권고 | 처리 |
| --- | --- | --- |
| 1 | ACCEPTED 누락: 구독을 action client보다 먼저 만드는 순서 규칙, 200회 누락 계수 실험 | 수용. 쟁점 7, P3a |
| 2 | on_activate의 `/clock` 2 s 대기는 벽시계다. 콜드 기동의 첫 `/clock` 수신 시간을 잰다 | 수용. 쟁점 2, P3a와 첫 CI 실행 |
| 3 | P3b 전에 ITEM_TIMEOUT 뒤 정리와 TAKEOFF 시작 조건을 닫는다. reason별 "ABORTED 뒤 기체 상태" 표 | 수용. 쟁점 4의 "P3b 착수 전 px4-engineer 승인 항목", 7단계 넘김 |
| 4 | 지상 arm 취소 분기에서 TAKEOFF 목표점 발행을 유지하면 이륙 의도가 켜진다 | 수용. 이 분기의 setpoint는 px4-engineer가 P3b 전에 명시한다(2026-11-11 지상 setpoint로 확정) |
| 5 | LAND 대비책 "`COM_DISARM_LAND` + 3 s"는 노드 파라미터로, 출처 표기 | 수용. 쟁점 10 `land_disarm_fallback_delay` |
| 6 | `executor_node` 이름의 출처를 하나로 | 수용. 생성기가 launch 인자로 넘긴다. 쟁점 2 |
| 7 | 문서 반영 목록의 누락 | 수용. 문서 반영 목록 |
| 8 | T의 대기 상한, `px4_raw.py`의 `vehicle_command`는 sysid 대조 뒤에만 | 수용. 쟁점 8, 9 |
| 9 | P3 완료 기준을 "39건"이 아니라 golden diff로 | 수용하되 M5 (나)에 맞췄다. README.md |
| 10 | 주석 수정 때 `test_contract.py`의 가드가 실패할 수 있다 | 수용. 쟁점 3 구현 지시 |

`CLAUDE.md` 담당자 표와 `.claude/agents/`의 세 파일(ros2, px4, test)의 `idsim_mission` 소유 반영은 architect가 하지 않았다(다른 에이전트가 전한 승인으로는 규칙 파일을 고치지 않는다). 사용자가 2026-11-11에 직접 승인했고 호출한 쪽이 "문서 반영 목록"의 문안대로 반영했다.

표기: [실측]은 담당자가 스택이나 이미지에서 직접 확인한 것(run id는 의견서), [소스]는 PX4 v1.17.0 원문이나 설치된 패키지 원문, [추정]은 확인하지 않은 판단이다. [추정]에 기대는 결정은 "reviewer가 검증할 가정"에 모았다.

용어: 이 문서의 "공중"은 `vehicle_land_detected.landed == false`, "지상"은 `landed == true`를 뜻한다. 기체의 높이가 아니라 PX4의 착륙 판정이다. position만 쓰는 Offboard나 Hold에서는 이륙 램프가 시작된 뒤 기체가 땅에 닿아 있어도 `landed`가 false로 남는다([실측] run 20261111-030155-k5의 H, X2a). 분기는 이 뜻으로 맞게 동작한다(공중 분기의 Hold는 받아들여진다).

## px4-engineer 승인 반영 (2026-11-11)

입력은 px4-engineer P3b 착수 전 승인 검토(git 이력)다. 확인 방법은 PX4 v1.17.0 태그 원문 대조와 스택 5 실측(run 20261111-030155-k5. 경우마다 1-3회, 16 vCPU 호스트)이다. 다섯 항목 중 승인 2건(2, 5), 수정 조건부 3건(1, 3, 4)이고 반대는 없다. 수정 조건은 모두 문장 수정이고 이 개정에 반영했다. 이것으로 쟁점 4의 "P3b 착수 전 px4-engineer 승인 항목"이 닫혔다. 반영은 PR #21로 main에 들어갔다. px4-engineer는 반영된 문장과 뒤의 개정을 2026-11-11에 다시 확인했다(px4-engineer PR #23 반영 확인(git 이력). "PR #23 검토 반영"). 실측이 없는 경로 둘(지상 setpoint 발행 중의 Hold, 이륙 직후 landed가 아직 true인 구간의 지상 setpoint와 disarm)은 닫힌 것이 아니고 필수 재실측 대상이다. P3b는 이 두 경로를 표대로 구현하되 재실측 결과로 바뀔 수 있다.

승인 항목 다섯

| 번호 | 항목 | 판정 | 반영한 것 | 위치 |
| --- | --- | --- | --- | --- |
| 1 | ITEM_TIMEOUT 뒤의 정리 | 수정 조건부 | (a) 지상 arm 분기는 지상 setpoint 규칙을 따른다. (b) LAND 항목의 ITEM_TIMEOUT 문장을 바꿨다. (c) Hold로 끝난 기체의 상태 한 줄. (d) arm 전송 뒤의 경쟁과 arm 재전송 중단을 정리 절차 전체에 적용 | 쟁점 4의 항목 표 아래, "끝난 뒤 기체 상태", 쟁점 3 M5 |
| 2 | TAKEOFF 시작 조건(지상이고 DISARMED만) | 승인 | 결정은 그대로다. 근거를 보강했다(실측 H, K) | 쟁점 4 PREPARING |
| 3 | 지상 arm 분기의 setpoint | 수정 조건부(문장 확정) | 지상 setpoint(그 tick의 위치에서 z만 +0.5 m, NED). 지상 arm 정리 전부에 쓴다. 0.5 m는 어댑터 상수 | 쟁점 3 M5 |
| 4 | LAND 감시의 세 구간 | 수정 조건부 | (a) AUTO_LAND 확인은 `failsafe` 값과 무관. (b) 확인 전 구간에도 발행 규칙 적용. (c) landed는 고정 규칙으로 읽는다 | 쟁점 4 LAND 감시 |
| 5 | 방어용 분류, landed 뒤의 disarm | 승인, 조건 하나 | disarm의 분류를 처음 관측한 DISARMED 표본의 tick에 고정한다 | 쟁점 4 비행 중 감시 |

px4-engineer가 정한 값(쟁점 6의 소유 규칙에 따라 그대로 채택): 타임아웃 기본값과 재전송 주기는 쟁점 10의 표, 명령별 재전송 규칙은 쟁점 4의 "명령 재전송 규칙"이다.

추가로 발견된 문제 다섯

| 번호 | 문제 | 처리 | 위치 |
| --- | --- | --- | --- |
| 1 | arm을 보낸 뒤 취소나 실패가 오면 snapshot이 아직 DISARMED일 수 있다. "지상 disarm이면 바로 끝"으로 발행을 멈추면 그 뒤 arm이 처리되어 기체가 지상에 armed로 남는다 | 수용. 이 goal에서 arm을 한 번이라도 보냈으면 지상 분기는 `arming_state`와 무관하게 disarm 분기를 거친다 | 쟁점 3 M3, M5 |
| 2 | arm 재전송을 멈추는 조건이 문서에 없다 | 수용. 취소나 실패를 정한 tick에 즉시 멈춘다 | 쟁점 4 P6, 명령 재전송 규칙 |
| 3 | 감시 표의 빈 칸: setpoint 항목 중 지상에서 DISARMED(TAKEOFF가 뜨기 전의 외부 disarm). 어떤 행에도 걸리지 않아 ITEM_TIMEOUT까지 발행이 이어진다 | 수용. 행을 더했다. reason은 아래 architect 결정(새 상수 `REASON_EXTERNAL_DISARM = 14`) | 쟁점 4 비행 중 감시 |
| 4 | 지면 근접 Hold의 [추정](내려앉아 disarm될 수 있다)이 실측과 반대다 | 쟁점 3 M3의 계약 문장 둘을 고쳤다. 필수 재실측을 다시 정했다(닫힌 것은 이륙 단계와 0.5 m 호버의 Hold이고, 새로 드러난 미실측 조합이 더해져 항목 수는 늘었다) | 쟁점 3 M3, 넘김 목록 |
| 5 | `landed`가 false인데 기체가 사실상 지상에 있는 상태가 있다 | 용어 주석을 넣었다 | 위 "용어" |

architect가 정한 것

- 추가 문제 3의 reason(reviewer 지적 뒤 다시 판단했다): 상수 `REASON_EXTERNAL_DISARM = 14`를 더한다. setpoint 항목 중 지상에서 Executor가 보내지 않은 disarm을 관측하면, `failsafe`가 true이면 REASON_FAILSAFE이고 아니면 REASON_EXTERNAL_DISARM이다. `detail`에 지상 disarm임을 적는다. 의미 문장: "setpoint 항목 실행 중에 Executor가 보내지 않은 disarm이 지상에서 failsafe 없이 관측됐다. 끝난 뒤 기체는 지상에 disarm 상태다. 원인은 판정하지 않는다(외부 명령뿐 아니라 PX4 자체의 disarm과 kill을 포함한다)". `failsafe` 가지의 정확한 조건은 쟁점 4 감시 표의 순위 5다(이 표본이나 이 항목 실행 중의 앞선 표본에서 `failsafe == true`를 봤으면 FAILSAFE). REASON_EXTERNAL_MODE_CHANGE의 의미는 넓히지 않는다(Executor가 요청하지 않은 모드 변화).
  - 앞 판(PR #21)의 결정은 "새 상수 없이 REASON_EXTERNAL_MODE_CHANGE"였고 근거 넷을 댔다. reviewer가 그 근거를 반박했고 받아들인다. 근거 2(상태는 `arming_state`와 `detail`로 읽힌다)와 근거 4(소비자가 없다)는 M5에도 똑같이 적용되어 M5의 상수 추가를 기각하는 논리다. 근거 1(다음 동작이 같다)은 틀렸다. 공중에서 모드가 바뀐 기체에는 TAKEOFF 미션이 PRECONDITION_FAILED이고, 지상에서 disarm된 기체는 TAKEOFF 미션을 받을 수 있다. 앞 판의 근거 넷을 철회한다.
  - 근거: M5 (나)에서 쓴 기준을 그대로 적용한다. (1) 끝난 뒤 기체 상태가 다르다(모드 변화는 보통 공중 armed, 이쪽은 지상 disarm). (2) 읽는 쪽의 다음 동작이 갈린다(위). (3) 한 상수에 묶어 1a에 고정하면 "상수의 의미를 바꾸지 않는다"에 걸려 뒤에 가를 수 없다. (4) 고정 전인 지금의 비용은 golden 두 파일에 한 줄씩이다. (5) 이름과 의미가 맞는다(mode change라는 이름에 disarm을 담지 않는다).
  - 기각: REASON_EXTERNAL_MODE_CHANGE 유지. "끝난 뒤 상태가 위험한가" 하나를 기준으로 삼으면 유지할 수 있다(지상 disarm은 안전한 쪽이다). 그러나 M5에 적은 기준은 위험 여부가 아니라 상태와 다음 동작의 차이였다. 결정을 지키려고 기준을 뒤에 좁히지 않는다. 상수는 고정 전후 모두 추가만 하므로 두 선택 다 되돌릴 수 없는데, 쓰이지 않는 구분은 해가 없고 묶인 의미는 영영 가를 수 없다.
  - 기각: 늘 REASON_FAILSAFE(공중 disarm 행과 대칭이지만 운용자가 지상에서 disarm한 것을 기체 이상으로 읽게 만든다), REASON_INTERNAL(Executor 내부 오류가 아니다).
  - 한계: "external"은 추론이다. Executor가 아는 것은 "`failsafe`가 false인데 Executor가 보내지 않은 disarm"뿐이고 원인은 모른다(`latest_disarming_reason`은 판정에 쓰지 않는다). REASON_EXTERNAL_MODE_CHANGE도 같은 수준의 추론이다. 의미 문장에는 원인이 아니라 관측을 적는다.
  - px4-engineer는 처음에 EXTERNAL_MODE_CHANGE를 제안했고 확인에서 그 제안을 철회하고 상수 추가를 승인했다(px4-engineer PR #23 반영 확인(git 이력) 2번. 다음 동작이 다르다는 같은 이유).
  - 이름에 남는 문제(7단계에 1a 고정 전 다시 본다): 의미 문장이 "원인은 판정하지 않는다"인데 이름은 external이다. 다시 볼 때의 시나리오로 `COM_DISARM_LAND` 자동 disarm을 넣는다(TAKEOFF가 뜬 뒤 어떤 이유로 지면에 내려앉아 PX4가 스스로 disarm한 경우. 외부 주체가 없는데 EXTERNAL_DISARM이 나온다).
- 지상 disarm 확인의 타임아웃 이름: `mode_confirm_timeout`을 그대로 쓴다. px4-engineer가 권고로만 낸 `disarm_confirm_timeout`은 만들지 않는다. 값이 같고(3 s) M5의 계약 문장이 이미 `mode_confirm_timeout`을 가리킨다. 값이 갈려야 할 실측이 나오면 그때 나눈다(노드 파라미터라 계약 변경이 아니다).
- 지상 setpoint와 발행 규칙의 관계(architect가 채운 문장. px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 3번 승인. 보강 문장은 쟁점 3 M5): 지상 setpoint로 바꿔 발행하는 것은 그 tick에 발행 중일 때뿐이다. 발행 규칙에 따라 이미 멈춘 발행(예: LAND 항목에서 AUTO_LAND를 관측한 뒤의 취소, Hold를 관측한 뒤 지상 판정이 올라간 경우)은 지상 arm 분기에서도 다시 켜지 않고 disarm만 재전송한다. Offboard가 아닌 모드에서 setpoint를 발행하지 않는다는 규칙이 앞선다.
- 감시 표의 행 우선순위(architect가 채운 문장. px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 2번 승인. 재실측 (4) 전까지는 잠정): 한 tick에 여러 행이 맞으면 순위가 앞선 행이 이긴다. 순위는 쟁점 4의 감시 표에 번호로 적었고 근거도 거기에 있다. 앞 판의 근거 "단위 테스트가 표와 한 줄씩 대조할 수 있게"는 순서가 있어야 하는 이유일 뿐 그 순서가 옳은 이유가 아니었다(reviewer). 철회한다.
- 필수 재실측의 X3(이륙한 적 없는 지상 armed에서 발행 중단)은 남긴다. 이번 run은 X3을 실측하지 않았고 추가 문제 1의 설명도 [소스]에 기댄다.
- "disarm 전송 뒤에 받은 표본"의 기준(px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 1번 승인과 보강, reviewer 필수 2 반영): 표본의 수신 tick이 이 분기의 첫 disarm 전송 tick보다 크고(tick 번호 비교. `수신 tick > 전송 tick`), `vehicle_status.timestamp`가 그 첫 전송에 실은 `Px4Timestamp`보다 엄격히 뒤(>)인 표본만 센다(두 조건 모두. 비교 대상은 재전송마다 새로 생기는 값이 아니라 첫 전송의 값이다). 3회 연속의 계수: 직전에 센 표본과 `timestamp`가 같은 표본은 건너뛴다(되돌리지도 더하지도 않는다. tick당 표본은 최대 1개이므로 같은 표본을 다음 tick에 다시 본 경우다). DISARMED가 아닌 표본은 계수를 0으로 되돌린다. `timestamp`가 줄어든 표본은 세지 않는다. 3회 연속은 서로 다른 `timestamp` 3개다. 두 값은 같은 축이다([소스] `vehicle_status.timestamp`는 `Commander.cpp` 1943행 근처에서 publish 직전의 `hrt_absolute_time()`이고 SITL lockstep에서 sim 시간이다).
  - 이 기준이 막는 것은 하나다. disarm이 처리되기 전의 DISARMED 표본을 세는 것. [소스] arm과 disarm은 같은 `vehicle_command` 토픽의 FIFO이고 Commander는 주기마다 하나씩 처리한다(`Commander.cpp` 1884-1898행). 늦게 도착한 arm이 disarm 뒤에 처리되는 일은 없다. 잘못 세려면 표본 간격 약 0.5 s의 3회 연속, 곧 약 1 s 동안 arm이 처리되지 않아야 한다.
  - "엄격히 뒤"는 방어층이다(px4-engineer 확인 2026-11-11, px4-engineer 최종 확인(git 이력) C2). [소스] `vehicle_status.timestamp`는 publish 직전의 `hrt_absolute_time()`이라 단조 증가한다. 같으면 같은 표본을 다시 본 것이고 줄어드는 것은 PX4 재시작이나 시계 되감김뿐이다. 전달 지연 동안 이미 publish된 표본이 "뒤" 조건을 만족할 수 있지만 그 표본이 DISARMED면 기체는 실제로 disarm 상태라 오판정이 아니다. 남는 위험은 늦게 처리된 arm 하나인데 위 FIFO 순서 때문에 disarm 뒤에 처리되는 arm은 없다.
  - 노드 시계의 지연: 크기는 [추정]이다. 앞 판이 적은 "[실측] 최대 180 ms"는 "노드 sim 시각 - `vehicle_status.timestamp`", 곧 받은 표본이 묵은 정도이지 노드 시계가 늦은 크기가 아니다(reviewer). 철회한다. 재실측 (5)에서 부호 있는 분포를 기록한다.

계약, golden, 상수에 주는 영향

- `REASON_*` 상수: 하나가 더 는다. `ExecuteMission.action`의 result에 `uint8 REASON_EXTERNAL_DISARM = 14`(`REASON_DISARM_FAILED = 13` 다음 줄, REASON_INTERNAL 앞). 6단계가 더하는 상수는 13과 14 둘이다. 필드는 바꾸지 않는다.
- golden: `golden/direct/action/ExecuteMission.txt`와 `golden/action/ExecuteMission.txt`에 각각 두 줄(13과 14)이 는다. 다른 golden과 `type_hashes.txt`는 그대로다. P3의 완료 기준은 "`git diff test/golden`이 이 두 파일의 두 줄씩 추가뿐"으로 바뀐다.
- M1, M2: 영향 없다.
- M3: 문장이 바뀐다(의미 변경, 고정 전). "CANCELED로 끝난 기체는 Hold이거나 지상 disarm이다"는 그대로이고, "지면 바로 위에서 취소되면 내려앉아 disarm될 수 있다"를 지우고 "Hold로 끝난 기체는 지면 근처여도 ARMED, landed false로 머문다(12 s 관찰)"로 바꾼다. `[LAND]`의 PRECONDITION_FAILED 가능성은 이륙 단계와 0.5 m 호버에 대해서는 실측과 맞지 않아 지웠고, 미확인 범위(쟁점 3 M3의 목록)에는 남아 있다. "지상 disarm이면 바로 CANCELED"에 "이 goal에서 arm을 보낸 적이 없을 때"라는 조건이 붙는다.
- M4: 계약 문장은 그대로다. 지상 arm 분기에서 넘어온 경우 지상 setpoint를 유지한 채 Hold를 보낸다는 절차가 더해진다.
- M5: 결과와 reason은 그대로다(REASON_DISARM_FAILED의 의미 문장도 그대로). 유지하는 setpoint가 지상 setpoint로 확정됐고, disarm 분기에 들어가는 조건이 "지상 arm"에서 "지상 arm이거나, 지상이고 이 goal에서 arm을 보낸 적이 있음"으로 넓어졌다. client가 보는 차이는 그 경우 CANCELED가 약 1 s 늦게 온다는 것뿐이다.
- 전이 표(M 번호 없음. 의미 변경, 고정 전): 감시 표에 지상 DISARMED 행(REASON_EXTERNAL_DISARM), 행 순위(잠정), disarm 분류의 고정 규칙, LAND 항목의 ITEM_TIMEOUT 문장.
- P3e의 범위: 상수 둘(`REASON_DISARM_FAILED = 13`, `REASON_EXTERNAL_DISARM = 14`)의 추가, M3의 고친 문장과 두 상수의 의미 주석, golden 두 파일 갱신.

## PR #21 reviewer 검증 반영 (2026-11-11)

PR #21(위 승인 반영)에 대한 reviewer 판정은 조건부였다(px4 보고의 반영 누락 없음, 새 음차 없음. 필수 5건, 권고 6건). PR #21은 그 조건이 반영되기 전에 main에 들어갔고, 이 절의 내용은 후속 PR(브랜치 `docs/1a-6-p3b-review`)로 반영한다.

사용자 결정(2026-11-11, 호출한 쪽이 전달)
- U4: replay job의 trigger는 지금 정하지 않는다. replay job을 만드는 Phase 2에서 정하고, `docs/architecture.md` 277행과 `docs/roadmap.md` 59행은 그때 고친다.
- U5: px4-engineer의 반영 확인은 이 개정이 끝난 뒤 다시 받는다. px4-engineer의 읽기 전용 확인은 앞으로 sonnet으로 받는다(px4-engineer의 기본 모델 opus의 예외. 사용자가 2026-11-11에 정한 일반 규칙이다. 실측과 구현, 설계 토론에는 적용하지 않는다). 확인은 2026-11-11에 끝났고(px4-engineer PR #23 반영 확인(git 이력)) 결과는 "PR #23 검토 반영"에 있다.

필수 5건의 처리

| 번호 | 지적 | 처리 | 위치 |
| --- | --- | --- | --- |
| 1 | 실측이 없는 두 조합이 닫힘으로 적혀 있다. (a) 지상 setpoint 발행 중에 보낸 Hold(H의 정리는 NAV_LAND였고 X2a는 TAKEOFF 목표점 발행 중의 Hold였다). (b) 목표점 발행 중이고 `landed`가 아직 true인 구간(첫 ARMED 뒤 약 0-1.3 s)에서 지상 setpoint로 바꾸고 disarm(G는 처음부터 지상 setpoint, H는 이미 landed false). (b)가 "이륙 직후 취소"의 정상 경로다 | M5의 H 문장을 "Hold는 미실측"으로 고쳤다. 필수 재실측에 둘을 더했다. P3b는 두 경로를 표대로 구현하되 재실측 결과로 바뀔 수 있다고 표시했다 | 쟁점 3 M5, 넘김 목록, 구현 지시 |
| 2 | M3 계약 문장이 실측 범위를 넘는다("AUTO_LAND 하강 중 0.3 m 아래 취소만 미확인") | "만"을 지우고 미확인 목록을 적었다. Hold 종료 경로의 표본을 X2a 1.8 s 1회와 X2b 1회로 고쳤다. NAV_LAND 5회를 Hold 상태 3회와 H 2회로 갈랐다. 표와 알림 줄에 "12 s 관찰, 스크립트 명령"을 붙였다. 재실측 관찰은 60 s 이상 | 계약 변경 표 M3, 쟁점 3 M3, 끝난 뒤 기체 상태, 사용자에게 알릴 것, 넘김 목록 |
| 3 | "모든 push"가 P0 뒤 틀린 문장인 것은 `docs/architecture.md` 276행(단위)뿐이다. 277행(리플레이)과 `docs/roadmap.md` 59행은 아직 없는 replay job의 계획이라 U2 범위 밖이다 | 276행만 P4 문서 반영 목록에 남겼다. 277행과 59행은 U4에 따라 Phase 2로 넘겼다. 274행 표 머리의 음차를 P4에서 함께 고치도록 적었다 | 문서 반영 목록, 넘김 목록 |
| 4 | 감시 표의 "위 행 우선"은 근거가 순서를 정당화하지 못한다. 식별 불일치 행이 아래라 FAILSAFE가 먼저 나갈 수 있다. 지상 외부 disarm 뒤 `nav_state`가 OFFBOARD로 남는다는 것은 근거가 없다 | 행 순위를 다시 정했다(입력을 믿을 수 없게 하는 행, arming 상태 행, 모드 행 순). 잠정으로 표시하고 확인 실험을 재실측에 넣었다 | 쟁점 4 비행 중 감시, 넘김 목록 |
| 5 | 추가 문제 3의 근거 2, 4는 M5의 상수도 기각하는 논리이고 근거 1은 불완전하다 | 결정을 바꿨다. 상수 `REASON_EXTERNAL_DISARM = 14`를 더한다. golden은 두 파일에 두 줄씩 | "px4-engineer 승인 반영"의 architect 결정, 계약 변경 절 |

권고 6건의 처리

| 번호 | 권고 | 처리 |
| --- | --- | --- |
| 1 | 재실측의 "좁혔다"는 범위가 늘었으니 고친다. arm 전송 직후 취소의 경쟁을 재실측에 더한다. 실측 스크립트를 저장소에 둘지 | 수용. "다시 정했다"로 고쳤다. 경쟁 실측을 더했다. 스크립트의 보관은 px4-engineer와 test-engineer가 정하도록 넘김 목록에 적었다 |
| 2 | "arm을 한 번이라도 보냈으면"의 파급을 단위 테스트로 | 수용. test-engineer 구현 지시에 셋을 적었다. "disarm 전송 뒤 받은 표본"의 기준을 한 줄로 정했다(잠정). ITEM_TIMEOUT의 지상 disarm 분기는 1a에서 닿지 않으므로 전용 테스트를 요구하지 않는다 |
| 3 | LAND 항목 ITEM_TIMEOUT 문장에 `[LAND]` 단독 미션의 예외 | 수용. 단서를 달았다 |
| 4 | 재전송 표의 NAV_LAND 행과 LAND 대비책 disarm의 타임아웃 | 수용. 채웠다(architect가 채운 문장. px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 5번 승인) |
| 5 | 쟁점 10 표 앞 다섯 행의 근거 출처 | 수용. px4-engineer 의견서(git 이력)의 절 번호를 적었다 |
| 6 | README의 "P1 진행 중" | 사실이라 그대로 둔다 |

## PR #23 검토 반영 (2026-11-11)

PR #23(위 reviewer 검증 반영)에 검토 둘이 왔고 같은 PR에 반영했다.

px4-engineer 확인(px4-engineer PR #23 반영 확인(git 이력). U5. 이 확인은 사용자 결정으로 sonnet으로 받는다(px4-engineer의 기본 모델 opus의 예외. 사용자가 2026-11-11에 직접 골랐다)): 승인 3건, 수정 조건부 2건, 반대 없음. PX4 v1.17.0 태그 원문 대조이고 새 실측은 없다. 이것으로 앞 개정의 확인 예정 표시를 모두 닫았다. 감시 표의 순위만 재실측 (4) 전까지 잠정으로 남는다.

| 번호 | 대상 | 판정 | 반영 |
| --- | --- | --- | --- |
| 1 | "disarm 전송 뒤 받은 표본"의 기준 | 승인, 보강 둘 | 엄격 부등호, 같은 timestamp는 한 번, 근거를 [소스] FIFO와 표본 간격으로 |
| 2 | `REASON_EXTERNAL_DISARM = 14`와 감시 표 순위 | 상수와 순위는 승인. 순위 5의 `failsafe` 가지는 수정 조건부 | 순위 5의 조건을 "이 항목 실행 중 failsafe나 OFFBOARD 이탈을 한 번이라도 봤으면 FAILSAFE"로. 의미 문장에 "원인은 판정하지 않는다" |
| 3 | 지상 setpoint는 발행 중일 때만, 멈춘 발행은 다시 켜지 않음 | 승인, 보강 한 문장 | 불변식과 적용 대상이 아닌 경우를 적었다 |
| 4 | `[LAND]` 단독 미션의 ITEM_TIMEOUT 단서 | 수정 조건부 | 문장을 바꿨다(DESCEND 포함) |
| 5 | 재전송 표 | 승인 | Hold 행의 타임아웃이 `hold_confirm_timeout`임을 적었다. 대비책 disarm의 시작 조건을 적었다 |

- px4-engineer의 정정: 앞 보고의 "지상 외부 disarm 뒤 `nav_state`가 OFFBOARD로 남는다"는 [소스]에 기댄 추정이었다. 실측 전에는 사실로 쓰지 않는다(쟁점 4 감시 표의 지상 DISARMED 행).
- 필수 재실측에 셋을 더했다(넘김 목록의 (2), (4), (5)).

reviewer(조건부. 필수 3건)

| 번호 | 지적 | 처리 |
| --- | --- | --- |
| 1 | 쟁점 3 구현 지시의 golden "한 줄씩" | "두 줄씩"으로 고쳤다 |
| 2 | 표본 기준의 한계 설명이 180 ms 실측을 잘못 읽었다. 기준이 test 지시 (3)과 어긋난다 | 지연 크기를 [추정]으로 내리고 재실측 (5)에 분포 기록을 넣었다. 기준을 "첫 disarm 전송 tick 뒤에 받음"과 "timestamp가 엄격히 뒤"의 AND로 통일했다 |
| 3 | U5의 모델 예외를 기록 | 이 문서 두 곳과 `progress.md` 결정 기록에 적었다 |

reviewer 권고의 처리
- 순위는 같은 tick의 동률만 가른다는 한 줄과, 엇갈려 시작하는 경우의 테스트: 수용(쟁점 4 감시 표, test 지시).
- REASON_EXTERNAL_DISARM의 이름을 다시 볼 때 `COM_DISARM_LAND` 자동 disarm 시나리오: 수용(위 architect 결정, 넘김 목록).
- snapshot에 `vehicle_status.timestamp`와 명령 시각이 넘어와야 한다: 수용(쟁점 6의 snapshot 승인 대상).
- README의 사용자 결정 표기에 U4, U5: 수용.
- 13과 14를 다른 브랜치가 쓰는지 P3e 전에 확인: 수용(architect 구현 지시).
- 재실측 (2)-(5)를 P3 머지 조건으로 올릴지: 올리지 않는다. (2), (3), (5)는 P4 머지 조건으로 둔다. (4)와 나머지는 7단계 고정 전이다.
  - P3 머지 조건으로 두지 않는 이유: P3이 합쳐져도 Executor는 어떤 스택에서도 기본으로 뜨지 않는다(`ops-N` 서비스와 `sim_stack.sh`의 노드 단계는 P4다). P3의 단위 테스트는 표와 구현의 일치를 볼 뿐 표와 PX4의 일치는 보지 못하므로, 재실측이 표를 바꾸면 고치는 비용은 P3 머지 전이나 뒤나 같다. 반대로 P3을 묶으면 P4까지의 사슬 전체가 px4-engineer의 실측 일정에 걸린다.
  - (2), (3), (5)를 P4 머지 조건으로 두는 이유: P4부터 `tools/sim_stack.sh up`이 Executor를 띄우고 사람이 goal과 취소를 보낼 수 있다. 세 항목은 이륙 직후 취소가 지나는 경로이고, 틀리면 기체가 지상에 armed로 남거나 떠오른다. 시나리오 D는 5 m에서 취소하므로 통합 테스트는 이 경로를 지나지 않는다. 그래서 테스트 통과가 아니라 실측이 근거여야 한다.
  - (4)를 P4 조건에서 뺀 이유: 결과가 바꾸는 것은 reason의 분류이고 기체 동작(발행 중단, ABORTED)은 순위와 무관하게 같다.

## P3a 결과 반영 (2026-11-11)

입력은 P3a 실행 확인 결과(git 이력)다(ros2-engineer, 스택 6 run 20261111-030924-k6, launch_ros 0.26.13).

| 항목 | 결과 | 처리 |
| --- | --- | --- |
| 컨테이너 autostart | [실측] `component_container_isolated` + `ComposableLifecycleNode(autostart=True)`는 노드를 load하지만 CONFIGURE를 걸지 못해 `unconfigured`에 남는다(5/5, 오류 로그 없음). [소스] `load_composable_nodes.py`가 FQN을 `/px4_1mission_executor`로 만들고 `ChangeState`의 matcher가 어느 네임스페이스에서도 맞지 않는다 | 쟁점 2의 전제가 깨졌다. 다시 결정했다(아래) |
| 대안 A. 컨테이너 유지 + 노드의 자기 전이 | [실측] 스택에서 10/10 active, 프로세스 시작부터 0.30-0.64 s | 채택 |
| 대안 B. 단독 실행 파일 + `launch_ros.actions.LifecycleNode(autostart=True)` | [실측] 스택에서 10/10 active, 0.28-0.60 s | 기각(쟁점 2) |
| 실패 시 동작 | [실측] configure FAILURE, configure 예외, activate FAILURE 모두 노드는 `unconfigured`나 `inactive`에 머물고 프로세스와 launch는 산다 | 그대로 둔다(쟁점 2) |
| healthcheck | [실측] `ros2 lifecycle get --no-daemon`의 출력은 `active [3]` 형식이고 `docker exec`로 3.0-4.5 s 걸린다(20회) | `active`로 시작하는지 판정은 성립. timeout은 10 s 이상(devops 지시) |
| `/**` params | [실측] 컨테이너 노드와 단독 노드 모두에 적용된다. 선언하지 않은 key는 무시되고 `vehicle.id` 누락은 configure FAILURE다 | 결정 그대로. reviewer 판정표 9행 |
| 첫 `/clock` | [실측] 프로세스 시작부터 최대 0.66 s. on_activate에 들어갈 때는 이미 시작되어 있어 실제 대기는 20/20 0 s. `/clock`이 없으면 2.000 s 뒤 FAILURE | 2 s 그대로. CI 첫 실행에서 다시 잰다 |
| ACCEPTED 누락 | [실측] 실험군(구독 -> client -> 즉시 goal) 0/400. 대조군(client -> 구독) 87/400. 누락 87건은 모두 Executor 쪽 `get_subscription_count()`가 0이었고, 구독 쪽 `get_publisher_count()`는 800회 모두 1 이상이었다 | 쟁점 7 유지, 보강 |
| PID 1의 신호 | [실측] `init` 없이 PID 1인 launch는 SIGTERM을 무시해 15 s 뒤 SIGKILL된다. `init: true`이면 SIGTERM에 0.4-0.5 s 만에 끝나지만 launch의 정리 로그가 없다. SIGINT는 `init` 유무와 무관하게 1.7 s에 정리 로그를 남기고 exit 1(각 1-2회) | devops 지시(`init: true`와 `stop_signal: SIGINT`) |

쟁점 2의 재결정: A를 고른다. 내용과 근거는 쟁점 2에 있다. 함께 정한 것은 셋이다.
- 자기 전이가 실패하면 프로세스를 끝내지 않고 노드를 그 상태(`unconfigured` 또는 `inactive`)에 남긴다. 재시도하지 않는다. compose healthcheck가 잡는다.
- 끄는 param은 `lifecycle.self_start`(bool, 기본 true, 읽기 전용)다. 생성기는 이 key를 만들지 않는다. 단위 테스트와 배선 테스트는 false로 둔다.
- 앞 판이 미리 정해 둔 물러설 자리(단독 실행 파일이 `main`에서 전이)로는 가지 않는다. 그 문장은 컨테이너를 지키는 대안이 없다고 보고 쓴 것이고, A가 실측으로 성립했다.

## 쟁점 2 재결정의 검토 반영 (2026-11-11)

devops-engineer 의견(devops-engineer 쟁점 2 재결정 검토(git 이력). 읽기 전용 검토, 반대 없음). 받은 것은 쟁점 2와 devops 구현 지시, README의 P4 완료 기준에 넣었다.

| 항목 | 내용 | 반영 |
| --- | --- | --- |
| healthcheck 값 | `interval` 10s, `timeout` 10s, `retries` 2, `start_period` 20s, `start_interval` 2s. 명령 안쪽에 `timeout 8`. 출력을 버리지 않는다(`.State.Health.Log`에 상태가 남는다) | 채택. 쟁점 2 |
| 실패가 드러나기까지의 상한 | 컨테이너 시작부터 약 54 s, 모든 probe가 timeout까지 가는 최악 70 s([추정]. probe의 직렬 동작은 기억에 기댄다) | 채택. P4에서 결함 주입으로 잰다 |
| `stop_grace_period` | 10s. `sim_stack.sh`와 `run_smoke.sh`의 `down --timeout 10`이 서비스 값보다 우선하므로 하나로 맞춘다 | 채택(앞 판의 15s를 고친다) |
| exit code | 컨테이너 exit code를 판정에 쓰지 않는다. stop 전에 `compose ps -a`를 기록해 실행 중 사망과 정상 정리를 순서로 가른다 | 채택. reviewer 필수 2와 합쳤다 |
| 다른 서비스의 신호 | bridge(`ros2 run`의 python)와 xrce-agent는 PID 1이라 SIGTERM을 버린다([소스] 떠 있는 스택의 신호 마스크. down 시간은 미측정). 상주 ros-ws 서비스와 xrce-agent에 `init: true` | 채택. P4 같은 PR, 생성기 golden 4종 |
| runner | wrapper의 `timeout`이 보내는 SIGTERM이 PID 1인 pytest에서 버려질 수 있다([추정]) | P4에서 1회 확인하고 `init: true` 또는 `timeout -s INT -k 30` |
| 생성기 성질 테스트 | 상주 ros-ws 서비스는 모두 `init: true`. `ops-N`은 `stop_signal: SIGINT`와 `stop_grace_period: 10s`. params 파일에 `lifecycle.`로 시작하는 key가 없다. healthcheck의 FQN이 `stack.json`의 `executor_node`와 같다 | 채택 |
| ERROR 로그 | 자기 전이 실패 로그는 grep할 수 있는 고정 접두어의 한 줄 | 채택. 쟁점 2 |
| 표시 파일 | 지금은 필요 없다. 다시 볼 조건: CI에서 probe 평균이 7 s를 넘거나 probe 부하로 RTF가 0.7 기준에 걸릴 때 | 채택(두지 않는다) |

reviewer 최종 확인(조건부. 필수 3건). 앞선 조건(golden 두 줄씩, disarm 표본의 AND 기준, U5의 모델 예외)과 px4-engineer 확인의 반영은 확인됐고, P3a 실행 확인 결과(git 이력)의 launch_ros 원인 분석은 이미지의 소스(0.26.13, `load_composable_nodes.py` 245행, `matches_node_name.py`)와 일치했다.

| 번호 | 지적 | 처리 |
| --- | --- | --- |
| 1 | 감시 표 순위 5의 "OFFBOARD가 아닌 표본을 본 적"은 앞선 표본에서 생길 수 없다(순위 6-8이 한 표본으로 goal을 끝낸다). 지금의 DISARMED 표본을 이력에 넣는지 정해야 한다 | 넣지 않는다. 살아 있는 경우를 적고 잠정으로 표시했다(뒤에 px4-engineer가 승인해 닫혔다. "확인 예정의 처리"). 쟁점 4 |
| 2 | exit 1 허용이 넓다(launch 인자 누락도 rc 1). `stop_signal`의 이유 문장이 `init: true` 구성과 맞지 않는다 | exit 1을 보아 넘기는 것은 stop을 요청한 뒤에 한정했다. 이유 문장을 `init: true` 구성의 실측으로 바꿨다. P4 검증의 회수와 조건을 적었다 |
| 3 | 자기 전이 일회 timer의 시계가 적혀 있지 않다 | 벽시계 일회 timer로 정했다. 벽시계 예외 목록에 넣었다. P3a 시험 코드도 벽시계 timer였다(ros2-engineer 확인. "확인 예정의 처리") |

reviewer 권고의 처리: 모두 받았다. 재실측 (5)의 회수, 통과 기준, 결과 파일, 판정자(넘김 목록). 실측 스크립트의 저장 위치는 P4 선행 조건(`progress.md` 미해결). test 지시에 "test-engineer 확인 예정". goal 실행 중 stop의 종료 사건 수신 여부를 P4 stop 검증에. 쟁점 7의 기전 문장과 0/400의 상한. 결정 요약의 "launch autostart는 Jazzy에서"를 "컨테이너 autostart는 launch_ros 0.26.13에서"로. P3a 실행 확인 결과(git 이력)의 upstream rolling 문장에 [미확인]. 음차 표기 셋을 이 문서와 P3a 실행 확인 결과(git 이력), README에서 고쳤다(px4-engineer 근거 파일은 원문 그대로 둔다).

## 확인 예정의 처리 (2026-11-11)

앞 개정이 남긴 확인 예정 셋이 모두 닫혔다. px4-engineer 몫은 이 절을 쓰는 동안 넷으로 늘었고(순위 5의 이력 문장, OFFBOARD이고 ARMED인 채 failsafe가 true인 표본, 지상 disarm 분기의 LINK_LOST, DISARM의 그 밖의 거부 ack) 마지막에 확인을 받았다(아래 "px4-engineer 최종 확인").

ros2-engineer(닫힘): P3a 시험 코드의 자기 전이는 `create_wall_timer(0 ms)`였다. `/clock`이 없는 실행에서도 fire해 configure가 성공했고 activate는 2.000 s 뒤 FAILURE였다. 결정에 반대가 없다. 노드 시계 timer면 `/clock`의 부재를 configure 실패와 구분하지 못한다. 주의 둘을 쟁점 2에 넣었다(콜백 첫 줄의 `cancel()`, on_activate가 executor를 막는 동안의 `/clock` 수신).

test-engineer(test-engineer P3 조건부 승인(git 이력). 조건부 승인. 선결 C1-C6). C1-C5를 반영했으므로 P3 단위 테스트 목록의 "test-engineer 확인 예정"을 닫는다.

| 번호 | 조건 | 처리 | 위치 |
| --- | --- | --- | --- |
| C1 | core 입력 계약 | 문장 그대로 넣었다 | 쟁점 6 |
| C2 | "전송 뒤에 받은" 기준의 셋(첫 전송의 `Px4Timestamp`, tick 번호 비교, 3회 연속의 계수 규칙) | 넣었다 | "px4-engineer 승인 반영", 쟁점 3 M5 |
| C3 | 감시 표의 행별 3회/1회 | 순위 1, 2, 4-8은 1회, 순위 3은 시간 누적이라고 적었다 | 쟁점 4 비행 중 감시 |
| C4 | 지상 disarm 분기의 LINK_LOST, TEMPORARILY_REJECTED가 아닌 거부 ack, 재전송 표의 "같다" | architect 결정(아래) | 쟁점 3 M5, 쟁점 4 재전송 표 |
| C5 | 같은 tick의 종료 충돌 | architect 결정(아래) | 쟁점 3 "종료의 충돌 규칙" |
| C6 | 측정 스크립트의 위치 | `tests/sitl/measure/`(소유 test-engineer, 절차의 필수 승인자 px4-engineer). 넘김 목록의 미결을 닫았다. P4 선행 조건 | 넘김 목록, 문서 반영 목록 |

architect가 정한 것

- C4 지상 disarm 분기의 LINK_LOST: 지상 disarm 분기에서 `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 끝낸다. 취소 중이었으면 ABORTED, REASON_LINK_LOST다. PREPARING 실패나 ITEM_TIMEOUT의 정리 중이었으면 원래 reason을 유지하고 `detail`에 상태 끊김과 disarm 미확인을 적는다. 공중 분기(M4)의 LINK_LOST와 같은 규칙이다. `link_timeout`(2 s)이 `mode_confirm_timeout`(3 s)보다 짧으므로 표본이 아예 없으면 LINK_LOST가 먼저이고, 표본은 오는데 기준을 만족하는 DISARMED가 차지 않으면 REASON_DISARM_FAILED다. 발행 중단 시점을 정하는 문장이라 px4-engineer 확인을 받았다(승인. 아래).
- C4 DISARM의 그 밖의 거부 ack(DENIED 등): 그 자리에서 끝내지 않는다. `landed`가 true인 동안 재전송을 이어 가고 `mode_confirm_timeout`에 REASON_DISARM_FAILED(정리 중이었으면 원래 reason)로 끝내며 마지막 ack의 결과를 `detail`에 적는다. 이유: 성공의 판정은 ack가 아니라 `arming_state`다. 일찍 끝내도 기체는 arm으로 남을 뿐이라 얻는 것이 없고, 3 s 안의 재전송이 받아들여질 수 있다. ARM은 다르다(거부되면 일찍 끝내도 기체가 지상 disarm이라 안전하다). px4-engineer 확인을 받았다(동작 승인. 아래).
- C4 재전송 표의 "같다": NAV_LAND(M4의 Land 경로)는 NAV_LAND(LAND 항목) 행과 같다는 뜻이고(force라 거부가 없다), DISARM(LAND 대비책)은 DISARM(지상 arm 분기) 행과 같다는 뜻이다. ARM 행을 가리키지 않는다. 표에 풀어 적었다.
- C5 종료의 충돌: test-engineer의 권고를 받았다. 종료는 먼저 정해진 것이 이긴다. 같은 tick이면 ABORTED 사유, 완료, 취소 순이다. 종료 뒤의 cancel은 무시한다. 세부는 쟁점 3에 있다.
- test-engineer P3 조건부 승인(git 이력) 2절 (ii)의 의도 확인: OFFBOARD이고 ARMED인 채 `failsafe == true`인 표본은 어느 행에도 걸리지 않고 goal을 끝내지 않는다. 표대로가 의도다. "failsafe를 보면 즉시 멈춘다"는 문장이 가리킨 것은 failsafe로 OFFBOARD를 벗어난 표본(순위 6)이고, 문장을 그렇게 고쳤다. 근거: 발행 규칙은 `nav_state`가 OFFBOARD인 동안 발행하는 것이고, 발행을 멈춰야 하는 이유(멈추지 않으면 failsafe Land 중인 기체가 Offboard로 돌아간다)는 OFFBOARD를 벗어난 뒤에만 생긴다. [소스]로는 이 조합이 정상 상태에서 나오지 않는다(None과 Warn이 아니면 failsafe 동작이 모드를 바꾼다). 그 표본의 `failsafe`는 순위 5의 이력에 기록된다. px4-engineer 확인을 받았다(승인. v1.17.0에서는 이 조합이 나오지 않아 이력 가지는 방어용이다. 아래).
- on_activate의 `/clock` 대기(2 s)는 배선 테스트용 param으로 만들지 않는다. 벽시계 예외 그대로 두고, 배선 테스트는 가짜 PX4 발행자와 함께 `/clock`을 발행한다.

test-engineer가 더한 테스트와 P4 기록 방법은 담당자별 구현 지시(test-engineer)와 README의 P4 완료 기준에 넣었다.

px4-engineer 최종 확인(px4-engineer 최종 확인(git 이력). PX4 v1.17.0 원문 대조, 새 실측 없음. 반대 없음). 이것으로 px4-engineer 확인 예정을 모두 닫는다. 감시 표 순위의 "재실측 (4) 전까지 잠정"은 그대로다.

| 번호 | 대상 | 판정 | 반영 |
| --- | --- | --- | --- |
| 1 | 순위 5의 이력 문장 | 승인(문장 그대로). 설명 정정 | "살아 있는 경우" 설명을 px4-engineer 문장으로 바꿨다. 이력 가지는 v1.17.0에서 닿지 않는 방어용이고 테스트는 합성 표본으로만 한다. "덮지 못하는 경우"는 노드가 순위 6의 표본을 놓쳤을 때뿐이다 |
| 2 | OFFBOARD이고 ARMED인 채 failsafe가 true인 표본은 goal을 끝내지 않는다 | 승인 | 근거에 "예외는 Disarm과 Terminate"를 더했다. 나왔다면 계속하는 것이 안전하다 |
| 3 | 지상 disarm 분기의 LINK_LOST | 승인 | 강제 disarm을 쓰지 않는다는 조건을 적었다 |
| 4 | DISARM의 그 밖의 거부 ack | 수정 조건부(동작 승인) | [소스] 문장을 더했다. ARM 행의 그 밖의 거부도 방어용이다. 테스트는 합성 ack로만 한다 |
| C5 | 종료의 충돌 규칙 | 문제 없음 | 전제(종료 시점에 발행이 멈추고 명령 재전송이 지워져 있다)를 적었다 |
| C2 | "전송 뒤에 받은" 기준 | 문제 없음 | FIFO 논거 한 줄을 더했다 |

- 재실측 (4)에 선택 항목 하나를 더했다(failsafe 동작이 Disarm인 경로).
- 사용자 결정(2026-11-11): px4-engineer의 읽기 전용 확인은 앞으로 sonnet으로 받는다. U5를 이 일반 규칙으로 고쳐 적었다.

## 결정 요약

| 쟁점 | 결정 | 계약 변경 |
| --- | --- | --- |
| 1. 스택 기동 주체 | 호스트 wrapper `tests/sitl/run_sitl.sh`가 올리고 내린다. pytest는 `runner` 안에서 돌고 fixture는 붙기만 한다 | 없음(architecture.md 문장 수정) |
| 2. 노드 실행 형태 | 기체당 서비스 `ops-N`. 정적 launch로 `component_container_isolated`에 Executor 컴포넌트를 load하고, 노드가 스스로 configure와 activate를 건다(`lifecycle.self_start`. 컨테이너 autostart는 launch_ros 0.26.13에서 동작하지 않는다. P3a). params는 `params/ops-N.yaml`의 `/**`에 식별값만. 스모크는 `--infra-only` | 없음 |
| 3. 5단계 계약 | 의미 문장 넷(M1-M4)을 고치고 상수 둘(`REASON_DISARM_FAILED = 13`은 M5, `REASON_EXTERNAL_DISARM = 14`는 감시 표의 지상 DISARMED 행)을 더한다 | M1-M4는 의미 변경(고정 전), golden 무변경. 상수 둘은 `ExecuteMission`의 직접 정의와 펼친 정의 golden에 두 줄씩 추가, type hash 무변경 |
| 4. PX4 실측 사실 | 전부 채택. 전이 표로 고정 | 의미 변경(고정 전), golden 무변경 |
| 5. `idsim_common` 추가 | `VehicleId`, vehicle params 해석, Options overload, position setpoint 헬퍼, 사건 QoS, 빌더 `make` | 없음 |
| 6. `idsim_mission` 소유 | ros2-engineer. `px4/` 디렉터리 셋만 px4-engineer. 상태기 전이 표는 px4-engineer 필수 승인 | 없음(file-ownership.md) |
| 7. `MissionEvent` QoS | VOLATILE 유지. goal 전 gate는 자기 구독의 `get_publisher_count()` | 없음 |
| 8. 테스트의 /fmu/in | Python, `tests/support/px4_raw.py` 한 모듈만. 별도 C++ 노드는 두지 않는다 | 없음 |
| 9. 시나리오 | B, C, A, D, T 순서. 다섯 모두 1a 필수(U1). `[LAND]` 한 항목 미션 지원 | 없음 |
| 10. 타임아웃 | px4 값 채택. 벽시계 가드는 `CLOCK_STALLED`와 `CLOCK_SLOW`로 분류 | 없음 |
| 11. CI `sitl` | `sitl.yml`, timeout 30분, 재시도 없음. PR 머리 커밋마다와 main push(U2) | 없음 |
| 12. viz | foxglove_bridge는 단독 선행 이미지 PR. 화이트리스트는 네임스페이스 접두. Lichtblick 1.30.0 digest. recorder는 1a에 두지 않는다 | 없음 |
| 13. PR 분할 | P0-P5 여섯 개. README.md | - |

## 계약 변경 여부와 golden 영향 (먼저 읽을 것)

- 필드는 바꾸지 않는다. type hash golden(`type_hashes.txt`)은 그대로여야 한다([실측] 5단계: 상수는 hash에 들어가지 않는다).
- 상수 둘을 더한다: `ExecuteMission.action`의 result에 `uint8 REASON_DISARM_FAILED = 13`(M5. REASON_PRECONDITION_FAILED 다음 줄)과 `uint8 REASON_EXTERNAL_DISARM = 14`(2026-11-11 추가. 그다음 줄, REASON_INTERNAL 앞). 바뀌는 golden은 `golden/direct/action/ExecuteMission.txt`와 `golden/action/ExecuteMission.txt` 둘이고 각각 두 줄이 늘어난다. 다른 golden은 그대로다. P3의 완료 기준은 "`git diff test/golden`이 이 두 파일의 두 줄씩 추가뿐"이다.
- 이 변경의 절차 근거(5단계 `decisions.md`): 110행 "상수는 고정 전후 모두 추가만 한다. 상수의 의미는 그 상수를 처음 쓰는 소비자가 생기는 묶음과 함께 고정된다", 112행 "고정 전에는 첫 소비자의 구현에서 드러난 문제가 변경 사유로 인정된다", 598행(필드와 의미의 변경 규칙. 고정 여부는 파일 단위, 판정은 직접 정의 golden), 630행(지상 취소에서 disarm이 거부되거나 확인되지 않을 때의 분기를 6단계 px4-engineer에 넘김), 680행(Hold 실패와 지상 disarm 정책은 6단계 실험 결과에 따라 1a 고정 전에 바뀔 수 있다고 사용자에게 알림). `ExecuteMission.action`은 아직 고정 전이고 첫 소비자(6단계 Executor)의 설계에서 드러난 분기다.
- M5에서 (가) "REASON_MODE_SWITCH_FAILED의 의미를 넓히고 뒤에 가르지 않는다"가 아니라 (나) 상수 추가를 고른 이유: 두 경우는 ABORTED 뒤의 기체 상태가 다르다. Hold 실패는 Executor가 Land를 보내 기체가 내려오는 중이고, 지상 disarm 실패는 기체가 지상에 arm 상태로 남는다. 읽는 쪽(Fleet, 운용자)의 다음 동작이 갈린다. (가)로 가면 1a에 고정된 뒤에는 "상수의 의미를 바꾸지 않는다"에 걸려 영영 가를 수 없다. 앞 판의 "상수는 나중에 더하면 된다"는 논리는 이 점에서 틀렸으므로 철회한다(나중에 더하면 기존 상수의 의미가 좁아진다). 고정 전인 지금은 golden 두 줄의 비용뿐이다.
- 나머지(M1-M4와 전이 표)는 의미 변경(고정 전)이고 golden은 바뀌지 않는다. 반영할 곳은 `ExecuteMission.action`의 주석(주석은 직접 정의 golden에 들어가지 않는다), 7단계 `docs/interface.md`, `docs/architecture.md` 인터페이스 계약 절이다.
- 계약 golden이 바뀌는 PR(P3)에는 architect 승인이 필요하고 결정 근거는 PR 본문에 적는다(file-ownership.md). `docs/interface.md`는 7단계에 만들어지므로 그때 반영한다.
- `last_item_index`의 "항목 시작 전 실패" 구분 필드(5단계에서 6단계로 넘긴 검토 항목): 의견서 넷 어디에서도 필요가 나오지 않았다. 더하지 않는다. P3 구현이 끝날 때 한 번 더 확인하고 7단계에서 닫는다.

변경 다섯 건(쟁점 3에 근거).

| 번호 | 5단계 문장 | 6단계 결정 |
| --- | --- | --- |
| M1 | 즉시 abort되는 goal(BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION, NOT_READY)은 feedback 0건 | feedback 0건이 보장되는 것은 VEHICLE_ID_MISMATCH, INVALID_MISSION, BUSY뿐이다. NOT_READY 앞에는 PHASE_PREPARING feedback이 나갈 수 있다. "Fleet은 feedback 수신을 수락 확인으로 쓰지 않는다"는 그대로다 |
| M2 | (없음) | 항목 실행 중에 식별 대조가 어긋나면 ABORTED, REASON_INTERNAL이고 `detail`에 기대값과 받은 값을 적는다 |
| M3 | 잠정 규칙: failsafe 동작 중에 취소가 오면 Hold 확인 실패와 같은 경로 | 삭제. 취소는 상황을 가리지 않고 Hold를 시도하고 결과로 가른다. LAND 항목 중의 취소도 같다. CANCELED로 끝난 기체는 Hold(ARMED, `landed` false)이거나 지상 disarm이다. Hold로 끝난 기체는 지면 근처이거나 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않는다([실측] X2a 1.8 s 1회와 X2b 1회, 12 s 관찰, 스크립트가 보낸 명령. 미확인 범위는 쟁점 3 M3의 목록). 지상 disarm 상태의 취소는 이 goal에서 arm을 보낸 적이 없을 때만 바로 CANCELED다 |
| M4 | 공중 취소: setpoint 발행을 유지한 채 Hold 명령, 확인 뒤 CANCELED | 더한다: Hold를 처음 관측하면 setpoint 발행을 멈춘다. Hold 명령의 ack가 거부이면 타임아웃을 기다리지 않고 Land 경로로 간다 |
| M5 | 지상 arm 상태 취소: disarm 확인 뒤 CANCELED(실패 분기 없음) | disarm이 `mode_confirm_timeout` 안에 확인되지 않으면 ABORTED, REASON_DISARM_FAILED(새 상수 13. 의미: 취소 처리 중 지상에서 보낸 disarm이 제한 시간 안에 확인되지 않았고 기체가 arm 상태로 남았을 수 있다). 대기 중 지상 판정이 풀리면 공중 분기로 넘어간다. REASON_MODE_SWITCH_FAILED의 의미는 넓히지 않는다(요청한 모드 전환이 확인되지 않음). 이 goal에서 arm을 한 번이라도 보냈으면 지상에서 DISARMED로 보여도 같은 disarm 확인을 거친다(2026-11-11 px4 승인 반영) |

1a에 고정하지 않고 표시만 하는 것(U3. 5단계 사용자 결정 1의 고정 범위에서 뺀 조각): 마지막 항목이 LAND가 아닌 미션(공중에서 끝나는 미션)의 종료 동작. 1a 노드는 그런 미션을 INVALID_MISSION으로 끝낸다(임시 제한, 계약 문장이 아니다). 첫 소비자가 1b의 YAML 미션이므로 1b 설계 토론에서 정하고 1b 완료에 고정한다. architect 권고는 취소와 같은 이유로 "Hold 확인 뒤 SUCCEEDED"다. 7단계 `docs/interface.md`에 "고정 전"으로 적는다.

## 재질문 결과 요약

- ros2 R1(LAND 뒤 취소): REJECT 안을 철회하고 Hold 한 규칙을 수용했다. 조건: 취소 결과는 Hold ack가 아니라 ack 뒤의 snapshot으로 정한다. Hold가 받아들여진 순간 지상 판정이 올라가고 PX4가 스스로 disarm할 수 있고, 그때는 지상 분기다.
- ros2 R2(NOT_READY): `handle_accepted`의 "즉시 NOT_READY"를 없애는 데 수용. `ready_timeout`은 ROS 시각이고 on_activate가 `/clock`을 전제로 하므로 멈춘 시계에서 무한 대기하지 않는다. 5단계 넘김 문장을 M1대로 고친다.
- ros2 R3(`[LAND]` 한 항목 미션): 수용. 추가 복잡도는 PREPARING 분기 하나와 시작 조건 술어 하나. 우려 넷: 이 미션은 `offboard_control_mode`와 `trajectory_setpoint`를 발행하지 않는다는 단위 테스트, 다시 취소하면 또 Hold(정상), EKF gate 타임아웃으로 NOT_READY가 되면 기체는 공중 Hold로 남는다, TAKEOFF로 시작하는 미션의 시작 조건을 같은 표에 px4 승인으로 명시.
- ros2 R4(소유): 수용. 같은 패키지 안의 디렉터리로 나눈다. snapshot 구조체 헤더는 경계라서 ros2 소유, px4 필수 승인.
- ros2 R5(params, launch): `/**` 유지. compose command로 `ros2 launch`를 쓸 때의 함정 셋: launch는 SIGTERM을 받으면 자식에게 SIGINT, 5 s 뒤 SIGTERM, 다시 5 s 뒤 SIGKILL을 보내 기본 유예 10 s를 넘길 수 있다(`stop_grace_period` 15 s), 컨테이너 프로세스가 죽어도 launch는 살아 있다(`on_exit=Shutdown()`), PID 1의 zombie 회수(`init: true`).
- ros2 R6(bridge): 1a는 CLI 인자 유지, `bridge.yaml` 생성은 1b.
- ros2 R7(빌더 `make`): 호출처는 `idsim_common` 안의 테스트 두 곳뿐이다. 기존 테스트의 source (254, 1), (1, 191)은 대상 sysid 2와 달라 새 규칙을 통과한다. 거부 테스트 1건을 더한다.
- ros2 R8(autostart의 원문): [소스] ros-base 이미지의 `/opt/ros/jazzy/lib/python3.12/site-packages/launch_ros/descriptions/composable_lifecycle_node.py` 30-35행(`ComposableLifecycleNode`, `autostart: bool = False`)과 `launch_ros/actions/load_composable_nodes.py` 243-256행(CONFIGURE, ACTIVATE를 한 번씩, 재시도 없음). 실행 중 동작은 확인하지 않았다.
- test T1(wrapper): 수용. 조건: wrapper는 스택을 `tools/sim_stack.sh`로만 올리고 내린다(수집에만 `compose ps/logs/stop`), `--attach`는 down을 부르지 않는다, 바깥 `timeout`은 CI `timeout-minutes`보다 짧다.
- test T2(시나리오): 순서를 B, C, A, D, T로 바꾸자고 했다(T의 발행자나 신호 손실 상태가 D를 오염하지 않게). 한 스택의 판정 구간은 [추정] sim 90-110 s. 사전조건에 `nav_state` 값을 넣지 않는다. 자기 의견서의 "첫 항목이 TAKEOFF가 아니면 INVALID_MISSION"은 `[LAND]`와 충돌하므로 architect와 ros2가 검증 규칙을 확정해야 한다.
- test T3(T의 판정): 발행자가 없을 때도 `offboard_control_signal_lost`는 true라 "묵은 timestamp 뒤 true"만으로는 vacuous하다. 대조군 false -> 묵은 timestamp true -> 대조군 복귀 false의 양방향 전이를 단정한다. 발행 전에 발행자의 `get_subscription_count() >= 1`을 확인한다. `failsafe_flags`가 변화 때만 나오면 "N회 연속"을 셀 수 없으므로 px4 확인이 필요하다.
- test T4(/fmu/in): 수용. `px4-api` 예외는 한 파일, `vehicle_command` 발행은 source가 (254, 25)가 아니면 생성 거부, `offboard_control_mode` 발행자는 T 안의 context manager로만.
- test T5(gate): 수용. `/clock` 수신과 `now() > 0`, graph의 QoS 대조를 더한다. ACCEPTED 사건이 빠지면 재시도 없이 `EVENT_MISSING`.
- test T6(recorder): 미도입 수용. `trace.jsonl`은 통과한 회차에도 남긴다.
- test T7(벽시계 가드): [실측] ros-ws 이미지에 pytest-timeout이 없다(pytest 7.4.4만). 이미지에 더하지 않는다. `wall_cap` 초과를 둘로 가른다: `/clock`이 벽시계 5 s 동안 진행하지 않으면 `CLOCK_STALLED`, 진행하는데 넘으면 `CLOCK_SLOW`.
- devops D1(wrapper): 수용. 조건: `--attach`는 스택을 내리지 않는다, 수집 순서는 `compose stop -t 15 px4-N` -> 수집 -> down이고 trap으로 중단돼도 down이 돈다, 마지막 stdout 줄에 실행 디렉터리. `sitl.yml`은 colcon build를 별도 step으로 앞에 둔다.
- devops D2(서비스, params): `ops-N`과 `/**` 수용. launch에 `output='screen'`(아니면 stdout이 `compose logs`에 없다), `stop_grace_period: 15s`, `init: true`(검증 필요).
- devops D3: `bridge.yaml`, recorder, `.idsim_build.json` 미도입 수용. recorder는 "실패한 sitl은 MCAP 업로드"의 1a 예외로 결정 기록에 남길 것.
- devops D5(PR): golden이 두 번 바뀌는 것은 문제가 아니다. `GENERATOR_VERSION`은 P4에서 3, P5에서 4. `--run-id` 제거는 P4. lint/unit trigger 정리는 맨 앞의 작은 PR. P1 머지 뒤 main build가 새 key를 올린 다음에 다른 PR을 rebase한다. autostart 실증은 P4 전에 CI에 없으니 P3에서 수동 스택 확인을 완료 조건으로 둔다.
- devops D6(trigger): 공개 저장소의 표준 hosted runner가 무료라는 근거는 GitHub Docs "About billing for GitHub Actions"인데 오늘 원문을 다시 확인하지 않았다. 선택지별 단점은 "사용자 결정 필요" U2.
- logging L1(recorder): 미도입에 동의. regex 기록에는 오프셋 메타데이터와 미션 경계가 없어 Phase 2 replay 입력으로 다시 쓸 수 없다. 6단계가 지켜 둘 것: `artifacts/runs/<id>/bag/` 이름 예약, 수집 순서 맨 앞에 recorder 정지 자리, trace 표본에 수신 ROS 시각과 PX4 `timestamp`(us)를 함께 기록. logging은 `MissionEvent`를 TRANSIENT_LOCAL로 발행하자고도 했는데 받지 않았다(쟁점 7).
- px4 X1(실험 C와 `[LAND]`의 근거): [실측] 실험 C 때 setpoint 발행은 켜져 있었다. "AUTO_LOITER, armed, 발행 없음에서 NAV_LAND"도 [실측] 1회 있다(run3: 32 ms 뒤 AUTO_LAND, 9.03 s 뒤 landed, 11.05 s 뒤 DISARMED). `[LAND]` 한 항목 미션의 근거로 쓸 수 있다. 다만 EKF gate 직후에 보내는 순서 자체는 실측과 다르다.
- px4 X2(지면 바로 위의 Hold): [소스] `MulticopterPositionControl.cpp` 501-519행. `ground_contact`가 참이면 모드와 무관하게 추력을 0으로 만든다. 그래서 Hold가 받아들여져도 계속 내려앉고, landed 뒤 `COM_DISARM_LAND`로 자동 disarm된다. 기체에 위험은 없다. 요구 둘: Hold 확인 창에서 본 DISARMED를 "공중 disarm = FAILSAFE"로 분류하지 않는다(landed 뒤의 disarm은 지상 disarm이다), CANCELED 뒤 기체가 지상에 disarm 상태로 남을 수 있다는 것을 기대 결과로 적는다. `ground_contact`가 거짓이면 그 높이에서 호버한다([추정]). reviewer 검증 뒤 "계속 내려앉아 disarm"은 쟁점 3 M3에서 [추정]으로 내렸다. 2026-11-11 실측(px4-engineer P3b 착수 전 승인 검토(git 이력) 추가 문제 4)으로 이 [추정]은 이륙 단계와 0.5 m 호버에 대해 반증됐다. Hold에서는 `ground_contact`가 서지 않아 기체가 ARMED, landed false로 머문다.
- px4 X3(이륙한 적 없는 지상 armed, OFFBOARD에서 발행 중단): [소스] 1 s 뒤 AUTO_LAND, `failsafe` true가 되고, 이륙한 적이 없어 land 자동 disarm이 없으며 `COM_DISARM_PRFLT=-1`이라 armed인 채 남는다. 실측은 없다. 이 상태의 강제가 아닌 disarm은 받아들여진다. ABORTED 전에 disarm을 한 번 더 보내기를 권한다.
- px4 X4(감시 표의 빈 조합): [소스] `Commander.cpp` 2369-2372행. `failsafe`가 거짓이면 `nav_state`는 사용자 의도와 같으므로 정상 상태에서는 나오지 않는 조합이다. 방어용 분류는 REASON_FAILSAFE(사용자 의도가 OFFBOARD로 남아 있다는 것은 아무도 모드 변경을 요청하지 않았다는 뜻이다).
- px4 X5(T의 flag 판정): [소스] `offboardCheck.cpp`의 `data_is_recent` 경로를 지난다. `failsafe_flags`는 5 Hz 상한으로 나간다. 조건 둘: `offboard_control_mode`에 `position=true`를 넣는다, `local_position_invalid`가 거짓일 때만 의미가 있다(대조군 단계가 이것을 걸러 준다). [실측] 시동 해제 상태에서는 신호가 없어도 failsafe가 걸리지 않았다. 바뀌는 것은 `pre_flight_checks_pass`뿐이다.
- px4 X6(소유): 수용. 조건 다섯: core는 px4_msgs를 include하지 않고 이를 기계적으로 강제한다, 모드 명령 송신과 발행 중단 시점과 3회 연속의 의미를 바꾸는 전이 표 수정은 px4 승인 없이 머지하지 않는다, 타임아웃 기본값은 px4 소유, X2와 X4를 전이 표에 넣는다, 어댑터 단위 테스트의 fixture 값은 px4 실측 로그에서 뽑는다.
- px4 X7(ULog): 모른다. SIGTERM에서 logger가 파일을 정상적으로 닫는지 확인하지 않았다. [추정] ULog는 append 형식이라 끝이 잘려도 마지막 버퍼만 잃는다. 확인 방법은 `stop`의 종료 코드(137이면 KILL)와 pyulog 검증이다(호스트에 pyulog 없음).

---

## 쟁점 1. 스택 기동 주체

결정
- 스택을 올리고 내리는 것은 호스트 wrapper `tests/sitl/run_sitl.sh`다. pytest는 `runner` 서비스(ros-ws, `compose run --rm`) 안에서 돌고, fixture는 `IDSIM_STACK_FILE`의 `stack.json`을 읽어 이미 떠 있는 스택에 붙어 준비 상태를 검증만 한다. 준비 검증이 실패하면 skip이 아니라 session 오류다.
- `runner`에 docker 소켓을 주지 않는다.
- wrapper의 인자: `--stack k`(없으면 `IDSIM_STACK_INDEX`, 없으면 0), `--repeat N`(회마다 down 뒤 콜드 up, 실행 id가 다르다), `--attach <실행 디렉터리>`(올리지도 내리지도 않고 pytest와 수집만. QGC와 Gazebo GUI 육안 확인, 디버깅용), pytest로 넘기는 선택 인자.
- wrapper 규칙: 스택은 `tools/sim_stack.sh`로만 올리고 내린다. 수집에만 `docker compose ps/logs/stop`을 직접 쓴다. 순서는 up -> pytest(바깥 `timeout`) -> (Phase 2에 recorder 정지가 들어올 자리) -> `compose stop -t 15 px4-N` -> 수집 -> down이고, 중단돼도 trap으로 down이 돈다(`--attach` 제외). 마지막 stdout 줄은 실행 디렉터리 경로다. `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다.
- CI와 로컬은 이 한 명령을 쓴다. `sitl.yml`은 시나리오를 모른다.
- 소유: wrapper를 포함한 `tests/sitl/` 전체는 test-engineer. devops-engineer는 compose와 `sim_stack.sh` 호출부를 검토하고 `sitl.yml`을 소유한다.

근거: architecture.md의 두 문장("fixture가 `docker compose up --wait`로 올린다", "pytest는 ros-ws 컨테이너 안")은 `runner`에 docker CLI와 소켓이 없어 함께 성립하지 않는다(test, devops 둘 다 지적). 소켓을 마운트하면 호스트 root 권한이 테스트 컨테이너로 넘어가 3단계의 uid:gid 매핑 취지와 어긋난다.

기각한 안
- `tools/sitl_test.sh`와 `tests/integration/`(devops): 층 이름이 문서와 CI에서 "SITL 통합", job 이름이 `sitl`이고, 선례 `tests/smoke/run_smoke.sh`와 같은 자리에 두는 쪽이 찾기 쉽다. devops가 재질문에서 수용했다.
- 스크립트 셋(`run_sitl.sh`, `repeat.sh`, `collect.sh`. test 초안): 진입점은 하나로 한다. 수집을 내부 함수로 둘지 보조 파일로 둘지는 test-engineer가 정한다.

## 쟁점 2. 노드 실행 형태, lifecycle, 생성기

결정: 실행 형태
- 언어는 C++17. 패키지 `idsim_mission`(ament_cmake) 하나에 라이브러리 셋: `idsim_mission_core`(ROS 비의존. 검증, 상태기, 종료 결과), `idsim_mission_px4`(px4_msgs -> snapshot 어댑터), `mission_executor_component`(lifecycle 노드 껍질). 이것은 언어 선택이 아니라 기존 결정(architecture.md의 "핵심 노드는 C++")의 적용이다.
- 기체마다 compose 서비스 `ops-N` 하나. command는 `ros2 launch idsim_mission vehicle_ops.launch.py namespace:=/px4_N executor_name:=mission_executor params_file:=/opt/idsim/artifacts/runs/<id>/params/ops-N.yaml`. 노드 이름의 출처는 생성기 하나다. 값 `mission_executor`는 생성기의 상수이고, 생성기가 같은 값으로 `stack.json`의 `executor_node`와 healthcheck를 만든다. launch 파일은 생성하지 않는 정적 파일이고 `ComposableNodeContainer(component_container_isolated, 이름 ops_container)`와 그 안에 load하는 컴포넌트 `idsim_mission::MissionExecutorNode`(이름은 인자 `executor_name`의 값) 하나만 담는다. launch의 `autostart`는 쓰지 않는다(P3a 결과. 아래 "전이"). launch 파일은 `executor_name`에 기본값을 두지 않고 노드 이름 문자열을 직접 적지 않는다. remap은 두지 않는다. launch에는 `output='screen'`과 컨테이너의 `on_exit=Shutdown()`을 건다.
- 전이(2026-11-11 재결정. P3a 실행 확인 결과(git 이력)): 전이를 거는 주체는 노드 자신이다. Executor는 생성자에서 만든 벽시계 일회 timer(`create_wall_timer`, 0 ms)로 `configure()`를 부르고, 성공하면 `activate()`를 부른다. 각각 한 번이고 재시도하지 않는다(launch autostart가 하려던 것과 같다). fixture, compose command, launch는 전이를 걸지 않는다.
  - timer의 시계: 벽시계여야 한다. 노드 시계(`use_sim_time`) timer는 `/clock`이 오기 전에는 fire하지 않으므로, `/clock`이 없으면 전이를 시도하지도 않아 ERROR 로그 없이 `unconfigured`에 남는다. 이 timer는 판정에 쓰지 않는 trigger이고 벽시계 예외 목록(문서 반영 목록의 시간 기준 문장)에 넣는다. P3a 시험 코드의 자기 전이도 `create_wall_timer(0 ms)`였다(ros2-engineer 확인 2026-11-11. `/clock`이 없는 실행에서도 fire해 configure가 성공했고 activate는 2.000 s 뒤 FAILURE였다). 주의 둘: (1) 콜백의 첫 줄에서 timer를 `cancel()`한다. 0 ms 벽시계 timer는 취소하지 않으면 계속 다시 fire한다. (2) on_activate는 이 timer 콜백 안에서 최대 2 s 동안 executor를 막는다. 그동안에도 `/clock`은 TimeSource의 clock thread(`use_clock_thread` 기본 true)가 받으므로 대기가 풀린다([실측] 대기 중에 `/clock`이 도착한 경우 1.350 s 뒤 성공). NodeOptions에서 `use_clock_thread`를 끄지 않는다.
  - 끄는 param: 선언 param `lifecycle.self_start`(bool, 기본 true, 읽기 전용. 생성자에서만 읽는다). 생성기는 이 key를 params 파일에 만들지 않는다(식별값만 생성한다는 규칙 그대로). 단위 테스트와 노드 배선 테스트는 NodeOptions의 parameter override로 false를 주고 전이를 직접 건다. false여도 lifecycle 서비스는 그대로라 손으로 전이할 수 있다.
  - 실패 시: 프로세스를 끝내지 않는다. 노드는 실패한 자리(`unconfigured` 또는 `inactive`)에 남고, 어느 전이가 왜 실패했는지 ERROR 로그 한 줄을 고정 접두어로 남긴다(grep할 수 있게. 접두어 문자열은 ros2-engineer가 정하고 devops-engineer에게 알린다). 드러나는 길은 compose healthcheck(`active`로 시작하지 않음)와 `sim_stack.sh`의 노드 단계 실패 때 출력하는 `ops-N` 로그 끝과 `.State.Health.Log`다. `run_sitl.sh`는 둘 다 아티팩트에 넣는다.
  - 실패 시 프로세스를 끝내는 안을 기각한 이유: 컴포넌트가 `rclcpp::shutdown()`을 부르면 컨테이너 프로세스 전체가 내려간다. Phase 2에 같은 컨테이너에 들어올 Collector까지 내리게 되고, 프로세스의 수명을 컴포넌트 하나가 정하는 구조가 된다. 남겨 두면 상태를 조회하고 손으로 전이를 다시 걸 수 있다. 실패가 드러나는 방식이 원래 설계(healthcheck)와 같다. 대가는 실패가 즉시가 아니라 healthcheck 주기 뒤에 드러난다는 것이다. 상한은 컨테이너 시작부터 약 54 s, 최악 70 s다(devops-engineer. [추정]. 아래 healthcheck 값). 실패한 실행에서만 드는 비용이고 `STACK_UP_TIMEOUT` 240 s와 CI 15분 안이다.
  - 표시 파일(노드가 전이 결과를 파일에 쓰고 healthcheck가 먼저 읽는 안)은 두지 않는다. 컴포넌트와 compose 사이에 경로 계약이 하나 생기고, `ros2 lifecycle get`이라는 직접 신호가 이미 있다. 다시 볼 조건: CI에서 probe 평균이 7 s를 넘거나 probe 부하로 RTF가 0.7 기준에 걸릴 때(devops-engineer).
  - launch 쪽: [실측]은 `ComposableLifecycleNode(autostart=True)`를 둔 채 자기 전이를 켠 형태였다(10/10 active). 구현은 `autostart`를 빼고 load만 하는 형태로 두고(`ComposableNode`를 쓸지 `ComposableLifecycleNode(autostart=False)`를 쓸지는 ros2-engineer가 정한다) P3의 수동 확인에서 그 형태로 active를 다시 확인한다.
- lifecycle: on_configure에서 params 검증(`vehicle.*` 누락이나 불일치, `use_sim_time` false이면 FAILURE)과 PX4 구독, 발행자, 사건 발행자 생성. on_activate에서 `/clock` 대기(2 s. `wait_until_started`의 벽시계 대기다. [실측] P3a: 프로세스 시작부터 첫 `/clock`까지 최대 0.66 s이고 on_activate에 들어갈 때는 이미 시작되어 있어 실제 대기는 20/20 0 s였다. `/clock`이 없으면 2.000 s 뒤 FAILURE로 `inactive`에 남는다. CI runner에서는 첫 CI 실행에서 다시 재고 2 s가 모자라면 값을 올린다)와 `Px4Timestamp::now` 성공 확인, 20 Hz timer(노드 시계), action 서버 생성. goal 실행 중의 deactivate는 거부. on_shutdown과 on_error는 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝내고 종료 사건을 낸다. `vehicle_status` 수신과 식별 대조는 activate 조건에 넣지 않는다(쟁점 3 M1).
- action 서버를 on_activate에서 만든다. 그래서 client의 `server_is_ready`가 active의 근거가 된다([추정]. 쟁점 7).
- callback group은 MutuallyExclusive 하나에 PX4 구독, timer, action 서버를 모두 넣는다. goal 실행용 thread를 만들지 않고 timer tick이 상태기의 `step()`을 부른다. 구독 callback은 최신 표본과 수신 ROS 시각만 저장한다.
- 컨테이너 autostart는 동작하지 않는다([실측] P3a. 5/5 `unconfigured`, 오류 로그 없음. [소스] launch_ros 0.26.13의 `load_composable_nodes.py`가 FQN을 `/px4_1mission_executor`로 만들고 `ChangeState`의 matcher가 어느 네임스페이스에서도 맞지 않는다). 앞 판은 이 경우 "단독 실행 파일이 `main`에서 전이"로 물러선다고 적었으나 그 길로 가지 않고 위 자기 전이를 고른다. 컨테이너를 고른 이유(Phase 2 Collector 동거, isolated executor)가 그대로 지켜지고 서비스 command, launch 인자, healthcheck가 바뀌지 않는다. launch_ros 판에도 의존하지 않는다.

결정: 생성기와 `stack.json`
- params 파일은 `artifacts/runs/<id>/params/ops-N.yaml`. key는 `/**`이고 내용은 `use_sim_time: true`, `vehicle.id`, `vehicle.ns`, `vehicle.sysid`뿐이다. 튜닝 값(타임아웃, 주기), `command_source.*`, `lifecycle.self_start`는 생성하지 않고 노드 선언 기본값에 둔다. [실측] P3a: `/**`의 값은 컨테이너 노드에 적용되고 선언하지 않은 key는 LoadNode 오류 없이 무시된다. 패키지 config yaml을 둘째 params 파일로 두지 않는다. 노드는 `vehicle.*`에 기본값을 두지 않아 누락이면 configure가 실패한다.
- `stack.json`(schema 1 유지, key 추가만): `vehicles[].vehicle_id`, `vehicles[].params_file`(실행 디렉터리 기준 상대 경로), `vehicles[].executor_node`(노드 FQN. healthcheck와 진단용), `run.params_dir`, `startup.node_stages`, `services.ops`. `GENERATOR_VERSION`은 P4에서 3, P5에서 4.
- `vehicle_id`와 `px4_ns`는 별도 key로 둔다. 지금은 값이 같고 생성기의 불변식 검사가 `vehicle_id == ns[1:]`과 토큰 하나임을 단정한다. `px4_ns`는 PX4 환경변수에 넣는 값이고 `vehicle_id`는 계약 식별자라서 의미가 다르다.
- `ops-N` 서비스: ros-ws 이미지, 호스트 uid:gid, `ROS_LOG_DIR=<run>/ros_log/ops-N`, `depends_on`은 `bridge`와 `px4-N`(healthy), `restart: no`, `stop_grace_period: 10s`(`sim_stack.sh`와 `run_smoke.sh`의 `down --timeout 10`이 서비스 값보다 우선하므로 하나로 맞춘다. 앞 판의 15s를 고쳤다), `init: true`, `stop_signal: SIGINT`.
  - `stop_signal`을 SIGINT로 두는 이유([실측] P3a, 각 1-2회): `init: true` 구성에서 SIGTERM이면 0.4-0.5 s에 끝나지만 launch가 바로 죽어 정리 로그가 없다. SIGINT면 `init` 유무와 무관하게 1.7 s에 launch가 자식에게 신호를 넘기고 정리 로그를 남기며 끝난다. Executor의 on_shutdown(실행 중인 goal을 ABORTED로 끝내고 종료 사건을 낸다)이 돌 기회가 SIGINT 쪽에만 있다고 본다([추정]. 실측 없음. P4 stop 검증). `init` 없이 PID 1인 launch가 SIGTERM을 무시해 15.5 s 뒤 SIGKILL되는 것은 `init: true`를 두는 이유다.
  - exit code: SIGINT로 끝난 launch의 exit code는 정상 정리에서도 1이다([실측]). 컨테이너 exit code는 판정에 쓰지 않는다(판정은 junit과 verdict). exit 1을 보아 넘기는 것은 stop을 요청한 뒤(down 단계)에 한정한다. up 단계와 실행 중의 종료는 코드와 무관하게 실패다(launch 인자 누락도 rc 1이고, 컨테이너 프로세스가 죽으면 `on_exit=Shutdown()`으로 exited가 된다). 둘을 가르는 것은 순서다: (1) stop 전에 `compose ps -a --format json`을 기록하고, (2) 그 시점에 running이 아닌 `ops-N`이 있으면 실패, (3) `compose stop`, (4) `compose logs`(SIGINT 정리 로그 포함), (5) down. stop 뒤의 exit code(1, 130 등)는 기록만 한다. `--abort-on-container-exit`와 `--exit-code-from`은 쓰지 않고, entrypoint에서 exit 1을 0으로 바꾸지 않는다.
  - healthcheck: `ros2 lifecycle get --no-daemon <executor_node>`의 출력이 `active`로 시작하는지([실측] P3a: 출력은 `active [3]`, `inactive [2]`, `unconfigured [1]` 형식이고 `docker exec`로 3.0-4.5 s 걸린다). 값은 devops-engineer의 것을 채택한다: `interval` 10s, `timeout` 10s, `retries` 2, `start_period` 20s, `start_interval` 2s. 명령은 `/opt/ros/<distro>/setup.sh`만 source하고(`bash -l`과 workspace overlay 없음) `ROS_LOG_DIR=/tmp/hc timeout 8 ros2 lifecycle get --no-daemon <FQN>`의 출력을 echo한 뒤 판정한다. 출력을 버리지 않아 `.State.Health.Log`에 `unconfigured [1]` 같은 상태가 남는다. FQN은 생성기 상수 하나에서 나오고 `stack.json`의 `executor_node`와 같다.
  - 실패가 드러나기까지의 상한([추정] devops-engineer. probe가 겹치지 않고 앞 probe가 끝난 뒤 `interval`만큼 기다린다는 동작은 기억에 기댄다): 정상은 약 5-6.5 s에 healthy. 자기 전이 실패는 20 + 4.5 + 2 x 14.5 = 약 54 s, 모든 probe가 timeout까지 가면 20 + 10 + 2 x 20 = 70 s. P4에서 결함 주입으로 잰다. `retries` 2는 runner가 `ops-N`의 healthy에 의존하게 되므로 probe 한 번의 흔들림으로 테스트 시작이 실패하지 않게 하려는 값이다. CI 첫 3회에 RTF와 함께 probe 시간을 기록하고, RTF가 0.7 기준에 걸리면 `interval` 30s를 먼저 시험한다.
  - 다른 서비스: bridge와 xrce-agent도 PID 1이라 SIGTERM을 버린다([소스] 떠 있는 스택의 신호 마스크. down 시간은 미측정이고 지금 약 20 s 이상으로 추정). 상주 ros-ws 서비스(bridge, `ops-N`, P5의 foxglove)와 xrce-agent에 `init: true`를 둔다. `stop_signal: SIGINT`는 launch로 띄우는 `ops-N`에만 둔다(bridge의 `ros2 run`이 SIGINT를 자식에 넘기는지 모른다). P4의 같은 PR에서 고치고 생성기 golden 4종이 함께 바뀐다.
- `runner`의 `depends_on`을 `bridge`에서 `ops-1..N`으로 바꾼다.
- 기동 단계: `tools/sim_stack.sh up`은 인프라 3단계 -> 모델 사전 검사 -> 노드 단계. `--infra-only`면 노드 단계를 건너뛴다. `run_smoke.sh`는 `--infra-only`를 쓴다. 노드 단계 전에 `ros_ws/install/idsim_mission/`이 없으면 안내와 함께 실패한다(1a 4단계 넘김).
- embedded 변형에는 `ops-N`, `foxglove`, `lichtblick`을 만들지 않는다(`/clock` bridge가 없다).
- golden 비교를 실행 디렉터리 전체 트리(파일 집합과 바이트)로 넓힌다. 성질 검사에 "생성 파일 어디에도 `fmu/`가 없다"를 넣는다.
- `check_host.sh`에 Docker Engine 25 이상 점검을 넣는다(`start_interval`. 미해결 항목 닫기).
- `gen_compose.sh`의 `--run-id` 제거(결정 (l))는 P4에서 한다.

근거
- isolated 컨테이너는 Phase 2에 Collector가 같은 프로세스에 들어와도 Executor의 20 Hz tick을 밀어내지 않는다(ros2 1-4). architecture.md의 "기체당 컴포넌트 컨테이너 하나"와 같다.
- 서비스 이름을 `mission-N`이 아니라 `ops-N`으로 두는 이유: Phase 2에 Collector가 들어오면 이름이 역할과 어긋난다(devops도 중립 이름을 대안으로 냈다).
- `/**`: 컨테이너 노드와 Phase 2 Collector가 같은 식별값을 받고, 선언하지 않은 key는 무시된다. FQN key의 걱정(이름이 틀리면 조용히 미적용)은 `/**`에서는 생기지 않고, 누락은 configure 실패로 드러난다.
- 튜닝 값을 생성하지 않는 이유: 생성기 golden이 튜닝 변경에 흔들리지 않고, 값의 출처가 하나다(ros2, devops 같은 의견).
- 스모크에서 노드를 빼는 이유: 스모크는 PX4, Gazebo, DDS 회귀 판정이고, px4-in의 arm과 disarm이 Executor와 같은 기체에 명령을 보내는 일을 피한다(devops, px4).

기각한 안
- `ros2 run` 단독 실행 파일과 `autostart` param(devops 초안), 단독 실행 파일 + `launch_ros.actions.LifecycleNode(autostart=True)`(P3a의 대안 B. [실측] 10/10 active), 단독 실행 파일이 `main`에서 전이(앞 판의 물러설 자리): 셋 다 Phase 2의 같은 컨테이너 요구를 잃는다. B는 전이 주체가 launch로 남고 실패 때 launch가 ERROR 로그를 내는 장점이 있지만 그 이유로 컨테이너를 버리지 않는다.
- launch가 `change_state` 서비스를 직접 부르거나 `ros2 lifecycle set` 프로세스를 띄우는 안(P3a의 D): 측정하지 않았고 launch 코드나 participant가 는다.
- FQN key와 패키지 config 둘째 params 파일(devops): 위 근거. devops가 수용했다.
- `bridge.yaml` 생성(devops): 1a에는 `/clock` 한 줄뿐이라 바꿀 이유가 없다. 1b에서 표적과 함께 옮긴다(ros2 권고, devops 수용). progress의 "다음 작업 5"에서 이 부분은 1b로 간다.
- `.idsim_build.json`: `stack.json`의 git commit, dirty와 반복 요약으로 대신한다.

## 쟁점 3. 5단계 계약의 변경

결정은 "계약 변경 여부와 golden 영향"의 M1-M5다. 근거와 기각한 안을 적는다.

M1(NOT_READY의 시점)
- `handle_accepted`는 goal과 노드 자신의 상태만으로 판정되는 것만 즉시 abort한다. 순서는 VEHICLE_ID_MISMATCH -> INVALID_MISSION -> BUSY다(틀린 기체로 온 goal에 BUSY를 주면 Fleet이 다른 기체에 재시도해 설정 오류를 덮는다. ros2 2-1).
- PX4 상태에 달린 판정(`vehicle_status`, `failsafe_flags`, `vehicle_local_position`, `vehicle_land_detected` 수신, 식별 대조, EKF gate)은 모두 PREPARING에서 `ready_timeout`(ROS 시각) 안에 기다린다. 식별 불일치가 확정되면 그 tick에 NOT_READY, 시간을 넘기면 NOT_READY다.
- 근거: [실측] ros2 M2. PX4 토픽은 에이전트를 거쳐 discovery에 약 1.1 s가 걸린다. activate 직후의 goal에 "status 미수신이면 즉시 NOT_READY"를 적용하면 흔들린다. EKF 수렴은 기다리면 풀린다. 5단계의 `reason` 경계("NOT_READY는 항목을 시작하기 전(PHASE_PREPARING)에")와는 이미 맞고, 어긋나는 것은 "feedback 0건" 문장뿐이다.
- 기각: 즉시 NOT_READY를 식별 불일치와 미수신에 남기는 안(ros2 초안). 경로가 둘이 되고 미수신 쪽이 흔들린다. ros2가 수용했다.

M2(실행 중 식별 불일치): REASON_INTERNAL과 `detail`. 사실상 설정 오류이거나 같은 네임스페이스에 다른 발행자가 있는 경우다. NOT_READY와 PRECONDITION_FAILED는 정의상 항목 시작 전이다. 새 상수는 소비자가 없어 더하지 않는다.

M3(LAND 중 취소와 잠정 규칙 삭제)
- 취소는 어느 상태에서 오든 그 tick의 snapshot으로 분기를 고른다: 지상 disarm이면 바로 CANCELED(이 goal에서 arm을 한 번도 보내지 않았을 때만이다. 보냈으면 `arming_state`와 무관하게 disarm 분기를 거친다. M5), 지상 arm이면 disarm 분기, 공중이면 Hold 분기. LAND 항목 중이어도 같다. 분기는 매 tick 다시 고른다(Hold를 보낸 뒤 지상 판정이 올라가면 지상 분기로 간다. ros2 조건).
- 근거: [실측] px4 4.1의 B(offboard 손실 failsafe 진행 중의 Hold가 ACCEPTED, 첫 status에서 AUTO_LOITER, `failsafe` false)와 C(NAV_LAND 착륙 중의 Hold가 ACCEPTED, 하강 정지). [소스] 모드 폴백은 사용자 넘겨받기를 항상 허용한다. 계약의 분기가 하나가 되고, cancel 거부라는 새 분기를 client에 만들지 않는다. 착륙 중 취소는 "지금 하는 것을 멈추고 대기"로 읽히며, 내리는 것은 취소를 요청한 쪽의 책임이다(5단계 "취소 뒤의 책임").
- 지면 근처에서의 취소(2026-11-11 실측으로 고침): [실측] run 20261111-030155-k5. TAKEOFF 목표점 발행 중의 이륙 램프(첫 ARMED 표본 뒤 1.3 s와 1.8 s. 높이 -0.11에서 0.06 m)와 0.5 m 호버(0.37-0.47 m)에서 Hold를 보내고 처음 관측한 순간 발행을 멈추면 기체는 내려앉지 않는다. 12 s 동안 ARMED, `landed` false, AUTO_LOITER로 머물렀고 자동 disarm은 없었다(X2a 2회, X2b 1회. 모두 실측 스크립트가 보낸 명령이다). [소스] Hold에는 하강 속도 setpoint가 없어 `ground_contact`가 서지 않는다(`MulticopterLandDetector.cpp` 229-236행. reviewer의 지적이 맞았다). 앞 판의 [추정] "`ground_contact`가 참이면 Hold가 받아들여져도 계속 내려앉아 자동 disarm될 수 있다"는 이 범위에서 반증됐으므로 철회한다.
  - Executor의 규칙으로 읽은 표본 수: Hold로 끝나는 경로의 표본은 X2a 1.8 s 1회와 X2b 1회, 둘이다. X2a 1.3 s는 Hold를 확인한 시점에 `landed`가 true였으므로(0.16 s 뒤 false) Executor의 규칙에서는 공중 분기가 아니라 지상 arm 분기다.
- 계약 문장: CANCELED로 끝난 시점의 기체는 Hold(AUTO_LOITER, ARMED, `landed` false)이거나 지상 disarm이다. Hold로 끝난 기체는 지면 근처이거나 사실상 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않고 그대로 머문다(위 표본, 12 s 관찰). 분기 규칙은 그대로다. Hold 확인을 기다리는 중에 `landed`가 참이 되면 지상 분기로 넘어가고, 그 창에서 본 DISARMED의 분류는 쟁점 4의 고정 규칙을 따른다(지상 disarm이면 FAILSAFE가 아니라 CANCELED).
- CANCELED 뒤 이어 보낸 `[LAND]` 미션: Hold로 끝난 기체는 armed이고 `landed` false이므로 `[LAND]`의 시작 조건을 통과한다. [실측] 실측 스크립트가 보낸 NAV_LAND 5회가 모두 disarm까지 갔다. 갈라 적으면 Hold 상태(AUTO_LOITER, 발행 없음)에서 3회(X2a 2회, X2b 1회), 지상 setpoint를 발행하던 OFFBOARD에서 2회(H)다. Executor가 보낸 `[LAND]` 미션은 아직 실측이 없다(Executor가 없다). 따라서 이륙 단계나 낮은 호버에서 Hold로 끝난 취소 때문에 `[LAND]`가 PRECONDITION_FAILED로 끝난다는 앞 판의 문장은 이 표본에서는 맞지 않는다. 취소가 지상 disarm 분기로 끝난 경우(기체가 이미 DISARMED)에는 당연히 PRECONDITION_FAILED다.
- 미확인 목록(위 계약 문장이 덮지 못하는 범위. 넘김 목록의 필수 재실측). 결과가 계약 문장과 다르면 고정 전에 고친다.
  - AUTO_LAND 하강 중 0.3 m 아래에서의 취소. 하강 중에는 `ground_contact`가 이미 서 있을 수 있어 위 실측과 다를 수 있다([추정]). "Hold로 CANCELED된 뒤 스스로 내려앉아 disarm되고, 이어 보낸 `[LAND]`가 PRECONDITION_FAILED"가 나올 수 있는 경우다.
  - 12 s 이후의 동작. 관찰이 12 s까지였다. 재실측은 60 s 이상 본다.
  - 지상 setpoint 발행 중에 보낸 Hold(M5의 지상 arm 분기에서 공중 분기로 넘어가는 경로). H의 정리는 NAV_LAND였다.
  - TAKEOFF 목표점 발행 중이고 `landed`가 아직 true인 구간(첫 ARMED 뒤 약 0-1.3 s)에서 지상 setpoint로 바꾸고 disarm. 이륙 직후 취소의 정상 경로다.
  - 높이 0.06 m와 0.37 m 사이에서의 Hold.
  - Executor가 보낸 `[LAND]` 미션(지면 근처 Hold에서).
- 시나리오 D는 5 m에서 취소하므로 위 미확인 범위에 들지 않는다.
- 기각: `handle_cancel`에서 REJECT(ros2 초안). ros2가 철회했다.

M4(Hold 확인 뒤 발행 중단, ack 거부의 처리)
- 공중 분기: 발행을 유지한 채 Hold 명령을 재전송하며 기다린다. AUTO_LOITER를 처음 관측하면 발행을 멈추고, 3회 연속이면 CANCELED. ack가 거부(TEMPORARILY_REJECTED, DENIED 등)이거나 `hold_confirm_timeout`(기본 3 s)을 넘기면 Land 경로: NAV_LAND를 재전송하며 AUTO_LAND를 처음 관측하면 발행을 멈추고 ABORTED, REASON_MODE_SWITCH_FAILED. `mode_confirm_timeout` 안에 AUTO_LAND도 보이지 않으면 발행을 멈추고 같은 결과로 끝낸다(그 뒤는 PX4의 offboard 손실 경로 `COM_OBL_RC_ACT=4`가 내린다). `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 ABORTED, REASON_LINK_LOST.
- 근거: [소스][실측] px4 3절. `/fmu/in/trajectory_setpoint`는 PX4 안에서 FlightModeManager의 setpoint와 같은 uORB 토픽이라 Offboard가 아닌 모드에서 발행하면 섞인다. Hold 중 발행을 유지하자 0.4 m 끌렸고 멈추자 돌아왔다(1회).
- 지상 arm 분기에서 넘어온 경우(대기 중 `landed`가 false가 됨)에는 TAKEOFF 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다(M5). Hold와 NAV_LAND의 재전송을 멈추는 때는 쟁점 4의 "명령 재전송 규칙"이다.

M5(지상 disarm 실패)
- 지상 arm 분기: 지상 setpoint를 발행하면서(아래) 강제가 아닌 disarm을 재전송하며 DISARMED 3회 연속을 기다린다. disarm의 TEMPORARILY_REJECTED ack는 그 자체로 실패가 아니고 `landed`가 true인 동안 재전송을 이어 간다. 확인되면 발행을 멈추고 CANCELED. 대기 중 `landed`가 false가 되면 공중 분기로 넘어간다. landed인 채 `mode_confirm_timeout`을 넘기면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 ABORTED, REASON_DISARM_FAILED. 이때 기체는 지상에 arm 상태로 남을 수 있고([소스] 이륙한 적이 없으면 offboard 손실 Land 뒤에도 자동 disarm이 없다. 실측 없음) `detail`에 그 사실을 적는다.
- 근거: 강제가 아닌 disarm은 지상 판정이 아니면 거부된다([실측] px4 4.1 D). 이륙 램프가 막 시작된 경계에서만 생기는 분기이고, 그때 기체는 사실상 공중이므로 공중 분기로 보내는 것이 맞다.
- 이 분기에서 유지하는 setpoint(px4-engineer가 2026-11-11에 확정한 문장. px4-engineer P3b 착수 전 승인 검토(git 이력) 3번): 지상 arm 분기에 들어간 tick에 `trajectory_setpoint`를 "지상 setpoint"로 바꾼다. 지상 setpoint는 그 tick의 `vehicle_local_position` x, y, z에서 z만 +0.5 m(NED, 아래쪽)이고 yaw는 그 tick의 heading이다. position과 yaw만 유한값이고 나머지는 NaN이며, `offboard_control_mode`는 position만 true다(헬퍼 그대로). 20 Hz 발행을 유지한 채 disarm을 재전송한다. DISARMED 3회 연속이면 발행을 멈추고 CANCELED. 대기 중 `landed`가 false가 되면 공중 분기로 넘어가되, setpoint는 TAKEOFF 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다. Hold를 처음 관측하면 발행을 멈춘다. disarm의 TEMPORARILY_REJECTED ack는 그 자체로 실패가 아니다. `landed`가 true인 동안 재전송을 이어 간다.
  - [소스] `MulticopterPositionControl.cpp` 466-472행: 이륙 의도는 setpoint z < 현재 z일 때만 켜진다(엄격 비교). 504-520행: 이륙 전이면 추력이 0이다. 0.5 m는 z 잡음(+-0.1 m)의 5배 여유다.
  - [실측] run 20261111-030155-k5. G(처음부터 지상 setpoint로 arm, 2회): 상승은 최대 0.05 m, `landed`는 계속 true, disarm부터 DISARMED까지 4-12 ms. K(목표점을 유지한 채 disarm, 1회): disarm이 거부되고 4.2 m 올라갔다. reviewer가 우려한 경우가 실제로 일어난다. H(목표점으로 arm한 뒤 1.5 s와 2.5 s에 지상 setpoint로 바꿈, 2회): 바꾸는 순간 이미 `landed`가 false였고(높이 0.07 m 이하) disarm은 TEMPORARILY_REJECTED였다. 지상 setpoint로 상승은 0.2 m 이하로 막혔지만 `landed`는 6 s 동안 돌아오지 않았다. 정리는 Hold가 아니라 NAV_LAND로 했다(3.4-3.5 s 뒤 disarm). 위 문장의 "공중 분기로 넘어가 지상 setpoint를 유지한 채 Hold"는 실측이 없다.
  - 실측이 없는 두 경로(reviewer 필수 1. 필수 재실측. P3b는 위 문장대로 구현하되 재실측 결과로 바뀔 수 있다): (가) 지상 setpoint 발행 중에 보낸 Hold. X2a의 Hold는 TAKEOFF 목표점 발행 중이었다. (나) TAKEOFF 목표점 발행 중이고 `landed`가 아직 true인 구간(첫 ARMED 뒤 약 0-1.3 s)에서 지상 setpoint로 바꾸고 disarm. G는 처음부터 지상 setpoint였고 H는 바꿀 때 이미 landed false였다. (나)가 "이륙 직후 취소"의 정상 경로다.
  - 기각: 발행을 멈춘 뒤 disarm. 마지막 setpoint의 timestamp + 1 s 동안 이륙 의도가 남고(466-467행), 그 뒤에는 offboard 손실 Land가 걸려 상태가 하나 더 생긴다. 기각: TAKEOFF 목표점 유지(실측 K).
  - 0.5 m는 `src/px4/` 어댑터의 상수이고 노드 파라미터로 만들지 않는다. core는 이 값을 직접 적지 않는다(넘기는 방법은 ros2-engineer와 px4-engineer가 snapshot 경계에서 정한다).
  - 발행 규칙과의 관계(architect가 채운 문장. px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 3번 승인): 지상 setpoint로 바꿔 발행하는 것은 그 tick에 발행 중일 때뿐이다. 발행 규칙에 따라 이미 멈춘 발행은 이 분기에서도 다시 켜지 않고 disarm만 재전송한다.
    - px4-engineer 보강 문장: 발행이 멈춘 뒤에는 `trajectory_setpoint`를 바꾸지 않으므로 이륙 의도에 영향이 없다. 이 규칙은 "멈춘 발행은 항상 `nav_state`가 OFFBOARD가 아닌 것을 본 뒤"라는 불변식에 기댄다. LAND 항목의 ITEM_TIMEOUT처럼 OFFBOARD인 채 멈추는 경우는 이 규칙의 적용 대상이 아니다(지상 arm이면 offboard 손실 Land가 내린다).
    - [소스] `MulticopterPositionControl.cpp` 464-467행: 이륙 의도는 `flag_control_offboard_enabled`일 때만 `_setpoint.timestamp + 1 s` 안의 setpoint로 켜진다. `Commander.cpp` 644-662행: 강제가 아닌 disarm은 `landed || maybe_landed`일 때 받는다. 노드가 본 `landed == true`는 수락의 충분조건이다.
- 같은 규칙을 지상 arm 정리 전부에 쓴다: 취소, PREPARING 실패, ITEM_TIMEOUT의 지상 arm 분기, 그리고 아래의 "arm을 보낸 뒤" 경우.
- 지상 disarm 분기의 상태 끊김과 거부 ack(test-engineer C4. architect 결정. px4-engineer 확인 2026-11-11, px4-engineer 최종 확인(git 이력) 3번 승인, 4번 동작 승인): `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 끝낸다. 취소 중이었으면 ABORTED, REASON_LINK_LOST이고, PREPARING 실패나 ITEM_TIMEOUT의 정리 중이었으면 원래 reason을 유지하고 `detail`에 적는다. `link_timeout`이 `mode_confirm_timeout`보다 짧으므로 표본이 아예 없으면 LINK_LOST가 먼저이고, 표본은 오는데 기준을 만족하는 DISARMED가 3회 차지 않으면 REASON_DISARM_FAILED다. disarm의 거부 ack는 TEMPORARILY_REJECTED든 그 밖의 것(DENIED 등)이든 그 자리에서 끝내지 않는다. `landed`가 true인 동안 재전송을 이어 가고 타임아웃에 끝내며 마지막 ack의 결과를 `detail`에 적는다(성공의 판정은 ack가 아니라 `arming_state`다).
  - 끝내기 전에 한 번 더 보내는 disarm도 강제가 아닌 disarm이다. 강제 disarm(param2 21196)은 어디에서도 쓰지 않는다. [소스] 강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 거부되므로(`Commander.cpp` 638-662행) 공중 기체를 끄지 않는다. 발행을 멈춘 뒤의 offboard 손실 동작은 지상이면 Land와 자동 disarm, 공중이면 하강이다.
  - [소스] v1.17.0의 ARM_DISARM 처리(`Commander.cpp` 969-980행)는 유효한 param1에 ACCEPTED와 TEMPORARILY_REJECTED만 돌려준다. 그 밖의 ack(DENIED, UNSUPPORTED 등)는 방어용이며 같은 규칙(재전송, 타임아웃에 종료)을 쓴다. 대상이 어긋난 명령은 ack 없이 버려지고 타임아웃이 처리한다. ARM의 "그 밖의 거부는 ARM_REJECTED"도 같은 이유로 방어용이다(arm의 DENIED도 TEMPORARILY_REJECTED로 돌아온다. 549행). 이 경로들의 테스트는 합성 ack로만 한다.
- arm을 보낸 뒤의 지상 분기(px4-engineer P3b 착수 전 승인 검토(git 이력) 추가 문제 1): 이 goal에서 arm을 한 번이라도 보냈으면 지상 분기는 `arming_state`와 무관하게 disarm 분기(지상 setpoint + disarm + disarm 전송 뒤에 받은 DISARMED 3회 연속)를 거친다. "전송 뒤에 받은"의 기준: 표본의 수신 tick이 이 분기의 첫 disarm 전송 tick보다 크고(tick 번호 비교. `수신 tick > 전송 tick`), `vehicle_status.timestamp`가 그 첫 전송에 실은 `Px4Timestamp`보다 엄격히 뒤(>)인 표본만 센다(두 조건 모두. 비교 대상은 재전송마다 새로 생기는 값이 아니라 첫 전송의 값이다). 3회 연속의 계수: 직전에 센 표본과 `timestamp`가 같은 표본은 건너뛴다(되돌리지도 더하지도 않는다. tick당 표본은 최대 1개이므로 같은 표본을 다음 tick에 다시 본 경우다). DISARMED가 아닌 표본은 계수를 0으로 되돌린다. `timestamp`가 줄어든 표본은 세지 않는다. 3회 연속은 서로 다른 `timestamp` 3개다(근거와 한계는 "px4-engineer 승인 반영"). arm 재전송은 취소나 실패를 정한 tick에 즉시 멈춘다. 이유: P6에서 보낸 arm이 아직 처리되지 않았거나 status에 반영되기 전이면 snapshot은 DISARMED다. 여기서 "바로 끝"으로 발행을 멈추면 그 뒤 arm이 처리되어 기체가 OFFBOARD에서 신호 없이 armed가 되고 offboard 손실 Land로 들어간다. 이륙 이력이 없어 자동 disarm이 없으므로 지상에 armed로 남는다([소스] `Commander.cpp` 2290, 2294행. `COM_DISARM_PRFLT=-1`. X3과 같은 상태이고 실측은 없다). 비용은 약 1 s다. 이미 DISARMED인 기체에 보낸 disarm은 ACCEPTED다([소스] `Commander.cpp` 640-642, 976-980행. [실측] D 1회).
- 기각: REASON_MODE_SWITCH_FAILED의 의미 넓히기(px4 권고였다. 위 "계약 변경 여부"의 이유로 받지 않는다), REASON_ARM_REJECTED(이름이 arm 거부라 disarm에 쓰면 PREPARING의 arm 거부와 섞인다), REASON_INTERNAL(Executor 내부 오류가 아니다).
- PREPARING 실패의 정리도 같은 절차다: 발행을 멈추기 전에 지상 arm이거나 이 goal에서 arm을 보낸 적이 있으면 지상 setpoint로 바꾸고 disarm을 보내 확인한다(`COM_DISARM_PRFLT=-1`). 이때의 reason은 원래의 실패 사유를 유지하고, disarm이 확인되지 않았으면 `detail`에 적는다.

종료의 충돌 규칙(test-engineer C5. architect 결정)
- 종료는 먼저 정해진 것이 이긴다. 종료가 정해진 tick 뒤의 표본과 cancel은 결과를 바꾸지 않는다. 종료 사건은 정확히 1건이다.
- 같은 tick에 둘 이상이 정해지면 ABORTED 사유, 완료(SUCCEEDED), 취소 순이다. 예: LAND에서 DISARMED 3번째 표본과 cancel이 같은 tick이면 SUCCEEDED다. 감시 표의 행과 cancel이 같은 tick이면 그 행의 ABORTED다. ABORTED 사유가 둘이면 감시 표의 순위를 따른다.
- "정해진다"의 시점은 정리가 끝난 때가 아니라 사유가 생긴 tick이다. ITEM_TIMEOUT이나 PREPARING 실패의 정리(Hold, disarm 확인) 중에 온 cancel은 결과를 바꾸지 않고 ABORTED와 원래 reason으로 끝난다(정리 절차는 취소와 같은 분기라 기체 동작도 같다). 반대로 CANCELING 중에 항목 `timeout`이 지나도 취소 경로로 끝난다(CANCELED, 또는 그 분기가 정한 ABORTED).
- 전제(px4-engineer 확인 2026-11-11, px4-engineer 최종 확인(git 이력) C5): 종료가 정해져 끝나는 시점에는 발행이 멈춰 있고 명령 재전송이 지워져 있다. 그래야 종료 뒤의 cancel을 무시해도 남는 동작이 없다. ABORTED 사유가 완료보다 앞서는 것은 안전 쪽이다(같은 tick에 `landed` false의 DISARMED(순위 4)와 완료 후보가 겹치면 FAILSAFE가 이겨야 공중 disarm이 성공으로 기록되지 않는다).
- 이유: 취소는 "지금 하는 것을 멈추라"는 요청이고, 이미 끝났거나 끝나기로 정해진 미션에는 멈출 것이 없다. 실제로 일어난 일을 result가 말하게 한다. cancel이 받아들여진 goal을 SUCCEEDED나 ABORTED로 끝내는 것이 rclcpp_action에서 허용되는지는 [추정]이고(기억에 기댄다) ros2-engineer가 노드 배선 테스트에서 한 건으로 확인한다. 허용되지 않으면 architect에게 알린다.

구현 지시
- architect: P3에서 `ExecuteMission.action`에 `REASON_DISARM_FAILED = 13`을 더하고, 주석의 "(취소의 분기는 1a 고정 전까지 잠정이다.)"를 지우고 M1, M3-M5를 반영한다(M3은 2026-11-11에 고친 문장). `REASON_EXTERNAL_DISARM = 14`를 그다음 줄에 더하고 두 상수에 의미 주석을 단다. golden 갱신은 `tools/ros_ws.sh shell` 안에서 `IDSIM_UPDATE_GOLDEN=1`로 하고 diff가 두 파일의 두 줄씩인지 확인한다. 주의: 줄 끝 주석에 그 줄 앞부분과 같은 문자열을 쓰면 `ros2 interface show`가 줄을 잘라 `test_contract.py`의 가드(217-222행 근처의 최상위 줄 == 직접 정의 단정)가 실패한다. 주석의 표현을 바꿔 피한다. 5단계 `decisions.md`의 쟁점 9와 넘김 목록은 고치지 않고 이 문서가 뒤의 결정임을 7단계 `docs/interface.md`에서 정리한다.

## 쟁점 4. PX4 절차 (전이 표)

px4 의견서 1-4절을 채택한다. 상태기 구현의 정본은 아래 표이고, 값과 술어의 근거는 px4-engineer 의견서(git 이력)다.

미션의 정적 검증(INVALID_MISSION. `validate_mission`)
- 계약: 항목 1개 이상, `type`이 `TYPE_*`, `timeout` > 0, 쓰지 않는 서브메시지는 기본값, 서브메시지 값의 범위(`height_m` > 0, `acceptance_m` > 0, `duration` > 0이고 `timeout`보다 짧다, `YawSetpoint.mode` 유효, 유한값), `mission_id` 정규식.
- 1a 임시 제한(계약 문장이 아니다): `type`은 TAKEOFF, LOITER, LAND만. 마지막 항목은 LAND이고 LAND는 마지막에만. 첫 항목은 TAKEOFF 또는 LAND. 따라서 LAND로 시작하는 미션은 길이 1이다.
- 항목 분류 함수(setpoint 항목과 모드 명령 항목)와 "모든 `TYPE_*`가 정확히 한 분류에 속한다"는 테스트를 core에 둔다(5단계 넘김).

PREPARING(첫 항목이 TAKEOFF)

| 단계 | 동작 | 통과 조건 | 실패 |
| --- | --- | --- | --- |
| P0 | 수신과 식별 | 네 토픽 수신, `vehicle_status`가 신선, 식별 대조 Match | 불일치 확정이면 즉시, 아니면 `ready_timeout`에 NOT_READY |
| P1 | 시작 조건 | `landed == true`이고 DISARMED | PRECONDITION_FAILED |
| P2 | EKF gate | `failsafe_flags`의 `local_position_invalid`, `local_altitude_invalid`, `global_position_invalid`, `home_position_invalid`가 모두 false | `ready_timeout`에 NOT_READY |
| P3 | 발행 시작 | 20 Hz로 `offboard_control_mode`(position만 true)와 `trajectory_setpoint`(TAKEOFF 목표점) | - |
| P4 | 신호 확인 | 발행 10회 이상이고 `offboard_control_signal_lost == false` | `offboard_signal_timeout`에 MODE_SWITCH_FAILED |
| P5 | Offboard | DO_SET_MODE를 0.5 s마다 재전송. ack가 거부이면 실패. `nav_state`가 OFFBOARD 3회 연속 | `mode_confirm_timeout`에 MODE_SWITCH_FAILED |
| P6 | arm | arm을 재전송. TEMPORARILY_REJECTED는 `arm_timeout` 안에서 재시도. ARMED 3회 연속이고 여전히 OFFBOARD | `arm_timeout`에, 또는 TEMPORARILY_REJECTED가 아닌 거부 ack에 ARM_REJECTED. 취소나 실패를 정한 tick에 arm 재전송을 즉시 멈춘다 |

- `ready_timeout` 하나가 P0과 P2를 덮는다(goal 접수 시각부터). px4가 낸 이름 `ekf_ready_timeout`을 이 이름으로 합친다.
- P1에서 지상 arm을 받지 않는 이유: arm 상태이고 OFFBOARD가 아닌 모드에서 P3이 목표점을 발행하면 Hold 중 0.4 m 끌림([실측])과 같은 setpoint 섞임이 생기고, Executor가 arm하지 않은 기체(QGC 등 외부에서 arm한 기체)를 넘겨받는 길이 열린다. 실측 없이 허용하지 않는다. 대가: REASON_DISARM_FAILED로 지상 arm이 남은 기체는 누군가 disarm해야 다음 TAKEOFF 미션을 받는다. px4-engineer 승인(2026-11-11): 허용으로 바꿀 이유를 찾지 못했다. 보강 근거는 실측 H와 K다. arm 뒤 이륙 램프가 시작되면 높이 0.07 m에서도 `landed`가 false가 되고 그 뒤로는 강제가 아닌 disarm이 거부된다([소스] `Commander.cpp` 644-662행). Takeoff 상태기는 rampup에서 뒤로 돌아가지 않는다([소스] `Takeoff.cpp` 77-87행). 남이 arm한 기체를 넘겨받으면 이 경계를 통제할 수 없다.
- Offboard가 먼저이고 arm이 나중이다. [소스] 시동 해제 상태의 모드 변경은 항상 허용되고 arm 때 "현재 모드에 신호가 없으면 거부"가 걸리므로, arm이 받아들여졌다는 것이 Offboard가 돌 수 있다는 뜻이다. [실측] 4회.
- `vehicle_command`는 식별 대조 Match 뒤에만 낸다. setpoint stream은 gate로 막지 않는다(1a 4단계 px4 조건). P0이 P3보다 앞이라 이 순서에서 자연히 지켜진다.
- `pre_flight_checks_pass`와 `vehicle_local_position.xy_valid`는 gate로 쓰지 않는다. [실측] 착륙 뒤 `nav_state`가 OFFBOARD로 돌아가 `pre_flight_checks_pass`가 false로 남으므로 그 값을 쓰면 두 번째 미션이 늘 NOT_READY가 된다.
- 성공 판정은 ack가 아니라 `nav_state`와 `arming_state`다. ack는 거부를 빨리 아는 데만 쓴다.

PREPARING(첫 항목이 LAND): P0 -> 시작 조건(armed이고 `landed == false`, 아니면 PRECONDITION_FAILED) -> P2 -> LAND 항목. Offboard 진입과 arm을 하지 않고 `offboard_control_mode`와 `trajectory_setpoint`를 한 번도 발행하지 않는다. `ready_timeout`으로 NOT_READY가 되면 기체는 공중에 있던 모드(보통 Hold)로 남고 그 뒤는 취소를 요청한 쪽과 PX4 failsafe의 몫이다.

항목

| 항목 | 시작 | 동작 | 완료 | feedback phase |
| --- | --- | --- | --- | --- |
| TAKEOFF | P6의 ARMED 확인 시점(항목 `timeout`이 여기서 흐른다) | 목표점은 P3에서 읽은 위치의 z만 `-height_m`. yaw는 항상 유한값(MODE_KEEP이면 그때의 heading). 처음부터 목표점을 보낸다 | `z_valid`이고 `abs(z - z_target) < acceptance_m` | EXECUTING |
| LOITER | 앞 항목 완료 | 직전 setpoint 유지(PX4 Hold 모드가 아니다) | ROS 시각으로 `duration` 경과 | EXECUTING |
| LAND | 앞 항목 완료 또는 PREPARING 끝 | 발행 중이면 유지한 채 NAV_LAND 재전송. AUTO_LAND를 처음 관측하면 발행 중단(다시 켜지 않는다). AUTO_LAND 3회 연속(`mode_confirm_timeout`, 넘기면 MODE_SWITCH_FAILED). 확인 전에는 모드 이탈 판정을 하지 않는다(아래 LAND 감시) | DISARMED 3회 연속. 대비책: `landed`인 채 `land_disarm_fallback_delay`(노드 파라미터) 동안 arm이면 강제가 아닌 disarm | WAITING_MODE |

- 모든 항목은 `timeout`을 넘기면 ITEM_TIMEOUT. 이때의 정리(px4-engineer 승인 2026-11-11, 수정 조건 넷 반영): setpoint 항목이면 취소와 같이 그 tick의 snapshot으로 분기를 고르고 매 tick 다시 고른다. 공중이면 Hold 분기(확인되지 않으면 Land를 보낸다), 지상 arm이면 disarm 분기(지상 setpoint. 쟁점 3 M5), 지상 disarm이면 바로 끝낸다(이 goal에서 arm을 보낸 적이 있으면 disarm 분기를 거친다. 1a에서 setpoint 항목이 있는 미션은 늘 arm을 보낸 뒤다). 어느 분기든 결과는 ABORTED이고 reason은 ITEM_TIMEOUT을 유지하며, Hold나 disarm이 확인되지 않았으면 `detail`에 적는다(REASON_MODE_SWITCH_FAILED나 REASON_DISARM_FAILED로 바꾸지 않는다).
  - LAND 항목의 ITEM_TIMEOUT(px4-engineer 문장): NAV_LAND 재전송을 멈춘다. 아직 발행 중이면(AUTO_LAND를 한 번도 관측하지 못함) 발행을 멈춘다. 그 뒤는 PX4의 offboard 손실 Land(`COM_OBL_RC_ACT=4`)가 내린다. Hold는 보내지 않는다. landed인 채 ARMED였으면 `detail`에 적는다.
    - `[LAND]` 한 항목 미션의 예외(px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 4번의 문장으로 바꿨다): 이 미션은 발행한 적이 없고 기체가 OFFBOARD가 아니므로 offboard 손실 Land가 걸리지 않는다. AUTO_LAND를 관측하지 못한 채 ITEM_TIMEOUT이 되는 것은 항목 `timeout`이 `mode_confirm_timeout`보다 짧을 때뿐이다. 이때 NAV_LAND가 도착하지 않았다면 기체는 있던 모드(보통 Hold)에, 도착했다면 AUTO_LAND(위치가 무효면 DESCEND)로 PX4가 착륙을 이어 간다. 어느 쪽인지 `detail`에 적는다. AUTO_LAND를 확인한 뒤의 ITEM_TIMEOUT도 PX4가 착륙을 이어 간다. [소스] `Commander.cpp` 1093-1110행(NAV_LAND는 force라 사용자 의도가 즉시 AUTO_LAND로 바뀐다), 1089-1091행(Land를 쓸 수 없는 상태면 DESCEND로 대체).
  - 지상 arm 분기에서 TAKEOFF가 `timeout`까지 땅을 뜨지 못했다는 것은 사실상 이륙 의도가 켜지지 않은 경우다(timestamp 문제 등. [소스] `MulticopterPositionControl.cpp` 466-467행). 이때 Takeoff 상태는 ready_for_takeoff에 머물러 disarm이 바로 받아들여진다([실측] G).
  - 지상 arm 분기가 필요한 이유(reviewer): TAKEOFF가 뜨지 못한 채 `timeout`이 되면 기체는 지상 arm이다. 여기서 Hold만 받고 끝내면 기체가 지상에 arm으로 남는다([소스] 이륙 이력이 없어 자동 disarm이 없다. `Commander.cpp` 2290, 2294행. `COM_DISARM_PRFLT=-1`). 그 상태에서는 `[LAND]`도 PRECONDITION_FAILED다.
- `latest_disarming_reason`은 판정에 쓰지 않는다([실측][소스] 메시지 상수가 내부 enum과 어긋난다).

P3b 착수 전 px4-engineer 승인 항목(reviewer 권고 3, 4): 2026-11-11에 다섯 모두 닫혔다(px4-engineer P3b 착수 전 승인 검토(git 이력). 판정과 반영 위치는 "px4-engineer 승인 반영"). PR #21로 main에 들어갔으므로 상태기 구현(P3b)을 시작할 수 있다.
- ITEM_TIMEOUT 뒤의 정리: 수정 조건부 승인. 위 문장.
- TAKEOFF의 시작 조건("지상이고 DISARMED". 지상 arm이면 PRECONDITION_FAILED): 승인.
- 지상 arm 분기에서 발행할 setpoint: 지상 setpoint로 확정(쟁점 3 M5).
- LAND 감시: 수정 조건부 승인. 보강 셋은 아래 LAND 감시.
- 감시 표의 방어용 분류와 "`landed` 뒤의 disarm은 지상 disarm": 승인. 조건은 아래 disarm 분류의 고정 규칙.

발행 규칙: `trajectory_setpoint`와 `offboard_control_mode`는 `nav_state`가 OFFBOARD이거나 Offboard로 들어가는 중(P3-P6)일 때만 발행한다. 모드 명령(NAV_LAND, Hold)을 보낸 뒤 그 모드를 처음 관측한 tick에 멈춘다. [실측] 착륙 중 발행을 유지한 2회는 착지 뒤 60-90 s 동안 `landed`가 나오지 않았고, 멈춘 2회는 약 1 s 뒤에 나왔다. 지상 arm 분기의 지상 setpoint도 이 규칙 안에 있다. 발행 중일 때만 바꿔 발행하고 멈춘 발행을 다시 켜지 않는다.

비행 중 감시(setpoint 항목 실행 중. 들어감은 3회 연속, 벗어남은 1회)

| 순위 | 관측 | reason | 동작 |
| --- | --- | --- | --- |
| 1 | `Px4Timestamp::now` 실패 | INTERNAL | 발행 중단, ABORTED |
| 2 | 식별 대조 불일치 | INTERNAL(M2) | 발행 중단, ABORTED |
| 3 | `vehicle_status`가 `link_timeout` 동안 없음 | LINK_LOST | 발행 중단, ABORTED |
| 4 | DISARMED이고 `landed == false`(아래 고정 규칙으로 읽은 값) | FAILSAFE | 발행 중단, ABORTED |
| 5 | DISARMED이고 `landed == true`(같은 고정 규칙) | 이 표본의 `failsafe`가 true이거나, 이 항목 실행 중 앞선 표본에서 `failsafe == true`를 한 번이라도 봤으면 FAILSAFE, 아니면 EXTERNAL_DISARM. 이 표본의 `nav_state`는 보지 않는다(아래) | 발행 중단, ABORTED. `detail`에 지상 disarm임을 적는다 |
| 6 | `nav_state != OFFBOARD`이고 `failsafe == true` | FAILSAFE | 발행 즉시 중단, ABORTED |
| 7 | `nav_state != OFFBOARD`이고 `failsafe == false`이고 `nav_state_user_intention != OFFBOARD` | EXTERNAL_MODE_CHANGE | 발행 즉시 중단, ABORTED |
| 8 | `nav_state != OFFBOARD`이고 `failsafe == false`이고 `nav_state_user_intention == OFFBOARD` | FAILSAFE(방어용. [소스] 정상 상태에서는 나오지 않는다) | 발행 즉시 중단, ABORTED |

- 한 tick에 여러 행이 맞으면 순위가 앞선 행이 이긴다. 순위는 같은 tick의 동률만 가른다. 조건이 엇갈려 시작하면(어느 tick에 한 행만 맞고 다음 tick에 순위가 앞선 행이 맞는 경우) 먼저 맞은 행이 그 tick에 goal을 끝내고, 그 뒤의 표본은 효과가 없다. 표 머리의 "들어감은 3회 연속, 벗어남은 1회"를 행별로 적으면: 순위 1, 2, 4-8은 모두 1회 판정이다(실패 한 번, 어긋난 표본 하나, 해당 표본 하나). 순위 3만 누적이다(마지막 `vehicle_status` 수신 뒤 ROS 시각으로 `link_timeout`). 3회 연속은 이 표가 아니라 확인(OFFBOARD, ARMED, AUTO_LOITER, AUTO_LAND, DISARMED)에 쓴다. 이 순위는 px4-engineer가 승인했고(px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 2번) 재실측 (4) 전까지는 잠정이다. 근거는 셋이다.
  - 순위 1-3은 나머지 행의 입력을 믿을 수 없게 하는 조건이다. 시각을 만들 수 없으면 발행 자체가 안 되고, 식별이 어긋난 `vehicle_status`는 이 기체의 것이 아닐 수 있으며, 상태가 끊기면 아래 행이 읽을 값이 없다. 앞 판은 식별 불일치가 아래에 있어 남의 기체의 표본으로 FAILSAFE가 먼저 나갈 수 있었다(reviewer).
  - 순위 4-5(arming 상태)가 6-8(모드)보다 앞이다. disarm된 뒤의 `nav_state`는 확인된 사실이 없다. px4 보고의 "지상에서 외부 disarm되면 `nav_state`는 OFFBOARD로 남는다"는 실측이 없고, 한 표본이라도 OFFBOARD를 벗어나면 모드 행이 먼저 걸려 방어용 FAILSAFE(순위 8)가 된다(reviewer). arming 상태를 먼저 보면 `nav_state`가 어떻게 되든 같은 reason이 나온다.
  - 순위 6-8은 조건이 서로 겹치지 않아 그 안의 순서는 뜻이 없다. 순위 4와 5도 겹치지 않는다.
  - 순위 5의 `failsafe` 가지(px4-engineer 수정 조건을 reviewer 지적으로 다시 적었다. px4-engineer 확인 2026-11-11, px4-engineer 최종 확인(git 이력) 1번 승인): 지금 표본의 `failsafe`만 보면 자동 disarm에서는 이 가지가 걸리지 않는다. [소스] `Commander.cpp` 1843행 `handleAutoDisarm()`이 1866행 근처 `handleModeIntentionAndFailsafe()`보다 앞에서 disarm하고, 후자는 `state.armed = isArmed()`(2346행 근처)로 읽으며 `framework.cpp` 452-455행은 disarm이면 `Action::None`이다. 그래서 자동 disarm 주기의 첫 DISARMED 표본은 `failsafe == false`이고 `nav_state`는 의도로 되돌아가 있다.
    - px4-engineer의 앞 문장은 "이 항목 실행 중 `failsafe == true`이거나 `nav_state`가 OFFBOARD가 아닌 표본을 한 번이라도 본 적이 있으면 FAILSAFE"였다. 그런데 이 표는 벗어남을 1회로 판정하므로 OFFBOARD가 아닌 ARMED 표본은 순위 6-8에서 그 tick에 goal을 끝낸다. 앞선 표본의 "OFFBOARD 아님" 이력은 생길 수 없다(reviewer. px4-engineer도 앞 문장이 틀렸다고 확인했다).
    - 정한 것: 이력에 지금의 DISARMED 표본을 넣지 않는다. 그 표본의 `nav_state`는 보지 않는다. 넣으면 외부 disarm 뒤 `nav_state`가 OFFBOARD를 떠나는 경우가 모두 FAILSAFE가 되어 EXTERNAL_DISARM이 나오지 않게 되고, 순위 4-5를 모드 행보다 앞에 둔 이유(disarm 뒤의 `nav_state`는 확인된 사실이 아니다)와도 어긋난다.
    - 이 가지가 걸리는 경우(px4-engineer 문장): 이 표본의 `failsafe`가 true인 DISARMED는 명령 disarm과 failsafe 동작 Disarm(`COM_OBL_RC_ACT`가 Disarm인 경우, GCS 손실 Disarm. `Commander.cpp` 2375-2377행)에서 나온다. 앞선 표본의 `failsafe` 이력은 v1.17.0에서 OFFBOARD인 채로는 생기지 않으므로([소스]) 이 가지는 방어용이다. failsafe 동작 Disarm에서는 `nav_state`가 OFFBOARD로 남고 `landed`에 따라 순위 4나 5의 FAILSAFE가 된다. 이 프로젝트의 SITL 파라미터는 Land라 이 경로에 닿지 않는다.
    - 이력 가지의 테스트는 합성 표본으로만 할 수 있다(실제 PX4 v1.17.0에서는 만들 수 없다).
    - 덮지 못하는 경우: failsafe Land로 OFFBOARD를 벗어난 ARMED 표본을 노드가 놓친 채 자동 disarm된 경우뿐이다. [소스] failsafe가 걸리는 주기에 `nav_state`와 `failsafe`가 바뀌면 `vehicle_status`가 즉시 publish되고(`Commander.cpp` 1941-1945행) 자동 disarm(`COM_DISARM_LAND` 2 s)은 그 뒤이므로, 그 표본은 보통 순위 6에서 goal을 끝낸다. 놓치는 것은 수신이 끊겼거나, tick당 최신 표본 1개 모델에서 50 ms 안에 표본이 연달아 온 경우다. 그때의 첫 DISARMED 표본은 외부 disarm과 구별할 값이 없어 EXTERNAL_DISARM이 된다. 의미 문장이 "원인은 판정하지 않는다"이므로 틀린 말이 되지는 않는다.
- disarm 분류의 고정 규칙(px4-engineer 조건. px4-engineer P3b 착수 전 승인 검토(git 이력) 5번): disarm의 분류(지상 대 공중)는 처음 관측한 DISARMED 표본의 tick에, 그때까지 받은 최신 `landed` 값으로 정하고 고정한다. 뒤에 오는 `landed` 표본으로 바꾸지 않는다. 이 규칙은 감시 표의 두 DISARMED 행, LAND 감시의 완료 우선 규칙, 취소의 Hold 확인 창에서 본 DISARMED에 모두 쓴다. 근거: [소스] `MulticopterLandDetector.cpp` 249, 287, 296행(`return !_armed || ...`)과 318-320행(LNDMC_TRIG_TIME/3 지연). 공중에서 disarm돼도 약 0.33 s 뒤 `landed`가 true로 바뀌어 발행된다. 고정하지 않으면 공중 disarm이 지상 disarm(CANCELED 또는 완료)으로 잘못 분류될 수 있다.
- 지상 DISARMED 행(순위 5. px4-engineer P3b 착수 전 승인 검토(git 이력) 추가 문제 3): TAKEOFF가 뜨기 전에 외부에서 disarm되면 모드 행에 걸리지 않을 수 있다. 이 행이 없으면 ITEM_TIMEOUT까지 발행이 이어진다. disarm 뒤의 `nav_state`는 확인된 사실이 아니다. px4-engineer가 앞 보고의 "`nav_state`는 OFFBOARD로 남는다"를 [소스]에 기댄 추정으로 정정했다(px4-engineer PR #23 반영 확인(git 이력). `UserModeIntention.cpp` 78-84행과 94-101행, `framework.cpp` 452-455행. OFFBOARD가 `modePreventsArming`에 걸리는지는 확인하지 못했다). 실측(재실측 (4)) 전에는 사실로 쓰지 않으며, 순위 4-5를 모드 행보다 앞에 둔 것이 이 불확실성을 덮는다. reason을 새 상수 REASON_EXTERNAL_DISARM으로 둔 이유는 "px4-engineer 승인 반영"의 architect 결정에 있다.
- 방어용 분류(순위 8)는 px4-engineer 승인. [소스] `framework.h` 150행: `inFailsafe`는 None과 Warn이 아닐 때 참이다. `framework.cpp` 684-690행: None과 Warn에서는 `nav_state`가 사용자 의도와 같다. `Commander.cpp` 2369-2372, 2388행.
- OFFBOARD이고 ARMED인 채 `failsafe == true`인 표본은 어느 행에도 걸리지 않고 goal을 끝내지 않는다. 표대로가 의도다(architect 확인. test-engineer P3 조건부 승인(git 이력) 2절 (ii). px4-engineer 확인 2026-11-11, px4-engineer 최종 확인(git 이력) 2번 승인). [소스]로는 정상 상태에서 나오지 않는다. None과 Warn이 아니면 failsafe 동작이 모드를 바꾼다. 예외는 Disarm(같은 주기에 DISARMED 표본이 된다)과 Terminate(`nav_state`가 TERMINATION이 된다)다. `COM_FAIL_ACT_T`의 지연 중에는 선택된 동작이 Hold라 AUTO_LOITER와 `failsafe` true로 순위 6에 걸린다. 만약 나왔다면 goal을 계속하는 것이 안전하다. 모드를 바꾸지 않는 failsafe이고, 발행을 멈추면 offboard 손실 failsafe를 스스로 일으킨다. 다음 표본의 모드 이탈은 순위 6-8이 잡는다. 그 표본의 `failsafe`는 순위 5의 이력에 남는다.
- failsafe로 OFFBOARD를 벗어난 표본(순위 6)을 보면 즉시 멈추는 이유: [실측] offboard 손실 Land 중에 발행만 다시 시작하자 모드 명령 없이 0.07 s 만에 OFFBOARD로 돌아갔다(1회). Executor가 발행을 이어 가면 착륙 중인 기체가 다시 올라간다.
- LAND 항목(WAITING_MODE)의 감시는 세 구간으로 나뉜다. px4-engineer가 세 구간과 완료 우선 규칙을 승인했고(2026-11-11) 보강 문장 셋을 반영했다.
  - 확인 전(NAV_LAND를 보낸 뒤 AUTO_LAND 3회 연속까지): 모드 이탈 판정을 하지 않는다. 항목 시작 때의 `nav_state`는 AUTO_LAND가 아니기 때문이다(정식 미션이면 OFFBOARD, `[LAND]` 한 항목 미션이면 보통 AUTO_LOITER). 이 구간에서 보는 것은 `mode_confirm_timeout`(MODE_SWITCH_FAILED), 상태 없음(LINK_LOST), 항목 `timeout`뿐이다. 발행 규칙은 이 구간에서도 그대로 적용한다. OFFBOARD도 AUTO_LAND도 아닌 표본을 보면 발행을 멈추고 다시 켜지 않는다. 이탈 판정은 하지 않고 NAV_LAND 재전송과 `mode_confirm_timeout`만 이어 간다.
  - AUTO_LAND 확인(3회 연속)은 `failsafe` 값과 무관하게 `nav_state == AUTO_LAND`로 센다. offboard 손실 Land 중인 기체에 보낸 `[LAND]`도, 흔들림 뒤 발행 중단으로 생긴 failsafe Land도 정상 경로다.
  - 처음 관측과 3회 연속 사이의 흔들림: AUTO_LAND를 한 번 본 뒤 다른 모드 표본이 오면 연속 계수를 0으로 되돌릴 뿐 이탈로 보지 않는다. 멈춘 발행은 다시 켜지 않고(켜면 Offboard로 돌아갈 수 있다) NAV_LAND 재전송을 이어 가며, `mode_confirm_timeout`은 NAV_LAND를 처음 보낸 시각부터 그대로 흐른다.
  - 확인 뒤: 모드 이탈 판정은 ARMED인 동안만 적용한다. ARMED인데 AUTO_LAND에서 벗어나 다른 모드가 되면 EXTERNAL_MODE_CHANGE(`failsafe`이면 FAILSAFE).
  - 어느 구간에서든 DISARMED이고 `landed`이면 `nav_state`가 무엇이든 이탈로 보지 않고 완료 계수(DISARMED 3회 연속)가 우선한다. 이유: [실측] 자동 disarm과 동시에 `nav_state`가 AUTO_LAND를 떠나 사용자 의도의 모드로 돌아간다(`UserModeIntention`의 disarm 처리. px4-engineer 의견서(git 이력) 44행). 1회 이탈 규칙을 그대로 쓰면 정상 착륙이 EXTERNAL_MODE_CHANGE로 끝난다. `landed`가 아닌 채 DISARMED는 FAILSAFE다. 여기의 `landed`는 위 disarm 분류의 고정 규칙으로 읽는다.
  - 완료 우선 규칙이 두 경우를 다 덮는 근거([소스] px4-engineer): 정상 착륙에서 "ARMED인데 AUTO_LAND가 아닌" 표본은 나오지 않는다. 자동 disarm(`Commander.cpp` 1843행 handleAutoDisarm, 675행 onDisarm)이 같은 주기의 `nav_state` 계산(1866, 2369-2372행)과 발행(1945행)보다 앞서므로 DISARMED와 새 `nav_state`가 한 표본에 같이 온다. 대비책 disarm처럼 명령으로 내는 disarm은 `nav_state` 계산 뒤에 처리되어(1898행) "DISARMED + AUTO_LAND" 표본이 한 번 나온 다음 `nav_state`가 바뀐다.
- CANCELING 중에는 위 표를 쓰지 않고 쟁점 3의 분기만 본다.

명령 재전송 규칙(px4-engineer가 정한 값. px4-engineer P3b 착수 전 승인 검토(git 이력)): 대기 중인 명령은 한 번에 하나다. 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 즉시 지운다. ack는 `command`와 `target`으로 맞춘다. 주기는 `command_resend_period`(0.5 s)다.

| 명령 | 재전송을 멈추는 때 | 거부 ack |
| --- | --- | --- |
| DO_SET_MODE(Offboard) | OFFBOARD 3회 연속, 타임아웃 | ACCEPTED가 아니면 MODE_SWITCH_FAILED |
| ARM | ARMED 3회 연속, 타임아웃, 취소나 실패를 정한 tick(즉시) | TEMPORARILY_REJECTED는 재시도, 그 밖의 거부는 ARM_REJECTED |
| Hold | AUTO_LOITER 3회 연속, `hold_confirm_timeout` | 거부면 즉시 Land 경로 |
| NAV_LAND(LAND 항목) | AUTO_LAND 3회 연속, `mode_confirm_timeout`(MODE_SWITCH_FAILED), ITEM_TIMEOUT | force라 거부가 없다([소스] `Commander.cpp` 1093-1110행) |
| NAV_LAND(M4의 Land 경로) | AUTO_LAND를 처음 관측한 tick(그 tick에 ABORTED로 끝난다), `mode_confirm_timeout` | NAV_LAND(LAND 항목) 행과 같다(force라 거부가 없다) |
| DISARM(지상 arm 분기) | DISARMED 3회 연속, `landed` false로 분기 전환, `mode_confirm_timeout`, `link_timeout`(상태 끊김) | TEMPORARILY_REJECTED여도, 그 밖의 거부여도 `landed`인 동안 재시도. 그 자리에서 끝내지 않는다 |
| DISARM(LAND 대비책) | DISARMED 3회 연속(항목 완료), 항목 `timeout`(ITEM_TIMEOUT). 따로 타임아웃을 두지 않는다. `landed == true`이고 `land_disarm_fallback_delay`가 지난 뒤에만 시작한다 | DISARM(지상 arm 분기) 행과 같다(거부 ack는 종류와 무관하게 `landed`인 동안 재시도) |

- 같은 명령을 여러 번 받아도 결과가 같다. 이미 disarm된 기체에 보낸 disarm은 ACCEPTED다([소스] `Commander.cpp` 640-642, 976-980행. [실측] D).
- arm을 보낸 뒤의 DISARM 확인은 disarm 전송 뒤에 받은 표본만 센다(쟁점 3 M5).
- px4-engineer의 표는 NAV_LAND와 DISARM이 한 행씩이었다. 경우를 가른 행(M4의 Land 경로, LAND 대비책)과 NAV_LAND 행의 `mode_confirm_timeout`은 이 문서의 다른 곳에 이미 있던 규칙을 architect가 표에 옮긴 것이다(px4-engineer 확인 2026-11-11, px4-engineer PR #23 반영 확인(git 이력) 5번 승인. 강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 거부되므로 대비책 disarm이 공중 기체를 끌 위험은 없다).

끝난 뒤 기체 상태(7단계 `docs/interface.md`의 reason별 "ABORTED 뒤 기체 상태" 표에 넣을 줄. 표 전체는 7단계에 px4-engineer와 만든다)

| 끝난 방식 | 기체 상태 | 근거 |
| --- | --- | --- |
| 지면 바로 위에서 Hold로 끝난 ITEM_TIMEOUT 또는 CANCELED | ARMED, `landed` false인 채 지상이나 지면 근처에 머문다. 스스로 disarm되지 않는다(12 s 관찰). 이어 보낸 `[LAND]` 미션은 시작 조건(armed이고 `landed` false)을 통과한다 | [실측] Hold로 끝나는 경로의 표본은 X2a 1.8 s 1회와 X2b 1회(각 12 s 관찰, 스크립트가 보낸 명령). 같은 Hold 상태에서 스크립트가 보낸 NAV_LAND 3회가 disarm까지 갔다. Executor가 보낸 `[LAND]`는 미실측 |

source 값 표(1a 4단계 넘김 (1))

| 주체 | source_system | source_component |
| --- | --- | --- |
| `idsim_mission` Executor | 254 | 191 |
| SITL 통합 테스트 fixture | 254 | 25 |
| 스모크 `check_px4.py` | 254 | 1 |

- 규칙: source_system은 어떤 기체 sysid와도 같지 않다(빌더가 거부한다. 쟁점 5). 255와 component 190은 쓰지 않는다. Executor의 값은 노드 선언 기본값이다(역할 상수라 생성하지 않는다).

SITL 파라미터는 바꾸지 않는다. `Dockerfile.px4`도 바꾸지 않는다.

닫힌 넘김 항목: 1a 4단계의 (1) source 표, (2) position flag 고정(쟁점 5의 헬퍼), (3) `/clock` 지연과 `COM_OF_LOSS_T` 여유([실측] 노드 sim 시각 - `vehicle_status.timestamp` 최대 180 ms, 여유 약 0.77 s. 회귀 판정은 시나리오 A의 단정과 fixture 사전조건), (4) 신호 없는 Offboard 요청([실측] 시동 해제면 ACCEPTED이고 그 상태의 arm이 TEMPORARILY_REJECTED). 5단계의 Hold 실험, failsafe 파라미터 기본값 대조, `acceptance_m` 0.3 m, Offboard 상승 속도 제한([소스] `MPC_Z_VEL_MAX_UP`), land 완료 판정.

실측하지 않고 남는 것: 위치 무효에서 Hold가 거부되는 경로(계약 분기는 ack와 `nav_state`로 이미 덮는다), arm 상태에서 신호 없는 Offboard 요청, CI 4 vCPU 조건. 모든 실측은 경우마다 1-4회이고 16 vCPU 호스트 한 대에서 했다.

## 쟁점 5. idsim_common 추가 항목

결정: 아래를 `idsim_common`에 더한다. 소유는 ros2-engineer, PX4 필드 표는 px4-engineer가 승인한다. P2(단독 PR)다.

| 항목 | 내용 | 테스트 |
| --- | --- | --- |
| `VehicleId` | `parse(text)`: ROS 이름 토큰 하나("/" 없음, 비어 있지 않음). `matches(VehicleNamespace)`: ns == "/" + id. N을 뽑지 않는다 | 다중 토큰, 앞 "/", 빈 문자열 거부. 일치와 불일치 |
| vehicle params 해석 | `parse_vehicle_params(id, ns, sysid)`(순수 함수)와 노드에서 선언하는 얇은 `declare_vehicle_params(node)`. key는 `vehicle.id`, `vehicle.ns`, `vehicle.sysid` | 순수 함수만(노드 생성 없음) |
| Options overload | `px4::create_subscription`, `create_publisher`가 `SubscriptionOptions`, `PublisherOptions`를 받는 판(callback group 지정용). 이름과 QoS 고정은 그대로 | 컴파일 확인 |
| setpoint 헬퍼 | `offboard_position_mode(Px4Timestamp)`: position만 true. `position_setpoint(Px4Timestamp, ned, yaw_ned)`: 위치와 yaw가 유한해야 하고(아니면 nullopt) velocity, acceleration, jerk, yawspeed는 NaN | 필드 표 대조, 비유한 거부 |
| 사건 QoS | `event_pub_qos()`, `event_sub_qos()`: RELIABLE, VOLATILE, KEEP_LAST 10 | 호환 검사, TRANSIENT_LOCAL 구독 대 이 발행은 불일치 |
| 빌더 `make` | `VehicleCommandBuilder`의 public 생성자를 없애고 `static std::optional<VehicleCommandBuilder> make(VehicleIdentity, CommandSource)`. `source.system() == target.sysid`이면 nullopt | 거부 1건, 기존 테스트 두 곳 수정 |

- 넣지 않는 것: `nav_state`와 `arming_state` 분류(PX4 의미라 `idsim_mission`의 `px4/`), action과 사건 토픽 이름 조립(노드가 `/px4_N` 네임스페이스에서 상대 이름 상수를 쓰면 필요 없다. `idsim_common`은 `idsim_interfaces`에 의존하지 않는다), source 값(노드 params).
- setpoint 헬퍼를 `idsim_common`에 두는 이유: /fmu/in 발행 API와 같은 곳이어야 position flag 고정이 우회되지 않는다(px4, ros2 같은 의견).
- `px4-api` lint 범위를 넓힌다(1a 4단계 미해결 항목의 답): `ros_ws/src/**/*.yaml`, launch 파일(`.py`는 이미 대상), 생성기 golden의 `params/*.yaml`. /fmu 문자열이 나오면 실패. devops-engineer가 P4에서 한다.

## 쟁점 6. idsim_mission의 소유

결정
- `ros_ws/src/idsim_mission/`은 ros2-engineer 소유다(패키지 골격, core의 검증과 상태기와 종료 결과, 노드 껍질, launch).
- 예외: `include/idsim_mission/px4/`, `src/px4/`, `test/px4/`는 px4-engineer 소유다(px4_msgs -> snapshot 변환, `nav_state`와 `arming_state`와 준비 판정 술어, ack 해석).
- 경계인 snapshot 구조체 헤더(`include/idsim_mission/core/snapshot.hpp`)는 ros2 소유이고 px4-engineer가 필수 승인자다. 승인 때 볼 것에 넣는다: "disarm 전송 뒤 받은 표본"의 기준을 core가 판정하려면 `vehicle_status.timestamp`와 명령에 실은 `Px4Timestamp`(또는 둘을 비교한 결과)가 경계를 넘어와야 한다. 지상 setpoint z 오프셋도 같은 경계로 넘어온다.
- core 입력 계약(test-engineer C1): core의 `step()`은 (tick 번호, ROS 시각, 최신 표본 1개와 그 `timestamp`와 수신 tick, `Px4Timestamp` 공급 port(실패 가능), 명령 sink, setpoint sink, 사건 sink)만 입력으로 받는다. core는 벽시계와 rclcpp를 부르지 않는다. core 테스트 target은 gtest와 core만 링크한다. 구독 callback은 최신 표본만 저장하므로 tick당 표본은 최대 1개이고, 같은 `timestamp`가 두 번 보이는 것은 같은 표본을 다음 tick에 다시 본 경우다. 감시 표 순위 1(`Px4Timestamp::now` 실패), "첫 disarm 전송 tick", "명령에 실은 `Px4Timestamp`"는 이 port로만 결정적으로 시험할 수 있다. 표본이 토픽 넷으로 나뉘는 것을 이 입력 모델에 어떻게 담을지는 ros2-engineer가 snapshot 헤더에서 정하고 px4-engineer와 test-engineer가 승인한다.
- 상태기는 ros2-engineer가 이 문서의 전이 표대로 구현한다. 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자, 테스트 구조는 test-engineer가 승인자다. 타임아웃 기본값과 재전송 주기 같은 PX4 절차 값은 px4-engineer가 정한다.

근거: 상태기 한 파일을 두 소유자가 나눠 가지면 수정 권한이 모호하다. 상태기는 PX4 enum을 보지 않는 순수 클래스이고 PX4 의미는 어댑터 한 곳에 모인다(PX4 태그를 올릴 때 바뀌는 곳이 어댑터뿐이다). CLAUDE.md 표의 "px4-engineer: `idsim_mission`의 PX4 인터페이스"와 맞는다. PX4 절차의 정확성은 소유가 아니라 필수 승인으로 지킨다.

px4-engineer의 수용 조건(모두 받는다): core는 px4_msgs를 include하지 않는다(`idsim_mission_core` 대상이 px4_msgs에 의존하지 않게 CMake로 강제하고 단위 테스트가 그 대상만 링크한다). 모드 명령 송신, 발행 중단 시점, 3회 연속의 의미를 바꾸는 전이 표 수정은 px4-engineer 승인 없이 머지하지 않는다. 타임아웃 기본값은 px4-engineer가 값을 정하고 변경의 필수 승인자다(값이 적힌 노드 파일의 소유는 ros2-engineer다. px4 X6의 "내 소유"는 이 뜻으로 받았다). 어댑터 단위 테스트의 fixture 값은 px4 실측 로그에서 뽑는다.

기각한 안: 상태기의 PX4 절차 부분을 px4-engineer가 소유(ros2 초안 1-8). 파일 단위로 나뉘지 않는다. ros2와 px4 둘 다 수용했다.

## 쟁점 7. MissionEvent QoS와 goal 전 gate

결정
- 계약 QoS는 5단계 그대로 RELIABLE, VOLATILE이다. TRANSIENT_LOCAL로 바꾸지 않는다.
- 통합 테스트의 goal 전 gate(모두 `/clock` 기준 상한 안에서): `/clock` 수신과 `now() > 0`, 자기 `mission_event` 구독의 `get_publisher_count() >= 1`, PX4 구독들의 `get_publisher_count() >= 1`, action client의 `server_is_ready()`, 기대 sysid의 `vehicle_status` 표본 1회 이상, 시나리오의 사전조건(지상, disarmed. `nav_state` 값은 사전조건에 넣지 않는다).
- 순서 규칙(필수 조건이다. [실측] P3a): 테스트는 `mission_event` 구독을 action client보다 먼저, 같은 노드(같은 participant)에서 만든다. 순서를 어기면 ACCEPTED가 빠진다(대조군 87/400. 새 프로세스 71/200, 새 노드 16/200). `tests/support`의 해당 코드에 이유를 주석으로 남긴다. 구독과 client를 다른 프로세스에 두는 구성은 재지 않았고 쓰지 않는다.
- 구독 쪽 `get_publisher_count() >= 1` gate는 사건 수신을 보장하지 않는다([실측] 누락 87건이 모두 이 조건을 만족했다). gate에는 남기되 "사건이 온다"의 근거로 쓰지 않는다. 수신을 받치는 것은 위 순서 규칙이다.
- 누락 계수 실험(P3a, ros2-engineer): "구독 생성 -> client 생성 -> 즉시 goal"을 200회 돌려 ACCEPTED 사건이 빠진 횟수를 센다(gate 없이 가장 나쁜 순서). 결과를 progress에 남기고, 0이 아니면 이 쟁점을 다시 연다. 결과(P3a 실행 확인 결과(git 이력)): 0/400(새 프로세스 200회, 새 노드 200회). 이 쟁점을 다시 열지 않는다.
- graph 조회(`count_publishers`, `get_publishers_info_by_topic`)는 맺어짐의 판정에 쓰지 않는다. 계약 QoS의 대조(Executor의 `mission_event` 발행이 RELIABLE, VOLATILE인지)에만 쓴다.
- lifecycle `get_state` 호출은 gate에 넣지 않는다.
- goal 응답은 accepted인데 ACCEPTED 사건이 없으면 `EVENT_MISSING`으로 실패시키고 재시도하지 않는다. Executor는 ACCEPTED를 낼 때 사건 발행자의 `get_subscription_count()`를 debug 로그에 남긴다.

근거
- [실측] ros2 M1, M3. QoS가 맞지 않아도 graph에는 발행자가 1로 보이고 구독의 matched 수는 0이다.
- TRANSIENT_LOCAL을 받지 않는 이유는 5단계와 같다(지난 실행의 사건이 새 구독자에게 현재 사건으로 보인다). logging-engineer가 재질문 답에서 다시 제안했지만 5단계 PR 검토에서 VOLATILE에 동의했던 사안이고 새 근거가 없다. `MissionEvent`의 고정 시점은 Phase 2 완료이므로 Phase 2 기록 설계에서 다시 올릴 수 있다(넘김 목록).
- 남는 위험([실측] P3a의 대조군에서 실제로 일어났다. 누락 87건 모두 Executor 쪽 `get_subscription_count()`가 0이었다. 순서 규칙을 지킨 실험군에서는 0/400. 0/400은 누락률의 95% 상한 약 0.75%를 뜻하고 16 vCPU 호스트 한 대의 값이다. 순서 규칙이 이 틈을 막는 기전은 [추정]이다: goal 요청이 서버에 닿으려면 서버가 client의 writer를 알아야 하고, 같은 participant에서 그 공지는 먼저 만든 구독의 공지 뒤에 간다. 그래서 goal이 닿았을 때는 서버가 구독도 이미 알고 있다): DDS의 match는 양쪽이 따로 한다. 구독 쪽이 맺어졌어도 Executor의 writer가 그 구독을 아직 모르면 그 사이의 ACCEPTED는 오지 않는다. 테스트에서 writer 쪽을 볼 방법이 없다. 구독을 session 시작에 걸고 그 뒤 action 서버 준비와 PX4 표본을 더 기다리므로 틈은 작다고 본다. 발생하면 `EVENT_MISSING`과 Executor의 debug 로그가 증거가 되고, 그때 이 쟁점을 다시 연다.

## 쟁점 8. 테스트의 /fmu/in 쓰기

결정
- Python으로 한다. `tests/support/px4_raw.py` 한 모듈만 PX4 토픽의 발행자를 만든다. 허용은 둘이다: `offboard_control_mode`(시나리오 T. context manager로만 만들고 끝나면 destroy), `vehicle_command`(비상 정리 전용. source가 (254, 25)가 아니면 생성 거부. 기대 sysid의 `vehicle_status`를 받아 대조한 뒤에만 발행한다). 테스트는 `trajectory_setpoint`를 발행하지 않는다.
- timestamp는 `Px4Timestamp`와 같은 변환(ROS 시각 ns / 1000)을 쓰고 그 변환을 단위 테스트로 고정한다.
- Python 쪽 PX4 토픽 이름(1a 4단계 넘김): `tests/support`에 `px4_topic(ns, direction, base, msg_cls)` 한 함수. 접미사는 `getattr(msg_cls, "MESSAGE_VERSION", 0)`에서 만든다. golden `topics.txt`와 양방향 일치 pytest를 둔다. 통합 테스트 코드에 버전 접미사가 붙은 이름이나 /fmu 문자열을 쓰지 않는다. 스모크의 정규식은 그대로 둔다.
- `px4-api` lint는 지금 `tests/`를 보지 않는다. P4에서 `tests/sitl/`과 `tests/support/`를 대상에 넣고 예외를 `tests/support/px4_raw.py`와 `px4_topic`이 든 파일로만 둔다(devops, test 승인. `px4_raw.py`의 변경은 px4-engineer가 필수 승인자다).
- Executor에 테스트 전용 파라미터나 우회 경로를 두지 않는다.

근거: 묵은 timestamp 판정은 `Px4Timestamp`를 우회해야만 만들 수 있어 C++ 노드로 가도 `idsim_common` 밖의 우회가 필요하다. 그러면 별도 실행 파일과 빌드 대상만 늘고 얻는 것이 없다. 스모크 px4-in이 이미 Python으로 `vehicle_command`를 발행하는 선례가 있다. 발행 허용 목록은 "실수 방지 수준이며 보안 경계가 아니다"(roadmap 4번).

기각한 안: `tests/` 아래 별도 C++ 테스트 노드(ros2 A9의 한 갈래). 위 근거.

## 쟁점 9. 시나리오와 완료 기준

결정: 한 스택에서 아래 순서로 돌린다(test 재질문 답의 순서).

| 시나리오 | 내용 | 판정 요지 | 1a 필수 |
| --- | --- | --- | --- |
| B. 무효 미션 | GOTO가 든 미션 | ABORTED, INVALID_MISSION. 접수와 종료 사건. feedback 0건. 일정 ROS 시간 동안 disarmed 유지 | 예 |
| C. id 불일치 | goal의 `vehicle_id`가 다른 값 | ABORTED, VEHICLE_ID_MISMATCH. 사건의 `vehicle_id`는 Executor 자신의 값. feedback 0건 | 예 |
| A. 정상 | `[TAKEOFF 5 m, LOITER 5 s, LAND]`, 콜드 상태 | 접수 -> ARMED -> 고도 도달 -> LOITER 유지 -> AUTO_LAND -> DISARMED -> SUCCEEDED. 이정표의 순서와 ROS 시각 단조 증가. 사건 짝과 result 일치. TAKEOFF와 LOITER 동안 `failsafe`가 한 번도 true가 아니고 `nav_state`가 OFFBOARD | 예 |
| D. 공중 취소 | 고도 도달 뒤 cancel. 이어서 `[LAND]` 한 항목 미션 | AUTO_LOITER 3회 연속, CANCELED와 REASON_NONE, 그 뒤 일정 시간 고도 유지. `[LAND]`가 SUCCEEDED이고 DISARMED. 두 번째 비행이라 시작 상태가 OFFBOARD, disarmed다. [실측] Hold(발행 없음)에서 NAV_LAND는 1회 확인됐다 | 예(U1) |
| T. 묵은 timestamp | 지상, 비행 없음, Executor idle | `offboard_control_mode`(`position=true`)만 20 Hz 발행. timestamp가 현재이면 `offboard_control_signal_lost` false, `now - 2 s`이면 true, 다시 현재이면 false. 양방향 전이를 단정한다 | 예 |

- 각 시나리오 시작 전에 사전조건(지상, DISARMED N회 연속)을 단정하고 어긋나면 그 자리에서 실패한다(앞 시나리오의 잔재를 숨기지 않는다).
- "disarm 확인"은 ARMED를 본 뒤의 DISARMED여야 한다(시작 때 이미 DISARMED라 순서를 보지 않으면 vacuous하다).
- "도달"의 입력은 goal의 목표값과 `vehicle_local_position`(goal 직전의 z0 기준, `z_valid`)이다. 노드가 낸 setpoint는 판정 입력으로 쓰지 않는다(노드와 테스트의 오류가 상관된다). architecture.md의 "setpoint 거리" 문구를 고친다.
- N은 3이다(스모크와 같다). N의 단위는 메시지 수이고, 유지 구간이 필요한 곳은 ROS 시각 경과로 따로 단정한다.
- fixture 사전조건에 `/clock` 정렬을 넣는다: `use_sim_time` 노드 시각 - `vehicle_status.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s. progress의 "clock에 넣을지" 항목은 이것으로 닫는다(clock에는 `use_sim_time` PX4 수신 노드가 없다).
- T의 각 단계 대기 상한은 ROS 시각 5 s다(`failsafe_flags`는 5 Hz 상한이고 변화가 없으면 500 ms 주기일 수 있어 3회 연속에 1.5 s 이상이 든다).
- T가 맨 뒤인 이유: T의 발행자나 신호 상태가 뒤 시나리오의 Offboard 진입을 오염할 수 없다. T의 대조군(현재 timestamp에서 false)이 없으면 발행자가 없을 때의 true와 구분되지 않는다. T는 1a 4단계가 넘긴 "sim 시간 timestamp 경로의 회귀 판정"이고 `UXRCE_DDS_SYNCT`가 실수로 1로 돌아가면 실패한다. arm 명령을 보내지 않는 flag 판정으로 한 것은 테스트가 기체에 보내는 명령을 줄이기 위해서다(px4 5.1 가안의 변형. [소스] 같은 `data_is_recent` 경로를 지난다). `failsafe_flags`는 5 Hz 상한으로 주기 발행되므로 "3회 연속"으로 센다. 발행 전에 발행자의 `get_subscription_count() >= 1`을 확인한다. 대조군 단계가 `local_position_invalid`가 참인 경우(timestamp와 무관하게 true)를 걸러 준다.
- 통합에서 하지 않고 core 단위 테스트로 덮는 것: BUSY, 지상 취소, NOT_READY, failsafe, EXTERNAL_MODE_CHANGE, EXTERNAL_DISARM, LINK_LOST, ARM_REJECTED, MODE_SWITCH_FAILED, DISARM_FAILED, ITEM_TIMEOUT, Hold 실패 뒤 Land, status와 reason 대응표, 종료 사건 == result, `[LAND]` 미션이 setpoint를 발행하지 않음, LAND로 시작하면 길이 1.
- 노드 배선 테스트(PX4 없이, rclcpp GoogleTest 하나): 가짜 PX4 발행자로 정상 한 경로와 무효 한 경로만.
- "3회 연속 통과"의 정의: 같은 commit, 같은 이미지 key에서 `run_sitl.sh --repeat 3`의 세 회가 모두 통과. 회마다 콜드 스택. 실패가 나오면 0부터 다시 센다. pytest rerun과 shell 재시도는 쓰지 않는다. 회차 요약(`repeat_summary.tsv`: 실행 id, commit과 dirty, 이미지 key, 시나리오별 verdict, 이정표별 ROS 시각 소요, 벽시계 소요)을 남긴다.
- 판정 기준(허용 오차, N, 타임아웃)을 느슨하게 바꾸려면 실측 분포와 함께 architect에게 올린다. 테스트를 통과시키려고 늘리지 않는다.

U1 결정에 따라 D는 1a 필수이고 `[LAND]` 한 항목 미션이 1a 노드의 지원 범위에 들어온다(쟁점 4의 PREPARING 분기).

## 쟁점 10. 타임아웃과 벽시계 가드

결정: 노드 파라미터 기본값(ROS 시각. 계약이 아니다). px4 7.2를 채택한다.

| 이름 | 값 | 근거 |
| --- | --- | --- |
| `ready_timeout` | 30 s | 준비까지 약 7 s의 4배, discovery 1.1 s 포함(px4-engineer 의견서(git 이력) 1.2절, 7.2절). px4의 `ekf_ready_timeout`을 P0까지 덮게 이름을 바꿨다 |
| `offboard_signal_timeout` | 2 s | 10회 발행 0.5 s + 여유(px4-engineer 의견서(git 이력) 1.1절, 7.2절) |
| `mode_confirm_timeout` | 3 s | 3회 연속 약 1.0 s, 표본 1개 유실 때 1.5 s, 명령 1회 유실 0.5 s(px4-engineer 의견서(git 이력) 1.1절, 7.2절) |
| `arm_timeout` | 5 s | ARMED 3회 연속 약 1.5 s + TEMPORARILY_REJECTED 재시도(px4-engineer 의견서(git 이력) 1.1절, 7.2절) |
| `hold_confirm_timeout` | 3 s | px4-engineer 의견서(git 이력) 4.1절(실측), 4.3절(권고), 7.2절 |
| 지상 disarm 확인(M5) | 3 s | `mode_confirm_timeout`을 그대로 쓴다(이름을 따로 두지 않는다. architect). [실측] disarm부터 DISARMED까지 4-12 ms + 3회 연속 약 1.0 s |
| `link_timeout` | 2 s | `vehicle_status` 최소 2 Hz의 4주기 |
| `land_disarm_fallback_delay` | 5 s | [소스] `COM_DISARM_LAND` 기본값 2 s(이 프로젝트는 바꾸지 않는다) + 3 s. PX4 파라미터를 노드가 읽지 않으므로 값을 따로 둔다 |
| `command_resend_period` | 0.5 s | [실측] run 20261111-030155-k5에서 ack 1건 유실. `check_px4.py`와 같은 값이다 |
| 지상 setpoint z 오프셋 | +0.5 m | 노드 파라미터가 아니라 `src/px4/` 어댑터 상수다(쟁점 3 M5) |

값은 px4-engineer가 2026-11-11에 최종으로 낸 것이다(px4-engineer P3b 착수 전 승인 검토(git 이력). 쟁점 6의 규칙에 따라 px4-engineer가 정하고 변경의 필수 승인자다). 명령별 재전송 규칙은 쟁점 4에 있다.

통합 테스트의 미션 값(테스트 입력): TAKEOFF 5 m, `acceptance_m` 0.3, timeout 20 s([실측] 6.2-7.6 s). LOITER 5 s, timeout 10 s. LAND timeout 30 s([실측] 10.9-11.1 s). goal 결과 대기 90 s(ROS 시각).

벽시계 가드
- 판정 시간은 모두 ROS 시각이다. 대기를 시작할 때 `/clock`이 없으면 `CLOCK_ABSENT`로 즉시 실패한다. 시각이 뒤로 가면 즉시 실패한다.
- 대기마다 `wall_cap = ROS 시각 타임아웃 x 3 + 10 s`. 넘었을 때 `/clock`이 벽시계 5 s 동안 진행하지 않았으면 `CLOCK_STALLED`, 진행은 했으면 `CLOCK_SLOW`다. 둘 다 `TIMEOUT_SIM`과 다른 분류이고, 판정을 느슨하게 하는 용도가 아니라 hang 방지다. trace에 RTF를 남긴다. 배수가 3이므로 RTF가 약 0.33 아래로 내려가면 ROS 시각 타임아웃보다 `wall_cap`이 먼저 걸려 `CLOCK_SLOW`가 된다. 그 경우 배수를 올려 통과시키지 않고 architect에게 올린다.
- pytest-timeout은 이미지에 없고 더하지 않는다. 전체는 wrapper가 `timeout`으로 감싸고 그 값은 CI `timeout-minutes`보다 짧게 둔다(수집이 반드시 돌게).
- 노드 쪽에는 벽시계 가드를 두지 않는다. timer가 노드 시계라 `/clock`이 멈추면 노드도 멈추고, lockstep이라 PX4도 멈춘다. bridge만 죽은 경우는 `Px4Timestamp`가 정체해 PX4가 손실로 판정하고 Land한다(원하는 동작).
- 배속은 쓰지 않는다.

## 쟁점 11. CI sitl job

결정
- trigger(U2): `pull_request`(opened, synchronize, reopened, ready_for_review. draft 제외)와 `push: main`, `workflow_dispatch`. 같은 PR의 옛 실행은 취소한다. architecture.md의 "PR당 1회"를 "PR 머리 커밋당 1회, 자동 재시도 없음"으로 고친다. lint와 unit도 `pull_request` + `push: main`으로 맞춘다(P0). 대가는 PR이 없는 브랜치 push에 CI가 돌지 않는 것이다.
- 별도 워크플로 `.github/workflows/sitl.yml`. runner `ubuntu-24.04`, `timeout-minutes: 30`, 자동 재시도 없음(다시 돌릴 때는 re-run 또는 `workflow_dispatch`), `concurrency`로 같은 ref의 옛 실행을 끊는다.
- 단계: checkout -> `tools/ci/build_images.py --mode pull`(xrce-agent, sim-base, px4, ros-ws. GHCR 로그인 없이) -> `tools/ros_ws.sh build`(별도 step) -> `tests/sitl/run_sitl.sh --stack 0` -> 아티팩트.
- 아티팩트: 실패 때 실행 디렉터리 전체(compose.yaml, stack.json, params, `px4-N/log`의 ULog, ros_log, compose logs, `sitl/`의 trace.jsonl과 graph snapshot과 junit.xml, verdict)와 `ros_ws/log/`. 보존 7일. 성공 때는 junit.xml, trace.jsonl, 단계별 시간 요약. `GITHUB_STEP_SUMMARY`에 단계별 초를 남긴다.
- 문서만 바뀐 PR은 워크플로 수준 `paths`로 거르지 않는다(필수 검사로 걸었을 때 대기 상태로 남는다). job 수준 `if`만으로는 바뀐 경로를 알 수 없으므로, 앞에 경로 감지 job(`changes`. `git diff`로 코드 경로 변경 여부를 output으로 낸다. 외부 action 없이)을 두고 `sitl` job이 `needs: changes`와 그 output을 보는 `if`로 건너뛴다. 코드 경로는 `ros_ws/**`, `docker/**`, `config/**`, `tools/**`, `tests/**`, `.github/workflows/sitl.yml`이다. main push에서는 건너뛰지 않는다.
- px4 이미지 key가 바뀌는 PR은 이미지 PR을 먼저 합친다.
- CI는 `viz`를 켜지 않는다.

GHCR 패키지 다섯이 Public인지의 화면 확인을 사용자에게 요청한다([실측] devops: 2026-11-11 익명 manifest 조회가 다섯 모두 200).

근거: architecture.md의 목표는 15분 이내이고 devops의 예상은 10-13분이다([추정]. pull 2-4분, build 2-3분, 기동 2-3분, 테스트 2-3분). GitHub runner 4 vCPU에서 Gazebo와 PX4 1대가 실시간에 가깝게 도는지는 실측이 없다. 첫 실행이 실험이고, 첫 3회의 단계별 시간과 RTF를 progress에 기록한다. 10-13분과 판정 구간 ROS 시각 90-110 s는 둘 다 실측이 없는 추정이다.

올림 기준(P4 완료 기준에도 넣는다): `sitl` job이 15분을 넘거나 판정 구간의 RTF가 0.7 미만이면, 타임아웃이나 허용 오차나 `wall_cap` 배수를 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다. 0.7은 architecture.md의 "실시간에 가깝게"를 수치로 옮긴 architect의 기준이고 첫 3회 실측 뒤에 다시 본다. RTF의 계산: 판정 구간(첫 시나리오의 goal 전 gate가 통과한 시점부터 마지막 시나리오의 판정이 끝난 시점까지)의 ROS 시각 경과를 같은 구간의 벽시계 경과로 나눈 값이고 `run_sitl.sh`가 회차 요약에 적는다. 15분은 `sitl` job 전체의 벽시계다. 올림은 평균이 아니라 한 회 기준이다(한 실행이라도 넘으면 올린다). 첫 3회는 넘지 않아도 값을 기록한다.

## 쟁점 12. foxglove_bridge, Lichtblick, recorder

결정
- ros-ws 이미지에 `ros-${ROS_DISTRO}-foxglove-bridge`를 더한다. 지금 이미지에 없다([실측] ros2 M6. architecture.md의 이미지 표는 이미 들어 있는 것처럼 적혀 있다). 이 변경은 단독 선행 PR(P1)이다. 같은 PR에 섞으면 그 PR의 unit과 sitl이 GHCR에서 새 key를 찾지 못해 ros-base부터 다시 빌드한다.
- 버전: `versions.env`에 `FOXGLOVE_BRIDGE_VERSION=3.6.0`. apt로 설치한 뒤 `dpkg-query` 결과가 upstream 버전 접두와 같은지 빌드에서 단정한다. 정확한 pin은 쓰지 않는다(ROS apt 저장소는 최신 빌드 하나만 남긴다).
- `foxglove` 서비스(`viz` 프로필, ros-ws, 저장소 마운트): `address` 127.0.0.1, `port` 8765 + k, `capabilities` [connectionGraph], `topic_whitelist`는 기체마다 `^/px4_N/`(생성기에 /fmu 문자열을 쓰지 않는다), `client_topic_whitelist`, `service_whitelist`, `param_whitelist`는 아무것과도 맞지 않는 정규식([실측] M8은 `^$`), `use_sim_time` true, `remote_access` false, `sysinfo` false. `/clock`은 화이트리스트에 넣지 않는다(250 Hz).
- `lichtblick` 서비스: `versions.env`의 `LICHTBLICK_IMAGE=ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:285adff96f24c80b511cf159e97e5395a6b154126c70c62d1199456009de07cc`(linux/amd64 manifest digest, 조회 2026-11-11). command를 `caddy file-server --listen 127.0.0.1:<18080 + k>`로 덮는다(이미지 기본은 `:8080`으로 모든 인터페이스에 연다). root로 둔다(entrypoint가 이미지 안의 `index.html`을 고쳐 쓰고 호스트에 쓰는 마운트가 없다). healthcheck 없음.
- 기본 layout 파일은 1a에 넣지 않는다(layout에 버전 접미사가 붙은 토픽 경로가 들어간다). `sim_stack.sh up --viz`가 접속 URL을 출력한다.
- progress의 "Lichtblick 2.5.2"는 Caddy의 버전 label을 Lichtblick 버전으로 읽은 것이다([실측] ros2 M9, devops). 1.30.0으로 고친다.
- viz 서비스는 P5(별도 PR)다. 완료 조건은 브라우저 실접속(P5의 수동 확인): Lichtblick 1.30.0이 foxglove_bridge 3.6.0에 붙는지, clientPublish를 뺀 상태에서 연결이 유지되는지, PX4 토픽에 대한 bridge의 구독이 BEST_EFFORT인지(`ros2 topic info -v`. RELIABLE로 붙으면 수신이 없으므로 `best_effort_qos_topic_whitelist`에 넣고 lint 예외로 기록), setpoint와 `vehicle_local_position`이 같은 플롯에 놓이는지. 붙지 않으면 서브프로토콜을 기준으로 앞 버전을 고르고 architect에게 알린다.
- 1a에는 recorder 서비스를 두지 않는다. 실패 산출물은 ULog, compose logs, ros_log, 판정 trace, graph snapshot, junit이다. 이것은 architecture.md의 "실패 시 MCAP 기록물과 ULog를 업로드"의 1a 예외다. MCAP 업로드는 Phase 2부터다.

근거(recorder): 기록 정책(구독 QoS override, 대상 토픽, hidden 토픽, SIGINT 종료)은 Phase 2 logging-engineer의 설계 몫이고 아직 없다. regex 기록에는 오프셋 메타데이터와 미션 경계가 없어 Phase 2 replay 입력으로 다시 쓸 수 없다(logging). 판정 실행에 PX4 토픽 구독을 더한다(판정 probe도 참가자이지만 recorder만큼 구독을 더하지는 않는다). test, devops, logging 셋이 수용했다.

Phase 2를 위해 6단계가 지켜 둘 것(logging): 실행 디렉터리의 `bag/` 이름을 다른 용도로 쓰지 않는다, wrapper의 수집 순서 맨 앞에 recorder 정지가 들어올 자리를 둔다, trace 표본에 수신 ROS 시각과 PX4 `timestamp`(us)를 함께 적는다.

기각한 안
- foxglove_bridge 설치 판을 ENV로 기록만(ros2): 버전 고정 원칙과 어긋난다. 접두 단정은 같은 3.6.0의 재빌드는 통과시키고 다음 판은 분명한 실패로 드러낸다.
- 화이트리스트에 `^/clock$`(devops 초안), `bridge.yaml`(쟁점 2).
- trace의 필드 이름을 `docs/interface.md`에 올리는 안(logging): trace는 테스트 산출물이고 인터페이스가 아니다. `tests/sitl/`의 설명에 둔다.

## 쟁점 13. 작업 단위와 PR 분할

README.md에 있다. 요약: P0(CI trigger 정리) / P1(ros-ws에 foxglove_bridge) / P2(`idsim_common` 추가) / P3(`idsim_mission` 패키지와 단위 테스트, `ExecuteMission.action`의 상수 `REASON_DISARM_FAILED` 추가와 주석, golden 두 파일) / P4(생성기, `sim_stack.sh`, `tests/support`, `tests/sitl`, `sitl.yml`, 문서 반영) / P5(viz). P1과 P2는 병렬, P3은 P2 뒤, P4는 P1과 P3 뒤, P5는 P4 뒤다.

---

## 담당자별 구현 지시

ros2-engineer
- P2: 쟁점 5의 표.
- P3a: autostart를 실행해 확인(시험 컴포넌트로 configure, activate, `wait_until_started`), 콜드 기동의 첫 `/clock` 수신 시간, ACCEPTED 누락 계수 실험 200회(쟁점 7).
- P3b 이후: `idsim_mission` 패키지. P3b는 "P3b 착수 전 px4-engineer 승인 항목"이 닫힌 뒤에 시작한다(2026-11-11에 닫혔고 PR #21로 main에 들어갔다). 실측이 없는 두 경로(지상 setpoint 발행 중의 Hold, 이륙 직후 `landed`가 true인 구간의 지상 setpoint와 disarm), 감시 표의 행 순위, "disarm 전송 뒤 받은 표본"의 기준은 표대로 구현하되 재실측과 px4-engineer 확인으로 바뀔 수 있다. 바뀌어도 고칠 곳이 한곳이 되게 둔다. core는 쟁점 4의 전이 표와 쟁점 3의 취소 분기를 `step()` 하나로(입력은 snapshot과 지금 ROS 시각, 출력은 setpoint 유무, 명령 목록, feedback, 종료 결과). 종료 결과는 한 구조체에서 action result와 종료 사건을 둘 다 채운다. `handle_goal`은 항상 `ACCEPT_AND_EXECUTE`. 사건의 `stamp`는 노드 clock의 ROS 시각. 이름 상수(`Mission::ACTION_NAME`, `MissionEvent::TOPIC_NAME`)는 상대 이름으로 쓰고 namespace 범위 static 초기화식에 쓰지 않는다. 설계 노트(패키지 README 또는 헤더 주석)에 구현 규칙(`ACCEPT_AND_EXECUTE`만, 판정 순서)을 적는다.
- P3a는 끝났다(2026-11-11. P3a 실행 확인 결과(git 이력)). 결과에 따라 Executor는 자기 전이(`lifecycle.self_start`)로 구현한다(쟁점 2).
- P3 완료 조건의 수동 확인: 스택 위에서 `ops` 컨테이너를 손으로 띄워 자기 전이로 active가 되는지(launch에서 `autostart`를 뺀 형태로. P4 전에는 CI에 없다). `lifecycle.self_start`가 false이면 `unconfigured`에 머무는 것도 본다.
- P4, P5 검토: launch와 params의 대응, foxglove params.

px4-engineer
- P3b 전: 쟁점 4의 "P3b 착수 전 px4-engineer 승인 항목" 다섯을 닫는다(완료 2026-11-11. px4-engineer P3b 착수 전 승인 검토(git 이력)).
- P3: `px4/` 디렉터리 셋(어댑터와 그 테스트. 지상 setpoint z 오프셋 0.5 m 상수 포함). 전이 표와 상태기 단위 테스트의 승인. architect가 채운 문장(지상 setpoint는 발행 중일 때만, 감시 표의 행 순위, "disarm 전송 뒤 받은 표본"의 기준, `[LAND]` 단독 미션의 ITEM_TIMEOUT 단서, 재전송 표에 옮긴 행)과 `REASON_EXTERNAL_DISARM`은 2026-11-11에 확인했다(px4-engineer PR #23 반영 확인(git 이력)). 구현 때 확인할 것: 대비책 disarm은 `landed == true`이고 `land_disarm_fallback_delay`가 지난 뒤에만 시작한다.
- P4 머지 전: 필수 재실측 (2), (3), (5)(넘김 목록).
- 7단계 고정 전: 필수 재실측(넘김 목록).
- P2 검토: setpoint 헬퍼와 빌더의 필드 표.
- P4 검토: 시나리오 A, D, T의 판정 필드와 타임아웃 값. `check_px4.py`의 source (254, 1)은 그대로.
- 안전장치 오류로 중단되면 해당 항목을 미결로 남기고 architect에게 알린다(2026-11-11 사용자 결정의 운용 방법).

test-engineer
- P3 승인: core 단위 테스트의 구조(전이 표 대조, status와 reason 대응표, 사건 == result).
- P3 단위 테스트에 넣을 것("이 goal에서 arm을 보낸 적이 있으면 disarm 분기"의 파급. 작성은 ros2-engineer, 구조 승인은 test-engineer. test-engineer 조건부 승인 2026-11-11, test-engineer P3 조건부 승인(git 이력). 선결 C1-C5를 반영해 확인 예정을 닫았다. 아래 "test-engineer가 더한 것"까지가 목록이다): (1) LAND가 자동 disarm으로 막 끝나려는 시점(DISARMED 표본이 1-2회 온 뒤)의 취소가 disarm 분기를 거쳐 CANCELED로 끝난다. (2) disarm을 보낸 뒤 `mode_confirm_timeout` 안에 기준을 만족하는 DISARMED가 3회 차지 않으면 REASON_DISARM_FAILED다. (3) 첫 disarm 전송 tick 전에 받은 DISARMED 표본, `timestamp`가 명령의 `Px4Timestamp`와 같거나 앞선 표본, 같은 `timestamp`가 다시 온 표본은 세지 않는다. 감시 표는 순위마다 한 건, 두 행이 같은 tick에 함께 맞는 경우 한 건 이상, 엇갈려 시작하는 경우(먼저 맞은 행이 이긴다) 한 건, 순위 5의 이력 가지(앞선 표본에서 OFFBOARD인 채 `failsafe == true`를 본 뒤의 지상 DISARMED는 FAILSAFE) 한 건, 이 표본의 `nav_state`가 OFFBOARD가 아니어도 순위 5의 결과가 같다는 것 한 건. ITEM_TIMEOUT의 "지상 disarm이면 바로 끝" 분기는 1a에서 닿지 않으므로(setpoint 항목은 늘 arm 뒤다) 전용 테스트를 요구하지 않고, 대신 "arm을 보낸 뒤 DISARMED snapshot에서의 ITEM_TIMEOUT은 disarm 분기를 거친다"를 한 건 둔다.
- test-engineer가 더한 것(test-engineer P3 조건부 승인(git 이력) 2절, 3절. P3. 작성은 ros2-engineer, `test/px4/`는 px4-engineer)
  - 위 (1)은 DISARMED 1회와 2회의 두 경우로 나누고(3번째와 같은 tick의 취소는 종료의 충돌 규칙으로 SUCCEEDED), "발행이 이미 멈춘 상태이므로 지상 setpoint를 새로 켜지 않는다"를 단정한다. (2)는 표본이 아예 없는 경우(LINK_LOST 경계)와 묵은 `timestamp`의 DISARMED가 계속 오는 경우로 나눈다. 종료 시점이 첫 전송 시각 + `mode_confirm_timeout`인지(경계의 `>`와 `>=`를 정해 단정), 종료 직전의 disarm 재전송, `landed`가 false로 바뀌면 공중 분기. (3)에는 늦게 처리된 arm의 경합([ARMED, DISARMED, DISARMED, ARMED]에서 계수가 되돌아감)을 넣는다.
  - disarm 분류의 고정 규칙: 첫 DISARMED 때 `landed`가 false였다가 뒤에 true가 되어도 FAILSAFE 유지, 반대도 지상 유지. 적용처 셋(감시 표의 두 행, LAND 완료 우선, 취소의 Hold 확인 창)에 각 한 건.
  - PREPARING 실패의 정리: arm을 보낸 뒤 ARM_REJECTED, `arm_timeout`, `offboard_signal_timeout` 등으로 실패하면 지상 setpoint + disarm, 원래 reason 유지, disarm 미확인은 `detail`. 한 건씩.
  - 정리 분기의 교차표: 취소, ITEM_TIMEOUT, PREPARING 실패는 같은 "정리 분기 고르기"를 쓴다. (원인 3종) x (snapshot 유형 5종)의 표 한 벌로 쓰고, 분기 내부(disarm 확인, Hold 확인)는 따로 한 번씩 쓴다. 취소 쪽에는 매 tick 다시 고르기, Hold 거부 ack와 `hold_confirm_timeout`의 Land 경로, CANCELING 중에는 감시 표를 쓰지 않음, `[LAND]` 단독 미션의 취소(발행 없음), PREPARING 중 취소(arm 재전송이 그 tick에 멈춤)를 넣는다.
  - ITEM_TIMEOUT: 분기별(공중 Hold 성공, Hold 불확인 때 Land, 지상 arm의 disarm, LAND 항목의 세 변형과 landed인 ARMED의 `detail`). 모든 분기에서 reason이 ITEM_TIMEOUT으로 남고 `detail`만 다르다는 단정. 항목 `timeout`이 흐르기 시작하는 시점(TAKEOFF는 ARMED 확인, LOITER는 앞 항목 완료, LAND는 앞 항목 완료 또는 PREPARING 끝)의 시각 경계. "setpoint 항목이 시작될 때 arm을 보낸 적이 있다"는 불변식 한 건.
  - 지상 disarm 분기의 LINK_LOST와 그 밖의 거부 ack(C4) 각 한 건. 종료의 충돌 규칙(C5): 같은 tick의 세 조합과 정리 중의 cancel, 종료 뒤 step이 명령, 사건, 상태를 바꾸지 않는다는 것.
  - 감시 표의 같은 tick 동률은 표 주도형으로, 동시에 맞을 수 있는 행 쌍을 전부 만든다(순위 1-3은 서로와 모든 행, 6-8끼리와 4-5끼리는 배타). 순위 5의 이력은 두 건을 더한다: 이력은 그 항목 안에서만 유효하다(TAKEOFF에서 본 failsafe가 LOITER로 넘어오지 않는다). OFFBOARD이고 ARMED인 채 `failsafe == true`인 표본은 goal을 끝내지 않는다(표대로. "확인 예정의 처리"). 이 둘과 DISARM, ARM의 그 밖의 거부 ack는 PX4 v1.17.0에서 닿지 않는 방어 경로라 합성 표본과 합성 ack로만 시험한다는 것을 테스트 주석에 적는다.
  - status와 reason 대응표: 모든 `REASON_*`(13, 14 포함)가 정확히 한 status에 대응한다는 전수 표. core의 reason enum 값과 생성된 메시지 상수 값이 같다는 교차 검사를 노드 쪽 gtest에 한 건(상수가 늘면 깨진다).
  - 종료 사건 == result: harness의 불변식으로 모든 시나리오에 건다(종료 사건 정확히 1건, ACCEPTED가 앞, 종료 뒤 사건 없음, `mission_id`와 status와 reason이 result와 일치). result와 사건을 한 종료 결과 객체에서 만든다(ros2-engineer 지시에 이미 있다). 노드 배선 gtest(정상, 무효 각 한 경로)에서 두 소비자가 같은 값을 받는지 한 번.
  - 노드 쪽: `lifecycle.self_start`의 대조군 쌍(같은 spin 횟수에서 true는 active, false는 `unconfigured`). 이어서 직접 건 configure와 activate의 성공, goal 실행 중 deactivate 거부, on_shutdown이 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝내고 사건을 내는지. 배선 테스트는 `/clock`도 발행한다(on_activate의 2 s 대기는 param으로 만들지 않는다).
  - 구조: 시나리오를 tick 열(snapshot 열)로 쓰는 작은 헬퍼. 테스트 이름에 감시 표의 순위. 표의 행 수와 parametrize 수가 같다는 단정 한 건. core 소스에 `chrono`의 `clock::now`와 `rclcpp`가 없다는 grep 검사를 lint에 넣는다(devops-engineer와).
  - 단위 테스트는 합성한 `timestamp`만 검사한다. 실제 시계 관계(`vehicle_status.timestamp`와 `Px4Timestamp`)는 재실측 (5)의 분포만이 확인한다.
- P4의 실측 기록(test-engineer P3 조건부 승인(git 이력) 4절. stop 검증, 결함 주입, px4 재실측에 공통)
  - 측정 스크립트는 `tests/sitl/measure/`에 둔다(소유 test-engineer, 절차의 필수 승인자 px4-engineer. C6). px4 재실측 (2), (3), (5)가 P4 머지 조건이므로 P4의 선행 작업이다.
  - 시도마다 기계가 읽는 행을 남긴다(`measure_<항목>.tsv` 또는 jsonl): run id, commit과 dirty, 이미지 key, 시도 번호, 주입 조건과 trigger, 결과, ROS 시각과 벽시계 소요, 종료 코드, ULog 경로. 실패한 시도를 빼지 않고 재시도하지 않는다. 위치는 `run_sitl.sh`와 같은 아티팩트 디렉터리다. 통과 기준은 실행 전에 요약 파일 머리에 적는다. trigger는 sleep이 아니라 이벤트(feedback phase, `landed` 표본)다.
  - 회수의 한계를 적는다. 10회 중 0건은 실패율의 95% 상한이 약 26%라는 뜻이다(3/n). "10/10 통과"를 "플래키 없음"으로 쓰지 않는다.
  - stop 검증의 goal 실행 중 stop은 단계를 나눈다: PREPARING, TAKEOFF, LOITER, LAND 각 1회 이상(4회 이상). 종료 사건의 수신은 구독자(테스트 노드)에서 기록하고 못 받으면 "수신 실패"로 남긴다.
  - 결함 주입(`vehicle.id` 누락에서 unhealthy까지): 시작은 compose up 시각, 끝은 `.State.Health.Log`의 첫 unhealthy. 벽시계 측정임을 행에 적는다. 정상일 때 healthy까지의 시간과 쌍으로 잰다.
  - 재실측 (5)의 `timestamp - Px4Timestamp` 분포가 0 근처에서 부호가 섞이면 "엄격히 뒤" 기준을 px4-engineer와 architect가 다시 본다.
  - `tests/support/mission_client.py`가 `mission_event` 구독을 action client보다 먼저, 같은 node 객체로 만드는지 mock으로 검사한다. DDS에서의 효과(87/400)는 단위로 재현되지 않으므로 구조만 건다. 효과는 P3a의 0/400과 시나리오의 `EVENT_MISSING` 분류가 받친다.
- P4: `tests/support/`(clock, waiting, probe, judge, mission_client, events, trace, `px4_topic`, `px4_raw`. 판정 함수는 rclpy 없는 순수 코드로 두고 단위 테스트는 lint job의 pytest에서 돈다), `tests/sitl/`(`run_sitl.sh`, conftest, 시나리오), `tests/support/stack.py`의 새 key 접근자. lint job의 pytest가 `tests/sitl/`을 수집하지 않게 한다. 로컬 3회 연속 통과의 실행과 기록.
- verdict 분류: `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_SLOW`, `CLOCK_ABSENT`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`.

devops-engineer
- P0: lint, unit trigger 정리(`pull_request` + `push: main`).
- P1: `Dockerfile.ros-ws`, `versions.env`, `docker-bake.hcl`. 빌드 뒤 이미지 크기를 실측해 알린다.
- P4의 `ops-N` 서비스와 기동, 정지 경로(P3a 결과와 devops-engineer 쟁점 2 재결정 검토(git 이력). 쟁점 2의 값 그대로)
  - `ops-N`: `init: true`, `stop_signal: SIGINT`, `stop_grace_period: 10s`, healthcheck(`interval` 10s, `timeout` 10s, `retries` 2, `start_period` 20s, `start_interval` 2s, 안쪽 `timeout 8`, 출력 남김).
  - 상주 ros-ws 서비스(bridge, P5의 foxglove)와 xrce-agent에 `init: true`. 같은 PR에서 하고 생성기 golden 4종이 함께 바뀐다. 바꾸기 전후의 down 시간을 1회씩 잰다.
  - runner: wrapper의 `timeout`이 보낸 SIGTERM이 PID 1인 pytest에서 버려지는지 1회 확인하고 `init: true` 또는 `timeout -s INT -k 30`으로 고친다(test-engineer와).
  - exit code: 판정에 쓰지 않는다. stop 전 `compose ps -a --format json` 기록 -> running이 아닌 `ops-N`이 있으면 실패 -> `compose stop` -> `compose logs` -> down. exit 1을 보아 넘기는 것은 stop을 요청한 뒤에 한정한다(쟁점 2).
  - `sim_stack.sh`는 노드 단계가 실패하면 `ops-N` 로그 끝과 `.State.Health.Log`를 함께 찍는다.
  - 생성기 성질 테스트 넷: ros-ws 이미지의 상주 서비스는 모두 `init: true`. `ops-N`은 `stop_signal: SIGINT`와 `stop_grace_period: 10s`. 생성된 params 파일에 `lifecycle.`로 시작하는 key가 없다. healthcheck 문자열의 FQN이 `stack.json`의 `executor_node`와 같다.
  - P4 검증(결과를 progress에 남기고, 값이 아래와 다르면 architect에게 알린다)
    - stop 검증 10회: 그중 4회 이상은 goal 실행 중에 stop한다(PREPARING, TAKEOFF, LOITER, LAND 각 1회 이상. test-engineer). 기록 형식은 test-engineer 지시의 "P4의 실측 기록"을 따른다. 볼 것은 유예(10 s) 안에 끝나는지, 정리 로그가 있는지, exit code의 분포, goal 실행 중 stop에서 종료 사건(ABORTED, REASON_INTERNAL)이 구독자에게 오는지다(on_shutdown이 SIGINT 뒤에 도는지는 실측이 없다).
    - 결함 주입 1회 이상: `vehicle.id`가 빠진 params로 `sim_stack.sh up`이 unhealthy를 보고하기까지의 시간(예상 약 54 s, 최악 70 s)과 정상일 때 healthy까지의 시간(예상 약 5-6.5 s).
    - CI 첫 3회의 probe 시간(`.State.Health.Log`의 Start와 End)을 RTF와 함께 기록한다. runner의 `docker version`을 job 로그에 남긴다(`start_interval`은 Engine 25 이상).
- P4: 생성기(쟁점 2), `sim_stack.sh`(`--infra-only`, install 검사, 노드 단계 실패 때 `ops-N` 로그 출력), `run_smoke.sh`, `check_host.sh`, `--run-id` 제거, `build_images.py --mode pull`, `sitl.yml`, `px4-api` 범위 확장, 생성기 golden 4종과 전체 트리 비교. 손대는 파일의 음차("키", "잡")를 고친다.
- P5: `foxglove`, `lichtblick` 서비스와 `LICHTBLICK_IMAGE`, `docker/README.md`의 갱신 절차와 접속 안내.

architect
- P3: `ExecuteMission.action`의 상수 둘 추가(`REASON_DISARM_FAILED = 13`, `REASON_EXTERNAL_DISARM = 14`), 주석(M1, M3-M5, 두 상수의 의미), golden 두 파일 갱신과 diff 승인(두 줄씩). P3e 전에 값 13과 14를 쓰는 다른 브랜치나 열린 PR이 없는지 확인한다(`ExecuteMission.action`을 고치는 브랜치 조회).
- P4: 문서 반영 목록.
- 7단계: `docs/interface.md`에 M1-M5(새 상수 포함)와 전이 표의 계약 부분, source 표, 타임아웃이 노드 파라미터라는 구분.

reviewer: 이 문서의 검증("reviewer가 검증할 가정")과 PR마다의 검토.

## 넘김 목록

| 받는 쪽 | 시점 | 항목 |
| --- | --- | --- |
| px4-engineer | (2), (3), (5)는 P4 머지 전(필수. 근거는 "PR #23 검토 반영"). 나머지는 7단계 고정 전(필수) | 재실측(2026-11-11에 다시 정했다. 이륙 단계와 0.5 m 호버의 Hold는 run 20261111-030155-k5로 표본이 생겼고, 새로 드러난 미실측 조합이 더해졌다). Hold로 끝난 상태의 관찰은 60 s 이상으로 한다. (1) AUTO_LAND 하강 중 0.3 m 아래에서의 취소 3회: 내려앉는지 호버하는지, CANCELED 뒤의 상태, landed인 채 armed로 남는 경우가 있는지. (2) 지상 setpoint 발행 중의 Hold 3회: H와 같은 조건에서 NAV_LAND 대신 Hold를 보내고 처음 관측한 순간 발행을 멈춘다. 이어서 "Hold를 확인하고 발행을 멈춘 뒤 `landed`가 true인 상태에서 disarm" 3회(수락 여부, 고도 변화 0.2 m 이하인지). (3) 이륙 직후의 지상 setpoint와 disarm 3회: TAKEOFF 목표점으로 arm한 뒤 `landed`가 아직 true인 구간(약 0.3-1.0 s)에 지상 setpoint로 바꾸고 disarm. 보내는 시점은 sleep이 아니라 `landed` 표본에 맞춘 조건으로 잡는다(px4-engineer 권고). (4) 감시 표 순위의 확인: G처럼 지상 setpoint로 arm한 뒤 다른 source로 disarm하고, 뒤따르는 표본의 `nav_state`, `failsafe`, `nav_state_user_intention`을 기록한다. failsafe Land 뒤 자동 disarm의 첫 DISARMED 표본과 명령 disarm(대비책)의 첫 표본도 기록한다(`failsafe`, `nav_state`, `nav_state_user_intention`, `landed`). 선택 항목: failsafe 동작이 Disarm인 경로(`COM_OBL_RC_ACT`를 Disarm으로 둔 실행)의 DISARMED 표본이 예상(`failsafe` true, `nav_state` OFFBOARD)과 같은지. 이 프로젝트의 파라미터(Land)로는 닿지 않아 필수가 아니다. (5) arm 전송 직후 취소의 경쟁(추가 문제 1): arm을 보낸 직후(0-0.2 s)에 지상 setpoint와 disarm을 보내고 끝난 상태가 DISARMED인지. 10회 이상. 통과 기준은 전부에서 `mode_confirm_timeout` 안에 기준을 만족하는 DISARMED 3회가 차고, 상승이 0.2 m 이하이며, 지상에 armed로 남은 회가 없는 것이다. 모든 `vehicle_status` 표본의 (`timestamp`, 노드가 받은 ROS 시각, 같은 시점의 `/clock`)을 기록해 `timestamp - Px4Timestamp`의 부호 있는 분포를 구한다. (6) 표본 늘리기: Hold 실험 B(offboard 손실 failsafe 중 Hold)와 C(NAV_LAND 중 Hold), 이번 run의 G, H, X2a, X2b를 각 3회 이상. 높이 0.06-0.37 m 사이의 Hold 포함. (7) X3(이륙한 적 없는 지상 armed에서 발행 중단) 1회. (8) Executor가 보낸 `[LAND]`(지면 근처 Hold에서. P3 뒤에 가능). 결과가 M3, M4, M5의 문장이나 감시 표와 다르면 고정 전에 고친다. 결과 파일은 `docs-for-agent/plan-1a-6-idsim-mission/remeasure-px4.md`(run id, 항목별 회수와 값). 측정은 px4-engineer, 표와의 대조와 통과 판정은 architect, 근거 확인은 reviewer다. (2)와 (3)의 통과 기준은 3회 모두 이 문서의 표대로 끝나는 것이다 |
| test-engineer, px4-engineer | P4의 선행 작업(닫힘 2026-11-11: 위치와 소유를 정했다) | 측정 스크립트는 `tests/sitl/measure/`에 둔다. 소유는 test-engineer이고 절차는 px4-engineer가 필수 승인자다(test-engineer P3 조건부 승인(git 이력) C6). 재실측 (2), (3), (5)가 P4 머지 조건이므로 스크립트가 먼저 있어야 한다 |
| architect | 7단계 | `docs/interface.md`: M1-M5(M3은 2026-11-11에 고친 문장), `REASON_DISARM_FAILED`와 `REASON_EXTERNAL_DISARM`의 의미(1a 고정 전에 두 상수의 이름과 의미 문장을 한 번 더 본다. EXTERNAL_DISARM은 "원인은 판정하지 않는다"와 이름의 불일치를 `COM_DISARM_LAND` 자동 disarm 시나리오로 따진다), 감시 표의 행 순위(재실측 (4) 뒤), disarm 분류의 고정 규칙, "공중"과 "지상"이 `landed` 값이라는 용어 주석, reason별 "ABORTED 뒤 기체 상태" 표(px4-engineer와. 쟁점 4의 "끝난 뒤 기체 상태" 줄 포함), 공중에서 끝나는 미션은 "고정 전"(U3), source 표, 발행 규칙(Offboard가 아닌 모드에서는 setpoint를 발행하지 않는다), 5단계 `decisions.md` 쟁점 9와 이 문서의 관계. `last_item_index` 구분 필드 불요 확인 |
| architect, px4, ros2 | 1b 설계 토론 | 공중에서 끝나는 미션의 종료 동작(권고: Hold 확인 뒤 SUCCEEDED), setpoint 항목으로 시작하는 공중 시작 미션(Offboard 재진입), 1a 임시 제한(마지막이 LAND, 첫 항목 제한)의 해제 |
| ros2-engineer, devops-engineer | 1b | `bridge.yaml` 생성(표적과 함께), world ENU <-> 로컬 NED 변환이 상태기 입력 직전 한 곳에 들어가는 구조 |
| px4-engineer | 7단계 전(선택) | 위치 무효에서의 Hold 거부 1회 실측(`failure gps off`), arm 상태에서 신호 없는 Offboard 요청 |
| px4-engineer | 다음에 `Dockerfile.px4`를 바꿀 때 | 주석의 옛 문서 이름(기존 미해결 항목 그대로) |
| px4-engineer, test-engineer | P4 | ULog가 `compose stop -t 15`에서 정상적으로 닫히는지 모른다. 첫 실행에서 `stop`의 종료 코드(137이면 KILL)를 기록하고 결과를 progress에 남긴다. 실패 산출물 용도라 1a 완료를 막지 않는다 |
| architect, devops-engineer | Phase 2 | replay job의 trigger를 정한다(U4). 그때 `docs/architecture.md` 277행(리플레이 통합 행의 "모든 push")과 `docs/roadmap.md` 59행(Phase 2 완료 기준의 "모든 push")을 고친다 |
| logging-engineer | Phase 2 | recorder 도입과 `sitl`의 MCAP 업로드, `MissionEvent` QoS 재검토 제안(TRANSIENT_LOCAL)은 5단계 근거와 함께 다시 토론, wrapper의 recorder 정지 자리와 `bag/` 사용, ULog가 `compose stop`에서 정상적으로 닫히는지 |
| ops-service-engineer | Phase 3 | `validate_mission`(core)을 Fleet이 같이 쓰는 구조, 취소 뒤 Hold로 남은 기체에 `[LAND]` 미션을 보내는 절차, NOT_READY 앞에 feedback이 올 수 있다는 것 |
| devops-engineer | 뒤로 | Lichtblick 기본 layout, snapshots.ros.org 날짜 고정, clang-tidy 도구 이미지 분리(foxglove 추가 뒤 ros-ws 크기를 보고), 3대 nightly(Phase 3), unit job의 pull 분기를 `--mode pull`로 |
| test-engineer | Phase 2 | 판정 함수를 리플레이가 같은 이력 객체로 쓰는 구조의 확인, 가짜 PX4 발행자의 Python 판 |
| ros2-engineer | Phase 3 | component마다 생기는 `/clock`(250 Hz) 구독의 CPU, 참가자 수 상한 |

## 문서 반영 목록

이번에는 고치지 않았다. P4 PR 안에서 reviewer 확인 뒤 architect가 반영한다(viz 관련 줄은 P5).

- `docs/architecture.md`
  - 테스트 절의 통합 테스트 구조: "pytest fixture가 `docker compose up --wait`로 스택을 올리고"를 "호스트 wrapper `tests/sitl/run_sitl.sh`가 `tools/sim_stack.sh`로 스택을 올리고 내리며, pytest는 `runner` 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증한다"로. "fixture가 active 전이를 기다릴 수 있게"는 "compose healthcheck가 active를 확인한다"로.
  - 테스트 절의 판정 기준: "도달은 `vehicle_local_position`과 setpoint 거리"를 "goal의 목표값과 `vehicle_local_position`"으로.
  - CI 절 (4) `sitl`: 실패 산출물을 ULog, compose logs, ros_log, 판정 trace로, "MCAP 업로드는 Phase 2부터". "PR당 1회"를 "PR 머리 커밋당 1회, 자동 재시도 없음"으로(U2).
  - 283행 (1) `lint`: `px4-api` 검사의 넓힌 범위(yaml, 생성기 golden params, `tests/sitl`, `tests/support`와 예외 파일).
  - 191행(시작 순서와 healthcheck)과 193행(컨테이너 사용자)의 `ros-ws` 서비스 이름을 `ops-N`으로, 노드 단계와 lifecycle healthcheck.
  - 인터페이스 계약 절의 고정 시점 문장: 1a 완료에 고정되는 `ExecuteMission`의 범위에서 "공중에서 끝나는 미션의 종료 동작"을 빼고 1b 완료로(U3).
  - 서비스 표: `ros-ws` 행을 `ops-1 ... ops-N`으로(launch, 컴포넌트 컨테이너, healthcheck). `runner`의 의존.
  - 이미지 표: foxglove_bridge는 P1부터 들어간다는 사실과 버전 단정.
  - 216행(`docker/versions.env`에 적는 것의 열거)에 `FOXGLOVE_BRIDGE_VERSION`과 `LLVM_MAJOR`를 더한다(P5에서 `LICHTBLICK_IMAGE`).
  - 191행과 서비스 표: `ops-N`의 전이 주체가 노드 자신이라는 것(`lifecycle.self_start`), `init: true`와 `stop_signal`.
  - 기술 스택 표의 토픽 시각화 행(106행)과 미해결 서술의 "Lichtblick 2.5"를 1.30.0으로, 서브프로토콜 문장은 P5 실접속 결과로.
  - 기체 식별 절: params key(`vehicle.id`, `vehicle.ns`, `vehicle.sysid`), `stack.json`의 새 key, 식별 gate의 위치(PREPARING).
  - 인터페이스 계약 절: 취소 의미(M3-M5. Hold로 끝난 기체는 지면 근처여도 ARMED로 머문다는 문장 포함), `REASON_DISARM_FAILED`, `REASON_EXTERNAL_DISARM`, 발행 규칙.
  - 인터페이스 계약 절의 시간 기준 문장(170행 근처): 판정과 타임아웃은 ROS 시각이라는 원칙에 벽시계 예외 넷을 적는다. on_activate의 `/clock` 첫 수신 대기, 테스트 대기의 `wall_cap`, `CLOCK_STALLED` 판정의 5 s, Executor의 자기 전이 일회 timer(쟁점 2). 앞의 셋은 hang 방지용이고 넷째는 `/clock`이 오기 전에도 전이를 시도하게 하는 trigger다. 넷 다 판정 기준이 아니다.
  - 디렉터리 구조: `tests/sitl/`, `params/`, `ros_ws/src/idsim_mission/`.
- `docs/roadmap.md`
  - 리스크 표 95행: "EKF 수렴(`vehicle_local_position.xy_valid`) 대기 후 arm"을 "EKF 준비(`failsafe_flags`의 위치와 고도와 home 무효 flag 넷이 모두 false) 뒤 Offboard, 그다음 arm"으로. 같은 표에 "Offboard가 아닌 모드에서 setpoint를 발행하면 착륙 판정이 늦고 Hold가 끌린다"와 "failsafe 뒤 발행을 재개하면 Offboard로 돌아간다"를 더한다.
  - 1a 6번: "pytest fixture가 compose를 올리고"를 wrapper로, "EKF 수렴 대기 후 arm"의 순서, `bridge` 설정 파일은 1b, foxglove_bridge 이미지 추가, 통합 테스트의 시나리오 목록. 1a 3번의 "pytest fixture" 언급도 같이 본다.
  - 16행(고정 시점을 나눈 문장)과 31행(1a 7번의 "계약으로 고정"): `ExecuteMission`에서 공중에서 끝나는 미션의 종료 동작은 1b 완료에 고정(U3).
  - 33행(1a 완료 기준): "이륙-호버-착륙 통합 테스트"가 시나리오 B, C, A, D, T 다섯을 가리킨다는 문장을 더한다.
  - 1a 4번의 발행 허용 문장: 테스트 harness의 예외(`tests/support/px4_raw.py`)를 적는다.
  - 1b 1번: 공중에서 끝나는 미션의 종료 동작 결정과 1a 임시 제한(마지막이 LAND, 첫 항목 제한)의 해제. `bridge.yaml`.
  - Phase 2: `sitl`의 MCAP 업로드.
  - 59행(Phase 2 완료 기준의 "replay CI job이 모든 push에서 돈다")은 P4에서 고치지 않는다. replay job의 trigger는 Phase 2에서 정하고 그때 고친다(U4).
- `docs/smoke-test.md`: `run_smoke.sh`가 `--infra-only`로 올린다는 것.
- `ros_ws/src/idsim_interfaces/action/ExecuteMission.action`: `REASON_DISARM_FAILED = 13`, `REASON_EXTERNAL_DISARM = 14`와 주석(M1, M3-M5, 두 상수의 의미), golden 두 파일(P3).
- 루트 `README.md`와 `docker/README.md`: `tests/sitl/run_sitl.sh` 실행 안내(`--repeat`, `--attach`), `sim_stack.sh up --infra-only`.
- `docs-for-agent/file-ownership.md`: P4가 아니라 계획 PR(브랜치 `docs/1a-6-plan`)에서 호출한 쪽이 반영한다. 구현이 시작되기 전에 소유가 문서에 있어야 한다. 문안은 아래 그대로다.
  - 표의 ros2-engineer 행 파일 목록 끝에 더한다: `ros_ws/src/idsim_mission/`(launch, `include/idsim_mission/core/snapshot.hpp` 포함. 아래 px4-engineer 몫 제외)
  - 표의 px4-engineer 행 파일 목록 끝에 더한다: `ros_ws/src/idsim_mission/include/idsim_mission/px4/`, `ros_ws/src/idsim_mission/src/px4/`, `ros_ws/src/idsim_mission/test/px4/`
  - 표의 test-engineer 행 파일 목록 끝에 더한다: `tests/sitl/`(`run_sitl.sh` 포함)
  - 표의 devops-engineer 행은 `.github/workflows/`가 이미 있어 `sitl.yml`을 따로 적지 않는다.
  - 표 아래에 절을 더한다.

```
## idsim_mission의 승인 규칙

- 상태기는 ros2-engineer가 `docs-for-agent/plan-1a-6-idsim-mission/decisions.md`의 전이 표대로 구현한다. 전이 표와 상태기 단위 테스트의 변경은 px4-engineer가 필수 승인자다.
- `include/idsim_mission/core/snapshot.hpp`는 ros2-engineer 소유이고 변경은 px4-engineer가 필수 승인자다.
- 타임아웃 기본값과 명령 재전송 주기(노드 파라미터의 기본값)는 값을 px4-engineer가 정한다. 그 값이 적힌 파일은 ros2-engineer 소유이고, 값의 변경은 px4-engineer가 필수 승인자다.
- 패키지 `test/`는 `test/px4/`가 px4-engineer, 나머지가 ros2-engineer 소유다. 단위 테스트의 구조는 test-engineer가 승인한다.
- `tests/support/px4_raw.py`(테스트가 /fmu/in에 쓰는 유일한 모듈)는 test-engineer 소유이고 변경은 px4-engineer가 필수 승인자다.
- `idsim_mission_core`는 px4_msgs에 의존하지 않는다. PX4 enum의 해석은 `px4/` 디렉터리에만 둔다.
```

- `docs-for-agent/file-ownership.md`(호출한 쪽): "idsim_mission의 승인 규칙" 절에 한 줄을 더한다. "`tests/sitl/measure/`(실측 스크립트)는 test-engineer 소유이고 측정 절차의 변경은 px4-engineer가 필수 승인자다."
- `docs-for-agent/progress.md`(호출한 쪽): 현재 상태 갱신, "Lichtblick 2.5.2" 정정, 닫히는 미해결 항목(6단계로 넘김 4건, clock의 `/clock` 판정, `px4-api` 범위, `start_interval` 하한, `--run-id`, `--mode pull`), "다음 작업 5"의 bridge 설정 파일은 1b로.
- `CLAUDE.md` 담당자 표와 `.claude/agents/`(사용자 승인 2026-11-11, 호출한 쪽이 반영 완료)
  - `CLAUDE.md` 표의 ros2-engineer 소유 영역: "`idsim_common`, `config/cyclonedds.xml`"에 "`idsim_mission`(`px4/` 디렉터리 제외)"를 더한다.
  - `CLAUDE.md` 표의 px4-engineer 소유 영역: "`idsim_mission`의 PX4 인터페이스"를 "`idsim_mission`의 `px4/` 디렉터리(어댑터), 상태기 전이 표의 필수 승인"으로.
  - `CLAUDE.md` 표의 test-engineer 소유 영역: "`tests/`, 각 패키지 `test/`"를 "`tests/`, 각 패키지 `test/`의 구조 승인(`idsim_mission/test/`의 소유는 ros2, `test/px4/`는 px4)"으로.
  - `.claude/agents/ros2-engineer.md` 소유 영역에 `ros_ws/src/idsim_mission/`(`px4/` 디렉터리 셋 제외, snapshot 헤더 포함)을 더한다.
  - `.claude/agents/px4-engineer.md` 17행 "`ros_ws/src/idsim_mission/`에서 PX4와 맞닿는 부분"을 "`ros_ws/src/idsim_mission/`의 `include/idsim_mission/px4/`, `src/px4/`, `test/px4/`. 상태기 전이 표, snapshot 헤더, `tests/support/px4_raw.py`의 필수 승인. 타임아웃 기본값과 명령 재전송 주기는 값을 정하고 변경의 필수 승인자다(파일은 ros2-engineer 소유)"로.
  - `.claude/agents/test-engineer.md`: `idsim_mission/test/`는 소유가 아니라 구조 승인이라는 것과 `tests/sitl/` 소유를 더한다.

## 사용자 결정 (2026-11-11 확정. 호출한 쪽이 전달)

1. U1: 가. 시나리오 D(공중 취소)와 `[LAND]` 한 항목 미션을 1a 필수에 넣는다. 귀결: D가 "3회 연속"과 CI 필수에 들어가고, 상태기에 PREPARING 분기 하나가 는다. 기각된 선택지는 D를 로컬 전용으로 두는 안과 `[LAND]` 없이 스택을 내려 정리하는 안이다.
2. U2: 가. `sitl`은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외, 옛 실행 취소)와 main push에서 돈다. lint와 unit의 trigger도 `pull_request` + `push: main`으로 맞춘다(P0). 기각된 선택지는 label을 붙인 PR만 돌리는 안과 main과 수동 실행만 두는 안이다. 판단 재료의 한계: 실행당 10-13분은 실측이 없는 추정이고, 공개 저장소의 표준 hosted runner가 과금되지 않는다는 것은 GitHub 문서 원문을 다시 확인하지 않은 devops의 이해다. 첫 실행들의 실측이 이 가정과 다르면 다시 올린다(쟁점 11의 올림 기준).
3. U3: 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작은 1b로 미룬다. 1a 노드는 INVALID_MISSION으로 끝낸다. 5단계 사용자 결정 1의 고정 범위("1a 완료에 `ExecuteMission`")에서 이 조각을 뺀 것이다.

4. U4(2026-11-11): replay job의 trigger는 지금 정하지 않는다. replay job을 만드는 Phase 2에서 정하고 `docs/architecture.md` 277행과 `docs/roadmap.md` 59행은 그때 고친다.
5. U5(2026-11-11): px4-engineer의 반영 확인은 "PR #21 reviewer 검증 반영" 개정이 끝난 뒤 다시 받는다. px4-engineer의 읽기 전용 확인은 앞으로 sonnet으로 받는다(px4-engineer의 기본 모델 opus의 예외. 사용자가 2026-11-11에 정한 일반 규칙이다. 실측과 구현, 설계 토론에는 적용하지 않는다).

남은 확인 요청(결정이 아니다): GHCR 패키지 다섯과 buildcache가 Public으로 설정되어 있는지 패키지 설정 화면에서 확인. 익명 조회는 200이었다.

## 사용자에게 알릴 것 (결정은 했으나 뒤집을 수 있음)

- 1a `sitl`은 실패 때 MCAP을 올리지 않는다(architecture.md 문장의 1a 예외). recorder는 Phase 2에서 붙인다.
- Lichtblick 이미지는 1.30.0이다. 2026-11-06 결정에 적힌 "2.5.2"는 베이스 Caddy의 버전 label이었다. foxglove_bridge 3.6.0과의 브라우저 접속은 P5에서 확인하며 그 결과로 버전이 바뀔 수 있다.
- LAND 항목 중에 취소해도 Hold다(기체가 하강을 멈추고 그 자리에 머문다).
- 이륙 직후나 지면 근처에서 Hold로 취소된 기체는 땅에 닿아 있어도 ARMED인 채 머문다(2026-11-11 실측 2회, 12 s 관찰, 스크립트가 보낸 명령. 더 긴 시간과 Executor의 동작은 재실측 대상이다). 내리고 disarm하려면 `[LAND]` 미션을 보낸다.
- `ExecuteMission`의 result에 상수 둘을 더한다. `REASON_DISARM_FAILED = 13`(취소 중 지상 disarm이 확인되지 않음)과 `REASON_EXTERNAL_DISARM = 14`(실행 중 지상에서 Executor가 보내지 않은 disarm). 고정 전의 계약 변경이고 golden은 두 파일에 두 줄씩이다.
- ros-ws 이미지가 foxglove_bridge로 [추정] 50-70 MB 커지고 key가 바뀐다. 다른 이미지와 SITL 파라미터는 바뀌지 않는다.
- 스모크는 노드 없이(`--infra-only`) 돈다.
- 6단계는 PR 여섯 개로 나뉜다.

## reviewer 검증 결과 (가정 13건)

reviewer의 판정은 조건부였다(P1, P2, P3a 착수 가능, P3b는 필수 수정 반영 뒤). 아래 판정은 reviewer 판정표 원문으로 채웠다. PX4 소스는 px4 이미지에 없어(`Dockerfile.px4`가 `build/px4_sitl_default/{bin,etc,rootfs}`만 복사) reviewer가 GitHub의 v1.17.0 태그 원문을 받아 행 단위로 대조했다.

| 번호 | 가정 | 판정(전달된 범위) | 처리 |
| --- | --- | --- | --- |
| 1 | 주석만 고치면 golden 셋이 그대로다 | 성립하되 주의 있음(권고 10: 주석 표현에 따라 `test_contract.py`의 가드가 실패할 수 있다) | 쟁점 3 구현 지시. M5 (나)로 golden 두 파일은 상수 한 줄씩 바뀐다 |
| 2 | REASON_MODE_SWITCH_FAILED의 의미 넓히기가 5단계 규칙에 걸리지 않는다 | 성립하지 않음(필수 3: "나중에 더하면 된다"와 모순) | (나) 상수 추가로 바꿨다 |
| 3 | 공중에서 끝나는 미션을 1b로 미루는 것은 알림으로 충분하다 | 성립하지 않음(필수 1: 사용자 결정으로 올린다) | U3으로 확정 |
| 4 | `ComposableLifecycleNode(autostart=True)`가 Jazzy에 있다 | 확인됨(소스). ros-ws 이미지의 launch_ros 0.26.13 `descriptions/composable_lifecycle_node.py` 30-35행, `actions/load_composable_nodes.py` 243-256행(CONFIGURE, ACTIVATE 한 번씩). 실행 중 동작은 미확인 | P3a에서 실행해 확인. 결과: 동작하지 않는다([실측] 5/5 `unconfigured`. API는 있으나 0.26.13이 FQN과 matcher를 잘못 다뤄 전이가 걸리지 않는다). 쟁점 2를 노드의 자기 전이로 다시 결정했다 |
| 5 | `server_is_ready()`가 active의 근거이고 match의 틈이 작다 | 근거 부족(권고 1: 순서 규칙과 200회 계수 실험) | 쟁점 7. P3a 결과: 순서 규칙을 지키면 누락 0/400, 어기면 87/400. 순서 규칙은 필수 조건이다 |
| 6 | px4 실측의 표본 수가 M3, M4를 받친다 | 부족(필수 4: 7단계 고정 전 재실측 필수) | 넘김 목록 |
| 7 | px4의 소스 인용이 v1.17.0과 맞다 | 일부 보정(필수 2: 자동 disarm 때 `nav_state`가 AUTO_LAND를 떠난다. 필수 4: `MulticopterLandDetector.cpp` 229-236행. 권고 4: `MulticopterPositionControl.cpp` 466-472행). 나머지는 확인됨: `UserModeIntention.cpp` 53-60, `modeCheck.cpp` 144-152, `estimatorCheck.cpp` 664-743과 796-821, `offboardCheck.cpp`, `failsafe.cpp` 641, `framework.cpp` 351-360과 504-519, `MulticopterPositionControl.cpp` 466-490과 501-519(`ground_contact` 추력 0), `Commander.cpp` 918, 1093-1110, 2285-2291, 2369-2372, `mode_requirements.cpp` 110-123, `dds_topics.yaml`의 5 Hz와 50 Hz, `VehicleStatus.msg`의 6 = SAFETY_BUTTON | 쟁점 3, 4 |
| 8 | T의 flag 경로, X2, X3 | X2는 [추정]으로 내림(필수 4). T는 대기 상한 보정(권고 8). X3은 재실측 대상 | 쟁점 3, 9, 넘김 목록 |
| 9 | `/**` params가 컨테이너 노드에도 적용되고 미선언 key는 무시된다 | 확인됨(소스). `launch_ros/utilities/to_parameters_list.py` 60-63행과 100행이 `/**`를 노드 FQN에 맞춰 LoadNode 요청의 parameters로 넘긴다. 실행 중 동작은 미확인 | P3a에서 확인됨([실측] 스택 21회, 스택 밖 2회) |
| 10 | `tests/`의 /fmu/in 예외가 발행 허용 목록의 취지와 맞다 | 조건부(필수 7: `px4_raw.py`의 px4 필수 승인. 권고 7: roadmap 4번 문장에 예외를 적는다. 권고 8: sysid 대조 뒤에만) | 쟁점 8, 문서 반영 목록 |
| 11 | `sitl` 10-13분과 4 vCPU runner의 실시간성 | 근거 없음(필수 5) | 올림 기준(15분, RTF 0.7) |
| 12 | `executor_node`의 이름이 두 곳에 있다 | 고칠 것(권고 6) | 생성기가 launch 인자로 넘긴다 |
| 13 | test-engineer의 구조와 시간 추정은 실측이 없다 | 근거 없음(필수 5와 같다) | P4에서 처음 검증. 올림 기준 |

reviewer의 착수 판정: P1, P2, P3a는 지금 착수할 수 있다. P3b는 필수 수정 반영 뒤다. 이 개정이 필수 7건을 반영했고, P3b에는 추가로 "P3b 착수 전 px4-engineer 승인 항목"(쟁점 4)이 걸려 있다.

reviewer 재확인이 필요한 지점
- M5 (나): 상수 이름과 값(`REASON_DISARM_FAILED = 13`), 위치, 의미 문장. golden 영향이 두 파일의 한 줄씩이라는 것.
- LAND 감시의 ARMED 한정 문단(쟁점 4).
- 지면 근접 취소의 [추정] 표기와 `[LAND]`의 PRECONDITION_FAILED 가능성(쟁점 3 M3).
- 올림 기준의 RTF 0.7.

px4-engineer 승인 반영(PR #21) 뒤 reviewer가 본 지점과 결과: 조건부였다. 처리는 "PR #21 reviewer 검증 반영"에 있다.

후속 개정에서 reviewer가 볼 지점
- `REASON_EXTERNAL_DISARM = 14`: 이름, 값, 위치, 의미 문장. M5 (나)와 같은 기준을 적용했다는 설명이 성립하는지. golden 영향이 두 파일의 두 줄씩이라는 것.
- 감시 표의 행 순위(잠정)와 그 근거. 순위 4-5를 6-8보다 앞에 둔 것.
- M3의 계약 문장과 미확인 목록이 실측 범위와 맞는지.
- architect가 채운 문장들("disarm 전송 뒤 받은 표본"의 기준, `[LAND]` 단독 미션의 ITEM_TIMEOUT 단서, 재전송 표에 옮긴 행).

## 다음 절차

1. reviewer가 위 "재확인이 필요한 지점"을 본다.
2. P0, P1, P2, P3a를 시작한다(README.md의 순서).
3. (닫힘 2026-11-11) px4-engineer가 "P3b 착수 전 승인 항목"을 닫았다(PR #21). P3b를 시작할 수 있다.
3b. (완료 2026-11-11) 후속 개정(PR #23)에 대한 px4-engineer 확인을 받아 반영했다(U5. px4-engineer PR #23 반영 확인(git 이력)).
3d. (완료 2026-11-11) P3a. 컨테이너 autostart가 동작하지 않아 쟁점 2를 자기 전이로 다시 결정했다.
3e. (완료 2026-11-11) px4-engineer의 최종 확인(px4-engineer 최종 확인(git 이력))으로 확인 예정을 모두 닫았다. P3b를 시작한다.
3c. px4-engineer의 필수 재실측 (2), (3), (5)는 P4 머지 전에, 나머지는 7단계 고정 전에 끝낸다.
4. GHCR Public 확인(사용자).
