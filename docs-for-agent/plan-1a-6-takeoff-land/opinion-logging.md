# 1a 6번 작업 설계 토론 답변: logging-engineer

작성 2026-11-10, logging-engineer. 질문은 `questions.md`의 logging-engineer 절(L1-L3)이다.

## 실측 조건

- 스택은 올리지 못했다. 답을 쓰는 동안 다른 스택이 셋(idsim-1, idsim-3, idsim-5) 떠 있었고 load average가 8.4(4 vCPU)였다. 운영 조건에 따라 스택 없이 답했다. 그래서 "비행 1회"의 ULog는 직접 만들지 못했고, 이미 `compose down`으로 끝난 스모크 실행의 ULog 7개를 대상으로 했다.
- 대상: `artifacts/runs/20261110-0932..-0950*-k6-s{2,3,4,5}/px4-1/log/` 7개. 모두 `tests/smoke/run_smoke.sh` 320행의 `docker compose -p <프로젝트> down --timeout 10`으로 내려간 실행이다. 같은 시각에 떠 있던 k1, k3, k5의 ULog는 아직 기록 중이라 판정에서 뺐다.
- 도구: scratchpad venv의 pyulog 1.3.0, 그리고 ULog 메시지 경계를 끝까지 따라가는 20행짜리 파서(header 16바이트 뒤 `uint16 size, uint8 type, payload`를 EOF까지 읽고 남는 바이트를 센다).

## L1. ULog의 종료(D11)

결론: 정상 `compose down` 경로에서 ULog는 닫힌 상태로 끝나고 끝까지 읽힌다. 주의할 곳은 Gazebo가 먼저 죽은 실패 경로다.

실측
- [실측] 7개 모두 pyulog `file_corruption=False`, `dropouts=0`, 토픽 82개(이름 81종). 자체 파서로 마지막 메시지가 온전하고 남는 바이트가 0이다(마지막 메시지 type `D`). 반복 7회, 스택 k=6, S2-S5.
- [실측] 크기는 sim 시간 1분당 17.2-17.5 MB로 7개가 거의 같다(31-435초 구간). `SDLOG_MODE=2`(boot-shutdown), `SDLOG_PROFILE=131`이라 arm 여부와 무관하게 부팅부터 같은 비율로 쌓인다. 435초 실행(S4)은 124.5 MB였다.
- [실측] gzip -6으로 9.04 MB -> 2.44 MB(27%), zstd -3으로 2.27 MB. S5 ULog 1개.
- [실측] 파일 소유는 호스트 uid:gid(daniel:daniel, 644)라 CI runner에서 그대로 올릴 수 있다.
- [실측] 기록 토픽에 `trajectory_setpoint`, `vehicle_command`, `vehicle_command_ack`, `vehicle_status`, `vehicle_control_mode`, `failsafe_flags`, `vehicle_land_detected`, `vehicle_local_position(_setpoint)`가 있고 `offboard_control_mode`는 없다(S3 ULog).
- 비행 1회의 크기는 재지 못했다. [추정] 위 비율이 비행 중에도 크게 다르지 않다면 6단계 시나리오(부팅부터 착륙, disarm까지 sim 시간 2-3분)는 35-55 MB, 압축 뒤 10-15 MB다. 스택을 띄울 수 있을 때 `px4-commander takeoff/land` 1회로 확인할 수 있다(scratchpad의 `exp.sh`).

원문
- [소스] PX4 v1.17.0 `platforms/posix/src/px4/common/main.cpp` 496-499행: SIGINT와 SIGTERM을 같은 `sig_int_handler`로 받는다. 503-509행: 핸들러는 `_exit_requested`만 세운다. 610-615행 `wait_to_exit()`는 벽시계 `usleep`로 이 값을 본다. 390-391행: 그 뒤 `shutdown` 명령을 처리한다. 사본은 `raw.githubusercontent.com/PX4/PX4-Autopilot/v1.17.0/...`에서 태그 경로로 받았다(이미지에는 소스가 없다).
- [소스] `src/modules/logger/logger.cpp` 650행: logger가 shutdown hook(`request_stop_static`)을 등록하고, 933-934행에서 loop를 빠져나오며 `stop_log_file`로 파일을 닫는다.
- [소스] `platforms/common/shutdown.cpp` 118-119행 `shutdown_timeout_us = 5_s`, 215/244/268행: shutdown worker는 HPWORK work queue에서 돈다. 즉 hook 대기와 5초 강제 종료가 PX4 hrt 기준이다.

의견: `sitl` 실패 artifact로 올릴 때의 주의
1. 업로드는 `compose down`(또는 `stop`)이 끝난 뒤에 한다. 기록 중인 파일은 logger 버퍼가 남아 마지막 부분이 빠진다. [추정]
2. Gazebo가 PX4보다 먼저 멈추는 경로를 따로 본다. 정상 `down`은 의존 순서상 px4-N을 gazebo보다 먼저 멈춰 문제가 없다([소스] 생성된 compose의 px4-1 `depends_on: gazebo`, [실측] 위 7회). 그런데 lockstep SITL에서 hrt는 sim 시간이라, Gazebo가 이미 죽은 실패(artifact가 가장 필요한 경우)에서는 shutdown worker와 logger loop가 진행하지 못해 `--timeout 10` 뒤 SIGKILL로 끝나고 파일이 닫히지 않을 수 있다. [추정, 원문에서 끌어낸 것. 실측하지 못했다] 그래서 (가) artifact에 px4 컨테이너 종료 코드(0인지 137인지)를 함께 남기고, (나) 판정이나 분석 도구는 잘린 ULog를 실패로 보지 말고 "끝이 잘림"으로 표시하며, (다) 내리는 순서를 바꾸지 않는다(px4를 먼저). 이 경로의 실측은 스택이 비면 `exp.sh gzfirst`(bridge, gazebo를 먼저 stop하고 px4 stop의 소요 시간과 종료 코드, ULog 끝을 확인)로 한다.
3. 크기. 1분당 약 17 MB이므로 실패 job 1회의 ULog는 수십 MB다. `upload-artifact`의 압축으로 약 1/4이 된다. 보관 기간은 devops가 정한다. 프로필을 줄일 이유는 아직 없다(6단계 진단에 필요한 토픽이 기본 프로필에 있다).
4. 파일 이름은 PX4가 정하는 `log/<날짜>/<시각>.ulg`(UTC 벽시계)이고 실행 디렉터리 `artifacts/runs/<실행 id>/px4-N/`가 이미 실행을 구분하므로 6단계에서 이름을 바꾸거나 복사할 필요가 없다. ULog 복사와 오프셋 메타데이터는 Phase 2 `idsim_logger`가 정한다.
5. `offboard_control_mode`가 ULog에 없다. Offboard heartbeat의 끊김은 ULog에서 `failsafe_flags`(`offboard_control_signal_lost`)와 `vehicle_control_mode`로만 보인다. 6단계 failsafe 분석에서 노드 쪽 발행 시각을 보려면 노드 로그(`ros_log`)를 함께 올려야 한다. [실측, 위 토픽 목록]

## L2. `sitl` artifact의 MCAP

결론: 플러그인은 이미 있다. 6단계에는 넣지 않고 Phase 2로 미루기를 권한다. 넣는다면 아래 세 조건을 지켜야 Phase 2 설계를 묶지 않는다.

실측
- [실측] `idsim/ros-ws:local`(sha256:88ad3ee3..., 2026-11-10 생성)에 `ros-jazzy-rosbag2-storage-mcap 0.26.11`, `mcap_vendor`, `rosbag2_compression_zstd`, `librosbag2_storage_mcap.so`가 있다. `ros2 bag record --help`가 `--storage {mcap,sqlite3}, defaults to 'mcap'`이다. `docker run --rm` 1회.
- [소스] `docker/Dockerfile.ros-base` 46행이 `ros-${ROS_DISTRO}-ros-base`를 설치하고, rosbag2는 여기서 따라 들어온다(Dockerfile에 rosbag2를 직접 적은 줄은 없다). [문서] REP 2001(https://www.ros.org/reps/rep-2001.html)의 ros_base 변형에 rosbag2가 포함된다. 그래서 이미지 변경 없이 쓸 수 있지만, 우리가 고정한 의존이 아니라 메타패키지의 귀결이다.

의견
- 6단계에 넣었을 때 얻는 것은 ROS 쪽 사실(`/<vehicle_id>/mission_event`, action status, 노드의 setpoint 발행 시각과 `/clock`의 관계)이다. PX4 쪽 상태는 ULog가 더 높은 rate로 이미 갖고 있다(L1 토픽 목록). [추정]
- 6단계에 넣을 때 드는 것: runner에서 recorder 프로세스 하나(4 vCPU 호스트에서 스택과 경합), fixture의 종료 처리(rosbag2는 정상 종료해야 MCAP summary와 `metadata.yaml`이 써진다. 5단계 넘김 목록의 [실측]대로 비대화형 bash의 백그라운드 프로세스는 SIGINT를 무시하므로 `setsid`로 띄워 그룹에 신호를 보낸다), 기록 대상 목록.
- Phase 2를 묶는 것. 다음 넷 중 하나라도 생기면 묶인다.
  1. 기록물 경로와 이름. 6단계 fixture가 `artifacts/runs/<실행 id>/` 아래에 정한 이름이 Phase 2의 `<시각>_<미션 id>_<기체 id>` 규칙 이전에 굳는다.
  2. 기록 대상 목록과 QoS override 파일. 6단계 목록이 Phase 2 선별 목록의 출발점으로 오인된다.
  3. 소비자. 6단계 기록물을 읽는 테스트(replay나 판정)가 생기면 그 형식이 사실상 계약이 된다. 이것이 가장 크다.
  4. 기록기와 Executor의 순서(L3). fixture가 recorder를 띄우면 "recorder 구독이 맺어진 뒤 goal" 문제가 6단계로 당겨진다. 테스트가 그 순서를 지키지 않으면 접수 사건이 빠진 기록물이 올라오고, 지키려면 Phase 2의 ready 신호 결정이 앞당겨진다.
- 넣기로 한다면 조건: (가) 진단 전용이며 어떤 테스트도 읽지 않는다, (나) 이름과 위치를 `docs/interface.md`에 올리지 않고 `artifacts/runs/<실행 id>/diag/` 같은 진단 위치에 둔다, (다) 접수 사건의 손실을 허용한다고 적는다(순서를 보장하지 않는다). 이 조건이면 Phase 2는 그것을 버리고 새로 정할 수 있다.
- `docs/architecture.md`의 `sitl` 문장("실패 시 MCAP 기록물과 ULog를 artifact로")과 6단계 실제(ULog와 컨테이너 로그, `ros_log`)의 차이는 문장에 "MCAP은 Phase 2부터"를 붙여 맞추는 쪽이 범위를 늘리지 않는다. 문장 수정은 architect 몫이고, 당기는 쪽은 사용자 결정 후보 4다.

## L3. `MissionEvent` 발행 쪽 확인

결론: 6단계 구현(RELIABLE, VOLATILE, KEEP_LAST 10, goal마다 접수와 종료)은 Phase 2의 기록기 순서 결정을 막지 않는다. Executor 쪽 구독자 수 게이트는 6단계에 넣지 않는다.

의견(이 절은 실측 대상이 없다. 근거는 5단계 `decisions.md`의 계약 문장과 아래 [추정]이다)
- 막지 않으려면 발행 쪽이 지킬 것 셋.
  1. 발행자를 goal 처리 안에서 만들지 않는다. configure나 activate에서 만들어 노드가 살아 있는 동안 그래프에 계속 보이게 한다. 기록기는 토픽을 주기 탐색해 구독하므로, goal 때 처음 생기는 발행자이면 어떤 순서를 정해도 접수 사건이 기록되지 않는다. [추정, Jazzy recorder의 topic polling 동작]
  2. TRANSIENT_LOCAL로 바꾸지 않는다(5단계 계약 그대로). depth 10은 goal마다 두 건이라 충분하다. 기록기 쪽은 Phase 2에서 명시 QoS override로 RELIABLE, VOLATILE을 고정한다.
  3. 접수 사건은 goal이 수락된 뒤(`handle_accepted` 안)에, 종료 사건은 result를 돌려주는 호출 직전에 낸다. 테스트는 result 수신과 종료 사건 수신의 순서를 가정하지 않고 둘 다 기다린다(다른 DDS 엔터티라 도착 순서가 보장되지 않는다). [추정]
- 구독자 수 게이트를 넣지 말아야 하는 이유.
  1. 6단계에는 기록기가 없다. 게이트를 넣으면 "구독자 없으면 goal을 어떻게 하나"(거부, 대기)라는 새 동작이 Executor에 생기고, 관찰용 사본(`MissionEvent`)이 정본(action)의 수락을 좌우하게 된다. 5단계의 "정본은 action, 이 메시지는 기록과 관찰을 위한 사본" 원칙과 맞지 않는다.
  2. 게이트가 증명하지 못한다. `get_subscription_count() >= 1`은 테스트의 구독만으로 참이 되어 기록기가 맺어졌는지를 말해 주지 않는다. Phase 2에서 이 방식을 고르더라도 "어떤 구독자를 기다리는지"를 따로 정해야 하므로 6단계에 미리 둘 이득이 없다.
  3. Phase 2에서 내가 기울어 있는 쪽은 logger 쪽 ready 신호다(기록기가 Executor 발행자와 맺어진 것을 logger가 확인해 알린다). 이 방식이면 Executor는 바뀌지 않는다. 결정은 Phase 2에서 한다.
- 6단계 통합 테스트의 "자기 구독의 발행자 수 확인 뒤 goal"은 Phase 2 결정과 독립이다. 테스트가 기록기의 순서를 대신 보장하지 않는다는 것만 테스트 주석에 적으면 된다.

## 다른 담당자와 부딪칠 수 있는 곳

- devops: 실패 artifact의 업로드 시점(down 뒤)과 크기(수십 MB, 압축 뒤 1/4), px4 컨테이너 종료 코드 기록. Gazebo가 먼저 죽은 경우의 ULog 잘림은 내리는 순서를 바꿔서 풀 수 없다.
- test: fixture가 recorder를 띄울지(L2). 띄우면 L3의 순서 문제가 6단계로 들어온다. 종료 사건과 result의 도착 순서를 가정하지 않는 판정.
- ros2: `MissionEvent` 발행자 생성 시점(configure/activate)과 종료 사건의 발행 위치, 구독자 수 게이트를 두지 않는 것.

## 재질문 답(2026-11-11)

실측 조건: 호스트 4 vCPU, 시작 전 `docker ps -a` 0개, load 0.86/2.29/2.20. 스택은 나 혼자 k=6으로 순서대로 6회 올렸다(다른 컨테이너 없음). 측정 중 5초 간격 기록에서 1분 load는 0.35-2.50, 컨테이너 수는 0-4개(모두 idsim-6). 저장소 빌드와 파일 변경 없음. 비행은 `px4-commander takeoff`(기본 2.5 m) -> 약 24 s hover -> `land` -> disarm. script는 scratchpad `lq/exp2.sh`, `lq/exp3.sh`(`exp.sh`를 고쳐 px4만 따로 stop해 시간을 재고, 멈춘 hrt를 `px4-listener`로 확인하는 단계와 비행 중 kill 모드를 더했다). 끝에 스택, 백그라운드 기록 프로세스를 정리했고 남은 컨테이너 0개를 확인했다. 실행 디렉터리는 `artifacts/runs/20261110-17{0003,0139,0401,0544,0707,0840}-k6/`.

### 1. 비행 1회의 ULog 크기와 판독

결론: 비행 1회(부팅 -> 이륙 -> hover -> 착륙 -> disarm -> stop, sim 43-46 s)는 12.9-13.5 MB, 압축 뒤 3.7-3.9 MB(gzip -6)다. 비율은 sim 시간 1분당 17.8-18.0 MB로 지상 대기만 있던 앞선 측정(17.2-17.5)보다 약 3% 크다. px4의 "약 10 MB/분"은 비율이 다른 것이 아니라 분모를 잘못 잡은 것이다.

실측(정상 종료 2회 n1, n2와 아래 2번의 4회를 합쳐 6개)

| 실행 | 종료 | sim 길이(s) | 크기(MB) | MB/분 | gzip -6(MB) | zstd -3(MB) |
| --- | --- | --- | --- | --- | --- | --- |
| n1 170003 | 정상 | 43.3 | 12.87 | 17.9 | 3.73 | 3.49 |
| n2 170707 | 정상 | 45.5 | 13.51 | 17.8 | 3.91 | 3.65 |
| g1 170139 | Gazebo 먼저 stop | 53.3 | 16.01 | 18.0 | 4.55 | 4.26 |
| g2 170401 | Gazebo 먼저 stop | 52.5 | 15.66 | 17.9 | 4.50 | 4.20 |
| k1 170544 | hover 중 Gazebo kill | 33.5 | 10.01 | 17.9 | 2.88 | 2.70 |
| k2 170840 | hover 중 Gazebo kill | 33.4 | 9.99 | 17.9 | 2.88 | 2.70 |

- [실측] 6개 모두 pyulog `file_corruption=False`, `dropouts=0`, 토픽 83-84개. 자체 parser로 마지막 메시지가 온전하고 남는 바이트 0(마지막 type `D`). `vehicle_status.arming_state`에 1 -> 2(-> 1)가 들어 있다.
- [실측] 압축률은 gzip -6 29%, zstd -3 27%로 앞선 값(27%, 25%)과 비슷하다.
- [실측] px4 값의 출처는 `artifacts/runs/20261110-143204-k1/px4-1/log/2026-11-10/14_32_30.ulg`(266.5 MB)다. 이 파일의 sim 길이는 922.1 s(15.4분)이고 비율은 17.34 MB/분이다. 파일 이름(UTC 14:32:30)과 mtime(14:47:55 UTC)의 차도 925 s라 벽시계로도 15.4분이다. "25분"은 ULog 길이가 아니었다(스택 수명을 어림한 것으로 보인다. [추정]). 같은 날 다른 px4 스택의 ULog(14_48_33.ulg 142.2 MB, 485 s)도 17.59 MB/분, sim 스택의 ULog(14_33_13.ulg 411.2 MB, 1451 s)는 17.00 MB/분이다. 비율은 실행과 경합에 무관하게 17-18 MB/분이다.
- 6단계 시나리오(sim 2-3분)에 다시 대면 36-54 MB, gzip 뒤 10-16 MB다. decisions-draft 10번의 "큰 쪽(17.5 MB/분, 압축 뒤 약 1/4)"은 18 MB/분, 압축 뒤 약 0.3으로 고치면 맞다.

### 2. Gazebo가 먼저 죽었을 때

결론: 앞선 [추정](hrt가 멈춰 logger와 shutdown worker가 진행하지 못하고 SIGKILL, 파일 잘림)은 틀렸다. Gazebo를 SIGTERM으로 먼저 멈추든 hover 중 SIGKILL로 죽이든 px4는 SIGTERM 뒤 0.09-0.10 s에 종료 코드 0으로 끝났고, ULog는 hrt가 멈춘 시점까지 빠짐없이 온전했다. 실패 artifact 쪽 권고(px4 종료 코드 기록, 잘린 ULog를 "끝이 잘림"으로 표시, 내리는 순서 px4 먼저)는 그대로 두되, 6단계에서 Gazebo 선사망이 ULog를 자른다는 근거는 없다.

실측
- [실측] g1, g2: 지상 disarm 뒤 `docker compose stop -t 10 bridge gazebo`(10.4 s, bridge 137, gazebo 143) -> 3 s 대기 -> `vehicle_status.timestamp`가 2 s 간격 두 번 같은 값(g2 69.168 s, "0.4 s ago")이라 hrt가 멈춘 것을 확인 -> `compose stop -t 10 px4-1` 0.097 s, 종료 코드 0, 로그 끝 `PX4 Exiting...`, `Exiting NOW.`
- [실측] k1, k2: 이륙 뒤 hover 중(z 약 -2.8 m, armed) `docker kill` gazebo, bridge(둘 다 137) -> 3 s 대기 -> hrt 멈춤 확인(k1 50.492 s, k2 50.484 s) -> px4 stop 0.090/0.105 s, 종료 코드 0, `Exiting NOW.`
- [실측] ULog의 마지막 data 시각은 멈춘 hrt와 같다(g2 69.568 = 69.168 + 0.4, k2 50.484 = 50.384 + 0.1, k1 50.492, 4 ms 한 칸 이내). 멈춘 뒤의 sim 시간은 0이므로 잃은 구간이 없다. k1, k2 ULog에는 disarm이 없다(armed 상태로 끝).
- [실측] 비교: 정상 종료 n1, n2의 px4 stop은 0.098/0.208 s, 종료 코드 0. 나머지 컨테이너 stop은 정상 20.4-20.5 s(bridge, xrce-agent가 각각 10 s 뒤 137), Gazebo가 이미 없을 때 10.1 s. devops의 약 21 s와 맞다.
- 한계: 반복 각 2회. Gazebo를 먼저 멈춘 것은 지상 disarm 상태에서만, kill은 hover 중에만 했다.

원인(미확인)
- [소스] v1.17.0 `platforms/common/shutdown.cpp` 172-175행은 `now > shutdown_time_us`(hrt)를 요구하고, `logger.cpp` 434-441행의 hook은 logger가 도는 동안 false를 돌려주며, logger loop(927행)는 hrt timer가 올리는 semaphore를 기다린다. lockstep에서 hrt가 멈춰 있으면 이 경로로는 끝날 수 없어 보이는데 실제로는 `Exiting NOW.`가 0.1 s 안에 찍혔다. 무엇이 진행시켰는지는 찾지 못했다. 결과(종료 코드 0, ULog 온전)는 4/4라 결정에는 실측을 쓰고, 원인은 px4-engineer에게 넘긴다.
- ULog에는 끝 표시가 없어 "정상으로 닫힘"과 "버퍼까지 다 쓴 뒤 끊김"을 파일만으로 가를 수 없다. 그래서 판독 도구는 종료 코드와 함께 본다는 권고는 유지한다.
