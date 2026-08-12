#!/usr/bin/env python3
"""STAGE 2 — Download images referenced in scraped HTML files.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/images_download.py

Reads:  utilities/scraper/html/<contest_id>-<index>.html
Saves:  static/images/<filename>  (named by the image URL's basename)

Skips images already on disk. Does not touch the HTML files.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared._bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

import time

import requests
from bs4 import BeautifulSoup

from utilities.scraper.config import SCRAPE_DELAY, BASE
from utilities.scraper import log

HTML_DIR = BASE / "html"
IMG_DIR = BASE / "images"


def extract_image_urls(html: str) -> set:
    """Return set of espresso.codeforces.com image URLs in the HTML."""
    urls = set()
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "espresso.codeforces.com" in src:
            urls.add(src)
    return urls


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    if not HTML_DIR.exists():
        log.error(f"HTML dir not found: {HTML_DIR}")
        return

    files = sorted(HTML_DIR.glob("*.html"))
    log.info(f"Scanning {len(files)} HTML files")

    seen = set()
    to_download = set()
    for f in files:
        try:
            urls = extract_image_urls(f.read_text())
        except Exception as e:
            log.warn(f"parse error {f.name}: {e}")
            continue
        for u in urls:
            if u not in seen:
                seen.add(u)
                to_download.add(u)

    log.info(f"Found {len(to_download)} unique images, checking disk...")

    ok = 0
    skipped = 0
    failed = 0
    for url in sorted(to_download):
        name = url.rsplit("/", 1)[-1].split("?")[0]
        if not name:
            failed += 1
            continue
        out_path = IMG_DIR / name
        if out_path.exists():
            skipped += 1
            continue
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                out_path.write_bytes(r.content)
                ok += 1
                log.info(f"downloaded: {name} ({len(r.content)} bytes)")
            else:
                failed += 1
                log.warn(f"HTTP {r.status_code}: {url}")
        except Exception as e:
            failed += 1
            log.warn(f"download error: {e} — {url}")
        time.sleep(0.2)

    log.info(f"Done. {ok} downloaded, {skipped} already on disk, {failed} failed.")


if __name__ == "__main__":
    main()
