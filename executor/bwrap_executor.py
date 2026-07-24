from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

import pymysql
from pymysql.cursors import DictCursor

POLL_INTERVAL = 1
TIMEOUT = 30
BWRAP = "/usr/bin/bwrap"


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


def mark_completed(conn, queue_id, result, error, timing_ms, memory_kb):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE execution_queue
               SET status = 'completed', result = %s, error = %s,
                   timing_ms = %s, memory_kb = %s, completed_at = NOW()
               WHERE id = %s""",
            (result, error, timing_ms, memory_kb, queue_id),
        )


def mark_failed(conn, queue_id, error):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE execution_queue SET status = 'failed', error = %s, completed_at = NOW() WHERE id = %s",
            (error, queue_id),
        )


def get_test_cases(conn, problem_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, args, expected, input, expected_output FROM test_cases WHERE problem_id = %s ORDER BY id",
            (problem_id,),
        )
        return cur.fetchall()


def get_problem_method(conn, problem_id):
    with conn.cursor() as cur:
        cur.execute("SELECT method_name FROM problems WHERE id = %s", (problem_id,))
        row = cur.fetchone()
        return row["method_name"] if row and row.get("method_name") else "run"


def build_wrapper(user_code: str, method_name: str, test_cases: list[dict]) -> str:
    parts = [
        "import json",
        "from typing import List, Optional, Dict, Tuple, Set",
        user_code,
        "solution = Solution()",
        "method = getattr(solution, " + json.dumps(method_name) + ")",
        "results = []",
    ]
    for tc in test_cases:
        args_str = tc.get("args") or tc.get("input") or ""
        expected_str = tc.get("expected") or tc.get("expected_output") or ""
        if not args_str:
            args_str = "[]"
        if not expected_str:
            expected_str = '""'
        parts.append("try:")
        parts.append("    args = json.loads(" + json.dumps(args_str) + ")")
        parts.append("    expected = json.loads(" + json.dumps(expected_str) + ")")
        parts.append("    result = method(*args)")
        parts.append("    got = json.dumps(result)")
        parts.append("    passed = got == " + json.dumps(expected_str))
        parts.append("except Exception as ex:")
        parts.append("    got = json.dumps(str(ex))")
        parts.append("    passed = False")
        parts.append("results.append({'passed': passed, 'got': got, 'error': repr(ex) if not passed else ''})")
    parts.append("print(json.dumps(results))")
    return "\n".join(parts)


def run_code(wrapper_code: str, timeout: int = TIMEOUT) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper_code)
        tmp.close()
        os.chmod(tmp.name, 0o644)

        python_path = "/usr/local/bin/python3"
        start = time.perf_counter()

        cmd = [python_path, tmp.name]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except OSError:
            r = subprocess.run(["python3", tmp.name], capture_output=True, text=True, timeout=timeout)

        elapsed = int((time.perf_counter() - start) * 1000)
        return {
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "timing_ms": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Time Limit Exceeded", "timing_ms": timeout * 1000}
    except Exception as e:
        return {"returncode": -2, "stdout": "", "stderr": str(e), "timing_ms": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def run_bwrap(wrapper_code: str, timeout: int = TIMEOUT) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper_code)
        tmp.close()
        os.chmod(tmp.name, 0o644)

        cmd = [BWRAP, "--unshare-user", "--unshare-net", "--unshare-ipc", "--unshare-pid",
               "--die-with-parent", "--ro-bind", "/usr", "/usr",
               "--ro-bind", "/usr/local", "/usr/local",
               "--ro-bind", "/lib", "/lib",
               "--ro-bind", "/lib64", "/lib64",
               "--dev", "/dev",
               "--ro-bind", tmp.name, tmp.name,
               "--chdir", "/", "/usr/local/bin/python3", tmp.name]

        start = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = int((time.perf_counter() - start) * 1000)

        if r.returncode != 0:
            err = r.stderr.lower()
            if "operation not permitted" in err or "namespace" in err or "cannot" in err:
                return run_code(wrapper_code, timeout)

        return {
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "timing_ms": elapsed,
        }
    except OSError:
        return run_code(wrapper_code, timeout)
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Time Limit Exceeded", "timing_ms": timeout * 1000}
    except Exception as e:
        return {"returncode": -2, "stdout": "", "stderr": str(e), "timing_ms": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def create_solution(conn, problem_id, code, verdict, passed, total, timing_ms, memory_kb):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count, timing_ms, memory_kb)
               VALUES (%s, %s, 'python', %s, %s, %s, %s, %s)""",
            (problem_id, code, verdict, passed, total, timing_ms, memory_kb),
        )
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        return cur.fetchone()["id"]


def process_entry(conn, entry):
    qid = entry["id"]
    problem_id = entry["problem_id"]
    code = entry["code"]
    method_name = entry.get("method_name") or "run"
    exec_type = entry.get("exec_type") or "run"

    mark_running(conn, qid)

    test_cases = None
    raw = entry.get("test_cases_json")
    if raw:
        try:
            test_cases = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    if not test_cases:
        test_cases = get_test_cases(conn, problem_id)
    if not test_cases:
        mark_failed(conn, qid, "No test cases found")
        return

    wrapper = build_wrapper(code, method_name, test_cases)
    result = run_bwrap(wrapper)

    if result["returncode"] != 0:
        mark_failed(conn, qid, result["stderr"] or result["stdout"])
        return

    try:
        tc_results = json.loads(result["stdout"])
    except json.JSONDecodeError as e:
        mark_failed(conn, qid, f"Failed to parse output: {e}\nRaw: {result['stdout']}")
        return

    passed = sum(1 for t in tc_results if t.get("passed"))
    total = len(tc_results)
    timing_ms = result["timing_ms"]
    memory_kb = 0  # bwrap doesn't easily report memory

    result_lines = []
    for i, t in enumerate(tc_results):
        status = "PASS" if t.get("passed") else "FAIL"
        got = t.get("got", "")
        err = t.get("error", "")
        result_lines.append(f"TC #{i+1}: {status}")
        if not t.get("passed"):
            result_lines.append(f"  Got: {got}")
            if err:
                result_lines.append(f"  Error: {err}")
    result_text = "\n".join(result_lines)

    verdict = "Accepted" if passed == total else "Wrong Answer"
    mark_completed(conn, qid, result_text, "", timing_ms, memory_kb)

    if exec_type == "submit":
        sid = create_solution(conn, problem_id, code, verdict, passed, total, timing_ms, memory_kb)
        with conn.cursor() as cur:
            cur.execute("UPDATE execution_queue SET solution_id = %s WHERE id = %s", (sid, qid))


def main():
    print("[bwrap-executor] Starting...")
    while True:
        try:
            conn = get_connection()
            print("[bwrap-executor] Connected to MySQL.")
            while True:
                try:
                    entry = fetch_queued(conn)
                    if entry:
                        print(f"[bwrap-executor] Processing queue #{entry['id']}...")
                        process_entry(conn, entry)
                        print(f"[bwrap-executor] Queue #{entry['id']} done.")
                    else:
                        time.sleep(POLL_INTERVAL)
                except Exception as e:
                    print(f"[bwrap-executor] Poll error: {e}")
                    time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[bwrap-executor] DB connection failed: {e}, retrying in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()
