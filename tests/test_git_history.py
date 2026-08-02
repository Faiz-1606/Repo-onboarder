"""Commit history extraction, against a real git repo."""

from chunkers.git_history import get_commit_history


def test_reads_a_commit(sample_repo):
    commits = get_commit_history(sample_repo)

    assert len(commits) == 1
    assert commits[0].author == "Test Dev"
    assert commits[0].date.startswith("20")  # ISO 8601


def test_message_survives_a_literal_pipe(sample_repo):
    # The whole reason for the \x1f / \x1e delimiters: a message containing a
    # comma or pipe would break naive splitting.
    message = get_commit_history(sample_repo)[0].message

    assert "with a comma | and a pipe" in message


def test_message_body_is_kept_not_just_the_subject(sample_repo):
    # The body is where a "why" answer usually lives.
    message = get_commit_history(sample_repo)[0].message

    assert "Why: we switched to reversal hashing" in message


def test_captures_changed_files_and_the_summary_line(sample_repo):
    commit = get_commit_history(sample_repo)[0]

    assert sorted(commit.files_changed) == ["README.md", "auth.py"]
    assert "changed" in commit.diff_summary


def test_commits_come_back_newest_first(sample_repo, add_commit):
    add_commit(sample_repo, "auth.py", "x = 1\n", "Replace auth with a stub")

    commits = get_commit_history(sample_repo)

    assert len(commits) == 2
    assert commits[0].message == "Replace auth with a stub"


def test_max_commits_is_respected(sample_repo, add_commit):
    add_commit(sample_repo, "b.py", "y = 2\n", "Add b.py")

    assert len(get_commit_history(sample_repo, max_commits=1)) == 1


def test_repo_with_no_commits_returns_empty_not_an_error(empty_repo):
    # `git log` exits non-zero here, which is not a failure worth raising on.
    assert get_commit_history(empty_repo) == []


def test_commit_hashes_are_full_length(sample_repo):
    # Stored in full; shortened only when formatted for display.
    assert len(get_commit_history(sample_repo)[0].commit_hash) == 40
