"""Structural mirror of the project bundle history API (read-only reference:
``skeleton/ai/game_builder/project_bundle/{history,project_save}.py`` at
eb310c4f on feat/mb-project-bundle-oyvind-20261031). Inject a real
``ProjectHistory(ProjectSaver(plane))``; tests use an in-memory fake.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


class ManifestLike(Protocol):
    sequence: int
    label: str | None
    content_digest: str


class VersionLike(Protocol):
    manifest: ManifestLike
    files: Mapping[str, str]
    sections: Mapping[str, Any]


class VersionEntryLike(Protocol):
    sequence: int
    label: str | None
    content_digest: str
    files: int


@runtime_checkable
class ProjectSaverLike(Protocol):
    # ProjectSaver.save_files - "save version"
    def save_files(self, project_id: str, genre: str, files: Mapping[str, str], *,
                   sequence: int | None = None, label: str | None = None,
                   extra_sections: Mapping[str, Mapping[str, Any]] | None = None) -> ManifestLike: ...

    # ProjectSaver.load
    def load(self, project_id: str, *, sequence: int | None = None) -> VersionLike: ...


@runtime_checkable
class ProjectHistoryLike(Protocol):
    saver: ProjectSaverLike

    def versions(self, project_id: str) -> list[VersionEntryLike]: ...

    def find_label(self, project_id: str, label: str) -> int: ...

    def label(self, project_id: str, sequence: int, label: str) -> ManifestLike: ...

    def rollback(self, project_id: str, sequence: int, *, workspace: Any = None,
                 human_approved: bool = False, authorized: bool = False) -> dict[str, Any]: ...
