"""Evidence-aware research adapters for the Curiosity Engine.

The pipeline deliberately separates source evidence from model observations.
Model ensemble agreement can generate hypotheses, associations and follow-up
questions, but it does not magically become authoritative evidence. External
source adapters may add verified evidence with explicit locators/confidence.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Awaitable, Callable, Iterable

from core.curiosity_engine import Inquiry


Completion = Callable[[str, str, str], Awaitable[str | dict[str, Any]]]
SourceSearch = Callable[[Inquiry, tuple[str, ...]], Awaitable[Iterable[dict[str, Any]]]]


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source: str
    locator: str
    excerpt: str
    confidence: float
    verified: bool = False


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
            seen.add(key); out.append(text[:3000])
        if len(out) >= limit:
            break
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

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are one member of an epistemic research panel. Return strict JSON with keys "
            "summary, claims, questions, contradictions, tags. Separate known facts from inference. "
            "Never invent citations or URLs. If evidence is absent, phrase claims as hypotheses and "
            "increase questions/contradictions rather than pretending certainty."
        )

    @staticmethod
    def _prompt(inquiry: Inquiry, context: dict[str, Any]) -> str:
        return json.dumps({
            "subject": inquiry.subject,
            "questions": inquiry.questions,
            "known_context": context.get("working_context", ()),
            "known_claims": context.get("claims", ()),
            "known_unresolved": context.get("unresolved", ()),
            "task": "Deepen this subject: identify robust claims, disagreements, gaps, adjacent concepts and falsifiable follow-ups.",
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

    async def __call__(self, inquiry: Inquiry, context: dict[str, Any]) -> dict[str, Any]:
        observations = await asyncio.gather(
            *(self._observe(model, inquiry, context) for model in self.models),
            return_exceptions=True,
        )
        valid = [x for x in observations if isinstance(x, ModelObservation) and (x.summary or x.claims)]
        if not valid:
            errors = [type(x).__name__ for x in observations if isinstance(x, Exception)]
            raise RuntimeError(f"curiosity research ensemble produced no usable observations: {errors}")

        sources: list[ResearchSource] = []
        if self.source_search is not None:
            raw_sources = await self.source_search(inquiry, inquiry.questions)
            for raw in raw_sources:
                if not isinstance(raw, dict) or not str(raw.get("source") or "").strip():
                    continue
                sources.append(ResearchSource(
                    source=str(raw["source"])[:1000],
                    locator=str(raw.get("locator") or "")[:2000],
                    excerpt=str(raw.get("excerpt") or "")[:6000],
                    confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.65)))),
                    verified=bool(raw.get("verified", False)),
                ))
                if len(sources) >= self.max_sources:
                    break

        claim_votes: dict[str, tuple[str, int]] = {}
        all_questions: list[str] = []
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
            all_questions.extend(obs.questions)
            contradictions.extend(obs.contradictions)
            tags.extend(obs.tags)

        consensus = [claim for claim, votes in claim_votes.values() if votes >= max(2, len(valid) // 2 + 1)]
        disputed = [claim for claim, votes in claim_votes.values() if votes == 1 and len(valid) > 1]
        contradictions.extend(f"Panel disagreement / single-model claim: {claim}" for claim in disputed[:16])

        verified = [source for source in sources if source.verified]
        evidence = [
            {"source": source.source, "locator": source.locator, "confidence": source.confidence}
            for source in verified
        ]
        # Model observations are recorded explicitly as non-authoritative evidence.
        if not evidence:
            evidence = [
                {"source": f"model-observation:{obs.model}", "locator": "curiosity-panel", "confidence": 0.30}
                for obs in valid
            ]

        source_excerpt = " ".join(source.excerpt for source in verified[:4] if source.excerpt)
        summary = summaries[0]
        if source_excerpt:
            summary = f"{summary} Verified source excerpts were also retrieved for cross-checking."

        confidence = 0.35
        if verified:
            diversity = len({source.source for source in verified})
            confidence = min(0.92, 0.55 + min(0.25, diversity * 0.06) + min(0.12, len(consensus) * 0.02))
        elif len(valid) >= 3 and consensus:
            confidence = 0.44

        return {
            "title": f"Curiosity research: {inquiry.subject}",
            "summary": summary,
            "claims": consensus,
            "questions": list(dict.fromkeys(all_questions))[:24],
            "contradictions": list(dict.fromkeys(contradictions))[:24],
            "tags": list(dict.fromkeys(tags))[:24],
            "evidence": evidence,
            "confidence": confidence,
            "panel": [asdict(obs) for obs in valid],
            "verified_source_count": len(verified),
            "source_count": len(sources),
        }


async def llm_router_completion(task: str, prompt: str, system: str) -> str:
    """Lazy adapter to the platform LLM router without coupling Curiosity boot to it."""
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
