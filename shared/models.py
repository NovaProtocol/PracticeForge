from __future__ import annotations
import json

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


def get_all_test_cases(problem_id: int):
    return query(
        "SELECT * FROM test_cases WHERE problem_id = %s ORDER BY id",
        (problem_id,),
    )


def get_all_test_cases_json(problem_id: int):
    """Returns test cases suitable for LeetCode-style execution (args+expected JSON)."""
    return query(
        "SELECT id, args, expected, is_sample FROM test_cases WHERE problem_id = %s AND args IS NOT NULL ORDER BY id",
        (problem_id,),
    )


def get_sample_cases_json(problem_id: int):
    return query(
        "SELECT id, args, expected FROM test_cases WHERE problem_id = %s AND is_sample = TRUE AND args IS NOT NULL ORDER BY id",
        (problem_id,),
    )


def get_sample_cases(problem_id: int):
    return query(
        "SELECT * FROM test_cases WHERE problem_id = %s AND is_sample = TRUE ORDER BY id",
        (problem_id,),
    )


def create_solution(problem_id: int, code: str, verdict: str = "Pending", passed: int = 0, total: int = 0, timing_ms: int = 0, memory_kb: int = 0, language: str = "python"):
    execute(
        """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count, timing_ms, memory_kb)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (problem_id, code, language, verdict, passed, total, timing_ms, memory_kb),
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





# ── Auto-save ──

def save_code(problem_id: int, code: str):
    execute(
        "INSERT INTO auto_saves (problem_id, code) VALUES (%s, %s) ON DUPLICATE KEY UPDATE code = %s",
        (problem_id, code, code),
    )


def load_code(problem_id: int) -> str | None:
    row = query_one("SELECT code FROM auto_saves WHERE problem_id = %s", (problem_id,))
    return row["code"] if row else None





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





def get_problem_submissions(problem_id: int) -> list:
    return query(
        """SELECT id, verdict, passed_count, total_count, code, timing_ms, memory_kb, created_at
           FROM solutions WHERE problem_id = %s
           ORDER BY created_at DESC""",
        (problem_id,),
    )


def get_editorial(problem_id: int) -> dict | None:
    return None


def create_custom_test_case(problem_id: int, input_data: str, expected_output: str) -> int:
    execute(
        "INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES (%s, %s, %s, FALSE)",
        (problem_id, input_data, expected_output),
    )
    return query_one("SELECT LAST_INSERT_ID() AS id")["id"]


def delete_custom_test_case(tc_id: int) -> bool:
    execute("DELETE FROM test_cases WHERE id = %s", (tc_id,))
    return True






