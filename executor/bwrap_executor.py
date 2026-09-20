from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import time

import pymysql
from pymysql.cursors import DictCursor
from wrapper import build_wrapper, parse_output

# gRPC (internal): optional, best-effort. If import fails, poll-only mode continues.
try:
    import grpc  # noqa: F401
    from grpc_server import serve_grpc as _grpc_serve  # type: ignore

    _HAS_GRPC = True
except Exception:  # pragma: no cover
    _HAS_GRPC = False
    _grpc_serve = None  # type: ignore

POLL_INTERVAL = 1
TIMEOUT = 30
BWRAP = "/usr/bin/bwrap"
_LOG_INDENT = 0

# Hard limits applied to every sandboxed process tree (see _set_rlimits).
# User code inherits them and cannot raise a hard limit.
MEMORY_LIMIT_MB = int(os.environ.get("MEMORY_LIMIT_MB", "1024"))
PROCESS_LIMIT = int(os.environ.get("PROCESS_LIMIT", "64"))
CPU_LIMIT_SECONDS = int(os.environ.get("CPU_LIMIT_SECONDS", "25"))


def _find_python() -> str:
    """Resolve the python interpreter once. The sandbox binds the host's
    /usr and /usr/local read-only, so the interpreter must live under
    one of those paths. Fail loudly if not found."""
    for candidate in ("/usr/local/bin/python3", "/usr/bin/python3", "/bin/python3"):
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError("no python3 found under /usr or /usr/local, sandbox cannot run")


def _log(msg: str, indent: int = 0):
    pad = "    " * (_LOG_INDENT + indent)
    print(f"[bwrap-executor] {pad}{msg}", flush=True)


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
        cur.execute("SELECT * FROM execution_queue WHERE status = 'queued' ORDER BY id LIMIT 1")
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


def _bwrap_env():
    """Sandboxed process gets an empty environment: no MYSQL_* secrets, nothing.
    Only absolute python path matters; it does not need env vars."""
    return {}


PYTHON_BIN = _find_python()


def _bwrap_cmd(script_path: str, extra_binds: tuple = ()) -> list:
    args = [
        BWRAP,
        "--unshare-all",  # user, net, ipc, pid, uts, cgroup, time
        "--die-with-parent",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/usr/local",
        "/usr/local",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--tmpfs",
        "/tmp",
        "--dev",
        "/dev",
        "--ro-bind",
        script_path,
        script_path,
    ]
    for src in extra_binds:
        args += ["--ro-bind", src, src]
    args += ["--chdir", "/", PYTHON_BIN, script_path]
    return args


def _set_rlimits():
    """Hard rlimits for the sandboxed process tree. Runs in the forked child
    before bwrap execs, so bwrap and everything inside the sandbox inherits
    them. User code cannot raise a hard limit. If a limit cannot be set it is
    logged loudly, the sandbox still runs, the cgroup limits back it up.

    NOTE: RLIMIT_NPROC is NOT enforced while the sandbox runs as uid 0 in its
    own user namespace, the kernel exempts processes with CAP_SYS_ADMIN in
    that namespace, so fork bombs are instead bounded by the container's
    pids cgroup limit (pids_limit in compose.yaml). The other limits here
    (RLIMIT_AS, RLIMIT_CPU, RLIMIT_CORE) apply unconditionally."""
    import resource

    limits = {
        resource.RLIMIT_AS: MEMORY_LIMIT_MB * 1024 * 1024,
        resource.RLIMIT_NPROC: PROCESS_LIMIT,
        resource.RLIMIT_CPU: CPU_LIMIT_SECONDS,
        resource.RLIMIT_CORE: 0,
    }
    for rlim, value in limits.items():
        try:
            resource.setrlimit(rlim, (value, value))
        except (ValueError, OSError) as e:
            _log(f"setrlimit {rlim} failed: {e}", indent=1)


def _run_sandboxed(cmd: list, timeout: int) -> dict:
    """Run a command inside the sandbox. No fallback, if bwrap fails,
    the error is returned loudly and the queue entry is marked failed."""
    try:
        start = time.perf_counter()
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_bwrap_env(),
            preexec_fn=_set_rlimits,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception as e:
            _log(f"getrusage failed: {e}", indent=1)
            mem = 0
        return {
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "timing_ms": elapsed,
            "memory_kb": mem,
        }
    except subprocess.TimeoutExpired as te:
        partial = ""
        if te.output:
            partial = te.output.decode() if isinstance(te.output, bytes) else te.output
        msg = "Time Limit Exceeded"
        if partial:
            idx = partial.find("case ")
            if idx >= 0:
                msg += f" (during test {partial[idx : idx + 20].strip()})"
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": msg,
            "timing_ms": timeout * 1000,
            "memory_kb": 0,
        }


def run_bwrap(
    wrapper_code: str, wrapper_path: str, user_code_path: str | None = None, timeout: int = TIMEOUT
) -> dict:
    """Write the wrapper and run it inside the sandbox. NO unsandboxed fallback."""
    with open(wrapper_path, "w") as f:
        f.write(wrapper_code)
    os.chmod(wrapper_path, 0o644)

    extra = (user_code_path,) if user_code_path else ()
    cmd = _bwrap_cmd(wrapper_path, extra)
    result = _run_sandboxed(cmd, timeout)
    parsed = parse_output(result["stdout"])
    result["results_json"] = parsed["results_json"]
    return result


def run_script_bwrap(script_path: str, timeout: int = TIMEOUT) -> dict:
    """Run an arbitrary script file inside the sandbox (used for generator_code)."""
    cmd = _bwrap_cmd(script_path)
    result = _run_sandboxed(cmd, timeout)
    result["results_json"] = ""
    return result


def create_solution(conn, problem_id, code, verdict, passed, total, timing_ms, memory_kb):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO solutions (problem_id, code, language, verdict, passed_count, total_count, timing_ms, memory_kb)
               VALUES (%s, %s, 'python', %s, %s, %s, %s, %s)""",
            (problem_id, code, verdict, passed, total, timing_ms, memory_kb),
        )
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        return cur.fetchone()["id"]


def generate_brute_force_test_cases(conn, problem_id, qid, max_valid=100):
    """Generate test cases using generator_code, validate with solution_code.
    ALL code runs inside the sandbox. Returns (list | None, error_msg)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT generator_code, solution_code, method_name, executor_code FROM problems WHERE id = %s",
            (problem_id,),
        )
        row = cur.fetchone()
    if not row:
        return None, f"Problem #{problem_id} not found in database"
    generator_code = row.get("generator_code") or ""
    solution_code = row.get("solution_code") or ""
    method_name = row.get("method_name") or "run"
    executor_code = row.get("executor_code") or ""
    if not generator_code:
        return None, "Problem has no generator_code"
    if not solution_code:
        return None, "Problem has no solution_code"

    gen_path = f"/tmp/gen-{get_problem_label(conn, problem_id)}-{qid}.py"
    gen_wrapper = (
        generator_code
        + "\n\nimport json\ntry:\n    result = generate()\n    print(json.dumps(result))\nexcept Exception as e:\n    print(json.dumps({'error': str(e)}))\n"
    )
    with open(gen_path, "w") as f:
        f.write(gen_wrapper)
    os.chmod(gen_path, 0o644)

    try:
        gen_result = run_script_bwrap(gen_path, timeout=30)
        if gen_result["returncode"] != 0:
            return (
                None,
                f"Generator crashed (rc={gen_result['returncode']}):\n{gen_result['stderr']}\n{gen_result['stdout']}",
            )
        if gen_result["stderr"]:
            for line in gen_result["stderr"].split("\n"):
                _log(f"generator stderr: {line}", indent=2)
        try:
            all_cases = json.loads(gen_result["stdout"].split("\n")[0] or "[]")
        except (json.JSONDecodeError, ValueError) as e:
            return None, f"Generator output not valid JSON: {e}\nRaw:\n{gen_result['stdout']}"
    finally:
        if os.path.exists(gen_path):
            os.unlink(gen_path)

    if not isinstance(all_cases, list) or len(all_cases) == 0:
        return None, "Generator produced no valid test cases"

    valid = []
    for tc_data in all_cases:
        if len(valid) >= max_valid:
            break
        if not isinstance(tc_data, dict):
            continue

        sol_path = f"/tmp/sol-{get_problem_label(conn, problem_id)}-{qid}-{len(valid)}.py"
        sol_wrap_path = f"/tmp/solwrap-{get_problem_label(conn, problem_id)}-{qid}-{len(valid)}.py"
        try:
            with open(sol_path, "w") as f:
                f.write(solution_code)
            os.chmod(sol_path, 0o644)
            sol_wrapper = build_wrapper(
                sol_path,
                method_name,
                [
                    {
                        "input": {
                            k: v for k, v in tc_data.items() if k not in ("hidden", "output")
                        },
                        "hidden": tc_data.get("hidden"),
                        "output": None,
                    }
                ],
                executor_code=executor_code,
            )
            sol_result = run_bwrap(sol_wrapper, sol_wrap_path, sol_path, timeout=15)
        except Exception as e:
            _log(f"gen case validation setup failed: {e}", indent=2)
            continue
        finally:
            for p in (sol_path, sol_wrap_path):
                if os.path.exists(p):
                    os.unlink(p)

        inp_str = json.dumps(tc_data)
        if sol_result["returncode"] != 0:
            _log(f"gen case: {inp_str}, runtime error (rc={sol_result['returncode']})", indent=2)
            for line in (sol_result["stderr"] or "").split("\n"):
                _log(f"stderr: {line}", indent=3)
            continue
        try:
            tc_results = json.loads(sol_result["results_json"])
        except (json.JSONDecodeError, ValueError) as e:
            _log(f"gen case: {inp_str}, parse error: {e}", indent=2)
            _log(f"raw output: {sol_result['stdout'][:500]}", indent=3)
            continue
        if not tc_results:
            _log(f"gen case: {inp_str}, no results returned", indent=2)
            continue
        if tc_results[0].get("status") == "failed":
            got = tc_results[0].get("got", "")
            err = tc_results[0].get("error", "")
            _log(f"gen case: {inp_str}, solution failed", indent=2)
            _log(f"got: {got}", indent=3)
            for line in (err or "").split("\n"):
                _log(f"{line}", indent=3)
            continue

        got = tc_results[0].get("got", "")
        try:
            expected_raw = json.loads(got)
        except (json.JSONDecodeError, ValueError):
            expected_raw = got
        valid.append(
            {
                "input": {k: v for k, v in tc_data.items() if k not in ("hidden", "output")},
                "hidden": tc_data.get("hidden"),
                "output": expected_raw,
            }
        )

    if not valid:
        return None, f"All {len(all_cases)} generated cases failed validation"
    return valid, ""


def process_entry(conn, entry):
    global _LOG_INDENT
    qid = entry["id"]
    problem_id = entry["problem_id"]
    code = entry["code"]
    method_name = entry.get("method_name") or "run"
    exec_type = entry.get("exec_type") or "run"

    label = get_problem_label(conn, problem_id)
    _log(f"queue [{qid}] ({label}) {exec_type}, started")
    _LOG_INDENT += 1

    try:
        mark_running(conn, qid)

        executor_code = ""
        with conn.cursor() as cur:
            cur.execute("SELECT executor_code FROM problems WHERE id = %s", (problem_id,))
            p_row = cur.fetchone()
        if p_row and p_row.get("executor_code"):
            executor_code = p_row["executor_code"]

        test_cases = None
        raw = entry.get("test_cases_json")
        if raw is not None:
            if isinstance(raw, (list, dict)):
                test_cases = raw if isinstance(raw, list) else [raw]
            elif isinstance(raw, str):
                try:
                    test_cases = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as e:
                    _log(f"test_cases_json parse error: {e}", indent=1)
                    mark_failed(conn, qid, f"Invalid test_cases_json: {e}")
                    return
        if exec_type in ("brute_force", "submit_brute"):
            _log("generating test cases from generator...", indent=1)
            gen_cases, gen_err = generate_brute_force_test_cases(conn, problem_id, qid)
            if gen_cases is None:
                _log(f"generator failed: {gen_err}", indent=1)
                mark_failed(conn, qid, f"Failed to generate test cases: {gen_err}")
                return
            test_cases = gen_cases
            _log(f"generated {len(test_cases)} test cases", indent=1)

        if not test_cases:
            _log("no test cases found", indent=1)
            mark_failed(conn, qid, "No test cases found")
            return

        source = "examples" if exec_type == "run" else "generator"
        _log(f"running {len(test_cases)} test cases ({source})", indent=1)

        user_code_path = f"/tmp/solver-{label}-{qid}.py"
        with open(user_code_path, "w") as f:
            f.write(code)
        os.chmod(user_code_path, 0o644)

        wrapper_path = f"/tmp/wrapper-{label}-{qid}.py"
        stop_on_failure = exec_type in ("brute_force", "submit_brute")
        wrapper = build_wrapper(
            user_code_path, method_name, test_cases, stop_on_failure, executor_code
        )
        result = run_bwrap(wrapper, wrapper_path, user_code_path)
        for p in (user_code_path, wrapper_path):
            if os.path.exists(p):
                os.unlink(p)

        if result["returncode"] != 0:
            _log(f"execution failed: {result['stderr'] or result['stdout']}", indent=1)
            mark_failed(conn, qid, result["stderr"] or result["stdout"])
            return

        try:
            tc_results = json.loads(result["results_json"])
        except json.JSONDecodeError as e:
            _log(f"parse error: {e}", indent=1)
            mark_failed(conn, qid, f"Failed to parse output: {e}\nRaw: {result['stdout']}")
            return

        _LOG_INDENT += 1
        for i, tc in enumerate(tc_results):
            inp = json.dumps(tc.get("input", ""))
            exp = json.dumps(tc.get("expected", ""))
            got = tc.get("got", "")
            status = tc.get("status", "unknown")
            timing = tc.get("timing_ms")
            t_str = f"  ({timing:.3f}ms)" if timing is not None else ""
            if status == "passed":
                _log(f"✓ test ({i + 1}/{len(tc_results)})  {inp}  →  {got}{t_str}", indent=1)
            elif status == "failed":
                _log(
                    f"✗ test ({i + 1}/{len(tc_results)})  {inp}  expected {exp}  got {got}{t_str}",
                    indent=1,
                )
            elif status == "skipped":
                _log(f"− test ({i + 1}/{len(tc_results)})  skipped (no input)", indent=1)
        _LOG_INDENT -= 1

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
            sol_path = f"/tmp/solcompare-{label}-{qid}.py"
            sol_wrap_path = f"/tmp/solcomparewrap-{label}-{qid}.py"
            try:
                with open(sol_path, "w") as f:
                    f.write(sol_code)
                os.chmod(sol_path, 0o644)
                sol_wrapper = build_wrapper(
                    sol_path,
                    method_name,
                    test_cases,
                    stop_on_failure=False,
                    executor_code=executor_code,
                )
                sol_result = run_bwrap(sol_wrapper, sol_wrap_path, sol_path, timeout=30)
                if sol_result["returncode"] == 0:
                    try:
                        sol_tc_results = json.loads(sol_result["results_json"])
                    except (json.JSONDecodeError, ValueError) as e:
                        _log(f"solution compare parse error: {e}", indent=1)
                        sol_tc_results = None
                    if sol_tc_results:
                        for i, t in enumerate(sol_tc_results):
                            if i < len(tc_results):
                                tc_results[i]["sol_timing"] = t.get("timing_ms", None)
            finally:
                for p in (sol_path, sol_wrap_path):
                    if os.path.exists(p):
                        os.unlink(p)

        result_data = json.dumps(
            {
                "results": tc_results,
                "stdout": all_stdout,
            }
        )

        verdict = "Accepted" if passed == total else "Wrong Answer"
        _log(
            f"verdict: {verdict} ({passed}/{total} passed, {timing_ms}ms, {memory_kb}KB)", indent=1
        )
        mark_completed(conn, qid, result_data, all_stdout, "", timing_ms, memory_kb)

        if exec_type == "submit":
            sid = create_solution(
                conn, problem_id, code, verdict, passed, total, timing_ms, memory_kb
            )
            with conn.cursor() as cur:
                cur.execute("UPDATE execution_queue SET solution_id = %s WHERE id = %s", (sid, qid))
            _log(f"solution #{sid} created", indent=1)

        _log(f"queue [{qid}], done ({timing_ms}ms)")
    finally:
        _LOG_INDENT -= 1


def _become_subreaper() -> None:
    """Make this process the child subreaper so orphaned sandbox processes are
    reparented here instead of the container init, then get reaped by
    reap_orphans(). Without this, every bwrap run leaks a zombie until the
    container's pids cgroup saturates and forks fail with EAGAIN."""
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_CHILD_SUBREAPER = 36
        if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_CHILD_SUBREAPER)")
        _log("subreaper enabled, orphaned sandbox processes will be reaped")
    except Exception as e:
        _log(f"FATAL: cannot become subreaper, zombies will accumulate: {e}")


def reap_orphans() -> None:
    """Non-blocking waitpid sweep for reaped-orphan zombies.

    Only safe while no subprocess.run is in flight, the executor is
    single-threaded, so call between sandbox runs (process_entry finally and
    the idle poll loop)."""
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except ChildProcessError:
        pass
    except Exception as e:
        _log(f"reap_orphans error: {e}")


def _start_grpc_background() -> None:
    """Start gRPC ExecutorService in a daemon thread (internal net only)."""
    if not _HAS_GRPC:
        _log("gRPC not available, running poll-only")
        return
    import threading

    def _run() -> None:
        import asyncio

        port = int(os.environ.get("GRPC_PORT", "50051"))
        try:
            asyncio.run(_grpc_serve(port))  # type: ignore[misc]
        except Exception as exc:  # pragma: no cover
            print(f"[bwrap-executor] gRPC server crashed: {exc}", flush=True)

    t = threading.Thread(target=_run, name="grpc-server", daemon=True)
    t.start()
    _log(f"gRPC server starting on :{os.environ.get('GRPC_PORT', '50051')} (internal)")


def main():
    _become_subreaper()
    _start_grpc_background()
    print("[bwrap-executor] Starting...", flush=True)
    while True:
        try:
            conn = get_connection()
            print("[bwrap-executor] Connected to MySQL.", flush=True)
            while True:
                try:
                    entry = fetch_queued(conn)
                    if entry:
                        try:
                            process_entry(conn, entry)
                        except Exception as e:
                            import traceback

                            traceback.print_exc(file=sys.stderr)
                            _log(f"FATAL: queue #{entry['id']} crashed: {e}", indent=1)
                            try:
                                mark_failed(conn, entry["id"], f"Executor error: {e}")
                            except Exception as e2:
                                _log(f"mark_failed also crashed: {e2}", indent=1)
                        finally:
                            reap_orphans()
                    else:
                        reap_orphans()
                        time.sleep(POLL_INTERVAL)
                except Exception as e:
                    print(f"[bwrap-executor] Poll error: {e}", flush=True)
                    time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[bwrap-executor] DB connection failed: {e}, retrying in 5s...", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
