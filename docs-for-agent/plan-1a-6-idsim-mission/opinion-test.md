# 1a 6단계 의견서: test-engineer

작성: 2026-11-11, 의견 수집 단계. 구현하지 않았고 실측도 하지 않았다(문서와 코드 읽기만). 숫자 중 [추정]은 근거 없는 감이므로 구현 중 실측으로 바꿔야 하고, [근거]는 문서나 코드의 출처가 있다.

읽은 것: roadmap Phase 1a 6, 7번과 완료 기준, architecture.md 테스트 자동화와 CI 절, smoke-test.md 원칙, `tests/support/`(stack.py, receive.py 등), `tests/smoke/check_px4.py`, `tools/stack.sh`, 생성된 compose의 `runner` 서비스, `tools/ci/lint.sh`의 px4-api 검사, `.github/workflows/unit.yml`, plan-1a-5 decisions.md의 MissionEvent, 수락 정책, 취소 절.

## 0. 먼저 architect에게 올릴 문서와 현실의 충돌 하나

architecture.md는 "pytest fixture가 `docker compose up --wait`로 스택을 올리고, pytest는 `ros-ws` 컨테이너 안에서 실행한다"고 쓴다. 두 문장은 동시에 성립하지 않는다. `runner`는 ros-ws 이미지이고 docker CLI와 소켓이 없다. 소켓을 마운트하면 컨테이너가 호스트 root 권한과 같아져 3단계의 uid:gid 매핑 취지와 어긋난다.

권고: 역할을 둘로 나눈다.

- 호스트 쪽 드라이버 스크립트 `tests/sitl/run_sitl.sh`가 스택 올리기, pytest 실행, 산출물 수집, 스택 내리기를 맡는다. `tools/stack.sh up`을 그대로 재사용한다.
- pytest는 `runner`(ros-ws, `compose run --rm runner`)에서 돌며, fixture는 스택을 올리지 않고 `IDSIM_STACK_FILE`의 `stack.json`을 읽어 이미 떠 있는 스택에 붙고(attach) 준비 상태를 검증만 한다.

이렇게 하면 로컬과 CI가 같은 진입점(`run_sitl.sh`) 하나를 쓴다. architecture.md의 해당 문장은 "pytest fixture가 스택에 붙는다. 올리고 내리는 것은 드라이버 스크립트"로 고쳐야 한다. 이 변경은 architect 결정 사항으로 올린다.

## 1. 통합 테스트 구조

### 디렉터리

```
tests/sitl/
  run_sitl.sh          호스트 드라이버(up -> pytest -> collect -> down). 한 번 실행
  repeat.sh            N회 반복과 요약(4절)
  collect.sh           실패 산출물 수집(호스트에서 docker compose 사용)
  conftest.py          attach fixture, probe fixture, 실패 시 trace 기록 hook
  test_takeoff_land.py 정상 시나리오
  test_mission_rejects.py 무효 미션, vehicle_id 불일치(지상, 비행 없음)
  test_cancel.py       공중 취소(승격 조건은 3절)
tests/support/         판정 코드(2절). SITL과 리플레이가 같이 쓴다
```

`tests/sitl/`은 pytest 마커 `sitl`을 달고, 기본 `pytest tests/`에서는 제외한다(스택이 없으면 수집 단계에서 건너뛰는 것이 아니라 마커로 명시 제외. 조용한 skip은 쓰지 않는다).

### 스택 생명주기

- scope: 스택은 `run_sitl.sh` 한 번에 하나. pytest session scope의 attach fixture 하나가 stack.json을 읽고 (a) `/clock` 수신, (b) 필요한 토픽 발행자 수, (c) Executor lifecycle active, (d) 사전 상태(disarmed, 지상)를 검증한다. 하나라도 어긋나면 모든 테스트를 건너뛰는 것이 아니라 session 실패(setup error)로 보고한다.
- 시나리오는 스택 하나를 공유한다. 비행 상태가 다음 시나리오에 새는 것을 막으려고 순서를 고정한다: 지상 시나리오(무효 미션, id 불일치) -> 정상 비행 -> 취소 비행(마지막에 `[LAND]` 한 항목 미션으로 정리하고 disarm 확인). 각 테스트 시작 전에 `ground_idle` 사전조건(disarmed N회 연속, 지상)을 단정하며, 어긋나면 그 자리에서 실패한다(앞 테스트의 잔재를 숨기지 않는다).
- 시나리오마다 스택을 새로 올리면 정확히 독립적이지만 up --wait 시간(아래 [추정])을 시나리오 수만큼 곱한다. 대신 반복 검증(4절)이 매번 스택을 처음부터 올리므로 "콜드 스택에서의 독립 실행"은 거기서 얻는다.
- run_id: `tools/stack.sh up`이 `artifacts/runs/<UTC시각>-k<k>/`를 만든다. 드라이버는 이 경로를 stdout에서 받아 쓰고 그 아래 `sitl/`에 pytest 산출물을 둔다. 반복 실행은 실행 id가 서로 달라 겹치지 않는다. 스택 번호 k는 `IDSIM_STACK_INDEX`를 따른다(CI는 0).
- `runner` 실행: `docker compose -p idsim-<k> -f <run>/compose.yaml --profile tools run --rm runner python3 -m pytest tests/sitl ...`. runner는 `bridge` healthy에 의존한다. 노드 서비스(Executor)가 어느 서비스에서 도는지는 ros2/devops 결정이며, 테스트는 서비스 이름을 하드코딩하지 않고 `stack.json`의 `services`에서 읽는다. 테스트가 쓰는 노드 이름과 lifecycle 서비스 경로는 stack.json 또는 params에 싣기를 요청한다(식별자를 다시 계산하지 않는다는 기존 규칙과 같다).
- 빌드: runner에서 `idsim_interfaces`, `px4_msgs`를 import하려면 install 공간이 필요하다. `run_sitl.sh`는 시작 시 `tools/ros_ws.sh build`를 선행 호출하거나, 빌드 산출물이 없으면 명시적으로 실패한다. CI에서는 devops의 step이 먼저 빌드한다.

### 실패 시 수집할 산출물

모든 수집은 호스트의 `collect.sh`가 한다(pytest가 docker를 못 부르므로). 성공해도 요약과 trace는 남기고, 아래 전체 수집은 실패(setup error 포함)일 때 한다.

1. `docker compose ps -a` 결과(종료 코드 포함)와 서비스별 `compose logs --no-color --timestamps`.
2. PX4 ULog. `px4-1/` 바인드 마운트의 `log/`가 이미 실행 디렉터리에 있다. ULog는 정상 종료 때 닫히므로 수집 전에 `docker compose stop -t 10 px4-N`을 먼저 부른 뒤 복사한다(실행 중 파일 잘림 방지). 이 순서는 px4-engineer 확인 필요.
3. ROS 로그. 이미 `artifacts/runs/<id>/ros_log/`에 있다.
4. 판정 trace(`sitl/trace.jsonl`): probe가 받은 vehicle_status, vehicle_local_position, MissionEvent, feedback의 요약과 이정표(milestone) 이름, 모두 `/clock` 시각 포함. MCAP가 없으므로(rosbag2는 Phase 2) 이것이 1a의 사후 분석 기록이다. 원자료를 다 남기지 않고 판정에 쓴 필드만 남긴다.
5. 그래프 스냅샷: 실패 시점의 토픽, 타입, 발행자/구독자 수와 QoS(`get_publishers_info_by_topic`). 디스커버리 문제를 사후에 구분하는 근거다.
6. `junit.xml`, `verdict.json`(시나리오별 통과/실패와 실패 분류), `stack.json`, 이미지 key.

## 2. 판정 코드와 `tests/support/` 배치

기존 `receive.py`(SpinThread, `hold_state`, `receive_once`)는 호출마다 구독을 만들고 spin하는 일회성 구조다. 통합 테스트는 여러 조건을 동시에 보고(고도 도달을 기다리면서 MissionEvent 순서도 검증) 과거 이력이 필요하므로, 장수명 probe로 한 단계 올린다. 기존 smoke는 그대로 두고(회귀 방지) 새 모듈이 `SpinThread`, `_wait`의 시계 주입 설계를 이어받는다.

| 모듈 | 내용 | rclpy 의존 |
| --- | --- | --- |
| `clock.py` | `SimClock`: `/clock` 구독, `now()`로 초 float, 호출은 스레드 안전. `receive.py`의 `clock` 인자에 그대로 꽂는다 | 있음 |
| `waiting.py` | `wait_until(pred, timeout_sim_s, clock, wall_cap_s)`, `hold_n(...)`. 판정 로직(순수 함수) | 없음 |
| `probe.py` | 장수명 노드 하나(session scope), 전용 스레드 executor. 토픽마다 최신 값, 이력 deque(sim 시각 포함)를 보관. 구독 QoS는 `qos_profile_sensor_data`(PX4 토픽), MissionEvent는 계약 QoS | 있음 |
| `judge.py` | "도달", "arm/disarm", "이정표 순서" 같은 조건 함수(메시지 -> bool, 이력 -> 판정). architecture.md의 "토픽에서만 읽는다"를 구현하는 곳. 리플레이도 같은 함수를 이력에 적용 | 없음(메시지 속성만) |
| `mission_client.py` | `ExecuteMission` action client 래퍼: 서버 대기, goal 전송, 접수 응답, feedback 수집, result 대기, cancel | 있음 |
| `events.py` | MissionEvent 수집과 짝 확인(접수 1, 종료 1, 순서, 값 대조) | 없음 |
| `trace.py` | trace.jsonl 기록기 | 없음 |

판정 함수(`judge.py`, `waiting.py`, `events.py`)를 rclpy 없는 순수 코드로 두는 것이 핵심이다. 라이브 probe와 리플레이(rosbag2 재생을 같은 probe가 받는다)가 이력 객체만 공유하므로 두 층이 같은 코드를 쓴다. 순수 부분은 단위 테스트(pytest, 호스트에서도 돈다)로 덮는다.

### `/clock` 기준 타임아웃

- 판정 시간은 전부 sim 시간. 폴링 간격만 벽시계 `time.sleep(0.05)`로 둔다(타임아웃 판단에는 쓰지 않는다. 기존 `_wait` 구조 유지).
- 시작 시각은 대기를 부른 순간의 `SimClock.now()`. `/clock`이 아직 안 왔으면(`None`) 대기를 시작하지 않고 즉시 `CLOCK_ABSENT`로 실패시킨다.
- 안전망: sim 시간 타임아웃만 쓰면 Gazebo가 멈췄을 때(`/clock` 정지) 영원히 끝나지 않는다. 그래서 대기마다 벽시계 상한(`wall_cap = sim 타임아웃 x 속도 여유 + 고정 여유`)을 두고, 넘으면 타임아웃과 다른 분류 `CLOCK_STALLED`로 실패한다. 이 상한은 판정을 느슨하게 하는 용도가 아니라 hang 방지이며 분류가 다르므로 원인이 섞이지 않는다. pytest-timeout(벽시계, 테스트당)도 최후 보호로 건다.
- sim 시간이 뒤로 가면(월드 리셋) 즉시 실패한다. 단위 테스트로 덮는다.
- 실패 분류(verdict 코드): `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_ABSENT`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`(드라이버가 up --wait 실패를 기록). 플래키 담당자 분배(4절)가 이 분류로 갈린다.

### "최신 상태 N회 연속"

기존 `hold_state`와 같은 정의를 쓴다: 조건을 만족하는 메시지가 N개 연속(거짓 하나가 나오면 0으로 복귀). 보강 두 가지.

- 이정표의 순서 보호. disarm 판정은 "ARMED를 본 뒤의 DISARMED N회"여야 한다. 테스트 시작 시점에 이미 DISARMED이므로 순서를 보지 않으면 vacuous 통과한다. 판정은 이정표 이력(`goal 접수 -> ARMED -> 고도 도달 -> LOITER 유지 -> nav_state가 land -> DISARMED -> 종료 사건`)을 sim 시각이 단조 증가하는지까지 단정한다.
- N의 단위는 메시지 수다. 메시지 주기는 토픽마다 다르므로(그리고 best-effort라 일부 손실되므로) N을 시간으로 환산하지 않고, 유지 구간이 필요한 곳(LOITER 시간)은 별도로 sim 시간 경과로 단정한다. N 기본값은 smoke와 같은 값에서 시작(px4와 확인).

### 도달 판정의 입력

- 고도: `vehicle_local_position`의 z(NED, 위쪽이 음수)와 goal의 TakeoffItem 고도. 기준 z0는 goal 전송 직전 지상에서의 값을 읽어 둔다(원점 고도에 의존하지 않는다). 유효 플래그(`z_valid`) 포함. 허용 오차는 px4-engineer가 "현실적 값"을 주기로 한다(요청 사항, 아래). 판정 코드에는 z 부호 처리 한 줄만 있고 좌표 변환 로직은 두지 않는다. tests/는 px4-api lint 대상이 아니지만(lint.sh 확인), 토픽 이름 정규식은 smoke의 `check_px4.py` 패턴(`^/(ns/)?fmu/out/<base>(_v[0-9]+)?$`)을 `tests/support`로 옮겨 재사용한다.
- arm/disarm: `vehicle_status.arming_state`. 비행 모드: `vehicle_status.nav_state`.
- 미션 완료: action result와 MissionEvent 종료 사건 둘 다. 서로 다르면 `EVENT_MISMATCH`(decisions.md가 Executor 단위 테스트로 묶겠다고 한 동일성을 통합에서 한 번 더 확인).
- setpoint 값은 노드 출력이라 판정 입력으로 쓰지 않는다. goal의 목표 값과 기체가 실제로 낸 위치만 비교한다(노드와 테스트의 오류 상관 방지).

### 구독-발행자 매칭 확인과 goal 전송

1. probe를 session 시작에 만들어 구독을 먼저 걸어 둔다(스택이 올라오는 동안 이미 맺어지게).
2. goal 전송 직전 gate: 각 구독 토픽의 `get_publisher_count() >= 1`, `/clock` 수신 중, action 서버 `wait_for_server`, Executor lifecycle active(`get_state` 서비스 호출), 사전 상태 확인. 어느 하나라도 시간 안에 안 되면 해당 분류로 실패한다.
3. 한계(중요): 구독 쪽 `publisher_count`는 발행자가 내 구독자를 아는지를 보장하지 않는다. MissionEvent는 VOLATILE이라 발행자가 내 구독자와 맺어지기 전에 나간 ACCEPTED는 영영 오지 않는다(logging 조건 2가 기록기에 대해 적은 것과 같은 문제). 완화: 구독은 session 시작에 걸어 goal보다 수십 초 앞서므로 현실적 위험은 작다. 그래도 "goal 접수 응답을 받았는데 ACCEPTED 사건이 없다"는 상황은 `EVENT_MISSING`으로 그대로 실패시키고 재시도하지 않는다(발생하면 QoS 계약 문제의 증거다).
4. 접수 확인은 goal 응답(accepted 여부)과 MissionEvent ACCEPTED 둘 다. 거절(reject)은 이 계약에서 쓰지 않으므로 거절이 오면 실패다.
5. 종료 확인: result 수신과 MissionEvent 종료 사건 수신을 모두 기다리고, 두 값(status, reason, items_completed, last_item_index, detail)을 비교한다. 종료 사건 없이 result만 오면 `EVENT_MISSING`.

## 3. 시나리오 목록과 1a 완료 기준

시간은 모두 [추정]이다(실측 없음, sim 시간 기준, 실시간 비율 약 1 가정). 구현 뒤 `trace.jsonl`의 이정표 sim 시각으로 교체한다.

| 시나리오 | 1a 완료 기준에 넣나 | 이유 | 시간 [추정] |
| --- | --- | --- | --- |
| A. 정상 `[TAKEOFF, LOITER, LAND]` | 넣는다 | roadmap 완료 기준 그 자체. 접수 -> arm -> 도달 -> LOITER 유지 -> land -> disarm -> SUCCEEDED, MissionEvent 접수/종료 짝, feedback의 phase가 앞으로만 진행 | EKF 수렴 대기 포함 1-3분 sim |
| B. 무효 미션(goto 항목 포함) | 넣는다 | roadmap 6번이 "goto, track_entity, rtl이 든 미션은 미션 무효로 끝낸다"고 못 박았다. 지상에서 끝나므로 비용이 거의 없다. ABORTED/INVALID_MISSION, 접수+종료 사건, 기체가 disarmed에 머문 것(N회 연속, 일정 sim 시간 동안 arm 안 됨), 비행 명령이 나가지 않은 것(arming_state 변화 없음) | 수 초 |
| C. `vehicle_id` 불일치 | 넣는다 | 이 계약에서 가장 비싼 실수를 막는 비교(decisions 쟁점 9). 통합에서는 action 배선과 params 주입(stack.json -> 노드)이 실제로 이어진 것을 확인한다. ABORTED/VEHICLE_ID_MISMATCH | 수 초 |
| D. 공중 취소 -> Hold 확인 뒤 CANCELED | 조건부 | roadmap 6번이 취소 의미 확정을 위한 Hold 실험을 6단계로 당겼고 7번 계약 고정 전에 반영하라고 했다. 이 시나리오가 그 실험의 반복 가능한 형태다. 아래 승격 조건 참조 | A와 같은 이륙 + 취소 + 정리 land, 2-3분 sim |
| E. BUSY(실행 중 두 번째 goal) | 미룬다 | 단위 테스트로 충분하고 통합에서 보려면 비행 하나가 더 든다. Phase 3 재배분과 함께 | - |
| F. 지상 취소(arm 상태에서 disarm 확인) | 미룬다 | 단위 테스트로 덮는다 | - |
| G. NOT_READY, failsafe, EXTERNAL_MODE_CHANGE | 미룬다 | 상태 주입이 필요해 SITL에서 재현이 어렵다. 단위 테스트(가짜 PX4)로 덮는다 | - |

D 승격 조건: px4-engineer가 Hold 실험 결과(failsafe 진행 중의 Hold 명령 동작, Hold 확인 타임아웃의 현실적 값)를 내놓고 architect가 취소 의미를 확정하기 전까지, D는 마커 `experimental`로 두고 완료 기준의 "3회 연속"과 CI `sitl` 필수 통과에서 뺀다(로컬 실행과 trace 수집은 한다). 확정 후 마커를 제거해 승격한다. 이는 판정 기준을 느슨하게 하는 것이 아니라 아직 설계가 확정되지 않은 시나리오의 편입 시점을 정하는 것이며, 이 결정은 architect에게 올린다. 만약 실험이 6단계 안에 끝난다면(roadmap 6번의 의도) 처음부터 A, B, C, D 넷을 완료 기준에 넣는 쪽이 낫다.

D의 판정: 고도 도달 후 cancel 요청 -> `nav_state`가 Hold로 N회 연속 -> result CANCELED(reason NONE) + MissionEvent CANCELED -> 이후에도 기체가 공중에서 Hold 유지(일정 sim 시간 고도 변화 허용 범위 안) -> 정리로 `[LAND]` 미션 전송 -> disarm. `[LAND]` 한 항목 미션이 유효한 미션 형태인지 ros2/px4가 확인해 주기 바란다(decisions의 "Fleet이 취소 뒤 land 항목 하나짜리 미션을 보낸다"와 일치).

전체 예상(PR 경로): 스택 기동 + A + B + C (+ D) = [추정] 8-12분 정도로 15분 목표(architecture.md) 안이나 여유가 크지 않다. 이미지 pull 시간(5절)이 지배 변수다.

## 4. "3회 연속 통과"의 실행, 기록, 플래키 대응

### 실행

`tests/sitl/repeat.sh [N=3]`가 `run_sitl.sh`를 N번 호출한다. 매 회: 이전 프로젝트 down -> 콜드 스택 up(stack.sh가 이미 항상 down 뒤 up) -> pytest -> 수집 -> down. 회마다 실행 id가 다르다. 반복 사이에 상태를 공유하지 않는다.

### 기록

`artifacts/runs/<repeat id>/repeat_summary.tsv` 한 줄 = 한 회: 회차, 실행 id, git commit과 dirty 여부, 이미지 key, 시나리오별 verdict와 분류, 이정표별 sim 소요, wall 소요, up --wait 소요, 종료 코드. 끝에 "연속 통과 N" 한 줄. 실패한 회의 실행 디렉터리는 지우지 않는다. 결과는 `docs-for-agent/progress.md`에 요약을 옮긴다(기록은 test-engineer 책임).

### 규칙

- "3회 연속"은 같은 commit, 같은 이미지 key에서 세 회 모두 통과다. 실패가 나오면 카운터는 0으로 돌아간다(고쳐서 다시 3회). 한 번 실패하고 두 번 통과한 것은 통과가 아니다.
- 재시도 금지. 로컬 스크립트와 CI 모두에서 pytest rerun 플러그인과 shell 재시도 루프를 쓰지 않는다. architecture.md도 `sitl` job을 PR당 1회, 재시도는 수동으로 한다고 적었다. 재시도는 플래키를 가리고 standalone에서 모델 잔존 문제를 만든다(smoke-test.md가 이미 같은 이유로 자동 재시작을 금지).
- 실패 분류에 따른 이관: `INFRA_UP`(up --wait 실패)은 devops 또는 해당 서비스 owner(로그가 가리키는 서비스), `NO_PUBLISHER`/`SERVER_ABSENT`/`EVENT_MISSING`은 ros2-engineer, `TIMEOUT_SIM`의 이정표 중 고도/모드 쪽은 px4-engineer, Executor 쪽은 ros2/px4 공동, `CLOCK_STALLED`/`CLOCK_ABSENT`는 sim-engineer. 넘길 때 증거(trace 해당 구간, 해당 서비스 compose logs, ULog, 그래프 스냅샷)를 함께 첨부한다.
- 테스트가 실패하면 결과를 그대로 보고하고, 통과시키려고 허용 오차나 N, 타임아웃을 늘리지 않는다. 바꿔야 하면 근거(실측 분포)와 함께 architect에 올린다.

### 타임아웃 값의 근거

감으로 정하지 않고 구성 요소로 쌓는다.

- 이륙 도달: (목표 고도 / 이륙 속도) + 가감속 여유. 속도는 SITL 파라미터에서 읽는다(px4가 값을 준다. `MPC_TKO_SPEED`류).
- EKF 수렴 대기: px4가 현실적 상한을 준다. 첫 수 회 실행에서 실측.
- 착륙: (고도 / 착륙 속도) + 여유. disarm 확인은 자동 disarm 파라미터와 `COM_DISARM_LAND` 상호작용을 px4와 확인.
- 처음에는 이 계산값의 약 2-3배로 시작해 측정 분포를 `repeat_summary.tsv`에 쌓고, 여유 비율(소요 / 타임아웃)이 1/2을 넘기 시작하면 플래키 위험 신호로 다룬다. 줄이는 방향의 조정은 근거가 쌓이면 가능하나 늘리는 방향은 위 규칙대로 architect 경유.
- 배속은 쓰지 않는다(smoke-test.md: `PX4_SIM_SPEED_FACTOR`는 rcS가 손실 타임아웃 파라미터를 덮어쓴다). 1이하로 내리는 옵션은 CI에서 느리면 그때 검토.

## 5. CI `sitl` job 요구사항과 devops 경계

### 가능성과 위험

- GitHub hosted 공개 runner는 4 vCPU, 16 GB(architecture.md 근거). 개발 PC가 4 vCPU, 7 GB이고 스모크가 이 위에서 통과했으므로 CPU와 메모리 여유는 개발 PC보다 낫다 [근거: progress.md]. headless gz 서버 + PX4 1대 + 노드는 GUI와 센서 렌더링이 없어 가능성이 높지만, GitHub runner에서의 실제 성공은 [미검증]이다. 첫 실행이 곧 실험이다.
- 디스크: 이미지 합계가 압축 해제 기준 약 9GB(px4 3.07, sim-base 2.98, ros-ws 1.99, ros-base 0.84, xrce 0.15)이고, build 워크플로에 "free runner disk" step이 이미 있다. sitl job도 필요한지 devops가 판단.
- pull 시간: 이미지 5종 pull이 시간 예산을 크게 좌우한다 [추정: 수 분]. 필요한 이미지만 받아야 한다(xrce-agent, sim-base, px4, ros-ws. ros-base는 베이스라 불필요). GHCR 패키지가 Public이 되기 전에는 포크 PR이 못 받는다(progress.md 다음 작업 1번).
- 15분 목표(architecture.md)는 job 전체 시간이므로 pull + build(`tools/ros_ws.sh build`) + up + 테스트 + 수집이 합쳐서 들어가야 한다. 초과 위험은 pull과 up이다.
- 3대 nightly는 6단계 범위 밖.

### 경계

| 항목 | 담당 |
| --- | --- |
| `.github/workflows/sitl.yml`: trigger(PR, main), concurrency, timeout-minutes, 이미지 pull, 디스크 확보, ros_ws build 호출, `run_sitl.sh` 호출, `if: always()` 아티팩트 업로드, 보존 기간, step summary | devops |
| `tests/sitl/run_sitl.sh`, `collect.sh`, `repeat.sh`, pytest, 판정 코드, verdict 분류, junit과 요약 형식 | test |
| 업로드할 경로 목록(`artifacts/runs/<id>/`의 어떤 파일을 올리는가) | test가 `run_sitl.sh`의 마지막 줄 stdout으로 실행 디렉터리 경로를 내고 devops는 그 경로를 통째로 올린다. 크기가 크면 test가 `sitl/` 하위만 올리도록 알려 줌 |
| 재시도 없음, PR당 1회 | 둘 다 지킨다(devops의 워크플로에 retry 없음) |

CI는 `run_sitl.sh` 한 명령만 호출하고 로컬과 같다(`unit.yml`이 `tools/ros_ws.sh ci` 한 줄인 것과 같은 방식). 워크플로가 시나리오 세부를 알지 않게 한다.

## 6. 노드 단위 테스트(PX4 없이)

architecture.md는 "미션 상태기: ROS 없이 시계와 입출력 포트를 주입한 순수 클래스"를 단위 층의 대상으로 적었다. 이를 6단계의 가장 큰 테스트 투자처로 둔다. SITL은 최소로 유지하고 분기는 여기서 덮는다.

### 순수 클래스 단위 테스트(C++, GoogleTest)

주입: 시계(수동으로 진행하는 가짜), 입력 포트(vehicle_status, local position, command ack를 스크립트된 시퀀스로 먹임), 출력 포트(발행된 setpoint, offboard_control_mode, vehicle_command를 기록). 덮을 것(예):

- 정상 경로 전체와 단계 순서. 모드 전환 전 최소 10회 setpoint 발행, 20 Hz 간격(sim 시간), 모든 단계에서 setpoint 지속 발행.
- 검증: 빈 미션, 첫 항목이 TAKEOFF가 아님, LAND가 마지막이 아님, goto/track_entity/rtl 포함, 비정상 고도(음수, NaN) 등 -> INVALID_MISSION. vehicle_id 불일치. BUSY(실행 중 두 번째), 접수 정책(항상 수락 후 abort).
- 거부 경로: arm 거부 ack -> ARM_REJECTED, 모드 전환 실패 -> MODE_SWITCH_FAILED, 고도 도달 타임아웃 -> ITEM_TIMEOUT, 외부 모드 변경 -> EXTERNAL_MODE_CHANGE, failsafe -> FAILSAFE, 상태 미수신 -> LINK_LOST, EKF 미수렴 -> NOT_READY/PRECONDITION_FAILED.
- 취소: 공중(Hold 확인 -> CANCELED, Hold 미확인 타임아웃 -> Land 명령 + ABORTED/MODE_SWITCH_FAILED, 상태 없음 -> LINK_LOST), 지상(arm 상태면 강제 아닌 disarm 확인).
- 상태-사유 대응표: SUCCEEDED/CANCELED면 reason NONE, ABORTED면 NONE 아님(decisions가 요구).
- MissionEvent와 result의 동일성(status, reason, items_completed, last_item_index, detail)과 사건 수(접수 1, 종료 1, 이른 abort도 둘 다).
- 속성 테스트 후보: 임의의 입력 시퀀스에서 종료 사건은 최대 1회, reason 대응표 위반이 없다.

### 노드 배선 테스트(PX4 없이, 최소)

action 서버 래퍼, lifecycle 전이, 토픽 이름과 QoS(PX4 토픽 BEST_EFFORT 구독 등)는 순수 클래스로는 못 덮는다. 작은 rclcpp GoogleTest 하나(`idsim_mission/test/`, `colcon test`로 unit job에서 돈다)로: 가짜 PX4 발행자 노드를 같은 프로세스에서 띄워 `vehicle_status`/`vehicle_local_position`을 스크립트로 발행하고(`idsim_common`의 토픽 기술자와 QoS를 써서 발행 이름과 타입을 맞춘다), Executor를 active로 전이시킨 뒤 `[TAKEOFF, LOITER, LAND]`를 처리하는 한 경로와 무효 미션 한 경로만 확인한다. 이 테스트는 "배선이 이어졌다"만 보고 분기 로직은 순수 클래스 테스트에 맡긴다.

가짜 PX4 발행자를 `tests/support/`의 Python(rclpy) 버전으로도 만들어 둘지는 선택 사항이다. 리플레이 쪽(Phase 2)과 Fleet 단위/리플레이 테스트(Phase 3)가 재사용할 수 있으나 지금 필요한 것은 아니다. 6단계에서는 C++ gtest 안의 것만 만들기를 권한다.

범위 밖(6단계 단위 테스트에서 하지 않음): PX4 모드 전환의 실제 동작, 파라미터 효과, EKF. 이는 SITL이 확인한다.

## 요청 사항(다른 담당자에게)

- px4-engineer: (1) 도달 허용 오차, N 기본값, 이륙/착륙 속도와 상한 시간 근거값. (2) 자동 disarm 파라미터와 disarm 확인에 필요한 최대 시간. (3) ULog 수집 전 `compose stop`이 정상 종료를 보장하는지. (4) Hold 실험 일정과 결과가 D 승격의 선행 조건임.
- ros2-engineer: (1) Executor lifecycle 서비스 경로와 노드 이름을 stack.json 또는 노드 params로 싣기. (2) MissionEvent QoS 최종값과 ACCEPTED 손실 가능성의 재확인. (3) `[LAND]` 한 항목 미션의 유효 여부. (4) 가짜 PX4 발행자를 gtest 안에서 만들 때 쓸 `idsim_common` API.
- devops-engineer: (1) `sitl` job의 디스크, pull 대상 이미지, 시간 예산 합산. (2) Executor 노드 서비스 위치와 healthcheck(스택 `up --wait` 안에 lifecycle active가 들어가는지). (3) 아티팩트 경로 규칙과 보존 기간.
- architect: (1) 0절의 문서 수정(fixture는 attach, 올리기는 드라이버). (2) D 시나리오의 승격 시점. (3) 판정 기준(허용 오차, N, 타임아웃)을 바꿔야 할 때 올리는 절차.
