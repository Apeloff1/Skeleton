"""macOS export: .zip / .dmg / .app bundle."""
from __future__ import annotations

import zipfile
from pathlib import Path

from .base import PlatformSpec, read_head, require_pattern

BUNDLE_ID = r"[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+"


def check_artifact(path: Path) -> list[str]:
    if path.is_dir():
        if not (path / "Contents" / "Info.plist").is_file():
            return [f"{path.name} bundle lacks Contents/Info.plist"]
        return []
    if path.suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return [f"{path.name} is not a zip"]
        if not any(n.endswith(".app/Contents/Info.plist") for n in names):
            return [f"{path.name} has no .app/Contents/Info.plist"]
        return []
    if path.suffix == ".dmg":
        return [] if read_head(path, 1) else [f"{path.name} empty"]
    return [f"unexpected macOS artifact {path.name}"]


def _no_notarize_without_codesign(preset) -> list[str]:
    if preset.option("notarization/notarization") not in (None, 0) and preset.option("codesign/codesign") in (None, 0):
        return ["notarization enabled without codesign"]
    return []


SPEC = PlatformSpec(
    name="macOS",
    extensions=(".zip", ".dmg", ".app"),
    option_checks=(require_pattern("application/bundle_identifier", BUNDLE_ID, required=True),
                   _no_notarize_without_codesign),
    artifact_check=check_artifact,
)
