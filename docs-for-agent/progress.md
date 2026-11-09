# idsim 진행 상황

이 폴더는 에이전트와 작업자가 세션을 시작할 때 현재 상태를 파악하기 위한 기록이다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`에 두고, 여기에는 무엇이 끝났고 무엇이 진행 중이며 다음에 무엇을 할지만 적는다. 날짜는 항상 절대 날짜(YYYY-MM-DD)로 쓴다.

## 현재 상태 (2026-11-09)

- 저장소: 원격 github.com/danielhongwoo/idsim. main에 PR #1 CI 골격, #2 큰 그림 다이어그램, #3 시각 도구 로드맵, #4 인계용 진행 기록이 합쳐져 있다. 2b단계는 브랜치 `feat/phase1a-viz-tools`에서 PR로 올린다.
- 첫 개발 호스트(2026-11-06까지): VMware VM, x86_64 Ubuntu 24.04, 16 vCPU, 31GB, NVIDIA 없음, GNOME Wayland. 이 호스트에는 다른 compose 프로젝트(`docker`: open_manipulator, zenoh_daemon, cyclo_manager 등)가 host 네트워크로 떠 있었다. 아래 실측값(빌드 시간, 이미지 크기, Gazebo GUI fps)은 이 호스트 기준이다.
- Phase 1a 1단계 환경 스모크 테스트 S0부터 S5까지 로컬에서 모두 통과(스택 번호 0, 도메인 20). 설계는 `docs/smoke-test-phase1a.md`.
- 이미지 5종 빌드 완료: ros-base 838MB, sim-base 2.97GB, px4 3.06GB(builder 단계 7.7GB), ros-ws 1.57GB, xrce-agent 153MB. 전체 재빌드는 부분 캐시로 약 2분 30초, PX4 첫 빌드는 이 호스트(16 vCPU)에서 163초.
- 골든 첫 생성: `tests/fixtures/px4/v1.17.0/`(토픽 65, qos 27, env 4키). 재실행 `--check` 일치.
- 산출물: 스모크 실행 기록 `artifacts/smoke/`는 git에 추적되지 않으므로 다른 PC로 옮겨지지 않는다. 판정에 필요한 골든은 `tests/fixtures/`에 추적된다.
- 2026-11-06: Phase 1a 2단계 CI 골격 완료. PR #1로 main에 합침(ddbe835). lint(11종, 대상 없는 4종은 PASS-NO-TARGETS)와 build(이미지별 키, 레지스트리에 키가 있으면 건너뜀, PR은 빌드만, main만 GHCR 푸시) 워크플로.
- 2026-11-06: 아키텍처 문서에 큰 그림 다이어그램 추가(PR #2).
- 2026-11-06: 시각 도구 실측(sim-engineer)에 따라 `docs/roadmap.md`와 `docs/architecture.md`에 시각 도구 구성을 반영(1a 2b단계 신설, 3단계 `viz` 프로필, 6단계 foxglove_bridge, Foxglove 표기를 Lichtblick으로).
- CI 첫 실행 결과(PR #1, 2026-11-06): lint 11종 통과, 이미지 5종 콜드 빌드 성공(약 22분: ros-base 44초, xrce-agent 334초, ros-ws 444초, sim-base 51초, px4 255초). 러너 디스크는 정리 전 여유 86GB, 정리 후 114GB, 빌드 뒤 106GB로 문제 없음. 없는 buildcache를 cache-from으로 주면 ERROR 줄이 찍히지만 빌드는 계속된다. 같은 저장소 PR 브랜치에서는 push와 pull_request 트리거로 lint가 두 번 돈다.
- GHCR 조회(2026-11-06): 로그인한 토큰으로 없는 패키지를 조회하면 GHCR는 403이 아니라 not found를 준다(PR #1 실측). 그래서 push 모드는 not found만 "키 없음"으로 보고 권한 거부(denied, 403)는 중단한다. PR 모드와 로컬은 권한 거부도 "키 없음"으로 보고 빌드만 한다.
- 2026-11-09: Phase 1a 2b단계 시각 도구 준비 구현(브랜치 `feat/phase1a-viz-tools`). `tools/qgc.sh`(QGC v5.1.5 AppImage, `versions.env`의 `QGC_VERSION`과 `QGC_APPIMAGE_SHA256`으로 내려받아 `${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/`에 캐시, INT/TERM에 TERM 후 5초 유예, 그다음 SIGKILL), sim-base에 `libqt5svg5`, `ros_ws/src/idsim_sim/config/gui.config`(gz-sim8 기본에서 WorldControl만 제외, 플러그인 17개), `docker/README.md` 시각 도구 절. 로컬 검증: QGC 다운로드, 캐시 재사용, 손상 재다운로드, INT와 TERM 종료 통과. Gazebo GUI는 standalone 스택 위에서 50초 생존, SVG 경고 29건에서 0건, 창 `Gazebo Sim` 존재, `Loaded plugin` 17개에 WorldControl 없음, GUI를 붙여도 서버 RTF 1.0. lint 11종 통과.
- 2026-11-09: 이 호스트에서 archive.ubuntu.com이 IPv4, IPv6 모두 타임아웃(security.ubuntu.com, kr.archive.ubuntu.com, mirror.kakao.com은 정상). 로컬 sim-base와 px4 이미지는 저장소 Dockerfile을 바꾸지 않고 scratch 복사본에 kr 미러 sed 한 줄을 넣어 빌드했다. 따라서 이 호스트의 `idsim/sim-base:local`, `idsim/px4:local`의 apt sources는 kr 미러다. 정식 이미지는 CI가 원본 Dockerfile로 빌드한다.
- 다음 작업:
  1. 첫 main 빌드가 GHCR에 이미지를 올리면 사용자가 패키지 5개와 buildcache를 Public으로 바꾼다. 비공개면 포크 PR과 익명 조회가 403을 받아 매번 전체를 다시 빌드한다. 두 번째 main 실행에서 다섯 이미지 모두 SKIP인지 확인.
  2. 2b PR을 CI 통과 후 main에 합친다. CI에서 sim-base와 px4 이미지가 다시 빌드된다(키 변경). 합친 뒤 사람이 화면으로 확인할 것: standalone 스택 위에서 Gazebo GUI에 x500이 보이는지(에이전트는 창 존재와 엔티티 목록 `x500_1`까지만 확인), `tools/qgc.sh`로 QGC에 기체가 연결되는지.
  2b. 새 PC 재구성 지원(사용자 요청, 2b 다음 별도 PR): 저장소 루트 `README.md`(소개, 호스트 조건, 빌드와 스모크, 문서 지도)와 `tools/check_host.sh`(x86_64, docker 실행 권한, compose v2, buildx, python3, curl, sha256sum, 화면이면 DISPLAY 확인). 아울러 apt 미러를 빌드 인자로 바꿀 수 있게 할지(devops-engineer 판단, 아래 미해결 항목).
  3. CI 후속 PR: Dockerfile.px4의 pip 고정과 PX4_OPTICAL_FLOW_REF 반영, `ls | grep` 정리(px4-engineer). Dockerfile.sim-base의 GZ_APT_KEY_FPR 검증(sim-engineer). ruff 임시 예외 정리(test-engineer). 설계 문서의 키 재료와 KEY_<이미지> 설명 갱신(architect). image_keys.py가 bake 블록의 tags와 공백까지 해시하는 것 정리, lint가 같은 저장소 PR에서 두 번 도는 것(devops-engineer).
  4. roadmap 1a 3단계 `config/fleet.yaml`과 `tools/gen_compose.py`(`viz` 프로필 생성 포함).
  5. 6단계에서 ros-ws에 foxglove_bridge 추가와 Lichtblick 브라우저 실접속 확인.

## 새 개발 PC에서 시작할 때

1. 호스트 조건: x86_64 Linux, Docker와 compose v2, docker buildx, git, gh(GitHub CLI, `gh auth login`). 화면 확인을 하려면 X11 또는 XWayland 데스크톱.
2. 같은 호스트에 다른 ROS 2 스택, Gazebo, compose 프로젝트가 있는지 먼저 본다(`docker ps`, `docker compose ls`). idsim은 ROS 도메인 20 + k, 에이전트 포트 8888 + k, `GZ_PARTITION=idsim-<k>`, compose 프로젝트 `idsim-smoke`를 쓴다. 겹치면 스택 번호 k(`IDSIM_STACK_INDEX`)를 바꾼다.
3. 이미지: `python3 tools/ci/build_images.py --mode load`로 로컬 빌드한다. GHCR 패키지가 Public이면 `ghcr.io/danielhongwoo/idsim/<이미지>:<키>`를 받아 쓸 수도 있다(키는 `python3 tools/ci/image_keys.py`).
4. 확인: `tests/smoke/run_smoke.sh S0`로 이미지 버전과 `docker/versions.env` 일치를 보고, `S2`로 PX4와 Gazebo 연동, 파라미터 저장값을 본다. `tools/ci/lint.sh all`이 통과해야 한다.
5. 사용자 전역 규칙은 저장소 밖에 있다: `~/.claude/CLAUDE.md`(커밋과 PR에 공동 저자 줄을 넣지 않는다). 새 PC에도 같은 파일을 두어야 한다.

## Phase별 진행

| Phase | 상태 | 마지막 갱신 | 비고 |
| --- | --- | --- | --- |
| 1a | 1, 2단계 완료(main), 2b단계 시각 도구 준비 구현 완료, 완료 기준의 화면 확인(x500 육안, QGC 연결)은 사람이 할 것 | 2026-11-09 | 스모크 설계는 `docs/smoke-test-phase1a.md` |
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
- 2026-11-06: Foxglove 화면 앱은 Lichtblick(사용자 결정). 이유: 계정 없이 로컬에서 쓸 수 있고 MPL 라이선스, 공식 이미지(2.5.2, 285MB)를 digest로 고정할 수 있다. 공식 Foxglove 앱은 쓰지 않는다. 브리지는 ros-jazzy-foxglove-bridge 3.6.0(서브프로토콜 foxglove.sdk.v1, 현재 cyclonedds.xml로 채널 69개 수신 실측).
- 2026-11-06: 시각 도구 구성(사용자 결정, sim-engineer 실측 근거). compose 프로필 `viz`에 `gz-gui`(sim-base에서 `gz sim -g`로 기존 서버에 클라이언트만 붙임, WorldControl을 뺀 `gui.config`), `foxglove`(ros-ws + foxglove_bridge, 127.0.0.1, 8765 + k, 토픽 화이트리스트, clientPublish, services, parameters 제외로 읽기 전용), `lichtblick`(공식 이미지 digest 고정, 127.0.0.1의 18080 + k). QGroundControl은 compose 서비스가 아니라 호스트 스크립트 `tools/qgc.sh`(버전과 sha256은 `versions.env`, 캐시, 종료는 TERM 뒤 유예를 두고 SIGKILL). `viz` 프로필은 어떤 서비스의 `depends_on` 대상도 아니고 `run_smoke.sh`, pytest fixture, CI는 켜지 않는다. 3대 시나리오 CPU 측정은 GUI 없이. 로드맵은 1a 2b단계(3단계 전 작은 작업), 3단계 `viz` 프로필 생성, 6단계 foxglove_bridge(Phase 2에서 당김)로 배치. gz 웹 시각화(gz-launch websocket)는 프런트엔드 미성숙으로 보류, VNC는 17 fps에 2코어라 원격 작업이 생길 때만.
- 2026-11-06: Gazebo GUI의 GPU 경로는 실측대로 문서화. 컨테이너 안 OpenGL은 VMware SVGA3D(Mesa 25.2.8, OpenGL 4.3), Xwayland가 DRI3로 렌더 노드를 넘겨 `--device /dev/dri` 없이 약 90 fps. llvmpipe 강제 시 15 fps. sim-base Qt5에 wayland 플러그인이 없어 xcb만. GUI를 붙이면 서버 CPU 21%에서 31%, RTF 1.0 유지.

- 2026-11-09: sim-base에 `libqt5svg5` 추가(sim-engineer 실측). 기존 이미지의 GUI `-v 4` 로그에 SVG 디코딩 경고 29건, 설치 뒤 0건. 추가 의존성 없이 libqsvg.so만 들어온다. 이미지 키가 바뀌어 CI가 sim-base와 px4를 다시 빌드한다.
- 2026-11-09: `idsim_sim/config/gui.config`는 gz-sim8 기본 `/usr/share/gz/gz-sim8/gui/gui.config`에서 WorldControl 블록만 뺀 것(플러그인 17개). gz 버전을 올릴 때는 새 기본 파일에서 같은 방식으로 다시 만든다. 이미지에 넣지 않고 컨테이너에 읽기 전용으로 마운트한다.
- 2026-11-09: QGC 릴리스 자산은 `QGroundControl-x86_64.AppImage`(v5.1.5, 195,332,600바이트), sha256은 GitHub API digest와 대조해 `versions.env`에 고정. `qgc.sh`는 versions.env를 source하지 않고 두 키만 grep으로 읽는다(다른 값에 `@`가 있음).

- 2026-11-09: "QGC AppImage가 SIGTERM을 무시한다"는 2026-11-06 관측은 reviewer 재실험으로 반증됐다. AppRun이 QGC 바이너리를 exec하므로 `qgc.sh`의 자식 PID가 QGC 본체이고, 그 PID에 TERM을 보내면 1초 안에 종료 코드 0으로 끝나며 설정(QGroundControl.ini)이 저장된다. 원래 관측은 FUSE 도우미 PID에 보냈거나 기체 연결 상태의 종료 확인 대화상자였을 가능성이 크다. `qgc.sh`는 TERM -> 5초 유예 -> KILL로 바꿨다(INT는 130, TERM은 143). 기체가 연결된 상태의 TERM 동작은 미실측. 2026-11-09 호스트 재확인: INT는 정상 종료(130), TERM도 끝나지만 한 번은 QGC가 종료 중 segfault를 냈다(프로세스와 마운트 잔재 없음).

- 2026-11-09: `gui.config`에 GridConfig 플러그인 추가(플러그인 18개). PX4 기본 월드(`default.sdf`)는 `<grid>false`, 배경 0.7, 바닥 0.8 회색이라 GUI에서 기체 이동이 보이지 않았다. gz-gui 8의 Grid3D는 QML 리소스가 없어 로드 실패(`Can't find :/Grid3D/Grid3D.qml`). GridConfig는 장면에 격자가 없으면 기본 격자를 만든다.
- 2026-11-09: 기체 출발 위치는 PX4 환경변수 `PX4_HOME_LAT/LON/ALT`(셋 다 필수)로 바꾼다. `px4-rc.gzsim`이 시작 시 `/world/<월드>/set_spherical_coordinates` 서비스를 불러 월드 기준 좌표를 바꾼다(서울시청으로 실측, PX4 `sensor_gps`가 37.5660, 126.9785를 보고). QGC에는 기본 위치 설정이 없고 기체 위치를 따라간다. 저장소에는 README의 덮어쓰기 예시만 두고 정식 값은 3단계 `fleet.yaml`에 넣는다.

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
- 스택 둘의 GCS 포트 충돌(미실측). 두 스택의 PX4가 모두 14550으로 보내고 `MAV_SYS_ID`도 같아 QGC가 기체를 구분하지 못할 것으로 본다. 3단계에서 GCS 포트 기준값을 스택 오프셋으로 분리할 수 있는지 PX4 rcS에서 확인하고, 안 되면 "QGC는 한 번에 스택 하나" 제약을 `docs/interface.md`에 적는다.
- `COM_RC_IN_MODE`=4라 QGC 수동 모드와 가상 조이스틱은 쓸 수 없다. ARM, TAKEOFF(2.5m, `MIS_TAKEOFF_ALT` 기본), LAND, 자동 disarm은 pymavlink로 확인. `docs/interface.md`의 SITL 파라미터 절에 적을 것(ros2-engineer 초안, px4-engineer 확인).
- Lichtblick 2.5.2 공식 이미지의 브라우저 실접속은 미확인. 두 서브프로토콜(foxglove.websocket.v1, foxglove.sdk.v1)을 제시하는 것만 확인했고 foxglove_bridge 3.6.0과의 실제 접속은 1a 6단계에서 확인한다.
- apt 미러 고정 리스크(2026-11-09 실측). Dockerfile이 ubuntu 베이스의 archive.ubuntu.com에 묶여 있어 그 미러가 막히면 새 PC 콜드 빌드가 실패한다. 선택지: 빌드 인자로 미러 지정(이미지 키에 들어가지 않게 할 방법 포함), apt `Acquire::Retries`, GHCR 공개 이미지를 받아 `idsim/<이미지>:local`로 태그하는 `build_images.py --mode pull`. devops-engineer가 2b 다음 PR에서 제안한다.
- WorldControl을 빼도 GUI가 읽기 전용은 아니다. Spawn, Shapes, TransformControl, ComponentInspector가 남아 월드 내용을 바꿀 수 있고, `gz service`로 `/world/<월드>/control`을 부르면 멈출 수도 있다. 3단계 `gz-gui` 서비스에서 편집 플러그인까지 뺄지는 architect 결정.
- `qgc.sh`의 sha256 불일치 시 종료 코드 1 경로는 코드만 있고 실행으로 확인하지 않았다(손상 캐시 재다운로드 경로는 같은 함수를 쓰며 확인됨).
- Gazebo GUI 깜빡임과 장면 미표시(사용자 관측 2026-11-09, VMware + Xwayland). `QSG_RENDER_LOOP=basic`과 `vblank_mode=1`, GridConfig 격자를 적용해도 해결되지 않았다(격자도 보이지 않음). 2026-11-06 실측(SVGA3D 약 90 fps)과 달리 VM의 3D 가속이 꺼져 있을 가능성이 있어 사용자가 3D 가속을 켜고 재부팅해 다시 본다. 재확인 때 컨테이너 안 `glxinfo -B`의 renderer가 SVGA3D인지 llvmpipe인지 먼저 본다(sim-base에는 glxinfo가 없으므로 `apt-get install mesa-utils`로 임시 설치하거나 호스트에서 본다). 다음 후보: SceneBroadcaster `state_hertz`(기본 60) 낮추기(sim-base 서버 설정), GUI 렌더 엔진 ogre(`--render-engine-gui ogre`), 소프트웨어 렌더링(15fps, CPU 부담). 효과가 확인되면 README의 `docker run` 기본 명령이나 3단계 `gz-gui` 서비스 환경에 넣는다.
- 호스트 포트 5900, 8090은 다른 프로젝트의 novnc-server가 쓰므로 VNC를 도입하면 피한다.

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
