# Phase 1b 미션 시퀀스와 표적 추종 설계 결정

Phase 1b(미션 시퀀스와 표적 추종)의 설계 결정이다. 구현은 이 문서를 따른다. 지금 유효한 것만 적는다. 결정의 경위(담당자 의견, 토론, 검토)는 커밋 메시지와 PR 본문에 있다. 작업 단위와 완료 기준은 같은 디렉터리의 `README.md`에, `docs/`에 반영할 것은 아래 "문서 반영 목록"에 있다.

표기: [소스]는 PX4 v1.17.0, gz-sim 8.15.0, gz-math 7, sdformat14, 저장소 원문으로 확인한 것, [실측]은 1a에서 잰 것이거나 이미지 안의 라이브러리로 계산한 것, [추정]은 확인하지 않은 판단이다. 모든 쟁점은 확정이고 그대로 구현한다. 구현 중에 확인할 사실은 "실측과 확인 목록"에 있고, 확인 결과가 결정과 다르면 architect에게 올린다.

## 사용자 결정

- U7: 1b 범위에서 반복 이륙(첫 항목이 아닌 TAKEOFF)은 뺀다. Executor가 거부하고, 계약 문장으로 둔다(쟁점 6).
- U8: `COM_LOW_BAT_ACT`를 계약 SITL 파라미터 표에 넣어 2(Land)로 고정한다.
- U9: `RTL_RETURN_ALT`는 미션 고도에 맞춘다. 1b는 순항 고도 5 m, `RTL_RETURN_ALT` 10 m다(쟁점 9).
- U10: 범위 문구는 표적을 "`config/fleet.yaml`에 적은 스크립트 궤적을 시뮬레이션 시간에 맞춰 따르는 점 표적"으로 좁히고, "표적 생산자는 `TargetState` 계약 뒤에서 교체할 수 있고 Gazebo 기반 생산자는 확장 항목"을 함께 적는다. 문구 초안은 "문서 반영 목록"에 있다.
- U11: CI `sitl` job의 시간 목표는 15분이고 F1, F2, F3을 모두 PR CI에 둔다. 넘으면 겹치는 비행 구간 -> 순회 waypoint 수 -> Hold 유지 시간 순으로 줄인다(U15). 그래도 넘으면 측정값과 함께 사용자에게 올린다. 판정 기준을 느슨하게 해서 줄이지 않는다.
- U12: 정답 pose(`/sim/` 토픽)를 SITL 실행의 기록물(MCAP)에 함께 기록한다. 실기체 기록물에는 없고 그때 판정은 계약 부분만 돈다. 효력은 Phase 2의 기록 대상 결정부터이고 1b 구현은 판정 코드를 계약 부분과 정답 부분으로 나누는 것까지다.
- U13: roadmap 1b 목표("YAML 미션 하나로 이륙 -> 웨이포인트 순회 -> 표적 접근 -> 복귀, 착륙")를 그대로 덮는 합친 미션 시나리오 F4(`[TAKEOFF, GOTO x N, TRACK_ENTITY, RTL]`)를 더한다. F1-F3은 경계 상황(공중 종료, 공중 시작) 검증용으로 남긴다. CI `sitl` job이 15분을 넘을 때 줄이는 순서는 U15다.
- U14: waypoint 판정 반경은 1 m(roadmap 1b 4번)를 유지한다. 시험 미션의 `acceptance_radius_m`은 `1 m - b` 이하로 둔다(쟁점 5).
- U15: CI `sitl` job이 15분을 넘으면 겹치는 비행 구간 -> 순회 waypoint 수 -> Hold 유지 시간 순으로 줄인다. 겹치는 비행 구간은 F1과 F4의 순회처럼 같은 판정을 두 비행이 보는 부분이다. F2의 공중 종료와 F3의 공중 시작은 빼지 않는다.
- U16: `docs-for-agent/file-ownership.md`의 소유자는 architect다.

## 결정 요약

| 쟁점 | 결정 | 1a 고정 계약 영향 | 상태 |
| --- | --- | --- | --- |
| 1. 표적 생산 경로 | 어댑터가 `fleet.yaml`의 궤적 정의에서 계산한다. Gazebo Actor는 같은 정의로 생성하는 화면 확인용. 구간 속도 상한 수평 5 m/s, 수직 1 m/s | 없음(`TargetState`는 1b 고정) | 확정 |
| 2. 월드, 원점, bridge | `world.template`에서 월드 SDF를 생성(fleet schema 2). 원점은 SDF로만. 템플릿의 월드 직속 `<plugin>`과 `<include>` 거부. bridge는 명령행 인자 `/clock` 하나 | 없음 | 확정 |
| 3. 표적 어댑터와 `TargetState` 발행 | Python(rclpy) 노드, 별도 compose 서비스 `targets`. params 평탄화, 표시 파일 healthcheck | 공통 규칙 "이름과 식별자"의 Python 조립 위치 | 확정 |
| 4. 원점 이동 변환 | gz와 PX4의 식을 그대로 재현하는 사슬(`idsim_common::geo`). core에는 `FramePort`로 주입. 기준 유효 술어에 `ref_alt != 0.0` | 없음 | 확정 |
| 5. 판정 입력과 임계값 | 정답 pose는 `sim-oracle`이 낸 base_link pose. 도달 판정 반경 1 m(U14), 시험 미션 반경 `1 m - b`. b는 R2의 정규 허용한계(부팅 30회 이상), `R_home`은 R4의 Rayleigh 허용한계 | 없음 | 확정 |
| 6. 항목 순서 규칙 | "TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막에만"을 계약으로 | 1a 임시 제한 문장을 계약 문장으로 | 확정 |
| 7. 공중 시작 미션 | Hold이고 failsafe가 아닌 공중 ARMED 기체만 받는다. 감시는 P3부터, 첫 OFFBOARD 표본 전의 AUTO_LOITER 면제는 순위 7, 8에만. P4에서 먼저 본 OFFBOARD는 MODE_SWITCH_FAILED | 준비 단계, 발행 규칙, 감시 시작, reason "나오는 곳", "끝난 뒤 기체 상태"의 준비 단계 MODE_SWITCH_FAILED 행 | 확정 |
| 8. GOTO, TRACK_ENTITY | 도달은 서로 다른 위치 표본 3개 연속. TRACK_ENTITY는 표적 속도를 feedforward로 싣는다. `target_fresh_age` 0.1 s, `target_timeout` 1.0 s. float32에 실을 수 없는 값은 `FramePort`가 값 없음으로 거른다. GOTO `position`과 TRACK_ENTITY `offset`의 성분은 절댓값 1e6 m 이하 | "정리"와 "정리의 상한"의 원인 목록, "종료의 충돌 규칙", feedback의 `PHASE_EXECUTING`, "Offboard setpoint"의 `velocity`, "좌표계"의 원점 이동 | 확정 |
| 9. RTL과 SITL 파라미터 | 모드 명령 항목. 실패 fallback은 Land(RTL 실패의 정리. Hold를 거치지 않는다). RTL 중 취소는 Hold. 파라미터 일곱을 계약 표에 더한다. F3, F4 RTL `timeout` 60 s | SITL 파라미터 표, "LAND 항목" 절, "정리"와 "정리의 상한"의 원인 목록, "끝난 뒤 기체 상태"의 MODE_SWITCH_FAILED와 ITEM_TIMEOUT 행, "용어"의 명령과 확인 대상 | 확정 |
| 10. 공중에서 끝나는 미션 | 공중 Hold 3회 확인이면 SUCCEEDED. 지상에서는 세지 않고, 종료 단계의 어느 분기에서든 지상 DISARMED 3회면 SUCCEEDED | "끝난 뒤 기체 상태" SUCCEEDED 행, "정리의 상한"의 원인과 결과, feedback의 `PHASE_EXECUTING` | 확정 |
| 11. 지상 취소의 disarm 확인 | 1a 규칙(tick 조건, timestamp 조건, 3회 연속)을 유지한다. 처리 전 표본의 창은 arm 처리 전(폭 W_arm)이고 publish 간격 두 개보다 좁다. Phase 2 다중 스택 부하에서 다시 본다 | "시간 기준" 예외 문장의 근거 서술(사실 갱신. 규칙은 그대로) | 확정 |
| 12. snapshot과 core 구조 | 헤더 추가는 한 PR, px4-engineer 조건부 승인 네 조건과 `SetpointOut` 속도. 지상 arm 진입의 arm 순서 불변식. 상태기 PR은 여섯(S1-S6)이고 goal 접수가 받는 미션은 B10까지 1a 그대로. S마다 로컬 `run_sitl.sh`로 1a 동작을 본다 | 준비 단계 표의 Offboard 전환 행((t)) | 확정 |
| 13. 전이 덮음 | 사건 꼬리표 계측을 동작 무변경 PR로 먼저. 칸 목록 파일과 관측 집합 비교 | 없음 | 확정 |
| 14. YAML 로더, `idsim_common` 공개 | 로더는 `idsim_mission` 안의 Python 모듈. `position_setpoint`에 속도 feedforward 인자 | 없음 | 확정 |
| 15. 시나리오와 CI 시간 | B(1b 무효 사례로 교체), C, A, D, F1, F2, F3, F4(합친 미션, U13), T. 15분 목표 | 없음 | 확정 |
| 16. 다대 원점 판정 | `stack.json`의 기체별 `expect_gps`(base_link 기준)를 생성기가 계산하고 `check_px4`는 비교만 | 없음 | 확정 |
| 17. viz 확인 | Actor 월드에 `gz-gui`를 붙이는 수동 확인 1회 | 없음 | 확정 |

## 쟁점 1. 표적 상태 생산 경로

결정
- 표적 어댑터가 `config/fleet.yaml`의 `targets` 궤적 정의를 노드 시계(ROS 시각) t에서 평가해 `TargetState`를 낸다. 월드 SDF의 Actor는 같은 정의에서 생성하는 화면 확인용이다. 표적 위치의 원천은 Gazebo가 아니다(U10).
- 궤적 정의의 유일한 출처는 `fleet.yaml`의 `targets`다. 생성기가 정규화한 값을 월드 SDF의 Actor, 어댑터 params(`params/targets.yaml`, 쟁점 3의 평탄화 형식, 실수는 모두 소수점 표기), `stack.json`의 `targets` 셋에 낸다. 어댑터는 `fleet.yaml`을 읽지 않는다.
- 스키마(devops-engineer 소유, sim-engineer 접점 검토): `targets[]`의 `id`(`target_id` 규칙, 중복 금지), `start_s`(그 전에는 첫 waypoint에 정지), `loop`(true면 처음과 끝 waypoint가 같아야 한다), `waypoints[]`의 `{t, x, y, z}`(world ENU m, t는 `start_s` 기준 s, 첫 t는 0, 엄격히 증가, 2개 이상).
- 보간은 구간 직선이고 속도는 구간 기울기다(`velocity_valid` true, 정지 구간은 0 벡터). waypoint 시각 정확히에서는 다음 구간 값이다. `loop` false면 끝난 뒤 마지막 점에 정지한다.
- 네 key(`id`, `start_s`, `loop`, `waypoints`)와 waypoint의 `{t, x, y, z}`는 모두 필수이고 기본값이 없다. 상한은 표적 32, 표적당 waypoint 256, 모든 표적의 궤적 길이(마지막 waypoint의 `t`를 ms로 반올림한 값)의 합 2400 s, `start_s` 86400 s, 좌표 |x|, |y| 10000 m와 z 1000 m다. 궤적 길이에는 `start_s`와 Actor의 끝 정지 꼬리를 넣지 않고, 정지 구간은 움직이는 구간과 똑같이 센다. 표적 하나의 길이 상한은 합 상한과 같다(따로 두지 않는다). 길이 합과 좌표의 상한은 `TargetState` 계약이 아니라 Gazebo 월드를 생성하는 쪽의 규칙이다(Actor 표본의 비용과 출력 크기를 묶는다. 좌표 상한은 변환 정확도의 보장이 아니다). `embedded` 변형은 `targets`를 경고와 함께 무시하지만 검증은 변형과 무관하게 한다.
- 시간 규칙은 ms로 반올림한 시각에서 판정한다(`T = round(t x 1000)`, 여유값 없음). 인접 waypoint는 `T` 차가 100 이상이어야 하고(오류에 두 `T` 값을 함께 낸다), `T`가 2400000을 넘는 waypoint는 거부하며, 길이의 합은 표적마다의 마지막 `T`를 더해 2400000 이하여야 한다. 세 규칙의 상수와 영역이 같다. 합에는 waypoint 형식이 맞고 `t`가 엄격히 증가하며 `T`가 2400000을 넘는 waypoint가 없는 표적을 모두 넣는다(속도나 시작 위치 같은 다른 규칙으로 거부된 표적도 넣는다). 합에서 빠진 표적을 고친 뒤 합 오류가 새로 나올 수 있다. 합 오류는 합, 상한, 합에 넣은 표적 모두의 길이를 `targets[i]` 표기로 fleet 파일 순서대로 낸다.
- 생성기 거부 조건: id 형식과 중복, waypoint 2개 미만, t 비증가, 첫 t가 0이 아님, `loop`인데 처음과 끝이 다름, z < 0, 구간 속도 상한 초과(수평 5 m/s, 수직 성분 1 m/s), t=0 위치가 기체 스폰 지점과 수평 2 m 안, ms로 반올림한 인접 waypoint 시각의 차가 100 ms 미만, ms로 반올림한 시각이 2400000 ms를 넘는 waypoint, 좌표 범위 초과(모든 waypoint), `start_s` 상한 초과, 궤적 길이의 합 초과, `id`가 기체 모델 이름(`x500_N` 형식)이나 템플릿 최상위 `<model>`, `<actor>`, `<light>` 이름과 같음(Actor 이름이 `target_id`라 충돌하면 oracle과 GUI가 다른 엔티티를 본다), 개수 상한 초과.
- Gazebo Actor는 spline 보간이라 waypoint 사이에서 `TargetState`와 어긋난다. 이 차이는 `TargetState` 계약에 적지 않는다(`TargetState`는 시뮬레이터를 모른다). `docs/architecture.md`의 시뮬레이션 레이어 설명과 `idsim_sim` README에 "Gazebo 화면의 Actor 위치는 참고용"으로 적는다. 생성기는 Actor waypoint를 균일 간격의 표본으로 촘촘히 낸다(구간마다 같은 간격으로 나눈다. 간격의 상한은 sim-engineer가 M4의 육안 확인으로 정하고 잠정값은 250 ms다). 간격 상한은 200 ms 이상에서만 고른다. 간격이나 길이 합의 상한을 바꾸면 단위 테스트의 표본 예산 단정과 인접 표본 100 ms 단정이 깨져 Gazebo 쪽 비용을 다시 보게 된다. 표본 시각은 정수 ms로 계산해 소수 3자리로 쓴다. `<loop>`는 항상 true이고 `<script>`는 항상 있다. `loop` false 표적은 마지막 waypoint 뒤에 같은 위치의 두 점(250 ms 뒤, 86400 s 뒤)을 표본으로 나누지 않고 그대로 더해 정지로 나타낸다. 그래서 화면의 Actor는 `start_s` + 궤적 길이 + 86400 s에 처음 위치로 돌아가고 `TargetState`는 마지막 점에 머문다. `start_s` 전에는 둘 다 첫 waypoint에 있다. 맨 처음 렌더링 한 장에서는 Actor가 월드 원점에 보인다. `loop` true 표적은 Actor의 주기가 ms로 잘린 값이라 한 바퀴마다 최대 약 1.5 ms씩 `TargetState`와 위상이 어긋난다. 여기 적은 것은 알려진 차이이고 전부가 아닐 수 있다. 모두 화면 참고용의 차이다.

근거
- [소스] 스크립트 궤적은 렌더링 쪽(`SceneManager`)에서만 평가되고 서버 ECM에는 궤적을 평가하는 system이 없다. 서버 쪽 system을 만드는 것은 같은 계산을 C++로 다시 하는 것이고 얻는 것은 GUI와의 일치뿐이다.
- 소비자(Executor, 판정, 기록)에게 정본은 `TargetState`이고 원천은 보이지 않는다. stamp와 값이 같은 함수에서 나와 시간 정합이 정의로 성립한다. 생산자를 바꿔도 `TargetState`, 토픽, `targets` 스키마는 그대로이고 어댑터의 입력만 바뀐다.
- 속도 상한: 수평 5 m/s는 x500 자동 모드 순항 속도(`MPC_XY_CRUISE`)와 같고, TRACK_ENTITY의 feedforward(쟁점 8) 5 m/s에 위치 P 항을 더해도 `MPC_XY_VEL_MAX` 12 m/s 포화까지 여유가 있다([추정]. P 항의 크기는 추종 오차에 달려 있고 재지 않았다). 수직 1 m/s는 하강 한계 `MPC_Z_VEL_MAX_DN` 1.5 m/s에 여유를 둔 값이다([소스] `mc_pos_control` 파라미터 기본값, x500 airframe은 덮지 않는다).
- Actor 표본의 비용은 이동 여부와 무관하게 월드 전체 표본 수에 비례한다. [실측] Gazebo 서버의 상주 메모리가 표본당 약 7.2 KB다. [소스] GUI는 state 메시지마다 Actor별 궤적을 복사해 프레임 비용이 표본 수에 선형이다. 어댑터는 waypoint만 쓰므로 궤적 길이와 무관하다. 합 2400 s의 최악은 17,856 표본이다. 2400 s는 [추정]이고(1b와 Phase 3의 수요 추정의 2배를 넘는다) 올리는 쪽이 호환된다. `start_s` 86400 s와 좌표 10000 m, 1000 m도 [추정]이다(쓸 만한 값을 막지 않으면서 출력 크기와 시각 변환을 묶는 값).
- [소스] gz-sim은 waypoint 시각을 ms 정수로 잘라 map의 key로 쓰므로 1 ms 간격의 두 시각은 합쳐질 수 있다. [계산] 궤적 길이 상한 안(0-3000 s)에서 2 ms 이상의 간격은 합쳐지지 않는다. 100 ms는 그 50배다([추정]. 내리는 쪽이 호환된다).
- [실측, 소스] gz-sim 8.15.0의 렌더링은 `<loop>`가 false인 Actor에서 `delay_start`가 0이면 끝나지 않는 루프에 빠지고, 0보다 크면 첫 waypoint에서 움직이지 않는다(`SceneManager.cc`의 `CreateActor`와 `ActorTrajectoryAt`). [소스] `<script>`가 없는 Actor도 궤적 길이가 0이라 같은 루프에 걸린다. 그래서 `<loop>`를 true로 고정하고 `<script>`를 항상 넣으며 정지를 꼬리로 나타낸다.
- [소스] `delay_start`와 script 시각은 int ms로 바뀌어 약 2147483 s에서 넘친다. `start_s` 86400 s와 최대 script 시각 88800 s(길이 2400 s + 꼬리 86400 s)는 그 안이다.
- [수치 계산] 표본 간격을 구간 안에서 바꾸면 spline의 접선이 표본 순번 기준이라 같은 표본 수의 균일 간격보다 화면 오차가 크다.

## 쟁점 2. 월드 SDF, 원점, bridge, 커스텀 모델

결정
- 손으로 쓰는 월드는 템플릿 하나 `ros_ws/src/idsim_sim/worlds/idsim_base.sdf`다(PX4 `default.sdf`의 physics, scene, light, ground를 출처 주석과 함께 옮긴다. 월드 직속 `<plugin>`, `<spherical_coordinates>`, `<actor>`는 넣지 않는다). 생성기가 이 템플릿에 `<world name>`, `<spherical_coordinates>`(`world.origin`, heading 0, ENU), 표적마다 `<actor>`를 넣어 `artifacts/runs/<실행 id>/world/<name>.sdf`로 쓰고 gazebo 서비스의 `/opt/idsim/world`에 읽기 전용으로 마운트한다(`IDSIM_WORLD_FILE`이 그 파일을 가리킨다). 표적이 없어도 같은 경로로 생성한다. embedded 변형은 PX4가 이미지의 `/opt/px4-gz/worlds/<name>.sdf`를 직접 열므로 생성하지 않는다. 생성은 표준 라이브러리 `xml.etree`로 하고(출처 주석 보존), 출력을 다시 파싱해 `<spherical_coordinates>` 정확히 하나, 월드 직속 `<plugin>` 0, `<actor>` 이름 집합 = 표적 id 집합, `dynamic_pose` 문자열 없음을 단정한다. Actor마다 `<script>`가 있고 `<loop>`가 true인 것, `plugin`, `skin`, `animation`, `collision`이 없는 것, 표본 시각이 0에서 시작해 엄격히 증가하는 정수 ms인 것, 원래 waypoint가 모두 들어 있는 것, 인접 표본 시각 차가 100 ms 이상이고 간격 상한 이하인 것(끝 정지 꼬리의 마지막 구간은 예외), `loop` false 표적은 표본이 궤적 부분보다 정확히 2개 많고 마지막 세 점의 위치가 같으며 마지막 시각이 마지막 waypoint + 86400 s인 것도 단정한다. Actor를 만들기 전에 궤적 길이의 합을 다시 본다.
- 템플릿은 `PX4_GZ_MODELS_REF`의 `default.sdf` 사본이므로 원본과의 대조를 둘로 둔다(둘 다 B3 PR). (가) 스모크 images(S0)의 월드 템플릿 대조(devops-engineer 구현, 비교 규칙은 sim-engineer 검토): sim-base 이미지의 `/opt/px4-gz/worlds/default.sdf`와 템플릿의 월드 직속 요소를 XML 정규화(주석, 바깥 공백, text 앞뒤 공백, BOM 무시)해 순서까지 비교한다. 비교에서 빼는 것은 원본의 `<spherical_coordinates>`와 `<world>`의 `name` 속성뿐이다. 원본에 월드 직속 `<plugin>`, `<include>`, `<actor>`가 있으면 빼고 넘어가지 않고 "템플릿에 옮길 수 없는 요소"로 따로 실패한다(sim-engineer가 판단한다). 의도적으로 원본과 다르게 둘 요소가 생기면 그 요소를 검사의 제외 목록에 이유와 함께 더한다(지금은 없다). (나) 템플릿 출처 주석의 ref 줄(정해진 형식 한 줄)이 `docker/versions.env`의 `PX4_GZ_MODELS_REF`와 같음을 `tests/tools/`의 단위 테스트가 본다(devops-engineer, 주석 형식은 sim-engineer). 주석의 ref는 "이 ref의 원본과 대조했다"는 표시이고, ref를 올리고 템플릿을 다시 대조하지 않은 PR이 lint에서 실패한다.
- `world.origin`은 필수다. 생성기가 누락을 거부한다.
- 템플릿은 `world.template`(저장소 기준 상대 경로. 절대 경로와 `..` 거부, `.sdf`로 끝남)으로 고르고 `world.file`은 없앤다. 옛 key는 "모르는 key"로 실패하고 오류 메시지가 새 key를 알려 준다. `fleet.yaml`의 `schema`는 2로 올리고 2만 받는다(이행 기간 없이 한 PR에서 `config/fleet.yaml`과 fixture를 모두 바꾼다). `stack.json`은 `schema` 1을 유지하고 생성기 판 5(`GENERATOR_VERSION` 5)에서 key를 더한다: `inputs.world_template`(`{path, sha256}`), `world.template`, `world.file`, `targets`, `services.targets`, `services.sim_oracle`, `vehicles[].expect_gps`. 판 5부터 key는 항상 있어야 하고 값만 null이 될 수 있다(로더 `tests/support/stack.py`의 판 5 명세). `stack.json`의 `world.file`은 fleet의 옛 key와 달리 생성된 월드의 실행 디렉터리 기준 상대 경로(예: `world/default.sdf`)이고 월드를 생성하지 않는 embedded만 null이다. `services.targets`는 `targets`가 빈 목록이면 null이고 비어 있지 않으면 null일 수 없다. `services.sim_oracle`은 서비스가 없으면 null이다(B7 전과 embedded. B7부터 standalone은 `sim-oracle`). `vehicles[].expect_gps`는 embedded만 null이다.
- golden(4종)은 저장소의 실제 템플릿이 아니라 fixture 전용 템플릿 `tests/fixtures/gen_compose/world_template.sdf`를 쓴다(실제 템플릿을 고칠 때 생성기 golden이 깨지지 않게). standalone fixture 셋은 생성된 월드 SDF(`world/default.sdf`)도 golden에 둔다. `targets` 스키마가 B6 몫이므로 그 전에는 모든 fixture의 `targets`가 빈 목록이고, B6에서 3대-k0 fixture에 표적 둘(`loop` true와 false, `start_s` 0과 0 초과, 정수로 적은 좌표 하나)을 넣는다. 실제 템플릿과 `config/fleet.yaml`은 golden이 아닌 단위 테스트 하나가 검증, 생성, 출력 단정까지 통과함을 본다.
- 원점은 SDF로만 넣는다. `gz_server.sh`에는 런타임 `set_spherical_coordinates` 호출과 표시 파일 `origin_set`이 없고, 생성기는 gazebo 서비스에 `IDSIM_ORIGIN_*`를 주지 않는다(불변식이 부재를 단정한다). 월드 생성, `IDSIM_ORIGIN_*` 전달 제거, 런타임 호출 제거는 한 PR(B3)에 있다. [실측] M5: 원점을 SDF로만 넣은 스택에서 스모크 S2의 `sensor_gps` 판정이 통과한다.
- wrapper는 서버를 띄우기 전에 `<world name>`이 `IDSIM_WORLD_NAME`과 같은지와 `<spherical_coordinates>`가 정확히 하나인지만 줄 단위 grep으로 본다(원점 값은 보지 않는다). 그래서 생성된 SDF는 `<world` 여는 태그와 `name=`이 한 줄에 있고 주석 안에 `<world name=`이나 `<spherical_coordinates` 문자열이 없어야 하며, 생성기의 출력 단정이 같은 조건을 본다. 준비 파일 `/tmp/idsim/ready`는 `scene/info` 응답 직후에 남기고 healthcheck 명령은 그대로다.
- `tools/sim_stack.sh up`은 아무것도 올리기 전에 `stack.json`의 `world.file`이 null이 아니면 그 파일이 있고 `<spherical_coordinates>`가 정확히 하나인지 본다.
- 일치 검사는 하지 않고 구성으로 보장한다. 생성기 단위 테스트가 생성된 SDF의 위도, 경도, 고도, heading 0, ENU가 `fleet.yaml` 값과 같음을 단정한다. 실제 적용은 스모크 S2가 판정한다.
- 생성기는 템플릿에서 `<world>`가 정확히 하나가 아니거나 월드 직속 `<plugin>`(있으면 `server.idsim.config`가 무시된다), `<spherical_coordinates>`, `<actor>`, `<include>`(include된 모델의 월드 수준 plugin은 생성기가 볼 수 없다)가 있으면 거부한다. Actor 안에도 `<plugin>`을 넣지 않는다.
- bridge: 1b의 bridge 토픽은 `/clock`(gz -> ROS) 하나다. 표적 pose와 정답 pose는 bridge를 거치지 않는다. 형식은 지금의 명령행 인자 하나(`/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock`)를 유지한다. 생성기 단위 테스트가 bridge 토픽 인자 집합이 정확히 그 하나임과, compose와 생성된 SDF 어디에도 `dynamic_pose`가 없음을 단정한다. 같은 금지 검사를 `sim-oracle`의 구독 토픽에도 적용한다(쟁점 5, `idsim_sim` 단위 테스트). `gui.config`는 plugin 목록을 고정한다. `idsim_sim` 단위 테스트(B6, sim-engineer. 패키지의 `test/`가 B6의 ament_python 전환에서 생긴다)가 `ros_ws/src/idsim_sim/config/gui.config`의 `<plugin filename>` 목록이 테스트 안의 고정 목록(gz-sim8 기본 `gui.config`에서 WorldControl을 빼고 GridConfig를 더한 것)과 정확히 같고 파일에 `dynamic_pose` 문자열이 없음을 본다. 설정 파일 수준의 방어이고, 실행 중 GUI 메뉴로 plugin을 더하거나 `IDSIM_GUI_CONFIG`로 다른 설정을 주는 것은 막지 않는다(쟁점 17의 운영 문서 문장이 맡는다).
- bridge healthcheck는 `/clock` 1회 수신 그대로다.
- 커스텀 모델: 모델 파일을 두지 않는다. [실측] M1(headless ogre2 카메라 센서 영상): `<skin>` 없이 `<link>` visual만 가진 Actor가 렌더링되고 script 궤적대로 움직인다. [소스] GUI도 같은 `RenderUtil`/`SceneManager::CreateActor` 경로를 쓴다. GUI와 ogre 엔진에서의 확인은 M4에서 한다. `GZ_SIM_RESOURCE_PATH`는 바꾸지 않는다.

근거
- Actor 궤적과 원점을 SDF에 손으로 다시 적으면 출처가 둘이 된다.
- 원점이 월드 로드 때 들어가면 PX4 첫 GNSS fix보다 늦을 수 없다. 런타임 호출은 대개 앞서지만 순서가 구조로 보장되지 않는다([추정]). SDF만으로 원점이 적용되는 것은 M5로 확인했다([실측]).
- 표적과 정답 pose가 bridge를 거치지 않으므로 bridge 설정을 생성 파일로 옮길 이유가 없다.
- 템플릿 대조를 둘로 나눈 이유: 원본은 이미지 안에만 있어 내용 대조는 이미지가 있는 S0에서만 할 수 있는데, S0은 CI에서 돌지 않는다. ref 줄 대조는 이미지 없이 lint에서 PR마다 돌아 ref를 올리는 사람이 S0을 돌리게 만든다. sim-base 빌드 단계에 두면 템플릿이 sim-base key의 입력이 되어 템플릿을 고칠 때마다 sim-base와 px4 이미지가 다시 빌드된다. [실측] 템플릿의 월드 직속 요소 일곱(physics, gravity, magnetic_field, atmosphere, scene, ground_plane 모델, sunUTC light)이 `idsim/sim-base:local`의 원본에서 `<spherical_coordinates>`를 뺀 것과 순서까지 같고, 원본에는 `<plugin>`, `<include>`, `<actor>`가 없다.
- [실측] sim-base 이미지(libgz-sim8 8.15.0, libgz-gui8 8.4.0)의 GUI plugin 바이너리에서 `dynamic_pose` 문자열은 발행 쪽인 scene-broadcaster system에만 있고 `gui.config`의 plugin 어느 것에도 없다. 그래서 방어의 본체는 목록 고정(설정의 `<topic>`으로 구독 대상을 받는 TopicEcho, TopicViewer, Plotting 계열이 들어오지 못하게 한다)이고 문자열 단정은 보조다. B3 월드에는 Actor가 없어 이 테스트가 B6에 있어도 그 사이의 위험은 없다.
- `world.file`의 의미를 "컨테이너 안 완성 월드"에서 "저장소 안 템플릿"으로 바꾸면 옛 값이 다른 경로로 조용히 해석된다. 이름을 바꾸면 옛 파일이 바로 실패한다. `stack.json`은 바뀌는 것이 모두 key 추가라 지금의 판 문턱 규칙으로 충분하고, `schema`를 올리면 읽는 쪽 셋이 함께 바뀌는데 얻는 것이 없다.
- 판 5부터 key를 생략하지 못하게 하는 것은 로더가 "생성기가 그 key를 내지 않았다"(옛 판이거나 생성기 결함)와 "값이 없다"(embedded, 표적 없음)를 구분하게 하려는 것이다. 없는 key를 null로 읽으면 key 이름의 오타나 누락이 "해당 없음"으로 통과한다.
- `sim_stack.sh up`의 사전 검사는 월드 파일이 없거나 원점이 빠진 실행 디렉터리를 컨테이너를 올리기 전에 호스트에서 실패시킨다. wrapper의 검사만 있으면 같은 결함이 앞 단계 서비스를 올린 뒤 gazebo 컨테이너의 종료로 드러나고 원인은 컨테이너 로그에 남는다. wrapper의 검사는 `sim_stack.sh`를 거치지 않고 compose를 직접 올리는 경로를 위해 그대로 둔다.

## 쟁점 3. 표적 어댑터 노드와 TargetState 발행

결정
- 언어: Python(rclpy). `docs/architecture.md` 기술 스택의 "도구, 테스트, 어댑터 Python"을 따른다.
- 패키지: `ros_ws/src/idsim_sim`을 ament_python 패키지로 만든다(`package.xml` 신설, 의존 `rclpy`, `idsim_interfaces`). `scripts/`의 셸 wrapper와 `sim_oracle.py`(쟁점 5)는 설치 대상이 아니고 지금처럼 마운트해서 쓴다.
- 구조: 노드 하나가 모든 표적을 발행한다(표적별 publisher). 궤적 평가와 stamp 단조 규칙("직전 stamp, 지금 t -> 발행 여부")은 rclpy를 import하지 않는 순수 함수이고, 단위 테스트가 같은 평가 함수를 부르지 않고 손으로 계산한 golden 표와 비교한다(표의 위치는 test-engineer가 정한다).
- params는 평탄화한다: `target_ids`(문자열 배열)와 표적마다 `targets.<id>.start_s`, `targets.<id>.loop`, `targets.<id>.t`, `.x`, `.y`, `.z`(같은 길이의 double 배열). ROS 2 파라미터가 구조체 배열을 담지 못하기 때문이다. 생성기가 이 형식으로 내고(`/**: ros__parameters:` 아래 `use_sim_time: true`와 위 이름들. 실수는 모두 소수점 표기로 써서 `double_array` 선언과 타입이 맞게 한다), 노드는 배열 길이 불일치와 누락에서 시작을 거부한다.
- 실행 위치: 별도 compose 서비스 `targets`(ros-ws 이미지, `depends_on: bridge` healthy, `init: true`, `stop_signal: SIGINT`). 생성기가 다른 ros-ws 서비스와 같은 함수로 만들어 `network_mode: host`, `RMW_IMPLEMENTATION`, `CYCLONEDDS_URI`, `ROS_DOMAIN_ID`, 호스트 uid:gid, 저장소 마운트가 같다. 명령은 `ros2 run idsim_sim <실행 이름> --ros-args --params-file <실행 디렉터리>/params/targets.yaml`이고 실행 이름은 생성기 상수 하나다. `targets`가 비면 서비스, `params/targets.yaml`, `services.targets`를 만들지 않는다.
- 기동 단계: `startup.node_stages = [[ops-1 .. ops-N, targets(있으면), sim-oracle]]` 한 단계이고 셋을 병렬로 올린다. `ops-N`은 `targets`를 기다리지 않는다. 스모크(`--infra-only`)에서는 둘 다 뜨지 않는다(두 서비스의 실패가 스모크 판정을 흐리지 않게). `runner.depends_on`은 `ops-N` 전부, `targets`(있으면), `sim-oracle`이다. `targets`가 있으면 `sim_stack.sh up`의 사전 검사가 `ros_ws/install/idsim_sim`도 본다.
- healthcheck: 표시 파일. 노드는 시작 때 `/tmp/idsim/targets_ready`를 지우고, 모든 표적이 stamp > 0으로 한 번 이상 발행된 순간 임시 파일에 쓴 뒤 rename으로 원자적으로 만든다(내용은 표적 id와 각 첫 stamp). healthcheck는 `test -f /tmp/idsim/targets_ready`다. 설정 오류(`use_sim_time` false, params 누락, id 형식)는 0이 아닌 종료 코드로 끝낸다. 이것은 "한 번 이상 발행"만 보고, 발행 중단은 R3 기록과 Executor의 `target_timeout`이 맡는다.
- 토픽: 절대 이름 `/targets/<target_id>/state`. 메시지 상수 `TOPIC_PREFIX`, `TOPIC_SUFFIX`(rosidl Python 클래스 상수)로 조립한다. 노드 네임스페이스는 기체 네임스페이스가 아니다.
- QoS: 계약 상태 행(발행 RELIABLE, VOLATILE). 구현 값 KEEP_LAST 5. Python은 `contract_qos.hpp`를 쓰지 못하므로 값을 다시 적고, 통합 테스트가 그래프의 발행자 QoS를 계약과 대조한다.
- stamp: timer 콜백에서 읽은 노드 시계 시각 t이고 위치와 속도는 같은 t에서 계산한다. 0을 내지 않는다. 표적마다 직전 발행 stamp보다 큰 t에서만 발행한다(`/clock` 정지나 역행에서 발행하지 않는다. 역행은 오류 로그를 남긴다). `use_sim_time` false이면 시작을 거부한다. 주기는 params(기본 20 Hz, 계약 아님).
- 이름 조립과 id 검증: 어댑터 패키지 안에 조립과 `target_id` 정규식 검증 함수를 두고 `tests/support`와 같은 사례 표로 단위 테스트한다. `docs/interface.md` "이름과 식별자"의 "Python은 `tests/support`가 한다"를 "판정은 `tests/support`, 발행은 표적 어댑터"로 고친다(1a 고정 계약 영향 (j)).
- 원점: 어댑터는 원점을 모른다. 출력은 world ENU뿐이다. architecture.md의 "운용 노드와 표적 어댑터는 같은 값을 params로 받는다"에서 표적 어댑터를 뺀다.
- replay 프로필에서는 `targets`와 `sim-oracle`을 띄우지 않는다(발행자가 둘이 되거나 Gazebo가 없다).

근거
- 별도 서비스로 두면 bridge healthcheck가 `/clock`만으로 남고, 표적 생산 실패가 기체 노드 기동을 막지 않으며, 소실 시험에서 서비스 하나만 멈출 수 있다.
- stamp 규칙은 계약("유효한 ROS 시각, 0이 아님, 단조 증가")을 생산자 쪽에서 구조로 지키는 방법이다. 첫 `/clock` 전에는 `now()`가 0이라 같은 규칙이 막는다.
- 표시 파일은 healthcheck 한 번에 프로세스 생성이 `test` 하나다. `ros2 topic echo --once`는 표적 수만큼 CLI 기동과 discovery를 치른다. stamp > 0 조건이 `/clock` 수신을 함의하므로 판정 조건 "모든 표적이 `/clock` 시작 뒤 한 번 이상 발행됨"과 같다.

## 쟁점 4. 원점 이동 변환

결정
- 입력: params의 `world.origin`(생성기가 `ops-N` params에 `world.origin.lat`, `lon`, `alt`를 싣는다. Executor는 configure에서 누락을 거부한다. embedded 변형에는 `ops-N` 서비스와 params 파일이 없으므로(쟁점 2. `/clock` bridge가 없어 `use_sim_time` 노드를 올릴 수 없다) 이 거부가 embedded에 새 제약을 더하지 않는다. embedded는 진단용이고 운용 노드를 올리는 변형이 아니다)과 `vehicle_local_position`의 `ref_lat`, `ref_lon`, `ref_alt`. 스폰 pose는 입력이 아니다.
- 기준 유효 술어: `xy_global`과 `z_global`이 true이고, `ref_lat`, `ref_lon`, `ref_alt`가 유한하며, `ref_alt`가 정확히 0.0이 아니다. 하나라도 어긋나면 변환은 값 없음이다. PX4는 고도 원점이 없을 때 `ref_alt`에 NaN이 아니라 0을 내고 `z_global`은 위경도 원점만 본다. 이 술어는 기준을 읽는 px4 어댑터 함수에 두고 snapshot 헤더 주석의 대응 표에 적는다.
- 기준은 그 tick의 `Snapshot.position`과 같은 `vehicle_local_position` 표본에서 읽는다. 노드가 callback의 최신 표본 하나에서 둘을 함께 만든다(원점이 바뀌는 tick에 위치와 setpoint가 서로 다른 원점에 있지 않게).
- 사슬: world ENU 점 -> WGS84(gz `SphericalCoordinates::PositionTransform(p, LOCAL2, SPHERICAL)`과 같은 식, 원점 `world.origin`, 타원체 고) -> 기체 로컬 NED(PX4 `MapProjection`의 식, 기준 `ref_*`, 고도는 `ref_alt`와의 차). 평행 이동 근사를 쓰지 않는다. 고도는 gz가 낸 타원체 고를 그대로 쓰고 geoid 보정을 하지 않는다. 역방향(로컬 NED -> world ENU)도 같이 만들고 왕복 테스트로 묶는다(Phase 2 Collector가 쓴다).
- 벡터(속도)는 기준에 의존하지 않는 축 치환(ENU <-> NED)이다. 자오선 수렴과 척도 차이(0.2%)는 무시한다.
- 위치: 식은 `idsim_common::geo`(Eigen만 쓰는 순수 함수, double). 벡터 축 치환은 기존 `idsim_common` 좌표 변환 함수를 쓴다. `vehicle_local_position`에서 기준을 읽는 함수는 px4 어댑터(px4-engineer 소유). core에는 snapshot 헤더의 `FramePort`(`world_to_local` 점 변환과 `world_velocity_to_local` 벡터 변환. 기준이 무효면 점 변환은 값 없음)로 주입한다. 노드 구현은 그 tick의 기준과 params 원점으로 `geo`를 부른다.
- `FramePort` 구현(`Px4FramePort`)은 `trajectory_setpoint`(float32)에 실을 수 있는 값만 돌려준다. 점 변환은 결과의, 벡터 변환은 축 치환한 값의 성분이 하나라도 비유한이거나 float32 범위 밖이면 값 없음이다. 그래서 벡터 변환도 값 없음을 돌려줄 수 있는 형이다(헤더 변경. 속도를 처음 쓰는 쟁점 12의 S6에서 바꾸고, 점 변환의 술어는 S5에 넣는다). 술어는 `idsim_common`의 `position_setpoint`가 쓰는 것(유한하고 절댓값이 float 최댓값 이하)을 `idsim_common::px4::fits_float32`로 공개해 한 곳에 두고 둘이 함께 쓴다(쟁점 14). snapshot 헤더 머리 주석의 `FramePort` 행에 "float32에 실을 수 없는 값은 값 없음"을 술어를 넣는 PR에서 적는다. `Px4FramePort`가 값을 돌려준 점과 벡터를 `to_setpoint_messages`가 버리지 않는다는 대조 테스트를 `test/px4/`에 둔다(1e39와 float 최댓값 경계 포함). core는 float32를 모르고 값 없음만 다룬다(쟁점 8). 계약 좌표 상한(쟁점 8) 안의 미션 값은 이 술어에 걸리지 않는다. 술어는 표적 위치와 기준이 만드는 나머지 경우의 안전망이다.
- 단위 테스트: gz-math 7 `SphericalCoordinates::PositionTransform(p, LOCAL2, SPHERICAL)`(heading 0)의 값과 PX4 `MapProjection`의 알려진 값과 차등 비교한다. 기준값은 gz-math 7.7.0 Python 바인딩으로 뽑고 원문의 판(gz-math 7.7.0, PX4 v1.17.0)을 테스트 주석에 고정한다. `SphericalFromLocalPosition`과 `LOCAL`은 heading 0에서 수평을 반전하므로 기준값으로 쓰지 않는다.
- 원점 변경: 변환을 tick마다 최신 기준으로 하므로 `ref_timestamp`가 바뀌어도 따로 다시 만들 것이 없다. 비행 중 바뀌면 노드가 기준을 읽을 때 WARN 로그 한 줄을 남긴다. 사건 메시지는 더하지 않는다.
- 커스텀 월드의 `world_frame_orientation`은 생성기가 ENU로만 쓰므로 검사하지 않는다(쟁점 2의 구성 보장).

근거
- [소스] PX4 `MapProjection`은 반지름 6371 km 구면의 방위 등거리 투영이다(`geo.h` 55행, `geo.cpp` 67-112행). gz-sim 8.15.0의 NavSat은 센서의 world pose를 `gz::sim::sphericalCoordinates`로 바꾸고, `libgz-sim8`이 쓰는 gz-math 변환은 `PositionTransform` 하나다(local -> ECEF -> geodetic, WGS84 타원체). [실측] S2-a: 기체 1을 (6, -3, 0)에 스폰한 스모크 S2에서 `sensor_gps`와 `expect_gps`의 수평 오차는 최대 0.051 m다(반전이면 약 13.4 m). NavSat의 수평 변환은 LOCAL2와 같은 방향이고 반전이 없다. [실측, 계산: gz-math 7.7.0 LOCAL2와 MapProjection 식] 원점 위도 37.57도에서 world 동쪽 100 m는 PX4 로컬 99.763 m, 북쪽 100 m는 100.186 m다. 평행 이동 근사는 기체의 EKF 원점에서 100 m 떨어진 점에서 약 20 cm 틀린다.
- [소스] EKF는 자기 GNSS를 같은 투영으로 로컬로 바꾸므로(`position_fusion.cpp` 142-146행) 같은 사슬을 재현하면 척도 차이와 EKF 원점의 초기 잡음이 함께 상쇄된다. 상쇄는 "gz와 PX4가 실제로 쓰는 식을 그대로 재현한다"에서 나오므로 `geo`는 두 원문의 식을 옮기고 근사하지 않는다.
- [소스] `ref_alt`의 0 대체와 `z_global`: `estimator_interface.h` 328-330행, `EKF2.cpp` 1594-1607행. GZBridge는 NavSat 고도를 MSL과 타원체 고도에 같은 값으로 넣는다(`GZBridge.cpp` 777-778행).
- [소스] `check_core_purity.cmake`가 core에서 `idsim_common`을 금지하므로 port 주입이 "변환은 `idsim_common` 한 곳"과 core 순수성을 함께 지킨다.

## 쟁점 5. 판정 입력과 임계값

결정
- 판정 입력은 둘로 나눈다. 계약 판정은 계약 토픽과 PX4 토픽(`mission_event`, feedback, result, `vehicle_status`, `vehicle_land_detected`, `vehicle_local_position`, `TargetState`)만 쓴다. 정답 판정은 SITL 전용 정답 pose를 쓴다. 판정 코드는 두 부분을 함수 수준에서 나눈다. 정답 pose가 있어야 하는 실행에서 없으면 실패(`ORACLE_ABSENT`)이고 조용히 건너뛰지 않는다.
- 정답 pose: 토픽 `/sim/<vehicle_id>/pose`, `geometry_msgs/msg/PoseStamped`, `header.frame_id` `world`, `header.stamp`는 Gazebo `pose/info`의 sim 시각, 약 50 Hz. 기준점은 기체 base_link 원점(PX4 센서가 붙은 점, PX4 로컬 위치가 가리키는 점. 근거는 아래 [소스])이고 model 원점이 아니다.
- 공급: 별도 compose 서비스 `sim-oracle`(sim-base 이미지, `depends_on` gazebo와 `px4-N` 전부 healthy). `ros_ws/src/idsim_sim/scripts/sim_oracle.py` 한 파일의 rclpy 노드가 gz-transport Python 바인딩으로 `/world/<월드>/pose/info`를 직접 구독한다. ros_gz_bridge를 거치지 않고 `/clock`을 구독하지 않는다. top-level model `x500_N` pose에 base_link 오프셋을 합성한다(`p_bl = p_model + R_model * offset`, 자세는 model과 같다). 오프셋은 노드가 시작할 때 sdformat14로 모델 SDF를 해석해 얻는다(손으로 적지 않는다). 합성 함수는 순수 Python으로 두고 단위 테스트한다. 구독 토픽은 상수로 조립하고 단위 테스트가 `/pose/info`로 끝나며 `dynamic_pose`를 포함하지 않음을 단정한다. `idsim_interfaces`에 의존하지 않는다.
- 정답 pose 토픽 이름 `/sim/<vehicle_id>/pose`는 발행하는 `sim_oracle.py`와 구독하는 `tests/support`가 각자 조립한다. 공유 상수를 두지 않는다(`sim_oracle.py`는 sim-base 이미지에서 마운트로 돌고 `tests/support`는 다른 이미지와 소유자의 것이라, 한 모듈을 함께 import하면 이미지와 소유 경계를 넘는다). 대신 두 곳 모두 조립을 순수 함수 하나로 두고, 같은 사례 표(`px4_1 -> /sim/px4_1/pose` 등, 쟁점 3의 이름 조립과 같은 방식)로 각자 단위 테스트한다. 두 조립이 어긋나도 판정이 정답 pose를 받지 못해 `ORACLE_ABSENT`로 실패하므로 조용히 지나가지 않는다.
- `sim-oracle` 서비스: standalone이면 표적과 무관하게 항상 만들고 embedded에는 없다. sim-base 이미지, 호스트 uid:gid, `init: true`, `depends_on` gazebo와 `px4-N` 전부 healthy(모델이 스폰된 뒤라야 준비 조건이 성립한다), 노드 단계(쟁점 3). 환경 변수는 `GZ_PARTITION`, `GZ_IP`, ROS 공통값, `IDSIM_WORLD_NAME`, 기체 목록 `IDSIM_ORACLE_VEHICLES`(`px4_1=x500_1 px4_2=x500_2` 형식, 생성기가 `vehicles[]`에서 만들고 `assert_invariants`가 대조한다). 볼륨은 `idsim_sim` 읽기 전용, `config/cyclonedds.xml` 파일 하나 읽기 전용, `ros_log/sim-oracle` 쓰기. healthcheck는 쟁점 3과 같은 표시 파일(`/tmp/idsim/oracle_ready`, 모든 기체의 pose를 한 번 이상 냈을 때)이다.
- waypoint 도달의 주 판정은 정답 판정이다: Executor가 항목을 완료로 넘긴 시각 `t_f`(feedback의 항목 전환 stamp)에서 정답 pose와 world 목표의 3차원 거리가 판정 반경 `R_judge` 1.0 m(U14, 판정 상수) 안이어야 한다(아니면 `REACH_MISMATCH`). 시험 미션의 `acceptance_radius_m`은 `1.0 m - b` 이하이므로 `acceptance_radius_m + b`는 1.0 m를 넘지 않는다. 정답 pose는 `t_f` 앞뒤 표본에서 선형 보간하고, 앞뒤 표본 간격이 0.1 s를 넘으면 그 사건은 `ORACLE_STALE`로 실패한다. 테스트는 Python에서 원점 변환을 다시 구현하지 않는다. 통과 기준은 3차원 하나이고 수평과 수직 성분은 trace에 따로 남긴다.
- b의 정의(R2): GOTO 도달 사건마다 부호 있는 초과량 `s = d_oracle(t_f) - acceptance_radius_m`을 재고(0으로 자르지 않는다. `max(0, s)`는 trace 보고용이다), b는 `ceil_0.05(mean(s) + k x std(s))`다. k는 정규 분포의 단측 허용계수이고 신뢰 95%, 사건당 커버리지 `1 - 0.005 / m`이다. m은 한 실행에서 b를 쓰는 판정 사건(GOTO와 TRACK_ENTITY의 완료) 수이고, 실행당 실패 예산 1% 가운데 b에 0.5%를 주어 사건마다 Bonferroni로 나눈다. 1b 시나리오에서 m은 9(F1 3, F2 2, F3 1, F4 3)이고 부팅 30회에서 k = 4.237이다([계산] 비중심 t 분포). b의 평균과 표준편차는 부팅 30회 이상에서 모은 GOTO 도달 사건(부팅당 7개)으로만 계산하고, 표본 크기는 사건 수가 아니라 부팅 수로 본다(한 부팅의 사건은 수직 편향을 공유한다). std는 사건 전체의 표본 분산으로 계산한다(부팅 간 분산을 포함해 보수적이다). 보정 실행의 `acceptance_radius_m`은 0.5 m다.
- TRACK_ENTITY 완료는 m에는 세지만 GOTO 표본에 섞지 않는다(표적 지연 항 `v x L`과 움직이는 setpoint의 추종 동특성이 있어 분포가 다르다). 대신 `s_track = d_oracle(t_f) - acceptance_radius_m - v x L`을 따로 재고(부팅당 2개), 같은 k의 정규 허용한계 `mean(s_track) + k x std(s_track)`가 b 이하인지 점검한다. 넘으면 L이 모자라거나 추종 오차가 크다는 뜻이므로 모형을 기각하고, 판정을 느슨하게 하지 않고 architect에게 올린다. 이 점검은 R3(F2, F4 추종 오차)와 함께 본다.
- 판정 상수 m과 m_home은 시나리오에서 파생된 값이다. 단위 테스트가 판정 상수의 m이 sitl 시나리오 목록의 GOTO와 TRACK_ENTITY 완료 사건 수(지금 9)와 같고 m_home이 RTL 사건 수(지금 2)와 같음을 단정한다. 시나리오를 바꾸면 이 테스트가 깨져 k와 `q x f`를 다시 계산하게 한다.
- 모형 검증: GOTO의 `s`와 `s_track` 각각에서 표본 최댓값이 자기 허용한계 이하이고 Shapiro-Wilk p가 0.01 이상이어야 b를 정한다. 어느 하나라도 실패하거나 부팅 수가 30 미만이면 상수를 정하지 않고(보정 상태 유지) architect에게 올린다. 허용한계를 키워서 맞추지 않는다.
- 보정 상태: b와 `R_home`을 정하기 전에는 두 상수를 비워 둔다. 상수가 빈 상태가 곧 보정 상태이고 따로 스위치나 환경 변수를 두지 않는다. 보정 상태에서도 U14 뒤의 도달 판정(`REACH_MISMATCH`, 판정 반경 1.0 m)과 표적 접근 판정(1.0 m + v x L)은 b를 쓰지 않으므로 그대로 실패로 센다. 보정 상태에서 바뀌는 것은 `R_home`에 기대는 RTL 착륙 위치 단정 하나이고, 이 단정은 R4 값과 함께 `recorded_only`로 남기고 실패로 세지 않는다. 그 밖의 판정(계약 판정, `ORACLE_ABSENT`, `ORACLE_STALE`, 착륙 후 disarm, `UPSTREAM_FAILED` 규칙)은 그대로라 한 실행의 실패는 `--repeat`를 멈추고 0부터 다시 세게 한다(플래키를 감추지 않는다). 그래서 보정 실행에서 F1이 실패하지 않으면 F2-F4가 돌아 GOTO 표본과 R4가 모인다. 보정 상태는 머지되지 않는다: 단위 테스트가 "CI 시나리오 목록에 F1-F4가 있으면 b와 `R_home`이 정해져 있다"를 단정하므로, 상수가 빈 채 F1-F4를 CI에 넣는 상태는 lint에서 실패한다.
- b를 정하는 커밋: 부팅 수, GOTO 사건 수, `mean(s)`, `std(s)`, 최댓값, `s_track`의 사건 수, 평균, 표준편차, 최댓값, k, 두 Shapiro-Wilk p, 실행 id를 `tests/support/sitl_judge.py` 머리말에 적는다. 같은 커밋이 `tests/sitl/missions/`의 GOTO와 TRACK_ENTITY 항목 `acceptance_radius_m`을 `1.0 - b`로 바꾸고 F1-F4를 CI 시나리오 목록에 넣는다(README의 두 커밋 절차). b가 0.05 m 단위로 올린 값이라 `1.0 - b`도 0.05 m 단위다. 반경의 숫자는 미션 YAML에만 적고, b가 정해진 상태에서 단위 테스트가 로더로 읽은 모든 sitl 미션의 `acceptance_radius_m`이 0.5 m 이상이고 `R_judge - b` 이하임을 판정 상수와 대조한다(보정 상태에서는 0.5 m임을 단정한다). 그 커밋의 상태로 로컬 부팅 10회 이상을 돌려 모든 도달 사건이 1.0 m 안인지 확인한다(보정 반경 0.5 m와 확정 반경의 차로 `s`가 달라지는지 보는 확인이다). 확인에서 1.0 m를 넘는 사건이 있으면 올린다.
- 정한 뒤 통과와 실패를 보고 바꾸지 않는다. CI에서 판정 반경을 넘는 사건이 나오면 b를 올리지 않고 architect에게 올린다. 한 달에 2회를 넘게 나오면 모형이 틀린 것으로 본다.
- b의 상한은 0.5 m다(`acceptance_radius_m` 0.5 m 이상. 그 아래에서는 Executor가 waypoint에서 도착 3표본 확인을 못 하고 정체할 위험이 커진다 [추정]). b가 0.5 m를 넘으면 반경을 줄이거나 판정을 넓히지 않고 보정 결과(분포, `d_h`, `d_v`, R1)를 들고 architect와 사용자에게 올린다. b가 0.35 m를 넘으면 통과하되 PR 본문에 적고 F1에서 도달 사건이 모두 비행당 시간 한도 안이었는지 보고한다(0.35는 [추정] 경고선이다).
- `REACH_MISMATCH`는 보정 표본에서는 거의 늘 통과하고(허용한계가 표본 최댓값 이상이다) 보정 뒤의 퇴행을 잡는 검사다. EKF 오차를 독립으로 확인하는 실질은 "b가 0.5 m 이하"라는 상한 점검이다.
- trace 항목: 도달 사건마다 `(t_f, d3, d_h, d_v, 정답 표본 간격)`, 부팅마다 `(R1_h, R1_v)`.
- R1(EKF 원점과 기대 스폰 위치의 차)은 b의 입력이 아니라 기록 항목이다. sitl gate가 매 실행 `verdict.json`에 `recorded_only`로 남긴다. 참고: 생성기 `AIRFRAME_SENSOR_Z_M`(0.24)로 낸 `expect_gps` 고도는 지상 정지에서 실제 센서 높이(model이 1.3 cm 내려앉아 0.227)보다 약 1.3 cm 높다(쟁점 5 [실측] S1-a). R1 수직 기록에 이 차가 상수로 실린다.
- 표적 접근: 판정은 수신한 `TargetState`만 본다(정의에서 기대 위치를 다시 계산하지 않는다). 기체 정답 표본 시각마다 표적 위치를 감싸는 두 `TargetState` 표본에서 선형 보간하고 외삽하지 않는다. 거리는 보간한 표적 위치에 항목의 `offset`을 더한 점(Executor의 setpoint 점)까지 잰다. 임계값은 `R_judge + v x L`(1.0 m + v x L)이다. TRACK_ENTITY의 완료도 GOTO와 같은 EKF 거리 조건이므로 GOTO와 같은 판정 반경과 시험 미션 반경 규칙(`acceptance_radius_m`은 `1.0 m - b` 이하)을 쓰고, 표적 쪽 지연만 `v x L`로 더한다. v는 시나리오 표적 속도의 최댓값, L은 0.2 s(= `target_fresh_age` 0.1 s + Executor tick 0.05 s + 여유 0.05 s)다. 판정 코드 머리말에 이 식을 적고, 단위 테스트가 판정 상수 L과 노드의 `target_fresh_age` 기본값이 이 식으로 맞는지 대조한다(대조 방법은 test-engineer와 ros2-engineer가 정한다). L은 TRACK_ENTITY의 속도 feedforward(쟁점 8)를 전제로 한 상수이고 PX4가 setpoint를 반영하는 지연을 약 한 tick으로 본 것은 [추정]이다. F2 trace(R3의 `TargetState` 나이와 추종 오차)로 확인한다. 확인에서 L이 모자라면 판정을 느슨하게 하지 않고 architect에게 올린다. 접근 구간에 표적이 실제로 움직였음을 단정한다(`NO_TARGET_MOTION`). F2와 F4의 표적 속도는 1-2 m/s다.
- 착륙 후 disarm: 1a의 `disarmed_confirmed`, `landed_confirmed`를 그대로 쓰고, DISARMED 시점의 정답 z가 그 비행의 이륙 직전 정답 z + 0.3 m 안임을 더한다(스폰 pose z는 model 원점이라 base_link와 0.24 m 다르므로 쓰지 않는다). RTL이면 착륙 수평 위치가 그 비행의 이륙 직전 정답 위치에서 `R_home` 안이다.
- `R_home`은 b와 따로 정한다. RTL 착륙점(PX4 home)과 판정 기준점이 같은 물리 위치를 가리켜 사슬 오차가 들어가지 않기 때문이다. RTL 착륙 수평 위치와 기준점의 거리 R4에 Rayleigh 허용한계를 쓴다: `sigma_hat^2 = mean(R4^2) / 2`(영점 편향이 있으면 값이 커져 보수적이다), `R_home = ceil_0.05(q x f x sigma_hat)`, `q = sqrt(-2 ln(0.005 / m_home))`, `f = sqrt(2n / chi2_0.05(2n))`(sigma의 95% 상한 보정, n은 부팅 수). 실행당 예산 0.5%를 RTL 사건 수 m_home에 Bonferroni로 나눈다. 1b 시나리오에서 m_home은 2(F3, F4)이고 부팅 30회에서 `q x f` = 4.080이다([계산]). 부팅 30회 이상(b와 같은 실행)에서 정하고, 값, 부팅 수, 사건 수, 최댓값, 실행 id를 머리말에 적는다. 표본 최댓값이 허용한계를 넘으면 모형을 기각하고 상수를 정하지 않고 올린다. 착륙 위치 벡터의 평균이 2 표준오차보다 크면 기록한다(편향은 RMS에 들어가 보수적이라 기각 사유가 아니다). `R_home`이 1 m를 넘으면 올린다. F3의 기준점은 F3이 이어받은 비행(F2)의 이륙 직전 정답 위치이고, F4의 기준점은 F4 자신의 이륙 직전 정답 위치다. 판정이 그 비행의 기준점을 쥐도록 F1에서 F4까지 같은 세션 객체(비행 단위 상태)를 넘기는 fixture를 둔다.
- 판정은 미션의 종료 유형(`LANDED_DISARMED`, `HOLD_AIRBORNE`)으로 매개변수화한다. `SUCCEEDED => disarm` 가정을 두지 않는다.
- 정답 pose는 `idsim_interfaces`의 계약이 아니고 `docs/interface.md`의 계약 절에 넣지 않는다. 시뮬레이터 전용 토픽은 접두 `/sim/`을 쓴다. 운용 패키지(`idsim_common`, `idsim_mission`, 그리고 앞으로의 `idsim_telemetry`, `idsim_fleet`, `gateway/`)는 `/sim/`을 쓰지 않고 lint가 검사한다. 검사 대상은 소스, launch 파일, params YAML이다. SITL 실행의 기록물에는 `/sim/` 토픽이 들어간다(U12). 이 규칙은 `docs/architecture.md`의 테스트 절에 둔다.

근거
- Executor는 EKF 위치로 도달을 판정한다. 테스트도 EKF 위치로 판정하면 EKF 오차와 원점 변환 오류가 양쪽에 같이 실려 보이지 않는다. 정답 pose는 사슬 전체를 독립으로 보는 유일한 입력이다.
- [소스] v1.17.0 SITL x500은 `EKF2_HGT_REF=1`(GNSS 기준)이다(`ekf2/module.yaml` 87-104행, x500 경로와 idsim `config/`는 덮지 않는다). 수평과 수직 모두 기체 추정과 목표가 같은 EKF 원점으로 로컬화되므로 원점의 초기 잡음은 도착점에 들어가지 않는다. 도착점 오차는 도달 순간의 GNSS 오차, EKF 지연, 센서 장착 위치에서 오고 R2가 이를 잰다. 그래서 b는 3차원 하나로 정한다. `EKF2_HGT_REF`를 계약 파라미터로 고정한다(쟁점 9).
- 최댓값 규칙은 쓰지 않는다. 표본 n개의 최댓값을 다음 표본이 넘을 기대 확률은 1/(n+1)이라(n = 10이면 9.1%) "로컬 3회 연속 통과"가 약 25% 확률로 실패하고, 같은 보장을 분포 가정 없이 얻으려면 부팅 99회(신뢰 50%)에서 299회(신뢰 95%)가 든다([계산]). 분포를 가정한 허용한계는 부팅 30회로 되고, 가정이 틀리면 모형 검증에서 드러난다. 정규 가정의 물리 근거는 `t_f`의 EKF 거리가 반경 근처이고 정답 거리와의 차가 작은 독립 항(GNSS Gauss-Markov 잡음, 확인 지연 x 속도, 부팅마다 일정한 수직 편향)의 합이라는 것이다([추정]).
- [소스] Gazebo x500 NavSat에는 잡음 요소가 없다(`x500_base/model.sdf` 310-314행). PX4 GZBridge가 NavSat 값에 1차 Gauss-Markov 잡음을 더한다(`GZBridge.cpp` 680-711행. 정상 표준편차 [추정, 계산] 수평 축마다 약 2 cm, 수직 약 3 cm). 기압계는 백색 잡음 3 Pa다. b의 기대 크기는 수평 0.2 m, 수직 0.3 m 아래다([추정], R2로 확인). b가 0.5 m를 넘으면 센서 잡음보다 사슬이나 기준점 오류를 먼저 의심한다.
- [소스] base_link는 model 프레임 (0, 0, 0.24)에 회전 없이 있고(`x500_base/model.sdf` 4행, sdformat14 해석) PX4가 쓰는 센서 넷이 모두 base_link에 pose 없이 붙어 있다. model pose를 쓰면 정답이 0.24 m 아래로 치우친다.
- [소스] PX4 로컬 위치가 base_link 원점을 가리킨다. px4 이미지(v1.17.0 빌드)의 `etc/extras/parameters.json.xz`에서 EKF2 위치 오프셋 파라미터 15개(`EKF2_IMU_POS_X/Y/Z`, `EKF2_GPS_POS_X/Y/Z`, `EKF2_EV_POS_*`, `EKF2_OF_POS_*`, `EKF2_RNG_POS_*`)의 기본값이 모두 0이고, `4001_gz_x500`, `4001_gz_x500.post`, `rc.mc_defaults`, posix `rcS`, idsim `config/px4/sitl_params.env`가 이 값을 바꾸지 않는다. sim-base 이미지의 `x500_base/model.sdf`에서 IMU, NavSat, 기압계, 지자기 센서 넷이 모두 `base_link`에 센서 pose 없이 붙어 있다(K4).
- [실측] S1-a: 스택 9에 기체 둘을 (6, -3, 0, yaw 0)과 (-2, 4, 0, yaw 1.2)에 스폰해 지상 정지에서 쟀다. oracle 위치의 x, y는 스폰과 같고 z는 0.227 m다. 스폰 z + 0.24보다 1.3 cm 낮은데, model이 지상 접촉으로 1.3 cm 내려앉기 때문이다(Pose_V의 model 항목 z가 -0.013). Pose_V의 `x500_N` model 항목은 world 기준이다(`x500_2`의 쿼터니언이 yaw 1.2 rad). link 항목은 부모 model 기준이고 이름에 scope가 없어 `base_link`가 기체 수만큼 나오므로, 구독은 top-level model 항목만 읽는다. sdformat14가 낸 base_link 오프셋은 (0, 0, 0.24)이고 발행 주기는 50.3 Hz다.
- [소스] ros-ws 이미지에는 gz Python 바인딩이 없고 sim-base에는 `python3-gz-transport13`, `python3-gz-msgs10`, rclpy, `geometry_msgs`, `rmw_cyclonedds_cpp`가 함께 import된다. ros_gz_bridge의 Pose_V 변환은 엔티티 이름과 부모 관계를 잃는다([추정]). `pose/info`는 `dynamic_pose/info`와 다른 경로이고 1a-5에서 Actor 월드에 구독해도 서버가 살아 있었다([실측]). PX4 GZBridge가 이미 같은 토픽을 구독한다.

## 쟁점 6. 항목 순서 규칙과 첫 항목이 아닌 TAKEOFF

결정
- 계약 문장으로 둔다: TAKEOFF는 첫 항목에만 온다. LAND와 RTL은 마지막 항목에만 온다. 그래서 모드 명령 항목으로 시작하는 미션은 `[LAND]`나 `[RTL]` 한 항목뿐이고, 미션 안에서 모드 명령 항목 뒤에 setpoint 항목이 오지 않는다(미션 중간의 Offboard 재진입은 없다).
- 이 규칙은 `validate_mission_contract`(Phase 3 Fleet도 쓰는 층)에 둔다. 어기면 INVALID_MISSION이고 `detail`에 이유를 적는다.
- 1a 노드의 임시 제한(받는 type 셋, 마지막이 LAND)은 1b에서 모두 없어진다. 남는 것은 위 계약 규칙뿐이다.
- 반복 비행은 미션 둘로 보낸다(`[TAKEOFF, ..., LAND]` 다음 `[TAKEOFF, ..., LAND]`). goal 경계가 소비자에게 지상 DISARMED 확인 지점을 준다.
- `MissionItem.timeout`, `YawSetpoint`, `TakeoffItem.height_m`의 "첫 항목이 아닌 TAKEOFF는 1b에서 정한다" 괄호는 "TAKEOFF는 첫 항목에만 온다"로 닫는다.

근거
- 1b 완료에 "첫 항목이 아닌 TAKEOFF의 의미"를 고정해야 한다(interface.md 고정 시점 절). 계약으로 두면 고정되는 의미는 "무효"다.
- 나중에 허용하는 것은 전에 거부하던 입력을 받는 완화라 기존 생산자를 깨지 않는다. 그때는 "고정 뒤 새 요구"로 변경 절차를 밟는다.
- 허용하면 1a 고정 문장 넷(준비 단계 feedback의 `item_index` 0, NOT_READY와 PRECONDITION_FAILED의 "보내지 않았다", 지상 disarm 1회 조건 (2), `ready_timeout` 기준)이 깨진다.
- `docs/architecture.md` 인터페이스 계약 절의 "다음 setpoint 항목에서 Offboard 재진입 절차를 다시 밟는다"는 이 결정과 어긋나므로 고친다(1a 고정 계약 영향 (h)).

## 쟁점 7. 진입 방식과 공중 시작 미션

결정
- 준비 단계는 미션 단위로 한 번 돈다. 진입 방식은 첫 항목의 type에서 파생한다(core의 `EntryPlan`).

| 진입 방식 | 첫 항목 | 시작 조건(P1) | P2 | 단계 | 첫 항목 시작 시각 |
| --- | --- | --- | --- | --- | --- |
| 지상 arm 진입 | TAKEOFF | 지상 DISARMED(1a 그대로) | 1a 그대로 | P0-P6. P5 -> P6 조건에 마지막 DO_SET_MODE 전송 뒤의 ack를 더한다(쟁점 12의 불변식). 나머지는 1a 그대로 | arm 확인 |
| 공중 Offboard 진입 | GOTO, TRACK_ENTITY, LOITER | ARMED, 공중, `nav_state`와 `nav_state_user_intention`이 AUTO_LOITER, `failsafe` false | EKF gate와 위치, heading 유한(진입 setpoint에 쓴다) | P0-P2, P3(진입 setpoint), P4, P5. P6 없음 | OFFBOARD 3회 연속 확인 |
| 모드 명령 진입 | LAND, RTL | ARMED이고 공중(1a `[LAND]` 그대로) | 1a 그대로 | P0-P2 | 준비 끝 |

- 공중 Offboard 진입의 시작 조건이 맞지 않으면 PRECONDITION_FAILED다(발행 시작 전이라 아무것도 보내지 않았다). 이미 OFFBOARD인 기체, AUTO_RTL이나 AUTO_LAND 중인 기체, failsafe 중인 기체는 받지 않는다. 보내는 쪽이 먼저 기체를 Hold로 둔 뒤(예: 실행 중 goal의 취소) 다시 보낸다. 접수 뒤 P4에서 처음 본 OFFBOARD도 받지 않는다(아래 "P4에서 먼저 본 OFFBOARD").
- P3의 진입 setpoint는 P3 tick에 읽은 위치와 heading이고 OFFBOARD 확인까지 바꾸지 않는다. OFFBOARD 3회 확인 tick에 첫 항목을 시작하고 그 항목의 setpoint로 바꾼다. 첫 항목이 LOITER이면 진입 setpoint가 "직전 setpoint"다.
- 감시: P3부터 비행 중 감시 표를 적용한다.

| 순위 | 행 | 첫 OFFBOARD 표본 전(P3부터) |
| --- | --- | --- |
| 1-5 | timestamp 실패, 식별, 끊김, 공중 DISARMED, 지상 DISARMED | 그대로 |
| 6 | OFFBOARD 아님이고 failsafe | 그대로(AUTO_LOITER여도 적용) |
| 7 | OFFBOARD 아님, failsafe 아님, 의도 OFFBOARD 아님 | `nav_state`가 AUTO_LOITER이면 적용하지 않는다 |
| 8 | OFFBOARD 아님, failsafe 아님, 의도 OFFBOARD | `nav_state`가 AUTO_LOITER이면 적용하지 않는다 |

- 첫 OFFBOARD 표본은 P3 뒤에 온 표본 가운데 `nav_state`가 OFFBOARD이고 감시의 행(순위 1-6)에 걸리지 않은 첫 표본이다. `failsafe` 값과 무관하다(순위 6은 OFFBOARD가 아닌 표본에만 맞고, OFFBOARD이고 failsafe인 표본이 어느 행에도 맞지 않는 1a 규칙은 그대로다).
- 면제는 P5에서 첫 OFFBOARD 표본을 본 tick에 끝난다(OFFBOARD 3회 확인을 기다리지 않는다). 그 tick부터 순위 7, 8은 1a 그대로이고, 공중 Offboard 진입의 P5는 그 tick부터 DO_SET_MODE를 재전송하지 않는다(전환이 처리된 것을 이미 봤다). 재전송을 멈추는 조건은 이 표본 하나이고 수락 ack는 조건으로 쓰지 않는다. 지상 arm 진입은 마지막 전송 뒤의 비거부 ack를 받을 때까지 재전송한다(쟁점 12. 조건이 다른 이유는 아래 근거).
- P4에서 먼저 본 OFFBOARD: P4(이 goal이 DO_SET_MODE를 보내기 전)에 첫 OFFBOARD 표본이 오면 다른 주체의 전환이다. DO_SET_MODE를 보내지 않고 ABORTED, MODE_SWITCH_FAILED(준비 단계)로 끝내며 `detail`로 구분한다("OFFBOARD before DO_SET_MODE"). P4, P5의 다른 실패처럼 정리의 공중 분기를 거친다(발행을 유지한 채 Hold, Hold 관측에 발행 중단). 같은 tick의 순서에서 감시 표 다음이고 `offboard_signal_timeout`과 신호 확인보다 앞이다. 함께 참인 사건과의 겹침 칸은 px4-engineer의 칸 명세(쟁점 12의 S4)가 이 방향대로 적는다.
- 공중 Offboard 진입에서 감시가 쓰는 `vehicle_status`의 하한 timestamp는 P3 tick에 쓴 표본의 timestamp다. 공중 Offboard 진입에서 P5의 OFFBOARD 계수는 감시를 지난 표본만 센다. 공중 Offboard 진입에서 같은 tick의 순서는 P4가 감시 표, 먼저 본 OFFBOARD, `offboard_signal_timeout`, 신호 확인이고 P5가 감시 표, 거부 ack, `mode_confirm_timeout`, OFFBOARD 3회 확인, 취소다.
- 순위 5의 failsafe 이력 구간은 P3 tick부터 첫 항목이 끝날 때까지 한 구간이다(첫 항목 시작 tick에 이력을 지우지 않는다). 이 goal은 arm을 보내지 않았으므로 지상 disarm 1회 조건 (1)은 늘 거짓이고 `landed_false_seen`은 보지 않는다.
- 공중 진입의 식별 불일치는 준비 단계의 별도 분기가 아니라 감시 순위 2로 처리한다(결과는 같다. 전이 칸이 둘로 갈리지 않게).
- P4, P5 실패(MODE_SWITCH_FAILED)는 정리의 공중 분기를 거친다(발행을 유지한 채 Hold, Hold 관측에 발행 중단). 늦게 처리된 Offboard 전환 뒤에 발행을 멈추면 1 s 뒤 offboard 손실 Land가 걸리기 때문이다. 기체가 아직 Hold이면 첫 Hold 확인 3회로 바로 끝난다.
- P5에서 OFFBOARD 표본을 본 뒤 운용자가 Hold로 되돌리면 그 표본에서 순위 7의 EXTERNAL_MODE_CHANGE로 끝난다. 정리를 거치지 않고 그 tick에 발행을 멈추며, arm을 보내지 않은 goal이라 명령을 보내지 않는다. OFFBOARD 표본을 보기 전에는 운용자가 다시 지정한 Hold와 전환 전의 Hold를 가를 수 없어 면제와 재전송이 이어진다.
- 먼 첫 GOTO의 setpoint 점프는 1b에서 점진 이동으로 다루지 않는다(1a TAKEOFF가 처음부터 목표점을 보내는 것과 같다). F3의 trace로 본다.

근거
- [소스] failsafe 중의 모드 변경은 사용자 넘겨받기다(`framework.cpp` 501-518행). AUTO_RTL, AUTO_LAND, failsafe 중인 기체를 받거나 진입 중 failsafe인 기체에 OFFBOARD 전환을 보내면 Executor가 다른 주체의 결정을 덮는다. 그래서 순위 6은 면제하지 않는다(failsafe 동작이 Hold인 표본, `nav_state` AUTO_LOITER이고 `failsafe` true).
- [소스] Hold 중의 `trajectory_setpoint`는 비행제어 자신의 setpoint와 섞인다. 현재 위치를 보내면 끌림이 작다([실측] 1a에서 다음 목표를 보냈을 때 0.4 m 끌림).
- 모드 행을 확인 전에 아예 빼면 진입 중에 failsafe Land나 외부 RTL로 바뀐 기체를 `offboard_signal_timeout` 뒤 정리의 Hold로 덮는다. 감시를 P3부터 두면 그 tick에 FAILSAFE나 EXTERNAL_MODE_CHANGE로 끝낸다.
- [소스, 완전성은 추정] K1, K2(PX4 v1.17.0 원문 열람): failsafe 동작이 Hold인 표본은 `failsafe` true, `nav_state` AUTO_LOITER이고(`Commander.cpp` 2388행, `framework.h` 150행, `framework.cpp` 680행) 순위 6이 잡는다. `failsafe` false인 채 OFFBOARD에서 AUTO_LOITER로 돌아가는 길은 다른 주체의 모드 변경뿐이다. 모드 의도 변경은 원자적이고(`UserModeIntention.cpp`의 `change()`), 수락 뒤 `nav_state`가 의도와 달라지는 길은 failsafe 동작 선택(`Commander.cpp` 2349-2353행)뿐이다. 그 밖의 길이 없다는 완전성은 [추정]이다. 그래서 OFFBOARD를 본 뒤의 AUTO_LOITER는 다른 주체의 결정이다. 완전성이 틀려 PX4가 스스로 되돌아가는 길이 있으면 goal이 순위 7이나 8로 거짓 종료하지만, 명령 없이 Hold인 기체를 두고 끝나므로 fail-closed다. F3 trace로 본다(실측과 확인 목록의 "공중 시작").
- [추정] 면제와 재전송을 3회 확인까지 두면 그 사이의 재전송이 다른 주체의 Hold를 덮는다. `/fmu/out/vehicle_status`는 모드 변경 직후의 표본 하나 뒤에 약 0.5 s 간격으로 오므로 3회 확인까지 약 1 s이고, 그 사이에 `command_resend_period` 0.5 s의 재전송이 1-2회 나간다(간격은 재지 않았다. F3 trace로 본다).
- 첫 OFFBOARD 표본에서 재전송을 멈추는 이유: 감시의 행으로 끝난 goal은 발행을 멈추므로, 그 뒤에 이 goal의 DO_SET_MODE가 처리되면 기체가 발행 없는 OFFBOARD가 되어 `COM_OF_LOSS_T` 뒤 Offboard 손실 failsafe가 걸린다. 전제는 DO_SET_MODE 전송에서 OFFBOARD 표본 도착까지의 지연 D가 `command_resend_period`(0.5 s)보다 작다는 것이다. D는 처리 W(16 ms 이하 [실측], 쟁점 11), `/fmu/out/vehicle_status`의 5 Hz 제한에 따른 최대 200 ms([소스] uXRCE-DDS 클라이언트 `dds_topics.yaml`의 `rate_limit`. idsim은 재정의하지 않는다. PX4는 모드 변경 직후 같은 루프에서 `vehicle_status`를 publish한다, `Commander.cpp`), 전송, tick 50 ms의 합이고 약 0.27 s 이하다([추정]. 재지 않았다). 이 전제에서 첫 OFFBOARD 표본 전에 나간 DO_SET_MODE는 하나이고 그 표본을 만든 명령이라 이미 처리됐다. 그래서 첫 OFFBOARD 표본 뒤의 순위 7, 8 종료에 한해, 종료 뒤에 처리될 이 goal의 명령이 남지 않는다. D가 주기를 넘으면 표본 전에 재전송이 하나 더 나갈 수 있고, 그 명령이 감시 종료 뒤에 처리되려면 다른 주체의 Hold와 그 표본의 도착이 그 명령의 W 안에 끼어야 한다. 첫 OFFBOARD 표본 전에 다른 주체가 지정한 Hold는 이 근거가 덮지 않는다(전환 전의 Hold와 가를 수 없어 재전송이 이어진다). D와 P5의 전송 수는 F3 trace로 보고(실측과 확인 목록의 "공중 시작"), 부하 아래의 D는 Phase 2에서 다시 본다(넘김 목록).
- 수락 ack를 재전송 중단 조건에 더하지 않는 이유: 공중 Offboard 진입은 arm을 보내지 않아 진행 조건에 ack가 없고, 첫 OFFBOARD 표본이 전환이 처리됐다는 관측이다. 위 전제에서는 그 표본 전에 재전송이 나가지 않아 ack 조건으로 얻는 것이 없고 칸만 늘어난다. 첫 OFFBOARD 표본 전의 DO_SET_MODE 유실은 재전송이 회복하고 그 뒤의 진행은 주기 표본(`vehicle_status`)에만 달려 있으므로 쟁점 12의 "명령과 ack의 유실" 규칙을 지킨다. [소스] ack는 명령의 source를 target으로 싣고(`Commander.cpp` 2677-2678행) 노드는 자기 `CommandSource`와 target이 다른 ack를 버리므로(`src/px4/inputs.cpp`의 `to_ack_sample`) GCS나 Navigator가 낸 명령의 ack는 이 goal의 것으로 읽히지 않는다. 잘못 읽힐 수 있는 것은 같은 source를 쓰는 송신자의 ack뿐이다(다른 송신자, 그리고 이 노드의 앞선 goal이 보낸 같은 묶음 명령의 늦은 ack). F3 trace에서 P5의 전송 수가 1을 넘으면 다시 본다.
- 재전송 중단 조건이 지상 arm 진입과 다른 이유: 지상 arm 진입은 arm 순서 불변식 때문에 ack가 진행 조건이라(쟁점 12) 그 ack를 얻을 때까지 재전송하고 얻으면 멈춘다. 지상은 DISARMED라 ack 전의 재전송이 다른 주체의 결정을 덮어도 failsafe가 걸리지 않는다([소스] `framework.cpp` 452-455행). 공중은 덮은 뒤 발행 중단과 겹치면 Offboard 손실 failsafe가 걸리므로 전환의 관측(첫 OFFBOARD 표본)에서 멈춘다.
- P4에서 먼저 본 OFFBOARD를 정리의 공중 분기로 끝내는 이유: 기체는 OFFBOARD이고 이 goal이 P3부터 낸 진입 setpoint를 따르고 있다. 그 전환은 이 goal의 Offboard 신호가 있어서 받아들여졌을 수 있다([추정]). 그 tick에 발행을 멈추면 `COM_OF_LOSS_T` 뒤 Offboard 손실 failsafe가 걸릴 수 있으므로 발행을 유지한 채 Hold로 되돌린다. Hold는 goal이 기체를 받은 때의 상태이고 시작 조건(이미 OFFBOARD인 기체는 받지 않는다)과 같은 요구다. 다른 주체의 OFFBOARD를 Hold로 덮는 것은 정책 판단이다. reason을 EXTERNAL_MODE_CHANGE로 두지 않는 이유: 그 reason의 끝난 뒤 기체 상태는 "다른 주체가 고른 모드의 ARMED이고 Executor는 발행을 멈췄다"로 1a에 고정되어 있어 Hold를 보내는 종료를 넣으면 그 행이 갈린다. MODE_SWITCH_FAILED(준비 단계)는 공중 Offboard 진입의 P4, P5 실패와 끝 상태가 같다(1a 고정 계약 영향 (m)). 1a에도 선례가 있다: DO_SET_MODE 전 P4 실패(`offboard_signal_timeout`)가 MODE_SWITCH_FAILED다(`docs/interface.md` 신호 확인 행).
- [소스] 감시 판정은 순수 함수이고(`rules.cpp` 65-90행) 면제는 `MonitorInput`에 입력 하나를 더해 순위 7, 8의 조건에 거는 것으로 끝난다. `kMonitorRankOrder`는 바뀌지 않는다.

## 쟁점 8. GOTO와 TRACK_ENTITY

결정

| 항목 | GOTO | TRACK_ENTITY |
| --- | --- | --- |
| setpoint 위치 | `position`(world ENU)을 `FramePort`로 로컬 NED로. 매 tick 변환 | 최신 유효 표적 위치 + `offset`(world ENU)을 로컬 NED로. 유효 표본이 없는 동안 직전 setpoint 위치 유지 |
| setpoint 속도 | 없음(NaN) | 그 tick의 표적 표본이 신선하고 `velocity_valid`가 true이면 표적 속도(world ENU)를 `FramePort`로 로컬 NED로 바꿔 feedforward로 싣는다. 아니면 없음 |
| 시작 대기 | 점 변환이 값 없음인 동안 직전 setpoint 유지(계약 그대로) | 같다. 표적 첫 유효 표본까지 |
| 완료 | 서로 다른 `vehicle_local_position` 표본(PX4 `timestamp`로 구분) 3개 연속, `xy_valid`와 `z_valid`, 3차원 거리 < `acceptance_radius_m` | 같은 조건. 그 tick의 표적 표본이 신선할 때만 센다 |
| timeout 기준 | 항목 시작 tick | 같다 |
| TARGET_LOST | - | 항목 시작부터 `target_timeout` 안에 유효 표본이 없거나, 얻은 뒤 `now - header.stamp > target_timeout` |
| 실패의 정리 | ITEM_TIMEOUT은 정리 | ITEM_TIMEOUT과 TARGET_LOST 모두 정리. reason 유지 |

- 같은 tick의 순서: 감시 표 -> TARGET_LOST -> ITEM_TIMEOUT -> 완료.
- 유효 표본(노드 변환에서 거른다): `target_id`가 토픽 토큰과 같고, `frame_id`가 `world`, 값이 유한(위치, 그리고 `velocity_valid`가 true이면 속도. false이면 속도 필드를 보지 않는다), stamp가 0이 아니고 직전 유효 표본보다 크다. 유효로 표시된 속도가 비유한이면 표본 전체가 무효다(속도만 떼어 위치를 쓰지 않는다). 거른 표본은 소실 판정을 앞당기지 않는다. 나이가 음수이면 0으로 본다.
- 신선한 표본: 최신 유효 표본의 나이(`now - header.stamp`)가 `target_fresh_age`(노드 파라미터, ROS 시각, 기본 0.1 s) 이하. 0.1 s는 표적 발행 간격 0.05 s의 두 배로 표본 하나 손실까지 신선하다고 본다. 두 값의 관계는 "`target_fresh_age` < `target_timeout`" 하나이고 `target_timeout`(노드 파라미터, 기본 1.0 s)은 `COM_OF_LOSS_T`와 무관하다. 두 값은 R3 기록을 보고 바꾼다(R3의 판단 기준).
- TARGET_LOST를 판정한 tick부터 Hold 확인(또는 Hold 실패 뒤 Land 경로)까지 setpoint 발행을 유지한다(정리의 공중 분기 규칙 그대로). 이 유지가 `target_timeout`과 PX4의 Offboard 손실 판정을 떼어 놓는다.
- 속도 feedforward: 신선하지 않은 tick에는 속도를 싣지 않고 위치만 보낸다(묵은 속도로 기체가 앞서 나가지 않게). 표적 속도의 크기를 Executor가 자르지 않는다. 수평과 수직 한계는 PX4 위치 제어가 적용한다. `offboard_control_mode`는 그대로 position만 true다. GOTO, TAKEOFF, LOITER, 지상 setpoint는 속도를 싣지 않는다.
- 변환 값 없음: `FramePort`의 점 변환과 벡터 변환은 기준이 무효이거나 결과가 `trajectory_setpoint`에 실을 수 없는 값(비유한 또는 float32 범위 밖)이면 값 없음이다(쟁점 4). 점 변환이 값 없음인 tick은 직전 setpoint를 유지하고 완료를 세지 않는다. 속도 변환이 값 없음인 tick은 속도만 싣지 않고 위치는 보낸다(신선하지 않은 tick과 같다). 그래서 유한하지만 float 범위 밖인 GOTO 위치나 표적 위치는 발행을 끊지 않고 ITEM_TIMEOUT과 그 정리로 끝난다. 항목 시작부터 한 번도 점 변환 값을 얻지 못한 채 난 ITEM_TIMEOUT은 `detail`에 그 사실을 적는다.
- 어댑터 출력은 1a 규칙 그대로다. core가 낸 위치, yaw, 또는 `velocity_valid`가 true인 속도가 실을 수 없는 값이면 그 tick의 짝 전체(`offboard_control_mode`와 `trajectory_setpoint`)를 내지 않고 오류 로그를 남긴다. 속도만 빼고 내지 않는다. `FramePort`를 거친 값(GOTO와 TRACK_ENTITY의 위치, 속도)은 앞에서 걸러지므로 그 값으로 이 경로에 닿으면 결함이다. port를 거치지 않는 TAKEOFF의 목표 높이는 1a 그대로 이 경로에 닿을 수 있다. `height_m`이 유한하지만 float 범위 밖이면 지상 DISARMED에서 짝이 나가지 않아 준비 단계의 MODE_SWITCH_FAILED로 끝난다(arm 전).
- 좌표 상한(계약): GOTO `position`과 TRACK_ENTITY `offset`의 성분은 절댓값이 1e6 m 이하다. `validate_mission_contract`가 검사하고 어기면 INVALID_MISSION이다(쟁점 12의 S5). TAKEOFF `height_m`에는 상한을 더하지 않는다(1a 고정 문장이고 범위 밖 값의 결과는 위처럼 지상에서 arm 없이 끝난다). float 범위 안이지만 매우 큰 높이(예 1e30)에서 PX4 수직 제어 동작은 확인하지 않았다([추정]: 수직 성분은 constrainXY에 걸리지 않는다). 1e6 m 값은 S5 칸 명세에서 px4-engineer가 확인한다(아래 근거). 표적의 유효 표본 규칙은 유한만 보고, 표적 위치의 범위는 `Px4FramePort`의 float32 술어가 안전망이다. float32 범위는 `Px4FramePort`만 안다(core와 검증은 모른다).
- 계약 문장(TRACK_ENTITY): "setpoint는 표적 위치에 `offset`을 더한 점이다. 표적 표본이 신선하고 속도가 유효하면 표적 속도를 같은 setpoint에 feedforward로 싣는다. 그래서 일정 속도 표적에 대한 정상 추종 지연은 표본과 tick 지연 정도다." 여기서 표본과 tick 지연은 표본 나이 상한 `target_fresh_age`에 tick 하나를 더한 것이다.
- 표적 구독은 goal 접수 때 미션에 나오는 모든 `target_id`에 대해 만들고 goal이 끝나면 지운다. 구독 QoS는 계약 상태 행(BEST_EFFORT, VOLATILE). 변환은 노드(`node/conversion.cpp`)에서 `core::TargetSample`로 한다(PX4 메시지가 아니므로 px4 어댑터가 아니다). `TargetSample`은 위치, 속도 유효와 속도, ROS 시각 `stamp_ns`를 갖는다.
- `MODE_KEEP` 기준 yaw: 직전 setpoint의 yaw. 직전 setpoint가 없으면 발행을 시작할 때 읽은 heading. 1a의 "첫 항목인 TAKEOFF는 기준 위치를 읽을 때의 heading"과 공중 Offboard 진입의 첫 항목이 이 규칙의 특수한 경우다.
- `distance_remaining_m`: 로컬 NED 위치와 setpoint 점의 3차원 거리. `distance_valid`는 위치(`xy_valid`, `z_valid`)와 변환이 모두 유효할 때만.
- TRACK_ENTITY의 지속 시간 필드는 더하지 않는다. `TrackEntityItem`과 `GoToItem`의 필드는 바꾸지 않는다.

근거
- [소스] 위치만 보내면 PX4 위치 제어는 순수 P 제어라(`PositionControl.cpp` 124-138행, `MPC_XY_P` 0.95) 일정 속도 v의 목표를 v / 0.95, 약 1.05 s 뒤처져 따른다([추정] 선형 근사). 1-2 m/s에서 1.1-2.2 m이고 b(수십 cm 아래로 예상)보다 훨씬 크다. 위치 setpoint와 함께 온 유한한 `velocity`는 feedforward로 더해지고 P 항이 그 위에 더해진다(`PositionControl.cpp`의 `_positionControl` 125-137행, `addIfNotNanVector3f`). 그래서 feedforward를 실으면 정상 지연이 사라지고 남는 것은 표본 나이 상한 0.1 s와 tick 0.05 s에 여유 0.05 s를 더한 0.2 s x v(1-2 m/s에서 0.2-0.4 m)다.
- [소스] `target_timeout`과 `COM_OF_LOSS_T`(1.0 s, `config/px4/sitl_params.env`)는 서로 의존하지 않는다. PX4가 보는 것은 Offboard 신호의 지속이고 표적 표본이 아니며, 표적이 사라져도 발행은 끊기지 않는다. 1.0 s는 20 Hz 표본 20개 분량이라 산발 손실과 tick 지터에 오탐이 없다([추정]).
- `target_fresh_age`가 0.1 s보다 작으면 정상 지터에도 신선하지 않은 tick이 생겨 feedforward가 깜박인다. `target_fresh_age`를 0.1 s로 조여 계약이 허용하는 최악 지연(`target_fresh_age` + tick, 0.15 s)을 L 0.2 s 안에 넣는다. 비교한 다른 안은 `target_fresh_age`를 0.2 s로 둔 채 L만 0.25 s 이상으로 키우는 것이고, 그 안에서는 feedforward 누락 같은 작은 퇴행이 판정 여유에 가려진다. R3 판단 기준에 따라 `target_fresh_age`와 L을 함께 올리는 것은 이 안과 다르다(표본 나이 상한과 판정이 같은 식으로 묶여 있다).
- feedforward는 시나리오 표적 속도를 낮추거나 판정을 넓히지 않고 맞추는 길이다. 위치만 보내는 안은 판정 상수가 `MPC_XY_P`에 묶여 계약 파라미터가 하나 늘고, 시나리오 속도를 0.5 m/s 아래로 낮춰야 해 `NO_TARGET_MOTION` 단정이 약해진다.
- [소스] `position_setpoint`는 유한하고 float 범위 안인 값만 받고(`idsim_common`의 `px4_setpoint.cpp`), 아니면 어댑터가 짝 전체를 내지 않는다(`src/px4/outputs.cpp`의 `to_px4_messages`). 같은 값이 매 tick 오면 `COM_OF_LOSS_T` 뒤 Offboard 손실 failsafe가 되어 원인이 FAILSAFE나 EXTERNAL_MODE_CHANGE로 보고된다. 걸러야 할 것은 로컬 NED 값이고 world ENU 값에서 로컬 값은 그 tick의 기준을 거쳐야 정해진다. float32는 PX4 메시지의 성질이기도 하므로 float32 술어는 px4 어댑터인 `Px4FramePort`에 둔다. 어댑터가 속도만 빼면 core가 낸 출력과 나간 메시지가 달라지고 core 단위 테스트로 볼 수 없으므로, 속도를 싣지 않는 판단은 값 없음을 받은 core가 한다.
- 좌표 상한의 근거: [소스, 실행하지 않음] PX4 위치 제어에는 위치 크기 제한이 없다. 수평 성분이 약 1.8e19 m(float 최댓값의 제곱근)를 넘으면 `ControlMath::constrainXY`의 norm이 inf가 되어 수평 속도 setpoint가 0이 된다(`ControlMath.cpp` 116-125행, `Vector.hpp` 105-108행). 기체는 오류 없이 멈추고 goal은 ITEM_TIMEOUT으로 끝난다. float 최댓값 근처에서는 NaN이 생겨 `PositionControl::update`가 실패하는 길이 있다([추정]. `MulticopterPositionControl.cpp` 575-598행). 그래서 float32 술어만으로는 PX4의 동작이 확인된 범위를 묶지 못하고, 미션 값에 계약 상한을 둔다. 1e6 m는 float32의 값 간격이 0.0625 m 이하로 남는 범위(2^20 m 미만)이고 위 한계보다 13자리 작다. 사슬(쟁점 4)의 수평 결과는 구면 위의 거리라 world 좌표가 상한 안이면 로컬 값도 float 범위 안이다([추정]. 계산으로 확인하지 않았고 float32 술어가 안전망이다). 상한은 올리는 쪽이 호환된다. 표적 위치는 상한 검사를 받지 않으므로 float 범위 안의 매우 큰 표적 위치는 위 PX4 동작에 닿을 수 있다(SITL 표적은 생성기의 좌표 상한 10000 m 안이다. 쟁점 1). 1e6 m는 px4-engineer의 확인을 받지 않았다(px4-engineer는 1e7을 예로만 들었다). 1e6 m에서 EKF와 로컬 위치의 float32 정밀도, 그리고 float32 값 간격 0.0625 m보다 작은 `acceptance_radius_m`의 도달 판정 안정성은 다루지 않았다. S5 칸 명세에서 px4-engineer가 값과 이 두 점을 확인한다. 값은 그 확인 전까지 그대로 둔다.
- 표본 하나로 완료하면 GNSS 잡음이 실린 위치에서 경계 근처 조기 완료가 난다. 3개 연속은 약 0.15 s로 비용이 작다. TAKEOFF는 1a 고정이라 표본 하나 그대로다.
- TARGET_LOST에서 발행만 멈추면 `COM_OF_LOSS_T` 뒤 offboard 손실 Land가 걸린다. 기체는 정상이므로 취소와 같은 Hold가 맞다.
- 직전 setpoint의 yaw는 결정적이라 단위 테스트와 리플레이 판정이 실행마다 같고, LOITER의 "직전 setpoint 유지"와 같은 뜻이다.

## 쟁점 9. RTL 항목과 SITL 파라미터

결정
- RTL은 모드 명령 항목이다. `docs/interface.md`의 "LAND 항목" 절을 "모드 명령 항목(LAND, RTL)" 절로 넓히고 LAND의 규칙을 그대로 쓴다.

| 항목 | 명령 | 확인할 모드 | 확인 전 | 확인 전의 거부 ack | `mode_confirm_timeout` 안에 미확인 | 확인 뒤 이탈 | 완료 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LAND | NAV_LAND(21) | AUTO_LAND | 이탈 판정 없음 | 끝내지 않는다. 재전송을 이어 간다(1a 그대로) | 정리 없이 ABORTED, REASON_MODE_SWITCH_FAILED(1a 그대로) | EXTERNAL_MODE_CHANGE, failsafe이면 FAILSAFE | 지상 DISARMED 3회 |
| RTL | NAV_RETURN_TO_LAUNCH(20) | AUTO_RTL | 이탈 판정 없음 | 실패 fallback | 실패 fallback | 같다 | 지상 DISARMED 3회. `nav_state`는 보지 않는다 |

- "LAND의 규칙을 그대로 쓴다"의 예외는 위 표의 두 열(거부 ack, 미확인)뿐이다. LAND에는 정리 분기가 없고 RTL에는 실패 fallback의 정리가 있다.

- 실패 fallback: RTL 항목에서 AUTO_RTL 확인 전에 NAV_RETURN_TO_LAUNCH의 거부 ack(ACCEPTED와 IN_PROGRESS가 아닌 결과 모두. Offboard 전환(P5)의 거부 ack와 같은 뜻이다)를 받거나, 항목 시작부터 `mode_confirm_timeout` 안에 AUTO_RTL이 확인되지 않으면 정리(RTL 실패의 정리)로 들어가고 결과는 ABORTED, REASON_MODE_SWITCH_FAILED다. 새 reason은 더하지 않는다. 모든 실패 fallback은 Land로 모이고 RTL은 명령 항목으로만 쓴다.
- RTL 실패의 정리는 `docs/interface.md` "정리"와 "정리의 상한" 절의 규칙(분기 고르기, 한 tick의 순서, 발행 규칙, 상한, 정리 중에 온 cancel은 결과를 바꾸지 않는다)을 그대로 쓰고 하나만 다르다. 공중 분기에서 Hold를 보내지 않고 바로 취소의 Hold 실패 뒤와 같은 Land 경로로 간다(NAV_LAND를 재전송하고, AUTO_LAND를 처음 관측하거나 `mode_confirm_timeout`이 지나면 발행을 멈추고 끝낸다). 지상 분기에서 공중으로 돌아갈 때도 Land 경로다. 분기별 동작은 아래와 같다.

| 정리 첫 tick의 기체 | 동작 | 끝난 뒤 기체 상태 |
| --- | --- | --- |
| 공중 ARMED | NAV_LAND 재전송. 발행 중이었으면(RTL이 거부되어 OFFBOARD로 남은 기체) AUTO_LAND를 처음 관측할 때까지 발행을 유지한다 | 보통 AUTO_LAND로 내려오는 중이고 PX4가 착지 뒤 자동 disarm한다. AUTO_LAND를 확인하지 못했으면 `detail`에 적는다 |
| 지상 ARMED, 또는 이 goal이 arm을 보낸 지상 DISARMED | 지상 disarm 분기(1a 그대로) | 보통 지상 DISARMED. disarm이 확인되지 않았으면 `detail`에 적는다 |
| 이 goal이 arm을 보내지 않은(`[RTL]`) 지상 DISARMED | 아무것도 보내지 않는다 | 지상 DISARMED |
| 공중 DISARMED | 아무것도 보내지 않는다 | 공중 disarm(추락했을 수 있다) |

- RTL 실패의 정리는 어떻게 끝나든(Land 경로의 관측과 미확인, 지상 disarm의 확인과 미확인, 정리할 것 없음, 상한, 정리 중의 상태 끊김과 공중 DISARMED) reason이 REASON_MODE_SWITCH_FAILED이고 정리 결과는 `detail`에만 적는다("정리" 절의 "reason은 원래 실패 사유를 유지한다"를 그대로 따른다. REASON_DISARM_FAILED, REASON_LINK_LOST, REASON_FAILSAFE로 바꾸지 않는다. `docs/interface.md` 589행은 MODE_SWITCH_FAILED와 DISARM_FAILED만 이름을 들므로, LINK_LOST와 FAILSAFE로 바꾸지 않는 근거는 구현이다: `mission_runner.cpp` `finish`의 1156-1160행이 취소가 아닌 정리의 reason을 `cleanup_reason_`로 유지하고, `transition_cells.tsv` 199, 200, 206, 207, 213, 214행의 `CLEANUP.ITEM_TIMEOUT.*`가 같은 규칙을 칸으로 고정한다). 정리 중 feedback의 `phase`는 실패한 단계의 것인 `PHASE_WAITING_MODE`이고 `item_type`은 RTL이다.
- `detail`은 실패 원인 뒤에 `; cleanup: `과 정리 결과를 잇는다. 실패 원인은 거부이면 `NAV_RETURN_TO_LAUNCH rejected: <ack 결과>`, 미확인이면 `mode_confirm_timeout: AUTO_RTL not confirmed`를 담는다. Land 경로의 정리 결과는 취소의 Land 경로와 같은 형식(`<이유>; Land sent, <결과>`)이라 `RTL not confirmed`로 시작하고 `; Land sent, <결과>`를 포함한다(거부와 미확인 모두). 지상 분기 뒤 공중으로 재진입하는 칸(`CLEANUP.RTL_FAILURE.GROUND`의 ENTER_AIR -> AIR_LAND)의 `detail`은 `RTL not confirmed; air re-entered after ground branch; Land sent, <결과>`다.
- RTL 항목에서 같은 tick에 겹칠 때: 식별 불일치, 상태 끊김, 공중 DISARMED가 실패 fallback보다 앞이다. AUTO_RTL 3회 확인이 난 tick에 거부 ack도 함께 있는 경계와, AUTO_RTL 3회 확인과 `mode_confirm_timeout`이 같은 tick인 경계는 S2가 LAND 항목의 지금 순서를 RTL에도 그대로 쓴다. 확인과 만료의 경계는 `docs/interface.md` 종료의 충돌 규칙("같은 tick에 만료와 기다리던 확인이 함께 정해지면 만료가 이긴다")과 어긋나 정해지지 않았다. 확인 tick의 거부 ack는 계약이 정하지 않았고(계약은 만료와 확인만 정한다), 구현은 LAND 항목(`step_land`)이 확인으로 대기 명령을 지워 그 tick의 거부 ack를 보지 않고, `prepare_offboard`는 같은 tick의 거부 ack를 확인보다 먼저 본다. 후보 (u)가 이 경계 tick도 함께 본다(B10 전에 px4-engineer, ros2-engineer와 정한다. 1a 고정 계약 영향 후보 (u)). S2는 LAND의 지금 순서를 쓰고 테스트와 칸은 이 두 경계 tick을 어느 쪽으로도 단정하지 않는다. S3, S4의 새 확인 지점은 계약 문장을 따른다(만료가 이긴다). 종료 단계에서 이 문장을 적용하는 쌍과, 지상 DISARMED를 보는 동안 분기의 기한을 보지 않는다는 단서는 쟁점 10에 있다. 거부 ack가 `mode_confirm_timeout`보다 앞이고(결과는 같고 `detail`만 거부 문구다), 실패 fallback이 ITEM_TIMEOUT과 완료(지상 DISARMED 3회)보다 앞이다(LAND의 "MODE_SWITCH_FAILED가 ITEM_TIMEOUT보다 먼저"와 같은 방향).
- RTL 항목의 ITEM_TIMEOUT은 LAND와 같다. NAV_RETURN_TO_LAUNCH 재전송을 멈추고, 아직 발행 중이면 발행을 멈추고, Hold도 Land도 보내지 않는다(실패 fallback을 거치지 않는다). 항목 `timeout`이 `mode_confirm_timeout`보다 짧아 확인 전에 먼저 오는 경우도 같다. 그 뒤는 PX4가 맡는다(AUTO_RTL을 확인했으면 그 귀환과 착륙, OFFBOARD였으면 offboard 손실 Land, `[RTL]` 미션이면 있던 모드에 남을 수 있다). 어느 쪽인지 `detail`에 적는다.
- RTL 항목 중의 취소는 1a 취소 규칙 그대로다(LAND 항목 중의 취소와 같다). 공중이면 Hold를 보내 귀환을 멈추고(AUTO_RTL 중의 Hold가 받아들여진다는 것은 [추정]이다. `docs/interface.md` 583행은 failsafe 중과 착륙 중만 말한다. 거부돼도 Hold 실패의 Land 경로가 덮으므로 안전 쪽이다), 기체는 그 자리(귀환 경로 위일 수 있다)에 Hold로 남는다. 내리거나 다시 귀환시키는 것은 취소를 요청한 쪽이 `[LAND]`나 `[RTL]` 미션으로 한다. 실패 fallback의 정리가 시작된 뒤에 온 취소는 결과를 바꾸지 않는다.
- `[RTL]` 미션의 시작 조건은 `[LAND]`와 같다(ARMED이고 공중).
- 목적지는 PX4 home이다. 계약 문장: "RTL은 그 기체가 마지막으로 arm하거나 이륙한 지점으로 돌아가 착륙한다. 공중 시작 미션의 RTL 목적지는 그 미션이 아니라 앞선 비행의 지점이다." `RtlItem`이나 목적지 필드는 두지 않는다.
- 계약 SITL 파라미터 표에 더하는 것(`config/px4/sitl_params.env`).

| 파라미터 | 값 | 이유 |
| --- | --- | --- |
| `RTL_TYPE` | 0 | 기본값과 같다. home이나 rally point 가운데 가까운 곳으로 직선 복귀한다. idsim은 rally point와 MAVLink 미션을 올리지 않으므로 목적지는 home이다. 2와 4는 MAVLink 미션 경로를 따른다 |
| `RTL_CONE_ANG` | 0 | 귀환 고도가 `max(현재 고도, home 고도 + RTL_RETURN_ALT)` 하나로 정해진다 |
| `RTL_RETURN_ALT` | 10 m | 1b 시험 미션 고도 5 m보다 높은 한 값. x500 기본 30 m(`rc.mc_defaults` 20행의 set-default이고 펌웨어 기본값은 60 m)는 시험 시간을 늘린다(U9) |
| `RTL_LAND_DELAY` | 0 | 기본값과 같다. 멀티콥터는 home 위에서 바로 착륙한다(MOVE_TO_LOITER -> LAND). 그래서 `RTL_DESCEND_ALT`가 쓰이는 상태를 지나지 않아 그 값은 계약 표에 넣지 않는다. -1이면 착륙하지 않아 완료 조건이 오지 않는다 |
| `COM_DISARM_LAND` | 2 s | 기본값과 같지만 RTL과 LAND 완료, 공중 종료 단계의 지상 판정의 근거라 명시한다 |
| `COM_LOW_BAT_ACT` | 2(Land) | U8. 실패 fallback은 Land라는 원칙과 맞춘다. SITL 배터리는 50%에서 멈춰 닿지 않는다 |
| `EKF2_HGT_REF` | 1 | 기본값과 같다. 높이 기준이 GNSS여야 EKF 원점의 초기 고도 잡음이 도착점에서 상쇄된다(쟁점 4, 5). 0(기압계)이면 초기 GNSS 고도 오차가 bias로 남는다 |

- 1b 시험 미션의 순항 고도는 5 m다(1a 시나리오 A와 같다. 표적 궤적의 z도 5 m). 귀환 고도는 home 고도 + 10 m다.
- F3과 F4의 RTL 항목 `timeout`은 60 s다(공칭 약 26-30 s [추정]의 2배. 착지 검출과 자동 disarm 4-5 s가 고정으로 들어간다). F3, F4 trace의 실측 최댓값이 30 s를 넘으면 다시 본다.
- F3의 home은 F2의 이륙 지점(F1의 착지 지점)이다. `tests/sitl/README.md`의 F3 설명에 적는다.
- 기체별 `px4_params`로 `RTL_RETURN_ALT`를 덮어도 계약 안으로 두는 예외는 1b에 넣지 않는다(넘김 목록).

근거
- [소스] 귀환 고도: `rtl.cpp` 471-478행. 멀티콥터에서 `RTL_LAND_DELAY` 0이면 MOVE_TO_LOITER 다음이 LAND이고(`rtl_direct.cpp` 163-184행, `_updateRtlState` 머리 163행과 MOVE_TO_LOITER 분기 `break` 184행). `RTL_DESCEND_ALT`의 직접 참조는 587행(`sanitizeLandApproach`) 하나지만, 거기서 만든 값을 233행 `loiter_altitude = min(_land_approach.height_m, _rtl_alt)`이 받아 LOITER_DOWN과 LOITER_HOLD 상태에서 쓰고 452-454행 시간 추정에서도 쓴다. 우리 경로(CLIMBING -> MOVE_TO_LOITER -> LAND)는 이 상태들을 지나지 않고 MOVE_TO_LOITER는 `_rtl_alt`만 쓰므로 결론은 같다. RTL은 착륙까지 AUTO_RTL이고, disarm 때 사용자 의도 모드가 arm을 막지 않는 마지막 사용자 의도 모드(`_nav_state_after_disarming`)로 돌아간다(`UserModeIntention.cpp`의 `onDisarm` 94-102행, 그 값을 저장하는 77-84행). 그래서 완료에서 `nav_state`를 보지 않는다.
- RTL을 실패 fallback으로 쓰면 다대에서 같은 귀환 고도의 경로가 교차한다(`COM_OBL_RC_ACT=4`의 이유와 같다).
- 거부 ack의 비대칭: LAND 항목이 확인 전에 보는 것은 `mode_confirm_timeout`, 상태 끊김, 항목 `timeout`뿐이라는 것이 1a 고정 문장이고, Land는 마지막 수단이라 거부 ack로 일찍 끝내도 갈 곳이 없다(재전송을 이어 가는 쪽이 낫다). RTL은 갈 곳(Land)이 있고, [소스] NAV_RETURN_TO_LAUNCH의 ack는 ACCEPTED와 TEMPORARILY_REJECTED뿐이며(`Commander.cpp` 1050-1061행) 거부는 ARMED에서 AUTO_RTL의 모드 요구(위치, 고도, home)가 맞지 않을 때다(`UserModeIntention.cpp` 55-59행, `mode_requirements.cpp` 126-141행). TEMPORARILY_REJECTED는 `mode_confirm_timeout` 안에 풀릴 수 있고 S1의 P6 arm은 같은 값을 재전송 대상으로 두지만(`mission_runner.cpp` 516행), RTL은 P2 gate를 지난 뒤 시작한 항목이라 거부는 위치, 고도, home 추정이 무효가 된 기체를 뜻한다고 보고 기다리지 않고 Land로 넘어간다([추정]. 거부가 3 s 안에 풀리는지는 실측하지 않았다).
- 실패 fallback이 Hold를 거치지 않는 이유: 미션이 요청한 것은 귀환과 착륙이고, Hold로 끝내면 내려오지 않은 기체가 공중에 남는다. 발행을 유지하는 이유: RTL이 거부된 기체는 OFFBOARD로 남으므로 그 tick에 발행을 멈추면 `COM_OF_LOSS_T` 뒤 offboard 손실 failsafe가 걸린다. AUTO_LAND를 관측할 때까지 발행을 유지하는 정리의 발행 규칙이 이를 막는다.
- RTL 실패의 정리를 지상 분기와 "정리할 것 없음"까지 정리 규칙 그대로 두는 이유: 실패를 정한 tick의 기체가 공중이라는 보장이 없고(확인 전에 다른 주체가 내렸을 수 있다), 분기를 따로 정의하면 "끝난 뒤 기체 상태"가 다른 정리와 갈린다.
- RTL 중 취소가 Hold인 근거: `docs/interface.md` "취소" 절은 취소를 상황(LAND 항목 중 포함)을 가리지 않고 같은 분기로 처리하고, CANCELED 뒤의 기체 상태(공중 Hold 또는 지상 disarm)가 goal이 무엇을 보냈는지에 기대지 않게 하며, 취소 뒤 동작을 고르는 필드를 두지 않는다(Land나 RTL은 운용 정책이고 취소 뒤 미션 하나로 표현된다). RTL만 취소를 받지 않거나 귀환을 이어 가게 하면 이 성질이 항목 type에 따라 갈린다.

## 쟁점 10. 공중에서 끝나는 미션(U3)

결정
- 마지막 항목이 setpoint 항목인 미션은 그 항목의 완료 tick에 `items_completed`를 N으로 올리고 종료 단계에 들어간다. 종료 단계는 발행을 유지한 채 Hold를 재전송하고, Hold를 처음 관측한 tick에 발행을 멈춘다.
- SUCCEEDED(Hold)는 ARMED이고 AUTO_LOITER이고 그 tick의 최신 `landed`가 false인 표본 3회 연속일 때만이다. 지상에서 Hold가 받아들여져도 세지 않는다.
- 종료 단계는 공중 분기, 공중에서의 Hold 실패 뒤 Land 경로, 지상 대기를 쓴다. 취소의 지상 분기는 쓰지 않는다. 지상 대기는 Hold 거부나 `hold_confirm_timeout`이 지상에서 왔을 때 들어가며 NAV_LAND를 보내지 않고, LAND 항목의 착지 뒤 규칙(`land_disarm_fallback_delay` 뒤 강제가 아닌 disarm을 재전송하며 기다린다)으로 지상 DISARMED를 기다린다. 이 disarm의 실패는 상한의 MODE_SWITCH_FAILED로 끝나고 DISARM_FAILED를 내지 않는다(REASON_DISARM_FAILED의 고정 의미 "취소 처리 중"을 건드리지 않는다).

| 종료 단계의 관측 | 결과 |
| --- | --- |
| ARMED, AUTO_LOITER, `landed` false 3회 연속 | SUCCEEDED(Hold) |
| 지상 DISARMED 3회 연속(disarm 분류의 고정 규칙으로 지상). 분기(Hold, Land 경로, 지상 대기)를 가리지 않는다 | SUCCEEDED, `detail` "ended on ground". 명령을 보내지 않는다 |
| 공중 DISARMED | ABORTED, FAILSAFE |
| 상태 끊김 | ABORTED, LINK_LOST. 그 tick의 분기가 지상 대기이고 대비책 disarm을 이미 보냈으면 강제가 아닌 disarm을 한 번 더 보낸다 |
| Hold 거부 ack 또는 `hold_confirm_timeout`, 그 tick에 공중 | Land 경로. AUTO_LAND 첫 관측이나 `mode_confirm_timeout`으로 끝나면 ABORTED, MODE_SWITCH_FAILED. `items_completed`는 N |
| Hold 거부 ack 또는 `hold_confirm_timeout`, 그 tick에 지상 | 지상 대기(결과 없음) |
| 지상 대기 중 `landed` true, ARMED가 `land_disarm_fallback_delay` 이어짐 | 강제가 아닌 disarm을 재전송한다(결과 없음) |
| 지상 대기 중 `landed`가 false로 바뀜 | Land 경로(이 정리에서 Hold가 한 번 실패했으므로) |
| 정리의 상한(`hold_confirm_timeout + 3 x mode_confirm_timeout`), 공중 | NAV_LAND 1회 뒤 ABORTED, MODE_SWITCH_FAILED |
| 정리의 상한, 지상(ARMED이고 `landed` true, 또는 분류가 지상인 DISARMED) | disarm 1회 뒤 ABORTED, MODE_SWITCH_FAILED |

- 지상 DISARMED 3회의 계수는 종료 단계 전체에 하나이고 분기가 바뀌어도 이어진다. Land 경로에서 AUTO_LAND를 보기 전에 지상 DISARMED 3회가 되어도 SUCCEEDED다. 결과는 Hold가 실패한 tick이 아니라 단계가 끝나는 tick의 관측으로 정한다(취소의 Land 경로가 지상 분기를 거쳐 CANCELED로 끝날 수 있는 것과 같은 방향이다). 대비책 disarm을 보내기 전에는 일반 계수로, 보낸 뒤에는 쟁점 11의 확인 함수로 세고, 그 뒤 Land 경로로 옮겨도 확인 함수를 유지한다.
- 지상 DISARMED를 보는 동안의 규칙: disarm 분류가 지상인 동안(첫 지상 DISARMED 표본부터 다음 ARMED 표본 전까지. 식별 불일치 tick은 분류를 바꾸지 않는다)에는 분기의 거부 ack, 분기의 기한(`hold_confirm_timeout`, Land 경로의 `mode_confirm_timeout`), 분기 이동, AUTO_LAND 관측을 보지 않는다. 그 동안 보는 것은 상태 끊김, 정리의 상한, 지상 DISARMED 3회뿐이다. 첫 지상 DISARMED 표본의 tick에 발행을 멈추고 대기 중인 명령(Hold, NAV_LAND, 대비책 disarm)을 지운다. ARMED 표본이 다시 오면(쟁점 11의 전제 밖) 지상 DISARMED 계수는 0으로 돌아가고 분기의 판정을 원래 기준 시각으로 이어 간다. 지운 명령의 재전송은 되살리지 않고, 분기 이동이 보내는 명령과 아직 보내지 않은 대비책 disarm만 규칙대로 보낸다. 분기의 기한이나 상한이 끝낸다.
- 같은 tick의 만료와 확인(`docs/interface.md` 종료의 충돌 규칙의 "만료가 이긴다")은 종료 단계에서 두 쌍에 적용한다: `hold_confirm_timeout`과 Hold 3회째(만료가 이겨 Land 경로로 간다), 정리의 상한과 모든 확인(Hold 3회째, 지상 DISARMED 3회째. 상한이 이겨 ABORTED다). 분기의 기한은 그 분기가 기다리던 것(Hold 확인, AUTO_LAND 관측)의 기한이고 지상 DISARMED 3회의 기한이 아니므로, 분기의 기한과 지상 DISARMED 3회째는 겹치지 않는다(위 규칙으로 그 tick에 분기의 기한을 보지 않는다). 그래서 지상에서 `hold_confirm_timeout`이 지나는 tick에 지상 DISARMED 3회째가 오면 지상 대기를 거치지 않고 그 tick에 SUCCEEDED이고, Land 경로의 `mode_confirm_timeout` tick에 3회째가 와도 SUCCEEDED다. 보지 않는 판정은 그 tick에 정해진 것이 아니므로 "ABORTED 사유, 완료, 취소 순"의 대상이 아니다(계약 문장에 이 단서를 적는다. 후보 (u)). 모드 명령 항목(LAND, RTL)은 1a 순서를 지켜 실패 fallback과 기한이 완료(지상 DISARMED 3회)보다 앞이고(쟁점 9), 종료 단계만 이 규칙을 쓴다. Hold 3회째와 같은 tick의 Hold 거부 ack는 단정하지 않는다(후보 (u)).
- 정리의 상한에서 지상과 공중은 그 tick의 신뢰 표본으로 정한다. 그 tick의 표본이 식별 불일치면 disarm 분류가 지상이면 지상, 아니면 분기로 정한다(지상 대기는 지상, 그 밖은 공중). 이미 DISARMED인 기체에 보낸 disarm은 ACCEPTED로 끝나고 해가 없다([소스] `Commander.cpp` 640-642행, 976-981행).
- 지상 대기에서 상태가 끊겼을 때 대비책 disarm을 보내기 전이면(PX4 자동 disarm을 기다리는 중) 명령을 보내지 않는다.
- 종료 단계에서 Px4Timestamp를 만들지 못하면 그 tick의 출력을 버리고 ABORTED, INTERNAL로 끝난다. `items_completed`는 N이고 기체 상태는 보장하지 않는다(지상 ARMED로 남을 수 있다).

- 발행: 지상 대기에서 아직 OFFBOARD이고 발행 중이면 setpoint를 지상 setpoint(그 tick의 위치, 어댑터가 지상 오프셋을 더한다)로 바꾼다. 첫 DISARMED 표본에서 발행을 멈춘다.
- 종료 단계에 지상 ARMED로 들어가도 같은 규칙이다: Hold를 보내고, 지상의 Hold 관측은 세지 않으며, 기다리는 근거는 PX4 자동 disarm(`COM_DISARM_LAND`)이다. 그래서 공중 종료 미션의 SUCCEEDED 뒤 기체 상태는 "공중 Hold" 또는 "지상 DISARMED"이고 "지상 ARMED"는 없다.
- 위험(계약 문장으로 적는다): 마지막 setpoint 항목의 목표가 지면 높이면 항목 실행 중 착지하고 `COM_DISARM_LAND` 뒤 PX4가 disarm할 수 있다. 항목 완료와 이 disarm 가운데 무엇이 먼저 오는지는 경합이고, disarm이 먼저면 실행 중의 지상 disarm 분류(1a 규칙)로 끝난다. 계약은 지면 높이 목표의 결과를 보장하지 않는다. 1b 시나리오에는 지면 높이 목표가 없고 단위 테스트로 덮는다.
- 종료 단계 중의 cancel은 결과를 바꾸지 않는다. feedback의 `phase`는 `PHASE_EXECUTING`, `item_index`는 마지막 항목이다. result의 `last_item_index`는 N-1이다.
- Hold 지점은 마지막 setpoint가 아니라 Hold로 바뀐 순간의 위치에 제동 거리를 더한 점이다([소스] `loiter.cpp` 111-112행). 계약 문장에 적는다. 마지막 항목이 표적 추종이면 표적 쪽으로 앞선다.
- 마지막 setpoint 항목의 높이 하한은 미션 검증에 두지 않는다. world ENU z는 지면 높이가 아니고 Executor는 지형을 모른다.
- 끝없는 Hold: SITL에서는 배터리와 failsafe가 닿지 않아 영원히 머문다. 끝점이 겹치지 않게 하는 것은 Phase 3 Fleet 계획의 책임이다(넘김 목록).
- core: `CleanupCause`에 미션 종료, 분기에 지상 대기 하나를 더한다. 종료 단계의 분기 고르기는 취소, ITEM_TIMEOUT, 준비 단계 실패의 분기 고르기와 따로 둔다. `kDisarmFailed`는 종료 단계에서 나오지 않는 불가능 칸이다. LAND 항목의 착지 뒤 fallback 계산은 함수로 빼서 지상 대기와 함께 쓴다(LAND 항목의 동작은 그대로).

근거
- [소스] offboard 손실 failsafe는 사용자 의도 모드가 offboard 신호를 요구할 때만 걸리고 Hold는 요구하지 않는다(`failsafe.cpp` 664-666행). Hold 확인 뒤 발행을 멈춰도 아무 일이 없다. [실측] 1a 시나리오 D와 60 s 관찰이 같은 상태다.
- [소스] ARMED 중 모드 변경은 `canRun`만 보고 AUTO_LOITER의 요구 조건에 "공중"이 없다(`UserModeIntention.cpp` 44-91행, `mode_requirements.cpp` 110-124행). Hold는 `landed`이면 IDLE setpoint만 낸다(`loiter.cpp` 77-95행). 착지 자동 disarm은 모드를 보지 않고 이륙 이력과 `landed`가 `COM_DISARM_LAND` 이어짐으로 걸린다(`Commander.cpp` 2279-2306행, 이륙 이력 2136-2140행). 지상 Hold 3회를 SUCCEEDED로 세면 결과는 Hold인데 2 s 뒤 기체가 지상 DISARMED가 되어, Hold라고 믿은 소비자의 공중 시작 미션이 PRECONDITION_FAILED가 된다.
- 지상에서 Hold가 거부될 때 Land 경로로 가면 곧 스스로 disarm할 정상 기체를 실패로 보고한다. 착지 뒤의 disarm fallback은 PX4 자동 disarm이 꺼진 경우에도 기체를 정해진 상태로 보낸다.
- [소스] 1a 정리의 분기 고르기는 ARMED이고 `landed` true이면 지상 분기, `arm_sent`가 참이면 DISARMED여도 disarm 재전송으로 간다(`rules.cpp` 187-197행). 종료 단계에 그대로 쓰면 지상 분기와 DISARM_FAILED로 가므로 별도 선택 규칙이 필요하다.
- [소스] DISARMED에서는 TERMINATION 말고는 모드 변경이 받아들여져 Hold 거부 ack가 나오지 않고(`UserModeIntention.cpp` 55, 73-74행, `Commander.cpp` 913-932행), Hold 3회는 ARMED를 요구하므로 지상 DISARMED 기체에서 분기의 기한이 지나도 새 정보가 없다. NAV_LAND는 force로 요청되어 DISARMED에서도 받아들여진다(`Commander.cpp` 1093-1104행). [추정] 그래서 disarm 직후 처리된 재전송이 `nav_state`가 AUTO_LAND인 DISARMED 표본을 만들 수 있다(DISARMED의 `nav_state`가 사용자 의도 모드를 따른다는 것은 재지 않았다). 이 표본을 AUTO_LAND 관측으로 세면 지상 DISARMED 기체의 결과가 재전송 위상에 따라 ABORTED와 SUCCEEDED로 갈린다. 지상 DISARMED를 보는 동안 분기의 판정을 멈추면 결과가 정해진다.
- Land 경로에서 지상 DISARMED 3회가 AUTO_LAND 표본 없이 오는 것은 보낸 NAV_LAND가 모두 처리되지 않았을 때뿐이라 드물고([소스] 자동 disarm은 `landed`가 `COM_DISARM_LAND` 이어진 뒤다, `Commander.cpp` 2285-2302행), 그때 기체는 지상 DISARMED다(공중의 강제 disarm은 분류가 공중이라 FAILSAFE로 간다). SUCCEEDED의 끝 상태 "공중 Hold 또는 지상 DISARMED"에 맞는다.
- Offboard 유지는 기체 상태를 Executor 프로세스 생존에 묶는다. 자동 RTL이나 LAND는 운용 정책을 Executor가 정하는 것이고 미션에 RTL이나 LAND를 넣으면 같은 일이 된다.

## 쟁점 11. 지상 취소의 disarm 확인과 /clock 지연 실측

결정
- 취소 지상 분기의 DISARMED 확인은 1a 규칙(tick 조건, timestamp 조건, 서로 다른 timestamp 3회 연속)을 그대로 쓴다. ack timestamp 기준은 쓰지 않고, snapshot에 `AckSample.timestamp_us`를 더하지 않는다.
- 유지 조건: 처리 전 DISARMED 표본이 확인에 들어갈 수 있는 창은 arm이 처리되기 전이고, 그 폭은 W_arm(arm에 실은 timestamp에서 그 arm의 `vehicle_command_ack.timestamp`까지) 이하다. 잘못된 확인에는 이 창 안에 서로 다른 timestamp의 DISARMED `vehicle_status` publish 3개, 즉 publish 간격 두 개가 들어가야 한다. W_arm이 창 안의 publish 간격 두 개보다 좁으면 1a 규칙을 유지한다. 이 조건은 쟁점 12의 순서 불변식(지상 arm 진입에서 arm은 마지막 DO_SET_MODE(Offboard 전환)를 보낸 tick보다 뒤의 tick에 받은 그 명령의 ack가 있고 OFFBOARD 3회 연속 확인이 된 tick에만 보낸다)에 기댄다. 그래야 queue에서 arm 앞에 이 goal이 보낸 명령이 없고, 창 안의 trigger에 이 goal이 보낸 명령의 처리가 끼지 않는다. PX4 내부 명령도 trigger가 되지만 이 goal이 막을 수 없고, 1a 실행의 두 arm 창 근처에는 없었다([실측] 아래). 불변식의 전제는 W_DO_SET_MODE가 `command_resend_period`(0.5 s)보다 작다는 것이다. ack에 명령을 가르는 값이 없어 앞선 재전송의 ack와 마지막 전송의 ack를 내용으로 가르지 못하고, FIFO와 도착 tick으로만 가른다. W_DO_SET_MODE가 `command_resend_period`의 두 배보다 작으면 전제가 깨져도 arm 앞에 남는 것은 DO_SET_MODE 하나이고, 이는 창 안의 trigger를 하나 늘릴 뿐이다. 판단은 W의 상한 하나가 아니라 W_arm과 그 창 안의 publish trigger(처리한 명령, 500 ms 주기, 상태 변화)로 한다.
- 이 조건이 깨지는 관측이 나오면 "받아들여진 disarm ack의 PX4 `timestamp` 이상인 DISARMED 표본만 센다. ack가 없으면 1a 규칙"으로 바꾸고, `AckSample.timestamp_us`(`vehicle_command_ack.timestamp`)를 snapshot 헤더에 더한다(px4-engineer 필수 승인). "ack 뒤에 받은 표본만 센다"는 쓰지 않는다(토픽 간 수신 순서가 보장되지 않는다). 다시 볼 시점은 Phase 2 다중 스택 부하다("넘김 목록").
- 전제: 이 goal 밖의 명령 출처(GCS 등)가 기체를 arm하지 않는다.
- 같은 확인 함수를 공중 종료 단계의 지상 대기 disarm(쟁점 10)에도 쓴다. PX4 자동 disarm은 Executor가 명령을 보내지 않았으므로 이 창과 무관하다.
- L(gz `/clock`과 ROS `/clock`의 도착 차)은 유지 조건이 깨져 원인을 나눠야 할 때만 잰다. 별도 `clockskew` 측정 항목은 두지 않는다. sitl gate가 이미 보는 `now - vehicle_status.timestamp`의 분위수를 `verdict.json`에 `recorded_only`로 남긴다. 표적 어댑터가 생긴 뒤 `TargetState` 나이(R3)와 `/clock` 간격도 같은 방식으로 남긴다.

근거
- 위험은 "disarm 처리 전에 publish된 DISARMED 표본이 timestamp 조건을 통과하는 것"이고 그 창은 L이 아니라 명령에서 ack까지다. [소스] Commander는 루프마다 `vehicle_command` 하나를 FIFO로 처리하고, 한 주기에 ack를 먼저, `vehicle_status`를 나중에 publish한다(`Commander.cpp` 1887-1899행, 2674-2680행, 1930-1945행).
- [소스] 처리 전 DISARMED 표본이 계수에 들어가는 길은 `arm_sent` 경합뿐이다. 정리의 분기 고르기에서 `in_ground_branch`로 들어온 DISARMED는 실제 상태이고(`rules.cpp` 187-197행), 지상 ARMED에서 보낸 disarm의 처리 전 표본은 ARMED라 계수를 0으로 되돌린다(`rules.cpp` 207-216행). arm에 실은 timestamp는 disarm의 것 이하이고 두 명령은 FIFO이므로, 해로운 표본의 timestamp는 (첫 disarm의 timestamp, arm ack timestamp) 안에 있고 이는 (arm의 timestamp, arm ack timestamp]에 들어간다. 그래서 disarm 명령의 W는 판단에 필요하지 않다.
- [소스] 창 안의 publish trigger: 처리한 명령마다 즉시(`Commander.cpp` 1897-1899행), 500 ms 주기와 상태 변화(1931-1945행). 처리할 명령이 없으면 루프는 10 ms 잔다(1977-1980행, `Commander.hpp` 217행). core는 OFFBOARD 3회 확인 뒤 마지막 DO_SET_MODE 전송 tick보다 뒤의 tick에 받은 그 명령의 비거부 ack가 있을 때만 arm을 보낸다(`MissionRunner::prepare_offboard`, `prepare_offboard_ack`, `arm_if_offboard_acked`). 확인 직전 tick에 보낸 재전송이 처리되기 전에 arm이 나가는 일을 tick 주기(50 ms)가 W보다 길다는 시간 여유가 아니라 순서로 막는다. 그 여유는 SITL 1 스택에서만 맞는 가정이라(다중 스택 CPU 경합과 실기체 링크 지연에서는 근거가 없다) 근거로 쓰지 않는다.
- [소스] FIFO이므로 잘못된 확인이 나와도 disarm은 arm 뒤에 처리된다. 기체가 지상 ARMED로 남는 것은 그 disarm이 처리되지 않거나(거부 또는 손실) 다른 출처가 arm할 때뿐이다.
- [실측] `run_sitl.sh` 1회(SITL lockstep)의 ULog에서 arm, DO_SET_MODE, NAV_LAND의 W가 모두 16 ms 이하이고 W_arm은 8 ms 이하다(arm 표본 2개). ULog의 `vehicle_command.timestamp`는 실은 값 이하이므로 이 값은 상한이다. 같은 ULog의 지상 DISARMED 구간에서 명령과 필드 변화 없이 수십 ms 간격의 즉시 publish가 이어진 곳이 있어(원인은 ULog로 정해지지 않는다), W 상한 하나로는 조건이 되지 않는다. 두 arm 창 근처(63.5-65.5 s, 94.8-95.6 s)에는 PX4 내부 명령이 없었고, 두 번 모두 arm을 보내기 전에 앞의 DO_SET_MODE의 ack가 와 있었다.
- 처리 전 표본이 계수에 들어간 기록은 1a 시나리오가 취소 지상 분기를 타지 않아 관찰할 기회가 없다. 새 시나리오를 만들지 않고(U6) 위의 구조 논증과 1a 실측(arm 직후 disarm 10회가 모두 DISARMED)으로 대신한다.
- gate에 얹은 기록은 별도 실행이 없어 비용이 0이다(U6의 산출물 최소 원칙).

## 쟁점 12. snapshot 헤더와 core 구조 변경

결정
- snapshot 헤더(px4-engineer 필수 승인)에 더하는 것을 한 PR에 묶는다.

| 항목 | PX4 쪽 대응 |
| --- | --- |
| `PositionSample.timestamp_us` | `vehicle_local_position.timestamp`(`timestamp_sample`이 아니다). "서로 다른 표본 3개"를 이 값으로 가른다 |
| `PositionSample.xy_valid` | `vehicle_local_position.xy_valid` |
| `NavMode::kRtl` | `NAVIGATION_STATE_AUTO_RTL`(5) |
| `AckCommand::kNavRtl` | `VEHICLE_CMD_NAV_RETURN_TO_LAUNCH`(20). 지금의 ack target 필터를 그대로 둔다(Navigator도 같은 명령을 낼 수 있다) |
| `CommandKind::kNavRtl` | `idsim_common::VehicleCommandBuilder::rtl` |
| `FramePort` | `world_to_local`(점), `world_velocity_to_local`(벡터). 둘 다 값 없음을 돌려줄 수 있다(벡터 쪽은 S6에서 바꾼다). 기준과 유효 술어, float32 술어는 쟁점 4 |
| `TargetSample`과 표적 맵 | PX4 메시지가 아니다. 시각 필드는 ROS 시각임이 이름에 드러나는 `stamp_ns` |
| `SetpointOut`의 속도 | `velocity_valid`(기본 false)와 로컬 NED 속도(m/s). false면 어댑터가 `velocity`를 NaN으로 낸다(쟁점 8) |

- 승인 조건(px4-engineer): (1) `FramePort`의 유효 술어(쟁점 4)를 기준을 읽는 px4 어댑터 함수에 둔다. (2) 기준은 그 tick의 `Snapshot.position`과 같은 표본에서 읽는다. (3) `TargetSample`의 시각 필드 이름이 ROS 시각임을 드러낸다. (4) 헤더 머리 주석의 "어댑터가 채울 것"과 "출력에 할 것" 표를 같은 PR에서 고친다(`NAVIGATION_STATE_AUTO_RTL -> kRtl`, `VEHICLE_CMD_NAV_RETURN_TO_LAUNCH -> kNavRtl`, `timestamp_us <- timestamp`, `xy_valid <- xy_valid`, `kNavRtl -> rtl`, `FramePort`의 기준 필드와 유효 술어, `SetpointOut` 속도 -> `trajectory_setpoint.velocity`).
- 더하지 않는 것: `ref_timestamp`, `xy_reset_counter`, `z_reset_counter`(원점 변경 WARN은 노드가 기준을 읽을 때 남기고, EKF reset은 프레임이 아니라 추정을 옮긴다), `heading_good_for_control`(1a TAKEOFF와 같은 규칙), world ENU yaw의 기준 의존 변환(축 치환이고 자오선 수렴은 무시한다).
- core 구조(ros2-engineer): `EntryPlan`(지상 arm, 공중 Offboard, 모드 명령), setpoint 항목의 type별 처리(setpoint, 완료, TARGET_LOST만 내고 감시 표, ITEM_TIMEOUT, 정리 진입은 공통), 모드 명령 항목 처리의 일반화(보낼 명령, 확인할 모드), 공중 종료 단계(쟁점 10). 전이 표는 px4-engineer 필수 승인이다.
- 상태기 PR은 여섯이고 아래 순서로 하나씩 머지한다(같은 `mission_runner.cpp`와 칸 목록을 고치므로 병렬로 하지 않는다). PR마다 px4-engineer의 칸 명세 표 -> ros2-engineer의 테스트와 구현 -> px4-engineer 대조 순서이고 칸 목록 diff를 낸다.

| PR | 범위 | runner가 새로 받는 미션 |
| --- | --- | --- |
| S1 | 지상 arm 진입의 arm 순서 불변식과 ack 대기 구간(아래), `detail` 구분, 단위 테스트 사례(아래), 쟁점 11 근거 문장. 첫 커밋은 테스트만 고친다: flow 칸 테스트(`test_runner_flow_cells.cpp`)의 `expect_cell`에 사건 직전 `edges().size()`를 시작 인덱스로 넘기고, `test_runner_conflicts.cpp`의 대표 취소 칸 두 테스트에 `expect_cell`을 더한다(이 커밋에서 core 소스와 칸 목록은 그대로다) | 없음. 1a 미션의 P5 칸이 바뀐다 |
| S2 | 첫 커밋은 검증 함수의 분리다(아래 "미션 제한의 두 자리"). 순서 규칙을 `validate_mission_contract`로(쟁점 6), `EntryPlan`의 두 갈래(지상 arm, 모드 명령), 모드 명령 항목 처리의 일반화와 RTL 항목, Land fallback(쟁점 9) | `[RTL]`, RTL로 끝나는 미션 |
| S3 | 공중 종료 단계(쟁점 10) | 마지막 항목이 setpoint 항목인 미션(`[TAKEOFF, LOITER]`) |
| S4 | `EntryPlan`의 공중 Offboard 갈래와 그 준비 조건, 감시 면제, P4에서 먼저 본 OFFBOARD(쟁점 7) | 첫 항목이 LOITER인 미션 |
| S5 | `step()`이 `FramePort`를 받는다. 첫 커밋은 `step()` 시그니처, 테스트 harness의 호출부, 노드의 임시 port만 바꾼다(동작 무변경). 이어서 `Px4FramePort` 점 변환의 float32 술어와 `fits_float32` 공개(쟁점 4, 14), 좌표 상한과 GOTO(쟁점 8). 1a의 type(TAKEOFF, LOITER, LAND)만 든 미션에서 `FramePort`를 부르지 않음을 단정하는 단위 테스트를 둔다(부르면 실패하는 port) | GOTO |
| S6 | core가 `Snapshot.targets`를 읽는다. `world_velocity_to_local`의 반환형과 벡터 변환의 float32 술어(헤더 변경, 쟁점 4), TRACK_ENTITY, TARGET_LOST와 그 정리, 속도 feedforward(쟁점 8) | TRACK_ENTITY |

- 순서의 이유: S1은 1a가 받던 미션의 결과와 `/fmu/in` 출력을 바꾸려는 유일한 변경이라 미덮임 0인 1a 칸 목록만을 기준으로 먼저 대조한다. B8b에서 넘어온 테스트 수정 둘은 그 대조에 쓰는 도구의 수정이라 첫 칸 목록 diff보다 앞에 둔다. S2-S4는 있는 항목 type(TAKEOFF, LOITER, LAND)으로 구조(모드 명령 항목, 종료 단계, 진입 방식)를 먼저 넣어 diff를 구조 변경에 한정하고, S5와 S6은 그 위에 항목 type을 더해 type마다의 칸(쟁점 13의 tick 순서 겹침)을 낸다. `EntryPlan`은 S2가 `[RTL]`을 받으려면 준비 단계의 `[LAND]` 분기를 고쳐야 하므로 S2에 두 갈래로 넣고 S4는 공중 Offboard 갈래만 더한다. `FramePort`와 표적은 S5, S6에서 처음 쓰이므로 `step()` 인자는 S5에, 벡터 변환의 반환형은 속도를 처음 쓰는 S6에 바꾼다(쓰지 않는 인자를 먼저 넣지 않는다). `Event`나 칸의 이름을 바꾸는 것(LAND 전용 이름의 일반화 등)은 동작 변경과 다른 커밋으로 하고, 그 커밋의 칸 목록 diff는 이름 치환뿐이다. S2는 LAND 전용 사건 여덟(`READY_LAND`와 `LAND_*` 일곱)을 모드 명령 항목의 이름(`READY_MODE_ITEM`, `MODE_ITEM_*`)으로 바꾸고 RTL 전용 사건을 따로 두지 않는다(칸은 상태 key `ITEM.LAND`, `ITEM.RTL`로 갈린다). 정리의 Land 경로 사건(`LAND_PATH_*`)은 그대로다. S2가 더하는 사건은 `MODE_ITEM_REJECTED` 하나이고(S2에서는 `ITEM.RTL`에서만 난다), RTL 실패의 정리는 정리 원인 `RTL_FAILURE`(`CleanupCause::kRtlFailure`)다. 이 원인에서 `CLEANUP.RTL_FAILURE.AIR`(Hold를 기다리는 공중 분기)에는 닿지 않는다.
- 1a 동작의 보존: 1a가 받던 미션의 결과(status, reason)와 `/fmu/in` 출력이 바뀌도록 의도한 것은 S1뿐이다. S2-S6은 1a 미션이 지나는 코드(LAND 처리의 일반화, 착지 뒤 처리, `EntryPlan` 재구성, `step()` 호출부와 `to_setpoint_messages`, `idsim_common`의 `px4_setpoint.cpp`)를 고치므로 동작이 그대로임을 PR마다 두 겹으로 보인다. (가) 칸 목록 diff에서 1a 미션이 지나는 덮임 칸의 from, 사건, to, reason이 그대로임을 PR 본문(로컬 branch는 merge 커밋 메시지)에 적는다. 예외는 S1의 P5 칸, 이름 바꾸기 커밋, 새로 받는 미션이 닿게 되어 "불가능"에서 부류가 바뀌는 칸이다. (나) S1-S6 모두 머지 전에 로컬 `tests/sitl/run_sitl.sh`(1a 시나리오)가 통과한다. 로컬 branch에서는 CI `sitl`이 돌지 않고, 칸 목록은 core 전이만 보기 때문이다.
- goal 접수에서 달라지는 것은 INVALID_MISSION의 `detail` 문구뿐이다(status와 reason은 그대로다). S2는 계약 순서 규칙의 문구를 1a 임시 제한 문구의 앞부분과 같게 쓰고(`items[i].type TAKEOFF is allowed only as the first item`, `... LAND is allowed only as the last item`. 끝의 "in 1a"가 빠진다), 1a 제한 쪽에서 닿지 않게 되는 TAKEOFF와 LAND 위치 검사를 지운다. S5의 좌표 상한도 1a 접수가 이미 거부하던 미션의 `detail`만 바꾼다. S2에서 기대값이 바뀌는 테스트(순서를 어긴 미션에 `validate_mission_contract`가 valid라고 단정하던 `test_mission_validation.cpp`의 두 곳)는 S2 칸 명세에 적고 같은 PR에서 고친다.
- 미션 제한의 두 자리: `validate_mission`을 S2의 첫 커밋에서 둘로 나누고 그 이름은 남기지 않는다. `validate_mission_1a_goal`은 goal 접수(`screen_goal`)가 쓰고, 받는 미션 집합은 그대로 두고(닿지 않는 코드를 지우는 것만 예외) B10에서 지운다. `validate_mission_runnable`은 runner 생성자가 쓰고, 위 표의 PR마다 그 PR이 구현한 만큼 풀며, S6에서 계약 검증과 같아지면 지우고 runner가 `validate_mission_contract`를 부른다. 그래서 goal 접수가 받는 미션은 B9 동안 1a 그대로이고 B10에서 계약 검증으로 바뀐다. 단위 테스트 둘을 둔다. (1) PR마다 그 PR이 새로 받는 미션에 `validate_mission_runnable`이 valid이고 `screen_goal`이 INVALID_MISSION임을 같은 PR에서 단정한다. (2) 항목 type 여섯으로 만든 길이 4 이하의 모든 순서(1554개)에서 `validate_mission_1a_goal`이 받는 미션은 `validate_mission_runnable`도 받는다. 칸 목록의 "불가능" 근거(쟁점 13)는 runner가 실제로 부르는 검증 함수를 가리키게 적는다.
- B9와 B10의 경계: B9는 core와 px4 어댑터까지다. S5부터 노드는 `step()` 호출부만 맞춰 늘 값 없음을 돌려주는 port(노드의 익명 namespace에 둔 class 하나. 이름과 주석에 B10에서 지울 것임을 적는다)와 빈 `Snapshot.targets`를 넘긴다. 진짜 `Px4FramePort`를 넘기는 것(`to_local_position_input` 채택, 원점 변경 WARN, `world.origin`), 표적 구독, goal 접수 제한의 제거는 B10이다. 진짜 port는 `ops-N` params의 `world.origin`(devops-engineer)과 configure 거부를 함께 끌고 오고, TRACK_ENTITY는 표적 구독 없이는 노드에서 돌 수 없으므로 B9에 당기지 않는다. 승인 조건 (2)의 실제 충족은 B10 검토에서 본다. goal 접수 제한을 지우면 1a의 시나리오 B(`[GOTO]`에 INVALID_MISSION을 기대한다)와 노드 테스트의 무효 미션 사례가 깨지므로 B10이 같은 PR에서 둘을 1b 무효 사례로 바꾼다(쟁점 15).
- core 구조가 지킬 불변식(쟁점 11의 유지 조건): 지상 arm 진입에서 arm은 마지막 DO_SET_MODE(Offboard 전환)를 보낸 tick보다 뒤의 tick에 받은 그 명령의 ack가 있고 OFFBOARD 3회 연속 확인이 된 tick에만 보낸다. 이를 위해 (1) `Pending`에 마지막 전송 tick을 두고 재전송마다 갱신하며, ack는 그 tick보다 뒤의 tick에 받은 것만 이 조건에 쓴다(거부 ack는 지금처럼 MODE_SWITCH_FAILED). (2) OFFBOARD 3회 확인 tick에 확인을 고정한다(이후 계수가 0으로 돌아가도 다시 세지 않는다). DO_SET_MODE는 P5와 ack 대기 구간을 통틀어 arm을 보내기 전까지, 이 조건에 쓸 ack(마지막 전송 tick보다 뒤의 tick에 받은 비거부 ack. 이하 유효 ack)가 없는 동안 `command_resend_period`마다 재전송하고 유효 ack가 있으면 재전송하지 않는다. 확인 tick도 같다(유효 ack가 없고 주기가 찼으면 그 tick에 재전송한다). 재전송하면 마지막 전송 tick이 바뀌므로 그 뒤의 ack를 다시 기다린다. (3) ack 대기 구간은 P5 안의 하위 단계이고 칸 목록에서는 따로 된 상태 key `PREPARING.OFFBOARD_ACK`(`PrepStep::kOffboardAck`)다. stage와 feedback의 phase는 PREPARING 그대로이고 `arm_sent`는 false로 남는다. OFFBOARD 3회 확인 tick은 늘 이 상태를 거친다(유효한 ack가 이미 있으면 같은 tick에 기록이 둘이다). 새 사건은 `OFFBOARD_ACK_ACCEPTED`와 `OFFBOARD_LEFT` 둘이고, 거부 ack, timeout, 식별, 취소는 기존 사건을 새 상태 key에서 쓴다. 새 timeout을 두지 않는다(기한은 P5 진입부터의 `mode_confirm_timeout` 하나다). 대기 구간에 따로 정하는 나가는 길은 아래 다섯이고, P5 공통 출구(식별 불일치의 ABORTED, REASON_INTERNAL 등)는 1a P5 그대로다.

| 사건 | 결과 |
| --- | --- |
| 마지막 전송 뒤의 ack(거부가 아님) | arm을 보내고 P6 |
| 거부 ack | arm 없이 MODE_SWITCH_FAILED(준비 단계). DISARMED이고 arm을 보내지 않았으므로 정리할 것이 없다 |
| 이탈: 식별이 맞고 timestamp가 확인에 쓴 마지막 OFFBOARD 표본보다 큰 OFFBOARD 아닌 표본 하나 | arm 없이 MODE_SWITCH_FAILED(준비 단계). `detail`은 timeout과 구분한다 |
| `mode_confirm_timeout`(P5 진입부터, 1a 그대로) | arm 없이 MODE_SWITCH_FAILED(준비 단계) |
| 취소 | disarm 없이 CANCELED(arm을 보내지 않은 지상 disarm 분기) |

- 명령과 ack의 유실(core 전체의 규칙): `/fmu/in`의 명령과 `/fmu/out`의 ack는 best-effort라 하나가 유실될 수 있다([소스] PX4 v1.17.0 uXRCE-DDS 클라이언트의 data stream은 양방향 best-effort다). 명령 하나나 ack 하나의 유실만으로 goal이 실패하지 않아야 한다. (가) goal 결과가 정해지기 전의 명령은 그 효과를 관측할 때까지 또는 기한까지 `command_resend_period`마다 재전송한다((나)의 상태는 그 ack를 얻으면 멈춘다. 그 뒤의 진행은 주기 표본에 달린다). (나) 진행 조건이 ack처럼 주기적이지 않은 메시지에 달린 상태는 그 메시지를 다시 얻는 재전송을 기한까지 가진다. (다) ack 판정은 같은 tick의 재전송보다 앞에 두고, 진행 조건에는 마지막 전송 tick보다 뒤의 tick에 받은 ack만 쓴다. (라) 주기 표본(`vehicle_status` 등)의 유실은 timeout 여유로 견딘다. `/fmu/out/vehicle_status`는 5 Hz로 제한되고 최신 값만 오므로([소스] `dds_topics.yaml`의 `rate_limit`) 200 ms 안에 지나간 중간 상태는 보이지 않을 수 있고, 이탈 관측에 기대는 논증은 이를 셈에 넣는다. 예외는 결과가 이미 정해진 종료 tick의 1회 명령(`send_final`: 식별 불일치와 감시 행의 지상 disarm, 정리 상한의 NAV_LAND와 disarm 등)이다. 관측을 더 기다리지 않으므로 재전송하지 않고 `detail`에 확인하지 못했음을 적는다. 지금 (나)에 해당하는 상태는 지상 arm 진입의 ack 대기 하나다. 모드 명령 항목(LAND, RTL), P6의 arm, 정리의 Hold, Land 경로, 지상 disarm, 착지 뒤의 대비책 disarm, 공중 Offboard 진입의 P5는 재전송하면서 주기 표본으로 진행하고 ack는 거부 판정에만 쓴다(거부 ack가 유실되면 다음 재전송의 거부 ack나 기한이 같은 결과로 끝낸다). 진행 조건에 ack를 더하는 새 상태(쟁점 11의 ack timestamp 기준 등)는 이 규칙으로 검토한다.
- 같은 tick에 겹치면 1a P5 순위를 따른다: 거부 ack, `mode_confirm_timeout`, 이탈이 arm보다 먼저다. 취소는 1a처럼 단계 처리 뒤에 본다(`MissionRunner::step_tick`). 그래서 같은 tick에 ack와 취소가 오면 arm 판정이 먼저라 `arm_sent`가 true인 지상 arm 분기로 간다. 그 tick의 arm은 정리 진입(`begin_cleanup`)이 그 tick의 명령을 지워 나가지 않고 disarm 하나가 나간다(1a의 확인 tick 취소와 같다. arm이 PX4 queue에 들어가지 않으므로 쟁점 11의 창이 생기지 않는다). 재전송은 arm 판정 뒤에 본다(실패 판정, arm 판정, 재전송 순서). 그래서 유효 ack가 있는 tick에는 재전송이 나가지 않고, 실패나 취소로 끝나는 tick의 재전송도 나가지 않는다(취소는 정리 진입이 그 tick의 명령을 지운다).
- ack 대기를 상태 key로 가르는 이유: 같은 key(`PREPARING.OFFBOARD`)에 두면 대기 구간의 취소, 식별 불일치, 거부 ack, timeout 칸이 1a P5 칸과 이름이 같아져 덮음 테스트가 새 경로를 따로 요구하지 못한다(쟁점 13).
- 확인 고정과 이탈 규칙의 근거: [소스] DISARMED에서는 failsafe 동작을 고르지 않아(`framework.cpp` 452-455행) 지상 DISARMED의 OFFBOARD는 offboard 신호 손실로 빠지지 않는다. 대기 구간에 OFFBOARD에서 빠지는 길은 다른 출처의 모드 변경뿐이고(DISARMED에서는 늘 받아들여진다, `UserModeIntention.cpp` 55, 73-74행), 이는 쟁점 11의 전제가 깨진 것이다. 이탈을 본 뒤 재전송을 이어 가거나 다시 세면 운용자와 다투고, 이탈을 보지 않고 확인을 고정하면 OFFBOARD가 아닌 모드에서 arm할 수 있으므로 arm 없이 실패한다(fail-closed). 이탈 표본이 오기 전에 나간 재전송은 다른 주체의 모드를 OFFBOARD로 덮을 수 있고, 두 처리가 200 ms 안에 끝나면 이탈 표본이 오지 않아(위 규칙 (라)) 덮은 채 arm할 수 있다. 재전송은 유효 ack가 없는 동안에만 나가므로 이 창은 유효 ack를 받기 전까지이고 보통의 실행에서는 첫 전송의 ack까지다. 유효 ack 뒤에 다른 주체가 모드를 바꾸면 재전송으로 덮지 않고 이탈이나 `mode_confirm_timeout`으로 끝난다. 실패 뒤 지상 DISARMED 기체가 발행 없는 OFFBOARD로 남는 것은 1a P5 실패 뒤와 같은 상태이고 failsafe가 걸리지 않는다. DISARMED에서 DO_SET_MODE 거부는 TERMINATION뿐이다(`Commander.cpp` 927-932행).
- 유효 ack까지 재전송하고 그 뒤에 멈추는 근거: [실측] 재전송 하나가 PX4에 닿지 않는 일이 있다(CI `sitl`의 ULog. 지상 DO_SET_MODE 묶음 211개 가운데 1개에서 확인 직전 tick의 재전송). 확인 뒤에 재전송하지 않으면 그 ack를 기다리다 `mode_confirm_timeout`으로 끝난다. [소스] `vehicle_status`의 주기 publish는 직전 publish부터 500 ms이고 명령을 처리하면 바로 publish하므로(`Commander.cpp` 1897-1899, 1932행) 표본의 위상이 첫 DO_SET_MODE에 묶인다. [실측] 211개 가운데 210개에서 세 번째 OFFBOARD 표본이 마지막 재전송의 4-16 ms 뒤였다. 확인까지 주기마다 재전송하면 arm이 늘 확인 직전의 재전송과 그 ack에 달리고, 유효 ack에서 멈추면 보통의 실행에서 DO_SET_MODE는 하나이고 arm은 첫 전송의 ack에 달린다(queue에서 arm 앞에 놓일 이 goal의 명령도 준다. 쟁점 11). 불변식은 재전송마다 마지막 전송 tick이 바뀌므로 그대로 성립한다. W_DO_SET_MODE가 `command_resend_period`보다 작으면 유실된 전송 뒤에 오는 ack는 없고 다음 재전송의 ack를 기다린다. 주기와 그 두 배 사이면 앞선 전송의 ack가 유효로 읽혀 arm 앞에 DO_SET_MODE 하나가 남는다(쟁점 11이 허용한 열화다). ack가 끝내 없으면 전송은 `mode_confirm_timeout`(3 s) 안에 여섯 번까지 나간다.
- 대기 중 취소에 disarm이 필요 없는 근거: [소스] arm이 PX4 queue에 들어가는 길은 core 출력의 kArm 하나이고 어댑터는 같은 tick에 변환해 publish하며 버퍼나 재전송이 없다(`src/px4/outputs.cpp` 98-100행, `src/node/mission_executor_node.cpp` 534행). kArm을 내지 않았으면 이 goal의 arm은 queue에 없고, 남을 수 있는 것은 DO_SET_MODE 하나라 1a P5의 취소와 같은 상태(지상 DISARMED, `nav_state`는 OFFBOARD일 수 있다)다.
- 불변식은 B9가 구현한다. 단위 테스트 사례: ack 없이 재전송한 다음 tick에 OFFBOARD 확인이 나면 arm은 그 재전송의 ack를 받은 tick에 나간다. 유효 ack 뒤에는 재전송이 없고 확인 tick에 arm이 나간다(IN_PROGRESS ack도 같다). 확인 뒤 재전송 하나나 그 ack 하나가 유실돼도 다음 주기의 재전송과 그 ack로 arm한다. 확인 tick에 유효 ack가 없고 주기가 찼으면 그 tick에 재전송하고 arm은 없다. 주기가 찬 tick에 유효 ack가 있으면 재전송 없이 그 ack를 쓴다. 확인 뒤 ack가 끝내 오지 않으면 주기마다 재전송하다 `mode_confirm_timeout`에 arm 없이 MODE_SWITCH_FAILED다. 확인 뒤 거부 ack에 arm 없이 MODE_SWITCH_FAILED다. 대기 중 이탈에 arm 없이 MODE_SWITCH_FAILED이고 그 tick과 그 뒤에 재전송이 없다. ack 전 tick의 대기 중 취소에 disarm 없이 CANCELED이고 주기가 찬 tick이어도 재전송이 나가지 않는다. 전이 칸 변경(P5 -> P6 조건, 대기 구간의 나가는 길 넷)은 B8 칸 목록 diff로 내고 px4-engineer 필수 승인을 받는다. 공중 Offboard 진입은 arm을 보내지 않으므로 이 조건이 없다. `detail`은 앞부분으로 가른다: 확인되지 않은 전환(`mode_confirm_timeout: OFFBOARD not confirmed`), 확인 뒤 ack 없음(`mode_confirm_timeout: OFFBOARD confirmed but no DO_SET_MODE(OFFBOARD) ack`), 확인 전 거부 ack(`DO_SET_MODE(OFFBOARD) rejected: `), 확인 뒤 거부 ack(`DO_SET_MODE(OFFBOARD) rejected after OFFBOARD confirmed: `), 대기 중 이탈(`OFFBOARD left before DO_SET_MODE(OFFBOARD) ack`).
- 확인 뒤 유효 ack가 끝내 오지 않는 실패는 재전송이나 그 ack가 기한까지 거듭 유실된 경우이고, OFFBOARD로 바뀌었지만 ack를 얻지 못한 거짓 실패일 수 있다. arm 전이고 DISARMED이므로 fail-closed이고, 재시도는 운용 쪽이 goal을 다시 보내는 것이다.
- `idsim_mission_core`는 계속 `idsim_common`과 px4_msgs를 모른다(`check_core_purity.cmake` 그대로).

## 쟁점 13. 상태기 단위 테스트의 "전이 전부를 덮음"

결정
- "전부"의 정의는 px4-engineer가 승인한 전이 칸 목록이다. 칸은 (상태 key, 사건) -> (다음 상태 key, reason)이고 세 부류(덮임, 불가능과 이유, 미덮임)다. 같은 tick에 조건이 겹치는 칸은 (이긴 사건, 함께 참이던 사건 하나) 쌍으로 따로 열거한다. 미덮임이 0이면 완료 기준을 만족한다.
- 단일 칸(겹침이 아닌 칸)은 줄이지 않고 모두 열거한다. 겹침 칸은 결정 지점마다 아래 범위로 열거한다.
  - 감시 표의 행끼리: 상태기 칸 목록에 상태 x 쌍으로 열거하지 않는다. 행 쌍의 "전부"는 `test_monitor_table`이 보증한다. `kMonitorRankOrder`에서 모든 쌍(i < j)을 만들어, 함께 맞을 수 있는 쌍은 두 행이 함께 맞는 입력에서 `evaluate_monitor`의 `row`가 앞 순위 행이고 `matched`가 두 행을 담음을 단정하고, 배타 쌍(순위 4와 5, 순위 6-8끼리)은 함께 맞지 않음을 단정하고, 두 부류의 쌍 수를 고정한다. 상태기 칸 목록에는 감시 표를 쓰는 상태 key마다 대표 쌍을 하나 이상 둔다. 대표는 DISARMED 행(순위 4나 5)이 모드 행(순위 6-8)을 이기는 쌍이다(PX4의 DISARMED 표본은 `nav_state`가 OFFBOARD가 아닌 채로 온다). 덮음 테스트는 감시 표 사건의 칸을 가진 상태 key마다 그런 칸이 있음을 단정한다. 상태기 수준의 행 쌍 칸에는 "불가능" 부류를 두지 않는다. 목록에 없는 행 쌍이 runner 테스트에서 관측되면 목록에 없는 칸의 관측으로 실패하므로, 그 칸을 목록에 더하고 승인을 받는다.
  - setpoint 항목의 tick 순서: (감시 표 행, `ITEM_TIMEOUT`), (감시 표 행, 완료 사건), (`ITEM_TIMEOUT`, 완료 사건)을 setpoint 항목 type마다 열거한다. 감시 표 행은 입력 출처별 대표 넷으로 열거한다: 순위 1(`Px4Timestamp`), 순위 3(link), arming 행 하나(순위 4나 5), 모드 행 하나(순위 6-8).
  - 취소와 그 tick의 종료(무시된 취소): 정리로 들어가는 사건과 `CANCEL`의 쌍은 모두 열거한다(정리 원인과 종료 reason이 취소가 이겼을 때와 갈린다). 그 tick에 goal을 바로 끝내는 사건과 `CANCEL`의 쌍은 상태 key마다 대표를 둔다: 실패로 끝내는 사건 하나, 성공으로 끝내는 사건이 있는 상태 key는 그 사건 하나 더. 대표 칸의 테스트는 취소가 이겼다면 나갔을 명령(Hold, disarm)이 그 tick과 그 뒤에 나가지 않음을 함께 단정한다. 무효 미션과 `CANCEL`의 쌍은 호출 지점이 달라 대표에 넣지 않고 따로 열거한다.
  - 대표로 줄인 쌍을 "불가능"으로 옮기지 않는다. "불가능"은 닿을 수 없다는 [소스] 이유가 있는 칸에만 쓴다.
- "불가능"의 근거는 core 계약 안의 사실이어야 한다. core 계약은 `idsim_mission_core`의 소스와 core 헤더에 적힌 전제다. core 밖 층(노드의 goal 검증과 configure, 어댑터)이 그 입력을 만들지 않는다는 것은 근거가 아니다. 그런 칸은 core 테스트로 덮는다(무효 미션과 `CANCEL`의 쌍이 그 예다).
- `Timeouts`의 값이 모두 양수라는 것은 core 전제다. `core/config.hpp`에 전제로 적고, 0 이하인 값에서의 상태기 동작은 정의하지 않는다. 칸 목록은 이 전제 아래의 전이 표다. runner는 이 전제를 검사하지 않는다. 전제를 지키는 것은 runner를 만드는 쪽이고, 노드는 configure에서 0 이하를 거부한다. `CLEANUP.*.NONE / CLEANUP_CAP` 다섯 칸은 이 전제로 "불가능"이고, note는 노드가 아니라 `core/config.hpp`의 전제를 근거로 적는다.
- 측정은 선언이 아니라 관측이다. 방법:
  - 전이를 일으키는 호출 지점(`terminate`, `begin_cleanup`, `start_item`, `complete_item`, `enter_air`, `enter_ground`, `enter_air_land`, `finish`, 준비 단계를 바꾸는 곳)이 첫 인자로 사건 꼬리표 `Event`를 받는다. 꼬리표 없이는 컴파일되지 않는다.
  - from과 to는 손으로 적지 않는다. runner가 꼬리표를 받는 순간의 상태 key(`stage`, `prep`, 현재 항목 type, 정리 원인, 정리 분기)를 from으로, 다음 꼬리표나 그 tick의 끝에서의 상태 key와 종료 reason을 to로 기록한다. 한 tick의 연쇄 전이는 기록이 여럿이다.
  - 상태 쓰기는 private setter 하나로 모은다. 꼬리표 하나는 상태 key를 한 번까지만 바꾼다. 꼬리표 없이 상태 key가 바뀌거나, 한 꼬리표의 기록이 열린 동안 상태 key가 두 번째로 바뀌면 그 변경은 untagged 기록이 되고 덮음 테스트가 실패한다. 두 번째 변경은 앞 기록의 to에 넣지 않는다(앞 기록은 그 변경 직전의 상태 key로 닫는다).
  - 겹침 칸: 결정 지점에서 후보 조건을 모두 계산한 뒤 고르고 함께 참이던 사건을 기록에 싣는다. 대상은 감시 표(`evaluate_monitor`가 맞는 행 전부를 함께 돌려준다. 첫 행 선택은 그대로), setpoint 항목의 tick 순서, 취소와 그 tick의 종료다.
  - 주입: `TransitionObserver`(`on_edge` 하나)를 `MissionRunner` 생성자의 마지막 인자로 받고 기본값은 `nullptr`이다. 노드는 넘기지 않는다. `step` 시그니처와 snapshot 헤더는 바꾸지 않는다.
  - 비교: 칸 목록은 데이터 파일 `test/transition_cells.tsv`(from, 사건, to, reason, 부류, 겹침이면 함께 참이던 사건) 하나다. 덮음 테스트는 관측한 칸 집합이 "덮임" 부류와 같고, "불가능" 칸이 관측되지 않았고, 목록에 없는 칸이 관측되지 않았고, `Event` enum의 이름 집합이 목록의 사건 집합과 같음을 단정한다.
  - 집계: runner 상태기 테스트 파일들을 gtest 실행 파일 하나 `test_runner`로 묶고 `Environment::TearDown`에서 비교한다. 일부만 돌면(`--gtest_filter`, sharding, `DISABLED_`, `GTEST_SKIP`) 비교 대신 실패한다. 환경변수 `IDSIM_TRANSITION_PARTIAL_OK=1`을 준 실행만 비교를 건너뛰고 그 사실을 출력한다.
- 순서: 이 계측을 1b 동작 변경보다 먼저 동작 무변경 PR 하나로 넣는다. 그 PR에서 1a 칸 목록을 처음 만들고 px4-engineer가 승인한다. 처음 목록에서 드러난 1a 미덮임 칸은 그 PR에서 "미덮임"으로 두고, 상태기를 바꾸는 첫 PR보다 먼저 테스트만 더하는 PR(B8b)에서 0으로 만든다. 뒤의 상태기 PR은 칸 목록의 diff로 px4-engineer 승인을 받는다.
- B8b는 미덮임 칸을 실제 관측으로 덮는다. 정리 단계의 칸은 (정리 원인, 분기, 사건)을 파라미터로 받는 테스트 harness로 덮는다. `idsim_mission_core`의 소스는 바꾸지 않는다. 덮는 중에 닿을 수 없음이 드러난 칸만 [소스] 이유를 note에 적어 "불가능"으로 옮기고 px4-engineer 승인을 받는다. 1a 전이 표와 다른 동작이 드러나면 그 수정은 별도 PR로 낸다. B8b부터 덮음 테스트는 "미덮임" 부류의 칸이 목록에 있으면 실패한다. 그래서 뒤의 상태기 PR은 새 칸을 같은 PR에서 덮는다.
- 소유: `transition.hpp`는 ros2-engineer 소유이고, `Event` 목록과 칸 목록 파일은 전이 표의 일부라 px4-engineer 승인 대상이다. 이 승인 규칙을 `docs-for-agent/file-ownership.md`의 "idsim_mission의 승인 규칙"에 한 줄 더하는 것은 architect가 계측 PR(B8)에 자기 커밋으로 넣는다(U16. 그 파일의 소유자는 architect다). 테스트 실행 파일 통합은 test-engineer의 구조 승인 대상이다.
- 줄과 분기 커버리지는 게이트로 쓰지 않는다. 변이 확인은 일회성 감사로 한다.

근거
- [소스] 지금 상태기는 상태 변경과 동작(명령 전송, 기한 기록, 발행 켜고 끄기, 계수 초기화)이 한 함수에 섞여 있다(`mission_runner.cpp`의 `start_item`, `begin_cleanup`, `enter_ground`). 전이를 한 함수로 모으는 표 구동 재작성은 1a 동작 전체를 다시 검증해야 하고, 1b 확장과 같은 시기에 하면 회귀 원인을 가를 수 없다. 꼬리표 계측은 같은 관측을 동작 변경 없이 얻는다.
- `RunnerView` 전후 비교만으로는 같은 (from, to, reason)을 내는 서로 다른 사건(P5의 거부 ack와 `mode_confirm_timeout`)을 가르지 못한다. gcov는 겹침 칸을 보지 못한다.
- [소스] runner 상태기 테스트 파일들은 실행 파일 하나 `test_runner`다(`CMakeLists.txt`의 `ament_add_gtest(test_runner`). 파일마다 별도 실행 파일이면 실행 파일을 넘는 집계가 ctest 순서에 묶이므로, 한 process 안에서 기록하고 대조한다.
- [소스] 감시 표를 쓰는 상태(P6의 첫 ARMED 뒤, setpoint 항목)는 모두 `monitor_flight` 하나를 거쳐 `evaluate_monitor`의 `row`로 끝낸다(`mission_runner.cpp`의 `monitor_flight`와 그 호출 지점인 준비 단계의 arm 확인과 `step_setpoint_item`). 행 사이의 승패는 순수 함수 `evaluate_monitor`의 성질이라 상태 x 쌍으로 열거하면 같은 성질을 상태 수만큼 되풀이하고, 1b에서 감시 표를 쓰는 항목 type이 늘 때마다 곱으로 는다. `test_monitor_table`의 쌍 표는 `kMonitorRankOrder`에서 만들어지므로(`test_monitor_table.cpp`의 `tie_table`) 행이 늘면 쌍이 따라 늘고, 손으로 적은 목록보다 빠뜨릴 길이 적다. 상태마다의 대표 쌍은 그 상태가 이 표를 거치고 `matched`가 기록까지 닿는지를 본다.
- [소스] setpoint 항목은 만료와 완료 조건을 먼저 계산해 `monitor_flight` 한 호출에 넘기고, 그 뒤 만료, 완료 순으로 본다(`mission_runner.cpp`의 `step_setpoint_item`). 어느 행이 이겼는지는 이 순서에 들어가지 않으므로 행은 입력 출처(시각 포트, 수신 경과, status 표본의 arming과 모드)별 대표로 충분하다.
- [소스] 무시된 취소는 단계 처리 뒤 한 곳에서 적는다(`mission_runner.cpp`의 `step_tick` 끝부분과 `note_ignored_cancel`). 단계 처리가 goal을 바로 끝냈으면 어느 사건이었든 취소는 아무 일도 하지 않는다. 정리로 들어간 경우만 정리 원인이 사건마다 갈린다. 무효 미션은 호출 지점이 따로다(`step_tick`의 `!mission_valid_` 분기).
- "불가능"의 근거를 core 계약 안으로 묶는 이유: 칸 목록은 core 상태기의 전이 표이고 덮음 테스트는 core만 링크한다. core 밖 층의 검사는 그 층이 바뀌면 사라지는데, 그때 칸 목록 diff도 px4-engineer 승인도 생기지 않는다. [소스] 무효 미션은 core가 스스로 검사해 전이로 정의한 입력이라(`mission_runner.cpp`의 `step_tick`에서 `!mission_valid_` 분기) 노드가 먼저 걸러도 core 칸이다.
- [소스] 정리의 상한은 `hold_confirm_timeout_ns + 3 * mode_confirm_timeout_ns`이고(`core/config.hpp`의 `cleanup_cap_ns`), 정리를 시작한 tick의 시각부터 잰 경과가 상한 이상이면 상한이다(`mission_runner.cpp`의 `begin_cleanup`이 `cleanup_start_ns_`를 두는 곳과 `cleanup_cap_reached`). 첫 tick의 경과는 0이므로 상한이 양수이면 `CLEANUP.*.NONE / CLEANUP_CAP`에 닿지 않는다. 양수 전제가 없으면 다섯 칸이 모두 닿는다. `hold_confirm_timeout_ns`가 음수이면 `mode_confirm_timeout_ns`가 양수여도 상한이 0 이하가 되므로, P5를 지났다는 사실로는 `ITEM_TIMEOUT`과 PREPARING 실패의 칸을 막지 못한다. 그래서 일부만 "미덮임"으로 돌리지 않고 전제를 core에 둔다.
- runner가 전제를 검사하지 않는 이유: `Config`는 tick 입력이 아니라 생성 인자이고, 0 이하인 값은 운용 중에 생기는 상황이 아니라 runner를 만드는 쪽의 결함이다. runner가 검사해 goal을 끝내면 종료 길이 하나 늘어 칸이 생기는 상태기 변경이다. 전제를 주석으로 적는 것은 동작을 바꾸지 않는다.
- untagged를 한 꼬리표의 두 번째 변경까지 넓히는 이유: [소스] 기록의 to는 다음 꼬리표나 tick 끝의 상태 key라서(`mission_runner.cpp`의 `close_record`), 꼬리표를 단 전이 뒤에 꼬리표 없는 상태 쓰기가 같은 tick에 오면 앞 기록의 to에 섞여 (from, 사건, to) 하나로 보인다. 그 칸을 목록에 더하면 사건 없는 상태 변경이 승인된 칸으로 남는다. 지금 전이 함수는 모두 꼬리표 하나에 상태 쓰기 하나다.
- 미덮임을 상태기 변경보다 먼저 0으로 만드는 이유: 계측을 동작 변경보다 먼저 넣는 것은 회귀를 칸 목록 diff로 가르기 위해서인데, 관측된 적 없는 1a 칸은 1b 변경 전후를 견줄 기준이 없다. B8 PR에 합치지 않는 이유: 동작 무변경 검토(기존 테스트 본문 무변경)와 테스트 추가 검토를 가르고, B8에 걸린 B9 헤더 PR을 미루지 않는다.

## 쟁점 14. YAML 로더와 idsim_common 공개

결정
- YAML 로더: `idsim_mission` 안의 Python 모듈 `idsim_mission.mission_yaml`(`ament_cmake_python`)과 CLI `send_mission <file> --vehicle <vehicle_id>`. 소유 ros2-engineer. 로더는 구조 검사(모르는 key 거부, 필수 key, 타입), 단위 변환(`timeout_s` -> `Duration`, ns 반올림, 음수와 비유한 거부), 기본값 채움, `mission_id`(YAML 값 또는 파일 이름, 정규식 검사)만 한다. 계약 검증의 정본은 Executor의 goal 검증이고 로더에 다시 구현하지 않는다. yaw는 `yaw_rad`만 받는다.
- 1b 시험 미션 YAML은 `tests/sitl/missions/`에 둔다(test-engineer). 시간 합산 단정은 로더가 만든 `Mission`에서 한다(기본값이 채워진 뒤).
- `idsim_common`: NAV_TAKEOFF 빌더는 더하지 않는다. 공개 /fmu/in은 셋 그대로다. 더하는 것은 `geo.hpp`(쟁점 4), `TargetId`, `target_state_topic`, 상태 QoS 함수(`state_pub_qos`, `state_sub_qos`), 그리고 `px4::position_setpoint`의 속도 feedforward 인자(선택 인자, 없으면 지금처럼 `velocity` NaN. 있으면 유한성과 float 범위를 위치와 같이 검사한다), 그리고 float32 술어 `px4::fits_float32`(`px4_setpoint.hpp`. double과 `Eigen::Vector3d`를 받는다. `position_setpoint`가 이 함수를 쓰고, 주석에 `position_setpoint`의 수용 조건과 같다고 적는다. 단위 테스트는 float 최댓값과 그 음수, 최댓값 바로 다음의 double, 1e39, inf, NaN을 본다. 쟁점 12의 S5에 넣는다)다. `offboard_position_mode`는 그대로다.
- `goto_setpoint`는 Restricted 그대로다. PX4는 위치 제어 중 그 주기에 새 `trajectory_setpoint`가 없으면 500 ms 안의 `goto_setpoint`를 따르므로(`MulticopterPositionControl.cpp` 429-436행) Offboard에서 발행하면 우리 setpoint 사이사이에 섞인다.

## 쟁점 15. 시나리오, 순서, CI 시간

결정
- 한 스택에서 이 순서로 돈다: B, C, A, D, F1, F2, F3, F4, T.

| id | 미션 | 보는 것 | 끝 상태 |
| --- | --- | --- | --- |
| B | 1b의 무효 사례로 한다(1a의 GOTO 사례는 1b에서 유효하므로 쓰지 않는다): 항목 없는 미션 `[]`, 첫 항목이 아닌 TAKEOFF, `[LAND, GOTO]`, 마지막이 아닌 RTL, `[RTL, ...]` 여러 항목, TRACK_ENTITY의 0 `offset`, 형식이 틀린 `target_id`, 기본값 TRACK_ENTITY 서브메시지 | 사례마다 ABORTED, INVALID_MISSION, 비행 없음 | 지상 |
| C, A, D, T | 1a 그대로 | 1a 그대로 | 1a 그대로 |
| F1 | `[TAKEOFF 5 m, GOTO x 3, LAND]`(한 변 10 m) | waypoint 도달(정답 판정), 항목 순서, 착륙 후 disarm. b의 표본(R2) | 지상 DISARMED |
| F2 | `[TAKEOFF, GOTO, TRACK_ENTITY]`, 표적 속도 1-2 m/s | 표적 접근, 공중 종료의 SUCCEEDED와 Hold(`HOLD_AIRBORNE`) | 공중 Hold |
| F3 | `[GOTO, RTL]`(F2가 남긴 Hold에서 공중 시작, RTL `timeout` 60 s) | 공중 시작, RTL 완료(착륙 위치, disarm). `R_home`의 표본(R4) | 지상 DISARMED |
| F4 | 합친 미션(U13) `[TAKEOFF 5 m, GOTO x 2, TRACK_ENTITY, RTL]`. 표적은 F2와 같은 표적(`loop` true. 시작 위상은 앞 비행의 시간에 따라 달라진다), RTL `timeout` 60 s | roadmap 1b 목표 그대로의 미션 하나: waypoint 도달(정답 판정, b의 표본), 표적 접근, RTL 착륙 위치(R4), 착륙 후 disarm | 지상 DISARMED |

- B의 구성: 사례를 순서대로 하나씩 보내 각각 ABORTED, INVALID_MISSION을 확인한다. DISARMED 유지와 `never_armed` 단정은 첫 goal 전송부터 끝까지 한 구간에 한 번 건다. 거부가 아닌 결과가 나오면 즉시 실패하고 비상 정리한다. 규칙 하나당 통합 사례 하나가 원칙이고 조합의 완전성은 `validate_mission_contract` 단위 테스트가 덮는다. `[TAKEOFF, TAKEOFF]`는 "첫 항목이 아닌 TAKEOFF"와 같은 규칙이라 넣지 않는다.
- B의 교체 시점: goal 접수 제한을 지우는 B10 PR에 함께 넣는다(test-engineer 커밋). B10부터 `[GOTO]`는 접수되어 지상 DISARMED에서 PRECONDITION_FAILED로 끝나므로(쟁점 7), 1a 사례를 그대로 두면 B11까지 main의 `sitl`이 실패한다. B10에 넣는 최소는 1a 사례를 위 1b 무효 사례 하나 이상으로 바꾸는 것이다. 사례 전부와 위 구성을 B10에 넣을지 B11에 둘지는 test-engineer가 정한다. 노드 테스트(`test/node/test_executor_node.cpp`)의 무효 미션 사례는 ros2-engineer가 B10에서 1b 무효 사례로 바꾼다.
- 형식은 맞지만 없는 `target_id`는 INVALID_MISSION이 아니다. 계약상 받아들여 이륙하고 TARGET_LOST로 끝난다. 그래서 B에 넣지 않는다.
- 비행 시나리오(A, D, F1, F2, F3, F4)가 실패하면 뒤의 비행 시나리오는 실행하지 않고 `UPSTREAM_FAILED`(실패로 센다)로 기록한다. A, D의 실패도 F1-F4를 `UPSTREAM_FAILED`로 만든다. 정리용 `[LAND]`는 한 번 시도하고 판정에 넣지 않는다. 정리도 실패해 T의 선행조건(지상 DISARMED)이 맞지 않으면 T는 `PRECONDITION`으로 실패하고 `UPSTREAM_FAILED`와 따로 분류한다. F3만 따로 돌릴 수 없다는 것을 `tests/sitl/README.md`에 적는다.
- TARGET_LOST와 표적 서비스 정지의 통합 시나리오는 1b에 두지 않는다. 단위 테스트(가짜 `FramePort`와 표적 맵)로 덮고 계약 문장의 근거는 [단위 테스트]로 적는다.
- `config/fleet.yaml`의 기체 1을 (6, -3, 0)에 스폰해 스모크 S2가 NavSat 변환의 수평 반전을 가려낸다(S2-a. 반전이면 수평 오차가 약 13.4 m라 0.5 m 허용으로 실패한다). 1a 시나리오 A, C, D, T는 위치와 무관한 미션이다.
- sitl은 전용 fleet 파일 `tests/sitl/fleet.yaml`(test-engineer 소유. F2 표적 포함)을 `sim_stack.sh up --fleet`으로 쓴다. 개발용 `config/fleet.yaml`의 `targets`는 시연용 하나 또는 빈 목록이다(sim-engineer, test-engineer가 정한다). 개발 fleet을 고쳐도 CI 시나리오 기하가 바뀌지 않게 하려는 것이다.
- TRACK_ENTITY의 `timeout`은 표적 위상과 무관하게 잡는다. `loop` 표적의 위상은 앞 시나리오의 소요 시간에 따라 달라지므로(F2, F4), 항목 시작점(직전 GOTO 목표)에서 loop 궤적 위 가장 먼 점까지의 거리를 따라잡는 시간에 완료 마진을 더한 값으로 둔다. 접근 속도와 마진의 값은 [추정]이고 test-engineer가 미션 YAML 주석에 근거와 함께 적는다.
- 시간 규칙: 시나리오마다 항목 `timeout` 합 + 마진이 비행당 상한(ROS 시각 3분)을 넘지 않음을 단위 테스트가 단정한다. 같은 단위 테스트가 TRACK_ENTITY의 `timeout`이 `tests/sitl/fleet.yaml`의 궤적에서 계산한 최원점 기준 값 이상임을 단정한다. RTF가 1 미만이면 `SITL_PYTEST_TIMEOUT`(벽시계)은 올려도 되고 판정의 ROS 시각 한도는 올리지 않는다. CI `sitl` job의 목표는 15분이다(U11). 넘으면 겹치는 비행 구간 -> 순회 waypoint 수 -> Hold 유지 시간 순으로 줄인다(U15). 겹치는 비행 구간은 F1과 F4의 순회처럼 같은 판정을 두 비행이 보는 부분이다. 경계 상황을 보는 F2의 공중 종료와 F3의 공중 시작은 빼지 않는다. 그래도 넘으면 측정값과 함께 사용자에게 올린다. 판정 기준을 느슨하게 해서 줄이지 않는다.
- [추정] 1b 추가 뒤 `run_sitl.sh`는 약 5.5-7분(F1 약 45 s, F2 약 40 s, F3 약 40 s, F4 약 75 s, B 약 11 s), CI `sitl` job은 보통 약 9.5-10.5분, 가장 나쁜 조합(pull 캐시 없음, ros_ws 빌드 최장)에서 약 14-14.5분이다. 근거는 1a 실행 기록의 이정표와 최근 sitl 실행의 step 시각이고, 순회, 표적 접근, RTL 구간은 실측 전 추정이다. 인프라 추가(새 서비스 둘, 월드 생성, `idsim_sim` 빌드)는 20초 아래다. 1b 첫 로컬 보정 실행(`--repeat 30`)의 값으로 교체한다. RTF가 0.7로 떨어지면 가장 나쁜 조합이 약 16분으로 15분을 넘는다. 15분을 넘으면 위 시간 규칙의 순서를 따른다.

근거
- 1a의 B 사례(GOTO가 든 미션)는 쟁점 6으로 유효 미션이 되어 그대로 두면 기체가 이륙한다. 그래서 B의 사례를 1b 기준으로 바꾼다.
- 지상 거부 사례는 비행 전에 둔다(비행 실패가 사전조건을 깨지 않게). 유지 구간을 한 번만 두어 B가 사례 수에 비례해 늘지 않는다. F2의 끝(공중)과 F3의 시작(공중)을 맞물려 이착륙 한 번을 줄인다. F4는 F3이 남긴 지상 DISARMED에서 시작한다. T는 지상 시나리오라 맨 뒤다.
- F1-F3은 경계 상황(공중 종료, 공중 시작)을 따로 보지만 roadmap 목표의 미션 하나(이륙부터 착륙까지)를 덮지 않는다. F4가 그 미션을 그대로 돈다(U13).
- job 시간의 변동은 대부분 이미지 pull과 ros_ws 빌드(합 약 3-6분)에서 오고 1b에서는 비행 시나리오 넷이 pytest 시간의 과반이 된다.

## 쟁점 16. 다대 원점 판정

결정
- 생성기(`tools/gen_compose.py`)가 기체별 기대 GPS `vehicles[].expect_gps = {lat, lon, alt}`를 `world.origin`과 스폰 pose로 계산해 `stack.json`에 싣는다. `check_px4`는 지금의 `--expect-origin`을 기체마다 그 값으로 부르기만 한다. `--expect-pose-enu`는 두지 않는다.
- 기준점은 GNSS 센서가 붙은 base_link다. 식은 WGS84 곡률 반지름의 국소 근사(`M`, `N`을 원점 위도에서 계산, 표준 라이브러리 `math`)이고 고도는 `world.origin.alt + 스폰 z + 센서 높이`다. 센서 높이는 생성기 상수 `AIRFRAME_SENSOR_Z_M = {"4001_gz_x500": 0.24}`(airframe 허용 목록 옆)다. 오프셋이 수직뿐이라 yaw와 무관하다. embedded는 null이다.
- 센서 높이의 출처가 생성기 상수와 x500 모델 SDF(`sim-oracle`이 읽는다) 둘이므로, 스모크 images 단계(S0)가 sim-base 안에서 sdformat으로 읽은 `navsat_sensor`의 모델 기준 높이(센서는 base_link에 붙어 있고 둘 다 0.24 m다)를 생성기의 `--print-sensor-z AIRFRAME` 출력과 대조한다(차 1e-6 m 미만). `PX4_GZ_MODELS_REF`가 바뀌는 PR에서 어긋남이 드러난다.
- `run_smoke.sh`는 `vehicles.0.expect_gps`를 같은 `--expect-origin`으로 넘긴다. 허용 오차(수평 0.5 m, 수직 1.0 m)는 그대로다. 다대 비교는 호출하는 쪽이 `vehicles[i]`마다 `check_px4`를 부른다.
- 생성기의 식은 스모크 기대값이고 운용 변환이 아니다. "world ENU <-> 로컬 NED 변환은 `idsim_common` 한 곳"은 운용 노드의 규칙이고 이 식에 적용하지 않는다. 생성기 단위 테스트가 gz-math 7.7.0 LOCAL2 값 셋(원점 서울시청에서 북 100 m, 동 100 m, (6, -3))과 1e-8 도 안에서 맞음을 단정하고 3대-k0 golden이 값을 바이트로 고정한다.

근거: 비교기는 그대로이고 인자 출처만 바뀐다. 근사와 gz-math LOCAL2의 차는 원점에서 100 m에 약 0.7 mm다([실측, 계산]). GNSS 고도는 센서가 붙은 base_link의 고도이므로 스폰 z만 더하면 R1 수직 기록이 0.24 m 치우친다.

## 쟁점 17. Actor 월드의 viz 확인

결정: sim-engineer의 수동 절차(M4)를 1회 하고 결과를 PR 본문에 남긴다. ogre2와 ogre 둘 다, GUI 재접속 1회, 120 s 동안 서버 생존과 `/clock` 증가와 `vehicle_status` 수신. CI에 넣지 않는다. Actor 위치와 `TargetState`의 차이(M2)는 같은 확인에서 육안으로 본다. `gui.config` 고정 목록 밖의 plugin 추가 금지를 운영 문서에 적는다. 같은 확인에서 궤적 길이의 합이 상한인 월드(표적 4 x 600 s) 하나를 더 열어 GUI CPU, 서버 RSS, RTF를 golden 월드와 나란히 기록한다. 통과 기준은 두지 않고, sim-engineer가 화면 확인에 지장이 있다고 판단하면 값과 함께 architect에게 올린다.

## 1a 고정 계약 영향

모두 `docs/interface.md`의 1a 고정 절이고 `idsim_interfaces`의 필드와 상수는 바뀌지 않는다(golden과 type hash 무변경. 정의 주석만 바뀐다). `docs/architecture.md`의 변경 절차("고정 뒤에는 새 요구가 있어야 한다. 변경 절차를 따른다")가 적용된다. 새 요구는 1b 범위(U3의 공중 종료, 로드맵 1b의 RTL과 공중 시작과 표적 추종, U7, U8)다. (t)의 새 요구는 쟁점 11의 유지 조건(arm 처리 전 창에 이 goal이 보낸 명령이 끼지 않는다)을 tick 주기와 W의 시간 관계가 아니라 명령 순서로 지키는 것이다. 1a의 "같은 queue에서 FIFO" 근거는 arm 앞에 이 goal의 명령이 남지 않는다는 것을 tick 주기가 W보다 길다는 데 기대고 있었고, 이 관계는 SITL 1 스택에서만 근거가 있다(Phase 2 다중 스택 부하와 실기체에는 없다). 반영은 B13(계약 고정 문서)에서 한 PR로 하고((r)과 (k)의 앞부분인 bridge 문장은 사실 갱신이라 B3 PR에서 한다. "문서 반영 목록"의 B3 묶음), PR 본문에 아래 목록과 근거를 적으며 architect 승인과 reviewer 검토를 받는다. 1a에서 받던 미션(첫 항목 TAKEOFF와 마지막 LAND, `[LAND]`)에 대한 동작은 아래 예외 하나 말고는 어느 항목에서도 바뀌지 않는다. 예외: 지상 arm 진입의 P5 완료에 마지막 DO_SET_MODE 전송 뒤의 ack를 더한다((t), 쟁점 12). 그래서 OFFBOARD 3회 확인 뒤 그 ack를 기다리는 구간(대기 구간)이 생기고, 1a에서는 확인 tick에 arm을 보내 P6에서 다루던 사건이 이 구간에서는 arm 전의 P5 사건이 된다. 대기 구간의 사건은 P5 규칙으로 처리한다. 대기 구간에만 있는 경로는 넷이다: 그 ack가 `mode_confirm_timeout` 안에 오지 않음, 확인 뒤의 거부 ack, ack 전 tick의 대기 중 취소, 대기 중 OFFBOARD 이탈. P5 공통 출구(식별 불일치 등)도 대기 구간에서 나올 수 있고, 1a에서는 확인 뒤가 P6이라 disarm을 한 번 보냈지만 이제는 arm 전이라 보내지 않는다(reason과 끝 상태는 같다). 넷 모두 arm을 보내지 않은 P5의 사건이다(`arm_sent` false). 앞의 셋은 arm 없이 MODE_SWITCH_FAILED(준비 단계)로 끝나고, 대기 중 취소는 disarm 없이 CANCELED로 끝난다(1a에서는 arm을 보낸 뒤라 지상 arm 분기의 disarm 확인을 거쳤다). 결과(reason, 끝난 뒤 기체 상태인 지상 DISARMED, feedback의 phase)는 1a의 MODE_SWITCH_FAILED(준비 단계) 행과 CANCELED(지상 분기) 행과 같다. 1a에서 확인 뒤 거부 ack는 무시되어 arm으로 갔고 대기 중 이탈은 P6 감시가 다뤘다는 점이 달라진다. [실측] 1a 실행의 arm 2회에서는 ack가 확인보다 먼저 와 있었으므로 보통은 대기 구간이 0 tick이고 arm 시점도 바뀌지 않는다. 이 예외와 경로별 결과는 B13 PR 본문에 적는다.

| 번호 | 대상 문장 | 바꾸는 이유 | 성격 |
| --- | --- | --- | --- |
| (a) | "끝난 뒤 기체 상태"의 SUCCEEDED 행 "지상 DISARMED(마지막 항목 LAND의 완료 조건)" | 공중 종료(쟁점 10)와 RTL(쟁점 9). 마지막 항목별로 행을 나눈다: LAND와 RTL은 지상 DISARMED, setpoint 항목은 공중 Hold이거나 지상 DISARMED(마지막 목표가 지면에 닿은 경우). 지상 ARMED는 SUCCEEDED의 끝 상태가 아니다 | 행 분할. LAND로 끝나는 미션의 보장은 같다 |
| (b) | "GoalStatus와 reason" 표의 "나오는 곳" 열(MODE_SWITCH_FAILED, FAILSAFE, EXTERNAL_MODE_CHANGE, LINK_LOST, ITEM_TIMEOUT)과 PRECONDITION_FAILED, EXTERNAL_DISARM 의미 칸의 괄호 | RTL, 공중 Offboard 진입, 공중 종료가 같은 reason을 낸다(쟁점 7, 9, 10) | 적용 경로의 열거 확장. reason의 핵심 의미는 그대로. 같은 표의 "정리"(574-575행 상태 끊김과 공중 DISARMED 문장, 표의 FAILSAFE와 LINK_LOST 행)가 취소의 정리임을 밝힌다. 빠지기 쉬운 둘을 목록에 둔다: MODE_SWITCH_FAILED 의미 칸의 괄호(624행. RTL 항목의 AUTO_RTL 전환과 RTL 실패의 정리를 더한다), "MODE_SWITCH_FAILED와 DISARM_FAILED를 나눈 이유"(637행. RTL 실패의 지상 분기에서 disarm이 확인되지 않으면 MODE_SWITCH_FAILED로 끝난 기체가 지상 ARMED로 남는다) |
| (c) | 용어 "정리"와 "정리" 절 첫 문장의 원인 목록(취소, setpoint 항목의 ITEM_TIMEOUT, 준비 단계의 실패) | TARGET_LOST가 같은 정리를 거친다(쟁점 8). RTL 항목의 실패(거부 ack, AUTO_RTL 미확인)도 정리를 거치되 공중 분기가 Hold 없이 Land 경로다(쟁점 9). "정리" 절의 phase 문장("EXECUTING 또는 PREPARING")에 RTL 실패의 `PHASE_WAITING_MODE`를 더한다. "정리할 것 없음" 문장("준비 단계의 실패에서")에 `[RTL]` 미션의 RTL 실패를 더한다. 공중 종료 단계는 정리와 같은 장치를 쓰되 결과 표가 따로다(쟁점 10) | 원인 추가 |
| (d) | "비행 중 감시" 첫 문장의 시작 시점과 "(TAKEOFF, LOITER)", 순위 5의 failsafe 이력 구간 | 공중 Offboard 진입은 P3부터, 모드 행 7, 8은 첫 OFFBOARD 표본 전 AUTO_LOITER 면제(순위 6은 면제 없음), setpoint 항목 전체로(쟁점 7, 8) | 범위 확장 |
| (e) | "발행 규칙"의 "Offboard로 들어가는 중(준비 단계의 발행 시작부터 arm 확인까지)" | 공중 Offboard 진입은 Hold 중에 OFFBOARD 확인까지 현재 위치 setpoint를 발행한다(쟁점 7) | 예외 구간 추가 |
| (f) | "준비 단계" 절 첫 문장("첫 항목이 TAKEOFF인 미션은")과 `[LAND]` 문단 | 공중 Offboard 진입 문단 추가, `[LAND]` 문단을 `[LAND]`와 `[RTL]`로(쟁점 7, 9) | 문단 추가 |
| (g) | "LAND 항목" 절, feedback 표의 `PHASE_WAITING_MODE`(1a는 LAND) | 모드 명령 항목(LAND, RTL)으로 넓힌다(쟁점 9). "LAND 항목에는 정리 분기가 없다"는 LAND에 한정하고 RTL의 실패 fallback(거부 ack와 미확인)을 적는다. RTL의 ITEM_TIMEOUT과 RTL 중 취소는 LAND와 같다 | 구조 변경. LAND 규칙은 그대로 |
| (h) | 미션 정의 절의 "1a 노드의 임시 제한(계약 문장이 아니다. 1b에서 푼다)"과 `MissionItem.timeout`, `YawSetpoint.mode`, `TakeoffItem.height_m`의 "1b에서 정한다" 괄호. `docs/architecture.md` 인터페이스 계약 절의 "다음 setpoint 항목에서 Offboard 재진입 절차를 다시 밟는다" | 순서 규칙이 계약이 된다(쟁점 6, U7) | 임시 제한의 계약화와 1b 몫 닫기 |
| (i) | "SITL 파라미터"의 계약 표 | `RTL_TYPE`, `RTL_CONE_ANG`, `RTL_RETURN_ALT`, `RTL_LAND_DELAY`, `COM_DISARM_LAND`, `COM_LOW_BAT_ACT`, `EKF2_HGT_REF` 행 추가(쟁점 9, U8, U9) | 행 추가 |
| (j) | 공통 규칙 "이름과 식별자"의 "Python은 `tests/support`가 한다" | Python 생산자(표적 어댑터)가 생긴다(쟁점 3) | 위치 추가 |
| (k) | "시간 기준"의 "1a는 `/clock`만 브리지한다", 그리고 "예외 하나: 취소의 지상 분기"의 근거 서술("지연 크기는 미측정", "3개가 되려면 표본 간격 약 0.5 s로 arm이 약 1 s 동안 처리되지 않아야 한다") | 1b도 bridge는 `/clock` 하나이고 표적과 정답 pose는 bridge를 거치지 않는다(쟁점 2, 5). 처리 전 표본의 창은 W_arm 이하이고 잘못된 확인에는 그 창 안에 publish 간격 두 개가 들어가야 한다(쟁점 11의 유지 조건과 실측) | 사실 갱신. 확인 규칙은 그대로 |
| (l) | "Offboard setpoint" 절의 "`velocity`, `acceleration`, `jerk`, `yawspeed`는 NaN"과 "1a는 position 제어만 쓴다" | TRACK_ENTITY는 표적 속도를 `velocity` feedforward로 싣는다. `offboard_control_mode`는 그대로 position만 true다(쟁점 8) | 예외 추가. 1a 항목의 setpoint는 그대로 |
| (m) | "끝난 뒤 기체 상태"의 `MODE_SWITCH_FAILED(준비 단계)` 행("arm 전이므로 지상 DISARMED"), `MODE_SWITCH_FAILED(LAND 항목)`과 `ITEM_TIMEOUT(LAND 항목)` 행, `ITEM_TIMEOUT(setpoint 항목)` 행 | 공중 Offboard 진입의 P4, P5 실패는 정리의 공중 분기를 거쳐 공중 Hold(또는 Hold 실패 뒤 Land 진행 중)로 끝난다(쟁점 7). RTL 항목의 실패는 Land fallback 뒤 끝나 LAND 항목 행과 상태가 다르다: `MODE_SWITCH_FAILED(RTL 항목)` 행을 더하고 쟁점 9의 분기별 표(공중이면 NAV_LAND를 보내 보통 AUTO_LAND로 내려오는 중, 지상이면 disarm 분기, 확인되지 않은 것과 상한, 끊김은 `detail`)를 옮긴다. `ITEM_TIMEOUT(LAND 항목)` 행은 모드 명령 항목(LAND, RTL)으로 넓힌다(쟁점 9). TARGET_LOST 행을 더한다(ITEM_TIMEOUT(setpoint 항목)과 같은 정리, 쟁점 8). 공중 종료 단계의 끝을 더한다(쟁점 10): MODE_SWITCH_FAILED(Land 경로나 상한)는 취소의 Hold 실패 행과 같은 상태이거나 지상(disarm 1회를 보냈고 확인되지 않았다), LINK_LOST는 지상 대기에서 대비책 disarm을 보낸 뒤였으면 disarm을 한 번 더 보냈다, INTERNAL은 Px4Timestamp를 만들지 못한 경우를 포함한다 | 행 분할과 추가. 지상 arm 진입의 행은 그대로 |
| (n) | "정리의 상한" 절 첫 문장의 원인 목록(취소, setpoint 항목의 ITEM_TIMEOUT, 준비 단계의 실패)과 상한에서의 결과 문장("ITEM_TIMEOUT과 준비 단계 실패의 정리이면 같은 동작에 원래 reason을 유지") | TARGET_LOST의 정리는 원래 reason을 유지한다(쟁점 8). RTL 실패의 정리도 같은 상한을 쓰고 원래 reason(MODE_SWITCH_FAILED)을 유지한다(쟁점 9). 공중 종료 단계도 같은 상한을 쓰고 상한에서 공중 NAV_LAND 1회, 지상(ARMED이고 `landed` true, 또는 분류가 지상인 DISARMED) disarm 1회 뒤 ABORTED, MODE_SWITCH_FAILED다(쟁점 10의 결과 표). 종료 단계의 한 tick 순서(지상 DISARMED를 보는 동안 분기의 판정을 멈춘다)를 "정리 중 한 tick의 순서" 문장 옆에 적는다 | 원인과 결과 대응 추가 |
| (o) | "종료의 충돌 규칙"의 "감시 표의 행은 ITEM_TIMEOUT을 이긴다" | 같은 tick의 순서가 감시 표 -> TARGET_LOST -> ITEM_TIMEOUT -> 완료다(쟁점 8) | 순서에 사건 하나 추가 |
| (p) | "용어"의 "명령"(Offboard 전환, arm, disarm, Hold 전환, Land)과 "N회 연속 확인"의 확인 대상(OFFBOARD, ARMED, Hold, Land 모드, DISARMED) | RTL(NAV_RETURN_TO_LAUNCH) 명령과 AUTO_RTL 확인이 더해진다(쟁점 9) | 열거 확장 |
| (q) | feedback 표의 `PHASE_EXECUTING` 행("setpoint 항목 실행 중. 그 항목의 ITEM_TIMEOUT 정리 중") | TARGET_LOST의 정리 중과 공중 종료 단계 중도 `PHASE_EXECUTING`이다(쟁점 8, 10) | 적용 구간 추가 |
| (r) | "SITL 파라미터" 절의 "월드 원점은 gazebo wrapper가 `world.origin`으로 적용한다" | 원점은 생성기가 만든 월드 SDF의 `<spherical_coordinates>`로만 들어간다(쟁점 2, M5 통과 뒤) | 사실 갱신 |
| (t) | "준비 단계" 표의 Offboard 전환 행(완료 조건 "OFFBOARD 3회 연속 확인"), "GoalStatus와 reason" 표의 MODE_SWITCH_FAILED 의미("요청한 모드 전환이 확인되지 않았다"를 "요청한 모드 전환이 확인되지 않았다. 지상 arm 진입에서는 arm 전까지 그 명령의 ack가 오지 않았거나 확인한 모드가 유지되지 않은 것도 포함한다"로), "시간 기준" 예외 문장의 FIFO 근거, 그리고 "명령" 문단의 "확인을 기다리는 명령은 `command_resend_period`마다 재전송"과 "ack는 거부를 빨리 아는 데만 쓴다" | 지상 arm 진입의 Offboard 전환은 유효 ack가 없는 동안만 재전송하고(유효 ack 뒤에는 확인 전이어도 재전송하지 않는다. 1a 미션의 보통 실행에서 전송 수가 준다) ack를 arm 조건으로도 쓴다. 지상 arm 진입의 arm은 마지막 DO_SET_MODE 전송 뒤의 ack와 OFFBOARD 3회 확인이 갖춰진 tick에만 보낸다. 확인 뒤 ack가 `mode_confirm_timeout` 안에 오지 않으면 MODE_SWITCH_FAILED. 처리 전 DISARMED 표본의 창에 이 goal이 보낸 다른 명령이 끼지 않게 한다(쟁점 11, 12) | 완료 조건 추가와 reason 의미 확장. 대기 구간의 사건은 P5 규칙(머리 문단의 예외) |
| (u) 후보 | "종료의 충돌 규칙"의 "같은 tick에 만료와 기다리던 확인(3회 연속)이 함께 정해지면 만료가 이긴다" | 구현은 LAND 항목(`step_land`)만 확인을 먼저 세운다. 준비 단계(`prepare_offboard`), 공중 종료(`run_air`), 지상 종료(`run_ground`)는 계약대로 만료가 이긴다. S2의 RTL은 LAND 순서를 따르고 테스트는 이 경계 tick을 단정하지 않는다. 확인 tick의 거부 ack도 같은 범위다: 모드 명령 항목의 확인 tick과, 공중 종료 단계의 Hold 3회째 tick에 온 Hold 거부 ack(구현은 `run_air` 순서대로 거부가 먼저이고 S3 테스트는 단정하지 않는다). 종료 단계에서 "만료가 이긴다"를 적용하는 쌍과, 지상 DISARMED를 보는 동안 보지 않는 분기의 판정은 같은 tick의 순서("ABORTED 사유, 완료, 취소 순")의 대상이 아니라는 단서(쟁점 10)를 계약 문장에 함께 적는다. B10 전에 구현을 계약에 맞출지(1a 동작 변경, 별도 PR과 칸 명세), 계약에 모드 명령 항목의 예외를 둘지 정한다 | 정해지지 않음. 정해지면 번호를 확정하거나 뺀다 |

## 실측과 확인 목록

U6의 산출물 최소 원칙을 1b에도 쓴다. 결과는 PR 본문과, 상수를 정한 경우 그 상수의 근거 주석에 남긴다. 결과가 결정의 전제와 다르면 architect에게 올린다.

| 이름 | 무엇 | 왜 | 담당 | 방법 |
| --- | --- | --- | --- | --- |
| M1 | `<skin>` 없는 Actor가 렌더링되고 움직이는가(headless ogre2 카메라 센서 영상으로 실측함. GUI와 ogre 확인은 M4) | 커스텀 모델 필요 여부(쟁점 2) | sim-engineer | 수동 1회 |
| M4 | Actor 월드에 `gz-gui` 연결, 재접속, 120 s 생존. link visual만 가진 Actor가 GUI(ogre2, ogre)에서 보이는지. M2(Actor와 `TargetState` 차)를 육안으로 같이. 궤적 길이 합이 상한인 월드의 GUI CPU, 서버 RSS, RTF 기록 | viz 서버 생존 리스크(쟁점 17) | sim-engineer | 수동 1회 |
| M5 | 원점을 SDF로만 넣었을 때 스모크 S2 통과 | 런타임 원점 호출 제거(쟁점 2) | sim-engineer, test-engineer | 스모크 1회 |
| S1-a | 지상 정지에서 oracle의 base_link 위치와 스폰 pose(x, y 같고 z는 스폰 z + 0.24에서 지상 접촉 침하분만큼 낮다. 결과는 쟁점 5 근거), Pose_V의 `x500_N` model 항목이 world 기준인지 | 오프셋 합성과 top-level pose가 world 기준이라는 [추정](쟁점 5) | sim-engineer | B7 PR의 스택 실행(`sim-oracle`이 생긴 뒤) |
| S1-b | 호버 중 oracle 위치와 `vehicle_local_position`을 사슬 역변환한 값의 차, 수평과 수직 | 기준점이 같다는 판단과 사슬의 부호, 축(쟁점 4, 5) | sim-engineer, test-engineer | F1 trace |
| S1-c | oracle 프로세스 CPU와 `/sim/*/pose` 발행 주기 | 비용 [추정] 확인 | sim-engineer | F1 중 `docker stats` |
| S2-a | 원점에서 떨어진 스폰에서 `sensor_gps` 위경도와 LOCAL2 기대값의 차 | NavSat이 LOCAL2를 쓴다는 [추정]. 반전이면 사슬의 기준 식이 바뀐다(쟁점 4) | sim-engineer, test-engineer | 스모크 S2(기체 1을 (6, -3)에 스폰) |
| S3-a | `targets` 컨테이너 CPU, `/clock` 수신 주기, `TargetState` 발행 간격 분위수 | Python의 `/clock` 수신 비용과 timer 흔들림(쟁점 3) | sim-engineer | F2와 같은 실행, R3와 함께 |
| R1 | `ref_*`와 `expect_gps`의 차(수평, 수직, base_link 기준) | 기록(쟁점 5) | test-engineer | sitl gate의 `recorded_only` |
| R2 | GOTO 도달 사건마다 `t_f`의 부호 있는 초과량 `s`, 성분과 정답 표본 간격. TRACK_ENTITY 완료는 `s_track`을 따로 | b와 `s_track` 점검(쟁점 5). 부팅 30회 이상, 두 표본 각각의 모형 검증 | test-engineer | F1-F4 trace, 로컬 `--repeat 30` |
| R3 | `TargetState` 나이, `/clock` 간격, `now - vehicle_status.timestamp` 분위수, 신선하지 않은 tick 비율, F2와 F4 추종 오차 | `target_timeout`, `target_fresh_age`, 표적 접근 L(쟁점 5, 8, 11). 판단 기준: `TargetState` 나이의 99.9% 분위수가 0.1 s를 넘거나 신선하지 않은 tick 비율이 1%를 넘으면 `target_fresh_age`를 0.15 s로 올리고 L을 같은 식으로 함께 올린다(값과 근거를 PR 본문에 남긴다). 이 전환은 판정의 통과 여부가 아니라 나이 분위수와 tick 비율로 미리 정한 규칙이다. 추종 오차에 비해 L이 모자라면 판정을 느슨하게 하지 않고 architect에게 올린다 | test-engineer | sitl gate의 `recorded_only`, F2, F4 trace |
| R4 | RTL 착륙 수평 위치와 그 비행 기준점(쟁점 5)의 거리 | `R_home`(쟁점 5). 부팅 30회 이상 | test-engineer | F3, F4 trace, 로컬 `--repeat 30`(R2와 같은 실행) |
| 공중 시작 | F3 진입 구간의 위치 변화, P4-P5 소요, P5의 DO_SET_MODE 전송 수, DO_SET_MODE 첫 전송에서 첫 OFFBOARD 표본까지의 시간(D), `vehicle_status` 표본 간격, 첫 OFFBOARD 표본 뒤 P5에 OFFBOARD가 아닌 표본이 있는지 | 섞임 크기, 재전송 중단의 전제(D가 `command_resend_period`보다 작다), K2의 완전성(쟁점 7) | test-engineer | F3 trace |
| RTL | AUTO_RTL 확인 시간, 착지까지, disarm까지 | RTL `timeout` 60 s(쟁점 9) | test-engineer | F3, F4 trace |
| K1 | v1.17.0에서 failsafe 동작이 Hold인 표본의 `vehicle_status.failsafe` 값 | 진입 중 순위 6이 그 표본을 잡는다는 전제(쟁점 7) | px4-engineer | 소스 확인(결과는 쟁점 7 근거) |
| K2 | Offboard 전환 직후 PX4가 AUTO_LOITER로 잠깐 되돌아가는 경우가 있는가 | 첫 OFFBOARD 표본에서 AUTO_LOITER 면제를 끝내는 전제(쟁점 7) | px4-engineer | 소스 확인(결과는 쟁점 7 근거. 완전성은 F3 trace의 "공중 시작"으로 본다) |
| K3 | GNSS 기준 설정에서 위경도 원점과 고도 원점이 늘 같은 EKF 갱신에서 정해지는가 | `ref_alt` 0 창의 크기. 술어는 이와 무관하게 둔다(쟁점 4) | px4-engineer | 소스 확인, B9 헤더 PR 때 |
| K4 | EKF2의 IMU, GPS 위치 오프셋 파라미터가 x500 SITL에서 0인가 | PX4 로컬 위치가 base_link 원점이라는 전제(쟁점 5) | px4-engineer | 소스 확인(결과는 쟁점 5 근거) |

재지 않는 것: L(gz와 ROS `/clock` 도착 차. 쟁점 11의 유지 조건이 깨질 때만), M3(model과 actor 수준 plugin의 영향), M6(표적 수와 서버 CPU. Phase 3 입력), 반복 이륙(U7), 지면 높이 목표에서 OFFBOARD 중의 land detector 시점(단위 테스트로만 덮는다).

## 문서 반영 목록

B1은 설계와 계획 문서(`docs/architecture.md`, `docs/roadmap.md`)의 1b 설계 문장이고, 지금의 동작과 다른 것에는 Phase 한정어("1b", "1b부터")를 달아 구현 전에 고친다. B3 몫은 한정어 없이 지금 실행되는 절차나 구현된 동작을 설명하는 문장(`docs/smoke-test.md`, 서비스 표의 현재 동작, `docs/interface.md`의 사실 문장)이라 B3 PR에서 그 구현과 함께 고친다(먼저 고치면 문서와 main의 코드가 어긋난다). B6, B7 몫은 그 PR에서 생기는 서비스를 설명하는 문장이라 서비스와 함께 고친다. B13은 1b 완료 기준을 만족한 뒤 고친다.

B1(architect)
- `docs/architecture.md` "목표와 범위"의 "다루지 않는 것" 문단(U10). 초안:

  > 다루지 않는 것: 특정 표적을 추적, 교전하는 유도 알고리즘 자체. 움직이는 표적은 `config/fleet.yaml`에 적은 스크립트 궤적을 시뮬레이션 시간에 맞춰 따르는 점 표적으로 두고, 그 위치를 미션 노드가 `TargetState` 계약으로 구독해 따라가는 수준까지만 다룬다. 표적 생산자는 이 계약 뒤에서 교체할 수 있다. 시뮬레이션에서는 표적 어댑터가 궤적 정의를 계산해 채우고, 실기체에서는 같은 토픽을 추적기가 채운다. Gazebo의 물리 상태를 따라 움직이는 표적(반응형 기동 등)의 생산자는 확장 항목이다. 즉 교전 로직이 아니라 그 로직을 올릴 플랫폼(통신, 미션, 텔레메트리, 리플레이, 테스트)을 만든다.

- `docs/architecture.md` 기술 스택 표의 ros_gz_bridge 행("표적 Actor pose, `/clock`을 ROS 2로 노출"을 "`/clock`을 ROS 2로 노출"로)과 Gazebo Actor 행("이동 표적"을 "이동 표적의 화면 확인용. 표적 위치의 원천은 `fleet.yaml`의 궤적 정의"로), 이미지 표의 "뜨는 컨테이너" 열(ros-ws에 `targets`, sim-base에 `sim-oracle`).
- `docs/architecture.md` "전체 아키텍처"의 표적 경로 문단. 초안:

  > 이 원칙은 표적 경로에도 적용한다. Mission Executor는 Gazebo 토픽을 직접 구독하지 않고 `idsim_interfaces`의 `TargetState` 계약(`/targets/<id>/state`)만 구독한다. 시뮬레이션에서는 `idsim_sim`의 표적 어댑터 노드가 `config/fleet.yaml`의 궤적 정의를 시뮬레이션 시간에 평가해 이 계약으로 발행하고, Gazebo 월드의 Actor는 같은 정의로 생성해 화면에서 확인하는 용도다(Actor의 화면 위치는 참고용이다). 실기체에서는 같은 토픽을 추적기가 채운다.

- 같은 절의 구성 요소 표 `idsim_sim` 행("Gazebo pose -> `TargetState`"를 "궤적 정의 -> `TargetState`"로, ros_gz_bridge는 `/clock`만), 토픽 표의 `/targets/*/state` 발행자.
- `docs/architecture.md` "기체 식별과 설정의 단일 출처": `world.origin`의 적용 방식(생성된 월드 SDF), `ops-N` params의 `world.origin`, 표적 어댑터는 원점을 받지 않는 것, `targets` 스키마 요지(네 key 필수와 상한), `world.file` 삭제와 `world.template`, fleet `schema` 2. "`config/fleet.yaml` 하나에서 파생한다"는 문장은 "스택 하나는 그 스택을 만든 fleet 파일 하나에서 파생한다"로 고치고, 개발 스택은 `config/fleet.yaml`, SITL 통합 테스트는 전용 `tests/sitl/fleet.yaml`(쟁점 15)을 쓰며 어느 파일인지는 `stack.json`의 `inputs`에 남는다는 것을 적는다.
- `docs/architecture.md` "Docker Compose 실행 환경 설계": `bridge` 서비스 설명의 "1b에서 Gazebo 표적 pose를 더한다"를 "`/clock`만"으로, 서비스 표에 `targets`(ros-ws, 표적 어댑터)와 `sim-oracle`(sim-base, SITL 전용 정답 pose) 행, 그림의 표적 pose 화살표와 "1b에서 정한다" 문장, 디렉터리 설명의 `idsim_sim`(ament_python 패키지, 월드 템플릿).
- `docs/architecture.md` "테스트 자동화와 CI": 도달 판정 문장("goal의 목표값과 `vehicle_local_position`")을 계약 판정과 정답 판정의 구분으로, `/sim/` 토픽 규칙(운용 패키지는 쓰지 않고 lint가 소스, launch, params YAML을 검사, SITL 기록물에는 들어간다), SITL 시나리오 목록(B, C, A, D, F1, F2, F3, F4, T)과 CI `sitl` 15분 목표.
- `docs/architecture.md` 인터페이스 계약 절 시간 기준 요지의 bridge 문장("1b에서 표적 pose를 더한다"를 "bridge가 넘기는 토픽은 `/clock` 하나"로). 쟁점 2의 확정 사항이고 계약 고정과 무관하다.
- `docs/roadmap.md` Phase 1b: 2번의 `bridge.yaml`, "Gazebo pose -> `TargetState`", "표적 상태의 생산 경로는 1b 착수 때 정한다"를 해법 (가)와 U10 문구로, "EKF 원점 오차 실측으로 표적 접근 임계값을 정한다"를 R2와 R1의 역할로, 4번의 판정 문장("반경 1 m 이내 도달"은 그대로 두고(U14), 판정 입력이 정답 pose라는 것과 표적 접근 임계값 `1 m + v x L`, 합친 미션 하나로 판정한다는 것(U13)을 더한다). 리스크 표의 해당 행(Actor pose, 범위 문구, `bridge.yaml` 금지 검사, "범위 확장 유혹"의 "pose를 따라가는 Actor")을 지금 유효한 대응으로. 확장 후보에 "Gazebo 기반 표적 생산자".
- `docs/roadmap.md` Phase 2: 기록 대상에 SITL 실행의 `/sim/` 토픽(U12), 리플레이 판정이 도달 판정까지 덮는다는 것.

B3(B3 PR 안에서. M5 통과 결과대로)
- architect: `docs/smoke-test.md`. "서비스별 환경변수"의 `gazebo` 문단(명령이 생성된 월드 `/opt/idsim/world/<월드>.sdf`를 연다, wrapper의 원점 단계), healthcheck 표의 gazebo 행(준비 파일의 조건), px4-out과 "예외 사항과 가정"의 원점 판정 문장(기대값은 `stack.json` `vehicles[0].expect_gps`, base_link 높이 포함, 기체 1은 원점에서 떨어진 스폰), `px4` 문단의 `PX4_GZ_MODEL_POSE` 값, images 단계의 센서 높이 대조(S0), `sim_stack.sh`의 월드 파일 사전 검사. 원점은 월드 SDF로만 들어가고 `set_spherical_coordinates` 호출과 `origin_set`이 없다고 적는다.
- architect: `docs/architecture.md` "Docker Compose 실행 환경 설계"의 `gazebo` 서비스 행(wrapper의 런타임 `set_spherical_coordinates` 호출과 "원점 단계가 끝나면 준비 파일" 문장을 M5 결과대로, 여는 월드가 생성된 월드라는 것)과 시작 순서 문단의 gazebo healthcheck 문장, 월드 파일 사전 검사. "기체 식별과 설정의 단일 출처"와 볼륨 표에서 B3으로 지금 사실이 된 문장(fleet `schema` 2, `world.template`, `world.file` 없음, `world.origin` 필수, 생성된 월드 마운트)의 Phase 한정어를 떼고, `vehicles[].expect_gps`와 `inputs`의 월드 템플릿을 적는다. `docs/roadmap.md` Phase 1a 3번의 "원점 설정 완료 표시"와 "wrapper가 월드 로드 직후 한 번 설정" 문장도 같은 결과로 고친다.
- architect: `docs/interface.md` "SITL 파라미터" 절의 "월드 원점은 gazebo wrapper가 `world.origin`으로 적용한다"(위 (r))를 M5 결과대로, "시간 기준" 절의 "1a는 `/clock`만 브리지한다"(위 (k)의 앞부분)를 "bridge가 넘기는 토픽은 `/clock` 하나"로. 둘 다 계약 고정과 무관한 사실 갱신이다. 앞의 것은 B3 구현 뒤에 사실이 되고, 뒤의 것은 같은 파일의 같은 커밋에 묶는다.
- devops-engineer: `docker/README.md`의 서비스 표 gazebo 행의 원점 문장, 변형 절의 embedded 문장, 생성 절의 `world.origin` 문장, 저장소 `README.md`의 "기체 출발 위치는 `world.origin`" 문장.

B6(B6 PR 안에서. `targets` 서비스와 함께)
- devops-engineer: `docker/README.md` 서비스 표의 `targets` 행(ros-ws, 표적 어댑터, 준비 판정은 표시 파일, fleet 파일에 표적이 없으면 만들지 않는다)과 기동 순서 그림의 노드 단계.

B7(B7 PR 안에서. `sim-oracle` 서비스와 함께)
- devops-engineer: `docker/README.md` 서비스 표의 `sim-oracle` 행(sim-base, SITL 전용 정답 pose, 준비 판정은 표시 파일, standalone이면 항상 만든다)과 기동 순서 그림의 노드 단계.

B13(1b 완료 전, architect)
- `docs/interface.md`: 위 "1a 고정 계약 영향" (a)-(t)와 후보 (u)(B3 묶음의 (r)과 (k) 앞부분, (s)는 B4 PR에서 반영해 표에서 뺐다. (k)의 뒷부분은 "시간 기준" 예외 문장의 "지연 크기는 미측정"을 쟁점 11의 실측으로, "3개가 되려면 ... 약 1 s 동안 처리되지 않아야 한다"를 쟁점 11의 유지 조건(W_arm 대 publish 간격 두 개)으로 고치는 것), "GoToItem과 TrackEntityItem" 절의 확정 문장(쟁점 8, 속도 feedforward 포함), "TargetState" 절의 "고정 전" 해제와 QoS 상태 행 고정, `REASON_TARGET_LOST` 의미, "공중에서 끝나는 미션" 절(쟁점 10, 지면 높이 목표의 경합 문장 포함), "참고: 노드 파라미터" 표의 `hold_confirm_timeout`(종료 단계의 Hold 확인)과 `land_disarm_fallback_delay`(지상 대기의 대비책 disarm) 덮는 것 열, 고정 시점 표의 1b 행, 미확인 목록의 1b 항목(K1-K4의 결과).
- `ros_ws/src/idsim_interfaces/`: `ExecuteMission.action`, `MissionItem.msg`, `YawSetpoint.msg`, `TakeoffItem.msg`, `GoToItem.msg`, `TrackEntityItem.msg`, `TargetState.msg`의 의미 주석. golden 무변경을 단정한다.
- `docs/architecture.md` 인터페이스 계약 절: 묶음 표의 1b 행, 미션 실행 요지의 재진입 문장(h), 공중 종료 문장, RTL 요지.

## 넘김 목록

| 받는 쪽 | 시점 | 항목 |
| --- | --- | --- |
| px4-engineer, ros2-engineer, architect | 반복 비행의 소비자가 생길 때(Phase 3 이후) | 첫 항목이 아닌 TAKEOFF 허용. 규칙 후보: LAND나 RTL 바로 뒤에만, 준비 단계를 P0부터 다시, `ready_timeout`은 항목 시작부터, P5는 그 항목의 DO_SET_MODE 뒤 표본만 |
| px4-engineer, architect | Phase 2(다중 스택 부하) | 쟁점 11의 유지 조건을 다시 본다. 부하 아래 ULog에서 W_arm과 arm 처리 전 창의 `vehicle_status` publish 간격(지상 DISARMED 구간의 촘촘한 publish 원인 포함), 순서 불변식의 전제(W_DO_SET_MODE가 `command_resend_period`보다 작다), 공중 Offboard 진입에서 첫 OFFBOARD 표본 전에 재전송이 나가지 않는다는 전제(DO_SET_MODE 전송에서 OFFBOARD 표본 도착까지의 지연 D가 `command_resend_period`보다 작다. 부하 아래 D의 분위수를 본다. 쟁점 7). 조건이 깨지면 쟁점 11의 ack timestamp 기준과 `AckSample.timestamp_us` |
| px4-engineer, architect | Phase 3 | `RTL_RETURN_ALT`를 기체별 `px4_params`로 덮어도 계약 안으로 두는 예외(고도 층 분리) |
| ops-service-engineer | Phase 3 | Fleet의 배분 전 검증은 core `validate_mission_contract`를 쓴다. 공중 종료 미션의 끝점이 겹치지 않게 하는 계획 책임. 공중 시작 미션은 Hold인 기체에만 보낸다 |
| px4-engineer | Phase 3 설계 후보 | `VEHICLE_CMD_SET_GPS_GLOBAL_ORIGIN`으로 모든 기체의 EKF 원점을 `world.origin`에 맞추는 안(실측 없이 1b에 넣지 않는다) |
| logging-engineer, architect | Phase 2 | U12에 따라 SITL 기록물에 `/sim/` 토픽을 넣는 기록 대상 정의, 미션 YAML과 `stack.json`과 라이브 `verdict.json`을 기록물 디렉터리에 함께 두는 규약, bag 로그 시각이 sim 시각인지, 순수 Python mcap 읽기 |
| test-engineer | B3, B11 | `tests/support/stack.py` 판 5 명세(`expect_gps`, `targets`, `services.targets`, `services.sim_oracle`, `world.template`), `tests/sitl/fleet.yaml`과 `run_sitl.sh --fleet`, F4 미션 YAML, `/sim/<vehicle_id>/pose` 조립 함수와 사례 표 |
| px4-engineer | B3 | `tests/smoke/check_px4.py` 고도 주석("기대값에 base_link 높이를 넣었다") |
| sim-engineer | B3, B6, B7 | `idsim_sim` 실행 이름(생성기 상수 하나), `sim_oracle.py`의 환경 변수 계약(`IDSIM_WORLD_NAME`, `IDSIM_ORACLE_VEHICLES`), `/sim/<vehicle_id>/pose` 조립 함수와 사례 표, 두 표시 파일의 경로, Actor waypoint 표본 간격(M4 뒤), `idsim_base.sdf`가 생성기 거부 조건을 지키는지 |
| devops-engineer | B3, B6, B7 | 생성기, fixture와 golden, `config/fleet.yaml`(schema 2, template, 기체 1 스폰), `sim_stack.sh` 사전 검사, `tools/ci/lint.sh`의 `/sim/` 검사(운용 패키지의 소스, launch, params YAML), `docker/README.md`, `tests/smoke/run_smoke.sh`의 `origin_args` 출처 변경(`expect_gps`)과 S0 센서 높이 항목. sim-base에 패키지가 필요해지면 이미지 변경만 담은 PR을 먼저 main에 합친다(sim-base와 px4 key가 바뀌어 `sitl` pull이 실패하는 문제를 피한다). 이미지 key가 바뀌는 PR은 CI `sitl`이 아직 publish되지 않은 이미지를 pull하지 못하므로 로컬 `tests/sitl/run_sitl.sh`로 머지를 판정하고 결과를 PR 본문에 남긴다. 머지 뒤 publish가 끝나면 main에서 `sitl`을 다시 돌려 통과를 확인한다 |
| sim-engineer | 플래키가 보일 때 | Xvfb와 소프트웨어 렌더링으로 `gz-gui` 생존 확인 자동화 |
| sim-engineer, architect | Gazebo 기반 표적 생산자가 필요할 때(U10의 확장 항목) | 서버 plugin이 model을 이동하는 안(Actor를 쓰지 않아 `dynamic_pose` 위험이 사라진다) 또는 Actor 컴포넌트를 읽는 system. `TargetState`와 토픽은 그대로이고 생산자만 바뀐다 |
