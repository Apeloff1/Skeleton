"""Conservative architecture hypotheses derived from observable evidence."""

from __future__ import annotations

from collections import defaultdict

from .contracts import EvidenceBundle, InferenceClaim, ProbeKind, ensure_supported_claims
from .fingerprint import fingerprint_bundle


def _claim(
    claim_id: str,
    statement: str,
    confidence: float,
    probes: set[str],
    *,
    supported: bool,
    falsifiers: tuple[str, ...],
) -> InferenceClaim:
    return InferenceClaim(
        claim_id=claim_id,
        statement=statement,
        confidence=round(max(0.0, min(1.0, confidence)), 6),
        evidence_probe_ids=tuple(sorted(probes)),
        falsifiers=falsifiers,
        status="supported" if supported else "hypothesis",
    )


def infer_architecture(bundle: EvidenceBundle) -> tuple[InferenceClaim, ...]:
    """Infer only properties justified by repeatable black-box observations.

    These are hypotheses about observable behavior, not claims about proprietary
    source code, hidden weights, implementation identity, or vendor internals.
    """
    by_kind: dict[ProbeKind, list] = defaultdict(list)
    for obs in bundle.observations:
        by_kind[obs.kind].append(obs)

    claims: list[InferenceClaim] = []
    deterministic = by_kind.get(ProbeKind.DETERMINISM, [])
    if deterministic:
        groups: dict[str, set[str]] = defaultdict(set)
        for obs in deterministic:
            if obs.success:
                groups[obs.probe_id].add(obs.output_digest)
        usable = {pid: vals for pid, vals in groups.items() if vals}
        if usable:
            stable = sum(1 for vals in usable.values() if len(vals) == 1)
            ratio = stable / len(usable)
            claims.append(
                _claim(
                    "observable.repeatability",
                    "Observed deterministic probes are repeatable under the tested conditions.",
                    0.55 + 0.4 * ratio,
                    set(usable),
                    supported=ratio >= 0.8,
                    falsifiers=("repeat probe under equivalent conditions and observe divergent outputs",),
                )
            )

    state = by_kind.get(ProbeKind.STATE, [])
    if state:
        probe_ids = {obs.probe_id for obs in state}
        flagged = sum("stateful" in obs.feature_flags for obs in state)
        ratio = flagged / len(state)
        claims.append(
            _claim(
                "observable.statefulness",
                "The target exposes state-dependent behavior under the tested probe protocol.",
                0.5 + 0.45 * ratio,
                probe_ids,
                supported=ratio >= 0.6,
                falsifiers=("replay the same state probes in isolated sessions and eliminate the effect",),
            )
        )

    tooling = by_kind.get(ProbeKind.TOOLING, [])
    if tooling:
        probe_ids = {obs.probe_id for obs in tooling}
        flagged = sum("tool_boundary" in obs.feature_flags for obs in tooling)
        ratio = flagged / len(tooling)
        claims.append(
            _claim(
                "observable.tool_boundary",
                "The target exposes a distinguishable tool-use boundary under the tested protocol.",
                0.5 + 0.45 * ratio,
                probe_ids,
                supported=ratio >= 0.6,
                falsifiers=("repeat with tool-disabled controls and observe the same boundary markers",),
            )
        )

    context = by_kind.get(ProbeKind.CONTEXT, [])
    if context:
        probe_ids = {obs.probe_id for obs in context}
        flagged = sum("context_boundary" in obs.feature_flags for obs in context)
        ratio = flagged / len(context)
        claims.append(
            _claim(
                "observable.context_boundary",
                "The target exposes a measurable context boundary under the tested inputs.",
                0.45 + 0.5 * ratio,
                probe_ids,
                supported=ratio >= 0.6,
                falsifiers=("increase/decrease controlled context lengths and fail to reproduce the boundary",),
            )
        )

    refusal = by_kind.get(ProbeKind.REFUSAL, [])
    if refusal:
        probe_ids = {obs.probe_id for obs in refusal}
        flagged = sum("policy_refusal" in obs.feature_flags for obs in refusal)
        ratio = flagged / len(refusal)
        claims.append(
            _claim(
                "observable.refusal_policy",
                "The target exposes a repeatable refusal/policy boundary under the tested probes.",
                0.45 + 0.5 * ratio,
                probe_ids,
                supported=ratio >= 0.6,
                falsifiers=("controlled semantic paraphrases eliminate the observed refusal boundary",),
            )
        )

    if not claims and bundle.observations:
        fingerprint_bundle(bundle)
        claims.append(
            InferenceClaim(
                claim_id="observable.behavioral_fingerprint",
                statement="A deterministic behavioral fingerprint was captured; no architecture claim is yet supported.",
                confidence=0.5,
                evidence_probe_ids=bundle.probe_ids(),
                falsifiers=("collect additional targeted probes that invalidate the current fingerprint",),
                status="hypothesis",
            )
        )

    ensure_supported_claims(claims, bundle)
    return tuple(sorted(claims, key=lambda item: item.claim_id))
