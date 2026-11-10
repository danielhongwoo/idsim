# 미션 실행의 접수와 종료 기록. Mission Executor가 goal마다 두 번 발행한다. 토픽 /<vehicle_id>/mission_event
# 정본은 action(GoalStatus와 result)이고 이 메시지는 기록과 관찰을 위한 사본이다.
# 종료 사건 없이 접수만 남을 수 있다(Executor가 실행 중에 죽은 경우). 읽는 쪽은 결과 미상으로 다룬다.
string TOPIC_NAME = "mission_event"

uint8 STATUS_UNKNOWN = 0
uint8 STATUS_ACCEPTED = 1    # goal 접수. action_msgs/GoalStatus의 같은 이름과 같은 값
uint8 STATUS_SUCCEEDED = 4
uint8 STATUS_CANCELED = 5
uint8 STATUS_ABORTED = 6

builtin_interfaces/Time stamp   # 이 사건이 일어난 시각. Executor 노드 clock의 ROS 시각(use_sim_time이면 /clock)이고 벽시계가 아니다
string vehicle_id               # 발행한 Executor의 vehicle_id. 토픽 네임스페이스와 같다
string mission_id               # goal에 적힌 값 그대로. 검증에 실패한 값일 수 있다
uint8[16] goal_id               # action goal의 UUID. _action/status, _action/feedback의 goal_id와 같다
uint8 status                    # STATUS_*
uint8 reason                    # ExecuteMission 결과의 REASON_*. 접수 때는 REASON_NONE
uint32 item_count               # goal의 항목 수
uint32 items_completed          # 접수 때는 0. 종료 때는 result와 같다
uint32 last_item_index          # 접수 때는 0. 종료 때는 result와 같다
string detail                   # 접수 때는 빈 문자열. 종료 때는 result와 같다
