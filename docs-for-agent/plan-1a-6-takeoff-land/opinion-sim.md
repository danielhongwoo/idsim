# sim-engineer 의견 (1a 6단계 설계 토론, S1-S4)

작성 2026-11-10, sim-engineer. main 88afeda, 브랜치 feat/1a-6-takeoff-land. 저장소 파일은 이 문서 말고는 바꾸지 않았고 colcon build는 하지 않았다.

## 실측 조건 (모든 [실측]에 공통)

- 스택 k = 5(`tools/stack.sh up --stack 5`, 실행 id 20261110-143245-k5, 기체 1대, standalone, headless), 이미지 `idsim/*:local`. 측정이 끝난 뒤 `tools/stack.sh down --stack 5`로 내렸고 탐침 컨테이너와 viz 컨테이너도 모두 지웠다.
- 같은 시간에 다른 담당자의 스택 idsim-1(4 서비스)과 이미지 빌드(`idsim-d4-build` 등)가 함께 돌았다. 측정 구간의 호스트 load1 평균은 A 6.4, B 7.2, C 13.4, D 16.0(4 vCPU)이고 MemAvailable 최소는 4.0-5.6 GB였다. 아래 RTF와 CPU는 이 경합 위의 값이다. 경합 없는 값은 따로 재지 못했다.
- 탐침 스크립트는 scratchpad에 있다: `monitor.sh`(gz `/stats`의 sim_time/real_time 처음과 끝, `docker stats` 8초 간격), `clock_probe.py`(rclpy, `use_sim_time` 참, `/clock` 수신 간격과 ROS 시각 20 Hz timer 주기), `sp_pub.py`, `fg_client.py`(표준 라이브러리 websocket 클라이언트).
- 화면: 이 호스트에는 사용자 그래픽 세션이 없었다(셸 `DISPLAY` 비어 있음, `loginctl`에 gdm greeter만, 사용자는 SSH 접속). 그래서 gz-gui는 scratch 이미지(sim-base + xvfb)에서 Xvfb :99와 llvmpipe(`LIBGL_ALWAYS_SOFTWARE=1`)로 띄웠다. 실제 화면 세션의 GPU 경로와 CPU가 다를 수 있다.

## S1. `/clock`의 원천과 RTF

결론: Gazebo는 물리 스텝마다(250 Hz) `/clock`을 내고 bridge는 이를 그대로 250 Hz로 넘긴다. RTF는 경합 아래서도 0.99 이상이었다. `/clock` 주기는 낮추지 않는다.

실측
- [실측] Gazebo 쪽: gazebo 컨테이너 안 `gz topic -e -t <토픽> -n 1000`의 벽시계 소요가 `/clock` 4208 ms, `/world/default/clock` 4137 ms, `/stats` 4242 ms(기동 시간 포함, 약 240-250 Hz). `/stats`의 `step_size` 4 ms. 5분 구간 iterations 75764 / 304.3 s = 249.0 Hz.
- [소스] sim-base 이미지 `/opt/px4-gz/worlds/default.sdf` 5-7행 `max_step_size 0.004`, `real_time_update_rate 250`. `/opt/px4-gz/models/x500_base/model.sdf` 261행 IMU `update_rate 250`(같은 파일 221, 235, 313행은 50, 100, 30). 이미지 안 파일을 직접 grep했다(PX4 v1.17.0 태그에서 이미지가 복사한 사본).
- [실측] bridge 뒤(ROS 쪽): `clock_probe.py` 60초 1회(부하 없음) 수신 249.83 Hz, 수신 간격 p50 4.000 ms, p99 5.76 ms, 최대 12.5 ms. sim 시각 증가는 모든 메시지에서 정확히 4 ms(건너뜀과 중복 없음). 190초 1회(부하 있음) 249.42 Hz, p99 5.93 ms, 최대 106.0 ms(1회), sim 증가는 역시 모두 4 ms.
- [실측] ROS 시각 20 Hz timer(`create_timer(0.05)`, `use_sim_time` 참): sim 주기 평균 49.97 ms(부하 없음), 49.99 ms(부하), 값은 48/52 ms처럼 `/clock` 한 스텝(4 ms) 단위로 양자화되고 최대 56 ms. 벽시계 주기 최대 64.8 ms(부하 없음), 157.6 ms(부하. 100 ms 넘은 것 2회/3790회). 벽시계로 길었던 순간에 sim 주기는 늘지 않았고 같은 구간에 `/clock` 자체가 106 ms 끊겼다. 즉 끊김은 ROS timer가 아니라 `/clock`을 만드는 쪽(Gazebo 스텝 또는 호스트 스케줄링)이나 그 전달에서 생겼다. 둘 중 어느 쪽인지는 이 실험으로 가르지 못했다.
- [실측] bridge CPU: `parameter_bridge` 프로세스(pid 직접, `/proc/<pid>/stat` 30초) 6.7%(구독자 없음), 5.5%(구독자 1개 추가). 한 코어 = 100%. `docker stats` 기준 bridge 컨테이너는 평균 4.1%, 메모리 32 MiB이고 30초마다 healthcheck(`ros2 topic echo --once`)가 순간 수십 %를 더한다. gazebo 컨테이너도 healthcheck의 `gz-transport-service`가 순간 25%를 쓴다.
- [실측] RTF(gz `/stats`의 sim_time 증가 / real_time 증가, 1회씩):
  - A. headless 스택만, 304.3 s: RTF 0.9960. gazebo 평균 32.6%(p95 48.4%), px4 20.0%, 에이전트 2.6%, bridge 4.1%. 메모리 gazebo 143 MiB.
  - B. 운용 노드 하나에 해당하는 부하(아래), 187.8 s: RTF 0.9976. 탐침 컨테이너 약 15% CPU.
  - C. gz-gui(Xvfb, llvmpipe) 붙임, 181.3 s: RTF 0.9899. gz-gui 평균 93%(p95 131%), 메모리 최대 732 MiB.
  - D. gz-gui + foxglove_bridge + lichtblick + websocket 클라이언트 1개, 128.6 s: RTF 0.9877.
- [추정] B의 부하는 운용 노드의 대리다. rclpy 노드 하나가 `use_sim_time`으로 `/clock`, `vehicle_local_position_v1`(49.6 Hz 수신), `vehicle_status_v1`를 BEST_EFFORT로 구독하고 20 Hz timer로 `TrajectorySetpoint`를 `/fmu/in`이 아닌 `/sim_probe/trajectory_setpoint`에 발행했다. C++ lifecycle 노드의 실제 CPU와는 다르다.
- [추정] C와 D의 RTF 하락(0.996 -> 0.988)은 같은 시간대 호스트 load1이 6에서 16으로 오른 것과 겹쳐 gz-gui 탓만으로 볼 수 없다. 2026-11-06 기록(GPU 경로, GUI를 붙여도 RTF 1.0)과 모순되지는 않는다.

의견
- [추정] `/clock` 주기를 낮추는 길은 둘인데 둘 다 쓰지 않는다. (1) 스텝을 키우면(`max_step_size`) `/clock`은 줄지만 IMU 250 Hz와 PX4 lockstep 주기가 함께 바뀐다(위 [소스]). (2) bridge 뒤에 throttle을 두면 ROS 시각 해상도가 throttle 주기가 되어 20 Hz timer의 양자화가 4 ms에서 그 주기(예 50 Hz면 20 ms)로 커진다. ros_gz_bridge `parameter_bridge`에는 메시지 수를 줄이는 설정이 없다고 알고 있으나 원문으로 확인하지 않았다.
- [실측 근거의 의견] 낮출 이유도 작다. bridge는 한 코어의 5-7%, 메모리 30 MiB 수준이다.
- [추정] 충돌 지점 1에 대한 sim 쪽 사실: PX4는 Gazebo와 lockstep이므로 Gazebo 스텝이 멈추면 PX4 시각도 멈춘다. 그러면 ROS 시각 timer가 쉬는 동안 PX4의 `COM_OF_LOSS_T` 판정 시각도 같이 쉰다. 반대로 벽시계 timer는 이런 정지 동안에도 돌아 같은 PX4 시각에 setpoint가 몰린다. 끊김이 Gazebo 뒤(DDS 전달)에서 생긴 경우는 PX4 시각만 흐르므로 이 논리가 성립하지 않는다. 어느 쪽이 실제로 일어났는지는 PX4 timestamp와 `/clock`을 함께 기록해야 가린다(px4, ros2 담당 실험).
- `PX4_SIM_SPEED_FACTOR`: 1a에서는 쓰지 않는다(`fleet.yaml`의 `speed_factor: null` 유지). 기체 1대 RTF가 경합 아래서도 0.99라 배속으로 테스트 시간을 줄일 여지는 있으나 3대 시나리오 실측(1b)을 한 뒤 정한다.

## S2. Lichtblick 실접속(D3)

결론: foxglove_bridge 3.6.0과 Lichtblick 이미지의 서버 쪽 접속, px4_msgs 스키마 전달, setpoint와 `vehicle_local_position` 동시 수신은 확인했다. 브라우저 화면의 플롯은 보지 못했다(사용자 확인 필요). layout은 `ros_ws/src/idsim_sim/config/lichtblick/default-layout.json`에 두고 lichtblick 컨테이너의 `/lichtblick/default-layout.json`에 읽기 전용으로 마운트하기를 제안한다.

실측(모두 스택 k = 5, 각 1회)
- [실측] D5보다 먼저 확인하려고 scratch 이미지 `idsim-scratch/ros-ws-foxglove:sim`(`FROM idsim/ros-ws:local`, `apt-get install ros-jazzy-foxglove-bridge`)를 만들었다. 설치 버전 3.6.0-1noble.20260930.003057, 추가 레이어 49.6 MB(이미지 1.99 GB -> 2.05 GB). 이 이미지는 저장소와 무관하며 devops의 D1을 대신하지 않는다.
- [실측] 파라미터: `address 127.0.0.1`, `port 8770`(8765 + 5), `use_sim_time true`, `capabilities [connectionGraph]`, `topic_whitelist ['^/clock$', '^/px4_[1-9]/fmu/out/.*', '^/px4_[1-9]/fmu/in/(trajectory_setpoint|offboard_control_mode|vehicle_command)$']`, service/param/client_topic whitelist `['^$']`. 서버가 알린 `serverInfo`: capabilities `["connectionGraph", "time"]`(clientPublish, services, parameters 없음. `time`은 `use_sim_time`이라 서버가 붙인다), supportedEncodings `["cdr", "json"]`, `fg-library: foxglove-bridge/3.6.0 foxglove-sdk-cpp/0.28.0`.
- [실측] 서브프로토콜: `foxglove.sdk.v1`은 101, `foxglove.websocket.v1`은 400 Bad Request.
- [실측] 채널 32개(허용 목록 결과, `/foxglove_bridge/sysinfo` 포함). `/px4_1/fmu/out/vehicle_local_position_v1`은 `px4_msgs/msg/VehicleLocalPosition`, encoding cdr, schemaEncoding ros2msg, 스키마 본문 4797자. `/px4_1/fmu/in/trajectory_setpoint`는 `px4_msgs/msg/TrajectorySetpoint`, 637자. `/fmu/in/vehicle_command`와 `offboard_control_mode`는 발행자 없이(PX4 쪽 구독자만 있어도) 채널로 나왔다.
- [실측] 구독: 비시동 상태에서 스택 안 탐침(`sp_pub.py`, `/px4_1/fmu/in/trajectory_setpoint` 20 Hz, `offboard_control_mode`는 보내지 않음)을 돌리고 세 채널을 구독했다. 10초 동안 `vehicle_local_position_v1` 49.6 Hz, `trajectory_setpoint` 19.8 Hz, `/clock` 247.7 Hz. 135초 연속도 끊김 없이 수신(`vehicle_local_position_v1` 49.5 Hz).
- [실측] Lichtblick 이미지 `ghcr.io/lichtblick-suite/lichtblick@sha256:25333a8f...a5177e9`(로컬에 있던 것, Created 2026-10-22)를 `-p 127.0.0.1:18085:8080`으로 띄워 `/`가 200을 돌려줬다. 메모리 40 MiB, CPU 0%.
- [실측] 버전 표기 정정: 이 이미지의 `2.5.2`는 Caddy 버전이다(이미지 라벨 `org.opencontainers.image.version v2.5.2`, ENV `CADDY_VERSION=v2.5.2`). 번들 `2132.*.js` 안의 문자열은 `"Lichtblick version ","1.30.0"`이다. progress.md 결정 기록(2026-11-06)과 `docs/architecture.md` 106행의 "Lichtblick 2.5"는 Lichtblick 1.30.0으로 읽어야 한다. 번들에는 `foxglove.sdk.v1`과 `foxglove.websocket.v1` 문자열이 둘 다 있다.
- [실측] layout: 이미지의 `/entrypoint.sh`가 시작할 때 `/lichtblick/default-layout.json`을 읽어 `/src/index.html`의 `LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER` 자리에 넣는다. 파일이 없으면 빈 파일을 만든다. 컨테이너는 root로 돌고 `/src/index.html`을 고쳐 쓰므로 루트 파일시스템을 읽기 전용으로 둘 수 없다.
- [실측] 번들에 `ds.url` 처리 코드가 있다. [추정] `http://127.0.0.1:18085/?ds=foxglove-websocket&ds.url=ws://127.0.0.1:8770`으로 접속 대화상자 없이 붙는다(화면으로 확인하지 않음).
- 못 한 것: 브라우저에서 Plot 패널에 두 경로(`/px4_1/fmu/in/trajectory_setpoint.position[2]`, `/px4_1/fmu/out/vehicle_local_position_v1.z`)를 놓는 것. 호스트에 화면이 없고, 사용자 브라우저는 다른 기계(SSH 클라이언트)에 있어 127.0.0.1 바인드에 닿지 않는다. [추정] 두 채널이 같은 서버에서 ros2msg 스키마와 함께 오므로 Plot 패널에 함께 놓을 수 있다. 사용자 확인 항목으로 남긴다.

의견
- [추정] 사용자 브라우저가 다른 기계에 있으면 두 포트를 모두 터널로 넘겨야 한다: `ssh -L 18085:127.0.0.1:18085 -L 8770:127.0.0.1:8770 <호스트>`. Lichtblick은 정적 파일만 주고 websocket은 브라우저가 직접 연다. 127.0.0.1 바인드는 그대로 두는 것이 맞고, 절차 문서(docker/README.md 시각 도구 절)에 이 줄이 필요하다.
- layout 파일을 저장소에 둔다. 위치는 `ros_ws/src/idsim_sim/config/lichtblick/default-layout.json`(gz-gui의 `gui.config`와 같은 곳, 같은 방식의 읽기 전용 바인드 마운트). 이유: [실측] 이미지가 그 경로 하나만 지원하고, layout이 토픽 이름을 담으므로 버전 관리가 필요하다.
- [추정] layout의 토픽 이름은 기체 1(`/px4_1`)과 px4_msgs 메시지 버전 접미사(`_v1`)에 묶인다. PX4 태그를 올릴 때 layout이 조용히 빈 플롯이 되므로, S4 golden 토픽 목록과 layout의 토픽을 대조하는 단위 검사를 test-engineer에게 제안한다. 다른 기체는 화면에서 고친다.
- [추정] Lichtblick의 기본 layout은 브라우저에 저장된 layout이 없을 때만 쓰인다고 알고 있다. 절차에 "처음이 아니면 layout 메뉴에서 기본값으로 되돌린다"를 넣는다(화면 확인 필요).
- 허용 목록의 `^/clock$`는 빼도 된다. [실측] 서버가 `time` capability로 시각을 따로 보낸다. 구독하면 250 Hz가 브라우저로 간다.

## S3. 육안 확인 절차(D10)

결론: gz-gui(소프트웨어 렌더링) + foxglove_bridge + lichtblick 서버를 함께 올려도 스택 메모리 합은 약 1 GB, RTF 0.988이었다. QGC는 재지 못했다. 7 GB 호스트에서 함께 띄우는 것은 [추정] 가능하나, 이 호스트에 지금 화면 세션이 없다는 것이 먼저 풀려야 한다.

실측(D 구간 128.6 s, 1회)
- [실측] 컨테이너 메모리 최대: gz-gui 726 MiB(Xvfb 포함, llvmpipe), gazebo 144 MiB, foxglove 33 MiB(클라이언트 1개가 세 채널 구독), lichtblick 40 MiB, bridge 30 MiB, px4 19 MiB, 에이전트 13 MiB. 합 약 1.0 GB. 같은 시점 호스트 MemAvailable 최소 4482 MiB(다른 담당자의 스택과 빌드 포함).
- [실측] CPU 평균: gz-gui 103%(p95 143%), gazebo 29%, px4 17%, foxglove 17%, lichtblick 0%. RTF 0.9877(호스트 load1 평균 16).
- 못 한 것: QGC(AppImage가 cache에 없고 호스트에 화면과 Xvfb가 없다), 브라우저 쪽 Lichtblick 메모리(브라우저는 사용자 기계에서 돈다), GPU 경로의 gz-gui.

의견(사용자 절차 초안, 화면 세션이 있는 호스트에서)
1. `tools/stack.sh up --viz`로 스택과 gz-gui를 올린다. gz-gui에 x500_1이 보이는지 본다.
2. `tools/qgc.sh --stack k`로 QGC를 띄워 기체 연결과 비행 모드 표시를 본다. QGC로 ARM이나 TAKEOFF는 누르지 않는다(통합 테스트 노드와 명령 source가 섞인다).
3. `foxglove`와 `lichtblick`을 `--profile viz`로 올리고 브라우저에서 `http://127.0.0.1:18080+k/?ds=foxglove-websocket&ds.url=ws://127.0.0.1:8765+k`를 연다. 원격이면 두 포트를 `ssh -L`로 넘긴다.
4. 통합 테스트(또는 미션 goal 하나)를 돌리며 세 화면에서 같은 이륙-호버-착륙을 본다. Lichtblick Plot에서 setpoint z와 `vehicle_local_position` z가 함께 움직이는지 본다.
5. 끝나면 `docker compose -p idsim-<k> stop gz-gui foxglove lichtblick`, QGC 종료, `tools/stack.sh down`.
- 메모리가 모자라면 gz-gui와 Lichtblick을 따로 확인한다(사용자 결정 사항 8번과 같은 질문).

화면 도구가 판정에 영향을 주지 않는다는 근거
- [문서] `docs/architecture.md` 222행: 본 스택 서비스는 `viz` 서비스에 `depends_on`하지 않고, 프로필 서비스는 `up --wait`에 들어가지 않으며, `run_smoke.sh`, pytest fixture, CI는 프로필을 켜지 않는다.
- [실측] foxglove_bridge는 clientPublish, services, parameters capability를 알리지 않았다. 브라우저에서 토픽 버스에 쓸 길이 없다.
- [소스] `ros_ws/src/idsim_sim/config/gui.config`에 WorldControl이 없어 GUI에서 월드를 멈추거나 스텝 실행할 수 없다.
- [실측 근거의 의견] 판정은 `/clock` 기준이라 RTF가 떨어져도 판정 값은 바뀌지 않아야 하고, 측정한 RTF 하락은 1.3% 이내였다. 다만 벽시계 상한(`up --wait`, pytest 전체 timeout)은 RTF 하락만큼 여유가 줄어든다.
- [추정] 남는 영향: foxglove_bridge가 구독하면 PX4 out 토픽에 DDS reader가 늘고, gz-gui는 Gazebo의 scene/state 구독자가 된다. 둘 다 CPU를 쓰지만 쓰기 경로가 없다. 판정 시간 축에 미치는 효과는 위 RTF 수치 이상으로 보지 않는다.

## S4. bridge 설정 파일

결론: 6단계에 파일로 만들되, 생성기가 만드는 파일이 아니라 `idsim_sim`의 고정 파일(`ros_ws/src/idsim_sim/config/bridge.yaml`)로 두고 생성기는 마운트와 `config_file` 인자만 넣기를 제안한다. 실측 없는 의견이다.

- [추정] ros_gz_bridge YAML 항목(`ros_topic_name`, `gz_topic_name`, `ros_type_name`, `gz_type_name`, `direction`, `lazy`)에는 스택 번호 k나 기체 목록에 따라 바뀌는 값이 없다. 스택 격리는 `GZ_PARTITION` 환경변수가 맡는다. 1a의 내용은 `/clock` 한 줄(`direction: GZ_TO_ROS`, `lazy: false`)이다. 생성할 이유가 없다.
- 6단계에 두는 이유: 1b의 금지 토픽 검사(운용 노드는 Gazebo 토픽을 보지 않는다, bridge는 허용 목록만)를 명령 인자 문자열이 아니라 YAML 목록 하나에 대해 하게 된다. 1b에서 표적 항목이 더해져도 검사 방식이 그대로다.
- 1b에서 생성으로 바꿀 수 있는 경우: 표적 수나 이름이 `fleet.yaml`에서 오고 그것이 Gazebo 토픽 이름에 들어갈 때다. 다만 스크립트 궤적 Actor의 pose가 서버 토픽에 나오지 않는다는 기존 실측이 있어 표적 경로 자체가 1b 착수 때 정해지므로, 지금 생성 규칙을 만들지 않는다.
- [추정] 파일화로 healthcheck(`ros2 topic echo --once /clock`)는 바뀌지 않는다. 생성기 golden은 bridge의 `command`가 바뀌므로 다시 만들어야 한다(devops).

## 부딪칠 것으로 보이는 지점

- D4(생성기가 bridge 설정 파일을 생성)와 S4(고정 파일). 내 근거는 내용에 파생값이 없다는 것 하나다.
- 충돌 1: ROS 시각 timer의 sim 주기는 4 ms 양자화(48/52 ms) 외에는 안정적이었고 벽시계 끊김(최대 157 ms)은 `/clock` 자체의 끊김과 겹쳤다. 이 끊김이 Gazebo 정지인지 DDS 전달 지연인지는 가르지 못했다.
- 기록 정정: "Lichtblick 2.5.2"는 Caddy 버전이고 이미지 안 Lichtblick은 1.30.0이다. architecture.md 106행과 progress.md 결정 기록을 architect가 고칠지 정한다.
- devops 관례와 lichtblick 컨테이너: 이미지 entrypoint가 root로 `/src/index.html`을 다시 쓰므로 호스트 uid:gid 실행이나 읽기 전용 루트 파일시스템을 바로 쓸 수 없다. 호스트에 쓰는 파일은 없다.
- D10: 호스트에 사용자 화면 세션이 없을 때(SSH만) gz-gui와 QGC를 어디서 보는지. 사용자 결정 사항 8번에 더해야 할 수 있다.

## 실험하지 못한 것

- 경합 없는 RTF와 CPU: 다른 담당자의 스택과 빌드가 측정 내내 돌았다.
- QGC 메모리와 RTF 영향, GPU 경로의 gz-gui: 호스트에 화면 세션과 QGC cache가 없었다.
- Lichtblick 브라우저 화면(Plot 패널, `ds.url` 자동 접속, 기본 layout 적용): 브라우저가 호스트에 닿지 않는다. 사용자 확인이 필요하다.
- `/clock` 끊김의 원인 분리(Gazebo 정지 대 DDS 지연): PX4 timestamp 동시 기록이 필요하다.
- 3대 시나리오 측정: 6단계 범위가 아니라 하지 않았다.

## 재질문 답(2026-11-11)

결론: 경합 없는 10분과 의도한 CPU 부하 5분 모두에서 ROS 쪽 `/clock` 도착 끊김 최대는 25.9 ms다(뒤집기 조건 0.5 s의 1/19). 1번 결정(ROS 시각 timer)을 뒤집을 근거는 없다. 20 ms를 넘은 끊김은 두 구간을 합쳐 2회뿐이었다. 하나는 전달 지연(Gazebo 발행은 4 ms 간격 그대로)이고, 다른 하나는 Gazebo 스텝 자체가 늦은 것(발행 간격 17.1 ms)이다. 지난번 106 ms는 이번 조건에서 재현되지 않았다.

실측 조건
- 스택 k = 5(`tools/stack.sh up --stack 5`, 실행 id 20261110-155640-k5, 기체 1대, standalone, headless), 이미지 `idsim/*:local`, 4 vCPU, 메모리 7.9 GB.
- 시작 전: `docker ps -a` 비어 있음, load1 0.66, MemAvailable 6.1 GB. 측정 중 8초마다 기록한 `docker ps`에는 idsim-5의 4개 서비스와 내 탐침 컨테이너(`sim_rq_main`, 부하 구간에는 `sim_rq_load`)만 있었다.
- 단독 구간 602 s: load1 평균 4.44(1.40-6.30). 스택과 탐침 자신의 부하다. 컨테이너 CPU 평균은 gazebo 83%, px4 50%, 탐침 68%, bridge 11%, 에이전트 8%(`docker stats`, 한 코어 = 100%).
- 부하 구간 299 s: 이미지 `idsim/ros-base:local`로 컨테이너 하나를 띄워 python busy loop 프로세스 4개(vCPU 수만큼)를 300 s 돌렸다. CPU 제한과 nice는 주지 않았다. 부하 컨테이너 CPU 평균 331%, load1 평균 7.40(6.49-8.34). 지난번 경합 구간(load1 6-19, 이미지 빌드의 디스크와 메모리 압박 포함)보다 CPU만 누르는 가벼운 조건이다.
- 탐침(scratchpad `rq/`)
  - `gz_rec.py`: gazebo 컨테이너 안에서 gz-transport Python으로 gz `/clock`과 `/stats`를 구독한다. 수신 벽시각, sim 시각, `Clock.system`(서버가 메시지를 만든 벽시각)을 기록한다.
  - `ros_rec.py`: 별도 컨테이너(host network, `use_sim_time` 참)에서 bridge 뒤 `/clock`, `vehicle_local_position_v1`, `vehicle_status_v1`, `failsafe_flags`의 수신 벽시각, PX4 timestamp, 수신 시 ROS 시각을 기록한다. ROS 시각 50 ms timer로 `offboard_control_mode`(position)와 `trajectory_setpoint`를 실제 `/px4_1/fmu/in`에 발행한다(비시동. arm과 모드 명령은 보내지 않는다).
  - 두 컨테이너는 같은 호스트 벽시계를 쓰므로 sim 시각을 열쇠로 Gazebo 발행 시각과 ROS 도착 시각을 맞춘다. 분석은 `ana.py`가 한다.
- 정리: `tools/stack.sh down --stack 5`, 탐침과 부하 컨테이너 삭제, 남은 컨테이너 0개 확인. scratch 이미지 `idsim-scratch/ros-ws-foxglove:sim`, `idsim-scratch/sim-xvfb:sim`은 지웠다. 저장소 파일은 이 절 말고 바꾸지 않았다.

수치(단독 / 부하)

| 값 | 단독 602 s | 부하 299 s |
| --- | --- | --- |
| ROS `/clock` 도착 간격 p50, p99, p999, 최대 | 4.00, 5.47, 7.09, 25.90 ms | 4.00, 6.98, 9.79, 21.08 ms |
| 그중 20 ms 초과, 50 ms 초과 | 1, 0 | 1, 0 |
| sim 증가(메시지마다) | 모두 4 ms(빠짐과 중복 없음) | 모두 4 ms |
| Gazebo 발행 간격(`Clock.system`) p99, 최대 | 4.21, 16.14 ms(아래 주의) | 5.85, 17.10 ms |
| 전달 지연(Gazebo 발행 -> ROS 도착) p50, p99, p999, 최대 | 1.59, 3.52, 6.16, 22.84 ms | 1.42, 4.40, 7.02, 13.53 ms |
| RTF(`/stats` sim_time/real_time) | 0.9994, 249.8 Hz | 0.9981, 249.5 Hz |
| ROS 시각 timer의 벽시계 간격 p99, 최대, 100 ms 초과 | 54.42, 67.72 ms, 0회 | 56.11, 70.32 ms, 0회 |
| ROS 시각 timer의 sim 간격 | 44-56 ms(4 ms 양자화, p50 48) | 44-56 ms |
| setpoint timestamp의 묵음(PX4 현재 시각 추정 - stamp) 최대 | 7.6 ms | 10.5 ms |
| `vehicle_status.timestamp` 수신 시 ROS 시각 - timestamp | -4 - 4 ms | -8 - 8 ms |
| `vehicle_local_position_v1` 같은 차 | -4 - 24 ms | -12 - 20 ms |
| `failsafe_flags.offboard_control_signal_lost` 참 | 0/1115 | 0/554 |
| `vehicle_status` (nav_state, failsafe) | (4, 거짓)만 | (4, 거짓)만 |

끊김의 원인 분리
- [실측] 단독 t = 12.3 s: ROS 쪽 25.9 ms 끊김, 같은 두 sim 시각의 Gazebo 발행 간격 4.0 ms, 끊김 뒤 첫 메시지의 전달 지연 22.8 ms. Gazebo는 멈추지 않았고 bridge, DDS, 탐침 수신 중 어딘가의 전달 지연이다. 이 경우 PX4 시각은 흐르고 ROS 시각만 늦는다. 그래서 setpoint stamp가 그만큼 묵지만, 측정한 묵음 최대는 7.6 ms였다(timer 발화가 다음 `/clock` 뒤로 밀리면서 일부가 상쇄된다).
- [실측] 부하 t = 654.0 s: ROS 쪽 21.1 ms, Gazebo 발행 간격 17.1 ms, 전달 지연 6.1 ms. 주된 원인은 Gazebo 스텝이 늦은 것이다. lockstep이라 PX4 시각도 같이 늦으므로 묵음이 생기지 않는다.
- [실측] 두 종류 모두 지속 시간이 수십 ms 단위이고 sim 증가에 빠짐이 없다. PX4의 손실 판정(묵음 1 s 초과)과는 두 자리 차이다.
- [추정] 지난번 106 ms(load1 6-19)는 이번 CPU 부하(load1 7.4)로는 재현되지 않았다. 차이는 그때 함께 돈 이미지 빌드의 디스크와 메모리 압박이다. 원인을 그것으로 확정하지는 않았다.

주의
- `Clock.system`에는 기록 이상이 2회(t = 170, 180 s 근처) 있었다. 초 경계에서 nsec가 0이고 sec가 1 작은 값이 한 메시지씩 찍혀 발행 간격이 +1004/-996 ms로 보인다. 같은 메시지의 수신 벽시각과 sim 시각은 정상이라 Gazebo의 system 시각 기록 문제로 보고 제외했다. 위 표의 단독 Gazebo 발행 간격 최대는 system 시각이 수신 시각과 0.5 s 넘게 어긋난 메시지 2개를 뺀 값이다. 단독 구간의 Gazebo 발행 간격 16.14 ms는 ROS 쪽 끊김(20 ms 초과)으로 이어지지 않았다.
- 묵음 추정은 직전 `vehicle_local_position_v1`의 PX4 timestamp에 그 뒤 흐른 벽시각을 더한 값으로 PX4 현재 시각을 잡는다(RTF 1 가정, 도착 지연만큼 작게 잡힌다). 음수는 stamp가 추정보다 앞선 것이다(최소 -18.5 ms).
- 결정 기록 330-338행 재측정 목록의 값 갱신 제안: `/clock` 끊김 최대 106 -> 25.9 ms, `vehicle_status.timestamp` 차 최소 -176 -> -8 ms, ROS 시각 timer 벽시계 간격 최대 157.6 -> 70.3 ms, RTF 0.988-0.998 -> 0.998-0.999. 1번 결정의 여유 근거(4)는 수치만 바꾸면 그대로 성립한다.
