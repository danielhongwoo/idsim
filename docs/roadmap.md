# idsim 로드맵

2026-11-06, Daniel

이 문서는 Phase별 작업 항목, 완료 기준, 리스크, 확장 방향을 정한다. 레이어 구조, 기술 스택, 기체 식별 규칙, 인터페이스 계약, Docker Compose 실행 환경, 테스트 전략은 [architecture.md](architecture.md)를 따른다. 진행 상황(무엇이 끝났고 무엇이 진행 중인지)은 이 문서에 적지 않고 `docs-for-agent/progress.md`에 기록한다.

## Phase 개요

| Phase | 목표 | 산출물 |
| --- | --- | --- |
| 1a | 환경 검증, CI 골격, 공통 라이브러리, 이륙과 착륙 | `docker/` 이미지 4종, `config/fleet.yaml`과 생성 스크립트, CI lint/build/unit 잡, `idsim_common`, `idsim_interfaces`, 이륙-호버-착륙 Offboard 통합 테스트, `docs/interface.md` |
| 1b | 미션 시퀀스와 표적 추종 | `idsim_mission`, `idsim_sim`(월드, 표적 Actor, 표적 어댑터), 단일 기체 미션 통합 테스트 |
| 2 | 텔레메트리 수집 + 로그/리플레이 | `idsim_telemetry`, `idsim_logger`, WebSocket 페이지, `replay` 프로필, 기록물 인덱스 CLI, 리플레이 CI 잡 |
| 3 | 멀티 기체 Fleet + Mission Planning | 3대 compose 생성, `idsim_fleet`, gRPC API, Rust 게이트웨이, 시나리오 러너, 3대 배분과 재배분 nightly 테스트 |

각 Phase는 앞 Phase의 완료 기준을 만족한 뒤 시작한다. Phase 1a에서 만드는 공통 라이브러리, 기체 식별 규칙, 인터페이스 계약이 이후 모든 Phase의 토대이므로, Phase 3에서 재사용이 안 되면 Phase 1a 설계로 돌아간다. 가장 큰 리스크 두 가지(버전 조합, 컨테이너 간 DDS)는 Phase 1a 안에서 닫는다.

## Phase 1a: 환경 검증, CI 골격, 공통 라이브러리, 이륙과 착륙

목표: `docker compose up --wait` 한 번으로 Gazebo 안의 x500 한 대(`/px4_1`)가 Offboard로 이륙해 호버하고 착륙하며, 그 결과를 `ros-ws` 컨테이너 안의 pytest가 판정한다. 미션 시퀀스는 아직 없다.

1. 환경 스모크 테스트. `ros-base`/`sim-base`/`px4`/`ros-ws` 이미지 빌드. 먼저 `px4` 컨테이너 하나에서 `HEADLESS=1 make px4_sitl gz_x500`(PX4가 Gazebo를 직접 띄우는 모드)이 뜨고 `MicroXRCEAgent udp4 -p 8888`에 접속되며 CycloneDDS rmw의 `ros2 topic echo`로 `vehicle_status`가 찍히는 것까지. 그다음 `PX4_GZ_STANDALONE=1`로 Gazebo를 `gazebo` 컨테이너로 분리하고 `PX4_UXRCE_DDS_NS=px4_1`을 적용해 같은 결과가 나오는지 확인. 이때 `ros2 topic list` 결과를 저장해 토픽 이름의 버전 접미사 유무를 확정하고 PX4 태그(v1.16 또는 v1.17)를 고른다. Jazzy + 24.04 + Harmonic + PX4 릴리스 태그 + CycloneDDS 조합의 검증 지점.
2. CI 골격. `lint`(clang-format, clang-tidy, ament_lint, ruff, 문자 집합 검사)와 `build`(이미지 4종, GHCR 푸시, 레이어 캐시) 잡. `docker/versions.env`로 버전 고정. 이후 모든 항목은 PR로 들어간다.
3. `config/fleet.yaml`과 `tools/gen_compose.py`. 기체 1대짜리 레지스트리에서 compose 서비스, launch 파라미터, `ROS_DOMAIN_ID`와 포트 오프셋을 생성. healthcheck와 `depends_on` 순서 포함. `COM_OBL_ACT`를 비롯한 SITL 파라미터도 여기서 주입.
4. `idsim_common` (C++). PX4 구독용 QoS 프로필, PX4 버전별 토픽 이름 매핑, NED <-> ENU / FRD <-> FLU 변환(px4_ros_com `frame_transforms` 래핑), 기체 네임스페이스 해석과 `target_system` 매핑, `VehicleCommand` 빌더. GoogleTest 단위 테스트 포함.
5. `idsim_interfaces`. `VehicleState.msg`, `TargetState.msg`, `Mission.msg`(takeoff / goto / track_entity / loiter / rtl / land, setpoint 항목과 모드 명령 항목 구분), `ExecuteMission.action`.
6. 이륙-호버-착륙 노드와 통합 테스트. `idsim_mission`의 뼈대로서 Offboard 진입 절차(`OffboardControlMode`와 `TrajectorySetpoint`를 20 Hz로 지속 발행, 모드 전환 전 최소 10회, EKF 수렴 대기 후 arm), 고도 도달 판정, land 명령과 disarm 확인만 구현한다. lifecycle 노드. pytest fixture가 compose를 올리고 rclpy로 "목표 고도 도달", "착륙 후 disarm"을 `/clock` 기준 타임아웃으로 판정.
7. `docs/interface.md`. 토픽 이름과 QoS, 좌표계, 기체 식별 규칙, 포트, SITL 파라미터, 시간 기준을 정리하고 계약으로 고정.

완료 기준: 이륙-호버-착륙 통합 테스트가 headless로 로컬에서 3회 연속 통과하고 CI의 `sitl` 잡에서도 통과, QGroundControl로 같은 비행을 눈으로 확인, `docs/interface.md` 완성.

가장 시간이 드는 곳은 Offboard 진입 타이밍과 컨테이너 간 DDS 디스커버리다.

## Phase 1b: 미션 시퀀스와 표적 추종

목표: YAML 미션 하나로 x500이 이륙 -> 웨이포인트 순회 -> 이동 표적의 현재 위치로 접근 -> 복귀, 착륙을 수행하고, pytest가 판정한다.

1. `idsim_mission` 상태기. 미션 항목을 실행하는 상태기는 ROS에 의존하지 않는 순수 C++ 클래스로 만들고 시계와 입출력 포트를 주입한다. 노드는 그 클래스를 토픽에 연결하는 얇은 껍질이다. setpoint 항목은 Offboard로, rtl과 land는 PX4 모드 명령으로 처리하며 `nav_state`로 전이를 추적하고 Offboard 재진입을 다룬다. 실패 시 폴백은 `COM_OBL_ACT`와 일치시킨다. YAML 로더가 `Mission.msg`로 변환.
2. `idsim_sim`. 커스텀 Gazebo 월드(기본 월드 상속), 스크립트 궤적을 따르는 표적 Actor, ros_gz_bridge 설정, 표적 어댑터 노드(Gazebo pose -> `TargetState`, ENU 유지), 전체 launch 파일.
3. `track_entity` 항목. `TargetState`를 구독해 그 위치를 NED로 변환한 setpoint로 쓰는 단순 추종.
4. 통합 테스트. "각 웨이포인트 반경 1 m 이내 도달", "표적 접근 거리 임계 이내", "착륙 후 disarm"을 토픽으로 판정. 상태기 단위 테스트(GoogleTest, 시뮬레이터 없음)로 전이와 타임아웃을 먼저 덮는다.

완료 기준: 미션 통합 테스트가 headless로 로컬 3회 연속과 CI에서 통과, 상태기 단위 테스트가 전이 전부를 덮음.

## Phase 2: 텔레메트리 수집 + 로그/리플레이

목표: 비행 한 회를 "기록물" 단위로 남기고, 그 기록물만으로 운용 서비스가 당시 상황을 그대로 다시 볼 수 있게 한다. 기록은 ROS 2 토픽(rosbag2/MCAP)과 PX4 내부 상태(ULog) 두 계열이고, 리플레이는 시뮬레이터 없이 rosbag만으로 운용 서비스를 돌리는 방식이다.

1. `idsim_telemetry` 수집기 (C++, lifecycle). `/px4_N/fmu/out/*` 중 운용에 필요한 토픽(vehicle_status, vehicle_local_position, vehicle_global_position, battery_status, failsafe_flags)을 구독해 `VehicleState`로 요약하고 5 Hz로 재발행. 기체 네임스페이스를 파라미터로 받아 Phase 3에서 N개 인스턴스로 띄울 수 있게. Executor와 같은 컴포넌트 컨테이너에 올린다.
2. WebSocket 발행 (Python, 임시). `VehicleState`를 JSON으로 뿌리는 어댑터와 브라우저에서 지도 위에 기체 위치를 찍는 최소 페이지 한 장. Phase 3의 Rust 게이트웨이가 같은 페이지를 gRPC 위에서 서빙하게 되면 이 어댑터는 개발용으로만 남긴다. 페이지의 WebSocket 메시지 형식은 Phase 3에서 바뀌지 않도록 여기서 JSON 스키마를 고정한다.
3. `idsim_logger` 기록 제어. 미션 시작/종료에 맞춰 rosbag2 기록을 MCAP 스토리지, `--use-sim-time`으로 자동 시작, 종료(서비스 호출 또는 rosbag2 API 직접 사용). 기록 대상은 네임스페이스별 선별 목록이며 `/clock`은 제외. 기록물 이름은 `<시각>_<미션 id>_<기체 id>`. PX4가 남긴 ULog(`px4` 컨테이너의 `build/px4_sitl_default/rootfs/log/`, 볼륨으로 공유)를 같은 디렉터리로 복사하고 시작 시각 오프셋을 메타데이터로 기록. 시뮬레이션에서는 오프셋이 0에 가깝지만 실기체 전환을 위해 필드를 둔다.
4. 리플레이 모드. compose 프로필 `replay`: 시뮬레이터, PX4, 에이전트 없이 `ros2 bag play --clock`으로 토픽을 재생하고, 수집기, WebSocket, (Phase 3의) Fleet Manager가 그대로 올라온다. 모든 노드가 `use_sim_time`을 따르므로 재생 속도를 바꿔도 동일하게 동작.
5. 기록물 인덱스. 기록물 디렉터리를 훑어 미션 id, 기체, 기간, 결과를 SQLite 한 개에 정리하는 CLI(`idsim-log ls / show / replay`, Python). 대규모 로깅 시스템의 축소판.
6. 검증. Phase 1b 통합 테스트를 "라이브로 1회 실행 -> 기록 -> 리플레이로 같은 판정 통과"로 확장. 이것은 시스템이 아니라 수집기와 판정 코드의 회귀 테스트이며, 시뮬레이터가 필요 없어 CI에서 수 초에 돈다. 리플레이 CI 잡을 이 단계에서 추가.

완료 기준: 기록물 하나를 Foxglove에서 열어 궤적과 상태 변화를 확인할 수 있고, `replay` 프로필로 올린 WebSocket 페이지에 같은 움직임이 다시 나오며, 리플레이 CI 잡이 모든 push에서 돈다.

함정은 QoS와 데이터량이다. PX4 토픽은 best-effort로 발행되므로 rosbag2가 기록할 때는 퍼블리셔 QoS를 자동으로 따라가지만, 재생 시 구독자가 reliable을 요구하면 받지 못하므로 수집기와 테스트는 라이브와 같은 sensor_data QoS를 써야 하고 필요하면 `--qos-profile-overrides-path`로 맞춘다. 또 PX4 토픽이 수백 Hz로 나와 기록 대상을 골라야 한다.

## Phase 3: 멀티 기체 Fleet + Mission Planning

목표: 기체 3대를 한 번에 띄우고, Fleet Manager가 기체 등록, 상태 집계, 미션 배분을 맡으며, gRPC 클라이언트 하나로 "표적 A는 1번 기체, 표적 B는 2번 기체"를 지시할 수 있게 한다. Phase 1-2 코드는 `config/fleet.yaml`의 기체 수만 바꿔 그대로 재사용되어야 한다. 안 되면 Phase 1a 설계가 틀린 것이다.

1. 멀티 인스턴스 스폰. [PX4 멀티 기체 문서](https://docs.px4.io/main/en/ros2/multi_vehicle.html) 규칙대로 `px4 -i N`, `PX4_GZ_MODEL_POSE`로 간격 배치. 기체 번호, 네임스페이스, `UXRCE_DDS_KEY`, `MAV_SYS_ID`, 포트는 Phase 1a의 파생 규칙을 그대로 따르므로 새 결정은 없다. `tools/gen_compose.py`가 3대 compose를 만든다.
2. 기체별 서비스 인스턴스. 기체당 컴포넌트 컨테이너 하나에 `idsim_mission`과 `idsim_telemetry`를 올려 3개 launch. `target_system` 매핑은 `idsim_common`이 이미 처리한다.
3. `idsim_fleet` Fleet Manager (C++). 기체 레지스트리(`VehicleState` 수신 주기로 자동 발견, `/clock` 기준 타임아웃으로 이탈 감지), 전체 기체 상태 집계, 미션 큐와 배분(가용 기체 중 표적에 가장 가까운 기체 선택 정도의 단순 규칙), 미션 상태 추적(대기 -> 배분 -> 실행 -> 완료/실패). gRPC 서버 스레드와 rclcpp executor라는 두 이벤트 루프가 공유하는 상태는 단일 뮤텍스로 보호하고, 설계 문서에 어떤 스레드가 어떤 상태를 쓰는지 표로 적는다.
4. gRPC API (`proto/fleet.proto`). `ListVehicles`, `StreamVehicleStates`(server streaming), `StreamMissionEvents`(server streaming), `SubmitMission`, `AbortMission`, `GetMissionStatus`. Protobuf `VehicleState`와 ROS msg의 변환은 `idsim_fleet` 변환 모듈 한 곳에서만 하고 왕복 단위 테스트를 둔다. Python 클라이언트 CLI로 호출.
5. 브라우저 게이트웨이 (`gateway/`, Rust). tonic으로 Fleet Manager의 두 스트림을 구독해 WebSocket으로 중계하고, 미션 제출과 중단을 HTTP JSON으로 받아 gRPC로 넘기며, Phase 2 페이지를 정적으로 서빙한다. ROS 2 비의존이므로 cargo만으로 빌드하고 단위 테스트는 gRPC 서버 목으로 한다. Phase 2에서 고정한 WebSocket JSON 스키마를 그대로 지킨다.
6. 시나리오 정의. `missions/scenario_*.yaml`에 기체 수, 초기 배치, 표적 Actor 경로, 미션 목록을 한 파일로. 시나리오 러너(Python)가 `config/fleet.yaml` 생성 -> compose 생성 -> `up --wait` -> 미션 제출 -> 기록 -> 판정까지 한 번에.
7. 검증. 시나리오 "3대, 표적 2개, 동시 배분"에서 두 미션이 서로 다른 기체에 배분되고 모두 완료되는지, 한 기체의 px4 컨테이너를 강제 종료했을 때 Fleet Manager가 이탈을 감지하고 미션을 다른 기체에 재배분하는지를 pytest로. 배분 규칙은 단위 테스트로 먼저 덮고, SITL 테스트는 nightly 전용.

완료 기준: 3대 시나리오가 headless로 nightly에서 통과하고, 재배분 테스트가 통과하며, 기록물 하나에 3대 모두의 토픽이 네임스페이스로 구분되어 들어 있다.

PC 한 대에서 Gazebo + PX4 3대 + 노드들을 돌리면 CPU가 부족할 수 있어 `PX4_SIM_SPEED_FACTOR`를 1 이하로 내리는 옵션을 처음부터 두는 게 좋다.

## 리스크와 확장 방향

가장 큰 리스크는 버전 조합과 DDS 네트워크다. 둘 다 Phase 1a 첫 단계인 스모크 테스트에서 드러나므로 그 전에 설계를 더 하지 않는 게 맞다.

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| PX4 릴리스 태그와 px4_msgs 브랜치 불일치 | 토픽은 보이나 디시리얼라이즈 실패, 조용히 드롭 | 둘을 같은 `release/1.xx`로 `versions.env`에 고정하고 스모크 테스트에 메시지 수신 확인 포함 |
| PX4 메시지 버저닝으로 토픽 이름 변경 | 하드코딩한 토픽 이름이 특정 버전에서만 동작 | 토픽 이름은 `idsim_common` 매핑으로만 접근, 스모크 테스트에서 실제 목록 저장 |
| Jazzy + 24.04 + PX4 조합의 문서 부족 | 공식 예제가 Humble 기준이라 초기 시행착오 증가 | Phase 1a 첫머리에 스모크 테스트를 두고, 막히면 `ros-ws`만 Humble 컨테이너로 내려 비교(DDS 도메인은 배포판 간에도 통함) |
| 컨테이너 간 DDS 데이터 미수신 | 토픽은 보이나 데이터가 안 오거나 간헐적으로 끊김 | rmw를 CycloneDDS로 고정해 공유 메모리 전송 경로를 없애고, `network_mode: host`, 필요 시 `config/cyclonedds.xml`에 인터페이스와 유니캐스트 피어 명시 |
| 같은 호스트의 스택 충돌 | 개발자 둘 또는 병렬 CI 잡이 서로의 토픽과 포트를 봄 | `fleet.yaml` 스택 오프셋으로 `ROS_DOMAIN_ID`, 에이전트 포트, MAVLink 포트 분리 |
| 시작 순서 | gazebo 전에 px4가 스폰을 시도해 실패, 테스트 플래키 | healthcheck + `depends_on` 조건 + `compose up --wait` |
| 시간 기준 불일치 | 라이브와 리플레이의 판정이 다름 | 정식 기준은 `/clock`, 기록은 `--use-sim-time`, `/clock` 미기록 |
| PC 성능 | 3대 시나리오에서 Gazebo 물리 스텝 드롭, PX4 타이밍 경고 | headless 기본, `PX4_SIM_SPEED_FACTOR` 조절, 카메라와 라이다 없는 기본 x500 모델 사용, 표적은 Actor |
| Offboard 모드 진입 실패 | 기체가 arm되지 않거나 바로 페일세이프 | setpoint를 20 Hz로, 모드 전환 전 최소 10회 발행, EKF 수렴(`vehicle_local_position.xy_valid`) 대기 후 arm, `COM_OBL_ACT` 명시 |
| MAVLink 포트 혼동 | QGC가 14540에 붙어 연결 안 됨, MAVSDK가 14550에 붙어 GCS 링크 점유 | GCS는 14550 공통, 온보드 API는 14540+N으로 `docs/interface.md`에 고정하고 compose 환경변수로만 노출 |
| 범위 확장 유혹 | 표적 추종 알고리즘, 예쁜 UI로 샘이 나감 | 표적은 "pose를 따라가는 Actor"로, UI는 지도 위 점으로 고정. architecture.md의 "다루지 않는 것"을 기준으로 |

Phase 3 이후 확장 후보(우선순위 순): (1) 영상 스트리밍 - x500_gimbal 모델의 Gazebo 카메라 -> ros_gz_bridge -> GStreamer(appsrc -> x264enc -> webrtcbin)로 브라우저 재생. MIPI/V4L2 경험이 그대로 이어지는 영역. (2) arm64 호스트 지원 - 이미지를 multi-arch(amd64 + arm64)로 빌드해 Apple Silicon Mac을 개발 호스트로 쓰거나, Orin NX에서 노드만 돌리고 PC의 SITL과 네트워크로 연결(HITL에 가까운 구성). (3) 상태 저장과 OTA - Fleet Manager 상태를 SQLite/Postgres로, 노드 이미지 업데이트를 compose pull로 흉내 내기. (4) MQTT 텔레메트리 - WebSocket 대신/병행으로 Mosquitto에 발행. (5) 미션 로직 고도화 - Nav2 또는 자체 경로 계획, 센서 융합. 이 단계부터는 플랫폼이 아니라 알고리즘 영역이다.

## 참고 자료

- [PX4 Multi-Vehicle Simulation with ROS 2](https://docs.px4.io/main/en/ros2/multi_vehicle.html) - 인스턴스, 네임스페이스, target_system 규칙
- [PX4 Multi-Vehicle Simulation with Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/multi_vehicle_simulation.html) - `-i`, `PX4_GZ_MODEL_POSE` 예제
- [PX4 #24159](https://github.com/PX4/PX4-Autopilot/issues/24159) - Jazzy + 24.04 초기 이슈 보고
