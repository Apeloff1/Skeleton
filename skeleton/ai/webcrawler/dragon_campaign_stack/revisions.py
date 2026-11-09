"""Exact snapshot-to-snapshot source revisions with stale citation disposition.

Source text is never silently promoted on a new hash. A content revision,
consent withdrawal, loss of retained proof or source disappearance invalidates
passage references built from the previous snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import digest, exact_digest
from .evidence import SourceInspection, CampaignPassage


@dataclass(frozen=True)
class SourceDelta:
    source_id: str
    disposition: str
    previous_hash: str | None
    current_hash: str | None
    requires_re_review: bool


@dataclass(frozen=True)
class PassageDisposition:
    source_id: str
    passage_hash: str
    current: bool
    reason: str


@dataclass(frozen=True)
class RevisionImpact:
    deltas: tuple[SourceDelta, ...]
    citations: tuple[PassageDisposition, ...]
    impact_digest: str


def compare_research_revisions(
    before: Iterable[SourceInspection],
    after: Iterable[SourceInspection],
    citations: Iterable[CampaignPassage] = (),
    *, revoked_source_ids: Iterable[str] = (),
) -> RevisionImpact:
    old = tuple(before)
    new = tuple(after)
    cited = tuple(citations)
    if len(old) > 128 or len(new) > 128 or len(cited) > 256:
        raise ValueError("source revision comparison budget exceeded")
    def mapped(rows: tuple[SourceInspection, ...]) -> dict[str, SourceInspection]:
        result = {}
        for row in rows:
            if not isinstance(row, SourceInspection):
                raise TypeError("typed source observation required")
            if row.source_id in result:
                raise ValueError("duplicate revision source identity")
            result[row.source_id] = row
        return result
    previous = mapped(old)
    current = mapped(new)
    revoked = set(revoked_source_ids)
    for item in revoked:
        exact_digest(item, "revoked source")
        if item not in previous and item not in current:
            raise ValueError("revocation of unknown source")
    changes: list[SourceDelta] = []
    for source_id in sorted(set(previous) | set(current)):
        a = previous.get(source_id)
        b = current.get(source_id)
        if source_id in revoked:
            status = "withdrawn"
        elif a is None:
            status = "new"
        elif b is None:
            status = "missing"
        elif (a.full_content_hash != b.full_content_hash
              or a.preserved_text_hash != b.preserved_text_hash):
            status = "changed"
        elif a.text_truncated or b.text_truncated:
            status = "partial_evidence"
        elif not b.inspectable:
            status = "review_hold"
        else:
            status = "unchanged"
        changes.append(SourceDelta(
            source_id=source_id, disposition=status,
            previous_hash=a.full_content_hash if a else None,
            current_hash=b.full_content_hash if b else None,
            requires_re_review=status != "unchanged",
        ))
    checks: list[PassageDisposition] = []
    for citation in cited:
        if not isinstance(citation, CampaignPassage):
            raise TypeError("typed source citations required")
        destination = current.get(citation.source_id)
        prior = previous.get(citation.source_id)
        valid = (
            destination is not None and prior is not None
            and citation.source_id not in revoked
            and destination.inspectable
            and destination.full_content_hash == citation.source_content_hash
            and destination.preserved_text_hash == citation.preserved_text_hash
            and prior.full_content_hash == destination.full_content_hash
            and prior.preserved_text_hash == destination.preserved_text_hash
        )
        checks.append(PassageDisposition(
            citation.source_id, citation.passage_hash, bool(valid),
            "same_retained_revision_requires_current_authority" if valid
            else "stale_revoked_or_unreviewable_source",
        ))
    payload = {
        "deltas": [asdict(x) for x in changes],
        "citations": [asdict(x) for x in checks],
    }
    return RevisionImpact(tuple(changes), tuple(checks), digest(payload))
