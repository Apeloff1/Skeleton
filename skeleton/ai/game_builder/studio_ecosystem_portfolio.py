"""Private per-project workspace isolation for the original studio catalog.

Each project uses its own source-bound journal and artifact spool. A project
cannot accidentally adopt another project's SQLite state or output directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .studio_ecosystem_catalog import IDENT, catalog_index, StudioEcosystemError
from .studio_ecosystem_journal import _private_directory
from .studio_ecosystem_supervisor import StudioSupervisor
from .studio_ecosystem_quest import StudioQuestError


class StudioPortfolio:
    def __init__(self, root: Path, *, authorized: bool):
        if not authorized:
            raise PermissionError("portfolio access requires operator authorization")
        self.root=Path(root)
        _private_directory(self.root)
        self.projects=self.root/"projects"
        self.projects.mkdir(mode=0o700,exist_ok=True)
        _private_directory(self.projects)
        self.registered=frozenset(record["id"] for record in catalog_index())

    def project_root(self, project_id: str) -> Path:
        if (not isinstance(project_id,str) or not IDENT.fullmatch(project_id)
                or project_id not in self.registered):
            raise StudioEcosystemError("portfolio project not in authoritative registry")
        target=self.projects/project_id
        if target.is_symlink():
            raise StudioQuestError("linked portfolio workspace")
        target.mkdir(mode=0o700,exist_ok=True)
        _private_directory(target)
        return target

    def open(self, project_id: str, *, authorized: bool) -> StudioSupervisor:
        if not authorized:
            raise PermissionError("project open requires authorization")
        return StudioSupervisor(self.project_root(project_id),project_id,
                                authorized=True)

    def inspect_registered_workspaces(self) -> Iterator[dict[str, object]]:
        """Yield one row at a time; never invent completed project status."""
        from os import scandir
        with scandir(self.projects) as children:
            for entry in children:
                if entry.name not in self.registered:
                    raise StudioQuestError("unknown directory in private portfolio")
                directory=Path(entry.path)
                _private_directory(directory)
                yield {"project_id":entry.name,
                       "journal_present":(directory/"studio_work.sqlite3").is_file(),
                       "release_certified":False}
