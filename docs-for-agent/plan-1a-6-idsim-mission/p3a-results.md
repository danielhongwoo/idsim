# P3a 실행 확인 실험 결과

2026-11-11, ros2-engineer. `decisions.md` 쟁점 2(autostart, on_activate의 `/clock` 대기, `/**` params, `executor_name` 인자)와 쟁점 7(ACCEPTED 누락 계수)의 전제를 실행해서 확인했다. 브랜치 `exp/1a-6-p3a`(main 153a4d6에서). `decisions.md`는 고치지 않았다. 결정이 필요한 항목은 끝의 "결정 영향"에 모았다.

## 요약

| 항목 | 결론 | 수치 |
| --- | --- | --- |
| 1. `ComposableLifecycleNode(autostart=True)` | **동작하지 않는다.** 노드는 load되지만 CONFIGURE를 받지 않고 `unconfigured`에 머문다. 네임스페이스를 `/`로 둬도 같다. 쟁점 2의 전제가 깨졌다 | 스택 밖 4회, 스택 1회 모두 `unconfigured [1]` |
| 1. 대안 둘의 동작 | 컴포넌트 자기 전이(self-start)와 단독 실행 파일 + `launch_ros.actions.LifecycleNode(autostart=True)` 둘 다 active가 된다 | 스택에서 각 10/10 active |
| 1. 실패 시 동작 | configure FAILURE, configure 예외, activate FAILURE 모두 노드는 `unconfigured` 또는 `inactive`에 머물고 프로세스와 launch는 살아 있다. launch는 종료하지 않는다 | 스택 밖 각 1회 |
| 1. healthcheck | `ros2 lifecycle get --no-daemon <FQN>` 출력은 `active [3]`(정상), `unconfigured [1]`, `inactive [2]`. `docker exec`로 부르면 3.0-4.5 s 걸린다 | 스택 20회 |
| 2. `/**` params | 컨테이너 안 노드와 단독 노드 모두에 적용된다. 선언하지 않은 key는 LoadNode 오류 없이 무시된다(`has_parameter` false). `vehicle.id` 누락은 configure FAILURE로 드러난다 | 스택 21회(컨테이너 11, 단독 10), 스택 밖 2회 |
| 3. 첫 `/clock` 수신 | 프로세스 시작부터 중앙값 0.368 s, 최대 0.660 s(컨테이너). 노드 생성 뒤 최대 0.054 s. on_activate에 들어갈 때 이미 시계가 시작되어 있어 `wait_until_started` 대기는 20/20 0.000 s. 2 s 값은 이 호스트에서 여유가 크다 | 스택 20회 |
| 4. ACCEPTED 누락 | 실험군(구독 -> client -> 즉시 goal) **0/200**(새 프로세스), **0/200**(새 노드). 대조군(client -> 구독) **71/200**(새 프로세스), **16/200**(새 노드). 누락 87건 모두 Executor 쪽 `get_subscription_count()`가 0이었고, 구독 쪽 `get_publisher_count()`는 800회 모두 1 이상이었다 | 4 x 200회 |

## 실험 환경

- 이미지: `idsim/ros-ws:local` = `sha256:85fedc7d9731...`(launch_ros 0.26.13, rclcpp 28.1.22, rmw_cyclonedds_cpp 2.2.4, cyclonedds 0.10.5). 같은 호스트에서 태그가 바뀔 수 있어 실험 중에는 이미지 ID로 고정했다.
- 스택: `tools/stack.sh up --stack 6`(48.6 s에 준비), run id `20261111-030924-k6`, `ROS_DOMAIN_ID` 26, bridge 이미지도 같은 ID. 끝나고 `tools/stack.sh down --stack 6`. 사용자 스택 `idsim-0`은 건드리지 않았다.
- 시험 컨테이너: `--network host`, `ROS_DOMAIN_ID=26`, `CYCLONEDDS_URI=file:///opt/idsim/config/cyclonedds.xml`(worktree를 `/opt/idsim`에 읽기 전용 마운트). 스택 밖 확인은 `--network none`, 도메인 99, `CYCLONEDDS_URI` 비움.
- 시험 코드는 저장소에 넣지 않았다(scratchpad의 colcon workspace. `ros_ws/src/` 패키지를 만들지 않았다). 구성:
  - `idsim_interfaces`(저장소 사본, 테스트 제외)와 시험 패키지 `p3a_probe`.
  - `p3a::TestExecutor`(C++ lifecycle 컴포넌트, `rclcpp_components_register_node`로 같은 클래스의 단독 실행 파일도 생성). `vehicle.id`, `vehicle.ns`, `vehicle.sysid`를 선언하고 on_configure에서 값, `use_sim_time`, `has_parameter("undeclared_key")`, 선언된 params 목록을 로그에 남긴다. 누락이면 FAILURE. `mission_event` 발행자(RELIABLE, VOLATILE, depth 10)를 만든다. on_activate에서 `get_clock()->wait_until_started(2 s)`(벽시계), 실패면 FAILURE, 성공하면 `execute_mission` action 서버 생성. `handle_accepted`에서 ACCEPTED 사건 발행(발행 직전 `get_subscription_count()`를 로그), 곧바로 `succeed` 후 SUCCEEDED 사건 발행. 생성자에서 1 ms 벽시계 timer로 `get_clock()->started()`를 보아 첫 `/clock` 시각을 로그. 선언 param `self_start`(기본 false)가 true면 생성자의 0 ms 일회 timer가 `configure()`, `activate()`를 부른다.
  - launch 두 개. `vehicle_ops.launch.py`는 `decisions.md` 쟁점 2 그대로다(`ComposableNodeContainer(component_container_isolated, ops_container)`, `ComposableLifecycleNode(name=LaunchConfiguration('executor_name'), autostart=True)`, `namespace`, `params_file`, 기본값 없는 세 인자, `output='screen'`, `on_exit=Shutdown()`). 시험용으로 `self_start` 인자(기본 false)를 더했다. `standalone_lc.launch.py`는 `launch_ros.actions.LifecycleNode(executable=test_executor_node, autostart=True, on_exit=Shutdown())`.
  - params 파일: `ok.yaml`(`/**`에 `use_sim_time: true`, `vehicle.id: px4_1`, `vehicle.ns: /px4_1`, `vehicle.sysid: 2`, `undeclared_key: 42`), `missing.yaml`(`vehicle.id` 없음), `throw.yaml`(on_configure에서 예외).
  - `accept_probe.py`(rclpy): 한 회 = 새 노드에서 순서대로 구독과 action client 생성 -> `wait_for_server(10 s)` -> 곧바로 `send_goal_async` -> goal 응답 -> 2 s 동안 그 goal_id의 ACCEPTED 사건을 기다림. gate는 없다. 회마다 JSON 한 줄.

## 1. autostart

### 명령

```
ros2 launch p3a_probe vehicle_ops.launch.py namespace:=/px4_1 executor_name:=mission_executor params_file:=<ok|missing|throw>.yaml [self_start:=true]
ros2 launch p3a_probe standalone_lc.launch.py namespace:=/px4_1 executor_name:=mission_executor params_file:=<...>.yaml
ROS_LOG_DIR=/tmp/hc ros2 lifecycle get --no-daemon /px4_1/mission_executor     # docker exec로 8-9 s 뒤
```

### 결과

| 형태 | 조건 | 결과 |
| --- | --- | --- |
| 컨테이너 + `autostart=True` | 스택 밖(ok, missing, throw), `namespace:=/`, 스택(ok, `/clock` 있음) | 5/5 `unconfigured [1]`. on_configure가 한 번도 불리지 않는다. launch 로그는 `Autostart enabled for requested lifecycle node /px4_1mission_executor`(슬래시 빠짐) 한 줄뿐이고 오류도 없다 |
| 컨테이너 + self-start | 스택, ok | 10/10 `active [3]`. 프로세스 시작부터 active까지 0.30-0.64 s |
| 단독 + `LifecycleNode(autostart=True)` | 스택, ok | 10/10 `active [3]`. 프로세스 시작부터 active까지 0.28-0.60 s |
| 컨테이너 + self-start | 스택 밖, `/clock` 없음 | configure 성공, activate가 2.000 s 기다린 뒤 FAILURE -> `inactive [2]` |
| 단독 + autostart | 스택 밖, `/clock` 없음 | 같음. launch가 `Failed to make transition 'TRANSITION_ACTIVATE'` ERROR 로그 |
| 둘 다 | `missing.yaml` | configure FAILURE -> `unconfigured [1]`. 단독은 launch가 `Failed to make transition 'TRANSITION_CONFIGURE'` |
| 둘 다 | `throw.yaml` | rclcpp가 `Caught exception in callback for transition 10`, `Callback returned ERROR during the transition: configure` -> on_error 기본 처리 뒤 `unconfigured [1]` |
| 컨테이너 | `executor_name` 인자 빠짐 | launch가 바로 실패(rc 1): `Included launch description missing required argument 'executor_name'` |

- 실패한 모든 경우에 컨테이너 프로세스와 launch는 계속 산다. 실패는 healthcheck(`active`로 시작하지 않음)로만 드러난다.
- 원인([소스], 이미지의 launch_ros 0.26.13): `actions/load_composable_nodes.py`가 `complete_node_name = request.node_namespace + request.node_name`으로 이름을 만들어 `/px4_1mission_executor`가 된다. 또 `LifecycleTransition`이 내는 `ChangeState`의 matcher(`events/matchers/matches_node_name.py`)는 `'/' + 이름`과 `ComposableLifecycleNode.node_name`(치환된 상대 이름 `mission_executor`)을 비교하므로 네임스페이스가 `/`여도 맞지 않는다. `utilities/lifecycle_event_manager.py`도 서비스 이름을 상대 이름(`mission_executor/change_state`)으로 만든다. 그래서 Jazzy 이 판에서는 컨테이너 autostart가 어떤 네임스페이스에서도 동작하지 않는다([실측] 위 5회). [미확인] upstream rolling의 `load_composable_nodes.py`는 네임스페이스와 이름 사이에 `/`를 넣도록 고쳐져 있으나 matcher 쪽이 고쳐졌는지는 확인하지 않았다. 고쳐진 판이 Jazzy에 들어오기를 기다릴 근거는 없다.
- 단독 `LifecycleNode` action은 FQN을 제대로 다뤄 동작한다(10/10).

### healthcheck 근거

- 출력 형식: `<상태 label> [<id>]`. `active [3]`, `inactive [2]`, `unconfigured [1]`. "출력이 `active`로 시작" 판정이 성립한다(`inactive`는 `active`로 시작하지 않는다).
- `--no-daemon`은 Jazzy `ros2 lifecycle get`에 있다(`-h` 확인). `ROS_LOG_DIR=/tmp/hc`로 실행했다.
- 걸린 시간: `docker exec ... bash -lc 'source ...; ros2 lifecycle get --no-daemon ...'` 20회 3.03-4.53 s(DDS discovery 포함). healthcheck `timeout`은 10 s 이상이 맞다. bash login과 setup.bash source를 빼면 줄 수 있다(측정 안 함).

## 2. `/**` params

- `ok.yaml`로 스택에서 컨테이너(self-start) 11회와 단독 10회, 스택 밖 2회(컨테이너 self-start, 단독): `id='px4_1' ns='/px4_1' sysid=2 use_sim_time=1 has_undeclared=0`. 선언 목록은 `clock_wait_s, qos_overrides./clock.subscription.*, self_start, start_type_description_service, throw_in_configure, use_sim_time, vehicle.id, vehicle.ns, vehicle.sysid`이고 `undeclared_key`가 없다. LoadNode는 성공했다(`Loaded node '/px4_1/mission_executor' in container '/px4_1/ops_container'`).
- `missing.yaml`: `id=''`로 configure FAILURE(위 표).
- 결론: 쟁점 2의 "`/**` 값이 컨테이너 노드에 적용되고 미선언 key는 무시된다"는 [실측]으로 성립한다. launch 인자의 dict param(`{'self_start': LaunchConfiguration(...)}`)도 bool로 적용되었다.

## 3. 콜드 기동의 첫 `/clock` 수신

스택 6이 준비된 뒤(bridge healthy, `/clock` 발행 중) 새 컨테이너에서 launch를 매번 새로 시작했다. 시간은 `/proc/self/stat`의 프로세스 시작 시각과 `CLOCK_BOOTTIME`의 차이(해상도 10 ms).

| 형태 | 회수 | 프로세스 시작 -> 첫 `/clock` | 노드 생성 -> 첫 `/clock` | on_activate의 대기 |
| --- | --- | --- | --- | --- |
| 컨테이너 + self-start | 10 | 중앙값 0.368 s, 최소 0.300, 최대 0.660 | 중앙값 0.020 s, 최대 0.054 | 10/10 0.000 s(이미 시작) |
| 단독 + autostart | 10 | 중앙값 0.213 s, 최소 0.136, 최대 0.385 | 중앙값 0.002 s, 최대 0.055 | 10/10 0.000 s |

- on_activate가 `/clock`을 실제로 기다리는 경우도 확인했다(스택 밖, 컨테이너 + self-start, 1 s 뒤 `ros2 topic pub -r 100 /clock` 시작): `clock_ok=1 wait_s=1.350`. on_activate가 executor thread를 막는 동안에도 `/clock`은 받는다(rclcpp TimeSource의 clock thread. NodeOptions `use_clock_thread` 기본 true).
- `/clock`이 없으면 정확히 2.000 s 뒤 false, FAILURE, `inactive`(위 표).
- 결론: 2 s는 이 호스트에서 최대 관측값의 약 3배 이상이다(on_activate 진입 뒤 실제 대기는 20/20 0). CI runner에서 다시 재는 일(`decisions.md` 쟁점 2)은 그대로 남는다.

## 4. ACCEPTED 누락 계수

### 방식

- 서버: 스택 6 위에 컨테이너 + self-start의 시험 Executor 하나(`/px4_1/mission_executor`, active)를 띄워 두고 800회 동안 유지했다.
- 클라이언트: `decisions.md`가 "새 프로세스"와 "새 노드" 중 하나를 정하지 않아 둘 다 돌렸다.
  - 새 프로세스: 컨테이너 하나 안에서 `python3 accept_probe.py --reps 1`을 200번(회마다 새 DDS participant).
  - 새 노드: 한 프로세스에서 회마다 노드를 만들고 지운다(Jazzy는 context당 participant 하나라 endpoint discovery만 새로 한다).
- 실험군 `sub_first`: 구독 생성 -> action client 생성 -> `wait_for_server` -> 즉시 goal. 대조군 `client_first`: client -> 구독 순서만 바꿨다. 둘 다 같은 노드에서 연이어 만든다.
- 판정: goal 응답이 accepted이고 2 s 안에 그 goal_id의 ACCEPTED 사건이 오면 OK, 안 오면 EVENT_MISSING. 서버 로그의 `subs=`(ACCEPTED 발행 직전 `get_subscription_count()`)를 순서대로 맞춰 붙였다.
- 시작 2026-11-11T03:18:37Z, 총 15분 31초.

### 결과

| 묶음 | 회수 | goal accepted | ACCEPTED 사건 누락 | 서버 `subs` (OK / 누락) | 구독 `get_publisher_count()==0` (goal 때) | SUCCEEDED 사건 수신 | `wait_for_server` 중앙값/최대 | goal 송신 -> ACCEPTED 중앙값/최대 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 새 프로세스, sub_first | 200 | 200 | **0** | 1 / - | 0 | 200 | 0.104 / 0.229 s | 0.0082 / 0.2095 s |
| 새 프로세스, client_first | 200 | 200 | **71** | 1 / 0 | 0 | 141 | 0.107 / 0.227 s | 0.0094 / 0.2078 s |
| 새 노드, sub_first | 200 | 200 | **0** | 1 / - | 0 | 200 | 0.256 / 0.292 s | 0.0084 / 0.2077 s |
| 새 노드, client_first | 200 | 200 | **16** | 1 / 0 | 0 | 185 | 0.256 / 0.297 s | 0.0083 / 0.1124 s |

- 누락 87건 전부에서 서버 writer의 matched 구독 수가 0이었고, OK 713건 전부에서 1이었다. Executor가 ACCEPTED 때 `get_subscription_count()`를 debug 로그에 남기는 결정(쟁점 7)은 누락의 원인을 정확히 가른다.
- 누락된 회에도 구독 쪽 matched 수(`get_publisher_count()`)는 goal 시점에 1이었다(800/800). 쟁점 7의 "남는 위험"(구독 쪽은 맺어졌지만 writer가 아직 그 구독을 모름)이 대조군에서 실제로 일어났다. 구독 쪽 matched 수만으로는 사건이 올지 판정할 수 없다.
- 대조군에서는 바로 뒤의 SUCCEEDED 사건도 함께 빠진 회가 있다(새 프로세스 59회, 새 노드 15회). 종료 사건 누락도 같은 원인이다.
- 기전([추정]): 같은 participant의 endpoint 공지(SEDP)는 만든 순서대로 한 reliable 흐름으로 간다. 구독을 client보다 먼저 만들면, 서버가 client의 endpoint를 알게 되어 `wait_for_server`가 참이 될 즈음에는 그보다 앞선 구독 공지도 이미 처리되어 있다. client를 먼저 만들면 그 보장이 없다. 따라서 순서 규칙은 "틈을 줄이는 여유"가 아니라 누락을 막는 실제 조건이다. 같은 participant에서만 성립하는 논리이므로, 구독과 action client를 다른 participant(다른 프로세스)에 두면 이 보장이 없다(측정 안 함).
- 결론: `decisions.md` 쟁점 7의 실험 조건(구독 -> client -> 즉시 goal, gate 없음)에서 누락 0/400이다. "0이 아니면 이 쟁점을 다시 연다"의 조건에는 걸리지 않는다. 다만 순서를 어기면 8-36%가 빠지므로 순서 규칙은 반드시 지켜야 하는 규칙이다.

## 부수 관찰(devops-engineer 넘김 후보)

- PID 1 신호: `exec ros2 launch ...`를 PID 1로 둔 컨테이너에 `docker stop -t 15`(SIGTERM)를 보내면 무시되어 15.5 s 뒤 SIGKILL(exit 137). `--init`을 주면 0.4-0.5 s에 exit 143으로 끝나지만 launch의 정리 로그가 없다(launch가 SIGTERM으로 바로 죽는다). `docker stop -s SIGINT`면 `--init` 유무와 관계없이 1.7 s에 정리 로그(`sending signal 'SIGINT'`, `process has finished cleanly`)를 남기고 끝난다. 이때 exit code는 1이다(launch의 `Caught exception in launch: Cannot shutdown a ROS adapter that is not running`. 정상 종료에서도 나온다). compose의 `stop_signal: SIGINT`를 검토할 근거다. 각 1-2회 측정.
- 컨테이너 프로세스가 끝나면 `on_exit=Shutdown()`으로 launch도 끝난다(`process[component_container_isolated-1] was required: shutting down launched system`).

## 결정 영향

### 깨진 전제: 컨테이너 autostart (쟁점 2)

`decisions.md` 쟁점 2의 "전이를 거는 주체는 launch autostart뿐이다"와 "정적 launch로 `component_container_isolated` + `ComposableLifecycleNode(autostart)`"는 이 이미지에서 동작하지 않는다. 쟁점 2는 이 경우 "단독 실행 파일이 `main`에서 스스로 configure와 activate"로 물러선다고 정했고, 물러서면 architect에게 알린다고 했다. 이 문서가 그 알림이다. 대안과 실측:

| 안 | 내용 | 실측 | 장점 | 단점 |
| --- | --- | --- | --- | --- |
| A. 컴포넌트 자기 전이 | 컨테이너 구성은 그대로 두고, Executor가 생성자에서 0 ms 일회 timer로 `configure()`, 성공하면 `activate()`를 부른다. launch의 `autostart`는 빼거나 false | 10/10 active, 0.30-0.64 s. 실패 시 `unconfigured`/`inactive`에 머문다 | 기체당 컨테이너 하나(Phase 2 Collector 동거)와 isolated executor를 지킨다. launch와 compose command는 그대로. launch_ros 판에 의존하지 않는다 | 전이 주체가 launch가 아니라 노드 자신이다. 단위 테스트와 수동 전이용으로 끄는 param이 필요하다(선언 param, 생성기가 만들지 않는 기본값 true. 쟁점 2의 "params에는 식별값만"과 충돌하지 않는다) |
| B. 단독 실행 파일 + `LifecycleNode(autostart=True)` | `rclcpp_components_register_node(... EXECUTABLE ...)`로 같은 클래스의 실행 파일을 만들고 launch의 `LifecycleNode` action이 전이 | 10/10 active, 0.28-0.60 s. 실패 시 launch가 ERROR 로그를 남긴다 | 전이 주체가 launch로 남는다. 첫 `/clock`이 조금 빠르다 | Phase 2에 Collector가 같은 프로세스에 들어갈 수 없다(쟁점 2가 기각한 이유 그대로) |
| C. 단독 실행 파일이 `main`에서 전이 | `decisions.md`의 물러설 자리 | 측정 안 함(A와 같은 호출) | launch 의존 없음 | B의 단점과 같다 |
| D. launch에서 `change_state` 서비스를 직접 호출하는 OpaqueFunction이나 `ros2 lifecycle set` 프로세스 | 컨테이너 유지, 전이 주체는 launch | 측정 안 함 | 전이 주체가 launch | launch 코드가 늘고 CLI 프로세스면 participant가 하나 더 생긴다 |

ros2-engineer 권고는 A다. 근거: 쟁점 2가 컨테이너를 고른 이유(Phase 2 Collector 동거, isolated executor)를 지키면서 바뀌는 것이 노드 안의 수십 줄과 launch의 `autostart` 한 줄뿐이고, healthcheck(`ros2 lifecycle get`이 `active`)와 실패 시 동작(노드가 비활성으로 남아 healthcheck가 unhealthy)이 컨테이너 autostart를 가정했을 때와 같다. 결정은 architect 몫이다. 함께 정할 것:
- 자기 전이가 실패했을 때 프로세스를 끝낼지(`rclcpp::shutdown()` -> 컨테이너 종료 -> `on_exit=Shutdown()`로 launch 종료 -> compose에서 exited)와 비활성으로 남겨 healthcheck가 잡게 할지. 지금 측정한 동작은 후자다. 앞의 것이 실패를 빨리 드러내지만, Phase 2에 같은 컨테이너의 Collector까지 내린다.
- 끄는 param의 이름과 기본값(예: 선언 param `lifecycle.self_start`, 기본 true. 단위 테스트는 false).
- A를 고르면 `decisions.md`의 "전이를 거는 주체는 launch autostart뿐", launch 파일 설명(`autostart=True`), reviewer 판정표 4행을 고쳐야 한다.

### 유지되는 전제

- `/**` params(쟁점 2, reviewer 판정표 9행): [실측]으로 확인. 바꿀 것 없음.
- on_activate의 `/clock` 2 s 벽시계 대기(쟁점 2): 이 호스트에서 실제 대기 0 s(20/20), 첫 수신은 프로세스 시작 뒤 최대 0.660 s. 값을 바꿀 근거 없음. CI 첫 실행에서 다시 잰다는 계획은 그대로.
- `executor_name`에 기본값 없음: 빠지면 launch가 바로 rc 1로 실패한다. 의도대로다.
- 쟁점 7: 실험군 누락 0/400으로 전제가 성립한다. 대조군 결과(87/400 누락, 전부 writer 쪽 미매칭)로 다음을 덧붙이기를 권고한다.
  - 순서 규칙(구독을 action client보다 먼저)은 필수다. `tests/support`의 세션 코드에 이유를 주석으로 남기고, 같은 노드(같은 participant)에서 만든다.
  - 구독 쪽 `get_publisher_count() >= 1` gate는 사건 수신을 보장하지 않는다(대조군 87건이 모두 gate를 통과했다). gate에는 남기되 근거로 쓰지 않는다.
  - Executor의 ACCEPTED 때 `get_subscription_count()` debug 로그는 누락 원인을 정확히 가르므로 유지한다.

### 남은 것

- `--no-daemon` healthcheck가 3-4.5 s 걸린다. healthcheck `timeout`, `interval`, `start_interval`은 devops-engineer가 P4에서 이 값을 보고 정한다.
- 다른 participant(별도 프로세스)에서 구독을 먼저 만들고 client를 나중에 만드는 구성은 재지 않았다. 통합 테스트는 한 노드에서 만들므로 해당하지 않는다.
- 이 결과의 progress 반영(결정 기록, 쟁점 2 재결정)은 호출한 쪽과 architect가 한다.
