# 1a 6번 작업 ros2-engineer 의견서

작성 2026-11-10, ros2-engineer. 질문지 `questions.md`의 ros2-engineer 절(R1-R14)에 답한다.

## 실험 조건(모든 [실측]에 공통)

- 이미지 `idsim/ros-ws:local`(Jazzy, rclcpp 28.1.22, rclcpp_action/rclcpp_lifecycle 28.1.22, rmw_cyclonedds_cpp 2.2.4, cyclonedds 0.10.5).
- 탐침 패키지 `probe6`(C++ lifecycle Executor 흉내, timer 탐침, 가짜 `/clock` 발행기, rclpy action client)와 저장소 `idsim_common`, `idsim_interfaces`의 사본을 scratchpad의 별도 작업공간에서만 빌드했다. 저장소 `ros_ws`는 빌드하지 않았다.
- "격리 조건"은 `tools/ros_ws.sh`와 같은 `docker run --network none -e CYCLONEDDS_URI= -e ROS_DOMAIN_ID=99`다. "컨테이너 사이 조건"은 `--network host`, `ROS_DOMAIN_ID=98`(스택 범위 20-29 밖), `CYCLONEDDS_URI`=저장소 `config/cyclonedds.xml` 사본이고 컨테이너를 따로 띄웠다.
- 가짜 `/clock`은 보낼 때의 CLOCK_MONOTONIC 값을 그대로 싣는다(RTF 1). 그래서 "관측 시각 - 값"이 발행에서 관측까지의 지연이다. 컨테이너들은 같은 호스트의 CLOCK_MONOTONIC을 본다.
- 스택 실측은 k=2 한 번(run id `20261110-145422-k2`, standalone, 1대, GUI 없음)이고 측정이 끝나자 바로 내렸다.
- 함께 떠 있던 것: 다른 담당자의 스택 `idsim-1`, `idsim-5`(각 1대, 하나는 foxglove_bridge 포함)와 그들의 빌드, 탐침. load average는 측정 동안 6-19였다(4 vCPU). 이 의견서의 "유휴 상태" 측정은 하지 못했다. 모든 시간 분포는 이 부하 상태의 값이다.

## R1. `/clock`과 timer의 시계

[실측] 스택 k=2에서 bridge를 거친 `/clock`(1000회 timer 동안 약 12400개 수신, 2회 반복은 clock thread 켬/끔 동시 실행):
- `/clock` 값 간격은 p50 4.00 ms, p99 4.00 ms, 최대 12.00 ms다. 발행은 sim 4 ms마다(250 Hz)이고 가끔 1-2개가 빠진다(BEST_EFFORT).
- 벽시계 기준 도착 간격은 p50 4.00 ms, p99 8.3 ms, 최대 16.1 ms다. 같은 구간의 RTF는 0.991이다.
- `use_sim_time` 노드의 ROS 시각 50 ms timer(1000회): ROS 시각 간격은 48 ms와 52 ms가 번갈아 나온다(p50 48, p99 52, 최대 56 ms). 50 ms가 4 ms의 배수가 아니라서 `/clock` 단위로 양자화되고 평균은 50 ms다. 벽시계 간격은 p50 50.4 ms, p99 61.9 ms, 최대 69.2 ms다.
- 같은 노드의 wall timer 50 ms: p50 50.0 ms, p99 51.7 ms, 최대 53.0 ms.
- 노드 자신의 `/clock` 구독 도착에서 `now()` 반영까지: p50 0.07 ms, p99 1.5 ms, 최대 6.1 ms. Gazebo 발행에서 노드 도착까지의 구간은 이 측정에 들어 있지 않다.

[실측] 격리 조건, 가짜 `/clock` 250 Hz, 1000회, clock thread 켬/끔 동시 실행:
- 발행에서 `now()` 반영까지: p50 0.23 ms, p99 1.5 ms, 최대 5.9 ms(켬). 끔도 p99 1.5 ms, 최대 4.0 ms로 차이가 없다.
- ROS 시각 timer의 벽시계 간격: p50 50.2 ms, p99 52.7 ms, 최대 56.6 ms. wall timer는 p99 50.8 ms.
- clock thread 옵션(`NodeOptions::use_clock_thread`, Jazzy 기본 true)은 executor가 막히지 않을 때 timer 분포를 바꾸지 않는다. 차이는 executor가 막힐 때 생긴다(R3의 실측: 끄면 전이 callback 안의 대기에서 `/clock`이 갱신되지 않는다).

[실측] `/clock`이 멈출 때(가짜 `/clock`을 5 s 멈춘 뒤 재개, clock thread 켬/끔 각 1회):
- ROS 시각 timer는 멈춘 동안 한 번도 발화하지 않는다(벽시계 최대 간격 5012 ms). 재개 뒤 밀린 발화를 몰아서 하지 않는다(재개 직후 5 ms 안의 연속 발화 0건).
- wall timer는 계속 발화하고 그동안 `now()`는 같은 값을 돌려준다(99회 연속 같은 값).
- `/clock`이 처음부터 없으면 ROS 시각 timer는 약 180 s 동안 한 번도 발화하지 않았다(첫 시도에서 가짜 발행기가 파라미터 형 오류로 죽은 실행. 같은 시간 wall timer는 3614회).

의견:
- 20 Hz setpoint timer는 ROS 시각 timer로 한다. 근거: [실측] `/clock`이 멈추면 발행도 멈추므로 묵은 timestamp(같은 값 반복)를 보내는 경로가 생기지 않는다. wall timer로 하면 멈춘 동안 같은 `Px4Timestamp`를 20 Hz로 계속 보낸다. 그것이 PX4에서 어떻게 판정되는지는 P9의 몫이다. [추정] Gazebo 정지(RTF 0)에서는 PX4 hrt도 함께 멈추므로 ROS 시각 timer가 같이 멈추는 것이 맞는 동작이다.
- [실측] ROS 시각 timer의 실제 간격은 48/52 ms 교대이고 벽시계 최대 69 ms(부하 상태)다. `COM_OF_LOSS_T=1.0`(sim 시간) 대비 여유는 크다. 다만 PX4가 보는 신선도의 끝단 지연(Gazebo -> bridge -> 노드 -> 에이전트 -> PX4)은 이 측정에 없고 P9가 잰다.
- 항목 `timeout`과 Hold 확인 시간은 ROS 시각으로 잰다(계약대로). 판정은 setpoint timer의 tick 안에서 `now()`와 시작 시각을 비교하는 방식으로 하고, 따로 일회성 timer를 두지 않는다. [실측] `/clock`이 멈추면 tick이 멈추므로 timeout도 같이 멈춘다. 이것은 원하는 동작이다(sim이 멈추면 비행도 멈춘다).
- `/clock` 정지 자체의 감지는 벽시계가 필요하다. 의견: 1 Hz wall timer 하나가 "ROS 시각이 N초(벽시계) 동안 늘지 않음"을 경고 로그로만 남긴다. goal 결과를 바꾸지 않는다(정지가 풀리면 비행이 이어지므로). [추정] N은 5 s.
- 충돌 예상 1에 대해: 내 영역의 근거는 "timer를 ROS 시각으로 두면 `/clock` 경로가 멈출 때 setpoint가 0건이 된다, wall로 두면 같은 timestamp가 반복된다"까지다. 어느 쪽이 PX4에서 더 빨리, 확실히 failsafe가 되는지는 PX4 쪽 사실이다.

## R2. 노드 구조

[실측] 격리 조건, 실제 `ExecuteMission`, 한 프로세스 gtest(3회 같은 결과):
- 생성자에서 만든 action 서버는 lifecycle 상태와 무관하게 동작한다. unconfigured와 inactive에서도 `handle_goal`이 불리고 goal이 수락된다. 거기서 무엇을 할지는 노드 코드의 몫이다(탐침은 `handle_accepted`에서 NOT_READY로 abort했고 클라이언트는 ABORTED, reason 4를 받았다).
- 실행 중인 goal은 deactivate로 멈추지 않는다. timer도 lifecycle이 관리하지 않으므로 계속 돌고, 탐침의 goal은 deactivate 뒤에도 SUCCEEDED로 끝났다.
- `LifecycleNode::create_publisher`는 `LifecyclePublisher`를 준다. inactive와 unconfigured에서 `publish`는 버려진다. inactive에서 NOT_READY로 끝낸 goal의 접수와 종료 `MissionEvent` 2건, deactivate 뒤 끝난 goal의 종료 `MissionEvent` 1건이 구독자에 오지 않았다(수신 7건 중 inactive 시점 것은 0건).

[실측] executor 구성(격리 조건, 가짜 `/clock`, 3 s 미션, 각 1회):
- 단일 thread executor에서 미션 진행을 20 Hz timer의 tick으로 돌리면 timer 간격 p50 49.9 ms, p99 55.2 ms, 최대 61 ms이고 feedback 6건이 왔다.
- 같은 구성에서 `handle_accepted` 안에서 미션을 끝까지 돌리면(흔한 예제 방식) timer가 3020 ms 동안 막혔고 feedback은 0건이었다. setpoint 스트림이 이만큼 멈추면 `COM_OF_LOSS_T` 1 s를 넘는다.

의견:
- 구성: `SingleThreadedExecutor` 하나, callback group 기본 하나, 미션 실행은 20 Hz ROS 시각 timer의 tick이 상태기를 한 걸음씩 진행한다. action callback(`handle_goal`, `handle_cancel`, `handle_accepted`)은 짧게 판정하고 상태만 바꾼다. 실행용 thread와 mutex 경합을 만들지 않는다. [실측] 위의 tick 방식이 timer를 막지 않는다.
- 단일 thread에서도 `handle_accepted`의 mutex는 남긴다(계약된 구현 규칙이고, 뒤에 executor가 바뀌어도 BUSY 판정이 깨지지 않게).
- `MissionEvent`는 `LifecyclePublisher`가 아닌 일반 publisher로 만든다(`rclcpp::create_publisher(node->get_node_parameters_interface(), node->get_node_topics_interface(), ...)` 형태. [추정] 이 호출 형태는 탐침에서 쓰지 않았다). 근거: [실측] lifecycle publisher는 inactive에서 사건을 버려 "goal마다 접수와 종료 둘"이 깨진다. setpoint publisher(/fmu/in)는 `idsim_common::px4::create_publisher`를 쓰고, inactive에서 발행 자체를 하지 않으므로 어느 쪽이든 같다.
- action 서버는 on_configure에서 만들고 on_cleanup에서 없앤다. inactive에서 온 goal은 수락 뒤 NOT_READY다(일반 publisher라 사건도 남는다).
- 실행 중 deactivate: on_deactivate가 goal이 있으면 FAILURE를 돌려 active에 머문다(운용 경로가 아니다). 종료 신호(SIGINT/SIGTERM의 shutdown 전이)는 거부할 수 없으므로 실행 중 goal을 ABORTED, `REASON_INTERNAL`로 끝내고 종료 사건을 낸 뒤 setpoint를 멈춘다. 그 뒤의 기체 동작은 PX4 failsafe(`COM_OBL_RC_ACT`)다. [추정] 이것이 "종료 사건 없이 접수만 남는" 경우를 SIGKILL로 좁힌다.
- 컴포넌트냐 단독 실행 파일이냐: 6단계는 `rclcpp_components`로 등록하는 컴포넌트 클래스로 만들고, 실행은 그 클래스를 직접 쓰는 작은 `main`(단독 실행 파일) 하나로 한다. 근거: [추정] 컴포넌트 등록은 클래스 생성자 시그니처(`NodeOptions`)만 요구하므로 비용이 거의 없고, Phase 2에서 Collector가 합류할 때 실행 파일만 `component_container`로 바꾸면 된다. 6단계에 `component_container`를 쓰면 lifecycle 전이를 누가 걸지(R3)가 컨테이너 밖으로 나가야 해서 지금 이득이 없다.
- Phase 2에서 바뀌는 것: Executor와 Collector가 한 프로세스(참가자 1개, R13)에 들어가고 executor를 공유한다. Collector 쪽 callback이 Executor의 tick을 막지 않도록 그때 callback group을 나누고 `MultiThreadedExecutor`로 갈지 다시 잰다. 전이를 거는 주체도 컨테이너 단위로 다시 정한다.

## R3. activate 조건과 active 판정

[실측] 격리 조건, lifecycle 노드 하나, 가짜 `/clock`은 activate 요청 2 s 뒤에 시작(방식별 1회):
- (가) 실패로 돌려주고 다시 시도: `/clock` 전 activate는 `Px4Timestamp::now`가 nullopt라 FAILURE로 inactive에 돌아갔다. `/clock` 시작 뒤 다시 시도한 activate는 성공했다.
- (나) 전이 callback 안에서 최대 5 s 기다리기, clock thread 켬(기본): 858 ms 대기 뒤 성공. 그동안 executor가 막힌다(같은 노드의 서비스, action, timer 모두).
- (다) (나)와 같은데 clock thread 끔: 5002 ms 동안 `/clock`이 반영되지 않아 실패했다. executor가 막혀 `/clock` 구독도 처리되지 않기 때문이다.
- `ros2 lifecycle get` 한 번의 벽시계 시간: daemon이 떠 있을 때 1.32-1.79 s(15회), `--no-daemon`이면 2.03-2.07 s(3회). `ros2 lifecycle set`은 1.34-2.36 s.
- DDS 참가자(유니캐스트 포트 쌍으로 셌다): 노드 하나는 참가자 1개(포트 2개). CLI 실행 중에는 CLI 참가자 1개가 더해지고, daemon을 쓰는 첫 CLI 호출이 `ros2-daemon`을 띄워 그 뒤로 참가자 1개가 계속 남았다.

의견:
- activate 조건은 둘이다. (1) `Px4Timestamp::now(*get_clock())` 성공, (2) `vehicle_status` 수신과 `verify` Match(R5). 둘 다 전이 callback 안에서 기다리지 않고 즉시 판정해 FAILURE를 돌려준다(방식 가). 근거: [실측] 기다리는 방식은 executor를 막고 clock thread 설정에 따라 결과가 바뀐다.
- 전이를 거는 주체: 노드 실행 파일 자신이다. `main`이 configure를 한 번 걸고, 벽시계 1 s 주기의 wall timer가 inactive인 동안 activate를 다시 시도하며 실패 이유를 로그로 남긴다(같은 이유는 반복하지 않는다). active가 되면 timer를 멈춘다. 근거: launch 파일을 만들지 않는다는 전제에서 compose 서비스 하나로 닫히고, `/clock`이 늦는 것은 정상 기동 경로라 재시도가 필요하다. [추정] 자기 timer callback 안에서 `activate()`를 부르는 것은 같은 thread의 동기 호출이라 문제가 없다(탐침에서는 다른 thread에서 부른 경우만 확인했다).
- 시험과 수동 조작을 위해 외부의 `ros2 lifecycle set`도 그대로 쓸 수 있다(자동 시도와 겹쳐도 전이 하나는 실패로 끝날 뿐이다. [추정]).
- healthcheck 초안: `ros2 lifecycle get --no-daemon /<ns>/mission_executor`의 출력이 `active`로 시작하는지 본다. 노드 이름은 생성기가 stack.json에서 넣는다. `--no-daemon`을 꼭 붙인다. 근거: [실측] daemon을 쓰면 참가자가 1개 계속 남고, 컨테이너 밖에서도 같은 도메인의 CLI가 그 daemon을 공유한다([추정] host 네트워크에서 daemon은 127.0.0.1의 도메인별 포트로 열린다).
- 비용: [실측] 1회 약 2 s(부하 상태)다. healthcheck 주기는 devops가 정하되 `interval`은 10 s 이상, `timeout`은 5 s 이상을 권한다. 더 싼 대안은 노드가 active 진입과 이탈 때 파일 표식(예: `/tmp/idsim-active`)을 쓰고 healthcheck가 `test -f`만 하는 것이다. 표식 방식은 참가자와 CPU를 쓰지 않지만 노드가 죽어도 파일이 남는다(노드가 PID 1이면 컨테이너도 끝나므로 문제가 없다. [추정]). 충돌 예상 3, D3에서 devops와 정할 지점이다.

## R4. 식별 파라미터와 이름

[실측] 격리 조건. 노드를 `-r __ns:=/px4_1`로 띄우고 상대 이름 `Mission.ACTION_NAME`, `MissionEvent.TOPIC_NAME`을 쓰고, 같은 네임스페이스에 `ros2 topic pub /px4_1/fmu/out/vehicle_status_v1`, `/px4_1/fmu/in/trajectory_setpoint`를 함께 띄웠다(1회).
- `ros2 action list -t`: `/px4_1/execute_mission [idsim_interfaces/action/ExecuteMission]`.
- `ros2 topic list`: `/px4_1/fmu/in/trajectory_setpoint`, `/px4_1/fmu/out/vehicle_status_v1`, `/px4_1/mission_event`, `/px4_1/mission_executor/transition_event`과 전역 `/clock`, `/parameter_events`, `/rosout`. 서비스는 `/px4_1/mission_executor/{change_state, get_state, ...}`.
- 이름 충돌은 없다. PX4 토픽은 `fmu/` 아래이고 Executor의 이름은 그 밖이다. `idsim_common::px4::topic_name`은 절대 이름을 만들므로 노드 네임스페이스와 무관하다([소스] 저장소 `px4_io.hpp`, `detail::topic_name`).

의견:
- params key는 `vehicle.ns`(예 "/px4_1")와 `vehicle.sysid`(정수) 둘만 둔다. `vehicle_id`는 params로 받지 않고 `vehicle.ns`에서 파생한다. 근거: 계약상 `vehicle_id`는 토픽 네임스페이스와 같은 값이다(`MissionEvent.msg` 주석). 셋째 값을 받으면 셋이 서로 어긋나는 경우가 생긴다. `stack.json`의 `vehicle_id`(C12)는 테스트와 생성기 소비자용으로 두되, 생성기가 같은 원천에서 쓴다.
- 대조 함수(`idsim_common/vehicle.hpp`에 추가):
  - `class VehicleId { static std::optional<VehicleId> from_namespace(const VehicleNamespace & ns, std::string * error = nullptr); const std::string & str() const; }`. 토큰이 정확히 하나("/a"는 되고 "/a/b"는 안 된다)일 때만 성공하고 값은 앞 빗금을 뺀 것이다. C8의 다중 토큰 거부 단위 테스트가 여기에 붙는다.
  - `bool matches(const VehicleId & id, std::string_view goal_vehicle_id)`. 정확한 문자열 비교다. 대소문자나 빗금을 정규화하지 않는다.
- 선언 helper: `template <class NodeT> std::optional<VehicleIdentity> declare_vehicle_identity(NodeT & node, std::string * error = nullptr)`. `vehicle.ns`, `vehicle.sysid`를 기본값 없이 선언하고(없으면 실패), parse와 make를 거치며, 노드의 `get_namespace()`가 `vehicle.ns`와 같은지 본다. `VehicleIdentity`에 `VehicleId id`를 더한다.
- 노드 네임스페이스와 params가 어긋나면 on_configure의 FAILURE다(설정 오류라 재시도로 풀리지 않는다). 그러면 노드는 unconfigured에 머물고 healthcheck가 실패하며 로그에 두 값이 남는다. 노드 네임스페이스를 params에서 바꾸지 않는다(compose의 `__ns`와 params가 같은 stack.json에서 나오므로 어긋남은 생성기 버그다).

## R5. 식별 게이트의 위치

의견(근거는 R2, R3의 [실측]):
- `vehicle_status` 미수신: activate 시점이면 activate FAILURE(재시도 대상, R3의 자동 재시도). active 뒤에 끊기면 lifecycle 전이를 하지 않고 goal 쪽에서 다룬다. 실행 중이면 계약의 LINK_LOST, 접수 시점이면 NOT_READY다. 근거: 미수신은 일시적일 수 있고, lifecycle 전이로 다루면 실행 중 goal과 setpoint를 전이 callback에서 정리해야 해 R2의 "deactivate가 goal을 멈추지 않는다"는 문제가 그대로 들어온다.
- 불일치(system_id, component_id): activate 시점이면 activate FAILURE이고, 재시도는 계속하되 로그는 ERROR 수준으로 남긴다. 설정 오류이므로 healthcheck가 실패해 `up --wait`가 멈추는 것이 맞다. active 뒤에 불일치가 보이면(PX4 재기동 등. [추정] 정상 경로에서는 생기지 않는다) 실행 중 goal을 ABORTED, `REASON_INTERNAL`로 끝내고 `VehicleCommand` 발행을 막은 뒤 자기 자신을 deactivate한다. ERROR 전이(on_error)는 쓰지 않는다. 근거: [추정] ERROR 뒤 복구 경로(on_error에서 unconfigured로)는 다시 configure가 필요해 자동 재시도 loop가 복잡해지고, 얻는 것이 없다.
- px4 조건(A3: `VehicleCommand`만 막고 setpoint 스트림은 막지 않는다)과의 관계: inactive에서는 setpoint 스트림 자체가 없다(goal이 없으므로). active 뒤 불일치에서 setpoint를 멈추면 failsafe가 되므로, 이 경우에만 px4 조건과 부딪친다. px4의 답(P12)을 따른다.
- `up --wait`의 원인 보고: activate 실패 이유를 노드 로그 한 줄로 남기면 `stack.sh up`의 실패 보고가 그 줄을 찾을 수 있다. 줄 모양은 devops와 맞춘다(D3).

## R6. setpoint helper

의견. API 초안(`idsim_common/px4_setpoint.hpp`):

```cpp
namespace idsim_common::px4
{
struct PositionSetpoint
{
  px4_msgs::msg::OffboardControlMode mode;   // position만 true, timestamp는 ts
  px4_msgs::msg::TrajectorySetpoint trajectory;  // position만 값, 나머지 NaN, timestamp는 ts
};

// position_ned: PX4 로컬 NED(m). yaw_ned: rad, nullopt이면 NaN(PX4 쪽 의미는 px4가 확인).
PositionSetpoint make_position_setpoint(
  const Px4Timestamp & ts, const Eigen::Vector3d & position_ned, std::optional<double> yaw_ned);
}
```

- 입력은 로컬 NED다. 근거: PX4로 나가는 마지막 단계라 변환을 여기서 하지 않으면 "어느 좌표인지"가 타입 하나로 고정된다. ENU 입력은 호출자가 `enu_to_ned`, `enu_to_ned_yaw`(4단계에 있다)로 바꾼다.
- 두 메시지가 같은 `Px4Timestamp`를 쓰고, timestamp를 다른 방법으로 넣을 길을 주지 않는다(결정 B안의 유지).
- `offboard_control_mode`는 position만 true로 고정하고 attitude, body_rate, direct_actuator 등을 열지 않는다(B4). velocity, acceleration, jerk, yawspeed는 NaN이다. 입력의 NaN과 무한대는 거부(nullopt 반환 또는 assert)한다. 단위 테스트가 flag 전부와 NaN 필드를 단정한다.
- 1b의 world ENU -> 로컬 NED 원점 변환은 이 helper 앞단의 별도 함수다(`frames.hpp`에 들어갈 예정). helper의 시그니처는 1b에서 바뀌지 않는다.
- `idsim_common`에 두는 근거: (1) /fmu/in 발행 규칙(QoS, 이름, timestamp, flag)을 한 곳에 모은다는 4단계 결정과 같은 선. (2) 1b의 TRACK_ENTITY와 GOTO, 그리고 다른 Executor 계열 코드가 같은 함수를 쓴다. (3) 노드 없이 단위 테스트할 수 있다. `idsim_mission`에 두면 flag 고정이 리뷰에만 기대게 되고, 1b에서 다른 패키지가 생기면 옮겨야 한다.

## R7. action 서버와 단위 테스트

[실측] 격리 조건(`tools/ros_ws.sh test`와 같은 `--network none`, `CYCLONEDDS_URI=`, 도메인 99), 실제 `idsim_interfaces/action/ExecuteMission`, 서버와 클라이언트를 한 프로세스의 한 executor에 둔 gtest, 3회 실행(colcon test가 아니라 같은 조건에서 gtest 바이너리를 직접 실행):
- 실행 중 goal이 있을 때 둘째 goal(같은 `vehicle_id`)은 ABORTED, `REASON_BUSY`, 셋째(`px4_2`)는 ABORTED, `REASON_VEHICLE_ID_MISMATCH`다. 첫 goal은 SUCCEEDED다. 5단계의 흉내 action 결과와 같다.
- 3회 모두 통과. 테스트 본체 2.30-2.43 s(미션 1 s 포함), 컨테이너 기동까지 포함 3.76-3.86 s. `wait_for_action_server`는 0 ms였다(같은 프로세스).
- 이 조건에서 CycloneDDS는 "lo is not multicast-capable" 경고를 내고 동작한다.

의견:
- 시뮬레이터 없이 고정할 범위: 수락 정책(BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION, inactive의 NOT_READY), GoalStatus와 `reason`의 대응(C21), 종료 `MissionEvent`와 result의 필드 일치(C20), 접수와 종료 사건이 goal마다 하나씩, 취소 분기(공중 Hold 확인, Hold 미확인 뒤 Land와 MODE_SWITCH_FAILED, 상태 미수신 LINK_LOST, 지상 disarm), 항목 timeout. 취소 분기를 단위 테스트로 덮으려면 R9의 ROS 비의존 상태기가 필요하다.
- PX4 대신: 두 층으로 한다. (1) 상태기 층: PX4 관측(`vehicle_status`, `vehicle_local_position`, `vehicle_land_detected`, `vehicle_command_ack`)을 struct 값으로 주고 출력(setpoint, 명령)을 단정한다. DDS 없음. (2) 노드 층(위 gtest 형태): 같은 프로세스에서 가짜 `/clock`과 가짜 /fmu/out 발행자를 두고 action 경로만 본다. /fmu/out 가짜 발행은 시험 코드가 `idsim_common::px4::topic_name`으로 이름을 얻는다.
- 노드 층 테스트는 가짜 `/clock`을 시험 쪽에서 직접 밀어 시간을 진행시키는 방식이 좋다(벽시계 대기 없이 timeout 분기를 결정적으로). [실측] 가짜 `/clock`으로 activate와 미션 진행이 동작했다.
- `last_item_index` 구분 필드(C22): 구현에서는 필요 없다. 구분이 필요한 경우("항목 시작 전 실패")는 `reason`이 INVALID_MISSION, VEHICLE_ID_MISMATCH, BUSY, NOT_READY인 것과 같다. 근거: 계약상 NOT_READY는 "항목을 시작하기 전", PRECONDITION_FAILED는 "항목을 시작할 때"이므로 `reason`만으로 갈린다. 다만 실행 중의 ARM_REJECTED, MODE_SWITCH_FAILED가 PREPARING(항목 0 전)에서 났는지 항목 0에서 났는지는 `reason`만으로 갈리지 않는다. 이것을 Fleet이 구분해야 하는지는 ops와 architect의 판단이다.

## R8. `MissionEvent` 발행

[실측] 위 gtest(3회): `ServerGoalHandle::get_goal_id()`(16바이트 배열)를 `std::copy`로 `goal_id`(uint8[16])에 옮긴 값이 클라이언트 goal handle의 UUID와 같고, `/px4_1/execute_mission/_action/status`의 `goal_info.goal_id.uuid`와도 같다(첫 goal의 사건 2건, status 항목 8건 일치).

의견:
- 사건 토픽 QoS 함수는 `idsim_common/qos.hpp`에 `mission_event_qos()`(RELIABLE, VOLATILE, KEEP_LAST 10)로 둔다. 1b의 `state_pub_qos()`, `state_sub_qos()`와 같은 파일, 같은 네임스페이스(`idsim_common`, `px4` 아님)에 둔다. 사건은 "놓치면 안 되는 드문 메시지"이고 상태는 "최신만 중요한 주기 메시지"라 QoS가 다르므로 함수를 합치지 않는다. 구독 쪽(테스트, Phase 2 기록기)도 같은 함수를 쓴다.
- 순서: `handle_accepted` 진입에서 mutex를 잡은 뒤 접수 사건을 내고, 그 다음 판정(inactive, 불일치, BUSY, 검증)과 abort, 종료 사건 순서다. [실측] 탐침이 이 순서로 동작했고 수신 순서도 접수 -> 종료였다. mutex 밖에서 접수 사건을 내면 두 goal이 동시에 들어올 때 사건 순서와 판정 순서가 달라질 수 있다([추정]. 단일 thread executor에서는 생기지 않는다).
- `stamp`는 노드 clock의 `now()`다. 발행 직전에 한 번 읽는다.

## R9. 패키지 구조

의견: 6단계부터 `idsim_mission` 안에 ROS 비의존 라이브러리(가칭 `idsim_mission_core`)를 둔다. 담는 것: 미션 검증(C24), 항목 분류(C19), 항목 실행과 취소의 상태기(tick 입력: ROS 시각 ns, 최신 PX4 관측 struct, 취소 요청. 출력: setpoint 목표, 보낼 명령, 종료 판정과 `reason`). 의존은 `idsim_interfaces`와 `px4_msgs`의 C++ struct, `idsim_common`의 ROS 비의존 부분(frames, vehicle)까지이고 rclcpp를 쓰지 않는다.

- 근거 1([실측] R2): 노드는 어차피 tick 기반 상태기여야 한다(callback 안에서 돌리면 timer가 3 s 막힌다). 상태기를 노드 클래스 안에 두느냐 밖에 두느냐의 차이일 뿐 코드 양은 거의 같다.
- 근거 2: 안에 두면 취소와 실패 분기의 검증이 SITL(T5) 또는 R7의 노드 층(DDS, 가짜 `/clock`)으로만 가능하다. 밖에 두면 분기마다 struct 입력 몇 개로 결정적인 단위 테스트가 된다.
- 1b에서 다시 쓰는 양: 밖에 두면 1b는 GOTO, TRACK_ENTITY, RTL 상태를 더하고 전이 전부의 테스트를 늘린다. 안에 두면 1b 1번에서 노드에서 떼어 내는 작업과 그 회귀 검증이 추가된다.
- 범위가 늘어나는 것: 상태기 입력과 출력 struct의 설계가 6단계로 당겨진다. 이 struct가 1b에서 바뀌는 것은 내부 API라 계약 변경이 아니다.
- C29(Fleet과 공유하는 검증 함수): 검증 함수는 위 라이브러리의 별도 header로 두고 상태기와 섞지 않는다. Fleet이 C++이 아니면 공유 방식이 달라지므로 ops의 언어 결정 뒤에 정한다.

## R10. 컨테이너 사이의 action

[실측] 컨테이너 사이 조건. 서버 컨테이너(lc 탐침 Executor, 가짜 `/clock`, `/px4_1` 네임스페이스)와 클라이언트 컨테이너(rclpy `ActionClient`, `MultiThreadedExecutor` 별도 thread, `use_sim_time` true)를 따로 띄웠다(각 경우 1회).
- goal, feedback, result: 수락, feedback 2건(PHASE_EXECUTING), result SUCCEEDED, reason 0.
- cancel: cancel 응답 `return_code` 0(ERROR_NONE), result CANCELED.
- `wait_for_server`는 0.00 s에 참이 됐다(rclpy 노드 생성과 executor thread 시작 뒤에 부른 경우). 클라이언트 프로세스 전체(컨테이너 기동 포함, 15 s와 3 s 대기 포함)는 19.96 s였다. 컨테이너 기동에서 첫 `wait_for_server` 성공까지는 따로 재지 않았다.
- `use_sim_time` rclpy 노드: `wait_for_server` 직후 `get_clock().now()`가 이미 가짜 `/clock` 값이었다.
- `result_timeout`: goal이 끝난 뒤 벽시계 15 s를 기다리고 결과를 요청하면 status 0(UNKNOWN)이 왔다(결과가 지워졌다). 같은 실험을 서버의 `/clock`이 goal 종료 약 3 s 뒤에 멈추게 해 다시 하면 벽시계 15 s 뒤에도 SUCCEEDED가 왔다. 따라서 `result_timeout` 10 s는 서버 노드 clock의 ROS 시각으로 잰다(각 1회라 강한 결론은 아니다).

의견:
- 컨테이너 사이에서 action의 서비스 셋과 토픽 둘은 문제없이 맺어진다(같은 `cyclonedds.xml`, host 네트워크). 리스크 표의 해당 행은 닫아도 된다.
- 통합 테스트는 goal 수락 직후 `get_result_async`를 먼저 걸어 두고 기다린다. 그러면 `result_timeout`과 무관하다. [실측] 결과를 늦게 요청하면 UNKNOWN을 받는다.
- 판정 시간은 ROS 시각인데 `result_timeout`도 ROS 시각이라 RTF 저하에 같이 늘어난다. 테스트에 유리하다.

## R11. 이름 상수와 검사 범위

[실측] 격리 조건. namespace 범위 `const std::string kAction = Mission::ACTION_NAME;`과 `MissionEvent::TOPIC_NAME`을 쓰는 TU에 저장소 `.clang-tidy`를 돌리면 아무것도 잡지 않는다. `cppcoreguidelines-interfaces-global-init`, `bugprone-dynamic-static-initializers`도 잡지 않는다. `cert-err58-cpp`와 `fuchsia-statically-constructed-objects`는 두 줄을 모두 잡는다. 저장소 `idsim_common/src/*.cpp` 다섯 개는 이 두 검사에서 경고 0건이다.

의견:
- 규칙은 "namespace 범위와 클래스 static의 동적 초기화 객체를 두지 않는다"로 넓혀 기계적으로 막는다. `.clang-tidy`에 `cert-err58-cpp`를 더하는 안이 가장 작다(`std::string` 같은 throw 가능한 정적 초기화 전부를 잡는다). 이름 상수만 골라 잡는 검사는 찾지 못했다. `.clang-tidy`의 소유자(devops)와 정한다.
- 이름 상수는 함수 안에서만 쓴다(`create_server(..., Mission::ACTION_NAME, ...)`처럼 호출 시점). Executor 설계 노트에 적는다.
- params yaml이 생길 때 `px4-api` 검사가 볼 것: 생성기가 만든 params 파일과 저장소의 params 원본(있다면)에 `/fmu/` 또는 `fmu/(in|out)/` 문자열이 없어야 한다. remap으로 PX4 토픽 이름을 바꾸는 경로를 막기 위해서다. 6단계 노드는 PX4 토픽 이름을 params로 받지 않는다. 예외는 foxglove 허용 목록(R14)이고, 그것은 읽기 전용 필터라 생성기 한 곳에서만 만들고 검사에서 그 파일만 뺀다.

## R12. clang-tidy 범위

[실측] 격리 조건. `idsim_common` 사본의 `px4_io.hpp`에 일부러 `int x;`(cppcoreguidelines-init-variables 위반)를 넣고 설치한 뒤, 그 header를 include하는 소비자 패키지 소스에 저장소 `.clang-tidy`로 clang-tidy를 돌렸다.
- header의 위반은 보고되지 않았다. 소비자의 compile_commands에서 `idsim_common` header 경로는 `-isystem /opt/idsim/ros_ws/install/idsim_common/include/idsim_common`이다.
- `-header-filter='.*'`로 넓혀도 0건이다. `-system-headers`를 더하면 그때서야 `install/.../px4_io.hpp:97`로 보고된다.
- 따라서 원인은 둘이다. (1) 설치 경로가 `HeaderFilterRegex`(`.*/ros_ws/src/idsim_[a-z_]+/include/.*`)에 맞지 않는다. (2) ament의 export가 `-isystem`이라 시스템 header로 취급된다. `--symlink-install`로는 (2)가 풀리지 않는다([추정]. 경로 표기만 바뀐다).
- 결론: "`idsim_mission`이 두 header를 include하면 B9가 닫힌다"는 성립하지 않는다.

의견:
- `idsim_common` 안에 두 header(와 공개 header 전부)를 include하는 TU를 하나 둔다(예: `src/public_headers.cpp`, 라이브러리에 포함). 자기 패키지의 TU는 `BUILD_INTERFACE`의 `-I .../src/idsim_common/include`로 header를 보므로 지금 regex에 맞는다. 6단계 `idsim_common` 추가 PR에 넣는다.
- `test/`를 tidy 대상에 넣을지: `idsim_mission`은 처음부터 넣는 것을 권한다. [실측] 탐침 gtest 파일 하나에 돌렸을 때 gtest 매크로에서 온 경고는 없었고, 나온 21건(braces 11, const-correctness 3 등)은 모두 탐침 코드 자체의 것이었다. 기존 `idsim_common/test/`는 재지 않았다(px4_ros_com 등 test 의존을 빌드해야 한다). 이미 있는 테스트까지 넣을지는 한 번 돌려 건수를 본 뒤 devops와 정한다.

## R13. DDS 참가자 수

[실측] 호스트에서 `ss -uln`으로 도메인별 유니캐스트 포트(7410 + 250D + 2i, 7411 + 250D + 2i)를 셌다. 참가자 하나가 포트 둘이다. 남의 도메인에는 참가자를 만들지 않고 포트만 셌다.
- 스택 k=2(1대, 운용 노드 없음): 참가자 2개(인덱스 0, 1). `ss -p`로 프로세스를 본 도메인 25에서 인덱스 0은 에이전트(root 소유라 이름은 안 보였다), 1은 `parameter_bridge`였다.
- 탐침 노드 하나를 더하면 1개씩 는다(k=2에서 timer 탐침 둘이 떠 있는 동안 4개).
- 노드 하나 = 참가자 하나, CLI 한 번 = 실행 중 1개, daemon = 계속 1개(R3).
- 다른 담당자의 도메인 25에서는 같은 시각에 에이전트, bridge, foxglove_bridge, python3 하나로 4개였다.

의견(1대와 3대의 예상치. 운용 노드는 프로세스 하나로 계산):

| 항목 | 1대 | 3대 | 근거 |
| --- | --- | --- | --- |
| 에이전트(PX4 클라이언트마다 1) | 1 | 3 | [실측] 1대. 3대는 `cyclonedds.xml` 주석의 3대 실측 |
| bridge | 1 | 1 | [실측] |
| 운용 노드 서비스(기체당 컨테이너, Phase 2에도 프로세스 하나) | 1 | 3 | [실측] 노드 하나 = 1 |
| pytest(rclpy) | 1 | 1 | [추정] 프로세스 하나 |
| healthcheck CLI(`--no-daemon`, 동시 실행 상한) | 1 | 3 | [실측] 실행 중에만 1 |
| daemon(`--no-daemon`을 안 쓰면) | 1 | 1 | [실측] |
| foxglove_bridge(`viz`) | 1 | 1 | [실측] 도메인 25 |
| 합 | 7 | 13 | |

- `MaxAutoParticipantIndex` 50 대비 여유가 크다. Phase 3의 Fleet Manager와 게이트웨이(ROS를 모른다)를 더해도 15 안팎이다([추정]).
- 주의: 인덱스는 빈 포트를 앞에서부터 잡으므로 프로세스가 죽으면 다시 쓰인다(도메인 21에서 인덱스 0이 비고 1, 2가 쓰이는 것을 봤다). SIGKILL된 참가자의 포트는 프로세스 종료와 함께 풀린다([추정] 소켓은 커널이 닫는다. lease가 남는 것은 그래프 항목이다).

## R14. `foxglove` 허용 목록

의견. foxglove_bridge의 `topic_whitelist`(정규식 목록) 초안. 생성기가 stack.json의 기체 네임스페이스마다 만든다.

```yaml
topic_whitelist:
  - '^/clock$'
  # 기체마다 <ns> 자리에 stack.json의 ns(예 /px4_1)
  - '^<ns>/fmu/in/(trajectory_setpoint|offboard_control_mode)$'
  - '^<ns>/fmu/out/(vehicle_local_position|vehicle_status|vehicle_land_detected|vehicle_attitude)(_v[0-9]+)?$'
  - '^<ns>/mission_event$'
  - '^<ns>/execute_mission/_action/(status|feedback)$'
```

- 표기: `_v[0-9]+`를 선택 꼬리로 두어 PX4 메시지 버전이 바뀌어도 고치지 않는다. 생성기는 Python이라 `idsim_common`의 C++ mapping을 쓸 수 없으므로 버전을 박지 않는 것이 "토픽 이름은 mapping에서만"과 부딪치지 않는 방법이다. 이 파일은 읽기 전용 필터라 이름이 틀리면 화면에 안 보일 뿐이다.
- 기체 수: 줄이 기체마다 늘 뿐 모양은 같다. `^/px4_[0-9]+/`처럼 기체 번호 규칙을 정규식에 넣지 않는다(N에서 이름을 계산하지 않는다는 원칙).
- `/fmu/in/*`의 구독은 PX4에 영향이 없다([추정] 읽기 전용 구독자 추가일 뿐이다). foxglove_bridge의 파라미터 이름과 QoS 적응 동작은 이 이미지에 패키지가 없어 확인하지 못했다. [문서] https://github.com/foxglove/ros-foxglove-bridge 의 README로 devops가 확인한다.

## 부딪칠 것으로 보이는 지점

1. 충돌 예상 1(R1, P9): ROS 시각 timer를 권한다. PX4가 "setpoint 0건"과 "같은 timestamp 반복"을 어떻게 다르게 보는지가 px4 답에 달렸다.
2. 충돌 예상 3(R3, R5, D3): activate 실패를 healthcheck 실패로 드러내는 데 찬성한다. CLI healthcheck가 1회 약 2 s(부하 상태)라 devops의 비용 판단과 부딪칠 수 있다. 파일 표식 대안을 냈다.
3. 충돌 예상 4(R9, T5): ROS 비의존 상태기를 6단계로 당기자는 의견이다. roadmap의 1b 1번 범위와 부딪친다.
4. R2: 실행 중 deactivate를 거부(FAILURE)하자는 안은 계약에 없는 동작이다. architect가 Executor 설계 노트에 둘지 정할 일이다.
5. R12: B9가 "include로 닫힌다"는 README의 전제가 [실측]으로 틀렸다. `idsim_common`에 header 검사 TU를 더해야 한다.
6. R11: `cert-err58-cpp` 추가는 `.clang-tidy` 변경이라 devops 영역이다.
7. R4: `vehicle_id`를 params로 따로 받지 않자는 안은 C12(stack.json과 params에 `vehicle_id`)의 "params" 부분과 부딪친다.

## 실험을 못 한 것과 이유

- R1의 유휴 상태 분포와 일부러 건 CPU 부하 분포: 측정 내내 다른 담당자의 스택 둘과 빌드가 떠 있어 유휴 상태를 만들 수 없었고, 추가 부하는 그들의 측정을 흔들어 걸지 않았다. 있는 값은 모두 load average 6-19의 값이다.
- R1의 Gazebo 발행에서 노드 `now()`까지의 끝단 지연: Gazebo `/clock`에 보낸 시각이 없어 노드 도착 이후 구간만 쟀다.
- R3의 자기 timer 안에서 `activate()`를 부르는 방식: 탐침에서는 다른 thread에서 부른 경우만 확인했다.
- R7의 `colcon test` 경유 소요 시간: 저장소 `ros_ws`를 빌드하지 않는 조건이라 gtest 바이너리를 같은 컨테이너 조건에서 직접 돌렸다.
- R10의 컨테이너 기동에서 첫 `wait_for_server` 성공까지의 시간, `result_timeout`의 ROS 시각 판정 반복: 각 1회다.
- R12의 기존 `idsim_common/test/` tidy 건수: test 의존(px4_ros_com 등)까지 빌드해야 해서 하지 않았다.
- R14: 이미지에 foxglove_bridge가 없어 파라미터 이름을 확인하지 못했다.

## 재질문 답(2026-11-11)

공통 조건. 스택은 올리지 않았다(그 시각 호스트에는 px4-engineer의 스택 하나만). 탐침은 scratchpad `r6/root/ros_ws/src/probe7`(C++ `rclcpp_lifecycle::LifecycleNode` 하나와 같은 executor의 구독 노드 하나)이고 ros-ws 이미지(Jazzy, `rclcpp_lifecycle` 28.1.22, `ros2run` 0.32.13)에서 `--network none`, 도메인 97, 저장소 `cyclonedds.xml` 사본으로 돌렸다. 빌드는 `MAKEFLAGS=-j2`, worker 1. 저장소 `ros_ws`는 빌드하지 않았다. 시간 값은 1-3회의 값이다.

### 재질문 ros2 1. 자기 전이와 표식 파일

[실측] (가) 자기 timer 안의 `activate()`
- `main`이 `configure()`를 한 번 부르고 `SingleThreadedExecutor`의 1 s wall timer가 inactive이면 `activate()`를 부른다. on_activate가 FAILURE면 `activate()`는 inactive를 돌려주고(0.1-0.3 ms) 다음 tick에 다시 시도한다. 두 번 실패하게 둔 실행(1회)은 셋째 시도에 active, 한 번 실패하게 둔 실행(1회)은 둘째에 active였고, 실패 없이 둔 실행 15회(종료 시험 14회, 정지 시험 1회)는 모두 첫 시도에 active였다. 막힘이나 교착은 없다.
- 같은 timer에서 `deactivate()`를 부른 뒤 재시도 loop로 돌아가 다시 active가 된다(1회: active 2.014 s -> 자기 deactivate 6.014 s -> 실패 7.013 s -> active 8.014 s). 5번 결정의 "스스로 deactivate해 재시도 loop로"가 이 모양으로 된다.

[실측] (나) node interface로 만든 일반 publisher
- `rclcpp::create_publisher<MissionEvent>(npi, nti, name, qos)`는 `rclcpp::Publisher`를 돌려주고 inactive에서도 전달된다(inactive 3 s 동안 일반 14건, `LifecyclePublisher` 0건과 경고 로그. active에서는 둘 다 14건).
- 주의: 이 함수는 interface `SharedPtr`를 lvalue 참조로 받는다. `get_node_topics_interface()`를 인자에 바로 넣으면 컴파일되지 않고 지역 변수로 받아 넘겨야 한다. `this->create_publisher`는 lifecycle 노드에서 `LifecyclePublisher`를 돌려주므로 쓰지 않는다.

[실측] (다) 표식 파일과 종료. 표식은 on_activate에서 쓰고 on_deactivate, on_shutdown에서 지운다. 컨테이너 PID 1 기준, `docker stop -t 10`과 `docker kill -s KILL`.

| 실행 방식 | 종료 처리(`main`) | 신호 | stop 시간 | 종료 코드 | 표식 |
| --- | --- | --- | --- | --- | --- |
| 직접 `exec` | 없음 | TERM | 0.10-0.21 s | 0 | 남음 |
| 직접 `exec` | spin 뒤 `shutdown()` | TERM | 0.24 s | 0 | 남음 |
| 직접 `exec` | context pre-shutdown callback에서 `shutdown()` | TERM | 0.09-0.18 s(3회) | 0 | 지워짐 |
| 직접 `exec` | spin 뒤 파일을 직접 지움 | TERM | 0.21 s | 0 | 지워짐 |
| `exec ros2 run` | 없음 또는 spin 뒤 `shutdown()` | TERM | 10.15-10.19 s | 137 | 남음 |
| 직접, `ros2 run` | - | KILL | 0.09-0.14 s | 137 | 남음 |

- SIGTERM이 오면 rclcpp 신호 처리기가 context를 닫고 spin이 돌아온다. 그 뒤의 `shutdown()`은 전이하지 않고 active를 그대로 돌려주며 on_shutdown이 불리지 않는다. 소멸자도 on_shutdown을 부르지 않는다(28.1.22, 로그 `dtor state=active`). 그래서 "shutdown에서 지운다"는 그대로 두면 동작하지 않는다.
- on_shutdown이 불리는 길은 context의 pre-shutdown callback(`get_node_base_interface()->get_context()->add_pre_shutdown_callback`) 하나였다. 그 안에서 `shutdown()`이 on_shutdown을 부르고 finalized로 가며, on_shutdown 안의 publish는 예외 없이 돌아왔다(`rclcpp::ok()` 참. 수신까지는 다른 프로세스로 확인하지 않았다). 이 callback은 신호 처리 thread에서 돌아 executor thread와 동시에 실행된다.
- `ros2 run`을 PID 1로 두면 Python이 SIGTERM 처리기를 두지 않아 PID 1의 신호가 무시되고 자식은 신호를 받지 못한 채 10 s 뒤 SIGKILL된다. `bash -c "source ...; 실행 파일"`은 bash가 마지막 명령을 exec해 직접 실행과 같았다(0.08-0.10 s, 코드 0). 의존할 동작은 아니므로 명시적 `exec`를 쓴다.
- SIGKILL 뒤의 표식은 당연히 남는다. 컨테이너를 다시 시작하면 쓰기 계층이 그대로라 남은 표식이 다음 기동에 이어진다. 노드가 생성자에서 표식을 먼저 지우게 하자 남은 파일(1회)이 configure 전에 지워졌다.

[실측] 멈춘 프로세스. active에서 executor를 30 s 막자(`sleep`) 표식은 계속 있었고 `test -f`는 참이었다. 1 Hz 재시도 timer가 active일 때 표식의 mtime을 갱신하게 하면 막힌 동안 나이가 1 s씩 늘었다. 컨테이너 안에서 100회 실행: `test -f` 3 ms, `test -n "$(find <표식> -newermt '-5 seconds')"` 115 ms(1회 약 1.2 ms).

의견: 표식 방식은 받되 결함 셋을 구현 규칙으로 막는다.
1. 종료 시 표식 제거와 종료 사건은 pre-shutdown callback에 건다. 다만 lifecycle `shutdown()`을 신호 thread에서 부르면 tick과 경합하므로, callback은 노드의 mutex를 잡고 "goal을 ABORTED, INTERNAL로 끝내고 종료 사건을 내고 setpoint를 멈추고 표식을 지운다"를 직접 한다. 5번의 "shutdown 전이에서 ..." 문장은 "context 종료 직전 callback에서 ..."로 읽는다. spin 뒤에는 publish가 닿는다고 가정하지 않는다.
2. 남은 표식: 노드는 생성자에서 표식을 지운다. 생성기는 표식 경로를 컨테이너의 `tmpfs` 마운트(예 `/run/idsim`) 아래로 준다. 둘 중 하나로도 막히지만 생성자 제거는 노드 규칙, `tmpfs`는 생성기 규칙으로 둘 다 둔다(devops 확인 대상).
3. 멈춘 노드: `test -f`만으로는 executor 정지를 못 본다. active 동안 1 Hz wall timer가 mtime을 갱신하고 healthcheck는 "5 s 안에 갱신됨"을 본다. 비용은 1회 약 1 ms다. 갱신 주기 1 s 대비 5 s는 경합 중 timer 지연(최대 157.6 ms)의 30배 여유다. healthcheck 실패가 컨테이너를 재시작하지는 않으므로(compose 기본) 이 판정은 기동 순서와 `stack.sh`의 실패 보고에만 쓰인다.
- 실행: `mission-N`의 command는 실행 파일 직접 `exec`이고 `ros2 run`을 쓰지 않는다(위 10 s와 137). devops의 재질문 1(bridge, agent)과 같은 규칙이다.
- 대안(`ros2 lifecycle get --no-daemon`)으로 돌아갈 근거는 없다.

### 재질문 ros2 2. `vehicle_id` 전달

[실측] C++ lifecycle 노드, `-r __ns:=/px4_1 -r __node:=<이름>`, `vehicle_id`(문자열)와 `sysid`(정수)를 기본값 없이 타입만으로 on_configure에서 선언(`declare_parameter(name, ParameterType)`, `has_parameter`로 재선언을 피함). 각 1회.

| 경우 | 결과 |
| --- | --- |
| key `/px4_1/mission_executor`, `__node:=mission_executor` | 적용, configure SUCCESS |
| key `/px4_1/mex`, `__node:=mex` | 적용 |
| key `/px4_1/mission_executor`, `__node:=mex`(원래 이름 key) | 적용 안 됨 |
| 다른 기체 파일(key `/px4_2/mission_executor`) | 적용 안 됨. 선언은 통과하고 `get_parameter`에서 `ParameterUninitializedException` -> configure FAILURE |
| params 파일 없음 | 위와 같다 |
| key `/**`, `vehicle_id: px4_2` | 적용됨. 대조에서 `/px4_1 != /px4_2`로 FAILURE |
| key `px4_1/mission_executor`(앞 빗금 없음) | 적용 |
| `sysid: "2"`(문자열) | 선언에서 `InvalidParameterTypeException` -> FAILURE |
| 파일 둘(`/px4_2/...`, `/px4_1/...`) | 정확한 key 쪽만 적용 |
| ns `/a/b`, `vehicle_id: a/b` | 단순 비교(`ns == "/" + vehicle_id`)로는 통과한다 |

- 결론: 다른 기체의 파일은 "선언" 단계가 아니라 "읽기" 단계에서 실패한다(타입만으로 선언하면 선언 자체는 통과). 어느 쪽이든 on_configure 안에서 잡으면 FAILURE이고, 생성자에서 선언하면 타입 오류가 예외로 프로세스를 끝낸다. 그래서 선언은 on_configure에서 한다.
- 노드 key는 remap 뒤의 이름이어야 한다. `__node`를 생성기가 주는 이상 params key와 `__node`는 같은 원천에서 만들어야 한다(잠정안대로).

의견: 잠정안에 반대하지 않는다. 내 R4(파생)는 철회한다. 값의 수가 같고, 다른 기체 파일과 `/**` 파일이 모두 configure에서 걸리는 것을 확인했으며, 파생을 두지 않으면 `idsim_common`이 이름 규칙을 해석하지 않는다는 5단계 결정과 맞는다. 단 마지막 줄 때문에 대조에 "토큰 하나" 검사가 필요하다.

key 철자: `vehicle_id`(문자열), `sysid`(정수). 점 접두사 없이 `stack.json`의 필드 이름과 같게 한다. 표식 경로는 `health_marker`(문자열, 비면 쓰지 않음).

시그니처(`idsim_common`. `vehicle.hpp`는 rclcpp 없이 두고 선언 helper는 새 header에 둔다):

```cpp
// vehicle.hpp
class VehicleId
{
public:
  // 비어 있지 않고 빗금이 없으며 rmw_validate_node_name 규칙의 토큰 하나. 정규화하지 않는다.
  static std::optional<VehicleId> parse(const std::string & text, std::string * error = nullptr);
  const std::string & str() const;
  bool operator==(const VehicleId &) const;  // 정확한 문자열 비교
};
struct VehicleIdentity { VehicleId id; VehicleNamespace ns; SystemId sysid; };
// ns.str() == "/" + id.str()인지만 본다. 변환 함수는 두지 않는다.
bool namespace_matches(const VehicleId & id, const VehicleNamespace & ns);

// vehicle_params.hpp
inline constexpr char kVehicleIdParam[] = "vehicle_id";
inline constexpr char kSysidParam[] = "sysid";
// 두 파라미터를 기본값 없이 선언하고(이미 있으면 건너뜀) 노드 네임스페이스와 대조한다.
// 예외를 내지 않는다. 실패하면 nullopt이고 error에 두 값을 적는다. on_configure에서 부른다.
std::optional<VehicleIdentity> declare_vehicle_identity(
  rclcpp::node_interfaces::NodeBaseInterface & base,
  rclcpp::node_interfaces::NodeParametersInterface & params,
  std::string * error = nullptr);
```

- interface 인자로 두어 `rclcpp::Node`와 `LifecycleNode` 둘 다 받는다(템플릿을 피한다).
- `VehicleIdentity`에 필드가 늘어 기존 집합체 초기화(`test_vehicle.cpp`, `test_vehicle_command.cpp`)를 고친다. 단위 테스트: 위 표의 열 줄 중 파일 기반 일곱 줄과 다중 토큰 거부.
- `VehicleCommandBuilder`, `verify`는 `id`를 쓰지 않는다. `MissionEvent.vehicle_id`와 goal의 `vehicle_id` 대조가 `id.str()`을 쓴다.
