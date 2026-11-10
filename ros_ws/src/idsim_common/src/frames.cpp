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

#include "idsim_common/frames.hpp"

#include <cmath>
#include <limits>

namespace idsim_common::frames
{

namespace
{

constexpr double kPi = 3.14159265358979323846;

// R_enu_ned: NED 벡터를 ENU로. (n, e, d) -> (e, n, -d). 행렬식 +1인 회전이다.
const Eigen::Quaterniond & q_enu_ned()
{
  static const Eigen::Quaterniond q = [] {
    Eigen::Matrix3d r;
    r << 0, 1, 0, 1, 0, 0, 0, 0, -1;
    return Eigen::Quaterniond(r).normalized();
  }();
  return q;
}

// R_frd_flu: FLU 벡터를 FRD로. (f, l, u) -> (f, -l, -u). x축 기준 pi 회전이다.
const Eigen::Quaterniond & q_frd_flu()
{
  static const Eigen::Quaterniond q = [] {
    Eigen::Matrix3d r;
    r << 1, 0, 0, 0, -1, 0, 0, 0, -1;
    return Eigen::Quaterniond(r).normalized();
  }();
  return q;
}

}  // namespace

Eigen::Vector3d ned_to_enu(const Eigen::Vector3d & ned) { return {ned.y(), ned.x(), -ned.z()}; }

Eigen::Vector3d enu_to_ned(const Eigen::Vector3d & enu) { return {enu.y(), enu.x(), -enu.z()}; }

Eigen::Vector3d frd_to_flu(const Eigen::Vector3d & frd) { return {frd.x(), -frd.y(), -frd.z()}; }

Eigen::Vector3d flu_to_frd(const Eigen::Vector3d & flu) { return {flu.x(), -flu.y(), -flu.z()}; }

Eigen::Quaterniond px4_to_ros_orientation(const Eigen::Quaterniond & q_ned_frd)
{
  return (q_enu_ned() * q_ned_frd * q_frd_flu()).normalized();
}

Eigen::Quaterniond ros_to_px4_orientation(const Eigen::Quaterniond & q_enu_flu)
{
  // 두 정적 회전 모두 pi 회전이라 자기 역이지만, 의미를 드러내려고 conjugate로 쓴다.
  return (q_enu_ned().conjugate() * q_enu_flu * q_frd_flu().conjugate()).normalized();
}

double wrap_pi(double angle)
{
  if (!std::isfinite(angle)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  double wrapped = std::fmod(angle + kPi, 2.0 * kPi);
  if (wrapped < 0.0) {
    wrapped += 2.0 * kPi;
  }
  wrapped -= kPi;
  // fmod 반올림으로 정확히 pi가 나오는 경우를 -pi로 맞춘다.
  if (wrapped >= kPi) {
    wrapped -= 2.0 * kPi;
  }
  return wrapped;
}

double ned_to_enu_yaw(double yaw_ned) { return wrap_pi(kPi / 2.0 - yaw_ned); }

double enu_to_ned_yaw(double yaw_enu) { return wrap_pi(kPi / 2.0 - yaw_enu); }

Eigen::Vector3d ned_to_enu_variance(const Eigen::Vector3d & variance_ned)
{
  return {variance_ned.y(), variance_ned.x(), variance_ned.z()};
}

Eigen::Vector3d enu_to_ned_variance(const Eigen::Vector3d & variance_enu)
{
  return {variance_enu.y(), variance_enu.x(), variance_enu.z()};
}

Eigen::Vector3d to_eigen(const std::array<float, 3> & v)
{
  return {static_cast<double>(v[0]), static_cast<double>(v[1]), static_cast<double>(v[2])};
}

std::array<float, 3> to_px4_array(const Eigen::Vector3d & v)
{
  return {static_cast<float>(v.x()), static_cast<float>(v.y()), static_cast<float>(v.z())};
}

Eigen::Quaterniond to_eigen_quaternion(const std::array<float, 4> & q)
{
  // Eigen::Quaterniond 생성자 인자 순서는 (w, x, y, z)다. 내부 저장 순서(x, y, z, w)와 다르다.
  return {
    static_cast<double>(q[0]), static_cast<double>(q[1]), static_cast<double>(q[2]),
    static_cast<double>(q[3])};
}

std::array<float, 4> to_px4_array(const Eigen::Quaterniond & q)
{
  return {
    static_cast<float>(q.w()), static_cast<float>(q.x()), static_cast<float>(q.y()),
    static_cast<float>(q.z())};
}

}  // namespace idsim_common::frames
