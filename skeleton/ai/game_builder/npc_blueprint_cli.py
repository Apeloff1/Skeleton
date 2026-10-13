"""Generate editable citizen psychology, schedules and kinship JSON blueprints."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys

from .contracts import canonical_json
from .quest_scene_forge import read_director_blueprint
from .quest_scene_engine import DirectorError
from .npc_authoring import CitizenAuthoringError, npc_template, MAX_BYTES


def main(argv=None):
    parser=argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.npc_blueprint_cli",
        description="Export original NPC biographies, professions, traits and full routines.",
    )
    parser.add_argument("--director-blueprint",required=True,
                        help="Local human-reviewed scene/mission source JSON")
    parser.add_argument("--output",required=True)
    parser.add_argument("--population",type=int,default=96)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    if not args.trusted_local_operator:
        print("error: authoring requires trusted local operator",file=sys.stderr)
        return 2
    try:
        world=read_director_blueprint(args.director_blueprint,human_reviewed=True)
        doc=npc_template(world,args.population,authorized=True)
        data=(canonical_json(doc)+"\n").encode("utf-8")
        if len(data)>MAX_BYTES:
            raise CitizenAuthoringError("roster requires a smaller population/metadata budget")
        destination=Path(args.output)
        if (destination.suffix.lower()!=".json" or destination.exists()
            or destination.is_symlink() or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
            raise CitizenAuthoringError("new original local JSON output required")
        with destination.open("xb") as file:
            file.write(data)
        print(canonical_json({
            "schema":"skeleton.game_builder.original_npc_template_receipt.v1",
            "output":str(destination),"source_sha256":sha256(data).hexdigest(),
            "world_digest":world.digest,
            "population":len(doc["profiles"]),
            "author_review_required_before_product_build":True,
            "no_external_assets_or_model_weights":True,
        }))
        return 0
    except (DirectorError,CitizenAuthoringError,OSError,ValueError) as exc:
        print("error: "+type(exc).__name__+": "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

__all__=["main"]
