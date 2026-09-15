from __future__ import annotations
"""
Primary math tier — calculator + lightweight spreadsheet grid.
"""

import ast
import operator
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import math


# Safe eval for calculator
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_FUNCS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
}


class SafeCalculator:
    def eval(self, expr: str) -> float:
        tree = ast.parse(expr, mode="eval")
        return float(self._eval(tree.body))

    def _eval(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Num):  # pragma: no cover
            return node.n
        if isinstance(node, ast.BinOp):
            op = _OPS.get(type(node.op))
            if not op:
                raise ValueError("unsupported operator")
            return op(self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _OPS.get(type(node.op))
            if not op:
                raise ValueError("unsupported unary")
            return op(self._eval(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = _FUNCS.get(node.func.id)
            if not fn or not callable(fn):
                raise ValueError(f"unsupported function {node.func.id}")
            args = [self._eval(a) for a in node.args]
            return fn(*args)
        if isinstance(node, ast.Name) and node.id in _FUNCS and not callable(_FUNCS[node.id]):
            return _FUNCS[node.id]
        raise ValueError("unsupported expression")


@dataclass
class Sheet:
    name: str
    cells: Dict[str, Any] = field(default_factory=dict)  # A1 -> value or formula

    def set(self, addr: str, value: Any):
        self.cells[addr.upper()] = value

    def get(self, addr: str) -> Any:
        addr = addr.upper()
        v = self.cells.get(addr)
        if isinstance(v, str) and v.startswith("="):
            return self._eval_formula(v[1:])
        return v

    def _eval_formula(self, formula: str) -> Any:
        # very small formula: SUM(A1:A3) or arithmetic with cell refs
        f = formula.strip().upper()
        if f.startswith("SUM(") and f.endswith(")"):
            inner = f[4:-1]
            if ":" in inner:
                start, end = inner.split(":")
                cells = _expand_range(start, end)
                vals = [float(self.get(c) or 0) for c in cells]
                return sum(vals)
        # replace cell refs
        import re

        calc = SafeCalculator()
        expr = formula
        for ref in sorted(set(re.findall(r"[A-Z]+\d+", formula.upper())), key=len, reverse=True):
            val = self.get(ref)
            expr = expr.replace(ref, str(float(val or 0)))
        return calc.eval(expr)


def _expand_range(start: str, end: str) -> List[str]:
    import re

    m1 = re.match(r"([A-Z]+)(\d+)", start)
    m2 = re.match(r"([A-Z]+)(\d+)", end)
    if not m1 or not m2:
        return [start]
    c1, r1 = m1.group(1), int(m1.group(2))
    c2, r2 = m2.group(1), int(m2.group(2))
    # same column only for simplicity
    if c1 == c2:
        return [f"{c1}{r}" for r in range(min(r1, r2), max(r1, r2) + 1)]
    return [start, end]


class PrimaryMathTier:
    def __init__(self):
        self.calc = SafeCalculator()
        self.sheets: Dict[str, Sheet] = {"default": Sheet("default")}

    def calculate(self, expr: str) -> Dict[str, Any]:
        try:
            value = self.calc.eval(expr)
            return {"ok": True, "value": value, "expr": expr}
        except Exception as e:
            return {"ok": False, "error": str(e), "expr": expr}

    def sheet(self, name: str = "default") -> Sheet:
        if name not in self.sheets:
            self.sheets[name] = Sheet(name)
        return self.sheets[name]

    def set_cell(self, addr: str, value: Any, sheet: str = "default") -> Dict[str, Any]:
        self.sheet(sheet).set(addr, value)
        return {"ok": True, "addr": addr, "value": value}

    def get_cell(self, addr: str, sheet: str = "default") -> Dict[str, Any]:
        try:
            return {"ok": True, "addr": addr, "value": self.sheet(sheet).get(addr)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
