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

// 전이 표에서 떼어 낸 순수 규칙 셋. 상태기(mission_runner)가 쓰고 단위 테스트가 표로 시험한다.
// 근거는 docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 3, 4.
//
// 재실측으로 바뀔 수 있는 것은 고칠 곳이 한 곳이 되게 여기에 모았다(README.md "재실측으로 바뀔 수
// 있는 곳").
// - 비행 중 감시 표의 행 순위(재실측 (4) 전까지 잠정): kMonitorRankOrder 한 배열.
// - "disarm 전송 뒤 받은 표본"의 기준(재실측 (5)): is_after_disarm_send 한 함수.

#ifndef IDSIM_MISSION__CORE__RULES_HPP_
#define IDSIM_MISSION__CORE__RULES_HPP_

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "idsim_mission/core/snapshot.hpp"
#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

// ---- 비행 중 감시 표(지상 arm 진입은 P6에서 첫 ARMED 표본을 본 tick부터, 공중 Offboard 진입은 P3
// 다음 tick부터 setpoint 항목이 끝날 때까지) ----

enum class MonitorRow : std::uint8_t
{
  kTimestampFailure,  // Px4Timestamp::now 실패 -> INTERNAL
  kIdentityMismatch,  // 식별 대조 불일치 -> INTERNAL(M2)
  kLinkLost,          // vehicle_status가 link_timeout 동안 없음 -> LINK_LOST
  kDisarmedInAir,     // DISARMED이고 landed false -> FAILSAFE
  kDisarmedOnGround,  // DISARMED이고 landed true -> FAILSAFE 또는 EXTERNAL_DISARM
  kModeFailsafe,      // OFFBOARD 아님이고 failsafe -> FAILSAFE
  kModeExternal,  // OFFBOARD 아님, failsafe 아님, 사용자 의도 OFFBOARD 아님 -> EXTERNAL_MODE_CHANGE
  kModeDefensive,  // OFFBOARD 아님, failsafe 아님, 사용자 의도 OFFBOARD -> FAILSAFE(방어용)
};

// 순위. 앞이 이긴다. 순위는 같은 tick의 동률만 가른다(엇갈려 시작하면 먼저 맞은 행이 그 tick에
// goal을 끝낸다). 재실측 (4) 전까지 잠정이다. 순위를 바꾸려면 이 배열만 고친다.
inline constexpr std::array<MonitorRow, 8> kMonitorRankOrder = {
  MonitorRow::kTimestampFailure, MonitorRow::kIdentityMismatch, MonitorRow::kLinkLost,
  MonitorRow::kDisarmedInAir,    MonitorRow::kDisarmedOnGround, MonitorRow::kModeFailsafe,
  MonitorRow::kModeExternal,     MonitorRow::kModeDefensive,
};

// 1부터. kMonitorRankOrder에 없으면 0.
int monitor_rank(MonitorRow row);
const char * monitor_row_name(MonitorRow row);

struct MonitorInput
{
  bool timestamp_ok{true};
  const StatusSample * status{nullptr};  // 최신 vehicle_status. 없으면 상태 끊김으로 본다
  bool landed{true};                     // 그 tick까지 받은 최신 landed
  bool link_lost{false};
  // 이 항목 실행 중 앞선 표본에서 failsafe == true를 본 적이 있는가(순위 5의 이력 가지).
  // 지금 표본은 넣지 않는다.
  bool failsafe_history{false};
  // AUTO_LOITER 면제(공중 Offboard 진입의 첫 OFFBOARD 표본 전. 1b decisions.md 쟁점 7). true이면
  // 순위 7, 8은 표본의 nav가 AUTO_LOITER(kHold)일 때 맞지 않는다(의도는 보지 않는다). 순위 1-6은
  // 바뀌지 않는다(순위 6은 AUTO_LOITER여도 맞는다).
  bool hold_exempt{false};
};

bool monitor_row_matches(MonitorRow row, const MonitorInput & input);
// 행이 맞을 때의 reason. 순위 5는 이 표본의 failsafe와 이력으로 가른다.
Reason monitor_row_reason(MonitorRow row, const MonitorInput & input);

struct MonitorVerdict
{
  MonitorRow row{MonitorRow::kTimestampFailure};
  Reason reason{Reason::kInternal};
  std::string detail;
  // 이 입력에 맞는 행 전부(순위 순서, row 포함). 판정에는 row만 쓴다. 전이 관측의 겹침 칸용이다.
  std::vector<MonitorRow> matched;
};

// 순위대로 처음 맞는 행. 어느 행도 맞지 않으면 nullopt(goal을 계속한다). 맞는 행 전부를 matched에
// 함께 싣는다. OFFBOARD이고 ARMED인
// 채 failsafe가 true인 표본은 어느 행에도 맞지 않는다(decisions.md 쟁점 4 "비행 중 감시" 표 아래
// 문단).
std::optional<MonitorVerdict> evaluate_monitor(const MonitorInput & input);

// 감시 표의 행으로 goal을 끝낼 때 강제가 아닌 disarm을 한 번 보내는가(decisions.md 쟁점 4 표 아래
// "지상 disarm 1회"와 "순위 2의 disarm 1회"). 보낸 disarm은 재전송하지 않고 확인하지 않는다.
enum class MonitorDisarm : std::uint8_t
{
  kNever,      // 순위 1(명령에 실을 시각이 없다), 4, 5(이미 DISARMED)
  kIfArmSent,  // 순위 2. 이 goal이 arm을 보냈으면 landed와 이력을 보지 않고 보낸다
  kIfNeverAirborne,  // 순위 3, 6, 7, 8. 아래 조건 셋이 모두 참일 때만 보낸다
};

MonitorDisarm monitor_row_disarm(MonitorRow row);

struct MonitorDisarmInput
{
  bool arm_sent{false};  // 조건 1: 이 goal이 arm을 보냈다
  bool landed_false_seen{false};  // 첫 ARMED 표본 뒤에 받은 landed가 false인 적이 있다(goal 이력)
  bool landed_known{false};  // vehicle_land_detected 표본이 있다
  bool landed{false};  // 조건 3: 그 tick의 최신 landed(순위 3에서는 끊기기 전의 값)
};

bool monitor_sends_disarm(MonitorRow row, const MonitorDisarmInput & input);

// ---- 준비 단계의 진입 방식과 모드 명령 항목(1b decisions.md 쟁점 9, 12) ----

// 진입 방식은 첫 항목 type에서 정한다.
enum class EntryPlan : std::uint8_t
{
  kGroundArm,  // 첫 항목 TAKEOFF: landed이고 DISARMED에서 Offboard로 들어가 arm(P3-P6)
  kModeCommand,  // 첫 항목 LAND, RTL: landed가 아니고 ARMED에서 P2 뒤 바로 그 항목을 시작
  // 첫 항목 LOITER: landed가 아니고 ARMED이고 AUTO_LOITER(의도도 AUTO_LOITER), failsafe 없음에서
  // 지금 위치를 진입 setpoint로 발행하고 Offboard로 들어간다(P3-P5. arm을 보내지 않는다. 1b
  // decisions.md 쟁점 7). GOTO와 TRACK_ENTITY는 runner가 그 type을 받을 때 더한다.
  kAirOffboard,
};

// 그 밖의 type은 nullopt(runner가 아직 실행하지 않는 진입).
std::optional<EntryPlan> entry_plan(std::uint8_t first_item_type);

// detail에 쓰는 nav_state 이름(OFFBOARD, AUTO_LOITER, AUTO_LAND, AUTO_RTL, OTHER).
const char * nav_mode_name(NavMode mode);

// 모드 명령 항목의 type별 값. 판정 순서와 규칙은 LAND와 RTL이 같고 아래 값만 다르다.
struct ModeItemSpec
{
  CommandKind command{CommandKind::kNavLand};  // 항목 시작 tick에 보내고 확인 전까지 재전송
  NavMode mode{NavMode::kLand};                // 확인 대상 모드
  const char * mode_name{""};                  // detail의 모드 이름
  const char * command_name{""};               // detail의 명령 이름
  // 확인 전 거부 ack와 mode_confirm_timeout이 RTL 실패의 정리(Land fallback)로 가는가. false이면
  // 거부 ack를 보지 않고(재전송 계속) mode_confirm_timeout에 MODE_SWITCH_FAILED로 바로
  // 끝낸다(LAND).
  bool land_fallback{false};
};

// LAND, RTL이 아니면 nullopt.
std::optional<ModeItemSpec> mode_item_spec(std::uint8_t type);

// ---- 정리 분기 고르기(취소, ITEM_TIMEOUT, PREPARING 실패, RTL 실패가 같이 쓴다) ----

// disarm의 지상 대 공중 분류. 처음 관측한 DISARMED 표본의 tick에 그때까지 받은 최신 landed로
// 정하고 고정한다(뒤의 landed 표본으로 바꾸지 않는다). ARMED 표본을 보면 kUnknown으로 되돌린다.
enum class DisarmClass : std::uint8_t
{
  kUnknown,
  kGround,
  kAir,
};

enum class CleanupChoice : std::uint8_t
{
  kAir,        // Hold 분기(확인되지 않으면 Land 경로)
  kGround,     // 지상 disarm 분기(지상 setpoint + disarm + 전송 뒤 DISARMED 확인)
  kAirDisarm,  // 공중에서 disarm됨. 정리 없이 끝낸다(취소면 FAILSAFE)
  kEnd,        // 지상 disarm이고 이 goal에서 arm을 보낸 적이 없음. 바로 끝낸다
};

const char * cleanup_choice_name(CleanupChoice choice);

struct CleanupInput
{
  Arming arming{Arming::kDisarmed};
  bool landed{true};                                // 최신 landed(ARMED일 때 쓴다)
  DisarmClass disarm_class{DisarmClass::kUnknown};  // DISARMED일 때 쓴다(고정된 분류)
  bool arm_sent{false};          // 이 goal에서 arm을 한 번이라도 보냈는가
  bool in_ground_branch{false};  // 이미 지상 disarm 분기에 있는가
};

// 매 tick 다시 고른다. DISARMED이면 고정된 분류를 쓰고, ARMED이면 최신 landed를 쓴다.
CleanupChoice select_cleanup(const CleanupInput & input);

// ---- 확인 계수 ----

// "N회 연속"의 계수. 표본은 vehicle_status.timestamp로 가른다. timestamp가 직전에 본 표본보다
// 크지 않으면(같은 표본을 다시 본 경우와 줄어든 경우) 건너뛴다(되돌리지도 더하지도 않는다).
// 맞는 표본은 1을 더하고 맞지 않는 표본은 0으로 되돌린다.
class SampleCounter
{
public:
  void reset();
  // 새 표본으로 셌으면 true.
  bool observe(std::uint64_t timestamp_us, bool matches);
  int count() const { return count_; }

private:
  int count_{0};
  std::uint64_t last_timestamp_us_{0};
  bool has_last_{false};
};

// "disarm 전송 뒤 받은 표본"의 기준(decisions.md 쟁점 3 M5 "arm을 보낸 뒤의 지상 분기"). 재실측
// (5)로 바뀌면 이 함수만 고친다. 수신 tick이 이 분기의 첫 disarm 전송 tick보다 크고, timestamp가
// 첫 전송에 실은 Px4Timestamp보다 엄격히 뒤인 표본만 센다(두 조건 모두. 재전송의 값이 아니라
// 첫 전송의 값과 비교한다).
bool is_after_disarm_send(
  const StatusSample & sample, std::uint64_t first_send_tick, std::uint64_t first_send_stamp_us);

// 지상 disarm 분기의 DISARMED 확인. 전송 뒤의 표본만 보고, 그 안에서 SampleCounter 규칙을 쓴다
// (DISARMED가 아닌 표본은 0으로 되돌린다. 늦게 처리된 arm의 경합).
class DisarmConfirm
{
public:
  // 분기에 들어가 첫 disarm을 보낸 tick. 계수를 0으로 되돌리고 전송 시각은 모르는 상태로 둔다.
  void begin(std::uint64_t first_send_tick);
  // 첫 전송에 실은 Px4Timestamp. 알기 전의 표본은 세지 않는다.
  void set_first_stamp(std::uint64_t stamp_us);
  void observe(const StatusSample & sample);
  int count() const { return counter_.count(); }
  std::uint64_t first_send_tick() const { return first_send_tick_; }
  bool stamp_known() const { return stamp_known_; }

private:
  SampleCounter counter_;
  std::uint64_t first_send_tick_{0};
  std::uint64_t first_send_stamp_us_{0};
  bool stamp_known_{false};
};

// ---- 착지 뒤 대비책 disarm의 기한 ----

// landed이고 ARMED인 상태가 land_disarm_fallback_delay 이어졌는가(decisions.md 쟁점 10 "LAND 항목의
// 착지 뒤 fallback 계산은 함수로 빼서 지상 대기와 함께 쓴다"). 기준 시각은 그 상태가 처음 관측된
// tick의 시각이고, 그 상태가 아닌 관측이 오면 끊고 다음 관측에서 다시 잰다. 어느 tick에 관측을
// 반영할지(observe를 부를지)와 보낼 조건(확인 뒤, 분기)은 부르는 쪽이 정한다. observe를 부르지 않은
// tick은 기준 시각을 끊지도 새로 시작하지도 않는다. 대비책은 한 번만 보낸다(mark_sent 뒤 due는
// false).
class LandedArmedFallback
{
public:
  void reset();
  // 그 tick의 관측. landed_and_armed가 false면 이어짐을 끊는다.
  void observe(bool landed_and_armed, std::int64_t now_ns);
  // 이어지는 중이고 기준 시각부터 delay_ns 이상 지났고 아직 보내지 않았다.
  bool due(std::int64_t now_ns, std::int64_t delay_ns) const;
  void mark_sent() { sent_ = true; }
  bool sent() const { return sent_; }

private:
  bool known_{false};
  std::int64_t since_ns_{0};
  bool sent_{false};
};

// world ENU yaw -> 로컬 NED yaw, [-pi, pi). idsim_common/frames의 enu_to_ned_yaw와 같은 식이다.
// core는 idsim_common(rclcpp 의존)을 링크하지 않으므로 식을 다시 쓴다. 같은 값인지는 노드 쪽
// gtest(P3d)가 교차 검사한다.
double enu_to_ned_yaw(double yaw_enu);
double wrap_pi(double angle);

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__RULES_HPP_
