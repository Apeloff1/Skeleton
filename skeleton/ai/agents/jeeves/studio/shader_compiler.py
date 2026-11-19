"""Shader compiler.
Emits era-aware shader stubs with optical uniforms.
"""
from typing import Any, Dict

_MODES = {"2D", "2.9D", "3D", "4d"}


class ShaderCompiler:
    def compile(self, era: str, mode: str, optical: float) -> Dict[str, Any]:
        if mode not in _MODES:
            return {"ok": False, "reason": "bad_mode", "era": era, "mode": mode, "schema": "skeleton.shader.v1"}
        if isinstance(optical, bool) or not isinstance(optical, (int, float)) or optical < 0 or optical > 1:
            return {"ok": False, "reason": "bad_optical", "era": era, "mode": mode, "schema": "skeleton.shader.v1"}
        uniforms = {"optical": float(optical), "scale": 1.0}
        if mode == "4d":
            uniforms["time"] = 0.0
        source = (
            "shader_type canvas_item;\n"
            f"uniform float optical = {float(optical)};\n"
            "void fragment() {\n"
            "    COLOR = vec4(optical, optical, optical, 1.0);\n"
            "}\n"
        )
        return {
            "ok": True,
            "era": era,
            "mode": mode,
            "uniforms": uniforms,
            "stages": ["vertex", "fragment"],
            "source": source,
            "schema": "skeleton.shader.v1",
            "reason": "ok",
        }
