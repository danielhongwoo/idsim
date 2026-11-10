> 이 파일은 2026-11-10 설계 토론의 원문이다. 본문의 `/tmp/...scratchpad...` 경로와 `re/`, `ws/`, `exp/` 같은 실험 경로는 당시 작업 환경의 임시 파일이라 저장소에 없다. 실험 결과는 본문에 인용된 내용이 전부다.

# 1a 4단계 idsim_common 설계 초안과 사실 확인 (ros2-engineer, 2026-11-10)

실험 환경: `idsim/ros-ws:local`(IDSIM_BUILD_PX4_ROS_COM_REF=86e9aeb..., IDSIM_BUILD_PX4_MSGS_REF=86d8239e...), GCC 13.3. 스택은 k=4로 올렸다가 내렸다(run `artifacts/runs/20261110-050217-k4`). 실험 소스는 스크래치 `step4/ws/src/ft_probe/`, `step4/py/`, PX4 v1.17.0 원문은 `step4/dl/`. 저장소 파일은 고치지 않았다.

## Q1 frame_transforms 호환

결론: 빌드와 링크는 된다(C++17/20, -Wall -Wextra -Wpedantic -Werror). 하지만 래핑하지 말고 직접 구현할 것을 권고한다. 벡터와 쿼터니언 정적 변환은 맞다. 그러나 공분산 3x3 변환 두 개가 틀렸고, 공개 템플릿 3개는 링크가 안 되고, yaw 스칼라 변환이 없고, 동체 좌표 변환이 NaN을 다른 축으로 번지게 한다. px4_ros_com은 단위 테스트의 비교 기준(oracle)으로만 쓴다(test_depend).

근거.
- 라이브러리 `frame_transforms`는 px4_msgs에 의존하지 않는다(CMakeLists: `ament_target_dependencies(frame_transforms Eigen3 geometry_msgs sensor_msgs)`). 따라서 "px4_msgs v1.17 호환"은 순수 수학 코드 문제이고, 접점은 `std::array<float,4>` 쿼터니언 하나뿐이다(`array_to_eigen_quat(odom.q)` 정상).
- 내보내는 타깃은 `px4_ros_com::frame_transforms`이고, include 경로가 `include/px4_ros_com`와 `include` 두 개라 `<frame_transforms.h>`로도 잡힌다(전역 헤더 이름 충돌 위험).
- 헤더 API: `StaticTF{NED_TO_ENU, ENU_TO_NED, AIRCRAFT_TO_BASELINK, BASELINK_TO_AIRCRAFT, ECEF_TO_ENU, ENU_TO_ECEF}`, `transform_orientation`, `transform_static_frame`(Vector3d, Covariance3d/6d/9d), `transform_frame(vec|cov, q)`, 편의 템플릿 `ned_to_enu_local_frame`, `px4_to_ros_orientation`, `ros_to_px4_orientation`, `baselink_to_aircraft_body_frame` 등, `utils::quaternion::{quaternion_from_euler, quaternion_to_euler, quaternion_get_yaw, eigen_quat_to_array, array_to_eigen_quat}`, `utils::types::{covariance_to_array, covariance_urt_to_array, array_urt_to_covariance_matrix}`(템플릿). 헤더 안에 `static const` 전역(NED_ENU_Q 등)이 있다.
- 프로브 출력(C++17과 20에서 같음):
```
ned_to_enu_local_frame(1,2,3) = (2.000, 1.000, -3.000)                         <- 맞음
baselink_to_aircraft_body_frame(1,2,3) (FLU->FRD 기대 1,-2,-3) = (1.000, -2.000, -3.000)  <- 맞음
px4_to_ros_orientation(I) = w-0.7071 x0.0000 y0.0000 z-0.7071 ; yaw_ros(deg)=90.000      <- 맞음(부호 반전 q, 같은 회전)
PX4 yaw30 -> ROS yaw(deg)=60.000                                                <- 맞음
quaternion_to_euler(yaw -90)(deg) = (180.000, 180.000, 90.000)                  <- 같은 회전이지만 표준형이 아님. yaw 추출에 못 씀
transform_frame(Cov3d diag(1,4,9), yaw90) = 0.00 -1.00 0.00 4.00 0.00 0.00 0.00 0.00 9.00   <- 틀림(R C R^T가 아니라 C R. 기대 diag(4,1,9))
transform_frame(Cov6d diag(1..6), yaw90) diag = 2.00 1.00 3.00 5.00 4.00 6.00   <- 맞음
transform_static_frame(Cov3d diag(1,4,9), AIRCRAFT_TO_BASELINK) = 1 0 0 0 -4 -0 0 0 -9  <- 틀림(음의 분산)
```
- 템플릿 링크 실패(정의가 .cpp에만 있고 명시적 인스턴스화가 없다):
```
undefined reference to `void px4_ros_com::frame_transforms::utils::types::covariance_urt_to_array<Eigen::Matrix<double, 3, 3, 0, 3, 3>, 6ul>(...)'
```
- NaN 전파(TrajectorySetpoint는 NaN을 "제어 안 함"으로 쓴다):
```
enu_to_ned(1,2,NaN) = 2.000000 1.000000 nan        <- 축별 치환이라 안전
baselink_to_aircraft(1,2,NaN) = nan nan nan        <- Affine 곱이라 NaN이 다른 축으로 번진다
```
- `TrajectorySetpoint.yaw`(NED, 북 기준 시계방향)와 ENU yaw 사이의 스칼라 변환 함수가 없다. 6단계와 1b에 바로 필요하다.

직접 구현 범위(작다): 축 치환과 부호만으로 하는 NED<->ENU, FRD<->FLU(NaN 보존), 쿼터니언 `q_ros = Q_NED_ENU * q_px4 * Q_FRD_FLU`와 역변환, yaw `wrap_pi(pi/2 - yaw)`(자기 역함수), px4_msgs `std::array<float,3>`, `std::array<float,4>` 어댑터, 대각 분산(position_variance 등) 치환. 전체 공분산 회전은 소비자가 없어 범위에서 뺀다. 테스트는 회전이 같은지(q와 -q를 같은 것으로)를 비교하고, 벡터와 쿼터니언은 px4_ros_com 결과와 차등 비교한다.

## Q2 토픽 이름 매핑

결론: px4_msgs 고정 커밋의 C++ 타입에는 `static constexpr uint32_t MESSAGE_VERSION`이 있거나(34개 타입) 아예 없다. PX4 규칙은 "버전이 0이 아니면 `_v<N>`"이고, 골든 65줄 전부가 이 규칙과 맞는다. API는 문자열 인자를 받는 `px4_topic<T>(ns, dir, base)`를 공개하지 말고, idsim_common 안에 (타입, 방향, 논리 이름) 기술자(descriptor) 목록을 두는 형태를 권고한다.

근거.
- PX4 v1.17.0 `src/modules/uxrce_dds_client/utilities.hpp` 26-50행:
```
if (message_version != 0) { snprintf(version, sizeof(version), "_v%u", (unsigned)message_version); ...
snprintf(topic_name, TOPIC_NAME_SIZE, "rt/%s/%s%s", client_namespace, topic, version);
```
  버전은 `dds_topics.h.em` 44-58행에서 SFINAE로 얻는다(`decltype(&C::MESSAGE_VERSION)`가 있으면 그 값, 없으면 0). 우리 방식과 같다.
- px4_msgs 헤더: `vehicle_status__struct.hpp:491: static constexpr uint32_t MESSAGE_VERSION =`. offboard_control_mode에는 없다. 프로브 결과 `ver VehicleStatus=1 VehicleLocalPosition=1 TrajectorySetpoint=0 OffboardControlMode=0 VehicleCommand=0`(`std::void_t` 특수화).
- `.msg` 34개에 상수가 있다: 값 1이 9개(Event 포함), 0이 25개. Event는 DDS로 나가지 않아 골든의 `_v1`은 8개다.
- 골든 65줄 전체를 대조했다. 각 줄의 타입에 대해 `.msg`의 버전으로 기대 이름을 만들어 비교한 결과 `bad=0`이다. PX4 v1.17.0 `dds_topics.yaml`의 토픽 집합도 골든 65개와 정확히 같다(diff에 나온 건 주석 처리된 `vehicle_angular_velocity` 1줄뿐).
- 논리 이름이 타입 이름과 다른 실례가 있다: `vehicle_gps_position`(SensorGps), `aux_global_position`(VehicleGlobalPosition), `config_control_setpoints`(VehicleControlMode). 같은 타입을 두 토픽이 쓰는 경우도 있다: `vehicle_command`와 `vehicle_command_mode_executor`, `vehicle_mocap_odometry`와 `vehicle_visual_odometry`. 그래서 키는 반드시 (논리 이름, 타입) 쌍이어야 한다.

API 제안(C++17 원형을 ros-ws에서 컴파일했고 Node와 LifecycleNode 둘 다 동작):
```cpp
namespace idsim_common::px4 {
enum class Direction { In, Out };
namespace topics {   // 이 목록이 유일한 출처. 다른 패키지는 문자열을 쓰지 않는다
IDSIM_PX4_TOPIC(VehicleStatus, px4_msgs::msg::VehicleStatus, Out, "vehicle_status")
IDSIM_PX4_TOPIC(VehicleCommand, px4_msgs::msg::VehicleCommand, In, "vehicle_command")
...
}
template <class Topic> std::string topic_name(const VehicleNamespace & ns);
template <class Topic, class NodeT, class Cb> auto create_subscription(NodeT &, const VehicleNamespace &, Cb &&);  // Out만, QoS 고정
template <class Topic, class NodeT> auto create_publisher(NodeT &, const VehicleNamespace &);                    // In만, QoS 고정
}
```
원형 출력:
```
/px4_1/fmu/out/vehicle_status_v1
/px4_1/fmu/in/vehicle_command
/px4_2/fmu/in/offboard_control_mode
```
잘못된 방향으로 쓰면 컴파일이 실패한다: `error: static assertion failed: publish only to /fmu/in`. 논리 이름에 `_vN`을 붙이면 `static_assert(!has_version_suffix(BASE))`가 막는다.
- 컴파일 시점 강제의 뜻: 타입, 방향, 논리 이름이 기술자 하나에 묶이므로 호출자는 셋 중 어느 것도 따로 고를 수 없다. 메시지 타입은 `Topic::Msg`에서 나오므로 타입 불일치가 컴파일 오류가 된다. 버전 접미사는 `if constexpr`로 결정된다. 스모크 문서가 적은 `px4_topic<T>(ns, dir, base)`는 `detail`로 내린다(공개하면 다른 패키지에 문자열이 생긴다). 이것은 smoke-test-phase1a.md 문구와 달라지는 점이라 architect 결정 사항이다.
- 다른 패키지의 문자열 금지는 컴파일러로 강제할 수 없다. lint.sh에 "`ros_ws/src`에서 idsim_common과 test를 빼고 `fmu/(in|out)/` 문자열이 나오면 실패" 검사를 더할 것을 devops에 제안한다.
- 1a 기술자 목록(6단계 소비자 기준. 추정이며 px4-engineer와 확정): Out은 vehicle_status, vehicle_local_position, vehicle_land_detected, vehicle_command_ack, vehicle_attitude, vehicle_odometry, vehicle_global_position, failsafe_flags, home_position, timesync_status. In은 offboard_control_mode, trajectory_setpoint, vehicle_command.

골든 비교 테스트.
- 경로: smoke 문서 설계대로 CMakeLists가 configure 시점에 `${CMAKE_CURRENT_SOURCE_DIR}/../../../docker/versions.env`에서 `PX4_TAG`와 `PX4_MSGS_REF`를 읽고, `ament_add_gtest(... ENV IDSIM_PX4_FIXTURE_DIR=<repo>/tests/fixtures/px4/<tag> IDSIM_PX4_MSGS_REF=<ref>)`로 넘긴다. 테스트는 변수가 없거나 디렉터리가 없으면 FAIL한다. 주의: 패키지를 이미지에 COPY해 빌드하면(Dockerfile.ros-ws 주석의 자리) 상대 경로가 깨진다. 그래서 `IDSIM_REPO_ROOT` CMake 캐시 변수로 덮어쓸 수 있게 하고, 없으면 configure를 실패시킨다.
- 테스트 세 가지.
  1. 기술자 목록 전체에서 `(topic_name 상대형, "px4_msgs/msg/<Type>")` 쌍이 topics.txt의 부분집합인지. 타입 문자열은 `rosidl_generator_traits::name<Msg>()`(`"px4_msgs/msg/VehicleStatus"`)로 얻는다. 리터럴로 쓰지 않는다.
  2. 규칙 전수 검사: 테스트 안에 px4_msgs 타입 목록만 X-macro로 둔다(골든에 나오는 타입 약 60개. 토픽 이름은 쓰지 않는다). 골든 각 줄에 대해 기본 이름(`_v<숫자>`를 뗀 것)과 타입으로 `detail::topic_name<T>`를 불러 원래 줄과 같은지 본다. 골든에 목록에 없는 타입이 나오면 FAIL하고 그 타입 이름을 출력한다(태그를 올릴 때 목록 갱신을 강제한다). 이렇게 하면 "골든에 있지만 매핑에는 없는 토픽"은 규칙 수준에서 다 검증되면서도 실패가 아니다. 개수는 정보로만 출력한다.
  3. 더미 타입(상수 없음, 0, 3)으로 `msg_version` 자체를 검사하고, env.txt의 `PX4_MSGS_REF`가 versions.env와 같은지 본다.
- Python 쪽(check_px4.py, 6단계 pytest)은 지금 정규식 `(_v[0-9]+)?`로 찾는다. C++ 매핑은 Python에서 쓸 수 없다. rclpy 메시지 클래스에도 `MESSAGE_VERSION` 속성이 있으므로 같은 규칙의 Python 쌍둥이를 `tests/support`에 둘지는 Q6으로 넘긴다.

## Q3 QoS

결론: `/fmu/out` 구독과 `/fmu/in` 발행 모두 BEST_EFFORT, VOLATILE, KEEP_LAST, depth 5다. 값은 `rclcpp::SensorDataQoS()`와 같다. 이름 있는 함수 `px4_out_qos()`와 `px4_in_qos()` 두 개로 감싸 한 곳에서만 바꾸게 한다. 구독에 TRANSIENT_LOCAL을 쓰지 않는다(효과가 없음을 실측했다).

근거.
- 골든 qos 27개가 모두 같다: `reliability=BEST_EFFORT durability=TRANSIENT_LOCAL history=KEEP_LAST depth=1`. PX4 소스 `utilities.hpp` 78-83행의 writer는 `TRANSIENT_LOCAL, BEST_EFFORT, KEEP_LAST, depth 0`이고, 135-140행의 reader는 `VOLATILE, BEST_EFFORT, KEEP_LAST, depth = orb 큐 x 2`다.
- k=4 실측, 에이전트 reader(`/fmu/in`):
```
== in/offboard_control_mode   SUBSCRIPTION  Reliability: BEST_EFFORT  History (Depth): KEEP_LAST (1)  Durability: VOLATILE
== in/trajectory_setpoint     (같음)
in/vehicle_command  Node name: _CREATED_BY_BARE_DDS_APP_  SUBSCRIPTION  BEST_EFFORT  KEEP_LAST (1)  VOLATILE
```
- 늦게 붙은 구독자 실험. disarm 명령으로 ack를 만든 뒤 새 프로세스로 `vehicle_command_ack`를 3초 구독했다:
```
-- late join TL    tl vehicle_command_ack: count=0 first=None
-- late join VOL   vol vehicle_command_ack: count=0 first=None
```
  에이전트(Fast DDS)의 best-effort TL writer는 늦게 붙은 구독자에게 이력을 주지 않는다. vehicle_status 첫 수신은 TL 1.15초, VOL 1.50초로, 디스커버리 소요 차이 수준이다. TL reader는 매칭 조건만 좁히므로(VOLATILE writer, 예를 들어 다른 재생 도구와 안 맞음) VOLATILE이 낫다.
- `/fmu/in` 발행: RELIABLE과 BEST_EFFORT 둘 다 ack를 받았다(`target 2, ts now, RELIABLE` -> `ack result=0`, BE도 `result=0`). reader가 BE이므로 실효 신뢰성은 어느 쪽이든 BE다. 상대와 같은 BE로 두어 heartbeat와 재전송 상태를 없앤다. 발행 depth는 BE+VOLATILE에서 전송에 영향이 없다.
- SensorDataQoS 값 실측: `reliability=2 durability=2 history=1 depth=5`(rmw enum으로 BEST_EFFORT, VOLATILE, KEEP_LAST, 5). 차이는 없다. 다른 점은 이름 붙인 래퍼가 "PX4 계약"을 한 곳에 고정한다는 것뿐이다. rclpy 판정의 `qos_profile_sensor_data`와도 같은 값이라 테스트와 노드가 어긋나지 않는다.
- depth 5는 버스트가 있는 ack에서 콜백이 늦을 때 버퍼가 된다. 최신값만 쓰는 상태 토픽에서도 손해가 없다.

부수 사실(6단계와 로깅에 중요).
- `/fmu/out`의 timestamp는 에이전트 OS 시각(epoch us)이다. 실측: `ack ... ts=1794287035630346`, vehicle_status `timestamp: 1794287104615710`. 이유는 UXRCE_DDS_SYNCT 기본값 1과 ucdr serialize의 `topic.timestamp + time_offset` 때문이다. `/clock`(sim)과도, PX4 hrt와도 기준이 다르다. architecture.md의 "PX4 timestamp는 ULog 정렬에만"과 맞지만, ULog의 hrt와 맞추려면 offset이 필요하다. logging-engineer에게 넘긴다.
- `/fmu/in` 수신 시 PX4 ucdr deserialize(Tools/msg/templates/ucdr/msg.h.em 167-169행):
```
if (topic.timestamp == 0) topic.timestamp = hrt_absolute_time();
else topic.timestamp = math::min(topic.timestamp - time_offset, hrt_absolute_time());
```
  use_sim_time 노드가 `now()`(sim us)를 넣으면 `ts - offset`이 unsigned로 언더플로해 우연히 now가 된다. 그래서 `/fmu/in` 메시지의 timestamp는 0으로 보내 PX4가 수신 시각으로 찍게 하는 것을 권고한다. 소스 기반이다. ts=0인 disarm은 받아들여졌고(ack 0), Offboard 신선도 판정은 6단계가 반증 지점이다.

## Q4 네임스페이스와 식별

결론: `target_system = N+1`을 idsim_common의 상수나 공식으로 두지 않는다. 노드는 생성된 파라미터 파일(6단계, stack.json에서 생성)로 `vehicle.ns`와 `vehicle.sysid`를 받는다. 실행 중에는 `vehicle_status.system_id`와 대조해 다르면 명령 발행을 거부한다(lifecycle activate 실패). idsim_common은 파싱, 검증, 대조 함수만 제공하고 N에서 아무것도 계산하지 않는다.

근거.
- k=4 실측(disarm, target_component 1):
```
-- target 2, ts 0, BE   -> ack result=0
-- target 0, ts 0, BE   -> ack result=0      (broadcast 수락)
-- target 3, ts 0, BE   -> no ack in 3 s      (조용히 무시)
vehicle_status: system_id: 2  component_id: 1
```
  PX4 Commander.cpp 745-749행: `(cmd.target_system != _vehicle_status.system_id) && (cmd.target_system != 0)`이면 return false이고 ack도 없다. sysid가 틀리면 조용한 실패가 되므로 대조가 필요하다.
- 재계산 금지와 단일 출처의 관계: stack.json이 단일 출처이고, 노드는 stack.json을 직접 읽지 않고 그것에서 생성된 params 파일을 받는다(결정 (a), "launch 파일은 생성하지 않고 노드 파라미터 파일만"). N+1을 코드에 두면 같은 규칙의 두 번째 사본이 되고, 실기체 확장 때(architecture 목표: SITL을 실기체로 교체) 깨진다. `vehicle_status.system_id`는 PX4가 실제로 쓰는 값이라 대조 기준으로 가장 강하다. 그것만으로 sysid를 정하면(파라미터 없이 학습) 설정 오류(ns가 다른 기체를 가리킴)를 못 잡으므로 둘 다 쓴다.
- target 0(broadcast)은 DDS 네임스페이스가 이미 기체를 나누므로 동작은 하지만, 명시 sysid를 원칙으로 한다(방어 계층과 대조 가능성).
- API 초안:
  - `VehicleNamespace::parse(std::string)`: 절대 경로, 끝에 `/` 없음, `rmw_validate_namespace` 통과. `/px4_N` 형태를 강제할지는 architect 결정이다(권고: 형태만 검증하고 N은 꺼내지 않는다).
  - `SystemId`(1-255 강타입), `VehicleIdentity{VehicleNamespace ns; SystemId sysid;}`, `IdentityCheck verify(const VehicleIdentity&, const px4_msgs::msg::VehicleStatus&)`(system_id 불일치, component_id != 1을 구분해 보고).
  - 파라미터 이름(`vehicle.ns`, `vehicle.sysid`)과 선언 헬퍼 `declare_vehicle_identity(node)`도 idsim_common에 둔다. 생성기(devops)와 이름 계약이 필요하다.
- stack.json에는 `ns`(/px4_1), `px4_ns`(px4_1), `sysid`(2)가 이미 있다. 노드가 쓰는 건 `ns`와 `sysid` 둘이고 `px4_ns`는 PX4 환경용이다.
- 노드 네임스페이스(`/px4_N`에 띄우고 상대 이름 `fmu/out/...`)에 기대는 대안은 기각을 권고한다. Phase 3 Fleet Manager는 한 노드가 여러 기체를 구독하므로 명시적 ns가 필요하다.

## Q5 패키지 구조

결론: ament_cmake 패키지 하나에 작은 SHARED 라이브러리와 템플릿 헤더를 둔다. C++17. 의존은 rclcpp, rclcpp_lifecycle(헬퍼가 LifecycleNode를 받도록), px4_msgs, Eigen3(eigen3_cmake_module)이다. px4_ros_com은 test_depend만. 포매터는 clang-format(ROS 2 ament_clang_format 설정 그대로). ament_lint_auto에서는 uncrustify와 copyright를 끈다.

레이아웃:
```
ros_ws/src/idsim_common/
  package.xml  CMakeLists.txt
  include/idsim_common/
    px4_topics.hpp        Direction, detail::msg_version, detail::topic_name, IDSIM_PX4_TOPIC 기술자 목록
    px4_io.hpp            create_subscription/create_publisher 템플릿(QoS 고정, 방향 static_assert)
    qos.hpp               px4_out_qos(), px4_in_qos()
    frames.hpp            NED/ENU, FRD/FLU, 쿼터니언, yaw, px4_msgs 배열 어댑터
    vehicle.hpp           VehicleNamespace, SystemId, VehicleIdentity, verify, declare_vehicle_identity
    vehicle_command.hpp   CommandBuilder
  src/ vehicle.cpp vehicle_command.cpp frames.cpp
  test/ test_topics_rule.cpp test_topics_golden.cpp test_frames.cpp test_vehicle.cpp test_vehicle_command.cpp test_qos.cpp
```
- 라이브러리로 하는 이유: 검증 코드(rmw 이름 검사)와 빌더를 헤더에 두면 컴포넌트마다 중복된다. `ament_export_targets(... HAS_LIBRARY_TARGET)`, 네임스페이스는 `idsim_common::`.
- 단위 테스트는 노드와 DDS 참가자를 만들지 않는 순수 함수만 다룬다(CI unit 잡에서 네트워크와 CYCLONEDDS_URI가 필요 없다). 참고: 노드를 만드는 프로그램은 저장소 마운트가 없으면 이미지 기본값 `CYCLONEDDS_URI` 때문에 `can't open configuration file`로 죽는다(실측, 결정 (h)와 같은 현상).
- C++ 표준: GCC 13.3에서 17과 20 모두 px4_msgs, rclcpp, frame_transforms 헤더가 -Werror로 통과했다. Jazzy의 기준(REP 2000)이 C++17이고 필요한 기능(void_t, if constexpr, string_view)이 17에 있으므로 17을 권고한다. 프로젝트 전체 표준은 architect가 정한다(Phase 3 gRPC와 함께).
- VehicleCommand 빌더 불변식:
  - 생성자가 `VehicleIdentity`와 `CommandSource{system, component}`를 요구한다(target 없이 만들 수 없음).
  - `target_component = 1`(실측 component_id 1), `from_external = true`, `confirmation = 0`, `timestamp = 0`(Q3).
  - `from_external = true`의 근거는 PX4 `mavlink/streams/COMMAND_LONG.hpp` 89행 `if (!cmd.from_external && !px4_internal_cmd && !target_system_internal)`다. false면 MAVLink로 다시 내보내고 MavlinkCommandSender가 재전송한다.
  - 메서드: `arm()`, `disarm()`, `set_offboard()`(DO_SET_MODE param1=1, param2=6, px4-engineer 확인 필요), `land()`, `rtl()`, `raw(command, params)`.
  - ack는 commander가 `target_system/component = cmd.source_*`로 돌려준다(실측: source 1/1 -> ack target 1/1). 그래서 송신자 역할별 source_component를 정하면 각 소비자가 자기 ack만 거를 수 있다. 값은 px4-engineer와 정한다.
- clang-format: lint.sh 207행의 결정. `.clang-format` 제안(ament_lint jazzy `ament_clang_format/configuration/.clang-format` 원문과 같다, GitHub에서 받아 확인):
```
---
Language: Cpp
BasedOnStyle: Google

AccessModifierOffset: -2
AlignAfterOpenBracket: AlwaysBreak
BraceWrapping:
  AfterClass: true
  AfterFunction: true
  AfterNamespace: true
  AfterStruct: true
  AfterEnum: true
BreakBeforeBraces: Custom
ColumnLimit: 100
ConstructorInitializerIndentWidth: 0
ContinuationIndentWidth: 2
DerivePointerAlignment: false
PointerAlignment: Middle
ReflowComments: false
...
```
  ros-ws 이미지에는 clang-format과 ament_clang_format이 없다(`which clang-format` 결과 없음). 이 호스트는 archive.ubuntu.com이 막혀 apt 확인을 끝내지 못했다. lint 잡이 쓸 도구 고정(apt 버전 또는 pip `clang-format==<ver>`를 LINT_PYTHON_IMAGE에)은 devops-engineer가 정한다. 버전이 다르면 출력이 달라지므로 버전 고정이 필수다.
- ament_lint_auto: `ament_lint_common`을 test_depend로 두되 다음과 같이 한다.
  - `ament_cmake_uncrustify`는 끈다(clang-format과 서로 다른 형식을 강제해 충돌).
  - `ament_cmake_copyright`도 끈다(저장소에 LICENSE도 저작권 머리말 정책도 없다. 라이선스는 사용자 결정 사항).
  - cpplint는 켜되 clang-format과 충돌하는 필터(예: whitespace/braces)가 나오면 그때 끈다.
  - cppcheck는 이미지의 2.13이 ament의 "slow version"이라 `AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS` 없이는 스스로 건너뛴다(main.py 126행 확인). 켜지 않는다.
  - xmllint와 lint_cmake는 켠다. flake8과 pep257은 Python이 없어 대상이 없다.
  - clang-tidy는 lint.sh 계획대로 colcon 빌드의 compile_commands.json 뒤에 연결한다.
- 노드 구조 규약(6단계 이후 적용, 여기서는 헬퍼만): lifecycle 노드, 기체당 컴포넌트 컨테이너, `use_sim_time` true. idsim_common 헬퍼는 `NodeT` 템플릿이라 `rclcpp::Node`와 `LifecycleNode` 모두 받는다(원형 컴파일 확인).

## Q6 4단계에서 정하지 않고 넘길 것

- 6단계(px4-engineer, ros2): Offboard 신선도와 timestamp=0의 실제 동작 확인, DO_SET_MODE 값과 SET_NAV_STATE 중 어느 쪽을 쓸지, source_system/component 값 표, params 파일 키 이름(`vehicle.ns`, `vehicle.sysid`)과 생성기 출력(devops), 컴포넌트 컨테이너 구성(ops-service와 함께).
- 1b(sim, px4, ros2): 월드 ENU <-> 기체 로컬 NED 원점 오프셋(스폰 pose 또는 ref_lat/lon/alt). idsim_common 4단계는 축 변환만 하고 원점 이동은 다루지 않는다. TargetState -> setpoint 변환 함수의 위치.
- logging-engineer: `/fmu/out` timestamp가 에이전트 epoch 기준이라는 사실의 기록과 ULog 정렬 방법.
- test-engineer: Python 쪽 토픽 이름 규칙(rclpy `MESSAGE_VERSION` 쌍둥이를 tests/support에 둘지, 정규식을 유지할지). 골든 테스트의 실패 메시지 형식.
- devops: clang-format 버전 고정 방식, lint.sh의 "fmu 문자열 금지" 검사, idsim_common을 CI unit 잡에서 colcon test로 돌리는 방법(저장소 루트 경로 전달).
- 7단계 interface.md: 위 QoS 표, 좌표계, timestamp 기준, sysid 대조 규칙.

## architect 결정 요청 쟁점

1. frame_transforms를 래핑하지 않고 직접 구현하며 px4_ros_com은 test_depend oracle로만 둔다(로드맵 "래핑, 안 맞으면 직접"의 "안 맞음" 판정. 근거: 공분산 3x3 오류, 템플릿 링크 불가, yaw 없음, NaN 번짐). roadmap과 architecture 문구 갱신 여부.
2. 공개 매핑 API를 smoke 문서의 `px4_topic<T>(ns, dir, base)` 대신 기술자 목록(`topics::VehicleStatus`)으로 바꾸고 문자열 함수는 detail로 내린다. smoke-test-phase1a.md 문구 갱신.
3. 골든 테스트에 "규칙 전수 검사(테스트 내 타입 목록, 골든에 모르는 타입이 있으면 FAIL)"를 더하고, 매핑 목록은 부분집합 검사로 둔다.
4. 구독과 발행 QoS 모두 BE/VOLATILE/KEEP_LAST/5(SensorDataQoS와 같은 값)로 하고 구독 TL은 쓰지 않는다.
5. `/fmu/in` 메시지 timestamp는 0(PX4가 수신 시각으로 찍음)을 규약으로 할지. 6단계에서 반증한다.
6. sysid는 idsim_common에 N+1 공식으로 두지 않고 params 파일로 받아 vehicle_status.system_id와 대조한다. 불일치면 activate 실패.
7. VehicleNamespace가 `/px4_N` 형태까지 강제할지, ROS 네임스페이스 형식만 검증할지.
8. 프로젝트 C++ 표준 17(권고) 또는 20.
9. clang-format 스타일 = ament_clang_format 설정 그대로, ament_lint_auto에서 uncrustify와 copyright를 끄고 cppcheck는 쓰지 않는다. copyright를 끄는 건 라이선스 미정(사용자 결정 사항)과 묶인다.
10. idsim_common을 SHARED 라이브러리와 템플릿 헤더로 둔다(헤더 전용 아님).
11. `/fmu/out` timestamp가 에이전트 epoch라는 사실을 interface.md의 시간 기준 절에 적을지.
