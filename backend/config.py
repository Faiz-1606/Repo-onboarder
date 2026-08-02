

import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"

STORAGE_ROOT = Path(tempfile.gettempdir()) / "repo_onboarder"

CODE_COLLECTION = "code_chunks"
COMMIT_COLLECTION = "commit_chunks"

TFIDF_MAX_FEATURES = 4096


DEFAULT_TOP_K = 5

MAX_CALL_EXPANSIONS = 3


CLONE_TIMEOUT_SECONDS = 300
GIT_COMMAND_TIMEOUT_SECONDS = 60

MAX_COMMITS = 500

SKIP_DIRECTORIES = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    "coverage",
}

MAX_SOURCE_FILE_BYTES = 512_000

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.2:3b")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")

LLM_MAX_TOKENS = 800

LLM_TEMPERATURE = 0.2

LLM_TIMEOUT_SECONDS = 120


PORT = int(os.environ.get("PORT", "8000"))


def _split_origins(raw: str) -> list[str]:
    """Parse a comma-separated origin list, ignoring blanks and stray spaces."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


ALLOWED_ORIGINS = _split_origins(os.environ.get("ALLOWED_ORIGINS", ""))
