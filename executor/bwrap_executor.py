from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
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




def get_problem_method(conn, problem_id):
    with conn.cursor() as cur:
        cur.execute("SELECT method_name FROM problems WHERE id = %s", (problem_id,))
        row = cur.fetchone()
        return row["method_name"] if row and row.get("method_name") else "run"


def get_problem_label(conn, problem_id):
    with conn.cursor() as cur:
        cur.execute("SELECT contest_id, problem_index FROM problems WHERE id = %s", (problem_id,))
        row = cur.fetchone()
        if row:
            return f"{row['contest_id']}{row['problem_index']}"
        return str(problem_id)


def build_wrapper(user_code_path: str, method_name: str, test_cases: list[dict], stop_on_failure: bool = False) -> str:
    lines = [
        "import json, sys, io, time, traceback, signal",
        "from typing import List, Optional, Dict, Tuple, Set",
        f"exec(compile(open({json.dumps(user_code_path)}).read(), {json.dumps(user_code_path)}, 'exec'))",
        "solution = Solution()",
        "method = getattr(solution, " + json.dumps(method_name) + ")",
        "results = []",
        "_abort = False",
        "class _TimeoutError(Exception): pass",
        "def _timeout_handler(signum, frame): raise _TimeoutError",
        "signal.signal(signal.SIGALRM, _timeout_handler)",
    ]
    for tc in test_cases:
        kwargs_str = tc.get("kwargs") or tc.get("input") or ""
        expected_str = tc.get("expected") or tc.get("expected_output") or ""
        inp_display = tc.get("kwargs") or tc.get("input") or ""
        exp_display = tc.get("expected") or tc.get("expected_output") or ""

        if not kwargs_str:
            lines.append("results.append({'input': " + json.dumps(inp_display) + ", 'expected': " + json.dumps(exp_display) + ", 'got': '', 'error': '', 'passed': True, 'stdout': '', 'status': 'skipped'})")
            continue

        lines.append("if not _abort:")
        lines.append("  signal.alarm(10)")
        lines.append("  _cap = io.StringIO()")
        lines.append("  _old_stdout = sys.stdout")
        lines.append("  sys.stdout = _cap")
        lines.append("  _r_input = " + json.dumps(inp_display))
        lines.append("  _r_expected = " + json.dumps(exp_display))
        lines.append("  err = ''")
        lines.append("  _t0 = time.perf_counter()")
        lines.append("  try:")
        lines.append("    kwargs = json.loads(" + json.dumps(kwargs_str) + ")")
        lines.append("    result = method(**kwargs)")
        lines.append("    got = json.dumps(result)")
        if expected_str:
            lines.append("    expected = json.loads(" + json.dumps(json.dumps(expected_str)) + ")")
            lines.append("    passed = got == " + json.dumps(json.dumps(expected_str)))
            lines.append("    status = 'passed' if passed else 'failed'")
        else:
            lines.append("    status = 'checked'")
            lines.append("    passed = True")
        lines.append("  except _TimeoutError:")
        lines.append("    got = json.dumps('TIMEOUT')")
        lines.append("    err = 'Test case exceeded 10s limit'")
        lines.append("    passed = False")
        lines.append("    status = 'failed'")
        lines.append("  except Exception as _ex:")
        lines.append("    got = json.dumps(str(_ex))")
        lines.append("    err = traceback.format_exc()")
        lines.append("    passed = False")
        lines.append("    status = 'failed'")
        lines.append("  finally:")
        lines.append("    signal.alarm(0)")
        lines.append("  _tc_stdout = _cap.getvalue()")
        lines.append("  sys.stdout = _old_stdout")
        lines.append("  _timing = round((time.perf_counter() - _t0) * 1000, 3)")
        lines.append("  results.append({'input': _r_input, 'expected': _r_expected, 'got': got, 'error': err, 'passed': passed, 'stdout': _tc_stdout, 'status': status, 'timing_ms': _timing})")
        if stop_on_failure:
            lines.append("  if not passed: _abort = True")
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


def run_code(wrapper_code: str, wrapper_path: str, user_code_path: str | None = None, timeout: int = TIMEOUT) -> dict:
    try:
        with open(wrapper_path, "w") as f:
            f.write(wrapper_code)
        os.chmod(wrapper_path, 0o644)

        python_path = "/usr/local/bin/python3"
        start = time.perf_counter()

        cmd = [python_path, wrapper_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except OSError:
            r = subprocess.run(["python3", wrapper_path], capture_output=True, text=True, timeout=timeout)

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
        for p in [wrapper_path, user_code_path]:
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


def run_bwrap(wrapper_code: str, wrapper_path: str, user_code_path: str | None = None, timeout: int = TIMEOUT) -> dict:
    try:
        with open(wrapper_path, "w") as f:
            f.write(wrapper_code)
        os.chmod(wrapper_path, 0o644)

        bwrap_args = [BWRAP, "--unshare-user", "--unshare-net", "--unshare-ipc", "--unshare-pid",
               "--die-with-parent", "--ro-bind", "/usr", "/usr",
               "--ro-bind", "/usr/local", "/usr/local",
               "--ro-bind", "/lib", "/lib",
               "--ro-bind", "/lib64", "/lib64",
               "--dev", "/dev",
               "--ro-bind", wrapper_path, wrapper_path]
        if user_code_path:
            bwrap_args.extend(["--ro-bind", user_code_path, user_code_path])
        bwrap_args.extend(["--chdir", "/", "/usr/local/bin/python3", wrapper_path])

        cmd = bwrap_args

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
                return run_code(wrapper_code, wrapper_path, user_code_path, timeout)

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
        return run_code(wrapper_code, wrapper_path, user_code_path, timeout)
    except subprocess.TimeoutExpired as te:
        partial = ""
        if te.output:
            partial = te.output.decode() if isinstance(te.output, bytes) else te.output
        msg = "Time Limit Exceeded"
        if partial:
            idx = partial.find("case ")
            if idx >= 0:
                msg += f" (during test {partial[idx:idx+20].strip()})"
        return {"returncode": -1, "stdout": "", "stderr": msg, "timing_ms": timeout * 1000}
    except Exception as e:
        return {"returncode": -2, "stdout": "", "stderr": str(e), "timing_ms": 0}
    finally:
        for p in [wrapper_path, user_code_path]:
            if p:
                try:
                    os.unlink(p)
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


def generate_brute_force_test_cases(conn, problem_id, qid, max_valid=100, max_attempts=1000):
    """Generate test cases using generator_code, validate with solution_code. Returns (list | None, error_msg)."""
    with conn.cursor() as cur:
        cur.execute("SELECT generator_code, solution_code, method_name FROM problems WHERE id = %s", (problem_id,))
        row = cur.fetchone()
    if not row:
        return None, f"Problem #{problem_id} not found in database"
    generator_code = row.get("generator_code") or ""
    solution_code = row.get("solution_code") or ""
    method_name = row.get("method_name") or "run"
    if not generator_code:
        return None, "Problem has no generator_code"
    if not solution_code:
        return None, "Problem has no solution_code"

    gen_path = f"/tmp/gen-{get_problem_label(conn, problem_id)}-{qid}.py"
    gen_wrapper = generator_code + "\n\nimport json\ntry:\n    result = generate()\n    print(json.dumps(result))\nexcept Exception as e:\n    print(json.dumps({'error': str(e)}))\n"
    try:
        with open(gen_path, "w") as f:
            f.write(gen_wrapper)
    except OSError:
        return None, "Failed to write generator file"

    valid = []
    try:
        proc = subprocess.Popen([sys.executable, gen_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        stdout, _ = proc.communicate(timeout=30)
        all_cases = json.loads(stdout.strip().split("\n")[0] or "[]")
    except (json.JSONDecodeError, ValueError, subprocess.TimeoutExpired):
        all_cases = []
    finally:
        try:
            os.unlink(gen_path)
        except OSError:
            pass

    if not isinstance(all_cases, list) or len(all_cases) == 0:
        return None, "Generator produced no valid test cases"

    for tc_data in all_cases:
        if len(valid) >= max_valid:
            break
        if not isinstance(tc_data, dict):
            continue

        kwargs_str = json.dumps(tc_data)

        sol_path = f"/tmp/sol-{get_problem_label(conn, problem_id)}-{qid}-{len(valid)}.py"
        try:
            with open(sol_path, "w") as f:
                f.write(solution_code)
        except OSError:
            continue

        sol_wrapper = build_wrapper(sol_path, method_name, [{"kwargs": kwargs_str, "expected": ""}])
        sol_wrap_path = f"/tmp/solwrap-{get_problem_label(conn, problem_id)}-{qid}-{len(valid)}.py"
        sol_result = run_code(sol_wrapper, sol_wrap_path, sol_path, timeout=15)

        try:
            os.unlink(sol_path)
        except OSError:
            pass
        try:
            os.unlink(sol_wrap_path)
        except OSError:
            pass

        if sol_result["returncode"] != 0:
            continue
        try:
            tc_results = json.loads(sol_result["results_json"])
        except (json.JSONDecodeError, ValueError):
            continue
        if not tc_results or tc_results[0].get("status") == "failed":
            continue

        got = tc_results[0].get("got", "")
        try:
            expected_raw = json.loads(got)
        except (json.JSONDecodeError, ValueError):
            expected_raw = got
        valid.append({"kwargs": kwargs_str, "expected": expected_raw, "input": "", "expected_output": ""})

    if not valid:
        return None, f"All {len(all_cases)} generated cases failed validation"
    return valid, ""


def process_entry(conn, entry):
    qid = entry["id"]
    problem_id = entry["problem_id"]
    code = entry["code"]
    method_name = entry.get("method_name") or "run"
    exec_type = entry.get("exec_type") or "run"

    mark_running(conn, qid)

    test_cases = None
    raw = entry.get("test_cases_json")
    if raw is not None:
        if isinstance(raw, (list, dict)):
            test_cases = raw if isinstance(raw, list) else [raw]
        elif isinstance(raw, str):
            try:
                test_cases = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
    if exec_type in ("brute_force", "submit_brute"):
        gen_cases, gen_err = generate_brute_force_test_cases(conn, problem_id, qid)
        if gen_cases is None:
            mark_failed(conn, qid, f"Failed to generate test cases: {gen_err}")
            return
        test_cases = gen_cases

    if not test_cases:
        mark_failed(conn, qid, "No test cases found")
        return

    user_code_path = f"/tmp/solver-{get_problem_label(conn, problem_id)}-{qid}.py"
    try:
        with open(user_code_path, "w") as f:
            f.write(code)
    except OSError as e:
        mark_failed(conn, qid, f"Failed to write user code: {e}")
        return

    wrapper_path = f"/tmp/wrapper-{get_problem_label(conn, problem_id)}-{qid}.py"
    stop_on_failure = exec_type in ("brute_force", "submit_brute")
    wrapper = build_wrapper(user_code_path, method_name, test_cases, stop_on_failure)
    result = run_bwrap(wrapper, wrapper_path, user_code_path)

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

    # Run solution code against same test cases for timing comparison
    with conn.cursor() as cur:
        cur.execute("SELECT solution_code FROM problems WHERE id = %s", (problem_id,))
        sol_row = cur.fetchone()
    if sol_row and sol_row.get("solution_code"):
        sol_code = sol_row["solution_code"]
        sol_path = f"/tmp/solcompare-{get_problem_label(conn, problem_id)}-{qid}.py"
        sol_wrap_path = f"/tmp/solcomparewrap-{get_problem_label(conn, problem_id)}-{qid}.py"
        try:
            with open(sol_path, "w") as f:
                f.write(sol_code)
            sol_wrapper = build_wrapper(sol_path, method_name, test_cases, stop_on_failure=False)
            sol_result = run_bwrap(sol_wrapper, sol_wrap_path, sol_path, timeout=30)
            if sol_result["returncode"] == 0:
                try:
                    sol_tc_results = json.loads(sol_result["results_json"])
                except (json.JSONDecodeError, ValueError):
                    sol_tc_results = None
                if sol_tc_results:
                    for i, t in enumerate(sol_tc_results):
                        if i < len(tc_results):
                            tc_results[i]["sol_timing"] = t.get("timing_ms", None)
        finally:
            for p in [sol_path, sol_wrap_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass

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
