"""tests/tools 옵션. --update-golden: 생성기 골든(tests/fixtures/gen_compose/)을 다시 쓴다."""


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", default=False,
                     help="tests/fixtures/gen_compose/<사례>/의 compose.yaml, stack.json을 다시 쓴다")
