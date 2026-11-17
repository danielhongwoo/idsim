# idsim 로드맵

이 문서는 Phase별 작업 항목, 완료 기준, 리스크, 확장 방향을 정한다. 레이어 구조, 기술 스택, 기체 식별 규칙, 인터페이스 계약, Docker Compose 실행 환경, 테스트 전략은 [architecture.md](architecture.md)를 따른다.

## Phase 개요

| Phase | 목표 | 산출물 |
| --- | --- | --- |
| 1 | 단일 기체 환경과 미션 실행 | `docker/` 이미지 5종, 스모크 golden 파일, `config/fleet.yaml`과 생성 스크립트, CI lint/build/unit job, `idsim_common`, `idsim_interfaces`, `idsim_mission`, `idsim_sim`(월드 템플릿, 표적 어댑터, 정답 pose 노드), `/clock` bridge, 단일 기체 미션 통합 테스트, `docs/interface.md`, compose `viz` 프로필(Gazebo GUI, foxglove_bridge, Lichtblick) |
| 2 | 텔레메트리 수집 + 로그/리플레이 | `idsim_telemetry`, `idsim_logger`, WebSocket 페이지, `replay` 프로필, 기록물 인덱스 CLI, replay CI job |
| 3 | 멀티 기체 Fleet + Mission Planning | 3대 compose 생성, `idsim_fleet`, gRPC API, Rust 게이트웨이, 시나리오 runner, 3대 배분과 재배분 nightly 테스트 |

각 Phase는 앞 Phase의 완료 기준을 만족한 뒤 시작한다. Phase 1에서 만든 공통 라이브러리, 기체 식별 규칙, 인터페이스 계약이 이후 모든 Phase의 토대이므로, Phase 3에서 재사용이 안 되면 Phase 1 설계로 돌아간다. 인터페이스 계약은 정의를 Phase 1에서 전부 만들고, 고정은 첫 소비자가 생기는 Phase의 완료에 맞춘다. Phase 1 완료에 고정된 것은 공통 규칙, 미션 실행(`ExecuteMission`과 모든 항목), `TargetState`다. Phase 2 완료에 고정할 것은 `VehicleState`와 `MissionEvent`다. 묶음별 범위와 "고정"의 정의는 architecture.md의 인터페이스 계약 절에 있다. 가장 큰 리스크 두 가지(버전 조합, 컨테이너 간 DDS)는 Phase 1 안에서 닫았다.

## Phase 1: 단일 기체 환경과 미션 실행

목표: `tools/sim_stack.sh up` 한 번으로 Gazebo 안의 x500 한 대(`/px4_1`)가 YAML 미션 하나로 이륙, waypoint 순회, 이동 표적의 현재 위치로 접근, 복귀, 착륙을 수행하고, `runner`(ros-ws) 컨테이너 안의 pytest가 판정한다.

갖춘 것. 설계의 정본은 각 문서와 README에 있다.

- 환경 스모크 테스트와 이미지 5종, `docker/versions.env`: [smoke-test.md](smoke-test.md), `docker/README.md`
- CI 골격(lint, build, unit, sitl job), 테스트 구조: architecture.md "테스트 자동화와 CI"
- `config/fleet.yaml`과 `tools/gen_compose.py`(compose, `stack.json`, `runner`와 `viz` 프로필 생성): architecture.md "기체 식별과 설정의 단일 출처", "Docker Compose 실행 환경 설계"
- `idsim_common`(QoS 프로필, 토픽 이름 매핑, 좌표 변환, 공개 /fmu/in 목록): interface.md "PX4 토픽"
- `idsim_interfaces`와 계약 테스트: interface.md "변경 절차와 계약 테스트"
- `idsim_mission`(상태기, `ExecuteMission` action 서버, YAML 로더): interface.md "ExecuteMission", `ros_ws/src/idsim_mission/README.md`
- `idsim_sim`(월드 템플릿과 생성, 표적 어댑터, 정답 pose 노드): `ros_ws/src/idsim_sim/README.md`
- 시각 도구(`viz` 프로필의 Gazebo GUI, foxglove_bridge, Lichtblick): `docker/README.md`
- 단일 기체 미션 통합 테스트(시나리오 A, B, C, D, T와 비행 시나리오 F1-F4): `tests/sitl/README.md`

완료 기준: 통합 테스트가 headless로 로컬에서 3회 연속 통과하고 CI의 `sitl` job에서도 통과, Gazebo GUI로 비행을 눈으로 확인, 상태기 단위 테스트가 전이 전부를 덮음, `docs/interface.md` 완성과 Phase 1 범위의 계약 고정.

## Phase 2: 텔레메트리 수집 + 로그/리플레이

목표: 비행 한 회를 "기록물" 단위로 남기고, 그 기록물만으로 운용 서비스가 당시 상황을 그대로 다시 볼 수 있게 한다. 기록은 ROS 2 토픽(rosbag2/MCAP)과 PX4 내부 상태(ULog) 두 계열이고, 리플레이는 시뮬레이터 없이 rosbag만으로 운용 서비스를 돌리는 방식이다.

1. `idsim_telemetry` 수집기 (C++, lifecycle). `/px4_N/fmu/out/*` 중 운용에 필요한 토픽(vehicle_status, vehicle_local_position, vehicle_global_position, vehicle_land_detected, battery_status, failsafe_flags)을 구독해 `VehicleState`로 요약하고 5 Hz로 재발행(주기는 참고값이고 계약이 아니다). 식별 대조가 맞고 `vehicle_status`가 신선한 동안에만 발행하며, 다른 원천이 묵으면 발행을 멈추지 않고 해당 `*_valid`를 false로 한다. 신선도 검사와 발행 timer는 ROS 시각 기준이다. 기체 네임스페이스를 파라미터로 받아 Phase 3에서 N개 인스턴스로 띄울 수 있게. Executor와 같은 컴포넌트 컨테이너에 올린다.
2. WebSocket 발행 (Python, 임시). `VehicleState`를 JSON으로 뿌리는 어댑터와 브라우저에서 지도 위에 기체 위치를 찍는 최소 페이지 한 장. Phase 3의 Rust 게이트웨이가 같은 페이지를 gRPC 위에서 서빙하게 되면 이 어댑터는 개발용으로만 남긴다. 페이지의 WebSocket 메시지 형식은 Phase 3에서 바뀌지 않도록 여기서 JSON 스키마를 고정한다.
3. `idsim_logger` 기록 제어. 미션 시작/종료에 맞춰 rosbag2 기록을 MCAP 스토리지, `--use-sim-time`으로 자동 시작, 종료(서비스 호출 또는 rosbag2 API 직접 사용). 기록 대상은 네임스페이스별 선별 목록이며 `/<vehicle_id>/mission_event`를 포함하고 `/clock`은 제외. SITL 실행의 기록물에는 정답 pose(`/sim/` 토픽)도 넣는다(실기체 기록물에는 없다). 기록물 이름은 `<시각>_<미션 id>_<기체 id>`. 미션 id는 `MissionEvent`의 접수 사건에서야 알려지고 접수 사건은 기록기의 구독이 Executor와 맺어진 뒤에 나가야 기록물에 남으므로, 기록 시작, goal 전송, 기록물 이름 확정의 순서와 미션 id의 입력 경로는 이 작업의 착수 때 정한다. PX4가 남긴 ULog(`artifacts/runs/<실행 id>/px4-N/log/`. px4 작업 디렉터리 `rootfs/N`의 바인드 마운트)를 같은 디렉터리로 복사하고 시작 시각 오프셋을 메타데이터로 기록. 시뮬레이션에서는 오프셋이 0에 가깝지만 실기체 전환을 위해 필드를 둔다.
4. 리플레이 모드. compose 프로필 `replay`: 시뮬레이터, PX4, Agent 없이 `ros2 bag play --clock`으로 토픽을 재생하고, 수집기, WebSocket, (Phase 3의) Fleet Manager가 그대로 올라온다. 모든 노드가 `use_sim_time`을 따르므로 재생 속도를 바꿔도 동일하게 동작. `viz` 프로필을 함께 켜면 재생 토픽을 Lichtblick으로도 본다.
5. 기록물 인덱스. 기록물 디렉터리를 훑어 미션 id, 기체, 기간, 결과를 SQLite 한 개에 정리하는 CLI(`idsim-log ls / show / replay`, Python). 미션 id와 결과는 기록물의 `mission_event` 토픽에서 읽는다(action의 goal과 result는 기록되지 않는다). 실행 단위의 key는 (기체 id, goal id)이고, 종료 사건이 없는 접수는 결과 미상으로 둔다. 대규모 로깅 시스템의 축소판.
6. 검증. Phase 1 통합 테스트를 "라이브로 1회 실행 -> 기록 -> 리플레이로 같은 판정 통과"로 확장. SITL 기록물에 정답 pose가 있으므로 리플레이 판정은 waypoint 도달과 표적 접근의 정답 판정까지 덮고, 정답 pose가 없는 기록물에서는 계약 판정만 돈다. 이것은 시스템이 아니라 수집기와 판정 코드의 회귀 테스트이며, 시뮬레이터가 필요 없어 CI에서 수 초에 돈다. replay CI job을 이 단계에서 추가. CI `sitl` job의 실패 산출물에 MCAP 기록물을 더한다(Phase 1에는 recorder가 없어 ULog, compose logs, ros_log, 판정 trace만 올린다).

완료 기준: 기록물 하나를 Lichtblick(Foxglove 호환 오픈소스 뷰어)에서 열어 궤적과 상태 변화를 확인할 수 있고, `replay` 프로필로 올린 WebSocket 페이지에 같은 움직임이 다시 나오며, replay CI job이 모든 push에서 돈다. `VehicleState`(WebSocket JSON 스키마와 함께)와 `MissionEvent`의 계약을 고정한다.

함정은 QoS와 데이터량이다. PX4 토픽은 best-effort로 발행되므로 rosbag2가 기록할 때는 퍼블리셔 QoS를 자동으로 따라가지만, 재생 시 구독자가 reliable을 요구하면 받지 못하므로 수집기와 테스트는 라이브와 같은 sensor_data QoS를 써야 하고 필요하면 `--qos-profile-overrides-path`로 맞춘다. 또 PX4 토픽이 수백 Hz로 나와 기록 대상을 골라야 한다.

## Phase 3: 멀티 기체 Fleet + Mission Planning

목표: 기체 3대를 한 번에 띄우고, Fleet Manager가 기체 등록, 상태 집계, 미션 배분을 맡으며, gRPC 클라이언트 하나로 "표적 A는 1번 기체, 표적 B는 2번 기체"를 지시할 수 있게 한다. Phase 1-2 코드는 `config/fleet.yaml`의 기체 수만 바꿔 그대로 재사용되어야 한다. 안 되면 Phase 1 설계가 틀린 것이다.

1. 멀티 인스턴스 스폰. [PX4 멀티 기체 문서](https://docs.px4.io/main/en/ros2/multi_vehicle.html) 규칙대로 `px4 -d -i N`, `PX4_GZ_MODEL_POSE`로 간격 배치(기체 간격 4 m 이상. 생성 스크립트가 2 m 미만을 거부한다). 기체 번호, 네임스페이스, `UXRCE_DDS_KEY`, `MAV_SYS_ID`, 포트는 Phase 1의 파생 규칙을 그대로 따르므로 새 결정은 없다. `tools/gen_compose.py`가 3대 compose를 만든다.
2. 기체별 서비스 인스턴스. 기체당 컴포넌트 컨테이너 하나에 `idsim_mission`과 `idsim_telemetry`를 올려 3개 launch. 노드는 기체별 params(`stack.json`에서 생성)로 sysid를 받고 `idsim_common`의 대조 함수로 확인한다.
3. `idsim_fleet` Fleet Manager (C++). 기체 레지스트리(`VehicleState` 수신으로 등록, `/clock` 기준 미수신 timeout으로 이탈 감지. 구독 대상을 params의 기체 목록으로 정할지 그래프에서 찾을지는 Phase 3 착수 때 정한다. 어느 쪽이든 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다), 전체 기체 상태 집계, 미션 큐와 배분(가용 기체 중 표적에 가장 가까운 기체 선택 정도의 단순 규칙), 미션 상태 추적(대기 -> 배분 -> 실행 -> 완료/실패). gRPC 서버 스레드와 rclcpp executor라는 두 이벤트 루프가 공유하는 상태는 단일 뮤텍스로 보호하고, 설계 문서에 어떤 스레드가 어떤 상태를 쓰는지 표로 적는다.
4. gRPC API (`proto/fleet.proto`). `ListVehicles`, `StreamVehicleStates`(server streaming), `StreamMissionEvents`(server streaming), `SubmitMission`, `AbortMission`, `GetMissionStatus`. Protobuf `VehicleState`와 ROS msg의 변환은 `idsim_fleet` 변환 모듈 한 곳에서만 하고 왕복 단위 테스트를 둔다. Python 클라이언트 CLI로 호출.
5. 브라우저 게이트웨이 (`gateway/`, Rust). tonic으로 Fleet Manager의 두 스트림을 구독해 WebSocket으로 중계하고, 미션 제출과 중단을 HTTP JSON으로 받아 gRPC로 넘기며, Phase 2 페이지를 정적으로 서빙한다. ROS 2 비의존이므로 cargo만으로 빌드하고 단위 테스트는 gRPC 서버 목으로 한다. Phase 2에서 고정한 WebSocket JSON 스키마를 그대로 지킨다.
6. 시나리오 정의. `missions/scenario_*.yaml`에 기체 수, 초기 배치, 표적 Actor 경로, 미션 목록을 한 파일로. 시나리오 runner(Python)가 `config/fleet.yaml` 생성 -> compose 생성 -> `up --wait` -> 미션 제출 -> 기록 -> 판정까지 한 번에.
7. 검증. 시나리오 "3대, 표적 2개, 동시 배분"에서 두 미션이 서로 다른 기체에 배분되고 모두 완료되는지, 한 기체의 px4 컨테이너를 강제 종료했을 때 Fleet Manager가 이탈을 감지하고 미션을 다른 기체에 재배분하는지를 pytest로. 배분 규칙은 단위 테스트로 먼저 덮고, SITL 테스트는 nightly 전용.

완료 기준: 3대 시나리오가 headless로 nightly에서 통과하고, 재배분 테스트가 통과하며, 기록물 하나에 3대 모두의 토픽이 네임스페이스로 구분되어 들어 있다.

PC 한 대에서 Gazebo + PX4 3대 + 노드들을 돌리면 CPU가 부족할 수 있어 `PX4_SIM_SPEED_FACTOR`를 1 이하로 내리는 옵션을 처음부터 두는 게 좋다. 3대 시나리오의 CPU 측정은 `viz` 프로필 없이 한다.

## 리스크와 확장 방향

가장 큰 리스크는 버전 조합과 DDS 네트워크다. 둘 다 환경 스모크 테스트가 잡으므로 이미지, PX4 태그, DDS 설정을 바꾸면 스모크를 다시 돌린다.

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| PX4 릴리스 태그와 px4_msgs 브랜치 불일치 | 토픽은 보이나 디시리얼라이즈 실패, 조용히 드롭 | 둘을 같은 `release/1.17`로 `versions.env`에 고정하고 스모크 테스트에 양방향 메시지 수신 확인 포함 |
| PX4 메시지 버저닝으로 토픽 이름 변경 | 하드코딩한 토픽 이름이 특정 버전에서만 동작 | 토픽 이름은 `idsim_common` 매핑으로만 접근, 스모크 테스트의 golden 목록과 단위 테스트로 비교 |
| 모델 파일 불일치 | standalone 스폰이 조용히 실패 | 모델은 sim-base `/opt/px4-gz` 한 벌, 커밋은 `versions.env`로 고정하고 px4 빌드가 검사, `gz model --list`로 스폰 확인 |
| Jazzy + 24.04 + PX4 조합의 문서 부족 | 공식 예제가 Humble 기준이라 초기 시행착오 증가 | Phase 1 첫머리에 스모크 테스트를 두고, 막히면 `ros-ws`만 Humble 컨테이너로 내려 비교(DDS 도메인은 배포판 간에도 통함) |
| 컨테이너 간 DDS 데이터 미수신 | 토픽은 보이나 데이터가 안 오거나 간헐적으로 끊김 | rmw를 CycloneDDS로 고정해 공유 메모리 전송 경로를 없애고, `network_mode: host`, `config/cyclonedds.xml`에 유니캐스트 피어 명시(인터페이스는 고정하지 않음. Agent가 호스트 인터페이스 주소만 광고한다) |
| 같은 호스트의 스택 충돌 | 개발자 둘 또는 병렬 CI job이 서로의 토픽과 포트를 봄 | 생성 인자 k로 `ROS_DOMAIN_ID`, Agent 포트, MAVLink 포트 분리 |
| 스택 둘의 MAVLink 포트 충돌 | 오프셋이 없으면 스택 k가 달라도 같은 N의 PX4가 같은 로컬 포트(18570+N, 14580+N)에 bind해 두 번째 스택이 `bind failed` 경고를 내고(실측) GCS 14550도 공유된다 | PATH 앞의 idsim용 `px4-rc.mavlink`가 스택 오프셋 1000k를 적용하고, 스모크가 px4 로그에 `bind failed`가 없음을 판정한다. `MAV_SYS_ID`는 스택 간에 같아 외부 GCS 하나는 한 번에 한 스택만 본다는 제약을 `docs/interface.md`에 적는다 |
| 시작 순서 | gazebo 전에 px4가 스폰을 시도해 실패, 테스트 flaky | healthcheck + `depends_on` 조건 + `compose up --wait` |
| 시간 기준 불일치 | 라이브와 리플레이의 판정이 다름 | 정식 기준은 `/clock`, 기록은 `--use-sim-time`, `/clock` 미기록 |
| PC 성능 | 3대 시나리오에서 Gazebo 물리 스텝 드롭, PX4 타이밍 경고 | headless 기본, `PX4_SIM_SPEED_FACTOR` 조절, 카메라와 라이다 없는 기본 x500 모델 사용, 표적은 Actor |
| Offboard 모드 진입 실패 | 기체가 arm되지 않거나 바로 페일세이프 | setpoint를 20 Hz로, 모드 전환 전 최소 10회 발행, EKF 준비(`failsafe_flags`의 위치, 고도, home 무효 flag 넷이 모두 false) 뒤 Offboard, 그다음 arm, `COM_OBL_RC_ACT` 명시 |
| Offboard가 아닌 모드에서의 setpoint 발행 | 착륙 판정이 늦어지고 Hold가 끌린다. failsafe 뒤 발행을 재개하면 기체가 Offboard로 돌아간다 | Executor는 Offboard가 아닌 모드를 관측하면 setpoint 발행을 멈춘다(architecture.md의 발행 규칙) |
| MAVLink 포트 혼동 | GCS가 14540에 붙어 연결 안 됨, MAVSDK가 14550에 붙어 GCS 링크 점유 | GCS는 스택 안 공통 14550 + 1000k, 온보드 API는 14540 + 1000k + N으로 `docs/interface.md`에 고정하고 compose 환경변수로만 노출 |
| 스크립트 궤적 Actor의 pose가 서버 토픽에 없다 | gz-sim 8.15.0 실측. Actor 엔티티는 `/world/<월드>/pose/info` 목록에 없고 그 link pose는 0으로 고정되며 `PosePublisher`는 Actor에 붙지 않는다. Gazebo에서 표적 위치를 받아 변환할 수 없다 | 표적 어댑터가 fleet 파일의 궤적 정의에서 직접 계산한다. 궤적 정의의 유일한 출처는 fleet 파일의 `targets`이고 월드 SDF의 Actor는 같은 정의로 생성하는 화면 확인용이다. 소비자는 `TargetState`만 보므로 원천이 Gazebo가 아니어도 바뀌는 것이 없다 |
| Actor 월드에서 `dynamic_pose/info` 구독이 서버를 죽인다 | 실측. bridge 설정이나 `gz topic -e` 한 번으로 gazebo 서비스가 내려가고 lockstep 때문에 PX4가 멈춘다 | bridge는 `/clock` 하나만 bridge하고 정답 pose는 `pose/info`를 쓴다. 생성기 단위 테스트가 bridge 인자, compose, 생성된 월드 SDF, `gui.config`에 `dynamic_pose`가 없음을 검사하고, `idsim_sim` 단위 테스트가 정답 pose 노드의 구독 토픽을 같은 기준으로 검사한다. 운영 문서에 적는다 |
| Actor 월드에 `gz-gui`를 붙였을 때의 서버 생존은 확인한 조건에서만 성립한다 | `gui.config`에 plugin을 더하거나 Gazebo 버전이 바뀌면 `viz` 프로필이 서버를 죽일 수 있다 | gz-sim 8.15.0, gz-gui 8.4.0에서 고정한 `gui.config`로 GUI 연결, 재접속, Actor 렌더링(ogre2, ogre) 동안 서버가 살아 있었다(실측, 표적 4개까지). GUI 플러그인 .so에 `dynamic_pose` 문자열이 없다. `gui.config`의 plugin 목록을 고정하고 목록 밖의 plugin을 더하지 않는다. Gazebo 버전, plugin 목록, 표적 수를 이 조건 밖으로 바꾸면 수동 확인을 다시 한다 |
| 범위 문구와 표적 생산 경로의 어긋남 | 범위 문구가 "Gazebo 안의 엔티티"를 말하면 궤적 정의에서 계산하는 생산 경로와 어긋나고, 반대로 생산 경로가 Gazebo에 묶이면 실기체 추적기로 바꿀 자리가 흐려진다 | architecture.md의 "다루지 않는 것"이 표적을 fleet 파일의 스크립트 궤적을 따르는 점 표적으로 정하고, Gazebo 물리 상태를 따르는 생산자를 확장 항목으로 둔다. 생산자를 바꿔도 `TargetState`와 토픽은 그대로다 |
| 범위 확장 유혹 | 표적 추종 알고리즘, 예쁜 UI로 샘이 나감 | 표적은 스크립트 궤적을 따르는 점 표적으로, UI는 지도 위 점으로 고정. architecture.md의 "다루지 않는 것"을 기준으로 |

Phase 3 이후 확장 후보(우선순위 순): (1) 영상 스트리밍 - x500_gimbal 모델의 Gazebo 카메라 -> ros_gz_bridge -> GStreamer(appsrc -> x264enc -> webrtcbin)로 브라우저 재생. MIPI/V4L2 경험이 그대로 이어지는 영역. (2) Orin NX 같은 arm64 보드에서 노드만 돌리고 PC의 SITL과 네트워크로 연결(HITL에 가까운 구성). (3) 상태 저장과 OTA - Fleet Manager 상태를 SQLite/Postgres로, 노드 이미지 업데이트를 compose pull로 흉내 내기. (4) MQTT 텔레메트리 - WebSocket 대신/병행으로 Mosquitto에 발행. (5) Gazebo 기반 표적 생산자 - 서버 쪽에서 표적 model을 움직이거나 Actor 상태를 읽는 Gazebo system이 `TargetState`를 채운다. 반응형 기동처럼 Gazebo 물리 상태를 따르는 표적이 필요할 때이고, `TargetState`와 토픽은 그대로 두고 생산자만 바꾼다. (6) 미션 로직 고도화 - Nav2 또는 자체 경로 계획, 센서 융합. 이 단계부터는 플랫폼이 아니라 알고리즘 영역이다.

## 참고 자료

- [PX4 Multi-Vehicle Simulation with ROS 2](https://docs.px4.io/main/en/ros2/multi_vehicle.html) - 인스턴스, 네임스페이스, target_system 규칙
- [PX4 Multi-Vehicle Simulation with Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/multi_vehicle_simulation.html) - `-i`, `PX4_GZ_MODEL_POSE` 예제
- [PX4 #24159](https://github.com/PX4/PX4-Autopilot/issues/24159) - Jazzy + 24.04 초기 이슈 보고
