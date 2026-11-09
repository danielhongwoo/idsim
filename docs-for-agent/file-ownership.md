# 파일 소유

담당자 에이전트(`.claude/agents/`)별로 수정 권한을 가진 파일이다. 소유자가 아닌 담당자는 그 파일을 고치지 않고, 증상과 증거를 소유자에게 넘긴다.

| 파일 | 담당 |
| --- | --- |
| `docker/versions.env`, `docker/docker-bake.hcl`, `docker/Dockerfile.ros-base`, `docker/Dockerfile.ros-ws`, `docker/Dockerfile.xrce-agent`, `docker/ros-ws-entrypoint.sh`, `docker/compose.smoke.yaml`, `docker/README.md`, `tests/smoke/run_smoke.sh`, `.gitignore`, `.github/workflows/`, `tools/ci/`, `ruff.toml`, `.hadolint.yaml`, `.yamllint.yaml`, `tools/qgc.sh`, `tools/gen_compose.py`(`viz` 프로필 생성 포함), `tools/gen_compose.sh`, `tools/stack.sh`, `config/fleet.yaml`(접점 검토 px4-engineer, sim-engineer, ros2-engineer), `tests/tools/`(초안. 승인은 test-engineer), `README.md`(저장소 루트), `tools/check_host.sh` | devops-engineer |
| `docker/Dockerfile.px4`, `docker/px4/px4-rc.mavlink`, `config/px4/sitl_params.env`, `tests/smoke/check_px4.py`, `tests/smoke/check_px4_pxh.py` | px4-engineer |
| `docker/Dockerfile.sim-base`, `ros_ws/src/idsim_sim/`(Gazebo GUI 설정 `gui.config`, gazebo와 gz-gui wrapper `scripts/` 포함) | sim-engineer |
| `config/cyclonedds.xml`, `tests/smoke/capture.sh`, `tools/to_interface.py`, `docs/interface.md` 초안 | ros2-engineer |
| `tests/support/`(`stack.py` 포함), `tests/fixtures/` 골든 갱신 절차, `tests/tools/` 승인 | test-engineer |
| `docs/architecture.md`, `docs/roadmap.md`, `docs/smoke-test-phase1a.md`, `docs/interface.md` 최종, `ros_ws/src/idsim_interfaces/` | architect |

골든 파일(`tests/fixtures/px4/<태그>/`)의 내용 변경은 px4-engineer와 ros2-engineer가 diff를 승인한다.
