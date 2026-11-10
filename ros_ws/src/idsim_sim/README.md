# idsim_sim

Gazebo 시뮬레이션 쪽 설정과 노드를 모으는 패키지다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`를 따른다.

## 예정 역할

- 커스텀 월드와 표적 Actor(스크립트 궤적). 표적은 물리 모델이 아니라 Actor로 만들어 결정적이고 가볍게 한다.
- ros_gz_bridge 설정. 1a에서는 `/clock`만, 1b에서 표적 pose를 더한다.
- 표적 어댑터 노드. Gazebo 표적 pose를 `TargetState` 계약으로 변환해 발행한다. 운용 노드는 Gazebo 토픽을 직접 보지 않는다.
- launch 파일.

아직 ROS 패키지가 아니다(`package.xml` 없음). 노드가 생길 때 ROS 패키지로 만든다.

## 현재 들어 있는 것

- `config/gui.config`: Gazebo GUI 클라이언트(`gz sim -g`) 설정. gz-sim8 기본 설정에서 WorldControl 플러그인을 빼고 바닥 격자(GridConfig)를 더했다. 화면에서 실수로 월드를 일시정지하거나 스텝 실행해 시뮬레이션 시계를 멈추는 것을 막고, 균일한 회색 월드에서 기체 이동이 보이게 한다. 출처와 이유는 파일 첫머리 주석에 있다. `scripts/gz_gui.sh`가 `--gui-config`로 넘긴다.
- `scripts/gz_server.sh`: gazebo 서비스의 진입 스크립트(sim-base, root). 월드 SDF의 `<world name>`이 `IDSIM_WORLD_NAME`과 같은지 검사하고, `gz sim -r -s <IDSIM_WORLD_FILE>`을 자식으로 띄워 `/world/<이름>/scene/info`가 응답할 때까지(상한 60초) 기다린다. `IDSIM_ORIGIN_LAT/LON/ALT` 세 값이 모두 있으면 `set_spherical_coordinates`를 한 번 호출하고 `data: true`를 받으면 표시 파일 `/tmp/idsim/origin_set`을 남긴다. 세 값 중 일부만 있거나, 이름이 다르거나, 응답이 `data: true`가 아니면 종료 코드 1로 끝난다. 원점 단계가 끝나면(원점이 없어도) 준비 파일 `/tmp/idsim/ready`를 남긴다. TERM/INT는 자식 서버에 전달하고 5초 안에 안 끝나면 KILL한다(종료 코드 TERM 143, INT 130). `data: true`는 요청 수리일 뿐이라 원점의 실제 적용은 px4의 `sensor_gps` 좌표로 판정한다. healthcheck는 원점 유무와 무관하게 `gz service -i --service /world/<이름>/scene/info | grep -q "Service providers" && test -f /tmp/idsim/ready` 하나다(파일 머리 주석).
- `scripts/gz_gui.sh`: gz-gui 서비스(`viz` 프로필)의 진입 스크립트(호스트 uid:gid). `XAUTHORITY`를 마운트 지점 `/tmp/.Xauthority`로 스스로 정하고(compose env에 의존하지 않는다), `DISPLAY`가 비었거나 그 파일이 없거나 비었거나 읽을 수 없거나 GUI 설정 파일을 읽을 수 없으면 안내 메시지와 종료 코드 1로 끝낸다(gz는 설정 파일을 못 읽으면 경고만 내고 WorldControl이 있는 기본 설정으로 뜨기 때문이다). `HOME`에 쓸 수 없으면 `/tmp/gz-home`을 쓴다. 그 뒤 `gz sim -g --gui-config ${IDSIM_GUI_CONFIG:-/opt/idsim/sim/config/gui.config} --render-engine-gui ${IDSIM_GZ_GUI_ENGINE:-ogre2}`로 exec한다. `--render-engine-gui`는 `gui.config`의 `<engine>`을 덮는다(ogre를 주면 OGRE 1.9가 로드되고 격자도 보인다, 2026-11-09 실측).

두 스크립트는 이 패키지 디렉터리를 컨테이너의 `/opt/idsim/sim`에 읽기 전용으로 마운트해 쓴다(`/opt/idsim/sim/scripts/...`, `/opt/idsim/sim/config/gui.config`).
