# test-engineer 확인: P3 단위 테스트 목록과 P4 실측 기록 (2026-11-11)

판정: 조건부 승인. 테스트 구조와 지시 목록의 방향은 맞다. core 단위로 결정적으로 쓰려면 아래 C1-C6을 문서에 먼저 반영한다. 근거는 decisions.md 쟁점 3, 4, 7, 9, 10과 담당자별 구현 지시.

## 1. 조건

C1. 쟁점 6 snapshot/port 승인 항목(또는 test 지시 첫 줄)에 core 입력 계약을 적는다.
- 문장: "core의 `step()`은 (tick 번호, ROS 시각, 최신 표본 1개와 그 `timestamp`와 수신 tick, Px4Timestamp 공급 port(실패 가능), 명령 sink, setpoint sink, 사건 sink)만 입력으로 받는다. core는 벽시계와 rclcpp를 부르지 않는다. core 테스트 target은 gtest와 core만 링크한다."
- 이유: 순위 1(`Px4Timestamp::now` 실패), "첫 disarm 전송 tick 뒤", "명령에 실은 Px4Timestamp"는 이 port 없이 결정적으로 쓸 수 없다. 구독 callback은 최신 표본만 저장하므로 tick당 표본은 최대 1개이고, 같은 timestamp 두 번은 같은 표본을 다음 tick에 다시 본 경우다. 이를 입력 모델로 명시한다.

C2. 쟁점 3 M5의 "전송 뒤에 받은" 기준에 셋을 못박는다.
- (a) 비교 대상은 첫 disarm 전송의 `Px4Timestamp`다(재전송마다 새 값).
- (b) "전송 tick 뒤"는 tick 번호로 정의한다(`수신 tick > 전송 tick`).
- (c) "3회 연속": 중복 timestamp는 건너뛴다(리셋도 가산도 아님), 비-DISARMED 표본은 리셋, timestamp가 줄어든 표본은 세지 않는다.

C3. 쟁점 4 감시 표에 "3회 연속/1회"가 어느 행에 걸리는지 한 줄. 순위 4-8이 모두 1회 판정이면 "엇갈려 시작"은 "먼저 끝난 goal 뒤의 표본은 효과가 없다"가 되고, 테스트는 "종료 사건이 정확히 1건이고 이후 step이 명령, 사건, 상태를 바꾸지 않는다"로 쓴다. 누적이 걸린 행(LINK_LOST 등)은 적는다.

C4. 지상 disarm 분기(M5)에 LINK_LOST를 정한다. 지금은 공중 분기(M4)에만 있다. 지상 분기에서 `link_timeout` 2 s가 `mode_confirm_timeout` 3 s보다 짧아 LINK_LOST가 먼저 걸리는데 reason이 없다. DISARM의 TEMPORARILY_REJECTED가 아닌 거부 ack(DENIED 등)도 정한다. 재전송 표의 "같다"가 ARM 행을 가리키는지 분명히 한다. 한 줄씩 추가하고 테스트 한 건씩.

C5. 취소와 완료의 같은 tick 충돌 규칙. LAND에서 DISARMED 3번째 표본과 cancel이 같은 tick이면? ITEM_TIMEOUT 정리 중 cancel은? 권고: "종료는 먼저 정해진 것이 이긴다. 같은 tick이면 ABORTED 사유, 완료, 취소 순이고, 종료 뒤의 cancel은 무시한다."

C6. 측정 스크립트는 `tests/sitl/measure/`에 둔다(소유 test-engineer, px4-engineer가 절차의 필수 승인자). 넘김 목록의 미결 항목은 이것으로 닫는다. 출력 형식은 4절. P4 선행 조건이다.

## 2. 지시된 테스트가 결정적으로 쓸 수 있는가

- 지시 (1)-(3): PX4 없이 core에서 쓸 수 있다(C1, C2 전제).
  - (1)은 DISARMED 1회와 2회 두 경우로 나눈다. 3번째에서의 취소는 C5. 단정에 "발행이 이미 멈춘 상태이므로 지상 setpoint를 새로 켜지 않는다".
  - (2)는 표본이 아예 없는 경우(C4의 LINK_LOST 경계)와 묵은 timestamp의 DISARMED가 계속 오는 경우(vacuous 위험을 직접 잡음)로 나눈다. 단정: 종료 시점이 전송 시각 + `mode_confirm_timeout`인지(`>`와 `>=`를 못박음), 종료 직전 disarm 재전송, reason DISARM_FAILED, `landed`가 false로 바뀌면 공중 분기.
  - (3)은 전송 tick 전 표본, timestamp가 같은 표본, 줄어든 표본, 같은 timestamp 중복, [ARMED(새), DISARMED, DISARMED, ARMED(새)] 같은 늦게 처리된 arm 경합(리셋 확인).
- 감시 표: 같은 tick 동률은 표 주도형(parametrize)으로 동시에 맞을 수 있는 행 쌍(1-3은 서로와 모든 행, 6-8끼리와 4-5끼리는 배타)을 전부 만들어 앞선 순위가 이기는지 본다.
- 순위 5 이력 가지: 두 건 추가. (i) 이력은 이 항목 안에서만 유효(TAKEOFF에서 본 failsafe가 LOITER로 넘어오지 않음). (ii) OFFBOARD이고 ARMED인 채 `failsafe == true`인 표본은 어느 행에도 걸리지 않고 goal을 끝내지 않는다. (ii)는 "failsafe를 보면 즉시 멈춘다"(발행 규칙 근거)와 표가 어긋나 보이는 지점이다. 테스트는 표대로 쓰되 architect가 의도를 한 줄 확인한다.
- disarm 분류 고정 규칙(approval-px4-p3b.md 5번): test 지시에 없다. 반드시 넣는다. 첫 DISARMED 때 landed false였다가 뒤에 true가 되어도 FAILSAFE 유지, 반대도 지상 유지. 적용처 셋(감시 표 두 행, LAND 완료 우선, 취소의 Hold 확인 창)에 각 한 건.
- ITEM_TIMEOUT: "arm 뒤 DISARMED snapshot의 ITEM_TIMEOUT은 disarm 분기" 한 건. "지상 disarm이면 바로 끝"은 전용 테스트 없이 불변식 한 건("setpoint 항목이 시작될 때 `arm_sent == true`"). 나머지는 분기별(공중 Hold 성공, Hold 불확인 시 Land, 지상 arm의 disarm, LAND 항목 세 변형과 landed인 ARMED의 detail). 모든 분기에서 reason이 ITEM_TIMEOUT으로 유지되고 detail만 다름을 단정. 항목 timeout이 흐르기 시작하는 시점(TAKEOFF는 ARMED 확인, LOITER는 앞 항목 완료, LAND는 앞 항목 완료 또는 PREPARING 끝)을 시각 경계 테스트로.
- 취소 분기: 공중, 지상 arm, 지상 disarm + arm 안 보냄(즉시 CANCELED), 지상 disarm + arm 보냄(disarm 분기)의 분기 고르기 표. 매 tick 다시 고르기(Hold 뒤 landed true), Hold 거부 ack와 hold_confirm_timeout의 Land 경로, CANCELING 중에는 감시 표를 쓰지 않음, [LAND] 단독 미션 취소(발행 없음), PREPARING 중 취소(arm 재전송이 그 tick에 멈춤).
- 빠진 것: PREPARING 실패 정리(M5 마지막 문단). arm 뒤 ARM_REJECTED, arm_timeout, offboard_signal_timeout 등으로 실패하면 지상 setpoint + disarm, 원래 reason 유지, disarm 미확인은 detail. 한 건씩.
- 중복 정리: 취소, ITEM_TIMEOUT, PREPARING 실패는 같은 "정리 분기 선택" 함수를 공유. (원인 3종) x (snapshot 유형 5종) 교차표 한 벌로 쓰고 분기 내부(disarm 확인, Hold 확인)는 따로 한 번씩.
- status/reason 대응표: 모든 `REASON_*`(13, 14 포함)가 정확히 한 status에 대응하는지 전수 표. core의 reason enum과 생성된 메시지 상수 값이 같다는 교차 검사를 shim 쪽 gtest에 한 건(상수가 늘면 깨짐).
- 종료 사건 == result: 하네스 불변식으로 모든 시나리오에 건다(종료 사건 정확히 1건, ACCEPTED가 앞, 종료 뒤 사건 없음, mission_id/status/reason이 result와 일치). result와 사건을 한 `Termination` 객체에서 만드는 구조를 ros2-engineer에게 요구하고, 노드 배선 gtest(정상, 무효 각 한 경로)에서 두 소비자가 같은 값을 받는지 한 번.

## 3. 노드 쪽과 P4 지원 코드

- `lifecycle.self_start` false: 같은 spin 횟수 K에서 true는 active, false는 unconfigured인 대조군 쌍. 이어서 직접 trigger_configure/activate 성공, goal 실행 중 deactivate 거부, on_shutdown이 실행 중 goal을 ABORTED/REASON_INTERNAL로 끝내고 사건을 내는지. 컴포넌트 gtest(가짜 발행자). on_activate의 /clock 2 s 대기는 배선 테스트에서 override 가능한 param이거나 그 대기만 벽시계 예외로 명시.
- 구독 먼저 순서 규칙: DDS 효과(87/400)는 단위로 재현되지 않는다. 단위로는 구조를 건다: `tests/support/mission_client.py`가 `create_subscription(mission_event)`를 `create_client`보다 먼저 같은 node 객체로 하는지 mock 검사. 효과는 P3a 0/400과 시나리오의 EVENT_MISSING 분류가 받친다. test 지시에 적는다.
- 구조: 시나리오를 tick 열(snapshot 열)로 쓰는 작은 DSL 헬퍼. 테스트 이름에 감시 표 순위와 행 번호, 표 행 수와 parametrize 수가 같다는 단정 한 건. core 소스에 `chrono::*clock::now`와 `rclcpp`가 없다는 grep 검사를 lint에.

## 4. P4 실측 항목의 기록 방법

- 시도마다 기계가 읽는 행(`measure_<항목>.tsv` 또는 jsonl): run id, commit과 dirty, 이미지 key, 시도 번호, 주입 조건과 trigger 이벤트, 결과, ROS 시각과 벽시계 소요, 종료 코드, ULog와 MCAP 경로. 실패한 시도를 빼지 않는다. 재시도나 rerun 없음. 수집 위치는 run_sitl.sh와 같은 아티팩트 디렉터리.
- 통과 기준을 실행 전에 요약 파일 머리에. stop 검증 기준: 유예 안 종료, 정리 로그 있음, 종료 사건 수신, exit code 분포. trigger는 sleep이 아니라 이벤트(feedback phase, landed 표본).
- 회수의 한계: 10회 0건은 실패율 95% 상한 약 26%(3/n). "10/10 통과"를 "플래키 없음"으로 쓰지 않는다. repeat.sh 구조 재사용.
- stop 검증 10회 중 goal 실행 중 3회 이상은 단계 분포가 비어 있다. 최소 PREPARING, TAKEOFF, LOITER, LAND 각 1회(4회 이상). 종료 사건 수신은 구독자(테스트 노드)에서 기록하고 못 받으면 "수신 실패"로 남긴다.
- 결함 주입(vehicle.id 누락의 unhealthy까지): 시작은 compose up 시각, 끝은 `.State.Health.Log`의 첫 unhealthy. 벽시계 측정임을 행에 명시. 정상 healthy까지와 쌍으로.
- (5)의 `timestamp - Px4Timestamp` 부호 있는 분포는 C2 "엄격히 뒤" 규칙의 근거. 분포가 0 근처에서 부호가 섞이면 결과가 나온 뒤 C2 기준을 다시 확인하도록 px4와 architect에게 넘긴다. 단위 테스트는 합성 값만 검사하므로 실제 시계 관계는 이 실측만이 확인한다는 점을 test 지시에 명시.

## 5. 정리

수용: 지시 (1)-(3), 감시 표 5종류, 죽은 분기 배제, 구조(GoogleTest, port 주입).
추가 필요: disarm 분류 고정, PREPARING 실패 정리, 정리 분기 교차표, 대응표 전수, 하네스 불변식, 순위 5 이력의 항목 경계와 OFFBOARD failsafe 음성.
선결: C1-C6. P3 구조 승인은 C1-C5 반영 즉시 줄 수 있다. 반영 전 구현은 시작해도 되지만 C2와 C4는 구현이 갈리기 쉬우므로 먼저 정한다.
