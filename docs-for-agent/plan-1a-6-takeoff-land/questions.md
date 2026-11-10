# Phase 1a 6번 작업 설계 토론 질문지

작성 2026-11-10, architect. 계획 초안은 같은 디렉터리 `README.md`다. 넘김 항목 번호(A1, B1, C1, D1 등)는 그 문서의 표를 가리킨다.

## 공통 규칙

- 각 질문은 "실측"이나 "원문"을 먼저 하고, 그 결과 위에서 "의견"을 적는다. 실측 없이 의견만 적은 답은 받지 않는다.
- 답의 문장마다 [실측](이 호스트에서 직접 돌린 것. 스택 번호, run id, 반복 횟수, 명령을 적는다), [소스](PX4 v1.17.0 원문. 파일과 행, 사본의 출처와 태그 대조 방법을 적는다. B10), [문서](링크), [추정]을 붙인다.
- 호스트는 4 vCPU, 7GB RAM이다. 시간과 메모리 실측값에는 그때 함께 떠 있던 것(스택, 빌드, GUI)을 적는다.
- 탐침 스크립트와 실험 산출물은 scratchpad에 둔다. 저장소 파일은 바꾸지 않는다. 다른 스택과 겹치지 않게 스택 번호 k를 고른다.
- /fmu/in에 쓰는 탐침은 스택 안에서만 쓰고 저장소에 넣지 않는다.
- 답은 `docs-for-agent/plan-1a-6-takeoff-land/opinion-<담당>.md`로 낸다. 완성형 한글과 아스키만 쓰고 음차하지 않는다.
- 시각은 "ROS 시각(`use_sim_time`이면 `/clock`)"으로 적는다. 시간 값을 제안할 때는 그 축(ROS 시각인지 벽시계인지)을 적는다.
- "충돌 예상"은 다른 담당자의 답과 부딪칠 것으로 architect가 보는 곳이다. 상대의 입장을 짐작해 맞추지 말고 자기 영역의 근거만 적는다. 재질문은 architect가 한다.

## px4-engineer (13문항)

P1. Offboard 진입과 PREPARING 순서(C18).
- 실측: 탐침으로 (가) setpoint 20 Hz 발행 시작 -> arm -> DO_SET_MODE(Offboard), (나) setpoint -> DO_SET_MODE -> arm 두 순서를 각각 5회. 회마다 setpoint 발행 시작부터 `nav_state` 14까지, arm 명령부터 `arming_state` 2까지의 PX4 timestamp 차이. 부팅 뒤 `xy_valid`, `z_valid`, `pre_flight_checks_pass`가 참이 되는 시각의 분포(스택 재기동 5회).
- 원문: Offboard 신호 유효 판정과 모드 전환 가능 조건(Commander, `offboard_control_signal_lost`가 풀리는 조건). roadmap의 "모드 전환 전 최소 10회"가 v1.17.0에서 횟수 조건인지 시간 조건인지.
- 의견: PREPARING의 순서, 단계별 타임아웃 기본값, 실패한 단계와 `reason`(NOT_READY, ARM_REJECTED, MODE_SWITCH_FAILED)의 대응.

P2. 시동 상태에서 신호 없는 Offboard 요청(A9).
- 실측: arm 뒤 setpoint 없이 DO_SET_MODE(Offboard). ack의 result 값, `nav_state` 변화. disarm 상태에서도 같은 것.
- 의견: Executor가 ack로 알 수 있는 것과 `nav_state`로만 알 수 있는 것의 구분.

P3. DO_SET_MODE와 SET_NAV_STATE(A5).
- 원문: 두 명령의 Commander 처리 경로 차이(v1.17.0).
- 실측: 필요하면 같은 전환을 둘로 해 보고 ack와 `nav_state`를 비교.
- 의견: 지금 빌더(DO_SET_MODE)를 유지하는지. 바꾸자면 근거.

P4. Hold 실험(C1, C2, C27, C32).
- 실측(각 5회 이상):
  - (가) Offboard 호버 중 `set_mode_hold`. ack, `nav_state`가 4가 되기까지의 시간 분포, 전환 순간의 위치 변화.
  - (나) (가) 뒤 setpoint 발행을 끊는다. 모드와 위치가 그대로인지, `offboard_control_signal_lost`가 서는지, 선다면 Hold에 영향이 있는지.
  - (다) setpoint를 끊어 Offboard 손실 failsafe(이 스택은 Land)를 일으키고, 내려오는 중에 `set_mode_hold`. ack, `nav_state`, `vehicle_status.failsafe`의 변화.
  - (라) (다)에서 setpoint를 다시 보내기 시작한 뒤 `set_mode_hold`.
  - (마) 위치 추정 무효 상태를 SITL에서 만들 방법이 있으면 그 상태의 Hold 요청. 없으면 없다고 적는다.
- 원문: failsafe 동작 중의 사용자 모드 요청 처리(failsafe 상태기와 모드 요청의 우선순위), armed 상태 Hold 전환의 위치 조건.
- 의견: 취소 분기의 확정안(공중 정상, failsafe 진행 중, 확인 실패 각각의 GoalStatus와 `reason`). Hold 확인 타임아웃 기본값과 그 근거(실측 분포의 몇 배). 확인 실패 때 Land를 보내는 지금 규칙이 맞는지.

P5. 지상 취소와 disarm(C3).
- 실측: 비강제 disarm을 (가) arm 직후 지상, (나) Offboard 진입 뒤 상승 직전(TAKEOFF setpoint를 낸 직후), (다) 착지 직후 `landed`가 참이 되기 전에 각각 보낸다. ack result와 `arming_state`.
- 원문: 비강제 disarm의 수락 조건.
- 의견: "지상"을 Executor가 무엇으로 판정하는지, disarm이 거부되거나 확인되지 않을 때의 분기(GoalStatus, `reason`, 다시 보낼지).

P6. LAND 항목(B1, C7).
- 실측: 호버 중 `land()` 명령. `nav_state` 18까지의 시간, 착지까지의 하강 속도, `vehicle_land_detected.landed`가 참이 되는 시각과 `arming_state`가 1이 되는 시각의 차이, `COM_DISARM_LAND`의 실제 저장값. LAND 명령 뒤 Offboard setpoint를 계속 냈을 때와 끊었을 때의 차이. 5회.
- 원문: NAV_LAND가 읽는 param(1-7)과 공중에서의 동작. 빌더의 "param4-7 NaN"이 뜻하는 것.
- 의견: land 완료 판정에 쓸 토픽과 조건, LAND 항목 중 setpoint 발행을 언제 멈추는지, 자동 disarm이 오지 않을 때의 처리.

P7. TAKEOFF 항목(C5, C6).
- 원문: Offboard position setpoint의 상승 속도를 제한하는 파라미터(이름과 이 스택의 값).
- 실측: 지상에서 상대 높이 5 m setpoint 하나를 준 상승. 최대 상승 속도, overshoot, 정착 뒤 30 s 동안 z의 표준편차와 최대 편차. 5회. 지상에 서 있을 때 `vehicle_local_position.z`의 drift(arm 전 60 s).
- 의견: `acceptance_m` 기본값, 도달 판정의 "N회 연속"과 표본 주기, "항목 시작 위치"의 기준점을 언제 잡는지.

P8. 지상과 공중의 판정(C25).
- 원문과 실측: TAKEOFF의 시작 조건(지상)과 취소 분기(공중인가)에 쓸 근거 토픽. `vehicle_land_detected`의 필드별 의미, arm 전과 상승 직후의 값 변화 시각.
- 의견: NOT_READY와 PRECONDITION_FAILED를 가르는 조건표.

P9. sim 시간 timestamp 경로의 failsafe 회귀(A8, B5, B6).
- 실측: Offboard 호버 중 setpoint의 timestamp를 ROS 시각보다 0.5, 0.9, 1.1, 2.0 s 묵게 보낸다(발행 주기는 20 Hz 유지). 각각 `offboard_control_signal_lost`가 서는지와 서기까지의 시간. 5회씩. failsafe 뒤 Land가 끝나 disarm되기까지의 시간.
- 실측: 정상 발행에서 PX4가 본 setpoint의 나이(가능하면 ULog나 uORB로)와 `COM_OF_LOSS_T`의 여유.
- 의견: 회귀 판정의 경계값(어느 묵음에서 반드시 failsafe, 어느 묵음에서 반드시 정상). S5에 `vehicle_status.timestamp`와 `/clock`의 차이 상한 판정을 넣을지와 상한값.
- 충돌 예상: 묵은 timestamp를 누가 어떻게 보내는지(T6, R1). 탐침으로는 가능해도 저장소의 회귀 테스트에 넣는 방법은 따로 정한다.

P10. Hold와 반복 비행 중의 다른 failsafe(C4).
- 실측: 이 스택의 `param show`로 배터리(`COM_LOW_BAT_ACT`, `BAT_*_THR`), geofence, 바람, 비행 시간 관련 파라미터와 SITL 배터리 시뮬레이션 파라미터의 실제 값.
- 원문: 각 기본값이 Hold 중에 모드를 바꾸는지.
- 실측: 스택을 내리지 않고 비행을 반복하거나 Hold로 길게 두었을 때 배터리 잔량의 변화율.
- 의견: "Hold에서 벗어나는 경로"의 목록. `sitl_params.env`에 더할 값이 있는지(있으면 이유).

P11. source 값 표(A4, B2, B3).
- 실측: 비행 1회 동안 `vehicle_command_ack` 전부를 기록해 `target_system`, `target_component`, `command`의 분포. PX4 내부 명령의 ack가 섞이는지와 그 값.
- 원문: `from_external`의 처리 경로(false면 MAVLink로 재송출된다는 주석의 근거).
- 의견: 역할별 표(Mission Executor, pytest 하네스, `check_px4.py`, 손으로 보내는 CLI). 금지 조합. 기체가 여럿일 때 Executor끼리 값이 같아도 되는지.

P12. 식별 게이트(A3).
- 실측: PX4 healthy 뒤 `vehicle_status` 첫 수신까지의 시간(ROS 쪽에서 본 값).
- 의견: 4단계의 조건(명령만 막고 setpoint는 막지 않는다, 미수신이면 보류, 불일치면 오류)을 6단계 절차에 그대로 적용하는지. 불일치가 실행 도중에 드러나면(재부팅 등) 무엇을 하는지.
- 충돌 예상: 불일치를 activate 실패로 할지 goal의 NOT_READY로 할지(R5, D3).

P13. 실행 중 이상의 판정.
- 원문과 실측: REASON_FAILSAFE, REASON_EXTERNAL_MODE_CHANGE, REASON_LINK_LOST를 가를 근거 필드(`vehicle_status.failsafe`, `nav_state`, `failsafe_flags`). QGC로 모드를 바꿨을 때 보이는 것. `vehicle_status`의 최대 수신 간격(ROS 쪽, 비행 1회).
- 의견: 세 사유의 판정 조건과 LINK_LOST의 미수신 임계 기본값.

## ros2-engineer (14문항)

R1. `/clock`과 timer의 시계(B5, D5).
- 실측: `bridge`를 거친 `/clock`의 발행 주기와 간격 분포(벽시계 기준과 sim 기준). `use_sim_time` 노드에서 ROS 시각 50 ms timer의 실제 발화 간격 분포(1000회, 유휴 상태와 CPU 부하 상태), 같은 조건의 wall timer. `/clock` 수신에서 `now()` 반영까지의 지연. clock 전용 스레드 옵션의 영향.
- 의견: 20 Hz setpoint timer, 항목 `timeout`, Hold 확인 시간에 쓸 시계. `/clock`이 멈추면 각각 어떻게 되는지.
- 충돌 예상: PX4는 setpoint의 신선도를 자기 시각(sim 시간)으로 본다(P9). timer의 시계 선택이 그 여유를 정한다.

R2. 노드 구조(A13).
- 실측: `LifecycleNode`에 `rclcpp_action` 서버를 만들었을 때 inactive 상태에서 goal이 어떻게 처리되는지, deactivate 때 실행 중인 goal이 어떻게 되는지. 실행 흐름이 길게 도는 동안 20 Hz timer가 막히지 않는 executor와 callback group 구성(원형 코드로).
- 의견: 컴포넌트(기체당 컨테이너)로 만들지 단독 실행 파일로 둘지. Phase 2에서 Collector가 합류할 때 바뀌는 것.

R3. activate 조건과 active 판정(A7, D6).
- 실측: `/clock` 첫 수신 전 `Px4Timestamp::now`의 실패를 activate에서 다루는 방식별 동작(전이 callback 안에서 기다리기, 실패로 돌려주고 다시 시도하기). `ros2 lifecycle get` 한 번의 소요 시간과 그동안 생기는 DDS 참가자.
- 의견: configure와 activate 전이를 누가 거는지(launch 파일은 생성하지 않는다). healthcheck 명령의 초안.
- 충돌 예상: healthcheck의 비용과 주기(D3).

R4. 식별 파라미터와 이름(A1, A2, C8).
- 실측: 노드를 `/<vehicle_id>` 네임스페이스에 두고 상대 이름 `execute_mission`(`Mission.ACTION_NAME`), `mission_event`(`MissionEvent.TOPIC_NAME`)를 썼을 때 `ros2 action list`, `ros2 topic list`의 결과. PX4 토픽과 같은 네임스페이스에 있어도 충돌이 없는지.
- 의견: params key 이름의 확정안(`vehicle.ns`, `vehicle.sysid`, `vehicle_id`의 관계. `ns`와 `vehicle_id`를 둘 다 줄지), 대조 함수와 `declare_vehicle_identity`의 시그니처, 노드 네임스페이스와 params가 어긋날 때의 처리.

R5. 식별 게이트의 위치(A3).
- 의견: `vehicle_status` 미수신, 불일치 각각을 lifecycle 전이(activate 실패, ERROR)와 goal 결과(NOT_READY) 중 어디에 대응시킬지. 근거는 R2, R3의 실측.
- 충돌 예상: px4의 조건(P12), `up --wait`의 실패 보고(D3).

R6. setpoint 헬퍼(A6, B4).
- 의견: API 초안. 입력 좌표(로컬 NED인지 ENU인지), yaw, `Px4Timestamp`, `offboard_control_mode`의 position만 참. 1b의 world ENU -> 로컬 NED 변환이 들어올 자리. 헬퍼가 `idsim_common`에 있어야 하는 근거와 `idsim_mission`에 둘 때의 차이.

R7. action 서버와 단위 테스트(C9, C20, C21, C22).
- 실측: 5단계의 실측(흉내 action)을 실제 `idsim_interfaces/action/ExecuteMission`으로 다시 해 BUSY, VEHICLE_ID_MISMATCH가 같은지. `tools/ros_ws.sh test`의 조건(`--network none`)에서 action 서버와 클라이언트를 한 프로세스에 둔 테스트가 도는지와 소요 시간.
- 의견: 시뮬레이터 없이 고정할 범위(수락 정책, GoalStatus와 `reason`, 종료 `MissionEvent`와 result의 일치, 취소 분기). PX4 쪽을 무엇으로 대신할지. `last_item_index` 구분 필드가 구현에서 필요한지.

R8. `MissionEvent` 발행(C10).
- 실측: `rclcpp_action`의 goal UUID를 `uint8[16]`으로 옮긴 값이 `_action/status`의 `goal_id`와 같은지.
- 의견: 사건 토픽 QoS 함수를 어디에 둘지(1b의 `state_pub_qos()`와의 관계). 접수 사건을 `handle_accepted` 진입에서 내는 것과 mutex 판정의 순서.

R9. 패키지 구조(C19, C24, C29).
- 의견: 검증, 분류, 항목 실행 절차를 6단계부터 ROS 비의존 라이브러리로 나눌지, 노드 안에 두고 1b에서 나눌지. 근거로 각 안에서 6단계 단위 테스트가 덮는 범위와 1b에서 다시 쓰는 양을 적는다.
- 충돌 예상: roadmap은 순수 상태기를 1b 1번에 둔다. 6단계에 당기면 범위가 늘고, 미루면 취소 분기를 SITL로만 검증하게 된다(T5).

R10. 컨테이너 사이의 action(리스크 표).
- 실측: `runner`의 rclpy action client와 다른 컨테이너의 action 서버가 맺어지는지(goal, feedback, result, cancel). `wait_for_server`까지의 시간. `use_sim_time`인 rclpy 노드에서의 동작. `result_timeout` 10 s가 지난 뒤 결과를 요청했을 때의 동작.

R11. 이름 상수와 검사 범위(C11, B7).
- 의견: 이름 상수를 namespace 범위 static 초기화식에 쓰지 않는 규칙을 코드에서 어떻게 지키게 할지. params yaml이 생길 때 `px4-api` 검사가 봐야 할 것.

R12. clang-tidy 범위(B9).
- 실측: `idsim_mission`이 `px4_topics.hpp`, `px4_io.hpp`를 include하는 소스를 가질 때 그 헤더가 tidy에 걸리는지(원형으로).
- 의견: `test/`를 tidy 대상에 넣을지.

R13. DDS 참가자 수.
- 실측: 지금 스택의 참가자 수와 인덱스 사용. 운용 노드 서비스, pytest, healthcheck의 `ros2` CLI, `foxglove`가 더해질 때의 수. `MaxAutoParticipantIndex` 50의 여유.

R14. `foxglove` 화이트리스트(D2).
- 의견: 토픽 화이트리스트의 초안(setpoint, `vehicle_local_position`, `vehicle_status`, `mission_event` 등)과 표기 방식. 기체 수가 늘어도 그대로 쓰이는지.

## test-engineer (11문항)

T1. 스택을 올리는 주체와 fixture 수명.
- 실측: `runner` 컨테이너 안에서 `docker compose`를 쓸 수 있는지(지금 이미지와 마운트). `tools/stack.sh up`과 `down`의 소요 시간(이 호스트, 3회), 이륙-호버-착륙 1회의 sim 시간과 벽시계 시간(P7의 탐침을 빌려도 된다).
- 의견: `docs/architecture.md`의 "pytest fixture가 compose를 올린다"와 "pytest는 `ros-ws` 컨테이너 안에서"를 어떻게 함께 만족시킬지(스모크처럼 호스트 스크립트가 올리고 `runner`가 판정하는 구조인지, 다른 구조인지). 스택의 수명(세션 하나, 시나리오마다).
- 충돌 예상: 시나리오마다 재기동하면 `sitl` job 시간이 는다(D7). 공유하면 상태가 샌다.

T2. `/clock` 시계(A12).
- 실측: `tests/support/receive.py`에 `/clock` 기반 시계를 주입했을 때 `hold_state`와 `_wait`의 동작. `/clock`이 오지 않을 때 판정이 영원히 기다리는지.
- 의견: `/clock`이 멈춘 경우의 벽시계 상한을 어디에 두는지(판정이 아니라 안전망으로).

T3. 판정 값(C5, D7).
- 의견: "목표 고도 도달"과 "착륙 후 disarm"의 판정식, "N회 연속"의 N, 타임아웃(ROS 시각). 고도 판정의 독립 기준(Executor의 feedback이 아니라 `vehicle_local_position`). P7의 실측값이 필요한 곳을 표시한다.

T4. `MissionEvent`와 goal 전송 순서(C13, C14, C30).
- 실측: 구독 생성 -> 발행자 수 1 이상 확인 -> `wait_for_server` -> goal 전송 순서로 20회. 접수 사건을 잃은 횟수. 확인을 빼면 잃는지.
- 의견: 확인 함수의 위치(`tests/support`)와 타임아웃의 시계. 결과를 받는 시점이 `result_timeout`에 걸릴 수 있는지.

T5. 시나리오와 층 배치.
- 의견: 아래 각각을 SITL, 단위(가짜 PX4), 수동 중 어디에 둘지와 근거. 정상 비행, 공중 취소(Hold 뒤 CANCELED), 지상 취소, BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION(GOTO 포함), NOT_READY, PRECONDITION_FAILED(공중에서 TAKEOFF), ITEM_TIMEOUT, failsafe 회귀. PR마다 도는 것과 로컬에서만 도는 것.
- 충돌 예상: 단위에 두려면 ROS 비의존 핵심이 6단계에 있어야 한다(R9). SITL에 두면 job 시간이 는다(D7).

T6. failsafe 회귀 판정의 주입 방법(A8).
- 실측: 방법별로 실제로 되는지. (가) Executor가 도는 동안 `bridge`를 멈춰 `/clock`을 끊는다(그때 Executor의 timestamp와 발행이 어떻게 되는지는 R1에 달려 있다). (나) 하네스가 /fmu/in에 묵은 timestamp를 직접 보낸다(`px4-api` 검사와 "접근은 `idsim_common`만" 원칙에 걸린다). (다) Executor에 시험용 파라미터를 둔다.
- 의견: 어느 방법이 "B안 경로가 살아 있다"를 실제로 검증하는지, 각 방법이 깨는 원칙.
- 충돌 예상: px4(P9), ros2(R1), architect의 원칙.

T7. 종료와 teardown(C15, C16).
- 의견: 테스트가 실패해도 도는 teardown의 순서(취소된 기체의 착륙과 disarm 확인, 로그와 ULog 수집, `down`). 프로세스 종료 신호 규칙. teardown 자체가 실패할 때의 보고.

T8. 하네스의 PX4 접근(A4, A10).
- 실측: rclpy 메시지 클래스의 `MESSAGE_VERSION`으로 토픽 접미사를 파생하는 방식이 골든 65개와 맞는지.
- 의견: Python 쪽 이름 규칙(쌍둥이 함수와 정규식 중). 하네스가 /fmu/in에 쓰는 일이 6단계에 남는지(남으면 source 값은 P11의 표를 따른다).

T9. "3회 연속"과 플래키 정책(D9).
- 의견: 3회의 정의(스택 재기동을 포함한 3회인지), 기록 방식(run id), 실패 1회가 나왔을 때의 절차. CI에서의 반복 횟수.

T10. 디렉터리와 진입점.
- 의견: 통합 테스트의 위치(`tests/sitl/` 등), 진입 스크립트와 `run_smoke.sh`의 관계, `tools/ros_ws.sh`의 패키지별 테스트 단정이 `idsim_mission`에 요구하는 것.

T11. 설정 일치 검사(C28).
- 의견: `inputs.cyclonedds_xml` sha256 대조를 6단계 통합 테스트의 어디에 넣을지. 스모크와 같은 코드를 쓰는지.

## devops-engineer (11문항)

D1. `stack.json`의 `vehicle_id`(C12).
- 실측: 생성기에 필드를 더했을 때 golden 4종의 diff 범위. `tests/support/stack.py`의 검증 표에 더할 줄.
- 의견: 위치와 이름, `schema` 번호를 유지할지(결정 (m)의 선례는 `generator.version` 증가).

D2. 노드 params 파일(A1, D4, B7).
- 실측: ROS 2 params yaml을 `--params-file`로 줄 때 노드 이름과 네임스페이스 표기(와일드카드 포함)별 적용 여부.
- 의견: 파일 위치(`artifacts/runs/<실행 id>/` 아래), 기체별 파일인지, 생성기가 싣는 key(식별, `use_sim_time`)와 싣지 않는 것(미션 노드의 조정 값은 패키지 기본값인지). `px4-api` 검사 범위.
- 충돌 예상: key 이름은 ros2가 정한다(R4).

D3. 운용 노드 서비스(D6, D15).
- 의견: 서비스 이름과 단위(스택에 하나인지 기체마다 하나인지. Phase 3에서 기체 수만 바꿔 재사용되는지), command, healthcheck(명령, interval, `start_interval`), `startup.stages`의 단계, 실패 때 `stack.sh`가 보고할 내용. 스모크 S2-S5가 이 서비스까지 올리는지와 S4 골든에 미치는 영향.
- 충돌 예상: lifecycle 전이를 누가 거는지와 healthcheck 비용(R3), 식별 불일치가 `up --wait` 실패가 되는지(R5).

D4. 빌드와 install 부재 검사(A11).
- 실측: 이 호스트에서 `tools/ros_ws.sh build`의 콜드 소요 시간과 최대 메모리(스택이 내려가 있을 때, 떠 있을 때). 빌드 산출물의 소유 uid.
- 의견: `stack.sh up`의 검사 문구와 종료 코드. 빌드와 스택 가동을 겹치지 않게 할 규칙이 필요한지.

D5. ros-ws 이미지의 foxglove_bridge(D1).
- 실측: apt의 `ros-jazzy-foxglove-bridge` 버전, 설치 크기 증가, 새 이미지 key와 빌드 시간. `lichtblick` 공식 이미지의 digest와 크기.
- 의견: `versions.env`의 고정 방식. 이미지 변경을 앞쪽 PR로 분리하는 것에 대한 입장.

D6. `viz` 서비스(D2).
- 실측: `foxglove_bridge`의 실행 인자로 주소, 포트, 화이트리스트, capabilities 제한이 실제로 적용되는지(clientPublish가 거부되는지).
- 의견: 생성기의 단정과 단위 테스트에 더할 성질, golden, lint의 `compose config`.

D7. `sitl` job(D8, D12, A15).
- 실측: GHCR 패키지의 지금 공개 상태. 러너에서 이미지 세 개를 받는 시간(가능하면 임시 workflow가 아니라 기존 build job의 기록에서), `tools/ros_ws.sh build`와 스택 기동, 비행 1회, `down`의 합. `artifacts/runs/`의 크기(ULog 포함).
- 의견: 트리거, concurrency, `timeout-minutes`, 실패 때 올릴 아티팩트, unit job과 빌드를 나눠 쓸지. 15분 안에 들어오는 시나리오 수.
- 충돌 예상: 시나리오 범위(T5), fixture 수명(T1). 러너 시간은 사용자 결정 후보다.

D8. 벽시계 제한.
- 실측: 러너와 이 호스트에서 `STACK_UP_TIMEOUT` 240 s 대비 실제 기동 시간의 여유.
- 의견: 운용 노드 단계가 더해질 때의 값.

D9. bridge 설정 파일(D4).
- 실측: 지금 `bridge`가 `/clock`을 받는 방식(인자인지 파일인지).
- 의견: 6단계에 설정 파일 생성으로 바꿀지, 표적이 생기는 1b에 할지.
- 충돌 예상: sim(S4).

D10. 진입 스크립트의 소유.
- 의견: 통합 테스트 진입 스크립트를 `tests/` 아래에 둘 때의 소유(지금 `run_smoke.sh`는 devops)와 `stack.sh`의 재사용 범위.

D11. 열린 항목.
- 의견: lint와 unit이 같은 저장소 PR에서 두 번 도는 문제가 `sitl` job에서는 비용이 된다. 6단계에서 정리할지.

## sim-engineer (4문항)

S1. `/clock`의 원천과 RTF.
- 실측: Gazebo 쪽 `/clock`의 발행 주기, `bridge` 뒤의 주기, `bridge`의 CPU. 이 호스트(4 vCPU)에서 headless 스택의 RTF(5분), 운용 노드 하나에 해당하는 부하를 더했을 때, `gz-gui`를 붙였을 때.
- 의견: `/clock` 주기를 낮추는 설정이 있는지와 낮출 때의 부작용.

S2. Lichtblick 실접속(D3).
- 실측: foxglove_bridge를 넣은 ros-ws(devops의 D5가 먼저다)와 `lichtblick` 이미지로 브라우저 접속. px4_msgs 토픽의 스키마가 보이는지, `trajectory_setpoint`와 `vehicle_local_position`을 한 플롯에 놓을 수 있는지.
- 의견: 레이아웃 파일을 저장소에 둘지와 위치.

S3. 육안 확인 절차(D10).
- 실측: 이 호스트에서 `gz-gui`, QGC, Lichtblick을 함께 띄웠을 때의 메모리와 RTF.
- 의견: 사용자가 따라 할 절차의 초안. 화면 도구가 통합 테스트의 판정에 영향을 주지 않는다는 근거.

S4. bridge 설정 파일.
- 의견: 6단계에 파일화하는 것에 대한 입장(1b의 금지 토픽 검사와의 관계). D9와 같은 질문이다.

## logging-engineer (3문항)

L1. ULog의 종료(D11).
- 실측: `compose down` 뒤 `px4-N/log/`의 ULog가 pyulog 등으로 끝까지 읽히는지. 비행 1회의 크기.
- 의견: `sitl` 실패 아티팩트로 올릴 때의 주의.

L2. `sitl` 아티팩트의 MCAP.
- 실측: ros-ws 이미지에 rosbag2의 MCAP 스토리지 플러그인이 있는지.
- 의견: 6단계에서 fixture가 최소 기록을 띄우는 것과 Phase 2까지 미루는 것의 차이. 6단계에 넣을 경우 Phase 2 설계를 묶는 것이 있는지.
- 참고: 범위가 늘어나는 쪽은 사용자 결정 후보다.

L3. `MissionEvent` 발행 쪽 확인.
- 의견: 6단계 구현(RELIABLE, VOLATILE, KEEP_LAST 10, 접수와 종료)에서 Phase 2의 기록기 쪽 순서 결정을 막는 것이 있는지. Executor 쪽 구독자 수 게이트를 6단계에 넣지 말아야 하는지.

## 묻지 않는 담당자

- ops-service-engineer: 질문은 없다. `idsim_mission`의 검증 함수 구조(C29)가 정해지면 구현 검토에서 소비자 관점으로 본다.
- reviewer: `decisions.md` 초안이 나온 뒤 가정의 근거를 검증한다.

## 충돌 예상 지점 요약

| 번호 | 지점 | 관련 질문 |
| --- | --- | --- |
| 1 | setpoint timer와 타임아웃의 시계(ROS 시각 timer인가 wall timer인가)와 `/clock` 지연의 failsafe 여유 | R1, P9, S1 |
| 2 | failsafe 회귀 판정의 주입 방법. 운용 원칙(setpoint는 Executor만, 접근은 `idsim_common`만)과 검증력 | T6, P9, R1 |
| 3 | 식별 불일치와 `/clock` 미수신을 lifecycle 전이로 다룰지 goal 결과로 다룰지, 그리고 healthcheck | R3, R5, P12, D3 |
| 4 | ROS 비의존 핵심을 6단계에 둘지와 취소, 실패 경로의 검증 층 | R9, T5, D7 |
| 5 | 스택을 올리는 주체와 수명, `sitl` job 시간 | T1, D7, D3 |
| 6 | bridge 설정 파일을 6단계에 만들지 | D9, S4 |
