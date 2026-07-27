from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
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


def mark_completed(conn, queue_id, result, stdout, error, timing_ms, memory_kb):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE execution_queue
               SET status = 'completed', result = %s, stdout = %s, error = %s,
                   timing_ms = %s, memory_kb = %s, completed_at = NOW()
               WHERE id = %s""",
            (result, stdout, error, timing_ms, memory_kb, queue_id),
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
    lines = [
        "import json, sys, io, time",
        "from typing import List, Optional, Dict, Tuple, Set",
        user_code,
        "solution = Solution()",
        "method = getattr(solution, " + json.dumps(method_name) + ")",
        "results = []",
    ]
    for tc in test_cases:
        args_str = tc.get("args") or tc.get("input") or ""
        expected_str = tc.get("expected") or tc.get("expected_output") or ""
        inp_display = tc.get("args") or tc.get("input") or ""
        exp_display = tc.get("expected") or tc.get("expected_output") or ""

        if not args_str:
            lines.append("results.append({'input': " + json.dumps(inp_display) + ", 'expected': " + json.dumps(exp_display) + ", 'got': '', 'error': '', 'passed': True, 'stdout': '', 'status': 'skipped'})")
            continue

        lines.append("_cap = io.StringIO()")
        lines.append("_old_stdout = sys.stdout")
        lines.append("sys.stdout = _cap")
        lines.append("_r_input = " + json.dumps(inp_display))
        lines.append("_r_expected = " + json.dumps(exp_display))
        lines.append("err = ''")
        lines.append("_t0 = time.perf_counter()")
        lines.append("try:")
        lines.append("    args = json.loads(" + json.dumps(args_str) + ")")
        lines.append("    result = method(*args)")
        lines.append("    got = json.dumps(result)")
        if expected_str:
            lines.append("    expected = json.loads(" + json.dumps(json.dumps(expected_str)) + ")")
            lines.append("    passed = got == " + json.dumps(json.dumps(expected_str)))
            lines.append("    status = 'passed' if passed else 'failed'")
        else:
            lines.append("    status = 'checked'")
            lines.append("    passed = True")
        lines.append("except Exception as _ex:")
        lines.append("    got = json.dumps(str(_ex))")
        lines.append("    err = repr(_ex)")
        lines.append("    passed = False")
        lines.append("    status = 'failed'")
        lines.append("_tc_stdout = _cap.getvalue()")
        lines.append("sys.stdout = _old_stdout")
        lines.append("_timing = int((time.perf_counter() - _t0) * 1000)")
        lines.append("results.append({'input': _r_input, 'expected': _r_expected, 'got': got, 'error': err, 'passed': passed, 'stdout': _tc_stdout, 'status': status, 'timing_ms': _timing})")
    lines.append("print('__SOLVER_RESULT__')")
    lines.append("print(json.dumps(results))")
    return "\n".join(lines)


def _parse_output(stdout: str) -> dict:
    result = {"results_json": "[]", "user_stdout": "", "raw_stdout": stdout}
    marker = "__SOLVER_RESULT__"
    if marker in stdout:
        parts = stdout.split(marker + "\n", 1)
        if len(parts) > 1:
            result["results_json"] = parts[1].strip()
    return result


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
        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem = 0
        parsed = _parse_output(r.stdout)
        return {
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "results_json": parsed["results_json"],
            "timing_ms": elapsed,
            "memory_kb": mem,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Time Limit Exceeded", "timing_ms": timeout * 1000, "results_json": "[]", "memory_kb": 0}
    except Exception as e:
        return {"returncode": -2, "stdout": "", "stderr": str(e), "timing_ms": 0, "results_json": "[]", "memory_kb": 0}
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

        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem = 0

        if r.returncode != 0:
            err = r.stderr.lower()
            if "operation not permitted" in err or "namespace" in err or "cannot" in err:
                return run_code(wrapper_code, timeout)

        parsed = _parse_output(r.stdout)
        return {
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "results_json": parsed["results_json"],
            "timing_ms": elapsed,
            "memory_kb": mem,
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
        tc_results = json.loads(result["results_json"])
    except json.JSONDecodeError as e:
        mark_failed(conn, qid, f"Failed to parse output: {e}\nRaw: {result['stdout']}")
        return

    passed = sum(1 for t in tc_results if t.get("passed"))
    total = len(tc_results)
    timing_ms = result["timing_ms"]
    memory_kb = result.get("memory_kb", 0) or 0

    all_stdout = "\n".join(t.get("stdout", "") for t in tc_results if t.get("stdout"))

    result_data = json.dumps({
        "results": tc_results,
        "stdout": all_stdout,
    })

    verdict = "Accepted" if passed == total else "Wrong Answer"
    mark_completed(conn, qid, result_data, all_stdout, "", timing_ms, memory_kb)

    if exec_type == "submit":
        sid = create_solution(conn, problem_id, code, verdict, passed, total, timing_ms, memory_kb)
        with conn.cursor() as cur:
            cur.execute("UPDATE execution_queue SET solution_id = %s WHERE id = %s", (sid, qid))


def main():
    print("[bwrap-executor] Starting...", flush=True)
    while True:
        try:
            conn = get_connection()
            print("[bwrap-executor] Connected to MySQL.", flush=True)
            while True:
                try:
                    entry = fetch_queued(conn)
                    if entry:
                        print(f"[bwrap-executor] Processing queue #{entry['id']}...", flush=True)
                        try:
                            process_entry(conn, entry)
                        except Exception as e:
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                            print(f"[bwrap-executor] FATAL: queue #{entry['id']} crashed: {e}", file=sys.stderr, flush=True)
                            try:
                                mark_failed(conn, entry["id"], f"Executor error: {e}")
                            except Exception:
                                pass
                        print(f"[bwrap-executor] Queue #{entry['id']} done.", flush=True)
                    else:
                        time.sleep(POLL_INTERVAL)
                except Exception as e:
                    print(f"[bwrap-executor] Poll error: {e}", flush=True)
                    time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[bwrap-executor] DB connection failed: {e}, retrying in 5s...", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
