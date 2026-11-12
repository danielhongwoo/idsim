# Offboard position setpoint로 상승한다. 지상 상태에서만 시작할 수 있다.
# 기준 위치는 준비 단계에서 setpoint 발행을 시작할 때(arm 전, 지상) 읽은 위치다.
float64 height_m       # 기준 위치에서 올라갈 상대 높이(m). 0보다 크다
float64 acceptance_m   # 수직 허용 오차(m). 0보다 크다
YawSetpoint yaw
