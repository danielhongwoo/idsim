# Phase 1a 6번 작업: 새 취소 분기에 대한 ops-service-engineer 검토

작성 2026-11-11, ops-service-engineer. 대상: `decisions.md` 2번의 취소 분기 표, K4, K5, "ops 검토" 절의 질문 다섯. 관점: Phase 3 Fleet Manager(미션 상태 추적, 재배분)와 gRPC 소비자. 읽은 것: `decisions.md`, `opinion-px4.md`의 "추가 실험 답(E1-E5)", 5단계 `decisions.md`와 `opinion-ops.md`, `ExecuteMission.action`. 다른 파일은 고치지 않았다.

## 결론: 조건부 승인

항목으로 가르는 분기(사용자 5의 (5) (가))와 K5 문장("지상 disarm이거나 armed Hold 모드")은 승인한다. Fleet 쪽에서 막히는 경우는 없다. 조건은 셋이고 모두 1a 고정 전에 들어가야 한다(C1은 golden이 바뀐다).

- C1. result 끝에 기체의 끝 상태 필드를 더한다(질문 2). feedback과 텔레메트리로는 (A)와 (B)를 결정적으로 가를 수 없다.
- C2. 취소 착륙(CANCELING) 동안에도 실행 중 이상 판정(LINK_LOST, FAILSAFE, EXTERNAL_MODE_CHANGE)이 그대로 돌고, 취소 요청부터 result까지 상한이 있다는 것을 계약 문장에 둔다(질문 3).
- C3. 취소로 착륙을 끝낸 경우의 `last_item_index`와 `items_completed`의 값을 정한다(질문 2의 부속). 제안: `last_item_index`는 취소 시점에 실행 중이던 항목(TAKEOFF 줄이면 TAKEOFF의 번호), `items_completed`에 그 항목을 세지 않는다. 취소 착륙은 미션의 LAND 항목을 실행한 것으로 보지 않는다.

## 질문별 답

### 1. TAKEOFF 중 취소가 "착륙 뒤 CANCELED"여도 재배분에 문제가 없는가

문제없다. Phase 3에서 Fleet이 취소를 보내는 경우는 둘이다.
- 기체 이탈에 따른 재배분: 옛 기체의 취소 결과를 기다리지 않고 새 기체에 `attempt+1`로 보낸다(5단계 의견 2-4 그대로). 옛 기체는 대개 px4가 죽어 LINK_LOST로 끝나므로 취소 분기의 착륙 여부와 무관하다.
- 사용자의 `AbortMission`: 상승 중 기체를 착륙시켜 지상 disarm으로 돌리는 것이 운용상 더 안전하고 끝 상태가 하나라 Fleet의 가용 판정이 단순해진다.
- 상승 중인 기체를 공중에 세워 두고 새 미션을 주는 경우(표적 변경에 따른 재지정)는 Phase 3 범위의 단순 배분 규칙에 없다. 필요해지면 취소 의미가 아니라 미션 교체 기능으로 따로 정할 일이고, 그때도 LOITER에 들어간 뒤 취소하는 경로가 있다.

### 2. (A)와 (B)를 result만으로 알아야 하는가

알아야 한다(조건 C1). feedback과 텔레메트리로는 부족하다.
- feedback으로 가르기: Fleet이 마지막으로 받은 feedback의 항목은 취소가 Executor에 닿은 tick의 항목과 다를 수 있다. TAKEOFF 도달 판정 직후의 취소는 Fleet이 보기에 TAKEOFF인데 Executor는 LOITER 줄(B)로 간다. feedback은 best effort이고 순서와 도착을 보장하지 않는다.
- result의 기존 필드로 가르기: `last_item_index`와 Fleet이 보낸 미션의 항목 종류를 합쳐도 두 경우가 겹친다. (1) LOITER 줄의 Hold(B)와 LOITER 방어 줄의 착륙(A). (2) `[LAND]` 미션의 Land 명령 전 취소(B)와 뒤 취소(A). 둘 다 같은 번호, 같은 항목 종류다.
- 텔레메트리로 가르기: `VehicleState`는 5 Hz 참고 주기이고 result와 같은 시점의 값이 아니다. Fleet은 result 직후 다음 배분을 정하는데 그 판단이 텔레메트리 도착 순서에 기대면 단위 테스트에서 결정적이지 않다. 텔레메트리는 교차 확인으로만 쓴다.
- Executor는 자기가 어느 줄로 끝났는지 틀리지 않게 안다. 그 값을 result에 싣는 것이 가장 싸다.

제안(이름과 값은 architect가 정한다).

```
uint8 END_STATE_UNKNOWN = 0          # 계약이 약속하지 않음
uint8 END_STATE_GROUND_DISARMED = 1  # landed 참, arming_state 1을 확인하고 끝냄
uint8 END_STATE_ARMED_HOLD = 2       # arming_state 2, nav_state 4를 확인하고 끝냄
uint8 end_state
```

- 규칙: CANCELED와 SUCCEEDED는 0이 아니다(1a의 두 항목 순서는 SUCCEEDED면 항상 1이다). ABORTED는 Executor가 끝날 때 확인한 값이 있으면 싣고 없으면 0이다. ABORTED의 값은 계약이 약속하는 상태가 아니라 "Executor가 끝날 때 관측한 값"이다.
- "Hold 모드의 기체가 공중에 있다"는 이 필드도 약속하지 않는다(K5와 같다). 이름에 AIR를 넣지 않는 이유다.
- `MissionEvent`의 종료 사건에도 같은 값을 실을지는 Phase 2 고정 전에 정한다(비차단).

### 3. 취소 뒤 result까지 수십 초. 더 필요한 것

Fleet 쪽 설계: gRPC `AbortMission`은 취소 요청을 action에 넘긴 즉시 돌려주고, 미션 상태를 "취소 중"으로 둔다. 최종 상태는 result로 바꾼다. 그동안 그 기체는 배분 대상이 아니다. 필요한 것은 넷이다.
- (C2) 취소 착륙 중에도 실행 중 이상 판정이 돈다는 문장. 표의 "끝내지 못하면 LAND 항목의 실패 결과(ABORTED)"가 LINK_LOST, FAILSAFE, EXTERNAL_MODE_CHANGE까지 포함하는지 계약에서 읽히지 않는다. 포함하지 않으면 px4가 죽은 기체의 취소가 착륙 제한 시간(45 s)까지 매달린다.
- (C2) 상한. 취소 요청부터 result까지 "Hold 확인 2 s, disarm 확인 2 s, 취소 착륙 제한 시간(또는 LAND 항목의 `timeout`)의 합을 넘지 않는다"는 형태로 적는다. 값은 노드 파라미터라 계약 숫자가 아니어도 되고, Fleet은 이 합에 여유를 더한 자기 감시 시간을 둔다. 넘으면 Fleet은 END_STATE_UNKNOWN의 ABORTED와 같게 다룬다.
- CANCELING 동안 feedback을 계속 낸다는 것(주기는 계약이 아니어도 된다). Fleet이 "Executor가 살아서 착륙 중"과 "멈췄다"를 가르는 근거다. 취소 착륙 중의 `distance_remaining_m`은 남은 높이로 내거나 `distance_valid` 거짓으로 둔다. 어느 쪽인지 정해 두면 된다(비차단).
- 활성 goal에 대한 취소 요청은 항상 ACCEPT로 응답하고, 같은 goal에 대한 거듭된 취소는 무시한다(멱등). Fleet은 재배분 때와 기체가 다시 나타났을 때 같은 goal에 취소를 다시 보낸다(5단계 의견 2-4). 이미 지금 구현의 의도라면 문장만 더한다.

### 4. (B)의 기체에 곧바로 새 비행 미션(1b의 GOTO)을 주려면

1a에는 필요 없다. Phase 3의 첫 구현은 (B)를 `[LAND]`로 내리고 지상 disarm에서 다시 배분한다. 1b에서 Hold 기체의 직접 재지정을 열 때 필요한 시작 조건은 다음이다.
- 시작 조건: `arming_state` 2, `landed` 거짓, `nav_state` 4, `failsafe` 거짓, 위치 유효. 그리고 Executor가 공중임을 확인할 근거(높이 하한이나 앞 goal에서 넘겨받은 기준점). K5가 공중을 약속하지 않으므로, 지면 위 armed Hold에 GOTO가 들어가는 경우를 Executor가 막아야 한다. Fleet은 그 판정을 하지 않는다.
- PREPARING 경로: arm을 건너뛰고, setpoint를 현재 위치로 시작한 뒤 신호 유효와 Offboard 진입을 확인한다(Hold에서 `offboard_control_signal_lost` 참인 상태에서 시작하므로 1a의 6번 단계와 판정이 다르다. px4 실측 대상).
- 기준점: 이 goal에는 arm 직전 위치가 없다. GOTO의 좌표가 기준점 상대라면 기준점을 무엇으로 할지 1b에서 정해야 한다. 절대 좌표라면 필요 없다.

### 5. ABORTED로 끝난 기체의 처리

Fleet은 ABORTED 기체를 "격리"로 두고 배분하지 않는다. 복귀 조건은 텔레메트리로 지상 disarm(`landed` 참, disarm)이 일정 시간 이어지는 것이다. END_STATE_GROUND_DISARMED가 실려 오면 그 확인을 생략할 수 있다. armed로 공중이나 Hold가 아닌 모드에 남은 기체는 1a, 1b 계약으로 내릴 방법이 없으므로 운용자 표시만 하고 손대지 않는다. 미션 쪽은 5단계 의견 2-5의 사유별 재배분 표를 그대로 쓴다.

계약에 더 필요한 문장.
- ABORTED로 끝난 뒤 Executor는 그 goal로 /fmu/in에 아무것도 내지 않는다(발행 규칙 6번의 계약 쪽 문장).
- MODE_SWITCH_FAILED(Hold 미확인)는 "Land 명령을 보냈다"까지 계약에 적는다. Fleet은 그 기체를 착륙 진행 중으로 보고 격리한다.
- `VehicleState`(Phase 2 고정)에 위 복귀 판정에 쓸 `armed`, `landed`, 모드(Hold 여부)와 각 유효 플래그가 있어야 한다. 1a를 막지 않으며 Phase 2 스키마 검토 때 다시 올린다.

## architect에게 넘길 것

- C1의 필드 이름과 값, ABORTED 때의 의미. golden 변경은 작업 단위 H에서 함께 한다.
- C2, C3의 문장을 N1 초안에 더할지.
- 비차단: `MissionEvent` 종료 사건의 끝 상태, CANCELING 중 `distance_remaining_m`의 뜻.
