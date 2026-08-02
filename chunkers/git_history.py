
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.config import GIT_COMMAND_TIMEOUT_SECONDS, MAX_COMMITS


FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


LOG_FORMAT = f"%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%aI{FIELD_SEPARATOR}%B{RECORD_SEPARATOR}"


@dataclass
class CommitChunk:
    """One commit: who changed what, when, and the reason they gave."""

    commit_hash: str
    author: str
    date: str
    message: str
    files_changed: list[str]
    diff_summary: str


def _run_git(args: list[str], repo_path: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command inside the repo and capture its output.

    errors="replace" because author names and commit messages are not
    guaranteed to be valid UTF-8, and one odd byte should not abort indexing.
    """
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _parse_stat_output(output: str) -> tuple[list[str], str]:
    """Pull the changed-file list and the summary line out of `git show --stat`.

    The stat block looks like:

        src/app/auth.py | 12 ++++++------
        README.md       |  2 +-
        2 files changed, 8 insertions(+), 7 deletions(-)

    Every file line contains a pipe; the trailing summary line does not.
    """
    files_changed: list[str] = []
    diff_summary = ""

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
           
            files_changed.append(line.split("|")[0].strip())
        else:
            diff_summary = line

    return files_changed, diff_summary


def _files_changed_in(commit_hash: str, repo_path: Path) -> tuple[list[str], str]:
    """One `git show --stat` for a single commit.

    A merge commit shows a combined diff whose stat block is usually empty,
    which is why an empty result is treated as normal rather than an error.
    """
    result = _run_git(
        ["show", "--stat", "--format=", commit_hash],
        repo_path,
    )
    if result.returncode != 0:
        return [], ""
    return _parse_stat_output(result.stdout)


def get_commit_history(
    repo_path: Path,
    max_commits: int = MAX_COMMITS,
) -> list[CommitChunk]:
    """Read up to `max_commits` commits, newest first."""
    result = _run_git(
        ["log", f"-n{max_commits}", f"--format={LOG_FORMAT}"],
        repo_path,
    )
    
    if result.returncode != 0:
        return []

    commits: list[CommitChunk] = []
    for record in result.stdout.split(RECORD_SEPARATOR):
        record = record.strip()
        if not record:
            continue

        fields = record.split(FIELD_SEPARATOR)
        if len(fields) != 4:
           
            continue

        commit_hash, author, date, message = fields
        files_changed, diff_summary = _files_changed_in(commit_hash, repo_path)
        commits.append(
            CommitChunk(
                commit_hash=commit_hash,
                author=author,
                date=date,
                message=message.strip(),
                files_changed=files_changed,
                diff_summary=diff_summary,
            )
        )

    return commits
