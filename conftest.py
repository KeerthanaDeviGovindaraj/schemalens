"""Ensure the src-layout package is importable during tests.

The editable install adds src/ via a .pth file; this is a belt-and-suspenders
fallback so the test suite imports the in-tree package regardless of how the
environment was set up.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
