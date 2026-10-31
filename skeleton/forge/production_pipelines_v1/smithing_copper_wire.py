"""Deterministic copper wire production pipeline.

One production lot has a three-stage workflow. The caller authenticates
operator and evidence provenance and stores the complete ledger atomically.
No physical device actuation or external inventory transfer occurs here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "skeleton.production_pipeline.v1"
RECIPE_ID = "smithing_copper_wire"
DOMAIN = "smithing"
STAGES = ("prepare", "fabricate", "inspect")
MATERIAL_COST = 6
ENERGY_PER_STAGE = 7
YIELD_PER_BATCH = 1
WASTE_PER_BATCH = 0
BATCH_LIMIT = 5
INITIAL_MATERIAL = 38
INITIAL_ENERGY = 73
MAX_EVENTS = 4096
MAX_STOCK = 100000


@dataclass(frozen=True, slots=True)
class ProductionState:
    status: str = "idle"
    stage: int = 0
    batch: int = 0
    materials: int = INITIAL_MATERIAL
    energy: int = INITIAL_ENERGY
    products: int = 0
    scrap: int = 0
    spent_materials: int = 0
    version: int = 0
    tick: int = 0
    event_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in (
            "idle", "working", "completed", "cancelled"
        ):
            raise ValueError("invalid-status")
        if type(self.stage) is not int or not 0 <= self.stage <= len(STAGES):
            raise ValueError("invalid-stage")
        if type(self.batch) is not int or not 0 <= self.batch <= BATCH_LIMIT:
            raise ValueError("invalid-batch")
        for key in (
            "materials", "energy", "products", "scrap", "spent_materials"
        ):
            value = getattr(self, key)
            if type(value) is not int or not 0 <= value <= MAX_STOCK:
                raise ValueError("invalid-" + key)
        for key in ("version", "tick"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError("invalid-" + key)
        if self.status == "idle" and (self.stage != 0 or self.batch != 0):
            raise ValueError("idle-with-active-batch")
        if self.status == "working" and not (0 <= self.stage <= len(STAGES) and self.batch > 0):
            raise ValueError("invalid-working-stage")
        if self.status == "completed" and (self.stage != len(STAGES) or self.batch == 0):
            raise ValueError("invalid-completion")
        if self.status == "cancelled" and self.batch == 0:
            raise ValueError("invalid-cancellation")
        if type(self.event_ids) is not frozenset or len(self.event_ids) > MAX_EVENTS:
            raise ValueError("invalid-event-ledger")
        if any(type(key) is not str or not 1 <= len(key) <= 128 for key in self.event_ids):
            raise ValueError("invalid-event-identity")


@dataclass(frozen=True, slots=True)
class ProductionReceipt:
    event_id: str
    accepted: bool
    reason: str
    previous_version: int
    next_version: int
    status: str
    stage: int
    product_delta: int


def _command(raw: dict[str, Any]) -> tuple[str, str, int, int, int, str]:
    if type(raw) is not dict or set(raw) != {
        "id", "action", "batch", "expected_version", "tick", "evidence"
    }:
        raise ValueError("invalid-command-shape")
    event_id, action, batch, version, tick, evidence = (
        raw["id"], raw["action"], raw["batch"],
        raw["expected_version"], raw["tick"], raw["evidence"]
    )
    if type(event_id) is not str or not 1 <= len(event_id) <= 128:
        raise ValueError("invalid-id")
    if type(action) is not str or action not in (
        "start", "advance", "finish", "cancel", "observe"
    ):
        raise ValueError("invalid-action")
    if type(batch) is not int or not 1 <= batch <= BATCH_LIMIT:
        raise ValueError("invalid-batch")
    if type(version) is not int or version < 0:
        raise ValueError("invalid-expected-version")
    if type(tick) is not int or tick < 0:
        raise ValueError("invalid-tick")
    if type(evidence) is not str or len(evidence) > 128:
        raise ValueError("invalid-evidence")
    return event_id, action, batch, version, tick, evidence


def transition(
    state: ProductionState, raw: dict[str, Any]
) -> tuple[ProductionState, ProductionReceipt]:
    """Evaluate one command with monotonic tick/version and replay fencing."""
    if type(state) is not ProductionState:
        raise TypeError("invalid-production-state")
    event_id, action, batch, version, tick, evidence = _command(raw)

    def reject(reason: str) -> tuple[ProductionState, ProductionReceipt]:
        return state, ProductionReceipt(
            event_id, False, reason, state.version, state.version,
            state.status, state.stage, 0
        )

    if event_id in state.event_ids:
        return reject("duplicate-event")
    if version != state.version:
        return reject("stale-version")
    if tick <= state.tick:
        return reject("nonmonotonic-tick")
    if len(state.event_ids) >= MAX_EVENTS:
        return reject("event-ledger-full")
    if action == "observe":
        return reject("observation-readonly")
    status, stage, lot = state.status, state.stage, state.batch
    materials, energy = state.materials, state.energy
    products, scrap, spent = state.products, state.scrap, state.spent_materials
    reason = "accepted"
    added = 0

    if action == "start":
        if status != "idle":
            return reject("already-started")
        required = MATERIAL_COST * batch
        if materials < required:
            return reject("insufficient-material")
        materials -= required
        spent += required
        lot = batch
        status = "working"
        reason = "lot-started"
    elif action == "advance":
        if status != "working" or batch != lot:
            return reject("not-current-lot")
        if stage >= len(STAGES):
            return reject("stages-complete-awaiting-quality")
        if not evidence:
            return reject("stage-evidence-missing")
        required_energy = ENERGY_PER_STAGE * lot
        if energy < required_energy:
            return reject("insufficient-energy")
        energy -= required_energy
        stage += 1
        reason = "stage-advanced"
        if stage == len(STAGES):
            # All physical work is complete; final acceptance is separate.
            status = "working"
    elif action == "finish":
        if status != "working" or batch != lot:
            return reject("not-current-lot")
        if stage != len(STAGES):
            return reject("stages-incomplete")
        if not evidence:
            return reject("quality-evidence-missing")
        added = YIELD_PER_BATCH * lot
        waste = WASTE_PER_BATCH * lot
        if products + added > MAX_STOCK or scrap + waste > MAX_STOCK:
            return reject("output-capacity")
        products += added
        scrap += waste
        status = "completed"
        reason = "production-accepted"
    elif action == "cancel":
        if status != "working" or batch != lot:
            return reject("not-current-lot")
        status = "cancelled"
        reason = "cancelled-no-output"

    updated = ProductionState(
        status=status, stage=stage, batch=lot,
        materials=materials, energy=energy, products=products,
        scrap=scrap, spent_materials=spent,
        version=state.version + 1, tick=tick,
        event_ids=state.event_ids | {event_id}
    )
    return updated, ProductionReceipt(
        event_id, True, reason, state.version, updated.version,
        updated.status, updated.stage, added
    )


def snapshot(state: ProductionState) -> dict[str, Any]:
    if type(state) is not ProductionState:
        raise TypeError("invalid-production-state")
    return {
        "schema": SCHEMA, "recipe_id": RECIPE_ID, "domain": DOMAIN,
        "status": state.status, "stage": state.stage,
        "stage_count": len(STAGES), "batch": state.batch,
        "materials": state.materials, "energy": state.energy,
        "products": state.products, "scrap": state.scrap,
        "spent_materials": state.spent_materials, "version": state.version,
        "tick": state.tick, "event_count": len(state.event_ids),
        "material_unit_cost": MATERIAL_COST, "energy_per_stage": ENERGY_PER_STAGE,
        "expected_yield_per_batch": YIELD_PER_BATCH,
    }


def replay(
    commands: list[dict[str, Any]], initial: ProductionState | None = None
) -> tuple[ProductionState, tuple[ProductionReceipt, ...]]:
    if type(commands) is not list or len(commands) > MAX_EVENTS:
        raise ValueError("invalid-command-batch")
    state = ProductionState() if initial is None else initial
    receipts: list[ProductionReceipt] = []
    for command in commands:
        state, receipt = transition(state, command)
        receipts.append(receipt)
    return state, tuple(receipts)
