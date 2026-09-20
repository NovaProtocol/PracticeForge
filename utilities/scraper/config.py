import os
from pathlib import Path

# Paths (relative to this file)
BASE = Path(__file__).resolve().parent
BROWSER_DATA_DIR = BASE / "browser_profile"

# API: tunnel only; the app is not reachable on the LAN.
API_BASE = "https://solver.projectnova.download"

# Access code for the GateKeeper forward-auth gate (magic-link handshake).
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")

CF_API = "https://codeforces.com/api/problemset.problems"

# AI
# The endpoint, model and key are configuration, not code: the enrichment step
# is skipped whenever any of the three is blank, so a checkout with no LLM
# configured still scrapes and still leaves problems in a valid state.
LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_URL = os.environ.get("LLM_BASE_URL", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# Timing
SCRAPE_DELAY = 1  # seconds between scraping problems
AI_DELAY = 1  # seconds between AI calls
CF_POLL = 3  # seconds between checks for Cloudflare captcha

# Limit: set to int to process that many per run. 0/None = process all pending.
# Order: oldest problems first (1/A, 1/B, ...).
LIMIT = 0

# Test target: set to e.g. "3/A" to only process that one problem.
# ""/None = process normally (respecting LIMIT).
TEST_TARGET = ""

# AI
RETRY_LIMIT = 5  # max retries for solution/generator validation
