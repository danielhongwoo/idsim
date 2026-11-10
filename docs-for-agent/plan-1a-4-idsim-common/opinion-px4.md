> 이 파일은 2026-11-10 설계 토론의 원문이다. 본문의 `/tmp/...scratchpad...` 경로와 `re/`, `ws/`, `exp/` 같은 실험 경로는 당시 작업 환경의 임시 파일이라 저장소에 없다. 실험 결과는 본문에 인용된 내용이 전부다.

# 1a 4단계 idsim_common 설계 토론: px4-engineer 의견

작성 2026-11-10, px4-engineer. 저장소 파일은 고치지 않았다.

근거 출처 표기
- [소스]: PX4 v1.17.0 태그(커밋 d6f12ad1c4f70ad3230afd7d86e971421e02fef4)를 scratchpad에 sparse clone
  (`.../scratchpad/step4/src/px4`). 런타임 px4 이미지에는 PX4 소스가 없다(`/opt/PX4-Autopilot`에 build, Tools만).
- [이미지]: `idsim/ros-ws:local`(IDSIM_BUILD_PX4_MSGS_REF=86d8239e..., IDSIM_BUILD_PX4_ROS_COM_REF=86e9aeb2...).
- [실측]: 스택 5(`tools/stack.sh up --stack 5`, 2026-11-10 04:59 기동, 작업 후 down). bridge 컨테이너에서
  rclpy 프로브(`.../scratchpad/step4/exp/probe.py`, `probe2.py`)를 돌렸다. 노드는 `use_sim_time=True`.
- [골든]: `tests/fixtures/px4/v1.17.0/`.

---

## P1. MESSAGE_VERSION과 토픽 이름 접미사

결론
- 규칙: 토픽 이름 = `rt/<ns>/<dds_topics.yaml의 topic에서 앞 빗금 제거><접미사>`, 접미사는
  해당 uORB 타입의 `MESSAGE_VERSION`이 0이 아니면 `_v<N>`, 0이거나 상수가 없으면 없음.
  /fmu/out(data writer)과 /fmu/in(data reader)이 같은 함수 `generate_topic_name`을 쓰므로 방향과 무관하게 같은 규칙이다.
- 버전은 "토픽 이름"이 아니라 "타입"에서 온다. dds_topics.yaml 항목의 `type`(예: vehicle_gps_position의 SensorGps)으로 정해진다.
- px4_msgs `PX4_MSGS_REF`(86d8239e)의 C++ 헤더에 `MESSAGE_VERSION` 상수가 34개 타입에 있다(1이 9개, 0이 25개). 상수가 아예 없는 타입도 있다(OffboardControlMode 등 `msg/` 최상위 비버전 메시지).
  PX4 v1.17.0 소스 `msg/versioned/`의 값과 정확히 같다.
- 소스 규칙으로 dds_topics.yaml 65개 항목의 이름을 계산하면 골든 `topics.txt` 65줄과 차이 0(타입 포함).
- 어긋남이 드러나는 방식: 이름이 달라져 매칭이 안 될 뿐 오류는 없다. 아래 "어긋날 때" 참조.

근거
- [소스] `src/modules/uxrce_dds_client/utilities.hpp` `generate_topic_name`:
  ```
  if (message_version != 0) { snprintf(version, sizeof(version), "_v%u", (unsigned)message_version); ...
  ... snprintf(topic_name, TOPIC_NAME_SIZE, "rt/%s/%s%s", client_namespace, topic, version);
  ```
  `create_data_writer`(out)와 `create_data_reader`(in) 둘 다 이 함수를 부른다.
- [소스] `dds_topics.h.em`: 버전은 uORB 구조체에서 SFINAE로 읽고 없으면 0.
  ```
  static constexpr uint32_t get(decltype(&C::MESSAGE_VERSION)) { return C::MESSAGE_VERSION; }
  static constexpr uint32_t get(...) { return 0; }
  ...
  get_message_version<@(pub['simple_base_type'])_s>(),           // publications
  uint32_t message_version = get_message_version<@(sub['simple_base_type'])_s>();  // subscriptions
  ```
- [소스] `msg/versioned/`에서 `MESSAGE_VERSION = 1`: AirspeedValidated, ArmingCheckReply, ArmingCheckRequest,
  BatteryStatus, Event, HomePosition, VehicleAttitudeSetpoint, VehicleLocalPosition, VehicleStatus (9개.
  Event는 DDS로 나가지 않아 골든의 `_v1`은 8개).
- [이미지] `/opt/px4_ws/install/px4_msgs/include/px4_msgs/px4_msgs/msg/detail/*__struct.hpp`:
  ```
  vehicle_status__struct.hpp:491:  static constexpr uint32_t MESSAGE_VERSION =
      1u;
  (집계) count 1 -> 9, count 0 -> 25. 1인 것: airspeed_validated arming_check_reply arming_check_request
  battery_status event home_position vehicle_attitude_setpoint vehicle_local_position vehicle_status
  offboard_control_mode__struct.hpp: MESSAGE_VERSION 없음 (grep rc=1)
  ```
  클래스 밖 정의(`constexpr uint32_t VehicleStatus_<ContainerAllocator>::MESSAGE_VERSION;`)도 생성되어 있어 ODR 사용에 문제 없다.
- [소스 대 골든] dds_topics.yaml(publications, subscriptions, subscriptions_multi)을 위 규칙으로 계산:
  ```
  65 65
  only derived []
  only golden []
  ```

어긋날 때 (px4_msgs 쪽 버전 != PX4 쪽 버전)
- PX4는 자기 트리의 uORB 메시지로 이름을 만들고, ROS 쪽은 px4_msgs로 만든다. 둘이 다르면 ROS 노드는
  존재하지 않는 이름(예: `vehicle_status`)을 구독하고 PX4는 `vehicle_status_v1`에 쓴다. DDS 매칭이 안 되어
  "데이터 없음"으로만 보인다. 예외나 로그는 없다. /fmu/in 쪽이면 PX4가 명령을 조용히 못 받는다.
- 버전은 같은데 필드가 다르면(상류의 버전 미증가 실수) 이름은 맞고 CDR 역직렬화가 어긋나 값이 깨진다.
  타입 해시 검사는 없다. [실측] `ros2 topic info -v /px4_1/fmu/in/vehicle_command` -> `Topic type hash: INVALID`
  (에이전트 쪽 엔드포인트가 RIHS 해시를 광고하지 않는다).
- 그래서 방어선은 (1) 컴파일 시점 파생(같은 px4_msgs로 빌드한 노드는 서로 일치), (2) 골든 대조 단위 테스트
  (PX4 쪽 실제 이름과 일치), (3) 2026-11-06에 확인한 px4_msgs와 PX4 v1.17.0 msg 235개 diff 0.
  버전 교차가 필요해지면 PX4가 `msg/translation_node`(px4_msgs_old)를 제공하지만 idsim에는 필요 없다.

idsim_common 구현 의견
- PX4와 같은 방식으로 "상수가 없으면 0"을 처리해야 한다. OffboardControlMode는 상수가 없으므로
  `T::MESSAGE_VERSION`을 직접 쓰면 컴파일 오류다. C++17 `std::void_t` 특수화 하나면 된다.
- 접미사 규칙은 `N != 0 ? "_v" + N : ""`. `_v0`은 존재하지 않는다.

## P2. 6단계(이륙-호버-착륙)가 쓸 최소 토픽

결론: 아래 표가 최소 집합이다. 이름은 네임스페이스(`/px4_<N>`) 뒤에 붙는다.

| 방향 | 토픽(골든 실제 이름) | 타입 | MESSAGE_VERSION | 6단계 용도 |
| --- | --- | --- | --- | --- |
| 구독 | fmu/out/vehicle_status_v1 | VehicleStatus | 1 | arming_state(1 DISARMED, 2 ARMED), nav_state(4 LOITER, 5 RTL, 14 OFFBOARD, 18 LAND), pre_flight_checks_pass, failsafe, system_id |
| 구독 | fmu/out/vehicle_local_position_v1 | VehicleLocalPosition | 1 | z(고도 도달), xy_valid/z_valid(EKF 수렴 판단), heading |
| 구독 | fmu/out/vehicle_land_detected | VehicleLandDetected | 0 | landed(착지 판정의 보조) |
| 구독 | fmu/out/vehicle_command_ack | VehicleCommandAck | 0 | command, result, target_system/target_component로 자기 명령의 ack만 거름 |
| 발행 | fmu/in/offboard_control_mode | OffboardControlMode | 상수 없음(0) | 20 Hz 하트비트 |
| 발행 | fmu/in/trajectory_setpoint | TrajectorySetpoint | 0 | 20 Hz 위치 setpoint |
| 발행 | fmu/in/vehicle_command | VehicleCommand | 0 | arm, DO_SET_MODE offboard, NAV_LAND, disarm |

있으면 좋은 것(6단계 디버깅과 1b 대비)
- fmu/out/failsafe_flags (FailsafeFlags, 0): `offboard_control_signal_lost`, `local_position_invalid`. [실측]에서 Offboard
  신호 판정을 직접 보는 데 썼다. 6단계 진입 실패 진단에 가장 유용하다.
- fmu/out/vehicle_attitude (VehicleAttitude, 0), fmu/out/vehicle_odometry (VehicleOdometry, 0): 좌표 변환 테스트용.
- fmu/out/home_position_v1 (HomePosition, 1), fmu/out/vehicle_global_position (VehicleGlobalPosition, 0): 1b RTL과 표적 좌표.
- fmu/out/timesync_status: P4의 결정에 따라 없을 수 있다(SYNCT=0에서 수신 안 됨 [실측]).

매핑 범위 의견
- 매핑은 골든 65개 전부를 처음부터 덮는 것을 권한다. 컴파일 시점 파생이면 항목 하나의 비용이 작고, 골든
  대조 테스트가 "전부 일치"여야 PX4 태그를 올릴 때 diff가 한눈에 보인다. 6단계 노드는 위 7개만 쓴다.
- 키는 (논리 이름, 타입)만으로는 유일하지 않다. 골든에서 `mode_completed`(ModeCompleted)가 in과 out 양쪽에
  있다. 방향(in/out)을 키에 넣거나 논리 이름에 방향을 포함해야 한다. 같은 타입이 여러 이름에 쓰이는 경우도
  있다(VehicleCommand: vehicle_command, vehicle_command_mode_executor. VehicleOdometry 3개 등). 그래서
  "타입 -> 이름" 역방향 조회는 만들면 안 된다.
- 이름과 타입이 다른 항목에 주의: fmu/out/vehicle_gps_position은 SensorGps, fmu/in/aux_global_position은
  VehicleGlobalPosition, fmu/in/config_control_setpoints는 VehicleControlMode, fmu/in/manual_control_input은
  ManualControlSetpoint. 버전은 타입에서 오므로 표는 (방향, 논리 이름) -> 타입을 손으로 적고, 접미사만 파생한다.
  (추정) 이것이 "손 매핑 테이블 금지" 결정과 충돌하지는 않는다고 본다. 금지 대상은 태그별 접미사 표이고,
  dds_topics.yaml의 이름-타입 쌍은 태그가 바뀌어도 골든 대조로 검증된다.

## P3. VehicleCommand 빌더

결론
- 필드 값(검증된 조합)
  - `target_system` = MAV_SYS_ID = N + 1. 0(브로드캐스트)도 받아들여진다. 그 외 값은 조용히 무시되고 ack도 없다.
  - `target_component` = 1(autopilot). 0도 받아들여진다.
  - `source_system` = 254, `source_component` = 1 (check_px4.py와 같음). `source_component >= 1000`은 쓰지 않는다
    (Commander가 mode executor 출처로 분류).
  - `from_external` = true. `confirmation` = 0.
  - `timestamp`는 P4 참조. 0도 받아들여진다.
- 권장: target_system은 0이 아니라 N + 1을 명시한다. 0은 동작하지만 네임스페이스 매핑 실수(px4_1에 기체 2의
  id를 쓰는 등)를 숨긴다. N + 1이면 매핑이 틀릴 때 ack가 오지 않아 바로 드러난다.
- ack 거르기: Commander는 `ack.target_system = cmd.source_system`, `ack.target_component = cmd.source_component`로
  답한다. 빌더 쪽 헬퍼는 (command, target_system == 254, target_component == 1)로 거른다. Commander 내부나
  navigator가 낸 명령의 ack도 같은 토픽으로 나가므로 command만으로 거르면 섞일 수 있다(추정, 미실측).
- `result == ACCEPTED(0)`는 "모드 의도가 바뀌었다"이지 "nav_state가 바뀌었다"가 아니다. 모드 전환 성공은 반드시
  vehicle_status.nav_state로 확인한다(아래 E4, E5).

빌더가 제공할 명령과 파라미터 배치

| 이름 | command | param1 | param2 | param3 | 그 외 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| arm | 400 COMPONENT_ARM_DISARM | 1.0 | 0 | | | 강제 시동 21196은 빌더에 넣지 않는다 |
| disarm | 400 | 0.0 | 0 | | | 공중 disarm은 21196 필요(넣지 않음) |
| set_mode_offboard | 176 DO_SET_MODE | 1.0 (MAV_MODE_FLAG_CUSTOM_MODE_ENABLED) | 6.0 (PX4_CUSTOM_MAIN_MODE_OFFBOARD) | 0 | | |
| set_mode_hold | 176 | 1.0 | 4.0 (AUTO) | 3.0 (AUTO_LOITER) | | |
| land | 21 NAV_LAND | 0 | 0 | 0 | param4-7 NaN | Commander는 force로 항상 진입. 현재 위치 착륙 |
| rtl | 20 NAV_RETURN_TO_LAUNCH | 0 | | | | |
| takeoff (1b 선택) | 22 NAV_TAKEOFF | NaN | | | param4 yaw NaN, param5/6 NaN(현재 위치), param7 NaN(MIS_TAKEOFF_ALT) 또는 AMSL 고도 | param7=0이면 "현재 고도보다 낮음"으로 제자리. 기본값 0을 쓰면 안 된다 |

- DO_SET_MODE 대신 `VEHICLE_CMD_SET_NAV_STATE`(100001, param1 = nav_state)도 있다(주석 "Used from ROS").
  6단계는 MAVLink와 같은 DO_SET_MODE를 권한다. QGC와 로그에서 의미가 같고, PX4 문서 예제도 이것이다.
- DO_SET_MODE의 함정: param1에 1.0을 빠뜨리면(base_mode 0) 원하는 모드가 계산되지 않아 TRANSITION_NOT_CHANGED이고
  결과는 ACCEPTED다. 모드는 바뀌지 않는다. 빌더가 이 조합을 고정해야 하는 이유다.

근거
- [소스] `src/modules/commander/Commander.cpp` 746행:
  ```
  if (((cmd.target_system != _vehicle_status.system_id) && (cmd.target_system != 0))
      || ((cmd.target_component != _vehicle_status.component_id) && (cmd.target_component != 0))) {
      return false;
  ```
  2677행 `command_ack.target_system = cmd.source_system; command_ack.target_component = cmd.source_component;`
  1561행 `cmd.source_component >= COMPONENT_MODE_EXECUTOR_START(1000) ? ModeExecutor : User`.
  DO_SET_MODE 분기: `if (main_ret != TRANSITION_DENIED) cmd_result = ACCEPTED` (desired_nav_state가 MAX여도 ACCEPTED).
  NAV_LAND: `const bool force = true;`.
- [소스] `UserModeIntention.cpp`: `bool always_allow = force || !isArmed();` 시동 전에는 어떤 모드든 허용, 시동 후에는
  `canRun` 검사(Offboard는 offboard 신호가 있어야 함).
- [소스] `px4_custom_mode.h`: MAIN_MODE MANUAL=1, ALTCTL, POSCTL, AUTO=4, ACRO, OFFBOARD=6. SUB_MODE_AUTO READY=1,
  TAKEOFF=2, LOITER=3, MISSION=4, RTL=5, LAND=6.
- [소스] `navigator_main.cpp` 598행 이하(TAKEOFF: param5/6 비유한값이면 현재 위치, `rep->current.alt = cmd.param7`),
  `takeoff.cpp` 184-199행(param7 비유한값이면 MIS_TAKEOFF_ALT, 현재 고도보다 낮으면 현재 고도).
- [실측] probe.py 결과(시동 해제 상태, sysid 2, compid 1):
  ```
  T0 {"status_sysid": 2, "status_compid": 1, "nav_state": 4, ...}
  E1 wrong target 3 {"ack": null, "nav_state": 4, "arming_state": 1}
  E2 arm tsys0 ts0 {"ack": {"result": 0, "target_system": 254, "target_component": 1, "from_external": false}, "nav_state": 4, "arming_state": 2}
  E3 disarm tsys2 simtime {"ack": {"result": 0, ...}, "arming_state": 1}
  E4 set offboard no stream {"ack": {"result": 0, ...}, "nav_state": 14, "arming_state": 1}
  E8 set AUTO_LOITER {"ack": {"result": 0, ...}, "nav_state": 4}
  E9 NAV_LAND disarmed {"ack": {"result": 0, ...}, "nav_state": 18}
  E10 NAV_RTL disarmed {"ack": {"result": 0, ...}, "nav_state": 5}
  E12 source_component 1000 {"ack": {"result": 0, "target_system": 254, "target_component": 1000, ...}}
  ```
  E4: 시동 전에는 setpoint 스트림 없이도 Offboard로 바뀐다(UserModeIntention의 always_allow). 그래서 "set_mode
  ACCEPTED"는 Offboard 진입 준비의 증거가 아니다. 시동 후 Offboard 요청이나 Offboard 상태에서의 arm에는 신호가 필요하다
  (소스 근거, 시동 상태는 미실측). E5(base_mode 0)는 이미 14인 상태에서 시험해 nav_state로는 구별되지 않았고, 소스 근거만 있다.
  check_px4.py S3(2026-11-06 이후 통과 기록)의 조합(target 2, comp 1, source 254/1, from_external true, 노드 시각)도 같다.

## P4. timestamp

결론
- PX4가 /fmu/in 메시지를 받을 때 `timestamp`(와 `timestamp_sample`)는 이렇게 처리된다.
  - 0이면 PX4가 수신 시각(hrt_absolute_time)으로 채운다.
  - 0이 아니면 `min(timestamp - time_offset, hrt_now)`로 바꾼다. time_offset은 uXRCE-DDS timesync가 추정한
    "에이전트 시계 - PX4 시계"이고, `UXRCE_DDS_SYNCT=0`이면 0이다.
- PX4가 /fmu/out으로 보낼 때는 `timestamp + time_offset`이다. 즉 현재 설정(SYNCT 기본값 1)에서는 out 메시지의
  timestamp가 sim 시간이 아니라 에이전트 컨테이너의 벽시계(UNIX epoch 마이크로초)다.
- SITL lockstep에서 PX4 hrt는 gz sim 시간 그 자체다(gz_bridge가 /clock 콜백마다 CLOCK_MONOTONIC을 sim 시간으로 설정).
- 그래서 use_sim_time 노드가 노드 시계(sim 시간)를 timestamp에 넣으면, SYNCT=1에서는 `작은 값 - epoch 크기 offset`이
  uint64로 언더플로해 min에 걸려 "지금"이 된다. 동작은 하지만 우연이고, 오래된 메시지 판정(COM_OF_LOSS_T)이 timestamp로는
  불가능해진다(수신 시각 기준이 된다).
- check_px4.py와 PX4 offboard 예제의 "노드 시계" 방식은 use_sim_time=false(노드 시계 = 벽시계 = 에이전트 시계)일 때만 의도대로 맞는다.

선택지 (6단계 use_sim_time 결정과 맞물림)
- A안: SYNCT=1 유지. out timestamp는 벽시계. idsim은 /fmu/in에 timestamp 0을 보낸다(PX4가 수신 시각으로 채움).
  use_sim_time과 무관하게 안전하다. 대신 PX4 out timestamp를 /clock과 비교하면 안 되고, rosbag 리플레이에서 메시지 안 시각이
  벽시계로 남아 sim 시간 축과 어긋난다.
- B안(권장): SITL 파라미터에 `UXRCE_DDS_SYNCT=0`을 넣는다. out timestamp = PX4 hrt = gz sim 시간(마이크로초)이 되어
  /clock, use_sim_time 노드 시계, ULog 시각이 같은 축에 놓인다. idsim은 /fmu/in에 노드 시계(sim 시간, us)를 넣고, PX4가
  그 값을 그대로 써서 오래된 setpoint 판정도 정상 동작한다. Phase 2의 ULog 정렬 오프셋이 시뮬레이션에서 정확히 0이 된다.
  단점: 실기체나 sim이 아닌 환경에서는 다시 timesync가 필요하다(그때 파라미터만 되돌린다). timesync_status 토픽이 나오지 않는다.
- 어느 안이든 idsim_common 빌더는 timestamp를 내부에서 정하지 말고 호출자가 넘기게 한다(`uint64_t timestamp_us` 인자 또는
  시계 주입). 정책은 6단계 노드와 interface.md가 정한다. SITL 파라미터는 내 소유이므로 B안이 채택되면 내가
  `config/px4/sitl_params.env`에 넣고 S2-S4로 회귀 확인한다.

근거
- [소스] `Tools/msg/templates/ucdr/msg.h.em`:
  ```
  serialize:   const uint64_t timestamp_adjusted = topic.timestamp + time_offset;
  deserialize: if (topic.timestamp == 0) topic.timestamp = hrt_absolute_time();
               else topic.timestamp = math::min(topic.timestamp - time_offset, hrt_absolute_time());
  ```
- [소스] `uxrce_dds_client.cpp` `on_time`: `session->time_offset = -timesync->offset() * 1000;`,
  `on_time_no_sync`: `session->time_offset = 0;`. `module.yaml` UXRCE_DDS_SYNCT default 1, reboot_required.
- [소스] `src/modules/simulation/gz_bridge/GZBridge.cpp` 331-346행 `clockCallback`: 첫 콜백에 CLOCK_REALTIME, 이후
  `px4_clock_settime(CLOCK_MONOTONIC, &ts)` (ts = gz sim 시간).
- [소스] `HealthAndArmingChecks/checks/offboardCheck.cpp`:
  `data_is_recent = hrt_absolute_time() < offboard_control_mode.timestamp + COM_OF_LOSS_T * 1_s`.
- [실측] SYNCT=1(현재 설정), probe.py T0:
  ```
  "status_ts": 1794286860586490, "clock_us": 77780000, "wall_us": 1794286861083987, "node_now_us": 77780000,
  "ts_status": {"estimated_offset": -1794286783282490, ...}
  ```
  status_ts는 벽시계 epoch(us), /clock은 77.78 s. status_ts + estimated_offset = 77,304,000 us로 sim 시간과 같은 축.
- [실측] SYNCT=0(컨테이너 안에서 `uxrce_dds_client stop`, `param set UXRCE_DDS_SYNCT 0`, `start -t udp -p 8893 -n px4_1`), probe2.py:
  ```
  T0 {"status_ts": 180516000, "clock_us": 180520000, ..., "est_offset": null}
  M zero    [false x6]   (offboard_control_signal_lost)
  M sim     [false x6]
  M sim-2s  [true x6]    <- 2초 묵은 timestamp를 PX4가 손실로 판정
  M wall    [false x6]
  M wall-2s [false x6]   <- 벽시계 값은 min에 걸려 지금이 되므로 묵은 것을 못 잡음
  M stopped True
  ```
  SYNCT=1로 되돌려 같은 시험:
  ```
  M zero [false x6], M sim [false x6], M sim-2s [false x6] (언더플로 -> 지금), M wall [false x6], M wall-2s [true x6]
  ```
  즉 timestamp가 의미를 가지려면 "보내는 시계"와 "PX4 쪽 시계 축"이 같아야 한다. SYNCT=0 + sim 시간, 또는 SYNCT=1 + 벽시계.
  시험 후 SYNCT를 1로 되돌리고 스택을 내렸다(파라미터는 컨테이너 안에서만 바꿨다).
- 부수 관측 [실측]: 시동 해제 상태에서는 스트림을 끊어도 nav_state가 14로 남았다(E7, 4초). failsafe 동작은 시동 후에 걸린다(추정, 소스 미확인).

## P5. 좌표 관례

결론 (idsim_common 변환이 맞춰야 할 PX4 쪽 사실)
- VehicleLocalPosition: x 북, y 동, z 아래(NED), m. 원점은 EKF2 시작 시 기체 위치(스폰 지점)이고 월드 원점이 아니다.
  원점의 WGS84 좌표는 `ref_lat`, `ref_lon`(deg, float64), `ref_alt`(AMSL m, float32), 유효 여부는 `xy_global`, `z_global`,
  설정 시각 `ref_timestamp`. `heading`은 NED 기준 yaw(rad, -pi..pi, 북 0, 시계방향 양). 추정치 리셋은 `*_reset_counter`와
  `delta_*`로 알려진다(1b 추종에서 setpoint 점프 원인).
- VehicleAttitude.q: Hamilton, 순서 (w, x, y, z), "FRD 기체 -> NED 지구" 회전(벡터를 FRD에서 NED로 옮기는 회전).
  VehicleOdometry.q도 같은 관례(pose_frame NED일 때).
- TrajectorySetpoint: 위치, 속도, 가속도 모두 로컬 NED(위 원점). `yaw`는 NED yaw(rad, -pi..pi, 북 0, 시계방향 양),
  `yawspeed`는 NED z축(아래) 회전 rad/s. NaN은 "그 항목을 제어하지 않음". 6단계 위치 제어는 position 유한값,
  velocity/acceleration NaN, yaw는 유한값(현재 heading 유지) 권장. yaw NaN은 (추정) 위치 제어기가 yaw를 고정하지 않는다.
- ENU yaw 변환: `yaw_enu = pi/2 - yaw_ned`(그리고 -pi..pi로 감기). 위치: (x_e, y_e, z_e) = (y_n, x_n, -z_n).
- 기체 축 FRD <-> FLU: y, z 부호 반전(x축 기준 pi 회전).
- 완전한 자세 변환(PX4 q_ned_frd -> ROS q_enu_flu)은 `q_enu_flu = Q_NED_ENU * q_ned_frd * Q_FRD_FLU` 두 번의
  정적 회전이 필요하다. frame_transforms로는 `ned_to_enu_orientation(baselink_to_aircraft_orientation(q))` 순서다
  (transform_orientation이 NED<->ENU는 왼쪽 곱, AIRCRAFT<->BASELINK는 오른쪽 곱). 한쪽만 하면 틀린다.
- px4_ros_com frame_transforms 호환: 이 라이브러리는 px4_msgs에 의존하지 않는다(include는 Eigen, geometry_msgs,
  sensor_msgs만). 그러므로 "v1.17.0 호환"은 API 문제가 아니라 관례 문제이고, 관례(배열 순서 w,x,y,z, NED_ENU_Q =
  euler(pi, 0, pi/2), 위치는 x<->y 교환 후 z 반전)는 PX4 메시지 정의와 맞다. 남은 위험은 ros-ws 이미지에 이미 빌드된
  `libframe_transforms.so`를 링크하는지 소스 복사인지의 빌드 문제뿐이다(ros2-engineer 판단).
- 1b 주의(기존 미해결 항목 재확인): 월드 ENU(TargetState) -> 기체 NED setpoint에는 월드 원점과 기체 EKF 원점의 차이가
  필요하다. 단일 기체 6단계는 로컬 NED만 쓰므로 무관하다. 변환 API에 "원점 오프셋"을 넣을 자리만 남겨 두기를 권한다.

근거
- [소스] `msg/versioned/VehicleLocalPosition.msg` 1-2행 "Fused local position in NED. The coordinate system origin is the
  vehicle position at the time when the EKF2-module was started.", 15-17행 x North, y East, z Down, 42행 heading,
  51-57행 ref_*.
- [소스] `msg/versioned/VehicleAttitude.msg` 2행 "Hamilton convention, and the order is q(w, x, y, z)", 10행 "Quaternion rotation
  from the FRD body frame to the NED earth frame".
- [소스] `msg/versioned/TrajectorySetpoint.msg` "Trajectory setpoint in NED frame ... setting a value to NaN means the state
  should not be controlled ... yaw # euler angle of desired attitude in radians -PI..+PI ... yawspeed # angular velocity around NED frame z-axis".
- [이미지] `/opt/px4_ws/src/px4_ros_com/src/lib/frame_transforms.cpp`: `array_to_eigen_quat` -> `Eigen::Quaterniond(q[0], q[1], q[2], q[3])`
  (w 먼저), `transform_orientation` NED_TO_ENU `out = NED_ENU_Q * q`, AIRCRAFT_TO_BASELINK `out = q * AIRCRAFT_BASELINK_Q`,
  `transform_static_frame` NED_TO_ENU = 반사 XY 교환 * Z 반전.
- [실측] T0 lpos: `x -0.023, y 0.019, z 0.009, heading 1.279, ref_lat 37.5665002, ref_lon 126.9780001, ref_alt 38.219,
  xy_valid/z_valid/xy_global/z_global true`. ref_lat/lon이 fleet.yaml 원점(서울시청)과 같은 것은 기체 pose가 (0,0)이기 때문이며,
  ref_alt 38.22는 navsat 높이(check_px4.py 주석의 0.22 m)가 들어간 값이다.

## P6. QoS

결론
- PX4 발행자(/fmu/out, 에이전트가 만든 DataWriter): BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST.
- PX4 구독자(/fmu/in, DataReader): BEST_EFFORT, VOLATILE, KEEP_LAST, depth = uORB 큐 크기 x 2.
- idsim 구독 프로필: BEST_EFFORT, VOLATILE, KEEP_LAST, 작은 depth(`rclcpp::SensorDataQoS()`와 같은 값, depth 5).
  판정 QoS를 sensor_data 하나로 정한 2026-11-06 결정, check_px4.py와 일치한다.
  TRANSIENT_LOCAL 구독은 권하지 않는다. (추정) Fast DDS 에이전트가 BEST_EFFORT writer의 이력을 늦게 붙은 reader에게
  재전송한다는 보장이 없고, 된다 해도 vehicle_command_ack에서 이전 명령의 ack가 들어오는 부작용이 더 크다. 상태 토픽은 5 Hz 이상이라 이력이 필요 없다.
- idsim 발행 프로필(/fmu/in): BEST_EFFORT, VOLATILE, KEEP_LAST depth 1-5. RELIABLE writer도 BEST_EFFORT reader와 매칭되지만
  얻는 것이 없고 큐가 차면 지연이 생긴다. 손실은 20 Hz 재발행(setpoint)과 ack 대기 재전송(명령, 0.5 s 간격)으로 메운다.
- 골든 qos/의 `depth=1`은 소스 값(writer depth 0)이 아니다. DDS 디스커버리는 history/depth를 전파하지 않으므로
  (추정) rmw가 원격 엔드포인트에 기본값을 보여 주는 것이다. 골든 비교에서 history/depth는 계약 값으로 쓰지 말자고 제안한다.
  reliability와 durability만 계약이다.

근거
- [소스] `utilities.hpp` `create_data_writer`: `.durability = UXR_DURABILITY_TRANSIENT_LOCAL, .reliability = UXR_RELIABILITY_BEST_EFFORT,
  .history = UXR_HISTORY_KEEP_LAST, .depth = 0`. `create_data_reader`: `.durability = UXR_DURABILITY_VOLATILE,
  .reliability = UXR_RELIABILITY_BEST_EFFORT, .history = UXR_HISTORY_KEEP_LAST, .depth = queue_depth`,
  `dds_topics.h.em`: `queue_depth = orb_get_queue_size(...) * 2`.
- [골든] `qos/fmu/out/vehicle_status_v1.txt` 등 29개 모두 `reliability=BEST_EFFORT durability=TRANSIENT_LOCAL history=KEEP_LAST depth=1`.
- [실측] `ros2 topic info -v /px4_1/fmu/in/vehicle_command` (PX4 reader):
  ```
  Topic type hash: INVALID
  Endpoint type: SUBSCRIPTION
    Reliability: BEST_EFFORT
    History (Depth): KEEP_LAST (1)
    Durability: VOLATILE
  ```
  offboard_control_mode도 같다. 소스의 reader depth는 1이 아닌데 1로 보이므로 depth 표시는 신뢰하지 않는다.

---

## ros2-engineer 설계와 충돌할 수 있는 지점

1. 매핑 키. "(논리 이름, 타입)"만으로는 `mode_completed`(in, out 둘 다 ModeCompleted)가 겹친다. 방향을 키에 넣어야 한다.
   같은 타입이 여러 이름에 쓰이므로(VehicleCommand x 2, VehicleOdometry x 3 등) 타입에서 이름을 역으로 찾는 API는 금지.
2. 버전 파생의 "상수 없음" 처리. OffboardControlMode 등은 MESSAGE_VERSION이 없다. `T::MESSAGE_VERSION`을 직접 쓰면 컴파일이
   깨진다. PX4와 같은 SFINAE(없으면 0)가 필요하고, 0이면 접미사 없음(`_v0` 아님).
3. 이름과 타입이 다른 항목(vehicle_gps_position = SensorGps 등). 논리 이름을 타입명에서 자동 생성(snake_case)하면 틀린다.
   (방향, 논리 이름) -> 타입 표는 사람이 쓰고, 골든 65개 전수 대조로 검증하는 구조를 제안한다.
4. 골든 QoS의 history/depth. 골든에는 depth=1이 있지만 소스 값은 writer 0, reader 큐 x 2다. QoS 프로필 단위 테스트가 골든의
   depth를 계약으로 대조하면 근거 없는 값을 고정하게 된다. reliability, durability만 대조하자.
5. timestamp 정책. 빌더가 내부에서 `now()`를 넣으면 use_sim_time과 SYNCT 조합에 따라 PX4가 값을 버리거나(언더플로 클램프)
   오래된 판정이 무력화된다. 빌더는 timestamp를 인자로 받고, 정책(B안 SYNCT=0 + sim 시간, 또는 A안 0)은 6단계에서 정한다.
   B안은 SITL 파라미터 변경이라 px4-engineer가 구현하고 스모크로 회귀 확인한다. 6단계 use_sim_time 결정 전에 architect가 정해 주기 바란다.
6. PX4 out 메시지의 timestamp 해석. 현재 설정(SYNCT=1)에서 out timestamp는 벽시계 epoch이다. idsim_common이나 판정 코드가
   msg.timestamp를 노드 시계(/clock)와 비교하는 유틸(신선도 검사 등)을 두면 틀린다. B안이면 같은 축이 된다.
7. target_system 매핑. 네임스페이스 `px4_N` -> target_system N + 1을 idsim_common이 소유한다는 데는 동의한다. 다만 기본값 0
   (브로드캐스트)을 허용하는 API는 두지 말자는 것이 내 의견이다. 0은 PX4가 받아들여 매핑 오류를 숨긴다.
   N = 0(S1, 수동 실행)의 네임스페이스 없음과 sysid 1도 해석기가 받아야 한다(check_px4.py의 `--ns ""` 경로).
8. 명령 성공 판정. 빌더에 "ack ACCEPTED = 성공" 헬퍼를 두면 DO_SET_MODE에서 거짓 양성이 나온다(시동 전 Offboard는 신호 없이도
   ACCEPTED, base_mode 누락도 ACCEPTED). 모드 명령의 성공은 nav_state 확인까지가 한 단위이며, 그 상태기는 idsim_mission(내 접점)에
   두고 idsim_common은 ack 거르기 조건(command, target_system, target_component)까지만 제공하는 경계를 제안한다.
9. 좌표 변환 범위. frame_transforms는 px4_msgs 비의존이라 "v1.17.0 호환 확인"은 관례 단위 테스트로 충분하다. 자세 변환은 NED<->ENU와
   FRD<->FLU 둘 다 적용해야 하며 곱 순서가 다르다. 위치 변환 API에 EKF 원점 오프셋 자리를 남겨 두지 않으면 1b(track_entity)에서 API를 바꿔야 한다.
10. QoS 프로필 이름. 구독, 발행 모두 sensor_data 계열 하나로 충분하다. 발행에 RELIABLE이나 TRANSIENT_LOCAL을 쓰는 별도 프로필을
    만들 근거는 없다.

## 확인하지 못한 것 (추정으로 남김)

- 시동 상태에서 신호 없이 Offboard 요청 시 TEMPORARILY_REJECTED가 오는지(소스상 그렇다, 미실측). 6단계 통합 테스트 개발 중 확인.
- Commander 외 모듈이 낸 명령의 ack가 /fmu/out/vehicle_command_ack에 섞이는 빈도.
- Fast DDS 에이전트의 TRANSIENT_LOCAL + BEST_EFFORT writer가 늦게 붙은 TRANSIENT_LOCAL reader에게 이력을 주는지.
- SYNCT=0에서 timesync_status가 발행되지 않는 이유(3초 동안 수신 없음만 관측).
- uxrce_dds_client 소스에 `vehicle_command` 서비스(replier, `rq/<ns>/fmu/vehicle_commandRequest`)가 있으나 이 스택의
  `ros2 service list`에는 fmu 서비스가 보이지 않았다. 6단계는 토픽 경로만 쓰므로 영향 없다.
