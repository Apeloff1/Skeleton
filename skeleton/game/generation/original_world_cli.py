"""Local, offline CLI for exploring original world laws and presentation options.

No AI provider, crawler, proprietary platform SDK or online network is used.
Output is a deterministic design manifest; --demo-rules runs only the eight
specifically compiled sample rule operators, not the entire chosen world.
"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from .original_world_compiler import TOTAL_VARIANTS, blueprint_at, blueprint_from_seed
from .original_foundation_compiler import (
    foundation_at, foundation_from_seed, provenance_report,
)
from .original_world_simulator import (
    WorldRuleAction, replay_rules, route_edges,
)
from .world_experience_manifest import project_experience
from .world_styling import WorldStyling


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview original authored world designs, not finished games."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--index", type=int, help="Exact zero-based recipe index")
    selector.add_argument("--seed", help="Reproducible design seed")
    selector.add_argument("--foundation-index", type=int,
                          help="Exact authorial cross-law foundation index [0,10239]")
    selector.add_argument("--foundation-seed",
                          help="Deterministically choose a causal foundation")
    parser.add_argument("--era", default="near-future")
    parser.add_argument("--chronology", default="fictional-history")
    parser.add_argument("--theology", default="none")
    parser.add_argument("--theme", action="append", dest="themes")
    parser.add_argument("--visual-style", default="stylized-pbr")
    parser.add_argument("--tone", default="adventurous")
    parser.add_argument("--simulation-realism", default="systemic-lite")
    parser.add_argument("--comfort", type=int, default=50)
    parser.add_argument("--realism", type=int, default=50)
    parser.add_argument("--hardware-target", default="pc-windows")
    parser.add_argument("--brief", action="store_true",
                        help="Compact design identity and readiness summary")
    parser.add_argument("--demo-rules", action="store_true",
                        help="Run a separate deterministic proof-of-execution scenario")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        styling = WorldStyling(
            era=args.era, chronology=args.chronology,
            theology=args.theology,
            themes=tuple(args.themes or ("exploration",)),
            visual_style=args.visual_style,
            tone=args.tone,
            simulation_realism=args.simulation_realism,
            comfort=args.comfort,
            realism=args.realism,
            hardware_target=args.hardware_target,
        )
        if args.foundation_index is not None or args.foundation_seed is not None:
            law = (foundation_at(args.foundation_index)
                   if args.foundation_index is not None
                   else foundation_from_seed(args.foundation_seed))
            result = {
                "catalog": "causal-composed-foundations",
                "foundation": law.as_dict() if not args.brief else {
                    "foundation_id": law.foundation_id,
                    "index": str(law.foundation_index),
                    "title": law.title, "root_id": law.root.root_id,
                    "regime_id": law.regime.regime_id,
                    "coupling": law.coupling,
                    "provenance": law.provenance,
                },
                "styling": styling.as_dict(),
                "inventory": provenance_report(),
                "realization_status": "bounded-generic-causal-prototype",
                "play_command": "python -m skeleton.game.generation.original_foundation_cli --index "
                                + str(law.foundation_index) + " --interactive",
                "warning": "Causal composition is not individually handwritten, "
                           "nor does a stylistic choice create a native playable build.",
            }
            if args.demo_rules:
                result["warning"] += (
                    " The legacy eight-rule demonstration is separate "
                    "from this causal composition."
                )
            print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
        blueprint = (
            blueprint_at(args.index) if args.index is not None
            else blueprint_from_seed(args.seed or "atlas-preview")
        )
        exp = project_experience(blueprint, styling)
    except (ValueError, TypeError) as exc:
        _parser().error(str(exc))

    if args.brief:
        payload = {
            "world": exp.blueprint.world.__dict__,
            "recipe_id": exp.blueprint.recipe_id,
            "experience_id": exp.experience_id,
            "recipe_index": str(exp.blueprint.variant_index),
            "recipe_capacity": str(TOTAL_VARIANTS),
            "mechanic_ids": [m.mechanic_id for m in exp.blueprint.mechanics],
            "unresolved_levers": exp.blueprint.unresolved_lever_count,
            "bridge_hypotheses": len(exp.blueprint.bridges),
            "styling": exp.styling.as_dict(),
            "continuity_contract": exp.continuity_contract,
            "compatibility_findings": list(exp.compatibility_findings),
            "realization_status": exp.realization_status,
        }
    else:
        payload = exp.as_dict()
        payload["recipe_capacity"] = str(TOTAL_VARIANTS)
    if args.demo_rules:
        # Separate from the design; this sample is not a synthesized world.
        actions = (
            WorldRuleAction("time-m01", amount=2),
            WorldRuleAction("topology-m02", mode="unobserved"),
            WorldRuleAction("ecology-m02", mode="west-to-east"),
            WorldRuleAction("world.tick"),
            WorldRuleAction("world.tick"),
            WorldRuleAction("survival-m01", amount=2),
            WorldRuleAction("serenity-m01", amount=1),
        )
        state, receipts = replay_rules(actions)
        payload["abstract_rule_demo"] = {
            "status": "simulated-abstract",
            "room_edges": [list(edge) for edge in route_edges(state)],
            "rainfall": list(state.rainfall),
            "food": state.food,
            "energy": state.energy,
            "event_head": state.event_head,
            "events": [r.event_digest for r in receipts],
            "note": "Only eight explicitly supported rule IDs are executable; "
                    "the selected recipe is not compiled to a complete game.",
        }
    print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
