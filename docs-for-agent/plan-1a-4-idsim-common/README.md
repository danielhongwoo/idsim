# Phase 1a 4번 작업 idsim_common 작업 계획

작성 2026-11-10. 설계는 확정되었고 구현은 같은 날 브랜치 `feat/1a-4-idsim-common`에서 진행했다. 다른 작업 환경에서 이어서 구현할 수 있도록 이 디렉터리에 근거를 모두 둔다.

## 진행 상태 (2026-11-10)

| 단위 | 상태 |
| --- | --- |
| A | 파일 수정 완료(`sitl_params.env`, `check_px4_pxh.py`). S2-S5 회귀는 사용자가 직접 실행 중, 생성기 골든 갱신은 devops-engineer가 진행 중 |
| B | 완료(`tools/ros_ws.sh ci` 통과) |
| C | 완료. unit job의 CI 첫 실행은 PR 뒤 |
| D | 완료 |
| E | 진행(설계 문서와 progress.md 반영) |

남은 것: px4-engineer 접점 검토, reviewer 검토, PR과 CI. 실측값과 열린 항목은 `docs-for-agent/progress.md`에 있다.

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | architect 설계 결정 10건과 담당자별 구현 지시. reviewer 검증 조건 4건과 권고 5건 반영본 | 계약. 구현은 이 문서를 따른다 |
| `opinion-ros2.md` | ros2-engineer 초안과 실측(frame_transforms 결함, MESSAGE_VERSION 규칙, QoS, 패키지 구조, clang-format 설정 원문) | 근거 |
| `opinion-px4.md` | px4-engineer 의견과 실측(토픽 접미사 규칙, VehicleCommand 필드와 DO_SET_MODE 값, timestamp 동작, 좌표 관례, 공개 /fmu/in 허용과 차단 목록) | 근거 |
| `opinion-devops.md` | devops-engineer 의견과 실측(colcon 종료 코드 함정, 빌드 위치, unit job, lint 연결, `tools/ros_ws.sh`, 골든 경로 전달) | 근거 |
| `prototypes.md` | 토픽 기술자와 음성 컴파일 테스트 원형 코드, `.clang-format` 시안 | 참고. 그대로 옮기지 않는다 |

근거 파일에 나오는 `/tmp/...scratchpad...` 경로와 실험 디렉터리는 당시 환경의 임시 파일이라 저장소에 없다. 결론과 인용된 실측값만 쓴다.

## 새 환경에서 시작하는 순서

1. `docs-for-agent/progress.md`의 "새 개발 PC에서 시작할 때"를 따른다(`tools/check_host.sh`, 이미지 빌드, 스모크 S0과 S2).
2. 이 문서와 `decisions.md`를 읽는다. 담당자를 부를 때는 자기 몫의 "구현 지시" 절과 관련 근거 파일을 함께 넘긴다.
3. PR #11(이미지 빌드 apt 미러를 `UBUNTU_APT_MIRROR`로 지정, 기본 kr)은 2026-11-10 main에 들어갔다. 작업 단위 C도 바로 시작할 수 있다.
4. main에서 브랜치 `feat/1a-4-idsim-common`을 만든다. PR은 하나로 하고 커밋은 담당자 소유 단위로 나눈다.

도커 스택을 올리는 실험은 담당자마다 스택 번호를 나눠 쓴다(예: px4 5, ros2 4). 사용자가 화면 확인용으로 띄운 스택(보통 0)은 건드리지 않는다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| A. SITL 시간 기준 | px4-engineer | `config/px4/sitl_params.env`에 `UXRCE_DDS_SYNCT=0`과 근거 주석. `tests/smoke/check_px4_pxh.py`의 `DEFAULT_EXPECT`에 `UXRCE_DDS_SYNCT=0`(param show 저장값 판정). 생성기 골든이 바뀌면 `--update-golden`으로 갱신. 스택에서 S2-S5 회귀(S4 `--check` 일치) | 없음 |
| B. idsim_common 패키지 | ros2-engineer | 하위 작업 B1-B8(아래) | 없음. ros-ws 기존 이미지로 colcon 빌드 가능 |
| C. 빌드 도구와 CI | devops-engineer | ros-ws 이미지에 `clang-tidy-18`, `clang-format-18`, `versions.env`에 `LLVM_MAJOR=18`과 `LINT_CLANG_FORMAT_VERSION=18.1.3`, bake, `tools/ros_ws.sh`(build, test, tidy, ci, clean, shell), `.github/workflows/unit.yml`, lint job에 clang-format 연결, lint의 clang-tidy와 ament-lint 항목 삭제, `ros_ws/src`의 fmu 문자열과 `detail` 사용 검사 | 없음(PR #11 머지됨) |
| D. 부속 정리 | ros2-engineer, test-engineer | `tests/smoke/capture.sh`의 hz 목록에서 `timesync_status` 제외(ros2). `docs-for-agent/file-ownership.md`에 골든 경로 규칙이 Python과 CMake 두 곳에 있다는 접점 기록(test) | 없음 |
| E. 문서 | architect | `decisions.md` 쟁점 10의 문서 수정 목록(roadmap, architecture, smoke-test). `progress.md` 결정 기록과 미해결 갱신 | B 마무리 무렵 |

B의 하위 작업(세부는 `decisions.md`의 해당 쟁점).

| 번호 | 내용 | 쟁점 |
| --- | --- | --- |
| B1 | 패키지 골격(ament_cmake, SHARED, C++17, `-Werror`), `.clang-format`, `.clang-tidy`, ament 린터 xmllint, lint_cmake, cpplint(copyright 끔) | 7 |
| B2 | 좌표 변환 직접 구현(NED/ENU, FRD/FLU, 쿼터니언, yaw, 대각 분산), px4_ros_com과 차등 비교 테스트 | 1 |
| B3 | 골든 토픽 65개 기술자, key는 (방향, 논리 이름), 발행 허용 3개, `is_registered`와 `#undef`, 음성 컴파일 테스트 4건, 골든 양방향 일치 | 2 |
| B4 | QoS 프로필 두 개와 골든 writer 27개 대조 | 3 |
| B5 | `Px4Timestamp::now(rclcpp::Clock &)`와 거부 테스트 4종 | 4 |
| B6 | 기체 식별 타입과 vehicle_status 대조 함수 | 5 |
| B7 | VehicleCommand 빌더와 `is_ack_for` | 6 |
| B8 | CMake 골든 경로(`IDSIM_PX4_FIXTURE_DIR`)와 PX4_MSGS_REF 3곳 일치 테스트 | 9 |

## 진행 순서

1. A와 B를 병렬로 시작한다.
2. C도 같이 시작한다(PR #11 머지됨).
3. B와 C가 만나면 `tools/ros_ws.sh ci`로 로컬에서 먼저 돌리고, unit job에서 패키지 빌드, 테스트, clang-tidy를 처음 돌린다.
4. D와 E를 마무리한다.
5. 접점 검토와 reviewer 검토, PR, CI 통과, 사용자 머지.

## 검토

- px4-engineer: VehicleCommand 필드 표, 공개 /fmu/in 허용 목록과 차단 분류.
- devops-engineer: B8의 CMake 골든 블록이 `tools/ros_ws.sh`와 맞는지.
- test-engineer: 종료 코드 규칙(`colcon test --return-code-on-test-failure`와 테스트 수 0 초과 단정), 아티팩트 범위, 골든 경로 접점.
- reviewer: 전체(규칙, 결정과의 일치, 근거).

## 완료 기준

- unit job이 CI에서 통과하고 테스트 수가 0보다 크다.
- `decisions.md`가 요구한 테스트가 모두 있다: 좌표 변환 차등 비교와 NaN 보존, 골든 65개 양방향 일치, 허용 목록 3개 명시 비교, 음성 컴파일 4건, QoS 대조, `Px4Timestamp` 거부 4종, 식별 검사, 빌더 필드 표, PX4_MSGS_REF 3곳 일치.
- `UXRCE_DDS_SYNCT=0`에서 스모크 S2-S5 통과, S2의 pxh 판정에 `UXRCE_DDS_SYNCT=0`.
- `tools/ci/lint.sh all`과 clang-format 통과.
- 문서 수정 목록 반영, progress.md 갱신.

## 범위 밖(넘길 곳)

- 6번 작업: params 키와 생성기 출력, `declare_vehicle_identity`, 식별 게이트 정책, source 값 표(테스트 하네스 포함), setpoint 헬퍼, `/clock` 첫 수신 확인, sim 시간 timestamp 묵음 failsafe 통합 판정, 시동 상태 Offboard 거부 실측, Python 쪽 토픽 이름 규칙, `stack.sh up`의 install 부재 검사.
- 7번 작업: `docs/interface.md` 전체.
- 1b: 원점 이동 변환 함수, takeoff 빌더, `goto_setpoint` 공개 검토.
- Phase 2: ULog와 /fmu/out이 같은 시간 축이라는 전제의 정렬 설계(logging-engineer).

## 사용자 결정과 알림

- 결정 필요: 저장소 라이선스와 소스 파일 저작권 머리말 정책. 정해질 때까지 `ament_copyright`와 cpplint `legal/copyright`를 끈다.
- 알림: ros-ws 이미지가 clang 18 도구로 약 297MB 커지고 재빌드가 한 번 생긴다(공개 저장소의 무료 러너 안이라 금전 비용 없음으로 판단). 크기를 줄여야 하면 clang-tidy를 별도 도구 이미지로 빼는 안이 있다.

## 모델 운용 메모(2026-11-10)

- 이 설계 토론에서 Fable로 부른 architect와 reviewer가 모델 안전장치 오류(`[general_harms]`)로 세 번 중단되었다. 재호출하면 통과한 경우가 있었다.
- 사용자 결정: architect는 이번 설계 결정 한 번만 Opus로 불렀다. reviewer는 Fable을 유지한다.
- 구현 중 px4-engineer 호출이 같은 모델 안전장치 오류(`[general_harms]`)로 두 번 중단되었다. 그래서 `UXRCE_DDS_SYNCT=0` 스모크 S2-S5 회귀는 사용자가 호스트에서 직접 돌리기로 했다.
