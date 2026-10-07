import contextlib
import time

from . import log
from .config import BROWSER_DATA_DIR, CF_POLL


class Browser:
    """Manages a persistent headful Chromium context for scraping.

    The profile is saved to `browser_profile/` so cookies and Cloudflare
    clearance persist across restarts. If Cloudflare shows a captcha, the
    scraper loops with a 1s delay until you solve it in the browser window.
    """

    def __init__(self):
        self._playwright = None
        self._context = None
        self._page = None

    def start(self):
        try:
            self._start()
        except Exception as e:
            self._page = None
            self._context = None
            self._playwright = None
            raise e

    def _start(self):
        from playwright.sync_api import sync_playwright

        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    @property
    def page(self):
        if self._page is None:
            self._start()
        return self._page

    def scrape_problem_page(self, cid: int, idx: str) -> str | None:
        url = f"https://codeforces.com/problemset/problem/{cid}/{idx}"
        log.info(f"Opening {url}")
        page = self.page
        page.goto(url)

        try:
            page.wait_for_selector(
                "div.problem-statement, #challenge-error-title, title",
                timeout=30000,
            )
        except Exception:
            log.error("Page load timeout (30s)")
            return None

        try:
            while self._is_cloudflare_blocked():
                log.info("Cloudflare captcha, solve it in the browser window, waiting...")
                time.sleep(CF_POLL)
        except Exception as e:
            log.error(f"Cloudflare check failed (browser gone?): {e}")
            return None

        time.sleep(2)
        return page.content()

    def _is_cloudflare_blocked(self) -> bool:
        page = self.page
        title = (page.title() or "").lower()
        return "just a moment" in title or page.locator("#challenge-error-title").count() > 0

    def close(self):
        if self._context:
            with contextlib.suppress(Exception):
                self._context.close()
        if self._playwright:
            with contextlib.suppress(Exception):
                self._playwright.stop()
        self._page = None
        self._context = None
        self._playwright = None
