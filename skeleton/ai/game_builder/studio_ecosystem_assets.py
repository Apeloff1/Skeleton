"""Source-owned, ordered asset production jobs for the original game studio."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import compile_quest_program, StudioQuestError


def planned_assets(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    visual=documents.get("visual")
    if (not isinstance(visual,dict) or visual.get("project_id")!=program.project_id
            or visual.get("release_certified") is not False):
        raise StudioQuestError("invalid original art source")
    recipes=visual.get("asset_recipes", visual.get("jobs"))
    if not isinstance(recipes,list) or not recipes:
        raise StudioQuestError("no authored production recipes")
    jobs=[]
    seen=set()
    for recipe in recipes:
        if not isinstance(recipe,dict):
            raise StudioQuestError("invalid asset recipe")
        ident=recipe.get("id")
        kind=recipe.get("type")
        if (not isinstance(ident,str) or not ident or ident in seen
                or not isinstance(kind,str) or not kind):
            raise StudioQuestError("duplicate or invalid original asset identity")
        if recipe.get("status","not_created")!="not_created" or (
            "production" in recipe and recipe["production"]!="design_only"
        ):
            raise StudioQuestError("unverified asset completion claim")
        seen.add(ident)
        parts=recipe.get("deliverables",[])
        if not isinstance(parts,list) or any(not isinstance(p,str) for p in parts):
            raise StudioQuestError("invalid asset deliverable plan")
        digest=sha256(json.dumps(recipe,sort_keys=True,separators=(",",":"),
                                 ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()
        jobs.append({"asset_id":ident,"asset_type":kind,"recipe_sha256":digest,
                     "required_outputs":parts,"asset_delivered":False})
    return {"schema":"skeleton.game_builder.studio_art_jobs.v1",
            "project_id":program.project_id,
            "source_digest":program.source_digest,
            "jobs":jobs,"assets_created":0,"rights_qualified":False,
            "release_certified":False}
