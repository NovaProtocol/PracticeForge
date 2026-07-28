import json

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
8. SOLUTION_CODE: Provide the working reference solution matching the base code signature for student review when stuck.
9. GENERATOR_CODE: Provide a Python script (using the random module) that dynamically generates valid test cases conforming to the problem's constraints. It should output a string or list representing test cases.
10. Return ONLY pure JSON."""


class AIEnricher:

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


        log.info(f"Sending to AI ({len(problem_text)} chars)")
        try:
            resp = self._openai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": problem_text},
                ],
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
