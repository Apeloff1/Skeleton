"""Generate a real, deterministic HTML5 preview from registered original intent.

This invokes the existing approved grid-maze compiler, not a full native
implementation of the target authored genre. The local spool owns the bytes.
"""
from __future__ import annotations

from hashlib import sha256
from .studio_ecosystem_catalog import compile_preview, read_blueprint
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_journal import WorkJournal
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_quest import StudioQuestError


def compile_and_spool_preview(journal: WorkJournal, spool: ArtifactSpool, *,
                              authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("production preview requires operator authorization")
    documents = read_blueprint(journal.project)
    fence = assert_source_fence(journal, documents, authorized=True)
    output = compile_preview(journal.project, authorized=True)
    if output.proof.final_state.status != "won":
        raise StudioQuestError("offline grid preview has no winning replay")
    html = output.playable.html.encode("utf-8")
    fingerprint = sha256(html).hexdigest()
    artifact = spool.ingest([html],expected_sha256=fingerprint,authorized=True)
    # Re-verify the immutable source tree after compiler and disk work.
    assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    return {
        "schema":"skeleton.game_builder.studio_real_preview.v1",
        "project_id":journal.project,
        "source_chain_sha256":fence["section_chain_sha256"],
        "html_sha256":artifact["sha256"],
        "html_bytes":artifact["bytes"],
        "world_digest":output.world.digest,
        "winning_replay_digest":output.proof.digest,
        "winning_replay_proven_in_grid":True,
        "target_genre_implemented":False,
        "asset_rights_verified":False,
        "consumer_release_certified":False,
    }
