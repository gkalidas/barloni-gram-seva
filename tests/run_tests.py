#!/usr/bin/env python3
"""Run the whole automated regression suite in one command.

    python tests/run_tests.py

Each suite runs in its own subprocess so it gets a fresh, isolated scratch
database (the app reads its config once at import time, so they must not share
a process). Exits non-zero if any suite fails.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SUITES = ["security_checks.py", "functional_checks.py", "api_e2e_checks.py"]


def main() -> int:
    failures = 0
    for suite in SUITES:
        print(f"\n{'#' * 60}\n# Running {suite}\n{'#' * 60}")
        result = subprocess.run([sys.executable, str(HERE / suite)], cwd=str(ROOT))
        if result.returncode != 0:
            failures += 1
    print(f"\n{'=' * 60}")
    if failures:
        print(f"OVERALL: {failures} suite(s) FAILED")
    else:
        print("OVERALL: all suites passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
