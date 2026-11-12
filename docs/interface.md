# idsim 인터페이스

이 문서는 idsim의 레이어 사이 인터페이스를 필드와 동작 단위로 정한다. 앞 부분은 PX4와 ROS 2 사이(기준 버전, 공통 규칙, 시간 기준, 좌표계, PX4 토픽, 기체 식별, 명령, setpoint, SITL 파라미터, 포트)이고, 뒷 부분은 `idsim_interfaces`의 정의별 계약이다. 설계의 배경과 고정 원칙은 `docs/architecture.md` "인터페이스 계약" 절에 있다.

각 절의 첫 줄에 그 절의 고정 시점을 적는다. "고정 전"인 절의 문장은 지금의 정의와 동작이며, 첫 소비자의 구현에서 드러난 문제에 한해 바뀔 수 있다.

## 고정 시점

PX4 인터페이스("PX4 쪽 기준 버전", "좌표계", "PX4 토픽", "기체 식별과 네임스페이스", "VehicleCommand", "Offboard setpoint", "SITL 파라미터", "포트" 절)와 공통 규칙("공통 규칙", "시간 기준", "정의 작성 규칙", "변경 절차와 계약 테스트" 절)은 1a 완료에 고정한다. `idsim_interfaces`의 정의 파일(msg 10개, action 1개)은 Phase 1a에서 모두 만들었고, 고정은 첫 소비자가 생기는 Phase의 완료에 맞춰 파일 단위로 나눈다.

| 파일 | 묶음 | 고정 시점 | 1a 완료 때 |
| --- | --- | --- | --- |
| `action/ExecuteMission.action` | 미션 실행(1a 부분) | 1a 완료 | 고정 |
| `msg/Mission.msg` | 미션 실행(1a 부분) | 1a 완료 | 고정 |
| `msg/MissionItem.msg` | 미션 실행(1a 부분). GOTO, TRACK_ENTITY, RTL의 의미는 1b 부분 | 1a 완료(직접 필드와 상수). 세 항목의 의미는 1b 완료 | 직접 필드와 상수, TAKEOFF, LOITER, LAND의 의미 고정 |
| `msg/YawSetpoint.msg` | 미션 실행(1a 부분) | 1a 완료 | 고정 |
| `msg/TakeoffItem.msg` | 미션 실행(1a 부분) | 1a 완료 | 고정 |
| `msg/LoiterItem.msg` | 미션 실행(1a 부분) | 1a 완료 | 고정 |
| `msg/GoToItem.msg` | 미션 실행(1b 부분) | 1b 완료 | 고정 전 |
| `msg/TrackEntityItem.msg` | 미션 실행(1b 부분) | 1b 완료 | 고정 전 |
| `msg/TargetState.msg` | 표적 | 1b 완료 | 고정 전 |
| `msg/VehicleState.msg` | 기체 요약 | Phase 2 완료(WebSocket JSON 스키마 고정과 함께) | 고정 전 |
| `msg/MissionEvent.msg` | 미션 기록 | Phase 2 완료(기록물 인덱스가 필드를 검증한 뒤) | 고정 전 |

1a 완료에 함께 고정되는 의미: `ExecuteMission`의 수락 정책, 취소 의미, TAKEOFF, LOITER, LAND 항목의 의미, `reason` 값의 의미(`REASON_TARGET_LOST` 제외). 공중에서 끝나는 미션(마지막 항목이 LAND가 아닌 미션)의 종료 동작은 1a 고정에서 빠지고 1b 완료에 고정한다("공중에서 끝나는 미션" 절).

"고정"의 정의.

- 고정의 단위는 타입이 아니라 파일이다. 한 파일이 고정되면 그 파일의 직접 필드(이름, 타입, 순서, 기본값)와 상수(이름, 값), 그리고 이 문서에 적힌 그 필드와 상수의 의미가 고정된다. 중첩된 타입의 내용은 그 타입의 파일이 고정될 때 고정된다.
- 중첩 타입이 바뀌면 그것을 담은 타입의 type hash(RIHS01)와 펼친 정의도 바뀐다. 이 전파는 상위 타입의 변경으로 보지 않으며, 그 중첩 타입이 고정되기 전까지만 허용된다. 예: 1b에서 `GoToItem`을 고치면 `MissionItem`, `Mission`, `ExecuteMission`의 type hash golden과 펼친 정의 golden이 함께 바뀌지만 세 파일의 직접 정의 golden이 그대로이면 고정된 계약의 변경이 아니다. 1b 완료 뒤에는 미션 타입의 어떤 golden 변경도 계약 변경이다.
- `MissionItem`의 직접 필드에는 `go_to`, `track_entity` 자리와 `TYPE_GOTO`, `TYPE_TRACK_ENTITY`, `TYPE_RTL`의 값이 있고 이것은 1a 완료에 고정된다. 1b에서 이 서브메시지를 다른 타입으로 갈아야 하면 고정된 계약의 변경으로 다룬다.
- 상수(enum 값, 비트, 이름)는 고정 전후 모두 추가만 한다. 상수의 의미는 그 상수를 처음 쓰는 소비자가 생기는 묶음과 함께 고정된다(`VehicleState`의 `WARN_*`는 Phase 2).
- 고정 전인 파일은 첫 소비자의 구현에서 드러난 문제에 한해 바꿀 수 있고, 고정 뒤에는 새 요구가 있어야 한다. 어느 쪽이든 "변경 절차와 계약 테스트" 절을 따른다.
- 의미 문장 가운데 실측이나 소스로 확인하지 않은 경계 상황의 기체 동작은 "미확인"으로 표시하고, 그때 노드가 택하는 보수적 동작을 함께 적는다. 미확인 표시는 고정을 막지 않는다. 관찰된 문제가 그 동작을 반증하면 변경 절차로 고친다.

## PX4 쪽 기준 버전

고정 시점: 1a 완료.

| 항목 | 값 | 출처 |
| --- | --- | --- |
| PX4 | `v1.17.0` | `docker/versions.env` `PX4_TAG` |
| px4_msgs | `86d8239e962f6939e05c3737784f60c02fa884db` | `docker/versions.env` `PX4_MSGS_REF`, `tests/fixtures/px4/v1.17.0/env.txt` |
| uXRCE-DDS Agent | `v2.4.3` | `docker/versions.env` `XRCE_AGENT_TAG` |
| ROS 2 | Jazzy | `docker/versions.env` `ROS_DISTRO` |
| rmw | `rmw_cyclonedds_cpp`(모든 ROS 2 컨테이너의 `RMW_IMPLEMENTATION`) | `tools/gen_compose.py` `RMW`, `tests/fixtures/px4/v1.17.0/env.txt` |
| PX4 골든 | `tests/fixtures/px4/v1.17.0/`(`topics.txt`, `qos/`, `env.txt`) | 환경 스모크 golden 단계가 만든다(`docs/smoke-test.md`) |

- PX4 태그를 올리는 조건은 환경 스모크 golden 단계의 통과다. 새 태그의 골든은 `tests/fixtures/px4/<PX4_TAG>/`에 새로 두고, 이 문서의 토픽 표를 그 골든으로 다시 만든다.
- `PX4_MSGS_REF`는 세 곳(`docker/versions.env`, 골든 `env.txt`, ros-ws 이미지의 `IDSIM_BUILD_PX4_MSGS_REF`)이 같아야 하고 `idsim_common`의 `test_topics_golden`이 판정한다. 셋이 다르면 토픽은 보이지만 역직렬화가 조용히 실패할 수 있기 때문이다.
- 이 문서의 PX4 소스 행 번호는 PX4 `v1.17.0` 태그의 원문 기준이다.

## 공통 규칙

고정 시점: 1a 완료.

`idsim_interfaces`의 모든 정의와 그 정의를 쓰는 노드에 적용된다. 정의별 문장은 각 정의의 절에 있다.

- 단위는 SI다(m, m/s, rad, s). 스칼라 필드 이름에 단위 접미사(`_m`, `_rad`, `_deg`, `_s` 등)를 붙이고, geometry_msgs 필드는 주석에 단위를 적는다.
- 계약 프레임은 `"world"` 하나다. 원점은 `config/fleet.yaml`의 `world.origin`이 가리키는 점(Gazebo 월드 (0, 0, 0))이고, 축은 x 동, y 북, z 위(ENU)이며, yaw는 ENU yaw(동 0, 반시계 양, `[-pi, pi)`)다. `header.frame_id`는 그 메시지의 `FRAME_ID` 상수와 같고, 소비자는 다르면 버린다.
- 기체 로컬 NED, 동체 FRD, 위경도는 미션과 표적 계약에 나오지 않는다(`VehicleState`만 지도 표시용 WGS84를 함께 싣는다). PX4 timestamp(us)와 PX4의 enum 값(`nav_state`, `arming_state`)은 어떤 필드에도 넣지 않는다. PX4 값에서 계약 값으로의 변환표는 생산자 한 곳에만 둔다.
- NaN과 무한대는 어떤 필드에도 넣지 않는다. 값이 없으면 짝이 되는 `*_valid`가 false이고 값은 0이다. NaN을 "제어 안 함"으로 쓰는 PX4 `TrajectorySetpoint`의 관례는 `idsim_mission` 안에서만 번역한다.
- enum은 uint8 상수이고 0은 "모름 또는 무효"다. 기본 생성된 메시지가 유효한 값이 되지 않는다. 소비자는 모르는 값을 UNKNOWN 또는 OTHER로 다룬다. 상수는 추가만 하고 값을 재사용하지 않는다.
- 의존은 `builtin_interfaces`, `std_msgs`, `geometry_msgs`뿐이다. 위치와 속도는 `std_msgs/Header` + `geometry_msgs/Point`, `geometry_msgs/Vector3`로 싣는다. 좌표가 없는 메시지(`MissionEvent`, `ExecuteMission` feedback)는 Header 대신 `builtin_interfaces/Time stamp`를 둔다.
- 시각은 "시간 기준" 절을 따른다.

### 이름과 식별자

이름의 고정 부분(토픽, action, 프레임 이름)은 메시지의 string 상수(`ACTION_NAME`, `TOPIC_NAME`, `TOPIC_PREFIX`, `TOPIC_SUFFIX`, `FRAME_ID`)로 둔다. C++ 노드와 Python 판정 코드는 문자열을 다시 쓰지 않고 같은 상수로 전체 이름을 조립한다. 전체 이름의 조립과 id 검증은 C++은 `idsim_common`, Python은 `tests/support`가 한다.

| 이름 | 전체 이름 | 상수 |
| --- | --- | --- |
| 미션 실행 action | `/<vehicle_id>/execute_mission` | `Mission.ACTION_NAME` |
| 미션 기록 토픽 | `/<vehicle_id>/mission_event` | `MissionEvent.TOPIC_NAME` |
| 기체 요약 토픽 | `/<vehicle_id>/vehicle_state` | `VehicleState.TOPIC_NAME` |
| 표적 토픽 | `/targets/<target_id>/state` | `TargetState.TOPIC_PREFIX`, `TargetState.TOPIC_SUFFIX` |
| 계약 프레임 | `world` | `VehicleState.FRAME_ID`, `TargetState.FRAME_ID`(같은 값) |

| 식별자 | 규칙 |
| --- | --- |
| `vehicle_id` | 기체 네임스페이스에서 앞의 "/"를 뗀 ROS 이름 토큰 하나. 출처는 `config/fleet.yaml`에서 생성된 `stack.json`과 노드 params이고, 노드와 테스트는 계산하지 않고 읽는다("기체 식별과 네임스페이스" 절). 소비자는 내용을 해석하지 않는다(번호를 뽑거나 sysid를 계산하지 않는다) |
| `mission_id` | `^[a-z0-9][a-z0-9_-]{0,63}$`. 불투명 문자열. Executor는 해석하지 않는다. 같은 값이 재사용될 수 있다 |
| `target_id` | `^[a-z][a-z0-9_]{0,31}$`. 시뮬레이션에서는 `fleet.yaml`의 `targets[].id` = Gazebo 엔티티 이름 = 토픽 토큰 = 메시지 필드다 |

### 계약 토픽 QoS

QoS 계약은 reliability와 durability 둘이다. history와 depth는 구현 값이고 계약이 아니다. DDS deadline과 liveliness로 신선도를 판정하지 않는다(벽시계 기준이다). PX4 토픽의 QoS는 "PX4 토픽 QoS" 절에 있다.

| 토픽 묶음 | 발행 | 구독 | 구현(`idsim_common`) |
| --- | --- | --- | --- |
| 상태(`VehicleState`, `TargetState`) | RELIABLE, VOLATILE | BEST_EFFORT, VOLATILE | 고정 전(첫 발행자가 생길 때 둔다. 구현 값은 KEEP_LAST 5) |
| 사건(`MissionEvent`) | RELIABLE, VOLATILE | RELIABLE, VOLATILE | `event_pub_qos()`, `event_sub_qos()`(`contract_qos.hpp`. KEEP_LAST 10) |

- 상태 토픽 구독이 BEST_EFFORT인 것은 라이브 발행자와 rosbag2 재생 발행자 어느 쪽과도 맞게 하려는 것이다. 상태 토픽의 주기는 계약이 아니다.
- 사건 토픽은 구독이 BEST_EFFORT이면 사건을 잃으므로 양쪽 모두 RELIABLE이다. TRANSIENT_LOCAL은 쓰지 않는다(지난 실행의 사건이 새 구독자에게 현재 사건으로 보인다). TRANSIENT_LOCAL 구독은 이 발행자와 맞지 않는다.
- 사건 토픽은 VOLATILE이라 늦게 붙은 구독자는 지난 사건을 받지 않는다. 구독을 만드는 순서는 "MissionEvent" 절의 발행 규칙에 있다.

## 시간 기준

고정 시점: 1a 완료.

- 정식 기준은 ROS 시각이다. `use_sim_time`이 true이면 노드 시계는 `/clock`을 따르고, idsim의 모든 운용 노드는 true로 돈다(생성기가 `params/ops-N.yaml`의 `/**`에 `use_sim_time: true`를 싣고, Executor는 configure에서 false를 거부한다). 판정, 집계, 계약 메시지의 모든 시각 필드와 시간 길이 필드, 기록물 타임스탬프는 모두 ROS 시각이다. 벽시계가 아니다.
- 이 문서에서 "ROS 시각"은 이 뜻이다. 메시지는 시뮬레이터에 의존하지 않으므로 "시뮬레이션 시각"이라고 쓰지 않는다.
- `/clock`의 공급자는 `bridge` 서비스의 ros_gz_bridge다(1a는 `/clock`만 브리지한다).
- 벽시계를 쓰는 곳과 그 이유는 `docs/architecture.md` "인터페이스 계약" 절의 목록이 정본이다. 어느 것도 판정 기준이 아니고 hang 방지와 시계 이상 검출이다.

PX4 timestamp.

- PX4 메시지의 `timestamp` 필드(us)는 PX4 hrt 시각이다. SITL에서 PX4 hrt는 Gazebo `/world/<월드>/clock`의 `sim` 시간(us)이고(gz_bridge가 clock 콜백마다 PX4 lockstep 시계에 쓴다. `src/modules/simulation/gz_bridge/GZBridge.cpp` 331-347행, `platforms/posix/src/px4/common/drv_hrt.cpp` 106-110행, 484-491행), `/clock`도 같은 `sim` 시간(ros_gz_bridge 변환)이라 두 값 사이에 상수 오프셋은 없다. 다만 `/clock`은 gz-transport, bridge, DDS를 거치는 전달 경로만큼 늦으므로 같은 순간의 두 값은 같지 않다. 이 지연은 측정하지 않았다.
- 그래서 판정과 신선도 검사의 경과 시간은 PX4 `timestamp`를 ROS 시각과 비교하지 않고 메시지를 받은 시점의 ROS 시각으로 잰다. PX4 `timestamp`는 ULog 정렬, PX4 쪽 묵은 setpoint 판정, 같은 토픽 표본끼리의 순서 비교(Executor의 "N회 연속 확인"에서 같은 표본 건너뛰기)에 쓴다.
- 예외 하나: 취소의 지상 분기에서 DISARMED 표본을 셀 때 Executor는 표본의 PX4 `timestamp`를 첫 disarm에 실은 timestamp(노드의 ROS 시각)와 비교한다("취소" 절). `/clock`이 늦으므로(지연 크기는 미측정) 이 비교만으로는 disarm 처리 뒤의 표본임이 보장되지 않는다. 수신 tick 조건(`ros_ws/src/idsim_mission/src/core/rules.cpp`의 `is_after_disarm_send`)은 전송 이전 tick의 표본만 거른다. 처리 전 DISARMED 표본 하나는 지연 창에서 통과할 수 있고, 이를 막는 것은 서로 다른 `timestamp`를 가진 DISARMED 표본 3개의 연속 확인(`kConfirmSamples = 3`)과, arm과 disarm이 같은 `vehicle_command` queue에서 FIFO로 처리된다는 점이다([소스] `Commander.cpp` 1888-1902행. [실측] arm 직후에 disarm을 보낸 10회가 모두 DISARMED로 끝났다). 3개가 되려면 표본 간격 약 0.5 s로 arm이 약 1 s 동안 처리되지 않아야 한다.
- 공통 SITL 파라미터 `UXRCE_DDS_SYNCT=0`(`config/px4/sitl_params.env`)으로 uXRCE-DDS 세션의 시간 동기화를 끈다. 그러면 세션 `time_offset`이 0이다.
- PX4는 /fmu/in 메시지를 받을 때 `timestamp`가 0이면 수신 시각으로 채우고, 아니면 `min(timestamp - time_offset, 수신 시각)`으로 쓴다(`Tools/msg/templates/ucdr/msg.h.em` 167-169행. `config/px4/sitl_params.env`의 근거 주석). 그래서 0이나 벽시계 값을 넣으면 PX4에는 "지금"으로 보이고, 묵은 setpoint를 `COM_OF_LOSS_T`로 판정하는 경로가 조용히 꺼진다. ROS 시각은 PX4 hrt보다 늦으므로 노드가 넣은 값은 이 `min`에서 잘리지 않는다(전달 경로 구조에서 추정한 것이고, 위 지연 미측정과 같은 근거다).
- 규칙: 노드가 /fmu/in에 넣는 `timestamp`는 노드 시계의 ROS 시각(us)이다. 0과 벽시계 값은 보내지 않는다. `idsim_common::Px4Timestamp::now(clock)`가 유일한 생성 경로이고, 시계가 `RCL_ROS_TIME`이면서 ROS 시간 override가 켜져 있고(`/clock` 구독 중) 값이 1 us 이상일 때만 값을 만든다. 그 밖(override가 꺼진 ROS 시계, `RCL_SYSTEM_TIME`, `RCL_STEADY_TIME`, `/clock` 수신 전의 0)에서는 값이 없고, 값이 없으면 /fmu/in에 아무것도 보내지 않는다. Executor는 activate 때 값을 만들 수 없으면 activate를 실패시키고, goal 실행 중에 만들 수 없으면 그 tick의 발행과 명령을 버리고 goal을 ABORTED로 끝낸다(정리 중이 아니면 `REASON_INTERNAL`, 정리 중이면 원래 reason을 유지하고 detail에 적는다. `ros_ws/src/idsim_mission/src/core/mission_runner.cpp`). `VehicleCommandBuilder`와 setpoint 헬퍼는 `Px4Timestamp` 인자로만 timestamp를 받는다(`ros_ws/src/idsim_common/include/idsim_common/px4_timestamp.hpp`, `test/test_px4_timestamp.cpp`).
- `UXRCE_DDS_SYNCT=0`에서 uXRCE-DDS client는 시간 동기화 콜백을 달지 않으므로(`on_time_no_sync`. `src/modules/uxrce_dds_client/uxrce_dds_client.cpp` 206행, 318-323행) client 쪽의 `timesync_status` 발행이 없다. DDS writer는 만들어지므로 `fmu/out/timesync_status` 토픽은 그래프에 남지만 표본은 오지 않는다. MAVLink 모듈이 같은 uORB 토픽에 쓰는 경우(GCS가 TIMESYNC를 보낼 때)는 확인하지 않았다. 이 토픽으로 시간 동기 상태를 판정하지 않고, 이 토픽의 수신을 기다리지 않는다.
- `UXRCE_DDS_SYNCT=0`은 SITL 전용 값이다. 실기체에서는 1로 되돌리며, 파라미터 한 줄이라 운용 노드는 차이를 모른다.

## 정의 작성 규칙

고정 시점: 1a 완료.

`idsim_interfaces`의 정의 파일을 고치거나 더할 때 지킨다. 앞의 둘은 계약 테스트의 guard가 잡고, 나머지는 검토 항목이다.

- string 상수와 기본값에 "#"을 넣지 않는다. rosidl 파서는 따옴표 안의 "#"도 주석으로 처리한다.
- 줄 끝 주석에 그 줄 앞부분과 같은 문자열을 쓰지 않는다. `ros2 interface show`가 그 자리에서 줄을 잘라 펼친 정의가 틀려진다("uint8 status  # status"가 "uint8"이 된다). 여러 줄에 걸친 의미 주석은 줄 전체 주석으로 쓴다.
- 이름 상수는 C++에서 namespace 범위 static 변수의 초기화식에 쓰지 않는다(함수와 생성자 안에서만 쓴다). rosidl string 상수는 동적 초기화라 초기화 순서가 정해지지 않는다.
- 필드 이름에 C, C++, Python 예약어를 쓰지 않는다(`goto`는 C 생성기에서 컴파일이 실패해 `go_to`다).
- 주석은 한국어로 쓰고 단위와 좌표계를 필드마다 적는다. `.msg`, `.action`에는 저작권 머리말을 넣지 않는다(type description 원문에 들어간다).
- bounded string이나 공백이 든 기본값을 가진 필드를 더할 때는 계약 테스트의 상수 줄 판정(`"=" in line`)을 상수 정규식 기준으로 바꾼다. 지금은 그런 필드가 없다.

## 변경 절차와 계약 테스트

고정 시점: 1a 완료.

- 메시지 안에 버전 필드나 버전 상수를 두지 않는다. `package.xml` 버전을 계약 식별에 쓰지 않는다. 타입 식별은 type hash(RIHS01)가 한다(상수는 hash에 들어가지 않는다).
- 필드는 끝에 추가만 하고 기존 필드의 이름, 타입, 의미, 단위를 바꾸지 않는다. 상수 값은 재사용하지 않는다. 예약 필드를 미리 두지 않는다(CDR은 위치 기반이라 자리를 잡아도 호환이 생기지 않는다).
- 계약 테스트(`idsim_interfaces/test/`)의 golden은 세 종류다.

| golden | 내용 | 잡는 것 |
| --- | --- | --- |
| `test/golden/type_hashes.txt` | 타입별 RIHS01 한 줄 | 필드 변경. 중첩 타입의 변경이 상위 타입에 번진다 |
| `test/golden/<msg 또는 action>/<Type>.txt` | `ros2 interface show --no-comments` 출력(펼친 정의) | hash가 잡지 못하는 상수 값, 상수 추가, 기본값 변경. 출력의 최상위 줄이 직접 정의와 같은지를 먼저 단정한다 |
| `test/golden/direct/<msg 또는 action>/<Type>.txt` | 그 파일의 직접 필드와 상수만(주석과 빈 줄을 빼고 공백을 정규화) | "고정"의 판정 단위. 고정된 파일의 이 golden이 바뀌면 고정된 계약의 변경이고, 앞의 둘만 바뀌면 중첩 타입에서 온 전파다 |

- 상수 검사: `MissionItem`의 `TYPE_*` 집합, 값 0을 가진 상수는 `*_UNKNOWN` 또는 `*_NONE`뿐, 이름 상수가 이름 규칙과 맞음, `VehicleState.FRAME_ID == TargetState.FRAME_ID`, `MissionEvent`의 `STATUS_*`가 `action_msgs/GoalStatus`의 같은 이름 상수와 같은 값.
- golden이 다르면 테스트가 diff와 어느 종류의 golden인지를 출력하고 실패한다. 자동 갱신은 하지 않는다. 갱신은 `tools/ros_ws.sh shell` 안에서 `IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces`로만 되고, 달라진 golden만 쓰며 파일마다 경고를 낸다.
- 주석은 golden에 들어가지 않는다. 의미 문장만 바뀌는 변경은 golden을 바꾸지 않으며, 이 문서와 정의 주석을 함께 고친다.
- 계약 변경 PR에는 golden 갱신, 이 문서, PR 본문의 결정 근거, (Phase 3 뒤) proto와 왕복 테스트, 영향받는 replay fixture 갱신이 함께 들어가고 계약 owner의 승인이 필요하다.

## 좌표계

고정 시점: 1a 완료.

PX4 쪽은 지구 NED, 동체 FRD이고 ROS와 Gazebo 쪽은 지구 ENU, 동체 FLU다. 변환은 `idsim_common::frames`(`ros_ws/src/idsim_common/include/idsim_common/frames.hpp`) 한 곳에 두고, setpoint를 보낼 때와 표적 pose를 setpoint로 바꿀 때(1b) 모두 이 함수를 쓴다.

| 대상 | PX4 <-> ROS | 함수 |
| --- | --- | --- |
| 지구 벡터(위치, 속도, 가속도) | (n, e, d) <-> (e, n, -d) | `ned_to_enu`, `enu_to_ned` |
| 동체 벡터(각속도, 동체 속도) | (f, r, d) <-> (f, -r, -d) | `frd_to_flu`, `flu_to_frd` |
| 자세 | `q_enu_flu = R_enu_ned * q_ned_frd * R_frd_flu` | `px4_to_ros_orientation`, `ros_to_px4_orientation` |
| yaw | `yaw_enu = wrap_pi(pi/2 - yaw_ned)`, 역변환도 같은 식 | `ned_to_enu_yaw`, `enu_to_ned_yaw` |
| 대각 분산 | 축 치환만, 부호 유지 | `ned_to_enu_variance`, `enu_to_ned_variance` |

- NED yaw는 북 0, 시계방향 양이고 ENU yaw는 동 0, 반시계방향 양이다. 결과는 `[-pi, pi)`다(`wrap_pi`).
- PX4 쿼터니언은 Hamilton 규약, 배열 순서 (w, x, y, z), FRD 동체 -> NED 지구 회전이다. q와 -q는 같은 회전으로 본다.
- 벡터 변환은 축 치환과 부호만 쓰므로 NaN은 그 축에만 남는다(`TrajectorySetpoint`의 NaN은 "제어하지 않음"이다). 비대각 공분산은 다루지 않는다.
- px4_ros_com `frame_transforms`는 래핑하지 않고 `test/test_frames.cpp`의 차등 비교 기준으로만 쓴다(공분산 변환 오류와 NaN 번짐이 있다).
- 원점 이동(world ENU <-> 기체 로컬 NED)은 아직 없다. 1b에 `idsim_common`에 더하고, 입력은 PX4가 실제로 쓰는 원점과 params로 받은 `world.origin`이다.
- 기체 로컬 NED의 원점은 월드 원점이 아니라 그 기체의 EKF 원점이다. SITL에서 EKF 원점은 EKF2가 첫 GNSS fix를 받는 순간의 GNSS 위치다(`src/modules/ekf2/EKF/aid_sources/gnss/gps_control.cpp`의 `resetHorizontalPositionToGnss`, 226-239행, 442-445행). 기체가 스폰 지점에 정지한 채 부팅하므로 스폰 지점 근처지만, GNSS 잡음만큼의 오차가 있을 수 있고 그 크기는 측정하지 않았다. 또 이 원점은 월드 `spherical_coordinates`가 첫 fix 전에 적용되어 있어야 의미가 있다. 그래서 변환 입력은 스폰 pose가 아니라 `vehicle_local_position`의 `ref_lat`, `ref_lon`, `ref_alt`로 한다. 비행 중 EKF 원점이 다시 정해지는 조건은 확인하지 않았다.
- 1a에서 PX4로 가는 setpoint는 기체 로컬 NED 위치(m)와 NED yaw(rad)다(`px4_setpoint.hpp`). ENU 값은 호출자가 `frames`로 바꿔서 넘긴다. 1a 미션의 yaw 입력(`YawSetpoint`)은 ENU yaw이고 `idsim_mission` core가 같은 식으로 NED yaw로 바꾼다(`ros_ws/src/idsim_mission/include/idsim_mission/core/rules.hpp`의 `enu_to_ned_yaw`. core는 ROS 비의존이라 식을 따로 두고 단위 테스트로 덮는다).

## PX4 토픽

고정 시점: 1a 완료.

### 이름 규칙

- 실제 토픽 이름은 `/<기체 네임스페이스>/fmu/{in,out}/<논리 이름>[_v<N>]`이다. 예: `/px4_1/fmu/out/vehicle_status_v1`.
- `_v<N>` 접미사는 px4_msgs 타입의 `MESSAGE_VERSION` 상수에서 파생한다. 상수가 없거나 0이면 접미사가 없다(PX4 `dds_topics.h.em`과 같은 규칙). 접미사는 PX4 태그마다 바뀔 수 있으므로 어디에도 하드코딩하지 않는다.
- C++에서 토픽 이름은 `idsim_common`의 기술자(`idsim_common::px4::topics::*`)로만 얻는다. 기술자는 메시지 타입, 방향, 논리 이름, 발행 허용을 하나로 묶고, 논리 이름에 `_v<N>`을 쓰면 컴파일 오류다. 기술자 목록은 `ros_ws/src/idsim_common/include/idsim_common/detail/px4_topic_list.inc` 하나다. 공개 API는 `px4_io.hpp`의 `topic_name`, `create_subscription`, `create_publisher`다.
- Python(통합 테스트, 스모크)에서는 `tests/support/px4_topic.py`가 같은 규칙으로 이름을 조립한다.
- 다른 패키지와 테스트 코드에 `fmu/in/`, `fmu/out/` 문자열이 생기면 `tools/ci/lint.sh`의 `px4-api` 검사가 실패한다. 예외는 파일 이름으로만 둔다(`tests/support/px4_raw.py`, `tests/support/px4_measure_pub.py`, `tests/support/px4_topic.py`, `tests/support/test_px4_topic_names.py`).
- 골든 비교 테스트: `idsim_common`의 `test_topics_golden`(C++)과 `tests/support/test_px4_topic_names.py`(Python)가 기술자 또는 조립 규칙이 만든 이름 집합과 골든 `topics.txt`의 집합을 양방향으로 비교한다. 골든 디렉터리가 없으면 실패한다. 그래서 PX4 태그를 올려 접미사가 바뀌면 이 테스트가 먼저 실패하고, 소스는 바꾸지 않아도 이름이 따라간다.

### 토픽 표

`tools/to_interface.py`가 `tests/fixtures/px4/v1.17.0/`에서 만든 표다. 토픽 이름은 네임스페이스를 뗀 상대 이름이다. QoS 열은 골든의 발행자 값(reliability, durability, history(depth))이고, /fmu/in 토픽은 골든에 발행자가 없어 "-"다. PX4 쪽 /fmu/in reader의 QoS는 "PX4 토픽 QoS" 절에 있다. 이 표의 토픽 이름은 참고용이며 코드는 이 표가 아니라 기술자로 이름을 얻는다.

| 토픽 | 방향 | 타입 | 발행자 QoS |
| --- | --- | --- | --- |
| `fmu/in/actuator_motors` | ROS 2 -> PX4 | `px4_msgs/msg/ActuatorMotors` | - |
| `fmu/in/actuator_servos` | ROS 2 -> PX4 | `px4_msgs/msg/ActuatorServos` | - |
| `fmu/in/arming_check_reply_v1` | ROS 2 -> PX4 | `px4_msgs/msg/ArmingCheckReply` | - |
| `fmu/in/aux_global_position` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleGlobalPosition` | - |
| `fmu/in/config_control_setpoints` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleControlMode` | - |
| `fmu/in/config_overrides_request` | ROS 2 -> PX4 | `px4_msgs/msg/ConfigOverrides` | - |
| `fmu/in/distance_sensor` | ROS 2 -> PX4 | `px4_msgs/msg/DistanceSensor` | - |
| `fmu/in/fixed_wing_lateral_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/FixedWingLateralSetpoint` | - |
| `fmu/in/fixed_wing_longitudinal_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/FixedWingLongitudinalSetpoint` | - |
| `fmu/in/goto_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/GotoSetpoint` | - |
| `fmu/in/landing_gear` | ROS 2 -> PX4 | `px4_msgs/msg/LandingGear` | - |
| `fmu/in/lateral_control_configuration` | ROS 2 -> PX4 | `px4_msgs/msg/LateralControlConfiguration` | - |
| `fmu/in/longitudinal_control_configuration` | ROS 2 -> PX4 | `px4_msgs/msg/LongitudinalControlConfiguration` | - |
| `fmu/in/manual_control_input` | ROS 2 -> PX4 | `px4_msgs/msg/ManualControlSetpoint` | - |
| `fmu/in/message_format_request` | ROS 2 -> PX4 | `px4_msgs/msg/MessageFormatRequest` | - |
| `fmu/in/mode_completed` | ROS 2 -> PX4 | `px4_msgs/msg/ModeCompleted` | - |
| `fmu/in/obstacle_distance` | ROS 2 -> PX4 | `px4_msgs/msg/ObstacleDistance` | - |
| `fmu/in/offboard_control_mode` | ROS 2 -> PX4 | `px4_msgs/msg/OffboardControlMode` | - |
| `fmu/in/onboard_computer_status` | ROS 2 -> PX4 | `px4_msgs/msg/OnboardComputerStatus` | - |
| `fmu/in/register_ext_component_request` | ROS 2 -> PX4 | `px4_msgs/msg/RegisterExtComponentRequest` | - |
| `fmu/in/rover_attitude_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverAttitudeSetpoint` | - |
| `fmu/in/rover_position_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverPositionSetpoint` | - |
| `fmu/in/rover_rate_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverRateSetpoint` | - |
| `fmu/in/rover_speed_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverSpeedSetpoint` | - |
| `fmu/in/rover_steering_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverSteeringSetpoint` | - |
| `fmu/in/rover_throttle_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/RoverThrottleSetpoint` | - |
| `fmu/in/sensor_optical_flow` | ROS 2 -> PX4 | `px4_msgs/msg/SensorOpticalFlow` | - |
| `fmu/in/telemetry_status` | ROS 2 -> PX4 | `px4_msgs/msg/TelemetryStatus` | - |
| `fmu/in/trajectory_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/TrajectorySetpoint` | - |
| `fmu/in/unregister_ext_component` | ROS 2 -> PX4 | `px4_msgs/msg/UnregisterExtComponent` | - |
| `fmu/in/vehicle_attitude_setpoint_v1` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleAttitudeSetpoint` | - |
| `fmu/in/vehicle_command` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleCommand` | - |
| `fmu/in/vehicle_command_mode_executor` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleCommand` | - |
| `fmu/in/vehicle_mocap_odometry` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleOdometry` | - |
| `fmu/in/vehicle_rates_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleRatesSetpoint` | - |
| `fmu/in/vehicle_thrust_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleThrustSetpoint` | - |
| `fmu/in/vehicle_torque_setpoint` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleTorqueSetpoint` | - |
| `fmu/in/vehicle_visual_odometry` | ROS 2 -> PX4 | `px4_msgs/msg/VehicleOdometry` | - |
| `fmu/out/airspeed_validated_v1` | PX4 -> ROS 2 | `px4_msgs/msg/AirspeedValidated` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/arming_check_request_v1` | PX4 -> ROS 2 | `px4_msgs/msg/ArmingCheckRequest` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/battery_status_v1` | PX4 -> ROS 2 | `px4_msgs/msg/BatteryStatus` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/collision_constraints` | PX4 -> ROS 2 | `px4_msgs/msg/CollisionConstraints` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/estimator_status_flags` | PX4 -> ROS 2 | `px4_msgs/msg/EstimatorStatusFlags` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/failsafe_flags` | PX4 -> ROS 2 | `px4_msgs/msg/FailsafeFlags` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/gimbal_device_attitude_status` | PX4 -> ROS 2 | `px4_msgs/msg/GimbalDeviceAttitudeStatus` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/home_position_v1` | PX4 -> ROS 2 | `px4_msgs/msg/HomePosition` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/manual_control_setpoint` | PX4 -> ROS 2 | `px4_msgs/msg/ManualControlSetpoint` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/message_format_response` | PX4 -> ROS 2 | `px4_msgs/msg/MessageFormatResponse` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/mode_completed` | PX4 -> ROS 2 | `px4_msgs/msg/ModeCompleted` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/position_setpoint_triplet` | PX4 -> ROS 2 | `px4_msgs/msg/PositionSetpointTriplet` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/register_ext_component_reply` | PX4 -> ROS 2 | `px4_msgs/msg/RegisterExtComponentReply` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/sensor_combined` | PX4 -> ROS 2 | `px4_msgs/msg/SensorCombined` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/timesync_status` | PX4 -> ROS 2 | `px4_msgs/msg/TimesyncStatus` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/transponder_report` | PX4 -> ROS 2 | `px4_msgs/msg/TransponderReport` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_attitude` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleAttitude` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_command_ack` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleCommandAck` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_control_mode` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleControlMode` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_global_position` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleGlobalPosition` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_gps_position` | PX4 -> ROS 2 | `px4_msgs/msg/SensorGps` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_land_detected` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleLandDetected` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_local_position_v1` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleLocalPosition` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_odometry` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleOdometry` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vehicle_status_v1` | PX4 -> ROS 2 | `px4_msgs/msg/VehicleStatus` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/vtol_vehicle_status` | PX4 -> ROS 2 | `px4_msgs/msg/VtolVehicleStatus` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |
| `fmu/out/wind` | PX4 -> ROS 2 | `px4_msgs/msg/Wind` | BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST(1) |

- 65개다(in 38, out 27). `mode_completed`는 in과 out 양쪽에 있다. 같은 타입을 여러 토픽이 쓰고(`VehicleCommand`, `VehicleOdometry` 등) 논리 이름과 타입 이름이 다른 토픽이 있다(`vehicle_gps_position`은 `SensorGps`). 그래서 타입에서 이름을 만들거나 타입으로 이름을 역조회하지 않는다.
- 측정 주기는 계약이 아니다. 수신 판정은 "T초 안에 1회 이상"이고 주기에 묶지 않는다. 주기 하한 계약은 필요한 토픽에 한해 Phase 3에서 넣는다. 이 표에는 측정 주기 열을 두지 않는다(골든에는 주기가 없고, 주기 참고값은 환경 스모크의 원시 산출물에서만 나온다).

### 공개 /fmu/in 목록과 허용 절차

idsim이 발행할 수 있는 /fmu/in은 셋뿐이다.

| 논리 이름 | 타입 | 발행 주체 | 만드는 함수 |
| --- | --- | --- | --- |
| `offboard_control_mode` | `OffboardControlMode` | 기체별 Mission Executor | `idsim_common::px4::offboard_position_mode` |
| `trajectory_setpoint` | `TrajectorySetpoint` | 기체별 Mission Executor | `idsim_common::px4::position_setpoint` |
| `vehicle_command` | `VehicleCommand` | 기체별 Mission Executor | `idsim_common::VehicleCommandBuilder` |

- 나머지 /fmu/in 35개와 /fmu/out 전부는 `Restricted`이고 공개 API로 발행자를 만들 수 없다(`create_publisher`의 `static_assert`, 음성 컴파일 테스트 `test/compile_fail/`). /fmu/out은 구독만 한다.
- Fleet Manager, Telemetry Collector, 그 밖의 운용 서비스는 /fmu/in에 쓰지 않는다.
- 테스트 harness의 예외는 둘이다. `tests/support/px4_raw.py`(통합 테스트. 시나리오 T의 `offboard_control_mode`와 비상 정리 전용 `vehicle_command`), `tests/support/px4_measure_pub.py`(PX4 재실측 전용. `tests/sitl/measure/` 밖에서 쓰지 않는다).
- `Restricted`를 `Allowed`로 바꾸는 PR에는 다섯 가지가 함께 있어야 한다. (1) `px4_topic_list.inc`의 해당 항목 변경, (2) PX4 인터페이스 owner의 승인, (3) PR 본문에 허용 근거, (4) `test_topics_traits`의 허용 목록 기대 집합 갱신, (5) 이 문서의 공개 /fmu/in 목록 갱신.
- 발행 차단은 실수 방지 수준이며 보안 경계가 아니다. rclcpp를 직접 부르거나 이름 문자열을 직접 쓰는 우회는 `px4-api` lint와 코드 리뷰로만 잡는다. 같은 DDS 도메인의 어떤 참가자도 /fmu/in에 쓸 수 있다.

### PX4 토픽 QoS

reliability와 durability가 계약이다. history와 depth는 계약 밖이다(골든의 `depth=1`은 rmw가 원격 엔드포인트에 보여 주는 값이다). PX4 쪽 엔드포인트는 uXRCE-DDS Agent가 PX4 client의 요청으로 만드는 엔드포인트다.

| 방향 | PX4 쪽 엔드포인트 | idsim 쪽 엔드포인트 | 함수 |
| --- | --- | --- | --- |
| /fmu/out | writer: BEST_EFFORT, TRANSIENT_LOCAL(골든 `qos/fmu/out/*.txt` 27개 모두 같다. `src/modules/uxrce_dds_client/utilities.hpp` 78-82행) | reader: BEST_EFFORT, VOLATILE | `px4_out_qos()` |
| /fmu/in | reader: BEST_EFFORT, VOLATILE(`src/modules/uxrce_dds_client/utilities.hpp` 136-137행) | writer: BEST_EFFORT, VOLATILE | `px4_in_qos()` |

- 두 함수는 `ros_ws/src/idsim_common/include/idsim_common/qos.hpp`에 있고 구현 값은 KEEP_LAST 5, liveliness Automatic이다. 이 값은 `rmw_qos_profile_sensor_data`의 reliability, durability와 같다. Python 판정 코드는 `qos_profile_sensor_data`를 쓴다.
- 기본 QoS(RELIABLE) 구독은 PX4의 BEST_EFFORT writer와 맞지 않아 아무것도 받지 못한다. 그래서 `create_subscription`과 `create_publisher`는 options의 `qos_overriding_options`를 비워 `qos_overrides.*` 파라미터로 QoS를 바꾸지 못하게 한다.
- TRANSIENT_LOCAL 구독은 쓰지 않는다. 에이전트가 늦게 붙은 reader에게 이력을 주지 않음을 실측했다. 구독자는 연결 직후 첫 표본을 기다린다.
- BEST_EFFORT라 /fmu/in 명령은 손실될 수 있다. 명령을 보내는 쪽은 ack 또는 상태 관측으로 확인하고, 확인될 때까지 다시 보낸다. Executor는 확인을 기다리는 명령을 `command_resend_period`(기본 0.5 s, ROS 시각)마다 다시 보낸다(`ros_ws/src/idsim_mission/include/idsim_mission/core/config.hpp`). 한 번만 보내고 확인하지 않는 예외(지상 disarm 1회 등)는 "비행 중 감시" 절에 있다.

## 기체 식별과 네임스페이스

고정 시점: 1a 완료.

기체 식별자는 `config/fleet.yaml`의 기체 번호 N(1-9)과 생성 인자 스택 번호 k(0-9)에서 `tools/gen_compose.py`가 파생해 `artifacts/runs/<실행 id>/stack.json`과 `params/ops-N.yaml`에 적는다. 노드와 테스트는 파생 공식을 다시 계산하지 않고 이 파일들만 읽는다.

| 식별자 | 값 | 어디서 정해지는가 |
| --- | --- | --- |
| PX4 인스턴스 | N | `px4 -d -i N`(`tools/gen_compose.py`) |
| `MAV_SYS_ID` | N + 1 | PX4 rcS가 인스턴스 번호에서 정한다(`ROMFS/px4fmu_common/init.d-posix/rcS` 140행). 생성기는 `stack.json`의 `derived_params`에 기대값만 적고, 스모크가 `pxh param show`로 대조한다 |
| `UXRCE_DDS_KEY` | N + 1 | 위와 같다(rcS 141행) |
| `UXRCE_DDS_DOM_ID` | 20 + k | px4 서비스의 `ROS_DOMAIN_ID` 환경변수를 rcS가 읽는다(rcS 310-315행. 비어 있으면 0이 되어 스택 도메인을 놓친다) |
| `SYS_AUTOSTART` | airframe 번호(1a는 4001) | `PX4_SYS_AUTOSTART`(생성기, `airframe`에서 파생) |
| ROS 네임스페이스 | `/px4_N` | `PX4_UXRCE_DDS_NS=px4_N` |
| `vehicle_id` | `px4_N`(네임스페이스에서 앞의 "/"를 뗀 것) | 생성기가 `stack.json`과 `vehicle.id` param에 싣는다 |
| Gazebo 모델 이름 | `x500_N`(airframe의 시뮬레이터 모델에서 `gz_`를 뗀 것) | 생성기 |
| compose 서비스 | `px4-N`, `ops-N` | 생성기. 프로젝트 이름은 `idsim-k` |
| Executor 노드 | `/px4_N/mission_executor` | 생성기 상수 `EXECUTOR_NODE_NAME`, `stack.json`의 `executor_node` |

- N은 1부터다. PX4 인스턴스 0의 "네임스페이스 없음"은 어디서도 쓰지 않고 네임스페이스를 항상 명시한다.
- `config/fleet.yaml`에는 파생값을 적을 수 없고, 기체별 `px4_params`에도 `MAV_SYS_ID`, `UXRCE_DDS_KEY`, `UXRCE_DDS_DOM_ID`, `UXRCE_DDS_AG_IP`, `SYS_AUTOSTART`를 적을 수 없다(생성기가 거부한다). rcS의 위 행은 `PX4_PARAM_*` 환경변수 적용(rcS 129-135행)보다 뒤라 환경변수로 주어도 덮인다.
- 노드 params는 `vehicle.id`, `vehicle.ns`, `vehicle.sysid` 셋이고 기본값이 없다. 누락, 타입 불일치, 해석 실패, `vehicle.ns != "/" + vehicle.id`이면 configure가 실패한다(`vehicle_params.hpp`). 노드는 자기 네임스페이스가 `vehicle.ns`와 같은지도 본다.
- `idsim_common`의 타입은 빈 네임스페이스, "/"만 있는 네임스페이스, 토큰이 여럿인 `vehicle_id`, sysid 0(브로드캐스트)을 만들지 못한다(`vehicle.hpp`의 `VehicleNamespace`, `VehicleId`, `SystemId`). 소비자는 `vehicle_id`의 내용을 해석하지 않는다(N을 뽑거나 sysid를 계산하지 않는다).

sysid 대조 규칙.

- 노드는 받은 `vehicle_status`의 `system_id`가 params의 `vehicle.sysid`와 같고 `component_id`가 1(`MAV_COMP_ID_AUTOPILOT1`)인지 `idsim_common::verify`로 본다. 결과는 `Match`, `SystemIdMismatch`, `ComponentIdMismatch`이고 둘 다 틀리면 `SystemIdMismatch`다.
- `vehicle_status`를 아직 받지 못한 동안은 명령과 발행을 보류한다. 대조가 어긋나면 오류다. Executor에서는 goal의 준비 단계에서 확인하고, 발행 시작 전의 불일치는 NOT_READY, 시작 뒤의 불일치는 REASON_INTERNAL로 끝난다.
- PX4 Commander는 `target_system`이 자기 `MAV_SYS_ID`이거나 0이고 `target_component`가 자기 component id(1)이거나 0인 명령만 처리한다(`src/modules/commander/Commander.cpp` `handle_command` 746-749행). idsim은 0(브로드캐스트)을 보내지 않는다.

## VehicleCommand

고정 시점: 1a 완료.

`idsim_common::VehicleCommandBuilder`(`vehicle_command.hpp`)가 유일한 생성 경로다. 대상(`VehicleIdentity`: 네임스페이스와 sysid)과 송신자(`CommandSource`) 없이는 만들 수 없다.

| 메서드 | command | param |
| --- | --- | --- |
| `arm` | 400 `COMPONENT_ARM_DISARM` | param1 = 1(강제 시동 21196은 두지 않는다) |
| `disarm` | 400 | param1 = 0 |
| `set_mode_offboard` | 176 `DO_SET_MODE` | param1 = 1(custom mode), param2 = 6(OFFBOARD) |
| `set_mode_hold` | 176 | param1 = 1, param2 = 4(AUTO), param3 = 3(AUTO_LOITER) |
| `land` | 21 `NAV_LAND` | param1-3 = 0, param4-7 = NaN(현재 위치와 yaw로 착륙) |
| `rtl` | 20 `NAV_RETURN_TO_LAUNCH` | 모두 0 |

- `DO_SET_MODE`의 custom mode 값(6, 4, 3)은 `px4_custom_mode.h`와 직접 대조하지 않았고, Offboard 진입(시나리오 A)과 Hold 전환(시나리오 D)의 실측이 근거다.
- 고정 필드: `target_system` = 대상 sysid, `target_component` = 1, `from_external` = true, `confirmation` = 0, `timestamp` = `Px4Timestamp`.
- `from_external`을 true로 고정한다. false이면 `COMMAND_LONG` 스트림이 명령을 MAVLink로 재송출한다(`src/modules/mavlink/streams/COMMAND_LONG.hpp` 90-93행. 조건은 `!from_external`, PX4 내부 명령(`VEHICLE_CMD_PX4_INTERNAL_START` 이상)이 아님, 송신자가 대상 autopilot 자신이 아님의 셋이다). idsim의 송신자는 대상 autopilot과 달라 세 번째 조건을 만족하므로 false이면 재송출된다. 또 Commander는 arm에서 `from_external`로 사유를 가른다(`Commander.cpp` 965행 `command_external`과 `command_internal`, 969행 preflight 검사 실행 여부). true가 외부 명령의 정상 경로다.
- 송신자는 `source_system` 1-255, `source_component` 1-999다(1000 이상은 PX4가 mode executor로 분류한다. `Commander.cpp` 1561-1562행, `VehicleCommand.msg`의 `COMPONENT_MODE_EXECUTOR_START`). `source_system`이 대상 sysid와 같으면 빌더를 만들 수 없다(송신자가 대상 autopilot 자신으로 보이는 조합을 막는다).
- 검증 없는 raw 명령은 두지 않는다. 새 명령은 PX4 인터페이스 owner의 승인 뒤 메서드로 더한다.
- ack 매칭: `is_ack_for(ack, cmd)`는 `command`가 같고 ack의 `target_system`, `target_component`가 cmd의 `source_system`, `source_component`인지 본다(PX4는 ack를 송신자에게 돌려준다).
- ack ACCEPTED는 성공이 아니다. ack는 명령을 받아들였다는 뜻이고 전환 결과의 확인이 아니다. ACCEPTED 뒤에 모드 전환이 일어나지 않는 경로가 있는지는 확인하지 않았다(미확인). 보수적 동작: 모드 전환 성공은 `vehicle_status.nav_state`로, arm과 disarm은 `arming_state`로 확인하고, ack는 거부를 빨리 아는 데만 쓴다.

source 값(노드 params와 테스트 상수. 서로 겹치지 않게 둔다).

| 송신자 | `source_system` | `source_component` |
| --- | --- | --- |
| `idsim_mission` Executor(`command_source.system`, `command_source.component` 기본값) | 254 | 191 |
| SITL 통합 테스트 비상 정리(`tests/support/px4_raw.py`) | 254 | 25 |
| 스모크 `tests/smoke/check_px4.py`, 측정 전용 `tests/support/px4_measure_pub.py` | 254 | 1 |

- 254는 어떤 기체 sysid(2-10)와도 같지 않다. 255와 component 190은 QGroundControl의 기본값이라 쓰지 않는다.

## Offboard setpoint

고정 시점: 1a 완료.

- 1a는 position 제어만 쓴다. `offboard_control_mode`는 `position = true`이고 나머지 여섯 flag(velocity, acceleration, attitude, body_rate, thrust_and_torque, direct_actuator)는 false다.
- `trajectory_setpoint`의 `position`(로컬 NED, m)과 `yaw`(NED, rad)는 유한값이고 float 범위 안이어야 한다. `velocity`, `acceleration`, `jerk`, `yawspeed`는 NaN("제어하지 않음")이다. 둘 다 `px4_setpoint.hpp`의 함수로만 만든다.
- yaw는 항상 유한값으로 보낸다. NaN yaw의 Offboard 동작은 미확인이다. 보수적 동작: 보내지 않는다(현재 heading을 유지하려면 현재 yaw를 넣는다).
- 언제 발행하는가(Offboard 진입 준비와 Offboard 동안만)는 "발행 규칙" 절이 정한다.

## SITL 파라미터

고정 시점: 1a 완료.

공통 SITL 파라미터는 `config/px4/sitl_params.env`(`config/fleet.yaml`의 `px4.params_file`) 한 파일이다. 형식은 `PX4_PARAM_<이름>=<값>`이고 compose가 px4 서비스에 `env_file`로 넘긴다. PX4 rcS가 airframe 스크립트보다 먼저 `param set`하고(rcS 129-135행), px4 이미지의 airframe 훅(`<airframe>.post`, `docker/Dockerfile.px4`)이 airframe 뒤에 한 번 더 적용해 이 파일의 값이 최종값이 된다(펌웨어 기본값과 같은 값은 airframe의 `set-default`가 덮어쓰기 때문이다). 실제 적용 값은 환경 스모크가 `pxh param show`로 `stack.json`의 `expected_params`, `derived_params`와 대조한다.

계약으로 고정하는 값(근거는 `config/px4/sitl_params.env`의 항목 주석).

| 파라미터 | 값 | 의미 | 고정하는 이유 |
| --- | --- | --- | --- |
| `COM_OBL_RC_ACT` | 4 | Offboard 손실 시 Land | 그 자리에서 내려와 착지 뒤 자동 disarm으로 끝난다. Return은 다대에서 경로가 겹칠 수 있고, Hold는 손실이 길어지면 제자리에 남아 미션이 끝나지 않는다. 1b 상태기의 실패 폴백은 이 값과 일치시킨다 |
| `COM_OF_LOSS_T` | 1.0 s | Offboard 손실 판정 시간 | 기본값과 같지만 명시한다. 20 Hz 발행에서 연속 20개 손실이다 |
| `NAV_DLL_ACT` | 0 | GCS 연결 손실 동작 끔 | airframe 기본은 Return이다. QGC를 붙였다 떼는 것만으로 RTL이 걸리지 않게 한다 |
| `COM_RC_IN_MODE` | 4 | 수동 조종 입력 끔 | 수동 조종 손실 failsafe(`NAV_RCL_ACT`)를 검사하지 않게 해 외부 입력이 붙었다 끊겨도 Offboard 중 failsafe가 걸리지 않는다 |
| `COM_DISARM_PRFLT` | -1 | 이륙 전 자동 disarm 끔 | 시동과 이륙 사이 간격이 부하로 길어져도 PX4가 스스로 disarm하지 않는다. 착지 뒤 자동 disarm(`COM_DISARM_LAND`, 기본 2 s)은 그대로다 |
| `SDLOG_MODE` | 2 | ULog를 부팅부터 종료까지 | 컨테이너 한 번 실행에 ULog 한 파일. 첫 disarm 뒤 기록도 남는다 |
| `UXRCE_DDS_SYNCT` | 0 | uXRCE-DDS 시간 동기화 끔 | "시간 기준" 절. SITL 전용이고 실기체에서는 1 |

- `NAV_DLL_ACT` 값 0이 "GCS 연결 손실 failsafe를 걸지 않음"이라는 것은 navigator 파라미터 원문과 대조하지 않았다(미확인. 0이 아닐 때만 연결 손실 failsafe를 거는 쪽은 `failsafe.cpp` 515행으로 확인했다). 보수적 동작: 판정과 CI에 QGC를 쓰지 않는다.
- 기체별 `px4_params`는 공통 파일 값을 덮을 수 있고 생성기는 경고만 낸다. 위 표의 파라미터를 기체별로 덮으면 그 기체는 이 계약 밖이다.
- `PX4_SIM_SPEED_FACTOR`는 주지 않는다(주면 rcS 197-210행이 `COM_OF_LOSS_T` 등 손실 타임아웃을 덮어쓴다). 배속은 Phase 3에서 정한다.
- `COM_RC_IN_MODE=4`의 영향: QGroundControl의 수동 모드 비행과 가상 조이스틱을 쓸 수 없다. QGC는 모니터링과 ARM, TAKEOFF, LAND 같은 명령에만 쓴다. 수동 계열 모드(Position, Altitude, Manual) 진입이 가능한지와 부팅 직후의 기본 모드는 확인하지 않았다(미확인). 보수적 동작: idsim은 수동 계열 모드를 요청하지 않고, Executor는 부팅 모드에 기대지 않고 arm 전에 Offboard를 요청한다.
- 생성기가 px4 서비스 환경에 넣는 값(파라미터 파일 밖): `PX4_SYS_AUTOSTART`, `PX4_SIM_MODEL`, `PX4_GZ_WORLD`, `PX4_GZ_MODELS`, `PX4_GZ_MODEL_POSE`, `PX4_GZ_STANDALONE=1`, `PX4_UXRCE_DDS_NS`, `PX4_UXRCE_DDS_PORT`, `ROS_DOMAIN_ID`, `IDSIM_MAVLINK_OFFSET`, `GZ_PARTITION`, `GZ_IP`(`tools/gen_compose.py`).
- px4 서비스에는 `PX4_HOME_*`를 주지 않는다. 월드 원점은 gazebo wrapper가 `world.origin`으로 적용한다. gz 경로에서 `PX4_HOME_*`의 소비자는 `px4-rc.gzsim`의 원점 호출뿐이지만 SIH 경로 `px4-rc.sihsim`도 이 변수를 읽는다. SIH 변형을 더할 때는 원점의 출처가 둘이 되지 않도록 `PX4_HOME_*`와 `world.origin`의 관계를 다시 정한다. 지금 SIH 변형은 없다(생성기 단위 테스트 `tests/tools/test_gen_compose.py`가 `PX4_HOME_*`의 부재를 단정한다).

## 포트

고정 시점: 1a 완료.

스택 번호 k(0-9)와 기체 번호 N(1-9)에서 파생한다. 식의 정본은 `tools/gen_compose.py`의 상수이고, 실행 시점의 값은 `stack.json`에 있다. 모든 컨테이너가 `network_mode: host`라 스택은 아래 값으로만 갈린다.

| 용도 | 프로토콜 | 식 | k = 0, N = 1 | 정해지는 곳 |
| --- | --- | --- | --- | --- |
| ROS 2 도메인 | DDS | `ROS_DOMAIN_ID` = 20 + k | 20 | `tools/gen_compose.py` |
| DDS 포트 구간 | RTPS UDP | 7400 + 250 x (20 + k) 부터 249개. 실사용 끝은 참가자 인덱스 상한 50에서 + 11 + 2 x 50 | 12400-12649(실사용 12511까지) | `tools/gen_compose.py`, `config/cyclonedds.xml` |
| uXRCE-DDS 에이전트 | UDP | 8888 + k(`PX4_UXRCE_DDS_PORT`와 같다) | 8888 | `tools/gen_compose.py` |
| gz-transport | - | `GZ_PARTITION` = `idsim-k`, `GZ_IP` = 127.0.0.1 | `idsim-0` | `tools/gen_compose.py` |
| MAVLink GCS(원격, QGC가 듣는다) | UDP | 14550 + 1000k(스택 안 모든 기체 공통) | 14550 | `docker/px4/px4-rc.mavlink` |
| MAVLink GCS(PX4 로컬) | UDP | 18570 + 1000k + N | 18571 | `docker/px4/px4-rc.mavlink` |
| MAVLink 온보드 API(원격) | UDP | 14540 + 1000k + N | 14541 | `docker/px4/px4-rc.mavlink` |
| MAVLink 온보드 API(PX4 로컬) | UDP | 14580 + 1000k + N | 14581 | `docker/px4/px4-rc.mavlink` |
| foxglove(`viz` 프로필) | WebSocket | 127.0.0.1:8765 + k | 8765 | `tools/gen_compose.py` |
| lichtblick(`viz` 프로필) | HTTP | 127.0.0.1:18080 + k | 18080 | `tools/gen_compose.py` |

- MAVLink 오프셋 1000k는 생성기가 `IDSIM_MAVLINK_OFFSET`으로 넘기고 idsim용 `px4-rc.mavlink`(px4 이미지가 PATH 맨 앞에 둔다)가 더한다. 오프셋을 뺀 값은 상류 파일의 포트와 같다. 오프셋은 0 또는 9000 이하의 앞자리 0 없는 정수만 받고, N > 9이면 PX4 기동이 실패한다. 상류 파일과 달리 payload와 gimbal 링크는 열지 않는다.
- 생성기는 k 0-9, N 1-9를 모두 동시에 올린다고 보고 위 구간이 서로 겹치지 않으며 임시 포트 범위(32768 이상)에 들어가지 않음을 단정한다(`check_port_plan`). CycloneDDS의 `MaxAutoParticipantIndex`가 64를 넘으면 DDS 포트가 이웃 스택의 MAVLink 포트와 겹치므로 생성을 거부한다(`config/cyclonedds.xml` 주석).
- 온보드 API 포트(14540 + 1000k + N)는 1a에서 쓰는 주체가 없다. idsim의 명령 경로는 uXRCE-DDS다.
- SIH 표시용 MAVLink 링크(`PX4_SIMULATOR=sihsim`일 때 19450 + N, 19410 + N)에는 오프셋이 없다. 지금 SIH 변형이 없어 열리지 않는다.
- 환경 스모크는 px4 로그에 MAVLink `bind failed`가 없음을 판정한다. bind에 실패한 PX4의 동작은 미확인이다. 보수적 동작: 스모크 실패로 본다.

QGroundControl.

- QGC는 compose 밖의 호스트 앱이고 `tools/qgc.sh --stack k`로 띄운다. 스크립트가 QGC 설정의 자동 연결 UDP 포트를 14550 + 1000k로 고친다.
- 한 스택의 모든 기체가 같은 GCS 포트로 보내므로 QGC 하나가 그 스택의 N대를 `MAV_SYS_ID`로 구분해 보인다.
- `MAV_SYS_ID`는 스택 간에 같다(스택 k와 무관하게 N + 1). 그래서 QGC 하나는 한 번에 한 스택만 본다. 다른 스택을 보려면 QGC를 `--stack`을 바꿔 다시 띄운다.
- QGC는 판정과 CI에 쓰지 않는다. QGC에서 보낸 모드 전환이나 disarm은 Executor에게 외부 명령으로 보인다.

## 미션 정의: Mission, MissionItem, YawSetpoint, TakeoffItem, LoiterItem

고정 시점: 1a 완료.

미션은 항목의 목록이고, 항목은 `type`과 그 type의 서브메시지 하나로 이뤄진다.

- `Mission.mission_id`: `mission_id` 규칙의 문자열. 발급 주체는 1b에서는 YAML 로더, Phase 3에서는 Fleet이다. `Mission.items`: 1개 이상이고 순서대로 실행한다.
- `MissionItem.type`: `TYPE_*`. 0은 무효다. `MissionItem.timeout`: 이 항목의 제한 시간(ROS 시각). 0보다 크다. 넘기면 ITEM_TIMEOUT이다. 기준 시각은 항목이 시작된 시각이다(첫 항목인 TAKEOFF는 준비 단계의 arm 확인 시점. "준비 단계" 절).
- 서브메시지는 type에 맞는 하나만 채우고 나머지는 기본값이어야 한다. RTL과 LAND는 서브메시지가 없다.
- 항목은 두 부류다. setpoint 항목(TAKEOFF, GOTO, TRACK_ENTITY, LOITER)은 Offboard setpoint로 처리하고, 모드 명령 항목(RTL, LAND)은 PX4 고유 모드로 전환한다. 이 구분은 필드로 두지 않고 type에서 파생한다. 모든 `TYPE_*`가 정확히 한 부류에 속한다는 것을 `idsim_mission` 단위 테스트가 단정한다.
- 모든 값은 명시적이다. "0이면 기본값" 규칙은 없다. 기본값은 미션을 만드는 쪽(YAML 로더)이 채운다. 표적 신선도 임계, setpoint 주기 같은 안전 값은 메시지가 아니라 노드 파라미터다.
- 좌표는 world ENU 하나다. 미션은 기체에 묶이지 않으므로 재배분 때 다시 쓰지 않는다.

| 정의 | 필드 | 의미 |
| --- | --- | --- |
| `YawSetpoint` | `mode` | `MODE_KEEP`(1): 항목의 기준 yaw를 유지한다(TAKEOFF는 기준 위치를 읽을 때의 heading). `MODE_FIXED`(2): `yaw_rad`로. 0은 무효 |
| `YawSetpoint` | `yaw_rad` | world ENU yaw, `[-pi, pi)`. `MODE_FIXED`일 때만 쓰고 아니면 0이어야 한다 |
| `TakeoffItem` | `height_m` | 기준 위치에서 올라갈 상대 높이(m). 0보다 크다. 기준 위치는 준비 단계에서 setpoint 발행을 시작할 때(arm 전, 지상) 읽은 위치다 |
| `TakeoffItem` | `acceptance_m` | 수직 허용 오차(m). 0보다 크다 |
| `TakeoffItem` | `yaw` | 상승 중의 yaw |
| `LoiterItem` | `duration` | 항목 시작 때의 setpoint를 유지할 시간(ROS 시각). 0보다 크고 그 항목의 `timeout`보다 짧다 |

항목의 의미(1a에 구현된 셋).

| 항목 | 시작 조건 | 동작 | 완료 | feedback phase |
| --- | --- | --- | --- | --- |
| TAKEOFF | 지상(`landed` true)이고 DISARMED. 아니면 PRECONDITION_FAILED | 준비 단계에서 setpoint 발행을 시작할 때(arm 전, 지상) 읽은 위치가 기준 위치다. 목표점은 그 위치 위 `height_m`이고 처음부터 목표점을 보낸다. `MODE_KEEP`의 yaw는 그때의 heading이다. 비행제어의 자동 이륙 모드가 아니라 Offboard position setpoint로 상승한다. 상승 속도는 비행제어 파라미터가 제한한다 | 고도 추정이 유효하고 목표 고도와의 차가 `acceptance_m`보다 작다 | EXECUTING |
| LOITER | 앞 항목 완료 | 직전 setpoint를 Offboard로 유지한다. 비행제어의 Hold 모드가 아니다 | 항목 시작부터 ROS 시각으로 `duration` 경과 | EXECUTING |
| LAND | 앞 항목 완료, 또는 `[LAND]` 한 항목 미션이면 준비 단계 끝 | Land 명령(NAV_LAND)을 보내 비행제어의 Land 모드로 전환한다("LAND 항목" 절) | 지상 판정 뒤 DISARMED 확인까지(자동 disarm을 기다린다) | WAITING_MODE |

- `MissionItem.TYPE_LOITER`(Offboard에서 setpoint 유지)와 `VehicleState.MODE_HOLD`(비행제어의 Hold 모드)는 다른 것이다. 취소가 만드는 상태는 뒤의 것이다.
- GOTO, TRACK_ENTITY, RTL의 의미는 1b 완료에 고정한다("GoToItem과 TrackEntityItem" 절).

미션 검증(INVALID_MISSION).

- 계약: 항목 1개 이상, `type`이 `TYPE_*` 가운데 하나, `timeout` > 0, 쓰지 않는 서브메시지는 기본값, 서브메시지 값의 범위(`height_m` > 0, `acceptance_m` > 0, `duration` > 0이고 `timeout`보다 짧다, `YawSetpoint.mode`가 유효, `MODE_KEEP`이면 `yaw_rad` 0, `MODE_FIXED`이면 `yaw_rad`가 `[-pi, pi)`, 모든 실수가 유한), `mission_id` 규칙. `builtin_interfaces/Duration`의 `nanosec`은 1e9보다 작아야 한다.
- 1a 노드의 임시 제한(계약 문장이 아니다. 1b에서 푼다): `type`은 TAKEOFF, LOITER, LAND만 받는다. 마지막 항목은 LAND이고 LAND는 마지막에만 온다. 첫 항목은 TAKEOFF 또는 LAND다. 따라서 LAND로 시작하는 미션은 `[LAND]` 한 항목뿐이다. 이 제한에 걸린 미션도 INVALID_MISSION으로 끝나고 `detail`에 이유가 적힌다.

## ExecuteMission

고정 시점: 1a 완료("공중에서 끝나는 미션"은 1b 완료).

action `/<vehicle_id>/execute_mission`. 기체마다 Mission Executor 하나가 서버다. 성공, 중단, 취소의 정본은 action의 GoalStatus와 result이고, `MissionEvent`는 그 사본이다.

| 부분 | 필드 | 의미 |
| --- | --- | --- |
| goal | `vehicle_id` | 이 goal을 실행할 기체. 받는 쪽은 자기 `vehicle_id`와 문자열로 대조한다 |
| goal | `mission` | 실행할 미션 |
| result | `reason` | `REASON_*`("GoalStatus와 reason" 절) |
| result | `items_completed` | 완료한 항목 수 |
| result | `last_item_index` | 끝날 때 실행 중이던 항목(0부터). 항목을 시작하기 전에 끝났으면 0 |
| result | `detail` | 사람이 읽는 설명. 판정에 쓰지 않는다 |
| feedback | `stamp` | 그 feedback을 만든 tick의 입력 시각(ROS 시각. "feedback" 절) |
| feedback | `item_index`, `item_count`, `item_type` | 실행 중인 항목의 번호(0부터), 미션의 항목 수, 그 항목의 `MissionItem.TYPE_*` |
| feedback | `phase` | `PHASE_*`("feedback" 절) |
| feedback | `distance_valid`, `distance_remaining_m` | TAKEOFF는 목표 고도까지 남은 높이(m). GOTO와 TRACK_ENTITY는 setpoint 점까지의 거리(1b). 그 밖에는 `distance_valid` false |

`last_item_index`와 `items_completed`가 둘 다 0이면 "첫 항목 실행 중에 끝남"과 "항목을 시작하기 전에 끝남"을 가르지 않는다. 가르는 필드는 두지 않는다. 소비자의 다음 동작은 `reason`으로 갈리고, 항목 시작 전의 종료는 `reason`(NOT_READY, PRECONDITION_FAILED, ARM_REJECTED 등)과 마지막 feedback의 `PHASE_PREPARING`으로 읽힌다.

### 용어

- 공중과 지상: 이 절의 "공중"은 PX4의 착륙 판정 `vehicle_land_detected.landed`가 false, "지상"은 true인 것이다. 기체의 높이가 아니다. Offboard position setpoint나 Hold 중에는 이륙 ramp가 시작된 뒤 기체가 땅에 닿아 있어도 `landed`가 false로 남는다. 분기는 이 뜻으로 동작한다(땅에 닿은 채 `landed` false인 기체에도 공중 분기의 Hold는 받아들여진다).
- 발행: Executor가 20 Hz로 `offboard_control_mode`(position만 true)와 `trajectory_setpoint`를 내는 것.
- 명령: Executor가 `vehicle_command`로 보내는 Offboard 전환, arm, disarm, Hold 전환, Land(NAV_LAND). disarm은 모두 강제가 아닌 disarm이고 강제 disarm은 어디에서도 쓰지 않는다. 강제가 아닌 disarm은 PX4가 착륙 판정(`landed` 또는 `maybe_landed`)일 때만 받아들이므로 떠 있는 기체를 끄지 않는다. 확인을 기다리는 명령은 `command_resend_period`마다 재전송하고, 한 번에 하나만 기다린다. 성공의 판정은 ack가 아니라 `vehicle_status`(`nav_state`, `arming_state`)이고 ack는 거부를 빨리 아는 데만 쓴다.
- N회 연속 확인: 서로 다른 `vehicle_status` 표본 3개가 연달아 조건을 만족하는 것. 직전 표본보다 timestamp가 크지 않은 표본은 건너뛴다. 확인은 OFFBOARD, ARMED, Hold, Land 모드, DISARMED에 쓴다.
- 만료: 기준 시각부터의 ROS 시각 경과가 그 값 이상(`>=`)인 것.
- 정리: 취소, setpoint 항목의 ITEM_TIMEOUT, 준비 단계의 실패 뒤에 기체를 정해진 상태로 두려는 절차("취소" 절, "정리" 절).
- 시간 값(timeout, 확인 기한, 상한)은 모두 ROS 시각이다. 이름 붙은 값(`ready_timeout`, `mode_confirm_timeout` 등)은 노드 파라미터이고 기본값은 "참고: 노드 파라미터" 절에 있다. 값은 계약이 아니고, 어느 값으로 어느 분기가 끝나는지가 계약이다.

### 수락 정책

- Executor는 판단할 수 있는 goal을 모두 받아들이고, 받을 수 없으면 즉시 ABORTED로 끝내며 `reason`에 이유를 싣는다. 거절(reject)은 쓰지 않는다. ROS 2 action의 거절은 이유를 실을 수 없고, 소비자의 다음 동작이 이유로 갈리기 때문이다(BUSY는 다른 기체에 재시도, INVALID_MISSION은 미션 실패, VEHICLE_ID_MISMATCH는 설정 오류).
- goal과 Executor 자신의 상태만으로 판정되는 것은 접수 즉시 이 순서로 본다: VEHICLE_ID_MISMATCH -> INVALID_MISSION -> BUSY. 틀린 기체로 온 goal에 BUSY를 주면 소비자가 다른 기체에 재시도해 설정 오류를 덮으므로 대조가 먼저다.
- 실행 중인 goal은 선점하지 않는다. 두 번째 goal은 BUSY로 끝나고 첫 goal에 영향이 없다.
- 즉시 끝나는 셋(VEHICLE_ID_MISMATCH, INVALID_MISSION, BUSY)은 feedback이 0건이다. PX4 상태에 달린 판정(수신, 식별 대조, EKF 준비)은 즉시 하지 않고 준비 단계에서 기다리므로, NOT_READY 앞에는 `PHASE_PREPARING` feedback이 나갈 수 있다. 소비자는 feedback 수신을 수락 확인으로 쓰지 않는다. 수락의 확인은 goal 응답(accepted)이다.
- Executor가 종료(lifecycle shutdown) 뒤에 받은 goal은 즉시 ABORTED, REASON_INTERNAL로 끝난다(feedback 0건).
- 이 즉시 판정은 기체에 setpoint도 명령도 보내지 않는다.
- goal 응답이 없거나 action server가 없으면(Executor 미기동, 그 기체의 운용 컨테이너 종료, 응답 지연) 그 goal이 기체에 무엇을 보냈는지 소비자는 알 수 없다. goal을 보낸 직후 응답만 끊긴 경우 Executor가 이미 받았을 수 있다. 소비자는 이 기체의 상태를 `vehicle_status`와 `landed`(Phase 2부터는 `VehicleState`)로 확인한 뒤에만 다음 goal을 보낸다. 수락 뒤 result가 끝내 오지 않는 goal(실행 중 Executor 종료 등)도 같다. 응답 대기 시간은 소비자가 정한다.

### 준비 단계

첫 항목이 TAKEOFF인 미션은 아래 순서로 준비한 뒤 TAKEOFF를 시작한다. 이 구간의 feedback phase는 `PHASE_PREPARING`이다. `ready_timeout`은 goal 접수 시각부터 수신, 식별, EKF 준비 대기를 덮는다.

| 순서 | 내용 | 실패 |
| --- | --- | --- |
| 수신과 식별 | `vehicle_status`, `vehicle_land_detected`, `vehicle_local_position`, `failsafe_flags`를 받고, `vehicle_status`가 신선하며(마지막 수신이 `link_timeout` 안), 식별 대조(네임스페이스와 sysid)가 맞는다 | 식별 불일치가 확정되면 그 자리에서, 아니면 `ready_timeout`에 NOT_READY |
| 시작 조건 | 지상이고 DISARMED. EKF 준비를 기다리는 동안에도 다시 본다 | PRECONDITION_FAILED |
| EKF 준비 | `failsafe_flags`의 local position, local altitude, global position, home position 무효 flag가 모두 false이고 위치 값이 유한하다(`MODE_KEEP`이면 heading도 유한하다) | `ready_timeout`에 NOT_READY |
| 발행 시작 | 기준 위치와 heading을 읽고 TAKEOFF 목표점으로 발행을 시작한다 | - |
| 신호 확인 | 발행 10회 이상이고 PX4가 offboard 신호를 잃지 않았다 | `offboard_signal_timeout`에 MODE_SWITCH_FAILED |
| Offboard 전환 | Offboard 전환 명령. OFFBOARD 3회 연속 확인 | 거부 ack 또는 `mode_confirm_timeout`에 MODE_SWITCH_FAILED |
| arm | arm 명령. ARMED를 처음 관측하면 재전송을 멈춘다. ARMED이고 OFFBOARD인 표본 3회 연속 확인 | ARMED를 처음 관측하기 전: `arm_timeout`(arm을 처음 보낸 시각부터) 또는 TEMPORARILY_REJECTED가 아닌 거부 ack에 ARM_REJECTED. 처음 관측한 뒤: 그 시각부터 `mode_confirm_timeout` 안에 확인되지 않으면 ARM_REJECTED. 그 사이의 이상은 "비행 중 감시"가 끝낸다 |

- Offboard 전환이 먼저이고 arm이 나중이다. PX4는 arm 때 현재 모드에 신호가 없으면 거부하므로, arm이 받아들여졌다는 것이 Offboard가 돌 수 있다는 뜻이다.
- 시작 조건에서 지상 arm 기체를 받지 않는다. Executor가 arm하지 않은 기체(외부에서 arm한 기체)를 넘겨받지 않기 위해서다. 그래서 REASON_DISARM_FAILED로 지상에 arm 상태로 남은 기체는 누군가 disarm해야 다음 TAKEOFF 미션을 받는다.
- 첫 명령(`vehicle_command`)은 준비 단계의 식별 대조가 맞은 뒤에만 보낸다. 발행(setpoint stream)은 이 대조로 막지 않는다.
- NOT_READY와 PRECONDITION_FAILED로 끝난 goal은 발행을 시작하기 전에 끝났으므로 기체에 setpoint도 명령도 보내지 않았다. 발행을 시작한 뒤의 식별 불일치는 NOT_READY가 아니라 ABORTED, REASON_INTERNAL이고 `detail`에 기대값과 받은 값을 적는다. 이때 arm을 보냈으면 확인 없이 disarm을 한 번 보내고 끝낸다(입력을 믿을 수 없으므로 정리 분기를 고르지 않는다).
- 이 goal의 arm 뒤 ARMED를 처음 관측한 다음부터는 첫 항목을 시작하기 전이라도 "비행 중 감시"가 적용된다. 그래서 REASON_FAILSAFE, REASON_EXTERNAL_MODE_CHANGE, REASON_EXTERNAL_DISARM, REASON_LINK_LOST가 `PHASE_PREPARING`(`last_item_index` 0)에서 나올 수 있다. ARMED 확인 구간과 TAKEOFF는 같은 물리 상태(arm과 함께 이륙 ramp가 시작된다)이므로 같은 관측에 같은 동작을 낸다.
- 준비 단계의 실패 가운데 ARM_REJECTED와 MODE_SWITCH_FAILED는 정리("정리" 절)를 거친다. 비행 중 감시로 끝나면 정리를 거치지 않는다.

`[LAND]` 한 항목 미션의 준비: 수신과 식별 -> 시작 조건(ARMED이고 공중. 아니면 PRECONDITION_FAILED) -> EKF 준비 -> LAND 항목. Offboard 전환과 arm을 하지 않고 발행도 하지 않는다. `ready_timeout`으로 NOT_READY가 되면 기체는 있던 모드(보통 Hold)에 그대로 있다. 취소 뒤 Hold로 남은 기체(ARMED, `landed` false)는 이 시작 조건을 통과한다.

### 발행 규칙

- Executor는 Offboard로 들어가는 중(준비 단계의 발행 시작부터 arm 확인까지)과 `nav_state`가 OFFBOARD인 동안에만 발행한다. OFFBOARD가 아닌 모드(Hold, Land, failsafe 동작)를 관측하면 그 tick에 발행을 멈추고 다시 켜지 않는다. 모드 명령(Hold, NAV_LAND)을 보낸 뒤에는 그 모드를 처음 관측한 tick에 멈춘다.
- 이유: PX4 안에서 `trajectory_setpoint`는 비행제어 자신의 setpoint와 같은 토픽이라, Offboard가 아닌 모드에서 발행하면 섞인다. Hold 중 발행하면 기체가 끌리고, 착륙 중 발행하면 착륙 판정이 늦어지며, failsafe 뒤 발행을 재개하면 기체가 Offboard로 돌아간다.
- 정리의 지상 분기는 발행 중이면 setpoint를 "지상 setpoint"(그 tick의 위치에서 0.5 m 아래, 그 tick의 heading. 위치가 유한하지 않으면 준비 단계에서 읽은 기준 위치)로 바꿔 발행한다. 이륙 의도가 꺼져 추력이 오르지 않게 하려는 것이다. 이미 멈춘 발행은 이 분기에서도 다시 켜지 않는다.

### 비행 중 감시

준비 단계에서 ARMED를 처음 관측한 tick부터 setpoint 항목(TAKEOFF, LOITER)이 끝날 때까지 매 tick 아래 표를 본다. 표의 행으로 끝나는 goal은 정리를 거치지 않고 그 tick에 발행을 멈추고 ABORTED로 끝난다. 한 tick에 여러 행이 맞으면 순위가 앞선 행이 이긴다. 순위는 같은 tick의 동률만 가르고, 먼저 맞은 행이 그 tick에 goal을 끝낸다. 순위 3만 누적 판정(마지막 수신부터 `link_timeout`)이고 나머지는 표본 하나로 판정한다.

| 순위 | 관측 | reason | 동작 |
| --- | --- | --- | --- |
| 1 | 명령에 실을 PX4 시각을 만들 수 없다 | INTERNAL | 발행 중단. 명령을 보낼 수 없어 disarm도 보내지 않는다 |
| 2 | 식별 대조 불일치 | INTERNAL | 발행 중단. arm을 보냈으면 disarm 1회(`landed`를 보지 않는다) |
| 3 | `vehicle_status`가 `link_timeout` 동안 없다 | LINK_LOST | 발행 중단. 지상 disarm 1회 조건이면 disarm 1회 |
| 4 | DISARMED이고 공중 | FAILSAFE | 발행 중단 |
| 5 | DISARMED이고 지상 | 이 표본이 failsafe이거나 이력 구간 안에서 failsafe를 본 적이 있으면 FAILSAFE, 아니면 EXTERNAL_DISARM | 발행 중단. `detail`에 지상 disarm임을 적는다 |
| 6 | OFFBOARD가 아니고 failsafe | FAILSAFE | 발행 즉시 중단. 지상 disarm 1회 조건이면 disarm 1회 |
| 7 | OFFBOARD가 아니고 failsafe가 아니며 사용자 의도도 OFFBOARD가 아니다 | EXTERNAL_MODE_CHANGE | 위와 같다 |
| 8 | OFFBOARD가 아니고 failsafe가 아니며 사용자 의도는 OFFBOARD다 | FAILSAFE(방어용. PX4 v1.17.0의 정상 상태에서는 나오지 않는다) | 위와 같다 |

- 순위의 이유. 1-3은 나머지 행의 입력을 믿을 수 없게 하는 조건이다(시각이 없으면 발행이 안 되고, 식별이 어긋난 표본은 남의 기체의 것일 수 있으며, 끊기면 읽을 값이 없다). arming 행(4, 5)이 모드 행(6-8)보다 앞인 것은 disarm된 뒤의 `nav_state`가 확인된 사실이 아니기 때문이다. arming 상태를 먼저 보면 그 `nav_state`가 무엇이든 같은 reason이 나온다.
- 순위 5의 failsafe 이력 구간: 첫 항목(TAKEOFF)은 첫 ARMED 표본부터 그 항목이 끝날 때까지이고, 그 뒤의 항목은 항목이 시작된 뒤에 받은 표본부터다. 지금의 DISARMED 표본의 `nav_state`는 보지 않는다. PX4의 자동 disarm 주기의 첫 DISARMED 표본은 `failsafe`가 false이므로, failsafe Land로 OFFBOARD를 벗어난 표본을 Executor가 놓친 채 자동 disarm된 경우는 EXTERNAL_DISARM이 된다(원인을 판정하지 않는다는 의미에 맞다).
- 지상 disarm 1회(순위 3, 6, 7, 8): 세 조건이 모두 참이면 발행을 멈춘 그 tick에 disarm을 한 번 보내고 확인 없이 끝내며, `detail`에 "disarm sent once, not confirmed; vehicle may remain armed on ground"를 적는다. (1) 이 goal이 arm을 보냈다. (2) 첫 ARMED 표본 뒤에 받은 `landed`가 한 번도 false가 아니었다(이륙 이력이 없다). (3) 그 tick의 최신 `landed`가 true다. 이유: PX4의 착지 자동 disarm(`COM_DISARM_LAND`)은 이륙 이력이 있어야 동작하고, 이 프로젝트는 `COM_DISARM_PRFLT=-1`이라 한 번도 뜨지 않은 지상 arm 기체는 스스로 disarm되지 않는다. 이륙 이력이 생긴 뒤는 PX4가 맡는다. disarm은 모드 변경 요청이 아니라 failsafe 중에 보내도 사용자 넘겨받기를 일으키지 않는다.
- 순위 2의 disarm 1회는 `landed`를 보지 않는다. 같은 네임스페이스에 다른 발행자가 있을 수 있는 경우라 `vehicle_land_detected`(식별 필드가 없다)를 믿을 수 없기 때문이다. 이 disarm은 기대 sysid로 주소를 정하므로 우리 기체가 아니면 PX4가 무시하고, 떠 있는 기체에서는 거부된다.
- OFFBOARD이고 ARMED인 채 failsafe인 표본은 어느 행에도 걸리지 않고 goal을 계속한다. 모드를 바꾸지 않는 failsafe이고, 발행을 멈추면 offboard 신호 손실 failsafe를 스스로 일으키기 때문이다. 다음 표본의 모드 이탈은 순위 6-8이 잡는다.

disarm 분류의 고정 규칙: 관측한 disarm이 지상인지 공중인지는 처음 관측한 DISARMED 표본의 tick에, 그때까지 받은 최신 `landed` 값으로 정하고 고정한다. 뒤에 오는 `landed` 표본으로 바꾸지 않는다. PX4는 공중에서 disarm돼도 약 0.33 s 뒤 `landed`를 true로 바꿔 발행하므로, 고정하지 않으면 공중 disarm이 지상 disarm(완료나 CANCELED)으로 잘못 분류된다. 이 규칙은 감시 표의 순위 4와 5, LAND 항목의 완료 판정, 정리 중에 본 DISARMED에 모두 쓴다.

### LAND 항목

LAND 항목은 NAV_LAND를 재전송하며 Land 모드(AUTO_LAND)를 기다린다. 발행 중이었으면 AUTO_LAND를 처음 관측한 tick에 멈춘다.

- 확인 전(NAV_LAND를 보낸 뒤 AUTO_LAND 3회 연속까지): 모드 이탈 판정을 하지 않는다. 항목 시작 때의 모드가 AUTO_LAND가 아니기 때문이다(보통 OFFBOARD, `[LAND]` 미션이면 보통 Hold). 이 구간에서는 `mode_confirm_timeout`(NAV_LAND를 처음 보낸 시각부터. MODE_SWITCH_FAILED), 상태 끊김(LINK_LOST), 항목 `timeout`(ITEM_TIMEOUT)만 본다. 같은 tick이면 MODE_SWITCH_FAILED가 ITEM_TIMEOUT보다 먼저다. AUTO_LAND를 한 번 본 뒤 다른 모드 표본이 오면 계수를 0으로 되돌릴 뿐 이탈로 보지 않는다. AUTO_LAND 확인은 `failsafe` 값과 무관하게 센다(offboard 손실 Land 중인 기체에 보낸 `[LAND]`도 정상 경로다).
- 확인 뒤: ARMED인 동안 AUTO_LAND를 벗어나면 EXTERNAL_MODE_CHANGE(failsafe이면 FAILSAFE)다.
- 어느 구간에서든 DISARMED이고 지상이면 `nav_state`가 무엇이든 이탈로 보지 않고 완료 계수(DISARMED 3회 연속)가 우선한다. PX4는 자동 disarm과 함께 `nav_state`를 사용자 의도의 모드로 되돌리기 때문이다. DISARMED이고 공중이면 FAILSAFE다. 지상과 공중은 disarm 분류의 고정 규칙으로 읽는다.
- 대비책: 지상이고 ARMED인 채 `land_disarm_fallback_delay`가 지나면(AUTO_LAND 확인 뒤에만) disarm을 재전송하며 완료를 기다린다.
- 식별 불일치 표본은 ABORTED, REASON_INTERNAL로 끝낸다. LAND 항목에는 정리 분기가 없다.
- LAND 항목의 ITEM_TIMEOUT: NAV_LAND 재전송을 멈추고, 아직 발행 중이면 발행을 멈춘다. Hold는 보내지 않는다. 그 뒤는 PX4가 맡는다(OFFBOARD였으면 offboard 손실 동작 `COM_OBL_RC_ACT=4`의 Land, AUTO_LAND를 확인했으면 그 착륙). `[LAND]` 미션은 발행한 적이 없어 offboard 손실 Land가 걸리지 않으므로, NAV_LAND가 PX4에 닿지 않았다면 기체는 있던 모드(보통 Hold)에 남는다. 어느 쪽인지 `detail`에 적는다.

### 취소

Executor는 cancel 요청을 항상 받아들인다. 취소는 상황(준비 단계, failsafe 동작 중, LAND 항목 중 포함)을 가리지 않고 같은 분기로 처리하고 결과로 가른다. 분기는 매 tick 그 tick의 상태로 다시 고른다.

| 분기 | 조건 | 동작 | 결과 |
| --- | --- | --- | --- |
| 공중 | 공중 | 발행 중이면 유지한 채 Hold 명령을 재전송한다. Hold를 처음 관측하면 발행을 멈춘다. Hold 3회 연속 확인 | CANCELED |
| 공중(Hold 실패) | Hold 명령의 ack가 거부이거나 `hold_confirm_timeout`(Hold를 처음 보낸 시각부터) 안에 확인되지 않음 | Land 경로: NAV_LAND를 재전송하고, AUTO_LAND를 처음 관측하면 발행을 멈추고 끝낸다. `mode_confirm_timeout` 안에 AUTO_LAND가 보이지 않아도 발행을 멈추고 끝낸다 | ABORTED, REASON_MODE_SWITCH_FAILED |
| 지상 arm | 지상이고 ARMED, 또는 지상이고 이 goal에서 arm을 보낸 적이 있음 | 발행 중이면 지상 setpoint로 바꿔 유지한 채 disarm을 재전송한다. DISARMED 3회 연속이면 발행을 멈춘다. TEMPORARILY_REJECTED를 포함한 거부 ack는 그 자체로 실패가 아니고, 지상인 동안 재전송을 이어 간다 | CANCELED. `mode_confirm_timeout`까지 확인되지 않으면 발행을 멈추고 disarm을 한 번 더 보낸 뒤 ABORTED, REASON_DISARM_FAILED |
| 지상 disarm | 지상이고 DISARMED이며 이 goal에서 arm을 보낸 적이 없음 | 아무것도 보내지 않는다 | CANCELED |

- 분기 사이의 이동: Hold를 기다리는 중에 지상이 되면 지상 분기로, disarm을 기다리는 중에 공중이 되면 공중 분기로 넘어간다(지상 setpoint를 유지한 채 Hold를 보낸다. TAKEOFF 목표점으로 되돌리지 않는다). 분기에 들어갈 때마다 그 분기의 기준 시각, 재전송, 확인 계수를 새로 잡는다. 이 정리에서 Hold가 한 번 실패했으면 다시 공중 분기에 들어갈 때 Hold를 다시 보내지 않고 Land 경로로 간다.
- 이 goal에서 arm을 한 번이라도 보냈으면 지상에서 DISARMED로 보여도 disarm 분기를 거친다. 보낸 arm이 아직 처리되지 않았거나 ARMED 표본이 한 번도 보이지 않을 수 있기 때문이다. 이 분기의 DISARMED 확인은 그 분기에서 처음 보낸 disarm보다 뒤의 tick에 받았고 PX4 timestamp가 그 disarm에 실은 timestamp보다 엄격히 뒤인 표본만 센다. 다만 처리 전 DISARMED 표본 하나는 통과할 수 있고, 서로 다른 timestamp 3개의 연속 확인과 command queue FIFO가 막는다("시간 기준" 절의 예외). arm 재전송은 취소를 정한 tick에 즉시 멈춘다.
- 상태 끊김: `vehicle_status`가 `link_timeout` 동안 없으면 발행을 멈추고 ABORTED, REASON_LINK_LOST로 끝낸다. 그 tick의 분기가 지상이면 disarm을 한 번 더 보낸다.
- 정리 중의 공중 DISARMED(disarm 분류의 고정 규칙으로 공중)는 ABORTED, REASON_FAILSAFE다.
- 정리 중에 식별이 어긋난 `vehicle_status` 표본은 발행 규칙, 분기 고르기, 확인 계수에 쓰지 않는다. 이미 정해진 분기는 유지하고 그 분기의 timeout이나 정리의 상한이 끝낸다. 분기를 정하기 전(정리의 첫 tick)이면 ABORTED, REASON_INTERNAL로 끝내고, arm을 보냈으면 disarm을 한 번 보낸다.
- 아무것도 보내지 않은 goal의 취소도 같은 분기를 쓴다. 취소 뒤의 기체 상태 보장(아래)이 goal이 무엇을 보냈는지에 기대지 않게 하려는 것이다. 그래서 `[LAND]` 미션의 준비 중 취소는 공중이면 Hold를 보내고, TAKEOFF 미션이 수신을 기다리는 중에 외부에서 arm된 지상 기체를 만나면 그 기체를 disarm한다(강제가 아닌 disarm이다). 다만 `vehicle_status`나 `vehicle_land_detected` 표본이 없거나 상태가 끊긴 채이면 바로 CANCELED이고, 그때는 아래의 기체 상태를 보장하지 않는다. 미확인: 이 경로는 SITL에서 돌리지 않았다. 보수적 동작은 위와 같다.
- arm을 보내지 않은 goal(`[LAND]` 미션, arm 전의 준비 단계)의 "지상 disarm이면 바로 CANCELED"는 표본 하나로 정한다. 공중 분기 중에 지상 DISARMED 표본이 오면 그 tick에 끝낸다(예: `[LAND]` 미션을 취소해 공중 분기에 있는 동안 PX4가 스스로 착륙해 disarm한 경우). 지상 분기 중이면 그 분기의 disarm 확인을 이어 간다.
- 전체 취소: cancel은 goal id를 지정하지 않은 전체 취소(rclcpp_action의 `async_cancel_all_goals`)로도 올 수 있다. rclcpp_action은 전체 취소를 끝나지 않은 goal마다의 cancel 요청으로 Executor에 넘기고 Executor는 goal을 가리지 않고 받아들이므로, 처리는 위 분기와 같다. 소비자가 진행 중 goal의 handle을 잃으면(소비자 재시작) 전체 취소로 기체를 정리한 뒤, 기체 상태를 확인하고 다시 보낸다. 미확인: 이 경로는 테스트하지 않았다. 보수적 동작: 소비자는 전체 취소의 응답을 goal의 종료로 보지 않고, 기체 상태로 정리를 확인한 뒤에만 다음 goal을 보낸다.

CANCELED로 끝난 기체는 공중에 Hold(AUTO_LOITER, ARMED, `landed` false)로 있거나 지상에 disarm 상태다. Hold로 끝난 기체는 지면 근처이거나 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않고 그대로 머문다(이륙 ramp 중과 0.5 m 호버에서 60 s까지 관찰했다. 넘는 범위는 "미확인"). 그 기체를 내리는 것은 취소를 요청한 쪽의 책임이고, `[LAND]` 한 항목 미션을 보내면 된다. goal에 취소 뒤 동작(`on_cancel`)을 고르는 필드는 두지 않는다. Land나 RTL은 운용 정책이고 취소 뒤 미션 하나로 표현된다.

Hold를 고른 이유: setpoint를 그냥 끊으면 `COM_OF_LOSS_T` 뒤 `COM_OBL_RC_ACT`가 정한 대체 동작으로 넘어가 취소 뒤 동작이 파라미터에 따라 달라진다. Offboard로 위치를 계속 유지하면 기체 상태가 Executor 프로세스의 생존에 묶인다. Hold는 비행제어가 스스로 유지하는 가장 놀랍지 않은 상태다. PX4는 failsafe 동작 중이나 착륙 중에 온 Hold도 사용자 넘겨받기로 받아들인다. Executor가 죽은 경우는 취소가 아니라 offboard 손실 동작이 맡는다.

### 정리

setpoint 항목의 ITEM_TIMEOUT과 준비 단계의 실패(ARM_REJECTED, MODE_SWITCH_FAILED)는 취소와 같은 분기로 기체를 정리한다. 다른 점은 결과다.

- 결과는 항상 ABORTED이고 reason은 원래 실패 사유를 유지한다. Hold나 disarm이 확인되지 않았으면 `detail`에 적고, REASON_MODE_SWITCH_FAILED나 REASON_DISARM_FAILED로 바꾸지 않는다. 그래서 REASON_DISARM_FAILED는 취소에서만 나온다.
- 준비 단계의 실패에서 지상이고 DISARMED이며 arm을 보낸 적이 없으면 발행을 멈추는 것으로 끝낸다(정리할 것이 없다).
- 정리 중 feedback의 `phase`는 실패한 단계의 phase(EXECUTING 또는 PREPARING)를 유지한다. `PHASE_CANCELING`은 취소일 때만이다.
- 정리 중에 온 cancel은 결과를 바꾸지 않는다(ABORTED와 원래 reason으로 끝난다. 정리 절차가 취소와 같아 기체 동작도 같다).

### 정리의 상한

정리(취소, setpoint 항목의 ITEM_TIMEOUT, 준비 단계의 실패)는 분기를 오가도 정리를 시작한 tick부터 `hold_confirm_timeout + 3 x mode_confirm_timeout`(기본 12 s) 안에 끝난다. 이 값은 노드 파라미터가 아닌 파생값이다. 정당한 경로 가운데 가장 긴 것(지상 -> Hold 실패 -> Land 경로 -> 다시 지상)의 합이라 정당한 경로를 자르지 않는다.

- 상한에 닿으면 발행을 멈추고 대기 중인 명령을 지운 뒤, 그 tick의 분기에 따라 명령 하나를 보내고 끝낸다. 지상이면 disarm 1회, 공중이면 NAV_LAND 1회(Hold를 이미 관측해 발행을 멈춘 기체는 이 NAV_LAND가 유실되면 Hold로 남는다. 그 경우를 `detail`에 적는다). 그 tick의 표본이 식별 불일치이면 직전 분기로 정한다.
- 취소이면 지상은 ABORTED, REASON_DISARM_FAILED, 공중은 ABORTED, REASON_MODE_SWITCH_FAILED다. ITEM_TIMEOUT과 준비 단계 실패의 정리이면 같은 동작에 원래 reason을 유지한다. 어느 경우든 `detail`에 상한으로 끝났다는 것과 마지막 분기를 적는다.
- 정리 중 한 tick의 순서: (1) 상태 끊김 (2) 공중 DISARMED (3) 정리할 것 없음(지상 DISARMED이고 arm을 보낸 적이 없고 지상 분기 중이 아님) (4) 상한 (5) 그 분기의 실행. 표본 하나로 정해지는 관측((1)-(3))은 상한보다 앞이고, 상한은 그 tick에 온 확인 표본보다 앞이다.
- 소비자는 취소의 결과를 기다리는 시간을 이 값에 하드코딩하지 않는다. 노드 파라미터가 바뀌면 상한도 바뀌므로, 여유를 두거나 result를 비동기로 받는다.

### 종료의 충돌 규칙

- 먼저 정해진 종료가 이긴다. 종료가 정해진 tick 뒤의 표본과 cancel은 결과를 바꾸지 않는다. 종료는 goal마다 정확히 한 번이다. "정해진다"는 정리가 끝난 때가 아니라 사유가 생긴 tick이다.
- 같은 tick에 둘 이상이 정해지면 ABORTED 사유, 완료(SUCCEEDED), 취소 순이다. ABORTED 사유가 둘이면 비행 중 감시 표의 순위를 따르고, 감시 표의 행은 ITEM_TIMEOUT을 이긴다. 예: LAND 항목에서 DISARMED 세 번째 표본과 cancel이 같은 tick이면 SUCCEEDED다. CANCELING 중에 항목 `timeout`이 지나도 취소 경로로 끝난다.
- 같은 tick에 만료와 기다리던 확인(3회 연속)이 함께 정해지면 만료가 이긴다. 표본 하나로 정해지는 관측(공중 DISARMED, 정리할 것 없음, 첫 ARMED 표본)은 만료보다 앞이다.
- 종료가 정해져 끝나는 시점에는 발행이 멈춰 있고 명령 재전송이 지워져 있다. 그래서 종료 뒤의 cancel을 무시해도 남는 동작이 없다.

### GoalStatus와 reason

- SUCCEEDED이면 `reason`은 REASON_NONE, CANCELED이면 REASON_NONE, ABORTED이면 REASON_NONE이 아니다. 이 대응을 Executor 단위 테스트가 묶는다.
- `reason` 값은 추가만 하고 의미를 바꾸지 않는다. 255는 INTERNAL로 고정이다.
- 1a 노드가 내지 않는 값: REASON_TARGET_LOST(1b. 의미는 1b 완료에 고정한다).

| reason | 의미 | 나오는 곳 |
| --- | --- | --- |
| NONE (0) | 사유 없음 | SUCCEEDED, CANCELED |
| INVALID_MISSION (1) | 미션이 검증을 통과하지 못했다(1a 임시 제한 포함) | 접수 즉시 |
| VEHICLE_ID_MISMATCH (2) | goal의 `vehicle_id`가 Executor의 값과 다르다 | 접수 즉시 |
| BUSY (3) | 다른 goal을 실행 중이다 | 접수 즉시 |
| NOT_READY (4) | 항목을 시작하기 전에 기체가 준비되지 않았다(수신, 식별, EKF 준비). 이 goal은 setpoint와 명령을 보내지 않았다 | 준비 단계(발행 시작 전) |
| ARM_REJECTED (5) | arm이 거부되었거나 `arm_timeout` 안에 ARMED가 관측되지 않았거나, ARMED를 관측했으나 확인되지 않았다 | 준비 단계(arm) |
| MODE_SWITCH_FAILED (6) | 요청한 모드 전환이 확인되지 않았다(Offboard 신호 확인과 전환, LAND 항목의 Land 전환, 취소의 Hold) | 준비 단계, LAND 항목, 취소의 정리 |
| ITEM_TIMEOUT (7) | 항목이 `timeout` 안에 완료되지 않았다 | 항목 |
| FAILSAFE (8) | 비행제어의 failsafe가 관측되었거나 공중 disarm이 관측되었다 | 비행 중 감시(준비 단계의 ARMED 관측 뒤 포함), LAND 항목, 정리 |
| EXTERNAL_MODE_CHANGE (9) | Executor가 요청하지 않은 모드 변화가 failsafe 없이 관측되었다 | 비행 중 감시, LAND 항목(Land 확인 뒤) |
| TARGET_LOST (10) | 1b | - |
| LINK_LOST (11) | `vehicle_status`가 `link_timeout` 동안 오지 않았다 | 비행 중 감시, LAND 항목, 정리 |
| PRECONDITION_FAILED (12) | 항목을 시작할 때 그 항목의 시작 조건이 맞지 않았다(TAKEOFF는 지상 DISARMED, `[LAND]`는 공중 ARMED가 조건). 이 goal은 setpoint와 명령을 보내지 않았다 | 준비 단계(발행 시작 전) |
| DISARM_FAILED (13) | 취소 처리 중 지상에서 보낸 disarm이 제한 시간 안에 확인되지 않았고 기체가 arm 상태로 남았을 수 있다 | 취소의 정리 |
| EXTERNAL_DISARM (14) | setpoint 항목 실행 중이거나 그 앞의 arm 확인 중(ARMED를 처음 관측한 뒤)에 Executor가 보내지 않은 disarm이 지상에서 failsafe 없이 관측되었다. 원인은 판정하지 않는다 | 비행 중 감시 |
| INTERNAL (255) | Executor 쪽 문제로 끝났다: 발행을 시작한 뒤의 식별 불일치, 명령에 실을 PX4 시각을 만들 수 없음, Executor의 종료(lifecycle shutdown, error)와 종료 뒤의 goal. 끝난 뒤 기체 상태를 보장하지 않는다 | 어디서나 |

- EXTERNAL_MODE_CHANGE와 EXTERNAL_DISARM의 "external"은 "Executor가 보내지 않은"이라는 뜻이고 외부 주체가 있었다는 판정이 아니다. Executor가 아는 것은 "`failsafe`가 false인데 Executor가 요청하지 않은 변화"뿐이다. EXTERNAL_DISARM에는 외부 명령(GCS, 다른 노드)뿐 아니라 PX4 자체의 disarm과 kill이 들어간다. 예: 기체가 떠오른 뒤 어떤 이유로 지면에 내려앉아 PX4가 착지 자동 disarm(`COM_DISARM_LAND`)을 하면 외부 주체 없이 EXTERNAL_DISARM이 나온다(미확인: Offboard position setpoint를 유지하는 중에 착륙 판정이 서는 경로는 실측하지 않았다). 소비자는 이 reason을 "Executor 밖의 원인으로 지상 disarm됨"으로 읽고, 다음 동작은 아래 "끝난 뒤 기체 상태"로 정한다.
- FAILSAFE와 EXTERNAL_DISARM은 같은 사건이 관측 시점에 따라 어느 쪽으로도 나올 수 있다(순위 5의 이력 구간). 그래서 소비자는 둘의 다음 동작을 다르게 두지 않고, reason 이름을 운용자 개입의 근거로 표시하지 않는다.
- MODE_SWITCH_FAILED와 DISARM_FAILED를 나눈 이유: 끝난 뒤 기체 상태가 다르다. Hold 실패는 Executor가 Land를 보내 기체가 내려오는 중이고, 지상 disarm 실패는 기체가 지상에 arm으로 남는다. EXTERNAL_MODE_CHANGE와 EXTERNAL_DISARM도 같은 이유로 나눈다(앞은 보통 공중 ARMED, 뒤는 지상 disarm).

### 끝난 뒤 기체 상태

goal이 끝난 시점의 기체 상태다. 소비자(Fleet, 운용자, 통합 테스트)가 다음 동작을 정하는 근거다. 표의 상태는 Executor가 끝낼 때 기대하는 상태이고, 소비자는 다음 미션 전에 `vehicle_status`와 `landed`(Phase 2부터는 `VehicleState`)로 실제 상태를 확인한다. "근거"의 [실측]은 SITL에서 관찰한 것, [소스]는 PX4 v1.17.0 원문으로 확인한 것, 미확인은 그 경로를 실측하지 않아 지금 동작을 적은 것이다.

| 끝난 방식 | 기체 상태 | 근거 |
| --- | --- | --- |
| SUCCEEDED | 지상 DISARMED(마지막 항목 LAND의 완료 조건) | [실측] 시나리오 A, D |
| CANCELED(공중 분기) | Hold(AUTO_LOITER, ARMED, `landed` false). 스스로 내려앉거나 disarm되지 않는다. 내리려면 `[LAND]` 미션을 보낸다 | [실측] 시나리오 D(5 m), 이륙 ramp 중과 0.5 m 호버(60 s까지 관찰) |
| CANCELED(지상 분기) | 지상 DISARMED | [실측] PX4에 직접 보낸 이륙 직후의 지상 setpoint와 disarm(spoolup, rampup 대역 모두 지상 DISARMED). Executor 경유는 단위 테스트 |
| CANCELED(상태 표본 없이 끝남) | 보장하지 않는다(이 goal은 아무것도 보내지 않았다) | 미확인 |
| 지면 바로 위에서 Hold로 끝난 CANCELED 또는 ITEM_TIMEOUT | ARMED, `landed` false인 채 지상이나 지면 근처에 머문다. 높이가 약 0 m여도 Hold 중이라 모터가 돈다. 스스로 disarm되지 않는다. `landed`와 `nav_state`로는 낮은 높이의 Hold와 같고, 지상에 arm으로 남은 상태(`landed` true. DISARM_FAILED 뒤)와는 `landed`로 갈린다. 이어 보낸 `[LAND]` 미션은 시작 조건을 통과한다 | [실측] 이륙 ramp 중, 0.5 m 호버, 이륙 직후 취소의 경계 1회(60 s 관찰). 같은 상태에서 직접 보낸 NAV_LAND는 disarm까지 갔다. Executor가 보낸 `[LAND]`는 미확인 |
| INVALID_MISSION, VEHICLE_ID_MISMATCH, BUSY | 이 goal은 기체에 아무것도 보내지 않았다. 기체 상태는 이 goal과 무관하다(BUSY이면 실행 중인 goal이 그대로 돈다) | [실측] 시나리오 B, C(goal 뒤 5 s 동안 ARMED 없음) |
| NOT_READY, PRECONDITION_FAILED | 이 goal은 기체에 아무것도 보내지 않았다. 기체는 있던 상태 그대로다 | 구현 규칙(발행 시작 전에만 쓴다) |
| ARM_REJECTED | 정리를 거친다. arm을 보냈으므로 지상 disarm 분기: 보통 지상 DISARMED. disarm이 확인되지 않았으면 `detail`에 적고 지상에 arm으로 남았을 수 있다. 공중이 되었으면 Hold 또는 Land 진행 중 | 정리 분기의 PX4 쪽 사실은 [실측](이륙 직후 취소의 재실측). 이 reason으로 끝나는 경로는 SITL에서 돌리지 않았다(단위 테스트) |
| MODE_SWITCH_FAILED(준비 단계) | arm 전이므로 지상 DISARMED. 발행은 멈춰 있다. `nav_state`는 OFFBOARD로 남을 수 있으나 DISARMED라 해가 없고 다음 TAKEOFF를 막지 않는다 | 미확인. 보수적 동작: 발행 중단만 한다 |
| MODE_SWITCH_FAILED(LAND 항목) | 공중. NAV_LAND 재전송과 발행이 멈춰 있다. OFFBOARD였으면 PX4의 offboard 손실 동작(Land)이 내리고, `[LAND]` 미션이면 있던 모드(보통 Hold)에 남을 수 있다 | 미확인. 보수적 동작: 발행 중단, Hold를 보내지 않는다 |
| MODE_SWITCH_FAILED(취소. Hold 실패나 공중의 상한) | 공중. Executor가 NAV_LAND를 보냈고 보통 AUTO_LAND로 내려오는 중이며 PX4가 착지 뒤 자동 disarm한다. AUTO_LAND를 확인하지 못했으면 `detail`에 적고, Hold를 관측한 뒤였으면 NAV_LAND 유실 시 Hold로 남는다 | [소스] NAV_LAND는 force로 요청되어 모드 가용성 검사를 우회한다. 거부(TEMPORARILY_REJECTED) 경로는 소스에 남아 있고(`Commander.cpp` 1106-1109행), force 요청에서 거부되는 조건은 확인하지 않았다(미확인). 그래서 `mode_confirm_timeout` 안에 AUTO_LAND가 보이지 않아도 끝내는 방어를 둔다. 경로는 미확인(위치 무효에서 Hold가 거부되는 경우를 실측하지 않았다) |
| ITEM_TIMEOUT(setpoint 항목) | 취소와 같은 정리를 거친다: Hold(공중), 지상 DISARMED, 또는 Hold 실패 뒤 Land 진행 중. 확인되지 않은 것은 `detail`에 적는다 | 정리 분기는 취소와 같다. 이 reason으로 끝나는 경로는 SITL에서 돌리지 않았다(단위 테스트) |
| ITEM_TIMEOUT(LAND 항목) | 공중이거나 착륙 중. 발행과 NAV_LAND 재전송이 멈춰 있고 PX4가 착륙을 이어 가거나(AUTO_LAND 확인 뒤, 또는 OFFBOARD였으면 offboard 손실 Land) `[LAND]` 미션이면 있던 모드에 남을 수 있다. 지상에 ARMED로 남았으면 `detail`에 적는다 | 미확인. 보수적 동작: Hold를 보내지 않는다 |
| FAILSAFE | PX4의 failsafe 동작 중(이 프로젝트의 SITL 파라미터에서 offboard 손실은 Land)이거나 disarm 상태(공중 disarm이면 추락했을 수 있다). Executor는 발행을 멈췄고, 이륙 이력이 없는 지상 arm이면 disarm을 한 번 보냈다 | [소스] failsafe 중의 발행 재개는 기체를 Offboard로 되돌린다([실측] 1회). 이 reason으로 끝나는 경로는 SITL에서 돌리지 않았다 |
| EXTERNAL_MODE_CHANGE | 다른 주체가 고른 모드의 ARMED. Executor는 발행을 멈췄고, 이륙 이력이 없는 지상 arm이면 disarm을 한 번 보냈다(넘겨받은 쪽이 비행을 원하면 다시 arm한다) | 미확인 |
| EXTERNAL_DISARM | 지상 DISARMED | 미확인(지상 disarm 뒤의 `nav_state`는 확인된 사실이 아니다. 판정은 `nav_state`를 보지 않는다) |
| LINK_LOST | 알 수 없다. Executor는 발행을 멈췄고 이륙 이력이 없는 지상 arm이면 disarm을 한 번 보냈다. OFFBOARD였으면 PX4가 offboard 손실 동작으로 들어간다 | 미확인 |
| DISARM_FAILED | 지상(`landed` true)에 ARMED로 남았을 수 있다. 이륙 이력이 없으면 PX4가 스스로 disarm하지 않는다. 그 기체는 누군가 disarm할 때까지 TAKEOFF와 `[LAND]` 미션 모두 PRECONDITION_FAILED다 | [소스] `COM_DISARM_PRFLT=-1`. 실측 없음 |
| INTERNAL | 보장하지 않는다. 식별 불일치와 Executor의 종료에서는 arm을 보낸 goal이면 확인 없이 disarm을 한 번 보낸다. PX4 시각을 만들 수 없으면 명령을 보내지 못한다. 어느 쪽인지 `detail`에 적는다("disarm sent once, not confirmed; vehicle may remain armed on ground", "vehicle state unknown" 등) | 미확인 |
| goal 응답 없음, action server 없음 | 알 수 없다("수락 정책" 절). 기체 상태로 확인한 뒤에만 다음 goal을 보낸다 | - |

### feedback

- Executor는 실행 중인 goal에 phase나 항목이 바뀐 tick에 바로, 그 밖에는 약 2 Hz로 feedback을 낸다. 주기는 계약이 아니다. 즉시 끝나는 goal(VEHICLE_ID_MISMATCH, INVALID_MISSION, BUSY, 종료 뒤의 INTERNAL)은 feedback이 없다.
- `stamp`는 그 feedback을 만든 tick의 입력 시각이다. Executor가 그 tick에서 경과 시간(timeout, `duration`)을 잰 ROS 시각과 같은 값이다. 명령에 싣는 PX4 timestamp와는 따로 읽은 값이라 다를 수 있다.
- 준비 단계의 feedback은 `item_index` 0, `item_type`은 첫 항목의 type, `phase`는 `PHASE_PREPARING`이다.

| phase | 언제 |
| --- | --- |
| `PHASE_PREPARING` (1) | 준비 단계(수신과 식별, Offboard 진입, arm). 준비 단계 실패의 정리 중 |
| `PHASE_EXECUTING` (2) | setpoint 항목 실행 중. 그 항목의 ITEM_TIMEOUT 정리 중 |
| `PHASE_WAITING_MODE` (3) | 모드 명령 항목(1a는 LAND)에서 모드 전이와 완료를 기다리는 중 |
| `PHASE_CANCELING` (4) | 취소 요청 뒤 정리 중 |

### 공중에서 끝나는 미션

고정 시점: 고정 전(1b 완료에 고정).

마지막 항목이 LAND가 아닌 미션의 종료 동작은 정하지 않았다. 1a 노드는 그런 미션을 INVALID_MISSION으로 끝낸다. 이것은 임시 제한이고 계약 문장이 아니다. 첫 소비자인 1b의 YAML 미션 설계에서 정하고 1b 완료에 고정한다. 같은 때에 setpoint 항목으로 시작하는 공중 시작 미션(Offboard 재진입)과 1a 임시 제한(마지막이 LAND, 첫 항목 제한)의 해제를 정한다. 지금의 권고안은 취소와 같은 이유로 "Hold 확인 뒤 SUCCEEDED"다.

### 미확인 목록

아래는 실측하지 않은 경계 상황이다. 계약은 지금 동작을 기본으로 두며, 소비자는 이 경우의 기체 상태를 계약 문장으로 가정하지 않고 `vehicle_status`와 `landed`로 확인한다.

| 경계 상황 | 지금의 동작(보수적 기본) |
| --- | --- |
| Land 모드 하강 중 지면 가까이(약 0.3 m 아래)에서의 취소 | 분기 규칙 그대로(공중이면 Hold). PX4의 지면 접촉 판정이 이미 서 있으면 Hold로 CANCELED된 뒤 스스로 내려앉아 disarm되고, 이어 보낸 `[LAND]`가 PRECONDITION_FAILED일 수 있다 |
| Hold로 끝난 뒤 60 s 이후의 기체 동작 | 아무것도 보내지 않는다. 내리는 것은 취소를 요청한 쪽의 책임이다 |
| 높이 0.06 m와 0.37 m 사이에서의 Hold | 분기 규칙 그대로 |
| 지면 근처 Hold에서 Executor가 보낸 `[LAND]` 미션 | `[LAND]` 미션의 정상 경로 그대로 |
| 이륙 직후 취소에서 첫 disarm이 유실되어 재전송이 `landed` false 뒤에 처리되는 경우 | 지상 분기에서 공중 분기로 넘어가 지상 setpoint를 유지한 채 Hold. 그 뒤 정리의 상한 |
| 정리 중 failsafe 동작 중인 기체에 Hold를 보내는 것 | 분기 규칙 그대로(Hold가 failsafe 동작을 사용자 넘겨받기로 덮는다. offboard 손실 failsafe와 Land 중의 Hold는 받아들여지는 것을 확인했고, 그 밖의 failsafe는 확인하지 않았다) |
| 위치 추정이 무효라 Hold가 거부되는 경우 | Hold 거부 ack이거나 `hold_confirm_timeout`이면 Land 경로 |
| 아무것도 보내지 않은 goal의 취소가 Hold나 disarm을 보내는 것 | 분기 규칙 그대로("취소" 절) |
| 전체 취소(goal id 미지정) | 분기 규칙 그대로("취소" 절). 소비자는 기체 상태로 정리를 확인한다 |
| 감시 표 순위 5에서 지상 disarm 뒤의 `nav_state` | 판정에 쓰지 않는다(arming 행이 모드 행보다 앞) |
| Offboard position setpoint 중에 착륙 판정이 서서 PX4가 착지 자동 disarm하는 경우 | 감시 표 순위 5, EXTERNAL_DISARM |
| arm 상태에서 신호 없는 Offboard 요청 | 준비 단계는 arm 전에 Offboard를 요청하므로 이 경로를 쓰지 않는다 |
| 지면 근처 Hold에서 스스로 disarm되지 않는다는 관찰의 범위(이륙 ramp 중과 0.5 m 호버 밖) | 위 CANCELED 문장 그대로 |
| Executor 컨테이너를 goal 실행 중에 멈췄을 때 종료 사건이 구독자에게 오는지 | Executor는 종료 처리에서 goal을 ABORTED, REASON_INTERNAL로 끝내고 종료 사건을 낸다. 오지 않으면 읽는 쪽은 결과 미상으로 다룬다 |

### 참고: 노드 파라미터

시간 값의 기본값(ROS 시각, 노드 파라미터. 계약이 아니다). 바꾸면 그 값으로 끝나는 분기의 시각만 달라지고 분기와 결과는 그대로다. 명령의 source 값은 "VehicleCommand" 절의 source 표에 있다.

| 이름 | 기본값 | 덮는 것 |
| --- | --- | --- |
| `ready_timeout` | 30 s | 준비 단계의 수신, 식별, EKF 준비(goal 접수 시각부터) |
| `offboard_signal_timeout` | 2 s | 발행 10회와 신호 확인(발행 시작부터) |
| `mode_confirm_timeout` | 3 s | Offboard 확인, LAND 항목의 Land 확인, Hold 실패 뒤 Land 경로, 지상 disarm 확인, 첫 ARMED 관측 뒤의 arm 확인 |
| `arm_timeout` | 5 s | arm을 처음 보낸 시각부터 ARMED를 처음 관측할 때까지 |
| `hold_confirm_timeout` | 3 s | 취소의 Hold 확인(Hold를 처음 보낸 시각부터) |
| `link_timeout` | 2 s | `vehicle_status` 끊김 판정. `mode_confirm_timeout`보다 짧아야 한다(지상 disarm 분기에서 표본이 아예 없으면 LINK_LOST가 먼저다) |
| `land_disarm_fallback_delay` | 5 s | LAND 항목의 대비책 disarm까지의 지연 |
| `command_resend_period` | 0.5 s | 확인을 기다리는 명령의 재전송 주기 |
| 정리의 상한 | 12 s | 파라미터가 아니다. `hold_confirm_timeout + 3 x mode_confirm_timeout` |

## MissionEvent

고정 시점: 고정 전(Phase 2 완료에 고정).

토픽 `/<vehicle_id>/mission_event`. 미션 실행의 접수와 종료 기록이다. rosbag2(Jazzy)는 action의 goal과 result를 기록하지 않으므로, 기록물에서 미션 id와 결과를 읽을 일반 토픽을 따로 둔다. 정본은 action(GoalStatus와 result)이고 이 메시지는 기록과 관찰을 위한 사본이다. 소비자는 기록물 인덱스(Phase 2)와 통합 테스트다. Fleet은 배분 판단에 쓰지 않는다.

| 필드 | 의미 |
| --- | --- |
| `stamp` | 사건 시각. Executor 노드 시계의 ROS 시각이고 벽시계가 아니다(아래 발행 규칙) |
| `vehicle_id` | 발행한 Executor의 `vehicle_id`. 토픽 네임스페이스와 같다. VEHICLE_ID_MISMATCH로 끝난 goal에서도 Executor 자신의 값이고, goal에 적힌 값은 `detail`에 있다 |
| `mission_id` | goal에 적힌 값 그대로. 검증에 실패한 값일 수 있다 |
| `goal_id` | action goal의 UUID(16바이트, UUID의 `uuid` 필드와 같은 순서). `_action/status`, `_action/feedback`의 goal id와 같다 |
| `status` | `STATUS_ACCEPTED`(1) 접수, `STATUS_SUCCEEDED`(4), `STATUS_CANCELED`(5), `STATUS_ABORTED`(6) 종료. 값은 `action_msgs/GoalStatus`의 같은 이름 상수와 같다(타입은 uint8) |
| `reason` | 종료 때 result의 `reason`. 접수 때는 REASON_NONE |
| `item_count` | goal의 항목 수 |
| `items_completed`, `last_item_index`, `detail` | 접수 때는 0, 0, 빈 문자열. 종료 때는 result와 같다 |

발행 규칙.

- Executor는 goal마다 접수 때(`handle_accepted` 진입) STATUS_ACCEPTED를 한 번, 종료 상태를 정했을 때 종료 사건을 한 번 낸다. 거절을 쓰지 않으므로 즉시 ABORTED로 끝나는 goal(BUSY 등)도 접수와 종료를 하나씩 갖는다. 종료 사건의 `status`, `reason`, `items_completed`, `last_item_index`, `detail`은 GoalStatus와 result와 같다(Executor 단위 테스트가 묶는다).
- `stamp`: 접수 사건과 즉시 종료의 종료 사건은 접수 callback에서 한 번 읽은 시각이라 서로 같다. 실행 중에 tick에서 정한 종료의 사건은 그 tick의 입력 시각이다(그 tick의 feedback `stamp`, Executor가 경과를 잰 시각과 같다). Executor의 종료(lifecycle shutdown, error)로 끝낸 goal의 사건은 종료할 때 읽은 시각이다.
- Executor가 실행 중에 죽거나 스택이 내려가면 접수 사건만 남는다. 읽는 쪽은 짝을 전제하지 않고, 종료 사건이 없는 접수를 결과 미상으로 다룬다.
- QoS는 "계약 토픽 QoS" 절의 사건 행이다.
- VOLATILE이므로 구독이 발행자와 맺어지기 전에 나간 사건은 오지 않는다. goal을 보내는 쪽이 사건도 받으려면 `mission_event` 구독을 action client보다 먼저, 같은 노드(같은 participant)에서 만든다. 이 순서를 어기면 접수 사건이 빠지는 것을 관찰했다. 구독 쪽의 `get_publisher_count() >= 1`은 goal 전의 확인으로 두되 사건 수신의 보장으로 쓰지 않는다. graph 조회는 QoS 대조에만 쓴다.
- 기록기(rosbag2 recorder)는 토픽을 주기적으로 찾아 늦게 구독하므로, goal을 보내는 쪽의 확인만으로는 기록기의 구독이 맺어졌다는 보장이 없다. 기록기가 맺어졌다는 신호와 그 뒤에 goal을 보내는 순서는 Phase 2에서 정한다. 기록기의 구독은 RELIABLE, VOLATILE을 명시 QoS override로 고정한다.

기록물 인덱스가 지킬 것(Phase 2).

- 실행 단위의 key는 (`vehicle_id`, `goal_id`)다. `mission_id`는 재사용될 수 있어 key로 쓰지 않는다. `item_count`, `items_completed`, `last_item_index`, `detail`은 표시용이다.
- 종료 사건이 없는 접수는 실패가 아니라 결과 미상이고, 그 실행의 기간의 끝은 기록물의 마지막 메시지 시각이다. 같은 기체에서 앞 접수의 종료 사건 없이 뒤의 접수가 나오면 앞 접수도 결과 미상이다(Executor가 재시작한 경우. BUSY로 끝난 둘째 goal은 자기 종료 사건을 가져 `goal_id`로 구분된다). 결과와 종료 시각 column은 미상 값을 허용한다.
- 필드를 바꾸면 type hash가 바뀌어 이전 fixture 기록물과 맞지 않으므로, 필드 변경이 필요하면 Phase 2 초반에 한다.

## GoToItem과 TrackEntityItem

고정 시점: 고정 전(1b 완료에 고정).

1a 노드는 이 둘과 RTL이 든 미션을 INVALID_MISSION으로 끝낸다. 아래는 지금의 정의이고 1b 구현에서 확정한다.

| 정의 | 필드 | 의미 |
| --- | --- | --- |
| `GoToItem` | `position` | world ENU 목표점(m) |
| `GoToItem` | `acceptance_radius_m` | 3차원 거리 허용 오차(m). 0보다 크다 |
| `GoToItem` | `yaw` | 이동 중의 yaw |
| `TrackEntityItem` | `target_id` | 추종할 표적(`TargetState.target_id`) |
| `TrackEntityItem` | `offset` | world ENU(m). 표적 위치에 더한 점이 setpoint다. 0 벡터는 검증에서 거부한다(시뮬레이션 표적은 충돌이 없어 테스트에서 드러나지 않는다) |
| `TrackEntityItem` | `acceptance_radius_m` | setpoint 점까지 이 거리 안에 들면 항목 완료. 0보다 크다 |
| `TrackEntityItem` | `yaw` | 추종 중의 yaw |

- GOTO와 TRACK_ENTITY는 PX4 위치 추정의 전역 기준(`xy_global`, `z_global`)이 유효해지기 전에는 시작하지 않는다. 기다리는 동안에도 항목 `timeout`이 흐르고, 넘기면 ITEM_TIMEOUT이며 `detail`에 사유를 적는다.
- 미션에 적힌 `target_id`가 실제로 있는지는 검사하지 않고, 항목 시작 뒤 정해진 시간 안에 유효 표본이 없으면 REASON_TARGET_LOST로 드러난다.
- RTL은 모드 명령 항목이고 LAND처럼 지상 판정 뒤 DISARMED 확인까지가 한 항목이다.
- TRACK_ENTITY의 지속 시간 종료 조건은 두지 않았다. 필요해지면 1b 고정 전에 끝에 필드를 더한다.
- `YawSetpoint.MODE_KEEP`의 기준 yaw는 1b에서 정한다.

## TargetState

고정 시점: 고정 전(1b 완료에 고정).

토픽 `/targets/<target_id>/state`. 표적 하나의 상태이고 시뮬레이터에 의존하지 않는다. 소비자에게 정본은 `TargetState`다.

| 필드 | 의미 |
| --- | --- |
| `header.stamp` | 그 상태가 유효한 ROS 시각. 발행 시각이 아니다. 0이 아니고 같은 표적에서 단조 증가한다 |
| `header.frame_id` | `FRAME_ID`(`world`) |
| `target_id` | 표적 id. 토픽의 `<target_id>`와 같다 |
| `position` | world ENU(m) |
| `velocity_valid`, `velocity` | world ENU(m/s). `velocity_valid`는 언제든 false일 수 있고(첫 표본에 한정하지 않는다) false면 `velocity`는 0이다 |

- 소비자는 증가하지 않는 stamp의 표본과 `target_id`가 토픽 토큰과 다른 표본을 버린다.
- 소실 플래그와 종료 메시지는 없다. 소실은 발행 중단으로 표현하고, 소비자가 `now - header.stamp > T`(T는 노드 파라미터, `now`는 ROS 시각)로 판정한다. 한 번도 오지 않은 경우도 같다.
- 주기와 위상은 계약이 아니다(참고값 20 Hz).
- QoS는 "계약 토픽 QoS" 절의 상태 행이다.
- 넣지 않은 것: 자세(점 표적이다), 공분산과 신뢰도(읽는 소비자가 없다), 위경도와 원점(생산자가 world 원점으로 변환한다).

## VehicleState

고정 시점: 고정 전(Phase 2 완료에 고정).

토픽 `/<vehicle_id>/vehicle_state`. 기체 요약 상태이고 Telemetry Collector가 기체마다 발행한다. 공통 토픽은 두지 않는다(ROS 2 메시지에는 key가 없어 한 토픽의 발행자들이 구독자의 history depth를 나눠 쓴다). 소비자는 Fleet Manager, WebSocket, 테스트다.

| 필드 | 의미 |
| --- | --- |
| `header.stamp`, `header.frame_id` | 이 메시지를 만든 ROS 시각, `FRAME_ID`(`world`) |
| `vehicle_id` | 토픽 네임스페이스와 같은 값 |
| `system_id` | `vehicle_status`와의 대조를 통과한 MAVLink system id. 표시와 진단용 |
| `arming_state` | `ARMING_UNKNOWN`, `ARMING_DISARMED`, `ARMING_ARMED` |
| `flight_mode` | `MODE_*`. 비행제어의 실제 모드(`nav_state`)에서 온다. Offboard setpoint로 상승하는 동안은 TAKEOFF가 아니라 OFFBOARD다 |
| `failsafe` | 비행제어가 failsafe 동작 중 |
| `warnings` | `WARN_*` 비트의 OR. 비트 목록과 원천 대응은 Phase 2에서 정할 때까지 잠정이다 |
| `landed_valid`, `landed` | 지상 판정 |
| `position_valid`, `position` | world ENU(m). 위치 추정이 유효하고 world 변환이 가능할 때만 valid |
| `yaw_valid`, `yaw_rad` | world ENU yaw, `[-pi, pi)` |
| `velocity_valid`, `velocity` | world ENU(m/s) |
| `geodetic_valid`, `latitude_deg`, `longitude_deg`, `altitude_amsl_m` | WGS84. 지도 표시용 |
| `battery_valid`, `battery_remaining` | 0.0-1.0 |

- `MODE_*`의 잠정 대응: MANUAL은 조종사 입력 계열 전부, HOLD는 Hold(AUTO_LOITER), OFFBOARD는 OFFBOARD, TAKEOFF는 자동 이륙 계열, LAND는 AUTO_LAND, AUTO_PRECLAND, DESCEND, RTL은 AUTO_RTL, AUTO_OTHER는 그 밖의 자동 모드, TERMINATION은 비행 종료, OTHER는 변환표에 없는 값. 전체 표는 Phase 2에서 Collector 단위 테스트와 함께 확정한다. `MODE_HOLD`는 `MissionItem.TYPE_LOITER`와 다르다.
- 발행자 불변식: 발행자는 `vehicle_status`와의 식별 대조가 맞고 `vehicle_status`가 신선한 동안에만 발행한다. 따라서 메시지가 오면 `arming_state`, `flight_mode`, `failsafe`는 신선하다. 발행 중단은 `vehicle_status`만 본다. 위치, 자세, 측지 좌표, 배터리, 지상 판정의 원천이 신선도 임계보다 묵으면 해당 `*_valid`를 false로 하고 값을 0으로 둔다. 묵은 값을 valid로 내보내지 않는다. 발행 timer와 신선도 검사는 ROS 시각 기준이다.
- 소비자 조건.
  - (1) `vehicle_id`가 토픽 네임스페이스와 같은지 대조하고 다르면 버리고 경고한다.
  - (2) 미수신 시간은 소비자가 메시지를 받은 시점의 자기 ROS 시각으로 잰다. `header.stamp`는 표시와 진단용이다. 그래서 replay의 일시정지와 배속에서 가짜 이탈을 만들지 않는다.
  - (3) 이탈 판정은 소비자의 미수신 타임아웃 한 경로이고, 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다. 임계값의 순서는 `vehicle_status` 최대 발행 간격 < Collector 신선도 임계 < 소비자 미수신 타임아웃이다.
  - (4) 이탈은 goal의 종료를 뜻하지 않는다. goal의 종료는 action result만 정한다.
  - (5) `*_valid`가 false인 필드의 값(0)은 값으로 쓰지 않는다. 가용 판정은 `landed_valid`가 true일 때만 `landed`를 본다.
- replay: 기록물 안의 `vehicle_state`는 재생하지 않는다. 입력 토픽(`vehicle_status` 등)을 재생해 Collector가 다시 만든다. 기록물의 `vehicle_state`를 함께 재생하면 Collector와 이중 발행이 된다.
- QoS는 "계약 토픽 QoS" 절의 상태 행이다. 주기는 계약이 아니다(참고값 5 Hz).
- Protobuf의 `VehicleState`와 중첩 타입까지 멤버 단위로 1:1 대응하며, 변환은 `idsim_fleet`의 변환 모듈 한 곳에서만 하고 양방향 왕복 단위 테스트를 둔다(Phase 3). WebSocket JSON의 key는 msg 필드 이름 그대로다. 중첩과 enum의 JSON 표현은 Phase 2의 스키마 고정에서 정한다.
