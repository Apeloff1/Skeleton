"""Source-leased, deterministic dependency impact previews for original worlds.

An impact proof identifies authored steps requiring renewed review after a graph
edit. It is deliberately not execution authorization, semantic equivalence,
playable runtime validation, or evidence that a change is safe to ship.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from skeleton.ai.game_builder.studio_world_dependency import (
    MAX_GRAPH_BYTES, compile_dependency_world_batch, replay_dependency_world_batch,
)

SCHEMA = "skeleton.jeeves.studio_world_dependency_impact.v1"
FILENAME = "studio_world_dependency_impact.json"
MAX_RECEIPT_BYTES = 512 * 1024


def _step_index(proof: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["id"]: step for step in proof["graph"]["steps"]}


def _followers(*proofs: dict[str, Any]) -> dict[str, set[str]]:
    """Union both graphs: a removed dependency still invalidates descendants."""
    result: dict[str, set[str]] = {}
    for proof in proofs:
        for step in proof["graph"]["steps"]:
            result.setdefault(step["id"], set())
            for predecessor in step["depends_on"]:
                result.setdefault(predecessor, set()).add(step["id"])
    return result


def _affected(changed: set[str], followers: dict[str, set[str]]) -> list[str]:
    seen = set(changed)
    pending = sorted(changed)
    while pending:
        current = pending.pop(0)
        for child in sorted(followers.get(current, ())):
            if child not in seen:
                seen.add(child)
                pending.append(child)
        if len(seen) > 32:
            raise StudioQuestError("dependency impact exceeds bounded step budget")
    return sorted(seen)


def compile_dependency_impact(
    baseline_proof: object, candidate_graph: object, *,
    authorized: bool, expected_catalog_digest: str,
) -> dict[str, Any]:
    """Recompile both graphs against the live catalog before deriving impact."""
    if authorized is not True:
        raise PermissionError("dependency impact preview requires authorization")
    _lease(expected_catalog_digest, "dependency impact catalog")
    baseline = replay_dependency_world_batch(baseline_proof, authorized=True)
    if baseline["catalog_digest"] != expected_catalog_digest:
        raise StudioQuestError("stale dependency impact baseline catalog")
    candidate = compile_dependency_world_batch(
        candidate_graph, authorized=True,
        expected_catalog_digest=expected_catalog_digest,
    )
    if candidate["source_projects"] != baseline["source_projects"]:
        raise StudioQuestError("dependency impact cannot cross canonical source custody")
    old, new = _step_index(baseline), _step_index(candidate)
    changes: list[dict[str, Any]] = []
    changed: set[str] = set()
    for step_id in sorted(set(old) | set(new)):
        before, after = old.get(step_id), new.get(step_id)
        if before is None:
            kind = "added"
        elif after is None:
            kind = "removed"
        elif before["request"] != after["request"] and before["depends_on"] != after["depends_on"]:
            kind = "request_and_dependencies_changed"
        elif before["request"] != after["request"]:
            kind = "request_changed"
        elif before["depends_on"] != after["depends_on"]:
            kind = "dependencies_changed"
        else:
            continue
        changed.add(step_id)
        changes.append({
            "step_id": step_id, "kind": kind,
            "before_digest": _digest(before) if before is not None else None,
            "after_digest": _digest(after) if after is not None else None,
        })
    # A pure reorder of independent authored steps changes the actual batch
    # invocation order, even when every request and edge is byte-identical.
    # Never classify that edit as an unchanged workflow.
    if set(old) == set(new):
        prior_order = baseline["execution_order"]
        next_order = candidate["execution_order"]
        if prior_order != next_order:
            prior_positions = {step_id: i for i, step_id in enumerate(prior_order)}
            for index, step_id in enumerate(next_order):
                if prior_positions[step_id] != index and step_id not in changed:
                    changed.add(step_id)
                    changes.append({
                        "step_id": step_id, "kind": "execution_order_changed",
                        "before_digest": _digest(old[step_id]),
                        "after_digest": _digest(new[step_id]),
                    })
            changes.sort(key=lambda item: item["step_id"])
    impacted = _affected(changed, _followers(baseline, candidate))
    existing_impacted = [
        step_id for step_id in candidate["execution_order"] if step_id in impacted
    ]
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "catalog_digest": expected_catalog_digest,
        "source_projects": candidate["source_projects"],
        "baseline_proof": baseline,
        "baseline_proof_digest": baseline["proof_digest"],
        "candidate_graph": candidate_graph,
        "candidate_proof": candidate,
        "candidate_proof_digest": candidate["proof_digest"],
        "changes": changes, "changed_step_count": len(changed),
        "impacted_step_ids": impacted,
        "recompile_order": existing_impacted,
        "removed_step_ids": sorted(set(old) - set(new)),
        "change_requires_reverification": bool(changed),
        "source_replay_verified": True,
        "file_write_performed": False,
        "native_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("dependency impact proof exceeds byte budget")
    result["impact_digest"] = _digest(result)
    return result


def replay_dependency_impact(receipt: object, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dependency impact replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid dependency impact proof")
    verified = compile_dependency_impact(
        receipt.get("baseline_proof"), receipt.get("candidate_graph"),
        authorized=True, expected_catalog_digest=receipt.get("catalog_digest"),
    )
    if verified != receipt:
        raise StudioQuestError("dependency impact failed canonical replay")
    return verified


def render_dependency_impact_html(receipt: object, *, authorized: bool) -> bytes:
    verified = replay_dependency_impact(receipt, authorized=authorized)
    rows = "".join(
        "<li>" + escape(row["step_id"], quote=True) + ": " +
        escape(row["kind"], quote=True) + "</li>"
        for row in verified["changes"]
    )
    order = ", ".join(verified["recompile_order"]) or "none"
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Original world dependency impact</title></head><body><main>"
        "<h1>Source-verified dependency impact preview</h1>"
        "<p>Not a native execution or release certificate. Recompile and review "
        "every impacted step before handoff.</p><ol>" + rows + "</ol>"
        "<p>Recompile in order: " + escape(order, quote=True) + "</p>"
        "<p>Impact digest: " + escape(verified["impact_digest"]) + "</p>"
        "</main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("dependency impact HTML exceeds budget")
    return html


def publish_dependency_impact(
    receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_dependency_impact(receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("dependency impact publication exceeds budget")
    fd = _open_directory(directory)
    temp = ".world-impact-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(
            temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=fd,
        )
        created = True
        try:
            _write_all(handle, raw)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(
            temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
            follow_symlinks=False,
        )
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "impact_digest": verified["impact_digest"],
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }


def restore_dependency_impact(
    directory: Path, *, authorized: bool, expected_catalog_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("dependency impact restore requires authorization")
    _lease(expected_catalog_digest, "dependency impact restore catalog")
    fd = _open_directory(directory)
    try:
        handle = os.open(
            FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd,
        )
        try:
            info = os.fstat(handle)
            if (
                not stat.S_ISREG(info.st_mode)
                or not 0 < info.st_size <= MAX_RECEIPT_BYTES
                or (os.name == "posix" and (
                    info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                    or info.st_nlink != 1
                ))
            ):
                raise StudioQuestError("dependency impact receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid dependency impact receipt size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate dependency impact JSON key")
            output[key] = value
        return output

    try:
        record = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite dependency impact JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid dependency impact JSON") from exc
    if type(record) is not dict or record.get("catalog_digest") != expected_catalog_digest:
        raise StudioQuestError("stale or malformed dependency impact receipt")
    return replay_dependency_impact(record, authorized=True)
