"""skeleton/artifact/plane_100x_v2.py
Further 100x extreme Artifact plane.
Godot binaries and Track E root sprawl off main. Pointer files, LFS or external URL.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class PlaneError(Exception):
    pass

class ArtifactPlane100xV2:
    def pointer_binary(self, path: str) -> str:
        if any(path.endswith(ext) for ext in (".exe", ".bin", ".godot", ".pck")):
            return hashlib.sha256(path.encode()).hexdigest()
        raise PlaneError("not binary or not allowed on main")
