# 1a 6단계 의견서: devops-engineer

2026-11-11, devops-engineer

범위: 생성기(`tools/gen_compose.py`, `stack.json`), ros-ws 이미지, Lichtblick 이미지 고정, CI `sitl` job, 함께 처리할 미해결 항목. 구현은 하지 않았고, 판단 근거로 아래 "오늘 확인한 사실"의 조회만 했다(`idsim-0` 프로젝트는 건드리지 않았다).

## 0. 핵심 권고

1. 생성기는 식별값과 시간값만 생성 파일에 싣는다. 노드 튜닝값(타임아웃, 고도 허용오차 등)은 `idsim_mission` 패키지의 config에 두고 생성기는 모른다. 그래야 튜닝을 바꿀 때 생성기 golden이 흔들리지 않는다.
2. 노드는 이미지에 굽지 않는다(architecture.md의 기존 결정 유지). 저장소 마운트 위에서 `tools/ros_ws.sh build`로 만든 `ros_ws/install`을 쓴다. `stack.sh up`이 install이 없으면 안내와 함께 실패한다.
3. 기동 단계를 "인프라 3단계 + 노드 단계"로 나눈다. 스모크(`run_smoke.sh`)는 인프라 3단계만 올려 노드 빌드에 의존하지 않는다.
4. ros-ws에 foxglove_bridge를 넣는 변경은 6단계 기능 PR보다 먼저 작은 이미지 PR로 main에 합친다. 그래야 기능 PR의 unit과 sitl job이 GHCR에서 새 key를 받는다.
5. foxglove_bridge 버전은 `versions.env`의 `FOXGLOVE_BRIDGE_VERSION`에 두고, apt로 설치한 뒤 `dpkg-query` 결과가 그 버전인지 빌드에서 단정한다(ROS apt 저장소는 최신 하나만 남겨 정확한 pin이 곧 깨진다).
6. Lichtblick은 `versions.env`에 `LICHTBLICK_IMAGE=<이름>:<태그>@sha256:<amd64 manifest digest>` 한 줄로 고정한다. 진행 기록의 "Lichtblick 2.5.2"는 Lichtblick 버전이 아니라 베이스 Caddy의 라벨 값이다. 현재 최신 태그는 1.30.0이다.
7. Lichtblick은 host 네트워크라 포트 매핑이 안 된다. 기본 명령이 `:8080`(모든 인터페이스)을 열므로 command를 `caddy file-server --listen 127.0.0.1:<18080 + k>`로 덮어쓴다.
8. CI `sitl`은 별도 워크플로 `sitl.yml`. `pull_request`(draft 제외)와 `push: main`에서 돌고, 문서만 바뀐 PR은 job 수준에서 건너뛴다. 재시도는 수동(`workflow_dispatch` 또는 re-run). 예상 10-13분, `timeout-minutes: 30`.
9. pytest는 ros-ws 컨테이너(runner) 안에서 돌고 그 컨테이너에는 docker 소켓이 없다. 따라서 스택 기동과 정리는 호스트 쪽 wrapper(`tools/sitl_test.sh`, 가칭)가 하고 pytest fixture는 이미 뜬 스택에 붙는다. docker 소켓 마운트는 권하지 않는다.
10. GHCR 패키지 5종은 오늘 익명 manifest 조회가 200이다(이미 공개). `sitl`은 GHCR 로그인 없이 pull하며 포크 PR도 같은 경로로 돈다. 진행 기록의 "다음 작업 1"은 사용자 확인 뒤 닫을 수 있다.

## 오늘 확인한 사실 (2026-11-11)

- GHCR 익명 조회: `ghcr.io/danielhongwoo/idsim/{ros-base, ros-ws, px4, sim-base, xrce-agent}`의 현재 key(`tools/ci/image_keys.py` 출력: ros-base 9a4a9837507d2e44, ros-ws a0f1847b30f3b76f, sim-base cd6a22462ff15990, px4 81678f535f7e4b05, xrce-agent decfdd1ff03d1456) manifest가 토큰 없이(익명 pull 토큰) 모두 HTTP 200.
- 압축 크기(GHCR manifest 합): px4 631 MiB(sim-base, ros-base 레이어 포함), sim-base 608 MiB, ros-ws 420 MiB(ros-base 레이어 포함), xrce-agent 35 MiB. sitl이 받는 고유 레이어는 대략 0.9-1.0 GiB다.
- ROS apt(packages.ros.org noble main amd64): `ros-jazzy-foxglove-bridge` 3.6.0-1noble.20260930.003057, Installed-Size 41834 KiB. 새 의존은 `resource-retriever`, `rosx-introspection`, `libcurl-vendor`(curl, libcurl4-openssl-dev) 정도다.
- Lichtblick: `ghcr.io/lichtblick-suite/lichtblick` 태그 30개, 최신 1.30.0(`latest`와 같은 index digest sha256:25333a8f57737c8c5866abf75670b8dcf2ed6c2cb5ce3d64f3c63f210a5177e9). 1.30.0의 linux/amd64 manifest digest는 sha256:285adff96f24c80b511cf159e97e5395a6b154126c70c62d1199456009de07cc, 압축 55 MiB.
  - 이미지 config의 라벨은 Caddy 것(`org.opencontainers.image.version: v2.5.2`, title Caddy)이다. 진행 기록 2026-11-06 결정과 미해결 항목의 "2.5.2"는 이 값을 Lichtblick 버전으로 잘못 읽은 것으로 보인다. 고쳐야 한다(progress.md는 이번에 고치지 않았다).
  - ExposedPorts 8080 외, Cmd `caddy file-server --listen :8080`, Entrypoint `/bin/sh /entrypoint.sh`, User 미지정(root).
  - entrypoint.sh: `/lichtblick/default-layout.json`이 있으면 그 내용을 `index.html`의 placeholder에 넣고 `exec "$@"`. `set -e`가 없다.
- 현재 ros-ws 이미지(로컬 옛 태그 기준)에 `rosbag2`, `rosbag2_storage_mcap`, `rclcpp_lifecycle`, `ros2lifecycle`이 이미 있다(ros-base의 `ros-jazzy-ros-base`에서 온다). MCAP 기록과 lifecycle CLI를 위해 이미지에 더할 것은 없다.
- 최근 CI: unit job(push, feat/1a-6-takeoff-land) 1분 40초로 통과. main build는 key가 모두 있어 건너뛰는 상태.

## 1. 생성기 변경

### 1-1. `stack.json` 기체 항목의 `vehicle_id`

- 위치: `vehicles[].vehicle_id`(문자열, 예 `px4_1`). `ns`, `px4_ns` 옆에 둔다.
- 값은 지금 `px4_ns`와 같다. 둘을 합치지 않는다. `px4_ns`는 PX4 환경변수(`PX4_UXRCE_DDS_NS`)에 넣는 값이고 `vehicle_id`는 계약 메시지의 식별자다. 실기체 전환이나 네임스페이스 규칙 변경 때 둘이 갈라질 수 있다. 대신 생성기의 `assert_invariants`가 `vehicle_id == ns[1:]`와 "토큰 하나(`/` 없음)"를 단정한다.
- schema는 1을 유지한다(key 추가만). `GENERATOR_VERSION`은 2 -> 3. 로더(`tests/support/stack.py`, test-engineer 소유)에 `vehicle_id` 접근자와 필수 key를 더하고, 옛 산출물 호환이 필요하면 로더가 "없으면 실패"로 둔다(6단계 이전 run 디렉터리를 6단계 테스트가 읽을 일은 없다).

### 1-2. 노드 params 파일

- 경로: `artifacts/runs/<run_id>/params/<서비스>.yaml`. 컨테이너 안에서는 `/opt/idsim/artifacts/runs/<run_id>/params/...`로 보인다. 저장소 마운트 하나로 보이므로 새 바인드 마운트가 없다(중첩 마운트 금지 규칙 유지).
- `stack.json`에 `vehicles[].params_file`(실행 디렉터리 기준 상대 경로)과 `run.params_dir: "params"`를 싣는다.
- 내용(기체당 하나, `mission-N.yaml`):

```yaml
/px4_1/mission_executor:          # 노드 FQN. 이름은 ros2-engineer가 정한다
  ros__parameters:
    vehicle_id: px4_1
    target_system: 2              # stack.json vehicles[].sysid. VehicleCommand 대상
    use_sim_time: true
    autostart: true               # lifecycle 자기 활성화(1-3 참고). 이름과 존재 여부는 ros2-engineer
```

- 생성기가 쓰는 key는 식별과 시간뿐이다(`vehicle_id`, sysid, `use_sim_time`, 활성화 플래그). 튜닝값은 패키지의 `config/*.yaml`을 두 번째 `--params-file`로 겹쳐 쓴다. 순서는 패키지 기본 -> 생성 파일(나중 것이 이긴다).
- FQN key와 `/**` wildcard 중 무엇을 쓸지는 ros2-engineer가 정한다. 내 선호는 FQN이다. Phase 2에 Collector가 같은 component container에 들어오면 노드별로 다른 값이 필요할 수 있고, 잘못된 노드 이름은 "parameter 미적용"으로 조용히 넘어가므로 노드가 `vehicle_id` 미설정을 시작 실패로 처리해 주어야 한다(ros2-engineer 요청).
- YAML은 PyYAML `safe_dump(sort_keys=True)`로 쓴다. golden 비교가 바이트 단위라 key 순서를 고정한다.

### 1-3. `mission-N` 서비스

- 이름: `mission-N`(기체당 하나, `px4-N`과 같은 규칙). 3대 golden에는 `mission-1..3`이 나온다. Phase 2에 Collector가 같은 component container로 들어오면 서비스 이름이 역할과 어긋나므로, 그때 바꾸기 싫으면 지금 `vehicle-N` 같은 중립 이름을 쓴다. architecture.md 표의 `ros-ws` 서비스가 이것이며, 표 갱신은 architect 몫이다.
- 이미지: ros-ws(`images.ros_ws`). 사용자 uid:gid, `ROS_LOG_DIR=<run>/ros_log/mission-N`, 기존 `ros_ws_service()` 헬퍼 재사용.
- command(예):

```
ros2 run idsim_mission <실행 파일> --ros-args
  -r __ns:=/px4_1
  --params-file /opt/idsim/ros_ws/install/idsim_mission/share/idsim_mission/config/<기본>.yaml
  --params-file /opt/idsim/artifacts/runs/<run_id>/params/mission-1.yaml
```

  실행 파일 이름, 단독 실행 파일인지 component container(`component_container` + load)인지는 ros2-engineer가 정한다. 생성기는 어느 쪽이든 command 목록만 바꾸면 된다. launch 파일은 생성하지 않는다(기존 결정).
- depends_on: `bridge`(healthy)와 해당 `px4-N`(healthy). bridge가 이미 모든 px4에 의존하지만 기체 대응을 명시해 둔다.
- healthcheck: lifecycle 상태가 active인지.

```
. /opt/ros/$${ROS_DISTRO}/setup.sh && . /opt/idsim/ros_ws/install/setup.sh &&
ROS_LOG_DIR=/tmp/hc timeout 8 ros2 lifecycle get --no-daemon /px4_1/mission_executor | grep -q '^active'
interval 30s, timeout 10s, retries 3, start_period 60s, start_interval 5s
```

  bridge와 같은 패턴(`start_interval`로 기동 중에만 촘촘히, 이후 30초)이다. `ros2 lifecycle get`이 `--no-daemon`을 받는지와 출력 형식(`active [3]`)은 구현 때 실측한다. CLI 한 번이 4 vCPU에서 2-4초 걸릴 것으로 보이므로 timeout은 10초로 둔다.
- 전제: 노드가 외부 호출 없이 active까지 가야 `up --wait`가 끝난다. 노드 자기 활성화(autostart parameter) 또는 노드와 같은 프로세스의 관리자 중 무엇으로 할지는 ros2-engineer가 정한다. fixture가 configure/activate를 직접 부르는 방식이면 이 healthcheck는 "inactive 이상"으로 바꿔야 하고 compose의 "모두 healthy" 순서 규칙이 약해진다. 나는 자기 활성화를 권한다.
- runner의 depends_on을 `bridge`에서 `mission-1..N`으로 바꾼다. `run_smoke.sh`는 `compose run --no-deps`라 영향이 없다.
- embedded 변형에는 `mission`, `foxglove`, `lichtblick`을 만들지 않는다(`/clock` 브리지가 없어 `use_sim_time`이 성립하지 않는다). embedded는 S1b 진단용으로만 남는다.

### 1-4. 기동 단계와 스모크

- `stack.json`의 `startup.stages`는 지금 그대로 인프라 3단계로 두고 `startup.node_stages: [["mission-1", ...]]`를 더한다.
- `tools/stack.sh up`은 인프라 3단계 -> 모델 사전 검사 -> 노드 단계 순서로 `up --wait`. 새 옵션 `--infra-only`면 노드 단계를 건너뛴다. `run_smoke.sh`는 `--infra-only`를 쓴다. 이유: 스모크(S2-S5)는 PX4, Gazebo, DDS 회귀 판정이고, 노드 빌드 실패나 노드 버그가 스모크를 깨면 원인 분리가 안 된다(결정 (k)의 "변수 분리는 기동 단계가 맡는다"와 같은 원리).
- 노드 단계 실패 시 진단: 기존 `report_bad_services`에 더해 `mission-N` 로그 마지막 50줄을 stderr로 찍는다.
- install 사전 검사: 노드 단계 전에 `ros_ws/install/idsim_mission/`이 없으면 "`tools/ros_ws.sh build`를 먼저 하라"로 실패한다. 선택 옵션 `stack.sh up --build`는 up 전에 `tools/ros_ws.sh build`를 부른다. 스택이 떠 있는 동안 install을 바꾸는 경고는 `ros_ws.sh`에 이미 있다.
- 재현성 보강(권고, 필수 아님): `ros_ws.sh build`가 `ros_ws/install/.idsim_build.json`({git_commit, git_dirty, built_at})을 남기고 생성기가 이를 `stack.json.inputs.ros_ws_install`로 옮긴다. 실행 디렉터리만 보고 어떤 노드 코드로 돌았는지 알 수 있다.

### 1-5. bridge 설정 파일

- `artifacts/runs/<run_id>/params/bridge.yaml`(ros_gz_bridge `config_file` 형식)을 생성하고 command를 `ros2 run ros_gz_bridge parameter_bridge --ros-args -p config_file:=<경로>`로 바꾼다.

```yaml
- ros_topic_name: /clock
  gz_topic_name: /clock
  ros_type_name: rosgraph_msgs/msg/Clock
  gz_type_name: gz.msgs.Clock
  direction: GZ_TO_ROS
```

- 1a에는 `/clock` 한 줄뿐이라 정적 파일로도 되지만, 1b에서 `fleet.yaml`의 `targets`로 줄이 늘어나므로 지금 생성기로 옮긴다. healthcheck는 그대로(`/clock` 1회 수신).
- `/clock`의 발행 QoS가 CLI 인자 방식과 같은지 S5를 다시 돌려 확인한다(S5는 `/clock` 발행자 수 1과 수신을 본다). 미해결 항목 "bridge healthcheck의 `ROS_LOG_DIR=/tmp/hc` 뒤 run 디렉터리에 로그가 안 생기는지"도 이때 같이 본다.

### 1-6. `viz` 프로필: `foxglove`와 `lichtblick`

`foxglove`

- ros-ws 이미지, `profiles: [viz]`, 사용자 uid:gid, `ROS_LOG_DIR=<run>/ros_log/foxglove`, depends_on `bridge`(viz -> 본 스택 방향은 허용).
- command: `ros2 run foxglove_bridge foxglove_bridge --ros-args --params-file <run>/params/foxglove.yaml`.
- 생성 params(값은 `stack.json`에서):

```yaml
foxglove_bridge:
  ros__parameters:
    address: 127.0.0.1
    port: 8765                       # 8765 + k
    use_sim_time: true
    capabilities: [connectionGraph]  # clientPublish, services, parameters, parametersSubscribe, assets 제외
    topic_whitelist: ['^/px4_1/.*', '^/clock$']   # 기체마다 한 줄, vehicles[].ns에서 생성
    service_whitelist: ['^$']
    param_whitelist: ['^$']
```

- 화이트리스트는 기체 네임스페이스 접두로만 만든다. `/fmu/out/...` 같은 PX4 토픽 이름을 생성기에 적지 않는다. 이유: PX4 토픽 이름의 단일 출처는 `idsim_common`이고(px4-api 검사의 취지), PX4 토픽이 바뀔 때마다 생성기 golden이 흔들리지 않게 하려는 것이다. 읽기 전용이고 127.0.0.1에만 열리므로 기체 네임스페이스 전체를 보여도 위험이 늘지 않는다.
- parameter 이름과 capabilities 값은 foxglove_bridge 3.6.0 기준으로 구현 때 `ros2 param list`로 확인한다. clientPublish를 뺀 상태에서 Lichtblick이 연결을 유지하는지도 함께 본다.
- healthcheck 없음(viz는 `up --wait` 대상이 아니다).

`lichtblick`

- 이미지: `stack.json.images.lichtblick` = `versions.env`의 `LICHTBLICK_IMAGE`(3절).
- `profiles: [viz]`, `network_mode: host`, `restart: no`, 사용자는 root(entrypoint가 이미지 안의 `index.html`을 다시 쓴다. 호스트에 쓰는 마운트가 없으므로 uid 규칙 대상이 아니다).
- command: `["caddy", "file-server", "--listen", "127.0.0.1:18080"]`(18080 + k). 기본 Cmd는 `:8080`이라 모든 인터페이스에 열리고 스택 간에 충돌한다.
- 선택: 기본 레이아웃 `params/lichtblick-layout.json`(setpoint와 `vehicle_local_position`을 한 플롯에 놓는 레이아웃)을 `/lichtblick/default-layout.json`에 읽기 전용 바인드. entrypoint의 `touch`가 읽기 전용 파일에서 실패하지만 `set -e`가 없어 계속 진행할 것으로 보인다(구현 때 확인). 레이아웃 JSON 안의 토픽 이름은 PX4 토픽이므로 생성기가 아니라 저장소에 추적하는 정적 파일(`idsim_sim` 또는 `config/viz/`)로 두고, 기체 네임스페이스만 생성 때 치환한다. 레이아웃은 1a 완료 기준이 아니므로 뒤로 미뤄도 된다.
- depends_on 없음(브라우저가 foxglove에 직접 붙는다).
- `stack.sh up --viz`가 접속 주소를 안내한다: `http://127.0.0.1:<18080 + k>/?ds=foxglove-websocket&ds.url=ws://127.0.0.1:<8765 + k>`. 이 질의 매개변수를 Lichtblick이 받는지는 브라우저 실접속 때 확인한다(받지 않으면 수동 연결 안내로 바꾼다).

`stack.json`의 `services.foxglove`, `services.lichtblick`, `services.profiles.viz`, `images.lichtblick`이 지금 null이거나 빠져 있으므로 채운다. 포트 계획(`port_ranges`)에는 두 포트가 이미 들어 있다.

### 1-7. 생성기 단위 테스트와 golden 4종 갱신 범위

| golden | 바뀌는 것 |
| --- | --- |
| `1대-k0` | stack.json(`vehicle_id`, `params_file`, `node_stages`, services, images.lichtblick, generator version), compose.yaml(`mission-1`, `foxglove`, `lichtblick`, bridge command, runner depends_on), 새 파일 `params/{mission-1, foxglove, bridge}.yaml` |
| `1대-k3` | 위와 같고 포트(8768, 18083), 도메인 23이 들어간 것을 확인하는 용도 |
| `3대-k0` | 위와 같고 `mission-1..3`, params 3개, 화이트리스트 3줄 |
| `embedded` | stack.json만(`vehicle_id`, generator version, 새 key의 null 값). compose.yaml은 그대로여야 한다 |

- golden 비교를 "생성 디렉터리 전체 트리와 golden 디렉터리 전체 트리의 파일 집합과 바이트 일치"로 바꾼다(지금은 compose.yaml과 stack.json 두 파일). params 파일이 빠지거나 남는 것을 잡는다.
- 더할 성질 검사: `vehicle_id == ns[1:]`이고 `/`가 없다, params 파일의 `vehicle_id`와 sysid가 stack.json과 같다, `mission-N`이 `px4-N`과 `bridge`에 healthy로 의존한다, 어떤 본 스택 서비스도 `foxglove`/`lichtblick`에 의존하지 않는다(기존 viz 검사가 덮는다), foxglove params의 address와 lichtblick의 `--listen`이 127.0.0.1이고 포트가 stack.json과 같다, foxglove capabilities에 clientPublish, services, parameters가 없다, `LICHTBLICK_IMAGE`에 `@sha256:`가 있다, 생성 파일 어디에도 `fmu/`가 없다, embedded에는 노드와 viz 서비스가 없다.
- lint job의 `compose config -q`는 golden compose.yaml을 그대로 검사하므로 자동으로 새 서비스까지 덮는다.

## 2. ros-ws 이미지

- 변경: `Dockerfile.ros-ws`의 apt 목록에 `"ros-${ROS_DISTRO}-foxglove-bridge"`를 더하고 `ARG FOXGLOVE_BRIDGE_VERSION`(기본값 없음, 빈 값 검사)을 받는다. 설치 뒤 다음을 단정한다.

```
v="$(dpkg-query -W -f='${Version}' "ros-${ROS_DISTRO}-foxglove-bridge")"
case "$v" in "${FOXGLOVE_BRIDGE_VERSION}"-*) ;; *) echo "foxglove-bridge ${v} != ${FOXGLOVE_BRIDGE_VERSION}" >&2; exit 1 ;; esac
```

- `versions.env`: `FOXGLOVE_BRIDGE_VERSION=3.6.0`(조회일 주석 포함). `docker-bake.hcl`의 ros-ws args에 한 줄, `ENV IDSIM_BUILD_FOXGLOVE_BRIDGE_VERSION`을 더해 `ros_ws.sh`의 이미지 대조와 스모크 S0가 자동으로 확인하게 한다.
- 정확한 pin(`=3.6.0-1noble.20260930.003057`)을 쓰지 않는 이유: packages.ros.org는 동기화마다 최신 빌드 하나만 남기므로 다음 동기화 뒤 콜드 빌드가 "패키지 없음"으로 깨진다. upstream 버전 단정은 3.6.x 다음 판이 나왔을 때 "버전이 바뀌었다"는 분명한 실패를 주고, 같은 3.6.0의 재빌드(빌드 날짜만 다른 것)는 통과시킨다. ROS apt 서명 key를 지문으로 검증하는 기존 방식과 같은 원리다. snapshots.ros.org로 날짜 고정하는 안은 sources 설정이 늘어 이번에는 미룬다.
- 크기: foxglove_bridge 본체 약 41 MiB(Installed-Size)와 의존(libcurl 개발 패키지, rapidjson-dev 등)으로 50-70 MB 증가 예상. ros-ws 1.99 GB -> 약 2.05 GB. 4단계 때 예상보다 커진 전례가 있으므로 빌드 뒤 실측해 진행 기록에 남긴다.
- image key: `Dockerfile.ros-ws` 바이트와 새 `versions.env` 줄 때문에 ros-ws key만 바뀐다. ros-base, sim-base, px4, xrce-agent key는 그대로다.
- PR 분리: 이 변경은 6단계 기능 PR 전에 단독 PR로 합친다. 같은 PR에 섞으면 그 PR의 unit job과 sitl job이 GHCR에서 새 key를 찾지 못해 runner에서 ros-base부터 다시 빌드한다(unit 기준 약 8-10분 증가, sitl은 시간 예산 초과 위험). 단독 PR이 main에 합쳐지면 build job이 새 key를 올리고 이후 PR은 pull로 끝난다.
- 노드를 이미지에 넣지 않는다(architecture.md의 기존 결정 유지). 이유는 그대로다: 소스를 COPY하면 커밋마다 key가 바뀌어 PR마다 이미지 재빌드와 푸시가 생긴다. 산출물 경로는 `ros_ws/install`(호스트 저장소, 호스트 사용자 소유)이고 컨테이너 안 `/opt/idsim/ros_ws/install`로 보인다. `ros-ws-entrypoint.sh`가 이미 이 overlay를 source하므로 compose에 새 마운트가 필요 없다. 빌드 타입은 `ros_ws.sh`의 RelWithDebInfo를 그대로 쓴다.

## 3. Lichtblick 이미지 고정

- `versions.env`에 한 줄.

```
# Lichtblick 웹 앱(viz 프로필의 lichtblick 서비스). 어떤 Dockerfile의 ARG도 아니므로 이미지 key에 영향이 없다.
# 태그와 linux/amd64 manifest digest를 함께 적는다(조회일 2026-11-11). 이미지 라벨의 v2.5.2는 베이스 Caddy 버전이다.
LICHTBLICK_IMAGE=ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:285adff96f24c80b511cf159e97e5395a6b154126c70c62d1199456009de07cc
```

- digest는 `UBUNTU_IMAGE`와 같은 규칙(linux/amd64 manifest digest)을 쓴다. index digest(sha256:25333a8f...)를 쓰면 arm64 등 다른 플랫폼 변화에도 값이 바뀌는데 우리는 amd64만 쓴다.
- 생성기가 `versions.env`에서 이 줄을 읽어 `images.lichtblick`과 compose `image:`에 그대로 넣는다(생성기는 이미 versions.env의 sha256을 inputs에 기록한다). 값이 없거나 `@sha256:`가 없으면 생성 실패.
- 갱신 절차(docker/README.md에 적는다): 태그 목록 확인 -> 새 태그의 amd64 manifest digest 조회 -> `versions.env` 한 줄 수정 -> `stack.sh up --viz`로 브라우저 접속 확인. 버전을 바꿀 때 foxglove_bridge의 서브프로토콜 호환(지금은 foxglove.sdk.v1)을 같이 본다.
- 1.30.0으로 정한 근거는 "지금 최신"뿐이다. foxglove_bridge 3.6.0과의 브라우저 실접속(미해결 항목)이 이 버전으로 통과하면 확정한다. 실패하면 서브프로토콜을 기준으로 앞 버전을 고른다.
- CI는 viz를 켜지 않으므로 Lichtblick 이미지를 받지 않는다. lint의 `compose config`는 이미지를 받지 않고 문자열만 검사한다.

## 4. CI `sitl` job

### 4-1. 워크플로 구성

```
name: sitl
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  push:
    branches: [main]
  workflow_dispatch:
permissions: { contents: read }
concurrency:
  group: sitl-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  changes:   # git diff로 코드 경로 변경 여부만 판단(외부 action 없이)
  sitl:
    needs: changes
    if: github.event.pull_request.draft != true && needs.changes.outputs.code == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 30
```

- trigger: `pull_request`와 `push: main`만. 브랜치 push에는 걸지 않는다(lint와 unit이 같은 저장소 PR에서 두 번 도는 문제를 반복하지 않는다). `cancel-in-progress`로 PR의 옛 커밋 실행을 끊어 "PR 머리 커밋당 1회"가 되게 한다. 자동 재시도는 두지 않는다(architecture.md). 다시 돌릴 때는 re-run 또는 `workflow_dispatch`.
- "PR당 1회"의 해석: 나는 "머리 커밋당 1회, 자동 재시도 없음"으로 읽었다. 문자 그대로 "PR 하나에 한 번"이면 label trigger(`sitl` label을 붙일 때만)가 필요하다. 공개 저장소의 표준 runner는 사용 시간이 과금되지 않으므로(GitHub 정책, 정책 변경 여부는 주기적으로 확인) 비용보다 대기열과 피드백 시간이 기준이다. architect가 정한다.
- 경로 판단: 워크플로 수준 `paths` 필터는 쓰지 않는다. branch protection에서 `sitl`을 필수 검사로 걸면 필터로 워크플로가 안 뜬 PR이 영원히 대기한다. job 수준 `if`로 건너뛰면 skipped가 통과로 취급된다. 코드 경로: `ros_ws/**`, `docker/**`, `config/**`, `tools/**`, `tests/**`, `.github/workflows/sitl.yml`. 그 밖(`docs/**`, `docs-for-agent/**`, `*.md`)만 바뀐 PR은 건너뛴다.
- main push에서도 돈다. 머지 결과(여러 PR이 순서대로 합쳐진 상태)의 회귀를 잡는다.

### 4-2. 단계

1. checkout.
2. 이미지 확보: `tools/ci/build_images.py --mode pull xrce-agent sim-base px4 ros-ws`(새 모드, 5절). key가 GHCR에 있으면 pull 뒤 `idsim/<이미지>:local`로 tag, 없으면 레지스트리의 베이스 key를 `docker-image://` context로 쓰고 `buildcache`를 cache-from으로 받아 그 이미지만 `--load` 빌드. 익명 pull이 되므로 GHCR 로그인을 하지 않는다(포크 PR과 같은 경로). sim-base는 gazebo 서비스와 모델 사전 검사에 쓰인다.
3. `tools/ros_ws.sh build`(colcon, `--network none`). 스택 기동 전에 끝내 CPU 경합을 피한다.
4. `tools/sitl_test.sh --stack 0`(호스트 wrapper, 가칭. 4-3).
5. 실패 시 아티팩트 업로드, 항상 정리(4-4).

### 4-3. 호스트 wrapper와 fixture의 경계

- architecture.md는 "pytest fixture가 `docker compose up --wait`로 스택을 올리고"와 "pytest는 ros-ws 컨테이너 안에서 실행"을 함께 적는다. runner 컨테이너에는 docker CLI와 소켓이 없어 둘이 같이 성립하지 않는다.
- 권고: 호스트 wrapper가 `stack.sh up`(인프라 + 노드 단계) -> `compose run --rm runner pytest tests/integration --junitxml=<run>/junit.xml` -> 수집 -> `stack.sh down`. fixture는 `IDSIM_STACK_FILE`의 stack.json을 읽고 "스택이 이미 healthy"를 전제로 붙는다. 로컬의 "3회 연속 통과"도 같은 wrapper의 `--repeat 3`으로 돈다(회마다 down 뒤 up).
- docker 소켓을 runner에 마운트하는 안은 권하지 않는다. ros-ws 이미지에 docker CLI가 들어가고, 호스트 uid:gid로 도는 컨테이너에 docker 그룹을 줘야 하며, 사실상 호스트 root 권한이 테스트 컨테이너로 넘어간다.
- 이 경계는 test-engineer의 fixture 설계와 맞물린다. 4절의 가장 큰 충돌 후보다.

### 4-4. 기록과 아티팩트

- MCAP: 1a에는 `idsim_logger`가 없으므로 생성기가 `recorder` 서비스(ros-ws, 프로필 `record`, `ros2 bag record -s mcap --use-sim-time --regex '^/px4_[0-9]+/' -o <run>/bag`, `/clock` 제외)를 만들고 wrapper가 노드 단계 뒤에 올린다. 기록은 항상 하고 업로드는 실패 때만 한다. 대상 선정과 QoS 처리는 logging-engineer가 검토한다(Phase 2의 기록 정책으로 대체될 임시 구성).
- ULog: `px4-N/log/`(실행 디렉터리 바인드 마운트). `compose down`에서 ULog가 정상 종료되는지 미확인이므로, 수집 순서를 "recorder 정지 -> `compose stop -t 15 px4-N` -> 로그 수집 -> 업로드 -> down"으로 둔다.
- 수집: `docker compose logs --no-color > <run>/compose.log`, `docker compose ps -a`, junit.xml.
- 업로드(`if: failure()`): `artifacts/runs/<run_id>/` 전체(compose.yaml, stack.json, params, px4-N/log, ros_log, bag, compose.log, junit.xml)와 `ros_ws/log/`. retention 7일. 예상 크기: ULog 약 285 KiB/s로 5분 약 85 MB, MCAP 수십 MB, 합계 150 MB 이내. 성공 때는 junit.xml과 단계별 시간 요약만 올린다.
- `GITHUB_STEP_SUMMARY`에 단계별 초(이미지 확보, colcon build, 단계별 up, pytest, 수집)와 Gazebo RTF(가능하면 `/stats` 한 번)를 표로 남긴다. 4 vCPU에서 실시간에 가까운지 추세를 본다.

### 4-5. 시간 예산(무료 runner 4 vCPU, 16 GB)

| 단계 | 예상 | 근거 |
| --- | --- | --- |
| checkout, 준비 | 0.5분 | |
| 이미지 pull | 2-4분 | 고유 압축 레이어 약 1 GiB, px4 3 GB 풀기가 대부분 |
| colcon build | 2-3분 | idsim_common 33초(로컬 4 vCPU 콜드), interfaces rosidl 생성과 mission 추가 |
| 스택 기동 | 2-3분 | gazebo start_period 90초 상한, px4 연결, bridge, mission 활성화 |
| 이륙-호버-착륙 테스트 | 2-3분 | 시뮬레이션 시간 기준 타임아웃 |
| 수집, 업로드, 정리 | 0.5-1분 | 실패 때 업로드가 더 걸린다 |
| 합계 | 10-13분 | architecture.md 목표 15분 이내 |

- 디스크: px4 3.07 GB + ros-ws 약 2.05 GB(ros-base 공유) + xrce-agent 0.15 GB로 약 4.5 GB. runner 여유(실측 86 GB)로 충분하고 정리 단계가 필요 없다. px4를 runner에서 빌드해야 할 때만 build-images.yml과 같은 디스크 정리를 한다.
- px4 key가 바뀌는 PR(PX4_TAG 변경)은 sitl 안에서 px4를 빌드하면 20분 이상 늘어 timeout을 넘는다. 규칙: 이미지 변경 PR을 먼저 합친다(2절과 같은 원칙). 그래도 같이 가야 하면 그 PR에서만 `workflow_dispatch`로 timeout을 늘린 실행을 쓴다.

### 4-6. GHCR 공개 여부의 영향

- 오늘 익명 조회로 5종 모두 받을 수 있음을 확인했다. 따라서 sitl과 unit은 포크 PR에서도 pull로 끝난다.
- 만약 비공개로 돌아가면: 같은 저장소 PR과 main은 `GITHUB_TOKEN`(packages: read)으로 받을 수 있지만 포크 PR과 새 개발 PC는 받지 못해 sitl이 이미지 전체를 빌드하게 되고(콜드 약 22분) 시간 예산을 넘는다. 그 경우 포크 PR의 sitl은 건너뛰고 유지보수자가 `workflow_dispatch`로 돌린다. 공개 유지가 전제다.
- 사용자에게 확인 요청: 패키지 설정 화면에서 5종이 Public인지(익명 조회 결과와 일치하는지) 한 번 보고 진행 기록 "다음 작업 1"을 닫는다.

## 5. 함께 처리할 것과 미룰 것

함께 처리(6단계 PR들에 포함):

- `build_images.py --mode pull` 구현. sitl과 새 PC 재구성(README의 알려진 제약)이 모두 쓴다. unit.yml의 pull 분기도 이 모드로 바꿔 key가 없을 때 ros-base를 다시 빌드하지 않고 레지스트리 베이스를 쓴다.
- `gen_compose.sh`의 `--run-id` 제거(결정 (l)). 이번에 생성기 인자를 손대므로 같이 한다. `--run-dir`만 남고 run id는 basename이다. `run_smoke.sh`는 이미 `--run-dir`를 쓴다.
- sitl 워크플로의 trigger 규칙(`pull_request` + `push: main`)을 lint와 unit에도 맞춰 같은 저장소 PR의 이중 실행을 없앤다. 대가: PR 없는 브랜치 push에는 CI가 돌지 않는다. 작은 별도 PR이 낫다.
- `check_host.sh`에 Docker Engine 25 이상 점검(healthcheck `start_interval`은 Engine 25.0에서 도입). mission healthcheck도 `start_interval`을 쓰므로 미해결 항목 "start_interval 하한"을 여기서 닫는다.
- 손대는 워크플로와 `tools/ci/` 파일의 음차("키", "잡")를 key, job으로 고친다(미해결 항목).
- 진행 기록의 "Lichtblick 2.5.2" 정정(Caddy 라벨). progress.md 갱신 때.
- unit job 단계별 시간 3회 기록(4c 남은 일). sitl 첫 3회 시간도 같은 표에 남긴다.

미룰 것:

- apt 미러 재시도(`Acquire::Retries`)와 PR #14 처리: 사용자 결정 대기. sitl은 pull 경로라 영향이 적다.
- clang-tidy를 별도 도구 이미지로 분리(ros-ws 크기): foxglove 추가 뒤 실측 크기를 보고 사용자 알림으로 다시 올린다. 6단계에서 하지 않는다.
- `image_keys.py`가 bake 블록의 tags와 공백까지 해시하는 문제: key 방식 변경(SCHEME 올림)은 모든 이미지를 다시 빌드하게 하므로 PX4 태그 변경처럼 어차피 전체 재빌드가 있을 때 묶는다.
- snapshots.ros.org 날짜 고정, GZ_IP 제거 비교, VNC, 3대 nightly(Phase 3), `qgc.sh` 설정 되돌림 옵션.
- Lichtblick 기본 레이아웃 파일: 실접속 확인 뒤 여유가 있으면.

## 6. 다른 담당자와 맞출 지점

- ros2-engineer: 노드 FQN과 실행 형태(단독 실행 파일 또는 component container), lifecycle 자기 활성화 여부(compose healthcheck의 전제), params key 이름(`vehicle_id`, sysid key, 활성화 플래그), FQN key와 `/**` 중 선택, foxglove params 이름과 capabilities 값, 패키지 기본 params 파일 경로. 서비스 이름(`mission-N` 또는 중립 이름)은 Phase 2 Collector 배치와 같이 정한다.
- test-engineer: 스택 기동 주체(호스트 wrapper와 fixture의 경계, 4-3), junit 경로, `--repeat 3`의 회차 사이 down/up, 판정 타임아웃과 sitl job timeout(30분)의 관계, flaky 대응에서 자동 재시도를 두지 않는 규칙, 로더(`tests/support/stack.py`)의 `vehicle_id`와 `node_stages` 추가.
- px4-engineer: mission params의 대상 sysid(`stack.json` `sysid`에서), Hold 실험과 failsafe(`COM_OF_LOSS_T`) 판정을 sitl에 넣을지(넣으면 시간 예산 재계산), ULog 정상 종료를 위한 `compose stop` 유예 시간, 노드 단계를 스모크에서 빼는 것(S3 arm/disarm과 노드의 동시 발행 회피)에 동의하는지.
- logging-engineer(이번 토론 밖): 1a 임시 `recorder` 서비스의 대상 선정과 QoS, Phase 2 `idsim_logger`로의 교체 시점.
- architect: `vehicle_id`와 `px4_ns`를 별도 key로 두는 것, "PR당 1회" 해석, `stack.json` schema 1 유지(key 추가만), architecture.md의 fixture 문장과 서비스 표(`ros-ws` -> `mission-N`) 갱신.
