# 미션 항목 하나. type에 맞는 서브메시지 하나만 채우고 나머지는 기본값으로 둔다. RTL과 LAND는 서브메시지가 없다.
uint8 TYPE_TAKEOFF = 1
uint8 TYPE_GOTO = 2
uint8 TYPE_TRACK_ENTITY = 3
uint8 TYPE_LOITER = 4
uint8 TYPE_RTL = 5
uint8 TYPE_LAND = 6

uint8 type                           # TYPE_*. 0은 무효
builtin_interfaces/Duration timeout  # 이 항목의 제한 시간(sim 시간). 0보다 크다
TakeoffItem takeoff                  # type == TYPE_TAKEOFF일 때만
GoToItem go_to                       # type == TYPE_GOTO일 때만
TrackEntityItem track_entity         # type == TYPE_TRACK_ENTITY일 때만
LoiterItem loiter                    # type == TYPE_LOITER일 때만
