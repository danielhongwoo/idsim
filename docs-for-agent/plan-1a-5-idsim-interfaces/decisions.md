# 1a 5단계 idsim_interfaces 설계 결정 (architect, 2026-11-10 확정)

입력: 담당자 의견서 셋(ros2, sim, ops. git 이력), 충돌 지점 재질문 답 네 건(ros2, ops, sim, px4. 아래 "재질문 결과 요약"), reviewer 검증 보고(필수 5건, 권고 8건)와 재확인 보고(비차단 6건), ros2-engineer 추가 실측(accept 뒤 abort, rosbag2의 action 기록), 사용자 결정 2건(2026-11-10). 뒤의 셋이 이 문서를 어떻게 바꿨는지는 "확정 개정 요약"에 있다. 이 문서는 확정본이고 구현은 이 문서를 따른다. 패키지 파일을 만든 뒤 5단계 PR에서 owner 다섯의 검토를 받았고 그 반영은 "5단계 PR owner 검토 반영"에 있다(필드와 상수는 바뀌지 않았다). `docs/` 반영(D)도 끝났다. `progress.md`는 호출한 쪽이 갱신한다.

표기: [실측]은 담당자가 이미지에서 직접 확인한 것(reviewer의 재현과 ros2-engineer의 2026-11-10 추가 실측 포함), [소스]는 PX4 v1.17.0 원문(reviewer가 사본의 commit과 blob hash를 v1.17.0 태그와 대조했다), [문서]는 공식 문서나 저장소 문서, [추정]은 확인하지 않은 판단이다. [추정]에 기대는 결정은 해당 쟁점에 따로 적었다.

## 확정 개정 요약 (2026-11-10)

사용자 결정(둘 다 architect 권고안 채택)
- 결정 1: 계약 고정 시점을 나눈다. 1a 완료에 공통 규칙, `ExecuteMission`, TAKEOFF, LOITER, LAND. 1b 완료에 `TargetState`, GOTO, TRACK_ENTITY, RTL. Phase 2 완료에 `VehicleState`.
- 결정 2: 6단계 이륙/착륙 노드는 `ExecuteMission` action 서버로 `[TAKEOFF, LOITER, LAND]` 미션을 받는다. 따라서 Hold 취소 실험을 6단계로 당긴다.

reviewer 필수 5건의 해소

| 번호 | 지적 | 해소 | 위치 |
| --- | --- | --- | --- |
| 1 | "정의는 사용자 결정과 무관하게 같다"가 성립하지 않는 조합이 있다 | 두 결정이 모두 채택되어 조합이 하나로 확정됐다. 귀결은 "고정 시점과 범위 구분" 표 그대로다. sim의 공분산 제외 수용은 "`TargetState` 고정이 1b 완료"라는 조건부였고 결정 1이 그 조건을 채웠으므로 공분산 제외를 확정하며 재질문하지 않는다. 채택되지 않은 세 조합의 처리는 필요가 없어져 적지 않는다 | 고정 시점 절, 재질문 요약 sim Q1 |
| 2 | 고정 시점이 타입 단위로 나뉘지 않는다(중첩 타입의 변경이 상위 타입의 hash를 바꾼다) | "고정"의 단위를 그 파일의 직접 필드와 상수로 정의했다. 중첩 타입의 변경이 상위 타입의 RIHS01과 펼친 정의에 번지는 것은 상위 타입의 변경으로 보지 않는다. 이를 기계적으로 가르도록 직접 정의 golden을 더했다 | 고정 시점 절, 쟁점 10 |
| 3 | 취소 의미의 확인 시점이 서로 다르고 고정 시점보다 늦다 | Hold 실험(failsafe 진행 중의 Hold 명령, 확인 타임아웃)을 6단계 px4-engineer 몫으로 당겼다. 결과는 1a 고정(7단계) 전에 쟁점 9에 반영하고, 그 전까지 취소의 분기는 잠정이다. 세 곳의 시점을 6단계로 맞췄다 | 쟁점 9, 넘김 목록 |
| 4 | 기록물에서 `mission_id`와 결과를 뽑을 토픽이 없다 | [실측] Jazzy rosbag2는 action의 goal과 result를 기록하지 않고 action introspection도 없다. 일반 토픽 `MissionEvent.msg`를 더했다. action 정의는 바꾸지 않았다. 고정 시점은 Phase 2 완료다(사용자 결정 1의 기준의 예외. 고정 시점 절) | 쟁점 8, 쟁점 9 |
| 5 | accept 뒤 abort 경로에 실측이 없다 | [실측]으로 닫았다. `ACCEPT_AND_EXECUTE` 뒤 `handle_accepted`의 abort는 동작하고, `ACCEPT_AND_DEFER` 상태의 abort는 예외다. Executor는 `ACCEPT_AND_EXECUTE`만 쓴다 | 재질문 요약 ros2 Q4, 쟁점 9 |

reviewer 권고 8건의 처리

| 번호 | 권고 | 처리 |
| --- | --- | --- |
| 1 | roadmap 16행, 7번 문구를 문서 반영 목록에. 알림에 Land 명령과 지상 disarm 정책 포함. 취소 뒤 Hold로 남은 기체의 책임 | 수용. 문서 반영 목록, "사용자에게 알릴 것", 쟁점 9 |
| 2 | `vehicle_id`를 `stack.json`과 노드 params에 직접 싣는다. 다중 토큰 거부 단위 테스트 | 수용. 쟁점 1. 스키마 변경은 devops-engineer가 6단계 착수 때 확인한다 |
| 3 | EKF 원점 오차를 1b 첫 작업으로 실측하고 임계값을 그 결과로 정한다. 링크 없는 [문서] 표시 | 수용. 쟁점 3, 넘김 목록. 링크 없는 [문서] 두 곳(RELIABLE KEEP_LAST 1, Header 도구)은 [추정]으로 내렸다. 둘 다 결정이 기대지 않는다 |
| 4 | 원천이 묵은 값의 `*_valid`를 false로 | 수용. 쟁점 1 불변식 |
| 5 | "Hold에서 벗어나는 경로는 위치 무효뿐"의 표현 | 수용. "확인한 범위에서는"으로 낮추고 `commander_params` 기본값 대조를 6단계 px4-engineer에 넘겼다 |
| 6 | "Gazebo 화면의 Actor 위치는 참고용" 문장은 해법 (가)를 전제한다. architecture.md 22행 범위 문구 | 수용. 지금은 "소비자에게 정본은 `TargetState`다"까지만 계약에 넣는다. 나머지는 1b 해법 선택 뒤 |
| 7 | 판정의 독립 기준(스폰 pose), `FRAME_ID` 일치 단정, 작은 의미 셋, test 의존 선언, TrackEntity 지속 시간을 뺀 이유 | 수용. 쟁점 8, 9, 10, 11, 넘김 목록. 다만 `last_item_index`의 "시작 전 실패" 구분을 위한 필드는 더하지 않는다(그 구분을 읽는 소비자가 없다. 6단계 구현에서 필요가 드러나면 고정 전에 끝에 더한다) |
| 8 | opinion 파일의 음차 표기. `idsim_sim`이 패키지가 되면 패키지별 단정에 걸린다 | 수용. opinion 세 파일의 표기를 고쳤다(내용은 그대로). 뒤의 것은 devops 1b 항목 |

필드 목록의 변경: `MissionEvent.msg` 추가, 이름 상수 하나(`MissionEvent.TOPIC_NAME`)뿐이다. 기존 9개 메시지와 action의 필드, 상수는 reviewer 검증 전과 같다.

## 5단계 PR owner 검토 반영 (2026-11-10)

결과: ros2-engineer 승인(권고 4), test-engineer 승인(권고 2), sim-engineer 승인(문서 조건 1, 보완 2), ops-service-engineer 조건부 승인(조건 1), logging-engineer 조건부 승인(조건 3). 필드와 상수의 변경 요구는 없었다. 조건은 모두 반영했고, 권고 가운데 받지 않은 것은 없다(이번 PR에서 하지 않은 것은 넘김 목록으로 보냈다). 주석만 바뀌었으므로 golden 세 종류는 그대로다(계약 테스트 통과로 확인).

| 출처 | 항목 | 처리 | 위치 |
| --- | --- | --- | --- |
| ops 조건 | `VehicleState.msg` 머리 주석이 묵은 값을 덮지 못한다 | 반영. "원천이 신선도 임계보다 묵어도 해당 `*_valid`는 false, 발행 중단은 `vehicle_status`만 본다" 두 줄을 더했다 | `VehicleState.msg`, 쟁점 8 |
| ops 비차단 | 소비자 조건 넷, 즉시 abort되는 goal은 feedback 0건이고 Fleet은 feedback 수신을 수락 확인으로 쓰지 않는다, `ACCEPT_AND_EXECUTE`만 쓰는 것은 구현 규칙 | 앞의 둘은 7단계 `docs/interface.md`로, 뒤의 것은 6단계 Executor 설계 노트로 넘겼다. `.action` 주석에는 넣지 않는다 | 넘김 목록 |
| logging 조건 1 | `MissionEvent.stamp`의 시간 기준 | 반영. "Executor 노드 clock의 ROS 시각(`use_sim_time`이면 `/clock`)이고 벽시계가 아니다". 제안 문구의 "시뮬레이션 시간"은 쓰지 않았다(메시지는 시뮬레이터 비의존이다. 쟁점 7, sim 조건과 같은 이유) | `MissionEvent.msg`, 쟁점 8 |
| logging 조건 2 | 기록기와 발행자가 맺어지기 전의 사건 손실은 발행자 수 확인만으로 막히지 않는다. 기록 시작과 기록물 이름 확정의 순서 | 반영. 쟁점 8 `MissionEvent`의 QoS 항과 넘김 목록 logging Phase 2 항목, roadmap Phase 2 3번 | 쟁점 8, 넘김 목록 |
| logging 조건 3 | 인덱스 쪽 요구(결과 미상의 정의, 기간의 끝, key) | 반영. 쟁점 8 `MissionEvent`의 "인덱스 쪽 요구" 항 | 쟁점 8 |
| logging 주의 | 필드 변경과 인덱스 prototype은 Phase 2 초반에, 기록기 구독 QoS는 명시 override로 | 넘김 목록 logging Phase 2 항목 | 넘김 목록 |
| sim 조건 | 문서에 옮길 때 "sim 시각", "sim 시간"은 "ROS 시각(`use_sim_time`이면 `/clock`)"으로 | 반영. `docs/architecture.md`와 `docs/roadmap.md`는 그렇게 썼고, 이 문서의 쟁점 5 계약 문장과 `TargetState` 항도 고쳤다. 이 문서의 다른 "sim 시간" 표현(노드 파라미터의 시간 기준)도 7단계에서 같은 표기로 옮긴다 | 쟁점 5, 쟁점 8, 넘김 목록 |
| sim 보완 1 | "Actor 엔티티 자체는 `pose/info` 목록에 없다" | 반영 | 쟁점 5 사실 |
| sim 보완 2 | "`pose/info` 50 Hz, header stamp는 sim 시간 [실측]"을 사실 목록에 | 반영 | 쟁점 5 사실 |
| ros2 권고 1 | 펼친 정의 출력의 최상위 줄 == 직접 정의 가드 | 반영. golden 비교 전에 단정하고 갱신 모드에서도 한다. 결함 주입("uint8 status  # status")으로 실패를 확인했다 | `test_contract.py`, 쟁점 10 |
| ros2 권고 2 | 정의 작성 규칙(string 상수와 기본값에 "#" 금지, C++ 상수 사용 규칙) | 7단계 `docs/interface.md`로 넘겼다 | 넘김 목록 |
| ros2 권고 3 | `direct_definition`의 `"=" in line` 판정은 bounded string이나 공백이 든 기본값에서 어색하다 | 지금은 그런 필드가 없어 고치지 않고 넘김 목록에 적었다(그런 필드를 더하는 PR에서 `_CONSTANT` 정규식 기준으로 바꾼다) | 넘김 목록 |
| ros2 권고 4 | `<test_depend>ament_index_python</test_depend>` | 반영 | `package.xml`, 쟁점 11 |
| test 권고 1 | 갱신 모드가 조용히 통과한다 | 반영. 달라진 golden만 쓰고 파일마다 pytest 경고 "golden 갱신됨: <경로>"를 낸다 | `test_contract.py`, 쟁점 10 |
| test 권고 2 | ros2-engineer 의견서(git 이력)의 갱신 명령 예시는 동작하지 않는다 | 반영. 그 줄에 주석을 달았다 | ros2-engineer 의견서(git 이력) |

## 재질문 결과 요약

- ops Q1: 공통 토픽 `/fleet/vehicle_state` 안을 철회했다. 기체별 토픽을 수용한다. 조건 셋: 구독은 한 번 만들면 지우지 않고 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다, Fleet은 `msg.vehicle_id`와 토픽 네임스페이스를 대조한다, replay에서 기록물 안의 `vehicle_state`를 재생하지 않는다.
- ops Q2: `last_status_rx`, `link_ok` 제거를 수용했다. 조건: Collector의 신선도 검사와 발행 timer는 sim 시간 timer, 임계값 순서는 `vehicle_status` 최대 발행 간격 < Collector 신선도 임계 < Fleet 미수신 타임아웃. "끊김" 표시는 msg 필드가 아니라 소비자(WebSocket 어댑터, Fleet 레지스트리)가 만든다.
- ops Q3: goal의 `attempt`, result의 `outcome`, `mission_id`와 `attempt` 되울림 제거를 수용했다. Fleet은 goal handle로 배분을 구분할 수 있다. 조건: BUSY와 `vehicle_id` 불일치는 거절이 아니라 accept 뒤 abort이고 reason에 값이 있어야 한다.
- ops Q4: Header + geometry_msgs 통일을 수용했다. proto 서브메시지는 presence가 있으므로 "변환 모듈은 항상 채우고 게이트웨이는 None을 프로토콜 오류로 버린다"는 규칙이 필요하고, 멤버 수 비교 테스트는 중첩 타입까지 재귀로 한다.
- ops Q5: `MissionItem` 서브메시지 방식을 수용했다. proto `oneof`에는 빈 메시지 `Rtl {}`, `Land {}`를 둬 type과 case를 전단사로 맞춘다.
- ros2 Q1: 기체별 토픽에 찬성. [실측] 한 토픽에 writer 둘이 번갈아 발행하면 reader depth 1에서 한 기체의 표본만 남는다(RELIABLE, BEST_EFFORT 모두). ROS 2 메시지는 key가 없어 KEEP_LAST depth를 writer들이 나눠 쓴다. Fleet의 구독 목록은 params의 기체 목록으로 하고 그래프 탐색은 진단에만 쓰자는 의견이다(같은 도메인의 `ros2 topic pub`, 재생, 시험 도구가 유령 기체가 된다. [추정] SIGKILL된 참가자는 lease가 끝날 때까지 그래프에 남는다).
- ros2 Q2: 발행 KEEP_LAST 1을 철회했다. 계약은 reliability와 durability뿐, 구현 기본 depth는 양쪽 5에 찬성. [추정] RELIABLE writer가 KEEP_LAST 1이면 ack 전 표본을 다음 write가 덮어 느린 RELIABLE reader가 표본을 빠뜨릴 수 있다(출처 링크를 확인하지 못했다. depth는 계약 밖이라 결정이 기대지 않는다).
- ros2 Q3: 통일이 조건이면 Header + geometry_msgs. Header가 없으면 `ros2 topic delay`, message_filters, Lichtblick 플롯의 header.stamp 축을 잃는다. rosbag2, foxglove_bridge, `ros2 topic echo/hz`는 차이가 없다.
- ros2 Q4: goal의 `vehicle_id` 대조에 반대하지 않는다. accept 뒤 즉시 abort는 `ACCEPT_AND_EXECUTE`를 돌려준 뒤 `handle_accepted`에서 `abort(result)`를 부른다. busy 판정은 `handle_accepted` 안에서 mutex로 한다. [실측] Jazzy action 서버의 기본 `result_timeout`은 10 s다.
- ros2 추가 실측(2026-11-10, `idsim/ros-ws:local`, `--network none`, rmw_cyclonedds_cpp, 시험 action은 `ExecuteMission`을 흉내 낸 것)
  - [실측] 실행 중인 goal이 있을 때 둘째 goal(같은 `vehicle_id`)과 셋째 goal(다른 `vehicle_id`)은 둘 다 accepted 응답을 받고, 결과는 ABORTED에 `reason`이 BUSY, VEHICLE_ID_MISMATCH로 전달됐다. feedback은 0건이다. 첫 goal은 영향 없이 SUCCEEDED로 끝났다.
  - [실측] abort가 `handle_accepted` 안에서 동기로 끝나므로 BUSY goal에 cancel이 끼어드는 경쟁 구간이 없다. 이미 끝난 BUSY goal에 cancel을 보내면 `ERROR_GOAL_TERMINATED`가 오고 결과는 ABORTED 그대로다. `async_cancel_all_goals`는 실행 중인 goal만 대상으로 한다.
  - [실측] 취소 요청 뒤(CANCELING)에 `canceled`, `abort`, `succeed` 어느 것으로 끝내도 예외 없이 그 상태와 `reason`이 전달된다. 쟁점 9의 "Hold 미확인이면 ABORTED" 분기가 action 계층에서 표현된다.
  - [실측] `ACCEPT_AND_DEFER` 상태에서 abort를 부르면 예외다("goal_handle attempted invalid transition from state ACCEPTED with event ABORT"). Executor는 `ACCEPT_AND_EXECUTE`만 쓴다.
  - [실측] rosbag2 0.26.11은 action의 `send_goal`, `get_result`, `cancel_goal`을 기록하지 않는다. `--include-hidden-topics`를 줘야 `_action/feedback`과 `_action/status`만 남는다(status에는 goal UUID와 상태 코드뿐). Jazzy의 `rcl_action`, `rclcpp_action`에는 introspection을 켜는 API가 없다.
- ros2 Q5: [실측] rosidl string 상수는 C++에서 템플릿 static 멤버(동적 초기화, 두 TU에서 주소 같음), Python에서 `str`이고 `ros2 interface show`에 나온다. C++에서 namespace 범위 static 초기화식에 쓰면 초기화 순서가 정해지지 않는다.
- sim Q1: 공분산 제외를 수용했다(`TargetState` 고정 시점이 1b 완료라는 조건). Phase 3까지 소비자를 대지 못한다. 사용자 결정 1로 그 조건이 충족되어 공분산 제외는 확정이다.
- sim Q2: QoS 잠정안을 수용했다.
- sim Q3: [실측] `set_spherical_coordinates` 뒤에도 월드 축은 ENU이고 heading은 0이다. 요청에 `heading_deg` 필드가 있고 넣으면 적용되며(90이면 월드 x축이 북쪽), 생략하면 0으로 덮인다. navsat 고도는 `origin.alt + 월드 z`다(38 + 10에서 48.00078). Gazebo는 geoid 보정을 하지 않는다.
- sim Q4: `world.origin` 필수화와 결정 (b)의 1b 구절 뒤집기에 찬성. wrapper 조건 다섯(쟁점 3).
- sim Q5: [실측] 이미지의 gz 관련 .so 중 `dynamic_pose` 문자열은 scene-broadcaster에만 있다. GUI가 쓰는 state 경로를 Actor 월드에 걸어도 서버는 살아 있었다. 실제 GUI 연결과 렌더링은 확인하지 못했다.
- sim Q6: 세 해법 어느 것에서도 TargetState 필드는 바뀌지 않는다. 계약 문장 셋이 필요하다(쟁점 5).
- px4 Q1: 취소 뒤 Hold가 맞다. [소스] armed 상태의 Hold 전환은 global position, local position, local alt가 유효해야 하고 아니면 거부되어 Offboard에 머문다. 이 프로젝트의 SITL 파라미터에서 Hold가 다른 모드로 넘어가는 경로는 위치 무효뿐이다(px4의 답 원문. 쟁점 9에서 "확인한 범위에서는"으로 범위를 낮췄다). 지상에서 armed로 취소되면 `COM_DISARM_PRFLT=-1` 때문에 무기한 armed로 남는다.
- px4 Q2: 모드 묶음에 `MODE_TERMINATION`을 더한다. [실측] v1.17.0 `VehicleStatus`의 NAVIGATION_STATE 전체를 묶음에 대응시켰다(쟁점 8의 표). Offboard 상승 중의 모드는 TAKEOFF가 아니라 OFFBOARD로 보인다.
- px4 Q3: [실측] `VehicleLocalPosition`에 `ref_lat`, `ref_lon`(float64), `ref_alt`(float32, AMSL), `xy_global`, `z_global`, `ref_timestamp`가 있다. [소스] gz SITL에서는 AMSL과 타원체 높이에 같은 navsat 고도가 들어간다. `EKF2_HGT_REF` 기본값은 GPS다. 원점이 PX4의 첫 GPS fix 전에 적용되어야 한다.
- px4 Q4: 1a 6단계는 takeoff -> loiter -> land로 표현된다. 필드 추가는 필요 없다. land 완료는 착륙 판정 뒤 자동 disarm까지다.

---

## 고정 시점과 범위 구분 (먼저 읽을 것)

`docs/architecture.md`는 계약을 "Phase 1a 완료 시점에 고정"한다고 적는다. 그런데 1a가 끝날 때 소비자가 있는 것은 이 패키지의 일부뿐이고, 소비자 없이 고정하면 틀린 정의를 계약으로 굳히게 된다. 사용자 결정 1(2026-11-10)로 고정 시점을 나눈다. 정의는 5단계에서 전부 만든다. `docs/architecture.md`와 `docs/roadmap.md`의 문장은 문서 반영 때 이 표대로 고친다.

| 묶음 | 고정되는 것 | 첫 소비자 | 고정 시점 | 뒤에 바꿀 때의 비용 |
| --- | --- | --- | --- | --- |
| 공통 규칙 | 단위, 좌표계, 시각, NaN 금지, 이름 규칙, QoS 계약, 변경 절차 | 1a 6단계 | 1a 완료 | 모든 정의에 번진다 |
| 미션 실행(1a 부분) | `ExecuteMission`(goal, result, feedback), `Mission`, `MissionItem`, `TakeoffItem`, `LoiterItem`, `YawSetpoint`의 직접 필드와 상수. TAKEOFF, LOITER, LAND 항목의 의미, 수락 정책, 취소 의미, `reason` 값의 의미(1b 부분 제외) | 1a 6단계(사용자 결정 2) | 1a 완료 | action은 replay 입력이 아니다. golden과 코드만 고친다 |
| 미션 실행(1b 부분) | `GoToItem`, `TrackEntityItem`의 직접 필드. GOTO, TRACK_ENTITY, RTL 항목의 의미, `REASON_TARGET_LOST`의 의미 | 1b | 1b 완료 | 위와 같다 |
| 표적 | `TargetState` | 1b | 1b 완료 | replay 입력이다. Phase 2에서 fixture 기록물이 생긴 뒤에 필드를 바꾸면 옛 기록물이 재생되지 않는다 |
| 기체 요약 | `VehicleState` | Phase 2 | Phase 2 완료(WebSocket JSON 스키마 고정과 함께) | Collector가 다시 만드는 파생 토픽이라 기록물은 안 깨진다. JSON key와 proto가 따라 바뀐다 |
| 미션 기록 | `MissionEvent` | 생산자는 6단계 Executor, 읽는 쪽은 6단계 통합 테스트와 Phase 2 기록물 인덱스 | Phase 2 완료 | replay 입력이 아니다. 인덱스가 읽는 fixture 기록물과 인덱스 코드를 고친다 |

"고정"의 정의

- 고정의 단위는 타입이 아니라 파일이다. 한 파일이 고정되면 그 파일의 직접 필드(이름, 타입, 순서, 기본값)와 상수(이름, 값), 그리고 이 문서와 `docs/interface.md`에 적힌 그 필드의 의미가 고정된다. 중첩된 타입의 내용은 그 타입의 파일이 고정될 때 고정된다.
- 중첩 타입이 바뀌면 그것을 담은 타입의 RIHS01과 `ros2 interface show` 출력도 바뀐다([실측] ros2). 이 전파는 상위 타입의 변경으로 보지 않는다. 예: 1b에서 `GoToItem`을 고치면 `MissionItem`, `Mission`, `ExecuteMission`의 type hash golden과 펼친 정의 golden이 함께 바뀌지만, 세 파일의 직접 필드와 상수가 그대로이면 1a에 고정된 계약의 변경이 아니다.
- 판정은 사람의 해석이 아니라 직접 정의 golden(쟁점 10)으로 한다. 고정된 파일의 직접 정의 golden이 바뀌면 고정된 계약의 변경이고, type hash golden이나 펼친 정의 golden만 바뀌면 중첩 타입에서 온 전파다. 전파가 허용되는 것은 그 중첩 타입이 고정되기 전까지다. 1b 완료 뒤에는 미션 타입의 어떤 golden 변경도 계약 변경이다.
- `MissionItem`의 직접 필드에는 `go_to`, `track_entity` 자리와 `TYPE_GOTO`, `TYPE_TRACK_ENTITY`, `TYPE_RTL`의 값이 들어 있고 이것은 1a 완료에 고정된다. 1b에 남는 것은 두 서브메시지의 내용과 세 항목의 의미다. 1b에서 서브메시지를 다른 타입으로 갈아야 하면 그것은 고정된 계약의 변경으로 다룬다.
- 상수는 고정 전후 모두 추가만 한다. 상수의 의미는 그 상수를 처음 쓰는 소비자가 생기는 묶음과 함께 고정된다(`WARN_*`는 Phase 2).

고정 전이든 후든 변경은 쟁점 10의 절차를 따른다. 고정 전에는 "첫 소비자의 구현에서 드러난 문제"가 변경 사유로 인정되고, 고정 뒤에는 새 요구가 있어야 한다.

`MissionEvent`의 고정 시점은 사용자 결정 1의 기준(첫 소비자가 생기는 Phase의 완료)의 예외다. 기준을 그대로 적용하면 1a 완료다(6단계 통합 테스트가 읽는다). 그런데도 Phase 2 완료로 둔다. 이 메시지는 사용자 결정 1의 목록에 없던 항목이고(결정 뒤에 더했다), 이 시점은 architect가 정했으며 사용자가 뒤집을 수 있다("사용자에게 알릴 것"). 예외의 이유는 셋이다. 첫째, 필드가 맞는지를 정하는 소비자는 Phase 2의 기록물 인덱스이고 그 owner인 logging-engineer가 5단계 토론에 없었다. 6단계 통합 테스트는 접수와 종료 사건이 왔는지와 `status`, `reason`만 읽어 나머지 필드를 검증하지 못한다. 둘째, action 정의와 분리된 토픽이라 이 메시지를 고쳐도 1a에 고정된 타입의 hash와 golden은 바뀌지 않는다. 셋째, replay 입력이 아니어서 늦게 고치는 비용이 인덱스 코드와 fixture 기록물에 그친다. 6단계에서 Executor가 발행하고 통합 테스트가 읽으므로 정의는 1a 안에서 한 번 실행된다.

지금 정하는 것과 미루는 것의 기준은 둘이다.

- 필드(타입 hash를 바꾼다)는 지금 아는 소비자 요구가 있는 것만 넣는다. 소비자를 대지 못하는 필드는 넣지 않는다(공분산, `attempt`, 배터리 전압).
- 상수(enum 값, 비트, 이름)는 추가해도 타입 hash가 바뀌지 않는다([실측] ros2). 그래서 최소 목록으로 시작하고 추가만 한다.

---

## 쟁점 1. VehicleState 토픽

결정: 기체별 토픽 `/<vehicle_id>/vehicle_state`가 계약이다. 메시지 안에도 `vehicle_id`를 둔다. 공통 토픽은 두지 않는다. Fleet이 구독 대상을 찾는 방법(params의 기체 목록인가, 그래프에서 타입으로 찾는가)은 계약이 아니며 Phase 3 설계 토론에서 정한다.

근거
- ROS 2 메시지에는 key가 없어 한 토픽의 writer들이 reader의 KEEP_LAST depth를 나눠 쓴다. [실측] depth 1에서 기체 하나의 표본만 남았다. 공통 토픽은 depth를 기체 수에 맞춰야 하고 기체끼리 표본을 밀어낸다. "기체 수만 바꿔 재사용"이 QoS 값에 묶인다.
- Fleet은 action `/<vehicle_id>/execute_mission` 때문에 어차피 기체별 이름을 조립한다. 공통 토픽이 그 일을 없애 주지 않는다.
- 로드맵 Phase 3 완료 기준 "기록물 하나에 3대 모두의 토픽이 네임스페이스로 구분"과 맞고, Lichtblick과 판정 코드가 기체별로 바로 구독한다.
- ops는 재질문에서 공통 토픽안을 철회했다.

Fleet의 발견 방식을 미루는 이유: ops는 그래프 탐색(자동 발견), ros2는 params 목록(유령 기체 방지)을 주장했고 둘 다 근거가 있다. 어느 쪽이든 아래 불변식만 계약에 있으면 성립하고, 1a-2의 구현에 영향이 없다.

계약에 넣는 불변식
- 발행자는 `vehicle_status`와의 식별 대조(`idsim_common`의 `verify`)가 Match가 되기 전과 어긋난 동안 발행하지 않는다.
- 발행자는 `vehicle_status`가 신선도 임계(노드 파라미터, sim 시간)보다 묵으면 발행을 멈춘다. 따라서 "VehicleState가 오면 비행제어 상태(`arming_state`, `flight_mode`, `failsafe`)는 신선하다". 이탈 판정은 소비자의 미수신 타임아웃(`/clock` 기준) 한 경로다. 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다.
- 발행 중단은 `vehicle_status`만 본다. 위치, 자세, 측지 좌표, 배터리, 지상 판정의 원천 토픽이 각자의 신선도 임계보다 묵으면 발행자는 해당 `*_valid`를 false로 하고 값을 0으로 둔다. 묵은 값을 valid로 내보내지 않는다(묵은 위치가 `position_valid=true`로 나가면 "가장 가까운 기체" 계산이 틀린다).
- 소비자는 `msg.vehicle_id`가 토픽 네임스페이스와 같은지 대조하고, 다르면 버리고 경고한다.
- replay에서는 기록물 안의 `vehicle_state`를 재생하지 않는다(Collector가 다시 만든다).
- 발행 timer와 신선도 검사는 sim 시간 기준이다(replay의 일시정지와 배속에서 가짜 이탈을 만들지 않는다).

`vehicle_id` 규칙: 기체 네임스페이스에서 앞의 "/"를 뗀 문자열이다(1a-3에서는 `px4_N`). 소비자는 내용을 해석하지 않는다(N을 뽑거나 sysid를 계산하지 않는다). 기체 번호를 정수로 싣지 않는다(결정 (u)가 금지한 파생을 소비자가 다시 하게 된다).

`vehicle_id`의 출처: 생성기가 `stack.json`의 기체 항목과 노드 params에 `vehicle_id`를 직접 싣는다. 노드와 테스트는 계산하지 않고 읽는다. `idsim_common`의 함수는 변환이 아니라 대조를 한다(노드의 네임스페이스가 "/" + `vehicle_id`인지, 토큰이 하나인지). 이렇게 하면 C++(`idsim_common`)과 Python(`tests/support`, Phase 2 WebSocket 어댑터)에 같은 변환의 사본이 생기지 않는다. 지금 `stack.json`에는 `ns`("/px4_1")와 `px4_ns`("px4_1")가 있고 `vehicle_id`는 없다. `px4_ns`는 PX4 쪽 설정 이름이라 운용 노드가 읽는 key로 쓰지 않는다.

구현 지시
- architect: 쟁점 8의 `VehicleState.msg`.
- devops-engineer(6단계): 생성기가 `stack.json` 기체 항목에 `vehicle_id`를 더하고 노드 params로 넘긴다. 생성기 golden을 갱신한다. 스키마의 세부(위치, 이름)는 6단계 착수 때 devops-engineer가 확인하고 이견이 있으면 architect에게 돌린다.
- ros2-engineer(6단계): `idsim_common`에 네임스페이스와 `vehicle_id`의 대조 함수와 단위 테스트(토큰이 둘 이상인 네임스페이스 거부 포함). 6단계의 goal 대조가 첫 소비자다.
- ops-service-engineer(Phase 2): Collector가 위 불변식을 지킨다. 임계값 순서(`vehicle_status` 최대 발행 간격 < 신선도 임계 < Fleet 타임아웃)는 1b 기록물로 `vehicle_status` 간격을 실측한 뒤 정한다.

## 쟁점 2. 상태 토픽의 QoS

결정: `VehicleState`와 `TargetState` 공통으로 계약은 reliability와 durability 둘뿐이다. 발행은 RELIABLE, VOLATILE. 구독은 BEST_EFFORT, VOLATILE. history와 depth는 계약 밖이고 구현 기본값은 양쪽 KEEP_LAST 5다. liveliness는 `Automatic`을 명시한다(결정 (s)와 같다). DDS deadline과 liveliness로 신선도를 판정하지 않는다(벽시계 기준이다). action은 rcl 기본 QoS를 바꾸지 않는다.

근거
- RELIABLE 발행은 BEST_EFFORT, RELIABLE 구독 모두와 맞는다. BEST_EFFORT 구독은 어떤 발행자(라이브, rosbag2 재생, 뒤에 생길 best-effort 어댑터)와도 맞는다. 로드맵 Phase 2의 "재생 시 구독자가 reliable을 요구해 못 받음" 함정이 구독자 쪽에서 닫힌다.
- sim(depth 5)과 ros2(depth 1)의 차이는 재질문에서 둘 다 "depth는 계약 밖, 구현 5"로 모였다. RELIABLE writer의 KEEP_LAST 1은 느린 RELIABLE reader(rosbag2)에게 표본을 빠뜨릴 수 있다([추정] ros2. depth가 계약 밖이라 결정이 기대지 않는다).
- TRANSIENT_LOCAL은 쓰지 않는다. 주기 토픽이라 늦게 붙어도 한 주기 안에 받고, 묵은 표본이 현재 값으로 오인될 여지만 생긴다.
- 결정 (s)와 같은 원칙(계약은 reliability와 durability)이라 `docs/interface.md`의 QoS 표가 한 형식이 된다.

[추정]에 기대는 부분: "rosbag2가 발행자 QoS를 기록하고 재생 때 그대로 쓴다"는 확인하지 않았다. 이 결정은 그 가정이 틀려도 성립한다(구독이 BEST_EFFORT다). Phase 2에서 logging-engineer가 확인한다.

주기는 계약이 아니다. 참고값은 `VehicleState` 5 Hz, `TargetState` 20 Hz(setpoint 주기 이상)이며 노드 파라미터다. 수신 판정은 "T초 안에 1회 이상"이다.

`MissionEvent`는 주기 토픽이 아니라 사건 토픽이라 이 절의 대상이 아니다. QoS는 쟁점 8의 `MissionEvent` 항에 있다.

구현 지시
- ros2-engineer(1b, 첫 발행자와 구독자가 생길 때): `idsim_common`에 `state_pub_qos()`, `state_sub_qos()`와 `qos_check_compatible` 단위 테스트(발행 대 구독 Ok, RELIABLE 구독 대 발행 Ok). 5단계에서는 만들지 않는다(소비자가 없다).
- test-engineer(1b): Python 판정 코드가 같은 값을 쓰고, 통합 테스트에서 `get_publishers_info_by_topic`으로 실제 발행 QoS의 reliability와 durability를 대조한다.

## 쟁점 3. world 프레임과 원점 변환

결정
- 계약 프레임은 하나, `"world"`다. 원점은 `config/fleet.yaml`의 `world.origin`(위도, 경도, 고도)이 가리키는 점이고 Gazebo 월드 (0, 0, 0)과 같다. 축은 x 동, y 북, z 위(ENU). yaw는 ENU yaw(동 0, 반시계 양, `[-pi, pi)`)다. 기체 로컬 NED와 위경도는 미션과 표적 계약에 나오지 않는다. `VehicleState`만 지도 표시용으로 WGS84를 함께 싣는다.
- world ENU <-> 기체 로컬 NED 변환 함수는 `idsim_common`에 한 곳만 둔다(1b, 결정 (q)의 "원점 이동은 1b에서 별도 함수"). 입력은 `VehicleLocalPosition`의 `ref_lat`, `ref_lon`, `ref_alt`(+ `xy_global`, `z_global`, `ref_timestamp`)와 params로 받은 `world.origin`이다. 부르는 쪽은 운용 노드(Executor, Collector)다. 스폰 pose는 운용 노드에 주지 않고 통합 테스트의 교차 검증에만 쓴다.
- `world.origin`은 메시지에 싣지 않는다. `stack.json`에서 생성된 params로 운용 노드와 표적 어댑터에 같은 값을 준다.
- `world.origin`은 1b 첫 작업에서 `fleet.yaml`의 필수 항목이 되고 유일한 출처가 된다. 커스텀 월드에서도 wrapper가 항상 `set_spherical_coordinates`로 적용한다. 결정 (b)의 "1b 커스텀 월드는 SDF `<spherical_coordinates>`에 넣고 wrapper는 건너뛴다"를 이것으로 뒤집는다. 1a에서는 지금처럼 선택 항목이다(원점을 읽는 노드가 없다).
- 고도: `world.origin.alt`는 기체의 전역 고도와 같은 기준으로 읽는다. world z = 기체 전역 고도 - `world.origin.alt`. SITL에서는 Gazebo가 geoid 보정을 하지 않고 PX4 AMSL과 타원체 높이에 같은 값이 들어가므로 기준 이름이 문제가 되지 않는다. 실기체에서는 AMSL로 읽는다(`ref_alt`가 AMSL이다).

근거
- ros2와 sim은 같은 안이다. 사용자 메모의 "충돌"은 "함수를 어디에 두는가"(ros2: `idsim_common`)와 "누가 계산하는가"(sim: 운용 쪽)로 서로 다른 질문에 답한 것이다. sim도 측지 계산은 `idsim_common` 한 곳이라고 적었다.
- `ref_lat/lon/alt`는 PX4가 실제로 쓰는 원점이고 EKF 원점 재설정(`ref_timestamp` 변화)을 따라갈 수 있으며 실기체에서도 같은 코드가 돈다. 스폰 pose는 Gazebo에만 있는 지식이라 운용 노드가 알면 레이어 경계가 깨진다.
- [실측] `set_spherical_coordinates` 뒤 월드 축은 ENU, heading 0, 고도는 `origin.alt + z`다. [실측] 필요한 여섯 필드가 v1.17.0에 있다.
- `world.origin`을 필수로 하는 시점이 Phase 2가 아니라 1b인 이유: 첫 소비자가 `VehicleState`가 아니라 1b의 goto와 track_entity다(world ENU 위치를 기체 NED setpoint로 바꾼다).
- 유일한 출처를 `fleet.yaml`로 두는 이유: 원점이 SDF에 있으면 `stack.json`이 그 값을 모르고, 운용 노드 params와 Gazebo가 다른 원점을 쓰는 조용한 실패가 생긴다.

계약에 넣는 조건
- GoTo와 TrackEntity 항목은 `xy_global && z_global`이 참이 되기 전에는 시작하지 않는다. takeoff, loiter, land는 원점이 필요 없다.
- `VehicleState.position_valid`는 위치 추정이 유효하고 world 변환이 가능할 때만 참이다.
- `ref_timestamp`가 바뀌면 변환을 다시 잡는다.

구현 지시(전부 1b. 5단계에서는 계약 문장만 정한다)
- ros2-engineer: 변환 함수와 단위 테스트.
- devops-engineer: 생성기가 `world.origin` 없음을 거부, `stack.json`에서 노드 params로 원점 전달, `targets[].id` 정규식(쟁점 4)과 중복 검사.
- sim-engineer: wrapper가 항상 원점을 적용하고 요청에 `heading_deg: 0`을 명시한다. SDF에 `<spherical_coordinates>` 값이 있고 `fleet.yaml`과 다르면 경고하고 덮어쓴다(실패로 만들면 PX4 기본 월드를 못 쓴다). 월드 SDF에 `<plugin>`이 있으면 UserCommands와 NavSat을 SDF에 직접 넣는다. 원점 적용 완료가 gazebo healthcheck 조건이고 px4가 그 뒤에 뜨는 1a의 순서를 유지한다(EKF 원점은 첫 GPS fix에서 잡힌다).
- px4-engineer와 test-engineer: 통합 테스트에 `|ref - world.origin|` 임계 검사(원점이 늦게 적용되면 수 km 어긋난다)와 스폰 pose 교차 검증. GPS 잡음으로 인한 EKF 원점 오차 크기는 1b의 첫 작업으로 실측한다([추정] 수십 cm. gz의 GPS 잡음은 감쇠가 있는 random walk라 첫 fix 때의 오차는 재 봐야 안다). 1b 판정 "표적 접근 거리 임계 이내"는 world 좌표 비교라 이 오차가 그대로 들어가므로, 그 임계값은 실측 결과를 보고 정한다. 좌표 계약 자체는 이 값에 기대지 않는다.

## 쟁점 4. 이름과 이름 상수

결정
- `VehicleState`: `/<vehicle_id>/vehicle_state`. `ExecuteMission`: `/<vehicle_id>/execute_mission`. `MissionEvent`: `/<vehicle_id>/mission_event`. `TargetState`: `/targets/<target_id>/state`.
- `target_id`: `^[a-z][a-z0-9_]{0,31}$`. [실측] ROS 이름 규칙이 숫자로 시작하는 토큰과 하이픈을 거부한다. 시뮬레이션에서는 `fleet.yaml`의 `targets[].id` = Gazebo 엔티티 이름 = 토픽 토큰 = 메시지 필드다. 정수로 두지 않는다(기체 번호와 섞인다).
- `mission_id`: `^[a-z0-9][a-z0-9_-]{0,63}$`. 불투명 문자열이며 실행 단위의 key다.
- 이름의 고정 부분은 메시지의 string 상수로 둔다: `VehicleState.TOPIC_NAME`, `MissionEvent.TOPIC_NAME`, `TargetState.TOPIC_PREFIX`, `TargetState.TOPIC_SUFFIX`, `Mission.ACTION_NAME`, 프레임 이름 `FRAME_ID`. 전체 이름의 조립과 id 검증은 C++은 `idsim_common`, Python 판정 코드는 `tests/support`가 이 상수로 한다.
- C++ 규칙: 이 상수를 namespace 범위 static 변수의 초기화식에 쓰지 않는다(함수와 생성자 안에서만 쓴다). lint로 강제하지 못하므로 검토 항목이다.

근거
- C++ 노드와 Python 판정 코드가 같은 출처를 쓴다. 상수는 `ros2 interface show` golden에 잡혀 이름 변경이 계약 변경으로 드러난다. `idsim_common`의 header에만 두면 Python 쪽에 사본이 생긴다.
- [실측] C++과 Python 모두에서 쓸 수 있고 ODR 문제가 없다. 동적 초기화라는 점만 규칙으로 막는다.
- 프레임 이름이 `"map"`이 아닌 이유: REP-105에서 `map`은 로봇 하나의 고정 프레임, `earth`는 ECEF다. `"world"`는 Gazebo와 ros_gz의 관례와 같다.
- 기체 목록과 표적 목록은 `stack.json`에서 생성된 params가 출처다. 미션에 적힌 `target_id`가 실제로 있는지는 운용 노드가 검사하지 않고 "항목 시작 뒤 T초 안에 유효 표본 없음"으로 드러난다(쟁점 9의 TARGET_LOST).

구현 지시
- architect: 상수를 쟁점 8의 정의에 넣는다.
- ros2-engineer(1b): `idsim_common`에 강타입 `TargetId`(정규식 검증)와 토픽 이름 조립 함수. `target_id` 필드와 토픽 토큰의 일치 검사도 여기 둔다.
- test-engineer(1b): `tests/support`가 같은 상수로 이름을 만든다.

## 쟁점 5. sim이 실측한 1b 리스크

사실([실측] sim, gz-sim 8.15.0. reviewer가 `idsim/sim-base:local`, `--network none`에서 재현했다)
- 스크립트 궤적 Actor의 pose는 `/world/<w>/pose/info`에 반영되지 않는다. Actor 엔티티 자체는 목록에 없고, 그 link만 상대 pose 0으로 고정되어 나온다.
- `/world/<w>/pose/info`는 50 Hz이고 header stamp는 sim 시간이다. ros_gz_bridge는 이 stamp를 ROS header로 그대로 옮긴다(아래 stamp 계약 문장의 근거).
- `PosePublisher`는 Actor에 붙지 않는다.
- Actor가 있는 월드에서 `/world/<w>/dynamic_pose/info`를 구독하면 서버가 `SceneBroadcaster::PoseUpdate`에서 segfault로 죽는다.

판단: 메시지 필드에는 영향이 없다. sim이 제시한 세 해법((가) 어댑터가 궤적 정의에서 직접 계산, (나) 정적 model을 서버 쪽에서 이동, (다) Actor 컴포넌트를 읽는 system) 어느 것에서도 `TargetState`의 필드는 같다(sim Q6). 영향을 받는 것은 계약 문장 셋과 설계 문서의 생산 경로 서술이다.

계약 문장(쟁점 8의 `TargetState`에 반영)
- `velocity_valid`는 언제든 false일 수 있다(첫 표본에 한정하지 않는다. 차분 방식은 궤적 반복 경계와 표본 누락 뒤에도 false가 된다).
- `header.stamp`는 "그 상태가 유효한 ROS 시각(`use_sim_time`이면 `/clock`)"이다. 발행 시각이 아니다. 주기와 위상은 계약이 아니다. "sim 시각"이라고 쓰지 않는다(메시지는 시뮬레이터 비의존이고 실기체 추적기도 생산자가 될 수 있다. sim 검토 조건).
- 소비자에게 정본은 `TargetState`다.

"Gazebo 화면의 Actor 위치는 참고용이며 보간 차이만큼 어긋날 수 있다"는 문장은 해법 (가)를 전제하므로 지금 계약에 넣지 않는다. 해법 (나)에서는 Gazebo가 원천이다. 1b 해법 선택 뒤에 정한다.

리스크 기록(문서 반영 때 `docs/roadmap.md` 리스크 표에 옮긴다. `progress.md` 반영은 호출한 쪽이 한다)

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| 스크립트 궤적 Actor의 pose가 서버 토픽에 없다 | `docs/architecture.md`의 "ros_gz_bridge로 받은 Gazebo pose를 변환"과 로드맵 1b 2번의 전제가 성립하지 않는다. 2026-11-06 결정 "표적 엔티티는 Gazebo Actor"를 다시 봐야 한다 | 1b 착수 때 설계 토론으로 해법을 고른다(sim-engineer 실측, 관련 owner는 devops(`targets` 스키마), ros2(bridge 설정)). 해법 (가)를 택하면 궤적 정의의 유일한 출처는 `fleet.yaml`의 `targets`이고 월드 SDF의 Actor는 생성한다. 그때 architecture.md의 생산 경로 문장을 고친다 |
| Actor 월드에서 `dynamic_pose/info` 구독이 서버를 죽인다 | bridge 설정이나 `gz topic -e` 한 번으로 gazebo 서비스가 내려가고 lockstep 때문에 PX4가 멈춘다 | bridge 설정의 금지 토픽으로 두고 생성기 단위 테스트가 검사한다(devops, sim. 1b). 운영 문서에 적는다 |
| Actor 월드에 `gz-gui`를 붙였을 때의 서버 생존은 미확인 | `viz` 프로필이 서버를 죽일 수 있다 | [실측] GUI 플러그인 .so에 `dynamic_pose` 문자열이 없고 state 경로는 안전했다. 실제 GUI 연결과 Actor 렌더링은 1b의 viz 확인 항목이다(sim) |
| 해법에 따라 설계 문서의 범위 문구가 달라진다 | 해법 (가)는 `docs/architecture.md`의 "Gazebo 안의 임의 이동 엔티티의 위치를 구독"과 "ros_gz_bridge로 받은 Gazebo pose를 변환"과 문구가 어긋난다 | 1b 설계 토론에서 범위 문구를 함께 본다. 범위 문구를 바꾸게 되면 사용자 결정으로 올린다 |

이 리스크들은 메시지 필드와 5단계, 6단계의 작업에 영향이 없다. `TargetState`의 고정이 1b 완료인 것도 이 리스크를 흡수한다(1b 해법이 계약 문장을 바꾸면 고정 전에 고친다).

## 쟁점 6. tools/ros_ws.sh의 테스트 수 단정

결정: devops-engineer의 몫이고 5단계 범위에 넣는다(작업 단위 C). `tools/ros_ws.sh test`의 단정을 "워크스페이스 합계 > 0"에서 "패키지마다 결과가 1건 이상"으로 바꾼다.

근거
- 지금 단정은 합계라서 `idsim_common`의 84건이 있으면 `idsim_interfaces`의 테스트가 0건이어도 통과한다. 두 번째 패키지가 생기는 5단계가 이 단정이 처음 부족해지는 시점이다.
- 이 패키지의 테스트는 계약 변경을 드러내는 유일한 장치(쟁점 10의 golden)다. 그 테스트가 수집되지 않은 채 통과하면 계약이 조용히 바뀐다.
- 변경이 작고 `ros_ws.sh`의 소유자가 devops-engineer다.

구현 지시
- devops-engineer: `colcon list -n`의 각 패키지에 대해 `build/<pkg>/test_results/` 아래 결과 XML의 테스트 수가 1 이상인지 본다. 테스트 없는 패키지를 일부러 두려면 스크립트 안의 명시 목록에 적게 한다(지금은 빈 목록). `--packages-select`로 일부만 돌릴 때는 돌린 패키지만 검사한다. 실패 메시지에 패키지 이름을 적는다.
- test-engineer: 규칙 승인. 검증은 4단계와 같은 방식(한 패키지의 테스트를 0건으로 만들면 종료 코드 1).
- 범위 밖으로 남기는 것: 기존 미해결 항목 "`ros_ws.sh tidy`의 PASS-NO-TARGETS". `idsim_interfaces`는 C++ 소스가 없어 tidy 대상이 0개인 것이 정상이므로 이번에 묶지 않는다.

## 쟁점 7. 필드 모양의 통일

결정: 패키지 전체를 `std_msgs/Header` + `geometry_msgs/Point`, `geometry_msgs/Vector3`로 통일한다. `header.frame_id`는 항상 `FRAME_ID` 상수와 같고 소비자는 다르면 버린다. 의존은 `builtin_interfaces`, `std_msgs`, `geometry_msgs`뿐이다. `geographic_msgs`, `unique_identifier_msgs`는 쓰지 않는다.

근거
- ops는 `VehicleState`만 평평한 원시 타입을 원했고 ros2와 sim은 Header + geometry_msgs였다. 한 패키지 안에서 `TargetState.position.x`와 `VehicleState.pos_e`가 섞이면 소비자가 두 관례를 다뤄야 한다.
- Header가 없으면 `ros2 topic delay`, message_filters, Lichtblick 플롯의 header.stamp 축을 잃는다([추정] ros2. 출처 링크를 확인하지 못했다. ops가 통일을 수용했으므로 결정은 이 문장 하나에 기대지 않는다). 얻는 것은 proto 거울 타입 셋(Time, Header, Vec3)을 줄이는 것뿐이고 ops가 재질문에서 비용이 작다고 수용했다.
- "Protobuf와 1:1"은 중첩 타입까지 멤버 단위로 대응한다는 뜻으로 읽는다.

공통 규칙(모든 정의)
- 단위는 SI다. 스칼라 필드 이름에 단위 접미사를 붙인다(`_m`, `_rad`, `_deg`). geometry_msgs 필드는 주석에 적는다.
- NaN과 무한대는 어떤 필드에도 넣지 않는다. 값이 없으면 `*_valid`를 false로 두고 값은 0이다. 근거: JSON에는 NaN이 없고, NaN은 변환과 setpoint 계산으로 번진다. NaN을 "제어 안 함"으로 쓰는 것은 PX4 `TrajectorySetpoint`의 관례이며 그 번역은 `idsim_mission` 안에서만 한다.
- enum은 uint8 상수이고 0은 "모름 또는 무효"다. 기본 생성된 메시지가 유효한 값이 되지 않게 한다. 소비자는 모르는 값을 UNKNOWN 또는 OTHER로 다룬다.
- 시각은 모두 ROS 시각(`use_sim_time`이면 `/clock`)이다. PX4 timestamp(us)는 어떤 필드에도 넣지 않는다(실기체에서 `UXRCE_DDS_SYNCT`를 되돌리면 축이 달라지고, 싣는 순간 소비자가 비행제어 시계를 알게 된다).
- PX4의 enum 값(`nav_state`, `arming_state`)과 PX4 용어는 계약에 넣지 않는다. PX4 -> 계약 값의 변환표는 Collector 한 곳에만 둔다.
- 필드 이름에 C, C++, Python 예약어를 쓰지 않는다([실측] `goto`는 C 생성기에서 컴파일 실패. 그래서 `go_to`).
- 메시지 주석은 한국어로 쓰고 단위와 좌표계를 필드마다 적는다. `.msg`, `.action`에는 저작권 머리말을 넣지 않는다(ament_copyright가 보지 않고 type description 원문에 들어간다).

## 쟁점 8. 메시지 정의 (확정)

아래가 5단계에서 만들 파일의 필드 목록이다. 주석은 파일에 쓸 때 다듬어도 되지만 필드의 이름, 타입, 순서, 상수 값은 이대로다. reviewer는 이 목록에서 고칠 결함을 찾지 못했다. 검증 뒤에 바뀐 것은 `MissionEvent.msg` 추가 하나다(이유는 그 항에 있다). 제목의 고정 시점은 그 파일의 직접 필드와 상수에 대한 것이다("고정 시점과 범위 구분").

### msg/VehicleState.msg (고정: Phase 2 완료)

```
# 기체 요약 상태. Telemetry Collector가 기체마다 발행한다. 토픽 /<vehicle_id>/vehicle_state
# 발행자는 vehicle_status와의 식별 대조가 맞고 vehicle_status가 신선한 동안에만 발행한다.
# NaN과 무한대는 어떤 필드에도 넣지 않는다. 값이 없으면 *_valid가 false이고 값은 0이다.
# 위치, 자세, 측지 좌표, 배터리, 지상 판정의 원천이 신선도 임계보다 묵어도 해당 *_valid는 false이고 값은 0이다.
# 발행 중단은 vehicle_status만 본다.
string TOPIC_NAME = "vehicle_state"
string FRAME_ID = "world"

uint8 ARMING_UNKNOWN = 0
uint8 ARMING_DISARMED = 1
uint8 ARMING_ARMED = 2

uint8 MODE_UNKNOWN = 0
uint8 MODE_MANUAL = 1        # 조종사 입력 계열 전부
uint8 MODE_HOLD = 2
uint8 MODE_OFFBOARD = 3
uint8 MODE_TAKEOFF = 4
uint8 MODE_LAND = 5
uint8 MODE_RTL = 6
uint8 MODE_AUTO_OTHER = 7    # 위에 없는 자동 모드
uint8 MODE_TERMINATION = 8   # 비행 종료
uint8 MODE_OTHER = 255       # 변환표에 없는 값

uint32 WARN_LOCAL_POSITION_INVALID = 1
uint32 WARN_GLOBAL_POSITION_INVALID = 2
uint32 WARN_BATTERY_LOW = 4
uint32 WARN_BATTERY_CRITICAL = 8
uint32 WARN_OFFBOARD_SIGNAL_LOST = 16
uint32 WARN_PREFLIGHT_CHECK_FAILED = 32

std_msgs/Header header         # stamp: 이 메시지를 만든 시각. frame_id: FRAME_ID
string vehicle_id              # 기체 네임스페이스에서 앞의 "/"를 뗀 값. 토픽 네임스페이스와 같다
uint8 system_id                # vehicle_status와의 대조를 통과한 MAVLink system id. 표시와 진단용

uint8 arming_state             # ARMING_*
uint8 flight_mode              # MODE_*. 비행제어의 실제 모드
bool failsafe                  # 비행제어가 failsafe 동작 중
uint32 warnings                # WARN_* 비트의 OR

bool landed_valid
bool landed                    # 지상 판정

bool position_valid            # false면 position은 0
geometry_msgs/Point position   # world ENU, m
bool yaw_valid
float64 yaw_rad                # world ENU yaw, [-pi, pi)
bool velocity_valid
geometry_msgs/Vector3 velocity # world ENU, m/s

bool geodetic_valid
float64 latitude_deg           # WGS84
float64 longitude_deg
float64 altitude_amsl_m

bool battery_valid
float32 battery_remaining      # 0.0-1.0
```

- `MODE_*` 묶음의 대응(px4 [실측], 전체 표는 Phase 2에서 px4-engineer가 Collector 단위 테스트와 함께 확정): MANUAL은 수동 계열 전부, HOLD는 AUTO_LOITER, RTL은 AUTO_RTL, OFFBOARD는 OFFBOARD, TAKEOFF는 AUTO_TAKEOFF 계열, LAND는 AUTO_LAND, AUTO_PRECLAND, DESCEND, AUTO_OTHER는 AUTO_MISSION, FOLLOW_TARGET, ORBIT, EXTERNAL1-8, TERMINATION은 TERMINATION, OTHER는 FREE 슬롯과 범위 밖. 단위 테스트는 `NAVIGATION_STATE_*` 상수 전부를 넣어 UNKNOWN으로 떨어지는 값이 없음을 확인한다.
- `flight_mode`는 실제 모드(`nav_state`)에서 온다. Offboard setpoint로 상승하는 동안은 TAKEOFF가 아니라 OFFBOARD다. `MissionItem.TYPE_LOITER`(Offboard에서 setpoint 유지)와 `MODE_HOLD`(비행제어의 Hold 모드)는 다른 것이다. `docs/interface.md`에 적는다.
- `WARN_*` 비트의 원천 필드 대응은 Phase 2에서 px4-engineer가 정한다. 그때까지 비트 목록은 잠정이다(상수라 타입 hash에 영향이 없다).
- 넣지 않은 것과 이유: `last_status_rx`, `link_ok`(쟁점 1의 발행 중단 불변식으로 대체), `nav_state` 원값(계약이 PX4 태그에 묶인다. 디버깅은 기록물의 `vehicle_status`로), 기체 번호 정수(쟁점 1), 배터리 전압(읽는 소비자가 없다. Phase 2 고정 전에 필요가 확인되면 더한다).
- Collector 입력에 `vehicle_land_detected`가 필요하다(로드맵 Phase 2 1번 목록에 없다. `idsim_common` 기술자는 이미 있다). 로드맵 반영은 문서 작업에 넣는다.

### msg/TargetState.msg (고정: 1b 완료)

```
# 표적 하나의 상태. 시뮬레이터 비의존. 토픽 /targets/<target_id>/state
string TOPIC_PREFIX = "/targets"
string TOPIC_SUFFIX = "state"
string FRAME_ID = "world"

std_msgs/Header header          # stamp: 이 상태가 유효한 시각(발행 시각이 아니다). frame_id: FRAME_ID
string target_id                # ^[a-z][a-z0-9_]{0,31}$. 토픽의 <target_id>와 같다
geometry_msgs/Point position    # world ENU, m
bool velocity_valid             # 언제든 false일 수 있다. false면 velocity는 0
geometry_msgs/Vector3 velocity  # world ENU, m/s
```

- stamp는 0이 아니고 같은 `target_id`에서 단조 증가한다. 소비자는 증가하지 않는 표본을 버린다.
- 소실 플래그와 종료 메시지는 없다. 소실은 발행 중단으로 표현하고 소비자가 `now - header.stamp > T`(T는 노드 파라미터. `now`는 ROS 시각이고 `use_sim_time`이면 `/clock`)로 판정한다. 한 번도 오지 않은 경우도 같은 규칙이다.
- 소비자는 `target_id`가 토픽 토큰과 다르면 버린다.
- 넣지 않은 것과 이유: 자세(점 표적이다. 추적기가 주지 못하는 값을 소비자가 믿게 된다), 공분산(Phase 3까지 읽는 소비자가 없고 sim이 재질문에서 수용. 불확실도 표현은 `docs/architecture.md`의 "다루지 않는 것"에 가깝다), 신뢰도 스칼라, 위경도(생산자가 world 원점을 받아 변환한다), 원점(쟁점 3).

### msg/Mission.msg (고정: 1a 완료)

```
string ACTION_NAME = "execute_mission"

string mission_id      # ^[a-z0-9][a-z0-9_-]{0,63}$
MissionItem[] items    # 1개 이상. 순서대로 실행한다
```

- `mission_id`의 발급 주체는 1b에서는 YAML 로더, Phase 3에서는 Fleet이다. Executor는 내용을 해석하지 않는다.
- 넣지 않은 것과 이유: 사람용 이름, 생성 시각, 개정 번호, 배분 제약(요청 기체, 우선순위). Executor가 쓰지 않는 값이고 Fleet 내부 상태와 gRPC 요청에 있으면 된다.

### msg/MissionItem.msg (고정: 1a 완료. GOTO, TRACK_ENTITY, RTL의 의미는 1b 완료)

```
uint8 TYPE_TAKEOFF = 1
uint8 TYPE_GOTO = 2
uint8 TYPE_TRACK_ENTITY = 3
uint8 TYPE_LOITER = 4
uint8 TYPE_RTL = 5
uint8 TYPE_LAND = 6

uint8 type                           # TYPE_*. 0은 무효
builtin_interfaces/Duration timeout  # 이 항목의 제한 시간(sim 시간). 0보다 크다
TakeoffItem takeoff                  # type == TYPE_TAKEOFF일 때만
GoToItem go_to                       # type == TYPE_GOTO일 때만
TrackEntityItem track_entity         # type == TYPE_TRACK_ENTITY일 때만
LoiterItem loiter                    # type == TYPE_LOITER일 때만
```

- 쓰지 않는 서브메시지는 기본값이어야 하고 아니면 검증에서 거부한다. RTL과 LAND는 서브메시지가 없다.
- setpoint 항목(TAKEOFF, GOTO, TRACK_ENTITY, LOITER)과 모드 명령 항목(RTL, LAND)의 구분은 필드로 두지 않고 type에서 파생한다. 분류 함수는 `idsim_mission`에 두고, 모든 `TYPE_*` 상수가 정확히 한 분류에 속하는지 단정하는 테스트를 둔다(6단계). 분류 필드를 두면 type과 어긋난 조합이 표현 가능해진다.
- 모든 값은 명시적이어야 한다. "0이면 기본값" 규칙은 없다. 기본값은 YAML 로더가 채운다. 표적 신선도 임계와 setpoint 주기 같은 안전 값은 메시지가 아니라 노드 파라미터다.
- 좌표는 world ENU 하나다. 기체 로컬 NED면 기체마다 원점이 달라 재배분 때 미션을 다시 써야 한다.
- 서브메시지 방식을 택한 이유(ops의 평평한 구조 대신): "goto인데 duration을 채움" 같은 실수를 `operator==` 한 줄로 잡고 proto `oneof`와 1:1이다. ops가 재질문에서 수용했다.

### msg/YawSetpoint.msg (고정: 1a 완료)

```
uint8 MODE_KEEP = 1    # 항목 시작 때의 yaw 유지
uint8 MODE_FIXED = 2   # yaw_rad로

uint8 mode             # MODE_*. 0은 무효
float64 yaw_rad        # world ENU yaw, [-pi, pi). MODE_FIXED일 때만. 아니면 0
```

### msg/TakeoffItem.msg (고정: 1a 완료)

```
float64 height_m       # 항목 시작 위치 기준 상대 높이. 0보다 크다
float64 acceptance_m   # 수직 허용 오차. 0보다 크다
YawSetpoint yaw
```

- Offboard position setpoint로 상승한다(비행제어의 자동 이륙 모드가 아니다). 지상 상태에서만 시작할 수 있고 공중이면 PRECONDITION_FAILED로 끝난다. 상승 속도 필드는 두지 않는다(비행제어 파라미터가 제한한다. [추정] 6단계에서 확인).

### msg/LoiterItem.msg (고정: 1a 완료)

```
builtin_interfaces/Duration duration   # 0보다 크고 timeout보다 짧다. 항목 시작 때의 setpoint를 유지한다
```

### msg/GoToItem.msg (고정: 1b 완료)

```
geometry_msgs/Point position   # world ENU, m
float64 acceptance_radius_m    # 3차원 거리 허용 오차. 0보다 크다
YawSetpoint yaw
```

### msg/TrackEntityItem.msg (고정: 1b 완료)

```
string target_id               # TargetState.target_id
geometry_msgs/Vector3 offset   # world ENU, m. 표적 위치에 더한 점이 setpoint다. 0 벡터는 검증에서 거부한다
float64 acceptance_radius_m    # setpoint 점까지 이 거리 안에 들면 항목 완료. 0보다 크다
YawSetpoint yaw
```

- 0 벡터를 거부하는 이유: 표적 위치 그대로면 충돌인데 시뮬레이션 Actor는 충돌이 없어 테스트에서 드러나지 않는다(sim).
- 넣지 않은 것과 이유: 지속 시간 종료 조건(sim 제안). 1b 통합 테스트의 판정은 접근 거리이고 "T초 동안 추종한 뒤 다음 항목"을 쓰는 미션이 1b에 없다. `timeout`은 실패(ITEM_TIMEOUT)라 대신 쓸 수 없으므로, 필요해지면 1b 고정 전에 이 파일 끝에 필드를 더한다.
- 원점을 기다리는 동안(쟁점 3의 `xy_global && z_global`)도 항목의 `timeout`이 흐른다. 넘기면 ITEM_TIMEOUT이고 `detail`에 사유를 적는다. GoTo에도 같다. 1b 묶음이라 1b 구현에서 확정한다.

### action/ExecuteMission.action (고정: 1a 완료)

```
# goal
string vehicle_id      # 받는 쪽이 자기 vehicle_id와 다르면 VEHICLE_ID_MISMATCH로 중단한다
Mission mission
---
# result. 성공, 중단, 취소의 정본은 action의 GoalStatus다
uint8 REASON_NONE = 0
uint8 REASON_INVALID_MISSION = 1
uint8 REASON_VEHICLE_ID_MISMATCH = 2
uint8 REASON_BUSY = 3
uint8 REASON_NOT_READY = 4
uint8 REASON_ARM_REJECTED = 5
uint8 REASON_MODE_SWITCH_FAILED = 6
uint8 REASON_ITEM_TIMEOUT = 7
uint8 REASON_FAILSAFE = 8
uint8 REASON_EXTERNAL_MODE_CHANGE = 9
uint8 REASON_TARGET_LOST = 10
uint8 REASON_LINK_LOST = 11
uint8 REASON_PRECONDITION_FAILED = 12
uint8 REASON_INTERNAL = 255

uint8 reason               # REASON_*
uint32 items_completed     # 완료한 항목 수
uint32 last_item_index     # 끝날 때 실행 중이던 항목(0부터). 항목을 시작하기 전에 끝났으면 0
string detail              # 사람이 읽는 설명. 판정에 쓰지 않는다
---
# feedback
uint8 PHASE_PREPARING = 1      # 식별 대조, arm, Offboard 진입
uint8 PHASE_EXECUTING = 2
uint8 PHASE_WAITING_MODE = 3   # 모드 명령 항목에서 모드 전이 확인 대기
uint8 PHASE_CANCELING = 4      # 취소 요청 뒤 정리 중

builtin_interfaces/Time stamp
uint32 item_index              # 0부터
uint32 item_count
uint8 item_type                # MissionItem.TYPE_*
uint8 phase                    # PHASE_*
bool distance_valid
float64 distance_remaining_m   # takeoff는 남은 높이, goto와 track_entity는 setpoint 점까지
```

- 넣지 않은 것과 이유: goal의 `attempt`와 result, feedback의 `mission_id`, `attempt` 되울림(Fleet은 goal handle로 배분을 구분한다. `attempt`는 Fleet 내부 상태와 proto에만 둔다. ops 수용), result의 `outcome`(GoalStatus와 두 출처가 된다), `final_arming`, `final_landed`(없어도 동작하고 `VehicleState`가 정본이다), 단일 백분율(track_entity와 loiter에서 거짓이 된다).
- 기록물 인덱스의 미션 id와 결과는 이 action이 아니라 `MissionEvent`에서 얻는다. feedback에 `mission_id`를 되돌리지 않는 이유: feedback을 한 번도 내지 않고 끝나는 goal(BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION, NOT_READY)은 UUID와 `mission_id`를 잇지 못하고, result의 `reason`은 어떤 경우에도 기록물에 남지 않는다([실측] ros2). 그것까지 feedback에 넣으면 feedback이 결과의 두 번째 출처가 된다.
- `reason`의 경계: NOT_READY는 항목을 시작하기 전(PHASE_PREPARING)에 기체가 준비되지 않은 경우다(식별 대조 미완 또는 불일치, 비행제어 상태 미수신, arm 전 점검 미통과). PRECONDITION_FAILED는 항목을 시작할 때 그 항목의 시작 조건이 맞지 않는 경우다(공중에서 TAKEOFF).
- `last_item_index`는 "0번 항목 실행 중 실패"와 "항목 시작 전 실패"를 구분하지 못한다. 구분을 위한 필드는 두지 않는다. Fleet의 다음 동작은 `reason`으로 갈리고 이 구분을 읽는 소비자가 없다. 6단계 구현에서 필요가 드러나면 1a 고정 전에 result 끝에 더한다.

### msg/MissionEvent.msg (고정: Phase 2 완료)

```
# 미션 실행의 접수와 종료 기록. Mission Executor가 goal마다 두 번 발행한다. 토픽 /<vehicle_id>/mission_event
string TOPIC_NAME = "mission_event"

uint8 STATUS_UNKNOWN = 0
uint8 STATUS_ACCEPTED = 1    # goal 접수. action_msgs/GoalStatus의 같은 이름과 같은 값
uint8 STATUS_SUCCEEDED = 4
uint8 STATUS_CANCELED = 5
uint8 STATUS_ABORTED = 6

builtin_interfaces/Time stamp   # 이 사건이 일어난 시각. Executor 노드 clock의 ROS 시각(use_sim_time이면 /clock)이고 벽시계가 아니다
string vehicle_id               # 발행한 Executor의 vehicle_id. 토픽 네임스페이스와 같다
string mission_id               # goal에 적힌 값 그대로. 검증에 실패한 값일 수 있다
uint8[16] goal_id               # action goal의 UUID. _action/status, _action/feedback의 goal_id와 같다
uint8 status                    # STATUS_*
uint8 reason                    # ExecuteMission 결과의 REASON_*. 접수 때는 REASON_NONE
uint32 item_count               # goal의 항목 수
uint32 items_completed          # 접수 때는 0. 종료 때는 result와 같다
uint32 last_item_index          # 접수 때는 0. 종료 때는 result와 같다
string detail                   # 접수 때는 빈 문자열. 종료 때는 result와 같다
```

- 추가한 이유(reviewer 필수 4, ros2 실측): [실측] Jazzy rosbag2는 action의 goal과 result를 기록하지 않고 action introspection이 없다. 지금 정의만으로는 기록물에서 미션 id와 실패 사유를 뽑을 토픽이 없어 로드맵 Phase 2의 기록물 인덱스가 성립하지 않는다. 일반 토픽 하나면 기록 정책이 hidden 토픽에 기대지 않는다.
- 발행 시점: goal이 접수됐을 때(`handle_accepted` 진입) STATUS_ACCEPTED 한 번, 종료 상태를 정했을 때 STATUS_SUCCEEDED, STATUS_CANCELED, STATUS_ABORTED 중 하나를 한 번. 거절을 쓰지 않으므로(쟁점 9) 정상 종료한 goal은 접수와 종료를 하나씩 갖는다. accept 뒤 즉시 abort되는 goal(BUSY 등)도 둘 다 낸다. Executor가 실행 중에 죽거나 스택이 내려가면 접수 사건만 남는다. 읽는 쪽(인덱스, 판정 코드)은 짝을 전제하지 않고, 종료 사건이 없는 접수를 결과 미상으로 다룬다.
- 정본은 action이다(GoalStatus와 result). `MissionEvent`는 기록과 관찰을 위한 사본이고, 운용 노드(Fleet)는 배분 판단에 쓰지 않는다. 종료 사건의 `status`, `reason`, `items_completed`, `last_item_index`, `detail`이 GoalStatus, result와 같다는 것을 Executor 단위 테스트로 묶는다.
- `status`의 값은 `action_msgs/GoalStatus`와 같게 둔다(기록물에서 `_action/status`와 바로 대조된다). 계약 테스트가 `action_msgs.msg.GoalStatus`의 상수와 같은지 단정한다. 타입은 다르고 값만 같다(GoalStatus는 `int8`, 여기는 쟁점 7의 규칙대로 `uint8`). 접수와 종료를 가르는 별도 필드는 두지 않는다(`status`와 어긋난 조합이 표현 가능해진다). EXECUTING, CANCELING 같은 중간 사건이 필요해지면 상수만 더한다(type hash가 바뀌지 않는다).
- `goal_id`를 `unique_identifier_msgs/UUID`가 아니라 `uint8[16]`으로 둔 이유: 쟁점 7의 의존 목록을 늘리지 않고 JSON과 proto로 옮기기 쉽다. 바이트 순서는 UUID의 `uuid` 필드와 같다.
- Header가 아니라 `stamp`인 이유: 좌표가 없어 `frame_id`가 뜻이 없다. feedback과 같은 모양이다.
- `vehicle_id` 불일치로 끝난 goal에서 이 필드는 goal에 적힌 값이 아니라 Executor 자신의 값이다. goal에 적힌 값은 `detail`에 적는다.
- QoS 계약: 발행 RELIABLE, VOLATILE. 구독 RELIABLE, VOLATILE. 사건 토픽이라 구독이 BEST_EFFORT이면 사건을 잃는다(상태 토픽과 다른 점). history와 depth는 계약 밖이고 구현 기본값은 KEEP_LAST 10이며 Phase 2에서 logging-engineer와 확정한다. TRANSIENT_LOCAL은 쓰지 않는다(지난 실행의 사건이 새 구독자에게 현재 사건으로 보인다). 따라서 기록과 테스트는 구독이 발행자와 맺어진 것을 확인한 뒤에 goal을 보낸다. 구독을 만든 것만으로는 부족하다(맺어지기 전에 나간 ACCEPTED 사건은 잃는다). 테스트처럼 goal을 보내는 프로세스가 구독도 가진 경우의 확인은 자기 구독의 발행자 수 조회로 하고 벽시계 대기나 재시도로 덮지 않는다. 기록기는 다르다(logging 검토 조건 2). rosbag2 recorder는 토픽을 주기적으로 탐색해 늦게 구독하므로, goal을 보내는 쪽이 발행자 수를 확인해도 기록기의 구독이 맺어졌다는 보장이 없다. Phase 2에서는 기록기의 구독이 생겼다는 신호(logger의 ready 서비스나 토픽, 또는 Executor 쪽 `get_subscription_count() >= 1` 게이트)가 있어야 goal을 보낸다. 방식은 Phase 2에서 정한다. 기록기의 구독은 RELIABLE, VOLATILE을 명시 QoS override로 고정한다.
- 인덱스 쪽 요구(logging 검토 조건 3. Phase 2 기록물 인덱스가 지킨다)
  - 실행 단위의 key는 (`vehicle_id`, `goal_id`)다. `mission_id`는 재사용될 수 있어 key로 쓰지 않는다. `item_count`, `items_completed`, `last_item_index`, `detail`은 `idsim-log show`의 표시용이다.
  - 종료 사건이 없는 접수는 결과 미상이다(실패가 아니다). 그 실행의 기간의 끝은 기록물의 마지막 메시지 시각으로 둔다.
  - 같은 기체에서 앞 접수의 종료 사건 없이 뒤의 ACCEPTED가 나오면 앞 접수도 결과 미상이다(Executor가 재시작한 경우다. BUSY로 끝나는 둘째 goal은 자기 종료 사건을 가지므로 이 경우와 `goal_id`로 구분된다).
  - 인덱스의 결과와 종료 시각 column은 미상(unknown) 값을 허용한다.
  - 필드를 바꾸면 type hash가 바뀌어 이전 fixture 기록물과 맞지 않는다. 필드 변경이 필요하면 Phase 2 초반에 하고, 그러려면 인덱스 prototype을 Phase 2 초반에 만든다.
- 넣지 않은 것과 이유: 항목별 진행 사건(feedback이 있고 `--include-hidden-topics` 없이도 필요하다는 소비자가 없다), `attempt`(Fleet 내부 상태), 미션 내용의 사본(goal 전체를 싣는 것은 기록 크기와 두 번째 출처 문제가 있다. 인덱스에는 id와 결과면 된다).
- logging-engineer는 이 메시지의 첫 소비자인데 5단계 토론에 들어오지 않았다. 5단계 PR에서 검토를 받았다(조건부 승인. 필드 구성에 이견이 없고 고정 시점 Phase 2 완료에 동의했다. 조건 셋은 위에 반영했다). Phase 2에서 인덱스 구현이 드러낸 문제는 고정 전 변경으로 받는다.

## 쟁점 9. ExecuteMission의 의미 (취소 포함)

결정

수락 정책
- Executor는 판단할 수 있는 goal을 모두 수락하고, 받을 수 없으면 즉시 ABORTED로 끝내며 `reason`을 싣는다(INVALID_MISSION, VEHICLE_ID_MISMATCH, BUSY, NOT_READY). 거절(reject)은 쓰지 않는다. 근거: ROS 2 action의 goal 거절은 이유를 실을 수 없고, Fleet의 다음 동작이 이유로 갈린다(BUSY는 다른 기체로 재시도, INVALID_MISSION은 미션 실패, VEHICLE_ID_MISMATCH는 설정 오류).
- 구현 방식은 하나다. `handle_goal`은 `ACCEPT_AND_EXECUTE`를 돌려주고, `handle_accepted` 안에서 mutex로 판정한 뒤 `abort(result)`를 부른다. [실측] 이 경로로 클라이언트가 ABORTED와 `reason`(BUSY, VEHICLE_ID_MISMATCH)을 받는다. `ACCEPT_AND_DEFER`는 쓰지 않는다([실측] 그 상태의 abort는 예외다).
- 실행 중인 goal은 선점하지 않는다. 두 번째 goal은 BUSY로 끝나고 첫 goal에 영향이 없다([실측] 첫 goal은 끝까지 실행되어 SUCCEEDED).
- goal의 `vehicle_id` 대조는 결정 (u)의 "params + 실제 값 대조"와 같은 취지다. 틀린 기체가 미션을 실행하는 것이 이 계약에서 가장 비싼 실수이고 문자열 비교 한 번으로 막는다.

GoalStatus와 `reason`
- SUCCEEDED이면 `reason`은 NONE. CANCELED이면 NONE. ABORTED이면 NONE이 아니다. 이 대응을 Executor 단위 테스트로 묶는다.
- `reason` 값은 추가만 하고 의미를 바꾸지 않는다. 255는 INTERNAL로 고정한다.

취소(ops 미해결 질문에 대한 답)
- 공중에서 취소되면 Executor는 setpoint 발행을 유지한 채 Hold 모드 명령(`idsim_common`의 `set_mode_hold`)을 보내고, 비행제어의 모드가 Hold로 바뀐 것을 확인한 뒤 CANCELED로 끝낸다.
- 정해진 시간(노드 파라미터, sim 시간) 안에 Hold가 확인되지 않으면 Land 명령을 보내고 ABORTED, MODE_SWITCH_FAILED로 끝낸다. 비행제어 상태가 오지 않아 확인할 수 없으면 ABORTED, LINK_LOST다.
- 지상에서 취소되면 모드 명령을 보내지 않는다. 다만 arm 상태이면 강제가 아닌 disarm 명령을 보내고 disarm을 확인한 뒤 CANCELED로 끝낸다.
- goal에 `on_cancel` 필드를 두지 않는다.

취소의 근거
- setpoint를 그냥 끊으면 `COM_OF_LOSS_T` 뒤 `COM_OBL_RC_ACT`가 정한 대체 동작으로 넘어가 취소 뒤 동작이 파라미터에 따라 달라진다. Offboard로 계속 위치를 유지하면 기체 상태가 Executor 프로세스의 생존에 묶인다. Hold는 비행제어가 스스로 유지하고 되돌릴 수 있는 가장 놀랍지 않은 상태다.
- [소스] px4: armed 상태의 Hold 전환은 위치 추정이 무효면 거부되어 Offboard에 머문다. 그래서 확인 실패 경로가 필요하다. 확인한 범위에서는 이 프로젝트의 SITL 파라미터에서 Hold가 다른 모드로 넘어가는 경로는 위치 무효다. 배터리, geofence, 바람, 비행 시간 failsafe는 Hold에서도 걸릴 수 있고 그 파라미터 기본값(`COM_LOW_BAT_ACT` 등)은 아직 대조하지 않았다(6단계 px4-engineer). 계약 필드에는 영향이 없다.
- [소스] px4: `COM_DISARM_PRFLT=-1`이라 지상에서 arm 상태로 취소되면 무기한 arm으로 남는다. 강제가 아닌 disarm은 지상 판정 상태에서만 받아들여지므로 공중에서 잘못 보내도 거부된다.
- `on_cancel`을 두지 않는 이유: Land와 RTL은 운용 정책이고 Fleet이 취소 뒤 land 항목 하나짜리 미션을 보내는 것으로 표현된다. 소비자가 없는 goal 필드를 지금 넣지 않는다. 필요해지면 쟁점 10의 절차로 더한다.
- [실측] ros2: 취소 요청 뒤(CANCELING)에 `canceled`로도 `abort`로도 끝낼 수 있고 `reason`이 전달된다. 위 분기는 action 계층에서 그대로 표현된다.
- [추정]으로 남는 것: failsafe 진행 중의 Hold 명령 동작, Hold 확인 타임아웃 값. 앞의 것은 취소의 분기(CANCELED인가 ABORTED인가)를 바꿀 수 있다. 사용자 결정 2에 따라 6단계에서 px4-engineer가 실험하고, 결과를 1a 고정(7단계 `docs/interface.md`) 전에 이 절과 `.action` 주석에 반영한다. 그때까지 취소의 분기는 잠정이다. 실험 전의 잠정 규칙: failsafe 동작 중에 취소가 오면 Hold 확인 실패와 같은 경로로 처리한다. 타임아웃 값은 노드 파라미터라 계약에 영향이 없다.

취소 뒤의 책임
- CANCELED로 끝난 기체는 공중에서 Hold로 남는다. 그 기체를 내리는 것은 취소를 요청한 쪽의 책임이다. Phase 3에서는 Fleet(취소 뒤 land 항목 미션을 보내거나 재배분한다), 그 전에는 통합 테스트 fixture(teardown에서 착륙과 disarm을 확인한다)와 손으로 goal을 보낸 사람이다. `sitl_params.env`가 Offboard 손실 동작에서 Hold를 기각한 이유("손실이 길어지면 상태가 결정되지 않는다")는 명령할 주체가 없는 경우의 이야기이고, 취소는 요청한 주체가 살아 있다. Executor가 죽은 경우는 취소가 아니라 Offboard 손실 경로(`COM_OBL_RC_ACT`)가 맡는다.

항목 완료의 의미
- TAKEOFF: 시작 위치 위 `height_m`에 `acceptance_m` 안으로 도달. LOITER: `duration` 경과. GOTO: `acceptance_radius_m` 안. TRACK_ENTITY: setpoint 점까지 `acceptance_radius_m` 안.
- LAND와 RTL: 지상 판정 뒤 disarm 확인까지가 한 항목이다(자동 disarm을 기다린다).
- 모든 항목은 `timeout`을 넘기면 ITEM_TIMEOUT이다. 도달 판정의 "N회 연속" 같은 구현 값은 노드 파라미터다.

1a에 필요한 범위: 6단계의 이륙-호버-착륙은 `[TAKEOFF, LOITER, LAND]` 미션 하나로 표현된다(px4 Q4). 사용자 결정 2에 따라 6단계 노드는 이 action을 실제로 제공한다(검증, 수락 정책, 취소, 실패 사유, `MissionEvent` 발행 포함). GOTO, TRACK_ENTITY, RTL 항목이 든 미션은 6단계 노드가 INVALID_MISSION으로 끝낸다(1b에서 구현할 때까지의 임시 동작이고 계약 문장이 아니다).

feedback 주기는 계약이 아니다. 참고값은 전이 시점과 2 Hz 이하다.

구현 지시
- architect: 위 의미를 `.action` 주석과 7단계 `docs/interface.md`에 적는다.
- 6단계 설계 토론으로 넘김(px4, ros2, test): Hold 실험(failsafe 진행 중의 Hold 명령, 확인 타임아웃 기본값)과 그 결과의 계약 반영, PREPARING 단계의 세부 순서, 분류 함수와 테스트, land 완료 판정 토픽, `MissionEvent` 발행과 종료 사건이 result와 같다는 단위 테스트, `last_item_index` 구분 필드가 필요한지. accept 뒤 abort 방식은 [실측]으로 닫혔으므로 토론 항목이 아니다(`ACCEPT_AND_EXECUTE`, `handle_accepted`의 mutex).

## 쟁점 10. 버전과 변경 절차

결정
- 메시지 안에 버전 필드나 버전 상수를 두지 않는다. `package.xml` 버전을 계약 식별에 쓰지 않는다. 타입 식별은 RIHS01 type hash가 한다. 근거: 단일 저장소, 단일 빌드라 실행 중 협상이 필요 없고, [실측] 상수는 hash에 들어가지 않아 버전 상수는 식별자가 되지 못한다.
- 계약 테스트(pytest, `idsim_interfaces/test/`)에 golden 셋과 상수 검사를 둔다.
  1. type hash golden `test/golden/type_hashes.txt`: 설치된 `share/idsim_interfaces/{msg,action}/*.json`의 RIHS01을 타입별 한 줄로. 중첩 타입의 변경이 상위 타입에 번진다.
  2. 펼친 정의 golden `test/golden/<msg|action>/<Type>.txt`: `ros2 interface show --no-comments`의 출력. hash가 잡지 못하는 상수 값 변경, 상수 추가, 기본값 변경을 잡는다. 중첩 타입을 펼치므로 `ros-base`를 올려 geometry_msgs가 바뀌는 것도 드러난다. 가드: [실측] ros2. `ros2 interface show`는 줄 끝 주석과 같은 문자열이 그 줄 앞부분에 다시 나오면 그 자리에서 줄을 자른다("uint8 status  # status"가 "uint8"이 된다). 잘린 출력이 golden에 굳으면 이후 변경을 놓치므로, 출력의 최상위 줄(들여쓰기 없는 줄을 직접 정의와 같은 방식으로 정규화한 것)이 직접 정의와 같다는 것을 golden 비교 전에 단정한다. 갱신 모드에서도 단정한다.
  3. 직접 정의 golden `test/golden/direct/<msg|action>/<Type>.txt`: 그 파일의 직접 필드와 상수만(원문에서 주석과 빈 줄을 빼고 공백을 정규화한 것. 중첩 타입은 타입 이름만 남는다). "고정"의 판정 단위다. 고정된 파일의 이 golden이 바뀌면 고정된 계약의 변경이고, 1번과 2번만 바뀌면 중첩 타입에서 온 전파다. [실측] 원문은 설치된 `share/idsim_interfaces/{msg,action}/`에 `.msg`, `.action`으로 들어 있고 계약 테스트는 거기서 읽는다(reviewer가 `action_msgs`에서, architect가 구현 때 자기 패키지에서 확인했다).
  4. 상수 검사: `MissionItem`의 `TYPE_*` 집합 == 기대 집합, 모든 enum에서 값 0을 가진 상수는 `*_UNKNOWN` 또는 `*_NONE`뿐이거나 없다, 이름 상수 값이 쟁점 4의 규칙과 맞다(`TOPIC_NAME`은 ROS 이름 토큰), `VehicleState.FRAME_ID` == `TargetState.FRAME_ID`, `MissionEvent`의 `STATUS_*` 값이 `action_msgs.msg.GoalStatus`의 같은 이름 상수와 같다.
- golden이 다르면 테스트가 diff와 갱신 방법(`IDSIM_UPDATE_GOLDEN=1`)을 출력하고 실패한다. 자동 갱신은 하지 않는다. 갱신은 `tools/ros_ws.sh shell` 안에서 `IDSIM_UPDATE_GOLDEN=1 colcon test --packages-select idsim_interfaces`로만 된다(`tools/ros_ws.sh test`와 `ci`는 이 변수를 컨테이너에 넘기지 않는다). 갱신 모드는 달라진 golden만 쓰고 파일마다 pytest 경고 "golden 갱신됨: <경로>"를 낸다(조용히 통과하지 않는다). 실패 메시지는 어느 종류의 golden이 다른지 적는다(직접 정의인지 전파인지가 PR에서 바로 보인다).
- 변경 규칙
  - 필드는 끝에 추가만 한다. 기존 필드의 이름, 타입, 의미, 단위를 바꾸지 않는다. 고정 전인 파일에서는 첫 소비자의 구현에서 드러난 문제에 한해 바꿀 수 있다. 고정 여부는 파일 단위이고 판정은 직접 정의 golden으로 한다("고정 시점과 범위 구분").
  - 상수 값은 재사용하지 않는다. enum 값과 비트는 추가만 한다.
  - "예약 필드"를 미리 두지 않는다(CDR은 위치 기반이라 자리를 잡아도 호환이 생기지 않는다).
  - 계약 변경 PR에는 golden 갱신, `docs/interface.md`, PR 본문의 결정 근거, (Phase 3 뒤) proto와 왕복 테스트, 영향받는 replay fixture 갱신이 함께 들어가고 architect 승인이 필요하다.
- Protobuf 스키마 규칙(스키마 설계는 architect, 파일은 Phase 3 착수 때 ops-service-engineer가 만든다. 1a에 코드 생성 도구를 들이지 않는다)
  - 패키지는 `idsim.fleet.v1`, 파일은 `proto/idsim/fleet/v1/`. 깨는 변경은 v2로만 한다.
  - 필드 번호는 ROS 필드 순서(1부터)와 같다. 번호는 재사용하지 않고 지운 필드는 `reserved`로 막는다.
  - enum은 0을 `*_UNSPECIFIED`로 두고 ROS의 0과 맞춘다. 경고 비트는 `uint32`다.
  - 시각은 `google.protobuf.Timestamp`가 아니라 `builtin_interfaces/Time`을 본뜬 메시지(`int32 sec`, `uint32 nanosec`)다(sim 시간은 epoch 의미가 없다). Header, Point, Vector3도 거울 메시지를 둔다.
  - `VehicleState`는 중첩까지 멤버 단위 1:1이다. 변환 모듈은 서브메시지를 항상 채우고 게이트웨이는 비어 있으면 프로토콜 오류로 버린다. `MissionItem`은 `oneof`(빈 `Rtl`, `Land` 포함)로 type과 case를 전단사로 맞춘다. 왕복 테스트는 중첩 타입까지 멤버 수를 재귀로 비교하고, 쓰지 않는 서브메시지가 기본값이 아니면 실패하는 경로를 포함한다.
  - WebSocket JSON의 `data` key는 msg 필드 이름 그대로다(`position.x`). 이것은 ops-service-engineer의 Phase 2 스키마에서 고정한다.

구현 지시
- architect: 계약 테스트와 golden(작업 단위 B).
- test-engineer: golden 갱신 절차와 `IDSIM_UPDATE_GOLDEN` 규칙 승인. 결함 주입 확인(필드 타입을 바꾸면 hash golden이, 상수 값을 바꾸면 정의 golden이 실패).

## 쟁점 11. 패키지 골격

결정
- `ament_cmake` + `rosidl_generate_interfaces(... DEPENDENCIES builtin_interfaces std_msgs geometry_msgs)`. `package.xml`: `buildtool_depend` `ament_cmake`, `rosidl_default_generators`. `depend` `builtin_interfaces`, `std_msgs`, `geometry_msgs`, `action_msgs`. `exec_depend` `rosidl_default_runtime`. `test_depend` `ament_lint_auto`, `ament_cmake_xmllint`, `ament_cmake_lint_cmake`, `ament_cmake_copyright`, `ament_cmake_pytest`, `ament_index_python`(계약 테스트가 직접 import한다), `ros2cli`, `ros2interface`(계약 테스트가 `ros2 interface show`를 부른다. 이미지에 이미 있지만 선언한다). `member_of_group` `rosidl_interface_packages`. xml-model 줄은 뺀다(unit job은 네트워크가 없다). license `Apache-2.0`, maintainer는 `idsim_common`과 같다.
- 생성기는 기본값 그대로 둔다(C, C++, Python, introspection, type description).
- 이 패키지에는 `-Werror` 같은 컴파일 옵션을 넣지 않는다(대상이 생성 코드뿐이다). 코드를 넣지 않는다(rosidl 전용).
- lint: `ament_lint_auto` + `ament_cmake_xmllint`, `ament_cmake_lint_cmake`, `ament_cmake_copyright`. cpplint는 넣지 않는다(대상 0개의 의미 없는 테스트가 된다). 저작권 머리말은 `CMakeLists.txt`와 테스트 `.py`에 넣는다.
- 테스트 `.py`는 `lint` job의 ruff와 `px4-api` 검사 대상이다.
- 파일: `msg/VehicleState.msg`, `msg/TargetState.msg`, `msg/Mission.msg`, `msg/MissionItem.msg`, `msg/YawSetpoint.msg`, `msg/TakeoffItem.msg`, `msg/GoToItem.msg`, `msg/TrackEntityItem.msg`, `msg/LoiterItem.msg`, `msg/MissionEvent.msg`, `action/ExecuteMission.action`, `test/test_contract.py`, `test/golden/`.

근거: ros2 의견 1절과 [실측](한글 주석 빌드, `action_msgs` 없이도 빌드되지만 rosdep을 위해 선언, colcon test 안에서 자기 패키지의 `ros2 interface show`와 Python import 동작. reviewer가 `tools/ros_ws.sh`와 같은 조건인 `--network none`, `CYCLONEDDS_URI` 비움, `ROS_DOMAIN_ID=99`에서 다시 확인했다).

## 넘김 목록

| 받는 쪽 | 시점 | 항목 |
| --- | --- | --- |
| px4-engineer | 6단계 | Hold 실험: failsafe 진행 중의 Hold 명령 동작, Hold 확인 타임아웃 기본값, 지상 취소에서 disarm이 거부되거나 확인되지 않을 때의 분기(PX4가 아직 landed가 아니면 강제가 아닌 disarm은 거부된다. 5단계 PR reviewer 지적). 결과는 1a 고정 전에 쟁점 9에 반영한다(architect와). `commander_params`의 배터리, geofence, 바람, 비행 시간 failsafe 기본값 대조. takeoff의 `acceptance_m` 기본값([추정] 0.3 m 이상), Offboard 상승 속도 제한 확인, land 완료 판정(지상 판정 뒤 자동 disarm) |
| px4-engineer | 1b 첫 작업 | EKF 원점과 스폰 지점의 오차 실측(표적 접근 임계값을 이 결과로 정한다), `ref_timestamp`가 비행 중 바뀌는 조건, navsat 고도와 `ref_alt` 대조, 실행 중 `EKF2_HGT_REF` 실제 값 확인 |
| px4-engineer | Phase 2 | `nav_state` -> `MODE_*` 전체 대응표와 Collector 단위 테스트 입력, `failsafe_flags` -> `WARN_*` 비트 대응, `vehicle_status` 최대 발행 간격 실측(uXRCE-DDS를 거친 뒤) |
| sim-engineer | 1b 착수 | 표적 생산 방식((가), (나), (다)) 실측과 선택, `dynamic_pose/info` 금지, Actor 월드에서 `gz-gui` 확인, wrapper의 원점 항상 적용과 `heading_deg: 0`, 커스텀 월드의 `<plugin>` 조건, `targets` 스키마(devops와), 표적과 기체 스폰 위치 겹침 검사, "Gazebo 화면은 참고용" 문장과 architecture.md 범위 문구의 처리 |
| ros2-engineer | 6단계 | 네임스페이스와 `vehicle_id`의 대조 함수(다중 토큰 거부 단위 테스트), action 서버 구현(`ACCEPT_AND_EXECUTE`만, `handle_accepted` 안의 mutex 판정. [실측]으로 확인된 방식. 이것은 계약 문장이 아니라 구현 규칙이므로 `.action` 주석이 아니라 Executor 설계 노트에 적는다), `MissionEvent` 발행(`stamp`는 노드 clock의 ROS 시각), 이름 상수를 namespace 범위 static 초기화식에 쓰지 않는 규칙의 검토 |
| ros2-engineer | 1b | world ENU <-> 로컬 NED 변환 함수, `state_pub_qos()`, `state_sub_qos()`, `TargetId`와 토픽 이름 조립 |
| ops-service-engineer | Phase 2 | Collector 불변식(쟁점 1. 원천이 묵은 값의 `*_valid` 포함), 임계값 순서, WebSocket JSON의 "끊김" 값은 어댑터가 만든다, JSON key는 msg 필드 이름 |
| ops-service-engineer | Phase 3 | Fleet의 발견 방식(params 목록 대 그래프 탐색) 설계 토론, `attempt`는 Fleet 내부와 proto에, action 서버 `result_timeout`(기본 10 s) 검토, 미션 의미 검증 함수를 Executor와 Fleet이 같이 쓰는 구조(`idsim_mission`의 ROS 비의존 라이브러리), 취소 뒤 Hold로 남은 기체의 처리, proto 파일 작성 |
| logging-engineer | 5단계 PR | (완료, 조건부 승인) `MissionEvent.msg` 필드 검토(기록물 인덱스의 요구와 맞는지) |
| logging-engineer | Phase 2 | 기록 대상에 `/<vehicle_id>/mission_event` 포함과 구독 depth 확정, 인덱스는 이 토픽에서 미션 id와 결과를 읽는다(action의 goal과 result는 기록되지 않는다. [실측]), 종료 사건이 없는 접수는 실패로 처리하지 않고 결과 미상으로 채운다, 기록기의 구독도 VOLATILE이라 발행자와 맺어지기 전에 나간 사건은 기록물에 없다(기록기가 Executor와 맺어진 뒤에 goal이 나가게 하는 순서는 Phase 2에서 정한다), `_action/status`와 feedback을 함께 기록할지(`--include-hidden-topics` 또는 명시 목록. `goal_id`로 잇는다), replay에서 `vehicle_state` 제외 규칙, rosbag2가 발행자 QoS를 기록하고 재생에 쓰는지, 기록물별 type hash 기록. 5단계 PR 검토에서 더한 것: (1) 기록기 구독 생성 신호. recorder는 토픽을 주기 탐색해 늦게 구독하므로 발행자 수 확인만으로 접수 사건의 손실이 막히지 않는다. logger의 ready 서비스나 토픽, 또는 Executor의 `get_subscription_count() >= 1` 게이트 중에서 정하고 그 뒤에 goal이 나가게 한다. (2) roadmap의 "미션 시작/종료에 맞춰 기록 시작"과 기록물 이름 `<시각>_<미션 id>_<기체 id>`의 순서. `mission_id`는 ACCEPTED에서야 알려지므로 미션 전에 기록을 시작하고 이름을 뒤에 확정하는 순서와 `mission_id`의 입력 경로를 정한다. (3) 인덱스 쪽 요구(쟁점 8 `MissionEvent` 항: key는 (`vehicle_id`, `goal_id`), 결과 미상의 정의, 기간의 끝, unknown 허용 column). (4) 기록기 구독은 RELIABLE, VOLATILE을 명시 QoS override로 고정하고 depth는 KEEP_LAST 10으로 충분하다. (5) `MissionEvent`의 필드 변경이 필요하면 Phase 2 초반에 한다(type hash가 바뀌어 fixture 기록물과 어긋난다). 인덱스 prototype을 Phase 2 초반에 만든다 |
| devops-engineer | 5단계 | `tools/ros_ws.sh`의 패키지별 테스트 수 단정(쟁점 6) |
| devops-engineer | 6단계 | `stack.json` 기체 항목과 노드 params에 `vehicle_id`(쟁점 1), 생성기 golden 갱신 |
| devops-engineer | 1b | `world.origin` 필수화와 params 전달, `targets[].id` 정규식과 중복 검사, bridge 설정의 금지 토픽 검사, `idsim_sim`이 colcon 패키지가 되면 패키지별 테스트 수 단정에 걸린다(테스트를 두거나 명시 목록에 적는다) |
| test-engineer | 5단계 | golden 갱신 절차 승인(golden 세 종류), 패키지별 단정 규칙 승인 |
| test-engineer | 6단계 | 통합 테스트가 `MissionEvent`의 접수와 종료 사건을 확인한다. 구독을 만들고 그 토픽의 발행자 수가 1 이상인 것을 확인한 뒤에 goal을 보낸다(sleep이나 재시도로 대신하지 않는다). 취소된 기체의 teardown(착륙과 disarm 확인). fixture의 프로세스 종료 방식: [실측] 비대화형 bash에서 `&`로 띄운 백그라운드 프로세스는 SIGINT를 무시한다. `kill -INT`로 끝나지 않아 실측 스크립트가 한 번 멈췄다. fixture는 SIGTERM으로 끝내거나 `setsid`(또는 `set -m`)로 프로세스 그룹을 만들어 그룹에 신호를 보낸다. `ros2 bag record`처럼 SIGINT로 끝내야 파일이 정리되는 프로세스에 특히 해당한다 |
| test-engineer | 1b | 상태 토픽 QoS 대조, 이름 상수 사용, 원점 임계 검사, 다대 원점 판정의 pose 보정(기존 미해결 항목과 합친다). 1b에는 `VehicleState` 생산자가 없으므로 world 좌표 판정은 스폰 pose(`stack.json`)를 독립 기준으로 쓴다. Executor가 낸 setpoint와의 거리만으로 판정하지 않는다(원점 변환 오류가 통과한다) |
| architect | 6단계 | Hold 실험 결과를 쟁점 9, `.action` 주석에 반영. 6단계 구현이 드러낸 문제의 계약 반영(1a 고정 전) |
| architect | 7단계 | `docs/interface.md`에 이 문서의 계약 문장 전부, 파일별 고정 시점 표, `TYPE_LOITER`와 `MODE_HOLD`의 구분. 5단계 PR 검토에서 더한 것: (1) 시각 표기. "sim 시각", "sim 시간"이라고 쓰지 않고 "ROS 시각(`use_sim_time`이면 `/clock`)"으로 쓴다(`TargetState`의 stamp와 소실 판정, 신선도 임계와 timer, 항목 `timeout`, Hold 확인 시간 모두). (2) 정의 작성 규칙(ros2 권고 2). string 상수와 기본값에 "#"을 넣지 않는다(rosidl 파서가 따옴표 안의 "#"도 주석으로 처리한다). 줄 끝 주석에 그 줄 앞부분과 같은 문자열을 쓰지 않는다(`ros2 interface show`가 줄을 자른다. 계약 테스트의 가드가 잡는다). 이름 상수는 C++에서 namespace 범위 static 변수의 초기화식에 쓰지 않는다(쟁점 4). (3) `VehicleState`의 소비자 조건 넷(ops): `msg.vehicle_id`와 토픽 네임스페이스 대조, replay에서 `vehicle_state`를 재생하지 않음, 발행 timer와 신선도 검사는 ROS 시각, 그래프 항목으로 등록이나 이탈을 판정하지 않음. (4) 즉시 abort되는 goal(BUSY, VEHICLE_ID_MISMATCH, INVALID_MISSION, NOT_READY)은 feedback이 0건이다. "Fleet은 feedback 수신을 수락 확인으로 쓰지 않는다"를 적는다(ops) |
| architect | bounded string이나 공백이 든 기본값을 가진 필드를 더할 때 | `test_contract.py`의 `direct_definition`이 `"=" in line`으로 상수 줄을 가른다. 그런 필드에서는 정규화가 어색해지므로 `_CONSTANT` 정규식 기준으로 바꾼다(ros2 권고 3. 지금은 그런 필드가 없다) |

## 문서 반영 목록 (5단계 PR 안에서, reviewer 재확인 뒤, architect)

상태(2026-11-10): `docs/architecture.md`, `docs/roadmap.md`, `docs-for-agent/file-ownership.md`는 반영했다. owner 검토에서 더해진 것(roadmap Phase 2 3번의 기록 순서, 5번의 인덱스 key와 결과 미상, architecture.md 테스트 절의 계약 테스트와 패키지별 단정)도 함께 넣었다. `progress.md`는 호출한 쪽이 갱신한다.

- `docs/architecture.md` 인터페이스 계약 절: "Phase 1a 완료 시점에 고정" 문장을 나눈 고정 시점으로(사용자 결정 1), "고정"의 정의, `VehicleState` 토픽과 불변식, `"world"` 프레임 정의, `TargetState`의 시각 의미, `MissionEvent`, 취소 의미, 변경 절차. 표적 생산 경로 문장("ros_gz_bridge로 받은 Gazebo pose를 변환")과 범위 문구("Gazebo 안의 임의 이동 엔티티")는 1b 해법 선택 뒤에 고친다(지금은 리스크만 적는다).
- `docs/architecture.md` 기체 식별 절: `world.origin`은 1b부터 필수, 노드는 원점과 `vehicle_id`를 params로 받는다.
- `docs/roadmap.md`
  - 16행(Phase 1a의 인터페이스 계약이 이후 Phase의 토대라는 문장)과 1a 7번의 "계약으로 고정": 1a 완료에 고정되는 범위를 사용자 결정 1대로 적는다.
  - 20행 1a 목표의 "미션 시퀀스는 아직 없다": 사용자 결정 2와 어긋나게 읽히므로 고친다(6단계 노드는 `[TAKEOFF, LOITER, LAND]` 미션 하나를 action으로 받는다. YAML 미션 시퀀스와 나머지 항목은 1b).
  - 1a 5번: 파일 목록(`MissionItem`과 서브메시지, `MissionEvent.msg`).
  - 1a 6번: 노드가 `ExecuteMission` action 서버로 `[TAKEOFF, LOITER, LAND]` 미션을 받는다(사용자 결정 2). Hold 취소 실험, `MissionEvent` 발행.
  - 1b 2번(생산 경로는 착수 때 결정), 1b 완료 기준에 `TargetState`와 GOTO, TRACK_ENTITY, RTL 고정.
  - Phase 2 1번(`vehicle_land_detected` 추가, 발행 중단 불변식), 기록 대상에 `mission_event`, Phase 2 완료 기준에 `VehicleState`와 `MissionEvent` 고정.
  - Phase 3 3번("자동 발견"의 방식은 Phase 3 토론).
  - 리스크 표: 쟁점 5의 네 줄.
- `docs/interface.md`는 7단계에서 만든다. 5단계에서는 만들지 않는다.
- `docs-for-agent/file-ownership.md`: `idsim_interfaces/test/golden/`의 갱신 승인 주체.
- `docs-for-agent/progress.md`: 결정 기록, "1b 전 결정" 항목 갱신(원점 변환의 출처와 `world.origin` 필수화는 닫고 표적 생산 방식은 새로 연다), 미해결 사항. 호출한 쪽이 갱신한다.
- `config/fleet.yaml`의 주석은 1b에서 devops-engineer가 고친다.

## 사용자 결정 (2026-11-10 확정)

1. 계약 고정 시점을 나눈다(architect 권고안 채택). 1a 완료에 공통 규칙, `ExecuteMission`, TAKEOFF, LOITER, LAND. 1b 완료에 `TargetState`, GOTO, TRACK_ENTITY, RTL. Phase 2 완료에 `VehicleState`. 귀결: "고정 시점과 범위 구분" 표가 확정됐고, sim의 공분산 제외 조건이 충족됐다.
2. 6단계 이륙/착륙 노드는 `ExecuteMission` action 서버로 `[TAKEOFF, LOITER, LAND]` 미션을 받는다(architect 권고안 채택). 귀결: "1a 완료 고정" 묶음에 소비자가 생겼고, Hold 취소 실험이 6단계로 왔으며, 6단계의 작업량이 늘었다(검증, 수락 정책, 취소, 실패 사유, `MissionEvent` 발행).

남은 사용자 결정은 없다. 새로 생길 수 있는 곳은 한 군데다. 1b 표적 생산 방식 토론에서 `docs/architecture.md`의 범위 문구를 바꿔야 하면 그때 올린다.

## 사용자에게 알릴 것 (결정은 했으나 뒤집을 수 있음)

- 취소 뒤 기체 동작을 Hold로 정했다(공중). Land나 RTL을 기본으로 원하면 바꿀 수 있고, 그때는 goal에 `on_cancel`을 두는 것이 아니라 기본 동작을 바꾸는 쪽이 간단하다. Hold로 남은 기체를 내리는 것은 취소를 요청한 쪽의 책임이다.
- 같은 성격의 정책 둘. Hold가 정해진 시간 안에 확인되지 않으면 Executor가 Land 명령을 보내고 ABORTED로 끝낸다. 지상에서 arm 상태로 취소되면 강제가 아닌 disarm 명령을 보낸다. 둘 다 6단계 Hold 실험 결과에 따라 1a 고정 전에 바뀔 수 있다.
- `MissionEvent.msg`를 더했다(기록물에 미션 id와 결과를 남기는 일반 토픽). 사용자 결정 1의 목록에 없던 항목이다. 고정 시점은 Phase 2 완료로 두었고, 이것은 사용자 결정 1의 기준(첫 소비자가 생기는 Phase의 완료. 그대로면 1a 완료)의 예외다. 이유는 필드를 정하는 소비자가 Phase 2의 기록물 인덱스이기 때문이다. 1a 완료로 당기기를 원하면 바꿀 수 있다.
- `stack.json`과 노드 params에 `vehicle_id`를 직접 싣기로 했다(6단계, devops-engineer 확인 조건).
- 결정 (b)의 1b 구절을 뒤집었다(`world.origin`은 1b부터 필수이고 유일한 출처, 커스텀 월드에서도 wrapper가 적용).
- 2026-11-06 결정 "표적 엔티티는 Gazebo Actor"는 sim의 실측 때문에 1b 착수 때 다시 토론한다. 지금은 바꾸지 않았다.
- 비용: 새 이미지나 의존 패키지는 없다(`std_msgs`, `geometry_msgs`, `action_msgs`, `ros2cli`, `ros2interface`는 ros-ws 이미지에 이미 있다). ros-ws 이미지 key는 바뀌지 않는다.

## 다음 절차

- (완료) 패키지 파일(작업 단위 A, B. architect), C(devops-engineer), owner 검토 반영, 문서 반영(D).
- reviewer가 문서 변경과 검토 반영을 확인한 뒤 PR, CI 통과, 사용자 머지.
- 6단계에서 Hold 실험과 구현이 드러낸 문제를 1a 고정 전에 이 문서의 계약 문장에 반영한다.
