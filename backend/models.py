"""Request and response schemas for the four HTTP routes.

Only API-facing shapes live here. CodeChunk and CommitChunk are dataclasses
that belong with the code that produces them (chunkers/), not with the wire
format - they are never serialised to a client directly.
"""

from typing import Literal

from pydantic import BaseModel, Field

from backend.config import DEFAULT_TOP_K

# Defining these vocabularies once means retrieve.py and main.py cannot drift
# apart on what a valid route or status string is.
Route = Literal["code", "commits", "both"]
SessionStatus = Literal["indexing", "ready", "failed"]


class IndexRequest(BaseModel):
    repo_url: str = Field(min_length=1)


class IndexResponse(BaseModel):
    session_id: str
    status: SessionStatus


class IndexStats(BaseModel):
    code_chunks_indexed: int
    commit_chunks_indexed: int
    files_seen: int


class IndexStatusResponse(BaseModel):
    status: SessionStatus
    # Both are null until indexing finishes; exactly one is populated after.
    stats: IndexStats | None = None
    error: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=1)
    # Bounded so a client cannot ask for a context block big enough to blow
    # past the model's context window.
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=20)


class ChatResponse(BaseModel):
    answer: str
    # Surfacing the route and the per-collection hit counts is what makes the
    # routing decision visible to the person asking, instead of a black box.
    route: Route
    code_hits: int
    commit_hits: int


class HealthResponse(BaseModel):
    status: str
