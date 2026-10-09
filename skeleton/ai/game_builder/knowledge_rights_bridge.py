"""Bind reviewed gameplay research to the existing game-builder rights authority.

A knowledge hit can inform a design only if the canonical RightsLedger has
independently registered the exact source digest, license and permitted use.
This is an authenticated integration point, not an independent rights engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import canonical_digest
from .reviewed_knowledge import (
    KnowledgeBrief,
    KnowledgeError,
    KnowledgeHit,
    ReviewedKnowledgeStore,
    _digest,
    _id,
)
from .rights import (
    IncorporationDecision,
    RightsError,
    RightsLedger,
    RightsState,
    UseKind,
)


class ResearchHandoffError(KnowledgeError):
    """A research-to-design handoff is unqualified."""


@dataclass(frozen=True, slots=True)
class ClearedResearchSource:
    source_id: str
    revision_digest: str
    source_text_digest: str
    rights_record_digest: str
    rights_decision_digest: str
    attribution_text: str | None
    license_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "revision_digest": self.revision_digest,
            "source_text_digest": self.source_text_digest,
            "rights_record_digest": self.rights_record_digest,
            "rights_decision_digest": self.rights_decision_digest,
            "attribution_text": self.attribution_text,
            "license_id": self.license_id,
        }


@dataclass(frozen=True, slots=True)
class ClearedResearchPacket:
    project_id: str
    artifact_digest: str
    owner: str
    knowledge_root: str
    research_brief_digest: str
    rights_ledger_digest: str
    sources: tuple[ClearedResearchSource, ...]
    citations: tuple[KnowledgeHit, ...]
    conflicts: tuple[str, ...]
    human_approved: bool

    def to_payload(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": "skeleton.game_builder.cleared_research_packet.v1",
            "project_id": self.project_id,
            "artifact_digest": self.artifact_digest,
            "owner": self.owner,
            "knowledge_root": self.knowledge_root,
            "research_brief_digest": self.research_brief_digest,
            "rights_ledger_digest": self.rights_ledger_digest,
            "sources": [source.to_payload() for source in self.sources],
            "citations": [hit.to_payload() for hit in self.citations],
            "conflicts": list(self.conflicts),
            "human_approved": self.human_approved,
            "build_authority": False,
            "training_authority": False,
            "release_authority": False,
        }
        return {**body, "packet_digest": canonical_digest(body)}


def clear_research_for_design(
    library: ReviewedKnowledgeStore,
    brief: KnowledgeBrief,
    rights: RightsLedger,
    *,
    project_id: str,
    artifact_digest: str,
    human_approved: bool,
    authorized: bool,
) -> ClearedResearchPacket:
    """Authorize research *reference*, not copying, model training or release.

    Preconditions are checked before calling RightsLedger.decide_incorporation,
    which records reference-only rights decisions. Callers must authenticate the
    operator externally and must not treat this deterministic packet as a
    producer's authorization to synthesize or publish an artifact.
    """
    if not authorized:
        raise PermissionError("research-to-design handoff needs authenticated operator")
    if type(human_approved) is not bool or not human_approved:
        raise ResearchHandoffError("research handoff requires explicit human approval")
    if not isinstance(library, ReviewedKnowledgeStore):
        raise ResearchHandoffError("canonical reviewed knowledge library required")
    if not isinstance(brief, KnowledgeBrief) or not isinstance(rights, RightsLedger):
        raise ResearchHandoffError("typed brief and canonical rights ledger required")
    _id(project_id, "project_id")
    _digest(artifact_digest, "artifact_digest")
    if brief.scope != "design_reference":
        raise ResearchHandoffError("design must not consume training or research-only scope")
    library.require_fresh_brief(brief, authorized=True)
    if not brief.citations:
        raise ResearchHandoffError("empty evidence cannot authorize design reference")

    identities: dict[str, KnowledgeHit] = {}
    for hit in brief.citations:
        earlier = identities.get(hit.source_id)
        if earlier is not None and (
            earlier.source_text_digest != hit.source_text_digest
            or earlier.revision_digest != hit.revision_digest
            or earlier.license_id != hit.license_id
        ):
            raise ResearchHandoffError("ambiguous source revision in a research brief")
        identities[hit.source_id] = hit

    # Pure validation pass first. Never apply partial ledger decisions when a
    # later source in this same batch is known to be blocked.
    records = {}
    for source_id in sorted(identities):
        hit = identities[source_id]
        try:
            record = rights.source(source_id)
        except RightsError as exc:
            raise ResearchHandoffError("research source not registered in canonical rights ledger") from exc
        if record.content_digest != hit.source_text_digest:
            raise ResearchHandoffError("source body and independently registered rights digest disagree")
        if record.license_id != hit.license_id:
            raise ResearchHandoffError("source license differs from canonical rights evidence")
        if record.rights_state in {RightsState.UNKNOWN_QUARANTINE, RightsState.FORBIDDEN}:
            raise ResearchHandoffError("quarantined or forbidden research source")
        if (
            record.rights_state not in {
                RightsState.FACTS_IDEAS_REFERENCE_ONLY,
                RightsState.RESTRICTED_REFERENCE_ONLY,
            }
            and UseKind.FACTS_IDEAS_REFERENCE not in record.allowed_uses
        ):
            raise ResearchHandoffError("canonical source policy does not permit research reference")
        if record.consent_required and not record.consent_digest:
            raise ResearchHandoffError("required research source consent missing")
        if record.attribution_required and not record.attribution_text:
            raise ResearchHandoffError("required research attribution missing")
        records[source_id] = record

    if rights.unresolved_high_risk(artifact_digest=artifact_digest):
        raise ResearchHandoffError("high-risk source similarity requires independent review")

    decisions: list[IncorporationDecision] = []
    for source_id in sorted(records):
        decision = rights.decide_incorporation(
            source_id=source_id,
            artifact_digest=artifact_digest,
            use_kind=UseKind.FACTS_IDEAS_REFERENCE,
        )
        if not decision.allowed:
            # This must not arise after the preflight above. Fail closed if
            # policy behavior evolves underneath this adapter.
            raise ResearchHandoffError("rights authority refused research reference")
        decisions.append(decision)

    allowed, blockers = rights.release_gate(
        artifact_digest=artifact_digest,
        incorporation_decisions=decisions,
    )
    if not allowed:
        raise ResearchHandoffError("research reference blocked: " + "; ".join(blockers))

    sources: list[ClearedResearchSource] = []
    for decision in decisions:
        hit = identities[decision.source_id]
        record = records[decision.source_id]
        if decision.source_record_digest != record.rights_binding_digest:
            raise ResearchHandoffError("rights receipt does not match registered source")
        sources.append(ClearedResearchSource(
            source_id=decision.source_id,
            revision_digest=hit.revision_digest,
            source_text_digest=hit.source_text_digest,
            rights_record_digest=record.rights_binding_digest,
            rights_decision_digest=decision.decision_digest,
            attribution_text=record.attribution_text,
            license_id=hit.license_id,
        ))
    rights_snapshot = rights.snapshot()
    return ClearedResearchPacket(
        project_id, artifact_digest, brief.owner, brief.knowledge_root,
        brief.to_payload()["brief_digest"], rights_snapshot["digest"],
        tuple(sources), brief.citations, brief.conflicts, human_approved,
    )


def require_cleared_research_current(
    packet: ClearedResearchPacket,
    library: ReviewedKnowledgeStore,
    rights: RightsLedger,
    *,
    authorized: bool,
) -> None:
    """Fail closed before builder consumption if source rights or custody moved."""
    if not authorized:
        raise PermissionError("research packet inspection requires authorization")
    if not isinstance(packet, ClearedResearchPacket) or not packet.human_approved:
        raise ResearchHandoffError("typed approved research packet required")
    if not isinstance(library, ReviewedKnowledgeStore) or not isinstance(rights, RightsLedger):
        raise ResearchHandoffError("canonical knowledge and rights owners required")
    if packet.knowledge_root != library.snapshot_root(packet.owner, authorized=True):
        raise ResearchHandoffError("research packet is stale after knowledge revision")
    if rights.snapshot()["digest"] != packet.rights_ledger_digest:
        raise ResearchHandoffError("research packet is stale after rights ledger revision")
    sources = {item.source_id: item for item in packet.sources}
    if len(packet.sources) != len(sources) or not packet.citations:
        raise ResearchHandoffError("research packet source set invalid")
    if {hit.source_id for hit in packet.citations} != set(sources):
        raise ResearchHandoffError("research packet evidence source mismatch")
    for hit in packet.citations:
        source = sources[hit.source_id]
        if (source.source_text_digest != hit.source_text_digest
                or source.revision_digest != hit.revision_digest
                or source.license_id != hit.license_id):
            raise ResearchHandoffError("research packet citation custody mismatch")
        record = rights.source(hit.source_id)
        if record.rights_binding_digest != source.rights_record_digest:
            raise ResearchHandoffError("research packet rights reference mismatch")
    # Not a replacement for matching the original brief query (which may be
    # broader). Independently validate every exact citation via its source's
    # current latest revision, even when its ranking is query-dependent.
    current = library._rows(packet.owner)
    latest = {row["source_id"]: row for row in current}
    for hit in packet.citations:
        record = latest.get(hit.source_id)
        if record is None or record["revision_digest"] != hit.revision_digest:
            raise ResearchHandoffError("cited source was superseded")
        if "design_reference" not in record["allowed_scopes"] or record["status"] != "active":
            raise ResearchHandoffError("cited source is no longer design-reference admissible")
        if not any(
            entry["note"]["note_id"] == hit.note_id
            and entry["note"]["statement"] == hit.statement
            and entry["exact_quote"] == hit.exact_quote
            and entry["note"]["stance"] == hit.stance
            and entry["note"]["start"] == hit.start
            and entry["note"]["end"] == hit.end
            and entry["note"]["confidence_ppm"] == hit.confidence_ppm
            and entry["note"]["dependence_group"] == hit.dependence_group
            for entry in record["notes"]
        ):
            raise ResearchHandoffError("research packet cited note no longer exists")


__all__ = [
    "ResearchHandoffError", "ClearedResearchSource", "ClearedResearchPacket",
    "clear_research_for_design", "require_cleared_research_current",
]
