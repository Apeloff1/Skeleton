"""AST instrumentation for sandboxed scripts (sandbox layer 2).

Runs only on trees that already passed :func:`script_policy.validate_source`.
The rewrite injects calls to guard functions that live in the script's
globals under the reserved ``_sbx_`` prefix (unreachable from user code
because the policy rejects every identifier starting with ``_``):

``_sbx_step(n)``
    prepended to **every statement list** (module, function, loop, branch and
    handler bodies), charging the number of statements in that block.  Loop
    bodies therefore pay per iteration, so ``while True: pass`` is bounded.
``_sbx_enter()`` / ``_sbx_leave()``
    wrap every function body in ``try/finally`` to bound call depth (the
    policy forbids *user* ``finally`` clauses, so this one cannot be abused).
``_sbx_iter(it)``
    wraps every comprehension source, charging one step per item pulled —
    including items a filter discards, so ``[x for x in range(10**12) if 0]``
    is bounded too.
``_sbx_list`` / ``_sbx_dict`` / ``_sbx_gen``
    replace list/dict comprehensions and generator expressions, metering
    produced elements and modelled memory as they are built.
``_sbx_binop(op, a, b)``
    replaces ``+ * ** << %`` (and their augmented forms), predicting result
    size *before* computing, so ``"x" * 10**12`` or ``9 ** 10**9`` fail fast
    instead of exhausting host memory.
``_sbx_attr(obj, name, *args)`` / ``_sbx_getattr(obj, name)``
    mediate every attribute call / load against a per-type allowlist.
``_sbx_alloc(value)``
    meters f-string results.
``(_sbx_step(1), body)[1]``
    charges every lambda invocation.
"""
from __future__ import annotations

import ast
import itertools

GUARD_PREFIX = "_sbx_"
_GUARDED_BINOPS: dict[type, str] = {
    ast.Add: "+",
    ast.Mult: "*",
    ast.Pow: "**",
    ast.LShift: "<<",
    ast.Mod: "%",
}


def _name(identifier: str, ctx: ast.expr_context | None = None) -> ast.Name:
    return ast.Name(id=identifier, ctx=ctx or ast.Load())


def _call(guard: str, *args: ast.expr, keywords: list[ast.keyword] | None = None) -> ast.Call:
    return ast.Call(func=_name(GUARD_PREFIX + guard), args=list(args), keywords=keywords or [])


def _step(count: int) -> ast.Expr:
    return ast.Expr(value=_call("step", ast.Constant(value=count)))


class _Rewriter(ast.NodeTransformer):
    def __init__(self) -> None:
        self._temps = itertools.count()

    # -- statement lists --------------------------------------------------
    def _block(self, body: list[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for stmt in body:
            result = self.visit(stmt)
            if result is None:
                continue
            if isinstance(result, list):
                out.extend(result)
            else:
                out.append(result)
        return [_step(max(1, len(body)))] + out

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._block(node.body)
        return node

    def _generic_blocks(self, node: ast.stmt, fields: tuple[str, ...]) -> ast.stmt:
        for name, value in ast.iter_fields(node):
            if name in fields:
                if value:
                    setattr(node, name, self._block(value))
            elif isinstance(value, list):
                setattr(node, name, [self.visit(v) if isinstance(v, ast.AST) else v for v in value])
            elif isinstance(value, ast.AST):
                setattr(node, name, self.visit(value))
        return node

    def visit_If(self, node: ast.If) -> ast.stmt:
        return self._generic_blocks(node, ("body", "orelse"))

    def visit_For(self, node: ast.For) -> ast.stmt:
        return self._generic_blocks(node, ("body", "orelse"))

    def visit_While(self, node: ast.While) -> ast.stmt:
        return self._generic_blocks(node, ("body", "orelse"))

    def visit_Try(self, node: ast.Try) -> ast.stmt:
        node.body = self._block(node.body)
        node.orelse = self._block(node.orelse) if node.orelse else []
        for handler in node.handlers:
            if handler.type is not None:
                handler.type = self.visit(handler.type)
            handler.body = self._block(handler.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.stmt:
        node.args = self.visit(node.args)
        body = self._block(node.body)
        node.body = [
            ast.Expr(value=_call("enter")),
            ast.Try(body=body, handlers=[], orelse=[], finalbody=[ast.Expr(value=_call("leave"))]),
        ]
        return node

    # -- expressions ------------------------------------------------------
    def visit_Lambda(self, node: ast.Lambda) -> ast.expr:
        node.args = self.visit(node.args)
        body = self.visit(node.body)
        node.body = ast.Subscript(
            value=ast.Tuple(elts=[_call("step", ast.Constant(value=1)), body], ctx=ast.Load()),
            slice=ast.Constant(value=1),
            ctx=ast.Load(),
        )
        return node

    def _comprehension_generators(self, generators: list[ast.comprehension]) -> list[ast.comprehension]:
        out = []
        for gen in generators:
            gen.target = self.visit(gen.target)
            gen.iter = _call("iter", self.visit(gen.iter))
            gen.ifs = [self.visit(cond) for cond in gen.ifs]
            out.append(gen)
        return out

    def visit_ListComp(self, node: ast.ListComp) -> ast.expr:
        gen = ast.GeneratorExp(elt=self.visit(node.elt), generators=self._comprehension_generators(node.generators))
        return _call("list", gen)

    def visit_DictComp(self, node: ast.DictComp) -> ast.expr:
        pair = ast.Tuple(elts=[self.visit(node.key), self.visit(node.value)], ctx=ast.Load())
        gen = ast.GeneratorExp(elt=pair, generators=self._comprehension_generators(node.generators))
        return _call("dict", gen)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.expr:
        node.elt = self.visit(node.elt)
        node.generators = self._comprehension_generators(node.generators)
        return _call("gen", node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        left = self.visit(node.left)
        right = self.visit(node.right)
        symbol = _GUARDED_BINOPS.get(type(node.op))
        if symbol is None:
            node.left, node.right = left, right
            return node
        return _call("binop", ast.Constant(value=symbol), left, right)

    def visit_AugAssign(self, node: ast.AugAssign):
        symbol = _GUARDED_BINOPS.get(type(node.op))
        value = self.visit(node.value)
        target = node.target
        if symbol is None:
            node.target = self.visit(target)
            node.value = value
            return node
        if isinstance(target, ast.Name):
            return ast.Assign(
                targets=[_name(target.id, ast.Store())],
                value=_call("binop", ast.Constant(value=symbol), _name(target.id), value),
            )
        if isinstance(target, ast.Subscript):
            n = next(self._temps)
            obj, key = f"{GUARD_PREFIX}o{n}", f"{GUARD_PREFIX}k{n}"
            key_expr = target.slice
            if isinstance(key_expr, ast.Slice):
                none = ast.Constant(value=None)
                key_expr = _call(
                    "slice",
                    self.visit(key_expr.lower) if key_expr.lower else none,
                    self.visit(key_expr.upper) if key_expr.upper else none,
                    self.visit(key_expr.step) if key_expr.step else none,
                )
            else:
                key_expr = self.visit(key_expr)
            return [
                ast.Assign(targets=[_name(obj, ast.Store())], value=self.visit(target.value)),
                ast.Assign(targets=[_name(key, ast.Store())], value=key_expr),
                ast.Assign(
                    targets=[ast.Subscript(value=_name(obj), slice=_name(key), ctx=ast.Store())],
                    value=_call(
                        "binop",
                        ast.Constant(value=symbol),
                        ast.Subscript(value=_name(obj), slice=_name(key), ctx=ast.Load()),
                        value,
                    ),
                ),
            ]
        # Attribute targets are rejected by the policy; keep the node inert.
        node.target = self.visit(target)
        node.value = value
        return node

    def visit_Call(self, node: ast.Call) -> ast.expr:
        args = [self.visit(a) for a in node.args]
        keywords = [self.visit(k) for k in node.keywords]
        func = node.func
        if isinstance(func, ast.Attribute):
            return _call("attr", self.visit(func.value), ast.Constant(value=func.attr), *args, keywords=keywords)
        node.func = self.visit(func)
        node.args = args
        node.keywords = keywords
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        return _call("getattr", self.visit(node.value), ast.Constant(value=node.attr))

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.expr:
        # Format specs are themselves JoinedStr nodes but must stay literal.
        node.values = [self.visit(v) if isinstance(v, ast.FormattedValue) else v for v in node.values]
        return _call("alloc", node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.expr:
        node.value = self.visit(node.value)
        return node


def instrument(tree: ast.Module) -> ast.Module:
    """Return an instrumented, location-fixed copy-in-place of ``tree``."""
    rewritten = _Rewriter().visit(tree)
    return ast.fix_missing_locations(rewritten)


__all__ = ["GUARD_PREFIX", "instrument"]
