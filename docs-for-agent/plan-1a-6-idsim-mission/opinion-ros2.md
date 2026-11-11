# 1a 6단계 idsim_mission 의견: ros2-engineer

2026-11-11. architect 결정 전 의견이다. 질문마다 권고안 하나와 근거를 적고, 필요하면 대안을 붙인다. 실측은 ros-ws 이미지(`idsim/ros-ws:aptkr`, Jazzy, rmw_cyclonedds_cpp)와 스택 k = 6에서 했고, 이 의견서 말고 저장소 파일은 고치지 않았다. 표기는 1a 5단계와 같다: [실측]은 이번에 직접 확인한 것, [소스]는 설치된 패키지 원문, [추정]은 확인하지 않은 판단이다.

## 실측 요약

| 번호 | 명령(요지) | 결과 |
| --- | --- | --- |
| M1 | ros-ws 컨테이너(`--network none`, 도메인 99)에서 rclpy로 BEST_EFFORT 발행자와 RELIABLE 구독자를 만들고 `Node.count_publishers()`와 `Subscription.get_publisher_count()`를 비교 | QoS가 맞지 않으면 graph 수는 1, 구독의 matched 수는 0, matched event는 0건. QoS가 맞으면 둘 다 1이고 `Publisher.get_subscription_count()`도 1 |
| M2 | `tools/stack.sh up --stack 6`(약 40초에 healthy) 뒤 `docker compose run runner python3 probe.py`. 새 프로세스에서 `use_sim_time` 노드로 `/clock`, `vehicle_status`, `vehicle_local_position`을 구독 | 프로세스 시작부터 `/clock` matched와 첫 수신 0.053 s, `now()`가 0이 아니게 된 시점 0.063 s, `vehicle_status` matched 1.111 s(graph에 보인 시점과 같음), 첫 `vehicle_local_position` 1.136 s, 첫 `vehicle_status` 1.347 s. 받은 표본 timestamp 56004000 us(sim 시간 축), `system_id` 2, `component_id` 1 |
| M3 | 같은 프로세스에서 PX4 토픽을 RELIABLE로 구독 | graph 수 1, matched 0, 수신 없음, rmw 경고 "offering incompatible QoS" |
| M4 | 5초 동안 `/clock` 수신 수와 sim 시간 증가 | `/clock` 250 msg/s(벽시계 기준), RTF 1.0. `/clock` 발행자는 `ros_gz_bridge`, RELIABLE, VOLATILE, KEEP_LAST 10 |
| M5 | 스택 6 내림(`tools/stack.sh down --stack 6`) | 내려감. `idsim-0`은 건드리지 않았다(측정 중에 `idsim-5`도 떠 있었는데 내 것이 아니다) |
| M6 | ros-ws 이미지 위 1회성 컨테이너(기본 bridge 네트워크, root)에 `apt-get install ros-jazzy-foxglove-bridge` | 3.6.0-1noble.20260930.003057. ros-ws 이미지에는 지금 foxglove_bridge가 없다(`dpkg -l`). Dockerfile.ros-ws에도 없다 |
| M7 | 같은 컨테이너에서 foxglove_bridge를 파라미터 없이 띄우고 `ros2 param get` | 기본값: `address` 0.0.0.0, `port` 8765, `capabilities` [clientPublish, connectionGraph, parametersSubscribe, parameters, services, assets], `remote_access` False, `sysinfo` True, `include_hidden` False, `use_sim_time` False, 모든 whitelist `.*`, `best_effort_qos_topic_whitelist` `(?!)`, `min_qos_depth` 1, `max_qos_depth` 25 |
| M8 | `address:=127.0.0.1 port:=8771 topic_whitelist:=[두 정규식] capabilities:=[connectionGraph] client_topic_whitelist/service_whitelist/param_whitelist:=["^$"]` | 로그 "Started server on 127.0.0.1:8771", whitelist에 든 두 토픽만 channel로 광고. websocket client가 없으면 그 토픽에 구독을 만들지 않는다(`ros2 topic info -v`에 bridge 구독자 없음). 그래서 PX4 토픽에 대한 bridge의 실제 구독 QoS는 확인하지 못했다 |
| M9 | Lichtblick 이미지(`ghcr.io/lichtblick-suite/lichtblick:latest`, repo digest sha256:25333a8f57737c8c5866abf75670b8dcf2ed6c2cb5ce3d64f3c63f210a5177e9) inspect | ENTRYPOINT `/bin/sh /entrypoint.sh`(`/lichtblick/default-layout.json`을 읽어 `/src/index.html`을 고쳐 쓴다), CMD `caddy file-server --listen :8080`, WORKDIR `/src`, User 비어 있음(root). 이미지 label의 version v2.5.2는 Caddy의 label이다(`caddy version`이 v2.5.2). Lichtblick 앱 자체의 버전 문자열은 찾지 못했다 |
| M10 | ros-ws 이미지의 launch_ros, rclcpp 원문 | [소스] Jazzy launch_ros에 `ComposableLifecycleNode(autostart=...)`와 `LifecycleNode(autostart=...)`가 있고, autostart는 load 뒤 configure, activate를 한 번씩 보낸다(재시도 없음). 컴포넌트 parameters 파일의 `/**` wildcard를 처리한다. `rclcpp::Clock::wait_until_started(timeout)`, `LifecycleNode::create_timer`(노드 시계 사용)가 있다. 컨테이너 실행 파일은 `component_container`, `_mt`, `_isolated`, `_events_cbg` |
| M11 | rclpy에서 px4_msgs 상수 | `VehicleStatus.MESSAGE_VERSION` 1, `TrajectorySetpoint.MESSAGE_VERSION` 0, `VehicleLocalPosition.MESSAGE_VERSION` 1. 클래스 속성으로 읽힌다 |

M1, M3은 5번 질문의 핵심 근거다. "구독이 발행자와 맺어졌다"는 graph 조회(`count_publishers`, `get_publishers_info_by_topic`)로는 판정할 수 없고 구독 자신의 matched 수(`Subscription.get_publisher_count()`)로만 판정된다.

## 1. idsim_mission 패키지 구조

### 1-1. 언어: C++17

권고: C++17(rclcpp, rclcpp_lifecycle, rclcpp_action, rclcpp_components).

근거
- PX4 토픽 이름, QoS, `Px4Timestamp`, `VehicleCommandBuilder`, 발행 허용 목록이 모두 `idsim_common`(C++) 안에만 있다. Python으로 짜면 이것을 다시 써야 하고, 그러면 토픽 이름과 timestamp 규칙의 두 번째 사본이 생긴다. "토픽 이름은 `idsim_common` 매핑으로만 얻는다"는 규칙을 지킬 길이 C++뿐이다.
- architecture.md가 핵심 노드를 C++로 정했고, Phase 2에서 Collector(C++)와 같은 컴포넌트 컨테이너에 올린다. 컴포넌트는 같은 언어여야 한 프로세스에 들어간다.
- 1b의 상태기 단위 테스트(GoogleTest, ROS 없음)가 같은 코드를 직접 링크한다.

### 1-2. 패키지 안의 나눔

권고: 한 colcon 패키지 `idsim_mission`(ament_cmake) 안에 라이브러리 셋.

| 대상 | 내용 | 의존 | 테스트 |
| --- | --- | --- | --- |
| `idsim_mission_core`(SHARED) | 미션 검증 함수(`validate_mission`, 1a는 TAKEOFF, LOITER, LAND만 허용), 상태기 클래스, 종료 결과 구조체(GoalStatus, `reason`, `items_completed`, `last_item_index`, `detail`) | idsim_interfaces의 C++ 메시지 구조체(rosidl 헤더)만. rclcpp, px4_msgs 없음 | GoogleTest. 노드와 DDS 참가자 없음 |
| `idsim_mission_px4`(SHARED) | PX4 어댑터: px4_msgs -> 상태기 입력 구조체(nav_state, arming_state, failsafe, 위치와 유효 flag, 지상 판정, ack), 상태기 출력 -> `idsim_common` 빌더 호출 | px4_msgs, idsim_common | GoogleTest. 표 대조 |
| `mission_executor_component`(SHARED, 컴포넌트) | lifecycle 노드 껍질: params, 구독과 발행, timer, action 서버, `MissionEvent` | 위 둘, rclcpp_lifecycle, rclcpp_action, rclcpp_components | 통합 테스트가 덮는다 |

- 상태기를 1a부터 ROS 비의존 순수 클래스로 둔다. 1b 1번이 같은 구조를 요구하므로 1a에서 노드 안에 짰다가 1b에서 꺼내는 이중 작업을 피한다. 입력은 "최신 snapshot + 지금 ROS 시각(ns)", 출력은 "이번 tick에 낼 setpoint(없을 수 있음), 보낼 명령 목록, feedback, 종료 결과(있으면)"인 `step()` 하나로 한다. 시계와 입출력은 주입한다.
- 상태기는 PX4 enum 값을 보지 않는다. nav_state, arming_state의 해석은 어댑터 한 곳에 둔다. PX4 태그를 올릴 때 바뀌는 곳이 어댑터뿐이 된다.
- `validate_mission`은 Phase 3에서 Fleet이 같이 쓸 함수(넘김 목록, ops)라 core에 둔다.
- 좌표: 상태기 내부의 setpoint는 기체 로컬 NED(PX4가 소비하는 좌표)로 둔다. 1a에서 ENU가 들어오는 곳은 `YawSetpoint.yaw_rad`(MODE_FIXED) 하나이고 `idsim_common::frames::enu_to_ned_yaw`로 바꾼다. 1b의 GOTO, TRACK_ENTITY는 world ENU -> 로컬 NED 변환(1b `idsim_common`)을 항목 시작 때 한 번 거친다. 변환을 부르는 곳은 어댑터가 아니라 상태기 입력 직전 한 곳으로 한다.
- 실행 파일: `rclcpp_components_register_node(... PLUGIN "idsim_mission::MissionExecutorNode" EXECUTABLE mission_executor)`로 컴포넌트와 단독 실행 파일을 같이 만든다. 단독 실행 파일은 디버깅용이고 compose는 컨테이너를 쓴다(1-4).
- launch 파일 하나 `launch/vehicle_ops.launch.py`(생성하지 않는 정적 파일. 인자는 `namespace`, `params_file`). 3번 참고.

### 1-3. lifecycle 구성

| 전이 | 하는 일 | 실패 조건 |
| --- | --- | --- |
| on_configure | params 읽기와 검증(`vehicle.id`, `vehicle.ns`, `vehicle.sysid`, `command_source.*`), `VehicleNamespace::parse`, `SystemId::make`, `VehicleId`가 ns와 맞는지, 노드 자신의 `get_namespace()`가 `vehicle.ns`와 같은지, `use_sim_time`이 true인지. PX4 구독 넷과 발행 셋(`idsim_common::px4`), `mission_event` 발행자 생성. timer는 만들지 않는다 | 위 검증 하나라도 실패하면 FAILURE(unconfigured로 남는다) |
| on_activate | `get_clock()->wait_until_started(2 s)` 뒤 `Px4Timestamp::now(*get_clock())`가 값을 주는지 확인(1a 4단계 넘김 항목). 기반 클래스 on_activate로 lifecycle publisher 활성화. 20 Hz timer(노드 시계, ROS 시각) 생성. action 서버 생성 | `/clock`이 2 s 안에 오지 않으면 FAILURE |
| on_deactivate | 실행 중인 goal이 있으면 거부(FAILURE). 없으면 action 서버 해제, timer 해제 | goal 실행 중 |
| on_cleanup | 구독, 발행자 해제 | 없음 |
| on_shutdown, on_error | 실행 중인 goal을 ABORTED, `REASON_INTERNAL`로 끝내고 종료 사건을 낸 뒤 해제. setpoint를 끊으므로 그 뒤는 PX4의 Offboard 손실 경로(`COM_OBL_RC_ACT`)가 맡는다 | 없음 |

근거와 세부
- action 서버를 on_activate에서 만들고 on_deactivate에서 해제한다. rclcpp_action 서버는 lifecycle을 모르므로 configure에서 만들면 inactive 상태에서도 goal을 받는다. activate에서 만들면 "client의 `wait_for_server`가 참 = Executor가 active"가 되어 fixture가 따로 상태를 물을 필요가 줄어든다.
- `vehicle_status` 수신과 식별 대조는 activate 조건에 넣지 않는다. 컴포넌트 컨테이너가 isolated(component마다 SingleThreadedExecutor)이면 PX4 구독 callback과 lifecycle 서비스 callback이 같은 thread라 on_activate 안에서 `vehicle_status`를 기다리면 교착이다. `/clock`은 rclcpp의 clock thread(`use_clock_thread` 기본 true)가 받으므로 on_activate 안에서 기다려도 된다[소스]. 또 M2에서 PX4 토픽 discovery가 1.1 s 걸렸으므로 activate를 거기에 묶으면 autostart(재시도 없음)가 흔들린다. 식별 대조는 실행 중 gate(2-1)로 둔다.
- goal 실행 중 deactivate를 거부하는 이유: deactivate는 setpoint를 끊어 failsafe를 부른다. 의도된 정지는 취소(Hold)이고, 프로세스 종료는 on_shutdown 경로다.
- `use_sim_time`이 false이면 configure를 실패시킨다. `Px4Timestamp`가 어차피 막지만 timer와 항목 timeout이 벽시계로 도는 것을 configure에서 바로 드러낸다.

### 1-4. 실행 방식: 기체당 component container 하나

권고: 기체마다 `component_container_isolated` 프로세스 하나(이름 `ops_container`, 네임스페이스 `/px4_N`)에 `MissionExecutorNode`를 `ComposableLifecycleNode(autostart=True)`로 올린다. Phase 2에서 Collector가 같은 컨테이너에 들어온다.

근거
- isolated는 component마다 자기 SingleThreadedExecutor와 thread를 준다. Phase 2에서 Collector의 callback이 Executor의 20 Hz tick을 밀어내지 않는다. 한 component 안에서는 단일 thread라 상태 경합이 없다.
- `component_container_mt` 하나에 둘을 올리면 두 노드가 thread 풀을 나눠 쓰고, callback group을 잘못 두면 경합이 생긴다. 얻는 것이 없다.
- 프로세스와 DDS 참가자가 기체당 하나라 `MaxAutoParticipantIndex` 50의 여유를 덜 쓴다(Phase 3 3대).
- 대안(단독 실행 파일, `main`에서 스스로 configure와 activate): launch가 없어 단순하지만 Phase 2의 같은 컨테이너 요구와 외부 lifecycle 관리를 잃는다. launch autostart가 실패하면 이 대안으로 물러선다.

### 1-5. callback group, executor, timer

- callback group은 MutuallyExclusive 하나(`control`)를 만들어 PX4 구독 넷, 20 Hz timer, action 서버를 모두 넣는다. isolated에서는 어차피 한 thread지만 명시해 두면 executor를 바꿔도 경합이 생기지 않는다. 지금 `idsim_common::px4::create_subscription`은 `SubscriptionOptions`를 받지 않아 group을 지정할 수 없으므로 overload를 더한다(1-7).
- goal 실행용 thread를 따로 만들지 않는다. rclcpp_action 예제는 handle_accepted에서 thread를 띄우지만, 여기서는 handle_accepted가 goal handle을 상태기에 넘기기만 하고 timer tick이 상태기를 진행시킨다. 그러면 상태기의 입력과 출력이 모두 한 thread에서 일어나 결정적이고, 1a 5단계 결정의 "handle_accepted 안의 mutex 판정"은 같은 group 안의 직렬화로 이미 보장된다(mutex는 executor를 바꿀 때를 위한 보험으로 남겨도 된다).
- 구독 callback은 최신 표본과 수신 ROS 시각만 저장한다. 판단은 tick에서 한다.
- timer는 `create_timer`(노드 시계, ROS 시각)로 만든다. `create_wall_timer`를 쓰지 않는다. PX4는 setpoint 손실을 sim 시간으로 판정하므로(`UXRCE_DDS_SYNCT=0`, `COM_OF_LOSS_T`) 발행 주기도 sim 시간이어야 RTF가 1이 아닐 때 손실로 오판되지 않는다. Gazebo가 멈추면 timer도 멈추지만 PX4도 lockstep으로 멈추므로 일관된다.
- tick 한 번의 순서: `Px4Timestamp::now` -> 상태기 `step` -> setpoint stream 중이면 `offboard_control_mode`, `trajectory_setpoint` 발행 -> 보낼 명령이 있으면 `vehicle_command` 발행 -> feedback(전이 때와 2 Hz 이하) -> 종료면 result와 `MissionEvent`. `Px4Timestamp`가 값을 주지 않으면 goal을 ABORTED, `REASON_INTERNAL`로 끝낸다.
- `/clock`은 250 Hz다(M4). rclcpp는 노드마다 clock thread와 `/clock` 구독을 만들므로 component가 늘면 그만큼 구독이 는다. 1a는 하나라 문제없고, Phase 3의 CPU 측정 때 같이 본다.

### 1-6. 상태기 구조와 위치

- 상태(제안): `IDLE` -> `PREPARING`(식별 gate, 준비 대기, setpoint 선행 발행 N회, Offboard 명령, arm 명령) -> `EXECUTING(item i)` -> `WAITING_MODE`(LAND 명령 뒤 지상 판정과 disarm 대기) -> 종료. 취소는 어느 상태에서든 `CANCELING`(지상: disarm 확인, 공중: Hold 확인, 실패 시 Land)으로 간다. feedback의 PHASE_* 넷과 일대일로 맞춘다.
- 위치: 전부 `idsim_mission_core`. PX4 의미(어떤 nav_state가 Offboard인지, Hold인지, 무엇이 "준비됨"인지, ack 결과 해석)는 어댑터가 bool과 작은 enum으로 바꿔 넘긴다.
- 명령은 BEST_EFFORT 토픽으로 나가므로 잃을 수 있다. 상태기는 명령을 "확인될 때까지 주기적으로 다시 보냄"으로 다루고(예: 0.5 s ROS 시각마다, 상한 시간 뒤 실패), 성공 판정은 ack가 아니라 `vehicle_status`(nav_state, arming_state)로 한다. ack는 거부(DENIED, TEMPORARILY_REJECTED 등)를 빨리 알아채는 데만 쓴다. 재송신 주기와 상한은 px4-engineer가 정한다.
- 모드 전환 전 setpoint "최소 10회"는 시간이 아니라 발행 횟수로 센다.
- 종료 결과는 한 함수가 만든 구조체 하나에서 action result와 `MissionEvent` 종료 사건을 둘 다 채운다. "종료 사건 == result"와 "SUCCEEDED/CANCELED이면 REASON_NONE, ABORTED이면 NONE이 아님"을 core 단위 테스트로 묶는다.

### 1-7. idsim_common에 새로 들어갈 것

| 항목 | 내용 | 테스트 |
| --- | --- | --- |
| `VehicleId` | `parse(text)`: 비어 있지 않은 ROS 이름 토큰 하나(`rmw_validate_node_name` 수준의 토큰 검사, "/" 없음). `matches(const VehicleNamespace &)`: ns == "/" + id. 해석하지 않는다(N을 뽑지 않는다) | 다중 토큰("a/b"), 앞 "/", 빈 문자열 거부, 일치와 불일치 |
| vehicle params 해석 | `parse_vehicle_params(id, ns, sysid) -> VehicleParams{VehicleId, VehicleIdentity}` 또는 오류 문자열. 노드에서 선언하는 얇은 함수 `declare_vehicle_params(node)`가 이것을 부른다. key 이름은 `vehicle.id`, `vehicle.ns`, `vehicle.sysid` | 순수 함수만 단위 테스트(노드 생성 없음, 1a 4단계 규칙) |
| `create_subscription`, `create_publisher` overload | `rclcpp::SubscriptionOptions`, `rclcpp::PublisherOptions`를 받는 판. callback group 지정용. 이름과 QoS 고정은 그대로 | 기존 trait 테스트에 컴파일 확인 추가 |
| setpoint 헬퍼 | `offboard_position_mode(Px4Timestamp)`: `position`만 true, 나머지 flag false(1a 4단계 넘김 (2)). `position_setpoint(Px4Timestamp, Eigen::Vector3d ned, double yaw_ned)`: 위치와 yaw가 유한해야 하고(아니면 nullopt), velocity, acceleration, jerk, yawspeed는 NaN | 필드 표 대조, 비유한 거부 |
| 사건 토픽 QoS | `event_pub_qos()`, `event_sub_qos()`: RELIABLE, VOLATILE, KEEP_LAST 10, liveliness Automatic. 1b의 `state_pub_qos()`, `state_sub_qos()`와 같은 파일(`contract_qos.hpp`)에 둔다 | `qos_check_compatible` Ok, BEST_EFFORT 구독 대 이 발행은 Ok지만 계약 위반이라는 주석, TRANSIENT_LOCAL 구독 대 VOLATILE 발행 Error |

넣지 않는 것
- nav_state, arming_state 분류 함수: PX4 의미라 `idsim_mission_px4`(px4-engineer)에 둔다.
- action 이름과 `mission_event` 토픽 이름 조립 함수: Executor 노드가 `/px4_N` 네임스페이스에서 돌고 상수(`Mission::ACTION_NAME`, `MissionEvent::TOPIC_NAME`)를 상대 이름으로 쓰면 조립이 필요 없다. `idsim_common`이 `idsim_interfaces`에 의존하지 않게 유지한다.
- source system/component 값: 값은 params로 받는다(표는 px4-engineer).

### 1-8. 소유 경계 제안

`idsim_mission`의 소유자가 file-ownership.md에 아직 없다. 제안: 노드 껍질(lifecycle, params, action 연결, QoS, launch, callback group)은 ros2-engineer, `idsim_mission_px4` 어댑터와 상태기의 PX4 절차(준비 조건, 모드 확인, 명령 재송신, 착륙 판정, Hold 실험 반영)는 px4-engineer, core의 검증과 종료 결과 구조체는 ros2-engineer, core 단위 테스트의 전이 표는 test-engineer 승인. architect가 정한다.

## 2. action 서버 구현 세부

### 2-1. goal 수락 정책

- `handle_goal`은 항상 `ACCEPT_AND_EXECUTE`. 여기서는 아무것도 판정하지 않는다(거절은 이유를 실을 수 없다).
- `handle_accepted`(control group 안): 먼저 `MissionEvent` ACCEPTED를 낸다. 그 다음 판정 순서: (1) goal의 `vehicle_id` != 자기 `vehicle.id` -> VEHICLE_ID_MISMATCH, (2) `validate_mission` 실패(GOTO, TRACK_ENTITY, RTL 포함) -> INVALID_MISSION, (3) 실행 중인 goal 있음 -> BUSY, (4) 즉시 판정 가능한 미준비 -> NOT_READY. 모두 `abort(result)`와 종료 사건, feedback 0건. 통과하면 상태기에 넘기고 PREPARING.
  - 순서의 이유: 틀린 기체로 온 goal에 BUSY를 주면 Fleet이 다른 기체에 재시도해 설정 오류를 덮는다. 무효 미션도 BUSY보다 먼저여야 재시도가 무의미함을 알린다.
- (4)의 "즉시 판정 가능한 미준비"를 좁게 두자고 제안한다: 식별 대조가 확정적으로 틀림(`vehicle_status`의 sysid 또는 compid 불일치), 또는 `vehicle_status`가 한 번도 오지 않았거나 신선도 임계(ROS 시각, 노드 파라미터)를 넘김. EKF 수렴, 사전 점검 통과처럼 기다리면 풀리는 조건은 PREPARING 안에서 `prepare_timeout`(ROS 시각)까지 기다리고, 넘기면 NOT_READY로 끝낸다. 이 경우 NOT_READY 앞에 PREPARING feedback이 나간다. 이것은 1a 5단계 넘김의 "즉시 abort되는 goal(... NOT_READY)은 feedback이 0건" 문장과 부딪힌다(아래 "부딪히는 지점" A1).
- 식별 gate(1a 4단계 넘김): `vehicle_command`는 식별 대조 Match 뒤에만 낸다. setpoint stream은 gate하지 않는다(px4 조건). 실행 중에 불일치가 보이면 goal을 ABORTED로 끝내야 하는데, 지금 정의에는 맞는 `reason`이 없다(NOT_READY는 항목 시작 전, PRECONDITION_FAILED는 항목 시작 조건이다). 실행 중 불일치는 사실상 설정 오류라 `REASON_INTERNAL`과 `detail`로 끝내기를 제안한다(A2).

### 2-2. 취소

- `handle_cancel`: 실행 중이면 ACCEPT를 돌려주고 상태기에 취소 요청만 표시한다. 실제 처리는 tick에서 한다(PHASE_CANCELING feedback). 끝은 `canceled(result)` 또는 `abort(result)`([실측] 1a 5단계에서 CANCELING 뒤 둘 다 가능).
- 분기(결정 쟁점 9 그대로): 지상 비무장 -> 바로 CANCELED. 지상 무장 -> 강제 아닌 disarm, disarm 확인 뒤 CANCELED. 공중 -> setpoint 유지, Hold 명령, nav_state가 Hold이면 CANCELED, `hold_confirm_timeout` 넘기면 Land 명령과 ABORTED MODE_SWITCH_FAILED, `vehicle_status`가 묵으면 ABORTED LINK_LOST. 지상 무장에서 disarm이 거부되거나 확인되지 않는 분기는 px4 실험 결과로 정한다.
- 제안: LAND 명령을 이미 보낸 뒤(WAITING_MODE)의 취소는 `handle_cancel`에서 REJECT한다. 착륙 중에 Hold로 공중에 다시 세우는 것이 "가장 놀랍지 않은 상태"라는 취소 근거와 맞지 않는다. px4-engineer와 architect의 판단이 필요하다(A3).
- Hold 확인 뒤 CANCELED가 되면 setpoint stream을 멈춘다(Hold는 PX4가 유지한다). stream을 계속 내면 Offboard 재진입 조건이 남는다.

### 2-3. MissionEvent 발행

- 이름: 노드 네임스페이스 `/px4_N` 안의 상대 이름 `MissionEvent::TOPIC_NAME`. 결과는 `/px4_N/mission_event`.
- QoS: `event_pub_qos()`(RELIABLE, VOLATILE, KEEP_LAST 10). lifecycle publisher로 만들고, on_deactivate와 on_shutdown에서 종료 사건을 낸 뒤에 기반 클래스의 비활성화를 부른다(비활성 publisher의 publish는 버려진다).
- `stamp`: `get_clock()->now()`(ROS 시각). activate가 `/clock`을 보장하므로 0이 나가지 않는다. `goal_id`: `goal_handle->get_goal_id()`의 16바이트 그대로.
- 진단: ACCEPTED를 낼 때 `mission_event` 발행자의 `get_subscription_count()`를 debug 로그에 남긴다. 사건 손실이 생겼을 때 discovery 경합인지 가를 근거가 된다(5-3).

### 2-4. action QoS와 이름

- action은 rcl 기본 QoS를 바꾸지 않는다(1a 5단계 결정). 이름은 상대 이름 `Mission::ACTION_NAME` -> `/px4_N/execute_mission`.
- `result_timeout`은 기본값(10 s)을 둔다. rclcpp_action 서버는 노드 시계로 만료를 재므로 `use_sim_time`에서는 sim 시간 10 s다[추정, 원문 확인 필요]. 테스트는 goal 수락 직후 `get_result_async`를 걸어 이 값에 기대지 않는다.

### 2-5. vehicle_id params 대조

- configure: `VehicleId::parse(vehicle.id)`, `VehicleNamespace::parse(vehicle.ns)`, `VehicleId::matches(ns)`, `get_namespace() == vehicle.ns`. 하나라도 틀리면 configure FAILURE.
- goal: 문자열 완전 일치. 정규화(대소문자, 앞뒤 "/")를 하지 않는다. 틀리면 VEHICLE_ID_MISMATCH, `MissionEvent.vehicle_id`는 자기 값, goal에 적힌 값은 `detail`.

### 2-6. use_sim_time

- params 파일의 `/**` 절에 `use_sim_time: true`(컨테이너 노드에도 적용된다). configure에서 확인.
- 모든 시간 비교(항목 timeout, `prepare_timeout`, `hold_confirm_timeout`, 신선도, 재송신 주기)는 `get_clock()->now()` 기준.
- `Px4Timestamp`는 tick마다 새로 만든다. 같은 tick에서 낸 `offboard_control_mode`, `trajectory_setpoint`, `vehicle_command`는 같은 값을 쓴다.

## 3. bridge, params 생성, 네임스페이스, lifecycle 전이

### 3-1. bridge 서비스

지금 생성된 compose의 `bridge`(`parameter_bridge /clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock`)를 그대로 두기를 권한다.

- `[`는 gz -> ROS 한 방향이다. bridge 노드는 `/clock`의 원천이므로 `use_sim_time`을 켜지 않는다(기본 false 그대로).
- 발행 QoS는 RELIABLE, VOLATILE, KEEP_LAST 10이고 250 Hz다(M4). rclcpp TimeSource 구독(ClockQoS, BEST_EFFORT, depth 1)과 맞는다.
- `lazy`는 기본(false)을 유지한다. 구독자가 없을 때도 `/clock`이 나가야 healthcheck와 늦게 붙는 노드가 바로 시계를 얻는다.
- 1b에서 표적 pose를 더할 때는 CLI 인자 대신 생성된 bridge 설정 파일로 옮긴다(이미 progress의 다음 작업 목록에 있다). 1a는 바꾸지 않는다.

### 3-2. 노드 params 파일 생성

권고: 생성기가 기체마다 `artifacts/runs/<id>/params/px4-N.yaml`을 쓴다. 생성하는 값은 식별값뿐이다. 튜닝 값(주기, timeout, 임계)은 생성하지 않고 노드의 선언 기본값에 둔다(두 번째 출처를 만들지 않는다).

```yaml
# 생성 파일. tools/gen_compose.py가 만든다. 값의 출처는 같은 디렉터리의 stack.json이다.
/**:
  ros__parameters:
    use_sim_time: true
    vehicle:
      id: px4_1
      ns: /px4_1
      sysid: 2
    command_source:
      system: <px4-engineer 표>
      component: <px4-engineer 표>
```

- `/**`를 쓰는 이유: 같은 컨테이너의 컨테이너 노드와 Phase 2 Collector가 같은 식별값을 받는다. 선언하지 않은 파라미터는 무시된다.
- `stack.json`의 기체 항목에 `vehicle_id`("px4_1")와 `params_file`(실행 디렉터리 기준 상대 경로)을 더한다. `vehicle_id`는 생성기가 `px4_ns`와 같은 값을 직접 쓴다. 테스트와 스크립트는 계산하지 않고 이 값을 읽는다(architecture.md 기체 식별 절).
- params 파일에 /fmu 문자열이 없다. 생성기도 /fmu 문자열을 쓰지 않는다(foxglove whitelist도 네임스페이스 접두로 한다, 4-2).

### 3-3. 네임스페이스와 remap

- Executor는 네임스페이스 `/px4_N`, 이름 `mission_executor`로 띄운다. lifecycle 서비스는 `/px4_N/mission_executor/change_state`, `get_state`.
- PX4 토픽은 `idsim_common`이 `vehicle.ns`에서 만든 절대 이름이라 노드 네임스페이스와 무관하고 remap하지 않는다. 계약 토픽과 action은 상대 이름이라 네임스페이스만으로 맞는다. 따라서 remap을 하나도 두지 않는다.
- 규칙 제안: launch 파일과 params 파일에 remap을 두지 않는다. `px4-api` lint의 범위(지금 C++과 `.py`)에 `ros_ws/src/**/*.yaml`과 생성기 출력 golden(`tests/fixtures/gen_compose/**/params/*.yaml`)을 더해 /fmu 문자열이 나오면 실패하게 한다(1a 4단계 미해결 항목 "params, remap yaml이 생기면 범위를 다시 본다"의 답).

### 3-4. lifecycle 전이를 거는 주체

권고: launch autostart. fixture와 compose command는 전이를 걸지 않는다.

- compose의 운용 서비스(이름은 devops가 정한다. 제안 `ops-N`, 기체당 하나) command:
  `ros2 launch idsim_mission vehicle_ops.launch.py namespace:=/px4_N params_file:=/opt/idsim/artifacts/runs/<id>/params/px4-N.yaml`
- launch 파일은 `ComposableNodeContainer(executable component_container_isolated, name ops_container, namespace /px4_N, parameters [params_file])`와 `ComposableLifecycleNode(plugin idsim_mission::MissionExecutorNode, name mission_executor, namespace /px4_N, parameters [params_file], autostart True)`만 담는다. 생성하지 않는 정적 파일이다(architecture.md "launch 파일은 생성하지 않는다"와 맞다).
- autostart는 configure, activate를 한 번씩만 보낸다[소스]. activate가 `/clock` 대기(2 s)를 안에 품으므로 bridge healthy 뒤에 뜨는 이 서비스에서는 충분하다. 실패하면 노드가 inactive로 남고 healthcheck가 실패해 `up --wait`가 원인을 드러낸다.
- healthcheck: `ros2 lifecycle get /px4_N/mission_executor --no-daemon`의 출력이 `active`로 시작하는지. bridge처럼 `interval` 30 s, `start_interval` 5 s, `ROS_LOG_DIR=/tmp/hc`. CLI마다 DDS 참가자를 하나 잠깐 만든다(참가자 상한 50 안). 대안은 노드가 activate에서 표시 파일을 쓰는 방식인데 DDS 경로를 확인하지 못하므로 권하지 않는다.
- 서비스 조건: `user` 호스트 uid:gid, 저장소 `/opt/idsim` 마운트(설치된 `ros_ws/install`을 entrypoint가 읽는다), `ROS_LOG_DIR`, `depends_on: bridge healthy`. `tools/stack.sh up`의 install 부재 검사(1a 4단계 넘김)가 이 서비스 때문에 필요해진다.
- fixture는 `up --wait`가 끝난 뒤 이 노드에 전이를 걸지 않는다. 테스트가 active를 다시 확인하려면 `lifecycle_msgs/srv/GetState`를 rclpy로 부른다.

## 4. foxglove_bridge와 Lichtblick

### 4-1. 이미지와 버전

- ros-ws 이미지에 foxglove_bridge가 없다(M6). Dockerfile.ros-ws에 `ros-${ROS_DISTRO}-foxglove-bridge`를 더해야 하고 ros-ws 이미지 key가 바뀐다(devops). 지금 apt의 판은 3.6.0(M6). ROS apt는 옛 판을 남기지 않으므로 버전은 고정할 수 없고, 빌드에서 설치된 판을 `IDSIM_BUILD_FOXGLOVE_BRIDGE` 같은 ENV로 남겨 기록만 하자고 제안한다.
- `foxglove` 서비스도 저장소 마운트가 필요하다. bridge가 `MissionEvent` 같은 idsim 타입의 스키마를 내려면 `ros_ws/install`이 환경에 있어야 한다(entrypoint가 있으면 읽는다).

### 4-2. foxglove 파라미터

생성기가 서비스 command 인자나 params 파일로 넣을 값(M7, M8 근거).

| 파라미터 | 값 | 이유 |
| --- | --- | --- |
| `address` | `127.0.0.1` | 기본이 0.0.0.0이다(M7). 127.0.0.1에서 뜨는 것을 M8에서 확인 |
| `port` | 8765 + k | stack.json `foxglove_port` |
| `capabilities` | `[connectionGraph]` | 기본에 clientPublish, parameters, parametersSubscribe, services, assets가 있다. 빈 목록은 ROS 파라미터 타입을 정하지 못할 수 있어[추정] M8에서 동작을 확인한 한 항목 목록으로 둔다 |
| `client_topic_whitelist`, `service_whitelist`, `param_whitelist` | `["(?!)"]` | capability를 빼도 두 번째 방어선. `(?!)`는 아무것과도 맞지 않는다(bridge 자신의 `best_effort_qos_topic_whitelist` 기본값과 같은 형식) |
| `topic_whitelist` | 기체마다 `^/px4_N/`(stack.json의 ns에서 생성) | 네임스페이스 접두라 /fmu 문자열과 버전 접미사를 생성기에 쓰지 않는다. bridge는 client가 구독하기 전에는 DDS 구독을 만들지 않으므로(M8) 넓은 whitelist의 비용이 없다. `/clock`(250 Hz), `/rosout`, `/parameter_events`는 넣지 않는다. 1b에서 `^/targets/`를 더한다 |
| `include_hidden` | false(기본) | action 내부 토픽 제외 |
| `use_sim_time` | true | 수신 시각이 `/clock` 축이 되어 PX4 timestamp(sim us)와 같은 축에서 본다. "모든 노드가 use_sim_time" 규칙과도 맞다 |
| `remote_access` | false 명시 | 3.6.0에 Foxglove 원격 접속 기능이 있다. 기본이 false지만 판이 바뀌어도 꺼져 있게 명시 |
| `sysinfo` | false | 기본 true(M7). 무엇을 내는지 확인하지 않았고 디버깅에 필요 없다 |
| `asset_uri_allowlist` | `["(?!)"]` | assets capability를 뺐지만 같은 이유의 두 번째 방어선 |

### 4-3. 화이트리스트에 들어가는 토픽(1a에서 실제로 볼 것)

`^/px4_N/` 접두가 덮는 것 중 Offboard 디버깅에 쓰는 것: `fmu/out`의 `vehicle_local_position`, `vehicle_status`, `vehicle_land_detected`, `vehicle_command_ack`, `failsafe_flags`, `fmu/in`의 `trajectory_setpoint`, `offboard_control_mode`, `vehicle_command`, 그리고 `/px4_N/mission_event`. 이 문서에 버전 접미사를 붙인 이름은 적지 않는다.

### 4-4. QoS 문제

- PX4 /fmu/out 발행자는 BEST_EFFORT, TRANSIENT_LOCAL이다. foxglove_bridge는 client가 구독할 때 발행자 QoS를 보고 구독 QoS를 고른다(발행자가 모두 RELIABLE일 때만 RELIABLE, 모두 TRANSIENT_LOCAL이면 TRANSIENT_LOCAL)[추정, 소스 기억. M8에서 client가 없어 확인하지 못했다]. 그렇다면 PX4 토픽에는 BEST_EFFORT로 붙어 문제가 없다. TRANSIENT_LOCAL 구독이 되더라도 BE/TL 발행자와 호환되고, 에이전트가 늦은 TL reader에 이력을 주지 않는다는 1a 4단계 실측대로 현재 값만 받는다.
- 확인 방법(6단계 구현 때): Lichtblick에서 `vehicle_local_position` panel을 연 상태로 `ros2 topic info -v`에 foxglove_bridge 구독이 BEST_EFFORT로 보이는지 본다. RELIABLE로 붙으면 수신이 없고(M3과 같은 현상) 그때는 `best_effort_qos_topic_whitelist`에 `^/px4_N/fmu/`를 넣는다(이 경우만 생성기에 /fmu가 들어가므로 lint 예외로 기록).
- `/fmu/in`의 setpoint는 Executor가 BEST_EFFORT로 내므로 같은 규칙으로 BEST_EFFORT 구독이 된다. bridge가 /fmu/in에 reader로 붙어도 PX4에 영향이 없다(PX4는 그 토픽의 reader일 뿐이다).
- `mission_event`는 RELIABLE 발행이라 RELIABLE로 붙는다. VOLATILE이라 Lichtblick을 연 뒤의 사건만 보인다.

### 4-5. Lichtblick

- 이미지 CMD가 `caddy file-server --listen :8080`이라(M9) host 네트워크에서는 command를 `caddy file-server --listen 127.0.0.1:<18080 + k>`로 덮는다. 포트 매핑이 아니라 listen 주소로 127.0.0.1을 지킨다. entrypoint가 `/src/index.html`을 고쳐 쓰므로 root(이미지 기본)로 두거나 쓰기 가능한 위치를 확인해야 한다. healthcheck는 두지 않는다(viz 프로필).
- digest는 지금 로컬의 sha256:25333a8f...(M9)를 후보로 하되, progress의 "Lichtblick 2.5.2"는 Caddy label을 읽은 것일 가능성이 있다(M9). Lichtblick 판과 서브프로토콜 `foxglove.sdk.v1` 제시 여부를 브라우저 실접속으로 다시 확인해야 architecture.md의 "foxglove_bridge 3.x는 foxglove.sdk.v1만 받고 Lichtblick 2.5는 이를 제시" 문장이 근거를 갖는다(devops, sim).
- 기본 layout(`/lichtblick/default-layout.json`)은 1a에서 넣지 않기를 권한다. layout에는 버전 접미사가 붙은 토픽 경로가 들어가 저장소에 /fmu 문자열이 생긴다. 대신 `tools/stack.sh up --viz`가 접속 URL `http://127.0.0.1:<18080+k>/?ds=foxglove-websocket&ds.url=ws://127.0.0.1:<8765+k>`를 출력하게 한다[추정, URL 형식은 실접속 때 확인].

## 5. 통합 테스트의 rclpy 쪽

### 5-1. 노드와 executor

- 판정 노드 하나, `use_sim_time` true(파라미터 override). `/clock` 기준 타임아웃은 이 노드의 `get_clock().now()`로 잰다. rclpy는 clock thread가 없어 `/clock`(250 Hz) callback도 같은 executor에서 돈다(M4에서 250 msg/s를 문제없이 처리).
- `tests/support/receive.py`의 `SpinThread`(SingleThreadedExecutor, 전용 thread)를 그대로 쓴다. callback은 표본을 lock 아래 deque에 넣기만 하고 판정은 호출 thread가 한다.
- 종료 순서: executor shutdown -> thread join -> 구독과 action client destroy -> node destroy -> `rclpy.shutdown()`. 순서를 어기면 프로세스 끝에서 "terminate called without an active exception"이 난다(M2 probe에서 관찰, 판정에는 영향 없음).
- 벽시계 바깥 가드: `/clock` 기준 타임아웃은 Gazebo가 멈추면 끝나지 않는다. 테스트마다 벽시계 상한(예: sim 타임아웃 x 3, RTF 1.0 실측 기준)을 둔다.

### 5-2. QoS와 이름

- PX4 토픽: `qos_profile_sensor_data`(BEST_EFFORT, VOLATILE, depth 5). `idsim_common::px4::px4_out_qos()`와 reliability, durability가 같다.
- `mission_event`: RELIABLE, VOLATILE, KEEP_LAST 10(계약). BEST_EFFORT로 구독하면 사건을 잃을 수 있다.
- PX4 토픽 이름(1a 4단계 넘김, Python 쪽 규칙): `tests/support`에 `px4_topic(ns, direction, base, msg_cls)` 한 함수를 두고 접미사는 `getattr(msg_cls, "MESSAGE_VERSION", 0)`에서 만든다(M11. C++ 매핑과 같은 규칙). golden `topics.txt`와 양방향 일치를 보는 pytest를 둔다. 테스트 코드에 `vehicle_status_v1` 같은 문자열을 쓰지 않는다. 계약 토픽과 action 이름은 `MissionEvent.TOPIC_NAME`, `Mission.ACTION_NAME`과 `stack.json`의 `vehicle_id`로 만든다.

### 5-3. "구독이 발행자와 맺어진 뒤 goal 전송"의 판정

권고 순서
1. `mission_event` 구독, PX4 구독들, action client를 먼저 만든다.
2. `/clock` 기준 상한 안에서 다음이 모두 참이 될 때까지 기다린다.
   - `mission_event_sub.get_publisher_count() >= 1`. graph 조회(`count_publishers`)를 쓰지 않는다(M1, M3: QoS가 맞지 않아도 graph에는 보인다).
   - `action_client.server_is_ready()`(또는 `wait_for_server`). rmw_cyclonedds의 service 가용 판정은 client 쪽 endpoint의 matched 상태를 본다[추정, rmw 원문 기억]. 서버를 activate에서 만들므로 이것이 참이면 Executor는 active다.
   - `vehicle_status` 구독이 기대 sysid의 표본을 1회 이상 받음. Executor도 PX4 토픽 discovery에 같은 시간(M2: 약 1.1 s)이 걸리므로 이것이 Executor 준비의 간접 근거가 된다(2-1의 PREPARING 대기가 남은 틈을 덮는다).
3. goal을 보내고 수락 응답 직후 `get_result_async`를 건다.
4. 판정: 같은 `goal_id`의 ACCEPTED 사건과 종료 사건이 하나씩, 종료 사건의 `status`, `reason`, `items_completed`, `last_item_index`가 result와 같다. goal의 UUID와 `goal_id`(uint8[16])는 바이트 순서 그대로 비교한다.
5. 계약 QoS 대조: `get_publishers_info_by_topic`으로 Executor의 `mission_event` 발행이 RELIABLE, VOLATILE인지 본다(graph 조회는 QoS 확인에는 맞는 도구다).

남는 위험과 대응
- DDS의 match는 양쪽이 따로 한다. reader 쪽 matched가 1이어도 Executor의 writer가 그 reader를 아직 match하지 않았을 수 있고, 그 사이에 나간 RELIABLE VOLATILE 표본은 그 reader에 가지 않는다. 테스트 쪽에서는 writer 쪽 match를 볼 방법이 없다. 두 쪽의 SEDP는 같은 participant discovery 교환에서 오가고, 위 순서에서는 reader match 뒤에도 action server 준비와 PX4 표본 수신(수백 ms 이상)을 더 기다리므로 실제 틈은 작다고 본다[추정]. ACCEPTED가 빠지고 종료 사건만 온 실패가 나면 Executor의 debug 로그(2-3의 `get_subscription_count()`)로 이 경합인지 가른다. sleep이나 재시도로 덮지 않는다.
- PX4 토픽은 에이전트(Fast DDS)를 거쳐 discovery가 `/clock`보다 20배 느리다(M2: 1.1 s 대 0.05 s). 고정 대기를 두지 말고 위 조건으로 기다린다.
- 같은 도메인에 앞 실행의 죽은 참가자가 lease 만료 전까지 graph와 match에 남을 수 있다[추정]. `stack.sh up`이 down 뒤 약 40 s 걸려 올라오므로(M2) Cyclone 기본 lease보다 길다. CI에서 스택을 연달아 올리는 구성이 생기면 다시 본다.
- 참가자 상한: 판정 프로세스, healthcheck CLI, ops 컨테이너, bridge, foxglove, 에이전트의 참가자(PX4 client마다 하나)가 도메인 하나의 `MaxAutoParticipantIndex` 50을 나눠 쓴다. 1a는 여유가 크다.
- 서로 다른 스택은 도메인으로만 격리된다(측정 중 `idsim-0`, `idsim-5`, `idsim-6`이 동시에 떠 있었고 k = 6 판정 노드는 자기 도메인 26의 토픽만 받았다).

## 다른 담당자와 부딪힐 수 있는 지점

| 번호 | 상대 | 지점 | 내 제안 |
| --- | --- | --- | --- |
| A1 | architect, px4, test | NOT_READY의 시점. 결정은 "즉시 abort, feedback 0건"인데 EKF 수렴과 사전 점검은 기다려야 풀린다 | 즉시 NOT_READY는 식별 불일치와 `vehicle_status` 미수신, 묵음만. 기다리면 풀리는 조건은 PREPARING에서 `prepare_timeout`까지 기다린 뒤 NOT_READY(feedback 있음). 7단계 계약 문장을 그에 맞게 고친다 |
| A2 | architect | 실행 중 식별 불일치의 `reason` 값이 없다 | `REASON_INTERNAL` + `detail`. 새 상수가 필요하면 1a 고정 전에 추가 |
| A3 | px4, architect | LAND 명령 뒤의 취소 | `handle_cancel` REJECT |
| A4 | px4 | 상태기와 어댑터의 소유 경계(1-8), 준비 조건(어떤 필드로 EKF 수렴과 사전 점검을 보나), 명령 재송신 주기와 상한, source system/component 값 | 껍질과 core 골격은 ros2, PX4 절차는 px4 |
| A5 | devops | 운용 서비스 이름과 command(launch), healthcheck CLI, params 파일 위치, stack.json `vehicle_id`와 `params_file`, ros-ws 이미지에 foxglove_bridge 추가와 key 변경, Lichtblick command 덮기와 root 실행, `px4-api` lint 범위 확장(yaml) | 3, 4절 그대로 |
| A6 | test | goal 전송 전 판정을 graph 조회가 아니라 `Subscription.get_publisher_count()`로, Python 토픽 이름 함수를 `tests/support`에, 벽시계 바깥 가드 | 5절 |
| A7 | devops, sim | progress의 "Lichtblick 2.5.2"가 Caddy label일 가능성 | 6단계에서 실접속과 판 확인 |
| A8 | devops | foxglove_bridge 버전 고정 불가 | 설치 판을 ENV로 기록만 |
| A9 | test, px4 | 1a 4단계 넘김의 "sim 시간 timestamp를 `COM_OF_LOSS_T`보다 묵게 보내면 failsafe" 판정은 Executor가 아니라 테스트 하네스가 묵은 setpoint를 직접 내야 한다. 하네스가 /fmu/in에 쓰려면 Python에서 발행 허용 목록을 우회하게 된다 | 이 판정은 별도 테스트 노드(C++, `idsim_common` 사용, `tests/` 아래)로 두거나, Executor에 테스트 전용 파라미터를 두지 않는다는 원칙만 정하고 방식은 test와 px4가 정한다 |

## 이번에 하지 않은 것

- websocket client가 없어 foxglove_bridge의 실제 구독 QoS와 Lichtblick 실접속은 확인하지 못했다(4-4, 4-5).
- `component_container_isolated` + `ComposableLifecycleNode(autostart)` 조합은 원문으로만 확인했다. 시험 컴포넌트로 configure, activate와 `wait_until_started` 동작을 확인하는 것은 구현 첫 작업으로 둔다.
- rclcpp_action 서버의 `result_timeout`이 노드 시계를 쓰는지는 원문을 보지 않았다(2-4).
