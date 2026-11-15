# world 좌표의 한 점으로 이동한다. position을 기체 로컬 NED로 바꿔 Offboard position setpoint로 보낸다.
# position의 각 성분은 절댓값 1e5 m 이하다(어기면 INVALID_MISSION).
# 완료: 서로 다른 위치 표본 3개 연속에서 위치가 유효하고 3차원 거리가 acceptance_radius_m보다 작다.
# acceptance_radius_m에 하한은 없다. 위치 분해능보다 작은 반경은 완료하지 못하고 ITEM_TIMEOUT으로 끝날 수 있다(거짓 완료는 없다).
# MODE_KEEP의 기준 yaw는 직전 setpoint의 yaw다.
geometry_msgs/Point position   # world ENU, m
float64 acceptance_radius_m    # 3차원 거리 허용 오차. 0보다 크다
YawSetpoint yaw
