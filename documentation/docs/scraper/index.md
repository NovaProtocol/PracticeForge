# Scraper

Host-side 4-stage pipeline that scrapes Codeforces and uploads AI-enriched problems.

## Layout

```
utilities/scraper/
  run.py               # CLI entrypoint: python utilities/scraper/run.py <contestId>
  scrape.py            # stage 1: fetch HTML (browser for Cloudflare)
  extract.py           # parse problem blocks, examples, constraints, tags
  browser.py           # Playwright-like browser helper for CF challenge
  images_download.py   # download problem images to images/
  images_upload.py     # upload images via POST /api/images
  ai.py / ai_process.py# AI enrichment (generator/solution/executor/hints)
  api.py / uploader.py # HTTP client for POST /api/problems/upload
  config.py, log.py, tokens.py
```

## Stages

| Stage | Script | Input | Output |
|---|---|---|---|
| Scrape | `scrape.py` | Contest ID | `html/<cid><idx>.html` |
| Download images | `images_download.py` | HTML `img` src | `images/<file>` |
| Upload images | `images_upload.py` | `images/` | DB `problem_images` via `/api/images` |
| AI + upload | `ai.py` → `uploader.py` | HTML + images | `problems` rows via `/api/problems/upload` |

Stage 1 requires a browser profile for Cloudflare (`browser_profile/`).

## Trigger

```bash
python3 utilities/scraper/run.py 1234
python3 utilities/scraper/run.py 1234 --limit 5
```

`run.py` orchestrates the stages sequentially, honoring `LIMIT` env.

## Image Handling

Images are extracted from problem HTML, downloaded, then uploaded as base64 via `POST /api/images` with strict `content_type` allowlist; served later via `GET /api/images/<filename>`.
