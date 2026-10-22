"""One local-first host owner for native Jeeves game-studio production.

Real loaded Jeeves LocalInferenceEngine -> 38-facet questionnaires and
rights-reviewed text/media context -> typed local proposal -> explicit
human approval -> host grants -> existing ToolExecutor / durable runbook.

A host constructs this once per project/session. No model, book, media decoder,
tool permission, or production achievement is fabricated by this wrapper.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from skeleton.ai.runtime.inference.local import LocalInferenceEngine
from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolExecutor, ToolGrant, ToolRegistry,
)
from .creator_runbook_store import CreatorRunbookStore
from .studio_book_memory import ReviewedBookMemory
from .studio_canon_memory import StudioCanonStore
from .studio_creator_source import (
    CreatorProjectSourceStore, register_creator_source_tool,
)
from skeleton.forge.creator.command_surface import CreatorCommand
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
        book_source_root_sha256: str | None = None,
        canon_index: Path | None = None,
        canon_expected_head_sha256: str | None = None,
        source_index: Path | None = None,
        source_export_root: Path | None = None,
    ) -> None:
        identifier(project_id, "project")
        identifier(session_id, "session")
        runbook_directory = Path(runbook_directory)
        if (not runbook_directory.is_absolute()
                or runbook_directory.is_symlink()
                or not runbook_directory.is_dir()):
            raise StudioInteractionError("private existing runbook directory required")
        if len({book_index is None, book_admission_sha256 is None,
                book_source_root_sha256 is None}) != 1:
            raise StudioInteractionError("book index, admission and independent source-root pin must coexist")
        self.directory = runbook_directory
        self.journal = StudioEvidenceJournal(
            Path(journal_path), project_id=project_id, session_id=session_id,
        )
        self.book_memory: ReviewedBookMemory | None = None
        self.canon_memory: StudioCanonStore | None = None
        self.source_store: CreatorProjectSourceStore | None = None
        try:
            if book_index is not None and book_admission_sha256 is not None:
                self.book_memory = ReviewedBookMemory(
                    Path(book_index), project_id=project_id,
                    admission_sha256=book_admission_sha256,
                    expected_source_root_sha256=book_source_root_sha256,
                )
            if canon_index is not None:
                self.canon_memory = StudioCanonStore(
                    Path(canon_index), project_id=project_id,
                    expected_head_sha256=canon_expected_head_sha256,
                )
            elif canon_expected_head_sha256 is not None:
                raise StudioInteractionError("cannot pin a nonexistent project canon")
            if (source_index is None) != (source_export_root is None):
                raise StudioInteractionError("creator source DB and export authority must coexist")
            if source_index is not None and source_export_root is not None:
                self.source_store = CreatorProjectSourceStore(
                    Path(source_index), project_id=project_id,
                    export_root=Path(source_export_root),
                )
            self.controller = JeevesStudioController(self.journal)
            self.model = NativeStudioModel(
                engine, book_memory=self.book_memory,
                canon_memory=self.canon_memory,
                source_store=self.source_store,
            )
        except BaseException:
            if self.source_store is not None:
                self.source_store.close()
            if self.canon_memory is not None:
                self.canon_memory.close()
            if self.book_memory is not None:
                self.book_memory.close()
            self.journal.close()
            raise

    def answer(self, facet: str, response: str, *, actor_id: str) -> dict[str, Any]:
        return self.controller.answer(facet, response, actor_id=actor_id)

    def admit_media(self, **host_media_arguments: Any) -> dict[str, Any]:
        """Real file bytes + verified sidecar, never a model-authored path claim."""
        return admit_reviewed_media(self.controller, **host_media_arguments)

    def revise_canon(
        self, *, subject_id: str, attribute_id: str,
        action: str, expected_fact_sha256: str | None,
        actor_id: str, reviewer_id: str, source_receipt_sha256: str,
        fact: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The authenticated host supplies distinct author and human reviewer."""
        if self.canon_memory is None:
            raise StudioInteractionError("project canon store is not configured")
        return self.canon_memory.revise(
            subject_id=subject_id, attribute_id=attribute_id,
            action=action, expected_fact_sha256=expected_fact_sha256,
            actor_id=actor_id, reviewer_id=reviewer_id,
            source_receipt_sha256=source_receipt_sha256, fact=fact,
        )

    def plan(self, instruction: str, *, max_output_tokens: int = 2048,
             seed: int = 0) -> dict[str, Any]:
        return self.model.plan(
            self.controller, instruction=instruction,
            max_output_tokens=max_output_tokens, seed=seed,
        )

    def approve(self, plan: Mapping[str, Any], *, reviewer_id: str) -> dict[str, Any]:
        """Durable human review ONLY; high-impact grants are still separate."""
        return self.controller.approve(plan, reviewer_id=reviewer_id)

    def register_native_creator_tools(
        self, registry: ToolRegistry, *,
        authorize: Callable[[CreatorCommand, ToolExecutionContext], bool],
    ) -> str:
        """Give the existing host ToolExecutor REAL project-source handlers.

        This installs zero grants and does not approve any model-proposed
        action; every command still requires independent host authorization.
        """
        if self.source_store is None:
            raise StudioInteractionError("host has not supplied a private source store")
        return register_creator_source_tool(
            registry, store=self.source_store, authorize=authorize,
        )

    def verify_real_sprite_import(
        self, *, record_id: str, godot_executable: str, actor_id: str,
        authorize_sprite_import: Callable[[str, str, str, str], bool],
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Verify actual Godot SpriteFrames without granting AI process rights.

        Host checks authorization for the exact project, sprite, binary and
        authenticated reviewer. The model only receives the journal receipt.
        """
        identifier(actor_id, "sprite import reviewer")
        record_id = identifier(record_id, "original sprite source")
        if self.source_store is None:
            raise StudioInteractionError("native sprite source owner is unavailable")
        if (not isinstance(godot_executable, str) or not godot_executable.strip()
                or not callable(authorize_sprite_import)
                or authorize_sprite_import(
                    self.journal.project_id, record_id, godot_executable,
                    actor_id,
                ) is not True):
            raise StudioInteractionError("host denied reviewed Godot sprite verification")
        verified = self.source_store.verify_native_sprite_import(
            record_id, godot_executable=godot_executable,
            timeout_seconds=timeout_seconds,
        )
        proof = self.journal.append(
            "native_sprite_import_verified",
            {**verified, "actor_id": actor_id},
            _authority=self.journal._native_execution_token,
        )
        return {
            **verified, "studio_event_sha256": proof["digest"],
            "host_permission_verified": True,
        }

    def verify_real_player_avatar(
        self, *, binding_record_id: str, godot_executable: str,
        actor_id: str,
        authorize_avatar_execution: Callable[[str, str, str, str], bool],
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Observe real animated player actor, never mint model tool authority."""
        identifier(actor_id, "original game avatar reviewer")
        record_id = identifier(binding_record_id, "player avatar source record")
        if self.source_store is None:
            raise StudioInteractionError("original game's source owner is unavailable")
        if (not isinstance(godot_executable, str) or not godot_executable.strip()
                or not callable(authorize_avatar_execution)
                or authorize_avatar_execution(
                    self.journal.project_id, record_id, godot_executable, actor_id,
                ) is not True):
            raise StudioInteractionError(
                "host denied independent real-engine player avatar observation"
            )
        evidence = self.source_store.verify_native_player_avatar(
            godot_executable=godot_executable,
            expected_binding_record_id=record_id,
            timeout_seconds=timeout_seconds,
        )
        event = self.journal.append(
            "native_player_avatar_verified",
            {**evidence, "actor_id": actor_id},
            _authority=self.journal._native_execution_token,
        )
        return {
            **evidence, "studio_event_sha256": event["digest"],
            "host_permission_verified": True,
        }

    def verify_real_native_gameplay(
        self, *, godot_executable: str,
        actor_id: str, authorize_native_execution: Callable[[str, str, str], bool],
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Run the ACTUAL Godot 4 engine after separate host authorization.

        The model has no general process-launch tool here; a real producer
        authenticates the actor and exact binary before this method is called.
        """
        identifier(actor_id, "native engine reviewer")
        if self.source_store is None:
            raise StudioInteractionError("original game source owner is unavailable")
        if (not isinstance(godot_executable, str) or not godot_executable.strip()
                or not callable(authorize_native_execution)
                or authorize_native_execution(
                    self.journal.project_id, godot_executable, actor_id,
                ) is not True):
            raise StudioInteractionError("host denied independently reviewed Godot execution")
        result = self.source_store.run_native_playthrough(
            godot_executable=godot_executable, timeout_seconds=timeout_seconds,
        )
        event = self.journal.append(
            "native_gameplay_verified",
            {**result, "actor_id": actor_id},
            _authority=self.journal._native_execution_token,
        )
        return {
            **result, "studio_event_sha256": event["digest"],
            "host_permission_verified": True,
        }

    def _require_fresh_native_plan(self, plan: Mapping[str, Any],
                                   restored: Mapping[str, Any] | None) -> None:
        """Bind every real effect to the native plan's verified input generation.

        A source changed by a PREVIOUS successful command in this SAME plan
        remains permissible. Mutations by any other producer invalidate the
        proposal and require a new local deliberation and approval. External
        rights/canon changes always invalidate the proposal.
        """
        plan_sha = plan["plan_sha256"]
        matches = [
            event["payload"] for event in self.journal.read()
            if event["kind"] == "plan_context_bound"
            and event["payload"].get("plan_sha256") == plan_sha
        ]
        if len(matches) != 1:
            raise StudioInteractionError(
                "native proposal has no unique trusted source-generation binding"
            )
        pinned = matches[0]
        if self.book_memory is not None:
            if (pinned["book_admission_sha256"] != self.book_memory.admission_sha256
                    or pinned["book_source_root_sha256"] !=
                    self.book_memory.expected_source_root_sha256
                    or pinned["book_rights_head_sha256"] !=
                    self.book_memory.rights_policy_head()):
                raise StudioInteractionError(
                    "book admission or rights changed since this native model proposal"
                )
        elif pinned["book_admission_sha256"] is not None:
            raise StudioInteractionError("native plan's reviewed book source is unavailable")
        if self.canon_memory is not None:
            if (pinned["canon_head_sha256"] !=
                    self.canon_memory.head_identity()):
                raise StudioInteractionError(
                    "project canon changed since this native model proposal"
                )
        elif pinned["canon_head_sha256"] is not None:
            raise StudioInteractionError("native plan's reviewed project canon is absent")
        if self.source_store is None:
            if pinned["creator_source_head_sha256"] is not None:
                raise StudioInteractionError("native plan's creator source owner is absent")
            return
        # No independent project edits may appear, except commands whose
        # real receipts were already durably marked succeeded by this runbook.
        allowed: set[str] = set()
        if restored is not None:
            successful = {
                item["step_id"] for item in restored["steps"]
                if item["status"] == "succeeded"
            }
            allowed = {
                step["command"]["digest"] for step in plan["steps"]
                if step["step_id"] in successful
            }
        delta = self.source_store.mutations_after(
            pinned["creator_source_head_sha256"], limit=32,
        )
        if any(item["command_sha256"] not in allowed for item in delta):
            raise StudioInteractionError(
                "another editor changed actual game source after native deliberation"
            )

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
            self._require_fresh_native_plan(plan, store.load())
            return execute_approved_studio_batch(
                self.controller, plan, executor=executor, store=store,
                host_grants=host_grants, max_steps=max_steps,
                before_step=lambda _step: self._require_fresh_native_plan(
                    plan, store.load(),
                ),
            )

    def audit(self) -> dict[str, Any]:
        """Read and reverify the project/session history and optional book index."""
        events = self.journal.read()
        book = self.book_memory.verify() if self.book_memory is not None else None
        canon = self.canon_memory.verify() if self.canon_memory is not None else None
        source = self.source_store.snapshot() if self.source_store is not None else None
        report = {
            "schema_version": "skeleton.jeeves.native_studio_host_audit.v1",
            "project_id": self.journal.project_id,
            "session_id": self.journal.session_id,
            "events": len(events),
            "last_event_sha256": events[-1]["digest"] if events else None,
            "reviewed_book_memory": book,
            "reviewed_game_canon": canon,
            "source_authoring_state": source,
            "standalone_native_owner": True,
            "production_game_complete": False,
        }
        report["audit_sha256"] = digest(report)
        return report

    def close(self) -> None:
        if self.source_store is not None:
            self.source_store.close()
        if self.canon_memory is not None:
            self.canon_memory.close()
        if self.book_memory is not None:
            self.book_memory.close()
        self.journal.close()

    def __enter__(self) -> "NativeStudioHost":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["NativeStudioHost"]
