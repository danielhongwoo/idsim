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
| 6 이륙-호버-착륙 노드와 통합 테스트 | 진행 중. 계획은 `docs-for-agent/plan-1a-6-idsim-mission/README.md`, 계약은 같은 디렉터리 `decisions.md`. P0(CI trigger), P1(ros-ws 이미지의 foxglove_bridge), P2(`idsim_common` 추가), P3a(런타임 확인)는 완료. P3(`idsim_mission` 패키지)도 완료(승인 내역과 넘기는 항목은 PR #27 본문). `decisions.md`는 지금 유효한 계약만 담은 한 판이고 P4 착수 전 설계 토론의 결정(P6의 ARMED 관측 뒤 감시, 정리의 상한)이 들어 있다. P4(그 결정의 core 구현, 생성기, 통합 테스트, `sitl` job, 문서)와 P5(viz)는 시작 전 |
| 7 `docs/interface.md` | 시작 전 |

환경.

- 저장소 원격은 github.com/danielhongwoo/idsim, 이미지 레지스트리는 ghcr.io/danielhongwoo/idsim이다. 이미지 5종의 현재 key는 익명으로 조회된다.
- CI의 `lint`와 `unit`은 `pull_request`와 `push: main`에서 돈다. PR이 없는 브랜치 push에는 CI가 돌지 않는다. `build`는 PR에서 빌드만 하고 main에서만 GHCR에 올린다.
- 개발 호스트는 x86_64 Ubuntu 24.04 VM(16 vCPU, 31GB, NVIDIA 없음, GNOME Wayland)이다. 이 호스트에서 archive.ubuntu.com이 응답하지 않는 날이 있어 이미지 빌드의 apt 미러 기본값이 kr 미러다.
- 스모크와 스택의 실행 기록 `artifacts/`는 git에 추적되지 않으므로 다른 PC로 옮겨지지 않는다. 판정에 필요한 golden은 `tests/fixtures/`에 추적된다.

## 운영 규칙

담당자 구성과 모델 선택의 기본은 `CLAUDE.md`에 있다. 아래는 그 밖에 지금 적용되는 규칙이다.

- 문서에는 지금 유효한 것만 둔다. 이력(누가 언제 무엇을 왜 바꿨는지, 실측 run, 검토 경과)은 커밋 메시지와 PR 본문에 적는다(사용자 결정).
- px4-engineer의 모델 선택 예외는 `CLAUDE.md` 모델 선택 규칙의 "사용자 예외"를 따른다(읽기 전용 확인과 정형 작업은 sonnet, 안전장치로 중단된 기본 모델 호출은 sonnet으로 다시 부른다).
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

1. P4의 선행 측정: 측정 스크립트 `tests/sitl/measure/`(`run_measure.sh`, 사용법은 같은 디렉터리 `README.md`)가 있고 절차는 px4-engineer가 승인했다. 남은 일은 px4-engineer의 본 측정이다. 재실측 (2), (3), (5)와 `armed` 항목(PX4 직접 명령) 10회이며 P4 머지 조건이다. 통과 판정 범위와 종료 코드의 뜻은 `plan-1a-6-idsim-mission/decisions.md`의 "P4의 실측 기록" 절과 넘김 목록 px4-engineer 행에 있다. item2는 종료 코드 0이 나오지 않고 (2)의 통과는 architect가 판정한다. ARMED 표본 기준은 Executor 경유(시나리오 A) 부류도 따로 10회 이상 통과해야 P4 머지 조건이 채워지며, 그 기록은 P4 시나리오가 `tests/support/px4_raw.py`, `measure_judge.py`, `measure_check.py`를 써서 남긴다.
2. P4의 core 변경(ros2-engineer 구현, px4-engineer 필수 승인. `decisions.md` 쟁점 3 M6과 쟁점 4, 담당자별 구현 지시). P6에서 ARMED를 처음 관측한 뒤의 감시 표 적용과 arm 재전송 중단, 감시 표로 끝낼 때의 disarm 1회, ARMED 관측 뒤의 확인 기한, 정리의 상한(`hold_confirm_timeout + 3 x mode_confirm_timeout`, 기본 12 s)과 상한 tick의 동작, Hold 실패 뒤 공중 재진입은 Land 경로, 단위 테스트, 패키지 `README.md` 갱신. `ExecuteMission.action`의 의미 주석은 이미 이 결정에 맞춰져 있다(golden 무변경).
3. P4 생성기와 통합(devops-engineer, test-engineer, architect의 문서 반영). `ops-N` 서비스, params와 `stack.json` key, `tests/sitl/`, CI `sitl` job, `build_images.py --mode pull`. 함께 할 것: `idsim_mission/config/ops.example.yaml`의 손으로 쓴 식별자를 지우거나 install에서 빼기, 노드 이름 기본값 `mission_executor`와 생성기의 대조, CI 첫 몇 회의 노드 테스트(`test_executor_node`) 소요 기록(벽시계 1 ms당 sim 2 ms라 runner가 느리면 LINK_LOST로 흔들릴 수 있다. 흔들리면 재시도나 상한 늘리기로 덮지 않는다).
4. P5 viz(devops-engineer). `foxglove`와 `lichtblick` 서비스, 브라우저 실접속 확인.
5. 6단계 마무리: 통합 테스트 로컬 3회 연속 통과, CI `sitl` 통과, 사용자가 QGC와 Gazebo GUI로 같은 비행을 확인.
6. 1a 7단계 `docs/interface.md`. ros2-engineer가 `tools/to_interface.py`로 초안을 내고 architect가 확정한다. 계약 고정 전에 px4-engineer의 나머지 필수 재실측이 끝나야 한다. 6단계에서 넘어온 것은 `plan-1a-6-idsim-mission/decisions.md` 넘김 목록의 architect 7단계 행에 있다(reason별 ABORTED 뒤 기체 상태 표, 정리의 상한, 정리 중 failsafe인 기체에 Hold를 보낼지, 아무것도 하지 않은 goal의 취소 동작 재검토).
7. CI 후속 PR. `Dockerfile.px4`의 pip 고정과 `PX4_OPTICAL_FLOW_REF` 반영, `ls | grep` 정리(px4-engineer). `Dockerfile.sim-base`의 `GZ_APT_KEY_FPR` 검증(sim-engineer). ruff 임시 예외 정리(test-engineer). 설계 문서의 이미지 key 재료 설명 갱신(architect. `UBUNTU_APT_MIRROR`를 key에서 뺀 것이 "같은 key는 같은 바이트"의 예외라는 점 포함). `image_keys.py`가 bake 블록의 tags와 공백까지 해시하는 것 정리(devops-engineer).

## 미해결 사항

사용자 결정이나 확인이 필요한 항목.

- GHCR 패키지 5개와 buildcache가 Public인지 설정 화면에서 확인한다. 비공개면 포크 PR과 익명 조회가 거부되어 매번 전체를 다시 빌드한다.

1a 6단계.

- 감시 표의 행 순위는 필수 재실측 (4) 전까지 잠정이다. 필수 재실측 여덟 항목은 `plan-1a-6-idsim-mission/decisions.md` 넘김 목록에 있다.
- `idsim_mission` 패키지의 소스 주석 일부가 `decisions.md`의 없어진 절 이름("px4-engineer 승인 반영", "담당자별 구현 지시", "C4", "C5" 등)을 가리킨다. P4의 core 변경 때 맞춘다(ros2-engineer. 목록은 `decisions.md` 담당자별 구현 지시).
- `ExecuteMission.action`의 주석 가운데 정리의 상한, 첫 항목 전의 FAILSAFE 등, EXTERNAL_DISARM의 넓힌 범위는 P4의 core 변경이 들어가기 전까지 구현과 다르다.
- 스모크 images 단계(`tests/smoke/run_smoke.sh`의 check_s0)가 `LLVM_MAJOR`와 `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다. `tools/ros_ws.sh`의 대조는 이미지에 있는 ENV만 돌아서 그 ENV가 없는 옛 ros-ws 이미지가 통과한다. 옛 `:local` 이미지로 `sim_stack.sh up --viz`를 하면 foxglove만 죽는다. P4 또는 P5 전에 images 단계에 넣는다(test-engineer). `ros_ws.sh`에 `versions.env`의 이름 기준 존재 검사를 둘지는 devops-engineer와 test-engineer가 정한다.
- foxglove_bridge의 판은 `FOXGLOVE_BRIDGE_VERSION` 접두 단정까지만 고정된다. ROS sync로 새 판이 오면 ros-ws key가 바뀌는 PR의 빌드가 실패한다(의도한 동작). 같은 판 안의 revision과 의존 패키지는 고정되지 않는다.
- Lichtblick 공식 이미지(1.30.0. 이미지 label의 2.5.2는 베이스 Caddy의 버전)가 두 서브프로토콜을 제시하는 것만 확인했다. foxglove_bridge와의 브라우저 실접속은 P5에서 확인한다.
- `px4-api` 검사는 C++과 `.py`만 본다. params와 remap yaml이 생기는 P4에서 범위를 넓힌다.
- PX4 timestamp와 `/clock`이 같은 축이라는 것의 회귀 판정은 P4의 SITL fixture 사전조건(`/clock` 정렬)과 시나리오 T가 생길 때까지 없다. 스모크 clock 단계에는 넣지 않는다(`decisions.md` 쟁점 9).
- `artifacts/`를 CI job 아티팩트로 올리는 것은 `sitl` job을 만드는 P4에서 확인한다.

1a 7단계(`docs/interface.md`)에 적을 것.

- `COM_RC_IN_MODE`가 4라 QGC 수동 모드와 가상 조이스틱은 쓸 수 없다(ros2-engineer 초안, px4-engineer 확인).
- QGC 하나는 한 번에 한 스택만 본다는 제약, 포트와 식별자 표, SIH 변형의 `PX4_HOME_*` 주의.
- 4단계(`idsim_common`) 계약: QoS 표(reliability와 durability는 계약, depth는 계약 밖), 좌표계, timestamp 기준(`UXRCE_DDS_SYNCT=0`, `Px4Timestamp` 규칙, `timesync_status`는 SYNCT=0에서 DDS timesync 데이터가 없다), sysid 대조 규칙, 공개 /fmu/in 목록과 허용 절차(`docs/architecture.md`), "발행 차단은 실수 방지 수준이며 보안 경계가 아니다".

빌드와 CI.

- 같은 key로 두 번째 main build가 돌 때 이미지 5종이 모두 SKIP되는지 확인한다(devops-engineer).
- 비결정 빌드 요소: PX4-OpticalFlow master(px4 builder, 결과물은 버려짐), empy 외 pip 패키지 미고정, ros.key와 gazebo.gpg URL 미고정(다음 작업 7).
- apt 미러: 지정 미러가 막히면 콜드 빌드가 실패한다. apt `Acquire::Retries` 미적용. CI에서는 Canonical 노드의 동기화 시차로 apt 단계가 간헐적으로 실패할 수 있다(대안: apt 단계 재시도, CI 미러 변경). GHCR 이미지를 받아 태그하는 `build_images.py --mode pull`은 P4에서 만든다.
- `docker/Dockerfile.px4` 132행 주석이 없는 문서 이름 `smoke-test-phase1a.md`를 가리킨다. 주석만 고쳐도 px4 이미지 key가 바뀌므로 다음에 그 파일을 바꿀 때 `smoke-test.md`로 함께 고친다(px4-engineer).
- `plan-1a-6-idsim-mission/decisions.md`에 옛 판에서 온 음차("헬퍼", "램프", "가드", "히스테리시스")가 남아 있다. 다음에 그 문서를 고칠 때 바꾼다(architect).
- `.github/workflows/build.yml`, `build-images.yml`, `tools/ci/image_keys.py`, `tools/ci/build_images.py`에 음차("키", "잡")가 남아 있다. 다음에 고칠 때 바꾼다.
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다(`src/`의 소스가 include하는 헤더만 검사된다). 헤더 전용 검사를 둘지, `test/`를 tidy 대상에 넣을지 정한다(ros2-engineer, devops-engineer).
- `tools/ros_ws.sh tidy`는 대상이 0개이면 PASS-NO-TARGETS로 통과한다. `ci`에서는 경고나 실패로 바꿀지 검토한다(devops-engineer).
- 이미지 ENV와 `versions.env`의 대조는 스모크 images 단계와 `tools/ros_ws.sh`에서만 일어난다. 다른 스모크 단계를 단독 실행하면 대조가 없다.
- `gen_compose.sh`의 `--run-id` 인자 제거(devops-engineer).
- compose healthcheck `start_interval`의 Docker 하한은 실측하지 않았다(Docker 29.1.3, Compose 2.40.3에서 동작). `check_host.sh`에 넣을 값은 devops-engineer가 정한다.
- `tools/check_host.sh`의 셸 단위 테스트(가짜 ss, df, docker)는 두지 않았다(test-engineer 판단).

시뮬레이션과 화면 도구.

- `idsim_common/vehicle_command.hpp` 주석의 "`from_external=false`면 MAVLink로 재송출"은 소스 행(PX4 v1.17.0 `COMMAND_LONG.hpp` 89행 근처)을 주석에 적지 않았다. 6단계 실측 또는 다음 수정 때 확인한다(ros2-engineer).
- QGC가 기체에 연결된 상태에서 `qgc.sh`의 TERM 종료 동작은 실측하지 않았다.
- Gazebo GUI 깜빡임(VMware 3D 가속을 켠 상태). `QSG_RENDER_LOOP=basic`과 `vblank_mode=1`의 효과는 확인되지 않았다. 다음 후보: SceneBroadcaster `state_hertz` 낮추기, `--render-engine-gui ogre`.
- `ros_ws/src/idsim_sim/scripts/gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"는 표현이 부정확하다(sim-engineer).
- `qgc.sh`의 sha256 불일치 시 종료 코드 1 경로는 실행으로 확인하지 않았다.
- 실측하지 않은 것: `GZ_IP=127.0.0.1`을 뺐을 때의 gz-transport 디스커버리, GPS 잡음의 출처, bridge healthcheck의 `ROS_LOG_DIR=/tmp/hc`가 run 디렉터리에 로그를 남기지 않는지, 에이전트의 Fast DDS 멀티캐스트가 같은 LAN의 다른 호스트와 섞이는지, MAVLink bind에 실패한 PX4의 동작, passwd에 없는 uid 1001로 지금 스택이 도는지.
- 이 호스트의 포트 5900과 8090은 다른 프로젝트가 쓴다. VNC를 도입하면 피한다.

1b 전에 정할 것.

- takeoff 빌더와 `goto_setpoint` 공개 검토(`idsim_common`, ros2-engineer와 px4-engineer). TargetState -> setpoint 변환 위치와 원점 이동 변환 함수.
- 다대 원점 판정의 pose 보정 방식(`check_px4 --expect-pose-enu` 또는 `stack.json`의 기체별 기대 위경도). 지금 `--expect-origin`은 1대 기준이다(architect, test-engineer).
- 기체별 EKF 원점은 월드 원점이 아니라 스폰 지점이다. 월드 ENU `TargetState`를 기체 NED setpoint로 바꾸는 입력과, 커스텀 월드에서 `world.origin`과 SDF `<spherical_coordinates>`의 일치를 검사하는 주체를 정한다. 월드 SDF에 `<plugin>`이 하나라도 있으면 서버 설정 파일이 무시된다.
- bridge healthcheck는 `/clock` 1회 수신을 유지하고 표적 어댑터 판정은 별도 단계로 둔다. 커스텀 모델은 `GZ_SIM_RESOURCE_PATH`에 `/opt/idsim/sim/models`를 더해야 한다.

Phase 2와 3 전에 정할 것.

- replay job의 trigger(U4). `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 그때 고친다.
- ULog가 `compose down`에서 정상 종료되는지 확인한다. 기록량은 약 285 KiB/s, 기체당 약 1 GB/h다(logging-engineer, Phase 2 전).
- Phase 3에서 주기 하한 계약이 필요한 토픽 목록(px4-engineer).
- lockstep의 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지)은 실측하지 않았다. Phase 3 CPU 포화 해석의 전제다.

## 새 개발 PC에서 시작할 때

1. 저장소를 받는다(`git clone https://github.com/danielhongwoo/idsim.git`). 작업은 main에서 브랜치를 만들어 한다. 열린 브랜치와 PR은 `gh pr list`로 본다.
2. 호스트 조건과 환경 구성 순서는 저장소 루트 `README.md`의 "호스트 조건"과 "빠른 시작"을 따른다(`tools/check_host.sh`, 이미지, 스모크 images, px4-out, px4-in, clock). 이어서 `tools/ci/lint.sh all`과 `tools/ros_ws.sh ci`가 통과해야 한다.
3. 이미지는 로컬 빌드(`python3 tools/ci/build_images.py --mode load`, 콜드 약 22분) 대신 GHCR에서 받아 쓸 수 있다. `--mode pull`이 생기기 전에는 손으로 받는다. key는 `python3 tools/ci/image_keys.py`가 보여 주고, main build가 그 key를 올린 뒤에만 받을 수 있다.

```
python3 tools/ci/image_keys.py
for img in ros-base ros-ws xrce-agent sim-base px4; do
  key=$(python3 tools/ci/image_keys.py | awk -v i="$img" '$1==i{print $2}')
  docker pull "ghcr.io/danielhongwoo/idsim/${img}:${key}"
  docker tag "ghcr.io/danielhongwoo/idsim/${img}:${key}" "idsim/${img}:local"
done
```

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
