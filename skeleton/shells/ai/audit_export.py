"""Redacted export of AI shell decision evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.provenance import AIDecisionProvenance


@dataclass(frozen=True)
class AIAuditExport:
    schema_version: int
    journal_root: str
    journal_valid: bool
    provenance: dict[str, object]
    events: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "journal_root": self.journal_root,
            "journal_valid": self.journal_valid,
            "provenance": dict(self.provenance),
            "events": list(self.events),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class AIAuditExporter:
    """Export only bounded decision summaries and digests, never child output."""

    _ALLOWED_EVENT_DATA = frozenset(
        {
            "model_id",
            "proposal_fingerprint",
            "risk_score",
            "risk_band",
            "allowed",
            "requires_approval",
            "guardrail_errors",
            "approval_id",
            "approved_by",
            "ok",
            "verified",
            "duration_ms",
            "provenance_digest",
            "error_type",
        }
    )

    def export(
        self,
        journal: AIDecisionJournal,
        provenance: AIDecisionProvenance,
    ) -> AIAuditExport:
        events = []
        for event in journal.snapshot():
            data = {
                key: value
                for key, value in event.data.items()
                if key in self._ALLOWED_EVENT_DATA
            }
            events.append(
                {
                    "sequence": event.sequence,
                    "previous_hash": event.previous_hash,
                    "event_hash": event.event_hash,
                    "kind": event.kind,
                    "observed_at": event.observed_at,
                    "session_id": event.session_id,
                    "intent_id": event.intent_id,
                    "proposal_id": event.proposal_id,
                    "summary": event.summary,
                    "data": data,
                }
            )
        return AIAuditExport(
            1,
            journal.root_hash(),
            journal.verify(),
            provenance.to_dict(),
            tuple(events),
        )
