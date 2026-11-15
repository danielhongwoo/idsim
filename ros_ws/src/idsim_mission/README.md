# idsim_mission

기체 하나의 Mission Executor. `ExecuteMission` action 서버(`/<vehicle_id>/execute_mission`)로 미션을 받아 PX4 Offboard로 실행하고, goal마다 접수와 종료 사건(`mission_event`)을 낸다. 계약은 `docs/interface.md`, 1b 계약은 `docs-for-agent/plan-1b-mission-target/decisions.md`다. 이 문서는 구현 규칙과 경계를 적는 설계 노트다.

## 구성

| 대상 | 내용 | 의존 | 소유 | 단계 |
| --- | --- | --- | --- | --- |
| `idsim_mission_core` | 미션 검증, `TYPE_*` 분류, 상태기(`MissionRunner`), 종료 결과, 전이 관측(`core/transition.hpp`) | 없음(C++17 표준 라이브러리만) | ros2-engineer. `core/snapshot.hpp`, 상태기 전이 표, `Event` 목록과 칸 목록(`test/transition_cells.tsv`)은 px4-engineer 필수 승인 | P3b, P4 |
| `idsim_mission_px4` | px4_msgs -> snapshot 변환, 명령 목록 -> `VehicleCommand`와 setpoint | core, `idsim_common`, px4_msgs | px4-engineer(`include/idsim_mission/px4/`, `src/px4/`, `test/px4/`) | P3c |
| `mission_executor_component` | lifecycle 노드 껍질 `idsim_mission::MissionExecutorNode`(컴포넌트), action 서버, 사건 발행, 계약 메시지 변환(`node/conversion.hpp`) | core, px4 어댑터, idsim_interfaces, rclcpp_lifecycle, rclcpp_action, rclcpp_components | ros2-engineer | P3d |

- `idsim_mission_core`는 어떤 ROS 패키지도 링크하지 않는다(CMake 대상에 링크가 없다). 단위 테스트는 gtest와 core만 링크한다. ctest의 `core_purity`가 core 소스에 `clock::now`, `clock_gettime`, `gettimeofday`, `std::time`, `this_thread`, `getenv`, `rclcpp`, `px4_msgs`, `idsim_common`, `idsim_interfaces`, `builtin_interfaces` 문자열이 없는지 본다(주석 줄 제외). `core_purity_negative`는 금지 문자열을 심은 임시 파일로 검사기 자체가 그 수만큼 잡는지 본다.
- core는 `idsim_interfaces`의 메시지를 쓰지 않고 같은 값을 다시 적는다(`core/types.hpp`의 `Reason`, `item_type`, `FeedbackPhase`, `core/termination.hpp`의 `event_status`). 값이 메시지 상수와 같은지는 `test/node/test_contract_constants.cpp`가 교차 검사한다(13, 14 포함). core의 `enu_to_ned_yaw`, `wrap_pi`가 `idsim_common/frames`와 같은 값인지도 같은 파일이 본다.

## core와 어댑터의 경계

경계는 `include/idsim_mission/core/snapshot.hpp` 하나다. 필드 목록과 px4_msgs 필드와의 대응표("어댑터가 채울 것", "출력에 할 것")는 그 헤더 머리 주석이 정본이고, 어댑터(`px4/`의 `inputs`, `outputs`, `frame_port`, `clock_port`)는 그 표대로 채운다. 여기에는 구조만 적는다.

- 입력: tick 번호, 그 tick의 ROS 시각, `Snapshot`(PX4 토픽마다 최신 표본 하나와 target_id별 최신 유효 표적 표본), `Px4ClockPort`(실패할 수 있는 `Px4Timestamp` 공급), `FramePort`(world ENU -> 기체 로컬 NED 변환. 그 tick의 `Snapshot.position`과 같은 표본의 기준으로 만든다. `step()`의 넷째 인자이고 GOTO와 TRACK_ENTITY 항목만 부른다. 점 변환과 벡터 변환 모두 결과가 float32에 실을 수 없으면 값 없음이다). core는 벽시계와 rclcpp를 부르지 않고 `idsim_common`과 px4_msgs를 모른다(decisions.md 쟁점 6 C1, 쟁점 4).
  - `received_tick`은 "그 표본을 처음 볼 수 있는 step의 tick 번호"다. 그래서 step k에서 낸 명령의 응답은 `received_tick > k`다.
- 출력(`StepOutput`): `px4_timestamp_us`(이 tick의 명령과 setpoint에 실을 값), `setpoint`(있으면 이 tick에 `offboard_control_mode`(position만)와 `trajectory_setpoint`를 발행. 속도는 `velocity_valid`일 때만 싣는다), `commands`(`CommandKind` 목록. 재전송도 여기에 나온다), `feedback`, `termination`.
  - 노드는 `Px4ClockPort::now_us`가 그 tick에 만든 `Px4Timestamp` 객체를 보관해 두고 그 객체로 명령과 setpoint를 만든다(`Px4Timestamp`는 시계에서만 만들 수 있다).

## 노드 껍질(P3d)

실행: `ros2 launch idsim_mission vehicle_ops.launch.py namespace:=/px4_N executor_name:=<이름> params_file:=<파일>`. launch는 `component_container_isolated`(이름 `ops_container`)에 컴포넌트 하나를 load하고(`ComposableNode`, autostart 없음), `output='screen'`, 컨테이너에 `on_exit=Shutdown()`을 건다. 세 인자 모두 기본값이 없다. params 파일은 생성기가 만든다(`/**` 아래 일곱: `use_sim_time`, `vehicle.id`, `vehicle.ns`, `vehicle.sysid`, `world.origin.lat`, `world.origin.lon`, `world.origin.alt`. 원점은 WGS84 도와 타원체 고 m의 double).

파라미터(모두 읽기 전용, 생성기는 만들지 않는다): `lifecycle.self_start`(bool, 기본 true), `command_source.system`(254), `command_source.component`(191), timeout 열(`ready_timeout`, `offboard_signal_timeout`, `mode_confirm_timeout`, `arm_timeout`, `hold_confirm_timeout`, `link_timeout`, `land_disarm_fallback_delay`, `command_resend_period`, `target_timeout`, `target_fresh_age`. 초 단위 double, 기본값은 `core/config.hpp`).

lifecycle
- 생성자: `vehicle.*`를 한 번 선언하고 해석한다(실패는 configure에서 드러난다). `lifecycle.self_start`가 true이면 벽시계 0 ms 일회 timer를 만들고, 그 callback의 첫 줄에서 timer를 취소한 뒤 `configure()`와 `activate()`를 한 번씩 부른다. 실패하면 그 상태에 남고 `IDSIM_EXECUTOR_START_FAILED: <전이> failed, state <상태>: <이유>` 한 줄을 ERROR로 남긴다(`kStartFailedLogPrefix`). 프로세스는 끝내지 않는다.
- on_configure: `link_timeout`이 `mode_confirm_timeout`보다 짧지 않으면 WARN(지상 disarm 분기의 상태 끊김 규칙의 전제. decisions.md 쟁점 3 M5). 정리의 상한(`core::cleanup_cap_ns`, 노드 파라미터가 아니다)의 계산값을 INFO로 남긴다. `vehicle.*` 해석 실패, `use_sim_time` false, `world.origin.*` 누락이나 타입 불일치, 비유한, 범위 밖(위도 -90-90, 경도 -180-180), 노드 네임스페이스와 `vehicle.ns` 불일치, timeout 0 이하, `target_fresh_age` >= `target_timeout`, command source 무효나 source == sysid이면 FAILURE. 구독 다섯, PX4 발행자 셋, 사건 발행자, `RosPx4ClockPort`를 만든다.
- on_activate: 첫 `/clock`을 벽시계 2 s 기다리고(`wait_until_started`. 파라미터가 아니다) `Px4Timestamp::now`가 되는지 본 뒤 발행자를 켜고, 20 Hz tick timer(노드 시계)와 action 서버를 만든다.
- on_deactivate: goal 실행 중이면 FAILURE(active에 남는다). 아니면 action 서버와 timer를 없앤다.
- on_shutdown, on_error, context 종료 직전(pre-shutdown callback): 실행 중인 goal을 ABORTED, REASON_INTERNAL로 끝내고 종료 사건을 낸다. 이 goal에서 arm을 보냈으면 새 `Px4Timestamp`로 강제가 아닌 disarm을 한 번 발행하고 `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground"를, 발행할 수 없으면(발행자 비활성, 시간 공급 실패) "disarm could not be sent, vehicle state unknown"을 더한다(지상 arm 뒤 이륙 전이면 자동 disarm이 없다. `COM_DISARM_PRFLT=-1`). on_error는 on_cleanup처럼 구독과 발행자를 비워 다음 configure가 새로 만들게 하고, 남은 action 서버는 다음 on_activate가 새 서버를 만들기 전에 지운다. on_shutdown 뒤에도 action 서버는 소멸자까지 남는다(끝낸 goal의 result 요청에 답해야 한다). 그 뒤에 온 goal은 `handle_accepted`가 즉시 ABORTED, REASON_INTERNAL("executor is not active")로 끝낸다.
- callback group은 MutuallyExclusive 하나(PX4 구독, tick timer, action 서버). pre-shutdown callback은 다른 thread에서 돌 수 있어 goal 상태와 snapshot은 mutex로 지킨다.

tick 순서: `begin_tick` -> `select_ack` -> `step`(FramePort는 params `world.origin`과 그 tick의 기준으로 만든 `px4::Px4FramePort`. 기준은 `vehicle_local_position` callback에서 `to_local_position_input`으로 `Snapshot.position`과 같은 표본에서 만든다. `ref_timestamp`가 바뀐 표본을 landed false인 동안 받으면 WARN 한 줄) -> `to_px4_messages(out, builder, port.stamp())` -> 오류면 ERROR 로그 -> `offboard_control_mode`, `trajectory_setpoint`, 명령 순 발행 -> feedback -> 종료면 사건과 result. tick 번호는 goal이 없어도 하나씩 오른다. 구독 callback은 "다음 step의 tick 번호"와 노드 시계 ROS 시각을 표본에 적는다.

표적 구독: goal을 실행하기로 정한 뒤(`screen_goal` 통과) `Snapshot.targets`만 비우고(PX4 표본은 그대로), 미션의 TRACK_ENTITY `target_id`마다 `/targets/<id>/state`(`idsim_common::target_state_topic`, `state_sub_qos`) 구독을 하나씩 만든다. goal이 끝나면(종료, 중단, 오류) 구독을 지운다. callback은 `to_target_sample`(`node/conversion.cpp`. 유효 표본 규칙과 `core::within_coordinate_bound`)로 거르고, 거른 표본은 버리고 WARN을 1 s throttle로 남긴다.

CLI: `ros2 run idsim_mission send_mission <file> --vehicle <vehicle_id>`. 미션 YAML을 `idsim_mission.mission_yaml`로 읽어 goal을 보내고 feedback과 result를 출력한다(형식은 모듈 docstring). 로더는 구조 검사(중복 key와 merge key 거부 포함. YAML 문법 오류도 로더 오류, 종료 코드 2), 단위 변환, 기본값(yaw는 `yaw_rad`가 없으면 MODE_KEEP. 허용 오차는 필수), `mission_id`(없으면 파일 이름)만 하고 계약 검증은 Executor가 한다.

구독 QoS와 ack: PX4 토픽의 QoS는 `idsim_common::px4::px4_out_qos()`(BEST_EFFORT, VOLATILE, KEEP_LAST 5)로 고정이고 바꾸지 않는다(idsim_common이 qos_overrides도 끈다. PX4 writer가 BEST_EFFORT라 RELIABLE로는 붙지 않는다). ack는 PX4 쪽 큐가 4라 한 tick에 여럿 올 수 있으므로, 노드는 command 묶음(DO_SET_MODE, ARM_DISARM, NAV_LAND, NAV_RTL, 그 밖)별로 최신 ack 하나를 두고 tick마다 대기 중인 명령의 묶음 것만 Snapshot에 넣는다. 다른 묶음의 ack가 대기 중인 명령의 거부를 덮지 않는다. 같은 묶음 안에서 한 tick에 둘이 오면 나중 것이 남는다(거부가 ACCEPTED에 덮이면 타임아웃이 잡는다. 안전 방향).

feedback: phase나 항목이 바뀐 tick과 항목이 완료된 tick(`items_completed`가 바뀐 tick. 마지막 setpoint 항목이 완료되어 공중 종료 단계로 들어가는 tick 포함)에는 바로, 그 밖에는 10 tick(0.5 s, 2 Hz)마다 낸다(`kFeedbackEveryTicks`). stamp는 `Feedback.stamp_ns`, 곧 그 tick의 `TickInput.now_ns`다. 노드는 tick 시각을 tick 머리에서 한 번만 읽고, core가 경과 시간을 재는 시각과 stamp가 같은 값이 된다(발행 때 다시 읽으면 `/clock` 한 양자만큼 어긋날 수 있다). `Px4ClockPort`의 `Px4Timestamp`는 따로 읽는 값이라 이 시각과 다를 수 있다.

## 구현 규칙

action 서버(P3d)
- `handle_goal`은 항상 `ACCEPT_AND_EXECUTE`다. 거절(REJECT)은 쓰지 않는다. 받을 수 없는 goal은 받아들인 뒤 즉시 ABORTED로 끝낸다.
- `handle_accepted`는 접수 사건을 낸 뒤 `screen_goal`(core)로 즉시 판정한다. 순서는 VEHICLE_ID_MISMATCH -> INVALID_MISSION -> BUSY다. 이 셋은 feedback 0건이다. PX4 상태에 달린 판정(수신, 식별 대조, EKF gate)은 즉시 하지 않고 PREPARING에서 `ready_timeout` 안에 기다린다(M1. NOT_READY 앞에 PHASE_PREPARING feedback이 나갈 수 있다).
- `handle_cancel`은 항상 받아들인다. 다음 tick부터 `TickInput.cancel_requested`를 true로 넘기고 분기는 core가 고른다.
- 종료는 `Termination` 하나로 정하고 action result(`to_result`)와 종료 사건(`to_terminal_event`)을 둘 다 그 객체에서 만든다. 사건의 `stamp`는 노드 시계의 ROS 시각이다. tick에서 정한 종료의 사건은 그 tick의 입력 시각을, `handle_accepted`의 접수 사건과 즉시 종료 사건은 그 callback에서 한 번 읽은 시각(runner의 시작 시각과 같은 값)을, 실행 중 goal의 강제 종료(on_shutdown, on_error, pre-shutdown)는 종료할 때 읽은 시각을 쓴다.
- 이름 상수(`Mission::ACTION_NAME`, `MissionEvent::TOPIC_NAME`)는 상대 이름으로 쓰고 namespace 범위 static 초기화식에 쓰지 않는다.

상태기(core)
- 20 Hz tick마다 `step()` 한 번. goal 실행용 thread를 두지 않는다.
- 한 tick 안의 판정 순서: (1) 그 단계의 실패(감시 표, 상태 끊김, 거부 ack, 타임아웃 만료) (2) 확인과 완료(N회 연속, 도달, 경과) (3) 취소 (4) 출력 마무리. 같은 tick에 실패와 확인이 함께 정해지면 실패가 이긴다(decisions.md 쟁점 3 "종료의 충돌 규칙"을 전이에도 같게 쓴다). P6에서 첫 ARMED 표본을 본 뒤에는 감시 표 -> 확인 기한 -> 확인 -> 취소다.
- 정리 중 한 tick의 순서(decisions.md 쟁점 3 M6): (1) 상태 끊김 (2) 공중 DISARMED (3) 정리할 것 없음 (4) 정리의 상한(정리 시작 tick부터 `max(hold_confirm_timeout + 3 x mode_confirm_timeout, hold_confirm_timeout + land_disarm_fallback_delay + mode_confirm_timeout)`, 기본 12 s. 뒤 항은 종료 단계의 지상 대기에 대비책 지연이 붙는 경로다) (5) 그 분기의 실행. 상한 tick에는 발행을 멈추고 대기 명령을 지운 뒤 지상이면 disarm, 공중이면 NAV_LAND를 한 번 보내고 끝낸다. 식별이 어긋난 표본의 tick이면 직전 분기로 정한다.
- 공중 종료 단계(1b decisions.md 쟁점 10. 마지막 항목이 setpoint 항목인 미션): 마지막 항목의 완료 tick에 `items_completed`를 N으로 올리고 정리 원인 `kMissionEnd`로 들어간다. 첫 tick은 늘 Hold(AIR)이고, Hold가 실패하면 그 tick의 최신 landed로 Land 경로(AIR_LAND)나 지상 대기(GROUND_WAIT)로 간다. 한 tick의 순서: (1) 표본 없음(방어) (2) 식별 불일치(분기가 있으면 표본 없이 이어 가고 상태 끊김을 보지 않는다) (3) 표본 반영(발행 규칙, disarm 분류, Hold 관측, 두 계수, 지상 대기의 대비책 이어짐) (4) 상태 끊김 (5) 공중 DISARMED (6) 정리의 상한 (6a) disarm 분류가 지상이면 지상 DISARMED 3회만 보고 끝(분류 지상 규칙. 첫 지상 DISARMED tick에 대기 명령을 지우고 그 동안의 ack는 버린다) (7) 분기의 거부 ack, 기한, 이동, AUTO_LAND 관측 (8) Hold 3회 (9) 지상 대기의 대비책 disarm (10) 재전송. 표본은 감시 표와 같은 신뢰 표본 규칙(`monitored_status`)이다. 지상 DISARMED 계수는 단계 전체에 하나이고(대비책 전 `SampleCounter`, 뒤 `DisarmConfirm`) 3회면 SUCCEEDED(`ended on ground`)다. 같은 tick의 `hold_confirm_timeout`과 Hold 3회째, 정리의 상한과 모든 확인은 만료가 이긴다. 취소는 결과를 바꾸지 않는다.
- 비행 중 감시 표로 끝낼 때는 정리 분기에 들어가지 않는다. 순위 2는 arm을 보냈으면, 순위 3, 6, 7, 8은 arm을 보냈고 첫 ARMED 표본 뒤 landed false를 본 적이 없고 그 tick의 landed가 true이면 강제가 아닌 disarm을 한 번 보낸다(`monitor_sends_disarm`). P6과 setpoint 항목이 같은 종료 함수(`end_by_monitor`)를 쓴다.
- 시간 경계: 경과가 값 이상(`>=`)이면 만료다.
- 전이 관측(`docs-for-agent/plan-1b-mission-target/decisions.md` 쟁점 13): 전이를 일으키는 함수(`terminate`, `begin_cleanup`, `start_signal`, `enter_prep`, `start_item`, `complete_item`, `enter_ground`, `enter_air`, `enter_air_land`, `mission_end_hold_failed`, `mission_end_enter_air_land`, `mission_end_enter_ground_wait`, `finish`)는 첫 인자로 사건 꼬리표 `Event`를 받는다. 상태 key 성분(`stage_`, `prep_`, `item_index_`, `cause_`, `branch_`)은 `set_state` 한 곳에서만 쓴다. 생성자의 `TransitionObserver`(기본 nullptr. 노드는 넘기지 않는다)가 있으면 tick마다 (from, 사건, to, reason, 함께 참이던 사건) 기록을 넘긴다. 꼬리표 하나는 상태 key를 한 번까지만 바꾼다. 꼬리표 없이 상태 key가 바뀌거나 한 꼬리표의 기록이 열린 동안 두 번째로 바뀌면 그 변경은 untagged 기록이 되고, 앞 기록은 그 변경 직전의 상태 key로 닫는다(같은 값 쓰기는 세지 않는다). 겹침을 실으려고 setpoint 항목은 감시 표, ITEM_TIMEOUT, 완료의 조건을 먼저 계산해 둔다(상태를 바꾸지 않는 식이고 고르는 순서는 그대로다). `evaluate_monitor`는 맞는 행 전부를 `matched`에 함께 싣는다(고르는 행은 그대로 첫 행이다). observer가 없으면 기록을 만들지 않고 출력은 같다.
- `termination`은 정확히 한 번 나오고, 그 뒤의 step은 빈 출력이다(명령, setpoint, feedback, 종료 없음).
- "N회 연속"은 서로 다른 vehicle_status 표본 N개다. timestamp가 직전 표본보다 크지 않은 표본은 건너뛴다(`SampleCounter`).
- 대기 중인 명령은 한 번에 하나다. 분기나 단계가 바뀌는 tick에 이전 명령의 재전송을 지운다(그 tick에 이미 쌓인 재전송도 지운다). ack는 대기 중인 명령의 command 묶음이고 첫 전송 tick 뒤에 받은 것만 본다. 지상 arm 진입의 arm 조건은 그보다 좁다: 마지막 DO_SET_MODE 전송(재전송 포함) tick보다 뒤의 tick에 받은 비거부 ack다(같은 tick에 받은 ack는 그 tick의 전송보다 앞이다).
- 발행 규칙: P3-P6(Offboard로 들어가는 중)이 아니면 `nav_state`가 OFFBOARD일 때만 발행한다. OFFBOARD가 아닌 표본을 보면 멈추고 다시 켜지 않는다(`apply_publish_rule`). Hold와 AUTO_LAND의 처음 관측도 이 규칙으로 멈춘다.
- `Px4ClockPort`는 출력(setpoint나 명령)이 있는 tick에만 부른다. P6에서 첫 ARMED 표본을 본 뒤와 setpoint 항목 실행 중에는 감시 표 순위 1을 보려고 판정 맨 앞에서 부른다.

## 전이 표와 구현의 대응

| decisions.md | 구현 |
| --- | --- |
| 쟁점 4 미션의 정적 검증과 1b 쟁점 6의 순서 규칙 | `validate_mission_contract`(goal 접수의 `screen_goal`과 runner 생성자가 부른다) |
| 받는 미션(type 여섯, 길이 4 이하의 1554개 순서): goal 접수와 runner 모두 계약 valid 미션 이백예순여섯(TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만). 계약 검증에는 좌표 상한(GOTO `position`과 TRACK_ENTITY `offset`의 각 성분 절댓값 `kMaxContractCoordinateM` 1e5 m 이하, 1b 쟁점 8)과 `target_id` 형식(`^[a-z][a-z0-9_]{0,31}$`, `is_valid_target_id`)이 든다. 같은 상한 술어 `within_coordinate_bound`를 노드의 표적 표본 변환이 쓴다 | `screen_goal`, `MissionRunner` 생성자의 `validate_mission_contract` |
| 쟁점 3 M1 즉시 판정 순서 | `screen_goal` |
| 쟁점 4 PREPARING P0-P2, 진입 방식(1b 쟁점 12 `EntryPlan`: TAKEOFF는 지상 arm, LAND와 RTL은 모드 명령, LOITER, GOTO, TRACK_ENTITY는 공중 Offboard) | `MissionRunner::prepare_wait_ready`, `entry_plan`(`core/rules.hpp`) |
| P3 발행 시작과 목표점 | `start_signal` |
| P4, P5 | `prepare_signal`, `prepare_offboard` |
| P5 안의 ack 대기(1b decisions.md 쟁점 12. 상태 key `PREPARING.OFFBOARD_ACK`. 확인 고정, P5부터 arm 전까지 유효 ack가 없는 동안만 DO_SET_MODE 재전송(확인 tick 포함), 마지막 전송 뒤의 비거부 ack로 arm, 거부 ack, timeout, 이탈) | `prepare_offboard_ack`, `arm_if_offboard_acked`, `Pending.last_send_tick`(`send`, `resend_due`), `Pending.accepted_ack_tick`(`take_ack`), `has_valid_offboard_ack`, `resend_offboard_until_acked` |
| P6(첫 ARMED 표본 전과 뒤, arm 재전송 중단, 확인 기한) | `prepare_arm`, `prepare_arm_before_armed` |
| 1b 쟁점 7 공중 Offboard 진입(첫 항목 LOITER, GOTO, TRACK_ENTITY). P1(ARMED, 공중, `nav_state`와 의도 AUTO_LOITER, failsafe 없음)과 P2(EKF gate, 위치와 heading 유한)는 `prepare_wait_ready`. P3 진입 setpoint(그 tick의 위치와 heading, OFFBOARD 3회 확인까지 유지. 첫 항목 LOITER는 그대로 쓰고 첫 항목 GOTO와 TRACK_ENTITY는 항목 시작 tick에 그 점으로 바꾼다)와 감시 시작(감시 표본의 하한, 신뢰 표본, 이력 구간을 P3 tick 표본으로) | `start_air_signal` |
| 공중 Offboard 진입의 P4(상태 key `PREPARING.AIR_SIGNAL`. 감시 표(AUTO_LOITER 면제), DO_SET_MODE 전에 본 OFFBOARD, 신호 기한, 신호 확인) | `prepare_air_signal` |
| 공중 Offboard 진입의 P5(상태 key `PREPARING.AIR_OFFBOARD`는 첫 OFFBOARD 표본 전: 감시 표(AUTO_LOITER 면제), 거부 ack, 첫 OFFBOARD 표본, 기한, 주기 재전송. `PREPARING.AIR_OFFBOARD_SEEN`은 그 뒤: 감시 표(면제 없음), 기한, OFFBOARD 3회로 첫 항목 시작). 재전송은 수락 ack가 아니라 첫 OFFBOARD 표본에서 멈춘다. 호출 순서는 감시 표, 거부 ack, 대기 명령 지우기다 | `prepare_air_offboard`, `prepare_air_offboard_seen`, `air_offboard_seen_checks` |
| 감시 구간의 시작 표시(지상 arm 진입은 P6의 첫 ARMED 표본, 공중 Offboard 진입은 P3 tick). 발행 뒤 준비 단계의 식별 검사와 첫 항목의 이력 지우기가 이것으로 가른다 | `monitor_active_`(`step_preparing`, `start_item`) |
| 감시 표의 AUTO_LOITER 면제(순위 7, 8만, 공중 Offboard 진입의 첫 OFFBOARD 표본 전) | `MonitorInput::hold_exempt`(`core/rules.hpp`), `monitor_flight`의 `hold_exempt` 인자 |
| 항목 표 TAKEOFF, LOITER | `step_setpoint_item` |
| 1b 쟁점 8 GOTO 결정 표(상태 key `ITEM.GOTO`, 완료 사건 `GOTO_REACHED`). 항목 시작 tick의 yaw 고정(MODE_KEEP은 직전 setpoint의 yaw)과 점 변환, 매 tick 점 변환(감시 표 앞), 서로 다른 위치 표본 3개 연속 반경 안의 완료(`xy_valid`, `z_valid`, 유한, 3차원 거리 엄격 부등호), 변환 값 없음의 setpoint 유지와 계수 지우기, ITEM_TIMEOUT detail의 "no frame transform since item start", feedback 거리. 순서는 감시 표 -> ITEM_TIMEOUT -> 완료 -> 취소다 | `start_item`, `goto_transform`, `step_setpoint_item`, `make_feedback`, `goto_counter_`, `goto_transformed_` |
| 1b 쟁점 8 TRACK_ENTITY 결정 표(상태 key `ITEM.TRACK_ENTITY`, 완료 사건 `TRACK_ENTITY_REACHED`, 실패 사건 `TARGET_LOST`). 표적 판정(이 goal의 최신 유효 표본, 나이는 음수이면 0, `target_fresh_age` 이하이면 신선, 표본이 없으면 항목 시작부터 있으면 stamp부터 `target_timeout` 초과가 소실), 표적 위치 + `offset`의 점 변환과 신선하고 속도가 유효할 때의 벡터 변환(세 성분을 통째로 싣거나 뺀다), 표본이 없거나 점 변환 값이 없는 tick의 위치와 yaw 유지, 신선하지 않은 tick의 완료 계수 지우기, 속도는 끝 상태가 `ITEM.TRACK_ENTITY`인 tick에만(항목 완료와 정리 진입이 지운다), TARGET_LOST의 detail 두 원인과 ITEM_TIMEOUT의 "no frame transform since item start". 순서는 감시 표 -> TARGET_LOST -> ITEM_TIMEOUT -> 완료 -> 취소다 | `start_item`, `track_target`, `track_transform`, `step_setpoint_item`, `complete_item`, `begin_cleanup`, `make_feedback`, `Timeouts::target_timeout_ns`, `Timeouts::target_fresh_age_ns`(`core/config.hpp`) |
| TARGET_LOST의 정리(상태 key `CLEANUP.TARGET_LOST.{NONE, AIR, AIR_LAND, GROUND}`). 분기 고르기와 분기 동작은 ITEM_TIMEOUT 정리와 같고 끝 reason이 TARGET_LOST다 | `CleanupCause::kTargetLost`, `begin_cleanup`, `step_cleanup`, `finish` |
| 1b 쟁점 12의 FramePort 호출 규율(한 tick에 한 항목당 점 변환과 벡터 변환이 각각 많아야 한 번. 완료 tick에 다음 항목도 GOTO나 TRACK_ENTITY이면 두 번. 벡터 변환은 TRACK_ENTITY만 부른다. 1a type 항목, 정리, 종료 단계는 부르지 않는다) | `Tick::frame`, `goto_transform`, `track_transform` |
| 비행 중 감시 표(지상 arm 진입은 P6의 첫 ARMED 표본부터, 공중 Offboard 진입은 P3 다음 tick부터 setpoint 항목 끝까지), failsafe 이력의 구간 | `monitor_flight`, `monitored_status`, `evaluate_monitor`(`core/rules.hpp`) |
| 감시 표로 끝낼 때의 disarm 1회 | `end_by_monitor`, `monitor_row_disarm`, `monitor_sends_disarm`(`core/rules.hpp`) |
| 항목 표 LAND와 RTL(1b 쟁점 9), 모드 명령 항목의 감시 세 구간, 대비책 disarm, RTL의 거부 ack와 미확인 | `step_mode_item`, `mode_item_spec`(`core/rules.hpp`) |
| 모드 명령 항목의 ITEM_TIMEOUT | `mode_item_timeout` |
| 쟁점 3 M3-M5 취소, setpoint 항목의 ITEM_TIMEOUT, TRACK_ENTITY의 TARGET_LOST, PREPARING 실패, RTL 실패(1b 쟁점 9)의 정리. 공중 Offboard 진입의 실패와 취소도 같은 분기 고르기다(arm을 보내지 않은 goal이라 지상 DISARMED이면 정리할 것 없음) | `begin_cleanup`, `step_cleanup`, `select_cleanup` |
| 1b 쟁점 10 공중 종료 단계(상태 key `CLEANUP.MISSION_END.{NONE, AIR, AIR_LAND, GROUND_WAIT}`), 쟁점 10의 지상 DISARMED 3회 계수, "지상 DISARMED를 보는 동안의 규칙"(아래와 테스트 주석의 "분류 지상 규칙")과 종료 단계의 "만료가 이긴다" 두 쌍, 쟁점 11의 지상 대기 disarm 확인 | `complete_item`, `step_mission_end`, `mission_end_hold_failed`, `mission_end_enter_air_land`, `mission_end_enter_ground_wait`, `mission_end_ground_disarm_count`, `finish`(원인 `kMissionEnd`의 결과 대응) |
| 착지 뒤 대비책 disarm의 기한(LAND, RTL 항목과 지상 대기가 같이 쓴다. 1b 쟁점 10) | `LandedArmedFallback`(`core/rules.hpp`) |
| M4 Hold 분기와 Land 경로, Hold 실패 뒤의 공중 재진입, RTL 실패의 Land 경로(Hold 없음) | `enter_air`, `run_air`, `enter_air_land`, `run_air_land` |
| M5 지상 disarm 분기, 상태 끊김과 거부 ack | `enter_ground`, `run_ground`, `DisarmConfirm` |
| M6 정리의 상한 | `cleanup_cap_ns`(`core/config.hpp`), `cleanup_cap_reached`, `end_at_cleanup_cap` |
| disarm 분류의 고정 규칙 | `disarm_class_`(모드 명령 항목, 정리, 공중 종료 단계), `DisarmClass` |
| 명령 재전송 규칙 | `send`, `resend_due`, `take_ack` |
| 쟁점 10 타임아웃 기본값, 정리의 상한 | `core/config.hpp`의 `Timeouts`, `cleanup_cap_ns` |

## SITL 시나리오 trace가 다르면 고칠 곳

아래 동작은 표대로 구현했고 Executor를 거치는 SITL 시나리오 trace로 확인한다. trace가 표와 다르면 아래 한 곳만 고친다. 고칠 때는 px4-engineer가 필수 승인자다.

| 항목 | 고칠 곳 |
| --- | --- |
| 지상 setpoint 발행 중의 Hold(지상 분기 -> 공중 분기) | `MissionRunner::enter_air` |
| 이륙 직후 landed가 true인 구간의 지상 setpoint와 disarm | `MissionRunner::enter_ground`, `ground_setpoint` |
| 감시 표의 행 순위 | `core/rules.hpp`의 `kMonitorRankOrder` |
| "disarm 전송 뒤 받은 표본"의 기준 | `core/rules.cpp`의 `is_after_disarm_send` |
| 타임아웃 기본값과 재전송 주기 | `core/config.hpp`의 `Timeouts` |

## 표에 없어 구현에서 정한 것

decisions.md에 적히지 않아 구현에서 정한 것이다. 근거가 바뀌거나 decisions.md에 올라가면 이 절에서 지운다. 고칠 때는 px4-engineer가 필수 승인자다.

1. P0의 "vehicle_status가 신선"은 마지막 수신이 `link_timeout`(2 s) 안이다.
2. P1(시작 조건)은 P0을 통과한 tick마다 P2를 기다리는 동안 다시 본다. 기다리는 중에 누가 arm하면 PRECONDITION_FAILED다.
3. P3은 위치 값(x, y, z와 MODE_KEEP이면 heading)이 유한할 때까지 기다린다(`ready_timeout` 안). `xy_valid`는 gate로 쓰지 않는다는 결정은 그대로다.
4. P4의 신호 확인은 발행 시작 tick 뒤에 받은 failsafe_flags만 쓴다(그 전의 flags는 앞 미션의 값일 수 있다).
5. P6의 확인 계수: 첫 ARMED 표본을 본 tick에 계수를 0으로 두고 그 표본부터 센다. 세는 것은 감시 표를 지난 표본 가운데 ARMED이고 OFFBOARD인 서로 다른 표본이다(감시 표를 지난 표본은 OFFBOARD이고 ARMED인 채 failsafe인 방어용 표본을 빼면 늘 ARMED이고 OFFBOARD다). 첫 ARMED 표본 전에는 세지 않는다.
6. 감시 구간(P6의 첫 ARMED 표본부터, 공중 Offboard 진입은 P3부터 setpoint 항목 끝까지)에서 timestamp가 하한(지상 arm 진입은 첫 ARMED 표본, 공중 Offboard 진입은 P3 표본이고 첫 OFFBOARD 표본의 tick에 그 표본으로 올린다)보다 작은 vehicle_status 표본은 판정에 쓰지 않고, 그 tick의 감시 표와 확인 계수는 직전에 쓴 표본으로 본다. 그래서 그런 표본만 오면 순위 3의 `link_timeout`은 직전에 쓴 표본의 수신 시각부터 흐른다. 식별이 어긋난 표본은 timestamp와 무관하게 순위 2로 본다. 이 거르기는 감시 구간과 그 바로 뒤의 공중 종료 단계에만 쓰고 그 밖의 정리와 모드 명령 항목(LAND, RTL)에는 적용하지 않는다(그 둘은 `SampleCounter`의 "직전보다 크지 않은 timestamp는 건너뛴다"와 disarm 확인의 전송 뒤 표본 기준만 쓴다).
7. 지상 disarm 1회의 조건 2("첫 ARMED 표본 뒤에 받은 landed가 한 번도 false가 아니었다")는 `received_tick`이 첫 ARMED 표본의 tick 이상인 vehicle_land_detected 표본으로 본다(같은 tick에 받은 표본을 넣는다). 조건 3의 "그 tick의 최신 landed"는 그 tick의 Snapshot 값이다.
8. Hold와 Offboard는 같은 DO_SET_MODE라 ack로 가를 수 없다. 대기 중인 명령이 하나라는 규칙에 기대어 그 명령의 ack로 본다. Offboard의 늦은 거부 ack가 Hold 대기 중에 오면 Hold 거부로 읽힌다.
9. 모드 명령 항목(LAND, RTL)의 대비책 disarm은 확인 대상 모드(AUTO_LAND, AUTO_RTL) 확인 뒤에만 보낸다(대기 중인 명령은 하나라 NAV_LAND, NAV_RTL 재전송과 겹치지 않게). 지연 시간은 landed이고 ARMED인 최신 값을 처음 본 tick부터 재고, 둘 중 하나가 깨지면 처음부터 다시 잰다.
10. disarm 분류(지상 대 공중)는 처음 관측한 DISARMED 표본에서 정하고, ARMED 표본을 보면 미정으로 되돌린다. 모드 명령 항목에서 정한 분류는 취소와 RTL 실패의 정리로 이어진다.
11. 지상 disarm 분기의 LINK_LOST에서 "disarm을 한 번 더 보낸다"는 그 tick의 분기 고르기가 지상일 때다.
12. ITEM_TIMEOUT, TARGET_LOST, PREPARING 실패, RTL 실패의 정리와 공중 종료 단계 중 feedback phase는 그 전 단계의 phase(EXECUTING, WAITING_MODE, PREPARING)를 유지한다(RTL 실패는 WAITING_MODE, 공중 종료 단계는 EXECUTING이고 `item_index`는 N-1). PHASE_CANCELING은 취소일 때만이다.
13. 지상 setpoint의 위치가 유한하지 않으면 P3에서 읽은 위치를 쓰고, heading이 유한하지 않으면 그때의 setpoint yaw를 쓴다.
14. 정리의 상한 tick에서 공중일 때 `detail`에 더하는 "Hold를 관측해 발행을 멈춘 기체"의 판정은 "이 정리에서 식별이 맞는 AUTO_LOITER 표본을 한 번이라도 봤다"이다. "발행을 멈췄다"는 이 goal이 발행한 적이 있을 때만 적는다. 상한의 `detail`에는 상한 값(ms)과 마지막 분기(none, air (Hold), air (Land path), ground (disarm), ground (wait for disarm))를 적는다.
15. "Hold가 한 번 실패했다"는 이 정리에서 Land 경로에 한 번이라도 들어갔다는 뜻이다(거부 ack와 `hold_confirm_timeout` 둘 다 Land 경로로 들어간다). 공중 종료 단계는 지상에서 온 Hold 실패(지상 대기로 간다)에도 이 표시를 세워 지상 대기에서 공중으로 돌아가면 늘 Land 경로다. 정리를 시작할 때 지운다. 재진입한 Land 경로의 `detail`에는 처음 실패한 이유와 재진입했다는 것을 한 번만 적는다. RTL 실패의 정리는 Hold를 보내지 않으므로 이 표시를 세우지 않고, 공중 진입이 Land 경로인 것은 원인으로 정한다.
16. 끝나는 tick에 확인 없이 한 번 보내는 명령(감시 표 종료의 disarm, 정리의 상한의 disarm과 NAV_LAND, 식별 불일치의 disarm, 지상 disarm 분기의 상태 끊김과 만료 때 한 번 더 보내는 disarm)은 그 tick의 `Px4Timestamp`를 먼저 묻는다(`send_final`). 명령의 종류, 조건, tick은 그대로다. 만들 수 없으면 명령을 버리고 결과는 유지하며, `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground" 대신 "disarm not sent (Px4Timestamp unavailable); vehicle state unknown, may remain armed on ground"를, NAV_LAND이면 "NAV_LAND not sent (Px4Timestamp unavailable); vehicle state unknown"을 적는다. NAV_LAND 문구에 "may remain armed on ground"를 붙이지 않는 것은 NAV_LAND를 보내는 상한 tick의 고르기가 공중(`landed` false)이기 때문이다. 그때 Hold 표본을 본 적이 있으면 보낸 경우 "vehicle stays in Hold if NAV_LAND is lost", 보내지 못한 경우 "vehicle stays in Hold"를 적는다. 이와 달리 `Px4Timestamp`를 만들지 못해 끝난 goal(감시 순위 1과 출력 마무리의 실패. 이 goal이 발행이나 명령을 낸 뒤만)의 꼬리는 그 tick의 최신 `landed`로 가른다(1b decisions.md 쟁점 12): true이면 "vehicle state unknown, may remain armed on ground", false이면 "vehicle state unknown, may remain armed in air", land 표본이 없으면 "vehicle state unknown"(`state_unknown_tail`).
17. GOTO의 setpoint는 항목 시작 tick(`start_item`)에 그 점으로 바꾼다(변환 값이 있으면). 1b 쟁점 7의 "OFFBOARD 3회 확인 tick에 첫 항목을 시작하고 그 항목의 setpoint로 바꾼다"를 중간 GOTO(TAKEOFF, LOITER, GOTO 뒤)에도 같게 써서 "항목 시작 tick의 setpoint는 그 항목의 것"을 한 규칙으로 둔다. 완료는 다음 tick부터 센다.
18. GOTO의 점 변환이 값 없음인 tick은 완료 계수를 0으로 되돌린다(1b 쟁점 8의 "완료를 세지 않는다"와 "3개 연속"을 합쳐 판정하지 못한 tick이 연속을 끊는다고 읽었다. 거짓 완료를 만들 길이 없는 쪽이다).
19. 값 없음인 동안 `setpoint_` 전체(위치와 yaw)를 유지한다. MODE_FIXED yaw도 첫 변환 값이 나올 때 함께 바뀐다. yaw 값은 항목 시작 tick에 정해 두고 첫 변환 값에서 쓴다. 17-19는 TRACK_ENTITY에도 같다(표본이 없는 tick도 값 없음과 같이 유지한다).
20. TRACK_ENTITY에서 표적 표본이 없는 tick은 점 변환과 벡터 변환을 부르지 않는다(변환할 점이 없다).
21. TRACK_ENTITY의 feedback 거리(`distance_valid`)는 그 tick에 점 변환 값을 얻었고 위치 표본이 쓸 수 있으면 표본이 신선하지 않아도 낸다. 신선도는 완료 계수와 feedforward만 가른다.
22. 새 사건 이름은 `TRACK_ENTITY_REACHED`(type마다 완료 사건)와 `TARGET_LOST`(reason 이름과 같다)이고 `GOTO_REACHED` 뒤에 이 순서로 둔다. 감시 표로 끝나는 tick의 기록에 싣는 뒤 사건(ITEM_TIMEOUT, 완료, TARGET_LOST)은 `kAllEvents` 순서다.

## 알려진 제한

- REASON_NOT_READY로 끝난 goal은 기체에 setpoint와 명령을 하나도 보내지 않았다(발행 시작 전인 P0-P2에서만 쓴다). 발행을 시작한 뒤의 식별 불일치는 INTERNAL이다.

## 테스트

`test/`의 core 단위 테스트는 gtest와 core만 링크한다(노드와 DDS 참가자를 만들지 않는다). `test/px4/`는 어댑터(px4-engineer), `test/node/`는 노드 껍질 테스트다. runner를 쓰는 테스트 파일(`test_mission_validation.cpp`, `test_runner_*.cpp`)과 `test_transition_coverage.cpp`는 gtest 실행 파일 하나 `test_runner`로 묶는다(전이 칸 대조가 모든 상태기 테스트의 관측을 모아야 한다). `test_termination`, `test_monitor_table`, `test_confirm_rules`, `test_snapshot`은 runner를 쓰지 않아 따로 둔다.

| 파일 | 내용 |
| --- | --- |
| `runner_harness.hpp` | tick 열 helper(20 Hz 흉내, 합성 timestamp, 가짜 PX4 반응(DO_SET_MODE OFFBOARD, Hold, NAV_LAND, NAV_RTL, DISARM 반응을 끄는 switch), 공중 Offboard 진입 미션과 진입 helper(`drive_to_air_offboard`, `drive_to_air_seen`), GOTO 항목과 미션 helper(`goto_item`, `takeoff_goto_land_mission`, `air_goto_mission`), TRACK_ENTITY 항목 helper(`track_entity_item`), 표적 표본(`World.targets`에 등록한 표적마다 tick마다 새 표본, `target_hook`으로 바꾸거나 생략), 위치 표본의 `xy_valid`와 timestamp 지정(`World.xy_valid`, `World.position_timestamp_us`), FramePort 시험 구현 `HarnessFramePort`(기본 `kFail`은 부르면 실패라 GOTO가 없는 모든 사례가 "1a type 미션은 FramePort를 부르지 않는다"를 함께 단정한다. `kAxis` 축 치환, `kNone` 점 값 없음, 점과 벡터의 tick별 hook, 점과 벡터 호출 수와 tick별 입력), 모든 step 뒤 속도 불변식(속도가 있으면 세 성분 유한, 끝 상태 `ITEM.TRACK_ENTITY`), `feed`로 표본 열 주입, 종료 불변식: 정확히 1건, result == 종료 사건, 종료 뒤 빈 출력). 만드는 runner에 전이 기록기를 넘기고, 기록기가 켜져 있으면 그 runner의 기록을 `edges()`에도 모은다. `expect_cell`은 한 시나리오가 낸 칸(from, 사건, to, reason, 함께 참이던 사건)을 시작 인덱스 뒤의 기록에서 찾아 단정하고 그 기록을 돌려준다(`output_of_tick`으로 그 tick의 출력을 본다) |
| `transition_recorder.hpp` | 전이 기록기(관측한 칸과 그 칸을 처음 낸 테스트, untagged 기록) |
| `transition_cells.tsv` | 전이 칸 목록(covered, impossible과 이유, uncovered, 겹침 칸) |
| `test_transition_coverage.cpp` | 칸 목록 파일 형식, `Event` 이름 집합 == 목록의 사건 집합, 감시 표 사건 칸을 가진 상태 key마다 대표 행 쌍(순위 4나 5가 6-8을 이김)이 있음, untagged 검출(`TransitionUntagged` 다섯 건: 한 꼬리표 아래 두 번째 변경이 untagged, 같은 값 쓰기는 세지 않음, 변경 하나는 tagged, 세 번째 변경은 같은 untagged 기록에 합쳐짐, 새 꼬리표가 오면 untagged 기록이 먼저 닫힘), 기록기를 켜고 끈 두 실행의 출력이 같음(시나리오 열아홉: 정상, 공중과 지상 취소, Px4Timestamp 실패, ITEM_TIMEOUT 정리의 Land 경로, 감시 표 행끼리 겹침, 감시 표와 완료 겹침, LAND 이탈, `[LAND]` 미션, `[TAKEOFF, LOITER, RTL]` 정상, RTL 거부의 Land 경로, 공중 종료 단계의 공중 Hold 확인, 지상 대기에서 Land 경로, 공중 Offboard 진입의 정상과 DO_SET_MODE 전에 본 OFFBOARD, `[TAKEOFF, GOTO, LAND]` 정상, 공중 Offboard 진입 `[GOTO]` 정상, `[TAKEOFF, TRACK_ENTITY, LAND]` 정상, 공중 Offboard 진입 `[TRACK_ENTITY]` 정상. setpoint의 속도까지 비교한다), `Environment::TearDown`의 대조(관측 == covered, impossible 미관측, 목록 밖 칸 미관측, untagged 0, uncovered 칸 0). uncovered 부류의 칸이 목록에 있으면 `TransitionCells.NoUncoveredCell`과 대조가 실패한다(B8b부터. 상태기를 바꾸는 PR은 새 칸을 같은 PR에서 덮는다). 일부만 돌면(`--gtest_filter`, sharding, `DISABLED_`, `GTEST_SKIP`) 실패한다. 개발자가 일부만 돌릴 때는 `IDSIM_TRANSITION_PARTIAL_OK=1 ./test_runner --gtest_filter=...`로 대조를 건너뛴다. `IDSIM_TRANSITION_CELLS_DUMP=<경로>`이면 관측한 칸을 같은 형식으로 쓴다 |
| `test_mission_validation.cpp` | 검증 규칙, 계약 순서 규칙과 그 문구, `target_id` 형식, 좌표 상한 술어(경계, 비유한), `TYPE_*` 분류 전수, `screen_goal` 순서와 순서 위반의 detail, type 여섯 x 길이 1-4의 1554개 순서에서 goal 접수가 받는 미션 == 계약(runner)이 받는 미션(266), GOTO, TRACK_ENTITY, RTL 미션의 goal 접수, 형식이 틀린 `target_id`의 INVALID_MISSION, runner INVALID_MISSION의 detail(계약 순서 위반), 계약 좌표 상한(경계 1e5 포함, 상한 밖 5e5, 유한 검사 뒤, 둘째 항목의 index, goal 접수의 detail, TAKEOFF `height_m`은 상한 없음) |
| `test_termination.cpp` | status와 reason 전수 대응표, reason 값, 종료 결과 == 종료 사건 |
| `test_monitor_table.cpp` | 감시 표 순위마다 한 건, 같은 tick 동률 24쌍(`row`가 앞 순위이고 `matched`가 두 행을 순위 순서로 담음. 행 쌍의 "전부"는 이 표가 보증한다), 배타 4쌍, 순위 5의 가지, 행 수와 parametrize 수, 감시 표로 끝낼 때의 disarm 술어(8행 전수 x 입력 16조합), AUTO_LOITER 면제(`hold_exempt`: 순위 7, 8만, 순위 6과 4, 5는 그대로, AUTO_LOITER 밖의 모드는 그대로, 기본값 꺼짐) |
| `test_confirm_rules.cpp` | N회 연속 계수, 전송 뒤 표본 기준, 늦은 arm 경합, 착지 뒤 대비책의 기한(`LandedArmedFallback`), 정리 분기 고르기(snapshot 5종), yaw 변환 |
| `test_snapshot.cpp` | snapshot 헤더의 새 타입 기본값(`SetpointOut.velocity_valid`, `PositionSample.xy_valid`와 `timestamp_us`, `TargetSample.stamp_ns`, 빈 `Snapshot.targets`), `kNavRtl`의 이름과 ack 묶음, 가짜 구현으로 본 `FramePort` 계약 모양(무효 기준의 점 변환은 nullopt, 벡터는 기준과 무관하게 값). 실제 변환 식과 기준 유효 술어는 `px4/test_px4_frame_port.cpp`가 본다 |
| `test_runner_preparing.cpp` | P0-P6, `[LAND]` 미션, PREPARING 실패의 정리, P6의 첫 ARMED 표본 뒤(감시 표 행마다, 묵은 표본, arm 재전송 중단, 늦은 거부 ack, 확인 기한과 3번째 확인의 같은 tick, P6 최대 길이의 끝 경계, 감시 표의 같은 tick, failsafe 이력의 구간, landed false 이력의 같은 tick 경계), 식별 불일치의 disarm과 `Px4Timestamp` 실패 |
| `test_runner_items.cpp` | TAKEOFF, LOITER, 상태기 안의 감시 표(순위마다), 엇갈림, 이력의 항목 경계, 분류 고정, 감시 표로 끝낼 때의 disarm 1회(8행 x {P6, TAKEOFF, LOITER} x landed 이력) |
| `test_runner_land.cpp` | LAND 세 구간, 완료 우선, AUTO_LAND 3회째와 `mode_confirm_timeout`의 같은 tick(만료가 이긴다), 대비책 disarm, LAND의 ITEM_TIMEOUT 변형 |
| `test_runner_rtl.cpp` | `EntryPlan`과 `mode_item_spec`, `[RTL]`과 `[TAKEOFF, RTL]`, `[TAKEOFF, LOITER, RTL]`(발행 중단 시점), 거부 ack와 미확인의 Land fallback(거부 범위, detail, Hold 실패 표시 없음, phase WAITING_MODE), 지상 분기 뒤 재진입 문구, 확인 뒤 이탈, 확인 전 흔들림, nav 무관 완료, 즉시 종료 넷, item timeout 문구, 대비책 disarm, 같은 tick 규칙(거부와 만료, 거부와 공중 DISARMED, 3회째와 거부, 3회째와 거부와 만료, 3회째와 만료), 취소의 Hold와 취소 겹침, LAND의 거부 ack 무시와 1a 문구 고정 |
| `test_runner_cleanup.cpp` | 취소 분기, Hold와 Land 경로, 지상 disarm 확인과 상태 끊김, ITEM_TIMEOUT 정리, 원인 3 x snapshot 3 교차표, 정리 중 식별 불일치, Hold 실패 뒤 공중 재진입과 재진입 문구, 분기 재진입(`BranchReentry`: 지상 재진입의 disarm 확인 기준, 공중 재진입의 Hold 재전송과 타이머와 계수), 정리의 상한(원인 3 x {지상, 공중}과 정확한 마지막 분기 문자열, 가장 긴 정당한 경로, 같은 tick 넷, 상한 tick의 고르기가 직전 분기와 다른 경우, 상한 대 3번째 Hold 확인, 마지막 분기가 Land 경로, 식별 불일치 표본, Hold 관측 문구), 끝나는 tick의 `Px4Timestamp` 실패(상한의 disarm과 NAV_LAND, 상태 끊김의 disarm, 정리 첫 tick 식별 불일치의 disarm) |
| `test_runner_conflicts.cpp` | 종료의 충돌 규칙, `Px4Timestamp` 공급 실패(지상 disarm 분기 만료의 마지막 disarm 포함) |
| `test_runner_mission_end.cpp` | 공중 종료 단계(1b decisions.md 쟁점 10, 쟁점 11): 공중 Hold 확인과 `[TAKEOFF]`, ACCEPTED ack 뒤의 Hold 재전송과 Hold 하나 유실, 공중 거부와 거부 ack 유실, Hold 기한과 Land 경로 기한, 만료가 이기는 두 쌍(Hold 3회째 대 `hold_confirm_timeout`, 확인 대 상한), Hold 3회째 tick의 거부 ack(거부가 먼저), 지상 대기의 대비책 disarm과 확인, Hold 대기 중 자동 disarm, 지상 거부 뒤 공중 재진입, 대비책 실패의 상한, Land 경로의 상한(공중과 지상), Land 경로의 지상 DISARMED, 상태 끊김 넷, 공중 DISARMED 셋, `Px4Timestamp` 실패 셋과 첫 tick, 취소 셋, 마지막 항목의 겹침(기존 칸), 식별 불일치 다섯, 묵은 표본, 지면 높이 목표, 분류 지상 규칙(DISARMED AUTO_LAND 표본, 분류 지상의 분기 기한과 상한, 버린 거부 ack, 식별 불일치 상한 tick). 칸마다 그 tick의 명령과 종료의 `items_completed` N, `last_item_index` N-1, phase EXECUTING을 본다 |
| `test_runner_offboard_ack.cpp` | P5 안의 ack 대기(1b decisions.md 쟁점 12): 단위 테스트 다섯 사례(재전송 다음 tick 확인, 확인 뒤 ack 없으면 주기 재전송 뒤 timeout, 확인 뒤 거부 ack, 대기 중 이탈, ack 전 대기 중 취소)와 보조(주기가 찬 tick에 받은 ack는 유효이고 재전송을 막음, 확인 전 유효 ack면 재전송 없이 확인 tick에 arm(IN_PROGRESS 포함), 재전송이나 그 ack의 유실 뒤 다음 주기로 arm, 주기가 찬 확인 tick의 재전송, 주기가 찬 tick의 실패와 취소에 재전송 없음, 유효 ack 뒤 OFFBOARD 미확인의 timeout, 앞선 전송의 늦은 ack의 열화, 확인 표본 이하 timestamp는 이탈이 아님, 확인 전 거부의 detail), 확인 tick이나 대기 중 tick의 취소 겹침 출력 |
| `test_runner_air_entry.cpp` | 공중 Offboard 진입(1b decisions.md 쟁점 7. 사례 이름의 A1-A27은 일련번호): 정상과 첫 항목 뒤 LAND, RTL, LOITER, 시작 조건 여섯(detail의 값), P2 대기와 `ready_timeout`, 진입 setpoint 고정, 신호 기한과 신호 확인의 같은 tick, DO_SET_MODE 전에 본 OFFBOARD와 그 겹침, DO_SET_MODE 유실 뒤 재전송, 거부와 거부 ack 유실, 첫 OFFBOARD 표본과 거부 ack의 같은 tick, 기한(OFFBOARD를 못 봄, 봄), 첫 표본과 3회째의 기한 같은 tick, 첫 OFFBOARD 표본 뒤 재전송 없음, AUTO_LOITER 면제와 그 끝, failsafe 이력 구간(첫 항목까지 한 구간), 세 상태 key의 감시 행 전부, 묵은 표본(첫 OFFBOARD 표본 뒤 하한 상승 포함), P3 tick의 Px4Timestamp, 취소와 겹침, 지상 ARMED의 취소와 실패(지상 분기, Hold 없음), ITEM_TIMEOUT 정리와 준비 단계 실패 정리의 "정리할 것 없음". 모든 사례에서 ARM이 없고 준비 단계 feedback은 item 0의 LOITER다 |
| `test_runner_goto.cpp` | FramePort 호출 규율(1a type 미션 일곱과 취소, TAKEOFF ITEM_TIMEOUT에서 호출 0, GOTO -> GOTO 완료 tick의 호출 2회)과 GOTO 항목(1b decisions.md 쟁점 8): 지상 진입 정상(시작 tick의 setpoint와 feedback 거리, tick당 호출 1회), 서로 다른 표본과 연속(같은 timestamp, `xy_valid`, `z_valid`, 반경 밖 표본), 경계 거리(엄격 부등호)와 ITEM_TIMEOUT, 첫 변환 대기, 중간의 변환 없음, 변환을 못 얻은 ITEM_TIMEOUT의 detail과 정리 중 phase, 만료와 3개째의 같은 tick, yaw(MODE_FIXED, 값 없음 동안 유지, MODE_KEEP의 직전 yaw), 매 tick 다시 변환, 다음 항목(LOITER, RTL, GOTO, 종료 단계, LOITER -> GOTO), 공중 진입(정상, LAND, LOITER 뒤, 시작 조건 detail, 변환 없음, 지상 DISARMED의 정리할 것 없음), 취소와 겹침, 감시 표 단일 행과 대표 쌍, ITEM_TIMEOUT과 완료의 대표 행 넷씩. 끝나는 사례마다 완료 수, index, 매 tick feedforward 없음을 단정한다 |
| `test_runner_track.cpp` | TRACK_ENTITY 항목(1b decisions.md 쟁점 8): 지상 진입 정상(시작 tick의 setpoint, 속도, feedback 거리, tick당 점과 벡터 호출 1회와 입력), 신선도와 feedforward(나이 0.1 s는 신선, 0.15 s는 아님, `velocity_valid` false, 벡터 변환 값 없음, 미래 stamp), 신선하지 않은 tick이 연속을 끊음, 표본 없이 시작(진입 전 setpoint 유지, 호출 0), TARGET_LOST(획득 전 K+21, 획득 뒤 마지막 표본 + 21 tick, 앞 항목의 표본, ITEM_TIMEOUT과 같은 tick, timeout 1 s의 ITEM_TIMEOUT이 먼저), ITEM_TIMEOUT과 정리 중 속도 없음, 만료와 3개째의 같은 tick, 움직이는 표적, 점 변환 값 없음, TRACK_ENTITY -> TRACK_ENTITY 완료 tick의 호출 2회, yaw(MODE_FIXED, 표본 전 유지, MODE_KEEP), 다음 항목(LOITER, RTL, GOTO, 종료 단계, GOTO -> TRACK_ENTITY, LOITER -> TRACK_ENTITY), 공중 진입(정상, LAND, LOITER 뒤, 시작 조건 detail, 표본 없음의 TARGET_LOST), 취소와 겹침(TARGET_LOST, ITEM_TIMEOUT, 완료, 바로 끝내는 사건, 다음 항목의 취소), 감시 표 단일 행과 대표 쌍, TARGET_LOST, ITEM_TIMEOUT, 완료의 대표 행 넷씩. 끝나는 사례마다 완료 수, index, port 호출 규율을 단정한다 |
| `test_runner_resend_after_ack.cpp` | 지상 arm 진입 밖의 재전송 경로 여섯 곳(P6 arm, 모드 명령 항목(NAV_LAND, NAV_RTL, 대비책 disarm), 정리의 지상 disarm, 공중 Hold, Land 경로, 공중 Offboard 진입의 P5)이 비거부 ack(ACCEPTED, IN_PROGRESS) 뒤에도 확인 표본 전까지 주기 재전송을 이어 감 |
| `test_runner_flow_cells.cpp` | PREPARING과 항목 단계의 칸을 하나씩 덮는다(칸마다 `expect_cell`과 종료 결과). 무시된 취소의 대표 칸은 Hold와 disarm이 그 tick과 그 뒤에 나가지 않음을 함께 단정한다(READY_TIMEOUT과 취소는 NOT_READY이고 명령 없음, ARM의 MONITOR_MODE_FAILSAFE와 취소는 disarm 1회). setpoint 항목의 tick 순서는 대표 행 넷 x {TAKEOFF, LOITER} x {ITEM_TIMEOUT, 완료}의 파라미터화 테스트(`SetpointOrderCells`) |
| `test_runner_cleanup_cells.cpp` | 정리 단계 칸의 파라미터화 harness(`CleanupCellTest`). 파라미터 하나가 칸 하나(정리 원인, 분기, 사건)이고, `CleanupRig`가 원인의 입구(P5 취소, TAKEOFF의 ITEM_TIMEOUT, P5 거부 ack, P6 거부 ack, `[RTL]`의 NAV_RTL 거부 ack, `[TAKEOFF, TRACK_ENTITY]`와 공중 Offboard 진입 `[TRACK_ENTITY]`의 TARGET_LOST)로 정리를 시작해 분기(NONE, AIR, AIR_LAND, GROUND, Hold 실패 뒤 GROUND)까지 몰고 간 뒤 사건을 일으킨다. 칸마다 그 칸의 기록이 난 tick의 명령(없음, disarm 1회, NAV_LAND 1회, Hold 1회)을 1a 표대로 단정하고, Hold 거부와 Hold 만료는 NAV_LAND의 첫 발행과 그 시점도 본다. 정리의 상한 칸은 분기를 나갔다 바로 돌아와 분기 타이머를 다시 시작하며 목표 분기에서 상한 tick을 맞는다(머무는 tick 수는 분기 타임아웃에서 파생, 상한 tick 표본의 landed는 칸의 입력 열) |
| `node/test_contract_constants.cpp` | core 값과 메시지 상수(REASON_* 13, 14 포함, TYPE_*, MODE_*, PHASE_*, STATUS_*), yaw 식과 idsim_common/frames, 변환의 result == 사건, `is_valid_target_id`와 `TargetId::parse`의 사례 표 대조, `to_target_sample`의 유효 표본 규칙(경계 1e5, 비유한 위치와 유효 속도, 무효 속도 필드 무시, stamp 0과 비증가, 다른 target_id와 frame_id), 비행 중 원점 변경 WARN 판정 `reference_changed_in_flight`(landed false에서 바뀜만 참, 지상의 첫 원점 설정은 거짓) |
| `python/test_send_mission_wait.py` | `send_mission._wait`: 끝나지 않는 future를 `POLL_S` timeout으로 반복 spin, 끝난 future는 spin하지 않음, spin의 KeyboardInterrupt 전파(가짜 rclpy) |
| `python/test_mission_yaml.py` | 미션 YAML 로더: YAML 파일 -> `Mission`(type 여섯, 기본값, ns 반올림, 메시지 상수 대조), `mission_id` 기본값과 정규식, 구조 오류(모르는 key, 중복 key, merge key, 필수 key, 타입), YAML 문법 오류, float과 Duration 범위를 넘는 정수, UTF-8이 아닌 파일, CLI의 로더 오류 종료 코드 2, timeout 변환 오류(음수, 비유한, int32 초과), 계약 위반 미션은 로더 오류가 아님 |
| `node/test_executor_node.cpp` | 한 프로세스 배선(노드, 가짜 PX4, /clock thread, action client): self_start 대조군 쌍, 직접 configure/activate, configure 실패(`vehicle.*`, `use_sim_time`, `world.origin` 누락, 범위 밖, 타입, `target_fresh_age` >= `target_timeout`), 정상 경로 SUCCEEDED와 1b 무효 경로(TRACK_ENTITY 0 `offset`) INVALID_MISSION(사건 ACCEPTED가 앞, 종료 사건 1건, result와 같은 값), `target_timeout`, `target_fresh_age` 기본값(1.0 s, 0.1 s), GOTO setpoint가 진짜 `Px4FramePort`를 거쳐 로컬 NED로 나감, 표적 표본을 끊은 TARGET_LOST에서 Hold 관측까지 setpoint 발행 유지와 관측 뒤 중단, 표적 구독 수명(goal 접수에 생기고 끝에 없어짐, 같은 id는 하나)과 다음 goal 접수의 `Snapshot.targets`만 비움, goal 중 deactivate 거부와 on_shutdown의 ABORTED INTERNAL, 종료 때 disarm(arm 뒤 1개, arm 전 0개), PREPARING 중 취소의 CANCELED, 두 번째 goal의 BUSY, cancel을 받아들인 goal의 abort 허용(rclcpp_action) |

전이 칸 목록(`test/transition_cells.tsv`)의 부류별 칸 수. 겹침 칸의 열거 범위는 `docs-for-agent/plan-1b-mission-target/decisions.md` 쟁점 13이다(감시 표 행 쌍은 상태 key마다 대표, setpoint 순서는 대표 행 넷, 무시된 취소는 정리로 들어가는 사건 모두와 바로 끝내는 사건의 대표). 미덮임은 0이고, 목록에 생기면 덮음 테스트가 실패한다.

| 부류 | 단일 | 겹침 | 합 |
| --- | --- | --- | --- |
| covered | 358 | 94 | 452 |
| impossible | 130 | 1 | 131 |
| uncovered | 0 | 0 | 0 |
| 합 | 488 | 95 | 583 |

PX4 v1.17.0에서 나오지 않는 방어 경로(OFFBOARD이고 ARMED인 채 failsafe, 순위 5의 이력, 순위 8, DISARM과 ARM의 그 밖의 거부 ack, 첫 ARMED 표본보다 묵은 표본, timestamp가 늘지 않는 표본)와 실제 PX4로 재현하기 어려운 P3-P5의 외부 arm, P5 ack 대기의 확인 뒤 거부 ack(DISARMED에서 DO_SET_MODE 거부는 TERMINATION뿐)와 대기 중 OFFBOARD 이탈(다른 출처의 모드 변경), 정리 중 공중 DISARMED, 정리의 상한, 공중 종료 단계의 Hold 거부 ack와 식별 불일치, 시각 건너뛰기, NAV_RTL의 거부 ack(SITL의 1b 시나리오에 RTL이 거부되는 경우가 없다)와 RTL 실패 정리 첫 tick의 묵은 공중 DISARMED 표본은 합성 표본과 합성 ack로만 시험하고 테스트 주석에 그렇게 적었다. 단위 테스트는 합성 timestamp만 검사한다. 실제 시계 관계는 SITL 시나리오 trace가 확인한다.
