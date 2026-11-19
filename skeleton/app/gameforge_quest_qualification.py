"""Seven-stage GameForge plan and actual source-level quest qualification."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import EvidenceError, array, fields, integer, text, identifier, seal, canonical, read_document
from skeleton.gameforge.conductor import ConductorConfig, GameForgeConductor
from skeleton.gameforge.manifest import verify_manifest
from skeleton.gameforge.plans import STEPS, VisionRequest
from skeleton.gameforge.errors import GameForgeError
from skeleton.ai.game_builder.synthesized_quest_runtime import qualify_campaign


def qualify_forge(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit local operator required")
    fields(order,{"schema","vision","config","quest"})
    if order["schema"]!="skeleton.gameforge-quest.order.v1":
        raise EvidenceError("unsupported order")
    vision=fields(order["vision"],{"title","pitch","genre","era","pillars","target_minutes"})
    req=VisionRequest(text(vision["title"],120),text(vision["pitch"],400),
                      identifier(vision["genre"]),identifier(vision["era"]),
                      tuple(text(x,100) for x in array(vision["pillars"],1,5)),
                      integer(vision["target_minutes"],1,600))
    config=fields(order["config"],{"budget_bytes","regions","target"})
    cfg=ConductorConfig(integer(config["budget_bytes"],1,8_000_000),
                        integer(config["regions"],1,64),identifier(config["target"]))
    quest=fields(order["quest"],{"seed","length","policy","mechanics","npcs"})
    result=GameForgeConductor(config=cfg).run(req)
    if not result.ok or result.manifest is None or tuple(result.completed)!=STEPS:
        raise EvidenceError("conductor rejected order")
    manifest=result.manifest.to_dict()
    verify_manifest(manifest,result.artifacts)
    rerun=GameForgeConductor(config=cfg).run(req)
    if not rerun.ok or rerun.manifest is None or rerun.manifest.to_dict()!=manifest or rerun.artifacts!=result.artifacts:
        raise EvidenceError("conductor replay differs")
    world=result.plans["world"]
    # WorldPlan validates its region links as undirected. Preserve that exact
    # connectivity convention, including isolated single-region worlds.
    edges={region.key:set(region.neighbors) for region in world.regions}
    for region in world.regions:
        for neighbor in region.neighbors:
            edges[neighbor].add(region.key)
    campaign={"schema":"skeleton.synthesized-quest.order.v1",
              "campaign_id":result.plans["vision"].game_id,"title":req.title,
              "seed":quest["seed"],"length":quest["length"],
              "world":{"start":world.start,"edges":{k:sorted(v) for k,v in edges.items()},
                       "npcs":quest["npcs"]},"policy":quest["policy"],"mechanics":quest["mechanics"]}
    executed=qualify_campaign(campaign,authorized=True)
    return seal({"schema":"skeleton.gameforge-quest.qualification.v1","manifest":manifest,
                 "world_plan":world.to_dict(),"campaign_order":campaign,
                 "conductor_replayed":True,"quest_campaign":executed,
                 "declarative_artifacts_only":True,"native_engine_executed":False,
                 "release_certified":False})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit local operator required")
        order,_=read_document(args.order)
        print(canonical(qualify_forge(order,authorized=True)).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,GameForgeError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
