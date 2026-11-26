"""
Keep Godot binaries and Track E root sprawl off main. Pointer files, LFS or external URL, archive root tests and SEVEN_BY docs, plane audit.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

PLANE = "ARTIFACT_PLANE"
_BINARIES = (".exe", ".dll", ".dylib", ".so", ".pck", ".apk", ".wasm")


def process(data: dict) -> dict:
    refused = admit("artifact_plane", data)
    if refused:
        return refused
    path = data.get("path")
    if path is None:
        return stamp("artifact_plane", data, {"plane": PLANE})
    lowered = path.lower() if isinstance(path, str) else ""
    if (
        not isinstance(path, str)
        or not path
        or len(path) > 240
        or ".." in path
        or path.startswith(("/", "\\"))
        or "\\" in path
        or any(ord(ch) < 32 for ch in path)
        or lowered.endswith(_BINARIES)
    ):
        return {
            "ok": False,
            "error": "binary stays off the plane",
            "card": "artifact_plane",
            "plane": PLANE,
        }
    return stamp("artifact_plane", data, {"plane": PLANE, "path": path})
