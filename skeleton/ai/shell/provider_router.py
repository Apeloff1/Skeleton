"""Route planning to providers using health and empirical trust signals."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.provider_health import ProviderHealth, ProviderHealthRegistry
from skeleton.shells.ai.trust import ModelTrustRegistry


@dataclass(frozen=True)
class ProviderRoute:
    model: AIModelPort
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model.model_id,
            "score": self.score,
            "reasons": list(self.reasons),
        }


class AIProviderRouter:
    """Provider routing is advisory and never changes execution authority."""

    def __init__(
        self,
        health: ProviderHealthRegistry,
        trust: ModelTrustRegistry | None = None,
    ) -> None:
        self.health = health
        self.trust = trust

    def route(self, models: tuple[AIModelPort, ...]) -> tuple[ProviderRoute, ...]:
        result = []
        seen = set()
        for model in models:
            if model.model_id in seen:
                continue
            seen.add(model.model_id)
            snapshot = self.health.snapshot(model.model_id)
            score = 0.0
            reasons = []
            if snapshot.state is ProviderHealth.QUARANTINED:
                score -= 1000
                reasons.append("provider quarantined")
            elif snapshot.state is ProviderHealth.UNHEALTHY:
                score -= 100
                reasons.append("provider unhealthy")
            elif snapshot.state is ProviderHealth.DEGRADED:
                score -= 25
                reasons.append("provider degraded")
            elif snapshot.state is ProviderHealth.HEALTHY:
                score += 10
                reasons.append("provider healthy")
            else:
                reasons.append("provider health unknown")
            if snapshot.avg_latency_ms:
                score -= min(20.0, snapshot.avg_latency_ms / 1000.0)
                reasons.append("latency penalty applied")
            if self.trust is not None:
                try:
                    profile = self.trust.profile(model.model_id)
                except KeyError:
                    profile = None
                if profile is not None:
                    score += profile.trust_score * 30.0
                    reasons.append("empirical trust signal applied")
            if model.capabilities.structured_output:
                score += 5
            if model.capabilities.tool_use:
                score += 5
            if model.capabilities.critique:
                score += 2
            result.append(ProviderRoute(model, score, tuple(reasons)))
        result.sort(key=lambda item: (-item.score, item.model.model_id))
        return tuple(result)
