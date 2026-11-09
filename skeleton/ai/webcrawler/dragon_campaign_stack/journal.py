"""Portable hash-chained campaign decisions with revision fencing.

The journal is an *inspection/transfer artifact*. It is not a signature,
an authentication mechanism, an independent SQLite/Mongo authority, or a
substitute for the application's atomic versioned write and worker lease.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import json

from .contracts import CampaignMandate, digest, exact_digest, finite, integer


GENESIS = "0" * 64
_EVENTS = frozenset({
    "admitted", "planned", "capture_observed", "evidence_review_requested",
    "source_withdrawn", "consent_expired", "paused", "cancelled",
    "snapshot_reconciled", "recovery_blocked", "campaign_completed",
})


@dataclass(frozen=True)
class CampaignEntry:
    sequence: int
    event_type: str
    at: float
    actor: str
    binding_digest: str
    previous_digest: str
    data_digest: str
    entry_digest: str


@dataclass(frozen=True)
class CampaignJournal:
    mandate_digest: str
    entries: tuple[CampaignEntry, ...] = ()

    @property
    def head(self) -> str:
        return self.entries[-1].entry_digest if self.entries else GENESIS

    @property
    def revision(self) -> int:
        return len(self.entries)

    def append(
        self, *, expected_revision: int, event_type: str, at: float,
        actor: str, data: dict[str, object], authorized: bool,
        mandate: CampaignMandate,
    ) -> "CampaignJournal":
        mandate.admit(now=at, authorized=authorized)
        if self.mandate_digest != mandate.fingerprint:
            raise PermissionError("journal not bound to campaign mandate")
        integer(expected_revision, "journal revision", 0, 1024)
        if expected_revision != self.revision:
            raise RuntimeError("stale journal revision CAS")
        if self.revision >= mandate.limits.max_journal_entries:
            raise ValueError("journal capacity exceeded")
        if event_type not in _EVENTS:
            raise ValueError("unknown campaign transition")
        if not isinstance(actor, str) or actor != mandate.scope.owner_id:
            raise PermissionError("journal actor lacks owner binding")
        if not isinstance(data, dict):
            raise ValueError("journal event must be object")
        encoded = json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("journal entry payload budget exceeded")
        current_at = self.entries[-1].at if self.entries else mandate.created_at
        finite(at, "journal time", current_at, mandate.scope.expires_at)
        data_hash = digest(data)
        sequence = self.revision + 1
        envelope = {
            "sequence": sequence, "event_type": event_type,
            "at": at, "actor": actor,
            "binding_digest": self.mandate_digest,
            "previous_digest": self.head,
            "data_digest": data_hash,
        }
        entry = CampaignEntry(**envelope, entry_digest=digest(envelope))
        return CampaignJournal(self.mandate_digest, self.entries + (entry,))

    def verify(self, mandate: CampaignMandate) -> None:
        if self.mandate_digest != mandate.fingerprint:
            raise PermissionError("journal campaign mismatch")
        if len(self.entries) > mandate.limits.max_journal_entries:
            raise ValueError("journal capacity exceeded")
        predecessor = GENESIS
        last_at = mandate.created_at
        for i, entry in enumerate(self.entries, 1):
            if not isinstance(entry, CampaignEntry):
                raise ValueError("invalid journal entry type")
            if entry.sequence != i or entry.previous_digest != predecessor:
                raise ValueError("journal chain broken")
            if (entry.event_type not in _EVENTS
                    or entry.actor != mandate.scope.owner_id
                    or entry.binding_digest != mandate.fingerprint):
                raise ValueError("journal authority rebinding")
            finite(entry.at, "journal entry time", last_at, mandate.scope.expires_at)
            exact_digest(entry.data_digest, "journal payload digest")
            envelope = asdict(entry)
            observed = envelope.pop("entry_digest")
            if digest(envelope) != observed:
                raise ValueError("journal entry tampered")
            predecessor = observed
            last_at = entry.at

    def export(self, mandate: CampaignMandate) -> dict[str, object]:
        self.verify(mandate)
        return {
            "schema_version": "skeleton.ai.dragon.campaign_journal.v1",
            "mandate_digest": self.mandate_digest,
            "entries": [asdict(x) for x in self.entries],
            "head": self.head,
            "revision": self.revision,
            "source_authority": "existing_application_crawl_snapshot_only",
        }

    @classmethod
    def restore(
        cls, serialized: dict[str, object], mandate: CampaignMandate,
    ) -> "CampaignJournal":
        if (not isinstance(serialized, dict) or set(serialized) != {
            "schema_version", "mandate_digest", "entries", "head",
            "revision", "source_authority",
        }):
            raise ValueError("unknown journal schema")
        if (serialized["schema_version"] != "skeleton.ai.dragon.campaign_journal.v1"
                or serialized["source_authority"] != "existing_application_crawl_snapshot_only"):
            raise ValueError("unsupported journal schema")
        rows = serialized["entries"]
        if not isinstance(rows, list) or len(rows) > mandate.limits.max_journal_entries:
            raise ValueError("journal size invalid")
        names = set(CampaignEntry.__dataclass_fields__)
        entries = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != names:
                raise ValueError("invalid journal entry schema")
            entries.append(CampaignEntry(**row))
        journal = cls(serialized["mandate_digest"], tuple(entries))
        journal.verify(mandate)
        if serialized["head"] != journal.head or serialized["revision"] != journal.revision:
            raise ValueError("journal head or revision mismatch")
        return journal
