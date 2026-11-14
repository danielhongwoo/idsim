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
"""config/gui.config의 plugin 목록 고정(decisions.md 쟁점 2).

고정 목록은 gz-sim8 기본 gui.config(/usr/share/gz/gz-sim8/gui/gui.config, sim-base 이미지의 libgz-sim8 8.15.0)에서
WorldControl을 빼고 GridConfig를 더한 것이다. 설정의 <topic>으로 구독 대상을 받는 plugin(TopicEcho,
TopicViewer, Plotting 계열)이 들어와 dynamic_pose 같은 토픽을 화면에 띄우는 것을 설정 파일 수준에서 막는다.
Gazebo를 올리거나 목록을 바꾸면 이 목록을 그 판의 기본 설정에서 다시 만든다.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

GUI_CONFIG = Path(__file__).resolve().parents[1] / "config" / "gui.config"

EXPECTED_PLUGINS = [
    "MinimalScene",
    "GridConfig",  # idsim 추가
    "EntityContextMenuPlugin",
    "GzSceneManager",
    "InteractiveViewControl",
    "CameraTracking",
    "MarkerManager",
    "SelectEntities",
    "Spawn",
    "VisualizationCapabilities",
    # WorldControl은 뺐다(시뮬레이션 시계를 화면에서 멈추지 못하게)
    "WorldStats",
    "Shapes",
    "Lights",
    "TransformControl",
    "Screenshot",
    "CopyPaste",
    "ComponentInspector",
    "EntityTree",
]


def _text():
    return GUI_CONFIG.read_text(encoding="utf-8")


def test_plugin_list_is_fixed():
    # gui.config는 최상위 요소가 여럿이라 XML 문서가 아니다. 선언을 떼고 감싸서 읽는다
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", _text())
    root = ET.fromstring(f"<root>{body}</root>")
    got = [el.get("filename") for el in root.iter("plugin")]
    assert got == EXPECTED_PLUGINS


def test_plugin_count_matches_raw_text():
    # 파서가 놓친 plugin(주석 밖 문자열 등)이 없는지 원문 개수로도 본다
    assert len(re.findall(r"<plugin\b", re.sub(r"<!--.*?-->", "", _text(), flags=re.S))) == len(EXPECTED_PLUGINS)


def test_no_dynamic_pose():
    assert "dynamic_pose" not in _text()
