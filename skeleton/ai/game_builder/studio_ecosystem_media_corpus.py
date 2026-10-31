"""Stream full registered original studio source renderability audit.

Every project gets real schema checks. No media or release claim is silently
fabricated; only the source's declared renderability is examined here.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .studio_ecosystem_catalog import catalog_index,read_blueprint,StudioEcosystemError
from .studio_ecosystem_vector_art import render_environment_svg
from .studio_ecosystem_synth_audio import _tempo
from .studio_ecosystem_audio import compile_cue_sheet
from .studio_ecosystem_assets import planned_assets
from .studio_ecosystem_quest import compile_quest_program,StudioQuestError


def audit_original_studio_media_sources(*, max_error_details: int = 64) -> dict[str, object]:
    if type(max_error_details) is not int or not 1<=max_error_details<=512:
        raise StudioEcosystemError("invalid bounded source audit detail")
    index=catalog_index()
    hash_chain=sha256(b"skeleton.game_builder.studio_media_source_corpus.v1\n")
    valid=0
    invalid=0
    details=[]
    for record in index:
        pid=record["id"]
        problems=[]
        try:
            docs=read_blueprint(pid)
            program=compile_quest_program(docs)
            art=planned_assets(docs)
            sheet=compile_cue_sheet(docs)
            tempo=_tempo(docs)
            svg=render_environment_svg(docs)
            if (not art["jobs"] or not sheet["cues"] or
                    not svg.startswith(b"<?xml") or not 35<=tempo<=240):
                problems.append("renderability_contract_incomplete")
            digest=program.source_digest
        except (StudioEcosystemError,StudioQuestError,ValueError,TypeError,
                OSError,UnicodeError) as exc:
            problems.append(type(exc).__name__)
            digest=""
        succeeded=not problems
        valid+=int(succeeded)
        invalid+=int(not succeeded)
        if problems and len(details)<max_error_details:
            details.append({"project_id":pid,"errors":problems})
        line={"project_id":pid,"quest_sha256":digest,"renderable":succeeded}
        hash_chain.update(json.dumps(line,sort_keys=True,separators=(",",":"),
                                     ensure_ascii=True).encode("ascii")+b"\n")
    return {"schema":"skeleton.game_builder.studio_media_source_corpus.v1",
            "indexed_projects":len(index),"renderable_source_projects":valid,
            "rejected_source_projects":invalid,
            "source_chain_sha256":hash_chain.hexdigest(),
            "errors":details,"errors_truncated":invalid>len(details),
            "all_source_schemas_renderable":invalid==0,
            "actual_media_rendered_for_all":False,
            "native_gameplay_verified":False,
            "rights_verified":False,"release_certified":False}
