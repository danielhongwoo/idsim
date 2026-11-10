# 1a 5단계 idsim_interfaces 의견 (ops-service-engineer, 2026-11-10)

관점: `VehicleState`의 생산자(Phase 2 Telemetry Collector)이자 `VehicleState`, `ExecuteMission`의 소비자(Phase 3 Fleet Manager, gRPC, Rust 게이트웨이, Phase 2 WebSocket 어댑터).

근거로 읽은 것: `docs/roadmap.md` 1a 5번, 1b 1번, Phase 2 1-5번, Phase 3 2-7번. `docs/architecture.md`의 전체 architecture, 기체 식별 절, 인터페이스 계약 절. `docs-for-agent/progress.md` 결정 기록 (q)-(x). golden `tests/fixtures/px4/v1.17.0/topics.txt`와 `idsim_common`의 `detail/px4_topic_list.inc`. 스택과 docker는 실행하지 않았다. px4_msgs 필드 이름과 rosbag2 동작에 관한 서술 중 저장소에서 확인하지 못한 것은 "추정"으로 표시했다.

## 먼저 짚을 전제 두 가지

1. Collector와 Executor는 경계 어댑터다. 운용 서비스 레이어에 있지만 `/fmu/out`을 읽는 유일한 두 노드라 PX4를 안다. "운용 서비스는 PX4를 모른다"는 원칙은 Fleet Manager, gRPC, 게이트웨이, 브라우저에 적용하고, 그 경계선이 `VehicleState`다. 따라서 `VehicleState`에는 PX4 고유 값(nav_state 원값, PX4 timestamp, `_v1` 같은 토픽 사정)이 하나도 없어야 하고, PX4 -> 추상 값 변환표는 Collector 한 곳에만 둔다. Executor는 지금처럼 `vehicle_status`를 직접 본다(결정 기록 (u)의 nav_state 상태기).
2. Phase 3 재배분 시험은 "px4 컨테이너 강제 종료"다. 이때 같은 기체의 Collector와 Executor는 ros-ws 컨테이너에서 살아 있다. Collector가 마지막 값을 5 Hz로 계속 내보내면 Fleet은 `VehicleState` 수신 주기로 이탈을 감지할 수 없다. 이 시나리오가 `VehicleState`의 시각 필드와 링크 상태 필드를 결정한다(아래 1-5).

## 1. VehicleState.msg

### 권고안

```
# idsim_interfaces/msg/VehicleState.msg
# 기체 요약 상태. Telemetry Collector가 기체마다 5 Hz로 발행한다.
# 좌표계: map은 world.origin을 원점으로 하는 ENU(TargetState와 같은 프레임).
# NaN과 Inf는 넣지 않는다. 값이 없으면 *_valid를 false로 두고 값은 0이다.

# 식별
string vehicle_id            # 불투명 key. 기체 네임스페이스에서 앞의 "/"를 뗀 값(예: px4_1). params로 받는다
uint8  system_id             # 대조를 통과한 MAVLink system id. 표시와 진단용

# 시각 (모두 ROS 시각, use_sim_time이면 /clock)
builtin_interfaces/Time stamp           # 이 메시지를 만든 시각
builtin_interfaces/Time last_status_rx  # 비행제어 상태를 마지막으로 받은 시각
bool link_ok                             # stamp - last_status_rx <= link_timeout (Collector params)

# 상태 (우리 enum. 0은 항상 UNKNOWN)
uint8 ARMING_UNKNOWN=0
uint8 ARMING_DISARMED=1
uint8 ARMING_ARMED=2
uint8 arming

uint8 MODE_UNKNOWN=0
uint8 MODE_MANUAL=1          # 조종사 입력 계열 전부
uint8 MODE_HOLD=2
uint8 MODE_OFFBOARD=3
uint8 MODE_TAKEOFF=4
uint8 MODE_LAND=5
uint8 MODE_RTL=6
uint8 MODE_AUTO_OTHER=7      # 위에 없는 자동 모드(미션, follow 등)
uint8 MODE_OTHER=255         # 변환표에 없는 값. Collector가 경고 로그를 남긴다
uint8 flight_mode

bool landed

# 건강
bool  failsafe_active
uint32 WARN_LOCAL_POSITION_INVALID=1
uint32 WARN_GLOBAL_POSITION_INVALID=2
uint32 WARN_BATTERY_LOW=4
uint32 WARN_BATTERY_CRITICAL=8
uint32 WARN_OFFBOARD_SIGNAL_LOST=16
uint32 WARN_PREFLIGHT_CHECK_FAILED=32
uint32 warnings              # 위 비트의 OR. 비트는 추가만 한다

# 위치와 속도 (map ENU, m와 m/s), 방위(ENU yaw, rad, 동쪽 0, 반시계 양)
bool    position_valid
float64 pos_e
float64 pos_n
float64 pos_u
bool    velocity_valid
float32 vel_e
float32 vel_n
float32 vel_u
bool    yaw_valid
float32 yaw

# 지리 좌표 (WGS84, 도와 m AMSL). 브라우저 지도용
bool    geodetic_valid
float64 lat_deg
float64 lon_deg
float64 alt_amsl_m

# 배터리 (첫 번째 배터리)
bool    battery_valid
float32 battery_remaining    # 0.0-1.0
float32 battery_voltage_v
```

세부 권고.

1-1. 기체 식별은 문자열 `vehicle_id` 하나를 주 key로 쓴다. 값은 Collector가 params로 받은 네임스페이스에서 "/"만 뗀 것이고 Fleet은 이를 불투명 문자열로 다룬다. 기체 번호 N을 정수로 따로 싣지 않는다. 정수가 있으면 소비자가 "N+1 = sysid", "/px4_N" 같은 파생을 다시 하고 싶어지는데 결정 기록 (u)가 바로 그것을 금지했다. Fleet이 Executor의 action 이름을 찾을 때도 `vehicle_id`를 네임스페이스로 그대로 쓴다(`/<vehicle_id>/execute_mission`). `system_id`는 대조가 끝난 값만 싣고, Collector는 대조가 Match가 되기 전과 어긋난 동안 `VehicleState`를 발행하지 않는다. 그래야 Fleet 레지스트리에 신원 미확인 기체가 들어오지 않는다. 값 "px4_1"에 PX4라는 글자가 남지만 Fleet은 내용을 해석하지 않으므로 경계 위반으로 보지 않는다.

1-2. arming과 nav_state는 우리 enum으로 추상화한다. 근거: (a) Fleet의 배분 규칙은 "가용인가"만 묻고 PX4의 nav_state 22개 남짓을 알 필요가 없다. (b) PX4 태그를 올리면 nav_state 값이 바뀔 수 있는데(추정. v1.14 이후 몇 값이 폐지된 이력이 있다고 알고 있으나 원문 확인 안 함) 그 영향이 Collector 변환표의 단위 테스트에서 멈추고 proto, JSON, 브라우저로 번지지 않는다. (c) 실기체 교체 원칙. 변환표는 Collector 안의 `switch`이고, 단위 테스트는 px4_msgs의 `NAVIGATION_STATE_*` 상수 전부를 넣어 UNKNOWN이 아닌 값으로 떨어지는지(OTHER 허용) 확인한다. 원값은 싣지 않는다. 디버깅에는 rosbag의 `vehicle_status`가 있다. 다만 우리 enum의 값 목록(위의 MANUAL, HOLD 등 묶음)은 px4-engineer가 nav_state 전체를 보고 확정해야 한다. 위 목록은 Fleet이 필요로 하는 최소 구분이다.

1-3. 위치는 map ENU(TargetState와 같은 프레임)와 WGS84 둘 다 싣는다.
  - map ENU가 필요한 이유: Fleet의 배분 규칙 "표적에 가장 가까운 기체"는 `TargetState`(ENU, Gazebo 월드 프레임)와 거리를 잰다. PX4 `vehicle_local_position`의 NED는 기체마다 EKF 원점이 달라(기체마다 스폰 위치가 다르다) 기체끼리도, 표적과도 바로 비교할 수 없다. 기체 로컬 NED를 그대로 실으면 모든 소비자가 기체별 원점을 알아야 하므로 Collector에서 한 번 map 프레임으로 옮긴다.
  - WGS84가 필요한 이유: Phase 2 페이지가 "지도 위에 기체 위치"를 찍는다.
  - 계산 방법 권고: map ENU 위치는 `vehicle_global_position`의 위경도고도를 `world.origin` 기준 local tangent plane으로 변환하고(ECEF 경유), 속도는 `vehicle_local_position`의 NED 속도를 축 교환으로 ENU로 바꾼다(로컬 NED도 진북 정렬이므로 회전 없이 맞다). yaw는 `heading`(NED)을 `idsim_common`의 yaw 변환으로 바꾼다. 변환 함수는 ros2-engineer 소유 `idsim_common`에 더하는 것을 권한다(결정 기록 (q)의 "원점 이동은 1b에서 별도 함수로"와 같은 자리).
  - 전제와 미해결: (a) Gazebo 월드 프레임 원점이 `world.origin`이고 축이 동쪽, 북쪽에 정렬되어 있다는 것(set_spherical_coordinates의 heading 0. sim-engineer 확인 필요, 추정). (b) `world.origin`은 현재 선택 항목이다. map 프레임이 계약이 되면 Collector params에 원점이 반드시 있어야 하므로 Phase 2부터 `world.origin`을 필수로 할지 architect와 devops-engineer가 정해야 한다.

1-4. 유효성은 `*_valid` 불리언으로 표현하고 NaN을 쓰지 않는다. 근거: JSON에는 NaN이 없다. serde_json은 NaN을 null로 쓰고(추정, 기본 동작으로 알고 있음), Protobuf JSON mapping은 문자열 "NaN"으로 쓴다. 같은 값이 어댑터마다 다르게 나가면 Phase 2에서 고정한 WebSocket 스키마를 Phase 3 게이트웨이가 지키지 못한다. PX4의 `xy_valid`, `v_xy_valid` 등을 그대로 반영한다.

1-5. 시각은 셋. `stamp`(생성 시각), `last_status_rx`(비행제어 상태를 마지막으로 받은 ROS 시각), `link_ok`. 수신 시각은 PX4 timestamp가 아니라 Collector의 ROS 시계로 잰 값이다. SITL에서는 둘이 같은 축이지만(결정 기록 (t)) 실기체에서는 SYNCT를 되돌리므로 PX4 timestamp를 싣는 순간 Fleet이 비행제어 시계를 알게 된다. Fleet의 이탈 판정은 두 단계로 둔다: `VehicleState` 미수신 T초(Collector 사망) 또는 `link_ok == false`가 T초 지속(비행제어 사망). 재배분 nightly 시험은 후자로 잡힌다. Collector는 `vehicle_status`를 한 번도 받지 못했으면 발행하지 않고, 받은 뒤 끊기면 마지막 값과 `link_ok=false`로 계속 발행한다(Fleet과 브라우저가 "끊긴 기체"를 보여 줄 수 있게).

1-6. `std_msgs/Header`를 쓰지 않는다. `frame_id`는 프레임이 계약으로 고정되어 의미가 없고, proto에 대응 필드를 만들어야 한다. Lichtblick 플롯은 Header 없이도 숫자 필드를 그린다.

1-7. 건강 상태는 `failsafe_active`(vehicle_status의 failsafe) 하나와 경고 bitmask로 둔다. `failsafe_flags`의 수십 개 필드를 그대로 옮기지 않고 Fleet의 가용 판정에 쓰이는 것만 비트로 묶는다. bitmask는 새 비트를 더해도 구 소비자가 깨지지 않고 proto에서 `uint32` 하나로 대응한다. 어떤 failsafe_flags 필드를 어느 비트로 묶을지는 px4-engineer와 정한다.

1-8. Collector 입력 토픽에 `vehicle_land_detected`를 더할 것을 권한다(Phase 2 1번의 목록에 없다). Fleet의 "가용" 판정에는 지상 대기와 공중 hover를 구분할 `landed`가 필요하다. golden `topics.txt`와 `px4_topic_list.inc`에 `VehicleLandDetected`(Out)가 있으므로 새 기술자는 필요 없다.

1-9. 발행 토픽과 QoS(interface.md와 ros2-engineer 인터페이스). 기체별 네임스페이스 토픽(`/<ns>/vehicle_state`) 대신 공통 절대 토픽 하나(`/fleet/vehicle_state`, 메시지 안의 `vehicle_id`로 구분)를 권한다. ROS 2에는 와일드카드 구독이 없어 네임스페이스별 토픽이면 Fleet이 기체 목록을 미리 알거나 그래프를 훑어야 하고, 그러면 "수신 주기로 자동 발견"이 성립하지 않는다. QoS는 RELIABLE, VOLATILE, KEEP_LAST 10(N대가 한 토픽을 공유하므로 1보다 크게). 레지스트리 타임아웃은 5 Hz의 수 배(예: 2 s, `/clock` 기준)로 Phase 3에서 정한다.

1-10. Protobuf 1:1을 쉽게 하는 형태. 필드는 평평한 원시 타입으로 두고 `geometry_msgs` 같은 외부 패키지 타입을 쓰지 않는다(proto에 거울 타입을 또 만들어야 한다). 시각은 proto에서 `google.protobuf.Timestamp`가 아니라 `builtin_interfaces/Time`을 그대로 본뜬 우리 메시지(`int32 sec`, `uint32 nanosec`)로 받는다. 근거: sim 시간은 0에서 시작해 epoch 의미가 없고, Timestamp의 JSON mapping은 "1970-01-01T00:02:13Z" 같은 RFC 3339 문자열이 되어 브라우저 쪽 비교가 번거롭다. ROS `uint8` 상수는 proto3 enum으로 옮기고 0을 UNSPECIFIED(=UNKNOWN)로 맞춘다. 경고 비트는 enum이 아니라 `uint32`.

## 2. ExecuteMission.action

### 권고안

```
# Goal
string vehicle_id                      # 받는 쪽이 자기 vehicle_id와 다르면 VEHICLE_ID_MISMATCH로 중단
uint32 attempt                         # 같은 mission_id의 몇 번째 배분인가. 1부터. 재배분마다 +1
idsim_interfaces/Mission mission
---
# Result
uint8 OUTCOME_UNKNOWN=0
uint8 OUTCOME_SUCCEEDED=1
uint8 OUTCOME_FAILED=2
uint8 OUTCOME_CANCELED=3
uint8 outcome

uint8 REASON_NONE=0
uint8 REASON_INVALID_MISSION=1         # 검증 실패(항목 필드, 범위)
uint8 REASON_VEHICLE_ID_MISMATCH=2
uint8 REASON_BUSY=3                    # 다른 미션 실행 중
uint8 REASON_NOT_READY=4               # 신원 대조 전, 위치 추정 미수렴, preflight 실패
uint8 REASON_ARM_REJECTED=5
uint8 REASON_MODE_SWITCH_FAILED=6      # Offboard 진입이나 모드 명령이 nav_state로 확인되지 않음
uint8 REASON_ITEM_TIMEOUT=7
uint8 REASON_FAILSAFE=8                # 비행제어가 failsafe로 제어를 가져감
uint8 REASON_EXTERNAL_MODE_CHANGE=9    # 우리가 요청하지 않은 모드 전환(GCS 등)
uint8 REASON_TARGET_LOST=10            # track_entity 중 TargetState 미수신
uint8 REASON_LINK_LOST=11              # 비행제어 상태 미수신
uint8 REASON_INTERNAL=255
uint8 reason
string detail                          # 사람이 읽는 설명. 판정에 쓰지 않는다

string  mission_id
uint32  attempt
uint16  items_completed
uint16  last_item_index                # 마지막으로 실행하던 항목. 시작 전 실패면 0
uint8   final_arming                   # VehicleState.ARMING_* 값
bool    final_landed
---
# Feedback
string  mission_id
uint32  attempt
uint16  item_index                     # 0부터
uint16  item_count
uint8   item_type                      # MissionItem.TYPE_*
uint8 PHASE_PREPARING=1                # 신원 대조, arm, Offboard 진입
uint8 PHASE_EXECUTING=2
uint8 PHASE_SETTLING=3                 # 도달 판정 "N회 연속" 대기
uint8 PHASE_CANCELING=4                # 취소 요청 뒤 HOLD 전환 확인 중
uint8   phase
bool    distance_valid
float32 distance_to_goal_m             # goto, takeoff(고도 차), track_entity(표적까지)
float32 item_elapsed_s                 # 항목 시작 뒤 경과(ROS 시각). loiter의 남은 시간은 소비자가 계산
builtin_interfaces/Time stamp
```

세부 권고.

2-1. 거절 대신 수락 후 중단. ROS 2 action의 goal 거절은 이유를 실어 보낼 수 없다(goal 응답은 accepted 불리언과 시각뿐). Fleet은 BUSY와 INVALID_MISSION을 구분해야 다음 동작(다른 기체로 재시도 vs 미션 자체를 실패 처리)을 정할 수 있으므로, Executor는 goal을 일단 수락하고 바로 `aborted`로 끝내며 result에 reason을 싣는다. action 상태(SUCCEEDED, ABORTED, CANCELED)와 result의 `outcome`이 겹치지만, gRPC와 rosbag 쪽에서는 result만으로 해석할 수 있게 `outcome`을 둔다. 둘의 대응은 Executor 단위 테스트로 묶는다.

2-2. 진행률은 단일 백분율이 아니라 "항목 인덱스 / 항목 수 + 항목 단계 + 목표까지 거리"로 표현한다. track_entity와 loiter는 끝이 거리로 정해지지 않아 백분율이 거짓이 된다. Fleet의 `StreamMissionEvents`는 `item_index`와 `phase`가 바뀔 때만 이벤트를 내고, 거리는 `GetMissionStatus`에서만 보인다. feedback 주기는 2 Hz 이하와 전이 시점으로 충분하다(Fleet 입장의 요구, Executor 구현 비용은 ros2/px4-engineer 판단).

2-3. 취소 의미를 계약에 적는다. "취소되면 Executor는 setpoint 발행을 끊지 않고 HOLD 모드 명령을 보내 nav_state로 확인한 뒤 CANCELED로 끝낸다. 지상이면 disarm 상태를 유지한다." 근거: setpoint를 그냥 끊으면 `COM_OF_LOSS_T` 뒤 `COM_OBL_RC_ACT` fallback으로 넘어가 취소 뒤 기체 동작이 파라미터에 따라 달라진다. HOLD는 `idsim_common` VehicleCommand 빌더에 이미 있다(결정 기록 (u)). 다만 "공중 취소 뒤 HOLD"가 맞는지, LAND나 RTL이어야 하는지는 운용 정책이라 architect가 정하고, 필요하면 goal에 `on_cancel` 필드를 나중에 더한다(추가는 아래 4번 규칙상 허용).

2-4. 재배분에 필요한 것은 `mission_id`와 `attempt` 두 개다.
  - Fleet은 이탈을 감지하면 옛 기체의 goal에 취소를 보내되 그 응답을 기다리지 않고 바로 새 기체에 `attempt+1`로 보낸다. px4가 죽은 기체의 Executor는 HOLD를 확인할 수 없어 취소가 끝나지 않을 수 있다(그때 Executor는 REASON_LINK_LOST로 끝내야 한다).
  - Fleet은 result와 feedback의 `(mission_id, attempt)`가 현재 배분과 다르면 버린다. 옛 기체가 늦게 SUCCEEDED를 보내도 미션 상태가 뒤집히지 않는다.
  - 이탈한 기체가 다시 나타났는데 옛 goal이 아직 살아 있으면 Fleet이 다시 취소한다. 그래서 같은 미션이 두 기체에서 동시에 도는 시간을 줄인다.
  - goal UUID는 action 계층의 것이고 재배분마다 바뀐다. 미션의 정체성은 `mission_id`로, 시도의 정체성은 `attempt`로 둔다. rosbag과 기록물 인덱스에서도 이 둘로 찾는다.

2-5. 실패 사유 코드는 위 표처럼 PX4 용어 없이 둔다(ARM_REJECTED, MODE_SWITCH_FAILED 정도는 비행제어 일반 개념). Fleet의 재배분 정책이 사유로 갈린다: INVALID_MISSION은 재시도하지 않고, BUSY, NOT_READY, LINK_LOST, FAILSAFE는 다른 기체로 재시도할 수 있고, TARGET_LOST는 미션 실패. 이 표는 Phase 3 단위 테스트(test-engineer 인터페이스)의 입력이 된다. 값은 추가만 하고 의미를 바꾸지 않으며 255는 INTERNAL로 고정한다.

2-6. result의 `final_arming`, `final_landed`는 Fleet이 "이 기체를 바로 다시 배분할 수 있는가"를 `VehicleState`가 올 때까지 기다리지 않고 판단하기 위한 것이다. 없어도 동작은 하므로 architect가 줄이고 싶으면 빼도 된다(그때 Fleet은 다음 `VehicleState`를 기다린다).

2-7. 기록물 인덱스와의 인터페이스(logging-engineer 확인 필요). Phase 2 5번 인덱스가 "미션 id, 결과"를 기록물에서 뽑으려면 미션 id가 토픽에 있어야 한다. action의 feedback과 status는 숨김 토픽(`<action>/_action/feedback`, `_action/status`)이라 `--include-hidden-topics`로 기록되지만, goal과 result는 서비스라 Jazzy rosbag2에서는 서비스 introspection을 켜야 기록된다(추정, Jazzy의 서비스 기록 지원 범위를 확인하지 못했다). feedback에 `mission_id`를 넣은 이유 중 하나가 이것이다. 결과와 사유까지 인덱스에 넣으려면 Executor가 미션 시작과 종료 때 일반 토픽으로 이벤트를 내는 `MissionEvent.msg`가 필요할 수 있다. 1a에서 만들지 말고 Phase 2에서 logging-engineer가 필요를 확인하면 추가로 더하는 것을 권한다.

## 3. Mission.msg

### 권고안

```
# idsim_interfaces/msg/Mission.msg
string mission_id                  # 불투명 문자열, [A-Za-z0-9_-] 1-64자. 실행 단위 key
string name                        # 사람이 붙인 이름(YAML의 name). 판정에 쓰지 않는다
builtin_interfaces/Time created    # 미션을 만든 ROS 시각
idsim_interfaces/MissionItem[] items
```

```
# idsim_interfaces/msg/MissionItem.msg (항목 필드는 Executor 소유자들이 정한다. 아래는 소비자 요구만)
uint8 type                         # TYPE_*. setpoint 부류와 모드 명령 부류는 type에서 파생(별도 필드 없음)
... 위치는 map ENU(TargetState, VehicleState와 같은 프레임), target_id, 시간과 반경 등
```

세부 권고.

3-1. `mission_id`는 `Mission.msg`에 두고 goal에는 두지 않는다. Mission이 홀로 기록되거나 로그에 찍혀도 식별되게 하기 위해서다. 발급 주체는 둘이다: Phase 1b의 YAML 직접 실행은 로더가(YAML에 `id`가 있으면 그것, 없으면 `name`과 생성 시각으로 만든다), Phase 3은 Fleet이 `SubmitMission` 때 발급한다. Executor는 내용을 해석하지 않는다.

3-2. "버전"은 미션 내용의 개정 번호로 두지 않는다. Phase 3 API에는 미션 수정이 없고(`SubmitMission`, `AbortMission`뿐) 재배분은 `attempt`로 표현한다. 스키마 버전은 4번에서 다룬다. 실행 중 미션을 바꾸는 기능이 생기면 그때 `revision`을 더한다.

3-3. 배분 제약(요청 기체, 우선순위, 표적 기준점)은 `Mission.msg`에 넣지 않는다. Executor가 쓰지 않는 값이고, gRPC의 `SubmitMissionRequest`(예: `requested_vehicle_id` 선택 필드)와 Fleet 내부 상태에 있으면 된다. "표적에 가장 가까운 기체" 규칙의 기준점은 Fleet이 항목에서 파생한다(첫 track_entity의 표적 현재 위치, 없으면 첫 goto 위치). 이 파생 규칙은 Fleet 단위 테스트로 고정한다.

3-4. 항목의 위치 프레임은 map ENU로 둘 것을 권한다. Fleet이 기준점을 계산할 때 `VehicleState`, `TargetState`와 같은 프레임이면 변환이 필요 없다. 기체 로컬 NED로의 변환은 Executor 안에서 `idsim_common`으로 한다(결정 기록 (q)의 원점 이동 함수). takeoff 고도는 프레임이 아니라 "이륙 지점 위 m"로 두는 편이 자연스럽다(px4/ros2-engineer 판단).

3-5. `MissionItem`은 type + 공통 필드의 평평한 구조를 권한다. ROS msg에는 oneof가 없다. proto 쪽은 oneof로 타입별 메시지를 두는 편이 클라이언트에 낫지만, 그러면 VehicleState와 달리 1:1이 아니다. architecture 문서가 1:1을 요구한 것은 `VehicleState`뿐이므로 Mission은 "평평한 ROS msg <-> oneof proto" 변환을 허용하고, 변환은 같은 `idsim_fleet` 변환 모듈 한 곳에서 하며(VehicleState와 함께) 왕복 테스트를 둔다. 왕복 테스트에서 type에 쓰이지 않는 필드가 0이 아니면 변환이 실패해야 한다.

3-6. YAML 로더와의 관계. 미션의 사람용 정식 형식은 YAML 하나다. 진입점은 둘이 된다: (a) Phase 1b의 C++ YAML 로더 -> `Mission.msg`, (b) Phase 3의 Python 클라이언트 CLI가 같은 YAML -> proto -> Fleet -> `Mission.msg`. 검증 규칙이 두 곳에서 갈라지지 않도록 권위 있는 의미 검증은 하나의 ROS 비의존 C++ 함수(예: `idsim_mission`의 라이브러리 타깃 `validate(const Mission&)`)로 두고, Executor는 실행 전에, Fleet은 `SubmitMission` 수리 전에 같은 함수를 부른다. Python CLI는 구문만 확인하고 의미 검증은 서버에 맡긴다. 같은 YAML fixture를 두 경로로 넣어 같은 `Mission.msg`가 나오는지 확인하는 테스트를 둔다(test-engineer 인터페이스). `idsim_interfaces`는 rosidl 전용 패키지로 두고 코드를 넣지 않는다.

## 4. 버전과 호환

### 권고안

4-1. 먼저 사실 하나. ROS 2 msg의 CDR 직렬화는 위치 기반이라 Protobuf처럼 "필드 추가는 구버전과 호환"이 성립하지 않는다. 필드를 하나 더하면 구버전 노드와 새 노드는 서로의 메시지를 해석할 수 없고, Jazzy는 타입 hash(RIHS01)가 달라진다(추정: hash 불일치 때 CycloneDDS가 엔드포인트를 매칭하지 않는지 경고만 하는지는 확인하지 못했다). 한 스택은 한 이미지에서 빌드한 노드만 돌므로 실행 중 혼재는 문제가 아니고, 실제 위험은 (a) 옛 기록물 재생, (b) 스택 밖 클라이언트(브라우저, gRPC 클라이언트)다. 규칙은 이 둘을 막는 데 맞춘다.

4-2. ROS msg 규칙.
  - 필드는 끝에 추가만 한다. 기존 필드의 이름, 타입, 의미, 단위를 바꾸지 않는다. 바꿔야 하면 새 이름으로 추가하고 옛 필드는 `# deprecated` 주석과 함께 남긴다.
  - 상수 값은 재사용하지 않는다. enum 값과 경고 비트는 추가만 한다. 소비자는 모르는 enum 값을 UNKNOWN 또는 OTHER로 다룬다.
  - "예약 필드"를 미리 두지 않는다. 위치 기반 직렬화라 빈 자리를 미리 잡아도 호환이 생기지 않는다.
  - `idsim_interfaces`의 `package.xml` 버전을 계약 변경마다 올리고 결정 기록에 남긴다.

4-3. 기록물 규칙(logging-engineer 인터페이스). `replay` 프로필은 PX4 원천 토픽(`/px4_N/fmu/out/*`)과 `/clock`, `TargetState`만 재생하고 기록물 안의 `VehicleState`처럼 우리 노드가 만든 파생 토픽은 재생하지 않는다(Collector가 재생 입력으로 다시 만든다). 이러면 `VehicleState`가 바뀌어도 replay CI의 fixture 기록물이 깨지지 않고, 재생된 `VehicleState`와 새로 만든 `VehicleState`가 한 토픽에 겹치는 문제도 없다. 기록물의 MCAP에는 스키마가 함께 들어가므로 옛 `VehicleState`는 Lichtblick으로 열람은 된다.

4-4. Protobuf 규칙.
  - 패키지에 주 버전을 넣는다(`idsim.fleet.v1`, 파일은 `proto/idsim/fleet/v1/*.proto`). 깨는 변경은 v2 패키지로만 한다.
  - 필드 번호는 재사용하지 않고 지운 필드는 `reserved`로 번호와 이름을 막는다. 예약은 지울 때 하고 미리 잡지 않는다.
  - enum은 0을 `*_UNSPECIFIED`로 두고 ROS 상수 0(UNKNOWN)과 맞춘다. proto3 enum은 열린 enum이라 모르는 값이 보존된다.
  - ROS 필드 순서와 proto 필드 번호를 같은 순서로 맞춘다(1:1 확인이 쉬워진다).

4-5. ROS와 proto를 맞추는 기계적 장치. `idsim_fleet` 변환 모듈의 단위 테스트가 (a) 모든 필드를 기본값이 아닌 값으로 채운 `VehicleState`를 msg -> proto -> msg로 왕복해 같음을 확인하고, (b) rosidl introspection의 멤버 수와 proto descriptor의 필드 수가 같음을 단정한다. (b)가 있으면 msg에 필드를 더하고 proto를 잊은 PR이 바로 깨진다. enum은 ROS 상수 목록과 proto enum 값 목록을 같은 방식으로 비교한다.

4-6. proto는 Phase 3에 생기지만 번호와 이름은 지금 고정한다. 1a 5단계에서 `docs/interface.md`(7단계)에 "msg 필드 / proto 필드 번호 / WebSocket JSON key" 대응표를 넣을 것을 권한다. Phase 2의 WebSocket JSON 스키마가 proto보다 먼저 고정되므로, 이 표가 없으면 Phase 2의 JSON key와 Phase 3의 proto 이름이 갈라질 수 있다. proto 파일 자체는 Phase 3 착수 때 이 표에서 만든다(코드 생성 도구를 1a에 들이지 않기 위해).

4-7. WebSocket JSON 규칙(내 소유, 참고로 적는다). 봉투 `{"type": "vehicle_state", "v": 1, "data": {...}}`. `data`의 key는 msg 필드 이름(snake_case) 그대로. enum은 이름 문자열("ARMED")로 내보낸다(정수가 바뀌어도 화면이 조용히 틀리지 않게). 시각은 `{"sec":..,"nanosec":..}`. key는 추가만 하고 페이지는 모르는 key를 무시한다. Phase 3 게이트웨이는 Protobuf JSON mapping(lowerCamelCase, int64 문자열)을 쓰지 않고 serde 구조체로 같은 key를 직접 낸다. Phase 2 Python 어댑터와 Phase 3 Rust 게이트웨이가 같은 입력에서 같은 JSON을 내는지 golden fixture(`tests/fixtures/ws/`)로 확인한다.

## 소유자에게 넘기는 미해결 질문

- (architect, devops) map 프레임이 계약이 되면 `world.origin`을 Phase 2부터 필수로 할지.
- (sim) Gazebo 월드 프레임 축이 `set_spherical_coordinates` 뒤에도 동쪽, 북쪽 정렬인지.
- (px4) nav_state -> 우리 MODE 묶음의 최종 목록, failsafe_flags -> 경고 비트 대응.
- (architect) 취소 뒤 기체 동작(HOLD 권고)과 `on_cancel` 필드의 필요 여부.
- (ros2) `/fleet/vehicle_state` 공통 토픽안과 QoS, map ENU 변환 함수를 `idsim_common`에 둘지.
- (logging) action goal과 result의 기록 가능 여부, `MissionEvent.msg` 필요 여부, replay에서 파생 토픽 제외.
