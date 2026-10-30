"""Verify canonical source and work-graph identity before producer operations."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_manifest import source_manifest
from .studio_ecosystem_work import build_work_graph
from .studio_ecosystem_journal import WorkJournal
from .studio_ecosystem_quest import StudioQuestError


def pin_source_sections(journal: WorkJournal, documents: Mapping[str, Any],
                        *, authorized: bool) -> dict[str, object]:
    """Bind original full-source identity before any producer event is admitted."""
    if not authorized:
        raise PermissionError("source pin requires operator authorization")
    graph=build_work_graph(documents)
    if (graph["project_id"]!=journal.project or
            graph["source_digest"]!=journal.source or
            graph["work_graph_sha256"]!=journal.graph_digest):
        raise StudioQuestError("source and producer DAG differ")
    manifest=source_manifest(documents)
    fingerprint=manifest["source_chain_sha256"]
    with journal._tx() as db:
        row=db.execute("SELECT value FROM meta WHERE key='section_chain'").fetchone()
        if row is None:
            count=db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            active=db.execute("SELECT COUNT(*) FROM tasks WHERE status!='pending'").fetchone()[0]
            if count or active:
                raise StudioQuestError("cannot retroactively pin after journal activity")
            db.execute("INSERT INTO meta(key,value) VALUES('section_chain',?)",
                       (fingerprint,))
        elif row[0]!=fingerprint:
            raise StudioQuestError("source section chain is already immutably pinned")
    return {"project_id":journal.project,"source_chain_sha256":fingerprint,
            "source_bound_before_work":True,"release_certified":False}


def assert_source_fence(journal: WorkJournal, documents: Mapping[str, Any],
                        *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("source-fence validation requires operator authorization")
    graph=build_work_graph(documents)
    if (graph["project_id"]!=journal.project or
            graph["source_digest"]!=journal.source or
            graph["work_graph_sha256"]!=journal.graph_digest):
        raise StudioQuestError("live source changed since producer graph was opened")
    manifest=source_manifest(documents)
    with journal._tx() as db:
        stored=db.execute("SELECT value FROM meta WHERE key='section_chain'").fetchone()
    if stored is None or stored[0]!=manifest["source_chain_sha256"]:
        raise StudioQuestError("full original section identity missing or changed")
    return {"schema":"skeleton.game_builder.studio_work_source_fence.v1",
            "project_id":journal.project,
            "source_digest":journal.source,
            "work_graph_sha256":journal.graph_digest,
            "section_chain_sha256":manifest["source_chain_sha256"],
            "section_count":len(manifest["sections"]),
            "source_current":True,
            "external_attestation_verified":False,
            "release_certified":False}


def fence_registered_source(journal: WorkJournal, *, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("registered source recheck requires authorization")
    return assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
