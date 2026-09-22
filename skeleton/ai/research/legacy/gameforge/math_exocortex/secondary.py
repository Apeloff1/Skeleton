from __future__ import annotations
"""
Secondary sandbox — symbolic math (SymPy), matrices, larger numerical workspaces.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("gameforge.math.secondary")


class SymbolicWorkspace:
    """
    SymPy-backed symbolic workspace. Degrades gracefully if sympy missing.
    """

    def __init__(self):
        self._sympy = None
        self.symbols: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        try:
            import sympy as sp

            self._sympy = sp
        except ImportError:
            logger.warning("sympy not installed — symbolic features limited")

    @property
    def available(self) -> bool:
        return self._sympy is not None

    def define_symbols(self, names: str) -> Dict[str, Any]:
        """names: 'x y z' """
        if not self._sympy:
            for n in names.split():
                self.symbols[n] = n
            return {"ok": False, "error": "sympy_unavailable", "symbols": list(self.symbols)}
        sp = self._sympy
        syms = sp.symbols(names)
        if not isinstance(syms, tuple):
            syms = (syms,)
        for s in syms:
            self.symbols[str(s)] = s
        return {"ok": True, "symbols": [str(s) for s in syms]}

    def simplify(self, expr: str) -> Dict[str, Any]:
        return self._op("simplify", expr)

    def expand(self, expr: str) -> Dict[str, Any]:
        return self._op("expand", expr)

    def diff(self, expr: str, var: str = "x", n: int = 1) -> Dict[str, Any]:
        if not self._sympy:
            return {"ok": False, "error": "sympy_unavailable"}
        sp = self._sympy
        try:
            e = sp.sympify(expr, locals=self.symbols)
            v = self.symbols.get(var) or sp.Symbol(var)
            out = str(sp.diff(e, v, n))
            self.history.append({"op": "diff", "expr": expr, "result": out})
            return {"ok": True, "result": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def integrate(self, expr: str, var: str = "x") -> Dict[str, Any]:
        if not self._sympy:
            return {"ok": False, "error": "sympy_unavailable"}
        sp = self._sympy
        try:
            e = sp.sympify(expr, locals=self.symbols)
            v = self.symbols.get(var) or sp.Symbol(var)
            out = str(sp.integrate(e, v))
            self.history.append({"op": "integrate", "expr": expr, "result": out})
            return {"ok": True, "result": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def solve(self, expr: str, var: str = "x") -> Dict[str, Any]:
        if not self._sympy:
            return {"ok": False, "error": "sympy_unavailable"}
        sp = self._sympy
        try:
            e = sp.sympify(expr, locals=self.symbols)
            v = self.symbols.get(var) or sp.Symbol(var)
            sols = sp.solve(e, v)
            out = [str(s) for s in sols]
            self.history.append({"op": "solve", "expr": expr, "result": out})
            return {"ok": True, "result": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def matrix(self, rows: List[List[Any]]) -> Dict[str, Any]:
        if not self._sympy:
            return {"ok": False, "error": "sympy_unavailable"}
        sp = self._sympy
        try:
            M = sp.Matrix(rows)
            return {
                "ok": True,
                "matrix": str(M),
                "det": str(M.det()) if M.shape[0] == M.shape[1] else None,
                "rank": int(M.rank()),
                "shape": list(M.shape),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _op(self, op: str, expr: str) -> Dict[str, Any]:
        if not self._sympy:
            return {"ok": False, "error": "sympy_unavailable"}
        sp = self._sympy
        try:
            e = sp.sympify(expr, locals=self.symbols)
            fn = getattr(sp, op)
            out = str(fn(e))
            self.history.append({"op": op, "expr": expr, "result": out})
            return {"ok": True, "result": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class SecondaryMathSandbox:
    def __init__(self):
        self.symbolic = SymbolicWorkspace()
        self.logs: List[Dict[str, Any]] = []

    def run(self, action: str, **kwargs) -> Dict[str, Any]:
        sym = self.symbolic
        dispatch = {
            "define": lambda: sym.define_symbols(kwargs.get("names", "x")),
            "simplify": lambda: sym.simplify(kwargs["expr"]),
            "expand": lambda: sym.expand(kwargs["expr"]),
            "diff": lambda: sym.diff(kwargs["expr"], kwargs.get("var", "x"), int(kwargs.get("n", 1))),
            "integrate": lambda: sym.integrate(kwargs["expr"], kwargs.get("var", "x")),
            "solve": lambda: sym.solve(kwargs["expr"], kwargs.get("var", "x")),
            "matrix": lambda: sym.matrix(kwargs["rows"]),
            "status": lambda: {"ok": True, "sympy": sym.available, "symbols": list(sym.symbols)},
        }
        if action not in dispatch:
            return {"ok": False, "error": f"unknown action {action}"}
        result = dispatch[action]()
        self.logs.append({"action": action, "kwargs": {k: str(v)[:80] for k, v in kwargs.items()}, "ok": result.get("ok")})
        return result
