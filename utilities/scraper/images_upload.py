#!/usr/bin/env python3
"""STAGE 3 — Upload downloaded images to the server via the images API.

Usage:  cd Projects/SolveSpace && python3 utilities/scraper/images_upload.py

Reads:  static/images/<filename>
Uploads: POST /api/images {filename, data(base64), content_type} to API_BASE

Skips images already on the server (checks /api/images/exists/<filename>).
"""

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared._bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

import time

from utilities.scraper import log
from utilities.scraper.api import get_session
from utilities.scraper.config import API_BASE, BASE

IMG_DIR = BASE / "images"
RETRIES = 3
BACKOFF = 2

_API_TOKEN = os.environ.get("API_TOKEN", "")


def _headers():
    return {"X-API-Token": _API_TOKEN} if _API_TOKEN else {}


CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "image/png")


def _exists_on_server(filename: str) -> bool:
    try:
        r = get_session().get(f"{API_BASE}/api/images/exists/{filename}", timeout=10)
        return r.status_code == 200 and r.json().get("exists", False)
    except Exception as e:
        log.warn(f"exists check failed for {filename}: {e}")
        return False


def _upload(filename: str, data_b64: str, content_type: str) -> bool:
    for attempt in range(RETRIES):
        try:
            r = get_session().post(
                f"{API_BASE}/api/images",
                json={"filename": filename, "data": data_b64, "content_type": content_type},
                headers=_headers(),
                timeout=60,
            )
            if r.status_code == 200:
                return True
            log.warn(f"upload {filename} HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warn(f"upload {filename} error: {e}")
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF * (attempt + 1))
    return False


def main():
    if not IMG_DIR.exists():
        log.error(f"Image dir not found: {IMG_DIR}")
        return

    files = sorted(IMG_DIR.glob("*"))
    log.info(f"Found {len(files)} images to check/upload")

    ok = 0
    skipped = 0
    failed = 0
    for path in files:
        filename = path.name
        if _exists_on_server(filename):
            skipped += 1
            continue
        data_b64 = base64.b64encode(path.read_bytes()).decode()
        content_type = _content_type(path)
        if _upload(filename, data_b64, content_type):
            ok += 1
            log.info(f"uploaded: {filename} ({content_type})")
        else:
            failed += 1
            log.warn(f"FAILED: {filename}")
        time.sleep(0.2)

    log.info(f"Done. {ok} uploaded, {skipped} already on server, {failed} failed.")


if __name__ == "__main__":
    main()
