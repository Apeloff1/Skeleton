"""Dependency-ordered producer workload using *real* source sections and jobs."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .studio_ecosystem_quest import compile_quest_program, StudioQuestError
from .studio_ecosystem_assets import planned_assets
from .studio_ecosystem_audio import compile_cue_sheet
from .studio_ecosystem_rights import release_requirements


def build_work_graph(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    art=planned_assets(documents)["jobs"]
    cues=compile_cue_sheet(documents)["cues"]
    assurance=release_requirements(documents)
    tasks=[
        {"id":"source-canon","depends_on":[],"kind":"canon_review"},
        {"id":"quest-integration","depends_on":["source-canon"],"kind":"quest_engine"},
        {"id":"scene-integration","depends_on":["quest-integration"],"kind":"scene_engine"},
    ]
    for item in art:
        tasks.append({"id":"asset:"+item["asset_id"],"depends_on":["scene-integration"],
                      "kind":"original_asset_production","recipe_sha256":item["recipe_sha256"]})
    for cue in cues:
        tasks.append({"id":"audio:"+cue["cue_id"],"depends_on":["scene-integration"],
                      "kind":"original_audio_production"})
    leaves=[item["id"] for item in tasks if item["id"].startswith(("asset:","audio:"))]
    tasks.extend([
        {"id":"integration-playtest","depends_on":leaves,
         "kind":"actual_prototype_integration"},
        {"id":"rights-review","depends_on":leaves,"kind":"authorship_and_license_review"},
        {"id":"release-qualification","depends_on":["integration-playtest","rights-review"],
         "kind":"device_security_ci_qualification"},
    ])
    ids=set()
    for task in tasks:
        if task["id"] in ids or not set(task["depends_on"]).issubset(ids):
            raise StudioQuestError("duplicate or unsorted work dependency")
        ids.add(task["id"])
    payload={"project":program.project_id,"source":program.source_digest,"tasks":tasks}
    digest=sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()
    return {"schema":"skeleton.game_builder.studio_work_graph.v1",
            "project_id":program.project_id,"source_digest":program.source_digest,
            "work_graph_sha256":digest,"tasks":tasks,
            "unresolved_release_blockers":assurance["unresolved_release_blockers"],
            "work_done":False,"release_certified":False}


def ready_work(graph: Mapping[str, Any], completed: Sequence[str], *,
               authorized: bool) -> dict[str, object]:
    """What would be schedulable in a *simulation*; no proof of completion."""
    if not authorized:
        raise PermissionError("producer work dispatch requires operator authorization")
    tasks=graph.get("tasks")
    if not isinstance(tasks,list):
        raise StudioQuestError("invalid work graph")
    ids=[item["id"] for item in tasks]
    if not isinstance(completed,(list,tuple)) or (
        len(completed)!=len(set(completed)) or
        any(not isinstance(x,str) or x not in ids for x in completed)
    ):
        raise StudioQuestError("unknown or duplicate simulation completion")
    done=set(completed)
    if any(not set(t["depends_on"]).issubset(done)
           for t in tasks if t["id"] in done):
        raise StudioQuestError("completed work lacks prerequisite")
    ready=[t["id"] for t in tasks if t["id"] not in done
           and set(t["depends_on"]).issubset(done)]
    return {"project_id":graph.get("project_id"),"simulated_completed":len(done),
            "ready_for_operator_review":ready,
            "completion_evidence_verified":False,
            "release_certified":False}
