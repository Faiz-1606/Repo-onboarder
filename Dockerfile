# Container image for Hugging Face Spaces, Render, Railway, Fly.
#
# Two stages: Node compiles the React frontend, then the Python image serves
# the build alongside the API. Node is not present in the final image.

# ---- stage 1: build the frontend -------------------------------------------
FROM node:22-slim AS frontend

RUN corepack enable
WORKDIR /build

# Manifest and lockfile first, so editing a component does not re-run install.
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# Vite inlines env vars at BUILD time, unlike the backend's runtime settings.
# Empty is correct when this image serves both halves; pass a build arg only
# if the frontend is being pointed at an API on another host.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN pnpm build

# ---- stage 2: the API, serving that build ----------------------------------
FROM python:3.12-slim

# git is not optional here: the app shells out to `git clone` and `git log`,
# and the slim base image does not include it. ca-certificates is needed for
# cloning over HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Spaces runs containers as UID 1000, so a matching user is created before
# anything is copied in.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=user backend/ backend/
COPY --chown=user chunkers/ chunkers/
COPY --from=frontend --chown=user /build/dist frontend/dist

# Clones and the Qdrant store are written under the system temp directory,
# which is writable by any user. That data does not survive a restart - the
# same limitation as the in-memory session dictionary.
ENV PYTHONUNBUFFERED=1

# Spaces expects 7860 by default; PORT lets other hosts choose their own.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
