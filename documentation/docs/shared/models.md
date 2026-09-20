# Models & DB

## Engine

`shared/db.py`: `create_engine(mysql+pymysql://user:pass@host:port/db, pool_pre_ping=True, pool_recycle=300)`.

## Tables

### problems

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | autoinc |
| `contest_id` | Integer | + `problem_index` unique |
| `problem_index` | String(3) | `A`, `B1`, … |
| `title`, `slug` | String(255) | `slug` unique |
| `difficulty_rating` | Integer | |
| `tags` | JSON | |
| `base_code`, `method_name` | Text, String(100) | default `run` |
| `description_html`, `input_spec`, `output_spec` | Text(LONG) | |
| `time_limit`, `memory_limit` | String(100) | |
| `examples_json`, `constraints_json`, `hints` | JSON | |
| `solution_code`, `generator_code`, `executor_code` | Text | AI-enriched |
| `url` | String(255) | |
| `created_at` | DateTime | `CURRENT_TIMESTAMP` |

### solutions

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `problem_id` | FK `problems.id` | `CASCADE` |
| `code` | Text | |
| `language` | String(50) | default `python` |
| `verdict` | String(50) | `Accepted` / `Wrong Answer` |
| `passed_count`, `total_count`, `timing_ms`, `memory_kb` | Integer | |
| `created_at`, `updated_at` | DateTime | |

### execution_queue

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `problem_id` | FK | |
| `code` | Text | |
| `method_name` | String(100) | |
| `test_cases_json` | JSON | |
| `exec_type` | Enum `run/submit/brute_force/submit_brute` | |
| `status` | Enum `queued/running/completed/failed` | |
| `result` | LONGTEXT | JSON `{"results":…}` |
| `stdout` | LONGTEXT | |
| `error` | Text | |
| `timing_ms`, `memory_kb`, `solution_id` | Integer | |
| `started_at`, `completed_at`, `created_at` | DateTime | |

### auto_saves

`(problem_id, filename)` composite PK, `code` Text, `last_ran` Text, `active` Bool.

### problem_images

`filename` unique, `data` LONGBLOB, `content_type` String(50).

## MySQL Notes

- `mysql:8.4`, `TEXT` columns must not have `server_default` (MySQL 8.4 rejects `TEXT DEFAULT`); use Python-side `default=` instead.
- Adaptive migrations wrap `ALTER` with `SET FOREIGN_KEY_CHECKS=0/1`.
- Volume `mysql_data:/var/lib/mysql` persists data; healthcheck `mysqladmin ping` `5s/5s/10`.
