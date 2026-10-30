"""Content-addressed, source-bound quest checkpoints across app restarts."""
from __future__ import annotations

from .studio_ecosystem_journal import WorkJournal, HEX
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_quest import QuestSession, StudioQuestError
from .studio_ecosystem_save import encode_quest_save, restore_quest_save


def persist_quest_checkpoint(journal: WorkJournal, spool: ArtifactSpool,
                             session: QuestSession, *,
                             authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("quest checkpoint requires authorization")
    docs=read_blueprint(journal.project)
    pin=assert_source_fence(journal,docs,authorized=True)
    raw=encode_quest_save(session,docs,authorized=True)
    result=spool.ingest([raw],authorized=True)
    assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    return {"schema":"skeleton.game_builder.studio_durable_quest_checkpoint.v1",
            "project_id":journal.project,"source_chain_sha256":pin["section_chain_sha256"],
            "session_digest":session.digest,"save_sha256":result["sha256"],
            "save_bytes":result["bytes"],
            "quest_source_replayable":True,"native_game_save_qualified":False,
            "release_certified":False}


def resume_quest_checkpoint(journal: WorkJournal, spool: ArtifactSpool, *,
                            checkpoint: dict[str, object],
                            authorized: bool) -> QuestSession:
    if not authorized:
        raise PermissionError("quest restore requires authorization")
    docs=read_blueprint(journal.project)
    pin=assert_source_fence(journal,docs,authorized=True)
    if (not isinstance(checkpoint,dict) or
            checkpoint.get("schema")!="skeleton.game_builder.studio_durable_quest_checkpoint.v1" or
            checkpoint.get("project_id")!=journal.project or
            checkpoint.get("source_chain_sha256")!=pin["section_chain_sha256"] or
            checkpoint.get("release_certified") is not False):
        raise StudioQuestError("checkpoint changed authority or source")
    fingerprint=checkpoint.get("save_sha256")
    if not isinstance(fingerprint,str) or not HEX.fullmatch(fingerprint):
        raise StudioQuestError("invalid checkpoint blob identity")
    total=spool.verify(fingerprint)
    if total>65536 or total<=0 or total!=checkpoint.get("save_bytes"):
        raise StudioQuestError("oversize or changed canonical quest checkpoint")
    raw=spool.read_window(fingerprint,offset=0,length=total,
                          memory_budget_bytes=65536,authorized=True)
    restored=restore_quest_save(raw,docs,authorized=True)
    if restored.digest!=checkpoint.get("session_digest"):
        raise StudioQuestError("checkpoint session replay differs")
    return restored
