"""Settings for the whole app, in one place.

These are plain module-level constants rather than a settings class: nothing
here holds state or needs validation, and a constant is easier to find than an
attribute on an object that has to be constructed first. The two values that
genuinely vary per deployment (the API key and the port) are read from the
environment.
"""

import os
import tempfile
from pathlib import Path

# --- paths -----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The frontend is a Vite build, so this points at the compiled output rather
# than the source. It only exists after `npm run build`; main.py checks before
# mounting it, so the API still runs from a clean checkout.
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"

# Every session gets its own on-disk Qdrant directory under here. Using the
# system temp dir means indexed data does not survive a restart on hosts with
# an ephemeral filesystem - the same limitation as the in-memory session dict.
STORAGE_ROOT = Path(tempfile.gettempdir()) / "repo_onboarder"

# --- qdrant collections ----------------------------------------------------

# Code and commit messages use different vocabularies, so they get separate
# collections *and* separate embedder instances. See vectorstore.py.
CODE_COLLECTION = "code_chunks"
COMMIT_COLLECTION = "commit_chunks"

# --- embeddings ------------------------------------------------------------

# TF-IDF produces one vector dimension per vocabulary term, and Qdrant needs a
# fixed vector size when the collection is created. Capping the vocabulary
# keeps vectors small enough to store comfortably for a demo-sized repo.
TFIDF_MAX_FEATURES = 4096

# --- retrieval -------------------------------------------------------------

DEFAULT_TOP_K = 5

# Call-graph expansion looks at the single best code hit and follows at most
# this many of the functions it calls. One hop only - no recursion - so the
# context block stays bounded however deep the real call chain goes.
MAX_CALL_EXPANSIONS = 3

# --- ingestion -------------------------------------------------------------

CLONE_TIMEOUT_SECONDS = 300
GIT_COMMAND_TIMEOUT_SECONDS = 60

# History extraction runs one `git show --stat` per commit, so it is linear in
# commit count. This cap keeps indexing fast on large repos; raise it if you
# need deeper history and can afford the wait.
MAX_COMMITS = 500

# Directories that never contain source worth indexing.
SKIP_DIRECTORIES = {".git", "__pycache__", "venv", ".venv", "node_modules"}

# --- answer synthesis ------------------------------------------------------

# The model is reached over the OpenAI-compatible chat-completions endpoint,
# which Ollama, Groq, Google Gemini and OpenRouter all speak. That makes the
# provider three environment variables rather than a code change: a local
# model while developing, a free hosted one once deployed, same code path.
#
#   local (default)  http://localhost:11434/v1                          (Ollama, no key)
#   Groq             https://api.groq.com/openai/v1
#   Gemini           https://generativelanguage.googleapis.com/v1beta/openai
#   OpenRouter       https://openrouter.ai/api/v1
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")

# Must match the provider: "llama3.2:3b" for Ollama, "llama-3.3-70b-versatile"
# for Groq, "gemini-3.6-flash" for Gemini, and so on.
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.2:3b")

# Empty by default, because a local Ollama server does not check it. Hosted
# providers need one; it is only ever read from the environment.
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")

# Answers are meant to be a few sentences with citations, not an essay.
LLM_MAX_TOKENS = 800

# Low, because the answer should stay close to the retrieved context. Not zero:
# greedy decoding tends to produce repetitive text on smaller models.
LLM_TEMPERATURE = 0.2

# A stalled request would otherwise hold the HTTP request open indefinitely.
LLM_TIMEOUT_SECONDS = 120

# --- server ----------------------------------------------------------------

PORT = int(os.environ.get("PORT", "8000"))


def _split_origins(raw: str) -> list[str]:
    """Parse a comma-separated origin list, ignoring blanks and stray spaces."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# Only needed when the frontend is hosted somewhere other than this API. A
# browser refuses a cross-origin request unless the API says that origin is
# allowed, and the origin must match exactly - scheme and host, no trailing
# slash, e.g. "https://faizz.github.io,https://repo-onboarder.netlify.app".
#
# Empty by default, which is correct when one process serves both.
ALLOWED_ORIGINS = _split_origins(os.environ.get("ALLOWED_ORIGINS", ""))
