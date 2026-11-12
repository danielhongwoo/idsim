# idsim

idsim은 Interceptor Drone Simulator의 약자다. PX4 SITL, Gazebo Harmonic, ROS 2 Jazzy 위에서 드론 여러 대의 운용 서비스(Fleet, Mission, Telemetry, Replay)를 컨테이너로 돌리는 시뮬레이션 플랫폼이다. 지원 호스트는 x86_64 Linux뿐이다.

계획과 단계는 `docs/roadmap.md`, 설계는 `docs/architecture.md`에 있다.

## 호스트 조건

| 항목 | 조건 |
| --- | --- |
| OS와 CPU | x86_64 Linux (Ubuntu 24.04에서 확인) |
| Docker | Docker Engine 25.0 이상(healthcheck `start_interval`), compose v2 플러그인, buildx. 사용자가 docker 그룹에 속해야 한다(`sudo usermod -aG docker $USER` 뒤 다시 로그인). Ubuntu 24.04 패키지는 `docker.io`, `docker-compose-v2`, `docker-buildx`이고, Docker 공식 저장소는 `docker-ce`, `docker-compose-plugin`, `docker-buildx-plugin`이다 |
| 저장소 경로 | 공백과 아스키 밖 문자가 없어야 한다(생성기 `PATH_SAFE_RE`가 거부한다) |
| 도구 | git, python3 (표준 라이브러리만 사용. 3.12에서 확인, 하한 3.10), curl, sha256sum |
| 디스크 | 30GB 이상 권장. 근거: 이미지 5종 합 약 8.6GB(공유 레이어 중복 포함이라 실제 점유는 더 작다) + px4 builder 단계 7.7GB + buildkit 캐시 |
| 메모리 | 16GB 이상. 개발 VM 31GB와 CI runner 16GB에서 확인했고 그 아래는 미실측 |
| 선택 | gh (PR을 올리거나 합칠 때), 화면 확인용 X11 또는 XWayland 데스크톱 |

조건은 `tools/check_host.sh`가 점검한다. 시스템을 바꾸지 않고 조회만 하며, 외부 네트워크 검사는 `--offline`으로 건너뛴다.

## 빠른 시작

새 호스트에서 한 번 하는 환경 구성이다. 순서대로 돌리고, 모두 통과하면 개발을 시작할 수 있다.

```
tools/check_host.sh
python3 tools/ci/build_images.py --mode load
tests/smoke/run_smoke.sh images
tests/smoke/run_smoke.sh px4-out
tests/smoke/run_smoke.sh px4-in
tests/smoke/run_smoke.sh clock
```

| 명령 | 하는 일 |
| --- | --- |
| `tools/check_host.sh` | 호스트가 위 조건을 갖췄는지, 포트와 미러 접근에 문제가 없는지 본다 |
| `python3 tools/ci/build_images.py --mode load` | 이미지 5종을 로컬에 빌드한다. 콜드 빌드는 CI runner에서 약 22분이다 |
| `tests/smoke/run_smoke.sh images` | 이미지 버전과 `docker/versions.env`의 일치를 본다. 스택을 올리지 않는다 |
| `tests/smoke/run_smoke.sh px4-out` | 운용과 같은 구성(Gazebo 분리)에서 기체 스폰, PX4 -> ROS 방향 토픽, `commander check`를 본다 |
| `tests/smoke/run_smoke.sh px4-in` | ROS -> PX4 방향. arm/disarm 왕복과 `trajectory_setpoint` 구독을 본다. 미션 노드가 이 방향으로 명령과 setpoint를 보낸다 |
| `tests/smoke/run_smoke.sh clock` | `/clock` 브리지의 발행자 수와 시각 증가를 본다. 노드와 통합 테스트의 시간 기준이다 |

px4-out, px4-in, clock은 각각 스택을 내렸다가 다시 올리고, 끝나면 내린다.

## 개발 중에 쓰는 도구

환경 구성이 끝난 뒤 작업하면서 반복해서 쓰는 명령이다.

| 명령 | 하는 일 |
| --- | --- |
| `tools/sim_stack.sh up` | `config/fleet.yaml`로 스택(아래 "스택과 스택 번호")을 생성하고 인프라(에이전트, gazebo, px4-N, bridge)에 이어 Mission Executor(`ops-N`)까지 healthy로 올린다. 실행 디렉터리 `artifacts/runs/<실행 id>/`를 출력한다. Executor 없이 인프라만 올리려면 `--infra-only`(스모크와 측정 스크립트가 쓴다). `ros_ws/install/idsim_mission/`이 없으면 먼저 `tools/ros_ws.sh build`. 내리기는 `tools/sim_stack.sh down`. 화면 도구는 아래 "화면으로 보기" |
| `tests/sitl/run_sitl.sh --stack k` | 통합 테스트(이륙-호버-착륙 시나리오 B, C, A, D, T). 아래 "통합 테스트" |
| `tools/ros_ws.sh ci` | `ros_ws/src`의 ROS 2 패키지를 ros-ws 컨테이너에서 빌드하고 테스트(ament_lint 포함)와 clang-tidy를 돌린다. CI의 unit job과 같은 명령 |
| `tools/ci/lint.sh all` | CI와 같은 lint 전체 (호스트에 linter 설치가 필요 없다) |
| `python3 tools/ci/build_images.py --mode load [이미지]` | `docker/`나 `versions.env`를 바꾼 뒤 이미지를 다시 빌드한다. 이미지 이름을 주면 그 이미지와 베이스만 빌드한다 |
| `tests/smoke/run_smoke.sh <images, px4-out, px4-in, clock>` | 이미지나 스택을 바꾼 뒤 빠른 시작의 스모크를 다시 돌린다 |
| `tests/smoke/run_smoke.sh golden` | 토픽, QoS, 파라미터를 golden 파일과 비교한다. 이미지나 PX4 설정을 바꾼 뒤의 회귀 확인. golden을 의도해서 바꿀 때는 `--update-golden` |
| `tests/smoke/run_smoke.sh embedded` | PX4가 Gazebo를 직접 띄우는 구성. 운용 구성이 아니라 px4-out이 실패할 때 원인을 가르는 진단용이다. 단계 설명은 `docs/smoke-test.md` |
| `python3 -m pytest tests/tools --update-golden` | compose 생성기 golden(`tests/tools`)을 의도해서 바꿨을 때 ros-ws 컨테이너 안에서 갱신한다. CI에서는 거부된다 |

## 통합 테스트

```
tests/sitl/run_sitl.sh --stack 0                       # 스택을 올리고 시나리오를 돌린 뒤 내린다
tests/sitl/run_sitl.sh --stack 0 --repeat 3            # 회마다 down 뒤 콜드 up으로 3번. 첫 실패에서 멈춘다
tests/sitl/run_sitl.sh --attach <실행 디렉터리>         # 이미 떠 있는 스택에 붙어 pytest와 수집만 한다
tests/sitl/run_sitl.sh --stack 0 -- -k test_b          # `--` 뒤는 pytest 인자
```

- `--stack k`는 스택 번호(0-9, 없으면 `IDSIM_STACK_INDEX`, 없으면 0). 로컬과 CI(`sitl.yml`)가 같은 명령을 쓴다.
- 사용자가 QGC와 Gazebo GUI로 눈으로 확인할 때는 `tools/sim_stack.sh up --viz`로 스택을 올리고 출력된 실행 디렉터리를 `--attach`로 넘겨 시나리오 A 등을 돌린다. `--attach`는 스택을 올리지도 내리지도 않고, 산출물은 `<실행 디렉터리>/sitl-attach-<시각>/`에 쓴다.
- `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다(`tools/ros_ws.sh build`).
- 종료 코드는 0 전체 통과, 1 시나리오 실패, 정지 검사 실패, ULog 교차 확인 실패, 2 사용법, 선행 조건, 스택 올리기 실패, ULog 교차 확인 입력 없음과 판정 불가. 마지막 stdout 줄이 실행 디렉터리다.
- 시나리오와 판정, 산출물은 `tests/sitl/README.md`를 본다.

## 화면으로 보기

스택을 `tools/sim_stack.sh up --viz`로 올리면 Gazebo GUI(compose `viz` 프로필의 `gz-gui`)가 함께 뜬다. QGroundControl은 `tools/qgc.sh --stack k`로 호스트에서 띄운다. 기체 출발 위치는 `config/fleet.yaml`의 `world.origin`(기본 서울시청)이다. 자세한 것은 `docker/README.md`의 "시각 도구" 절을 따른다.

## 스택과 스택 번호

스택은 서로 격리된 시뮬레이션 한 벌이다. 에이전트, Gazebo 서버, 기체 px4-N, `/clock` 브리지가 compose 프로젝트 하나로 함께 뜬다. Gazebo GUI와 QGroundControl은 스택이 아니라 떠 있는 스택에 붙는 화면 도구다.

같은 호스트에 스택이 둘 있거나 다른 ROS 2, Gazebo가 함께 떠 있으면 여러 계층에서 통신이 섞이거나 이름이 충돌한다. 스택 번호 k(0-9, 기본 0. `--stack k` 또는 환경 변수 `IDSIM_STACK_INDEX`)에서 계층마다 하나씩 격리 값을 파생해 이를 막는다.

| 값 | 막는 충돌 |
| --- | --- |
| compose 프로젝트 `idsim-k` | 컨테이너와 네트워크 이름 |
| ROS 2 도메인 20 + k | ROS 토픽(DDS)이 다른 스택이나 다른 ROS 2와 섞이는 것 |
| 에이전트 포트 8888 + k | PX4의 uXRCE-DDS 클라이언트가 다른 스택의 에이전트에 붙는 것(UDP) |
| Gazebo 파티션 `idsim-k` | gz-transport 토픽과 모델이 다른 Gazebo와 섞이는 것 |
| QGC GCS 포트 14550 + 1000k | MAVLink UDP 포트 |

다른 프로그램과 겹치면 k를 바꾼다(`tools/sim_stack.sh up --stack 1`, `tools/qgc.sh --stack 1`). k가 다르면 idsim 스택 둘을 동시에 띄울 수 있다. 자세한 것은 `docker/README.md`의 "격리 규칙" 절을 본다.

## 알려진 제약

- 이미지 빌드의 apt 미러는 `docker/versions.env`의 `UBUNTU_APT_MIRROR`(기본 kr 미러)이다. 다른 호스트에서 바꾸는 방법은 `docker/README.md`의 "apt 미러" 절을 본다. 해당 미러가 막히면 콜드 빌드가 실패한다.
- GHCR의 이미지를 빌드 없이 받아 쓰는 경로는 아직 없다.

## 문서 지도

| 문서 | 내용 |
| --- | --- |
| `docs/architecture.md` | 설계 |
| `docs/roadmap.md` | Phase별 계획 |
| `docs/smoke-test.md` | 환경 스모크 설계 |
| `docker/README.md` | 이미지와 compose |
| `CLAUDE.md` | 작업 규칙 |

`docs-for-agent/`는 에이전트용 정보이므로 처음 읽을 필요가 없다.
