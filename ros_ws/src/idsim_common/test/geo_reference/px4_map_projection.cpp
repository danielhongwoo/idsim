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

// test_geo.cpp의 PX4 기준값을 PX4 v1.17.0 src/lib/geo/geo.cpp의 MapProjection으로 뽑는다.
//
// 빌드와 테스트가 부르지 않는다(CMakeLists.txt에 넣지 않는다). 기준값을 다시 만들 때만 PX4 v1.17.0
// 소스 트리(<px4>. src/lib/geo, src/lib/mathlib, src/lib/matrix, src/include,
// platforms/common/include만 있으면 된다)를 두고 손으로 컴파일한다. <stub>은 빈
// px4_boardconfig.h 하나를 둔 디렉터리다(빌드 시스템이 생성하는 헤더이고 geo.cpp는 그 내용을 쓰지
// 않는다).
//
//   g++ -std=c++17 -O0 -D__PX4_POSIX -I<stub> -I<px4>/src -I<px4>/src/lib -I<px4>/src/lib/matrix \
//     -I<px4>/src/include -I<px4>/platforms/common/include \
//     px4_map_projection.cpp <px4>/src/lib/geo/geo.cpp -o px4_map_projection
//
// 입력은 표준 입력의 줄이다.
//   P <ref_lat_deg> <ref_lon_deg> <lat_deg> <lon_deg>   project. 출력: P <x> <y> (float, %.9g)
//   R <ref_lat_deg> <ref_lon_deg> <x> <y>               reproject(x, y는 float로 읽는다).
//                                                       출력: R <lat_deg> <lon_deg> (%.17g)

#include <cstdio>
#include <cstdlib>

#include "lib/geo/geo.h"

int main()
{
  char kind = 0;
  double ref_lat = 0.0;
  double ref_lon = 0.0;
  double a = 0.0;
  double b = 0.0;
  while (std::scanf(" %c %lf %lf %lf %lf", &kind, &ref_lat, &ref_lon, &a, &b) == 5) {
    MapProjection proj(ref_lat, ref_lon);
    if (kind == 'P') {
      float x = 0.0F;
      float y = 0.0F;
      proj.project(a, b, x, y);
      std::printf("P %.9g %.9g\n", static_cast<double>(x), static_cast<double>(y));
    } else if (kind == 'R') {
      double lat = 0.0;
      double lon = 0.0;
      proj.reproject(static_cast<float>(a), static_cast<float>(b), lat, lon);
      std::printf("R %.17g %.17g\n", lat, lon);
    } else {
      return EXIT_FAILURE;
    }
  }
  return EXIT_SUCCESS;
}
