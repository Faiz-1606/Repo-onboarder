"""JavaScript / TypeScript chunking via tree-sitter.

The same rules the Python chunker follows have to hold here, because the rest
of the system cannot tell which parser produced a chunk.
"""

import pytest

from chunkers.js_chunker import chunk_js_file
from chunkers.repo import LANGUAGE_BY_SUFFIX, chunk_repo

SAMPLE_JSX = """\
import { useState } from "react";

/**
 * Format a score for display.
 */
export function formatScore(score) {
  return `${Math.round(score)}%`;
}

const JobCard = ({ job }) => {
  const label = formatScore(job.score);
  return <div className="card">{label}</div>;
};

export default class ResumeClient {
  constructor(apiKey) {
    this.apiKey = apiKey;
  }

  async fetchJobs(query) {
    const res = await fetch(`/jobs?q=${query}`);
    return res.json();
  }
}

function outer() {
  function inner() {
    return 1;
  }
  return inner();
}
"""


def write(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture
def chunks(tmp_path):
    return chunk_js_file(write(tmp_path, "App.jsx", SAMPLE_JSX), "javascript")


def named(chunks, name):
    return next(chunk for chunk in chunks if chunk.name == name)


def test_finds_a_declared_function(chunks):
    assert named(chunks, "formatScore").kind == "function"


def test_finds_an_arrow_function_assigned_to_a_const(chunks):
    # The dominant declaration style in a React codebase - a chunker that only
    # looked for `function` would miss most of the file.
    assert named(chunks, "JobCard").kind == "function"


def test_finds_a_class_and_its_methods(chunks):
    assert named(chunks, "ResumeClient").kind == "class"
    assert named(chunks, "fetchJobs").parent == "ResumeClient"
    assert named(chunks, "constructor").parent == "ResumeClient"


def test_nested_functions_stay_inside_their_parent(chunks):
    # Same rule as the Python chunker.
    assert not any(chunk.name == "inner" for chunk in chunks)
    assert "function inner" in named(chunks, "outer").source


def test_records_called_function_names(chunks):
    assert "formatScore" in named(chunks, "JobCard").calls


def test_member_calls_are_recorded_by_bare_name(chunks):
    # res.json() -> "json", matching how the Python chunker records self.x().
    assert "json" in named(chunks, "fetchJobs").calls


def test_jsdoc_becomes_the_docstring(chunks):
    assert named(chunks, "formatScore").docstring == "Format a score for display."


def test_exported_declarations_keep_the_export_in_range(chunks):
    assert named(chunks, "formatScore").source.lstrip().startswith(("/**", "export"))


def test_unparseable_encoding_is_skipped(tmp_path):
    path = tmp_path / "broken.js"
    path.write_bytes(b"\xff\xfe const x = () => {}")

    assert chunk_js_file(path, "javascript") == []


@pytest.mark.parametrize(
    "name, source, expected_kind",
    [
        ("types.ts", "export interface Job { id: string }", "interface"),
        ("types.ts", "export type Score = number;", "type"),
        ("types.ts", "export enum Kind { A, B }", "enum"),
    ],
)
def test_typescript_type_declarations(tmp_path, name, source, expected_kind):
    chunks = chunk_js_file(write(tmp_path, name, source), "typescript")

    assert [chunk.kind for chunk in chunks] == [expected_kind]


def test_tsx_is_parsed_with_its_own_grammar(tmp_path):
    path = write(tmp_path, "Card.tsx", "const Card = (): JSX.Element => <div />;\n")

    assert [chunk.name for chunk in chunk_js_file(path, "tsx")] == ["Card"]


# --- the dispatcher ---------------------------------------------------------


@pytest.mark.parametrize(
    "suffix, language",
    [(".py", "python"), (".js", "javascript"), (".jsx", "javascript"),
     (".ts", "typescript"), (".tsx", "tsx")],
)
def test_extensions_map_to_languages(suffix, language):
    assert LANGUAGE_BY_SUFFIX[suffix] == language


def test_chunk_repo_handles_mixed_languages(tmp_path):
    write(tmp_path, "app.jsx", SAMPLE_JSX)
    write(tmp_path, "helper.py", '"""Helper."""\n\n\ndef helper():\n    return 1\n')
    write(tmp_path, "README.md", "not code\n")

    chunks, files_seen = chunk_repo(tmp_path)

    assert files_seen == 2  # the markdown file is not a language we parse
    assert {"formatScore", "JobCard", "helper"} <= {chunk.name for chunk in chunks}
    assert {chunk.file_path for chunk in chunks} == {"app.jsx", "helper.py"}


def test_chunk_repo_skips_dependency_and_build_directories(tmp_path):
    for directory in ("node_modules", "dist"):
        (tmp_path / directory).mkdir()
        write(tmp_path, f"{directory}/vendor.js", "export function vendored() {}\n")
    write(tmp_path, "app.js", "export function mine() {}\n")

    chunks, files_seen = chunk_repo(tmp_path)

    assert files_seen == 1
    assert [chunk.name for chunk in chunks] == ["mine"]


def test_chunk_repo_skips_minified_files(tmp_path):
    write(tmp_path, "app.min.js", "export function packed() {}\n")
    write(tmp_path, "app.js", "export function mine() {}\n")

    _, files_seen = chunk_repo(tmp_path)

    assert files_seen == 1


def test_chunk_repo_skips_oversized_files(tmp_path):
    # A checked-in bundle: one enormous line.
    write(tmp_path, "bundle.js", "const x = 1;" * 60_000)
    write(tmp_path, "app.js", "export function mine() {}\n")

    _, files_seen = chunk_repo(tmp_path)

    assert files_seen == 1
