# idsim_sim

Gazebo 시뮬레이션 쪽 설정과 노드를 모으는 패키지다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`를 따른다.

## 예정 역할

- 커스텀 월드와 표적 Actor(스크립트 궤적). 표적은 물리 모델이 아니라 Actor로 만들어 결정적이고 가볍게 한다.
- ros_gz_bridge 설정. 1a에서는 `/clock`만, 1b에서 표적 pose를 더한다.
- 표적 어댑터 노드. Gazebo 표적 pose를 `TargetState` 계약으로 변환해 발행한다. 운용 노드는 Gazebo 토픽을 직접 보지 않는다.
- launch 파일.

아직 ROS 패키지가 아니다(`package.xml` 없음). 노드가 생길 때 ROS 패키지로 만든다.

## 현재 들어 있는 것

- `config/gui.config`: Gazebo GUI 클라이언트(`gz sim -g`) 설정. gz-sim8 기본 설정에서 WorldControl 플러그인을 빼고 바닥 격자(GridConfig)를 더했다. 화면에서 실수로 월드를 일시정지하거나 스텝 실행해 시뮬레이션 시계를 멈추는 것을 막고, 균일한 회색 월드에서 기체 이동이 보이게 한다. 출처와 이유는 파일 첫머리 주석에 있다. sim-base 컨테이너에 읽기 전용으로 마운트해 `gz sim -g --gui-config <경로>`로 쓴다.
