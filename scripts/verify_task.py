#!/usr/bin/env python
"""Verify a solution to one of the assessment tasks in ``tasks/``.

    python scripts/verify_task.py LL-101            # full verification
    python scripts/verify_task.py LL-101 --quick    # acceptance tests only
    python scripts/verify_task.py --list
    python scripts/verify_task.py --update-manifest # maintainers only

Checks, in order:

1. integrity  - the task's acceptance tests and fixtures are unmodified
                (SHA-256 against tasks/manifest.json);
2. acceptance - every test in tasks/<task>/tests passes;
3. regression - the main suite (tests/) passes;
4. lint       - flake8, black --check and isort --check-only are clean;
5. review     - lists changes to existing tests since the assessment base
                (informational: some tasks legitimately update tests, a
                reviewer must check that none were weakened).

Exit status is 0 only if checks 1-4 pass.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "tasks")
MANIFEST = os.path.join(TASKS_DIR, "manifest.json")
BASE_TAG = "assessment-base"
LINT_PATHS = ["ledgerline", "tests", "migrations", "scripts", "conftest.py", "wsgi.py"]


def task_dirs():
    return sorted(
        path
        for path in glob.glob(os.path.join(TASKS_DIR, "LL-*"))
        if os.path.isfile(os.path.join(path, "TASK.md"))
    )


def find_task(task_id):
    for path in task_dirs():
        if os.path.basename(path).split("-")[:2] == task_id.upper().split("-")[:2]:
            return path
    raise SystemExit("Unknown task %r. Use --list to see the available tasks." % task_id)


def protected_files(task_dir):
    files = []
    for sub in ("tests", "fixtures"):
        for path in sorted(glob.glob(os.path.join(task_dir, sub, "**", "*"), recursive=True)):
            if os.path.isfile(path) and "__pycache__" not in path:
                files.append(os.path.relpath(path, ROOT).replace(os.sep, "/"))
    return files


def sha256(path):
    with open(os.path.join(ROOT, path), "rb") as handle:
        # Normalize line endings so that checkouts with autocrlf verify too.
        return hashlib.sha256(handle.read().replace(b"\r\n", b"\n")).hexdigest()


def update_manifest():
    manifest = {}
    for task_dir in task_dirs():
        for path in protected_files(task_dir):
            manifest[path] = sha256(path)
    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("wrote %d entries to %s" % (len(manifest), os.path.relpath(MANIFEST, ROOT)))


def check_integrity(task_dir):
    with io.open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    prefix = os.path.relpath(task_dir, ROOT).replace(os.sep, "/") + "/"
    expected = {path: digest for path, digest in manifest.items() if path.startswith(prefix)}
    problems = []
    for path, digest in sorted(expected.items()):
        if not os.path.exists(os.path.join(ROOT, path)):
            problems.append("missing:  %s" % path)
        elif sha256(path) != digest:
            problems.append("modified: %s" % path)
    for path in protected_files(task_dir):
        if path not in expected:
            problems.append("added:    %s" % path)
    return problems


def run_pytest(target):
    """Run pytest on ``target``; return (ok, summary dict, output tail)."""
    handle, report = tempfile.mkstemp(suffix=".xml")
    os.close(handle)
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                target,
                "-q",
                "-p",
                "no:cacheprovider",
                "--junitxml",
                report,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        if os.path.getsize(report):
            suite = ElementTree.parse(report).getroot()
            if suite.tag == "testsuites":
                suite = suite[0]
            for key in summary:
                summary[key] = int(suite.get(key, 0))
        ok = process.returncode == 0 and summary["tests"] > 0
        return ok, summary, process.stdout.strip().splitlines()[-25:]
    finally:
        os.remove(report)


def run_lint():
    commands = [
        [sys.executable, "-m", "flake8"] + LINT_PATHS,
        [sys.executable, "-m", "black", "--check", "-q"] + LINT_PATHS,
        [sys.executable, "-m", "isort", "--check-only", "-q"] + LINT_PATHS,
    ]
    failures = []
    for command in commands:
        process = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if process.returncode != 0:
            failures.append("%s\n%s" % (" ".join(command[2:4]), process.stdout.strip()))
    return failures


def changed_tests():
    process = subprocess.run(
        ["git", "diff", "--name-status", BASE_TAG, "--", "tests"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if process.returncode != 0:
        return None
    return [line for line in process.stdout.splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("task", nargs="?", help="task id, e.g. LL-101")
    parser.add_argument("--list", action="store_true", help="list the tasks")
    parser.add_argument("--quick", action="store_true", help="acceptance tests only")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    parser.add_argument("--update-manifest", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.update_manifest:
        update_manifest()
        return 0
    if args.list or not args.task:
        for path in task_dirs():
            with io.open(os.path.join(path, "TASK.md"), encoding="utf-8") as handle:
                title = handle.readline().lstrip("# ").strip()
            print("%-42s %s" % (os.path.basename(path), title))
        return 0

    task_dir = find_task(args.task)
    report = {"task": os.path.basename(task_dir), "checks": {}}

    problems = check_integrity(task_dir)
    report["checks"]["integrity"] = {"ok": not problems, "problems": problems}

    ok, summary, tail = run_pytest(os.path.relpath(os.path.join(task_dir, "tests"), ROOT))
    report["checks"]["acceptance"] = dict(summary, ok=ok, output=tail if not ok else [])

    if not args.quick:
        ok, summary, tail = run_pytest("tests")
        report["checks"]["regression"] = dict(summary, ok=ok, output=tail if not ok else [])
        failures = run_lint()
        report["checks"]["lint"] = {"ok": not failures, "problems": failures}
        report["review"] = {"changed_tests": changed_tests()}

    passed = all(check["ok"] for check in report["checks"].values())
    report["passed"] = passed

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n%s" % report["task"])
        for name, check in report["checks"].items():
            detail = ""
            if "tests" in check:
                detail = "%(tests)d tests, %(failures)d failures, %(errors)d errors" % check
            print("  %-11s %s  %s" % (name, "PASS" if check["ok"] else "FAIL", detail))
            for line in check.get("problems", []) + check.get("output", []):
                print("      " + line)
        review = report.get("review", {}).get("changed_tests")
        if review is None and not args.quick:
            print("  review      tag '%s' not found; cannot list changed tests" % BASE_TAG)
        elif review:
            print(
                "  review      existing tests changed since %s (check none were weakened):"
                % BASE_TAG
            )
            for line in review:
                print("      " + line)
        print("\nRESULT: %s" % ("PASSED" if passed else "FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
