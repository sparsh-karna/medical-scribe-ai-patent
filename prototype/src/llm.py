"""
Shared LLM access for the optional LLM-backed stages (fact extraction and,
for single-channel audio, speaker-role attribution).

Two providers are supported behind one `generate_json()` call:

  - Gemini (google-genai), with the response constrained to a JSON schema
  - Claude (anthropic)

Provider selection: LLM_PROVIDER ("gemini" | "claude") if set, otherwise
whichever API key is present (GEMINI_API_KEY first). Keys are read from
the environment, which src/env.py populates from prototype/.env.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional


class LLMError(RuntimeError):
    """Raised when an LLM stage is misconfigured or returns unusable output."""


def llm_provider() -> Optional[str]:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in ("gemini", "claude"):
        return explicit
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return None


def llm_model_name() -> Optional[str]:
    provider = llm_provider()
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    if provider == "claude":
        return os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
    return None


def parse_json_response(raw: str) -> Any:
    """Parse model JSON, tolerating a surrounding ```json fence."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM returned invalid JSON ({e}); first 200 chars: {text[:200]!r}")


_gemini_client = None
_claude_client = None


def _gemini():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise LLMError("The `google-genai` package is not installed (pip install google-genai).")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("GEMINI_API_KEY not set.")
        # Gemini often returns transient 503 "high demand" / 429 errors;
        # retry those with exponential backoff before giving up.
        _gemini_client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=2.0, max_delay=15.0,
                http_status_codes=[429, 500, 502, 503, 504],
            )),
        )
    return _gemini_client


def _claude():
    global _claude_client
    if _claude_client is None:
        try:
            import anthropic
        except ImportError:
            raise LLMError("The `anthropic` package is not installed (pip install anthropic).")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError("ANTHROPIC_API_KEY not set.")
        _claude_client = anthropic.Anthropic()
    return _claude_client


def _generate_gemini(system: str, user: str, schema: Dict[str, Any], max_tokens: int) -> str:
    from google.genai import errors, types

    client = _gemini()
    primary = llm_model_name()
    fallbacks = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.7-flash")
    models = [primary] + [m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != primary]
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        max_output_tokens=max_tokens,
    )
    failures = []
    for model in models:
        try:
            resp = client.models.generate_content(model=model, contents=user, config=config)
        except errors.APIError as e:
            failures.append(f"{model}: {e.code} {e.status}")
            if e.code in (429, 500, 502, 503, 504):
                continue  # overloaded -> try the next model
            raise LLMError(f"Gemini API call failed ({model}): {e}")
        except Exception as e:
            raise LLMError(f"Gemini API call failed ({model}): {e}")
        finish = resp.candidates[0].finish_reason if resp.candidates else None
        if finish is not None and finish.name == "MAX_TOKENS":
            raise LLMError(f"Gemini output was truncated ({model}, max_output_tokens reached).")
        if not resp.text:
            raise LLMError(f"Gemini returned no text ({model}, finish reason: {finish}).")
        return resp.text
    raise LLMError("All Gemini models are unavailable right now, try again shortly ("
                   + "; ".join(failures) + ").")


def _generate_claude(system: str, user: str, max_tokens: int) -> str:
    client = _claude()
    try:
        resp = client.messages.create(
            model=llm_model_name(),
            max_tokens=max_tokens,
            system=system + " Output JSON only, no prose.",
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        raise LLMError(f"Claude API call failed: {e}")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Claude output was truncated (max_tokens reached).")
    return "".join(block.text for block in resp.content if block.type == "text")


def generate_json(system: str, user: str, schema: Dict[str, Any], max_tokens: int = 16000) -> Any:
    """Run one LLM call and return the parsed JSON response."""
    provider = llm_provider()
    if provider == "gemini":
        raw = _generate_gemini(system, user, schema, max_tokens)
    elif provider == "claude":
        raw = _generate_claude(system, user, max_tokens)
    else:
        raise LLMError("No LLM is configured: set GEMINI_API_KEY or ANTHROPIC_API_KEY "
                       "(e.g. in prototype/.env).")
    return parse_json_response(raw)


def format_transcript(segments: List[Dict[str, Any]]) -> str:
    return "\n".join(f"[{s['id']}] {s['speaker']}: {s['text']}" for s in segments)
