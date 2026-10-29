"""Shader compiler.
Emits era-aware shader stubs with optical uniforms.
"""
from typing import Any, Dict

class ShaderCompiler:
    def compile(self, era: str, mode: str, optical: float) -> Dict[str, Any]:
        uniforms = {"optical": optical, "scale": 1.0}
        if mode == "4d":
            uniforms["time"] = 0.0
        return {
            "era": era,
            "mode": mode,
            "uniforms": uniforms,
            "stages": ["vertex", "fragment"],
            "schema": "skeleton.shader.v1",
        }
