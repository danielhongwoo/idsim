# Phase 1a 5번 작업 idsim_interfaces 작업 계획

작성 2026-11-10, 같은 날 확정 개정. 설계 결정은 `decisions.md`에 있고 확정본이다(reviewer 검증, ros2-engineer 추가 실측, 사용자 결정 2건 반영). 패키지 파일(A, B), 테스트 수 단정(C), owner 검토 반영, 문서 반영(D)까지 끝났다. 남은 것은 reviewer의 문서 확인, PR, CI, 사용자 머지다. 브랜치는 `feat/1a-5-idsim-interfaces`다.

## 진행 상태 (2026-11-10)

| 단위 | 상태 |
| --- | --- |
| 설계 결정 | 확정(`decisions.md`). reviewer 재확인 완료(구현 착수 가능). 비차단 6건을 `decisions.md`에 반영했다 |
| A | 완료. 정의 11개가 `decisions.md` 쟁점 8과 직접 정의 단위로 같다. ros2-engineer 승인 |
| B | 완료. 결함 주입 네 가지 확인(architect). test-engineer 승인. 검토 뒤 가드(펼친 정의의 최상위 줄 == 직접 정의)와 갱신 모드 경고를 더했다 |
| C | 완료(devops-engineer). 패키지마다 테스트 결과 1건 이상을 단정한다. test-engineer 승인 |
| owner 검토 | 완료. ros2 승인(권고 4), test 승인(권고 2), sim 승인(문서 조건 1, 보완 2), ops 조건부(조건 1), logging 조건부(조건 3). 조건은 모두 반영했고 권고는 반영하거나 넘김 목록으로 보냈다(받지 않은 것 없음). 필드와 상수는 바뀌지 않았고 golden 세 종류도 그대로다. 처리 표는 `decisions.md`의 "5단계 PR owner 검토 반영" |
| D | 완료. `docs/architecture.md`(인터페이스 계약 절, 기체 식별 절, 테스트 절), `docs/roadmap.md`(16행, 1a 목표, 1a 5-7번, 1b 2번과 완료 기준, Phase 2 1, 3, 5번과 완료 기준, Phase 3 3번, 리스크 표 네 줄), `docs-for-agent/file-ownership.md`(계약 golden의 승인 주체). reviewer 확인 대기 |
| 검증 | `tools/ros_ws.sh ci` 통과(148 tests: `idsim_common` 109, `idsim_interfaces` 39), `tools/ci/lint.sh all` 통과, 문자 집합 검사 통과 |

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | architect 결정 11건(확정본), 확정 개정 요약(reviewer 필수 5건과 권고 8건의 처리), 메시지와 action의 필드 목록, 담당자별 구현 지시, 넘김 목록, 사용자 결정 2건의 결과 | 계약. 구현은 이 문서를 따른다 |
| `opinion-ros2.md` | ros2-engineer 의견과 실측(rosidl 빌드, 예약어, type hash가 바뀌는 조건, 토픽 이름 검증) | 근거 |
| `opinion-sim.md` | sim-engineer 의견과 실측(스크립트 궤적 Actor의 pose, `dynamic_pose/info` segfault, pose/info 주기) | 근거 |
| `opinion-ops.md` | ops-service-engineer 의견(`VehicleState`와 `ExecuteMission`의 소비자 요구, proto와 JSON 규칙) | 근거 |

재질문 답 네 건(ros2, ops, sim, px4)은 파일로 두지 않고 `decisions.md`의 "재질문 결과 요약"에 옮겼다. reviewer 검증 보고와 ros2-engineer 추가 실측 보고도 파일로 두지 않고 결론을 `decisions.md`에 옮겼다. 의견서의 권고 중 `decisions.md`와 다른 것은 `decisions.md`가 우선한다(공통 토픽, 평평한 필드, 공분산, `attempt`, `link_ok`, 발행 KEEP_LAST 1은 채택하지 않았다).

근거 파일에 나오는 scratchpad 경로와 실험 디렉터리는 당시 환경의 임시 파일이라 저장소에 없다. 결론과 인용된 실측값만 쓴다.

## 범위

5단계가 만드는 것은 rosidl 전용 패키지 `ros_ws/src/idsim_interfaces/`와 그 계약 테스트, 그리고 `tools/ros_ws.sh`의 단정 변경이다. 노드, QoS 함수, 대조 함수, proto 파일은 만들지 않는다.

고정 시점은 `decisions.md`의 "고정 시점과 범위 구분" 표에 있다(사용자 결정 1). 요약하면 1a 완료에 공통 규칙, `ExecuteMission`, `Mission`, `MissionItem`, `TakeoffItem`, `LoiterItem`, `YawSetpoint`와 TAKEOFF, LOITER, LAND의 의미. 1b 완료에 `TargetState`, `GoToItem`, `TrackEntityItem`과 GOTO, TRACK_ENTITY, RTL의 의미. Phase 2 완료에 `VehicleState`와 `MissionEvent`(`MissionEvent`는 사용자 결정 1의 기준의 예외이고 이유는 `decisions.md`의 고정 시점 절에 있다). "고정"의 단위는 파일의 직접 필드와 상수다. 정의는 전부 5단계에서 만든다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| A. 패키지와 정의 | architect(검토 ros2-engineer) | `package.xml`, `CMakeLists.txt`, `msg/` 10개와 `action/` 1개(`decisions.md` 쟁점 8, 11). 필드 이름, 타입, 순서, 상수 값은 결정 그대로 옮긴다 | 없음 |
| B. 계약 테스트 | architect(승인 test-engineer) | `test/test_contract.py`와 `test/golden/`(type hash golden, 펼친 정의 golden, 직접 정의 golden, 상수 검사. 쟁점 10), ament lint 3종(xmllint, lint_cmake, copyright) | A |
| C. 테스트 수 단정 | devops-engineer(승인 test-engineer) | `tools/ros_ws.sh test`의 단정을 패키지별로(쟁점 6) | 없음. A와 병렬 |
| D. 문서 | architect | `decisions.md`의 "문서 반영 목록"(`docs/architecture.md`, `docs/roadmap.md`, `docs-for-agent/file-ownership.md`) | A-C, reviewer 재확인 |

`docs/interface.md`는 7단계 몫이라 만들지 않는다. `progress.md`는 호출한 쪽이 갱신한다. `stack.json`의 `vehicle_id`는 6단계 몫이라 이번 PR에 넣지 않는다.

## 진행 순서

1. (완료) reviewer가 `decisions.md`를 검증했다. 필수 5건과 권고 8건을 확정본에 반영했다.
2. (완료) ros2-engineer가 accept 뒤 abort와 rosbag2의 action 기록을 실측했다. 사용자 결정 2건을 받았다.
3. (완료) A와 C를 병렬로 한다. A 뒤에 B.
4. (완료) `tools/ros_ws.sh ci`를 로컬에서 돌린다. 두 패키지 모두 결과가 1건 이상이어야 한다.
5. (완료) 관련 owner 검토(아래 "검토")와 reviewer 재확인. reviewer는 확정본이 필수 5건을 닫았는지와 구현이 쟁점 8과 같은지를 본다.
6. (D 완료) D(문서 반영)를 한다. reviewer가 문서 변경을 확인한 뒤 PR, CI 통과, 사용자 머지.

PR은 하나로 하고 커밋은 담당자 소유 단위로 나눈다. 스택을 올리는 작업은 없다.

## 검토

- ros2-engineer: A의 rosidl 구성과 의존, 이름 상수의 C++ 사용 규칙, 정의가 `idsim_common`의 관례(yaw, 프레임)와 맞는지.
- ops-service-engineer: `VehicleState`, `ExecuteMission`이 재질문에서 수용한 조건(accept 뒤 abort와 `reason` 값, 발행 중단 불변식)을 담았는지.
- sim-engineer: `TargetState`의 계약 문장 셋(쟁점 5)과 id 규칙.
- logging-engineer: `MissionEvent.msg`의 필드가 기록물 인덱스의 요구와 맞는지(5단계 토론에 들어오지 않은 첫 소비자다).
- devops-engineer: C의 구현. `stack.json`의 `vehicle_id`(6단계)에 이견이 있으면 이 PR에서 말한다.
- px4-engineer: `MODE_*` 묶음, 취소 의미, takeoff와 land의 의미. 읽기 전용 검토다.
- test-engineer: golden 갱신 절차, 패키지별 단정 규칙, 결함 주입 확인.
- reviewer(재확인): 첫 검증의 결과는 `decisions.md`의 "확정 개정 요약"에 있다. 재확인에서 볼 것.
  - 필수 5건이 확정본에서 닫혔는지. 특히 "고정"의 정의와 직접 정의 golden이 전파와 직접 변경을 실제로 가르는지(결함 주입).
  - `MissionEvent.msg`가 roadmap Phase 2의 기록물 인덱스 완료 기준을 성립시키는지, 고정 시점(Phase 2 완료)이 사용자 결정 1의 기준의 예외로 이유와 함께 적혀 있는지.
  - Hold 실험이 1a 고정 전에 잡혀 있고 세 곳(쟁점 9, 넘김 목록, 이 문서)의 시점이 같은지.
  - `stack.json`의 `vehicle_id`가 "식별자를 `fleet.yaml` 밖에서 파생하지 않는다"와 결정 (u)에 맞는지.
  - 구현된 정의가 쟁점 8과 필드 단위로 같은지, 문서 반영(D)이 사용자 결정 2건과 같은지.

## 완료 기준

- `tools/ros_ws.sh ci`가 로컬과 CI unit job에서 통과하고, `idsim_common`과 `idsim_interfaces` 각각 테스트 결과가 1건 이상이다.
- 한 패키지의 테스트를 0건으로 만들면 `tools/ros_ws.sh test`가 종료 코드 1로 끝나고 실패 메시지에 패키지 이름이 나온다(test-engineer 확인).
- 계약 테스트의 결함 주입: 필드 타입을 바꾸면 type hash golden과 직접 정의 golden이, 상수 값을 바꾸면 펼친 정의 golden과 직접 정의 golden이, `TYPE_*`를 더하면 상수 검사가 실패한다. `GoToItem`의 필드를 바꾸면 `MissionItem`의 type hash golden은 실패하고 직접 정의 golden은 통과한다(전파와 직접 변경이 갈린다).
- 정의가 `decisions.md` 쟁점 8과 필드 단위로 같다(reviewer가 `ros2 interface show` 출력과 대조). `MissionEvent.msg` 포함 msg 10개, action 1개.
- `tools/ci/lint.sh all` 통과(문자 집합, ruff, `px4-api`).
- 문서 반영 목록 반영. `progress.md`는 호출한 쪽이 갱신한다.


## 범위 밖(넘길 곳)

`decisions.md`의 "넘김 목록"이 정본이다. 요약.

- 6단계: `ExecuteMission` action 서버(수락 정책, 취소, `MissionEvent` 발행), Hold 실험과 그 결과의 계약 반영(1a 고정 전), `stack.json`과 params의 `vehicle_id`와 대조 함수, 항목 분류 함수와 테스트, takeoff와 land의 판정 값, fixture의 프로세스 종료 방식(SIGTERM 또는 프로세스 그룹).
- 7단계: `docs/interface.md`(파일별 고정 시점 표 포함).
- 1b: EKF 원점 오차 실측(첫 작업), world ENU <-> 로컬 NED 변환 함수, 상태 토픽 QoS 함수, `TargetId`, `world.origin` 필수화, 표적 생산 방식 결정, `dynamic_pose/info` 금지 검사, 스폰 pose를 독립 기준으로 쓰는 판정.
- Phase 2: `MODE_*`와 `WARN_*` 대응표, Collector 불변식, `mission_event` 기록과 인덱스, replay에서 `vehicle_state` 제외.
- Phase 3: Fleet의 발견 방식, proto 파일, action 서버 `result_timeout`, 취소 뒤 Hold로 남은 기체의 처리.

## 사용자 결정과 알림

- 결정(2026-11-10, 둘 다 architect 권고안 채택): 계약 고정 시점을 나눈다. 6단계 노드는 `ExecuteMission` action 서버로 `[TAKEOFF, LOITER, LAND]` 미션을 받는다.
- 남은 사용자 결정은 없다.
- 알림: 취소 뒤 동작은 Hold(확인 실패 때 Land 명령, 지상 arm 상태는 disarm), `MissionEvent.msg` 추가와 고정 시점(Phase 2 완료. 사용자 결정 1의 목록에 없던 항목이고 그 기준의 예외다. 1a 완료로 당길 수 있다), `stack.json`의 `vehicle_id`, `world.origin`은 1b부터 필수, "표적 엔티티는 Gazebo Actor" 결정은 1b 착수 때 재토론, 이미지와 의존 변경 없음.
