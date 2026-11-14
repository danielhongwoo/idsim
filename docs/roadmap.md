# idsim 로드맵

이 문서는 Phase별 작업 항목, 완료 기준, 리스크, 확장 방향을 정한다. 레이어 구조, 기술 스택, 기체 식별 규칙, 인터페이스 계약, Docker Compose 실행 환경, 테스트 전략은 [architecture.md](architecture.md)를 따른다.

## Phase 개요

| Phase | 목표 | 산출물 |
| --- | --- | --- |
| 1a | 환경 검증, CI 골격, 공통 라이브러리, 이륙과 착륙 | `docker/` 이미지 5종, 스모크 golden 파일, `config/fleet.yaml`과 생성 스크립트, CI lint/build/unit job, `idsim_common`, `idsim_interfaces`, `/clock` 브리지, 이륙-호버-착륙 Offboard 통합 테스트, `docs/interface.md`, `tools/qgc.sh`와 compose `viz` 프로필(Gazebo GUI, foxglove_bridge, Lichtblick) |
| 1b | 미션 시퀀스와 표적 추종 | `idsim_mission`, `idsim_sim`(월드 템플릿, 표적 어댑터, 정답 pose 노드), 단일 기체 미션 통합 테스트 |
| 2 | 텔레메트리 수집 + 로그/리플레이 | `idsim_telemetry`, `idsim_logger`, WebSocket 페이지, `replay` 프로필, 기록물 인덱스 CLI, replay CI job |
| 3 | 멀티 기체 Fleet + Mission Planning | 3대 compose 생성, `idsim_fleet`, gRPC API, Rust 게이트웨이, 시나리오 runner, 3대 배분과 재배분 nightly 테스트 |

각 Phase는 앞 Phase의 완료 기준을 만족한 뒤 시작한다. Phase 1a에서 만드는 공통 라이브러리, 기체 식별 규칙, 인터페이스 계약이 이후 모든 Phase의 토대이므로, Phase 3에서 재사용이 안 되면 Phase 1a 설계로 돌아간다. 인터페이스 계약은 정의를 Phase 1a에서 전부 만들되, 고정은 첫 소비자가 생기는 Phase의 완료에 맞춰 나눈다. 1a 완료에 공통 규칙, `ExecuteMission`, TAKEOFF, LOITER, LAND 항목(공중에서 끝나는 미션의 종료 동작은 뺀다). 1b 완료에 `TargetState`, GOTO, TRACK_ENTITY, RTL 항목과 공중에서 끝나는 미션의 종료 동작. Phase 2 완료에 `VehicleState`와 `MissionEvent`. 묶음별 범위와 "고정"의 정의는 architecture.md의 인터페이스 계약 절에 있다. 가장 큰 리스크 두 가지(버전 조합, 컨테이너 간 DDS)는 Phase 1a 안에서 닫는다.

## Phase 1a: 환경 검증, CI 골격, 공통 라이브러리, 이륙과 착륙

목표: `tools/sim_stack.sh up` 한 번으로(안에서 `docker compose up --wait`를 단계로 나눠 모델 잔존을 검사하고 마지막 단계에서 운용 노드 `ops-N`을 올린다) Gazebo 안의 x500 한 대(`/px4_1`)가 Offboard로 이륙해 호버하고 착륙하며, 그 결과를 `runner`(ros-ws) 컨테이너 안의 pytest가 판정한다. 이 비행은 `[TAKEOFF, LOITER, LAND]` 미션 하나를 `ExecuteMission` action으로 보내 실행한다. YAML 미션 시퀀스와 나머지 항목(goto, track_entity, rtl)은 1b에서 만든다.

1. 환경 스모크 테스트. 설계는 [smoke-test.md](smoke-test.md)를 따른다. `ros-base`/`sim-base`/`px4`/`ros-ws`/`xrce-agent` 이미지와 `docker/versions.env`, 스모크 스크립트(`tests/smoke/`)를 만든다. 단계는 한 번에 한 변수만 바꾼다. images는 이미지 버전을 확인하고, embedded는 PX4가 Gazebo를 직접 띄우는 진단용 구성(`-i 1`, `PX4_UXRCE_DDS_NS=px4_1`)에서 Agent 접속과 CycloneDDS rmw의 `vehicle_status` 수신을 확인하고, px4-out은 `PX4_GZ_STANDALONE=1`로 Gazebo를 `gazebo` 컨테이너로 분리하고, px4-in은 `/fmu/in` 방향으로 arm과 disarm을 왕복하고, golden은 토픽 목록과 발행자 QoS를 `tests/fixtures/px4/<PX4_TAG>/`의 golden 파일과 비교하고, clock은 `ros-ws`의 ros_gz_bridge가 `gazebo`의 `/clock`을 받는지(gz-transport 와이어 호환) 확인한다. PX4 태그는 v1.17.0이고 태그를 올릴 때는 golden 통과가 조건이다. 스모크의 정규화와 수신 확인 코드는 `tests/support/`에 두어 6단계가 재사용한다. 인스턴스 0 구성은 스모크에 없다(생성 스크립트가 지원하지 않는다).
2. CI 골격. `lint`(clang-format, ruff, hadolint, actionlint, yamllint, shellcheck, 문자 집합 검사. clang-tidy와 ament_lint는 compile_commands.json과 ROS 헤더가 필요해 4번 작업의 `unit` job에 둔다)와 `build`(이미지 5종, GHCR 푸시, 레이어 캐시, key가 있으면 건너뜀) job. `docker/versions.env`로 버전 고정. 이후 모든 항목은 PR로 들어간다.

2b. 시각 도구 준비. 판정, 스모크, CI와 무관한 개발자용 화면이다. `tools/qgc.sh`(QGroundControl AppImage를 `docker/versions.env`에 고정한 버전과 sha256으로 내려받아 캐시하고 호스트에서 직접 실행한다. compose 서비스가 아니다. 종료는 TERM 뒤 유예를 두고 SIGKILL), sim-base에 `libqt5svg5` 추가(Gazebo GUI 아이콘 경고 제거), `idsim_sim`의 `gui.config`(WorldControl 플러그인을 뺀 Gazebo GUI 설정. 화면에서 실수로 월드를 일시정지하는 것을 막는다), `docker/README.md`의 실행 안내. Gazebo GUI는 sim-base 컨테이너에서 `gz sim -g`로 이미 떠 있는 `gazebo` 서버에 클라이언트만 붙인다(같은 `GZ_PARTITION`과 `GZ_IP`, `DISPLAY`, X11 소켓과 `XAUTHORITY` 읽기 전용 마운트). 완료 기준: 스모크 standalone 스택(px4-out 이후) 위에서 Gazebo GUI에 x500이 보이고 QGroundControl에 기체가 연결된다.

3. `config/fleet.yaml`과 `tools/gen_compose.py`. 기체 1대짜리 레지스트리(사람이 고르는 값만: 기체 번호, airframe, 초기 pose, 기체별 파라미터, 월드와 원점, 표적, 공통 파라미터 파일)에서 compose 서비스와 `stack.json`을 `artifacts/runs/<실행 id>/`에 생성. 스택 번호 k(0-9)는 생성 인자이며 `ROS_DOMAIN_ID`, `GZ_PARTITION`, Agent 포트, MAVLink 오프셋(1000k. px4 이미지가 PATH 앞에 두는 idsim용 `px4-rc.mavlink`가 읽는다)을 파생. healthcheck(Agent 포트의 16진수 계산, px4는 uxrce 연결 문자열만, gazebo는 scene/info와 wrapper의 준비 파일, bridge는 `start_interval`)와 `depends_on` 순서 포함. `COM_OBL_RC_ACT`를 비롯한 SITL 파라미터는 공통 env 파일과 기체별 항목으로 주입. 월드 원점은 생성 스크립트가 만든 월드 SDF의 `<spherical_coordinates>`로만 들어가고(gazebo 서비스의 wrapper(`idsim_sim`)는 그 요소가 정확히 하나인지만 검사한다), 적용 여부는 px4의 `sensor_gps` 좌표를 `stack.json`의 기체별 기대 GPS와 대조해 판정한다. 생성 스크립트는 ros-ws 컨테이너에서 실행(`tools/gen_compose.sh`)하고 단위 테스트와 golden(`tests/fixtures/gen_compose/`)과 `compose config`는 lint job에서 돈다. 스모크도 생성된 compose(프로젝트 `idsim-<k>`, 실행 디렉터리 `artifacts/runs/<실행 id>/smoke/`)로 돌고, px4-out, px4-in, golden, clock은 `bridge`까지 전체 스택을 올린다. 호스트 uid:gid `user` 매핑과 `rootfs/N` 바인드 마운트를 써서 `artifacts/`에 root 소유 파일이 생기지 않는다. 편의 스크립트 `tools/sim_stack.sh`(생성과 up/down/ps/logs 묶음. down 뒤 up, 모델 잔존 사전 검사, Agent bind 오류 보고)와 `tools/qgc.sh --stack k`(다른 k의 GCS 포트)도 여기에 든다. 판정 명령용 `runner` 서비스(프로필 `tools`, 상주하지 않고 `compose run`으로 쓴다)와 compose 프로필 `viz`도 여기서 생성한다. Gazebo GUI는 `viz` 프로필의 `gz-gui` 서비스(sim-base, `gz sim -g`, `gui.config`, `ipc: host`)이고, 6단계의 `foxglove`와 `lichtblick`이 같은 프로필에 들어간다. 어떤 본 스택 서비스도 `viz` 프로필의 서비스에 `depends_on`하지 않고, `run_smoke.sh`, 통합 테스트 wrapper, CI는 이 프로필을 켜지 않는다(`tools` 프로필은 판정 때만 켠다). 완료 기준: k = 0에서 images, px4-out, px4-in, golden, clock 통과(golden 단계의 `--check` 일치, px4-out에 `sensor_gps` 원점 판정과 모델 유일성 판정 포함), k = 1 스택을 동시에 올려 px4-out 통과(두 스택의 px4 로그 모두에 `WARN  [mavlink] bind failed` 없음), 생성기 단위 테스트와 golden과 `compose config`가 lint job에서 통과, `artifacts/runs/`에 호스트 사용자 소유가 아닌 파일 없음, 생성된 스택 위에서 `--profile viz`의 Gazebo GUI에 x500_1이 보임, `tools/qgc.sh --stack 1`로 k = 1 스택에 QGC 접속 확인(`qgc.sh`가 QGC 설정의 수신 포트를 14550 + 1000k로 맞춘다).
4. `idsim_common` (C++17). PX4 구독과 발행용 QoS 프로필, 토픽 이름 매핑(golden의 토픽 전부를 기술자 목록 하나에 둔다. key는 방향과 논리 이름, 타입은 기술자에 묶고 접미사는 `MESSAGE_VERSION`에서 컴파일 시점에 파생), NED <-> ENU / FRD <-> FLU 변환(직접 구현. px4_ros_com `frame_transforms`는 공분산 변환 오류와 NaN 번짐이 있어 래핑하지 않고 단위 테스트의 비교 기준으로만 쓴다), 기체 네임스페이스 검증과 sysid 대조 함수(값은 params로 받고 `vehicle_status`와 대조한다. 파생 공식을 코드에 두지 않는다), /fmu/in timestamp 타입(노드 시계의 시뮬레이션 시간만 받는다. 공통 SITL 파라미터에 `UXRCE_DDS_SYNCT=0`을 더해 PX4 timestamp와 `/clock`을 같은 축에 둔다), `VehicleCommand` 빌더. 위험한 /fmu/in 토픽의 발행은 공개 API에서 막고 1a 허용은 `offboard_control_mode`, `trajectory_setpoint`, `vehicle_command` 셋뿐이다(실수 방지 수준이며 보안 경계가 아니다). 공개 API 밖에서 /fmu/in에 쓰는 테스트 코드는 통합 테스트의 `tests/support/px4_raw.py`(시나리오 T의 `offboard_control_mode`와 비상 정리 전용 `vehicle_command`), 환경 스모크의 `tests/smoke/check_px4.py`(px4-in 단계의 arm과 disarm) 둘이다. `px4-api` lint는 앞의 하나(`px4_raw.py`)에 예외 없이 적용하고, `tests/smoke/`는 lint 범위 밖이다. GoogleTest 단위 테스트 포함. 매핑 테스트는 1단계 golden 파일과 양방향 집합 일치로 비교하며 golden 디렉터리가 없으면 실패한다. 빌드와 테스트의 진입점은 `tools/ros_ws.sh`(ros-ws 컨테이너에서 colcon build, colcon test, clang-tidy)이고 CI의 `unit` job이 같은 명령(`tools/ros_ws.sh ci`)을 돌린다.
5. `idsim_interfaces`. rosidl 전용 패키지. `VehicleState.msg`, `TargetState.msg`, `Mission.msg`, `MissionItem.msg`(takeoff / goto / track_entity / loiter / rtl / land. setpoint 항목과 모드 명령 항목의 구분은 type에서 파생)와 항목별 서브메시지(`TakeoffItem.msg`, `GoToItem.msg`, `TrackEntityItem.msg`, `LoiterItem.msg`, `YawSetpoint.msg`), `ExecuteMission.action`, `MissionEvent.msg`(미션 실행의 접수와 종료 기록. rosbag2가 action의 goal과 result를 기록하지 않아 둔다). 계약 테스트(type hash, 펼친 정의, 직접 정의 golden과 상수 검사)가 정의 변경을 PR에서 드러낸다. `tools/ros_ws.sh test`는 패키지마다 테스트 결과가 1건 이상인지 단정한다. 정의는 여기서 전부 만들고 고정 시점은 묶음별로 다르다.
6. 이륙-호버-착륙 노드와 통합 테스트. `idsim_mission`의 뼈대로서 Offboard 진입 절차(`OffboardControlMode`와 `TrajectorySetpoint`를 20 Hz로 지속 발행, 모드 전환 전 최소 10회, EKF 준비(`failsafe_flags`의 위치, 고도, home 무효 flag 넷이 모두 false) 뒤 Offboard 전환, 그다음 arm), 고도 도달 판정, land 명령과 disarm 확인만 구현한다. 노드는 `ExecuteMission` action 서버로 `[TAKEOFF, LOITER, LAND]` 미션과 `[LAND]` 한 항목 미션(공중 취소 뒤 내리기)을 받는다(검증, 수락 정책, 취소, 실패 사유, `MissionEvent` 발행 포함). goto, track_entity, rtl 항목이 든 미션과 마지막 항목이 LAND가 아닌 미션은 1b에서 정할 때까지 미션 무효로 끝낸다. 취소 의미(공중이면 Hold 확인 뒤 CANCELED)를 확정하기 위한 Hold 실험(failsafe 진행 중의 Hold 명령 동작, Hold 확인 타임아웃)을 여기서 하고, 결과를 7번에서 계약을 고정하기 전에 반영한다. 생성 스크립트가 `stack.json`의 기체 항목과 노드 params에 `vehicle_id`를 싣고, 노드는 goal의 `vehicle_id`를 자기 값과 대조한다. lifecycle 노드이고 기체별 `ops-N` 서비스의 컴포넌트 컨테이너에서 돌며 전이는 노드 자신이 건다. `bridge` 서비스(ros-ws + ros_gz_bridge)가 `/clock`만 브리지해 이 단계부터 모든 노드가 `use_sim_time`을 따른다. 호스트 wrapper `tests/sitl/run_sitl.sh`가 `tools/sim_stack.sh`로 스택을 올리고, `runner` 안의 pytest가 rclpy(`qos_profile_sensor_data`, 전용 스레드 executor)로 "목표 고도 도달", "착륙 후 disarm"을 `/clock` 기준 타임아웃으로, 상태 전이는 "최신 상태 N회 연속"으로 판정. 통합 테스트는 `MissionEvent`의 접수와 종료 사건도 확인하며, 구독이 발행자와 맺어진 것을 확인한 뒤에 goal을 보낸다. 시나리오는 B(무효 미션), C(`vehicle_id` 불일치), A(`[TAKEOFF 5 m, LOITER 5 s, LAND]`), D(공중 취소 뒤 `[LAND]`), T(묵은 timestamp의 Offboard 신호 판정. `UXRCE_DDS_SYNCT`의 회귀)를 한 스택에서 이 순서로 돈다. ros-ws 이미지에는 foxglove_bridge가 들어간다. Offboard 진입 디버깅용으로 `viz` 프로필에 `foxglove`(ros-ws + foxglove_bridge. 주소 127.0.0.1, 포트 8765 + k, 토픽 화이트리스트, clientPublish, services, parameters 기능을 빼 읽기 전용)와 `lichtblick`(Foxglove 호환 오픈소스 뷰어, 공식 이미지 digest 고정, 127.0.0.1의 18080 + k)을 더해 setpoint와 `vehicle_local_position`을 같은 플롯에 놓고 본다.
7. `docs/interface.md`. 토픽 이름과 QoS, 좌표계, 기체 식별 규칙, 포트, SITL 파라미터, 시간 기준, `idsim_interfaces` 정의별 계약 문장과 파일별 고정 시점 표를 정리한다. 여기서 계약으로 고정하는 것은 1a 완료 범위다: PX4 인터페이스(토픽 이름과 QoS, 포트, SITL 파라미터), 공통 규칙, `ExecuteMission`과 TAKEOFF, LOITER, LAND 항목의 의미, 수락 정책, 취소 의미(공중에서 끝나는 미션의 종료 동작은 1b 완료에 고정한다). `TargetState`, GOTO, TRACK_ENTITY, RTL 항목은 1b 완료에, `VehicleState`와 `MissionEvent`는 Phase 2 완료에 고정하며, 그때까지 이 문서에 "고정 전"으로 표시한다. 실측이나 소스로 확인하지 않은 경계 상황의 기체 동작은 "미확인"으로 표시하고 그때의 보수적 동작을 함께 적으며, 고정은 그 확인을 기다리지 않는다.

완료 기준: 이륙-호버-착륙 통합 테스트(시나리오 B, C, A, D, T 다섯)가 headless로 로컬에서 3회 연속 통과하고 CI의 `sitl` job에서도 통과, QGroundControl과 Gazebo GUI로 같은 비행을 눈으로 확인, `docs/interface.md` 완성과 1a 완료 범위의 계약 고정.

가장 시간이 드는 곳은 Offboard 진입 타이밍과 컨테이너 간 DDS 디스커버리다.

## Phase 1b: 미션 시퀀스와 표적 추종

목표: YAML 미션 하나로 x500이 이륙 -> 웨이포인트 순회 -> 이동 표적의 현재 위치로 접근 -> 복귀, 착륙을 수행하고, pytest가 판정한다.

1. `idsim_mission` 상태기. 미션 항목을 실행하는 상태기는 ROS에 의존하지 않는 순수 C++ 클래스로 만들고 시계와 입출력 포트를 주입한다. 노드는 그 클래스를 토픽에 연결하는 얇은 껍질이다. setpoint 항목은 Offboard로, rtl과 land는 PX4 모드 명령으로 처리하며 `nav_state`로 전이를 추적하고 Offboard 재진입을 다룬다. 실패 시 폴백은 `COM_OBL_RC_ACT`와 일치시킨다. YAML 로더가 `Mission.msg`로 변환. 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작을 정하고, 1a의 임시 제한(마지막 항목이 LAND, 첫 항목 제한)과 setpoint 항목으로 시작하는 공중 시작 미션(Offboard 재진입)을 다룬다.
2. `idsim_sim`과 월드 생성. 표적은 `config/fleet.yaml`에 적은 스크립트 궤적을 시뮬레이션 시간에 맞춰 따르는 점 표적이다. 궤적 정의의 유일한 출처는 fleet 파일의 `targets`이고, 표적 어댑터 노드(rclpy, 별도 compose 서비스 `targets`)가 그 정의를 노드 시계에서 평가해 `TargetState`(world ENU)로 발행한다. 표적 생산자는 `TargetState` 계약 뒤에서 교체할 수 있고, Gazebo의 물리 상태를 따라 움직이는 표적의 생산자는 확장 항목이다. 월드는 손으로 쓰는 템플릿 하나(PX4 기본 월드의 physics, scene, light, ground를 옮긴 것)에 생성기가 `world.origin`(`<spherical_coordinates>`)과 표적마다 같은 궤적 정의의 Actor를 넣어 실행 디렉터리에 만든다. Actor는 Gazebo GUI로 보는 화면 확인용이고 화면 위치는 참고용이다. 그래서 fleet 파일의 판을 2로 올리고 `world.file`을 `world.template`으로 바꾸며 `world.origin`을 필수로 한다. ros_gz_bridge는 1a 그대로 `/clock` 하나만 브리지하고 bridge 설정 파일을 두지 않는다. 판정용 정답 pose를 내는 `sim-oracle` 서비스(sim-base, Gazebo `pose/info`를 직접 구독해 기체 base_link pose를 `/sim/<vehicle_id>/pose`로 발행)도 여기서 만든다. 스모크의 원점 판정은 기체 1을 원점에서 떨어진 곳에 스폰해 위경도 변환의 축 반전까지 가려내고, 원점이 월드 SDF만으로 적용되는지를 확인한다. 기체 EKF 원점과 기대 스폰 위치의 차는 매 SITL 실행에 기록만 하고 판정 상수의 입력으로 쓰지 않는다. Lichtblick 3D 패널(ENU TF, 표적 마커)은 선택이다.
3. `track_entity` 항목. `TargetState`를 구독해 그 위치를 NED로 변환한 setpoint로 쓰는 단순 추종. 표적 표본이 신선하면 표적 속도를 같은 setpoint에 feedforward로 실어 일정 속도 표적에 대한 정상 지연을 없앤다.
4. 통합 테스트. "각 웨이포인트 반경 1 m 이내 도달", "표적 접근 거리 임계 이내", "착륙 후 disarm"을 토픽으로 판정. 도달과 표적 접근의 판정 입력은 Executor가 쓰는 EKF 위치가 아니라 SITL 전용 정답 pose(기체 base_link의 world 위치)다. 시험 미션의 `acceptance_radius_m`은 `1 m - b` 이하로 둔다. b는 도달 순간 정답 거리가 `acceptance_radius_m`을 넘는 양의 허용한계이고, 판정 반경 1 m를 바꾸지 않고 부팅 30회 이상의 보정 실행에서 정한다. 표적 접근 임계값은 `1 m + v x L`(v는 시나리오 표적 속도의 최댓값, L은 표적 표본 나이 상한과 Executor tick과 여유를 더한 0.2 s)이다. 1b 목표의 미션은 합친 미션 하나(`[TAKEOFF, GOTO x N, TRACK_ENTITY, RTL]`)로 판정하고, 공중에서 끝나는 미션과 공중에서 시작하는 미션은 따로 둔 시나리오가 본다. 상태기 단위 테스트(GoogleTest, 시뮬레이터 없음)로 전이와 타임아웃을 먼저 덮는다.

완료 기준: 미션 통합 테스트가 headless로 로컬 3회 연속과 CI에서 통과, 상태기 단위 테스트가 전이 전부를 덮음, `TargetState`와 GOTO, TRACK_ENTITY, RTL 항목(`GoToItem`, `TrackEntityItem` 포함)의 계약 고정.

## Phase 2: 텔레메트리 수집 + 로그/리플레이

목표: 비행 한 회를 "기록물" 단위로 남기고, 그 기록물만으로 운용 서비스가 당시 상황을 그대로 다시 볼 수 있게 한다. 기록은 ROS 2 토픽(rosbag2/MCAP)과 PX4 내부 상태(ULog) 두 계열이고, 리플레이는 시뮬레이터 없이 rosbag만으로 운용 서비스를 돌리는 방식이다.

1. `idsim_telemetry` 수집기 (C++, lifecycle). `/px4_N/fmu/out/*` 중 운용에 필요한 토픽(vehicle_status, vehicle_local_position, vehicle_global_position, vehicle_land_detected, battery_status, failsafe_flags)을 구독해 `VehicleState`로 요약하고 5 Hz로 재발행(주기는 참고값이고 계약이 아니다). 식별 대조가 맞고 `vehicle_status`가 신선한 동안에만 발행하며, 다른 원천이 묵으면 발행을 멈추지 않고 해당 `*_valid`를 false로 한다. 신선도 검사와 발행 timer는 ROS 시각 기준이다. 기체 네임스페이스를 파라미터로 받아 Phase 3에서 N개 인스턴스로 띄울 수 있게. Executor와 같은 컴포넌트 컨테이너에 올린다.
2. WebSocket 발행 (Python, 임시). `VehicleState`를 JSON으로 뿌리는 어댑터와 브라우저에서 지도 위에 기체 위치를 찍는 최소 페이지 한 장. Phase 3의 Rust 게이트웨이가 같은 페이지를 gRPC 위에서 서빙하게 되면 이 어댑터는 개발용으로만 남긴다. 페이지의 WebSocket 메시지 형식은 Phase 3에서 바뀌지 않도록 여기서 JSON 스키마를 고정한다.
3. `idsim_logger` 기록 제어. 미션 시작/종료에 맞춰 rosbag2 기록을 MCAP 스토리지, `--use-sim-time`으로 자동 시작, 종료(서비스 호출 또는 rosbag2 API 직접 사용). 기록 대상은 네임스페이스별 선별 목록이며 `/<vehicle_id>/mission_event`를 포함하고 `/clock`은 제외. SITL 실행의 기록물에는 정답 pose(`/sim/` 토픽)도 넣는다(실기체 기록물에는 없다). 기록물 이름은 `<시각>_<미션 id>_<기체 id>`. 미션 id는 `MissionEvent`의 접수 사건에서야 알려지고 접수 사건은 기록기의 구독이 Executor와 맺어진 뒤에 나가야 기록물에 남으므로, 기록 시작, goal 전송, 기록물 이름 확정의 순서와 미션 id의 입력 경로는 이 작업의 착수 때 정한다. PX4가 남긴 ULog(`artifacts/runs/<실행 id>/px4-N/log/`. px4 작업 디렉터리 `rootfs/N`의 바인드 마운트)를 같은 디렉터리로 복사하고 시작 시각 오프셋을 메타데이터로 기록. 시뮬레이션에서는 오프셋이 0에 가깝지만 실기체 전환을 위해 필드를 둔다.
4. 리플레이 모드. compose 프로필 `replay`: 시뮬레이터, PX4, Agent 없이 `ros2 bag play --clock`으로 토픽을 재생하고, 수집기, WebSocket, (Phase 3의) Fleet Manager가 그대로 올라온다. 모든 노드가 `use_sim_time`을 따르므로 재생 속도를 바꿔도 동일하게 동작. `viz` 프로필을 함께 켜면 재생 토픽을 Lichtblick으로도 본다.
5. 기록물 인덱스. 기록물 디렉터리를 훑어 미션 id, 기체, 기간, 결과를 SQLite 한 개에 정리하는 CLI(`idsim-log ls / show / replay`, Python). 미션 id와 결과는 기록물의 `mission_event` 토픽에서 읽는다(action의 goal과 result는 기록되지 않는다). 실행 단위의 key는 (기체 id, goal id)이고, 종료 사건이 없는 접수는 결과 미상으로 둔다. 대규모 로깅 시스템의 축소판.
6. 검증. Phase 1b 통합 테스트를 "라이브로 1회 실행 -> 기록 -> 리플레이로 같은 판정 통과"로 확장. SITL 기록물에 정답 pose가 있으므로 리플레이 판정은 waypoint 도달과 표적 접근의 정답 판정까지 덮고, 정답 pose가 없는 기록물에서는 계약 판정만 돈다. 이것은 시스템이 아니라 수집기와 판정 코드의 회귀 테스트이며, 시뮬레이터가 필요 없어 CI에서 수 초에 돈다. replay CI job을 이 단계에서 추가. CI `sitl` job의 실패 산출물에 MCAP 기록물을 더한다(1a에는 recorder가 없어 ULog, compose logs, ros_log, 판정 trace만 올린다).

완료 기준: 기록물 하나를 Lichtblick(Foxglove 호환 오픈소스 뷰어)에서 열어 궤적과 상태 변화를 확인할 수 있고, `replay` 프로필로 올린 WebSocket 페이지에 같은 움직임이 다시 나오며, replay CI job이 모든 push에서 돈다. `VehicleState`(WebSocket JSON 스키마와 함께)와 `MissionEvent`의 계약을 고정한다.

함정은 QoS와 데이터량이다. PX4 토픽은 best-effort로 발행되므로 rosbag2가 기록할 때는 퍼블리셔 QoS를 자동으로 따라가지만, 재생 시 구독자가 reliable을 요구하면 받지 못하므로 수집기와 테스트는 라이브와 같은 sensor_data QoS를 써야 하고 필요하면 `--qos-profile-overrides-path`로 맞춘다. 또 PX4 토픽이 수백 Hz로 나와 기록 대상을 골라야 한다.

## Phase 3: 멀티 기체 Fleet + Mission Planning

목표: 기체 3대를 한 번에 띄우고, Fleet Manager가 기체 등록, 상태 집계, 미션 배분을 맡으며, gRPC 클라이언트 하나로 "표적 A는 1번 기체, 표적 B는 2번 기체"를 지시할 수 있게 한다. Phase 1-2 코드는 `config/fleet.yaml`의 기체 수만 바꿔 그대로 재사용되어야 한다. 안 되면 Phase 1a 설계가 틀린 것이다.

1. 멀티 인스턴스 스폰. [PX4 멀티 기체 문서](https://docs.px4.io/main/en/ros2/multi_vehicle.html) 규칙대로 `px4 -d -i N`, `PX4_GZ_MODEL_POSE`로 간격 배치(기체 간격 4 m 이상. 생성 스크립트가 2 m 미만을 거부한다). 기체 번호, 네임스페이스, `UXRCE_DDS_KEY`, `MAV_SYS_ID`, 포트는 Phase 1a의 파생 규칙을 그대로 따르므로 새 결정은 없다. `tools/gen_compose.py`가 3대 compose를 만든다.
2. 기체별 서비스 인스턴스. 기체당 컴포넌트 컨테이너 하나에 `idsim_mission`과 `idsim_telemetry`를 올려 3개 launch. 노드는 기체별 params(`stack.json`에서 생성)로 sysid를 받고 `idsim_common`의 대조 함수로 확인한다.
3. `idsim_fleet` Fleet Manager (C++). 기체 레지스트리(`VehicleState` 수신으로 등록, `/clock` 기준 미수신 타임아웃으로 이탈 감지. 구독 대상을 params의 기체 목록으로 정할지 그래프에서 찾을지는 Phase 3 착수 때 정한다. 어느 쪽이든 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다), 전체 기체 상태 집계, 미션 큐와 배분(가용 기체 중 표적에 가장 가까운 기체 선택 정도의 단순 규칙), 미션 상태 추적(대기 -> 배분 -> 실행 -> 완료/실패). gRPC 서버 스레드와 rclcpp executor라는 두 이벤트 루프가 공유하는 상태는 단일 뮤텍스로 보호하고, 설계 문서에 어떤 스레드가 어떤 상태를 쓰는지 표로 적는다.
4. gRPC API (`proto/fleet.proto`). `ListVehicles`, `StreamVehicleStates`(server streaming), `StreamMissionEvents`(server streaming), `SubmitMission`, `AbortMission`, `GetMissionStatus`. Protobuf `VehicleState`와 ROS msg의 변환은 `idsim_fleet` 변환 모듈 한 곳에서만 하고 왕복 단위 테스트를 둔다. Python 클라이언트 CLI로 호출.
5. 브라우저 게이트웨이 (`gateway/`, Rust). tonic으로 Fleet Manager의 두 스트림을 구독해 WebSocket으로 중계하고, 미션 제출과 중단을 HTTP JSON으로 받아 gRPC로 넘기며, Phase 2 페이지를 정적으로 서빙한다. ROS 2 비의존이므로 cargo만으로 빌드하고 단위 테스트는 gRPC 서버 목으로 한다. Phase 2에서 고정한 WebSocket JSON 스키마를 그대로 지킨다.
6. 시나리오 정의. `missions/scenario_*.yaml`에 기체 수, 초기 배치, 표적 Actor 경로, 미션 목록을 한 파일로. 시나리오 runner(Python)가 `config/fleet.yaml` 생성 -> compose 생성 -> `up --wait` -> 미션 제출 -> 기록 -> 판정까지 한 번에.
7. 검증. 시나리오 "3대, 표적 2개, 동시 배분"에서 두 미션이 서로 다른 기체에 배분되고 모두 완료되는지, 한 기체의 px4 컨테이너를 강제 종료했을 때 Fleet Manager가 이탈을 감지하고 미션을 다른 기체에 재배분하는지를 pytest로. 배분 규칙은 단위 테스트로 먼저 덮고, SITL 테스트는 nightly 전용. QGroundControl에 3대가 `MAV_SYS_ID`로 구분되어 모두 표시되는지는 확인 항목이며 판정에는 넣지 않는다.

완료 기준: 3대 시나리오가 headless로 nightly에서 통과하고, 재배분 테스트가 통과하며, 기록물 하나에 3대 모두의 토픽이 네임스페이스로 구분되어 들어 있다.

PC 한 대에서 Gazebo + PX4 3대 + 노드들을 돌리면 CPU가 부족할 수 있어 `PX4_SIM_SPEED_FACTOR`를 1 이하로 내리는 옵션을 처음부터 두는 게 좋다. 3대 시나리오의 CPU 측정은 `viz` 프로필 없이 한다.

## 리스크와 확장 방향

가장 큰 리스크는 버전 조합과 DDS 네트워크다. 둘 다 환경 스모크 테스트가 잡으므로 이미지, PX4 태그, DDS 설정을 바꾸면 스모크를 다시 돌린다.

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| PX4 릴리스 태그와 px4_msgs 브랜치 불일치 | 토픽은 보이나 디시리얼라이즈 실패, 조용히 드롭 | 둘을 같은 `release/1.17`로 `versions.env`에 고정하고 스모크 테스트에 양방향 메시지 수신 확인 포함 |
| PX4 메시지 버저닝으로 토픽 이름 변경 | 하드코딩한 토픽 이름이 특정 버전에서만 동작 | 토픽 이름은 `idsim_common` 매핑으로만 접근, 스모크 테스트의 golden 목록과 단위 테스트로 비교 |
| 모델 파일 불일치 | standalone 스폰이 조용히 실패 | 모델은 sim-base `/opt/px4-gz` 한 벌, 커밋은 `versions.env`로 고정하고 px4 빌드가 검사, `gz model --list`로 스폰 확인 |
| Jazzy + 24.04 + PX4 조합의 문서 부족 | 공식 예제가 Humble 기준이라 초기 시행착오 증가 | Phase 1a 첫머리에 스모크 테스트를 두고, 막히면 `ros-ws`만 Humble 컨테이너로 내려 비교(DDS 도메인은 배포판 간에도 통함) |
| 컨테이너 간 DDS 데이터 미수신 | 토픽은 보이나 데이터가 안 오거나 간헐적으로 끊김 | rmw를 CycloneDDS로 고정해 공유 메모리 전송 경로를 없애고, `network_mode: host`, `config/cyclonedds.xml`에 유니캐스트 피어 명시(인터페이스는 고정하지 않음. Agent가 호스트 인터페이스 주소만 광고한다) |
| 같은 호스트의 스택 충돌 | 개발자 둘 또는 병렬 CI job이 서로의 토픽과 포트를 봄 | 생성 인자 k로 `ROS_DOMAIN_ID`, Agent 포트, MAVLink 포트 분리 |
| 스택 둘의 MAVLink 포트 충돌 | 오프셋이 없으면 스택 k가 달라도 같은 N의 PX4가 같은 로컬 포트(18570+N, 14580+N)에 bind해 두 번째 스택이 `bind failed` 경고를 내고(실측) GCS 14550도 공유된다 | PATH 앞의 idsim용 `px4-rc.mavlink`가 스택 오프셋 1000k를 적용하고, 스모크가 px4 로그에 `bind failed`가 없음을 판정한다. `MAV_SYS_ID`는 스택 간에 같아 QGC 하나는 한 번에 한 스택만 본다는 제약을 `docs/interface.md`에 적는다 |
| 시작 순서 | gazebo 전에 px4가 스폰을 시도해 실패, 테스트 flaky | healthcheck + `depends_on` 조건 + `compose up --wait` |
| 시간 기준 불일치 | 라이브와 리플레이의 판정이 다름 | 정식 기준은 `/clock`, 기록은 `--use-sim-time`, `/clock` 미기록 |
| PC 성능 | 3대 시나리오에서 Gazebo 물리 스텝 드롭, PX4 타이밍 경고 | headless 기본, `PX4_SIM_SPEED_FACTOR` 조절, 카메라와 라이다 없는 기본 x500 모델 사용, 표적은 Actor |
| Offboard 모드 진입 실패 | 기체가 arm되지 않거나 바로 페일세이프 | setpoint를 20 Hz로, 모드 전환 전 최소 10회 발행, EKF 준비(`failsafe_flags`의 위치, 고도, home 무효 flag 넷이 모두 false) 뒤 Offboard, 그다음 arm, `COM_OBL_RC_ACT` 명시 |
| Offboard가 아닌 모드에서의 setpoint 발행 | 착륙 판정이 늦어지고 Hold가 끌린다. failsafe 뒤 발행을 재개하면 기체가 Offboard로 돌아간다 | Executor는 Offboard가 아닌 모드를 관측하면 setpoint 발행을 멈춘다(architecture.md의 발행 규칙) |
| MAVLink 포트 혼동 | QGC가 14540에 붙어 연결 안 됨, MAVSDK가 14550에 붙어 GCS 링크 점유 | GCS는 스택 안 공통 14550 + 1000k, 온보드 API는 14540 + 1000k + N으로 `docs/interface.md`에 고정하고 compose 환경변수로만 노출 |
| 스크립트 궤적 Actor의 pose가 서버 토픽에 없다 | gz-sim 8.15.0 실측. Actor 엔티티는 `/world/<월드>/pose/info` 목록에 없고 그 link pose는 0으로 고정되며 `PosePublisher`는 Actor에 붙지 않는다. Gazebo에서 표적 위치를 받아 변환할 수 없다 | 표적 어댑터가 fleet 파일의 궤적 정의에서 직접 계산한다. 궤적 정의의 유일한 출처는 fleet 파일의 `targets`이고 월드 SDF의 Actor는 같은 정의로 생성하는 화면 확인용이다. 소비자는 `TargetState`만 보므로 원천이 Gazebo가 아니어도 바뀌는 것이 없다 |
| Actor 월드에서 `dynamic_pose/info` 구독이 서버를 죽인다 | 실측. bridge 설정이나 `gz topic -e` 한 번으로 gazebo 서비스가 내려가고 lockstep 때문에 PX4가 멈춘다 | bridge는 `/clock` 하나만 브리지하고 정답 pose는 `pose/info`를 쓴다. 생성기 단위 테스트가 bridge 인자, compose, 생성된 월드 SDF, `gui.config`에 `dynamic_pose`가 없음을 검사하고, `idsim_sim` 단위 테스트가 정답 pose 노드의 구독 토픽을 같은 기준으로 검사한다. 운영 문서에 적는다 |
| Actor 월드에 `gz-gui`를 붙였을 때의 서버 생존은 미확인 | `viz` 프로필이 서버를 죽일 수 있다 | GUI 플러그인 .so에 `dynamic_pose` 문자열이 없고 GUI가 쓰는 state 경로는 안전했다(실측). 실제 GUI 연결과 Actor 렌더링은 1b의 `viz` 확인 항목이다 |
| 범위 문구와 표적 생산 경로의 어긋남 | 범위 문구가 "Gazebo 안의 엔티티"를 말하면 궤적 정의에서 계산하는 생산 경로와 어긋나고, 반대로 생산 경로가 Gazebo에 묶이면 실기체 추적기로 바꿀 자리가 흐려진다 | architecture.md의 "다루지 않는 것"이 표적을 fleet 파일의 스크립트 궤적을 따르는 점 표적으로 정하고, Gazebo 물리 상태를 따르는 생산자를 확장 항목으로 둔다. 생산자를 바꿔도 `TargetState`와 토픽은 그대로다 |
| 범위 확장 유혹 | 표적 추종 알고리즘, 예쁜 UI로 샘이 나감 | 표적은 스크립트 궤적을 따르는 점 표적으로, UI는 지도 위 점으로 고정. architecture.md의 "다루지 않는 것"을 기준으로 |

Phase 3 이후 확장 후보(우선순위 순): (1) 영상 스트리밍 - x500_gimbal 모델의 Gazebo 카메라 -> ros_gz_bridge -> GStreamer(appsrc -> x264enc -> webrtcbin)로 브라우저 재생. MIPI/V4L2 경험이 그대로 이어지는 영역. (2) arm64 호스트 지원 - 이미지를 multi-arch(amd64 + arm64)로 빌드해 Apple Silicon Mac을 개발 호스트로 쓰거나, Orin NX에서 노드만 돌리고 PC의 SITL과 네트워크로 연결(HITL에 가까운 구성). (3) 상태 저장과 OTA - Fleet Manager 상태를 SQLite/Postgres로, 노드 이미지 업데이트를 compose pull로 흉내 내기. (4) MQTT 텔레메트리 - WebSocket 대신/병행으로 Mosquitto에 발행. (5) Gazebo 기반 표적 생산자 - 서버 쪽에서 표적 model을 움직이거나 Actor 상태를 읽는 Gazebo system이 `TargetState`를 채운다. 반응형 기동처럼 Gazebo 물리 상태를 따르는 표적이 필요할 때이고, `TargetState`와 토픽은 그대로 두고 생산자만 바꾼다. (6) 미션 로직 고도화 - Nav2 또는 자체 경로 계획, 센서 융합. 이 단계부터는 플랫폼이 아니라 알고리즘 영역이다.

## 참고 자료

- [PX4 Multi-Vehicle Simulation with ROS 2](https://docs.px4.io/main/en/ros2/multi_vehicle.html) - 인스턴스, 네임스페이스, target_system 규칙
- [PX4 Multi-Vehicle Simulation with Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/multi_vehicle_simulation.html) - `-i`, `PX4_GZ_MODEL_POSE` 예제
- [PX4 #24159](https://github.com/PX4/PX4-Autopilot/issues/24159) - Jazzy + 24.04 초기 이슈 보고
