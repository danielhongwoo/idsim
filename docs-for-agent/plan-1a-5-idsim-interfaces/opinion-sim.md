# 1a 5단계 idsim_interfaces 설계 토론: sim-engineer 의견

작성 2026-11-10, sim-engineer. 관점: `TargetState`의 생산자(1b 표적 어댑터). 저장소의 다른 파일은 고치지 않았다.

근거 출처 표기
- [실측]: `idsim/sim-base:local`(gz-harmonic 1.0.0, libgz-sim8 8.15.0)을 `--network none` 단독 컨테이너로 띄워 확인. 스택은 올리지 않았다. 실험 월드는 scratchpad의 임시 파일이며 저장소에 없다. 내용은 아래 0절에 요약했다.
- [문서]: `docs/architecture.md` 인터페이스 계약 절과 표적 경로 원칙, `docs/roadmap.md` 1b, `docs-for-agent/progress.md` 1b 전 결정, `config/fleet.yaml`.
- [추정]: 실측이나 소스 확인 없이 경험으로 적은 것. 해당 문장에 표시했다.

---

## 0. 먼저 알릴 실측 결과: 스크립트 궤적 Actor의 pose가 서버 토픽에 나오지 않는다

계약 필드와는 별개지만 "Gazebo pose -> 어댑터 -> TargetState" 경로의 전제를 흔들어서 먼저 적는다. 계약 결정은 이 문제와 독립적으로 할 수 있고, 아래 권고는 어느 해법을 택해도 그대로 유효하다.

실험: 원점(서울시청)과 ENU를 지정한 최소 월드에 `<script><trajectory>`(0-10 s에 x 0 -> 20 m 왕복, z 10 m) Actor `target_1` 하나와 Physics, SceneBroadcaster 시스템을 두고 `gz sim -r -s`로 띄웠다.

- `/world/t/pose/info`(50 Hz, header stamp는 sim 시간): Actor 엔티티 자체는 목록에 없고 그 link `body`만 상대 pose 0으로 나온다. 1.5초 간격 세 표본 모두 위치가 0으로 변하지 않았다. 즉 궤적 진행이 서버 쪽 pose 토픽에 반영되지 않는다.
- Actor 안에 `PosePublisher` 시스템을 붙이면 `PosePublisher plugin should be attached to a model entity. Failed to initialize.`로 로드에 실패한다.
- Actor가 있는 월드에서 `/world/t/dynamic_pose/info`를 구독하면 서버가 `SceneBroadcaster::PoseUpdate`에서 segfault로 죽는다. 같은 월드에서 Actor만 정적 model로 바꾸면 죽지 않는다. 브리지에 이 토픽을 넣으면 gazebo 서비스 전체가 내려간다.

[추정] 스크립트 궤적 Actor의 애니메이션은 렌더링 쪽(GUI, 센서)에서 계산되고 서버 ECM의 Pose는 갱신되지 않는 것으로 보인다. 소스는 아직 보지 않았다.

함의와 1b 선택지(1b 착수 때 sim-engineer가 실측으로 고른다. 이번 결정 사항은 아니다)
- (가) 어댑터가 궤적 정의(waypoint 목록)를 직접 갖고 `/clock` 기준으로 위치와 속도를 계산해 발행하고, Gazebo에는 같은 궤적을 시각화용 Actor로 둔다. 결정적이고 가볍지만 "Gazebo pose를 변환"이 아니라 "같은 정의를 두 곳에서 해석"이 된다. 정의의 단일 출처는 `fleet.yaml`의 `targets`로 두고 월드 SDF의 Actor는 생성한다.
- (나) 충돌, 중력 없는 정적 model을 서버 쪽 소형 system 플러그인 또는 `set_pose`로 움직인다. pose/info에 실제 값이 나오므로 경로 원칙 그대로다. 플러그인을 넣으면 월드 SDF에 `<plugin>`이 생겨 서버 설정 파일이 무시된다는 1b 전 결정과 맞물린다.
- (다) Actor의 `TrajectoryPose` 계열 컴포넌트를 읽는 서버 system을 만든다. 존재와 동작은 미확인이다.

계약 쪽 요구: 어느 경우든 `TargetState`가 위치와 속도를 함께 담아야 소비자가 생산 방식을 모른다. 속도가 계약에 있으면 (가)는 해석 미분, (나)와 (다)는 차분으로 채운다.

---

## 1. TargetState.msg 필드

### 권고안

```
# 표적 하나의 상태. 시뮬레이터 비의존. 토픽 /targets/<target_id>/state
std_msgs/Header header        # stamp: 상태가 유효한 시각(ROS 시각). frame_id: "world" 고정
string target_id              # ^[a-z][a-z0-9_]{0,31}$, 토픽 이름의 <id>와 같다

geometry_msgs/Point position  # world ENU, m
geometry_msgs/Vector3 velocity  # world ENU, m/s

bool velocity_valid           # false면 velocity를 쓰지 않는다(0으로 채운다)

uint8 COVARIANCE_TYPE_UNKNOWN = 0
uint8 COVARIANCE_TYPE_DIAGONAL_KNOWN = 1
uint8 COVARIANCE_TYPE_KNOWN = 2
float64[9] position_covariance  # 행 우선 3x3, m^2, world ENU
float64[9] velocity_covariance  # 행 우선 3x3, (m/s)^2, world ENU
uint8 position_covariance_type
uint8 velocity_covariance_type
```

항목별 근거

- 표적 id: 문자열 `^[a-z][a-z0-9_]{0,31}$`.
  - 토픽 경로 `/targets/<id>/state`의 한 토큰이 되므로 ROS 이름 규칙(영문 소문자 시작, 영숫자와 밑줄)을 그대로 따라야 한다. 대문자는 ROS가 허용하지만 Gazebo 엔티티 이름과 파일 이름에서 혼동을 줄이려고 막는다.
  - 정수로 두지 않는다. 기체 번호 N과 같은 정수 공간이면 로그와 미션에서 "1"이 기체인지 표적인지 헷갈린다. 실기체 추적기도 자체 문자열 id를 그대로 쓸 수 있다.
  - 시뮬레이션에서는 `fleet.yaml`의 `targets[].id` = Gazebo 엔티티 이름 = 토픽 토큰 = 이 필드, 넷이 같다. 생성기가 정규식과 중복을 검사한다.
  - 메시지 안에도 id를 두는 이유: 토픽 이름에서 id를 뽑아내지 않아도 되고, rosbag2와 Phase 3 Fleet Manager가 여러 표적 토픽을 하나의 callback으로 받을 때 필요하다. 토픽 토큰과 필드가 다르면 소비자는 버린다(검사는 `idsim_common`에 둔다).
- 위치와 속도: 둘 다 넣는다.
  - `track_entity`의 단순 추종은 위치만으로 되지만 PX4 `TrajectorySetpoint`의 velocity feedforward에 표적 속도를 넣으면 지연이 줄고, Phase 3 배분 규칙과 이후 요격 예측에도 필요하다.
  - 생산자가 차분으로 만드는 편이 소비자 셋이 각자 차분하는 것보다 낫다. 차분 잡음 처리 위치가 한 곳이 된다.
  - 실기체 추적기가 속도를 못 주는 경우가 있어 `velocity_valid`를 둔다. NaN으로 표시하지 않는 이유는 NaN이 변환과 setpoint 계산으로 번지기 때문이다(4단계 `frame_transforms` NaN 번짐 결정과 같은 이유).
- 자세: 넣지 않는다.
  - 표적은 점 표적으로 다룬다. 시뮬레이션 쪽은 줄 수 있지만(Actor 궤적의 yaw), 레이더나 영상 추적기는 표적 자세를 거의 주지 못하고, 주면 소비자가 믿게 된다. 필요해지면 `heading`과 유효 플래그를 계약 버전을 올려 더한다.
- 공분산: 넣는다. 형식은 `sensor_msgs/NavSatFix`의 관례(3x3 행 우선 + 유형 상수)를 따른다.
  - 실기체 추적기가 같은 토픽을 채운다는 원칙상 신뢰도 정보 자리를 1a에서 비워 두면 나중에 계약을 깨야 한다. 1b 소비자는 쓰지 않아도 된다.
  - 시뮬레이션 어댑터는 참값이므로 공분산 0, 유형 `KNOWN`으로 채운다. 이후 잡음 주입 파라미터를 더하면 그 분산과 `DIAGONAL_KNOWN`으로 바꾼다.
  - 별도 "신뢰도 0-1" 스칼라는 두지 않는다. 의미가 생산자마다 달라 소비자가 판단에 쓸 수 없다.
  - 표적 "소실" 플래그도 두지 않는다. 소실은 갱신 중단으로 표현하고 소비자가 stamp 나이로 판단한다(3절). 플래그와 staleness 두 경로가 생기면 서로 어긋나는 경우의 의미를 또 정해야 한다.
- frame_id: `"world"` 고정 문자열. 정의는 `docs/interface.md`에 적는다.
  - 원점: `fleet.yaml`의 `world.origin`(WGS84 위도, 경도, 고도)이 가리키는 점. Gazebo 월드 좌표 (0, 0, 0)과 같은 점이다. Gazebo는 `<spherical_coordinates>`의 위경도를 월드 원점에 둔다.
  - 축: x 동, y 북, z 위(로컬 접평면). Gazebo SDF의 `<world_frame_orientation>ENU</world_frame_orientation>`, `<heading_deg>0</heading_deg>`가 전제이고, 1b 커스텀 월드의 일치 검사(1b 전 결정)에 이 두 값을 함께 넣어야 한다. heading이 0이 아니면 Gazebo x축이 동쪽이 아니게 되어 world ENU가 깨진다.
  - `fleet.yaml`의 기체 `pose`도 같은 world ENU라 기체와 표적이 한 좌표계에 있다.
  - 이름을 `"map"`이나 `"earth"`로 하지 않는 이유: REP-105에서 `map`은 로봇 하나의 고정 프레임, `earth`는 ECEF라 뜻이 다르다. `"world"`는 Gazebo와 ros_gz 쪽 관례와 맞는다. [추정] 다른 이름이 필요하면 architect가 정하되, 문자열 상수를 메시지 정의에 `string FRAME_WORLD = "world"`로 두어 오타를 막자는 것이 요지다.
  - 고도 기준 주의: [추정] Gazebo의 `<elevation>`은 WGS84 타원체 높이로 다뤄지고 PX4의 고도는 AMSL이다. `world.origin.alt`를 무엇으로 볼지 interface.md에 적어야 한다. 1b에서 PX4 `ref_alt`와 대조로 확인할 항목이다.
- 시각: `header.stamp`는 "그 상태가 유효한 시각"이며 ROS 시각(시뮬레이션에서는 `/clock`)이다.
  - 발행 시각(`now()`)이 아니다. 시뮬레이션 어댑터는 원천 표본의 sim 시간을 쓴다. 실측으로 `/world/<w>/pose/info`의 header stamp는 sim 시간이고, ros_gz_bridge는 이 stamp를 ROS header로 옮긴다. (가) 해법이면 계산에 쓴 `/clock` 시각이다.
  - 실기체 추적기는 측정 시각을 ROS 시각으로 바꿔 넣는다. 그 변환 책임은 생산자에 있다.
  - 계약 문장: "stamp는 0이 아니어야 하고 같은 target_id에서 단조 증가한다. 소비자는 증가하지 않는 표본을 버린다."

## 2. 위치 표현

### 권고안: world ENU(m)만 둔다. 위경도는 계약에 넣지 않는다. 월드 원점(위경도)은 별도 경로로 모든 노드에 같은 값을 준다.

근거
- 소비자가 하는 일은 기체 로컬 NED setpoint 계산이다. 미터 단위 데카르트 좌표가 바로 쓰이고, 위경도면 소비자마다 측지 변환을 해야 한다. 변환은 계산 위치가 적을수록 좋다.
- 둘 다 넣으면 두 값이 어긋날 때 어느 쪽을 믿을지 정해야 한다. 이중 표현은 생산자 한 곳에서 원점을 알면 충분하다.
- 시뮬레이터 어댑터에는 world ENU가 원래 값이라 변환이 없다(roadmap 1b 2번 "ENU 유지"와 일치).
- 실기체 추적기가 GPS 위경도를 낸다면 그 변환(위경도 -> world ENU)은 생산자가 world 원점을 받아 한다. [추정] 실기체 추적기는 GPS 기반보다 레이더나 영상 기반으로 센서 기준 상대 좌표를 낼 가능성이 높고, 그 경우에도 결국 센서 위치(위경도) + 상대 벡터 -> 고정 프레임 변환을 생산자가 해야 하므로 위경도를 계약으로 해도 생산자 부담이 줄지 않는다.
- 범위: 표적과 기체가 원점에서 수 km 안이면 접평면 근사의 오차는 무시할 수준이다. [추정] 1 km에서 곡률에 의한 수직 오차는 약 8 cm, 수평은 mm 수준. 시나리오 크기가 이보다 커지면 다시 본다.

1b 원점 문제와의 관계
- 1b 전 결정대로 기체 EKF 원점은 스폰 지점이다. 그래서 `track_entity`는 world ENU 표적을 "기체 원점의 world ENU 위치"만큼 빼고 ENU -> NED로 바꿔야 한다.
- 기체 원점의 world ENU 위치를 얻는 길은 둘이다.
  - (A) `fleet.yaml`의 스폰 pose(sim 전용 지식). 간단하지만 실기체에는 없고, 스폰 직후 EKF가 원점을 잡은 위치가 스폰 pose와 미세하게 다를 수 있다.
  - (B) `VehicleLocalPosition`의 `ref_lat/ref_lon/ref_alt`와 world 원점 위경도로 계산. 실기체에서도 같은 코드가 돈다.
- sim 관점 권고: (B). 운용 노드가 시뮬레이터를 모른다는 원칙에 맞는 쪽이 (B)뿐이다. 이를 위해 world 원점 위경도는 `stack.json` -> params로 운용 노드와 어댑터에 같은 값을 준다. `TargetState`에 원점을 넣지 않는다(매 표본에 반복할 정적 값이고, 생산자마다 다른 원점을 넣을 여지가 생긴다).
- 그러면 sim 쪽 책임: Gazebo 월드 원점(`<spherical_coordinates>` 또는 `set_spherical_coordinates`)이 `world.origin`과 실제로 같다는 것을 보장. 이미 1a에서 px4 `sensor_gps`로 판정하고 있고, 1b 커스텀 월드의 일치 검사로 이어진다.
- (B)의 측지 계산(위경도 차 -> ENU)은 `idsim_common`에 한 곳만 두는 것이 맞다(ros2-engineer 소관). 변환 책임 경계는 "sim은 world ENU까지, world ENU -> 기체 NED는 운용 쪽"이다.

## 3. 발행 주기와 QoS

### 권고안
- 주기: 시뮬레이션 어댑터는 sim 시간 20 Hz로 발행한다. 주기는 계약이 아니라 interface.md의 참고값으로 둔다(1a의 "주기는 계약이 아니다" 원칙과 같다).
- QoS: 발행자 RELIABLE, VOLATILE, KEEP_LAST depth 5. 구독자는 BEST_EFFORT 또는 RELIABLE 아무거나. `idsim_common`에 `target_state_qos()` 하나로 둔다.
- staleness: 소비자가 `now() - header.stamp > T`면 표적 소실로 본다. T는 소비자 파라미터(권장 기본 0.5 s, sim 시간)이며 계약에는 "T초 안에 1회 이상" 형식의 하한만 적는다.

근거
- 주기
  - [실측] `/world/<w>/pose/info`는 sim-base 기본 설정에서 50 Hz(평균 50.01 Hz, 표준편차 0.04 ms)였다. ros_gz_bridge는 원천 주기를 그대로 넘긴다. 어댑터는 이를 받아 20 Hz로 줄여 내면 된다(최신 표본만 유지하고 sim 시간 timer로 발행).
  - 20 Hz는 1a 6번의 Offboard setpoint 주기(20 Hz)와 같아 추종 loop가 표본 하나 이상 늦지 않는다. 더 높이면 3대 x 표적 2개 시나리오에서 DDS 부하만 늘고 추종 품질은 PX4 위치 제어 대역폭에 묶인다. [추정] 50 Hz도 부하상 문제는 없을 것이나 이득이 없다.
  - pose/info는 월드의 모든 엔티티 pose를 담는 Pose_V라 기체가 늘면 메시지가 커진다. 어댑터가 이것을 받는다면 bridge 설정에서 이 토픽 하나만 받고 이름으로 거른다. 0절의 해법 (나)를 택하면 표적 전용 토픽을 만들 수 있다.
  - `dynamic_pose/info`는 0절의 segfault 때문에 브리지 대상에서 뺀다.
- QoS
  - 발행자가 RELIABLE이면 BEST_EFFORT와 RELIABLE 구독자 모두 붙는다. 발행자가 BEST_EFFORT면 RELIABLE 구독자(기본 QoS로 만든 rosbag2, 테스트 도구)가 조용히 못 받는다. 1a에서 `vehicle_status` QoS 불일치로 겪은 종류의 문제를 표적 토픽에서는 만들지 않는다.
  - VOLATILE: 마지막 표본을 늦게 붙은 구독자에게 주면(TRANSIENT_LOCAL) 묵은 위치를 현재 위치로 오인할 수 있다. staleness 판정으로 걸러지긴 하지만 처음부터 주지 않는 편이 단순하다.
  - depth 5: 같은 호스트 통신이라 손실은 드물고, 소비자는 최신 하나만 쓴다. 1이 아닌 이유는 rosbag2 기록에서 순간 지연으로 표본이 덮이는 것을 줄이려는 정도다. [추정]
  - DDS `deadline`/`liveliness` QoS로 staleness를 판정하지 않는다. 벽시계 기준이라 `use_sim_time`과 맞지 않고 배속이나 replay에서 오판한다.
- staleness
  - stamp 나이 기준이면 생산자 종류(sim 어댑터, 추적기, replay)와 무관하게 같은 판정이 된다. 수신 시각 기준은 replay 속도를 바꾸면 달라진다.
  - 0.5 s는 20 Hz 기준 10 표본이다. 시뮬레이션에서는 Gazebo가 멈추면 `/clock`도 멈춰 소비자의 now()가 같이 멈추므로 오판하지 않는다.
  - 표적이 영구히 사라지는 경우(궤적 종료, 추적 포기): 생산자는 발행을 멈춘다. 별도 종료 메시지는 두지 않는다(1절 소실 플래그를 두지 않는 이유와 같다). `track_entity`의 행동(소실 시 hover 후 실패 처리, 대기 상한)은 미션 쪽 결정이다.
  - 처음부터 한 번도 안 온 경우도 같은 규칙으로 본다: 항목 시작 후 T_wait 안에 유효 표본이 없으면 실패. T_wait는 Mission 항목 필드(4절).

## 4. Mission.msg의 track_entity 표적 참조와 sim 쪽에서 필요한 것

### 권고안: `track_entity` 항목은 `string target_id`(1절과 같은 정규식)로 표적을 참조한다. 토픽 이름은 소비자가 `/targets/<target_id>/state`로 만든다.

근거와 함께 필요한 것
- 참조는 id 문자열만. 토픽 이름 전체를 넣으면 계약된 토픽 규칙을 우회하는 경로가 생기고, 네임스페이스나 remapping이 바뀔 때 미션 파일을 고쳐야 한다. 토픽 이름 생성은 `idsim_common`의 함수 하나로 둔다.
- id 검증 위치: YAML 로더(1b 1번)가 정규식을 검사한다. 미션에 적힌 id가 `fleet.yaml`의 `targets`에 있는지는 시뮬레이션에서만 알 수 있는 사실이라 운용 노드가 검사하지 않는다. 대신 위 T_wait 실패로 드러난다. 시나리오 러너(Phase 3)는 둘을 교차 검사해도 된다.
- track_entity 항목에 함께 둘 필드(sim 관점 제안, 최종은 px4-engineer와 architect)
  - 표적 기준 오프셋: world ENU 벡터(m). 표적 바로 위나 뒤 일정 거리에서 따라가게 한다. 0이면 표적 위치 그대로라 충돌이 나므로 기본값을 0이 아닌 값(예: z +5 m)으로 하거나 필수로 둔다. 시뮬레이션 Actor는 충돌이 없어 테스트에서 이 실수가 드러나지 않는다는 점이 중요하다.
  - 종료 조건: 지속 시간(s, sim 시간) 또는 접근 거리 임계(m). 1b 4번 통합 테스트의 "표적 접근 거리 임계 이내" 판정과 같은 값을 쓸 수 있게.
  - T_wait(최초 표본 대기 상한, s)와 staleness T를 항목 필드로 둘지 노드 파라미터로 둘지는 미션 쪽 결정이다. sim 관점에서는 노드 파라미터가 충분하다.
- sim 쪽에서 1b에 필요한 것(이번 계약에는 들어가지 않는다. 기록용)
  - `fleet.yaml`의 `targets` 스키마: `id`, 궤적(waypoint 목록: 시각 s, world ENU 위치 m), loop 여부, 시작 지연. 1a에서 비워 둔 자리다. 이것이 어댑터 params, Gazebo Actor SDF, (0절 (가)를 택하면) 어댑터의 궤적 계산 모두의 단일 출처가 된다. 스키마는 devops-engineer와 함께 정한다.
  - 표적이 기체 스폰 위치와 겹치지 않는지 생성기 검사(기체 간격 규칙과 같은 방식).
  - 어댑터의 시간 기준은 `use_sim_time`이다. bridge 서비스가 이미 `/clock`을 내므로 새 요구는 없다.

---

## 요약

1. `TargetState`: Header(stamp는 상태 유효 시각, frame_id `"world"`), `target_id` 문자열(`^[a-z][a-z0-9_]{0,31}$`), ENU 위치와 속도, `velocity_valid`, NavSatFix식 공분산 둘과 유형. 자세, 신뢰도 스칼라, 소실 플래그는 넣지 않는다.
2. 위치는 world ENU(m)만. 원점은 `world.origin` 위경도이며 Gazebo 월드 (0,0,0)과 같은 점이다. 원점은 메시지가 아니라 `stack.json` params로 모든 노드에 같은 값을 준다. world ENU -> 기체 NED는 `ref_lat/lon/alt`로 운용 쪽이 계산한다.
3. 어댑터는 sim 시간 20 Hz, 발행자 RELIABLE/VOLATILE/KEEP_LAST 5. staleness는 소비자가 `now() - stamp > T`(기본 0.5 s)로 판정. 주기는 참고값이다.
4. `track_entity`는 `target_id` 문자열로 참조하고 오프셋과 종료 조건을 함께 둔다.
5. [실측] gz-sim 8.15.0에서 스크립트 궤적 Actor의 pose는 서버 pose 토픽에 반영되지 않고, PosePublisher는 Actor에 붙지 않으며, Actor가 있을 때 `dynamic_pose/info` 구독은 서버를 죽인다. 계약에는 영향이 없지만 1b 어댑터 설계의 전제를 바꾸므로 1b 착수 전 리스크로 기록할 것을 권한다.
