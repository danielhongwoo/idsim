# Phase 1a 6번 작업 이륙-호버-착륙 노드와 통합 테스트 계획

작성 2026-11-10, 갱신 2026-11-11, architect. 상태: 설계 토론과 재질문이 끝났고 결정은 같은 디렉터리 `decisions.md`에 있다. 이 문서의 "작업 단위", "PR 분할", "사용자 결정" 절은 `decisions.md`에 맞춰 확정했다. 범위, 넘김 항목 목록, 완료 기준, 리스크 표는 토론 전의 초안 그대로이고, 두 문서가 다르면 `decisions.md`가 우선한다. 담당자 질문지는 `questions.md`, 답은 `opinion-<담당>.md`다. reviewer의 근거 검증(조건부, 필수 6, 권고 7)을 반영했다. 추가 실험 E1-E5의 결과로 취소 분기를 다시 정했다(`decisions.md` 2번과 "추가 실험" 절의 "결과와 처리"). 새 취소 분기에 대한 ops-service-engineer의 검토는 조건부 승인으로 끝났고 조건 셋을 받았다(`decisions.md` "ops의 답과 처리", K13-K18. result 끝에 `end_state` 필드를 더한다). 사용자 결정 9항목은 2026-11-11에 모두 권고안으로 확정됐다. 구현은 아직 시작하지 않았다(아래 "다음 절차").

전제: 5단계 PR #17(`feat/1a-5-idsim-interfaces`)이 main에 합쳐진 뒤에 구현을 시작한다. 설계 토론과 PX4 실험은 그 전에 시작할 수 있다(스택만 쓰고 저장소 코드를 바꾸지 않는다).

읽은 것: `docs/roadmap.md` 1a 6번, 7번과 완료 기준, `docs/architecture.md`, `docs-for-agent/progress.md`(결정 (a), (m), (q)-(x), 5단계 기록, 미해결 사항), `plan-1a-4-idsim-common/decisions.md`와 의견서, `plan-1a-5-idsim-interfaces/decisions.md`(쟁점 1, 8, 9, 넘김 목록).

## 지금 저장소 상태에서 확인한 사실

토론의 출발점이다. 모두 이 브랜치의 파일에서 직접 읽었다.

- `ros_ws/src/`에는 `idsim_common`, `idsim_interfaces`, `idsim_sim`(스크립트와 설정만, colcon 패키지 아님)이 있다. `idsim_mission`은 없다.
- 생성된 compose의 서비스는 `xrce-agent`, `gazebo`, `px4-N`, `bridge`, `runner`(프로필 `tools`), `gz-gui`(프로필 `viz`)다. 운용 노드를 올리는 서비스, `foxglove`, `lichtblick`은 아직 없다. `stack.json`의 `services.foxglove`와 `services.lichtblick`은 null이고 포트 값(`foxglove_port`, `lichtblick_port`)만 있다.
- `stack.json`의 기체 항목에는 `ns`("/px4_1")와 `px4_ns`가 있고 `vehicle_id`는 없다. 노드 params 파일은 생성되지 않는다.
- `docker/Dockerfile.ros-ws`에 foxglove_bridge가 없다. `docs/architecture.md`의 이미지 표는 들어 있다고 적는다. 6단계에서 넣으면 ros-ws 이미지 key가 바뀌어 다시 빌드된다.
- `docker/ros-ws-entrypoint.sh`는 `/opt/idsim/ros_ws/install/setup.bash`가 있으면 읽는다. 프로젝트 패키지는 이미지에 없고 저장소 마운트에서 `tools/ros_ws.sh build`로 빌드한 것을 쓴다.
- `tests/support/receive.py`의 시계는 주입식이고 기본이 벽시계다. `/clock` 시계는 아직 없다. `tests/smoke/check_px4.py`의 명령 source는 254/1이다.
- `runner` 서비스는 ros-ws 이미지이고 스모크에서는 호스트의 `run_smoke.sh`가 스택을 올린 뒤 `compose run`으로 판정만 시킨다. `docs/architecture.md`의 "pytest fixture가 `docker compose up --wait`로 스택을 올린다"와 "pytest는 `ros-ws` 컨테이너 안에서 실행"이 한 프로세스에서 함께 성립하는지는 확인하지 않았다(질문지 T1).
- `config/px4/sitl_params.env`: `COM_OBL_RC_ACT=4`(Land), `COM_OF_LOSS_T=1.0`, `COM_DISARM_PRFLT=-1.0`, `COM_RC_IN_MODE=4`, `UXRCE_DDS_SYNCT=0`. `PX4_SIM_SPEED_FACTOR`는 주지 않는다(주면 rcS가 손실 타임아웃을 덮는다).
- CI workflow는 `lint`, `build`, `unit`뿐이다. `sitl` job은 없다.
- `idsim_mission` 전체의 소유자가 `docs-for-agent/file-ownership.md`에 없다. CLAUDE.md 표는 px4-engineer에게 "`idsim_mission`의 PX4 접점"만 준다. 소유 분할은 아래 "작업 단위 (확정)"에서 정했다.

## 범위

### 6단계가 만드는 것

1. `ros_ws/src/idsim_mission/`(C++17, 새 colcon 패키지). Mission Executor의 뼈대.
   - `ExecuteMission` action 서버. `[TAKEOFF, LOITER, LAND]` 미션을 받는다. 미션 검증, 수락 정책(`ACCEPT_AND_EXECUTE`만, `handle_accepted` 안의 mutex 판정, 받을 수 없으면 사유를 실어 ABORTED), 취소, 실패 사유, feedback.
   - `MissionEvent` 발행(접수와 종료, goal마다 둘).
   - PX4 절차: Offboard 진입(`OffboardControlMode`와 `TrajectorySetpoint` 20 Hz 지속 발행, 모드 전환 전 최소 10회, EKF 수렴 대기 뒤 arm), 고도 도달 판정, LOITER의 setpoint 유지, land 명령과 disarm 확인, 취소 때의 Hold 전환과 그 실패 경로.
   - 식별 게이트(`vehicle_status`와의 대조), goal의 `vehicle_id` 대조.
   - 항목 분류 함수(setpoint 항목과 모드 명령 항목)와 `TYPE_*` 전수 단정 테스트.
   - lifecycle 노드, `use_sim_time`.
   - 단위 테스트(시뮬레이터 없이).
2. `idsim_common` 추가: 네임스페이스와 `vehicle_id`의 대조 함수, `declare_vehicle_identity`, setpoint helper(`Px4Timestamp`만 받고 `offboard_control_mode`는 position만 참).
3. 생성기와 스택: `stack.json` 기체 항목의 `vehicle_id`, 노드 params 파일 생성, 운용 노드 서비스와 healthcheck와 시작 단계, `stack.sh up`의 install 부재 검사, 생성기 golden 갱신, `tests/support/stack.py`의 `vehicle_id` 읽기.
4. 통합 테스트: `/clock` 기준 시계, compose fixture, action client, 판정 코드. "목표 고도 도달", "착륙 후 disarm", `MissionEvent`의 접수와 종료, sim 시간 timestamp 경로의 failsafe 회귀 판정.
5. `viz` 프로필의 `foxglove`와 `lichtblick`, ros-ws 이미지의 foxglove_bridge, Lichtblick browser 실접속 확인.
6. CI의 `sitl` job.
7. PX4 실험과 그 결과의 계약 반영: Hold 취소 실험, 지상 disarm 거부 분기, NAV_LAND 실측 등. 결과는 7단계 전에 `plan-1a-5-idsim-interfaces/decisions.md` 쟁점 9, `ExecuteMission.action` 주석, `docs/architecture.md`의 취소 문장에 반영한다.

### 6단계가 만들지 않는 것

| 항목 | 가는 곳 |
| --- | --- |
| GOTO, TRACK_ENTITY, RTL 항목의 실행(6단계 노드는 INVALID_MISSION으로 끝낸다. 임시 동작이고 계약 문장이 아니다) | 1b |
| YAML 미션 로더, takeoff builder, world ENU <-> 로컬 NED 원점 변환, `state_pub_qos()`, `TargetId` | 1b |
| 상태기 전이 전부를 덮는 단위 테스트(1b 완료 기준). 6단계에서 ROS 비의존 핵심을 어디까지 나눌지는 토론 항목(질문지 R9) | 1b |
| `world.origin` 필수화와 params 전달, 표적 관련 전부 | 1b |
| `docs/interface.md` | 7단계 |
| Telemetry Collector와 `VehicleState` 발행, rosbag2 기록 제어, 기록물 인덱스, `MissionEvent`의 기록기 쪽 순서 | Phase 2 |
| Fleet Manager, proto, `result_timeout` 조정, 취소 뒤 Hold로 남은 기체의 처리 | Phase 3 |
| 강제 시동, 강제 disarm, `raw()` builder, /fmu/in 허용 목록 확대 | 하지 않는다. 필요가 드러나면 결정 (r)의 해제 절차 |

확인이 필요한 경계 둘(토론에서 정한다).

- `docs/architecture.md`의 `sitl` job 설명은 "실패 시 MCAP 기록물과 ULog를 artifact로 업로드"다. MCAP 기록은 Phase 2의 `idsim_logger` 몫이라 6단계에서는 ULog와 컨테이너 로그만 올리는 것이 초안이다. MCAP을 6단계로 당기면 범위가 늘어난다(사용자 결정 후보 4).
- `docs/architecture.md`는 Executor와 Collector를 기체당 컴포넌트 컨테이너 하나에 올린다고 적는다. Collector가 없는 6단계에서 컴포넌트로 만들지 단독 실행 파일로 둘지는 질문지 R2.

## 넘김 항목 전체 목록

처리 시점의 뜻. "6 안": 6단계 PR들 안에서 닫는다. "6 끝": 6단계 마지막(7단계 착수 전)에 닫는다. "7": 7단계 `docs/interface.md`에서 문서로 닫는다. 담당은 초안이다.

### A. 4단계(`plan-1a-4-idsim-common/decisions.md`, 결정 (t), (u))에서 넘어온 것

| 번호 | 항목 | 담당 | 시점 | 질문 |
| --- | --- | --- | --- | --- |
| A1 | params key 이름(`vehicle.ns`, `vehicle.sysid` 제안)과 생성기 출력 | ros2(이름), devops(생성) | 6 안 | R4, D2 |
| A2 | 선언 helper `declare_vehicle_identity(node)` | ros2 | 6 안 | R4 |
| A3 | 식별 게이트 정책. px4 조건: `VehicleCommand`만 막고 setpoint 스트림은 막지 않는다, 미수신이면 명령 보류, 불일치면 activate 실패 또는 ERROR 전이. 게이트는 `idsim_mission`에 둔다 | px4(조건), ros2(구현) | 6 안 | P12, R5 |
| A4 | source_system/component 값 표(역할별. 미션 노드, `tests/support`, `check_px4.py`(지금 254/1), 손으로 보내는 명령) | px4(표), test(하네스 적용) | 6 안, 문서는 7 | P11, T8 |
| A5 | DO_SET_MODE와 SET_NAV_STATE 최종 선택 확인(지금 builder는 DO_SET_MODE) | px4 | 6 안 | P3 |
| A6 | setpoint helper(`Px4Timestamp`만 받는다) | ros2, 접점 px4 | 6 안 | R6 |
| A7 | activate에서 `/clock` 첫 수신 확인(`Px4Timestamp` 생성 실패를 activate 실패로) | ros2 | 6 안 | R3 |
| A8 | sim 시간 timestamp를 `COM_OF_LOSS_T`보다 묵게 보내면 failsafe(`offboard_control_signal_lost`)라는 통합 판정. B안 경로의 회귀 판정이다 | test, px4 | 6 안 | P9, T6 |
| A9 | 시동 상태에서 신호 없는 Offboard 요청의 TEMPORARILY_REJECTED 여부 실측 | px4 | 6 안 | P2 |
| A10 | Python 쪽 토픽 이름 규칙(rclpy `MESSAGE_VERSION` 쌍둥이를 `tests/support`에 둘지, 정규식을 유지할지) | test, 접점 ros2 | 6 안 | T8 |
| A11 | `stack.sh up`의 `ros_ws/install/setup.bash` 부재 검사(자동 빌드는 하지 않는다) | devops | 6 안 | D4 |
| A12 | 판정에서 PX4 timestamp와 `/clock`을 같은 축(us)으로 전제해도 된다. 판정 기준 시각은 ROS 시각이다(규칙) | test | 6 안 | T2 |
| A13 | 컴포넌트 컨테이너 구성(ops-service와 함께) | ros2 | 6 안에 구조만, Collector 합류는 Phase 2 | R2 |
| A14 | `TrajectorySetpoint.yaw`용 ENU <-> NED yaw 변환 | 닫힘(4단계 `ned_to_enu_yaw`, `enu_to_ned_yaw`). 6단계는 쓰기만 한다 | - | - |
| A15 | ccache와 actions/cache(build 단계가 3분을 넘을 때), 노드 이미지 굽기(`ros-app`. 저장소 없는 실행 요구가 생길 때) | devops | `sitl` job 설계에서 다시 본다 | D7 |
| A16 | `docs/interface.md` 전체 | architect, 초안 ros2 | 7 | - |

### B. 4단계 PX4 인터페이스 검토와 미해결 사항("1a 4번 작업에서 올라온 항목")에서 넘어온 것

| 번호 | 항목 | 담당 | 시점 | 질문 |
| --- | --- | --- | --- | --- |
| B1 | NAV_LAND의 공중 착륙 동작과 param 사용 실측 | px4 | 6 안 | P6 |
| B2 | `vehicle_command.hpp` 주석 "`from_external=false`면 MAVLink로 재송출"의 소스 근거 | px4 | 6 안 | P11 |
| B3 | source 값 표에 "source가 (대상 기체 sysid, component 1)이면 안 된다"를 넣는다(PX4 내부 명령의 ack와 `is_ack_for`가 섞인다) | px4 | 6 안 | P11 |
| B4 | `offboard_control_mode`의 attitude, body_rate, direct_actuator flag는 열려 있다. setpoint helper가 position만 참으로 고정한다 | ros2, 접점 px4 | 6 안 | R6 |
| B5 | `/clock` 전달 지연만큼 /fmu/in timestamp가 묵게 보인다. failsafe 판정 여유를 `COM_OF_LOSS_T` 대비로 테스트에서 확인 | px4, ros2, test | 6 안 | P9, R1 |
| B6 | S5에 `vehicle_status.timestamp`와 `/clock`의 차이 상한 판정을 넣을지 | px4, test | 6 안에 결정 | P9 |
| B7 | px4-api 검사는 C++과 `.py`만 본다. params, remap yaml이 생기면 범위를 다시 본다 | devops, 접점 ros2 | 6 안 | D2 |
| B8 | px4-engineer가 안전장치 오류로 반복 중단된다. 6단계 전에 운용 방법을 다시 정한다 | 사용자와 호출하는 쪽 | 6 착수 전 | 사용자 결정 후보 5 |
| B9 | clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다. `tidy` 대상 0개가 PASS-NO-TARGETS다 | ros2, devops | `idsim_mission`이 두 header를 include하면 앞의 것은 닫힌다. 확인만 6 안 | R12 |
| B10 | 4단계 검토 때 PX4 원문 사본이 v1.17.0 태그인지 직접 확인하지 않았다(5단계에서 reviewer가 commit과 blob hash를 대조했다) | px4 | 6단계 답의 [소스]는 사본의 출처와 태그 대조 방법을 적는다 | questions.md 공통 규칙 |

### C. 5단계(`plan-1a-5-idsim-interfaces/decisions.md`)에서 넘어온 것

| 번호 | 항목 | 담당 | 시점 | 질문 |
| --- | --- | --- | --- | --- |
| C1 | Hold 실험: failsafe 진행 중의 Hold 명령 동작 | px4 | 6 안(구현 전) | P4 |
| C2 | Hold 확인 타임아웃 기본값(노드 파라미터, ROS 시각) | px4 | 6 안 | P4 |
| C3 | 지상 취소에서 disarm이 거부되거나 확인되지 않을 때의 분기(아직 landed가 아니면 강제가 아닌 disarm은 거부된다) | px4 | 6 안(구현 전) | P5 |
| C4 | `commander_params`의 배터리, geofence, 바람, 비행 시간 failsafe 기본값 대조("Hold에서 벗어나는 경로"의 범위) | px4 | 6 안 | P10 |
| C5 | takeoff의 `acceptance_m` 기본값([추정] 0.3 m 이상) | px4, test | 6 안 | P7, T3 |
| C6 | Offboard 상승 속도 제한 확인("상승 속도 필드를 두지 않는다"의 근거가 [추정]이다) | px4 | 6 안 | P7 |
| C7 | land 완료 판정(지상 판정 뒤 자동 disarm)과 판정 토픽 | px4 | 6 안 | P6 |
| C8 | 네임스페이스와 `vehicle_id`의 대조 함수(`idsim_common`), 토큰이 둘 이상인 네임스페이스 거부 단위 테스트 | ros2 | 6 안 | R4 |
| C9 | action 서버 구현(`ACCEPT_AND_EXECUTE`만, `handle_accepted` 안의 mutex). 구현 규칙이므로 `.action` 주석이 아니라 Executor 설계 노트에 적는다 | ros2 | 6 안 | R7 |
| C10 | `MissionEvent` 발행(`stamp`는 노드 clock의 ROS 시각. RELIABLE, VOLATILE, 구현 기본 KEEP_LAST 10) | ros2 | 6 안 | R8 |
| C11 | 이름 상수를 namespace 범위 static 초기화식에 쓰지 않는 규칙의 검토 | ros2 | 6 안, 문서는 7 | R11 |
| C12 | `stack.json` 기체 항목과 노드 params에 `vehicle_id`, 생성기 golden 갱신. 스키마의 세부(위치, 이름)는 devops가 확인하고 이견이면 architect에게 | devops | 6 안 | D1 |
| C13 | 통합 테스트가 `MissionEvent`의 접수와 종료 사건을 확인 | test | 6 안 | T4 |
| C14 | 구독을 만들고 발행자와 맺어진 것(발행자 수 1 이상)을 확인한 뒤에 goal 전송. sleep이나 재시도로 대신하지 않는다 | test | 6 안 | T4 |
| C15 | 취소된 기체의 teardown(착륙과 disarm 확인) | test | 6 안 | T7 |
| C16 | fixture의 프로세스 종료 방식(비대화형 bash의 `&` 프로세스는 SIGINT를 무시한다. SIGTERM 또는 `setsid`로 프로세스 그룹) | test | 6 안 | T7 |
| C17 | Hold 실험 결과를 쟁점 9와 `.action` 주석에 반영. 6단계 구현이 드러낸 문제의 계약 반영(1a 고정 전) | architect, px4 | 6 끝 | - |
| C18 | PREPARING 단계의 세부 순서(식별 대조, arm, Offboard 진입) | px4, ros2 | 6 안(구현 전) | P1 |
| C19 | 항목 분류 함수(`idsim_mission`)와 모든 `TYPE_*`가 정확히 한 분류에 속한다는 단정 테스트 | ros2 | 6 안 | R9 |
| C20 | 종료 `MissionEvent`의 `status`, `reason`, `items_completed`, `last_item_index`, `detail`이 GoalStatus, result와 같다는 Executor 단위 테스트 | ros2, 승인 test | 6 안 | R7 |
| C21 | GoalStatus와 `reason`의 대응(SUCCEEDED와 CANCELED는 NONE, ABORTED는 NONE이 아님) 단위 테스트 | ros2, 승인 test | 6 안 | R7 |
| C22 | `last_item_index`의 "시작 전 실패" 구분 필드가 필요한지(필요하면 1a 고정 전에 result 끝에 더한다) | architect(의견 ros2, test) | 6 끝 | R7, T5 |
| C23 | GOTO, TRACK_ENTITY, RTL이 든 미션은 INVALID_MISSION | ros2 | 6 안 | - |
| C24 | 미션 검증 규칙의 구현: `mission_id` 정규식, 항목 1개 이상, `timeout` > 0, 쓰지 않는 서브메시지는 기본값, `LoiterItem.duration`은 0보다 크고 `timeout`보다 짧다, `YawSetpoint.mode`, NaN과 무한대 금지, `height_m`과 `acceptance_m` > 0 | ros2 | 6 안 | R9 |
| C25 | TAKEOFF는 지상에서만 시작, 공중이면 PRECONDITION_FAILED. NOT_READY와 PRECONDITION_FAILED의 경계 | px4(판정 근거), ros2 | 6 안 | P8 |
| C26 | feedback(`phase`, `distance_remaining_m`, 전이 시점과 2 Hz 이하. 주기는 계약이 아니다) | ros2 | 6 안 | - |
| C27 | 취소 의미의 구현: 공중이면 setpoint 유지한 채 Hold 명령, 확인 뒤 CANCELED. 미확인이면 Land 명령 뒤 ABORTED(MODE_SWITCH_FAILED). 상태 미수신이면 ABORTED(LINK_LOST). 지상이면 모드 명령 없이 arm 상태일 때만 비강제 disarm. failsafe 동작 중의 취소는 실험 전 잠정 규칙(Hold 확인 실패와 같은 경로) | px4, ros2 | 6 안(C1-C3 결과 뒤) | P4, P5 |
| C28 | 결정 (m): `stack.json`의 `inputs.cyclonedds_xml` sha256 대조의 소비자에 6단계 통합 테스트가 들어 있다 | test | 6 안 | T11 |
| C29 | 미션 의미 검증 함수를 Executor와 Fleet이 같이 쓰는 구조(`idsim_mission`의 ROS 비의존 라이브러리). Phase 3 항목이지만 패키지 구조를 6단계에서 잡는다 | ros2, 검토 ops | 6 안에 구조만 | R9 |
| C30 | action 서버 `result_timeout`(기본 10 s) 검토는 Phase 3. 6단계 통합 테스트가 결과를 늦게 받아 영향을 받는지만 확인 | test | 6 안 | T4 |
| C31 | `ACCEPT_AND_EXECUTE`만 쓰는 것은 구현 규칙이다(ops 비차단). C9와 같은 곳에 적는다 | ros2 | 6 안 | - |
| C32 | `TYPE_LOITER`(Offboard setpoint 유지)와 `MODE_HOLD`(비행제어의 Hold 모드)의 구분 | 구현 주의 ros2, px4 | 6 안, 문서는 7 | P4 |
| C33 | 7단계 넘김: 계약 문장 전부, 파일별 고정 시점 표, 시각 표기("ROS 시각(`use_sim_time`이면 `/clock`)"), 정의 작성 규칙, 즉시 abort되는 goal의 feedback 0건 | architect | 7 | - |

### D. roadmap 6번, progress.md "다음 작업 5", 열린 항목에서 오는 것

| 번호 | 항목 | 담당 | 시점 | 질문 |
| --- | --- | --- | --- | --- |
| D1 | ros-ws 이미지에 foxglove_bridge 추가(이미지 key 변경) | devops | 6 안(앞쪽) | D5 |
| D2 | `viz` 프로필에 `foxglove`(127.0.0.1, 8765 + k, 토픽 허용 목록, clientPublish, services, parameters 제외)와 `lichtblick`(공식 이미지 digest 고정, 127.0.0.1의 18080 + k). 본 스택 서비스는 `viz`에 `depends_on`하지 않는다 | devops, 접점 sim | 6 안 | D6, S2 |
| D3 | Lichtblick 2.5.2와 foxglove_bridge 3.6.0의 browser 실접속 확인. setpoint와 `vehicle_local_position`을 같은 plot에 | sim, 화면은 사용자 | 6 안 | S2 |
| D4 | 생성기의 ROS params 파일과 bridge 설정 파일 생성(결정 (a)) | devops, 접점 ros2, sim | params는 6 안. bridge 설정 파일은 토론 | D2, D9 |
| D5 | 모든 노드가 `use_sim_time`을 따른다. `bridge`는 `/clock`만 | ros2 | 6 안 | R1 |
| D6 | 운용 노드 서비스의 healthcheck는 lifecycle 노드의 active 상태, 시작 순서는 bridge 다음 | devops, ros2 | 6 안 | D3, R3 |
| D7 | pytest fixture, rclpy(`qos_profile_sensor_data`, 전용 thread executor), `/clock` 기준 타임아웃, 상태 전이는 "최신 상태 N회 연속" | test | 6 안 | T1-T3 |
| D8 | CI `sitl` job(PR과 main 머지, PR당 1회, 재시도는 수동, 15분 이내, 실패 시 artifact) | devops, 접점 test | 6 안(뒤쪽) | D7 |
| D9 | 로컬 headless 3회 연속 통과 | test | 6 끝 | T9 |
| D10 | QGroundControl과 Gazebo GUI로 같은 비행을 눈으로 확인. 3단계의 육안 확인 2건(x500_1, `qgc.sh --stack`)도 함께 | 사용자 | 6 끝 | S3 |
| D11 | ULog가 `compose down`에서 정상 종료되는지 미확인(Phase 2 전 항목). `sitl` artifact에 ULog를 올리면 6단계에서 먼저 걸린다 | logging | 6 안에 확인만 | L1 |
| D12 | `artifacts/`를 CI job artifact로 업로드(가정) | devops | 6 안 | D7 |
| D13 | GHCR 패키지 공개 전환(다음 작업 1, 사용자). `sitl` job이 px4와 sim-base 이미지를 받아야 한다 | 사용자 | `sitl` job 전 | 사용자 결정 후보 1 |
| D14 | `COM_RC_IN_MODE=4`라 QGC는 관찰만 한다(수동 모드 불가) | 문서 | 7 | - |
| D15 | 3단계 결정 (k)의 "S2-S5는 운영 스택과 같은 구성". 운용 노드 서비스가 생기면 스모크가 그것까지 올리는지 정해야 한다 | devops, test | 6 안 | D3 |

## 작업 단위 (확정)

담당과 검토는 `decisions.md`의 결정을 따른다. 사용자 2(상태기를 6단계로 당김)가 권고대로 채택된 경우다. 채택되지 않으면 C를 D에 합친다(소유의 경계는 같다).

| 단위 | 내용 | 담당 | 선행 | 검토 |
| --- | --- | --- | --- | --- |
| Q. 설계 토론 | 끝남. `decisions.md`. reviewer 검증 반영까지 끝남. 남은 것은 추가 실험 결과의 반영과 사용자 결정 | architect | 없음 | reviewer |
| X. PX4 실험 | 첫 실험, 재질문, 추가 실험 E1-E5 모두 끝남(의견서, 재질문 답, 추가 실험 답). 남은 것: `decisions.md`의 "재질문에서 넘어온 미해결"(battery_simulator의 주기 실행 정지 원인 규명, 낮은 `height_m`의 하한, 취소 착륙의 제한 시간 포함) | px4 | 없음 | reviewer(근거), architect(결과의 처리) |
| O. 소유 반영 | `docs-for-agent/file-ownership.md`에 `idsim_mission`의 분할, `tests/sitl/`(`run_sitl.sh`는 devops), `tests/px4_facts/`를 적는다. CLAUDE.md 표는 사용자 9이고 이 단위는 그것을 기다리지 않는다 | architect | Q | ros2, px4, test, devops, reviewer |
| S. 스택 준비 | bridge를 실행 파일 직접 실행으로, xrce-agent에 `init: true`, 생성기 단정("ros-ws 서비스의 command가 `ros2`로 시작하지 않는다")과 golden. ros-ws 이미지에 foxglove_bridge. `versions.env`의 `LICHTBLICK_IMAGE`. `sitl_params.env`의 `SIM_BAT_MIN_PCT`(px4)와 S4 기대값 | devops(`sitl_params.env`는 px4) | Q | sim(bridge), px4, test(스모크), reviewer |
| B. `idsim_common` 추가 | `VehicleId`, `namespace_matches`, `vehicle_params.hpp`의 `declare_vehicle_identity`, `px4_setpoint.hpp`, source 값 상수, `mission_event_qos()`, 공개 header 전부를 include하는 TU(B9), `.clang-tidy`의 `cert-err58-cpp`, 기존 테스트 둘 수정 | ros2 | Q | px4(helper, source 값), devops(`.clang-tidy`), architect |
| A1. 생성기: 식별과 params | `stack.json`의 `vehicle_id`와 `ros_params_file`, params 파일 생성(key `vehicle_id`, `sysid`, `health_marker`, `use_sim_time`, 정확한 FQN), 생성기 단정, golden, `tests/support/stack.py`, `px4-api` 검사 범위에 yaml | devops(`stack.py`는 test) | Q | ros2, test, reviewer |
| C. `idsim_mission` 핵심(ROS 비의존) | C-1 패키지 골격, 미션 검증, 1a 임시 항목 순서 규칙(`[TAKEOFF, LOITER 0개 이상, LAND]`와 `[LAND]`만 실행. 그 밖은 INVALID_MISSION), 항목 분류와 단위 테스트(ros2). C-2 PX4 절차 상태기(PREPARING 두 경로, TAKEOFF, LOITER, LAND, 취소 표, 실행 중 이상)와 입출력 struct, ROS 시각 역행의 처리, 단위 테스트(px4). 취소 분기는 `decisions.md` 2번의 새 표(실행 중인 항목으로 가른다. 관찰 창 없음)와 "ops 검토로 더한 규칙"(끝 상태, CANCELING 중의 이상 판정, 상한, 취소로 끝난 goal의 항목 번호)으로 구현한다. 상태기의 출력 struct에 끝 상태를 둔다 | ros2(C-1), px4(C-2) | B, O | 서로, test, reviewer |
| D. `idsim_mission` 노드 | lifecycle과 자기 전이, action 서버, `MissionEvent`, 식별 게이트, params, 표식 파일, 종료 처리(pre-shutdown callback. 채택안은 [추정]이라 원형으로 먼저 확인한다), ROS 시각 역행 때의 timer 동작 확인, 노드 층 테스트(C20, C21), Executor 설계 노트 | ros2(설계 노트의 PX4 절차 절은 px4) | B, C, H-1 | px4, ops(소비자 관점. 첫 항목 LAND의 시작 조건, Phase 2에 Collector가 합류할 때의 자기 전이와 표식 구조 포함), test, reviewer |
| A2. 생성기: 운용 노드 서비스 | `mission-N`(직접 실행, `init` 없음, tmpfs `uid,gid,mode`, healthcheck find 형태), 넷째 시작 단계, embedded 변형 제외 단정, `stack.sh up`의 install 부재 검사와 실패 로그, 3대 golden. 스모크 S2-S5가 이 단계까지 올린다. S5에 `vehicle_status.timestamp` 판정(px4) | devops(`check_px4.py`는 px4) | A1, D | ros2, test, px4, reviewer |
| E. 통합 테스트 | `tests/support`의 `SimClock`, 판정 함수, `px4_names.py`(구독용과 발행용 함수 분리). `tests/sitl/`의 fixture, action client, 시나리오(PR 넷, 로컬 취소 둘), 판정(고도 `z0`, setpoint z 대조, timestamp 축, `MissionEvent`). `run_sitl.sh`(devops) | test(`run_sitl.sh`는 devops) | A2 | px4, ros2, devops |
| G. `sitl` job | workflow(`pull_request`, main은 `workflow_run`, `workflow_dispatch`), 이미지 정책(ros-ws와 xrce-agent는 job 안 빌드, px4와 sim-base는 실패), 시간 한도 35분과 테스트 단계 15분, 실패 artifact | devops | E | test, reviewer |
| P. PX4 사실 시나리오 | `tests/px4_facts/`(로컬 전용, 별도 스택, 묵은 timestamp 두 경우), `run.sh`, 발행 이름 함수의 호출 위치 검사(`tools/ci/`, devops) | test(검사는 devops) | E | px4, devops |
| F. 시각 도구 | `viz` 프로필의 `foxglove`(허용 목록은 `stack.json`의 네임스페이스마다. PX4 토픽은 `fmu/(in|out)/` 접두사 한 줄)와 `lichtblick`(command 교체, 127.0.0.1), 실접속 확인 절차 | devops(확인 sim, 화면은 사용자) | S, A1 | sim, ros2, reviewer |
| H-1. 계약 정의 변경 | `ExecuteMission.action`의 result 끝에 `END_STATE_*` 상수 셋과 `uint8 end_state`(K13, N5). golden 갱신(`ExecuteMission`의 type hash, 펼친 정의, 직접 정의. msg 쪽은 바뀌지 않아야 한다), 계약 테스트에 `END_STATE_*` 집합 검사. 절차는 `decisions.md`의 "K13의 반영 절차"(5단계 쟁점 10) | architect | Q | ops의 승인이 조건이다(필드의 소비자). test(golden 갱신 절차), ros2, reviewer |
| H-2. 계약 반영 | `decisions.md`의 "5단계 계약에 반영할 변경" 가운데 의미 문장과 주석(K1-K12, K14-K18, N1-N4, N6), `docs/architecture.md`, `docs/roadmap.md`. K3-K5에 대한 ops의 검토는 끝났다(조건부 승인) | architect | D, E, X, H-1 | px4와 ops의 승인이 조건이다(ops는 취소 계약의 소비자다). reviewer |
| V. 검증 | 로컬 3회 연속, CI 통과, 육안 확인 | test, 사용자 | 전부 | reviewer |

`idsim_mission`의 소유 분할(확정. `decisions.md` 4번)
- ros2-engineer: 패키지 골격, 미션 검증, 항목 분류, 노드 전부, 노드 층 테스트, Executor 설계 노트.
- px4-engineer: PX4 절차 상태기와 그 단위 테스트, 상태기의 입출력 struct, 설계 노트의 PX4 절차 절. 패키지 안의 한 디렉터리(`procedure/`. 이름은 골격을 만들 때 ros2가 확정)로 모은다.
- 입출력 struct를 바꾸려면 ros2의 승인이 필요하다. 서로의 영역은 고치지 않고 증상과 증거를 넘긴다.

PR 분할과 순서(확정)

| PR | 내용 | 선행 PR | 비고 |
| --- | --- | --- | --- |
| 0 | O. 소유 반영(`file-ownership.md`) | 없음 | 1-3과 병렬. 4보다 먼저 합친다. 4-8의 검토가 이 파일로 소유를 판정한다 |
| 1 | S. 스택 준비 | 없음 | ros-ws 이미지가 먼저 GHCR에 올라가야 뒤의 unit과 `sitl`이 다시 빌드하지 않는다. `down`이 약 1 s가 되어 뒤의 모든 실측과 테스트가 빨라진다 |
| 2 | B. `idsim_common` 추가 | 없음 | 1과 병렬 |
| 3 | A1. 생성기: 식별과 params | 없음 | 1, 2와 병렬. 서비스는 아직 만들지 않는다(노드가 없다) |
| 3b | H-1. 계약 정의 변경(`idsim_interfaces`의 `end_state`와 golden) | 없음 | 0-3과 병렬. 5보다 먼저 합친다(노드가 result에 값을 채운다). 직접 정의 golden이 바뀌는 계약 변경 PR이다 |
| 4 | C. `idsim_mission` 핵심 | 0, 2 | `tools/ros_ws.sh ci`가 `idsim_mission`의 테스트 1건 이상을 단정한다. 취소 분기는 `decisions.md` 2번의 새 표와 "ops 검토로 더한 규칙"으로 넣는다(ops의 검토에서 분기는 바뀌지 않았다) |
| 5 | D. `idsim_mission` 노드 | 4, 3b | |
| 6 | A2. 생성기: 운용 노드 서비스 | 3, 5 | 스모크 S2-S5 회귀 확인을 이 PR에서 한다 |
| 7 | E, G. 통합 테스트와 `sitl` job | 6 | 이 PR 자신의 `sitl`이 첫 runner 실측이다 |
| 8 | P. PX4 사실 시나리오 | 7 | 작으면 7에 합쳐도 된다 |
| 9 | F. 시각 도구 | 1, 3 | 4-8과 병렬 |
| 10 | H-2. 계약 반영 문서 | 7 | 7단계 착수 전. px4와 ops의 승인이 조건 |

순서: (0, 1, 2, 3, 3b 병렬) -> 4 -> 5 -> 6 -> 7 -> 8 -> 10 -> V. 9는 1과 3 뒤 아무 때나. 0은 4보다, 3b는 5보다 먼저 합친다.

`progress.md`는 호출한 쪽이 갱신한다.

## 완료 기준 초안

roadmap의 기준(바꾸지 않는다).

- 이륙-호버-착륙 통합 테스트가 headless로 로컬에서 3회 연속 통과한다.
- CI의 `sitl` job에서 통과한다.
- QGroundControl과 Gazebo GUI로 같은 비행을 눈으로 확인한다(사용자).

roadmap 6번 본문에서 나오는 기준.

- 통합 테스트가 `[TAKEOFF, LOITER, LAND]` 미션을 `ExecuteMission` action으로 보내고 결과 SUCCEEDED, `reason` NONE을 받는다.
- "목표 고도 도달"과 "착륙 후 disarm"을 `/clock` 기준 타임아웃으로, 상태 전이를 "최신 상태 N회 연속"으로 판정한다. 벽시계 대기와 재시도로 덮지 않는다.
- `MissionEvent`의 접수와 종료 사건을 받고, 구독이 발행자와 맺어진 것을 확인한 뒤에 goal을 보낸다.
- GOTO, TRACK_ENTITY, RTL이 든 미션은 ABORTED, INVALID_MISSION이다.
- goal의 `vehicle_id`가 다르면 ABORTED, VEHICLE_ID_MISMATCH다. 실행 중의 둘째 goal은 ABORTED, BUSY이고 첫 goal에 영향이 없다.
- `--profile viz`에서 Lichtblick이 `foxglove`에 접속해 setpoint와 `vehicle_local_position`을 같은 plot에 보인다. `foxglove`는 읽기 전용이다.

넘김 항목에서 나오는 기준.

- X의 실험 결과가 [실측]과 [소스]로 `decisions.md`에 있고, 취소의 분기와 지상 disarm 분기가 잠정이 아니다(C1-C3, C17).
- sim 시간 timestamp 경로의 failsafe 회귀 판정이 통합 테스트에 있다(A8).
- source 값 표가 정해져 미션 노드, 테스트 하네스, `check_px4.py`가 그 값을 쓴다(A4, B3).
- 단위 테스트: 분류 함수의 `TYPE_*` 전수 단정(C19), 종료 `MissionEvent`와 result의 일치(C20), GoalStatus와 `reason`의 대응(C21), `vehicle_id` 대조 함수의 다중 토큰 거부(C8), 검증 규칙(C24).
- 1a 노드는 `[TAKEOFF, LOITER 0개 이상, LAND]`와 `[LAND]`만 실행하고 그 밖의 항목 순서는 ABORTED, INVALID_MISSION이다(임시 규칙. 단위 테스트).
- 취소 경로(LOITER 중 Hold, TAKEOFF와 LAND 중 착륙으로 끝냄, 지상 disarm)의 검증이 있다. SITL로 할지 단위 테스트로 할지는 T5.
- result의 `end_state`: 정상 비행의 SUCCEEDED는 `END_STATE_GROUND_DISARMED`다(통합 테스트). CANCELED는 취소 표의 줄마다 정해진 값이고 0이 아니다(단위 테스트). 계약 테스트의 `END_STATE_*` 집합 검사와 갱신된 golden이 통과한다.
- 취소 처리 중의 이상 판정(LINK_LOST, FAILSAFE, EXTERNAL_MODE_CHANGE), 취소 요청부터 result까지의 상한, 취소로 끝난 goal의 `last_item_index`와 `items_completed`가 단위 테스트로 묶여 있다.
- 생성기 golden 4종과 `tests/support/test_stack.py`가 `vehicle_id`를 포함해 통과한다. 기체 식별자가 `config/fleet.yaml`과 생성기 밖에서 하드코딩되지 않는다(노드, 테스트, params 원본 어디에도 `px4_1` 리터럴이 없다. golden과 fixture 입력은 예외).
- `tools/ros_ws.sh ci`와 `tools/ci/lint.sh all`이 통과한다. `idsim_mission`은 `idsim_common` 밖에서 /fmu 토픽 문자열을 쓰지 않는다(`px4-api`).
- 스모크 S2-S5가 회귀 없이 통과한다(S4 `--check` 일치).
- 3대 fleet golden(`3대-k0`)에서 운용 노드 서비스와 params가 기체 수만큼 생성된다(Phase 3 재사용 검사. 실행은 하지 않는다).

## 검토 체크리스트(architect가 각 PR에서 본다)

- 새 토픽, action, 파라미터가 `idsim_interfaces`와 7단계 문서 대상 목록에 있는가. 6단계에서 계약에 없는 토픽을 새로 만들지 않는다.
- `idsim_mission`이 Gazebo, PX4 버전 문자열, compose 서비스 이름, 컨테이너 경로를 알지 않는가. 노드가 읽는 것은 params와 ROS 토픽뿐이다.
- 통합 테스트의 판정이 토픽에서만 읽는가(`docker exec`, pxh, 로그 grep으로 판정하지 않는다. 진단 수집은 예외).
- N+1 같은 파생을 노드와 테스트가 다시 계산하지 않는가.
- `sitl_params.env`의 값(`COM_OBL_RC_ACT`, `COM_OF_LOSS_T`)을 노드가 리터럴로 품지 않는가.

## 리스크

| 리스크 | 영향 | 대응 초안 |
| --- | --- | --- |
| 호스트 4 vCPU, 7GB RAM | 스택(Gazebo, PX4, 에이전트, bridge)과 colcon build, pytest를 함께 돌리면 메모리가 모자라거나 RTF가 떨어져 `up --wait`의 벽시계 제한에 걸린다 | 빌드와 스택 가동을 겹치지 않는다. RTF와 메모리 실측을 먼저 한다(D4, S1). 판정은 `/clock` 기준이라 RTF 저하 자체는 판정을 바꾸지 않아야 한다 |
| `/clock` 전달 주기와 지연 | ROS 시각 timer의 해상도와 /fmu/in timestamp의 묵음이 여기에 묶인다. 20 Hz가 흔들리면 Offboard 진입 실패나 가짜 failsafe | 실측(R1, S1)으로 timer의 시계를 정한다 |
| Hold 실험이 취소 계약을 바꾼다 | `ExecuteMission`의 의미 변경. 상수 추가는 가능하지만 필드 추가는 직접 정의 golden을 바꾼다 | 구현 전에 X를 먼저 한다. 고정 전이므로 "첫 소비자의 구현에서 드러난 문제"로 변경 가능. 실제로 생겼다: 취소의 끝 상태가 둘로 갈려 result 끝에 `end_state`를 더한다(작업 단위 H-1) |
| px4-engineer의 반복 중단(B8) | X와 C의 PX4 절차가 멈춘다. 6단계에서 PX4 판단이 가장 많다 | 사용자 결정 후보 5. 실험을 작은 단위로 나누고 결과를 그때그때 파일로 남기게 한다 |
| 테스트 사이의 상태 누출 | 앞 테스트가 arm, 공중, failsafe Land 상태를 남기면 뒤 테스트가 흔들린다 | 시나리오별 스택 재기동과 공유 스택의 비용을 실측해 정한다(T1). teardown에서 착륙과 disarm을 확인(C15) |
| failsafe 회귀 판정의 주입 방법 | 묵은 timestamp를 보내려면 Executor 밖에서 /fmu/in에 쓰거나 Executor에 시험용 경로를 넣어야 한다. 앞의 것은 "setpoint는 Executor만, 접근은 `idsim_common`만"과, 뒤의 것은 운용 노드의 단순함과 부딪친다 | T6에서 방법별 실측 뒤 결정 |
| `sitl` job의 시간과 이미지 | px4 3.07GB, sim-base 2.98GB, ros-ws 1.99GB를 매번 받는다. GHCR가 비공개이면 포크 PR은 받지 못한다. job 안에서 colcon build도 한다 | D7 실측. GHCR 공개(D13) |
| ros-ws 이미지 재빌드 | foxglove_bridge 추가로 key가 바뀌고 크기가 는다. 4단계에서 같은 일이 예상보다 컸다(297MB 예상, 410MB 실측) | 크기를 먼저 실측(D5). 앞쪽 PR로 분리 |
| lifecycle active를 healthcheck로 쓰는 것 | 식별 불일치나 `/clock` 미수신이 activate 실패가 되면 `up --wait`가 실패한다. 원하는 동작일 수 있지만 원인 보고가 필요하다 | R3, R5, D3 |
| 운용 노드 서비스가 스모크에 끼어든다(D15) | S4 golden(토픽 목록)에 Executor의 토픽이 섞일 수 있다 | D3에서 스모크 범위를 정한다 |
| 배터리 등 Hold 중 failsafe | 반복 실행이나 긴 Hold에서 SITL 배터리 소모로 failsafe가 걸릴 수 있다([추정]) | P10 |
| SITL battery_simulator의 주기 실행 정지 | `battery_unhealthy`로 arm 거부(NOT_READY, ARM_REJECTED) 또는 arm 직후 failsafe disarm. 추가 실험 중 7회([실측]), 원인 미확인. `sitl`의 플래키 원인 후보 | px4가 원인 규명. test는 판정 실패 때 원인을 따로 적고, devops는 실패 artifact의 ULog로 구분되게 한다(`decisions.md` 미해결 표) |
| 컨테이너 사이의 action(서비스) 디스커버리 | 토픽은 확인됐지만 action의 서비스 다섯 개가 `runner`와 운용 노드 서비스 사이에서 맺어지는지는 실측이 없다 | R10 |

## 사용자 결정 항목

최종 목록은 `decisions.md`의 "사용자 결정 항목 (최종 9개)"다. 올리는 것은 호출한 쪽이다. 토론 전 후보 8개의 처리:

| 토론 전 후보 | 처리 |
| --- | --- |
| 1 GHCR 공개 전환 | 닫힘. 이미 익명으로 조회된다([실측] devops). 사실만 알린다 |
| 2 `sitl` job의 runner 시간, 3 반복 횟수와 시나리오 범위 | 최종 1 |
| 4 실패 artifact의 MCAP | 최종 3 |
| 5 px4-engineer 운용 방법(B8) | 이번 토론에서는 다루지 않았다. 호출한 쪽과 사용자의 몫으로 남는다 |
| 6 ros-ws 이미지 크기 | 최종 4 |
| 7 취소 정책 변경 | 최종 5(바뀌는 것 여섯. 추가 실험 뒤 다시 썼다: 취소를 실행 중인 항목으로 가른다. ops 조건부 승인, result에 `end_state` 필드 추가로 golden이 바뀐다) |
| 8 육안 확인 장소 | 최종 6 |
| (새) 상태기를 6단계로 당김 | 최종 2 |
| (새) `sitl`을 필수 검사로 | 최종 7 |
| (새) `tests/px4_facts/`의 nightly | 최종 8 |
| (새) CLAUDE.md 담당자 표의 `idsim_mission` 소유 | 최종 9 |

최종 목록 1-9와 권고(2026-11-11. 문안과 이유의 정본은 `decisions.md`)

결정 결과(2026-11-11, 사용자): 아래 1-9 모두 권고안으로 확정.

| 번호 | 항목 | 권고 |
| --- | --- | --- |
| 1 | `sitl` job의 시나리오 범위와 시간 | (가) PR마다 넷, 1회. 취소와 failsafe는 단위 테스트와 로컬. 한도는 테스트 단계 15분, job 35분 |
| 2 | ROS 비의존 상태기를 6단계로 당긴다 | (가) 구조와 TAKEOFF, LOITER, LAND, 취소만 당긴다 |
| 3 | `sitl` 실패 artifact의 MCAP | (가) Phase 2로 미룬다 |
| 4 | ros-ws 이미지에 foxglove_bridge | (가) 넣는다(49.6 MB 증가) |
| 5 | 취소 정책의 변경(ops 조건부 승인, result에 `end_state` 필드 추가로 golden 변경) | 여섯 다 채택, (5)는 (가) 실행 중인 항목으로 가른다. `end_state`는 어느 선택에서도 넣는다 |
| 6 | 육안 확인의 장소 | (가) 호스트 화면 세션, 안 되면 (다) 나눠서 |
| 7 | `sitl`을 필수 검사로 둔다 | (가) 6단계에서는 두지 않고 1a 완료 때 실행 기록으로 다시 올린다 |
| 8 | `tests/px4_facts/`의 nightly | (가) 로컬 전용 |
| 9 | CLAUDE.md 담당자 표의 `idsim_mission` 소유 | (가) 표를 고친다(ros2와 px4로 분할) |

## 다음 절차

1. 추가 실험 E1-E5는 끝났고 취소 분기와 K3-K5, 사용자 5를 다시 정했다. ops-service-engineer의 검토도 끝났다(조건부 승인. 조건은 `decisions.md`의 K13-K18로 받았다).
2. (완료 2026-11-11) 사용자 결정 9항목 모두 권고안 (가)로 확정. 9에 따라 CLAUDE.md 담당자 표를 고쳤다.
3. 구현은 위 PR 순서를 따른다. 첫 순서는 PR 0(작업 단위 O, `file-ownership.md`)과 PR 1, 2, 3, 3b(병렬)다. 구현 전에 px4-engineer에게 미해결 셋(battery_simulator 원인, 낮은 `height_m` 하한, 취소 착륙 제한 시간)을, test와 devops에게 battery_simulator 대응을 보낸다(작업 단위 E 전까지). 설계 토론과 계약 변경이 아닌 정형 작업은 CLAUDE.md의 모델 선택 규칙대로 내려 호출한다.
