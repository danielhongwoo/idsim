"""tests/tools 옵션. --update-golden: 생성기 골든(tests/fixtures/gen_compose/)을 다시 쓴다."""
import os

import pytest


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", default=False,
                     help="tests/fixtures/gen_compose/<사례>/의 compose.yaml, stack.json을 다시 쓴다(CI에서는 거부)")


def pytest_configure(config):
    # CI에서 실수로 켜도 골든이 통과로 바뀌지 않게 막는다(lint 잡은 저장소를 읽기 전용으로 마운트하지만 이중 방어)
    if config.getoption("--update-golden", default=False) and (
            os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
        raise pytest.UsageError("--update-golden은 CI에서 쓸 수 없다")
