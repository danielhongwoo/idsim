"""capture.sh 원문 산출물을 골든 디렉터리로 정규화하는 진입점.

사용: python3 -m tests.support.normalize --raw OUT_DIR --ns NS [--out GOLDEN_DIR]
      [--update | --check]
저장소 루트에서 실행한다(tests 패키지를 import해야 한다).
"""
import argparse
import difflib
import os
import shutil
import sys
import tempfile

from tests.support import golden

# 골든 env.txt의 키 이름. 키 이름이 바뀌면 golden.py의 ENV_KEYS만 고친다.
ENV_KEYS = golden.ENV_KEYS


def _read(path):
    with open(path) as f:
        return f.read()


def build(raw_dir, ns):
    """(topics, qos_by_topic, env, skipped)를 만든다."""
    topics = golden.normalize_topic_list(_read(os.path.join(raw_dir, "topic_list.txt")), ns)
    qos, skipped = {}, []
    info_root = os.path.join(raw_dir, "topic_info")
    for root, _, files in os.walk(info_root):
        for name in sorted(files):
            if not name.endswith(".txt"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, info_root)[:-4].replace(os.sep, "/")
            try:
                qos[rel] = golden.normalize_qos(_read(full))
            except ValueError:
                skipped.append(rel)
    env_all = golden._read_kv(os.path.join(raw_dir, "env_raw.txt"))
    missing = [k for k in ENV_KEYS if k not in env_all]
    if missing:
        raise SystemExit("env_raw.txt에 키 없음: %s" % ",".join(missing))
    env = {k: env_all[k] for k in ENV_KEYS}
    return topics, qos, env, sorted(skipped)


def _tree(d):
    out = {}
    for root, _, files in os.walk(d):
        for name in files:
            full = os.path.join(root, name)
            out[os.path.relpath(full, d).replace(os.sep, "/")] = _read(full).splitlines(True)
    return out


def diff_dirs(old, new):
    """두 골든 디렉터리의 unified diff 줄 목록. 같으면 빈 목록."""
    a, b = _tree(old), _tree(new)
    lines = []
    for k in sorted(set(a) | set(b)):
        lines += difflib.unified_diff(a.get(k, []), b.get(k, []),
                                      "golden/" + k, "new/" + k)
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(prog="tests.support.normalize")
    p.add_argument("--raw", required=True, help="capture.sh의 OUT_DIR")
    p.add_argument("--ns", default="", help="네임스페이스(예: px4_1)")
    p.add_argument("--out", help="골든 디렉터리. 생략하면 versions.env의 PX4_TAG로 계산")
    p.add_argument("--versions-env", default=None, help="기본 <repo>/docker/versions.env")
    p.add_argument("--update", action="store_true", help="기존 골든을 덮어쓴다")
    p.add_argument("--check", action="store_true", help="쓰지 않고 기존 골든과 diff만 본다")
    args = p.parse_args(argv)

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = args.out or golden.golden_dir(
        repo, args.versions_env or os.path.join(repo, "docker", "versions.env"))
    topics, qos, env, skipped = build(args.raw, args.ns)
    if skipped:
        print("발행자 없음, QoS 건너뜀: %s" % " ".join(skipped), file=sys.stderr)

    if args.check:
        if not os.path.isdir(out):
            print("골든 디렉터리 없음: %s" % out, file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            new = os.path.join(tmp, "g")
            golden.write_golden(new, topics, qos, env)
            diff = diff_dirs(out, new)
        sys.stdout.writelines(diff)
        return 1 if diff else 0

    if os.path.exists(out):
        if not args.update:
            print("골든이 이미 있다: %s (갱신하려면 --update)" % out, file=sys.stderr)
            return 1
        shutil.rmtree(out)
    golden.write_golden(out, topics, qos, env)
    print("골든 작성: %s (토픽 %d, qos %d)" % (out, len(topics), len(qos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
