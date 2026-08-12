"""Put the project root on sys.path so scripts can import shared/utilities.

Note: script-mode Python only puts the script's own directory on sys.path, so
entrypoint scripts that live deeper in the tree still need a tiny
`sys.path.insert(0, ...)` before this module can be imported.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_project_root_on_path() -> Path:
    """Insert the project root into sys.path (idempotent) and return it."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return PROJECT_ROOT
