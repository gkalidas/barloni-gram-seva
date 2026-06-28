"""pytest entry point.

Each suite is a self-contained script that sets up its own isolated scratch
database before importing the app. Because the app binds its configuration at
import time, the suites must not share a Python process — so we run each in a
subprocess and assert it exits cleanly. This lets both `pytest` and
`python tests/run_tests.py` work.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _run(script: str) -> None:
    result = subprocess.run([sys.executable, str(HERE / script)], cwd=str(ROOT))
    assert result.returncode == 0, f"{script} reported failures"


def test_security_checks():
    _run("security_checks.py")


def test_functional_checks():
    _run("functional_checks.py")
