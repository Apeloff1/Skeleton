"""Version list, labels and rollback over save-plane sequences.

Versions are whatever ``GameSavePlane.backups()`` still retains (bounded by
the store's ``retain``); rollback is ``restore(sequence=)`` followed by an
optional reviewed write-back, or a re-save as a new head version.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace

from .manifest import BundleError, BundleManifest
from .project_save import ProjectSaver, slot_for


@dataclass(frozen=True, slots=True)
class VersionEntry:
    sequence: int
    label: str | None
    content_digest: str
    files: int


class ProjectHistory:
    def __init__(self, saver: ProjectSaver) -> None:
        self.saver = saver

    def sequences(self, project_id: str) -> tuple[int, ...]:
        return self.saver.plane.backups(slot_for(project_id))

    def versions(self, project_id: str) -> list[VersionEntry]:
        out = []
        for seq in self.sequences(project_id):
            m = self.saver.load(project_id, sequence=seq).manifest
            out.append(VersionEntry(seq, m.label, m.content_digest, len(m.files)))
        return out

    def find_label(self, project_id: str, label: str) -> int:
        hits = [v.sequence for v in self.versions(project_id) if v.label == label]
        if not hits:
            raise BundleError(f"no retained version labelled {label!r}")
        return hits[-1]

    def label(self, project_id: str, sequence: int, label: str) -> BundleManifest:
        """Labels are immutable per save, so labelling re-saves that content as a new head."""
        v = self.saver.load(project_id, sequence=sequence)
        extra = {k: s for k, s in v.sections.items() if k not in ("bundle", "files")}
        return self.saver.save_files(project_id, v.manifest.genre, v.files, label=label,
                                     extra_sections=extra)

    def rollback(self, project_id: str, sequence: int, *, workspace: GameWorkspace | None = None,
                 human_approved: bool = False, authorized: bool = False) -> dict[str, Any]:
        """Make ``sequence`` the new head (history is append-only) and optionally write it back."""
        # Reject unapproved workspace rollback before publishing a new save
        # head. Previously the save-plane history advanced before the later
        # restore_to_workspace approval gate raised PermissionError.
        if workspace is not None and (not authorized or human_approved is not True):
            raise PermissionError("workspace rollback needs explicit human approval")
        v = self.saver.load(project_id, sequence=sequence)
        extra = {k: s for k, s in v.sections.items() if k not in ("bundle", "files")}
        head = self.saver.save_files(project_id, v.manifest.genre, v.files,
                                     label=f"rollback-of-{sequence}", extra_sections=extra)
        result: dict[str, Any] = {"rolled_back_to": sequence, "new_head": head.sequence,
                                  "files_match": head.file_map() == v.manifest.file_map()}
        if workspace is not None:
            result["workspace"] = self.saver.restore_to_workspace(
                workspace, project_id, sequence=head.sequence,
                human_approved=human_approved, authorized=authorized)
        return result


__all__ = ["ProjectHistory", "VersionEntry"]
