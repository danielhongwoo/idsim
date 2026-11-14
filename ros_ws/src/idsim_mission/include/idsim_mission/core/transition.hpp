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

// 상태기 전이의 관측(docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 13).
//
// - 상태 key: stage, 준비 단계, 현재 항목 type, 정리 원인, 정리 분기. 이름(state_key_name)에는 그
//   stage가 읽는 성분만 넣는다. PREPARING은 준비 단계, ITEM은 항목 type, CLEANUP은 원인과 분기다.
// - 전이를 일으키는 runner의 호출 지점은 첫 인자로 사건 꼬리표 Event를 받는다. 꼬리표를 받는 순간의
//   상태 key가 from이고, 다음 꼬리표나 그 tick의 끝의 상태 key와 종료 reason이 to다. 한 tick의 연쇄
//   전이는 기록이 여럿이다.
// - 꼬리표 하나는 상태 key를 한 번까지만 바꾼다. 꼬리표 없이 상태 key가 바뀌거나, 한 꼬리표의
//   기록이 열린 동안 상태 key가 두 번째로 바뀌면 그 변경은 untagged 기록(tagged false)이 된다.
//   두 번째 변경은 앞 기록의 to에 넣지 않는다(앞 기록은 그 변경 직전의 상태 key로 닫는다).
// - 겹침: 결정 지점에서 함께 참이던 사건을 also_true에 싣는다(감시 표의 다른 행, setpoint 항목의
//   ITEM_TIMEOUT과 완료, 그 tick에 무시된 취소).
// - observer는 MissionRunner 생성자의 마지막 인자다. 기본값 nullptr이면 아무것도 기록하지 않고
//   동작은 같다. 노드는 넘기지 않는다.
//
// Event 목록과 칸 목록(test/transition_cells.tsv)은 전이 표의 일부라 바꾸려면 px4-engineer가 필수
// 승인자다. Event를 더하거나 지우면 kAllEvents와 event_name을 같이 고친다(칸 목록 테스트가 이름
// 집합을 대조한다).

#ifndef IDSIM_MISSION__CORE__TRANSITION_HPP_
#define IDSIM_MISSION__CORE__TRANSITION_HPP_

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "idsim_mission/core/types.hpp"

namespace idsim_mission::core
{

enum class Stage : std::uint8_t
{
  kPreparing,
  kItem,
  // 취소, setpoint 항목의 ITEM_TIMEOUT, PREPARING 실패, RTL 실패 뒤의 정리와 공중 종료 단계
  kCleanup,
  kDone,
};

// PREPARING(첫 항목이 TAKEOFF)의 단계. kWaitReady는 P0-P2, kSignal은 P3-P4. kOffboardAck는 P5 안의
// ack 대기 구간(OFFBOARD 3회 확인 뒤 마지막 DO_SET_MODE 전송 뒤의 ack를 기다린다. 1b decisions.md
// 쟁점 12).
enum class PrepStep : std::uint8_t
{
  kWaitReady,
  kSignal,
  kOffboard,
  kOffboardAck,
  kArm,
};

enum class CleanupCause : std::uint8_t
{
  kCancel,
  kItemTimeout,
  kPreparingFailure,
  kRtlFailure,  // RTL 항목의 거부 ack나 mode_confirm_timeout. 공중이면 Hold 없이 Land 경로
  // 마지막 setpoint 항목(TAKEOFF, LOITER)의 완료 뒤의 공중 종료 단계(1b decisions.md 쟁점 10).
  // 분기 고르기는 다른 원인과 따로 둔다(AIR -> AIR_LAND 또는 GROUND_WAIT, GROUND_WAIT -> AIR_LAND).
  kMissionEnd,
};

enum class Branch : std::uint8_t
{
  kNone,
  kAir,      // Hold를 보내고 AUTO_LOITER 확인
  kAirLand,  // Hold가 거부되거나 확인되지 않아(원인이 RTL 실패이면 바로) NAV_LAND
  kGround,  // 지상 setpoint + disarm
  // 공중 종료 단계에서 Hold 실패가 지상에서 온 뒤의 지상 대기. NAV_LAND를 보내지 않고 PX4 자동
  // disarm을 기다리며, landed이고 ARMED인 채 land_disarm_fallback_delay가 지나면 대비책 disarm.
  kGroundWait,
};

// 사건 꼬리표. 값은 0부터 빈틈없이 늘어난다(kAllEvents의 순서와 같다).
enum class Event : std::uint8_t
{
  // PREPARING 전체
  kInvalidMission,             // validate_mission_runnable 미통과 미션의 첫 step
  kPreparingIdentityMismatch,  // 발행 시작 뒤, 첫 ARMED 표본 전의 식별 불일치
  // P0-P2
  kReadyIdentityMismatch,  // P0 식별 불일치
  kPreconditionFailed,     // P1 시작 조건
  kReadyTimeout,           // ready_timeout
  kReadyTakeoff,           // 첫 항목 TAKEOFF: P3 발행 시작
  kReadyModeItem,          // 첫 항목이 모드 명령 항목(LAND, RTL): 항목 시작
  // P3-P4
  kSignalTimeout,
  kSignalConfirmed,
  // P5와 ack 대기(P5a)
  kOffboardRejected,
  kOffboardTimeout,
  kOffboardConfirmed,    // OFFBOARD 3회 연속 확인. 확인을 고정하고 ack 대기로
  kOffboardAckAccepted,  // ack 대기에서 arm 조건의 ack를 가짐. arm을 보내고 P6
  kOffboardLeft,         // ack 대기에서 OFFBOARD 이탈
  // P6
  kArmRejected,        // 첫 ARMED 표본 전의 거부 ack(TEMPORARILY_REJECTED 밖)
  kArmTimeout,         // 첫 ARMED 표본 전의 arm_timeout
  kArmConfirmTimeout,  // 첫 ARMED 표본 뒤 확인 기한
  kArmConfirmed,       // ARMED이고 OFFBOARD 3회: 첫 항목 시작
  // 비행 중 감시 표(P6의 첫 ARMED 표본부터 setpoint 항목 끝까지). 행마다 하나(rules.hpp MonitorRow)
  kMonitorTimestampFailure,
  kMonitorIdentityMismatch,
  kMonitorLinkLost,
  kMonitorDisarmedInAir,
  kMonitorDisarmedOnGround,
  kMonitorModeFailsafe,
  kMonitorModeExternal,
  kMonitorModeDefensive,
  // setpoint 항목
  kItemTimeout,
  kTakeoffReached,
  kLoiterElapsed,
  // 모드 명령 항목(LAND, RTL). 칸은 상태 key(ITEM.LAND, ITEM.RTL)로 갈린다
  kModeItemIdentityMismatch,  // 식별 불일치
  kModeItemLinkLost,          // 상태 끊김
  kModeItemDisarmedInAir,     // 공중 DISARMED
  kModeItemLeftMode,  // 확인 뒤 ARMED인 채 확인 대상 모드(AUTO_LAND, AUTO_RTL) 이탈
  // 확인 전 그 항목의 명령에 대한 거부 ack(RTL만. LAND는 거부 ack로 끝내지 않는다)
  kModeItemRejected,
  kModeItemModeTimeout,      // mode_confirm_timeout 안에 확인 대상 모드 미확인
  kModeItemTimeout,          // 모드 명령 항목의 timeout
  kModeItemDisarmConfirmed,  // 지상 DISARMED 3회
  // 취소(단계 처리 뒤)
  kCancel,
  // 정리
  kCleanupNoSample,          // 판단할 표본이 없다(정리할 것 없음)
  kCleanupIdentityMismatch,  // 분기를 고르기 전(정리 첫 tick)의 식별 불일치
  kCleanupLinkLost,
  kCleanupAirDisarm,
  kCleanupNothingToDo,  // 지상 DISARMED이고 arm을 보낸 적이 없다
  kCleanupCap,          // 정리의 상한
  kEnterGround,
  // Hold 분기(Hold가 이미 실패했거나 원인이 RTL 실패이면 Land 경로). 공중 종료 단계에서는 첫
  // tick의 Hold 분기와 지상 대기에서 공중으로 돌아간 Land 경로
  kEnterAir,
  kGroundDisarmTimeout,
  // 지상 DISARMED 3회. 지상 disarm 분기에서는 disarm 전송 뒤의 확인이고, 공중 종료 단계에서는
  // PX4 자동 disarm(대비책 disarm 전)이나 대비책 disarm 뒤의 확인이다(분기 무관, 단계 전체에 하나)
  kGroundDisarmConfirmed,
  kHoldRejected,
  kHoldTimeout,
  kHoldConfirmed,
  kLandPathModeObserved,
  kLandPathTimeout,
  // 출력 마무리
  kStampUnavailable,  // Px4Timestamp 공급 실패
};

inline constexpr std::array<Event, 54> kAllEvents = {
  Event::kInvalidMission,
  Event::kPreparingIdentityMismatch,
  Event::kReadyIdentityMismatch,
  Event::kPreconditionFailed,
  Event::kReadyTimeout,
  Event::kReadyTakeoff,
  Event::kReadyModeItem,
  Event::kSignalTimeout,
  Event::kSignalConfirmed,
  Event::kOffboardRejected,
  Event::kOffboardTimeout,
  Event::kOffboardConfirmed,
  Event::kOffboardAckAccepted,
  Event::kOffboardLeft,
  Event::kArmRejected,
  Event::kArmTimeout,
  Event::kArmConfirmTimeout,
  Event::kArmConfirmed,
  Event::kMonitorTimestampFailure,
  Event::kMonitorIdentityMismatch,
  Event::kMonitorLinkLost,
  Event::kMonitorDisarmedInAir,
  Event::kMonitorDisarmedOnGround,
  Event::kMonitorModeFailsafe,
  Event::kMonitorModeExternal,
  Event::kMonitorModeDefensive,
  Event::kItemTimeout,
  Event::kTakeoffReached,
  Event::kLoiterElapsed,
  Event::kModeItemIdentityMismatch,
  Event::kModeItemLinkLost,
  Event::kModeItemDisarmedInAir,
  Event::kModeItemLeftMode,
  Event::kModeItemRejected,
  Event::kModeItemModeTimeout,
  Event::kModeItemTimeout,
  Event::kModeItemDisarmConfirmed,
  Event::kCancel,
  Event::kCleanupNoSample,
  Event::kCleanupIdentityMismatch,
  Event::kCleanupLinkLost,
  Event::kCleanupAirDisarm,
  Event::kCleanupNothingToDo,
  Event::kCleanupCap,
  Event::kEnterGround,
  Event::kEnterAir,
  Event::kGroundDisarmTimeout,
  Event::kGroundDisarmConfirmed,
  Event::kHoldRejected,
  Event::kHoldTimeout,
  Event::kHoldConfirmed,
  Event::kLandPathModeObserved,
  Event::kLandPathTimeout,
  Event::kStampUnavailable,
};
static_assert(
  static_cast<std::size_t>(Event::kStampUnavailable) + 1 == kAllEvents.size(),
  "kAllEvents must list every Event in declaration order");

// 칸 목록에 쓰는 이름(대문자와 밑줄, 앞의 k 없이). 예: kReadyTakeoff -> READY_TAKEOFF.
const char * event_name(Event event);

// runner의 상태. item_index는 untagged 검출에만 쓰고 이름에는 넣지 않는다(이름은 항목 type).
struct StateKey
{
  Stage stage{Stage::kPreparing};
  PrepStep prep{PrepStep::kWaitReady};
  CleanupCause cause{CleanupCause::kCancel};
  Branch branch{Branch::kNone};
  std::uint8_t item_type{0};
  std::uint32_t item_index{0};
};

bool operator==(const StateKey & a, const StateKey & b);
bool operator!=(const StateKey & a, const StateKey & b);

// 칸 목록의 상태 이름. PREPARING.<단계>, ITEM.<항목 type>, CLEANUP.<원인>.<분기>, DONE.
// 예: PREPARING.WAIT_READY, ITEM.LOITER, CLEANUP.ITEM_TIMEOUT.AIR_LAND.
std::string state_key_name(const StateKey & key);

struct TransitionEdge
{
  std::uint64_t tick{0};
  bool tagged{true};  // false면 꼬리표 없이 상태가 바뀌었다(event와 also_true는 뜻이 없다)
  Event event{Event::kInvalidMission};
  std::vector<Event> also_true;  // 함께 참이던 사건. kAllEvents 순서이고 중복이 없다
  StateKey from;
  StateKey to;
  bool terminated{false};  // to가 DONE이고 이 기록이 종료를 정했다
  Status status{Status::kAborted};
  Reason reason{Reason::kNone};
};

// 칸 목록의 reason 열. 종료가 아니면 "-", 종료면 <status>/<reason>(예: ABORTED/ITEM_TIMEOUT).
std::string edge_reason_name(const TransitionEdge & edge);

class TransitionObserver
{
public:
  virtual ~TransitionObserver() = default;
  // step 하나가 끝날 때 그 tick의 기록을 순서대로 넘긴다.
  virtual void on_edge(const TransitionEdge & edge) = 0;
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__TRANSITION_HPP_
