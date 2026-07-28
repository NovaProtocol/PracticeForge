import json
import os
import subprocess
import sys
import tempfile

from .config import AI_KEY, AI_MODEL, AI_URL
from . import log
from .tokens import record

SYSTEM_PROMPT = r"""You are an expert Python educational coding platform engine for high school students. Extract problem data from the HTML into this exact JSON structure:
{
  "title": "",
  "time_limit": "",
  "memory_limit": "",
  "input": "",
  "output": "",
  "description": "",
  "input_specification": "",
  "output_specification": "",
  "examples": [
    {
      "input": {},
      "output": 0
    }
  ],
  "constraints": [],
  "hints": [],
  "is_interactive": false,
  "base_code": "",
  "solution_code": "",
  "generator_code": ""
}

Guidelines (Strictly Python-Centric):
1. MATH CONVERSION: Ensure all mathematical variables and expressions are cleanly formatted using standard LaTeX (e.g., $n$, $n \times m$, $998\,244\,353$) so they render properly on the frontend. Do NOT wrap variable names in HTML tags — just use LaTeX directly. Write $a_i$ instead of <var>a_i</var> ($a_i$).
2. DESCRIPTION: Rewrite the problem description so it reads like a clean, standalone coding challenge (like LeetCode). Strip out all competitive programming I/O boilerplate (e.g., ignore mentions of "the first line contains t test cases", "standard input", or raw stream reading). Focus entirely on explaining the core logical task using the input variables provided to the function. IMPORTANT: Keep the original structure with short paragraphs, bullet points, and clear sections. Do NOT condense everything into a single dense paragraph. Preserve whitespace and logical breaks. Keep the full reasoning, edge cases, tie-breaking rules, and any conditional logic from the original problem. If the original has multiple scenarios (e.g., tie-breaking rules, special conditions), describe each one clearly. The description should be complete enough that someone understands the entire problem without guessing. Preserve all numerical bounds and constraints mentioned in the original.
3. CONSTRAINTS: Bulleted list of constraints inferred or stated.
4. HINTS: Python-friendly logic tips and algorithmic hints.
5. IS_INTERACTIVE: Set to true if the problem requires real-time interaction (flushing stdout/reading queries interactively), otherwise false.
6. EXAMPLES: Parse raw sample test cases into an array (`examples`). NEVER use newline strings (`\n`). Every individual test case must have its inputs parsed into a keyword-argument object (`input`), with keys matching the parameter names in the `run()` method signature. The output must be cast to its correct primitive type. If the problem's sample output contains multiple lines (e.g., two numbers on separate lines, or a number followed by a string), convert them into a list `[first, second]` rather than a single string. Example: for a problem that prints "4\n()()" as output, produce `"output": [4, "()()"]` instead of `"output": "4\n()()"`. Similarly, if the problem prints a single value that can be parsed as a number, cast it to int/float instead of keeping it as a string. Example: for `def run(self, n: int, rounds: list) -> str:`, produce `{"input": {"n": 3, "rounds": [["mike", 3], ["andrew", 5], ["mike", 2]]}, "output": "andrew"}`.
7. BASE_CODE: Provide a friendly LeetCode-style starter code for students. Do NOT use a generic `parsed_input: list`. Instead, write explicit parameter names with clear type hints matching the problem's inputs (e.g., `def run(self, h: int, n: int, damage: list, cooldown: list) -> int:`). The parameters will be passed as keyword arguments (**kwargs), so parameter names MUST be meaningful and match the keys used in the `input` objects of the example test cases.
   Example template style:
   class Solution:
       def run(self, h: int, n: int, damage: list, cooldown: list) -> int:
           # Write your code here
           pass
8. SOLUTION_CODE: Provide the CORRECT working reference solution matching the base code signature for student review when stuck. This solution will be AUTOMATICALLY RUN against all example test cases to verify correctness. If it fails any example, you will be asked to fix it. Test your logic carefully — this is the ground truth used by the platform. Do NOT use recursion deeper than Python's default limit. Do NOT use external libraries. Handle ALL edge cases mentioned in the constraints. The solution MUST pass every example test case.
9. GENERATOR_CODE: Provide a Python script that dynamically generates valid test cases conforming to the problem's constraints. The script MUST have a function called `generate()` that returns a list of dictionaries, where each dictionary has keyword argument keys matching the `run()` method parameters and their corresponding values. Example structure:
   ```python
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
   ```
   The generated test cases will be AUTOMATICALLY RUN against the solution_code to verify that every single one passes. If ANY generated case fails the solution, you will be asked to fix the generator. Generate cases covering a range of difficulty (small inputs, large inputs, edge cases, boundary values). The first 100 generated cases MUST pass the solution with 100% success rate.
10. Return ONLY pure JSON."""


class AIEnricher:

    MAX_RETRIES = 5

    def __init__(self):
        self._client = None

    @property
    def _openai_client(self):
        if self._client is None:
            if not AI_KEY:
                raise ValueError("ZEN_API_KEY not set")
            from openai import OpenAI
            self._client = OpenAI(api_key=AI_KEY, base_url=AI_URL)
        return self._client

    def enrich(self, problem_text: str) -> dict | None:
        if not AI_KEY:
            log.warn("ZEN_API_KEY not set — skipping AI enrichment")
            return None

        # First call: raw HTML + system prompt
        data = self._call_ai(problem_text, None)
        if not data:
            return None

        # Solution validation — retry with cleaned problem data
        solution_ok, solution_err = self._validate_solution(data)
        if not solution_ok:
            for attempt in range(self.MAX_RETRIES):
                log.warn(f"Solution failed (attempt {attempt+1}/{self.MAX_RETRIES}): {solution_err[:200]}")
                ctx = self._build_solution_retry_context(data, solution_err)
                retry_data = self._call_ai(None, ctx)
                if retry_data:
                    data["solution_code"] = retry_data.get("solution_code", data["solution_code"])
                    data["base_code"] = retry_data.get("base_code", data["base_code"])
                solution_ok, solution_err = self._validate_solution(data)
                if solution_ok:
                    break
            if not solution_ok:
                log.error(f"Solution validation failed after max retries: {solution_err}")
                return None

        # Generator validation — retry with cleaned problem data + solution + generator
        gen_ok, gen_err = self._validate_generator(data)
        if not gen_ok:
            for attempt in range(self.MAX_RETRIES):
                log.warn(f"Generator failed (attempt {attempt+1}/{self.MAX_RETRIES}): {gen_err[:200]}")
                ctx = self._build_generator_retry_context(data, gen_err)
                retry_data = self._call_ai(None, ctx)
                if retry_data:
                    data["generator_code"] = retry_data.get("generator_code", data["generator_code"])
                    data["solution_code"] = retry_data.get("solution_code", data["solution_code"])
                gen_ok, gen_err = self._validate_generator(data)
                if gen_ok:
                    break
            if not gen_ok:
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

        log.info(f"Sending to AI (problem={len(problem_text or '')} chars, context={len(error_context or '')} chars)")
        try:
            resp = self._openai_client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
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
        examples = data.get("examples", [])
        if not solution_code or not examples:
            return False, "Missing solution_code or examples"
        for i, ex in enumerate(examples):
            kwargs = ex.get("input", {})
            expected = ex.get("output")
            result = _run_code(solution_code, kwargs)
            if result["error"]:
                return False, f"Example {i+1}: raised {result['error']}"
            # Compare JSON-serialized forms (matches executor's effective comparison)
            if json.dumps(result["output"]) != json.dumps(expected):
                return False, f"Example {i+1}: expected {expected!r}, got {result['output']!r}"
        return True, ""

    def _validate_generator(self, data: dict) -> tuple[bool, str]:
        generator_code = data.get("generator_code", "")
        solution_code = data.get("solution_code", "")
        if not generator_code or not solution_code:
            return False, "Missing generator_code or solution_code"
        cases = _run_generator(generator_code, count=100)
        if cases is None:
            return False, "Generator crashed or produced no output"
        if not cases:
            return False, "Generator returned empty list"
        failed = []
        for i, kwargs in enumerate(cases):
            result = _run_code(solution_code, kwargs)
            if result["error"]:
                failed.append(f"Case {i+1}: solution crashed with {result['error']}")
        if failed:
            return False, f"{len(failed)}/100 generated cases failed. First failures:\n" + "\n".join(failed[:5])
        return True, ""


def _run_code(user_code: str, kwargs: dict) -> dict:
    wrapper = f"""
import json, sys
{user_code}
try:
    solution = Solution()
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
