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

#include "idsim_common/geo.hpp"

#include <algorithm>
#include <cmath>

namespace idsim_common::geo
{

namespace
{

constexpr double kPi = 3.14159265358979323846;

double radians(double degrees) { return degrees * (kPi / 180.0); }

double degrees(double radians) { return radians * (180.0 / kPi); }

// ---- gz-math 7.7.0 src/SphericalCoordinates.cc (EARTH_WGS84, heading 0) ----
// 상수와 연산 순서를 원문대로 둔다(SetSurface, UpdateTransformationMatrix, PositionTransform).
constexpr double kEllA = 6378137.0;       // g_EarthWGS84AxisEquatorial
constexpr double kEllB = 6356752.314245;  // g_EarthWGS84AxisPolar

double ell_e() { return std::sqrt(1.0 - std::pow(kEllB, 2) / std::pow(kEllA, 2)); }

double ell_p() { return std::sqrt(std::pow(kEllA, 2) / std::pow(kEllB, 2) - 1.0); }

// PositionTransform(_, SPHERICAL, ECEF). lat, lon은 rad.
Eigen::Vector3d spherical_to_ecef(double lat, double lon, double alt)
{
  const double cos_lat = std::cos(lat);
  const double sin_lat = std::sin(lat);
  const double cos_lon = std::cos(lon);
  const double sin_lon = std::sin(lon);
  const double e = ell_e();
  double curvature = 1.0 - e * e * sin_lat * sin_lat;
  curvature = kEllA / std::sqrt(curvature);
  return {
    (alt + curvature) * cos_lat * cos_lon, (alt + curvature) * cos_lat * sin_lon,
    ((kEllB * kEllB) / (kEllA * kEllA) * curvature + alt) * sin_lat};
}

// PositionTransform(_, ECEF, SPHERICAL). 출력 lat, lon은 rad.
Eigen::Vector3d ecef_to_spherical(const Eigen::Vector3d & ecef)
{
  const double e = ell_e();
  const double ep = ell_p();
  const double p = std::sqrt(ecef.x() * ecef.x() + ecef.y() * ecef.y());
  const double theta = std::atan((ecef.z() * kEllA) / (p * kEllB));
  const double lat = std::atan(
    (ecef.z() + std::pow(ep, 2) * kEllB * std::pow(std::sin(theta), 3)) /
    (p - std::pow(e, 2) * kEllA * std::pow(std::cos(theta), 3)));
  const double lon = std::atan2(ecef.y(), ecef.x());
  double n_curvature = 1.0 - std::pow(e, 2) * std::pow(std::sin(lat), 2);
  n_curvature = kEllA / std::sqrt(n_curvature);
  return {lat, lon, p / std::cos(lat) - n_curvature};
}

// UpdateTransformationMatrix가 캐시하는 값.
struct GzFrame
{
  double cos_lat;
  double sin_lat;
  double cos_lon;
  double sin_lon;
  Eigen::Vector3d origin_ecef;
};

GzFrame gz_frame(const WorldOrigin & origin)
{
  const double lat = radians(origin.lat_deg);
  const double lon = radians(origin.lon_deg);
  return GzFrame{
    std::cos(lat), std::sin(lat), std::cos(lon), std::sin(lon),
    spherical_to_ecef(lat, lon, origin.alt_m)};
}

// origin + rotGlobalToECEF * enu. 행렬 곱은 gz Matrix3d * Vector3d처럼 행마다 왼쪽부터 더한다.
// heading 0이면 LOCAL2의 heading 회전(cosHea 1, sinHea -0)은 값을 바꾸지 않는다.
Eigen::Vector3d local2_to_ecef(const GzFrame & f, const Eigen::Vector3d & enu)
{
  const double x = enu.x();
  const double y = enu.y();
  const double z = enu.z();
  const Eigen::Vector3d rotated(
    -f.sin_lon * x + -f.cos_lon * f.sin_lat * y + f.cos_lon * f.cos_lat * z,
    f.cos_lon * x + -f.sin_lon * f.sin_lat * y + f.sin_lon * f.cos_lat * z,
    0.0 * x + f.cos_lat * y + f.sin_lat * z);
  return f.origin_ecef + rotated;
}

// rotECEFToGlobal * (ecef - origin).
Eigen::Vector3d ecef_to_local2(const GzFrame & f, const Eigen::Vector3d & ecef)
{
  const Eigen::Vector3d d = ecef - f.origin_ecef;
  return {
    -f.sin_lon * d.x() + f.cos_lon * d.y() + 0.0 * d.z(),
    -f.cos_lon * f.sin_lat * d.x() + -f.sin_lon * f.sin_lat * d.y() + f.cos_lat * d.z(),
    f.cos_lon * f.cos_lat * d.x() + f.sin_lon * f.cos_lat * d.y() + f.sin_lat * d.z()};
}

// ---- PX4 v1.17.0 src/lib/geo/geo.h, geo.cpp (MapProjection) ----
constexpr double kRadiusOfEarth = 6371000;  // CONSTANTS_RADIUS_OF_EARTH

}  // namespace

Geodetic world_enu_to_geodetic(const WorldOrigin & origin, const Eigen::Vector3d & enu)
{
  const Eigen::Vector3d s = ecef_to_spherical(local2_to_ecef(gz_frame(origin), enu));
  return Geodetic{degrees(s.x()), degrees(s.y()), s.z()};
}

Eigen::Vector3d geodetic_to_world_enu(const WorldOrigin & origin, const Geodetic & point)
{
  const Eigen::Vector3d ecef =
    spherical_to_ecef(radians(point.lat_deg), radians(point.lon_deg), point.alt_m);
  return ecef_to_local2(gz_frame(origin), ecef);
}

Eigen::Vector3d geodetic_to_local_ned(const LocalReference & ref, const Geodetic & point)
{
  // initReference
  const double ref_lat = radians(ref.lat_deg);
  const double ref_lon = radians(ref.lon_deg);
  const double ref_sin_lat = std::sin(ref_lat);
  const double ref_cos_lat = std::cos(ref_lat);
  // project
  const double lat_rad = radians(point.lat_deg);
  const double lon_rad = radians(point.lon_deg);
  const double sin_lat = std::sin(lat_rad);
  const double cos_lat = std::cos(lat_rad);
  const double cos_d_lon = std::cos(lon_rad - ref_lon);
  const double arg =
    std::clamp(ref_sin_lat * sin_lat + ref_cos_lat * cos_lat * cos_d_lon, -1.0, 1.0);
  const double c = std::acos(arg);
  double k = 1.0;
  if (std::fabs(c) > 0) {
    k = (c / std::sin(c));
  }
  const double x = k * (ref_cos_lat * sin_lat - ref_sin_lat * cos_lat * cos_d_lon) * kRadiusOfEarth;
  const double y = k * cos_lat * std::sin(lon_rad - ref_lon) * kRadiusOfEarth;
  return {x, y, -(point.alt_m - ref.alt_m)};
}

Geodetic local_ned_to_geodetic(const LocalReference & ref, const Eigen::Vector3d & ned)
{
  const double ref_lat = radians(ref.lat_deg);
  const double ref_lon = radians(ref.lon_deg);
  const double ref_sin_lat = std::sin(ref_lat);
  const double ref_cos_lat = std::cos(ref_lat);
  // reproject
  const double x_rad = ned.x() / kRadiusOfEarth;
  const double y_rad = ned.y() / kRadiusOfEarth;
  const double c = std::sqrt(x_rad * x_rad + y_rad * y_rad);
  Geodetic out{ref.lat_deg, ref.lon_deg, ref.alt_m - ned.z()};
  if (std::fabs(c) > 0) {
    const double sin_c = std::sin(c);
    const double cos_c = std::cos(c);
    const double lat_rad = std::asin(cos_c * ref_sin_lat + (x_rad * sin_c * ref_cos_lat) / c);
    const double lon_rad =
      (ref_lon + std::atan2(y_rad * sin_c, c * ref_cos_lat * cos_c - x_rad * ref_sin_lat * sin_c));
    out.lat_deg = degrees(lat_rad);
    out.lon_deg = degrees(lon_rad);
  } else {
    // 원문은 degrees(_ref_lat)를 돌려준다(도 -> rad -> 도).
    out.lat_deg = degrees(ref_lat);
    out.lon_deg = degrees(ref_lon);
  }
  return out;
}

Eigen::Vector3d world_enu_to_local_ned(
  const WorldOrigin & origin, const LocalReference & ref, const Eigen::Vector3d & enu)
{
  return geodetic_to_local_ned(ref, world_enu_to_geodetic(origin, enu));
}

Eigen::Vector3d local_ned_to_world_enu(
  const WorldOrigin & origin, const LocalReference & ref, const Eigen::Vector3d & ned)
{
  return geodetic_to_world_enu(origin, local_ned_to_geodetic(ref, ned));
}

}  // namespace idsim_common::geo
