"""Jeeves upscale evidence queue, within the existing local production workbench.

Upscaled original outputs enter the highest available project learning-review
lane. This is not a model trainer, neural checkpoint promoter, or exception to
rights, policy, QA, storage and per-invocation resource admission.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "skeleton.jeeves.upscale_candidate.v1"
PRIORITIES = ("P0", "P1", "P2", "P3")
HEX = re.compile(r"^[0-9a-f]{64}$")


class QueueError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,
                            separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _folder(root:Path, *, create:bool) -> Path:
    from skeleton.developer.jeeves_game_production import _safe_folder
    parent = _safe_folder(root,create=create)
    folder = parent/"upscale_candidates"
    if folder.is_symlink() or folder.exists() and not folder.is_dir():
        raise QueueError("unsafe training review queue")
    if create:
        folder.mkdir(exist_ok=True)
    return folder


def _check_sha(digest:str):
    if not isinstance(digest,str) or HEX.fullmatch(digest) is None:
        raise QueueError("invalid SHA-256 in training candidate")


def _check_value(value:dict[str,Any], *, digest:str) -> None:
    if not isinstance(value,dict) or set(value)!={
        "schema","category","source","output","input_sha256","output_sha256",
        "target","quality","priority","requires_rights_review",
        "needs_independent_critique","model_training_performed","digest"
    }:
        raise QueueError("unrecognized upscale queue evidence envelope")
    if value["schema"] != SCHEMA or value["digest"] != digest:
        raise QueueError("training queue event identity mismatch")
    if value["quality"] not in {"failed","requires_review","verified"}:
        raise QueueError("unknown upscale quality status")
    expect={"failed":"P0","requires_review":"P1","verified":"P2"}[value["quality"]]
    if value["priority"] != expect:
        raise QueueError("upscaled evidence priority policy was modified")
    if value["requires_rights_review"] is not True or value["needs_independent_critique"] is not True:
        raise QueueError("upscale review permissions bypassed")
    if value["model_training_performed"] is not False:
        raise QueueError("candidate cannot claim trained model weights")
    for key in ("input_sha256","output_sha256"):
        _check_sha(value[key])
    for key in ("source","output"):
        v=value[key]
        if not isinstance(v,str) or len(v)>256 or not v or "\\" in v or ".." in v.split("/"):
            raise QueueError("unsafe candidate path")
    if not isinstance(value["target"],str) or not 1<=len(value["target"])<=128:
        raise QueueError("invalid console target")
    if not isinstance(value["category"],str) or value["category"] not in (
        "asset","animation","music","stage","3d_reference","environment",
        "shadow","clutter","foliage","parallax",
    ):
        raise QueueError("unregistered upscale candidate domain")
    if _digest({k:v for k,v in value.items() if k!="digest"}) != digest:
        raise QueueError("tampered training candidate receipt")


def record_output(root:Path, *, category:str, source:str, output:str,
                  input_sha256:str, output_sha256:str, target:str,
                  quality:str="requires_review") -> dict[str,Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    from skeleton.developer.game_cli import _load
    _load(root)
    payload={
        "schema":SCHEMA,"category":category,"source":source,"output":output,
        "input_sha256":input_sha256,"output_sha256":output_sha256,
        "target":target,"quality":quality,
        "priority":{"failed":"P0","requires_review":"P1","verified":"P2"}.get(quality),
        "requires_rights_review":True,"needs_independent_critique":True,
        "model_training_performed":False,
    }
    digest=_digest(payload)
    payload["digest"]=digest
    _check_value(payload,digest=digest)
    folder=_folder(root,create=True)
    path=folder/(digest+".json")
    if not path.exists():
        _create_only(path,(json.dumps(payload,indent=2,sort_keys=True)+"\n").encode())
    else:
        existing=_load_candidate(path,digest)
        if existing!=payload:
            raise QueueError("existing upscale candidate was modified")
    return {"candidate_sha256":digest,"priority":payload["priority"],
            "training_promotion_allowed":False,"quality":quality}


def _load_candidate(path:Path, digest:str):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise QueueError("unsafe or oversized candidate")
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise QueueError("invalid candidate JSON") from exc
    _check_value(data,digest=digest)
    return data


def training_queue(root:Path, *, page:int=0, page_size:int=64) -> dict[str,Any]:
    if type(page) is not int or page<0 or type(page_size) is not int or not 1<=page_size<=256:
        raise QueueError("invalid training queue page")
    folder=_folder(root,create=False)
    values=[]
    if folder.exists():
        for file in folder.iterdir():
            if file.name.startswith(".jeeves-"):
                continue
            if not file.name.endswith(".json"):
                raise QueueError("unrecognized queue artifact")
            digest=file.stem
            _check_sha(digest)
            values.append(_load_candidate(file,digest))
    values.sort(key=lambda v:(PRIORITIES.index(v["priority"]),v["digest"]))
    start=page*page_size
    output=values[start:start+page_size]
    return {
        "ok":True,"action":"queue-upscaled-training","schema":SCHEMA,
        "page":page,"page_size":page_size,"total_candidates":len(values),
        "candidates":output,
        "next_page":page+1 if (page+1)*page_size<len(values) else None,
        "upscaled_content_priority":True,
        "neural_model_trained":False,"promoted_weights":False,
        "candidate_rights_and_quality_independently_verified":False,
    }
