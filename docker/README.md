# docker/

idsim의 실행 환경을 이루는 Docker 이미지와 compose 구성이다. 모든 구성 요소는 VM이 아니라 컨테이너로 돈다. 컨테이너는 호스트 커널을 공유하는 프로세스 격리 단위이므로, 기체 여러 대와 시뮬레이터를 PC 한 대에서 가볍게 띄울 수 있다.

지원 호스트는 x86_64 Linux뿐이다. 설계 배경은 [../docs/architecture.md](../docs/architecture.md)의 "Docker Compose 실행 환경 설계" 절, 스모크 테스트 절차는 [../docs/smoke-test-phase1a.md](../docs/smoke-test-phase1a.md)에 있다.

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
| `compose.smoke.yaml` | Phase 1a 스모크 테스트용 컨테이너 구성 (임시, 3단계에서 생성 스크립트가 대체) |

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
| `px4` | `sim-base` | PX4 SITL 빌드 결과물(`px4` 바이너리, 시작 스크립트). 빌드 도구와 소스는 최종 이미지에 없다 | 3.06GB |
| `ros-ws` | `ros-base` | px4_msgs, px4_ros_com, ros_gz_bridge. 이 프로젝트의 소스는 이미지에 넣지 않고 실행 시 `/opt/idsim`에 마운트한다. Gazebo 서버는 없다 | 1.57GB |
| `xrce-agent` | Ubuntu 24.04 (digest 고정) | Micro XRCE-DDS Agent. ROS 없음 | 153MB |

이렇게 나눈 이유는 다음과 같다.

- `ros-ws`는 프로젝트 코드가 바뀔 때마다 다시 빌드되므로 Gazebo가 없는 `ros-base`에서 가볍게 갈라진다.
- 모델 파일은 `sim-base` 한 곳에만 둔다. Gazebo 서버와 PX4가 같은 절대 경로로 모델을 열어야 하는데, 둘 다 `sim-base` 위에 있으면 경로가 저절로 일치한다.
- `xrce-agent`는 자체 Fast-DDS를 소스 빌드하므로, ROS가 가져오는 다른 Fast-DDS와 섞이지 않게 ROS 없는 베이스에 둔다.

각 이미지는 빌드에 쓴 버전을 `IDSIM_BUILD_*` 환경변수로 남긴다. 스모크 S0가 이 값을 `versions.env`와 대조해, 이미지를 다시 빌드하지 않은 채 버전만 올린 상태를 잡아낸다.

## 컨테이너 구성 (compose.smoke.yaml)

모든 컨테이너는 `network_mode: host`로 호스트 네트워크를 공유하고, 자동 재시작하지 않는다. 기체 한 대가 컨테이너 하나다.

```
xrce-agent --> gazebo --> px4 --> bridge --> smoke
 (에이전트)    (시뮬레이터)  (기체)   (/clock)   (판정)
```

화살표는 시작 순서다. 앞 컨테이너가 healthy가 되어야 다음 컨테이너가 뜬다.

| 서비스 | 이미지 | 하는 일 | 준비 판정 |
| --- | --- | --- | --- |
| `xrce-agent` | xrce-agent | PX4의 uORB 토픽을 ROS 2 DDS 토픽으로 중계한다. 기체 전부가 이 에이전트 하나에 접속한다 | 에이전트 UDP 포트가 열림 |
| `gazebo` | sim-base | Gazebo 서버만 헤드리스로 띄우고 월드를 올린다. 물리와 센서를 계산한다 | 월드의 `scene/info` 서비스가 보임 |
| `px4` | px4 | 기체 한 대의 비행 제어기. Gazebo 월드에 기체 모델을 스폰하고 에이전트에 접속한다. 데몬 모드(`-d`)로 실행 | 에이전트 연결 상태가 `Running, connected` |
| `px4-embedded` | px4 | 진단용. PX4가 Gazebo까지 직접 띄우는 단일 컨테이너 모드 | 위와 같음 |
| `bridge` | ros-ws | Gazebo의 시뮬레이션 시계를 ROS 2 `/clock` 토픽으로 넘긴다 | `/clock` 수신 |
| `smoke`, `smoke-embedded` | ros-ws | 상주하지 않는다. 스모크 스크립트가 판정 명령을 실행할 때만 쓴다 | 없음 |

프로필은 둘이다.

- `embedded`: `xrce-agent`, `px4-embedded`, `smoke-embedded`. 스모크 S1과 S1b에서 쓴다.
- `standalone`: `xrce-agent`, `gazebo`, `px4`, `bridge`, `smoke`. S2 이후에 쓴다. 기본 구성은 이쪽이다.

## 격리 규칙

같은 호스트에 다른 ROS 2 스택이나 Gazebo가 돌 수 있으므로, 스택 번호 k(기본 0) 하나에서 아래 값을 파생해 모든 컨테이너에 넘긴다.

| 항목 | 값 | 기본값 |
| --- | --- | --- |
| ROS 2 도메인 (`ROS_DOMAIN_ID`) | 20 + k | 20 |
| 에이전트 포트 | 8888 + k | 8888 |
| Gazebo 파티션 (`GZ_PARTITION`) | idsim-k | idsim-0 |
| compose 프로젝트 이름 | idsim-smoke | idsim-smoke |

도메인 0은 다른 ROS 2 프로젝트가 흔히 쓰므로 피한다. compose 프로젝트 이름을 명시하지 않으면 디렉터리 이름 `docker`가 프로젝트 이름이 되어, 같은 이름을 쓰는 다른 프로젝트의 컨테이너까지 함께 내릴 수 있다. 지금은 프로젝트 이름이 스택 번호와 무관하므로 스모크는 호스트당 하나만 돌린다.

## 사용법

이미지 빌드. 저장소 루트에서 실행한다. docker buildx가 필요하다. 빌드 스크립트가 `versions.env`를 읽고 이미지마다 키를 계산해 bake를 의존 순서대로 부른다. CI도 같은 스크립트를 쓴다.

```
python3 tools/ci/build_images.py --mode load
```

특정 이미지만 빌드할 때는 이미지 이름을 붙인다. 의존 이미지는 함께 빌드된다. 실제로 빌드하지 않고 bake 명령만 보려면 `--dry-run`을 붙인다.

```
python3 tools/ci/build_images.py --mode load px4
```

이미지 키는 그 이미지의 Dockerfile, bake 정의, COPY하는 파일, `versions.env` 중 그 Dockerfile이 쓰는 줄, 베이스 이미지의 키에서 계산한다. 키가 같으면 같은 이미지로 보고, CI는 레지스트리(`ghcr.io/danielhongwoo/idsim/<이미지>:<키>`)에 같은 키가 있으면 빌드를 건너뛴다. 계산 근거는 아래 명령으로 볼 수 있다.

```
python3 tools/ci/image_keys.py --explain px4
```

스모크 실행. compose 파일을 직접 실행하지 않는다. 필요한 변수를 스크립트가 계산해 넘긴다.

```
tests/smoke/run_smoke.sh S0
tests/smoke/run_smoke.sh S2
tests/smoke/run_smoke.sh --update-golden S4   # 골든이 없을 때 처음 한 번
```

실행 결과와 로그는 `artifacts/smoke/<실행 id>/<단계>/`에 남는다. 컨테이너가 root로 쓰므로 지울 때 권한이 필요할 수 있다.

## 시각 도구

이 절의 도구는 개발자가 눈으로 보기 위한 화면이다. 판정, 스모크, CI와 무관하며 어떤 테스트도 이 도구에 의존하지 않는다. 스모크 standalone 스택(S2 이후) 위에서 쓴다.

### QGroundControl

호스트에서 직접 실행하며 compose 서비스가 아니다. 저장소 루트에서 `tools/qgc.sh`를 실행한다.

```
tools/qgc.sh                  # 필요하면 내려받아 검증하고 실행
tools/qgc.sh --download-only  # 내려받기와 검증만
tools/qgc.sh --print-path     # 캐시된 AppImage 경로 출력
```

- 버전과 sha256은 `versions.env`의 `QGC_VERSION`, `QGC_APPIMAGE_SHA256`이 정한다. 캐시는 `${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/`에 두고, 파일이 없거나 sha256이 다르면 다시 받는다. 검증에 실패하면 파일을 지우고 종료 코드 1로 끝난다.
- PX4는 GCS 포트 14550(UDP)으로 MAVLink를 보내며 이 포트는 모든 인스턴스가 같다. 스택을 둘 이상 띄우면 QGC가 기체를 구분하지 못할 수 있으므로 QGC는 한 번에 스택 하나에만 쓴다.
- `COM_RC_IN_MODE`가 4라 QGC의 수동 모드와 가상 조이스틱은 쓸 수 없다. 모니터링과 ARM, TAKEOFF, LAND 명령용이다.
- 스크립트가 QGC를 자식으로 띄우고, Ctrl-C나 TERM을 받으면 QGC에 TERM을 보내 정상 종료를 5초 기다린 뒤 끝나지 않으면 SIGKILL로 끝낸다. 기체가 연결된 상태에서는 QGC가 종료 확인 대화상자를 띄울 수 있어서다.

### Gazebo GUI (수동 실행)

로드맵 3단계에서 `viz` 프로필의 `gz-gui` 서비스로 옮기기 전까지는 `sim-base` 컨테이너를 손으로 띄운다. 이미 떠 있는 `gazebo` 서버에 클라이언트만 붙는다.

전제는 standalone 스택이 떠 있는 것이다. `run_smoke.sh`는 끝에 스택을 내리므로, 스택을 유지하려면 스크립트가 계산하는 변수를 직접 내보내고 compose를 올린다(`tests/smoke/run_smoke.sh`의 격리 규칙과 인스턴스 변수 부분 참조).

```
export IDSIM_ROS_DOMAIN_ID=20 IDSIM_AGENT_PORT=8888 IDSIM_GZ_PARTITION=idsim-0
export IDSIM_INSTANCE=1 IDSIM_PX4_ARGS="-d -i 1" IDSIM_PX4_NS=px4_1 IDSIM_ULOG_SUBDIR=1/log
mkdir -p artifacts/viz/ulog && export IDSIM_ULOG_HOST_DIR="$PWD/artifacts/viz/ulog"
docker compose -p idsim-smoke -f docker/compose.smoke.yaml --profile standalone up --wait xrce-agent gazebo px4
```

기체의 출발 위치(월드 기준 좌표)는 월드 파일의 취리히가 기본이다. 다른 곳으로 바꾸려면 PX4가 읽는 환경변수 세 개를 모두 넣은 덮어쓰기 compose 파일을 `-f`로 덧붙인다. PX4가 시작할 때 Gazebo 월드의 기준 좌표를 이 값으로 바꾸고 QGroundControl 지도도 그 위치로 간다. 3단계의 `config/fleet.yaml`이 이 값을 가진다.

```
# 예: 서울시청. 세 값이 모두 있어야 하며 하나라도 빠지면 px4가 시작하지 않는다
services:
  px4:
    environment:
      PX4_HOME_LAT: "37.5665"
      PX4_HOME_LON: "126.9780"
      PX4_HOME_ALT: "38"
```

이 스택은 `run_smoke.sh`와 같은 프로젝트 이름과 스택 번호를 쓰므로, 떠 있는 동안 `run_smoke.sh`를 돌리면 스크립트 끝의 `compose down`이 이 스택을 내린다. 3단계의 `gen_compose.py`가 이 번거로움을 없앤다. 스택이 뜨면 다음 명령으로 GUI를 붙인다. `GZ_PARTITION`은 스택 번호 k에 따라 `idsim-k`다.

```
docker run --rm --name idsim-gz-gui --network host --ipc=host \
  -e DISPLAY -e XAUTHORITY=/tmp/.Xauthority -e GZ_PARTITION=idsim-0 -e GZ_IP=127.0.0.1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:ro -v "$XAUTHORITY:/tmp/.Xauthority:ro" \
  -v "$PWD/ros_ws/src/idsim_sim/config/gui.config:/opt/idsim/gui.config:ro" \
  idsim/sim-base:local gz sim -g --gui-config /opt/idsim/gui.config
```

- `gui.config`는 WorldControl 플러그인을 뺐으므로 GUI에서 월드를 멈출 수 없다. 화면에서 실수로 일시정지하는 것을 막기 위해서다.
- `--ipc=host`가 없으면 GPU 가속이 없는 호스트(소프트웨어 렌더링)에서 창이 검게 나온다. Mesa의 소프트웨어 경로가 X 서버와 MIT-SHM 공유 메모리로 화면을 전달하는데, 컨테이너의 IPC 네임스페이스가 분리되어 있으면 X 서버가 그 메모리에 붙지 못하기 때문이다. GPU 가속(DRI3) 경로에서는 없어도 되지만 항상 붙인다.
- `gui.config`는 바닥 격자(GridConfig, 1m 간격, 50 x 50 m, 어두운 선)를 켠다. PX4 기본 월드는 배경과 바닥이 균일한 회색이라 격자가 없으면 기체 이동이 보이지 않는다. 왼쪽 패널의 "Grid config"에서 칸 수와 간격을 바꿀 수 있다.
- 화면이 깜빡이면 `docker run`에 `-e QSG_RENDER_LOOP=basic -e vblank_mode=1`을 더해 본다. Qt 렌더 루프를 단일 스레드로 고정하고 Mesa 수직 동기를 켜 주사율 이하로 그린다. 가상머신에서 효과가 있는지는 확인 중이다.
- 도구 모음 아이콘이 보이도록 `sim-base`에 `libqt5svg5`가 들어 있다.
- 종료는 Ctrl-C나 `docker stop idsim-gz-gui`다. GUI만 끝나고 서버는 계속 돈다.
- `XAUTHORITY`가 환경변수에 없으면(GNOME Wayland에서는 `/run/user/<uid>/.mutter-Xwaylandauth.*`가 쓰인다) 그 파일 경로를 직접 넣는다.
- 창이 뜨지 않거나 경고를 보려면 `gz sim -g -v 4 ...`로 플러그인 로드 줄과 Qt 메시지를 확인한다. WorldStats의 "Binding loop detected" 한 줄은 gz 자체 경고라 무시한다.

## 버전을 올릴 때

1. `versions.env`의 값을 바꾼다. PX4 태그를 올리면 `PX4_MSGS_REF`도 같은 릴리스 브랜치의 커밋으로 함께 올린다.
2. 이미지를 다시 빌드한다.
3. `run_smoke.sh S0`로 이미지 버전과 `versions.env`가 일치하는지 확인한다.
4. PX4 태그를 올렸다면 `run_smoke.sh --update-golden S4`로 새 태그의 골든을 만들고, 옛 태그 디렉터리는 지운다.
