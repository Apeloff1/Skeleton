"""Composite artifact plane surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.artifact_plane.cards import plane_card
from skeleton.artifact_plane.godot_locate import GodotLocator
from skeleton.artifact_plane.seven_by import SevenByAuditor
from skeleton.artifact_plane.track_e import TrackEAuditor


class ArtifactPlane:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd()
        self.track_e = TrackEAuditor(self.root)
        self.seven_by = SevenByAuditor(self.root)
        self.godot = GodotLocator(self.root)

    def snapshot(self) -> dict[str, Any]:
        track = self.track_e.audit()
        seven = self.seven_by.audit()
        godot = self.godot.locate()
        # The composite plane is fail-closed across every archive policy that it
        # exposes.  Reporting a failing child card while keeping the parent hit
        # green would let callers that gate only on the composite card bypass
        # the GB-8b root-sprawl policy.
        hit = 1 if track.get("hit") == 1 and seven.get("hit") == 1 else 0
        return plane_card(
            kind="artifact-plane",
            hit=hit,
            law="GB-8/GB-8b",
            citation="docs/ARTIFACT_PLANE.md",
            extra={"track_e": track, "seven_by": seven, "godot": godot},
        )
