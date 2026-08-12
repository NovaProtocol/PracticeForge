"""Shared test setup: put the paths modules import from on sys.path.

- repo root, for absolute imports like ``from shared.db import ...``
- shared/, for imports like the executor's ``from wrapper import ...``
- solver_private/, whose blueprints import as ``from apps.problems.routes ...``
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for path in (ROOT, ROOT / "shared", ROOT / "solver_private"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
