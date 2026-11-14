# idsim 진행 상황

에이전트와 작업자가 세션을 시작할 때 지금 어디에 있는지 파악하기 위한 파일이다. 지금 유효한 것만 적는다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`, 진행 중인 단계의 계약은 `docs-for-agent/plan-*/decisions.md`에 있다. 무엇이 언제 왜 바뀌었는지는 여기에 적지 않고 git(커밋 메시지, PR 본문)에서 본다.

## 현재 상태

| Phase | 상태 |
| --- | --- |
| 1a | 완료. 1a 완료 범위의 계약은 `docs/interface.md`에 고정되어 있다 |
| 1b | 구현 중. 계획은 `docs-for-agent/plan-1b-mission-target/README.md`, 계약은 같은 디렉터리 `decisions.md`. B1, B2, B3(원점과 월드: 생성기 판 5, fleet schema 2, 원점은 월드 SDF로만), B4, B5(RTL과 실패 폴백 SITL 파라미터 일곱), B6(표적 어댑터 `targets` 서비스, Actor 생성, 궤적 상한), B7(정답 pose `sim-oracle`, `sim-topic` lint), B8, B8b(1a 칸 목록 미덮임 0), B9 snapshot 헤더(쟁점 12 항목, px4 어댑터 대응과 `px4/frame_port`. 상태기 동작 무변경) 반영됨 |
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
| 6 이륙-호버-착륙 노드와 통합 테스트 | 완료. 계획은 `docs-for-agent/plan-1a-6-idsim-mission/README.md`, 계약은 같은 디렉터리 `decisions.md`. P0-P5 완료(P4는 PR #36. 로컬 `run_sitl.sh --repeat 10` 10/10, CI `sitl` 첫 실행 통과. P5는 PR #38). 사용자가 QGC와 Gazebo GUI로 같은 비행을 확인했다. Executor의 feedback stamp는 tick 입력 시각이고 시나리오 A의 LOITER 유지 판정에 시계 양자 허용이 없다 |
| 7 `docs/interface.md` | 완료. PX4 인터페이스와 `idsim_interfaces` 계약, 정의별 고정 시점 표 |

환경.

- 저장소 원격은 github.com/danielhongwoo/idsim, 이미지 레지스트리는 ghcr.io/danielhongwoo/idsim이다. GHCR 패키지 5개는 Public이고, 이미지 5종의 현재 key와 `buildcache` 태그가 익명으로 조회된다.
- CI의 `lint`와 `unit`은 `pull_request`와 `push: main`에서 돈다. PR이 없는 브랜치 push에는 CI가 돌지 않는다. `build`는 PR에서 빌드만 하고 main에서만 GHCR에 올린다.
- 개발 호스트는 x86_64 Ubuntu 24.04 VM(16 vCPU, 31GB, NVIDIA 없음, GNOME Wayland)이다. 이 호스트에서 archive.ubuntu.com이 응답하지 않는 날이 있어 이미지 빌드의 apt 미러 기본값이 kr 미러다.
- 스모크와 스택의 실행 기록 `artifacts/`는 git에 추적되지 않으므로 다른 PC로 옮겨지지 않는다. 판정에 필요한 golden은 `tests/fixtures/`에 추적된다.

## 운영 규칙

담당자 구성과 모델 선택의 기본은 `CLAUDE.md`에 있다. 아래는 그 밖에 지금 적용되는 규칙이다.

- 문서에는 지금 유효한 것만 둔다. 이력(누가 언제 무엇을 왜 바꿨는지, 실측 run, 검토 경과)은 커밋 메시지와 PR 본문에 적는다(사용자 결정).
- px4-engineer의 모델 선택 예외는 `CLAUDE.md` 모델 선택 규칙의 "사용자 예외"를 따른다(읽기 전용 확인과 정형 작업은 sonnet, 안전장치로 중단된 기본 모델 호출은 sonnet으로 다시 부른다).
- 그림은 계층으로 나눈다. 개요 그림 하나가 묶음과 주요 경로만 보이고 상세 그림이 개요의 상자를 하나씩 펼치며, 상세 그림의 도입 문장에 어느 상자를 펼친 것인지 적는다. 같은 내용을 두 그림에 그리지 않는다. 그림 하나는 node 8개 이하, edge 10개 이하, subgraph 중첩 1단, node label 두 줄 이하(이름과 짧은 구절 하나), edge label은 프로토콜이나 내용의 이름 하나(15자 이하)이고, 넘으면 그림을 나눈다. 포트 식, 환경변수, 마운트 경로, 명령줄 같은 세부는 label에 넣지 않고 그림 아래 표나 문장에 둔다(사용자 결정).
- 실험용 스택 번호는 px4 5, ros2 6, test 7, devops 8, sim 9이다. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.
- 관련 owner의 승인 없이 머지하지 않는다. `idsim_mission`의 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자다(`file-ownership.md`).
- 1a는 대표 시나리오(B, C, A, D, T)의 통과를 기준으로 개발한다. 경계 상황은 실측 증명 대신 보수적 기본 동작으로 덮고 계약 문서에 "미확인"으로 적는다. 새 실측은 관찰된 실패나 이상 동작의 원인을 재현할 때만 하고, 문서 분량과 실행 산출물과 기록 항목은 최소로 둔다(U6).

지금 유효한 사용자 결정.

- U1: 공중 취소 시나리오 D와 `[LAND]` 한 항목 미션은 1a 필수다.
- U2: `sitl` job은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외)와 main push에서 돈다. `lint`와 `unit`의 trigger도 `pull_request`와 `push: main`이다.
- U3: 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작은 1b에서 정한다. 1a 노드는 그런 미션을 INVALID_MISSION으로 거부한다.
- U4: replay job의 trigger는 replay job을 만드는 Phase 2에서 정한다.
- U5: P4는 core 변경을 먼저 머지한다. `decisions.md`의 P4 머지 조건(필수 재실측 (2), (3), (5)와 두 부류의 ARMED 표본 기준)은 `tools/sim_stack.sh up`이 Executor를 띄우게 되는 P4 생성기와 통합 PR에 적용한다.
- U6: 1a는 대표 시나리오(B, C, A, D, T)의 통과(로컬 3회 연속, CI `sitl`, 육안 확인)를 기준으로 한다. 경계 상황은 보수적 기본 동작과 "미확인" 표기로 덮고, 새 실측은 관찰된 문제의 재현용으로만 하며, 재실측 (1), (4), (6), (7), (8)은 하지 않는다. 산출물은 최소로 둔다.
- U7: 1b 범위에서 반복 이륙(첫 항목이 아닌 TAKEOFF)은 뺀다. Executor는 1b에서도 거부한다.
- U8: `COM_LOW_BAT_ACT`를 계약 SITL 파라미터 표에 넣어 2(Land)로 고정한다.
- U9: `RTL_RETURN_ALT`는 미션 고도에 맞춰 정한다(1b는 순항 5 m에 10 m).
- U10: 표적은 "스크립트 궤적을 따르는 점 표적"이다. 표적 생산자는 교체 가능하며 Gazebo 기반 생산자는 확장 항목이다. `docs/architecture.md` 범위 문구를 이에 맞춘다.
- U11: CI `sitl` 목표 15분. 1b 비행 시나리오를 모두 PR CI에 두고, 넘으면 U15 순서로 줄인다.
- U12: Gazebo 정답 pose(`/sim/`)를 SITL MCAP 기록물에 넣는다(Phase 2부터 효과).
- U13: roadmap 1b 목표(YAML 미션 하나로 이륙 -> 순회 -> 표적 접근 -> 복귀, 착륙)를 그대로 덮는 합친 미션 시나리오(F4)를 둔다. F1-F3은 경계 상황 검증용으로 남긴다. CI 15분을 넘을 때의 조정은 U15를 따른다.
- U14: 1b waypoint 판정 반경은 1 m를 유지한다. 시험 미션의 `acceptance_radius_m`은 `1 m - b` 이하로 둔다.
- U15: CI `sitl`이 15분을 넘으면 겹치는 비행 구간 -> waypoint 수 -> Hold 시간 순으로 줄인다. F2의 공중 종료와 F3의 공중 시작은 빼지 않는다.
- U16: `docs-for-agent/file-ownership.md`의 소유자는 architect다.
- 저장소 라이선스는 Apache-2.0이다. 새 소스와 CMake 파일에 머리말을 넣고 `ament_copyright`와 cpplint `legal/copyright` 검사를 켠 채로 둔다.
- 이미지 빌드의 apt 미러 기본값은 kr 미러(`docker/versions.env`의 `UBUNTU_APT_MIRROR`)이고 CI는 우분투 기본 미러를 쓴다.
- ros-ws 이미지에 clang-tidy와 clang-format을 그대로 둔다. 별도 도구 이미지로 빼지 않는다.
- `tools/qgc.sh`에 설정을 되돌리는 옵션을 두지 않는다. 기본 포트로 돌리려면 `--stack 0`을 쓴다.

## 다음 작업

1. 1b: README 진행 순서대로 B9, B12를 진행한다. B4(`idsim_common`의 원점 이동 변환, `TargetId`, 상태 QoS, `position_setpoint` 속도 인자), B5(SITL 파라미터 일곱), B6(표적 어댑터, Actor 생성, 궤적 상한), B7(정답 pose, `/sim/` lint), B8(전이 관측 계측, 1a 칸 목록), B8b(1a 칸 목록 covered 218, impossible 69, uncovered 0. 덮음 테스트가 uncovered 칸을 거부)는 끝났다. B9 snapshot 헤더는 반영됐고, 다음은 B9 상태기 PR 여섯(S1-S6)이다. 순서와 범위, B9와 B10의 경계는 `decisions.md` 쟁점 12에 있고 S1(지상 arm 진입의 arm 순서 불변식, 첫 커밋은 B8b에서 넘어온 테스트 수정 둘)부터 한다. PR마다 px4-engineer의 칸 명세 표가 먼저이고, 칸 목록 diff를 내고 새 칸을 같은 PR에서 덮는다. goal 접수가 받는 미션은 B9 동안 1a 그대로이고, 노드는 S5부터 값 없는 임시 port와 빈 `Snapshot.targets`를 넘긴다. 진짜 `Px4FramePort`(`to_local_position_input` 채택, 비행 중 `ref_timestamp_us` 변경 WARN, `world.origin` 전달), 표적 구독(`Snapshot.targets`는 goal 접수 때 비우고 노드 테스트에 사례를 둔다), goal 접수 제한의 제거는 B10이고, 쟁점 12 승인 조건 (2)의 실제 충족은 B10 검토 때 본다. 칸 명세 때 px4-engineer가 확인할 [추정]: 공중 Offboard 진입에서 첫 OFFBOARD 표본 뒤 재전송 중단의 근거(쟁점 7, S4), float 범위 안의 매우 큰 setpoint에서 PX4 위치 제어의 동작(쟁점 8, S5). B12(M4)는 궤적 길이 합 상한 월드(표적 4 x 600 s)의 GUI CPU, 서버 RSS, RTF도 기록한다. `target_id` 사례 표의 단일 출처(test-engineer 제안 위치 `idsim_interfaces/test/cases/`, architect)는 `tests/support`에 이름 조립이 들어올 때 정한다. B11 판정 쪽에서 챙길 것(B7 검토, test-engineer): `tests/support`에 `/sim/<vehicle_id>/pose` 조립 순수 함수와 `sim_oracle.py`의 `ORACLE_TOPIC_CASES`, `ORACLE_TOPIC_INVALID`와 같은 사례 표(import로 공유하지 않음), 정답 pose 구독은 첫 `mission_event` 전에 discovery와 `sim-oracle` 준비를 확인하고 depth를 크게(발행은 RELIABLE, VOLATILE, KEEP_LAST 10), `ORACLE_STALE`은 `t_f` 뒤 표본을 `/clock`이 `t_f + 0.1 s`를 지날 때까지 기다린 뒤 판정, 정답 pose QoS를 구독 QoS와 짝으로 `tests/support` 머리말에 적는다. B11 표적 소실 시험은 같은 `targets` 컨테이너를 stop/start하면 컨테이너 레이어의 `/tmp/idsim/targets_ready`가 남아 healthcheck가 새 노드 기동 전에 통과할 수 있다. `sim-oracle`도 `docker restart`하면 옛 `oracle_ready`가 0.5-1 s 남는 것을 B7 실측에서 관측했다([실측]). 대응은 `/tmp/idsim`을 tmpfs로 두는 것(uid 지정이 필요하다) 또는 재시작 뒤 stamp로 판정하는 것이다.

## 미해결 사항

1a 6단계.

- CI `sitl`(1a 시나리오)이 간헐적으로 실패한다. 관측한 두 종류: 시나리오 D의 "D 고도 도달" `TIMEOUT_SIM`(60 s, #43, #49 머지 뒤 main과 #54 첫 실행), 이정표 순서 위반 "result가 disarmed보다 앞"(4 ms 차, #50 머지 뒤 main). #54는 같은 commit의 재실행에서 통과했다. main은 #49, #50 머지 뒤 연속으로 실패했고 #51 머지의 실행부터 통과했다. 장애 분석(test-engineer, px4-engineer)을 할지는 사용자가 정한다.
- CI `sitl` job의 기록은 첫 1회뿐이다(PR #36: 전체 5분 43초, 이미지 pull 약 3분 20초, 스택 올리기부터 정리까지 약 2분 13초, runner Docker Engine 28.0.4). 실패 때 `artifacts/runs/`가 job artifact로 올라가는지는 아직 보지 못했다. 판정 상수의 재검토(쟁점 9)는 CI 기록이 쌓이면 한다.
- 스모크 images 단계(`tests/smoke/run_smoke.sh`의 check_s0)가 `LLVM_MAJOR`와 `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다. `tools/ros_ws.sh`의 대조는 이미지에 있는 ENV만 돌아서 그 ENV가 없는 옛 ros-ws 이미지가 통과한다. 옛 `:local` 이미지로 `sim_stack.sh up --viz`를 하면 foxglove만 죽는다. images 단계에 넣는다(test-engineer). `ros_ws.sh`에 `versions.env`의 이름 기준 존재 검사를 둘지는 devops-engineer와 test-engineer가 정한다.
- foxglove_bridge의 판은 `FOXGLOVE_BRIDGE_VERSION` 접두 단정까지만 고정된다. ROS sync로 새 판이 오면 ros-ws key가 바뀌는 PR의 빌드가 실패한다(의도한 동작). 같은 판 안의 revision과 의존 패키지는 고정되지 않는다.
- P5 완료 기준 가운데 setpoint와 `vehicle_local_position`을 Lichtblick의 같은 플롯에 놓는 것은 확인하지 않았다(U6에 따라 6단계를 막지 않는다). 연결, 토픽 목록, Plot 갱신은 확인했다.
- PX4 버전을 올리면 "ULog의 `vehicle_command` `timestamp`가 측정기의 stamp와 같다"와 "ack 기록 순서가 처리 순서와 같다"를 다시 확인한다(px4-engineer).
- 실행하지 않고 [미확인]으로 둔 것: `ops-N`의 goal 실행 중 stop에서 종료 사건이 구독자에게 오는지, `vehicle.id` 누락에서 unhealthy까지의 시간(추정 약 54 s, 최악 70 s). 관찰된 문제가 있을 때만 잰다(U6).

빌드와 CI.

- `sitl.yml`은 GHCR에서 이미지 key로 pull하는데, PR에서는 새 key가 아직 없고 main push에서는 `build`의 publish와 동시에 돌아 이미지 key가 바뀌는 PR은 PR과 머지 직후 main 양쪽에서 pull 단계가 실패한다. 지금은 로컬 `tests/sitl/run_sitl.sh`로 대신하고 publish 뒤 main에서 `sitl`을 다시 돌린다. 대안: `sitl`을 build 완료의 `workflow_run`으로 묶기, key가 없으면 실패 원인을 명시해 보고하기(조용한 skip은 쓰지 않는다). devops-engineer와 architect가 정한다.
- 같은 key로 두 번째 main build가 돌 때 이미지 5종이 모두 SKIP되는지 확인한다(devops-engineer).
- 비결정 빌드 요소: ros.key와 gazebo.gpg는 URL이 고정되어 있지 않다. 받은 key의 지문은 `ROS_APT_KEY_FPR`, `GZ_APT_KEY_FPR`와 대조한다. apt 저장소 상태, pip 인덱스, 대조하지 않는 apt 패키지 판은 이미지 key에 들어가지 않는다(`docs/architecture.md` 이미지 key 문단).
- apt 미러: 지정 미러가 막히면 콜드 빌드가 실패한다. apt `Acquire::Retries` 미적용. CI에서는 Canonical 노드의 동기화 시차로 apt 단계가 간헐적으로 실패할 수 있다(대안: apt 단계 재시도, CI 미러 변경).
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다(`src/`의 소스가 include하는 헤더만 검사된다). 헤더 전용 검사를 둘지, `test/`를 tidy 대상에 넣을지 정한다(ros2-engineer, devops-engineer).
- `tools/ros_ws.sh tidy`는 대상이 0개이면 PASS-NO-TARGETS로 통과한다. `ci`에서는 경고나 실패로 바꿀지 검토한다(devops-engineer).
- 이미지 ENV와 `versions.env`의 대조는 스모크 images 단계와 `tools/ros_ws.sh`에서만 일어난다. 다른 스모크 단계를 단독 실행하면 대조가 없다.
- compose healthcheck `start_interval`의 Docker 하한은 실측하지 않았다(Docker 29.1.3, Compose 2.40.3에서 동작). `check_host.sh`는 Engine 25 미만이면 WARN만 낸다.
- `tools/check_host.sh`의 셸 단위 테스트(가짜 ss, df, docker)는 두지 않았다(test-engineer 판단).

시뮬레이션과 화면 도구.

- `idsim_common/vehicle_command.hpp` 주석의 "`from_external=false`면 MAVLink로 재송출"에 소스 행(PX4 v1.17.0 `COMMAND_LONG.hpp` 82-96행, 조건은 90행)을 다음 수정 때 적는다(ros2-engineer).
- QGC가 기체에 연결된 상태에서 `qgc.sh`의 TERM 종료 동작은 실측하지 않았다.
- Gazebo GUI 깜빡임(VMware 3D 가속을 켠 상태). `QSG_RENDER_LOOP=basic`과 `vblank_mode=1`의 효과는 확인되지 않았다. 다음 후보: SceneBroadcaster `state_hertz` 낮추기, `--render-engine-gui ogre`.
- `ros_ws/src/idsim_sim/scripts/gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"는 표현이 부정확하다(sim-engineer).
- `qgc.sh`의 sha256 불일치 시 종료 코드 1 경로는 실행으로 확인하지 않았다.
- 실측하지 않은 것: `GZ_IP=127.0.0.1`을 뺐을 때의 gz-transport 디스커버리, GPS 잡음의 출처, bridge healthcheck의 `ROS_LOG_DIR=/tmp/hc`가 run 디렉터리에 로그를 남기지 않는지, 에이전트의 Fast DDS 멀티캐스트가 같은 LAN의 다른 호스트와 섞이는지, MAVLink bind에 실패한 PX4의 동작, passwd에 없는 uid 1001로 지금 스택 전체(runner, `ops-N`, `targets`)가 도는지(`sim-oracle`은 sim-base 이미지에서 uid 1001로 import, 모델 해석, 구독, 표시 파일, 발행까지 B7에서 확인했다).
- 이 호스트의 포트 5900과 8090은 다른 프로젝트가 쓴다. VNC를 도입하면 피한다.

Phase 2와 3 전에 정할 것.

- Phase 2 착수 전 설계 토론(ops-service-engineer, logging-engineer, architect): `VehicleState`에서 ROS 시각이 역행할 때의 레지스트리 처리(replay 일시정지와 배속 포함), 소비자 미수신 timeout의 배수, stamp 단조성 규칙, WebSocket JSON의 중첩과 enum 표현, gRPC `StreamMissionEvents`와 ROS `MissionEvent`의 관계(ops 권고는 별도 메시지), 기록기의 구독 확인 순서.
- Phase 3: Fleet 재시작 복구 경로. 전체 취소 뒤에는 result를 받을 handle이 없으므로 기체 상태로만 확인한다. 이탈 기체 goal의 재배분은 한 번(Fleet 정책).

- replay job의 trigger(U4). `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 그때 고친다.
- ULog가 `compose down`에서 정상 종료되는지 확인한다. 기록량은 약 285 KiB/s, 기체당 약 1 GB/h다(logging-engineer, Phase 2 전).
- Phase 3에서 주기 하한 계약이 필요한 토픽 목록(px4-engineer).
- lockstep의 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지)은 실측하지 않았다. Phase 3 CPU 포화 해석의 전제다.

## 새 개발 PC에서 시작할 때

1. 저장소를 받는다(`git clone https://github.com/danielhongwoo/idsim.git`). 작업은 main에서 브랜치를 만들어 한다. 열린 브랜치와 PR은 `gh pr list`로 본다.
2. 호스트 조건과 환경 구성 순서는 저장소 루트 `README.md`의 "호스트 조건"과 "빠른 시작"을 따른다(`tools/check_host.sh`, 이미지, 스모크 images, px4-out, px4-in, clock). 이어서 `tools/ci/lint.sh all`과 `tools/ros_ws.sh ci`가 통과해야 한다.
3. 이미지는 로컬 빌드(`python3 tools/ci/build_images.py --mode load`, 콜드 약 22분) 대신 GHCR에서 받아 쓸 수 있다. `python3 tools/ci/build_images.py --mode pull`이 받아서 태그한다. key는 `python3 tools/ci/image_keys.py`가 보여 주고, main build가 그 key를 올린 뒤에만 받을 수 있다.
4. 같은 호스트에 다른 ROS 2 스택, Gazebo, compose 프로젝트가 있는지 먼저 본다(`docker ps`, `docker compose ls`). 겹치면 스택 번호 k(`--stack k` 또는 `IDSIM_STACK_INDEX`)를 바꾼다.
5. PR을 올리려면 gh(GitHub CLI)에 로그인한다(`gh auth login`). `gh pr edit`는 이 저장소에서 GraphQL Projects(classic) 오류로 실패하므로 PR 본문은 `gh api -X PATCH repos/danielhongwoo/idsim/pulls/<번호> -F body=@<파일>`로 고친다.
6. 저장소 밖에 있던 것.
   - 사용자 전역 규칙 `~/.claude/CLAUDE.md`: 커밋 메시지와 PR 본문에 Co-Authored-By 같은 공동 저자 줄이나 생성 도구 표기를 넣지 않는다. 새 PC에도 같은 파일을 둔다.
   - Claude Code 메모리(`~/.claude/projects/<저장소>/memory/`)는 옮겨지지 않는다. 거기 있던 규칙(공동 저자 줄 금지, 기술 용어 영문 표기, 문서는 현재 상태만, px4-engineer의 sonnet 예외)은 모두 `CLAUDE.md`와 이 파일의 "운영 규칙"에 있다.
   - 담당자 검토 보고는 저장소 파일로 두지 않는다. 지난 검토 내용은 PR 본문에 있다(P3은 PR #27).
   - 로컬 `artifacts/`(스모크와 실측 기록)는 옮겨지지 않는다. 필요한 값은 PR 본문과 `tests/fixtures/`에 있다.

## 갱신 규칙

- 이 파일에는 지금 유효한 것만 둔다. 작업 단위가 끝나면 "현재 상태"의 해당 칸을 고쳐 쓰고, 끝난 "다음 작업"과 닫힌 "미해결 사항"은 지운다. 완료 표시나 날짜를 붙여 남기지 않는다.
- 결정은 이 파일에 기록으로 쌓지 않는다. 설계 규칙이면 `docs/architecture.md`(환경 스모크는 `docs/smoke-test.md`, 계약 문장은 `docs/interface.md`)를, 진행 중인 단계의 계약이면 그 단계의 `decisions.md`를 현재형으로 고치고, 근거와 경위는 그 변경의 커밋 메시지와 PR 본문에 적는다.
- 사용자 결정과 담당자 운용 규칙처럼 설계 문서에 자리가 없는 규칙은 "운영 규칙"에 현재형으로 적는다. 바뀌면 고쳐 쓰고 옛 문장을 남기지 않는다.
- 사용자만 정할 수 있는 사항(범위, 언어 선택, 비용)은 "미해결 사항"의 첫 묶음에 올린다.
- 실측값, run id, 검토 경과는 PR 본문에 적는다. 설계 문서에는 규칙의 근거가 되는 사실만 남긴다.
