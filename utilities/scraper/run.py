#!/usr/bin/env python3
"""Entry point for the SolveSpace scraper pipeline.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/run.py <stages>

<stages> is a string of digits selecting which stages to run:
  1 = scrape.py          (scrape problem HTML, needs browser/captcha)
  2 = images_download.py (download images referenced in the HTML)
  3 = images_upload.py   (upload images to the server via API)
  4 = ai_process.py      (AI enrichment + problem upload)

Examples:
  python3 utilities/scraper/run.py 1        # scrape only
  python3 utilities/scraper/run.py 12       # scrape + download images
  python3 utilities/scraper/run.py 1234     # full pipeline
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared._bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

STAGES = {
    "1": ("utilities.scraper.scrape", "scrape.py"),
    "2": ("utilities.scraper.images_download", "images_download.py"),
    "3": ("utilities.scraper.images_upload", "images_upload.py"),
    "4": ("utilities.scraper.ai_process", "ai_process.py"),
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    stages = sys.argv[1]
    if not stages.isdigit():
        print(f"Invalid stages: {stages!r}, expected digits like 1234")
        print(__doc__)
        sys.exit(1)

    unknown = [c for c in stages if c not in STAGES]
    if unknown:
        print(f"Unknown stage(s): {unknown}, valid are 1, 2, 3, 4")
        sys.exit(1)

    for c in stages:
        module_path, script_name = STAGES[c]
        print(f"\n{'=' * 60}\nRunning stage {c} ({script_name})\n{'=' * 60}", flush=True)
        module = __import__(module_path, fromlist=["main"])
        module.main()


if __name__ == "__main__":
    main()
