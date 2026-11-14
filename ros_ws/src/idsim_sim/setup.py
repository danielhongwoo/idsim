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
"""idsim_sim 설치 설정(ament_python).

설치 대상은 Python 패키지 idsim_sim과 실행 파일 target_adapter뿐이다. scripts/의 셸 wrapper, config/, worlds/는
설치하지 않고 compose가 이 디렉터리를 /opt/idsim/sim에 읽기 전용으로 마운트해 쓴다.
"""

from setuptools import setup

PACKAGE = "idsim_sim"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=[PACKAGE],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Daniel Hongwoo Lee",
    maintainer_email="27140685+danielhongwoo@users.noreply.github.com",
    description="idsim 표적 어댑터: fleet 파일의 궤적 정의를 시뮬레이션 시간에 평가해 TargetState로 발행한다",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # 실행 이름은 생성기(tools/gen_compose.py)의 상수와 같아야 한다. 바꾸면 생성기와 함께 바꾼다.
            "target_adapter = idsim_sim.target_adapter:main",
        ],
    },
)
