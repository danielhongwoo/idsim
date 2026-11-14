# idsim_sim

Gazebo 시뮬레이션 쪽 설정과 노드를 모으는 패키지다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`를 따른다.

## 역할

ament_python 패키지다. 설치 대상은 Python 패키지 `idsim_sim`과 실행 파일 `target_adapter`뿐이고, `scripts/`의 셸 wrapper와 정답 pose 노드 `sim_oracle.py`, `config/`, `worlds/`는 설치하지 않고 이 디렉터리를 컨테이너에 마운트해서 쓴다(아래 마지막 문단).

## 표적 어댑터 (`target_adapter`)

`ros2 run idsim_sim target_adapter --ros-args --params-file <실행 디렉터리>/params/targets.yaml`. compose의 `targets` 서비스가 띄운다. fleet 파일의 `targets` 궤적 정의(생성기가 정규화해 params로 준 값)를 노드 시계(`/clock`)에서 평가해 `TargetState`를 발행한다. Gazebo를 구독하지 않고, 운용 노드도 Gazebo 토픽을 직접 보지 않는다. 원점을 모르고 출력은 world ENU뿐이다.

- params(평탄화 형식, 형식은 `idsim_sim/params.py` 머리 주석): `use_sim_time: true`, `target_ids`(문자열 배열), 표적마다 `targets.<id>.start_s`(double), `targets.<id>.loop`(bool), `targets.<id>.t`, `.x`, `.y`, `.z`(같은 길이의 double 배열). 선택 `publish_rate_hz`(double, 기본 20.0). 노드는 params 전부를 override에서 자동 선언하고 형까지 검사한다. 실수를 정수로 적으면 INTEGER로 읽혀 거부된다. `targets.` 아래의 모르는 이름도 거부한다.
- 토픽: 절대 이름 `/targets/<target_id>/state`(`TargetState.TOPIC_PREFIX`, `TOPIC_SUFFIX`로 조립, `idsim_sim/naming.py`). `target_id` 규칙은 `^[a-z][a-z0-9_]{0,31}$`.
- QoS: RELIABLE, VOLATILE, KEEP_LAST 5, liveliness AUTOMATIC.
- stamp: timer 콜백의 노드 시계 시각 t이고 위치와 속도를 같은 t에서 계산한다. 표적마다 직전 stamp보다 큰 t에서만 발행하고 0은 내지 않는다. 역행하면 오류 로그를 남기고 직전 stamp를 넘을 때까지 발행하지 않는다.
- 궤적: 구간 직선 보간, 속도는 구간 기울기(`velocity_valid` true). `start_s` 전에는 첫 점에 정지, waypoint 시각 정확히는 다음 구간, loop true는 마지막 시각의 나머지, loop false는 끝난 뒤 마지막 점에 정지. 평가와 stamp 규칙은 rclpy를 import하지 않는 `idsim_sim/trajectory.py`에 있다.
- 준비 표시 파일 `/tmp/idsim/targets_ready`: 시작 때 지우고, 모든 표적이 stamp > 0으로 한 번 이상 발행되면 임시 파일에 쓴 뒤 rename으로 만든다. 내용은 표적마다 `<id> <첫 stamp 초.ns>` 한 줄. healthcheck는 `test -f /tmp/idsim/targets_ready`다.
- 종료 코드: 설정 오류(`use_sim_time` false, params 누락, 형 불일치, 길이 불일치, id 형식과 중복, t가 0에서 시작해 엄격히 증가하지 않음, loop인데 처음과 끝이 다름, 빈 배열처럼 rclpy가 선언하지 못하는 값)는 2, SIGINT 정상 종료는 0. 시작 뒤 `use_sim_time`, `target_ids`, `publish_rate_hz`, `targets.*`의 변경은 거부한다(`use_sim_time`을 false로 바꾸면 stamp가 벽시계로 뛰어도 단조 규칙을 통과하고, 나머지는 시작 때만 읽는다).

Gazebo 화면의 Actor 위치는 참고용이다. 표적 위치의 원천은 Actor가 아니라 fleet 파일의 궤적 정의이고 정본은 `TargetState`다. Actor는 생성기가 같은 정의에서 뽑은 표본 waypoint를 Gazebo가 spline으로 보간해 그리므로 waypoint 사이와 꺾이는 점 근처에서 `TargetState`와 조금 어긋난다.

## 정답 pose 노드 (`scripts/sim_oracle.py`)

SITL 판정 전용 노드다. 계약이 아니고 `idsim_interfaces`에 의존하지 않는다. 운용 패키지는 `/sim/` 토픽을 쓰지 않는다. compose의 `sim-oracle` 서비스(sim-base 이미지, standalone 변형에만 있다)가 이 패키지 디렉터리를 `/opt/idsim/sim`에 읽기 전용으로 마운트하고 `python3 /opt/idsim/sim/scripts/sim_oracle.py`로 띄운다. 설치 대상이 아니다.

- 입력: gz-transport Python 바인딩(`gz.transport13`, `gz.msgs10`)으로 `/world/<IDSIM_WORLD_NAME>/pose/info`(`gz.msgs.Pose_V`)를 직접 구독한다. ros_gz_bridge와 `/clock`을 거치지 않고 `dynamic_pose/info`는 구독하지 않는다. Pose_V의 top-level model 항목(`x500_N`)은 world 기준 pose이고, link 항목은 부모 model 기준이며 이름에 scope가 없다(`base_link`가 기체마다 하나씩 있다). 그래서 기체는 top-level model 이름으로만 찾는다. 같은 이름이 한 표본에 둘 이상이면 그 기체를 내지 않고 오류 로그를 남긴다.
- 기준점: 기체 base_link 원점(PX4 센서가 붙은 점)이다. `p_bl = p_model + R_model * offset`이고 자세는 model 자세 그대로다. offset은 시작할 때 sdformat14로 모델 SDF(`GZ_SIM_RESOURCE_PATH`에서 찾은 `model://<model 이름에서 _N을 뗀 것>/model.sdf`, include는 같은 경로로 푼다)를 해석해 얻는 base_link의 model 프레임 위치다. x500은 (0, 0, 0.24)다. base_link가 model 프레임에서 회전을 가지면 시작을 거부한다.
- 환경 변수: `IDSIM_WORLD_NAME`(필수), `IDSIM_ORACLE_VEHICLES`(`px4_1=x500_1 px4_2=x500_2`, 공백 구분 `<vehicle_id>=<model>`, 중복 거부), `GZ_SIM_RESOURCE_PATH`(sim-base 기본값), `GZ_PARTITION`, `GZ_IP`, ROS 공통값. `vehicle_id`는 ROS 이름 토큰 하나로만 검사하고 내용은 해석하지 않는다.
- 출력: `/sim/<vehicle_id>/pose`(`geometry_msgs/msg/PoseStamped`, `header.frame_id` `world`, `header.stamp`는 `pose/info` header의 sim 시각). QoS는 RELIABLE, VOLATILE, KEEP_LAST 10. 주기는 SceneBroadcaster의 `pose/info` 주기를 따른다(sim 시간 약 50 Hz). 기체마다 stamp 0, 역행, 직전 발행에서 10 ms 미만인 표본은 내지 않는다. `use_sim_time`을 쓰지 않는다(stamp는 Gazebo 표본의 시각이다).
- 준비 표시 파일 `/tmp/idsim/oracle_ready`: 시작 때 지우고, 모든 기체의 pose를 한 번 이상 낸 순간 임시 파일에 쓴 뒤 rename으로 만든다(`idsim_sim/ready.py` 재사용). 내용은 기체마다 `<vehicle_id> <첫 stamp 초.ns>` 한 줄. healthcheck는 `test -f /tmp/idsim/oracle_ready`다. 모델이 스폰되기 전에는 성립하지 않으므로 서비스는 gazebo와 `px4-N` 전부의 healthy를 기다린다.
- 종료 코드: 설정 오류(환경 변수 누락과 형식, 모델 SDF를 찾지 못함, base_link 없음이나 회전 있음, gz 구독 실패)는 2, SIGINT와 SIGTERM은 0.
- 구조: 이름 조립(`pose_info_topic`, `oracle_pose_topic`), 환경 변수 해석(`parse_vehicles`, `load_env`), 오프셋 합성(`compose_base_link`), 발행 판단(`should_publish`, `OracleCore`)은 rclpy, gz, sdformat14를 import하지 않는 순수 함수이고, rclpy, gz, sdformat14, `geometry_msgs`는 실행 함수 안에서만 import한다. 그래서 gz 바인딩이 없는 ros-ws 이미지의 단위 테스트(`test/test_sim_oracle.py`)가 이 파일을 경로로 읽어 시험한다. 모듈은 자기 부모 디렉터리(마운트된 패키지 디렉터리)를 `sys.path`에 넣어 `idsim_sim.ready`를 쓴다.

## 단위 테스트

`tools/ros_ws.sh test`가 `test/`를 돌린다. 궤적 평가는 손 계산 golden `test/golden/trajectory_eval.csv`와 비교한다(평가 함수로 기대값을 만들지 않는다). 정답 pose 노드의 오프셋 합성은 손 계산 golden(`test/test_sim_oracle.py`의 표)과 비교하고, 구독 토픽이 `/pose/info`로 끝나며 `dynamic_pose`가 없음과 `/sim/<vehicle_id>/pose` 조립 사례 표도 본다. 그 밖에 stamp 규칙, `target_id`와 토픽 조립 사례 표, params 거부 조건, 표시 파일, 설정 오류의 종료 코드, `config/gui.config`의 plugin 목록 고정, Apache-2.0 머리말이 있다.

## 현재 들어 있는 것

- 월드 생성 규칙: 생성기 `tools/gen_compose.py`가 `world.origin`의 `<spherical_coordinates>`를 넣어 월드 SDF를 만든다. 표적마다 `<actor>`(이름은 `target_id`, `<link>` visual 하나, `<loop>`는 항상 true)도 넣는다. Actor는 화면 확인용이고 물리 모델이 아니다. gz-sim 8.15.0에서 `<loop>`가 false인 Actor는 `delay_start`가 0이면 렌더링(GUI, 카메라 센서)이 끝나지 않는 루프에 빠지고, 0보다 크면 첫 waypoint에서 움직이지 않는다. `<script>`가 없는 Actor도 같은 루프에 걸린다. 그래서 loop false 표적은 마지막 점에 오래 머무는 waypoint를 더해 표현한다.
- ros_gz_bridge 설정은 이 패키지에 파일로 없고 생성기 상수 `BRIDGE_TOPIC_ARGS`에 있다. bridge 토픽은 `/clock`(gz -> ROS) 하나이고, 표적 pose와 정답 pose는 bridge를 거치지 않는다.
- `config/gui.config`: Gazebo GUI 클라이언트(`gz sim -g`) 설정. gz-sim8 기본 설정에서 WorldControl plugin을 빼고 바닥 격자(GridConfig)를 더했다. plugin 목록은 단위 테스트(`test/test_gui_config.py`)가 고정한다. 이 목록 밖의 plugin(특히 설정의 `<topic>`으로 구독 대상을 받는 TopicEcho, TopicViewer, Plotting 계열)을 더하지 않는다. 화면에서 실수로 월드를 일시정지하거나 스텝 실행해 시뮬레이션 시계를 멈추는 것을 막고, 균일한 회색 월드에서 기체 이동이 보이게 한다. 출처와 이유는 파일 첫머리 주석에 있다. `scripts/gz_gui.sh`가 `--gui-config`로 넘긴다.
- `worlds/idsim_base.sdf`: 월드 템플릿. PX4-gazebo-models `worlds/default.sdf`(ref는 `PX4_GZ_MODELS_REF`)의 physics, gravity, magnetic_field, atmosphere, scene, ground_plane, sunUTC light를 값 그대로 옮겼다(출처는 파일 주석). 월드 직속 `<plugin>`, `<spherical_coordinates>`, `<actor>`, `<include>`는 넣지 않는다. 월드 직속 plugin이 없어야 `server.idsim.config`의 system plugin 목록(Physics, UserCommands, SceneBroadcaster, Imu, AirPressure, Magnetometer, NavSat 등)이 적용된다. `<world name>`의 값 `idsim_base`는 자리표시다. 생성기(`tools/gen_compose.py`)가 이름을 `world.name`으로 바꾸고 `<spherical_coordinates>`(`world.origin`, heading 0, ENU)를 넣어 실행 디렉터리의 `world/<이름>.sdf`로 쓴다. 템플릿을 Gazebo로 직접 열지 않는다.
- `scripts/gz_server.sh`: gazebo 서비스의 진입 스크립트(sim-base, root). `IDSIM_WORLD_FILE`(생성된 월드, compose가 `/opt/idsim/world/<이름>.sdf`를 준다)의 `<world name>`이 `IDSIM_WORLD_NAME`과 같은지, `<spherical_coordinates>`가 정확히 하나인지 검사하고, `gz sim -r -s <IDSIM_WORLD_FILE>`을 자식으로 띄워 `/world/<이름>/scene/info`가 응답할 때까지(상한 60초) 기다린 뒤 준비 파일 `/tmp/idsim/ready`를 남긴다. 원점은 SDF로만 들어가고 런타임 호출은 없다. 이름이 다르거나 `<spherical_coordinates>`가 하나가 아니면 종료 코드 1로 끝난다. TERM/INT는 자식 서버에 전달하고 5초 안에 안 끝나면 KILL한다(종료 코드 TERM 143, INT 130). 원점의 실제 적용은 px4의 `sensor_gps` 좌표로 판정한다. healthcheck는 `gz service -i --service /world/<이름>/scene/info | grep -q "Service providers" && test -f /tmp/idsim/ready`다(파일 머리 주석).
- `scripts/gz_gui.sh`: gz-gui 서비스(`viz` 프로필)의 진입 스크립트(호스트 uid:gid). `XAUTHORITY`를 마운트 지점 `/tmp/.Xauthority`로 스스로 정하고(compose env에 의존하지 않는다), `DISPLAY`가 비었거나 그 파일이 없거나 비었거나 읽을 수 없거나 GUI 설정 파일을 읽을 수 없으면 안내 메시지와 종료 코드 1로 끝낸다(gz는 설정 파일을 못 읽으면 경고만 내고 WorldControl이 있는 기본 설정으로 뜨기 때문이다). `HOME`에 쓸 수 없으면 `/tmp/gz-home`을 쓴다. 그 뒤 `gz sim -g --gui-config ${IDSIM_GUI_CONFIG:-/opt/idsim/sim/config/gui.config} --render-engine-gui ${IDSIM_GZ_GUI_ENGINE:-ogre2}`로 exec한다. `--render-engine-gui`는 `gui.config`의 `<engine>`을 덮는다(ogre를 주면 OGRE 1.9가 로드되고 격자도 보인다, 2026-11-09 실측).

`scripts/`의 파일은 이 패키지 디렉터리를 컨테이너의 `/opt/idsim/sim`에 읽기 전용으로 마운트해 쓴다(`/opt/idsim/sim/scripts/...`, `/opt/idsim/sim/config/gui.config`). 생성된 월드는 별도로 `/opt/idsim/world`에 읽기 전용으로 마운트한다.
