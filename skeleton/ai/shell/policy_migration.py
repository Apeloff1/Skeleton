"""Risk-classified diffs for AI autonomy policy changes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.policy import AIShellPolicy


class AIPolicyChangeRisk(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    BREAKING = "breaking"


@dataclass(frozen=True)
class AIPolicyChange:
    code: str
    risk: AIPolicyChangeRisk
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "risk": self.risk.value,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class AIPolicyMigration:
    changes: tuple[AIPolicyChange, ...]

    @property
    def requires_review(self) -> bool:
        return any(item.risk is not AIPolicyChangeRisk.SAFE for item in self.changes)

    @property
    def breaking(self) -> bool:
        return any(item.risk is AIPolicyChangeRisk.BREAKING for item in self.changes)

    def to_dict(self) -> dict[str, object]:
        return {
            "requires_review": self.requires_review,
            "breaking": self.breaking,
            "changes": [item.to_dict() for item in self.changes],
        }


class AIPolicyMigrationPlanner:
    def compare(self, old: AIShellPolicy, new: AIShellPolicy) -> AIPolicyMigration:
        changes = []
        if old.autonomy != new.autonomy:
            risk = (
                AIPolicyChangeRisk.SAFE
                if new.autonomy.value in {"observe", "propose"}
                and old.autonomy.value not in {"observe", "propose"}
                else AIPolicyChangeRisk.REVIEW
            )
            changes.append(AIPolicyChange("autonomy_changed", risk, f"{old.autonomy.value}->{new.autonomy.value}"))
        if new.max_actions < old.max_actions:
            changes.append(AIPolicyChange("max_actions_narrowed", AIPolicyChangeRisk.SAFE, "maximum action count decreased"))
        elif new.max_actions > old.max_actions:
            changes.append(AIPolicyChange("max_actions_widened", AIPolicyChangeRisk.REVIEW, "maximum action count increased"))
        if new.min_confidence > old.min_confidence:
            changes.append(AIPolicyChange("confidence_narrowed", AIPolicyChangeRisk.SAFE, "minimum confidence increased"))
        elif new.min_confidence < old.min_confidence:
            changes.append(AIPolicyChange("confidence_widened", AIPolicyChangeRisk.REVIEW, "minimum confidence decreased"))
        if new.max_uncertainty < old.max_uncertainty:
            changes.append(AIPolicyChange("uncertainty_narrowed", AIPolicyChangeRisk.SAFE, "maximum uncertainty decreased"))
        elif new.max_uncertainty > old.max_uncertainty:
            changes.append(AIPolicyChange("uncertainty_widened", AIPolicyChangeRisk.REVIEW, "maximum uncertainty increased"))
        removed_denials = old.denied_effects - new.denied_effects
        added_denials = new.denied_effects - old.denied_effects
        if removed_denials:
            changes.append(AIPolicyChange("effect_denials_removed", AIPolicyChangeRisk.REVIEW, "one or more denied effects became available"))
        if added_denials:
            changes.append(AIPolicyChange("effect_denials_added", AIPolicyChangeRisk.BREAKING, "one or more effects became denied"))
        if old.deny_unknown_effects and not new.deny_unknown_effects:
            changes.append(AIPolicyChange("unknown_effects_allowed", AIPolicyChangeRisk.REVIEW, "unknown effects are no longer denied"))
        if not old.deny_unknown_effects and new.deny_unknown_effects:
            changes.append(AIPolicyChange("unknown_effects_denied", AIPolicyChangeRisk.BREAKING, "unknown effects became denied"))
        added_auto = new.auto_execute_bands - old.auto_execute_bands
        removed_auto = old.auto_execute_bands - new.auto_execute_bands
        if added_auto:
            changes.append(AIPolicyChange("auto_execute_widened", AIPolicyChangeRisk.REVIEW, "additional risk bands became autonomous"))
        if removed_auto:
            changes.append(AIPolicyChange("auto_execute_narrowed", AIPolicyChangeRisk.BREAKING, "autonomous risk bands were removed"))
        if old.require_reversible_for_autonomy and not new.require_reversible_for_autonomy:
            changes.append(AIPolicyChange("reversibility_relaxed", AIPolicyChangeRisk.REVIEW, "autonomous plans need not be reversible"))
        if not old.require_reversible_for_autonomy and new.require_reversible_for_autonomy:
            changes.append(AIPolicyChange("reversibility_required", AIPolicyChangeRisk.BREAKING, "autonomous plans must now be reversible"))
        return AIPolicyMigration(tuple(changes))
