# 항목 실행 중의 yaw 지정
# MODE_KEEP의 기준 yaw: 직전 setpoint의 yaw다. 직전 setpoint가 없으면(첫 항목인 TAKEOFF와 공중 Offboard 진입의 첫 항목)
# 준비 단계에서 setpoint 발행을 시작할 때 읽은 heading이다.
uint8 MODE_KEEP = 1    # 항목의 기준 yaw를 유지
uint8 MODE_FIXED = 2   # yaw_rad로

uint8 mode             # MODE_*. 0은 무효
float64 yaw_rad        # world ENU yaw, [-pi, pi). MODE_FIXED일 때만. 아니면 0
