# idsim

idsim은 Interceptor Drone Simulator의 약자다. PX4 SITL, Gazebo Harmonic, ROS 2 Jazzy 위에서 드론 여러 대의 운용 서비스(Fleet, Mission, Telemetry, Replay)를 컨테이너로 돌리는 시뮬레이션 플랫폼이다. 지원 호스트는 x86_64 Linux뿐이다.

계획과 단계는 `docs/roadmap.md`, 설계는 `docs/architecture.md`에 있다.

## 호스트 조건

| 항목 | 조건 |
| --- | --- |
| OS와 CPU | x86_64 Linux (Ubuntu 24.04에서 확인) |
| Docker | Docker Engine, compose v2 플러그인, buildx. 사용자가 docker 그룹에 속해야 한다(`sudo usermod -aG docker $USER` 뒤 다시 로그인). Ubuntu 24.04 패키지는 `docker.io`, `docker-compose-v2`, `docker-buildx`이고, Docker 공식 저장소는 `docker-ce`, `docker-compose-plugin`, `docker-buildx-plugin`이다 |
| 도구 | git, python3 (표준 라이브러리만 사용. 3.12에서 확인, 하한 3.10), curl, sha256sum |
| 디스크 | 30GB 이상 권장. 근거: 이미지 5종 합 약 8.6GB(공유 레이어 중복 포함이라 실제 점유는 더 작다) + px4 builder 단계 7.7GB + buildkit 캐시 |
| 메모리 | 16GB 이상. 개발 VM 31GB와 CI 러너 16GB에서 확인했고 그 아래는 미실측 |
| 선택 | gh (PR을 올리거나 합칠 때), 화면 확인용 X11 또는 XWayland 데스크톱 |

조건은 `tools/check_host.sh`가 점검한다. 시스템을 바꾸지 않고 조회만 하며, 외부 네트워크 검사는 `--offline`으로 건너뛴다.

## 빠른 시작

```
tools/check_host.sh
python3 tools/ci/build_images.py --mode load
tests/smoke/run_smoke.sh S0
tests/smoke/run_smoke.sh S2
tools/ci/lint.sh all
```

| 명령 | 확인하는 것 |
| --- | --- |
| `tools/check_host.sh` | 호스트가 위 조건을 갖췄는지, 포트와 미러 접근에 문제가 없는지 |
| `python3 tools/ci/build_images.py --mode load` | 이미지 5종을 로컬에 빌드한다. 콜드 빌드는 CI 실측 약 22분. 로컬 16 vCPU에서 PX4 컴파일 단계는 163초였다 |
| `tests/smoke/run_smoke.sh S0` | 이미지 버전과 `docker/versions.env`의 일치 |
| `tests/smoke/run_smoke.sh S2` | PX4와 Gazebo 연동, 파라미터 저장값 |
| `tools/ci/lint.sh all` | CI와 같은 린트 전체 (호스트에 린터 설치가 필요 없다) |

## 화면으로 보기

QGroundControl은 `tools/qgc.sh`로, Gazebo GUI는 수동 `docker run`으로 띄운다. 명령은 `docker/README.md`의 "시각 도구" 절을 따른다.

## 같은 호스트에 다른 ROS 2나 Gazebo가 있을 때

idsim은 스택 번호 k(기본 0, 환경 변수 `IDSIM_STACK_INDEX`)에서 격리 값을 파생한다.

| 항목 | 값 |
| --- | --- |
| ROS 2 도메인 | 20 + k |
| 에이전트 포트 | 8888 + k |
| Gazebo 파티션 | idsim-k |
| compose 프로젝트 | idsim-smoke |

겹치면 k를 바꾼다. 현재 compose 프로젝트 이름이 k와 무관하므로 스모크는 호스트당 하나만 돌린다. 자세한 것은 `docker/README.md`의 "격리 규칙" 절을 본다.

## 알려진 제약

- apt 미러가 archive.ubuntu.com에 고정되어 있어, 미러 장애 시 콜드 빌드가 실패한다 (2026-11-09 실측, 미해결).
- GHCR 이미지가 공개되면 빌드 없이 받아 쓰는 경로를 검토 중이다.

## 문서 지도

| 문서 | 내용 |
| --- | --- |
| `docs/architecture.md` | 설계 |
| `docs/roadmap.md` | Phase별 계획 |
| `docs/smoke-test-phase1a.md` | 환경 스모크 설계 |
| `docker/README.md` | 이미지와 compose |
| `CLAUDE.md` | 작업 규칙 |

`docs-for-agent/`는 에이전트용 기록이므로 처음 읽을 필요가 없다.
