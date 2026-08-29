"""Pytest bootstrap for the rag package.

``rag/pyproject.toml`` sets ``testpaths = ["eval"]``. Tests here need two
import roots:

* ``rag.*`` — the installed package (editable via ``uv sync``).
* ``prose_preprocessing_util`` — a build-only helper that lives next to the
  adapter scripts in ``rag/build/`` and is **not** part of the wheel, so we
  put ``rag/build`` on ``sys.path`` the same way the process scripts do.
"""

from __future__ import annotations

import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))
