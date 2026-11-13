"""Source-pinned supervisor: every durable work action rechecks live canon.

This class governs local design-artifact claims only, not deployment,
machine execution, native gameplay, physical evidence or public release.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_fence import pin_source_sections,assert_source_fence
from .studio_ecosystem_journal import WorkJournal
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_filing import submit_local_artifact,review_local_artifact
from .studio_ecosystem_recovery import inspect_resumption
from .studio_ecosystem_work import build_work_graph


class StudioSupervisor:
    def __init__(self, root: Path, project_id: str, *, authorized: bool):
        if not authorized:
            raise PermissionError("studio supervisor requires explicit operator authorization")
        documents=read_blueprint(project_id)
        self.journal=WorkJournal(root,build_work_graph(documents),authorized=True)
        self.spool=ArtifactSpool(root,authorized=True)
        pin_source_sections(self.journal,documents,authorized=True)

    def _fence(self) -> dict[str, object]:
        return assert_source_fence(
            self.journal,read_blueprint(self.journal.project),authorized=True)

    def claim(self, task_id: str, *, worker: str, token: str,
              authorized: bool) -> None:
        if not authorized:
            raise PermissionError("supervised producer claim requires authorization")
        self._fence()
        self.journal.claim(task_id,worker=worker,token=token,authorized=True)

    def submit(self, task_id: str, *, worker: str, token: str,
               chunks: Iterable[bytes], authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("supervised artifact submission requires authorization")
        self._fence()
        artifact=self.spool.ingest(chunks,authorized=True)
        # If source changed during lengthy output streaming, do not associate
        # these bytes with an obsolete task graph.
        self._fence()
        return submit_local_artifact(self.journal,self.spool,task_id=task_id,
                                     worker=worker,token=token,
                                     sha256=artifact["sha256"],authorized=True)

    def review(self, task_id: str, *, reviewer: str, accepted: bool,
               authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("supervised review requires authorization")
        self._fence()
        return review_local_artifact(self.journal,self.spool,task_id=task_id,
                                     reviewer=reviewer,accepted=accepted,
                                     authorized=True)

    def resume(self, *, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("supervised resume requires authorization")
        self._fence()
        return inspect_resumption(self.journal,self.spool,authorized=True)
