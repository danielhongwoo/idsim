# idsim_mission

기체 하나의 Mission Executor. `ExecuteMission` action 서버(`/<vehicle_id>/execute_mission`)로 미션을 받아 PX4 Offboard로 실행하고, goal마다 접수와 종료 사건(`mission_event`)을 낸다. 설계 결정의 정본은 `docs-for-agent/plan-1a-6-idsim-mission/decisions.md`(쟁점 2, 3, 4, 6, 10)다. 이 문서는 구현 규칙과 경계를 적는 설계 노트다.

## 구성

| 대상 | 내용 | 의존 | 소유 | 단계 |
| --- | --- | --- | --- | --- |
| `idsim_mission_core` | 미션 검증, `TYPE_*` 분류, 상태기(`MissionRunner`), 종료 결과 | 없음(C++17 표준 라이브러리만) | ros2-engineer. `core/snapshot.hpp`와 상태기 전이 표는 px4-engineer 필수 승인 | P3b(이 단계) |
| `idsim_mission_px4` | px4_msgs -> snapshot 변환, 명령 목록 -> `VehicleCommand`와 setpoint | core, `idsim_common`, px4_msgs | px4-engineer(`include/idsim_mission/px4/`, `src/px4/`, `test/px4/`) | P3c |
| `mission_executor_component` | lifecycle 노드 껍질 `idsim_mission::MissionExecutorNode`(컴포넌트), action 서버, 사건 발행, 계약 메시지 변환(`node/conversion.hpp`) | core, px4 어댑터, idsim_interfaces, rclcpp_lifecycle, rclcpp_action, rclcpp_components | ros2-engineer | P3d |

- `idsim_mission_core`는 어떤 ROS 패키지도 링크하지 않는다(CMake 대상에 링크가 없다). 단위 테스트는 gtest와 core만 링크한다. ctest의 `core_purity`가 core 소스에 `clock::now`, `clock_gettime`, `gettimeofday`, `std::time`, `this_thread`, `getenv`, `rclcpp`, `px4_msgs`, `idsim_common`, `idsim_interfaces`, `builtin_interfaces` 문자열이 없는지 본다(주석 줄 제외). `core_purity_negative`는 금지 문자열을 심은 임시 파일로 검사기 자체가 그 수만큼 잡는지 본다.
- core는 `idsim_interfaces`의 메시지를 쓰지 않고 같은 값을 다시 적는다(`core/types.hpp`의 `Reason`, `item_type`, `FeedbackPhase`, `core/termination.hpp`의 `event_status`). 값이 메시지 상수와 같은지는 `test/node/test_contract_constants.cpp`가 교차 검사한다(13, 14 포함). core의 `enu_to_ned_yaw`, `wrap_pi`가 `idsim_common/frames`와 같은 값인지도 같은 파일이 본다.

## core와 어댑터의 경계

경계는 `include/idsim_mission/core/snapshot.hpp` 하나다. 헤더 머리 주석에 px4_msgs 필드와의 대응표가 있고 P3c는 그 표대로 채운다. 요약:

- 입력: tick 번호, 그 tick의 ROS 시각, `Snapshot`(토픽마다 최신 표본 하나), `Px4ClockPort`(실패할 수 있는 `Px4Timestamp` 공급). core는 벽시계와 rclcpp를 부르지 않는다(decisions.md 쟁점 6 C1).
  - `Snapshot.status`(vehicle_status): `timestamp_us`, `received_tick`, `received_ns`, 식별 대조 결과와 불일치 설명, `Arming`, `NavMode`(nav_state와 사용자 의도. OFFBOARD, AUTO_LOITER, AUTO_LAND, 그 밖), `failsafe`.
  - `Snapshot.land`(vehicle_land_detected): `landed`.
  - `Snapshot.position`(vehicle_local_position): x, y, z, heading(NED), `z_valid`.
  - `Snapshot.flags`(failsafe_flags): `ekf_ready`(무효 flag 넷이 모두 false. 술어는 어댑터), `offboard_signal_lost`.
  - `Snapshot.ack`(vehicle_command_ack, target이 이 Executor인 것만): command 묶음(DO_SET_MODE, ARM_DISARM, NAV_LAND)과 result.
  - `received_tick`은 "그 표본을 처음 볼 수 있는 step의 tick 번호"다. 그래서 step k에서 낸 명령의 응답은 `received_tick > k`다.
- 출력(`StepOutput`): `px4_timestamp_us`(이 tick의 명령과 setpoint에 실을 값), `setpoint`(있으면 이 tick에 `offboard_control_mode`(position만)와 `trajectory_setpoint`를 발행), `commands`(`CommandKind` 목록. 재전송도 여기에 나온다), `feedback`, `termination`.
  - `CommandKind` -> `VehicleCommandBuilder`: `kSetModeOffboard` -> `set_mode_offboard`, `kSetModeHold` -> `set_mode_hold`, `kArm` -> `arm`, `kDisarm` -> `disarm`(강제가 아님), `kNavLand` -> `land`.
  - `SetpointOut.kind == kGround`이면 어댑터가 z에 지상 setpoint 오프셋 +0.5 m(NED 아래쪽, 어댑터 상수)를 더한다. core는 그 값을 모른다.
  - 노드는 `Px4ClockPort::now_us`가 그 tick에 만든 `Px4Timestamp` 객체를 보관해 두고 그 객체로 명령과 setpoint를 만든다(`Px4Timestamp`는 시계에서만 만들 수 있다).

## 노드 껍질(P3d)

실행: `ros2 launch idsim_mission vehicle_ops.launch.py namespace:=/px4_N executor_name:=<이름> params_file:=<파일>`. launch는 `component_container_isolated`(이름 `ops_container`)에 컴포넌트 하나를 load하고(`ComposableNode`, autostart 없음), `output='screen'`, 컨테이너에 `on_exit=Shutdown()`을 건다. 세 인자 모두 기본값이 없다. params 예시는 `config/ops.example.yaml`(생성기가 만드는 `/**`의 넷: `use_sim_time`, `vehicle.id`, `vehicle.ns`, `vehicle.sysid`).

파라미터(모두 읽기 전용, 생성기는 만들지 않는다): `lifecycle.self_start`(bool, 기본 true), `command_source.system`(254), `command_source.component`(191), 타임아웃 여덟(`ready_timeout`, `offboard_signal_timeout`, `mode_confirm_timeout`, `arm_timeout`, `hold_confirm_timeout`, `link_timeout`, `land_disarm_fallback_delay`, `command_resend_period`. 초 단위 double, 기본값은 `core/config.hpp`).

lifecycle
- 생성자: `vehicle.*`를 한 번 선언하고 해석한다(실패는 configure에서 드러난다). `lifecycle.self_start`가 true이면 벽시계 0 ms 일회 timer를 만들고, 그 콜백의 첫 줄에서 timer를 취소한 뒤 `configure()`와 `activate()`를 한 번씩 부른다. 실패하면 그 상태에 남고 `IDSIM_EXECUTOR_START_FAILED: <전이> failed, state <상태>: <이유>` 한 줄을 ERROR로 남긴다(`kStartFailedLogPrefix`). 프로세스는 끝내지 않는다.
- on_configure: `vehicle.*` 해석 실패, `use_sim_time` false, 노드 네임스페이스와 `vehicle.ns` 불일치, 타임아웃 0 이하, command source 무효나 source == sysid이면 FAILURE. 구독 다섯, PX4 발행자 셋, 사건 발행자, `RosPx4ClockPort`를 만든다.
- on_activate: 첫 `/clock`을 벽시계 2 s 기다리고(`wait_until_started`. 파라미터가 아니다) `Px4Timestamp::now`가 되는지 본 뒤 발행자를 켜고, 20 Hz tick timer(노드 시계)와 action 서버를 만든다.
- on_deactivate: goal 실행 중이면 FAILURE(active에 남는다). 아니면 action 서버와 timer를 없앤다.
- on_shutdown, on_error, context 종료 직전(pre-shutdown callback): 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝내고 종료 사건을 낸다. on_shutdown 뒤에도 action 서버는 소멸자까지 남는다(끝낸 goal의 result 요청에 답해야 한다). 그 뒤에 온 goal은 `handle_accepted`가 즉시 ABORTED, REASON_INTERNAL("executor is not active")로 끝낸다.
- callback group은 MutuallyExclusive 하나(PX4 구독, tick timer, action 서버). pre-shutdown callback은 다른 thread에서 돌 수 있어 goal 상태와 snapshot은 mutex로 지킨다.

tick 순서: `begin_tick` -> `select_ack` -> `step` -> `to_px4_messages(out, builder, port.stamp())` -> 오류면 ERROR 로그 -> `offboard_control_mode`, `trajectory_setpoint`, 명령 순 발행 -> feedback -> 종료면 사건과 result. tick 번호는 goal이 없어도 하나씩 오른다. 구독 callback은 "다음 step의 tick 번호"와 노드 시계 ROS 시각을 표본에 적는다.

구독 QoS와 ack: PX4 토픽의 QoS는 `idsim_common::px4::px4_out_qos()`(BEST_EFFORT, VOLATILE, KEEP_LAST 5)로 고정이고 바꾸지 않는다(idsim_common이 qos_overrides도 끈다. PX4 writer가 BEST_EFFORT라 RELIABLE로는 붙지 않는다). ack는 PX4 쪽 큐가 4라 한 tick에 여럿 올 수 있으므로, 노드는 command 묶음(DO_SET_MODE, ARM_DISARM, NAV_LAND)별로 최신 ack 하나를 두고 tick마다 대기 중인 명령의 묶음 것만 Snapshot에 넣는다. 다른 묶음의 ack가 대기 중인 명령의 거부를 덮지 않는다. 같은 묶음 안에서 한 tick에 둘이 오면 나중 것이 남는다(거부가 ACCEPTED에 덮이면 타임아웃이 잡는다. 안전 방향).

feedback: phase나 항목이 바뀐 tick에는 바로, 그 밖에는 10 tick(0.5 s, 2 Hz)마다 낸다(`kFeedbackEveryTicks`).

## 구현 규칙

action 서버(P3d)
- `handle_goal`은 항상 `ACCEPT_AND_EXECUTE`다. 거절(REJECT)은 쓰지 않는다. 받을 수 없는 goal은 받아들인 뒤 즉시 ABORTED로 끝낸다.
- `handle_accepted`는 접수 사건을 낸 뒤 `screen_goal`(core)로 즉시 판정한다. 순서는 VEHICLE_ID_MISMATCH -> INVALID_MISSION -> BUSY다. 이 셋은 feedback 0건이다. PX4 상태에 달린 판정(수신, 식별 대조, EKF gate)은 즉시 하지 않고 PREPARING에서 `ready_timeout` 안에 기다린다(M1. NOT_READY 앞에 PHASE_PREPARING feedback이 나갈 수 있다).
- `handle_cancel`은 항상 받아들인다. 다음 tick부터 `TickInput.cancel_requested`를 true로 넘기고 분기는 core가 고른다.
- 종료는 `Termination` 하나로 정하고 action result(`to_result`)와 종료 사건(`to_terminal_event`)을 둘 다 그 객체에서 만든다. 사건의 `stamp`는 노드 시계의 ROS 시각이다.
- 이름 상수(`Mission::ACTION_NAME`, `MissionEvent::TOPIC_NAME`)는 상대 이름으로 쓰고 namespace 범위 static 초기화식에 쓰지 않는다.

상태기(core)
- 20 Hz tick마다 `step()` 한 번. goal 실행용 thread를 두지 않는다.
- 한 tick 안의 판정 순서: (1) 그 단계의 실패(감시 표, 상태 끊김, 거부 ack, 타임아웃 만료) (2) 확인과 완료(N회 연속, 도달, 경과) (3) 취소 (4) 출력 마무리. 같은 tick에 실패와 확인이 함께 정해지면 실패가 이긴다(decisions.md 쟁점 3 "종료의 충돌 규칙"을 전이에도 같게 쓴다).
- 시간 경계: 경과가 값 이상(`>=`)이면 만료다.
- `termination`은 정확히 한 번 나오고, 그 뒤의 step은 빈 출력이다(명령, setpoint, feedback, 종료 없음).
- "N회 연속"은 서로 다른 vehicle_status 표본 N개다. timestamp가 직전 표본보다 크지 않은 표본은 건너뛴다(`SampleCounter`).
- 대기 중인 명령은 한 번에 하나다. 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 지운다(그 tick에 이미 쌓인 재전송도 지운다). ack는 대기 중인 명령의 command 묶음이고 첫 전송 tick 뒤에 받은 것만 본다.
- 발행 규칙: P3-P6(Offboard로 들어가는 중)이 아니면 `nav_state`가 OFFBOARD일 때만 발행한다. OFFBOARD가 아닌 표본을 보면 멈추고 다시 켜지 않는다(`apply_publish_rule`). Hold와 AUTO_LAND의 처음 관측도 이 규칙으로 멈춘다.
- `Px4ClockPort`는 출력(setpoint나 명령)이 있는 tick에만 부른다. setpoint 항목 실행 중에는 감시 표 순위 1을 보려고 tick 머리에서 부른다.

## 전이 표와 구현의 대응

| decisions.md | 구현 |
| --- | --- |
| 쟁점 4 미션의 정적 검증, 1a 임시 제한 | `validate_mission_contract`, `validate_mission` |
| 쟁점 3 M1 즉시 판정 순서 | `screen_goal` |
| 쟁점 4 PREPARING P0-P2(TAKEOFF와 LAND 분기) | `MissionRunner::prepare_wait_ready` |
| P3 발행 시작과 목표점 | `start_signal` |
| P4, P5, P6 | `prepare_signal`, `prepare_offboard`, `prepare_arm` |
| 항목 표 TAKEOFF, LOITER와 비행 중 감시 표 | `step_setpoint_item`, `evaluate_monitor`(`core/rules.hpp`) |
| 항목 표 LAND와 LAND 감시 세 구간, 대비책 disarm | `step_land` |
| LAND 항목의 ITEM_TIMEOUT | `land_item_timeout` |
| 쟁점 3 M3-M5 취소, setpoint 항목의 ITEM_TIMEOUT, PREPARING 실패의 정리 | `begin_cleanup`, `step_cleanup`, `select_cleanup` |
| M4 Hold 분기와 Land 경로 | `enter_air`, `run_air`, `enter_air_land`, `run_air_land` |
| M5 지상 disarm 분기, C4 | `enter_ground`, `run_ground`, `DisarmConfirm` |
| disarm 분류의 고정 규칙 | `disarm_class_`(LAND, 정리), `DisarmClass` |
| 명령 재전송 규칙 | `send`, `resend_due`, `take_ack` |
| 쟁점 10 타임아웃 기본값 | `core/config.hpp`의 `Timeouts` |

## 재실측으로 바뀔 수 있는 곳

결과가 표와 다르면 아래 한 곳만 고친다. 고칠 때는 px4-engineer가 필수 승인자다.

| 항목 | 재실측 | 고칠 곳 |
| --- | --- | --- |
| 지상 setpoint 발행 중의 Hold(지상 분기 -> 공중 분기) | (2) | `MissionRunner::enter_air` |
| 이륙 직후 landed가 true인 구간의 지상 setpoint와 disarm | (3) | `MissionRunner::enter_ground`, `ground_setpoint` |
| 감시 표의 행 순위 | (4) | `core/rules.hpp`의 `kMonitorRankOrder` |
| "disarm 전송 뒤 받은 표본"의 기준 | (5) | `core/rules.cpp`의 `is_after_disarm_send` |
| 타임아웃 기본값과 재전송 주기 | - | `core/config.hpp`의 `Timeouts` |

## 표에 없어 구현에서 정한 것

px4-engineer 검토(2026-11-11, P3b 구현)에서 1-8, 10-12, 14-18은 승인, 9, 13, 19는 수정 조건부였고 그 수정을 반영했다(아래 문장). 근거가 바뀌면 표에 올리고 이 절을 지운다.

1. 시간 경계와 같은 tick의 순서: 만료는 `>=`이고, 같은 tick에 만료(실패)와 확인이 함께 정해지면 만료가 이긴다. 전이(P5 확인 대 `mode_confirm_timeout` 등)에도, 정리 분기의 확인(Hold, disarm) 대 타임아웃에도 같다. 그래서 정확히 타임아웃 tick에 3번째 확인 표본이 오면 실패다.
2. setpoint 항목에서 감시 표 행과 ITEM_TIMEOUT이 같은 tick이면 감시 표 행이 이긴다(감시 표를 먼저 본다). ITEM_TIMEOUT은 정리가 필요한 ABORTED 사유이고 감시 표 행은 정리 없이 끝낸다.
3. LAND 항목의 확인 전 구간에서는 `mode_confirm_timeout`이 지상 DISARMED 계수 중에도 흐른다. 같은 tick이면 MODE_SWITCH_FAILED가 ITEM_TIMEOUT보다 먼저다(`[LAND]` 단독 미션 단서의 "timeout이 `mode_confirm_timeout`보다 짧을 때뿐"과 맞춘다).
4. P0의 "vehicle_status가 신선"은 마지막 수신이 `link_timeout`(2 s) 안이다.
5. P1(시작 조건)은 P0을 통과한 tick마다 P2를 기다리는 동안 다시 본다. 기다리는 중에 누가 arm하면 PRECONDITION_FAILED다.
6. P3은 위치 값(x, y, z와 MODE_KEEP이면 heading)이 유한할 때까지 기다린다(`ready_timeout` 안). `xy_valid`는 gate로 쓰지 않는다는 결정은 그대로다.
7. P4의 신호 확인은 발행 시작 tick 뒤에 받은 failsafe_flags만 쓴다(그 전의 flags는 앞 미션의 값일 수 있다).
8. P6의 "ARMED 3회 연속이고 여전히 OFFBOARD"는 ARMED이고 OFFBOARD인 표본을 센다.
9. PREPARING 중 발행을 시작한 뒤(P3-P6)의 식별 불일치는 NOT_READY로 끝내고 정리 분기를 고르지 않는다(감시 표 순위 2처럼 입력을 믿지 않는다). 이 goal에서 arm을 보냈으면 강제가 아닌 disarm을 한 번 보내고 `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground"를 적는다. vehicle_command는 target_system으로 주소가 정해져 status의 식별과 무관하고, 강제가 아닌 disarm은 공중에서 거부되며, 이륙 이력이 없으면 자동 disarm이 없다(`COM_DISARM_PRFLT=-1`). PREPARING 중에는 LINK_LOST 판정을 두지 않고 각 단계의 타임아웃이 잡는다.
10. 정리 분기(취소, ITEM_TIMEOUT, PREPARING 실패)는 Executor가 발행이나 명령을 한 번이라도 한 뒤에만 의미가 있다. P0-P2에서 끝나는 NOT_READY와 PRECONDITION_FAILED는 정리 없이 끝난다. 아무것도 하지 않은 상태의 취소는 표본이 없거나 끊겼으면 바로 CANCELED이고, 표본이 있으면 표대로 고른다. 예: `[LAND]` 미션의 P2 대기 중 취소는 공중이면 Hold를 보낸다. TAKEOFF 미션이 P0에서 다른 토픽을 기다리는 중이라 P1 재확인이 아직 걸리지 않았는데 외부에서 arm된 지상 기체를 취소가 만나면, 지상 분기가 그 기체를 disarm한다. 표(M3)대로이고 강제가 아닌 disarm이라 위험은 낮다.
11. 거부 ack의 정의: ACCEPTED와 IN_PROGRESS가 아니면 거부다. DO_SET_MODE(Offboard)의 "ACCEPTED가 아니면 MODE_SWITCH_FAILED"도 IN_PROGRESS는 거부로 보지 않는다.
12. Hold와 Offboard는 같은 DO_SET_MODE라 ack로 가를 수 없다. 대기 중인 명령이 하나라는 규칙에 기대어 그 명령의 ack로 본다. Offboard의 늦은 거부 ack가 Hold 대기 중에 오면 Hold 거부로 읽힌다.
13. 정리 중(취소, ITEM_TIMEOUT, PREPARING 실패)에 식별이 어긋난 vehicle_status 표본은 발행 규칙, 분기 고르기, 확인 계수(disarm, Hold, AUTO_LAND)에 쓰지 않는다. 같은 네임스페이스의 다른 발행자의 DISARMED나 Hold로 정리를 끝내면 우리 기체가 arm으로 남을 수 있기 때문이다. 이미 정해진 분기는 유지하고 그 분기의 타임아웃(`hold_confirm_timeout`, `mode_confirm_timeout`)이 끝낸다. 분기가 정해지기 전(정리의 첫 tick)이면 끝낸다: 취소는 ABORTED, INTERNAL, 그 밖은 원래 reason이고 arm을 보냈으면 9와 같이 disarm을 한 번 보낸다. 정리를 시작하는 tick의 표본은 그 단계가 이미 식별을 보므로 이 첫 tick 경로는 방어용이다(`cleanup_with_untrusted_sample`).
14. LAND 항목의 대비책 disarm은 AUTO_LAND 확인 뒤에만 보낸다(대기 중인 명령은 하나라 NAV_LAND 재전송과 겹치지 않게). 지연 시간은 landed이고 ARMED인 최신 값을 처음 본 tick부터 재고, 둘 중 하나가 깨지면 처음부터 다시 잰다.
15. disarm 분류(지상 대 공중)는 처음 관측한 DISARMED 표본에서 정하고, ARMED 표본을 보면 미정으로 되돌린다. LAND 항목에서 정한 분류는 취소의 정리로 이어진다.
16. 지상 disarm 분기의 LINK_LOST에서 "disarm을 한 번 더 보낸다"는 그 tick의 분기 고르기가 지상일 때다.
17. ITEM_TIMEOUT과 PREPARING 실패의 정리 중 feedback phase는 실패한 단계의 phase(EXECUTING, WAITING_MODE, PREPARING)를 유지한다. PHASE_CANCELING은 취소일 때만이다.
18. 지상 setpoint의 위치가 유한하지 않으면 P3에서 읽은 위치를 쓰고, heading이 유한하지 않으면 그때의 setpoint yaw를 쓴다.
19. `Px4Timestamp` 공급이 실패한 tick: 출력을 모두 버리고 ABORTED로 끝낸다. reason은 정리 중(ITEM_TIMEOUT, PREPARING 실패)이면 원래 것, 그 밖은 INTERNAL이다. 발행이나 명령을 한 번이라도 했으면 `detail`에 "vehicle state unknown, may remain armed on ground"를 더한다. 끝나는 tick에 보내려던 마지막 disarm은 버리고 결과는 유지한다.

## 테스트

`test/`의 core 단위 테스트는 gtest와 core만 링크한다(노드와 DDS 참가자를 만들지 않는다). `test/px4/`는 어댑터(px4-engineer), `test/node/`는 노드 껍질 테스트다.

| 파일 | 내용 |
| --- | --- |
| `runner_harness.hpp` | tick 열 헬퍼(20 Hz 흉내, 합성 timestamp, 가짜 PX4 반응, `feed`로 표본 열 주입, 종료 불변식: 정확히 1건, result == 종료 사건, 종료 뒤 빈 출력) |
| `test_mission_validation.cpp` | 검증 규칙, 1a 제한, `TYPE_*` 분류 전수, `screen_goal` 순서 |
| `test_termination.cpp` | status와 reason 전수 대응표, reason 값, 종료 결과 == 종료 사건 |
| `test_monitor_table.cpp` | 감시 표 순위마다 한 건, 같은 tick 동률 24쌍, 순위 5의 가지, 행 수와 parametrize 수 |
| `test_confirm_rules.cpp` | N회 연속 계수, 전송 뒤 표본 기준, 늦은 arm 경합, 정리 분기 고르기(snapshot 5종), yaw 변환 |
| `test_runner_preparing.cpp` | P0-P6, `[LAND]` 미션, PREPARING 실패의 정리 |
| `test_runner_items.cpp` | TAKEOFF, LOITER, 상태기 안의 감시 표(순위마다), 엇갈림, 이력의 항목 경계, 분류 고정 |
| `test_runner_land.cpp` | LAND 세 구간, 완료 우선, 대비책 disarm, LAND의 ITEM_TIMEOUT 변형 |
| `test_runner_cleanup.cpp` | 취소 분기, Hold와 Land 경로, 지상 disarm 확인과 C4, ITEM_TIMEOUT 정리, 원인 3 x snapshot 3 교차표, 정리 중 식별 불일치 |
| `test_runner_conflicts.cpp` | 종료의 충돌 규칙(C5), `Px4Timestamp` 공급 실패 |
| `node/test_contract_constants.cpp` | core 값과 메시지 상수(REASON_* 13, 14 포함, TYPE_*, MODE_*, PHASE_*, STATUS_*), yaw 식과 idsim_common/frames, 변환의 result == 사건 |
| `node/test_executor_node.cpp` | 한 프로세스 배선(노드, 가짜 PX4, /clock thread, action client): self_start 대조군 쌍, 직접 configure/activate, configure 실패 둘, 정상 경로 SUCCEEDED와 무효 경로 INVALID_MISSION(사건 ACCEPTED가 앞, 종료 사건 1건, result와 같은 값), goal 중 deactivate 거부와 on_shutdown의 ABORTED INTERNAL, cancel을 받아들인 goal의 abort 허용(rclcpp_action) |

PX4 v1.17.0에서 나오지 않는 방어 경로(OFFBOARD이고 ARMED인 채 failsafe, 순위 5의 이력, 순위 8, DISARM과 ARM의 그 밖의 거부 ack)는 합성 표본과 합성 ack로만 시험하고 테스트 주석에 그렇게 적었다. 단위 테스트는 합성 timestamp만 검사한다. 실제 시계 관계는 재실측 (5)만 확인한다.
