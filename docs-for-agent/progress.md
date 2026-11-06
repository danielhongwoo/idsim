# idsim 진행 상황

이 폴더는 에이전트와 작업자가 세션을 시작할 때 현재 상태를 파악하기 위한 기록이다. 설계는 `docs/architecture.md`, 계획은 `docs/roadmap.md`에 두고, 여기에는 무엇이 끝났고 무엇이 진행 중이며 다음에 무엇을 할지만 적는다. 날짜는 항상 절대 날짜(YYYY-MM-DD)로 쓴다.

## 현재 상태 (2026-11-06)

- 코드는 아직 없다. 저장소는 git으로 초기화했고 첫 커밋에 문서와 규칙만 들어 있다.
- 설계 문서(`docs/`), 규칙(`CLAUDE.md`), 담당자 정의(`.claude/agents/`)까지 작성 완료.
- 다음 작업: roadmap Phase 1a의 1단계 환경 스모크 테스트. `docker/`에 `ros-base`, `sim-base`, `px4`, `ros-ws` 이미지와 `versions.env`를 만들고, CycloneDDS rmw로 `/px4_1/fmu/out/vehicle_status`가 보이는지 확인한다. 이때 토픽 이름 목록을 저장해 버전 접미사 유무와 PX4 태그를 확정한다.

## Phase별 진행

| Phase | 상태 | 마지막 갱신 | 비고 |
| --- | --- | --- | --- |
| 1a | 시작 전 | 2026-11-06 | 1단계 스모크 테스트부터 |
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
- 2026-11-06: Fleet Manager 구현 언어는 C++로 확정. gRPC 서버 스레드와 rclcpp executor가 공유하는 상태는 명시적으로 보호하고 설계 문서에 표로 남긴다.

## 미해결 사항

- PX4 릴리스 태그를 v1.16과 v1.17 중 무엇으로 고정할지는 스모크 테스트 결과로 정한다.
- Phase 1a 완료 기준의 `docs/interface.md`는 아직 없다.

## 갱신 규칙

- 작업 단위가 끝날 때마다 "현재 상태"와 "Phase별 진행"을 갱신하고, 설계에 영향을 주는 결정은 "결정 기록"에 날짜와 함께 추가한다.
- 설계나 계획 자체가 바뀌면 `docs/`를 고치고, 여기에는 바뀌었다는 사실과 날짜만 남긴다.
