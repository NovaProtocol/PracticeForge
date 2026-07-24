from __future__ import annotations

from shared.db import execute, query, query_one


def get_problems():
    return query("SELECT * FROM problems ORDER BY contest_id, problem_index")


def get_problem(contest_id: int, index: str):
    return query_one(
        "SELECT * FROM problems WHERE contest_id = %s AND problem_index = %s",
        (contest_id, index),
    )


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


def create_solution(problem_id: int, code: str, language: str = "python"):
    execute(
        """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count)
           VALUES (%s, %s, %s, 'Pending', 0, 0)""",
        (problem_id, code, language),
    )
    return query_one("SELECT LAST_INSERT_ID() AS id")["id"]


def get_solution(solution_id: int):
    return query_one("SELECT * FROM solutions WHERE id = %s", (solution_id,))


def get_solutions():
    return query(
        """SELECT s.*, p.title, p.slug, p.contest_id, p.problem_index
           FROM solutions s
           JOIN problems p ON p.id = s.problem_id
           ORDER BY s.created_at DESC"""
    )


def queue_execution(submission_id: int):
    execute(
        "INSERT INTO execution_queue (submission_id, status) VALUES (%s, 'queued')",
        (submission_id,),
    )


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
