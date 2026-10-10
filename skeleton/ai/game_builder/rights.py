"""Fail-closed source-rights and originality governance for game artifacts.

This module enforces project policy; it does not make legal determinations.
Similarity findings are risk signals and ambiguous high-risk cases require
human/legal review before release.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .contracts import EvaluatorProvenance, canonical_digest


class RightsError(RuntimeError):
    pass


class RightsState(str, Enum):
    PROJECT_OWNED = "project_owned"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSIVE_REUSE = "permissive_reuse"
    LICENSED_REUSE = "licensed_reuse"
    FACTS_IDEAS_REFERENCE_ONLY = "facts_and_ideas_reference_only"
    RESTRICTED_REFERENCE_ONLY = "restricted_reference_only"
    UNKNOWN_QUARANTINE = "unknown_quarantine"
    FORBIDDEN = "forbidden"


class UseKind(str, Enum):
    FACTS_IDEAS_REFERENCE = "facts_ideas_reference"
    EXPRESSIVE_INCORPORATION = "expressive_incorporation"
    CODE_INCORPORATION = "code_incorporation"
    MODEL_TRAINING = "model_training"
    RELEASE_DISTRIBUTION = "release_distribution"


class SimilarityRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    content_digest: str
    rights_state: RightsState
    allowed_uses: frozenset[UseKind]
    source_class: str
    rights_authority: EvaluatorProvenance
    rights_evidence_digest: str
    license_id: str | None = None
    attribution_text: str | None = None
    attribution_required: bool = False
    consent_required: bool = False
    consent_digest: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id.strip()
            or not isinstance(self.source_class, str)
            or not self.source_class.strip()
        ):
            raise ValueError("source identity and source_class must be non-empty")
        if not isinstance(self.content_digest, str) or len(self.content_digest) < 16:
            raise ValueError("content_digest must be stable")
        if not isinstance(self.rights_state, RightsState):
            raise TypeError("rights_state must be RightsState")
        if not isinstance(self.allowed_uses, frozenset) or any(
            not isinstance(item, UseKind) for item in self.allowed_uses
        ):
            raise TypeError("allowed_uses must be a frozenset of UseKind")
        if not isinstance(self.rights_authority, EvaluatorProvenance):
            raise TypeError("rights_authority must be EvaluatorProvenance")
        if (
            not isinstance(self.rights_evidence_digest, str)
            or len(self.rights_evidence_digest) < 16
        ):
            raise ValueError("rights_evidence_digest must be stable")
        if self.rights_evidence_digest not in self.rights_authority.output_evidence_refs:
            raise RightsError(
                "rights evidence must be referenced by rights authority"
            )
        if not isinstance(self.attribution_required, bool):
            raise TypeError("attribution_required must be boolean")
        if not isinstance(self.consent_required, bool):
            raise TypeError("consent_required must be boolean")
        if self.attribution_required and not (self.attribution_text or "").strip():
            raise ValueError("required attribution text is missing")
        if self.consent_required and not self.consent_digest:
            raise ValueError("required consent evidence is missing")
        if self.consent_digest is not None and (
            not isinstance(self.consent_digest, str)
            or len(self.consent_digest) < 16
        ):
            raise ValueError("consent_digest must be stable")
        if self.rights_state is RightsState.LICENSED_REUSE and not (
            self.license_id or ""
        ).strip():
            raise ValueError("licensed reuse requires license identity")
        if self.rights_state in {RightsState.UNKNOWN_QUARANTINE, RightsState.FORBIDDEN}:
            if self.allowed_uses:
                raise ValueError("quarantined/forbidden sources cannot declare allowed uses")

    @property
    def rights_binding_digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "allowed_uses": sorted(item.value for item in self.allowed_uses),
            "attribution_required": self.attribution_required,
            "attribution_text": self.attribution_text,
            "consent_digest": self.consent_digest,
            "consent_required": self.consent_required,
            "content_digest": self.content_digest,
            "license_id": self.license_id,
            "rights_authority_digest": self.rights_authority.digest,
            "rights_evidence_digest": self.rights_evidence_digest,
            "rights_state": self.rights_state.value,
            "source_class": self.source_class,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class SimilarityFinding:
    finding_id: str
    artifact_digest: str
    source_id: str
    modality: str
    risk: SimilarityRisk
    evidence_digest: str
    evaluator_provenance: EvaluatorProvenance
    resolved: bool = False
    resolution: str | None = None
    resolution_evidence_digest: str | None = None
    resolution_authority: EvaluatorProvenance | None = None

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or not self.modality.strip():
            raise ValueError("similarity finding identity/modality must be non-empty")
        if len(self.artifact_digest) < 16 or len(self.evidence_digest) < 16:
            raise ValueError("similarity finding digests must be stable")
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("similarity evaluator_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.evaluator_provenance.output_evidence_refs:
            raise RightsError(
                "similarity evidence must be referenced by evaluator authority"
            )
        if not isinstance(self.resolved, bool):
            raise TypeError("similarity resolved state must be boolean")
        if self.resolved:
            if not (self.resolution or "").strip():
                raise ValueError("resolved finding requires a resolution")
            if not isinstance(self.resolution_authority, EvaluatorProvenance):
                raise TypeError("resolved finding requires resolution authority")
            if (
                not isinstance(self.resolution_evidence_digest, str)
                or len(self.resolution_evidence_digest) < 16
            ):
                raise ValueError("resolved finding requires stable resolution evidence")
            if (
                self.resolution_evidence_digest
                not in self.resolution_authority.output_evidence_refs
            ):
                raise RightsError(
                    "similarity resolution evidence must be referenced by resolution authority"
                )
            if (
                self.risk is SimilarityRisk.HIGH
                and self.resolution_authority.evaluator_id
                == self.evaluator_provenance.evaluator_id
            ):
                raise RightsError(
                    "high-risk similarity resolution requires independent authority"
                )
        elif (
            self.resolution is not None
            or self.resolution_evidence_digest is not None
            or self.resolution_authority is not None
        ):
            raise ValueError("unresolved finding cannot carry resolution authority state")

    @property
    def evidence_binding_digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
                "evidence_digest": self.evidence_digest,
                "finding_id": self.finding_id,
                "modality": self.modality,
                "risk": self.risk.value,
                "source_id": self.source_id,
            }
        )

    @property
    def resolution_binding_digest(self) -> str | None:
        if not self.resolved or self.resolution_authority is None:
            return None
        return canonical_digest(
            {
                "finding_evidence_binding_digest": self.evidence_binding_digest,
                "resolution": self.resolution,
                "resolution_authority_digest": self.resolution_authority.digest,
                "resolution_evidence_digest": self.resolution_evidence_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class IncorporationDecision:
    source_id: str
    artifact_digest: str
    use_kind: UseKind
    allowed: bool
    reason: str
    source_record_digest: str
    decision_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("incorporation allowed state must be boolean")
        if not isinstance(self.use_kind, UseKind):
            raise TypeError("incorporation use_kind must be UseKind")
        if not self.source_id.strip() or not self.reason.strip():
            raise ValueError("incorporation identity/reason must be non-empty")
        for value in (
            self.artifact_digest,
            self.source_record_digest,
            self.decision_digest,
        ):
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError("incorporation decision identities must be stable")
        expected = canonical_digest(self.decision_payload())
        if self.decision_digest != expected:
            raise ValueError("incorporation decision digest mismatch")

    def decision_payload(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "artifact_digest": self.artifact_digest,
            "reason": self.reason,
            "source_id": self.source_id,
            "source_record_digest": self.source_record_digest,
            "use_kind": self.use_kind.value,
        }


class RightsLedger:
    """Content-addressed source policy and release-risk ledger."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceRecord] = {}
        self._findings: dict[str, SimilarityFinding] = {}
        self._decisions: list[IncorporationDecision] = []

    def register_source(self, record: SourceRecord) -> None:
        existing = self._sources.get(record.source_id)
        if existing is not None and existing != record:
            raise RightsError("source identity cannot be rebound to different rights metadata")
        self._sources[record.source_id] = record

    def source(self, source_id: str) -> SourceRecord:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise RightsError(f"unknown source: {source_id}") from exc

    def decide_incorporation(
        self,
        *,
        source_id: str,
        artifact_digest: str,
        use_kind: UseKind,
    ) -> IncorporationDecision:
        if len(artifact_digest) < 16:
            raise ValueError("artifact_digest must be stable")
        source = self.source(source_id)
        state = source.rights_state

        if state is RightsState.UNKNOWN_QUARANTINE:
            allowed, reason = False, "unknown rights are quarantined"
        elif state is RightsState.FORBIDDEN:
            allowed, reason = False, "source is forbidden"
        elif state in {
            RightsState.FACTS_IDEAS_REFERENCE_ONLY,
            RightsState.RESTRICTED_REFERENCE_ONLY,
        }:
            allowed = use_kind is UseKind.FACTS_IDEAS_REFERENCE
            reason = (
                "reference-only source may inform facts/ideas"
                if allowed
                else "reference-only source cannot supply incorporated expression"
            )
        else:
            allowed = use_kind in source.allowed_uses
            reason = (
                "requested use is explicitly allowed"
                if allowed
                else "requested use is not in the source permission envelope"
            )

        source_digest = canonical_digest(source.to_payload())
        core = {
            "allowed": allowed,
            "artifact_digest": artifact_digest,
            "reason": reason,
            "source_id": source_id,
            "source_record_digest": source_digest,
            "use_kind": use_kind.value,
        }
        decision = IncorporationDecision(
            source_id=source_id,
            artifact_digest=artifact_digest,
            use_kind=use_kind,
            allowed=allowed,
            reason=reason,
            source_record_digest=source_digest,
            decision_digest=canonical_digest(core),
        )
        self._decisions.append(decision)
        return decision

    def record_similarity(self, finding: SimilarityFinding) -> None:
        if finding.source_id not in self._sources:
            raise RightsError("similarity finding references unknown source")
        existing = self._findings.get(finding.finding_id)
        if existing is not None and existing != finding:
            raise RightsError("similarity finding identity cannot be rebound")
        self._findings[finding.finding_id] = finding

    def resolve_similarity(
        self,
        finding_id: str,
        *,
        resolution: str,
        resolution_evidence_digest: str,
        resolution_authority: EvaluatorProvenance,
    ) -> SimilarityFinding:
        existing = self._findings.get(finding_id)
        if existing is None:
            raise RightsError(f"unknown similarity finding: {finding_id}")
        if existing.resolved:
            return existing
        if not resolution.strip():
            raise ValueError("similarity resolution must be non-empty")
        resolved = SimilarityFinding(
            finding_id=existing.finding_id,
            artifact_digest=existing.artifact_digest,
            source_id=existing.source_id,
            modality=existing.modality,
            risk=existing.risk,
            evidence_digest=existing.evidence_digest,
            evaluator_provenance=existing.evaluator_provenance,
            resolved=True,
            resolution=resolution,
            resolution_evidence_digest=resolution_evidence_digest,
            resolution_authority=resolution_authority,
        )
        self._findings[finding_id] = resolved
        return resolved

    def unresolved_high_risk(
        self, *, artifact_digest: str | None = None
    ) -> tuple[SimilarityFinding, ...]:
        rows = [
            row
            for row in self._findings.values()
            if row.risk is SimilarityRisk.HIGH
            and not row.resolved
            and (artifact_digest is None or row.artifact_digest == artifact_digest)
        ]
        return tuple(sorted(rows, key=lambda row: row.finding_id))

    def release_gate(
        self,
        *,
        artifact_digest: str,
        incorporation_decisions: Iterable[IncorporationDecision],
    ) -> tuple[bool, tuple[str, ...]]:
        decisions = tuple(incorporation_decisions)
        blockers: list[str] = []
        if not decisions:
            blockers.append("no incorporation/provenance decisions supplied")
        for decision in decisions:
            if not isinstance(decision, IncorporationDecision):
                raise RightsError("release decisions must be typed ledger receipts")
            if decision not in self._decisions:
                blockers.append(f"decision {decision.decision_digest} was not issued by this ledger")
            record = self._sources.get(decision.source_id)
            if record is None or record.rights_binding_digest != decision.source_record_digest:
                blockers.append(f"source {decision.source_id} rights binding is missing or stale")
            if decision.artifact_digest != artifact_digest:
                blockers.append(f"decision {decision.decision_digest} targets another artifact")
            if not decision.allowed:
                blockers.append(
                    f"source {decision.source_id} is not cleared for {decision.use_kind.value}"
                )
        for finding in self.unresolved_high_risk(artifact_digest=artifact_digest):
            blockers.append(
                f"similarity finding {finding.finding_id} requires human/legal review"
            )
        return not blockers, tuple(sorted(set(blockers)))

    def snapshot(self) -> dict[str, object]:
        core: dict[str, object] = {
            "decisions": [
                {
                    "allowed": row.allowed,
                    "artifact_digest": row.artifact_digest,
                    "decision_digest": row.decision_digest,
                    "reason": row.reason,
                    "source_id": row.source_id,
                    "source_record_digest": row.source_record_digest,
                    "use_kind": row.use_kind.value,
                }
                for row in self._decisions
            ],
            "findings": [
                {
                    "artifact_digest": row.artifact_digest,
                    "evidence_digest": row.evidence_digest,
                    "evidence_binding_digest": row.evidence_binding_digest,
                    "evaluator_provenance_digest": row.evaluator_provenance.digest,
                    "finding_id": row.finding_id,
                    "modality": row.modality,
                    "resolution": row.resolution,
                    "resolution_binding_digest": row.resolution_binding_digest,
                    "resolved": row.resolved,
                    "risk": row.risk.value,
                    "source_id": row.source_id,
                }
                for row in sorted(self._findings.values(), key=lambda x: x.finding_id)
            ],
            "sources": [
                self._sources[key].to_payload() for key in sorted(self._sources)
            ],
        }
        return {**core, "digest": canonical_digest(core)}
