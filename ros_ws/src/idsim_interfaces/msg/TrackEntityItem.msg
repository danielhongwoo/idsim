# 표적 위치에 offset을 더한 점을 setpoint로 추종한다. 표적 표본이 신선하고 속도가 유효하면 표적 속도를 같은 setpoint에
# feedforward로 싣는다. offset의 각 성분은 절댓값 1e5 m 이하이고 0 벡터가 아니다(어기면 INVALID_MISSION).
# 표적이 실제로 있는지는 검사하지 않는다. 항목 시작 뒤 정해진 시간(target_timeout) 안에 유효 표본이 없으면 REASON_TARGET_LOST다.
# 완료: GOTO와 같은 거리 조건. 그 tick의 표적 표본이 신선할 때만 센다.
string target_id               # TargetState.target_id
geometry_msgs/Vector3 offset   # world ENU, m. 표적 위치에 더한 점이 setpoint다. 0 벡터는 검증에서 거부한다
float64 acceptance_radius_m    # setpoint 점까지 이 거리 안에 들면 항목 완료. 0보다 크다
YawSetpoint yaw
