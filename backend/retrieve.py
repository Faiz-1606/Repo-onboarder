

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.config import (
    CODE_COLLECTION,
    COMMIT_COLLECTION,
    DEFAULT_TOP_K,
    MAX_CALL_EXPANSIONS,
)
from backend.models import Route
from backend.vectorstore import RepoVectorStore, SearchHit


WHY_PATTERNS = re.compile(
    r"\b(why|decided|decision|reason|history|changed|switched|chose|rationale)\b",
    re.IGNORECASE,
)


WHERE_PATTERNS = re.compile(
    r"\b(where|which file|find|locate|show me)\b",
    re.IGNORECASE,
)


def classify_query(question: str) -> Route:
    """Pick which collection(s) to search, using only the question's wording.

    A regex is free and adds no latency, where an LLM classifier would mean a
    network round-trip before search even starts.

    Both ambiguous cases resolve to "both" on purpose:
      - matching neither pattern set means the phrasing is one this heuristic
        was not written for, so check everything rather than guess;
      - matching both means the question really is asking about a location
        *and* a change, and picking a winner would drop a real source.
    """
    wants_why = bool(WHY_PATTERNS.search(question))
    wants_where = bool(WHERE_PATTERNS.search(question))

    if wants_why and not wants_where:
        return "commits"
    if wants_where and not wants_why:
        return "code"
    return "both"


def expand_via_calls(
    store: RepoVectorStore,
    code_hits: list[SearchHit],
    max_expansions: int = MAX_CALL_EXPANSIONS,
) -> list[SearchHit]:
    """Pull in the functions the best code match directly calls.

    One hop, from one chunk, capped at `max_expansions` names. The bound is
    the design: without it, following a call chain could drag in most of the
    repository, and the context block has to stay a predictable size no matter
    how deep the real chain goes.
    """
    if not code_hits:
        return []

    best = code_hits[0]
    called_names = best.payload.get("calls", [])[:max_expansions]

    already_returned = {hit.payload.get("chunk_id") for hit in code_hits}
    expanded: list[SearchHit] = []

    for name in called_names:
       
        matches = store.search(
            CODE_COLLECTION,
            name,
            top_k=1,
            filter_field="name",
            filter_value=name,
        )
        for hit in matches:
            chunk_id = hit.payload.get("chunk_id")
            if chunk_id in already_returned:
                continue
            already_returned.add(chunk_id)
            expanded.append(hit)

    return expanded


def _format_code_hit(payload: dict) -> str:
    """One code chunk as a cited, fenced block."""
    location = f"{payload['file_path']}:{payload['start_line']}-{payload['end_line']}"
    heading = f"{payload['kind']} {payload['name']}"
    if payload.get("parent"):
        heading += f" (in class {payload['parent']})"
    return f"{location} - {heading}\n```python\n{payload['source']}\n```"


def _format_commit_hit(payload: dict) -> str:
    """One commit as a bullet: short hash, date, author, message, files."""
    short_hash = payload["commit_hash"][:8]
    date = payload["date"][:10]  # the YYYY-MM-DD part of the ISO timestamp

    lines = [f"- {short_hash} ({date}, {payload['author']})"]
   
    lines.extend(f"  {line}".rstrip() for line in payload["message"].splitlines())
    if payload.get("files_changed"):
        lines.append(f"  files: {', '.join(payload['files_changed'])}")
    return "\n".join(lines)


def format_context_for_llm(
    code_hits: list[SearchHit],
    commit_hits: list[SearchHit],
) -> str:
    """Turn search results into a cited markdown block.

    No model calls happen here - it is string formatting and nothing else.
    That is deliberate: with no API key configured, this text is returned to
    the client directly and is a perfectly usable answer on its own.
    """
    sections: list[str] = []

    if code_hits:
        blocks = [_format_code_hit(hit.payload) for hit in code_hits]
        sections.append("## Code\n\n" + "\n\n".join(blocks))

    if commit_hits:
        blocks = [_format_commit_hit(hit.payload) for hit in commit_hits]
        sections.append("## Commit history\n\n" + "\n\n".join(blocks))

    if not sections:
        
        return "No matching code or commits were found in this repository."

    return "\n\n".join(sections)


@dataclass
class RetrievalResult:
    """Everything the chat endpoint needs, apart from the written answer."""

    route: Route
    context: str
    code_hits: int
    commit_hits: int


def retrieve_context(
    store: RepoVectorStore,
    question: str,
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalResult:
    """Route the question, search the chosen collection(s), format the result."""
    route = classify_query(question)
    code_hits: list[SearchHit] = []
    commit_hits: list[SearchHit] = []

    if route in ("code", "both"):
        code_hits = store.search(CODE_COLLECTION, question, top_k=top_k)
       
        code_hits = code_hits + expand_via_calls(store, code_hits)

    if route in ("commits", "both"):
        commit_hits = store.search(COMMIT_COLLECTION, question, top_k=top_k)

    return RetrievalResult(
        route=route,
        context=format_context_for_llm(code_hits, commit_hits),
        code_hits=len(code_hits),
        commit_hits=len(commit_hits),
    )
