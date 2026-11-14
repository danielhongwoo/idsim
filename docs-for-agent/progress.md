# idsim 진행 상황

세션을 시작할 때 지금 어디에 있는지 파악하는 파일이다. 지금 유효한 것만 적는다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`, 진행 중인 단계의 계약은 `docs-for-agent/plan-*/decisions.md`에 있다. 경위는 git(커밋 메시지, PR 본문)에서 본다. 담당자 구성, 호출 규칙, 모델 선택은 `CLAUDE.md`에 있다.

## 현재 상태

| Phase | 상태 |
| --- | --- |
| 1a | 완료. 계약은 `docs/interface.md`에 고정 |
| 1b | 구현 중. 계획은 `docs-for-agent/plan-1b-mission-target/README.md`, 계약은 같은 디렉터리 `decisions.md`. B1-B8b, B9 snapshot 헤더, B9 S1-S4 반영. 칸 목록 covered 350, impossible 108, uncovered 0. runner가 받는 미션 22종 |
| 2 | 시작 전 |
| 3 | 시작 전 |

## 다음 작업

1. B9 S5(`step()`의 `FramePort`, GOTO, 좌표 상한 1e6 m, `fits_float32` 공개). 이어서 S6(표적, TRACK_ENTITY, TARGET_LOST). 순서와 범위, B9와 B10의 경계는 `decisions.md` 쟁점 12.
   - 상태기 PR마다 px4-engineer 칸 명세가 먼저이고, 칸 목록 diff의 새 칸을 같은 PR에서 덮는다.
   - 머지 전에 로컬 `tests/sitl/run_sitl.sh`(1a 시나리오)를 돌리고 1a 미션이 지나는 덮임 칸이 그대로라는 대조를 merge 메시지에 남긴다.
   - goal 접수가 받는 미션은 B9 동안 1a 그대로이고, 노드는 값 없는 임시 port와 빈 `Snapshot.targets`를 넘긴다.
2. B10: 진짜 `Px4FramePort`(`to_local_position_input`, 비행 중 `ref_timestamp_us` 변경 WARN, `world.origin` 전달), 표적 구독(goal 접수 때 `Snapshot.targets`를 비우고 노드 테스트에 사례), goal 접수 제한 제거. 같은 PR에서 시나리오 B와 노드 테스트의 무효 미션 사례를 1b 무효 사례로 바꾼다(B의 사례 범위는 test-engineer). 쟁점 12 승인 조건 (2)는 B10 검토 때 본다.
3. B11, B12, B13은 README 순서대로. B12(M4)는 궤적 길이 합 상한 월드(표적 4 x 600 s)의 GUI CPU, 서버 RSS, RTF도 기록한다.

## 운영 규칙

- 실험용 스택 번호는 px4 5, ros2 6, test 7, devops 8, sim 9. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.
- 로컬 branch는 main에 `--no-ff`로 머지하고, 적절한 시점에 origin main에 push해 CI를 확인한다.
- `idsim_mission`의 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자다(`file-ownership.md`).
- 그림은 계층으로 나눈다. 개요 그림은 묶음과 주요 경로만, 상세 그림은 개요의 상자 하나를 펼치고 도입 문장에 어느 상자인지 적는다. 같은 내용을 두 그림에 그리지 않는다. 그림 하나는 node 8개, edge 10개 이하, subgraph 중첩 1단, node label 두 줄, edge label 15자 이하이고 넘으면 나눈다. 포트, 환경변수, 경로, 명령줄은 label에 넣지 않고 그림 아래에 둔다(사용자 결정).
- 대표 시나리오의 통과를 기준으로 개발한다. 경계 상황은 보수적 기본 동작과 "미확인" 표기로 덮고, 새 실측은 관찰된 문제의 재현용으로만 하며, 산출물은 최소로 둔다(U6).
- 저장소 라이선스는 Apache-2.0. 새 소스와 CMake 파일에 머리말을 넣고 `ament_copyright`와 cpplint `legal/copyright` 검사를 켠 채로 둔다.
- 이미지 빌드의 apt 미러 기본값은 kr 미러(`docker/versions.env`의 `UBUNTU_APT_MIRROR`), CI는 우분투 기본 미러. ros-ws 이미지에 clang-tidy와 clang-format을 둔다. `tools/qgc.sh`에 설정을 되돌리는 옵션을 두지 않는다(`--stack 0`을 쓴다).

지금 유효한 사용자 결정.

- U2: `sitl` job은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외)와 main push에서 돈다. `lint`, `unit`도 `pull_request`와 `push: main`.
- U4: replay job의 trigger는 Phase 2에서 정한다. 그때 `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 고친다.
- U7: 1b에서 반복 이륙(첫 항목이 아닌 TAKEOFF)은 뺀다.
- U8: `COM_LOW_BAT_ACT`를 계약 SITL 파라미터 표에 넣어 2(Land)로 고정한다.
- U9: `RTL_RETURN_ALT`는 미션 고도에 맞춘다(1b는 순항 5 m에 10 m).
- U10: 표적은 스크립트 궤적을 따르는 점 표적이다. 생산자는 교체 가능하고 Gazebo 기반 생산자는 확장 항목이다.
- U11, U15: CI `sitl` 목표 15분. 1b 비행 시나리오를 모두 PR CI에 두고, 넘으면 겹치는 비행 구간 -> waypoint 수 -> Hold 시간 순으로 줄인다. F2의 공중 종료와 F3의 공중 시작은 빼지 않는다.
- U12: Gazebo 정답 pose(`/sim/`)를 SITL MCAP 기록물에 넣는다(Phase 2부터 효과).
- U13: roadmap 1b 목표를 그대로 덮는 합친 미션 시나리오 F4를 둔다. F1-F3은 경계 상황 검증용.
- U14: 1b waypoint 판정 반경은 1 m. 시험 미션의 `acceptance_radius_m`은 `1 m - b` 이하.
- U16: `docs-for-agent/file-ownership.md`의 소유자는 architect.

## 미해결 사항

B10 전에 정할 것.

- (u) 모드 명령 항목(LAND, RTL)에서 모드 3회 확인과 `mode_confirm_timeout`이 같은 tick이면 구현은 확인이 이기는데 `docs/interface.md` "종료의 충돌 규칙"은 만료가 이긴다고 적는다. 구현을 고칠지(1a 동작 변경) 계약에 예외를 둘지, 확인 tick의 거부 ack까지 함께 정한다(architect, px4-engineer, ros2-engineer).
- 공중 종료 단계의 정리 상한(12 s)이 `land_disarm_fallback_delay`를 포함하지 않는다. 지연을 9 s 이상으로 주면 이륙 이력 없는 지상 대기가 늘 상한 ABORTED다. 상한에 넣을지 파라미터 관계 검사를 둘지 정하고 `config.hpp` 상한 주석도 고친다(architect).
- 공중 Offboard 진입: 첫 OFFBOARD 표본 뒤에도 감시 하한 timestamp가 P3 표본에 머문다(`monitored_status`). 늦은 AUTO_LOITER 표본이 EXTERNAL_MODE_CHANGE를 낼 수 있다(관찰 안 됨). 하한을 올릴지, 재전송이 운용자 Hold를 한 번 덮는 경우를 받아들인 위험에 올릴지, `docs/interface.md` 607행 목록에 먼저 본 OFFBOARD와 첫 OFFBOARD 표본을 넣을지(B13) 정한다(architect).
- Px4Timestamp를 만들지 못해 끝난 goal의 `detail` 꼬리 "vehicle state unknown, may remain armed on ground"가 공중 경로에도 붙는다. `landed`로 문구를 가를지 정해 별도 PR로 고친다. `COM_FAIL_ACT_T`가 `sitl_params.env`에 없어 Offboard 손실 Land 앞에 지연이 끼는지도 본다(architect, px4-engineer, ros2-engineer).

S6 칸 명세 전에 정할 것.

- 표적 위치의 유효 표본 규칙에 좌표 상한을 둘지(px4-engineer, ros2-engineer, sim-engineer, architect).

문서 정리(정형, 다음 문서 정리 때).

- `decisions.md` 쟁점 12 근거의 "DISARMED에서 DO_SET_MODE 거부는 TERMINATION뿐이다" 인용을 `UserModeIntention.cpp` 73-74행(결과 값은 `Commander.cpp` 927-932행)으로 고친다. 쟁점 7의 "루프"는 loop로.
- 유효 ack 뒤 재전송을 멈추는 규칙의 전제 "ACCEPTED면 모드 전환이 일어난다"(`Commander.cpp` 912-927행, [실측] 17회)를 쟁점 12 근거에 적고, `docs/interface.md` 341행을 1a 고정 계약 영향 (t)에 넣을지 정한다(architect).
- 저장소 밖 이름표("쟁점 10 A1/A2", "칸 명세 6.2절", "D12", "B9 S4 칸 명세(7.1)의 사례 A1-A27")를 `mission_runner.cpp/.hpp`, 패키지 `README.md`, `test_runner_mission_end.cpp`, `test_runner_air_entry.cpp`에서 `decisions.md` 문구로 바꾼다(ros2-engineer).
- `idsim_common/vehicle_command.hpp` 주석의 MAVLink 재송출 문장에 소스 행(v1.17.0 `COMMAND_LONG.hpp` 82-96행)을 적는다(ros2-engineer). `gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다"를 고친다(sim-engineer).
- `docs/architecture.md`의 `tools/sim_stack.sh` 운영 규칙 문단에 restart-ops 뒤 attach 경로를 적을지(architect). `docs/interface.md` SITL 파라미터 표에 `IMU_GYRO_CAL_EN`을 넣을지(architect).

테스트 보강.

- 종료 단계에서 대비책 뒤 지상 DISARMED를 `DisarmConfirm`으로 세는 연결을 가르는 사례가 없다. timestamp가 전송 stamp 이하인 지상 DISARMED 셋으로는 끝나지 않음을 T10 경로와 G8 뒤 AIR_LAND에서 단정한다. 6a의 ack 버림 줄은 주석을 달거나 지운다(ros2-engineer, test-engineer, px4-engineer).
- 쟁점 7의 D [추정]을 기존 1a 산출물(A의 LAND, D의 Hold)의 모드 표본 간격으로 [실측]으로 바꾼다(px4-engineer).
- ACCEPTED 사건 stamp의 건전성을 노드 테스트로 덮을지 판정으로 덮을지(test-engineer, ros2-engineer).
- 성공 sitl run의 summary.md에 ULog `battery_status`, `cpuload`, `system_power` 마지막 표본 시각을 남겨 숨은 발행 정지를 센다. trace 이정표에 수신 시각을 남긴다(test-engineer, logging-engineer).
- `test_px4_topic_names.py::test_argument_checks`의 SpinThread `InvalidHandle` 경고, `tools/vehicle_arming_state.py`의 rc 2 사례 테스트(test-engineer).
- 스모크 images 단계가 `LLVM_MAJOR`, `FOXGLOVE_BRIDGE_VERSION`을 대조하지 않는다(test-engineer). `ros_ws.sh`에 `versions.env` 이름 기준 존재 검사를 둘지(devops-engineer, test-engineer).

B11 판정에서 챙길 것(test-engineer).

- `tests/support`에 `/sim/<vehicle_id>/pose` 조립 순수 함수와 `sim_oracle.py`의 `ORACLE_TOPIC_CASES`, `ORACLE_TOPIC_INVALID`와 같은 사례 표(import로 공유하지 않음). `target_id` 사례 표의 단일 출처는 이때 정한다(architect).
- 정답 pose 구독은 첫 `mission_event` 전에 discovery와 `sim-oracle` 준비를 확인하고 depth를 크게 둔다(발행은 RELIABLE, VOLATILE, KEEP_LAST 10). QoS 짝을 `tests/support` 머리말에 적는다. `ORACLE_STALE`은 `/clock`이 `t_f + 0.1 s`를 지날 때까지 기다린 뒤 판정한다.
- start 뒤 health가 healthy가 되기를 기다린다(interval 10 s). uid 1001로 스택 전체가 도는지는 CI sitl에서 본다.
- F2 trace: Land 경로 뒤 DISARMED 표본의 `nav_state`, 지상 Hold 뒤 자동 disarm, Hold 3회 소요. F3 trace: D와 P5의 DO_SET_MODE 전송 수, 첫 OFFBOARD 표본 뒤 OFFBOARD가 아닌 표본의 timestamp 순서.

빌드와 CI.

- `sitl.yml`은 GHCR에서 이미지 key로 pull하므로 이미지 key가 바뀌는 PR은 PR과 머지 직후 main 양쪽에서 pull이 실패한다. 지금은 로컬 `run_sitl.sh`로 대신하고 publish 뒤 main에서 `sitl`을 다시 돌린다. `workflow_run`으로 묶을지 등은 devops-engineer와 architect가 정한다.
- 같은 key로 두 번째 main build가 돌 때 이미지 5종이 모두 SKIP되는지 확인한다(devops-engineer).
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다. `tools/ros_ws.sh tidy`의 대상 0개 통과를 `ci`에서 바꿀지(ros2-engineer, devops-engineer).
- 비결정 빌드 요소(ros.key, gazebo.gpg URL, apt 저장소 상태, pip 인덱스)는 이미지 key에 들어가지 않는다. apt `Acquire::Retries` 미적용이라 미러 장애나 동기화 시차로 apt 단계가 실패할 수 있다.
- 실패 run의 `artifacts/runs/`가 job artifact로 올라가는지 확인하고, 판정 상수를 재검토한다(1a 쟁점 9).

시뮬레이션과 화면 도구.

- Gazebo GUI 깜빡임(VMware 3D 가속). 다음 후보: SceneBroadcaster `state_hertz` 낮추기, `--render-engine-gui ogre`.
- 이 호스트의 포트 5900과 8090은 다른 프로젝트가 쓴다. VNC를 도입하면 피한다.
- PX4 버전을 올리면 "ULog `vehicle_command` `timestamp`가 측정기 stamp와 같다"와 "ack 기록 순서가 처리 순서와 같다"를 다시 확인한다(px4-engineer).
- [미확인]으로 둔 것(관찰된 문제가 있을 때만 잰다, U6): QGC 연결 중 `qgc.sh` TERM 종료와 sha256 불일치 경로, `GZ_IP` 없는 디스커버리, `ops-N` goal 실행 중 stop의 종료 사건, `vehicle.id` 누락에서 unhealthy까지의 시간, 에이전트 Fast DDS 멀티캐스트의 LAN 섞임, MAVLink bind 실패 시 PX4 동작, compose `start_interval`의 Docker 하한.

Phase 2와 3 전에 정할 것.

- Phase 2 착수 전 설계 토론(ops-service-engineer, logging-engineer, architect): `VehicleState`의 ROS 시각 역행 처리(replay 일시정지와 배속 포함), 소비자 미수신 timeout 배수, stamp 단조성, WebSocket JSON 표현, gRPC `StreamMissionEvents`와 ROS `MissionEvent`의 관계, 기록기의 구독 확인 순서.
- ULog가 `compose down`에서 정상 종료되는지(기체당 약 1 GB/h, logging-engineer).
- Phase 3: Fleet 재시작 복구 경로, 이탈 기체 goal 재배분 한 번, 주기 하한 계약이 필요한 토픽 목록(px4-engineer), lockstep 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지).

## 새 개발 PC에서 시작할 때

1. `git clone https://github.com/danielhongwoo/idsim.git`. 열린 브랜치와 PR은 `gh pr list`로 본다.
2. 호스트 조건과 환경 구성은 루트 `README.md`의 "호스트 조건"과 "빠른 시작"을 따른다. 이어서 `tools/ci/lint.sh all`과 `tools/ros_ws.sh ci`가 통과해야 한다.
3. 이미지는 `python3 tools/ci/build_images.py --mode pull`로 GHCR에서 받을 수 있다(key는 `python3 tools/ci/image_keys.py`, main build가 올린 뒤에만).
4. 같은 호스트의 다른 ROS 2 스택, Gazebo, compose 프로젝트를 먼저 보고(`docker ps`, `docker compose ls`) 겹치면 스택 번호를 바꾼다.
5. `gh pr edit`는 이 저장소에서 GraphQL Projects(classic) 오류로 실패한다. PR 본문은 `gh api -X PATCH repos/danielhongwoo/idsim/pulls/<번호> -F body=@<파일>`로 고친다.
6. 사용자 전역 규칙 `~/.claude/CLAUDE.md`(커밋 메시지에 도구 트레일러 금지)를 새 PC에도 둔다. 로컬 `artifacts/`는 옮겨지지 않는다.

## 갱신 규칙

- 작업 단위가 끝나면 "현재 상태"를 고쳐 쓰고, 끝난 "다음 작업"과 닫힌 "미해결 사항"은 지운다. 완료 표시, 날짜, 경위를 남기지 않는다.
- 항목은 한두 줄로 쓴다. 근거, 실측값, run id, 검토 경과는 커밋 메시지와 PR 본문에, 계약은 `decisions.md`나 `docs/`에 둔다.
- 사용자만 정할 수 있는 사항(범위, 언어 선택, 비용)은 "미해결 사항"의 첫 묶음에 올린다.
