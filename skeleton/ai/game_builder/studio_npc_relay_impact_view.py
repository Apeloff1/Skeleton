"""Offline, script-free, source-replayed NPC relay impact review surface."""
from __future__ import annotations

from hashlib import sha256
from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _open_directory, _write_all
from .studio_npc_relay_impact import replay_npc_relay_impact

FILENAME = "npc_relay_impact_review.html"
MAX_HTML_BYTES = 128 * 1024


def render_npc_relay_impact_review(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    """Return a private HTML review without copying NPC prose into the UI."""
    checked = replay_npc_relay_impact(documents, receipt, authorized=authorized)
    cells = []
    for row in checked["changes"]:
        values = [
            row["fact_id"], row["recipient_scene_id"], row["target_scene_id"],
            row["baseline_status"], row["candidate_status"],
            "yes" if row["delivery_regressed"] else "no",
            row["baseline_proof_digest"] or "absent",
            row["candidate_proof_digest"] or "absent",
        ]
        cells.append("<tr>" + "".join(
            "<td>" + escape(str(value), quote=True) + "</td>"
            for value in values) + "</tr>")
    header = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; base-uri 'none'; form-action 'none'; "
        "object-src 'none'; connect-src 'none'\">"
        "<meta name='referrer' content='no-referrer'>"
        "<title>NPC relay impact review</title></head><body>"
        "<h1>NPC relay impact review</h1>"
        "<p>Offline source-replayed sandbox evidence only; not native NPC speech.</p>"
    )
    summary = (
        "<dl><dt>Project</dt><dd>" + escape(checked["project_id"]) + "</dd>"
        "<dt>Source digest</dt><dd>" + checked["source_digest"] + "</dd>"
        "<dt>Impact digest</dt><dd>" + checked["impact_digest"] + "</dd>"
        "<dt>Changed routes</dt><dd>" + str(checked["changed_route_count"]) + "</dd>"
        "<dt>Delivery regressions</dt><dd>" + str(checked["delivery_regressions"]) + "</dd>"
        "<dt>Playable handoff permitted</dt><dd>" +
        ("yes" if checked["playable_handoff_allowed"] else "no") +
        "</dd></dl>"
    )
    columns = (
        "<table><caption>Changed original knowledge routes</caption><thead><tr>"
        "<th>Fact</th><th>Recipient scene</th><th>Target scene</th>"
        "<th>Before</th><th>After</th><th>Regressed</th>"
        "<th>Before proof</th><th>After proof</th>"
        "</tr></thead><tbody>"
    )
    ending = (
        "</tbody></table><p>Native NPC cognition and release qualification: "
        "NOT VERIFIED.</p></body></html>"
    )
    raw = (header + summary + columns + "".join(cells) + ending).encode("utf-8")
    if not 0 < len(raw) <= MAX_HTML_BYTES:
        raise StudioQuestError("NPC relay impact review exceeds HTML budget")
    return raw


def publish_npc_relay_impact_review(
    documents: Mapping[str, Any], receipt: object, directory: Path,
    *, authorized: bool,
) -> dict[str, Any]:
    raw = render_npc_relay_impact_review(
        documents, receipt, authorized=authorized)
    fd = _open_directory(directory)
    temporary = ".npc-impact-view-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "html_sha256": sha256(raw).hexdigest(),
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }
