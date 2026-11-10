# 표적 위치에 offset을 더한 점을 setpoint로 추종한다.
string target_id               # TargetState.target_id
geometry_msgs/Vector3 offset   # world ENU, m. 표적 위치에 더한 점이 setpoint다. 0 벡터는 검증에서 거부한다
float64 acceptance_radius_m    # setpoint 점까지 이 거리 안에 들면 항목 완료. 0보다 크다
YawSetpoint yaw
