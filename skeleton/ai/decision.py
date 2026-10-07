"""Evidence-bearing, non-executing decision engine for VOL-304."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class DecisionOption:
    option_id: str
    description: str
    admissible: bool
    utility: float | None
    evidence: tuple[str, ...] = ()
    uncertainty: float = 0.0

    def __post_init__(self) -> None:
        if not self.option_id or self.option_id.strip() != self.option_id:
            raise ValueError("option_id must be explicit")
        if not self.description or self.description.strip() != self.description:
            raise ValueError("description must be explicit")
        if self.utility is not None and not isinstance(self.utility, (int, float)):
            raise ValueError("utility must be numeric or absent")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be within [0, 1]")
        if any(not item or item.strip() != item for item in self.evidence):
            raise ValueError("evidence references must be explicit")


@dataclass(frozen=True)
class DecisionContext:
    criteria: tuple[str, ...]
    consequential: bool = False
    max_uncertainty: float = 1.0

    def __post_init__(self) -> None:
        if not self.criteria or any(not c or c.strip() != c for c in self.criteria):
            raise ValueError("decision criteria must be explicit")
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError("decision criteria must be unique")
        if not 0.0 <= self.max_uncertainty <= 1.0:
            raise ValueError("max_uncertainty must be within [0, 1]")


@dataclass(frozen=True)
class Decision:
    selected_option_id: str | None
    considered_option_ids: tuple[str, ...]
    rejected_option_ids: tuple[str, ...]
    criteria: tuple[str, ...]
    evidence: tuple[str, ...]
    uncertainty: float | None
    abstained: bool
    reason: str

    @property
    def executable(self) -> bool:
        """Decisions are recommendations, never execution authority."""
        return False


def decide(context: DecisionContext, options: Sequence[DecisionOption]) -> Decision:
    if not options:
        return Decision(None, (), (), context.criteria, (), None, True, "no_options")
    ids = [o.option_id for o in options]
    if len(ids) != len(set(ids)):
        raise ValueError("decision option IDs must be unique")

    ordered = sorted(options, key=lambda o: o.option_id)
    admissible = [o for o in ordered if o.admissible]
    rejected = tuple(o.option_id for o in ordered if not o.admissible)
    if not admissible:
        return Decision(None, tuple(ids), rejected, context.criteria, (), None, True, "no_admissible_option")

    eligible = [o for o in admissible if o.utility is not None and o.uncertainty <= context.max_uncertainty]
    if context.consequential:
        eligible = [o for o in eligible if o.evidence]
    if not eligible:
        return Decision(None, tuple(ids), rejected, context.criteria, (), None, True, "insufficient_evidence_or_certainty")

    # Preference optimization occurs only inside the already-admissible set.
    ranked = sorted(eligible, key=lambda o: (-float(o.utility), o.uncertainty, o.option_id))
    winner = ranked[0]
    tied = [o for o in ranked if float(o.utility) == float(winner.utility) and o.uncertainty == winner.uncertainty]
    if len(tied) > 1:
        return Decision(None, tuple(ids), rejected, context.criteria, (), None, True, "unresolved_tie")

    evidence = tuple(sorted(set(winner.evidence)))
    return Decision(
        winner.option_id,
        tuple(ids),
        rejected,
        context.criteria,
        evidence,
        winner.uncertainty,
        False,
        "selected_admissible_preference",
    )
