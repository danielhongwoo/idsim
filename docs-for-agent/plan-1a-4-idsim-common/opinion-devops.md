> 이 파일은 2026-11-10 설계 토론의 원문이다. 본문의 `/tmp/...scratchpad...` 경로와 `re/`, `ws/`, `exp/` 같은 실험 경로는 당시 작업 환경의 임시 파일이라 저장소에 없다. 실험 결과는 본문에 인용된 내용이 전부다.

# 1a 4단계 idsim_common: CI와 빌드 설계 의견 (devops-engineer)

작성 2026-11-10, 브랜치 feat/1a-4-idsim-common(5fd11a6). 저장소 파일은 고치지 않았다.
실험은 scratchpad의 모형 저장소(`.../scratchpad/step4/exp/repo`, 저장소 구조를 흉내 낸 디렉터리)를
`idsim/ros-ws:local`의 /opt/idsim에 마운트해 돌렸다. 모형 패키지 `demo_common`은 rclcpp, px4_msgs,
px4_ros_com에 의존하고 `px4_ros_com/frame_transforms.h`를 include하며 gtest 하나를 둔다.

## 실험 요약 (근거로 아래에서 인용)

| 번호 | 내용 | 결과 |
| --- | --- | --- |
| E1 | ros-ws 이미지 도구 확인 | clang-format, clang-tidy, ccache 없음. uncrustify, cppcheck 있음. ament_cmake_gtest/gmock, ament_lint_auto, ament_lint_common(copyright, cppcheck, cpplint, flake8, lint_cmake, pep257, uncrustify, xmllint) 있음. ament_cmake_clang_format/clang_tidy 없음 |
| E2 | `--user $(id -u):$(id -g) -e HOME=/tmp/h -e CYCLONEDDS_URI= --network none`로 `colcon build` | 13.1초(16 vCPU 호스트, 패키지 1개, RelWithDebInfo). build/install/log 모두 uid 1000 소유, 호스트 uid가 아닌 파일 0개. build 32MB, install 1.6MB |
| E3 | frame_transforms include와 px4_msgs `MESSAGE_VERSION` 사용 | 컴파일 성공(호환의 첫 신호일 뿐, 의미 검증은 ros2-engineer의 단위 테스트) |
| E4 | `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` | colcon-cmake가 `ros_ws/build/compile_commands.json`으로 합쳐 준다. 경로는 컨테이너 경로 `/opt/idsim/...` |
| E5 | `ament_add_gtest(... ENV IDSIM_PX4_GOLDEN_DIR=...)` | CTest 명령에 `--env IDSIM_PX4_GOLDEN_DIR=/opt/idsim/tests/fixtures/px4/v1.17.0`이 들어가고 테스트가 topics.txt 65줄을 읽음 |
| E6 | 골든 디렉터리를 치운 뒤 `colcon test` | **`colcon test` 종료 코드 0**, `colcon test-result` 종료 코드 1(1 failure) |
| E7 | package.xml 오류로 빌드 실패시킨 뒤 `colcon test`, `colcon test-result --verbose` | **`test-result`가 "0 tests" 종료 코드 0**. 빌드 실패를 test-result만으로는 못 잡는다 |
| E8 | `colcon test --return-code-on-test-failure` | 실패 시 종료 코드 1 |
| E9 | `ament_lint_auto_find_test_dependencies()` + ament_lint_common 기본 묶음 | 1.4초. copyright 3, cpplint 4, uncrustify 3건 실패(모형 코드 기준). uncrustify는 clang-format과 규칙이 겹친다 |
| E10 | lint용 python 이미지(`LINT_PYTHON_IMAGE`)에 `pip install clang-format==18.1.3` | 설치되고 `clang-format version 18.1.3`. PyPI에 clang-tidy 18.1.8 wheel(35MB)도 있음 |
| E11 | ros-ws 안 apt 후보(kr 미러로 조회) | clang-format/clang-tidy 1:18.0 메타 -> clang-format-18, clang-tidy-18 1:18.1.3-1ubuntu1, ccache 4.9.1, ros-jazzy-ament-cmake-clang-format/tidy 0.17.5 |
| E12 | ros-ws에 apt clang-tidy, clang-format 설치(일회용 컨테이너, kr 미러) 뒤 compile_commands로 clang-tidy 실행 | 루트 파일시스템 +297MB(ros-ws 1.57GB -> 약 1.87GB). `Ubuntu clang-format version 18.1.3 (1ubuntu1)`. 소스 파일 1개 tidy 8.7초(bugprone, modernize, performance), 비사용자 코드 경고 63151건이 억제됨. 즉 헤더 필터를 저장소 경로로 한정하는 것이 필수 |

ros-ws 이미지에는 pip가 없다(`python3 -m pip` 없음). 이 호스트는 archive.ubuntu.com 타임아웃이 계속되어 apt 실험은 kr 미러로 바꾼 일회용 컨테이너에서만 했다.

## D1 colcon 빌드 위치

결론
- 개발과 CI 모두 ros-ws 컨테이너 안, 저장소 마운트 `/opt/idsim/ros_ws`에서 빌드한다. 산출물은 저장소의 `ros_ws/{build,install,log}`. 호스트에서 직접 colcon을 돌리지 않는다(install의 setup 스크립트와 CMake 경로가 `/opt/idsim/...` 절대 경로라 호스트에서 쓸모가 없고, 호스트에 ROS가 없는 것이 전제다).
- 컨테이너 사용자: `--user <호스트 uid>:<호스트 gid>`, `HOME=/tmp/idsim-home`(passwd에 없는 uid여도 됨, 결정 기록 (i)), `CYCLONEDDS_URI=` 비움, `--network none`. 빌드와 단위 테스트에 네트워크가 필요 없고, 단위 테스트가 rclcpp 노드를 만들 때 같은 호스트의 개발 스택(도메인 20 + k)과 섞이지 않게 하는 가장 확실한 격리다. 추가로 `ROS_DOMAIN_ID`는 스택 범위(20-29) 밖 값으로 준다(제안: 0이 아니라 99. --network none이면 사실상 무의미하지만 사람이 옵션을 빼고 돌릴 때를 위한 이중 잠금. 추정 수준의 방어).
- `.gitignore`: 이미 `ros_ws/build/`, `ros_ws/install/`, `ros_ws/log/`가 있다. 추가할 것 없음. lint의 대상 목록은 `git ls-files -co --exclude-standard`라 산출물은 lint 대상에 안 들어간다(lint.sh 44-49행).
- 스택의 source: 지금 `ros-ws-entrypoint.sh`가 `/opt/idsim/ros_ws/install/setup.bash`가 있으면 읽는다. bridge, runner, 이후 노드 서비스 모두 같은 이미지와 같은 저장소 마운트(gen_compose.py `ros_ws_service`)를 쓰므로 entrypoint를 바꿀 필요가 없다. 다만 두 가지를 보강한다.
  1. 오래된 install 문제: 브랜치를 바꾸거나 패키지를 지우면 install에 남은 것이 그대로 source된다. 빌드 진입점(D4)에 `clean`을 두고, 이 단계에서는 개발자 책임으로 둔다.
  2. 6단계부터 노드 서비스가 overlay를 필요로 하면 `stack.sh up`이 `ros_ws/install/setup.bash` 부재를 시작 전에 오류로 보고한다(자동 빌드는 하지 않는다: up은 스택 조작만, 빌드 실패와 스택 실패를 구분하기 위해). 4단계에서는 bridge가 이미지의 ros_gz_bridge만 쓰므로 검사가 필요 없다.
  3. 스택이 떠 있는 동안 다시 빌드하면 install의 .so가 실행 중에 바뀐다. 실행 중 프로세스가 깨질 수 있다(추정, 실측 안 함). 진입점이 `docker compose ls`로 `idsim-*` 프로젝트가 있으면 경고만 한다.
- 이미지에 굽지 않는 이유
  1. ros-ws 이미지 키는 Dockerfile과 versions.env 줄로 정해진다. 소스를 COPY하면 소스 커밋마다 키가 바뀌어 ros-ws 재빌드(CI 콜드 444초)와 GHCR 푸시가 PR마다 생긴다. 무료 러너 한도와 레지스트리 용량에 맞지 않는다.
  2. 아키텍처 결정이 이미 "프로젝트 소스는 /opt/idsim에 마운트"이고, compose의 bridge와 runner가 같은 마운트를 쓴다. 빌드도 같은 경로에서 해야 install의 절대 경로가 맞는다.
  3. 4단계 빌드는 13초 수준(E2)이라 굽는 이득이 없다.
- 나중에 굽는 시점: 저장소 없이 이미지만으로 노드를 띄워야 할 때. 후보는 (1) Phase 2 replay 프로필을 다른 PC나 CI에서 저장소 마운트 없이 돌리고 싶을 때, (2) 확장 방향 (3)의 "compose pull로 노드 이미지 업데이트". 그때는 ros-ws를 바꾸지 않고 별도 타깃(가칭 `ros-app`, ros-ws 위에 `COPY ros_ws/src`, `-DBUILD_TESTING=OFF`, 키에 소스 해시 포함)을 둔다. 판단 기준은 "colcon build가 unit 잡에서 3분을 넘거나, 저장소 없는 실행 요구가 생길 때"이며 지금 결정하지 않는다. `Dockerfile.ros-ws` 37-38행의 주석 자리는 이 방향으로 문구를 고친다(이 PR에서 devops가).

## D2 unit 잡

결론: 이 PR에서 만든다. 이유는 (1) FAIL-NOT-WIRED를 풀려면 clang-tidy와 ament-lint가 돌 곳이 필요하고(D3), (2) 로드맵 4단계 완료 조건인 GoogleTest가 CI에서 돌아야 이후 "모든 항목은 PR로" 규칙이 의미가 있으며, (3) 패키지가 하나일 때 잡을 만드는 것이 가장 싸다.

구성(새 워크플로 `.github/workflows/unit.yml`, 제안)
- 트리거: `push`, `pull_request`. architecture.md 테스트 표의 "모든 push"를 따른다. lint와 같은 이중 실행(같은 저장소 PR 브랜치에서 push와 pull_request 둘 다) 문제가 있으므로, 이미 미해결로 잡혀 있는 lint 이중 실행 정리와 같은 방식(예: push는 main만, 나머지는 pull_request)으로 함께 고친다. concurrency는 lint와 같은 꼴, PR에서 cancel-in-progress.
- 권한: `contents: read`, `packages: read`.
- 단계
  1. checkout(persist-credentials: false).
  2. 이미지 확보: `tools/ci/image_keys.py --format env`로 ros-ws 키를 얻고 `ghcr.io/.../ros-ws:<키>`를 pull. 없으면(이 PR처럼 Dockerfile.ros-ws를 바꾸는 PR, 또는 GHCR 패키지가 아직 비공개라 포크 PR이 못 받는 경우) `tools/ci/build_images.py --mode load ros-ws`로 러너에서 빌드한다(ros-base는 레지스트리에 키가 있으면 그대로 씀). 이 분기는 build 잡과 같은 ros-ws를 한 번 더 빌드하는 비용이 있지만 Dockerfile을 바꾸는 PR에서만 생긴다. build 잡의 산출물을 넘겨받는 방식(artifact로 tar 전달)은 1.5GB라 득이 없다고 본다(추정).
  3. `tools/ros_ws.sh ci`(D4) 한 줄: build -> test -> test-result -> clang-tidy. 컨테이너 옵션은 D1과 같고 uid는 러너의 `id -u`(1001).
  4. 실패 시 `ros_ws/log/`와 `ros_ws/build/*/test_results/`를 아티팩트로 올린다(보존 7일).
- 종료 코드 처리(실험 근거 E6, E7, E8): `colcon build`는 `set -e`로 끊고, `colcon test --return-code-on-test-failure`, 그다음 `colcon test-result --verbose`를 출력용으로 돌린다. 여기에 "결과 파일의 테스트 수 > 0"을 단정한다. test-result는 빌드가 실패해도 0 tests로 종료 코드 0을 주기 때문이다. 패키지가 하나도 안 잡히는 경우(package.xml 오류, COLCON_IGNORE 실수)도 이 단정이 잡는다. 기대 패키지 목록(`colcon list -n`)을 출력해 로그에 남긴다.
- 빌드 옵션: `--cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`, `--event-handlers console_cohesion+`(패키지별로 묶여 CI 로그를 읽기 쉽다), `--parallel-workers 4`(무료 러너 4 vCPU). 경고를 오류로 바꾸는 것(`-Werror`)은 패키지 CMakeLists의 컴파일 옵션으로 ros2-engineer가 정한다. CI 전용 플래그로 넣지 않는다(로컬과 결과가 달라지지 않게).
- 캐시: 지금은 넣지 않는다. ccache는 이미지에 없고(E1), 패키지 1개 빌드가 13초(16 vCPU, E2)라 4 vCPU 러너에서도 1분 안쪽일 것으로 본다(추정, 4배 보정). 다시 볼 조건: unit 잡 build 단계가 3분을 넘을 때. 그때는 ccache를 ros-ws에 넣고 `actions/cache`로 `~/.ccache`를 키(ros-ws 키 + 브랜치)로 저장한다. ccache 버전은 versions.env에 둔다.
- 시간: 추정 대신 실측 계획. 단계마다 `date +%s`를 찍어 GITHUB_STEP_SUMMARY에 `pull`, `image build(있으면)`, `colcon build`, `colcon test`, `clang-tidy` 초를 표로 남긴다. 이 PR의 첫 실행(이미지 재빌드 포함)과 머지 뒤 첫 3회(이미지 pull만)를 모아 progress.md에 기록하고, architecture.md의 단위 층 목표 "1분 이내"를 colcon test 단계에 대한 목표로 본다(pull과 빌드는 별도 집계). timeout-minutes는 처음에 30(이미지 빌드 분기 포함), 실측 뒤 줄인다.
- 월 사용 시간: 저장소가 공개라 표준 러너 분은 과금되지 않지만 동시 실행 한도와 대기 시간은 있다. 잡 하나가 PR마다 pull 포함 3-5분이면 lint 매트릭스(12잡)보다 작다(추정).

## D3 lint 연결

결론: clang-format은 lint 잡에 남기고, clang-tidy와 ament-lint는 unit 잡으로 옮긴다. lint.sh에서 두 항목을 빼고(all_checks와 lint.yml 매트릭스에서 제거), 빠진 사실을 lint.yml 머리 주석에 "unit 잡에서 돈다"로 적는다. lint.sh에 "다른 잡에서 통과"로 PASS를 찍는 가짜 항목은 두지 않는다(GitHub UI에서 실제로 돌지 않은 검사가 녹색으로 보이는 것을 피한다). FAIL-NOT-WIRED의 목적(대상이 생기면 연결을 강제)은 unit 잡이 생기는 것으로 채워진다.

clang-format
- 실행 위치: lint 잡, `LINT_PYTHON_IMAGE`에 `pip install clang-format==${LINT_CLANG_FORMAT_VERSION}`(E10에서 18.1.3 설치 확인). yamllint, pytest와 같은 방식이고 ros-ws pull이 필요 없어 수 초 안에 끝난다.
- 명령: `clang-format --dry-run --Werror` (git 추적 파일 + 추적 안 된 비무시 파일, lint.sh의 `list_files` 그대로). 스타일 파일은 저장소 루트 `.clang-format`(ros2-engineer 결정). 루트에 없으면 FAIL로 둔다(clang-format이 조용히 LLVM 기본 스타일을 쓰는 것을 막는다: `--style=file:<저장소>/.clang-format`로 명시).
- 버전 출처: versions.env 한 곳. 제안 키 두 개.
  - `LLVM_MAJOR=18`: ros-ws Dockerfile이 `clang-tidy-${LLVM_MAJOR}`, `clang-format-${LLVM_MAJOR}`를 apt로 설치(개발자가 컨테이너 안에서 같은 major의 clang-format을 쓰게). 이미지 키에 들어간다.
  - `LINT_CLANG_FORMAT_VERSION=18.1.3`: lint 잡의 pip 버전. Ubuntu 24.04 release 포켓의 clang-format-18이 1:18.1.3(E11)이라 lint와 컨테이너가 같은 패치 버전이 된다. 두 값의 major 일치를 lint의 clang-format 검사가 먼저 단정한다.
  - noble-updates에 18.1.x 갱신이 올라오면 ros-ws 재빌드 때 컨테이너 쪽만 바뀔 수 있다. apt 버전을 문자열로 고정하면(`clang-format-18=1:18.1.3-1ubuntu1`) 갱신 시 빌드가 깨지므로 고정하지 않고, 대신 ros-ws에 `IDSIM_BUILD_CLANG_FORMAT`(설치된 `--version`)를 남겨 S0 또는 unit 잡이 대조하게 하는 안을 제시한다(추정: 18.1.3 이후 noble 갱신 가능성은 낮다).
- ament_cmake_clang_format(ament 래퍼)은 쓰지 않는다. 같은 검사가 두 곳에서 다른 버전으로 돌 위험만 생긴다.

clang-tidy
- 실행 위치: unit 잡 안, colcon build 직후. `compile_commands.json`(E4)과 ros-ws의 헤더가 있어야 하므로 ros-ws 이미지 밖에서는 못 돈다.
- 도구: ros-ws에 apt `clang-tidy-${LLVM_MAJOR}`(E11, E12의 크기 실측 참조). pip wheel(E10)도 있으나 ros-ws에 pip가 없고, wheel이 GCC 13 libstdc++ 헤더와 자기 내장 헤더를 맞게 찾는지는 확인하지 못했다. apt를 기본안으로 한다.
- 명령: `run-clang-tidy-18 -p ros_ws/build -j 4 -quiet '<저장소 패키지 경로 정규식>'`. 대상은 우리 패키지의 소스만(`/opt/idsim/ros_ws/src/`), 헤더 필터도 같은 경로로 한정해 px4_msgs 생성 헤더와 rclcpp 경고를 빼고 `--warnings-as-errors='*'`. 검사 목록은 저장소 루트 `.clang-tidy`(ros2-engineer 결정).
- 시간: 파일 하나에 8.7초(E12, 16 vCPU 호스트)가 드는 것은 rclcpp와 px4_msgs 헤더 파싱 때문이며 파일 수에 비례한다(추정). 소스 10개면 4 vCPU 러너에서 -j 4로 30-60초 정도로 본다(추정, 첫 실행에서 실측). 3분을 넘으면 PR에서는 바뀐 파일만 tidy하는 방식으로 바꾼다.
- ros-ws 크기 증가 297MB(E12)는 clang-18 런타임이 대부분이다. clang-format만 넣으면 훨씬 작지만 clang-tidy가 필요하므로 감수한다.
- 테스트 소스(gtest 매크로)를 tidy 대상에 넣을지는 ros2-engineer와 정한다. 넣으면 gtest 매크로 때문에 끄는 규칙이 늘어난다.

ament-lint
- `ament_lint_auto`를 colcon test로 돌리면 unit 잡 안에 들어간다(E9: 1.4초). lint.sh의 ament-lint 항목은 위와 같이 제거한다.
- 기본 묶음 `ament_lint_common`을 그대로 쓰면 uncrustify가 clang-format과 충돌하고(E9), cpplint도 줄 길이와 include 순서에서 clang-format 결과와 어긋날 수 있다(추정). 제안: package.xml에 `ament_lint_common` 대신 필요한 것만 `test_depend`로 적는다. 후보는 `ament_cmake_xmllint`(package.xml), `ament_cmake_lint_cmake`(CMakeLists), `ament_cmake_cppcheck`(clang-tidy와 겹치지만 싸다, 선택), `ament_cmake_copyright`(저작권 머리말 정책을 정해야 함). 최종 선택은 ros2-engineer. devops 조건은 "clang-format과 같은 대상을 다른 규칙으로 보는 린터(uncrustify)를 넣지 않는다" 하나다.
- 이 묶음은 이미지에 이미 있다(E1). 새 apt 설치 없음.

정리하면 이 PR에서 바뀌는 CI 파일(전부 devops 소유)
- `tools/ci/lint.sh`: clang-format 실제 검사로 교체, clang-tidy와 ament-lint 함수와 all_checks 항목 제거.
- `.github/workflows/lint.yml`: 매트릭스에서 clang-tidy, ament-lint 제거, 머리 주석 갱신.
- `.github/workflows/unit.yml`: 새로.
- `docker/Dockerfile.ros-ws`: `clang-tidy-${LLVM_MAJOR}`, `clang-format-${LLVM_MAJOR}` 설치, ARG `LLVM_MAJOR`, 37-38행 주석 정정. ros-ws 키가 바뀌므로 이 PR의 build 잡이 ros-ws를 다시 빌드한다(CI 콜드 기준 444초 + 설치분).
- `docker/versions.env`: `LLVM_MAJOR`, `LINT_CLANG_FORMAT_VERSION`.
- `docker/docker-bake.hcl`: ros-ws 타깃에 `LLVM_MAJOR` 인자.
- `tools/ros_ws.sh`: 새로(D4).
- architecture.md "파이프라인 구성"의 (1) lint 항목에서 clang-tidy, ament_lint를 (3) unit으로 옮기는 문장 수정은 architect 소유라 요청만 한다.

## D4 tools/ 진입점

결론: `tools/stack.sh`에 하위 명령으로 넣지 않고 새 스크립트 `tools/ros_ws.sh`를 둔다. stack.sh는 compose 스택 조작(생성, up, down)이고, 빌드는 스택 없이도 하는 일이라 섞으면 `stack.sh` 인자 해석이 복잡해진다. 이름은 대상 디렉터리 `ros_ws`와 맞춘다.

하위 명령(제안)
- `tools/ros_ws.sh build [colcon 인자...]`: ros-ws 컨테이너(D1 옵션)에서 `colcon build`(기본 cmake 인자 포함). 뒤 인자는 colcon에 그대로(예: `--packages-select idsim_common`).
- `tools/ros_ws.sh test [colcon 인자...]`: build를 먼저 하고 `colcon test --return-code-on-test-failure`, `colcon test-result --verbose`, 테스트 수 > 0 단정.
- `tools/ros_ws.sh tidy`: build 뒤 run-clang-tidy(D3).
- `tools/ros_ws.sh ci`: build -> test -> tidy를 CI와 같은 순서로. unit.yml은 이것만 부른다(lint.sh와 같은 원칙: 로컬과 CI가 같은 진입점).
- `tools/ros_ws.sh clean`: `ros_ws/{build,install,log}` 삭제. 컨테이너로 만든 파일이 호스트 uid 소유라 호스트에서 지울 수 있다(E2). 실행 중 스택이 있으면 경고.
- `tools/ros_ws.sh shell`: 같은 옵션으로 대화형 bash(개발자가 ros2 명령으로 확인할 때). 이때만 `--network none`을 빼는 `--net` 옵션을 둘지는 열어 둔다.
- 공통 옵션: `--image-tag t | --registry r`(gen_compose.sh와 같은 의미, 기본 `idsim/ros-ws:local`). 실행 전 이미지의 `IDSIM_BUILD_*`와 versions.env를 대조해 다르면 중단(S0와 같은 원칙. 오래된 로컬 이미지로 빌드하는 실수 방지).
- 내부 구현은 `docker run --rm --user $(id -u):$(id -g) --network none -e HOME=/tmp/idsim-home -e CYCLONEDDS_URI= -e ROS_DOMAIN_ID=99 -v <저장소>:/opt/idsim -w /opt/idsim/ros_ws <이미지> bash -c ...`. entrypoint가 ROS와 px4 underlay를 source하므로 스크립트가 따로 source하지 않는다. 다만 entrypoint가 기존 `ros_ws/install`도 source하므로, 빌드는 이전 overlay가 섞인 환경에서 돈다(colcon이 경고만 낸다). `ci` 하위 명령은 clean 상태(CI 체크아웃)에서 돌므로 문제없고, 로컬은 경고를 감수한다.

## D5 골든 경로 전달

결론: CMake가 configure 때 저장소 루트와 `docker/versions.env`의 `PX4_TAG`로 골든 디렉터리를 계산하고, `ament_add_gtest(... ENV IDSIM_PX4_GOLDEN_DIR=<경로>)`로 테스트 프로세스에 넘긴다. 테스트는 환경 변수가 없거나 디렉터리가 없으면 실패한다. 둘 다 `if(BUILD_TESTING)` 안에서만.

근거
- E5: ENV 인자가 CTest 명령의 `--env`로 들어가고 로그에 경로가 그대로 찍혀 사후 확인이 쉽다.
- E6: 디렉터리를 치우면 테스트가 실패한다(종료 코드 처리는 D2).
- 컴파일 정의(`target_compile_definitions`)도 동작했지만 경로가 바이너리에 박혀 다시 가리키려면 재컴파일이 필요하다. ENV를 기본으로 한다.
- 태그를 CMake에 문자열로 쓰지 않는다(버전 단일 출처 규칙). Python 쪽 `tests/support/golden.py`의 `golden_dir()`가 이미 versions.env의 PX4_TAG로 `tests/fixtures/px4/<tag>`를 계산하므로 C++도 같은 규칙을 쓴다. CMake 예: `file(STRINGS "${IDSIM_REPO_ROOT}/docker/versions.env" _l REGEX "^PX4_TAG=")`로 읽고, 줄이 없거나 둘 이상이면 FATAL_ERROR.
- 저장소 루트: 기본 `${CMAKE_CURRENT_SOURCE_DIR}/../../..`(ros_ws/src/idsim_common 기준), `-DIDSIM_REPO_ROOT=`로 바꿀 수 있게. 저장소 없이 빌드하는 경우(나중의 이미지 굽기)는 `BUILD_TESTING=OFF`라 이 블록을 타지 않는다.
- 이중 잠금: configure 단계에서 `IS_DIRECTORY` 검사로 FATAL_ERROR(빌드 시점에 바로 드러남) + 테스트 안에서 다시 검사(설치 후 디렉터리가 사라진 경우). 테스트 쪽 검사는 꼭 `ASSERT`로(빈 목록과 비교해 통과하는 일 방지). 골든 topics.txt의 줄 수가 0이면 실패도 넣는다.
- 추가 제안: 골든 `env.txt`의 `PX4_MSGS_REF`와 이미지의 `IDSIM_BUILD_PX4_MSGS_REF`(ros-ws ENV)가 같은지 테스트 하나로 단정하면, 매핑이 파생되는 px4_msgs와 비교 대상 골든이 같은 버전 조합임이 보장된다. 다르면 "골든 재생성 필요"로 실패.

## ros2-engineer, test-engineer와 맞춰야 할 지점

ros2-engineer
1. `.clang-format`, `.clang-tidy`를 저장소 루트에 두는지, 내용(기반 스타일, 열 수, 검사 목록). devops는 위치와 실행만 정한다.
2. ament_lint 묶음: ament_lint_common 대신 개별 test_depend로(uncrustify 제외 조건). copyright 머리말 정책.
3. `-Werror` 등 경고 정책을 패키지 CMakeLists에 둘지.
4. clang-tidy를 test 소스에 적용할지, 헤더 필터 범위.
5. 단위 테스트가 rclcpp 노드를 만드는지. 만들면 `--network none`, `CYCLONEDDS_URI=` 비움, `ROS_DOMAIN_ID=99` 조건에서 동작하는지 첫 PR에서 확인.
6. CMake 골든 경로 블록(D5)의 변수 이름 `IDSIM_REPO_ROOT`, 환경 변수 이름 `IDSIM_PX4_GOLDEN_DIR`. `env.txt`의 PX4_MSGS_REF와 이미지 ENV 대조 테스트를 넣을지.
7. `LLVM_MAJOR=18`(Ubuntu 24.04 기본) 수용 여부. 더 새 major가 필요하면 apt.llvm.org 저장소와 서명 키 지문을 versions.env에 추가해야 해서 비용이 커진다.
8. frame_transforms 호환: E3은 컴파일만 확인했다. 의미 검증 테스트가 없으면 "호환 확인"으로 기록하지 않는다.

test-engineer
1. colcon test의 종료 코드 규칙(E6, E7): `--return-code-on-test-failure` + 테스트 수 > 0 단정을 `tools/ros_ws.sh`에 두는 것에 동의하는지. 플래키 재시도는 unit 층에 두지 않는다(제안).
2. 골든 경로 계산 규칙을 Python(`tests/support/golden.py`)과 C++(CMake)가 같은 방식(versions.env PX4_TAG)으로 쓰는 것. 규칙이 바뀌면 두 곳을 같이 고친다는 점을 file-ownership 접점에 적을지.
3. unit 잡 아티팩트 범위(`ros_ws/log/`, `build/*/test_results/`)와 보존 기간.
4. 단위 층 "1분 이내" 목표를 colcon test 단계만으로 잴지, pull과 빌드를 포함할지. 첫 실측 4회 뒤 정한다.
5. 앞으로 pytest 단위 테스트(ROS 의존)를 같은 unit 잡의 colcon test(ament_cmake_pytest 또는 ament_python)로 넣을지, 별도 단계로 둘지. lint 잡의 pytest(생성기, tests/support)는 ROS가 없어 거기 남긴다.

architect(요청만)
- architecture.md "파이프라인 구성"에서 clang-tidy와 ament_lint를 (1) lint에서 (3) unit으로 옮기는 문장 수정.
