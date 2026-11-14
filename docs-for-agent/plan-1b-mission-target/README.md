# Phase 1b 미션 시퀀스와 표적 추종 작업 계획

설계 결정과 계약은 `decisions.md`에 있다. 지금 어디까지 왔는지는 `docs-for-agent/progress.md`에 있다. 경위와 검토 내역은 커밋 메시지와 PR 본문에 있다.

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 범위, 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | 사용자 결정, 결정 요약, 쟁점 1-17, 1a 고정 계약 영향, 실측과 확인 목록, 문서 반영 목록, 넘김 목록 | 계약. 구현은 이 문서를 따른다 |

## 범위

목표(`docs/roadmap.md` Phase 1b): YAML 미션 하나로 x500이 이륙 -> 웨이포인트 순회 -> 이동 표적의 현재 위치로 접근 -> 복귀, 착륙을 수행하고 pytest가 판정한다. 표적은 `config/fleet.yaml`의 스크립트 궤적을 따르는 점 표적이다(U10).

1b가 만드는 것
- `idsim_mission`: GOTO, TRACK_ENTITY(표적 속도 feedforward 포함), RTL 항목, 진입 방식 셋(지상 arm, 공중 Offboard, 모드 명령), 공중에서 끝나는 미션의 종료 단계, 항목 순서 규칙의 계약 검증, 표적 구독, `FramePort`, 전이 관측 계측, YAML 로더(Python)와 CLI.
- `idsim_common`: `geo.hpp`(world ENU <-> 기체 로컬 NED 사슬), `TargetId`, `target_state_topic`, 상태 QoS 함수, `px4::position_setpoint`의 속도 feedforward 인자, float32 술어 `px4::fits_float32`.
- `idsim_sim`: ament_python 패키지 전환, 월드 템플릿 `idsim_base.sdf`, 표적 어댑터(Python), 정답 pose 노드 `sim_oracle.py`, wrapper의 원점 단계 정리.
- 생성기: `world.origin` 필수, 월드 SDF와 Actor 생성, `targets` 스키마와 서비스, `sim-oracle` 서비스, `ops-N` params의 `world.origin`, `stack.json`의 `expect_gps`, bridge 허용 목록 검사.
- SITL 파라미터: `RTL_TYPE`, `RTL_CONE_ANG`, `RTL_RETURN_ALT`, `RTL_LAND_DELAY`, `COM_DISARM_LAND`, `COM_LOW_BAT_ACT`, `EKF2_HGT_REF`.
- 통합 테스트: 시나리오 B(1b 무효 사례로 교체), C, A, D, F1, F2, F3, F4(roadmap 목표 그대로의 합친 미션, U13), T. 계약 판정과 정답 판정의 분리, `/sim/<vehicle_id>/pose`, 판정 반경 1 m(U14).
- 문서: `docs/architecture.md`, `docs/roadmap.md`, `docs/smoke-test.md`의 1b 문장, `docs/interface.md`의 1b 계약 고정.

만들지 않는 것: 첫 항목이 아닌 TAKEOFF(U7), TARGET_LOST의 통합 시나리오(단위 테스트로 덮는다), Gazebo 기반 표적 생산자(U10의 확장 항목), setpoint 점진 이동, recorder와 기록물(Phase 2. `/sim/` 기록은 U12로 Phase 2에서), 3대 시나리오(Phase 3).

`idsim_interfaces`의 필드와 상수는 바꾸지 않는다. 의미 주석만 바뀌고 golden과 type hash는 그대로다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| B0. 설계 확정 | architect, reviewer | 확정한 결정(쟁점 1-17)의 reviewer 검토. 검토 지적은 architect가 `decisions.md`에 반영 | 없음. 맨 먼저 |
| B1. 설계 문서의 범위와 경로 | architect | `decisions.md` "문서 반영 목록"의 B1 항목. U10 문구 | B0 |
| B2. W 실측 | px4-engineer | `run_sitl.sh` 1회의 ULog로 W와 disarm 전후 `vehicle_status` 간격. 쟁점 11의 유지 조건으로 판단 | 없음 |
| B3. 원점과 월드 | devops-engineer(생성기 판 5, fleet schema 2, fixture 템플릿과 golden, `config/fleet.yaml`의 기체 1 스폰, `sim_stack.sh` 사전 검사, `run_smoke.sh`의 `expect_gps`와 S0 센서 높이 대조, S0 월드 템플릿 대조와 템플릿 출처 ref 단위 테스트, `docker/README.md`와 저장소 `README.md`의 원점 문장), sim-engineer(`idsim_base.sdf`와 출처 주석의 ref 줄, `gz_server.sh`, S0 월드 템플릿 대조의 비교 규칙 검토), test-engineer(`stack.py` 판 5 명세), px4-engineer(`check_px4.py` 고도 주석), architect(`decisions.md` "문서 반영 목록"의 B3 묶음: `docs/smoke-test.md`, `docs/architecture.md` gazebo 행의 원점 단계와 시작 순서 문장, `docs/roadmap.md` 1a 3번의 원점 문장, `docs/interface.md`의 원점 적용 문장과 bridge 문장) | 쟁점 2, 16. 월드 생성, `IDSIM_ORIGIN_*` 제거, 런타임 원점 호출 제거를 한 PR로. M5, S2-a는 그 PR의 스모크 | B0 |
| B4. `idsim_common` 추가 | ros2-engineer | 쟁점 4, 14. `geo.hpp`와 gz-math LOCAL2, PX4 `MapProjection` 차등 단위 테스트, `TargetId`, `target_state_topic`, 상태 QoS, `position_setpoint`의 속도 인자. 머지는 S2-a 통과(B3 PR의 스모크) 뒤 | B0. 머지는 B3 뒤 |
| B5. SITL 파라미터 | px4-engineer(값과 근거 주석), devops-engineer(스모크 `expected_params`, 생성기 golden 재생성) | 쟁점 9의 일곱 파라미터. `sitl_params.env`가 바뀌면 생성기 golden(`inputs`의 sha256, `expected_params`)이 바뀐다 | B0 |
| B6. 표적 어댑터 | sim-engineer(`idsim_sim` ament_python 전환, 어댑터, Actor 생성 내용, `gui.config` plugin 목록 고정 단위 테스트), devops-engineer(`targets` 스키마, 서비스, healthcheck, 생성기) | 쟁점 1, 3. M1 | B3 |
| B7. 정답 pose | sim-engineer(`sim_oracle.py`, 오프셋 합성과 구독 토픽 단위 테스트), devops-engineer(`sim-oracle` 서비스와 healthcheck) | 쟁점 5. S1-a | B3 |
| B8. 전이 관측 계측 | ros2-engineer(계측, `transition.hpp`, 칸 목록 파일), px4-engineer(1a 칸 목록 승인), test-engineer(테스트 실행 파일 통합의 구조 승인), architect(`docs-for-agent/file-ownership.md`에 `Event` 목록과 칸 목록 파일의 px4 승인 한 줄. U16) | 쟁점 13. 동작 무변경 | B0 |
| B8b. 1a 미덮임 칸 덮기 | ros2-engineer(runner 테스트와 정리 칸을 파라미터로 받는 테스트 harness, 칸 목록의 부류 갱신), px4-engineer(칸 목록 diff와 새 테스트의 필수 승인), test-engineer(harness 구조 승인) | 쟁점 13. 테스트만 더한다. `idsim_mission_core` 소스 무변경 | B8 |
| B9. `idsim_mission` core와 px4 어댑터 | ros2-engineer(core, 단위 테스트), px4-engineer(`px4/` 어댑터, snapshot 헤더와 전이 표의 필수 승인, K1-K4 확인) | 쟁점 6-10, 12. 헤더 PR 하나와 상태기 PR 여섯(S1-S6, 순서와 범위는 `decisions.md` 쟁점 12. 칸 목록 diff로 승인). 지상 arm 진입의 arm 순서 불변식과 ack 대기 구간(쟁점 12), 단위 테스트 다섯 사례. S2 첫 커밋에서 검증 함수를 goal 접수용과 runner용으로 나눈다. S5에 `idsim_common`의 `fits_float32` 공개(쟁점 14)와 좌표 상한(쟁점 8)이 들어간다. 경계: `step()`이 `FramePort`를 받고 core가 `Snapshot.targets`를 읽는 것까지이고, 노드는 호출부만 맞춰 늘 값 없음인 port와 빈 표적 맵을 넘기며 goal 접수가 받는 미션은 1a 그대로다 | B4, B8. 상태기 PR은 B8b 뒤 |
| B10. 노드 껍질과 YAML 로더 | ros2-engineer(노드, 표적 구독과 변환, 로더, CLI, 노드 테스트의 무효 미션 사례), devops-engineer(`ops-N` params의 `world.origin`), test-engineer(시나리오 B의 사례 교체) | 쟁점 4의 노드 쪽, 8의 표적 구독, 14. 경계: 노드가 진짜 `Px4FramePort`를 넘기고(`to_local_position_input` 채택, 원점 변경 WARN, `world.origin`) 표적을 구독하며, goal 접수의 1a 미션 제한을 지워 계약 검증만 남긴다. 같은 PR에서 시나리오 B와 노드 테스트의 무효 미션 사례를 1b 무효 사례로 바꾼다(쟁점 15) | B9 |
| B11. 통합 테스트 | test-engineer(판정, 시나리오 F1-F4, 미션 YAML, gate 기록, 비행 단위 fixture), sim-engineer(정답 pose 경로 확인), devops-engineer(compose와 `sitl.yml`) | 쟁점 5, 11의 gate 기록, 15. R1-R4, 공중 시작, RTL 실측 | B5, B6, B7, B10 |
| B12. viz 확인 | sim-engineer | 쟁점 17. M4 | B6 |
| B13. 계약 고정 문서 | architect | `decisions.md` "1a 고정 계약 영향" (a)-(t)((r)과 (k) 앞부분은 B3)와 "문서 반영 목록"의 B13 항목. `idsim_interfaces` 의미 주석 | B11의 완료 기준 충족 |

커밋은 담당자 소유 단위로 나눈다. PR은 단위마다 하나이고, 담당이 여럿인 단위는 담당자별 커밋으로 나눈다. 생성기 golden을 바꾸는 PR(B3, B5, B6, B7)은 나중에 머지되는 쪽이 main에 rebase한 뒤 golden을 생성기로 다시 만든다(손으로 합치지 않는다. 재생성은 devops-engineer). 예외 둘:
- B9의 snapshot 헤더 변경(`SetpointOut` 속도 포함)은 한 PR로 묶는다(쟁점 12). 상태기 변경은 px4-engineer가 먼저 바뀌는 칸과 칸마다 기대 명령의 표를 쓰고 ros2-engineer가 그 표대로 테스트와 구현을 한 뒤 px4-engineer가 대조한다. 상태기 변경은 B8b로 1a 칸 목록의 미덮임이 0이 된 뒤 PR마다 칸 목록 diff를 함께 내고, 새 칸은 그 PR에서 덮는다. 상태기 PR은 S1-S6 여섯이고 순서대로 하나씩 머지한다(`decisions.md` 쟁점 12). 로컬 branch로 진행하고 PR마다 reviewer 최종 검토를 받는다. 로컬 branch에서는 CI `sitl`이 돌지 않으므로 S1-S6 모두 머지 전에 로컬 `tests/sitl/run_sitl.sh`(1a 시나리오)를 돌린다.
- B11은 한 PR 안에서 커밋 둘로 나눈다. (가) F1-F4의 trace에 R2와 R4를 기록하는 커밋. b와 `R_home`이 빈 보정 상태(`decisions.md` 쟁점 5)이고 시험 미션의 `acceptance_radius_m`은 보정 값 0.5 m다. 보정 상태에서는 `R_home`에 기대는 단정만 `recorded_only`이고 나머지 판정은 그대로 실패로 세므로, F1이 통과하면 F2-F4가 돌아 표본이 모인다. 로컬 `run_sitl.sh --repeat 30`으로만 돌리고 CI 시나리오 목록에는 F1-F4를 모두 넣지 않는다. (가)는 머지되지 않는 중간 상태다. (나) b와 `R_home`을 근거(`decisions.md` 쟁점 5의 항목)와 함께 `tests/support/sitl_judge.py` 머리말에 적고, 시험 미션 YAML의 `acceptance_radius_m`을 `1.0 - b`로 바꾸고, F1-F4를 CI 목록에 넣는 커밋. (나)의 상태로 로컬 부팅 10회 이상의 확인 실행을 한다. 머지되는 상태는 (나)뿐이다. 이렇게 해서 CI가 상수 없는 판정으로 시작하지 않고, 상수를 통과와 실패를 보고 정하지 않는다.

실험용 스택 번호: px4 5, ros2 6, test 7, devops 8, sim 9. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.

## 진행 순서

1. B0. 확정한 결정을 reviewer가 검토한다. B2는 바로 시작한다(실측이라 결정을 기다리지 않는다).
2. B0 뒤 B1, B3, B4, B5, B8을 병렬로.
3. B6, B7(B3 뒤). B8b(B8 뒤). B9(B4, B8 뒤. 헤더 PR이 먼저이고 상태기 PR은 B8b 뒤).
4. B10(B9 뒤), B12(B6 뒤).
5. B11. 커밋 (가)로 로컬 `--repeat 30`에서 b와 `R_home`을 정하고 커밋 (나)로 적는다. (나)에서 확인 실행(부팅 10회 이상), 그 뒤 로컬 3회 연속과 CI.
6. B13.

## 검토

| 단위 | 관련 owner 검토 | 볼 것 |
| --- | --- | --- |
| B0 | reviewer | 결정의 근거([소스], [실측], [추정] 표기), 원칙(운용 서비스가 시뮬레이터를 모른다, 기체 식별 단일 출처, `/clock` 기준) 준수, 생성기와 서비스 결정(쟁점 2, 3, 5, 16)이 서로 맞는지 |
| B1 | reviewer | 범위 문구가 U10과 같은지, `docs/`가 `docs-for-agent/`를 가리키지 않는지 |
| B2 | ros2-engineer | W의 계산(명령과 ack의 대응), 쟁점 11 유지 조건 판단 |
| B3 | sim-engineer, test-engineer, devops-engineer(서로의 경계), px4-engineer(원점 적용과 `sensor_gps`), ros2-engineer(`config/fleet.yaml` 인터페이스 검토), reviewer(architect의 문서 커밋) | 생성기 golden diff, 월드 직속 `<plugin>` 거부 테스트, M5와 S2-a 결과, 스모크 S2 통과, 문서의 원점 경로가 M5 결과와 같은지 |
| B4 | px4-engineer(`MapProjection` 재현, 속도 인자), sim-engineer(`PositionTransform` LOCAL2 재현), test-engineer(테스트가 노드 없이 도는지) | 차등 테스트의 기준값과 원문 판 고정, 왕복 오차 |
| B5 | devops-engineer, test-engineer | 근거 주석, 스모크 `expected_params` 대조 통과, 생성기 golden diff가 파라미터 변경분뿐인지 |
| B6 | ros2-engineer(QoS, stamp, 이름 조립, DDS 환경), test-engineer(궤적 평가 golden), devops-engineer | 계약 상태 행 QoS, 같거나 작은 stamp 미발행, params 평탄화, 생성기 거부 조건 |
| B7 | test-engineer(판정이 쓰는 형식), devops-engineer, px4-engineer(기준점이 PX4 로컬 위치와 같은지, K4) | base_link 오프셋 합성, `dynamic_pose` 금지 단정, 표시 파일 healthcheck |
| B8 | px4-engineer(필수 승인: 1a 칸 목록과 `Event` 목록), test-engineer(구조 승인) | 동작 무변경(기존 runner 테스트 본문 무변경), untagged 검출, 겹침 칸의 열거 범위(쟁점 13), `test_monitor_table`의 행 쌍 단정(`row`와 `matched`) |
| B8b | px4-engineer(필수 승인: 칸 목록 diff, 새 테스트), test-engineer(구조 승인), reviewer | 미덮임 0, "불가능"으로 옮긴 칸의 [소스] 이유, 대표 취소 칸의 명령 미발행 단정, core 소스 무변경 |
| B9 | px4-engineer(필수 승인: snapshot 헤더, 전이 표, 상태기 단위 테스트), test-engineer(칸 목록 diff), architect(계약 문장과 구현의 일치) | 진입 방식 셋, 지상 arm 진입의 순서 불변식(쟁점 12), 감시 표 면제 구간(첫 OFFBOARD 표본까지)과 그 뒤 재전송 중단, RTL과 Land fallback, 공중 종료 결과 표, 속도 feedforward 조건, 변환 값 없음의 처리와 `Px4FramePort`의 float32 술어, 좌표 상한, 순서 규칙, 1a 미션이 지나는 덮임 칸이 그대로인지(쟁점 12의 예외 밖), PR이 새로 받는 미션을 goal 접수가 INVALID_MISSION으로 끝내는 단위 테스트, goal 접수가 받는 미션이 1a 그대로인지, core가 `idsim_common`과 px4_msgs에 의존하지 않는지 |
| B10 | px4-engineer(`px4/` 어댑터와 `FramePort` 연결, 같은 표본에서 기준 읽기, `target_fresh_age` 0.1 s와 `target_timeout` 1.0 s 기본값), test-engineer(로더 출력) | 값 없는 임시 port와 goal 접수의 1a 미션 제한(`validate_mission_1a_goal`)이 지워졌는지, 시나리오 B와 노드 테스트의 무효 사례가 1b 사례인지, 표적 구독 수명, TARGET_LOST 뒤 Hold 확인까지 발행 유지, `world.origin` 누락 시 configure 실패(embedded 변형에는 `ops-N`이 없어 해당 없음. `decisions.md` 쟁점 4) |
| B11 | px4-engineer(판정 필드와 timeout), sim-engineer(정답 pose 경로), devops-engineer(wrapper와 `sitl.yml`), architect(판정이 `decisions.md` 쟁점 5, 15와 같은지) | 계약 판정과 정답 판정의 분리, `ORACLE_ABSENT`, `ORACLE_STALE`, `UPSTREAM_FAILED`, b와 `R_home`의 근거와 모형 검증, 시험 미션 반경과 판정 상수의 대조 테스트, L과 `target_fresh_age`의 대조 테스트, `/targets/*/state` 발행자 QoS를 계약 상태 행과 대조하는 통합 테스트, 두 커밋 절차 |
| B12 | devops-engineer | 서버 생존 기록 |
| B13 | reviewer(필수), px4-engineer(SITL 파라미터 표, 전이 문장, "Offboard setpoint" 절의 속도 예외), ros2-engineer | golden 무변경, 1a 미션에 대한 의미가 그대로인지 |
| 전체 | reviewer | PR마다 규칙 준수와 가정의 근거. B8, B8b, B9, B11, B13은 머지 전 필수 |

관련 owner의 승인 없이 머지하지 않는다. px4-engineer 호출이 안전장치로 중단되면 `CLAUDE.md` 모델 선택 규칙의 "사용자 예외"를 따른다.

## 완료 기준

- B0: reviewer 검토를 받았고 지적이 `decisions.md`에 반영되었다.
- B1: B1 항목이 `docs/`에 반영되고 reviewer가 확인했다.
- B2: 명령별 W의 최댓값과 표본 수(W_arm 포함), 처리 전 표본이 확인 계수에 들어간 기록의 유무, 쟁점 11의 유지 조건에 따른 판단이 PR 본문에 있다.
- B3: `tools/ci/lint.sh all` 통과(생성기 단위 테스트와 golden, 월드 SDF 원점 단정, 월드 직속 `<plugin>` 거부, bridge 허용 목록). 스모크 images(S0 센서 높이 대조와 월드 템플릿 대조 포함), px4-out-clock 통과(S2 포함, M5, S2-a). fleet `schema` 1과 `world.file`은 생성이 실패한다. `world.origin`이 없는 `fleet.yaml`은 생성이 실패한다. `decisions.md` "문서 반영 목록"의 B3 묶음이 M5 결과대로 반영되었다.
- B4: `tools/ros_ws.sh ci` 통과. `geo` 차등 테스트와 왕복 테스트, `position_setpoint` 속도 인자 테스트가 있고 기존 테스트가 통과한다. S2-a가 통과했다(NavSat이 LOCAL2를 쓴다는 [추정]의 확인).
- B5: 스모크가 일곱 파라미터의 적용 값을 `expected_params`와 대조해 통과한다. 생성기 golden이 다시 만들어졌고 `tools/ci/lint.sh all`이 통과한다.
- B6: 표적 어댑터 단위 테스트(손 계산 golden)와 `gui.config` plugin 목록 고정 테스트 통과, `targets` 서비스 healthcheck 통과, 그래프의 발행자 QoS가 계약 상태 행과 같다. M1 결과가 PR 본문에 있다.
- B7: `sim_oracle.py` 단위 테스트(오프셋 합성, 구독 토픽) 통과, `sim-oracle` healthcheck 통과. S1-a 결과가 PR 본문에 있다.
- B8: `tools/ros_ws.sh ci` 통과. 1a 칸 목록이 쟁점 13의 열거 범위대로 있고 px4-engineer가 승인했다. `test_monitor_table`이 모든 행 쌍에서 `row`와 `matched`(배타 쌍은 함께 맞지 않음)를 단정한다. untagged 기록이 0이다. 기존 runner 테스트 본문이 바뀌지 않았다.
- B8b: `tools/ros_ws.sh ci` 통과. 1a 칸 목록의 미덮임이 0이고 덮음 테스트가 "미덮임" 부류의 칸을 거부한다. `idsim_mission_core` 소스가 바뀌지 않았다. px4-engineer가 승인했다.
- B9: `tools/ros_ws.sh ci` 통과. 승인된 전이 칸 목록에 대해 미덮임이 0이고 목록에 없는 변이 관측되지 않는다. px4-engineer가 승인했다. S6 뒤 runner의 검증은 계약 검증과 같고 goal 접수가 받는 미션은 1a 그대로다. S1-S6 각각의 머지 전에 로컬 `tests/sitl/run_sitl.sh`(1a 시나리오)가 통과했고, 1a 미션이 지나는 덮임 칸이 그대로라는 대조가 PR마다 본문에 있다. K1-K4 결과가 PR 본문에 있다. `idsim_interfaces` golden 무변경.
- B10: `tools/ros_ws.sh ci` 통과. 로더가 시험 미션 YAML을 `Mission`으로 바꾸는 단위 테스트가 있다. 시나리오 B가 1b 무효 사례이고 머지 전에 로컬 `tests/sitl/run_sitl.sh`가 통과했다.
- B11
  - `tests/sitl/run_sitl.sh --repeat 3`이 같은 commit, 같은 이미지 key에서 3회 연속 통과한다. 시나리오는 B, C, A, D, F1, F2, F3, F4, T다.
  - CI `sitl` job이 통과한다. 단계별 시간과 판정 구간 RTF를 PR 본문에 남긴다. 15분(U11)을 넘으면 겹치는 비행 구간 -> 순회 waypoint 수 -> Hold 유지 시간 순으로 줄이고(U15), 그래도 넘으면 판정 기준을 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다.
  - b와 `R_home`이 근거(값, 부팅 30회 이상, 사건 수, `mean(s)`, `std(s)`, 최댓값, `s_track` 통계, 실행 id)와 함께 판정 상수 머리말에 있고 모형 검증(GOTO와 `s_track` 각각의 최댓값 점검과 Shapiro-Wilk, `s_track` 허용한계가 b 이하)을 통과했다. m과 m_home이 시나리오의 사건 수와 같다는 단위 테스트가 있다. b가 0.5 m 이하이고(시험 미션의 `acceptance_radius_m = 1.0 - b`가 0.5 m 이상) `R_home`이 1 m 이하다. 넘거나 모형 검증에 실패하면 올린다(쟁점 5). (나)의 확인 실행에서 모든 도달 사건이 1.0 m 안이다.
  - R1, R3가 `verdict.json`에 `recorded_only`로 남는다. F2, F4 trace로 표적 접근의 L(0.2 s)이 맞는지와 R3 판단 기준(나이 99.9% 분위수, 신선하지 않은 tick 비율)을 확인한 결과가 PR 본문에 있다.
- B12: M4 결과(ogre2와 ogre, 재접속, 120 s 생존)와 궤적 길이 합 상한 월드의 기록이 PR 본문에 있다.
- B13: `docs/interface.md`의 1b 계약이 고정되고 "고정 전" 표시가 1b 몫에서 빠진다. 계약 테스트 golden과 type hash가 그대로다. reviewer가 확인했다.
- 1b 전체(roadmap 1b 완료 기준): 합친 미션 F4를 포함한 미션 통합 테스트가 headless로 로컬 3회 연속과 CI에서 통과, 상태기 단위 테스트가 승인된 전이 칸 전부를 덮음, `TargetState`와 GOTO, TRACK_ENTITY, RTL 항목(`GoToItem`, `TrackEntityItem` 포함)과 공중에서 끝나는 미션의 종료 동작의 계약 고정.

## 범위 밖(넘길 곳)

`decisions.md`의 "넘김 목록"이 정본이다. 요약: 반복 비행 허용(소비자가 생길 때), 기체별 `RTL_RETURN_ALT`와 EKF 원점 맞추기(Phase 3), SITL 기록물의 `/sim/` 기록과 기록물 디렉터리 규약(Phase 2, U12), Fleet의 배분 전 검증과 공중 종료 끝점 계획(Phase 3), Gazebo 기반 표적 생산자(U10의 확장 항목).

## 사용자 결정

U7-U16은 `decisions.md` 머리의 "사용자 결정"에 있다. 지금 사용자 결정을 기다리는 항목은 없다.
