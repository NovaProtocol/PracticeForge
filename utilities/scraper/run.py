#!/usr/bin/env python3
"""Entry point for the SolveSpace problem scraper.

Runs on your personal PC with a real Edge browser window.
If Cloudflare shows a captcha, just solve it in the browser —
the scraper waits and continues automatically.

Usage:
  pip install selenium webdriver-manager requests beautifulsoup4 openai
  export ZEN_API_KEY=sk-...
  export SOLVESPACE_API=http://debian.local:7031
  cd Projects/SolveSpace
  python3 utilities/scraper/run.py
"""

import sys
from pathlib import Path

# Add the project root to sys.path so absolute imports work
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from utilities.scraper.scraper import CodeforcesScraper


def main():
    scraper = CodeforcesScraper()
    scraper.run()


if __name__ == "__main__":
    main()
