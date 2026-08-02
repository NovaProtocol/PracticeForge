import json
import time

import requests

from .config import API_BASE
from . import log

RETRIES = 3
BACKOFF = 2


def _retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < RETRIES - 1:
                log.warn(f"Retry {attempt+1}/{RETRIES} after: {e}")
                time.sleep(BACKOFF * (attempt + 1))
    log.error(f"All {RETRIES} retries failed: {last_err}")
    return None if kwargs.get("default") is None else kwargs["default"]


class Uploader:

    def exists_on_server(self, cid: int, idx: str) -> bool:
        try:
            r = requests.get(f"{API_BASE}/api/problems/exists/{cid}/{idx}", timeout=10)
            exists = r.json().get("exists", False)
            if exists:
                log.info(f"{cid}/{idx} already on server")
            return exists
        except Exception as e:
            log.error(f"Server check failed: {e}")
            return False

    def build_payload(self, cf_data: dict, ai_data: dict) -> dict:
        return {
            "contest_id": cf_data["contestId"],
            "problem_index": cf_data["index"],
            "title": ai_data.get("title", cf_data.get("name", "")),
            "difficulty_rating": cf_data.get("rating"),
            "tags": json.dumps(cf_data.get("tags", [])),
            "url": f"https://codeforces.com/problemset/problem/{cf_data['contestId']}/{cf_data['index']}",
            "base_code": ai_data.get("base_code", ""),
            "method_name": "run",
            "description_html": ai_data.get("description", ""),
            "time_limit": ai_data.get("time_limit", ""),
            "memory_limit": ai_data.get("memory_limit", ""),
            "input_spec": ai_data.get("input_specification", ""),
            "output_spec": ai_data.get("output_specification", ""),
            "examples_json": json.dumps(ai_data.get("examples", [])),
            "constraints_json": json.dumps(ai_data.get("constraints", [])),
            "solution_code": ai_data.get("solution_code", ""),
            "generator_code": ai_data.get("generator_code", ""),
            "executor_code": ai_data.get("executor_code", ""),
            "hints": json.dumps(ai_data.get("hints", [])),
        }

    def _do_upload(self, data: dict) -> int | None:
        r = requests.post(f"{API_BASE}/api/problems/upload", json=data, timeout=30)
        if r.status_code == 200:
            pid = r.json().get("id")
            log.info(f"Uploaded ✅ (id={pid})")
            return pid
        log.error(f"Upload failed ({r.status_code}): {r.text[:200]}")
        raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")

    def upload(self, data: dict) -> int | None:
        result = _retry(self._do_upload, data)
        return result

    def _do_verify(self, data: dict) -> bool:
        cid = data["contest_id"]
        idx = data["problem_index"]
        r = requests.get(f"{API_BASE}/api/problems/{cid}/{idx}", timeout=15)
        if r.status_code != 200:
            raise Exception(f"Verify HTTP {r.status_code}")
        stored = r.json()
        checks = [
            ("title", data["title"], stored.get("title")),
            ("difficulty_rating", data.get("difficulty_rating"), stored.get("difficulty_rating")),
            ("time_limit", data.get("time_limit"), stored.get("time_limit")),
            ("memory_limit", data.get("memory_limit"), stored.get("memory_limit")),
        ]
        for field, expected, got in checks:
            if expected != got:
                log.error(f"  Verify mismatch — {field}: expected={expected!r}, got={got!r}")
                return False
        log.info(f"  Verify OK — {cid}/{idx} data matches server")
        return True

    def verify_upload(self, data: dict) -> bool:
        result = _retry(self._do_verify, data)
        return result if result is not None else False
