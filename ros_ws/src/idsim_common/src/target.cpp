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

#include "idsim_common/target.hpp"

#include <string>

#include "idsim_interfaces/msg/target_state.hpp"

namespace idsim_common
{

namespace
{

bool is_lower(char c) { return c >= 'a' && c <= 'z'; }

bool is_digit(char c) { return c >= '0' && c <= '9'; }

}  // namespace

std::optional<TargetId> TargetId::parse(const std::string & text, std::string * error)
{
  const auto fail = [&](const std::string & why) -> std::optional<TargetId> {
    if (error != nullptr) {
      *error = "invalid target id '" + text + "': " + why;
    }
    return std::nullopt;
  };
  if (text.empty()) {
    return fail("empty");
  }
  if (text.size() > kMaxLength) {
    return fail("longer than " + std::to_string(kMaxLength) + " characters");
  }
  if (!is_lower(text.front())) {
    return fail("must start with a lowercase ascii letter");
  }
  for (std::size_t i = 1; i < text.size(); ++i) {
    const char c = text[i];
    if (!is_lower(c) && !is_digit(c) && c != '_') {
      return fail("character at index " + std::to_string(i) + " is not [a-z0-9_]");
    }
  }
  return TargetId(text);
}

std::string target_state_topic(const TargetId & id)
{
  using idsim_interfaces::msg::TargetState;
  return std::string(TargetState::TOPIC_PREFIX) + "/" + id.str() + "/" + TargetState::TOPIC_SUFFIX;
}

}  // namespace idsim_common
