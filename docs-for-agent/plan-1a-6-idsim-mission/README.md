# Phase 1a 6번 작업 idsim_mission 작업 계획

작성 2026-11-11, 같은 날 확정 개정. 설계 결정은 `decisions.md`에 있고 확정본이다(reviewer 검증의 필수 7건과 권고 10건, 사용자 결정 3건 반영). 계획은 PR #18로 main에 들어갔다. P0은 끝났고(PR #19) P1, P2, P3a가 진행 중이다. px4-engineer의 P3b 착수 전 승인 항목 다섯은 2026-11-11에 닫혔고(`approval-px4-p3b.md`) 그 반영이 PR #21로 main에 들어가 P3b를 시작할 수 있다. PR #21에 대한 reviewer 조건(필수 5건)은 후속 PR(브랜치 `docs/1a-6-p3b-review`)로 반영한다.

## 진행 상태 (2026-11-11)

| 단위 | 상태 |
| --- | --- |
| 설계 결정 | 확정(`decisions.md`). 의견 넷, 재질문 다섯 건, reviewer 검증(조건부) 반영. reviewer 재확인(조건부) 반영: M5 (나) 성립, LAND 감시 시작 시점과 ITEM_TIMEOUT 정리 보강. P0-P3a 착수 가능, P3b는 px4-engineer 승인 항목 뒤 |
| 사용자 결정 | U1(D와 `[LAND]`를 1a 필수에), U2(`sitl`은 PR 머리 커밋마다와 main push, lint와 unit trigger 정리), U3(공중에서 끝나는 미션은 1b로) 확정. GHCR Public 확인만 남음 |
| 소유 반영(`CLAUDE.md`, `.claude/agents/`) | 완료(사용자 승인 2026-11-11, 호출한 쪽이 반영). `file-ownership.md`는 계획 PR에서 호출한 쪽이 반영한다(문안은 `decisions.md` 문서 반영 목록) |
| px4-engineer 승인 항목(P3b 착수 전) | 닫힘(2026-11-11). 승인 2건, 수정 조건부 3건, 반대 없음. 실측 run 20261111-030155-k5. `decisions.md`의 "px4-engineer 승인 반영"에 반영했다(PR #21 머지). P3b 착수 가능. 실측이 없는 두 경로와 감시 표의 행 순위는 표대로 구현하되 재실측으로 바뀔 수 있다 |
| PR #21 reviewer 검증 | 조건부(필수 5건, 권고 6건). 후속 PR에서 반영: 상수 `REASON_EXTERNAL_DISARM = 14` 추가(golden은 두 파일에 두 줄씩), 감시 표의 행 순위(잠정), M3의 미확인 목록, 필수 재실측 다시 정함. 사용자 결정 U4(replay job trigger는 Phase 2에서), U5(px4 확인은 개정 뒤). px4-engineer의 반영 확인은 개정 뒤 받을 예정 |
| P0 CI trigger 정리 | 완료(PR #19 머지 2026-11-11). lint와 unit이 `pull_request` + `push: main`에서 돈다 |
| P1 ros-ws에 foxglove_bridge | 진행 중 |
| P2 `idsim_common` 추가 | 진행 중 |
| P3 `idsim_mission` 패키지 | P3a 진행 중. P3b 착수 가능(승인 반영 PR #21 머지) |
| P4 생성기, 통합 테스트, `sitl` job, 문서 | 시작 전 |
| P5 viz | 시작 전 |
| 로컬 3회 연속 통과 | 시작 전 |

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | architect 결정 13건(확정본), 확정 개정 요약, 계약 변경 여부와 golden 영향, 재질문 결과 요약, 전이 표, 담당자별 구현 지시, 넘김 목록, 문서 반영 목록, 사용자 결정 3건, reviewer 검증 결과 | 계약. 구현은 이 문서를 따른다 |
| `opinion-px4.md` | px4-engineer 의견과 실측(스택 5. Offboard 진입, Hold 실험, 발행 중단 규칙, 타임아웃) | 근거 |
| `approval-px4-p3b.md` | px4-engineer의 P3b 착수 전 승인 항목 다섯 검토(2026-11-11. 스택 5 실측 run 20261111-030155-k5, 타임아웃과 재전송 주기의 최종 값, 추가로 발견한 문제 다섯) | 근거 |
| `opinion-ros2.md` | ros2-engineer 의견과 실측(스택 6. 패키지 구조, lifecycle, matched 판정, foxglove_bridge 파라미터) | 근거 |
| `opinion-test.md` | test-engineer 의견(실측 없음. 통합 테스트 구조, 판정 코드, 시나리오) | 근거 |
| `opinion-devops.md` | devops-engineer 의견과 조회(생성기, 이미지, Lichtblick digest, `sitl` job) | 근거 |

재질문 답 다섯 건(px4, ros2, test, devops, logging)은 파일로 두지 않고 `decisions.md`의 "재질문 결과 요약"에 옮겼다. 의견서의 권고 중 `decisions.md`와 다른 것은 `decisions.md`가 우선한다(`tools/sitl_test.sh`, `mission-N`, FQN params key, `bridge.yaml`, 임시 recorder, LAND 뒤 취소의 REJECT, 즉시 NOT_READY, `MissionEvent`의 TRANSIENT_LOCAL은 채택하지 않았다).

근거 파일에 나오는 scratchpad 경로와 실측 스크립트는 당시 환경의 임시 파일이라 저장소에 없다. 결론과 인용된 실측값만 쓴다.

## 범위

6단계가 만드는 것: `ros_ws/src/idsim_mission/`(Executor), `idsim_common`의 추가 항목, 생성기의 `ops-N` 서비스와 params와 `stack.json` key, `tests/sitl/`과 `tests/support/`의 판정 코드, CI `sitl` job, `viz` 프로필의 `foxglove`와 `lichtblick`.

만들지 않는 것: `docs/interface.md`(7단계), GOTO, TRACK_ENTITY, RTL과 YAML 미션(1b), `bridge.yaml`(1b), recorder와 MCAP 업로드(Phase 2), 3대 시나리오(Phase 3).

`idsim_interfaces`의 필드는 바꾸지 않는다. 상수 둘(`ExecuteMission`의 `REASON_DISARM_FAILED = 13`, `REASON_EXTERNAL_DISARM = 14`)을 더하고 의미 문장 넷(M1-M4)을 고친다. golden은 `ExecuteMission`의 직접 정의와 펼친 정의 두 파일에 두 줄씩 늘고 type hash는 그대로다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| P0. CI trigger 정리 | devops-engineer | lint, unit을 `pull_request` + `push: main`으로(U2) | 없음. 맨 먼저 |
| P1. 이미지 | devops-engineer | `Dockerfile.ros-ws`에 foxglove_bridge, `versions.env`의 `FOXGLOVE_BRIDGE_VERSION`, bake, 버전 접두 단정. 이미지 크기 실측 | 없음 |
| P2. `idsim_common` 추가 | ros2-engineer | `VehicleId`, vehicle params 해석, Options overload, position setpoint 헬퍼, 사건 QoS, 빌더 `make`(`decisions.md` 쟁점 5) | 없음. P1과 병렬 |
| P3. `idsim_mission` | ros2-engineer(껍질, core), px4-engineer(`px4/` 셋), architect(`ExecuteMission.action`의 상수 `REASON_DISARM_FAILED`, `REASON_EXTERNAL_DISARM` 추가와 주석, golden) | P3a autostart 런타임 확인, 콜드 기동의 첫 `/clock` 수신 시간, ACCEPTED 누락 계수 실험 200회. P3b core(검증, 분류 함수, 상태기, 종료 결과)와 단위 테스트. P3c `px4/` 어댑터와 단위 테스트. P3d 노드 껍질, launch, 배선 테스트. P3e `ExecuteMission.action`의 상수 둘 추가(13은 M5, 14는 감시 표의 지상 DISARMED 행)와 주석(M1, M3-M5, 두 상수의 의미), golden 두 파일 | P2. P3b는 `decisions.md` 쟁점 4의 "P3b 착수 전 px4-engineer 승인 항목" 뒤 |
| P4. 생성기와 통합 | devops-engineer(생성기, `stack.sh`, `run_smoke.sh`, `check_host.sh`, `build_images.py --mode pull`, `sitl.yml`, `px4-api` 범위), test-engineer(`tests/support/`, `tests/sitl/`), architect(문서 반영) | `decisions.md` 쟁점 1, 2, 7-11 | P1이 main에 들어가 build가 새 key를 올린 뒤, P3 뒤 |
| P5. viz | devops-engineer | `foxglove`, `lichtblick` 서비스, `LICHTBLICK_IMAGE`, 접속 안내, 브라우저 실접속 확인 | P4 |

커밋은 담당자 소유 단위로 나눈다. PR은 위 단위마다 하나다. P4가 합쳐지기 전에는 `tools/stack.sh up`의 동작이 바뀌지 않는다.

실험용 스택 번호: px4 5, ros2 6, test 7, devops 8. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.

## 진행 순서

1. (완료) reviewer가 `decisions.md`를 검증했다(조건부). 필수 7건과 권고 10건을 확정본에 반영했다.
2. (완료) 사용자 결정 U1, U2, U3. GHCR Public 확인은 남았다.
3. reviewer가 확정본의 "재확인이 필요한 지점"을 본다. 동시에 P0, P1, P2, P3a를 시작한다. P1이 합쳐지면 main build가 새 ros-ws key를 올린 것을 확인하고 뒤의 브랜치를 rebase한다.
4. P3. 첫 작업은 P3a다. autostart가 실패하면 단독 실행 파일로 물러서고 architect에게 알린다. px4-engineer가 승인 항목 다섯(ITEM_TIMEOUT 뒤 정리의 snapshot 분기, TAKEOFF 시작 조건은 지상이고 DISARMED, 지상 arm 취소 분기의 setpoint, LAND 감시의 세 구간, 방어용 분류)을 닫은 뒤 P3b를 시작한다(2026-11-11에 닫혔고 PR #21로 반영됐다. 시작할 수 있다).
5. P4. 로컬에서 `tests/sitl/run_sitl.sh --repeat 3`이 통과한 뒤 PR을 올리고 `sitl` job의 첫 실행을 본다. 첫 3회의 단계별 시간과 RTF를 기록한다.
6. P5. 브라우저 실접속을 확인한다.
7. 사용자 육안 확인(QGC, Gazebo GUI에서 같은 비행). `tools/stack.sh up --viz` 뒤 `tests/sitl/run_sitl.sh --attach <실행 디렉터리>`로 시나리오 A를 돌린다.
8. 7단계(`docs/interface.md`)로 넘어간다. 계약 고정 전에 px4-engineer의 필수 재실측이 끝나야 한다(`decisions.md` 넘김 목록의 여덟 항목: AUTO_LAND 하강 중 0.3 m 아래 취소, 지상 setpoint 발행 중의 Hold, 이륙 직후의 지상 setpoint와 disarm, 감시 표 순위의 확인, arm 전송 직후 취소의 경쟁, 표본 늘리기, X3, Executor가 보낸 `[LAND]`). P3b가 구현하는 경로에 걸린 항목은 P3 머지 전에 하기를 권한다.

## 검토

| 단위 | 관련 owner 검토 | 볼 것 |
| --- | --- | --- |
| P1 | ros2-engineer | 설치 판과 foxglove params 이름. 다른 이미지 key가 그대로인지 |
| P2 | px4-engineer, test-engineer | setpoint 헬퍼와 빌더의 필드 표, source == target 거부. 테스트가 노드 없이 도는지 |
| P3 | px4-engineer(전이 표와 상태기 테스트의 필수 승인), ros2-engineer(`px4/` 어댑터와 snapshot 경계), test-engineer(단위 테스트 구조), architect(계약 문장과 구현의 일치, golden diff가 `ExecuteMission`의 두 파일에 두 줄씩뿐이고 `type_hashes.txt`는 그대로인지) | 발행 규칙, 감시 표, 취소 분기, status와 reason 대응표, 사건 == result, core가 px4_msgs에 의존하지 않는지 |
| P4 | ros2-engineer(launch와 params 대응, matched 판정), px4-engineer(시나리오의 판정 필드, 타임아웃, 테스트의 /fmu/in 사용), test-engineer와 devops-engineer(서로의 경계: wrapper의 `stack.sh` 호출부, `stack.py` 접근자, 아티팩트 경로), sim-engineer(`--infra-only`가 스모크와 gazebo 단계에 주는 영향) | 스모크 S2-S5가 `--infra-only`로 통과하는지, 생성기 golden 4종의 diff, embedded에 노드 서비스가 없는지 |
| P5 | ros2-engineer, sim-engineer | 화이트리스트, 127.0.0.1, `viz`에 본 스택이 의존하지 않는지, 실접속 결과 |
| 전체 | reviewer | PR마다 규칙 준수와 가정의 근거. P3과 P4는 머지 전 필수 |

관련 owner의 승인 없이 머지하지 않는다. px4-engineer가 안전장치 오류로 중단되면 그 검토 항목을 미결로 적고 architect에게 알린다.

## 완료 기준

- P1: build job이 새 ros-ws key를 GHCR에 올리고 다른 넷의 key는 그대로다. 이미지 안에서 `ros2 pkg prefix foxglove_bridge`가 성공한다.
- P2: `tools/ros_ws.sh ci` 통과. `idsim_common` 테스트 수가 늘고 기존 109건이 통과한다.
- P3: `tools/ros_ws.sh ci` 통과. `idsim_mission` 테스트 결과 1건 이상. `idsim_interfaces` 계약 테스트가 통과하고 `git diff test/golden`이 `ExecuteMission`의 직접 정의와 펼친 정의 두 파일에 `REASON_DISARM_FAILED = 13`과 `REASON_EXTERNAL_DISARM = 14` 두 줄씩뿐이다(`type_hashes.txt` 무변경). core 단위 테스트가 `decisions.md`의 전이 표, 취소 분기, status와 reason 대응표, 종료 사건 == result, `TYPE_*` 분류를 덮는다. 스택 위에서 `ops` 컨테이너가 autostart로 active가 되는 것을 손으로 확인한다. P3a의 계수 실험 결과(200회 중 ACCEPTED 누락 횟수)와 첫 `/clock` 수신 시간이 기록되어 있다.
- P4
  - `tools/ci/lint.sh all` 통과(생성기 단위 테스트와 golden 4종, `compose config`, `px4-api` 넓힌 범위, 문자 집합).
  - 스모크 S0, S2-S5가 `--infra-only` 스택에서 통과한다(S4 `--check` 일치).
  - `tests/sitl/run_sitl.sh --repeat 3`이 같은 commit, 같은 이미지 key에서 3회 연속 통과하고 회차 요약이 남는다. 시나리오는 B, C, A, D, T 다섯이다.
  - 올림 기준: `sitl` job이 15분을 넘거나 판정 구간의 RTF(ROS 시각 경과 / 벽시계 경과)가 한 회라도 0.7 미만이면 타임아웃, 허용 오차, `wall_cap` 배수를 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다. 첫 3회의 단계별 시간과 RTF를 기록한다.
  - CI `sitl` job이 통과하고 실패 때 아티팩트가 올라가는 것을 한 번 확인한다(일부러 실패시킨 실행 또는 첫 실패 실행).
  - `artifacts/runs/`에 호스트 사용자 소유가 아닌 파일이 없다.
  - 문서 반영 목록 반영(reviewer 확인).
- P5: `tools/stack.sh up --viz` 뒤 브라우저에서 Lichtblick이 foxglove_bridge에 붙고 setpoint와 `vehicle_local_position`이 같은 플롯에 놓인다. 두 포트가 127.0.0.1에만 열려 있다.
- 6단계 전체(roadmap 1a 완료 기준 중 이 단계 몫): 통합 테스트 로컬 3회 연속 통과, CI `sitl` 통과, QGC와 Gazebo GUI로 같은 비행을 사용자가 확인.

## 범위 밖(넘길 곳)

`decisions.md`의 "넘김 목록"이 정본이다. 요약.

- 7단계: 필수 재실측(px4), `docs/interface.md`에 M1-M5, reason별 ABORTED 뒤 기체 상태 표, source 표, 발행 규칙, 공중에서 끝나는 미션의 "고정 전" 표시.
- 1b: 공중에서 끝나는 미션의 종료 동작, 공중 시작 미션, 1a 임시 제한 해제, `bridge.yaml`.
- Phase 2: replay job의 trigger(사용자 결정 U4), recorder와 MCAP 업로드, `MissionEvent` QoS 재검토 제안, ULog 종료 확인.
- Phase 3: `validate_mission`의 Fleet 공용, 취소 뒤 `[LAND]` 절차.

## 사용자 결정과 알림

- 결정(2026-11-11, 셋 다 architect 권고안. 호출한 쪽이 전달): U1 시나리오 D와 `[LAND]` 한 항목 미션을 1a 필수에 넣는다. U2 `sitl`은 PR 머리 커밋마다와 main push, lint와 unit trigger도 맞춘다. U3 공중에서 끝나는 미션의 종료 동작은 1b로 미룬다.
- 남은 것: GHCR 패키지 다섯과 buildcache의 Public 설정 확인. `CLAUDE.md` 담당자 표와 `.claude/agents/` 세 파일의 소유 반영은 끝났다(사용자 승인, 호출한 쪽이 반영).
- 알림: `ExecuteMission`에 상수 `REASON_DISARM_FAILED = 13`과 `REASON_EXTERNAL_DISARM = 14`를 더한다(고정 전의 계약 변경), 1a `sitl`은 MCAP을 올리지 않는다, Lichtblick은 1.30.0이다("2.5.2"는 Caddy label), LAND 중 취소도 Hold다, ros-ws 이미지 key가 바뀐다, 스모크는 노드 없이 돈다, PR이 여섯 개다.
