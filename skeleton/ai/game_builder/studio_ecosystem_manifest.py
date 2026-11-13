"""Canonical section-level content identity for studio production authoring."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_catalog import SECTIONS
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program


def _canonical(document: object) -> bytes:
    try:
        return json.dumps(document,sort_keys=True,separators=(",",":"),
                          ensure_ascii=True,allow_nan=False).encode("ascii")
    except (TypeError,ValueError,UnicodeError) as exc:
        raise StudioQuestError("source has noncanonical content") from exc


def source_manifest(documents: Mapping[str, Any]) -> dict[str, object]:
    program=compile_quest_program(documents)
    if set(documents)!=set(SECTIONS):
        raise StudioQuestError("missing, excess or unrecognized source section")
    entries=[]
    rolling=sha256(b"skeleton.game_builder.studio_source_manifest.v1\n")
    for key in SECTIONS:
        part=documents[key]
        if (not isinstance(part,dict) or part.get("project_id")!=program.project_id
                or key!="intent" and part.get("release_certified") is not False):
            raise StudioQuestError("invalid section identity or release status")
        content=_canonical(part)
        digest=sha256(content).hexdigest()
        entries.append({"section":key,"sha256":digest,"bytes":len(content)})
        rolling.update(key.encode("ascii")+b":"
                       +digest.encode("ascii")+b"\n")
    return {"schema":"skeleton.game_builder.studio_source_manifest.v1",
            "project_id":program.project_id,"sections":entries,
            "source_chain_sha256":rolling.hexdigest(),"release_certified":False}


def verify_source_manifest(expected: Mapping[str, Any],
                           documents: Mapping[str, Any]) -> None:
    if expected != source_manifest(documents):
        raise StudioQuestError("source section manifest differs from authored documents")
