# 항목 실행 중의 yaw 지정
uint8 MODE_KEEP = 1    # 항목 시작 때의 yaw 유지
uint8 MODE_FIXED = 2   # yaw_rad로

uint8 mode             # MODE_*. 0은 무효
float64 yaw_rad        # world ENU yaw, [-pi, pi). MODE_FIXED일 때만. 아니면 0
