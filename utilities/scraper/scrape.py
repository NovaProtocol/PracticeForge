#!/usr/bin/env python3
"""Scrape Codeforces problem pages and save problem-statement HTML to disk.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/scrape.py

Saves:  utilities/scraper/html/<contest_id>-<index>.html
        Contains the inner HTML of div.problem-statement.

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

from utilities.scraper.config import CF_API, SCRAPE_DELAY, BASE
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
    to_process = problems  # scrape everything, LIMIT not applied here
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
                out_file.write_text(str(problem_div))
                log.info(f"{pid_str} saved — problem statement, {len(str(problem_div))} chars")
            else:
                out_file.write_text(html)
                log.warn(f"{pid_str} problem-statement div not found, saved full page ({len(html)} chars)")

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
