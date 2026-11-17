# 기체 요약 상태. Telemetry Collector가 기체마다 발행한다. 토픽 /<vehicle_id>/vehicle_state
# 발행자는 vehicle_status와의 식별 대조가 맞고 vehicle_status가 신선한 동안에만 발행한다.
# NaN과 무한대는 어떤 필드에도 넣지 않는다. 값이 없으면 *_valid가 false이고 값은 0이다.
# 위치, 자세, 측지 좌표, 배터리, 지상 판정의 원천이 신선도 임계보다 묵어도 해당 *_valid는 false이고 값은 0이다.
# 발행 중단은 vehicle_status만 본다.
string TOPIC_NAME = "vehicle_state"
string FRAME_ID = "world"

uint8 ARMING_UNKNOWN = 0
uint8 ARMING_DISARMED = 1
uint8 ARMING_ARMED = 2

uint8 MODE_UNKNOWN = 0
uint8 MODE_MANUAL = 1        # 조종사 입력 계열 전부
uint8 MODE_HOLD = 2          # 비행제어의 Hold 모드. MissionItem.TYPE_LOITER와 다른 것이다
uint8 MODE_OFFBOARD = 3
uint8 MODE_TAKEOFF = 4
uint8 MODE_LAND = 5
uint8 MODE_RTL = 6
uint8 MODE_AUTO_OTHER = 7    # 위에 없는 자동 모드
uint8 MODE_TERMINATION = 8   # 비행 종료
uint8 MODE_OTHER = 255       # 변환표에 없는 값

uint32 WARN_LOCAL_POSITION_INVALID = 1
uint32 WARN_GLOBAL_POSITION_INVALID = 2
uint32 WARN_BATTERY_LOW = 4
uint32 WARN_BATTERY_CRITICAL = 8
uint32 WARN_OFFBOARD_SIGNAL_LOST = 16
uint32 WARN_PREFLIGHT_CHECK_FAILED = 32

std_msgs/Header header         # stamp: 이 메시지를 만든 시각. frame_id: FRAME_ID
string vehicle_id              # 기체 네임스페이스에서 앞의 "/"를 뗀 값. 토픽 네임스페이스와 같다
uint8 system_id                # vehicle_status와의 대조를 통과한 MAVLink system id. 표시와 진단용

uint8 arming_state             # ARMING_*
uint8 flight_mode              # MODE_*. 비행제어의 실제 모드
bool failsafe                  # 비행제어가 failsafe 동작 중
uint32 warnings                # WARN_* 비트의 OR

bool landed_valid
bool landed                    # 지상 판정

bool position_valid            # false면 position은 0
# world ENU, m. z는 world.origin의 접평면 위 높이이고 타원체 고도 AMSL도 아니다.
# 원점에서 수평으로 멀어질수록 같은 z의 점이 타원체 위로 높아지므로 지면 위 높이로 읽을 수 있는 곳은 원점 근처뿐이다.
geometry_msgs/Point position
bool yaw_valid
float64 yaw_rad                # world ENU yaw, [-pi, pi)
bool velocity_valid
geometry_msgs/Vector3 velocity # world ENU, m/s

bool geodetic_valid
float64 latitude_deg           # WGS84
float64 longitude_deg
# m. PX4가 내는 AMSL 고도이고 geoid 보정을 하지 않는다. SITL에서는 타원체 고와 같은 수다. 지도 표시용.
float64 altitude_amsl_m

bool battery_valid
float32 battery_remaining      # 0.0-1.0
