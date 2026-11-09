"""Evidence synthesis that preserves observation/inference separation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EvidenceSignal:
    signal_id: str
    domain: str
    report_digest: str
    proposition: str
    confidence: float
    supports: bool

    def __post_init__(self) -> None:
        if not self.signal_id or not self.domain or not self.proposition:
            raise ReverseEngineeringError("evidence signal identity fields are required")
        if not is_sha256_digest(self.report_digest):
            raise ReverseEngineeringError("report_digest must be a sha256 hex digest")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ReverseEngineeringError("confidence must be finite and within [0, 1]")


@dataclass(frozen=True)
class EvidenceSynthesisReport:
    proposition: str
    signal_count: int
    independent_domains: int
    supporting_weight: float
    contradicting_weight: float
    net_support: float
    status: str
    source_digests: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposition": self.proposition,
            "signal_count": self.signal_count,
            "independent_domains": self.independent_domains,
            "supporting_weight": self.supporting_weight,
            "contradicting_weight": self.contradicting_weight,
            "net_support": self.net_support,
            "status": self.status,
            "source_digests": list(self.source_digests),
            "digest": self.digest,
        }


def synthesize_evidence(
    signals: Sequence[EvidenceSignal],
    *,
    minimum_domains: int = 2,
    support_threshold: float = 0.75,
    contradiction_threshold: float = 0.25,
) -> tuple[EvidenceSynthesisReport, ...]:
    if not signals:
        raise ReverseEngineeringError("evidence synthesis requires signals")
    if minimum_domains < 1:
        raise ReverseEngineeringError("minimum_domains must be positive")
    for value, name in (
        (support_threshold, "support_threshold"),
        (contradiction_threshold, "contradiction_threshold"),
    ):
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ReverseEngineeringError(f"{name} must be finite and within [0, 1]")

    grouped: dict[str, list[EvidenceSignal]] = {}
    seen_ids: set[str] = set()
    for signal in signals:
        if signal.signal_id in seen_ids:
            raise ReverseEngineeringError(f"duplicate signal_id: {signal.signal_id!r}")
        seen_ids.add(signal.signal_id)
        grouped.setdefault(signal.proposition, []).append(signal)

    reports: list[EvidenceSynthesisReport] = []
    for proposition, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.signal_id)
        supporting = [item.confidence for item in ordered if item.supports]
        contradicting = [item.confidence for item in ordered if not item.supports]
        support_weight = sum(supporting) / len(supporting) if supporting else 0.0
        contradiction_weight = (
            sum(contradicting) / len(contradicting) if contradicting else 0.0
        )
        domains = {item.domain for item in ordered}
        net = support_weight - contradiction_weight

        status = "hypothesis"
        if contradiction_weight >= contradiction_threshold and support_weight >= support_threshold:
            status = "conflicted"
        elif (
            len(domains) >= minimum_domains
            and support_weight >= support_threshold
            and contradiction_weight < contradiction_threshold
        ):
            status = "supported"
        elif contradiction_weight >= support_threshold and support_weight < contradiction_threshold:
            status = "rejected"

        source_digests = tuple(sorted({item.report_digest for item in ordered}))
        payload = {
            "proposition": proposition,
            "signals": [
                {
                    "signal_id": item.signal_id,
                    "domain": item.domain,
                    "report_digest": item.report_digest,
                    "confidence": item.confidence,
                    "supports": item.supports,
                }
                for item in ordered
            ],
            "minimum_domains": minimum_domains,
            "support_threshold": support_threshold,
            "contradiction_threshold": contradiction_threshold,
        }
        reports.append(
            EvidenceSynthesisReport(
                proposition=proposition,
                signal_count=len(ordered),
                independent_domains=len(domains),
                supporting_weight=support_weight,
                contradicting_weight=contradiction_weight,
                net_support=net,
                status=status,
                source_digests=source_digests,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
