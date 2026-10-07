"""Artifact plane — Track E sprawl gate and Godot locate cards.

Import of this package must stay cheap and must not require a Godot
binary, torch, or network. Missing binaries return found=0 cards.
"""

from __future__ import annotations

from skeleton.artifact_plane.cards import plane_card
from skeleton.artifact_plane.godot_locate import GodotLocator, locate as godot_locate
from skeleton.artifact_plane.plane import ArtifactPlane
from skeleton.artifact_plane.seven_by import SevenByAuditor
from skeleton.artifact_plane.sprawl import RootSprawlIndex
from skeleton.artifact_plane.track_e import TrackEAuditor
from skeleton.artifact_plane.usage import ArtifactUsageMeter

__all__ = [
    "ArtifactPlane",
    "ArtifactUsageMeter",
    "GodotLocator",
    "RootSprawlIndex",
    "SevenByAuditor",
    "TrackEAuditor",
    "godot_locate",
    "plane_card",
]
