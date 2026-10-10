"""Canonical Dragon Forge research-to-game DAG with adversarial rounds.

Constructs explicit stage barriers and two competing design branches.
No worker execution is implied. A caller must supply actual implementations,
capture evidence and approval receipts to satisfy the graph.
"""
from __future__ import annotations
from dataclasses import dataclass

from .dragon_labyrinth import (
    LabyrinthPlan, WorkKind, WorkSpec, plan_labyrinth,
)


@dataclass(frozen=True)
class StudioScale:
    design_rounds: int = 100
    playtest_rounds: int = 1
    max_nodes: int = 10000
    max_cost: int = 100000


def create_studio_plan(owner: str, *, authorized: bool,
                       scale: StudioScale = StudioScale()) -> LabyrinthPlan:
    if not authorized:
        raise PermissionError("studio planning requires authorization")
    if not 1 <= scale.design_rounds <= 10000:
        raise ValueError("invalid design round count")
    if not 1 <= scale.playtest_rounds <= 1000:
        raise ValueError("invalid playtest round count")
    nodes = [
        WorkSpec("01.capture_consent", WorkKind.CAPTURE_REVIEW,
                 approval_required=True),
        WorkSpec("02.frames", WorkKind.FRAME_EXTRACTION,
                 ("01.capture_consent",), cost_units=2),
        WorkSpec("03.temporal", WorkKind.TEMPORAL_ANALYSIS,
                 ("02.frames",), cost_units=4),
        WorkSpec("04.hypotheses", WorkKind.MECHANIC_HYPOTHESIS,
                 ("03.temporal",), cost_units=3),
        WorkSpec("05.causal", WorkKind.CAUSAL_CHALLENGE,
                 ("04.hypotheses",), cost_units=4),
        WorkSpec("06.taste", WorkKind.TASTE_CONFIRMATION,
                 ("05.causal",), approval_required=True),
        WorkSpec("07.distill", WorkKind.KNOWLEDGE_DISTILLATION,
                 ("06.taste",), cost_units=2),
        WorkSpec("08.originality", WorkKind.ORIGINALITY_REVIEW,
                 ("07.distill",), approval_required=True),
    ]
    previous = "08.originality"
    for round_id in range(scale.design_rounds):
        prefix = f"round.{round_id:05d}"
        a, b = f"{prefix}.a", f"{prefix}.b"
        critique = f"{prefix}.critique"
        gate = f"{prefix}.gate"
        nodes.extend((
            WorkSpec(a, WorkKind.DESIGN_PROPOSAL, (previous,), cost_units=2),
            WorkSpec(b, WorkKind.DESIGN_PROPOSAL, (previous,), cost_units=2),
            WorkSpec(critique, WorkKind.ADVERSARIAL_CRITIQUE,
                     (a, b), cost_units=3),
            WorkSpec(gate, WorkKind.REGRESSION_GATE, (critique,), cost_units=2),
        ))
        previous = gate
    nodes.append(WorkSpec(
        "09.prototype", WorkKind.PROTOTYPE_BUILD, (previous,),
        cost_units=5,
    ))
    previous = "09.prototype"
    for round_id in range(scale.playtest_rounds):
        key = f"playtest.{round_id:05d}"
        nodes.append(WorkSpec(
            key, WorkKind.PLAYTEST, (previous,), cost_units=4,
        ))
        previous = key
    nodes.append(WorkSpec(
        "10.release_review", WorkKind.RELEASE_REVIEW,
        (previous,), approval_required=True,
    ))
    return plan_labyrinth(
        owner, tuple(nodes), authorized=True,
        max_nodes=scale.max_nodes, max_cost=scale.max_cost,
    )
