"""B023 safe price-rule scripting.

Designers write integer price formulas such as::

    base * (100 + demand) // 100 + max(0, 5 - stock) * 7

:func:`compile_rule` parses with :mod:`ast` and accepts only a small,
side-effect-free subset: integer literals, declared variable names, ``+ - *
// %``, unary minus, comparisons inside ``a if cond else b``, and calls to
``min``/``max``/``clamp``/``abs``. The expression is evaluated by walking the
tree — ``eval`` is never used — with a node budget and a magnitude ceiling,
so a rule cannot loop, allocate huge numbers, touch attributes or import.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Mapping

from skeleton.simulation.economy.sim import EconomySimError, _req_id, _req_int

MAX_SOURCE = 512
MAX_NODES = 96
MAX_MAGNITUDE = 10**15

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}
_CMPOPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}
_FUNCS = {
    "min": (2, None, min),
    "max": (2, None, max),
    "abs": (1, 1, abs),
    "clamp": (3, 3, lambda v, lo, hi: lo if v < lo else hi if v > hi else v),
}


class RuleError(EconomySimError):
    code = "ECO.RULE"


def _check(node: ast.AST, variables: frozenset[str]) -> None:
    if isinstance(node, ast.Expression):
        return _check(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int):
            raise RuleError("only integer literals are allowed")
        return None
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise RuleError(f"unknown variable {node.id!r}")
        return None
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise RuleError(f"operator {type(node.op).__name__} not allowed")
        _check(node.left, variables)
        return _check(node.right, variables)
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise RuleError("unary operator not allowed")
        return _check(node.operand, variables)
    if isinstance(node, ast.IfExp):
        if not isinstance(node.test, ast.Compare):
            raise RuleError("conditional test must be a comparison")
        for part in (node.test, node.body, node.orelse):
            _check(part, variables)
        return None
    if isinstance(node, ast.Compare):
        if any(type(op) not in _CMPOPS for op in node.ops):
            raise RuleError("comparison not allowed")
        for part in (node.left, *node.comparators):
            _check(part, variables)
        return None
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
            raise RuleError("call not allowed")
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            raise RuleError("star args not allowed")
        lo, hi, _ = _FUNCS[node.func.id]
        n = len(node.args)
        if n < lo or (hi is not None and n > hi):
            raise RuleError(f"bad arity for {node.func.id}")
        for arg in node.args:
            _check(arg, variables)
        return None
    raise RuleError(f"syntax {type(node).__name__} not allowed")


def _bounded(value: int) -> int:
    if abs(value) > MAX_MAGNITUDE:
        raise RuleError("value out of range")
    return value


def _eval(node: ast.AST, env: Mapping[str, int]) -> int:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        return _bounded(node.value)
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, env)
        right = _eval(node.right, env)
        if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and right == 0:
            raise RuleError("division by zero")
        return _bounded(_BINOPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, env)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval_cmp(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Call):
        args = [_eval(a, env) for a in node.args]
        return _bounded(_FUNCS[node.func.id][2](*args))
    raise RuleError("unreachable node")  # pragma: no cover - _check rejects first


def _eval_cmp(node: ast.Compare, env: Mapping[str, int]) -> bool:
    left = _eval(node.left, env)
    for op, comp in zip(node.ops, node.comparators):
        right = _eval(comp, env)
        if not _CMPOPS[type(op)](left, right):
            return False
        left = right
    return True


@dataclass(frozen=True)
class PriceRule:
    rule_id: str
    source: str
    variables: frozenset[str]
    floor: int = 1
    ceiling: int = MAX_MAGNITUDE
    _tree: ast.Expression | None = None

    def evaluate(self, env: Mapping[str, int]) -> int:
        missing = self.variables - set(env)
        if missing:
            raise RuleError(f"missing variables {sorted(missing)}")
        for name in self.variables:
            value = env[name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuleError(f"variable {name} must be an integer")
            _bounded(value)
        assert self._tree is not None
        raw = _eval(self._tree, {k: env[k] for k in self.variables})
        return min(self.ceiling, max(self.floor, raw))


def compile_rule(
    rule_id: str,
    source: str,
    variables: set[str] | frozenset[str],
    *,
    floor: int = 1,
    ceiling: int = MAX_MAGNITUDE,
) -> PriceRule:
    _req_id(rule_id, "rule_id")
    _req_int(floor, "floor")
    _req_int(ceiling, "ceiling", minimum=floor)
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise RuleError("rule source too long")
    for name in variables:
        if not isinstance(name, str) or not name.isidentifier() or name in _FUNCS:
            raise RuleError(f"invalid variable name {name!r}")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise RuleError(f"syntax error: {exc.msg}") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise RuleError("rule too complex")
    names = frozenset(variables)
    _check(tree, names)
    return PriceRule(rule_id, source, names, floor, ceiling, tree)


__all__ = ["MAX_MAGNITUDE", "PriceRule", "RuleError", "compile_rule"]
