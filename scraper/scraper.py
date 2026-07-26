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
ZEN_API_KEY = os.environ.get("ZEN_API_KEY", "")
ZEN_BASE_URL = "https://opencode.ai/zen/go/v1"
ZEN_MODEL = "deepseek-v4-flash"
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
    except Exception as e:
        import traceback
        print(f"  FAILED: request error — {e}", flush=True)
        traceback.print_exc()
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    # Check for Cloudflare block
    if len(r.text) < 2000 and ("cloudflare" in r.text.lower() or "just a moment" in r.text.lower()):
        print(f"  FAILED: Cloudflare blocked (HTTP {r.status_code}, response {len(r.text)} bytes)", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    stmt = soup.select_one("div.problem-statement")
    if not stmt:
        print(f"  FAILED: no problem-statement div found (HTTP {r.status_code}, response {len(r.text)} bytes)", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    title_el = stmt.select_one("div.header div.title")
    if not title_el:
        print(f"  FAILED: no title element found (HTTP {r.status_code})", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    scraped_title = title_el.text.strip()
    if problem.title.lower() not in scraped_title.lower():
        print(f"  FAILED: title mismatch — DB='{problem.title}' vs page='{scraped_title}'", flush=True)
        problem.status = "failed"
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

    # Don't set status here — wait for AI enrichment to succeed
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
    # Get the raw problem HTML — use the cleaned HTML from scrape, not just text
    url = f"https://codeforces.com/problemset/problem/{problem.contest_id}/{problem.problem_index}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.encoding = "utf-8"
    except Exception as e:
        import traceback
        print(f"  AI fetch error: {e}", flush=True)
        traceback.print_exc()
        return False

    soup = BeautifulSoup(r.text, "html.parser")

    # Use robust container selection matching scrape_problem_detail
    container = soup.select_one("div.problemindexholder")
    if not container:
        container = soup.select_one("div.problem-statement")
    if not container:
        print("  AI: could not locate problem statement container", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    # Preserve MathJax / TeX formulas
    for script_el in container.select("script[type='math/tex']"):
        latex_text = f"${script_el.string}$"
        script_el.replace_with(soup.new_string(latex_text))
    for script_el in container.select("script[type='math/tex; mode=display']"):
        latex_text = f"$${script_el.string}$$"
        script_el.replace_with(soup.new_string(latex_text))
    for span_el in container.select(".MathJax"):
        math_script = span_el.find("script", {"type": "math/tex"})
        if math_script:
            span_el.replace_with(soup.new_string(f"${math_script.string}$"))

    for element in container.select("style, .alert, .diff-notifier"):
        element.decompose()

    html_content = str(container)

    if not html_content.strip():
        print("  AI: empty HTML after cleaning", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    if not ZEN_API_KEY:
        print("  No ZEN_API_KEY set, skipping AI enrichment", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    if not check_token_limit(session, ESTIMATED_TOKENS_PER_CALL):
        print("  Token limit reached, skipping AI enrichment", flush=True)
        # Don't mark as failed — it'll retry when tokens reset
        return False

    system_prompt = r"""You are an expert Python educational coding platform engine for high school students. Extract problem data from the HTML into this exact JSON structure:
{
  "title": "",
  "time_limit": "",
  "memory_limit": "",
  "input": "",
  "output": "",
  "description": "",
  "input_specification": "",
  "output_specification": "",
  "examples": [
    {
      "input": [],
      "output": 0
    }
  ],
  "constraints": [],
  "hints": [],
  "is_interactive": false,
  "base_code": "",
  "solution_code": "",
  "generator_code": ""
}

Guidelines (Strictly Python-Centric):
1. MATH CONVERSION: Ensure all mathematical variables and expressions are cleanly formatted using standard LaTeX (e.g., $n$, $n \times m$, $998\,244\,353$) so they render properly on the frontend.
2. DESCRIPTION: Rewrite the problem description so it reads like a clean, standalone coding challenge (like LeetCode). Strip out all competitive programming I/O boilerplate (e.g., ignore mentions of "the first line contains t test cases", "standard input", or raw stream reading). Focus entirely on explaining the core logical task using the input variables provided to the function.
3. CONSTRAINTS: Bulleted list of constraints inferred or stated.
4. HINTS: Python-friendly logic tips and algorithmic hints.
5. IS_INTERACTIVE: Set to true if the problem requires real-time interaction (flushing stdout/reading queries interactively), otherwise false.
6. EXAMPLES: Parse raw sample test cases into an array (`examples`). NEVER use newline strings (`\n`). Every individual test case must have its inputs fully parsed into native JSON types (integers, floats, lists, or lists of lists matching the problem parameters, excluding the global test case count $t$), and the output must be cast to its correct primitive type.
7. BASE_CODE: Provide a friendly LeetCode-style starter code for students. Do NOT use a generic `parsed_input: list`. Instead, write explicit parameter names with clear type hints matching the problem's inputs (e.g., `def run(self, h: int, n: int, damage: list, cooldown: list) -> int:`).
   Example template style:
   class Solution:
       def run(self, h: int, n: int, damage: list, cooldown: list) -> int:
           # Write your code here
           pass
8. SOLUTION_CODE: Provide the working reference solution matching the base code signature for student review when stuck.
9. GENERATOR_CODE: Provide a Python script (using the random module) that dynamically generates valid test cases conforming to the problem's constraints. It should output a string or list representing test cases.
10. Return ONLY pure JSON."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=ZEN_API_KEY, base_url=ZEN_BASE_URL)
        response = client.chat.completions.create(
            model=ZEN_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": html_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
    except Exception as e:
        import traceback
        print(f"  AI API error: {e}", flush=True)
        traceback.print_exc()
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    content = response.choices[0].message.content
    if not content:
        print("  AI returned empty content", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    try:
        ai_data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  AI JSON parse error: {e}", flush=True)
        print(f"  Raw: {content[:1000]}", flush=True)
        problem.status = "failed"
        problem.last_scraped_at = datetime.now(timezone.utc)
        return False

    total_tokens = response.usage.total_tokens
    if total_tokens:
        update_tokens(session, total_tokens)
    print(f"  AI enrichment OK ({total_tokens} tokens)", flush=True)

    # Map AI fields to our schema
    problem.ai_description_html = ai_data.get("description") or ""
    if problem.ai_description_html:
        problem.description_html = problem.ai_description_html
    problem.time_limit = ai_data.get("time_limit") or problem.time_limit
    problem.memory_limit = ai_data.get("memory_limit") or problem.memory_limit
    problem.input_spec = ai_data.get("input_specification") or ai_data.get("input") or ""
    problem.output_spec = ai_data.get("output_specification") or ai_data.get("output") or ""
    if ai_data.get("examples"):
        problem.examples_json = ai_data["examples"]
    if ai_data.get("constraints"):
        problem.constraints_json = ai_data["constraints"]
    if ai_data.get("base_code"):
        problem.ai_base_code = ai_data["base_code"]
        problem.base_code = ai_data["base_code"]
    if ai_data.get("solution_code"):
        problem.ai_method_name = "run"

    # Detect interactive
    text_lower = html_content.lower()
    if ai_data.get("is_interactive") or "interactive problem" in text_lower or "protect" in text_lower:
        problem.is_interactive = True
        problem.status = "interactive"
    else:
        problem.status = "ready"

    session.commit()
    return True


# ── API Sync ──

def sync_from_api(session: Session) -> tuple[int, int]:
    """Fetch the full problemset API and sync to DB. Returns (new, updated)."""
    try:
        r = requests.get(API_PROBLEMS, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except json.JSONDecodeError:
        import traceback
        print(f"[api] Non-JSON response ({r.status_code}), body: {r.text[:500]}", flush=True)
        traceback.print_exc()
        return 0, 0
    except Exception as e:
        import traceback
        print(f"[api] Request failed: {e}", flush=True)
        traceback.print_exc()
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
                    print(f"[scraper]   Scrape OK", flush=True)
                    if len(ai_calls) < AI_RATE_LIMIT:
                        print(f"[scraper]   AI enriching...", flush=True)
                        ai_success = ai_enrich_problem(db, queued)
                        if ai_success:
                            ai_calls.append(now)
                        db.commit()
                    else:
                        print(f"[scraper]   AI rate limit reached, deferring enrichment", flush=True)
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
                        Problem.status == "ready",
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
