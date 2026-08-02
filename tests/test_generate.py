"""Answer synthesis, and the fallbacks that keep it optional.

Every failure mode has to return the cited context rather than raise -
retrieval has already succeeded by the time this code runs.
"""

import httpx
import pytest

from backend import generate
from backend.generate import SYSTEM_PROMPT, synthesize_answer

CONTEXT = "## Code\n\nauth.py:19-24 - function login\n```python\ndef login(): ...\n```"
QUESTION = "where is login handled"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://test/chat/completions"),
                response=httpx.Response(self.status_code),
            )


@pytest.fixture
def fake_post(monkeypatch):
    """Stand in for the HTTP call and capture what was sent."""
    captured = {}

    def _install(answer="ok", status_code=200, payload=None, raises=None):
        if payload is None:
            payload = {"choices": [{"message": {"content": answer}}]}

        def _post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            if raises is not None:
                raise raises
            return FakeResponse(payload, status_code)

        monkeypatch.setattr(generate.httpx, "post", _post)
        return captured

    return _install


def test_returns_the_models_answer(fake_post):
    fake_post(answer="Login is handled in `auth.py:19-24`.")

    assert synthesize_answer(QUESTION, CONTEXT) == "Login is handled in `auth.py:19-24`."


def test_posts_to_the_chat_completions_endpoint(fake_post):
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    assert captured["url"] == f"{generate.LLM_BASE_URL.rstrip('/')}/chat/completions"


def test_a_trailing_slash_in_the_base_url_is_tolerated(fake_post, monkeypatch):
    # Google publishes its base URL with a trailing slash.
    monkeypatch.setattr(generate, "LLM_BASE_URL", "https://example.test/v1/")
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    assert captured["url"] == "https://example.test/v1/chat/completions"


def test_sends_the_system_prompt_and_the_retrieved_context(fake_post):
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    system, user = captured["json"]["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert QUESTION in user["content"]
    assert CONTEXT in user["content"]


def test_uses_the_configured_model_and_limits(fake_post):
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    assert captured["json"]["model"] == generate.LLM_MODEL
    assert captured["json"]["max_tokens"] == generate.LLM_MAX_TOKENS
    assert captured["json"]["temperature"] == generate.LLM_TEMPERATURE


def test_sends_a_bearer_token_when_a_key_is_configured(fake_post, monkeypatch):
    monkeypatch.setattr(generate, "LLM_API_KEY", "test-key")
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_sends_no_auth_header_for_a_local_model(fake_post, monkeypatch):
    # A local Ollama server does not check it, and sending an empty bearer
    # token upsets some providers.
    monkeypatch.setattr(generate, "LLM_API_KEY", "")
    captured = fake_post()

    synthesize_answer(QUESTION, CONTEXT)

    assert "Authorization" not in captured["headers"]


def test_an_empty_answer_falls_back_to_the_context(fake_post):
    fake_post(answer="   ")

    assert synthesize_answer(QUESTION, CONTEXT) == CONTEXT


def test_a_null_answer_falls_back_to_the_context(fake_post):
    fake_post(answer=None)

    assert synthesize_answer(QUESTION, CONTEXT) == CONTEXT


def test_a_rejected_request_names_the_settings_to_check(fake_post):
    fake_post(status_code=401)

    answer = synthesize_answer(QUESTION, CONTEXT)

    assert "HTTP 401" in answer
    assert "LLM_API_KEY" in answer
    assert CONTEXT in answer


def test_an_unexpected_response_shape_falls_back(fake_post):
    # e.g. LLM_BASE_URL pointing at something that is not chat-completions.
    fake_post(payload={"unexpected": True})

    answer = synthesize_answer(QUESTION, CONTEXT)

    assert "chat-completions format" in answer
    assert CONTEXT in answer


def test_a_connection_failure_falls_back(fake_post):
    fake_post(raises=httpx.ConnectError("connection refused"))

    answer = synthesize_answer(QUESTION, CONTEXT)

    assert "could not reach the model" in answer
    assert CONTEXT in answer


def test_an_unreachable_endpoint_returns_the_context(monkeypatch):
    # A real request against a dead port - no mocking, and independent of
    # whether anything happens to be listening on this machine.
    monkeypatch.setattr(generate, "LLM_BASE_URL", "http://127.0.0.1:1/v1")

    answer = synthesize_answer(QUESTION, CONTEXT)

    assert "could not reach the model" in answer
    assert CONTEXT in answer


def test_citations_survive_every_fallback(monkeypatch):
    # The whole point of the fallbacks: the citation is never lost.
    monkeypatch.setattr(generate, "LLM_BASE_URL", "http://127.0.0.1:1/v1")

    assert "auth.py:19-24" in synthesize_answer(QUESTION, CONTEXT)
