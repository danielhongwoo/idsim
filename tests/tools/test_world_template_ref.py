"""월드 템플릿의 ref 줄이 docker/versions.env의 PX4_GZ_MODELS_REF와 같은지 본다.

내용 대조(sim-base의 원본 default.sdf와의 비교)는 스모크 images 단계가 한다. 여기서는 ref 줄만 본다.
"""

import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATE = os.path.join(REPO, "ros_ws/src/idsim_sim/worlds/idsim_base.sdf")
VERSIONS = os.path.join(REPO, "docker/versions.env")
REF_RE = re.compile(r"^\s*PX4_GZ_MODELS_REF=([0-9a-f]{40})\s*$", re.M)


def template_refs(text):
    return REF_RE.findall(text)


def versions_ref():
    with open(VERSIONS, encoding="utf-8") as f:
        m = re.search(r"^PX4_GZ_MODELS_REF=(\S+)\s*$", f.read(), re.M)
    assert m, "versions.env에 PX4_GZ_MODELS_REF가 없다"
    return m.group(1)


def test_template_ref_equals_versions_env():
    with open(TEMPLATE, encoding="utf-8") as f:
        refs = template_refs(f.read())
    assert len(refs) == 1, f"템플릿에 ref 줄이 정확히 하나여야 한다: {len(refs)}개"
    assert refs[0] == versions_ref()


def test_ref_regex_rejects_bad_lines():
    h = "a" * 40
    assert template_refs(f"    PX4_GZ_MODELS_REF={h}\n") == [h]
    assert template_refs("PX4_GZ_MODELS_REF=abc\n") == []
    assert template_refs(f"PX4_GZ_MODELS_REF={'A' * 40}\n") == []
    assert template_refs("") == []
    assert len(template_refs(f"PX4_GZ_MODELS_REF={h}\nPX4_GZ_MODELS_REF={h}\n")) == 2
