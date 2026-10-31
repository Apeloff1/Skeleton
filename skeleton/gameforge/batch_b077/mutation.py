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


def _compile(m: Mutant, name: str, env: dict) -> Callable:
    ns = dict(env)
    exec(compile(m.source, f"<mutant {m.ident}>", "exec"), ns)  # noqa: S102 - local mutant code only
    return ns[name]


def run_mutation(fn: Callable, test: Callable[[Callable], object]) -> MutationReport:
    """``test(candidate)`` must pass for ``fn`` itself; it is then run per mutant."""
    if test(fn) is False:
        raise AssertionError("test fails on the unmutated function")
    rep = MutationReport(fn.__name__)
    env = dict(fn.__globals__)
    for m in generate_mutants(fn):
        try:
            cand = _compile(m, fn.__name__, env)
            killed = test(cand) is False
        except Exception:  # noqa: BLE001 - any failure kills the mutant
            killed = True
        (rep.killed if killed else rep.survived).append(m)
    return rep
