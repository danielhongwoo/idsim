# 1a 6단계 idsim_mission 설계 결정

1a 6단계(이륙-호버-착륙 노드와 통합 테스트)의 계약과 설계 결정이다. 구현은 이 문서를 따른다. 지금 유효한 것만 적는다. 결정의 경위(토론, 검토, 승인 내역)는 커밋 메시지와 PR 본문에 있다. 작업 단위와 완료 기준은 같은 디렉터리의 `README.md`에, `docs/`에 반영할 것은 아래 "문서 반영 목록"에 있다.

표기: [실측]은 담당자가 스택이나 이미지에서 직접 확인한 것, [소스]는 PX4 v1.17.0 원문이나 설치된 패키지 원문, [추정]은 확인하지 않은 판단이다. 실측은 경우마다 1-4회이고 16 vCPU 호스트 한 대에서 했다. "[실측] P3a"는 P3의 첫 작업이던 런타임 확인 실험(ros2-engineer)이다. 실측에 붙은 글자는 px4-engineer의 실험 이름이다(시나리오 A-D, T와 다르다). B는 offboard 손실 failsafe 진행 중의 Hold, C는 NAV_LAND 착륙 중의 Hold, G는 처음부터 지상 setpoint로 arm, H는 목표점으로 arm한 뒤 지상 setpoint로 바꿈, K는 목표점을 유지한 채 disarm, X2a는 이륙 램프 중의 Hold, X2b는 0.5 m 호버에서의 Hold, X3은 이륙한 적 없는 지상 armed에서의 발행 중단(미실측)이다. disarm 실험은 공중과 지상, 이미 disarm된 기체에 강제가 아닌 disarm을 보낸 것이다.

용어: 이 문서의 "공중"은 `vehicle_land_detected.landed == false`, "지상"은 `landed == true`를 뜻한다. 기체의 높이가 아니라 PX4의 착륙 판정이다. position만 쓰는 Offboard나 Hold에서는 이륙 램프가 시작된 뒤 기체가 땅에 닿아 있어도 `landed`가 false로 남는다([실측] H, X2a). 분기는 이 뜻으로 맞게 동작한다(공중 분기의 Hold는 받아들여진다).

사용자 결정

- U1: 시나리오 D(공중 취소)와 `[LAND]` 한 항목 미션은 1a 필수다. D가 "3회 연속"과 CI 필수에 들어가고 상태기에 PREPARING 분기 하나가 는다.
- U2: `sitl`은 PR 머리 커밋마다(draft와 문서만 바뀐 PR 제외, 옛 실행 취소)와 main push에서 돈다. lint와 unit의 trigger도 `pull_request`와 `push: main`이다. 판단 재료의 한계: 실행당 10-13분은 실측이 없는 추정이고, 공개 저장소의 표준 hosted runner가 과금되지 않는다는 것은 GitHub 문서 원문을 다시 확인하지 않은 이해다. 첫 실행들의 실측이 이 가정과 다르면 다시 올린다(쟁점 11의 올림 기준).
- U3: 공중에서 끝나는 미션(마지막 항목이 LAND가 아님)의 종료 동작은 1b에서 정한다. 1a 노드는 그런 미션을 INVALID_MISSION으로 끝낸다. 5단계 사용자 결정 1의 고정 범위("1a 완료에 `ExecuteMission`")에서 이 조각을 뺀 것이다.
- U4: replay job의 trigger는 replay job을 만드는 Phase 2에서 정한다. `docs/architecture.md` 테스트 층 표의 리플레이 행과 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"는 그때 고친다.
- 남은 확인 요청(결정이 아니다): GHCR 패키지 다섯과 buildcache가 Public으로 설정되어 있는지 패키지 설정 화면에서 확인한다. 익명 조회는 200이었다.

## 결정 요약

| 쟁점 | 결정 | 계약 변경 |
| --- | --- | --- |
| 1. 스택 기동 주체 | 호스트 wrapper `tests/sitl/run_sitl.sh`가 올리고 내린다. pytest는 `runner` 안에서 돌고 fixture는 붙기만 한다 | 없음(architecture.md 문장 수정) |
| 2. 노드 실행 형태 | 기체당 서비스 `ops-N`. 정적 launch로 `component_container_isolated`에 Executor 컴포넌트를 load하고, 노드가 스스로 configure와 activate를 건다(`lifecycle.self_start`. 컨테이너 autostart는 launch_ros 0.26.13에서 동작하지 않는다). params는 `params/ops-N.yaml`의 `/**`에 식별값만. 스모크는 `--infra-only` | 없음 |
| 3. 5단계 계약 | 의미 문장 일곱(M1-M7)을 고치거나 더하고 상수 둘(`REASON_DISARM_FAILED = 13`은 M5, `REASON_EXTERNAL_DISARM = 14`는 감시 표의 지상 DISARMED 행)을 더한다 | M1-M7은 의미 변경(고정 전), golden 무변경. 상수 둘은 `ExecuteMission`의 직접 정의와 펼친 정의 golden에 두 줄씩 들어가 있다. type hash 무변경 |
| 4. PX4 실측 사실 | 전부 채택. 전이 표로 고정 | 의미 변경(고정 전), golden 무변경 |
| 5. `idsim_common` 추가 | `VehicleId`, vehicle params 해석, Options overload, position setpoint 헬퍼, 사건 QoS, 빌더 `make` | 없음 |
| 6. `idsim_mission` 소유 | ros2-engineer. `px4/` 디렉터리 셋만 px4-engineer. 상태기 전이 표는 px4-engineer 필수 승인 | 없음(file-ownership.md) |
| 7. `MissionEvent` QoS | VOLATILE 유지. goal 전 gate는 자기 구독의 `get_publisher_count()` | 없음 |
| 8. 테스트의 /fmu/in | Python, `tests/support/px4_raw.py` 한 모듈만. 별도 C++ 노드는 두지 않는다 | 없음 |
| 9. 시나리오 | B, C, A, D, T 순서. 다섯 모두 1a 필수(U1). `[LAND]` 한 항목 미션 지원 | 없음 |
| 10. 타임아웃 | px4 값 채택. 벽시계 가드는 `CLOCK_STALLED`와 `CLOCK_SLOW`로 분류 | 없음 |
| 11. CI `sitl` | `sitl.yml`, timeout 30분, 재시도 없음. PR 머리 커밋마다와 main push(U2) | 없음 |
| 12. viz | foxglove_bridge는 단독 선행 이미지 PR. 화이트리스트는 네임스페이스 접두. Lichtblick 1.30.0 digest. recorder는 1a에 두지 않는다 | 없음 |
| 13. PR 분할 | P0-P5 여섯 개. README.md | - |

## 계약과 golden (먼저 읽을 것)

- 필드는 바꾸지 않는다. type hash golden(`type_hashes.txt`)은 5단계 그대로다([실측] 상수는 hash에 들어가지 않는다).
- 6단계가 `ExecuteMission.action`의 result에 더한 상수는 둘이다. `uint8 REASON_DISARM_FAILED = 13`(M5)과 `uint8 REASON_EXTERNAL_DISARM = 14`(감시 표의 지상 DISARMED 행. 근거는 쟁점 3). 두 상수는 `golden/direct/action/ExecuteMission.txt`와 `golden/action/ExecuteMission.txt`에 두 줄씩 들어가 있다. 그 밖의 golden은 5단계 그대로다.
- 나머지(M1-M7과 전이 표)는 의미 변경(고정 전)이고 golden은 바뀌지 않는다. 의미 문장은 `ExecuteMission.action`의 주석에 있다. golden 세 종류는 모두 주석을 빼고 비교한다([소스] `idsim_interfaces/test/test_contract.py`의 `_strip_comment`와 `_normalize`, `ros2 interface show --no-comments`). 주의: 줄 끝 주석에 그 줄 앞부분과 같은 문자열을 쓰면 `ros2 interface show`가 줄을 잘라 `test_contract.py`의 가드(최상위 줄 == 직접 정의 단정)가 실패한다. 여러 줄에 걸친 의미 주석은 줄 전체 주석으로 쓴다.
- 의미 변경을 반영하는 곳은 `ExecuteMission.action`의 주석, 7단계 `docs/interface.md`, `docs/architecture.md` 인터페이스 계약 절이다. `docs/interface.md`는 7단계에 만들어지므로 그때 반영한다.
- 이 변경의 절차 근거(5단계 `decisions.md`): 110행 "상수는 고정 전후 모두 추가만 한다. 상수의 의미는 그 상수를 처음 쓰는 소비자가 생기는 묶음과 함께 고정된다", 112행 "고정 전에는 첫 소비자의 구현에서 드러난 문제가 변경 사유로 인정된다", 598행(필드와 의미의 변경 규칙. 고정 여부는 파일 단위, 판정은 직접 정의 golden), 630행(지상 취소에서 disarm이 거부되거나 확인되지 않을 때의 분기를 6단계 px4-engineer에 넘김), 680행(Hold 실패와 지상 disarm 정책은 6단계 실험 결과에 따라 1a 고정 전에 바뀔 수 있다고 사용자에게 알림). `ExecuteMission.action`은 아직 고정 전이고 첫 소비자(6단계 Executor)의 설계에서 드러난 분기다.
- M5에서 (가) "REASON_MODE_SWITCH_FAILED의 의미를 넓히고 뒤에 가르지 않는다"가 아니라 (나) 상수 추가를 고른 이유: 두 경우는 ABORTED 뒤의 기체 상태가 다르다. Hold 실패는 Executor가 Land를 보내 기체가 내려오는 중이고, 지상 disarm 실패는 기체가 지상에 arm 상태로 남는다. 읽는 쪽(Fleet, 운용자)의 다음 동작이 갈린다. (가)로 가면 1a에 고정된 뒤에는 "상수의 의미를 바꾸지 않는다"에 걸려 영영 가를 수 없다. 나중에 상수를 더하면 기존 상수의 의미가 좁아지므로 "나중에 더하면 된다"는 성립하지 않는다. 고정 전의 비용은 golden 두 줄뿐이다.
- 계약 golden이나 의미 주석이 바뀌는 PR에는 architect 승인이 필요하고 결정 근거는 PR 본문에 적는다(file-ownership.md).
- `last_item_index`의 "항목 시작 전 실패" 구분 필드(5단계에서 6단계로 넘긴 검토 항목)는 더하지 않는다. 항목 시작 전의 종료는 feedback의 PHASE_PREPARING과 reason으로 읽힌다. 7단계에서 닫는다.

5단계 계약과 달라진 의미 문장(근거는 쟁점 3과 쟁점 4).

| 번호 | 5단계 문장 | 6단계 결정 |
| --- | --- | --- |
| M1 | 즉시 abort되는 goal(BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION, NOT_READY)은 feedback 0건 | feedback 0건이 보장되는 것은 VEHICLE_ID_MISMATCH, INVALID_MISSION, BUSY뿐이다. NOT_READY 앞에는 PHASE_PREPARING feedback이 나갈 수 있다. NOT_READY로 끝난 goal은 setpoint와 명령을 하나도 보내지 않았다. "Fleet은 feedback 수신을 수락 확인으로 쓰지 않는다"는 그대로다 |
| M2 | (없음) | 발행을 시작한 뒤(P3부터 항목 실행과 정리까지)에 식별 대조가 어긋나면 ABORTED, REASON_INTERNAL이고 `detail`에 기대값과 받은 값을 적는다. 발행을 시작하기 전(P0-P2)의 식별 불일치는 NOT_READY다 |
| M3 | 잠정 규칙: failsafe 동작 중에 취소가 오면 Hold 확인 실패와 같은 경로 | 삭제. 취소는 상황을 가리지 않고 Hold를 시도하고 결과로 가른다. LAND 항목 중의 취소도 같다. CANCELED로 끝난 기체는 Hold(ARMED, `landed` false)이거나 지상 disarm이다. Hold로 끝난 기체는 지면 근처이거나 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않는다([실측] X2a 1.8 s 1회와 X2b 1회, 12 s 관찰, 스크립트가 보낸 명령. 미확인 범위는 쟁점 3 M3의 목록). 지상 disarm 상태의 취소는 이 goal에서 arm을 보낸 적이 없을 때만 바로 CANCELED다 |
| M4 | 공중 취소: setpoint 발행을 유지한 채 Hold 명령, 확인 뒤 CANCELED | 더한다: Hold를 처음 관측하면 setpoint 발행을 멈춘다. Hold 명령의 ack가 거부이면 타임아웃을 기다리지 않고 Land 경로로 간다 |
| M5 | 지상 arm 상태 취소: disarm 확인 뒤 CANCELED(실패 분기 없음) | disarm이 `mode_confirm_timeout` 안에 확인되지 않으면 ABORTED, REASON_DISARM_FAILED(의미: 취소 처리 중 지상에서 보낸 disarm이 제한 시간 안에 확인되지 않았고 기체가 arm 상태로 남았을 수 있다). 대기 중 지상 판정이 풀리면 공중 분기로 넘어간다. REASON_MODE_SWITCH_FAILED의 의미는 넓히지 않는다(요청한 모드 전환이 확인되지 않음). 이 goal에서 arm을 한 번이라도 보냈으면 지상에서 DISARMED로 보여도 같은 disarm 확인을 거친다 |
| M6 | (없음) | 정리(취소, setpoint 항목의 ITEM_TIMEOUT, PREPARING 실패)는 분기를 오가도 상한 안에 끝난다. 상한에 닿으면 지상에서는 disarm을 한 번 더 보내고 취소이면 REASON_DISARM_FAILED, 공중에서는 Land 명령을 보내고 취소이면 REASON_MODE_SWITCH_FAILED다 |
| M7 | (없음) | 첫 항목을 시작하기 전이라도 이 goal의 arm 뒤 ARMED를 처음 관측한 다음에는 비행 중 감시 표가 적용된다. 그래서 REASON_FAILSAFE, REASON_EXTERNAL_MODE_CHANGE, REASON_EXTERNAL_DISARM, REASON_LINK_LOST가 PHASE_PREPARING에서(`last_item_index` 0) 나올 수 있다. REASON_EXTERNAL_DISARM의 의미 문장도 "setpoint 항목 실행 중이거나 그 앞의 arm 확인 중"으로 넓힌다 |

1a에 고정하지 않고 표시만 하는 것(U3. 5단계 사용자 결정 1의 고정 범위에서 뺀 조각): 마지막 항목이 LAND가 아닌 미션(공중에서 끝나는 미션)의 종료 동작. 1a 노드는 그런 미션을 INVALID_MISSION으로 끝낸다(임시 제한, 계약 문장이 아니다). 첫 소비자가 1b의 YAML 미션이므로 1b 설계 토론에서 정하고 1b 완료에 고정한다. architect 권고는 취소와 같은 이유로 "Hold 확인 뒤 SUCCEEDED"다. 7단계 `docs/interface.md`에 "고정 전"으로 적는다.

## 쟁점 1. 스택 기동 주체

결정
- 스택을 올리고 내리는 것은 호스트 wrapper `tests/sitl/run_sitl.sh`다. pytest는 `runner` 서비스(ros-ws, `compose run --rm`) 안에서 돌고, fixture는 `IDSIM_STACK_FILE`의 `stack.json`을 읽어 이미 떠 있는 스택에 붙어 준비 상태를 검증만 한다. 준비 검증이 실패하면 skip이 아니라 session 오류다.
- `runner`에 docker 소켓을 주지 않는다.
- wrapper의 인자: `--stack k`(없으면 `IDSIM_STACK_INDEX`, 없으면 0), `--repeat N`(회마다 down 뒤 콜드 up, 실행 id가 다르다), `--attach <실행 디렉터리>`(올리지도 내리지도 않고 pytest와 수집만. QGC와 Gazebo GUI 육안 확인, 디버깅용), pytest로 넘기는 선택 인자.
- wrapper 규칙: 스택은 `tools/sim_stack.sh`로만 올리고 내린다. 수집에만 `docker compose ps/logs/stop`을 직접 쓴다. 순서는 up -> pytest(바깥 `timeout`) -> (Phase 2에 recorder 정지가 들어올 자리) -> `compose stop -t 15 px4-N` -> 수집 -> down이고, 중단돼도 trap으로 down이 돈다(`--attach` 제외). 마지막 stdout 줄은 실행 디렉터리 경로다. `ros_ws/install/idsim_mission/`이 없으면 빌드하지 않고 안내와 함께 실패한다.
- CI와 로컬은 이 한 명령을 쓴다. `sitl.yml`은 시나리오를 모른다.
- 소유: wrapper를 포함한 `tests/sitl/` 전체는 test-engineer. devops-engineer는 compose와 `sim_stack.sh` 호출부를 검토하고 `sitl.yml`을 소유한다.

근거: architecture.md의 두 문장("fixture가 `docker compose up --wait`로 올린다", "pytest는 ros-ws 컨테이너 안")은 `runner`에 docker CLI와 소켓이 없어 함께 성립하지 않는다(test, devops 둘 다 지적). 소켓을 마운트하면 호스트 root 권한이 테스트 컨테이너로 넘어가 3단계의 uid:gid 매핑 취지와 어긋난다.

기각한 안
- `tools/sitl_test.sh`와 `tests/integration/`(devops): 층 이름이 문서와 CI에서 "SITL 통합", job 이름이 `sitl`이고, 선례 `tests/smoke/run_smoke.sh`와 같은 자리에 두는 쪽이 찾기 쉽다.
- 스크립트 셋(`run_sitl.sh`, `repeat.sh`, `collect.sh`): 진입점은 하나로 한다. 수집을 내부 함수로 둘지 보조 파일로 둘지는 test-engineer가 정한다.

## 쟁점 2. 노드 실행 형태, lifecycle, 생성기

결정: 실행 형태
- 언어는 C++17. 패키지 `idsim_mission`(ament_cmake) 하나에 라이브러리 셋: `idsim_mission_core`(ROS 비의존. 검증, 상태기, 종료 결과), `idsim_mission_px4`(px4_msgs -> snapshot 어댑터), `mission_executor_component`(lifecycle 노드 껍질). 이것은 언어 선택이 아니라 기존 결정(architecture.md의 "핵심 노드는 C++")의 적용이다.
- 기체마다 compose 서비스 `ops-N` 하나. command는 `ros2 launch idsim_mission vehicle_ops.launch.py namespace:=/px4_N executor_name:=mission_executor params_file:=/opt/idsim/artifacts/runs/<id>/params/ops-N.yaml`. 노드 이름의 출처는 생성기 하나다. 값 `mission_executor`는 생성기의 상수이고, 생성기가 같은 값으로 `stack.json`의 `executor_node`와 healthcheck를 만든다. launch 파일은 생성하지 않는 정적 파일이고 `ComposableNodeContainer(component_container_isolated, 이름 ops_container)`와 그 안에 load하는 컴포넌트 `idsim_mission::MissionExecutorNode`(이름은 인자 `executor_name`의 값) 하나만 담는다. launch의 `autostart`는 쓰지 않는다(아래 "전이"). launch 파일은 `executor_name`에 기본값을 두지 않고 노드 이름 문자열을 직접 적지 않는다. remap은 두지 않는다. launch에는 `output='screen'`과 컨테이너의 `on_exit=Shutdown()`을 건다.
- 전이: 전이를 거는 주체는 노드 자신이다. Executor는 생성자에서 만든 벽시계 일회 timer(`create_wall_timer`, 0 ms)로 `configure()`를 부르고, 성공하면 `activate()`를 부른다. 각각 한 번이고 재시도하지 않는다(launch autostart가 하려던 것과 같다). fixture, compose command, launch는 전이를 걸지 않는다.
  - timer의 시계: 벽시계여야 한다. 노드 시계(`use_sim_time`) timer는 `/clock`이 오기 전에는 fire하지 않으므로, `/clock`이 없으면 전이를 시도하지도 않아 ERROR 로그 없이 `unconfigured`에 남는다. 이 timer는 판정에 쓰지 않는 trigger이고 벽시계 예외 목록(문서 반영 목록의 시간 기준 문장)에 넣는다. P3a 시험 코드의 자기 전이도 `create_wall_timer(0 ms)`였다([실측] `/clock`이 없는 실행에서도 fire해 configure가 성공했고 activate는 2.000 s 뒤 FAILURE였다). 주의 둘: (1) 콜백의 첫 줄에서 timer를 `cancel()`한다. 0 ms 벽시계 timer는 취소하지 않으면 계속 다시 fire한다. (2) on_activate는 이 timer 콜백 안에서 최대 2 s 동안 executor를 막는다. 그동안에도 `/clock`은 TimeSource의 clock thread(`use_clock_thread` 기본 true)가 받으므로 대기가 풀린다([실측] 대기 중에 `/clock`이 도착한 경우 1.350 s 뒤 성공). NodeOptions에서 `use_clock_thread`를 끄지 않는다.
  - 끄는 param: 선언 param `lifecycle.self_start`(bool, 기본 true, 읽기 전용. 생성자에서만 읽는다). 생성기는 이 key를 params 파일에 만들지 않는다(식별값만 생성한다는 규칙 그대로). 단위 테스트와 노드 배선 테스트는 NodeOptions의 parameter override로 false를 주고 전이를 직접 건다. false여도 lifecycle 서비스는 그대로라 손으로 전이할 수 있다.
  - 실패 시: 프로세스를 끝내지 않는다. 노드는 실패한 자리(`unconfigured` 또는 `inactive`)에 남고, 어느 전이가 왜 실패했는지 ERROR 로그 한 줄을 고정 접두어로 남긴다(grep할 수 있게). 드러나는 길은 compose healthcheck(`active`로 시작하지 않음)와 `sim_stack.sh`의 노드 단계 실패 때 출력하는 `ops-N` 로그 끝과 `.State.Health.Log`다. `run_sitl.sh`는 둘 다 아티팩트에 넣는다.
  - 실패 시 프로세스를 끝내는 안을 기각한 이유: 컴포넌트가 `rclcpp::shutdown()`을 부르면 컨테이너 프로세스 전체가 내려간다. Phase 2에 같은 컨테이너에 들어올 Collector까지 내리게 되고, 프로세스의 수명을 컴포넌트 하나가 정하는 구조가 된다. 남겨 두면 상태를 조회하고 손으로 전이를 다시 걸 수 있다. 실패가 드러나는 방식이 원래 설계(healthcheck)와 같다. 대가는 실패가 즉시가 아니라 healthcheck 주기 뒤에 드러난다는 것이다. 상한은 컨테이너 시작부터 약 54 s, 최악 70 s다(devops-engineer. [추정]. 아래 healthcheck 값). 실패한 실행에서만 드는 비용이고 `STACK_UP_TIMEOUT` 240 s와 CI 15분 안이다.
  - 표시 파일(노드가 전이 결과를 파일에 쓰고 healthcheck가 먼저 읽는 안)은 두지 않는다. 컴포넌트와 compose 사이에 경로 계약이 하나 생기고, `ros2 lifecycle get`이라는 직접 신호가 이미 있다. 다시 볼 조건: CI에서 probe 평균이 7 s를 넘거나 probe 부하로 RTF가 0.7 기준에 걸릴 때(devops-engineer).
  - launch 쪽: [실측]은 `ComposableLifecycleNode(autostart=True)`를 둔 채 자기 전이를 켠 형태였다(10/10 active). 구현은 `autostart`를 빼고 load만 하는 형태로 두고(`ComposableNode`를 쓸지 `ComposableLifecycleNode(autostart=False)`를 쓸지는 ros2-engineer가 정한다).
- lifecycle: on_configure에서 params 검증(`vehicle.*` 누락이나 불일치, `use_sim_time` false이면 FAILURE)과 PX4 구독, 발행자, 사건 발행자 생성. on_activate에서 `/clock` 대기(2 s. `wait_until_started`의 벽시계 대기다. [실측] P3a: 프로세스 시작부터 첫 `/clock`까지 최대 0.66 s이고 on_activate에 들어갈 때는 이미 시작되어 있어 실제 대기는 20/20 0 s였다. `/clock`이 없으면 2.000 s 뒤 FAILURE로 `inactive`에 남는다. CI runner에서는 첫 CI 실행에서 다시 재고 2 s가 모자라면 값을 올린다)와 `Px4Timestamp::now` 성공 확인, 20 Hz timer(노드 시계), action 서버 생성. goal 실행 중의 deactivate는 거부. on_shutdown과 on_error는 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝내고 종료 사건을 낸다. `vehicle_status` 수신과 식별 대조는 activate 조건에 넣지 않는다(쟁점 3 M1).
- action 서버를 on_activate에서 만든다. 그래서 client의 `server_is_ready`가 active의 근거가 된다([추정]. 쟁점 7).
- callback group은 MutuallyExclusive 하나에 PX4 구독, timer, action 서버를 모두 넣는다. goal 실행용 thread를 만들지 않고 timer tick이 상태기의 `step()`을 부른다. 구독 callback은 최신 표본과 수신 ROS 시각만 저장한다.
- 컨테이너 autostart는 동작하지 않는다([실측] P3a. 5/5 `unconfigured`, 오류 로그 없음. [소스] launch_ros 0.26.13의 `load_composable_nodes.py`가 FQN을 `/px4_1mission_executor`로 만들고 `ChangeState`의 matcher가 어느 네임스페이스에서도 맞지 않는다). 이 경우에도 "단독 실행 파일이 `main`에서 전이"로 가지 않고 위 자기 전이를 고른다. 컨테이너를 고른 이유(Phase 2 Collector 동거, isolated executor)가 그대로 지켜지고 서비스 command, launch 인자, healthcheck가 바뀌지 않는다. launch_ros 판에도 의존하지 않는다.

결정: 생성기와 `stack.json`
- params 파일은 `artifacts/runs/<id>/params/ops-N.yaml`. key는 `/**`이고 내용은 `use_sim_time: true`, `vehicle.id`, `vehicle.ns`, `vehicle.sysid`뿐이다. 튜닝 값(타임아웃, 주기), `command_source.*`, `lifecycle.self_start`는 생성하지 않고 노드 선언 기본값에 둔다. [실측] P3a: `/**`의 값은 컨테이너 노드에 적용되고 선언하지 않은 key는 LoadNode 오류 없이 무시된다. 패키지 config yaml을 둘째 params 파일로 두지 않는다. 노드는 `vehicle.*`에 기본값을 두지 않아 누락이면 configure가 실패한다.
- `stack.json`(schema 1 유지, key 추가만): `vehicles[].vehicle_id`, `vehicles[].params_file`(실행 디렉터리 기준 상대 경로), `vehicles[].executor_node`(노드 FQN. healthcheck와 진단용), `run.params_dir`, `startup.node_stages`, `services.ops`. `GENERATOR_VERSION`은 P4에서 3, P5에서 4.
- `vehicle_id`와 `px4_ns`는 별도 key로 둔다. 지금은 값이 같고 생성기의 불변식 검사가 `vehicle_id == ns[1:]`과 토큰 하나임을 단정한다. `px4_ns`는 PX4 환경변수에 넣는 값이고 `vehicle_id`는 계약 식별자라서 의미가 다르다.
- `ops-N` 서비스: ros-ws 이미지, 호스트 uid:gid, `ROS_LOG_DIR=<run>/ros_log/ops-N`, `depends_on`은 `bridge`와 `px4-N`(healthy), `restart: no`, `stop_grace_period: 10s`(`sim_stack.sh`와 `run_smoke.sh`의 `down --timeout 10`이 서비스 값보다 우선하므로 하나로 맞춘다), `init: true`, `stop_signal: SIGINT`.
  - `stop_signal`을 SIGINT로 두는 이유([실측] P3a, 각 1-2회): `init: true` 구성에서 SIGTERM이면 0.4-0.5 s에 끝나지만 launch가 바로 죽어 정리 로그가 없다. SIGINT면 `init` 유무와 무관하게 1.7 s에 launch가 자식에게 신호를 넘기고 정리 로그를 남기며 끝난다. Executor의 on_shutdown(실행 중인 goal을 ABORTED로 끝내고 종료 사건을 낸다)이 돌 기회가 SIGINT 쪽에만 있다고 본다([추정]. 실측 없음. P4 stop 검증). `init` 없이 PID 1인 launch가 SIGTERM을 무시해 15.5 s 뒤 SIGKILL되는 것은 `init: true`를 두는 이유다. launch는 신호를 받으면 자식에게 SIGINT, 5 s 뒤 SIGTERM, 다시 5 s 뒤 SIGKILL을 보낸다([소스]. 유예 10 s 안에 끝나는지의 해석에 쓴다).
  - exit code: SIGINT로 끝난 launch의 exit code는 정상 정리에서도 1이다([실측]). 컨테이너 exit code는 판정에 쓰지 않는다(판정은 junit과 verdict). exit 1을 보아 넘기는 것은 stop을 요청한 뒤(down 단계)에 한정한다. up 단계와 실행 중의 종료는 코드와 무관하게 실패다(launch 인자 누락도 rc 1이고, 컨테이너 프로세스가 죽으면 `on_exit=Shutdown()`으로 exited가 된다). 둘을 가르는 것은 순서다: (1) stop 전에 `compose ps -a --format json`을 기록하고, (2) 그 시점에 running이 아닌 `ops-N`이 있으면 실패, (3) `compose stop`, (4) `compose logs`(SIGINT 정리 로그 포함), (5) down. stop 뒤의 exit code(1, 130 등)는 기록만 한다. `--abort-on-container-exit`와 `--exit-code-from`은 쓰지 않고, entrypoint에서 exit 1을 0으로 바꾸지 않는다.
  - healthcheck: `ros2 lifecycle get --no-daemon <executor_node>`의 출력이 `active`로 시작하는지([실측] P3a: 출력은 `active [3]`, `inactive [2]`, `unconfigured [1]` 형식이고 `docker exec`로 3.0-4.5 s 걸린다). 값은 devops-engineer의 것을 채택한다: `interval` 10s, `timeout` 10s, `retries` 2, `start_period` 20s, `start_interval` 2s. 명령은 `/opt/ros/<distro>/setup.sh`만 source하고(`bash -l`과 workspace overlay 없음) `ROS_LOG_DIR=/tmp/hc timeout 8 ros2 lifecycle get --no-daemon <FQN>`의 출력을 echo한 뒤 판정한다. 출력을 버리지 않아 `.State.Health.Log`에 `unconfigured [1]` 같은 상태가 남는다. FQN은 생성기 상수 하나에서 나오고 `stack.json`의 `executor_node`와 같다.
  - 실패가 드러나기까지의 상한([추정] devops-engineer. probe가 겹치지 않고 앞 probe가 끝난 뒤 `interval`만큼 기다린다는 동작은 기억에 기댄다): 정상은 약 5-6.5 s에 healthy. 자기 전이 실패는 20 + 4.5 + 2 x 14.5 = 약 54 s, 모든 probe가 timeout까지 가면 20 + 10 + 2 x 20 = 70 s. P4에서 결함 주입으로 잰다. `retries` 2는 runner가 `ops-N`의 healthy에 의존하게 되므로 probe 한 번의 흔들림으로 테스트 시작이 실패하지 않게 하려는 값이다. CI 첫 3회에 RTF와 함께 probe 시간을 기록하고, RTF가 0.7 기준에 걸리면 `interval` 30s를 먼저 시험한다.
  - 다른 서비스: bridge와 xrce-agent도 PID 1이라 SIGTERM을 버린다([소스] 떠 있는 스택의 신호 마스크. down 시간은 미측정이고 지금 약 20 s 이상으로 추정). 상주 ros-ws 서비스(bridge, `ops-N`, P5의 foxglove)와 xrce-agent에 `init: true`를 둔다. `stop_signal: SIGINT`는 launch로 띄우는 `ops-N`에만 둔다(bridge의 `ros2 run`이 SIGINT를 자식에 넘기는지 모른다). P4의 같은 PR에서 고치고 생성기 golden 4종이 함께 바뀐다.
- `runner`의 `depends_on`을 `bridge`에서 `ops-1..N`으로 바꾼다.
- 기동 단계: `tools/sim_stack.sh up`은 인프라 3단계 -> 모델 사전 검사 -> 노드 단계. `--infra-only`면 노드 단계를 건너뛴다. `run_smoke.sh`는 `--infra-only`를 쓴다. 노드 단계 전에 `ros_ws/install/idsim_mission/`이 없으면 안내와 함께 실패한다(1a 4단계 넘김).
- embedded 변형에는 `ops-N`, `foxglove`, `lichtblick`을 만들지 않는다(`/clock` bridge가 없다).
- golden 비교를 실행 디렉터리 전체 트리(파일 집합과 바이트)로 넓힌다. 성질 검사에 "생성 파일 어디에도 `fmu/`가 없다"를 넣는다.
- `check_host.sh`에 Docker Engine 25 이상 점검을 넣는다(`start_interval`. 미해결 항목 닫기).
- `gen_compose.sh`의 `--run-id` 제거는 P4에서 한다.

근거
- isolated 컨테이너는 Phase 2에 Collector가 같은 프로세스에 들어와도 Executor의 20 Hz tick을 밀어내지 않는다. architecture.md의 "기체당 컴포넌트 컨테이너 하나"와 같다.
- 서비스 이름을 `mission-N`이 아니라 `ops-N`으로 두는 이유: Phase 2에 Collector가 들어오면 이름이 역할과 어긋난다(devops도 중립 이름을 대안으로 냈다).
- `/**`: 컨테이너 노드와 Phase 2 Collector가 같은 식별값을 받고, 선언하지 않은 key는 무시된다. FQN key의 걱정(이름이 틀리면 조용히 미적용)은 `/**`에서는 생기지 않고, 누락은 configure 실패로 드러난다.
- 튜닝 값을 생성하지 않는 이유: 생성기 golden이 튜닝 변경에 흔들리지 않고, 값의 출처가 하나다(ros2, devops 같은 의견).
- 스모크에서 노드를 빼는 이유: 스모크는 PX4, Gazebo, DDS 회귀 판정이고, px4-in의 arm과 disarm이 Executor와 같은 기체에 명령을 보내는 일을 피한다(devops, px4).

기각한 안
- `ros2 run` 단독 실행 파일과 `autostart` param, 단독 실행 파일 + `launch_ros.actions.LifecycleNode(autostart=True)`(P3a의 대안 B. [실측] 10/10 active), 단독 실행 파일이 `main`에서 전이: 셋 다 Phase 2의 같은 컨테이너 요구를 잃는다. B는 전이 주체가 launch로 남고 실패 때 launch가 ERROR 로그를 내는 장점이 있지만 그 이유로 컨테이너를 버리지 않는다.
- launch가 `change_state` 서비스를 직접 부르거나 `ros2 lifecycle set` 프로세스를 띄우는 안(P3a의 D): 측정하지 않았고 launch 코드나 participant가 는다.
- FQN key와 패키지 config 둘째 params 파일: 위 근거.
- `bridge.yaml` 생성: 1a에는 `/clock` 한 줄뿐이라 바꿀 이유가 없다. 1b에서 표적과 함께 옮긴다.
- `.idsim_build.json`: `stack.json`의 git commit, dirty와 반복 요약으로 대신한다.

## 쟁점 3. 5단계 계약의 변경

결정은 "계약과 golden"의 M1-M7이다. 근거와 기각한 안을 적는다.

M1(NOT_READY의 시점)
- `handle_accepted`는 goal과 노드 자신의 상태만으로 판정되는 것만 즉시 abort한다. 순서는 VEHICLE_ID_MISMATCH -> INVALID_MISSION -> BUSY다(틀린 기체로 온 goal에 BUSY를 주면 Fleet이 다른 기체에 재시도해 설정 오류를 덮는다).
- PX4 상태에 달린 판정(`vehicle_status`, `failsafe_flags`, `vehicle_local_position`, `vehicle_land_detected` 수신, 식별 대조, EKF gate)은 모두 PREPARING에서 `ready_timeout`(ROS 시각) 안에 기다린다. 식별 불일치가 확정되면 그 tick에 NOT_READY, 시간을 넘기면 NOT_READY다. NOT_READY는 발행을 시작하기 전(P0-P2)에만 쓴다. NOT_READY로 끝난 goal은 setpoint와 명령을 하나도 보내지 않았다.
- 근거: [실측] PX4 토픽은 에이전트를 거쳐 discovery에 약 1.1 s가 걸린다. activate 직후의 goal에 "status 미수신이면 즉시 NOT_READY"를 적용하면 흔들린다. EKF 수렴은 기다리면 풀린다. 5단계의 `reason` 경계("NOT_READY는 항목을 시작하기 전(PHASE_PREPARING)에")와는 이미 맞고, 어긋나는 것은 "feedback 0건" 문장뿐이다.
- 기각: 즉시 NOT_READY를 식별 불일치와 미수신에 남기는 안. 경로가 둘이 되고 미수신 쪽이 흔들린다.

M2(식별 불일치)
- 발행을 시작하기 전(P0-P2)의 식별 불일치는 NOT_READY다(M1). 발행을 시작한 뒤(P3-P6, 항목 실행 중, 정리 중)의 식별 불일치는 ABORTED, REASON_INTERNAL이고 `detail`에 기대값과 받은 값을 적는다. 사실상 설정 오류이거나 같은 네임스페이스에 다른 발행자가 있는 경우다. NOT_READY와 PRECONDITION_FAILED는 정의상 항목 시작 전이고, NOT_READY는 기체에 아무것도 보내지 않은 goal에만 쓴다. 새 상수는 소비자가 없어 더하지 않는다.
- P3-P6에서 ARMED를 처음 관측하기 전의 식별 불일치는 정리 분기를 고르지 않는다(입력을 믿을 수 없다). 이 goal에서 arm을 보냈으면 강제가 아닌 disarm을 한 번 보내고 확인 없이 끝내며 `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground"를 적는다. 이 disarm은 기대 sysid로 주소를 정하므로 우리 기체가 맞다면 받아들여지고, PX4 sysid가 기대와 다르면 PX4가 `target_system` 불일치로 무시한다([소스] `Commander.cpp` 746행). 어느 쪽이든 해가 없다. 강제가 아닌 disarm은 공중에서 거부되며, 이륙 이력이 없으면 자동 disarm이 없다(`COM_DISARM_PRFLT=-1`).
- ARMED를 처음 관측한 뒤의 P6과 setpoint 항목 실행 중에는 비행 중 감시 표의 순위 2다(쟁점 4). disarm 규칙은 위와 같다(arm을 보냈으면 `landed`를 보지 않고 1회). LAND 항목 중에는 발행 중이면 발행을 멈추고 끝낸다.
- 정리 중(취소, ITEM_TIMEOUT, PREPARING 실패)에 식별이 어긋난 `vehicle_status` 표본은 발행 규칙, 분기 고르기, 확인 계수(disarm, Hold, AUTO_LAND)에 쓰지 않는다. 같은 네임스페이스의 다른 발행자의 DISARMED나 Hold로 정리를 끝내면 우리 기체가 arm으로 남을 수 있기 때문이다. 이미 정해진 분기는 유지하고 그 분기의 타임아웃이나 정리의 상한(M6)이 끝낸다. 분기가 정해지기 전(정리의 첫 tick)이면 끝낸다. 취소는 ABORTED, REASON_INTERNAL, 그 밖은 원래 reason이고 arm을 보냈으면 위와 같이 disarm을 한 번 보낸다.

M3(LAND 중 취소와 잠정 규칙 삭제)
- 취소는 어느 상태에서 오든 그 tick의 snapshot으로 분기를 고른다: 지상 disarm이면 바로 CANCELED(이 goal에서 arm을 한 번도 보내지 않았을 때만이다. 보냈으면 `arming_state`와 무관하게 disarm 분기를 거친다. M5), 지상 arm이면 disarm 분기, 공중이면 Hold 분기. LAND 항목 중이어도 같다. 분기는 매 tick 다시 고른다(Hold를 보낸 뒤 지상 판정이 올라가면 지상 분기로 간다).
- 근거: [실측] B(offboard 손실 failsafe 진행 중의 Hold가 ACCEPTED, 첫 status에서 AUTO_LOITER, `failsafe` false)와 C(NAV_LAND 착륙 중의 Hold가 ACCEPTED, 하강 정지). [소스] 모드 폴백은 사용자 넘겨받기를 항상 허용한다. 계약의 분기가 하나가 되고, cancel 거부라는 새 분기를 client에 만들지 않는다. 착륙 중 취소는 "지금 하는 것을 멈추고 대기"로 읽히며, 내리는 것은 취소를 요청한 쪽의 책임이다(5단계 "취소 뒤의 책임").
- 지면 근처에서의 취소: [실측] TAKEOFF 목표점 발행 중의 이륙 램프(첫 ARMED 표본 뒤 1.3 s와 1.8 s. 높이 -0.11에서 0.06 m)와 0.5 m 호버(0.37-0.47 m)에서 Hold를 보내고 처음 관측한 순간 발행을 멈추면 기체는 내려앉지 않는다. 12 s 동안 ARMED, `landed` false, AUTO_LOITER로 머물렀고 자동 disarm은 없었다(X2a 2회, X2b 1회. 모두 실측 스크립트가 보낸 명령이다). [소스] Hold에는 하강 속도 setpoint가 없어 `ground_contact`가 서지 않는다(`MulticopterLandDetector.cpp` 229-236행). "`ground_contact`가 참이면 Hold가 받아들여져도 계속 내려앉아 자동 disarm된다"는 이 범위에서 성립하지 않는다.
  - Executor의 규칙으로 읽은 표본 수: Hold로 끝나는 경로의 표본은 X2a 1.8 s 1회와 X2b 1회, 둘이다. X2a 1.3 s는 Hold를 확인한 시점에 `landed`가 true였으므로(0.16 s 뒤 false) Executor의 규칙에서는 공중 분기가 아니라 지상 arm 분기다.
- 계약 문장: CANCELED로 끝난 시점의 기체는 Hold(AUTO_LOITER, ARMED, `landed` false)이거나 지상 disarm이다. Hold로 끝난 기체는 지면 근처이거나 사실상 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않고 그대로 머문다(위 표본, 12 s 관찰). 분기 규칙은 그대로다. Hold 확인을 기다리는 중에 `landed`가 참이 되면 지상 분기로 넘어가고, 그 창에서 본 DISARMED의 분류는 쟁점 4의 고정 규칙을 따른다(지상 disarm이면 FAILSAFE가 아니라 CANCELED).
- CANCELED 뒤 이어 보낸 `[LAND]` 미션: Hold로 끝난 기체는 armed이고 `landed` false이므로 `[LAND]`의 시작 조건을 통과한다. [실측] 실측 스크립트가 보낸 NAV_LAND 5회가 모두 disarm까지 갔다. 갈라 적으면 Hold 상태(AUTO_LOITER, 발행 없음)에서 3회(X2a 2회, X2b 1회), 지상 setpoint를 발행하던 OFFBOARD에서 2회(H)다. Executor가 보낸 `[LAND]` 미션은 아직 실측이 없다(Executor가 없다). 따라서 이 표본에서는 이륙 단계나 낮은 호버에서 Hold로 끝난 취소 때문에 `[LAND]`가 PRECONDITION_FAILED로 끝나지 않는다. 취소가 지상 disarm 분기로 끝난 경우(기체가 이미 DISARMED)에는 당연히 PRECONDITION_FAILED다.
- 미확인 목록(위 계약 문장이 덮지 못하는 범위. 넘김 목록의 필수 재실측). 결과가 계약 문장과 다르면 고정 전에 고친다.
  - AUTO_LAND 하강 중 0.3 m 아래에서의 취소. 하강 중에는 `ground_contact`가 이미 서 있을 수 있어 위 실측과 다를 수 있다([추정]). "Hold로 CANCELED된 뒤 스스로 내려앉아 disarm되고, 이어 보낸 `[LAND]`가 PRECONDITION_FAILED"가 나올 수 있는 경우다.
  - 12 s 이후의 동작. 관찰이 12 s까지였다. 재실측은 60 s 이상 본다.
  - 지상 setpoint 발행 중에 보낸 Hold(M5의 지상 arm 분기에서 공중 분기로 넘어가는 경로). H의 정리는 NAV_LAND였다.
  - TAKEOFF 목표점 발행 중이고 `landed`가 아직 true인 구간(첫 ARMED 뒤 약 0-1.3 s)에서 지상 setpoint로 바꾸고 disarm. 이륙 직후 취소의 정상 경로다.
  - 높이 0.06 m와 0.37 m 사이에서의 Hold.
  - Executor가 보낸 `[LAND]` 미션(지면 근처 Hold에서).
- 시나리오 D는 5 m에서 취소하므로 위 미확인 범위에 들지 않는다.
- 정리 분기는 Executor가 발행이나 명령을 한 번이라도 한 뒤에만 의미가 있다. P0-P2에서 끝나는 NOT_READY와 PRECONDITION_FAILED는 정리 없이 끝난다. 아무것도 하지 않은 상태의 취소는 `vehicle_status`나 `vehicle_land_detected` 표본이 없거나 상태가 끊겼으면 바로 CANCELED이고(그때는 CANCELED 뒤의 기체 상태를 보장하지 않는다), 표본이 있으면 위 규칙대로 고른다. 예: `[LAND]` 미션의 P2 대기 중 취소는 공중이면 Hold를 보낸다. TAKEOFF 미션이 P0에서 다른 토픽을 기다리는 중에 외부에서 arm된 지상 기체를 취소가 만나면 지상 분기가 그 기체를 disarm한다(강제가 아닌 disarm이라 위험은 낮다). 이 동작은 7단계에서 다시 본다(넘김 목록).
- arm을 보내지 않은 goal(`[LAND]` 미션, arm 전의 PREPARING 실패)의 "지상 disarm이면 바로 끝"은 표본 하나로 정한다. 지상 분기 중이면 그 분기의 disarm 확인(3회 연속)을 이어 가고, 공중 분기 중에 지상 DISARMED 표본이 오면 그 tick에 끝낸다(앞서 지상 분기를 거친 적이 있어도 같다. 지상 분기 여부는 이력이 아니라 그 tick의 분기다). arm을 보낸 적이 없어 늦은 arm 경합(M5)이 없고, 그 표본의 기체는 CANCELED의 계약 상태(지상 disarm)에 있다. 예: `[LAND]` 미션을 취소해 공중 분기에 있는 동안 PX4가 스스로 착륙하고 disarm한 경우.
- 기각: `handle_cancel`에서 REJECT. cancel 거부라는 새 분기를 client에 만든다.

M4(Hold 확인 뒤 발행 중단, ack 거부의 처리)
- 공중 분기: 발행을 유지한 채 Hold 명령을 재전송하며 기다린다. AUTO_LOITER를 처음 관측하면 발행을 멈추고, 3회 연속이면 CANCELED. ack가 거부(TEMPORARILY_REJECTED, DENIED 등)이거나 `hold_confirm_timeout`(기본 3 s)을 넘기면 Land 경로: NAV_LAND를 재전송하며 AUTO_LAND를 처음 관측하면 발행을 멈추고 ABORTED, REASON_MODE_SWITCH_FAILED. `mode_confirm_timeout` 안에 AUTO_LAND도 보이지 않으면 발행을 멈추고 같은 결과로 끝낸다(그 뒤는 PX4의 offboard 손실 경로 `COM_OBL_RC_ACT=4`가 내린다). `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 ABORTED, REASON_LINK_LOST.
- 이 정리에서 Hold가 한 번 실패했으면(거부 ack이든 `hold_confirm_timeout`이든) 그 뒤 공중 분기에 다시 들어갈 때는 Hold를 다시 보내지 않고 Land 경로로 간다(Land 경로에서 지상 분기로 갔다가 `landed`가 다시 false가 된 경우). 다시 들어간 Land 경로의 `mode_confirm_timeout` 기준 시각은 다시 들어간 시각이다. [소스][추정] Hold가 실패하는 원인(위치 무효 같은 거부, 명령이나 표본의 연속 유실)은 금방 풀리지 않고, 같은 Hold를 다시 보내면 3 s를 버리고 정리의 상한(M6)에 먼저 닿는다.
- 이 정리에서 Hold가 아직 실패하지 않은 채 공중 분기에 다시 들어가면(지상 분기를 거쳐 `landed`가 다시 false가 된 경우) 새 분기로 본다. 들어간 tick에 Hold를 다시 보내고 재전송 주기, 대기 중인 명령, ack 창, AUTO_LOITER 확인 계수(3회 연속과 `timestamp` 중복을 건너뛰는 기억 포함), `hold_confirm_timeout`의 기준 시각을 모두 다시 들어간 시각부터 새로 잡는다. Hold 확인에는 disarm 확인과 같은 "전송 뒤에 받은" 표본 기준을 두지 않는다. ARMED이고 AUTO_LOITER인 표본은 그 시점의 기체 모드이고, 늦게 처리되어 결과를 뒤집을 경합 명령(M5의 arm)이 없다. Hold를 한 번 관측해 멈춘 발행은 다시 켜지 않는다. 분기를 오가는 전체 길이는 정리의 상한(M6)이 막는다.
- 근거: [소스][실측] `/fmu/in/trajectory_setpoint`는 PX4 안에서 FlightModeManager의 setpoint와 같은 uORB 토픽이라 Offboard가 아닌 모드에서 발행하면 섞인다. Hold 중 발행을 유지하자 0.4 m 끌렸고 멈추자 돌아왔다(1회).
- 지상 arm 분기에서 넘어온 경우(대기 중 `landed`가 false가 됨)에는 TAKEOFF 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다(M5). Hold와 NAV_LAND의 재전송을 멈추는 때는 쟁점 4의 "명령 재전송 규칙"이다.

M5(지상 disarm 실패)
- 지상 arm 분기: 지상 setpoint를 발행하면서(아래) 강제가 아닌 disarm을 재전송하며 DISARMED 3회 연속을 기다린다. disarm의 TEMPORARILY_REJECTED ack는 그 자체로 실패가 아니고 `landed`가 true인 동안 재전송을 이어 간다. 확인되면 발행을 멈추고 CANCELED. 대기 중 `landed`가 false가 되면 공중 분기로 넘어간다. landed인 채 `mode_confirm_timeout`을 넘기면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 ABORTED, REASON_DISARM_FAILED. 이때 기체는 지상에 arm 상태로 남을 수 있고([소스] 이륙한 적이 없으면 offboard 손실 Land 뒤에도 자동 disarm이 없다. 실측 없음) `detail`에 그 사실을 적는다.
- 근거: 강제가 아닌 disarm은 지상 판정이 아니면 거부된다([실측] disarm 실험). 이륙 램프가 막 시작된 경계에서만 생기는 분기이고, 그때 기체는 사실상 공중이므로 공중 분기로 보내는 것이 맞다.
- 이 분기에서 유지하는 setpoint: 지상 arm 분기에 들어간 tick에 `trajectory_setpoint`를 "지상 setpoint"로 바꾼다. 지상 setpoint는 그 tick의 `vehicle_local_position` x, y, z에서 z만 +0.5 m(NED, 아래쪽)이고 yaw는 그 tick의 heading이다. position과 yaw만 유한값이고 나머지는 NaN이며, `offboard_control_mode`는 position만 true다(헬퍼 그대로). 20 Hz 발행을 유지한 채 disarm을 재전송한다. DISARMED 3회 연속이면 발행을 멈추고 CANCELED. 대기 중 `landed`가 false가 되면 공중 분기로 넘어가되, setpoint는 TAKEOFF 목표점으로 되돌리지 않고 지상 setpoint를 유지한 채 Hold를 보낸다. Hold를 처음 관측하면 발행을 멈춘다. disarm의 TEMPORARILY_REJECTED ack는 그 자체로 실패가 아니다. `landed`가 true인 동안 재전송을 이어 간다.
  - [소스] `MulticopterPositionControl.cpp` 466-472행: 이륙 의도는 setpoint z < 현재 z일 때만 켜진다(엄격 비교). 504-520행: 이륙 전이면 추력이 0이다. 0.5 m는 z 잡음(+-0.1 m)의 5배 여유다.
  - [실측] G(처음부터 지상 setpoint로 arm, 2회): 상승은 최대 0.05 m, `landed`는 계속 true, disarm부터 DISARMED까지 4-12 ms. K(목표점을 유지한 채 disarm, 1회): disarm이 거부되고 4.2 m 올라갔다. H(목표점으로 arm한 뒤 1.5 s와 2.5 s에 지상 setpoint로 바꿈, 2회): 바꾸는 순간 이미 `landed`가 false였고(높이 0.07 m 이하) disarm은 TEMPORARILY_REJECTED였다. 지상 setpoint로 상승은 0.2 m 이하로 막혔지만 `landed`는 6 s 동안 돌아오지 않았다. 정리는 Hold가 아니라 NAV_LAND로 했다(3.4-3.5 s 뒤 disarm). 위 문장의 "공중 분기로 넘어가 지상 setpoint를 유지한 채 Hold"는 실측이 없다.
  - 실측이 없는 두 경로(필수 재실측. 구현은 위 문장대로이고 재실측 결과로 바뀔 수 있다): (가) 지상 setpoint 발행 중에 보낸 Hold. X2a의 Hold는 TAKEOFF 목표점 발행 중이었다. (나) TAKEOFF 목표점 발행 중이고 `landed`가 아직 true인 구간(첫 ARMED 뒤 약 0-1.3 s)에서 지상 setpoint로 바꾸고 disarm. G는 처음부터 지상 setpoint였고 H는 바꿀 때 이미 landed false였다. (나)가 "이륙 직후 취소"의 정상 경로다.
  - 기각: 발행을 멈춘 뒤 disarm. 마지막 setpoint의 timestamp + 1 s 동안 이륙 의도가 남고(466-467행), 그 뒤에는 offboard 손실 Land가 걸려 상태가 하나 더 생긴다. 기각: TAKEOFF 목표점 유지(실측 K).
  - 0.5 m는 `src/px4/` 어댑터의 상수이고 노드 파라미터로 만들지 않는다. core는 이 값을 직접 적지 않는다(넘기는 방법은 ros2-engineer와 px4-engineer가 snapshot 경계에서 정한다).
  - 발행 규칙과의 관계: 지상 setpoint로 바꿔 발행하는 것은 그 tick에 발행 중일 때뿐이다. 발행 규칙에 따라 이미 멈춘 발행은 이 분기에서도 다시 켜지 않고 disarm만 재전송한다.
    - 발행이 멈춘 뒤에는 `trajectory_setpoint`를 바꾸지 않으므로 이륙 의도에 영향이 없다. 이 규칙은 "멈춘 발행은 항상 `nav_state`가 OFFBOARD가 아닌 것을 본 뒤"라는 불변식에 기댄다. LAND 항목의 ITEM_TIMEOUT처럼 OFFBOARD인 채 멈추는 경우는 이 규칙의 적용 대상이 아니다(지상 arm이면 offboard 손실 Land가 내린다).
    - [소스] `MulticopterPositionControl.cpp` 464-467행: 이륙 의도는 `flag_control_offboard_enabled`일 때만 `_setpoint.timestamp + 1 s` 안의 setpoint로 켜진다. `Commander.cpp` 644-662행: 강제가 아닌 disarm은 `landed || maybe_landed`일 때 받는다. 노드가 본 `landed == true`는 수락의 충분조건이다.
- 같은 규칙을 지상 arm 정리 전부에 쓴다: 취소, PREPARING 실패, ITEM_TIMEOUT의 지상 arm 분기, 그리고 아래의 "arm을 보낸 뒤" 경우.
- 지상 disarm 분기의 상태 끊김과 거부 ack: `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 끝낸다. 취소 중이었으면 ABORTED, REASON_LINK_LOST이고, PREPARING 실패나 ITEM_TIMEOUT의 정리 중이었으면 원래 reason을 유지하고 `detail`에 적는다. `link_timeout`이 `mode_confirm_timeout`보다 짧으므로 표본이 아예 없으면 LINK_LOST가 먼저이고, 표본은 오는데 기준을 만족하는 DISARMED가 3회 차지 않으면 REASON_DISARM_FAILED다. disarm의 거부 ack는 TEMPORARILY_REJECTED든 그 밖의 것(DENIED 등)이든 그 자리에서 끝내지 않는다. `landed`가 true인 동안 재전송을 이어 가고 타임아웃에 끝내며 마지막 ack의 결과를 `detail`에 적는다(성공의 판정은 ack가 아니라 `arming_state`다).
  - 끝내기 전에 한 번 더 보내는 disarm도 강제가 아닌 disarm이다. 강제 disarm(param2 21196)은 어디에서도 쓰지 않는다. [소스] 강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 거부되므로(`Commander.cpp` 638-662행) 공중 기체를 끄지 않는다. 발행을 멈춘 뒤의 offboard 손실 동작은 지상이면 Land와 자동 disarm, 공중이면 하강이다.
  - [소스] v1.17.0의 ARM_DISARM 처리(`Commander.cpp` 969-980행)는 유효한 param1에 ACCEPTED와 TEMPORARILY_REJECTED만 돌려준다. 그 밖의 ack(DENIED, UNSUPPORTED 등)는 방어용이며 같은 규칙(재전송, 타임아웃에 종료)을 쓴다. 대상이 어긋난 명령은 ack 없이 버려지고 타임아웃이 처리한다. ARM의 "그 밖의 거부는 ARM_REJECTED"도 같은 이유로 방어용이다(arm의 DENIED도 TEMPORARILY_REJECTED로 돌아온다. 549행). 이 경로들의 테스트는 합성 ack로만 한다.
- arm을 보낸 뒤의 지상 분기: 이 goal에서 arm을 한 번이라도 보냈으면 지상 분기는 `arming_state`와 무관하게 disarm 분기(지상 setpoint + disarm + disarm 전송 뒤에 받은 DISARMED 3회 연속)를 거친다. "전송 뒤에 받은"의 기준: 표본의 수신 tick이 이 분기의 첫 disarm 전송 tick보다 크고(tick 번호 비교. `수신 tick > 전송 tick`), `vehicle_status.timestamp`가 그 첫 전송에 실은 `Px4Timestamp`보다 엄격히 뒤(>)인 표본만 센다(두 조건 모두. 비교 대상은 재전송마다 새로 생기는 값이 아니라 첫 전송의 값이다). 지상 분기에 들어갈 때마다(정리 중 지상 분기 -> 공중 분기 -> 지상 분기로 다시 들어간 경우 포함) 그 tick에 disarm을 보내고, DISARMED 확인 계수를 0으로 되돌리며, 첫 전송 기준(tick, `Px4Timestamp`)을 그 전송의 값으로 새로 잡는다. 앞선 지상 분기에서 센 표본은 이어 세지 않는다. 3회 연속의 계수: 직전에 센 표본과 `timestamp`가 같은 표본은 건너뛴다(되돌리지도 더하지도 않는다. tick당 표본은 최대 1개이므로 같은 표본을 다음 tick에 다시 본 경우이거나 같은 표본이 한 번 더 수신된 경우다. [실측] 같은 `timestamp`와 필드의 표본이 약 125 ms 뒤에 다시 수신된 회가 있다). DISARMED가 아닌 표본은 계수를 0으로 되돌린다. `timestamp`가 줄어든 표본은 세지 않는다. 3회 연속은 서로 다른 `timestamp` 3개다(근거는 바로 아래). arm 재전송은 취소나 실패를 정한 tick에 즉시 멈춘다. 이유: P6에서 보낸 arm이 아직 처리되지 않았거나 status에 반영되기 전이면 snapshot은 DISARMED다. arm이 받아들여져도 ARMED 표본이 한 번도 나오지 않을 수 있다. [실측] arm과 disarm을 같은 시각에 보낸 2회 모두 PX4는 arm을 받아들였는데(ULog `Armed by external command`) ARMED인 `vehicle_status` 표본은 ROS에도 ULog에도 없었고, 그 뒤의 첫 표본이 DISARMED였다. 그래서 disarm 분기를 거칠지는 ARMED를 관측했는가가 아니라 arm을 보냈는가로 정한다. 여기서 "바로 끝"으로 발행을 멈추면 그 뒤 arm이 처리되어 기체가 OFFBOARD에서 신호 없이 armed가 되고 offboard 손실 Land로 들어간다. 이륙 이력이 없어 자동 disarm이 없으므로 지상에 armed로 남는다([소스] `Commander.cpp` 2290, 2294행. `COM_DISARM_PRFLT=-1`. X3과 같은 상태이고 실측은 없다). 비용은 약 1 s다. 이미 DISARMED인 기체에 보낸 disarm은 ACCEPTED다([소스] `Commander.cpp` 640-642, 976-980행. [실측] disarm 실험 1회).
  - 표본 기준의 근거: 두 값은 같은 축이다([소스] `vehicle_status.timestamp`는 `Commander.cpp` 1943행 근처에서 publish 직전의 `hrt_absolute_time()`이고 SITL lockstep에서 sim 시간이다). 이 기준이 막는 것은 disarm이 처리되기 전의 DISARMED 표본을 세는 것 하나다. arm과 disarm은 같은 `vehicle_command` 토픽의 FIFO라 보낸 순서대로 처리된다([소스] `Commander.cpp` 1884-1898행. [실측] arm 직후에 disarm을 보낸 10회가 모두 DISARMED로 끝났다). 늦게 도착한 arm이 disarm 뒤에 처리되는 일은 없다. 이 기준은 처리 순서에만 기대고, Commander가 한 주기에 명령을 몇 개 처리하는지에는 기대지 않는다. [실측] 같은 시각에 보낸 arm과 disarm의 ACCEPTED ack 둘이 같은 `timestamp`로 왔다(2회). 한 주기에 둘 이상 처리하는지의 [소스] 확인은 없다. 잘못 세려면 표본 간격 약 0.5 s의 3회 연속, 곧 약 1 s 동안 arm이 처리되지 않아야 한다.
  - "엄격히 뒤"는 방어층이다. [소스] `vehicle_status.timestamp`는 단조 증가한다. 같으면 같은 표본을 다시 본 것이고 줄어드는 것은 PX4 재시작이나 시계 되감김뿐이다. 전달 지연 동안 이미 publish된 표본이 "뒤" 조건을 만족할 수 있지만 그 표본이 DISARMED면 기체는 실제로 disarm 상태라 오판정이 아니다.
  - 노드 시계와 `vehicle_status.timestamp`의 관계([실측] 재실측 (2), (3), (5)와 `armed` 항목, 호스트 한 대의 한 실행): 명령 전송 뒤 처음 받은 표본의 `timestamp - Px4Timestamp`는 169건 모두 양수다(+8에서 +20 ms). 0 근처에서 부호가 섞이지 않는다. "노드 sim 시각 - `vehicle_status.timestamp`"는 받은 표본이 묵은 정도이지 노드 시계의 지연이 아니다. 대부분 0이고, 상태가 바뀌어 표본이 연달아 publish된 직후의 표본(arm 뒤 disarm의 첫 DISARMED 표본 9건)이 `timestamp`보다 32-176 ms 늦게 수신됐다. 9건 모두 두 표본 앞의 수신에서 200-204 ms 뒤였다. 유실은 없었고(ULog 대조) `timestamp`로 본 판정은 그대로 맞다. 늦는 원인과, 표본이 셋보다 많이 연달아 나올 때 유실이 생기는지는 확인하지 않았다. 확인(3회 연속)의 소요는 최대 약 0.2 s 늘 수 있고 `mode_confirm_timeout`과 `hold_confirm_timeout`의 여유(약 1.0 s 대 3 s) 안이다.
- 기각: REASON_MODE_SWITCH_FAILED의 의미 넓히기(위 "계약과 golden"의 이유로 받지 않는다), REASON_ARM_REJECTED(이름이 arm 거부라 disarm에 쓰면 PREPARING의 arm 거부와 섞인다), REASON_INTERNAL(Executor 내부 오류가 아니다).
- PREPARING 실패의 정리도 같은 절차다: 발행을 멈추기 전에 지상 arm이거나 이 goal에서 arm을 보낸 적이 있으면 지상 setpoint로 바꾸고 disarm을 보내 확인한다(`COM_DISARM_PRFLT=-1`). 이때의 reason은 원래의 실패 사유를 유지하고, disarm이 확인되지 않았으면 `detail`에 적는다. 예외는 둘이다. 식별 불일치로 끝나는 PREPARING 실패는 정리 분기를 고르지 않는다(M2). P6에서 ARMED를 처음 관측한 뒤의 감시 표 행은 정리 없이 끝낸다(쟁점 4).

상수 REASON_EXTERNAL_DISARM(감시 표 순위 5)
- 의미 문장: "setpoint 항목 실행 중이거나 그 앞의 arm 확인 중(ARMED를 처음 관측한 뒤)에 Executor가 보내지 않은 disarm이 지상에서 failsafe 없이 관측됐다. 끝난 뒤 기체는 지상에 disarm 상태다. 원인은 판정하지 않는다(외부 명령뿐 아니라 PX4 자체의 disarm과 kill을 포함한다)". `failsafe` 가지의 조건은 쟁점 4 감시 표의 순위 5다. REASON_EXTERNAL_MODE_CHANGE의 의미는 넓히지 않는다(Executor가 요청하지 않은 모드 변화).
- 근거: M5 (나)에서 쓴 기준을 그대로 적용한다. (1) 끝난 뒤 기체 상태가 다르다(모드 변화는 보통 공중 armed, 이쪽은 지상 disarm). (2) 읽는 쪽의 다음 동작이 갈린다(공중에서 모드가 바뀐 기체에는 TAKEOFF 미션이 PRECONDITION_FAILED이고, 지상에서 disarm된 기체는 TAKEOFF 미션을 받을 수 있다). (3) 한 상수에 묶어 1a에 고정하면 "상수의 의미를 바꾸지 않는다"에 걸려 뒤에 가를 수 없다. (4) 고정 전인 지금의 비용은 golden 두 파일에 한 줄씩이다. (5) 이름과 의미가 맞는다(mode change라는 이름에 disarm을 담지 않는다).
- 기각: REASON_EXTERNAL_MODE_CHANGE 유지. "끝난 뒤 상태가 위험한가" 하나를 기준으로 삼으면 유지할 수 있다(지상 disarm은 안전한 쪽이다). 그러나 M5에 적은 기준은 위험 여부가 아니라 상태와 다음 동작의 차이였다. 결정을 지키려고 기준을 뒤에 좁히지 않는다. 상수는 고정 전후 모두 추가만 하므로 두 선택 다 되돌릴 수 없는데, 쓰이지 않는 구분은 해가 없고 묶인 의미는 영영 가를 수 없다.
- 기각: 늘 REASON_FAILSAFE(공중 disarm 행과 대칭이지만 운용자가 지상에서 disarm한 것을 기체 이상으로 읽게 만든다), REASON_INTERNAL(Executor 내부 오류가 아니다).
- 한계: "external"은 추론이다. Executor가 아는 것은 "`failsafe`가 false인데 Executor가 보내지 않은 disarm"뿐이고 원인은 모른다(`latest_disarming_reason`은 판정에 쓰지 않는다). REASON_EXTERNAL_MODE_CHANGE도 같은 수준의 추론이다. 의미 문장에는 원인이 아니라 관측을 적는다.
- 이름에 남는 문제(7단계에 1a 고정 전 다시 본다): 의미 문장이 "원인은 판정하지 않는다"인데 이름은 external이다. 다시 볼 때의 시나리오로 `COM_DISARM_LAND` 자동 disarm을 넣는다(TAKEOFF가 뜬 뒤 어떤 이유로 지면에 내려앉아 PX4가 스스로 disarm한 경우. 외부 주체가 없는데 EXTERNAL_DISARM이 나온다).

M6(정리의 상한)
- 정리(취소, setpoint 항목의 ITEM_TIMEOUT, PREPARING 실패)는 시작한 tick부터 ROS 시각으로 `hold_confirm_timeout + 3 x mode_confirm_timeout`(기본 12 s) 안에 끝난다. 이 값은 파생값이고 노드 파라미터로 만들지 않는다. 노드는 configure 때 계산값을 INFO 로그로 남긴다. LAND 항목의 ITEM_TIMEOUT은 정리 분기를 거치지 않으므로 해당하지 않는다.
- 분기마다의 타임아웃은 그대로다(분기에 들어갈 때마다 그 분기의 기준 시각을 다시 잡는다). 매 tick 다시 고르는 규칙이 arm 직후 이륙 램프와의 경쟁을 덮기 때문이다. 상한은 `landed`가 흔들려 분기가 오가는 경우의 전체 길이를 막는다.
- 정리 중 한 tick의 순서: (1) 상태 끊김(M4와 M5의 LINK_LOST 규칙) (2) 공중 DISARMED(FAILSAFE) (3) 정리할 것 없음(지상 DISARMED이고 이 goal에서 arm을 보낸 적이 없고 지상 분기 중이 아님. 바로 끝낸다) (4) 상한 (5) 그 분기의 실행(분기 타임아웃, 확인).
  - (1)-(3)은 표본 하나로 정해지는 관측이라 상한보다 앞이다. 기체가 이미 지상 disarm인데 상한의 실패 reason을 내면 사실과 다르다.
  - (4)가 (5)보다 앞이므로 상한 tick에 온 3번째 확인 표본은 세지 않는다(같은 tick이면 만료가 확인을 이긴다. 아래 "종료의 충돌 규칙").
- 상한 tick의 동작: 발행을 멈추고 대기 중인 명령을 지운 뒤, 그 tick의 고르기에 따라 명령 하나를 보내고 끝낸다.
  - 지상: 강제가 아닌 disarm 1회. 취소이면 ABORTED, REASON_DISARM_FAILED.
  - 공중: NAV_LAND 1회(Hold 분기였든 Land 경로였든, 지상 분기에서 막 넘어와 Hold를 아직 보내지 않았든 같다). 취소이면 ABORTED, REASON_MODE_SWITCH_FAILED. M4의 "Hold가 확인되지 않으면 Land"는 상한으로 끝나는 경우를 포함한다. Hold를 이미 관측해 발행을 멈춘 기체는 이 NAV_LAND가 유실되면 Hold로 남으므로 그 경우를 `detail`에 적는다.
  - ITEM_TIMEOUT과 PREPARING 실패의 정리이면 같은 동작에 원래 reason을 유지한다. 어느 경우든 `detail`에 상한으로 끝났다는 것과 마지막 분기를 적는다.
  - 그 tick의 표본이 식별 불일치이면 다시 고르지 않고 직전까지의 분기로 정한다(지상 분기면 disarm 1회, 공중 분기면 NAV_LAND 1회).
  - 그 tick에 `Px4Timestamp` 공급이 실패하면 명령은 버리고 결과는 유지한다(쟁점 4).
- 값의 근거: 정당한 경로 중 가장 긴 것은 지상 3 s -> Hold 3 s 실패 -> Land 경로 3 s -> 다시 지상 3 s다([소스] 분기를 바꾸는 것은 `landed` 전환과 Hold의 실패뿐이다). 상한이 그 합이므로 정당한 경로를 자르지 않는다(끝의 1 tick 이하 오차에서는 그 분기 자신의 만료와 같은 결과다). 재전송 1회가 유실돼도 분기의 기준 시각은 분기에 들어간 시각이라 경로가 길어지지 않는다. [추정] 정상 경로에서 가장 긴 것은 지상(램프 경쟁, 0.3-1.0 s 뒤 `landed` false) -> Hold 확인 약 1 s -> 지면 근처에서 `landed` true -> 지상 disarm 3 s로 약 5 s다. 나머지는 명령이나 ack의 유실과 낮은 RTF를 위한 여유다. 실측은 없다(재실측 (2), (3), (5)의 기록 항목. 넘김 목록).
- 공중에서 NAV_LAND를 보내는 근거: NAV_LAND는 force라 거부가 없고([소스] `Commander.cpp` 1093-1110행) 여러 번 받아도 결과가 같다. 아무것도 보내지 않으면 Hold를 한 번 관측해 발행을 멈춘 기체는 OFFBOARD가 아니라서 offboard 손실 Land가 걸리지 않고 Hold로 남는다. OFFBOARD인 기체에서도 결과가 다르다. offboard 손실 Land는 `COM_OF_LOSS_T` 1 s 뒤에야 걸리고, failsafe라서 다른 발행자의 setpoint가 들어오면 OFFBOARD로 돌아가며([실측] 0.07 s, 1회) 착륙 뒤에도 의도가 OFFBOARD로 남는다. NAV_LAND로 만든 AUTO_LAND는 사용자 의도라 돌아가지 않는다. 계약 주석의 "Land 명령을 보내고 ABORTED(REASON_MODE_SWITCH_FAILED)"와도 맞는다.
- 기각: 상한 9 s(`hold_confirm_timeout + 2 x mode_confirm_timeout`. 위의 가장 긴 경로에서 마지막 지상 분기를 자른다), 별도 노드 파라미터(configure 검사의 하한이 곧 이 식이라 값 하나만 는다. 상한을 분기 타임아웃과 따로 조정할 요구는 1a에 없다), 분기 전환 횟수의 상한(시간이 아니라서 "유한 시간 안에 끝난다"를 보장하지 못한다), 히스테리시스로 분기를 고정(실측 근거가 없고 램프 경쟁 규칙과 충돌한다), 새 reason(구별해 쓸 소비자가 없다), 상한에서 공중이면 명령 없음(위 근거), 분기 단계를 먼저 돌리고 상한을 보는 순서(상한 tick의 확인이 만료를 이기게 된다).

종료의 충돌 규칙
- 종료는 먼저 정해진 것이 이긴다. 종료가 정해진 tick 뒤의 표본과 cancel은 결과를 바꾸지 않는다. 종료 사건은 정확히 1건이다.
- 같은 tick에 둘 이상이 정해지면 ABORTED 사유, 완료(SUCCEEDED), 취소 순이다. 예: LAND에서 DISARMED 3번째 표본과 cancel이 같은 tick이면 SUCCEEDED다. 감시 표의 행과 cancel이 같은 tick이면 그 행의 ABORTED다. ABORTED 사유가 둘이면 감시 표의 순위를 따른다. 감시 표의 행과 ITEM_TIMEOUT이 같은 tick이면 감시 표의 행이 이긴다(감시 표를 먼저 본다. ITEM_TIMEOUT은 정리가 필요한 사유이고 감시 표의 행은 정리 없이 끝낸다). P6에서 ARMED를 처음 관측한 뒤의 감시 표 행과 확인 기한도 같다.
- 시간 경계: 경과가 값 이상(`>=`)이면 만료다. 같은 tick에 만료와 기다리던 확인 계수(N회 연속)가 함께 정해지면 만료가 이긴다. 전이(P5 확인 대 `mode_confirm_timeout` 등)에도, 정리 분기의 확인(Hold, disarm) 대 그 분기의 타임아웃에도, 확인 대 정리의 상한(M6)에도 같다. 그래서 정확히 타임아웃 tick에 3번째 확인 표본이 오면 실패다. 표본 하나로 정해지는 관측(공중 DISARMED, 정리할 것 없음)은 만료보다 앞이다.
- "정해진다"의 시점은 정리가 끝난 때가 아니라 사유가 생긴 tick이다. ITEM_TIMEOUT이나 PREPARING 실패의 정리(Hold, disarm 확인) 중에 온 cancel은 결과를 바꾸지 않고 ABORTED와 원래 reason으로 끝난다(정리 절차는 취소와 같은 분기라 기체 동작도 같다). 반대로 CANCELING 중에 항목 `timeout`이 지나도 취소 경로로 끝난다(CANCELED, 또는 그 분기가 정한 ABORTED).
- 전제: 종료가 정해져 끝나는 시점에는 발행이 멈춰 있고 명령 재전송이 지워져 있다. 그래야 종료 뒤의 cancel을 무시해도 남는 동작이 없다. ABORTED 사유가 완료보다 앞서는 것은 안전 쪽이다(같은 tick에 `landed` false의 DISARMED(순위 4)와 완료 후보가 겹치면 FAILSAFE가 이겨야 공중 disarm이 성공으로 기록되지 않는다).
- 이유: 취소는 "지금 하는 것을 멈추라"는 요청이고, 이미 끝났거나 끝나기로 정해진 미션에는 멈출 것이 없다. 실제로 일어난 일을 result가 말하게 한다. cancel이 받아들여진 goal을 SUCCEEDED나 ABORTED로 끝내는 것은 rclcpp_action에서 허용된다(노드 배선 테스트 `test/node/test_executor_node.cpp`가 한 건으로 확인한다).

## 쟁점 4. PX4 절차 (전이 표)

상태기 구현의 정본은 아래 표다. 값은 px4-engineer가 정하고, 전이 표의 변경은 px4-engineer가 필수 승인자다(쟁점 6).

미션의 정적 검증(INVALID_MISSION. `validate_mission`)
- 계약: 항목 1개 이상, `type`이 `TYPE_*`, `timeout` > 0, 쓰지 않는 서브메시지는 기본값, 서브메시지 값의 범위(`height_m` > 0, `acceptance_m` > 0, `duration` > 0이고 `timeout`보다 짧다, `YawSetpoint.mode` 유효, 유한값), `mission_id` 정규식.
- 1a 임시 제한(계약 문장이 아니다): `type`은 TAKEOFF, LOITER, LAND만. 마지막 항목은 LAND이고 LAND는 마지막에만. 첫 항목은 TAKEOFF 또는 LAND. 따라서 LAND로 시작하는 미션은 길이 1이다.
- 항목 분류 함수(setpoint 항목과 모드 명령 항목)와 "모든 `TYPE_*`가 정확히 한 분류에 속한다"는 테스트를 core에 둔다(5단계 넘김).

PREPARING(첫 항목이 TAKEOFF)

| 단계 | 동작 | 통과 조건 | 실패 |
| --- | --- | --- | --- |
| P0 | 수신과 식별 | 네 토픽 수신, `vehicle_status`가 신선, 식별 대조 Match | 불일치 확정이면 즉시, 아니면 `ready_timeout`에 NOT_READY |
| P1 | 시작 조건 | `landed == true`이고 DISARMED | PRECONDITION_FAILED |
| P2 | EKF gate | `failsafe_flags`의 `local_position_invalid`, `local_altitude_invalid`, `global_position_invalid`, `home_position_invalid`가 모두 false | `ready_timeout`에 NOT_READY |
| P3 | 발행 시작 | 20 Hz로 `offboard_control_mode`(position만 true)와 `trajectory_setpoint`(TAKEOFF 목표점) | - |
| P4 | 신호 확인 | 발행 10회 이상이고 `offboard_control_signal_lost == false` | `offboard_signal_timeout`에 MODE_SWITCH_FAILED |
| P5 | Offboard | DO_SET_MODE를 0.5 s마다 재전송. ack가 거부이면 실패. `nav_state`가 OFFBOARD 3회 연속 | `mode_confirm_timeout`에 MODE_SWITCH_FAILED |
| P6 | arm | arm을 재전송. TEMPORARILY_REJECTED는 `arm_timeout` 안에서 재시도. ARMED를 처음 관측하면 재전송을 멈춘다. ARMED이고 OFFBOARD인 표본 3회 연속 | ARMED를 처음 관측하기 전: `arm_timeout`(arm을 처음 보낸 시각부터)에, 또는 TEMPORARILY_REJECTED가 아닌 거부 ack에 ARM_REJECTED. ARMED를 처음 관측한 뒤: 비행 중 감시 표의 행이 정리 없이 끝내고, `arm_timeout` 대신 그 시각부터의 확인 기한(`mode_confirm_timeout`)이 흐른다(아래). 취소나 실패를 정한 tick에 arm 재전송을 즉시 멈춘다 |

- `ready_timeout` 하나가 P0과 P2를 덮는다(goal 접수 시각부터).
- P1에서 지상 arm을 받지 않는 이유: arm 상태이고 OFFBOARD가 아닌 모드에서 P3이 목표점을 발행하면 Hold 중 0.4 m 끌림([실측])과 같은 setpoint 섞임이 생기고, Executor가 arm하지 않은 기체(QGC 등 외부에서 arm한 기체)를 넘겨받는 길이 열린다. 실측 없이 허용하지 않는다. 대가: REASON_DISARM_FAILED로 지상 arm이 남은 기체는 누군가 disarm해야 다음 TAKEOFF 미션을 받는다. 보강 근거는 실측 H와 K다. arm 뒤 이륙 램프가 시작되면 높이 0.07 m에서도 `landed`가 false가 되고 그 뒤로는 강제가 아닌 disarm이 거부된다([소스] `Commander.cpp` 644-662행). Takeoff 상태기는 rampup에서 뒤로 돌아가지 않는다([소스] `Takeoff.cpp` 77-87행). 남이 arm한 기체를 넘겨받으면 이 경계를 통제할 수 없다.
- Offboard가 먼저이고 arm이 나중이다. [소스] 시동 해제 상태의 모드 변경은 항상 허용되고 arm 때 "현재 모드에 신호가 없으면 거부"가 걸리므로, arm이 받아들여졌다는 것이 Offboard가 돌 수 있다는 뜻이다. [실측] 4회.
- `vehicle_command`는 식별 대조 Match 뒤에만 낸다. setpoint stream은 gate로 막지 않는다(1a 4단계 px4 조건). P0이 P3보다 앞이라 이 순서에서 자연히 지켜진다.
- `pre_flight_checks_pass`와 `vehicle_local_position.xy_valid`는 gate로 쓰지 않는다. [실측] 착륙 뒤 `nav_state`가 OFFBOARD로 돌아가 `pre_flight_checks_pass`가 false로 남으므로 그 값을 쓰면 두 번째 미션이 늘 NOT_READY가 된다.
- 성공 판정은 ack가 아니라 `nav_state`와 `arming_state`다. ack는 거부를 빨리 아는 데만 쓴다.
- P0의 "`vehicle_status`가 신선"은 마지막 수신이 `link_timeout` 안이라는 뜻이다. P0-P6에서 ARMED를 처음 관측하기 전에는 LINK_LOST 판정을 두지 않고 각 단계의 타임아웃이 잡는다(그 구간의 기체는 DISARMED다. P0에는 discovery 흔들림이 있다).

P6에서 ARMED를 처음 관측한 뒤
- 첫 ARMED 표본은 식별 대조가 맞고 수신 tick이 arm을 처음 보낸 tick보다 큰 ARMED 표본이다(`nav_state`가 OFFBOARD가 아니어도 해당한다). 식별이 어긋난 표본은 ARMED여도 첫 ARMED 표본이 아니고 M2의 규칙으로 끝난다. 그 표본보다 `timestamp`가 작은 표본은 그 뒤의 판정에 쓰지 않는다.
- 첫 ARMED 표본을 본 tick에 arm 재전송을 멈춘다(대기 중인 명령을 지운다). 그 뒤의 ARM ack는 보지 않는다. 같은 tick에 도착한 늦은 거부 ack도 보지 않는다(status를 먼저 보고 대기 명령을 지운 뒤 ack를 읽는다). 확인 계수(ARMED이고 OFFBOARD인 표본 3회 연속)는 계속 센다.
  - 근거: 재전송을 이어 가면 외부 disarm을 Executor가 되돌린다. 외부 disarm 직후 재전송된 arm이 DISARMED 표본보다 먼저 PX4에 닿으면 기체는 다시 arm되는데 goal은 EXTERNAL_DISARM(끝난 뒤 지상 disarm)으로 끝난다. ARMED를 본 뒤의 arm 재전송은 쓸모가 없다([소스] 이미 arm인 기체의 arm은 상태를 바꾸지 않는다. `Commander.cpp` 551-553행).
- 첫 ARMED 표본을 본 tick부터(그 표본 포함) 아래 "비행 중 감시" 표의 순위 1-8을 TAKEOFF 항목과 똑같이 적용한다. 다른 점은 항목 `timeout` 대신 확인 기한(아래)이 흐른다는 것뿐이다. 순위 1을 보려고 그 tick부터 `Px4Timestamp`를 판정 맨 앞에서 묻는다. 감시 표의 행으로 끝나면 정리 분기에 들어가지 않고 그 tick에 발행을 멈추고 끝낸다. 결과의 `last_item_index`와 `items_completed`는 0이고 feedback phase는 PREPARING이다.
- 같은 tick의 순서: 감시 표(순위 1-8) -> 확인 기한 -> 확인(3회 연속) -> 취소.
- 확인 기한: `arm_timeout`은 arm을 처음 보낸 시각부터 첫 ARMED 표본을 볼 때까지만 흐른다. 첫 ARMED 표본을 본 tick부터는 그 시각 기준 `mode_confirm_timeout`(3 s) 안에 확인 3회가 차야 한다. P6의 최대 길이는 `arm_timeout + mode_confirm_timeout`이다. 첫 ARMED 표본은 표본 하나로 정해지는 관측이므로 같은 tick의 `arm_timeout` 만료보다 앞이다(그 tick에 ARM_REJECTED로 끝내지 않고 확인 기한을 시작한다).
  - 이유: arm이 TEMPORARILY_REJECTED 재시도 끝에 늦게 받아들여지면(예: arm 전송 뒤 4.2 s) `arm_timeout`(5 s)까지 남은 시간에 약 2 Hz인 표본 3개가 차지 않는다. 기한을 그대로 두면 정상 PX4에서 arm이 받아들여졌는데 ARM_REJECTED와 정리 분기로 끝난다. `mode_confirm_timeout`은 3회 연속 확인을 위한 값이다(쟁점 10. 3회 연속 약 1.0 s, 표본 1개 유실 때 1.5 s).
  - 확인 기한에 닿는 것은 `vehicle_status`가 `link_timeout`보다 짧은 간격으로 오기는 하는데 확인 3회가 차지 않는 경우다. `timestamp`가 늘지 않는 표본만 오거나, 표본이 드문드문 와서(예: 0, 1.5, 3.0 s) 서로 다른 표본 3개가 3 s 안에 차지 않는 경우다([추정] 정상 PX4의 2 Hz 이상 발행에서는 나오지 않는다. 표본이 `link_timeout` 동안 아예 오지 않으면 순위 3이 먼저 끝낸다). 그때는 ARM_REJECTED와 정리 분기로 끝내고 `detail`에 ARMED를 관측했으나 확인되지 않았다고 적는다.
- 1회 판정의 근거([소스]. 실측은 없고 재실측 (3), (5)와 시나리오 A의 원시 표본 기록의 통과 기준이다. 넘김 목록)
  - `Commander.cpp` `run()`의 한 주기 순서는 1843행 `handleAutoDisarm`, 1866행 `handleModeIntentionAndFailsafe`, 1898행 `handle_command`(arm 처리), 1932-1945행 발행이다. `arm()`(549-635행)은 `arming_state`만 바꾸고 모드와 사용자 의도를 건드리지 않는다. 그래서 arm이 처리된 주기의 첫 ARMED 표본은 그 주기 앞에서 disarm 상태로 계산한 `nav_state`(의도대로 OFFBOARD)와 `failsafe` false를 싣는다(`framework.cpp` 452-455행).
  - 다음 주기부터 arm 상태에서만 켜지는 failsafe 조건이 들어간다. 이 프로젝트의 SITL 파라미터에서 RC 손실(`COM_RC_IN_MODE=4`)과 GCS 손실(`NAV_DLL_ACT=0`)은 꺼져 있고, offboard 신호는 P4에서 확인한 뒤 20 Hz로 이어지며, spoolup 구간의 ESC 실패와 배터리 이상은 동작이 Disarm이라 같은 주기의 표본이 DISARMED다.
  - 따라서 ARMED이면서 OFFBOARD가 아닌 표본은 failsafe(`failsafe == true`)이거나 외부 모드 변경(`failsafe == false`이고 의도가 OFFBOARD가 아님)일 때만 나온다. 감시 표의 순위 6-8이 이 둘을 가른다.
- 정리 분기에 넣지 않는 이유: [소스] failsafe 중에 들어온 모드 변경 요청은 user takeover로 처리되어 failsafe 동작이 풀린다(`Commander.cpp` 2352-2354행, `framework.cpp` 502-518행). 공중 분기의 Hold는 PX4가 고른 failsafe 동작을 덮어쓰고, 외부 모드 변경이면 기체를 넘겨받은 쪽의 모드를 다시 바꾼다. P6의 ARMED 확인 구간은 TAKEOFF와 같은 물리 상태(P3부터 목표점을 발행하므로 arm과 함께 이륙 램프가 시작된다)이므로 같은 관측에 같은 동작을 낸다.
- 기각: ARM_REJECTED(arm은 받아들여졌다), MODE_SWITCH_FAILED(확인된 OFFBOARD를 다른 주체가 바꾼 것이다), 새 상수(구별해 쓸 소비자가 없다), 3회 연속 판정(위 [소스]), ARMED를 처음 관측한 tick에 TAKEOFF를 시작하기(P6의 정의와 항목 `timeout`의 기준이 바뀐다).

PREPARING(첫 항목이 LAND): P0 -> 시작 조건(armed이고 `landed == false`, 아니면 PRECONDITION_FAILED) -> P2 -> LAND 항목. Offboard 진입과 arm을 하지 않고 `offboard_control_mode`와 `trajectory_setpoint`를 한 번도 발행하지 않는다. `ready_timeout`으로 NOT_READY가 되면 기체는 공중에 있던 모드(보통 Hold)로 남고 그 뒤는 취소를 요청한 쪽과 PX4 failsafe의 몫이다.

항목

| 항목 | 시작 | 동작 | 완료 | feedback phase |
| --- | --- | --- | --- | --- |
| TAKEOFF | P6의 ARMED 확인 시점(항목 `timeout`이 여기서 흐른다) | 목표점은 P3에서 읽은 위치의 z만 `-height_m`. yaw는 항상 유한값(MODE_KEEP이면 그때의 heading). 처음부터 목표점을 보낸다 | `z_valid`이고 `abs(z - z_target) < acceptance_m` | EXECUTING |
| LOITER | 앞 항목 완료 | 직전 setpoint 유지(PX4 Hold 모드가 아니다) | ROS 시각으로 `duration` 경과 | EXECUTING |
| LAND | 앞 항목 완료 또는 PREPARING 끝 | 발행 중이면 유지한 채 NAV_LAND 재전송. AUTO_LAND를 처음 관측하면 발행 중단(다시 켜지 않는다). AUTO_LAND 3회 연속(`mode_confirm_timeout`, 넘기면 MODE_SWITCH_FAILED). 확인 전에는 모드 이탈 판정을 하지 않는다(아래 LAND 감시) | DISARMED 3회 연속. 대비책: `landed`인 채 `land_disarm_fallback_delay`(노드 파라미터) 동안 arm이면 강제가 아닌 disarm | WAITING_MODE |

- 모든 항목은 `timeout`을 넘기면 ITEM_TIMEOUT. 이때의 정리: setpoint 항목이면 취소와 같이 그 tick의 snapshot으로 분기를 고르고 매 tick 다시 고른다. 공중이면 Hold 분기(확인되지 않으면 Land를 보낸다), 지상 arm이면 disarm 분기(지상 setpoint. 쟁점 3 M5), 지상 disarm이면 바로 끝낸다(이 goal에서 arm을 보낸 적이 있으면 disarm 분기를 거친다. 1a에서 setpoint 항목이 있는 미션은 늘 arm을 보낸 뒤다). 어느 분기든 결과는 ABORTED이고 reason은 ITEM_TIMEOUT을 유지하며, Hold나 disarm이 확인되지 않았으면 `detail`에 적는다(REASON_MODE_SWITCH_FAILED나 REASON_DISARM_FAILED로 바꾸지 않는다).
  - LAND 항목의 ITEM_TIMEOUT: NAV_LAND 재전송을 멈춘다. 아직 발행 중이면(AUTO_LAND를 한 번도 관측하지 못함) 발행을 멈춘다. 그 뒤는 PX4의 offboard 손실 Land(`COM_OBL_RC_ACT=4`)가 내린다. Hold는 보내지 않는다. landed인 채 ARMED였으면 `detail`에 적는다.
    - `[LAND]` 한 항목 미션의 예외: 이 미션은 발행한 적이 없고 기체가 OFFBOARD가 아니므로 offboard 손실 Land가 걸리지 않는다. AUTO_LAND를 관측하지 못한 채 ITEM_TIMEOUT이 되는 것은 항목 `timeout`이 `mode_confirm_timeout`보다 짧을 때뿐이다. 이때 NAV_LAND가 도착하지 않았다면 기체는 있던 모드(보통 Hold)에, 도착했다면 AUTO_LAND(위치가 무효면 DESCEND)로 PX4가 착륙을 이어 간다. 어느 쪽인지 `detail`에 적는다. AUTO_LAND를 확인한 뒤의 ITEM_TIMEOUT도 PX4가 착륙을 이어 간다. [소스] `Commander.cpp` 1093-1110행(NAV_LAND는 force라 사용자 의도가 즉시 AUTO_LAND로 바뀐다), 1089-1091행(Land를 쓸 수 없는 상태면 DESCEND로 대체).
  - 지상 arm 분기에서 TAKEOFF가 `timeout`까지 땅을 뜨지 못했다는 것은 사실상 이륙 의도가 켜지지 않은 경우다(timestamp 문제 등. [소스] `MulticopterPositionControl.cpp` 466-467행). 이때 Takeoff 상태는 ready_for_takeoff에 머물러 disarm이 바로 받아들여진다([실측] G).
  - 지상 arm 분기가 필요한 이유: TAKEOFF가 뜨지 못한 채 `timeout`이 되면 기체는 지상 arm이다. 여기서 Hold만 받고 끝내면 기체가 지상에 arm으로 남는다([소스] 이륙 이력이 없어 자동 disarm이 없다. `Commander.cpp` 2290, 2294행. `COM_DISARM_PRFLT=-1`). 그 상태에서는 `[LAND]`도 PRECONDITION_FAILED다.
- `latest_disarming_reason`은 판정에 쓰지 않는다([실측][소스] 메시지 상수가 내부 enum과 어긋난다).

발행 규칙: `trajectory_setpoint`와 `offboard_control_mode`는 `nav_state`가 OFFBOARD이거나 Offboard로 들어가는 중(P3-P6)일 때만 발행한다. 모드 명령(NAV_LAND, Hold)을 보낸 뒤 그 모드를 처음 관측한 tick에 멈춘다. [실측] 착륙 중 발행을 유지한 2회는 착지 뒤 60-90 s 동안 `landed`가 나오지 않았고, 멈춘 2회는 약 1 s 뒤에 나왔다. 지상 arm 분기의 지상 setpoint도 이 규칙 안에 있다. 발행 중일 때만 바꿔 발행하고 멈춘 발행을 다시 켜지 않는다.

`Px4Timestamp` 공급이 실패한 tick: 출력(setpoint와 명령)을 모두 버리고 ABORTED로 끝낸다. reason은 ITEM_TIMEOUT이나 PREPARING 실패의 정리 중이면 원래 것, 그 밖은 INTERNAL이다. 발행이나 명령을 한 번이라도 했으면 `detail`에 "vehicle state unknown, may remain armed on ground"를 더한다. 끝나는 tick에 보내려던 마지막 명령(disarm, NAV_LAND)은 버리고 결과는 유지한다. P6에서 ARMED를 처음 관측한 뒤와 setpoint 항목 실행 중에는 감시 표의 순위 1로 판정 맨 앞에서 본다.

비행 중 감시(P6에서 ARMED를 처음 관측한 tick부터 setpoint 항목이 끝날 때까지. 들어감은 3회 연속, 벗어남은 1회)

| 순위 | 관측 | reason | 동작 |
| --- | --- | --- | --- |
| 1 | `Px4Timestamp::now` 실패 | INTERNAL | 발행 중단, ABORTED. 명령에 실을 시각이 없어 disarm을 보내지 않는다 |
| 2 | 식별 대조 불일치 | INTERNAL(M2) | 발행 중단, arm을 보냈으면 disarm 1회(`landed`를 보지 않는다. 아래), ABORTED |
| 3 | `vehicle_status`가 `link_timeout` 동안 없음 | LINK_LOST | 발행 중단, 지상 disarm 1회(아래), ABORTED |
| 4 | DISARMED이고 `landed == false`(아래 고정 규칙으로 읽은 값) | FAILSAFE | 발행 중단, ABORTED |
| 5 | DISARMED이고 `landed == true`(같은 고정 규칙) | 이 표본의 `failsafe`가 true이거나, 이력 구간(아래) 안의 앞선 표본에서 `failsafe == true`를 한 번이라도 봤으면 FAILSAFE, 아니면 EXTERNAL_DISARM. 이 표본의 `nav_state`는 보지 않는다(아래) | 발행 중단, ABORTED. `detail`에 지상 disarm임을 적는다 |
| 6 | `nav_state != OFFBOARD`이고 `failsafe == true` | FAILSAFE | 발행 즉시 중단, 지상 disarm 1회(아래), ABORTED |
| 7 | `nav_state != OFFBOARD`이고 `failsafe == false`이고 `nav_state_user_intention != OFFBOARD` | EXTERNAL_MODE_CHANGE | 발행 즉시 중단, 지상 disarm 1회(아래), ABORTED |
| 8 | `nav_state != OFFBOARD`이고 `failsafe == false`이고 `nav_state_user_intention == OFFBOARD` | FAILSAFE(방어용. [소스] 정상 상태에서는 나오지 않는다) | 발행 즉시 중단, 지상 disarm 1회(아래), ABORTED |

- 감시 표의 행으로 끝나는 goal은 정리 분기에 들어가지 않는다.
- 지상 disarm 1회(순위 3, 6, 7, 8): 아래 셋이 모두 참이면 발행을 멈춘 그 tick에 강제가 아닌 disarm을 한 번 보내고 확인 없이 끝낸다. `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground"를 적는다.
  - 조건 1: 이 goal이 arm을 보냈다.
  - 조건 2: 첫 ARMED 표본 뒤에 받은 `landed` 값이 한 번도 false가 아니었다(goal 동안 유지하는 이력이다. 항목이 바뀌어도 지우지 않는다).
  - 조건 3: 그 tick의 최신 `landed`가 true다(순위 3에서는 끊기기 전의 값이다. `vehicle_land_detected` 표본이 없으면 보내지 않는다).
  - 근거 [소스]: 이륙 이력(`_have_taken_off_since_arming`)은 arm 상태에서 `landed`가 true에서 false로 바뀌면 생기고(`Commander.cpp` 2136-2140행), 착지 자동 disarm(`COM_DISARM_LAND` 2 s)은 이륙 이력이 있어야 동작한다(2290행). 이 프로젝트는 `COM_DISARM_PRFLT=-1`이라 한 번도 뜨지 않은 지상 arm은 failsafe Land나 외부 모드에서 스스로 disarm되지 않는다. 노드의 disarm이 필요한 것은 그 경우뿐이고 이륙 이력이 생긴 뒤는 PX4가 맡는다. 그래서 LOITER는 따로 막지 않아도 빠진다(TAKEOFF가 끝났다면 보통 `landed` false를 이미 봤다. [실측] H, K: 높이 0.07 m에서 이미 false. `height_m`이 아주 작아 false를 보지 못한 채 LOITER에 들어간 경우에는 조건이 그대로 참이고, 그때 기체는 뜨지 않은 지상 arm이므로 보내는 것이 맞다).
  - 안전: 강제가 아닌 disarm은 PX4가 `landed || maybe_landed`라고 볼 때만 받아들인다(`Commander.cpp` 644-662행). 노드가 짧은 false 표본을 놓쳤거나 `landed` 값이 낡았어도 떠 있는 기체는 꺼지지 않는다.
  - disarm은 모드 변경 요청이 아니라서 failsafe 중에 보내도 user takeover를 일으키지 않는다([소스] `disarm()`이 부르는 `onDisarm`(`UserModeIntention.cpp` 94-101행)은 `_had_mode_change`를 세우지 않는다. 세우는 곳은 `change()`의 75행뿐이다). 확인을 기다리지 않고 재전송하지 않으므로 기체를 넘겨받은 쪽과 겨루지 않는다. 넘겨받은 쪽이 비행을 원하면 다시 arm하면 된다.
  - 순위 3의 근거: `vehicle_status`만 끊기고 `/fmu/in`은 살아 있을 수 있다.
- 순위 2의 disarm 1회: 이 goal이 arm을 보냈으면 `landed`를 보지 않고 강제가 아닌 disarm을 한 번 보내고 확인 없이 끝낸다. `detail` 문구는 위와 같다. M2의 PREPARING 규칙(첫 ARMED 표본 전)과 같은 규칙이다.
  - 조건 2와 3을 쓰지 않는 이유: 순위 2는 같은 네임스페이스에 다른 발행자가 있을 수 있는 경우다. `vehicle_land_detected`에는 식별 필드가 없어서, 남의 `landed` false 표본 하나로 조건 2가 깨지면 한 번도 뜨지 않은 우리 기체에 disarm이 나가지 않고 지상 arm으로 남는다.
  - 이 disarm은 기대 sysid로 주소를 정하므로 우리 기체가 맞다면 받아들여지고, PX4 sysid가 기대와 다르면 PX4가 `target_system` 불일치로 무시한다([소스] `Commander.cpp` 746행). 떠 있는 기체에서는 거부된다(644-662행. 이때 PX4가 "Disarming denied: not landed"를 한 번 남긴다). 어느 쪽이든 해가 없고, 확인하지 않으므로 `detail`의 "may remain armed on ground"가 맞다.
  - 실측은 없다(재실측 (4)의 기록 항목. 넘김 목록).

- 한 tick에 여러 행이 맞으면 순위가 앞선 행이 이긴다. 순위는 같은 tick의 동률만 가른다. 조건이 엇갈려 시작하면(어느 tick에 한 행만 맞고 다음 tick에 순위가 앞선 행이 맞는 경우) 먼저 맞은 행이 그 tick에 goal을 끝내고, 그 뒤의 표본은 효과가 없다. 표 머리의 "들어감은 3회 연속, 벗어남은 1회"를 행별로 적으면: 순위 1, 2, 4-8은 모두 1회 판정이다(실패 한 번, 어긋난 표본 하나, 해당 표본 하나). 순위 3만 누적이다(마지막 `vehicle_status` 수신 뒤 ROS 시각으로 `link_timeout`). 3회 연속은 이 표가 아니라 확인(OFFBOARD, ARMED, AUTO_LOITER, AUTO_LAND, DISARMED)에 쓴다. 이 순위는 재실측 (4) 전까지 잠정이다. 근거는 셋이다.
  - 순위 1-3은 나머지 행의 입력을 믿을 수 없게 하는 조건이다. 시각을 만들 수 없으면 발행 자체가 안 되고, 식별이 어긋난 `vehicle_status`는 이 기체의 것이 아닐 수 있으며, 상태가 끊기면 아래 행이 읽을 값이 없다. 식별 불일치가 아래에 있으면 남의 기체의 표본으로 FAILSAFE가 먼저 나갈 수 있다.
  - 순위 4-5(arming 상태)가 6-8(모드)보다 앞이다. disarm된 뒤의 `nav_state`는 확인된 사실이 없다. "지상에서 외부 disarm되면 `nav_state`는 OFFBOARD로 남는다"는 실측이 없고, 한 표본이라도 OFFBOARD를 벗어나면 모드 행이 먼저 걸려 방어용 FAILSAFE(순위 8)가 된다. arming 상태를 먼저 보면 `nav_state`가 어떻게 되든 같은 reason이 나온다.
  - 순위 6-8은 조건이 서로 겹치지 않아 그 안의 순서는 뜻이 없다. 순위 4와 5도 겹치지 않는다.
  - 순위 5의 `failsafe` 가지: 지금 표본의 `failsafe`만 보면 자동 disarm에서는 이 가지가 걸리지 않는다. [소스] `Commander.cpp` 1843행 `handleAutoDisarm()`이 1866행 근처 `handleModeIntentionAndFailsafe()`보다 앞에서 disarm하고, 후자는 `state.armed = isArmed()`(2346행 근처)로 읽으며 `framework.cpp` 452-455행은 disarm이면 `Action::None`이다. 그래서 자동 disarm 주기의 첫 DISARMED 표본은 `failsafe == false`이고 `nav_state`는 의도로 되돌아가 있다.
    - 이력의 구간: TAKEOFF로 시작하는 미션의 첫 항목은 첫 ARMED 표본부터(그 표본 포함) 그 항목이 끝날 때까지다. P6의 ARMED 확인 구간과 TAKEOFF가 한 구간이다(같은 물리 상태라 1 tick 차이로 분류가 바뀌지 않게 한다). 그 뒤의 항목은 항목이 시작된 뒤에 받은 표본부터다. 첫 ARMED 표본 전의 DISARMED 표본은 넣지 않는다(지상 preflight 상태의 `failsafe` 값이 섞인다).
    - 이력에 "OFFBOARD가 아닌 표본"은 넣지 않는다. 이 표는 벗어남을 1회로 판정하므로 OFFBOARD가 아닌 ARMED 표본은 순위 6-8에서 그 tick에 goal을 끝낸다. 앞선 표본의 "OFFBOARD 아님" 이력은 생길 수 없다.
    - 정한 것: 이력에 지금의 DISARMED 표본을 넣지 않는다. 그 표본의 `nav_state`는 보지 않는다. 넣으면 외부 disarm 뒤 `nav_state`가 OFFBOARD를 떠나는 경우가 모두 FAILSAFE가 되어 EXTERNAL_DISARM이 나오지 않게 되고, 순위 4-5를 모드 행보다 앞에 둔 이유(disarm 뒤의 `nav_state`는 확인된 사실이 아니다)와도 어긋난다.
    - 이 가지가 걸리는 경우: 이 표본의 `failsafe`가 true인 DISARMED는 명령 disarm과 failsafe 동작 Disarm(`COM_OBL_RC_ACT`가 Disarm인 경우, GCS 손실 Disarm. `Commander.cpp` 2375-2377행)에서 나온다. 앞선 표본의 `failsafe` 이력은 v1.17.0에서 OFFBOARD인 채로는 생기지 않으므로([소스]) 이 가지는 방어용이다. failsafe 동작 Disarm에서는 `nav_state`가 OFFBOARD로 남고 `landed`에 따라 순위 4나 5의 FAILSAFE가 된다. 이 프로젝트의 SITL 파라미터는 Land라 이 경로에 닿지 않는다.
    - 이력 가지의 테스트는 합성 표본으로만 할 수 있다(실제 PX4 v1.17.0에서는 만들 수 없다).
    - 덮지 못하는 경우: failsafe Land로 OFFBOARD를 벗어난 ARMED 표본을 노드가 놓친 채 자동 disarm된 경우뿐이다. [소스] failsafe가 걸리는 주기에 `nav_state`와 `failsafe`가 바뀌면 `vehicle_status`가 즉시 publish되고(`Commander.cpp` 1941-1945행) 자동 disarm(`COM_DISARM_LAND` 2 s)은 그 뒤이므로, 그 표본은 보통 순위 6에서 goal을 끝낸다. 놓치는 것은 수신이 끊겼거나, tick당 최신 표본 1개 모델에서 50 ms 안에 표본이 연달아 온 경우다. 그때의 첫 DISARMED 표본은 외부 disarm과 구별할 값이 없어 EXTERNAL_DISARM이 된다. 의미 문장이 "원인은 판정하지 않는다"이므로 틀린 말이 되지는 않는다.
- disarm 분류의 고정 규칙: disarm의 분류(지상 대 공중)는 처음 관측한 DISARMED 표본의 tick에, 그때까지 받은 최신 `landed` 값으로 정하고 고정한다. 뒤에 오는 `landed` 표본으로 바꾸지 않는다. 이 규칙은 감시 표의 두 DISARMED 행, LAND 감시의 완료 우선 규칙, 취소의 Hold 확인 창에서 본 DISARMED에 모두 쓴다. 근거: [소스] `MulticopterLandDetector.cpp` 249, 287, 296행(`return !_armed || ...`)과 318-320행(LNDMC_TRIG_TIME/3 지연). 공중에서 disarm돼도 약 0.33 s 뒤 `landed`가 true로 바뀌어 발행된다. 고정하지 않으면 공중 disarm이 지상 disarm(CANCELED 또는 완료)으로 잘못 분류될 수 있다.
- 지상 DISARMED 행(순위 5): TAKEOFF가 뜨기 전에 외부에서 disarm되면 모드 행에 걸리지 않을 수 있다. 이 행이 없으면 ITEM_TIMEOUT까지 발행이 이어진다. disarm 뒤의 `nav_state`는 확인된 사실이 아니다. "`nav_state`는 OFFBOARD로 남는다"는 [소스]에 기댄 추정이다(`UserModeIntention.cpp` 78-84행과 94-101행, `framework.cpp` 452-455행. OFFBOARD가 `modePreventsArming`에 걸리는지는 확인하지 못했다). 실측(재실측 (4)) 전에는 사실로 쓰지 않으며, 순위 4-5를 모드 행보다 앞에 둔 것이 이 불확실성을 덮는다. reason을 상수 REASON_EXTERNAL_DISARM으로 둔 이유는 쟁점 3에 있다.
- 방어용 분류(순위 8): [소스] `framework.h` 150행: `inFailsafe`는 None과 Warn이 아닐 때 참이다. `framework.cpp` 684-690행: None과 Warn에서는 `nav_state`가 사용자 의도와 같다. `Commander.cpp` 2369-2372, 2388행.
- OFFBOARD이고 ARMED인 채 `failsafe == true`인 표본은 어느 행에도 걸리지 않고 goal을 끝내지 않는다. 표대로가 의도다. [소스]로는 정상 상태에서 나오지 않는다. None과 Warn이 아니면 failsafe 동작이 모드를 바꾼다. 예외는 Disarm(같은 주기에 DISARMED 표본이 된다)과 Terminate(`nav_state`가 TERMINATION이 된다)다. `COM_FAIL_ACT_T`의 지연 중에는 선택된 동작이 Hold라 AUTO_LOITER와 `failsafe` true로 순위 6에 걸린다. 만약 나왔다면 goal을 계속하는 것이 안전하다. 모드를 바꾸지 않는 failsafe이고, 발행을 멈추면 offboard 손실 failsafe를 스스로 일으킨다. 다음 표본의 모드 이탈은 순위 6-8이 잡는다. 그 표본의 `failsafe`는 순위 5의 이력에 남는다.
- failsafe로 OFFBOARD를 벗어난 표본(순위 6)을 보면 즉시 멈추는 이유: [실측] offboard 손실 Land 중에 발행만 다시 시작하자 모드 명령 없이 0.07 s 만에 OFFBOARD로 돌아갔다(1회). Executor가 발행을 이어 가면 착륙 중인 기체가 다시 올라간다.
- LAND 항목(WAITING_MODE)의 감시는 세 구간으로 나뉜다.
  - 확인 전(NAV_LAND를 보낸 뒤 AUTO_LAND 3회 연속까지): 모드 이탈 판정을 하지 않는다. 항목 시작 때의 `nav_state`는 AUTO_LAND가 아니기 때문이다(정식 미션이면 OFFBOARD, `[LAND]` 한 항목 미션이면 보통 AUTO_LOITER). 이 구간에서 보는 것은 `mode_confirm_timeout`(MODE_SWITCH_FAILED), 상태 없음(LINK_LOST), 항목 `timeout`뿐이다. 발행 규칙은 이 구간에서도 그대로 적용한다. OFFBOARD도 AUTO_LAND도 아닌 표본을 보면 발행을 멈추고 다시 켜지 않는다. 이탈 판정은 하지 않고 NAV_LAND 재전송과 `mode_confirm_timeout`만 이어 간다. `mode_confirm_timeout`은 지상 DISARMED 계수 중에도 흐른다. 같은 tick이면 MODE_SWITCH_FAILED가 ITEM_TIMEOUT보다 먼저다.
  - AUTO_LAND 확인(3회 연속)은 `failsafe` 값과 무관하게 `nav_state == AUTO_LAND`로 센다. offboard 손실 Land 중인 기체에 보낸 `[LAND]`도, 흔들림 뒤 발행 중단으로 생긴 failsafe Land도 정상 경로다.
  - 처음 관측과 3회 연속 사이의 흔들림: AUTO_LAND를 한 번 본 뒤 다른 모드 표본이 오면 연속 계수를 0으로 되돌릴 뿐 이탈로 보지 않는다. 멈춘 발행은 다시 켜지 않고(켜면 Offboard로 돌아갈 수 있다) NAV_LAND 재전송을 이어 가며, `mode_confirm_timeout`은 NAV_LAND를 처음 보낸 시각부터 그대로 흐른다.
  - 확인 뒤: 모드 이탈 판정은 ARMED인 동안만 적용한다. ARMED인데 AUTO_LAND에서 벗어나 다른 모드가 되면 EXTERNAL_MODE_CHANGE(`failsafe`이면 FAILSAFE).
  - 어느 구간에서든 DISARMED이고 `landed`이면 `nav_state`가 무엇이든 이탈로 보지 않고 완료 계수(DISARMED 3회 연속)가 우선한다. 이유: [실측] 자동 disarm과 동시에 `nav_state`가 AUTO_LAND를 떠나 사용자 의도의 모드로 돌아간다(`UserModeIntention`의 disarm 처리). 1회 이탈 규칙을 그대로 쓰면 정상 착륙이 EXTERNAL_MODE_CHANGE로 끝난다. `landed`가 아닌 채 DISARMED는 FAILSAFE다. 여기의 `landed`는 위 disarm 분류의 고정 규칙으로 읽는다.
  - 완료 우선 규칙이 두 경우를 다 덮는 근거([소스]): 정상 착륙에서 "ARMED인데 AUTO_LAND가 아닌" 표본은 나오지 않는다. 자동 disarm(`Commander.cpp` 1843행 handleAutoDisarm, 675행 onDisarm)이 같은 주기의 `nav_state` 계산(1866, 2369-2372행)과 발행(1945행)보다 앞서므로 DISARMED와 새 `nav_state`가 한 표본에 같이 온다. 대비책 disarm처럼 명령으로 내는 disarm은 `nav_state` 계산 뒤에 처리되어(1898행) "DISARMED + AUTO_LAND" 표본이 한 번 나온 다음 `nav_state`가 바뀐다.
- CANCELING 중에는 감시 표를 쓰지 않고 쟁점 3의 분기만 본다.

명령 재전송 규칙(값은 px4-engineer가 정한다): 대기 중인 명령은 한 번에 하나다. 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 즉시 지운다. ack는 `command`와 `target`으로 맞춘다. 주기는 `command_resend_period`(0.5 s)다. 거부 ack는 ACCEPTED와 IN_PROGRESS가 아닌 것이다.

| 명령 | 재전송을 멈추는 때 | 거부 ack |
| --- | --- | --- |
| DO_SET_MODE(Offboard) | OFFBOARD 3회 연속, 타임아웃 | 거부이면 MODE_SWITCH_FAILED(IN_PROGRESS는 거부가 아니다) |
| ARM | ARMED를 처음 관측한 tick, 타임아웃, 취소나 실패를 정한 tick(즉시) | ARMED를 처음 관측하기 전에만 본다. TEMPORARILY_REJECTED는 재시도, 그 밖의 거부는 ARM_REJECTED |
| Hold | AUTO_LOITER 3회 연속, `hold_confirm_timeout`, 정리의 상한 | 거부면 즉시 Land 경로 |
| NAV_LAND(LAND 항목) | AUTO_LAND 3회 연속, `mode_confirm_timeout`(MODE_SWITCH_FAILED), ITEM_TIMEOUT | force라 거부가 없다([소스] `Commander.cpp` 1093-1110행) |
| NAV_LAND(M4의 Land 경로) | AUTO_LAND를 처음 관측한 tick(그 tick에 ABORTED로 끝난다), `mode_confirm_timeout`, 정리의 상한 | NAV_LAND(LAND 항목) 행과 같다(force라 거부가 없다) |
| DISARM(지상 arm 분기) | DISARMED 3회 연속, `landed` false로 분기 전환, `mode_confirm_timeout`, `link_timeout`(상태 끊김), 정리의 상한 | TEMPORARILY_REJECTED여도, 그 밖의 거부여도 `landed`인 동안 재시도. 그 자리에서 끝내지 않는다 |
| DISARM(LAND 대비책) | DISARMED 3회 연속(항목 완료), 항목 `timeout`(ITEM_TIMEOUT). 따로 타임아웃을 두지 않는다. `landed == true`이고 `land_disarm_fallback_delay`가 지난 뒤에만 시작한다 | DISARM(지상 arm 분기) 행과 같다(거부 ack는 종류와 무관하게 `landed`인 동안 재시도) |

- 같은 명령을 여러 번 받아도 결과가 같다. 이미 disarm된 기체에 보낸 disarm은 ACCEPTED다([소스] `Commander.cpp` 640-642, 976-980행. [실측] disarm 실험).
- arm을 보낸 뒤의 DISARM 확인은 disarm 전송 뒤에 받은 표본만 센다(쟁점 3 M5).
- 끝내는 tick에 한 번 보내는 명령(지상 disarm 1회, 정리의 상한에서의 disarm과 NAV_LAND, PREPARING의 식별 불일치에서의 disarm)은 재전송하지 않고 확인을 기다리지 않는다. 끝나는 tick의 명령은 늘 하나다.
- 대비책 disarm이 공중 기체를 끌 위험은 없다(강제가 아닌 disarm은 `landed || maybe_landed`가 아니면 거부된다).

끝난 뒤 기체 상태(7단계 `docs/interface.md`의 reason별 "ABORTED 뒤 기체 상태" 표에 넣을 줄. 표 전체는 7단계에 px4-engineer와 만든다)

| 끝난 방식 | 기체 상태 | 근거 |
| --- | --- | --- |
| 지면 바로 위에서 Hold로 끝난 ITEM_TIMEOUT 또는 CANCELED | ARMED, `landed` false인 채 지상이나 지면 근처에 머문다. 스스로 disarm되지 않는다(12 s 관찰). 이어 보낸 `[LAND]` 미션은 시작 조건(armed이고 `landed` false)을 통과한다 | [실측] Hold로 끝나는 경로의 표본은 X2a 1.8 s 1회와 X2b 1회(각 12 s 관찰, 스크립트가 보낸 명령). 같은 Hold 상태에서 스크립트가 보낸 NAV_LAND 3회가 disarm까지 갔다. Executor가 보낸 `[LAND]`는 미실측 |

source 값 표(1a 4단계 넘김 (1))

| 주체 | source_system | source_component |
| --- | --- | --- |
| `idsim_mission` Executor | 254 | 191 |
| SITL 통합 테스트 fixture | 254 | 25 |
| 스모크 `check_px4.py` | 254 | 1 |

- 규칙: source_system은 어떤 기체 sysid와도 같지 않다(빌더가 거부한다. 쟁점 5). 255와 component 190은 쓰지 않는다. Executor의 값은 노드 선언 기본값이다(역할 상수라 생성하지 않는다).

SITL 파라미터는 바꾸지 않는다. `Dockerfile.px4`도 바꾸지 않는다.

닫힌 넘김 항목: 1a 4단계의 (1) source 표, (2) position flag 고정(쟁점 5의 헬퍼), (3) `/clock` 지연과 `COM_OF_LOSS_T` 여유([실측] 노드 sim 시각 - `vehicle_status.timestamp` 최대 180 ms, 여유 약 0.77 s. 회귀 판정은 시나리오 A의 단정과 fixture 사전조건), (4) 신호 없는 Offboard 요청([실측] 시동 해제면 ACCEPTED이고 그 상태의 arm이 TEMPORARILY_REJECTED). 5단계의 Hold 실험, failsafe 파라미터 기본값 대조, `acceptance_m` 0.3 m, Offboard 상승 속도 제한([소스] `MPC_Z_VEL_MAX_UP`), land 완료 판정.

실측하지 않고 남는 것: 위치 무효에서 Hold가 거부되는 경로(계약 분기는 ack와 `nav_state`로 이미 덮는다), arm 상태에서 신호 없는 Offboard 요청, CI 4 vCPU 조건. 모든 실측은 경우마다 1-4회이고 16 vCPU 호스트 한 대에서 했다.

## 쟁점 5. idsim_common 추가 항목

결정: 아래를 `idsim_common`에 더한다. 소유는 ros2-engineer, PX4 필드 표는 px4-engineer가 승인한다. P2(단독 PR)다.

| 항목 | 내용 | 테스트 |
| --- | --- | --- |
| `VehicleId` | `parse(text)`: ROS 이름 토큰 하나("/" 없음, 비어 있지 않음). `matches(VehicleNamespace)`: ns == "/" + id. N을 뽑지 않는다 | 다중 토큰, 앞 "/", 빈 문자열 거부. 일치와 불일치 |
| vehicle params 해석 | `parse_vehicle_params(id, ns, sysid)`(순수 함수)와 노드에서 선언하는 얇은 `declare_vehicle_params(node)`. key는 `vehicle.id`, `vehicle.ns`, `vehicle.sysid` | 순수 함수만(노드 생성 없음) |
| Options overload | `px4::create_subscription`, `create_publisher`가 `SubscriptionOptions`, `PublisherOptions`를 받는 판(callback group 지정용). 이름과 QoS 고정은 그대로 | 컴파일 확인 |
| setpoint 헬퍼 | `offboard_position_mode(Px4Timestamp)`: position만 true. `position_setpoint(Px4Timestamp, ned, yaw_ned)`: 위치와 yaw가 유한해야 하고(아니면 nullopt) velocity, acceleration, jerk, yawspeed는 NaN | 필드 표 대조, 비유한 거부 |
| 사건 QoS | `event_pub_qos()`, `event_sub_qos()`: RELIABLE, VOLATILE, KEEP_LAST 10 | 호환 검사, TRANSIENT_LOCAL 구독 대 이 발행은 불일치 |
| 빌더 `make` | `VehicleCommandBuilder`의 public 생성자를 없애고 `static std::optional<VehicleCommandBuilder> make(VehicleIdentity, CommandSource)`. `source.system() == target.sysid`이면 nullopt | 거부 1건, 기존 테스트 두 곳 수정 |

- 넣지 않는 것: `nav_state`와 `arming_state` 분류(PX4 의미라 `idsim_mission`의 `px4/`), action과 사건 토픽 이름 조립(노드가 `/px4_N` 네임스페이스에서 상대 이름 상수를 쓰면 필요 없다. `idsim_common`은 `idsim_interfaces`에 의존하지 않는다), source 값(노드 params).
- setpoint 헬퍼를 `idsim_common`에 두는 이유: /fmu/in 발행 API와 같은 곳이어야 position flag 고정이 우회되지 않는다(px4, ros2 같은 의견).
- `px4-api` lint 범위를 넓힌다(1a 4단계 미해결 항목의 답): `ros_ws/src/**/*.yaml`, launch 파일(`.py`는 이미 대상), 생성기 golden의 `params/*.yaml`. /fmu 문자열이 나오면 실패. devops-engineer가 P4에서 한다.

## 쟁점 6. idsim_mission의 소유

결정
- `ros_ws/src/idsim_mission/`은 ros2-engineer 소유다(패키지 골격, core의 검증과 상태기와 종료 결과, 노드 껍질, launch).
- 예외: `include/idsim_mission/px4/`, `src/px4/`, `test/px4/`는 px4-engineer 소유다(px4_msgs -> snapshot 변환, `nav_state`와 `arming_state`와 준비 판정 술어, ack 해석).
- 경계인 snapshot 구조체 헤더(`include/idsim_mission/core/snapshot.hpp`)는 ros2 소유이고 px4-engineer가 필수 승인자다. 승인 때 볼 것에 넣는다: "disarm 전송 뒤 받은 표본"의 기준을 core가 판정하려면 `vehicle_status.timestamp`와 명령에 실은 `Px4Timestamp`(또는 둘을 비교한 결과)가 경계를 넘어와야 한다. 지상 setpoint z 오프셋도 같은 경계로 넘어온다.
- core 입력 계약(C1): core의 `step()`은 (tick 번호, ROS 시각, 최신 표본 1개와 그 `timestamp`와 수신 tick, `Px4Timestamp` 공급 port(실패 가능), 명령 sink, setpoint sink, 사건 sink)만 입력으로 받는다. core는 벽시계와 rclcpp를 부르지 않는다. core 테스트 target은 gtest와 core만 링크한다. 구독 callback은 최신 표본만 저장하므로 tick당 표본은 최대 1개이고, 같은 `timestamp`가 두 번 보이는 것은 같은 표본을 다음 tick에 다시 본 경우이거나 같은 표본이 한 번 더 수신된 경우다(쟁점 3 M5). 감시 표 순위 1(`Px4Timestamp::now` 실패), "첫 disarm 전송 tick", "명령에 실은 `Px4Timestamp`"는 이 port로만 결정적으로 시험할 수 있다. 표본이 토픽 넷으로 나뉘는 것을 이 입력 모델에 어떻게 담을지는 ros2-engineer가 snapshot 헤더에서 정하고 px4-engineer와 test-engineer가 승인한다.
- 상태기는 ros2-engineer가 이 문서의 전이 표대로 구현한다. 전이 표와 상태기 단위 테스트는 px4-engineer가 필수 승인자, 테스트 구조는 test-engineer가 승인자다. 타임아웃 기본값과 재전송 주기 같은 PX4 절차 값은 px4-engineer가 정한다.

근거: 상태기 한 파일을 두 소유자가 나눠 가지면 수정 권한이 모호하다. 상태기는 PX4 enum을 보지 않는 순수 클래스이고 PX4 의미는 어댑터 한 곳에 모인다(PX4 태그를 올릴 때 바뀌는 곳이 어댑터뿐이다). CLAUDE.md 표의 "px4-engineer: `idsim_mission`의 PX4 인터페이스"와 맞는다. PX4 절차의 정확성은 소유가 아니라 필수 승인으로 지킨다.

px4-engineer 쪽 조건: core는 px4_msgs를 include하지 않는다(`idsim_mission_core` 대상이 px4_msgs에 의존하지 않게 CMake로 강제하고 단위 테스트가 그 대상만 링크한다). 모드 명령 송신, 발행 중단 시점, 3회 연속의 의미를 바꾸는 전이 표 수정은 px4-engineer 승인 없이 머지하지 않는다. 타임아웃 기본값은 px4-engineer가 값을 정하고 변경의 필수 승인자다(값이 적힌 노드 파일의 소유는 ros2-engineer다). 어댑터 단위 테스트(`test/px4/`)는 필드 대응과 enum 매핑을 합성 값과 전 범위 순회로 검사한다. 실측 값과의 일치는 재실측 (2), (3), (5)와 P4 SITL 시나리오가 맡는다.

단위 테스트의 구성: 정리 분기의 교차표는 상태기 수준의 원인 3(취소, ITEM_TIMEOUT, PREPARING 실패) x snapshot 3(`test_runner_cleanup.cpp`의 `CauseCrossTable`)과 고르기 순수 함수의 snapshot 5종(`test_confirm_rules.cpp`)이다. PX4 v1.17.0에서 나오지 않는 방어 경로(OFFBOARD이고 ARMED인 채 failsafe, 순위 5의 이력, 순위 8, DISARM과 ARM의 그 밖의 거부 ack)는 합성 표본과 합성 ack로만 시험한다. 단위 테스트는 합성한 `timestamp`만 검사하고, 실제 시계 관계는 재실측 (5)의 분포만이 확인한다.

기각한 안: 상태기의 PX4 절차 부분을 px4-engineer가 소유. 파일 단위로 나뉘지 않는다.

## 쟁점 7. MissionEvent QoS와 goal 전 gate

결정
- 계약 QoS는 5단계 그대로 RELIABLE, VOLATILE이다. TRANSIENT_LOCAL로 바꾸지 않는다.
- 통합 테스트의 goal 전 gate(모두 `/clock` 기준 상한 안에서): `/clock` 수신과 `now() > 0`, 자기 `mission_event` 구독의 `get_publisher_count() >= 1`, PX4 구독들의 `get_publisher_count() >= 1`, action client의 `server_is_ready()`, 기대 sysid의 `vehicle_status` 표본 1회 이상, 시나리오의 사전조건(지상, disarmed. `nav_state` 값은 사전조건에 넣지 않는다).
- 순서 규칙(필수 조건이다. [실측] P3a): 테스트는 `mission_event` 구독을 action client보다 먼저, 같은 노드(같은 participant)에서 만든다. 순서를 어기면 ACCEPTED가 빠진다(대조군 87/400. 새 프로세스 71/200, 새 노드 16/200). `tests/support`의 해당 코드에 이유를 주석으로 남긴다. 구독과 client를 다른 프로세스에 두는 구성은 재지 않았고 쓰지 않는다.
- 구독 쪽 `get_publisher_count() >= 1` gate는 사건 수신을 보장하지 않는다([실측] 누락 87건이 모두 이 조건을 만족했다). gate에는 남기되 "사건이 온다"의 근거로 쓰지 않는다. 수신을 받치는 것은 위 순서 규칙이다.
- 누락 계수 실험: [실측] "구독 생성 -> client 생성 -> 즉시 goal"(gate 없이 가장 나쁜 순서)에서 ACCEPTED 사건이 빠진 횟수는 0/400이다(새 프로세스 200회, 새 노드 200회).
- graph 조회(`count_publishers`, `get_publishers_info_by_topic`)는 맺어짐의 판정에 쓰지 않는다. 계약 QoS의 대조(Executor의 `mission_event` 발행이 RELIABLE, VOLATILE인지)에만 쓴다.
- lifecycle `get_state` 호출은 gate에 넣지 않는다.
- goal 응답은 accepted인데 ACCEPTED 사건이 없으면 `EVENT_MISSING`으로 실패시키고 재시도하지 않는다. Executor는 ACCEPTED를 낼 때 사건 발행자의 `get_subscription_count()`를 debug 로그에 남긴다.

근거
- [실측] QoS가 맞지 않아도 graph에는 발행자가 1로 보이고 구독의 matched 수는 0이다.
- TRANSIENT_LOCAL을 받지 않는 이유는 5단계와 같다(지난 실행의 사건이 새 구독자에게 현재 사건으로 보인다). 5단계의 결정을 바꿀 새 근거가 없다. `MissionEvent`의 고정 시점은 Phase 2 완료이므로 Phase 2 기록 설계에서 다시 올릴 수 있다(넘김 목록).
- 남는 위험([실측] P3a의 대조군에서 실제로 일어났다. 누락 87건 모두 Executor 쪽 `get_subscription_count()`가 0이었다. 순서 규칙을 지킨 실험군에서는 0/400. 0/400은 누락률의 95% 상한 약 0.75%를 뜻하고 16 vCPU 호스트 한 대의 값이다. 순서 규칙이 이 틈을 막는 기전은 [추정]이다: goal 요청이 서버에 닿으려면 서버가 client의 writer를 알아야 하고, 같은 participant에서 그 공지는 먼저 만든 구독의 공지 뒤에 간다. 그래서 goal이 닿았을 때는 서버가 구독도 이미 알고 있다): DDS의 match는 양쪽이 따로 한다. 구독 쪽이 맺어졌어도 Executor의 writer가 그 구독을 아직 모르면 그 사이의 ACCEPTED는 오지 않는다. 테스트에서 writer 쪽을 볼 방법이 없다. 구독을 session 시작에 걸고 그 뒤 action 서버 준비와 PX4 표본을 더 기다리므로 틈은 작다고 본다. 발생하면 `EVENT_MISSING`과 Executor의 debug 로그가 증거가 되고, 그때 이 쟁점을 다시 연다.

## 쟁점 8. 테스트의 /fmu/in 쓰기

결정
- Python으로 한다. `tests/support/px4_raw.py` 한 모듈만 PX4 토픽의 발행자를 만든다. 허용은 둘이다: `offboard_control_mode`(시나리오 T. context manager로만 만들고 끝나면 destroy), `vehicle_command`(비상 정리 전용. source가 (254, 25)가 아니면 생성 거부. 기대 sysid의 `vehicle_status`를 받아 대조한 뒤에만 발행한다). 테스트는 `trajectory_setpoint`를 발행하지 않는다.
- timestamp는 `Px4Timestamp`와 같은 변환(ROS 시각 ns / 1000)을 쓰고 그 변환을 단위 테스트로 고정한다.
- Python 쪽 PX4 토픽 이름(1a 4단계 넘김): `tests/support`에 `px4_topic(ns, direction, base, msg_cls)` 한 함수. 접미사는 `getattr(msg_cls, "MESSAGE_VERSION", 0)`에서 만든다. golden `topics.txt`와 양방향 일치 pytest를 둔다. 통합 테스트 코드에 버전 접미사가 붙은 이름이나 /fmu 문자열을 쓰지 않는다. 스모크의 정규식은 그대로 둔다.
- `px4-api` lint는 지금 `tests/`를 보지 않는다. P4에서 `tests/sitl/`과 `tests/support/`를 대상에 넣고 예외를 `tests/support/px4_raw.py`와 `px4_topic`이 든 파일로만 둔다(`px4_raw.py`의 변경은 px4-engineer가 필수 승인자다).
- Executor에 테스트 전용 파라미터나 우회 경로를 두지 않는다.

근거: 묵은 timestamp 판정은 `Px4Timestamp`를 우회해야만 만들 수 있어 C++ 노드로 가도 `idsim_common` 밖의 우회가 필요하다. 그러면 별도 실행 파일과 빌드 대상만 늘고 얻는 것이 없다. 스모크 px4-in이 이미 Python으로 `vehicle_command`를 발행하는 선례가 있다. 발행 허용 목록은 "실수 방지 수준이며 보안 경계가 아니다"(roadmap 4번).

기각한 안: `tests/` 아래 별도 C++ 테스트 노드. 위 근거.

## 쟁점 9. 시나리오와 완료 기준

결정: 한 스택에서 아래 순서로 돌린다.

| 시나리오 | 내용 | 판정 요지 | 1a 필수 |
| --- | --- | --- | --- |
| B. 무효 미션 | GOTO가 든 미션 | ABORTED, INVALID_MISSION. 접수와 종료 사건. feedback 0건. 일정 ROS 시간 동안 disarmed 유지 | 예 |
| C. id 불일치 | goal의 `vehicle_id`가 다른 값 | ABORTED, VEHICLE_ID_MISMATCH. 사건의 `vehicle_id`는 Executor 자신의 값. feedback 0건 | 예 |
| A. 정상 | `[TAKEOFF 5 m, LOITER 5 s, LAND]`, 콜드 상태 | 접수 -> ARMED -> 고도 도달 -> LOITER 유지 -> AUTO_LAND -> DISARMED -> SUCCEEDED. 이정표의 순서와 ROS 시각 단조 증가. 사건 짝과 result 일치. TAKEOFF와 LOITER 동안 `failsafe`가 한 번도 true가 아니고 `nav_state`가 OFFBOARD | 예 |
| D. 공중 취소 | 고도 도달 뒤 cancel. 이어서 `[LAND]` 한 항목 미션 | AUTO_LOITER 3회 연속, CANCELED와 REASON_NONE, 그 뒤 일정 시간 고도 유지. `[LAND]`가 SUCCEEDED이고 DISARMED. 두 번째 비행이라 시작 상태가 OFFBOARD, disarmed다. [실측] Hold(발행 없음)에서 NAV_LAND는 1회 확인됐다 | 예(U1) |
| T. 묵은 timestamp | 지상, 비행 없음, Executor idle | `offboard_control_mode`(`position=true`)만 20 Hz 발행. timestamp가 현재이면 `offboard_control_signal_lost` false, `now - 2 s`이면 true, 다시 현재이면 false. 양방향 전이를 단정한다 | 예 |

- 각 시나리오 시작 전에 사전조건(지상, DISARMED N회 연속)을 단정하고 어긋나면 그 자리에서 실패한다(앞 시나리오의 잔재를 숨기지 않는다).
- "disarm 확인"은 ARMED를 본 뒤의 DISARMED여야 한다(시작 때 이미 DISARMED라 순서를 보지 않으면 vacuous하다).
- "도달"의 입력은 goal의 목표값과 `vehicle_local_position`(goal 직전의 z0 기준, `z_valid`)이다. 노드가 낸 setpoint는 판정 입력으로 쓰지 않는다(노드와 테스트의 오류가 상관된다). architecture.md의 "setpoint 거리" 문구를 고친다.
- N은 3이다(스모크와 같다). N의 단위는 메시지 수이고, 유지 구간이 필요한 곳은 ROS 시각 경과로 따로 단정한다.
- fixture 사전조건에 `/clock` 정렬을 넣는다: `use_sim_time` 노드 시각 - `vehicle_status.timestamp`의 중앙값 절대값 < 0.1 s, 최대 < 0.5 s. 스모크 clock 단계에는 넣지 않는다(clock에는 `use_sim_time` PX4 수신 노드가 없다).
- T의 각 단계 대기 상한은 ROS 시각 5 s다(`failsafe_flags`는 5 Hz 상한이고 변화가 없으면 500 ms 주기일 수 있어 3회 연속에 1.5 s 이상이 든다).
- T가 맨 뒤인 이유: T의 발행자나 신호 상태가 뒤 시나리오의 Offboard 진입을 오염할 수 없다. T의 대조군(현재 timestamp에서 false)이 없으면 발행자가 없을 때의 true와 구분되지 않는다. T는 1a 4단계가 넘긴 "sim 시간 timestamp 경로의 회귀 판정"이고 `UXRCE_DDS_SYNCT`가 실수로 1로 돌아가면 실패한다. arm 명령을 보내지 않는 flag 판정으로 한 것은 테스트가 기체에 보내는 명령을 줄이기 위해서다([소스] 같은 `data_is_recent` 경로를 지난다). `failsafe_flags`는 5 Hz 상한으로 주기 발행되므로 "3회 연속"으로 센다. 발행 전에 발행자의 `get_subscription_count() >= 1`을 확인한다. 대조군 단계가 `local_position_invalid`가 참인 경우(timestamp와 무관하게 true)를 걸러 준다.
- 통합에서 하지 않고 core 단위 테스트로 덮는 것: BUSY, 지상 취소, NOT_READY, failsafe, EXTERNAL_MODE_CHANGE, EXTERNAL_DISARM, LINK_LOST, ARM_REJECTED, MODE_SWITCH_FAILED, DISARM_FAILED, ITEM_TIMEOUT, Hold 실패 뒤 Land, status와 reason 대응표, 종료 사건 == result, `[LAND]` 미션이 setpoint를 발행하지 않음, LAND로 시작하면 길이 1.
- 노드 배선 테스트(PX4 없이, rclcpp GoogleTest 하나): 가짜 PX4 발행자로 정상 한 경로와 무효 한 경로만.
- "3회 연속 통과"의 정의: 같은 commit, 같은 이미지 key에서 `run_sitl.sh --repeat 3`의 세 회가 모두 통과. 회마다 콜드 스택. 실패가 나오면 0부터 다시 센다. pytest rerun과 shell 재시도는 쓰지 않는다. 회차 요약(`repeat_summary.tsv`: 실행 id, commit과 dirty, 이미지 key, 시나리오별 verdict, 이정표별 ROS 시각 소요, 벽시계 소요)을 남긴다.
- 판정 기준(허용 오차, N, 타임아웃)을 느슨하게 바꾸려면 실측 분포와 함께 architect에게 올린다. 테스트를 통과시키려고 늘리지 않는다.

U1 결정에 따라 D는 1a 필수이고 `[LAND]` 한 항목 미션이 1a 노드의 지원 범위에 들어온다(쟁점 4의 PREPARING 분기).

## 쟁점 10. 타임아웃과 벽시계 가드

결정: 노드 파라미터 기본값(ROS 시각. 계약이 아니다).

| 이름 | 값 | 근거 |
| --- | --- | --- |
| `ready_timeout` | 30 s | 준비까지 약 7 s의 4배, discovery 1.1 s 포함 |
| `offboard_signal_timeout` | 2 s | 10회 발행 0.5 s + 여유 |
| `mode_confirm_timeout` | 3 s | 3회 연속 약 1.0 s, 표본 1개 유실 때 1.5 s, 명령 1회 유실 0.5 s |
| `arm_timeout` | 5 s | arm을 처음 보낸 시각부터 ARMED를 처음 관측할 때까지를 덮는다. TEMPORARILY_REJECTED 재시도(0.5 s 주기)와 arm 처리 뒤 첫 ARMED 표본까지의 시간에 대한 여유다. [실측] 정상 경로에서 arm이 4 s 이상 걸린 기록은 없다. 값은 ARMED 3회 연속까지 덮던 때에 정한 것을 유지한다. ARMED를 처음 관측한 뒤의 확인 기한은 관측 시각부터 `mode_confirm_timeout`이다(쟁점 4) |
| `hold_confirm_timeout` | 3 s | `mode_confirm_timeout`과 같은 값이다. [실측] B에서 Hold는 ACCEPTED 뒤 첫 status에 AUTO_LOITER로 보였다 |
| 지상 disarm 확인(M5) | 3 s | `mode_confirm_timeout`을 그대로 쓴다(이름을 따로 두지 않는다. 값이 같고 M5의 계약 문장이 `mode_confirm_timeout`을 가리킨다. 값이 갈려야 할 실측이 나오면 그때 나눈다). [실측] disarm부터 DISARMED까지 4-12 ms + 3회 연속 약 1.0 s |
| 정리 전체의 상한(M6) | 12 s | `hold_confirm_timeout + 3 x mode_confirm_timeout`의 파생값이다. 노드 파라미터가 아니고 configure 때 계산값을 로그로 남긴다. 근거는 쟁점 3 M6 |
| `link_timeout` | 2 s | `vehicle_status` 최소 2 Hz의 4주기 |
| `land_disarm_fallback_delay` | 5 s | [소스] `COM_DISARM_LAND` 기본값 2 s(이 프로젝트는 바꾸지 않는다) + 3 s. PX4 파라미터를 노드가 읽지 않으므로 값을 따로 둔다 |
| `command_resend_period` | 0.5 s | [실측] ack 1건 유실. `check_px4.py`와 같은 값이다 |
| 지상 setpoint z 오프셋 | +0.5 m | 노드 파라미터가 아니라 `src/px4/` 어댑터 상수다(쟁점 3 M5) |

값은 쟁점 6의 규칙에 따라 px4-engineer가 정하고 변경의 필수 승인자다. 명령별 재전송 규칙은 쟁점 4에 있다.

통합 테스트의 미션 값(테스트 입력): TAKEOFF 5 m, `acceptance_m` 0.3, timeout 20 s([실측] 6.2-7.6 s). LOITER 5 s, timeout 10 s. LAND timeout 30 s([실측] 10.9-11.1 s). goal 결과 대기 90 s(ROS 시각).

벽시계 가드
- 판정 시간은 모두 ROS 시각이다. 대기를 시작할 때 `/clock`이 없으면 `CLOCK_ABSENT`로 즉시 실패한다. 시각이 뒤로 가면 즉시 실패한다.
- 대기마다 `wall_cap = ROS 시각 타임아웃 x 3 + 10 s`. 넘었을 때 `/clock`이 벽시계 5 s 동안 진행하지 않았으면 `CLOCK_STALLED`, 진행은 했으면 `CLOCK_SLOW`다. 둘 다 `TIMEOUT_SIM`과 다른 분류이고, 판정을 느슨하게 하는 용도가 아니라 hang 방지다. trace에 RTF를 남긴다. 배수가 3이므로 RTF가 약 0.33 아래로 내려가면 ROS 시각 타임아웃보다 `wall_cap`이 먼저 걸려 `CLOCK_SLOW`가 된다. 그 경우 배수를 올려 통과시키지 않고 architect에게 올린다.
- pytest-timeout은 이미지에 없고 더하지 않는다. 전체는 wrapper가 `timeout`으로 감싸고 그 값은 CI `timeout-minutes`보다 짧게 둔다(수집이 반드시 돌게).
- 노드 쪽에는 벽시계 가드를 두지 않는다. timer가 노드 시계라 `/clock`이 멈추면 노드도 멈추고, lockstep이라 PX4도 멈춘다. bridge만 죽은 경우는 `Px4Timestamp`가 정체해 PX4가 손실로 판정하고 Land한다(원하는 동작).
- 배속은 쓰지 않는다.

## 쟁점 11. CI sitl job

결정
- trigger(U2): `pull_request`(opened, synchronize, reopened, ready_for_review. draft 제외)와 `push: main`, `workflow_dispatch`. 같은 PR의 옛 실행은 취소한다. architecture.md의 "PR당 1회"를 "PR 머리 커밋당 1회, 자동 재시도 없음"으로 고친다. lint와 unit도 `pull_request` + `push: main`으로 맞춘다(P0). 대가는 PR이 없는 브랜치 push에 CI가 돌지 않는 것이다.
- 별도 워크플로 `.github/workflows/sitl.yml`. runner `ubuntu-24.04`, `timeout-minutes: 30`, 자동 재시도 없음(다시 돌릴 때는 re-run 또는 `workflow_dispatch`), `concurrency`로 같은 ref의 옛 실행을 끊는다.
- 단계: checkout -> `tools/ci/build_images.py --mode pull`(xrce-agent, sim-base, px4, ros-ws. GHCR 로그인 없이) -> `tools/ros_ws.sh build`(별도 step) -> `tests/sitl/run_sitl.sh --stack 0` -> 아티팩트.
- 아티팩트: 실패 때 실행 디렉터리 전체(compose.yaml, stack.json, params, `px4-N/log`의 ULog, ros_log, compose logs, `sitl/`의 trace.jsonl과 graph snapshot과 junit.xml, verdict)와 `ros_ws/log/`. 보존 7일. 성공 때는 junit.xml, trace.jsonl, 단계별 시간 요약. `GITHUB_STEP_SUMMARY`에 단계별 초를 남긴다.
- 문서만 바뀐 PR은 워크플로 수준 `paths`로 거르지 않는다(필수 검사로 걸었을 때 대기 상태로 남는다). job 수준 `if`만으로는 바뀐 경로를 알 수 없으므로, 앞에 경로 감지 job(`changes`. `git diff`로 코드 경로 변경 여부를 output으로 낸다. 외부 action 없이)을 두고 `sitl` job이 `needs: changes`와 그 output을 보는 `if`로 건너뛴다. 코드 경로는 `ros_ws/**`, `docker/**`, `config/**`, `tools/**`, `tests/**`, `.github/workflows/sitl.yml`이다. main push에서는 건너뛰지 않는다.
- px4 이미지 key가 바뀌는 PR은 이미지 PR을 먼저 합친다.
- CI는 `viz`를 켜지 않는다.

GHCR 패키지 다섯이 Public인지의 화면 확인을 사용자에게 요청한다([실측] 익명 manifest 조회가 다섯 모두 200).

근거: architecture.md의 목표는 15분 이내이고 devops의 예상은 10-13분이다([추정]. pull 2-4분, build 2-3분, 기동 2-3분, 테스트 2-3분). GitHub runner 4 vCPU에서 Gazebo와 PX4 1대가 실시간에 가깝게 도는지는 실측이 없다. 첫 실행이 실험이고, 첫 3회의 단계별 시간과 RTF를 PR 본문에 기록한다. 10-13분과 판정 구간 ROS 시각 90-110 s는 둘 다 실측이 없는 추정이다.

올림 기준(P4 완료 기준에도 넣는다): `sitl` job이 15분을 넘거나 판정 구간의 RTF가 0.7 미만이면, 타임아웃이나 허용 오차나 `wall_cap` 배수를 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다. 0.7은 architecture.md의 "실시간에 가깝게"를 수치로 옮긴 architect의 기준이고 첫 3회 실측 뒤에 다시 본다. RTF의 계산: 판정 구간(첫 시나리오의 goal 전 gate가 통과한 시점부터 마지막 시나리오의 판정이 끝난 시점까지)의 ROS 시각 경과를 같은 구간의 벽시계 경과로 나눈 값이고 `run_sitl.sh`가 회차 요약에 적는다. 15분은 `sitl` job 전체의 벽시계다. 올림은 평균이 아니라 한 회 기준이다(한 실행이라도 넘으면 올린다). 첫 3회는 넘지 않아도 값을 기록한다.

## 쟁점 12. foxglove_bridge, Lichtblick, recorder

결정
- ros-ws 이미지에 `ros-${ROS_DISTRO}-foxglove-bridge`가 들어 있다(P1). 이미지 변경을 단독 선행 PR로 둔 이유: 다른 변경과 같은 PR에 섞으면 그 PR의 unit과 sitl이 GHCR에서 새 key를 찾지 못해 ros-base부터 다시 빌드한다.
- 버전: `versions.env`에 `FOXGLOVE_BRIDGE_VERSION=3.6.0`. apt로 설치한 뒤 `dpkg-query` 결과가 upstream 버전 접두와 같은지 빌드에서 단정한다. 정확한 pin은 쓰지 않는다(ROS apt 저장소는 최신 빌드 하나만 남긴다).
- `foxglove` 서비스(`viz` 프로필, ros-ws, 저장소 마운트): `address` 127.0.0.1, `port` 8765 + k, `capabilities` [connectionGraph], `topic_whitelist`는 기체마다 `^/px4_N/`(생성기에 /fmu 문자열을 쓰지 않는다), `client_topic_whitelist`, `service_whitelist`, `param_whitelist`는 아무것과도 맞지 않는 정규식(`^$`), `use_sim_time` true, `remote_access` false, `sysinfo` false. `/clock`은 화이트리스트에 넣지 않는다(250 Hz).
- `lichtblick` 서비스: `versions.env`의 `LICHTBLICK_IMAGE=ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:285adff96f24c80b511cf159e97e5395a6b154126c70c62d1199456009de07cc`(linux/amd64 manifest digest, 조회 2026-11-11). command를 `caddy file-server --listen 127.0.0.1:<18080 + k>`로 덮는다(이미지 기본은 `:8080`으로 모든 인터페이스에 연다). root로 둔다(entrypoint가 이미지 안의 `index.html`을 고쳐 쓰고 호스트에 쓰는 마운트가 없다). healthcheck 없음.
- 기본 layout 파일은 1a에 넣지 않는다(layout에 버전 접미사가 붙은 토픽 경로가 들어간다). `sim_stack.sh up --viz`가 접속 URL을 출력한다.
- Lichtblick 이미지의 label에 보이는 2.5.2는 베이스 Caddy의 버전이다([실측]). Lichtblick은 1.30.0이다.
- viz 서비스는 P5(별도 PR)다. 완료 조건은 브라우저 실접속(P5의 수동 확인): Lichtblick 1.30.0이 foxglove_bridge 3.6.0에 붙는지, clientPublish를 뺀 상태에서 연결이 유지되는지, PX4 토픽에 대한 bridge의 구독이 BEST_EFFORT인지(`ros2 topic info -v`. RELIABLE로 붙으면 수신이 없으므로 `best_effort_qos_topic_whitelist`에 넣고 lint 예외로 기록), setpoint와 `vehicle_local_position`이 같은 플롯에 놓이는지. 붙지 않으면 서브프로토콜을 기준으로 앞 버전을 고르고 architect에게 알린다.
- 1a에는 recorder 서비스를 두지 않는다. 실패 산출물은 ULog, compose logs, ros_log, 판정 trace, graph snapshot, junit이다. 이것은 architecture.md의 "실패 시 MCAP 기록물과 ULog를 업로드"의 1a 예외다. MCAP 업로드는 Phase 2부터다.

근거(recorder): 기록 정책(구독 QoS override, 대상 토픽, hidden 토픽, SIGINT 종료)은 Phase 2 logging-engineer의 설계 몫이고 아직 없다. regex 기록에는 오프셋 메타데이터와 미션 경계가 없어 Phase 2 replay 입력으로 다시 쓸 수 없다(logging). 판정 실행에 PX4 토픽 구독을 더한다(판정 probe도 참가자이지만 recorder만큼 구독을 더하지는 않는다).

Phase 2를 위해 6단계가 지켜 둘 것(logging): 실행 디렉터리의 `bag/` 이름을 다른 용도로 쓰지 않는다, wrapper의 수집 순서 맨 앞에 recorder 정지가 들어올 자리를 둔다, trace 표본에 수신 ROS 시각과 PX4 `timestamp`(us)를 함께 적는다.

기각한 안
- foxglove_bridge 설치 판을 ENV로 기록만(ros2): 버전 고정 원칙과 어긋난다. 접두 단정은 같은 3.6.0의 재빌드는 통과시키고 다음 판은 분명한 실패로 드러낸다.
- 화이트리스트에 `^/clock$`, `bridge.yaml`(쟁점 2).
- trace의 필드 이름을 `docs/interface.md`에 올리는 안(logging): trace는 테스트 산출물이고 인터페이스가 아니다. `tests/sitl/`의 설명에 둔다.

## 쟁점 13. 작업 단위와 PR 분할

README.md에 있다. 요약: P0(CI trigger 정리) / P1(ros-ws에 foxglove_bridge) / P2(`idsim_common` 추가) / P3(`idsim_mission` 패키지와 단위 테스트, `ExecuteMission.action`의 상수 `REASON_DISARM_FAILED`와 `REASON_EXTERNAL_DISARM` 추가와 주석, golden 두 파일) / P4(쟁점 3 M6과 쟁점 4의 core 변경, 생성기, `sim_stack.sh`, `tests/support`, `tests/sitl`, `sitl.yml`, 문서 반영) / P5(viz). P1과 P2는 병렬, P3은 P2 뒤, P4는 P1과 P3 뒤, P5는 P4 뒤다.


## 담당자별 구현 지시

P0-P3은 끝났다. 남은 것은 P4와 P5다.

ros2-engineer
- P4: "P6에서 ARMED를 처음 관측한 뒤"의 감시, 감시 표로 끝낼 때의 지상 disarm 1회, 정리의 상한(M6), Hold 실패 뒤의 공중 재진입을 core에 구현한다. snapshot 헤더는 바꾸지 않는다. 전이 표와 상태기 단위 테스트의 변경이므로 px4-engineer의 승인 없이 머지하지 않는다.
  - P6: 첫 ARMED 표본의 기준(식별 대조가 맞고 수신 tick이 arm 첫 전송 tick보다 큼), 확인 기한(`arm_timeout`은 첫 ARMED 표본까지, 그 뒤는 그 시각부터 `mode_confirm_timeout`. 같은 tick이면 첫 ARMED 표본이 `arm_timeout` 만료보다 앞), 그 tick의 순서(status를 보고 대기 명령을 지운 뒤 ack), 그 tick부터의 감시 표 순위 1-8(`Px4Timestamp` 질의를 판정 맨 앞에), 같은 tick의 순서, failsafe 이력의 구간.
  - 감시 표의 종료: `evaluate_monitor`는 순수 함수로 둔다. "끝낼 때 disarm을 보내는 행인가(조건 셋을 보는 행, 조건 없이 보내는 행, 보내지 않는 행)"는 순수 술어로 두고, P6과 setpoint 항목이 같은 종료 헬퍼를 쓴다. "첫 ARMED 표본 뒤 `landed` false를 본 적이 있는가"는 goal 동안 유지하는 이력이다.
  - 정리의 상한: 정리 시작 tick의 ROS 시각, 한 tick의 순서, 상한 tick의 명령 하나, 식별 불일치 표본 경로에도 같은 검사. 노드는 configure 때 계산값을 INFO 로그로 남긴다.
  - 단위 테스트(`test_runner_preparing.cpp`, `test_runner_items.cpp`, `test_runner_cleanup.cpp`, `test_monitor_table.cpp`)
    - P6: ARMED 뒤 외부 모드(EXTERNAL_MODE_CHANGE), failsafe 모드(FAILSAFE), 방어용 행(합성 표본), 첫 ARMED 표본이 이미 OFFBOARD가 아닌 경우, 확인 2회 뒤의 이탈이 확인 기한을 기다리지 않고 끝나는 것, ARMED 뒤 DISARMED(공중과 지상), ARMED 뒤 상태 끊김(LINK_LOST), timestamp 공급 실패(INTERNAL), 첫 ARMED 표본보다 `timestamp`가 작은 표본은 판정에 쓰이지 않는 것. 끝나는 tick에 setpoint가 없고 `last_item_index`가 0이라는 것.
    - P6의 범위 고정: ARMED를 보기 전의 DISARMED이고 OFFBOARD가 아닌 표본은 지금처럼 끝내지 않는다. arm 전송 전에 받은 ARMED 표본은 "처음 관측"이 아니다. 첫 ARMED tick 뒤에는 arm 재전송이 없다. 같은 tick의 늦은 거부 ack가 ARM_REJECTED를 만들지 않는다.
    - 확인 기한: arm이 TEMPORARILY_REJECTED 재시도 끝에 늦게 받아들여진 경우(첫 ARMED 표본이 arm 전송 뒤 4.2 s)에 확인 3회가 `arm_timeout`을 넘겨 차도 TAKEOFF를 시작한다. 첫 ARMED 표본 뒤 `timestamp`가 늘지 않는 표본만 오면 그 시각부터 `mode_confirm_timeout`에 ARM_REJECTED와 정리 분기(합성 표본). 첫 ARMED 표본과 `arm_timeout` 만료가 같은 tick이면 끝내지 않고 확인 기한을 시작한다.
    - 같은 tick: 감시 표 행 대 확인 기한, 대 cancel. 모두 감시 표 행의 ABORTED.
    - 지상 disarm 1회: 순위 3, 6, 7, 8 각각에서 조건이 참이면 끝나는 tick에 disarm 1개, `landed`가 false이거나 false를 본 이력이 있으면 0개. 순위 2는 arm을 보냈으면 `landed`와 이력에 무관하게 1개. 순위 1, 4, 5는 0개. 그 tick의 timestamp 공급 실패면 명령 0개에 결과 유지. P6과 TAKEOFF에서 같은 쌍. LOITER에서는 `landed` false 이력이 있으면 0개(순위 2 제외). 술어는 8행 전수로 단정하고 행 수 단정은 그대로 둔다.
    - 정리의 상한: `landed`가 2.5 s마다 바뀌는 합성 열이 상한 직전 tick에는 끝나지 않고 상한 tick에 정확히 끝난다(종료 1건, 그 뒤 setpoint와 재전송 없음). 원인 3 x {지상, 공중} 6칸(취소면 DISARM_FAILED와 MODE_SWITCH_FAILED, 나머지는 원래 reason과 `detail`. 지상 칸은 disarm 1개, 공중 칸은 NAV_LAND 1개). 가장 긴 정당한 경로(지상 -> Hold 실패 -> Land 경로 -> 지상)가 상한 전에 끝나면 분기의 결과. 같은 tick 넷(상한 대 확인은 상한, 대 상태 끊김은 LINK_LOST, 대 공중 DISARMED는 FAILSAFE, 대 정리할 것 없음은 CANCELED). 식별 불일치 표본 경로에도 상한이 걸린다.
    - Hold 실패 뒤 Land 경로에서 지상을 거쳐 다시 공중이 되면 Hold가 아니라 NAV_LAND를 보낸다(거부 ack와 `hold_confirm_timeout` 각 한 건).
    - 합성 표본으로만 덮는 경로(상한, 방어용 행)는 테스트 주석에 그렇게 적는다.
  - 패키지 `README.md`: "알려진 제한"의 정리 상한 항목을 지운다. "표에 없어 구현에서 정한 것" 가운데 이 문서로 올라온 것(1, 2, 3, 9, 10, 11, 13, 19)은 지우고 8번(P6의 계수)과 "전이 표와 구현의 대응"을 이 문서에 맞춘다. 소스 주석이 가리키는 이 문서의 없어진 절 이름과 번호를 지금 것으로 고친다: `test/test_termination.cpp` 16행, `test/test_confirm_rules.cpp` 16행, `include/idsim_mission/core/termination.hpp` 16행, `include/idsim_mission/core/rules.hpp` 86행과 141행, `test/test_monitor_table.cpp` 187행, `test/node/test_executor_node.cpp` 22행("C5"), 패키지 `README.md`의 "C4".
- P4, P5 검토: launch와 params의 대응, foxglove params.

px4-engineer
- P4: 위 core 변경(P6 행, 감시 표의 적용 구간과 지상 disarm 1회, 재전송 표, 정리의 상한과 그 값, Hold 실패 뒤의 재진입)과 상태기 단위 테스트의 승인.
- P4 머지 전: 필수 재실측 (2), (3), (5)(넘김 목록).
- 7단계 고정 전: 나머지 필수 재실측(넘김 목록).
- P4 검토: 시나리오 A, D, T의 판정 필드와 타임아웃 값. `check_px4.py`의 source (254, 1)은 그대로.

test-engineer
- P4: 위 단위 테스트의 구조 승인.
- P4: 시나리오 A에 `vehicle_status` 원시 표본 기록을 넣는다(KEEP_ALL 구독의 별도 기록기. 판정 probe의 tick 모델과 따로 둔다). 표본마다 `timestamp`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`, 수신 ROS 시각을 trace에 남기고, arm 전송 시각 이후부터 TAKEOFF 시작(feedback의 PHASE_EXECUTING)까지 OFFBOARD가 아닌 ARMED 표본의 수와 ARMED 표본의 수를 회차 요약에 적는다. ULog의 `vehicle_status`와 교차 확인하는 절차는 px4-engineer와 정한다. 10회 이상은 `run_sitl.sh --repeat 10`으로 얻는다(넘김 목록의 통과 기준).
- P4의 실측 기록(stop 검증, 결함 주입, px4 재실측에 공통)
  - 측정 스크립트는 `tests/sitl/measure/`에 둔다(소유 test-engineer, 절차의 필수 승인자 px4-engineer). px4 재실측 (2), (3), (5)가 P4 머지 조건이므로 P4의 선행 작업이다.
  - 시도마다 기계가 읽는 행을 남긴다(`measure_<항목>.tsv` 또는 jsonl): run id, commit과 dirty, 이미지 key, 시도 번호, 주입 조건과 trigger, 결과, ROS 시각과 벽시계 소요, 종료 코드, ULog 경로. 실패한 시도를 빼지 않고 재시도하지 않는다. 위치는 `run_sitl.sh`와 같은 아티팩트 디렉터리다. 통과 기준은 실행 전에 요약 파일 머리에 적는다. trigger는 sleep이 아니라 이벤트(feedback phase, `landed` 표본)다.
  - 측정 스크립트의 종료 코드: 0은 모든 행의 최종 판정이 통과이고 시도 수가 충분한 것이다. 1은 기준과 다른 관측이 있는 것이다(기준에 어긋난 회, (2)의 뒷부분에서 `landed`가 true가 된 회, OFFBOARD가 아닌 ARMED 표본, ROS 기록과 ULog의 불일치). 이 문서의 기대가 반증된 것이고 PX4의 결함이라는 뜻이 아니며 architect에게 올린다. 2는 최종 판정이 통과가 아닌 행이 하나라도 있거나 기계가 판정하지 못한 것이다(조건이 생기지 않은 회, Hold로 끝난 회, 관찰 표본이 부족한 회, 유효 시도 수 부족, 인프라). 자극이 성립하지 않은 회((3)에서 창을 놓친 회, (5)에서 arm 수락의 증거가 없는 회)는 통과 기준의 대상이 아니므로 유효 시도와 이 집계에서 빼고 횟수를 따로 적는다. 창을 놓친 회는 측정 중에 정해지고, arm 수락의 증거가 없는 회는 ULog 교차 확인 뒤에 정해지며 그 전에는 2다. 빼는 것은 기준과 다른 관측이 없고 판정에 필요한 관찰이 다 된 회뿐이다. 창을 놓친 회에도 창과 무관한 기준은 적용한다. OFFBOARD가 아닌 ARMED 표본 0개, 정리 총 소요 9 s 미만, 전이 표에 있는 종료, 상승 0.2 m 이하이고, Hold로 끝났으면 60 s 동안 M3의 상태, 지상에서 끝났으면 armed로 남지 않는 것이다. 어긋나면 1이고 관찰이 모자라면 2다. 그 밖의 예외는 없다. 1이 2보다 앞선다. 최종 판정은 ULog 교차 확인 뒤의 것이다. 2의 통과 판정은 넘김 목록의 기준으로 architect가 한다.
  - 관찰 시간 기준(Hold로 끝난 상태의 60 s)은 표본이 실제로 덮은 구간으로 센다. 구간의 길이, 표본의 빈도와 최대 간격, 마지막 표본의 나이가 하한에 못 미치면 그 회는 판정하지 않는다. 하한 값은 `tests/support/measure_judge.py`의 상수이고 px4-engineer가 승인한다.
  - 회수의 한계를 적는다. 10회 중 0건은 실패율의 95% 상한이 약 26%라는 뜻이다(3/n 근사로는 30%). "10/10 통과"를 "플래키 없음"으로 쓰지 않는다.
  - stop 검증의 goal 실행 중 stop은 단계를 나눈다: PREPARING, TAKEOFF, LOITER, LAND 각 1회 이상(4회 이상). 종료 사건의 수신은 구독자(테스트 노드)에서 기록하고 못 받으면 "수신 실패"로 남긴다.
  - 결함 주입(`vehicle.id` 누락에서 unhealthy까지): 시작은 compose up 시각, 끝은 `.State.Health.Log`의 첫 unhealthy. 벽시계 측정임을 행에 적는다. 정상일 때 healthy까지의 시간과 쌍으로 잰다.
  - 재실측 (5)의 `timestamp - Px4Timestamp` 분포가 0 근처에서 부호가 섞이면 "엄격히 뒤" 기준을 px4-engineer와 architect가 다시 본다.
  - `tests/support/mission_client.py`가 `mission_event` 구독을 action client보다 먼저, 같은 node 객체로 만드는지 mock으로 검사한다. DDS에서의 효과(87/400)는 단위로 재현되지 않으므로 구조만 건다. 효과는 쟁점 7의 0/400과 시나리오의 `EVENT_MISSING` 분류가 받친다.
- P4: `tests/support/`(clock, waiting, probe, judge, mission_client, events, trace, `px4_topic`, `px4_raw`. 판정 함수는 rclpy 없는 순수 코드로 두고 단위 테스트는 lint job의 pytest에서 돈다), `tests/sitl/`(`run_sitl.sh`, conftest, 시나리오), `tests/support/stack.py`의 새 key 접근자. lint job의 pytest가 `tests/sitl/`을 수집하지 않게 한다. 로컬 3회 연속 통과의 실행과 기록.
- verdict 분류: `TIMEOUT_SIM`, `CLOCK_STALLED`, `CLOCK_SLOW`, `CLOCK_ABSENT`, `NO_PUBLISHER`, `SERVER_ABSENT`, `EVENT_MISSING`, `EVENT_MISMATCH`, `PRECONDITION`, `WRONG_RESULT`, `INFRA_UP`.

devops-engineer
- P4의 `ops-N` 서비스와 기동, 정지 경로(쟁점 2의 값 그대로)
  - `ops-N`: `init: true`, `stop_signal: SIGINT`, `stop_grace_period: 10s`, healthcheck(`interval` 10s, `timeout` 10s, `retries` 2, `start_period` 20s, `start_interval` 2s, 안쪽 `timeout 8`, 출력 남김).
  - 상주 ros-ws 서비스(bridge, P5의 foxglove)와 xrce-agent에 `init: true`. 같은 PR에서 하고 생성기 golden 4종이 함께 바뀐다. 바꾸기 전후의 down 시간을 1회씩 잰다.
  - runner: wrapper의 `timeout`이 보낸 SIGTERM이 PID 1인 pytest에서 버려지는지 1회 확인하고 `init: true` 또는 `timeout -s INT -k 30`으로 고친다(test-engineer와).
  - exit code: 판정에 쓰지 않는다. stop 전 `compose ps -a --format json` 기록 -> running이 아닌 `ops-N`이 있으면 실패 -> `compose stop` -> `compose logs` -> down. exit 1을 보아 넘기는 것은 stop을 요청한 뒤에 한정한다(쟁점 2).
  - `sim_stack.sh`는 노드 단계가 실패하면 `ops-N` 로그 끝과 `.State.Health.Log`를 함께 찍는다.
  - 생성기 성질 테스트 넷: ros-ws 이미지의 상주 서비스는 모두 `init: true`. `ops-N`은 `stop_signal: SIGINT`와 `stop_grace_period: 10s`. 생성된 params 파일에 `lifecycle.`로 시작하는 key가 없다. healthcheck 문자열의 FQN이 `stack.json`의 `executor_node`와 같다.
  - P4 검증(결과를 PR 본문에 남기고, 값이 아래와 다르면 architect에게 알린다)
    - stop 검증 10회: 그중 4회 이상은 goal 실행 중에 stop한다(PREPARING, TAKEOFF, LOITER, LAND 각 1회 이상. test-engineer). 기록 형식은 test-engineer 지시의 "P4의 실측 기록"을 따른다. 볼 것은 유예(10 s) 안에 끝나는지, 정리 로그가 있는지, exit code의 분포, goal 실행 중 stop에서 종료 사건(ABORTED, REASON_INTERNAL)이 구독자에게 오는지다(on_shutdown이 SIGINT 뒤에 도는지는 실측이 없다).
    - 결함 주입 1회 이상: `vehicle.id`가 빠진 params로 `sim_stack.sh up`이 unhealthy를 보고하기까지의 시간(예상 약 54 s, 최악 70 s)과 정상일 때 healthy까지의 시간(예상 약 5-6.5 s).
    - CI 첫 3회의 probe 시간(`.State.Health.Log`의 Start와 End)을 RTF와 함께 기록한다. runner의 `docker version`을 job 로그에 남긴다(`start_interval`은 Engine 25 이상).
- P4: 생성기(쟁점 2), `sim_stack.sh`(`--infra-only`, install 검사, 노드 단계 실패 때 `ops-N` 로그 출력), `run_smoke.sh`, `check_host.sh`, `--run-id` 제거, `build_images.py --mode pull`, `sitl.yml`, `px4-api` 범위 확장, 생성기 golden 4종과 전체 트리 비교. 손대는 파일의 음차("키", "잡")를 고친다.
- P5: `foxglove`, `lichtblick` 서비스와 `LICHTBLICK_IMAGE`, `docker/README.md`의 갱신 절차와 접속 안내.

architect
- 이 문서와 같은 PR: `ExecuteMission.action`의 의미 주석(M6, M7, REASON_EXTERNAL_DISARM의 범위). golden은 바뀌지 않는다.
- P4: 문서 반영 목록.
- 7단계: `docs/interface.md`에 M1-M7(새 상수 포함)과 전이 표의 계약 부분, source 표, 타임아웃이 노드 파라미터라는 구분(넘김 목록).

reviewer: PR마다의 검토.

## 넘김 목록

| 받는 쪽 | 시점 | 항목 |
| --- | --- | --- |
| px4-engineer | (2), (3), (5)는 P4 머지 전(필수. 이유는 표 아래). 나머지는 7단계 고정 전(필수) | 재실측. Hold로 끝난 상태의 관찰은 60 s 이상으로 한다. (1) AUTO_LAND 하강 중 0.3 m 아래에서의 취소 3회: 내려앉는지 호버하는지, CANCELED 뒤의 상태, landed인 채 armed로 남는 경우가 있는지. (2) 지상 setpoint 발행 중의 Hold 3회: H와 같은 조건에서 NAV_LAND 대신 Hold를 보내고 처음 관측한 순간 발행을 멈춘다. 이어서 "Hold를 확인하고 발행을 멈춘 뒤 `landed`가 true인 상태에서 disarm" 3회(수락 여부, 고도 변화 0.2 m 이하인지). (3) 이륙 직후의 지상 setpoint와 disarm 3회: TAKEOFF 목표점으로 arm한 뒤 `landed`가 아직 true인 구간(약 0.3-1.0 s)에 지상 setpoint로 바꾸고 disarm. 보내는 시점은 sleep이 아니라 `landed` 표본에 맞춘 조건으로 잡는다(px4-engineer 권고). (4) 감시 표 순위의 확인: G처럼 지상 setpoint로 arm한 뒤 다른 source로 disarm하고, 뒤따르는 표본의 `nav_state`, `failsafe`, `nav_state_user_intention`을 기록한다. failsafe Land 뒤 자동 disarm의 첫 DISARMED 표본과 명령 disarm(대비책)의 첫 표본도 기록한다(`failsafe`, `nav_state`, `nav_state_user_intention`, `landed`). 선택 항목: failsafe 동작이 Disarm인 경로(`COM_OBL_RC_ACT`를 Disarm으로 둔 실행)의 DISARMED 표본이 예상(`failsafe` true, `nav_state` OFFBOARD)과 같은지. 이 프로젝트의 파라미터(Land)로는 닿지 않아 필수가 아니다. (5) arm 전송 직후 취소의 경쟁: arm을 보낸 직후(0-0.2 s)에 지상 setpoint와 disarm을 보내고 끝난 상태가 DISARMED인지. 10회 이상. arm이 수락된 증거가 없는 시도는 경쟁이 없었으므로 10회에 넣지 않고 따로 적는다. 증거는 arm 전송 뒤 `timestamp`의 ARMED 표본(ROS 또는 ULog)이거나 ULog logged message `Armed by external command`(arm 전송 뒤, 정리 종료 전)다. ROS로 받은 ack는 증거가 아니다(arm과 disarm이 같은 command라 ack만으로는 어느 쪽의 것인지 가릴 수 없다). ARMED 표본이 1개 이상 보인 시도 수와 지연값별 유효 시도 수를 함께 적는다. 통과 기준은 전부에서 `mode_confirm_timeout` 안에 기준을 만족하는 DISARMED 3회가 차고, 상승이 0.2 m 이하이며, 지상에 armed로 남은 회가 없는 것이다. 모든 `vehicle_status` 표본의 (`timestamp`, 노드가 받은 ROS 시각, 같은 시점의 `/clock`)을 기록해 `timestamp - Px4Timestamp`의 부호 있는 분포를 구한다. (6) 표본 늘리기: Hold 실험 B(offboard 손실 failsafe 중 Hold)와 C(NAV_LAND 중 Hold), 이번 run의 G, H, X2a, X2b를 각 3회 이상. 높이 0.06-0.37 m 사이의 Hold 포함. (7) X3(이륙한 적 없는 지상 armed에서 발행 중단) 1회. (8) Executor가 보낸 `[LAND]`(지면 근처 Hold에서. P3 뒤에 가능). 함께 기록할 것: (3)과 (5)는 arm 전송부터 ARMED 3회까지 모든 표본의 `nav_state`, `failsafe`, `nav_state_user_intention`을 기록한다. 통과 기준은 OFFBOARD가 아닌 ARMED 표본이 0개인 것이고, 어긋나면 P6의 1회 판정을 architect에게 올린다. (3)과 (5)는 arm 직후에 disarm하므로 ARMED 표본이 실행당 0-2개뿐이라 이것만으로는 기준이 빈 채로 통과한다. 그래서 ARMED 3회까지 가는 실행(측정 스크립트의 `armed` 항목과 시나리오 A)에서도 같은 기록을 남긴다. `armed` 항목은 Executor 없이 PX4에 직접 명령을 보내며, P6과 같이 첫 ARMED 표본을 본 뒤에는 arm을 재전송하지 않는다. 이 기록은 노드의 tick 모델(tick당 최신 표본 1개)이 아니라 `vehicle_status` 원시 표본(KEEP_ALL 구독의 별도 기록기 또는 ULog의 `vehicle_status`)에서 얻는다. 상태가 바뀌면 `vehicle_status`가 즉시 publish되어([소스] `Commander.cpp` 1941-1945행) PX4 `timestamp`로 50 ms 안에 연달아 나오는 표본이 바로 보려는 경로이기 때문이다. 그런 표본은 ROS에 `timestamp`보다 늦게 도착할 수 있으므로([실측] 32-176 ms. 쟁점 3 M5) 표본의 순서와 간격은 수신 시각이 아니라 `timestamp`로 읽는다. 표본마다 `timestamp`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`을 적고, arm 전송 시각 이후부터 TAKEOFF 시작까지 전부를 센다. 값의 정본은 PX4이므로 ULog의 `vehicle_status`와 교차 확인한다. 실행은 두 부류로 나누어 센다. Executor 경유(시나리오 A)와 PX4 직접 명령(측정 스크립트의 `armed` 항목, 재실측 (3), (5))이다. 부류마다 ARMED 3회 확인까지 간 실행이 10회 이상이며 그 전부에서 0개여야 통과다. PX4 직접 명령 부류의 통과는 P6 구현의 착수 근거이고, P4 머지 조건은 두 부류가 모두 통과하는 것이다. 재실측 (2)의 실행은 실행 수에 넣지 않되 OFFBOARD가 아닌 ARMED 표본이 나오면 위반으로 센다. 세는 구간의 끝은 ARMED 3회 확인, 정리 종료, 측정기가 처음 보낸 Hold 가운데 가장 이른 시각이다. PR 본문에는 부류별 실행 수와 표본 수를 따로 적는다. 이것은 통계적 증명이 아니라 [소스]로 정한 메커니즘의 반증 확인이다. 한 건이라도 나오면 그 즉시 architect에게 올린다. (2), (3), (5)는 실행마다 정리의 총 소요(시작부터 종료까지), 분기가 바뀐 횟수와 순서, `landed`가 바뀐 횟수와 간격을 기록한다. 통과 기준은 모든 실행에서 총 소요가 9 s 아래인 것이고(상한 12 s에 여유 3 s), 넘는 실행이 있으면 상한을 올리지 않고 architect에게 올린다. 이 재실측은 Executor 없이 PX4에 직접 명령을 보내고, 정리 분기는 측정기의 모델이 표의 규칙대로 고른다. 근거가 되는 범위는 PX4 쪽 사실(명령의 수락 여부, 표본의 순서와 지연, `landed` 전환, 상승)이다. 총 소요 기준은 PX4의 응답이 표의 규칙 아래에서 정리를 그 안에 끝낼 수 있게 하는지를 보는 것이고 core의 소요를 보증하지 않는다. core가 표대로 움직이는 것과 상한은 상태기 단위 테스트가 받친다. Hold로 끝난 회의 총 소요는 AUTO_LOITER 3회 연속까지로 잰다. (3)은 disarm을 보낸 뒤 ACCEPTED가 오기 전에 `landed`가 false로 바뀌어 공중 분기로 넘어가는 회가 있는지와 다시 지상으로 돌아오는 데 걸리는 시간을, (5)는 지상 분기 -> 공중 분기 -> 지상 분기를 거치는 회의 비율을 기록한다. (4)에는 G 조건에서 ARMED를 본 직후 다른 source로 모드를 바꾸고(DO_SET_MODE Hold) 강제가 아닌 disarm 1회가 받아들여지는지와 표본 순서를 1-3회 기록한다(감시 표로 끝낼 때의 지상 disarm 1회의 근거). (6)의 높이 0.06-0.37 m Hold는 60 s 관찰 동안 `landed`가 바뀐 횟수를 기록한다(상한 값의 근거. P4 머지 조건은 아니다). 정리의 상한 경로 자체는 실제 PX4로 재현하기 어려워 합성 표본 단위 테스트로 덮는다. 결과가 M3-M7의 문장이나 감시 표와 다르면 고정 전에 고친다. 결과(run id, 항목별 회수와 값)는 (2), (3), (5)는 P4 PR의 본문에, 나머지는 7단계 PR의 본문에 적는다. 측정은 px4-engineer, 표와의 대조와 통과 판정은 architect, 근거 확인은 reviewer다. (2)와 (3)의 통과 기준은 3회 모두 이 문서의 표대로 끝나는 것이다. (2)의 앞부분은 Hold를 `hold_confirm_timeout` 안에 관측하는 것이다. (2)의 뒷부분은 둘 중 하나로 끝난다. (가) 60 s 관찰 동안 `landed`가 true로 돌아오지 않고 기체가 ARMED, AUTO_LOITER, `landed` false, 고도 변화 0.2 m 이하로 머문다. M3의 계약 문장대로이며 disarm은 조건이 생기지 않은 것으로 기록한다. (나) `landed`가 true가 되고 그 상태에서 보낸 disarm으로 DISARMED 3회가 차며 고도 변화가 0.2 m 이하다. 3회가 모두 (가)이면 (2)는 통과다. (나)가 한 회라도 있으면 M3의 "스스로 내려앉지 않는다"와 다르므로 architect에게 올린다. (3)에서 표대로 끝난다는 것은 창 안의 시도(취소 시점에 `landed` true)가 상승 0.2 m 이하, 정리 총 소요 9 s 미만으로 끝나고, 끝난 상태가 지상 DISARMED이거나 공중 분기로 넘어가 Hold로 끝난 뒤 60 s 동안 M3의 상태로 머무는 것이다. Hold로 끝난 회가 있으면 architect가 M5의 "이륙 직후 취소의 정상 경로" 문장을 다시 본 뒤 판정한다. 기준과 다른 관측은 PX4의 결함이 아니라 이 문서의 기대가 반증된 것으로 읽는다 |
| test-engineer, px4-engineer | P4의 선행 작업 | 측정 스크립트는 `tests/sitl/measure/`에 둔다. 소유는 test-engineer이고 절차는 px4-engineer가 필수 승인자다. 재실측 (2), (3), (5)가 P4 머지 조건이므로 스크립트가 먼저 있어야 한다 |
| architect | 7단계 | `docs/interface.md`: M1-M7, `REASON_DISARM_FAILED`와 `REASON_EXTERNAL_DISARM`의 의미(1a 고정 전에 두 상수의 이름과 의미 문장을 한 번 더 본다. EXTERNAL_DISARM은 "원인은 판정하지 않는다"와 이름의 불일치를 `COM_DISARM_LAND` 자동 disarm 시나리오로 따진다), 감시 표의 행 순위(재실측 (4) 뒤), M7 뒤에도 `last_item_index`의 구분 필드가 필요 없는지(P6과 TAKEOFF의 종료가 같은 result로 나오고 가르는 것은 feedback의 phase뿐이다), disarm 분류의 고정 규칙, "공중"과 "지상"이 `landed` 값이라는 용어 주석, reason별 "ABORTED 뒤 기체 상태" 표(px4-engineer와. 쟁점 4의 "끝난 뒤 기체 상태" 줄 포함. INTERNAL은 지상 arm으로 남거나 이륙 램프 중이면 offboard 손실 Land, NOT_READY는 손대지 않음, LAND의 MODE_SWITCH_FAILED 뒤 지상 disarm일 수 있음, PHASE_PREPARING에서 감시 표로 끝난 goal의 상태와 지상 disarm 1회, 정리의 상한으로 끝난 goal의 상태), 정리의 상한(식과 기본값 12 s, 상한에서의 reason과 명령), 정리 중에 `failsafe == true`이고 OFFBOARD가 아닌 기체에 Hold를 보내지 않고 끝낼지의 검토(failsafe 중의 Hold는 user takeover다. 취소는 M3이 failsafe 중에도 같은 분기로 정했다), 아무것도 하지 않은 goal의 취소가 Hold나 disarm을 보내는 동작의 재검토(ops-service-engineer 포함. failsafe Land 중인 기체를 Hold로 세울 수 있다), 공중에서 끝나는 미션은 "고정 전"(U3), source 표, 발행 규칙(Offboard가 아닌 모드에서는 setpoint를 발행하지 않는다), 5단계 `decisions.md` 쟁점 9와 이 문서의 관계. `last_item_index` 구분 필드 불요 확인 |
| architect, px4, ros2 | 1b 설계 토론 | 공중에서 끝나는 미션의 종료 동작(권고: Hold 확인 뒤 SUCCEEDED), setpoint 항목으로 시작하는 공중 시작 미션(Offboard 재진입), 1a 임시 제한(마지막이 LAND, 첫 항목 제한)의 해제 |
| ros2-engineer, devops-engineer | 1b | `bridge.yaml` 생성(표적과 함께), world ENU <-> 로컬 NED 변환이 상태기 입력 직전 한 곳에 들어가는 구조 |
| px4-engineer | 7단계 전(선택) | 위치 무효에서의 Hold 거부 1회 실측(`failure gps off`), arm 상태에서 신호 없는 Offboard 요청 |
| px4-engineer | 다음에 `Dockerfile.px4`를 바꿀 때 | 주석의 옛 문서 이름(기존 미해결 항목 그대로) |
| px4-engineer, test-engineer | P4 | ULog가 `compose stop -t 15`에서 정상적으로 닫히는지 모른다. 첫 실행에서 `stop`의 종료 코드(137이면 KILL)를 기록하고 pyulog로 파일을 검증해(호스트에 pyulog가 없다) 결과를 P4 PR 본문에 남긴다. 실패 산출물 용도라 1a 완료를 막지 않는다 |
| architect, devops-engineer | Phase 2 | replay job의 trigger를 정한다(U4). 그때 `docs/architecture.md` 테스트 층 표의 리플레이 통합 행의 "모든 push"와 `docs/roadmap.md` Phase 2 완료 기준의 "모든 push"를 고친다 |
| logging-engineer | Phase 2 | recorder 도입과 `sitl`의 MCAP 업로드, `MissionEvent` QoS 재검토 제안(TRANSIENT_LOCAL)은 5단계 근거와 함께 다시 토론, wrapper의 recorder 정지 자리와 `bag/` 사용, ULog가 `compose stop`에서 정상적으로 닫히는지 |
| ops-service-engineer | Phase 3 | `validate_mission`(core)을 Fleet이 같이 쓰는 구조, 취소 뒤 Hold로 남은 기체에 `[LAND]` 미션을 보내는 절차, NOT_READY 앞에 feedback이 올 수 있다는 것 |
| devops-engineer | 뒤로 | Lichtblick 기본 layout, snapshots.ros.org 날짜 고정, clang-tidy 도구 이미지 분리(foxglove 추가 뒤 ros-ws 크기를 보고), 3대 nightly(Phase 3), unit job의 pull 분기를 `--mode pull`로 |
| test-engineer | Phase 2 | 판정 함수를 리플레이가 같은 이력 객체로 쓰는 구조의 확인, 가짜 PX4 발행자의 Python 판 |
| ros2-engineer | Phase 3 | component마다 생기는 `/clock`(250 Hz) 구독의 CPU, 참가자 수 상한 |

재실측 (2), (3), (5)가 P4 머지 조건인 이유: P4부터 `tools/sim_stack.sh up`이 Executor를 띄우고 사람이 goal과 취소를 보낼 수 있다. 세 항목은 이륙 직후 취소가 지나는 경로이고, 틀리면 기체가 지상에 armed로 남거나 떠오른다. 시나리오 D는 5 m에서 취소하므로 통합 테스트는 이 경로를 지나지 않는다. 그래서 테스트 통과가 아니라 실측이 근거여야 한다. (4)를 P4 조건에서 뺀 이유는 결과가 바꾸는 것이 reason의 분류이고 기체 동작(발행 중단, ABORTED)은 순위와 무관하게 같기 때문이다.

## 문서 반영 목록

`docs/`와 README는 P4 PR 안에서 architect가 반영한다(viz 관련 줄은 P5). 소유 규칙은 `docs-for-agent/file-ownership.md`에 이미 있다.

- `docs/architecture.md`
  - 테스트 절의 통합 테스트 구조: "pytest fixture가 `docker compose up --wait`로 스택을 올리고"를 "호스트 wrapper `tests/sitl/run_sitl.sh`가 `tools/sim_stack.sh`로 스택을 올리고 내리며, pytest는 `runner` 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증한다"로. "fixture가 active 전이를 기다릴 수 있게"는 "compose healthcheck가 active를 확인한다"로.
  - 테스트 절의 판정 기준: "도달은 `vehicle_local_position`과 setpoint 거리"를 "goal의 목표값과 `vehicle_local_position`"으로.
  - CI 절 (4) `sitl`: 실패 산출물을 ULog, compose logs, ros_log, 판정 trace로, "MCAP 업로드는 Phase 2부터". "PR당 1회"를 "PR 머리 커밋당 1회, 자동 재시도 없음"으로(U2).
  - CI 절 (1) `lint`: `px4-api` 검사의 넓힌 범위(yaml, 생성기 golden params, `tests/sitl`, `tests/support`와 예외 파일).
  - 시작 순서와 healthcheck 문단, 컨테이너 사용자 문단의 `ros-ws` 서비스 이름을 `ops-N`으로, 노드 단계와 lifecycle healthcheck.
  - 인터페이스 계약 절의 고정 시점 문장: 1a 완료에 고정되는 `ExecuteMission`의 범위에서 "공중에서 끝나는 미션의 종료 동작"을 빼고 1b 완료로(U3).
  - 서비스 표: `ros-ws` 행을 `ops-1 ... ops-N`으로(launch, 컴포넌트 컨테이너, healthcheck). `runner`의 의존.
  - 이미지 표: foxglove_bridge는 P1부터 들어간다는 사실과 버전 단정.
  - `docker/versions.env`에 적는 것의 열거에 `FOXGLOVE_BRIDGE_VERSION`과 `LLVM_MAJOR`를 더한다(P5에서 `LICHTBLICK_IMAGE`).
  - 시작 순서와 healthcheck 문단과 서비스 표: `ops-N`의 전이 주체가 노드 자신이라는 것(`lifecycle.self_start`), `init: true`와 `stop_signal`.
  - 기술 스택 표의 토픽 시각화 행과 미해결 서술의 "Lichtblick 2.5"를 1.30.0으로, 서브프로토콜 문장은 P5 실접속 결과로.
  - 기체 식별 절: params key(`vehicle.id`, `vehicle.ns`, `vehicle.sysid`), `stack.json`의 새 key, 식별 gate의 위치(PREPARING).
  - 인터페이스 계약 절: 취소 의미(M3-M6. Hold로 끝난 기체는 지면 근처여도 ARMED로 머문다는 문장과 정리의 상한 포함), `REASON_DISARM_FAILED`, `REASON_EXTERNAL_DISARM`, 발행 규칙.
  - 인터페이스 계약 절의 시간 기준 문장: 판정과 타임아웃은 ROS 시각이라는 원칙에 벽시계 예외 넷을 적는다. on_activate의 `/clock` 첫 수신 대기, 테스트 대기의 `wall_cap`, `CLOCK_STALLED` 판정의 5 s, Executor의 자기 전이 일회 timer(쟁점 2). 앞의 셋은 hang 방지용이고 넷째는 `/clock`이 오기 전에도 전이를 시도하게 하는 trigger다. 넷 다 판정 기준이 아니다.
  - 디렉터리 구조: `tests/sitl/`, `params/`, `ros_ws/src/idsim_mission/`.
- `docs/roadmap.md`
  - 리스크 표의 EKF 행: "EKF 수렴(`vehicle_local_position.xy_valid`) 대기 후 arm"을 "EKF 준비(`failsafe_flags`의 위치와 고도와 home 무효 flag 넷이 모두 false) 뒤 Offboard, 그다음 arm"으로. 같은 표에 "Offboard가 아닌 모드에서 setpoint를 발행하면 착륙 판정이 늦고 Hold가 끌린다"와 "failsafe 뒤 발행을 재개하면 Offboard로 돌아간다"를 더한다.
  - 1a 6번: "pytest fixture가 compose를 올리고"를 wrapper로, "EKF 수렴 대기 후 arm"의 순서, `bridge` 설정 파일은 1b, foxglove_bridge 이미지 추가, 통합 테스트의 시나리오 목록. 1a 3번의 "pytest fixture" 언급도 같이 본다.
  - 고정 시점을 나눈 문장과 1a 7번의 "계약으로 고정": `ExecuteMission`에서 공중에서 끝나는 미션의 종료 동작은 1b 완료에 고정(U3).
  - 1a 완료 기준: "이륙-호버-착륙 통합 테스트"가 시나리오 B, C, A, D, T 다섯을 가리킨다는 문장을 더한다.
  - 1a 4번의 발행 허용 문장: 테스트 harness의 예외(`tests/support/px4_raw.py`)를 적는다.
  - 1b 1번: 공중에서 끝나는 미션의 종료 동작 결정과 1a 임시 제한(마지막이 LAND, 첫 항목 제한)의 해제. `bridge.yaml`.
  - Phase 2: `sitl`의 MCAP 업로드.
  - Phase 2 완료 기준의 "replay CI job이 모든 push에서 돈다"는 P4에서 고치지 않는다. replay job의 trigger는 Phase 2에서 정하고 그때 고친다(U4).
- `docs/smoke-test.md`: `run_smoke.sh`가 `--infra-only`로 올린다는 것.
- 루트 `README.md`와 `docker/README.md`: `tests/sitl/run_sitl.sh` 실행 안내(`--repeat`, `--attach`), `sim_stack.sh up --infra-only`.
