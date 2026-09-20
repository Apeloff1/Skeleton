"""Python source analysis for the repository machine plane.

The analyzer is intentionally static and non-executing. It parses source with
the ast module and emits bounded import/symbol/TODO metadata. It never imports
scanned modules and therefore cannot trigger repository side effects.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from typing import Iterable

from .model import ImportRef, Symbol


TODO_RE = re.compile(
    r"(?im)(?:^|\\s)(TODO|FIXME|XXX|HACK|DEPRECATED|BUG)\\s*[:#-]?\\s*(.{0,220})"
)
MAX_IMPORTS = 5000
MAX_SYMBOLS = 5000
MAX_TODOS = 200


@dataclass(frozen=True, slots=True)
class PythonAnalysis:
    imports: tuple[ImportRef, ...]
    symbols: tuple[Symbol, ...]
    todos: tuple[str, ...]
    lines: int
    parse_error: str | None
    docstring: str | None
    future_annotations: bool
    main_guard: bool


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return node.__class__.__name__


def _decorators(nodes: Iterable[ast.expr]) -> tuple[str, ...]:
    return tuple(_name(item) for item in nodes if _name(item))


def _exports(tree: ast.Module) -> set[str] | None:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
            value = node.value
        else:
            targets.append(node.target)
            value = node.value
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue
        if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return None
        result: set[str] = set()
        for item in value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                result.add(item.value)
            else:
                return None
        return result
    return None


def _import_refs(tree: ast.AST) -> tuple[ImportRef, ...]:
    result: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.append(
                    ImportRef(
                        module=alias.name,
                        line=node.lineno,
                        kind="import",
                        names=(alias.asname or alias.name,),
                        level=0,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = tuple(
                alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                for alias in node.names
            )
            result.append(
                ImportRef(
                    module=module,
                    line=node.lineno,
                    kind="from",
                    names=names,
                    level=node.level,
                )
            )
        if len(result) >= MAX_IMPORTS:
            break
    result.sort(key=lambda item: (item.line, item.kind, item.module, item.names))
    return tuple(result)


def _symbols(tree: ast.Module) -> tuple[Symbol, ...]:
    explicit = _exports(tree)
    result: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(
                Symbol(
                    name=node.name,
                    kind="function",
                    line=node.lineno,
                    exported=node.name in explicit if explicit is not None else not node.name.startswith("_"),
                    decorators=_decorators(node.decorator_list),
                    async_def=isinstance(node, ast.AsyncFunctionDef),
                )
            )
        elif isinstance(node, ast.ClassDef):
            result.append(
                Symbol(
                    name=node.name,
                    kind="class",
                    line=node.lineno,
                    exported=node.name in explicit if explicit is not None else not node.name.startswith("_"),
                    decorators=_decorators(node.decorator_list),
                    bases=tuple(_name(base) for base in node.bases),
                )
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result.append(
                        Symbol(
                            name=target.id,
                            kind="constant",
                            line=node.lineno,
                            exported=target.id in explicit if explicit is not None else True,
                        )
                    )
        if len(result) >= MAX_SYMBOLS:
            break
    result.sort(key=lambda item: (item.line, item.kind, item.name))
    return tuple(result)


def _todos(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in TODO_RE.finditer(text):
        kind = match.group(1).upper()
        detail = " ".join(match.group(2).split())
        item = kind if not detail else f"{kind}: {detail}"
        if item not in result:
            result.append(item)
        if len(result) >= MAX_TODOS:
            break
    return tuple(result)


def _has_main_guard(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            continue
        left = test.left
        right = test.comparators[0]
        if (
            isinstance(test.ops[0], ast.Eq)
            and isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
        ):
            return True
    return False


def analyze_python(text: str, *, filename: str = "<unknown>") -> PythonAnalysis:
    lines = text.count("\\n") + (1 if text else 0)
    todos = _todos(text)
    try:
        tree = ast.parse(text, filename=filename, type_comments=True)
    except (SyntaxError, ValueError) as exc:
        location = getattr(exc, "lineno", None)
        suffix = f":{location}" if location else ""
        return PythonAnalysis(
            imports=(),
            symbols=(),
            todos=todos,
            lines=lines,
            parse_error=f"{type(exc).__name__}{suffix}",
            docstring=None,
            future_annotations=False,
            main_guard=False,
        )

    future_annotations = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )
    return PythonAnalysis(
        imports=_import_refs(tree),
        symbols=_symbols(tree),
        todos=todos,
        lines=lines,
        parse_error=None,
        docstring=ast.get_docstring(tree, clean=False),
        future_annotations=future_annotations,
        main_guard=_has_main_guard(tree),
    )
