#!/usr/bin/env python
"""Check that Ledgerline stays within its 2020 toolchain.

    python scripts/check_2020_compat.py          # offline checks
    python scripts/check_2020_compat.py --pypi   # also verify PyPI release dates

Offline checks:

* every requirement is pinned with ``==``;
* ``setup.py`` limits Python to 3.8;
* Docker images and CI containers use the pinned 2020 images, and
  docker-compose.yml only uses features of the 2020 docker-compose releases;
* GitHub Actions use ``@v2`` (or older) releases;
* every Python file parses with the Python 3.8 grammar and does not use
  standard-library APIs introduced after Python 3.8 (or third-party APIs
  introduced after the pinned versions).

``--pypi`` downloads the release metadata of every pinned package and fails
if a file was first published after 2020-12-31 (see ``PYPI_EXCEPTIONS``).
Only the standard library is used, so the check runs before installation.
"""
import argparse
import ast
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUTOFF = "2020-12-31"
REQUIREMENTS = ("requirements.txt", "requirements-dev.txt")

# Container images and their upstream release dates.
IMAGES = {
    "python:3.8.6-slim-buster": "2020-09-24",
    "postgres:12.4": "2020-08-13",
    "redis:6.0.9": "2020-10-27",
}

# Releases whose files were re-uploaded to PyPI after the release date, so the
# upload timestamp is not the release date.
PYPI_EXCEPTIONS = {
    # The files were re-uploaded after the release; 1.4.0 was released in
    # April 2020. Windows-only dependency of pytest.
    ("atomicwrites", "1.4.0"): "re-uploaded after release, released 2020-04",
}

# Calls/imports that do not exist in Python 3.8 or in the pinned libraries.
FORBIDDEN_PATTERNS = {
    r"\.removeprefix\(": "str.removeprefix (Python 3.9)",
    r"\.removesuffix\(": "str.removesuffix (Python 3.9)",
    r"\bimport zoneinfo\b|\bfrom zoneinfo\b": "zoneinfo (Python 3.9)",
    r"\bfunctools\.cache\b|\bfrom functools import cache\b": "functools.cache (Python 3.9)",
    r"\bimport graphlib\b": "graphlib (Python 3.9)",
    r"\bfrom typing import [^\n]*\b(Annotated|ParamSpec|TypeAlias)\b": "typing addition (3.9+)",
    r"@\w+\.(get|post|put|patch|delete)\(": "Flask 2.0 route shortcuts",
    r"\bsqlalchemy\.future\b|\bfuture=True\b": "SQLAlchemy 1.4/2.0 API",
    r"\bmapped_column\(|\bMapped\[": "SQLAlchemy 2.0 typed mappings",
    r"\bload_default=|\bdump_default=": "marshmallow 3.13+ field arguments",
}
SOURCE_DIRS = ("ledgerline", "migrations", "tests", "tasks", "scripts")
SKIP_PATTERN_CHECK = {
    os.path.join("scripts", "check_2020_compat.py"),
    os.path.join("tests", "unit", "test_toolchain.py"),  # contains forbidden samples
}


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def pinned_requirements():
    """Yield ``(name, version, file, line)`` for every requirement line."""
    for filename in REQUIREMENTS:
        for line in read(filename).splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-r"):
                continue
            match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
            yield (match.group(1).lower(), match.group(2)) if match else (
                None,
                None,
            ), filename, line


def check_pins(errors):
    for (name, _), filename, line in pinned_requirements():
        if name is None:
            errors.append("%s: requirement is not pinned with '==': %s" % (filename, line))


def check_python_version(errors):
    if 'python_requires=">=3.8,<3.9"' not in read("setup.py"):
        errors.append("setup.py: python_requires must be '>=3.8,<3.9'")


def check_images(errors):
    compose = read("docker-compose.yml")
    sources = {
        "Dockerfile": re.findall(r"^FROM\s+(\S+)", read("Dockerfile"), re.M),
        "docker-compose.yml": re.findall(r"image:\s*(\S+)", compose),
    }
    if re.search(r"^\s+profiles:", compose, re.M):
        errors.append(
            "docker-compose.yml: service profiles are not supported by docker-compose 1.27"
        )
    for workflow in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
        name = os.path.relpath(workflow, ROOT)
        text = read(name)
        sources[name] = re.findall(r"(?:container|image):\s*(\S+:\S+)", text)
        for action, version in re.findall(r"uses:\s*([\w\-/]+)@v(\d+)", text):
            if int(version) > 2:
                errors.append(
                    "%s: %s@v%s is newer than the 2020 releases" % (name, action, version)
                )
    for source, images in sources.items():
        for image in images:
            if image not in IMAGES:
                errors.append("%s: image %s is not one of the pinned 2020 images" % (source, image))


def python_files():
    for directory in SOURCE_DIRS:
        for path in glob.glob(os.path.join(ROOT, directory, "**", "*.py"), recursive=True):
            yield os.path.relpath(path, ROOT)
    for path in glob.glob(os.path.join(ROOT, "*.py")):
        yield os.path.relpath(path, ROOT)


def check_sources(errors):
    count = 0
    for path in python_files():
        source = read(path)
        count += 1
        try:
            ast.parse(source, filename=path, feature_version=(3, 8))
        except SyntaxError as exc:
            errors.append("%s:%s: not valid Python 3.8 syntax (%s)" % (path, exc.lineno, exc.msg))
        if path in SKIP_PATTERN_CHECK:
            continue
        for pattern, feature in FORBIDDEN_PATTERNS.items():
            for match in re.finditer(pattern, source):
                line = source.count("\n", 0, match.start()) + 1
                errors.append("%s:%d: uses %s" % (path, line, feature))
    return count


def first_upload(name, version):
    url = "https://pypi.org/pypi/%s/%s/json" % (name, version)
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    uploads = sorted(item["upload_time_iso_8601"][:10] for item in data["urls"])
    return uploads[0] if uploads else None


def check_pypi(errors, report):
    for (name, version), filename, _ in pinned_requirements():
        if name is None:
            continue
        uploaded = first_upload(name, version)
        note = PYPI_EXCEPTIONS.get((name, version))
        report.append((name, version, uploaded, note or ""))
        if uploaded is None:
            errors.append("%s %s: no files on PyPI" % (name, version))
        elif uploaded > CUTOFF and not note:
            errors.append(
                "%s %s (%s): published %s, after %s" % (name, version, filename, uploaded, CUTOFF)
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the 2020 toolchain constraints.")
    parser.add_argument("--pypi", action="store_true", help="verify PyPI release dates (network)")
    args = parser.parse_args(argv)

    errors = []
    check_pins(errors)
    check_python_version(errors)
    check_images(errors)
    files = check_sources(errors)
    report = []
    if args.pypi:
        check_pypi(errors, report)
        for name, version, uploaded, note in report:
            print("  %-20s %-12s %s  %s" % (name, version, uploaded, note))

    print("checked %d Python files, %d requirement files" % (files, len(REQUIREMENTS)))
    for error in errors:
        print("ERROR " + error)
    print("2020 compatibility: %s" % ("FAILED" if errors else "OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
