"""Independent-source provenance registry for the dragon truth verifier.

Independence is an attested property, never inferred from a publisher's own
claims. The registry supports explicit common ownership and syndication
groups, with a fail-closed fallback for unknown publishers.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit
import json
import re

from .dragon_truth_verifier import Evidence, Claim, VerificationPolicy, VerificationResult, verify_claim
from .dragon_video_history import canonical_video_url


_GROUP = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class SourceAttestation:
    hostname: str
    ownership_group: str
    syndication_group: str = ""
    verified_by: str = ""
    evidence_reference: str = ""


@dataclass(frozen=True)
class ProvenancePolicy:
    require_attestation: bool = True
    max_attestations: int = 5000
    max_sources_per_claim: int = 256


@dataclass(frozen=True)
class ProvenanceReview:
    result: VerificationResult
    accepted_sources: int
    rejected_sources: int
    independence_groups: tuple[str, ...]
    registry_fingerprint: str


def _hostname(url: str) -> str:
    canonical = canonical_video_url(url)
    hostname = urlsplit(canonical).hostname
    if not hostname:
        raise ValueError("missing hostname")
    return hostname.casefold().rstrip(".")


class ProvenanceRegistry:
    def __init__(self, attestations: tuple[SourceAttestation, ...], *,
                 policy: ProvenancePolicy = ProvenancePolicy()):
        if not 1 <= policy.max_attestations <= 100000:
            raise ValueError("invalid registry budget")
        if not 1 <= policy.max_sources_per_claim <= 10000:
            raise ValueError("invalid source budget")
        if len(attestations) > policy.max_attestations:
            raise ValueError("registry budget exceeded")
        entries: dict[str, SourceAttestation] = {}
        for attestation in attestations:
            host = _hostname("https://" + attestation.hostname + "/")
            owner = attestation.ownership_group.casefold().strip()
            syndication = attestation.syndication_group.casefold().strip()
            if not _GROUP.fullmatch(owner):
                raise ValueError("invalid ownership group")
            if syndication and not _GROUP.fullmatch(syndication):
                raise ValueError("invalid syndication group")
            if not attestation.verified_by or len(attestation.verified_by) > 128:
                raise ValueError("unverified source attestation")
            if not attestation.evidence_reference or len(attestation.evidence_reference) > 256:
                raise ValueError("missing attestation evidence")
            if host in entries and entries[host] != attestation:
                raise ValueError("conflicting source attestation")
            entries[host] = attestation
        self._entries = entries
        self.policy = policy
        payload = [
            (host, a.ownership_group, a.syndication_group,
             a.verified_by, a.evidence_reference)
            for host, a in sorted(entries.items())
        ]
        self.fingerprint = sha256(json.dumps(
            payload, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")).hexdigest()

    def group_for(self, url: str) -> str | None:
        host = _hostname(url)
        entry = self._entries.get(host)
        if entry is None:
            return None if self.policy.require_attestation else "unknown-publisher"
        if entry.syndication_group:
            return "syndication:" + entry.syndication_group.casefold().strip()
        return "owner:" + entry.ownership_group.casefold().strip()

    def verify(
        self, claim: Claim, evidence: tuple[Evidence, ...], *,
        now: float, verification_policy: VerificationPolicy = VerificationPolicy(),
    ) -> ProvenanceReview:
        if len(evidence) > self.policy.max_sources_per_claim:
            raise ValueError("provenance review budget exceeded")
        validated = []
        rejected = 0
        groups = set()
        for item in evidence:
            try:
                group = self.group_for(item.source_url)
            except (TypeError, ValueError):
                rejected += 1
                continue
            if group is None:
                rejected += 1
                continue
            groups.add(group)
            # Ignore untrusted, self-declared family strings; only registry
            # attestation determines independent voting identity.
            validated.append(Evidence(
                item.evidence_id, item.claim_id, item.source_url, group,
                item.stance, item.excerpt, item.observed_at,
                item.confidence, item.primary, item.provenance_id,
            ))
        result = verify_claim(
            claim, tuple(validated), now=now, policy=verification_policy,
        )
        return ProvenanceReview(
            result, len(validated), rejected,
            tuple(sorted(groups)), self.fingerprint,
        )
