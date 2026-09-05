

import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"

STORAGE_ROOT = Path(tempfile.gettempdir()) / "repo_onboarder"

CODE_COLLECTION = "code_chunks"
COMMIT_COLLECTION = "commit_chunks"

# "fastembed" runs a real sentence-embedding model locally through ONNX
# Runtime - no API key, no per-question cost, and no PyTorch. "tfidf" is the
# original lexical fallback, kept because it needs no model download and very
# little memory.
EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "fastembed")

# 384 dimensions, ~67 MB on disk - the smallest model available, and strong
# for its size.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Peak memory while embedding is dominated by the ONNX inference arena, and it
# scales with batch size: measured ~195 MB at 8 against ~430 MB at the library
# default. Small batches are not slower here - with one thread there is less
# contention on a shared vCPU, which made it faster as well as lighter.
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "8"))
EMBEDDING_THREADS = int(os.environ.get("EMBEDDING_THREADS", "1"))

# Where model weights are cached. The Dockerfile sets this and warms it at
# build time, so a deployed instance never downloads on the first question.
EMBEDDING_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR") or None

# A relevance floor for semantic search. Below it a result is treated as "not
# really a match" rather than being handed to the model as context.
#
# Measured on pypa/sampleproject: questions the repo can answer score around
# 0.72, questions it cannot ("how do I bake a chocolate cake") score 0.48-0.55,
# so 0.60 sits in the gap.
#
# This applies to embedding models only. TF-IDF sets its own floor to zero -
# see vectorstore.py, where each embedder carries the threshold for its own
# score scale.
SEMANTIC_SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.6"))

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
