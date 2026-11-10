# 1a 5단계 idsim_interfaces 의견: ros2-engineer

2026-11-10. 소유자 architect의 결정 전 의견이다. 질문마다 권고안 하나와 근거, 필요하면 대안을 적는다. 실측은 ros-ws 이미지(`idsim/ros-ws:local`, Jazzy, rmw_cyclonedds_cpp)에서 scratchpad의 시험 패키지로 했고, 저장소 파일은 이 의견서 말고는 건드리지 않았다. 실측하지 않은 판단은 "추정"으로 표시한다.

## 실측 요약

시험 패키지(`TargetState`, `MissionItem`, `Mission`, `ExecuteMission`, 한글 주석, 상수, 중첩 메시지, action)를 `colcon build`와 `colcon test`로 돌렸다.

| 항목 | 결과 |
| --- | --- |
| 한글 주석이 든 .msg, .action | 빌드 성공(콜드 빌드 8.5초) |
| `.action`만 있고 `package.xml`에 `action_msgs` 없음 | 빌드 성공. rosidl이 암묵으로 끌어온다 |
| 필드 이름 `goto` | C 생성기에서 컴파일 실패(`expected identifier or '(' before 'goto'`). C/C++ 예약어는 필드 이름으로 못 쓴다 |
| ament_lint(xmllint, lint_cmake, copyright) + pytest 1개 | `colcon test-result` 9 tests. pytest 안에서 자기 패키지의 `ros2 interface show`와 Python import가 된다(colcon test 환경에 자기 install이 들어 있다) |
| ament_copyright 검사 대상 확장자 | c, cc, cpp, cxx, h, hh, hpp, hxx, cmake, py. `.msg`, `.action`은 보지 않는다 |
| RIHS01 type hash(`share/<pkg>/msg/<Type>.json`)가 바뀌는 경우 | 필드 타입 변경: 바뀜, 그 타입을 담은 `Mission`, `ExecuteMission`까지 연쇄로 바뀜. 주석 변경, 상수 값 변경, 상수 추가, 필드 기본값 추가: 안 바뀜 |
| `ros2 interface show --no-comments` | 상수와 기본값을 포함하고 중첩 타입을 펼쳐 보여 준다 |
| Python에서 상수 열거 | `MissionItem.__class__._Metaclass_MissionItem__constants`가 `{'TYPE_TAKEOFF': 1, ...}` dict를 준다 |
| 토픽 이름 검증(`validate_full_topic_name`) | `/targets/1/state` 거부(토큰이 숫자로 시작), `/targets/target-a/state` 거부(하이픈), `/targets/t1/state`, `/px4_1/vehicle_state` 통과 |
| `geographic_msgs` | ros-ws 이미지에 없다 |

## 1. 패키지 골격

### 1-1. rosidl 구성

권고
- `ament_cmake` + `rosidl_generate_interfaces(... DEPENDENCIES builtin_interfaces geometry_msgs std_msgs)`. `package.xml`에는 `buildtool_depend rosidl_default_generators`, `exec_depend rosidl_default_runtime`, `depend builtin_interfaces geometry_msgs std_msgs action_msgs`, `member_of_group rosidl_interface_packages`.
  - `action_msgs`는 빌드에 필요 없음을 실측했지만 ROS 공식 action 튜토리얼대로 선언한다. rosdep과 exec 의존을 정확히 하기 위해서다.
- `unique_identifier_msgs`는 쓰지 않는다. action goal에 이미 UUID가 있고, 미션 식별은 사람이 읽고 기록물 이름에 들어가는 문자열 `mission_id`가 맡는다. Phase 3 proto도 문자열 id가 자연스럽다.
- `geographic_msgs`는 쓰지 않는다(이미지에 없고, 위경도 필드 셋이면 된다).
- 생성기는 기본값(C, C++, Python, introspection, type description) 그대로 둔다. Python은 pytest 판정과 WebSocket 어댑터가 쓰고, introspection은 rosbag2와 foxglove_bridge가 쓴다. 생성기를 줄여 얻는 빌드 시간은 몇 초다.
- 이 패키지에는 `add_compile_options(-Werror ...)`를 넣지 않는다. 대상이 우리가 소유하지 않는 생성 코드뿐이다.
- 메시지 파일은 `msg/VehicleState.msg`, `msg/TargetState.msg`, `msg/Mission.msg`, `msg/MissionItem.msg`, 항목 서브메시지(`msg/TakeoffItem.msg`, `msg/GoToItem.msg`, `msg/TrackEntityItem.msg`, `msg/LoiterItem.msg`, `msg/YawSetpoint.msg`), `action/ExecuteMission.action`. 3절 참조.

### 1-2. lint 설정

권고
- 4단계 (v)와 같게 `ament_lint_common` 묶음을 쓰지 않고 `ament_lint_auto` + test_depend `ament_cmake_xmllint`, `ament_cmake_lint_cmake`, `ament_cmake_copyright`만 둔다. C++ 소스가 없으므로 cpplint는 넣지 않는다(넣으면 대상 0개로 의미 없는 테스트가 생긴다).
- `package.xml`은 4단계 (x)의 5)처럼 xml-model 줄을 뺀다(unit job은 네트워크가 없다). license `Apache-2.0`, maintainer는 `idsim_common`과 같게.
- Apache-2.0 머리말은 `CMakeLists.txt`와 테스트 `.py`에 넣는다. `.msg`, `.action`에는 넣지 않는다. ament_copyright가 보지 않고, ROS 2 core 메시지 패키지 관례도 머리말이 없으며, 넣으면 그 주석이 생성 코드와 type description의 원문에 그대로 들어간다.
- 테스트 `.py`는 `lint` job의 ruff와 `px4-api` 검사 대상(`ros_ws/src/*.py`)에 들어간다. 테스트 안에 `fmu/out/` 같은 문자열을 쓰지 않는다.
- clang-tidy는 바꿀 것이 없다. `ros_ws.sh tidy`의 대상 정규식이 `ros_ws/src/<pkg>/src/`이고 `.clang-tidy`의 `HeaderFilterRegex`가 `ros_ws/src/idsim_*/include/`라서 build 아래 생성 코드는 대상이 아니다.
- 메시지 주석은 한국어로 쓴다(한글 주석 빌드 실측 통과). 단위와 좌표계는 필드 주석에 반드시 적는다.

### 1-3. 테스트 수 0 단정

`tools/ros_ws.sh`의 단정은 워크스페이스 전체 합계(`Summary: N tests`)다. `idsim_common`이 이미 테스트를 갖고 있어서, `idsim_interfaces`가 테스트 0개여도 단정에 걸리지 않는다. 즉 "걸리지 않으려면"이 아니라 "걸려야 할 때 안 걸린다"가 문제다.

권고
- `idsim_interfaces`가 자기 테스트를 갖는다: ament_lint 3종과 `ament_add_pytest_test`로 계약 테스트(5절의 golden, 상수 분류 검사). 시험 패키지에서 9 tests로 집계됐다.
- devops-engineer에게 `ros_ws.sh test`의 단정을 패키지별로 바꾸는 것을 제안한다. 예: `colcon list -n`의 각 패키지에 대해 `build/<pkg>/test_results/` 아래 결과 XML이 하나 이상 있는지 본다. 테스트 없는 패키지를 일부러 두려면 목록에 명시하게 한다.

## 2. 네 정의의 필드

### 2-0. 공통 규칙(권고)

- 단위는 SI. float 필드 이름에 단위 접미사를 붙인다(`_m`, `_mps`, `_rad`, `_deg`). geometry_msgs 타입 필드는 접미사 대신 주석으로 적는다.
- 지구 좌표는 모두 월드 ENU(`header.frame_id = "world"`, Gazebo 월드 프레임, 원점은 `fleet.yaml`의 `world.origin`). PX4 NED, FRD는 계약에 나오지 않는다. NED 변환은 `idsim_common`의 내부 일이다.
- yaw는 ENU yaw(동 0, 반시계 양), `[-pi, pi)`. `idsim_common::frames`의 관례와 같다.
- NaN과 무한대는 어떤 필드에도 넣지 않는다. 유효하지 않은 값은 `*_valid` bool로 표현한다. 근거: Phase 2 WebSocket과 Phase 3 게이트웨이 HTTP는 JSON이고 JSON에는 NaN이 없다. NaN을 "제어 안 함"으로 쓰는 것은 PX4 `TrajectorySetpoint`의 관례이며 그 번역은 `idsim_mission`이 한다.
- enum은 uint8 상수로 두고 0은 "모름/무효"로 남긴다. 기본 생성된 메시지가 우연히 유효한 값이 되지 않게 하기 위해서다.
- PX4의 enum 값(`nav_state`, `arming_state`)을 그대로 계약에 넣지 않고 우리 enum으로 옮긴다. PX4 태그를 올릴 때 계약이 따라 흔들리지 않게 하기 위해서다.

### 2-1. 시간 기준

- 모든 `header.stamp`와 시각 필드는 ROS 시각(노드 시계, `use_sim_time`이므로 `/clock`의 sim 시간)이다. 모든 Duration은 sim 시간 길이다.
- PX4 timestamp(us)는 계약에 넣지 않는다. SITL에서는 `UXRCE_DDS_SYNCT=0` 때문에 sim 시간과 같은 축이지만 실기체에서는 SYNCT를 되돌려 축이 달라진다. 계약에 넣으면 운용 노드가 그 차이를 알게 된다(architecture.md의 원칙 위반). 수집기는 PX4 timestamp를 변환해 `header.stamp`에 넣지 않는다. ULog 정렬은 기록물에 함께 들어가는 원본 `/fmu/out` 토픽으로 한다(logging-engineer 인터페이스).
- `VehicleState.header.stamp`: 수집기가 메시지를 만든 시각(노드 시계). 원본 PX4 표본의 나이는 수집기의 신선도 임계(파라미터, 계약 밖) 안이고, 넘으면 해당 `*_valid`를 false로 한다.
- `TargetState.header.stamp`: 위치 표본의 시각. sim에서는 Gazebo pose 메시지 header의 sim 시간을 그대로 옮긴다(ros_gz_bridge가 gz header stamp를 보존한다는 것은 추정, sim-engineer 확인). 실기체 확장에서 센서 기반 표적이 오면 센서 표본 시각이 된다.

### 2-2. 원점 문제와의 관계(1b 전 결정에 대한 의견)

계약을 월드 ENU로 두면 "월드 ENU <-> 기체 로컬 NED" 변환이 필요하다. 기체 로컬 NED는 북쪽 정렬이고 원점만 스폰 지점이므로 회전은 없고 평행 이동뿐이다(스폰 yaw와 무관).

권고: 변환은 `idsim_common`의 원점 객체 하나로 하고, 원점의 1차 출처는 `VehicleLocalPosition`의 `ref_lat`, `ref_lon`, `ref_alt`(+ `xy_global`, `z_global`, `ref_timestamp`)와 `stack.json`에서 params로 받은 `world.origin`이다. 스폰 pose는 통합 테스트의 교차 검증에만 쓴다.
- 근거: PX4가 실제로 쓰는 원점이고, EKF 원점 재설정(`ref_timestamp` 변화)을 따라갈 수 있으며, 실기체에서도 같은 경로가 성립한다. 스폰 pose 경로는 Gazebo에만 있다.
- 결과로 생기는 계약 사항: `VehicleState.position_valid`는 `xy_valid && z_valid && xy_global && z_global`일 때만 참이다. GoTo와 TrackEntity 항목은 원점이 잡히기 전에는 시작하지 않는다(takeoff는 상대 높이라 원점이 필요 없다).
- 추정 표시: PX4 지도 투영(azimuthal equidistant)과 Gazebo 구면 좌표의 차이는 수백 m 범위에서 mm 이하라고 보지만 측정하지 않았다. GPS 잡음 때문에 EKF 원점이 스폰 지점과 수십 cm 어긋날 수 있다는 것도 추정이며, 1b에서 스폰 pose와 대조해 측정한다. 기본 `EKF2_HGT_REF`가 기압계이면 z가 GPS 고도와 서서히 어긋날 수 있다(추정, px4-engineer 확인).

### 2-3. VehicleState.msg(초안)

```
# 기체 요약 상태. Telemetry Collector가 기체마다 발행한다. 위치는 월드 ENU.
uint8 ARMING_UNKNOWN = 0
uint8 ARMING_DISARMED = 1
uint8 ARMING_ARMED = 2

uint8 MODE_UNKNOWN = 0
uint8 MODE_OFFBOARD = 1
uint8 MODE_TAKEOFF = 2     # PX4 AUTO_TAKEOFF
uint8 MODE_LAND = 3        # PX4 AUTO_LAND
uint8 MODE_RTL = 4         # PX4 AUTO_RTL
uint8 MODE_HOLD = 5        # PX4 AUTO_LOITER (Hold)
uint8 MODE_OTHER = 255     # 위에 없는 PX4 모드

std_msgs/Header header     # stamp: 수집기가 만든 시각(sim). frame_id: "world"
string vehicle_ns          # 예: "/px4_1". 노드 params 값
uint8 system_id            # MAVLink system id. vehicle_status와 대조(verify)를 통과한 값

uint8 arming_state
uint8 mode
bool failsafe

bool position_valid        # 2-2의 조건. false면 position, yaw는 의미 없음
geometry_msgs/Point position   # 월드 ENU, m
float64 yaw_rad            # 월드 ENU yaw, [-pi, pi)
bool velocity_valid
geometry_msgs/Vector3 velocity # 월드 ENU, m/s

bool global_valid
float64 latitude_deg       # WGS84
float64 longitude_deg
float64 altitude_amsl_m

bool battery_valid
float32 battery_remaining  # 0-1
```

- 수집기는 `verify`가 Match가 되기 전에는 발행하지 않는다. 그래서 식별 확인 플래그를 메시지에 두지 않는다.
- 위경도는 Phase 2 지도 페이지가 쓴다. 월드 ENU는 Fleet의 "표적에 가장 가까운 기체" 계산이 쓴다. 둘 다 둔다.
- 대안: 디버깅용으로 PX4 `nav_state` 원값을 함께 싣는 안. 계약을 PX4 태그에 묶으므로 권하지 않는다. 판정은 어차피 원본 PX4 토픽으로 한다.

### 2-4. TargetState.msg(초안)

```
# 표적 상태. 시뮬레이터 비의존. 위치와 속도는 월드 ENU.
std_msgs/Header header          # stamp: 위치 표본 시각(sim). frame_id: "world"
string target_id                # ^[a-z][a-z0-9_]{0,31}$. 토픽 경로 /targets/<id>/state의 <id>와 같다
geometry_msgs/Point position    # 월드 ENU, m
bool velocity_valid             # 첫 표본처럼 속도를 모를 때 false
geometry_msgs/Vector3 velocity  # 월드 ENU, m/s
```

- 자세와 공분산은 넣지 않는다. 소비자(track_entity, Fleet 배분)가 위치와 속도만 쓴다. 센서 기반 표적이 생기면 그때 더한다(5절 규칙으로 깨짐이 드러난다).
- 속도는 Gazebo Actor pose의 차분으로 어댑터가 만든다(sim-engineer). 구독자는 `target_id`가 토픽 경로의 id와 같은지 확인한다.

### 2-5. Mission.msg, ExecuteMission.action

3절에 함께 적는다.

## 3. Mission 항목 표현

### 3-1. 표현 방식

권고: `MissionItem`에 type 상수 + 공용 필드(timeout) + 항목별 서브메시지 필드 하나씩(태그 붙은 합집합 흉내). 쓰지 않는 서브메시지는 기본값이어야 하고, 아니면 검증에서 거부한다.

```
# Mission.msg
string mission_id          # ^[a-z0-9][a-z0-9_-]{0,63}$. 기록물 이름 <시각>_<미션 id>_<기체 id>에 들어간다
MissionItem[] items        # 1개 이상, 순서대로 실행

# MissionItem.msg
uint8 TYPE_TAKEOFF = 1
uint8 TYPE_GOTO = 2
uint8 TYPE_TRACK_ENTITY = 3
uint8 TYPE_LOITER = 4
uint8 TYPE_RTL = 5
uint8 TYPE_LAND = 6
uint8 type                          # 0은 무효
builtin_interfaces/Duration timeout # 이 항목의 제한 시간(sim). > 0
TakeoffItem takeoff                 # type == TYPE_TAKEOFF일 때만
GoToItem go_to                      # type == TYPE_GOTO일 때만. goto는 C 예약어라 쓸 수 없다(실측)
TrackEntityItem track_entity
LoiterItem loiter
# rtl, land는 서브메시지가 없다

# YawSetpoint.msg
uint8 MODE_HOLD = 1        # 항목 시작 때의 yaw 유지
uint8 MODE_FIXED = 2       # yaw_rad로
uint8 mode
float64 yaw_rad            # 월드 ENU yaw. MODE_FIXED일 때만

# TakeoffItem.msg
float64 height_m           # 항목 시작 위치(arm 지점) 기준 상대 높이, > 0
float64 acceptance_m       # 수직 허용 오차, > 0
YawSetpoint yaw

# GoToItem.msg
geometry_msgs/Point position  # 월드 ENU, m
float64 acceptance_radius_m   # 3차원 거리 허용 오차, > 0
YawSetpoint yaw

# TrackEntityItem.msg
string target_id              # TargetState.target_id
geometry_msgs/Vector3 offset  # 월드 ENU, m. 표적 위치에 더한 점을 setpoint로 쓴다(예: z + 5)
float64 acceptance_radius_m   # 접근 판정 거리, > 0. 이 안에 들면 항목 완료
YawSetpoint yaw

# LoiterItem.msg
builtin_interfaces/Duration duration  # > 0, timeout보다 짧다. 항목 시작 때의 setpoint에서 유지
```

근거
- 순서가 있는 이종 목록이 필요하다. 항목별 배열을 따로 두는 안은 순서를 위해 index 필드를 또 둬야 하고 검증이 더 어렵다.
- 공용 필드에 position, radius, duration, target_id를 몰아 두는 안은 어떤 필드가 어느 항목에 쓰이는지가 주석에만 있고, "goto인데 duration을 채움" 같은 실수를 잡지 못한다. 서브메시지 안은 rosidl이 만드는 `operator==`로 "쓰지 않는 서브메시지 == 기본값"을 한 줄로 검사할 수 있다.
- Phase 3 proto의 `oneof`와 1:1로 대응한다. 변환 모듈은 type과 oneof case가 맞는지만 보면 된다.
- 비용: 항목마다 쓰지 않는 서브메시지가 직렬화된다. 항목 수가 수십 개 수준이라 무시할 크기다(추정이 아니라 필드 수로 계산 가능: 항목당 수백 바이트 이하).

대안: type + 공용 필드 안. 메시지 파일 수가 적지만 위 근거로 권하지 않는다.

### 3-2. setpoint 항목과 모드 명령 항목의 구분

권고: 메시지에 분류 필드를 두지 않고 type에서 파생한다. 분류 함수(`is_setpoint_item(type)`, `is_mode_command_item(type)`)는 `idsim_mission`에 두고, 계약 테스트가 `MissionItem`의 모든 `TYPE_*` 상수를 Python 메타클래스의 상수 dict로 열거해 각 상수가 정확히 한 분류에 속하는지 단정한다. 상수를 추가하고 분류를 빠뜨리면 테스트가 깨진다.
- 근거: 분류 필드를 두면 type과 어긋난 조합(`type=LAND, kind=SETPOINT`)이 표현 가능해진다.
- 분류는 architecture.md대로: setpoint(takeoff, goto, track_entity, loiter), 모드 명령(rtl, land).
- 주의: `loiter`는 Offboard에서 setpoint를 유지하는 항목이고 PX4 Hold(AUTO_LOITER) 모드가 아니다. `VehicleState.MODE_HOLD`와 혼동하지 않도록 interface.md에 적는다. `takeoff`도 Offboard 상승이며 PX4 AUTO_TAKEOFF가 아니다.
- 대안: type 값 범위로 분류(1-63 setpoint, 64 이상 모드 명령). 테스트 없이도 드러나지만 값에 의미를 숨기는 방식이라 권하지 않는다.

### 3-3. 좌표 계약

권고: 월드 ENU 하나. 기체 로컬 NED는 계약에 넣지 않는다(기체마다 원점이 달라 Fleet이 기체별로 좌표를 바꿔 써야 하고, 재배분 때 미션을 다시 써야 한다). 위경도는 1a, 1b 계약에 넣지 않는다.
- 근거: 표적(`TargetState`)과 기체 상태(`VehicleState.position`)가 같은 월드 ENU라야 Fleet의 거리 계산과 미션 재배분이 좌표 변환 없이 된다. 기체별 변환은 2-2의 원점 객체로 실행 노드 안에서만 한다.
- 대안: 항목마다 `frame` enum(WORLD_ENU, GEODETIC)을 둬 실기체 확장을 미리 여는 안. 지금 소비자가 없고, 나중에 더해도 5절의 golden이 깨짐을 드러내므로 지금은 두지 않는다.

### 3-4. 허용 오차와 타임아웃

권고: 메시지에 둔다. 모든 값은 명시적이어야 하며 "0이면 기본값" 규칙을 두지 않는다. 기본값은 YAML 로더(`idsim_mission`)가 채우고, action 서버는 0, 음수, 비유한 값을 거부한다.
- 근거: 판정(테스트의 "반경 1 m 이내 도달")과 실행이 같은 값을 쓰고, 기록물에 실제로 쓰인 값이 남아 replay에서 같은 판정을 재현할 수 있다. 노드 파라미터에 두면 기록물만으로는 그 값을 알 수 없다.
- 시간 필드는 `builtin_interfaces/Duration`(sim 시간). proto의 `google.protobuf.Duration`과 1:1이다. YAML은 초 단위 실수로 쓰고 로더가 바꾼다.
- 표적 신선도 임계(TargetState가 몇 초 끊기면 실패인가), setpoint 주기 같은 안전 파라미터는 메시지가 아니라 노드 파라미터로 둔다. 미션 작성자가 바꿀 값이 아니다.

### 3-5. ExecuteMission.action(초안)

```
# goal
Mission mission
---
# result. 성공, 중단, 취소는 action의 GoalStatus가 정본이다. 여기에는 이유만 둔다
uint8 ERROR_NONE = 0
uint8 ERROR_INVALID_MISSION = 1
uint8 ERROR_ITEM_TIMEOUT = 2
uint8 ERROR_OFFBOARD_ENTRY_FAILED = 3
uint8 ERROR_MODE_CHANGE_FAILED = 4   # vehicle_command ack 뒤 nav_state 확인 실패
uint8 ERROR_FAILSAFE = 5
uint8 ERROR_TARGET_UNAVAILABLE = 6
uint8 ERROR_IDENTITY_MISMATCH = 7
uint8 error_code
uint32 completed_items               # 완료한 항목 수
uint32 failed_item_index             # error_code가 항목 단위 오류일 때만 의미
string message                       # 사람이 읽는 설명
---
# feedback
uint8 PHASE_ENTERING_OFFBOARD = 1
uint8 PHASE_EXECUTING = 2
uint8 PHASE_WAITING_MODE = 3         # 모드 명령 항목에서 nav_state 전이 대기
uint32 current_item_index
uint8 current_item_type
uint8 phase
bool distance_valid
float64 distance_remaining_m
```

- 기체 지정은 goal 필드가 아니라 action 이름의 네임스페이스로 한다(4절).
- 실행 중 새 goal은 거부한다(선점하지 않는다). 형식 오류 미션은 goal 단계에서 거부하지 말고 accept 뒤 `ERROR_INVALID_MISSION`으로 abort하는 것을 권한다. ROS 2 action에서 거부된 goal은 결과를 받지 못해 이유가 클라이언트(Fleet, 테스트)와 기록물에 남지 않는다. 이 정책은 idsim_mission, ops-service 인터페이스의 결정이다.

## 4. QoS와 토픽 이름

### 4-1. 이름

권고
- `VehicleState`: `/<기체 ns>/vehicle_state`. 수집기는 기체 네임스페이스로 띄우고 상대 이름 `vehicle_state`로 발행한다.
- `ExecuteMission`: `/<기체 ns>/execute_mission`. 같은 방식.
- `TargetState`: `/targets/<id>/state`. id 규칙 `^[a-z][a-z0-9_]{0,31}$`. 숫자로 시작하는 토큰과 하이픈은 ROS 이름 규칙이 거부함을 실측했다(`/targets/1/state` 불가). 그래서 `fleet.yaml`의 `targets[].id`도 이 규칙으로 생성기가 검사해야 한다(devops-engineer 인터페이스).
- 기체 목록과 표적 목록은 그래프 탐색이 아니라 `stack.json`에서 생성된 params로 받는다. 4단계 (u)의 "공식 대신 params" 원칙과 같다.
- PX4 토픽(`/px4_N/fmu/...`)과 겹치지 않는다. `idsim/` 같은 중간 토큰은 두지 않는다. rosbag 선별은 이름 목록으로 하면 된다.
- 이름 상수의 출처: 상대 이름과 접두사를 메시지 상수로 둔다(`VehicleState.TOPIC = "vehicle_state"`, `TargetState.TOPIC_PREFIX = "/targets"`, `TargetState.TOPIC_SUFFIX = "state"`, `ExecuteMission`은 action이라 상수를 둘 수 없으니 `Mission.ACTION = "execute_mission"`). 전체 이름 조립과 id 검증은 C++은 `idsim_common`(`VehicleNamespace`와 같은 강타입 `TargetId`), Python 판정 코드는 `tests/support`가 같은 상수로 한다.
  - 근거: C++ 노드와 Python 판정 코드가 같은 출처를 쓰고, 상수는 5절의 `interface show` golden에 들어가 이름 변경이 계약 변경으로 드러난다. PX4 토픽처럼 `idsim_common`에만 두면 Python 쪽 사본이 생긴다.
  - 대안: 이름을 `idsim_common` C++ header에만 두고 Python은 사본 + 교차 검사 테스트. 메시지에 이름을 넣는 것은 ROS 관례가 아니라는 반론이 있을 수 있어 architect 판단에 맡긴다.

### 4-2. QoS

권고(두 상태 토픽 공통)
- 발행: RELIABLE, VOLATILE, KEEP_LAST 1.
- 구독: BEST_EFFORT, VOLATILE, KEEP_LAST 1(최신값 의미).
- 근거: RELIABLE 발행은 BEST_EFFORT와 RELIABLE 구독 모두와 호환되고, rosbag2가 이 QoS를 기록해 재생할 때도 그대로라 Phase 2의 "재생 시 구독자가 reliable을 요구해 못 받음" 함정이 생기지 않는다. 구독을 BEST_EFFORT로 두면 어떤 발행자(라이브, 재생, 미래의 best-effort 어댑터)와도 호환된다. TRANSIENT_LOCAL은 이득이 없다. 5 Hz, 20 Hz 주기 토픽이라 늦게 붙어도 한 주기 안에 받고, 기체 이탈 판정이 묵은 표본에 속을 여지만 생긴다.
- 프로필은 `idsim_common`에 함수로 두고(`state_publisher_qos()`, `state_subscriber_qos()`), Python 판정 코드는 같은 값을 쓴다. 6단계 이후 통합 테스트에서 `get_publishers_info_by_topic`으로 실제 발행 QoS를 S4 golden처럼 대조할 것을 test-engineer에게 제안한다.
- 주기는 계약이 아니다(architecture.md 원칙). VehicleState 5 Hz는 수집기 파라미터, TargetState는 setpoint 주기(20 Hz) 이상을 어댑터 파라미터 기본값으로 권한다. Gazebo pose 원 주기를 그대로 내보내지 않는다.
- action은 rcl 기본 action QoS(서비스 RELIABLE, status TRANSIENT_LOCAL)를 바꾸지 않는다.
- logging-engineer 인터페이스: `replay` 프로필에서 수집기가 원본 PX4 토픽으로 `VehicleState`를 다시 만들므로, 기록물에 든 `VehicleState`를 함께 재생하면 한 토픽에 발행자가 둘이 된다. 재생 때 이 토픽을 빼거나 이름을 바꾸는 규칙이 필요하다.

## 5. 버전과 변경 규칙

권고: `idsim_interfaces/test/`의 pytest 계약 테스트 하나에 golden 두 가지와 상수 분류 검사를 둔다.

1. type hash golden `test/golden/type_hashes.txt`: 설치된 `share/idsim_interfaces/{msg,action}/*.json`의 `type_hashes[0]`(RIHS01)를 타입별 한 줄로. 이 값은 Jazzy가 DDS 디스커버리와 기록물에 쓰는 타입 식별자라서, 이것이 바뀌면 이전 기록물과 이전 빌드의 노드와는 맞지 않는다는 뜻이다.
2. 정의 golden `test/golden/<kind>/<Type>.txt`: `ros2 interface show --no-comments <type>` 출력. 실측상 RIHS01은 상수 값 변경, 상수 추가, 기본값 변경을 잡지 못한다. 그런데 이 계약에서 enum 값(`TYPE_GOTO` 등)과 이름 상수는 의미의 핵심이므로 이 golden이 필요하다. 중첩 타입을 펼쳐 보여 주므로 ros-base를 올려 geometry_msgs가 바뀌는 것도 드러난다. 주석은 빼서 주석 수정이 계약 변경으로 잡히지 않게 한다.
3. 상수 분류 검사: 3-2. 분류 함수가 `idsim_mission`에 있으므로 이 검사는 1b에서 `idsim_mission` 테스트로 옮기거나, 5단계에서는 "상수 집합 == 기대 집합"만 단정한다.

변경 규칙
- golden이 다르면 테스트가 diff와 갱신 명령(예: `IDSIM_UPDATE_GOLDEN=1 tools/ros_ws.sh test --packages-select idsim_interfaces`)을 출력하고 실패한다. (뒤에 붙인 주석: 이 예시 명령은 동작하지 않는다. `tools/ros_ws.sh`는 이 변수를 컨테이너에 넘기지 않는다. 갱신은 `decisions.md` 쟁점 10의 절차(`tools/ros_ws.sh shell` 안에서 `IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces`)를 따른다.) 4단계 PX4 golden처럼 자동 갱신은 하지 않는다.
- 계약 변경 PR에는 golden 갱신, `docs/interface.md`, 결정 기록, (Phase 3 이후) proto와 왕복 테스트, 영향받는 replay fixture 갱신이 함께 들어간다. architect 승인 필수.
- 메시지 안에 버전 필드나 버전 상수를 두지 않는다. 단일 저장소, 단일 빌드라 런타임 협상이 필요 없고, 타입 식별은 RIHS01이 이미 한다. 버전 상수는 hash에 들어가지 않아(실측) 식별자로도 쓸모가 없다.
- 기록물 호환: 계약이 바뀌면 이전 MCAP을 새 타입으로 읽을 수 없다. 기록물 인덱스 CLI가 기록물마다 type hash를 남겨 replay 전에 대조하는 것을 logging-engineer에게 제안한다(rosbag2 Jazzy가 MCAP에 type hash를 남긴다는 것은 추정, 확인 필요).

## 다른 담당자에게 넘길 확인 사항

| 담당 | 항목 |
| --- | --- |
| sim-engineer | ros_gz_bridge가 Gazebo pose header의 sim 시간을 ROS header.stamp로 보존하는지. Actor 속도를 차분으로 만들 때의 주기 |
| px4-engineer | EKF 원점이 스폰 지점의 GPS 표본과 얼마나 어긋나는지, `EKF2_HGT_REF` 기본값에서 `ref_alt` 기준 z가 GPS 고도와 어긋나는지, `ref_timestamp`가 비행 중 바뀌는 조건 |
| ops-service-engineer | 형식 오류 미션의 accept 후 abort 정책, `MissionItem`의 proto `oneof` 대응, `mission_id` 규칙 |
| devops-engineer | `ros_ws.sh test`의 패키지별 테스트 수 단정, `fleet.yaml` `targets[].id` 이름 규칙 검사 |
| logging-engineer | replay 때 `VehicleState` 중복 발행자, 기록물별 type hash 기록 |
| test-engineer | 상태 토픽 QoS 대조 테스트, Python 판정 코드의 이름 상수 사용 |
