"""The four HTTP routes, driven through FastAPI's TestClient.

TestClient runs background tasks inline once the response is returned, so a
poll immediately after POST /index already sees the finished state.
"""

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.main import app


@pytest.fixture
def client(tmp_path, fake_clone, monkeypatch):
    """A client whose indexing clones from the local fixture repo."""
    monkeypatch.setattr(main, "STORAGE_ROOT", tmp_path / "sessions")
    # Synthesis is covered by test_generate.py. Stubbing it here keeps these
    # tests about the HTTP layer, and independent of whether a local model
    # happens to be running on this machine.
    monkeypatch.setattr(main, "synthesize_answer", lambda question, context: context)

    main.SESSIONS.clear()
    yield TestClient(app)

    for session in main.SESSIONS.values():
        if session.store is not None:
            session.store.close()
    main.SESSIONS.clear()


def index_a_repo(client) -> str:
    response = client.post("/index", json={"repo_url": "https://example.com/sample.git"})
    return response.json()["session_id"]


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_returns_immediately_with_a_session_id(client):
    response = client.post("/index", json={"repo_url": "https://example.com/sample.git"})

    assert response.status_code == 200
    assert response.json()["status"] == "indexing"
    assert response.json()["session_id"]


def test_status_of_an_unknown_session_is_404(client):
    assert client.get("/index/nope").status_code == 404


def test_chat_on_an_unknown_session_is_404(client):
    response = client.post("/chat", json={"session_id": "nope", "question": "hi"})

    assert response.status_code == 404


def test_chat_before_indexing_finishes_is_400(client):
    main.SESSIONS["pending"] = main.Session()

    response = client.post("/chat", json={"session_id": "pending", "question": "hi"})

    assert response.status_code == 400


def test_indexing_reports_stats_when_ready(client):
    session_id = index_a_repo(client)

    body = client.get(f"/index/{session_id}").json()

    assert body["status"] == "ready"
    assert body["error"] is None
    assert body["stats"] == {
        # module docstring, 6 functions, 1 class, 2 methods
        "code_chunks_indexed": 10,
        "commit_chunks_indexed": 1,
        "files_seen": 1,
    }


def test_a_bad_url_fails_the_session_and_reports_why(client):
    session_id = client.post("/index", json={"repo_url": "not-a-url"}).json()["session_id"]

    body = client.get(f"/index/{session_id}").json()

    assert body["status"] == "failed"
    assert body["stats"] is None
    assert "http(s)" in body["error"]


def test_chat_on_a_failed_session_is_400(client):
    session_id = client.post("/index", json={"repo_url": "not-a-url"}).json()["session_id"]

    response = client.post("/chat", json={"session_id": session_id, "question": "hi"})

    assert response.status_code == 400


@pytest.mark.parametrize(
    "question, expected_route",
    [
        ("where is the password hash done", "code"),
        ("why did we switch hashing", "commits"),
        ("how does login work", "both"),
    ],
)
def test_chat_reports_the_route_it_used(client, question, expected_route):
    session_id = index_a_repo(client)

    body = client.post(
        "/chat", json={"session_id": session_id, "question": question}
    ).json()

    assert body["route"] == expected_route


def test_chat_response_carries_per_collection_hit_counts(client):
    session_id = index_a_repo(client)

    body = client.post(
        "/chat", json={"session_id": session_id, "question": "why did we switch hashing"}
    ).json()

    assert set(body) == {"answer", "route", "code_hits", "commit_hits"}
    assert body["code_hits"] == 0
    assert body["commit_hits"] == 1


def test_the_answer_is_built_from_the_cited_context(client):
    session_id = index_a_repo(client)

    body = client.post(
        "/chat", json={"session_id": session_id, "question": "where is login"}
    ).json()

    assert "auth.py:" in body["answer"]
    assert "```python" in body["answer"]


def test_questions_are_answered_independently(client):
    # No server-side conversation memory: the same question twice gives the
    # same answer, uninfluenced by anything asked in between.
    session_id = index_a_repo(client)
    ask = lambda q: client.post("/chat", json={"session_id": session_id, "question": q}).json()

    first = ask("where is login")
    ask("why did we switch hashing")
    second = ask("where is login")

    assert first == second


def test_no_cors_header_when_no_origins_are_configured(client):
    # With one process serving both, ALLOWED_ORIGINS is empty and the browser
    # gets no permission to call this API from anywhere else. Opening that up
    # should require setting the variable, never happen by default.
    response = client.get("/health", headers={"Origin": "https://somewhere.test"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "x", "question": ""},
        {"session_id": "x", "question": "hi", "top_k": 0},
        {"session_id": "x", "question": "hi", "top_k": 999},
        {"question": "missing session id"},
    ],
)
def test_invalid_chat_requests_are_rejected(client, body):
    assert client.post("/chat", json=body).status_code == 422
