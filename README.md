# Repo Onboarding Assistant

Ask questions about an unfamiliar codebase and get answers with citations —
either a `file:line` in the source, or the commit that explains why something
is the way it is.

**Stack:** FastAPI · Qdrant · scikit-learn · tree-sitter · React + TypeScript + Tailwind

Embeddings are computed locally with scikit-learn — no model downloads, no
embedding API. Answers are written by any OpenAI-compatible chat model, which
means a local model while you develop and a free hosted one once deployed,
selected by environment variable rather than by changing code.

---

## The idea

Most "chat with your codebase" tools embed source files as flat text and run
similarity search over them — the same technique used for chatting with a PDF.
That works reasonably well for **"where"** questions, because the answer really
does live in the code.

It fails for **"why"** questions. *"Why do we retry three times before failing
over?"* almost never has its answer inside the code. That reasoning lives in a
commit message — an artifact a pure code-embedding system never indexes at all.

So this system treats a repository as **two separate knowledge sources**, and
decides which one to search *before* retrieving anything:

| Question | Route | Searched |
|---|---|---|
| "Where is auth handled?" | `code` | code chunks |
| "Why did we switch to JWT?" | `commits` | commit history |
| "How does the build process work?" | `both` | both collections |

Every answer reports the route it took and how many hits came from each
collection, so the routing decision is visible rather than a black box.

---

## Quickstart

Requires **Python 3.12** and **git** on your PATH.

**API only** — enough to use the whole system through `/docs` or curl:

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

**With the UI**, two terminals. The Vite dev server proxies API routes to
port 8000, so both halves stay same-origin while you work:

```bash
uvicorn backend.main:app --reload      # terminal 1
cd frontend && npm install && npm run dev   # terminal 2 -> localhost:5173
```

**One process**, the way it is deployed — build the frontend, and FastAPI
serves it from the root route:

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn backend.main:app
```

Then open <http://localhost:8000> and paste a public repository URL, for
example `https://github.com/pypa/sampleproject.git`. Indexing that repo takes
about 10 seconds and produces 7 code chunks and 197 commit chunks.

Interactive API docs are at <http://localhost:8000/docs>.

### Answer synthesis (optional)

Retrieval works out of the box. To get written answers instead of raw cited
context, point the app at any OpenAI-compatible chat endpoint.

**Locally — free, no key, no signup.** Install
[Ollama](https://ollama.com/download) and pull a model:

```bash
ollama pull llama3.2:3b
```

That is all — the defaults already point at `http://localhost:11434/v1`. For
better answers on code questions, pull `qwen2.5-coder:7b` and set
`LLM_MODEL=qwen2.5-coder:7b`.

**Deployed — free hosted models.** See [Deployment](#deployment) below; it is
three environment variables and no code change.

**With no model reachable, nothing breaks.** Routing, retrieval, call
expansion, and citations all still work — `/chat` returns the cited context
block with a short note saying why it wasn't summarised. That is deliberate:
the retrieval half of the system never depends on a model being available,
which is also what makes it independently testable.

---

## How it works

### Ingestion — once per repository, in the background

`POST /index` returns a `session_id` immediately and hands the work to a
FastAPI background task, because cloning and indexing takes seconds to minutes.

1. **Clone** into a temp directory (`git clone`, full history — not shallow,
   since the history is half the point).
2. **Two independent extraction passes:**
   - `chunk_repo()` walks the tree and hands each file to the parser for its
     language — the stdlib `ast` module for Python, tree-sitter grammars for
     JavaScript, JSX, TypeScript and TSX. Either way it emits one chunk per
     function, class or type, never a fragment cut off mid-body, and records
     the function names each chunk calls. Only the parsing step is
     language-specific; every parser returns the same `CodeChunk`.
   - `get_commit_history()` runs `git log` with `\x1f`/`\x1e` field delimiters
     (a commit message can contain commas and pipes, but not ASCII unit
     separators), then one `git show --stat` per commit for its file list.
3. **Index each into its own Qdrant collection**, each with **its own embedder
   instance** — code and commit-message vocabularies are different enough that
   a shared vectorizer blurs both. The two collections end up with different
   vector widths as a result.

### Query — once per question

1. `classify_query()` runs two regexes — no LLM call, no latency — and returns
   `code`, `commits`, or `both`.
2. The routed collection(s) are searched.
3. If code was searched, `expand_via_calls()` takes the **single** best hit,
   reads up to 3 names from its recorded `calls` list, and runs one
   exact-name-filtered search each. One hop, no recursion, so the context stays
   a bounded size however deep the real call chain goes.
4. `format_context_for_llm()` turns the hits into cited markdown — fenced
   `python` blocks headed by `file:line`, commits as hash / date / author /
   message / files. Pure string formatting, no model calls.
5. `synthesize_answer()` POSTs that to an OpenAI-compatible chat endpoint with
   instructions to answer only from the provided context and always cite its
   source. If no model is reachable, the cited context is returned unchanged.

Each question is answered fresh. There is no server-side conversation memory.

---

## API

| Route | Purpose |
|---|---|
| `POST /index` | `{repo_url}` → `{session_id, status: "indexing"}` |
| `GET /index/{session_id}` | Poll target → `{status, stats, error}`; 404 if unknown |
| `POST /chat` | `{session_id, question, top_k?}` → `{answer, route, code_hits, commit_hits}`; 400 if not ready |
| `GET /health` | Liveness probe |

```bash
SESSION=$(curl -s -X POST localhost:8000/index \
  -H 'Content-Type: application/json' \
  -d '{"repo_url":"https://github.com/pypa/sampleproject.git"}' | jq -r .session_id)

curl -s localhost:8000/index/$SESSION | jq

curl -s -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"question\":\"why was the license changed\"}" | jq
```

---

## Layout

```
backend/
  main.py         FastAPI app, the four routes, in-memory SESSIONS
  config.py       every tuning knob in one place
  models.py       request/response schemas
  ingest.py       clone -> chunk -> index, and the embedding-text builders
  retrieve.py     query routing, call expansion, context formatting
  vectorstore.py  Qdrant wrapper and the embedding Protocol
  generate.py     system prompt and answer synthesis
chunkers/
  code_chunk.py       the CodeChunk every parser produces
  python_chunker.py   Python, via the stdlib ast module
  js_chunker.py       JavaScript/JSX/TypeScript/TSX, via tree-sitter
  repo.py             walks a repo, dispatches by file extension
  git_history.py      git log / git show parsing
frontend/         React + TypeScript + Tailwind (Vite)
  src/lib/api.ts       typed API client, one place that knows the base URL
  src/lib/answer.ts    parses the small markdown subset the API emits
  src/components/      RouteIndicator, AnswerBody, Conversation, ...
tests/
Dockerfile        multi-stage: Node builds the UI, Python serves it
```

`RouteIndicator` is the component worth looking at first — it lights a source
because it was *searched*, not because it returned hits, so "both" with zero
commit hits reads differently from the history never being consulted.

`ingest.py` draws a line worth knowing about: **what gets embedded is not what
gets stored.** A code chunk is embedded as
`"{kind} {name}\nin class {parent}\n{docstring}\n{source}"` — signature and
docstring ahead of the body, so the vector leans toward how a person would
phrase a question. The payload keeps every field verbatim, because that is what
produces the citation.

---

## Configuration

| Variable | Required | Effect if missing |
|---|---|---|
| `LLM_BASE_URL` | No | Defaults to `http://localhost:11434/v1` (local Ollama) |
| `LLM_MODEL` | No | Defaults to `llama3.2:3b` |
| `LLM_API_KEY` | Only for hosted providers | Empty — correct for local Ollama, which doesn't check it |
| `ALLOWED_ORIGINS` | Only if the frontend is hosted separately | Empty — correct when one process serves both |
| `PORT` | Set by most hosts | Falls back to 8000 |

No key is needed to run locally, and none is ever written to disk — the key is
read from the environment only.

Everything else — chunk limits, `top_k`, the commit cap, the TF-IDF vocabulary
size — lives in [`backend/config.py`](backend/config.py).

---

## Tests

```bash
pytest
```

91 tests covering AST chunking, git history extraction (against a real git repo
built in a fixture, not a mocked `subprocess`), query routing, vector search and
payload filtering, answer synthesis with its fallbacks, and all four HTTP
routes. The suite needs no model and no network connection.

---

## Known limitations

Stated plainly, because each one is a deliberate trade rather than an oversight.

| Limitation | Why | Impact |
|---|---|---|
| Embeddings are lexical (TF-IDF), not semantic | Fully offline, zero downloads, no external dependency | Won't match a question whose wording differs from the code's own vocabulary. *"how are passwords hashed"* misses a corpus containing `hash_password`, because `hashed` and `passwords` aren't the same tokens as `hash` and `password`. **This is the single highest-impact upgrade available.** |
| Only Python, JS and TS are parsed | Each language needs a grammar | A Go or Rust file is invisible to code retrieval. Commit history still covers it — git is language-agnostic. Adding a language is a parser plus one row in `LANGUAGE_BY_SUFFIX`. |
| No PR or issue ingestion | Would need authenticated GitHub API calls with pagination | Design discussions that never reached a commit message aren't retrievable. |
| Sessions live in memory | Simplest thing that works for a single-user demo | A restart loses every indexed repo, and the app can't run behind multiple workers. |
| Regex query routing | Free, zero latency, right on common phrasings | Misroutes unusual wording containing none of the matched keywords. |
| History extraction is O(n) subprocess calls | One `git show --stat` per commit, for simplicity | Slow on repositories with thousands of commits; capped at 500 by default. |

---

## Roadmap

In priority order by expected impact on answer quality.

1. **Real embeddings.** Swap `TfidfEmbedder` for `SentenceTransformerEmbedder`
   via the existing `embedder_factory` parameter on `RepoVectorStore` — no
   other code changes required.
2. **PR and issue ingestion.** A third collection from the GitHub REST API, one
   chunk per closed PR kept whole, since a design debate only makes sense read
   end to end.
3. ~~Multi-language support via tree-sitter.~~ **Done** — Python, JavaScript,
   JSX, TypeScript and TSX. `CodeChunk` stayed identical, so `retrieve.py`,
   `generate.py` and the frontend needed no changes at all. Adding Go or Rust
   is a parser module plus one row in `LANGUAGE_BY_SUFFIX`.
4. **LLM routing fallback.** Keep the regex as the fast path; escalate only
   when it's ambiguous.
5. **Persistent, multi-user sessions.** Redis for session metadata plus a
   durable Qdrant path.

---

## Deployment

This is a genuine long-running server process: it shells out to `git`, writes to
local disk, and runs background tasks in-process. It needs a normal server host.

**Vercel, Netlify, and GitHub Pages will not work** — none of them support
arbitrary subprocess execution or persistent local disk. Railway, Render, and
Fly.io all do.

A [`Dockerfile`](Dockerfile) is included. It installs `git` — which the app
shells out to and which the slim Python base image does not include — and
listens on `$PORT`, falling back to 7860.

### Recommended: Hugging Face Spaces + Groq (both free)

Free hosting from one service, a free model from another, each used for the
thing it is actually free at.

**1. Create the Space.** At [huggingface.co/new-space](https://huggingface.co/new-space),
pick **Docker** as the SDK and **CPU basic** as the hardware (the free tier).

**2. Add the Space config** to the top of this README, above everything else —
Spaces reads it to know how to build:

```yaml
---
title: Repo Onboarding Assistant
emoji: 🔍
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
---
```

**3. Push the repo** to the Space's git remote.

**4. Add the model settings** in *Settings → Variables and secrets*:

| Name | Kind | Value |
|---|---|---|
| `LLM_BASE_URL` | Variable | `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | Variable | `llama-3.3-70b-versatile` |
| `LLM_API_KEY` | **Secret** | your key from [console.groq.com](https://console.groq.com) |

Make `LLM_API_KEY` a *secret*, not a variable — secrets are not shown in the
Space's public settings. The key never goes in the repository, and never
reaches the browser: the frontend only ever calls this app's own `/chat`.

Two things to expect on the free tier: the Space **sleeps after inactivity**,
so the first visit after a quiet period waits for a cold start, and its disk is
wiped on restart, which clears indexed repos (the same limitation as the
in-memory session dictionary).

### Alternative: frontend and backend deployed separately

By default one process serves both, which needs no configuration. You can
instead put the frontend on a static host (GitHub Pages, Netlify, Vercel,
Cloudflare Pages) and the API somewhere that can run a server process.

The trade is real in both directions: a static host is always-on and instant,
where a free Space sleeps — but you now deploy two things, keep two URLs in
sync, and the API needs CORS.

**1. Point the frontend at the API** with `VITE_API_BASE_URL`. On Vercel or
Netlify, set it as an environment variable; locally, put it in
`frontend/.env.local`:

```
VITE_API_BASE_URL=https://faizz-repo-onboarder.hf.space
```

Note this one is **baked in at build time**, not read at runtime like the
backend's settings — changing it means rebuilding, which on a static host
means triggering a new deploy.

**2. Let the API accept that origin.** Set `ALLOWED_ORIGINS` on the backend to
the frontend's origin — scheme and host, no path, no trailing slash:

```
ALLOWED_ORIGINS = https://faizz.github.io
```

Several are allowed, comma-separated. Until an origin is listed the browser
blocks the request before it is sent, which shows up as a CORS error in the
console rather than anything in the server logs.

**3. Deploy `frontend/` to the static host.** On Vercel or Netlify: root
directory `frontend`, build command `npm run build`, output directory `dist`.

Leaving `VITE_API_BASE_URL` unset keeps the single-process deployment working,
so this is opt-in and both modes share one codebase.

### Other hosts and providers

Railway, Render, and Fly.io all run the same image. Any OpenAI-compatible
provider works — it is **three environment variables and no code change**.

| Provider | `LLM_BASE_URL` | Example `LLM_MODEL` |
|---|---|---|
| [Groq](https://console.groq.com) | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| [Google Gemini](https://aistudio.google.com) | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-3.6-flash` |
| [OpenRouter](https://openrouter.ai) | `https://openrouter.ai/api/v1` | a model ending in `:free` |

Hugging Face's router is worth a note: it is OpenAI-compatible too
(`https://router.huggingface.co/v1`), and one token reaches models across
several providers. Its free tier is a **$0.10/month credit cap** though, which
is roughly 50–300 questions depending on the model — Groq's per-minute rate
limit suits a demo better than a hard monthly ceiling.

Model names change over time; check the provider's model list if one stops
resolving. A wrong name surfaces as an `HTTP 404` note in the answer, not a
crash.

### Public-deployment caveats

- **There is no authentication on `POST /index`.** Anyone who can reach the URL
  can make the server clone an arbitrary public repository. Fine for a demo;
  add an API-key gate or rate limit for anything more exposed.
- **Session state is in memory**, so a redeploy clears every indexed repo.
- **Qdrant storage is under `tempfile.gettempdir()`**, so on a host with an
  ephemeral filesystem indexed data won't survive a restart anyway.
