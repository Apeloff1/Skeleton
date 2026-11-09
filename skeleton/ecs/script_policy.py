"""Static (AST) policy for sandboxed game-logic scripts.

This is the first of three sandbox layers (policy → rewrite → runtime
guards).  The policy is an **allowlist**: a construct is rejected unless it is
known to be safe.  It rejects, with a line/column-precise violation for each
occurrence:

* every import form, ``global``/``nonlocal``, classes, ``async``/``await``,
  generators (``yield``), ``with``, ``match``, decorators and annotations;
* any identifier or attribute beginning with ``_`` — which covers all dunder
  escapes (``__class__``, ``__globals__``, ``__builtins__``, ``__import__``…)
  and reserves the ``_sbx_`` namespace used by the instrumentation;
* dangerous names even though they are absent from the sandbox builtins
  (``eval``, ``exec``, ``compile``, ``open``, ``getattr``, ``type``,
  ``globals``, ``vars``, ``breakpoint``…), so authors get a clear error
  instead of a runtime ``NameError``;
* attribute access outside :data:`ALLOWED_ATTRIBUTES` (blocks frame/code
  walking such as ``gi_frame``/``f_globals``/``co_code`` and ``str.format``
  field-access escapes) and every attribute *store* or *delete*;
* ``try … finally`` (a ``finally: return`` could swallow a budget signal),
  bare ``except:`` and ``except BaseException``;
* ``set`` displays/comprehensions (string-set iteration order depends on
  ``PYTHONHASHSEED`` and would break determinism);
* f-string format specs that are dynamic or request huge widths;
* oversized sources, constants, AST node counts and nesting depth.

Nothing here executes code: the validator only parses.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from skeleton.simulation.ecs.errors import ScriptValidationError

MAX_SOURCE_BYTES = 65_536
MAX_AST_NODES = 20_000
MAX_AST_DEPTH = 64
MAX_CONSTANT_CHARS = 4_096
MAX_CONSTANT_INT_BITS = 256
MAX_FORMAT_WIDTH = 256

FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "input", "breakpoint", "help", "exit", "quit",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr", "hasattr",
    "type", "object", "super", "classmethod", "staticmethod", "property",
    "memoryview", "bytearray", "id", "hash", "iter", "next", "aiter", "anext",
    "format", "callable", "issubclass", "set", "frozenset", "copyright", "credits",
    "license", "BaseException", "GeneratorExit", "KeyboardInterrupt", "SystemExit",
})

#: Method / member names scripts may reach with ``obj.name``.  Membership here
#: is necessary but not sufficient: the runtime guard re-checks the concrete
#: receiver type (see ``skeleton.ecs.script_guard.METHOD_TABLE``).
ALLOWED_ATTRIBUTES = frozenset({
    # str
    "capitalize", "casefold", "center", "count", "endswith", "find", "index", "isalnum",
    "isalpha", "isdigit", "islower", "isnumeric", "isspace", "istitle", "isupper", "join",
    "ljust", "lower", "lstrip", "partition", "removeprefix", "removesuffix", "replace",
    "rfind", "rindex", "rjust", "rpartition", "rsplit", "rstrip", "split", "splitlines",
    "startswith", "strip", "swapcase", "title", "upper", "zfill",
    # list / dict / tuple
    "append", "clear", "copy", "extend", "insert", "pop", "remove", "reverse", "sort",
    "get", "items", "keys", "popitem", "setdefault", "update", "values",
    # numbers / bytes
    "bit_length", "is_integer", "hex", "decode",
    # math namespace
    "pi", "tau", "e", "inf", "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "floor", "ceil", "trunc", "fabs", "hypot", "exp", "log", "log2", "log10", "pow",
    "degrees", "radians", "isfinite", "isclose", "copysign", "fmod", "gcd", "lerp",
    "clamp", "sign", "dist",
})

ALLOWED_EXCEPTIONS = frozenset({
    "Exception", "ArithmeticError", "LookupError", "ValueError", "TypeError", "KeyError",
    "IndexError", "ZeroDivisionError", "RuntimeError", "AssertionError", "OverflowError",
})

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.Return, ast.If, ast.For, ast.While,
    ast.Break, ast.Continue, ast.Pass, ast.FunctionDef, ast.arguments, ast.arg, ast.Name,
    ast.Load, ast.Store, ast.Del, ast.Delete, ast.Constant, ast.List, ast.Tuple, ast.Dict,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call, ast.keyword, ast.IfExp,
    ast.Subscript, ast.Slice, ast.Attribute, ast.ListComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension, ast.JoinedStr, ast.FormattedValue, ast.Starred, ast.NamedExpr,
    ast.Lambda, ast.Try, ast.ExceptHandler, ast.Raise, ast.Assert,
    # operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.LShift,
    ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd, ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot,
    ast.In, ast.NotIn,
)

_REJECT_REASONS: dict[type, str] = {
    ast.Import: "imports are not allowed",
    ast.ImportFrom: "imports are not allowed",
    ast.ClassDef: "class definitions are not allowed",
    ast.AsyncFunctionDef: "async code is not allowed",
    ast.AsyncFor: "async code is not allowed",
    ast.AsyncWith: "async code is not allowed",
    ast.Await: "async code is not allowed",
    ast.With: "with-statements are not allowed",
    ast.Yield: "generators (yield) are not allowed",
    ast.YieldFrom: "generators (yield) are not allowed",
    ast.Global: "global declarations are not allowed",
    ast.Nonlocal: "nonlocal declarations are not allowed",
    ast.Set: "set displays are not allowed (iteration order is not deterministic)",
    ast.SetComp: "set comprehensions are not allowed (iteration order is not deterministic)",
    ast.AnnAssign: "annotations are not allowed",
    ast.MatMult: "matrix multiplication is not supported",
}
_WIDTH_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class Violation:
    line: int
    col: int
    rule: str
    detail: str

    def to_record(self) -> dict[str, object]:
        return {"line": self.line, "col": self.col, "rule": self.rule, "detail": self.detail}


class _Validator(ast.NodeVisitor):
    def __init__(self, max_nodes: int, max_depth: int) -> None:
        self.violations: list[Violation] = []
        self.nodes = 0
        self.depth = 0
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.finally_depth = 0

    def flag(self, node: ast.AST, rule: str, detail: str) -> None:
        self.violations.append(Violation(getattr(node, "lineno", 0), getattr(node, "col_offset", 0), rule, detail))

    # -- traversal --------------------------------------------------------
    def generic_visit(self, node: ast.AST) -> None:
        self.nodes += 1
        if self.nodes == self.max_nodes + 1:
            self.flag(node, "size", f"script exceeds {self.max_nodes} AST nodes")
        if self.nodes > self.max_nodes:
            return
        reason = _REJECT_REASONS.get(type(node))
        if reason is not None:
            self.flag(node, "construct", reason)
            return
        if not isinstance(node, _ALLOWED_NODES):
            self.flag(node, "construct", f"{type(node).__name__} is not allowed")
            return
        self.depth += 1
        if self.depth == self.max_depth + 1:
            self.flag(node, "depth", f"script nests deeper than {self.max_depth}")
        try:
            if self.depth <= self.max_depth:
                method = getattr(self, "check_" + type(node).__name__, None)
                if method is not None:
                    method(node)
                super().generic_visit(node)
        finally:
            self.depth -= 1

    def visit(self, node: ast.AST) -> None:  # route everything through generic_visit
        self.generic_visit(node)

    # -- identifiers ------------------------------------------------------
    def _identifier(self, node: ast.AST, name: str, kind: str) -> None:
        if name.startswith("_"):
            self.flag(node, "underscore", f"{kind} {name!r} starts with '_' (dunder/private access is forbidden)")
        elif name in FORBIDDEN_NAMES:
            self.flag(node, "forbidden-name", f"{kind} {name!r} is forbidden in scripts")

    def check_Name(self, node: ast.Name) -> None:
        self._identifier(node, node.id, "name")

    def check_arg(self, node: ast.arg) -> None:
        self._identifier(node, node.arg, "argument")
        if node.annotation is not None:
            self.flag(node, "construct", "annotations are not allowed")

    def check_keyword(self, node: ast.keyword) -> None:
        if node.arg is not None:
            self._identifier(node, node.arg, "keyword")

    def check_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._identifier(node, node.name, "function")
        if node.decorator_list:
            self.flag(node, "construct", "decorators are not allowed")
        if node.returns is not None:
            self.flag(node, "construct", "annotations are not allowed")

    def check_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            self.flag(node, "underscore", f"attribute {node.attr!r} starts with '_' (dunder/private access is forbidden)")
        elif node.attr not in ALLOWED_ATTRIBUTES:
            self.flag(node, "attribute", f"attribute {node.attr!r} is not allowed")
        if not isinstance(node.ctx, ast.Load):
            self.flag(node, "attribute-store", "assigning or deleting attributes is not allowed")

    # -- control flow -----------------------------------------------------
    def check_Try(self, node: ast.Try) -> None:
        if node.finalbody:
            self.flag(node, "finally", "try/finally is not allowed (use explicit cleanup)")
        for handler in node.handlers:
            if handler.type is None:
                self.flag(handler, "bare-except", "bare 'except:' is not allowed; name an exception type")
                continue
            names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
            for item in names:
                if not isinstance(item, ast.Name) or item.id not in ALLOWED_EXCEPTIONS:
                    label = item.id if isinstance(item, ast.Name) else type(item).__name__
                    self.flag(item, "except-type", f"cannot catch {label!r}; allowed: {', '.join(sorted(ALLOWED_EXCEPTIONS))}")
            if handler.name is not None:
                self._identifier(handler, handler.name, "exception name")

    def check_Raise(self, node: ast.Raise) -> None:
        if node.cause is not None:
            self.flag(node, "construct", "'raise … from …' is not allowed")
        exc = node.exc
        if exc is None:
            return
        target = exc.func if isinstance(exc, ast.Call) else exc
        if not isinstance(target, ast.Name) or target.id not in ALLOWED_EXCEPTIONS:
            self.flag(node, "raise-type", "scripts may only raise the allowed builtin exception types")

    # -- values -----------------------------------------------------------
    def check_Constant(self, node: ast.Constant) -> None:
        value = node.value
        if value is Ellipsis:
            self.flag(node, "construct", "Ellipsis is not allowed")
        elif isinstance(value, (str, bytes)) and len(value) > MAX_CONSTANT_CHARS:
            self.flag(node, "constant", f"constant longer than {MAX_CONSTANT_CHARS} characters")
        elif isinstance(value, int) and not isinstance(value, bool) and value.bit_length() > MAX_CONSTANT_INT_BITS:
            self.flag(node, "constant", f"integer constant wider than {MAX_CONSTANT_INT_BITS} bits")
        elif isinstance(value, complex):
            self.flag(node, "constant", "complex numbers are not supported")

    def check_FormattedValue(self, node: ast.FormattedValue) -> None:
        spec = node.format_spec
        if spec is None:
            return
        parts = spec.values if isinstance(spec, ast.JoinedStr) else [spec]
        for part in parts:
            if not isinstance(part, ast.Constant) or not isinstance(part.value, str):
                self.flag(node, "format-spec", "dynamic f-string format specs are not allowed")
                return
            for digits in _WIDTH_RE.findall(part.value):
                if int(digits) > MAX_FORMAT_WIDTH:
                    self.flag(node, "format-spec", f"format width/precision above {MAX_FORMAT_WIDTH}")
                    return


def validate_source(
    source: str,
    *,
    filename: str = "<script>",
    max_source_bytes: int = MAX_SOURCE_BYTES,
    max_nodes: int = MAX_AST_NODES,
    max_depth: int = MAX_AST_DEPTH,
) -> ast.Module:
    """Parse and validate ``source``; return the AST or raise with all violations."""
    if not isinstance(source, str):
        raise ScriptValidationError("script source must be text", context={"violations": []})
    raw = source.encode("utf-8", "surrogatepass")
    if len(raw) > max_source_bytes:
        raise ScriptValidationError(
            "script source too large",
            context={"violations": [Violation(0, 0, "size", f"source exceeds {max_source_bytes} bytes").to_record()]},
        )
    if "\x00" in source:
        raise ScriptValidationError("script source contains NUL", context={"violations": [Violation(0, 0, "size", "NUL byte").to_record()]})
    try:
        tree = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError as exc:
        raise ScriptValidationError(
            "script has a syntax error",
            context={"violations": [Violation(exc.lineno or 0, (exc.offset or 1) - 1, "syntax", exc.msg or "invalid syntax").to_record()]},
        ) from None
    except (RecursionError, MemoryError, ValueError) as exc:
        raise ScriptValidationError(
            "script could not be parsed safely",
            context={"violations": [Violation(0, 0, "size", type(exc).__name__).to_record()]},
        ) from None
    validator = _Validator(max_nodes, max_depth)
    try:
        validator.visit(tree)
    except RecursionError:
        validator.flag(tree, "depth", "script nests too deeply")
    if validator.violations:
        ordered = sorted(validator.violations, key=lambda v: (v.line, v.col, v.rule))
        first = ordered[0]
        raise ScriptValidationError(
            f"script rejected: line {first.line}: {first.detail}",
            context={"violations": [v.to_record() for v in ordered], "filename": filename},
        )
    return tree


__all__ = [
    "ALLOWED_ATTRIBUTES",
    "ALLOWED_EXCEPTIONS",
    "FORBIDDEN_NAMES",
    "MAX_AST_DEPTH",
    "MAX_AST_NODES",
    "MAX_SOURCE_BYTES",
    "Violation",
    "validate_source",
]
