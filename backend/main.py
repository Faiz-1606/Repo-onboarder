

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import ALLOWED_ORIGINS, FRONTEND_DIR, PORT, STORAGE_ROOT
from backend.generate import synthesize_answer
from backend.ingest import ingest_repo
from backend.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    IndexStats,
    IndexStatusResponse,
    SessionStatus,
)
from backend.retrieve import retrieve_context
from backend.vectorstore import RepoVectorStore

app = FastAPI(
    title="Repo Onboarding Assistant",
    description="Ask questions about an unfamiliar codebase, answered from its "
    "code and its commit history.",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@dataclass
class Session:
    """One indexed repository: how it is doing, and what it produced."""

    status: SessionStatus = "indexing"
    store: RepoVectorStore | None = None
    stats: IndexStats | None = None
    error: str | None = None



SESSIONS: dict[str, Session] = {}


def run_indexing(session_id: str, repo_url: str) -> None:
    """Background worker: clone, chunk, index, then flip the session to ready."""
    session = SESSIONS[session_id]
    store: RepoVectorStore | None = None

    try:
        store = RepoVectorStore(STORAGE_ROOT / session_id)
        stats = ingest_repo(repo_url, store)

        
        session.store = store
        session.stats = IndexStats(**stats)
        session.status = "ready"
    except Exception as exc:
        if store is not None:
            
            store.close()
        session.error = str(exc)
        session.status = "failed"


@app.post("/index", response_model=IndexResponse)
def start_indexing(
    request: IndexRequest,
    background_tasks: BackgroundTasks,
) -> IndexResponse:
    """Begin indexing a repository. Returns straight away."""
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = Session()
    background_tasks.add_task(run_indexing, session_id, request.repo_url)
    return IndexResponse(session_id=session_id, status="indexing")


@app.get("/index/{session_id}", response_model=IndexStatusResponse)
def indexing_status(session_id: str) -> IndexStatusResponse:
    """Poll target. Carries stats once ready, or the exception text if it failed."""
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    return IndexStatusResponse(
        status=session.status,
        stats=session.stats,
        error=session.error,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Answer one question. Each call is independent - no conversation memory."""
    session = SESSIONS.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if session.status != "ready" or session.store is None:
        raise HTTPException(
            status_code=400,
            detail=f"Session is not ready to answer questions (status: {session.status})",
        )

    result = retrieve_context(session.store, request.question, top_k=request.top_k)
    answer = synthesize_answer(request.question, result.context)

    return ChatResponse(
        answer=answer,
        route=result.route,
        code_hits=result.code_hits,
        commit_hits=result.commit_hits,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok")



if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
