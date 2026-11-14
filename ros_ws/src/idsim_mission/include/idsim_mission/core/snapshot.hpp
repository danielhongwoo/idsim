// Copyright 2026 Daniel Hongwoo Lee
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// core와 PX4 어댑터(px4/ 디렉터리) 사이의 경계. 소유는 ros2-engineer이고 변경은 px4-engineer가
// 필수 승인자다(docs-for-agent/file-ownership.md "idsim_mission의 승인 규칙").
//
// 이 헤더의 타입은 PX4 중립이다. PX4 enum 값의 해석(nav_state, arming_state, ack result, EKF 준비
// 술어)은 어댑터만 한다. core는 px4_msgs를 include하지 않는다.
//
// 입력 모델(decisions.md 쟁점 6 C1)
// - 노드는 tick마다(20 Hz, 노드 시계 timer) core의 step()을 한 번 부른다. 입력은 tick 번호, 그
//   tick의 ROS 시각, 아래 Snapshot, Px4ClockPort다. 출력은 StepOutput(mission_runner.hpp)이다.
// - 구독 callback은 토픽마다 최신 표본 하나만 저장한다(덮어쓴다). 그래서 tick당 토픽마다 표본은
//   최대 1개이고, 같은 표본이 다음 tick에 다시 보일 수 있다. core는 vehicle_status의 timestamp로
//   같은 표본을 가른다.
// - received_tick의 정의: 표본을 처음 볼 수 있는 step()의 tick 번호. 노드는 "다음에 부를 step의
//   tick 번호"를 하나 두고, callback은 그 값을 표본에 적고, timer는 그 번호로 step을 부른 뒤 번호를
//   1 올린다. 그러면 step k에서 낸 명령에 대한 응답 표본은 received_tick > k다("전송 tick 뒤에
//   받은"의 정의. decisions.md 쟁점 3 M5).
// - Snapshot의 optional은 "한 번도 받지 못함"이다. 한 번 받은 뒤에는 비우지 않는다(끊김은
//   received_ns로 core가 판정한다).
//
// 어댑터(P3c)가 채울 것. 왼쪽이 이 헤더의 필드, 오른쪽이 px4_msgs 필드다.
// - StatusSample <- vehicle_status
//   - timestamp_us <- timestamp
//   - received_tick, received_ns <- callback이 적은 tick 번호와 노드 시계 ROS 시각(ns)
//   - identity <- idsim_common::verify(VehicleIdentity, msg)가 Match이면 kMatch, 아니면 kMismatch.
//     identity_detail에 기대값과 받은 system_id, component_id를 적는다(M2의 detail로 쓰인다).
//   - arming <- arming_state: ARMING_STATE_ARMED이면 kArmed, 그 밖은 kDisarmed
//   - nav <- nav_state, nav_user_intention <- nav_state_user_intention. 둘 다 같은 표로:
//     NAVIGATION_STATE_OFFBOARD -> kOffboard, NAVIGATION_STATE_AUTO_LOITER -> kHold,
//     NAVIGATION_STATE_AUTO_LAND -> kLand, NAVIGATION_STATE_AUTO_RTL -> kRtl, 그 밖 -> kOther
//   - failsafe <- failsafe
// - LandSample <- vehicle_land_detected: landed <- landed
// - PositionSample <- vehicle_local_position: x, y, z, heading 그대로(NED, m, rad),
//   timestamp_us <- timestamp(timestamp_sample이 아니다. core는 이 값으로 서로 다른 표본을 가른다),
//   xy_valid <- xy_valid, z_valid <- z_valid
// - FlagsSample <- failsafe_flags
//   - ekf_ready <- local_position_invalid, local_altitude_invalid, global_position_invalid,
//     home_position_invalid가 모두 false(decisions.md 쟁점 4 P2. 술어는 어댑터에 둔다)
//   - offboard_signal_lost <- offboard_control_signal_lost
// - AckSample <- vehicle_command_ack. ack의 target이 이 Executor의 source(system, component)와
//   같은 것만 넘긴다(아니면 버린다). command는 VEHICLE_CMD_DO_SET_MODE -> kSetMode,
//   VEHICLE_CMD_COMPONENT_ARM_DISARM -> kArmDisarm, VEHICLE_CMD_NAV_LAND -> kNavLand,
//   VEHICLE_CMD_NAV_RETURN_TO_LAUNCH -> kNavRtl, 그 밖 -> kOther. target 필터는 명령과 무관하게
//   같다(Navigator도 RTL 명령을 낼 수 있으므로 target이 다른 ack는 버린다).
//   result는 VEHICLE_CMD_RESULT_* 이름 그대로 대응(ACCEPTED, TEMPORARILY_REJECTED, DENIED,
//   UNSUPPORTED, FAILED, IN_PROGRESS, CANCELLED, 그 밖 kOther).
// - FramePort <- 그 tick의 Snapshot.position과 같은 vehicle_local_position 표본(노드가 callback의
//   최신 표본 하나에서 둘을 함께 만든다)의 ref_lat, ref_lon, ref_alt, xy_global, z_global과
//   params의 world.origin. 기준 유효 술어(xy_global과 z_global이 true, ref_lat, ref_lon, ref_alt가
//   유한, ref_alt가 정확히 0.0이 아님)는 기준을 읽는 px4 어댑터 함수에 둔다. 술어가 거짓이면
//   world_to_local은 nullopt다. 식은 idsim_common::geo::world_enu_to_local_ned(점)와
//   idsim_common::frames::enu_to_ned(벡터)다(decisions.md 쟁점 4).
// - Snapshot.targets는 PX4 메시지가 아니다. 노드(node/conversion.cpp)가 idsim_interfaces
//   TargetState의 유효 표본만 TargetSample로 바꿔 target_id별로 최신 하나를 둔다(decisions.md
//   쟁점 8의 유효 표본 규칙).
//
// 어댑터(와 노드)가 출력에 할 것. StepOutput의 명령과 setpoint는 같은 tick의 px4_timestamp_us를
// 실은 Px4Timestamp(Px4ClockPort가 그 tick에 돌려준 값을 만든 객체)로 만든다.
// - CommandKind -> idsim_common::VehicleCommandBuilder:
//   kSetModeOffboard -> set_mode_offboard, kSetModeHold -> set_mode_hold, kArm -> arm,
//   kDisarm -> disarm(강제가 아닌 disarm. 강제 disarm은 어디에서도 쓰지 않는다), kNavLand -> land,
//   kNavRtl -> rtl.
// - SetpointOut이 있으면 idsim_common::px4::offboard_position_mode와 position_setpoint를 하나씩
//   발행한다. 위치는 (x, y, z), yaw는 yaw_ned. kind가 kGround이면 z에 지상 setpoint 오프셋
//   +0.5 m(NED, 아래쪽. 어댑터 상수, decisions.md 쟁점 3 M5)를 더한다. core는 이 값을 모른다.
//   velocity_valid가 true이면 velocity(로컬 NED, m/s)를 trajectory_setpoint.velocity에 싣고,
//   false이면 velocity를 NaN으로 낸다(feedforward 없음. decisions.md 쟁점 8).
//   offboard_control_mode는 velocity_valid와 무관하게 position만 true다.
//   position_setpoint가 nullopt(비유한 값)를 돌려주면 그 tick은 발행하지 않고 오류 로그를 남긴다.
// - core는 "그 tick에 발행한다"만 말한다. 발행 중단은 SetpointOut이 없는 tick이다.

#ifndef IDSIM_MISSION__CORE__SNAPSHOT_HPP_
#define IDSIM_MISSION__CORE__SNAPSHOT_HPP_

#include <cstdint>
#include <map>
#include <optional>
#include <string>

#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

enum class NavMode : std::uint8_t
{
  kOffboard,
  kHold,  // PX4 AUTO_LOITER
  kLand,  // PX4 AUTO_LAND
  kRtl,   // PX4 AUTO_RTL
  kOther,
};

enum class Arming : std::uint8_t
{
  kDisarmed,
  kArmed,
};

enum class IdentityCheck : std::uint8_t
{
  kMatch,
  kMismatch,
};

struct StatusSample
{
  std::uint64_t timestamp_us{0};  // vehicle_status.timestamp(PX4 시각, us)
  std::uint64_t received_tick{0};
  std::int64_t received_ns{0};  // 수신 ROS 시각
  IdentityCheck identity{IdentityCheck::kMatch};
  std::string identity_detail;  // kMismatch일 때만
  Arming arming{Arming::kDisarmed};
  NavMode nav{NavMode::kOther};
  NavMode nav_user_intention{NavMode::kOther};
  bool failsafe{false};
};

struct LandSample
{
  bool landed{true};
  std::uint64_t received_tick{0};
};

struct PositionSample
{
  std::uint64_t timestamp_us{0};  // vehicle_local_position.timestamp(PX4 시각, us)
  double x{0.0};                  // 로컬 NED, m
  double y{0.0};
  double z{0.0};
  double heading{0.0};  // NED yaw, rad
  bool xy_valid{false};
  bool z_valid{false};
  std::uint64_t received_tick{0};
};

struct FlagsSample
{
  bool ekf_ready{false};
  bool offboard_signal_lost{true};
  std::uint64_t received_tick{0};
};

enum class AckCommand : std::uint8_t
{
  kSetMode,
  kArmDisarm,
  kNavLand,
  kNavRtl,
  kOther,
};

enum class AckResult : std::uint8_t
{
  kAccepted,
  kTemporarilyRejected,
  kDenied,
  kUnsupported,
  kFailed,
  kInProgress,
  kCancelled,
  kOther,
};

const char * ack_result_name(AckResult result);

// 거부인가. ACCEPTED와 IN_PROGRESS가 아니면 거부다.
bool is_rejection(AckResult result);

struct AckSample
{
  AckCommand command{AckCommand::kOther};
  AckResult result{AckResult::kAccepted};
  std::uint64_t received_tick{0};
};

// 표적 표본. PX4 메시지가 아니다. 노드가 유효 표본만 넣는다(target_id가 토픽 토큰과 같고,
// frame_id가 world, 값이 유한, stamp가 0이 아니고 직전 유효 표본보다 크다).
struct TargetSample
{
  Vec3 position;  // world ENU, m
  bool velocity_valid{false};
  Vec3 velocity;             // world ENU, m/s. velocity_valid일 때만 뜻이 있다
  std::int64_t stamp_ns{0};  // TargetState header.stamp(ROS 시각, ns). PX4 시각이 아니다
};

struct Snapshot
{
  std::optional<StatusSample> status;
  std::optional<LandSample> land;
  std::optional<PositionSample> position;
  std::optional<FlagsSample> flags;
  std::optional<AckSample> ack;
  // target_id -> 최신 유효 표본. 키가 없으면 "유효 표본을 한 번도 받지 못함"이다. 한 번 받은 뒤에는
  // 지우지 않는다(소실은 stamp_ns로 core가 판정한다).
  std::map<std::string, TargetSample> targets;
};

// world ENU -> 기체 로컬 NED 변환 port. 노드는 tick마다 Snapshot.position과 같은 표본의 기준으로
// 구현을 만든다(위 "어댑터가 채울 것"의 FramePort). 기준이 무효면 점 변환은 nullopt다. 벡터 변환은
// 기준에 의존하지 않는 축 치환(ENU -> NED)이라 늘 값이 있다.
class FramePort
{
public:
  FramePort() = default;
  FramePort(const FramePort &) = delete;
  FramePort & operator=(const FramePort &) = delete;
  FramePort(FramePort &&) = delete;
  FramePort & operator=(FramePort &&) = delete;
  virtual ~FramePort() = default;

  // world ENU 점(m) -> 로컬 NED 점(m). 기준이 무효면 nullopt.
  virtual std::optional<Vec3> world_to_local(const Vec3 & world_enu) const = 0;

  // world ENU 벡터(m/s) -> 로컬 NED 벡터(m/s).
  virtual Vec3 world_velocity_to_local(const Vec3 & world_enu) const = 0;
};

// Px4Timestamp 공급 port. 노드 구현은 idsim_common::Px4Timestamp::now(clock)를 부르고, 성공하면 그
// 객체를 이 tick의 출력용으로 보관한 뒤 microseconds()를 돌려준다. 실패하면 nullopt.
// core는 tick마다 많아야 한 번 부른다.
class Px4ClockPort
{
public:
  Px4ClockPort() = default;
  Px4ClockPort(const Px4ClockPort &) = delete;
  Px4ClockPort & operator=(const Px4ClockPort &) = delete;
  Px4ClockPort(Px4ClockPort &&) = delete;
  Px4ClockPort & operator=(Px4ClockPort &&) = delete;
  virtual ~Px4ClockPort() = default;

  virtual std::optional<std::uint64_t> now_us() = 0;
};

// core가 보내라고 하는 명령. 대응하는 빌더 메서드는 위 주석.
enum class CommandKind : std::uint8_t
{
  kSetModeOffboard,
  kSetModeHold,
  kArm,
  kDisarm,
  kNavLand,
  kNavRtl,
};

const char * command_name(CommandKind kind);

// 이 명령의 ack가 오는 command 묶음(DO_SET_MODE는 Offboard와 Hold가 같고, ARM_DISARM은 arm과
// disarm이 같다).
AckCommand ack_command_of(CommandKind kind);

enum class SetpointKind : std::uint8_t
{
  kTarget,  // 항목의 목표점. 그대로 발행한다
  kGround,  // 지상 setpoint. 어댑터가 z에 지상 오프셋을 더한다
};

struct SetpointOut
{
  SetpointKind kind{SetpointKind::kTarget};
  double x{0.0};  // 로컬 NED, m
  double y{0.0};
  double z{0.0};
  double yaw_ned{0.0};         // rad, [-pi, pi)
  bool velocity_valid{false};  // false이면 어댑터가 velocity를 NaN으로 낸다
  Vec3 velocity;               // 로컬 NED, m/s. velocity_valid일 때만 뜻이 있다
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__SNAPSHOT_HPP_
