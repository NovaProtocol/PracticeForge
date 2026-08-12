#!/usr/bin/env python3
"""STAGE 1 — Scrape Codeforces problem pages and save problem-statement HTML.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/scrape.py

Saves:  utilities/scraper/html/<contest_id>-<index>.html
        Inner HTML of div.problem-statement, image src URLs left as-is.

Then run:
  python3 utilities/scraper/images_download.py   (stage 2)
  python3 utilities/scraper/images_upload.py     (stage 3)
  python3 utilities/scraper/ai_process.py        (AI enrichment)

Cloudflare captcha: solve it in the browser window — the script waits.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

import json
import time

import requests
from bs4 import BeautifulSoup

from utilities.scraper.config import CF_API, SCRAPE_DELAY, BASE, LIMIT, TEST_TARGET
from utilities.scraper.browser import Browser
from utilities.scraper import log

HTML_DIR = BASE / "html"


def fetch_problems():
    log.info("Fetching problem list from Codeforces API")
    try:
        r = requests.get(CF_API, headers={"Accept-Language": "en"}, timeout=30)
        data = r.json()
        if data["status"] != "OK":
            log.error(f"API error: {data.get('comment', 'unknown')}")
            return []
        problems = data["result"]["problems"]
        problems.sort(key=lambda p: (p["contestId"], p["index"]))
        return problems
    except Exception as e:
        log.error(f"API request failed: {e}")
        return []


def main():
    problems = fetch_problems()
    if not problems:
        return

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    to_process = problems
    if TEST_TARGET:
        parts = TEST_TARGET.split("/")
        if len(parts) == 2:
            to_process = [p for p in problems if str(p["contestId"]) == parts[0] and p["index"] == parts[1]]
            log.info(f"TEST_TARGET set — only scraping {TEST_TARGET}")
        else:
            log.error(f"Invalid TEST_TARGET: {TEST_TARGET}")
    if LIMIT:
        to_process = to_process[:LIMIT]
    total = len(to_process)
    log.info(f"Processing {total} problems")

    browser = Browser()
    ok = 0
    try:
        for i, cf_data in enumerate(to_process):
            cid = cf_data["contestId"]
            idx = cf_data["index"]
            pid_str = f"{cid}/{idx}"
            name = cf_data.get("name", "")
            log.info(f"[{i+1}/{total}] {pid_str} — {name}")

            out_file = HTML_DIR / f"{cid}-{idx}.html"

            if out_file.exists():
                log.info(f"{pid_str} already scraped, skipping")
                continue

            try:
                html = browser.scrape_problem_page(cid, idx)
            except Exception as e:
                import traceback
                log.error(f"{pid_str} browser crashed: {e}")
                log.error(traceback.format_exc())
                try:
                    browser.close()
                except Exception:
                    pass
                browser = Browser()
                html = None

            if not html:
                log.warn(f"{pid_str} no content, skipping")
                continue

            soup = BeautifulSoup(html, "html.parser")
            problem_div = soup.select_one("div.problemindexholder") or soup.select_one("div.problem-statement")
            if problem_div:
                saved_html = str(problem_div)
                out_file.write_text(saved_html)
                log.info(f"{pid_str} saved — problem statement, {len(saved_html)} chars")
            else:
                log.warn(f"{pid_str} problem-statement div not found — skipped")

            ok += 1
            time.sleep(SCRAPE_DELAY)

    except Exception as e:
        import traceback
        log.error(f"FATAL: {e}")
        log.error(traceback.format_exc())
    finally:
        browser.close()

    log.info(f"Done. {ok} scraped this run.")


if __name__ == "__main__":
    main()
