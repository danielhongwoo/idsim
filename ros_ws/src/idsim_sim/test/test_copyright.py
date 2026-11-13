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
"""Apache-2.0 머리말 검사(ament_copyright). 저장소 규칙: 새 소스에 머리말을 넣고 검사를 켠 채로 둔다."""

from pathlib import Path

from ament_copyright.main import main


def test_copyright():
    pkg = Path(__file__).resolve().parents[1]
    assert main(argv=[str(pkg / "idsim_sim"), str(pkg / "test"), str(pkg / "setup.py")]) == 0
