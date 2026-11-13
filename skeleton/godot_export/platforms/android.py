"""Android export: APK/AAB zip with manifest and classes."""
from __future__ import annotations

import zipfile
from pathlib import Path

from .base import PlatformSpec, require_pattern

PACKAGE = r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+"


def check_artifact(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
    except zipfile.BadZipFile:
        return [f"{path.name} is not a zip"]
    if path.suffix == ".aab":
        need = ("base/manifest/AndroidManifest.xml",)
    else:
        need = ("AndroidManifest.xml", "classes.dex")
    missing = [n for n in need if n not in names]
    pck = any(n.endswith(".pck") or n.startswith("assets/") for n in names)
    out = [f"{path.name} missing {m}" for m in missing]
    if not pck:
        out.append(f"{path.name} has no packed game assets")
    return out


def _min_sdk(preset) -> list[str]:
    v = preset.option("gradle_build/min_sdk")
    if v in (None, ""):
        return []
    try:
        return [] if int(v) >= 24 else [f"min_sdk {v} below Godot 4 floor 24"]
    except (TypeError, ValueError):
        return [f"min_sdk {v!r} not an integer"]


SPEC = PlatformSpec(
    name="Android",
    extensions=(".apk", ".aab"),
    option_checks=(require_pattern("package/unique_name", PACKAGE, required=True), _min_sdk),
    artifact_check=check_artifact,
)
