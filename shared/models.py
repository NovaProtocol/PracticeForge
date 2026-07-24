from __future__ import annotations

import json
import uuid

from shared.db import execute, query, query_one


def _parse_problem(row: dict) -> dict:
    if row and isinstance(row.get("tags"), str):
        try:
            row["tags"] = json.loads(row["tags"])
        except (json.JSONDecodeError, TypeError):
            pass
    return row


def get_problems():
    rows = query("SELECT * FROM problems ORDER BY contest_id, problem_index")
    return [_parse_problem(r) for r in rows]


def get_problems_with_status():
    rows = query(
        """SELECT p.*,
                  MAX(s.verdict) AS best_verdict,
                  COUNT(s.id) AS submission_count
           FROM problems p
           LEFT JOIN solutions s ON s.problem_id = p.id
           GROUP BY p.id
           ORDER BY p.contest_id, p.problem_index"""
    )
    result = []
    for r in rows:
        p = _parse_problem(r)
        if r["best_verdict"] == "Accepted":
            p["completion"] = "completed"
        elif r["submission_count"] > 0:
            p["completion"] = "in_progress"
        else:
            p["completion"] = "incomplete"
        result.append(p)
    return result


def get_problem(contest_id: int, index: str):
    row = query_one(
        "SELECT * FROM problems WHERE contest_id = %s AND problem_index = %s",
        (contest_id, index),
    )
    return _parse_problem(row)


def get_all_tags():
    rows = query("SELECT DISTINCT tags FROM problems WHERE tags IS NOT NULL")
    seen = set()
    tags = []
    for r in rows:
        try:
            for t in json.loads(r["tags"]):
                if t not in seen:
                    seen.add(t)
                    tags.append(t)
        except (json.JSONDecodeError, TypeError):
            pass
    return sorted(tags)


def get_test_cases(problem_id: int):
    return query(
        "SELECT * FROM test_cases WHERE problem_id = %s ORDER BY id",
        (problem_id,),
    )


def get_sample_cases(problem_id: int):
    return query(
        "SELECT * FROM test_cases WHERE problem_id = %s AND is_sample = TRUE ORDER BY id",
        (problem_id,),
    )


def get_all_test_cases(problem_id: int):
    return query(
        "SELECT * FROM test_cases WHERE problem_id = %s ORDER BY id",
        (problem_id,),
    )


def create_solution(problem_id: int, code: str, timing_ms: int = 0, memory_kb: int = 0, language: str = "python"):
    execute(
        """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count, timing_ms, memory_kb)
           VALUES (%s, %s, %s, 'Accepted', 0, 0, %s, %s)""",
        (problem_id, code, language, timing_ms, memory_kb),
    )
    return query_one("SELECT LAST_INSERT_ID() AS id")["id"]


def get_solution(solution_id: int):
    return query_one("SELECT * FROM solutions WHERE id = %s", (solution_id,))


def get_solutions_for_problem(problem_id: int):
    return query(
        """SELECT s.* FROM solutions s
           WHERE s.problem_id = %s
           ORDER BY s.created_at DESC""",
        (problem_id,),
    )


def get_solutions():
    return query(
        """SELECT s.*, p.title, p.slug, p.contest_id, p.problem_index
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           ORDER BY s.created_at DESC"""
    )


# ── Runs (ad-hoc per-test-case execution) ──

def create_run(problem_id: int, code: str) -> str:
    run_id = str(uuid.uuid4())
    execute(
        "INSERT INTO runs (id, problem_id, code) VALUES (%s, %s, %s)",
        (run_id, problem_id, code),
    )
    return run_id


def queue_test_cases(run_id: str, problem_id: int, code: str):
    test_cases = get_all_test_cases(problem_id)
    for tc in test_cases:
        execute(
            """INSERT INTO execution_queue (run_id, test_case_id, code, status)
               VALUES (%s, %s, %s, 'queued')""",
            (run_id, tc["id"], code),
        )
    return len(test_cases)


def get_run_status(run_id: str):
    run = query_one("SELECT * FROM runs WHERE id = %s", (run_id,))
    if not run:
        return None
    entries = query(
        """SELECT q.*, tc.input, tc.expected_output, tc.is_sample
           FROM execution_queue q
           JOIN test_cases tc ON tc.id = q.test_case_id
           WHERE q.run_id = %s
           ORDER BY q.id""",
        (run_id,),
    )
    total = len(entries)
    passed = sum(1 for e in entries if e["status"] == "completed" and e["result"] and e["result"].strip() == e["expected_output"].strip())
    all_done = all(e["status"] in ("completed", "failed") for e in entries)

    if all_done:
        execute("UPDATE runs SET status = 'completed', completed_at = NOW() WHERE id = %s", (run_id,))

    return {
        "run_id": run_id,
        "status": "completed" if all_done else "running",
        "passed": passed,
        "total": total,
        "entries": [
            {
                "id": e["id"],
                "test_case_id": e["test_case_id"],
                "status": e["status"],
                "input": e["input"],
                "expected": e["expected_output"],
                "got": e["result"] or "",
                "error": e["error"] or "",
                "timing_ms": e["timing_ms"],
                "memory_kb": e["memory_kb"],
                "is_sample": bool(e["is_sample"]),
            }
            for e in entries
        ],
    }


# ── Auto-save ──

def save_code(problem_id: int, code: str):
    execute(
        "INSERT INTO auto_saves (problem_id, code) VALUES (%s, %s) ON DUPLICATE KEY UPDATE code = %s",
        (problem_id, code, code),
    )


def load_code(problem_id: int) -> str | None:
    row = query_one("SELECT code FROM auto_saves WHERE problem_id = %s", (problem_id,))
    return row["code"] if row else None


# ── Submission queue (full submit) ──

def get_submission_status(solution_id: int):
    solution = query_one(
        "SELECT id, problem_id, verdict, passed_count, total_count, timing_ms, memory_kb FROM solutions WHERE id = %s",
        (solution_id,),
    )
    if not solution:
        return None
    return {
        "solution_id": solution["id"],
        "verdict": solution["verdict"],
        "passed": solution["passed_count"],
        "total": solution["total_count"],
        "timing_ms": solution["timing_ms"],
        "memory_kb": solution["memory_kb"],
    }


def queue_full_submission(problem_id: int, code: str, run_id: str) -> int:
    """After a successful run, create a solution and move queue entries to reference it."""
    total_timing = 0
    total_memory = 0
    entries = query("SELECT * FROM execution_queue WHERE run_id = %s", (run_id,))
    total = len(entries)
    passed = sum(1 for e in entries if e["status"] == "completed")
    for e in entries:
        total_timing += e["timing_ms"] or 0
        total_memory = max(total_memory, e["memory_kb"] or 0)

    solution_id = create_solution(problem_id, code, int(total_timing / max(total, 1)), total_memory)
    execute("UPDATE solutions SET passed_count = %s, total_count = %s WHERE id = %s", (passed, total, solution_id))
    execute("UPDATE execution_queue SET submission_id = %s WHERE run_id = %s", (solution_id, run_id))
    return solution_id


# ── Public API ──

def get_stats():
    total = query_one("SELECT COUNT(*) AS count FROM problems")
    solved = query_one(
        "SELECT COUNT(DISTINCT problem_id) AS count FROM solutions WHERE verdict = 'Accepted'"
    )
    by_difficulty = query(
        """SELECT
             CASE
               WHEN p.difficulty_rating < 1200 THEN 'easy'
               WHEN p.difficulty_rating < 1600 THEN 'medium'
               ELSE 'hard'
             END AS difficulty,
             COUNT(DISTINCT s.problem_id) AS count
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           WHERE s.verdict = 'Accepted'
           GROUP BY difficulty"""
    )
    recent = query(
        """SELECT p.title, p.slug, p.difficulty_rating AS difficulty, s.verdict, DATE(s.created_at) AS date
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           WHERE s.verdict = 'Accepted'
           ORDER BY s.created_at DESC LIMIT 10"""
    )
    return {
        "solved": solved["count"] if solved else 0,
        "total": total["count"] if total else 0,
        "by_difficulty": {r["difficulty"]: r["count"] for r in by_difficulty},
        "recent_solutions": recent,
    }


def get_solved():
    return query(
        """SELECT DISTINCT p.contest_id, p.problem_index, p.title, p.slug, p.difficulty_rating
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           WHERE s.verdict = 'Accepted'
           ORDER BY p.contest_id, p.problem_index"""
    )


def re_run_solution(solution_id: int) -> str | None:
    solution = get_solution(solution_id)
    if not solution or solution["verdict"] != "Accepted":
        return None
    run_id = create_run(solution["problem_id"], solution["code"])
    queue_test_cases(run_id, solution["problem_id"], solution["code"])
    return run_id


def get_completion_counts():
    rows = query(
        """SELECT p.id, p.contest_id, p.problem_index,
                  MAX(s.verdict) AS verdict
           FROM problems p
           LEFT JOIN solutions s ON s.problem_id = p.id
           GROUP BY p.id, p.contest_id, p.problem_index"""
    )
    counts = {"completed": 0, "in_progress": 0, "incomplete": 0}
    for r in rows:
        if r["verdict"] == "Accepted":
            counts["completed"] += 1
        elif r["verdict"]:
            counts["in_progress"] += 1
        else:
            counts["incomplete"] += 1
    return counts
