"""AST chunking: what becomes a chunk, and what deliberately does not."""

from chunkers.python_chunker import chunk_python_file, chunk_repo


def chunk_named(chunks, name):
    return next(chunk for chunk in chunks if chunk.name == name)


def test_emits_one_chunk_per_function_class_and_module_docstring(sample_repo):
    chunks = chunk_python_file(sample_repo / "auth.py")
    kinds = {chunk.name: chunk.kind for chunk in chunks}

    assert kinds["auth"] == "module_docstring"
    assert kinds["login"] == "function"
    assert kinds["SessionStore"] == "class"


def test_methods_record_their_enclosing_class(sample_repo):
    chunks = chunk_python_file(sample_repo / "auth.py")

    assert chunk_named(chunks, "remember").parent == "SessionStore"
    assert chunk_named(chunks, "login").parent is None


def test_async_methods_are_chunked_like_any_other(sample_repo):
    forget = chunk_named(chunk_python_file(sample_repo / "auth.py"), "forget")

    assert forget.kind == "function"
    assert forget.parent == "SessionStore"


def test_closures_stay_inside_their_parent_chunk(sample_repo):
    chunks = chunk_python_file(sample_repo / "auth.py")

    assert not any(chunk.name == "inner" for chunk in chunks)
    assert "def inner()" in chunk_named(chunks, "outer").source


def test_chunks_are_syntactically_whole(sample_repo):
    store = chunk_named(chunk_python_file(sample_repo / "auth.py"), "SessionStore")

    # A class chunk carries its whole body, not a truncated header.
    assert store.source.startswith("class SessionStore:")
    assert "def remember" in store.source


def test_records_the_functions_a_chunk_calls(sample_repo):
    login = chunk_named(chunk_python_file(sample_repo / "auth.py"), "login")

    assert "normalise_email" in login.calls
    assert "hash_password" in login.calls
    assert "build_report" not in login.calls


def test_attribute_calls_are_recorded_by_bare_name(sample_repo):
    # self.sessions.pop(...) is recorded as "pop", which is the form an
    # exact-name lookup can match against a chunk's `name` field.
    forget = chunk_named(chunk_python_file(sample_repo / "auth.py"), "forget")

    assert forget.calls == ["pop"]


def test_docstrings_are_captured(sample_repo):
    login = chunk_named(chunk_python_file(sample_repo / "auth.py"), "login")

    assert login.docstring == "Log a user in."


def test_line_range_includes_decorators(tmp_path):
    path = tmp_path / "routes.py"
    path.write_text(
        'import app\n\n@app.get("/users")\ndef list_users():\n    return []\n',
        encoding="utf-8",
    )

    chunk = chunk_python_file(path)[0]

    # The decorator is often the most informative line in the chunk, so the
    # citation's range has to start there rather than at `def`.
    assert chunk.start_line == 3
    assert chunk.source.startswith("@app.get")


def test_unparseable_file_is_skipped_not_raised(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("def oops(:\n", encoding="utf-8")

    assert chunk_python_file(path) == []


def test_empty_file_yields_nothing(tmp_path):
    path = tmp_path / "empty.py"
    path.write_text("", encoding="utf-8")

    assert chunk_python_file(path) == []


def test_chunk_repo_skips_noise_directories(sample_repo):
    vendored = sample_repo / "node_modules"
    vendored.mkdir()
    (vendored / "vendor.py").write_text("def vendored(): pass\n", encoding="utf-8")

    chunks, files_seen = chunk_repo(sample_repo)

    assert files_seen == 1
    assert not any(chunk.name == "vendored" for chunk in chunks)


def test_chunk_repo_rewrites_paths_relative_to_the_repo_root(sample_repo):
    nested = sample_repo / "src" / "app"
    nested.mkdir(parents=True)
    (nested / "db.py").write_text("def connect(): pass\n", encoding="utf-8")

    chunks, _ = chunk_repo(sample_repo)
    connect = chunk_named(chunks, "connect")

    # Forward slashes on every platform, and no temp-directory prefix.
    assert connect.file_path == "src/app/db.py"
    assert connect.chunk_id.startswith("src/app/db.py::")


def test_files_seen_counts_scanned_files_even_when_they_yield_nothing(sample_repo):
    (sample_repo / "__init__.py").write_text("", encoding="utf-8")

    chunks, files_seen = chunk_repo(sample_repo)

    assert files_seen == 2
    assert {chunk.file_path for chunk in chunks} == {"auth.py"}
