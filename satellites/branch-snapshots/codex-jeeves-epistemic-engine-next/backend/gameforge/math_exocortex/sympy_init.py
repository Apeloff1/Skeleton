from __future__ import annotations
"""
Detailed SymPy workspace initialization — exact symbolic mathematics.
No floating approximations unless explicitly requested via .evalf().
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("gameforge.math.sympy_init")


@dataclass
class SymPyInitReport:
    ok: bool
    version: Optional[str]
    symbols: List[str]
    assumptions: Dict[str, str]
    flags: Dict[str, Any]
    message: str
    log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "version": self.version,
            "symbols": self.symbols,
            "assumptions": self.assumptions,
            "flags": self.flags,
            "message": self.message,
            "log": self.log,
        }


def initialize_sympy_workspace(
    *,
    symbol_names: str = "x y z t n",
    real: bool = True,
    positive: bool = False,
    integer: bool = False,
    enable_pretty: bool = True,
) -> Dict[str, Any]:
    """
    Full SymPy sandbox bootstrap.

    Example:
        ws = initialize_sympy_workspace(symbol_names="x y λ", real=True)
        sp = ws["sympy"]
        x = ws["symbols"]["x"]
        expr = sp.diff(x**3 + sp.sin(x), x)
    """
    log: List[Dict[str, Any]] = []
    log.append({"ts": datetime.utcnow().isoformat(), "event": "init_start", "symbols": symbol_names})

    try:
        import sympy as sp
    except ImportError as e:
        log.append({"ts": datetime.utcnow().isoformat(), "event": "import_fail", "error": str(e)})
        return SymPyInitReport(
            ok=False,
            version=None,
            symbols=[],
            assumptions={},
            flags={},
            message="sympy not installed",
            log=log,
        ).to_dict() | {"sympy": None, "symbols": {}, "namespace": {}}

    version = getattr(sp, "__version__", "unknown")
    log.append({"ts": datetime.utcnow().isoformat(), "event": "import_ok", "version": version})

    # Exact mode preferences
    flags = {
        "evaluate": True,
        "rational_arithmetic": True,
        "prefer_exact": True,
        "float_auto": False,
    }
    log.append({"ts": datetime.utcnow().isoformat(), "event": "flags", **flags})

    if enable_pretty:
        try:
            sp.init_printing(use_unicode=True)
            log.append({"ts": datetime.utcnow().isoformat(), "event": "printing_unicode"})
        except Exception as e:
            log.append({"ts": datetime.utcnow().isoformat(), "event": "printing_skip", "error": str(e)})

    assumptions = {}
    kwargs = {}
    if real:
        kwargs["real"] = True
        assumptions["domain"] = "real"
    if positive:
        kwargs["positive"] = True
        assumptions["positive"] = "true"
    if integer:
        kwargs["integer"] = True
        assumptions["integer"] = "true"

    names = [n for n in symbol_names.replace(",", " ").split() if n]
    sym_map: Dict[str, Any] = {}
    for name in names:
        # greek-friendly: allow λ as Symbol
        sym_map[name] = sp.Symbol(name, **kwargs)
    log.append(
        {
            "ts": datetime.utcnow().isoformat(),
            "event": "symbols_defined",
            "names": names,
            "assumptions": assumptions,
        }
    )

    # Pre-bind common exact constructors into namespace
    namespace = {
        "sp": sp,
        "Symbol": sp.Symbol,
        "symbols": sp.symbols,
        "Integer": sp.Integer,
        "Rational": sp.Rational,
        "Float": sp.Float,  # explicit only
        "Matrix": sp.Matrix,
        "eye": sp.eye,
        "zeros": sp.zeros,
        "ones": sp.ones,
        "diff": sp.diff,
        "integrate": sp.integrate,
        "simplify": sp.simplify,
        "expand": sp.expand,
        "factor": sp.factor,
        "cancel": sp.cancel,
        "apart": sp.apart,
        "together": sp.together,
        "trigsimp": sp.trigsimp,
        "powsimp": sp.powsimp,
        "solve": sp.solve,
        "dsolve": sp.dsolve,
        "limit": sp.limit,
        "series": sp.series,
        "Sum": sp.Sum,
        "Product": sp.Product,
        "Eq": sp.Eq,
        "Lt": sp.Lt,
        "Gt": sp.Gt,
        "sin": sp.sin,
        "cos": sp.cos,
        "tan": sp.tan,
        "exp": sp.exp,
        "log": sp.log,
        "sqrt": sp.sqrt,
        "pi": sp.pi,
        "E": sp.E,
        "I": sp.I,
        "oo": sp.oo,
        "latex": sp.latex,
        "srepr": sp.srepr,
        **sym_map,
    }
    log.append(
        {
            "ts": datetime.utcnow().isoformat(),
            "event": "namespace_ready",
            "keys": sorted(list(namespace.keys()))[:40],
        }
    )

    report = SymPyInitReport(
        ok=True,
        version=version,
        symbols=names,
        assumptions=assumptions,
        flags=flags,
        message="SymPy workspace initialized for exact symbolic computation",
        log=log,
    )
    return {
        **report.to_dict(),
        "sympy": sp,
        "symbols": sym_map,
        "namespace": namespace,
    }


DETAILED_SYMPY_INIT_CODE = r'''
# === GameForge detailed SymPy initialization (exact math) ===
from gameforge.math_exocortex.sympy_init import initialize_sympy_workspace

ws = initialize_sympy_workspace(
    symbol_names="x y z t n",
    real=True,
    positive=False,
    integer=False,
    enable_pretty=True,
)
assert ws["ok"], ws["message"]
sp = ws["sympy"]
x, y, z, t, n = [ws["symbols"][k] for k in ("x", "y", "z", "t", "n")]

# Exact rational arithmetic (never auto-float)
expr = sp.Rational(1, 3) + sp.Rational(1, 6)          # 1/2
deriv = sp.diff(x**3 + sp.sin(x), x)                  # 3*x**2 + cos(x)
integ = sp.integrate(x**2, x)                         # x**3/3
sols = sp.solve(x**2 - 2, x)                          # [-sqrt(2), sqrt(2)]
M = sp.Matrix([[1, 2], [3, 4]])
det = M.det()                                         # -2

# Series and limits stay symbolic until .evalf() is explicit
ser = sp.series(sp.exp(x), x, 0, 5)
lim = sp.limit(sp.sin(x) / x, x, 0)                   # 1

print(expr, deriv, integ, sols, det, lim)
'''
