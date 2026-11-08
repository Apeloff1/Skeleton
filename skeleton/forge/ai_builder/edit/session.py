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
        self._held = False
        self.version = self._save("edit-base", None) if history is not None else None

    def _save(self, label: str, record: EditRecord | None, *,
              candidate: Mapping[str, Any] | None = None) -> int | None:
        if self.history is None:
            return None
        extra = {SECTION: record.as_dict()} if record else None
        target = self.plan if candidate is None else candidate
        m = self.history.saver.save_files(self.project_id, self.genre,
                                          {PLAN_FILE: json.dumps(target, sort_keys=True, indent=2)},
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
        if self._held:
            raise RuntimeError("edit custody held after failed durability operation")
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
        rec = EditRecord(self._seq, proposal.instruction, applied, invert(applied), prov, v, before, after,
                         None, base)
        # Prepare and persist the candidate before publishing it in memory.
        # A failed saver or provenance sink is a hard reconciliation hold.
        try:
            next_version = self._save(f"edit-{self._seq}", rec, candidate=new)
            self.ledger.append(prov)
        except Exception:
            self._held = True
            raise
        self.plan = new
        self.version = next_version
        rec = EditRecord(**{**rec.__dict__, "version": next_version})
        self.undo_stack.append(rec)
        self.redo_stack.clear()
        return EditResult("accepted" if v.verdict == ACCEPT else "repair", self.plan, proposal, v, rec,
                          issues=issues)

    def _move(self, *, backward: bool) -> EditRecord | None:
        if self._held:
            raise RuntimeError("edit custody held after failed durability operation")
        src, dst = (self.undo_stack, self.redo_stack) if backward else (self.redo_stack, self.undo_stack)
        if not src:
            return None
        rec = src[-1]
        candidate, _ = apply_diff(self.plan, rec.inverse if backward else rec.diff)
        target_version = rec.base_version if backward else rec.version
        next_version = self.version
        if self.history is not None and target_version is not None:
            try:
                reply = self.history.rollback(self.project_id, target_version)
                if not isinstance(reply, Mapping) or type(reply.get("new_head")) is not int:
                    raise RuntimeError("history rollback did not return a bound head")
                if reply.get("files_match") is False:
                    raise RuntimeError("history rollback receipt reports mismatch")
                next_version = reply["new_head"]
            except Exception:
                self._held = True
                raise
        self.plan = candidate
        self.version = next_version
        src.pop()
        dst.append(rec)
        return rec

    def undo(self) -> EditRecord | None:
        return self._move(backward=True)

    def redo(self) -> EditRecord | None:
        return self._move(backward=False)
