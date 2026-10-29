"""Particle emitter. Optical and combat particles."""
from typing import Any, Dict
class ParticleEmitter:
    def emit(self, kind: str, count: int = 8) -> Dict[str, Any]:
        return {"kind": kind, "count": count, "optical_tag": kind}
