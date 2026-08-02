"""Shared fixtures.

The repository fixture is a real git repo on disk rather than a mock. The
commit-history code parses actual `git log` and `git show --stat` output, so
faking subprocess would test the fake instead of the parsing.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Make the project importable as `backend.*` / `chunkers.*` when pytest is run
# from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import ingest  # noqa: E402
from backend.ingest import ingest_repo  # noqa: E402
from backend.vectorstore import RepoVectorStore  # noqa: E402

# One file with a deliberate shape: a call chain (login -> normalise_email,
# hash_password), a class with a method and an async method, a closure that
# must not be split out, and a function unrelated to everything else.
SAMPLE_SOURCE = '''"""Authentication entry points."""


def normalise_email(raw):
    """Lowercase and strip an email address."""
    return raw.strip().lower()


def hash_password(raw):
    """Hash a password for storage."""
    return raw[::-1]


def login(email, password):
    """Log a user in."""
    normalise_email(email)
    return hash_password(password)


class SessionStore:
    """Keeps sessions in memory."""

    def __init__(self):
        self.sessions = {}

    def remember(self, user):
        self.sessions[user] = True

    async def forget(self, user):
        self.sessions.pop(user, None)


def outer():
    """Holds a closure that should stay part of this chunk."""
    def inner():
        return 1
    return inner()


def build_report():
    """Billing report. Nothing to do with authentication."""
    return []
'''

COMMIT_MESSAGE = (
    "Add the login flow, with a comma | and a pipe\n\n"
    "Why: we switched to reversal hashing as a placeholder."
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def init_repo(path: Path) -> Path:
    """An initialised git repo with an identity configured, but no commits."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "dev@example.com")
    git(path, "config", "user.name", "Test Dev")
    return path


@pytest.fixture
def empty_repo(tmp_path):
    """A git repo with no commits at all."""
    return init_repo(tmp_path / "empty")


@pytest.fixture
def sample_repo(tmp_path):
    """A small repo with one Python file and one commit."""
    repo = init_repo(tmp_path / "sample")
    (repo / "auth.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
    (repo / "README.md").write_text("Not Python.\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", COMMIT_MESSAGE)
    return repo


@pytest.fixture
def add_commit():
    """Write a file and commit it, for tests that need more than one commit."""

    def _add_commit(repo: Path, filename: str, content: str, message: str) -> None:
        (repo / filename).write_text(content, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)

    return _add_commit


@pytest.fixture
def store(tmp_path):
    """An empty vector store, closed afterwards so the lock is released."""
    store = RepoVectorStore(tmp_path / "qdrant")
    yield store
    store.close()


@pytest.fixture
def fake_clone(sample_repo, tmp_path, monkeypatch):
    """Replace only the network part of cloning, not the URL validation.

    The copy matters because ingest_repo deletes the clone when it is done,
    and the fixture repo has to survive for other assertions. Validation is
    left real so tests can still exercise the rejected-URL path.
    """
    clones = []

    def _clone(repo_url: str) -> Path:
        ingest._validate_repo_url(repo_url)
        destination = tmp_path / f"clone{len(clones)}"
        clones.append(destination)
        return Path(shutil.copytree(sample_repo, destination))

    monkeypatch.setattr(ingest, "clone_repo", _clone)
    return _clone


@pytest.fixture
def indexed_store(store, fake_clone):
    """A store with `sample_repo` fully indexed into it."""
    ingest_repo("https://example.com/sample.git", store)
    return store
