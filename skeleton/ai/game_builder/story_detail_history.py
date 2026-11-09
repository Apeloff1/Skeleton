"""Verifiable historical scene-by-scene character, wardrobe, voice and item lookup.

The entire accepted 1..N story is independently replayed before any historical
page is emitted. Paged results are source-linked, not guessed conversation memory.
"""
from __future__ import annotations

from .story_canon_fabric import StoryCanonError, digest, ident, number, require
from .story_continuity_assurance import verify_production_history
from .story_workspace import load_continuity_contract, load_story_workspace


def _sources(workspace, project):
    bible, scenes, _ = load_story_workspace(workspace,project)
    require(bible is not None, "reviewed story bible needed")
    contract = load_continuity_contract(workspace,project)
    require(contract is not None, "no locked voice/wardrobe/facial history exists yet")
    confirmation = verify_production_history(bible,contract,scenes)
    return bible,contract,scenes,confirmation


def detail_timeline(workspace,project, *,character=None,item=None,
                    region=None,offset=0,limit=48):
    """Reconstruct exact immutable visual/voice facts and historical changes."""
    require(sum(x is not None for x in (character,item,region)) == 1,
            "request precisely one indexed story detail identity")
    number(offset,0,9999,"history offset")
    number(limit,1,96,"history page size")
    bible,contract,scenes,history = _sources(workspace,project)
    if character is not None:
        ident(character,"historical cast member")
        subject = next((x for x in contract["characters"]
                        if x["id"] == character),None)
        require(subject is not None,"requested character was never in approved cast")
        rows=[]
        for scene in scenes:
            observations=scene["assurance"]["observations"]
            actor=next((x for x in observations["cast"]
                        if x["character"]==character),None)
            if actor is None:
                continue
            relevant=[line for line in scene["dialogue"]
                      if line["speaker"]==character or line["listener"]==character]
            history_events=[e for e in scene["events"]
                            if e["actor"]==character or
                            any(c["character"]==character for c in e["changes"])]
            rows.append({
                "sequence":scene["sequence"],"act":scene["act"],
                "scene":scene["scene"],"source_digest":scene["digest"],
                "confirmation_digest":scene["assurance"]["digest"],
                "face_id":actor["face_id"],
                "facial_geometry_digest":actor["facial_geometry_digest"],
                "outfit_id":actor["outfit_id"],
                "outfit_palette":actor["outfit_palette"],
                "voice_id":actor["voice_id"],
                "voice_source_sha256":actor["voice_asset_sha256"],
                "dialogue_expressions":actor["dialogue_expressions"],
                "dialogue_backlinks":[d["id"] for d in relevant],
                "event_backlinks":[e["id"] for e in history_events],
            })
        profile={
            "voice_id":subject["voice_id"],
            "voice_source_sha256":subject["voice_asset_sha256"],
            "face_id":subject["face_id"],
            "face_structure":subject["facial_geometry"],
            "approved_wardrobe":subject["wardrobe"],
            "approved_expression_intents":subject["expressions"],
        }
        which="character"
        key=character
    elif item is not None:
        ident(item,"historical item")
        subject = next((x for x in contract["items"] if x["id"]==item),None)
        require(subject is not None,"item has no original scene-one identity")
        profile=subject
        owner=subject["initial_owner"]
        rows=[]
        for scene in scenes:
            evidence=scene["assurance"]["observations"]
            changes=[r for r in evidence["transfers"] if r["item"]==item]
            for change in changes:
                require(change["from_owner"]==owner,
                        "historical item ownership discontinuity")
                owner=change["to_owner"]
            appearance=next((row for row in evidence["items"]
                             if row["id"]==item),None)
            if changes or appearance:
                rows.append({
                    "sequence":scene["sequence"],"act":scene["act"],
                    "scene":scene["scene"],"source_digest":scene["digest"],
                    "confirmation_digest":scene["assurance"]["digest"],
                    "owner":owner, "transfer_events":
                        [x["event_ref"] for x in changes],
                    "appearance":appearance,
                })
        which="item";key=item
    else:
        ident(region,"historical region")
        subject=next((x for x in contract["regions"] if x["id"]==region),None)
        require(subject is not None,"unknown authored region")
        profile=subject
        rows=[]
        for scene in scenes:
            if scene["region"]!=region:continue
            rows.append({
                "sequence":scene["sequence"],"act":scene["act"],
                "scene":scene["scene"],"source_digest":scene["digest"],
                "confirmation_digest":scene["assurance"]["digest"],
                "style":scene["assurance"]["observations"]["region"],
                "assets":[x["asset"] for x in scene["assets"]],
            })
        which="region";key=region
    page=rows[offset:offset+limit]
    output={
        "schema":"skeleton.game_builder.jeeves_detail_history_page.v1",
        "subject_type":which, "subject_id":key,"project":project,
        "source_contract_digest":contract["digest"],
        "historical_reparse_digest":history["digest"],
        "source_head":history["verified_source_head"],
        "receipt_head":history["verified_receipt_head"],
        "immutable_source_profile":profile,
        "total_scene_occurrences":len(rows),
        "offset":offset,"limit":limit,
        "next_offset":offset+len(page) if offset+len(page)<len(rows) else None,
        "occurrences":page,
        "bookmarks_are_source_proved":True,
        "actual_audio_verified":False,"actual_rendered_face_verified":False,
    }
    return {**output,"digest":digest(output)}
