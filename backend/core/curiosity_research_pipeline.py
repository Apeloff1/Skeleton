"""Evidence-aware research adapters for the Curiosity Engine.

Model output creates hypotheses, never empirical facts. Source evidence enters the
truth pipeline only through an explicit claim-level citation binding with verified
provenance, an inspectable locator and evidence span. Topic-adjacent citations and
legacy ``supports_claims`` metadata remain useful for research discovery but cannot
silently promote a claim.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Awaitable, Callable, Iterable

from core.citation_integrity import CitationBinding, CitationIntegrityEngine
from core.curiosity_engine import Inquiry

Completion = Callable[[str, str, str], Awaitable[str | dict[str, Any]]]
SourceSearch = Callable[[Inquiry, tuple[str, ...]], Awaitable[Iterable[dict[str, Any]]]]


@dataclass(frozen=True, slots=True)
class SourceClaimBinding:
    claim: str
    supports: bool
    binding_method: str
    evidence_span: str
    mapping_rationale: str = ""


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source: str
    locator: str
    excerpt: str
    quality: float
    kind: str
    independence_group: str
    claim_bindings: tuple[SourceClaimBinding, ...]
    supports_claims: tuple[str, ...]
    contradicts_claims: tuple[str, ...]
    observed_at: str = ""
    reproducible: bool = False
    peer_reviewed: bool = False
    primary: bool = False
    provenance_verified: bool = False
    preregistered: bool = False
    data_available: bool = False
    code_available: bool = False
    sample_size: int | None = None
    uncertainty_reported: bool = False
    content_sha256: str = ""
    parent_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelObservation:
    model: str
    summary: str
    claims: tuple[str, ...]
    questions: tuple[str, ...]
    contradictions: tuple[str, ...]
    tags: tuple[str, ...]


def _extract_json(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {"summary": text[:8000]}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {"summary": text[:8000]}
        except json.JSONDecodeError:
            return {"summary": text[:8000]}


def _texts(value: Any, *, limit: int = 32) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item).split()).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text[:3000])
        if len(out) >= limit:
            break
    return tuple(out)


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _bindings(raw: Any, *, excerpt: str) -> tuple[SourceClaimBinding, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[SourceClaimBinding] = []
    for row in raw[:64]:
        if not isinstance(row, dict):
            continue
        claim = " ".join(str(row.get("claim") or "").split()).strip()
        if not claim:
            continue
        out.append(SourceClaimBinding(
            claim=claim[:3000],
            supports=bool(row.get("supports", True)),
            binding_method=str(row.get("binding_method") or "").strip()[:80],
            evidence_span=str(row.get("evidence_span") or excerpt or "")[:6000],
            mapping_rationale=str(row.get("mapping_rationale") or "")[:4000],
        ))
    return tuple(out)


class EnsembleCuriosityResearcher:
    def __init__(
        self,
        completion: Completion,
        *,
        models: tuple[str, ...] = ("reasoning", "balanced", "creative"),
        source_search: SourceSearch | None = None,
        max_sources: int = 12,
    ) -> None:
        if not models:
            raise ValueError("at least one research model is required")
        self.completion = completion
        self.models = models
        self.source_search = source_search
        self.max_sources = max(1, int(max_sources))
        self.citation_integrity = CitationIntegrityEngine()

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are one member of an epistemic research panel. Return strict JSON with keys "
            "summary, claims, questions, contradictions, tags. Claims are candidate hypotheses, not verified facts. "
            "Never invent citations, URLs, measurements, papers or source metadata. Prefer unknown over fabrication."
        )

    @staticmethod
    def _prompt(inquiry: Inquiry, context: dict[str, Any]) -> str:
        return json.dumps({
            "subject": inquiry.subject,
            "questions": inquiry.questions,
            "known_verified_context": context.get("working_context", ()),
            "known_verified_claims": context.get("claims", ()),
            "known_unresolved": context.get("unresolved", ()),
            "task": "Generate falsifiable candidate claims, disagreements, gaps and adjacent concepts. Do not represent a claim as verified.",
        }, ensure_ascii=False)

    async def _observe(self, model: str, inquiry: Inquiry, context: dict[str, Any]) -> ModelObservation:
        raw = await self.completion(model, self._prompt(inquiry, context), self._system_prompt())
        data = _extract_json(raw)
        return ModelObservation(
            model=model,
            summary=" ".join(str(data.get("summary") or "").split())[:8000],
            claims=_texts(data.get("claims")),
            questions=_texts(data.get("questions")),
            contradictions=_texts(data.get("contradictions")),
            tags=_texts(data.get("tags"), limit=16),
        )

    @staticmethod
    def _source(raw: dict[str, Any]) -> ResearchSource | None:
        source = str(raw.get("source") or raw.get("source_id") or "").strip()
        if not source:
            return None
        group = str(raw.get("independence_group") or source).strip()
        quality = max(0.0, min(1.0, float(raw.get("quality", raw.get("confidence", 0.0)) or 0.0)))
        excerpt = str(raw.get("excerpt") or "")[:6000]
        return ResearchSource(
            source=source[:1000],
            locator=str(raw.get("locator") or "")[:2000],
            excerpt=excerpt,
            quality=quality,
            kind=str(raw.get("kind") or "unsourced"),
            independence_group=group[:500],
            claim_bindings=_bindings(raw.get("claim_bindings"), excerpt=excerpt),
            supports_claims=_texts(raw.get("supports_claims"), limit=32),
            contradicts_claims=_texts(raw.get("contradicts_claims"), limit=32),
            observed_at=str(raw.get("observed_at") or "")[:100],
            reproducible=bool(raw.get("reproducible", False)),
            peer_reviewed=bool(raw.get("peer_reviewed", False)),
            primary=bool(raw.get("primary", False)),
            provenance_verified=bool(raw.get("provenance_verified", raw.get("verified_locator", False))),
            preregistered=bool(raw.get("preregistered", False)),
            data_available=bool(raw.get("data_available", False)),
            code_available=bool(raw.get("code_available", False)),
            sample_size=_positive_int(raw.get("sample_size")),
            uncertainty_reported=bool(raw.get("uncertainty_reported", False)),
            content_sha256=str(raw.get("content_sha256") or "")[:64].lower(),
            parent_source_ids=_texts(raw.get("parent_source_ids"), limit=32),
        )

    async def __call__(self, inquiry: Inquiry, context: dict[str, Any]) -> dict[str, Any]:
        observations = await asyncio.gather(
            *(self._observe(model, inquiry, context) for model in self.models),
            return_exceptions=True,
        )
        valid = [x for x in observations if isinstance(x, ModelObservation) and (x.summary or x.claims)]
        if not valid:
            errors = [type(x).__name__ for x in observations if isinstance(x, Exception)]
            raise RuntimeError(f"curiosity research ensemble produced no usable observations: {errors}")

        claim_votes: dict[str, tuple[str, int]] = {}
        questions: list[str] = []
        contradictions: list[str] = []
        tags: list[str] = []
        summaries: list[str] = []
        for obs in valid:
            if obs.summary:
                summaries.append(obs.summary)
            for claim in obs.claims:
                key = claim.casefold()
                original, votes = claim_votes.get(key, (claim, 0))
                claim_votes[key] = (original, votes + 1)
            questions.extend(obs.questions)
            contradictions.extend(obs.contradictions)
            tags.extend(obs.tags)
        candidate_claims = [claim for claim, _ in claim_votes.values()]
        single_model = [claim for claim, votes in claim_votes.values() if votes == 1 and len(valid) > 1]
        contradictions.extend(
            f"MODEL PANEL DISAGREEMENT — candidate not independently established: {claim}"
            for claim in single_model[:16]
        )

        sources: list[ResearchSource] = []
        if self.source_search is not None:
            for raw in await self.source_search(inquiry, inquiry.questions):
                if isinstance(raw, dict):
                    source = self._source(raw)
                    if source is not None:
                        sources.append(source)
                if len(sources) >= self.max_sources:
                    break

        canonical_claims = {claim.casefold(): claim for claim in candidate_claims}
        claim_evidence: dict[str, list[dict[str, Any]]] = {claim: [] for claim in candidate_claims}
        citation_reports: list[dict[str, Any]] = []
        for source in sources:
            common = {
                "source_id": source.source,
                "source": source.source,
                "locator": source.locator,
                "kind": source.kind,
                "independence_group": source.independence_group,
                "quality": source.quality,
                "observed_at": source.observed_at,
                "reproducible": source.reproducible,
                "peer_reviewed": source.peer_reviewed,
                "primary": source.primary,
                "provenance_verified": source.provenance_verified,
                "preregistered": source.preregistered,
                "data_available": source.data_available,
                "code_available": source.code_available,
                "sample_size": source.sample_size,
                "uncertainty_reported": source.uncertainty_reported,
                "content_sha256": source.content_sha256,
                "parent_source_ids": list(source.parent_source_ids),
            }
            for binding in source.claim_bindings:
                claim = canonical_claims.get(binding.claim.casefold())
                if claim is None:
                    citation_reports.append({
                        "source_id": source.source, "claim": binding.claim,
                        "accepted": False, "laundering_risk": "high",
                        "reasons": ["binding_claim_not_in_candidate_set"],
                    })
                    continue
                report = self.citation_integrity.validate(CitationBinding(
                    claim=claim,
                    source_id=source.source,
                    locator=source.locator,
                    binding_method=binding.binding_method,
                    evidence_span=binding.evidence_span,
                    supports=binding.supports,
                    provenance_verified=source.provenance_verified,
                    source_content_sha256=source.content_sha256,
                    mapping_rationale=binding.mapping_rationale,
                ))
                citation_reports.append({
                    "source_id": source.source, "claim": claim,
                    "accepted": report.accepted, "laundering_risk": report.laundering_risk,
                    "reasons": list(report.reasons), "attestation_sha256": report.attestation_sha256,
                })
                if report.accepted:
                    claim_evidence[claim].append({
                        **common, "supports": binding.supports,
                        "citation_binding_attestation_sha256": report.attestation_sha256,
                    })

            # Legacy claim labels are deliberately not promotion evidence. Record a
            # laundering diagnostic so providers can migrate instead of failing silently.
            legacy_claims = (*source.supports_claims, *source.contradicts_claims)
            for raw_claim in legacy_claims:
                if not any(b.claim.casefold() == raw_claim.casefold() for b in source.claim_bindings):
                    citation_reports.append({
                        "source_id": source.source, "claim": raw_claim,
                        "accepted": False, "laundering_risk": "critical",
                        "reasons": ["legacy_claim_label_without_inspectable_binding"],
                    })

        summary = summaries[0] if summaries else f"Research panel generated {len(candidate_claims)} candidate claims."
        if sources:
            summary += f" {len(sources)} source record(s) were examined; claim promotion remains verifier-controlled."
        return {
            "title": f"Curiosity research: {inquiry.subject}",
            "summary": summary,
            "claims": candidate_claims,
            "questions": list(dict.fromkeys(questions))[:24],
            "contradictions": list(dict.fromkeys(contradictions))[:24],
            "tags": list(dict.fromkeys(tags))[:24],
            "claim_evidence": claim_evidence,
            "falsifiable": {claim: True for claim in candidate_claims},
            "panel": [asdict(obs) for obs in valid],
            "source_count": len(sources),
            "provenance_verified_source_count": sum(source.provenance_verified for source in sources),
            "claim_bound_evidence_count": sum(len(v) for v in claim_evidence.values()),
            "citation_integrity": {
                "accepted": sum(bool(row.get("accepted")) for row in citation_reports),
                "rejected": sum(not bool(row.get("accepted")) for row in citation_reports),
                "reports": citation_reports[:128],
            },
        }


async def llm_router_completion(task: str, prompt: str, system: str) -> str:
    from routes.llm_router import route_complete
    result = await route_complete(task=task, prompt=prompt, system=system, use_cache=False)
    if not isinstance(result, dict):
        return str(result)
    for key in ("response", "content", "text", "output"):
        if result.get(key):
            return str(result[key])
    return json.dumps(result, ensure_ascii=False)


def default_ensemble_researcher(*, source_search: SourceSearch | None = None) -> EnsembleCuriosityResearcher:
    return EnsembleCuriosityResearcher(llm_router_completion, source_search=source_search)
