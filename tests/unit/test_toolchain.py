"""The repository must stay within its 2020 toolchain (see docs/2020-compatibility.md)."""
import importlib.util
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_checker():
    path = os.path.join(ROOT, "scripts", "check_2020_compat.py")
    spec = importlib.util.spec_from_file_location("check_2020_compat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def test_runs_on_python_3_8():
    assert sys.version_info[:2] == (3, 8)


def test_offline_checks_pass(capsys):
    assert checker.main([]) == 0
    assert "2020 compatibility: OK" in capsys.readouterr().out


def test_every_requirement_is_pinned():
    for (name, version), filename, line in checker.pinned_requirements():
        assert name is not None, "%s: %s" % (filename, line)


@pytest.mark.parametrize(
    "source",
    [
        "name.removeprefix('x')",
        "from zoneinfo import ZoneInfo",
        "@bp.post('/customers')\ndef f(): pass",
        "engine = create_engine(url, future=True)",
        "id: Mapped[int] = mapped_column(primary_key=True)",
    ],
)
def test_forbidden_apis_are_detected(source):
    assert any(re.search(pattern, source) for pattern in checker.FORBIDDEN_PATTERNS)


def test_pinned_images_only():
    errors = []
    checker.check_images(errors)
    assert errors == []
