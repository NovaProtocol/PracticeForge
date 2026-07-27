import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import BASE
from . import log

TRACKER_PATH = BASE / "token_usage.json"
WINDOW_SECONDS = 5 * 3600  # 5 hours
TOKEN_LIMIT = 1_000_000


def _load() -> dict:
    """Read token usage from disk, or return defaults."""
    if TRACKER_PATH.exists():
        try:
            return json.loads(TRACKER_PATH.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    return {"window_start": 0, "tokens_used": 0}


def _save(state: dict):
    TRACKER_PATH.write_text(json.dumps(state, indent=2) + "\n")


def check_and_track(tokens: int):
    """Check if under limit, record usage. Returns True if allowed. Exits if over limit."""
    state = _load()
    now = time.time()
    elapsed = now - state["window_start"]

    if elapsed > WINDOW_SECONDS:
        log.info(f"Token window reset ({elapsed:.0f}s elapsed)")
        state["window_start"] = now
        state["tokens_used"] = 0

    projected = state["tokens_used"] + tokens
    if projected > TOKEN_LIMIT:
        remaining = TOKEN_LIMIT - state["tokens_used"]
        reset_at = datetime.fromtimestamp(state["window_start"] + WINDOW_SECONDS, tz=timezone.utc)
        log.error(f"Token limit reached ({state['tokens_used']}/{TOKEN_LIMIT})")
        log.error(f"Window resets at {reset_at.isoformat()}")
        raise SystemExit(0)
