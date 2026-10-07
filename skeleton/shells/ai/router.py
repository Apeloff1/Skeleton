"""Deterministic routing from intent semantics to model-visible command cards."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.catalog import AIToolCard, AIToolCatalog
from skeleton.shells.ai.effects import EffectKind, EffectRegistry
from skeleton.shells.ai.types import AIIntent, IntentKind


_KIND_TAGS = {
    IntentKind.INSPECT: frozenset({"inspect", "read", "status", "query"}),
    IntentKind.BUILD: frozenset({"build", "compile", "package"}),
    IntentKind.TEST: frozenset({"test", "verify", "lint", "check"}),
    IntentKind.MODIFY: frozenset({"edit", "write", "modify"}),
    IntentKind.REPAIR: frozenset({"repair", "fix", "maintenance"}),
    IntentKind.MAINTAIN: frozenset({"maintenance", "status", "cleanup"}),
    IntentKind.DEPLOY: frozenset({"deploy", "release", "publish"}),
    IntentKind.ANALYZE: frozenset({"analyze", "inspect", "query"}),
}


@dataclass(frozen=True)
class RoutedTool:
    card: AIToolCard
    score: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "tool": self.card.to_dict(),
            "score": self.score,
            "reasons": list(self.reasons),
        }


class AIToolRouter:
    def __init__(self, catalog: AIToolCatalog, effects: EffectRegistry) -> None:
        self.catalog = catalog
        self.effects = effects

    def route(self, intent: AIIntent, *, limit: int = 32) -> tuple[RoutedTool, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        preferred = _KIND_TAGS[intent.kind]
        result = []
        for card in self.catalog.cards():
            if not intent.constraint.allows_command(card.name):
                continue
            contract = self.effects.inspect(card.name)
            score = 0
            reasons = []
            matched = preferred & set(card.tags)
            if matched:
                score += 20 + 4 * len(matched)
                reasons.append("intent tags match command tags")
            if contract is not None:
                if contract.idempotent:
                    score += 5
                    reasons.append("command is declared idempotent")
                if contract.reversible:
                    score += 5
                    reasons.append("command is declared reversible")
                if EffectKind.NETWORK in contract.effects and not intent.constraint.allow_network:
                    score -= 50
                    reasons.append("network effect conflicts with intent constraint")
                if (
                    {EffectKind.WRITE_FILESYSTEM, EffectKind.VCS_WRITE} & contract.effects
                    and not intent.constraint.allow_writes
                ):
                    score -= 50
                    reasons.append("write effect conflicts with intent constraint")
                if contract.destructive and not intent.constraint.allow_destructive:
                    score -= 100
                    reasons.append("destructive effect conflicts with intent constraint")
            else:
                score -= 25
                reasons.append("effect contract is missing")
            result.append(RoutedTool(card, score, tuple(reasons)))
        result.sort(key=lambda item: (-item.score, item.card.name))
        return tuple(result[:limit])
