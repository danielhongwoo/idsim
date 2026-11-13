# 환경 스모크 테스트 설계

이 문서는 환경 스모크 테스트의 설계다. 스모크는 이미지, PX4 파라미터, PX4 태그가 바뀔 때마다 돌리는 회귀 검사이며, 이 문서는 golden 파일 형식의 기준 문서다. 목적은 Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic + PX4 v1.17.0 + uXRCE-DDS Agent v2.4.3 + CycloneDDS 조합이 컨테이너 구성에서 동작하는지 확인하고, 토픽 이름의 버전 접미사와 발행자 QoS 실측값을 golden 파일로 고정하는 것이다. 버전과 경로의 단일 출처는 `docker/versions.env`이며, 이 문서의 값은 그 파일을 설명한 것이다.

## 원칙

- 한 단계에서 한 변수만 바꾼다. 앞 단계가 실패하면 뒤 단계는 보지 않는다.
- px4-out, px4-in, golden, clock은 운영 스택과 같은 구성으로 올린다(standalone은 bridge 포함). 변수 분리는 스모크 단계가 아니라 기동 단계가 맡는다: `startup.stages`는 Agent와 gazebo, px4-N, bridge의 세 단계이고 `up --wait`가 어느 단계에서 실패했는지로 원인을 가른다. bridge는 px4-N이 healthy가 된 뒤에만 시작되므로 px4 실패와 bridge 실패는 섞이지 않는다. 스모크는 `tools/sim_stack.sh up --infra-only`로 올리므로 노드 단계의 운용 노드(`ops-N`)는 뜨지 않는다. 스모크는 PX4, Gazebo, DDS의 회귀 판정이고, px4-in의 arm과 disarm이 Executor와 같은 기체에 명령을 보내지 않게 한다.
- ROS 2 CLI는 항상 `--no-daemon`으로 실행한다. 데몬 캐시로 오판하지 않기 위함이다.
- 토픽 수신 판정은 "벽시계 T초 안에 1회 이상 수신, timestamp 필드가 0이 아님"으로 정의하고 주기에 묶지 않는다. 상태 전이는 에지가 아니라 "최신 상태가 N회 연속 유지"로 판정한다.
- echo와 판정 노드의 QoS는 `sensor_data` 프로필 하나로 통일한다. `reliable`로 echo해 수신 0을 확인하는 반증 실험은 진단 절차로만 쓴다.
- 스모크의 타임아웃은 예외적으로 벽시계를 쓴다. `/clock` 공급 자체가 clock 단계의 판정 대상이기 때문이다. 통합 테스트는 architecture.md대로 `/clock` 기준이다.

## 단계와 통과 기준

images 이미지 확인. `ros-ws`에서 `printenv RMW_IMPLEMENTATION`이 `rmw_cyclonedds_cpp`. `px4`에서 `gz sim --versions`가 `versions.env`의 `GZ_RELEASE`에 해당하는 major 버전, `command -v px4`가 `/opt/PX4-Autopilot/build/px4_sitl_default/bin/px4`를 가리키고 `etc/init.d-posix/rcS`가 있고, `/opt/px4-gz/models/x500/model.sdf`, `/opt/px4-gz/server.config`, `/opt/px4-gz/server.idsim.config`가 있다. `xrce-agent`에서 `MicroXRCEAgent --help`가 동작. 센서 높이 대조: `sim-base` 안에서 sdformat으로 읽은 x500 모델 `navsat_sensor`의 모델 기준 높이(센서는 base_link에 붙어 있다)가 생성기의 `tools/gen_compose.py --print-sensor-z 4001_gz_x500` 출력과 같다(차 1e-6 m 미만). 기대 GPS 고도에 들어가는 센서 높이의 출처가 생성기 상수와 모델 SDF 둘이라, `PX4_GZ_MODELS_REF`를 올릴 때 어긋나는 것을 여기서 잡는다. 월드 템플릿 대조: `sim-base`의 `/opt/px4-gz/worlds/default.sdf`와 월드 템플릿 `ros_ws/src/idsim_sim/worlds/idsim_base.sdf`의 월드 직속 요소가 순서까지 같다(주석, 공백, BOM은 무시하고 원본의 `<spherical_coordinates>`와 `<world>`의 `name`만 뺀다. 원본에 월드 직속 `<plugin>`, `<include>`, `<actor>`가 있으면 따로 실패한다). 템플릿은 그 원본의 사본이라 `PX4_GZ_MODELS_REF`를 올릴 때 낡는 것을 여기서 잡는다. 모든 이미지의 `dpkg -l | grep gz-transport` 결과를 artifacts에 남긴다.

embedded (진단용). PX4가 Gazebo를 컨테이너 안에서 직접 띄우는 구성으로, 운용 구성이 아니라 px4-out이 실패할 때 원인을 가르는 데 쓴다. `gen_compose --variant embedded`(gazebo 서비스 없음, px4-1에 `HEADLESS=1`, `PX4_GZ_STANDALONE` 없음)로 만든 compose로 실행하고 인스턴스는 `-i 1`, 네임스페이스는 `px4_1`이다. 통과: PX4 로그에 `Gazebo world is ready`, `px4-uxrce_dds_client status` 출력에 `Running, connected`(단어 `connected`만 찾으면 `disconnected`에도 걸리므로 두 단어 문자열로 찾는다), `ros2 topic list --no-daemon`에 `^/px4_1/fmu/out/vehicle_status(_v[0-9]+)?$`가 정확히 한 줄, `timeout 10 ros2 topic echo --once --qos-profile sensor_data`가 종료 코드 0이고 timestamp가 0이 아님, `ros2 topic info -v`에서 Publisher count 1, 타입 `px4_msgs/msg/VehicleStatus`, 수신한 `vehicle_status.system_id`가 2. `info -v` 출력은 artifacts에 남기고 QoS 값 판정은 하지 않는다. 값은 golden 단계가 golden 파일로 저장하고 단위 테스트가 비교한다. 예상값(BEST_EFFORT, TRANSIENT_LOCAL)은 [PX4 ROS 2 가이드](https://docs.px4.io/main/en/ros2/user_guide)의 QoS 설명을 따른 참고값이다.

px4-out standalone. Gazebo를 `gazebo` 서비스로 분리하고 `PX4_GZ_STANDALONE=1`. 통과: `gz model --list`에 `x500_1`, PX4 로그에 gz_bridge 오류 없음, embedded 판정 반복, `pxh commander check` 통과, `sensor_gps` 좌표가 `stack.json`의 `vehicles[0].expect_gps`와 일치(원점 판정. 기대값과 허용 오차는 "예외 사항과 가정" 절). 스폰 요청(`/world/<월드>/create`)의 결과를 PX4가 검사하지 않으므로(v1.17.0 `ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim`, standalone 분기) `gz model --list`가 스폰 성공의 유일한 증거다.

px4-in in 방향 왕복. `/px4_1/fmu/in/vehicle_command`로 arm(`target_system` 2) 발행. 통과: `vehicle_command_ack.result` 0, `vehicle_status.arming_state` 2가 3회 연속, 이어서 disarm 명령 후 1로 복귀. `ros2 topic list --no-daemon`에서 `^/px4_1/fmu/in/trajectory_setpoint(_v[0-9]+)?$`에 맞는 한 줄을 찾아 그 이름으로 `ros2 topic info -v`를 실행하면 Subscription count 1. 이 단계가 `px4_msgs` 정합성을 양방향으로 검증한다.

golden 기록. `tests/smoke/capture.sh`가 golden 파일과 원시 산출물을 만든다. 원시 산출물은 `ros2 topic list -t`, 토픽별 `info -v` 원문, 30초 `hz`, `pxh param show`, `pxh ver all`, compose logs, ULog.

clock /clock 판정. `bridge` 서비스(ros-ws의 ros_gz_bridge, vendor gz-transport)가 `gazebo` 서비스(OSRF gz-transport13)의 `/clock`을 ROS 2로 넘기며 이것이 노드들의 시간 기준이다. 이 단계가 양쪽 gz-transport(둘 다 13.6.0)의 와이어 호환을 확인하고 이미지 재빌드 때의 회귀를 잡는다. bridge healthcheck는 `/clock` 1회 수신만 보므로 여기서 품질을 본다. 통과: `ros2 topic info -v /clock`의 Publisher count가 정확히 1, `ros2 topic echo /clock`의 sim 시각이 증가. 양쪽 gz-transport 버전을 artifacts에 기록. 실패하면 `bridge`를 sim-base 계열 이미지(ros_gz 소스 빌드)로 바꾸는 대안으로 간다.

## 서비스별 환경변수

`gazebo` (sim-base, px4-out부터): `GZ_PARTITION=idsim-<k>`, `GZ_IP=127.0.0.1`, `GZ_SIM_SERVER_CONFIG_PATH=/opt/px4-gz/server.idsim.config`, `GZ_SIM_RESOURCE_PATH=/opt/px4-gz/models:/opt/px4-gz/worlds`, `IDSIM_WORLD_NAME=default`, `IDSIM_WORLD_FILE=/opt/idsim/world/default.sdf`. 월드 파일은 생성기가 월드 템플릿(`world.template`)에 `world.name`과 `<spherical_coordinates>`(`world.origin`, heading 0, ENU)를 넣어 실행 디렉터리의 `world/<월드>.sdf`로 만든 것이고, 그 디렉터리를 `/opt/idsim/world`에 읽기 전용으로 마운트한다. 명령은 `idsim_sim`의 wrapper `gz_server.sh`다. wrapper는 서버를 띄우기 전에 월드 파일의 `<world name>`이 `IDSIM_WORLD_NAME`과 같은지, `<spherical_coordinates>`가 정확히 하나인지 검사하고(아니면 종료 코드 1), `gz sim -r -s ${IDSIM_WORLD_FILE}`을 띄운 뒤 `/world/<월드>/scene/info`가 응답하면 준비 파일 `/tmp/idsim/ready`를 남긴다. 원점은 이 월드 SDF로만 들어가 월드가 로드될 때 적용된다. wrapper는 `set_spherical_coordinates`를 호출하지 않고 원점 표시 파일도 없다. 헤드리스는 `-s`(서버만)로 얻는다. 렌더링 엔진 플래그는 주지 않는다. x500 기본 월드에는 렌더링 센서가 없어 Sensors 시스템이 렌더 엔진을 초기화하지 않고, ogre 1.x는 X 디스플레이 없이 돌지 않는다(gz-rendering8 소스 확인). 나중에 카메라 센서를 쓰면 ogre2 + `--headless-rendering` + Mesa llvmpipe로 간다. `HEADLESS`와 `PX4_GZ_SIM_RENDER_ENGINE`은 PX4 rcS 전용 변수임이 소스로 확인되어 gazebo 서비스에는 주지 않는다. `server.idsim.config`는 sim-base가 PX4-gazebo-models 원본 `server.config`에서 PX4 전용 plugin 두 줄(`libOpticalFlowSystem.so`, `libGstCameraSystem.so`)만 뺀 파일이며 빌드 때 지운 줄 수가 2인지 검사한다. 원본은 px4 builder의 diff 검사를 위해 그대로 둔다. 두 plugin은 sim-base에 없어 로드 실패 오류 두 줄이 나지만 서버는 정상 동작함이 실측되었고, x500 기본 모델에는 카메라와 광류 센서가 없다. 이 파일이 월드의 `<plugin>` 선언 대신 Imu, NavSat, Magnetometer, AirPressure 센서 시스템을 올리므로(월드 템플릿에는 월드 직속 plugin 선언이 없고, 있으면 생성기가 거부한다) 이 변수를 빼면 EKF가 수렴하지 않는다고 본다(가정 절 참조).

`px4` (px4): `PX4_SYS_AUTOSTART=4001`, `PX4_SIM_MODEL=gz_x500`, `PX4_GZ_STANDALONE=1`(standalone 구성), `PX4_GZ_WORLD=default`, `PX4_GZ_MODELS=/opt/px4-gz/models`(standalone 분기는 gz_env.sh를 읽지 않고 `file://${PX4_GZ_MODELS}/<모델>/model.sdf`로 스폰하므로 필수, v1.17.0 `px4-rc.gzsim` 137행), `PX4_GZ_MODEL_POSE="6.0,-3.0,0.0,0,0,0.0"`(fleet 파일의 `vehicles[].pose`. `config/fleet.yaml`의 기체 1은 원점에서 동쪽 6 m, 남쪽 3 m에 스폰한다), `PX4_UXRCE_DDS_NS=px4_1`, `PX4_UXRCE_DDS_PORT=<Agent 포트>`, `ROS_DOMAIN_ID=<스택 오프셋>`, `GZ_PARTITION`, `GZ_IP=127.0.0.1`, `config/px4/sitl_params.env`의 `PX4_PARAM_*`. 작업 디렉터리는 `/opt/PX4-Autopilot/build/px4_sitl_default/rootfs`, 명령 `px4 -d -i 1`(PATH에 `build/px4_sitl_default/bin`이 있다. `bin/px4`는 rootfs 기준으로 존재하지 않는다). px4 runtime의 `gz_bridge/server.config` 링크도 `/opt/px4-gz/server.idsim.config`를 가리킨다. `-i 1`이면 실제 작업 디렉터리는 `rootfs/1`이고 ULog는 `rootfs/1/log`다. `PX4_SIM_SPEED_FACTOR`는 스모크에서 주지 않는다(rcS가 손실 타임아웃 파라미터를 덮어쓴다). embedded 변형에서는 `HEADLESS=1`을 준다. 이 변수는 PX4 rcS가 읽어 Gazebo GUI를 띄우지 않게 하는 것이며, 빼면 rcS가 GUI를 띄우려 한다(실측). gazebo 서비스에는 효과가 없다. 이 서비스는 생성된 compose의 `px4-1`이고 호스트 uid:gid로 실행되며 `rootfs/1`은 `artifacts/runs/<실행 id>/px4-1/`의 바인드 마운트다. 판정 스크립트는 식별자를 `stack.json`에서 읽는다.

`xrce-agent`: 명령 `MicroXRCEAgent udp4 -p <Agent 포트>`. `ROS_DOMAIN_ID`는 주지 않는다. 도메인은 PX4 client가 세션 생성 때 넘긴다.

`ros-ws`, `bridge`, `runner`: `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, `CYCLONEDDS_URI=file:///opt/idsim/config/cyclonedds.xml`, `ROS_DOMAIN_ID`, `GZ_PARTITION`과 `GZ_IP=127.0.0.1`(bridge만).

스택 오프셋 전달. `tools/gen_compose.py`가 `config/fleet.yaml`과 스택 번호 k에서 값을 계산해 compose에 구체값으로 박고 같은 값을 `stack.json`에 남긴다(compose 보간은 산술을 못 한다). 스택을 올리는 진입점은 `tools/sim_stack.sh`(스모크는 같은 생성기를 부르는 `run_smoke.sh`)이며, 판정 스크립트는 `stack.json`만 읽고 값을 다시 계산하지 않는다. 그래서 compose를 직접 실행해 세 값이 어긋날 일이 없고, k가 다르면 스택과 스모크를 동시에 돌릴 수 있다.

스택 오프셋 값. 스택 번호 k(기본 0)에 대해 `ROS_DOMAIN_ID` = 20 + k, Agent 포트 = 8888 + k, `GZ_PARTITION` = `idsim-<k>`. 기본 도메인을 0이 아닌 20으로 두는 이유는 인터페이스를 제한하지 않는 DDS 설정에서 격리가 도메인 ID로만 이루어지는데, 도메인 0은 같은 호스트의 다른 ROS 2 스택이 흔히 쓰기 때문이다. CI도 같은 규칙을 쓰며 예외를 두지 않는다. `ROS_DOMAIN_ID`는 PX4 rcS가 `UXRCE_DDS_DOM_ID`로 복사해 Agent 세션에 넘기므로 px4 서비스와 ROS 서비스에 같은 값이 들어가야 한다. `GZ_PARTITION`은 gz-transport의 기본값(호스트명과 사용자명)에 기대지 않고 gazebo, px4, bridge 서비스에 항상 명시한다. 같은 호스트의 다른 Gazebo 인스턴스와 섞이지 않기 위해서다.

cyclonedds.xml은 유니캐스트 피어 127.0.0.1, 멀티캐스트 끔, `ParticipantIndex auto`만 둔 파일 하나이며 `NetworkInterface`를 고정하지 않는다. Agent의 Fast DDS는 호스트 인터페이스 주소(lo가 아님)만 메타트래픽 로케이터로 광고하고 `interfaceWhiteList` 프로필도 적용되지 않아, lo에 묶인 Cyclone 참가자는 Agent를 찾지 못한다(실측). 설정 없음과 비교할 때는 `CYCLONEDDS_URI`를 비운다.

compose 프로젝트 이름. 모든 compose 파일은 `name:`을 명시한다(스모크도 `gen_compose.py`가 만드는 `idsim-<k>`를 쓴다). 명시하지 않으면 디렉터리명이 프로젝트 이름이 되어 호스트의 다른 compose 프로젝트와 충돌한다.

## healthcheck와 시작 정책

| 서비스 | 명령 | interval / timeout / retries / start_period |
| --- | --- | --- |
| xrce-agent | `/proc/net/udp`의 local_address 열에 Agent 포트(16진수)가 바인드된 행 존재. UDP에는 LISTEN 상태가 없으므로 st 열은 보지 않는다. 포트는 compose가 계산 | 5s / 5s / 6 / 10s |
| gazebo | `gz service -i --service /world/<월드>/scene/info \| grep -q "Service providers" && test -f /tmp/idsim/ready`. 준비 파일은 wrapper가 `scene/info` 응답 직후에 쓴다 | 5s / 5s / 6 / 90s |
| px4 | `px4-uxrce_dds_client --instance 1 status \| grep -q 'Running, connected'`. 명령의 종료 코드는 연결 상태를 반영하지 않으므로(v1.17.0 `src/modules/uxrce_dds_client/uxrce_dds_client.cpp`의 `print_status`가 항상 0을 돌려준다) 문자열로 판정. `px4-gz_bridge status`는 연결 상태를 출력하지 않고 Gazebo가 멈춰도 종료 코드 0이라 healthcheck에 쓰지 않는다(실측). 옛 모델 잔존은 운영 스크립트의 down 뒤 up과 `gz model --list` 사전 검사로 막는다 | 5s / 5s / 6 / 90s(embedded), 45s(standalone) |
| bridge | `/clock` 1회 수신 | 30s / 5s / 3 / 60s(`start_period` 동안은 `start_interval` 5s) |

`depends_on`은 xrce-agent -> gazebo -> px4 -> bridge 순으로 `service_healthy`이며, 판정 명령은 상주 서비스가 아닌 `runner`(프로필 `tools`)에서 `compose run`으로 실행한다. `up --wait`는 `startup.stages`의 세 단계로 나눠 부른다. `docker compose up --wait --wait-timeout 240`. `tools/sim_stack.sh up`은 아무것도 올리기 전에 생성된 월드 파일(`stack.json`의 `world.file`)이 있고 그 안에 `<spherical_coordinates>`가 정확히 하나인지 본다(embedded는 `world.file`이 null이라 건너뛴다). `restart`는 모든 서비스에서 `no`다. px4-rc.gzsim(v1.17.0, standalone 분기)은 `/world/<월드>/scene/info` 서비스를 1초 간격 30회 기다리다 초과하거나 gz_bridge 시작에 실패하면 exit 1로 끝나며, 그러면 `up --wait`가 즉시 실패하고 `run_smoke.sh`가 compose logs와 ULog를 artifacts에 모은 뒤 실패한다. 자동 재시작은 flaky를 가리고 standalone에서 `x500_1`이 남아 재스폰이 반복 실패할 수 있어 쓰지 않는다.

## 산출물 위치와 golden 파일 형식

golden(추적): `tests/fixtures/px4/<PX4_TAG>/`. 현재 태그는 `versions.env`의 `PX4_TAG`로 경로를 계산하며 `current` 링크는 두지 않는다. 태그를 올리면 옛 디렉터리는 지운다. 결정적인 값만 넣는다.

- `topics.txt`: 한 줄에 `<상대 토픽> <타입>`. 형식 `fmu/out/<base>_v<N> px4_msgs/msg/<Type>`, 버전 0이면 접미사 없음. 네임스페이스 접두사 `/px4_1/`은 뗀다(embedded, px4-out과 Phase 3의 N대가 같은 파일과 비교된다). `fmu/` 아래만. `LC_ALL=C sort`, 끝 개행 하나.
- `qos/<상대 토픽>.txt`: `reliability`, `durability`, `history`, `depth` 네 줄, 발행자 값.
- `env.txt`: `PX4_TAG`, `PX4_MSGS_REF`, `RMW_IMPLEMENTATION`, `XRCE_AGENT_TAG` 네 줄. 호스트명과 시각은 넣지 않는다. 값은 `versions.env`가 아니라 실행 중인 이미지의 빌드 ENV에서 읽는다.

이미지의 빌드 버전 ENV. 각 Dockerfile은 자기가 받은 버전 ARG를 `IDSIM_BUILD_<key>` ENV로 남긴다. px4는 `IDSIM_BUILD_PX4_TAG`, ros-ws는 `IDSIM_BUILD_PX4_MSGS_REF`와 `IDSIM_BUILD_PX4_ROS_COM_REF`, xrce-agent는 `IDSIM_BUILD_XRCE_AGENT_TAG`, sim-base는 `IDSIM_BUILD_GZ_RELEASE`와 `IDSIM_BUILD_PX4_GZ_MODELS_REF`. `run_smoke.sh`는 images 전에 각 컨테이너의 이 값을 `versions.env`와 대조해 하나라도 다르면 실패한다. `versions.env`만 올리고 이미지를 다시 빌드하지 않은 채 옛 이미지의 측정값이 새 태그의 golden으로 저장되는 것을 막기 위해서다.

원시(비추적): `artifacts/runs/<실행 id>/smoke/`(같은 디렉터리에 생성된 `compose.yaml`, `stack.json`, `px4-N/log/`의 ULog가 있다. 실행 id는 `--run-dir`의 마지막 요소이고, `--run-dir`가 없으면 `<UTC YYYYmmdd-HHMMSS>-k<k>`이고 스모크는 `<UTC>-k<k>-<단계>`). `hz` 측정값은 golden이 아니라 여기에만 남고, 측정 조건(태그, 속도 배수, 벽시계 여부)을 병기한다. 측정 주기는 계약이 아니라 `docs/interface.md`의 토픽 표에 넣지 않는다. CI에서는 이 디렉터리를 job artifact로 올린다.

`docs/interface.md`의 PX4 토픽 표(이름, 방향, 타입, 발행자 QoS)는 `tools/to_interface.py`가 golden과 원시 산출물에서 만든 표에서 측정 주기 열을 뺀 것이다.

## golden 파일 단위 테스트

`idsim_common`의 토픽 매핑은 기술자 목록 하나다. 기술자는 px4_msgs 타입, 방향, 논리 이름, 발행 허용을 묶고, 목록은 golden의 토픽 전부를 담는다. key는 방향과 논리 이름이며(같은 논리 이름이 in과 out 양쪽에 있는 토픽이 있다), 접미사는 기술자에 묶인 타입의 `MESSAGE_VERSION`에서 컴파일 시점에 파생한다. 문자열 인자를 받아 이름을 만드는 함수는 공개하지 않고, 공개 API는 목록에 등록된 기술자만 받는다. 상수가 없는 메시지와 상수가 0인 메시지 둘 다 `std::void_t` 특수화로 0이 된다(두 경우 모두 px4_msgs에 실존한다고 보며, 가정 절 참조). 같은 타입을 쓰는 토픽이 둘 이상이어도 논리 이름이 다르므로 구분된다.

GoogleTest는 다음을 검사한다. 테스트 안에서만 정의한 더미 타입(상수 없음, 상수 0, 상수 N)으로 `msg_version` 특수화 자체를 검사하고, px4_msgs 타입의 버전 값을 리터럴로 고정하지 않는다. 그 값은 기술자 목록 전체가 만드는 (상대 이름, 타입) 쌍 집합이 `topics.txt`의 집합과 양방향으로 일치하는지로 검사한다(타입 문자열은 생성 코드의 `rosidl_generator_traits::name`에서 얻는다). 그래서 태그를 올려 토픽이 더해지거나 빠지거나 접미사가 바뀌면 이 테스트가 깨진다. `env.txt`의 `PX4_MSGS_REF`, `versions.env`의 값, 테스트가 도는 ros-ws 이미지의 ENV `IDSIM_BUILD_PX4_MSGS_REF` 셋이 같은지도 단정한다(이미지 ENV가 없으면 FAIL). 컴파일된 px4_msgs는 이미지의 것이므로, 이 대조가 있어야 매핑이 파생된 px4_msgs와 비교 대상 golden이 같은 조합임이 보장된다.

`idsim_common/CMakeLists.txt`가 테스트를 빌드할 때 `docker/versions.env`에서 `PX4_TAG`와 `PX4_MSGS_REF`를 읽어 `ament_add_gtest`의 ENV로 `IDSIM_PX4_FIXTURE_DIR` 절대 경로와 `IDSIM_PX4_MSGS_REF`를 넘긴다. `versions.env`에 해당 줄이 없거나 둘 이상이거나 golden 디렉터리가 없으면 configure가 실패하고, 테스트도 변수나 디렉터리가 없거나 `topics.txt`가 비어 있으면 SKIP이 아니라 FAIL이다. `ament_index`는 쓰지 않는다. 실패 메시지에는 경로, 양쪽에만 있는 쌍 목록, 접미사를 뗀 기본 이름을 함께 적는다. 이 테스트는 `tools/ros_ws.sh test`로 ros-ws 컨테이너 안에서 돌리며, 저장소 루트가 `/opt/idsim`에 마운트된다는 가정에 선다(다른 위치면 `-DIDSIM_REPO_ROOT=`로 지정).

갱신 절차: `versions.env`의 `PX4_TAG`와 `PX4_MSGS_REF`를 함께 올리고, `run_smoke.sh --update-golden`으로 golden을 다시 만들고, 단위 테스트를 돌리고, PR에서 golden diff를 검토해 승인한다. CI는 비교만 하고 갱신하지 않는다.

## 예외 사항과 가정

- 설계에 적힌 판정은 모두 1차 구현 범위다. 2차로 미루지 않는다. images 전체, embedded의 `info -v` 원문 저장과 Publisher count, px4-out의 `commander check`와 gz_bridge 오류 판정, px4-in의 Subscription count, golden의 `param show`와 `ver all` 저장은 각각 가정의 반증 지점이며, 특히 `param show` 저장값의 `COM_OBL_RC_ACT` = 4와 `COM_RC_IN_MODE` = 4 확인은 그 판정이 없으면 파라미터 이름 오타가 조용히 지나간다.
- 스모크 타임아웃은 벽시계다.
- compose는 `gen_compose.py`가 생성한다. `tests/support/` 모듈은 스모크와 통합 테스트가 함께 쓴다.
- `server.config`는 PX4 소스 `src/modules/simulation/gz_bridge/server.config`와 PX4-gazebo-models 루트의 것이 같다(실측 확인). px4 builder가 diff로 계속 검사한다. gz_plugins(광류, GStreamer 카메라)를 sim-base에 넣지 않는다. OpenCV, GStreamer 의존과 비재현 빌드가 따라오고 x500 기본 모델에는 쓸 곳이 없다.
- `OffboardControlMode`에는 `MESSAGE_VERSION` 상수가 없고 `VehicleStatus`는 1임이 실측으로 확인되었다. versioned 34개 중 9개가 1, 25개가 0이며 `TrajectorySetpoint`, `VehicleCommand`, `VehicleCommandAck`는 0이다. `ArmingCheckReply.msg`만 등호 앞 공백이 두 칸이라 `.msg`를 읽는 파서는 공백에 관대해야 한다.
- px4_ros_com에는 release/1.17 브랜치가 없다(release/1.13, 1.15, 1.16, v1.14, main). `PX4_ROS_COM_REF`는 release/1.16 HEAD와 같은 main 커밋으로 고정했다. `frame_transforms`는 px4_msgs에 의존하지 않아 태그 호환은 문제가 아니지만 공분산 변환 두 개가 틀리고 동체 변환이 NaN을 다른 축으로 번지게 하므로, `idsim_common`은 래핑하지 않고 변환을 직접 구현한다. 벡터와 쿼터니언 변환은 맞아서 px4_ros_com은 단위 테스트의 비교 기준으로만 쓴다.
- 생성된 compose가 호스트 uid:gid `user` 매핑을 넣으므로 `artifacts/`에 root 소유 파일이 생기지 않는다. px4-out 판정은 `sensor_gps` 좌표가 기대 GPS와 일치하는지(원점 판정), `gz model --list`에 `x500_1`이 정확히 하나인지, PX4 로그에 `WARN  [mavlink] bind failed`가 없는지를 포함한다.
- 원점 판정. 원점은 생성된 월드 SDF의 `<spherical_coordinates>`로만 들어간다. 기대값은 `stack.json`의 `vehicles[0].expect_gps`이고, 생성기가 `world.origin`, 기체의 스폰 pose, GNSS 센서가 붙은 base_link의 높이(x500은 0.24 m)로 계산한 그 기체의 GNSS 센서 위치다. `run_smoke.sh`는 이 값을 `check_px4.py --expect-origin`으로 넘기기만 하고 계산하지 않는다. 3D fix 표본들의 최대 오차가 수평 0.5 m, 수직 1.0 m 안이면 통과다. `config/fleet.yaml`의 기체 1은 원점에서 떨어진 (6, -3, 0)에 스폰하므로, 원점이 적용되지 않았거나 위경도 변환의 수평 축이 뒤집히면(오차 약 13.4 m) 이 판정이 실패한다. embedded는 월드를 생성하지 않아 `expect_gps`가 null이고 원점 판정을 하지 않는다.
- 가정: 모델 저장소 커밋은 `PX4_GZ_MODELS_REF`로 고정하고 px4 builder가 서브모듈 커밋과 같은지 검사한다. 런타임 이미지는 `/opt/PX4-Autopilot/Tools/simulation/gz`를 `/opt/px4-gz`로 가리키는 심볼릭 링크로 두어 빌드 때 박힌 gz_env.sh 경로를 살린다.
- 가정: `GZ_IP=127.0.0.1`을 빼면 gz-transport 디스커버리가 불안정하다(`make` 타깃이 이 값을 넣어 주는 것을 근거로 한 추측). 스모크는 명시하고 간다.
- 가정: `server.idsim.config`가 없으면 센서 시스템이 올라오지 않아 EKF가 수렴하지 않는다(PX4 소스 읽기 기반). px4-out의 `commander check`가 반증 지점이다. `COM_RC_IN_MODE=4`에서 `commander check`가 통과하는지도 같은 지점에서 본다.
- SITL 파라미터는 `config/px4/sitl_params.env`가 단일 출처이며 값마다 근거 주석을 둔다. Offboard 손실 시 동작 파라미터의 이름은 `COM_OBL_RC_ACT`(4 = Land)다. `COM_OBL_ACT`라는 파라미터는 v1.17.0에 없고, 잘못된 이름은 rcS의 `param set`이 오류만 찍고 넘어가 기본값(Position)이 남으므로 이름 오타는 조용한 실패가 된다. golden의 `param show` 저장값에서 이 이름의 값이 4인지 확인한다.
- 공통 SITL 파라미터에 `UXRCE_DDS_SYNCT=0`이 있다(PX4 timestamp를 시뮬레이션 시간 축에 둔다). px4-out의 `param show` 판정이 저장값 0을 확인한다. 이 값에서 `timesync_status` 토픽은 그래프와 golden에 남지만 데이터가 오지 않으므로 golden의 `hz` 측정 대상에서 뺀다.
- 가정: `/proc/net/udp`에서 Agent 포트의 행이 보인다(st 값은 보지 않는다). images에서 확인한다.

## 로컬 빌드

버전은 `docker/versions.env`에서만 읽는다. 환경변수로 내보낸 뒤 bake를 실행한다.

```
set -a; . docker/versions.env; set +a
docker buildx bake -f docker/docker-bake.hcl ros-base xrce-agent --load
```

- 타깃은 `ros-base`, `sim-base`, `px4`, `ros-ws`, `xrce-agent` 다섯 개다. 의존 이미지(`sim-base`는 `ros-base`, `px4`는 `sim-base`, `ros-ws`는 `ros-base`)는 bake의 named context로 연결되므로 하나만 지정해도 필요한 베이스가 먼저 빌드된다.
- 로컬 태그는 `idsim/<이미지>:local`. 레지스트리 태그는 `${REGISTRY}/<이미지>:<key>`이며 `<key>`는 환경변수 `KEY`(로컬 기본값 `local`, CI에서는 Dockerfile과 `versions.env` 해시)다.
- 빌드 인자는 기본값이 없다. `versions.env`를 내보내지 않으면 빌드가 실패한다.
