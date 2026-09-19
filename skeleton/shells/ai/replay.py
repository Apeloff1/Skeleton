"""Replay and verify AI decision evidence without model calls or execution."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.provenance import AIDecisionProvenance


@dataclass(frozen=True)
class AIReplayReport:
    journal_valid: bool
    provenance_valid: bool
    event_count: int
    journal_root: str
    provenance_digest: str
    reasons: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.journal_valid and self.provenance_valid

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "journal_valid": self.journal_valid,
            "provenance_valid": self.provenance_valid,
            "event_count": self.event_count,
            "journal_root": self.journal_root,
            "provenance_digest": self.provenance_digest,
            "reasons": list(self.reasons),
        }


class AIDecisionReplay:
    def verify(
        self,
        journal: AIDecisionJournal,
        provenance: AIDecisionProvenance,
        *,
        expected_policy_fingerprint: str | None = None,
        expected_effect_digest: str | None = None,
        expected_tool_catalog_digest: str | None = None,
    ) -> AIReplayReport:
        reasons = []
        journal_valid = journal.verify()
        if not journal_valid:
            reasons.append("AI decision journal hash chain is invalid")
        provenance_valid = True
        if (
            expected_policy_fingerprint is not None
            and provenance.policy_fingerprint != expected_policy_fingerprint
        ):
            provenance_valid = False
            reasons.append("policy fingerprint mismatch")
        if expected_effect_digest is not None and provenance.effect_digest != expected_effect_digest:
            provenance_valid = False
            reasons.append("effect digest mismatch")
        if (
            expected_tool_catalog_digest is not None
            and provenance.tool_catalog_digest != expected_tool_catalog_digest
        ):
            provenance_valid = False
            reasons.append("tool catalog digest mismatch")
        return AIReplayReport(
            journal_valid,
            provenance_valid,
            len(journal.snapshot()),
            journal.root_hash(),
            provenance.digest,
            tuple(reasons),
        )
