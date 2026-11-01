"""B077 — Mutation testing of critical rules.

Success criterion: "Tests demonstrably catch meaningful mutations in
security/gameplay invariants."

Operates on the *source of one function* via ``ast``: generates mutants
(comparison flips, boundary shifts, arithmetic swaps, boolean negation,
constant tweaks), compiles each in isolation and runs a caller-supplied test
callable against it. A mutant is *killed* if the test raises/returns False.
The report's score is killed/total; :meth:`MutationReport.gate` fails if the
score is below a threshold, listing survivors as evidence.
"""
from __future__ import annotations

import ast
import inspect
import operator
import textwrap
from dataclasses import dataclass, field
from typing import Callable, List

_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv}
_BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}


@dataclass(frozen=True)
class Mutant:
    ident: int
    description: str
    source: str


@dataclass
class MutationReport:
    function: str
    killed: List[Mutant] = field(default_factory=list)
    survived: List[Mutant] = field(default_factory=list)

    @property
    def score(self) -> float:
        total = len(self.killed) + len(self.survived)
        return len(self.killed) / total if total else 1.0

    def gate(self, threshold: float = 1.0) -> None:
        if self.score < threshold:
            names = "; ".join(m.description for m in self.survived)
            raise AssertionError(f"mutation score {self.score:.2f} < {threshold}: survivors: {names}")


def _sites(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _CMP_SWAP:
                    yield node, ("cmp", i)
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            yield node, ("bin", None)
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_SWAP:
            yield node, ("bool", None)
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            yield node, ("const", None)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield node, ("not", None)


def generate_mutants(fn: Callable) -> List[Mutant]:
    src = textwrap.dedent(inspect.getsource(fn))
    n_sites = sum(1 for _ in _sites(ast.parse(src)))
    out: List[Mutant] = []
    for k in range(n_sites):
        tree = ast.parse(src)
        node, (kind, idx) = list(_sites(tree))[k]
        line = getattr(node, "lineno", 0)
        if kind == "cmp":
            old = node.ops[idx]
            node.ops[idx] = _CMP_SWAP[type(old)]()
            desc = f"L{line}: {type(old).__name__}->{type(node.ops[idx]).__name__}"
        elif kind == "bin":
            old = node.op
            node.op = _BIN_SWAP[type(old)]()
            desc = f"L{line}: {type(old).__name__}->{type(node.op).__name__}"
        elif kind == "bool":
            old = node.op
            node.op = _BOOL_SWAP[type(old)]()
            desc = f"L{line}: {type(old).__name__}->{type(node.op).__name__}"
        elif kind == "const":
            desc = f"L{line}: {node.value}->{node.value + 1}"
            node.value = node.value + 1
        else:  # drop a `not`
            parent_src = ast.unparse(node)
            node.op = ast.UAdd()
            desc = f"L{line}: removed not in `{parent_src}`"
        out.append(Mutant(k, desc, ast.unparse(tree)))
    return out


class MutationUnsupportedError(ValueError):
    """Mutant cannot be interpreted safely; never count it as killed."""


_COMPARISONS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_ARITHMETIC = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.Not: operator.not_, ast.UAdd: operator.pos, ast.USub: operator.neg}


def _interpret(node: ast.AST, variables: dict, depth: int = 0):
    """Pure expression interpreter: no eval/exec/imports/calls/attributes."""
    if depth > 32:
        raise MutationUnsupportedError("mutant expression exceeds depth bound")
    if isinstance(node, ast.Constant) and type(node.value) in (bool, int, float, str):
        if type(node.value) is int and abs(node.value) > 10**9:
            raise MutationUnsupportedError("mutant integer exceeds bound")
        return node.value
    if isinstance(node, ast.Name) and node.id in variables:
        return variables[node.id]
    if isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or):
        if isinstance(node.op, ast.And):
            value = True
            for child in node.values:
                value = _interpret(child, variables, depth + 1)
                if not value:
                    return value
            return value
        value = False
        for child in node.values:
            value = _interpret(child, variables, depth + 1)
            if value:
                return value
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_interpret(node.operand, variables, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC:
        left = _interpret(node.left, variables, depth + 1)
        right = _interpret(node.right, variables, depth + 1)
        if type(left) not in (int, float) or type(right) not in (int, float):
            raise MutationUnsupportedError("mutant arithmetic requires numeric operands")
        result = _ARITHMETIC[type(node.op)](left, right)
        if abs(result) > 10**12:
            raise MutationUnsupportedError("mutant arithmetic exceeds bound")
        return result
    if isinstance(node, ast.Compare):
        left = _interpret(node.left, variables, depth + 1)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _COMPARISONS:
                raise MutationUnsupportedError("unsupported mutant comparison")
            right = _interpret(comparator, variables, depth + 1)
            if not _COMPARISONS[type(op)](left, right):
                return False
            left = right
        return True
    raise MutationUnsupportedError("unsupported mutant AST; execution refused")


def _compile(m: Mutant, name: str, env: dict) -> Callable:
    """Compile to a bounded *interpreter closure*, never Python bytecode.

    Only one pure function with a single return expression and positional
    arguments is accepted. Globals and arbitrary source execution are refused.
    """
    if len(m.source.encode("utf-8")) > 32768:
        raise MutationUnsupportedError("mutant source exceeds byte bound")
    tree = ast.parse(m.source)
    if len(list(ast.walk(tree))) > 256 or len(tree.body) != 1:
        raise MutationUnsupportedError("mutant AST exceeds shape bound")
    fn = tree.body[0]
    if not isinstance(fn, ast.FunctionDef) or fn.name != name or fn.decorator_list:
        raise MutationUnsupportedError("mutant must be one undecorated function")
    args = fn.args
    if (args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults
            or args.kw_defaults or len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return)):
        raise MutationUnsupportedError("mutant function signature/body is unsupported")
    names = [arg.arg for arg in args.args]
    if len(set(names)) != len(names):
        raise MutationUnsupportedError("duplicate mutant argument")

    def candidate(*values):
        if len(values) != len(names):
            raise TypeError("mutant argument count mismatch")
        return _interpret(fn.body[0].value, dict(zip(names, values)))

    return candidate


def run_mutation(fn: Callable, test: Callable[[Callable], object]) -> MutationReport:
    """``test(candidate)`` must pass for ``fn`` itself; it is then run per mutant."""
    if test(fn) is False:
        raise AssertionError("test fails on the unmutated function")
    rep = MutationReport(fn.__name__)
    env = dict(fn.__globals__)
    for m in generate_mutants(fn):
        # Unsupported syntax must not inflate the mutation score as a fake kill.
        cand = _compile(m, fn.__name__, env)
        try:
            killed = test(cand) is False
        except Exception:  # noqa: BLE001 - test failure kills an executable mutant
            killed = True
        (rep.killed if killed else rep.survived).append(m)
    return rep
