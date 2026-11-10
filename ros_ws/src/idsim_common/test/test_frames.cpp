// 좌표 변환 테스트. px4_ros_com frame_transforms와 차등 비교하고, NaN 보존과 yaw를 따로 본다.
// 결정: docs-for-agent/plan-1a-4-idsim-common/decisions.md 쟁점 1.

#include <gtest/gtest.h>

#include <array>
#include <cmath>
#include <limits>
#include <random>
#include <vector>

#include "idsim_common/frames.hpp"
#include "px4_ros_com/frame_transforms.h"

namespace ft = px4_ros_com::frame_transforms;
namespace fr = idsim_common::frames;

namespace
{

constexpr double kPi = 3.14159265358979323846;
constexpr double kTol = 1e-12;
const double kNaN = std::numeric_limits<double>::quiet_NaN();

// q와 -q는 같은 회전이다.
void expect_same_rotation(const Eigen::Quaterniond & a, const Eigen::Quaterniond & b)
{
  const double dot = std::abs(a.normalized().coeffs().dot(b.normalized().coeffs()));
  EXPECT_NEAR(dot, 1.0, 1e-12) << "a=" << a.coeffs().transpose() << " b=" << b.coeffs().transpose();
}

void expect_vec_near(const Eigen::Vector3d & a, const Eigen::Vector3d & b, double tol = kTol)
{
  EXPECT_NEAR(a.x(), b.x(), tol);
  EXPECT_NEAR(a.y(), b.y(), tol);
  EXPECT_NEAR(a.z(), b.z(), tol);
}

// 두 각의 차이를 [-pi, pi)로.
double angle_diff(double a, double b) { return fr::wrap_pi(a - b); }

std::vector<Eigen::Vector3d> sample_vectors()
{
  std::mt19937 gen(12345);
  std::uniform_real_distribution<double> dist(-100.0, 100.0);
  std::vector<Eigen::Vector3d> out = {{0, 0, 0}, {1, 0, 0}, {0, 1, 0},
                                      {0, 0, 1}, {1, 2, 3}, {-4.5, 0.25, -9.75}};
  for (int i = 0; i < 200; ++i) {
    out.emplace_back(dist(gen), dist(gen), dist(gen));
  }
  return out;
}

std::vector<Eigen::Quaterniond> sample_quaternions()
{
  std::mt19937 gen(67890);
  std::normal_distribution<double> dist(0.0, 1.0);
  std::vector<Eigen::Quaterniond> out = {
    Eigen::Quaterniond::Identity(),
    Eigen::Quaterniond(Eigen::AngleAxisd(kPi / 6.0, Eigen::Vector3d::UnitZ())),
    Eigen::Quaterniond(Eigen::AngleAxisd(-kPi / 2.0, Eigen::Vector3d::UnitZ())),
    Eigen::Quaterniond(Eigen::AngleAxisd(0.3, Eigen::Vector3d::UnitX())),
    Eigen::Quaterniond(Eigen::AngleAxisd(-0.7, Eigen::Vector3d::UnitY())),
  };
  for (int i = 0; i < 200; ++i) {
    out.push_back(Eigen::Quaterniond(dist(gen), dist(gen), dist(gen), dist(gen)).normalized());
  }
  return out;
}

}  // namespace

// ---- px4_ros_com 차등 비교 ----

TEST(FramesOracle, NedEnuVectorMatchesPx4RosCom)
{
  for (const auto & v : sample_vectors()) {
    expect_vec_near(fr::ned_to_enu(v), ft::ned_to_enu_local_frame(v));
    expect_vec_near(fr::enu_to_ned(v), ft::enu_to_ned_local_frame(v));
  }
}

TEST(FramesOracle, FrdFluVectorMatchesPx4RosCom)
{
  // 동체 변환은 유한값에서만 비교한다(px4_ros_com은 Affine 곱이라 NaN을 다른 축으로 번진다).
  for (const auto & v : sample_vectors()) {
    expect_vec_near(fr::frd_to_flu(v), ft::aircraft_to_baselink_body_frame(v));
    expect_vec_near(fr::flu_to_frd(v), ft::baselink_to_aircraft_body_frame(v));
  }
}

TEST(FramesOracle, OrientationMatchesPx4RosCom)
{
  for (const auto & q : sample_quaternions()) {
    expect_same_rotation(fr::px4_to_ros_orientation(q), ft::px4_to_ros_orientation(q));
    expect_same_rotation(fr::ros_to_px4_orientation(q), ft::ros_to_px4_orientation(q));
  }
}

// ---- 알려진 값 ----

TEST(Frames, KnownVectors)
{
  // 북 1, 동 2, 아래 3 -> 동 2, 북 1, 위 -3.
  expect_vec_near(fr::ned_to_enu({1, 2, 3}), {2, 1, -3});
  expect_vec_near(fr::enu_to_ned({2, 1, -3}), {1, 2, 3});
  // 앞 1, 오른쪽 2, 아래 3 -> 앞 1, 왼쪽 -2, 위 -3.
  expect_vec_near(fr::frd_to_flu({1, 2, 3}), {1, -2, -3});
  expect_vec_near(fr::flu_to_frd({1, -2, -3}), {1, 2, 3});
}

TEST(Frames, VectorRoundTrip)
{
  for (const auto & v : sample_vectors()) {
    expect_vec_near(fr::enu_to_ned(fr::ned_to_enu(v)), v);
    expect_vec_near(fr::flu_to_frd(fr::frd_to_flu(v)), v);
  }
}

TEST(Frames, OrientationRoundTrip)
{
  for (const auto & q : sample_quaternions()) {
    expect_same_rotation(fr::ros_to_px4_orientation(fr::px4_to_ros_orientation(q)), q);
  }
}

TEST(Frames, IdentityAttitudeIsNorthFacingLevel)
{
  // PX4 단위 쿼터니언 = 기체가 북을 보고 수평. ROS에서는 x(앞)가 북(ENU y)을 본다.
  const auto q_ros = fr::px4_to_ros_orientation(Eigen::Quaterniond::Identity());
  expect_vec_near(q_ros * Eigen::Vector3d::UnitX(), {0, 1, 0});
  expect_vec_near(q_ros * Eigen::Vector3d::UnitZ(), {0, 0, 1});
}

TEST(Frames, OrientationTransformsVectorsConsistently)
{
  // 동체 벡터를 PX4 쪽에서 NED로 돌린 뒤 ENU로 바꾼 것 == FLU로 바꾼 뒤 ROS 쪽에서 돌린 것.
  for (const auto & q : sample_quaternions()) {
    const Eigen::Vector3d v_frd(0.3, -1.2, 2.5);
    const Eigen::Vector3d via_px4 = fr::ned_to_enu(q * v_frd);
    const Eigen::Vector3d via_ros = fr::px4_to_ros_orientation(q) * fr::frd_to_flu(v_frd);
    expect_vec_near(via_px4, via_ros, 1e-9);
  }
}

// ---- NaN 보존 ----

TEST(Frames, NanStaysOnItsAxis)
{
  const auto enu = fr::ned_to_enu({1, 2, kNaN});
  EXPECT_DOUBLE_EQ(enu.x(), 2);
  EXPECT_DOUBLE_EQ(enu.y(), 1);
  EXPECT_TRUE(std::isnan(enu.z()));

  const auto ned = fr::enu_to_ned({kNaN, 5, 6});
  EXPECT_DOUBLE_EQ(ned.x(), 5);
  EXPECT_TRUE(std::isnan(ned.y()));
  EXPECT_DOUBLE_EQ(ned.z(), -6);

  const auto flu = fr::frd_to_flu({1, kNaN, 3});
  EXPECT_DOUBLE_EQ(flu.x(), 1);
  EXPECT_TRUE(std::isnan(flu.y()));
  EXPECT_DOUBLE_EQ(flu.z(), -3);

  const auto frd = fr::flu_to_frd({kNaN, 2, 3});
  EXPECT_TRUE(std::isnan(frd.x()));
  EXPECT_DOUBLE_EQ(frd.y(), -2);
  EXPECT_DOUBLE_EQ(frd.z(), -3);

  // 배열 어댑터도 NaN을 그 자리에 둔다(TrajectorySetpoint의 "제어 안 함").
  const auto arr = fr::to_px4_array(
    fr::enu_to_ned(fr::to_eigen({std::numeric_limits<float>::quiet_NaN(), 2.0F, 3.0F})));
  EXPECT_FLOAT_EQ(arr[0], 2.0F);
  EXPECT_TRUE(std::isnan(arr[1]));
  EXPECT_FLOAT_EQ(arr[2], -3.0F);
}

// ---- yaw ----

TEST(FramesYaw, KnownValues)
{
  EXPECT_NEAR(fr::ned_to_enu_yaw(0.0), kPi / 2.0, kTol);    // 북 -> ENU pi/2
  EXPECT_NEAR(fr::ned_to_enu_yaw(kPi / 2.0), 0.0, kTol);    // 동 -> ENU 0
  EXPECT_NEAR(fr::ned_to_enu_yaw(kPi), -kPi / 2.0, kTol);   // 남 -> ENU -pi/2
  EXPECT_NEAR(fr::ned_to_enu_yaw(-kPi / 2.0), -kPi, kTol);  // 서 -> ENU pi == -pi
  EXPECT_NEAR(fr::enu_to_ned_yaw(kPi / 2.0), 0.0, kTol);
  EXPECT_NEAR(fr::enu_to_ned_yaw(0.0), kPi / 2.0, kTol);
}

TEST(FramesYaw, WrapPi)
{
  EXPECT_NEAR(fr::wrap_pi(0.0), 0.0, kTol);
  EXPECT_NEAR(fr::wrap_pi(kPi), -kPi, kTol);
  EXPECT_NEAR(fr::wrap_pi(-kPi), -kPi, kTol);
  EXPECT_NEAR(fr::wrap_pi(3.0 * kPi), -kPi, 1e-9);
  EXPECT_NEAR(fr::wrap_pi(-1.5 * kPi), 0.5 * kPi, 1e-9);
  EXPECT_NEAR(fr::wrap_pi(2.5 * kPi), 0.5 * kPi, 1e-9);
  EXPECT_NEAR(fr::wrap_pi(7.0), 7.0 - 2.0 * kPi, 1e-12);
  EXPECT_NEAR(fr::wrap_pi(-100.0), -100.0 + 32.0 * kPi, 1e-9);
  for (double a = -20.0; a <= 20.0; a += 0.01) {
    const double w = fr::wrap_pi(a);
    EXPECT_GE(w, -kPi);
    EXPECT_LT(w, kPi);
    EXPECT_NEAR(std::sin(w), std::sin(a), 1e-9);
    EXPECT_NEAR(std::cos(w), std::cos(a), 1e-9);
  }
  EXPECT_TRUE(std::isnan(fr::wrap_pi(kNaN)));
  EXPECT_TRUE(std::isnan(fr::wrap_pi(std::numeric_limits<double>::infinity())));
}

TEST(FramesYaw, RoundTrip)
{
  for (double yaw = -10.0; yaw <= 10.0; yaw += 0.05) {
    EXPECT_NEAR(angle_diff(fr::enu_to_ned_yaw(fr::ned_to_enu_yaw(yaw)), yaw), 0.0, 1e-9);
    EXPECT_NEAR(angle_diff(fr::ned_to_enu_yaw(fr::enu_to_ned_yaw(yaw)), yaw), 0.0, 1e-9);
  }
}

TEST(FramesYaw, NanPreserved)
{
  EXPECT_TRUE(std::isnan(fr::ned_to_enu_yaw(kNaN)));
  EXPECT_TRUE(std::isnan(fr::enu_to_ned_yaw(kNaN)));
}

TEST(FramesYaw, MatchesOrientationTransform)
{
  // PX4 yaw psi(NED)인 자세를 ROS로 바꾸면 ENU yaw가 ned_to_enu_yaw(psi)와 같다.
  for (double psi = -3.1; psi <= 3.1; psi += 0.1) {
    const Eigen::Quaterniond q_ned_frd(Eigen::AngleAxisd(psi, Eigen::Vector3d::UnitZ()));
    const Eigen::Vector3d forward =
      fr::px4_to_ros_orientation(q_ned_frd) * Eigen::Vector3d::UnitX();
    const double yaw_enu = std::atan2(forward.y(), forward.x());
    EXPECT_NEAR(angle_diff(yaw_enu, fr::ned_to_enu_yaw(psi)), 0.0, 1e-9) << "psi=" << psi;
  }
}

// ---- 분산과 배열 어댑터 ----

TEST(Frames, DiagonalVariance)
{
  expect_vec_near(fr::ned_to_enu_variance({1, 4, 9}), {4, 1, 9});
  expect_vec_near(fr::enu_to_ned_variance({4, 1, 9}), {1, 4, 9});
  // px4_ros_com의 정적 공분산 변환은 음의 분산을 낸다(결정 1 근거). 우리 쪽은 부호를 바꾸지 않는다.
  const auto v = fr::ned_to_enu_variance({0.5, 0.25, 0.125});
  EXPECT_GE(v.minCoeff(), 0.0);
}

TEST(Frames, ArrayAdapters)
{
  const std::array<float, 3> a{1.5F, -2.0F, 3.25F};
  const auto e = fr::to_eigen(a);
  EXPECT_DOUBLE_EQ(e.x(), 1.5);
  EXPECT_DOUBLE_EQ(e.y(), -2.0);
  EXPECT_DOUBLE_EQ(e.z(), 3.25);
  EXPECT_EQ(fr::to_px4_array(e), a);

  // px4_msgs 쿼터니언 배열은 (w, x, y, z)다.
  const std::array<float, 4> q{0.5F, 0.5F, -0.5F, 0.5F};
  const auto qe = fr::to_eigen_quaternion(q);
  EXPECT_DOUBLE_EQ(qe.w(), 0.5);
  EXPECT_DOUBLE_EQ(qe.x(), 0.5);
  EXPECT_DOUBLE_EQ(qe.y(), -0.5);
  EXPECT_DOUBLE_EQ(qe.z(), 0.5);
  EXPECT_EQ(fr::to_px4_array(qe), q);
  // px4_ros_com의 배열 어댑터와 같은 순서.
  expect_same_rotation(qe, ft::utils::quaternion::array_to_eigen_quat(q));
}
