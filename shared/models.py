from __future__ import annotations

import contextlib
import json

from shared.db import execute, query, query_one


def _parse_problem(row: dict) -> dict:
    if row and isinstance(row.get("tags"), str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            row["tags"] = json.loads(row["tags"])
    return row


def get_problems_summary():
    """Lightweight list, no description_html or large text fields."""
    rows = query(
        """SELECT p.id, p.contest_id, p.problem_index, p.title, p.slug,
                  p.difficulty_rating, p.tags, p.time_limit, p.memory_limit, p.url,
                  MAX(s.verdict) AS best_verdict,
                  COUNT(s.id) AS submission_count
           FROM problems p
           LEFT JOIN solutions s ON s.problem_id = p.id
           GROUP BY p.id
           ORDER BY p.contest_id, p.problem_index"""
    )
    result = []
    for r in rows:
        p = {
            "id": r["id"],
            "contest_id": r["contest_id"],
            "problem_index": r["problem_index"],
            "title": r["title"],
            "slug": r["slug"],
            "difficulty_rating": r["difficulty_rating"],
            "time_limit": r["time_limit"],
            "memory_limit": r["memory_limit"],
            "url": r["url"],
            "submission_count": r["submission_count"],
        }
        tags = r.get("tags")
        p["tags"] = json.loads(tags) if isinstance(tags, str) else (tags or [])
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


def create_solution(
    problem_id: int,
    code: str,
    verdict: str = "Pending",
    passed: int = 0,
    total: int = 0,
    timing_ms: int = 0,
    memory_kb: int = 0,
    language: str = "python",
):
    return execute(
        """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count, timing_ms, memory_kb)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (problem_id, code, language, verdict, passed, total, timing_ms, memory_kb),
    )


def get_solution(solution_id: int):
    return query_one("SELECT * FROM solutions WHERE id = %s", (solution_id,))


def get_solution_results(solution_id: int) -> str:
    """Get the stored JSON result from the execution queue for a solution."""
    row = query_one(
        "SELECT result, stdout FROM execution_queue WHERE solution_id = %s ORDER BY id DESC LIMIT 1",
        (solution_id,),
    )
    return {"result": row["result"] if row else "{}", "stdout": row["stdout"] if row else ""}


def get_solutions():
    return query(
        """SELECT s.*, p.title, p.slug, p.contest_id, p.problem_index
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           ORDER BY s.created_at DESC"""
    )


# ── Auto-save ──


def list_files(problem_id: int) -> list:
    rows = query(
        "SELECT filename, code, last_ran FROM auto_saves WHERE problem_id = %s AND active = TRUE ORDER BY filename",
        (problem_id,),
    )
    return rows if rows else []


def save_code(problem_id: int, code: str, filename: str = "main.py"):
    execute(
        "UPDATE auto_saves SET code = %s WHERE problem_id = %s AND filename = %s AND active = TRUE",
        (code, problem_id, filename),
    )


def create_file(problem_id: int, filename: str, code: str = ""):
    execute(
        "INSERT INTO auto_saves (problem_id, filename, code, active) VALUES (%s, %s, %s, TRUE)",
        (problem_id, filename, code),
    )


def rename_file(problem_id: int, old_filename: str, new_filename: str):
    execute(
        "UPDATE auto_saves SET filename = %s WHERE problem_id = %s AND filename = %s AND active = TRUE",
        (new_filename, problem_id, old_filename),
    )


def delete_file(problem_id: int, filename: str):
    execute(
        "UPDATE auto_saves SET active = FALSE WHERE problem_id = %s AND filename = %s",
        (problem_id, filename),
    )


def save_last_ran(problem_id: int, code: str, filename: str = "main.py"):
    execute(
        "UPDATE auto_saves SET last_ran = %s WHERE problem_id = %s AND filename = %s AND active = TRUE",
        (code, problem_id, filename),
    )


def load_code(problem_id: int, filename: str = "main.py") -> dict:
    row = query_one(
        "SELECT code, last_ran FROM auto_saves WHERE problem_id = %s AND filename = %s",
        (problem_id, filename),
    )
    return {"code": row["code"] if row else None, "last_ran": row["last_ran"] if row else None}


# ── Public API ──


def upsert_problem(data: dict) -> int:
    """Insert or update a problem from uploaded data. Returns problem id."""
    slug = f"{data['contest_id']}/{data['problem_index']}-{data['title'].lower().replace(' ', '-')}"
    execute(
        """INSERT INTO problems (contest_id, problem_index, title, slug, difficulty_rating, tags,
            base_code, method_name, description_html, time_limit, memory_limit,
            input_spec, output_spec, examples_json, constraints_json,
            solution_code, generator_code, executor_code, hints, url)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
            title=VALUES(title), slug=VALUES(slug), difficulty_rating=VALUES(difficulty_rating),
            tags=VALUES(tags), base_code=VALUES(base_code), method_name=VALUES(method_name),
            description_html=VALUES(description_html), time_limit=VALUES(time_limit),
            memory_limit=VALUES(memory_limit), input_spec=VALUES(input_spec),
            output_spec=VALUES(output_spec), examples_json=VALUES(examples_json),
            constraints_json=VALUES(constraints_json),
            solution_code=VALUES(solution_code), generator_code=VALUES(generator_code),
            executor_code=VALUES(executor_code),
            hints=VALUES(hints), url=VALUES(url)""",
        (
            data["contest_id"],
            data["problem_index"],
            data["title"],
            slug,
            data.get("difficulty_rating"),
            data.get("tags"),
            data.get("base_code"),
            data.get("method_name"),
            data.get("description_html"),
            data.get("time_limit"),
            data.get("memory_limit"),
            data.get("input_spec"),
            data.get("output_spec"),
            data.get("examples_json"),
            data.get("constraints_json"),
            data.get("solution_code"),
            data.get("generator_code"),
            data.get("executor_code"),
            data.get("hints"),
            data.get("url"),
        ),
    )
    row = query_one(
        "SELECT id FROM problems WHERE contest_id = %s AND problem_index = %s",
        (data["contest_id"], data["problem_index"]),
    )
    return row["id"] if row else None


def get_problem_submissions(problem_id: int) -> list:
    return query(
        """SELECT id, verdict, passed_count, total_count, code, timing_ms, memory_kb, created_at
           FROM solutions WHERE problem_id = %s
           ORDER BY created_at DESC""",
        (problem_id,),
    )


def get_editorial(problem_id: int) -> dict | None:
    return None


# ── Images ──


def create_image(filename: str, data: bytes, content_type: str = "image/png"):
    return execute(
        """INSERT INTO problem_images (filename, data, content_type) VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE data = VALUES(data), content_type = VALUES(content_type)""",
        (filename, data, content_type),
    )


def get_image(filename: str):
    return query_one(
        "SELECT filename, data, content_type FROM problem_images WHERE filename = %s",
        (filename,),
    )


def image_exists(filename: str) -> bool:
    row = query_one("SELECT id FROM problem_images WHERE filename = %s", (filename,))
    return row is not None


def delete_image(filename: str):
    execute("DELETE FROM problem_images WHERE filename = %s", (filename,))
