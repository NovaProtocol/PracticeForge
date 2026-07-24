from __future__ import annotations

import os
import subprocess
import tempfile
import time
import traceback

import pymysql
from pymysql.cursors import DictCursor

POLL_INTERVAL = 2
TIMEOUT_PER_CASE = 10


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


def fetch_queued(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM execution_queue WHERE status = 'queued' ORDER BY id LIMIT 1"
        )
        return cur.fetchone()


def mark_running(conn, queue_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE execution_queue SET status = 'running', started_at = NOW() WHERE id = %s",
            (queue_id,),
        )


def mark_completed(conn, queue_id, result, error=None):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE execution_queue SET status = 'completed', result = %s, error = %s, completed_at = NOW() WHERE id = %s",
            (result, error, queue_id),
        )


def mark_failed(conn, queue_id, error):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE execution_queue SET status = 'failed', error = %s, completed_at = NOW() WHERE id = %s",
            (error, queue_id),
        )


def update_solution_verdict(conn, solution_id, verdict, passed, total):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE solutions SET verdict = %s, passed_count = %s, total_count = %s WHERE id = %s",
            (verdict, passed, total, solution_id),
        )


def run_test_case(code: str, stdin_data: str) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_PER_CASE,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return {"status": "error", "stdout": stdout, "stderr": stderr or "Non-zero exit code"}

        return {"status": "ok", "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "stdout": "", "stderr": "Time Limit Exceeded"}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def execute_submission(conn, queue_entry):
    queue_id = queue_entry["id"]
    submission_id = queue_entry["submission_id"]

    mark_running(conn, queue_id)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM solutions WHERE id = %s", (submission_id,))
            solution = cur.fetchone()

            cur.execute("SELECT * FROM test_cases WHERE problem_id = %s ORDER BY id", (solution["problem_id"],))
            test_cases = cur.fetchall()

        if not solution or not test_cases:
            mark_failed(conn, queue_id, "Solution or test cases not found")
            return

        code = solution["code"]
        passed = 0
        total = len(test_cases)
        first_failure = None

        for tc in test_cases:
            result = run_test_case(code, tc["input"])
            if result["status"] == "ok" and result["stdout"] == tc["expected_output"].strip():
                passed += 1
            else:
                if first_failure is None:
                    if result["status"] == "timeout":
                        first_failure = {
                            "input": tc["input"],
                            "expected": tc["expected_output"],
                            "got": "Time Limit Exceeded",
                            "error": result["stderr"],
                        }
                    elif result["status"] == "error":
                        first_failure = {
                            "input": tc["input"],
                            "expected": tc["expected_output"],
                            "got": result["stdout"],
                            "error": result["stderr"],
                        }
                    else:
                        first_failure = {
                            "input": tc["input"],
                            "expected": tc["expected_output"],
                            "got": result["stdout"],
                            "error": result["stderr"],
                        }

        if passed == total:
            verdict = "Accepted"
        elif first_failure and first_failure["error"] and "Time Limit" in first_failure["error"]:
            verdict = "Timeout"
        elif first_failure and first_failure["error"]:
            verdict = "Error"
        else:
            verdict = "Wrong Answer"

        update_solution_verdict(conn, submission_id, verdict, passed, total)

        result_text = (
            f"Passed {passed}/{total}\n"
        )
        if first_failure:
            result_text += (
                f"\nFirst failure:\n"
                f"Input: {first_failure['input']}\n"
                f"Expected: {first_failure['expected']}\n"
                f"Got: {first_failure['got']}\n"
            )
            if first_failure["error"]:
                result_text += f"Error: {first_failure['error']}\n"

        mark_completed(conn, queue_id, result_text)

    except Exception as e:
        tb = traceback.format_exc()
        mark_failed(conn, queue_id, f"{e}\n{tb}")
        update_solution_verdict(conn, submission_id, "Error", 0, 0)


def main():
    print("[executor] Starting queue worker...")
    while True:
        try:
            conn = get_connection()
            print("[executor] Connected to MySQL.")
            while True:
                try:
                    entry = fetch_queued(conn)
                    if entry:
                        print(f"[executor] Processing queue #{entry['id']} (submission #{entry['submission_id']})...")
                        execute_submission(conn, entry)
                        print(f"[executor] Queue #{entry['id']} done.")
                    else:
                        time.sleep(POLL_INTERVAL)
                except Exception as e:
                    print(f"[executor] Error in poll loop: {e}")
                    time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[executor] DB connection failed: {e}, retrying in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()
