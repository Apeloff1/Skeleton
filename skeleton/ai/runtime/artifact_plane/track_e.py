"""Track E auditor. Move-not-delete law for root *_test.py files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.artifact_plane.cards import plane_card
from skeleton.artifact_plane.sprawl import RootSprawlIndex


class TrackEAuditor:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.index = RootSprawlIndex(self.root)

    def audit(self) -> dict[str, Any]:
        stray = self.index.stray_root_tests()
        bak = self.index.stray_bak()
        lanes = self.index.archive_lanes_present()
        hit = 1 if not stray and not bak and any(lanes.values()) else 0
        return plane_card(
            kind="track-e",
            hit=hit,
            law="GB-8",
            citation="docs/ARTIFACT_PLANE.md",
            extra={
                "stray_root_tests": self.index.names(stray),
                "stray_bak": self.index.names(bak),
                "archive_lanes": lanes,
                "seven_by_deferred": self.index.names(self.index.seven_by_root()),
            },
        )

    def fail_closed(self) -> int:
        card = self.audit()
        return 0 if card["hit"] == 1 else 2
