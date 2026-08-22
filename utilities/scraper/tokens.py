import json
import time
from datetime import UTC, datetime

from . import log
from .config import BASE

TRACKER_PATH = BASE / "token_usage.json"
WINDOW_SECONDS = 5 * 3600
TOKEN_LIMIT = 1_000_000


def _load() -> dict:
    if TRACKER_PATH.exists():
        try:
            return json.loads(TRACKER_PATH.read_text())
        except json.JSONDecodeError, Exception:
            pass
    return {"window_start": 0, "tokens_used": 0}


def _save(state: dict):
    TRACKER_PATH.write_text(json.dumps(state, indent=2) + "\n")


def record(tokens: int):
    """Record actual tokens used after an AI call. Warns if over limit but doesn't stop."""
    state = _load()
    now = time.time()
    elapsed = now - state["window_start"]

    if elapsed > WINDOW_SECONDS:
        log.info(f"Token window reset ({elapsed:.0f}s elapsed)")
        state["window_start"] = now
        state["tokens_used"] = 0

    projected = state["tokens_used"] + tokens
    if projected > TOKEN_LIMIT:
        reset_at = datetime.fromtimestamp(state["window_start"] + WINDOW_SECONDS, tz=UTC)
        log.warn(f"Token limit exceeded ({state['tokens_used']}/{TOKEN_LIMIT}) — overage allowed")
        log.warn(f"Window resets at {reset_at.isoformat()}")

    state["tokens_used"] += tokens
    _save(state)
    log.info(f"Tokens: {state['tokens_used']}/{TOKEN_LIMIT} in current window")
