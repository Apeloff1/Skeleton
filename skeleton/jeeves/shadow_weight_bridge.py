"""Host-gated Jeeves access to the canonical training shadow-weight queue.

Jeeves has no credential, default writable store, global singleton or access to
other tenants' shadow records. The application must explicitly inject a
tenant-scoped queue plus a per-call read authorizer. Writes require a separate
host authorizer AND the existing HIGH_IMPACT ToolExecutor grant.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from typing import Any

from skeleton.ai.training.flgb_training_runtime import digest_json
from skeleton.ai.training.shadow_weight_pipeline import (
    ShadowReview, ShadowState, ShadowWeightIntake, ShadowWeightPipeline,
    ShadowWeightError, SourceAttestation,
)
from skeleton.ai.training.shadow_weight_store import DurableShadowWeightPipeline

MAX_REQUEST_BYTES = 64 * 1024
MAX_PAGE = 64


def _intent(tool_name: str, arguments: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            {"tool": tool_name, "arguments": dict(arguments)},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShadowWeightError("invalid shadow tool payload") from exc
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ShadowWeightError("shadow tool request exceeds size budget")
    return digest_json({"tool": tool_name, "arguments": dict(arguments)})


def _source(raw: Mapping[str, Any]) -> SourceAttestation:
    keys = {
        "source_id", "content_digest", "claim_digest", "independence_group",
        "rights_status", "rights_evidence_digest", "observed_at_ns",
    }
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ShadowWeightError("source attestation must contain exact contract fields")
    return SourceAttestation(**raw)


def _intake(raw: Any) -> ShadowWeightIntake:
    if not isinstance(raw, dict):
        raise ShadowWeightError("intake payload must be an object")
    keys = {
        "intake_id", "subject_id", "claim_digest", "target_scope",
        "sources", "proposed_dataset_digest", "parent_model_digest",
        "proposed_by", "relevance_ppm", "confidence_ppm", "novelty_ppm",
        "observed_at_ns",
    }
    if set(raw) != keys or not isinstance(raw["sources"], list):
        raise ShadowWeightError("intake does not match exact contract")
    return ShadowWeightIntake(
        **{name: raw[name] for name in keys - {"sources"}},
        sources=tuple(_source(item) for item in raw["sources"]),
    )


def _review(raw: Any) -> ShadowReview:
    if not isinstance(raw, dict):
        raise ShadowWeightError("review payload must be an object")
    keys = {
        "intake_digest", "verifier_id", "reviewed_at_ns", "rights_clear",
        "contamination_clear", "dataset_scope_approved", "evaluator_evidence_digest",
        "contamination_evidence_digest", "decision", "explanation_digest",
    }
    if set(raw) != keys:
        raise ShadowWeightError("review does not match exact contract")
    return ShadowReview(
        **{name: raw[name] for name in keys - {"decision"}},
        decision=ShadowState(raw["decision"]),
    )


def register_shadow_weight_tools(
    registry: Any, *,
    pipeline: ShadowWeightPipeline | DurableShadowWeightPipeline,
    read_authorize: Callable[..., bool],
    write_authorize: Callable[..., bool] | None = None,
    review_verify: Callable[..., bool] | None = None,
    admission_verify: Callable[..., bool] | None = None,
    consume_verify: Callable[..., bool] | None = None,
) -> tuple[str, ...]:
    """Register only explicitly host-scoped shadow tools.

    The authorizers have signature (tool_name, canonical_intent_digest,
    tool_execution_context) -> bool. They should validate tenant, principal,
    project, scope, revocation and exact digest; a bare model request never
    confers rights. A missing write_authorize means no mutation tools exist.
    """
    from skeleton.jeeves.agent.tools import (
        ArgumentRule, ToolDenied, ToolRegistry, ToolSpec,
    )
    from skeleton.jeeves.agent.types import RiskTier

    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be ToolRegistry")
    if not isinstance(pipeline, (ShadowWeightPipeline, DurableShadowWeightPipeline)):
        raise TypeError("pipeline must be a canonical shadow evidence owner")
    if not callable(read_authorize):
        raise TypeError("tenant-scoped read_authorize is required")
    if write_authorize is not None and not callable(write_authorize):
        raise TypeError("write_authorize must be a host callback")
    if write_authorize is not None and not all(callable(f) for f in (
        review_verify, admission_verify, consume_verify,
    )):
        raise TypeError("independent host review, admission and candidate verifiers required")

    def _gate(name: str, args: Mapping[str, Any], context: Any, *, writing: bool) -> None:
        digest = _intent(name, args)
        callback = write_authorize if writing else read_authorize
        if callback is None or callback(name, digest, context) is not True:
            raise ToolDenied("shadow operation denied by owning host")

    def _listing(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
        _gate("shadow_list", args, context, writing=False)
        raw = pipeline.snapshot()
        rows = raw["records"]
        state = args.get("state")
        if state is not None:
            selected = ShadowState(state)
            rows = [row for row in rows if row["state"] == selected.value]
        rows = sorted(rows, key=lambda row: (
            -row["intake"]["relevance_ppm"], row["intake"]["intake_id"],
        ))
        offset, limit = args.get("offset", 0), args.get("limit", 20)
        page = rows[offset:offset + limit]
        return {
            "schema": "jeeves.shadow_list.v1",
            "head_digest": raw["head_digest"],
            "total": len(rows),
            "offset": offset, "limit": limit,
            "has_more": offset + len(page) < len(rows),
            "records": [
                {
                    "intake_id": r["intake"]["intake_id"],
                    "subject_id": r["intake"]["subject_id"],
                    "target_scope": r["intake"]["target_scope"],
                    "state": r["state"], "version": r["version"],
                    "relevance_ppm": r["intake"]["relevance_ppm"],
                    "review_digest": r["review_digest"],
                    "training_manifest_digest": r["training_manifest_digest"],
                }
                for r in page
            ],
            "execution_authority": "none",
        }

    def _get(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
        _gate("shadow_inspect", args, context, writing=False)
        item = pipeline.get(args["intake_id"])
        return {
            "schema": "jeeves.shadow_inspect.v1",
            "record": item.to_dict() if item is not None else None,
            "execution_authority": "none",
        }

    entries: list[tuple[Any, Any]] = [
        (ToolSpec(
            name="shadow_list",
            description="List tenant-authorized shadow evidence candidates and states.",
            risk=RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("state", "string", required=False,
                             choices=tuple(s.value for s in ShadowState)),
                ArgumentRule("limit", "integer", required=False, minimum=1, maximum=MAX_PAGE),
                ArgumentRule("offset", "integer", required=False, minimum=0, maximum=20_000),
            ),
        ), _listing),
        (ToolSpec(
            name="shadow_inspect",
            description="Inspect one tenant-authorized shadow evidence record; no training.",
            risk=RiskTier.READ_ONLY,
            arguments=(ArgumentRule("intake_id", "string", max_length=256),),
        ), _get),
    ]

    if write_authorize is not None:
        def _submit(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            intake = _intake(args["intake"])
            _gate("shadow_submit", args, context, writing=True)
            return pipeline.submit(intake).to_dict()

        def _review_apply(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            review = _review(args["review"])
            _gate("shadow_review", args, context, writing=True)
            current = pipeline.get(args["intake_id"])
            if current is None or review_verify(current, review, context) is not True:
                raise ToolDenied("independent host rejected shadow corroboration")
            return pipeline.review(
                args["intake_id"], review,
                expected_version=args["expected_version"],
            ).to_dict()

        def _admit(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            _gate("shadow_admit_training", args, context, writing=True)
            current = pipeline.get(args["intake_id"])
            if current is None or admission_verify(current, args["training_manifest_digest"],
                                                   args["evidence_digest"], context) is not True:
                raise ToolDenied("independent host rejected training manifest")
            return pipeline.admit_training(
                args["intake_id"], expected_version=args["expected_version"],
                training_manifest_digest=args["training_manifest_digest"],
                training_authority=args["training_authority"],
                evidence_digest=args["evidence_digest"], at_ns=args["at_ns"],
            ).to_dict()

        def _quarantine(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            _gate("shadow_quarantine", args, context, writing=True)
            return pipeline.quarantine(
                args["intake_id"], expected_version=args["expected_version"],
                reason_digest=args["reason_digest"], authority=args["authority"],
                at_ns=args["at_ns"],
            ).to_dict()

        def _consume(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
            _gate("shadow_consume", args, context, writing=True)
            current = pipeline.get(args["intake_id"])
            if current is None or consume_verify(current, args["verified_candidate_digest"],
                                                 context) is not True:
                raise ToolDenied("independent host rejected candidate binding")
            return pipeline.consume(
                args["intake_id"], expected_version=args["expected_version"],
                verified_candidate_digest=args["verified_candidate_digest"],
                authority=args["authority"], at_ns=args["at_ns"],
            ).to_dict()

        common = (
            ArgumentRule("intake_id", "string", max_length=256),
            ArgumentRule("expected_version", "integer", minimum=0, maximum=1_000_000),
        )
        entries.extend((
            (ToolSpec(
                name="shadow_submit",
                description="Host-authorized shadow claim intake; no model weight mutation.",
                risk=RiskTier.HIGH_IMPACT, idempotent=False,
                arguments=(ArgumentRule("intake", "object", max_length=12),),
            ), _submit),
            (ToolSpec(
                name="shadow_review",
                description="Host-authorized independent source review; never self-approve.",
                risk=RiskTier.HIGH_IMPACT, idempotent=False,
                arguments=common + (ArgumentRule("review", "object", max_length=10),),
            ), _review_apply),
            (ToolSpec(
                name="shadow_admit_training",
                description="Host-authorized candidate-only training admission.",
                risk=RiskTier.HIGH_IMPACT, idempotent=False,
                arguments=common + (
                    ArgumentRule("training_manifest_digest", "string", max_length=64),
                    ArgumentRule("training_authority", "string", max_length=256),
                    ArgumentRule("evidence_digest", "string", max_length=64),
                    ArgumentRule("at_ns", "integer", minimum=0),
                ),
            ), _admit),
            (ToolSpec(
                name="shadow_quarantine",
                description="Quarantine an evidence candidate without deleting audit history.",
                risk=RiskTier.HIGH_IMPACT, idempotent=False,
                arguments=common + (
                    ArgumentRule("reason_digest", "string", max_length=64),
                    ArgumentRule("authority", "string", max_length=256),
                    ArgumentRule("at_ns", "integer", minimum=0),
                ),
            ), _quarantine),
            (ToolSpec(
                name="shadow_consume",
                description="Bind externally trained candidate digest, without deployment.",
                risk=RiskTier.HIGH_IMPACT, idempotent=False,
                arguments=common + (
                    ArgumentRule("verified_candidate_digest", "string", max_length=64),
                    ArgumentRule("authority", "string", max_length=256),
                    ArgumentRule("at_ns", "integer", minimum=0),
                ),
            ), _consume),
        ))

    for spec, handler in entries:
        registry.register(spec, handler)
    return tuple(spec.name for spec, _handler in entries)


__all__ = ["register_shadow_weight_tools"]
