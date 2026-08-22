#!/usr/bin/env python3
"""Read scraped HTML from disk, enrich with AI, upload to server.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/ai_process.py

Reads:  utilities/scraper/html/<contest_id>-<index>.html
Writes: utilities/scraper/fail.json (on failures)

Does NOT use a browser — run this unattended after scrape.py finishes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared._bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

import contextlib
import json
import time

import requests

from utilities.scraper import log
from utilities.scraper.ai import AIEnricher
from utilities.scraper.config import AI_DELAY, API_BASE, BASE, CF_API, LIMIT, TEST_TARGET
from utilities.scraper.extract import extract_text
from utilities.scraper.uploader import Uploader

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
        except json.JSONDecodeError, Exception:
            pass
    return FAILED_IDS_CACHE


def _record_failure(problem_id: str, problem_name: str, reason: str):
    failures = []
    if FAIL_PATH.exists():
        with contextlib.suppress(json.JSONDecodeError, Exception):
            failures = json.loads(FAIL_PATH.read_text())
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


def _fetch_cf_metadata():
    """Fetch problem metadata (tags, rating, name) from Codeforces API.
    Returns dict keyed by 'contestId/index'."""
    log.info("Fetching problem metadata from Codeforces API")
    try:
        r = requests.get(CF_API, headers={"Accept-Language": "en"}, timeout=30)
        data = r.json()
        if data["status"] != "OK":
            log.error(f"CF API error: {data.get('comment', 'unknown')}")
            return {}
        meta = {}
        for p in data["result"]["problems"]:
            key = f"{p['contestId']}/{p['index']}"
            meta[key] = {
                "contestId": p["contestId"],
                "index": p["index"],
                "name": p.get("name", ""),
                "tags": p.get("tags", []),
                "rating": p.get("rating"),
            }
        log.info(f"Loaded metadata for {len(meta)} problems")
        return meta
    except Exception as e:
        log.error(f"CF metadata fetch failed: {e}")
        return {}


def main():
    log.info(f"Server: {API_BASE}")

    uploader = Uploader()
    ai = AIEnricher()
    failed_ids = _load_failed_ids()
    cf_meta = _fetch_cf_metadata()

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
        log.info(f"[{i + 1}/{total}] {pid_str} — {html_file}")

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

        # Use CF API metadata (tags, rating, name) — fall back to AI title
        cf = cf_meta.get(pid_str, {})
        cf_data = {
            "contestId": cid,
            "index": idx,
            "name": cf.get("name") or ai_data.get("title", ""),
            "tags": cf.get("tags", []),
            "rating": cf.get("rating"),
        }
        payload = uploader.build_payload(cf_data, ai_data)

        pid = uploader.upload(payload)
        if pid:
            ok += 1
            if not uploader.verify_upload(payload):
                msg = "Upload verification failed — server data mismatch"
                log.warn(f"{pid_str} {msg}")
                _record_failure(pid_str, cf_data["name"], msg)
        else:
            msg = "Upload to server failed"
            log.warn(f"{pid_str} {msg}")
            _record_failure(pid_str, cf_data["name"], msg)

        time.sleep(AI_DELAY)

    log.info(f"Done. {ok} uploaded this run.")


if __name__ == "__main__":
    main()
