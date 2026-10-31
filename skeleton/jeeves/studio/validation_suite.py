"""Validation and critique subsystem.
Pack completeness, fidelity, rights, mass clips.
"""
from __future__ import annotations
from typing import Any, Dict

class PackValidator:
    def check_files(self, artifacts: Dict[str, str]) -> Dict[str, Any]:
        required = ["project.godot", "world.tscn", "player.gd", "boss.gd"]
        missing = [r for r in required if r not in artifacts]
        return {"missing": missing, "ok": len(missing)==0}
    def check_fidelity(self, card: Dict[str, Any]) -> bool:
        return card.get("fidelity", 0) >= 0.92
    def check_rights(self, card: Dict[str, Any]) -> bool:
        return card.get("security", {}).get("rights_acknowledged") is True

def rule_0(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("field_0", 0), (int, float))

def rule_1(data: Dict[str, Any]) -> bool:
    return isinstance(data.get("field_1", 0), (int, float))

def run_all(data: Dict[str, Any]) -> Dict[str, Any]:
    results = {"rule_0": rule_0(data), "rule_1": rule_1(data)}
    return {"passed": sum(results.values()), "total": 2}
