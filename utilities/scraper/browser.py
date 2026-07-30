import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import CF_POLL, BROWSER_DATA_DIR
from . import log


class Browser:
    """Manages a persistent Chrome WebDriver with a real GUI window.

    The browser profile is saved to `edge_profile/` so cookies and
    Cloudflare clearance persist across restarts. If Cloudflare shows
    a captcha, the scraper loops with 1s delay until you solve it.
    """

    def __init__(self):
        self._driver = None

    def start(self):
        try:
            self._start()
        except Exception as e:
            self._driver = None
            raise e

    def _start(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        service = Service(ChromeDriverManager().install())
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={BROWSER_DATA_DIR}")
        opts.add_argument("--disable-blink-features=AutomationControlled")

        self._driver = webdriver.Chrome(service=service, options=opts)

    @property
    def driver(self):
        if self._driver is None:
            self._start()
        return self._driver

    def scrape_problem_page(self, cid: int, idx: str) -> str | None:
        url = f"https://codeforces.com/problemset/problem/{cid}/{idx}"
        log.info(f"Opening {url}")
        self.driver.get(url)

        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div.problem-statement, #challenge-error-title, title",
                ))
            )
        except Exception:
            log.error("Page load timeout (30s)")
            return None

        while self._is_cloudflare_blocked():
            log.info("Cloudflare captcha — solve it in the browser window, waiting...")
            time.sleep(CF_POLL)

        time.sleep(2)
        return self.driver.page_source

    def _is_cloudflare_blocked(self) -> bool:
        title = self.driver.title.lower()
        return "just a moment" in title or bool(
            self.driver.find_elements(By.ID, "challenge-error-title")
        )

    def close(self):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
