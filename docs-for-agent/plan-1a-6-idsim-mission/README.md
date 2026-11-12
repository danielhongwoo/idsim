# Phase 1a 6번 작업 idsim_mission 작업 계획

설계 결정과 계약은 `decisions.md`에 있다. 지금 어디까지 왔는지는 `docs-for-agent/progress.md`에 있다. 경위와 검토 내역은 커밋 메시지와 PR 본문에 있다.

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | 사용자 결정, 결정 요약, 계약과 golden(M1-M7), 쟁점 1-13(전이 표는 쟁점 4, 취소와 정리는 쟁점 3), 담당자별 구현 지시, 넘김 목록, 문서 반영 목록 | 계약. 구현은 이 문서를 따른다 |

담당자 의견서의 권고 중 `decisions.md`와 다른 것은 `decisions.md`가 우선한다.

초기 근거 파일(담당자 의견서, 승인 검토, P3a 실행 확인 결과)은 저장소에 두지 않고 git 이력에서 본다: `git ls-tree --name-only b02f28f docs-for-agent/plan-1a-6-idsim-mission/`로 목록을, `git show b02f28f:<경로>`로 내용을 본다.

## 범위

6단계가 만드는 것: `ros_ws/src/idsim_mission/`(Executor), `idsim_common`의 추가 항목, 생성기의 `ops-N` 서비스와 params와 `stack.json` key, `tests/sitl/`과 `tests/support/`의 판정 코드, CI `sitl` job, `viz` 프로필의 `foxglove`와 `lichtblick`.

만들지 않는 것: `docs/interface.md`(7단계), GOTO, TRACK_ENTITY, RTL과 YAML 미션(1b), `bridge.yaml`(1b), recorder와 MCAP 업로드(Phase 2), 3대 시나리오(Phase 3).

`idsim_interfaces`의 필드는 바꾸지 않는다. 상수 둘(`ExecuteMission`의 `REASON_DISARM_FAILED = 13`, `REASON_EXTERNAL_DISARM = 14`)을 더하고 의미 문장(M1-M7)을 고친다. golden은 `ExecuteMission`의 직접 정의와 펼친 정의 두 파일에 두 줄씩 늘었고 type hash는 그대로다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| P0. CI trigger 정리 | devops-engineer | lint, unit을 `pull_request` + `push: main`으로(U2) | 없음. 맨 먼저 |
| P1. 이미지 | devops-engineer | `Dockerfile.ros-ws`에 foxglove_bridge, `versions.env`의 `FOXGLOVE_BRIDGE_VERSION`, bake, 버전 접두 단정. 이미지 크기 실측 | 없음 |
| P2. `idsim_common` 추가 | ros2-engineer | `VehicleId`, vehicle params 해석, Options overload, position setpoint 헬퍼, 사건 QoS, 빌더 `make`(`decisions.md` 쟁점 5) | 없음. P1과 병렬 |
| P3. `idsim_mission` | ros2-engineer(껍질, core), px4-engineer(`px4/` 셋), architect(`ExecuteMission.action`의 상수 `REASON_DISARM_FAILED`, `REASON_EXTERNAL_DISARM` 추가와 주석, golden) | P3a autostart 실행 확인, 콜드 기동의 첫 `/clock` 수신 시간, ACCEPTED 누락 계수 실험 200회. P3b core(검증, 분류 함수, 상태기, 종료 결과)와 단위 테스트. P3c `px4/` 어댑터와 단위 테스트. P3d 노드 껍질, launch, 배선 테스트. P3e `ExecuteMission.action`의 상수 둘 추가(13은 M5, 14는 감시 표의 지상 DISARMED 행)와 주석(M1, M3-M5, 두 상수의 의미), golden 두 파일 | P2 |
| P4. core 변경, 생성기, 통합 | ros2-engineer(core 변경과 단위 테스트, 패키지 README. px4-engineer 필수 승인), devops-engineer(생성기, `sim_stack.sh`, `run_smoke.sh`, `check_host.sh`, `build_images.py --mode pull`, `sitl.yml`, `px4-api` 범위), test-engineer(`tests/support/`, `tests/sitl/`), architect(문서 반영) | `decisions.md` 쟁점 3 M6과 쟁점 4의 core 변경(P6에서 ARMED를 처음 관측한 뒤의 감시와 확인 기한, 감시 표로 끝낼 때의 disarm 1회, 정리의 상한, Hold 실패 뒤의 재진입), 쟁점 1, 2, 7-11 | P1이 main에 들어가 build가 새 key를 올린 뒤, P3 뒤 |
| P5. viz | devops-engineer | `foxglove`, `lichtblick` 서비스, `LICHTBLICK_IMAGE`, 접속 안내, 브라우저 실접속 확인 | P4 |

커밋은 담당자 소유 단위로 나눈다. PR은 위 단위마다 하나다. P4가 합쳐지기 전에는 `tools/sim_stack.sh up`의 동작이 바뀌지 않는다.

실험용 스택 번호: px4 5, ros2 6, test 7, devops 8. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.

## 진행 순서

P0-P5, 재실측 (2), (3), (5), 사용자 육안 확인(QGC, Gazebo GUI)은 끝났다. 남은 순서는 아래와 같다. 기준은 대표 시나리오의 통과이고, 경계 상황은 보수적 기본 동작과 "미확인" 표기로 덮는다(`decisions.md` U6).

1. Executor feedback stamp를 tick 입력 시각으로 찍고, 시나리오 A의 LOITER 유지 판정에서 `/clock` 한 양자 허용을 되돌린다.
2. 7단계(`docs/interface.md`) 문서 작업. 새 실측을 기다리지 않는다.

## 검토

| 단위 | 관련 owner 검토 | 볼 것 |
| --- | --- | --- |
| P1 | ros2-engineer | 설치 판과 foxglove params 이름. 다른 이미지 key가 그대로인지 |
| P2 | px4-engineer, test-engineer | setpoint 헬퍼와 빌더의 필드 표, source == target 거부. 테스트가 노드 없이 도는지 |
| P3 | px4-engineer(전이 표와 상태기 테스트의 필수 승인), ros2-engineer(`px4/` 어댑터와 snapshot 경계), test-engineer(단위 테스트 구조), architect(계약 문장과 구현의 일치, golden diff가 `ExecuteMission`의 두 파일에 두 줄씩뿐이고 `type_hashes.txt`는 그대로인지) | 발행 규칙, 감시 표, 취소 분기, status와 reason 대응표, 사건 == result, core가 px4_msgs에 의존하지 않는지 |
| P4 | ros2-engineer(launch와 params 대응, matched 판정), px4-engineer(core 변경과 상태기 단위 테스트의 필수 승인, 시나리오의 판정 필드, 타임아웃, 테스트의 /fmu/in 사용), test-engineer와 devops-engineer(서로의 경계: wrapper의 `sim_stack.sh` 호출부, `stack.py` 접근자, 아티팩트 경로), sim-engineer(`--infra-only`가 스모크와 gazebo 단계에 주는 영향) | 스모크 px4-out-clock이 `--infra-only`로 통과하는지, 생성기 golden 4종의 diff, embedded에 노드 서비스가 없는지 |
| P5 | ros2-engineer, sim-engineer | 화이트리스트, 127.0.0.1, `viz`에 본 스택이 의존하지 않는지, 실접속 결과 |
| 전체 | reviewer | PR마다 규칙 준수와 가정의 근거. P3과 P4는 머지 전 필수 |

관련 owner의 승인 없이 머지하지 않는다. px4-engineer 호출이 안전장치로 중단되면 `CLAUDE.md` 모델 선택 규칙의 "사용자 예외"를 따른다.

## 완료 기준

- P1: build job이 새 ros-ws key를 GHCR에 올리고 다른 넷의 key는 그대로다. 이미지 안에서 `ros2 pkg prefix foxglove_bridge`가 성공한다.
- P2: `tools/ros_ws.sh ci` 통과. `idsim_common` 테스트 수가 늘고 기존 109건이 통과한다.
- P3: `tools/ros_ws.sh ci` 통과. `idsim_mission` 테스트 결과 1건 이상. `idsim_interfaces` 계약 테스트가 통과하고 `git diff test/golden`이 `ExecuteMission`의 직접 정의와 펼친 정의 두 파일에 `REASON_DISARM_FAILED = 13`과 `REASON_EXTERNAL_DISARM = 14` 두 줄씩뿐이다(`type_hashes.txt` 무변경). core 단위 테스트가 `decisions.md`의 전이 표, 취소 분기, status와 reason 대응표, 종료 사건 == result, `TYPE_*` 분류를 덮는다. 스택 위에서 `ops` 컨테이너가 자기 전이로 active가 되는 것을 손으로 확인한다(launch에서 `autostart`를 뺀 형태). P3a의 계수 실험 결과(200회 중 ACCEPTED 누락 횟수)와 첫 `/clock` 수신 시간이 기록되어 있다.
- P4
  - `decisions.md` 쟁점 3 M6과 쟁점 4의 core 변경이 구현되어 `tools/ros_ws.sh ci`가 통과하고 px4-engineer가 승인했다. `idsim_interfaces`의 golden은 그대로다.
  - `tools/ci/lint.sh all` 통과(생성기 단위 테스트와 golden 4종, `compose config`, `px4-api` 넓힌 범위, 문자 집합).
  - 스모크 images, px4-out-clock이 `--infra-only` 스택에서 통과한다(golden `--check` 일치).
  - `tests/sitl/run_sitl.sh --repeat 3`이 같은 commit, 같은 이미지 key에서 3회 연속 통과하고 회차 요약이 남는다. 시나리오는 B, C, A, D, T 다섯이다.
  - 올림 기준: `sitl` job이 15분을 넘거나 판정 구간의 RTF(ROS 시각 경과 / 벽시계 경과)가 한 회라도 0.7 미만이면 타임아웃, 허용 오차, `wall_cap` 배수를 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다. 첫 3회의 단계별 시간과 RTF를 기록한다.
  - CI `sitl` job이 통과하고 실패 때 아티팩트가 올라가는 것을 한 번 확인한다(일부러 실패시킨 실행 또는 첫 실패 실행).
  - `artifacts/runs/`에 호스트 사용자 소유가 아닌 파일이 없다.
  - 문서 반영 목록 반영(reviewer 확인).
  - 생성기 성질 테스트 넷(상주 ros-ws 서비스의 `init: true`, `ops-N`의 `stop_signal`과 `stop_grace_period`, params에 `lifecycle.` key 없음, healthcheck FQN과 `executor_node` 일치)이 통과한다.
  - 재실측 (2), (3), (5)와 ARMED 표본 기준이 `decisions.md` "재실측 결과와 기준"대로 통과했다(충족).
- P5: `tools/sim_stack.sh up --viz` 뒤 브라우저에서 Lichtblick이 foxglove_bridge에 붙고 setpoint와 `vehicle_local_position`이 같은 플롯에 놓인다. 두 포트가 127.0.0.1에만 열려 있다.
- 6단계 전체(roadmap 1a 완료 기준 중 이 단계 몫): 통합 테스트 로컬 3회 연속 통과, CI `sitl` 통과, QGC와 Gazebo GUI로 같은 비행을 사용자가 확인.

## 범위 밖(넘길 곳)

`decisions.md`의 "넘김 목록"이 정본이다. 요약.

- 7단계: `docs/interface.md`에 M1-M7, reason별 ABORTED 뒤 기체 상태 표, source 표, 발행 규칙, 공중에서 끝나는 미션의 "고정 전" 표시. 실측 근거가 없는 항목은 "미확인"과 보수적 동작으로 적는다.
- 1b: 공중에서 끝나는 미션의 종료 동작, 공중 시작 미션, 1a 임시 제한 해제, `bridge.yaml`.
- Phase 2: replay job의 trigger(사용자 결정 U4), recorder와 MCAP 업로드, `MissionEvent` QoS 재검토 제안, ULog 종료 확인.
- Phase 3: `validate_mission`의 Fleet 공용, 취소 뒤 `[LAND]` 절차.

## 사용자 결정

U1-U4와 U6은 `decisions.md` 머리의 "사용자 결정"에 있다. 남은 확인은 GHCR 패키지 다섯과 buildcache의 Public 설정이다.
