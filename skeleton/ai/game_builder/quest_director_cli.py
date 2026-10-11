"""Original game scene director CLI: create blueprints or build playable worlds."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .contracts import canonical_json
from .quest_scene_engine import ARCHETYPES, DirectorError
from .quest_scene_forge import forge_director, read_director_blueprint
from .quest_director_enhanced_product import build_earned_story_product
from .director_evolution_product import build_evolution_product
from .quest_director_export import export_director_studio


def parser():
    cli = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.quest_director_cli",
        description="Original scenes and cinematic multi-stage quests, with real alternative solutions.",
    )
    cli.add_argument("--mode", choices=("template", "build"), required=True)
    cli.add_argument("--output", required=True)
    cli.add_argument("--trusted-local-operator", action="store_true")
    cli.add_argument("--project", default="original_quest_director")
    cli.add_argument("--seed", type=int, default=20261011)
    cli.add_argument("--regions", type=int, default=16)
    cli.add_argument("--stages", type=int, default=3)
    cli.add_argument("--genres", default=(
        "main_story,escort_path,escort_leash,escort_introduction,"
        "courier,acquisition,rival_story,dungeoneering,infusion,"
        "timed_combat,survival_waves,attunement,profession,proficiency,"
        "investigation,regional_story"
    ))
    cli.add_argument("--goal", default="Rebuild an original world together without losing freedom.")
    cli.add_argument("--placement", choices=("seeded", "story", "regional", "player_choice"),
                     default="seeded")
    cli.add_argument("--blueprint", help="Custom full scene/quest JSON instead of generator")
    cli.add_argument("--human-reviewed", action="store_true",
                     help="Operator attests originality of all custom scene and quest content")
    cli.add_argument("--mirror-attempts", type=int, default=128)
    cli.add_argument("--evolve", action="store_true",
                     help="Build full modular NPC + mission + original scene director product")
    cli.add_argument("--npc-blueprint",
                     help="Fully authored original NPC profiles, schedules, relationships and backstories")
    cli.add_argument("--npc-human-reviewed", action="store_true",
                     help="Confirm separate review of all custom NPC authorship")
    cli.add_argument("--society-npcs", type=int, default=96,
                     help="Persistent individual citizens, 3..512")
    cli.add_argument("--target-tier",
                     choices=("retro","handheld","mobile","desktop","high_end"),
                     default="desktop")
    cli.add_argument("--no-deep-search", action="store_true",
                     help="Disable bounded alternative-route search in evolved source only")

    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: original director requires operator acknowledgement", file=sys.stderr)
        return 2
    if args.blueprint and not args.human_reviewed:
        print("error: original custom scenes require human review", file=sys.stderr)
        return 2
    try:
        if args.blueprint:
            world = read_director_blueprint(args.blueprint, human_reviewed=True)
        else:
            genres = tuple(part.strip() for part in args.genres.split(","))
            if any(genre not in ARCHETYPES for genre in genres):
                raise DirectorError("unrecognized game quest archetype")
            world = forge_director(
                args.project, seed=args.seed, regions=tuple(
                    f"region_{index:02d}" for index in range(args.regions)
                ),
                quest_types=genres, stages=args.stages,
                main_goal=args.goal, placement=args.placement,
            )
        output = Path(args.output)
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise DirectorError("output must be a new file/directory in an existing folder")
        if args.mode == "template":
            if output.suffix != ".json":
                raise DirectorError("original edit template must end in .json")
            payload = (canonical_json(world.payload()) + "\n").encode()
            if len(payload) > 1_200_000:
                raise DirectorError("custom scene editor JSON exceeds bounded size")
            with output.open("xb") as file:
                file.write(payload)
            print(canonical_json({
                "schema": "skeleton.game_builder.director_template_receipt.v1",
                "output": str(output), "world_digest": world.digest,
                "scene_count": len(world.scenes), "quest_count": len(world.quests),
                "custom_originality_review_needed_for_rebuild": True,
            }))
        else:
            product = (
                build_evolution_product(
                    world, authorized=True,
                    population=args.society_npcs, tier=args.target_tier,
                    npc_blueprint=args.npc_blueprint,
                    npc_human_reviewed=args.npc_human_reviewed,
                    deep_route_search=not args.no_deep_search,
                    mirror_attempts=args.mirror_attempts,
                ) if args.evolve else build_earned_story_product(
                    world, authorized=True, mirror_attempts=args.mirror_attempts,
                )
            )
            export_director_studio(product, output, authorized=True)
            print(canonical_json({
                "schema": "skeleton.game_builder.director_build_receipt.v1",
                "output": str(output), **product.receipt(),
                "authored_scene_count": len(world.scenes),
                "quest_count": len(world.quests),
                "stage_count": sum(len(q.stages) for q in world.quests),
                "cutscene_count": sum(len(s.cutscenes) for s in world.scenes),
            }))
        return 0
    except (DirectorError, OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["parser", "main"]
