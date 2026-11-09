"""Rights-cleared, independently replayed multi-factor Jeeves neural corpus.

This feeds *training-only text* to the existing production-checkpoint-
derived candidate optimizer through load_studio_curriculum. A label is
only a state/action/reward measurement reproduced by the canonical
original-game runtime. Never use heldout evaluation seeds as examples.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .jeeves_studio_curriculum import (
    StudioCurriculumError, MAX_EXAMPLES, _canonical,
    build_studio_curriculum, verify_studio_curriculum,
)
from skeleton.jeeves.game_studio_multifactor import (
    plan_multifactor_scenarios,
)

SCHEMA="skeleton.jeeves.multifactor_training_corpus.v1"
MAX_EPISODES=8


def _digest(document):
    return sha256(_canonical(document)).hexdigest()


def build_multifactor_training_corpus(
    base_source:dict, *,
    interaction_order:int,
    axis_offset:int,
    max_scenarios:int,
    recorded_training: list[dict],
    authorized:bool,
    rights_cleared:bool,
)->dict:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("multi-factor neural input needs actual owner/source rights admission")
    plan=plan_multifactor_scenarios(
        base_source,interaction_order=interaction_order,
        axis_offset=axis_offset,max_scenarios=max_scenarios,
    )
    if (type(recorded_training) is not list
        or not 2<=len(recorded_training)<=MAX_EPISODES
        or len(recorded_training)!=len(plan["scenarios"])):
        raise StudioCurriculumError("one distinct recorded source episode per selected multi-factor variant")
    episodes=[]
    seen=set()
    total=0
    for expected,entry in zip(plan["scenarios"],recorded_training):
        if (type(entry) is not dict or set(entry)!={"index","seed","actions"}
            or type(entry["index"]) is not int
            or entry["index"]!=expected["index"]
            or type(entry["seed"]) is not int
            or entry["seed"] in seen
            or type(entry["actions"]) is not list
            or not 1<=len(entry["actions"])<=32):
            raise StudioCurriculumError("multi-factor optimizer examples must be unique observed training episodes")
        seen.add(entry["seed"])
        total+=len(entry["actions"])
        if total>MAX_EXAMPLES:
            raise StudioCurriculumError("multi-factor neural text budget exceeded")
        material=build_studio_curriculum(
            expected["source"],
            [{"seed":entry["seed"],"actions":entry["actions"]}],
            authorized=True,rights_cleared=True,
        )
        episodes.append({
            "index":expected["index"],
            "source_digest":material["source_digest"],
            "factor_axes":expected["changed_axes"],
            "recorded":material,
        })
    record={
        "schema_version":SCHEMA,
        "base_source":base_source,
        "interaction_order":interaction_order,
        "axis_offset":axis_offset,
        "max_scenarios":max_scenarios,
        "plan_digest":plan["digest"],
        "entries":episodes,
        "training_only":True,
        "rights_acknowledged":True,
        "independent_heldout_supplied":False,
        "production_neural_weights_modified":False,
        "automatic_promotion":False,
        "real_multimedia_hardware_claimed":False,
    }
    _canonical(record)
    return {**record,"digest":_digest(record)}


def verify_multifactor_training_corpus(document:object)->tuple[str,...]:
    if (type(document) is not dict
        or set(document)!={
            "schema_version","base_source","interaction_order","axis_offset",
            "max_scenarios","plan_digest","entries","training_only",
            "rights_acknowledged","independent_heldout_supplied",
            "production_neural_weights_modified","automatic_promotion",
            "real_multimedia_hardware_claimed","digest",
        } or document["schema_version"]!=SCHEMA):
        raise StudioCurriculumError("exact multi-factor neural training custody schema required")
    if (document["training_only"] is not True or document["rights_acknowledged"] is not True
        or document["independent_heldout_supplied"] is not False
        or document["production_neural_weights_modified"] is not False
        or document["automatic_promotion"] is not False
        or document["real_multimedia_hardware_claimed"] is not False):
        raise StudioCurriculumError("unauthorized multi-factor corpus claims promotion or native multimodal learning")
    if _digest({k:v for k,v in document.items() if k!="digest"})!=document["digest"]:
        raise StudioCurriculumError("multi-factor model-training source or evidence hash differs")
    entries=document["entries"]
    if type(entries) is not list or not 2<=len(entries)<=MAX_EPISODES:
        raise StudioCurriculumError("bounded independent multi-factor sources required")
    recorded=[]
    for row in entries:
        if type(row) is not dict or set(row)!={"index","source_digest","factor_axes","recorded"}:
            raise StudioCurriculumError("neural training source record format differs")
        nested=row["recorded"]
        if (type(nested) is not dict or type(nested.get("episodes")) is not list
            or len(nested["episodes"])!=1 or type(nested["episodes"][0]) is not dict):
            raise StudioCurriculumError("each factor must have exactly one independently replayable episode")
        event=nested["episodes"][0]
        recorded.append({"index":row["index"],"seed":event["seed"],
                         "actions":event["actions"]})
    recreated=build_multifactor_training_corpus(
        document["base_source"],
        interaction_order=document["interaction_order"],
        axis_offset=document["axis_offset"],
        max_scenarios=document["max_scenarios"],
        recorded_training=recorded,authorized=True,rights_cleared=True,
    )
    if recreated!=document:
        raise StudioCurriculumError("actual multi-factor scenario/episode replay differs from model input")
    return tuple(
        ("Verified multi-factor mechanics "
         + ",".join(row["factor_axes"]) + ". " + label)
        for row in recreated["entries"]
        for label in verify_studio_curriculum(row["recorded"])
    )


def publish_multifactor_training_corpus(path:Path,document:dict)->str:
    verify_multifactor_training_corpus(document)
    raw=_canonical(document)
    destination=Path(path).expanduser().absolute()
    if destination.is_symlink() or not destination.parent.is_dir():
        raise StudioCurriculumError("private existing corpus storage required")
    import os
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return sha256(raw).hexdigest()


__all__=["SCHEMA","build_multifactor_training_corpus",
         "verify_multifactor_training_corpus","publish_multifactor_training_corpus"]
