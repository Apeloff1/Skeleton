"""Original authored cue routing; auditable metadata, no generated audio."""
from __future__ import annotations
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program


def compile_cue_sheet(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    audio=documents.get("audio")
    if (not isinstance(audio,dict) or audio.get("project_id")!=program.project_id
            or audio.get("release_certified") is not False):
        raise StudioQuestError("missing or falsely certified audio source")
    sources=[key for key in ("sound_layers","cue_sheet") if key in audio]
    if len(sources)!=1 or not isinstance(audio[sources[0]],list) or not audio[sources[0]]:
        raise StudioQuestError("missing unambiguous authored cue sheet")
    cues=[]
    seen=set()
    for cue in audio[sources[0]]:
        if not isinstance(cue,dict):
            raise StudioQuestError("invalid cue")
        name=cue.get("cue",cue.get("id"))
        trigger=cue.get("trigger")
        if (not isinstance(name,str) or not name or name in seen
                or not isinstance(trigger,str) or not trigger):
            raise StudioQuestError("invalid cue identity or trigger")
        seen.add(name)
        cues.append({"cue_id":name,"trigger":trigger,
                     "authored_source":cue.get("source"),
                     "audio_waveform_produced":False})
    return {"schema":"skeleton.game_builder.studio_audio_sheet.v1",
            "project_id":program.project_id,"source_digest":program.source_digest,
            "cues":cues,"audio_recorded":False,"release_certified":False}


def cues_for_event(documents: Mapping[str, Any], *, event: str,
                   authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("audio cue inspection requires operator authorization")
    if not isinstance(event,str) or not event:
        raise StudioQuestError("invalid event")
    sheet=compile_cue_sheet(documents)
    return {"project_id":sheet["project_id"],"event":event,
            "matched_cues":[c["cue_id"] for c in sheet["cues"]
                            if c["trigger"]==event],
            "audio_actually_played":False,"release_certified":False}
