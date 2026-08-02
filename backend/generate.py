"""Turn retrieved context into a written answer.

The model is called over the OpenAI-compatible /chat/completions endpoint.
Ollama, Groq, Google Gemini and OpenRouter all speak it, so which model
answers is a deployment-time setting rather than a code change: a local model
on your machine, a free hosted one on a deployed instance, one code path.

Synthesis stays optional either way. If the model is unreachable, rejects the
request, or answers with something unexpected, the retrieved context is
returned with its citations intact rather than the request failing - retrieval
has already succeeded by the time this code runs.
"""

from __future__ import annotations

import httpx

from backend.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
)

SYSTEM_PROMPT = """You are helping a developer get oriented in an unfamiliar codebase.

Answer only from the context provided in the user's message. It was retrieved \
from the repository they are asking about.

If the context does not contain the answer, say so plainly. Do not fill the gap \
with general knowledge about how projects like this usually work - a confident \
guess is worse than "the retrieved context doesn't cover this".

Always cite your source: file:line for code, the short commit hash for history.

Keep it short. This is a chat reply, not a report."""


def _build_prompt(question: str, context: str) -> str:
    return f"Question about this repository:\n{question}\n\nRetrieved context:\n{context}"


def _context_with_note(reason: str, context: str) -> str:
    """Return the cited context, explaining why it was not summarised.

    The note leads with something the reader can act on, because the usual
    cause is a setup step that has not been done yet.
    """
    return f"Note: {reason}\n\n{context}"


def synthesize_answer(question: str, context: str) -> str:
    """Write a grounded answer, or return the cited context if that is not possible."""
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    payload = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(question, context)},
        ],
    }

    # rstrip so the setting works whether or not it was given a trailing slash.
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"

    try:
        response = httpx.post(
            url, json=payload, headers=headers, timeout=LLM_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # The provider answered, but refused. 401/403 almost always means the
        # key is missing or wrong; 404 usually means the model name is not one
        # this provider serves.
        return _context_with_note(
            f"the model provider returned HTTP {exc.response.status_code} for "
            f"model {LLM_MODEL!r}. Check LLM_API_KEY and LLM_MODEL.",
            context,
        )
    except httpx.RequestError as exc:
        return _context_with_note(
            f"could not reach the model at {LLM_BASE_URL} ({exc}). If you are "
            "running locally, start Ollama; if deployed, check LLM_BASE_URL.",
            context,
        )

    try:
        answer = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        # Not a chat-completions response - usually LLM_BASE_URL pointing at
        # something that is not an OpenAI-compatible endpoint.
        return _context_with_note(
            f"the response from {LLM_BASE_URL} was not in chat-completions "
            "format. Check that LLM_BASE_URL ends with the OpenAI-compatible "
            "path (for Ollama that is /v1).",
            context,
        )

    return (answer or "").strip() or context
