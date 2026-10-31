"""Mesh simplifier.
Optical-weighted vertex reduction.
"""
from typing import Any, Dict

class MeshSimplifier:
    def simplify(self, verts: int, optical: float) -> Dict[str, Any]:
        if not isinstance(verts, int) or verts < 1:
            return {"ok": False, "reason": "bad_verts", "schema": "skeleton.mesh.v1"}
        kept = int(verts * (0.5 + optical*0.5))
        return {"ok": True, "original": verts, "kept": kept, "optical": optical, "reason": "ok", "schema": "skeleton.mesh.v1"}
