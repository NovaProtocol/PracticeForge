from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from shared.sqlalchemy_models import Base, Problem, TestCase

# ── Config ──

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept-Language": "en",
}

API_PROBLEMS = "https://codeforces.com/api/problemset.problems"
SCRAPE_RATE = 3          # max scrapes per window
SCRAPE_WINDOW = 60       # window in seconds
API_INTERVAL = 600       # API refresh every 10 minutes
RETRY_AFTER = 300        # retry failed problems after 5 minutes
REQUEST_TIMEOUT = 30

DSN = (
    f"mysql+pymysql://{os.environ.get('MYSQL_USER', 'root')}:{os.environ['MYSQL_PASS']}"
    f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT', '3306')}"
    f"/{os.environ['MYSQL_DATABASE']}"
)


# ── DB Session ──

engine = create_engine(DSN, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)


# ── Helpers ──

def slugify(contest_id: int, index: str, title: str) -> str:
    t = re.sub(r'[^\w\s-]', '', title.lower())
    t = re.sub(r'[-\s]+', '-', t).strip('-')
    return f"{contest_id}/{index}-{t}"


def compute_slug(problem: Problem) -> str:
    return slugify(problem.contest_id, problem.problem_index, problem.title)


def extract_section(stmt, soup, section_title: str) -> str:
    sects = soup.select("div.section-title")
    for s in sects:
        if section_title.lower() in s.text.strip().lower():
            parts = []
            nxt = s.next_sibling
            while nxt:
                if hasattr(nxt, "select_one") and (
                    nxt.select_one("div.section-title") or nxt.select_one("div.sample-test")
                ):
                    break
                if hasattr(nxt, "name") and nxt.name == "div" and not nxt.select_one("div.section-title"):
                    parts.append(str(nxt))
                nxt = nxt.next_sibling
            return "".join(parts)
    return ""


# ── Scrape detail page ──

def scrape_problem_detail(session: Session, problem: Problem) -> bool:
    url = f"https://codeforces.com/problemset/problem/{problem.contest_id}/{problem.problem_index}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.encoding = "utf-8"
    except Exception:
        problem.scrape_status = "failed"
        problem.last_scraped_at = datetime.utcnow()
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    stmt = soup.select_one("div.problem-statement")
    if not stmt:
        problem.scrape_status = "failed"
        problem.last_scraped_at = datetime.utcnow()
        return False

    title_el = stmt.select_one("div.header div.title")
    if not title_el:
        problem.scrape_status = "failed"
        problem.last_scraped_at = datetime.utcnow()
        return False

    scraped_title = title_el.text.strip()
    if problem.title.lower() not in scraped_title.lower():
        problem.scrape_status = "failed"
        print(f"  Title mismatch: '{problem.title}' vs '{scraped_title}'")
        problem.last_scraped_at = datetime.utcnow()
        return False

    # Save raw HTML
    container = soup.select_one("div.problemindexholder")
    if container:
        problem.problem_html = str(container)

    # Time and memory limits
    tl_el = stmt.select_one("div.header div.time-limit")
    if tl_el:
        problem.time_limit = tl_el.text.strip()

    ml_el = stmt.select_one("div.header div.memory-limit")
    if ml_el:
        problem.memory_limit = ml_el.text.strip()

    # Description: everything between header and first section-title, excluding header
    header = stmt.select_one("div.header")
    desc_parts = []
    capture = False
    for child in stmt.children:
        if not hasattr(child, "name") or child.name != "div":
            continue
        if child == header:
            capture = True
            continue
        if child.select_one("div.section-title") or child.select_one("div.sample-test"):
            break
        if capture and not child.select_one("div.header"):
            desc_parts.append(str(child))

    problem.description_html = "".join(desc_parts)

    # Input/output specs
    problem.input_spec = extract_section(stmt, soup, "Input")
    problem.output_spec = extract_section(stmt, soup, "Output")

    # Notes
    note_el = soup.select_one("div.note")
    if note_el:
        problem.notes_html = str(note_el)

    # Update slug
    problem.slug = compute_slug(problem)

    # Sample test cases — delete old ones and insert new
    session.query(TestCase).filter(TestCase.problem_id == problem.id).delete()

    samples = soup.select("div.sample-test")
    for sample in samples:
        inputs = sample.select("div.input pre")
        outputs = sample.select("div.output pre")
        for inp, out in zip(inputs, outputs):
            tc = TestCase(
                problem_id=problem.id,
                input=inp.get_text("\n").strip(),
                expected_output=out.get_text("\n").strip(),
                args=json.dumps([inp.get_text("\n").strip()]),
                expected=json.dumps(out.get_text("\n").strip()),
                is_sample=True,
            )
            session.add(tc)

    problem.scrape_status = "scraped"
    problem.last_scraped_at = datetime.utcnow()
    return True


# ── API Sync ──

def sync_from_api(session: Session) -> tuple[int, int]:
    """Fetch the full problemset API and sync to DB. Returns (new, updated)."""
    try:
        r = requests.get(API_PROBLEMS, headers=HEADERS, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"[api] Request failed: {e}")
        return 0, 0

    if data.get("status") != "OK":
        print(f"[api] API error: {data.get('comment', 'unknown')}")
        return 0, 0

    api_problems = data["result"]["problems"]
    api_stats = data["result"]["problemStatistics"]

    solved_map = {}
    for s in api_stats:
        solved_map[(s["contestId"], s["index"])] = s.get("solvedCount", 0)

    new_count = 0
    updated_count = 0

    for p in api_problems:
        cid = p.get("contestId")
        idx = p.get("index")
        name = p.get("name", "")
        rating = p.get("rating")
        tags = p.get("tags", [])

        existing = (
            session.query(Problem)
            .filter(Problem.contest_id == cid, Problem.problem_index == idx)
            .first()
        )

        if existing is None:
            new_count += 1
            slug = slugify(cid, idx, name)
            prob = Problem(
                contest_id=cid,
                problem_index=idx,
                title=name,
                slug=slug,
                difficulty_rating=rating,
                tags=json.dumps(tags),
                url=f"https://codeforces.com/problemset/problem/{cid}/{idx}",
                base_code="class Solution:\n    def run(self, input: str) -> str:\n        ",
                method_name="run",
                scrape_status=None,
            )
            session.add(prob)
        else:
            changed = False
            if existing.title != name:
                existing.title = name
                existing.slug = slugify(cid, idx, name)
                changed = True
            if existing.difficulty_rating != rating:
                existing.difficulty_rating = rating
                changed = True
            if json.loads(existing.tags or "[]") != tags:
                existing.tags = json.dumps(tags)
                changed = True
            if changed:
                existing.scrape_status = None
                existing.description_html = None
                existing.time_limit = None
                existing.memory_limit = None
                existing.input_spec = None
                existing.output_spec = None
                existing.notes_html = None
                existing.problem_html = None
                updated_count += 1

    session.commit()
    return new_count, updated_count


# ── Main loop ──

def main():
    print("[scraper] Starting...", flush=True)
    last_api_call = datetime.utcnow() - timedelta(seconds=API_INTERVAL)
    scrapes = []
    db = SessionLocal()

    while True:
        try:
            # Remove old timestamps from the window
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=SCRAPE_WINDOW)
            scrapes = [t for t in scrapes if t > cutoff]

            # Try to scrape a queued problem
            retry_cutoff = now - timedelta(seconds=RETRY_AFTER)
            queued = (
                db.query(Problem)
                .filter(
                    (Problem.scrape_status == None)
                    | (
                        (Problem.scrape_status == "failed")
                        & (Problem.last_scraped_at <= retry_cutoff)
                    )
                )
                .order_by(Problem.id)
                .first()
            )

            if queued and len(scrapes) < SCRAPE_RATE:
                print(f"[scraper] Scraping {queued.contest_id}/{queued.problem_index} — {queued.title}", flush=True)
                success = scrape_problem_detail(db, queued)
                scrapes.append(now)
                if success:
                    db.commit()
                    print(f"[scraper]   OK", flush=True)
                else:
                    db.commit()
                    print(f"[scraper]   FAILED", flush=True)
                time.sleep(1.5)
                continue

            # Check if API refresh is due
            if (now - last_api_call).total_seconds() >= API_INTERVAL:
                print("[scraper] Refreshing from API...", flush=True)
                new, updated = sync_from_api(db)
                last_api_call = now
                print(f"[scraper]   {new} new, {updated} updated", flush=True)

            time.sleep(3)

        except Exception as e:
            import traceback
            print(f"[scraper] FATAL: {e}", flush=True)
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    main()
