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
    base_code TEXT,
    method_name VARCHAR(100),
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
    args JSON,
    expected JSON,
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
    problem_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    method_name VARCHAR(100),
    test_cases_json JSON,
    exec_type ENUM('run','submit') DEFAULT 'run',
    status ENUM('queued','running','completed','failed') DEFAULT 'queued',
    result TEXT,
    error TEXT,
    timing_ms INTEGER,
    memory_kb INTEGER,
    solution_id INTEGER,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
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
        "description_html": "<p>Given two integers <code>a</code> and <code>b</code>, return their sum.</p>",
        "url": "https://leetcode.com/problems/two-sum/",
        "base_code": "class Solution:\n    def add(self, a: int, b: int) -> int:\n        ",
        "method_name": "add",
    },
    {
        "contest_id": 1, "problem_index": "B", "title": "Max of Three",
        "slug": "1/B-max-of-three", "difficulty_rating": 800,
        "tags": '["math", "implementation"]',
        "description_html": "<p>Given three integers <code>a</code>, <code>b</code>, and <code>c</code>, return the maximum among them.</p>",
        "url": "https://codeforces.com/problemset/problem/1/B",
        "base_code": "class Solution:\n    def maxOfThree(self, a: int, b: int, c: int) -> int:\n        ",
        "method_name": "maxOfThree",
    },
    {
        "contest_id": 1, "problem_index": "C", "title": "Even or Odd",
        "slug": "1/C-even-or-odd", "difficulty_rating": 800,
        "tags": '["math", "implementation"]',
        "description_html": "<p>Given an integer <code>n</code>, return \"Even\" if it is even, or \"Odd\" if it is odd.</p>",
        "url": "https://codeforces.com/problemset/problem/1/C",
        "base_code": "class Solution:\n    def evenOrOdd(self, n: int) -> str:\n        ",
        "method_name": "evenOrOdd",
    },
    {
        "contest_id": 1, "problem_index": "D", "title": "Count Vowels",
        "slug": "1/D-count-vowels", "difficulty_rating": 900,
        "tags": '["strings", "implementation"]',
        "description_html": "<p>Given a string <code>s</code> consisting of lowercase English letters, return the number of vowels (<code>a, e, i, o, u</code>) in it.</p>",
        "url": "https://codeforces.com/problemset/problem/1/D",
        "base_code": "class Solution:\n    def countVowels(self, s: str) -> int:\n        ",
        "method_name": "countVowels",
    },
    {
        "contest_id": 1, "problem_index": "E", "title": "Factorial",
        "slug": "1/E-factorial", "difficulty_rating": 900,
        "tags": '["math"]',
        "description_html": "<p>Given an integer <code>n</code> (1 &le; n &le; 12), return <code>n!</code> (n factorial).</p>",
        "url": "https://codeforces.com/problemset/problem/1/E",
        "base_code": "class Solution:\n    def factorial(self, n: int) -> int:\n        ",
        "method_name": "factorial",
    },
]

SEED_TEST_CASES = [
    # (problem_num, is_sample, args_json, expected_json)
    (1, True, '[2, 3]', '5'),
    (1, True, '[10, 20]', '30'),
    (1, False, '[0, 0]', '0'),
    (1, False, '[100, 200]', '300'),
    (1, False, '[-5, 5]', '0'),
    (1, False, '[-10, -20]', '-30'),
    (1, False, '[1, 999]', '1000'),
    (1, False, '[500, 500]', '1000'),
    (1, False, '[7, 8]', '15'),
    (1, False, '[123, 456]', '579'),
    (1, False, '[999, 1]', '1000'),
    (1, False, '[0, 100]', '100'),
    (1, False, '[-100, 100]', '0'),
    (1, False, '[256, 256]', '512'),
    (1, False, '[1, 0]', '1'),
    (1, False, '[999, 999]', '1998'),
    (2, True, '[1, 2, 3]', '3'),
    (2, True, '[5, 5, 5]', '5'),
    (2, False, '[10, 5, 3]', '10'),
    (2, False, '[-1, -5, -3]', '-1'),
    (2, False, '[0, 0, 1]', '1'),
    (2, False, '[100, 50, 75]', '100'),
    (2, False, '[4, 8, 2]', '8'),
    (2, False, '[-10, -20, -30]', '-10'),
    (2, False, '[7, 7, 3]', '7'),
    (2, False, '[1, 2, 2]', '2'),
    (2, False, '[999, 1000, 998]', '1000'),
    (2, False, '[0, -1, -2]', '0'),
    (2, False, '[123, 122, 121]', '123'),
    (2, False, '[50, 50, 50]', '50'),
    (2, False, '[3, 1, 4]', '4'),
    (2, False, '[-5, 0, 5]', '5'),
    (3, True, '[4]', '"Even"'),
    (3, True, '[7]', '"Odd"'),
    (3, False, '[0]', '"Even"'),
    (3, False, '[1]', '"Odd"'),
    (3, False, '[100]', '"Even"'),
    (3, False, '[999]', '"Odd"'),
    (3, False, '[-2]', '"Even"'),
    (3, False, '[-3]', '"Odd"'),
    (3, False, '[10]', '"Even"'),
    (3, False, '[11]', '"Odd"'),
    (3, False, '[256]', '"Even"'),
    (3, False, '[257]', '"Odd"'),
    (3, False, '[1024]', '"Even"'),
    (3, False, '[1025]', '"Odd"'),
    (3, False, '[5000]', '"Even"'),
    (3, False, '[5001]', '"Odd"'),
    (4, True, '["hello"]', '2'),
    (4, True, '["world"]', '1'),
    (4, False, '["aeiou"]', '5'),
    (4, False, '["bcdfg"]', '0'),
    (4, False, '["abcdefghijklmnopqrstuvwxyz"]', '5'),
    (4, False, '["programming"]', '3'),
    (4, False, '["competition"]', '5'),
    (4, False, '["python"]', '1'),
    (4, False, '[""]', '0'),
    (4, False, '["a"]', '1'),
    (4, False, '["z"]', '0'),
    (4, False, '["beautiful"]', '5'),
    (4, False, '["education"]', '5'),
    (4, False, '["algorithm"]', '3'),
    (4, False, '["datastructure"]', '4'),
    (4, False, '["openai"]', '4'),
    (5, True, '[1]', '1'),
    (5, True, '[3]', '6'),
    (5, False, '[2]', '2'),
    (5, False, '[4]', '24'),
    (5, False, '[5]', '120'),
    (5, False, '[6]', '720'),
    (5, False, '[7]', '5040'),
    (5, False, '[8]', '40320'),
    (5, False, '[9]', '362880'),
    (5, False, '[10]', '3628800'),
    (5, False, '[11]', '39916800'),
    (5, False, '[12]', '479001600'),
    (5, False, '[1]', '1'),
    (5, False, '[2]', '2'),
    (5, False, '[3]', '6'),
    (5, False, '[4]', '24'),
]


def ensure_schema():
    for statement in SCHEMA_SQL.split(";"):
        stmt = statement.strip()
        if stmt:
            execute(stmt)


def ensure_seed_data():
    tc_count = query_one("SELECT COUNT(*) AS c FROM test_cases")
    if tc_count and tc_count["c"] > 0:
        return

    problem_ids = {}
    for p in SEED_PROBLEMS:
        execute(
            """INSERT IGNORE INTO problems (contest_id, problem_index, title, slug, difficulty_rating, tags, description_html, url, base_code, method_name)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (p["contest_id"], p["problem_index"], p["title"], p["slug"],
             p["difficulty_rating"], p["tags"], p["description_html"], p["url"],
             p["base_code"], p["method_name"]),
        )

    for p in SEED_PROBLEMS:
        row = query_one(
            "SELECT id FROM problems WHERE contest_id = %s AND problem_index = %s",
            (p["contest_id"], p["problem_index"]),
        )
        if row:
            problem_ids[(p["contest_id"], p["problem_index"])] = row["id"]

    for problem_index, is_sample, args_json, expected_json in SEED_TEST_CASES:
        pid = problem_ids.get((1, chr(64 + problem_index)))
        if pid:
            execute(
                "INSERT INTO test_cases (problem_id, is_sample, args, expected) VALUES (%s, %s, %s, %s)",
                (pid, is_sample, args_json, expected_json),
            )


def run():
    ensure_schema()
    ensure_seed_data()
