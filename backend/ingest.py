"""Clone a repository, chunk it two ways, and index both into the store.

This module owns the whole ingestion sequence so nothing else has to know the
order of operations. The one subtlety worth reading closely is the pair of
_*_chunk_text() functions: what gets embedded is deliberately not the same as
what gets stored.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from backend.config import (
    CLONE_TIMEOUT_SECONDS,
    CODE_COLLECTION,
    COMMIT_COLLECTION,
    MAX_COMMITS,
)
from backend.vectorstore import RepoVectorStore
from chunkers.git_history import CommitChunk, get_commit_history
from chunkers.python_chunker import CodeChunk, chunk_repo


def _validate_repo_url(repo_url: str) -> None:
    """Reject anything that is not a plain http(s) URL.

    This is a small check with an outsized payoff: it keeps a local path or a
    file:// URL from being cloned, and it stops a string starting with "-"
    from reaching git, where it would be read as a command-line flag.
    """
    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"Expected an http(s) repository URL, got: {repo_url!r}"
        )


def _remove_clone(path: Path) -> None:
    """Delete a cloned repository directory.

    Git marks files under .git read-only, which makes a plain rmtree fail on
    Windows, so clear the flag and retry. Failing to clean up a temp directory
    is never worth failing an otherwise successful index over.
    """

    def clear_readonly(func, target, exc):  # noqa: ANN001 - shutil callback
        os.chmod(target, stat.S_IWRITE)
        func(target)

    try:
        shutil.rmtree(path, onexc=clear_readonly)
    except OSError:
        pass


def clone_repo(repo_url: str) -> Path:
    """Clone `repo_url` into a fresh temp directory and return its path.

    Deliberately not a shallow clone: commit history is half of what this
    system indexes, and --depth 1 would silently gut the commits route.
    """
    _validate_repo_url(repo_url)
    destination = Path(tempfile.mkdtemp(prefix="repo_onboarder_clone_"))

    try:
        result = subprocess.run(
            ["git", "clone", repo_url, str(destination)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLONE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        _remove_clone(destination)
        raise RuntimeError("git is not installed or not on PATH") from None
    except subprocess.TimeoutExpired:
        _remove_clone(destination)
        raise RuntimeError(
            f"Cloning timed out after {CLONE_TIMEOUT_SECONDS}s"
        ) from None

    if result.returncode != 0:
        _remove_clone(destination)
        # git's own stderr says useful things like "repository not found",
        # and this string is what the client eventually displays.
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

    return destination


def _code_chunk_text(chunk: CodeChunk) -> str:
    """The text a code chunk is embedded as.

    The signature line and docstring come first, ahead of the raw body, so the
    vector leans toward how a person would describe the code rather than
    toward whichever identifiers happen to repeat most inside it.
    """
    parts = [f"{chunk.kind} {chunk.name}"]
    if chunk.parent:
        parts.append(f"in class {chunk.parent}")
    if chunk.docstring:
        parts.append(chunk.docstring)
    parts.append(chunk.source)
    return "\n".join(parts)


def _commit_chunk_text(commit: CommitChunk) -> str:
    """The text a commit is embedded as.

    Message plus changed filenames. Author and date stay out of the embedding
    on purpose - they are needed for the citation, but a lexical index would
    let a prolific committer's name match half the history.
    """
    parts = [commit.message]
    if commit.files_changed:
        parts.append(" ".join(commit.files_changed))
    return "\n".join(parts)


def ingest_repo(
    repo_url: str,
    store: RepoVectorStore,
    max_commits: int = MAX_COMMITS,
) -> dict[str, int]:
    """Clone, chunk, and index a repository. Returns stats for the API.

    The two extraction passes are independent - neither reads the other's
    output - and each lands in its own collection with its own embedder.
    """
    repo_path = clone_repo(repo_url)
    try:
        code_chunks, files_seen = chunk_repo(repo_path)
        commits = get_commit_history(repo_path, max_commits=max_commits)

        # asdict() keeps every field of the chunk in the payload, because the
        # citation is built from those fields later. Only the *embedded* text
        # is trimmed and reordered.
        code_indexed = store.index(
            CODE_COLLECTION,
            [_code_chunk_text(chunk) for chunk in code_chunks],
            [asdict(chunk) for chunk in code_chunks],
        )
        commit_indexed = store.index(
            COMMIT_COLLECTION,
            [_commit_chunk_text(commit) for commit in commits],
            [asdict(commit) for commit in commits],
        )
    finally:
        # The working tree was only needed to produce chunks; everything the
        # query path reads now lives in the payloads.
        _remove_clone(repo_path)

    return {
        "code_chunks_indexed": code_indexed,
        "commit_chunks_indexed": commit_indexed,
        "files_seen": files_seen,
    }
