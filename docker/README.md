# docker/

idsim의 실행 환경을 이루는 Docker 이미지와 compose 구성이다. 모든 구성 요소는 VM이 아니라 컨테이너로 돈다. 컨테이너는 호스트 커널을 공유하는 프로세스 격리 단위이므로, 기체 여러 대와 시뮬레이터를 PC 한 대에서 가볍게 띄울 수 있다.

지원 호스트는 x86_64 Linux뿐이다. 설계 배경은 [../docs/architecture.md](../docs/architecture.md)의 "Docker Compose 실행 환경 설계" 절, 스모크 테스트 절차는 [../docs/smoke-test.md](../docs/smoke-test.md)에 있다.

## 파일

| 파일 | 역할 |
| --- | --- |
| `versions.env` | 모든 버전의 단일 출처. Dockerfile, bake, compose, CI가 이 파일만 읽는다 |
| `docker-bake.hcl` | 이미지 다섯 종의 빌드 정의와 의존 순서 |
| `Dockerfile.ros-base` | ROS 2 공통 바닥 이미지 |
| `Dockerfile.sim-base` | Gazebo와 PX4 기체 모델 이미지 |
| `Dockerfile.px4` | PX4 SITL 이미지 (멀티스테이지) |
| `Dockerfile.ros-ws` | ROS 2 작업 공간 이미지 |
| `Dockerfile.xrce-agent` | Micro XRCE-DDS Agent 이미지 (멀티스테이지) |
| `ros-ws-entrypoint.sh` | ros-ws 컨테이너 진입 시 ROS 환경을 불러오는 스크립트 |
| `px4/px4-rc.mavlink` | px4 이미지가 PATH 맨 앞에 두는 idsim용 MAVLink 시작 스크립트(스택 오프셋, payload와 gimbal 링크 없음) |

## 이미지

ROS 계열 셋은 `ros-base` 위에 쌓이고, 에이전트는 독립이다.

```
ubuntu:24.04 -> ros-base -+-> sim-base -> px4
                          +-> ros-ws
ubuntu:24.04 -> xrce-agent
```

| 이미지 | 베이스 | 들어가는 것 | 크기 (실측) |
| --- | --- | --- | --- |
| `ros-base` | Ubuntu 24.04 (digest 고정) | ROS 2 Jazzy, CycloneDDS rmw, 공통 도구. `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` 고정 | 838MB |
| `sim-base` | `ros-base` | OSRF 저장소의 Gazebo Harmonic, PX4-gazebo-models의 모델과 월드, 센서 설정 파일(`/opt/px4-gz`) | 2.97GB |
| `px4` | `sim-base` | PX4 SITL 빌드 결과물(`px4` 바이너리, 시작 스크립트), idsim용 `px4-rc.mavlink`와 airframe `.post` 훅. 빌드 도구와 소스는 최종 이미지에 없다 | 3.06GB |
| `ros-ws` | `ros-base` | px4_msgs, px4_ros_com, ros_gz_bridge, colcon, clang-tidy-18, clang-format-18. 이 프로젝트의 소스는 이미지에 넣지 않고 실행 시 `/opt/idsim`에 마운트한다. Gazebo 서버는 없다 | 1.99GB (clang 도구 추가 전 1.58GB, 추가분 약 410MB 실측) |
| `xrce-agent` | Ubuntu 24.04 (digest 고정) | Micro XRCE-DDS Agent. ROS 없음 | 153MB |

이렇게 나눈 이유는 다음과 같다.

- `ros-ws`는 Gazebo가 없는 `ros-base`에서 가볍게 갈라진다. 프로젝트 소스는 이미지에 굽지 않으므로(굽으면 커밋마다 이미지 key가 바뀐다) `ros_ws/src`의 패키지는 아래 "ROS 2 패키지 빌드" 절의 `tools/ros_ws.sh`로 빌드한다.
- 모델 파일은 `sim-base` 한 곳에만 둔다. Gazebo 서버와 PX4가 같은 절대 경로로 모델을 열어야 하는데, 둘 다 `sim-base` 위에 있으면 경로가 저절로 일치한다.
- `xrce-agent`는 자체 Fast-DDS를 소스 빌드하므로, ROS가 가져오는 다른 Fast-DDS와 섞이지 않게 ROS 없는 베이스에 둔다.

각 이미지는 빌드에 쓴 버전을 `IDSIM_BUILD_*` 환경변수로 남긴다. 스모크 S0가 이 값을 `versions.env`와 대조해, 이미지를 다시 빌드하지 않은 채 버전만 올린 상태를 잡아낸다.

## 컨테이너 구성 (생성되는 compose)

compose 파일은 손으로 쓰지 않는다. `tools/gen_compose.py`가 `config/fleet.yaml`(기체 레지스트리)과 스택 번호 k에서 `artifacts/runs/<실행 id>/compose.yaml`과 `stack.json`을 만든다. 모든 값(도메인, 포트, 경로, uid:gid)이 구체값으로 들어가므로 보간 변수가 없고, 무엇으로 돌았는지가 실행 디렉터리에 남는다. `stack.json`은 실행 시점의 단일 출처이며 스크립트와 테스트는 식별자를 다시 계산하지 않고 이 파일만 읽는다.

모든 컨테이너는 `network_mode: host`로 호스트 네트워크를 공유하고, 자동 재시작하지 않는다(`restart: "no"`). 기체 한 대가 컨테이너 하나(`px4-N`)다.

```
xrce-agent --> gazebo --> px4-1..N --> bridge      (본 스택, up --wait 대상)
 (에이전트)    (시뮬레이터)  (기체)       (/clock)
                  +--> gz-gui (viz 프로필)       runner (tools 프로필, 판정 명령용)
```

화살표는 시작 순서다. 앞 컨테이너가 healthy가 되어야 다음 컨테이너가 뜬다. `fleet.yaml`의 `px4.start: sequential`이면 `px4-(N+1)`이 `px4-N`을 기다린다.

| 서비스 | 이미지 | 하는 일 | 준비 판정 | 실행 사용자 |
| --- | --- | --- | --- | --- |
| `xrce-agent` | xrce-agent | PX4의 uORB 토픽을 ROS 2 DDS 토픽으로 중계한다. 기체 전부가 이 에이전트 하나에 접속한다 | 에이전트 UDP 포트가 열림(16진수 포트는 생성기가 계산) | root |
| `gazebo` | sim-base | `idsim_sim`의 `gz_server.sh`가 Gazebo 서버를 헤드리스로 띄우고 월드 이름을 검사하며, `world.origin`이 있으면 원점을 한 번 설정한다 | `scene/info` 서비스 응답과 준비 파일 `/tmp/idsim/ready` | root |
| `px4-N` | px4 | 기체 N의 비행 제어기(`px4 -d -i N`). Gazebo에 `<모델>_N`을 스폰하고 에이전트에 접속한다. 작업 디렉터리 `rootfs/N`은 실행 디렉터리 `px4-N/`의 바인드 마운트(ULog, 파라미터 파일이 산출물로 남는다) | 에이전트 연결 상태가 `Running, connected` | 호스트 uid:gid |
| `bridge` | ros-ws | Gazebo의 시뮬레이션 시계를 ROS 2 `/clock` 토픽으로 넘긴다 | `/clock` 수신(30초 간격, 시작 구간은 5초) | 호스트 uid:gid |
| `runner` | ros-ws | 상주하지 않는다. 스크립트가 `compose run`으로 판정 명령을 실행할 때 쓴다. 프로필 `tools` | 없음 | 호스트 uid:gid |
| `gz-gui` | sim-base | Gazebo GUI 클라이언트. 프로필 `viz`. 아래 "시각 도구" 절 | 없음 | 호스트 uid:gid |

변형은 둘이다(`--variant`).

- `standalone`(기본): 위 표 전부.
- `embedded`: 진단용(스모크 S1b). 기체 1대, `gazebo`, `bridge`, `gz-gui` 없이 PX4가 Gazebo를 컨테이너 안에서 직접 띄운다(`HEADLESS=1`). 원점은 적용하지 않는다.

호스트에 쓰는 서비스는 호스트 사용자의 uid:gid로 돌고 `HOME`은 컨테이너 안 `/tmp`, ROS 로그는 `artifacts/runs/<실행 id>/ros_log/<서비스>/`다. 그래서 `artifacts/runs/`에는 root 소유 파일이 생기지 않는다. 바인드 마운트는 중첩하지 않는다(중첩하면 마운트 지점이 root 소유로 생긴다).

## 격리 규칙

같은 호스트에 다른 ROS 2 스택이나 Gazebo, 또는 idsim 스택이 여럿 돌 수 있으므로, 스택 번호 k(0-9, 기본 0) 하나에서 아래 값을 파생한다. 기준값은 `tools/gen_compose.py`의 상수다.

| 항목 | 값 | k = 0 |
| --- | --- | --- |
| compose 프로젝트 이름 | idsim-k | idsim-0 |
| ROS 2 도메인 (`ROS_DOMAIN_ID`) | 20 + k | 20 |
| 에이전트 포트 (UDP) | 8888 + k | 8888 |
| Gazebo 파티션 (`GZ_PARTITION`) | idsim-k | idsim-0 |
| MAVLink 오프셋 (`IDSIM_MAVLINK_OFFSET`) | 1000k | 0 |
| QGC가 듣는 GCS 포트 (UDP) | 14550 + 1000k | 14550 |
| MAVLink API 포트 (UDP, 기체 N) | 14540 + 1000k + N | 14541 |

도메인 0은 다른 ROS 2 프로젝트가 흔히 쓰므로 피한다. compose 프로젝트 이름을 명시하지 않으면 디렉터리 이름이 프로젝트 이름이 되어 같은 이름을 쓰는 다른 프로젝트의 컨테이너까지 함께 내릴 수 있다. k가 다르면 스택 둘을 동시에 띄울 수 있다(스모크 포함). 포트 비충돌은 생성기 단위 테스트가 k 0-9, N 1-9 전 범위에서 검사한다.

## 사용법

이미지 빌드. 저장소 루트에서 실행한다. docker buildx가 필요하다. 빌드 스크립트가 `versions.env`를 읽고 이미지마다 key를 계산해 bake를 의존 순서대로 부른다. CI도 같은 스크립트를 쓴다.

```
python3 tools/ci/build_images.py --mode load
```

특정 이미지만 빌드할 때는 이미지 이름을 붙인다. 의존 이미지는 함께 빌드된다. 실제로 빌드하지 않고 bake 명령만 보려면 `--dry-run`을 붙인다.

```
python3 tools/ci/build_images.py --mode load px4
```

이미지 key는 그 이미지의 Dockerfile, bake 정의, COPY하는 파일, `versions.env` 중 그 Dockerfile이 쓰는 줄, 베이스 이미지의 key에서 계산한다. key가 같으면 같은 이미지로 보고, CI는 레지스트리(`ghcr.io/danielhongwoo/idsim/<이미지>:<key>`)에 같은 key가 있으면 빌드를 건너뛴다. 계산 근거는 아래 명령으로 볼 수 있다.

```
python3 tools/ci/image_keys.py --explain px4
```

### ROS 2 패키지 빌드 (tools/ros_ws.sh)

`ros_ws/src`의 패키지는 호스트가 아니라 ros-ws 컨테이너 안에서 빌드한다. install의 setup 스크립트와 CMake 경로가 `/opt/idsim/...` 절대 경로라 호스트에서는 쓸 수 없고, 스택의 노드 서비스도 같은 마운트 경로에서 `ros_ws/install`을 읽는다. 산출물은 저장소의 `ros_ws/build`, `ros_ws/install`, `ros_ws/log`(git 무시)에 호스트 uid:gid 소유로 생긴다.

| 명령 | 하는 일 |
| --- | --- |
| `tools/ros_ws.sh build [colcon 인자...]` | `colcon build`(RelWithDebInfo, `compile_commands.json` 생성) |
| `tools/ros_ws.sh test [colcon 인자...]` | build 뒤 `colcon test --return-code-on-test-failure`, `colcon test-result`, 테스트 수 > 0 단정 |
| `tools/ros_ws.sh tidy` | build 뒤 `run-clang-tidy-18`(저장소 루트 `.clang-tidy`, 각 패키지 `src/`의 C++ 소스) |
| `tools/ros_ws.sh ci` | build, test, tidy를 한 번씩. CI의 unit job이 이것만 부른다 |
| `tools/ros_ws.sh clean` | `ros_ws/build`, `install`, `log` 삭제 |
| `tools/ros_ws.sh shell` | 같은 조건의 대화형 bash |

컨테이너는 `--user <호스트 uid:gid>`, `--network none`, `HOME=/tmp/idsim-home`, `CYCLONEDDS_URI=` 비움, `ROS_DOMAIN_ID=99`로 돈다. 단위 테스트가 같은 호스트의 개발 스택(도메인 20 + k)과 섞이지 않게 하는 조건이다. 실행 전에 이미지의 `IDSIM_BUILD_*`(`PX4_MSGS_REF`, `PX4_ROS_COM_REF`, `LLVM_MAJOR`, `FOXGLOVE_BRIDGE_VERSION`)를 `versions.env`와 대조해 다르면 중단하므로, `versions.env`를 올린 뒤에는 `python3 tools/ci/build_images.py --mode load ros-ws`로 이미지를 다시 빌드한다. foxglove_bridge는 ROS apt가 최신 빌드 하나만 남겨 정확한 판을 pin할 수 없어, 설치한 dpkg 판이 `FOXGLOVE_BRIDGE_VERSION-` 접두로 시작하는지 빌드에서 단정하고 `IDSIM_BUILD_FOXGLOVE_BRIDGE_VERSION`으로 남긴다. 병렬 수는 `IDSIM_JOBS`(기본 min(코어 수, 4))로 바꾼다. 스택이 떠 있을 때 다시 빌드하면 실행 중인 노드의 `.so`가 바뀌므로 경고가 나온다.

`colcon test`는 테스트가 실패해도 0을 돌려주고 `colcon test-result`는 빌드가 실패해도 "0 tests"로 0을 돌려준다. 그래서 `test`는 `--return-code-on-test-failure`를 쓰고 테스트 수가 0이면 실패시킨다. 단위 층에는 재시도를 두지 않는다.

clang-format 검사는 CI lint job이 `LINT_PYTHON_IMAGE`에 pip `clang-format==$LINT_CLANG_FORMAT_VERSION`을 설치해 돌린다(`tools/ci/lint.sh clang-format`). ros-ws의 `clang-format-18`은 컨테이너 안에서 손으로 쓰는 같은 major이며, 두 값의 major가 `LLVM_MAJOR`와 같은지 lint.sh가 단정한다. clang-tidy와 ament_lint는 `compile_commands.json`과 ROS 헤더가 필요해 lint job이 아니라 `tools/ros_ws.sh ci`(unit job)에서 돈다.

### apt 미러

이미지 빌드의 우분투 apt 미러는 `versions.env`의 `UBUNTU_APT_MIRROR`(기본 `http://kr.archive.ubuntu.com/ubuntu`)이다. `ros-base`와 `xrce-agent`(build 단계)가 첫 `apt-get update` 앞에서 `/etc/apt/sources.list.d/ubuntu.sources`의 archive와 security 주소를 이 값으로 바꾸고, `sim-base`, `px4`, `ros-ws`는 `ros-base`를 상속한다. packages.ros.org와 packages.osrfoundation.org는 바꾸지 않는다. kr 미러는 noble, noble-updates, noble-security를 모두 제공한다.

이 값은 이미지 key에 들어가지 않는다(`tools/ci/image_keys.py`의 `KEY_EXCLUDED_ARGS`). `ubuntu.sources`는 이미지에 남아 미러별로 바이트가 다르지만 런타임이 apt를 쓰지 않으므로 같은 이미지로 본다. 미러 동기화 시차로 패키지 버전이 조금 다를 수 있으나, 이미지 key는 원래 apt 패키지 버전을 고정하지 않는다.

다른 미러를 쓰려면 같은 이름의 환경변수를 주고 빌드한다. 환경변수가 `versions.env`보다 우선한다(`build_images.py` 경로에 한함. `versions.env`를 source하는 직접 bake 경로에서는 `versions.env`가 이긴다). 값을 바꿔도 이미 캐시된 `apt` 레이어는 인자가 달라진 단계부터 다시 만들어진다.

http 미러만 가능하다(베이스 이미지에 CA 인증서가 없어 https 미러는 첫 apt 단계에서 인증서 오류).

```
UBUNTU_APT_MIRROR=http://archive.ubuntu.com/ubuntu python3 tools/ci/build_images.py --mode load
```

CI(`build-images.yml`)는 러너가 미국에 있어 위 방식으로 우분투 기본 미러를 쓴다. `tools/check_host.sh`의 미러 검사도 같은 값을 읽는다.

스택 올리기와 내리기. 저장소 루트에서 실행한다. `up` 한 번이 생성, 떠 있던 같은 스택 내리기, 두 단계 `up --wait`(gazebo까지 올린 뒤 이 스택의 모델이 Gazebo에 남아 있지 않은지 확인하고 나머지를 올린다)를 모두 한다. 실패하면 에이전트의 `bind error`와 px4의 `bind failed`를 찾아 알려 준다.

```
tools/stack.sh up                 # 스택 0. 실행 디렉터리 경로를 출력한다
tools/stack.sh up --stack 1       # 스택 1을 동시에
tools/stack.sh up --viz           # Gazebo GUI까지
tools/stack.sh ps
tools/stack.sh logs px4-1
tools/stack.sh down               # docker compose -p idsim-0 down
```

생성만 하려면 `tools/gen_compose.sh --stack k`를 쓴다. 생성기는 ros-ws 컨테이너 안에서 돌므로(호스트에 PyYAML이 필요 없다) ros-ws 이미지가 있어야 한다. 기체, 월드, 원점(`world.origin`), SITL 파라미터는 `config/fleet.yaml`에서 고친다.

스모크 실행. 같은 생성기와 `tools/stack.sh up`으로 스택을 올리고 판정한 뒤 내린다.

```
tests/smoke/run_smoke.sh S0
tests/smoke/run_smoke.sh S2
tests/smoke/run_smoke.sh --stack 1 S2         # 다른 스택 번호로
tests/smoke/run_smoke.sh --update-golden S4   # 골든이 없을 때 처음 한 번
```

실행 결과는 `artifacts/runs/<실행 id>/`에 남는다(`compose.yaml`, `stack.json`, 판정과 로그 `smoke/`, ULog `px4-N/log/`). 모든 파일이 호스트 사용자 소유다.

## 시각 도구

이 절의 도구는 개발자가 눈으로 보기 위한 화면이다. 판정, 스모크, CI와 무관하며 어떤 테스트도 이 도구에 의존하지 않는다(본 스택 서비스는 `viz` 프로필 서비스에 의존하지 않고, 스모크와 CI는 이 프로필을 켜지 않는다). `tools/stack.sh up`으로 올린 standalone 스택 위에서 쓴다.

### QGroundControl

호스트에서 직접 실행하며 compose 서비스가 아니다. 저장소 루트에서 `tools/qgc.sh`를 실행한다.

```
tools/qgc.sh                  # 필요하면 내려받아 검증하고 실행(스택 0)
tools/qgc.sh --stack 1        # 스택 1의 기체에 붙는다
tools/qgc.sh --download-only  # 내려받기와 검증만
tools/qgc.sh --print-path     # 캐시된 AppImage 경로 출력
```

- 버전과 sha256은 `versions.env`의 `QGC_VERSION`, `QGC_APPIMAGE_SHA256`이 정한다. 캐시는 `${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/`에 두고, 파일이 없거나 sha256이 다르면 다시 받는다. 검증에 실패하면 파일을 지우고 종료 코드 1로 끝난다.
- 스택 k의 PX4는 GCS 포트 14550 + 1000k(UDP)로 MAVLink를 보내며 이 포트는 스택 안 모든 기체가 같다. `qgc.sh --stack k`는 실행 전에 QGC 설정 파일(`~/.config/QGroundControl/QGroundControl.ini`)의 `[AutoConnect] udpListenPort`를 그 포트로 고친다. `--stack`이 없으면 k = 0(또는 `IDSIM_STACK_INDEX`)의 포트로 되돌린다. `MAV_SYS_ID`가 스택 간에 같으므로 QGC 하나는 한 번에 스택 하나만 본다.
- `COM_RC_IN_MODE`가 4라 QGC의 수동 모드와 가상 조이스틱은 쓸 수 없다. 모니터링과 ARM, TAKEOFF, LAND 명령용이다.
- 스크립트가 QGC를 자식으로 띄우고, Ctrl-C나 TERM을 받으면 QGC에 TERM을 보내 정상 종료를 5초 기다린 뒤 끝나지 않으면 SIGKILL로 끝낸다. 기체가 연결된 상태에서는 QGC가 종료 확인 대화상자를 띄울 수 있어서다.

### Gazebo GUI (viz 프로필)

생성된 compose의 `gz-gui` 서비스(sim-base, 프로필 `viz`)가 이미 떠 있는 `gazebo` 서버에 GUI 클라이언트만 붙인다. 같은 `GZ_PARTITION`, 호스트 uid:gid, `ipc: host`, X11 소켓과 Xauthority를 읽기 전용으로 마운트하고 `idsim_sim`의 `gz_gui.sh`와 `gui.config`를 쓴다.

```
tools/stack.sh up --viz           # 스택과 GUI를 함께
tools/stack.sh up                 # 또는 스택을 올린 뒤
docker compose -f artifacts/runs/<실행 id>/compose.yaml --profile viz up -d gz-gui
docker compose -p idsim-0 stop gz-gui   # GUI만 끈다. 서버는 계속 돈다
```

- 호스트 셸에 `DISPLAY`와 `XAUTHORITY`가 있어야 한다. compose는 `${DISPLAY:-}`와 `${XAUTHORITY:-/dev/null}`을 넘기므로 비어 있으면 `gz_gui.sh`가 안내 메시지와 함께 끝난다. GNOME Wayland(Xwayland)에서는 로그인마다 이름이 바뀌는 `/run/user/<uid>/.mutter-Xwaylandauth.*`를 쓴다: `export XAUTHORITY=$(ls /run/user/$(id -u)/.mutter-Xwaylandauth.* | head -n 1)`.
- GUI 렌더 엔진은 `IDSIM_GZ_GUI_ENGINE`(기본 ogre2), 깜빡임 시도용 `QSG_RENDER_LOOP`, `vblank_mode`는 호스트 셸에 있으면 그대로 넘어간다(예: `QSG_RENDER_LOOP=basic vblank_mode=1 tools/stack.sh up --viz`).
- `gui.config`는 WorldControl 플러그인을 뺐으므로 GUI에서 월드를 멈출 수 없다. 화면에서 실수로 일시정지하는 것을 막기 위해서다.
- `ipc: host`가 없으면 GPU 가속이 없는 호스트(소프트웨어 렌더링)에서 창이 검게 나온다. Mesa의 소프트웨어 경로가 X 서버와 MIT-SHM 공유 메모리로 화면을 전달하는데, 컨테이너의 IPC 네임스페이스가 분리되어 있으면 X 서버가 그 메모리에 붙지 못하기 때문이다. GPU 가속(DRI3) 경로에서는 없어도 되지만 항상 붙인다.
- `gui.config`는 바닥 격자(GridConfig, 2m 간격, 500 x 500 m, 어두운 선)를 켠다. PX4 기본 월드는 배경과 바닥이 균일한 회색이라 격자가 없으면 기체 이동이 보이지 않는다. 왼쪽 패널의 "Grid config"에서 칸 수와 간격을 바꿀 수 있다.
- 화면이 깜빡이면 `QSG_RENDER_LOOP=basic vblank_mode=1`을 호스트 셸에 두고 올려 본다. Qt 렌더 루프를 단일 스레드로 고정하고 Mesa 수직 동기를 켜 주사율 이하로 그린다. 가상머신에서 효과가 있는지는 확인 중이다.
- 도구 모음 아이콘이 보이도록 `sim-base`에 `libqt5svg5`가 들어 있다.
- 종료는 `docker compose -p idsim-<k> stop gz-gui`다. GUI만 끝나고 서버는 계속 돈다.
- 창이 뜨지 않거나 경고를 보려면 `docker compose -f <compose.yaml> --profile viz run --rm --no-deps gz-gui /opt/idsim/sim/scripts/gz_gui.sh -v 4`로 플러그인 로드 줄과 Qt 메시지를 확인한다. WorldStats의 "Binding loop detected" 한 줄은 gz 자체 경고라 무시한다.

## 버전을 올릴 때

1. `versions.env`의 값을 바꾼다. PX4 태그를 올리면 `PX4_MSGS_REF`도 같은 릴리스 브랜치의 커밋으로 함께 올린다.
2. 이미지를 다시 빌드한다.
3. `run_smoke.sh S0`로 이미지 버전과 `versions.env`가 일치하는지 확인한다(ros-ws의 PyYAML과 `LINT_PYYAML_VERSION` 대조 포함).
4. PX4 태그를 올렸다면 `docker/Dockerfile.px4`의 `sha256sum -c` 줄이 빌드에서 실패한다. 이것은 의도된 것이다. 상류 `ROMFS/px4fmu_common/init.d-posix/px4-rc.mavlink`를 새 태그에서 받아 `docker/px4/px4-rc.mavlink`와 비교하고(GCS, API 링크 정의와 포트 식이 바뀌었는지), idsim 파일을 맞춘 뒤 새 상류 파일의 sha256(`sha256sum`)으로 그 줄을 바꾼다. 상류에 `.post`가 있는 gz airframe이 생겨도 빌드가 실패하므로 같은 때에 본다. 검토는 px4-engineer다.
5. PX4 태그를 올렸다면 `run_smoke.sh --update-golden S4`로 새 태그의 골든을 만들고, 옛 태그 디렉터리는 지운다.
6. 생성기 골든(`tests/fixtures/gen_compose/`)은 이미지 버전과 무관하다. 생성 규칙이나 `config/px4/sitl_params.env`를 바꾸면 `python3 -m pytest tests/tools --update-golden`(PyYAML이 있는 환경, 예: ros-ws 컨테이너)으로 다시 만들고 diff를 리뷰한다.
