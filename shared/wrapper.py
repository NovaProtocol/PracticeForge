"""Shared test-case wrapper generation.

Used by BOTH the remote executor (bwrap_executor.py) and the scraper's
AI validation (utilities/scraper/ai.py) so that validation and execution
always run the exact same generated code.

The wrapper:
  1. execs the user's Solution class
  2. execs executor_code (interactive judge functions) if provided
  3. per test case: sets HIDDEN/_queries from the case's hidden field
  4. calls the method with the case's input kwargs
  5. compares got vs expected (numeric-lenient)
  6. emits __SOLVER_RESULT__ + JSON results
"""

import json


def _pyval(v):
    """JSON -> Python literal: None -> 'None', True->'True', etc."""
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    return json.dumps(v)


def build_wrapper(user_code_path: str, method_name: str, test_cases: list[dict], stop_on_failure: bool = False, executor_code: str = "") -> str:
    lines = [
        "import json, sys, io, time, traceback, signal",
        "from typing import List, Optional, Dict, Tuple, Set",
        "def _matches(got, expected):",
        "    if got == json.dumps(expected): return True",
        "    if isinstance(expected, (int, float)) and not isinstance(expected, bool):",
        "        try: return abs(float(got) - float(expected)) < 1e-9",
        "        except (ValueError, TypeError): return False",
        "    return False",
        f"exec(compile(open({json.dumps(user_code_path)}).read(), {json.dumps(user_code_path)}, 'exec'))",
    ]
    if executor_code:
        lines.append("HIDDEN = None")
        lines.append("_queries = 0")
        lines.append("exec(compile(" + json.dumps(executor_code) + ", '<executor_code>', 'exec'))")
    lines += [
        "solution = Solution()",
        "method = getattr(solution, " + json.dumps(method_name) + ")",
        "results = []",
        "_abort = False",
        "class _TimeoutError(Exception): pass",
        "def _timeout_handler(signum, frame): raise _TimeoutError",
        "signal.signal(signal.SIGALRM, _timeout_handler)",
    ]
    for tc in test_cases:
        input_data = dict(tc.get("input") or {})
        input_data.pop("_hint", None)  # marker only, never passed to run()
        expected = tc.get("output")
        hidden = tc.get("hidden")
        inp_display = input_data if input_data else ({"hidden": hidden} if hidden is not None else {})
        exp_display = expected

        lines.append("if not _abort:")
        lines.append("  signal.alarm(10)")
        lines.append("  _cap = io.StringIO()")
        lines.append("  _old_stdout = sys.stdout")
        lines.append("  sys.stdout = _cap")
        lines.append("  _r_input = " + json.dumps(inp_display))
        lines.append("  _r_expected = " + _pyval(exp_display))
        lines.append("  err = ''")
        lines.append("  _t0 = time.perf_counter()")
        lines.append("  try:")
        if hidden is not None:
            lines.append("    HIDDEN = " + _pyval(hidden))
            lines.append("    _queries = 0")
        lines.append("    result = method(**" + json.dumps(input_data) + ")")
        lines.append("    got = json.dumps(result)")
        if expected is not None:
            lines.append("    passed = _matches(got, " + _pyval(expected) + ")")
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


def parse_output(stdout: str) -> dict:
    """Split wrapper stdout into results JSON + user stdout."""
    result = {"results_json": "[]", "user_stdout": "", "raw_stdout": stdout}
    marker = "__SOLVER_RESULT__"
    if marker in stdout:
        parts = stdout.split(marker + "\n", 1)
        if len(parts) > 1:
            result["results_json"] = parts[1].strip()
    return result
