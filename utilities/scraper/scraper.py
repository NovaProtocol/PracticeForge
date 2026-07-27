"""Scraper service — orchestrates the full scraping, AI enrichment, and upload flow."""

import json
import time

import requests
from bs4 import BeautifulSoup

from .config import CF_API, AI_DELAY, SCRAPE_DELAY, LIMIT, API_BASE, DB_PATH
from .db import Database
from .browser import Browser
from .ai import AIEnricher
from .uploader import Uploader
from . import log


class CodeforcesScraper:

    def __init__(self):
        self.db = Database()
        self.browser = Browser()
        self.ai = AIEnricher()
        self.uploader = Uploader()

    def run(self):
        log.info(f"Server: {API_BASE}")
        log.info(f"DB: {DB_PATH}")

        self._sync_api()

        pending = self.db.get_pending()
        to_process = pending[:LIMIT] if LIMIT else pending
        total = len(to_process)
        log.info(f"{len(pending)} pending, processing {total} this run")

        ok = 0
        try:
            for i, (cid, idx, api_json) in enumerate(to_process):
                cf_data = json.loads(api_json)
                name = cf_data.get("name", "")
                log.info(f"[{i+1}/{total}] {cid}/{idx} — {name}")

                if self.uploader.exists_on_server(cid, idx):
                    self.db.mark_uploaded(cid, idx)
                    continue

                html = self.browser.scrape_problem_page(cid, idx)
                if not html:
                    self.db.mark_failed(cid, idx, "cf-blocked")
                    continue

                clean = self._extract_text(html)
                self.db.mark(cid, idx, html=json.dumps(clean), status="scraped")
                time.sleep(SCRAPE_DELAY)

                ai_data = self.ai.enrich(clean)
                if not ai_data:
                    self.db.mark(cid, idx, status="ai-failed")
                    continue
                self.db.mark(cid, idx, ai_data=json.dumps(ai_data), status="ai-done")

                payload = self.uploader.build_payload(cf_data, ai_data)
                pid = self.uploader.upload(payload)
                if pid:
                    ok += 1
                    if self.uploader.verify_upload(payload):
                        self.db.mark_uploaded(cid, idx)
                    else:
                        log.warn(f"Upload verification failed for {cid}/{idx}, will retry next run")
                else:
                    self.db.mark(cid, idx, status="upload-failed")

                time.sleep(AI_DELAY)

        finally:
            self.browser.close()
            self.db.close()

        log.info(f"Done. {ok} uploaded this run.")

    def _sync_api(self):
        log.info("Fetching problem list from Codeforces API")
        try:
            r = requests.get(CF_API, headers={"Accept-Language": "en"}, timeout=30)
            data = r.json()
            if data["status"] != "OK":
                log.error(f"API error: {data.get('comment', 'unknown')}")
                return
            self.db.sync_api(data["result"]["problems"])
        except Exception as e:
            log.error(f"API request failed: {e}")

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select("script[type='math/tex']"):
            if el.string:
                el.replace_with(soup.new_string(f"${el.string}$"))
        for el in soup.select("script[type='math/tex; mode=display']"):
            if el.string:
                el.replace_with(soup.new_string(f"$${el.string}$$"))
        for el in soup.select(".MathJax"):
            m = el.find("script", {"type": "math/tex"})
            if m and m.string:
                el.replace_with(soup.new_string(f"${m.string}$"))
        c = soup.select_one("div.problemindexholder") or soup.select_one("div.problem-statement")
        return str(c) if c else html
