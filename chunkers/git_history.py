"""Extract commit history from a cloned repository using the git CLI.

Reading the local clone instead of the GitHub API avoids rate limits entirely
and works the same for any git host, not just GitHub.

This is deliberately simple rather than fast: one `git log` for all commits,
then one `git show --stat` per commit for its file list. That is O(n)
subprocess calls, which is fine at the hundreds-of-commits scale and is why
config.MAX_COMMITS exists.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.config import GIT_COMMAND_TIMEOUT_SECONDS, MAX_COMMITS

# ASCII unit and record separators. Commit messages routinely contain commas,
# pipes and newlines, so any printable delimiter would eventually split a
# message in the wrong place. These two cannot appear in a message, which
# makes naive splitting genuinely safe here.
FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"

# hash, author name, author date (strict ISO 8601), raw subject + body.
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
            # Binary files ("Bin 0 -> 512 bytes") and renames ("a.py => b.py")
            # still land here, which is what we want - the name is the useful
            # part either way.
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
    # A repository with no commits yet makes `git log` exit non-zero. There is
    # no history to index in that case, which is not an error worth failing on.
    if result.returncode != 0:
        return []

    commits: list[CommitChunk] = []
    for record in result.stdout.split(RECORD_SEPARATOR):
        record = record.strip()
        if not record:
            continue

        fields = record.split(FIELD_SEPARATOR)
        if len(fields) != 4:
            # Malformed record - should not happen with these separators, but
            # skipping one commit beats aborting the whole history.
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
