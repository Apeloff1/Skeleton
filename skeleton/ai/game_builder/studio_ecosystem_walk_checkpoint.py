"""Durable source-pinned checkpoints for full walkable world event history."""
from __future__ import annotations

import json
from typing import Any, Mapping
from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_journal import HEX, WorkJournal
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_walk_replay import WalkSession, replay_walk, verify_walk
from .studio_ecosystem_quest import StudioQuestError

SCHEMA="skeleton.game_builder.studio_walk_replay.v1"
FIELDS={"schema","project_id","source_digest","events","scene_index","position",
        "choices","accepted_moves","session_digest","external_evidence_verified",
        "native_genre_runtime_verified","release_certified"}


def _canonical(session: WalkSession) -> bytes:
    return (json.dumps(session.receipt(), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False)+"\n").encode("ascii")


def persist_walk_checkpoint(journal: WorkJournal, spool: ArtifactSpool,
                            session: WalkSession, *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("walk persistence requires authorization")
    documents=read_blueprint(journal.project)
    fence=assert_source_fence(journal,documents,authorized=True)
    verify_walk(session,documents)
    raw=_canonical(session)
    stored=spool.ingest([raw],authorized=True)
    assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    return {"schema":"skeleton.game_builder.studio_walk_checkpoint.v1",
            "project_id":journal.project,"source_chain_sha256":fence["section_chain_sha256"],
            "walk_session_digest":session.digest,"checkpoint_sha256":stored["sha256"],
            "checkpoint_bytes":stored["bytes"],
            "native_gameplay_qualified":False,"release_certified":False}


def resume_walk_checkpoint(journal: WorkJournal, spool: ArtifactSpool, *,
                           checkpoint: Mapping[str, Any],
                           authorized: bool) -> WalkSession:
    if not authorized:
        raise PermissionError("walk restoration requires authorization")
    documents=read_blueprint(journal.project)
    fence=assert_source_fence(journal,documents,authorized=True)
    if (not isinstance(checkpoint,Mapping)
            or set(checkpoint)!={"schema","project_id","source_chain_sha256",
                                  "walk_session_digest","checkpoint_sha256",
                                  "checkpoint_bytes","native_gameplay_qualified",
                                  "release_certified"}
            or checkpoint["schema"]!="skeleton.game_builder.studio_walk_checkpoint.v1"
            or checkpoint["project_id"]!=journal.project
            or checkpoint["source_chain_sha256"]!=fence["section_chain_sha256"]
            or checkpoint["native_gameplay_qualified"] is not False
            or checkpoint["release_certified"] is not False):
        raise StudioQuestError("stale or uncertified walk checkpoint")
    fingerprint=checkpoint["checkpoint_sha256"]
    if not isinstance(fingerprint,str) or not HEX.fullmatch(fingerprint):
        raise StudioQuestError("invalid walk checkpoint SHA")
    actual_size=spool.verify(fingerprint)
    if (type(checkpoint["checkpoint_bytes"]) is not int or
            actual_size!=checkpoint["checkpoint_bytes"] or actual_size>4*1024*1024):
        raise StudioQuestError("changed or oversized walk save")
    raw=spool.read_window(fingerprint,offset=0,length=actual_size,
                          memory_budget_bytes=4*1024*1024,authorized=True)
    def unique(pairs: list[tuple[str,object]]) -> dict[str,object]:
        result={}
        for name,value in pairs:
            if name in result:
                raise StudioQuestError("ambiguous checkpoint JSON")
            result[name]=value
        return result
    try:
        payload=json.loads(raw.decode("ascii"),object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               StudioQuestError("invalid numeric save")))
    except (UnicodeError,ValueError) as exc:
        raise StudioQuestError("walk checkpoint decode failed") from exc
    if (not isinstance(payload,dict) or set(payload)!=FIELDS
            or payload["schema"]!=SCHEMA
            or any(payload[key] is not False for key in (
                "external_evidence_verified","native_genre_runtime_verified",
                "release_certified"))):
        raise StudioQuestError("invalid walk save contract")
    session=replay_walk(documents,payload["events"],authorized=True)
    if (raw!=_canonical(session) or session.project_id!=checkpoint["project_id"]
            or session.digest!=checkpoint["walk_session_digest"]):
        raise StudioQuestError("walk save differs from source replay")
    return session
