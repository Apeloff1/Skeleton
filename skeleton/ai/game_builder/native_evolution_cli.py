"""End-to-end ORIGINAL multi-era game evolution into genuine native source projects.

Example:
  python -m skeleton.ai.game_builder.native_evolution_cli \
      --basis commodore_vic20 --destination commodore_64 \
      --project-id moon-trails --title 'Moon Trails' --seed 1982 \
      --rights-evidence ./my-authorship.txt \
      --identity 'original maze rules' --identity 'own hand-made style' \
      --out ./evolution-games --authorize-original-homebrew

A hardware lineage is a *teaching chronology*, not proof of binary
compatibility. Compiled binaries, emulated runs and distribution rights
remain independent gates. No ROMs, BIOS, SDKs or firmware are downloaded.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .evolution_archive import plan_evolution_campaign
from .evolution_practice import practice_evolution_games
from .evolution_native_sources import compile_evolution_native_sources, export_evolution_native_sources
from .playable_world import GameBuildIntent, generate_playable_world
from .port_planner import HomebrewSource
from .platform_registry import default_registry

_MAX_RIGHTS_BYTES = 8 * 1024 * 1024


def build_native_evolution(
    *, basis: str, destination: str, project_id: str,
    title: str, seed: int, rights_evidence: str | Path,
    creative_identity: tuple[str, ...],
    output: str | Path, authorized: bool,
    width: int = 17, height: int = 15, levels: int = 3,
    collectibles: int = 3, hazards: int = 4,
    health: int = 4, reverse: bool = False,
) -> dict[str, Any]:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native evolution requires original-homebrew authorization")
    if type(reverse) is not bool:
        raise ValueError("reverse must be boolean")
    registry = default_registry()
    if basis not in registry.profiles or destination not in registry.profiles:
        raise ValueError("both historical systems must belong to validated catalogue")
    evidence_path = Path(rights_evidence)
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise ValueError("authorship evidence must be a local ordinary file")
    if not 0 < evidence_path.stat().st_size <= _MAX_RIGHTS_BYTES:
        raise ValueError("authorship evidence missing or too large")
    hasher = sha256()
    with evidence_path.open("rb") as stream:
        while blob := stream.read(1024 * 1024):
            hasher.update(blob)
    source = HomebrewSource(
        project_id=project_id, platform_id=basis,
        rights_basis="project_owned", evidence_sha256=hasher.hexdigest(),
        creative_identity=creative_identity,
    )
    world = generate_playable_world(GameBuildIntent(
        project_id=project_id, title=title,
        subtitle="Original machine-history game evolution",
        seed=seed, width=width, height=height,
        levels=levels, collectibles_per_level=collectibles,
        hazards_per_level=hazards, starting_health=health,
    ), authorized=True)
    campaign = plan_evolution_campaign(source, destination, reverse=reverse)
    practice = practice_evolution_games(world, campaign, authorized=True)
    native = compile_evolution_native_sources(practice, source, authorized=True)
    folder = export_evolution_native_sources(native, output, authorized=True)
    result = native.summary()
    if result["total_stages"] != len(campaign.stages):
        raise RuntimeError("evolution source stages lost the historical campaign")
    return {
        "schema": "skeleton.game_builder.native_evolution_authoring_receipt.v1",
        "original_project_id": project_id,
        "original_world_digest": world.digest,
        "source_platform": basis,
        "destination_platform": destination,
        "backward_evolution": reverse,
        "campaign_stage_count": len(campaign.stages),
        "native_source_stages": result["native_source_stages"],
        "design_only_stages": result["design_only_stages"],
        "budget_incompatible_stages": result["budget_incompatible_stages"],
        "stage_dispositions": result["stages"],
        "output_directory": str(folder),
        "campaign_source_digest": native.digest,
        "rights_evidence_sha256": source.evidence_sha256,
        "rights_independently_verified": False,
        "binary_built": False,
        "native_gameplay_executed": False,
        "licensed_distribution": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basis", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--width", type=int, default=17)
    parser.add_argument("--height", type=int, default=15)
    parser.add_argument("--levels", type=int, default=3)
    parser.add_argument("--collectibles", type=int, default=3)
    parser.add_argument("--hazards", type=int, default=4)
    parser.add_argument("--health", type=int, default=4)
    parser.add_argument("--rights-evidence", type=Path, required=True)
    parser.add_argument("--identity", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--authorize-original-homebrew", action="store_true")
    options = parser.parse_args()
    result = build_native_evolution(
        basis=options.basis, destination=options.destination,
        project_id=options.project_id, title=options.title,
        seed=options.seed, width=options.width, height=options.height,
        levels=options.levels, collectibles=options.collectibles,
        hazards=options.hazards, health=options.health,
        rights_evidence=options.rights_evidence,
        creative_identity=tuple(options.identity), output=options.out,
        reverse=options.reverse,
        authorized=options.authorize_original_homebrew,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
