import json

from .config import AI_KEY, AI_MODEL, AI_URL
from . import log
from .tokens import check_and_track


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

        # Rough estimate: ~4 chars per token for input + output
        estimated = max(1000, (len(problem_text) // 4) * 3)
        check_and_track(estimated)

        prompt = (
            r'Extract problem data as JSON: {"title","time_limit","memory_limit",'
            r'"description","input_specification","output_specification","examples",'
            r'"constraints","is_interactive","base_code","solution_code","generator_code"}. '
            r"Use $...$ LaTeX. Parse examples as native JSON types, NO \\n. "
            r"base_code = LeetCode-style starter with typed params. Return ONLY JSON."
        )

        log.info(f"Sending to AI ({len(problem_text)} chars)")
        try:
            resp = self._openai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt + "\n\n" + problem_text}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = resp.choices[0].message.content
            if not content:
                log.error("AI returned empty response")
                return None

            # Update with actual token count
            actual = resp.usage.total_tokens if resp.usage else estimated
            check_and_track(actual - estimated)  # correct the estimate

            log.info(f"AI OK ({actual} tokens)")
            return json.loads(content)
        except Exception as e:
            log.error(f"AI request failed: {e}")
            return None
