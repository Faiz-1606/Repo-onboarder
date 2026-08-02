

from __future__ import annotations

import ast
from pathlib import Path

from chunkers.code_chunk import CodeChunk, make_chunk_id


def _called_function_names(node: ast.AST) -> list[str]:
    
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
           
            continue

        if name not in names:
            names.append(name)
    return names


def _start_line(node: ast.AST) -> int:
    
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

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, name, parent, start),
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
    
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return []

    lines = source.splitlines()
    file_path = str(path)
    chunks: list[CodeChunk] = []

   
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
