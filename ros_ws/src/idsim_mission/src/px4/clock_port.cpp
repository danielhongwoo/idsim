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

#include "idsim_mission/px4/clock_port.hpp"

#include <cstdint>
#include <optional>

namespace idsim_mission::px4
{

std::optional<std::uint64_t> RosPx4ClockPort::now_us()
{
  stamp_ = idsim_common::Px4Timestamp::now(clock_);
  if (!stamp_) {
    return std::nullopt;
  }
  return stamp_->microseconds();
}

}  // namespace idsim_mission::px4
