# 파일 소유

담당자 에이전트(`.claude/agents/`)별로 수정 권한을 가진 파일이다. 소유자가 아닌 담당자는 그 파일을 고치지 않고, 증상과 증거를 소유자에게 넘긴다.

| 파일 | 담당 |
| --- | --- |
| `docker/versions.env`, `docker/docker-bake.hcl`, `docker/Dockerfile.ros-base`, `docker/Dockerfile.ros-ws`, `docker/Dockerfile.xrce-agent`, `docker/ros-ws-entrypoint.sh`, `docker/README.md`, `tests/smoke/run_smoke.sh`, `.gitignore`, `.github/workflows/`, `tools/ci/`, `ruff.toml`, `.hadolint.yaml`, `.yamllint.yaml`, `tools/qgc.sh`, `tools/gen_compose.py`(`viz` 프로필 생성 포함), `tools/gen_compose.sh`, `tools/sim_stack.sh`, `config/fleet.yaml`(인터페이스 검토 px4-engineer, sim-engineer, ros2-engineer), `tests/tools/`(초안. 승인은 test-engineer), `README.md`(저장소 루트), `tools/check_host.sh`, `tools/ros_ws.sh`, `.github/workflows/unit.yml` | devops-engineer |
| `docker/Dockerfile.px4`, `docker/px4/px4-rc.mavlink`, `config/px4/sitl_params.env`, `tests/smoke/check_px4.py`, `tests/smoke/check_px4_pxh.py`, `ros_ws/src/idsim_mission/include/idsim_mission/px4/`, `ros_ws/src/idsim_mission/src/px4/`, `ros_ws/src/idsim_mission/test/px4/` | px4-engineer |
| `docker/Dockerfile.sim-base`, `ros_ws/src/idsim_sim/`(Gazebo GUI 설정 `gui.config`, gazebo와 gz-gui wrapper `scripts/` 포함) | sim-engineer |
| `config/cyclonedds.xml`, `ros_ws/src/idsim_common/`, 루트 `.clang-format`, `.clang-tidy`, `tests/smoke/capture.sh`, `tools/to_interface.py`, `docs/interface.md` 초안, `ros_ws/src/idsim_mission/`(launch, `include/idsim_mission/core/snapshot.hpp` 포함. 아래 px4-engineer 몫 제외) | ros2-engineer |
| `tests/support/`(`stack.py` 포함), `tests/fixtures/` 골든 갱신 절차, `tests/tools/` 승인, `tests/sitl/`(`run_sitl.sh` 포함) | test-engineer |
| `docs/architecture.md`, `docs/roadmap.md`, `docs/smoke-test.md`, `docs/interface.md` 최종, `ros_ws/src/idsim_interfaces/` | architect |

골든 파일(`tests/fixtures/px4/<태그>/`)의 내용 변경은 px4-engineer와 ros2-engineer가 diff를 승인한다.

계약 golden(`ros_ws/src/idsim_interfaces/test/golden/`)의 내용 변경은 계약 변경이므로 architect가 diff를 승인한다. 고정된 파일의 직접 정의 golden(`golden/direct/`)이 바뀌는 PR에는 `docs/interface.md`의 갱신이 함께 들어가야 하고, 변경 근거는 PR 본문에 적는다. 갱신 절차(`IDSIM_UPDATE_GOLDEN=1`은 `tools/ros_ws.sh shell` 안에서만, 자동 갱신 없음)와 `test/test_contract.py`의 구조는 test-engineer가 승인한다.

## idsim_mission의 승인 규칙

- 상태기는 ros2-engineer가 `docs-for-agent/plan-1a-6-idsim-mission/decisions.md`의 전이 표대로 구현한다. 전이 표와 상태기 단위 테스트의 변경은 px4-engineer가 필수 승인자다.
- `include/idsim_mission/core/snapshot.hpp`는 ros2-engineer 소유이고 변경은 px4-engineer가 필수 승인자다.
- 타임아웃 기본값과 명령 재전송 주기(노드 파라미터의 기본값)는 값을 px4-engineer가 정한다. 그 값이 적힌 파일은 ros2-engineer 소유이고, 값의 변경은 px4-engineer가 필수 승인자다.
- 패키지 `test/`는 `test/px4/`가 px4-engineer, 나머지가 ros2-engineer 소유다. 단위 테스트의 구조는 test-engineer가 승인한다.
- `tests/support/px4_raw.py`(테스트가 /fmu/in에 쓰는 유일한 모듈)는 test-engineer 소유이고 변경은 px4-engineer가 필수 승인자다.
- `tests/sitl/measure/`(실측 스크립트)는 test-engineer 소유이고 측정 절차의 변경은 px4-engineer가 필수 승인자다.
- `idsim_mission_core`는 px4_msgs에 의존하지 않는다. PX4 enum의 해석은 `px4/` 디렉터리에만 둔다.

## 인터페이스: 골든 경로 규칙

골든 디렉터리 경로 규칙(`docker/versions.env`의 `PX4_TAG` -> `tests/fixtures/px4/<PX4_TAG>/`)이 두 곳에 구현되어 있다. 규칙을 바꾸면 둘 다 고친다.

- Python: `tests/support/golden.py`의 `golden_dir()` (test-engineer)
- CMake: `ros_ws/src/idsim_common/CMakeLists.txt`의 `IDSIM_PX4_FIXTURE_DIR` 블록 (ros2-engineer)
