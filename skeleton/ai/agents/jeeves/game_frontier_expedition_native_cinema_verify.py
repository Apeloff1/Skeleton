"""Independently verify real Godot 4 cinematic camera frame observations.

A synthetically described camera trace proves only source compatibility. A
native-process execution gate must independently verify binary/process origin.
Every sampled frame has its own expected canonical interpolation and is bound
to a specific world/storyboard, preventing a success-string-only cinematic.
"""
from __future__ import annotations
import json
from math import isclose
from typing import Mapping

from .game_frontier_expedition import ExpeditionError, _digest
from .game_frontier_expedition_cinematics import Storyboard, camera_at

PREFIX="EXPEDITION_CINEMATIC_FRAME "
SAMPLES=(0,17,35,54,71)


def verify_native_cinema_frames(
    stdout:str,storyboard:Storyboard, *,
    clip_id:str="scene_001",
)->dict:
    if type(stdout) is not str or len(stdout)>8_000_000:
        raise ExpeditionError("native cinematic output exceeds evidence budget")
    if not isinstance(storyboard,Storyboard):
        raise ExpeditionError("cinematic review needs original storyboard")
    clip=next((x for x in storyboard.clips if x.clip_id==clip_id),None)
    if clip is None:
        raise ExpeditionError("cinematic review references foreign clip")
    sample_frames=tuple(n for n in SAMPLES if n<clip.frames)
    frames=[]
    for line in stdout.splitlines():
        if not line.startswith(PREFIX):
            continue
        if len(line)>1024 or len(frames)>=len(sample_frames):
            raise ExpeditionError("native cinema observations duplicated or oversized")
        try:
            row=json.loads(line[len(PREFIX):],parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        except (ValueError,TypeError) as exc:
            raise ExpeditionError("native cinematic JSON observation malformed") from exc
        if (type(row) is not dict
                or set(row)!={"world_digest","clip_id","frame","x","y","z","fov"}
                or row["world_digest"]!=storyboard.world_digest
                or row["clip_id"]!=clip_id
                or type(row["frame"]) is not int
                or row["frame"]!=sample_frames[len(frames)]):
            raise ExpeditionError("native camera sample is out-of-order or foreign")
        canonical=camera_at(clip,row["frame"])
        for name in ("x","y","z","fov"):
            value=row[name]
            if (type(value) not in (float,int)
                    or not isclose(value,getattr(canonical,name),
                                   rel_tol=0,abs_tol=0.003)):
                raise ExpeditionError("native cinematic camera differs from original keyframes")
        frames.append({
            "frame":row["frame"],
            "position":{name:row[name] for name in ("x","y","z")},
            "fov":row["fov"],
            "source_digest":_digest(row),
        })
    if len(frames)!=len(sample_frames):
        raise ExpeditionError("native cinematic missed canonical frame samples")
    if ("EXPEDITION_CINEMATIC_AUDIT_VERIFIED "+clip_id not in stdout
            or "EXPEDITION_CINEMATIC_COMPLETE "+clip_id not in stdout):
        raise ExpeditionError("native cinematic did not report complete playback")
    evidence={
        "schema":"skeleton.game.native_camera_sample_verification.v1",
        "storyboard_digest":storyboard.digest,
        "world_digest":storyboard.world_digest,
        "clip_id":clip_id,
        "frames":frames,"observations":len(frames),
        "source_frame_replay_verified":True,
        "native_process_origin_independently_signed":False,
    }
    evidence["receipt_digest"]=_digest(evidence)
    return evidence
