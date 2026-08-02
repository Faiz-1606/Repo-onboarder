
from __future__ import annotations
from pathlib import Path
from backend.config import MAX_SOURCE_FILE_BYTES, SKIP_DIRECTORIES
from chunkers.code_chunk import CodeChunk, rewrite_chunk_id
from chunkers.js_chunker import chunk_js_file
from chunkers.python_chunker import chunk_python_file


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",  
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def _is_probably_generated(path: Path) -> bool:
    """Minified and bundled files produce chunks nobody wants to read."""
    name = path.name
    return ".min." in name or name.endswith((".bundle.js", ".d.ts"))


def chunk_file(path: Path, language: str) -> list[CodeChunk]:
    """Dispatch one file to the parser for its language."""
    if language == "python":
        return chunk_python_file(path)
    return chunk_js_file(path, language)


def chunk_repo(
    repo_path: Path,
    skip_directories: set[str] = SKIP_DIRECTORIES,
) -> tuple[list[CodeChunk], int]:
   
    chunks: list[CodeChunk] = []
    files_seen = 0

    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(repo_path)
        if any(part in skip_directories for part in relative.parts):
            continue

        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if language is None or _is_probably_generated(path):
            continue 
        try:
            if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
                continue
        except OSError:
            continue

        files_seen += 1
        
        relative_path = relative.as_posix()
        for chunk in chunk_file(path, language):
            chunk.file_path = relative_path
            chunk.chunk_id = rewrite_chunk_id(chunk.chunk_id, relative_path)
            chunks.append(chunk)

    return chunks, files_seen
