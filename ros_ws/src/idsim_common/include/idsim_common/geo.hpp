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

// 원점 이동 변환. world ENU 점 <-> WGS84 <-> 기체 로컬 NED 점.
// 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 4.
//
// 사슬은 Gazebo와 PX4가 실제로 쓰는 식을 그대로 옮긴다. 평행 이동으로 근사하지 않는다.
// - world ENU <-> WGS84: gz-math 7.7.0
//   SphericalCoordinates::PositionTransform(p, LOCAL2, SPHERICAL)와 그 역(SPHERICAL -> LOCAL2).
//   heading 0, 타원체 EARTH_WGS84. local -> ECEF -> geodetic이고 geodetic 계산은 gz-math의 닫힌
//   식(Bowring 1회)이다. 고도는 타원체 고이고 geoid 보정을 하지 않는다(GZBridge가 NavSat 고도를
//   그대로 PX4에 넣는다).
// - WGS84 <-> 기체 로컬 NED: PX4 v1.17.0 MapProjection(src/lib/geo/geo.cpp, 반지름 6371 km 구면의
//   방위 등거리 투영)의 project와 reproject. 고도는 기준 고도와의 차(z = -(alt - ref_alt)).
//   PX4는 project 결과를 float로 자르고 reproject 입력을 float로 받지만, 여기서는 double을 유지한다
//   (차이는 float 반올림뿐이다).
// world_enu_to_local_ned와 local_ned_to_world_enu가 두 단계를 묶는다. 왕복 오차는 gz의 geodetic
// 닫힌 식이 정확한 역이 아닌 데서 오고 수 km 안에서 1e-6 m 아래다(test_geo.cpp).
//
// 순수 함수다. Eigen만 쓰고 상태를 갖지 않는다. 입력 검사를 하지 않으며 비유한 입력은 비유한 출력이
// 된다. 기준의 유효 술어(xy_global, z_global, 유한성, ref_alt != 0.0)는 기준을 읽는 px4 어댑터가
// 맡는다. 속도 같은 벡터는 기준에 의존하지 않는 축 치환이므로 frames::enu_to_ned와 ned_to_enu를
// 쓴다(자오선 수렴과 척도 차이는 무시한다).

#ifndef IDSIM_COMMON__GEO_HPP_
#define IDSIM_COMMON__GEO_HPP_

#include "Eigen/Core"

namespace idsim_common::geo
{

// WGS84 점. 위도와 경도는 도, 고도는 타원체 고(m).
struct Geodetic
{
  double lat_deg{0.0};
  double lon_deg{0.0};
  double alt_m{0.0};
};

// 월드 원점. params의 world.origin(월드 SDF <spherical_coordinates>와 같은 값, heading 0).
struct WorldOrigin
{
  double lat_deg{0.0};
  double lon_deg{0.0};
  double alt_m{0.0};
};

// 기체 로컬 NED의 기준. vehicle_local_position의 ref_lat, ref_lon(도), ref_alt(m).
struct LocalReference
{
  double lat_deg{0.0};
  double lon_deg{0.0};
  double alt_m{0.0};
};

// gz PositionTransform(enu, LOCAL2, SPHERICAL)과 같은 식.
Geodetic world_enu_to_geodetic(const WorldOrigin & origin, const Eigen::Vector3d & enu);

// gz PositionTransform(point, SPHERICAL, LOCAL2)와 같은 식.
Eigen::Vector3d geodetic_to_world_enu(const WorldOrigin & origin, const Geodetic & point);

// PX4 MapProjection::project와 같은 식(x 북, y 동). z = -(alt - ref_alt).
Eigen::Vector3d geodetic_to_local_ned(const LocalReference & ref, const Geodetic & point);

// PX4 MapProjection::reproject와 같은 식. alt = ref_alt - z.
Geodetic local_ned_to_geodetic(const LocalReference & ref, const Eigen::Vector3d & ned);

// world ENU 점 -> 기체 로컬 NED 점(setpoint, 표적 위치).
Eigen::Vector3d world_enu_to_local_ned(
  const WorldOrigin & origin, const LocalReference & ref, const Eigen::Vector3d & enu);

// 기체 로컬 NED 점 -> world ENU 점(Phase 2 Collector).
Eigen::Vector3d local_ned_to_world_enu(
  const WorldOrigin & origin, const LocalReference & ref, const Eigen::Vector3d & ned);

}  // namespace idsim_common::geo

#endif  // IDSIM_COMMON__GEO_HPP_
