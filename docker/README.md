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

## 버전을 올릴 때

1. `versions.env`의 값을 바꾼다. PX4 태그를 올리면 `PX4_MSGS_REF`도 같은 릴리스 브랜치의 커밋으로 함께 올린다.
2. 이미지를 다시 빌드한다.
3. `run_smoke.sh S0`로 이미지 버전과 `versions.env`가 일치하는지 확인한다.
4. PX4 태그를 올렸다면 `run_smoke.sh --update-golden S4`로 새 태그의 골든을 만들고, 옛 태그 디렉터리는 지운다.
