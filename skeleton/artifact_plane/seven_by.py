"""GB-8b SEVEN_BY archive auditor. Root volumes fail closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.artifact_plane.cards import plane_card
from skeleton.artifact_plane.sprawl import RootSprawlIndex

ARCHIVE_LANE = "docs/archive/seven_by"
INDEX_NAME = "SEVEN_BY_INDEX.md"


class SevenByAuditor:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.index = RootSprawlIndex(self.root)

    def audit(self) -> dict[str, Any]:
        stray = self.index.seven_by_root()
        lane = self.root / ARCHIVE_LANE
        index_path = lane / INDEX_NAME
        hit = 1 if not stray and lane.is_dir() and index_path.is_file() else 0
        return plane_card(
            kind="seven-by-archive",
            hit=hit,
            law="GB-8b",
            citation="docs/ARTIFACT_PLANE.md",
            extra={
                "stray_root": self.index.names(stray),
                "lane": ARCHIVE_LANE,
                "lane_present": lane.is_dir(),
                "index_present": index_path.is_file(),
            },
        )

    def fail_closed(self) -> int:
        return 0 if self.audit().get("hit") == 1 else 2
