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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS execution_queue (
    id INTEGER AUTO_INCREMENT PRIMARY KEY,
    submission_id INTEGER NOT NULL,
    status ENUM('queued','running','completed','failed') DEFAULT 'queued',
    result TEXT,
    error TEXT,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (submission_id) REFERENCES solutions(id) ON DELETE CASCADE
);

-- =====================
-- Seed data: 5 problems
-- =====================

INSERT INTO problems (contest_id, problem_index, title, slug, difficulty_rating, tags, description_html, url) VALUES
(1, 'A', 'A + B Problem', '1/A-a-plus-b', 800, '["math", "implementation"]',
 '<p>Given two integers <code>A</code> and <code>B</code>, print their sum.</p>',
 'https://codeforces.com/problemset/problem/1/A'),
(1, 'B', 'Max of Three', '1/B-max-of-three', 800, '["math", "implementation"]',
 '<p>Given three integers, print the maximum among them.</p>',
 'https://codeforces.com/problemset/problem/1/B'),
(1, 'C', 'Even or Odd', '1/C-even-or-odd', 800, '["math", "implementation"]',
 '<p>Given an integer <code>N</code>, print "Even" if it is even, or "Odd" if it is odd.</p>',
 'https://codeforces.com/problemset/problem/1/C'),
(1, 'D', 'Count Vowels', '1/D-count-vowels', 900, '["strings", "implementation"]',
 '<p>Given a string <code>S</code> consisting of lowercase English letters, count the number of vowels (<code>a, e, i, o, u</code>) in it.</p>',
 'https://codeforces.com/problemset/problem/1/D'),
(1, 'E', 'Factorial', '1/E-factorial', 900, '["math"]',
 '<p>Given an integer <code>N</code> (1 &le; N &le; 12), compute <code>N!</code> (N factorial).</p>',
 'https://codeforces.com/problemset/problem/1/E');

-- Problem 1: A + B — 16 test cases
INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES
(1, '2 3', '5', TRUE),
(1, '10 20', '30', TRUE),
(1, '0 0', '0', FALSE),
(1, '100 200', '300', FALSE),
(1, '-5 5', '0', FALSE),
(1, '-10 -20', '-30', FALSE),
(1, '1 999', '1000', FALSE),
(1, '500 500', '1000', FALSE),
(1, '7 8', '15', FALSE),
(1, '123 456', '579', FALSE),
(1, '999 1', '1000', FALSE),
(1, '0 100', '100', FALSE),
(1, '-100 100', '0', FALSE),
(1, '256 256', '512', FALSE),
(1, '1 0', '1', FALSE),
(1, '999 999', '1998', FALSE);

-- Problem 2: Max of Three — 16 test cases
INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES
(2, '1 2 3', '3', TRUE),
(2, '5 5 5', '5', TRUE),
(2, '10 5 3', '10', FALSE),
(2, '-1 -5 -3', '-1', FALSE),
(2, '0 0 1', '1', FALSE),
(2, '100 50 75', '100', FALSE),
(2, '4 8 2', '8', FALSE),
(2, '-10 -20 -30', '-10', FALSE),
(2, '7 7 3', '7', FALSE),
(2, '1 2 2', '2', FALSE),
(2, '999 1000 998', '1000', FALSE),
(2, '0 -1 -2', '0', FALSE),
(2, '123 122 121', '123', FALSE),
(2, '50 50 50', '50', FALSE),
(2, '3 1 4', '4', FALSE),
(2, '-5 0 5', '5', FALSE);

-- Problem 3: Even or Odd — 16 test cases
INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES
(3, '4', 'Even', TRUE),
(3, '7', 'Odd', TRUE),
(3, '0', 'Even', FALSE),
(3, '1', 'Odd', FALSE),
(3, '100', 'Even', FALSE),
(3, '999', 'Odd', FALSE),
(3, '-2', 'Even', FALSE),
(3, '-3', 'Odd', FALSE),
(3, '10', 'Even', FALSE),
(3, '11', 'Odd', FALSE),
(3, '256', 'Even', FALSE),
(3, '257', 'Odd', FALSE),
(3, '1024', 'Even', FALSE),
(3, '1025', 'Odd', FALSE),
(3, '5000', 'Even', FALSE),
(3, '5001', 'Odd', FALSE);

-- Problem 4: Count Vowels — 16 test cases
INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES
(4, 'hello', '2', TRUE),
(4, 'world', '1', TRUE),
(4, 'aeiou', '5', FALSE),
(4, 'bcdfg', '0', FALSE),
(4, 'abcdefghijklmnopqrstuvwxyz', '5', FALSE),
(4, 'programming', '3', FALSE),
(4, 'competition', '5', FALSE),
(4, 'python', '1', FALSE),
(4, '', '0', FALSE),
(4, 'a', '1', FALSE),
(4, 'z', '0', FALSE),
(4, 'beautiful', '5', FALSE),
(4, 'education', '5', FALSE),
(4, 'algorithm', '3', FALSE),
(4, 'datastructure', '4', FALSE),
(4, 'openai', '4', FALSE);

-- Problem 5: Factorial — 16 test cases
INSERT INTO test_cases (problem_id, input, expected_output, is_sample) VALUES
(5, '1', '1', TRUE),
(5, '3', '6', TRUE),
(5, '2', '2', FALSE),
(5, '4', '24', FALSE),
(5, '5', '120', FALSE),
(5, '6', '720', FALSE),
(5, '7', '5040', FALSE),
(5, '8', '40320', FALSE),
(5, '9', '362880', FALSE),
(5, '10', '3628800', FALSE),
(5, '11', '39916800', FALSE),
(5, '12', '479001600', FALSE),
(5, '1', '1', FALSE),
(5, '2', '2', FALSE),
(5, '3', '6', FALSE),
(5, '4', '24', FALSE);
