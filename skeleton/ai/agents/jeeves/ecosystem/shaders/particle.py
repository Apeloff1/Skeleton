"""Shader: particle.
"""
from __future__ import annotations

NAME = "particle"

def compile(era: str = "ash", mode: str = "2.9D") -> dict:
    if not era:
        return {"ok": False, "reason": "empty_era"}
    uniforms = ["u_time", "u_optical"]
    if mode == "4D":
        uniforms.append("u_time_axis")
    return {"ok": True, "shader": NAME, "era": era, "mode": mode, "uniforms": uniforms}
