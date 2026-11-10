# 1a 6번 작업 devops-engineer 의견

작성 2026-11-10, devops-engineer. 질문지 `questions.md`의 D1-D11에 답한다.

공통 조건. 실험은 모두 scratchpad(`/tmp/claude-1000/.../scratchpad/d1`-`d8`)의 사본이나 1회성 컨테이너에서 했고 저장소 파일은 바꾸지 않았다. 실측하는 동안 호스트에는 다른 담당자의 스택 두 개(`idsim-1`, `idsim-5`, 각각 agent, gazebo, px4-1, bridge)가 떠 있었다(D8만 예외, 그 절에 적는다). GUI는 띄우지 않았다.

## D1. `stack.json`의 `vehicle_id`

- [실측] 생성기 사본(`d1/`)의 기체 항목에 `"vehicle_id": f"px4_{n}"` 한 줄을 넣고 `GENERATOR_VERSION`을 2 -> 3으로 올린 뒤 ros-ws 컨테이너(`--network none`)에서 `pytest tests/tools --update-golden`. golden diff는 `stack.json` 4개뿐이고 16줄 추가, 10줄 삭제(1대 golden 3개는 각 `generator.version` 1줄과 `vehicle_id` 1줄, 3대 golden은 기체 3개). `compose.yaml` golden 4개는 바뀌지 않았다.
- [실측] `tests/support/stack.py`의 `_VEHICLE_SPEC`에 `"vehicle_id": _STR`를 더하면 `tests/support/test_stack.py`의 손으로 쓴 표본 2개(123행, 266행 근처)에 필드가 없어 9건이 "필수 필드 누락: vehicles[0].vehicle_id"로 실패한다. 표본 두 곳에 한 줄씩 더하고 `Vehicle` dataclass에 `vehicle_id: str`를 더하면 된다(test-engineer 소유).
- [실측] 지금 `px4_ns`의 값("px4_1")이 `vehicle_id`와 같다.
- 의견. 위치는 `vehicles[]`의 항목, 이름은 계약 필드 이름 그대로 `vehicle_id`. 필수, null 불가. `schema`는 1로 둔다. 결정 (m)처럼 필드를 더하는 것은 하위 호환이고(로더는 모르는 필드를 무시한다) `generator.version`만 3으로 올린다.
- 의견. `px4_ns`와 값이 같아도 합치지 않는다. `px4_ns`는 `PX4_UXRCE_DDS_NS`에 넣는 PX4 쪽 값이고 `vehicle_id`는 계약 식별자다. 대신 `assert_invariants`에 `vehicle_id == ns.lstrip("/") == px4_ns`를 넣어 셋이 어긋난 stack.json이 생기지 않게 한다.
- 의견. 생성기 v2로 만든 옛 실행 디렉터리의 `stack.json`은 새 로더에서 읽히지 않는다. `artifacts/runs/`는 비추적이라 받아들인다.

## D2. 노드 params 파일

- [실측] ros-ws 이미지에서 rclpy 노드 `mission_executor`를 `-r __ns:=/px4_1 --params-file f.yaml`로 띄우고 노드 이름 키별로 적용 여부를 봤다(`d2/`, 각 1회, `automatically_declare_parameters_from_overrides=True`).

| 노드 키 | 적용 |
| --- | --- |
| `/**` | 됨 |
| `/px4_1/mission_executor` | 됨 |
| `px4_1/mission_executor`(앞 빗금 없음) | 됨 |
| `mission_executor`(네임스페이스 없음) | 안 됨 |
| `/**/mission_executor`, `/*/mission_executor`, `/px4_1/*`, `/px4_1/**` | 됨 |
| `/px4_2/mission_executor`(다른 기체) | 안 됨, 오류 없음 |
| `/**`와 `/px4_1/mission_executor` 둘 다 | 둘 다 적용, 같은 key는 정확한 이름 쪽이 이김 |

- [실측] key가 맞지 않아 적용되지 않을 때 오류는 나지 않는다. 노드가 기본값 없이 타입만 주고 `declare_parameter("vehicle.vehicle_id", STRING)`하면 `get_parameter`가 `ParameterUninitializedException`을 낸다. 같은 파일을 노드 이름 키가 맞게 주면 값이 들어온다. 중첩 yaml `vehicle: {vehicle_id: px4_1}`은 `vehicle.vehicle_id`로 선언된다.
- [추정] 노드 이름 매칭은 rcl이 하므로 rclcpp lifecycle 노드에서도 같다고 본다. C++ 노드로는 확인하지 않았다(저장소 ros_ws를 빌드하지 않는다는 조건).
- 의견. 파일은 기체마다 하나, `artifacts/runs/<실행 id>/ros_params/<vehicle_id>.yaml`. `px4-N/`은 PX4 rootfs의 바인드 마운트라 거기에 두지 않는다. Phase 2의 Collector처럼 같은 기체의 노드가 늘면 같은 파일에 노드 섹션을 더한다.
- 의견. 노드 키는 와일드카드 없이 정확한 FQN `/<vehicle_id>/<노드 이름>`으로 쓴다. 다른 기체의 파일을 잘못 넘기면 값이 아예 들어오지 않아 선언 단계에서 바로 실패한다. `/**`를 쓰면 엉뚱한 식별 값이 조용히 들어가고 대조 함수까지 가서야 드러난다. 노드 이름은 ros2-engineer가 정할 상수라 생성기 상수로 하나 더 들고, stack.json의 기체 항목에 `ros_params_file`(실행 디렉터리 기준 상대 경로)을 싣는다.
- 의견. 생성기가 싣는 key는 fleet.yaml과 k에서 파생되는 값만이다: 식별(`vehicle_id`, `sysid`. 이름과 중첩은 R4에 따른다)과 `use_sim_time: true`. 네임스페이스는 command의 `-r __ns:=`로 주므로 params에 `ns`를 또 싣지 않는다(같은 값의 사본이 셋이 된다). 미션 노드의 조정 값(타임아웃, `acceptance_m`)은 싣지 않고 패키지 기본값으로 둔다. 생성기가 싣기 시작하면 fleet.yaml 스키마가 노드 조정 값까지 늘어난다.
- 의견. 타입. `sysid`는 int, `use_sim_time`은 bool, `vehicle_id`는 따옴표 문자열로 내보내고 단위 테스트가 yaml을 다시 읽어 타입을 단정한다(노드가 int로 선언했는데 문자열이 오면 타입 오류).
- 의견(B7). 생성된 params는 `artifacts/`(무시 대상)라 lint가 보지 않는다. 그래서 생성기 단정에 "params 값에 `fmu/`가 없다"를 넣는다. `idsim_mission`이 패키지 안에 `config/*.yaml`을 두면 `px4-api` 대상에 `ros_ws/src/**/*.yaml`을 더한다(지금은 C++과 `.py`만 본다).

## D3. 운용 노드 서비스

- [실측] 지금 bridge healthcheck(`ros2 topic echo --once --no-daemon /clock`) 한 번의 실행 시간은 1.43-1.75 s(`idsim-1-bridge-1`, `idsim-5-bridge-1`, docker 헬스 로그 각 5건, 두 스택이 떠 있을 때). px4 healthcheck(`uxrce_dds_client status`)는 0.05-0.07 s. `ros2` CLI healthcheck는 한 번에 DDS 참가자 하나를 만들고 1.5 s 안팎을 쓴다.
- 의견. 서비스는 기체마다 하나, 이름 `mission-N`(px4-N과 같은 규칙). Phase 3에서 기체 수만 바꾸면 그대로 늘어나고, `up --wait`가 실패하면 어느 기체인지 서비스 이름으로 바로 보인다. 기체당 컨테이너 하나의 메모리는 지금 bridge 기준 30 MB 안팎이라 3대여도 부담이 없다. 컴포넌트로 묶을지는 R2의 결론을 따르되, 묶더라도 서비스는 기체 단위로 둔다.
- 의견. command 초안: `ros2 run idsim_mission <실행 파일> --ros-args -r __ns:=/<vehicle_id> --params-file /opt/idsim/artifacts/runs/<id>/ros_params/<vehicle_id>.yaml`. 이미지는 ros-ws, 사용자 uid:gid, 저장소 마운트 하나, `ROS_LOG_DIR`는 `ros_log/mission-N`(지금 `ros_ws_service` 그대로). lifecycle 전이를 별도 프로세스(`ros2 lifecycle set`)로 거는 방식은 compose command가 셸 스크립트가 되고 프로세스가 둘이 되므로, 노드가 스스로 configure, activate를 거는 쪽(params 하나로 켜는 autostart)을 devops 쪽에서는 선호한다. 결정은 R3.
- 의견. healthcheck는 bridge처럼 `interval 30s, timeout 5s, retries 3, start_period 60s, start_interval 2s`로 시작한다. 명령은 `ros2 lifecycle get`이면 1.5 s와 참가자 하나가 매번 든다(위 실측의 bridge와 같은 꼴로 본다, [추정]). 더 싼 대안은 노드가 active에 들어갈 때 `/tmp/idsim/active`를 쓰고 나갈 때 지우며 healthcheck는 `test -f`만 하는 것이다(gazebo의 ready 파일과 같은 방식, 실행 0.05 s 수준, 참가자 없음). 이 대안은 노드 코드에 파일 쓰기가 들어가므로 ros2-engineer의 판단이 필요하다.
- 의견. `startup.stages`: standalone은 `[[xrce-agent, gazebo], [px4-1..N], [bridge], [mission-1..N]]`의 네 단계, `mission-N`의 `depends_on`은 `bridge`(healthy)와 자기 `px4-N`(healthy). embedded 변형에는 bridge가 없어 `/clock`이 오지 않으므로 `mission-N`을 생성하지 않는다(생성기가 단정한다).
- 의견. 4단계에서 실패하면 `stack.sh`는 지금 보고(문제 서비스, bind 오류)에 더해 `mission-N` 로그의 마지막 30줄을 stderr에 찍고 "식별 불일치나 `/clock` 미수신이면 여기 보인다"는 안내를 한다. 식별 불일치를 activate 실패로 할지(R5) 그대로 이 경로로 보고된다.
- 의견(D15). 스모크 S2-S5도 이 단계까지 올린다(결정 (k) 유지). S4 golden은 `fmu/` 아래 토픽 목록과 `fmu/out` 발행자 QoS만 담으므로(`docs/smoke-test.md` 산출물 절) `mission_event`나 action 토픽은 섞이지 않는다. 다만 두 조건이 필요하다. (1) Executor가 PX4가 구독하지 않는 `/fmu/in` 이름으로 발행하면 topics.txt에 새 줄이 생겨 S4가 실패한다. 이것은 원하는 검출이다. (2) Executor가 goal 없이 activate만 된 상태에서 `/fmu/in`에 아무것도 발행하지 않아야 S3(스모크의 arm, disarm 왕복)과 섞이지 않는다. 대가로 스모크가 `ros_ws/install`을 요구하게 된다(D4의 검사가 스모크에도 걸린다).

## D4. 빌드와 install 부재 검사

- [실측] 저장소의 `ros_ws`가 아니라 같은 커밋의 사본(`d4/repo`, `git archive HEAD`)을 사본의 `tools/ros_ws.sh build`로 콜드 빌드(build, install, log 삭제 뒤). 다른 스택 두 개가 떠 있을 때 1회: 94 s(colcon Summary 1 min 32 s, idsim_interfaces 1 min 27 s와 idsim_common 1 min 32 s가 병렬), 컨테이너 메모리 최대 871 MiB(`docker stats` 1 s 표본이라 실제 최대는 조금 더 클 수 있다), 호스트 available 최소 4651 MB(시작 5455 MB).
- [실측] 스택이 모두 내려간 상태의 빌드는 못 했다. 측정하는 내내 다른 담당자의 스택이 둘 이상 떠 있었다(D8 절).
- [실측] 빌드 산출물(`ros_ws/build`, `install`, `log`)은 모두 호스트 uid 1000:1000 소유. `find -not -uid 1000` 결과 없음.
- [실측] CI unit job(run 42829237730, main)의 `tools/ros_ws.sh ci`(build, test, tidy 합계)는 85 s, 그중 build가 약 55 s(로그의 idsim_interfaces 42.5 s 완료 시각에서 셈).
- 의견. `stack.sh up`은 생성 전에(컨테이너를 하나도 만들기 전에) 운용 노드 서비스가 생성될 변형이면 `ros_ws/install/setup.bash`와 `ros_ws/install/idsim_mission/` 둘 다 있는지 본다. 없으면 `stack.sh: ros_ws/install/idsim_mission이 없다. 먼저 tools/ros_ws.sh build를 돌려라(자동 빌드는 하지 않는다)`를 찍고 종료 코드 1(기존 실패 코드와 같다. 2는 인자 오류로 남긴다). install이 src보다 오래됐는지는 보지 않는다(정확히 보려면 colcon을 돌려야 한다).
- 의견. 빌드와 스택 가동을 막는 규칙은 두지 않는다. 메모리는 위 실측에서 빌드가 0.8 GB 정도라 스택 두 개와 함께여도 4.6 GB가 남았다. 남는 위험은 떠 있는 스택의 `.so`가 바뀌는 것이고 `ros_ws.sh`가 이미 경고한다. 판정이 `/clock` 기준이라 빌드로 RTF가 떨어져도 판정은 바뀌지 않아야 한다(S1 실측이 반증 지점).

## D5. ros-ws 이미지의 foxglove_bridge

- [실측] ros-ws 이미지(kr 미러, ROS apt) 안에서 `apt-cache policy`: 후보 `ros-jazzy-foxglove-bridge 3.6.0-1noble.20260930.003057`, Installed-Size 41834 KB. 함께 설치되는 것: `libcurl4-openssl-dev`, `rapidjson-dev`, `ros-jazzy-libcurl-vendor`, `ros-jazzy-resource-retriever`, `ros-jazzy-rosx-introspection`.
- [실측] scratch Dockerfile(`d5/Dockerfile`, `FROM idsim/ros-ws:local`에 apt 설치 RUN 하나)로 빌드: 새 레이어 49.6 MB, 빌드 14.5 s(베이스 cache 있음, 스택 두 개가 떠 있을 때). 저장소 Dockerfile을 바꾸지 않았으므로 새 이미지 key는 계산하지 않았다. `Dockerfile.ros-ws` 바이트가 바뀌므로 ros-ws key 하나만 바뀐다(key는 Dockerfile과 ARG 줄로 정해진다).
- [실측] Lichtblick. 진행 기록과 architecture.md의 "Lichtblick 2.5.2"는 Lichtblick 버전이 아니다. `ghcr.io/lichtblick-suite/lichtblick:latest`의 이미지 설정 레이블 `org.opencontainers.image.version: v2.5.2`는 베이스인 Caddy의 레이블이다(같은 설정의 title "Caddy", source caddy-docker). GHCR 태그 목록에 2.x 태그는 없고 최신은 `1.30.0`(GitHub release v1.30.0, 2026-10-22)이며 `latest`와 같은 index digest `sha256:25333a8f57737c8c5866abf75670b8dcf2ed6c2cb5ce3d64f3c63f210a5177e9`. amd64 manifest `sha256:285adff96f24c80b511cf159e97e5395a6b154126c70c62d1199456009de07cc`, 압축 57.6 MB, 풀어서 285 MB.
- [실측] 그 이미지의 JS 번들에 `foxglove.sdk.v1`과 `foxglove.websocket.v1` 문자열이 둘 다 있다(서브프로토콜 제시 여부의 간접 증거. 브라우저 접속은 S2).
- [실측] 이미지는 Caddy가 `:8080`(모든 주소)에서 정적 파일을 낸다. command를 `caddy file-server --listen 127.0.0.1:18084`로 바꾸면 127.0.0.1에만 열린다(`--network none` 컨테이너 안 wget로 index.html 수신). 기본 entrypoint `/bin/sh /entrypoint.sh`는 `/lichtblick/default-layout.json`을 index.html에 끼워 넣는다. uid 1000으로 실행해도 페이지는 나왔고, layout 주입이 non-root에서 되는지는 확인하지 않았다.
- 의견. `versions.env`에 `LICHTBLICK_IMAGE=ghcr.io/lichtblick-suite/lichtblick:1.30.0@sha256:25333a8f...`(LINT 이미지와 같은 태그@digest 꼴) 한 줄. 어느 Dockerfile의 ARG도 아니라 이미지 key에 영향이 없고, 생성기가 이 줄을 읽어 compose와 `stack.json`의 `images.lichtblick`에 싣는다. foxglove_bridge는 apt 버전을 고정하지 않는다(ROS apt는 최신 하나만 남겨 고정하면 빌드가 깨진다. 지금 다른 apt 패키지도 고정하지 않는다). 대신 스모크 S0이 이미지 안 `dpkg-query` 버전을 artifacts에 남긴다.
- 의견. `Dockerfile.ros-ws`에는 기존 apt RUN에 넣지 않고 px4_ws 빌드 RUN 뒤에 별도 RUN으로 둔다. 기존 RUN에 넣으면 그 뒤 px4_msgs colcon 빌드 레이어까지 cache가 깨진다. buildcache(mode=min)는 최종 이미지 레이어를 담으므로 별도 RUN이면 CI에서 px4_msgs 레이어를 재사용한다([추정], buildcache 적중은 PR에서 확인).
- 의견. 이미지 변경은 앞쪽 PR로 분리하는 데 찬성한다. main에 먼저 들어가 새 key가 GHCR에 올라가야 뒤의 PR들의 unit과 sitl job이 이미지를 받기만 한다. key가 없으면 unit job이 ros-base부터 다시 빌드한다(unit.yml 주석). 같은 PR에서 architecture.md의 "Lichtblick 2.5" 표기 정정을 architect에게 요청한다.

## D6. `viz` 서비스

- [실측] D5의 scratch 이미지로 `--network none` 컨테이너에서 `foxglove_bridge`를 `-p address:=127.0.0.1 -p port:=8769 -p "topic_whitelist:=['^/px4_[0-9]+/fmu/out/.*', '^/px4_[0-9]+/mission_event$']" -p "capabilities:=[connectionGraph]"`로 띄우고, 토픽 셋(`/px4_1/fmu/out/vehicle_status_v3`, `/px4_1/mission_event`, `/secret`)을 발행한 뒤 손으로 쓴 WebSocket 클라이언트(`d6/wsprobe.py`)로 확인. 각 1회.
  - 소켓은 `127.0.0.1:8769`에만 LISTEN(`ss -ltnp`).
  - 서브프로토콜 `foxglove.sdk.v1`은 101, `foxglove.websocket.v1`은 400 Bad Request.
  - serverInfo의 capabilities는 `['connectionGraph']`뿐.
  - advertise된 채널: `/px4_1/fmu/out/vehicle_status_v3`, `/px4_1/mission_event`, `/foxglove_bridge/sysinfo`. `/secret`은 없다. `/foxglove_bridge/sysinfo`는 허용 목록과 무관하게 브리지가 스스로 낸다.
  - 클라이언트 advertise(`/px4_1/evil`) 요청에 status level 2 "Server does not support clientPublish capability". getParameters 요청에 "Server does not support parameters capability".
- 의견. 생성기의 `foxglove` 서비스: ros-ws 이미지, `profiles: [viz]`, host 네트워크, uid:gid, command `ros2 run foxglove_bridge foxglove_bridge --ros-args -p address:=127.0.0.1 -p port:=<8765+k> -p topic_whitelist:=[...] -p capabilities:=[connectionGraph] -p use_sim_time:=true`, `depends_on: bridge`(healthy, viz -> 본 스택 방향이라 허용). healthcheck는 두지 않는다(gz-gui와 같다). `lichtblick` 서비스: `LICHTBLICK_IMAGE`, `profiles: [viz]`, host 네트워크, command `caddy file-server --listen 127.0.0.1:<18080+k>`, depends_on 없음. embedded 변형의 viz는 지금처럼 비운다.
- 의견. 허용 목록 내용은 R14(ros2)가 정한다. 생성기에는 상수 하나로 두고, 기체 수와 무관하게 `px4_[0-9]+`로 쓴다.
- 의견. 생성기 단정과 단위 테스트에 더할 성질: (1) `foxglove`의 address 인자가 정확히 127.0.0.1, port가 `stack.foxglove_port`, `lichtblick` listen이 `127.0.0.1:<stack.lichtblick_port>`, (2) capabilities 목록이 정확히 `[connectionGraph]`(clientPublish, services, parameters, parametersSubscribe, assets가 없다), (3) 허용 목록이 비어 있지 않다(빈 목록은 전체 허용이 되는지 확인 안 함, 빈 목록을 거부한다), (4) lichtblick 이미지 참조가 `@sha256:<64자>`를 포함, (5) 어떤 본 스택 서비스도 두 서비스에 의존하지 않는다(지금 검사의 확장), (6) k 0-9에서 두 포트가 stack.json 값과 같다. golden은 standalone 3개의 `compose.yaml`에 두 서비스, `stack.json`에 `services.foxglove`, `services.lichtblick`, `images.lichtblick`, `services.profiles.viz`가 바뀐다. lint의 `compose config`는 꺼진 프로필 서비스도 해석하므로 새 서비스의 문법도 그대로 검사된다.

## D7. `sitl` job

- [실측] GHCR 패키지는 이미 공개 상태다. 토큰 없이 받은 익명 토큰으로 지금 key의 manifest를 조회해 ros-ws(a0f1847b30f3b76f), px4(81678f535f7e4b05), sim-base(cd6a22462ff15990), xrce-agent(decfdd1ff03d1456) 모두 200. 진행 기록 "다음 작업 1"(사용자의 공개 전환)은 끝난 것으로 보인다. `gh api`의 패키지 visibility 조회는 이 호스트 토큰에 `read:packages`가 없어 403이었다.
- [실측] 저장소는 PUBLIC(`gh repo view`). 표준 runner 사용 시간은 공개 저장소에서 과금되지 않는다([문서](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)). 남는 제약은 동시 실행 job 수와 벽시계 시간이다.
- [실측] runner에서의 이미지 받기. unit job(run 42829237730)의 ros-ws 1.99 GB `docker pull`이 22.7 s. px4, sim-base는 runner에서 받은 기록이 없다. 로컬 레이어 대조로 px4와 ros-ws가 공유하는 레이어는 ros-base 6개뿐이고 px4 + ros-ws + xrce-agent의 고유 레이어는 24개다.
- [추정] 이미지 셋(px4 3.07 GB, ros-ws 1.99 GB, xrce-agent 153 MB. sim-base는 px4와 같은 계열이라 레이어 대부분이 겹친다)을 받는 데 60-90 s.
- [실측] build job 전체(이미지 다섯 개를 키가 없을 때 빌드)는 PR에서 679-1273 s(run 42770470337, 42767888913, 42801954182).
- [실측] `artifacts/runs/`의 스모크 실행 디렉터리는 8.8-15 MB, ULog가 거의 전부(9-15 MB). 오래 둔 S4 실행은 ULog 124 MB(약 7분). ULog는 부팅부터 쌓이므로 스택 가동 시간에 비례한다.
- 의견. 트리거는 `pull_request`와 `push: branches: [main]`, `workflow_dispatch`. 기능 브랜치의 push에서는 돌리지 않는다(lint, unit처럼 push와 PR 둘 다에서 돌면 같은 커밋에 두 번 돈다. D11). concurrency `sitl-${{ github.ref }}`, PR은 cancel-in-progress, main은 취소하지 않는다. 재시도는 수동(re-run).
- 의견. `timeout-minutes: 25`. 목표 15분은 테스트 단계(스택 기동부터 down까지)의 제한으로 두고 그 단계에 `timeout-minutes: 15`를 따로 건다. 이미지 받기와 colcon build는 그 바깥.
- 의견. 이미지 key가 레지스트리에 없으면(이미지를 바꾸는 PR) job 안에서 빌드하지 않고 실패시킨다. 메시지로 "이미지 변경 PR은 이미지 PR을 먼저 main에 넣는다"를 남긴다. px4 빌드까지 하면 20분을 넘기고(위 build 실측), 통과로 보이는 건너뛰기는 두지 않는다는 규칙(lint.yml 주석)과도 맞는다. 이 정책은 D5의 "이미지 변경은 앞쪽 PR"과 짝이다.
- 의견. unit job과 빌드를 나눠 쓰지 않는다. `ros_ws.sh build`가 55 s 정도라 artifacts로 install을 넘기는 이득(업로드, 다운로드, 절대 경로 일치 조건)보다 단순함이 낫다. A15의 ccache는 build 단계가 3분을 넘을 때 다시 본다.
- 의견. 실패 때 올릴 artifact: 실행 디렉터리 통째(`compose.yaml`, `stack.json`, `ros_params/`, `ros_log/`, `px4-N/log/*.ulg`, 판정 JSON, `compose logs` 원문). retention 7일. MCAP은 logging의 L2 결정에 따른다. `compose down`을 먼저 해야 ULog가 닫힌다(L1 확인 대기)는 점 때문에 수집 순서는 logs 저장 -> down -> 업로드.
- 의견. 15분 안에 드는 시나리오 수는 스택을 공유하면 4-6개, 시나리오마다 재기동하면 3-4개 정도로 본다([추정]. 근거: 이 호스트의 기동 40 s 안팎(D8), 운용 노드 단계와 down을 더해 재기동 1회 1.5-2분으로 잡고, 비행 1회는 sim 시간 60-90 s에 RTF 1 가정, 시나리오 사이 착륙과 disarm 확인 포함. runner RTF는 미측정). 확정은 T1, T5의 결론과 첫 실제 실행의 summary 표로 한다.
- 충돌. 시나리오 범위(T5)와 스택 수명(T1)이 이 수를 정한다. runner 시간은 공개 저장소라 비용이 아니라 대기 시간 문제로 보며, PR당 1회 원칙은 지킨다.

## D8. 벽시계 제한

- [실측] 내 스택(k=4)은 올리지 않았다. 측정하는 동안 다른 담당자의 스택이 둘에서 셋(k=1, 5, 3)까지 떠 있어 넷째를 더하지 않았다. 대신 그들이 `tools/stack.sh up`으로 올린 스택의 컨테이너 생성 시각(`docker inspect .Created`, 다음 단계 서비스가 생성되는 시각 = 앞 단계 `up --wait` 통과 시각)으로 단계 시간을 쟀다. 3회.

| 스택 | 함께 떠 있던 것 | 1단계(agent, gazebo, 모델 사전 검사 포함) | 2단계(px4-1) | 3단계(bridge) |
| --- | --- | --- | --- | --- |
| idsim-1 | 없음 | 19.1 s | 6.8 s | 미상 |
| idsim-5 | idsim-1 | 19.7 s | 12.0 s | 미상 |
| idsim-3 | idsim-1, idsim-5 | 19.6 s | 12.0 s | 8.6 s 이하(bridge 생성 -> runner 생성) |

- [실측] 따라서 이 호스트의 standalone 1대 기동은 40 s 안팎이고, 단계별 제한 240 s 대비 단계마다 12배 이상 여유가 있다. px4 단계의 6.8 s와 12.0 s 차이는 healthcheck interval 5 s의 양자화로 본다([추정]). `down` 시간은 재지 못했다.
- [실측] runner에서는 못 했다. 지금 CI에 스택을 올리는 job이 없고, 임시 workflow를 push하는 것은 저장소 변경이라 하지 않았다.
- 의견. `STACK_UP_TIMEOUT` 240 s는 단계별 값이다. 운용 노드 단계(4단계)는 `/clock` 첫 수신과 activate까지라 짧지만, 같은 240 s를 쓴다. 단계마다 다른 값을 두면 설정 이름이 늘고 이득이 작다. 전체 상한은 job의 테스트 단계 `timeout-minutes`가 맡는다.

## D9. bridge 설정 파일

- [소스] 지금 bridge는 인자로 받는다. 생성기 `ros_ws_service("bridge")`의 command가 `ros2 run ros_gz_bridge parameter_bridge /clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock`이고(`tools/gen_compose.py`, golden `tests/fixtures/gen_compose/1대-k0/compose.yaml` 127-128행), 설정 파일은 없다.
- 의견. 6단계에서는 인자로 둔다. 6단계의 토픽은 `/clock` 하나이고 파일로 바꾸면 파일, 단정, golden이 하나씩 늘지만 소비자가 없다. 표적 pose가 더해지는 1b에서 `parameter_bridge`의 `config_file` 파라미터(yaml)로 바꾸고, 그때 금지 토픽 검사(sim S4)가 그 파일을 대상으로 삼는다.
- 충돌. sim(S4)이 6단계 파일화를 원하면 생성기 쪽 비용은 작다(params 파일 생성과 같은 경로). 반대하지 않는다.

## D10. 진입 스크립트의 소유

- [실측] ros-ws 이미지에는 docker CLI도 Python `docker` 모듈도 없다(`command -v docker`, `import docker`).
- 의견. 호스트에서 도는 진입 스크립트(스택 up, `compose run runner`로 pytest, 실패해도 도는 수집과 down)는 `run_smoke.sh` 선례대로 devops가 소유하고, 그 안에서 부르는 pytest 코드, fixture, 판정은 test-engineer가 소유한다. 위치는 `tests/sitl/run_sitl.sh`처럼 `tests/` 아래로 두되 file-ownership 표에 명시한다.
- 의견. `stack.sh`는 up과 down만 재사용한다(단계 순회, 사전 검사, 실패 보고, stdout의 실행 디렉터리 한 줄). 진입 스크립트가 단계 로직을 다시 쓰지 않는다. pytest fixture가 runner 안에서 직접 compose를 올리려면 ros-ws에 docker CLI와 호스트 docker 소켓 마운트가 필요하다. 소켓 마운트는 컨테이너에 호스트 root 권한을 주는 것이라 devops는 반대한다(T1에 대한 근거).

## D11. 열린 항목(lint, unit 이중 실행)

- [실측] 같은 커밋(feat/1a-5-idsim-interfaces)에서 lint는 push와 pull_request로 두 번(각 11 job, job당 3-13 s), unit은 두 번(106 s, 121 s) 돌았다.
- 의견. `sitl` job은 처음부터 `pull_request` + main push로만 만들어 이중 실행이 생기지 않게 한다(D7). lint와 unit의 정리는 지금 비용이 job당 2분 이하라 6단계 범위에 넣지 않고 별도 작은 PR로 한다. 트리거를 바꾸면 PR 없는 브랜치 push에서 CI가 안 도는 동작 변화가 있어 따로 보는 게 맞다.

## 부딪칠 것으로 보이는 지점

- D2의 노드 키 표기(정확한 FQN)와 key 이름: R4. 노드 이름 상수를 생성기도 들게 된다.
- D3의 healthcheck 방식(`ros2 lifecycle get` 1.5 s와 참가자 하나 vs 노드가 쓰는 표시 파일)과 전이를 거는 주체: R3. 식별 불일치를 activate 실패로 하면 `up --wait` 4단계 실패로 보고된다: R5, P12.
- D3의 스모크 범위: 스모크가 `ros_ws/install`을 요구하게 되고, Executor가 goal 없이 `/fmu/in`에 쓰지 않아야 S3와 섞이지 않는다: test, ros2, px4.
- D7의 시나리오 수와 이미지 변경 PR의 sitl 실패 정책: T1, T5, reviewer.
- D10의 runner 안 compose(소켓 마운트) 반대: T1.
- D5의 Lichtblick 버전 표기 정정: architect(architecture.md), sim(S2는 1.30.0으로 확인해야 한다).

## 실험을 못 한 것

- D2의 C++(rclcpp lifecycle) 노드 확인: 저장소 ros_ws를 빌드하지 않는 조건이라 rclpy로만 했다.
- D4의 "스택이 내려가 있을 때" 빌드, D8의 내 스택(k=4) up과 down 직접 측정: 측정 시점에 다른 담당자의 스택이 둘에서 셋 떠 있어 넷째를 올리지 않았다. D8은 다른 스택의 컨테이너 생성 시각으로 대신했다.
- D7, D8의 runner 실측(이미지 셋 받기, 스택 기동): 스택을 올리는 CI job이 없고 임시 workflow push는 저장소 변경이다.
- D5의 새 ros-ws 이미지 key: 저장소 Dockerfile을 바꾸지 않아 계산하지 않았다.
- D6의 capabilities 빈 목록과 허용 목록 빈 목록 동작, Lichtblick layout 주입의 non-root 동작.

## 재질문 답(2026-11-11)

공통 조건. 01:16-01:41(KST) 동안 호스트에는 내 컨테이너만 있었다. 시작 전 `docker ps -a`는 비어 있었고 load average는 0.87(1분)이었다(직전까지 다른 스택이 있어 15분 값은 4.14). 측정 중 1분 load는 0.4-2.6이고 2를 넘은 것은 colcon 빌드 직후뿐이다. 스택은 k=4 standalone 1대. 변형 compose는 scratchpad `q1/`(생성된 `compose.yaml`을 PyYAML로 고친 사본), 원형은 `hc/`, 빌드는 `q3b/`(`git archive HEAD` 사본)에 두었고 저장소 파일은 바꾸지 않았다. Docker 29.1.3, Compose v5.5.1. 끝난 뒤 컨테이너 0개, 새 이미지 없음. `artifacts/runs/`에 실행 디렉터리 4개(비추적)가 남았다.

### 재질문 devops 1. SIGTERM

[실측] 변형별 3회. 단계 순서대로 `up -d --wait` 뒤 `compose stop --timeout 10`(전체, 역순)을 재고 `docker events`의 kill과 die로 컨테이너별 시간을 봤다. 아래 "멈춤"은 신호에서 die까지.

| 변형 | bridge 멈춤, 종료 코드 | xrce-agent 멈춤, 종료 코드 | stop 전체 |
| --- | --- | --- | --- |
| 지금(`stack.sh down`, 3회) | 10.0 s 뒤 SIGKILL, 137 | 10.0 s 뒤 SIGKILL, 137 | down 20.8-21.1 s |
| SIGINT만 | 10.0 s 뒤 SIGKILL, 137 | 10.0 s 뒤 SIGKILL, 137 | 20.6-20.7 s |
| `init: true`만(`ros2 run` 유지) | 0.04-0.09 s, 143 | 0.03-0.05 s, 143 | 0.43-5.6 s(*) |
| 직접 실행만 | 0.04-0.05 s, 0 | 10.0 s 뒤 SIGKILL, 137 | 10.5 s |
| 직접 실행 + SIGINT | 0.04-0.06 s, 0 | 10.0 s 뒤 SIGKILL, 137 | 10.4-10.5 s |
| 직접 실행 + `init: true` | 0.05 s, 0 | 0.04-0.06 s, 143 | 0.46-0.48 s |
| 셋 다 | 0.04-0.05 s, 0 | 0.05-0.08 s, 130 | 0.47-0.50 s |

(*) 한 번은 gazebo가 SIGTERM 뒤 5.2 s 걸렸다(나머지 20회는 0.2 s, 늘 143). init 변형의 둘째 실행 1회는 px4-1이 기동 중 139(SIGSEGV)로 죽어 up이 실패했다. 변형과 무관한 서비스이고 같은 실행 디렉터리를 18회 다시 쓴 조건이라 재현 여부는 모른다(px4에 알릴 것).

- 직접 실행은 `/opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge <인자>`를 command로 두고 이미지 entrypoint(`ros-ws-entrypoint.sh`, 환경을 읽고 `exec "$@"`)를 그대로 썼다. bridge가 PID 1(`init` 없음) 또는 PID 2(`init` 있음)가 된다.
- 원인 둘. (1) bridge: PID 1이 `ros2 run`(Python)이면 SIGTERM과 SIGINT 둘 다 자식에게 가지 않는다. rclcpp 실행 파일을 직접 두면 rclcpp 처리기가 SIGTERM을 받아 0으로 끝난다. (2) xrce-agent: 이미 `MicroXRCEAgent`가 PID 1인데 SIGTERM과 SIGINT 둘 다 처리기가 없어 커널이 PID 1에 대한 기본 동작을 막는다. `init: true`(docker-init)가 PID 1이 되면 신호의 기본 동작으로 끝난다(143 또는 130). 정상 종료 경로는 없지만 Agent는 지울 상태가 없다.
- `init: true`만으로 bridge를 끝내는 것은 해법이 아니다. tini가 `ros2 run`(Python)에 신호를 주면 Python이 143으로 죽고 `parameter_bridge`는 신호 없이 컨테이너와 함께 정리된다.
- [실측] 직접 실행 + `init: true` 변형으로 정지 상태가 아니라 떠 있는 상태에서 `docker compose -p idsim-4 down --timeout 10`(= `stack.sh down`) 3회: 0.78, 0.82, 0.85 s(지금 20.8-21.1 s).

의견
- 6단계 앞쪽 PR에 넣을 것은 둘이다. bridge command를 실행 파일 직접 경로로(entrypoint의 exec를 거친다), xrce-agent에 `init: true`. `stop_signal: SIGINT`는 넣지 않는다. 두 서비스 모두 시간 이득이 없고 Agent는 종료 코드만 130으로 바뀐다. 경로의 `jazzy`는 생성기가 `versions.env`의 `ROS_DISTRO`로 만든다(버전 문자열을 생성기에 쓰지 않는다).
- 생성기 단정: ros-ws 이미지를 쓰는 본 스택 서비스의 command 첫 요소는 `/`로 시작하는 실행 파일이고 `ros2`가 아니다(healthcheck는 대상 아님). xrce-agent는 `init: true`. golden diff는 compose 4개의 bridge command와 agent 한 줄.
- `mission-N`: command는 `<install>/idsim_mission/lib/idsim_mission/<실행 파일> --ros-args -r __ns:=... -r __node:=... --params-file ...`의 직접 실행이고 `init`은 두지 않는다(bridge와 같이 rclcpp가 PID 1에서 SIGTERM을 받는다. ros2의 pre-shutdown callback이 이 신호로 불린다). `stop_grace_period`는 기본 10 s 유지. 종료 코드 0이 아니거나 10 s를 쓰면 `stack.sh down`의 로그로 보이게 하는 것은 run_sitl.sh에서 컨테이너 종료 코드를 남기는 것으로 한다(8번 결정의 "px4 컨테이너 종료 코드"에 bridge, agent, mission-N을 더한다).
- gazebo의 143은 sim 소유(`gz_server.sh`)라 알리기만 한다.

### 재질문 devops 2. 이미지 key가 없을 때의 `sitl`

[원문]
- PR의 build job은 이미지를 올리지 않는다(`build.yml`: PR은 `push: false`, 권한 `packages: read`). `--load`도 하지 않아 결과는 그 runner의 builder cache에만 남는다(`build-images.yml` 주석). 그래서 `needs: build`를 걸어도 sitl job이 받을 이미지가 없다.
- fork PR에는 쓰기 토큰이 없다(`build.yml` 주석, GitHub 기본 동작).
- unit job은 key가 없으면 runner에서 `build_images.py --mode load ros-ws`로 ros-base부터 빌드한다. [실측] run 42801954495(PR)에서 그 단계가 544 s, `ros_ws.sh ci`가 67 s. load 모드는 레지스트리 cache를 쓰지 않는다(로그 `load 모드는 레지스트리를 보지 않음`).
- [실측] main에 branch protection과 ruleset이 없다(required check 없음). 지금은 실패한 check가 있어도 머지가 막히지 않는다.

의견: "key가 없으면 실패"를 이미지별로 나눈다.
1. ros-ws와 xrce-agent의 key가 없으면 sitl job 안에서 unit과 같이 `--mode load`로 빌드하고 진행한다. 6단계에서 바뀌는 이미지는 ros-ws(foxglove_bridge)뿐이라 이 PR 자신의 sitl이 실제 이미지로 판정된다. 둘 다 PR 권한(read)만 쓰므로 fork PR에서도 같다.
2. px4, sim-base(또는 그 베이스가 바뀌어 key가 바뀐 경우)의 key가 없으면 빌드하지 않고 실패로 둔다. 건너뛰기(skipped, 통과처럼 보임)로 두지 않는다. 메시지: "px4/sim-base 이미지가 레지스트리에 없다. 이 PR의 sitl은 로컬 `run_sitl.sh` 결과를 PR 본문에 붙이고, main 머지 뒤 main의 sitl이 판정한다". px4 빌드만 15-20분이라(build-images.yml 추정) 시간 한도 안에 들지 않는다.
3. job `timeout-minutes`는 35로 둔다(빌드 분기 9분 + 이미지 받기 + 테스트 단계 15분). 테스트 단계의 15분 제한은 그대로다. 정상 경로(이미지를 받기만 함)는 영향이 없다.
4. main push에서의 경합: build(publish)와 sitl이 같은 push에서 동시에 돌면 sitl이 새 key를 못 받는다. main의 sitl은 `workflow_run`(build 완료, 성공)으로 띄운다. PR은 `pull_request`로 띄운다. 이렇게 하면 px4를 바꾼 PR의 판정이 main 머지 직후 한 번 생긴다.
5. 받지 않는 안. PR에서 별도 이름공간에 push: fork PR에서 안 되고, PR이 바꾼 workflow로 만든 이미지가 같은 key를 쓰게 되는 오염 경로가 생긴다. `docker save`를 artifact로 넘기기: px4 3.07 GB라 저장과 업로드 시간이 크고(미측정) 이득은 px4 PR 한 종류뿐이다.
- 사용자에게 갈 것: sitl을 required check로 둘지(지금은 required check가 하나도 없다). 위 2번은 required로 두면 px4 PR의 머지가 막히므로 그때는 "이미지 PR은 관리자가 우회한다" 같은 규칙이 필요하다.

### 재질문 devops 3. 경합 없는 재측정

[실측] `tools/stack.sh up --stack 4`와 `down` 3회(저장소 그대로).

| 회 | up | down | 단계 사이(컨테이너 Up 시각 차) |
| --- | --- | --- | --- |
| 1 | 35.3 s | 20.9 s | agent -> gazebo 5-6 s, gazebo -> px4 14-15 s, px4 -> bridge 7-8 s |
| 2 | 35.9 s | 20.8 s | 같은 꼴 |
| 3 | 35.8 s | 21.1 s | 같은 꼴 |

- up 35 s에는 생성기 컨테이너와 모델 사전 검사(sim-base 1회성 컨테이너 셋)가 들어 있다. 같은 compose로 단계 `up --wait`만 하면 28.6-28.7 s(1번의 직접 실행 + init 변형 3회). 경합 아래의 40 s 안팎(D8)보다 5 s 정도 짧다.
- down 20.8-21.1 s는 bridge 10 s + agent 10 s의 SIGKILL 대기가 전부이고 나머지 둘은 0.1-0.2 s다. 1번 변경 뒤 0.8 s.
- [실측] 콜드 빌드: 스택이 없을 때 사본의 `tools/ros_ws.sh build`(build, install, log 없음) 1회 42.0 s(colcon Summary 40.5 s, idsim_interfaces 32.7 s, idsim_common 40.4 s). 경합 아래 94 s(D4)의 절반이다. 컨테이너 cgroup `memory.peak` 1851 MiB(페이지 cache 포함. D4의 871 MiB는 `docker stats` 값이라 cache가 빠져 있어 직접 비교하지 않는다), 호스트 available 최소 4459 MB(시작 6129 MB, 1 s 표본).
- [실측] 표식 healthcheck 실행 시간(docker 헬스 로그 Start-End, 각 5회): `test -f` 36-98 ms, stat 나이 판정 33-45 ms, find 판정 32-45 ms. 대부분 docker exec 비용이다. 명령만 컨테이너 안에서 100회: `test -f` 2-3 ms, find 133-138 ms, stat과 date 204-221 ms(1회 약 2 ms, 프로세스 셋).

### ros2 몫의 확인: tmpfs 아래 표식과 mtime 판정

[실측] scratchpad `hc/`의 원형 compose(ros-ws 이미지, `user: 1000:1000`, `init: true`, `network_mode: none`, 1 s마다 `touch`하는 셸 loop).
- 같은 경로를 본다: compose `tmpfs: [/run/idsim]`의 마운트를 healthcheck 명령(docker exec)이 그대로 보고, 첫 기동에서 healthy까지 1.9 s(`start_interval` 1 s).
- 쓰기 권한에 함정이 있다. 옵션 없는 tmpfs는 첫 기동에서 `drwxrwxrwt root`(1777)라 uid 1000이 쓴다. 그런데 같은 컨테이너를 `docker restart`나 `docker kill` 뒤 `docker start`로 다시 띄우면 `mode=755 root`로 다시 마운트되어 `touch: Permission denied`이고 healthcheck가 영원히 starting이다(2/2 재현). `/run/idsim:mode=1777` 또는 `/run/idsim:uid=1000,gid=1000,mode=0700`을 주면 재기동 뒤에도 그대로였다(각 1회, compose 짧은 문법으로도 1회).
- 재기동 시 비워진다: 표식 외 파일(`stale`)을 만든 뒤 `compose restart`와 `kill` 뒤 `up`에서 둘 다 사라졌다. 남은 표식 문제(SIGKILL 뒤 재시작)는 tmpfs만으로 막힌다.
- 판정 형태. 아래 둘 다 동작한다. 갱신 loop를 SIGSTOP으로 멈추면 둘 다 10.0 s 뒤 unhealthy(interval 2 s, retries 3), SIGCONT 뒤 2.0 s 안에 healthy.
  - stat: `t=$$(stat -c %Y <표식>) && [ $$(( $$(date +%s) - t )) -le 5 ]`(compose 안에서는 `$$`). 파일이 없으면 stat이 실패해 1. 초 단위 절삭이라 실제 허용 나이는 5-6 s.
  - find: `test -n "$$(find <표식> -newermt -5seconds 2>/dev/null)"`. 한 프로세스이고 더 빠르다.
  - `find -mmin`은 분 단위라 쓰지 않는다. 이미지의 coreutils는 `stat -c %.3Y`(소수 초)도 된다.

의견
- 생성기: `mission-N`에 `tmpfs: ["/run/idsim:uid=<uid>,gid=<gid>,mode=0700"]`, 노드 파라미터 `health_marker: /run/idsim/active`. uid와 gid는 지금 `user`에 쓰는 값과 같은 원천이다. 단정: `health_marker`가 tmpfs 대상 아래에 있다.
- healthcheck는 find 형태로 한다(외부 명령 하나, 경로 하나). `interval 30s, timeout 5s, retries 3, start_period 60s, start_interval 2s`. 기동 단계의 판정은 `start_interval`로 2 s 간격이라 `up --wait`의 지연이 작다.
- 이 판정은 compose 기본에서 재시작을 일으키지 않는다(`restart: 'no'`). 실행 중 unhealthy는 run_sitl.sh가 실패 artifact를 모을 때 `docker inspect`의 Health 로그를 함께 남기는 것으로 쓴다.
