"""Plan provenance via b038 ``GenerationProvenance``/``ProvenanceLedger``.

No new receipt type: the routing receipt is folded into ``parameters`` and
``sources``, so ``to_record()`` keeps the b038 shape.
"""
from __future__ import annotations

from typing import Any

from skeleton.forge.game_design_spec import spec_digest
from skeleton.gameforge.batch_b038 import (
    EvalRecord,
    GenerationProvenance,
    ProvenanceLedger,
    SourceRef,
    Transformation,
    digest,
)

from .model_planner import PlanOutcome


def plan_provenance(outcome: PlanOutcome, *, evals: tuple[EvalRecord, ...] = ()) -> GenerationProvenance:
    r = outcome.receipt
    compiled_d = spec_digest(outcome.compiled)
    final_d = spec_digest(outcome.spec)
    transforms = [Transformation("compile_brief", digest(outcome.brief), compiled_d, "deterministic")]
    if final_d != compiled_d:
        transforms.append(Transformation("plan_guard", compiled_d, final_d, ",".join(outcome.violations)))
    served = r.served_by if outcome.used_model else None
    return GenerationProvenance(
        artifact_id=str(outcome.spec["spec_id"]),
        artifact_digest=final_d,
        model=served or "compile_brief",
        provider=served or "compiler",
        input_digest=digest(outcome.brief),
        parameters={
            "source": outcome.source,
            "fallback_reason": outcome.fallback_reason,
            "route_status": r.status,
            "route_backend": r.backend,
            "route_request_id": r.request_id,
            "route_receipt_digest": r.receipt_digest(),
            "route_rejected": {k: list(v) for k, v in r.rejected.items()},
            "capability_decisions": list(r.capability_decisions),
            "violations": list(outcome.violations),
        },
        sources=(SourceRef("routing_receipt", r.request_id, r.receipt_digest()),),
        transformations=tuple(transforms),
        evals=tuple(evals),
    )


class PlanLedger(ProvenanceLedger):
    """ProvenanceLedger that can take a :class:`PlanOutcome` directly."""

    def record(self, outcome: PlanOutcome, **kw: Any) -> str:
        return self.append(plan_provenance(outcome, **kw))
