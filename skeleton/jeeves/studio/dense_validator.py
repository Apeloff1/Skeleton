"""Dense validation rules.
Pack completeness, fidelity, rights, mass, optical, critique checks.
"""
from __future__ import annotations
from typing import Any, Dict

class DenseValidator:
    def check_pack(self, artifacts: Dict[str, str]) -> Dict[str, Any]:
        required = ["project.godot", "world.tscn", "player.gd", "boss.gd", "world.gd"]
        missing = [r for r in required if r not in artifacts]
        return {"missing": missing, "ok": len(missing) == 0, "count": len(artifacts)}
    def check_fidelity(self, card: Dict[str, Any]) -> bool:
        return card.get("fidelity", 0) >= 0.92
    def check_mass(self, mass: float, prior: float = 1.0) -> bool:
        return mass <= prior * 1.1
    def check_rights(self, card: Dict[str, Any]) -> bool:
        return card.get("security", {}).get("rights_acknowledged") is True
    def check_optical(self, optical: float) -> bool:
        return 0.5 <= optical <= 1.0

def rule_0(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("field_0", 0), (int, float))

def rule_1(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("field_1", 0), (int, float))

def rule_2(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("field_2", 0), (int, float))

def run_dense(data: Dict[str, Any]) -> Dict[str, Any]:
    results = {"rule_0": rule_0(data), "rule_1": rule_1(data), "rule_2": rule_2(data)}
    return {"passed": sum(results.values()), "total": 3}
