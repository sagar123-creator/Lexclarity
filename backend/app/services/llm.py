"""
LLM provider wrapper.

Every other service (summarizer, risk_analyzer, chatbot) calls `complete()`
and never talks to a provider SDK directly. This keeps the model swappable
through LLM_PROVIDER / LLM_MODEL / LLM_API_KEY alone.
"""
import json
import re

from app.config import settings


class LLMError(Exception):
    pass


def complete(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
    """Send one turn to the configured LLM and return the text response."""
    if not settings.LLM_API_KEY:
        raise LLMError(
            "LLM_API_KEY is not set. Add it to your .env file — see .env.example. "
            "LexClarity needs an LLM to summarize documents and power the chatbot."
        )

    max_tokens = max_tokens or settings.LLM_MAX_TOKENS

    if settings.LLM_PROVIDER == "anthropic":
        return _complete_anthropic(system_prompt, user_prompt, max_tokens)
    if settings.LLM_PROVIDER == "openai":
        return _complete_openai(system_prompt, user_prompt, max_tokens)
    if settings.LLM_PROVIDER == "gemini":
        return _complete_gemini(system_prompt, user_prompt, max_tokens)
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")


def _complete_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("The 'anthropic' package is not installed.") from e

    try:
        client = anthropic.Anthropic(api_key=settings.LLM_API_KEY)
        response = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        raise LLMError(f"LLM request failed: {e}") from e


def _complete_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("The 'openai' package is not installed.") from e

    try:
        client = OpenAI(api_key=settings.LLM_API_KEY)
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise LLMError(f"LLM request failed: {e}") from e


def _complete_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise LLMError("The 'google-genai' package is not installed. Run `pip install google-genai`.") from e

    try:
        client = genai.Client(api_key=settings.LLM_API_KEY)
        response = client.models.generate_content(
            model=settings.LLM_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text or ""
    except Exception as e:
        raise LLMError(f"LLM request failed: {e}") from e


def complete_json(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> dict | list:
    """Ask the LLM for strict JSON and parse it, tolerating markdown fences."""
    raw = complete(
        system_prompt + "\n\nRespond with ONLY valid JSON. No markdown fences, no preamble, no commentary.",
        user_prompt,
        max_tokens,
    )
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"LLM did not return valid JSON: {e}\nRaw response: {raw[:500]}")
