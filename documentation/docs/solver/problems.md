# Problems & Solutions

## Problems Table

`shared/sqlalchemy_models.py:Problem`

- Identity: `contest_id` + `problem_index` (unique), `slug` unique
- Content: `title`, `description_html`, `input_spec`, `output_spec`, `time_limit`, `memory_limit`
- Code: `base_code`, `method_name` (default `run`), `solution_code`, `generator_code`, `executor_code`
- Data: `tags` (JSON), `difficulty_rating`, `examples_json` (JSON), `constraints_json` (JSON), `hints` (JSON), `url`

## Solutions Table

`Solution`: `problem_id` FK, `code`, `language` (default `python`), `verdict` (`Accepted`/`Wrong Answer`), `passed_count`/`total_count`, `timing_ms`, `memory_kb`.

## AutoSave

`AutoSave`: `(problem_id, filename)` PK, `code`, `last_ran`, `active` bool. The editor autosaves per-file via `POST /api/files/...` and beacon `POST /api/save/...`.

## ProblemImages

`ProblemImage`: `filename` unique, `data` LONGBLOB, `content_type`.

## ExecutionQueue

`ExecutionQueue`: `problem_id` FK, `code`, `method_name`, `test_cases_json` (JSON), `exec_type` (`run`/`submit`/`brute_force`/`submit_brute`), `status` (`queued`/`running`/`completed`/`failed`), `result` LONGTEXT (JSON `{"results":…, "stdout":…}`), `stdout` LONGTEXT, `error` Text, `timing_ms`, `memory_kb`, `solution_id`, timestamps.

## Console & Editor

- Editor tab: per-file CodeMirror-style editor, `POST /api/files/...` autosave, `POST /api/format` via Black.
- Console tab: run examples or brute-force, poll `GET /api/queue-status/<id>`, render `results[].got/expected/status/timing_ms`.

## Detail Page Partials

`apps/problems/templates/problems/partials/`:

- `_description.html` — rendered `description_html` + images via `/api/images/<file>`
- `_editor.html` — file tabs + editor
- `_console_scripts.html` — queue poll + result render
