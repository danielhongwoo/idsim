# idsim 아키텍처

이 문서는 idsim(Drone Simulator)의 목표, 레이어 구조, 기술 스택, 실행 환경, 테스트 전략을 정의한다.

## 목표와 범위

이 프로젝트는 드론 자율비행 플랫폼 팀의 핵심 업무인 "자율비행 플랫폼 아키텍처, 비행제어-자율비행 알고리즘 간 데이터 파이프라인, Fleet Management, Mission Planning, Telemetry, 로그/replay, 테스트 자동화"를 PC 한 대 위의 시뮬레이션 환경으로 재현한다. 목적은 실기체 개발을 돕는 것이다. 실기체 개발에 쓸 플랫폼 소프트웨어를 실제 기체 없이 PX4 SITL + Gazebo 위에서 만들고 비행 시험 검증 체계를 돌려 본다. 프로젝트명 idsim은 Drone Simulator의 약자로, 이동하는 표적(공격 드론 등)을 방어적 수단으로 요격하는 드론 플릿을 올릴 플랫폼을 시뮬레이션한다는 뜻이다.

| 플랫폼 업무 항목 | 이 프로젝트에서의 대응 과제 | Phase (roadmap.md) |
| --- | --- | --- |
| 비행제어-자율비행 알고리즘 간 데이터 파이프라인, 통신 표준화 | PX4 <-> ROS 2(uXRCE-DDS) bridge, 토픽/QoS/좌표계 규약 정의 | 1 |
| 하드웨어-소프트웨어 인터페이스 정의 | SITL 기체를 "하드웨어"로 간주한 인터페이스 계약(토픽, 서비스, MAVLink 포트) 문서화 | 1 |
| Mission Planning | 미션 정의(waypoint/행동 시퀀스) -> ROS 2 미션 노드 -> PX4 Offboard 제어 | 1, 3 |
| Telemetry | PX4 uORB 토픽을 수집해 요약 상태로 재발행하는 수집기 서비스 | 2 |
| 대규모 로깅/replay 시스템 | rosbag2(MCAP) 기반 기록 + replay + ULog 연동 | 2 |
| Fleet Management | 다중 PX4 인스턴스 스폰, 기체별 네임스페이스, 상태 집계 API(gRPC/Protobuf) | 3 |
| CI/CD, 테스트 자동화 | Docker Compose 환경 + headless SITL 통합 테스트(pytest/GoogleTest) + GitHub Actions | 전체 |
| 실시간 영상 스트리밍 | Gazebo 카메라 -> GStreamer -> WebRTC. 이번 범위 밖, 확장 단계로 미룸 | 확장 |

다루지 않는 것: 특정 표적을 추적, 교전하는 유도 알고리즘 자체. 움직이는 표적은 `config/fleet.yaml`에 적은 스크립트 궤적을 시뮬레이션 시간에 맞춰 따르는 점 표적으로 두고, 그 위치를 미션 노드가 `TargetState` 계약으로 구독해 따라가는 수준까지만 다룬다. 표적 생산자는 이 계약 뒤에서 교체할 수 있다. 시뮬레이션에서는 표적 어댑터가 궤적 정의를 계산해 채우고, 실기체에서는 같은 토픽을 표적 추적기가 채운다. Gazebo의 물리 상태를 따라 움직이는 표적(반응형 기동 등)의 생산자는 확장 항목이다. 즉 교전 로직이 아니라 그 로직을 올릴 플랫폼(통신, 미션, Telemetry, replay, 테스트)을 만든다.

GPS 없는 비행도 다루지 않는다. GPS는 항상 수신된다고 가정한다.

## 전체 아키텍처

세 레이어로 나눈다. 기준은 실기체의 구조다. 맨 아래가 기체 레이어(PX4가 비행제어를 맡는 기체 N대)이고, 가운데 ROS 2 버스가 "비행제어-자율비행 알고리즘 간 데이터 파이프라인"이며, 위의 운용 서비스 레이어가 Fleet, Mission, Telemetry, Replay다. ROS 2 버스는 기체마다 하나이고 그 기체 안에 있다. 운용 서비스는 놓이는 곳으로 둘로 나뉜다. 기체 운용 노드(Mission Executor, Telemetry Collector)는 기체 안에서 그 기체의 버스에 붙고, Fleet 서비스(Fleet Manager)는 지상에 있다. 둘 사이가 지상 링크이고, 지상 링크를 건너는 계약은 `ExecuteMission`, `VehicleState`, `MissionEvent` 셋이고 `MissionEvent`는 지상에서 구독한다. 지상의 어느 컴포넌트가 구독하는지는 기록기의 위치와 함께 정하지 않았다. 지상 링크는 DDS가 아니라 Zenoh로 잇는다. Zenoh의 구성은 정하지 않았다.

시뮬레이션은 이 구조에서 실물이 필요한 부분만 대신하고, 그 밖의 구조(실행 주체, 버스의 범위, 통신 방식)는 실기체 환경과 같게 둔다. 그래서 두 환경의 차이는 실물을 대신하는 것으로만 남아야 한다. 이 저장소에서는 PX4 SITL x N과 Gazebo가 기체 레이어를 대신하고, 개발 호스트 한 대가 지상국과 기체의 장비를 대신한다. 대신하는 것은 장비의 수이지 통신 구조가 아니다. 시뮬레이션에서도 ROS 2 버스는 기체마다 DDS 도메인으로 나누고, Fleet Manager와 기체 운용 노드 사이의 지상 링크는 Zenoh로 잇는다. 기체가 한 대인 스택에서는 스택의 DDS 도메인이 곧 그 기체의 버스이고 지상 쪽 서비스가 없으므로 이 구조와 이미 같다. 기체마다의 도메인과 Zenoh 지상 링크는 기체가 여러 대가 되고 Fleet Manager가 생기는 Phase 3에서 더한다. 그 전에 계약을 쓰는 것은 통합 테스트와 CLI `send_mission`(`ExecuteMission`을 보낸다), Phase 2의 임시 WebSocket 어댑터(`VehicleState`를 읽는다)이고, 이들은 지상 링크를 거치지 않고 기체의 버스에서 계약을 직접 쓰고 읽는다. 무선 구간의 지연과 손실은 시뮬레이션에 넣지 않는다. 운용 서비스는 시뮬레이터의 토픽과 프로세스에 의존하지 않도록 설계해, 실기체에 올릴 때 고칠 곳이 아래에 적은 "시뮬레이션이 실기체와 달라지는 곳"으로 좁혀지게 한다.

이 절의 그림 둘은 같은 구조를 실기체 환경과 시뮬레이션 환경으로 보인다. 실행 주체, 그것이 놓이는 장비, 서로 주고받는 것을 보인다. 실기체 환경 그림이 기준이고 이 문서의 큰 그림이다. 시뮬레이션 환경 그림은 큰 그림의 어느 부분을 무엇이 대신하는지로 읽는다. 같은 실행 주체는 두 그림에서 같은 이름과 같은 순서로 둔다. 상자 테두리(subgraph)는 장비 한 대다. 통신 방식은 이 그림의 화살표에 적고, 컨테이너와 포트, 전송 계층의 세부는 "Docker Compose 실행 환경 설계" 절의 그림이 보인다.

큰 그림(실기체 환경). 아래 배치는 이 문서가 전제하는 기준 배치이고, 실기체 적용의 범위와 배치의 세부는 정해지지 않았다. 전제는 다음과 같다. PX4는 FMU에서 돌고, 기체마다 companion computer가 Agent와 그 기체의 운용 노드를 돌리며, 지상국이 Fleet Manager를 돌리고, 기체와 지상국은 지상 링크로 이어진다. 지상 링크는 Zenoh로 잇는다. companion computer의 사양과 무선 장비의 종류, Zenoh의 구성은 정하지 않았다.

```mermaid
flowchart TB
  EXT["외부 클라이언트<br/>웹, gRPC"]
  subgraph GND["지상국"]
    FM["Fleet Manager<br/>기체 등록, 미션 배분"]
  end
  subgraph CC["companion computer<br/>기체마다 하나"]
    OPS["기체 운용 노드<br/>Executor, Collector"]
    AG["uXRCE-DDS Agent<br/>기체마다 하나"]
  end
  subgraph FMU["FMU<br/>기체마다 하나"]
    PX["PX4<br/>비행제어"]
  end
  HW["기체와 센서<br/>실물"]
  TP["표적 추적기<br/>위치 정하지 않음"]
  EXT <-->|"gRPC, WebSocket"| FM
  FM <-->|"지상 링크: Zenoh"| OPS
  OPS <-->|"ROS 2 /fmu 토픽"| AG
  AG <-->|"XRCE-DDS"| PX
  PX <-->|"센서, 구동"| HW
  TP -->|"TargetState 토픽"| OPS
```

- 기체 운용 노드는 그 기체의 ROS 2 버스만 보고, 버스 아래가 실물인지 시뮬레이션인지에 의존하지 않는다. Gazebo 토픽을 구독하거나 시뮬레이터 프로세스를 참조하지 않는다. 버스로 명령과 setpoint를 내리고 상태를 받는다.
- ROS 2 버스는 기체마다 하나이고 companion computer 안에 있다. 그림에서 기체 운용 노드와 Agent 사이의 "/fmu 토픽"이 그 버스 위의 것이다.
- Fleet Manager는 기체의 버스에 직접 붙지 않는다. 지상 링크를 건너는 계약은 `ExecuteMission`, `VehicleState`, `MissionEvent` 셋이고 `MissionEvent`는 지상에서 구독한다. 지상의 어느 컴포넌트가 구독하는지는 기록기(Logger)의 위치와 함께 정하지 않았다. 표적 추적기와 기록기가 놓이는 곳에 따라 `TargetState`와 기록 대상인 `/fmu` 토픽도 건널 수 있고, 이것도 정하지 않았다. 지상 링크는 Zenoh로 잇고, Zenoh의 구성은 정하지 않았다.
- 통신 방식: 기체 안은 ROS 2(DDS), PX4와는 Agent를 거친 XRCE-DDS, 지상 링크는 Zenoh, 외부 클라이언트는 gRPC이고 웹 브라우저는 gateway를 거친 WebSocket이다.
- 맨 아래는 기체 레이어다. 기체 하나가 PX4 하나다.
- 외부 클라이언트는 ROS 2를 모르고 Fleet Manager의 API로만 기체들을 본다. Fleet Manager가 생기기 전의 임시 WebSocket 어댑터(Phase 2)는 기체의 버스에서 `VehicleState`를 직접 읽는 개발용이고 그림에 넣지 않았다.
- 기록과 재생(Logger, Replay)이 기체 안과 지상 가운데 어디에 놓이는지는 정하지 않아 큰 그림에 넣지 않는다.

시뮬레이션 환경. 큰 그림에서 실물이 필요한 부분만 대신한 것이다. FMU의 PX4는 PX4 SITL 프로세스가, 기체와 센서는 Gazebo가, 표적 추적기는 표적 어댑터가 대신하고, 장비 셋(지상국, companion computer, FMU)은 개발 호스트 한 대가 대신한다. 통신 구조는 큰 그림과 같다. ROS 2 버스는 기체마다 DDS 도메인 하나이고, Fleet Manager와 기체 운용 노드 사이의 지상 링크는 Zenoh로 잇는다(Phase 3). Zenoh의 구성과, `/clock`, 표적 상태, 정답 pose를 기체마다의 도메인에 공급하는 방법은 정하지 않았다. Fleet Manager, 기체 운용 노드, Agent는 실기체 환경과 같은 것이 돈다. Agent는 시뮬레이션에서도 기체마다 하나이다. 지금의 compose는 Agent 하나가 스택의 모든 PX4 SITL 인스턴스를 받고, 기체가 한 대이면 그 Agent가 곧 그 기체의 Agent라 이미 같은 구조이다. 기체가 여러 대가 될 때(Phase 3) 기체마다 하나로 만든다.

```mermaid
flowchart TB
  EXT["외부 클라이언트<br/>웹, gRPC"]
  subgraph HOST["개발 호스트 한 대"]
    FM["Fleet Manager<br/>기체 등록, 미션 배분"]
    OPS["기체 운용 노드 x N<br/>Executor, Collector"]
    AG["uXRCE-DDS Agent<br/>기체마다 하나"]
    PX["PX4 SITL x N<br/>FMU의 PX4를 대신"]
    GZ["Gazebo<br/>기체와 센서를 대신"]
    TP["표적 어댑터<br/>표적 추적기를 대신"]
  end
  EXT <-->|"gRPC, WebSocket"| FM
  FM <-->|"지상 링크: Zenoh"| OPS
  OPS <-->|"ROS 2 /fmu 토픽"| AG
  AG <-->|"XRCE-DDS"| PX
  PX <-->|"센서, 구동"| GZ
  GZ -->|"ROS 2 /clock"| OPS
  TP -->|"TargetState 토픽"| OPS
```

시뮬레이션이 실기체와 달라지는 곳은 둘로 가른다. 실물을 대신하므로 남는 차이와, 실물과 무관한데 다른 것이다.

실물을 대신하므로 남는 차이는 그림과 아래 표의 PX4 SITL, Gazebo, 표적 어댑터, `/clock`(시뮬레이션 시간), 정답 pose, 장비 한 대다. 이 가운데 운용 쪽의 코드와 설정이 시뮬레이션에 맞춰져 있는 곳으로 확인된 것은 다음 셋이고, 실기체에 올리려면 이 셋을 먼저 풀어야 한다. 이 밖에 없다는 것은 확인하지 않았다.

- 시간 출처: 실기체 그림에는 없고 시뮬레이션 그림에만 있는 `/clock` 화살표다. 실기체에는 `/clock`을 공급하는 주체가 없는데, 운용 노드는 `/clock`(시뮬레이션 시간)이 있어야 돈다. Executor는 `use_sim_time`이 true가 아니면 configure를 거부하고, /fmu/in에 넣는 timestamp는 ROS 시간 override가 켜진 시계에서만 만들어진다. 생성기도 운용 노드 params에 `use_sim_time: true`를 고정해 넣는다. PX4 쪽의 `UXRCE_DDS_SYNCT=0`도 SITL 전용 값이다(`docs/interface.md` "시간 기준" 절).
- 고도 기준: "센서, 구동"의 상대가 실제 GNSS가 아니라 Gazebo인 곳이다. PX4의 원점 고도는 AMSL이고, world ENU와 기체 로컬 NED 사이의 변환(`idsim_common`의 geo)은 `world.origin`의 고도를 타원체 고로 다룬다. 실제 GNSS에서는 두 값이 다르지만 SITL에서는 같은 수로 공급되어 차이가 드러나지 않는다(`docs/interface.md` "좌표계" 절). 이 변환은 Gazebo(gz-math)의 좌표 식을 그대로 옮긴 것이라 `idsim_common`에 Gazebo의 식과 이름이 있다. Gazebo 토픽과 include 의존은 없다.
- 한 호스트 배치: 실기체 그림의 장비 테두리 셋이 시뮬레이션 그림에서 하나로 합쳐진 것이다. 합쳐지는 것은 장비뿐이고, 기체마다의 버스와 지상 링크는 시뮬레이션에서도 따로 둔다. 시뮬레이션이 같게 두는 것은 통신 구조이고, 무선 구간의 지연과 손실은 시뮬레이션에 넣지 않는다. 지금의 DDS 설정(`config/cyclonedds.xml`)은 multicast를 끄고 peer를 127.0.0.1 하나로 두어, DDS 참가자(운용 노드와 Agent)가 모두 한 호스트에 있다고 가정한다.

실물과 무관한데 실기체와 다른 것은 설계로는 없다. 지금의 compose에만 남은 차이가 있고, 이는 기체가 여러 대일 때에만 차이가 되며 기체가 한 대인 스택에서는 실기체 구조와 같다. 기체가 여러 대가 될 때(Phase 3) 아래 둘을 모두 실기체 구조로 맞춘다.

- 버스의 범위와 지상 링크: 지금의 compose는 스택에 DDS 도메인 하나를 쓰고 Zenoh 구성이 없어, 기체가 여러 대이면 모든 기체의 운용 노드가 한 버스에서 만난다. 기체마다의 도메인과 Zenoh 지상 링크는 Phase 3에서 더한다.
- Agent의 수: 설계는 실기체와 같이 기체마다 하나이다. 지금의 compose는 스택에 하나가 모든 PX4 SITL 인스턴스를 받는다.

환경별 실체. 역할은 두 환경에서 같다. 실기체 환경 열은 위의 전제를 따르고, 시뮬레이션 환경 열은 그것을 무엇이 대신하는지다.

| 컴포넌트 | 역할 | 실기체 환경 | 시뮬레이션 환경(대신하는 것) |
| --- | --- | --- | --- |
| 비행제어(PX4) | 자세와 위치 제어, 모드와 failsafe, arm과 disarm | FMU의 PX4 펌웨어 | PX4 SITL 프로세스(기체마다 컨테이너 하나) |
| 기체 물리와 센서 | 기체의 운동과 IMU, GNSS 등의 측정값 | 실제 기체와 센서 | Gazebo(모든 기체가 월드 하나를 공유) |
| uXRCE-DDS Agent | PX4의 uORB 토픽과 ROS 2 토픽 사이의 중계 | companion computer마다 하나, FMU와 serial 또는 Ethernet | 같은 Agent. 기체마다 하나이다. 지금의 compose는 인스턴스 하나가 모든 기체를 UDP로 받고(기체가 한 대이면 이미 같은 구조), 기체가 여러 대가 될 때(Phase 3) 기체마다 하나로 바꾼다 |
| ROS 2 버스 | 기체 운용 노드와 PX4 사이의 토픽 전달 | 기체마다 하나이고 companion computer 안에 있다 | 기체마다 DDS 도메인 하나. 모두 개발 호스트 한 대에 있고 peer는 loopback이다. 지금의 compose는 스택에 도메인 하나라 기체가 한 대이면 이와 같고, 여러 대의 도메인 분리는 Phase 3에서 더한다 |
| 지상 링크 | Fleet Manager와 기체 운용 노드 사이의 계약 전달 | 지상국과 기체 사이의 무선 구간. Zenoh로 잇는다. 건너는 계약은 `ExecuteMission`, `VehicleState`, `MissionEvent`이고 `MissionEvent`는 지상에서 구독한다. Zenoh의 구성과 이 셋 밖에 무엇이 건너는지는 정하지 않음 | 개발 호스트 안에서 Zenoh로 잇는다(Phase 3). 무선 장비는 없고 무선의 지연과 손실은 넣지 않는다. Zenoh의 구성은 정하지 않음. 지금의 compose에는 지상 쪽 서비스와 Zenoh 구성이 없다 |
| Mission Executor | 미션을 Offboard setpoint와 명령으로 실행 | 그 기체의 companion computer | 같은 노드. 개발 호스트의 `ops-N` 컨테이너 |
| Telemetry Collector(Phase 2) | PX4 상태를 `VehicleState`로 요약 | 그 기체의 companion computer | 같은 노드. Executor와 같은 컨테이너 |
| Fleet Manager(Phase 3) | 기체 레지스트리, 미션 배분, 외부 API | 지상국 | 같은 서비스. 개발 호스트 |
| 표적 생산자 | `TargetState` 발행 | 표적 추적기. 위치는 정하지 않음 | 표적 어댑터(fleet 파일의 궤적 정의를 평가) |
| 시간 출처 | 판정, 집계, 기록의 시각 기준 | 정하지 않음(실기체에는 `/clock`을 공급하는 주체가 없다) | Gazebo 시뮬레이션 시간(`/clock`) |
| 정답 pose | 판정이 쓰는 기체의 참값 위치 | 없음 | `sim-oracle`이 Gazebo에서 읽어 발행 |
| GCS | MAVLink 지상 관제 | 정하지 않음 | idsim이 띄우는 GCS는 없다. 외부 GCS가 GCS 포트로 붙을 수 있다 |
| 기록(ULog, rosbag2) | 비행 기록과 토픽 기록 | ULog는 FMU의 저장 장치, rosbag2의 위치는 정하지 않음 | ULog는 px4 컨테이너의 실행 디렉터리, rosbag2는 개발 호스트(Phase 2) |

이 원칙은 표적 경로에도 적용한다. Mission Executor는 Gazebo 토픽을 직접 구독하지 않고 `idsim_interfaces`의 `TargetState` 계약(`/targets/<id>/state`)만 구독한다. 실기체에서는 이 토픽을 표적 추적기가 채운다. 시뮬레이션에서는 표적 추적기를 대신해 `idsim_sim`의 표적 어댑터 노드가 fleet 파일(`config/fleet.yaml` 등)의 궤적 정의를 시뮬레이션 시간에 평가해 이 계약으로 발행하고, Gazebo 월드의 Actor는 같은 정의로 생성해 화면에서 확인하는 용도다(Actor의 화면 위치는 참고용이다. Actor는 반복 재생으로만 만들고 `loop`가 false인 표적은 끝에 86400 s의 정지를 붙여 나타내므로, 그 뒤에는 화면의 Actor만 처음 위치로 돌아간다). 표적 어댑터는 Gazebo를 구독하지 않는다.

운용 서비스 레이어. 큰 그림의 "Fleet Manager"와 "기체 운용 노드" 상자를 펼쳐 운용 서비스끼리, 그리고 버스와 무엇을 주고받는지를 보인다. 장비 경계는 큰 그림에 있고 여기에는 그리지 않는다. Fleet Manager와 맺는 "미션 배분"과 "상태 집계"가 지상 링크(Zenoh)를 건너는 계약이다. 이 밖에 `MissionEvent`(미션 기록)도 지상에서 구독하며, 어느 컴포넌트가 구독하는지는 정하지 않아 그림에 넣지 않았다. Logger와 Replay는 놓이는 곳을 정하지 않았다. 그림의 "기록" 화살표는 Logger가 그 기체의 버스에 있는 토픽을 기록한다는 뜻이고 Logger가 기체 안에 놓인다는 뜻이 아니다. 큰 그림의 기체 쪽 상자(Agent, PX4, 기체와 센서)와 그 일부를 대신하는 시뮬레이션 구성(PX4 SITL, Gazebo, bridge)은 여기서 펼치지 않고, 그 컨테이너와 프로토콜은 "Docker Compose 실행 환경 설계" 절의 상세 1에만 그린다.

```mermaid
flowchart TB
  FM["Fleet Manager<br/>기체 등록, 미션 배분"]
  ME["Mission Executor<br/>기체마다"]
  TC["Telemetry Collector<br/>기체마다"]
  LR["Logger / Replay<br/>기록과 재생"]
  BUS["ROS 2 버스<br/>그 기체의 토픽"]

  FM -->|"미션 배분"| ME
  TC -->|"상태 집계"| FM
  ME -->|"setpoint, 명령"| BUS
  BUS -->|"TargetState"| ME
  BUS -->|"PX4 상태"| TC
  BUS -->|"기록"| LR
```

구성 요소가 하는 일. 큰 그림과 위 그림의 상자, 그리고 기체 레이어를 대신하는 시뮬레이션의 구성 요소를 함께 적는다. 이 표에서 표적 어댑터, 정답 pose, PX4 SITL, Gazebo의 행은 시뮬레이션이 대신하는 것이고, Agent의 행은 두 환경에 같이 있는 것을 시뮬레이션 구성의 값으로 적은 것이며, 실기체 쪽의 실체는 위의 환경별 실체 표에 있다.

| 구성 요소 | 레이어 | 하는 일 | Phase |
| --- | --- | --- | --- |
| Fleet Manager | 운용 서비스 | 기체 레지스트리, 상태 집계, 미션 큐와 배분(`ExecuteMission` action), gRPC/Protobuf API | 3 |
| Mission Executor x N (`idsim_mission`) | 운용 서비스 | YAML 미션 -> 행동 시퀀스 상태기. Offboard setpoint 발행(`OffboardControlMode`, `TrajectorySetpoint`, `VehicleCommand`). `TargetState` 구독(시뮬레이터 비의존 계약) | 1 |
| Telemetry Collector x N | 운용 서비스 | `/fmu/out` 구독 -> `VehicleState` 요약. Phase 2의 임시 WebSocket 어댑터가 이것을 읽어 브라우저로 낸다 | 2 |
| Logger / Replay | 운용 서비스 | rosbag2 (MCAP), ULog 동기화 | 2 |
| ROS 2 (DDS) 토픽 버스 | 버스 | `/px4_N/fmu/out/*`, `/px4_N/fmu/in/*`, `/targets/*/state`. 기체별 네임스페이스로 분리, px4_msgs 타입, sensor_data QoS, rmw는 CycloneDDS | 1 |
| Micro XRCE-DDS Agent v2.4.3 | 버스와 기체 사이 | PX4의 uXRCE-DDS client와 ROS 2 버스 사이의 중계. 시뮬레이션 구성: udp4, 기준 포트 8888 + 스택 번호 k, 지금의 compose는 인스턴스 하나로 모든 기체 수용(기체가 여러 대가 될 때 기체마다 하나로 바꾼다. Phase 3) | 1 |
| `idsim_sim` 표적 어댑터 + ros_gz_bridge | 버스와 시뮬레이션 사이 | 표적 어댑터는 궤적 정의 -> `TargetState`, ros_gz_bridge는 `/clock`만 | 1 |
| `idsim_sim` 정답 pose 노드 (`sim-oracle`) | 버스와 시뮬레이션 사이 | Gazebo의 기체 pose -> `/sim/<vehicle_id>/pose`(base_link 기준). SITL 판정 전용이고 계약이 아니다 | 1 |
| PX4 SITL `-i 1` | 기체(시뮬레이션이 대신) | uXRCE-DDS client, 네임스페이스 `/px4_1`, MAVLink 14550 + 1000k (GCS) / 14541 + 1000k (API), ULog 기록 | 1 |
| PX4 SITL `-i 2...N` | 기체(시뮬레이션이 대신) | `UXRCE_DDS_KEY` = i+1 = `MAV_SYS_ID`, 네임스페이스 `/px4_i`, API 14540 + 1000k + i | 3 |
| Gazebo Harmonic (`gz sim -s`, 서버 전용) | 기체(시뮬레이션이 대신) | x500 기체 모델 x N, 이동 표적 Actor(화면 확인용), 물리/센서 plugin | 1 |

버스 위의 이름과 쓰는 쪽, 읽는 쪽.

| 버스 위의 이름 | 쓰는 쪽 | 읽는 쪽 |
| --- | --- | --- |
| `/px4_N/fmu/in` | Mission Executor(운용 노드 가운데 유일). 통합 테스트와 스모크는 `tests/support/`의 발행 모듈(`px4_raw.py`)로 직접 쓴다 | PX4 (Agent 경유) |
| `/px4_N/fmu/out` | PX4 (Agent 경유) | Mission Executor, Telemetry Collector, 판정 노드 |
| `/clock` | ros_gz_bridge | 모든 ROS 2 노드 |
| `/targets/*/state` | 표적 어댑터 (시뮬레이션), 표적 추적기 (실기체) | Mission Executor, 판정 노드 |
| `/sim/<vehicle_id>/pose` | 정답 pose 노드 (SITL 전용) | 판정 노드, Logger (Phase 2, SITL 실행의 기록만). 운용 패키지(테스트 절의 목록)는 읽지 않는다 |
| `/px4_N/execute_mission` (action) | 판정 노드와 CLI `send_mission`(기체의 버스에서 직접), Fleet Manager (Phase 3, 지상 링크를 거쳐) | Mission Executor |
| `/px4_N/vehicle_state` | Telemetry Collector (Phase 2) | 임시 WebSocket 어댑터 (Phase 2, 기체의 버스에서 직접), Fleet Manager (Phase 3, 지상 링크를 거쳐), 판정 노드 |
| `/px4_N/mission_event` | Mission Executor | Logger, 판정 노드, 지상 (Phase 3, 지상 링크를 거쳐 구독. 컴포넌트는 정하지 않음) |

기체 운용 노드는 그 기체의 ROS 2 토픽만 보고 동작하고, PX4는 uXRCE-DDS Agent를 통해 그 기체의 버스에 올라온다. 실기체의 기준 배치에서는 Agent와 버스가 기체마다 하나다. 시뮬레이션에서도 버스가 기체마다 DDS 도메인 하나이고 Agent가 기체마다 하나이다(Phase 3). 지금의 compose에서는 Agent 하나가 모든 PX4 SITL 인스턴스를 같은 DDS 도메인에 올리며 기체는 네임스페이스로 나뉜다. 기체를 실제로 움직이는 setpoint는 운용 노드 가운데서는 기체별 Mission Executor만 발행하고(통합 테스트와 스모크가 `px4_raw.py`로 `/fmu/in`에 직접 쓰는 것은 테스트 전용 예외다), Fleet Manager는 지상 링크를 건너는 계약으로 미션을 배분하고 상태를 집계할 뿐 `/fmu/in/*`에 직접 쓰지 않는다. MAVLink는 외부 GCS용 곁가지이며 운용 서비스는 사용하지 않는다. PX4와 기체(모터, 센서) 사이의 교환은 ROS 2를 거치지 않는다. 시뮬레이션에서는 이것이 PX4 SITL <-> Gazebo의 직접 연결이다.

## 기체 식별과 설정의 단일 출처

기체 한 대는 compose 서비스 이름, PX4 인스턴스 번호, `MAV_SYS_ID`와 `UXRCE_DDS_KEY`, ROS 네임스페이스, Gazebo 모델 이름, MAVLink API 포트라는 여러 식별자를 동시에 가진다. 이것을 손으로 맞추지 않고, 스택 하나는 그 스택을 만든 fleet 파일 하나에서 파생한다. 개발 스택은 `config/fleet.yaml`을 쓰고, SITL 통합 테스트는 시나리오 기하가 개발용 설정에 끌려가지 않도록 전용 `tests/sitl/fleet.yaml`을 쓴다. 어느 파일로 만든 스택인지는 `stack.json`의 `inputs`에 남는다. 아래에서 `config/fleet.yaml`의 형식이라고 적은 것은 모든 fleet 파일에 같다.

- 기체 번호 N은 1부터 시작한다. 단일 기체 Phase에서도 N=1이며, PX4 인스턴스 0의 "네임스페이스 없음" 특수 케이스는 어디서도 쓰지 않는다. `PX4_UXRCE_DDS_NS=px4_N`으로 네임스페이스를 항상 명시한다.
- 파생 규칙: PX4 인스턴스 = N, `MAV_SYS_ID` = `UXRCE_DDS_KEY` = N+1, 네임스페이스 = `/px4_N`, Gazebo 모델 이름 = `<모델>_N`(모델은 airframe의 시뮬레이터 모델 이름에서 `gz_`를 뗀 것. 지금은 `x500_N`), MAVLink API 포트 = 14540 + 1000k + N(k는 스택 번호), compose 서비스 = `px4-N`.
- `config/fleet.yaml`에는 사람이 고르는 값만 적는다: 기체 목록(번호 `id`, `airframe`, 초기 `pose` {x, y, z, yaw}(Gazebo 월드 좌표 ENU, m, rad), 기체별 SITL 파라미터 `px4_params`), 월드(`world.name`, 월드 템플릿 `world.template`, 원점 `world.origin` {lat, lon, alt}, `world.speed_factor`), 표적 목록 `targets`, 공통 SITL 파라미터 파일 `px4.params_file`, 기동 방식 `px4.start`(parallel 또는 sequential). 파일 형식의 판은 최상위 `schema`이고 2만 받는다. `world.template`은 저장소 기준 상대 경로의 `.sdf` 파일(절대 경로와 `..`는 거부)이고, 컨테이너 안의 완성 월드를 가리키는 `world.file` key는 없다(적으면 모르는 key로 거부되고 오류 메시지가 `world.template`을 알려 준다). `airframe`(예: `4001_gz_x500`) 하나에서 `SYS_AUTOSTART`, `PX4_SIM_MODEL`, Gazebo 모델 이름이 파생된다. 파생값(포트, 네임스페이스, `MAV_SYS_ID`, `UXRCE_DDS_KEY`, 모델 이름, 서비스 이름)은 적을 수 없고 생성 스크립트가 거부한다. `px4_params`에서도 식별 파라미터(`MAV_SYS_ID`, `UXRCE_DDS_KEY`, `UXRCE_DDS_DOM_ID`, `UXRCE_DDS_AG_IP`, `SYS_AUTOSTART`)는 거부한다. `world.speed_factor`는 null이어야 한다(배속 기제는 Phase 3에서 정한다). `targets[]`는 표적마다 `id`(`target_id` 규칙, 중복 금지), `start_s`(그 전에는 첫 waypoint에 정지), `loop`(true면 처음과 끝 waypoint가 같아야 한다), `waypoints[]`(`{t, x, y, z}`, world ENU m, t는 `start_s` 기준 s로 0에서 시작해 엄격히 증가, 2개 이상) 네 key를 모두 적어야 하고 기본값이 없다. 궤적은 구간 직선이고, 생성 스크립트는 구간 속도 상한(수평 5 m/s, 수직 1 m/s), 음의 z, 기체 스폰 지점과 수평 2 m 안의 시작 위치, 기체 모델과 월드 엔티티와 겹치는 이름, 좌표 범위(|x|, |y| 10000 m, z 1000 m) 초과, ms로 반올림한 인접 waypoint 시각의 차가 100 ms 미만인 것, 86400 s를 넘는 `start_s`, 개수 상한(표적 32, 표적당 waypoint 256) 초과, 모든 표적의 궤적 길이(마지막 waypoint의 `t`를 ms로 반올림한 값) 합이 2400 s를 넘는 것을 거부한다. 길이 합의 상한은 궤적을 균일 간격의 표본으로 나눠 만드는 Gazebo Actor의 비용(서버 메모리, GUI 프레임)이 월드 전체 표본 수에 비례하기 때문에 둔다. 긴 실행은 `loop`로 덮는다. 궤적 정의의 출처는 fleet 파일의 `targets` 하나이고, 생성 스크립트가 정규화한 값을 월드 SDF의 Actor, 표적 어댑터의 params, `stack.json`에 함께 낸다. 기체 번호는 1-9, 기체 간격은 2 m 미만이면 거부하고 4 m 미만이면 경고한다. 스택 번호 k(0-9)는 추적 파일에 두지 않고 생성 인자(`--stack`, 없으면 `IDSIM_STACK_INDEX`, 없으면 0)로 준다. `GZ_PARTITION`은 gz-transport discovery를 스택 단위로 격리한다.
- 생성 스크립트 `tools/gen_compose.py`가 이 파일에서 compose 파일과 `stack.json`을 `artifacts/runs/<실행 id>/`에 만든다. `stack.json`은 실행 시점의 단일 출처이며, 스크립트와 테스트 fixture는 식별자를 다시 계산하지 않고 이 파일만 읽는다(경로는 `IDSIM_STACK_FILE`). launch 파일은 생성하지 않고 노드 파라미터 파일 `params/ops-N.yaml`만 생성한다. 그 안에는 `/**` 아래 `use_sim_time: true`, 식별값 `vehicle.id`, `vehicle.ns`, `vehicle.sysid`, 원점 `world.origin.lat`, `world.origin.lon`, `world.origin.alt`만 있고, timeout과 주기 같은 튜닝 값은 노드 선언 기본값에 둔다. 표적이 있으면 표적 어댑터의 params `params/targets.yaml`(궤적 정의를 ROS 2 파라미터로 담을 수 있게 표적별 배열로 평탄화한 것)도 생성한다. `stack.json`의 기체 항목은 `vehicle_id`, `params_file`, `executor_node`(Executor의 노드 FQN. healthcheck와 진단용)를 싣고, `services.ops`와 `startup.node_stages`가 운용 노드 서비스와 기동 단계를 적는다. 생성 스크립트는 `ros-ws` 컨테이너 안에서 실행하고(PyYAML을 호스트에 요구하지 않는다) 호스트 진입점은 `tools/gen_compose.sh`, 생성과 compose 호출을 묶은 편의 스크립트는 `tools/sim_stack.sh`다. Phase 1에서 기체 1대짜리로 시작하고 Phase 3에서 같은 스크립트로 3대를 만든다.
- 노드는 네임스페이스와 sysid를 params(`stack.json`에서 생성)로 받고, 수신한 `vehicle_status`의 `system_id`, `component_id`와 대조한다. 위 파생 규칙(N+1 등)을 노드 코드에서 다시 계산하지 않는다. 빈 네임스페이스와 `target_system` 0은 `idsim_common`의 타입이 만들지 못하게 막는다. 대조가 어긋나면 오류이고, `vehicle_status`를 아직 받지 못한 동안은 명령만 보류한다. Executor에서 이 게이트는 goal의 준비 단계(PREPARING)에 있고, 발행을 시작하기 전의 불일치는 NOT_READY, 시작한 뒤의 불일치는 REASON_INTERNAL로 끝난다. 노드는 configure 때 `vehicle.*` 누락이나 서로 맞지 않는 값, `use_sim_time` false를 거부한다.
- 계약 메시지에 실리는 기체 식별자 `vehicle_id`는 기체 네임스페이스에서 앞의 "/"를 뗀 문자열이다(`px4_N`). 생성 스크립트가 `stack.json`의 기체 항목과 노드 params(`vehicle.id`)에 직접 싣고, 노드와 테스트는 계산하지 않고 읽는다. `idsim_common`의 함수는 변환이 아니라 대조를 한다(노드의 네임스페이스가 "/" + `vehicle_id`인지, 토큰이 하나인지). 소비자는 `vehicle_id`의 내용을 해석하지 않는다(N을 뽑거나 sysid를 계산하지 않는다).
- `world.origin`은 필수이고(생성 스크립트가 누락을 거부한다) 원점의 유일한 출처다. 생성 스크립트가 `world.template`의 월드에 `world.name`과 이 값의 `<spherical_coordinates>`(heading 0, ENU)를 넣은 월드 SDF를 실행 디렉터리에 만들며(`artifacts/runs/<실행 id>/world/<월드>.sdf`. 표적마다 `<actor>`도 여기에 더한다), gazebo 서비스는 그 파일을 연다(embedded 변형에서는 PX4가 이미지 안의 월드를 직접 열므로 월드 SDF를 만들지 않는다). 그래서 원점은 월드가 로드될 때 들어가고, 런타임에 원점을 설정하는 경로는 없다. 생성 스크립트는 `world.origin`과 기체의 스폰 pose, GNSS 센서 높이로 기체별 기대 GPS를 계산해 `stack.json`의 `vehicles[].expect_gps`에 싣고, 스모크의 원점 판정이 이 값을 쓴다(운용 변환이 아니라 판정 기대값이다). 템플릿은 원점, Actor, 월드 직속 `<plugin>`, `<include>`를 갖지 않는다(생성 스크립트가 거부한다). Mission Executor는 같은 값을 params(`ops-N`의 `world.origin`)로 받아 configure에서 누락을 거부한다. 표적 어댑터는 원점을 받지 않고 world ENU만 낸다. 원점은 메시지에 싣지 않는다. 기체의 스폰 pose는 운용 노드에 주지 않고 통합 테스트의 교차 검증에만 쓴다(Gazebo에만 있는 지식이다).

## 기술 스택 선정 근거

x86_64 Linux와 arm64 Linux 호스트(개발은 Apple Silicon Mac도 된다. 아래 "개발 호스트") 위에서 Ubuntu 24.04 + ROS 2 Jazzy + PX4 정식 릴리스 태그(v1.17.0) + Gazebo Harmonic + uXRCE-DDS 조합을 표준으로 잡는다. PX4 공식 문서의 예제는 아직 Humble + 22.04 기준이지만, [px4_msgs](https://index.ros.org/p/px4_msgs/) CI가 Jazzy를 함께 빌드하고 Jazzy의 기본 Gazebo가 Harmonic이라 조합이 자연스럽다. v1.16 알파 시절 Jazzy + 24.04에서 gz_bridge 클럭 timeout 보고([PX4 #24159](https://github.com/PX4/PX4-Autopilot/issues/24159))가 있었으므로 PX4는 알파, main 대신 릴리스 태그로 고정하고, Phase 1 첫 단계를 이 조합의 스모크 테스트로 잡는다.

| 구성 요소 | 선택 | 이유, 대안 |
| --- | --- | --- |
| 호스트 / OS / ROS 2 | x86_64 Linux와 arm64 Linux 호스트(개발은 arm64 Mac도), Ubuntu 24.04, ROS 2 Jazzy | [PX4 ROS 2 가이드](https://docs.px4.io/main/en/ros2/user_guide) 예제는 Humble 기준이라 명령어를 따를 때 humble -> jazzy 치환. Jazzy는 LTS 2029년까지(Humble은 2027). px4_msgs는 Humble, Jazzy 모두 CI 빌드. 컨테이너 안에서 돌리므로 호스트 배포판은 무관하다. 이미지는 linux/amd64와 linux/arm64 두 플랫폼으로 빌드되고 CI와 판정의 기준은 x86_64 Linux runner와 arm64 Linux runner 둘이다 |
| ROS 2 미들웨어 | CycloneDDS (`rmw_cyclonedds_cpp`), 모든 ROS 2 컨테이너에 `RMW_IMPLEMENTATION`으로 고정 | 기체 안의 ROS 2 버스에 쓰는 미들웨어다. 지상 링크에는 쓰지 않는다(아래 행). Jazzy 기본 FastDDS는 같은 호스트로 판단되는 참가자끼리 공유 메모리 전송을 시도해, 컨테이너마다 `/dev/shm`이 다르면 "토픽은 보이는데 데이터가 안 온다"가 된다. CycloneDDS는 기본이 UDP 전용이라 이 함정이 없고, 설정 파일 하나로 peer와 multicast를 제어하기 쉽다. uXRCE-DDS Agent는 내부적으로 FastDDS를 쓰지만 표준 RTPS로 CycloneDDS 노드와 통신한다. 단 Agent는 호스트 인터페이스 주소만 광고하므로 Cyclone 쪽에서 인터페이스를 lo로 고정하면 Agent를 찾지 못한다(실측). `config/cyclonedds.xml`은 인터페이스를 고정하지 않고 unicast peer 127.0.0.1과 multicast 끔만 둔다 |
| 지상 링크(지상국 <-> 기체) | Zenoh. 구성(bridge의 종류, router의 위치, 건네는 토픽을 제한하는 방법)과 버전은 정하지 않음 | 지상국과 모든 기체를 한 DDS 도메인에 두면 참가자마다 나머지 전부의 endpoint 정보를 교환하므로 discovery의 통신량과 메모리가 기체 수에 따라 가파르게 늘고, multicast가 약하고 링크가 흔들리는 무선 구간에서는 더 나빠진다. 그래서 기체의 ROS 2 버스(DDS)는 기체 안에 두고 무선 구간에는 DDS를 쓰지 않는다. 이것은 DDS의 일반적인 동작에 근거한 판단이고 이 저장소에서 측정하지 않았다. Zenoh에는 ROS 2의 토픽, service, action을 중계하는 bridge([zenoh-plugin-ros2dds](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds))가 있다. 그래서 고정된 계약(`ExecuteMission`)을 다른 형식으로 다시 정의하지 않고 건네고, 건네는 토픽을 계약으로 제한하고, 같은 구성을 시뮬레이션에서 재현하는 것을 기대한다. 이 계약과 QoS가 bridge를 그대로 건너는지는 확인하지 않았다. 대안 MQTT는 action에 해당하는 것이 없어 goal, feedback, result, cancel을 따로 설계해야 하고 TCP 기반이라 고르지 않는다. MQTT는 외부 telemetry 연동용 확장 후보로 남는다 |
| 비행제어 | PX4 SITL, 정식 릴리스 태그 고정 (v1.17.0) | uXRCE-DDS는 v1.14부터 지원. px4_msgs는 펌웨어와 같은 release/1.17 브랜치의 커밋 SHA로 고정. v1.17.0은 메시지 버저닝 범위가 가장 넓어 토픽 매핑 설계를 가장 세게 시험한다. 태그를 올릴 때는 스모크 golden 단계 통과가 조건이다 |
| 시뮬레이터 | Gazebo Harmonic (gz sim), x500 모델 | [PX4 Gazebo 문서](https://docs.px4.io/main/en/sim_gazebo_gz/) 기본값. `gz sim -s`(서버 전용)로 GUI 없이 실행 가능해 CI에 적합. 센서 변형(x500_depth, x500_gimbal 등)으로 확장 |
| PX4 <-> ROS 2 bridge | uXRCE-DDS (Micro XRCE-DDS Agent v2.4.3) | PX4 uORB 토픽이 `/fmu/out/*`, `/fmu/in/*`로 직접 노출. v2.4.3은 PX4 문서의 Jazzy 권장 버전이며 v3.x는 PX4 재빌드가 필요해 쓰지 않는다. 대안 MAVROS는 MAVLink 경유라 지연과 변환이 한 겹 더 있고 PX4 쪽 기본 경로가 아님 |
| GCS 연동 | MAVLink UDP | 외부 GCS용 포트. idsim은 GCS 프로그램을 제공하지 않는다. PX4 SITL은 한 스택 안의 모든 인스턴스가 GCS용으로 공통 14550 + 1000k로 보내고 온보드 API(MAVSDK)용으로 14540 + 1000k + N을 연다. 포트는 px4 이미지가 PATH 앞에 두는 idsim용 `px4-rc.mavlink`(저장소 `docker/px4/px4-rc.mavlink`)가 정하며(상류 파일은 환경변수로 바꿀 수 없다) payload와 gimbal 링크는 열지 않는다. `MAV_SYS_ID`가 스택 간에 같으므로 외부 GCS 하나는 한 번에 한 스택만 본다. SITL 파라미터 `COM_RC_IN_MODE`가 4라 GCS의 수동 모드와 가상 조이스틱은 쓸 수 없다. 커스텀 Fleet UI는 이번 범위 밖 |
| 토픽 시각화 | Lichtblick(Foxglove 호환 오픈소스 뷰어, MPL) + foxglove_bridge, compose `viz` 프로필 | 실시간 토픽과 MCAP 기록물을 브라우저에서 플롯과 3D로 본다. 계정 없이 로컬에서 쓸 수 있고 공식 이미지를 digest로 고정할 수 있어 공식 Foxglove 앱 대신 쓴다. foxglove_bridge 3.x는 서브프로토콜 foxglove.sdk.v1만 받고 Lichtblick은 이를 제시한다. bridge는 읽기 전용으로 구성해 토픽 버스에 쓰지 못한다 |
| 서비스 간 API | gRPC + Protobuf | Fleet Manager의 외부 API만 gRPC로, 내부는 ROS 2 토픽/서비스/action(지상 링크에서는 Zenoh가 이를 건넨다) |
| 로깅 | rosbag2 + MCAP 스토리지, PX4 ULog | MCAP은 단일 파일, 인덱스, 압축 지원, Lichtblick으로 바로 열림. ULog는 PX4 내부 상태의 원본 |
| 언어 | 핵심 노드 C++17 (rclcpp), 도구, 테스트, 어댑터 Python (rclpy, pytest), 브라우저 gateway Rust | Linux C++ 기반. 테스트는 GoogleTest(단위) + pytest(통합). 기록물 인덱스 CLI, 시나리오 runner, Phase 2의 임시 WebSocket 어댑터는 Python. Rust는 ROS 2에 의존하지 않는 컴포넌트에만 쓴다. 현재는 Phase 3의 브라우저 gateway 하나 |
| 컨테이너 | Docker Compose, 다중 컨테이너 | Phase 별 컨테이너 추가. Kubernetes는 확장 단계 |

주의할 점 세 가지. 첫째, PX4 토픽을 구독하는 ROS 2 노드는 `rmw_qos_profile_sensor_data` 기반 QoS를 명시해야 한다(기본 QoS로는 수신 안 됨). 둘째, 좌표계는 PX4가 NED/FRD, ROS와 Gazebo가 ENU/FLU라 `TrajectorySetpoint`을 보낼 때와 표적 pose를 setpoint로 바꿀 때 모두 변환이 필요하다. 셋째, PX4 v1.16부터 메시지 버저닝이 도입되어 일부 토픽 이름에 `_v<N>` 접미사가 붙으므로, 노드는 토픽 이름을 하드코딩하지 않고 `idsim_common`의 매핑을 통해서만 얻는다. 매핑은 golden의 토픽 전부를 담은 기술자 목록 하나이고, key는 방향(/fmu/in, /fmu/out)과 논리 이름이다. px4_msgs 타입은 기술자에 묶여 호출자가 따로 고르지 않으며, 접미사는 타입의 `MESSAGE_VERSION` 상수에서 컴파일 시점에 파생한다(상수가 없거나 0이면 접미사 없음). 손으로 쓴 태그별 접미사 테이블은 두지 않는다. /fmu/in 기술자는 기본이 발행 차단이고 공개 API로 발행할 수 있는 것은 허용 목록(지금은 `offboard_control_mode`, `trajectory_setpoint`, `vehicle_command`)뿐이다. 허용 목록에 토픽을 더하려면 기술자 변경, PX4 인터페이스 owner의 승인, PR 본문에 적은 허용 근거, 허용 목록 기대 집합을 비교하는 단위 테스트의 갱신, `docs/interface.md`의 공개 /fmu/in 목록 갱신이 한 PR에 함께 있어야 한다. 이 차단은 실수 방지 수준이며 보안 경계가 아니다(의도적인 우회는 lint와 코드 리뷰로만 잡는다). 대신 스모크 테스트가 저장한 golden 토픽 목록(`tests/fixtures/px4/<PX4_TAG>/`)과 매핑 결과를 단위 테스트가 비교해, 태그를 올릴 때 이 테스트가 먼저 깨지게 한다. 이 문서와 로드맵에서도 접미사가 붙은 토픽 이름을 적지 않는다. 이 세 가지를 Phase 1에서 공통 라이브러리로 감싸는 것이 이후 모든 노드의 토대가 된다.

## 핵심 기술 간단 소개

이 프로젝트에 등장하는 기술을 "무엇이고, 여기서 어떤 역할인지"만 압축한다. DDS와 shared memory IPC는 이미 익숙한 영역이라 PX4 생태계 쪽 용어 위주로 정리했다.

| 기술 | 무엇인가 | 이 프로젝트에서의 역할 |
| --- | --- | --- |
| [PX4](https://docs.px4.io/main/en/) | 오픈소스 비행제어 스택(자세, 위치 제어, 상태 추정, failsafe, 미션 실행). 내부 모듈은 uORB라는 pub/sub 메시징으로 통신한다. 보통 Pixhawk 계열 FMU에 올리는 펌웨어 | 기체의 "두뇌". 우리 코드는 PX4를 수정하지 않고 외부에서 명령, setpoint를 주고 상태를 받는다 |
| PX4 SITL | Software-In-The-Loop. PX4 펌웨어를 하드웨어 없이 Linux 프로세스로 빌드해 실행하고, 센서 입력, 모터 출력을 시뮬레이터와 주고받는 모드. 실기체와 같은 코드 경로가 돌아간다. `-i N`으로 인스턴스를 여러 개 띄울 수 있다 | FMU의 PX4를 대신하는 프로세스(기체마다 컨테이너 하나). 기체 한 대 = SITL 프로세스 하나 |
| [Gazebo (gz sim)](https://gazebosim.org/) | OSRF의 로봇 물리 시뮬레이터. 강체 물리, 센서(카메라, IMU, GPS, 라이다) plugin, SDF 모델 형식. "Gazebo Classic"(구버전, 11.x)과 새 세대 "gz"(Fortress/Garden/Harmonic)는 다른 코드베이스다 | x500 기체 모델의 물리와 센서, 이동 표적 Actor, 월드. PX4와는 gz-transport로 직접 연결 |
| [uORB](https://docs.px4.io/main/en/middleware/uorb.html) | PX4 내부의 경량 pub/sub 메시징. 토픽당 고정 구조체(`.msg`), 공유 메모리 기반 | 직접 만지지 않지만, ROS 2에서 보이는 `/fmu/out/*` 토픽이 결국 uORB 메시지다 |
| [uXRCE-DDS](https://docs.px4.io/main/en/middleware/uxrce_dds) | eProsima의 Micro XRCE-DDS(DDS for eXtremely Resource Constrained Environments) 위에 만든 PX4 <-> ROS 2 bridge. PX4 쪽 "client"가 uORB 토픽을 직렬화해 UDP/시리얼로 "agent"에 보내고, agent가 이를 진짜 DDS 토픽으로 발행한다. ROS 2 쪽에서는 일반 토픽처럼 보인다. px4_msgs 패키지가 메시지 타입을 제공 | PX4와 운용 서비스를 잇는 유일한 데이터 경로. 지금의 compose는 agent 하나가 모든 SITL 인스턴스를 수용하고, 기체가 여러 대가 될 때 기체마다 하나로 바꾼다(Phase 3) |
| [CycloneDDS](https://cyclonedds.io/) | Eclipse의 DDS 구현. ROS 2에서는 `rmw_cyclonedds_cpp`로 쓴다. 기본 전송이 UDP이고 XML 설정으로 인터페이스, peer, multicast를 제어 | 모든 ROS 2 노드의 rmw. 컨테이너 간 통신을 UDP로 단순화 |
| [Zenoh](https://zenoh.io/) | Eclipse의 pub/sub, query 프로토콜과 그 구현. discovery의 부담이 DDS보다 작다고 알려져 있으나 이 저장소에서 측정하지 않았다. ROS 2(DDS)의 토픽, service, action을 Zenoh로 중계하는 bridge([zenoh-plugin-ros2dds](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds))가 있다 | 지상 링크. 지상국의 Fleet Manager와 기체 운용 노드 사이에서 계약(`ExecuteMission`, `VehicleState`, `MissionEvent`)을 건넨다. 기체 안의 버스는 DDS 그대로다. 구성은 정하지 않음 |
| [MAVLink](https://mavlink.io/en/) | 드론 <-> GCS 통신용 경량 메시지 프로토콜(바이너리, 최대 280바이트 패킷, XML로 메시지 정의). telemetry, 명령, 미션 업로드, 파라미터 등 업계 표준. PX4, ArduPilot이 모두 사용 | 외부 GCS 연동(GCS 포트 UDP 14550 + 1000k, 스택 안 전 인스턴스 공통) 전용. 필요하면 MAVSDK로 온보드 API 포트(14540 + 1000k + N)에 보조 경로를 만들 수 있지만 주 경로는 uXRCE-DDS |
| Offboard 모드 | PX4 비행 모드 중 하나. 외부 컴퓨터가 위치/속도/자세 setpoint를 주기적으로 보내면 PX4가 그걸 따른다. setpoint가 `COM_OF_LOSS_T`(기본 1 s) 이상 끊기면 `COM_OBL_RC_ACT`가 정한 failsafe 동작으로 넘어간다 | 미션 노드가 기체를 움직이는 방식. `OffboardControlMode` + `TrajectorySetpoint`를 계속 발행. `COM_OBL_RC_ACT`는 SITL 시작 파라미터로 명시해 failsafe 동작을 결정적으로 만든다 |
| [ros_gz_bridge](https://github.com/gazebosim/ros_gz) | Gazebo의 gz-transport 토픽과 ROS 2 토픽을 양방향 변환하는 bridge | `/clock`을 ROS 2로 노출. 확장 단계에서 카메라 영상도 같은 경로 |
| Gazebo Actor | 물리 연산 없이 스크립트 궤적을 따라 움직이는 애니메이션 엔티티. 시뮬레이션 시간 기준으로 결정적 | 이동 표적의 화면 확인용. 표적 위치의 원천은 `fleet.yaml`의 궤적 정의이고, 생성 스크립트가 같은 정의로 Actor를 만든다. 물리 비용이 없다 |
| [rosbag2 / MCAP](https://mcap.dev/) | rosbag2는 ROS 2 토픽 기록, 재생 도구. MCAP은 Foxglove가 만든 컨테이너 포맷으로 단일 파일, 인덱스, 압축, 스키마 내장. Jazzy의 rosbag2 기본 스토리지 | 로그/replay의 저장 형식 |
| [ULog](https://docs.px4.io/main/en/dev_log/ulog_file_format.html) | PX4 자체 로그 포맷. uORB 토픽을 고주파로 기록. Flight Review, pyulog로 분석 | PX4 내부 상태의 원본. rosbag과 시간 정렬해 함께 보관 |
| [Lichtblick](https://github.com/lichtblick-suite/lichtblick) + [foxglove_bridge](https://github.com/foxglove/ros-foxglove-bridge) | Lichtblick은 Foxglove Studio에서 갈라진 오픈소스(MPL) 시각화 도구(브라우저/데스크톱). 3D, 플롯, 이미지, 지도 패널. foxglove_bridge는 ROS 2 토픽을 WebSocket으로 내보내는 ROS 패키지 | 실시간 토픽 플롯(Offboard 디버깅), 기록물 열람과 replay 검증. compose `viz` 프로필로만 올린다 |
| gRPC / Protobuf | Google의 스키마 기반 직렬화(Protobuf) + 그 위의 RPC 프레임워크(HTTP/2, 스트리밍 지원) | Fleet Manager의 외부 API. ROS 2 없는 클라이언트(웹, 다른 서비스)가 플릿을 조회, 명령하는 경로 |
| 브라우저 gateway (Rust) | gRPC 클라이언트(tonic)와 WebSocket/HTTP 서버(axum)를 한 바이너리에 담은 작은 서비스. ROS 2를 전혀 모른다 | 브라우저는 gRPC를 직접 못 부르므로, Fleet Manager의 두 스트림을 WebSocket으로 중계하고 미션 제출과 중단을 HTTP JSON으로 받아 gRPC로 넘긴다. 정적 페이지도 여기서 서빙 |

## 인터페이스 계약

운용 서비스끼리(Fleet Manager와 기체 운용 노드), 그리고 표적 생산자와 운용 서비스 사이의 계약은 `idsim_interfaces`와 `docs/interface.md`가 정의한다. 운용 서비스와 기체 레이어(PX4) 사이는 px4_msgs의 `/fmu` 토픽이고, 쓰는 범위와 규칙은 `docs/interface.md`에 있다. 정의 파일(msg 10개, action 1개)은 모두 있고, 고정은 첫 소비자가 생기는 Phase의 완료에 맞춘다. 소비자 없이 고정하면 틀린 정의를 계약으로 굳히게 되기 때문이다.

| 묶음 | 고정되는 것 | 고정 상태 |
| --- | --- | --- |
| 공통 규칙 | 단위, 좌표계, 시각, NaN 금지, 이름 규칙, QoS 계약, 변경 절차 | 고정 |
| 미션 실행 | `ExecuteMission.action`, `Mission`, `MissionItem`, `YawSetpoint`, `TakeoffItem`, `LoiterItem`, `GoToItem`, `TrackEntityItem`의 직접 필드와 상수. TAKEOFF, LOITER, LAND, GOTO, TRACK_ENTITY, RTL 항목의 의미, 항목 순서 규칙(TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만), 수락 정책, 취소 의미, 공중 Offboard 진입, `reason` 값의 의미(`REASON_TARGET_LOST` 포함), 공중에서 끝나는 미션(마지막 항목이 setpoint 항목)의 종료 단계 | 고정 |
| 표적 | `TargetState` | 고정 |
| 기체 요약 | `VehicleState` | 고정 전(Phase 2 완료에 고정. WebSocket JSON 스키마 고정과 함께) |
| 미션 기록 | `MissionEvent` | 고정 전(Phase 2 완료에 고정. 기록물 인덱스가 필드를 검증한 뒤) |

"고정"의 정의.

- 고정의 단위는 타입이 아니라 파일이다. 한 파일이 고정되면 그 파일의 직접 필드(이름, 타입, 순서, 기본값)와 상수(이름, 값), 그리고 `docs/interface.md`에 적힌 그 필드의 의미가 고정된다. 중첩된 타입의 내용은 그 타입의 파일이 고정될 때 고정된다.
- 중첩 타입이 바뀌면 그것을 담은 타입의 type hash(RIHS01)와 `ros2 interface show` 출력도 바뀐다. 이 전파는 상위 타입의 변경으로 보지 않는다. 전파가 허용되는 것은 그 중첩 타입이 고정되기 전까지다.
- 판정은 `idsim_interfaces`의 계약 테스트가 한다. golden은 세 종류다. type hash, 펼친 정의(`ros2 interface show` 출력. hash가 잡지 못하는 상수 값과 기본값 변경을 잡는다), 직접 정의(그 파일의 직접 필드와 상수만). 고정된 파일의 직접 정의 golden이 바뀌면 고정된 계약의 변경이고, 앞의 둘만 바뀌면 중첩 타입에서 온 전파다.
- 상수(enum 값, 비트, 이름)는 고정 전후 모두 추가만 한다. 상수의 의미는 그 상수를 처음 쓰는 소비자가 생기는 묶음과 함께 고정된다.
- 고정 전인 파일은 첫 소비자의 구현에서 드러난 문제에 한해 바꿀 수 있고, 고정 뒤에는 새 요구가 있어야 한다. 어느 쪽이든 아래 변경 절차를 따른다.
- 의미 문장 중 실측이나 소스로 확인하지 않은 경계 상황의 기체 동작은 `docs/interface.md`에 "미확인"으로 표시하고 그때 노드가 택하는 보수적 동작을 함께 적는다. 미확인 표시는 고정을 막지 않고, 관찰된 문제가 그 동작을 반증하면 위 절차로 고친다.

정의별 계약의 요지. 필드 단위의 전체 계약은 `docs/interface.md`에 둔다.

- 공통 규칙: 단위는 SI이고 스칼라 필드 이름에 단위 접미사를 붙인다. 계약 프레임은 `"world"` 하나다. 원점은 `config/fleet.yaml`의 `world.origin`이 가리키는 점(Gazebo 월드 (0, 0, 0))이고, 축은 x 동, y 북, z 위(ENU), yaw는 ENU yaw(동 0, 반시계 양, `[-pi, pi)`)다. 기체 로컬 NED와 위경도는 미션과 표적 계약에 나오지 않는다(`VehicleState`만 지도 표시용으로 WGS84를 함께 싣는다). world ENU <-> 기체 로컬 NED 변환은 `idsim_common` 한 곳에 두고, PX4가 실제로 쓰는 원점(`vehicle_local_position`의 기준점)과 params로 받은 `world.origin`을 입력으로 한다. world ENU의 z는 `world.origin`의 접평면 위 높이이고 타원체 고가 아니다(원점에서 먼 곳에서는 같은 z가 지면 위 높이와 달라진다). NaN과 무한대는 어떤 필드에도 넣지 않고, 값이 없으면 `*_valid`가 false이고 값은 0이다. enum은 uint8 상수이고 0은 "모름 또는 무효"다. PX4의 enum 값과 PX4 timestamp는 계약에 넣지 않는다. 이름의 고정 부분(토픽, action, 프레임 이름)은 메시지의 string 상수로 두어 C++ 노드와 Python 판정 코드가 같은 출처를 쓴다.
- `VehicleState.msg`: 기체 요약 상태. 토픽은 기체별 `/<vehicle_id>/vehicle_state`이고 공통 토픽은 두지 않는다(ROS 2 메시지에는 key가 없어 한 토픽의 발행자들이 구독자의 history depth를 나눠 쓴다). Telemetry Collector가 만들고 Fleet Manager, WebSocket, 테스트가 소비한다. 불변식: 발행자는 `vehicle_status`와의 식별 대조가 맞고 `vehicle_status`가 신선한 동안에만 발행한다. 따라서 메시지가 오면 비행제어 상태(arm, 모드, failsafe)는 신선하고, 이탈 판정은 소비자의 미수신 timeout 한 경로다. 발행 중단은 `vehicle_status`만 본다. 위치, 자세, 측지 좌표, 배터리, 지상 판정의 원천이 묵으면 해당 `*_valid`를 false로 하고 묵은 값을 valid로 내보내지 않는다. 소비자는 메시지의 `vehicle_id`를 토픽 네임스페이스와 대조하고, 그래프 항목의 생성과 소멸로 등록이나 이탈을 판정하지 않는다. 발행 timer와 신선도 검사는 ROS 시각 기준이다. replay에서는 기록물 안의 `vehicle_state`를 재생하지 않는다(Collector가 다시 만든다). Protobuf의 `VehicleState`와 중첩 타입까지 멤버 단위로 1:1 대응하며, 변환은 `idsim_fleet`의 변환 모듈 한 곳에서만 하고 양방향 왕복 단위 테스트를 둔다.
- `TargetState.msg`: 표적 id, world ENU 위치와 속도, 시각. 시뮬레이터 비의존 계약이고 토픽은 `/targets/<target_id>/state`다. `header.stamp`는 발행 시각이 아니라 그 상태가 유효한 ROS 시각(`use_sim_time`이면 `/clock`)이며, 같은 표적에서 단조 증가한다. `velocity_valid`는 언제든 false일 수 있다. 소실 플래그는 없고, 소실은 발행 중단으로 표현하며 소비자가 stamp의 나이로 판정한다. 소비자에게 정본은 `TargetState`다. 소비자는 `frame_id`가 `world`가 아닌 표본과 값이 비유한인 표본을 버리고, Executor는 위치 성분의 절댓값이 1e5 m를 넘는 표본도 버린다.
- `Mission.msg`, `MissionItem.msg`와 `ExecuteMission.action`: 미션은 항목의 목록이고 항목은 type과 그 type의 서브메시지 하나로 이뤄진다. 항목은 두 부류로 나뉜다. Offboard setpoint로 처리하는 항목(takeoff, goto, track_entity, loiter)과 PX4 고유 모드로 전환하는 명령 항목(rtl, land). 이 구분은 필드로 두지 않고 type에서 파생한다. 명령 항목은 Offboard를 벗어나므로 상태기가 `vehicle_status.nav_state`로 전이를 추적하고, 항목 순서 규칙이 TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만 오게 하므로 명령 항목 뒤에 setpoint 항목이 없고 미션 중간의 Offboard 재진입은 없다(반복 비행은 미션 둘로 보낸다). action 이름은 `/<vehicle_id>/execute_mission`이다.
  - 수락 정책: Executor는 판단할 수 있는 goal을 모두 수락하고, 받을 수 없으면(미션 무효, `vehicle_id` 불일치, 실행 중, 준비 안 됨) 즉시 ABORTED로 끝내며 result의 `reason`에 이유를 싣는다. 거절은 쓰지 않는다(ROS 2 action의 거절은 이유를 실을 수 없다). 실행 중인 goal은 선점하지 않는다. 성공, 중단, 취소의 정본은 action의 GoalStatus다.
  - 취소: 상황(failsafe 동작 중, LAND와 RTL 항목 중 포함)을 가리지 않고 같은 분기로 처리하고 결과로 가른다. 공중(PX4의 착륙 판정 `landed` false)이면 setpoint 발행을 유지한 채 Hold 모드 명령을 보내고, Hold를 처음 관측하면 발행을 멈추며, 확인되면 CANCELED로 끝낸다. Hold 명령이 거부되거나 정해진 시간 안에 확인되지 않으면 Land 명령을 보내고 ABORTED(`REASON_MODE_SWITCH_FAILED`)로 끝낸다. 지상(`landed` true)에서 arm 상태이면 강제가 아닌 disarm을 확인한 뒤 CANCELED로 끝내고, 정해진 시간 안에 확인되지 않으면 ABORTED(`REASON_DISARM_FAILED`. 기체가 지상에 arm 상태로 남았을 수 있다)다. 이 goal에서 arm을 한 번이라도 보냈으면 지상에서 DISARMED로 보여도 같은 disarm 확인을 거치고, 대기 중 지상 판정이 풀리면 공중 분기로 넘어간다. CANCELED로 끝난 기체는 공중에 Hold(ARMED)로 남거나 지상 disarm이다. Hold로 끝난 기체는 지면 근처이거나 땅에 닿아 있어도 스스로 내려앉거나 disarm되지 않고 ARMED로 머문다. 그 기체를 내리는 것은 취소를 요청한 쪽의 책임이다(`[LAND]` 한 항목 미션을 보낸다). 취소의 분기는 고정이다.
  - 정리의 상한: 정리(취소, setpoint 항목의 ITEM_TIMEOUT과 TARGET_LOST, 준비 단계의 실패, RTL 항목의 실패)와 공중 종료 단계는 분기를 오가도 시작부터 `max(hold_confirm_timeout + 3 x mode_confirm_timeout, hold_confirm_timeout + land_disarm_fallback_delay + mode_confirm_timeout)`(기본 12 s. 노드 파라미터가 아닌 파생값) 안에 끝난다. 앞 항은 정리의 가장 긴 경로이고 뒤 항은 공중 종료 단계의 지상 경로라 정당한 경로를 자르지 않는다. 상한에 닿으면 지상에서는 disarm을, 공중에서는 Land 명령을 한 번 보내고 끝낸다. 취소이면 각각 `REASON_DISARM_FAILED`와 `REASON_MODE_SWITCH_FAILED`이고 공중 종료 단계는 둘 다 `REASON_MODE_SWITCH_FAILED`, 그 밖의 정리는 원래 reason을 유지한다.
  - 비행 중 감시: 이 goal의 arm 뒤 ARMED를 처음 관측한 다음부터(공중 Offboard 진입은 발행을 시작한 때부터)는 첫 항목을 시작하기 전이라도 감시가 적용되어 `REASON_FAILSAFE`, `REASON_EXTERNAL_MODE_CHANGE`, `REASON_EXTERNAL_DISARM`, `REASON_LINK_LOST`가 준비 단계(`last_item_index` 0)에서도 나온다. `REASON_EXTERNAL_DISARM`은 setpoint 항목 실행 중이거나 그 앞의 준비 중에 Executor가 보내지 않은 disarm이 지상에서 failsafe 없이 관측된 것이고 원인(외부 명령, PX4 자체의 disarm과 kill)은 판정하지 않는다.
  - 발행 규칙: Executor는 Offboard 진입 준비(모드 전환 전 최소 10회. 공중 Offboard 진입은 Hold 중에도 진입 setpoint를 발행한다)와 Offboard 동안에만 setpoint를 발행하고, Offboard가 아닌 모드(Hold, Land, failsafe 동작)를 관측하면 발행을 멈춘다. Offboard가 아닌 모드에서 setpoint를 발행하면 착륙 판정이 늦어지고 Hold가 끌리며, failsafe 뒤 발행을 재개하면 기체가 Offboard로 돌아가기 때문이다.
  - 공중 Offboard 진입: 첫 항목이 GOTO, TRACK_ENTITY, LOITER이면 기체가 이미 공중 Hold(ARMED, AUTO_LOITER, failsafe 없음)여야 한다. arm하지 않고 Hold 중에 현재 위치 setpoint를 발행한 뒤 Offboard로 전환하고, 전환 전부터 비행 중 감시를 적용한다. 첫 OFFBOARD 표본 전에는 AUTO_LOITER인 표본을 다른 주체의 모드 변경으로 보지 않는다.
  - GOTO와 TRACK_ENTITY: setpoint는 world ENU 점을 기체 로컬 NED로 바꾼 위치이고, TRACK_ENTITY는 표적 표본이 신선하면 표적 속도를 feedforward로 싣는다. 완료는 서로 다른 위치 표본 3개 연속으로 3차원 거리가 `acceptance_radius_m` 안일 때다. 표적 표본이 `target_timeout`을 넘겨 오지 않으면 `REASON_TARGET_LOST`로 정리를 거쳐 끝난다.
  - RTL 항목: 모드 명령 항목이고 LAND와 같은 규칙을 쓴다. 목적지는 PX4 home(그 기체가 마지막으로 arm하거나 이륙한 지점)이고 귀환과 착륙은 비행제어가 한다. RTL 명령이 거부되거나 AUTO_RTL이 확인되지 않으면 정리를 거쳐 Land로 모이고 ABORTED(`REASON_MODE_SWITCH_FAILED`)다.
  - 공중에서 끝나는 미션: 마지막 항목이 setpoint 항목이면 그 항목의 완료 뒤 종료 단계에서 Hold를 보내고, 공중 Hold를 3회 연속 확인하면 SUCCEEDED로 끝난다(기체는 공중 Hold로 남는다). 지상에서 끝났으면(마지막 목표가 지면에 닿아 PX4가 disarm한 경우 포함) 지상 DISARMED 확인으로 SUCCEEDED다. Hold가 거부되거나 확인되지 않으면 공중에서는 Land 경로로 ABORTED(`REASON_MODE_SWITCH_FAILED`)다. 마지막 목표가 지면 높이이면 결과는 보장하지 않는다.
- `MissionEvent.msg`: 미션 실행의 접수와 종료 기록. 토픽은 `/<vehicle_id>/mission_event`다. rosbag2(Jazzy)는 action의 goal과 result를 기록하지 않으므로, 기록물에서 미션 id와 결과를 읽을 일반 토픽을 따로 둔다. Executor가 goal마다 접수 때 한 번, 종료 때 한 번 발행한다. 정본은 action이고 이 메시지는 기록과 관찰을 위한 사본이며, Fleet Manager는 배분 판단에 쓰지 않는다. 사건 시각은 ROS 시각이다. 종료 사건 없이 접수만 남을 수 있고(Executor가 실행 중에 죽은 경우) 읽는 쪽은 결과 미상으로 다룬다.
- QoS: 계약은 reliability와 durability 둘뿐이고 history와 depth는 구현 값이다. 상태 토픽(`VehicleState`, `TargetState`)은 발행 RELIABLE, VOLATILE, 구독 BEST_EFFORT, VOLATILE이다. 구독이 BEST_EFFORT라 라이브와 rosbag2 재생의 어느 발행자와도 맞는다. 사건 토픽(`MissionEvent`)은 발행과 구독 모두 RELIABLE, VOLATILE이다. 그래서 늦게 붙은 구독자는 지난 사건을 받지 않으며, goal을 보내는 쪽은 사건 구독을 action client보다 먼저 같은 노드에서 만든다. DDS deadline과 liveliness로 신선도를 판정하지 않는다(벽시계 기준이다). 상태 토픽의 발행 주기는 계약이 아니다.
- 변경 절차: 메시지 안에 버전 필드나 버전 상수를 두지 않고, 타입 식별은 type hash가 한다. 필드는 끝에 추가만 하고 기존 필드의 이름, 타입, 의미, 단위를 바꾸지 않는다. 상수 값은 재사용하지 않는다. 예약 필드를 미리 두지 않는다. golden이 다르면 계약 테스트가 실패하고 자동 갱신은 하지 않는다. 계약 변경 PR에는 golden 갱신, `docs/interface.md`, (Phase 3 뒤) proto와 왕복 테스트, 영향받는 replay fixture 갱신이 함께 들어간다.
- PX4 토픽 이름과 QoS, 좌표 변환, 네임스페이스 검증과 sysid 대조는 `idsim_common`이 유일한 접근 경로이고, 네임스페이스와 sysid 값은 params로 받는다.
- fleet 파일의 key는 쓰이는 곳으로 둘로 나뉜다. 운용 쪽에도 쓰이는 것은 `vehicles[].id`(기체 식별의 출처)와 `world.origin`이다. `world.origin`은 월드 SDF의 `<spherical_coordinates>`와 운용 노드(`ops-N`)의 params `world.origin` 양쪽에 들어간다. 나머지(`airframe`, `pose`, `px4_params`, `world.name`, `world.template`, `world.speed_factor`, `targets`, `px4.params_file`, `px4.start`)는 시뮬레이션 전용이다. `targets`는 시뮬레이션의 표적 생산자가 쓰는 궤적 정의이고, `px4_params`와 `px4.params_file`의 값 가운데 미션 계약이 요구하는 것은 `docs/interface.md` "SITL 파라미터" 절의 분류가 가른다. 최상위 `schema`는 파일 형식의 판이고 어느 쪽에도 속하지 않는다. 파일 형식은 이 구분을 key 구조로 드러내지 않는다(`world.origin`이 `world` 아래에 있다).
- 시뮬레이션에서 시간의 정식 기준은 ROS 시각(`/clock`, 시뮬레이션 시간)이다. 실기체의 시간 출처는 정하지 않았다("전체 아키텍처" 절의 환경별 실체 표). 판정, 집계, 기록물 timestamp는 모두 이 시각을 쓴다. PX4 메시지의 timestamp 필드는 PX4 hrt 시각이고, SITL에서 hrt는 Gazebo 시뮬레이션 시간(us)이라 `/clock`, ULog와 같은 축이다(실측한 차이가 +8-20 ms라 큰 상수 오프셋은 없고, `/clock`은 전달 경로만큼 늦다. 두 gz 시계 토픽의 관계는 `docs/interface.md` "시간 기준" 절). 공통 SITL 파라미터 `UXRCE_DDS_SYNCT=0`은 uXRCE-DDS 세션의 시간 보정을 꺼 노드가 넣은 timestamp가 그대로 쓰이게 한다. 노드가 /fmu/in에 넣는 timestamp도 노드 시계의 시뮬레이션 시간(us)이고, 0과 벽시계 값은 보내지 않는다(`idsim_common`의 timestamp 타입이 시계에서만 값을 만든다). 그래도 판정 기준은 여전히 ROS 시각이고, PX4 timestamp는 ULog와의 정렬과 PX4 쪽의 묵은 setpoint 판정에 쓰인다. 이 값은 SITL 전용이다. 1로 되돌리면 /fmu/in과 /fmu/out의 timestamp 축이 바뀌므로 노드가 넣는 timestamp의 기준과 노드, Agent의 시계 조건이 함께 바뀌어야 한다(`docs/interface.md` "시간 기준" 절). 이와 별개로 운용 노드는 `/clock` 없이 돌지 않는다(Executor는 `use_sim_time`이 true가 아니면 configure를 거부한다). `/clock`의 공급 주체는 `bridge` 서비스의 ros_gz_bridge이며 bridge가 넘기는 토픽은 `/clock` 하나다(표적 상태와 정답 pose는 bridge를 거치지 않는다). 노드와 테스트 코드에서 벽시계를 쓰는 곳은 다음뿐이고 어느 것도 판정 기준이 아니다. (1) 환경 스모크 테스트의 timeout(`/clock` 공급 자체가 스모크의 판정 대상이다). (2) Executor의 activate에서 첫 `/clock` 수신 대기(2 s). (3) Executor가 자기 lifecycle 전이를 거는 일회 timer(`/clock`이 오기 전에도 전이를 시도하게 하는 trigger). (4) 통합 테스트 프로세스가 시작 직후 한 번 첫 `/clock` 수신을 기다리는 유예(15 s. 구독이 맺어지는 시간이다). (5) 통합 테스트 대기마다의 hang 방지 상한 `wall_cap`(ROS 시각 timeout x 3 + 10 s)과, 그때 `/clock`이 멈췄는지를 가르는 5 s. (6) CLI `send_mission`이 goal을 보내기 전에 action 서버를 기다리는 상한(`--server-timeout`, 기본 10 s). 넘으면 goal을 보내지 않고 끝나며, 이것은 미션의 결과가 아니다. (3)을 뺀 나머지는 hang 방지이고, (1), (2), (4), (5)는 넘으면 시간 판정이 아니라 시계 이상(`CLOCK_ABSENT`, `CLOCK_STALLED`, `CLOCK_SLOW`)으로 실패한다. 대기를 잘게 끊는 poll 간격(통합 테스트 지원 코드와 `send_mission`의 대기 반복)은 대기의 끝을 정하지 않으므로 이 목록에 넣지 않는다. 통합 테스트는 첫 수신 뒤 대기를 시작할 때 `/clock`이 없으면 즉시, 시각이 뒤로 가면 즉시(`CLOCK_BACKWARD`) 실패한다.
- PX4 토픽의 측정 주기는 계약이 아니라 참고값이다. 수신 판정은 "T초 안에 1회 이상"으로 정의하고 주기에 묶지 않는다. 주기 하한 계약은 Fleet 레지스트리 timeout을 정하는 Phase 3에서 필요한 토픽에만 넣는다.

## Docker Compose 실행 환경 설계

컨테이너는 "기체 한 대 = PX4 컨테이너 한 개" 단위로 나누고, 지금의 compose는 Gazebo와 Agent를 각각 하나씩만 띄우고, Agent는 기체가 여러 대가 될 때 기체마다 하나로 바꾼다(Phase 3). 모든 컨테이너는 `network_mode: host`로 돌려 DDS discovery와 UDP 포트 문제를 피한다. bridge 네트워크에서는 DDS discovery가 자주 깨진다. 같은 호스트에서 스택 두 개가 동시에 돌 수 있도록(개발자 둘, 병렬 CI job) `ROS_DOMAIN_ID`, `GZ_PARTITION`, Agent 포트, MAVLink 포트는 생성 인자인 스택 번호 k에서 파생해 compose 환경변수로 넘긴다. 스택 번호 k에 대해 `ROS_DOMAIN_ID` = 20 + k, Agent 포트 = 8888 + k, `GZ_PARTITION` = `idsim-<k>`, MAVLink 오프셋 = 1000k, foxglove 포트 = 8765 + k, lichtblick 포트 = 18080 + k. 지금의 compose는 스택 하나에 DDS 도메인 하나를 쓴다. 기체가 한 대이면 그 도메인이 곧 그 기체의 버스다. "전체 아키텍처" 절의 기체마다의 도메인, 기체마다의 Agent, Zenoh 지상 링크 구성은 들어 있지 않고 Phase 3에서 더한다. 기준값은 `fleet.yaml`이 아니라 생성 스크립트의 상수이며 `docs/interface.md`에 적는다. k는 0-9이고(MAVLink 로컬 포트 18579 + 1000k가 임시 포트 범위 아래에 있어야 한다) 생성 스크립트의 단위 테스트가 k 0-9, N 1-9 전 범위에서 포트 비충돌을 검사한다. DDS 포트 범위(7400 + 250 x 도메인부터 참가자 인덱스 50까지)와 MAVLink 포트는 이 범위에서 겹치지 않는다. DDS 설정이 인터페이스를 제한하지 않으므로 같은 호스트의 다른 ROS 2 스택과의 격리는 도메인 ID가 유일한 수단이며, 그래서 기본 도메인을 다른 프로젝트가 흔히 쓰는 0이 아닌 20으로 둔다. CI도 같은 규칙이다. `GZ_PARTITION`은 gz-transport 기본값에 기대지 않고 항상 명시한다. Agent에는 `ROS_DOMAIN_ID`를 주지 않는다. DDS 도메인은 PX4 client가 세션 생성 때 Agent에 넘기므로 px4 컨테이너에 ROS 컨테이너와 같은 `ROS_DOMAIN_ID`가 들어가야 한다. 모든 compose 파일은 `name:`으로 프로젝트 이름(`idsim-<k>`. 스모크도 생성된 파일을 쓰므로 같은 규칙)을 명시한다. 명시하지 않으면 디렉터리명이 프로젝트 이름이 되어 호스트의 다른 compose 프로젝트와 충돌한다. 이미지는 빌드에 쓴 버전을 `IDSIM_BUILD_<이름>` ENV(`<이름>`은 `versions.env` 항목 이름)로 남기고, 스모크와 테스트는 실행 전에 이 값을 `versions.env`와 대조한다.

컨테이너와 프로세스 구성. "전체 아키텍처" 절의 그림이 실행 주체와 장비, 주고받는 것을 보였다면 이 절의 그림은 시뮬레이션의 컨테이너 배치, 즉 어느 컨테이너에서 어떤 프로세스가 돌고 무슨 프로토콜로 이어지는지를 보인다. 그림은 계층으로 나눈다. 개요가 스택 하나(스택 번호 k)의 컨테이너 묶음만 보이고, 그 아래 상세 그림 넷이 개요의 상자를 하나씩 펼친다. 이 절의 그림에서 화살표는 데이터가 흐르는 방향이고, 점선 화살표는 판정과 CI가 쓰지 않는 경로이며, 점선 테두리는 표시한 Phase에서 더해지는 것이다. 포트, 환경변수, 이미지 같은 세부는 그림에 넣지 않고 그림 아래 표와 서비스 표에 둔다.

개요. 상자 하나가 컨테이너(compose 서비스)의 묶음이다.

```mermaid
flowchart TB
  SIM["시뮬레이션<br/>px4-N, gazebo"]
  LINK["Agent와 시뮬레이션 쪽 서비스<br/>xrce-agent, bridge, targets, sim-oracle"]
  DDS(["DDS 도메인"])
  ROS["운용과 판정<br/>ops-N, runner"]
  VIZ["viz 프로필<br/>gz-gui, foxglove, lichtblick"]
  HOST["호스트 도구<br/>브라우저, 외부 GCS"]
  EXT["Fleet Manager, gateway<br/>Phase 3"]

  SIM <--> LINK
  LINK <-->|"RTPS"| DDS
  DDS <--> ROS
  SIM <-.-> VIZ
  DDS -.-> VIZ
  VIZ -.-> HOST
  SIM <-.->|"MAVLink"| HOST
  DDS <-->|"지상 링크: Zenoh"| EXT
  EXT <--> HOST

  classDef later stroke-dasharray: 6 4
  class EXT later
```

- 스택은 호스트의 `tools/sim_stack.sh`가 올리고 내린다. 이 스크립트가 `tools/gen_compose.sh`로 compose 파일을 만든 뒤 `docker compose up --wait`를 단계별로 부르며, 그림에는 넣지 않았다.
- N이 붙은 컨테이너(`px4-N`, `ops-N`)는 fleet 파일의 기체마다 하나씩 생기고, `xrce-agent`, `gazebo`, `bridge`, `sim-oracle`은 스택에 하나씩이다. `targets`는 fleet 파일에 표적이 있을 때만 하나 생긴다. `runner`는 `tools` 프로필이라 상주하지 않는다.
- 본 스택의 컨테이너 사이 경로는 셋이다. PX4와 Agent 사이의 uXRCE-DDS(UDP), PX4, Gazebo, `bridge`, `sim-oracle` 사이의 gz-transport, 그리고 Agent와 ROS 2 프로세스가 함께 올라가는 DDS 도메인이다. 운용 노드와 판정 코드는 DDS 도메인만 본다.
- "DDS 도메인"은 프로세스가 아니라 참가자들이 만나는 버스다. Agent는 Fast DDS(기본 설정)로, ROS 2 프로세스는 CycloneDDS로 참가한다. multicast를 끄고 unicast peer 127.0.0.1로 discovery하는 것은 `config/cyclonedds.xml`을 읽는 CycloneDDS 쪽의 설정이다.
- 모든 컨테이너는 `network_mode: host`이고 compose 프로젝트 이름은 `idsim-k`다. 같은 호스트의 다른 스택은 k에서 파생한 값으로만 갈리며 네트워크 네임스페이스로는 격리되지 않는다.
- Fleet Manager는 DDS 도메인에 직접 붙지 않고 지상 링크(Zenoh)를 거친다. 둘 다 Phase 3에서 더해지고, 그때 "DDS 도메인"은 기체마다 하나가 된다. 그림의 나머지는 지금의 compose(스택에 도메인 하나)다.
- 그림은 `standalone` 변형이다. `embedded` 변형은 `xrce-agent`, `px4-1`, `runner`만 있고(`targets`와 `sim-oracle`도 없다) PX4가 Gazebo 서버를 자기 컨테이너 안에서 띄운다.

| k에서 파생하는 값 | 식 | 가르는 것 |
| --- | --- | --- |
| `ROS_DOMAIN_ID` | 20 + k | DDS 도메인 |
| `GZ_PARTITION` | `idsim-k` | gz-transport discovery |
| Agent 포트 | 8888 + k | uXRCE-DDS (UDP) |
| MAVLink 오프셋 | 1000k | GCS 포트 14550 + 1000k, API 포트 14540 + 1000k + N |
| foxglove 포트 | 8765 + k | WebSocket (127.0.0.1) |
| lichtblick 포트 | 18080 + k | HTTP (127.0.0.1) |

상세 1: 기체 1대의 시뮬레이션 경로. 개요의 "시뮬레이션"과 "Agent와 시뮬레이션 쪽 서비스" 상자를 펼친 것이다. `targets`는 Gazebo에 붙지 않고 궤적 정의만으로 표적을 내지만, 실기체에서는 없어지는 시뮬레이션 쪽 생산자라 같은 상자에 둔다. 바깥 상자는 컨테이너, 안쪽은 그 안의 프로세스 또는 PX4 모듈이다.

```mermaid
flowchart LR
  subgraph PXC["px4-N"]
    UX["uxrce_dds_client 모듈"]
    GB["gz_bridge 모듈"]
  end
  subgraph AGC["xrce-agent"]
    AGP["MicroXRCEAgent"]
  end
  subgraph GZC["gazebo"]
    GZP["gz sim 서버"]
  end
  subgraph BRC["bridge"]
    BRP["ros_gz_bridge"]
  end
  subgraph TGC["targets"]
    TA["표적 어댑터"]
  end
  subgraph ORC["sim-oracle"]
    ORP["정답 pose 노드"]
  end
  DDS1(["DDS 도메인"])

  UX <-->|"uXRCE-DDS"| AGP
  GB <-->|"gz-transport"| GZP
  AGP <-->|"RTPS"| DDS1
  GZP -->|"clock"| BRP
  GZP -->|"pose/info"| ORP
  BRP -->|"/clock"| DDS1
  DDS1 -->|"/clock"| TA
  TA -->|"TargetState"| DDS1
  ORP -->|"/sim/*/pose"| DDS1
```

| 경로 | 프로토콜 | 싣는 것 | 포트 또는 격리값 |
| --- | --- | --- | --- |
| `px4-N` <-> `xrce-agent` | uXRCE-DDS (UDP) | uORB 토픽 | 8888 + k |
| `px4-N` <-> `gazebo` | gz-transport | 모터 명령, 센서 | `GZ_PARTITION` `idsim-k` |
| `gazebo` -> `bridge` | gz-transport | clock | `GZ_PARTITION` `idsim-k` |
| `gazebo` -> `sim-oracle` | gz-transport | `/world/<월드>/pose/info` | `GZ_PARTITION` `idsim-k` |
| `xrce-agent` <-> DDS 도메인 | RTPS (Fast DDS) | `/px4_N/fmu/in`, `/px4_N/fmu/out` | 도메인 20 + k |
| `bridge` -> DDS 도메인 | RTPS (CycloneDDS) | `/clock` | 도메인 20 + k |
| `targets` <-> DDS 도메인 | RTPS (CycloneDDS) | `/clock` 수신, `/targets/*/state` 발행 | 도메인 20 + k |
| `sim-oracle` -> DDS 도메인 | RTPS (CycloneDDS) | `/sim/<vehicle_id>/pose` | 도메인 20 + k |

- `px4-N`의 프로세스는 `px4 -d -i N` 하나이고 uxrce_dds_client, gz_bridge, mavlink는 그 안의 모듈이다. ULog도 이 프로세스가 기록한다.
- `gazebo`에서는 `idsim_sim`의 `gz_server.sh`가 `gz sim -r -s`를 띄운다. 서버 하나가 월드, 기체 모델 N개, 표적 Actor를 모두 담는다.
- `bridge`의 ros_gz_bridge는 `parameter_bridge` 프로세스이고 명령행 인자로 `/clock` 하나만 넘긴다. 표적 상태와 정답 pose는 bridge를 거치지 않으므로 bridge 설정 파일은 두지 않는다.
- `targets`의 표적 어댑터는 `idsim_sim`의 rclpy 노드다. 입력은 생성된 params의 궤적 정의와 노드 시계(`/clock`)뿐이고 Gazebo에 붙지 않는다.
- `sim-oracle`의 정답 pose 노드는 `idsim_sim`의 rclpy 스크립트이고, gz-transport Python 바인딩으로 `pose/info`를 직접 구독해 기체 model pose에 base_link 오프셋(모델 SDF에서 읽는다)을 합성해 낸다. 그래서 sim-base 이미지에서 돈다. Actor 월드에서 서버를 죽이는 `dynamic_pose/info`는 bridge, `sim-oracle`, `gz-gui` 어디서도 구독하지 않게 하고, 생성 스크립트와 `idsim_sim`의 단위 테스트가 그 문자열이 없음을 검사한다.

상세 2: 운용 노드와 판정. 개요의 "운용과 판정" 상자를 펼친 것이다. 무엇을 주고받는지는 "전체 아키텍처" 절의 운용 서비스 레이어 그림과 그 아래 표에 있고, 여기서는 어느 컨테이너의 어느 프로세스인지만 보인다. 지금의 compose 기준이라 Phase 2 요소(Telemetry Collector, Logger / Replay)도 스택의 DDS 도메인 하나에 그렸다. 기체가 한 대이면 그 도메인이 그 기체의 버스다.

```mermaid
flowchart LR
  DDS2(["DDS 도메인"])
  subgraph OPSC["ops-N"]
    ME["Mission Executor"]
    TC["Telemetry Collector<br/>Phase 2"]
  end
  subgraph RUNC["runner"]
    RUNP["pytest, check 스크립트"]
  end
  LOG["Logger / Replay<br/>Phase 2"]

  DDS2 <--> ME
  DDS2 --> TC
  DDS2 <--> RUNP
  DDS2 --> LOG

  classDef later stroke-dasharray: 6 4
  class TC,LOG later
```

- `ops-N`의 프로세스는 `component_container_isolated` 하나이고, Mission Executor(`idsim_mission`)와 Telemetry Collector는 그 안에 올라가는 컴포넌트다.
- `runner`는 `compose run`으로 1회 실행하는 컨테이너이고, 그 안의 pytest와 check 스크립트가 rclpy 판정 노드로 DDS 도메인(기체의 버스)에 참가해 토픽을 구독하고 goal을 보낸다. 지상 링크를 거치지 않는다.
- Logger / Replay는 프로세스만 그렸다. 어느 compose 서비스에 둘지는 Phase 2에서 정한다.

상세 3: `viz` 프로필. 개요의 "viz 프로필" 상자와 그것이 닿는 호스트 도구를 펼친 것이다. 왼쪽 둘은 본 스택의 `gazebo` 컨테이너와 DDS 도메인이다.

```mermaid
flowchart LR
  GZ3["gazebo"]
  DDS3(["DDS 도메인"])
  subgraph VIZC["viz 프로필"]
    GUI["gz-gui"]
    FOX["foxglove"]
    LB["lichtblick"]
  end
  subgraph HOSTC["호스트 프로세스"]
    XS["X 서버"]
    WEB["브라우저"]
  end

  GZ3 <-.->|"gz-transport"| GUI
  GUI -.->|"X11 소켓 (호스트 방식)"| XS
  GUI -.->|"noVNC (가상 화면 방식)"| WEB
  DDS3 -.->|"구독"| FOX
  FOX -.->|"WebSocket"| WEB
  LB -.->|"HTTP"| WEB
```

| 도구 | 이미지 또는 실행 방식 | 붙는 곳 | 포트 |
| --- | --- | --- | --- |
| `gz-gui` | sim-base, `gz_gui.sh`가 `gz sim -g` 실행 | `gazebo` (gz-transport), 호스트 X 서버(Xwayland) 또는 컨테이너 안의 가상 화면(Xvnc + noVNC) | 가상 화면 방식은 127.0.0.1의 6080 + k, 호스트 방식은 없음 (X11 소켓 마운트) |
| `foxglove` | ros-ws, foxglove_bridge | DDS 도메인 (구독만, 쓰기 불가) | 127.0.0.1의 8765 + k |
| `lichtblick` | Lichtblick 공식 이미지, 정적 페이지 서버 | 브라우저가 열어 `foxglove`에 접속 | 127.0.0.1의 18080 + k |

- 판정과 CI는 `viz` 프로필의 세 서비스를 쓰지 않고, 본 스택의 어떤 서비스도 이들에 의존하지 않는다. `foxglove`는 토픽 버스에 쓰지 못하고 `gz-gui`는 월드를 멈출 수 없다.
- `gz-gui`는 조작이 가능한 경로다. WorldControl 말고 다른 GUI plugin이 남아 있다.

상세 4: 외부 클라이언트 경로(Phase 3). 개요의 "Fleet Manager, gateway" 상자를 펼친 것이다.

```mermaid
flowchart LR
  DDS4(["DDS 도메인"])
  FM["Fleet Manager"]
  GWP["gateway"]
  WEB4["브라우저"]

  DDS4 <-->|"지상 링크: Zenoh"| FM
  FM <-->|"gRPC"| GWP
  GWP <-->|"WebSocket, HTTP"| WEB4

  classDef later stroke-dasharray: 6 4
  class FM,GWP later
```

- Fleet Manager는 기체의 DDS 도메인에 직접 붙지 않고 지상 링크(Zenoh)를 거쳐 계약을 쓴다. Zenoh의 구성(bridge, router)은 정하지 않아 그리지 않았다.
- Fleet Manager는 gRPC 서버이며 프로세스만 그렸다. 어느 compose 서비스에 둘지는 Phase 3에서 정한다.
- `gateway`는 gRPC 클라이언트이자 WebSocket, HTTP 서버다. ROS 2를 모르고 Fleet Manager의 gRPC만 보며, 브라우저와는 WebSocket과 HTTP JSON으로 주고받는다.

| 서비스 | 이미지 | 역할 | 도입 Phase |
| --- | --- | --- | --- |
| `gazebo` | sim-base | `PX4_GZ_STANDALONE=1` 모드의 Gazebo 서버. `gz sim -r -s`로 월드를 직접 띄운다(`simulation-gazebo` 스크립트는 첫 실행 때 모델을 내려받으므로 쓰지 않는다). PX4-gazebo-models(모델, 월드, `server.config`)는 sim-base의 `/opt/px4-gz`에 한 벌만 두고 `GZ_SIM_SERVER_CONFIG_PATH`(PX4 전용 카메라, 광류 plugin 두 줄을 뺀 `server.idsim.config`), `GZ_SIM_RESOURCE_PATH`로 가리킨다. 월드 이름은 `config/fleet.yaml`의 `world.name`(모든 px4의 `PX4_GZ_WORLD`와 healthcheck 경로가 여기서 나온다). 헤드리스는 `gz sim -s`(서버만)로 얻는다. `HEADLESS`와 `PX4_GZ_SIM_RENDER_ENGINE`은 PX4 rcS 전용 변수라 이 서비스에는 주지 않는다. 여는 월드는 생성 스크립트가 만든 월드 SDF(`/opt/idsim/world/<월드>.sdf`. 실행 디렉터리의 `world/`를 읽기 전용으로 마운트)다. 명령은 `idsim_sim`의 wrapper 스크립트로, 서버를 띄우기 전에 그 SDF의 `<world name>`이 `world.name`과 같은지, `<spherical_coordinates>`가 정확히 하나인지 검사하고, 서버 기동 뒤 `scene/info`가 응답하면 준비 파일을 남긴다. 원점은 이 SDF로만 들어가고 wrapper는 런타임에 원점을 설정하지 않는다. 원점의 실제 적용은 px4 쪽 `sensor_gps` 좌표로 판정한다. px4 서비스에는 `PX4_HOME_*`를 주지 않는다(gz 경로에서 이 변수의 소비자는 `px4-rc.gzsim`의 원점 호출뿐이다. SIH 경로 `px4-rc.sihsim`도 이 변수를 읽으므로 SIH 변형을 추가하면 다시 본다) | 1 |
| `px4-1` ... `px4-N` | px4 | 빌드된 `px4` 바이너리를 `px4 -d -i N`으로 직접 실행(`make`가 아님. `-d`는 데몬 모드로, 컨테이너 stdin이 닫힌 상태에서 대화형 셸이 프롬프트를 끝없이 출력해 로그가 부푸는 것을 막는다. `build/px4_sitl_default/bin`이 PATH에 있고 작업 디렉터리는 `rootfs`). `PX4_SIM_MODEL=gz_x500`, `PX4_GZ_MODELS`, `PX4_GZ_MODEL_POSE`, `PX4_UXRCE_DDS_NS`, `GZ_IP`, `COM_OBL_RC_ACT` 등은 생성 스크립트가 넣는다. 인스턴스마다 환경변수가 달라 compose `scale`로는 부족하므로 `config/fleet.yaml`에서 N개 서비스를 생성. 작업 디렉터리 `rootfs/N`은 `artifacts/runs/<실행 id>/px4-N/`의 바인드 마운트이며 실행마다 새로 만든다(이전 `parameters.bson`을 읽지 않고 ULog, dataman이 산출물로 남는다). 호스트 uid:gid로 실행하고 `HOME`은 컨테이너 안 `/tmp`다. MAVLink 포트는 생성 스크립트가 넘기는 `IDSIM_MAVLINK_OFFSET`(1000k)을 px4 이미지의 idsim용 `px4-rc.mavlink`가 읽어 정한다 | 1 (1대), 3 (N대) |
| `xrce-agent` | xrce-agent (Micro XRCE-DDS Agent v2.4.3) | `MicroXRCEAgent udp4 -p <Agent 포트>`. 포트는 기준값 8888 + 스택 번호 k이며 PX4의 `PX4_UXRCE_DDS_PORT`와 같다. 지금의 compose는 모든 PX4가 여기로 접속한다(기체가 여러 대가 될 때 기체마다 하나로 바꾼다. Phase 3) | 1 |
| `runner` (`tools` 프로필) | ros-ws | 상주하지 않는 판정용 컨테이너. 스모크 스크립트와 통합 테스트가 `compose run`으로 판정 명령(check 스크립트, pytest)을 실행한다. 호스트 uid:gid, 저장소 마운트와 `IDSIM_STACK_FILE`(실행 디렉터리의 `stack.json`)을 `bridge`와 같은 방식으로 받는다. 본 스택의 `up --wait` 대상이 아니다. `depends_on`은 standalone에서 `ops-N` 전부와 `targets`(표적이 있을 때), `sim-oracle`의 healthy이고, 판정 스크립트는 스택을 먼저 올린 뒤 `compose run --no-deps`로 부른다 | 1 |
| `ops-1` ... `ops-N` | ros-ws | 기체별 운용 노드. 정적 launch(`idsim_mission`의 `vehicle_ops.launch.py`)로 기체당 컴포넌트 컨테이너(`component_container_isolated`) 하나에 Executor와 Collector(Phase 2)를 올려 프로세스와 DDS 참가자 수를 줄인다. 네임스페이스와 노드 이름은 launch 인자, 식별값은 생성된 `params/ops-N.yaml`로 받는다. 저장소를 `/opt/idsim`에 마운트하고 `tools/ros_ws.sh build`의 결과(`ros_ws/install`)를 쓴다. `init: true`, `stop_signal: SIGINT`, `stop_grace_period: 10s`, healthcheck는 Executor의 lifecycle 상태. `depends_on`은 `bridge`와 그 기체의 `px4-N` | 1 (Executor), 2 (Collector) |
| `bridge` | ros-ws | ros_gz_bridge. 시계를 `/clock`으로만 노출한다(명령행 인자 하나. 표적은 `targets` 서비스가 맡는다). ros-ws 안의 vendor gz-transport와 sim-base의 OSRF gz-transport가 와이어로 호환되는지는 스모크 테스트가 실측하며, 실패하면 이 서비스만 sim-base 계열 이미지로 옮긴다 | 1 |
| `targets` | ros-ws | `idsim_sim`의 표적 어댑터. 생성된 `params/targets.yaml`의 궤적 정의를 노드 시계(ROS 시각)에서 평가해 표적마다 `/targets/<target_id>/state`를 발행한다. fleet 파일에 표적이 없으면 만들지 않는다. 다른 ros-ws 서비스와 같은 공통값(host 네트워크, rmw, 도메인, 호스트 uid:gid, 저장소 마운트), `init: true`, `stop_signal: SIGINT`. `depends_on`은 `bridge`, healthcheck는 모든 표적을 한 번 이상 발행한 뒤 노드가 남기는 표시 파일. 노드 단계에서 `ops-N`과 함께 올라가고 `ops-N`은 이 서비스를 기다리지 않는다 | 1 |
| `sim-oracle` | sim-base | `idsim_sim`의 정답 pose 노드. 기체마다 base_link 기준 정답 pose `/sim/<vehicle_id>/pose`를 낸다(SITL 판정 전용. 계약이 아니다). standalone이면 표적과 무관하게 항상 만든다. `depends_on`은 `gazebo`와 `px4-N` 전부, healthcheck는 모든 기체의 pose를 한 번 이상 낸 뒤 노드가 남기는 표시 파일. 노드 단계에서 올라간다 | 1 |
| `gz-gui` (`viz` 프로필) | sim-base | `gz sim -g`로 이미 떠 있는 `gazebo` 서버에 GUI 클라이언트만 붙인다. 같은 `GZ_PARTITION`과 `GZ_IP`, `DISPLAY`, X11 소켓과 `XAUTHORITY` 읽기 전용 마운트. `idsim_sim`의 `gui.config`(WorldControl plugin 제외)를 쓴다. `ipc: host`, 호스트 uid:gid, `gazebo`에 `depends_on`(viz -> 본 스택 방향은 허용), healthcheck 없음. `idsim_sim`의 wrapper가 화면 방식을 고른다: `IDSIM_GZ_GUI_DISPLAY`가 `auto`(기본)이면 `DISPLAY`가 비어 있지 않고 Xauthority 파일을 읽을 수 있고 비어 있지 않을 때 호스트 X 서버에, 아니면 컨테이너 안의 가상 화면(Xvnc)에 띄우고 noVNC를 127.0.0.1의 6080 + k로 연다. `host`에서는 `DISPLAY`가 비었거나 Xauthority 파일이 없거나 비었거나 읽을 수 없으면 안내 메시지와 함께 끝내고, `virtual`은 항상 가상 화면이다. 가상 화면 방식에서 호스트 netns에 열리는 화면 관련 TCP 포트는 websockify의 127.0.0.1:6080 + k 하나뿐이다(Xvnc는 컨테이너 안 unix socket에만, X는 `-nolisten tcp`로 abstract socket에만 연다. 스택 9에서 확인). `/dev/dri`와 NVIDIA 전달은 opt-in | 1 |
| `foxglove` (`viz` 프로필) | ros-ws | foxglove_bridge. 주소 127.0.0.1, 포트 8765 + k, 토픽 allowlist, clientPublish, services, parameters 기능을 빼 읽기 전용 | 1 |
| `lichtblick` (`viz` 프로필) | Lichtblick 공식 이미지 (digest 고정) | 브라우저에서 127.0.0.1의 18080 + k으로 열어 `foxglove` 서비스에 접속. 실시간 플롯과 MCAP 열람 | 1 |
| `gateway` | gateway (Rust, 정적 바이너리) | Fleet Manager gRPC를 브라우저용 WebSocket과 HTTP JSON으로 중계하고 Fleet 페이지를 서빙. ROS 2 비의존이라 `ros-ws`와 무관하게 빌드 | 3 |

시작 순서와 healthcheck. Agent -> gazebo -> px4 -> bridge -> ops-N 순으로 `depends_on`에 `condition: service_healthy`를 건다. gazebo가 월드를 올리기 전에 px4가 모델 스폰을 시도하면 실패하기 때문이다. healthcheck는 Agent는 포트 열림(16진수 포트는 생성 스크립트가 계산해 넣는다), gazebo는 월드 서비스(`/world/<월드>/scene/info`) 응답과 wrapper가 그 응답 직후에 남기는 준비 파일, px4는 컨테이너 안에서 `px4-uxrce_dds_client --instance N status` 출력의 연결 상태 문자열, bridge는 `/clock` 수신(interval 30초, `start_period` 동안 `start_interval` 5초로 discovery 소음을 줄인다), ops-N은 Executor의 lifecycle 상태(`ros2 lifecycle get --no-daemon <노드 FQN>`의 출력이 `active`로 시작하는지. FQN은 `stack.json`의 `executor_node`와 같다), `targets`와 `sim-oracle`은 노드가 준비 조건을 만족한 뒤 원자적으로 만드는 표시 파일로 판정한다. lifecycle 전이를 거는 주체는 노드 자신이다. Executor는 생성자에서 만든 벽시계 일회 timer로 configure와 activate를 한 번씩 부르고(`lifecycle.self_start`, 기본 true. launch_ros 0.26.13에서 컨테이너 autostart는 동작하지 않는다), compose, launch, 테스트는 전이를 걸지 않는다. px4의 `gz_bridge status`는 연결 상태를 출력하지 않고 Gazebo가 멈춰도 성공하므로 healthcheck에 쓰지 않는다(실측). 같은 이름의 옛 모델이 남은 Gazebo에 px4가 다시 붙는 조용한 실패는 healthcheck로 잡히지 않으므로 운영 규칙으로 막는다: `restart`는 모두 `no`, 운영 스크립트(`tools/sim_stack.sh`, `run_smoke.sh`)는 `up` 전에 `down`을 하고, `up --wait`를 세 단계(Agent와 gazebo, px4-N, bridge)로 나눠 1단계 뒤 `gz model --list`에 `<모델>_N`이 없음을 확인하는 모델 사전 검사를 하고 나머지를 차례로 `up --wait`하며, 스택이 healthy가 된 뒤 모델이 정확히 하나인지 판정한다. 그 뒤 노드 단계(`stack.json`의 `startup.node_stages`. `ops-N`, `targets`(표적이 있을 때), `sim-oracle`을 한 단계에서 함께)를 `up --wait`한다. `--infra-only`는 노드 단계를 건너뛴다(Executor, 표적 어댑터, 정답 pose 노드 없이 인프라만. 스모크가 쓴다). standalone이면 생성된 월드 파일이 없거나 그 안의 `<spherical_coordinates>`가 정확히 하나가 아닐 때, 그리고 노드 단계를 올릴 때 `ros_ws/install/idsim_mission/`(표적이 있으면 `ros_ws/install/idsim_sim/`도), `sim-oracle`이 있으면 `ros_ws/src/idsim_sim/scripts/sim_oracle.py`가 없으면 아무것도 올리기 전에 실패하고, 노드 단계가 실패하면 `ops-N`, `targets`, `sim-oracle`의 로그 끝과 healthcheck 기록을 함께 보인다. 사용자 진입점은 `tools/sim_stack.sh up` 한 번이고 단계들은 그 안에 있다. Agent는 포트 bind에 실패해도 종료 코드 0으로 끝나므로 운영 스크립트는 `up --wait` 실패 시 Agent 로그의 `bind error`를 찾아 보고하고, px4 로그에 `WARN  [mavlink] bind failed`가 없음을 판정한다. px4 컨테이너에는 px4_msgs가 없고 healthcheck마다 DDS 참가자를 만들면 discovery 소음이 되므로 토픽 수신으로 판정하지 않는다. 토픽 수신은 `runner`의 판정 코드가 확인한다. 자동 재시작(`restart`)은 쓰지 않는다. flaky를 가리고 standalone에서 남은 모델 때문에 재스폰이 반복 실패할 수 있다. 통합 테스트는 `tools/sim_stack.sh up`이 노드 단계까지 healthy로 올린 뒤에만 미션을 보낸다. PID 1이 신호를 버리지 않도록 `xrce-agent`, `bridge`, `ops-N`, `targets`, `sim-oracle`, `runner`는 `init: true`다. `ops-N`은 SIGINT로 멈춰 rclcpp의 종료 경로를 탄다. 정지 뒤의 종료 코드는 판정에 쓰지 않고, 테스트 wrapper가 정지 전에 `ops-N`이 running인지를 기록해 판정한다.

컨테이너 사용자. 호스트에 쓰는 바인드 마운트가 있는 서비스(`px4-N`, `bridge`, `ops-N`, `targets`, `sim-oracle`, `runner`, `gz-gui`)는 생성 시 구운 호스트 사용자의 uid:gid로 실행하고 `HOME`을 컨테이너 안 `/tmp` 아래로, ROS 로그는 `ROS_LOG_DIR`로 `artifacts/runs/<실행 id>/ros_log/<서비스>/`에 둔다. `xrce-agent`와 `gazebo`는 root로 둔다(호스트에 쓰지 않는다). 그 uid가 이미지의 passwd에 없어도(CI runner는 1001) ros2 CLI, rclpy, px4, gz CLI는 동작함이 실측되었고 깨지는 것은 `whoami`, `pwd.getpwuid`, `getpass.getuser`뿐이다. 그래서 저장소 코드는 사용자 이름을 조회하지 않고(`getpass`, `pwd` 호출 금지) uid 숫자만 쓴다. 바인드 마운트 안에 또 바인드 마운트를 두면 마운트 지점이 root 소유가 되므로 생성 스크립트는 중첩 마운트를 만들지 않고 단위 테스트가 이를 검사한다. 생성 스크립트를 돌리는 1회용 컨테이너는 `--network none`이고 `CYCLONEDDS_URI`를 비운다(설정 파일을 마운트하지 않은 채 두면 rmw가 파일을 못 열어 CLI가 실패한다).

생성된 compose. 스택은 `tools/sim_stack.sh`(또는 생성만 하는 `tools/gen_compose.sh`)가 `artifacts/runs/<실행 id>/compose.yaml`과 `stack.json`, standalone이면 월드 SDF `world/<월드>.sdf`를 만들고 그 compose로 올린다. 실행 id의 기본값은 `<UTC 시각>-k<k>`이고 스모크는 단계 이름을 붙인다. `stack.json`의 `inputs`에는 fleet.yaml, versions.env, PX4 파라미터 파일, cyclonedds.xml, 월드 템플릿의 sha256이 기록되고, 판정 스크립트는 스택 기동 뒤 저장소의 cyclonedds.xml 해시를 이 값과 대조한다. 값(도메인, 포트, 경로, uid:gid, 이미지 태그)은 모두 구체값으로 박고 보간 변수를 쓰지 않으므로 실행 디렉터리만 보면 무엇으로 돌았는지 재현된다. 식별자의 단일 출처는 `stack.json`이며 스크립트, 판정 코드, 테스트는 이를 다시 계산하지 않고 읽는다(생성기와 `tests/support/`의 로더가 같은 스키마를 공유하고, golden `stack.json`을 로더로 읽는 교차 테스트가 어긋남을 잡는다). 규칙 네 가지. (1) compose 파일이 저장소 밖 실행 디렉터리에 놓이므로 compose 안의 경로는 호스트 저장소 루트 기준 절대 경로이고, 바인드 마운트는 원본이 없을 때 만들지 않는 긴 형식이다. (2) 저장소는 ros-ws 이미지를 쓰는 서비스(`bridge`, `ops-N`, `targets`, `runner`, `foxglove`)에 `/opt/idsim`으로 읽기/쓰기 하나만 마운트하고 `cyclonedds.xml` 같은 하위 파일을 따로 겹쳐 마운트하지 않는다(중첩 마운트 금지 규칙). (3) 서비스 사이 공통 환경변수는 YAML 앵커로 묶지 않고 서비스마다 풀어 쓴다. 생성기가 쓰는 PyYAML은 병합 key를 출력하지 못하고 출력 순서를 고정해야 golden이 안정되기 때문이다. (4) 변형은 `standalone`(기본)과 `embedded`(진단용. 기체 1대, `gazebo`와 `bridge` 없이 PX4가 Gazebo를 직접 띄움)이고, 호스트 Docker Engine은 healthcheck `start_interval` 때문에 25.0 이상이어야 한다.

이미지 구성. 직접 빌드하는 이미지는 다섯 종이다. ROS 계열 셋은 `ros-base` 위에 쌓이고(`ros-base` -> `sim-base` -> `px4`, `ros-ws`는 `ros-base`에서 바로 갈라진다), `xrce-agent`는 독립이다. 모든 Dockerfile은 `docker/` 아래에 있고 버전은 `docker/versions.env`에서만 읽는다. 예외는 월드 템플릿 `ros_ws/src/idsim_sim/worlds/idsim_base.sdf` 주석의 `PX4_GZ_MODELS_REF` ref 줄 하나로, 검증된 사본이다(lint 단위 테스트 `tests/tools/test_world_template_ref.py`가 `versions.env`의 값과 같음을 강제하고, 내용 대조는 스모크 S0가 한다).

직접 빌드하는 이미지 다섯의 계보는 다음과 같다. 화살표는 베이스 관계(`FROM`)다. 이미지에 들어가는 것과 이미지마다 뜨는 컨테이너는 아래 이미지 표에, 호스트 저장소의 바인드 마운트는 이 문단들 끝의 표에 있다.

```mermaid
flowchart TB
  UB["ubuntu:24.04"]
  RB["ros-base"]
  SB["sim-base"]
  PXI["px4"]
  WS["ros-ws"]
  XA["xrce-agent"]

  UB --> RB
  RB --> SB
  SB --> PXI
  RB --> WS
  UB --> XA
```

- 빌드하지 않는 이미지는 둘이다. `lichtblick` 서비스는 digest로 고정한 Lichtblick 공식 이미지를 쓰고, `gateway` 이미지(Rust 정적 바이너리)는 Phase 3에서 더한다.
- compose 서비스가 아닌 1회 실행 컨테이너도 같은 이미지를 쓴다. `tools/gen_compose.sh`와 `tools/ros_ws.sh`는 ros-ws로, `tools/sim_stack.sh`의 모델 사전 검사는 sim-base로 돈다.

| 이미지 | 베이스 | 들어가는 것 | 뜨는 컨테이너 | 다시 빌드되는 때 |
| --- | --- | --- | --- | --- |
| `ros-base` | Ubuntu 24.04 (digest 고정) | ROS 2 Jazzy, CycloneDDS rmw, 공통 도구. `RMW_IMPLEMENTATION` 고정 | 없음 (베이스 전용) | ROS 버전이나 공통 도구 변경 |
| `sim-base` | `ros-base` | OSRF apt의 Gazebo Harmonic, PX4-gazebo-models의 모델, 월드, `server.config`를 `/opt/px4-gz`에. 원본에서 PX4 전용 plugin 두 줄을 뺀 `server.idsim.config`를 함께 생성. Gazebo GUI 클라이언트용 `libqt5svg5`. 가상 화면용 `tigervnc-standalone-server`, `websockify`, `xauth`와 noVNC 정적 파일(`/usr/share/novnc`). PX4 gz_plugins(광류, GStreamer 카메라)는 넣지 않음 | `gazebo`, `gz-gui`, `sim-oracle` | Gazebo 버전이나 모델 커밋 변경 |
| `px4` | `sim-base` | PX4 릴리스 태그를 소스 빌드한 결과물: `px4` 바이너리, ROMFS 시작 스크립트. 모델은 복사하지 않고 `/opt/px4-gz`를 심볼릭 링크로 가리킴. 멀티스테이지라 빌드 도구와 소스는 최종 이미지에 없음 | `px4-1` ... `px4-N` (기체당 하나) | PX4 태그 변경 |
| `ros-ws` | `ros-base` | px4_msgs, px4_ros_com, ros_gz_bridge(vendor gz-transport만), foxglove_bridge(ROS apt 저장소의 최신 빌드. 설치된 판이 `FOXGLOVE_BRIDGE_VERSION`의 upstream 버전 접두와 같은지 빌드에서 단정한다), colcon, clang-tidy-18, clang-format-18. 이 프로젝트의 ROS 패키지는 이미지에 넣지 않고 실행 시 `/opt/idsim`에 마운트해 `tools/ros_ws.sh`로 빌드한다. gz 서버는 없음 | `ops-N`, `bridge`, `targets`, `runner`, `foxglove` | `ros-base`, 의존 패키지, 빌드 도구, `Dockerfile.ros-ws` 변경 (프로젝트 소스 변경은 이미지를 다시 빌드하지 않는다) |
| `xrce-agent` | Ubuntu 24.04 (digest 고정) | Micro XRCE-DDS Agent를 소스 빌드한 멀티스테이지. ROS 없음 | `xrce-agent` | Agent 버전 변경 |

이렇게 나눈 이유.

- `sim-base`의 Gazebo를 ROS vendor 패키지가 아니라 OSRF 패키지로 넣는 것은 PX4의 gz_bridge 빌드가 OSRF 개발 헤더를 `find_package`로 찾기 때문이다.
- 모델을 `sim-base` 한 벌에만 두는 것은 Gazebo 서버와 PX4가 같은 절대 경로로 모델 파일을 열어야 하기 때문이다. `gazebo`와 `px4` 컨테이너가 같은 베이스를 쓰면 경로 일치가 자동으로 보장되고 공유 볼륨이 필요 없다.
- `ros-ws`를 `sim-base`가 아니라 `ros-base`에서 가르는 것은 Gazebo 서버가 필요 없는 이미지를 가볍게 유지하기 위해서다. 프로젝트 소스를 이미지에 굽지 않는 것은 굽으면 커밋마다 이미지 key가 바뀌어 재빌드와 레지스트리 푸시가 PR마다 생기기 때문이다. bridge에 필요한 gz-transport는 ros_gz_bridge가 vendor 패키지로 끌어오며, gz 서버와 같은 프로세스에 들어가지 않으므로 OSRF 라이브러리와 섞이지 않는다.
- `xrce-agent`를 `ros-base` 위에 올리지 않는 것은 Agent 소스 빌드가 자체 Fast-DDS를 설치하는데 ROS가 가져오는 또 다른 Fast-DDS와 한 프로세스에서 섞일 수 있기 때문이다. ROS가 필요 없으므로 Ubuntu 베이스가 더 작기도 하다.
- PX4 빌드가 가장 무거우므로 `px4` 이미지는 ccache 마운트와 레지스트리 캐시를 쓰고, CI는 아래 이미지 key가 레지스트리에 있으면 빌드를 건너뛴다.
- `px4` 빌드 단계는 PX4 서브모듈의 모델 커밋이 `versions.env`의 값과 같은지 검사해 다르면 실패한다. 두 이미지의 모델이 어긋나는 것을 빌드 시점에 막기 위해서다.

바인드 마운트.

| 호스트 원본 (저장소 기준) | 컨테이너 안 경로 | 받는 서비스 | 모드 |
| --- | --- | --- | --- |
| `ros_ws/src/idsim_sim` | `/opt/idsim/sim` | `gazebo`, `gz-gui`, `sim-oracle` | 읽기 전용 |
| `artifacts/runs/<실행 id>/world` (생성된 월드 SDF) | `/opt/idsim/world` | `gazebo` | 읽기 전용 |
| `config/cyclonedds.xml` (파일 하나) | `CYCLONEDDS_URI`가 가리키는 경로 | `sim-oracle` | 읽기 전용 |
| `artifacts/runs/<실행 id>/ros_log/sim-oracle` | `ROS_LOG_DIR` | `sim-oracle` | 읽기/쓰기 |
| `artifacts/runs/<실행 id>/px4-N` | PX4 `rootfs/N` | `px4-N` | 읽기/쓰기 |
| 저장소 전체 | `/opt/idsim` | `bridge`, `ops-N`, `targets`, `runner`, `foxglove` | 읽기/쓰기 |

이 표는 compose 서비스의 저장소 마운트만 담는다. `gz-gui`는 X11 소켓과 Xauthority를 더 받고(서비스 표), 1회 실행 컨테이너의 마운트는 이 표와 다르다.

`docker/versions.env`에는 PX4 태그(`PX4_TAG`), px4_msgs 커밋(`PX4_MSGS_REF`), px4_ros_com 커밋(`PX4_ROS_COM_REF`), PX4-gazebo-models 커밋(`PX4_GZ_MODELS_REF`), PX4-OpticalFlow 커밋(`PX4_OPTICAL_FLOW_REF`), Agent 버전(`XRCE_AGENT_TAG`), Gazebo 릴리스(`GZ_RELEASE`), 기대하는 gz-sim upstream 버전(`GZ_SIM_VERSION`), apt 서명 key의 주 key 지문(`ROS_APT_KEY_FPR`, `GZ_APT_KEY_FPR`), 우분투 apt 미러(`UBUNTU_APT_MIRROR`), foxglove_bridge 판(`FOXGLOVE_BRIDGE_VERSION`), clang 도구의 major(`LLVM_MAJOR`), 베이스 이미지 digest, 레지스트리 주소를 적는다. Dockerfile은 기본값 없는 `ARG`로 받고, compose와 CI도 같은 파일을 읽는다. 다른 문서와 golden 파일도 이 파일의 key 이름을 그대로 쓴다. 이 파일 밖의 `PX4_GZ_MODELS_REF` 사본은 월드 템플릿 주석의 ref 줄뿐이며, `tests/tools/test_world_template_ref.py`가 같음을 강제하고 스모크 S0가 내용을 대조한다. px4_ros_com에는 release/1.17 브랜치가 없어 release/1.16 HEAD와 같은 main 커밋으로 고정한다. `idsim_common`은 `frame_transforms`를 래핑하지 않고 좌표 변환을 직접 구현하며, px4_ros_com은 단위 테스트의 비교 기준으로만 쓴다.

이미지 key. CI와 로컬 빌드는 `tools/ci/image_keys.py`로 이미지마다 key를 계산하고, 같은 key가 레지스트리에 있으면 그 이미지의 빌드를 건너뛴다. key는 다음 재료를 순서대로 이어 붙인 텍스트의 SHA-256 앞 16자리다. 재료 목록은 `image_keys.py --explain <이미지>`로 볼 수 있다.

1. key 방식 이름(`scheme idsim-image-key-v2`). 계산 방식을 바꾸면 이 값을 올려 모든 key를 바꾼다.
2. 이미지 이름(`image <이름>`).
3. Dockerfile 바이트의 sha256.
4. `docker/docker-bake.hcl`에서 그 target의 빌드 입력을 정규화한 줄. `bake dockerfile`, `bake context`, `bake platforms`, `bake args <이름>=<식>`(이름순), `bake contexts <이름>=<식>`(이름순)만 넣고, `inherits`로 받은 부모 target(`_common` 등)의 속성 위에 자식 속성을 합친 결과를 쓴다. 스칼라와 목록(`dockerfile`, `context`, `platforms`)은 자식이 덮고, `args`와 `contexts`는 bake처럼 항목별로 합치며 같은 이름이면 자식이 이긴다. 상속은 여러 단계를 풀고 순환하면 멈춘다. tags, 공백, 주석, 항목 순서는 이미지 바이트에 영향을 주지 않으므로 넣지 않는다. args의 식은 변수 이름 그대로 넣고 변수의 값은 6번이 넣는다. 정규화는 fail-closed다. 알려진 속성(`inherits`, `tags`, `dockerfile`, `context`, `platforms`, `args`, `contexts`) 밖의 속성(`target`, `labels` 등)이 있거나 해석할 수 없는 값(보간, 함수 호출, 문자열이 아닌 스칼라)이 있으면 말없이 버리지 않고 key 계산이 멈춘다. 그래서 bake에 새 속성을 쓰려면 `tools/ci/image_keys.py`부터 고친다.
5. Dockerfile이 COPY/ADD로 빌드 context(`docker/`)에서 가져오는 원본 파일의 sha256.
6. `versions.env` 중 그 Dockerfile이 `ARG`로 선언한 이름의 줄(`env NAME=값`).
7. 베이스 이미지의 이름과 key(`base <베이스> <베이스 key>`). 그래서 `ros-base`가 바뀌면 `sim-base`, `px4`, `ros-ws`의 key가 모두 바뀌고, 베이스 target이 없는 `xrce-agent`는 독립이다.

key의 원칙은 "같은 key는 같은 이미지"다. 다만 key는 저장소 안의 입력만 해시하므로 이 원칙에는 다음 두 가지 한계가 있다.

- `UBUNTU_APT_MIRROR`는 Dockerfile이 `ARG`로 받지만 key에서 뺀다(`image_keys.py`의 `KEY_EXCLUDED_ARGS`). 이것은 "같은 key는 같은 바이트"의 유일한 명시적 예외다. 미러는 같은 우분투 저장소의 사본을 받는 주소일 뿐이고, 기본 미러가 다른 개발 PC와 CI가 같은 key로 레지스트리의 이미지를 나눠 쓰려면 미러가 key에 들어가면 안 되기 때문이다. 그 대가로 이미지에 남는 `/etc/apt/sources.list.d/ubuntu.sources`의 바이트가 미러마다 다르고, 미러 동기화 시차로 우분투 패키지의 판이 다를 수 있다. 앞의 것은 런타임이 apt를 쓰지 않으므로 동작에 영향이 없고, 뒤의 것은 아래 apt 저장소 상태의 한계와 같다. 다른 빌드 인자를 key에서 빼려면 이처럼 이미지 동작에 영향이 없다는 근거가 있어야 한다.
- 빌드 시점의 외부 상태는 key에 들어가지 않는다. apt 저장소(우분투, packages.ros.org, packages.osrfoundation.org)에 그때 올라와 있는 패키지 판, pip 인덱스, 태그가 가리키는 커밋이 그렇다. apt 패키지는 판을 정확히 고정하지 않는다. 저장소가 옛 판을 지우면 콜드 빌드가 깨지기 때문이다. 그래서 같은 key로 다시 빌드하면 다른 패키지가 설치될 수 있고, 같은 key의 이미지는 레지스트리에 한 번만 올라가므로 먼저 올라간 이미지가 그 key의 이미지가 된다.

빌드 시점의 대조가 이 한계의 일부를 막는다. 동작에 직접 영향을 주는 패키지와 소스는 빌드 단계에서 `versions.env`의 값과 대조해 다르면 빌드가 실패한다. `sim-base`는 설치된 `libgz-sim<major>` 판의 upstream 버전을 `GZ_SIM_VERSION`과, `gazebo.gpg`의 주 key 지문을 `GZ_APT_KEY_FPR`과 대조하고, `ros-ws`는 설치된 foxglove_bridge 판의 upstream 버전을 `FOXGLOVE_BRIDGE_VERSION`과 대조한다. `px4` builder는 PX4-OpticalFlow 체크아웃 커밋을 `PX4_OPTICAL_FLOW_REF`와, PX4 서브모듈의 모델 커밋을 `PX4_GZ_MODELS_REF`와 대조한다. 이미지는 빌드에 쓴 주요 버전을 `IDSIM_BUILD_<이름>` ENV(`<이름>`은 `versions.env` 항목 이름)로 남기고(`sim-base`는 `IDSIM_BUILD_GZ_SIM_VERSION`을 남긴다), 스모크 images 단계는 `IDSIM_BUILD_GZ_SIM_VERSION` 같은 값을 `versions.env`와 대조해 `versions.env`만 올리고 이미지를 다시 빌드하지 않은 상태를 잡는다. 대조가 막지 못하는 범위는 세 가지다. (1) 대조는 upstream 버전까지만 보고 deb revision(같은 소스의 재빌드 판, 배포판 접미사)은 보지 않는다. (2) 대조하지 않는 나머지 apt 패키지(ROS 2 Jazzy와 CycloneDDS, gz-sim 밖의 Gazebo 라이브러리, 우분투 패키지)의 판은 빌드 시점의 저장소 상태를 따른다. (3) 그 차이는 key에도 `IDSIM_BUILD_*`에도 남지 않으므로 같은 key의 두 빌드는 레지스트리 digest로만 구별된다. 동작이 달라진 의심이 들면 `versions.env`의 대조 값이 아니라 이미지 digest와 그 안의 dpkg 목록을 비교한다.

스모크 테스트 산출물. 토픽 목록과 발행자 QoS의 golden 파일은 `tests/fixtures/px4/<PX4_TAG>/`에 추적하고, 실행 로그와 ULog 같은 원시 산출물은 `artifacts/`에 비추적으로 둔다. 단계, 판정, golden 형식은 [smoke-test.md](smoke-test.md)에 있다.

GUI와 GPU. 개발 중 Gazebo 화면은 `viz` 프로필의 `gz-gui` 서비스로 본다. sim-base 컨테이너에서 `gz sim -g`를 실행해 이미 떠 있는 `gazebo` 서버에 GUI 클라이언트만 붙이며, `DISPLAY`, X11 소켓(`/tmp/.X11-unix`), `XAUTHORITY`를 읽기 전용으로 넘긴다. 개발 호스트(GNOME Wayland + Xwayland, VMware 가상머신, NVIDIA 없음)에서는 컨테이너 안 OpenGL이 VMware SVGA3D(Mesa, OpenGL 4.3)로 잡히고 Xwayland가 DRI3로 렌더 노드를 넘겨 주므로 `--device /dev/dri` 없이 하드웨어 가속이 된다(약 90 fps, GUI를 붙여도 서버 RTF 1.0 유지). 이 호스트에서 llvmpipe를 강제하면 15 fps 수준이라 호스트 방식에서는 쓰지 않는다. sim-base의 Qt5에는 wayland plugin이 없어 GUI는 xcb(Xwayland)로만 뜬다. NVIDIA GPU가 있으면 `nvidia-container-toolkit`으로 넘긴다. 서버 쪽은 바뀌지 않는다. 렌더링 센서가 없는 기본 x500 월드에서는 서버의 렌더 엔진이 초기화되지 않고, 카메라 센서를 쓰는 확장 단계에서는 ogre2 + `--headless-rendering`으로 간다(ogre 1.x는 X 디스플레이 없이 돌지 않는다). CI는 항상 서버 전용(`gz sim -s`)이다. 호스트 X11이 없는 호스트에서는 `gz-gui`가 컨테이너 안의 가상 화면(Xvnc, 소프트웨어 렌더링 Mesa llvmpipe)에 뜨고 noVNC로 브라우저에서 본다. GPU 가속은 없다. Mac(OrbStack VM CPU 10개), 기체 1대, 인프라만(운용 노드 없음)에서 30 s 창을 네 번씩 잰 RTF가 GUI와 함께 0.9993-0.9998, GUI 없이 0.9984-0.9997로 차이가 없고 gz-gui 컨테이너가 CPU 약 2코어를 쓴다. 그 밖의 조건은 재지 않았다. llvmpipe에서 3D view 갱신은 약 12-16 fps다(VNC 갱신 횟수로 추정한 값). 이 방식은 Mac(OrbStack)에서 확인했고 Linux 호스트에서는 돌려 보지 않았다.

`viz` 프로필의 격리. `gz-gui`, `foxglove`, `lichtblick`은 compose 프로필 `viz`에만 속한다. 판정과 CI에 영향을 주지 않도록 어떤 본 스택 서비스도 `viz` 프로필의 서비스에 `depends_on`하지 않고(`viz` 서비스가 본 스택 서비스에 의존하는 반대 방향은 허용하며 생성 스크립트가 이를 단정하고 단위 테스트가 검사한다), 프로필 서비스는 `up --wait`의 healthy 조건에 들어가지 않으며, `run_smoke.sh`, pytest fixture, CI 워크플로는 프로필을 켜지 않는다. `foxglove`는 clientPublish, services, parameters 기능을 뺀 읽기 전용이라 토픽 버스에 쓸 수 없고, `foxglove`, `lichtblick`, noVNC의 포트는 127.0.0.1에만 열며 스택 번호 k로 분리한다. `gui.config`에서 WorldControl을 빼 화면에서 월드를 멈출 수 없다. compose는 꺼진 프로필의 서비스도 보간하므로(실측) `viz` 서비스의 환경변수에 `${X:?}`를 쓰지 않고 `${DISPLAY:-}`, `${XAUTHORITY:-/dev/null}:/tmp/.Xauthority:ro`처럼 기본값을 둔다. 렌더 엔진은 `--render-engine-gui ${IDSIM_GZ_GUI_ENGINE:-ogre2}`로 고를 수 있고 `QSG_RENDER_LOOP`, `vblank_mode`는 이름만 통과시킨다. 1회 실행용 runner 서비스는 프로필 `tools`에 두어 인자 없는 `up --wait`가 기다리지 않게 한다(`compose run`은 프로필 지정 없이 실행된다, 실측). 3대 시나리오의 CPU 측정은 GUI 없이 한다.

시간 동기화. 모든 ROS 2 노드는 `use_sim_time:=true`로 Gazebo `/clock`을 따르고, rosbag2 기록도 `--use-sim-time`으로 한다. 그래야 `PX4_SIM_SPEED_FACTOR`로 배속 실행해도 로그와 테스트 타이밍이 흔들리지 않고, 재생 시 `ros2 bag play --clock`이 만드는 시계가 기록 당시 시계와 같아진다. `/clock` 자체는 기록 대상에서 제외한다. 재생기가 만드는 시계와 충돌하기 때문이다.

개발 호스트. CI와 판정의 기준 환경은 x86_64 Linux runner와 arm64 Linux runner 둘이다. 판정 상수는 amd64에서 보정했다. Apple Silicon Mac(macOS, arm64)은 개발 호스트로 지원한다. 같은 Dockerfile, bake 파일, 생성기, 스크립트를 쓰고(아키텍처별 사본을 두지 않는다), 이미지는 linux/amd64와 linux/arm64 두 플랫폼으로 빌드한다. 이미지 key는 아키텍처와 무관하게 이미지마다 하나다. main의 build는 플랫폼마다 `<이미지>:<key>-<arch>` 태그로 올리고, 두 플랫폼이 모두 성공한 뒤 merge job이 key 태그 `<이미지>:<key>`를 multi-arch index로 만들어서 registry(GHCR)의 태그는 이미지마다 하나다. Mac은 GHCR에 arm64 index가 올라온 뒤에는 `--mode pull`로 받을 수 있고, 그 전에는 `--mode load`로 로컬 빌드한다. container runtime은 OrbStack을 기준으로 한다. Mac에서는 컨테이너가 Linux VM 안에서 돌므로 `network_mode: host`는 그 VM의 네트워크를 뜻한다. 스택 안의 통신은 Linux와 같고, Mac 쪽에서 스택의 포트에 닿는지는 container runtime에 달렸다. 요구 조건과 제약은 `README.md`의 "호스트 조건"에 둔다.

저장소 레이아웃(초안):

```
idsim/
  docker/            # Dockerfile.ros-base, Dockerfile.sim-base, Dockerfile.px4, Dockerfile.ros-ws,
                     # Dockerfile.xrce-agent, versions.env (compose 파일은 손으로 두지 않고 생성한다)
    px4/             # px4-rc.mavlink (idsim용 MAVLink 시작 스크립트. Dockerfile.px4가 PATH 앞에 COPY)
  .clang-format      # C++ 서식 (clang-format-18)
  .clang-tidy        # C++ 정적 검사 (clang-tidy-18)
  config/
    fleet.yaml       # 기체 레지스트리, 월드, 표적 (단일 출처. 스택 번호는 생성 인자)
    cyclonedds.xml   # rmw 설정
    px4/             # SITL 파라미터 (PX4_PARAM_* 환경변수)
  tools/
    gen_compose.py   # fleet.yaml -> artifacts/runs/<실행 id>/{compose.yaml, stack.json} (viz 프로필 포함). ros-ws 컨테이너에서 실행
    gen_compose.sh   # gen_compose.py의 호스트 진입점 (ros-ws 컨테이너, 호스트 uid:gid, --network none)
    ros_ws.sh        # ros-ws 컨테이너에서 ROS 패키지 build, test, tidy, ci, clean, shell (저장소를 /opt/idsim에 마운트)
    sim_stack.sh         # 생성 + compose up/down/logs 묶음. down 뒤 up, 모델 잔존 사전 검사, Agent bind 오류 보고,
                         # 인프라 단계 뒤 노드 단계(ops-N). --infra-only는 노드 단계를 건너뛴다.
                         # restart-ops는 떠 있는 스택에서 ops-N만 다시 만든다
    to_interface.py  # 스모크 산출물 -> docs/interface.md 표
  ros_ws/src/
    idsim_interfaces/ # 커스텀 msg/action (미션, 미션 기록 사건, 기체 상태, 표적 상태)와 계약 테스트(golden)
    idsim_common/     # QoS 프로필(PX4, 계약), 좌표 변환과 원점 이동, PX4 토픽 이름 매핑, 계약 이름 조립과 id 검증, 네임스페이스 유틸 (C++ 라이브러리)
    idsim_mission/    # 미션 실행 노드 Executor (Offboard 제어, lifecycle 컴포넌트)와 ops-N의 launch. 상태기(core)는 ROS와
                      # px4_msgs에 비의존인 순수 C++ 클래스이고 PX4 enum의 해석은 px4/ 디렉터리에만 둔다
    idsim_telemetry/  # 수집기, 임시 WebSocket 어댑터(Phase 2)
    idsim_logger/     # rosbag2 기록/replay 제어
    idsim_fleet/      # Fleet Manager + gRPC 서버 + msg/proto 변환
    idsim_sim/        # ament_python 패키지. 월드 템플릿(worlds/idsim_base.sdf. 원점과 Actor는 생성 스크립트가 넣는다), 표적 어댑터 노드,
                      # 정답 pose 스크립트(sim_oracle.py), gui.config (GUI 설정), gazebo와 gz-gui wrapper 스크립트
  proto/             # gRPC/Protobuf 정의 (C++, Python, Rust가 같은 파일에서 생성)
  gateway/           # Rust 크레이트: gRPC -> WebSocket/HTTP gateway, Fleet 페이지
  missions/          # YAML 미션, 시나리오 정의
  tests/
    support/         # 정규화, 토픽 수신 확인, stack.json 로더, SITL 대기와 판정 함수(rclpy 없는 순수 코드), 통합 테스트의
                     # /fmu/in 발행 모듈(px4_raw.py) 등 스모크와 pytest가 공유하는 Python 모듈
    smoke/           # 환경 스모크 스크립트 (run_smoke.sh, capture.sh, check_px4.py)
    tools/           # 생성기 단위 테스트 (test_gen_compose.py. golden과 불변식 검사)
    fixtures/px4/<PX4_TAG>/  # golden 토픽 목록, 발행자 QoS, env (추적)
    fixtures/gen_compose/    # 생성기 golden: 케이스별 fleet.yaml, compose.yaml, stack.json (추적)
    sitl/            # SITL 통합 테스트. 호스트 wrapper run_sitl.sh, 전용 fleet.yaml, 시나리오(pytest. runner 컨테이너 안에서 실행)
  artifacts/         # 실행 로그, ULog, 원시 측정값, 생성된 compose와 stack.json과 노드 params(runs/<실행 id>/params/),
                     # 통합 테스트 산출물(runs/<실행 id>/sitl/) (비추적, CI job artifact로 업로드)
  docs/
```

## 테스트 자동화와 CI

테스트는 세 층으로 나누고, 모두 GitHub Actions에서 돌린다. 비용이 큰 시뮬레이션 테스트는 최소한으로 유지하고, replay 기반 테스트로 대부분을 대체하는 것이 핵심 전략이다.

| 층 | 도구 | 대상 | 실행 시간 목표 | trigger |
| --- | --- | --- | --- | --- |
| 단위 | GoogleTest (C++), pytest (Python) | `idsim_common` 좌표 변환, 토픽 매핑, 네임스페이스, 커맨드 빌더. `idsim_interfaces` 계약 테스트(type hash, 펼친 정의, 직접 정의 golden과 상수 검사). 미션 상태기(ROS 없이 시계와 입출력 포트를 주입한 순수 클래스). Fleet 배분 규칙. msg/proto 왕복 변환 | 1분 이내 | PR과 main push |
| replay 통합 | pytest + rosbag2 play | 기록된 MCAP으로 수집기, Fleet Manager의 레지스트리와 집계, WebSocket 어댑터, 판정 코드를 검증. 시뮬레이터, PX4 불필요. 배분 결정처럼 Executor의 반응이 필요한 경로는 replay로 검증되지 않는다 | 3분 이내 | 모든 push |
| SITL 통합 | pytest + Docker Compose (gz 서버 전용, GUI 없음) | 단일 기체 시나리오(이륙과 착륙, 미션 순회, 표적 추종) | 15분 이내 | PR 머리 커밋(draft와 문서만 바뀐 PR 제외), main push |
| SITL 통합 (멀티) | 위와 동일 | 3대 배분, 재배분 | 30분 이내 | nightly |

통합 테스트 구조. launch_testing은 ROS launch 파일용이라 compose 스택과 맞지 않으므로 쓰지 않는다. 호스트 wrapper `tests/sitl/run_sitl.sh`가 `tools/sim_stack.sh`로 스택을 올리고 내리며, pytest는 `runner`(ros-ws) 컨테이너 안에서 돌고 fixture는 이미 뜬 스택에 붙어 준비 상태를 검증만 한다(검증 실패는 skip이 아니라 오류다). `runner`에는 docker 소켓을 주지 않는다. 테스트 프로세스 안의 rclpy 노드가 토픽을 구독해 판정한다. 시험은 계약의 경계에서 끊어서 한다. Mission Executor의 통합 테스트는 `runner`가 기체의 버스에 붙어 `ExecuteMission`을 직접 부르고 기체 안의 토픽으로 판정하며, 지상 링크를 거치지 않는다. 지상 링크(Zenoh가 계약을 건네는지)는 그 구성이 생기는 Phase 3에서 별도의 시험으로 본다. 기체가 여러 대일 때 `runner`가 기체마다의 도메인에 붙는 방법은 정하지 않았다. Executor와 Collector는 lifecycle 노드이고 compose healthcheck가 active를 확인한다. 로컬과 CI는 같은 wrapper 명령을 쓰고, `--repeat N`은 회마다 콜드 스택으로 N번 돈다(자동 재시도 없음). 시나리오는 B(무효 미션), C(`vehicle_id` 불일치), A(이륙-호버-착륙), D(공중 취소 뒤 `[LAND]`), F1(waypoint 순회 뒤 착륙), F2(표적 접근 뒤 공중 Hold로 끝나는 미션), F3(F2의 Hold에서 시작해 RTL), F4(이륙, waypoint 순회, 표적 접근, RTL을 한 미션으로), T(묵은 timestamp의 Offboard 신호 판정)를 한 스택에서 이 순서로 돈다. B는 무효 사례(항목 순서 규칙 위반, 형식이 틀린 `target_id` 등)를 비행 없이 확인하고, F4가 Phase 1 목표의 미션 하나를 그대로 돌고, F1-F3은 공중에서 끝나는 미션과 공중에서 시작하는 미션 같은 경계 상황을 본다. 비행 시나리오 하나가 실패하면 뒤의 비행 시나리오는 돌리지 않고 실패로 센다. SITL 통합 테스트는 개발용 `config/fleet.yaml`이 아니라 전용 `tests/sitl/fleet.yaml`(F2와 F4의 표적 포함)로 스택을 올린다. CI `sitl` job의 시간 목표는 15분이다. 넘으면 판정 기준을 느슨하게 하지 않고 두 비행이 같은 판정을 보는 겹치는 구간, 순회 waypoint 수, Hold 유지 시간 순으로 줄이며, 공중 종료(F2)와 공중 시작(F3)은 빼지 않는다.

파이프라인 구성. (1) `lint`: clang-format, ruff, shellcheck, hadolint, actionlint, yamllint, 문자 집합 검사, 생성기 단위 테스트와 `compose config`, `idsim_common` 밖에서 /fmu 토픽 문자열을 쓰는지 보는 검사(`px4-api`. 대상은 `ros_ws/src`의 C++, `.py`, `.yaml`, 생성기 golden의 params, `tests/sitl/`과 `tests/support/`이고, 예외는 토픽 이름 함수 파일과 그 테스트(`tests/support/px4_topic.py`, `tests/support/test_px4_topic_names.py`)를 이름으로 적은 것뿐이다), 운용 패키지가 `/sim/` 토픽을 쓰는지 보는 검사(`sim-topic`. 아래 판정 입력 문단), cargo fmt와 clippy(Phase 3). ROS 환경이 필요 없는 검사만 둔다. (2) `build`: `ros-base` -> `sim-base` -> `px4`, `ros-ws`와 독립적인 `xrce-agent` 이미지를 x86_64와 arm64 Linux runner의 matrix로 빌드하고 레이어 cache를 쓴다. main은 플랫폼마다 `<이미지>:<key>-<arch>` 태그로 GitHub Container Registry에 올리고, 두 플랫폼이 모두 성공한 뒤 merge job이 key 태그를 multi-arch index로 만든다. PR은 push하지 않고, 이미지를 바꾸는 PR에서는 build job이 빌드한 이미지로 스모크 네 단계를 두 runner에서 돌린다. 이미지 key(이미지 구성 절)가 registry에 있으면 그 이미지의 빌드를 건너뛰므로, PX4는 `px4` key의 재료나 베이스 key가 바뀔 때만 다시 빌드한다. (3) `unit` + `replay`: 두 runner에서 `ros-ws` 이미지 안에서 `tools/ros_ws.sh ci`가 colcon build, colcon test(GoogleTest, `idsim_interfaces`의 pytest 계약 테스트, ament_lint의 xmllint, lint_cmake, cpplint), clang-tidy를 차례로 돌린다. clang-tidy와 ament_lint는 compile_commands.json과 ROS 헤더가 필요해 `lint`가 아니라 여기에 둔다. 테스트가 실패하거나 테스트 결과가 0건인 패키지가 있으면 실패한다. 로컬에서도 같은 명령을 쓴다. `replay`의 pytest는 Phase 2에서 더한다. (4) `sitl`: 두 runner에서 GHCR의 이미지를 받고(`tools/ci/build_images.py --mode pull`) `tools/ros_ws.sh build` 뒤 `tests/sitl/run_sitl.sh`로 시나리오를 돌린다. 실패 시 실행 디렉터리 전체(ULog, compose logs, ros_log, 판정 trace, junit)를 artifact로 올린다. MCAP 기록물의 업로드는 recorder가 생기는 Phase 2부터다.

테스트 판정 기준은 토픽에서만 읽고, 판정 입력은 두 부분으로 나눈다. 계약 판정은 계약 토픽과 PX4 토픽(`mission_event`, action의 feedback과 result, `vehicle_status`, `vehicle_land_detected`, `vehicle_local_position`, `TargetState`)만 쓴다. "arm/disarm"은 `vehicle_status.arming_state`, "미션 완료"는 `ExecuteMission` action 결과다. 정답 판정은 SITL 전용 정답 pose(`/sim/<vehicle_id>/pose`. Gazebo가 아는 기체 base_link의 world 위치)를 쓴다. "waypoint 도달"과 "표적 접근"은 정답 판정이다. waypoint 도달은 Executor가 항목을 완료로 넘긴 시각의 정답 위치와 world 목표의 거리로, 표적 접근은 정답 위치와 수신한 `TargetState`의 위치에 항목의 `offset`을 더한 점의 거리로 본다. Executor도 EKF 위치로 도달을 판정하므로 테스트가 `vehicle_local_position`으로 판정하면 EKF 오차와 원점 변환 오류가 양쪽에 같이 실려 보이지 않기 때문이다(노드가 낸 setpoint도 같은 이유로 판정 입력으로 쓰지 않는다). 판정 코드는 두 부분을 함수 수준에서 나누고, 정답 pose가 있어야 하는 실행에서 없으면 건너뛰지 않고 실패한다. timeout은 `/clock` 기준. 이렇게 해야 라이브와 replay가 같은 판정 코드를 공유한다. 정답 pose는 SITL 실행의 기록물(MCAP)에 함께 들어가므로 SITL 기록물의 replay는 두 부분을 모두 돌고, 정답 pose가 없는 기록물에서는 계약 부분만 돈다(실기체 기록물이 그렇다. 실기체 기록물의 replay는 계획에 넣지 않았다).

시뮬레이터 전용 토픽은 접두 `/sim/`을 쓰고 `idsim_interfaces`의 계약이 아니다. 운용 패키지(`idsim_common`, `idsim_mission`, 그리고 앞으로의 `idsim_telemetry`, `idsim_fleet`, `gateway/`)는 `/sim/`을 쓰지 않고, lint 항목 `sim-topic`이 그 소스, launch 파일, params YAML과 생성기 golden의 `params/ops-N.yaml`에서 `/sim/` 문자열을 찾는다(디렉터리 이름이 `test`나 `tests`인 곳은 이 문자열이 없음을 단정하느라 쓸 수 있어 제외한다). 운용 서비스가 시뮬레이터를 모른다는 원칙을 토픽 이름으로 지키는 장치다.

저장소는 공개이며 CI는 GitHub Actions 무료 runner의 한도 안에서만 쓴다. 공개 저장소의 기본 Linux runner는 4 vCPU, 16 GB 메모리이고, 더 큰 runner는 쓰지 않는다. 이 사양에서 Gazebo + PX4 1대 + 노드는 실시간에 가깝게 돌지만 3대는 실시간보다 느리다. arm64 runner(`ubuntu-24.04-arm`)도 공개 저장소에서 무료인 표준 runner이고 사양이 같다([GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)). 그래서 3대 시나리오는 처음부터 nightly 전용이고, PR에서는 단일 기체만 돌린다. `PX4_SIM_SPEED_FACTOR`를 1 이하로 내리는 옵션과 시뮬레이션 시간 기준 timeout으로 대응한다. 월 사용 시간 한도를 넘지 않도록 `sitl` job은 PR 머리 커밋당 runner마다 1회만 돌리고(같은 PR의 옛 실행은 취소한다) 자동 재시도 없이 재시도는 수동으로 한다.

## 참고 자료

- [PX4 ROS 2 User Guide](https://docs.px4.io/main/en/ros2/user_guide) - 버전 조합, uXRCE-DDS Agent, QoS, 좌표계 주의점
- [PX4 Multi-Vehicle Simulation with ROS 2](https://docs.px4.io/main/en/ros2/multi_vehicle.html) - 인스턴스, 네임스페이스, target_system 규칙
- [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/) - 환경변수, headless, 기체 목록
- [px4_msgs on ROS Index](https://index.ros.org/p/px4_msgs/) - Humble/Jazzy CI 빌드, 버전 라인
- [PX4 #24159](https://github.com/PX4/PX4-Autopilot/issues/24159) - Jazzy + 24.04 초기 이슈 보고
- [ROS 2 DDS 구현 선택](https://docs.ros.org/en/jazzy/Installation/DDS-Implementations.html) - rmw 전환 방법
- [Zenoh](https://zenoh.io/) - 지상 링크의 통신 방식
- [zenoh-plugin-ros2dds](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds) - ROS 2의 토픽, service, action을 Zenoh로 중계하는 bridge
