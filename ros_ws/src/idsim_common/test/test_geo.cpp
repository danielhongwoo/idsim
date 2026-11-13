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

// 원점 이동 변환(geo.hpp)의 차등 테스트와 왕복 테스트. 노드와 DDS 참가자를 만들지 않는다.
// 결정: docs-for-agent/plan-1b-mission-target/decisions.md 쟁점 4.
//
// 기준값의 출처(원문의 판을 고정한다)
// - gz: gz-math 7.7.0(python3-gz-math7 7.7.0-1~noble, sim-base 이미지)의
//   SphericalCoordinates(EARTH_WGS84, heading 0).PositionTransform(p, LOCAL2, SPHERICAL)과 그 역
//   (SPHERICAL -> LOCAL2). 뽑은 스크립트는 test/geo_reference/gz_local2.py.
//   SphericalFromLocalPosition과 LOCAL은 heading 0에서 수평을 반전하므로 기준값으로 쓰지 않는다.
// - PX4: PX4 v1.17.0(커밋 d6f12ad1c4f70ad3230afd7d86e971421e02fef4) src/lib/geo/geo.cpp의
//   MapProjection::project, reproject를 그대로 컴파일해 뽑았다(test/geo_reference/
//   px4_map_projection.cpp). project 출력은 원문대로 float이다(%.9g로 적어 float로 정확히
//   왕복한다).
// - 사슬: gz 출력의 위경도를 PX4 project에 넣은 x, y와, z = -(gz 고도 - ref_alt).
// stack.json의 vehicles[].expect_gps는 기준값으로 쓰지 않는다. 그 값은 스모크용 기대값이라 국소
// 근사와 센서 높이를 포함한다. 기준은 위 두 라이브러리의 원값뿐이다.
//
// 기준값 갱신 절차: PX4 태그나 gz-math 판을 올리면 test/geo_reference의 두 도구
//   (gz_local2.py, px4_map_projection.cpp)를 새 판으로 다시 돌려 이 파일의 기준값과
//   위 판 표기를 갱신한다.
//
// 허용 오차
// - gz 위경도 1e-11 도(약 1e-6 m), 고도와 world ENU 1e-6 m. 식과 연산 순서를 원문대로 옮겼으므로
//   차이는 double 반올림(ECEF 크기 6.4e6 m에서 1e-9 m 수준)뿐이다.
// - PX4 x, y: 기준값 float의 ulp 하나 + 1e-6 m. 이 구현은 double을 유지하고 PX4는 float로 자른다.
// - PX4 reproject 위경도 1e-11 도. 입력 x, y는 float로 정확히 표현되는 값만 쓴다.

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

#include "idsim_common/frames.hpp"
#include "idsim_common/geo.hpp"

namespace geo = idsim_common::geo;

namespace
{

constexpr double kDegTol = 1e-11;
// z(고도 차)는 double 산술이라 float 반올림이 없으므로 PX4 쪽 z에도 같은 1e-6 m를 쓴다.
constexpr double kMeterTol = 1e-6;

struct Lla
{
  double lat;
  double lon;
  double alt;
};

struct LatLon
{
  double lat;
  double lon;
};

struct Xyz
{
  double x;
  double y;
  double z;
};

struct GzForwardCase
{
  Lla origin;
  Xyz enu;
  Lla expected;
};

struct GzInverseCase
{
  Lla origin;
  Lla point;
  Xyz expected_enu;
};

struct Px4ProjectCase
{
  LatLon ref;
  LatLon point;
  LatLon expected_xy;  // lat = x(북), lon = y(동)
};

struct Px4ReprojectCase
{
  LatLon ref;
  LatLon xy;  // lat = x(북), lon = y(동)
  LatLon expected;
};

struct ChainCase
{
  Lla origin;
  Lla ref;
  Xyz enu;
  Xyz expected_ned;
};

geo::WorldOrigin to_origin(const Lla & v) { return geo::WorldOrigin{v.lat, v.lon, v.alt}; }

geo::LocalReference to_ref(const Lla & v) { return geo::LocalReference{v.lat, v.lon, v.alt}; }

geo::LocalReference to_ref(const LatLon & v) { return geo::LocalReference{v.lat, v.lon, 0.0}; }

Eigen::Vector3d to_vec(const Xyz & v) { return Eigen::Vector3d(v.x, v.y, v.z); }

// PX4 float 출력과의 허용 오차.
double float_tol(double expected)
{
  const auto f = static_cast<float>(std::fabs(expected));
  const float ulp = std::nextafter(f, std::numeric_limits<float>::infinity()) - f;
  return static_cast<double>(ulp) + kMeterTol;
}

// ---- 기준값. 원점: 서울시청(config/fleet.yaml 기본값)과 PX4 SITL 기본 원점(취리히) ----
// 기준(ref): 원점과 같은 점, 기체 1 스폰 (6, -3, 0)의 gz 위경도와 고도 38.25, 약 1 km 떨어진 점.

const GzForwardCase kGzForward[] = {
  {{37.5665, 126.978, 38.0}, {0.0, 0.0, 0.0}, {37.5665, 126.978, 38.0}},
  {{37.5665, 126.978, 38.0},
   {100.0, 0.0, 0.0},
   {37.566499994574045, 126.97913189404852, 38.000782947055995}},
  {{37.5665, 126.978, 38.0}, {0.0, 100.0, 0.0}, {37.56740099050137, 126.978, 38.000786263495684}},
  {{37.5665, 126.978, 38.0},
   {6.0, -3.0, 0.24},
   {37.566472970264314, 126.97806791361582, 38.24000352434814}},
  {{37.5665, 126.978, 38.0},
   {-250.5, 400.25, 30.0},
   {37.5701061625843, 126.97516448203655, 68.01750885788351}},
  {{37.5665, 126.978, 38.0},
   {1500.0, -2000.0, 120.0},
   {37.54847928164673, 126.9949740024343, 158.4906594287604}},
  {{37.5665, 126.978, 38.0},
   {-4000.0, 3000.0, 10.0},
   {37.59352092063357, 126.9327079528947, 49.96034572273493}},
  {{47.397742, 8.545594, 488.0},
   {0.0, 0.0, 0.0},
   {47.39774200000002, 8.545594, 488.00000000186265}},
  {{47.397742, 8.545594, 488.0},
   {100.0, 0.0, 0.0},
   {47.39774199234773, 8.546918582113282, 488.0007824450731}},
  {{47.397742, 8.545594, 488.0},
   {0.0, 100.0, 0.0},
   {47.39864138473046, 8.545594, 488.0007848618552}},
  {{47.397742, 8.545594, 488.0},
   {-250.5, 400.25, 30.0},
   {47.40134172155157, 8.542275711381029, 518.0174832604825}},
  {{47.397742, 8.545594, 488.0},
   {1500.0, -2000.0, 120.0},
   {47.37975289440935, 8.565455598350734, 608.4899859828874}},
  {{37.5665, 126.978, 38.0},
   {6.0, -3.0, 0.0},
   {37.566472970263305, 126.97806791361839, 38.000003525055945}},
};
const GzInverseCase kGzInverse[] = {
  {{37.5665, 126.978, 38.0},
   {37.567397071917405, 126.97857297045178, 50.5},
   {50.61999422909217, 99.56543041557711, 12.49901993813441}},
  {{37.5665, 126.978, 38.0},
   {37.555699616345834, 127.01657584517122, 118.0},
   {3408.613596698964, -1198.0376564009534, 78.9774814331995}},
  {{37.5665, 126.978, 38.0}, {37.566499999999998, 126.97799999999999, 38.0}, {0.0, 0.0, 0.0}},
  {{37.5665, 126.978, 38.0},
   {37.566567398809312, 126.97783816069925, 43.5},
   {-14.298095701352079, 7.480542097541872, 5.499979594862647}},
  {{47.397742, 8.545594, 488.0},
   {47.415726704524452, 8.525658512536495, 588.0},
   {-1504.5510678684377, 1999.8945552720147, 99.50897668688822}},
  {{37.5665, 126.978, 38.0},
   {37.566845281570728, 126.98091763466313, 72.5},
   {257.7659066444309, 38.326650384031936, 34.4946823756915}},
  {{37.5665, 126.978, 38.0}, {37.5665, 126.978, 38.0}, {0.0, 0.0, 0.0}},
  {{37.5665, 126.978, 38.0},
   {37.5701061625843, 126.97516448203655, 68.01750885788351},
   {-250.50000000052424, 400.24999999928804, 30.000000000026716}},
};
const Px4ProjectCase kPx4Project[] = {
  {{37.5665, 126.978}, {37.5665, 126.978}, {0.0, 0.0}},
  {{37.5665, 126.978}, {37.566499994574045, 126.97913189404852}, {-2.54318024e-06, 99.7631531}},
  {{37.5665, 126.978}, {37.56740099050137, 126.978}, {100.18557, 0.0}},
  {{37.5665, 126.978}, {37.566472970264314, 126.97806791361582}, {-3.00556731, 5.98578882}},
  {{37.5665, 126.978}, {37.5701061625843, 126.97516448203655}, {400.990753, -249.905472}},
  {{37.5665, 126.978}, {37.54847928164673, 126.9949740024343}, {-2003.67737, 1496.42065}},
  {{37.5665, 126.978}, {37.59352092063357, 126.9327079528947}, {3005.55103, -3990.51294}},
  {{37.566472970263305, 126.97806791361839}, {37.5665, 126.978}, {3.00557184, -5.98578691}},
  {{37.566472970263305, 126.97806791361839},
   {37.566499994574045, 126.97913189404852},
   {3.00549722, 93.7773666}},
  {{37.566472970263305, 126.97806791361839},
   {37.56740099050137, 126.978},
   {103.191147, -5.98571444}},
  {{37.566472970263305, 126.97806791361839},
   {37.566472970264314, 126.97806791361582},
   {1.1246437e-07, -2.26505506e-07}},
  {{37.566472970263305, 126.97806791361839},
   {37.5701061625843, 126.97516448203655},
   {403.996521, -255.890961}},
  {{37.566472970263305, 126.97806791361839},
   {37.54847928164673, 126.9949740024343},
   {-2000.67285, 1490.43335}},
  {{37.566472970263305, 126.97806791361839},
   {37.59352092063357, 126.9327079528947},
   {3008.55957, -3996.49658}},
  {{37.57, 126.99}, {37.5665, 126.978}, {-389.114716, -1057.65894}},
  {{37.57, 126.99}, {37.566499994574045, 126.97913189404852}, {-389.127441, -957.895752}},
  {{37.57, 126.99}, {37.56740099050137, 126.978}, {-288.929138, -1057.64612}},
  {{37.57, 126.99}, {37.566472970264314, 126.97806791361582}, {-392.121033, -1051.67346}},
  {{37.57, 126.99}, {37.5701061625843, 126.97516448203655}, {11.9079533, -1307.51318}},
  {{37.57, 126.99}, {37.54847928164673, 126.9949740024343}, {-2392.98315, 438.50589}},
  {{37.57, 126.99}, {37.59352092063357, 126.9327079528947}, {2616.94604, -5047.7876}},
  {{47.397742, 8.545594}, {47.39774200000002, 8.545594}, {2.47563081e-09, 0.0}},
  {{47.397742, 8.545594}, {47.39774199234773, 8.546918582113282}, {-2.61744913e-06, 99.699173}},
  {{47.397742, 8.545594}, {47.39864138473046, 8.545594}, {100.007019, 0.0}},
  {{47.397742, 8.545594}, {47.40134172155157, 8.542275711381029}, {400.276093, -249.745209}},
  {{47.397742, 8.545594}, {47.37975289440935, 8.565455598350734}, {-2000.10645, 1495.46106}},
};
const Px4ReprojectCase kPx4Reproject[] = {
  {{37.5665, 126.978}, {99.75, 50.5}, {37.567397071917405, 126.97857297045178}},
  {{37.5665, 126.978}, {-1200.25, 3400.5}, {37.555699616345834, 127.01657584517122}},
  {{37.5665, 126.978}, {0.0, 0.0}, {37.566499999999998, 126.97799999999999}},
  {{37.566472970263305, 126.97806791361839},
   {10.5, -20.25},
   {37.566567398809312, 126.97783816069925}},
  {{47.397742, 8.545594}, {2000.0, -1500.0}, {47.415726704524452, 8.525658512536495}},
  {{37.57, 126.99}, {-350.75, -800.5}, {37.566845281570728, 126.98091763466313}},
};
const ChainCase kChain[] = {
  {{37.5665, 126.978, 38.0}, {37.5665, 126.978, 38.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, -0.0}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {100.0, 0.0, 0.0},
   {-2.54318024e-06, 99.7631531, -0.0007829470559954643}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {0.0, 100.0, 0.0},
   {100.18557, 0.0, -0.00078626349568367}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {6.0, -3.0, 0.24},
   {-3.00556731, 5.98578882, -0.24000352434813976}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {-250.5, 400.25, 30.0},
   {400.990753, -249.905472, -30.017508857883513}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {1500.0, -2000.0, 120.0},
   {-2003.67737, 1496.42065, -120.49065942876041}},
  {{37.5665, 126.978, 38.0},
   {37.5665, 126.978, 38.0},
   {-4000.0, 3000.0, 10.0},
   {3005.55103, -3990.51294, -11.960345722734928}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {0.0, 0.0, 0.0},
   {3.00557184, -5.98578691, 0.25}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {100.0, 0.0, 0.0},
   {3.00549722, 93.7773666, 0.24921705294400454}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {0.0, 100.0, 0.0},
   {103.191147, -5.98571444, 0.24921373650431633}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {6.0, -3.0, 0.24},
   {1.1246437e-07, -2.26505506e-07, 0.009996475651860237}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {-250.5, 400.25, 30.0},
   {403.996521, -255.890961, -29.767508857883513}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {1500.0, -2000.0, 120.0},
   {-2000.67285, 1490.43335, -120.24065942876041}},
  {{37.5665, 126.978, 38.0},
   {37.566472970263305, 126.97806791361839, 38.25},
   {-4000.0, 3000.0, 10.0},
   {3008.55957, -3996.49658, -11.710345722734928}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {0.0, 0.0, 0.0},
   {-389.114716, -1057.65894, 14.5}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {100.0, 0.0, 0.0},
   {-389.127441, -957.895752, 14.499217052944005}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {0.0, 100.0, 0.0},
   {-288.929138, -1057.64612, 14.499213736504316}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {6.0, -3.0, 0.24},
   {-392.121033, -1051.67346, 14.25999647565186}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {-250.5, 400.25, 30.0},
   {11.9079533, -1307.51318, -15.517508857883513}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {1500.0, -2000.0, 120.0},
   {-2392.98315, 438.50589, -105.99065942876041}},
  {{37.5665, 126.978, 38.0},
   {37.57, 126.99, 52.5},
   {-4000.0, 3000.0, 10.0},
   {2616.94604, -5047.7876, 2.539654277265072}},
  {{47.397742, 8.545594, 488.0},
   {47.397742, 8.545594, 488.0},
   {0.0, 0.0, 0.0},
   {2.47563081e-09, 0.0, -1.862645149230957e-09}},
  {{47.397742, 8.545594, 488.0},
   {47.397742, 8.545594, 488.0},
   {100.0, 0.0, 0.0},
   {-2.61744913e-06, 99.699173, -0.0007824450731277466}},
  {{47.397742, 8.545594, 488.0},
   {47.397742, 8.545594, 488.0},
   {0.0, 100.0, 0.0},
   {100.007019, 0.0, -0.0007848618552088737}},
  {{47.397742, 8.545594, 488.0},
   {47.397742, 8.545594, 488.0},
   {-250.5, 400.25, 30.0},
   {400.276093, -249.745209, -30.01748326048255}},
  {{47.397742, 8.545594, 488.0},
   {47.397742, 8.545594, 488.0},
   {1500.0, -2000.0, 120.0},
   {-2000.10645, 1495.46106, -120.48998598288745}},
};

}  // namespace

TEST(Geo, GzLocal2Forward)
{
  for (const auto & c : kGzForward) {
    const auto g = geo::world_enu_to_geodetic(to_origin(c.origin), to_vec(c.enu));
    EXPECT_NEAR(g.lat_deg, c.expected.lat, kDegTol) << c.enu.x << " " << c.enu.y;
    EXPECT_NEAR(g.lon_deg, c.expected.lon, kDegTol) << c.enu.x << " " << c.enu.y;
    EXPECT_NEAR(g.alt_m, c.expected.alt, kMeterTol) << c.enu.x << " " << c.enu.y;
  }
}

TEST(Geo, GzLocal2Inverse)
{
  for (const auto & c : kGzInverse) {
    const auto enu = geo::geodetic_to_world_enu(
      to_origin(c.origin), geo::Geodetic{c.point.lat, c.point.lon, c.point.alt});
    EXPECT_NEAR(enu.x(), c.expected_enu.x, kMeterTol) << c.point.lat << " " << c.point.lon;
    EXPECT_NEAR(enu.y(), c.expected_enu.y, kMeterTol) << c.point.lat << " " << c.point.lon;
    EXPECT_NEAR(enu.z(), c.expected_enu.z, kMeterTol) << c.point.lat << " " << c.point.lon;
  }
}

TEST(Geo, Px4MapProjectionProject)
{
  for (const auto & c : kPx4Project) {
    const auto ned =
      geo::geodetic_to_local_ned(to_ref(c.ref), geo::Geodetic{c.point.lat, c.point.lon, 0.0});
    EXPECT_NEAR(ned.x(), c.expected_xy.lat, float_tol(c.expected_xy.lat)) << c.point.lat;
    EXPECT_NEAR(ned.y(), c.expected_xy.lon, float_tol(c.expected_xy.lon)) << c.point.lon;
  }
}

TEST(Geo, Px4MapProjectionReproject)
{
  for (const auto & c : kPx4Reproject) {
    const auto g =
      geo::local_ned_to_geodetic(to_ref(c.ref), Eigen::Vector3d(c.xy.lat, c.xy.lon, 0.0));
    EXPECT_NEAR(g.lat_deg, c.expected.lat, kDegTol) << c.xy.lat << " " << c.xy.lon;
    EXPECT_NEAR(g.lon_deg, c.expected.lon, kDegTol) << c.xy.lat << " " << c.xy.lon;
  }
}

TEST(Geo, Px4AltitudeIsDifferenceFromRefAlt)
{
  const geo::LocalReference ref{37.5665, 126.978, 38.25};
  const auto ned = geo::geodetic_to_local_ned(ref, geo::Geodetic{37.5665, 126.978, 50.75});
  EXPECT_DOUBLE_EQ(ned.z(), -12.5);
  const auto g = geo::local_ned_to_geodetic(ref, Eigen::Vector3d(0.0, 0.0, -12.5));
  EXPECT_DOUBLE_EQ(g.alt_m, 50.75);
}

TEST(Geo, ChainWorldEnuToLocalNed)
{
  for (const auto & c : kChain) {
    const auto ned = geo::world_enu_to_local_ned(to_origin(c.origin), to_ref(c.ref), to_vec(c.enu));
    const auto at = ::testing::Message() << "enu (" << c.enu.x << ", " << c.enu.y << ", " << c.enu.z
                                         << ") ref " << c.ref.lat << " " << c.ref.lon;
    EXPECT_NEAR(ned.x(), c.expected_ned.x, float_tol(c.expected_ned.x)) << at;
    EXPECT_NEAR(ned.y(), c.expected_ned.y, float_tol(c.expected_ned.y)) << at;
    // z는 double 고도 차라 float ulp 허용이 필요 없다(kMeterTol 주석).
    EXPECT_NEAR(ned.z(), c.expected_ned.z, kMeterTol) << at;
  }
}

TEST(Geo, ChainIsNotATranslation)
{
  // decisions.md 쟁점 4 근거의 값: 원점 위도 37.57도에서 world 동쪽 100 m는 PX4 로컬 99.763 m,
  // 북쪽 100 m는 100.186 m다. 평행 이동(frames::enu_to_ned)으로 근사하면 약 20 cm 틀린다.
  const geo::WorldOrigin origin{37.5665, 126.978, 38.0};
  const geo::LocalReference ref{37.5665, 126.978, 38.0};
  const auto east = geo::world_enu_to_local_ned(origin, ref, Eigen::Vector3d(100.0, 0.0, 0.0));
  const auto north = geo::world_enu_to_local_ned(origin, ref, Eigen::Vector3d(0.0, 100.0, 0.0));
  EXPECT_NEAR(east.y(), 99.763, 5e-4);
  EXPECT_NEAR(north.x(), 100.186, 5e-4);
  const auto naive = idsim_common::frames::enu_to_ned(Eigen::Vector3d(100.0, 0.0, 0.0));
  EXPECT_GT((east - naive).norm(), 0.2);
}

TEST(Geo, NonFiniteInputGivesNonFiniteOutput)
{
  // 입력 검사를 하지 않는다. 비유한 값은 position_setpoint가 거부하도록 비유한 채로 나온다.
  const geo::WorldOrigin origin{37.5665, 126.978, 38.0};
  const geo::LocalReference ref{37.5665, 126.978, 38.0};
  const double nan = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(
    geo::world_enu_to_local_ned(origin, ref, Eigen::Vector3d(nan, 0.0, 0.0)).allFinite());
  const geo::LocalReference bad_ref{nan, 126.978, 38.0};
  EXPECT_FALSE(geo::world_enu_to_local_ned(origin, bad_ref, Eigen::Vector3d::Zero()).allFinite());
}

// ---- 왕복 ----
// 원점 넷(서울, 취리히, 남반구 시드니, 고위도 70도)과 기준 셋(원점, 원점에서 수 m, 약 1.5 km)에서
// world ENU 격자(수평 +-5 km, 고도 0-300 m)를 왕복시킨다. 오차의 원천은 gz geodetic 닫힌 식이
// 정확한 역이 아닌 것뿐이고(MapProjection의 project와 reproject는 서로 정확한 역이다), 측정값은
// 1e-8 m 수준이다(실측 최대 1.11e-8 m). 허용 1e-6 m.

namespace
{

struct RoundTripSetup
{
  geo::WorldOrigin origin;
  geo::LocalReference ref;
};

std::vector<RoundTripSetup> round_trip_setups()
{
  const geo::WorldOrigin origins[] = {
    {37.5665, 126.978, 38.0},
    {47.397742, 8.545594, 488.0},
    {-33.8688, 151.2093, 58.0},
    {70.0, -20.0, 0.0},
  };
  std::vector<RoundTripSetup> out;
  for (const auto & o : origins) {
    out.push_back({o, geo::LocalReference{o.lat_deg, o.lon_deg, o.alt_m}});
    const auto near = geo::world_enu_to_geodetic(o, Eigen::Vector3d(6.0, -3.0, 0.0));
    out.push_back({o, geo::LocalReference{near.lat_deg, near.lon_deg, o.alt_m + 0.25}});
    const auto far = geo::world_enu_to_geodetic(o, Eigen::Vector3d(-900.0, 1200.0, 15.0));
    out.push_back({o, geo::LocalReference{far.lat_deg, far.lon_deg, far.alt_m}});
  }
  return out;
}

std::vector<Eigen::Vector3d> round_trip_points()
{
  std::vector<Eigen::Vector3d> out;
  for (double x = -5000.0; x <= 5000.0; x += 1250.0) {
    for (double y = -5000.0; y <= 5000.0; y += 1250.0) {
      for (const double z : {0.0, 2.5, 30.0, 300.0}) {
        out.emplace_back(x + 0.37, y - 0.61, z);
      }
    }
  }
  return out;
}

// xml에 0.000000으로 남지 않도록 지수 표기로 기록한다.
std::string sci(double v)
{
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%.3e", v);
  return buf;
}

}  // namespace

TEST(Geo, RoundTripWorldEnu)
{
  double max_err = 0.0;
  for (const auto & s : round_trip_setups()) {
    for (const auto & p : round_trip_points()) {
      const auto ned = geo::world_enu_to_local_ned(s.origin, s.ref, p);
      const auto back = geo::local_ned_to_world_enu(s.origin, s.ref, ned);
      const double err = (back - p).norm();
      max_err = std::max(max_err, err);
      EXPECT_LT(err, kMeterTol) << "origin " << s.origin.lat_deg << " p " << p.transpose();
    }
  }
  std::cout << "world ENU -> local NED -> world ENU max error [m]: " << max_err << "\n";
  RecordProperty("max_error_m", sci(max_err));
}

TEST(Geo, RoundTripLocalNed)
{
  double max_err = 0.0;
  for (const auto & s : round_trip_setups()) {
    for (const auto & p : round_trip_points()) {
      const Eigen::Vector3d ned = idsim_common::frames::enu_to_ned(p);
      const auto enu = geo::local_ned_to_world_enu(s.origin, s.ref, ned);
      const auto back = geo::world_enu_to_local_ned(s.origin, s.ref, enu);
      const double err = (back - ned).norm();
      max_err = std::max(max_err, err);
      EXPECT_LT(err, kMeterTol) << "origin " << s.origin.lat_deg << " ned " << ned.transpose();
    }
  }
  std::cout << "local NED -> world ENU -> local NED max error [m]: " << max_err << "\n";
  RecordProperty("max_error_m", sci(max_err));
}
