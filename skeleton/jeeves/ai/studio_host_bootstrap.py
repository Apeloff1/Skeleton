"""One local-first host owner for native Jeeves game-studio production.

Real loaded Jeeves LocalInferenceEngine -> 38-facet questionnaires and
rights-reviewed text/media context -> typed local proposal -> explicit
human approval -> host grants -> existing ToolExecutor / durable runbook.

A host constructs this once per project/session. No model, book, media decoder,
tool permission, or production achievement is fabricated by this wrapper.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skeleton.ai.runtime.inference.local import LocalInferenceEngine
from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolExecutor, ToolGrant,
)
from .creator_runbook_store import CreatorRunbookStore
from .studio_book_memory import ReviewedBookMemory
from .studio_delegate_executor import execute_approved_studio_batch
from .studio_interaction_contract import (
    JeevesStudioController, StudioEvidenceJournal, StudioInteractionError,
    identifier, digest,
)
from .studio_multimodal_intake import admit_reviewed_media
from .studio_native_model import NativeStudioModel


class NativeStudioHost:
    """Real app-owned local Jeeves session, not a second inference authority."""

    def __init__(
        self, engine: LocalInferenceEngine, *,
        project_id: str, session_id: str, journal_path: Path,
        runbook_directory: Path,
        book_index: Path | None = None,
        book_admission_sha256: str | None = None,
    ) -> None:
        identifier(project_id, "project")
        identifier(session_id, "session")
        runbook_directory = Path(runbook_directory)
        if (not runbook_directory.is_absolute()
                or runbook_directory.is_symlink()
                or not runbook_directory.is_dir()):
            raise StudioInteractionError("private existing runbook directory required")
        if (book_index is None) != (book_admission_sha256 is None):
            raise StudioInteractionError("book index and independently pinned admission must coexist")
        self.directory = runbook_directory
        self.journal = StudioEvidenceJournal(
            Path(journal_path), project_id=project_id, session_id=session_id,
        )
        self.book_memory: ReviewedBookMemory | None = None
        try:
            if book_index is not None and book_admission_sha256 is not None:
                self.book_memory = ReviewedBookMemory(
                    Path(book_index), project_id=project_id,
                    admission_sha256=book_admission_sha256,
                )
            self.controller = JeevesStudioController(self.journal)
            self.model = NativeStudioModel(engine, book_memory=self.book_memory)
        except BaseException:
            if self.book_memory is not None:
                self.book_memory.close()
            self.journal.close()
            raise

    def answer(self, facet: str, response: str, *, actor_id: str) -> dict[str, Any]:
        return self.controller.answer(facet, response, actor_id=actor_id)

    def admit_media(self, **host_media_arguments: Any) -> dict[str, Any]:
        """Real file bytes + verified sidecar, never a model-authored path claim."""
        return admit_reviewed_media(self.controller, **host_media_arguments)

    def plan(self, instruction: str, *, max_output_tokens: int = 2048,
             seed: int = 0) -> dict[str, Any]:
        return self.model.plan(
            self.controller, instruction=instruction,
            max_output_tokens=max_output_tokens, seed=seed,
        )

    def approve(self, plan: Mapping[str, Any], *, reviewer_id: str) -> dict[str, Any]:
        """Durable human review ONLY; high-impact grants are still separate."""
        return self.controller.approve(plan, reviewer_id=reviewer_id)

    def execute_authorized(
        self, plan: Mapping[str, Any], *,
        executor: ToolExecutor,
        host_grants: Mapping[str, tuple[ToolExecutionContext, ToolGrant]],
        max_steps: int = 8,
    ) -> dict[str, Any]:
        """Resume exact verified plan state; never auto mint a grant."""
        from .creator_runbook_runtime import CreatorRunbook
        contract = CreatorRunbook(plan)
        if contract.project_id != self.journal.project_id:
            raise StudioInteractionError("cannot execute another game project's plan")
        # One independent host store per immutable plan. Reopening this file
        # automatically reconciles prior completed/uncertain effects.
        file = self.directory / ("jeeves-" + contract.plan_sha256 + ".sqlite")
        if file.is_symlink():
            raise StudioInteractionError("runbook persistence path cannot be a symlink")
        with CreatorRunbookStore(
            file, plan_sha256=contract.plan_sha256,
        ) as store:
            return execute_approved_studio_batch(
                self.controller, plan, executor=executor, store=store,
                host_grants=host_grants, max_steps=max_steps,
            )

    def audit(self) -> dict[str, Any]:
        """Read and reverify the project/session history and optional book index."""
        events = self.journal.read()
        book = self.book_memory.verify() if self.book_memory is not None else None
        report = {
            "schema_version": "skeleton.jeeves.native_studio_host_audit.v1",
            "project_id": self.journal.project_id,
            "session_id": self.journal.session_id,
            "events": len(events),
            "last_event_sha256": events[-1]["digest"] if events else None,
            "reviewed_book_memory": book,
            "standalone_native_owner": True,
            "production_game_complete": False,
        }
        report["audit_sha256"] = digest(report)
        return report

    def close(self) -> None:
        if self.book_memory is not None:
            self.book_memory.close()
        self.journal.close()

    def __enter__(self) -> "NativeStudioHost":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["NativeStudioHost"]
