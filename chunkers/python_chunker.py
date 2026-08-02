"""Split Python source into retrievable chunks using the standard library ast.

Parsing rather than splitting on token count is the whole point: every chunk
that comes out of here is a syntactically whole function or class, so a search
hit is never a function body cut off halfway through.

Each chunk also records the names of the functions it calls. That list is what
retrieve.expand_via_calls() follows to pull in adjacent context, so the AST
walk pays for itself twice.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from backend.config import SKIP_DIRECTORIES


@dataclass
class CodeChunk:
    """One function, class, or module docstring, plus where it came from."""

    chunk_id: str
    file_path: str
    kind: str  # "function" | "class" | "module_docstring"
    name: str
    parent: str | None  # enclosing class name, or None for top-level
    start_line: int
    end_line: int
    source: str
    docstring: str | None
    calls: list[str]  # function names invoked inside this chunk's body


def _called_function_names(node: ast.AST) -> list[str]:
    """Collect the names of every function called inside `node`.

    Attribute calls are reduced to the bare attribute (`self.save()` -> "save")
    because chunk names are stored without a class prefix, so that is the form
    an exact-name lookup can actually match.
    """
    names: list[str] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue

        func = inner.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            # Calling the result of an expression, e.g. get_handler()(x).
            # There is no name to record.
            continue

        if name not in names:
            names.append(name)
    return names


def _start_line(node: ast.AST) -> int:
    """First line of a definition, counting decorators.

    ast puts `lineno` on the `def`/`class` keyword, but a decorator like
    `@app.get("/users")` is often the most useful line in the whole chunk, so
    it belongs inside the citation's line range.
    """
    candidates = [node.lineno]
    candidates.extend(dec.lineno for dec in getattr(node, "decorator_list", []))
    return min(candidates)


def _make_chunk(
    node: ast.AST,
    *,
    file_path: str,
    lines: list[str],
    kind: str,
    name: str,
    parent: str | None,
) -> CodeChunk:
    start = _start_line(node)
    end = node.end_lineno or start
    qualified = f"{parent}.{name}" if parent else name

    return CodeChunk(
        chunk_id=f"{file_path}::{qualified}::{start}",
        file_path=file_path,
        kind=kind,
        name=name,
        parent=parent,
        start_line=start,
        end_line=end,
        source="\n".join(lines[start - 1 : end]),
        docstring=ast.get_docstring(node) if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ) else None,
        calls=_called_function_names(node),
    )


def chunk_python_file(path: Path) -> list[CodeChunk]:
    """Parse one file and return its chunks, or [] if it cannot be parsed.

    A repository can legitimately contain Python 2 files, template files with
    placeholder syntax, or deliberately-broken fixtures under tests/. None of
    those should stop the rest of the repo from being indexed, so a parse
    failure is skipped rather than raised.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return []

    lines = source.splitlines()
    file_path = str(path)
    chunks: list[CodeChunk] = []

    # The module docstring is usually the best one-paragraph description of
    # what a file is for, so it gets indexed as a chunk of its own.
    module_docstring = ast.get_docstring(tree)
    if module_docstring and tree.body:
        docstring_node = tree.body[0]
        start = docstring_node.lineno
        end = docstring_node.end_lineno or start
        chunks.append(
            CodeChunk(
                chunk_id=f"{file_path}::module::{start}",
                file_path=file_path,
                kind="module_docstring",
                name=path.stem,
                parent=None,
                start_line=start,
                end_line=end,
                source="\n".join(lines[start - 1 : end]),
                docstring=module_docstring,
                calls=[],
            )
        )

    # Only top-level definitions and methods one level inside a class are
    # split out. A closure defined inside a function stays part of its
    # parent's chunk - an intentional simplification, since a closure rarely
    # makes sense read on its own.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.append(
                _make_chunk(
                    node,
                    file_path=file_path,
                    lines=lines,
                    kind="function",
                    name=node.name,
                    parent=None,
                )
            )
        elif isinstance(node, ast.ClassDef):
            chunks.append(
                _make_chunk(
                    node,
                    file_path=file_path,
                    lines=lines,
                    kind="class",
                    name=node.name,
                    parent=None,
                )
            )
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chunks.append(
                        _make_chunk(
                            member,
                            file_path=file_path,
                            lines=lines,
                            kind="function",
                            name=member.name,
                            parent=node.name,
                        )
                    )

    return chunks


def _rewrite_chunk_id(chunk_id: str, file_path: str) -> str:
    """Swap the path at the front of a chunk id, leaving name and line alone."""
    _, _, tail = chunk_id.partition("::")
    return f"{file_path}::{tail}"


def chunk_repo(
    repo_path: Path,
    skip_directories: set[str] = SKIP_DIRECTORIES,
) -> tuple[list[CodeChunk], int]:
    """Chunk every .py file under `repo_path`.

    Returns the chunks and the number of Python files seen. The count is
    reported separately because a file that yields no chunks - a bare
    __init__.py, say - was still scanned, and the API surfaces it in the
    indexing stats.

    Each chunk's file_path is rewritten relative to the repo root so citations
    read as `src/app/auth.py` rather than exposing the temp directory the repo
    happened to be cloned into.
    """
    chunks: list[CodeChunk] = []
    files_seen = 0

    for path in sorted(repo_path.rglob("*.py")):
        relative = path.relative_to(repo_path)
        if any(part in skip_directories for part in relative.parts):
            continue

        files_seen += 1
        # as_posix() keeps citations looking the same on Windows and Linux.
        relative_path = relative.as_posix()
        for chunk in chunk_python_file(path):
            chunk.file_path = relative_path
            chunk.chunk_id = _rewrite_chunk_id(chunk.chunk_id, relative_path)
            chunks.append(chunk)

    return chunks, files_seen
