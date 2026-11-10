# 표적 하나의 상태. 시뮬레이터 비의존. 토픽 /targets/<target_id>/state
# 소실 플래그는 없다. 소실은 발행 중단으로 표현하고 소비자가 stamp의 나이로 판정한다.
string TOPIC_PREFIX = "/targets"
string TOPIC_SUFFIX = "state"
string FRAME_ID = "world"

std_msgs/Header header          # stamp: 이 상태가 유효한 시각(발행 시각이 아니다). frame_id: FRAME_ID
string target_id                # ^[a-z][a-z0-9_]{0,31}$. 토픽의 <target_id>와 같다
geometry_msgs/Point position    # world ENU, m
bool velocity_valid             # 언제든 false일 수 있다. false면 velocity는 0
geometry_msgs/Vector3 velocity  # world ENU, m/s
