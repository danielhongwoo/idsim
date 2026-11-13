# Copyright 2026 Daniel Hongwoo Lee
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""test_geo.cpp의 gz 기준값을 gz-math 7.7.0 Python 바인딩으로 뽑는다.

빌드와 테스트가 부르지 않는다. 기준값을 다시 만들 때만 sim-base 이미지(python3-gz-math7 7.7.0)에서
손으로 돌린다.

    docker run -i --rm --network none -v "$PWD:/w:ro" --entrypoint python3 idsim/sim-base:local \
        -I /w/gz_local2.py

입력은 표준 입력의 줄이다(test_geo.cpp 표의 origin/enu 열을 줄로 옮긴 것).
    F <origin_lat_deg> <origin_lon_deg> <origin_alt_m> <e> <n> <u>
        PositionTransform((e, n, u), LOCAL2, SPHERICAL). 출력: F <lat_deg> <lon_deg> <alt_m>
    I <origin_lat_deg> <origin_lon_deg> <origin_alt_m> <lat_deg> <lon_deg> <alt_m>
        PositionTransform((lat, lon, alt), SPHERICAL, LOCAL2). 출력: I <e> <n> <u>
기대 판(7.7.0)과 다르면 실패한다. PX4 태그나 gz-math 판을 올리면 이 도구와 px4_map_projection.cpp를
다시 돌려 test_geo.cpp의 기준값을 갱신한다.
heading은 0이다(생성기가 월드 SDF에 heading 0으로 쓴다). 값은 repr(왕복 가능한 double)로 쓴다.
"""

import math
import subprocess
import sys

from gz.math7 import Angle, SphericalCoordinates, Vector3d

EXPECTED_GZ_MATH = '7.7.0'


def make(lat_deg, lon_deg, alt_m):
    return SphericalCoordinates(
        SphericalCoordinates.EARTH_WGS84, Angle(math.radians(lat_deg)),
        Angle(math.radians(lon_deg)), alt_m, Angle(0.0))


def check_version():
    # 바인딩에는 버전 속성이 없어 패키지 버전으로 확인한다(예: 7.7.0-1~noble).
    ver = subprocess.run(
        ['dpkg-query', '-W', '-f=${Version}', 'python3-gz-math7'],
        capture_output=True, text=True, check=False).stdout.strip()
    print('python3-gz-math7 version:', ver, file=sys.stderr)
    if not ver.startswith(EXPECTED_GZ_MATH):
        raise SystemExit('gz-math %s expected, got %r' % (EXPECTED_GZ_MATH, ver))


def main():
    check_version()
    for line in sys.stdin:
        f = line.split()
        if not f:
            continue
        sc = make(float(f[1]), float(f[2]), float(f[3]))
        a, b, c = (float(v) for v in f[4:7])
        if f[0] == 'F':
            g = sc.position_transform(
                Vector3d(a, b, c), SphericalCoordinates.LOCAL2, SphericalCoordinates.SPHERICAL)
            print('F', repr(math.degrees(g.x())), repr(math.degrees(g.y())), repr(g.z()))
        elif f[0] == 'I':
            p = sc.position_transform(
                Vector3d(math.radians(a), math.radians(b), c),
                SphericalCoordinates.SPHERICAL, SphericalCoordinates.LOCAL2)
            print('I', repr(p.x()), repr(p.y()), repr(p.z()))
        else:
            raise SystemExit('unknown line: ' + line)


if __name__ == '__main__':
    main()
