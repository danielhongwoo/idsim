# 파일 소유

담당자 에이전트(`.claude/agents/`)별로 수정 권한을 가진 파일이다. 소유자가 아닌 담당자는 그 파일을 고치지 않고, 증상과 증거를 소유자에게 넘긴다.

| 파일 | 담당 |
| --- | --- |
| `docker/versions.env`, `docker/docker-bake.hcl`, `docker/Dockerfile.ros-base`, `docker/Dockerfile.ros-ws`, `docker/Dockerfile.xrce-agent`, `docker/ros-ws-entrypoint.sh`, `docker/compose.smoke.yaml`, `tests/smoke/run_smoke.sh`, `.gitignore` | devops-engineer |
| `docker/Dockerfile.px4`, `config/px4/sitl_params.env`, `tests/smoke/check_px4.py`, `tests/smoke/check_px4_pxh.py` | px4-engineer |
| `docker/Dockerfile.sim-base` | sim-engineer |
| `config/cyclonedds.xml`, `tests/smoke/capture.sh`, `tools/to_interface.py`, `docs/interface.md` 초안 | ros2-engineer |
| `tests/support/`, `tests/fixtures/` 골든 갱신 절차 | test-engineer |
| `docs/architecture.md`, `docs/roadmap.md`, `docs/smoke-test-phase1a.md`, `docs/interface.md` 최종, `ros_ws/src/idsim_interfaces/` | architect |

골든 파일(`tests/fixtures/px4/<태그>/`)의 내용 변경은 px4-engineer와 ros2-engineer가 diff를 승인한다.
