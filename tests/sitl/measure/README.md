# PX4 재실측 측정 스크립트

`docs-for-agent/plan-1a-6-idsim-mission/decisions.md`의 "재실측 결과와 기준" 절의 재실측 (2), (3), (5)와, OFFBOARD가 아닌 ARMED 표본 기록(`armed` 항목)을 돌리는 도구다. 소유는 test-engineer, 절차의 필수 승인자는 px4-engineer다.

이 측정은 Executor 없이 PX4에 직접 명령을 보낸다(PX4 직접 부류). 시나리오 A(Executor 경유)의 대응이나 대체가 아니다. 통과해도 P4 머지 조건은 Executor 경유 부류의 통과가 따로 필요하다.

## 실행

```
tests/sitl/measure/run_measure.sh [--stack 7] [--attempts N] [--keep] item2|item3|item5|armed|all
```

- 스택 번호 기본값은 7(실험용). 0은 사용자 스택이라 거부한다.
- `item2` 재실측 (2), `item3` 재실측 (3), `item5` 재실측 (5), `armed` PX4 직접 명령의 arm -> ARMED 3회 -> 이륙 -> 착륙 구간 기록.
- 기본 시도 수: item2 3, item3 27(지연값 아홉 개 x 3회), item5 10, armed 10. item2, item5, armed는 통과 기준의 최소 시도 수와 같고, item3은 대역별 최소 유효 시도(아래)보다 많다. item3의 `--attempts`는 27만 받는다(다른 수나 일부 지연값만의 실행은 받지 않는다). `run_measure.sh --attempts`는 모든 item에 적용되므로 item3과 다른 item을 함께 돌릴 때는 쓰지 않는다.
- `all`은 item3, item5, item2, armed 순으로 한 스택에서 돈다. 같은 item을 두 번 주면 거부하고, 기존 기록 파일이 있으면 덮어쓰지 않고 거부한다.
- `--keep`을 주면 끝나도 스택을 내리지 않는다. `measure.py`는 마지막 시도 뒤 기체를 DISARMED, `landed` true로 되돌리고(`--keep`이어도) 그 결과를 요약에 적는다. 되돌리지 못하면 Hold armed로 남아 있을 수 있다.
- 같은 실행 id의 `measure/`에 기록이 있으면 스택을 올리기 전에 거부한다.
- 추가 인자: `MEASURE_ARGS="--observe-s 60 --hold-observe-s 60 --delays 0,0.05,0.1,0.15,0.2 --takeoff-alt 5 --tail-s 3 --settle-s 3"`. `--delays`((5) 전용)는 0-0.2 s 범위만, `--tail-s`는 0보다 커야 한다. `--item3-delays`((3) 전용)는 고정 목록(아래) 아홉 개를 모두 포함해야 하고(순서는 자유) 부분 목록과 중복을 거부한다. 다른 값은 코드의 고정 목록을 고쳐야 한다.
- 이 스크립트는 `tools/sim_stack.sh up --infra-only`로 스택을 올린다. 그냥 `up`은 Executor(`ops-N`)도 띄워 setpoint가 측정기의 직접 발행과 섞인다.

## (3)의 대역과 판정

(3)은 이륙 직후(첫 ARMED 표본 뒤)의 취소를 세 대역으로 나누어 잰다. 정본은 decisions.md의 "재실측 결과와 기준" 절(재실측 (3))과 쟁점 3의 "이륙 직후 취소의 두 경로"다. 판별 코드는 `tests/support/measure_bands.py`(순수 코드)이고 `crosscheck.py`가 ULog로 적용한다.

실행 전에 고정한 지연값(이 호스트): spoolup 0, 0.5 s / 내부 1.074, 1.223, 1.372, 1.521 s / 경계 1.644, 1.694, 1.724 s. 지연값마다 3회, 합 27회이고 라운드 로빈 순서다. 계산식은 spoolup 0과 0.5 / 내부 T_r + {0.1, 0.3, 0.5, 0.7} x (T_lf - T_r) / 경계 T_lf - {0.10, 0.05, 0.02}이고, T_r은 `COM_SPOOLUP_TIME` 1.0 s, T_lf는 ULog의 `vehicle_land_detected` `landed` false `timestamp` - 첫 ARMED `vehicle_status` `timestamp`의 최솟값이다. 근거는 실행 `20261112-011246-k5-measure`의 13개 표본(최솟값 1.744 s, 최댓값 1.804 s)이고 image key `px4` 81678f535f7e4b05, `sim-base` cd6a22462ff15990에서 얻었다. 지연값과 T_r, T_lf의 출처는 실행 전에 `summary_item3.txt` 머리에 적힌다. 결과를 보고 지연값이나 시도를 더하지 않는다.

image key(px4, sim-base)나 TAKEOFF 목표 높이(`--takeoff-alt`, 근거 실행 5.0 m)가 근거 실행과 다르면 실행을 거부한다(`measure.py`가 스택에 아무것도 보내기 전에 종료 코드 2). 같은 key로 `armed` item을 먼저 돌리면 `crosscheck.py`가 ULog의 T_lf 표본 수, 최솟값, 최댓값과 그 최솟값으로 계산한 지연 목록을 출력한다. 그 값으로 `measure_bands.py`의 `T_LF_REF`와 `ITEM3_DELAYS_S`를 고친 뒤 (3)을 돌린다. 고친 뒤에는 커밋하고 돌린다(`dirty`가 true인 실행은 머지 조건으로 세지 않는다).

trigger: 첫 ARMED 표본의 PX4 `timestamp`(수신 `/clock`이 아니다) + 명목 지연까지 `/clock`으로 기다렸다가 지상 setpoint로 바꾸고 disarm한다. 이미 지났으면 즉시 보낸다. 기다리는 동안 TAKEOFF 목표점 발행을 이어 가고, `/clock`이 멈추면 `CLOCK_STALLED`다. 행의 `injection`에 명목 지연(`delay_s_nominal`), 실제 지연(`delay_s_actual` = 취소 `/clock` - 첫 ARMED `timestamp`), 첫 ARMED 수신 지연(`first_armed_recv_lag_s` = 수신 - `timestamp`), 취소 `/clock`(`cancel_clock_us`)이 남는다.

ULog에서 읽는 것(`ulog_min.read_topics`가 파일을 한 번만 읽는다): `vehicle_status`, `vehicle_land_detected`, `vehicle_command_ack`, `vehicle_command`, `vehicle_thrust_setpoint`, `takeoff_status`(보조), `actuator_armed`, `vehicle_local_position`, logged message(`Disarming denied: not landed`, `Disarmed by external command`, `Armed by external command`). SITL의 `timestamp`는 4 ms 단위다.

- t_A: arm 전송 뒤 첫 `arming_state` 2인 `vehicle_status`의 `timestamp`.
- t_ramp: t_A 뒤 `in_ground_effect` true인 첫 `vehicle_land_detected`(없을 수 있다). 교차 확인: `takeoff_state` 4 표본이 있으면 t_ramp와 8 ms 안, 추력(`vehicle_thrust_setpoint` xyz[2])이 "arm 뒤 0.9 s 바닥 중앙값 - 0.002" 아래로 내려간 첫 표본이 [t_ramp - 20 ms, t_ramp + 40 ms] 안. 어긋나면 기록하고 INCONCLUSIVE(2).
- t_ml, t_lf: t_A 뒤 `maybe_landed`, `landed`가 false인 첫 표본.
- t_p, r_p: 측정기가 처음 보낸 disarm(`vehicle_command` 400, param1 0, `timestamp` = 보낸 `Px4Timestamp`)에 대응하는 `vehicle_command_ack`의 `timestamp`(처리 시각)와 `result`. 대응은 `timestamp`의 크기가 아니라 ULog에 기록된 command 400과 ack 400의 파일 순서(1:1)로 한다. arm의 재전송 ack가 t_A 뒤 `timestamp`로 남거나 arm ack와 disarm ack의 `timestamp`가 같아도 섞이지 않는다. 근거는 Commander가 주기당 command 하나를 FIFO로 처리하고 ack가 처리 순서대로 기록되는 것이다([소스]. 실측은 없다).
- first_disarm_lost: 그 disarm의 `vehicle_command`가 ULog에 없음. INCONCLUSIVE(2). 구간의 command 400과 ack 400의 수가 다르면 `ACK_COUNT`로 INCONCLUSIVE(2)이고 이 검사가 일관성 검사보다 앞선다.
- ack를 찾는 구간은 구간 끝(`ros_end`) 뒤 0.5 s(`ACK_SLACK_US`)까지다. 다음 시도의 시작이 이보다 가까우면(`--settle-s`가 0.5 미만) 다음 시도의 arm ack가 구간에 들어와 `ACK_COUNT`로 빠진다. 쌍 간격 상한 `PAIR_MAX_GAP_US`(100 ms)는 px4-engineer가 승인했다(근거 실행은 65쌍이 8-20 ms).
- ld_p: `timestamp`가 t_p 이하인 마지막 `vehicle_land_detected`.

대역(t_p 기준. 계획한 지연값과 무관):

| 대역 | 조건 |
| --- | --- |
| spoolup | t_ramp가 없거나 t_ramp > t_p, 그리고 ld_p `landed` true |
| 내부 | t_ramp <= t_p, t_p - t_A < T_lf - 0.10 s, ld_p `landed` true |
| 경계 | t_ramp <= t_p 이고 (t_p - t_A >= T_lf - 0.10 s 또는 ld_p `landed` false) |

내부 시간대인데 ld_p `landed`가 false이면 경계로 분류하고 "T_lf가 앞선 최솟값보다 작다"는 관측으로 기록한다(`t_lf_below_ref`). 창 밖(`WINDOW_MISSED`)은 t_lf가 측정기의 취소 전송 `/clock` 이하인 회다.

최종 verdict(crosscheck 뒤). 판정 순서는 아래와 같고 앞 단계가 이긴다:

1. 창과 무관한 기준을 어긴 회(`measure.py` 단독의 FAIL, 1).
2. `M3_CONTRADICTED`(1): Hold 뒤 60 s 관찰(item3의 Hold 종료와 item2의 2b)의 ULog 전체 표본에 `landed` true가 있음. 관찰 구간 직전의 마지막 표본은 구간 시작 시점의 값이라 그것이 true여도 센다. ULog 표본이 부족해도 true가 보이면 이 단계다. 2b는 `measure.py` 단독이 INCONCLUSIVE였어도 ULog에 `landed` true가 있으면 1이다.
3. 대역 확정 계산(verdict 없음). 아래 중 하나면 대역 미확정이다: `NO_DISARM`(측정기가 disarm을 보내지 않음), `FIRST_DISARM_LOST`(그 command가 ULog에 없음), `ACK_COUNT`(command 400과 ack 400의 수가 다름), `ACK_PAIR`(대응한 쌍의 ack가 command보다 앞이거나 간격이 `PAIR_MAX_GAP_US`(100 ms)를 넘음), `NO_ACK`, `RAMP_MISMATCH`(t_ramp 판별 불일치. in_ground_effect, takeoff_state, 추력 하락의 시각을 사유에 남긴다), `BAND_UNKNOWN`.
4. 대역이 정해진 회: `M5_INCONSISTENT`, 이어서 `M5_CONTRADICTED`(둘 다 1). Hold 뒤 관찰이 모자라도, 창 밖이어도, `measure.py` 단독이 INCONCLUSIVE였어도 이 단계를 거친다.
5. INCONCLUSIVE(2): Hold 뒤 관찰의 ULog `vehicle_land_detected` 표본이 구간을 덮지 못함(0개 포함, `HOLD_OBS`)이거나 `maybe_landed`만 true(`MAYBE_LANDED`. 기록만 한다). 덮었는지의 기준은 구간 앞의 마지막 표본과 구간 끝을 포함한 이웃 표본 사이 최대 간격 2 s 이하이다(`HOLD_OBS_MAX_GAP_US`. 근거 실행은 60 s에 60-61개, 최대 간격 1.004 s).
6. `WINDOW_MISSED`: t_lf가 측정기 취소 전송 `/clock` 이하(제외). 3단계에서 대역이 미확정이었으면 그 사유(예: `RAMP_MISMATCH`의 근거 시각)를 사유에 함께 남기고 제외를 유지한다.
7. 대역 미확정 회의 판정 불가(INCONCLUSIVE, 2).
8. 대역별 결과(PASS, 경계의 `HOLD_END`).

그래서 대역이 정해진 회의 기준과 다른 관측(1)은 Hold 뒤 관찰이 모자라도 올라가고, 관찰이 모자라 판정하지 않는 것은 그런 관측이 없는 회뿐이다. 일관성 검사와 landed 복귀는 창 밖 회에도 본다. 첫 disarm이 유실된 회는 대응하는 ack가 없으므로 수락 여부를 보지 않는다.

`M5_INCONSISTENT`(1): 첫 disarm에 대응한 ack의 수락 여부가 처리 시각 앞 12 ms 구간 `[t_p - 12 ms, t_p]`의 `vehicle_land_detected` 상태와 맞지 않음. 구간 직전(시작 시각 이하) 마지막 표본의 값이 구간 시작 상태이고 구간 안의 표본이 이어진다. ACCEPTED인데 구간 내내 `landed`와 `maybe_landed`가 모두 false였거나, TEMPORARILY_REJECTED인데 구간 내내 둘 중 하나가 true였으면 맞지 않는 것이다. `maybe_landed`가 처음 false가 된 시각(t_ml) 하나와 견주지 않으며 t_ml과 t_p - t_ml은 기록만 한다. 구간 안에서 두 분류 사이로 값이 바뀐 회(예: `maybe_landed`가 false로 갔다가 true로 돌아옴)는 어느 결과도 불일치가 아니다. 거부 때의 `Disarming denied: not landed` logged message는 판정에 쓰지 않고 유무와 t_p와의 시각 차이(`log_denied_dt_us`)만 기록한다.

대역별 결과:

- spoolup, 내부: 분기 전환 없이 지상 DISARMED이고 r_p가 ACCEPTED이며 기존 기준을 만족하면 PASS. 어긋나면 `M5_CONTRADICTED`(1): 첫 disarm이 이 두 대역에서 처리되었는데 r_p가 ACCEPTED가 아니거나 공중 분기(Hold로 끝남, 지상 -> 공중 -> 지상 포함)로 간 회. `M5_CONTRADICTED`는 대역 문장이 반증된 것이고, `M5_INCONSISTENT`는 PX4의 disarm 수락 규칙과 ULog의 상태가 맞지 않는 것이다.
- 경계: r_p가 ACCEPTED이고 분기 전환 없이 지상 DISARMED로 끝날 때만 PASS. `landed`가 false가 된 뒤 true로 돌아와 지상 DISARMED로 끝난 회(공중 -> 지상 복귀, 첫 disarm이 거부된 뒤 재전송이 받아들여진 회)와 r_p가 ACCEPTED가 아닌데 지상 DISARMED로 끝난 회는 `M5_CONTRADICTED`(1)이다. 판별은 ROS(분기 순서에 A, 전환 횟수)와 ULog(t_lf 뒤 DISARMED 전의 `landed` true 표본) 둘 다 쓴다. Hold로 끝나면 `HOLD_END`(2)이고 기계가 통과로 올리지 않는다. 그런 회가 있으면 종료 코드는 0이 아니고 architect가 ULog의 선후 기록으로 판정한다. 판정 입력으로 r_p, t_p - t_ml, 구간의 상태 목록(`ld_states_before_tp`), logged message 유무와 시각 차이, ld_p의 네 필드(`landed`, `maybe_landed`, `ground_contact`, `in_ground_effect`), t_p 시각의 추력을 `bands_item3.json`에 기록한다.
- 창과 무관한 기준(OFFBOARD가 아닌 ARMED 0개, 정리 총 소요 9 s 미만, 상승 0.2 m 이하, 표의 종료)과 `measure.py` 단독 판정 함수는 그대로다.

`measure.py` 단독 verdict는 ROS 표본이 근거인 잠정 판정이다. (3)의 대역과 최종 verdict는 `crosscheck.py` 뒤에만 정해진다(`summary_item3.txt` 맨 위의 대역 충족 여부 절과 끝의 최종 판정 절, `final_summary.json`).

집계(`final_summary.json`의 `3.bands`와 요약 맨 위): 실제 대역별, 계획 지연값별 n, 유효(PASS, FAIL, M3_CONTRADICTED, M5_CONTRADICTED, M5_INCONSISTENT와 경계의 HOLD_END), PASS, 제외, 공중 분기 회수(ROS 분기 순서, 전환, ULog `landed` 복귀). 최소 유효 시도는 spoolup 6, 내부 10, 경계 4이고 spoolup과 내부는 계획한 지연값이 계획한 대역으로 분류된 유효 시도가 지연값마다 2 이상이어야 한다. `enough`는 이 최소치만 본다. 종료 코드 2는 PASS가 아닌 행(경계의 HOLD_END 포함)에서 나온다. 요약에 "경계 유효 n회(최소 4 충족), HOLD_END n회는 architect 판정 대기"가 따로 적힌다. 경계의 유효 시도가 1회 이상이고 공중 분기가 0회일 때만 "경계에서 공중 분기는 생기지 않았다(M5의 경계 문장이 실측으로 받쳐진 것은 아니다)"가 적히고, 경계 시도가 0회면 이 문장을 적지 않는다. 무실패일 때 실패율 95% 상한은 27회가 아니라 대역별 유효 시도 수로 적는다. 지연값별로 t_p - t_A, t_ramp - t_A, t_lf - t_A, 대역, r_p, first_disarm_lost가 표로 남고, 첫 disarm과 `landed` false의 부호 있는 간격은 t_p - t_lf로 잰다.

실행 시간: 보통 약 7분, 최악 약 22분으로 추정한다(최악은 Hold로 끝난 회마다 60 s 관찰이 붙는 경우). 측정하지 않은 추정이다.

## 종료 코드와 verdict

- 0: 모든 시도 PASS이고 시도 수 충분.
- 1: 기준과 다른 관측(verdict `FAIL`, `M3_CONTRADICTED`, (3)의 `M5_CONTRADICTED`와 `M5_INCONSISTENT`, ARMED 위반(어느 부류든)). 문서의 기대가 반증됐다는 뜻이며 PX4 결함이라는 뜻이 아니다. 2보다 앞선다. `M3_CONTRADICTED`는 2b에서 `landed`가 true에 닿은 경우로, M3 문장과 다른 관측이라 architect에게 올린다(그 회의 disarm 수락과 고도 변화는 facts에 기록한다).
- 2: 기계가 판정하지 않음. `COND_NOT_REACHED`(2b에서 `landed`가 true에 닿지 못함), `HOLD_END`((3)이 Hold로 끝남), `INCONCLUSIVE`(관찰 구간 60 s 미만이거나 관찰 구간의 표본이 모자람, 값이 없어 판정할 수 없음, (5)의 arm 수락 증거 미확인), `WINDOW_MISSED`, `PRECONDITION`, `ERROR`, `CLOCK_STALLED`, 시도 수 부족, 인프라, 처리하지 못한 예외.

시도 수(유효 시도)는 기준에 대한 판정이 있는 verdict(`PASS`, `FAIL`, `M3_CONTRADICTED`, `M5_CONTRADICTED`, `M5_INCONSISTENT`)만 센다. `INCONCLUSIVE`, `COND_NOT_REACHED`, `HOLD_END`, `WINDOW_MISSED`, `PRECONDITION` 등은 세지 않는다. 항목별 최소 PASS 횟수는 2b 3회, (5)와 `armed` 10회다. (3)은 대역별 최소 유효 시도(위)로 본다. 경계의 Hold 종료는 유효 시도로 세지만 PASS가 아니므로 종료 코드는 2다.

관찰 판정(2b의 `COND_NOT_REACHED`, (3)의 `HOLD_END`)은 표본 조건을 같이 본다. 관찰 구간(실제 sim 길이) 60 s 이상, 구간 안 `vehicle_status` 표본이 초당 1개 이상, `vehicle_land_detected`가 초당 0.5개 이상, 마지막 표본이 관찰 끝에서 각각 1 s, 2 s 이내여야 하고, 이웃한 표본 사이의 최대 간격(관찰 시작 가장자리 포함. 시작 직전 마지막 표본이 있으면 구간 안으로 세어 잰다)이 `vehicle_status` 2.0 s, `vehicle_land_detected` 4.0 s 이하여야 한다. 간격은 PX4 timestamp 기준과 ROS 수신 시각 기준을 둘 다 행에 남기고 긴 쪽으로 판정한다. 못 채우면 `INCONCLUSIVE`다. 상수의 근거는 PX4 v1.17.0 SITL의 trial4/5 ULog 실측(중앙값 504 ms/1000 ms, 최대 508/1004 ms)이고 PX4 버전을 올리면 다시 확인한다. 표본이 없는 관찰을 "상태 유지"로 읽지 않기 위한 조건이다.

최종 verdict가 PASS도 제외도 아닌 행이 하나라도 있으면(INCONCLUSIVE, HOLD_END, ERROR, CLOCK_STALLED, PRECONDITION 등) PASS 횟수를 채워도 종료 코드 0이 아니라 2다(FAIL이나 `M3_CONTRADICTED`가 있으면 1이 앞선다).

자극이 성립하지 않은 회는 유효 시도에도 not-pass 집계에도 넣지 않는다. 행과 횟수는 기록하고 요약과 `final_summary.json`(`n_excluded`, (5)는 지연값별)에 따로 적는다. 종료 코드는 나머지 행으로 정한다(유효 PASS가 최소 횟수 이상이고 다른 행이 없으면 0, 유효 시도가 모자라면 2).
- (3)의 `WINDOW_MISSED`: 취소 시점에 `landed`가 이미 false였던 회(`measure.py` 단독은 ROS 표본으로, 최종 판정은 ULog의 t_lf가 취소 전송 `/clock` 이하인 것으로 정한다). 창과 무관한 기준은 전부 적용한다(`OFFBOARD`가 아닌 ARMED 0개, 정리 총 소요 9 s 미만, 상승 0.2 m 이하, TIMEOUT_GROUND/TIMEOUT_HOLD/LIMIT/DISARMED_AIR는 FAIL, 지상 종료면 끝난 뒤 ARMED 없음과 마지막 DISARMED, Hold 종료면 60 s M3 상태와 표본 조건). 위반이 있으면 FAIL(1), Hold 종료의 관찰 표본이 모자라면 INCONCLUSIVE(2), 모두 만족하면 `WINDOW_MISSED`다. DISARMED 종료는 요구하지 않는다. 요약에 끝난 방식별 횟수와 회별 취소 시 높이가 적힌다.
- (5)의 `ARM_NOT_ACCEPTED`: `crosscheck.py`의 최종 판정(ULog 교차 확인 뒤)에서도 arm 수락 증거가 없는 회. `measure.py` 단독의 "증거 미확인"(`INCONCLUSIVE`)은 여전히 2이고, 빼는 것은 최종 판정 단계에서만이다.
- 그 회에서 기준과 다른 관측(OFFBOARD가 아닌 ARMED 표본 등)이 나오면 빼지 않고 FAIL(종료 코드 1)이다. 다른 INCONCLUSIVE(관찰 표본 부족, 값 없음)와 `PRECONDITION`은 제외 대상이 아니다.
- 시도 수는 실행 전에 정한다. 결과를 보고 시도를 더하지 않는다(유효 시도가 모자라면 2이고 새 실행이다).

`item2`는 2b가 PASS일 수 없어(`COND_NOT_REACHED` 또는 `M3_CONTRADICTED`) 종료 코드 0이 나오지 않는다. (2)의 통과는 architect가 (가) 3/3을 보고 판정한다. 요약과 `final_summary.json`에 "(가) 미도달 n회, (나) M3_CONTRADICTED n회"가 따로 적힌다.

ARMED 기준은 ARMED 3회 확인까지 간 실행이 10회 이상이어야 `enough`다. (5)는 취소가 빨라 ARMED 3회에 가지 못하고, (3)도 지연이 짧은 회(spoolup)는 가지 못한다. 지연이 1 s 이상인 회는 ARMED 3회에 닿을 수 있지만 몇 회가 닿는지는 측정하지 않은 값이다. 그래서 `armed` 항목 없이 item 하나만 돌리면 종료 코드 0이 되리라고 기대하지 않는다(`item5`만이면 도달 0). 0을 보려면 `armed`(또는 `all`)를 함께 돌린다.

최종 종료 코드는 `crosscheck.py`를 따른다. `run_measure.sh`의 종료 코드는 `measure.py`가 1을 낸 항목이 있으면 1, 아니면 `crosscheck.py`의 값이다. `crosscheck.py`가 ULog 증거로 확정한 최종 판정((5)의 증거 미확인 INCONCLUSIVE -> PASS. 값이 없어서 INCONCLUSIVE인 행은 승격하지 않는다), 최종 판정 기준의 유효 시도 수와 PASS 횟수(전체와 (5)의 지연값별, `final_summary.json`), commit과 image key, 요청한 item마다의 행과 `measure.py` 완료 기록(`done_<item>.json`)을 다시 평가한다. `run_measure.sh`가 요청 item 목록을 `--items`로 넘기므로 `measure.py`가 기록을 만들기 전에 죽은 item은 2다. `crosscheck.py`의 산출 파일이 이미 있으면 `--force` 없이는 덮어쓰지 않고 거부한다(종료 코드 2).

이 판 이전의 기록(`inconclusive_kind` 등 필요한 키가 없는 행)에 `crosscheck.py`를 돌리면 사유를 출력하고 종료 코드 2로 끝난다.

## 구조

| 파일 | 역할 |
| --- | --- |
| `run_measure.sh` | 호스트. 스택 올리기, runner에서 `measure.py` 실행, 스택 멈추기, ULog 교차 확인, 내리기 |
| `measure.py` | runner 안. 시도를 돌리고 시도마다 판정 |
| `crosscheck.py` | 호스트. 기록을 ULog의 `vehicle_status`와 대조하고 (5)의 arm 수락 증거를 확정하고 ARMED 기준을 부류별로 합산 |
| `tests/support/measure_judge.py` | 판정 로직(순수 코드)과 정리 모델 `CleanupModel`. 단위 테스트 `test_measure_judge.py` |
| `tests/support/measure_check.py` | ULog 대조, ARMED 합산, 종료 코드 집계(순수 코드). 단위 테스트 `test_measure_check.py` |
| `tests/support/measure_bands.py` | (3)의 대역 판별, ULog 분석, 최종 verdict, 대역별 집계(순수 코드). 단위 테스트 `test_measure_bands.py`, 인자 검증 `test_measure_args.py` |
| `tests/support/px4_raw.py` | KEEP_ALL 구독 기록기(구독 전용) |
| `tests/support/px4_measure_pub.py` | 측정 전용 발행자(`measure_only=True` 필수). 시나리오는 가져가지 않는다 |
| `tests/support/ulog_min.py` | ULog에서 고른 토픽(`read_topics`는 여러 토픽을 한 번에)과 logged message를 읽는 최소 parser(이미지에 pyulog가 없다) |

### 정리 모델이 흉내 내는 것

`CleanupModel`은 decisions.md M3, M5, M6의 일부만 옮긴 측정용 모델이고 core를 호출하지 않는다.

- 흉내 내는 것: 매 step 최신 `landed`로 지상(G)/공중(A) 분기를 다시 고름, 분기에 들어갈 때마다(G -> A -> G 포함) timeout 기준 시각과 확인 계수와 첫 전송 기준을 새로 잡고 명령을 새로 보냄, 지상은 강제가 아닌 disarm 재전송과 DISARMED 3회 연속, 공중은 Hold 재전송과 AUTO_LOITER 첫 관측에서 발행 중단 후 3회 연속에서 종료, 분기 timeout과 전체 상한 12 s, M6의 한 step 순서(공중 DISARMED, 정리할 것 없음, 상한, 분기 실행).
- 흉내 내지 않는 것: 상태 끊김(LINK_LOST), ack 거부 때의 Land 경로, Hold 실패 뒤 공중 재진입, 상한 tick에서의 reason과 명령 선택, 식별 불일치 종료. 입력은 tick이 아니라 약 2 ms polling이다.
- 그래서 근거 범위는 PX4 쪽 사실(명령 수락 여부, 표본 순서와 지연, `landed` 전환, 상승)이다. 정리 총 소요 9 s 기준은 이 모델의 소요이고 core의 소요를 보증하지 않는다.
- 모델의 timeout 상수 3, 3, 12, 0.5 s는 `idsim_mission` 노드 파라미터 기본값(`core/config.hpp`)의 사본이다. 자동으로 동기화되지 않는다.

## 기록

`artifacts/runs/<실행 id>/measure/` 아래.

- `measure_<item>.jsonl` 시도마다 한 줄. 필드: `run_id`, `commit`, `dirty`, `images`, `image_keys`, `attempt`, `item`(2a, 2b, 3, 5, armed), `class`(px4_direct), `args`(실행 인자), `injection`(조건과 trigger, (5)는 명목 지연과 실제 지연), `verdict`/`result`, `reasons`, `ros_start_us`, `ros_end_us`, `ros_elapsed_s`, `wall_elapsed_s`, `exit_code`(0 PASS, 1 FAIL, 2 그 밖), `ulog`, `facts`. 측정되지 않은 값은 0이나 false가 아니라 `null`이다. `facts`에는 이 시도의 arm 전송 횟수(`arm_sends`)와 `armed` 항목의 `stop_arm_resend_after_first_armed` 값도 남는다.
- `raw_<item>.jsonl` 시도마다 `vehicle_status`(`timestamp`, 받은 ROS 시각, 같은 시점의 `/clock`, `arming_state`, `nav_state`, `failsafe`, `nav_state_user_intention`), `vehicle_land_detected`, 위치, ack(`timestamp`, `result`, `result_param1/2`, `from_external`, `target_component` 포함), 명령 전송의 원시 표본. 구독은 BEST_EFFORT이므로 "하나도 버리지 않는다"는 노드가 받은 표본에 대해서만 참이다. 전송 중 유실은 `crosscheck.py`의 ULog 대조(`ulog_only`)로 본다.
- `summary_<item>.txt` 머리에 판정 뜻, 보증 범위, 실행 인자, 통과 기준(실행 전에 기록), 아래에 결과와 항목별 요약(2b 회별 결과, 분기 순서별 회수, (5)의 ARMED 표본과 지연값별 유효 시도).
- `distribution_<item>.json` 모든 `vehicle_status` 표본의 `timestamp - 받은 ROS 시각`, `timestamp - /clock`의 부호 있는 분포와, 명령 전송 뒤 처음 받은 표본의 `timestamp - Px4Timestamp` 분포.
- `done_<item>.json` `measure.py`가 끝까지 돈 기록(없으면 `crosscheck.py`가 2).
- `final_summary.json` 최종 판정 기준의 항목별 시도 수, 유효 시도 수, PASS 횟수, 지연값별 집계. (3)은 `3.bands`에 실제 대역별 집계가 들어 있다.
- `bands_item3.json` (3)의 시도마다 ULog 분석(t_A, t_ramp, t_ml, t_lf, t_p, r_p, ld_p, 대역, 일관성과 t_ramp 교차 확인의 사유, 판정 입력, 최종 verdict와 사유)과 대역별 집계. 이 파일이 이미 있으면 `crosscheck.py`는 `--force` 없이 덮어쓰지 않는다.
- `crosscheck_<item>.json`, `armed_criterion.json` ULog 교차 확인과 ARMED 기준의 부류별 합산(`classes`: `px4_direct`, `scenario_a`). `armed` 항목은 ARMED 3회 확인부터 NAV_LAND 전송까지의 구간도 ULog로 대조한다. ULog를 못 읽은 행이나 측정되지 않은 행이 있으면 `passed`는 false다. 출력에 ULog 안 `Armed by external command` 줄 총수가 있다.
- `stop_exit.txt` `compose stop -t 15` 뒤 서비스별 종료 코드(px4의 137은 KILL, ULog가 닫히지 않았을 수 있다).

상승(`climb_m`)의 기준인 지상 높이는 arm 직전 1 s의 `vehicle_local_position` z 중앙값이다(z 잡음이 0.1 m 수준이라 한 표본이면 0.2 m 기준의 여유가 줄어서). 표본 수는 `facts.ref_z_samples`에 남고 5개 미만이면 `PRECONDITION`이다.

## 규칙

- 실패한 시도를 기록에서 빼지 않고 재시도하지 않는다. 판정을 느슨하게 바꾸지 않는다.
- timeout과 지연은 `/clock` 기준이다. 벽시계는 `/clock`이 멈췄는지 보는 데만 쓴다.
- trigger는 sleep이 아니라 표본 이벤트다(첫 ARMED 표본, `landed` 표본, Hold 관측). 예외는 주입 지연 둘이다. (5)는 arm 전송 뒤 sim 시간 0-0.2 s이고, (3)은 첫 ARMED 표본의 PX4 `timestamp` 뒤 고정 목록의 sim 시간(0-1.724 s)이다. 둘 다 `/clock`으로 재는 입력 변수이며 명목 값과 실제 값을 기록한다. 벽시계 sleep으로 지연을 만들지 않는다.
- 10회 중 0건은 실패율의 95% 상한이 약 26%라는 뜻이다(3/n 근사로는 30%). 3회 중 0건은 약 63%다(3/n 근사로는 100%). 정확한 값은 1 - 0.05^(1/n)이다. "10/10 통과"를 "플래키 없음"으로 쓰지 않는다.
- 정리 총 소요 9 s 미만을 넘는 실행이 있으면 상한을 올리지 않고 architect에게 올린다.
- (5)의 arm 수락 증거는 ROS ack가 아니다(arm과 disarm이 같은 command 400이고 ack에 원 명령 필드가 없다). 증거 A는 arm 전송 뒤 timestamp의 ARMED 표본(ROS 또는 ULog), 증거 B는 ULog의 `[commander] Armed by external command`다. 최종 PASS는 `crosscheck.py` 뒤에만 선언한다.
