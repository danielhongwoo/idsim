# 1a 4단계 idsim_common 설계 결정 (architect, 2026-11-10)

입력: ros2-engineer.md(소유자 초안), px4-engineer.md, devops-engineer.md, 그리고 충돌 지점 재질문 답 두 건(아래 "재질문 결과"). 저장소 파일은 고치지 않았다. 문서 반영은 4단계 PR 안에서 architect가 한다(쟁점 10).

## 재질문 결과 요약

- px4 Q1: N=0(빈 네임스페이스) 허용 요청 철회. C++ 소비자 없음, gen_compose는 1-9만 생성(`tools/gen_compose.py:45`).
- px4 Q2: params로 받은 sysid + vehicle_status.system_id 대조는 요구(명시 sysid, 0 금지, 오류 즉시 드러남)를 충족. 조건 두 가지: 대조로 막는 것은 VehicleCommand뿐(setpoint 스트림은 막지 않음), "미수신"과 "불일치"를 구분(미수신이면 명령만 보류, 불일치면 오류). vehicle_status는 약 2 Hz, 첫 수신 1.15-1.5 s.
- px4 Q3: 스택 6에서 부팅 시점 주입 `UXRCE_DDS_SYNCT=0` 실측. 골든 topics 65줄과 qos 일치(`normalize --check` 통과, timesync_status 토픽은 그래프에 남고 데이터만 없음), check_px4 S3 arm/disarm 왕복 2회 통과. ULog, EKF에 영향 없음(`time_offset` 참조는 uxrce_dds_client와 lib/timesync뿐). SYNCT=1의 세션 생성 시 timesync 수렴 대기와 실패 경로가 사라진다.
- ros2 Q1: ts=0 규약 철회, B안 찬성. 조건: 0 timestamp 송신 차단(use_sim_time 노드는 /clock 전 now()=0). 강타입 `Px4Timestamp`를 `from_ros(rclcpp::Time)`로만 만들고 RCL_ROS_TIME이며 0보다 클 때만 성공. (reviewer 지적으로 시계 기반 생성으로 바뀜, 쟁점 4)
- ros2 Q2: 65개 전부를 목록 하나에 두는 것이 가능하고 비용이 없음. struct 헤더 58종 include는 13종 대비 약 40 ms(실비용은 템플릿 인스턴스화). io 템플릿에 `is_message` static_assert로 full 헤더 누락을 막음. 위험한 /fmu/in은 `Publish::{Allowed, Restricted}` 필드로 막는 안.
- px4 Q4: 거꾸로 ros2 원안(13개 기술자 + 테스트 X-macro)을 지지. 근거는 위험한 /fmu/in 토픽을 공개 API로 노출하지 않기. 공개 /fmu/in 허용 목록과 차단 목록 제출.
- ros2 Q3: 방향 정적 검사의 음성 컴파일 테스트 방식 실증(EXCLUDE_FROM_ALL OBJECT 타깃 + cmake -P 스크립트가 빌드 실패와 기대 문구를 함께 판정). 양성은 함수 템플릿 주소 취하기로 본문 인스턴스화.
- ros2 Q4: `qos_check_compatible`은 노드 없이 동작. liveliness가 system_default면 Warning이라 `Automatic`을 명시하면 Ok.
- ros2 Q5: devops 안(개별 test_depend) 수용. cpplint와 ament clang-format 충돌은 include 순서 하나이며 ROS 헤더를 따옴표로 쓰면 해소. cpplint의 `legal/copyright`는 따로 꺼야 한다.

---

## 쟁점 1. 좌표 변환

결정: px4_ros_com frame_transforms를 래핑하지 않고 idsim_common이 직접 구현한다. px4_ros_com은 `test_depend`의 차등 비교 기준(oracle)으로만 쓴다.

근거
- 로드맵의 "안 맞으면 직접 구현" 조건이 성립한다. 공분산 3x3 변환 두 개가 틀리고(C R, 음의 분산), 공개 템플릿 3개가 링크되지 않으며, NED yaw 스칼라 변환이 없고, 동체 변환이 NaN을 다른 축으로 번진다(TrajectorySetpoint는 NaN을 "제어 안 함"으로 쓴다).
- 벡터와 쿼터니언 정적 변환은 맞으므로 oracle로 쓸 가치가 있다. 라이브러리는 px4_msgs에 의존하지 않아 "v1.17.0 호환"은 관례 문제이고, 관례(q 순서 w,x,y,z, FRD->NED)는 px4가 메시지 정의로 확인했다.
- 직접 구현 범위가 작다(축 치환과 부호, 쿼터니언 정적 곱 두 번, yaw).

구현 지시
- ros2-engineer: `frames.hpp/.cpp`. NED<->ENU 벡터, FRD<->FLU 벡터(축 치환과 부호만, NaN 보존), `q_enu_flu = Q_NED_ENU * q_ned_frd * Q_FRD_FLU`와 역변환, yaw `wrap_pi(pi/2 - yaw)`, 대각 분산 치환, px4_msgs `std::array<float,3>`, `std::array<float,4>` 어댑터. 전체 공분산 회전은 소비자가 없어 뺀다. 테스트: px4_ros_com 결과와 벡터, 쿼터니언 차등 비교(q와 -q 동치), NaN 보존, yaw 왕복과 감기, 알려진 값(북쪽 yaw 0 -> ENU pi/2).
- 원점 이동(월드 ENU -> 기체 로컬 NED)은 4단계에서 다루지 않는다. 1b에서 축 변환 API를 바꾸지 않고 원점을 받는 별도 함수로 추가한다. 따라서 지금 "원점 자리"를 시그니처에 넣지 않는다(px4 지적 9에 대한 답).

## 쟁점 2. 토픽 매핑 API

결정: 기술자 목록 하나(`IDSIM_PX4_TOPIC(Name, MsgType, Direction, "logical_name", Publish)`)에 골든 65개 전부를 둔다. 키는 (방향, 논리 이름)이고 타입은 기술자에 묶인다. /fmu/in 기술자는 기본 `Restricted`이며 1a 허용은 `offboard_control_mode`, `trajectory_setpoint`, `vehicle_command` 셋뿐이다. Restricted 기술자는 공개 API(`topic_name`, `create_publisher`)로 쓸 수 없고 `detail`과 테스트만 접근한다. 문자열 함수 `px4_topic<T>(ns, dir, base)`는 공개하지 않는다. 공개 API는 목록에 등록된 기술자만 받는다(`detail::is_registered<T>`는 X-macro 목록 안에서만 특수화, `create_publisher`, `create_subscription`, `topic_name` 모두 `static_assert(is_registered_v<Topic>)`). 목록 끝에서 `IDSIM_PX4_TOPIC`을 `#undef`한다.

성격 명시: 이 차단은 실수 방지 수준이며 보안 경계가 아니다. C++에서 의도적인 우회(같은 모양의 타입을 직접 만들고 rclcpp를 직접 부르기, 문자열 직접 작성)는 막을 수 없고 lint와 코드 리뷰로만 잡는다(reviewer가 스크래치 `rv/bypass.cpp`로 매크로 재사용 우회를 실증. `is_registered`와 `#undef`로 그 경로는 닫히지만 다른 경로는 남는다). interface.md에도 같은 문구를 적는다.

허용 목록 해제 절차(Restricted -> Allowed): (1) 기술자의 `Publish`를 Allowed로 변경, (2) px4-engineer 접점 승인, (3) progress.md 결정 기록, (4) "허용 목록 == {offboard_control_mode, trajectory_setpoint, vehicle_command}"를 명시 비교하는 단위 테스트의 기대 집합 갱신, (5) interface.md 공개 /fmu/in 목록 갱신. 다섯 가지가 한 PR에 함께 있어야 한다.

근거(충돌 정리)
- ros2와 px4는 재질문 뒤 서로 반대쪽으로 넘어갔다. 두 사람의 실제 요구는 (1) 목록이 하나일 것(ros2), (2) 위험한 /fmu/in이 공개 API로 노출되지 않을 것(px4), (3) 태그를 올릴 때 diff가 드러날 것(둘 다)이다. 65개 기술자 + Restricted는 셋을 모두 만족한다. 13개 + 테스트 X-macro는 타입 목록이 두 곳(라이브러리, 테스트)에 생겨 (1)을 깨고, 토픽 삭제는 기술자가 없으면 단위 테스트로 안 잡힌다.
- 컴파일 비용은 실측상 무시할 수준(struct 헤더 58종이 13종보다 약 40 ms). 기술자 헤더는 `detail/<snake>__struct.hpp`만 include하고, 소비자는 자기가 쓰는 타입의 full 헤더를 include한다. 빠뜨리면 io 템플릿의 `is_message` static_assert가 막는다.
- 골든 비교의 타입 문자열은 65개 전부 `rosidl_generator_traits::name<Msg>()`로 만든다(매크로 `#MSG` 문자열화는 쓰지 않는다). 생성 코드가 실제로 광고하는 이름과 비교해야 하기 때문이다. 이 때문에 골든 테스트 TU만 65개 타입의 traits 헤더를 include한다(소비자 TU 비용과 무관).
- (방향, 논리 이름)->타입 표는 사람이 쓰지만, 금지된 것은 태그별 접미사 표다. 접미사는 여전히 `MESSAGE_VERSION`에서 컴파일 시점에 파생된다(2026-11-06 결정의 취지 유지). 타입 -> 이름 역조회 API는 두지 않는다(같은 타입 여러 토픽).
- `timesync_status`는 쟁점 4의 B안에서도 골든에 남으므로 기술자는 두고, interface.md에 "SYNCT=0에서 DDS timesync 데이터 없음(MAVLink timesync 상대가 있으면 다른 source_protocol의 데이터가 올 수 있음, 추정)"을 적는다. 1a 소비자 목록에서는 뺀다.

구현 지시
- ros2-engineer
  - `px4_topics.hpp`(기술자 65개, `Direction{In, Out}`, `Publish{Allowed, Restricted}`, `detail::msg_version`(없으면 0, `std::void_t`), `detail::topic_name`, `detail::is_registered<T>`(목록 안에서만 특수화), `static_assert(!has_version_suffix(name))`, 목록 끝 `#undef IDSIM_PX4_TOPIC`), `px4_io.hpp`(`create_subscription<Topic>`은 Out만, `create_publisher<Topic>`은 In이면서 Allowed만, 세 공개 함수 모두 `is_registered_v` static_assert, 각각 다른 static_assert 문구, `is_message` static_assert, QoS 고정, `NodeT` 템플릿으로 Node와 LifecycleNode).
  - 허용 목록 명시 비교 테스트: Allowed 기술자 집합 == {offboard_control_mode, trajectory_setpoint, vehicle_command}.
  - 공개 /fmu/in 허용 목록은 px4 제출 목록을 따른다. 차단 목록 전체를 기술자 주석에 분류(외부 모드 프로토콜, 제어기 우회, 추정기 주입, 수동 입력, 상태 위장, 기체 형식 불일치)와 함께 적는다. Allowed로 바꾸려면 px4-engineer 승인이 필요하다는 주석을 둔다. `goto_setpoint`는 1b에서 검토.
  - 골든 테스트: 기술자 목록 전체의 (상대 이름, `rosidl_generator_traits::name<Msg>()`) 집합 == `topics.txt` 집합(양방향, 차이는 양쪽 목록과 접미사 뗀 후보를 실패 메시지에). 더미 타입(상수 없음, 0, 3)으로 `msg_version` 검사.
  - 방향과 허용의 증명: trait 전수 검사(`is_publishable_v` 등) + 음성 컴파일 테스트 네 개(Out에 publish: vehicle_status, Restricted에 publish: actuator_motors로 고정, full 헤더 누락, 미등록 기술자(목록 밖에서 만든 같은 모양 struct)로 create_publisher), 재질문 Q3 방식(EXCLUDE_FROM_ALL OBJECT 타깃, `cmake -P` 스크립트가 빌드 실패와 기대 문구를 함께 판정, `RESOURCE_LOCK`). WILL_FAIL과 try_compile은 쓰지 않는다. 양성은 함수 템플릿 주소 취하기.
- devops-engineer: lint.sh에 검사 추가. `ros_ws/src` 아래에서 `idsim_common` 밖의 C++ 파일과 `.py` 파일에 (1) `fmu/in/` 또는 `fmu/out/` 문자열, (2) `detail::topic_name`, (3) `idsim_common::px4::detail` 문자열이 있으면 실패. Python 판정 코드 `tests/`는 대상 아님.

## 쟁점 3. QoS

결정: `px4_out_qos()`(구독)와 `px4_in_qos()`(발행) 모두 BEST_EFFORT, VOLATILE, KEEP_LAST, depth 5, liveliness `Automatic` 명시. 골든 qos의 history와 depth는 계약에서 뺀다. 계약은 reliability와 durability다.

근거
- PX4 writer는 BE/TL, reader는 BE/VOL(소스와 실측). BE reader와 VOL reader는 상대가 무엇이든 호환된다. 늦게 붙은 TL reader에게 에이전트가 이력을 주지 않음을 실측했으므로 TL 구독의 이득이 없다.
- 골든 depth=1은 rmw의 원격 엔드포인트 표시값이지 소스 값(writer 0, reader 큐 x 2)이 아니다.
- `qos_check_compatible`은 liveliness system_default에서 Warning을 내므로 Automatic을 명시한다(DDS 기본값과 같아 전송 동작은 그대로). 값은 테스트의 `qos_profile_sensor_data`와 reliability, durability, depth가 같다.

구현 지시
- ros2-engineer: `qos.hpp` 두 함수. 테스트: 골든 27개 writer(파일의 reliability, durability만 반영) 대 `px4_out_qos()`가 모두 Ok, `px4_in_qos()` 대 PX4 reader(BE, VOL)가 Ok, 음성 대조 두 개(RELIABLE reader, TL reader 대 VOL writer가 Error). 노드 없음.
- test-engineer: S4 골든 형식과 `--check`는 바꾸지 않는다(depth는 기록하되 idsim_common 테스트와 interface.md 계약에서 쓰지 않음). 변경 없음.

## 쟁점 4. timestamp

결정: 4단계에서 정한다. B안. SITL 공통 파라미터에 `UXRCE_DDS_SYNCT=0`. /fmu/out timestamp는 PX4 hrt = Gazebo sim 시간(us)이고, /fmu/in timestamp는 노드 시계(sim 시간)를 us로 넣는다. 0과 벽시계 값은 보내지 않는다. 빌더(그리고 6단계의 setpoint 헬퍼)는 강타입 `Px4Timestamp`를 인자로 받는다. `Px4Timestamp`는 시계를 받는 생성 함수 `Px4Timestamp::now(rclcpp::Clock & clock)` 하나로만 만든다(노드가 아니라 시계를 받는다). `clock.get_clock_type() == RCL_ROS_TIME`이고 `clock.ros_time_is_active()`가 참이며 값이 0보다 클 때만 성공하고, 그 외에는 실패(값 없음)를 돌려준다. `rclcpp::Time` 값을 받는 생성 경로는 두지 않는다.

인터페이스를 시계로 정한 이유: reviewer 실측에서 use_sim_time=false 노드 시계도 clock_type이 RCL_ROS_TIME이고 값은 epoch 벽시계라 `rclcpp::Time` 값만으로는 sim 시간인지 구분할 수 없다. 구분 정보(`ros_time_is_active`)는 시계에만 있다. 노드 대신 시계를 받으면 Node와 LifecycleNode 모두 `*node.get_clock()`으로 쓰고, 단위 테스트가 노드 없이 `rclcpp::Clock(RCL_ROS_TIME)`과 rcl의 ROS 시간 override로 활성/비활성을 만들 수 있다.

근거
- use_sim_time은 이미 모든 노드에 결정되어 있다. 이 조건에서 묵은 setpoint를 PX4가 판정하는 조합은 SYNCT=0 + sim 시간뿐이다(px4 실측: SYNCT=1에서는 sim 값이 언더플로 클램프로 "지금"이 되고, ts=0은 수신 시각이라 둘 다 못 잡는다).
- PX4 timestamp, `/clock`, rosbag 기록 시각(`--use-sim-time`), ULog가 한 축에 놓인다. "시간의 정식 기준은 /clock" 원칙과 맞고 Phase 2 ULog 정렬 오프셋이 시뮬레이션에서 0이 된다.
- 회귀 실측(스택 6, 부팅 시점 주입): 골든 topics와 qos 불변, S3 arm/disarm 2회 통과, 세션 생성 시 timesync 대기와 실패 경로 제거. 단 S3는 sim 시간 timestamp 경로를 지나지 않았다(check_px4.py 노드는 벽시계이고 Commander에는 cmd.timestamp 신선도 검사가 없다). sim 시간 경로의 실증은 px4의 probe2 실측(sim-2s를 손실로 판정)뿐이며 6단계 통합 테스트로 회귀 판정을 고정한다.
- 다른 모듈 영향 없음의 근거는 구조적이다. `time_offset`은 uxrce 세션 구조체의 필드라 다른 모듈이 접근할 경로가 없고(ULog와 EKF는 uORB hrt 시각만 쓴다), DDS 쪽 timesync_status 발행은 `Timesync::update()` 안에만 있는데 SYNCT=0이면 `on_time_no_sync` 경로라 update가 불리지 않으며, 그 토픽을 구독하는 idsim 소비자가 없다.
- 6단계로 미루면 6단계 노드가 두 정책을 다 염두에 두고 짜야 한다.
- 0과 벽시계 차단: use_sim_time 노드는 /clock 전 now()=0이고, 0을 보내면 PX4가 수신 시각으로 채운다. use_sim_time이 꺼진 노드의 벽시계 값은 SYNCT=0 PX4에서 min 클램프로 "지금"이 된다. 둘 다 묵은 setpoint 판정을 조용히 끈다.
- 실기체로 가면 SYNCT를 되돌리고 timesync가 다시 필요하다. 이것은 SITL 파라미터 한 줄이며 운용 노드는 모른다(레이어 경계 유지).

구현 지시
- px4-engineer: 같은 PR에서 `config/px4/sitl_params.env`에 `UXRCE_DDS_SYNCT=0`과 근거 주석. 적용 판정은 로그 grep이 아니라 `tests/smoke/check_px4_pxh.py` 38행 `DEFAULT_EXPECT`에 `UXRCE_DDS_SYNCT=0`을 더해 `param show` 저장값으로 한다(2026-11-06 결정: 잘못된 이름은 param set이 오류만 찍고 넘어간다). 스택 6에서 S2-S5 회귀(S4 `--check` 일치 포함)를 돌리고 run id를 PR에 적는다. 스모크 판정 중 out timestamp를 벽시계로 가정한 곳이 없는지 확인(`check_px4.py`의 timestamp_rises는 통과 확인됨).
- ros2-engineer: `Px4Timestamp`(`now(rclcpp::Clock &)`만 공개 생성 경로, RCL_ROS_TIME이고 `ros_time_is_active()` 참이고 값 > 0일 때만 성공, ns/1000). 빌더가 이 타입만 받는다(6단계 setpoint 헬퍼도 같은 타입). 테스트(노드 없음): use_sim_time 없는 시계(ROS 시간 비활성, 벽시계 값) 거부, RCL_SYSTEM_TIME과 RCL_STEADY_TIME 시계 거부, ROS 시간 활성이지만 값 0(/clock 전) 거부, 활성이고 값이 있을 때 us 변환. `tests/smoke/capture.sh` 35행 `DEFAULT_HZ_BASES`에서 timesync_status를 뺀다(데이터가 없어 hz가 비게 됨, 소유자 ros2).
- test-engineer: 6단계 판정에서 PX4 메시지 timestamp를 `/clock`과 비교하는 일이 생기면 같은 축(us)임을 전제로 해도 된다. 다만 판정 기준 시각은 여전히 ROS 시각(`/clock`). `tests/support` 변경 없음.
- logging-engineer(알림만): SITL에서 ULog와 /fmu/out timestamp가 같은 축이라는 사실을 Phase 2 정렬 설계의 전제로 삼는다.
- 6단계로 넘김: activate에서 `/clock` 첫 수신 확인(Px4Timestamp 생성 실패를 activate 실패로), 통합 테스트에 "sim 시간 timestamp를 COM_OF_LOSS_T보다 묵게 보내면 failsafe(offboard_control_signal_lost)" 판정 추가(test-engineer와 px4-engineer). 이것이 B안 sim 시간 경로의 회귀 판정이다.

## 쟁점 5. 식별

결정: idsim_common에 N+1 공식을 두지 않는다. 노드는 stack.json에서 생성된 params로 ns와 sysid를 받고, `vehicle_status.system_id`, `component_id`와 대조한다. 빈 네임스페이스와 "/"는 거부한다(N=0 미지원). target_system 0은 API로 만들 수 없다. 4단계는 타입과 검증 함수만 만든다.

근거
- 단일 출처는 stack.json이고 노드는 생성된 params만 받는다(결정 (a)). 공식을 코드에 두면 두 번째 사본이 되고 실기체 교체 때 깨진다.
- PX4는 틀린 target_system을 ack 없이 조용히 무시한다(실측). vehicle_status.system_id가 PX4의 실제 값이라 가장 강한 대조 기준이다. params만 믿으면 오설정을, 학습만 하면 ns 오지정을 못 잡으므로 둘 다 쓴다.
- N=0은 architecture.md와 2026-11-06 결정이 금지하고, px4가 요청을 철회했다.
- 노드 네임스페이스에 기대는 안은 Phase 3(한 노드가 여러 기체 구독)에서 깨지므로 기각.

구현 지시
- ros2-engineer: `vehicle.hpp/.cpp`. `VehicleNamespace::parse(std::string)`(절대 경로, 끝 빗금 없음, 비어 있지 않고 "/"가 아님, `rmw_validate_namespace` 통과. `/px4_N` 형태나 N은 해석하지 않는다), `SystemId`(1-255 강타입, 0 불가), `VehicleIdentity{ns, sysid}`, `verify(identity, VehicleStatus) -> {Match, SystemIdMismatch, ComponentIdMismatch}`. "미수신"은 호출자가 아직 status가 없는 상태로 표현한다. 테스트는 순수 함수만.
- 6단계로 넘김: params 키 이름(`vehicle.ns`, `vehicle.sysid` 제안)과 생성기 출력(devops), 선언 헬퍼 `declare_vehicle_identity(node)`, 게이트 정책(px4 조건: VehicleCommand만 막고 setpoint 스트림은 막지 않음, 미수신이면 명령 보류, 불일치면 오류로 activate 실패 또는 ERROR 전이). 게이트는 idsim_mission에 둔다.
- 생성기 책임(기록만): ns와 sysid가 같이 다른 기체를 가리키는 오류는 대조로 못 잡으므로 stack.json 생성기 단위 테스트가 막는다(이미 파생 규칙 단일화로 막혀 있음).

## 쟁점 6. VehicleCommand 빌더 경계

결정: 빌더는 `VehicleIdentity`와 `CommandSource{system 1-255, component 1-999}`가 없으면 만들 수 없다. 고정 필드는 `target_component=1`, `from_external=true`, `confirmation=0`, timestamp는 `Px4Timestamp` 인자. 메서드는 `arm`, `disarm`, `set_mode_offboard`(176, param1=1, param2=6), `set_mode_hold`(176, 1, 4, 3), `land`(21, param4-7 NaN), `rtl`(20). "ACCEPTED = 성공" 헬퍼는 두지 않고, ack 매칭 술어 `is_ack_for(ack, cmd)`(command, target_system == cmd.source_system, target_component == cmd.source_component)만 둔다.

근거
- DO_SET_MODE는 base_mode 누락이나 시동 전 Offboard에서도 ACCEPTED라 ack만으로 성공을 말할 수 없다(px4 소스와 실측 E4). 모드 성공은 nav_state 확인까지이며 그 상태기는 idsim_mission에 둔다.
- `from_external=false`면 MAVLink로 재송출되고(소스), `source_component >= 1000`은 ModeExecutor로 분류된다.
- 강제 시동(21196)과 takeoff(param7 NaN 함정)는 1a 범위 밖.

구현 지시
- ros2-engineer: `vehicle_command.hpp/.cpp`와 테스트(각 메서드의 필드 표 대조, component 1000 거부, sysid 0 불가가 타입으로 막힘, `is_ack_for`). `raw(command, params)`는 두지 않는다(검증 없는 탈출구. 필요가 생기면 px4 승인 뒤 추가).
- px4-engineer: 빌더 필드 표 리뷰(접점 승인).
- 6단계로 넘김: source_system/component 값 표(역할별). 표는 미션 노드뿐 아니라 테스트 하네스(`tests/support`, `check_px4.py`)의 source까지 정해, 같은 기체에 명령을 보내는 주체끼리 ack가 섞이지 않게 한다(지금 check_px4.py는 254/1). DO_SET_MODE와 SET_NAV_STATE 최종 선택 확인(현재 DO_SET_MODE), 시동 상태 Offboard 거부 실측.
- 1b로 넘김: takeoff 빌더.

## 쟁점 7. 패키지

결정: ament_cmake, SHARED 라이브러리 `idsim_common::idsim_common` + 템플릿 헤더, C++17(ROS 패키지 공통, Phase 3 gRPC 때 재검토 가능), `-Wall -Wextra -Wpedantic -Werror`는 패키지 CMakeLists에. 의존 rclcpp, rclcpp_lifecycle, px4_msgs, Eigen3(eigen3_cmake_module). px4_ros_com은 test_depend. ament_lint는 `ament_lint_common`을 쓰지 않고 `ament_cmake_xmllint`, `ament_cmake_lint_cmake`, `ament_cmake_cpplint`만 test_depend. cpplint는 `AMENT_LINT_AUTO_EXCLUDE` 뒤 `ament_cpplint(FILTERS "-legal/copyright")`로 직접 부른다. uncrustify, copyright, cppcheck는 쓰지 않는다. `.clang-format`은 ament_clang_format 설정 원문을 저장소 루트에. 비시스템 헤더는 따옴표 include.

근거
- 검증 코드와 빌더를 헤더에 두면 컴포넌트마다 중복된다. Jazzy 기준이 C++17이고 필요한 기능이 다 있다.
- common 묶음은 cppcheck가 slow version으로 스스로 건너뛰어 가짜 녹색이 되고, Python 파일이 생기면 flake8, pep257이 예고 없이 켜진다. uncrustify는 clang-format과 충돌.
- 저작권 머리말 검사는 라이선스 결정과 묶여 있어 사용자 결정 전까지 끈다(아래 사용자 결정 필요).
- 단위 테스트는 노드와 DDS 참가자를 만들지 않는다(네트워크 없는 unit 잡, CYCLONEDDS_URI 문제 회피).

구현 지시
- ros2-engineer: 패키지 골격, `.clang-format`, `.clang-tidy`(검사 목록, 헤더 필터는 저장소 패키지 경로), 위 lint 설정. clang-tidy는 `src/`와 `include/`만, `test/`는 처음에는 대상에서 뺀다.

## 쟁점 8. CI

결정: devops 안을 채택한다. 새 `unit.yml`(ros-ws 이미지에서 `tools/ros_ws.sh ci`: colcon build, `colcon test --return-code-on-test-failure`, test-result 출력, 테스트 수 > 0 단정, clang-tidy). ament_lint는 colcon test 안에서. clang-format은 lint 잡(`LINT_PYTHON_IMAGE` + pip `clang-format==18.1.3`, `--style=file:<저장소>/.clang-format`). lint.sh와 lint.yml에서 clang-tidy, ament-lint 항목을 지운다(가짜 PASS 항목을 두지 않는다). ros-ws에 apt `clang-tidy-18`, `clang-format-18` 추가. versions.env에 `LLVM_MAJOR=18`, `LINT_CLANG_FORMAT_VERSION=18.1.3`. unit 잡의 트리거와 concurrency는 지금 lint.yml과 똑같이 둔다(이중 실행 정리는 lint와 함께 별도 항목으로 유지).

근거
- clang-tidy는 compile_commands.json과 ros-ws 헤더가 있어야 하므로 ros-ws 안에서만 돈다. 4단계 완료 조건(GoogleTest)이 CI에서 돌아야 "PR로 검증" 규칙이 의미가 있다. 패키지가 하나일 때 잡을 만드는 것이 가장 싸다.
- `colcon test-result`는 빌드 실패 시 "0 tests"로 0을 반환한다(E7). 테스트 수 단정이 필요하다.
- 이미지 키 변경 비용: ros-ws 재빌드 1회(CI 콜드 기준 444초 + 설치분)와 GHCR 용량 약 297MB 증가, 개발자 로컬 재빌드 1회. 미러 변경 PR이 먼저 머지되어 그쪽도 ros-ws 키를 바꾸면 재빌드가 두 번 생기지만, 두 변경을 섞지 않는 편이 실패 원인 분리에 낫다. 공개 저장소의 무료 러너와 공개 패키지 안이라 금전 비용은 없다고 판단한다(사용자 알림 항목에 남김).
- unit 트리거를 lint와 다르게 바꾸면 architecture.md의 "모든 push" 문구와 lint 이중 실행 정리가 이 PR로 끌려 들어온다. 범위를 좁힌다.

구현 지시
- devops-engineer: `.github/workflows/unit.yml`(신규, timeout 30분, 실패 시 `ros_ws/log/`, `build/*/test_results/` 아티팩트 7일, 단계별 초를 GITHUB_STEP_SUMMARY에), `tools/ros_ws.sh`(build, test, tidy, ci, clean, shell. `--user` 호스트 uid:gid, `HOME=/tmp/idsim-home`, `CYCLONEDDS_URI=` 비움, `--network none`, `ROS_DOMAIN_ID=99`, 실행 전 이미지 `IDSIM_BUILD_*`와 versions.env 대조), `tools/ci/lint.sh`와 `lint.yml` 수정, `docker/Dockerfile.ros-ws`(LLVM 설치, `IDSIM_BUILD_LLVM_MAJOR` ENV, 37-38행 주석 정정), `versions.env`, `docker-bake.hcl`, 쟁점 2의 fmu 문자열 검사. 미러 변경 PR 머지 뒤 그 위에 rebase한다. 첫 실행과 머지 뒤 3회의 단계별 시간을 progress.md에 기록.
- test-engineer: 종료 코드 규칙(`--return-code-on-test-failure` + 테스트 수 > 0)과 unit 층에 재시도 없음 검토 승인. 아티팩트 범위 승인.
- 넘김: ccache와 actions/cache(build 단계가 3분을 넘을 때), 노드 이미지 굽기(`ros-app` 타깃, 저장소 없는 실행 요구가 생길 때), `stack.sh up`의 install 부재 검사(6단계), lint와 unit의 push/pull_request 이중 실행 정리(기존 미해결 항목).

## 쟁점 9. 골든 경로

결정: CMake가 `BUILD_TESTING`일 때만 `${IDSIM_REPO_ROOT}/docker/versions.env`(기본 `${CMAKE_CURRENT_SOURCE_DIR}/../../..`, `-DIDSIM_REPO_ROOT=`로 덮어쓰기)에서 `PX4_TAG`와 `PX4_MSGS_REF`를 읽고(줄이 없거나 둘 이상이면 FATAL_ERROR), 디렉터리가 없으면 configure FATAL_ERROR, `ament_add_gtest(... ENV IDSIM_PX4_FIXTURE_DIR=<경로> IDSIM_PX4_MSGS_REF=<값>)`로 넘긴다. 테스트도 다시 ASSERT(변수 없음, 디렉터리 없음, topics.txt 0줄이면 FAIL). 환경 변수 이름은 smoke-test 문서의 `IDSIM_PX4_FIXTURE_DIR`를 유지한다. `env.txt`의 PX4_MSGS_REF, versions.env의 값, 이미지 ENV `IDSIM_BUILD_PX4_MSGS_REF` 셋이 같은지 단정하는 테스트를 넣는다(이미지 ENV가 없으면 FAIL).

근거
- 태그를 CMake에 문자열로 쓰지 않는다(버전 단일 출처). Python `tests/support/golden.py`의 `golden_dir()`와 같은 규칙.
- 컴파일된 px4_msgs는 이미지의 것이므로 이미지 ENV까지 대조해야 "매핑이 파생된 px4_msgs"와 "비교 대상 골든"이 같은 조합임이 보장된다. S0 대조는 스모크에서만 돈다.
- 이름은 이미 설계 문서에 있는 것을 쓴다(문서 변경 최소화).

구현 지시
- ros2-engineer: CMake 블록과 테스트. 이미지 ENV 대조 테스트의 실패 메시지에 "ros-ws 이미지 안에서 tools/ros_ws.sh test로 실행하라"와 세 값을 적는다(호스트나 다른 이미지에서 돌려 ENV가 없는 경우의 안내).
- test-engineer: 골든 경로 규칙이 Python과 CMake 두 곳에 있다는 접점을 `docs-for-agent/file-ownership.md`에 적는다(규칙을 바꾸면 둘 다 고친다).
- 넘김(6단계, test-engineer): Python 쪽 토픽 이름 규칙(rclpy `MESSAGE_VERSION` 쌍둥이를 tests/support에 둘지, 정규식 유지할지).

## 쟁점 10. 문서 (architect, 4단계 PR 안에서)

- `docs/roadmap.md` 1a 4번: "키는 논리 이름과 타입의 쌍" -> "키는 방향과 논리 이름, 타입은 기술자에 묶고 접미사는 `MESSAGE_VERSION`에서 파생". "frame_transforms 래핑 ... 안 맞으면 직접 구현" -> "직접 구현, px4_ros_com은 단위 테스트 비교 기준". 위험한 /fmu/in 발행 차단(실수 방지 수준)을 한 줄 추가.
- `docs/roadmap.md` 68행(Phase 3 2번) "`target_system` 매핑은 `idsim_common`이 이미 처리한다" -> "기체별 params(stack.json에서 생성)로 sysid를 받고 `idsim_common`의 대조 함수로 확인한다"(결정 5).
- `docs/architecture.md` 109행 "매핑의 키는 논리 이름과 px4_msgs 타입의 쌍" -> 방향과 논리 이름 키, 타입은 기술자에 묶음, 허용 목록(결정 2).
- `docs/architecture.md` 141행 "네임스페이스와 `target_system` 매핑은 `idsim_common`이 유일한 접근 경로" -> "네임스페이스 검증과 sysid 대조는 `idsim_common`이 유일한 접근 경로이고, 값은 params로 받는다"(결정 5).
- `docs/architecture.md` 188행 "`frame_transforms`의 v1.17.0 호환은 idsim_common 빌드에서 확인" -> 결론(직접 구현, px4_ros_com은 테스트 비교 기준)으로 교체(결정 1).
- `docs/architecture.md`
  - 인터페이스 계약 절: PX4 메시지 timestamp는 SITL에서 `UXRCE_DDS_SYNCT=0`으로 sim 시간(us)이며 `/clock`과 같은 축이라는 사실, 판정 기준은 여전히 ROS 시각. "ULog와의 정렬에만" 문장을 이에 맞게.
  - 기체 식별 절: 노드는 sysid를 params로 받고 vehicle_status.system_id와 대조하며 공식을 재계산하지 않는다.
  - CI 파이프라인 문단: (1) lint는 clang-format, ruff, cargo fmt와 clippy, 문자 집합 등. clang-tidy와 ament_lint는 (3) unit으로.
  - 기술 스택에 C++17.
- `docs/smoke-test-phase1a.md` 골든 파일 단위 테스트 절: `px4_topic<T>(ns, dir, base)` 문구를 기술자 목록과 집합 일치 검사로, 이미지 ENV 대조 추가. 가정 절의 frame_transforms 문장을 결론으로 교체.
- `docs/interface.md`(7단계로 넘김): QoS 표(reliability, durability 계약, depth 비계약), 좌표계, timestamp 기준(SYNCT=0, Px4Timestamp 규칙, timesync_status는 DDS timesync 데이터 없음), sysid 대조 규칙, 공개 /fmu/in 목록과 해제 절차, "발행 차단은 실수 방지 수준이며 보안 경계가 아님".
- `docs-for-agent/progress.md` 결정 기록: 이 문서의 결정을 2026-11-10 항목으로, 2026-11-06 "키는 논리 이름과 타입의 쌍" 결정의 갱신을 명시. 미해결의 "frame_transforms 호환" 항목은 닫는다.

---

## 4단계 범위에서 뺄 것과 넘길 곳

- 6단계: params 키 이름과 생성기, `declare_vehicle_identity`, 식별 게이트 정책, source 값 표(테스트 하네스 포함), setpoint 헬퍼(Px4Timestamp 사용), `/clock` 첫 수신 확인, sim 시간 timestamp 묵음 failsafe 통합 판정, 시동 상태 Offboard 거부 실측, Python 토픽 이름 규칙, `stack.sh up`의 install 부재 검사.
- 7단계: interface.md 전체.
- 1b: 원점 이동 변환 함수, takeoff 빌더, `goto_setpoint` 공개 검토, TargetState -> setpoint 변환 위치.
- Phase 2(logging-engineer): ULog와 /fmu/out 같은 축 전제의 정렬 설계.
- 열린 항목 유지: lint/unit 이중 실행 정리, ccache, 노드 이미지 굽기.

## 사용자 결정 필요

- 저장소 라이선스와 소스 파일 저작권 머리말 정책. 결정 전까지 `ament_copyright`와 cpplint `legal/copyright`를 끈다. 결정되면 LICENSE 추가와 두 검사를 켜는 작업이 따른다. progress.md 미해결 사항에 올린다.

## 사용자에게 알릴 것(결정은 했으나 뒤집을 수 있음)

- ros-ws 이미지가 clang-tidy, clang-format 18 때문에 약 297MB 커지고(1.57GB -> 약 1.87GB) 이 PR에서 ros-ws 재빌드가 한 번 생긴다(미러 PR과 합쳐 두 번). 공개 저장소의 무료 러너와 공개 GHCR 안이라 금전 비용은 없다고 보고 진행한다. 이미지 크기를 줄여야 한다면 clang-tidy를 별도 도구 이미지로 빼는 안이 있다.

## 다음 절차

- reviewer 검증(2026-11-10): "조건부 진행 가능". 필수 조건 4건(Px4Timestamp 시계 기반 생성, 미등록 기술자 차단과 #undef와 lint 확장과 해제 절차, 충돌 문서 4줄, SYNCT 판정을 param show로)과 권고 5건을 이 문서에 반영했다. 이 문서 그대로 progress.md 결정 기록에 옮긴다.
- 구현 순서: devops(ros-ws 이미지, versions.env, ros_ws.sh)와 ros2(패키지)를 병렬, px4(SYNCT) 같은 PR, 접점 승인 px4(빌더 표, 공개 목록), devops(CMake 골든 블록과 ros_ws.sh), test(종료 코드 규칙), 문서는 architect.
