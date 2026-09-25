"""Artifact-surface routing for assistant-created deliverables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import ArtifactKind


@dataclass(frozen=True, slots=True)
class ArtifactRoute:
    kind: ArtifactKind
    capability_id: str
    binary_output: bool
    requires_source_materialization: bool = False


class ArtifactRouter:
    """Map artifact intent to a configured capability without format guessing."""

    DEFAULTS: Mapping[ArtifactKind, ArtifactRoute] = {
        ArtifactKind.DOCUMENT: ArtifactRoute(
            ArtifactKind.DOCUMENT, "artifact.document", True
        ),
        ArtifactKind.SPREADSHEET: ArtifactRoute(
            ArtifactKind.SPREADSHEET, "artifact.spreadsheet", True
        ),
        ArtifactKind.PRESENTATION: ArtifactRoute(
            ArtifactKind.PRESENTATION, "artifact.presentation", True
        ),
        ArtifactKind.PDF: ArtifactRoute(
            ArtifactKind.PDF, "artifact.pdf", True
        ),
        ArtifactKind.IMAGE: ArtifactRoute(
            ArtifactKind.IMAGE, "media.image_generation", True
        ),
        ArtifactKind.CODE: ArtifactRoute(
            ArtifactKind.CODE, "artifact.code", False
        ),
        ArtifactKind.OTHER: ArtifactRoute(
            ArtifactKind.OTHER, "artifact.generic", True
        ),
    }

    def __init__(self, overrides: Mapping[ArtifactKind, ArtifactRoute] | None = None) -> None:
        self._routes = dict(self.DEFAULTS)
        for raw_kind, route in dict(overrides or {}).items():
            kind = raw_kind if isinstance(raw_kind, ArtifactKind) else ArtifactKind(str(raw_kind))
            if not isinstance(route, ArtifactRoute) or route.kind is not kind:
                raise ValueError("artifact route override kind mismatch")
            self._routes[kind] = route

    def resolve(
        self,
        kind: ArtifactKind,
        *,
        editing_existing: bool = False,
    ) -> ArtifactRoute:
        normalized = kind if isinstance(kind, ArtifactKind) else ArtifactKind(str(kind))
        route = self._routes[normalized]
        if editing_existing and not route.requires_source_materialization:
            return ArtifactRoute(
                kind=route.kind,
                capability_id=route.capability_id,
                binary_output=route.binary_output,
                requires_source_materialization=True,
            )
        return route


__all__ = ["ArtifactRoute", "ArtifactRouter"]
