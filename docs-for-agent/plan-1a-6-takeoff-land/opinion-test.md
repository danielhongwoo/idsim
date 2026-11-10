# 6단계 설계 토론 test-engineer 의견

작성 2026-11-10, test-engineer. 대상은 `questions.md`의 "공통 규칙"과 T1-T11이다. 저장소 파일은 이 문서 말고 바꾸지 않았고, `ros_ws`를 빌드하지 않았다(이미 있는 `ros_ws/install`의 `idsim_interfaces`를 읽기 전용 마운트로 썼다).

## 실측 조건과 산출물

- 호스트 4 vCPU, 7.7GB. 모든 스택 실측 동안 다른 담당자의 스택 `idsim-1`, `idsim-5`(각각 에이전트, gazebo, px4-1, bridge)와 탐침 컨테이너 2-3개가 함께 떠 있었다. load average 5.9-8.0, available 메모리 4.0-5.6GB. GUI 없음, 빌드 없음.
- 내 스택은 k=3, 한 번에 하나만 올리고 매번 내렸다. 끝난 뒤 `idsim-3` 컨테이너 0개, 임시 컨테이너(`t4-server`) 정리 확인.
- 탐침과 결과는 scratchpad `/tmp/claude-1000/-home-daniel-work-idsim/da7a4a09-3e2d-4557-b34e-7026c7c8419b/scratchpad/`의 `t1/`(비행 탐침 `flight.py`, 회 실행 `round.sh`, `round_kill.sh`, 회별 `r<N>-<주입>/`에 flight.log, flight_*.json, up/down 로그, ULog 사본), `t2/`(`/clock` 시계), `t4/`(가짜 Executor), `t8/`(이름 파생)에 있다. 비행 탐침은 /fmu/in에 쓰므로 스택 안에서만 썼고 저장소에 넣지 않는다.
- 스택 실행 id(모두 k3): 정상 비행 `20261110-144254-k3`, `20261110-144435-k3`, `20261110-144609-k3`. 묵은 timestamp 주입 `20261110-144803-k3`. bridge 정지와 벽시계 timer `20261110-144941-k3`. bridge 강제 종료와 ROS 시각 timer `20261110-145124-k3`.
- 비행 탐침의 절차(Executor 대역이며 Executor 설계 제안이 아니다): `use_sim_time` 노드, ROS 시각 20 Hz timer로 `OffboardControlMode`(position만)와 `TrajectorySetpoint`(NED z=-5), timestamp는 노드 clock(`/clock`)의 us. 15회 뒤 DO_SET_MODE(176, 1, 6)를 1 s마다 재전송하며 `nav_state` 14 확인, ARM(400) 재전송하며 `arming_state` 2 확인, 고도 판정, 10 sim s 호버, NAV_LAND(21) 뒤 `nav_state` 18, setpoint 중지, `arming_state` 1이 연속 10개. source 254/1, target (sysid 2, 1).

## T1. 스택을 올리는 주체와 fixture 수명

결론: 호스트 진입 스크립트가 `tools/stack.sh up`으로 올리고 `compose run runner pytest`로 판정하는 스모크와 같은 구조를 쓴다. pytest fixture는 스택을 올리지 않고 `stack.json`을 읽어 "준비됨"을 ROS 토픽으로 확인한다. 스택 수명은 시나리오 묶음 하나(pytest 세션 하나)다.

- [실측] `runner`(ros-ws 이미지 `idsim/ros-ws:local`)에는 `docker` 실행 파일이 없고(`which docker` 비어 있음) 생성된 compose의 `runner`는 `/var/run/docker.sock`을 마운트하지 않는다(`tests/fixtures/gen_compose/1대-k3/compose.yaml`의 `runner.volumes`는 저장소 하나). 지금 이미지와 마운트로는 컨테이너 안 pytest가 compose를 부를 수 없다.
- [실측] `tools/stack.sh up --stack 3` 벽시계: 41.2, 41.2, 41.1 s(정상 비행 3회), 41.4, 43.2, 44.0 s(주입 3회). `down`: 20.7, 20.7, 20.7 s.
- [실측] `down`이 20 s인 이유를 서비스별 `compose stop -t 10`으로 쟀다(`20261110-144803-k3`): bridge 10.27 s(exit 137), px4-1 0.22 s(exit 0), gazebo 0.29 s(exit 143), xrce-agent 10.26 s(exit 137). bridge와 xrce-agent가 SIGTERM에 끝나지 않아 10 s 뒤 SIGKILL된다. devops와 ros2 영역이라 고치자고 하지 않고 사실만 넘긴다. 고치면 down이 1 s 안쪽이 된다([추정], 나머지 셋이 0.2-0.5 s).
- [실측] 이륙-호버-착륙 1회(탐침 시작부터 disarm 연속 10개까지): sim 29.25, 29.08, 29.69 s / 벽시계 29.37, 29.93, 29.74 s. 부하 속에서도 RTF는 약 1.0이었다. 단계별 sim 시간: arm 명령에서 `arming_state` 2까지 0.19-0.20 s, arm에서 고도 판정까지 7.2-7.7 s, NAV_LAND에서 disarm 판정까지 11.0-11.2 s. 스택 기동 직후 첫 `/clock`이 sim 33-36 s이고, 그 시점에 `xy_valid`, `z_valid`, `pre_flight_checks_pass`가 이미 참이었다(0.3 s 안에 확인).
- [추정] 이 값으로 셈하면 시나리오마다 재기동은 약 95 s(up 42 + 비행 30 + down 21), 공유하면 둘째 시나리오부터 비행 시간만 든다. 재기동 3회와 공유 3회의 차이는 약 2.1분이다.
- 의견: architecture.md의 "pytest fixture가 `docker compose up --wait`로 스택을 올린다"와 "pytest는 `ros-ws` 컨테이너 안에서"는 지금 구성으로는 한 프로세스에서 함께 성립하지 않는다. docker 소켓을 runner에 주면 성립하지만 판정 컨테이너가 호스트 Docker 전권을 갖고 ros-ws 이미지에 docker CLI가 들어간다(이미지 key 변경). 그래서 문장을 "호스트 진입 스크립트가 `stack.sh up`(내부가 `up --wait`)으로 스택을 올리고, `runner` 안의 pytest가 판정한다. fixture는 스택을 올리지 않고 `stack.json`과 토픽으로 준비를 확인한다"로 바꾸자고 architect에게 올린다. 판정 기준이 바뀌는 것이 아니라 기동 주체의 문장이다.
- 의견: 수명. 정상 비행과 둘째 goal(BUSY), VEHICLE_ID_MISMATCH, INVALID_MISSION은 한 스택을 공유한다(모두 기체를 지상 disarm 상태로 남긴다). 시나리오 사이에는 "지상, disarm, `nav_state`가 Offboard 아님, failsafe 거짓"을 확인하는 사전 조건 fixture를 두고, 깨져 있으면 그 시나리오를 실패로 보고하고 다음 시나리오를 돌리지 않는다(상태가 샌 것을 숨기지 않는다). failsafe 회귀처럼 기체를 failsafe Land로 끝내는 시나리오는 별도 스택(별도 진입 스크립트 호출)에서 돈다.

## T2. `/clock` 시계

결론: `tests/support`에 세션 동안 사는 전용 노드와 전용 spin thread로 `/clock`을 받는 `SimClock`을 두고, 판정 함수에는 그 시계를 주입한다. 판정 노드 자신을 `use_sim_time`으로 두고 호출 안에서만 spin하는 방식은 쓰지 않는다. `/clock`이 멈추면 판정은 영원히 기다리므로 벽시계 상한을 시계 래퍼에 안전망으로 둔다.

- [실측] 가짜 `/clock`(100 Hz 틱, 컨테이너 `--network none`, ROS_DOMAIN_ID 77)에 `SimClock`을 `hold_state`에 주입. RTF 0.5에서 거짓 술어 2 sim s 타임아웃 3회: sim 경과 2.01, 2.02, 2.00 s / 벽시계 4.18, 4.23, 4.18 s. 타임아웃이 sim 시간으로 잰다. 참 술어 N=10은 3회 모두 True.
- [실측] `/clock`을 멈추면 `_wait`의 `clock() - start`가 0에 머문다. 상한 없이는 끝나지 않는다(상한 15 s 래퍼로 끊었고 그동안 sim 경과 0.00 s). 재개하면 다음 호출은 정상(2.03 sim s).
- [실측] 결함 하나: 판정 노드를 `use_sim_time`으로 두고 `hold_state`가 호출 안에서만 spin하면, 호출 사이에 노드 시계가 갱신되지 않는다. 3 s 벽시계 간격 뒤 호출에서 시작 시각이 2.88 sim s 묵었고, 2 sim s 타임아웃이 0.05 s 만에 False로 끝났다(가짜 실패). 다른 3 s 간격 시도는 2.12 s로 정상이었다(재현이 늘 되지는 않는다). 그래서 시계는 판정 노드와 다른, 늘 spin하는 노드에 둔다.
- [실측] rclpy 데몬 spin thread를 끝내지 않고 `rclpy.shutdown()`하면 인터프리터 종료 때 abort(core dump)가 났다. `SimClock`은 fixture teardown에서 executor shutdown과 join을 한다.
- 의견: 벽시계 상한은 판정이 아니라 안전망이다. 값은 "그 대기의 sim 타임아웃 / 최소 허용 RTF + 여유"로 둔다. 제안: 최소 허용 RTF 0.25, 여유 30 s(벽시계). 상한에 걸리면 결과는 False가 아니라 별도 예외(`ClockStalled`)로 올리고 보고에 "`/clock` 정지, 판정 불가"와 마지막 sim 시각을 적는다. 판정 실패(기체가 목표에 못 감)와 기반 실패(`/clock` 끊김)를 섞지 않기 위해서다. 첫 `/clock` 수신 자체는 세션 fixture에서 벽시계 30 s 안에 받아야 한다(못 받으면 세션 실패).
- [소스] A12: PX4 timestamp와 `/clock`을 같은 us 축으로 전제하는 판정은 이번 탐침에서 문제가 없었다(묵은 timestamp 2 s가 그대로 failsafe로 이어졌다, T6). 판정 기준 시각은 ROS 시각으로 둔다.

## T3. 판정 값

결론: 판정식은 아래와 같고 모두 토픽에서만 읽는다. 값은 P7 실측으로 확정할 자리를 표시했다.

- 목표 고도 도달: 기준은 Executor feedback이 아니라 `vehicle_local_position`. goal 전송 직전의 `z0`(지상 z, `z_valid` 참)를 잡고 `|(z0 - z) - height_m| <= acceptance_m`이 연속 N개이면서 그 N개가 덮는 sim 시간이 0.5 s 이상. `z_valid`가 거짓인 메시지는 연속을 끊는다. [실측] `acceptance_m` 0.3에서 3회 모두 arm 뒤 7.2-7.7 sim s에 충족, 호버 10 s 동안 1.0 m 이상 벗어남 0회, 호버 끝 z는 -5.04, -4.98, -5.00. 최대 overshoot는 쟀지 않았다(P7).
- 착륙 후 disarm: `vehicle_status.arming_state == DISARMED`가 연속 N개, 그리고 `vehicle_land_detected.landed` 참. 그 뒤 action 결과 SUCCEEDED, `reason` NONE. [실측] NAV_LAND에서 disarm 연속 10개까지 11.0-11.2 sim s. landed 토픽은 이번 탐침에서 보지 않았다(P6, C7).
- N: 10. 메시지 개수만으로는 발행률이 바뀌면 뜻이 바뀌므로 "N개 그리고 0.5 sim s 이상"으로 둔다. [추정] 발행률은 P7에서 확인.
- 타임아웃(ROS 시각): 세션 준비(EKF와 preflight) 60 s, goal 접수 사건 5 s, 고도 도달 = TAKEOFF 항목의 `timeout`과 같게 하되 테스트 미션 값은 30 s(실측 최대 7.7 s의 약 4배), disarm = LAND 항목 `timeout`, 테스트 값 45 s(실측 11.2 s의 약 4배), 전체 결과 = 항목 timeout 합 + 10 s. 배수 4는 3대 nightly에서 RTF가 떨어져도 sim 시간 기준이라 바뀌지 않는다는 전제의 여유다. 판정 쪽 타임아웃이 Executor 항목 `timeout`보다 짧으면 ITEM_TIMEOUT 결과를 못 보므로 판정 타임아웃은 항목 timeout 이상으로 둔다.
- 판정 값을 통과시키려고 늘리지 않는다. P7 실측이 이 값과 다르면 근거와 함께 다시 올린다.

## T4. `MissionEvent`와 goal 전송 순서

결론: 확인 함수는 `tests/support`에 두고 구독 생성 -> 구독의 발행자 수 1 이상(ROS 시각 타임아웃, 벽시계 안전망) -> `wait_for_server` -> goal 전송 순서로 쓴다. 확인을 넣어도 접수 사건을 잃을 가능성은 남으므로 접수 사건 누락은 재시도 없이 실패로 판정한다. 결과는 goal 수락 직후에 `get_result_async`를 걸어 `result_timeout`에 걸리지 않게 한다.

- 조건: 실제 Executor가 없어 가짜 Executor(rclpy, `/px4_1/execute_mission` action 서버, `handle_accepted`에서 ACCEPTED 발행 뒤 0.5 s 실행하고 SUCCEEDED 발행, `MissionEvent`는 RELIABLE, VOLATILE, KEEP_LAST 10)를 다른 컨테이너에 띄웠다. 두 컨테이너 모두 `network_mode: host`, 저장소 `config/cyclonedds.xml`, ROS_DOMAIN_ID 87. 실제 Executor는 rclcpp라 타이밍이 다를 수 있다([추정]).
- [실측] 한 프로세스에서 구독을 매번 새로 만들고 20회씩: 확인 없음 20회 x 2, 확인 있음 20회 x 2, 구독을 `wait_for_server` 뒤로 미룬 경우 20회. 접수 유실 0, 종료 유실 0.
- [실측] 프로세스마다 새로 띄워 1회(세션의 첫 goal과 같은 조건): 확인 없음 5회 유실 0. 구독을 `wait_for_server` 뒤, goal 직전에 만들고 확인 없음 30회 중 접수 유실 1회. 같은 배치에서 확인 있음 25회(5 + 20) 유실 0.
- [실측] 발행자 수 확인은 모든 회에서 즉시(0.000 s) 참이었다. 원격 writer를 이미 안 상태라 reader 쪽 매칭은 즉시 된다. reader 쪽에서 발행자 1을 본 것이 writer 쪽이 reader를 안 것을 보장하지는 않는다([추정], DDS 매칭은 양쪽이 따로 한다). 그래서 확인은 유실을 줄이는 것이지 없애는 것이 아니고, 남은 위험은 판정에서 실패로 드러나게 둔다.
- [소스] `/opt/ros/jazzy/include/rcl_action/rcl_action/action_server.h` 228행 "result_timeout = RCUTILS_S_TO_NS(10)". rclcpp 서버는 이 기본을 쓴다. rclpy `ActionServer`의 기본은 900 s(`rclpy/action/server.py` 219행). 사본은 ros-ws 이미지의 Jazzy 설치본이다.
- [실측] 가짜 서버를 `result_timeout=10`으로 두고 종료 뒤 결과 요청을 늦췄다: 5 s 늦게 status 4(SUCCEEDED), 15 s 늦게 status 0(UNKNOWN). 6단계 테스트처럼 수락 직후 요청해 두면 서버가 끝날 때 응답하므로 영향이 없다. 결과를 나중에 요청하는 코드를 쓰면 10 s(Executor가 `use_sim_time`이면 ROS 시각, [추정]) 뒤 잃는다. 하네스는 수락 직후 요청을 규칙으로 한다.

## T5. 시나리오와 층 배치

결론: PR마다 도는 SITL은 한 스택에서 정상 비행, BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION 넷이다. 실패 경로의 분기는 단위(가짜 PX4)로 덮고, 공중 취소와 failsafe 회귀는 로컬 전용 SITL로 둔다.

| 시나리오 | 층 | 근거 |
| --- | --- | --- |
| 정상 비행 | SITL, PR마다 | 완료 기준 그 자체. 실측 비행 약 30 s |
| BUSY | SITL, PR마다(정상 비행 실행 중 둘째 goal) | 첫 goal에 영향이 없다는 것을 같은 비행에서 본다. 추가 시간 0에 가깝다 |
| VEHICLE_ID_MISMATCH | SITL, PR마다 + 단위 | 지상에서 즉시 끝난다. 컨테이너 사이 식별 값 전달(params, `stack.json`)은 SITL만 본다 |
| INVALID_MISSION(GOTO 포함) | 단위(검증 규칙 전부) + SITL 1건 | 즉시 끝나서 싸다. SITL 1건은 action 경로 확인용 |
| 지상 취소 | 단위 + SITL 로컬 | 분기는 단위. 실제 disarm 거부 여부(C3)는 P5 결과에 달려 있다 |
| 공중 취소(Hold 뒤 CANCELED) | 단위 + SITL 로컬 | Hold 동작은 PX4 실측(P4)이 계약을 정한 뒤 회귀로. 비행 시간이 든다 |
| NOT_READY, ARM_REJECTED, MODE_SWITCH_FAILED | 단위(가짜 PX4) | SITL에서 만들려면 PX4 상태를 억지로 바꿔야 한다 |
| PRECONDITION_FAILED(공중에서 TAKEOFF) | 단위 | SITL로는 공중 상태를 만들어야 한다 |
| ITEM_TIMEOUT | 단위(가짜 시계) | 시계 주입으로 바로 된다 |
| failsafe 회귀 | SITL 로컬과 nightly, 별도 스택 | T6. 기체를 failsafe Land로 끝내 공유 스택을 더럽힌다 |

- [추정] PR SITL 시간: 이미지 확보와 빌드를 뺀 스택 부분은 up 42 s + 비행 30 s + 즉시 끝나는 goal 셋 수 초 + down 21 s, 약 1.7분.
- 의견: 단위 층에 두려면 R9의 ROS 비의존 핵심(시계와 PX4 입출력 포트를 주입하는 순수 클래스)이 6단계에 있어야 한다. 없으면 위 "단위"의 대부분이 SITL로 오거나 검증 없이 남는다. 나는 6단계에 핵심을 두는 쪽이다. 한 시나리오씩 SITL로 옮기면 하나에 약 1.5분(재기동 포함)이 는다.
- C22(`last_item_index` 구분 필드): 판정 코드는 그 구분을 읽지 않는다. 테스트에서 필요는 드러나지 않았다.

## T6. failsafe 회귀 판정의 주입 방법

결론: 세 방법 모두 failsafe를 일으키지만 `vehicle_status`만으로는 "묵은 timestamp"와 "스트림 없음"을 가르지 못한다. PR 판정에는 주입 대신 "Executor가 /fmu/in에 싣는 timestamp가 `/clock`과 같은 축이다"를 읽기 전용으로 대조하고, 주입 실험(가)는 로컬과 nightly의 별도 스택 시나리오로 둔다.

- [실측] (나)와 같은 효과(발행자가 timestamp를 2 s 묵게 보냄, `20261110-144803-k3`): 호버 중 주입 뒤 0.12 sim s에 `failsafe` 참, `nav_state` 18(Land). disarm까지 정상. 단, 이것은 탐침이 setpoint 발행자 자신이라 가능했다. 하네스가 Executor와 별도로 /fmu/in에 쓰면 같은 토픽에 발행자가 둘이 되어 Executor의 신선한 메시지와 섞이므로 같은 결과를 보장하지 않는다([추정], 실측 안 함). "setpoint는 Executor만"과 "접근은 `idsim_common`만"을 둘 다 깬다.
- [실측] (가) bridge 정지 + 벽시계 timer(timestamp만 sim, `20261110-144941-k3`): `compose stop -t 5 bridge`는 SIGTERM이 듣지 않아 약 5 s 뒤 SIGKILL로 끝났고 그동안 `/clock`이 계속 흘렀다. `/clock`이 멈춘 뒤 약 1 s에 `failsafe` 참, `nav_state` 18. 굳은 timestamp가 계속 발행되는 경로이므로 B안의 "묵은 timestamp" 판정을 실제로 탄다.
- [실측] (가) bridge 강제 종료(`compose kill -s KILL`) + ROS 시각 timer(`20261110-145124-k3`): `/clock`이 멈추자 timer가 멈춰 발행 자체가 끊겼고, 1.04 s 뒤 `failsafe` 참, `nav_state` 18. 결과는 위와 구별되지 않는다. 이것은 "스트림 없음" 경로다.
- 의견: (가)가 "B안 경로가 살아 있다"를 검증하는지는 R1(Executor timer의 시계)에 달려 있다. ROS 시각 timer면 (가)는 스트림 단절만 본다. (가)는 또 docker 조작이 필요해 runner 안 pytest가 하지 못하고(T1) 호스트 진입 스크립트가 해야 한다. 판정이 토픽 밖 동작(호스트에서 컨테이너 정지)에 기대는 것도 원칙과 어색하다.
- 의견: (다) Executor 시험용 파라미터(timestamp 오프셋)는 실제 Executor 경로를 지나는 유일한 방법이다. 운용 노드에 시험 경로가 생기는 대가가 있다. 기본값 0이고 `idsim_common` setpoint helper 밖에서 오프셋을 더하지 못하게 하면 위험은 작다([추정]). 결정은 architect, ros2, px4의 몫이다.
- 의견: 내가 PR 판정으로 제안하는 것: 하네스가 `/px4_1/fmu/in/offboard_control_mode`를 구독만 하고(쓰지 않는다) 받은 메시지의 timestamp와 `SimClock` 값의 차이가 0.2 s 이하가 연속 N개인지 본다. 이것은 "Executor가 sim 시간 timestamp를 싣는다"를 직접 본다. "PX4가 그 timestamp로 손실을 판정한다"는 위의 [실측] 두 건이 근거이고, PX4 태그를 올릴 때 다시 돌리는 로컬 시나리오로 남긴다. 구독만 해도 Python에서 /fmu 이름이 필요하므로 T8의 이름 규칙이 먼저다.

## T7. 종료와 teardown

결론: teardown은 실패해도 끝까지 돌고, 각 단계의 실패를 모아 마지막에 보고한다. 순서는 기체 안전화 확인 -> 진단 수집 -> 판정 노드 종료 -> (호스트) 진단 수집 -> down이다.

- runner 안(pytest fixture, 역순 finalizer):
  1. 진행 중 goal이 있으면 cancel 요청(ROS 시각 10 s 결과 대기).
  2. 기체 상태 확인: `arming_state` DISARMED와 `landed`가 연속 N개(ROS 시각 60 s). 공중이면 테스트가 NAV_LAND를 직접 보내지 않는다(Executor 밖 명령. A4의 표가 테스트 하네스에 명령 source를 주면 그때 다시 본다). 확인 실패는 "기체가 안전 상태가 아님"으로 보고하고 다음 시나리오 진행을 막는다.
  3. 판정 노드 정리: `SimClock`와 `SpinThread`의 executor shutdown, join(벽시계 5 s), 그 뒤 `rclpy.shutdown()`. T2의 [실측]처럼 순서를 어기면 abort가 난다.
- 호스트 진입 스크립트(`trap ... EXIT`):
  4. `compose logs --no-color`를 실행 디렉터리에, ULog 경로 목록 기록. ULog 파일 자체는 `px4-N/log/`로 이미 실행 디렉터리 안에 있다([실측] `r1-none/ulog/`에 사본 `14_43_22.ulg`). ULog가 down에서 정상 종료되는지는 L1(D11)이다. [실측] px4-1은 SIGTERM에 0.22-0.30 s에 exit 0으로 끝났다.
  5. `stack.sh down --stack k`. 이것의 실패(종료 코드 0이 아님, 또는 `idsim-k` 컨테이너가 남음)는 테스트 결과와 별도의 줄로 보고하고 진입 스크립트의 종료 코드를 실패로 만든다. 테스트 통과 + down 실패도 실패다.
- 신호 규칙: 진입 스크립트가 띄우는 백그라운드 프로세스는 `setsid`로 그룹을 만들고 그룹에 SIGTERM을 보낸다(C16). 이번 실측의 감시 프로세스도 SIGTERM으로 정리했다. `compose run`은 `timeout -s TERM`으로 감싼다. pytest 자체가 SIGTERM을 받으면 finalizer가 돌지 않을 수 있으므로([추정]) 호스트 쪽 4, 5는 pytest와 무관하게 trap에서 돈다.
- [실측] bridge와 xrce-agent가 SIGTERM에 끝나지 않는다(T1). teardown 시간 예산은 이것을 넣어 down 30 s(벽시계)로 둔다.

## T8. 하네스의 PX4 접근

결론: Python은 정규식이 아니라 rclpy 메시지 클래스의 `MESSAGE_VERSION`으로 접미사를 파생하는 쌍둥이 함수를 `tests/support`에 둔다. 65개 golden과 모두 맞는다. 단, 논리 이름과 타입의 짝은 C++ 기술자 목록과 같은 표가 Python에도 필요하다.

- [실측] ros-ws 이미지의 px4_msgs Python 클래스로 `tests/fixtures/px4/v1.17.0/topics.txt` 65줄의 (토픽, 타입)을 대조: 기저 이름 + (`MESSAGE_VERSION`이 0이 아니면 `_v<N>`)이 65개 모두 golden과 같다. 속성 자체가 없는 클래스 26개, 0인 것 31개, 접미사가 붙는 것 8개. 기저 이름에 `_v숫자` 모양이 들어간 토픽은 없다.
- 의견: 속성이 없는 클래스가 26개라 "속성이 없거나 0이면 접미사 없음"을 C++과 같은 규칙으로 명시한다. 토픽 기저 이름은 타입 이름에서 기계적으로 나오지 않는다(예: `aux_global_position`의 타입은 `VehicleGlobalPosition`). 그래서 Python 쪽은 (방향, 논리 이름, 타입) 표가 필요한데, 이것을 손으로 다시 쓰면 C++ 기술자 목록과 두 벌이 된다. 제안: golden `topics.txt`와 Python 파생 결과를 비교하는 단위 테스트를 `tests/support`에 두고, 표는 6단계에서 쓰는 토픽(`vehicle_status`, `vehicle_local_position`, `vehicle_land_detected`, `offboard_control_mode` 읽기)만 둔다. C++ 목록과의 교차 검사는 R(ros2)과 정한다.
- 의견: 하네스가 /fmu/in에 쓰는 일은 6단계에 남기지 않는 것이 내 제안이다(T6에서 구독만, T7에서 착륙 명령 안 보냄). `check_px4.py`(254/1)는 스모크에 그대로 남으므로 P11의 source 표가 나오면 거기에 맞춘다.

## T9. "3회 연속"과 플래키 정책

결론: 3회는 "호스트 진입 스크립트 3번 호출"이고 매번 스택을 새로 올린다. 기록은 실행 id 3개와 git commit, 결과 JSON을 한 요약 파일에 남긴다.

- 정의: 한 회 = `stack.sh up`부터 down까지 전부. 같은 git commit, 같은 이미지 digest, 사이에 코드 변경 없음. 중간에 다른 스택이 떠 있었는지와 load average를 회마다 적는다(이번 실측처럼 다른 스택과 함께 돌면 그것도 조건이다).
- 기록: 진입 스크립트에 반복 옵션(예: `--repeat 3`)을 두고, 각 회의 실행 id(`<UTC>-k<k>-sitl-<회>`), pytest junit XML, 판정 JSON(단계별 sim과 벽시계 시각), 종료 코드를 `artifacts/sitl-repeat-<UTC>/summary.json`에 모은다. 첫 실패에서 멈추지 않고 3회를 다 돌려 몇 번 중 몇 번인지를 남긴다. "3회 연속"은 summary의 세 회가 모두 통과일 때만이다.
- 실패 1회: 판정 기준과 타임아웃을 바꾸지 않는다. 그 회의 실행 디렉터리(compose 로그, ULog, 판정 JSON)를 보존하고 증상별 담당자(px4, ros2, sim, devops)에게 넘긴다. 원인이 닫힌 뒤 3회를 처음부터 다시 센다. 같은 원인이 아닌 것이 확인되지 않은 실패는 플래키로 보고 "재시도로 통과"를 통과로 세지 않는다.
- CI: PR당 1회(architecture.md 그대로). 재시도는 수동. nightly(3대)에서 1회. CI에서 반복을 늘리는 것은 비용이라 사용자 결정이다.
- [실측] 참고: 이번 탐침의 정상 비행 3회는 모두 통과했다(Executor 대역이라 완료 기준의 3회는 아니다).

## T10. 디렉터리와 진입점

결론: `tests/sitl/`에 진입 스크립트 `run_sitl.sh`와 pytest 파일을 둔다. 공용 판정은 `tests/support/`에 더한다. `run_smoke.sh`와는 `stack.sh`와 `sj` 같은 공용 부분만 공유하고 합치지 않는다.

- 배치 제안: `tests/sitl/run_sitl.sh`(호스트, `stack.sh up` -> `compose run runner python3 -m pytest tests/sitl` -> 진단 수집 -> down, `--stack`, `--repeat`, `--fleet`), `tests/sitl/conftest.py`(세션: `stack.json` 읽기, `SimClock`, 준비 확인, 사전 조건 fixture), `tests/sitl/test_takeoff_land.py`, `tests/sitl/test_goal_rejects.py`(BUSY, MISMATCH, INVALID). 공용: `tests/support/clock.py`(`SimClock`, 안전망), `tests/support/judge.py`(고도, disarm, `MissionEvent` 대기), `tests/support/px4_names.py`(T8). `tests/support/receive.py`의 기본 시계를 벽시계로 두는 것은 스모크 호환으로 남긴다.
- `run_smoke.sh`와의 관계: 스모크는 S2-S5 단계 판정이고 벽시계 타임아웃이다. SITL 통합은 `/clock` 기준이다. 시간 규칙이 달라 한 스크립트로 합치면 둘 다 어색해진다. 공용으로 뽑을 것은 `sj`(stack.json 읽기)와 cyclonedds 해시 대조(T11) 정도다.
- `tools/ros_ws.sh`의 패키지별 1건 이상 단정: `idsim_mission`에 GoogleTest 1건 이상과 ament lint가 colcon test 결과로 잡혀야 한다(`no_test_packages`에 넣지 않는다). 단위 층에 R9의 순수 클래스 테스트, C19-C21, C24가 들어가면 자연히 충족된다. `tests/sitl/`는 colcon 패키지가 아니므로 이 단정 대상이 아니고 `sitl` job이 따로 단정한다(junit의 테스트 수 0이면 실패).

## T11. 설정 일치 검사

결론: cyclonedds.xml sha256 대조를 `tests/support/stack.py`의 함수로 옮기고, 스모크와 SITL 통합이 같은 함수를 쓴다. SITL에서는 세션 fixture의 첫 단계(ROS 참가자를 만들기 전)에 둔다.

- [소스] 지금 대조는 `tests/smoke/run_smoke.sh` 253-263행의 bash 함수 `dds_config_changed`(호스트 python3 한 줄)뿐이다. `tests/support/stack.py`의 `_SPEC["inputs"]`는 `fleet`, `px4_params_file`, `versions_env`만 검증하고 `cyclonedds_xml`은 스키마에 없다(41-49행).
- 의견: `stack.py`에 `cyclonedds_xml`을 스키마로 더하고 `Stack.check_inputs(repo_root)` 같은 함수(현재 파일의 sha256과 `stack.json` 값 비교, 다르면 어떤 입력이 다른지 돌려줌)를 둔다. pytest는 세션 fixture에서 불일치면 바로 실패(판정 참가자를 만들기 전이라 섞인 설정의 참가자가 생기지 않는다). `run_smoke.sh`는 같은 함수를 `python3 -m`으로 부른다. runner 안과 호스트가 같은 저장소 파일을 마운트로 보므로 어느 쪽에서 읽어도 같다. 같은 함수에 `px4_params_file`, `fleet`도 넣을지는 devops와 정한다(테스트가 쓰는 값의 출처라 넣는 쪽을 권한다).

## 부딪칠 것으로 보이는 지점

- T1과 architecture.md: "fixture가 compose를 올린다" 문장을 호스트 진입 스크립트로 바꾸자는 제안이다(D3, D7과 겹친다). runner에 docker 소켓을 주는 대안은 devops의 이미지와 보안 판단이다.
- T6과 R1, P9: Executor timer가 ROS 시각이면 bridge 정지 주입은 묵은 timestamp 경로를 검증하지 못한다(실측). 내 PR 판정 제안은 /fmu/in 구독(읽기)이 필요하다.
- T5와 R9: 실패 경로를 단위에 두려면 6단계에 ROS 비의존 핵심이 있어야 한다.
- T1, T7과 devops, ros2: bridge와 xrce-agent가 SIGTERM에 끝나지 않아 down이 약 20 s다(실측). `sitl` job 시간과 teardown 예산에 들어간다.
- T4: 발행자 수 확인으로도 접수 사건 유실을 완전히 막지 못할 수 있다(reader 쪽 매칭만 본다). C14의 "확인 뒤 전송"은 따르고, 남은 위험은 실패로 드러나게 둔다.

## 실험을 못 한 문항과 이유

- T3: 최대 overshoot, `vehicle_land_detected`, 발행률은 재지 않았다. P7, P6의 범위라 빌려 쓴다.
- T4: 실제 Executor(rclcpp)가 없어 rclpy 가짜 서버로 쟀다. 유실 1/30은 표본이 작다. Executor가 생기면 같은 탐침을 다시 돌린다.
- T6: (나)를 Executor와 별도 발행자로 실제로 해 보지 못했다(Executor가 없다). (다)는 구현이 없어 실측 불가. 탐침의 묵은 timestamp는 발행자 자신이 바꾼 것이라 (다)에 가깝다.
- T8: C++ 기술자 목록과 Python 파생의 교차 검사는 하지 않았다(빌드 금지 조건).
- T1의 "fixture가 compose를 직접 올리는" 경로는 docker 소켓 마운트를 해 보지 않았다(저장소와 이미지를 바꾸지 않는 조건).

## 재질문 답(2026-11-11)

실측 조건
- 스택 k=3, standalone 1대, 이미지 `idsim/*:local`, 4 vCPU, 7.7GB. 회마다 `tools/stack.sh up`부터 `down`까지 새로 올렸다. 시작 전 `docker ps -a` 비어 있음, load1 0.03. 측정 중 5 s마다 `docker ps`와 load를 기록했고, 보인 컨테이너는 `idsim-3`의 넷과 내 탐침(`t_flight`, `t_judge`)과 부하 컨테이너(`t_load`)뿐이다.
- 혼자 3회(r1-r3, 실행 id `20261110-164536-k3`, `20261110-164733-k3`, `20261110-164919-k3`). 비행 중 load1 0.3-5.2(스택과 탐침 자신의 부하).
- 부하 2회. r4(`20261110-165128-k3`)는 up 뒤 5 s에 부하를 걸어 load1이 비행 중 2.1-4.1에 그쳤다. 그래서 r5(`20261110-165438-k3`)는 up 60 s 전부터 부하를 걸었다(비행 중 load1 5.5-7.8). 부하: `idsim/ros-base:local` 컨테이너 하나에서 python busy loop 프로세스 4개, CPU 제한과 nice 없음. 수치는 r5를 부하 값으로 쓰고 r4는 참고로 둔다.
- 탐침(scratchpad `rq_t/`): `flight2.py`(Executor 대역, 유일한 setpoint 발행자, ROS 시각 20 Hz timer, 기준점은 goal 직전 대역 시점의 z, 목표는 z0 - 5 m), `judge.py`(별도 컨테이너. 구독만. `offboard_control_mode`와 `vehicle_status_v1`의 timestamp와 수신 시 SimClock. SimClock은 같은 executor에서 늘 spin하는 별도 `use_sim_time` 노드), `round2.sh`, `ana.py`. 회별 기록은 `rq_t/r1`-`r5`. 저장소 `ros_ws`는 빌드하지 않았고 저장소 파일은 이 절 말고 바꾸지 않았다.
- 비행 절차: 지상 준비 -> setpoint 15개 -> Offboard -> arm -> 고도 판정(|(z0 - z) - 5| <= 0.3이 연속 10개) -> 호버 10 s -> 묵음 0.5 s(그 뒤 10 s 동안 손실이 없는지) -> 묵음 시작(재개하지 않음) -> `offboard_control_signal_lost`, `failsafe`와 `nav_state` 18 -> disarm 연속 10개.
- 정리: 매회 `stack.sh down`, 탐침과 부하 컨테이너 삭제, 끝난 뒤 남은 컨테이너 0개. `artifacts/runs/`에 실행 디렉터리 5개(비추적)가 남았다.

### 재질문 test 1. PX4 탐침 시나리오

[실측] 한 벌(묵음 0.5 s 시작부터 disarm 연속 10개까지)과 비행 전체.

| 회 | 0.5 s 묵음 뒤 10 s의 손실 | 묵음 중 `offboard_control_mode` 간격(sim) | 손실 flag(묵음 시작 기준) | `failsafe`, `nav_state` 18 | disarm | 한 벌 sim / 벽시계 | 비행 전체 sim / 벽시계 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| r1 | 없음 | 0.548 s | 1.044 s | 1.056 s | 12.69 s | 22.69 / 22.69 s | 41.82 / 41.87 s |
| r2 | 없음 | 0.548 s | 1.016 s | 1.028 s | 12.30 s | 22.30 / 22.31 s | 41.78 / 41.79 s |
| r3 | 없음 | 0.552 s | 1.028 s | 1.040 s | 12.43 s | 22.43 / 22.43 s | 42.49 / 42.54 s |
| r5(부하) | 없음 | 0.548 s | 0.996 s | 1.044 s | 12.40 s | 22.40 / 22.44 s | 41.65 / 41.79 s |

- r4(부하 약함): 손실 0.992 s, `nav_state` 18 1.172 s, disarm 12.39 s. 5회 모두 "0.5 s 묵음은 정상, 1.5 s 묵음은 ROS 시각 2 s 안에 손실과 Land"를 만족했다. 최악 여유는 r4의 0.83 s.
- 0.5 s 묵음은 실제로 0.55 s 간격이 된다(timer 주기 50 ms가 더해진다). 0.5 s 묵음 뒤 10 s 동안 고도 오차는 -0.012-+0.036 m였다.
- 한 회 벽시계: up 35.1-35.8 s(혼자), 42.3 s(r5, 부하) + 비행 43.6-43.9 s(탐침 컨테이너 기동 포함) + down 20.7 s. 혼자 약 100 s.

의견: 저장소에 둔다. 위치는 `tests/sitl`도 스모크도 아닌 `tests/px4_facts/`이고 로컬 전용이다.
- 두는 이유: 9번 (A)의 PR 판정("Executor timestamp가 `/clock`과 같은 축")은 (B)("PX4가 그 timestamp로 손실을 판정한다")가 참일 때만 failsafe 회귀를 대신한다. (B)는 `PX4_TAG`에 묶인 사실이고(`COM_OF_LOSS_T`의 뜻, `/fmu/in` timestamp의 `min()` 처리) 태그를 올릴 때 사람이 절차를 다시 짜는 것보다 스크립트 한 번이 싸다. 비용은 혼자 약 100 s다.
- 스모크 계열이 아닌 이유: 스모크(S2-S5)는 arm하지 않고 벽시계 타임아웃이다. 이 시나리오는 비행하고 `/clock` 기준이다. `tests/sitl`이 아닌 이유: PR 하네스의 규칙("/fmu/in에 쓰지 않는다")을 디렉터리 경계로 지키기 위해서다.
- 진입: `tests/px4_facts/run.sh`(호스트, `run_sitl.sh`와 같은 꼴로 `stack.sh up` -> `compose run runner pytest tests/px4_facts` -> 진단 수집 -> down). 판정은 `tests/support`의 `SimClock`과 판정 함수를 같이 쓴다. 실행 시점은 `PX4_TAG`, px4 파라미터 파일, `idsim_common`의 timestamp helper를 바꾸는 PR의 로컬 확인이고, PR 본문에 결과 요약을 붙인다. CI에 넣을지(nightly)는 비용이라 사용자 결정으로 올린다.
- "6단계 하네스는 /fmu/in에 쓰지 않는다"와의 관계: 문장을 "`tests/sitl`과 `tests/smoke`는 /fmu/in에 발행하지 않는다. /fmu/in 발행은 `tests/px4_facts/`만 한다"로 좁힌다. 탐침이 유일한 발행자라는 것은 토픽으로 확인한다: 시작 전과 묵음 직전에 `/fmu/in/offboard_control_mode`와 `trajectory_setpoint`의 발행자가 자신 하나인지(`get_publishers_info_by_topic`) 보고, 아니면 판정 불가로 끝낸다. 그 스택에서는 goal을 보내지 않으므로 Executor가 떠 있어도 발행하지 않는다(2번 결정의 발행 규칙). 그래서 별도 compose 변형이 필요 없다([추정], Executor 구현 뒤 확인).
- `px4-api` 검사의 예외 형태: [소스] `tools/ci/lint.sh` 227-245행의 검사 대상은 `ros_ws/src` 아래 `idsim_common` 밖의 C++과 `.py`이고 `tests/`는 처음부터 대상이 아니다. 그래서 lint의 예외는 필요 없다. 대신 새 검사 하나를 제안한다(소유는 devops, 규칙은 test): `tests/` 아래에서 /fmu/in 이름을 만드는 함수(`tests/support/px4_names.py`에 둘 `in_topic_for_publish` 같은 이름 하나)를 부르는 파일은 `tests/px4_facts/`에만 있어야 한다. 9번 (A)의 구독은 다른 함수(`in_topic_for_subscribe`)를 쓴다. 이 검사도 실수 방지 수준이다.

### 재질문 test 2. timestamp 축 판정의 값

[실측] `offboard_control_mode`: 수신 시 SimClock - `timestamp`(ms, 음수가 없으면 최소 0).

| 회 | 구간 | 표본 | 중앙값 절댓값 | p99 | 최소 | 최대 |
| --- | --- | --- | --- | --- | --- | --- |
| r1 | 호버 10 s / 비행 전체 | 200 / 565 | 0 / 0 | 4.0 / 8.0 | 0 / 0 | 12 / 12 |
| r2 | 같음 | 200 / 564 | 0 / 0 | 4.0 / 4.0 | 0 / 0 | 8 / 8 |
| r3 | 같음 | 200 / 566 | 0 / 0 | 4.0 / 4.0 | 0 / 0 | 4 / 4 |
| r5(부하) | 같음 | 200 / 563 | 0 / 0 | 4.0 / 4.0 | 0 / 0 | 8 / 8 |

- r4도 최대 8 ms. 값은 `/clock`의 4 ms 양자화를 따른다. 음수(수신 시각보다 앞선 stamp)는 0건이다.
- [실측] `vehicle_status_v1`(스모크 S5 안, 9번 (A')): 중앙값 절댓값 0 ms. 최대가 매회 176-180 ms이고 모두 arm 전이의 메시지 한 건이다(5/5). r4는 failsafe 전이에서 164 ms, 112 ms가 더 있었다. 상태 전이에서 나가는 `vehicle_status`가 그 전 주기의 timestamp를 싣는 것으로 보인다[추정, 소스 확인 안 함]. 앞선 의견서와 결정 초안의 "176 ms"는 경합이 아니라 이것이다. sim의 -8-8 ms에는 arm이 없었다.

의견: 초안의 "중앙값 절댓값 0.1 s 이하, 최대 절댓값 0.5 s 이하"에 동의한다.
- `offboard_control_mode`에서 최대 0.5 s는 관측 최대 12 ms의 40배, sim의 `/clock` 끊김 최대 25.9 ms의 19배 여유다. 잡으려는 회귀(벽시계 epoch, steady 시각, 멈춘 시계, 고정 오프셋 1 s 이상)는 모두 몇 자릿수 차이라 0.1-0.5 s 어디에 두어도 잡힌다. 손실 판정 1 s보다 작게 두어야 "PX4가 묵었다고 볼 값"을 놓치지 않으므로 0.5 s가 위쪽 끝이다.
- 초안 9번의 "0.2 s는 수신 지연 0.176 s 때문에 여유가 없다"는 근거를 고쳐야 한다. 0.176 s는 `vehicle_status`의 arm 전이 한 건이고 `offboard_control_mode`와 무관하다. 그렇다고 0.2 s로 돌아가자는 것은 아니다. 두 판정(A, A')을 같은 통계로 두는 초안이 단순하다.
- (A')에는 주의 하나: 최대 0.5 s는 arm 전이의 180 ms 대비 2.8배 여유뿐이다. S5는 arm하지 않으므로 지금 S5에서는 영향이 없다. SITL 정상 비행에서 같은 통계를 `vehicle_status`에 걸면 이 값이 들어간다.
- 표본 구간: 호버 구간만이 아니라 "setpoint 발행 시작부터 disarm까지"의 전체로 한다. 이번 실측에서 전체와 호버의 최대가 같았고, 전체로 보면 PREPARING의 timestamp도 같이 본다. 표본 수 하한 100개(20 Hz에서 5 sim s)를 두어 구독이 늦게 붙어 표본이 적은 회는 판정 불가로 끝낸다.

### 재질문 test 3. 고도의 독립 판정

[실측] z(NED, m). "goal 직전"은 탐침의 준비 확인 시점(새 회) 또는 `ready` 시점(앞선 r1-r3).

| 회 | goal 직전 z | goal 직전 0.5 s 중앙값 | arm 시점 z | 직전 - arm | disarm 뒤 z | 직전 - disarm 뒤 |
| --- | --- | --- | --- | --- | --- | --- |
| 앞선 r1 | -0.027 | - | -0.031 | 0.004 | 0.006 | -0.033 |
| 앞선 r2 | -0.202 | - | -0.171 | -0.031 | -0.006 | -0.196 |
| 앞선 r3 | -0.196 | - | -0.190 | -0.006 | -0.032 | -0.164 |
| r1 | -0.427 | -0.428 | -0.401 | -0.026 | -0.027 | -0.400 |
| r2 | -0.198 | -0.199 | -0.183 | -0.015 | -0.067 | -0.131 |
| r3 | -0.297 | -0.299 | -0.274 | -0.023 | -0.045 | -0.252 |
| r4 | -0.215 | -0.222 | -0.196 | -0.019 | 0.031 | -0.246 |
| r5 | -0.250 | -0.258 | -0.241 | -0.008 | -0.023 | -0.227 |

- goal 직전과 arm 사이는 0.92-0.97 sim s이고 z 차는 최대 0.031 m다(8회).
- 기동 직후(첫 `vehicle_local_position` sim 29-36 s) 지상 z는 -0.43-0 m 사이에 있고 계속 움직인다. [실측] 앞선 r1-r3의 ULog에서 arm 전 1 s 창의 z 범위 0.009-0.034 m, 5 s 창 0.081-0.128 m, 10 s 창 0.191-0.243 m.
- 비행 동안 추정 좌표계의 지면이 움직인다: goal 직전 z와 착지 뒤 z의 차가 최대 0.400 m(r1)다. px4의 "60 s에 최대 0.28 m"보다 크다. 이것은 "실제 지면 위 높이"의 오차이고 Executor와 판정이 같은 좌표계를 쓰는 한 둘의 비교에는 들어가지 않는다.
- 고도 추종: 도달 판정 2 s 뒤부터 호버 끝까지 (z0 - z) - 5는 -0.097-+0.031 m. overshoot는 최대 0.031 m(아래에서 다가간다). arm에서 도달 판정까지 7.60-7.82 sim s(5회). `vehicle_local_position`은 50 Hz라 N=10은 0.2 s이고 "0.5 sim s 이상" 조건이 실제로 정한다.

의견
- `z0`는 goal 전송 직전에 잡는다. 값은 직전 0.5 sim s 안의 `z_valid` 표본 5개 이상의 중앙값이다(표본이 모자라면 기다린다. 세션 준비 타임아웃 안에서). arm 시점은 쓰지 않는다. arm은 Executor 절차 안의 사건이라 판정이 Executor 단계에 기대게 되고, 값도 직전 시점과 최대 0.031 m만 다르다. Executor의 기준점(PREPARING 4단계)은 그 둘 사이에 있으므로 판정 `z0`와 Executor 기준점의 차는 실측 최대 0.031 m 안이다.
- 허용값 `acceptance_m`은 0.3 m를 유지한다. 근거: 추종 오차(정착 뒤 최대 0.097 m)와 기준점 차(최대 0.031 m)의 합 0.13 m에 2배 남짓의 여유. 지상 drift 0.28 m(px4)나 비행 중 좌표계 이동 0.40 m(이번)는 같은 좌표계 비교에 들어가지 않으므로 허용값에 더하지 않는다. 0.3 m가 좌표계 이동과 비슷한 크기인 것은 우연이고 그것을 덮으려는 값이 아니다.
- 기준점의 잘못을 잡는 판정을 하나 더한다: 하네스가 `trajectory_setpoint`를 구독만 하고(9번 (A)와 같은 구독), PREPARING 뒤 첫 setpoint의 z와 `z0 - height_m`의 차가 0.1 m 이하인지 본다. 0.1 m는 기준점 차 실측 최대 0.031 m와 arm 전 1 s 창의 지상 z 범위 최대 0.034 m에 여유를 둔 값이다[추정, 실제 Executor로 다시 잰다]. 이것이 없으면 Executor가 기준점을 늦게(예: 기동 시점에) 잡아 0.2-0.4 m 틀려도 고도 판정 0.3 m 안에서 통과할 수 있다.
- 실제 지면 위 높이를 따로 보려면 Gazebo 기체 pose가 필요한데, bridge 설정 파일을 1b로 넘긴 7번 결정과 묶인다. 그때의 허용값은 0.3 m에 좌표계 이동(실측 최대 0.40 m)을 더해야 해서 판정 힘이 약하다. 6단계에는 넣지 않는다.

### 앞선 답에서 바뀐 것

- T1: 혼자일 때 `up` 35.1-35.8 s(앞선 값 41-44 s는 경합), 부하 아래 42.3 s. `down`은 혼자도 20.7 s(bridge와 xrce-agent의 SIGKILL 대기, devops 실측과 같다). devops 변경(bridge 직접 실행, xrce-agent `init: true`) 뒤에는 0.8 s다. 그러면 시나리오마다 재기동하는 비용은 약 95 s에서 약 37 s + 비행으로 준다. 그래도 PR 묶음이 한 스택을 공유하는 결론은 그대로다(시나리오 넷에 약 1.8분 차이). failsafe 시나리오와 `tests/px4_facts/`는 별도 스택이다.
- T3: 고도 판정을 `z0` 기준 상대 높이로 바꿔 쟀다. arm에서 도달까지 7.60-7.82 s(앞선 값 7.2-7.7 s는 절대 z 기준). overshoot 최대 0.031 m(앞선 답은 미측정). 고도 타임아웃 30 s는 3.8배 여유라 그대로 둔다. `z0` 정의를 위 3번대로 고친다.
- T3, T5: px4의 실측(지면 근처 Hold는 armed로 남는다)에 따라 사전 조건 fixture("지상, disarm, `nav_state`가 Offboard 아님, failsafe 거짓")가 취소 시나리오 뒤의 armed 지상 Hold를 잡는다. px4의 분기(셋 중 하나가 참이면 Land를 끝까지)가 구현되면 이 상태는 정상 경로에서 생기지 않는다. 로컬 SITL의 공중 취소 시나리오 뒤에 `[LAND]` 하나짜리 미션을 이어 보내 기체를 내리는 것을 T5의 같은 시나리오 안에 둔다(teardown이 NAV_LAND를 직접 보내지 않는다는 T7 규칙과 맞는다).
- T6: "0.2 s 이하 연속 N개"는 버리고 초안의 통계(중앙값 0.1 s, 최대 0.5 s, 전체 구간, 표본 하한)로 바꾼다. 묵은 timestamp 주입은 `tests/px4_facts/`로 옮긴다.
- T7: teardown 예산. devops 변경 전에는 down 30 s(벽시계) 그대로. 변경 뒤에는 15 s로 줄인다(`mission-N`의 `stop_grace_period` 10 s가 최악이고 여유 5 s. ros2 실측으로 직접 실행 노드의 SIGTERM 종료는 0.1-0.2 s). 진단 수집에 bridge, xrce-agent, `mission-N`의 컨테이너 종료 코드를 남긴다(devops 의견과 같다). 표식 파일 healthcheck의 tmpfs mode 함정은 재시작 경로에서만 생기므로 `stack.sh`가 매번 down 뒤 up하는 하네스에는 영향이 없다. 그래도 사전 조건 fixture는 healthcheck가 아니라 토픽으로 본다(앞선 답 그대로).
- T2: sim의 `/clock` 끊김 최대 25.9 ms로 벽시계 안전망 값(최소 RTF 0.25, 여유 30 s)은 바꿀 근거가 없다.
