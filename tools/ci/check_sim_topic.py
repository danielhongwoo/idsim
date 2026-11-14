#!/usr/bin/env python3
"""운용 패키지가 `/sim/` 토픽을 쓰지 않는지 검사한다. tools/ci/lint.sh의 sim-topic이 부른다. 담당: devops-engineer.

`/sim/<vehicle_id>/pose` 같은 시뮬레이터 전용 토픽은 SITL 정답 판정만 쓴다(decisions.md 쟁점 5).
운용 패키지가 이 토픽에 기대면 실기체에서 없는 입력에 의존하게 된다.

검사 대상(is_target): 운용 패키지의 소스, launch, params YAML.
  - 운용 패키지: ros_ws/src/idsim_common, idsim_mission, idsim_telemetry, idsim_fleet, gateway/.
    아직 없는 패키지는 디렉터리가 생기는 순간 대상이 된다.
  - 파일 종류: C/C++ 소스와 헤더(.inc 포함), .py(launch 포함), .rs, .xml(launch), .yaml, .yml.
  - 생성기 golden 중 ops-N params(tests/fixtures/gen_compose/<사례>/params/ops-*.yaml).
  - 제외: test, tests 디렉터리 아래(테스트는 이 문자열이 없음을 단정하느라 쓸 수 있다), 문서(.md)와 그 밖의 종류.
위반은 줄 안에 부분 문자열 `/sim/`이 있는 것이다. 주석도 센다(주석에 쓸 이유가 없다).
실수 방지 수준이며 보안 경계가 아니다(이름을 조립해서 쓰는 우회는 코드 검토가 본다).

사용법: check_sim_topic.py <파일>...
  대상이 아닌 경로는 건너뛴다. 마지막 줄에 `scanned=<N>`을 stdout에 쓴다. 위반이 있으면 `경로:줄:내용`을 찍고 종료 코드 1.
  검사한 파일이 0개여도 종료 코드 1이다(운용 패키지가 이미 있으므로 0은 대상 선별이 깨졌다는 뜻이다).
"""
import os
import re
import sys

OPERATIONAL_ROOTS = (
    "ros_ws/src/idsim_common/",
    "ros_ws/src/idsim_mission/",
    "ros_ws/src/idsim_telemetry/",
    "ros_ws/src/idsim_fleet/",
    "gateway/",
)
OPS_PARAMS_RE = re.compile(r"^tests/fixtures/gen_compose/[^/]+/params/ops-[0-9]+\.yaml$")
SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inc", ".py", ".rs", ".xml", ".yaml", ".yml")
EXCLUDED_DIRS = ("test", "tests")
NEEDLE = "/sim/"


def is_target(path):
    """저장소 루트 기준 상대 경로(/로 구분)가 검사 대상인가."""
    if OPS_PARAMS_RE.match(path):
        return True
    if not path.startswith(OPERATIONAL_ROOTS) or not path.endswith(SUFFIXES):
        return False
    return not any(part in EXCLUDED_DIRS for part in path.split("/")[:-1])


def violations(path, text):
    """[(줄 번호, 줄 내용)]. 줄 번호는 1부터."""
    return [(i, line.rstrip("\n")) for i, line in enumerate(text.splitlines(), 1) if NEEDLE in line]


def main(argv):
    scanned, bad = 0, 0
    for path in argv:
        rel = os.path.normpath(path).replace(os.sep, "/")
        if not is_target(rel):
            continue
        scanned += 1
        with open(path, encoding="utf-8") as f:
            for no, line in violations(rel, f.read()):
                print(f"{rel}:{no}:{line}")
                bad += 1
    print(f"scanned={scanned}")
    if scanned == 0:
        print("검사 대상이 0개다. 대상 선별(is_target, lint.sh의 후보 경로)이 깨졌다")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
