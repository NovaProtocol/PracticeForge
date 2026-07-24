from __future__ import annotations

import os
import resource
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymysql
from pymysql.cursors import DictCursor

POLL_INTERVAL = 1
TIMEOUT_PER_CASE = 10
MAX_WORKERS = 4


def get_connection():
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ["MYSQL_PASS"],
        database=os.environ["MYSQL_DATABASE"],
        cursorclass=DictCursor,
        autocommit=True,
    )


def fetch_batch(conn, limit=4):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM execution_queue WHERE status = 'queued' ORDER BY id LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            fmt = ",".join(["%s"] * len(ids))
            cur.execute(
                f"UPDATE execution_queue SET status = 'running', started_at = NOW() WHERE id IN ({fmt})",
                ids,
            )
        return rows


def mark_done(conn, entry_id, status, result, error, timing_ms, memory_kb):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE execution_queue
               SET status = %s, result = %s, error = %s, timing_ms = %s, memory_kb = %s, completed_at = NOW()
               WHERE id = %s""",
            (status, result, error, timing_ms, memory_kb, entry_id),
        )


def run_code(code: str, stdin_data: str) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(code)
        tmp.close()
        start = time.perf_counter()
        r = subprocess.run(
            ["python3", tmp.name],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_PER_CASE,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            mem = usage.ru_maxrss
        except Exception:
            mem = 0

        if r.returncode != 0:
            return {"status": "failed", "result": r.stdout.strip(), "error": r.stderr.strip() or "Non-zero exit", "timing_ms": elapsed, "memory_kb": mem}
        return {"status": "completed", "result": r.stdout.strip(), "error": r.stderr.strip(), "timing_ms": elapsed, "memory_kb": mem}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "result": "", "error": "Time Limit Exceeded", "timing_ms": TIMEOUT_PER_CASE * 1000, "memory_kb": 0}
    except Exception as e:
        return {"status": "failed", "result": "", "error": str(e), "timing_ms": 0, "memory_kb": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def process_entry(entry: dict) -> dict:
    return run_code(entry["code"], entry.get("input") or "")


def main():
    print("[executor] Starting multi-threaded worker (max_workers=%d)..." % MAX_WORKERS)
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    while True:
        try:
            conn = get_connection()
            print("[executor] Connected to MySQL.")
            while True:
                try:
                    entries = fetch_batch(conn, MAX_WORKERS)
                    if entries:
                        futures = {pool.submit(process_entry, e): e for e in entries}
                        for future in as_completed(futures):
                            entry = futures[future]
                            try:
                                result = future.result()
                                eid = entry["id"]
                                expected = entry.get("input")  # will match via test_case
                                mark_done(
                                    conn, eid,
                                    result["status"],
                                    result["result"],
                                    result["error"],
                                    result["timing_ms"],
                                    result["memory_kb"],
                                )
                                print(f"[executor] Queue #{eid}: {result['status']} ({result['timing_ms']}ms)")
                            except Exception as e:
                                print(f"[executor] Queue #{entry['id']} error: {e}")
                                mark_done(conn, entry["id"], "failed", "", str(e), 0, 0)
                    else:
                        time.sleep(POLL_INTERVAL)
                except Exception as e:
                    print(f"[executor] Poll error: {e}")
                    time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[executor] DB connection failed: {e}, retrying in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()
