"""Liveness/readiness probes with named dependency checks."""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable, Dict, Tuple, Union

Check = Callable[[], Union[bool, Awaitable[bool]]]


class HealthRegistry:
    def __init__(self, timeout_s: float = 2.0):
        self.timeout_s = timeout_s
        self._checks: Dict[str, Tuple[Check, bool]] = {}
        self.started = time.time()

    def add(self, name: str, check: Check, critical: bool = True) -> None:
        if name in self._checks:
            raise ValueError(f"duplicate check {name}")
        self._checks[name] = (check, critical)

    def live(self) -> Dict[str, Any]:
        return {"status": "ok", "uptime_s": round(time.time() - self.started, 3)}

    async def _run(self, check: Check) -> bool:
        try:
            r = check()
            if inspect.isawaitable(r):
                r = await asyncio.wait_for(r, self.timeout_s)
            return bool(r)
        except Exception:  # noqa: BLE001 - a crashing probe is a failing probe
            return False

    async def ready(self) -> Tuple[int, Dict[str, Any]]:
        names = list(self._checks)
        results = await asyncio.gather(*(self._run(self._checks[n][0]) for n in names))
        checks = {n: ("ok" if ok else "fail") for n, ok in zip(names, results)}
        critical_fail = any(not ok and self._checks[n][1] for n, ok in zip(names, results))
        degraded = any(not ok for ok in results)
        status = "fail" if critical_fail else ("degraded" if degraded else "ok")
        return (503 if critical_fail else 200), {"status": status, "checks": checks}
