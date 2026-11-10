# idsim 진행 상황

이 폴더는 에이전트와 작업자가 세션을 시작할 때 현재 상태를 파악하기 위한 기록이다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`에 두고, 여기에는 무엇이 끝났고 무엇이 진행 중이며 다음에 무엇을 할지만 적는다. 날짜는 항상 절대 날짜(YYYY-MM-DD)로 쓴다.

## 현재 상태 (2026-11-10)

- 저장소: 원격 github.com/danielhongwoo/idsim. main에 PR #1 CI 골격, #2 큰 그림 다이어그램, #3 시각 도구 로드맵, #4 인계용 진행 기록이 합쳐져 있다. 2b단계(PR #5)와 루트 README, `check_host.sh`(PR #6)도 합쳐졌다.
- 첫 개발 호스트(2026-11-06까지): VMware VM, x86_64 Ubuntu 24.04, 16 vCPU, 31GB, NVIDIA 없음, GNOME Wayland. 이 호스트에는 다른 compose 프로젝트(`docker`: open_manipulator, zenoh_daemon, cyclo_manager 등)가 host 네트워크로 떠 있었다. 아래 실측값(빌드 시간, 이미지 크기, Gazebo GUI fps)은 이 호스트 기준이다.
- Phase 1a 1단계 환경 스모크 테스트 S0부터 S5까지 로컬에서 모두 통과(스택 번호 0, 도메인 20). 설계는 `docs/smoke-test.md`(2026-11-10에 `smoke-test-phase1a.md`에서 이름 변경).
- 이미지 5종 빌드 완료: ros-base 838MB, sim-base 2.97GB, px4 3.06GB(builder 단계 7.7GB), ros-ws 1.57GB, xrce-agent 153MB. 전체 재빌드는 부분 캐시로 약 2분 30초, PX4 첫 빌드는 이 호스트(16 vCPU)에서 163초.
- 골든 첫 생성: `tests/fixtures/px4/v1.17.0/`(토픽 65, qos 27, env 4키). 재실행 `--check` 일치.
- 산출물: 스모크 실행 기록 `artifacts/smoke/`는 git에 추적되지 않으므로 다른 PC로 옮겨지지 않는다. 판정에 필요한 골든은 `tests/fixtures/`에 추적된다.
- 2026-11-06: Phase 1a 2단계 CI 골격 완료. PR #1로 main에 합침(ddbe835). lint(11종, 대상 없는 4종은 PASS-NO-TARGETS)와 build(이미지별 키, 레지스트리에 키가 있으면 건너뜀, PR은 빌드만, main만 GHCR 푸시) 워크플로.
- 2026-11-06: 아키텍처 문서에 큰 그림 다이어그램 추가(PR #2).
- 2026-11-06: 시각 도구 실측(sim-engineer)에 따라 `docs/roadmap.md`와 `docs/architecture.md`에 시각 도구 구성을 반영(1a 2b단계 신설, 3단계 `viz` 프로필, 6단계 foxglove_bridge, Foxglove 표기를 Lichtblick으로).
- CI 첫 실행 결과(PR #1, 2026-11-06): lint 11종 통과, 이미지 5종 콜드 빌드 성공(약 22분: ros-base 44초, xrce-agent 334초, ros-ws 444초, sim-base 51초, px4 255초). 러너 디스크는 정리 전 여유 86GB, 정리 후 114GB, 빌드 뒤 106GB로 문제 없음. 없는 buildcache를 cache-from으로 주면 ERROR 줄이 찍히지만 빌드는 계속된다. 같은 저장소 PR 브랜치에서는 push와 pull_request 트리거로 lint가 두 번 돈다.
- GHCR 조회(2026-11-06): 로그인한 토큰으로 없는 패키지를 조회하면 GHCR는 403이 아니라 not found를 준다(PR #1 실측). 그래서 push 모드는 not found만 "키 없음"으로 보고 권한 거부(denied, 403)는 중단한다. PR 모드와 로컬은 권한 거부도 "키 없음"으로 보고 빌드만 한다.
- 2026-11-09: Phase 1a 2b단계 시각 도구 준비 구현(브랜치 `feat/phase1a-viz-tools`). `tools/qgc.sh`(QGC v5.1.5 AppImage, `versions.env`의 `QGC_VERSION`과 `QGC_APPIMAGE_SHA256`으로 내려받아 `${XDG_CACHE_HOME:-$HOME/.cache}/idsim/qgc/<버전>/`에 캐시, INT/TERM에 TERM 후 5초 유예, 그다음 SIGKILL), sim-base에 `libqt5svg5`, `ros_ws/src/idsim_sim/config/gui.config`(gz-sim8 기본에서 WorldControl만 제외, 플러그인 17개), `docker/README.md` 시각 도구 절. 로컬 검증: QGC 다운로드, 캐시 재사용, 손상 재다운로드, INT와 TERM 종료 통과. Gazebo GUI는 standalone 스택 위에서 50초 생존, SVG 경고 29건에서 0건, 창 `Gazebo Sim` 존재, `Loaded plugin` 17개에 WorldControl 없음, GUI를 붙여도 서버 RTF 1.0. lint 11종 통과.
- 2026-11-09: 이 호스트에서 archive.ubuntu.com이 IPv4, IPv6 모두 타임아웃(security.ubuntu.com, kr.archive.ubuntu.com, mirror.kakao.com은 정상). 로컬 sim-base와 px4 이미지는 저장소 Dockerfile을 바꾸지 않고 scratch 복사본에 kr 미러 sed 한 줄을 넣어 빌드했다. 따라서 이 호스트의 `idsim/sim-base:local`, `idsim/px4:local`의 apt sources는 kr 미러다. 정식 이미지는 CI가 원본 Dockerfile로 빌드한다.
- 2026-11-09: 1a 3단계 설계 토론 완료. architect 주재, devops/px4/ros2/sim 의견, reviewer가 가정 10건을 실측 검증, 사용자 결정 4건. 결정은 아래 결정 기록, 설계 문서 반영은 브랜치 `docs/phase1a-step3-design`. 구현(A, B, C)은 시작 전.
- 2026-11-10: Phase 1a 3단계 C 완료(`feat/step3-compose` 브랜치. devops-engineer 구현, test-engineer와 px4-engineer 참여). PR 생성 전.
  - 산출물 구조: `artifacts/runs/<run_id>/{compose.yaml, stack.json, px4-N/, ros_log/, smoke/}`. 기본 run_id는 `<UTC>-k<k>`, 스모크는 `<UTC>-k<k>-<단계>`.
  - 진입점: `tools/stack.sh`(`up`, `down`, `ps`, 옵션 `--stack`, `--fleet`, `--variant`, `--viz`)와 `tools/gen_compose.sh`(ros-ws 컨테이너에서 생성기 실행). `runner` 서비스(프로필 `tools`)가 판정 명령을 돌린다. `config/fleet.yaml`(1대, 서울시청 원점), `tools/gen_compose.py`, `tests/tools/test_gen_compose.py`와 골든 4종(`tests/fixtures/gen_compose/{1대-k0, 1대-k3, 3대-k0, embedded}`), lint 잡의 pytest와 `compose config -q`, `LINT_PYYAML_VERSION=6.0.1`.
  - `tools/qgc.sh --stack k`: QGC 설정 `~/.config/QGroundControl/QGroundControl.ini`의 `[AutoConnect] udpListenPort`를 14550 + 1000k로 바꾼다. 실행이 끝나도 되돌리지 않는다(되돌림 옵션은 미해결 사항).
  - `docker/compose.smoke.yaml` 삭제. `run_smoke.sh`는 생성기를 호출해 stack.json을 소비하고, S2-S5는 운영 스택과 같은 구성으로 `bridge`까지 올린다(결정 기록 (k)).
  - 검증 결과: k=0에서 S0, S1b, S2, S3, S4(`--check` 일치), S5 통과. k=0과 k=1 동시 S2 통과, 두 스택 px4 로그 모두 `bind failed` 0건. `artifacts/runs/`에 root 소유 파일 0건. 단위 테스트 141 passed. `tools/ci/lint.sh all` 전부 PASS. `stack.sh up --viz`에서 gz-gui 창 확인(플러그인 18개). `qgc.sh --stack 1`에서 QGC가 15550을 수신하고 연결 확인(ParamCache 갱신). 8889를 점유한 상태에서 에이전트 `bind error` 보고 확인.
  - 접점 승인: test-engineer 조건부 승인 -> 조건 반영, ros2-engineer 승인, sim-engineer 조건부 승인(C1) -> 반영, px4-engineer 접점 문제 없음, reviewer 조건부 -> 반영.
  - 사용자 육안 확인 2건은 아직 안 됨: `stack.sh up --viz`의 Gazebo GUI에서 x500_1 확인, `qgc.sh --stack`으로 QGC 기체 연결 확인.
- 2026-11-10: 3단계는 PR #10으로 main에 합쳐졌다(5fd11a6).
- 2026-11-10: 1a 4번 작업 `idsim_common` 설계 확정(ros2, px4, devops 의견, architect 결정, reviewer 검증 조건부 -> 반영). 구현은 시작 전이며 다른 작업 환경에서 이어갈 수 있도록 계획과 근거 전체를 `docs-for-agent/plan-1a-4-idsim-common/`에 두었다.
- 2026-11-10: 개발 호스트가 바뀌었다. 새 개발 PC는 x86_64 Ubuntu 24.04, 4 vCPU, 7GB RAM이다. 이미지 5종을 이 호스트에서 로컬 빌드했다(px4 3.07GB, sim-base 2.98GB, ros-ws 1.99GB, ros-base 838MB, xrce-agent 153MB). 이 항목 아래의 실측값은 이 호스트 기준이다.
- 2026-11-10: 1a 4번 작업 `idsim_common` 구현 완료(브랜치 `feat/1a-4-idsim-common`). 작업 단위 A-E, PX4 인터페이스 검토, reviewer 검토, Apache-2.0 라이선스 적용이 끝났고 PR과 CI unit job 첫 통과가 남았다. 아직 끝나지 않은 것은 미해결 사항의 "1a 4번 작업에서 올라온 항목" 참조.
  - 산출물: `ros_ws/src/idsim_common/`(좌표 변환, 토픽 기술자 65개와 io 템플릿, QoS, `Px4Timestamp`, 기체 식별, `VehicleCommand` 빌더, GoogleTest와 음성 컴파일 테스트 4건), 루트 `.clang-format`과 `.clang-tidy`, `tools/ros_ws.sh`(build, test, tidy, ci, clean, shell), `.github/workflows/unit.yml`, `tools/ci/lint.sh`의 clang-format 연결과 새 검사 `px4-api`(clang-tidy와 ament-lint 항목은 삭제), `config/px4/sitl_params.env`의 `UXRCE_DDS_SYNCT=0`과 `check_px4_pxh.py` 기대값, `capture.sh`의 hz 목록에서 `timesync_status` 제외.
  - ros-ws 이미지: clang-tidy-18과 clang-format-18 추가로 key가 3774f33946b0b4d7에서 a0f1847b30f3b76f로 바뀌었다(reviewer 지적으로 `Dockerfile.ros-ws` 주석의 음차를 고쳐 1d6b08eb3f6efc06에서 다시 바뀜. 크기는 같다). 크기는 1.58GB에서 1.99GB로 약 410MB 늘었다(계획 때 예상은 297MB). 새 ros-ws 빌드에 400초가 걸렸다.
  - `tools/ros_ws.sh ci` 실측: build 33초(콜드), test 12초(84 tests, 0 failures), clang-tidy PASS(5 files, 14초).
  - test-engineer 검증: 테스트 실패를 주입하면 종료 코드 1, 테스트가 0건이면 종료 코드 1(`colcon test-result` 자체는 0을 반환), tidy 위반이면 종료 코드 1. 종료 코드 규칙과 아티팩트 범위 승인.
  - 설계 문서 반영(E): `docs/roadmap.md`, `docs/architecture.md`, `docs/smoke-test.md`. `docs/interface.md`는 7단계 몫이라 만들지 않았다.
- 2026-11-10: 사용자 결정으로 `docs/smoke-test-phase1a.md`를 `docs/smoke-test.md`로 이름을 바꿨다(결정 기록 참조).
- 2026-11-10: 1a 5번 작업 `idsim_interfaces` 구현 완료(브랜치 `feat/1a-5-idsim-interfaces`). 계획과 계약은 `docs-for-agent/plan-1a-5-idsim-interfaces/`(README.md, decisions.md).
  - 산출물: `ros_ws/src/idsim_interfaces/`(msg 10개: VehicleState, TargetState, Mission, MissionItem, YawSetpoint, TakeoffItem, LoiterItem, GoToItem, TrackEntityItem, MissionEvent. action 1개: ExecuteMission), 계약 테스트(type hash, 펼친 정의, 직접 정의 golden과 상수 검사, `ros2 interface show` 잘림 가드), `tools/ros_ws.sh test`의 ament 패키지별 테스트 1건 이상 단정(`no_test_packages` 예외 배열, 지금은 비어 있음), `docs/architecture.md`와 `docs/roadmap.md`의 고정 시점 분리 반영.
  - `tools/ros_ws.sh ci`: 148 tests(idsim_common 109, idsim_interfaces 39), clang-tidy PASS. 결함 주입 4가지(필드 타입, 상수 값, `TYPE_*` 추가, 중첩 타입 변경의 전파와 직접 변경 구분) 확인.
  - 관련 owner 검토: ros2, test, sim 승인. ops, logging 조건부 -> 반영. reviewer 최종 검토 PR 가능(PX4 읽기 검토 포함: Hold의 위치 요구, NAV_LAND force, 지상 아닌 disarm 거부, 자동 disarm 조건이 v1.17.0 원문과 모순 없음). 비차단 지적은 반영.
  - `MissionEvent` 고정 시점은 사용자 결정 1의 기준(첫 소비자가 생기는 Phase 완료)의 예외로 Phase 2 완료다(architect 결정, logging-engineer 동의). 이유는 decisions.md. 1a 완료로 당길 수 있다.
- 다음 작업:
  1. 첫 main 빌드가 GHCR에 이미지를 올리면 사용자가 패키지 5개와 buildcache를 Public으로 바꾼다. 비공개면 포크 PR과 익명 조회가 403을 받아 매번 전체를 다시 빌드한다. 두 번째 main 실행에서 다섯 이미지 모두 SKIP인지 확인.
  2. (완료 2026-11-09) 2b PR #5. 사용자가 QGC로 서울 상공 비행과 Gazebo GUI의 x500을 확인했다.
  2b. (완료 2026-11-09, 브랜치 docs/readme-check-host) 새 PC 재구성 지원: 저장소 루트 `README.md`와 `tools/check_host.sh`. 남은 것: apt 미러를 빌드 인자로 바꿀 수 있게 할지와 GHCR 이미지를 받아 쓰는 `--mode pull`(devops-engineer 판단, 아래 미해결 항목). README의 "알려진 제약" 절은 미러 문제가 풀리거나 GHCR가 공개되면 함께 고친다.
  3. CI 후속 PR: Dockerfile.px4의 pip 고정과 PX4_OPTICAL_FLOW_REF 반영, `ls | grep` 정리(px4-engineer). Dockerfile.sim-base의 GZ_APT_KEY_FPR 검증(sim-engineer). ruff 임시 예외 정리(test-engineer). 설계 문서의 키 재료와 KEY_<이미지> 설명 갱신(architect. `UBUNTU_APT_MIRROR`를 키에서 제외한 것이 "같은 키는 같은 바이트" 의미의 예외라는 점도 확인). image_keys.py가 bake 블록의 tags와 공백까지 해시하는 것 정리, lint가 같은 저장소 PR에서 두 번 도는 것(devops-engineer).
  4. roadmap 1a 3단계 구현(E, A, B, C 완료, 아래는 계획 당시 기록). 설계 결정은 결정 기록 2026-11-09 참조. 순서 E -> A, B 병렬 -> C -> 검증.
     - E (architect, 완료 2026-11-09, 브랜치 `docs/phase1a-step3-design`): architecture.md, roadmap.md, smoke-test-phase1a.md, progress.md, file-ownership.md 반영. 검토 reviewer.
     - 첫 작업(ros2-engineer, A와 B와 같은 시점): `stack.json` 스키마 초안 확정(k, domain, gz_partition, agent_port, world, foxglove_port, lichtblick_port, mavlink_offset, vehicles[{id, ns, px4_ns, sysid, key, instance, model, pose, mavlink_ports}]). A, B, C가 이 스키마를 기준으로 한다. 검토 devops, test-engineer.
     - A (px4-engineer): `docker/px4/px4-rc.mavlink`(idsim용, GCS와 API만, `IDSIM_MAVLINK_OFFSET` 읽음)와 `docker/Dockerfile.px4`의 COPY, PATH 앞 배치, 상류 sha256 기록과 빌드 시 대조, `airframes/*_gz_*` 전부의 `.post` 훅. `check_px4_pxh.py`에 PX4 로그의 `WARN  [mavlink] bind failed` 부재 판정 추가. check 스크립트의 stack.json 소비와 서비스 이름 `px4-1` 전환, S2의 `sensor_gps` 원점 판정과 모델 유일성 판정은 C로 미룬다(px4-engineer가 C에서 맡는다). 접점 검토 devops(Dockerfile, 이미지 키), reviewer. 완료: `IDSIM_MAVLINK_OFFSET=1000`에서 15550과 15541에 패킷, 14550에 0개, 이미지 빌드 통과.
     - B (sim-engineer): `ros_ws/src/idsim_sim/scripts/gz_server.sh`(서버 기동, 월드 이름 검사, 원점 설정과 응답 확인, 표시 파일), `gz_gui.sh`(DISPLAY와 Xauthority 점검, `gz sim -g` exec), `docker/README.md` 시각 도구 절 문안을 devops에 전달. 접점 검토 px4(원점이 `sensor_gps`에 반영), devops(compose 명령과 마운트 경로), reviewer. 완료: sim-base 단독으로 wrapper 실행 뒤 px4 `sensor_gps`가 원점 좌표, 잘못된 월드 이름에서 종료 코드 1.
     - C (완료 2026-11-10, 위 진행 상황 참조. 계획 당시 범위) (devops-engineer, test-engineer 참여): `config/fleet.yaml`(1대, 서울시청 원점), `tools/gen_compose.py`, `tools/gen_compose.sh`, `tools/stack.sh`, `tools/qgc.sh --stack`, `tests/tools/test_gen_compose.py`(성질: viz 비의존, host 네트워크, restart no, `${:?}` 없음, 16진수 포트, 도메인 일치, 에이전트에 도메인 없음, px4-1..N 개수, 중첩 마운트 없음, k 0-9와 N 1-9 포트 비충돌. 거부: id 0과 중복과 10 이상, pose 2 m 미만, origin 일부, targets 비어 있지 않음, speed_factor 비null, 모르는 키, 금지 파라미터, k 범위 밖, embedded 2대 이상), 골든 `tests/fixtures/gen_compose/{1대 k0, 1대 k3, 3대 k0, embedded}`, lint 잡에 pytest 범위와 `LINT_PYYAML_VERSION`과 `compose config -q`(viz 포함, DISPLAY 미설정), `run_smoke.sh` 재작성(오프셋 계산과 IDSIM_* 제거, 생성기 호출, stack.json 소비, down 뒤 up, 모델 잔존 사전 검사, 에이전트 bind 오류 보고), `docker/compose.smoke.yaml` 삭제, `README.md`와 `docker/README.md`, `check_host.sh`에 Docker 하한과 XAUTHORITY 점검. 3단계 뒤 틀리게 되는 문장 갱신: `README.md` 40, 51행과 `docker/README.md` 19, 47, 63-69, 81, 83, 113, 130, 136, 138-147, 159, 162-166, 175행(reviewer가 뽑은 목록). px4-engineer가 같은 PR에서 `check_px4.py`, `check_px4_pxh.py`를 stack.json과 `px4-1`에 맞추고 S2에 `sensor_gps` 원점 판정과 모델 유일성 판정을 넣는다. test-engineer는 `tests/support/stack.py`(stack.json 읽기)와 `tests/tools/` 구조 승인. 접점 검토 ros2(stack.json 스키마, ROS 환경변수), px4(px4-N 환경과 파라미터 검증, healthcheck), sim(gazebo와 gz-gui 서비스), reviewer.
     - 검증(C 머지 전): roadmap 3단계 완료 기준 그대로. k=0 S0-S5 재통과(S4 `--check` 일치), k=1 동시 S2 통과(두 스택 모두 bind failed 없음), lint 잡 통과, `artifacts/runs/`에 호스트 사용자 소유가 아닌 파일 없음, 생성된 스택 위 `--profile viz`의 Gazebo GUI에 x500_1(사용자 화면 확인).
     - interface.md 초안(ros2-engineer): 포트와 식별자 표(k 0-9, N 1-9, DDS 포트 범위 근거, MAVLink 1000k), QGC 한 스택 제약, SIH 변형의 `PX4_HOME_*` 주의.
  4b. 3단계 C 후속(2026-11-10):
     - PR 생성과 CI 통과 확인(devops-engineer). 사용자 머지.
     - 사용자 육안 확인 2건: `tools/stack.sh up --viz`의 Gazebo GUI에서 x500_1, `tools/qgc.sh --stack` 뒤 QGC 기체 연결.
     - 로드맵 다음 단계: 1a 4단계 `idsim_common`(C++, QoS 프로필, 토픽 이름 매핑, 좌표 변환, 네임스페이스 해석, `VehicleCommand` 빌더, GoogleTest). 이어서 5단계 `idsim_interfaces`, 6단계 이륙-호버-착륙 노드와 통합 테스트, 7단계 `docs/interface.md`. 4단계 착수 때 `frame_transforms`와 px4_msgs v1.17.0 호환을 확인한다(2026-11-10 확인 끝, 결정 기록 (q)).
     - 3단계 C 미해결 항목 처리는 미해결 사항 절 참조(`--run-id` 제거 PR, gz_server.sh 주석 정정 등).
  4c. 1a 4번 작업 `idsim_common`(구현 완료 2026-11-10, 브랜치 `feat/1a-4-idsim-common`). 계획은 `docs-for-agent/plan-1a-4-idsim-common/README.md`, 계약은 같은 디렉터리 `decisions.md`. S2-S5 회귀와 생성기 골든 갱신, reviewer 검토는 끝났다. 남은 순서: PR과 CI의 unit job 통과 -> 사용자 머지. 머지 뒤 unit job의 단계별 시간을 3회 기록한다(devops-engineer).
  5. 6단계에서 ros-ws에 foxglove_bridge 추가와 Lichtblick 브라우저 실접속 확인. 생성기에 ROS params 파일과 bridge 설정 파일 생성 추가.

## 새 개발 PC에서 시작할 때

1. 호스트 조건: x86_64 Linux, Docker와 compose v2, docker buildx, git, python3, curl, sha256sum, gh(GitHub CLI, `gh auth login`). 화면 확인을 하려면 X11 또는 XWayland 데스크톱. `tools/check_host.sh`가 이 조건과 포트 충돌, apt 미러 접근을 점검한다. 사람용 시작 안내는 저장소 루트 `README.md`.
2. 같은 호스트에 다른 ROS 2 스택, Gazebo, compose 프로젝트가 있는지 먼저 본다(`docker ps`, `docker compose ls`). idsim은 ROS 도메인 20 + k, 에이전트 포트 8888 + k, `GZ_PARTITION=idsim-<k>`, compose 프로젝트 `idsim-<k>`를 쓴다. 겹치면 스택 번호 k(`IDSIM_STACK_INDEX`)를 바꾼다. 3단계 이전에 만든 `idsim-smoke` 프로젝트가 남아 있으면 먼저 내려라(`docker compose -p idsim-smoke down`).
3. 이미지: `python3 tools/ci/build_images.py --mode load`로 로컬 빌드한다. GHCR 패키지가 Public이면 `ghcr.io/danielhongwoo/idsim/<이미지>:<키>`를 받아 쓸 수도 있다(키는 `python3 tools/ci/image_keys.py`).
4. 확인: `tests/smoke/run_smoke.sh S0`로 이미지 버전과 `docker/versions.env` 일치를 보고, `S2`로 PX4와 Gazebo 연동, 파라미터 저장값을 본다. `tools/ci/lint.sh all`이 통과해야 한다.
5. 사용자 전역 규칙은 저장소 밖에 있다: `~/.claude/CLAUDE.md`(커밋과 PR에 공동 저자 줄을 넣지 않는다). 새 PC에도 같은 파일을 두어야 한다.

## Phase별 진행

| Phase | 상태 | 마지막 갱신 | 비고 |
| --- | --- | --- | --- |
| 1a | 1, 2, 2b단계 완료(2b는 PR #5, 완료 기준을 사용자가 화면으로 확인: QGC 연결과 비행, Gazebo GUI에 x500). 3단계 완료(PR #10, 사용자 육안 확인 2건 남음). 4단계 구현 완료, 검토와 PR 전(브랜치 `feat/1a-4-idsim-common`, 계획과 계약은 `docs-for-agent/plan-1a-4-idsim-common/`) | 2026-11-10 | 스모크 설계는 `docs/smoke-test.md` |
| 1b | 시작 전 | 2026-11-06 | |
| 2 | 시작 전 | 2026-11-06 | |
| 3 | 시작 전 | 2026-11-06 | |

## 결정 기록

- 2026-11-06: 지원 호스트는 x86_64 Linux만. arm64(Apple Silicon Mac, Jetson Orin)는 Linux 환경이 Phase 3까지 완전히 동작한 뒤 확장 단계에서 검토.
- 2026-11-06: ROS 2 rmw는 CycloneDDS로 고정. FastDDS의 컨테이너 간 공유 메모리 함정을 피하기 위함. uXRCE-DDS Agent는 내부 FastDDS 그대로 두고 RTPS로 상호 운용.
- 2026-11-06: 기체 번호는 1부터, 네임스페이스는 항상 `PX4_UXRCE_DDS_NS`로 명시. 인스턴스 0의 네임스페이스 없음 케이스는 쓰지 않음. 모든 식별자는 `config/fleet.yaml`에서 파생.
- 2026-11-06: 표적은 `TargetState` 계약으로만 소비. Gazebo pose는 `idsim_sim` 어댑터가 변환. 표적 엔티티는 Gazebo Actor.
- 2026-11-06: 시간의 정식 기준은 `/clock`(시뮬레이션 시간). rosbag2 기록은 `--use-sim-time`, `/clock`은 미기록.
- 2026-11-06: 통합 테스트는 launch_testing 대신 compose fixture + rclpy. pytest는 `ros-ws` 컨테이너 안에서 실행.
- 2026-11-06: 베이스 이미지를 `ros-base`와 `sim-base`로 분리. 버전은 `docker/versions.env` 한 곳에서 고정.
- 2026-11-06: 3대 SITL 시나리오는 nightly 전용. PR에서는 단일 기체만.
- 2026-11-06: 저장소는 공개. CI는 GitHub Actions 무료 러너(4 vCPU) 한도 안에서만 쓴다.
- 2026-11-06: 브라우저 게이트웨이는 Rust(tonic + axum)로 구현. Rust는 ROS 2 비의존 컴포넌트에만 쓴다.
- 2026-11-06: 이미지 레지스트리는 ghcr.io/danielhongwoo/idsim. 공개 저장소의 공개 패키지로 둔다.
- 2026-11-06: 스모크 S1(인스턴스 0, 진단용)은 로컬에서 1회만 실행하고 CI에는 넣지 않는다.
- 2026-11-06: 이미지는 5종(ros-base, sim-base, px4, ros-ws, xrce-agent). 사용자 승인.
- 2026-11-06: Fleet Manager 구현 언어는 C++로 확정. gRPC 서버 스레드와 rclcpp executor가 공유하는 상태는 명시적으로 보호하고 설계 문서에 표로 남긴다.
- 2026-11-06: PX4 태그는 v1.17.0, px4_msgs는 release/1.17의 커밋 SHA, PX4-gazebo-models는 v1.17.0 서브모듈이 가리키는 b6127f4ec20de867e215fb5f78ae88b80f371909, Agent는 v2.4.3. v1.16.2를 버린 이유: 두 태그 사이에 메시지 버전이 바뀐 토픽이 있어(VehicleLocalPosition 0 -> 1) 어차피 태그별 골든이 필요하고, 정식 최신이 매핑 설계를 가장 세게 시험한다. 스모크 S4 통과가 확정 조건이며 실패하면 이 결정으로 돌아온다.
- 2026-11-06: 스모크 S1은 `make px4_sitl gz_x500`을 문자 그대로 돌리지 않고 runtime 이미지의 `px4` 바이너리를 `-i` 없이 실행한다. make 타깃이 하는 일은 `PX4_SIM_MODEL=gz_x500 GZ_IP=127.0.0.1`을 주고 rootfs에서 px4를 실행하는 것뿐이라 rcS 경로가 같다. make는 builder 스테이지 안에서만 쓴다. S1은 인스턴스 0을 쓰는 유일한 예외다.
- 2026-11-06: 스모크 타임아웃은 예외적으로 벽시계. 1단계에는 `/clock` 브리지가 아직 없기 때문이다. `/clock` 공급 주체는 `bridge` 서비스(ros-ws + ros_gz_bridge)이며 1b에서 1a로 당긴다. 1단계 S5에서 와이어 호환 실측용으로 처음 올라오고, 노드와 테스트는 6단계부터 이것을 시간 기준으로 쓴다.
- 2026-11-06: px4 healthcheck는 토픽 수신 대신 컨테이너 안 `px4-uxrce_dds_client --instance N status`의 문자열 판정. 종료 코드가 연결 상태를 반영하지 않아 문자열로 본다. 모든 서비스 `restart: no`.
- 2026-11-06: 토픽 이름 매핑은 `MESSAGE_VERSION`에서 컴파일 시점 파생이 단일 출처, 키는 논리 이름과 타입의 쌍(2026-11-10 결정 (r)이 key를 방향과 논리 이름으로 갱신했다). 태그별 손 매핑 테이블은 두지 않는다. 골든은 `tests/fixtures/px4/<PX4_TAG>/`에 결정적 값만 추적하고 측정 주기는 골든에서 제외. 골든 디렉터리가 없으면 단위 테스트는 SKIP이 아니라 FAIL. 갱신은 `--update-golden`과 px4, ros2 담당자의 diff 승인.
- 2026-11-06: 측정 주기는 계약이 아니라 참고값. 수신 판정은 "T초 안에 1회 이상". 주기 하한 계약은 Phase 3에서 Fleet 타임아웃이 필요한 토픽에만.
- 2026-11-06: 모델은 sim-base `/opt/px4-gz` 한 벌. px4 runtime은 복사하지 않고 심볼릭 링크로 gz_env.sh의 빌드 경로를 살린다. 공유 볼륨은 CI 캐시와 맞지 않아 쓰지 않는다. px4 builder가 서브모듈 커밋을 `versions.env`와 대조.
- 2026-11-06: sim-base의 Gazebo는 OSRF apt(PX4 gz_bridge가 그 헤더를 찾음), ros-ws의 ros_gz_bridge는 ROS vendor gz-transport. 한 프로세스에 둘이 섞이는 경로가 없어 와이어 호환만 문제이며 스모크 S5가 실측한다. 실패하면 bridge만 sim-base 계열로 옮긴다.
- 2026-11-06: xrce-agent 이미지는 ubuntu:24.04 digest 베이스의 별도 이미지(5종째). ros-base 위에 올리면 소스 빌드한 Fast-DDS가 `/opt/ros/jazzy`와 섞일 수 있고, CI에서 레이어 공유 이득이 없다. 에이전트에는 `ROS_DOMAIN_ID`를 주지 않는다(도메인은 PX4 client가 넘긴다).
- 2026-11-06: cyclonedds.xml은 환경변수 치환 없는 고정 파일 하나(유니캐스트 피어 127.0.0.1, 멀티캐스트 끔. 처음의 lo 인터페이스 고정은 같은 날 S1 실측 후 철회, 아래 결정 참조). 설정 없음과의 비교는 `CYCLONEDDS_URI`를 비워서. 멀티 호스트는 그때 gen_compose가 생성.
- 2026-11-06: 스택 오프셋에 `GZ_PARTITION` 추가. 판정 QoS는 `sensor_data` 하나, 상태 전이는 "최신 상태 N회 연속"으로 판정.
- 2026-11-06: Offboard 손실 동작 파라미터 이름은 `COM_OBL_RC_ACT`(4 = Land). 설계 문서가 적어 온 `COM_OBL_ACT`는 v1.17.0에 없는 이름이며, 잘못된 이름은 rcS `param set`이 오류만 찍고 넘어가 기본값이 남는다. 문서 전체를 고쳤고 S4의 `param show` 저장값에서 값 4를 확인한다.
- 2026-11-06: px4 실행 명령은 `px4 -i N`(이미지가 `build/px4_sitl_default/bin`을 PATH에 넣음). 작업 디렉터리 `rootfs` 기준으로 `bin/px4`는 존재하지 않는다.
- 2026-11-06: 버전 키 이름은 `versions.env`의 것을 따른다. 골든 `env.txt`와 설계 문서의 `PX4_MSGS_SHA`를 `PX4_MSGS_REF`로 통일. 이유: versions.env가 단일 출처이고 `PX4_GZ_MODELS_REF`, `PX4_ROS_COM_REF`와 일관.
- 2026-11-06: gazebo 서비스는 PX4-gazebo-models 원본 `server.config`에서 PX4 전용 플러그인 두 줄(`libOpticalFlowSystem.so`, `libGstCameraSystem.so`)을 뺀 `/opt/px4-gz/server.idsim.config`를 쓴다. sim-base가 생성하고 지운 줄 수 2를 검사, 원본은 px4 builder diff 검사용으로 유지, px4 runtime의 `gz_bridge/server.config` 링크도 이 파일로. gz_plugins를 sim-base에 넣는 안은 OpenCV, GStreamer 의존과 비재현 빌드 때문에 기각. x500 기본 모델에 카메라와 광류 센서가 없다.
- 2026-11-06: gazebo 서비스는 `gz sim -s`만 쓰고 `--render-engine` 플래그를 주지 않는다. x500 월드에 렌더링 센서가 없어 렌더 엔진이 초기화되지 않고, ogre 1.x는 X 없이 돌지 않는다(sim-engineer, gz-rendering8 소스). `HEADLESS`, `PX4_GZ_SIM_RENDER_ENGINE`은 rcS 전용임이 소스로 확인. 카메라를 쓰는 확장 단계에서 ogre2 + `--headless-rendering` + llvmpipe.
- 2026-11-06: px4_ros_com은 release/1.17 브랜치가 없어 `PX4_ROS_COM_REF`를 release/1.16 HEAD와 같은 main 커밋 86e9aeb로 고정. `frame_transforms`의 v1.17.0 호환은 가정이며 1a 4단계에서 확인, 안 맞으면 `idsim_common`이 변환을 직접 구현(2026-11-10 결정 (q)로 확정: 직접 구현).
- 2026-11-06: 1단계 임시 규칙으로 스택 오프셋은 `run_smoke.sh`가 `ROS_DOMAIN_ID`, `GZ_PARTITION`, `IDSIM_AGENT_PORT`로 계산해 compose에 넘긴다. compose 보간이 산술을 못 하기 때문이다. 1단계에서 compose 직접 실행은 지원하지 않으며 3단계 `gen_compose.py`가 대체한다.
- 2026-11-06: `config/cyclonedds.xml`에서 `NetworkInterface` 고정을 뺀다. 유니캐스트 피어 127.0.0.1, 멀티캐스트 끔, `ParticipantIndex auto`만 남긴다. 설계 토론의 "lo + 피어로 Fast DDS 에이전트와 SPDP 성립"은 추측이었고 S1 실측에서 틀렸다. 에이전트는 호스트 인터페이스 주소만 광고하고 `interfaceWhiteList` 프로필을 적용하지 않는다. 고정을 빼면 fmu 토픽 65개 확인.
- 2026-11-06: 격리는 도메인 ID로만 한다. 기본 스택 오프셋 k=0에서 `ROS_DOMAIN_ID` = 20 + k, 에이전트 포트 = 8888 + k, `GZ_PARTITION` = `idsim-<k>`. 도메인 0은 같은 호스트의 다른 ROS 2 스택(개발 호스트에 open_manipulator, zenoh 등이 host 네트워크로 떠 있음)이 쓰므로 피한다. CI도 같은 규칙, 예외 없음. px4 서비스에도 같은 `ROS_DOMAIN_ID`. `GZ_PARTITION`은 항상 명시해 다른 Gazebo 인스턴스와 분리.
- 2026-11-06: 모든 compose 파일은 `name:`을 명시한다. `gen_compose.py`도 `idsim-<k>`를 넣는다. 미지정 시 디렉터리명 `docker`가 프로젝트 이름이 되어 충돌한 사고가 있었다.
- 2026-11-06: 설계에 적힌 판정은 전부 1차 구현 범위. 가정의 반증 지점(특히 `param show` 저장값의 `COM_OBL_RC_ACT` = 4, `COM_RC_IN_MODE` = 4, `commander check`)이 구현에 없으면 파라미터 이름 오타 같은 조용한 실패를 못 잡는다. S1 복구 후 S2 전에 채운다.
- 2026-11-06: 이미지는 빌드 버전을 `IDSIM_BUILD_<키>` ENV로 남기고 `run_smoke.sh`가 S0 전에 `versions.env`와 대조해 다르면 실패. 골든 `env.txt`의 값은 이미지 ENV에서 읽는다. `versions.env`만 올리고 이미지를 안 올린 채 옛 측정값이 새 골든이 되는 것을 막는다.
- 2026-11-06: embedded px4 서비스에는 `HEADLESS=1`을 준다(rcS가 읽어 GUI를 띄우지 않음, 실측). "HEADLESS를 주지 않는다"는 gazebo 서비스에만 해당한다.
- 2026-11-06: px4는 데몬 모드 `px4 -d`로 실행한다. 컨테이너 stdin이 닫힌 상태에서 대화형 pxh 셸이 프롬프트를 끝없이 출력해 로그가 단계당 수십 MB, 15분 방치 시 4GB까지 불었다. `-d`에서 로그 36MB가 54KB로 줄었고 `px4-commander`, `px4-param`, `px4-uxrce_dds_client` 모듈 명령은 그대로 동작한다.
- 2026-11-06: airframe `4001_gz_x500`이 `NAV_DLL_ACT`를 `set-default 2`로 덮어써 `PX4_PARAM_NAV_DLL_ACT=0`이 무시된다(펌웨어 기본값과 같은 값은 변경으로 기록되지 않기 때문). px4 이미지에 공식 훅 `etc/init.d-posix/airframes/4001_gz_x500.post`를 넣어 `PX4_PARAM_*`를 다시 적용한다. 다른 기체를 쓰면 같은 훅이 필요하다.
- 2026-11-06: `artifacts/`의 root 소유 파일 문제는 1단계에서 감수하고 3단계 `gen_compose.py`의 `user` 매핑에서 닫는다. 지금 비루트 사용자를 넣으면 ros-ws 이미지의 HOME과 로그 디렉터리 설정이 따라와 스모크 범위가 커진다.
- 2026-11-06: Foxglove 화면 앱은 Lichtblick(사용자 결정). 이유: 계정 없이 로컬에서 쓸 수 있고 MPL 라이선스, 공식 이미지(2.5.2, 285MB)를 digest로 고정할 수 있다. 공식 Foxglove 앱은 쓰지 않는다. 브리지는 ros-jazzy-foxglove-bridge 3.6.0(서브프로토콜 foxglove.sdk.v1, 현재 cyclonedds.xml로 채널 69개 수신 실측).
- 2026-11-06: 시각 도구 구성(사용자 결정, sim-engineer 실측 근거). compose 프로필 `viz`에 `gz-gui`(sim-base에서 `gz sim -g`로 기존 서버에 클라이언트만 붙임, WorldControl을 뺀 `gui.config`), `foxglove`(ros-ws + foxglove_bridge, 127.0.0.1, 8765 + k, 토픽 화이트리스트, clientPublish, services, parameters 제외로 읽기 전용), `lichtblick`(공식 이미지 digest 고정, 127.0.0.1의 18080 + k). QGroundControl은 compose 서비스가 아니라 호스트 스크립트 `tools/qgc.sh`(버전과 sha256은 `versions.env`, 캐시, 종료는 TERM 뒤 유예를 두고 SIGKILL). `viz` 프로필은 어떤 서비스의 `depends_on` 대상도 아니고 `run_smoke.sh`, pytest fixture, CI는 켜지 않는다. 3대 시나리오 CPU 측정은 GUI 없이. 로드맵은 1a 2b단계(3단계 전 작은 작업), 3단계 `viz` 프로필 생성, 6단계 foxglove_bridge(Phase 2에서 당김)로 배치. gz 웹 시각화(gz-launch websocket)는 프런트엔드 미성숙으로 보류, VNC는 17 fps에 2코어라 원격 작업이 생길 때만.
- 2026-11-06: Gazebo GUI의 GPU 경로는 실측대로 문서화. 컨테이너 안 OpenGL은 VMware SVGA3D(Mesa 25.2.8, OpenGL 4.3), Xwayland가 DRI3로 렌더 노드를 넘겨 `--device /dev/dri` 없이 약 90 fps. llvmpipe 강제 시 15 fps. sim-base Qt5에 wayland 플러그인이 없어 xcb만. GUI를 붙이면 서버 CPU 21%에서 31%, RTF 1.0 유지.

- 2026-11-09: sim-base에 `libqt5svg5` 추가(sim-engineer 실측). 기존 이미지의 GUI `-v 4` 로그에 SVG 디코딩 경고 29건, 설치 뒤 0건. 추가 의존성 없이 libqsvg.so만 들어온다. 이미지 키가 바뀌어 CI가 sim-base와 px4를 다시 빌드한다.
- 2026-11-09: `idsim_sim/config/gui.config`는 gz-sim8 기본 `/usr/share/gz/gz-sim8/gui/gui.config`에서 WorldControl 블록만 뺀 것(플러그인 17개). gz 버전을 올릴 때는 새 기본 파일에서 같은 방식으로 다시 만든다. 이미지에 넣지 않고 컨테이너에 읽기 전용으로 마운트한다.
- 2026-11-09: QGC 릴리스 자산은 `QGroundControl-x86_64.AppImage`(v5.1.5, 195,332,600바이트), sha256은 GitHub API digest와 대조해 `versions.env`에 고정. `qgc.sh`는 versions.env를 source하지 않고 두 키만 grep으로 읽는다(다른 값에 `@`가 있음).

- 2026-11-09: "QGC AppImage가 SIGTERM을 무시한다"는 2026-11-06 관측은 reviewer 재실험으로 반증됐다. AppRun이 QGC 바이너리를 exec하므로 `qgc.sh`의 자식 PID가 QGC 본체이고, 그 PID에 TERM을 보내면 1초 안에 종료 코드 0으로 끝나며 설정(QGroundControl.ini)이 저장된다. 원래 관측은 FUSE 도우미 PID에 보냈거나 기체 연결 상태의 종료 확인 대화상자였을 가능성이 크다. `qgc.sh`는 TERM -> 5초 유예 -> KILL로 바꿨다(INT는 130, TERM은 143). 기체가 연결된 상태의 TERM 동작은 미실측. 2026-11-09 호스트 재확인: INT는 정상 종료(130), TERM도 끝나지만 한 번은 QGC가 종료 중 segfault를 냈다(프로세스와 마운트 잔재 없음).

- 2026-11-09: `gui.config`에 GridConfig 플러그인 추가(플러그인 18개). PX4 기본 월드(`default.sdf`)는 `<grid>false`, 배경 0.7, 바닥 0.8 회색이라 GUI에서 기체 이동이 보이지 않았다. gz-gui 8의 Grid3D는 QML 리소스가 없어 로드 실패(`Can't find :/Grid3D/Grid3D.qml`). GridConfig는 장면에 격자가 없으면 기본 격자를 만든다.
- 2026-11-09: 기체 출발 위치는 PX4 환경변수 `PX4_HOME_LAT/LON/ALT`(셋 다 필수)로 바꾼다. `px4-rc.gzsim`이 시작 시 `/world/<월드>/set_spherical_coordinates` 서비스를 불러 월드 기준 좌표를 바꾼다(서울시청으로 실측, PX4 `sensor_gps`가 37.5660, 126.9785를 보고). QGC에는 기본 위치 설정이 없고 기체 위치를 따라간다. 저장소에는 README의 덮어쓰기 예시만 두고 정식 값은 3단계 `fleet.yaml`에 넣는다.

- 2026-11-09: Gazebo GUI 창이 검게 나오던 원인은 컨테이너 IPC 네임스페이스. VM 3D 가속을 끈 상태(커널 vmwgfx 기능 목록에 3D 없음, Xwayland가 DRI3를 제공하지 않음, Mesa llvmpipe)에서 Mesa 소프트웨어 경로가 MIT-SHM으로 X 서버에 프레임을 넘기는데 컨테이너의 IPC가 분리되어 X 서버가 붙지 못했다. GUI 내부 스크린샷 서비스는 정상 프레임을 저장했으므로 렌더링 자체는 됐다. `docker run --ipc=host`로 해결(xwd 캡처로 확인). 하드웨어 DRI3 경로(2026-11-06 실측)에서는 dma-buf로 넘기므로 증상이 없었다. 3단계 `gz-gui` 서비스에 `ipc: host`를 넣는다.
- 2026-11-09: GridConfig 기본 격자는 색이 0.7 회색이라 0.8 바닥 위에서 보이지 않는다. `<insert>`로 50 x 50 m, 1 m, 색 0.25를 지정하니 선명하다(스크린샷 확인). MinimalScene의 `<sky>true</sky>`는 "Child elements of <sky> are not supported" 경고만 내고 효과가 없어 넣지 않았다.

- 2026-11-09: Gazebo GUI에서 기체가 안 보이는 흔한 원인은 거리다. 기본 카메라는 원점(-6, 0, 6)을 보는데 QGC로 비행한 기체는 178 m 밖에 있었다. Entity Tree에서 x500_1 오른쪽 클릭 -> Move To 뒤 Follow를 거는 순서가 확실하다(Move To 없이 Follow만 걸면 따라가지 않는 경우가 있었다). 서비스로는 `/gui/move_to`(StringMsg) 뒤 `/gui/follow`, 오프셋은 `/gui/follow/offset`. 격자는 바닥 평면 전체(500 x 500 m, 2 m 칸)로 넓혔다. GUI 안 `/gui/screenshot` 서비스(StringMsg에 디렉터리)로 렌더 프레임을 파일로 받을 수 있어, 화면 없이도 렌더링 결과를 확인하는 데 쓸 수 있다.

- 2026-11-09: 루트 `README.md`와 `tools/check_host.sh` 추가(devops-engineer, reviewer 검토 반영). reviewer가 포트 충돌 검사가 `ss -ulnp`의 5번째 열(Peer)을 보던 결함을 실험으로 잡아 4번째 열(Local)로 고쳤고, UDP 8888을 점유한 상태에서 WARN이 나오는 것을 확인했다. 권장치는 근거가 있는 값만 적는다: 메모리는 확인된 최소 16GB(CI 러너) 미만을 WARN, 디스크 30GB는 이미지 합 8.6GB + px4 builder 7.7GB + 캐시. python3은 3.12 확인, 하한 3.10. 에이전트 포트 검사는 `IDSIM_STACK_INDEX`를 따른다. 스크립트 단위 테스트(가짜 ss, df, docker를 PATH에 두는 셸 테스트)는 test-engineer 판단으로 미룬다.

- 2026-11-09: 1a 3단계(`config/fleet.yaml`, `tools/gen_compose.py`) 설계 토론 결정. architect 주재, devops/px4/ros2/sim 의견, reviewer 실측 검증(k=5, Docker 29.1.3, Compose 2.40.3), 사용자 결정 4건. 설계 문서 반영은 같은 날 브랜치 `docs/phase1a-step3-design`.
  - (a) 생성물은 `artifacts/runs/<run_id>/{compose.yaml, stack.json, px4-N/, ros_log/}`에 구체값으로. `generated/stack-<k>/` 고정 경로는 기각(px4 `rootfs/N`을 실행마다 새로 만들어야 이전 `parameters.bson` import를 막고, 무엇으로 돌았는지 산출물로 남는다). 골든은 `tests/fixtures/gen_compose/<사례>/`에 고정 인자로. `stack.json`이 실행 시점 단일 출처(`IDSIM_STACK_FILE`), 스크립트와 fixture는 식별자를 재계산하지 않는다. 3단계 생성물은 compose.yaml과 stack.json 둘뿐이고 ROS params 파일과 bridge 설정은 소비자가 생기는 6단계에서. launch 파일은 생성하지 않는다.
  - (b) 월드 원점은 gazebo 서비스의 wrapper(`idsim_sim/scripts/gz_server.sh`, sim-engineer)가 월드 로드 직후 `set_spherical_coordinates`를 한 번 호출하고 표시 파일을 남긴다. px4-N에는 `PX4_HOME_*`를 주지 않는다. reviewer 실측: gz 경로의 소비자는 `px4-rc.gzsim` 93-105뿐이지만 `px4-rc.sihsim` 5-13도 읽는다(SIH 변형 추가 시 주의). 응답 `data: true`는 세 경우 모두 돌아와 요청 수리일 뿐 적용 확인이 아니므로 적용은 S2 판정의 `sensor_gps` 좌표로 본다. 같은 값 재호출은 navsat 값 동일, 다른 값은 즉시 변경(비행 중 GPS 점프). 키 이름은 `origin`(PX4 home position과 혼동 방지). 1b 커스텀 월드는 SDF `<spherical_coordinates>`에 넣고 wrapper는 건너뛴다.
  - (c) MAVLink는 px4 이미지가 PATH 앞에 두는 idsim용 `px4-rc.mavlink`로 스택 오프셋 1000k(GCS 14550 + 1000k, API 14540 + 1000k + N, 로컬 18570/14580 + 1000k + N, payload와 gimbal 제거, 상류 sha256 기록). 근거: 오프셋 없이 두 스택을 올리면 두 번째 px4가 `WARN  [mavlink] bind failed: Address already in use`(18571, 14581, 14281, 13031)를 내고 계속 동작, 첫 스택 무영향(reviewer 실측). 생성기가 `IDSIM_MAVLINK_OFFSET`을 넘기고 stack.json에 포트를 적는다. 완료 기준의 "k=1 동시 S2"는 두 스택 px4 로그 모두에 `WARN  [mavlink] bind failed` 부재로 판정(check_px4_log). netns 분리 카드는 꺼내지 않는다. `MAV_SYS_ID`가 같아 QGC 하나는 한 번에 한 스택만 본다(interface.md에).
  - (d) fleet.yaml 스키마: `schema`, `world.{name, file, origin{lat,lon,alt}, speed_factor}`, `vehicles[].{id, airframe, pose{x,y,z,yaw}, px4_params}`, `targets`, `px4.{params_file, start}`. `airframe` 하나에서 SYS_AUTOSTART, PX4_SIM_MODEL, 모델 이름 `<모델>_N` 파생(x500_N 규칙의 일반화). pose는 Gazebo 월드 좌표 ENU, m, rad, 2 m 미만 거부, 4 m 미만 경고, 3대 예시 y 0, 4, 8. 파생값 키와 식별 파라미터(MAV_SYS_ID, UXRCE_DDS_KEY, UXRCE_DDS_DOM_ID, UXRCE_DDS_AG_IP, SYS_AUTOSTART)는 거부. `stack`, `viz` 섹션은 두지 않는다. k는 `--stack` > `IDSIM_STACK_INDEX` > 0, 기준값은 생성기 상수. 1a에서 `targets`는 비어야 하고 `speed_factor`는 null이어야 한다(Phase 3에서 sim과 px4가 기제 결정).
  - (e) k 범위 0-9. MAVLink 로컬 18579 + 1000k가 임시 포트 범위 아래여야 하고(k <= 14), 한 자리가 이름과 손계산을 단순하게 한다. DDS 포트 범위(12400 + 250k부터 참가자 인덱스 50까지)와 MAVLink 포트는 k 0-9, N 1-9에서 겹치지 않음을 손계산했고 생성기 단위 테스트가 전 범위를 검사한다. 에이전트 FastDDS 참가자 인덱스는 0으로 실측(도메인 25에서 13660/13661). 보강(2026-11-10): 한 스택에 기체 N대면 에이전트 참가자 인덱스는 0..N-1(3대 실측).
  - (f) gz-gui의 gazebo `depends_on`은 허용(금지는 본 스택 -> viz 방향뿐). 편집 플러그인(Spawn, Shapes, TransformControl, ComponentInspector)은 3단계에서 빼지 않는다(WorldControl 제거 목적은 한 번 클릭 사고 방지였고 TransformControl은 선택 기능을 겸한다). `ipc: host`, 호스트 uid:gid, `HOME=/tmp/gz-home`, `${XAUTHORITY:-/dev/null}` 마운트와 wrapper의 빈 파일 점검, `--render-engine-gui ${IDSIM_GZ_GUI_ENGINE:-ogre2}`, 렌더링 환경변수는 이름만 통과, `/dev/dri`와 NVIDIA는 opt-in. viz 서비스에 `${X:?}` 금지(꺼진 프로필도 보간됨, devops와 sim 실측).
  - (g) 생성기는 인스턴스 0을 지원하지 않는다. S1은 2026-11-06 1회 기록으로 남기고 재현하지 않는다(사용자 동의). `--variant embedded`(1대, gazebo 서비스 없음, `HEADLESS=1`)로 S1b는 유지. `compose.smoke.yaml`은 삭제.
  - (h) 생성기는 ros-ws 컨테이너에서 실행(`tools/gen_compose.sh`, 호스트 uid:gid, `--network none`, `CYCLONEDDS_URI` 비움). 사용자 결정으로 호스트 조건(표준 라이브러리만) 불변. 핵심은 dict -> dict 순수 함수, PyYAML은 읽기와 쓰기만. 단위 테스트는 lint 잡의 python:3.12-slim에 `pyyaml==<LINT_PYYAML_VERSION>`(ros-ws의 6.0.1, S0에서 대조). reviewer 실측: cyclonedds.xml을 마운트하지 않은 채 `CYCLONEDDS_URI`가 남아 있으면 rmw가 파일을 못 열어 모든 ROS CLI가 실패한다.
  - (i) 호스트에 쓰는 서비스(px4-N, bridge, ros-ws, 러너, gz-gui)만 호스트 uid:gid, `HOME`은 컨테이너 `/tmp`, ROS 로그는 `ROS_LOG_DIR`로 run 디렉터리에. agent와 gazebo는 root. px4는 `rootfs/N` 전체를 `artifacts/runs/<run_id>/px4-N/`에 마운트(rootfs 1777 안 기각). reviewer 실측: uid 1001(passwd에 없음)에서 ros2 CLI, rclpy, doctor, px4 SIH와 standalone 스폰(29초 healthy), gz service 모두 동작, 깨지는 것은 whoami, pwd.getpwuid, getpass.getuser뿐. 규칙: 저장소 코드에서 `getpass`, `pwd`(getpwuid) 호출 금지. 중첩 바인드 마운트는 마운트 지점을 root 소유로 만들므로 생성기 단위 테스트에 "중첩 마운트 없음"을 넣는다.
  - (j) px4 healthcheck는 uxrce `Running, connected` 항만 남긴다. `px4-gz_bridge --instance N status`는 연결 상태 문자열이 없고(mixer 출력 60줄, rc 0) gazebo를 멈춰도 rc 0, 옛 모델이 남은 상태에서 재시작해도 로그가 정상과 같고 중복 create도 `data: true`라 gz_bridge 항과 모델 유일성 항은 근거를 잃었다(reviewer 실측). 옛 모델 부착 방지는 운영 규칙으로: `restart: no`, 운영 스크립트(`tools/stack.sh`, `run_smoke.sh`)는 up 전에 down, gazebo healthy 뒤 px4를 올리기 전 `gz model --list`에 `<모델>_N` 없음 사전 검사, healthy 뒤 S2 판정에서 모델 정확히 하나. gazebo healthcheck는 scene/info AND 원점 표시 파일. bridge는 interval 30초와 `start_interval` 5초(Compose 2.40.3, Docker 29.1.3에서 수용 실측, 하한 미실측). 러너 서비스는 프로필 `tools`(`compose run`이 프로필 지정 없이 실행함을 실측).
  - 에이전트는 포트 bind 실패 시 `bind error ... errno 98` 뒤 종료 코드 0으로 끝나고 `up --wait`는 unhealthy로 실패한다(오탐 없음, reviewer 실측). 운영 스크립트는 `up --wait` 실패 시 에이전트 로그의 `bind error`를 찾아 보고한다. `check_host.sh`의 8888 + k 점검은 유지.
  - 그 밖에 합의: compose `name: idsim-<k>`(스모크 포함), host 네트워크, `restart: no`, `GZ_IP=127.0.0.1` 유지, `MAV_SYS_ID = UXRCE_DDS_KEY = N + 1`은 PX4가 `-i N`에서 자동 설정(rcS 140-141)이라 compose에 넣지 않고 stack.json에만, `.post` 훅은 Dockerfile이 `airframes/*_gz_*` 전부에 생성하고 1a 허용 airframe은 `4001_gz_x500` 하나, 기체별 `px4_params`는 이름 `^[A-Z0-9_]{1,16}$`와 값 공백 금지 검사. lockstep은 gazebo 정지 시 PX4 정지(한 방향 실측).
- 2026-11-09: 사용자 결정 4건(3단계). (1) `world.origin` 기본값은 서울시청(37.5665, 126.9780, 38). (2) 파서는 ros-ws 컨테이너 안에서 실행, 호스트 조건 불변. (3) S1(인스턴스 0) 재현 포기, embedded(S1b) 유지. (4) 편의 스크립트 `tools/stack.sh`(up|down|logs)와 `tools/qgc.sh --stack k`(다른 k의 GCS 포트) 둘 다 3단계에 추가, devops-engineer 범위. `qgc.sh --stack`은 QGC Comm Link 설정 방법(설정 파일 또는 명령행 인자) 조사가 필요하다.

- 2026-11-09: 3단계 A 완료(px4-engineer, reviewer와 devops 접점 검토 반영). `docker/px4/px4-rc.mavlink`가 PATH 맨 앞에서 상류를 대체하고 `IDSIM_MAVLINK_OFFSET`(0 또는 앞자리 0 없는 십진수, 최대 9000)을 GCS/API 포트에 더한다. 실측: 오프셋 1000, -i 1에서 15550에 sysid 2 패킷 4809개, 15541에 5256개, 14550과 14541에 0개. 오프셋 0은 기존과 동일. reviewer 재현(오프셋 2000, -i 3): 16550에 5433개, 16543에 5993개. 추가 결정: 상류에 `.post`가 이미 있는 gz airframe이 생기면 빌드를 실패시킨다(훅이 조용히 빠지거나 덮어쓰는 것 방지. v1.17.0에는 없음). N=0은 수동 실행용으로 거부하지 않는다. px4 이미지 키 변경(builder 단계 캐시 유지). `docker/px4/px4-rc.mavlink`는 `*.sh`가 아니라 lint.sh shellcheck 대상 밖이며 C에서 devops가 명시 경로로 추가한다.
- 2026-11-09: 3단계 B 완료(sim-engineer, reviewer 검토 반영). `ros_ws/src/idsim_sim/scripts/gz_server.sh`(월드 이름 검사, 서버 자식 실행, scene/info 대기 60초, 원점 1회 호출과 `data: true` 확인, 표시 파일, TERM 뒤 5초 유예 후 KILL, INT 130/TERM 143)와 `gz_gui.sh`(DISPLAY, Xauthority, GUI 설정 점검, HOME 대체, XAUTHORITY=/tmp/.Xauthority를 스스로 export). 실측: wrapper가 원점을 적용한 뒤 PX4_HOME_* 없이 붙인 px4의 `sensor_gps`가 37.566500, 126.978000(서울시청). healthcheck 창 없음(표시 파일은 원점 응답 뒤에만 생기고 시작 시 삭제, reviewer 실측).
- 2026-11-09: 준비 파일 단일화(결정 (j) 보완). wrapper는 원점 단계가 끝나면 원점 유무와 무관하게 `/tmp/idsim/ready`를 쓰고, 원점을 적용한 경우에만 `/tmp/idsim/origin_set`을 더 쓴다. gazebo healthcheck는 한 가지: `gz service -i --service /world/<이름>/scene/info | grep -q "Service providers" && test -f /tmp/idsim/ready`. 근거: 원점이 있을 때 생성기가 표시 파일 항을 빠뜨리면 "스폰은 원점 설정 뒤"가 조용히 깨지는 경로를 없앤다. gz-gui 기본 설정 경로는 `/opt/idsim/sim/config/gui.config`(패키지 전체를 `/opt/idsim/sim`에 마운트).
- 2026-11-09: `--render-engine-gui ogre`는 gui.config의 `<engine>ogre2</engine>`을 덮는다(sim-engineer 실측: OGRE 1.9 라이브러리 로드, GridConfig 격자 렌더링 정상). 미해결 항목 닫힘.

- 2026-11-10: 3단계 C 결정(architect 주재, devops/test/ros2/sim/px4 의견, reviewer 검토). 구현은 `feat/step3-compose`.
  - (k) 스모크 S2-S5는 운영 스택과 같은 구성으로 `bridge`까지 올린다. `startup.stages`는 세 단계: standalone `[[xrce-agent, gazebo], [px4-1..N], [bridge]]`, embedded `[[xrce-agent], [px4-1]]`. 변수 분리는 기동 단계가 맡는다. S5는 "bridge가 처음 올라오는 단계"가 아니라 "/clock 품질 판정 단계"이며 `/clock` 발행자 수 1 판정을 더한다. 근거: 스모크 전용 구성을 따로 두면 운영 스택과 어긋난 채 통과할 수 있다.
  - (l) `run.id == basename(run_dir)` 불변식은 생성기가 보장한다. `--run-dir`만 오면 basename이 run id, 둘 다 오고 어긋나면 거부, 부모가 `<host_repo_root>/artifacts/runs`가 아니면 거부. 로더는 검사하지 않는다(옛 산출물 호환). `--run-id` 인자 제거는 다음 PR. `run.id`는 표시용이고 경로 조립에 쓰지 않는다.
  - (m) `stack.json`에 `inputs.cyclonedds_xml {path, sha256}` 추가(필수, null 불가, schema 1 유지, generator.version 증가). 골든은 상수 0 x 64(`versions_env` 선례). 소비자는 `run_smoke.sh`(스택 기동 뒤 판정 전에 저장소 `config/cyclonedds.xml`의 sha256과 대조, 다르면 실패)와 6단계 ST. 런타임 컨테이너는 `/opt/idsim` 마운트의 현재 파일을 읽으므로 생성 시점 해시와 다르면 참가자 간 DDS 설정이 섞인 상태다.
  - (n) 같은 `GZ_PARTITION`의 다른 gz 서버 검사(`scene/info` 제공자 1, `/clock` 발행자 1)를 `stack.sh` 사전 검사와 `run_smoke.sh` S2 양쪽에 둔다. 근거: sim-engineer가 재현한 사례(같은 파티션에 서버가 둘이면 모델 유일성 판정만으로는 못 잡는 경로가 있음).
  - (o) 설계와 달라진 구현 결정. 1) compose 안 경로는 절대 경로(`<host-repo-root>/...`). compose.yaml이 run 디렉터리에 있기 때문. 2) 바인드 마운트는 긴 형식에 `create_host_path: false`. 3) bridge/runner는 저장소를 `/opt/idsim`에 rw 하나만 마운트하고 `cyclonedds.xml` 중첩 마운트를 없앴다. 4) YAML 앵커 미사용(PyYAML가 merge 키를 출력하지 못하고 자동 앵커를 끔). 5) Docker Engine 25.0 하한은 문서 근거이며 `check_host.sh`가 WARN(실측 아님). 6) `lint.sh`에 `core.quotepath=off` 적용(한글 경로 파일이 검사에서 빠지던 버그). 7) lint의 `compose config -q`는 골든 compose를 `/work/idsim` 치환 후 `--profile viz --profile tools`, DISPLAY/XAUTHORITY 미설정으로 검사.
  - (p) `check_px4.py --expect-origin`은 `vehicle_gps_position`(SensorGps) 기준, 수평 0.5 m, 수직 1.0 m. 실측 최대 오차 수평 0.07 m, 수직 0.34 m. pose 보정은 하지 않는다(1대 기준). `derived_params`도 S2에서 `pxh`로 판정한다.
- 2026-11-10: 사용자 결정, 이미지 빌드 apt 미러를 kr로 (devops-engineer 구현, 브랜치 `chore/apt-kr-mirror`). archive.ubuntu.com이 이 호스트에서 다시 응답하지 않아(2026-11-09, 11-10 실측) 결정했다.
  - 미러 값은 `versions.env`의 `UBUNTU_APT_MIRROR=http://kr.archive.ubuntu.com/ubuntu`, 빌드 인자로 전달한다. `ros-base`와 `xrce-agent` build 단계의 첫 `apt-get update` 앞에서 `ubuntu.sources`를 sed로 바꾸고 바뀌었는지 grep으로 검사한다. sim-base, px4, ros-ws는 ros-base를 상속하므로 손대지 않았다.
  - archive와 security를 둘 다 바꾼다. kr 미러가 noble, noble-updates, noble-security InRelease를 제공함을 실측했고, 같은 호스트에서 security.ubuntu.com도 응답하지 않는 날이 있었다. 서드파티(packages.ros.org, packages.osrfoundation.org)는 그대로다.
  - 이미지 키에서 제외한다(`image_keys.py`의 `KEY_EXCLUDED_ARGS`). `ubuntu.sources`는 이미지에 남아 미러별로 바이트가 다르지만 런타임이 apt를 쓰지 않으므로 같은 이미지로 보며, 키는 원래 apt 패키지 버전을 고정하지 않는다. 미러 동기화 시차로 패키지 버전이 달라질 수 있는 위험은 같은 키의 이미지가 어느 미러에서 빌드됐든 같은 것으로 보는 것으로 받아들인다. 이번 변경은 Dockerfile 바이트가 바뀌어 5종 키가 한 번 바뀐다.
  - CI는 `build-images.yml`의 환경변수로 기본 미러(archive.ubuntu.com)를 쓰도록 덮어쓴다. `build_images.py`는 미리 설정된 `UBUNTU_APT_MIRROR` 환경변수를 versions.env보다 우선한다. 키가 같으므로 GHCR 키와 충돌하지 않고, CI의 레이어 캐시는 항상 같은 미러값이라 맞는다.
  - `tools/check_host.sh` (l) 항목은 같은 값을 읽는다.
- 2026-11-10 (1a 4번 작업 `idsim_common`. architect 결정, ros2/px4/devops 의견과 재질문, reviewer 검증 조건 반영. 원문, 근거, 담당자별 구현 지시는 `docs-for-agent/plan-1a-4-idsim-common/decisions.md`)
  - (q) 좌표 변환(쟁점 1). px4_ros_com `frame_transforms`를 래핑하지 않고 `idsim_common`이 직접 구현한다. px4_ros_com은 `test_depend`의 차등 비교 기준으로만 쓴다. 근거: 공분산 3x3 변환 두 개가 틀리고, 공개 템플릿 3개가 링크되지 않고, NED yaw 스칼라 변환이 없고, 동체 변환이 NaN을 다른 축으로 번지게 한다(TrajectorySetpoint는 NaN을 "제어 안 함"으로 쓴다). 벡터와 쿼터니언 정적 변환은 맞아 비교 기준으로 쓸 수 있다. 전체 공분산 회전은 소비자가 없어 뺀다. 원점 이동(월드 ENU -> 기체 로컬 NED)은 1b에서 별도 함수로 더한다. 2026-11-06의 "호환은 가정이며 4단계에서 확인" 결정을 이것으로 닫는다.
  - (r) 토픽 매핑(쟁점 2). 2026-11-06의 "키는 논리 이름과 타입의 쌍" 결정을 갱신한다. 골든 65개 전부를 기술자 목록 하나에 두고 key는 (방향, 논리 이름)이며 타입은 기술자에 묶인다. 접미사는 여전히 `MESSAGE_VERSION`에서 컴파일 시점에 파생한다(태그별 접미사 표를 두지 않는다는 취지 유지). 문자열 함수 `px4_topic<T>(ns, dir, base)`는 공개하지 않고, 공개 API(`topic_name`, `create_subscription`, `create_publisher`)는 목록에 등록된 기술자만 받는다(`is_registered`는 목록 안에서만 특수화, 목록 끝에서 매크로를 `#undef`). /fmu/in 기술자는 기본 Restricted이고 1a 허용은 `offboard_control_mode`, `trajectory_setpoint`, `vehicle_command` 셋뿐이다. 이 차단은 실수 방지 수준이며 보안 경계가 아니다(의도적 우회는 lint `px4-api`와 코드 리뷰로만 잡는다). 허용 목록 해제(Restricted -> Allowed)는 기술자 변경, px4-engineer 접점 승인, 이 결정 기록, 허용 목록 기대 집합 테스트 갱신, interface.md 공개 목록 갱신이 한 PR에 함께 있어야 한다. 타입 -> 이름 역조회 API는 두지 않는다. 근거: 목록이 하나일 것(ros2), 위험한 /fmu/in이 공개 API로 노출되지 않을 것(px4), 태그를 올릴 때 diff가 드러날 것을 모두 만족하고 컴파일 비용은 실측상 무시할 수준이다.
  - (s) QoS(쟁점 3). `px4_out_qos()`(구독)와 `px4_in_qos()`(발행) 모두 BEST_EFFORT, VOLATILE, KEEP_LAST 5, liveliness Automatic 명시. 계약은 reliability와 durability이고 골든의 history와 depth는 계약 밖이다(골든 depth 1은 rmw의 원격 엔드포인트 표시값). 늦게 붙은 TRANSIENT_LOCAL reader에게 에이전트가 이력을 주지 않음을 실측해 TL 구독의 이득이 없다. S4 골든 형식과 `--check`는 바꾸지 않는다.
  - (t) timestamp(쟁점 4, B안). 공통 SITL 파라미터에 `UXRCE_DDS_SYNCT=0`. /fmu/out timestamp는 PX4 hrt = Gazebo sim 시간(us)이고 /fmu/in timestamp는 노드 시계의 sim 시간(us)이다. 0과 벽시계 값은 보내지 않는다. 빌더와 6단계 setpoint 헬퍼는 강타입 `Px4Timestamp`만 받고, 이 타입은 `Px4Timestamp::now(rclcpp::Clock &)` 하나로만 만든다(RCL_ROS_TIME이고 `ros_time_is_active()`가 참이고 값이 있을 때만 성공. `rclcpp::Time` 값으로는 sim 시간인지 구분할 수 없다는 reviewer 실측 때문). 근거: use_sim_time 조건에서 PX4가 묵은 setpoint를 판정하는 조합은 SYNCT=0과 sim 시간뿐이고, PX4 timestamp, `/clock`, rosbag 기록 시각, ULog가 한 축에 놓인다. 적용 판정은 로그 grep이 아니라 `check_px4_pxh.py`의 `param show` 저장값으로 한다. 실기체에서는 SYNCT를 되돌리며 운용 노드는 모른다. sim 시간 경로의 회귀 판정(묵은 timestamp -> failsafe)은 6단계 통합 테스트로 고정한다.
  - (u) 식별과 빌더(쟁점 5, 6). `idsim_common`에 N+1 공식을 두지 않는다. 노드는 `stack.json`에서 생성된 params로 ns와 sysid를 받고 `vehicle_status.system_id`, `component_id`와 대조한다(`verify`의 결과는 Match, SystemIdMismatch, ComponentIdMismatch. 미수신은 호출자가 표현). 빈 네임스페이스와 "/"는 거부하고 `target_system` 0은 타입으로 만들 수 없다. VehicleCommand 빌더는 `VehicleIdentity`와 `CommandSource`(system 1-255, component 1-999) 없이 만들 수 없고, 고정 필드는 `target_component=1`, `from_external=true`, `confirmation=0`이다. 메서드는 arm, disarm, set_mode_offboard, set_mode_hold, land, rtl. "ACCEPTED = 성공" 헬퍼와 `raw()`는 두지 않고 ack 매칭 술어 `is_ack_for`만 둔다(DO_SET_MODE는 실패 조건에서도 ACCEPTED라 모드 성공은 nav_state 확인까지이며 그 상태기는 `idsim_mission`에 둔다). params 키 이름, 게이트 정책, source 값 표는 6단계로 넘긴다.
  - (v) 패키지와 CI(쟁점 7, 8). 패키지는 ament_cmake, SHARED 라이브러리와 템플릿 헤더, C++17, `-Wall -Wextra -Wpedantic -Werror`. ament linter는 `ament_lint_common` 묶음을 쓰지 않고 xmllint, lint_cmake, cpplint(`legal/copyright` 끔)만 쓴다. CI는 새 `unit` job이 ros-ws 이미지에서 `tools/ros_ws.sh ci`(colcon build, `colcon test --return-code-on-test-failure`, 테스트 수 0 초과 단정, clang-tidy)를 돌리고 ament linter는 colcon test 안에서 돈다. clang-format은 `lint` job에 두고, lint에서 clang-tidy와 ament-lint 항목은 지운다(가짜 PASS 항목을 두지 않는다). ros-ws 이미지에 apt `clang-tidy-18`, `clang-format-18`, `versions.env`에 `LLVM_MAJOR=18`과 `LINT_CLANG_FORMAT_VERSION=18.1.3`. unit의 트리거와 concurrency는 lint와 같게 둔다.
  - (w) 골든 경로(쟁점 9). CMake가 `BUILD_TESTING`일 때만 `docker/versions.env`에서 `PX4_TAG`와 `PX4_MSGS_REF`를 읽어 테스트 ENV(`IDSIM_PX4_FIXTURE_DIR`, `IDSIM_PX4_MSGS_REF`)로 넘긴다. 줄이 없거나 둘 이상이거나 디렉터리가 없으면 configure 실패, 테스트도 다시 단정한다. `env.txt`, `versions.env`, 이미지 ENV `IDSIM_BUILD_PX4_MSGS_REF` 셋의 일치를 단정한다. 골든 경로 규칙이 Python(`tests/support/golden.py`)과 CMake 두 곳에 있다는 접점은 `file-ownership.md`에 적었다.
  - (x) 구현에서 ros2-engineer가 정한 것(decisions.md 대비 판단, architect 확인). 1) 기술자 목록은 `detail/px4_topic_list.inc` 하나를 두 번 include한다(기술자 정의와 전체 타입 목록). 2) Out 기술자도 `Publish::Restricted`로 둔다(매크로의 static_assert가 강제. /fmu/out은 구독만). 3) in과 out 양쪽에 있는 `mode_completed`의 기술자 이름은 `ModeCompletedIn`, `ModeCompletedOut`. 4) `Px4Timestamp`는 0보다 큰 값이 아니라 1 us 미만(1000 ns 미만)을 거부한다. us로 바꾸면 0이 되는 값을 막기 위해서다. 5) `package.xml`은 xml-model 줄을 뺐고(unit job은 네트워크가 없어 xmllint가 스키마를 받지 못한다) license는 TODO다(라이선스는 사용자 결정 대기). 6) 헤더 가드는 ROS 관례(`IDSIM_COMMON__X_HPP_`)를 유지하고 clang-tidy `bugprone-reserved-identifier`의 `AllowedIdentifiers`로 예외를 둔다. 7) `tools/ci/lint.sh`의 새 검사 이름은 `px4-api`다.
- 2026-11-10: 사용자 결정, `docs/smoke-test-phase1a.md`를 `docs/smoke-test.md`로 이름을 바꾼다. 이 문서는 1a 전용이 아니라 이미지, PX4 파라미터, PX4 태그가 바뀔 때마다 돌리는 회귀 검사의 설계이고 골든 형식의 기준 문서이므로 다른 문서처럼 주제 이름을 붙인다. 문서와 주석의 경로 참조를 함께 고쳤다. 이 파일과 `opinion-*.md`의 과거 기록 문장은 당시 이름 그대로 둔다. `docker/Dockerfile.px4` 주석은 고치지 않았다(미해결 사항 참조).
- 2026-11-10: 사용자 결정, 저장소 라이선스는 Apache-2.0. 이유: ROS 2 생태계 관례(ament_copyright 기본), 특허 조항, PX4(BSD-3-Clause)와 Gazebo(Apache-2.0) 의존과 호환. 루트 `LICENSE`, `idsim_common` `package.xml`의 license와 maintainer(Daniel Hongwoo Lee, GitHub noreply 주소), 소스와 CMake 파일의 머리말(`Copyright 2026 Daniel Hongwoo Lee`)을 넣고 `ament_copyright`와 cpplint `legal/copyright` 검사를 켰다. 기존 `.sh`, `.py`의 머리말은 범위 밖이다. (x)의 5) license TODO는 이것으로 닫힌다.
- 2026-11-10: 사용자 결정, ros-ws 이미지 크기(clang 도구로 약 410MB 증가, 1.99GB)는 그대로 둔다. clang-tidy를 별도 도구 이미지로 빼지 않는다.
- 2026-11-10: 사용자 결정, `tools/qgc.sh`에 `--restore` 옵션을 두지 않는다. 바꾼 `udpListenPort`는 되돌리지 않고, 기본 포트로 돌리려면 `--stack 0`을 쓴다는 안내만 둔다.
- 2026-11-10: 1a 4번 작업의 PX4 인터페이스 검토 완료. 16개 항목(공개 /fmu/in 허용 3개와 차단 35개의 분류, VehicleCommand 빌더 필드 표와 `CommandSource` 범위와 `is_ack_for`, `Px4Timestamp`의 0과 1 us 미만 거부) 모두 승인, 수정 요구 없음. 근거는 PX4 원문(Commander.cpp, dds_topics.yaml, ucdr_msg.h.em, uxrce_dds_client.cpp)과 `opinion-px4.md` 실측이다. 원문 사본이 v1.17.0 태그인지는 직접 확인하지 않았다(인용 행 번호와 골든 토픽 목록 일치가 간접 근거). 6단계 실측으로 남는 것: NAV_LAND의 공중 착륙 동작과 param 사용, `vehicle_command.hpp`의 "`from_external=false`면 MAVLink로 재송출" 주석의 소스 근거, sim 시간 timestamp 경로의 failsafe 회귀 판정.
- 2026-11-10: 1a 5번 작업 `idsim_interfaces` 사용자 결정 2건(둘 다 권고안). 1) 계약 고정 시점을 나눈다. 1a 완료 시 공통 규칙, `ExecuteMission`, TAKEOFF/LOITER/LAND. 1b 완료 시 `TargetState`, GOTO/TRACK/RTL. Phase 2 완료 시 `VehicleState`. 2) 6단계 이륙-호버-착륙 노드는 `ExecuteMission` action server로 미션 [TAKEOFF, LOITER, LAND]를 받는다. 그래서 취소 시 Hold 동작 실험을 6단계로 당기고 1a 고정 전에 결과를 반영한다. 근거와 확정 계약은 `docs-for-agent/plan-1a-5-idsim-interfaces/decisions.md`.
- 2026-11-10: 1a 5번 작업 ros2-engineer 실측 2건(Jazzy, rclcpp_action, rosbag2 0.26.11). 1) `ACCEPT_AND_EXECUTE`로 받은 뒤 사유를 실어 abort하는 방식은 동작한다(BUSY와 VEHICLE_ID_MISMATCH 사유 전달, 실행 중인 첫 goal 무영향, cancel과 abort 혼합 5가지 정상). `ACCEPT_AND_DEFER` 뒤 abort는 예외를 던지므로 Executor는 `ACCEPT_AND_EXECUTE`만 쓴다. 2) rosbag2는 action goal과 result를 기록하지 않는다(`--include-hidden-topics`로 feedback과 status만). Jazzy action에는 introspection이 없다. 그래서 기록물 인덱스용으로 일반 토픽 `MissionEvent.msg`를 둔다.

## 미해결 사항

사용자 결정이 필요한 항목.

- (2026-11-10) PR #14(apt security 미러 분리) 처리. devops-engineer 분석: PR 자신의 build 실패(run 42770470337, sim-base apt install)는 `security.ubuntu.com`의 91.189.91.82가 noble-security 신규 패키지(perl-base 5.38.2-3.2ubuntu0.7 등)에 404를 준 것이라, "security를 archive 미러로 바꾼 탓"이라는 PR 가설이 반증됐다. Canonical 노드 풀 일부의 동기화 시차이고 DNS가 주는 노드에 따라 성패가 갈린다(같은 코드의 앞선 run 42767888913은 통과). 권고: #14 close, 필요하면 미러 RUN 단계 테스트만 작은 PR로. CI 안정성 대안 (a) apt 단계 재시도(가장 쌈, 확률적), (b) CI에서 archive와 security 모두 `azure.archive.ubuntu.com`(noble-security 반영 시차는 미검증). 사용자 결정 대기.

- 없음(2026-11-10 기준).

아직 열린 항목.

- `docker/Dockerfile.px4` 132행 주석에 옛 문서 이름 `smoke-test-phase1a.md`가 남아 있다(2026-11-10). 이미지 key가 Dockerfile 바이트 해시라 주석만 고쳐도 px4 이미지가 다시 빌드되므로, 다음에 그 파일을 바꿀 때 `smoke-test.md`로 함께 고친다(px4-engineer).
- 비결정 빌드 요소: PX4-OpticalFlow master(px4 builder, 결과물은 버려짐), empy 외 pip 패키지 미고정, ros.key와 gazebo.gpg URL 미고정. 2단계 CI 캐시 키를 정할 때 처리.
- 이미지 ENV와 `versions.env` 대조가 S0에서만 일어난다. S1-S5를 단독 실행하면 대조가 없다.
- `GZ_IP=127.0.0.1`을 빼면 gz-transport 디스커버리가 불안정한지(추측). 지금은 명시하고 가며 제거 비교는 하지 않았다.
- `artifacts/`를 CI 잡 아티팩트로 업로드(가정, CI 골격에서 확인).
- Phase 3 주기 하한 계약이 필요한 토픽 목록(px4-engineer, Phase 3 전에).
- `COM_RC_IN_MODE`=4라 QGC 수동 모드와 가상 조이스틱은 쓸 수 없다. ARM, TAKEOFF(2.5m, `MIS_TAKEOFF_ALT` 기본), LAND, 자동 disarm은 pymavlink로 확인. `docs/interface.md`의 SITL 파라미터 절에 적을 것(ros2-engineer 초안, px4-engineer 확인).
- Lichtblick 2.5.2 공식 이미지의 브라우저 실접속은 미확인. 두 서브프로토콜(foxglove.websocket.v1, foxglove.sdk.v1)을 제시하는 것만 확인했고 foxglove_bridge 3.6.0과의 실제 접속은 1a 6단계에서 확인한다.
- apt 미러 고정 리스크(2026-11-09 실측). 2026-11-10에 `UBUNTU_APT_MIRROR` 빌드 인자(kr 기본, CI는 기본 미러)로 완화했다. 남은 것: 지정 미러가 막히면 콜드 빌드가 실패한다는 점, apt `Acquire::Retries` 미적용, GHCR 공개 이미지를 받아 태그하는 `build_images.py --mode pull` 미구현.
- `qgc.sh`의 sha256 불일치 시 종료 코드 1 경로는 코드만 있고 실행으로 확인하지 않았다(손상 캐시 재다운로드 경로는 같은 함수를 쓰며 확인됨).
- Gazebo GUI 깜빡임(사용자 관측 2026-11-09, VMware 3D 가속 켠 상태). `QSG_RENDER_LOOP=basic`과 `vblank_mode=1`은 효과 미확인. 3D 가속을 끈 소프트웨어 렌더링(llvmpipe, GUI 컨테이너 CPU 약 2.7코어)에서는 깜빡임 여부를 사용자가 다시 본다. 다음 후보: SceneBroadcaster `state_hertz` 낮추기, `--render-engine-gui ogre`.
- (2026-11-10, 1a 4번 작업에서 올라온 항목)
- 6단계로 넘김(PX4 인터페이스 검토에서 나옴): (1) source 값 표에 "source가 (대상 기체 sysid, component 1)이면 안 된다"를 넣는다. PX4 내부 명령의 ack와 `is_ack_for`가 섞일 수 있고 `CommandSource`는 이 조합을 막지 않는다. (2) `offboard_control_mode`는 Allowed지만 메시지 안의 attitude, body_rate, direct_actuator 플래그는 열려 있으니 setpoint 헬퍼가 position만 참으로 고정한다. (3) `/clock` 전달 지연만큼 /fmu/in timestamp가 묵게 보이므로 failsafe 판정 여유를 `COM_OF_LOSS_T` 대비로 테스트에서 확인한다. (4) 시동 상태에서 신호 없는 Offboard 요청의 TEMPORARILY_REJECTED 여부 실측.
- 완료: `UXRCE_DDS_SYNCT=0`에서 스모크 S2-S5 통과. 사용자가 이 호스트에서 직접 실행했다. 스택 6, run id는 20261110-093814-k6-s2, 20261110-093949-k6-s3, 20261110-094205-k6-s4, 20261110-095000-k6-s5. S2의 pxh 판정에서 `UXRCE_DDS_SYNCT` 저장값은 0이고, vehicle_status timestamp가 약 46 s로 sim 시간 축이다.
- 완료: 생성기 골든 `tests/fixtures/gen_compose/` 갱신. stack.json 4개에서 기대 파라미터에 `UXRCE_DDS_SYNCT`가 추가되고 sitl_params.env sha256이 바뀐 것뿐이며 compose.yaml은 그대로다.
- reviewer PR 전 검토 결과(2026-11-10). 결함 주입 실험에서 음성 컴파일 4건, 골든 양방향 일치, 3곳 일치 테스트가 실제로 실패를 잡았다. 머지 차단 3건(테스트의 버전 리터럴, architecture.md ros-ws 설명, 음차)은 모두 반영했다. 권고 중 반영한 것: px4-api 패턴 확대, unit.yml key 계산 실패 검사, ros_ws.sh errexit 주석, 묵은 test_results로 테스트 수가 집계되던 문제 수정(사실로 확인됨. `do_test`가 colcon test 전에 결과를 지운다), 테스트 2곳 정리.
- PX4 timestamp와 `/clock`이 같은 축이라는 주장은 1회 실측과 구조 논증만 있고 회귀 판정은 6단계 failsafe 테스트까지 없다. S5에 `vehicle_status.timestamp`와 `/clock`의 차이 상한 판정을 넣을지 px4-engineer와 test-engineer가 검토한다.
- px4-api 검사는 C++과 `.py`만 본다. 6단계에서 params, remap yaml이 생기면 범위를 다시 본다.
- 이 PR이 손대지 않은 `.github/workflows/build.yml`, `build-images.yml`, `tools/ci/image_keys.py`, `tools/ci/build_images.py`에 음차("키", "잡")가 남아 있다. 다음에 고칠 때 바꾼다.
- px4-engineer가 이 프로젝트 작업에서 안전장치 오류로 반복 중단된다(이번 3회, 설계 토론 때 architect와 reviewer 포함 3회). PX4 인터페이스 작업의 운용 방법이 필요하다. 사용자가 오탐으로 신고하기로 했다(Request ID req_011CgtyuPphfbHiy5z6LYHwa, req_011Cgu1vZ83zmpEFgTFRgHSX, req_011Cgu4CY2zeGbKJuHzw7Gf4). 6단계 전에 결과를 보고 운용 방법을 다시 정한다.
- clang-tidy가 `px4_topics.hpp`, `px4_io.hpp`를 보지 않는다. tidy 대상은 `src/`의 소스이고 헤더는 소스가 include할 때만 검사되는데 `src/`가 이 두 헤더를 include하지 않기 때문이다. 헤더 전용 검사를 둘지, `test/`를 tidy 대상에 넣을지 정해야 한다(ros2-engineer와 devops-engineer).
- `tools/ros_ws.sh tidy`는 대상이 0개이면 PASS-NO-TARGETS로 통과한다. 디렉터리 구조가 바뀌면 검사가 조용히 빠질 수 있으니 `ci`에서는 경고나 실패로 바꿀지 검토한다(test-engineer 제안, devops-engineer).
- unit job은 GHCR에 새 ros-ws key(a0f1847b30f3b76f)가 없으면 load 모드로 ros-base부터 다시 빌드한다. main 머지 뒤 build job이 이미지를 올리면 해소된다.
- ros-ws 이미지가 계획 예상(297MB)보다 많은 약 410MB 늘었다. 줄여야 하면 clang-tidy를 별도 도구 이미지로 빼는 안이 있다(사용자 알림 항목).
- unit job의 첫 실행과 머지 뒤 3회의 단계별 시간 기록(devops-engineer, CI 실행 뒤).
- (2026-11-10, 3단계 C에서 올라온 항목)
- 다대 원점 판정의 pose 보정 방식(`check_px4 --expect-pose-enu` 또는 stack.json 기체별 기대 위경도). 지금 `--expect-origin`은 1대 기준이다. architect와 test-engineer, 1b에서.
- GPS 잡음 출처 미확인(PX4 gz_bridge 추정).
- ULog가 `compose down`에서 정상 종료되는지 미확인. `SDLOG` 기록량은 약 285 KiB/s, 기체당 약 1 GB/h. logging-engineer가 Phase 2 전에 확인.
- bridge healthcheck에 `ROS_LOG_DIR=/tmp/hc`를 적용한 뒤 run 디렉터리에 로그 파일이 안 생기는지 미확인.
- 에이전트의 Fast DDS 멀티캐스트가 0.0.0.0에 bind되어 같은 LAN의 다른 호스트와 디스커버리가 섞일 가능성(추정, 미실측).
- `gen_compose.sh`의 `--run-id` 인자 제거 검토(다음 PR, 결정 기록 (l)).
- 1b 제약: bridge healthcheck는 `/clock` 1회 수신을 유지하고 표적 어댑터 판정은 별도 단계로 둔다. 커스텀 모델은 `GZ_SIM_RESOURCE_PATH`에 `/opt/idsim/sim/models` 추가가 필요하다.
- `ros_ws/src/idsim_sim/scripts/gz_server.sh` 머리 주석의 "문자열 그대로 넘긴다" 표현이 부정확하다(sim-engineer 다음 작업).
- uid 1001(passwd에 없음) 재실측은 C 구현 뒤 하지 않았다.
- 호스트 포트 5900, 8090은 다른 프로젝트의 novnc-server가 쓰므로 VNC를 도입하면 피한다.
- MAVLink bind에 실패한 PX4 인스턴스의 동작(GCS 링크 없이 계속 뜨는지, uXRCE 영향)은 미실측. 3단계 이후에는 오프셋으로 충돌 자체가 없어야 하므로 check_px4_log의 `bind failed` 판정이 회귀를 잡는다.
- lockstep 반대 방향(PX4가 느릴 때 Gazebo가 기다리는지)은 미실측. Phase 3 CPU 포화 해석의 전제.
- compose healthcheck `start_interval`의 Docker 하한은 미실측(Docker 29.1.3, Compose 2.40.3에서 수용). `check_host.sh`에 넣을 값은 devops-engineer가 정한다.
- 1b 전 결정: 기체별 EKF 원점은 월드 원점이 아니라 스폰 지점이라 월드 ENU `TargetState`를 기체 NED setpoint로 바꾸려면 스폰 pose 또는 `VehicleLocalPosition`의 ref_lat/lon/alt가 필요하다(px4, sim, ros2 제기). 1b 커스텀 월드에서 `world.origin`과 SDF `<spherical_coordinates>` 일치 검사 주체도 1b 착수 때 정한다. 월드 SDF에 `<plugin>`이 하나라도 있으면 서버 설정 파일이 무시된다(sim).

2026-11-10 1a 4번 작업으로 닫힌 항목.

- `frame_transforms`의 v1.17.0 호환(2026-11-06 결정의 가정, 4단계 착수 때 확인하기로 한 항목): 라이브러리는 px4_msgs에 의존하지 않아 태그 호환은 문제가 아니었고, 변환 자체의 결함 때문에 직접 구현으로 결정했다(결정 기록 (q)). px4_ros_com은 단위 테스트의 비교 기준으로 남는다.
- lint의 clang-format, clang-tidy, ament-lint 미연결(FAIL-NOT-WIRED): clang-format은 lint에 연결, clang-tidy와 ament linter는 unit job으로 옮겼다(결정 기록 (v)).

2026-11-09 3단계 설계 토론과 reviewer 실측으로 닫힌 항목.

- 스택 둘의 GCS/MAVLink 포트 충돌: idsim용 `px4-rc.mavlink`로 스택 오프셋 1000k 적용(충돌 실측, PATH 대체는 px4-engineer의 1회 실험, 오프셋 적용 효과는 3단계 A에서 확인). QGC 하나는 한 번에 한 스택만 본다는 제약은 `docs/interface.md`에 적는다.
- gz-gui 편집 플러그인 제거 여부: 3단계에서는 빼지 않는다(결정 기록 (f)).
- px4 healthcheck에 `gz_bridge status`를 쓰는 안: 연결 상태를 반영하지 않아 기각(결정 기록 (j)).
- passwd에 없는 uid의 컨테이너 실행: 동작 확인, `getpass`와 `pwd` 호출 금지 규칙으로 대체.
- 에이전트 `/proc/net/udp` healthcheck 오탐: bind 실패 시 종료 코드 0이지만 unhealthy로 잡힘, 오탐 없음.

2026-11-06 실측으로 닫힌 항목.

- `OffboardControlMode`에 `MESSAGE_VERSION` 상수 없음(ros-ws 이미지 `ros2 interface show`, 상수 0개). `VehicleStatus`는 1. versioned 34개 중 9개가 1, 25개가 0(`TrajectorySetpoint`, `VehicleCommand`, `VehicleCommandAck`는 0). `ArmingCheckReply.msg`만 등호 앞 공백 두 칸.
- px4_msgs `PX4_MSGS_REF`(86d8239e)와 PX4 v1.17.0 msg 235개 diff 0.
- PX4 `gz_bridge/server.config`와 PX4-gazebo-models `server.config` 동일. 그 파일의 PX4 전용 플러그인 두 줄은 sim-base에서 로드 실패하지만 서버는 정상(위 결정 기록).
- `gz sim -s` 헤드리스 서버 기동, `scene/info` 서비스, `/clock` 토픽 확인(sim-base 단독).
- `HEADLESS`, `PX4_GZ_SIM_RENDER_ENGINE`은 rcS 전용(소스 확인). ogre 1.x는 X 없이 불가.
- SITL 파라미터 값 확정: `COM_OBL_RC_ACT` 4, `COM_OF_LOSS_T` 1.0, `NAV_DLL_ACT` 0, `COM_RC_IN_MODE` 4, `COM_DISARM_PRFLT` -1, `SDLOG_MODE` 2. 근거 주석은 `config/px4/sitl_params.env`.
- 이미지 크기: ros-base 838MB, xrce-agent 153MB, sim-base 2.97GB, ros-ws 1.57GB, px4 3.06GB.
- 스모크 S0-S5 전체 통과로 닫힌 것:
  - uxrce status 연결 문자열은 `Running, connected`(끊기면 `Running, disconnected`).
  - `/proc/net/udp`에서 에이전트 포트 행이 보여 healthcheck가 동작한다.
  - 서브모듈 얕은 클론으로 PX4 빌드가 끝나고 `ver all`이 `Release 1.17.0`.
  - ros-ws의 저장소 마운트 `/opt/idsim`이 동작한다.
  - `COM_RC_IN_MODE=4`에서 `commander check`가 `Preflight check: OK`. `COM_OBL_RC_ACT`, `COM_RC_IN_MODE` 저장값 모두 4.
  - 토픽 이름: 접미사는 `_v1` 하나뿐이고 골든 65개 중 8개에 붙는다(arming_check_reply, arming_check_request, vehicle_attitude_setpoint, airspeed_validated, battery_status, home_position, vehicle_local_position, vehicle_status). `trajectory_setpoint`, `vehicle_command`, `vehicle_command_ack`는 접미사 없음.
  - `vehicle_status_v1` 발행자 QoS: BEST_EFFORT, TRANSIENT_LOCAL, KEEP_LAST, depth 1.
  - OSRF gz-transport 13.6.0(sim-base, px4)과 ROS vendor gz-transport13 13.6.0(ros-ws)의 와이어 호환. bridge로 `/clock` 수신 확인(S5).
  - 시동과 시동 해제 왕복(S3): ack result 0, ARMED와 DISARMED 각각 3회 연속 유지.

그 밖의 항목.

- Phase 1a 완료 기준의 `docs/interface.md`는 아직 없다. 스모크 S4 결과를 `tools/to_interface.py`로 정리한 초안을 ros2-engineer가 낸다.

## 갱신 규칙

- 작업 단위가 끝날 때마다 "현재 상태"와 "Phase별 진행"을 갱신하고, 설계에 영향을 주는 결정은 "결정 기록"에 날짜와 함께 추가한다.
- 설계나 계획 자체가 바뀌면 `docs/`를 고치고, 여기에는 바뀌었다는 사실과 날짜만 남긴다.
