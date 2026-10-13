"""Pre-render cinematic shot-board QC for chapter-authored game scenes.

Requires exactly mapped spoken lines and authored shot chronology, consistent
screen direction, immutable character voice/face and original regional design.
A source storyboard proof is NOT perceptual video or acoustic verification.
"""
from __future__ import annotations

from .story_canon_fabric import (
    StoryCanonError,array,colors,digest,ident,ids,number,require,shape,text)

CAMERAS = frozenset((
    "establishing","wide","medium","closeup","extreme_closeup",
    "tracking","over_shoulder","first_person","interactive","fixed"))
CUTS = frozenset(("straight","match_cut","cross_cut","dissolve",
                  "continuous","player_control","fade"))
AXES = frozenset(("axis_a","axis_b","neutral"))
MIN_SHOT_MS = 200
MAX_SHOT_MS = 180000
MAX_SCENE_MS = 20*60*1000


def verify_cinematic_shots(bible,contract,scene,shots):
    require(type(shots) is list and 1 <= len(shots) <= 128,
            "at least one chronological shot is required per original scene")
    identities=ids(contract["characters"],"approved actor identities")
    regional=ids(contract["regions"],"approved cinematic region")[scene["region"]]
    original_region=ids(bible["regions"],"approved authored regions")[scene["region"]]
    observed_dialogue=[]
    shot_ids=set()
    position=0
    previous_axis=None
    previous_shot=None
    for frame in shots:
        shape(frame,("id","start_ms","duration_ms","camera","cut","axis",
                     "focus_character","voice_id","face_id","dialogue_ids",
                     "style_id","palette","lighting","sound","director_note"),
              "ordered original cinematic shot")
        key=ident(frame["id"],"shot reference")
        require(key not in shot_ids,"shot identifier reused in one scene")
        shot_ids.add(key)
        number(frame["start_ms"],0,MAX_SCENE_MS,"shot start time")
        number(frame["duration_ms"],MIN_SHOT_MS,MAX_SHOT_MS,"shot duration")
        require(frame["start_ms"]==position,
                "shots must form one non-overlapping continuous timeline")
        position+=frame["duration_ms"]
        require(position<=MAX_SCENE_MS,
                "story scene would exceed reviewable cinematic duration")
        require(frame["camera"] in CAMERAS and frame["cut"] in CUTS and
                frame["axis"] in AXES,"unreviewed camera/cut/screen direction")
        if previous_axis is not None and frame["axis"] != previous_axis:
            require(previous_shot["camera"] == "establishing" and
                    not previous_shot["dialogue_ids"] and
                    frame["cut"] in ("straight","match_cut"),
                    "unmotivated 180-degree camera-axis flip")
        previous_shot=frame
        previous_axis=frame["axis"]
        who=frame["focus_character"]
        require(who in scene["cast"] and who in identities,
                "shot focuses an unapproved, absent character")
        identity=identities[who]
        require(frame["voice_id"]==identity["voice_id"] and
                frame["face_id"]==identity["face_id"],
                "shot swaps persistent speaking voice or facial identity")
        require(frame["style_id"]==regional["style_id"] and
                colors(frame["palette"],"shot palette")==
                    colors(regional["palette"],"canonical regional grade") and
                frame["lighting"]==original_region["lighting"],
                "cinematic shot violates period lighting, grade or regional style")
        require(type(frame["dialogue_ids"]) is list and
                len(frame["dialogue_ids"])<=32,
                "finite shot-specific spoken-line coverage required")
        for line in frame["dialogue_ids"]:
            original=next((d for d in scene["dialogue"] if d["id"]==line),None)
            require(original is not None and original["speaker"]==who,
                    "spoken shot line does not belong to the original face")
            observed_dialogue.append(line)
        for key in ("sound","director_note"):
            text(frame[key], "original director shot " + key, 600)
            require(len(frame[key].strip())>=10,
                    "shot requires meaningful audio and performance notes")
    require(observed_dialogue == [x["id"] for x in scene["dialogue"]],
            "every original line must be spoken once, in chronological shot order")
    body={
        "schema":"skeleton.game_builder.pre_render_cinematic_review.v1",
        "scene_source_digest":scene["digest"],"chapter":scene["chapter"],
        "act":scene["act"],"scene":scene["scene"],
        "shot_count":len(shots),"duration_ms":position,
        "spoken_lines_verified":len(observed_dialogue),
        "original_scene_style":regional["style_id"],
        "voice_faces_source_locked":True,
        "screen_direction_preflight_passed":True,
        "all_dialogue_once_in_order":True,
        "rendered_face_identity_verified":False,
        "generated_audio_speaker_verified":False,
        "movie_quality_render_certified":False,
    }
    return {**body,"digest":digest(body)}
