# Phase 1b 미션 시퀀스와 표적 추종 설계 결정

Phase 1b(미션 시퀀스와 표적 추종)의 설계 결정이다. 구현은 이 문서를 따른다. 지금 유효한 것만 적는다. 결정의 경위(담당자 의견, 토론, 검토)는 커밋 메시지와 PR 본문에 있다. 작업 단위와 완료 기준은 같은 디렉터리의 `README.md`에, `docs/`에 반영할 것은 아래 "문서 반영 목록"에 있다.

표기: [소스]는 PX4 v1.17.0, gz-sim 8.15.0, 저장소 원문으로 확인한 것, [실측]은 1a에서 잰 것, [추정]은 확인하지 않은 판단이다. 상태 표기: "확정"은 그대로 구현한다. "재질문"은 아래 "재질문" 절의 번호에 대한 담당자 답을 받아 확정한다. "사용자"는 아래 "사용자 결정 대기" 절의 번호에 대한 사용자 결정을 받아 확정한다. 재질문이나 사용자 결정이 이 문서의 결정을 뒤집으면 해당 쟁점을 고쳐 쓴다.

## 사용자 결정

- U7: 1b 범위에서 반복 이륙(첫 항목이 아닌 TAKEOFF)은 뺀다. 1b에서도 Executor가 거부한다. 계약 문장으로 올릴지는 architect가 정한다(쟁점 6에서 계약으로 올린다).
- U8: `COM_LOW_BAT_ACT`를 계약 SITL 파라미터 표에 넣어 2(Land)로 고정한다.
- U9: `RTL_RETURN_ALT`는 미션 고도에 맞춰 정한다. x500 기본값은 30 m다. 값은 1b 미션 고도와 함께 px4-engineer와 architect가 정한다(쟁점 9).
- 대기: U10(범위 문구), U11(CI `sitl` 시간 예산), U12(정답 pose의 기록물 포함 범위). "사용자 결정 대기" 절.

## 결정 요약

| 쟁점 | 결정 | 1a 고정 계약 영향 | 상태 |
| --- | --- | --- | --- |
| 1. 표적 생산 경로 | (가) 어댑터가 `fleet.yaml`의 궤적 정의에서 계산한다. Gazebo Actor는 같은 정의로 생성하는 화면 확인용 | 없음(`TargetState`는 1b 고정) | 사용자(U10) |
| 2. 월드, 원점, bridge | 월드 SDF를 템플릿에서 생성. 원점은 SDF로만 넣고 런타임 호출 제거. 월드 직속 `<plugin>` 거부. bridge 토픽은 허용 목록 검사 | 없음 | 확정(M5 조건) |
| 3. 표적 어댑터와 `TargetState` 발행 | Python(rclpy) 노드, 별도 compose 서비스 `targets`. stamp는 계산 시각, 같거나 작은 stamp 발행 금지. QoS는 계약 상태 행 | 공통 규칙 "이름과 식별자"의 Python 조립 위치 | 재질문 S-3 |
| 4. 원점 이동 변환 | gz와 PX4의 식을 그대로 재현하는 사슬(`idsim_common::geo`). core에는 `FramePort`로 주입 | 없음 | 재질문 S-2, P-1 |
| 5. 판정 입력과 임계값 | 도달의 주 판정은 SITL 전용 정답 pose와 world 목표. 반경은 `acceptance_radius_m + b`이고 b는 R2에서 정한다. 정답 pose는 계약 토픽이 아니다 | 없음 | 재질문 P-1, S-1, T-1. 기록물은 사용자(U12) |
| 6. 항목 순서 규칙 | "TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막에만"을 계약으로 올린다 | 1a 임시 제한 문장을 계약 문장으로 바꾼다 | 확정 |
| 7. 공중 시작 미션 | Hold(AUTO_LOITER)이고 failsafe가 아닌 공중 ARMED 기체만 받는다. 진입 setpoint는 현재 위치와 heading. 감시는 P3부터, OFFBOARD 확인 전에는 AUTO_LOITER를 이탈로 보지 않는다 | 준비 단계, 발행 규칙, 감시 시작, reason "나오는 곳"의 확장 | 재질문 R-2 |
| 8. GOTO, TRACK_ENTITY | 도달은 서로 다른 위치 표본 3개 연속. 같은 tick 순서는 감시 표, TARGET_LOST, ITEM_TIMEOUT, 완료. TARGET_LOST는 정리를 거친다. `MODE_KEEP`은 직전 setpoint의 yaw | "정리"의 원인 목록 확장 | 확정 |
| 9. RTL과 SITL 파라미터 | 모드 명령 항목. AUTO_RTL 3회 확인, 지상 DISARMED 3회 완료. 실패 폴백은 Land. 파라미터 여섯을 계약 표에 더한다 | SITL 파라미터 표에 행 추가, "LAND 항목" 절을 모드 명령 항목 절로 | 재질문 P-3 |
| 10. 공중에서 끝나는 미션 | Hold 3회 확인 뒤 SUCCEEDED. 취소의 공중 분기와 Hold 실패 뒤 Land 경로만 쓴다 | "끝난 뒤 기체 상태" SUCCEEDED 행을 마지막 항목별로 나눈다 | 재질문 P-2, R-3 |
| 11. 지상 취소의 disarm 확인 | `/clock` 지연 L 대신 명령에서 ack까지의 창 W를 ULog로 잰다. 기준을 넘으면 ack timestamp 기준으로 바꾼다 | 바꾸게 되면 "시간 기준"의 예외 문장과 "취소" 절 | 확정(W 결과 조건) |
| 12. snapshot과 core 구조 | 헤더 추가는 한 번에 묶어 px4-engineer가 승인한다. W 결과 뒤에 확정 | 없음 | 재질문 P-4 |
| 13. 전이 덮음 | 승인된 칸 목록이 "전부"의 정의. 테스트가 지나간 변을 관측해 미덮임 0을 단정 | 없음 | 재질문 R-1 |
| 14. YAML 로더, `idsim_common` 공개 | 로더는 `idsim_mission` 안의 Python 모듈. takeoff 빌더 없음, `goto_setpoint`는 Restricted 유지 | 없음 | 확정 |
| 15. 시나리오와 CI 시간 | B(1b 무효 사례 추가), C, A, D, F1, F2, F3, T를 한 스택에서 이 순서로 | 없음 | 사용자(U11), 재질문 T-2, T-3 |
| 16. 다대 원점 판정 | `stack.json`의 기체별 `expect_gps`를 생성기가 계산하고 `check_px4`는 비교만 | 없음 | 확정 |
| 17. viz 확인 | Actor 월드에 `gz-gui`를 붙이는 수동 확인 1회. CI에 넣지 않는다 | 없음 | 확정 |

## 쟁점 1. 표적 상태 생산 경로

결정
- 해법 (가): 표적 어댑터가 `config/fleet.yaml`의 `targets` 궤적 정의를 노드 시계(ROS 시각) t에서 평가해 `TargetState`를 낸다. 월드 SDF의 Actor는 같은 정의에서 생성하는 화면 확인용이다. 표적 위치의 원천은 Gazebo가 아니다.
- 궤적 정의의 유일한 출처는 `fleet.yaml`의 `targets`다. 생성기가 정규화한 값을 월드 SDF의 Actor, 어댑터 params, `stack.json` 셋에 낸다. 어댑터는 `fleet.yaml`을 읽지 않는다.
- 스키마(devops-engineer 소유, sim-engineer 접점 검토): `targets[]`의 `id`(`target_id` 규칙, 중복 금지), `start_s`(그 전에는 첫 waypoint에 정지), `loop`(true면 처음과 끝 waypoint가 같아야 한다), `waypoints[]`의 `{t, x, y, z}`(world ENU m, t는 `start_s` 기준 s, 첫 t는 0, 엄격히 증가, 2개 이상).
- 보간은 구간 직선이고 속도는 구간 기울기다(`velocity_valid` true, 정지 구간은 0 벡터). waypoint 시각 정확히에서는 다음 구간 값이다. `loop` false면 끝난 뒤 마지막 점에 정지한다.
- 생성기 거부 조건: id 형식과 중복, waypoint 2개 미만, t 비증가, 첫 t가 0이 아님, `loop`인데 처음과 끝이 다름, z < 0, 구간 속도 상한 초과(값은 재질문 P-5), t=0 위치가 기체 스폰 지점과 수평 2 m 안.
- Gazebo Actor는 spline 보간이라 waypoint 사이에서 `TargetState`와 어긋난다. 이 차이는 `TargetState` 계약에 적지 않는다(`TargetState`는 시뮬레이터를 모른다). `docs/architecture.md`의 시뮬레이션 레이어 설명과 `idsim_sim` README에 "Gazebo 화면의 Actor 위치는 참고용"으로 적는다. 생성기는 Actor waypoint를 촘촘히 샘플한다(간격은 sim-engineer가 M4의 육안 확인으로 정한다).

근거
- [소스] 스크립트 궤적은 렌더링 쪽(`SceneManager`)에서만 평가되고 서버 ECM에는 궤적을 평가하는 system이 없다(sim-engineer). 그래서 (다)는 같은 계산을 C++ system으로 다시 하는 것이고, 얻는 것은 GUI와의 일치와 문구뿐이다.
- 소비자(Executor, 판정, 기록)에게 정본은 `TargetState`이고 원천이 어디인지는 보이지 않는다. 가장 싼 경로를 고른다. stamp와 값이 같은 함수에서 나와 시간 정합이 정의로 성립한다(ros2-engineer).
- 되돌리기 쉽다. (나-2)나 (다)로 바꿔도 `TargetState`, 토픽, `targets` 스키마는 그대로이고 어댑터의 입력만 바뀐다.

담당자 의견과의 대응
- sim-engineer: 권고 (가)를 채택. (나-1) 외부 `set_pose` 기각도 채택. "Actor 위치는 참고용"을 `TargetState` 계약에 넣자는 질문은 받지 않고 architecture.md에 둔다(위 근거).
- ros2-engineer: (가) 권고와 같다.
- test-engineer: 판정은 수신한 `TargetState`만 본다는 sim-engineer 제안에 동의했고 그대로 채택(쟁점 5).
- 범위 문구가 바뀌므로 사용자 결정 U10을 기다린다. U10에서 "Gazebo가 원천"을 유지하면 이 쟁점을 (다)로 고쳐 쓴다.

## 쟁점 2. 월드 SDF, 원점, bridge, 커스텀 모델

결정
- 손으로 쓰는 월드는 템플릿 하나 `ros_ws/src/idsim_sim/worlds/idsim_base.sdf`다(PX4 `default.sdf`의 physics, scene, light, ground를 출처 주석과 함께 옮긴다. 월드 직속 `<plugin>`, `<spherical_coordinates>`, `<actor>`는 넣지 않는다). 생성기가 이 템플릿에 `<world name>`, `<spherical_coordinates>`(`world.origin`, heading 0, ENU), 표적마다 `<actor>`를 넣어 `artifacts/runs/<실행 id>/world/<name>.sdf`로 쓰고 gazebo 서비스에 읽기 전용으로 마운트한다. 표적이 없어도 같은 경로로 생성한다.
- `world.origin`은 필수다. 생성기가 누락을 거부한다. `world.file`의 의미와 key 이름(템플릿 경로), 스키마 번호는 devops-engineer가 sim-engineer와 정한다(재질문 D-1).
- 원점은 SDF로만 넣는다. `gz_server.sh`의 런타임 `set_spherical_coordinates` 호출과 표시 파일 `origin_set`을 지운다. 조건: M5(원점을 SDF로만 넣은 스택에서 스모크 S2의 `sensor_gps` 판정이 통과)가 통과해야 지운다. wrapper는 SDF에 `<spherical_coordinates>`가 정확히 하나인지만 본다.
- 일치 검사는 하지 않고 구성으로 보장한다. 생성기 단위 테스트가 생성된 SDF의 위도, 경도, 고도, heading 0, ENU가 `fleet.yaml` 값과 같음을 단정한다. 실제 적용은 스모크 S2가 판정한다.
- 생성기는 템플릿과 출력 SDF에서 월드 직속 `<plugin>`을 찾으면 거부한다(있으면 `server.idsim.config`가 무시된다). Actor 안에도 `<plugin>`을 넣지 않는다.
- bridge: 1b의 bridge 토픽은 `/clock`(gz -> ROS)과, 쟁점 5의 정답 pose를 bridge로 낸다면 그 경로뿐이다. 표적 pose는 bridge를 거치지 않는다. 형식(명령행 인자 유지 또는 생성 파일)은 sim-engineer와 devops-engineer가 정하고, 어느 형식이든 생성기 단위 테스트가 허용 목록(토픽과 방향)과 금지 정규식 `dynamic_pose`를 검사한다. `gui.config`의 plugin 목록도 고정하고 `dynamic_pose` 문자열이 없음을 단위 테스트가 본다.
- bridge healthcheck는 `/clock` 1회 수신 그대로다.
- 커스텀 모델: M1(`<skin>` 없이 `<link>` visual만 가진 Actor가 GUI에서 보이고 움직이는가)이 통과하면 모델 파일을 두지 않는다. 실패하면 `idsim_target` 모델 하나를 두고 `GZ_SIM_RESOURCE_PATH` 뒤에 `/opt/idsim/sim/models`를 붙인다(커스텀 모델 이름은 `idsim_` 접두, 생성기 단위 테스트가 확인).

근거
- Actor 궤적과 원점을 SDF에 손으로 다시 적으면 출처가 둘이 된다.
- 원점이 월드 로드 때 들어가면 PX4 첫 GNSS fix보다 늦을 수 없다. 런타임 호출은 대개 앞서지만 순서가 구조로 보장되지 않는다([추정] sim-engineer). M5가 이 판단을 확인한다.
- 표적이 bridge를 거치지 않으므로 bridge 설정 파일을 표적 목록에서 만들 이유가 없어졌다. 검사 지점은 형식과 무관하게 생성기 단위 테스트다.

담당자 의견과의 대응
- sim-engineer 2-2, 3, 4절 채택. 2-3절의 "`bridge.yaml`로 옮긴다"는 형식 선택으로 낮췄다(소비자가 하나 늘지 않는 한 형식은 담당자가 정한다).
- test-engineer: S2의 `origin_set` 의존 여부는 test-engineer가 `run_smoke.sh`를 보고 고친다(B3의 일).

## 쟁점 3. 표적 어댑터 노드와 TargetState 발행

결정
- 언어: Python(rclpy). `docs/architecture.md` 기술 스택의 "도구, 테스트, 어댑터 Python"을 따른다. sim-engineer의 C++ 컴포넌트 안은 언어 선택의 변경이라 이 토론에서 정하지 않는다(재질문 S-3에서 막는 이유가 나오면 사용자에게 올린다).
- 구조: 노드 하나가 모든 표적을 발행한다(표적별 publisher). 궤적 평가는 ROS 비의존 순수 함수이고 시뮬레이터 없는 단위 테스트가 같은 평가 함수를 부르지 않고 손으로 계산한 golden 표와 비교한다(표의 위치는 test-engineer가 정한다).
- 실행 위치: 별도 compose 서비스 `targets`(ros-ws 이미지, `depends_on: bridge` healthy). `targets`가 비면 서비스를 만들지 않는다. `ops-N`은 `targets`를 기다리지 않는다. 기동 단계(`startup.node_stages`)의 위치와 healthcheck 방식은 devops-engineer와 sim-engineer가 정하고, 판정 조건은 "모든 표적의 `TargetState`가 `/clock` 시작 뒤 한 번 이상 발행됨"이다.
- 토픽: 절대 이름 `/targets/<target_id>/state`. 메시지 상수 `TOPIC_PREFIX`, `TOPIC_SUFFIX`로 조립한다. 노드 네임스페이스는 기체 네임스페이스가 아니다.
- QoS: 계약 상태 행(발행 RELIABLE, VOLATILE). 구현 값 KEEP_LAST 5. Python은 `contract_qos.hpp`를 쓰지 못하므로 값을 다시 적고, 통합 테스트가 그래프의 발행자 QoS를 계약과 대조한다.
- stamp: timer가 깨어난 노드 시계 시각 t이고 위치는 f(t)다. 0을 내지 않는다. 표적마다 직전 발행 stamp보다 큰 t에서만 발행한다(`/clock` 정지나 역행에서 발행하지 않는다. 역행은 오류 로그를 남긴다). `use_sim_time` false이면 시작을 거부한다. 주기는 params(기본 20 Hz, 계약 아님).
- 이름 조립과 id 검증: Python 쪽 생산자가 처음 생긴다. 어댑터 패키지 안에 조립과 `target_id` 정규식 검증 함수를 두고 `tests/support`와 같은 사례 표로 단위 테스트한다. `docs/interface.md` "이름과 식별자"의 "Python은 `tests/support`가 한다"를 "판정은 `tests/support`, 발행은 표적 어댑터"로 고친다(1a 고정 계약 영향 (j)).
- 원점: 어댑터는 원점을 모른다. 출력은 world ENU뿐이다. architecture.md의 "운용 노드와 표적 어댑터는 같은 값을 params로 받는다"에서 표적 어댑터를 뺀다.
- replay 프로필에서는 어댑터를 띄우지 않는다(발행자가 둘이 된다).

근거
- 별도 서비스로 두면 bridge healthcheck가 `/clock`만으로 남고(progress의 "표적 어댑터 판정은 별도 단계"), 표적 생산 실패가 기체 노드 기동을 막지 않으며, 소실 시험에서 서비스 하나만 멈출 수 있다.
- stamp 규칙은 계약("유효한 ROS 시각, 0이 아님, 단조 증가")을 생산자 쪽에서 구조로 지키는 방법이다. (가)에서는 유효 시각과 계산 시각이 같다.

담당자 의견과의 대응
- ros2-engineer 7절의 "bridge 컨테이너 안에서 돈다"는 기각하고 sim-engineer 4절의 별도 서비스를 채택했다(위 근거).
- ros2-engineer 7절의 "어댑터는 Python"을 채택, sim-engineer의 C++ 컴포넌트 안은 보류(재질문 S-3).
- sim-engineer의 `/clock` 역행 시 발행 중단과 ros2-engineer의 "같거나 작은 stamp 발행 금지"는 같은 규칙으로 합쳤다.

## 쟁점 4. 원점 이동 변환

결정
- 입력: params의 `world.origin`(생성기가 `ops-N` params에 `world.origin.lat`, `lon`, `alt`를 싣는다. Executor는 configure에서 누락을 거부한다)과 `vehicle_local_position`의 `ref_lat`, `ref_lon`, `ref_alt`(`xy_global`, `z_global`이 true일 때만 유효). 스폰 pose는 입력이 아니다.
- 사슬: world ENU 점 -> WGS84(gz `SphericalCoordinates`의 식, 원점 `world.origin`) -> 기체 로컬 NED(PX4 `MapProjection`의 식, 기준 `ref_*`, 고도는 `ref_alt`와의 차). 평행 이동 근사를 쓰지 않는다. 역방향(로컬 NED -> world ENU)도 같이 만들고 왕복 테스트로 묶는다(Phase 2 Collector가 쓴다).
- 위치: 식은 `idsim_common::geo`(Eigen만 쓰는 순수 함수). `vehicle_local_position`에서 기준을 읽는 함수는 px4 어댑터(px4-engineer 소유). core에는 snapshot 헤더의 `FramePort`(`world_to_local`, 기준이 무효면 값 없음)로 주입한다. 노드 구현은 그 tick의 최신 기준과 params 원점으로 `geo`를 부른다.
- 단위 테스트: gz-math `SphericalCoordinates`와 PX4 `MapProjection`의 알려진 값과 차등 비교한다. 원문의 판(gz-math 7, PX4 v1.17.0)을 테스트 주석에 고정한다.
- 원점 변경: 변환을 tick마다 최신 기준으로 하므로 `ref_timestamp`가 바뀌어도 따로 다시 만들 것이 없다. 비행 중 바뀌면 Executor가 WARN 로그 한 줄을 남긴다. 사건 메시지는 더하지 않는다.
- 커스텀 월드의 `world_frame_orientation`은 생성기가 ENU로만 쓰므로 검사하지 않는다(쟁점 2의 구성 보장).

근거
- [추정, architect 계산] PX4 `MapProjection`은 반지름 상수 하나의 구면 방위 등거리 투영이고 gz는 WGS84 타원체다. 위도 37.6도에서 WGS84의 곡률 반지름은 남북 약 6359 km, 동서 약 6386 km로 구면 6371 km와 각각 약 0.19%, 0.24% 다르다. 원점에서 100 m면 약 20 cm다. PX4가 자기 GNSS를 같은 투영으로 로컬로 바꾸므로 같은 사슬을 재현하면 이 척도 차이가 상쇄된다. px4-engineer 의견의 "수백 m에서 cm 아래"는 이 계산과 다르다. 확인은 재질문 P-1, S-2.
- [소스] `check_core_purity.cmake`가 core에서 `idsim_common`을 금지하므로 port 주입이 "변환은 `idsim_common` 한 곳"과 core 순수성을 함께 지킨다.

담당자 의견과의 대응
- ros2-engineer 4.3절과 5절 채택.
- px4-engineer 6절의 입력(`ref_*`와 `world.origin`, 스폰 pose 제외)은 같다. 평행 이동 근사 허용은 위 근거로 받지 않는다. `ref_timestamp` 변경 감지는 tick마다의 변환으로 대신한다.
- sim-engineer: 어댑터는 원점을 모른다(쟁점 3)와 같다.

## 쟁점 5. 판정 입력과 임계값

결정
- 판정 입력은 둘로 나눈다. 계약 판정은 계약 토픽과 PX4 토픽(`mission_event`, feedback, result, `vehicle_status`, `vehicle_land_detected`, `vehicle_local_position`, `TargetState`)만 쓴다. 정답 판정은 SITL 전용 정답 pose(Gazebo의 기체 pose, world ENU)를 쓴다. 판정 코드는 두 부분을 함수 수준에서 나눈다. 정답 pose가 있어야 하는 실행에서 없으면 실패(`ORACLE_ABSENT`)이고 조용히 건너뛰지 않는다.
- 웨이포인트 도달의 주 판정은 정답 판정이다: world ENU 목표와 정답 pose의 3차원 거리가 `R_judge = acceptance_radius_m + b` 안인 서로 다른 stamp 표본 3개 연속. 테스트는 Python에서 원점 변환을 다시 구현하지 않는다. Executor가 항목을 완료로 넘긴 시각 직전 1 s 안에 `R_judge` 안의 정답 표본이 있어야 한다(없으면 `REACH_MISMATCH`). 수평과 수직 성분은 trace에 따로 남기고 통과 기준은 3차원 하나다.
- b의 정의: Executor가 도달로 넘긴 순간의 정답 pose와 world 목표 사이 거리에서 `acceptance_radius_m`을 넘는 부분의 상한(R2). F1의 trace에서 얻고, 표본 수와 함께 `tests/support/sitl_judge.py` 머리말에 적는다. 정하기 전에는 상수를 비워 두고 테스트는 "b 미정"으로 실패한다. 정한 뒤 통과와 실패를 보고 바꾸지 않는다. b가 0.5 m를 넘으면 판정을 느슨하게 하지 않고 architect와 사용자에게 올린다.
- R1(EKF 원점과 기대 스폰 위치의 차)은 b의 입력이 아니라 기록 항목이다. sitl gate가 매 실행 `verdict.json`에 `recorded_only`로 남긴다.
- 표적 접근: 판정은 수신한 `TargetState`만 본다(정의에서 기대 위치를 다시 계산하지 않는다). 기체 표본 시각마다 표적 위치를 감싸는 두 `TargetState` 표본에서 선형 보간하고 외삽하지 않는다. 임계값은 `acceptance_radius_m + b + v x L`이고 v는 시나리오 표적 속도, L은 추종 지연이다. 시나리오의 표적 속도를 작게 잡아(1-2 m/s) v x L을 b 아래로 줄이는 것이 먼저다. 접근 구간에 표적이 실제로 움직였음을 단정한다(`NO_TARGET_MOTION`).
- 착륙 후 disarm: 1a의 `disarmed_confirmed`, `landed_confirmed`를 그대로 쓰고, DISARMED 시점의 정답 z가 이륙 지점 z + 0.3 m 안임을 더한다. RTL이면 착륙 수평 위치가 그 비행의 이륙 직전 정답 위치에서 `R_home` 안이다(`R_home`은 b와 함께 정한다). 판정은 미션의 종료 유형(`LANDED_DISARMED`, `HOLD_AIRBORNE`)으로 매개변수화한다. `SUCCEEDED => disarm` 가정을 두지 않는다.
- 정답 pose는 `idsim_interfaces`의 계약이 아니고 `docs/interface.md`의 계약 절에 넣지 않는다. 시뮬레이터 전용 토픽은 접두 `/sim/`을 쓴다(정답 pose는 `/sim/<vehicle_id>/pose`. 타입과 경로는 재질문 S-1). 운용 패키지(`idsim_common`, `idsim_mission`, 그리고 앞으로의 `idsim_telemetry`, `idsim_fleet`, `gateway/`)는 `/sim/`을 쓰지 않고 lint가 검사한다. 이 규칙은 `docs/architecture.md`의 테스트 절에 둔다.
- 기록물에 넣을지는 Phase 2의 기록 대상 결정이고 사용자 결정 U12를 받는다. 1b는 판정 코드를 두 부분으로 나누는 것까지 한다.

근거
- Executor는 EKF 위치로 도달을 판정한다. 테스트도 EKF 위치로 판정하면 EKF 오차와 원점 변환 오류가 양쪽에 같이 실려 보이지 않는다. 정답 pose는 사슬 전체를 독립으로 보는 유일한 입력이다(test-engineer, ros2-engineer).
- [추정, architect 분석] 사슬 변환(쟁점 4)에서 Executor의 목표와 기체의 추정 위치는 같은 `ref_*`를 쓰고 기체 추정은 GNSS에 묶여 있으므로, 첫 fix의 잡음 n0는 수평에서 상쇄된다. 남는 수평 오차는 EKF 추정과 실제의 차(R2)다. 수직은 EKF 높이 기준이 기압계이면 `ref_alt`의 초기 잡음이 남을 수 있다. 그래서 b는 R2로 정하고 R1은 기록만 한다. test-engineer 의견의 "기체는 물리적으로 목표 - n0에 도착한다"는 원점을 스폰 지점으로 가정할 때의 결론으로 보고 받지 않았다. 확인은 재질문 P-1.

담당자 의견과의 대응
- test-engineer 1.0-1.3절 채택. b의 출처를 R1에서 R2로 바꿨다(재질문 T-1). 정답 pose를 interface.md에 올리자는 제안은 받지 않고 architecture.md 테스트 절의 규칙으로 둔다(계약은 운용 서비스와 시뮬레이션 사이의 것이고 이 토픽은 운용 서비스가 쓰지 않는다).
- ros2-engineer 8절 test 질문 1(정답 pose로 world 목표와 비교) 채택.
- sim-engineer 7절(판정은 수신한 `TargetState`만) 채택.
- `docs/architecture.md`의 "도달은 goal의 목표값과 `vehicle_local_position`"을 고친다(문서 반영 목록).

## 쟁점 6. 항목 순서 규칙과 첫 항목이 아닌 TAKEOFF

결정
- 계약 문장으로 둔다: TAKEOFF는 첫 항목에만 온다. LAND와 RTL은 마지막 항목에만 온다. 그래서 모드 명령 항목으로 시작하는 미션은 `[LAND]`나 `[RTL]` 한 항목뿐이고, 미션 안에서 모드 명령 항목 뒤에 setpoint 항목이 오지 않는다(미션 중간의 Offboard 재진입은 없다).
- 이 규칙은 `validate_mission_contract`(Phase 3 Fleet도 쓰는 층)에 둔다. 어기면 INVALID_MISSION이고 `detail`에 이유를 적는다.
- 1a 노드의 임시 제한(받는 type 셋, 마지막이 LAND)은 1b에서 모두 없어진다. 남는 것은 위 계약 규칙뿐이다.
- 반복 비행은 미션 둘로 보낸다(`[TAKEOFF, ..., LAND]` 다음 `[TAKEOFF, ..., LAND]`). goal 경계가 소비자에게 지상 DISARMED 확인 지점을 준다.
- `MissionItem.timeout`, `YawSetpoint`, `TakeoffItem.height_m`의 "첫 항목이 아닌 TAKEOFF는 1b에서 정한다" 괄호는 "TAKEOFF는 첫 항목에만 온다"로 닫는다.

근거
- 1b 완료에 "첫 항목이 아닌 TAKEOFF의 의미"를 고정해야 한다(interface.md 고정 시점 절). 임시 제한으로 두면 1b 완료에 고정할 의미가 남지 않는다. 계약으로 두면 고정되는 의미는 "무효"다.
- 나중에 허용하는 것은 전에 거부하던 입력을 받는 완화라 기존 생산자를 깨지 않는다. 그때는 "고정 뒤 새 요구"로 변경 절차를 밟는다.
- 허용하면 1a 고정 문장 넷(준비 단계 feedback의 `item_index` 0, NOT_READY와 PRECONDITION_FAILED의 "보내지 않았다", 지상 disarm 1회 조건 (2), `ready_timeout` 기준)이 깨진다(ros2-engineer 2절).

담당자 의견과의 대응
- ros2-engineer 2절 채택. px4-engineer 3절의 "거부 유지"와 같은 결론이고, px4-engineer의 "허용하게 되면 규칙"은 넘김 목록에 둔다.
- `docs/architecture.md` 인터페이스 계약 절의 "다음 setpoint 항목에서 Offboard 재진입 절차를 다시 밟는다"는 이 결정과 어긋나므로 고친다(1a 고정 계약 영향 (h)).

## 쟁점 7. 진입 방식과 공중 시작 미션

결정
- 준비 단계는 미션 단위로 한 번 돈다. 진입 방식은 첫 항목의 type에서 파생한다.

| 진입 방식 | 첫 항목 | 시작 조건(P1) | 단계 | 첫 항목 시작 시각 |
| --- | --- | --- | --- | --- |
| 지상 arm 진입 | TAKEOFF | 지상 DISARMED(1a 그대로) | P0-P6(1a 그대로) | arm 확인 |
| 공중 Offboard 진입 | GOTO, TRACK_ENTITY, LOITER | ARMED, 공중, `nav_state`와 `nav_state_user_intention`이 AUTO_LOITER, `failsafe` false | P0-P2, P3(진입 setpoint), P4, P5. P6 없음 | OFFBOARD 3회 연속 확인 |
| 모드 명령 진입 | LAND, RTL | ARMED이고 공중(1a `[LAND]` 그대로) | P0-P2 | 준비 끝 |

- 공중 Offboard 진입의 시작 조건이 맞지 않으면 PRECONDITION_FAILED다(발행 시작 전이라 아무것도 보내지 않았다). 이미 OFFBOARD인 기체, AUTO_RTL이나 AUTO_LAND 중인 기체, failsafe 중인 기체는 받지 않는다. 보내는 쪽이 먼저 기체를 Hold로 둔 뒤(예: 실행 중 goal의 취소) 다시 보낸다.
- P3의 진입 setpoint는 P3 tick에 읽은 위치와 heading이고 OFFBOARD 확인까지 바꾸지 않는다. OFFBOARD 3회 확인 tick에 첫 항목을 시작하고 그 항목의 setpoint로 바꾼다. 첫 항목이 LOITER이면 진입 setpoint가 "직전 setpoint"다.
- 감시: P3부터 비행 중 감시 표를 적용한다. 순위 1-5는 그대로다. 모드 행(6-8)은 OFFBOARD 3회 확인 전에는 `nav_state`가 AUTO_LOITER도 OFFBOARD도 아닐 때만 적용한다. 확인 뒤는 1a 그대로다. 순위 5의 failsafe 이력 구간은 P3부터 그 항목이 끝날 때까지다. 이 goal은 arm을 보내지 않았으므로 지상 disarm 1회 조건 (1)은 늘 거짓이다.
- P4, P5 실패(MODE_SWITCH_FAILED)는 정리의 공중 분기를 거친다(발행을 유지한 채 Hold, Hold 관측에 발행 중단). 늦게 처리된 Offboard 전환 뒤에 발행을 멈추면 1 s 뒤 offboard 손실 Land가 걸리기 때문이다.
- 먼 첫 GOTO의 setpoint 점프는 1b에서 점진 이동으로 다루지 않는다(1a TAKEOFF가 처음부터 목표점을 보내는 것과 같다). F3의 trace로 본다.

근거
- [소스] failsafe 중의 모드 변경은 사용자 넘겨받기다(`framework.cpp` 501-518행). AUTO_RTL, AUTO_LAND, failsafe 중인 기체를 받으면 Executor가 다른 주체의 결정을 덮는다(px4-engineer).
- [소스] Hold 중의 `trajectory_setpoint`는 비행제어 자신의 setpoint와 섞인다. 현재 위치를 보내면 끌림이 작다([실측] 1a에서 다음 목표를 보냈을 때 0.4 m 끌림).
- 모드 행을 확인 전에 아예 빼면(ros2-engineer 안) 진입 중에 failsafe Land나 외부 RTL로 바뀐 기체를 `offboard_signal_timeout` 뒤 정리의 Hold로 덮는다. px4-engineer 안은 이 경우를 그 tick에 FAILSAFE나 EXTERNAL_MODE_CHANGE로 끝낸다.

담당자 의견과의 대응
- px4-engineer 2절 채택(시작 조건, 진입 setpoint, 감시).
- ros2-engineer 1절의 진입 방식 셋과 core 구조(`EntryPlan`) 채택. 시작 조건 "공중 ARMED"와 "P3-P5에는 감시 표를 쓰지 않는다"는 px4-engineer 안으로 바꿨다(재질문 R-2). ros2-engineer의 "이미 OFFBOARD인 기체 거부" 질문은 위 시작 조건으로 답이 된다.

## 쟁점 8. GOTO와 TRACK_ENTITY

결정

| 항목 | GOTO | TRACK_ENTITY |
| --- | --- | --- |
| setpoint | `position`(world ENU)을 `FramePort`로 로컬 NED로. 매 tick 변환 | 유효한 최신 표적 위치 + `offset`(world ENU)을 로컬 NED로. 유효 표본이 없는 동안 직전 setpoint 유지 |
| 시작 대기 | 변환이 무효인 동안 직전 setpoint 유지(계약 그대로) | 같다. 표적 첫 유효 표본까지 |
| 완료 | 서로 다른 `vehicle_local_position` 표본(PX4 `timestamp`로 구분) 3개 연속, `xy_valid`와 `z_valid`, 3차원 거리 < `acceptance_radius_m` | 같은 조건. 그 tick의 표적 표본이 신선할 때만 센다 |
| timeout 기준 | 항목 시작 tick | 같다 |
| TARGET_LOST | - | 항목 시작부터 `target_timeout` 안에 유효 표본이 없거나, 얻은 뒤 `now - header.stamp > target_timeout` |
| 실패의 정리 | ITEM_TIMEOUT은 정리 | ITEM_TIMEOUT과 TARGET_LOST 모두 정리. reason 유지 |

- 같은 tick의 순서: 감시 표 -> TARGET_LOST -> ITEM_TIMEOUT -> 완료.
- 유효 표본(노드 변환에서 거른다): `target_id`가 토픽 토큰과 같고, `frame_id`가 `world`, 값이 유한, stamp가 0이 아니고 직전 유효 표본보다 크다. 거른 표본은 소실 판정을 앞당기지 않는다. 나이가 음수이면 0으로 본다.
- `target_timeout`은 노드 파라미터(ROS 시각, 기본 1.0 s). R3 기록을 보고 바꾼다.
- 표적 구독은 goal 접수 때 미션에 나오는 모든 `target_id`에 대해 만들고 goal이 끝나면 지운다. 구독 QoS는 계약 상태 행(BEST_EFFORT, VOLATILE). 변환은 노드(`node/conversion.cpp`)에서 `core::TargetSample`로 한다(PX4 메시지가 아니므로 px4 어댑터가 아니다).
- `MODE_KEEP` 기준 yaw: 직전 setpoint의 yaw. 직전 setpoint가 없으면 발행을 시작할 때 읽은 heading. 1a의 "첫 항목인 TAKEOFF는 기준 위치를 읽을 때의 heading"과 공중 Offboard 진입의 첫 항목이 이 규칙의 특수한 경우다.
- `distance_remaining_m`: 로컬 NED 위치와 setpoint 점의 3차원 거리. `distance_valid`는 위치(`xy_valid`, `z_valid`)와 변환이 모두 유효할 때만.
- TRACK_ENTITY의 지속 시간 필드는 더하지 않는다. `TrackEntityItem`과 `GoToItem`의 필드는 바꾸지 않는다.

근거
- 표본 하나로 완료하면 GNSS 잡음이 실린 위치에서 경계 근처 조기 완료가 난다. 3개 연속은 약 0.15 s로 비용이 작다. TAKEOFF는 1a 고정이라 표본 하나 그대로다.
- TARGET_LOST에서 발행만 멈추면 `COM_OF_LOSS_T` 뒤 offboard 손실 Land가 걸린다. 기체는 정상이므로 취소와 같은 Hold가 맞다.
- 직전 setpoint의 yaw는 결정적이라 단위 테스트와 리플레이 판정이 실행마다 같고, LOITER의 "직전 setpoint 유지"와 같은 뜻이다. 항목 시작 heading은 KEEP 항목이 이어질 때 추종 오차가 누적된다.

담당자 의견과의 대응
- ros2-engineer 4.1, 4.2, 4.4절 채택. px4-engineer와 test-engineer는 `MODE_KEEP`에 의견이 없었고 px4-engineer의 진입 setpoint(현재 heading)와 이 규칙이 맞는다.

## 쟁점 9. RTL 항목과 SITL 파라미터

결정
- RTL은 모드 명령 항목이다. `docs/interface.md`의 "LAND 항목" 절을 "모드 명령 항목(LAND, RTL)" 절로 넓히고 LAND의 규칙을 그대로 쓴다.

| 항목 | 명령 | 확인할 모드 | 확인 전 | 확인 뒤 이탈 | 완료 |
| --- | --- | --- | --- | --- | --- |
| LAND | NAV_LAND(21) | AUTO_LAND | 이탈 판정 없음 | EXTERNAL_MODE_CHANGE, failsafe이면 FAILSAFE | 지상 DISARMED 3회 |
| RTL | NAV_RETURN_TO_LAUNCH(20) | AUTO_RTL | 이탈 판정 없음 | 같다 | 지상 DISARMED 3회. `nav_state`는 보지 않는다 |

- 실패 폴백: RTL 거부 ack 또는 `mode_confirm_timeout` 안에 AUTO_RTL 미확인이면 취소의 Hold 실패 뒤와 같은 Land 경로로 가고 ABORTED, REASON_MODE_SWITCH_FAILED다. `detail`에 "RTL not confirmed, Land sent". 새 reason은 더하지 않는다. 모든 실패 폴백은 Land로 모이고 RTL은 명령 항목으로만 쓴다.
- `[RTL]` 미션의 시작 조건은 `[LAND]`와 같다(ARMED이고 공중).
- 목적지는 PX4 home이다. 계약 문장: "RTL은 그 기체가 마지막으로 arm하거나 이륙한 지점으로 돌아가 착륙한다. 공중 시작 미션의 RTL 목적지는 그 미션이 아니라 앞선 비행의 지점이다." `RtlItem`이나 목적지 필드는 두지 않는다.
- 계약 SITL 파라미터 표에 더하는 것(`config/px4/sitl_params.env`).

| 파라미터 | 값 | 이유 |
| --- | --- | --- |
| `RTL_TYPE` | 0 | home 직선 복귀. 2와 4는 MAVLink 미션 경로를 따른다 |
| `RTL_CONE_ANG` | 0 | 귀환 고도가 `max(현재 고도, home 고도 + RTL_RETURN_ALT)` 하나로 정해진다 |
| `RTL_RETURN_ALT` | 10 m(architect 안. 재질문 P-3) | 1b 시험 미션 고도 5 m보다 높은 한 값. x500 기본 30 m는 시험 시간을 늘린다(U9) |
| `RTL_LAND_DELAY` | 0 | 멀티콥터는 home 위에서 바로 착륙한다. -1이면 착륙하지 않아 완료 조건이 오지 않는다 |
| `COM_DISARM_LAND` | 2 s | 기본값과 같지만 RTL과 LAND 완료 조건의 근거라 명시한다 |
| `COM_LOW_BAT_ACT` | 2(Land) | U8. 실패 폴백은 Land라는 원칙과 맞춘다. SITL 배터리는 50%에서 멈춰 닿지 않는다 |

- 1b 시험 미션의 순항 고도는 5 m다(1a 시나리오 A와 같다. 표적 궤적의 z도 5 m). architect 안이고 재질문 P-3에서 px4-engineer가 확인한다.
- 기체별 `px4_params`로 `RTL_RETURN_ALT`를 덮어도 계약 안으로 두는 예외(px4-engineer 7절)는 1b에 넣지 않는다. 고도 층 분리가 필요한 Phase 3에서 "고정 뒤 새 요구"로 다룬다(넘김 목록).

근거
- [소스] 멀티콥터에서 `RTL_LAND_DELAY` 0이면 RTL은 착륙까지 AUTO_RTL이고(`rtl_direct.cpp` 176-183행, 365-377행) 착지 뒤 `nav_state`는 disarm 전 사용자 의도 모드로 돌아간다(`UserModeIntention.cpp` 77-84행). 그래서 완료에서 `nav_state`를 보지 않는다(px4-engineer).
- RTL을 실패 폴백으로 쓰면 다대에서 같은 귀환 고도의 경로가 교차한다(`COM_OBL_RC_ACT=4`의 이유와 같다).

담당자 의견과의 대응
- px4-engineer 1절 채택. ros2-engineer 8절 px4 질문 1, 2는 px4-engineer 1절로 답이 된다.
- test-engineer 1.3절의 "AUTO_LAND 또는 AUTO_RTL을 본 다음 DISARMED"는 RTL에서 AUTO_LAND를 거치지 않는다는 점만 맞춘다.

## 쟁점 10. 공중에서 끝나는 미션(U3)

결정
- 마지막 항목이 setpoint 항목인 미션은 그 항목의 완료 tick에 `items_completed`를 N으로 올리고 종료 단계에 들어간다. 종료 단계는 취소의 공중 분기와 같다: 발행을 유지한 채 Hold를 재전송하고, Hold를 처음 관측한 tick에 발행을 멈추며, Hold 3회 연속 확인이면 SUCCEEDED.
- 종료 단계는 공중 분기와 Hold 실패 뒤 Land 경로만 쓴다. 지상 분기(지상 setpoint와 disarm 확인)는 쓰지 않는다. 그래서 REASON_DISARM_FAILED의 고정 의미("취소 처리 중")를 건드리지 않는다.

| 종료 단계의 관측 | 결과 |
| --- | --- |
| Hold 3회 연속 확인 | SUCCEEDED |
| 지상 DISARMED(disarm 분류의 고정 규칙) | SUCCEEDED, `detail`에 "ended on ground" |
| 공중 DISARMED | ABORTED, FAILSAFE |
| 상태 끊김 | ABORTED, LINK_LOST |
| Hold 거부 ack 또는 `hold_confirm_timeout` | Land 경로 뒤 ABORTED, MODE_SWITCH_FAILED. `items_completed`는 N |
| 정리의 상한(`hold_confirm_timeout + 3 x mode_confirm_timeout`) | 공중이면 NAV_LAND 1회, 지상이면 disarm 1회 뒤 ABORTED, MODE_SWITCH_FAILED |

- 종료 단계 중의 cancel은 결과를 바꾸지 않는다. feedback의 `phase`는 `PHASE_EXECUTING`, `item_index`는 마지막 항목이다. result의 `last_item_index`는 N-1이다.
- 지상 `landed` true이고 ARMED인 채 종료 단계에 들어가는 경우의 동작은 재질문 P-2, R-3의 답으로 정한다.
- Hold 지점은 마지막 setpoint가 아니라 Hold로 바뀐 순간의 위치에 제동 거리를 더한 점이다([소스] `loiter.cpp` 111-112행). 계약 문장에 적는다. 마지막 항목이 표적 추종이면 표적 쪽으로 앞선다.
- 마지막 setpoint 항목의 높이 하한은 미션 검증에 두지 않는다. world ENU z는 지면 높이가 아니고 Executor는 지형을 모른다. 낮은 Hold는 1a "지면 바로 위에서 Hold로 끝난" 행의 상태와 같다.
- 끝없는 Hold: SITL에서는 배터리와 failsafe가 닿지 않아 영원히 머문다. 끝점이 겹치지 않게 하는 것은 Phase 3 Fleet 계획의 책임이다(넘김 목록).

근거
- [소스] offboard 손실 failsafe는 사용자 의도 모드가 offboard 신호를 요구할 때만 걸리고 Hold는 요구하지 않는다(`failsafe.cpp` 664-666행). Hold 확인 뒤 발행을 멈춰도 아무 일이 없다. [실측] 1a 시나리오 D와 60 s 관찰이 같은 상태다.
- Offboard 유지는 기체 상태를 Executor 프로세스 생존에 묶는다. 자동 RTL이나 LAND는 운용 정책을 Executor가 정하는 것이고 미션에 RTL이나 LAND를 넣으면 같은 일이 된다.
- Hold 실패를 SUCCEEDED로 두지 않는 것은 끝난 뒤 기체 상태(내려오는 중)가 SUCCEEDED의 상태(Hold)와 달라 소비자의 다음 동작이 갈리기 때문이다.

담당자 의견과의 대응
- px4-engineer 4절, ros2-engineer 3절 채택(둘이 같다). ros2-engineer의 "ended on ground" SUCCEEDED는 취소 공중 분기의 "지상 DISARMED 표본이면 그 tick에 끝낸다"와 같은 생각이라 채택.
- px4-engineer의 "마지막 setpoint 높이 하한"은 두지 않는다(위 근거).
- Hold 확인 전 발행 유지는 상태기 단위 테스트가 묶는다(px4-engineer 위험).

## 쟁점 11. 지상 취소의 disarm 확인과 /clock 지연 실측

결정
- 1b 첫 실측은 W다: 명령에 실은 timestamp(노드의 ROS 시각)와 같은 명령의 `vehicle_command_ack.timestamp`(Commander가 처리한 PX4 시각)의 차를 `run_sitl.sh` 한 회의 ULog에서 모든 명령(arm, disarm, DO_SET_MODE, NAV_LAND)에 대해 모은다. 새 시나리오를 만들지 않는다. 같은 ULog에서 disarm 전후 `vehicle_status` publish 간격을 함께 본다.
- 판단 기준(px4-engineer): W의 최댓값이 100 ms 미만이고 처리 전 표본이 확인 계수에 들어간 기록이 없으면 1a 규칙(tick 조건, timestamp 조건, 3회 연속)을 유지한다. 아니면 "받아들여진 disarm ack의 PX4 `timestamp` 이상인 DISARMED 표본만 센다. ack가 없으면 1a 규칙"으로 바꾼다. "ack 뒤에 받은 표본만 센다"는 쓰지 않는다(토픽 간 수신 순서가 보장되지 않는다).
- L(gz `/clock`과 ROS `/clock`의 도착 차)은 W가 기준을 넘어 원인을 나눠야 할 때만 잰다. test-engineer의 별도 `clockskew` 측정 항목은 두지 않는다. 대신 sitl gate가 이미 보는 `now - vehicle_status.timestamp`의 분위수를 `verdict.json`에 `recorded_only`로 남긴다. 표적 어댑터가 생긴 뒤 `TargetState` 나이(R3)와 `/clock` 간격도 같은 방식으로 남긴다.

근거
- 위험은 "disarm 처리 전에 publish된 DISARMED 표본이 timestamp 조건을 통과하는 것"이고 그 창은 L이 아니라 W다. [소스] Commander는 한 주기에 ack를 먼저, `vehicle_status`를 나중에 publish한다(`Commander.cpp` 1887-1899행, 2674-2680행, 1930-1945행).
- gate에 얹은 기록은 별도 실행이 없어 비용이 0이다(U6의 산출물 최소 원칙).

담당자 의견과의 대응
- px4-engineer 5절 채택. test-engineer 5.2절의 (a)는 gate 기록으로, (b)와 (c)는 어댑터 뒤 gate 기록으로 채택하고 `measure/`의 새 항목은 받지 않았다. progress의 "`/clock` 전달 지연의 크기"는 W로 대신한다.

## 쟁점 12. snapshot 헤더와 core 구조 변경

결정
- snapshot 헤더(px4-engineer 필수 승인)에 더하는 것을 한 PR에 묶는다: `PositionSample`의 `timestamp_us`, `xy_valid`, `NavMode::kRtl`, `AckCommand::kNavRtl`, `CommandKind::kNavRtl`, `FramePort`, `TargetSample`과 표적 맵. W 결과로 ack timestamp 기준을 쓰게 되면 `AckSample`의 PX4 timestamp를 같은 PR에 넣는다. 그래서 헤더 변경 PR은 W 결과 뒤에 연다.
- core 구조(ros2-engineer): `EntryPlan`(지상 arm, 공중 Offboard, 모드 명령), setpoint 항목의 type별 처리(setpoint, 완료, TARGET_LOST만 내고 감시 표, ITEM_TIMEOUT, 정리 진입은 공통), 모드 명령 항목 처리의 일반화(보낼 명령, 확인할 모드), 공중 종료 단계. 전이 표는 px4-engineer 필수 승인이다.
- `idsim_mission_core`는 계속 `idsim_common`과 px4_msgs를 모른다(`check_core_purity.cmake` 그대로).

담당자 의견과의 대응
- ros2-engineer 1절과 8절 px4 질문 7, px4-engineer 5절의 `AckSample` 변경을 한 번에 묶었다. 승인 목록은 재질문 P-4.

## 쟁점 13. 상태기 단위 테스트의 "전이 전부를 덮음"

결정
- "전부"의 정의는 px4-engineer가 승인한 전이 칸 목록이다. 칸은 (상태 또는 phase, 사건) -> (다음 상태, reason)이고 세 부류(덮임, 불가능과 이유, 미덮임)다. 같은 tick에 조건이 겹치는 칸은 "겹침 칸"으로 따로 열거한다. 미덮임이 0이면 완료 기준을 만족한다.
- 측정은 선언이 아니라 관측이다. 테스트가 실제로 지나간 변을 모아 칸 목록과 집합 비교하고, 미덮임이나 목록에 없는 변이 있으면 실패한다. 방법은 test-engineer 안(전이를 한 함수로 모으고 harness가 `TransitionObserver`를 주입)을 기본으로 하고 재질문 R-1의 답으로 확정한다.
- 줄과 분기 커버리지는 게이트로 쓰지 않는다. 변이 확인은 일회성 감사로 한다.

담당자 의견과의 대응
- test-engineer 4절 채택. 리팩터링 규모는 ros2-engineer에게 묻는다(재질문 R-1).

## 쟁점 14. YAML 로더와 idsim_common 공개

결정
- YAML 로더: `idsim_mission` 안의 Python 모듈 `idsim_mission.mission_yaml`(`ament_cmake_python`)과 CLI `send_mission <file> --vehicle <vehicle_id>`. 소유 ros2-engineer. 로더는 구조 검사(모르는 key 거부, 필수 key, 타입), 단위 변환(`timeout_s` -> `Duration`, ns 반올림, 음수와 비유한 거부), 기본값 채움, `mission_id`(YAML 값 또는 파일 이름, 정규식 검사)만 한다. 계약 검증의 정본은 Executor의 goal 검증이고 로더에 다시 구현하지 않는다. yaw는 `yaw_rad`만 받는다.
- 1b 시험 미션 YAML은 `tests/sitl/missions/`에 둔다(test-engineer). 시간 합산 단정은 로더가 만든 `Mission`에서 한다(기본값이 채워진 뒤).
- `idsim_common`: NAV_TAKEOFF 빌더는 더하지 않는다. `goto_setpoint`는 Restricted 그대로다(재질문 P-4에 확인 한 줄). 공개 /fmu/in은 셋 그대로다. 더하는 것은 `geo.hpp`(쟁점 4), `TargetId`, `target_state_topic`, 상태 QoS 함수(`state_pub_qos`, `state_sub_qos`)다.

담당자 의견과의 대응
- ros2-engineer 5, 6절 채택. Phase 3 Fleet(C++)의 배분 전 검증은 Python 로더가 아니라 core의 `validate_mission_contract`를 쓴다(넘김 목록).

## 쟁점 15. 시나리오, 순서, CI 시간

결정
- 한 스택에서 이 순서로 돈다: B, C, A, D, F1, F2, F3, T.

| id | 미션 | 보는 것 | 끝 상태 |
| --- | --- | --- | --- |
| B | 1a 무효 사례에 1b 사례를 더한다: 첫 항목이 아닌 TAKEOFF, 마지막이 아닌 LAND와 RTL, `[RTL, ...]` 여러 항목, TRACK_ENTITY의 0 `offset`, 형식이 틀린 `target_id`, 기본값 TRACK_ENTITY 서브메시지 | INVALID_MISSION, 비행 없음 | 지상 |
| C, A, D, T | 1a 그대로 | 1a 그대로 | 1a 그대로 |
| F1 | `[TAKEOFF 5 m, GOTO x 3, LAND]` | 웨이포인트 도달, 항목 순서, 착륙 후 disarm | 지상 DISARMED |
| F2 | `[TAKEOFF, GOTO, TRACK_ENTITY]` | 표적 접근, 공중 종료의 SUCCEEDED와 Hold(`HOLD_AIRBORNE`) | 공중 Hold |
| F3 | `[GOTO, RTL]`(F2가 남긴 Hold에서 공중 시작) | 공중 시작, RTL 완료(착륙 위치, disarm) | 지상 DISARMED |

- 형식은 맞지만 없는 `target_id`는 INVALID_MISSION이 아니다. 계약상 받아들여 이륙하고 TARGET_LOST로 끝난다. 그래서 B에 넣지 않는다.
- 비행 시나리오가 실패하면 뒤의 비행 시나리오는 실행하지 않고 `UPSTREAM_FAILED`(실패로 센다)로 기록한다. 정리용 `[LAND]`는 한 번 시도하고 판정에 넣지 않는다. F3만 따로 돌릴 수 없다는 것을 `tests/sitl/README.md`에 적는다.
- TARGET_LOST와 표적 서비스 정지의 통합 시나리오는 1b에 두지 않는다. 단위 테스트(가짜 `FramePort`와 표적 맵)로 덮고 계약 문장의 근거는 [단위 테스트]로 적는다.
- 시간 규칙: 시나리오마다 항목 `timeout` 합 + 마진이 비행당 상한(ROS 시각 3분)을 넘지 않음을 단위 테스트가 단정한다. RTF가 1 미만이면 `SITL_PYTEST_TIMEOUT`(벽시계)은 올려도 되고 판정의 ROS 시각 한도는 올리지 않는다. 15분 목표를 넘으면 순회 점 수와 Hold 유지 시간을 먼저 줄이고, 그래도 넘으면 측정값과 함께 사용자에게 올린다(U11). 판정 기준을 느슨하게 해서 줄이지 않는다.

근거
- 콜드 up이 비용의 대부분이다([실측] PR #36: 스택 올리기부터 정리까지 약 2분 13초). 지상 거부 사례는 비행 전에 둔다(비행 실패가 사전조건을 깨지 않게). F2의 끝(공중)과 F3의 시작(공중)을 맞물려 이착륙 한 번을 줄인다. T는 지상 시나리오라 맨 뒤다.
- B에 더하는 것은 G를 따로 두는 것보다 시나리오 수가 적고, 1a의 "B는 무효 미션"과 같은 뜻이다.

담당자 의견과의 대응
- test-engineer 2절 채택. G는 B에 합쳤고 G의 "알 수 없는 `target_id`" 사례는 계약("미션에 적힌 `target_id`가 실제로 있는지는 검사하지 않는다")과 어긋나 뺐다(재질문 T-2).

## 쟁점 16. 다대 원점 판정

결정
- 생성기(`tools/gen_compose.py`)가 기체별 기대 GPS `vehicles[].expect_gps = {lat, lon, alt}`를 `world.origin`과 스폰 pose로 계산해 `stack.json`에 싣는다. `check_px4`는 지금의 `--expect-origin`을 기체마다 그 값으로 부르기만 한다. `--expect-pose-enu`는 두지 않는다.
- 생성기의 식은 스모크 기대값이고 운용 변환이 아니다. "world ENU <-> 로컬 NED 변환은 `idsim_common` 한 곳"은 운용 노드의 규칙이고 이 식에 적용하지 않는다. 생성기 단위 테스트(3대-k0 fixture)가 식을 고정한다.

근거: 비교기는 그대로이고 인자 출처만 바뀐다. 스폰 오프셋 수 m에서 근사 차이는 허용 0.5 m보다 훨씬 작다([추정]).

담당자 의견과의 대응: test-engineer 3절 채택.

## 쟁점 17. Actor 월드의 viz 확인

결정: sim-engineer 5절의 수동 절차(M4)를 1회 하고 결과를 PR 본문에 남긴다. ogre2와 ogre 둘 다, GUI 재접속 1회, 120 s 동안 서버 생존과 `/clock` 증가와 `vehicle_status` 수신. CI에 넣지 않는다. Actor 위치와 `TargetState`의 차이(M2)는 같은 확인에서 육안으로 본다. `gui.config` 고정 목록 밖의 plugin 추가 금지를 운영 문서에 적는다.

## 재질문

메인 세션이 담당자에게 보낸다. 각 질문은 혼자 읽어도 되게 썼다. 답은 PR 본문에 남기고 이 문서의 해당 쟁점을 고친다.

px4-engineer
- P-1(쟁점 4, 5). 1b의 원점 이동 변환은 world ENU 점을 gz `SphericalCoordinates` 식으로 WGS84로 바꾼 뒤 PX4 `MapProjection` 식(기준 `vehicle_local_position.ref_lat/ref_lon/ref_alt`)으로 로컬 NED로 바꾸는 사슬로 정했다. 두 가지를 PX4 v1.17.0 원문으로 확인해 달라. (가) `MapProjection`이 구면 반지름 상수(`CONSTANTS_RADIUS_OF_EARTH`)를 쓰는가. 그렇다면 위도 37.6도에서 WGS84 곡률 반지름과의 차가 약 0.2%(원점에서 100 m에 약 20 cm)라는 architect 계산이 맞는가. 의견서의 "수백 m에서 cm 아래"와 다르다. (나) 이 사슬에서 기체가 물리적으로 도착하는 점의 오차에 첫 GNSS fix의 잡음(EKF 원점과 실제 스폰 지점의 차)이 들어가는가. architect 판단은 "수평은 기체 추정과 목표가 같은 `ref_*`를 쓰고 추정이 GNSS에 묶여 있어 상쇄되고, 수직은 EKF 높이 기준이 기압계이면 `ref_alt`의 초기 잡음이 남는다"이다. v1.17.0 SITL x500의 `EKF2_HGT_REF` 값과, 그 설정에서 로컬 z와 `ref_alt`의 관계를 함께 알려 달라. 답에 따라 판정 임계값 b의 출처(R1 또는 R2)가 정해진다.
- P-2(쟁점 10). 공중에서 끝나는 미션은 마지막 setpoint 항목이 끝나면 발행을 유지한 채 Hold를 보내고 Hold 3회 확인으로 SUCCEEDED다. 마지막 항목의 목표가 지면 높이인 경우처럼 이 단계에 들어갈 때 `landed`가 true이고 ARMED이면 PX4 v1.17.0은 (가) Hold(AUTO_LOITER) 요청을 받아들이는가, (나) 받아들인 뒤 이륙 이력이 있으므로 `COM_DISARM_LAND`(2 s) 뒤 스스로 disarm하는가. 소스 근거와 [추정] 여부를 구분해 달라.
- P-3(쟁점 9). 1b 시험 미션의 순항 고도를 5 m(1a 시나리오 A와 같다)로, `RTL_RETURN_ALT`를 10 m로 두는 안이다. `RTL_DESCEND_ALT`는 x500 기본 10 m를 계약에 넣지 않고 둔다. (가) 이 조합에서 귀환 고도가 10 m로 정해지고 `RTL_DESCEND_ALT`와의 관계로 다른 값이 되지 않는가. (나) F3(`[GOTO, RTL]`, home까지 수평 10-20 m)의 RTL 항목 `timeout` 권장값. 다른 값을 권하면 이유와 함께.
- P-4(쟁점 12, 14). snapshot 헤더에 한 PR로 더할 목록의 승인 여부: `PositionSample.timestamp_us`, `PositionSample.xy_valid`, `NavMode::kRtl`, `AckCommand::kNavRtl`, `CommandKind::kNavRtl`, `FramePort`, `TargetSample`과 표적 맵, (W가 기준을 넘으면) `AckSample`의 PX4 timestamp. 빠졌거나 이름이 PX4 쪽 의미와 어긋나는 것이 있으면 알려 달라. 덧붙여 `goto_setpoint`가 Offboard에서 쓰이지 않으므로 `idsim_common`에서 Restricted로 두는 데 동의하는가(예 또는 아니오와 근거 한 줄).
- P-5(쟁점 1). 표적 궤적의 구간 속도 상한을 생성기가 거부한다. x500의 Offboard position 추종이 따라갈 수 있는 상한으로 몇 m/s를 권하는가(architect 임시 안 10 m/s). 1b 시나리오의 표적 속도는 1-2 m/s로 잡는다.

ros2-engineer
- R-1(쟁점 13). test-engineer는 "전이 전부를 덮음"을 선언이 아니라 관측으로 보이자고 한다: core의 전이를 한 함수(`transition(from, event, to)`)로 모으고 `runner_harness.hpp`가 `TransitionObserver` port를 주입해, 모든 테스트가 끝난 뒤 지나간 변의 집합을 px4-engineer가 승인한 칸 목록과 비교한다. 지금 `mission_runner.cpp`(1231행)의 전이를 이렇게 모을 수 있는가, 리팩터링 규모는 어느 정도인가. 어렵다면 선언(칸 목록과 테스트 이름 대조)이 아닌 다른 관측 방법을 제안해 달라.
- R-2(쟁점 7). 공중 Offboard 진입(P3-P5)의 감시를 의견서 안("감시 표를 쓰지 않고 끊김, 공중 DISARMED, 식별만 본다") 대신 px4-engineer 안으로 정했다: P3부터 감시 표 순위 1-5를 그대로 적용하고, 모드 행 6-8은 OFFBOARD 3회 확인 전에는 `nav_state`가 AUTO_LOITER도 OFFBOARD도 아닐 때만 적용한다. 이유는 의견서 안에서는 진입 중에 failsafe Land나 외부 RTL로 바뀐 기체를 `offboard_signal_timeout` 뒤 정리의 Hold가 덮기 때문이다. core 구조에서 이 규칙을 넣기 어려운 점이 있는가. 이 경로에서 지상 DISARMED(순위 5)를 EXTERNAL_DISARM이나 FAILSAFE로 내는 데 이견이 있는가.
- R-3(쟁점 10). 공중 종료 단계는 공중 분기와 Hold 실패 뒤 Land 경로만 쓰고 지상 분기를 쓰지 않는다. 종료 단계에 들어가는 tick에 `landed`가 true이고 ARMED인 경우 core가 할 일을 정해 달라. architect 안은 "공중 분기 그대로 Hold를 보내고, Hold 3회면 SUCCEEDED, 지상 DISARMED면 SUCCEEDED('ended on ground'), 상한이면 disarm 1회 뒤 ABORTED, MODE_SWITCH_FAILED"다. px4-engineer의 P-2 답(지상 ARMED에서 Hold 수락 여부)을 함께 보고 답해 달라.

sim-engineer
- S-1(쟁점 5). 통합 테스트의 도달 판정은 SITL 전용 정답 pose(기체 `x500_N`의 world ENU pose)를 ROS 토픽 `/sim/<vehicle_id>/pose`로 받아 world 목표와 비교한다. 운용 노드는 이 토픽을 구독하지 않는다. (가) 가장 싼 공급 경로와 타입은 무엇인가(예: `/world/<월드>/pose/info`를 bridge해 작은 노드가 이름으로 걸러 다시 내기, 또는 다른 경로). Actor가 있는 월드에서 그 경로가 `dynamic_pose` 같은 서버 위험을 갖지 않는가. bridge CPU 비용은 어느 정도로 보는가. (나) 그 pose의 기준점이 x500 model 원점(base_link)이고 PX4 로컬 위치가 가리키는 점과 같은가.
- S-2(쟁점 4, 5). gz-sim 8.15.0의 NavSat 센서가 위경도를 만들 때 `SphericalCoordinates`의 WGS84 변환(local ENU -> ECEF -> geodetic)을 쓰는지, 고도가 `world.origin.alt + z`인지와 그 고도가 타원체 고인지를 소스로 확인해 달라. 그리고 x500 모델 SDF의 NavSat 잡음 설정(백색 잡음인지, bias나 random walk가 있는지, 크기)을 알려 달라. EKF 추정과 실제의 차(판정 임계값 b)의 기대 크기가 여기서 나온다.
- S-3(쟁점 3). 표적 어댑터를 `docs/architecture.md` 기술 스택의 "어댑터 Python"에 따라 rclpy 노드(궤적 평가는 순수 함수)로 정했다. 의견서의 C++ 컴포넌트 안은 언어 선택의 변경이라 이번에 정하지 않는다. Python으로 할 때 막히는 점(시계, 주기, 단위 테스트, 이미지)이 있는가. 그리고 별도 서비스 `targets`의 healthcheck를 "모든 표적이 `/clock` 시작 뒤 한 번 이상 발행됨"으로 할 때 Python 노드에서 가장 싼 확인 방법을 제안해 달라.

test-engineer
- T-1(쟁점 5). 정답 판정의 반경 `acceptance_radius_m + b`에서 b의 출처를 의견서의 R1(EKF 원점 오차)에서 R2(Executor가 도달로 넘긴 순간의 정답 pose와 목표의 거리)로 바꿨다. 근거는 사슬 변환에서 첫 fix 잡음이 수평으로 상쇄된다는 architect 판단이다(px4-engineer P-1로 확인 중). R1은 gate의 `recorded_only` 기록으로만 남긴다. 이 정의로 판정 상수와 F1 trace 항목을 구성할 때 문제가 있는가. P-1 답이 "수직에 `ref_alt` 초기 잡음이 남는다"이면 수직 성분 처리를 어떻게 할지 함께 제안해 달라.
- T-2(쟁점 15). 의견서의 G 사례 중 "알 수 없는 `target_id`"는 계약("미션에 적힌 `target_id`가 실제로 있는지는 검사하지 않고 항목 시작 뒤 TARGET_LOST로 드러난다")상 INVALID_MISSION이 아니라 이륙까지 간다. 그래서 G를 B에 합치면서 그 사례를 뺐다. B의 1b 사례 목록(첫 항목이 아닌 TAKEOFF, 마지막이 아닌 LAND와 RTL, `[RTL, ...]` 여러 항목, 0 `offset`, 형식이 틀린 `target_id`, 기본값 TRACK_ENTITY 서브메시지)에 더하거나 뺄 것이 있는가.
- T-3(쟁점 15, U11). 사용자가 CI `sitl` 시간 예산을 정하려면 숫자가 필요하다. 1a의 `repeat_summary.tsv`와 `steps.tsv`(시나리오별 벽시계)에서 새 측정 없이 F1, F2, F3의 벽시계를 추정해 달라. 조건: 순항 고도 5 m, F1은 한 변 10 m 정사각형 GOTO 셋, F2의 표적 속도 1-2 m/s, F3은 home까지 수평 10-20 m, `RTL_RETURN_ALT` 10 m. 이미지 pull 약 3분 20초를 포함한 job 전체 추정과 15분 대비 여유를 적어 달라.

devops-engineer(이번 토론 밖. 구현 전 확인)
- D-1(쟁점 2). `world.file`이 "템플릿 경로"로 바뀌고 생성기가 월드 SDF를 실행 디렉터리에 쓴다. key 이름을 유지할지 바꿀지, `fleet.yaml`의 `schema` 번호를 올릴지, 생성된 월드 SDF와 `targets` 서비스를 생성기 golden(4종)에 어떻게 넣을지 정해 달라. `targets`가 비었을 때 서비스를 만들지 않는 것과 `startup.node_stages`에서의 위치도 함께.
- D-2(쟁점 16). `stack.json`의 `vehicles[].expect_gps` 추가와 fixture 갱신, `world.origin` 필수화가 스모크(embedded 포함)에 주는 영향을 확인해 달라.

## 1a 고정 계약 영향

모두 `docs/interface.md`의 1a 고정 절이고 `idsim_interfaces`의 필드와 상수는 바뀌지 않는다(golden과 type hash 무변경. 정의 주석만 바뀐다). `docs/architecture.md`의 변경 절차("고정 뒤에는 새 요구가 있어야 한다. 변경 절차를 따른다")가 적용된다. 새 요구는 1b 범위(U3의 공중 종료, 로드맵 1b의 RTL과 공중 시작, U7, U8)다. 반영은 B11(계약 고정 문서)에서 한 PR로 하고, PR 본문에 아래 목록과 근거를 적으며 architect 승인과 reviewer 검토를 받는다. 1a에서 받던 미션(첫 항목 TAKEOFF와 마지막 LAND, `[LAND]`)에 대한 동작은 어느 항목에서도 바뀌지 않는다.

| 번호 | 대상 문장 | 바꾸는 이유 | 성격 |
| --- | --- | --- | --- |
| (a) | "끝난 뒤 기체 상태"의 SUCCEEDED 행 "지상 DISARMED(마지막 항목 LAND의 완료 조건)" | 공중 종료(쟁점 10)와 RTL(쟁점 9). 마지막 항목별로 행을 나눈다: LAND와 RTL은 지상 DISARMED, setpoint 항목은 Hold(드물게 지상 DISARMED) | 행 분할. LAND로 끝나는 미션의 보장은 같다 |
| (b) | "GoalStatus와 reason" 표의 "나오는 곳" 열(MODE_SWITCH_FAILED, FAILSAFE, EXTERNAL_MODE_CHANGE, LINK_LOST, ITEM_TIMEOUT)과 PRECONDITION_FAILED, EXTERNAL_DISARM 의미 칸의 괄호("TAKEOFF는 지상 DISARMED, `[LAND]`는 공중 ARMED", "setpoint 항목 실행 중이거나 그 앞의 arm 확인 중") | RTL, 공중 Offboard 진입, 공중 종료가 같은 reason을 낸다(쟁점 7, 9, 10) | 적용 경로의 열거 확장. reason의 핵심 의미는 그대로 |
| (c) | 용어 "정리"와 "정리" 절 첫 문장의 원인 목록(취소, setpoint 항목의 ITEM_TIMEOUT, 준비 단계의 실패) | TARGET_LOST가 같은 정리를 거친다(쟁점 8) | 원인 추가 |
| (d) | "비행 중 감시" 첫 문장의 시작 시점과 "(TAKEOFF, LOITER)", 순위 5의 failsafe 이력 구간 | 공중 Offboard 진입은 P3부터, setpoint 항목 전체로(쟁점 7, 8) | 범위 확장 |
| (e) | "발행 규칙"의 "Offboard로 들어가는 중(준비 단계의 발행 시작부터 arm 확인까지)" | 공중 Offboard 진입은 Hold 중에 OFFBOARD 확인까지 현재 위치 setpoint를 발행한다(쟁점 7) | 예외 구간 추가 |
| (f) | "준비 단계" 절 첫 문장("첫 항목이 TAKEOFF인 미션은")과 `[LAND]` 문단 | 공중 Offboard 진입 문단 추가, `[LAND]` 문단을 `[LAND]`와 `[RTL]`로(쟁점 7, 9) | 문단 추가 |
| (g) | "LAND 항목" 절, feedback 표의 `PHASE_WAITING_MODE`(1a는 LAND) | 모드 명령 항목(LAND, RTL)으로 넓힌다(쟁점 9) | 구조 변경. LAND 규칙은 그대로 |
| (h) | 미션 정의 절의 "1a 노드의 임시 제한(계약 문장이 아니다. 1b에서 푼다)"과 `MissionItem.timeout`, `YawSetpoint.mode`, `TakeoffItem.height_m`의 "1b에서 정한다" 괄호. `docs/architecture.md` 인터페이스 계약 절의 "다음 setpoint 항목에서 Offboard 재진입 절차를 다시 밟는다" | 순서 규칙이 계약이 된다(쟁점 6, U7). "1b에서 푼다"는 받는 type 셋과 마지막 LAND 제한만 풀리고 순서 규칙은 계약으로 남는다 | 임시 제한의 계약화와 1b 몫 닫기 |
| (i) | "SITL 파라미터"의 계약 표 | `RTL_TYPE`, `RTL_CONE_ANG`, `RTL_RETURN_ALT`, `RTL_LAND_DELAY`, `COM_DISARM_LAND`, `COM_LOW_BAT_ACT` 행 추가(쟁점 9, U8, U9) | 행 추가 |
| (j) | 공통 규칙 "이름과 식별자"의 "Python은 `tests/support`가 한다" | Python 생산자(표적 어댑터)가 생긴다(쟁점 3) | 위치 추가 |
| (k) | "시간 기준"의 "1a는 `/clock`만 브리지한다", 그리고 W 결과에 따라 "예외 하나: 취소의 지상 분기"와 "취소" 절의 DISARMED 확인 문장 | bridge 내용(쟁점 2, 5)과 disarm 확인 기준(쟁점 11) | 사실 갱신. 기준 변경은 W가 기준을 넘을 때만 |

## 사용자 결정 대기

- U10. 범위 문구. 해법 (가)를 택하면 `docs/architecture.md` "목표와 범위"의 "움직이는 표적은 Gazebo 안의 임의 이동 엔티티로 두고, 그 위치를 미션 노드가 '추적 대상 좌표'로 구독하는 수준까지만 다룬다"와 "표적 어댑터 노드가 ros_gz_bridge로 받은 Gazebo pose를 이 계약으로 변환"이 사실과 어긋난다.
  - 선택 1: 표적을 "`config/fleet.yaml`에 적은 스크립트 궤적을 시뮬레이션 시간에 맞춰 따르는 점 표적"으로 좁힌다. Gazebo Actor는 같은 궤적을 보여 주는 확인용이다. Gazebo 상태에 따라 움직이는 표적(물리, 회피 기동)은 확장 단계로 미룬다.
  - 선택 2: "Gazebo 안의 이동 엔티티의 위치"를 유지한다. 1b에서 Gazebo 서버 쪽 C++ system을 만들고 sim-base에 빌드 단계를 더한다(이미지 크기와 CI 빌드 시간이 는다). 쟁점 1을 (다)로 고쳐 쓴다.
  - 선택 3: 선택 1로 가고, 범위 문구에 "표적 생산자는 `TargetState` 계약 뒤에서 교체할 수 있고 Gazebo 기반 생산자는 확장 항목"을 함께 적는다.
  - 권고: 선택 3. 계약과 1b 구현은 선택 1과 같고 비용이 같다. "실기체에서는 같은 토픽을 추적기가 채운다"는 기존 원칙과 같은 말이라 문구가 원칙을 드러낸다. 어느 선택이든 "임의"는 지키기 어려우므로 고친다.
- U11. CI `sitl` 시간 예산. 지금 job 전체 약 5분 43초(1회 기록, pull 약 3분 20초). 1b 비행 셋(F1, F2, F3)이 더해진다. 추정은 재질문 T-3의 답으로 채워 올린다.
  - 선택 1: 15분 목표를 지키고 F1-F3을 모두 PR CI에 둔다. 넘으면 순회 점 수와 Hold 유지 시간을 먼저 줄이고, 그래도 넘으면 측정값과 함께 다시 올린다.
  - 선택 2: 목표를 20분으로 올린다(`sitl.yml` timeout 30분은 그대로). 공개 저장소의 표준 runner라 과금은 없다고 이해하지만(U2와 같은 전제, 문서 재확인 전) PR 피드백이 늦어진다.
  - 선택 3: F3(공중 시작과 RTL)을 nightly로 옮긴다. 1b 완료 기준의 "CI에서 통과" 범위가 바뀌고 nightly job이 아직 없다.
  - 권고: 선택 1. 추정으로는 15분 안에 들고(test-engineer 의견 5-8분 추가), 넘을 때 줄일 수단이 판정을 건드리지 않는다.
- U12. 정답 pose(`/sim/<vehicle_id>/pose`)를 Phase 2 기록물에 넣는 범위. 기록물에 없으면 리플레이 회귀가 웨이포인트 도달 판정을 다시 하지 못한다.
  - 선택 1: SITL 실행의 기록물(MCAP)에 `/sim/` 토픽을 함께 기록한다. 실기체 기록물에는 없고, 그때 판정은 계약 부분만 돈다. 운용 노드는 `/sim/`을 구독하지 않는다(lint 검사).
  - 선택 2: 같은 기록물 디렉터리의 별도 파일로 둔다. 운용 기록물(MCAP)은 시뮬레이터 항목이 없는 채로 남는다. 리플레이 판정이 두 파일을 읽는다.
  - 선택 3: 넣지 않는다. 리플레이 회귀는 계약 판정만 하고 도달 판정은 라이브에서만 한다.
  - 권고: 선택 1. 용량은 기체당 Pose 하나로 작고, "운용 서비스는 시뮬레이터를 모른다"는 구독 금지로 지켜지며, Phase 2 완료 기준("라이브 판정과 같은 판정이 리플레이에서 통과")을 도달 판정까지 덮는다. 이 결정은 Phase 2 기록 대상을 정할 때 효력이 생기고 1b 구현은 어느 선택에서도 같다.

## 실측 목록

U6의 산출물 최소 원칙을 1b에도 쓴다. 결과는 PR 본문과, 상수를 정한 경우 그 상수의 근거 주석에 남긴다.

| 이름 | 무엇 | 왜 | 담당 | 방법 |
| --- | --- | --- | --- | --- |
| W | 명령 timestamp -> ack timestamp 차, disarm 전후 `vehicle_status` 간격 | 지상 취소 disarm 확인 기준(쟁점 11) | px4-engineer | `run_sitl.sh` 1회의 ULog |
| M1 | `<skin>` 없는 Actor가 GUI에서 보이고 움직이는가 | 커스텀 모델 필요 여부(쟁점 2) | sim-engineer | 수동 1회 |
| M4 | Actor 월드에 `gz-gui` 연결, 재접속, 120 s 생존. M2(Actor와 `TargetState` 차)를 육안으로 같이 | viz 서버 생존 리스크(쟁점 17) | sim-engineer | 수동 1회 |
| M5 | 원점을 SDF로만 넣었을 때 스모크 S2 통과 | 런타임 원점 호출 제거(쟁점 2) | sim-engineer, test-engineer | 스모크 1회 |
| R1 | `ref_*`와 `expect_gps`의 차(수평, 수직) | 기록(쟁점 5) | test-engineer | sitl gate의 `recorded_only` |
| R2 | Executor 도달 순간의 정답 pose와 목표의 거리 | 판정 임계값 b(쟁점 5) | test-engineer | F1 trace |
| R3 | `TargetState` 나이, `/clock` 간격, `now - vehicle_status.timestamp` 분위수 | `target_timeout`, 추종 지연 L(쟁점 8, 11) | test-engineer | sitl gate의 `recorded_only` |
| 공중 시작 | F3 진입 구간의 위치 변화, P4-P5 소요 | 섞임 크기와 판정 허용(쟁점 7) | test-engineer | F3 trace |
| RTL | AUTO_RTL 확인 시간, 착지 위치와 home의 차, disarm까지 | RTL `timeout`과 `R_home`(쟁점 9) | test-engineer | F3 trace |

재지 않는 것: L(W가 기준을 넘을 때만), M3(model과 actor 수준 plugin의 영향. 해법 (다)를 고를 때만), M6(표적 수와 서버 CPU. Phase 3 입력), 반복 이륙(U7).

## 문서 반영 목록

결정이 확정된 뒤 고친다. 지금은 고치지 않는다.

B1(U10 뒤, architect)
- `docs/architecture.md` "목표와 범위": U10에 따른 범위 문구.
- `docs/architecture.md` "전체 아키텍처": 표적 경로 문단("ros_gz_bridge로 받은 Gazebo pose를 이 계약으로 변환"), 구성 요소 표의 `idsim_sim` 행(Gazebo pose -> `TargetState`), "Gazebo Actor 위치는 참고용" 문장.
- `docs/architecture.md` "기체 식별과 설정의 단일 출처": `world.origin`의 적용 방식(SDF), params에 `world.origin`이 더해지는 것, 표적 어댑터는 원점을 받지 않는 것, `targets` 스키마 요지, `world.file`의 의미(D-1 답).
- `docs/architecture.md` "Docker Compose 실행 환경 설계": `bridge` 서비스 설명의 "1b에서 Gazebo 표적 pose를 더한다", 표적 어댑터의 위치(`targets` 서비스), 그림의 표적 pose 화살표와 "1b에서 정한다" 문장, `gz_server.sh`의 원점 단계.
- `docs/architecture.md` "테스트 자동화와 CI": 도달 판정 문장("goal의 목표값과 `vehicle_local_position`")을 계약 판정과 정답 판정의 구분으로, `/sim/` 토픽 규칙과 lint, SITL 시나리오 목록(B, C, A, D, F1, F2, F3, T).
- `docs/roadmap.md` Phase 1b: 2번의 `bridge.yaml`과 "표적 상태의 생산 경로는 1b 착수 때 정한다", "EKF 원점 오차 실측으로 표적 접근 임계값을 정한다"(R2와 R1의 역할), 4번의 판정 문장. 리스크 표의 해당 세 행(Actor pose, 범위 문구, `bridge.yaml` 금지 검사).
- `docs/smoke-test.md`: S2의 원점 적용 경로와 `origin_set` 표시 파일(M5 뒤).

B11(1b 완료 전, architect)
- `docs/interface.md`: 위 "1a 고정 계약 영향" (a)-(k), "GoToItem과 TrackEntityItem" 절의 확정 문장(쟁점 8), "TargetState" 절의 "고정 전" 해제와 QoS 상태 행 고정, `REASON_TARGET_LOST` 의미, "공중에서 끝나는 미션" 절(쟁점 10), 고정 시점 표의 1b 행, 좌표계 절의 원점 이동 문장(쟁점 4), 미확인 목록의 1b 항목.
- `ros_ws/src/idsim_interfaces/`: `ExecuteMission.action`, `MissionItem.msg`, `YawSetpoint.msg`, `TakeoffItem.msg`, `GoToItem.msg`, `TrackEntityItem.msg`, `TargetState.msg`의 의미 주석. golden 무변경을 단정한다.
- `docs/architecture.md` 인터페이스 계약 절: 묶음 표의 1b 행, 미션 실행 요지의 재진입 문장(h), 공중 종료 문장, RTL 요지, 시간 기준 요지의 bridge 문장.

## 넘김 목록

| 받는 쪽 | 시점 | 항목 |
| --- | --- | --- |
| px4-engineer, ros2-engineer, architect | 반복 비행의 소비자가 생길 때(Phase 3 이후) | 첫 항목이 아닌 TAKEOFF 허용. 규칙 후보는 px4-engineer 의견 3절(LAND나 RTL 바로 뒤에만, 준비 단계를 P0부터 다시, `ready_timeout`은 항목 시작부터, P5는 그 항목의 DO_SET_MODE 뒤 표본만) |
| px4-engineer, architect | Phase 3 | `RTL_RETURN_ALT`를 기체별 `px4_params`로 덮어도 계약 안으로 두는 예외(고도 층 분리) |
| ops-service-engineer | Phase 3 | Fleet의 배분 전 검증은 core `validate_mission_contract`를 쓴다. 공중 종료 미션의 끝점이 겹치지 않게 하는 계획 책임. 공중 시작 미션은 Hold인 기체에만 보낸다 |
| px4-engineer | Phase 3 설계 후보 | `VEHICLE_CMD_SET_GPS_GLOBAL_ORIGIN`으로 모든 기체의 EKF 원점을 `world.origin`에 맞추는 안(실측 없이 1b에 넣지 않는다) |
| logging-engineer, architect | Phase 2 | U12에 따른 `/sim/` 토픽의 기록 여부, 미션 YAML과 `stack.json`과 라이브 `verdict.json`을 기록물 디렉터리에 함께 두는 규약, bag 로그 시각이 sim 시각인지, 순수 Python mcap 읽기 |
| sim-engineer | 플래키가 보일 때 | Xvfb와 소프트웨어 렌더링으로 `gz-gui` 생존 확인 자동화 |
| sim-engineer | 반응형 표적이 필요할 때 | 해법 (나-2)(서버 plugin이 model을 이동). Actor를 쓰지 않아 `dynamic_pose` 위험이 사라진다 |
