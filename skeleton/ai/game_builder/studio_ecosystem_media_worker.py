"""Actually produce source-derived SVG and WAV bytes into durable local storage."""
from __future__ import annotations

from hashlib import sha256
from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_journal import WorkJournal
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_vector_art import render_environment_svg
from .studio_ecosystem_synth_audio import render_cue_wav
from .studio_ecosystem_audio import compile_cue_sheet


def render_media_packet(journal: WorkJournal, spool: ArtifactSpool, *,
                        cue_id: str | None = None,
                        authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("local media production requires authorization")
    documents=read_blueprint(journal.project)
    fence=assert_source_fence(journal,documents,authorized=True)
    sheet=compile_cue_sheet(documents)
    first=sheet["cues"][0]["cue_id"]
    chosen=cue_id if cue_id is not None else first
    svg=render_environment_svg(documents)
    wav=render_cue_wav(documents,chosen)
    svg_receipt=spool.ingest([svg],expected_sha256=sha256(svg).hexdigest(),
                             authorized=True)
    wav_receipt=spool.ingest([wav],expected_sha256=sha256(wav).hexdigest(),
                             authorized=True)
    assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    return {"schema":"skeleton.game_builder.studio_local_media_packet.v1",
            "project_id":journal.project,
            "source_chain_sha256":fence["section_chain_sha256"],
            "svg_sha256":svg_receipt["sha256"],
            "svg_bytes":svg_receipt["bytes"],
            "wav_sha256":wav_receipt["sha256"],
            "wav_bytes":wav_receipt["bytes"],
            "cue_id":chosen,
            "local_svg_and_wav_rendered":True,
            "full_genre_assets_complete":False,
            "full_original_score_complete":False,
            "source_rights_approved":False,
            "release_certified":False}
