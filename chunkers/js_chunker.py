

from __future__ import annotations

from pathlib import Path

from chunkers.code_chunk import CodeChunk, make_chunk_id

try:
    import tree_sitter_javascript as tree_sitter_js
    import tree_sitter_typescript as tree_sitter_ts
    from tree_sitter import Language, Parser

    _GRAMMARS = {
        "javascript": tree_sitter_js.language,
        "typescript": tree_sitter_ts.language_typescript,
        "tsx": tree_sitter_ts.language_tsx,
    }
    TREE_SITTER_AVAILABLE = True
except ImportError:  
    _GRAMMARS = {}
    TREE_SITTER_AVAILABLE = False


_PARSERS: dict[str, "Parser"] = {}

_FUNCTION_NODES = {
    "function_declaration",
    "generator_function_declaration",
    "function_signature",
}
_CLASS_NODES = {"class_declaration", "abstract_class_declaration"}


_TYPE_NODES = {
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
}


_FUNCTION_VALUE_NODES = {"arrow_function", "function_expression", "function"}


def _parser_for(language: str) -> "Parser":
    if language not in _PARSERS:
        _PARSERS[language] = Parser(Language(_GRAMMARS[language]()))
    return _PARSERS[language]


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _name_of(node) -> str | None:
    field = node.child_by_field_name("name")
    return _text(field) if field is not None else None


def _leading_jsdoc(node):
    
    previous = node.prev_named_sibling
    if previous is None or previous.type != "comment":
        return None
    if not previous.text.startswith(b"/**"):
        return None
    
    if node.start_point[0] - previous.end_point[0] > 1:
        return None
    return previous


def _clean_jsdoc(comment_text: str) -> str:
    
    body = comment_text.removeprefix("/**").removesuffix("*/")
    lines = [line.strip().removeprefix("*").strip() for line in body.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _called_names(node) -> list[str]:
    
    names: list[str] = []

    def visit(current) -> None:
        if current.type == "call_expression":
            function = current.child_by_field_name("function")
            if function is not None:
                if function.type == "identifier":
                    candidate = _text(function)
                elif function.type == "member_expression":
                    prop = function.child_by_field_name("property")
                    candidate = _text(prop) if prop is not None else None
                else:
                    candidate = None
                if candidate and candidate not in names:
                    names.append(candidate)
        for child in current.named_children:
            visit(child)

    visit(node)
    return names


def _build_chunk(
    node,
    *,
    file_path: str,
    lines: list[str],
    kind: str,
    name: str,
    parent: str | None,
    extent,
) -> CodeChunk:
    
    jsdoc = _leading_jsdoc(extent)
    
    start = (jsdoc or extent).start_point[0] + 1
    end = extent.end_point[0] + 1

    return CodeChunk(
        chunk_id=make_chunk_id(file_path, name, parent, start),
        file_path=file_path,
        kind=kind,
        name=name,
        parent=parent,
        start_line=start,
        end_line=end,
        source="\n".join(lines[start - 1 : end]),
        docstring=_clean_jsdoc(_text(jsdoc)) if jsdoc is not None else None,
        calls=_called_names(node),
    )


def _handle(node, *, file_path: str, lines: list[str], parent: str | None, out: list[CodeChunk], extent=None) -> None:
    extent = extent or node
    kind = node.type

    
    if kind == "export_statement":
        for child in node.named_children:
            _handle(child, file_path=file_path, lines=lines, parent=parent, out=out, extent=node)
        return

    if kind in _FUNCTION_NODES:
        name = _name_of(node)
        if name:
            out.append(
                _build_chunk(node, file_path=file_path, lines=lines, kind="function",
                             name=name, parent=parent, extent=extent)
            )
        return

    if kind in _CLASS_NODES:
        name = _name_of(node)
        if not name:
            return
        out.append(
            _build_chunk(node, file_path=file_path, lines=lines, kind="class",
                         name=name, parent=parent, extent=extent)
        )
        body = node.child_by_field_name("body")
        if body is not None:
            for member in body.named_children:
                if member.type == "method_definition":
                    method_name = _name_of(member)
                    if method_name:
                        out.append(
                            _build_chunk(member, file_path=file_path, lines=lines,
                                         kind="function", name=method_name,
                                         parent=name, extent=member)
                        )
        return

    if kind in _TYPE_NODES:
        name = _name_of(node)
        if name:
            out.append(
                _build_chunk(node, file_path=file_path, lines=lines,
                             kind=_TYPE_NODES[kind], name=name, parent=parent,
                             extent=extent)
            )
        return

    
    if kind in ("lexical_declaration", "variable_declaration"):
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            value = declarator.child_by_field_name("value")
            if value is None or value.type not in _FUNCTION_VALUE_NODES:
                continue
            name = _name_of(declarator)
            if name:
                out.append(
                    _build_chunk(value, file_path=file_path, lines=lines,
                                 kind="function", name=name, parent=parent,
                                 extent=extent)
                )


def chunk_js_file(path: Path, language: str) -> list[CodeChunk]:
    
    if not TREE_SITTER_AVAILABLE or language not in _GRAMMARS:
        return []

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    tree = _parser_for(language).parse(source.encode("utf-8"))
    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    for node in tree.root_node.named_children:
        _handle(node, file_path=str(path), lines=lines, parent=None, out=chunks)

    return chunks
