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

#include "idsim_mission/core/termination.hpp"

#include <cstdint>

namespace idsim_mission::core
{

bool is_consistent(Status status, Reason reason)
{
  if (status == Status::kAborted) {
    return reason != Reason::kNone;
  }
  return reason == Reason::kNone;
}

std::uint8_t event_status_code(Status status)
{
  switch (status) {
    case Status::kSucceeded:
      return event_status::kSucceeded;
    case Status::kCanceled:
      return event_status::kCanceled;
    case Status::kAborted:
      return event_status::kAborted;
  }
  return event_status::kUnknown;
}

ResultFields to_result(const Termination & termination)
{
  ResultFields fields;
  fields.reason = static_cast<std::uint8_t>(termination.reason);
  fields.items_completed = termination.items_completed;
  fields.last_item_index = termination.last_item_index;
  fields.detail = termination.detail;
  return fields;
}

EventFields to_terminal_event(const Termination & termination, std::uint32_t item_count)
{
  const ResultFields result = to_result(termination);
  EventFields fields;
  fields.status = event_status_code(termination.status);
  fields.reason = result.reason;
  fields.item_count = item_count;
  fields.items_completed = result.items_completed;
  fields.last_item_index = result.last_item_index;
  fields.detail = result.detail;
  return fields;
}

EventFields accepted_event(std::uint32_t item_count)
{
  EventFields fields;
  fields.status = event_status::kAccepted;
  fields.reason = static_cast<std::uint8_t>(Reason::kNone);
  fields.item_count = item_count;
  return fields;
}

}  // namespace idsim_mission::core
