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
2. Zenoh 실험 결과의 계약 반영(architect). 중복 goal id 요청을 접수하지 않는 결정안(아래 "지상 링크 실험 결과")과 `MissionEvent` 접수 사건 유실, 단절 중 끝난 미션의 결과, action 내부 토픽 type hash, 지상 노드의 시간 기준을 `VehicleState`와 `MissionEvent` 고정 전에 정한다. 사용자 승인과 "미해결 사항"의 질문이 먼저다.
3. 지상 링크의 Zenoh 구성(architect, ros2-engineer, ops-service-engineer, devops-engineer). bridge 버전과 DDS 설정, 기동 순서와 재시작 묶음, allow 목록, router 위치는 정하지 않았다. 기체마다 DDS 도메인을 나누고 그 사이를 Zenoh로 이어 `ExecuteMission`, `VehicleState`, `MissionEvent`만 건네는 구성을 시뮬레이션에 넣는다(`docs/roadmap.md` Phase 3의 선행 항목. 설계는 `docs/architecture.md`에 있고 compose는 아직 스택에 도메인 하나다). `/clock`, 표적 상태, 정답 pose의 공급 도메인, 도메인 ID와 기체별 Agent 포트의 파생 규칙을 함께 정한다. Agent를 기체마다 하나씩 두는 변경도 이 항목에 넣는다. 링크 단절 중 미션의 동작(계속 또는 중단, 재연결 뒤의 정합, 단절과 이탈의 구분)은 방식과 별개로 계약에서 정한다. 단절 중과 재연결 뒤의 cancel, 손실 링크 위의 action 동작(feedback 유실, 취소 지연)은 확인하지 않았다.

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
- GHCR의 기존 이미지와 태그(이전 key 태그, `buildcache`)는 지우지 않는다. 이전 commit으로 돌아가 빌드할 때 필요하다. 정리 정책은 multi-arch index push가 main에서 동작하는 것을 확인한 뒤에 사용자가 정한다.
- `sitl` job은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외)와 main push에서 돈다. `lint`, `unit`도 `pull_request`와 `push: main`.
- replay job의 trigger는 Phase 2에서 정한다. 그때 `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 고친다.
- CI `sitl` 목표 15분. 비행 시나리오(F1-F4)를 모두 PR CI에 두고, 넘으면 겹치는 비행 구간 -> waypoint 수 -> Hold 시간 순으로 줄인다. F2의 공중 종료와 F3의 공중 시작은 빼지 않는다.
- Gazebo 정답 pose(`/sim/`)를 SITL MCAP 기록물에 넣는다(Phase 2부터 효과).
- `docs-for-agent/file-ownership.md`의 소유자는 architect.
- 수동 비행을 하지 않으므로 QGroundControl을 지원하지 않는다(실행 도구, 버전 고정, 완료 기준에 없다). 화면 확인은 Gazebo GUI와 Lichtblick이다.
- 프로젝트의 목적은 실기체 개발을 돕는 것이고 기준은 실기체의 구조다. 문서와 그림은 실기체를 먼저 쓰고 시뮬레이션은 그것을 대신하는 것으로 쓴다.
- 시뮬레이션 환경은 실기체 환경과 최대한 같은 구조로 둔다. 시뮬레이션이 대신하는 것은 실물이 필요한 부분뿐이다. 시뮬레이션에서도 지상 링크는 Zenoh로 잇고 uXRCE-DDS Agent는 기체마다 하나씩 둔다. 무선 구간의 지연과 손실은 시뮬레이션에 넣지 않는다.
- 테스트는 계약의 경계에서 끊어서 한다. 통합 테스트는 기체의 버스에 붙어 계약을 직접 부르고 지상 링크를 거치지 않는다. 지상 링크의 시험은 따로 둔다.
- 실기체 검증(실기체 기록물 리플레이, HITL, 지상 시험, 비행 시험, 실기체 조건 모사 시나리오)은 하드웨어 사양이 정해질 때까지 계획에 넣지 않는다.
- CI와 판정의 기준은 x86_64 Linux runner와 arm64 Linux runner 둘이다. Apple Silicon Mac(arm64)은 개발 호스트이고 container runtime은 OrbStack 기준이다. companion computer용 arm64 이미지는 정하지 않았다.
- GPS는 항상 쓸 수 있다고 가정한다. GPS 없는 비행은 범위 밖이다. 비행 중 GPS 상실 시의 동작은 정하지 않았고 확인하지도 않았다.
- 지상 링크(지상국과 기체 사이의 무선 구간)는 DDS가 아니라 Zenoh로 잇는다. 기체의 ROS 2 버스는 기체 안에 머문다. Zenoh의 구성(bridge 종류, 건네는 토픽의 제한, router 위치)은 실험 뒤에 정한다.
- `MissionEvent`를 지상에서 구독한다. 지상의 어느 컴포넌트가 구독하는지와 기록기의 위치는 정하지 않았다.
- Zenoh bridge가 `ExecuteMission` action과 `VehicleState`, `MissionEvent` 두 토픽을 건너는 것은 조건부로 확인했다(`VehicleState`는 임시 발행자로만 보았다. 조건과 계약에 닿는 예외는 아래 "지상 링크 실험 결과"). `docs/roadmap.md` Phase 2 항목 7은 계약 고정 전에 정할 것의 목록이고, 정한 것이 bridge를 건너는지는 고정 전에 다시 확인한다.

## 미해결 사항

사용자가 미룬 것.

- 실기체 적용 범위: 다음을 할지와 언제 할지를 사용자가 정한다. field 시간 모드(`/clock` 없는 실행과 `UXRCE_DDS_SYNCT=1`), 배치 경계(계약 밖에 무엇이 지상 링크를 넘는지, 기록기와 표적 추적기의 위치), `stack.json` 기체 항목의 식별값과 SITL 배치값 분리, 현장용 DDS 설정, FMU(NuttX)의 식별 설정.
- `world.origin.alt`의 datum(AMSL 또는 타원체 고)을 정하지 않았다. 아래 고도 제한과 함께 정한다(상하한의 기준 높이가 datum에 달려 있다).
- 고도 제한: 미션 고도에 상하한이 없다(TAKEOFF `height_m`은 양수만, GOTO z와 offset z는 좌표 상한만, 음수 허용). TRACK_ENTITY setpoint z는 실행 중 검사가 없고 PX4 `GF_MAX_VER_DIST`도 꺼져 있다(v1.17.0 기본 0). 범위 값과 두 겹(미션 검증, PX4 geofence)을 사용자가 정한다.
- Zenoh 지상 링크 실험에서 나온 질문(근거는 아래 "지상 링크 실험 결과").
  - 중복 goal id 요청을 접수하지 않는 결정안(Phase 1에 고정한 수락 정책의 변경)을 승인할지, 구현과 그 뒤의 실측(개발 호스트에서 50회 남짓)을 Phase 2 완료 전에 할지 완료 기준과 떼어 따로 할지. 전자이면 지상의 `MissionEvent` 중복이 보일 때 `MissionEvent` 고정이 그 처리 뒤로 밀린다.
  - upstream(zenoh-plugin-ros2dds) 보고를 누가, 언제, 어느 계정으로 하는지, 프로젝트의 구성과 로그를 공개 issue에 어디까지 실을지, 기존 issue #702에 덧붙일지 새로 낼지.
  - 지상이 `MissionEvent`를 빠짐없이 받아야 하는지. 그렇다면 bridge 너머의 구독이 맺어졌음을 goal 전에 확인하는 방법을 계약에 둘지, 접수 사건의 유실을 허용하고 action을 유일한 정본으로 둘지.
  - 지상 링크가 끊긴 동안 끝난 미션의 결과를 지상이 어떻게 알아야 하는지(재연결 뒤 result를 다시 물을 수 있는 기간, 기체 쪽 결과 보관 기간, 사건의 TRANSIENT_LOCAL 재전달). `VehicleState`에 미션 상태와 마지막 결과를 싣는 안은 제안 단계다. 지금 계약은 TRANSIENT_LOCAL을 쓰지 않는다.
  - 지상에 `/clock`을 건넬지, 지상 노드(Fleet Manager, 수집기 쪽)의 시간 기준을 무엇으로 할지(실기체에서 `/clock`이 없을 때 포함). 제안 단계이고 결정하지 않았다.
  - bridge 버전(1.9.0, 1.10.x, 또는 upstream 수정판 PR #705(열림, #702와 #703을 고침)를 기다리거나 쓰는 것), 배포물(공식 Docker 이미지와 릴리스 바이너리), 고정할 곳(`docker/versions.env` 등), 1.10.x를 쓸 때 bridge 전용 CycloneDDS 설정을 둘지(lo만 또는 interface 이름을 적음), bridge를 기체 쪽 노드보다 나중에 띄우는 순서 제약을 둘지.
  - action 내부 토픽의 type hash가 bridge에서 달라지는 것을 type hash 기반 계약 검사에서 어떻게 다룰지.
  - 위 구성 문제를 Phase 3의 "Zenoh의 구성"에서 다룰지, Phase 2 항목 7(계약 고정 전에 정할 것)에서 다룰지.

main 머지 뒤 확인할 것.

- arm64 runner의 `sitl` 판정 확인: 판정 상수는 amd64에서 보정했다. arm64 runner에서는 build workflow 수동 실행(입력 `sitl`)으로 `run_sitl.sh --stack 0` 1회 통과(21 passed, 판정 구간 RTF 1.000)만 보았다. 새 key가 GHCR에 올라간 뒤 `sitl (arm64)` job의 결과(RTF, 목표 15분)와 반복 실행의 흔들림을 확인한다.

문서 정리(정형, 다음 문서 정리 때).

- Dockerfile 주석에 남은 계획 표지: `Dockerfile.px4` 36, 226행 "(S1)"은 "(스모크 embedded 단계)", `Dockerfile.ros-ws` 56행과 `Dockerfile.xrce-agent` 39행 "스모크 S0가"는 "스모크 images 단계가", `Dockerfile.sim-base` 4행 "(지금은 README의 수동 docker run, 3단계부터 gz-gui 서비스)"는 "(viz 프로필의 gz-gui 서비스)"로 바꾼다. Dockerfile을 바꾸면 이미지 key가 바뀌어 PR의 sitl이 실패하므로 주석만 따로 고치지 않고, 그 Dockerfile을 실제로 바꾸는 이미지 PR에 함께 넣는다(각 owner).
- `idsim_common/vehicle_command.hpp` 주석의 MAVLink 재송출 문장에 소스 행(v1.17.0 `COMMAND_LONG.hpp` 82-96행)을 적는다(ros2-engineer). `gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"를 고친다(sim-engineer).
- `docs/interface.md` "시간 기준" 절의 FIFO 근거 문장은 `vehicle_command` queue에서 구독자가 뒤처지면 오래된 명령을 잃는다고 적는다. 그 경우가 DISARMED 확인의 논증에 무슨 뜻인지(arm이 유실되면 기체는 DISARMED다)를 덧붙일지 정한다. 고정 절이다(architect).
- `config/px4/sitl_params.env`: `UXRCE_DDS_SYNCT` 주석의 날짜 "(2026-11-10 결정)"을 지운다. `COM_RC_IN_MODE` 항목의 "추측: ... px4-out 단계에서 실측하고, 막히면 1로 되돌린다"가 지금도 유효한지 보고 고친다(px4-engineer). 주석을 고치면 gen_compose golden의 sha256이 바뀐다.
- `docker/versions.env`의 `GZ_SIM_VERSION` 주석은 버전을 바꿀 때 "시간 기준" 절의 행 번호만 다시 보라고 한다. "좌표계" 절에도 gz-sim과 gz-math의 행 번호가 있다. gz-math 버전은 기록도 대조도 없다(devops-engineer, sim-engineer).

테스트 보강.

- 종료 단계에서 대비책 뒤 지상 DISARMED를 `DisarmConfirm`으로 세는 연결을 가르는 사례가 없다. timestamp가 전송 stamp 이하인 지상 DISARMED 셋으로는 끝나지 않음을 `GroundEndWithFallbackDisarm` 경로와 `FallbackDisarmConfirmKeptOnLandPath`의 AIR_LAND에서 단정한다. `step_mission_end` (6a) 단계의 ack 버림 줄은 주석을 달거나 지운다(ros2-engineer, test-engineer, px4-engineer).
- 공중 Offboard 진입의 DO_SET_MODE에서 첫 OFFBOARD 표본까지의 시간 D [추정]을 기존 산출물(A의 LAND, D의 Hold)의 모드 표본 간격으로 [실측]으로 바꾼다(px4-engineer).
- ACCEPTED 사건 stamp의 건전성을 노드 테스트로 덮을지 판정으로 덮을지(test-engineer, ros2-engineer).
- 성공 sitl run의 summary.md에 ULog `battery_status`, `cpuload`, `system_power` 마지막 표본 시각을 남겨 숨은 발행 정지를 센다. trace 이정표에 수신 시각을 남긴다(test-engineer, logging-engineer).
- `test_px4_topic_names.py::test_argument_checks`의 SpinThread `InvalidHandle` 경고, `tools/vehicle_arming_state.py`의 rc 2 사례 테스트(test-engineer).
- 스모크 images 단계가 `LLVM_MAJOR`, `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다(test-engineer). `ros_ws.sh`에 `versions.env` 이름 기준 존재 검사를 둘지(devops-engineer, test-engineer).
- `stack.json`의 `expect_gps.alt`는 스폰 z와 센서 높이만 더한 값이라 착지 정착(실측 약 13 mm)이 들어 있지 않다. 이 값을 쓰는 스모크 원점 판정의 고도 허용 오차가 그 차를 덮는지 확인한다(test-engineer, sim-engineer).

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

## 지상 링크 실험 결과

Zenoh bridge 확인 실험의 결론이다. 근거와 실측값은 이 절을 넣은 PR의 본문에 있다. 보고서 원본은 저장소 밖 한 PC에만 있다(`/Users/daniel/Library/Application Support/Claude/side-session-notes/local_c8ac02d7-85f5-465a-81ea-b759c83115ec/zenoh-bridge-check/`). 조건은 Apple Silicon Mac, OrbStack, 기체 1대(실제 SITL Executor)와 지상 쪽 별도 DDS 도메인, bridge 1.10.2(다른 판은 적음), 무선 지연과 손실 없음이다. 확인 수준은 [관찰], [소스], [추론], [추측], [미확인]이다. Zenoh의 구성은 정하지 않았다. 결과가 계약과 Phase 3 구성에 반영되면 이 절을 지운다.

- [관찰] `ExecuteMission`의 완료, 비행 중 cancel, 즉시 ABORTED가 지상에서 건넜다(각 1회). `VehicleState`(임시 발행자로만 봄)와 `MissionEvent`는 타입, type hash, QoS가 같고 계약 구독 QoS로 받았다.
- [관찰] allow를 기체와 지상 양쪽에 두면 지상에 계약 셋만 보이고 `/fmu/out` 토픽 하나를 이름으로 8 s 구독해도 받지 못했다. 지상에서 기체 방향의 발행과 service 호출, `/fmu/in/*`, 한쪽만 둔 조합은 시험하지 않았다. allow가 없으면 `/fmu` 구독이 되고 지상 발행이 기체 쪽에 생기며 Executor의 lifecycle과 parameter service가 지상에 보인다.
- 접수 사건 유실(`docs/interface.md`의 "계약 토픽 QoS", "MissionEvent" 절, `docs/architecture.md`의 "인터페이스 계약" 절에 닿음). [관찰] 지상에 먼저 떠 있던 다른 사건 구독자가 없을 때, `mission_event` 구독을 action client보다 먼저 같은 노드에서 만들어도 지상에서 즉시 ABORTED로 끝나는 goal 7회 중 접수 사건 0회, 종료 사건 2회를 받았다. 구독자가 5 s 먼저 떠 있으면 3회 모두 받았다. [추측] 지상 쪽 구독을 기체 쪽에 알리는 시간이 goal 왕복보다 길다. 긴 미션에서 같은지는 [미확인].
- 재연결(`docs/interface.md`의 "MissionEvent" 절, `docs/architecture.md`의 "인터페이스 계약" 절에 닿음). [관찰] bridge를 멈췄다 켠 3회 모두 지상 client가 result를 받지 못했고(종료 사건은 2회 받음), 끊긴 동안의 `VehicleState`, `MissionEvent`, feedback은 오지 않았으며 action client는 단절을 알리지 않았다. Executor의 result는 종료 약 18 s 뒤 조회되지 않았다. 보관 기간 안의 재조회와 단절 중이나 재연결 뒤의 cancel은 [미확인].
- [관찰] action 내부 토픽(`_action/feedback`, `_action/status`)의 type hash가 지상 쪽에서 기체 쪽과 달랐다. 그래도 action은 동작했다. 원인은 [추측].
- [관찰] 지상의 `/clock`은 allow에 넣어야 건너고, 없으면 `use_sim_time` true 노드의 시계가 0에 머문다. `VehicleState.header.stamp`와 `MissionEvent.stamp`는 기체 시계 값 그대로 건넌다.
- discovery. [관찰] bridge 1.10.2는 저장소 `config/cyclonedds.xml`(multicast 끔, peer 127.0.0.1) 조건에서 자기보다 늦게 뜬 DDS 참가자를 서로 찾지 못한다(각 1회). 원인은 [소스]와 [관찰]로 본 CycloneDDS 11.0.1의 SPDP 검사로 보이고 bridge의 interface 선택과 어긋난다(늦게 뜬 노드의 SPDP가 버려지는 순간은 못 봄, 나머지 [추론]). bridge 전용 DDS 설정에 interface로 lo만 또는 eth0와 lo를 주면 해소된다(각 1-2회, 이름 `eth0`는 호스트마다 다를 수 있음). 1.9.0(CycloneDDS 0.11.0)은 저장소 xml 그대로 찾는다.
- Executor 종료. [관찰] 기체 쪽 bridge의 action route가 다시 만들어진 뒤(Executor 재시작, 또는 Executor가 없는 동안 지상 client가 공지됐다 물러난 뒤 Executor가 뜸) 오는 같은 goal 요청이 같은 요청 id로 두 번 건너가고, rclcpp_action이 예외를 던져 Executor 프로세스가 끝났다(4회 중 4회, 앞선 6회도 같음, route를 한 번만 만든 8회는 정상). 관찰은 1.10.2(저장소 DDS 설정 그대로인 조합과 bridge 전용 DDS 설정에 eth0와 lo를 준 조합)와 1.9.0(저장소 DDS 설정, 1회)에서이고, lo만 준 조합은 discovery만 확인했다. 예외는 [소스]상 노드 코드가 잡을 수 없는 위치에서 난다. 비행 중이면 Offboard 손실 failsafe로 Land에 간다(문서와 파라미터 확인, 실측 아님).
- Executor 종료의 결정안(architect, 사용자 승인 대기, 문서와 코드에 반영하지 않음). 이미 접수한 goal id로 다시 온 요청을 접수하지 않는다(rejected 응답). 이것은 고정된 수락 정책의 변경이라 변경 절차(`docs/architecture.md`)를 탄다. 구현 뒤 실측(route가 다시 만들어지는 두 경로 각 10회, 실행 중 지상 client 재기동 각 5회를 1.10.2와 1.9.0에서)에서 죽는 회차가 있으면 결정을 다시 연다. 이 방어를 넣은 뒤 지상이 받는 응답(accepted 또는 rejected)과, 지상이 받는 `MissionEvent`가 goal마다 접수 하나와 종료 하나인지는 [미확인](저장소 DDS 설정 조합 2회에서 같은 goal id의 접수 사건이 두 번 왔다).
- upstream: bridge 저장소의 열린 issue #702(같은 이름 노드 재시작 뒤 route 비활성)와 #703(subscriber 반복 생성과 삭제 뒤 DDS 불안정)은 1.9.0에서 보고됐고, 둘을 고치는 PR #705는 열려 있다. Executor 재시작 경로는 #702와 닿고 지상 client 공지 경로가 #705로 고쳐지는지는 [미확인].

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
