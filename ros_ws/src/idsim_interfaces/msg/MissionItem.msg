# 미션 항목 하나. type에 맞는 서브메시지 하나만 채우고 나머지는 기본값으로 둔다. RTL과 LAND는 서브메시지가 없다.
# 항목은 두 부류다. setpoint 항목(TAKEOFF, GOTO, TRACK_ENTITY, LOITER)은 Offboard setpoint로 처리하고, 모드 명령 항목(RTL, LAND)은
# 비행제어의 고유 모드로 전환한다. 이 구분은 type에서 파생한다.
# 순서 규칙: TAKEOFF는 첫 항목에만, LAND와 RTL은 마지막 항목에만 온다. 모드 명령 항목 뒤에 setpoint 항목이 오지 않는다.
# 항목의 시작 시각(timeout의 기준)은 앞 항목이 완료된 tick이고, 첫 항목은 준비 단계가 끝나는 때다(docs/interface.md).
uint8 TYPE_TAKEOFF = 1
uint8 TYPE_GOTO = 2
uint8 TYPE_TRACK_ENTITY = 3
uint8 TYPE_LOITER = 4
uint8 TYPE_RTL = 5
uint8 TYPE_LAND = 6

uint8 type                           # TYPE_*. 0은 무효
builtin_interfaces/Duration timeout  # 이 항목의 제한 시간(ROS 시각, use_sim_time이면 /clock). 0보다 크다
TakeoffItem takeoff                  # type == TYPE_TAKEOFF일 때만
GoToItem go_to                       # type == TYPE_GOTO일 때만
TrackEntityItem track_entity         # type == TYPE_TRACK_ENTITY일 때만
LoiterItem loiter                    # type == TYPE_LOITER일 때만
