"""Environment manager — multi-environment lifecycle (dev/stage/prod).

Tracks named environments with their config overlays, deployed
versions, and promotion paths. Enforces promotion gates (tests must
pass in stage before prod), records environment-specific state, and
prevents accidental cross-environment operations.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Environment:
    name: str
    order: int
    config_overlay: Dict[str, Any] = field(default_factory=dict)
    deployed_version: Optional[str] = None
    gate_checks: List[str] = field(default_factory=list)
    passed_gates: List[str] = field(default_factory=list)
    locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "order": self.order,
            "deployed_version": self.deployed_version,
            "locked": self.locked,
            "gates_passed": f"{len(self.passed_gates)}/{len(self.gate_checks)}",
        }


class EnvironmentManager:
    """Ordered environment promotion with gate enforcement."""

    def __init__(self):
        self._envs: Dict[str, Environment] = {}
        self._promotions: List[Dict[str, Any]] = []

    def define(self, name: str, order: int,
               config_overlay: Optional[Dict[str, Any]] = None,
               gate_checks: Optional[List[str]] = None) -> Environment:
        env = Environment(name=name, order=order,
                          config_overlay=config_overlay or {},
                          gate_checks=gate_checks or [])
        self._envs[name] = env
        return env

    def deploy(self, env: str, version: str) -> Dict[str, Any]:
        e = self._envs.get(env)
        if not e:
            return {"deployed": False, "reason": "unknown environment"}
        if e.locked:
            return {"deployed": False, "reason": "environment locked"}
        e.deployed_version = version
        return {"deployed": True, "environment": env, "version": version}

    def pass_gate(self, env: str, check: str) -> bool:
        e = self._envs.get(env)
        if not e or check not in e.gate_checks:
            return False
        if check not in e.passed_gates:
            e.passed_gates.append(check)
        return True

    def can_promote(self, from_env: str, to_env: str) -> Dict[str, Any]:
        src = self._envs.get(from_env)
        dst = self._envs.get(to_env)
        if not src or not dst:
            return {"allowed": False, "reason": "unknown environment"}
        if dst.order <= src.order:
            return {"allowed": False, "reason": "not a forward promotion"}
        if dst.order != src.order + 1:
            return {"allowed": False, "reason": "must promote one stage at a time"}
        if not src.deployed_version:
            return {"allowed": False, "reason": "nothing deployed in source"}
        missing = [g for g in src.gate_checks if g not in src.passed_gates]
        if missing:
            return {"allowed": False, "reason": f"gates not passed: {missing}"}
        if dst.locked:
            return {"allowed": False, "reason": "target environment locked"}
        return {"allowed": True, "version": src.deployed_version}

    def promote(self, from_env: str, to_env: str) -> Dict[str, Any]:
        check = self.can_promote(from_env, to_env)
        if not check["allowed"]:
            return {"promoted": False, **check}
        result = self.deploy(to_env, check["version"])
        if result["deployed"]:
            self._promotions.append({
                "from": from_env, "to": to_env,
                "version": check["version"], "timestamp_ns": time.time_ns(),
            })
            self._envs[from_env].passed_gates.clear()
        return {"promoted": True, "version": check["version"], "from": from_env, "to": to_env}

    def lock(self, env: str, locked: bool = True) -> bool:
        e = self._envs.get(env)
        if not e:
            return False
        e.locked = locked
        return True

    def resolved_config(self, env: str, base: Dict[str, Any]) -> Dict[str, Any]:
        e = self._envs.get(env)
        merged = dict(base)
        if e:
            merged.update(e.config_overlay)
        return merged

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "environment-card",
            "environments": {n: e.to_dict() for n, e in sorted(self._envs.items(), key=lambda kv: kv[1].order)},
            "promotions": len(self._promotions),
            "recent": self._promotions[-3:],
        }
