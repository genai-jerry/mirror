"""The suite must run on the Python the service ships on.

Design decision D2 chose Python 3.12 and `backend/Dockerfile` runs
`python:3.12-slim`. `backend/.python-version` pins the same minor version for
every local and factory run. This test is the tripwire: without it, a runner
that happens to offer a newer interpreter silently tests a version production
never runs, which is exactly what review round 1 caught.

Changing the version the product ships on means changing the design, the
Dockerfile, `.python-version`, the repo profile and this test together.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXPECTED = (3, 12)

PIN_FILE = Path(__file__).resolve().parent.parent / ".python-version"


def test_the_suite_runs_on_the_designed_python() -> None:
    assert sys.version_info[:2] == EXPECTED, (
        f"the design ships Python {EXPECTED[0]}.{EXPECTED[1]}, "
        f"but this suite is running on {sys.version.split()[0]}"
    )


def test_the_pin_file_agrees_with_this_test() -> None:
    pinned = PIN_FILE.read_text(encoding="utf-8").strip()

    assert pinned == f"{EXPECTED[0]}.{EXPECTED[1]}"
