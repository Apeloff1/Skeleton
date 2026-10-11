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
from .original_world_million_compiler import (
    advanced_at, advanced_from_seed, advanced_inventory, mode_at,
)
from .original_world_tenfold_compiler import (
    tenfold_at, tenfold_from_seed, tenfold_inventory, spatial_at,
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
    selector.add_argument("--mode-index", type=int,
                          help="Exact 100k gameplay-form foundation index [0,102399]")
    selector.add_argument("--advanced-index", type=int,
                          help="Exact million-world game configuration [0,1228799]")
    selector.add_argument("--advanced-seed",
                          help="Deterministic gameplay and progression configuration")
    selector.add_argument("--spatial-index", type=int,
                          help="One of 1,024,000 mechanical world-space foundations")
    selector.add_argument("--tenfold-index", type=int,
                          help="One of 12,288,000 world-space/genre/arc configurations")
    selector.add_argument("--tenfold-seed",
                          help="Deterministically sample actual spatial world rules")
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
        if args.spatial_index is not None:
            space = spatial_at(args.spatial_index)
            print(json.dumps({
                "catalog": "world-space-genre-foundations",
                "foundation": space.as_dict(),
                "inventory": tenfold_inventory(),
                "styling_request_only": styling.as_dict(),
                "warning": "A verified bounded spatial adapter exists, not a finished "
                           "native game, bespoke art or independently hand-written premise.",
            }, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
        if args.tenfold_index is not None or args.tenfold_seed is not None:
            law = (tenfold_at(args.tenfold_index)
                   if args.tenfold_index is not None
                   else tenfold_from_seed(args.tenfold_seed))
            print(json.dumps({
                "catalog": "tenfold-spatial-game-configurations",
                "configuration": law.as_dict() if not args.brief else {
                    "index": str(law.index),
                    "world_id": law.tenfold_id,
                    "design_id": law.design_id,
                    "architecture": law.spatial.architecture.architecture_id,
                    "form": law.advanced.mode.form.form_id,
                    "arc": law.advanced.arc.arc_id,
                    "provenance": law.provenance,
                },
                "inventory": tenfold_inventory(),
                "styling_request_only": styling.as_dict(),
                "play_command": "python -m skeleton.game.generation.original_world_tenfold_cli --index "
                                + str(law.index) + " --interactive",
                "warning": "A twelve-million-index compositional atlas is not "
                           "twelve million individually authored native games.",
            }, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
        if args.mode_index is not None:
            selected = mode_at(args.mode_index)
            print(json.dumps({
                "catalog": "mechanically-mode-bound-world-foundations",
                "mode": selected.as_dict(),
                "count": advanced_inventory()["mechanically_mode_bound_foundation_entries"],
                "styling_request_only": styling.as_dict(),
                "warning": "Gameplay form has a generic executing adapter. "
                           "Visual/hardware settings are design targets, not native builds.",
            }, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
        if args.advanced_index is not None or args.advanced_seed is not None:
            law = (advanced_at(args.advanced_index) if args.advanced_index is not None
                   else advanced_from_seed(args.advanced_seed))
            print(json.dumps({
                "catalog": "million-composed-causal-worlds",
                "advanced_world": law.as_dict() if not args.brief else {
                    "id": law.advanced_id,
                    "index": str(law.index),
                    "design_id": law.design_id,
                    "base_id": law.mode.base.foundation_id,
                    "play_form": law.mode.form.form_id,
                    "progression": law.arc.arc_id,
                    "provenance": law.provenance,
                    "simulation_status": law.simulation_status,
                },
                "inventory": advanced_inventory(),
                "styling_request_only": styling.as_dict(),
                "play_command": "python -m skeleton.game.generation.original_world_million_cli --index "
                                + str(law.index) + " --interactive",
                "warning": "The advanced catalog is lazy and composed, not 1.2m "
                           "individually authored or native playable games. "
                           "Styles are not implemented renderer artifacts.",
            }, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
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
