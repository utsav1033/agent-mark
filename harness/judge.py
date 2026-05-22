"""
Gemini 2.5 Flash rubric judge.

Returns {"success": 0|1, "reasoning": str} or {"success": null, "reasoning": "judge-failed"}
on parse failure after one retry. Never defaults to success or failure — failures are
explicitly marked so they can be excluded from aggregate stats.

Required env var: GOOGLE_API_KEY
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"

JUDGE_PROMPT = """\
Evaluate this agent response.

Task: {prompt}
Rubric: {rubric}
Agent's final response: {response}

Respond with JSON only:
{{"success": 0 or 1, "reasoning": "one sentence"}}
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


def _call_model(prompt_text: str) -> dict:
    client = _get_client()
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    raw = response.text.strip()
    return json.loads(raw)


def judge(prompt: str, rubric: str, response: str) -> dict:
    """
    Returns {"success": 0|1, "reasoning": str}.
    On parse failure after one retry: {"success": None, "reasoning": "judge-failed: <reason>"}.
    """
    if not rubric:
        rubric = "The agent should have answered the question accurately and completely."

    filled = JUDGE_PROMPT.format(prompt=prompt, rubric=rubric, response=response)

    for attempt in range(2):
        try:
            result = _call_model(filled)
            if "success" in result and "reasoning" in result:
                result["success"] = int(result["success"])
                return result
            log.warning("Judge attempt %d: unexpected shape %s", attempt + 1, result)
        except (json.JSONDecodeError, Exception) as exc:
            log.warning("Judge attempt %d failed: %s", attempt + 1, exc)

    return {"success": None, "reasoning": "judge-failed: could not parse response"}
