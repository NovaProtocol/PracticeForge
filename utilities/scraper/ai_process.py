#!/usr/bin/env python3
"""Read scraped HTML from disk, enrich with AI, upload to server.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/ai_process.py

Reads:  utilities/scraper/html/<contest_id>-<index>.html
Writes: utilities/scraper/fail.json (on failures)

Does NOT use a browser — run this unattended after scrape.py finishes.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

import json
import time

from utilities.scraper.config import AI_DELAY, LIMIT, API_BASE, BASE, TEST_TARGET
from utilities.scraper.ai import AIEnricher
from utilities.scraper.extract import extract_text
from utilities.scraper.uploader import Uploader
from utilities.scraper import log

HTML_DIR = BASE / "html"
FAIL_PATH = BASE / "fail.json"
FAILED_IDS_CACHE = None


def _load_failed_ids():
    global FAILED_IDS_CACHE
    if FAILED_IDS_CACHE is not None:
        return FAILED_IDS_CACHE
    FAILED_IDS_CACHE = set()
    if FAIL_PATH.exists():
        try:
            for entry in json.loads(FAIL_PATH.read_text()):
                FAILED_IDS_CACHE.add(entry.get("id"))
        except (json.JSONDecodeError, Exception):
            pass
    return FAILED_IDS_CACHE


def _record_failure(problem_id: str, problem_name: str, reason: str):
    failures = []
    if FAIL_PATH.exists():
        try:
            failures = json.loads(FAIL_PATH.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    failures.append({"id": problem_id, "name": problem_name, "reason": reason, "ts": time.time()})
    FAIL_PATH.write_text(json.dumps(failures, indent=2))
    global FAILED_IDS_CACHE
    FAILED_IDS_CACHE = None


def _collect_html_files():
    files = []
    if not HTML_DIR.exists():
        return files
    for html_file in sorted(HTML_DIR.glob("*.html")):
        stem = html_file.stem
        parts = stem.split("-", 1)
        if len(parts) == 2 and parts[0].isdigit():
            files.append((int(parts[0]), parts[1], html_file))
    return files


def main():
    log.info(f"Server: {API_BASE}")

    uploader = Uploader()
    ai = AIEnricher()
    failed_ids = _load_failed_ids()

    all_files = _collect_html_files()
    if TEST_TARGET:
        parts = TEST_TARGET.split("/")
        if len(parts) == 2:
            target_file = HTML_DIR / f"{parts[0]}-{parts[1]}.html"
            all_files = [f for f in all_files if f[2] == target_file]
        else:
            log.error(f"Invalid TEST_TARGET: {TEST_TARGET}")
    to_process = all_files[:LIMIT] if LIMIT else all_files
    total = len(to_process)
    log.info(f"Found {total} HTML files to process")

    ok = 0
    for i, (cid_str, idx, html_file) in enumerate(to_process):
        cid = int(cid_str)
        pid_str = f"{cid}/{idx}"
        log.info(f"[{i+1}/{total}] {pid_str} — {html_file}")

        if uploader.exists_on_server(cid, idx):
            continue

        if pid_str in failed_ids:
            log.info(f"{pid_str} previously failed, skipping")
            continue

        html = html_file.read_text()
        clean = extract_text(html)

        ai_data = ai.enrich(clean)
        if not ai_data:
            msg = ai.last_error or "AI enrichment failed (unknown)"
            log.warn(f"{pid_str} {msg}")
            _record_failure(pid_str, "", msg)
            continue

        # Try to get the problem title from CF API — fallback
        name = ai_data.get("title", "")
        payload = uploader.build_payload({"contestId": cid, "index": idx, "name": name, "tags": [], "rating": None}, ai_data)

        pid = uploader.upload(payload)
        if pid:
            ok += 1
            if not uploader.verify_upload(payload):
                msg = "Upload verification failed — server data mismatch"
                log.warn(f"{pid_str} {msg}")
                _record_failure(pid_str, name, msg)
        else:
            msg = "Upload to server failed"
            log.warn(f"{pid_str} {msg}")
            _record_failure(pid_str, name, msg)

        time.sleep(AI_DELAY)

    log.info(f"Done. {ok} uploaded this run.")


if __name__ == "__main__":
    main()
