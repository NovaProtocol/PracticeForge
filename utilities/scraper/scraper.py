"""Scraper service — orchestrates the full scraping, AI enrichment, and upload flow."""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from pathlib import Path

from .config import BASE, CF_API, AI_DELAY, SCRAPE_DELAY, LIMIT, API_BASE
from .browser import Browser
from .ai import AIEnricher
from .uploader import Uploader
from . import log


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


class CodeforcesScraper:

    def __init__(self):
        self._browser = None
        self.ai = AIEnricher()
        self.uploader = Uploader()

    @property
    def browser(self):
        if self._browser is None:
            self._browser = Browser()
            self._browser.start()
        return self._browser

    def _record_failure(self, problem_id: str, problem_name: str, reason: str):
        failures = []
        if FAIL_PATH.exists():
            try:
                failures = json.loads(FAIL_PATH.read_text())
            except (json.JSONDecodeError, Exception):
                pass
        failures.append({"id": problem_id, "name": problem_name, "reason": reason, "ts": time.time()})
        FAIL_PATH.write_text(json.dumps(failures, indent=2))
        global FAILED_IDS_CACHE
        FAILED_IDS_CACHE = None  # invalidate cache

    def _ensure_browser(self):
        if self._browser is not None:
            return True
        try:
            self._browser = Browser()
            self._browser.start()
            return True
        except Exception as e:
            log.error(f"Browser startup failed: {e}")
            return False

    def run(self):
        log.info(f"Server: {API_BASE}")

        problems = self._fetch_problems()
        if not problems:
            return

        to_process = problems[:LIMIT] if LIMIT else problems
        total = len(to_process)
        log.info(f"Processing {total} problems")

        failed_ids = _load_failed_ids()
        ok = 0
        try:
            for i, cf_data in enumerate(to_process):
                cid = cf_data["contestId"]
                idx = cf_data["index"]
                pid_str = f"{cid}/{idx}"
                name = cf_data.get("name", "")
                log.info(f"[{i+1}/{total}] {pid_str} — {name}")

                if self.uploader.exists_on_server(cid, idx):
                    continue

                if pid_str in failed_ids:
                    log.info(f"{pid_str} previously failed, skipping")
                    continue

                if not self._ensure_browser():
                    self._record_failure(pid_str, name, "Browser failed to start")
                    continue

                try:
                    html = self.browser.scrape_problem_page(cid, idx)
                except Exception as e:
                    log.error(f"Browser error: {e}, reinitializing...")
                    try:
                        self._browser.close()
                    except Exception:
                        pass
                    self._browser = None
                    if not self._ensure_browser():
                        self._record_failure(pid_str, name, f"Browser error: {e}")
                        continue
                    html = self.browser.scrape_problem_page(cid, idx)
                if not html:
                    msg = "Cloudflare blocked — no page content"
                    log.warn(f"{pid_str} {msg}")
                    self._record_failure(pid_str, name, msg)
                    continue

                clean = self._extract_text(html)
                time.sleep(SCRAPE_DELAY)

                ai_data = self.ai.enrich(clean)
                if not ai_data:
                    msg = self.ai.last_error or "AI enrichment failed (unknown)"
                    log.warn(f"{pid_str} {msg}")
                    self._record_failure(pid_str, name, msg)
                    continue

                payload = self.uploader.build_payload(cf_data, ai_data)
                pid = self.uploader.upload(payload)
                if pid:
                    ok += 1
                    if not self.uploader.verify_upload(payload):
                        msg = "Upload verification failed — server data mismatch"
                        log.warn(f"{pid_str} {msg}")
                        self._record_failure(pid_str, name, msg)
                else:
                    msg = "Upload to server failed"
                    log.warn(f"{pid_str} {msg}")
                    self._record_failure(pid_str, name, msg)

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
            problems = data["result"]["problems"]
            problems.sort(key=lambda p: (p["contestId"], p["index"]))
            return problems
        except Exception as e:
            log.error(f"API request failed: {e}")
            return None

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        # Convert math script tags to LaTeX text
        for sel, fmt in [
            ("script[type='math/tex']", "$ {} $"),
            ("script[type='math/tex; mode=display']", "$$ {} $$ "),
        ]:
            for el in soup.select(sel):
                if el.string:
                    val = el.string.strip()
                    token = fmt.replace("{}", val).strip()
                    el.replace_with(soup.new_string(f" {token} "))

        # Remove MathJax visual spans (they're just rendered markup, redundant)
        for el in soup.select(".MathJax, .MathJax_Preview"):
            el.decompose()

        # Remove tex-spans: they duplicate plain text. Insert $value$ and
        # strip any whitespace-only adjacent text nodes so we don't get "n n $n$".
        for el in soup.select("span.tex-span"):
            val = el.get_text().strip()
            el.replace_with(soup.new_string(f" ${val}$ "))

        # Remove duplicate text nodes around tex-span replacements
        for el in soup.find_all(string=True):
            if el.parent and el.parent.name in ("p", "div", "span") and el.strip() == "":
                prev = el.find_previous_sibling(string=True)
                if prev and prev.strip() == el.strip() and prev.parent is el.parent:
                    pass  # keep at least one space

        c = soup.select_one("div.problemindexholder") or soup.select_one("div.problem-statement")
        if not c:
            return html

        lines = []

        def strip_sec_name(text: str, name: str) -> str:
            if text.lower().startswith(name.lower()):
                text = text[len(name):].lstrip(" .:\n")
            return text

        def get_clean(el) -> str:
            if not el:
                return ""
            # Get text with space separator, then collapse all whitespace to single spaces
            text = el.get_text(" ")
            text = re.sub(r"\s+", " ", text)
            return text.strip()

        header = c.select_one(".header")
        if header:
            t = header.select_one(".title")
            if t: lines.append("Title: " + t.get_text(strip=True))
            tl = header.select_one(".time-limit")
            if tl: lines.append("Time: " + tl.get_text(strip=True).replace("time limit per test", "").strip(": \n"))
            ml = header.select_one(".memory-limit")
            if ml: lines.append("Memory: " + ml.get_text(strip=True).replace("memory limit per test", "").strip(": \n"))
            lines.append("")

        # Description: Find ALL content between .header and .input-specification
        # (Codeforces often uses an unnamed div, not .legend)
        desc_parts = []
        for sibling in header.find_next_siblings() if header else []:
            if sibling.name == "div" and sibling.get("class"):
                cls = " ".join(sibling.get("class"))
                if cls in ("input-specification", "output-specification", "sample-tests", "note"):
                    break
            t = get_clean(sibling)
            if t:
                desc_parts.append(t)
        if desc_parts:
            lines.append("Description:")
            lines.append("\n".join(desc_parts))
            lines.append("")

        inp_sec = c.select_one(".input-specification")
        if inp_sec:
            inp_text = strip_sec_name(get_clean(inp_sec), "Input")
            if inp_text:
                lines.append("Input:")
                lines.append(inp_text)
                lines.append("")

        out_sec = c.select_one(".output-specification")
        if out_sec:
            out_text = strip_sec_name(get_clean(out_sec), "Output")
            if out_text:
                lines.append("Output:")
                lines.append(out_text)
                lines.append("")

        for i, s in enumerate(c.select(".sample-test"), 1):
            inp = s.select_one(".input pre")
            out = s.select_one(".output pre")
            if inp:
                lines.append(f"Example {i} Input:")
                lines.append(inp.get_text("\n").strip())
                lines.append("")
            if out:
                lines.append(f"Example {i} Output:")
                lines.append(out.get_text("\n").strip())
                lines.append("")

        note = c.select_one(".note")
        if note:
            note_text = strip_sec_name(get_clean(note), "Note")
            if note_text:
                lines.append("Note:")
                lines.append(note_text)
                lines.append("")

        result = "\n".join(lines)
        # Clean up excessive blank lines
        result = re.sub(r"\n{3,}", "\n\n", result)
        # Remove lines that are just whitespace
        result = re.sub(r"^\s+$", "", result, flags=re.MULTILINE)
        return result.strip()
