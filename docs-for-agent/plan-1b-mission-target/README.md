# Phase 1b 미션 시퀀스와 표적 추종 작업 계획

설계 결정과 계약은 `decisions.md`에 있다. 지금 어디까지 왔는지는 `docs-for-agent/progress.md`에 있다. 경위와 검토 내역은 커밋 메시지와 PR 본문에 있다.

## 이 디렉터리의 파일

| 파일 | 내용 | 성격 |
| --- | --- | --- |
| `README.md` | 이 문서. 범위, 작업 단위, 순서, 검토, 완료 기준 | 실행 계획 |
| `decisions.md` | 사용자 결정, 결정 요약, 쟁점 1-17, 재질문, 1a 고정 계약 영향, 사용자 결정 대기, 실측 목록, 문서 반영 목록, 넘김 목록 | 계약. 구현은 이 문서를 따른다 |

담당자 의견서는 저장소에 두지 않는다. 의견서의 권고 중 `decisions.md`와 다른 것은 `decisions.md`가 우선한다.

## 범위

목표(`docs/roadmap.md` Phase 1b): YAML 미션 하나로 x500이 이륙 -> 웨이포인트 순회 -> 이동 표적의 현재 위치로 접근 -> 복귀, 착륙을 수행하고 pytest가 판정한다.

1b가 만드는 것
- `idsim_mission`: GOTO, TRACK_ENTITY, RTL 항목, 진입 방식 셋(지상 arm, 공중 Offboard, 모드 명령), 공중에서 끝나는 미션의 종료 단계, 항목 순서 규칙의 계약 검증, 표적 구독, `FramePort`, YAML 로더(Python)와 CLI.
- `idsim_common`: `geo.hpp`(world ENU <-> 기체 로컬 NED 사슬), `TargetId`, `target_state_topic`, 상태 QoS 함수.
- `idsim_sim`: 월드 템플릿 `idsim_base.sdf`, 표적 어댑터(Python), wrapper의 원점 단계 정리.
- 생성기: `world.origin` 필수, 월드 SDF와 Actor 생성, `targets` 스키마와 서비스, `ops-N` params의 `world.origin`, `stack.json`의 `expect_gps`, bridge 허용 목록 검사.
- SITL 파라미터: `RTL_TYPE`, `RTL_CONE_ANG`, `RTL_RETURN_ALT`, `RTL_LAND_DELAY`, `COM_DISARM_LAND`, `COM_LOW_BAT_ACT`.
- 통합 테스트: 시나리오 B(1b 무효 사례 추가), C, A, D, F1, F2, F3, T. 계약 판정과 정답 판정의 분리, `/sim/<vehicle_id>/pose`.
- 문서: `docs/architecture.md`, `docs/roadmap.md`, `docs/smoke-test.md`의 1b 문장, `docs/interface.md`의 1b 계약 고정.

만들지 않는 것: 첫 항목이 아닌 TAKEOFF(U7), TARGET_LOST의 통합 시나리오(단위 테스트로 덮는다), Gazebo 서버 쪽 표적 system(U10에서 선택 2가 아니면), setpoint 점진 이동, recorder와 기록물(Phase 2), 3대 시나리오(Phase 3).

`idsim_interfaces`의 필드와 상수는 바꾸지 않는다. 의미 주석만 바뀌고 golden과 type hash는 그대로다.

## 작업 단위

| 단위 | 담당 | 내용 | 선행 |
| --- | --- | --- | --- |
| B0. 설계 확정 | architect | 재질문(P-1-P-5, R-1-R-3, S-1-S-3, T-1-T-3, D-1, D-2)의 답과 사용자 결정 U10-U12를 `decisions.md`에 반영. reviewer 검토 | 없음. 맨 먼저 |
| B1. 설계 문서의 범위와 경로 | architect | `decisions.md` "문서 반영 목록"의 B1 항목 | B0(U10) |
| B2. W 실측 | px4-engineer | `run_sitl.sh` 1회의 ULog로 W와 disarm 전후 `vehicle_status` 간격. 쟁점 11의 기준으로 판단 | 없음. B0과 병렬 |
| B3. 원점과 월드 | devops-engineer(생성기, `fleet.yaml`, `stack.json`의 `expect_gps`), sim-engineer(`idsim_base.sdf`, `gz_server.sh`), test-engineer(스모크 S2와 `check_px4` 기체별 기대값) | 쟁점 2, 16. M5 | B0(D-1, D-2) |
| B4. `idsim_common` 추가 | ros2-engineer | 쟁점 4, 14. `geo.hpp`와 gz-math, PX4 `MapProjection` 차등 단위 테스트, `TargetId`, `target_state_topic`, 상태 QoS | B0(P-1, S-2) |
| B5. SITL 파라미터 | px4-engineer(값과 근거 주석), devops-engineer(스모크 `expected_params`) | 쟁점 9의 여섯 파라미터 | B0(P-3) |
| B6. 표적 | sim-engineer(어댑터, Actor 생성 내용), devops-engineer(`targets` 스키마, 서비스, healthcheck, 생성기) | 쟁점 1, 3. M1 | B3 |
| B7. `idsim_mission` core와 px4 어댑터 | ros2-engineer(core, 전이 관측 port, 단위 테스트), px4-engineer(`px4/` 어댑터, snapshot 헤더와 전이 표의 필수 승인) | 쟁점 6-10, 12, 13 | B2, B4 |
| B8. 노드 껍질과 YAML 로더 | ros2-engineer(노드, 로더, CLI), devops-engineer(`ops-N` params의 `world.origin`) | 쟁점 4의 노드 쪽, 8의 표적 구독, 14 | B7 |
| B9. 통합 테스트 | test-engineer(판정, 시나리오, 미션 YAML, gate 기록), sim-engineer(정답 pose 공급 경로), devops-engineer(bridge와 compose, `sitl.yml`) | 쟁점 5, 11의 gate 기록, 15. R1-R3, 공중 시작, RTL 실측 | B5, B6, B8 |
| B10. viz 확인 | sim-engineer | 쟁점 17. M4 | B6 |
| B11. 계약 고정 문서 | architect | `decisions.md` "1a 고정 계약 영향" (a)-(k)와 "문서 반영 목록"의 B11 항목. `idsim_interfaces` 의미 주석 | B9의 완료 기준 충족 |

커밋은 담당자 소유 단위로 나눈다. PR은 단위마다 하나이고, B3, B6, B9처럼 담당이 여럿인 단위는 담당자별 커밋으로 나눈다. B7의 snapshot 헤더 변경은 W 결과(B2) 뒤에 한 PR로 묶는다(쟁점 12).

실험용 스택 번호: px4 5, ros2 6, test 7, devops 8. 사용자가 띄운 스택(보통 0)은 건드리지 않는다.

## 진행 순서

1. B0. 재질문을 담당자에게 보내고 사용자 결정 U10-U12를 받는다. 답이 결정을 뒤집으면 `decisions.md`를 고쳐 쓴다. B2는 B0과 함께 시작한다(답을 기다리지 않는다).
2. B1(U10 뒤), B3, B4, B5를 병렬로.
3. B6(B3 뒤), B7(B2, B4 뒤).
4. B8(B7 뒤), B10(B6 뒤).
5. B9. 첫 실행에서 b(R2)를 정하고 `tests/support/sitl_judge.py` 머리말에 근거를 적는다. 그 뒤 로컬 3회 연속과 CI.
6. B11.

## 검토

| 단위 | 관련 owner 검토 | 볼 것 |
| --- | --- | --- |
| B1 | reviewer | 범위 문구가 U10과 같은지, `docs/`가 `docs-for-agent/`를 가리키지 않는지 |
| B2 | ros2-engineer | W의 계산(명령과 ack의 대응), 기준 판단 |
| B3 | sim-engineer, test-engineer, devops-engineer(서로의 경계), px4-engineer(원점 적용과 `sensor_gps`) | 생성기 golden diff, 월드 직속 `<plugin>` 거부 테스트, M5 결과, 스모크 S2 통과 |
| B4 | px4-engineer(`MapProjection` 재현), sim-engineer(`SphericalCoordinates` 재현), test-engineer(테스트가 노드 없이 도는지) | 차등 테스트의 기준값과 원문 판 고정, 왕복 오차 |
| B5 | devops-engineer, test-engineer | 근거 주석, 스모크 `expected_params` 대조 통과 |
| B6 | ros2-engineer(QoS, stamp, 이름 조립), test-engineer(궤적 평가 golden), devops-engineer | 계약 상태 행 QoS, 같거나 작은 stamp 미발행, 생성기 거부 조건 |
| B7 | px4-engineer(필수 승인: snapshot 헤더, 전이 표, 상태기 단위 테스트), test-engineer(전이 관측과 칸 목록), architect(계약 문장과 구현의 일치) | 진입 방식 셋, 감시 표 적용 구간, RTL과 Land 폴백, 공중 종료 결과 표, 순서 규칙, core가 `idsim_common`과 px4_msgs에 의존하지 않는지 |
| B8 | px4-engineer(`px4/` 어댑터와 `FramePort` 연결), test-engineer(로더 출력) | 표적 구독 수명, `world.origin` 누락 시 configure 실패 |
| B9 | px4-engineer(판정 필드와 timeout), sim-engineer(정답 pose 경로), devops-engineer(wrapper와 `sitl.yml`), architect(판정이 `decisions.md` 쟁점 5와 같은지) | 계약 판정과 정답 판정의 분리, `ORACLE_ABSENT`, `UPSTREAM_FAILED`, b의 근거 |
| B10 | devops-engineer | 서버 생존 기록 |
| B11 | reviewer(필수), px4-engineer(SITL 파라미터 표와 전이 문장), ros2-engineer | golden 무변경, 1a 미션에 대한 의미가 그대로인지 |
| 전체 | reviewer | PR마다 규칙 준수와 가정의 근거. B7, B9, B11은 머지 전 필수 |

관련 owner의 승인 없이 머지하지 않는다. px4-engineer 호출이 안전장치로 중단되면 `CLAUDE.md` 모델 선택 규칙의 "사용자 예외"를 따른다.

## 완료 기준

- B0: 재질문 답과 U10-U12가 `decisions.md`에 반영되어 결정 요약의 상태 칸이 모두 "확정"이다. reviewer 검토를 받았다.
- B2: W의 최댓값과 표본 수, 처리 전 표본이 확인 계수에 들어간 기록의 유무, 그에 따른 판단(1a 규칙 유지 또는 ack timestamp 기준)이 PR 본문에 있다.
- B3: `tools/ci/lint.sh all` 통과(생성기 단위 테스트와 golden, 월드 SDF 원점 단정, 월드 직속 `<plugin>` 거부, bridge 허용 목록). 스모크 images, px4-out-clock 통과(S2 포함, M5). `world.origin`이 없는 `fleet.yaml`은 생성이 실패한다.
- B4: `tools/ros_ws.sh ci` 통과. `geo` 차등 테스트와 왕복 테스트가 있고 기존 테스트가 통과한다.
- B5: 스모크가 여섯 파라미터의 적용 값을 `expected_params`와 대조해 통과한다.
- B6: 표적 어댑터 단위 테스트(손 계산 golden) 통과, `targets` 서비스 healthcheck 통과, 그래프의 발행자 QoS가 계약 상태 행과 같다. M1 결과가 PR 본문에 있다.
- B7: `tools/ros_ws.sh ci` 통과. 승인된 전이 칸 목록에 대해 미덮임이 0이고 목록에 없는 변이 관측되지 않는다. px4-engineer가 승인했다. `idsim_interfaces` golden 무변경.
- B8: `tools/ros_ws.sh ci` 통과. 로더가 시험 미션 YAML을 `Mission`으로 바꾸는 단위 테스트가 있다.
- B9
  - `tests/sitl/run_sitl.sh --repeat 3`이 같은 commit, 같은 이미지 key에서 3회 연속 통과한다. 시나리오는 B, C, A, D, F1, F2, F3, T다.
  - CI `sitl` job이 통과한다. 단계별 시간과 판정 구간 RTF를 PR 본문에 남긴다. U11에서 정한 예산을 넘으면 판정 기준을 느슨하게 하지 않고 측정값과 함께 architect와 사용자에게 올린다.
  - b와 `R_home`이 근거(값, 표본 수, 실행 id)와 함께 판정 상수 머리말에 있고 b가 0.5 m 이하다. 넘으면 올린다(쟁점 5).
  - R1, R3가 `verdict.json`에 `recorded_only`로 남는다.
- B10: M4 결과(ogre2와 ogre, 재접속, 120 s 생존)가 PR 본문에 있다.
- B11: `docs/interface.md`의 1b 계약이 고정되고 "고정 전" 표시가 1b 몫에서 빠진다. 계약 테스트 golden과 type hash가 그대로다. reviewer가 확인했다.
- 1b 전체(roadmap 1b 완료 기준): 미션 통합 테스트가 headless로 로컬 3회 연속과 CI에서 통과, 상태기 단위 테스트가 승인된 전이 칸 전부를 덮음, `TargetState`와 GOTO, TRACK_ENTITY, RTL 항목(`GoToItem`, `TrackEntityItem` 포함)과 공중에서 끝나는 미션의 종료 동작의 계약 고정.

## 범위 밖(넘길 곳)

`decisions.md`의 "넘김 목록"이 정본이다. 요약: 반복 비행 허용(소비자가 생길 때), 기체별 `RTL_RETURN_ALT`와 EKF 원점 맞추기(Phase 3), `/sim/` 토픽의 기록 여부와 기록물 디렉터리 규약(Phase 2, U12), Fleet의 배분 전 검증과 공중 종료 끝점 계획(Phase 3).

## 사용자 결정

U7-U9는 `decisions.md` 머리의 "사용자 결정"에 있다. 대기 중인 U10(범위 문구), U11(CI `sitl` 시간 예산), U12(정답 pose의 기록물 포함 범위)는 `decisions.md`의 "사용자 결정 대기"에 선택지와 권고가 있다.
