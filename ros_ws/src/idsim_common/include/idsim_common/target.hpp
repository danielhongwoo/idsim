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

// 표적 식별과 표적 상태 토픽 이름.
// 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 3, 14.
//
// target_id 규칙은 ^[a-z][a-z0-9_]{0,31}$다(docs/interface.md "이름과 식별자"). 토픽은 절대 이름
// /targets/<target_id>/state이고 idsim_interfaces TargetState의 TOPIC_PREFIX, TOPIC_SUFFIX 상수로
// 조립한다(문자열을 다시 쓰지 않는다). 기체 네임스페이스에 속하지 않는다.
// 같은 규칙의 Python 쪽은 판정이 tests/support, 발행이 표적 어댑터(idsim_sim)에 있다.

#ifndef IDSIM_COMMON__TARGET_HPP_
#define IDSIM_COMMON__TARGET_HPP_

#include <cstddef>
#include <optional>
#include <string>
#include <utility>

namespace idsim_common
{

// 계약 식별자 target_id. 예: "car_1".
class TargetId
{
public:
  // 최대 길이(첫 글자 포함).
  static constexpr std::size_t kMaxLength = 32;

  // ^[a-z][a-z0-9_]{0,31}$를 만족할 때만 값을 돌려준다. 실패하면 nullopt이고, error가 있으면
  // 이유를 적는다.
  static std::optional<TargetId> parse(const std::string & text, std::string * error = nullptr);

  const std::string & str() const { return value_; }

  bool operator==(const TargetId & other) const { return value_ == other.value_; }
  bool operator!=(const TargetId & other) const { return value_ != other.value_; }

private:
  explicit TargetId(std::string value) : value_(std::move(value)) {}

  std::string value_;
};

// 표적 상태 토픽의 절대 이름. 예: "/targets/car_1/state".
std::string target_state_topic(const TargetId & id);

}  // namespace idsim_common

#endif  // IDSIM_COMMON__TARGET_HPP_
