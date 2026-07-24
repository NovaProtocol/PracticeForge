from __future__ import annotations

from shared.db import execute, query, query_one

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS problems (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    contest_id INTEGER NOT NULL,
    problem_index VARCHAR(3) NOT NULL,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    difficulty_rating INTEGER,
    tags JSON,
    description_html TEXT,
    url VARCHAR(255),
    solved_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contest_id, problem_index)
);

CREATE TABLE IF NOT EXISTS test_cases (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    input TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    is_sample BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'python',
    verdict VARCHAR(50) DEFAULT 'Pending',
    notes TEXT,
    passed_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    timing_ms INTEGER,
    memory_kb INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS execution_queue (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(36),
    submission_id INTEGER,
    test_case_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    status ENUM('queued','running','completed','failed') DEFAULT 'queued',
    result TEXT,
    error TEXT,
    timing_ms INTEGER,
    memory_kb INTEGER,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY (submission_id) REFERENCES solutions(id) ON DELETE CASCADE,
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auto_saves (
    problem_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (problem_id),
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
"""

SEED_PROBLEMS = [
    {
        "contest_id": 1, "problem_index": "A", "title": "A + B Problem",
        "slug": "1/A-a-plus-b", "difficulty_rating": 800,
        "tags": '["math", "implementation"]',
        "description_html": "<p>Given two integers <code>A</code> and <code>B</code>, print their sum.</p>",
        "url": "https://codeforces.com/problemset/problem/1/A",
    },
    {
        "contest_id": 1, "problem_index": "B", "title": "Max of Three",
        "slug": "1/B-max-of-three", "difficulty_rating": 800,
        "tags": '["math", "implementation"]',
        "description_html": "<p>Given three integers, print the maximum among them.</p>",
        "url": "https://codeforces.com/problemset/problem/1/B",
    },
    {
        "contest_id": 1, "problem_index": "C", "title": "Even or Odd",
        "slug": "1/C-even-or-odd", "difficulty_rating": 800,
        "tags": '["math", "implementation"]',
        "description_html": "<p>Given an integer <code>N</code>, print \"Even\" if it is even, or \"Odd\" if it is odd.</p>",
        "url": "https://codeforces.com/problemset/problem/1/C",
    },
    {
        "contest_id": 1, "problem_index": "D", "title": "Count Vowels",
        "slug": "1/D-count-vowels", "difficulty_rating": 900,
        "tags": '["strings", "implementation"]',
        "description_html": "<p>Given a string <code>S</code> consisting of lowercase English letters, count the number of vowels (<code>a, e, i, o, u</code>) in it.</p>",
        "url": "https://codeforces.com/problemset/problem/1/D",
    },
    {
        "contest_id": 1, "problem_index": "E", "title": "Factorial",
        "slug": "1/E-factorial", "difficulty_rating": 900,
        "tags": '["math"]',
        "description_html": "<p>Given an integer <code>N</code> (1 &le; N &le; 12), compute <code>N!</code> (N factorial).</p>",
        "url": "https://codeforces.com/problemset/problem/1/E",
    },
]

SEED_TEST_CASES = [
    (1, "2 3", "5", True),
    (1, "10 20", "30", True),
    (1, "0 0", "0", False),
    (1, "100 200", "300", False),
    (1, "-5 5", "0", False),
    (1, "-10 -20", "-30", False),
    (1, "1 999", "1000", False),
    (1, "500 500", "1000", False),
    (1, "7 8", "15", False),
    (1, "123 456", "579", False),
    (1, "999 1", "1000", False),
    (1, "0 100", "100", False),
    (1, "-100 100", "0", False),
    (1, "256 256", "512", False),
    (1, "1 0", "1", False),
    (1, "999 999", "1998", False),
    (2, "1 2 3", "3", True),
    (2, "5 5 5", "5", True),
    (2, "10 5 3", "10", False),
    (2, "-1 -5 -3", "-1", False),
    (2, "0 0 1", "1", False),
    (2, "100 50 75", "100", False),
    (2, "4 8 2", "8", False),
    (2, "-10 -20 -30", "-10", False),
    (2, "7 7 3", "7", False),
    (2, "1 2 2", "2", False),
    (2, "999 1000 998", "1000", False),
    (2, "0 -1 -2", "0", False),
    (2, "123 122 121", "123", False),
    (2, "50 50 50", "50", False),
    (2, "3 1 4", "4", False),
    (2, "-5 0 5", "5", False),
    (3, "4", "Even", True),
    (3, "7", "Odd", True),
    (3, "0", "Even", False),
    (3, "1", "Odd", False),
    (3, "100", "Even", False),
    (3, "999", "Odd", False),
    (3, "-2", "Even", False),
    (3, "-3", "Odd", False),
    (3, "10", "Even", False),
    (3, "11", "Odd", False),
    (3, "256", "Even", False),
    (3, "257", "Odd", False),
    (3, "1024", "Even", False),
    (3, "1025", "Odd", False),
    (3, "5000", "Even", False),
    (3, "5001", "Odd", False),
    (4, "hello", "2", True),
    (4, "world", "1", True),
    (4, "aeiou", "5", False),
    (4, "bcdfg", "0", False),
    (4, "abcdefghijklmnopqrstuvwxyz", "5", False),
    (4, "programming", "3", False),
    (4, "competition", "5", False),
    (4, "python", "1", False),
    (4, "", "0", False),
    (4, "a", "1", False),
    (4, "z", "0", False),
    (4, "beautiful", "5", False),
    (4, "education", "5", False),
    (4, "algorithm", "3", False),
    (4, "datastructure", "4", False),
    (4, "openai", "4", False),
    (5, "1", "1", True),
    (5, "3", "6", True),
    (5, "2", "2", False),
    (5, "4", "24", False),
    (5, "5", "120", False),
    (5, "6", "720", False),
    (5, "7", "5040", False),
    (5, "8", "40320", False),
    (5, "9", "362880", False),
    (5, "10", "3628800", False),
    (5, "11", "39916800", False),
    (5, "12", "479001600", False),
    (5, "1", "1", False),
    (5, "2", "2", False),
    (5, "3", "6", False),
    (5, "4", "24", False),
]


MIGRATIONS = [
    "ALTER TABLE execution_queue ADD COLUMN run_id VARCHAR(36) AFTER submission_id",
    "ALTER TABLE execution_queue ADD COLUMN test_case_id INTEGER AFTER run_id",
    "ALTER TABLE execution_queue ADD COLUMN code TEXT AFTER test_case_id",
    "ALTER TABLE execution_queue ADD COLUMN timing_ms INTEGER AFTER error",
    "ALTER TABLE execution_queue ADD COLUMN memory_kb INTEGER AFTER timing_ms",
    "ALTER TABLE execution_queue MODIFY submission_id INTEGER",
    "ALTER TABLE solutions ADD COLUMN timing_ms INTEGER AFTER total_count",
    "ALTER TABLE solutions ADD COLUMN memory_kb INTEGER AFTER timing_ms",
]


def ensure_schema():
    for statement in SCHEMA_SQL.split(";"):
        stmt = statement.strip()
        if stmt:
            execute(stmt)
    for stmt in MIGRATIONS:
        try:
            execute(stmt)
        except Exception:
            pass


def ensure_seed_data():
    count = query_one("SELECT COUNT(*) AS c FROM problems")
    if count and count["c"] > 0:
        return

    problem_ids = {}
    for p in SEED_PROBLEMS:
        execute(
            """INSERT INTO problems (contest_id, problem_index, title, slug, difficulty_rating, tags, description_html, url)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (p["contest_id"], p["problem_index"], p["title"], p["slug"],
             p["difficulty_rating"], p["tags"], p["description_html"], p["url"]),
        )
        row = query_one("SELECT LAST_INSERT_ID() AS id")
        problem_ids[(p["contest_id"], p["problem_index"])] = row["id"]

    for problem_index, input_str, expected, is_sample in SEED_TEST_CASES:
        pid = problem_ids.get((1, chr(64 + problem_index)))
        if pid:
            execute(
                "INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES (%s, %s, %s, %s)",
                (pid, input_str, expected, is_sample),
            )


def run():
    ensure_schema()
    ensure_seed_data()
