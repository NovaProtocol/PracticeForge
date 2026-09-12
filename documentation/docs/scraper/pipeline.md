# Pipeline Stages

## Stage 1 — Scrape (`scrape.py`)

- Fetches `https://codeforces.com/contest/<id>/problem/<idx>` or problemset page.
- Uses `browser.py` to pass Cloudflare challenge; saves raw HTML to `html/`.
- Honors `LIMIT` and `TEST_TARGET` env for dev.

## Stage 2 — Extract (`extract.py`)

- Parses title, description_html, input_spec, output_spec, examples, constraints, tags, difficulty, time/memory limits via BeautifulSoup.
- Normalizes `examples_json` to `[{"input":…, "output":…, "hidden":…}]`.

## Stage 3 — Images

- `images_download.py`: resolves relative `src`, downloads to `images/`.
- `images_upload.py`: base64-encodes, `POST /api/images` with `content_type` check (`image/png`, `image/jpeg`, …). Rewrites HTML `src` to `/api/images/<filename>`.

## Stage 4 — AI Enrichment (`ai.py` + `ai_process.py`)

- Calls LLM (via `ZEN_API_KEY`) to generate:
 - `base_code` — `class Solution` skeleton with `method_name` (default `run`)
 - `solution_code` — reference solution
 - `generator_code` — `def generate(): return [cases]` for brute-force
 - `executor_code` — interactive judge helpers (defines `HIDDEN` checks)
 - `hints`, `tags` refinement
- Validates generated code by executing `shared/wrapper.py` locally via `build_wrapper()` — same wrapper the executor uses, so validation and production runs are identical.
- Token usage tracked in `token_usage.json`.

## Upload (`uploader.py` + `api.py`)

- `upsert_problem(data)` → `POST /api/problems/upload` → `problems` table.
- `image_exists` check via `GET /api/images/exists/<file>` avoids re-upload.
- Auth via `API_TOKEN` header if set.

## Running Locally

```bash
export ZEN_API_KEY=sk-...
export API_TOKEN=...
python utilities/scraper/run.py 1900
# inspect
ls utilities/scraper/html/
cat utilities/scraper/token_usage.json
```
