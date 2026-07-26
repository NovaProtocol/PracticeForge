from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from shared.sqlalchemy_models import ApiUsage, Base, Problem, TestCase

# ── Config ──

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept-Language": "en",
}

API_PROBLEMS = "https://codeforces.com/api/problemset.problems"
ZEN_API_URL = "https://opencode.ai/zen/v1/chat/completions"
ZEN_MODEL = "deepseek-v4-flash-free"
SCRAPE_RATE = 3          # max scrapes per window
SCRAPE_WINDOW = 60       # window in seconds
AI_RATE_LIMIT = 10       # max AI calls per minute
AI_WINDOW = 60           # window in seconds for AI
ESTIMATED_TOKENS_PER_CALL = 3000
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
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    stmt = soup.select_one("div.problem-statement")
    if not stmt:
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    title_el = stmt.select_one("div.header div.title")
    if not title_el:
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    scraped_title = title_el.text.strip()
    if problem.title.lower() not in scraped_title.lower():
        problem.status = "failed"
        print(f"  Title mismatch: '{problem.title}' vs '{scraped_title}'")
        problem.last_scraped_at = datetime.now(timezone.utc)
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

    problem.status = "scraped"
    problem.last_scraped_at = datetime.now(timezone.utc)

    problem_text = stmt.get_text().lower()
    if "interactive problem" in problem_text or "protect" in problem_text:
        problem.is_interactive = True

    return True


# ── AI Enrichment ──

def check_token_limit(session: Session, estimated_tokens: int) -> bool:
    row = session.query(ApiUsage).first()
    if not row:
        row = ApiUsage(tokens_used=0)
        session.add(row)
        session.flush()

    ws = row.window_start.replace(tzinfo=timezone.utc) if row.window_start.tzinfo is None else row.window_start
    if (datetime.now(timezone.utc) - ws).total_seconds() > row.window_seconds:
        row.tokens_used = 0
        row.window_start = datetime.now(timezone.utc)

    if row.tokens_used + estimated_tokens > row.token_limit:
        return False
    row.tokens_used += estimated_tokens
    session.commit()
    return True


def update_tokens(session: Session, token_count: int):
    row = session.query(ApiUsage).first()
    if not row:
        row = ApiUsage(tokens_used=token_count)
        session.add(row)
    else:
        row.tokens_used = (row.tokens_used or 0) + token_count
    session.commit()


def ai_enrich_problem(session: Session, problem: Problem) -> bool:
    text = problem.problem_html or problem.description_html or ""
    if not text.strip():
        return False

    api_key = os.environ.get("ZEN_API_KEY", "")
    if not api_key:
        print("  No ZEN_API_KEY set, skipping AI enrichment", flush=True)
        return False

    if not check_token_limit(session, ESTIMATED_TOKENS_PER_CALL):
        print("  Token limit reached, skipping AI enrichment", flush=True)
        return False

    prompt = f"""Return ONLY valid JSON. Do NOT include markdown, explanations, reasoning, or code fences.

Extract from this Codeforces problem, using these EXACT field names:
- title
- time_limit (e.g., "1 second")
- memory_limit (e.g., "256 megabytes")
- ai_description_html (the problem statement, fix LaTeX: $$$ → \\( \\) and $$$$ → \\[ \\])
- input_spec (include "Input:" prefix)
- output_spec (include "Output:" prefix)
- examples_json (array of {{input, output}}, at least 3)
- constraints_json (array of strings like "1 ≤ n ≤ 10^5")
- ai_base_code (Python class Solution with method def run(self, input: str) -> str:)
- ai_method_name (default "run")
- note (or empty string)

Raw problem:
{text[:6000]}"""

    try:
        r = requests.post(
            ZEN_API_URL,
            json={
                "model": ZEN_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise Codeforces problem parser. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  AI API error: {e}", flush=True)
        return False

    try:
        body = r.json()
    except json.JSONDecodeError:
        print("  AI API returned non-JSON response", flush=True)
        return False

    usage = body.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    if total_tokens:
        update_tokens(session, total_tokens)

    content = ""
    choices = body.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")

    if not content:
        print("  AI returned empty content", flush=True)
        return False

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    try:
        ai_data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  AI JSON parse error: {e}", flush=True)
        return False

    if not isinstance(ai_data, dict):
        print("  AI returned non-dict JSON", flush=True)
        return False

    problem.ai_description_html = ai_data.get("ai_description_html") or ai_data.get("description_html")
    problem.description_html = problem.ai_description_html or problem.description_html

    if ai_data.get("examples_json"):
        problem.examples_json = ai_data["examples_json"]
    if ai_data.get("constraints_json"):
        problem.constraints_json = ai_data["constraints_json"]
    if ai_data.get("ai_base_code"):
        problem.ai_base_code = ai_data["ai_base_code"]
        if not problem.base_code or problem.base_code.startswith("class Solution:\n    def run"):
            problem.base_code = ai_data["ai_base_code"]
    if ai_data.get("ai_method_name"):
        problem.ai_method_name = ai_data["ai_method_name"]
        problem.method_name = ai_data["ai_method_name"] or "run"
    if ai_data.get("note"):
        problem.notes_html = ai_data["note"]
    if ai_data.get("input_spec"):
        problem.input_spec = ai_data["input_spec"]
    if ai_data.get("output_spec"):
        problem.output_spec = ai_data["output_spec"]

    text_lower = text.lower()
    if "interactive problem" in text_lower or "protect" in text_lower:
        problem.is_interactive = True
        problem.status = "interactive"
    else:
        problem.status = "scraped"

    session.commit()
    print(f"  AI enrichment OK", flush=True)
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
                tags=tags,
                url=f"https://codeforces.com/problemset/problem/{cid}/{idx}",
                base_code="class Solution:\n    def run(self, input: str) -> str:\n        ",
                method_name="run",
                status=None,
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
            if existing.tags != tags:
                existing.tags = tags
                changed = True
            if changed:
                existing.status = None
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
    last_api_call = datetime.now(timezone.utc) - timedelta(seconds=API_INTERVAL)
    scrapes = []
    ai_calls = []
    db = SessionLocal()

    while True:
        try:
            # Remove old timestamps from the window
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=SCRAPE_WINDOW)
            scrapes = [t for t in scrapes if t > cutoff]

            # Remove old AI timestamps from the window
            ai_cutoff = now - timedelta(seconds=AI_WINDOW)
            ai_calls = [t for t in ai_calls if t > ai_cutoff]

            # Try to scrape a queued problem
            retry_cutoff = now - timedelta(seconds=RETRY_AFTER)
            queued = (
                db.query(Problem)
                .filter(
                    (Problem.status == None)
                    | (
                        (Problem.status == "failed")
                        & (Problem.last_scraped_at <= retry_cutoff)
                    )
                    | (
                        (Problem.status == "need-regeneration")
                        & (Problem.last_scraped_at <= retry_cutoff)
                    )
                )
                .order_by(Problem.id)
                .first()
            )

            if queued and len(scrapes) < SCRAPE_RATE:
                is_regen = queued.status == "need-regeneration"
                print(f"[scraper] {'Re-generating' if is_regen else 'Scraping'} {queued.contest_id}/{queued.problem_index} — {queued.title}", flush=True)
                success = scrape_problem_detail(db, queued)
                scrapes.append(now)
                if success:
                    db.commit()
                    print(f"[scraper]   Scrape OK", flush=True)
                    if len(ai_calls) < AI_RATE_LIMIT:
                        print(f"[scraper]   AI enriching...", flush=True)
                        ai_success = ai_enrich_problem(db, queued)
                        if ai_success:
                            ai_calls.append(now)
                            db.commit()
                    else:
                        print(f"[scraper]   AI rate limit reached, deferring enrichment", flush=True)
                        queued.status = "scraped"
                        db.commit()
                else:
                    db.commit()
                    print(f"[scraper]   Scrape FAILED", flush=True)
                time.sleep(1.5)
                continue

            # Check if there are scraped-but-not-AI-enriched problems
            if len(ai_calls) < AI_RATE_LIMIT:
                needs_ai = (
                    db.query(Problem)
                    .filter(
                        Problem.status == "scraped",
                        Problem.ai_description_html == None,
                        Problem.problem_html != None,
                    )
                    .order_by(Problem.id)
                    .first()
                )
                if needs_ai:
                    print(f"[scraper] AI enriching {needs_ai.contest_id}/{needs_ai.problem_index} — {needs_ai.title}", flush=True)
                    ai_success = ai_enrich_problem(db, needs_ai)
                    if ai_success:
                        ai_calls.append(now)
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
