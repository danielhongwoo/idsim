# devops-engineer 의견: 쟁점 2 재결정(자기 전이, healthcheck로 실패 드러냄, ops-N SIGINT) (2026-11-11)

읽기 전용. 근거: PR #23 decisions.md 쟁점 2, P3a 결과 반영, 쟁점 10, 11, devops 구현 지시, p3a-results.md, tools/gen_compose.py 426-427, 610-640행, tools/stack.sh 83-85, 149-193행, tests/smoke/run_smoke.sh 320행, config/cyclonedds.xml 37-38행, 떠 있는 스택 idsim-0의 /proc/1/status 신호 마스크(읽기만).

결론: 결정에 반대하지 않는다. 아래 조건을 붙인다. 표시 파일은 지금 필요 없다.

## 1. healthcheck 시간 값과 실패가 드러나기까지의 상한

권고 값(ops-N): interval 10s, timeout 10s, retries 2, start_period 20s, start_interval 2s.

명령은 CMD-SHELL. `. /opt/ros/$${ROS_DISTRO}/setup.sh`만 source(workspace overlay와 `bash -l` 없음). `ROS_LOG_DIR=/tmp/hc timeout 8 ros2 lifecycle get --no-daemon <FQN>` 출력을 echo하고 `active`로 시작하면 0, 아니면 1.
- 안쪽 `timeout 8` [추정, 미실측]: Docker는 timeout이 지난 probe를 죽이지 않는 것으로 안다. bridge의 `timeout 4`와 같은 방식.
- 출력을 버리지 않는다: `.State.Health.Log`에 `unconfigured [1]`, `inactive [2]`가 남아 run_sitl.sh 아티팩트의 진단이 된다.

exec 비용 [추정, moby health monitor 동작 기억]: probe는 겹치지 않고, 다음 probe는 앞 probe가 끝난 뒤 interval만큼 기다린다. 실제 주기는 interval + d(P3a 실측 d 3.0-4.5 s). start 구간 약 5-6.5 s, 그 뒤 약 13-14.5 s 간격. P4에서 Health.Log의 Start/End로 확인.

상한(컨테이너 시작부터):
- 정상: active까지 0.30-0.64 s(P3a), 첫 probe 약 2 s 시작, 약 5-6.5 s에 healthy. 느려도 약 13 s 이내.
- 자기 전이 실패: configure 실패 약 0.6 s, /clock 없어 activate 실패 2.0 s 뒤 상태 고정(재시도 없음). start_period 중 실패는 retries에 세지 않는다. 실측 d 기준 상한 20 + 4.5 + 2 x 14.5 = 약 54 s, 모든 probe가 timeout까지 가는 최악 20 + 10 + 2 x 20 = 70 s.
- `up --wait`는 unhealthy 즉시 실패. stack.sh 노드 단계와 run_sitl.sh(INFRA_UP)가 실패를 보는 상한 약 54 s, 최악 70 s. STACK_UP_TIMEOUT 240 s보다 작아 노드 단계 wait-timeout을 따로 둘 필요 없다.

값의 이유:
- start_period 20s: 정상 기동에서 상태가 굳는 최악(launch + configure + /clock 대기 2 s)을 CI에서 3배로 잡아도 약 12 s.
- retries 2: runner `depends_on`이 ops-1..N healthy로 바뀌면 probe 하나의 흔들림으로 테스트 시작이 실패하는 위험을 피한다(retries 1이면 상한 약 39 s).
- interval 10s: 판정 구간 90-110 s 동안 기체당 probe 약 7회. probe마다 python 기동과 DDS participant 합류/이탈이 생겨 4 vCPU에서 CPU를 나눈다. 30 s면 상한 약 94 s. 조건: CI 첫 3회에 RTF와 함께 probe 시간(Health.Log) 기록. RTF가 0.7 기준에 걸리면 interval 30 s를 먼저 시험.
- participant 수: MaxAutoParticipantIndex 50(cyclonedds.xml 38행) 안에서 probe는 기체당 한 번에 하나라 문제없다.
- start_interval: Engine 25 이상(check_host.sh 항목). CI에서 runner `docker version`을 job 로그에 남긴다.

P4 검증 조건: missing params 결함 주입으로 `stack.sh up`이 unhealthy를 보고하기까지 시간 1회 이상, 정상 healthy까지 시간. 상한과 다르면 architect에게 알린다.

## 2. SIGINT, exit 1, stop_grace_period, 다른 ros-ws 서비스

exit 1을 실패로 읽지 않는 방법:
- 컨테이너 exit code는 판정 근거로 쓰지 않는다. 판정은 junit과 verdict로만.
- `--abort-on-container-exit`, `--exit-code-from`은 쓰지 않는다. `compose down/stop`은 exit code와 관계없이 0.
- 테스트 중 ops-N이 죽은 것(`on_exit=Shutdown()`이라 exited)과 정상 정리를 순서로 구분: (1) stop 전 `compose ps -a --format json` 기록, (2) 그 시점 running이 아닌 ops-N이 있으면 실패, (3) `compose stop`, (4) `compose logs`(SIGINT 정리 로그 포함), (5) `down`.
- stop 뒤 exit code(1, 130 등)는 기록만 한다. stack.sh 161행은 up 실패 때만 돌므로 그대로. entrypoint에서 exit 1을 0으로 바꾸지 않는다.

stop_grace_period: stack.sh 85행과 run_smoke.sh 320행은 `down --timeout 10`이고 down의 `--timeout`이 서비스 stop_grace_period보다 우선한다. ops-N stop_grace_period를 10s로 맞춰 하나로 통일. 1.7 s(P3a, 1-2회)에 비해 여유. goal 실행 중 stop(on_shutdown이 ABORTED 사건) 시간은 미실측, P4에서 1회.

`init: true` 유지: SIGINT 경로는 tini가 전달하고 init 유무와 관계없이 1.7 s(P3a). SIGTERM이면 init 있을 때 0.4-0.5 s, 없으면 15 s 뒤 SIGKILL. 좀비 회수.

다른 서비스(근거: /proc/1/status SigCgt/SigIgn. PID 1은 handler 없는 신호를 버린다. 실제 down 시간은 미측정):

| 서비스 | PID 1 | SIGINT | SIGTERM | 판단 |
| --- | --- | --- | --- | --- |
| bridge | `ros2 run`의 python | handler 있음 | 버려짐 | down에서 10 s 뒤 SIGKILL(137) [추정] |
| xrce-agent | MicroXRCEAgent | 버려짐 | 버려짐 | 같은 문제 [추정] |
| px4 | `px4` | handler 있음 | handler 있음 | 문제 없음 |
| gazebo | gz_server.sh, TERM trap | handler 있음 | handler 있음 | 문제 없음 |

- 생성기에서 init, stop_signal, stop_grace_period를 쓰는 서비스는 지금 없다(`_base`는 image, network_mode, restart뿐, gen_compose.py 426-427행).
- compose는 의존 역순으로 멈추므로 지금 down은 bridge 10 s와 agent 10 s가 이어져 약 20 s 이상 [추정].

권고:
- 상주 ros-ws 서비스(bridge, ops-N, P5 foxglove)와 xrce-agent에 `init: true`. tini가 TERM을 전달하면 1초 안에 끝날 것으로 본다.
- launch로 띄우는 ops-N에만 `stop_signal: SIGINT`. bridge의 `ros2 run`이 SIGINT를 자식에 전달하는지는 모르므로 bridge는 init + TERM.
- 생성기 성질 테스트: (1) ros-ws 이미지 상주 서비스는 모두 init true, (2) ops-N은 stop_signal SIGINT, stop_grace_period 10s.
- P4에서 down 시간을 바꾸기 전후 1회씩.

runner [추정, 미실측]: wrapper가 `timeout`으로 `compose run`을 감싸면 SIGTERM이 PID 1 pytest에서 버려져 `-k` 시간까지 안 끝날 수 있다. runner에도 `init: true` 또는 `timeout -s INT -k 30`. P4에서 1회 확인.

## 3. 반대나 조건, 표시 파일

반대 없음. 조건:
1. 실패 ERROR 로그는 grep 가능한 고정 접두어의 한 줄(어느 전이가 왜 실패했는지). stack.sh는 노드 단계 실패 때 ops-N 로그 끝과 `.State.Health.Log`를 함께 찍고, run_sitl.sh는 둘 다 아티팩트에 넣는다.
2. 생성기 성질 테스트: params 파일에 `lifecycle.` key가 없어야 한다(self_start가 실수로 false면 약 54 s 뒤에야 보인다).
3. healthcheck 대상 FQN은 생성기 상수 하나에서. stack.json의 `executor_node`와 healthcheck 문자열 일치를 성질 테스트로(bridge 포트 대조 795행과 같은 방식).
4. 1절의 P4 실측 둘(결함 주입 unhealthy 시간, CI 첫 3회 probe 시간)을 P4 완료 기준에.
5. P4에서 ops-N 기동/정지 경로를 확정하며 bridge, agent init 문제도 같은 PR에서 고친다(생성기 golden 4종 함께 변경).

표시 파일: 지금 필요 없다. 자기 전이 실패는 영구 상태라 healthcheck가 반드시 잡고, 상한(약 54 s, 최악 70 s)은 실패한 run에서만 드는 비용이며 15분 예산 안이다. 표시 파일은 컴포넌트와 compose 사이에 경로 계약을 만든다(Phase 2에 Collector 동거). gazebo의 원점 표시 파일은 달리 신호가 없어서였고 여기는 `ros2 lifecycle get`이라는 직접 신호가 있다. 다시 볼 조건: CI에서 probe 평균 7 s 초과 또는 probe 부하가 RTF 0.7 기준에 걸릴 때. 대안: 노드가 전이 결과를 파일 하나에 쓰고 healthcheck가 그 파일을 먼저 읽어 failed면 즉시 실패, active면 `ros2 lifecycle get`으로 확인(ros2와 devops 합의 필요).

측정 없이 말한 것: probe 직렬 동작, timeout 지난 probe 미종료, bridge/agent down 시간, runner TERM 동작, goal 중 SIGINT 정리 시간. 모두 P4에서 잰다.
