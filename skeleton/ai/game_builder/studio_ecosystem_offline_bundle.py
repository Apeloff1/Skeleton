"""Materialize one real offline playable preview with original SVG and WAV.

The canonical game compiler supplies a working 2D grid maze. Original vector
art and sound are separately previewable media. They do not turn that maze
into the project's target native genre or a rights-certified release.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

from .studio_ecosystem_journal import WorkJournal, _private_directory
from .studio_ecosystem_spool import ArtifactSpool
from .studio_ecosystem_preview_worker import compile_and_spool_preview
from .studio_ecosystem_media_worker import render_media_packet
from .studio_ecosystem_fence import assert_source_fence
from .studio_ecosystem_catalog import read_blueprint
from .studio_ecosystem_quest import StudioQuestError


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False)+"\n").encode("ascii")


def _write_exclusive(path: Path, data: bytes) -> None:
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0)
    with os.fdopen(os.open(path,flags,0o600),"wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def build_offline_studio_bundle(journal: WorkJournal, spool: ArtifactSpool,
                                output_root: Path, *, cue_id: str | None = None,
                                authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("offline package needs operator authorization")
    output_root=Path(output_root)
    _private_directory(output_root)
    before=assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    target=output_root/journal.project
    if target.exists() or target.is_symlink():
        raise StudioQuestError("offline package already exists: never overwrite")
    preview=compile_and_spool_preview(journal,spool,authorized=True)
    media=render_media_packet(journal,spool,cue_id=cue_id,authorized=True)
    assert_source_fence(journal,read_blueprint(journal.project),authorized=True)
    target.mkdir(mode=0o700,exist_ok=False)
    # A package is complete only when manifest.json is the last new file.
    # Interrupted directories are intentionally left incomplete, not trusted.
    for name,digest in (
        ("index.html",preview["html_sha256"]),
        ("environment.svg",media["svg_sha256"]),
        ("soundscape.wav",media["wav_sha256"]),
    ):
        spool.export_verified(digest,target/name,authorized=True)
    body = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' "
            "content=\"default-src 'none'; frame-src 'self'; img-src 'self'; "
            "media-src 'self'; style-src 'unsafe-inline'\">"
            "<title>Original studio sandbox</title>"
            "<style>body{background:#121a23;color:#eef2f4;font:16px system-ui;"
            "max-width:1200px;margin:auto;padding:1rem}iframe{width:100%;"
            "height:520px;border:1px solid #526171}img{width:100%;height:auto}"
            "audio{width:100%}</style></head><body>"
            "<h1>Original studio sandbox</h1><p>Project: "
            +escape(journal.project)+
            "</p><p>Playable grid preview (not native genre):</p>"
            "<iframe sandbox='allow-scripts' title='Offline playable grid preview' "
            "src='index.html'></iframe>"
            "<h2>Original environment concept</h2>"
            "<img alt='Original generated environment illustration' "
            "src='environment.svg'>"
            "<h2>Original generated sound cue</h2>"
            "<audio controls preload='none' src='soundscape.wav'></audio>"
            "<p>Preview only. Rights, native gameplay and release remain unqualified.</p>"
            "</body></html>").encode("utf-8")
    _write_exclusive(target/"studio.html",body)
    receipt={
        "schema":"skeleton.game_builder.studio_offline_package.v1",
        "project_id":journal.project,"source_chain_sha256":before["section_chain_sha256"],
        "index_html_sha256":preview["html_sha256"],
        "environment_svg_sha256":media["svg_sha256"],
        "soundscape_wav_sha256":media["wav_sha256"],
        "studio_html_sha256":sha256(body).hexdigest(),
        "cue_id":media["cue_id"],
        "grid_winning_replay_verified":True,
        "target_genre_implemented":False,
        "rights_independently_qualified":False,
        "release_certified":False,
    }
    _write_exclusive(target/"manifest.json",_canonical(receipt))
    if os.name=="posix":
        fd=os.open(target,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {"project_id":journal.project,"output_dir":str(target),
            "manifest_sha256":sha256(_canonical(receipt)).hexdigest(),
            "assets":("index.html","environment.svg","soundscape.wav",
                      "studio.html","manifest.json"),
            "consumer_release_certified":False}
