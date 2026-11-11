# idsim 진행 상황

에이전트와 작업자가 세션을 시작할 때 지금 어디에 있는지 파악하기 위한 파일이다. 지금 유효한 것만 적는다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`, 진행 중인 단계의 계약은 `docs-for-agent/plan-*/decisions.md`에 있다. 무엇이 언제 왜 바뀌었는지는 여기에 적지 않고 git(커밋 메시지, PR 본문)에서 본다.

## 현재 상태

| Phase | 상태 |
| --- | --- |
| 1a | 진행 중. 1-5단계 완료, 6단계 진행 중, 7단계 시작 전 |
| 1b | 시작 전 |
| 2 | 시작 전 |
| 3 | 시작 전 |

Phase 1a의 단계별 위치(단계 번호는 `docs/roadmap.md`).

| 단계 | 상태 |
| --- | --- |
| 1 환경 스모크 테스트 | 완료. 골든은 `tests/fixtures/px4/v1.17.0/` |
| 2 CI 골격 | 완료. `lint`, `build`, `unit` job |
| 2b 시각 도구 준비 | 완료 |
| 3 `config/fleet.yaml`과 `tools/gen_compose.py` | 완료 |
| 4 `idsim_common` | 완료 |
| 5 `idsim_interfaces` | 완료. 계약은 `docs-for-agent/plan-1a-5-idsim-interfaces/decisions.md` |
| 6 이륙-호버-착륙 노드와 통합 테스트 | 진행 중. 계획은 `docs-for-agent/plan-1a-6-idsim-mission/README.md`, 계약은 같은 디렉터리 `decisions.md`. P0(CI trigger), P1(ros-ws 이미지의 foxglove_bridge), P2(`idsim_common` 추가), P3a(런타임 확인)는 완료. P3(`idsim_mission` 패키지) 구현 중. P4(생성기, 통합 테스트, `sitl` job, 문서)와 P5(viz)는 시작 전 |
| 7 `docs/interface.md` | 시작 전 |

환경.

- 저장소 원격은 github.com/danielhongwoo/idsim, 이미지 레지스트리는 ghcr.io/danielhongwoo/idsim이다. 이미지 5종의 현재 key는 익명으로 조회된다.
- CI의 `lint`와 `unit`은 `pull_request`와 `push: main`에서 돈다. PR이 없는 브랜치 push에는 CI가 돌지 않는다. `build`는 PR에서 빌드만 하고 main에서만 GHCR에 올린다.
- 개발 호스트는 x86_64 Ubuntu 24.04 VM(16 vCPU, 31GB, NVIDIA 없음, GNOME Wayland)이다. 이 호스트에서 archive.ubuntu.com이 응답하지 않는 날이 있어 이미지 빌드의 apt 미러 기본값이 kr 미러다.
- 스모크와 스택의 실행 기록 `artifacts/`는 git에 추적되지 않으므로 다른 PC로 옮겨지지 않는다. 판정에 필요한 golden은 `tests/fixtures/`에 추적된다.

## 운영 규칙

담당자 구성과 모델 선택의 기본은 `CLAUDE.md`에 있다. 아래는 그 밖에 지금 적용되는 규칙이다.

- 문서에는 지금 유효한 것만 둔다. 이력(누가 언제 무엇을 왜 바꿨는지, 실측 run, 검토 경과)은 커밋 메시지와 PR 본문에 적는다(사용자 결정).
- px4-engineer의 읽기 전용 확인과 정형 작업은 sonnet으로 부른다(사용자 결정. 기본 모델 opus의 예외). 실측, 구현, 설계 토론에는 적용하지 않는다.
- px4-engineer 호출이 모델 안전장치 오류로 중단되어도 운용 방법을 바꾸지 않는다(사용자 결정). 계속 호출하고, 중단되면 다시 호출한다. 그래도 답을 받지 못한 검토 항목은 미결로 적고 architect에게 알린다.
- 실험용 스택 번호는 px4 5, ros2 6, test 7, devops 8이다. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.
- 관련 owner의 승인 없이 머지하지 않는다. `idsim_mission`의 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자다(`file-ownership.md`).

지금 유효한 사용자 결정.

- U1: 공중 취소 시나리오 D와 `[LAND]` 한 항목 미션은 1a 필수다.
- U2: `sitl` job은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외)와 main push에서 돈다. `lint`와 `unit`의 trigger도 `pull_request`와 `push: main`이다.
- U3: 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작은 1b에서 정한다. 1a 노드는 그런 미션을 INVALID_MISSION으로 거부한다.
- U4: replay job의 trigger는 replay job을 만드는 Phase 2에서 정한다.
- 저장소 라이선스는 Apache-2.0이다. 새 소스와 CMake 파일에 머리말을 넣고 `ament_copyright`와 cpplint `legal/copyright` 검사를 켠 채로 둔다.
- 이미지 빌드의 apt 미러 기본값은 kr 미러(`docker/versions.env`의 `UBUNTU_APT_MIRROR`)이고 CI는 우분투 기본 미러를 쓴다.
- ros-ws 이미지에 clang-tidy와 clang-format을 그대로 둔다. 별도 도구 이미지로 빼지 않는다.
- `tools/qgc.sh`에 설정을 되돌리는 옵션을 두지 않는다. 기본 포트로 돌리려면 `--stack 0`을 쓴다.

## 다음 작업

1. 1a 6단계 P3 `idsim_mission` 패키지(ros2-engineer. `px4/` 디렉터리는 px4-engineer. `ExecuteMission.action`의 상수 둘과 golden은 architect). 머지 전에 px4-engineer의 필수 승인과 reviewer 검토를 받는다.
2. P4의 선행 작업: 측정 스크립트를 `tests/sitl/measure/`에 만든다(test-engineer, 절차 승인 px4-engineer). px4-engineer의 필수 재실측 (2), (3), (5)는 P4 머지 조건이다(`plan-1a-6-idsim-mission/decisions.md` 넘김 목록).
3. P4 생성기와 통합(devops-engineer, test-engineer, architect의 문서 반영). `ops-N` 서비스, params와 `stack.json` key, `tests/sitl/`, CI `sitl` job, `build_images.py --mode pull`.
4. P5 viz(devops-engineer). `foxglove`와 `lichtblick` 서비스, 브라우저 실접속 확인.
5. 6단계 마무리: 통합 테스트 로컬 3회 연속 통과, CI `sitl` 통과, 사용자가 QGC와 Gazebo GUI로 같은 비행을 확인.
6. P3 PR이 머지되면 `plan-1a-6-idsim-mission/decisions.md`를 지금 유효한 계약만으로 다시 쓴다(architect).
7. 1a 7단계 `docs/interface.md`. ros2-engineer가 `tools/to_interface.py`로 초안을 내고 architect가 확정한다. 계약 고정 전에 px4-engineer의 나머지 필수 재실측이 끝나야 한다.
8. CI 후속 PR. `Dockerfile.px4`의 pip 고정과 `PX4_OPTICAL_FLOW_REF` 반영, `ls | grep` 정리(px4-engineer). `Dockerfile.sim-base`의 `GZ_APT_KEY_FPR` 검증(sim-engineer). ruff 임시 예외 정리(test-engineer). 설계 문서의 이미지 key 재료 설명 갱신(architect. `UBUNTU_APT_MIRROR`를 key에서 뺀 것이 "같은 key는 같은 바이트"의 예외라는 점 포함). `image_keys.py`가 bake 블록의 tags와 공백까지 해시하는 것 정리(devops-engineer).

## 미해결 사항

사용자 결정이나 확인이 필요한 항목.

- GHCR 패키지 5개와 buildcache가 Public인지 설정 화면에서 확인한다. 비공개면 포크 PR과 익명 조회가 거부되어 매번 전체를 다시 빌드한다.

1a 6단계.

- 감시 표의 행 순위는 필수 재실측 (4) 전까지 잠정이다. 필수 재실측 여덟 항목은 `plan-1a-6-idsim-mission/decisions.md` 넘김 목록에 있다.
- 스모크 images 단계(`tests/smoke/run_smoke.sh`의 check_s0)가 `LLVM_MAJOR`와 `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다. `tools/ros_ws.sh`의 대조는 이미지에 있는 ENV만 돌아서 그 ENV가 없는 옛 ros-ws 이미지가 통과한다. 옛 `:local` 이미지로 `sim_stack.sh up --viz`를 하면 foxglove만 죽는다. P4 또는 P5 전에 images 단계에 넣는다(test-engineer). `ros_ws.sh`에 `versions.env`의 이름 기준 존재 검사를 둘지는 devops-engineer와 test-engineer가 정한다.
- foxglove_bridge의 판은 `FOXGLOVE_BRIDGE_VERSION` 접두 단정까지만 고정된다. ROS sync로 새 판이 오면 ros-ws key가 바뀌는 PR의 빌드가 실패한다(의도한 동작). 같은 판 안의 revision과 의존 패키지는 고정되지 않는다.
- Lichtblick 공식 이미지(1.30.0. 이미지 label의 2.5.2는 베이스 Caddy의 버전)가 두 서브프로토콜을 제시하는 것만 확인했다. foxglove_bridge와의 브라우저 실접속은 P5에서 확인한다.
- `px4-api` 검사는 C++과 `.py`만 본다. params와 remap yaml이 생기는 P4에서 범위를 넓힌다.
- PX4 timestamp와 `/clock`이 같은 축이라는 것의 회귀 판정은 6단계 failsafe 테스트까지 없다. 스모크 clock 단계에 `vehicle_status.timestamp`와 `/clock`의 차이 상한 판정을 넣을지 px4-engineer와 test-engineer가 검토한다.
- `artifacts/`를 CI job 아티팩트로 올리는 것은 `sitl` job을 만드는 P4에서 확인한다.

1a 7단계(`docs/interface.md`)에 적을 것.

- `COM_RC_IN_MODE`가 4라 QGC 수동 모드와 가상 조이스틱은 쓸 수 없다(ros2-engineer 초안, px4-engineer 확인).
- QGC 하나는 한 번에 한 스택만 본다는 제약, 포트와 식별자 표, SIH 변형의 `PX4_HOME_*` 주의.

빌드와 CI.

- 비결정 빌드 요소: PX4-OpticalFlow master(px4 builder, 결과물은 버려짐), empy 외 pip 패키지 미고정, ros.key와 gazebo.gpg URL 미고정(다음 작업 8).
- apt 미러: 지정 미러가 막히면 콜드 빌드가 실패한다. apt `Acquire::Retries` 미적용. CI에서는 Canonical 노드의 동기화 시차로 apt 단계가 간헐적으로 실패할 수 있다(대안: apt 단계 재시도, CI 미러 변경). GHCR 이미지를 받아 태그하는 `build_images.py --mode pull`은 P4에서 만든다.
- `docker/Dockerfile.px4` 132행 주석이 없는 문서 이름 `smoke-test-phase1a.md`를 가리킨다. 주석만 고쳐도 px4 이미지 key가 바뀌므로 다음에 그 파일을 바꿀 때 `smoke-test.md`로 함께 고친다(px4-engineer).
- `.github/workflows/build.yml`, `build-images.yml`, `tools/ci/image_keys.py`, `tools/ci/build_images.py`에 음차("키", "잡")가 남아 있다. 다음에 고칠 때 바꾼다.
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다(`src/`의 소스가 include하는 헤더만 검사된다). 헤더 전용 검사를 둘지, `test/`를 tidy 대상에 넣을지 정한다(ros2-engineer, devops-engineer).
- `tools/ros_ws.sh tidy`는 대상이 0개이면 PASS-NO-TARGETS로 통과한다. `ci`에서는 경고나 실패로 바꿀지 검토한다(devops-engineer).
- 이미지 ENV와 `versions.env`의 대조는 스모크 images 단계와 `tools/ros_ws.sh`에서만 일어난다. 다른 스모크 단계를 단독 실행하면 대조가 없다.
- `gen_compose.sh`의 `--run-id` 인자 제거(devops-engineer).
- compose healthcheck `start_interval`의 Docker 하한은 실측하지 않았다(Docker 29.1.3, Compose 2.40.3에서 동작). `check_host.sh`에 넣을 값은 devops-engineer가 정한다.
- `tools/check_host.sh`의 셸 단위 테스트(가짜 ss, df, docker)는 두지 않았다(test-engineer 판단).

시뮬레이션과 화면 도구.

- Gazebo GUI 깜빡임(VMware 3D 가속을 켠 상태). `QSG_RENDER_LOOP=basic`과 `vblank_mode=1`의 효과는 확인되지 않았다. 다음 후보: SceneBroadcaster `state_hertz` 낮추기, `--render-engine-gui ogre`.
- `ros_ws/src/idsim_sim/scripts/gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"는 표현이 부정확하다(sim-engineer).
- `qgc.sh`의 sha256 불일치 시 종료 코드 1 경로는 실행으로 확인하지 않았다.
- 실측하지 않은 것: `GZ_IP=127.0.0.1`을 뺐을 때의 gz-transport 디스커버리, GPS 잡음의 출처, bridge healthcheck의 `ROS_LOG_DIR=/tmp/hc`가 run 디렉터리에 로그를 남기지 않는지, 에이전트의 Fast DDS 멀티캐스트가 같은 LAN의 다른 호스트와 섞이는지, MAVLink bind에 실패한 PX4의 동작, passwd에 없는 uid 1001로 지금 스택이 도는지.
- 이 호스트의 포트 5900과 8090은 다른 프로젝트가 쓴다. VNC를 도입하면 피한다.

1b 전에 정할 것.

- 다대 원점 판정의 pose 보정 방식(`check_px4 --expect-pose-enu` 또는 `stack.json`의 기체별 기대 위경도). 지금 `--expect-origin`은 1대 기준이다(architect, test-engineer).
- 기체별 EKF 원점은 월드 원점이 아니라 스폰 지점이다. 월드 ENU `TargetState`를 기체 NED setpoint로 바꾸는 입력과, 커스텀 월드에서 `world.origin`과 SDF `<spherical_coordinates>`의 일치를 검사하는 주체를 정한다. 월드 SDF에 `<plugin>`이 하나라도 있으면 서버 설정 파일이 무시된다.
- bridge healthcheck는 `/clock` 1회 수신을 유지하고 표적 어댑터 판정은 별도 단계로 둔다. 커스텀 모델은 `GZ_SIM_RESOURCE_PATH`에 `/opt/idsim/sim/models`를 더해야 한다.

Phase 2와 3 전에 정할 것.

- replay job의 trigger(U4). `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 그때 고친다.
- ULog가 `compose down`에서 정상 종료되는지 확인한다. 기록량은 약 285 KiB/s, 기체당 약 1 GB/h다(logging-engineer, Phase 2 전).
- Phase 3에서 주기 하한 계약이 필요한 토픽 목록(px4-engineer).
- lockstep의 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지)은 실측하지 않았다. Phase 3 CPU 포화 해석의 전제다.

## 새 개발 PC에서 시작할 때

1. 호스트 조건과 환경 구성 순서는 저장소 루트 `README.md`의 "호스트 조건"과 "빠른 시작"을 따른다(`tools/check_host.sh`, 이미지 빌드, 스모크 images, px4-out, px4-in, clock). `tools/ci/lint.sh all`과 `tools/ros_ws.sh ci`가 통과해야 한다.
2. 같은 호스트에 다른 ROS 2 스택, Gazebo, compose 프로젝트가 있는지 먼저 본다(`docker ps`, `docker compose ls`). 겹치면 스택 번호 k(`--stack k` 또는 `IDSIM_STACK_INDEX`)를 바꾼다.
3. PR을 올리려면 gh(GitHub CLI)에 로그인한다(`gh auth login`).
4. 사용자 전역 규칙은 저장소 밖에 있다: `~/.claude/CLAUDE.md`(커밋과 PR에 공동 저자 줄을 넣지 않는다). 새 PC에도 같은 파일을 둔다.

## 갱신 규칙

- 이 파일에는 지금 유효한 것만 둔다. 작업 단위가 끝나면 "현재 상태"의 해당 칸을 고쳐 쓰고, 끝난 "다음 작업"과 닫힌 "미해결 사항"은 지운다. 완료 표시나 날짜를 붙여 남기지 않는다.
- 결정은 이 파일에 기록으로 쌓지 않는다. 설계 규칙이면 `docs/architecture.md`(환경 스모크는 `docs/smoke-test.md`, 계약 문장은 `docs/interface.md`)를, 진행 중인 단계의 계약이면 그 단계의 `decisions.md`를 현재형으로 고치고, 근거와 경위는 그 변경의 커밋 메시지와 PR 본문에 적는다.
- 사용자 결정과 담당자 운용 규칙처럼 설계 문서에 자리가 없는 규칙은 "운영 규칙"에 현재형으로 적는다. 바뀌면 고쳐 쓰고 옛 문장을 남기지 않는다.
- 사용자만 정할 수 있는 사항(범위, 언어 선택, 비용)은 "미해결 사항"의 첫 묶음에 올린다.
- 실측값, run id, 검토 경과는 PR 본문에 적는다. 설계 문서에는 규칙의 근거가 되는 사실만 남긴다.
