"""Advanced shader 0059.
"""
from __future__ import annotations

SHADER = "adv_shader_0059"

def compile(era: str = "ash") -> dict:
    if not era:
        return {"ok": False, "reason": "empty_era"}
    uniforms = ["u_time", "u_optical", "u_era"]
    return {"ok": True, "shader": SHADER, "era": era, "uniforms": uniforms}
