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

// 상태기의 시간 값과 계수. 모두 ROS 시각(ns)이다.
//
// 기본값은 px4-engineer가 정한 값이다(docs-for-agent/plan-1a-6-idsim-mission/decisions.md 쟁점 10,
// approval-px4-p3b.md). 값의 변경은 px4-engineer가 필수 승인자다. 노드는 같은 이름의 노드
// 파라미터를 선언하고 기본값을 이 구조체에서 읽는다(P3d). 지상 setpoint z 오프셋(0.5 m)은 노드
// 파라미터가 아니라 어댑터 상수라 여기에 없다.
//
// 시간 경계의 규칙: 경과 시간이 값 이상이면(>=) 만료다. 같은 tick에 만료와 확인이 함께 정해지면
// 만료가 이긴다(decisions.md 쟁점 3 "종료의 충돌 규칙"을 전이에도 같게 적용한다).

#ifndef IDSIM_MISSION__CORE__CONFIG_HPP_
#define IDSIM_MISSION__CORE__CONFIG_HPP_

#include <cstdint>

namespace idsim_mission::core
{

inline constexpr std::int64_t kNsPerSecond = 1000000000LL;

struct Timeouts
{
  // P0과 P2(수신, 식별, EKF gate). goal 접수 시각부터.
  std::int64_t ready_timeout_ns{30 * kNsPerSecond};
  // P4(발행 10회와 신호 확인). 발행 시작(P3)부터.
  std::int64_t offboard_signal_timeout_ns{2 * kNsPerSecond};
  // P5 Offboard 확인, LAND 항목의 AUTO_LAND 확인, Hold 실패 뒤 Land 경로, 지상 disarm 확인(M5).
  // 각각 그 명령을 처음 보낸 시각부터.
  std::int64_t mode_confirm_timeout_ns{3 * kNsPerSecond};
  // P6 arm. arm을 처음 보낸 시각부터.
  std::int64_t arm_timeout_ns{5 * kNsPerSecond};
  // 공중 정리의 Hold 확인. Hold를 처음 보낸 시각부터.
  std::int64_t hold_confirm_timeout_ns{3 * kNsPerSecond};
  // vehicle_status를 이 시간 동안 받지 못하면 상태 끊김(마지막 수신 ROS 시각부터).
  std::int64_t link_timeout_ns{2 * kNsPerSecond};
  // LAND 항목에서 landed이고 ARMED인 채 이 시간이 지나면 강제가 아닌 disarm을 보낸다.
  std::int64_t land_disarm_fallback_delay_ns{5 * kNsPerSecond};
  // 확인을 기다리는 명령의 재전송 주기.
  std::int64_t command_resend_period_ns{kNsPerSecond / 2};
};

// "N회 연속" 확인의 N(OFFBOARD, ARMED, AUTO_LOITER, AUTO_LAND, DISARMED). 서로 다른 표본 N개다.
inline constexpr int kConfirmSamples = 3;

// P4의 "발행 10회 이상".
inline constexpr std::uint32_t kOffboardSignalMinPublishes = 10;

struct Config
{
  Timeouts timeouts;
};

}  // namespace idsim_mission::core

#endif  // IDSIM_MISSION__CORE__CONFIG_HPP_
