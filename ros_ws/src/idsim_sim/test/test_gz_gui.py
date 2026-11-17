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
"""scripts/gz_gui.sh의 화면 방식 선택과 가상 화면 크기(컨테이너, X, gz 없이 bash로 source해 본다).

방식 선택 규칙: IDSIM_GZ_GUI_DISPLAY가 auto(또는 빈 값)이면 DISPLAY가 비어 있지 않고 Xauthority 파일을
읽을 수 있고 비어 있지 않을 때 host, 아니면 virtual. host, virtual은 그대로, 그 밖의 값은 종료 코드 1.
"""

import os
from pathlib import Path
import subprocess

import pytest

PKG = Path(__file__).resolve().parents[1]
SCRIPT = PKG / "scripts" / "gz_gui.sh"
GUI_CONFIG = PKG / "config" / "gui.config"


def _call(func, *args):
    # source해도 main은 돌지 않는다. 함수만 불러 stdout과 종료 코드를 본다
    return subprocess.run(
        ["bash", "-c", f'source "$0"; {func} "$@"', str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def xauth(tmp_path):
    full = tmp_path / "xauth_full"
    full.write_bytes(b"\x01\x00cookie")
    empty = tmp_path / "xauth_empty"
    empty.write_bytes(b"")
    return {"full": str(full), "empty": str(empty), "missing": str(tmp_path / "none")}


@pytest.mark.parametrize(
    "request_value, display, xauth_kind, expected",
    [
        ("auto", ":0", "full", "host"),
        ("", ":0", "full", "host"),
        ("auto", "", "full", "virtual"),
        ("auto", ":0", "empty", "virtual"),  # Mac: Xauthority 자리에 /dev/null
        ("auto", ":0", "missing", "virtual"),
        ("auto", "", "empty", "virtual"),
        ("host", "", "empty", "host"),  # host는 점검을 main이 하고 안내와 함께 1로 끝낸다
        ("virtual", ":0", "full", "virtual"),
    ],
)
def test_select_display_mode(xauth, request_value, display, xauth_kind, expected):
    r = _call("select_display_mode", request_value, display, xauth[xauth_kind])
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"{expected}\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 권한 0의 파일도 읽는다")
def test_unreadable_xauth_selects_virtual(xauth):
    os.chmod(xauth["full"], 0)
    r = _call("select_display_mode", "auto", ":0", xauth["full"])
    assert r.stdout == "virtual\n"


@pytest.mark.parametrize("bad", ["Auto", "x11", "vnc", " host"])
def test_select_display_mode_rejects_unknown(xauth, bad):
    r = _call("select_display_mode", bad, ":0", xauth["full"])
    assert r.returncode == 1
    assert r.stdout == ""
    assert "IDSIM_GZ_GUI_DISPLAY" in r.stderr


def test_sourcing_does_not_run_main():
    r = subprocess.run(
        ["bash", "-c", 'source "$0"', str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DISPLAY": ""},
    )
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_virtual_screen_matches_gui_config_window():
    # 창 관리자가 없으므로 가상 화면 크기를 gui.config의 창 크기와 같게 해야 창이 화면을 채운다
    r = _call("gui_window_geometry", str(GUI_CONFIG))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "1000x845\n"


def test_window_geometry_reads_only_window_block(tmp_path):
    cfg = tmp_path / "gui.config"
    cfg.write_text(
        "<plugin><width>1</width><height>2</height></plugin>\n"
        "<window>\n  <width> 1280 </width>\n  <height>720</height>\n</window>\n",
        encoding="utf-8",
    )
    r = _call("gui_window_geometry", str(cfg))
    assert r.stdout == "1280x720\n"


def test_window_geometry_missing_fails(tmp_path):
    cfg = tmp_path / "gui.config"
    cfg.write_text("<window><width>1280</width></window>\n", encoding="utf-8")
    r = _call("gui_window_geometry", str(cfg))
    assert r.returncode == 1
    assert r.stdout == ""
