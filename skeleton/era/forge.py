"""GameForgeRun.execute always stamps reference + reference_card."""

from __future__ import annotations

from skeleton.era.bind import era_bind


class GameForgeRun:
    def execute(self, vision: str = "extraction", project_root: str | None = None) -> dict:
        bound = era_bind.resolve(vision)
        if not bound.get("citation") or not bound.get("url"):
            raise ValueError("forge without citation is illegal")
        return {
            "kind": "forge",
            "vision": vision,
            "project_root": project_root,
            "reference": bound["citation"],
            "reference_card": bound,
            "era": bound["era"],
            "url": bound["url"],
            "stored_prose": 0,
        }


def forge(vision: str = "extraction", project_root: str | None = None) -> dict:
    return GameForgeRun().execute(vision, project_root=project_root)
