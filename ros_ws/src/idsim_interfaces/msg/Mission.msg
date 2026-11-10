# 기체 하나가 순서대로 실행하는 미션. ExecuteMission action의 goal에 실린다. action 이름 /<vehicle_id>/execute_mission
string ACTION_NAME = "execute_mission"

string mission_id      # ^[a-z0-9][a-z0-9_-]{0,63}$
MissionItem[] items    # 1개 이상. 순서대로 실행한다
