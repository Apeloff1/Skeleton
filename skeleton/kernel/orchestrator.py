"""Kernel orchestrator — one dispatch over the live bank.

Walks the router plan. Each stage calls the live kernel if present.
Failures are cards, not exceptions, except LawError from the house.
"""
from __future__ import annotations

from typing import Any, Dict, List


class Orchestrator:
    def __init__(self) -> None:
        self.runs = 0
        self.last: Dict[str, Any] = {}
        self._decode_n = 1

    def dispatch(self, text: str = "plan tensor ttk") -> Dict[str, Any]:
        from skeleton.kernel.bank import boot, get, live, snapshot
        from skeleton.kernel.krouter import plan
        from skeleton.kernel.governor import tick as gov_tick

        boot()
        gov = gov_tick()
        pressure = float(gov.get("pressure") or 0)
        profile = str(gov.get("profile") or snapshot().get("profile") or "mobile")
        thr = get("throttle")
        blocked = bool(thr is not None and hasattr(thr, "allow") and not thr.allow())
        slo = get("slo")
        slo_trip = bool(slo is not None and hasattr(slo, "trip") and slo.trip())
        route = plan(profile, pressure=pressure, blocked=blocked, slo_trip=slo_trip)
        self._decode_n = int(route.get("decode_n") or 1)
        pf = get("prefetch")
        if pf is not None and hasattr(pf, "load"):
            pf.load(list(route.get("run") or []))
        trace: List[Dict[str, Any]] = []
        bank = live()

        for stage in route["run"]:
            card = self._stage(stage, text, bank)
            trace.append({"stage": stage, **{k: card.get(k) for k in ("kind", "ok", "writes", "placed", "killed") if k in card}})
            if card.get("stop"):
                break

        self.runs += 1
        self.last = {
            "kind": "kernel-orch",
            "runs": self.runs,
            "route": route,
            "gov": gov,
            "trace": trace,
            "n": len(trace),
            "stored_prose": 0,
        }
        try:
            from skeleton.organism.chronicle import record
            record(None, {
                "book": "journal",
                "topic": "orch " + " ".join(route.get("run") or []),
                "decision": (route.get("run") or ["hold"])[0],
                "code": "orch",
                "why": profile,
                "phase": "orch",
            })
        except Exception:
            pass
        return self.last

    def _stage(self, stage: str, text: str, bank: Dict[str, Any]) -> Dict[str, Any]:
        if stage == "admit":
            adm = bank.get("admission")
            ok = adm.offer(text) if adm is not None and hasattr(adm, "offer") else True
            return {"kind": "admit", "ok": int(bool(ok)), "stop": not ok}
        if stage == "quota":
            q = bank.get("quota")
            ok = q.take("walks") if q is not None and hasattr(q, "take") else True
            return {"kind": "quota", "ok": int(bool(ok)), "stop": not ok}
        if stage == "place":
            ram = bank.get("ram")
            placed = 0
            if ram is not None and hasattr(ram, "put"):
                for tok in text.split()[:4]:
                    ram.put(tok)
                    placed += 1
            return {"kind": "place", "placed": placed}
        if stage == "prefill":
            pipe = bank.get("pipeline")
            gpu = bank.get("gpu")
            if pipe is not None and hasattr(pipe, "run"):
                return pipe.run(text, bank=bank)
            if gpu is not None and hasattr(gpu, "launch"):
                return gpu.launch()
            return {"kind": "prefill", "ok": 0}
        if stage == "decode":
            n = max(1, int(self._decode_n or 1))
            split = bank.get("split")
            blk = bank.get("block")
            last: Dict[str, Any] = {"kind": "decode", "ok": 0, "steps": 0}
            toks = text.split()[:4] or ["plan"]
            steps = 0
            for i in range(max(1, n)):
                if split is not None and hasattr(split, "take") and not split.take("decode"):
                    break
                if blk is not None and hasattr(blk, "forward"):
                    last = blk.forward(toks)
                else:
                    ops = bank.get("ops")
                    last = ops.step() if ops is not None and hasattr(ops, "step") else last
                steps += 1
            last = dict(last)
            last["steps"] = steps
            last["kind"] = last.get("kind") or "decode"
            return last
        if stage == "check":
            chk = bank.get("check")
            ram = bank.get("ram")
            if chk is not None and ram is not None and hasattr(chk, "stamp"):
                chk.stamp(ram.clock)
                return chk.card()
            return {"kind": "check", "ok": 0}
        if stage == "stock":
            sl = bank.get("stock_live")
            if sl is not None and hasattr(sl, "tick"):
                return sl.tick("orch")
            return {"kind": "stock", "ok": 0}
        if stage == "reclaim":
            rec = bank.get("reclaim")
            ram = bank.get("ram")
            if rec is not None and hasattr(rec, "card"):
                return rec.card()
            if ram is not None and hasattr(ram, "pressure"):
                return ram.pressure(0.82)
            return {"kind": "reclaim", "killed": 0}
        return {"kind": stage, "ok": 0}

    def card(self) -> Dict[str, Any]:
        return self.last or {"kind": "kernel-orch", "runs": self.runs, "stored_prose": 0}
