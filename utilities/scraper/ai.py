import json
import os
import subprocess
import sys
import tempfile

from .config import AI_KEY, AI_MODEL, AI_URL, RETRY_LIMIT
from . import log
from .tokens import record

SYSTEM_PROMPT = r"""You are an expert Python educational coding platform engine for high school students. Extract problem data from the HTML into this exact JSON structure:
{
  "title": "Problem Title",
  "time_limit": "1 second",
  "memory_limit": "256 MB",
  "input": "",
  "output": "",
  "description": "Full problem description rewritten for a LeetCode-style interface.",
  "input_specification": "Description of the input parameters.",
  "output_specification": "Description of the expected return value.",
  "examples": [
    {"input": {"n": 5, "arr": [1, 2, 3, 4, 5]}, "output": 15},
    {"input": {"n": 0}, "output": 0}
  ],
  "constraints": ["1 <= n <= 10^5"],
  "hints": ["Think about using two pointers."],
  "base_code": "class Solution:\n    def run(self, n: int, arr: list) -> int:\n        pass",
  "solution_code": "class Solution:\n    def run(self, n: int, arr: list) -> int:\n        return sum(arr)",
  "generator_code": "import random\n\ndef generate():\n    cases = []\n    for _ in range(100):\n        n = random.randint(1, 10)\n        arr = [random.randint(1, 100) for _ in range(n)]\n        cases.append({'n': n, 'arr': arr})\n    return cases",
  "executor_code": ""
}

Guidelines (Strictly Python-Centric):
1. MATH CONVERSION: Ensure all mathematical variables and expressions are cleanly formatted using standard LaTeX (e.g., $n$, $n \times m$, $998\,244\,353$) so they render properly on the frontend. Do NOT wrap variable names in HTML tags — just use LaTeX directly. Write $a_i$ instead of <var>a_i</var>.
2. DESCRIPTION: Rewrite the problem description so it reads like a clean, standalone coding challenge (like LeetCode). Strip out all competitive programming I/O boilerplate (e.g., ignore mentions of "the first line contains t test cases", "standard input", or raw stream reading). Focus entirely on explaining the core logical task using the input variables provided to the function. Keep the original structure with short paragraphs, bullet points, and clear sections. Preserve whitespace and logical breaks. Keep the full reasoning, edge cases, tie-breaking rules, and any conditional logic from the original. The description must be complete enough that someone understands the entire problem without guessing. Preserve all numerical bounds and constraints.
   IMAGES: A marker like `[image: <filename>]` in the problem text indicates a figure or diagram at that position in the original statement. Keep the marker in its original position in the description so the figure placement is preserved. The marker MUST be on its own line with no other text on that line — place it as a standalone line between the surrounding paragraphs. If the surrounding text explains what the figure shows (e.g., "according to the picture"), include that explanation in your own words in the adjacent paragraph. Do not invent facts about the image that the text does not support.
3. CONSTRAINTS: Bulleted list of constraints inferred or stated.
4. HINTS: Python-friendly logic tips and algorithmic hints.
5. EXECUTOR_CODE: This is for INTERACTIVE problems (problems where the solution must query the judge, e.g. "you can ask up to 20 queries", "this is an interactive problem", reading responses after printing queries). If the problem is interactive, provide Python source code in `executor_code` that defines the judge's state and query functions. This code is exec'd AFTER the user's `Solution` class is defined, in the same namespace, so it can attach functions to the class via `Solution.<name> = staticmethod(<function>)`. Use `staticmethod` so the user can call `self.<name>(...)` inside `run()` without binding issues. Example for a "guess the hidden number" problem:
   HIDDEN = 42
   _queries = 0
   def query(x):
       global _queries
       _queries += 1
       if _queries > 20:
           raise Exception("query limit exceeded")
       return HIDDEN % x == 0
   Solution.query = staticmethod(query)
   The user's solution then calls `self.query(...)` inside `run()`. The `HIDDEN` variable and `_queries` counter are reset by the executor before each test case from the test case's `hidden` field — your `base_code`, `solution_code`, and `generator_code` must reference `self.query` (or whatever you name it). The generator must emit cases with a `hidden` key carrying the judge's secret plus the expected final answer. The `run()` method should receive no input params for interactive problems (the interaction happens via the query functions) and return the final answer. If the problem is NOT interactive, set `executor_code` to an empty string.
6. EXAMPLES: Parse raw sample test cases into an array (`examples`). NEVER use newline strings (`\n`) in output. Every test case's `input` must be a keyword-argument object with keys matching the parameter names in `run()`. The `output` must be cast to its correct type: if the correct answer is a number, use int/float; if a string, use string; if multiple values, use a list. For example, if sample output is "4\n()()", produce `"output": [4, "()()"]`. If it's just "4", produce `"output": 4`.
7. BASE_CODE: Provide a friendly LeetCode-style starter code with explicit parameter names and type hints. Parameters will be passed as **kwargs. Example:
   class Solution:
       def run(self, h: int, n: int, damage: list, cooldown: list) -> int:
           pass
8. SOLUTION_CODE: Provide a CORRECT, general-purpose solution matching the base code signature. It will be automatically run against all example AND generated test cases. It must solve the problem generally — no hardcoded example-to-answer mapping. Write readable code with clear variable names, appropriate data structures, proper control flow. It does not need to be overly verbose. Do NOT use recursion deeper than Python's default limit. Do NOT use external libraries. Handle ALL edge cases mentioned in the constraints.
9. GENERATOR_CODE: Provide a Python script with a function `generate()` that returns a list of dicts. Each dict's keys must match the `run()` method parameter names. Do NOT wrap the code in markdown. Just output the raw Python source as a string. Example:
   import random
   def generate():
       cases = []
       for _ in range(100):
           n = random.randint(1, 1000)
           rounds = []
           for _ in range(n):
               name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=random.randint(1, 32)))
               score = random.randint(-1000, 1000)
               rounds.append([name, score])
           cases.append({'n': n, 'rounds': rounds})
       return cases
   The generated test cases will be automatically run against the solution_code. Generate cases covering a range of difficulty (small, large, edge cases, boundary values).
10. Return ONLY pure JSON. No markdown, no code fences, no extra text."""


class AIEnricher:

    def __init__(self):
        self._client = None
        self.last_error = ""

    @property
    def _openai_client(self):
        if self._client is None:
            if not AI_KEY:
                raise ValueError("ZEN_API_KEY not set")
            from openai import OpenAI
            self._client = OpenAI(api_key=AI_KEY, base_url=AI_URL)
        return self._client

    def enrich(self, problem_text: str) -> dict | None:
        self.last_error = ""
        if not AI_KEY:
            self.last_error = "ZEN_API_KEY not set"
            log.warn("ZEN_API_KEY not set — skipping AI enrichment")
            return None

        # First call: raw HTML + system prompt
        data = self._call_ai(problem_text, None)
        if not data:
            self.last_error = "AI returned no data (empty or parse failure)"
            return None

        # Solution validation — retry with cleaned problem data
        solution_ok, solution_err = self._validate_solution(data)
        if not solution_ok:
            for attempt in range(RETRY_LIMIT):
                log.warn(f"Solution failed (attempt {attempt+1}/{RETRY_LIMIT}): {solution_err}")
                ctx = self._build_solution_retry_context(data, solution_err)
                retry_data = self._call_ai(None, ctx)
                if retry_data:
                    data["solution_code"] = retry_data.get("solution_code", data["solution_code"])
                    data["base_code"] = retry_data.get("base_code", data["base_code"])
                solution_ok, solution_err = self._validate_solution(data)
                if solution_ok:
                    break
            if not solution_ok:
                self.last_error = f"Solution validation failed: {solution_err}"
                log.error(f"Solution validation failed after max retries: {solution_err}")
                return None

        # Generator validation — retry with cleaned problem data + solution + generator
        gen_ok, gen_err = self._validate_generator(data)
        if not gen_ok:
            for attempt in range(RETRY_LIMIT):
                log.warn(f"Generator failed (attempt {attempt+1}/{RETRY_LIMIT}): {gen_err}")
                ctx = self._build_generator_retry_context(data, gen_err)
                retry_data = self._call_ai(None, ctx)
                if retry_data:
                    data["generator_code"] = retry_data.get("generator_code", data["generator_code"])
                    data["solution_code"] = retry_data.get("solution_code", data["solution_code"])
                gen_ok, gen_err = self._validate_generator(data)
                if gen_ok:
                    break
            if not gen_ok:
                self.last_error = f"Generator validation failed: {gen_err}"
                log.error(f"Generator validation failed after max retries: {gen_err}")
                return None

        # Fully validated: solution passes examples AND generator produces 100% passing cases
        return data

    def _build_solution_retry_context(self, data: dict, error: str) -> str:
        """Build retry prompt using cleaned problem data (not raw HTML)."""
        examples = data.get("examples", [])
        ex_str = json.dumps(examples, indent=2) if examples else "[]"
        desc = data.get("description", "")[:1000]
        return (
            f"Your solution_code failed validation against the example test cases.\n\n"
            f"Error:\n{error}\n\n"
            f"Problem description:\n{desc}\n\n"
            f"Example test cases:\n{ex_str}\n\n"
            f"Your current solution_code:\n{data.get('solution_code', '')}\n\n"
            f"Current base_code:\n{data.get('base_code', '')}\n\n"
            f"Fix the solution_code so it produces the correct output for ALL example cases. "
            f"Return the COMPLETE JSON with updated solution_code. Keep all other fields unchanged."
        )

    def _build_generator_retry_context(self, data: dict, error: str) -> str:
        """Build retry prompt for generator failures, includes solution + generator."""
        examples = data.get("examples", [])
        ex_str = json.dumps(examples, indent=2) if examples else "[]"
        desc = data.get("description", "")[:1000]
        return (
            f"Your generator_code failed validation.\n\n"
            f"Error:\n{error}\n\n"
            f"Problem description:\n{desc}\n\n"
            f"Example test cases:\n{ex_str}\n\n"
            f"Current solution_code:\n{data.get('solution_code', '')}\n\n"
            f"Current generator_code:\n{data.get('generator_code', '')}\n\n"
            f"Current base_code:\n{data.get('base_code', '')}\n\n"
            f"Fix either the solution_code or the generator_code so that:\n"
            f"1. The solution_code produces correct output for ALL example cases.\n"
            f"2. The generator_code produces 100 test cases that ALL pass when validated against the solution_code.\n"
            f"Return the COMPLETE JSON with the corrected fields. Keep all other fields unchanged."
        )

    def _call_ai(self, problem_text: str | None, error_context: str | None) -> dict | None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if error_context:
            messages.append({"role": "user", "content": error_context})
        if problem_text:
            messages.append({"role": "user", "content": problem_text})

        full_text = "\n".join(m["content"] for m in messages)
        log.info(f"Sending to AI (problem={len(problem_text or '')} chars, context={len(error_context or '')} chars)")
        log.info(f"--- Full prompt ({len(full_text)} chars) ---")
        for line in full_text.split("\n"):
            log.info(line)
        log.info("--- End prompt ---")
        try:
            resp = self._openai_client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                timeout=600,
            )
            content = resp.choices[0].message.content
            if not content:
                log.error("AI returned empty response")
                return None
            tokens = resp.usage.total_tokens if resp.usage else 0
            if tokens:
                record(tokens)
            log.info(f"AI OK ({tokens} tokens)")
            return json.loads(content)
        except Exception as e:
            log.error(f"AI request failed: {e}")
            return None

    def _validate_solution(self, data: dict) -> tuple[bool, str]:
        solution_code = data.get("solution_code", "")
        executor_code = data.get("executor_code", "") or ""
        examples = data.get("examples", [])
        if not solution_code or not examples:
            return False, "Missing solution_code or examples"
        for i, ex in enumerate(examples):
            kwargs = ex.get("input", {})
            expected = ex.get("output")
            hidden = ex.get("hidden")
            result = _run_code(solution_code, kwargs, executor_code, hidden)
            if result["error"]:
                return False, f"Example {i+1}: raised {result['error']}"
            # Same comparison as executor's _matches: exact JSON equality
            # OR numeric equivalence for int/float (1 == 1.0)
            if not _val_equal(result["output"], expected):
                return False, f"Example {i+1}: expected {expected!r}, got {result['output']!r}"
        return True, ""

    def _validate_generator(self, data: dict) -> tuple[bool, str]:
        generator_code = data.get("generator_code", "")
        solution_code = data.get("solution_code", "")
        executor_code = data.get("executor_code", "") or ""
        if not generator_code or not solution_code:
            return False, "Missing generator_code or solution_code"
        cases = _run_generator(generator_code, count=100)
        if cases is None:
            return False, "Generator crashed or produced no output"
        if not cases:
            return False, "Generator returned empty list"
        failed = []
        for i, kwargs in enumerate(cases):
            hidden = kwargs.get("hidden") if isinstance(kwargs, dict) else None
            result = _run_code(solution_code, kwargs, executor_code, hidden)
            if result["error"]:
                failed.append(f"Case {i+1}: solution crashed with {result['error']}")
        if failed:
            return False, f"{len(failed)}/100 generated cases failed. First failures:\n" + "\n".join(failed[:5])
        return True, ""


def _val_equal(a, b):
    """Same comparison as executor's _matches: exact JSON equality or
    numeric equivalence for int/float (1 == 1.0)."""
    if json.dumps(a) == json.dumps(b):
        return True
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return abs(a - b) < 1e-9
    return False


def _run_code(user_code: str, kwargs: dict, executor_code: str = "", hidden=None) -> dict:
    wrapper = f"""
import json, sys
{user_code}
HIDDEN = None
_queries = 0
{executor_code}
try:
    solution = Solution()
    HIDDEN = {json.dumps(hidden)}
    _queries = 0
    result = solution.run(**json.loads(sys.argv[1]))
    print(json.dumps({{"output": result}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper)
        tmp.close()
        r = subprocess.run(
            [sys.executable, tmp.name, json.dumps(kwargs)],
            capture_output=True, text=True, timeout=15,
        )
        output = json.loads(r.stdout.strip() or "{}")
        if "error" in output:
            return {"output": None, "error": output["error"]}
        return {"output": output.get("output"), "error": None}
    except Exception as e:
        return {"output": None, "error": str(e)}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _run_generator(generator_code: str, count: int = 100) -> list | None:
    wrapper = f"""
import json
{generator_code}
result = generate()
print(json.dumps(result))
"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper)
        tmp.close()
        r = subprocess.run(
            [sys.executable, tmp.name],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            log.warn(f"Generator stderr: {r.stderr[:200]}")
            return None
        return json.loads(r.stdout.strip())
    except Exception as e:
        log.warn(f"Generator error: {e}")
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
