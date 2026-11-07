"""Edit session: apply, always revalidate, undo/redo, b038 provenance, history."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.gameforge.batch_b038 import (
    EvalRecord, GenerationProvenance, ProvenanceLedger, SourceRef, Transformation, digest,
)

from ..validate.scoring import ACCEPT, REGENERATE, REPAIR, Thresholds, Verdict, score_plan
from .diff import DiffError, PlanDiff, apply_diff, invert
from .model_edit import EditPlanner, EditProposal
from .protocol import ProjectHistoryLike

PLAN_FILE = "game_plan.json"
SECTION = "ai_builder_edit"


@dataclass(frozen=True)
class EditRecord:
    seq: int
    instruction: str
    diff: PlanDiff
    inverse: PlanDiff
    provenance: GenerationProvenance
    verdict: Verdict
    before_digest: str
    after_digest: str
    version: int | None = None       # history sequence after this edit
    base_version: int | None = None  # history sequence before it

    def as_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "instruction": self.instruction, "diff": self.diff.as_dict(),
                "inverse": self.inverse.as_dict(), "provenance": self.provenance.to_record(),
                "verdict": self.verdict.verdict, "score": round(self.verdict.score, 4)}


@dataclass(frozen=True)
class EditResult:
    status: str  # "accepted" | "repair" | "rejected" | "invalid" | "unparsed"
    plan: Mapping[str, Any]
    proposal: EditProposal
    verdict: Verdict | None = None
    record: EditRecord | None = None
    error: str | None = None
    issues: tuple[str, ...] = field(default_factory=tuple)


class EditSession:
    def __init__(self, plan: Mapping[str, Any], editor: EditPlanner, *, history: ProjectHistoryLike | None = None,
                 project_id: str | None = None, genre: str = "", thresholds: Thresholds = Thresholds(),
                 ledger: ProvenanceLedger | None = None) -> None:
        if history is not None and not project_id:
            raise ValueError("project_id required with history")
        self.plan = dict(plan)
        self.editor = editor
        self.history, self.project_id, self.genre = history, project_id, genre
        self.thresholds = thresholds
        self.ledger = ledger if ledger is not None else ProvenanceLedger()
        self.undo_stack: list[EditRecord] = []
        self.redo_stack: list[EditRecord] = []
        self._seq = 0
        self.version = self._save("edit-base", None) if history is not None else None

    def _save(self, label: str, record: EditRecord | None) -> int | None:
        if self.history is None:
            return None
        extra = {SECTION: record.as_dict()} if record else None
        m = self.history.saver.save_files(self.project_id, self.genre,
                                          {PLAN_FILE: json.dumps(self.plan, sort_keys=True, indent=2)},
                                          label=label, extra_sections=extra)
        return m.sequence

    def _provenance(self, instruction: str, proposal: EditProposal, before: str, after: str,
                    applied: PlanDiff, v: Verdict) -> GenerationProvenance:
        r = proposal.receipt
        who = r.served_by if proposal.source == "model" and r.served_by else None
        return GenerationProvenance(
            artifact_id=f"plan-edit:{self._seq}", artifact_digest=after,
            model=who or "rule_based_diff", provider=who or "rules",
            input_digest=digest({"instruction": instruction, "plan": before}),
            parameters={"source": proposal.source, "fallback_reason": proposal.fallback_reason,
                        "route_status": r.status, "route_receipt_digest": r.receipt_digest(),
                        "ops": len(applied.ops)},
            sources=(SourceRef("plan", "before", before), SourceRef("routing_receipt", r.request_id,
                                                                     r.receipt_digest())),
            transformations=(Transformation("apply_diff", before, after, f"{len(applied.ops)} ops"),),
            evals=(EvalRecord("plan_validation", v.score, v.verdict != REGENERATE, v.verdict),),
        )

    async def edit(self, instruction: str) -> EditResult:
        proposal = await self.editor.propose(instruction, self.plan)
        if proposal.diff is None:
            return EditResult("unparsed", self.plan, proposal, error=proposal.fallback_reason or "no diff")
        try:
            new, applied = apply_diff(self.plan, proposal.diff)
        except DiffError as exc:
            return EditResult("invalid", self.plan, proposal, error=str(exc))
        v = score_plan(new, self.thresholds)
        issues = tuple(p.message for p in v.errors)
        if v.verdict == REGENERATE:
            return EditResult("rejected", self.plan, proposal, v, issues=issues)
        before, after = digest(self.plan), digest(new)
        self._seq += 1
        prov = self._provenance(proposal.instruction, proposal, before, after, applied, v)
        base = self.version
        self.plan = new
        rec = EditRecord(self._seq, proposal.instruction, applied, invert(applied), prov, v, before, after,
                         None, base)
        self.version = self._save(f"edit-{self._seq}", rec)
        rec = EditRecord(**{**rec.__dict__, "version": self.version})
        self.ledger.append(prov)
        self.undo_stack.append(rec)
        self.redo_stack.clear()
        return EditResult("accepted" if v.verdict == ACCEPT else "repair", self.plan, proposal, v, rec,
                          issues=issues)

    def undo(self) -> EditRecord | None:
        if not self.undo_stack:
            return None
        rec = self.undo_stack.pop()
        self.plan, _ = apply_diff(self.plan, rec.inverse)
        if self.history is not None and rec.base_version is not None:
            self.version = self.history.rollback(self.project_id, rec.base_version)["new_head"]
        self.redo_stack.append(rec)
        return rec

    def redo(self) -> EditRecord | None:
        if not self.redo_stack:
            return None
        rec = self.redo_stack.pop()
        self.plan, _ = apply_diff(self.plan, rec.diff)
        if self.history is not None and rec.version is not None:
            self.version = self.history.rollback(self.project_id, rec.version)["new_head"]
        self.undo_stack.append(rec)
        return rec
