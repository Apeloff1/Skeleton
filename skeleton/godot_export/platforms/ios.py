"""iOS export: Xcode project; needs macOS host, so never exported on Linux CI."""
from __future__ import annotations

from pathlib import Path

from .base import PlatformSpec, require_pattern
from .macos import BUNDLE_ID


def check_artifact(path: Path) -> list[str]:
    proj = path.with_suffix(".xcodeproj")
    return [] if proj.exists() else [f"missing {proj.name}"]


SPEC = PlatformSpec(
    name="iOS",
    extensions=(".ipa", ".xcodeproj"),
    option_checks=(require_pattern("application/bundle_identifier", BUNDLE_ID, required=True),
                   require_pattern("application/app_store_team_id", r"[A-Z0-9]{10}")),
    artifact_check=check_artifact,
    export_on_linux=False,
)
