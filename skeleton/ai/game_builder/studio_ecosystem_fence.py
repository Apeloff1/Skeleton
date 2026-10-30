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
