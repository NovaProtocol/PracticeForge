"""Scraper service — orchestrates the full scraping, AI enrichment, and upload flow."""

import json
import time

import requests
from bs4 import BeautifulSoup

from .config import CF_API, AI_DELAY, SCRAPE_DELAY, LIMIT, API_BASE
from .browser import Browser
from .ai import AIEnricher
from .uploader import Uploader
from . import log


class CodeforcesScraper:

    def __init__(self):
        self.browser = Browser()
        self.ai = AIEnricher()
        self.uploader = Uploader()

    def run(self):
        log.info(f"Server: {API_BASE}")

        problems = self._fetch_problems()
        if not problems:
            return

        to_process = problems[:LIMIT] if LIMIT else problems
        total = len(to_process)
        log.info(f"Processing {total} problems")

        ok = 0
        try:
            for i, cf_data in enumerate(to_process):
                cid = cf_data["contestId"]
                idx = cf_data["index"]
                name = cf_data.get("name", "")
                log.info(f"[{i+1}/{total}] {cid}/{idx} — {name}")

                if self.uploader.exists_on_server(cid, idx):
                    continue

                html = self.browser.scrape_problem_page(cid, idx)
                if not html:
                    log.warn(f"{cid}/{idx} blocked by CF, skipping")
                    continue

                clean = self._extract_text(html)
                time.sleep(SCRAPE_DELAY)

                ai_data = self.ai.enrich(clean)
                if not ai_data:
                    log.warn(f"{cid}/{idx} AI enrichment failed, skipping")
                    continue

                payload = self.uploader.build_payload(cf_data, ai_data)
                pid = self.uploader.upload(payload)
                if pid:
                    ok += 1
                    if not self.uploader.verify_upload(payload):
                        log.warn(f"Upload verification failed for {cid}/{idx}")
                else:
                    log.warn(f"{cid}/{idx} upload failed")

                time.sleep(AI_DELAY)

        finally:
            self.browser.close()

        log.info(f"Done. {ok} uploaded this run.")

    def _fetch_problems(self):
        log.info("Fetching problem list from Codeforces API")
        try:
            r = requests.get(CF_API, headers={"Accept-Language": "en"}, timeout=30)
            data = r.json()
            if data["status"] != "OK":
                log.error(f"API error: {data.get('comment', 'unknown')}")
                return None
            return data["result"]["problems"]
        except Exception as e:
            log.error(f"API request failed: {e}")
            return None

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
