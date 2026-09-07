"""Blue-green deployments — atomic environment switching.

Maintains two environments (blue, green). New versions deploy to the
idle environment, get smoke-tested there, and traffic flips atomically
when healthy. Rollback is an instant flip back. Tracks switch history
and per-environment health for the deployment card.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Environment:
    name: str
    version: Optional[str] = None
    deployed_ns: int = 0
    healthy: bool = False
    smoke_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "healthy": self.healthy,
            "deployed_ns": self.deployed_ns,
            "smoke_checks": len(self.smoke_results),
        }


@dataclass
class SwitchRecord:
    from_env: str
    to_env: str
    version: str
    timestamp_ns: int
    rollback: bool = False


class BlueGreenDeployer:
    """Atomic blue-green environment switching."""

    def __init__(self):
        self._envs: Dict[str, Environment] = {
            "blue": Environment(name="blue"),
            "green": Environment(name="green"),
        }
        self._live = "blue"
        self._history: List[SwitchRecord] = []

    def live(self) -> Environment:
        return self._envs[self._live]

    def idle(self) -> Environment:
        return self._envs["green" if self._live == "blue" else "blue"]

    def deploy(self, version: str) -> Environment:
        env = self.idle()
        env.version = version
        env.deployed_ns = time.time_ns()
        env.healthy = False
        env.smoke_results.clear()
        return env

    def smoke_test(self, checks: List[Callable[[], bool]]) -> Dict[str, Any]:
        env = self.idle()
        results = []
        for i, check in enumerate(checks):
            try:
                ok = bool(check())
            except Exception:  # noqa: BLE001
                ok = False
            results.append({"check": f"smoke-{i}", "passed": ok})
        env.smoke_results = results
        env.healthy = all(r["passed"] for r in results) if results else False
        return {"environment": env.name, "healthy": env.healthy, "results": results}

    def promote(self) -> Dict[str, Any]:
        env = self.idle()
        if not env.healthy or not env.version:
            return {"promoted": False, "reason": "idle environment not healthy or empty"}
        record = SwitchRecord(
            from_env=self._live,
            to_env=env.name,
            version=env.version,
            timestamp_ns=time.time_ns(),
        )
        self._live = env.name
        self._history.append(record)
        return {"promoted": True, "live": self._live, "version": env.version}

    def rollback(self) -> Dict[str, Any]:
        if not self._history:
            return {"rolled_back": False, "reason": "no switch history"}
        last = self._history[-1]
        previous = self._envs[last.from_env]
        if not previous.version:
            return {"rolled_back": False, "reason": "previous environment has no version"}
        self._live = last.from_env
        self._history.append(SwitchRecord(
            from_env=last.to_env,
            to_env=last.from_env,
            version=previous.version,
            timestamp_ns=time.time_ns(),
            rollback=True,
        ))
        return {"rolled_back": True, "live": self._live, "version": previous.version}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "blue-green-card",
            "live": self._live,
            "environments": {n: e.to_dict() for n, e in self._envs.items()},
            "switches": len(self._history),
            "rollbacks": len([h for h in self._history if h.rollback]),
        }
