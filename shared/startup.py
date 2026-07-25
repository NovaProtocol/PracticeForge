from __future__ import annotations

from shared.db import execute

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
    description_html MEDIUMTEXT,
    time_limit VARCHAR(100),
    memory_limit VARCHAR(100),
    input_spec MEDIUMTEXT,
    output_spec MEDIUMTEXT,
    notes_html MEDIUMTEXT,
    problem_html MEDIUMTEXT,
    scrape_status VARCHAR(20),
    last_scraped_at TIMESTAMP NULL,
    url VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contest_id, problem_index)
);

CREATE TABLE IF NOT EXISTS test_cases (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    input TEXT,
    expected_output TEXT,
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

CREATE TABLE IF NOT EXISTS execution_queue (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    method_name VARCHAR(100),
    test_cases_json JSON,
    exec_type ENUM('run','submit') DEFAULT 'run',
    status ENUM('queued','running','completed','failed') DEFAULT 'queued',
    result LONGTEXT,
    stdout TEXT,
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
    last_ran TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (problem_id),
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
"""


def ensure_schema():
    for statement in SCHEMA_SQL.split(";"):
        stmt = statement.strip()
        if stmt:
            execute(stmt)


def run():
    ensure_schema()
