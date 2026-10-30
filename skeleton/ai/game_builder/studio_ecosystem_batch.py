"""Resource-budgeted batch materialization of *actual* offline HTML5 previews.

Production briefs stay in the canonical read-only game-builder catalog.
Compiled previews and proof receipts go to an operator-owned output directory;
this does not certify the target genres or publish a consumer game.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .playable_compiler import export_compiled_project
from .studio_ecosystem_catalog import (
    StudioEcosystemError, compile_preview, list_blueprints, read_blueprint,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def materialize_previews(
    destination: str | Path, *, authorized: bool,
    genre: str | None = None, biome: str | None = None,
    project_ids: tuple[str, ...] | None = None,
    max_artifact_bytes: int = 128 * 1024 * 1024,
) -> dict[str, object]:
    """Export selected deterministic prototypes with a transactional receipt.

    Caller supplies an existing, non-symlink output root; no output is replaced.
    Project paths are derived solely from validated, registered identifiers.
    A failed run removes only the temporary/owned output of the current item.
    """
    if not authorized:
        raise PermissionError("studio batch requires explicit operator authorization")
    if type(max_artifact_bytes) is not int or max_artifact_bytes <= 0:
        raise StudioEcosystemError("positive artifact budget required")
    root = Path(destination)
    if root.is_symlink() or not root.is_dir():
        raise StudioEcosystemError("existing non-symlink output directory required")
    available = {entry["id"] for entry in list_blueprints(genre=genre, biome=biome)}
    requested = sorted(available) if project_ids is None else list(project_ids)
    if not requested or len(requested) > 256 or len(set(requested)) != len(requested):
        raise StudioEcosystemError("nonempty unique bounded project selection required")
    if any(pid not in available for pid in requested):
        raise StudioEcosystemError("unknown or out-of-scope project")
    if any((root / pid).exists() or (root / pid).is_symlink() for pid in requested):
        raise StudioEcosystemError("output project already exists; never overwrite")
    results: list[dict[str, object]] = []
    total_bytes = 0
    for pid in requested:
        parts = read_blueprint(pid)
        output = compile_preview(pid, authorized=True)
        html_bytes = output.playable.html.encode("utf-8")
        receipt = {
            "schema": "skeleton.game_builder.studio_ecosystem.preview_receipt.v1",
            "project_id": pid,
            "source_sha256": sha256(_canonical(parts)).hexdigest(),
            "world_digest": output.world.digest,
            "proof_digest": output.proof.digest,
            "html_sha256": sha256(html_bytes).hexdigest(),
            "winning_replay": output.proof.final_state.status == "won",
            "target_runtime": "offline-html5",
            "genre_runtime_implemented": False,
            "release_certified": False,
        }
        if not receipt["winning_replay"]:
            raise StudioEcosystemError("preview did not achieve a winning replay")
        receipt_bytes = _canonical(receipt)
        projected = total_bytes + len(html_bytes) + len(receipt_bytes)
        if projected > max_artifact_bytes:
            raise StudioEcosystemError("artifact budget exceeded before export")
        # Atomic directory allocation: mkdir will fail on races and cannot
        # replace a pre-existing path. Receipt is committed last.
        target = root / pid
        target.mkdir(mode=0o700, exist_ok=False)
        try:
            export_compiled_project(output, target / "index.html", authorized=True)
            with (target / "receipt.json").open("xb") as stream:
                stream.write(receipt_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            total_bytes = projected
        except BaseException:
            # Own only the freshly created target, never another project.
            shutil.rmtree(target)
            raise
        results.append(receipt)
    return {
        "schema": "skeleton.game_builder.studio_ecosystem.batch_receipt.v1",
        "status": "preview_only",
        "project_count": len(results),
        "artifact_bytes": total_bytes,
        "receipts": results,
        "release_certified": False,
    }


__all__ = ["materialize_previews"]
