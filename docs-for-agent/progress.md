# idsim 진행 상황

세션을 시작할 때 지금 어디에 있는지 파악하는 파일이다. 지금 유효한 것만 적는다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`, 진행 중인 단계가 있으면 그 계약과 결정은 `docs-for-agent/plan-*/`에 있다. 경위는 git(커밋 메시지, PR 본문)에서 본다. 담당자 구성, 호출 규칙, 모델 선택은 `CLAUDE.md`에 있다.

## 현재 상태

| Phase | 상태 |
| --- | --- |
| 1 | 완료. 계약은 `docs/interface.md`에 고정 |
| 2 | 시작 전 |
| 3 | 시작 전 |

## 다음 작업

1. Phase 2 착수 전 설계 토론("Phase 2와 3 전에 정할 것"의 첫 항목).

## 운영 규칙

- 실험용 스택 번호는 px4 5, ros2 6, test 7, devops 8, sim 9. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.
- 작업 branch를 push해 PR을 만들고, CI 통과와 owner 승인 뒤 merge commit으로 main에 머지한다.
- `idsim_mission`의 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자다(`file-ownership.md`).
- 그림은 계층으로 나눈다. 개요 그림은 묶음과 주요 경로만, 상세 그림은 개요의 상자 하나를 펼치고 도입 문장에 어느 상자인지 적는다. 같은 내용을 두 그림에 그리지 않는다. 그림 하나는 node 8개, edge 10개 이하, subgraph 중첩 1단, node label 두 줄, edge label 15자 이하이고 넘으면 나눈다. 포트, 환경변수, 경로, 명령줄은 label에 넣지 않고 그림 아래에 둔다(사용자 결정).
- 대표 시나리오의 통과를 기준으로 개발한다. 경계 상황은 보수적 기본 동작과 "미확인" 표기로 덮고, 새 실측은 관찰된 문제의 재현용으로만 하며, 산출물은 최소로 둔다.
- 저장소 라이선스는 Apache-2.0. 새 소스와 CMake 파일에 머리말을 넣고 `ament_copyright`와 cpplint `legal/copyright` 검사를 켠 채로 둔다.
- CI와 판정의 기준은 x86_64 Linux runner와 arm64 Linux runner 둘이고, Apple Silicon Mac(arm64)은 개발 호스트다. 이미지 key는 아키텍처와 무관하게 이미지마다 하나이고, GHCR의 key 태그는 두 플랫폼의 multi-arch index다. Mac의 조건과 제약은 `README.md` "호스트 조건".
- 이미지 빌드의 apt 미러 기본값은 kr 미러(`docker/versions.env`의 `UBUNTU_APT_MIRROR`), CI의 amd64 runner는 우분투 기본 미러, arm64는 ports 미러(`tools/ci/image_keys.py`의 `CI_MATRIX`). ros-ws 이미지에 clang-tidy와 clang-format을 둔다.

지금 유효한 사용자 결정.

- 문자 집합 검사는 ripgrep(`rg`)으로 한다(`tools/ci/lint.sh charset`).
- `FOXGLOVE_BRIDGE_VERSION`은 3.6.3이다. ROS apt 저장소에 옛 버전이 남지 않기 때문이다.
- CI와 판정의 기준은 x86_64 Linux runner와 arm64 Linux runner 둘이다.
- `sitl` job은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외)와 main push에서 돈다. `lint`, `unit`도 `pull_request`와 `push: main`.
- replay job의 trigger는 Phase 2에서 정한다. 그때 `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 고친다.
- CI `sitl` 목표 15분. 비행 시나리오(F1-F4)를 모두 PR CI에 두고, 넘으면 겹치는 비행 구간 -> waypoint 수 -> Hold 시간 순으로 줄인다. F2의 공중 종료와 F3의 공중 시작은 빼지 않는다.
- Gazebo 정답 pose(`/sim/`)를 SITL MCAP 기록물에 넣는다(Phase 2부터 효과).
- `docs-for-agent/file-ownership.md`의 소유자는 architect.
- 수동 비행을 하지 않으므로 QGroundControl을 지원하지 않는다(실행 도구, 버전 고정, 완료 기준에 없다). 화면 확인은 Gazebo GUI와 Lichtblick이다.

## 미해결 사항

사용자가 미룬 것.

- 고도 제한: 미션 고도에 상하한이 없다(TAKEOFF `height_m`은 양수만, GOTO z와 offset z는 좌표 상한만, 음수 허용). TRACK_ENTITY setpoint z는 실행 중 검사가 없고 PX4 `GF_MAX_VER_DIST`도 꺼져 있다(v1.17.0 기본 0). 범위 값과 두 겹(미션 검증, PX4 geofence)을 사용자가 정한다.

main 머지 뒤 확인할 것.

- arm64 runner의 `sitl` 판정 확인: 판정 상수는 amd64에서 보정했다. arm64 runner에서는 build workflow 수동 실행(입력 `sitl`)으로 `run_sitl.sh --stack 0` 1회 통과(21 passed, 판정 구간 RTF 1.000)만 보았다. 새 key가 GHCR에 올라간 뒤 `sitl (arm64)` job의 결과(RTF, 목표 15분)와 반복 실행의 흔들림을 확인한다.

문서 정리(정형, 다음 문서 정리 때).

- Dockerfile 주석에 남은 계획 표지: `Dockerfile.px4` 36, 226행 "(S1)"은 "(스모크 embedded 단계)", `Dockerfile.ros-ws` 56행과 `Dockerfile.xrce-agent` 39행 "스모크 S0가"는 "스모크 images 단계가", `Dockerfile.sim-base` 4행 "(지금은 README의 수동 docker run, 3단계부터 gz-gui 서비스)"는 "(viz 프로필의 gz-gui 서비스)"로 바꾼다. Dockerfile을 바꾸면 이미지 key가 바뀌어 PR의 sitl이 실패하므로 주석만 따로 고치지 않고, 그 Dockerfile을 실제로 바꾸는 이미지 PR에 함께 넣는다(각 owner).
- `idsim_common/vehicle_command.hpp` 주석의 MAVLink 재송출 문장에 소스 행(v1.17.0 `COMMAND_LONG.hpp` 82-96행)을 적는다(ros2-engineer). `gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"를 고친다(sim-engineer).

테스트 보강.

- 종료 단계에서 대비책 뒤 지상 DISARMED를 `DisarmConfirm`으로 세는 연결을 가르는 사례가 없다. timestamp가 전송 stamp 이하인 지상 DISARMED 셋으로는 끝나지 않음을 `GroundEndWithFallbackDisarm` 경로와 `FallbackDisarmConfirmKeptOnLandPath`의 AIR_LAND에서 단정한다. `step_mission_end` (6a) 단계의 ack 버림 줄은 주석을 달거나 지운다(ros2-engineer, test-engineer, px4-engineer).
- 공중 Offboard 진입의 DO_SET_MODE에서 첫 OFFBOARD 표본까지의 시간 D [추정]을 기존 산출물(A의 LAND, D의 Hold)의 모드 표본 간격으로 [실측]으로 바꾼다(px4-engineer).
- ACCEPTED 사건 stamp의 건전성을 노드 테스트로 덮을지 판정으로 덮을지(test-engineer, ros2-engineer).
- 성공 sitl run의 summary.md에 ULog `battery_status`, `cpuload`, `system_power` 마지막 표본 시각을 남겨 숨은 발행 정지를 센다. trace 이정표에 수신 시각을 남긴다(test-engineer, logging-engineer).
- `test_px4_topic_names.py::test_argument_checks`의 SpinThread `InvalidHandle` 경고, `tools/vehicle_arming_state.py`의 rc 2 사례 테스트(test-engineer).
- 스모크 images 단계가 `LLVM_MAJOR`, `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다(test-engineer). `ros_ws.sh`에 `versions.env` 이름 기준 존재 검사를 둘지(devops-engineer, test-engineer).

빌드와 CI.

- `sitl.yml`은 GHCR에서 이미지 key로 pull하므로 이미지 key가 바뀌는 PR은 PR과 머지 직후 main 양쪽에서 pull이 실패한다. 머지 전 확인 수단은 build job이 빌드한 이미지로 두 runner에서 도는 스모크 네 단계와, build workflow 수동 실행의 입력 `sitl`로 도는 `tests/sitl/run_sitl.sh --stack 0`이다. publish 뒤 main에서 `sitl`을 다시 돌린다. `workflow_run`으로 묶을지 등은 devops-engineer와 architect가 정한다.
- 같은 key로 두 번째 main build가 돌 때 이미지 5종이 모두 SKIP되는지 확인한다(devops-engineer).
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다. `tools/ros_ws.sh tidy`의 대상 0개 통과를 `ci`에서 바꿀지(ros2-engineer, devops-engineer).
- 비결정 빌드 요소(ros.key, gazebo.gpg URL, apt 저장소 상태, pip 인덱스)는 이미지 key에 들어가지 않는다. apt `Acquire::Retries` 미적용이라 미러 장애나 동기화 시차로 apt 단계가 실패할 수 있다.
- 실패 run의 `artifacts/runs/`가 job artifact로 올라가는지 확인하고, CI 기록이 쌓이면 SITL 판정 상수를 재검토한다.

시뮬레이션과 화면 도구.

- `fleet.yaml` spawn 좌표에 미션과 같은 상한(1e5 m)을 둘지(devops-engineer, 급하지 않음).
- 이 호스트의 포트 5900과 8090은 다른 프로젝트가 쓴다. VNC를 도입하면 피한다.
- PX4 버전을 올리면 "ULog `vehicle_command` `timestamp`가 보낸 쪽(Executor)의 stamp와 같다"와 "ack 기록 순서가 처리 순서와 같다"를 다시 확인한다(px4-engineer).
- [미확인]으로 둔 것(관찰된 문제가 있을 때만 잰다): `GZ_IP` 없는 디스커버리, `ops-N` goal 실행 중 stop의 종료 사건, `vehicle.id` 누락에서 unhealthy까지의 시간, 에이전트 Fast DDS 멀티캐스트의 LAN 섞임, MAVLink bind 실패 시 PX4 동작, compose `start_interval`의 Docker 하한.

Phase 2와 3 전에 정할 것.

- Phase 2 착수 전 설계 토론(ops-service-engineer, logging-engineer, architect): `VehicleState`의 ROS 시각 역행 처리(replay 일시정지와 배속 포함), 소비자 미수신 timeout 배수, stamp 단조성, WebSocket JSON 표현, gRPC `StreamMissionEvents`와 ROS `MissionEvent`의 관계, 기록기의 구독 확인 순서.
- ULog가 `compose down`에서 정상 종료되는지(기체당 약 1 GB/h, logging-engineer).
- 반복 이륙(첫 항목이 아닌 TAKEOFF)은 소비자가 생길 때 허용한다.
- `docs/interface.md` "시간 기준"의 유지 조건을 부하 아래에서 다시 확인한다(Phase 2).
- 기체별 `RTL_RETURN_ALT` 예외를 정한다(Phase 3).
- Fleet 배분 전 검증은 `validate_mission_contract`로 한다. 공중 종료 끝점 계획을 세우고, 공중 시작은 Hold 기체에만 허용한다(Phase 3).
- `SET_GPS_GLOBAL_ORIGIN` 안(Phase 3 후보).
- 정답 pose 기록의 대상과 기록물 디렉터리 규약을 정한다(Phase 2).
- Gazebo 기반 표적 생산자(확장 항목).
- gz-gui 생존 확인 자동화(플래키가 보일 때).
- Phase 3: Fleet 재시작 복구 경로, 이탈 기체 goal 재배분 한 번, 주기 하한 계약이 필요한 토픽 목록(px4-engineer), lockstep 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지).

## 새 개발 PC에서 시작할 때

1. `git clone https://github.com/danielhongwoo/idsim.git`. 열린 브랜치와 PR은 `gh pr list`로 본다.
2. 호스트 조건과 환경 구성은 루트 `README.md`의 "호스트 조건"과 "빠른 시작"을 따른다. 이어서 `tools/ci/lint.sh all`과 `tools/ros_ws.sh ci`가 통과해야 한다.
3. 이미지는 `python3 tools/ci/build_images.py --mode pull`로 GHCR에서 받을 수 있다(key는 `python3 tools/ci/image_keys.py`, main build가 올린 뒤에만. Mac은 arm64 index가 올라온 뒤에만 받을 수 있고 그 전에는 `--mode load`로 로컬 빌드한다).
4. 같은 호스트의 다른 ROS 2 스택, Gazebo, compose 프로젝트를 먼저 보고(`docker ps`, `docker compose ls`) 겹치면 스택 번호를 바꾼다.
5. `gh pr edit`는 이 저장소에서 GraphQL Projects(classic) 오류로 실패한다. PR 본문은 `gh api -X PATCH repos/danielhongwoo/idsim/pulls/<번호> -F body=@<파일>`로 고친다.
6. 사용자 전역 규칙 `~/.claude/CLAUDE.md`(커밋 메시지에 도구 트레일러 금지)를 새 PC에도 둔다. 로컬 `artifacts/`는 옮겨지지 않는다.

## 갱신 규칙

- 작업 단위가 끝나면 "현재 상태"를 고쳐 쓰고, 끝난 "다음 작업"과 닫힌 "미해결 사항"은 지운다. 완료 표시, 날짜, 경위를 남기지 않는다.
- 항목은 한두 줄로 쓴다. 근거, 실측값, run id, 검토 경과는 커밋 메시지와 PR 본문에, 계약은 `docs/`(진행 중인 단계는 그 계획 디렉터리)에 둔다.
- 사용자만 정할 수 있는 사항(범위, 언어 선택, 비용)은 "미해결 사항"의 첫 묶음에 올린다.
