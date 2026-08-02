

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CodeChunk:
    """One function, class, type, or module docstring, plus where it came from."""

    chunk_id: str
    file_path: str
    kind: str 
    name: str
    parent: str | None  
    start_line: int
    end_line: int
    source: str
    docstring: str | None
    calls: list[str]  


def make_chunk_id(file_path: str, name: str, parent: str | None, start_line: int) -> str:
    """A stable, human-readable id: where it is, what it is called, which line."""
    qualified = f"{parent}.{name}" if parent else name
    return f"{file_path}::{qualified}::{start_line}"


def rewrite_chunk_id(chunk_id: str, file_path: str) -> str:
    """Swap the path at the front of a chunk id, leaving name and line alone."""
    _, _, tail = chunk_id.partition("::")
    return f"{file_path}::{tail}"
