import os
import socket
from pathlib import Path

# Paths (relative to this file)
BASE = Path(__file__).resolve().parent
BROWSER_DATA_DIR = BASE / "browser_profile"

# API
# Resolve mDNS hostname once at startup (~10s), reuse in-memory
# for the whole session so requests don't pay 10s DNS each.
API_HOST = "debian.local"
API_PORT = 7031


def _resolve_api_base() -> str:
    try:
        ip = socket.gethostbyname(API_HOST)
        return f"http://{ip}:{API_PORT}"
    except OSError:
        # Fall back to hostname (slow DNS each time, but works)
        return f"http://{API_HOST}:{API_PORT}"


API_BASE = _resolve_api_base()
CF_API = "https://codeforces.com/api/problemset.problems"

# AI
AI_KEY = os.environ.get("ZEN_API_KEY", "")
AI_URL = "https://opencode.ai/zen/go/v1"
AI_MODEL = "deepseek-v4-flash"

# Timing
SCRAPE_DELAY = 1  # seconds between scraping problems
AI_DELAY = 1      # seconds between AI calls
CF_POLL = 3       # seconds between checks for Cloudflare captcha

# Limit — set to int to process that many per run. None = process all pending.
# Order: oldest problems first (1/A, 1/B, ...).
LIMIT = 5

# Test target — set to e.g. "3/A" to only process that one problem.
# None = process normally (respecting LIMIT).
TEST_TARGET = "3/A"

# AI
RETRY_LIMIT = 5  # max retries for solution/generator validation
