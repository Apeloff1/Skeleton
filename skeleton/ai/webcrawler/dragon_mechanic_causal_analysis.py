"""Counterfactual gameplay mechanics analysis with explicit evidence limits.

Computes empirical conditional outcome rates and effect intervals from
labelled interventions. Observational contrasts are never presented as
causal effects. Uses conservative Wilson intervals for binary outcomes.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, sqrt


@dataclass(frozen=True)
class MechanicTrial:
    trial_id: str
    mechanic: str
    intervention: bool
    outcome_success: bool
    randomized: bool
    context_group: str
    source_id: str


@dataclass(frozen=True)
class TrialProtocol:
    protocol_id: str
    assignment_digest: str
    preregistered: bool
    allocation_verified: bool
    outcome_definition_locked: bool
    attrition_accounted: bool
    interference_assessed: bool


@dataclass(frozen=True)
class MechanicEffect:
    mechanic: str
    treated_trials: int
    control_trials: int
    treated_rate: float
    control_rate: float
    observed_difference: float
    difference_interval: tuple[float, float]
    causal_claim_permitted: bool
    randomized_effect_estimate_eligible: bool
    protocol_id: str | None
    independent_sources: int
    warnings: tuple[str, ...]


def _wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * sqrt(
        (p * (1 - p) + z * z / (4 * n)) / n
    ) / denom
    return max(0, center - spread), min(1, center + spread)


def analyze_mechanic_trials(
    trials: tuple[MechanicTrial, ...], *,
    authorized: bool, minimum_per_arm: int = 10,
    max_trials: int = 100000,
    protocol: TrialProtocol | None = None,
) -> MechanicEffect:
    if not authorized:
        raise PermissionError("mechanics analysis requires authorization")
    if not 1 <= minimum_per_arm <= 100000 or not 2 <= max_trials <= 1000000:
        raise ValueError("invalid trial budget")
    if not 2 <= len(trials) <= max_trials:
        raise ValueError("invalid trial count")
    mechanic = trials[0].mechanic
    seen = set()
    treated, control = [], []
    sources = set()
    randomized = True
    contexts = set()
    for item in trials:
        if not isinstance(item.trial_id, str) or not 1 <= len(item.trial_id) <= 128:
            raise ValueError("invalid trial id")
        if item.trial_id in seen:
            raise ValueError("duplicate trial id")
        seen.add(item.trial_id)
        if not isinstance(item.mechanic, str) or item.mechanic != mechanic or not 1 <= len(item.mechanic) <= 128:
            raise ValueError("mixed or invalid mechanics")
        if any(not isinstance(v, bool) for v in (
            item.intervention, item.outcome_success, item.randomized,
        )):
            raise ValueError("invalid trial labels")
        if not isinstance(item.context_group, str) or not 1 <= len(item.context_group) <= 128:
            raise ValueError("invalid context group")
        if not isinstance(item.source_id, str) or not 1 <= len(item.source_id) <= 256:
            raise ValueError("invalid source id")
        sources.add(item.source_id)
        contexts.add(item.context_group)
        randomized &= item.randomized
        (treated if item.intervention else control).append(item)
    if not treated or not control:
        raise ValueError("both treatment and control arms required")
    t_success = sum(x.outcome_success for x in treated)
    c_success = sum(x.outcome_success for x in control)
    t_rate = t_success / len(treated)
    c_rate = c_success / len(control)
    t_low, t_high = _wilson(t_success, len(treated))
    c_low, c_high = _wilson(c_success, len(control))
    warnings = []
    if len(treated) < minimum_per_arm or len(control) < minimum_per_arm:
        warnings.append("Insufficient observations in at least one arm")
    if not randomized:
        warnings.append("Observational contrast: causal inference not justified")
    if len(sources) < 2:
        warnings.append("Only one independent source identity")
    if len(contexts) > 1:
        warnings.append("Context heterogeneity may confound the contrast")
    design_eligible = (
        randomized and len(treated) >= minimum_per_arm
        and len(control) >= minimum_per_arm
        and len(contexts) == 1
    )
    protocol_verified = False
    if protocol is None:
        warnings.append("No verified experimental protocol: causal claim prohibited")
    else:
        if not isinstance(protocol.protocol_id, str) or not protocol.protocol_id:
            raise ValueError("invalid protocol id")
        if len(protocol.assignment_digest) != 64 or any(
            c not in "0123456789abcdef" for c in protocol.assignment_digest
        ):
            raise ValueError("invalid assignment digest")
        protocol_verified = all((
            protocol.preregistered,
            protocol.allocation_verified,
            protocol.outcome_definition_locked,
            protocol.attrition_accounted,
            protocol.interference_assessed,
        ))
        if not protocol_verified:
            warnings.append("Experimental protocol verification incomplete")
    # Even a verified protocol only establishes eligibility to interpret this
    # bounded randomized contrast causally under its recorded assumptions.
    causal = design_eligible and protocol_verified
    return MechanicEffect(
        mechanic, len(treated), len(control),
        round(t_rate, 6), round(c_rate, 6),
        round(t_rate - c_rate, 6),
        (round(max(-1, t_low - c_high), 6),
         round(min(1, t_high - c_low), 6)),
        causal, design_eligible,
        protocol.protocol_id if protocol is not None else None,
        len(sources), tuple(warnings),
    )
