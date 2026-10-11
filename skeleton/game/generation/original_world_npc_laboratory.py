"""Long-horizon adversarial NPC world laboratory with replayable public evidence.

No provider calls, trained weights download, statistical quality invention,
off-screen resources, performance promises or background work. Every scenario
runs the real original-world ProductSession, persistent cognition, finite
terrain and citizen physics, recording exact receipts and factual outcomes.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from typing import Sequence

from .original_foundation_compiler import FoundationError
from .original_world_living_10x_compiler import living_for
from .original_world_product_session import (
    ProductAction, ProductSession, create_product,
    step_product, product_save, validate_product,
)
from .original_world_npc_cognition_v2 import cognition_report

SCHEMA = "original-npc-long-horizon-laboratory.v1"
SCENARIOS = ("baseline", "food-shortage", "injured-community",
             "social-isolation", "public-construction",
             "civic-food-aid", "family-expansion")


def _digest(data: object) -> str:
    return sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode()).hexdigest()


def prepare(
    scenario: str, *, population: int = 12,
    root: int = 0, architecture: str = "lattice",
) -> ProductSession:
    if scenario not in SCENARIOS:
        raise FoundationError("unknown evaluated physical NPC world")
    if type(population) is not int or not 1 <= population <= 32:
        raise FoundationError("bounded local population must be 1..32")
    law = living_for(root, "puzzle", architecture, "trophic", "endless")
    state = create_product(law.index, inhabitants=population)
    if scenario == "food-shortage":
        # An explicit adversarial fixture, not a default game-state claim.
        people = tuple(replace(p, hunger=6) for p in state.society.inhabitants)
        state = replace(
            state, terrain=replace(state.terrain, provisions=0),
            society=replace(state.society, inhabitants=people),
        )
    elif scenario == "injured-community":
        first = state.society.inhabitants[0]
        people = (replace(first, health=4),) + state.society.inhabitants[1:]
        state = replace(state, society=replace(state.society,
                                              inhabitants=people))
    elif scenario == "social-isolation":
        state = replace(state, cognition=replace(
            state.cognition, minds=tuple(
                replace(m, loneliness=18, stress=7)
                for m in state.cognition.minds
            ),
        ))
    elif scenario == "public-construction":
        if population < 12:
            raise FoundationError("civic construction evaluation requires skilled core cohort")
        # No free building! Real player action escrow-funds it first.
        state, _ = step_product(state, ProductAction(
            "npc", "project", option="hearth", x=0, y=0,
        ))
    elif scenario == "civic-food-aid":
        if population < 4:
            raise FoundationError("civic majority demonstration requires four actual voters")
        people = tuple(replace(p, hunger=4, energy=0)
                       for p in state.society.inhabitants)
        state = replace(state, society=replace(state.society, inhabitants=people))
        state, _ = step_product(state, ProductAction(
            "npc", "propose", target=0, option="food-aid",
        ))
    elif scenario == "family-expansion":
        if population < 2 or population >= 32:
            raise FoundationError("generational scenario needs capacity for another body")
        # Earn physical shelter and mutual consent through four actual
        # transactions before advancing any world clocks.
        for command in (
            ProductAction("terrain", "build_hearth", x=0, y=0),
            ProductAction("npc", "council"),
            ProductAction("npc", "council"),
            ProductAction("npc", "household", target=0, option="1"),
        ):
            state, _ = step_product(state, command)
    validate_product(state)
    return state


def evaluate(
    scenario: str, *, turns: int = 24, population: int = 12,
    root: int = 0, architecture: str = "lattice",
) -> dict:
    if type(turns) is not int or not 1 <= turns <= 240:
        raise FoundationError("long-horizon laboratory supports 1..240 world turns")
    state = prepare(
        scenario, population=population, root=root,
        architecture=architecture,
    )
    initial = state
    receipts = []
    for _ in range(turns):
        state, receipt = step_product(state, ProductAction(
            "causal", "end_turn",
        ))
        receipts.append(receipt.receipt)
    validate_product(state)
    people = state.society.inhabitants
    minds = state.cognition.minds
    report = cognition_report(state.cognition, state.society, state.terrain)
    return {
        "schema": SCHEMA,
        "scenario": scenario,
        "architecture": architecture,
        "population_requested": population,
        "population_retained": len(people),
        "actual_world_ticks": state.living.living_turns,
        "citizen_decisions": sum(m.decisions for m in minds),
        "physical_world_actions": state.terrain.events,
        "all_citizens_physical": all(
            len((p.x, p.y)) == 2 for p in people
        ),
        "alive": sum(p.health > 0 for p in people),
        "incapacitated": sum(p.health == 0 for p in people),
        "hungry": sum(p.hunger >= 7 for p in people),
        "average_hunger_times_100": (
            100 * sum(p.hunger for p in people) // len(people)
        ),
        "mean_morale_times_100": (
            100 * sum(m.morale for m in minds) // len(minds)
        ),
        "total_experience": sum(p.experience for p in people),
        "materially_carried_stock": sum(p.cargo for p in people),
        "warehouse_stock": {
            kind: getattr(state.terrain, field) for kind, field in (
                ("food", "provisions"), ("wood", "lumber"),
                ("stone", "masonry"), ("water", "freshwater"),
            )
        },
        "resource_provenance": {
            "surviving_edited_physical_sites": len(state.terrain.edits),
            "constructed_physical_sites": sum(
                bool(site.building) for site in state.terrain.edits
            ),
        },
        "social_ties": report["social_relationships"],
        "real_public_mandate": state.cognition.civic.active_mandate,
        "recorded_civic_voters": sum(
            len(p.ballots) for p in state.cognition.civic.proposals
        ),
        "actually_funded_public_aid": len(state.cognition.civic.services),
        "earned_professional_graduations": state.cognition.training.completed,
        "physically_added_dependents": state.cognition.households.completed,
        "dependent_ages": list(state.cognition.households.ages[population:]),
        "verified_observations": report["verified_world_observations"],
        "socially_shared_observations": report["socially_learned_material_observations"],
        "sworn_public_testimonies": len(state.cognition.testimonies),
        "contracts_issued": len(state.cognition.orders),
        "contracts_physically_fulfilled": sum(
            o.status == "fulfilled" for o in state.cognition.orders
        ),
        "civic_projects": len(state.cognition.projects),
        "cooperatively_completed_projects": report["completed_constructed_projects"],
        "earned_policy_adjustments": sum(
            int(weight != 0) for mind in minds for weight in mind.learned
        ),
        "first_receipt": receipts[0],
        "last_receipt": receipts[-1],
        "final_product_event_head": state.event_head,
        "final_game_state_sha256": sha256(product_save(state).encode()).hexdigest(),
        "completed_native_games_claimed": 0,
        "quality_caveat": (
            "Deterministic reference-world observations, not a clinical, "
            "cognitive-human-equivalence, AAA playtest or benchmark of every "
            "possible world."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run real bounded NPC simulation scenarios and report measured state."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    parser.add_argument("--turns", type=int, default=24)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--base", type=int, default=0)
    parser.add_argument("--architecture", default="lattice")
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.scenario, turns=args.turns,
                          population=args.population, root=args.base,
                          architecture=args.architecture)
    except (FoundationError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
