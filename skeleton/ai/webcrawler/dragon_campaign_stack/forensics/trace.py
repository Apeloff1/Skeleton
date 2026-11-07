"""Deterministic, tamper-evident forensic stage chain.

SHA-256 records are integrity commitments, never cryptographic source-policy
authentication, human signatures, knowledge grants or execution permissions.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import digest, exact_digest, integer


ORDER = (
    "exact_selected_source_custody",
    "source_text_security_inspection",
    "anchored_passage_geometry",
    "possible_source_reuse",
    "objective_failure_counterfactual",
    "source_boilerplate_screening",
    "bounded_capture_age_analysis",
    "cross_source_sentence_echoes",
    "active_content_render_risk",
    "privacy_and_secret_exposure",
    "objective_host_concentration",
    "possible_polarity_collisions",
    "canonical_capture_provenance_posture",
    "operator_objective_grounding",
    "selected_reference_concentration",
    "mandate_consent_horizon",
    "reverse_source_objective_usage",
    "policy_bound_research_deficit_matrix",
    "untrusted_context_resource_budget",
    "captured_extraction_quality_diagnostics",
    "operator_query_rank_support_audit",
    "captured_origin_redirect_hygiene",
    "objective_selection_fairness_metrics",
    "conservative_risky_source_ablation",
    "script_coverage_lexical_limitations",
    "review_only_forensic_queue",
)


@dataclass(frozen=True)
class ForensicStage:
    number: int
    name: str
    prior_chain_digest: str
    receipt_digest: str
    chain_digest: str
    external_effect_committed: bool = False
    content_trusted: bool = False


def chain_forensic_receipts(
    mandate_digest: str, snapshot_digest: str, policy_digest: str,
    receipts: tuple[tuple[str, str], ...],
) -> tuple[ForensicStage, ...]:
    for name, value in (
        ("mandate", mandate_digest), ("snapshot", snapshot_digest),
        ("source policy", policy_digest),
    ):
        exact_digest(value, name)
    if not isinstance(receipts, tuple) or tuple(x[0] for x in receipts) != ORDER:
        raise ValueError("forensic stages must be complete and ordered")
    chain = digest({
        "schema": "skeleton.dragon.forensics.v1",
        "mandate": mandate_digest, "snapshot": snapshot_digest,
        "policy": policy_digest,
    })
    stages = []
    for number, (name, receipt) in enumerate(receipts):
        exact_digest(receipt, name + " digest")
        prior = chain
        chain = digest({"number": number, "name": name,
                        "prior": prior, "receipt": receipt})
        stages.append(ForensicStage(number, name, prior, receipt, chain))
    return tuple(stages)


def verify_forensic_stage_chain(
    stages: tuple[ForensicStage, ...],
    mandate_digest: str, snapshot_digest: str, policy_digest: str,
    receipts: tuple[tuple[str, str], ...],
) -> None:
    expected = chain_forensic_receipts(
        mandate_digest, snapshot_digest, policy_digest, receipts,
    )
    if not isinstance(stages, tuple) or stages != expected:
        raise PermissionError("forensic stage receipt chain was altered")
