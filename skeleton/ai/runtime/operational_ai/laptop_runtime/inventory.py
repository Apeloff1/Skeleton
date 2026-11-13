"""Deterministic complete source and adversarial-case identity for one laptop AI tree."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .contracts import refuse,safe_json

def inspect():
    base=Path(__file__).parent
    listing=[]
    for location in sorted(base.rglob("*")):
        if location.is_symlink():
            refuse("laptop source inventory cannot traverse symlinks")
        if not location.is_file():
            continue
        if location.suffix not in (".py",".json"):
            continue
        relative=location.relative_to(base).as_posix()
        data=location.read_bytes()
        if not 1<=len(data)<=131072:
            refuse("laptop source file outside bounded limits")
        if relative.endswith(".json"):
            payload=safe_json(data,ceiling=131072)
            if type(payload) is not dict or payload.get("release_claim") is not False:
                refuse("adversarial case may not claim release authority")
        listing.append((relative,data))
    fixtures=[(name,data) for name,data in listing if name.startswith(
        "qualification/scenarios/") and name.endswith(".json")]
    if len(fixtures)!=364 or len(listing)<420 or len(listing)>700:
        refuse("missing or oversized source-controlled laptop inventory")
    h=hashlib.sha256()
    for name,raw in listing:
        path=name.encode("utf-8")
        h.update(len(path).to_bytes(4,"big"))
        h.update(path)
        h.update(len(raw).to_bytes(8,"big"))
        h.update(raw)
    return {"schema":"laptop-runtime-source-tree.v1",
        "source_files":len(listing),"adversarial_cases":len(fixtures),
        "sha256":h.hexdigest(),
        "status":"structural-inventory-not-native-qualification",
        "real_model_e2e":False,"release_certified":False}
