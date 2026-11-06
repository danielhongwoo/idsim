# idsim 진행 상황

이 폴더는 에이전트와 작업자가 세션을 시작할 때 현재 상태를 파악하기 위한 기록이다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`에 두고, 여기에는 무엇이 끝났고 무엇이 진행 중이며 다음에 무엇을 할지만 적는다. 날짜는 항상 절대 날짜(YYYY-MM-DD)로 쓴다.

## 현재 상태 (2026-11-06)

- 저장소: 원격 github.com/danielhongwoo/idsim. 첫 커밋(문서와 규칙)만 올라가 있고, 스모크 구현과 이후 문서 변경은 아직 커밋 전이다.
- 개발 호스트: docker buildx 0.30.1 설치. 같은 호스트에 다른 compose 프로젝트(`docker`: open_manipulator, zenoh_daemon, cyclo_manager 등)가 host 네트워크로 떠 있다. compose 명령은 항상 `-p idsim-smoke`로 한다.
- Phase 1a 1단계 환경 스모크 테스트 S0부터 S5까지 로컬에서 모두 통과(스택 번호 0, 도메인 20). 설계는 `docs/smoke-test-phase1a.md`.
- 이미지 5종 빌드 완료: ros-base 838MB, sim-base 2.97GB, px4 3.06GB(builder 단계 7.7GB), ros-ws 1.57GB, xrce-agent 153MB. 전체 재빌드는 부분 캐시로 약 2분 30초, PX4 첫 빌드는 이 호스트(16 vCPU)에서 163초.
- 골든 첫 생성: `tests/fixtures/px4/v1.17.0/`(토픽 65, qos 27, env 4키). 재실행 `--check` 일치.
- 산출물: `artifacts/smoke/`에 실행 기록이 약 1.2GB 있고 root 소유라 일반 권한으로 지워지지 않는다(git 비추적).
- 2026-11-06: Phase 1a 2단계 CI 골격 작성. lint(11종, 대상 없는 4종은 PASS-NO-TARGETS)와 build(이미지별 키, 레지스트리에 키가 있으면 건너뜀, PR은 빌드만, main만 GHCR 푸시) 워크플로. 로컬 검증 통과, GitHub 첫 실행은 PR에서 한다.
- 다음 작업:
  1. CI 골격 PR을 올리고 첫 실행 결과 확인: 러너 디스크 여유, 빌더 캐시 누적, px4 빌드 완주와 총 시간, 없는 buildcache를 cache-from으로 줄 때 경고로 끝나는지.
  2. main 합치기 전 결정: push 모드에서 GHCR 조회가 403이면 지금은 "키 없음"으로 보고 빌드해 같은 키 태그를 덮어쓸 수 있다. 로그인한 토큰으로 없는 패키지를 조회할 때 GHCR가 무엇을 주는지 PR 실행에서 보고 정한다.
  3. 첫 main 푸시 뒤 사용자가 GHCR 패키지 5개와 buildcache를 Public으로 바꾼다. 비공개면 포크 PR과 익명 조회가 403을 받아 매번 전체를 다시 빌드한다.
  4. 다음 PR: Dockerfile.px4의 pip 고정과 PX4_OPTICAL_FLOW_REF 반영, `ls | grep` 정리(px4-engineer). Dockerfile.sim-base의 GZ_APT_KEY_FPR 검증(sim-engineer). ruff 임시 예외 정리(test-engineer). 설계 문서의 키 재료와 KEY_<이미지> 설명 갱신(architect). image_keys.py가 bake 블록의 tags와 공백까지 해시하는 것 정리, lint가 같은 저장소 PR에서 두 번 도는 것(devops-engineer).
  5. roadmap 1a 3단계 `config/fleet.yaml`과 `tools/gen_compose.py`.

## Phase별 진행

| Phase | 상태 | 마지막 갱신 | 비고 |
| --- | --- | --- | --- |
| 1a | 1단계 완료, 2단계 CI 골격 작성(GitHub 첫 실행 전) | 2026-11-06 | 스모크 설계는 `docs/smoke-test-phase1a.md` |
| 1b | 시작 전 | 2026-11-06 | |
| 2 | 시작 전 | 2026-11-06 | |
| 3 | 시작 전 | 2026-11-06 | |

## 결정 기록

- 2026-11-06: 지원 호스트는 x86_64 Linux만. arm64(Apple Silicon Mac, Jetson Orin)는 Linux 환경이 Phase 3까지 완전히 동작한 뒤 확장 단계에서 검토.
- 2026-11-06: ROS 2 rmw는 CycloneDDS로 고정. FastDDS의 컨테이너 간 공유 메모리 함정을 피하기 위함. uXRCE-DDS Agent는 내부 FastDDS 그대로 두고 RTPS로 상호 운용.
- 2026-11-06: 기체 번호는 1부터, 네임스페이스는 항상 `PX4_UXRCE_DDS_NS`로 명시. 인스턴스 0의 네임스페이스 없음 케이스는 쓰지 않음. 모든 식별자는 `config/fleet.yaml`에서 파생.
- 2026-11-06: 표적은 `TargetState` 계약으로만 소비. Gazebo pose는 `idsim_sim` 어댑터가 변환. 표적 엔티티는 Gazebo Actor.
- 2026-11-06: 시간의 정식 기준은 `/clock`(시뮬레이션 시간). rosbag2 기록은 `--use-sim-time`, `/clock`은 미기록.
- 2026-11-06: 통합 테스트는 launch_testing 대신 compose fixture + rclpy. pytest는 `ros-ws` 컨테이너 안에서 실행.
- 2026-11-06: 베이스 이미지를 `ros-base`와 `sim-base`로 분리. 버전은 `docker/versions.env` 한 곳에서 고정.
- 2026-11-06: 3대 SITL 시나리오는 nightly 전용. PR에서는 단일 기체만.
- 2026-11-06: 저장소는 공개. CI는 GitHub Actions 무료 러너(4 vCPU) 한도 안에서만 쓴다.
- 2026-11-06: 브라우저 게이트웨이는 Rust(tonic + axum)로 구현. Rust는 ROS 2 비의존 컴포넌트에만 쓴다.
- 2026-11-06: 이미지 레지스트리는 ghcr.io/danielhongwoo/idsim. 공개 저장소의 공개 패키지로 둔다.
- 2026-11-06: 스모크 S1(인스턴스 0, 진단용)은 로컬에서 1회만 실행하고 CI에는 넣지 않는다.
- 2026-11-06: 이미지는 5종(ros-base, sim-base, px4, ros-ws, xrce-agent). 사용자 승인.
- 2026-11-06: Fleet Manager 구현 언어는 C++로 확정. gRPC 서버 스레드와 rclcpp executor가 공유하는 상태는 명시적으로 보호하고 설계 문서에 표로 남긴다.
- 2026-11-06: PX4 태그는 v1.17.0, px4_msgs는 release/1.17의 커밋 SHA, PX4-gazebo-models는 v1.17.0 서브모듈이 가리키는 b6127f4ec20de867e215fb5f78ae88b80f371909, Agent는 v2.4.3. v1.16.2를 버린 이유: 두 태그 사이에 메시지 버전이 바뀐 토픽이 있어(VehicleLocalPosition 0 -> 1) 어차피 태그별 골든이 필요하고, 정식 최신이 매핑 설계를 가장 세게 시험한다. 스모크 S4 통과가 확정 조건이며 실패하면 이 결정으로 돌아온다.
- 2026-11-06: 스모크 S1은 `make px4_sitl gz_x500`을 문자 그대로 돌리지 않고 runtime 이미지의 `px4` 바이너리를 `-i` 없이 실행한다. make 타깃이 하는 일은 `PX4_SIM_MODEL=gz_x500 GZ_IP=127.0.0.1`을 주고 rootfs에서 px4를 실행하는 것뿐이라 rcS 경로가 같다. make는 builder 스테이지 안에서만 쓴다. S1은 인스턴스 0을 쓰는 유일한 예외다.
- 2026-11-06: 스모크 타임아웃은 예외적으로 벽시계. 1단계에는 `/clock` 브리지가 아직 없기 때문이다. `/clock` 공급 주체는 `bridge` 서비스(ros-ws + ros_gz_bridge)이며 1b에서 1a로 당긴다. 1단계 S5에서 와이어 호환 실측용으로 처음 올라오고, 노드와 테스트는 6단계부터 이것을 시간 기준으로 쓴다.
- 2026-11-06: px4 healthcheck는 토픽 수신 대신 컨테이너 안 `px4-uxrce_dds_client --instance N status`의 문자열 판정. 종료 코드가 연결 상태를 반영하지 않아 문자열로 본다. 모든 서비스 `restart: no`.
- 2026-11-06: 토픽 이름 매핑은 `MESSAGE_VERSION`에서 컴파일 시점 파생이 단일 출처, 키는 논리 이름과 타입의 쌍. 태그별 손 매핑 테이블은 두지 않는다. 골든은 `tests/fixtures/px4/<PX4_TAG>/`에 결정적 값만 추적하고 측정 주기는 골든에서 제외. 골든 디렉터리가 없으면 단위 테스트는 SKIP이 아니라 FAIL. 갱신은 `--update-golden`과 px4, ros2 담당자의 diff 승인.
- 2026-11-06: 측정 주기는 계약이 아니라 참고값. 수신 판정은 "T초 안에 1회 이상". 주기 하한 계약은 Phase 3에서 Fleet 타임아웃이 필요한 토픽에만.
- 2026-11-06: 모델은 sim-base `/opt/px4-gz` 한 벌. px4 runtime은 복사하지 않고 심볼릭 링크로 gz_env.sh의 빌드 경로를 살린다. 공유 볼륨은 CI 캐시와 맞지 않아 쓰지 않는다. px4 builder가 서브모듈 커밋을 `versions.env`와 대조.
- 2026-11-06: sim-base의 Gazebo는 OSRF apt(PX4 gz_bridge가 그 헤더를 찾음), ros-ws의 ros_gz_bridge는 ROS vendor gz-transport. 한 프로세스에 둘이 섞이는 경로가 없어 와이어 호환만 문제이며 스모크 S5가 실측한다. 실패하면 bridge만 sim-base 계열로 옮긴다.
- 2026-11-06: xrce-agent 이미지는 ubuntu:24.04 digest 베이스의 별도 이미지(5종째). ros-base 위에 올리면 소스 빌드한 Fast-DDS가 `/opt/ros/jazzy`와 섞일 수 있고, CI에서 레이어 공유 이득이 없다. 에이전트에는 `ROS_DOMAIN_ID`를 주지 않는다(도메인은 PX4 client가 넘긴다).
- 2026-11-06: cyclonedds.xml은 환경변수 치환 없는 고정 파일 하나(유니캐스트 피어 127.0.0.1, 멀티캐스트 끔. 처음의 lo 인터페이스 고정은 같은 날 S1 실측 후 철회, 아래 결정 참조). 설정 없음과의 비교는 `CYCLONEDDS_URI`를 비워서. 멀티 호스트는 그때 gen_compose가 생성.
- 2026-11-06: 스택 오프셋에 `GZ_PARTITION` 추가. 판정 QoS는 `sensor_data` 하나, 상태 전이는 "최신 상태 N회 연속"으로 판정.
- 2026-11-06: Offboard 손실 동작 파라미터 이름은 `COM_OBL_RC_ACT`(4 = Land). 설계 문서가 적어 온 `COM_OBL_ACT`는 v1.17.0에 없는 이름이며, 잘못된 이름은 rcS `param set`이 오류만 찍고 넘어가 기본값이 남는다. 문서 전체를 고쳤고 S4의 `param show` 저장값에서 값 4를 확인한다.
- 2026-11-06: px4 실행 명령은 `px4 -i N`(이미지가 `build/px4_sitl_default/bin`을 PATH에 넣음). 작업 디렉터리 `rootfs` 기준으로 `bin/px4`는 존재하지 않는다.
- 2026-11-06: 버전 키 이름은 `versions.env`의 것을 따른다. 골든 `env.txt`와 설계 문서의 `PX4_MSGS_SHA`를 `PX4_MSGS_REF`로 통일. 이유: versions.env가 단일 출처이고 `PX4_GZ_MODELS_REF`, `PX4_ROS_COM_REF`와 일관.
- 2026-11-06: gazebo 서비스는 PX4-gazebo-models 원본 `server.config`에서 PX4 전용 플러그인 두 줄(`libOpticalFlowSystem.so`, `libGstCameraSystem.so`)을 뺀 `/opt/px4-gz/server.idsim.config`를 쓴다. sim-base가 생성하고 지운 줄 수 2를 검사, 원본은 px4 builder diff 검사용으로 유지, px4 runtime의 `gz_bridge/server.config` 링크도 이 파일로. gz_plugins를 sim-base에 넣는 안은 OpenCV, GStreamer 의존과 비재현 빌드 때문에 기각. x500 기본 모델에 카메라와 광류 센서가 없다.
- 2026-11-06: gazebo 서비스는 `gz sim -s`만 쓰고 `--render-engine` 플래그를 주지 않는다. x500 월드에 렌더링 센서가 없어 렌더 엔진이 초기화되지 않고, ogre 1.x는 X 없이 돌지 않는다(sim-engineer, gz-rendering8 소스). `HEADLESS`, `PX4_GZ_SIM_RENDER_ENGINE`은 rcS 전용임이 소스로 확인. 카메라를 쓰는 확장 단계에서 ogre2 + `--headless-rendering` + llvmpipe.
- 2026-11-06: px4_ros_com은 release/1.17 브랜치가 없어 `PX4_ROS_COM_REF`를 release/1.16 HEAD와 같은 main 커밋 86e9aeb로 고정. `frame_transforms`의 v1.17.0 호환은 가정이며 1a 4단계에서 확인, 안 맞으면 `idsim_common`이 변환을 직접 구현.
- 2026-11-06: 1단계 임시 규칙으로 스택 오프셋은 `run_smoke.sh`가 `ROS_DOMAIN_ID`, `GZ_PARTITION`, `IDSIM_AGENT_PORT`로 계산해 compose에 넘긴다. compose 보간이 산술을 못 하기 때문이다. 1단계에서 compose 직접 실행은 지원하지 않으며 3단계 `gen_compose.py`가 대체한다.
- 2026-11-06: `config/cyclonedds.xml`에서 `NetworkInterface` 고정을 뺀다. 유니캐스트 피어 127.0.0.1, 멀티캐스트 끔, `ParticipantIndex auto`만 남긴다. 설계 토론의 "lo + 피어로 Fast DDS 에이전트와 SPDP 성립"은 추측이었고 S1 실측에서 틀렸다. 에이전트는 호스트 인터페이스 주소만 광고하고 `interfaceWhiteList` 프로필을 적용하지 않는다. 고정을 빼면 fmu 토픽 65개 확인.
- 2026-11-06: 격리는 도메인 ID로만 한다. 기본 스택 오프셋 k=0에서 `ROS_DOMAIN_ID` = 20 + k, 에이전트 포트 = 8888 + k, `GZ_PARTITION` = `idsim-<k>`. 도메인 0은 같은 호스트의 다른 ROS 2 스택(개발 호스트에 open_manipulator, zenoh 등이 host 네트워크로 떠 있음)이 쓰므로 피한다. CI도 같은 규칙, 예외 없음. px4 서비스에도 같은 `ROS_DOMAIN_ID`. `GZ_PARTITION`은 항상 명시해 다른 Gazebo 인스턴스와 분리.
- 2026-11-06: 모든 compose 파일은 `name:`을 명시한다. `gen_compose.py`도 `idsim-<k>`를 넣는다. 미지정 시 디렉터리명 `docker`가 프로젝트 이름이 되어 충돌한 사고가 있었다.
- 2026-11-06: 설계에 적힌 판정은 전부 1차 구현 범위. 가정의 반증 지점(특히 `param show` 저장값의 `COM_OBL_RC_ACT` = 4, `COM_RC_IN_MODE` = 4, `commander check`)이 구현에 없으면 파라미터 이름 오타 같은 조용한 실패를 못 잡는다. S1 복구 후 S2 전에 채운다.
- 2026-11-06: 이미지는 빌드 버전을 `IDSIM_BUILD_<키>` ENV로 남기고 `run_smoke.sh`가 S0 전에 `versions.env`와 대조해 다르면 실패. 골든 `env.txt`의 값은 이미지 ENV에서 읽는다. `versions.env`만 올리고 이미지를 안 올린 채 옛 측정값이 새 골든이 되는 것을 막는다.
- 2026-11-06: embedded px4 서비스에는 `HEADLESS=1`을 준다(rcS가 읽어 GUI를 띄우지 않음, 실측). "HEADLESS를 주지 않는다"는 gazebo 서비스에만 해당한다.
- 2026-11-06: px4는 데몬 모드 `px4 -d`로 실행한다. 컨테이너 stdin이 닫힌 상태에서 대화형 pxh 셸이 프롬프트를 끝없이 출력해 로그가 단계당 수십 MB, 15분 방치 시 4GB까지 불었다. `-d`에서 로그 36MB가 54KB로 줄었고 `px4-commander`, `px4-param`, `px4-uxrce_dds_client` 모듈 명령은 그대로 동작한다.
- 2026-11-06: airframe `4001_gz_x500`이 `NAV_DLL_ACT`를 `set-default 2`로 덮어써 `PX4_PARAM_NAV_DLL_ACT=0`이 무시된다(펌웨어 기본값과 같은 값은 변경으로 기록되지 않기 때문). px4 이미지에 공식 훅 `etc/init.d-posix/airframes/4001_gz_x500.post`를 넣어 `PX4_PARAM_*`를 다시 적용한다. 다른 기체를 쓰면 같은 훅이 필요하다.
- 2026-11-06: `artifacts/`의 root 소유 파일 문제는 1단계에서 감수하고 3단계 `gen_compose.py`의 `user` 매핑에서 닫는다. 지금 비루트 사용자를 넣으면 ros-ws 이미지의 HOME과 로그 디렉터리 설정이 따라와 스모크 범위가 커진다.

## 미해결 사항

사용자 결정이 필요한 항목.

- 없음.

아직 열린 항목.

- 스모크는 호스트당 하나만 돌린다. compose 프로젝트 이름이 스택 번호와 무관하게 `idsim-smoke`라 k=0과 k=1을 같은 호스트에서 동시에 돌리면 서로의 컨테이너를 재생성하거나 내린다. 3단계 `gen_compose.py`가 `idsim-<k>`를 넣을 때 해결.
- 비결정 빌드 요소: PX4-OpticalFlow master(px4 builder, 결과물은 버려짐), empy 외 pip 패키지 미고정, ros.key와 gazebo.gpg URL 미고정. 2단계 CI 캐시 키를 정할 때 처리.
- 이미지 ENV와 `versions.env` 대조가 S0에서만 일어난다. S1-S5를 단독 실행하면 대조가 없다.
- `GZ_IP=127.0.0.1`을 빼면 gz-transport 디스커버리가 불안정한지(추측). 지금은 명시하고 가며 제거 비교는 하지 않았다.
- `artifacts/`를 CI 잡 아티팩트로 업로드(가정, CI 골격에서 확인).
- `frame_transforms`(px4_ros_com main 커밋)와 v1.17.0 px4_msgs의 호환(1a 4단계).
- Phase 3 주기 하한 계약이 필요한 토픽 목록(px4-engineer, Phase 3 전에).

2026-11-06 실측으로 닫힌 항목.

- `OffboardControlMode`에 `MESSAGE_VERSION` 상수 없음(ros-ws 이미지 `ros2 interface show`, 상수 0개). `VehicleStatus`는 1. versioned 34개 중 9개가 1, 25개가 0(`TrajectorySetpoint`, `VehicleCommand`, `VehicleCommandAck`는 0). `ArmingCheckReply.msg`만 등호 앞 공백 두 칸.
- px4_msgs `PX4_MSGS_REF`(86d8239e)와 PX4 v1.17.0 msg 235개 diff 0.
- PX4 `gz_bridge/server.config`와 PX4-gazebo-models `server.config` 동일. 그 파일의 PX4 전용 플러그인 두 줄은 sim-base에서 로드 실패하지만 서버는 정상(위 결정 기록).
- `gz sim -s` 헤드리스 서버 기동, `scene/info` 서비스, `/clock` 토픽 확인(sim-base 단독).
- `HEADLESS`, `PX4_GZ_SIM_RENDER_ENGINE`은 rcS 전용(소스 확인). ogre 1.x는 X 없이 불가.
- SITL 파라미터 값 확정: `COM_OBL_RC_ACT` 4, `COM_OF_LOSS_T` 1.0, `NAV_DLL_ACT` 0, `COM_RC_IN_MODE` 4, `COM_DISARM_PRFLT` -1, `SDLOG_MODE` 2. 근거 주석은 `config/px4/sitl_params.env`.
- 이미지 크기: ros-base 838MB, xrce-agent 153MB, sim-base 2.97GB, ros-ws 1.57GB, px4 3.06GB.
- 스모크 S0-S5 전체 통과로 닫힌 것:
  - uxrce status 연결 문자열은 `Running, connected`(끊기면 `Running, disconnected`).
  - `/proc/net/udp`에서 에이전트 포트 행이 보여 healthcheck가 동작한다.
  - 서브모듈 얕은 클론으로 PX4 빌드가 끝나고 `ver all`이 `Release 1.17.0`.
  - ros-ws의 저장소 마운트 `/opt/idsim`이 동작한다.
  - `COM_RC_IN_MODE=4`에서 `commander check`가 `Preflight check: OK`. `COM_OBL_RC_ACT`, `COM_RC_IN_MODE` 저장값 모두 4.
  - 토픽 이름: 접미사는 `_v1` 하나뿐이고 골든 65개 중 8개에 붙는다(arming_check_reply, arming_check_request, vehicle_attitude_setpoint, airspeed_validated, battery_status, home_position, vehicle_local_position, vehicle_status). `trajectory_setpoint`, `vehicle_command`, `vehicle_command_ack`는 접미사 없음.
  - `vehicle_status_v1` 발행자 QoS: BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST, depth 1.
  - OSRF gz-transport 13.6.0(sim-base, px4)과 ROS vendor gz-transport13 13.6.0(ros-ws)의 와이어 호환. bridge로 `/clock` 수신 확인(S5).
  - 시동과 시동 해제 왕복(S3): ack result 0, ARMED와 DISARMED 각각 3회 연속 유지.

그 밖의 항목.

- Phase 1a 완료 기준의 `docs/interface.md`는 아직 없다. 스모크 S4 결과를 `tools/to_interface.py`로 정리한 초안을 ros2-engineer가 낸다.

## 갱신 규칙

- 작업 단위가 끝날 때마다 "현재 상태"와 "Phase별 진행"을 갱신하고, 설계에 영향을 주는 결정은 "결정 기록"에 날짜와 함께 추가한다.
- 설계나 계획 자체가 바뀌면 `docs/`를 고치고, 여기에는 바뀌었다는 사실과 날짜만 남긴다.
