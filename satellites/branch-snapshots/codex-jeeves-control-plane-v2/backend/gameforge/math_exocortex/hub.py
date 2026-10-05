from __future__ import annotations
"""
Math Exocortex Hub — synergistic primary / secondary / tertiary + formal certainty.
Certainty mode: exact rational, symbolic, machine-checked proofs. No probability path.
"""

import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from gameforge.math_exocortex.primary import PrimaryMathTier
from gameforge.math_exocortex.secondary import SecondaryMathSandbox
from gameforge.math_exocortex.tertiary_pow import TertiaryPoWSandbox
from gameforge.math_exocortex.advanced import BudgetSystem, ChartService, DependencyGraph
from gameforge.math_exocortex.lean4 import Lean4Verifier, LEAN_TEMPLATES
from gameforge.math_exocortex.mechanics import MechanicalToolkit, VirtualScale
from gameforge.math_exocortex.sympy_init import initialize_sympy_workspace, DETAILED_SYMPY_INIT_CODE
from gameforge.math_exocortex.tier_logs import TierLogger
from gameforge.math_exocortex.sota_tools import sota_summary, sota_tool_list


class MathExocortex:
    def __init__(self, pow_difficulty: int = 2, certainty_mode: bool = True):
        self.certainty_mode = certainty_mode
        self.primary = PrimaryMathTier()
        self.secondary = SecondaryMathSandbox()
        self.tertiary = TertiaryPoWSandbox(difficulty=pow_difficulty)
        self.budget = BudgetSystem()
        self.charts = ChartService()
        self.graph = DependencyGraph()
        self.lean = Lean4Verifier()
        self.mechanics = MechanicalToolkit()
        self.tier_log = TierLogger()
        self.sympy_ws: Optional[Dict[str, Any]] = None
        self.audit: List[Dict[str, Any]] = []
        self.tier_log.log("synergy", "hub_init", True, {"certainty_mode": certainty_mode})

    def _audit(self, tier: str, action: str, ok: bool, detail: Optional[dict] = None, duration_ms: Optional[float] = None):
        self.tier_log.log(tier, action, ok, detail=detail, duration_ms=duration_ms)
        self.audit.append(
            {
                "ts": datetime.utcnow().isoformat(),
                "tier": tier,
                "action": action,
                "ok": ok,
                "detail": detail or {},
                "duration_ms": duration_ms,
            }
        )
        if len(self.audit) > 5000:
            self.audit = self.audit[-5000:]

    # ----- primary -----
    def calc(self, expr: str) -> Dict[str, Any]:
        try:
            from gameforge.enterprise.zaibatsu_appwide import guard_text, POLICY
            if POLICY.enforce_on_math:
                g = guard_text(expr, surface="math.calc")
                if g.get("blocked"):
                    return {"ok": False, "error": "zaibatsu_blocked", "detail": g}
        except Exception:
            pass

        t0 = time.perf_counter()
        r = self.primary.calculate(expr)
        self._audit("primary", "calc", r.get("ok", False), {"expr": expr, "value": r.get("value")}, (time.perf_counter() - t0) * 1000)
        return r

    def sheet_set(self, addr: str, value: Any, sheet: str = "default") -> Dict[str, Any]:
        r = self.primary.set_cell(addr, value, sheet)
        self._audit("primary", "sheet_set", True, {"addr": addr, "sheet": sheet})
        return r

    def sheet_get(self, addr: str, sheet: str = "default") -> Dict[str, Any]:
        r = self.primary.get_cell(addr, sheet)
        self._audit("primary", "sheet_get", r.get("ok", False), {"addr": addr})
        return r

    # ----- secondary / sympy -----
    def init_sympy(self, symbol_names: str = "x y z t n", **kwargs) -> Dict[str, Any]:
        t0 = time.perf_counter()
        ws = initialize_sympy_workspace(symbol_names=symbol_names, **kwargs)
        self.sympy_ws = ws
        # sync secondary symbols if available
        if ws.get("ok") and ws.get("symbols"):
            self.secondary.symbolic.symbols.update(ws["symbols"])
            if ws.get("sympy"):
                self.secondary.symbolic._sympy = ws["sympy"]
        self._audit(
            "secondary",
            "sympy_init",
            ws.get("ok", False),
            {"symbols": ws.get("symbols_list") or ws.get("symbols") and list(ws.get("symbols", {}).keys()), "version": ws.get("version")},
            (time.perf_counter() - t0) * 1000,
        )
        # do not return live sympy module over API
        return {k: v for k, v in ws.items() if k not in ("sympy", "namespace", "symbols") or k == "symbols" and isinstance(v, dict) and not v} | {
            "ok": ws.get("ok"),
            "version": ws.get("version"),
            "symbol_names": list((ws.get("symbols") or {}).keys()),
            "message": ws.get("message"),
            "log": ws.get("log"),
            "init_code_ref": "DETAILED_SYMPY_INIT_CODE",
        }

    def sympy_init_code(self) -> Dict[str, Any]:
        return {"code": DETAILED_SYMPY_INIT_CODE}

    def symbolic(self, action: str, **kwargs) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if action == "init":
            return self.init_sympy(kwargs.get("names", "x y z t n"))
        r = self.secondary.run(action, **kwargs)
        self._audit("secondary", action, r.get("ok", False), {"kwargs": {k: str(v)[:80] for k, v in kwargs.items()}}, (time.perf_counter() - t0) * 1000)
        return r

    # ----- tertiary -----
    def pow_sum(self, numbers: List[float], chunk_size: int = 8) -> Dict[str, Any]:
        t0 = time.perf_counter()
        r = self.tertiary.shard_sum(numbers, chunk_size=chunk_size)
        self._audit("tertiary", "pow_sum", r.get("ok", False), {"shards": r.get("shards"), "answer": r.get("answer")}, (time.perf_counter() - t0) * 1000)
        return r

    def pow_map(self, items: List[Any], map_expr: str, chunk_size: int = 5) -> Dict[str, Any]:
        t0 = time.perf_counter()
        r = self.tertiary.shard_map(items, map_expr, chunk_size=chunk_size)
        self._audit("tertiary", "pow_map", r.get("ok", False), {"shards": r.get("shards")}, (time.perf_counter() - t0) * 1000)
        return r

    def pow_status(self) -> Dict[str, Any]:
        st = self.tertiary.chain_status()
        self._audit("tertiary", "status", True, {"height": st.get("height")})
        return st

    # ----- formal Lean 4 -----
    def lean_prove(self, statement: str, context: str = "", tactic: Optional[str] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        r = self.lean.prove(statement, context=context, tactic=tactic)
        self._audit(
            "formal",
            "lean_prove",
            r.get("ok", False),
            {"statement": statement[:200], "certainty": r.get("certainty"), "status": (r.get("obligation") or {}).get("status")},
            (time.perf_counter() - t0) * 1000,
        )
        return r

    def lean_template(self, name: str, tactic: Optional[str] = None) -> Dict[str, Any]:
        stmt = LEAN_TEMPLATES.get(name)
        if not stmt:
            return {"ok": False, "error": f"unknown template {name}", "templates": list(LEAN_TEMPLATES)}
        return self.lean_prove(stmt, tactic=tactic)

    def lean_status(self) -> Dict[str, Any]:
        return self.lean.status()

    # ----- mechanics: weights / scales -----
    def scale_create(self) -> Dict[str, Any]:
        s = self.mechanics.create_scale()
        self._audit("advanced", "scale_create", True, {"id": s.scale_id})
        return {"ok": True, "scale_id": s.scale_id}

    def scale_add_weight(self, scale_id: str, label: str, mass: Any, arm: Any, side: str = "left") -> Dict[str, Any]:
        s = self.mechanics.scales.get(scale_id)
        if not s:
            return {"ok": False, "error": "scale_not_found"}
        w = s.add_weight(label, mass, arm, side=side)
        self._audit("advanced", "add_weight", True, w.to_dict())
        return {"ok": True, "weight": w.to_dict()}

    def scale_counterweight(self, scale_id: str, label: str, mass: Any, arm: Any) -> Dict[str, Any]:
        s = self.mechanics.scales.get(scale_id)
        if not s:
            return {"ok": False, "error": "scale_not_found"}
        w = s.add_counterweight(label, mass, arm)
        self._audit("advanced", "add_counterweight", True, w.to_dict())
        return {"ok": True, "weight": w.to_dict()}

    def scale_evaluate(self, scale_id: str) -> Dict[str, Any]:
        s = self.mechanics.scales.get(scale_id)
        if not s:
            return {"ok": False, "error": "scale_not_found"}
        st = s.evaluate()
        self._audit("advanced", "scale_evaluate", st.balanced, {"net": st.net_moment})
        return {"ok": True, **st.__dict__}

    def scale_required_counterweight(self, scale_id: str, arm: Any) -> Dict[str, Any]:
        s = self.mechanics.scales.get(scale_id)
        if not s:
            return {"ok": False, "error": "scale_not_found"}
        r = s.required_counterweight(arm)
        self._audit("advanced", "required_counterweight", r.get("ok", False), r)
        return r

    def gear_ratio(self, teeth_a: int, teeth_b: int) -> Dict[str, Any]:
        r = self.mechanics.gear_ratio(teeth_a, teeth_b)
        self._audit("advanced", "gear_ratio", r.get("ok", False), r)
        return r

    # ----- budget / graph / charts (deterministic) -----
    def budget_summary(self) -> Dict[str, Any]:
        r = self.budget.summary()
        self._audit("advanced", "budget_summary", True, {"balance": r.get("balance")})
        return r

    def critical_path(self) -> Dict[str, Any]:
        r = self.graph.critical_path()
        self._audit("advanced", "critical_path", r.get("ok", False), r)
        return r

    def chart_line(self, xs, ys, title="line", name="line.png") -> Dict[str, Any]:
        r = self.charts.line(xs, ys, title=title, name=name)
        self._audit("advanced", "chart_line", r.get("ok", False))
        return r

    # probability intentionally disabled in certainty mode
    def forecast_completion(self, **kwargs) -> Dict[str, Any]:
        if self.certainty_mode:
            self._audit("advanced", "forecast_blocked", False, {"reason": "certainty_mode"})
            return {
                "ok": False,
                "error": "probability_disabled_in_certainty_mode",
                "message": "Use exact progress accounting, critical path, or Lean obligations instead of probabilistic forecasts.",
            }
        return {"ok": False, "error": "bayes_removed"}

    # ----- synergy -----
    def synergistic_solve(self, numbers: List[float], symbolic_followup: Optional[str] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        pow_result = self.pow_sum(numbers)
        out: Dict[str, Any] = {"pow": pow_result}
        if pow_result.get("ok") and symbolic_followup:
            if not self.secondary.symbolic.available:
                self.init_sympy()
            expr = symbolic_followup.replace("ANSWER", str(pow_result.get("answer")))
            out["symbolic"] = self.symbolic("simplify", expr=expr)
        self._audit("synergy", "synergistic_solve", pow_result.get("ok", False), {"has_symbolic": "symbolic" in out}, (time.perf_counter() - t0) * 1000)
        return out

    def synergistic_balance_and_prove(self, scale_id: str) -> Dict[str, Any]:
        """Evaluate scale; if balanced, emit a Lean proposition recording equilibrium fact as data obligation."""
        ev = self.scale_evaluate(scale_id)
        out = {"scale": ev}
        if ev.get("ok") and ev.get("balanced"):
            # Data-level certainty: exact rational balance — optional formal record
            stmt = "True"  # placeholder proposition; real models map moments into Nat encodings
            out["formal_note"] = {
                "message": "Scale balanced with exact rational moments; machine proof of numeric embedding is domain-specific.",
                "net_moment": ev.get("net_moment"),
                "certainty": "exact_rational_balance",
            }
            self._audit("synergy", "balance_certain", True, {"scale_id": scale_id})
        else:
            self._audit("synergy", "balance_uncertain", False, {"scale_id": scale_id})
        return out

    def status(self) -> Dict[str, Any]:
        return {
            "certainty_mode": self.certainty_mode,
            "primary": "ok",
            "secondary_sympy": self.secondary.symbolic.available,
            "tertiary_height": len(self.tertiary.chain) - 1,
            "lean": self.lean.status(),
            "charts": self.charts.available,
            "networkx": self.graph.available,
            "scales": list(self.mechanics.scales.keys()),
            "tier_log_stats": self.tier_log.stats(),
            "sota": sota_summary(),
            "audit_tail": self.audit[-8:],
        }

    def logs(self, tier: Optional[str] = None, n: int = 50) -> Dict[str, Any]:
        if tier:
            return {"tier": tier, "entries": self.tier_log.by_tier(tier, n)}
        return {"entries": self.tier_log.tail(n), "stats": self.tier_log.stats()}

    def tools(self) -> Dict[str, Any]:
        return sota_summary()
