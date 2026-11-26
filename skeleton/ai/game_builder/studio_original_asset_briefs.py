"""Original source-leased asset production briefs linked to real scene work orders.

Briefs describe planned original assets. They are not meshes, textures,
licensed third-party media, or proof that any production artifact exists.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_catalog import compile_preview
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_asset_bindings import compile_scene_asset_bindings
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease, _open_directory, _write_all

SCHEMA = "skeleton.game_builder.studio_original_asset_briefs.v1"
PROMPT = "draft source-bound original asset production briefs"
FILENAME = "original_asset_briefs.json"
MAX_BYTES = 512 * 1024
MAX_BRIEFS = 64
PLATFORMS = frozenset(("html5_reference", "native_design_only", "cross_platform_design"))


def _brief(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 1000
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise StudioQuestError("invalid original asset production brief")
    return value


def _bindings(
    documents: Mapping[str, Any], actions: object, binding_receipt: object,
    expected_source_digest: str, expected_visual_digest: str,
    expected_session_digest: str | None,
) -> dict[str, Any]:
    _lease(expected_source_digest, "original asset brief source")
    _lease(expected_visual_digest, "original asset brief visual")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "original asset brief session")
    if type(binding_receipt) is not dict:
        raise StudioQuestError("missing original asset binding receipt")
    if type(actions) is not list:
        raise StudioQuestError("missing original asset quest replay")
    verified = compile_scene_asset_bindings(
        documents, actions, binding_receipt.get("assignments"),
        authorized=True, expected_source_digest=expected_source_digest,
        expected_visual_digest=expected_visual_digest,
        expected_session_digest=expected_session_digest)
    if verified != binding_receipt:
        raise StudioQuestError("original asset binding receipt failed source replay")
    return verified


def compile_original_asset_briefs(
    documents: Mapping[str, Any], actions: object, binding_receipt: object,
    authoring: object, *, authorized: bool, expected_source_digest: str,
    expected_visual_digest: str, expected_session_digest: str | None = None,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original asset briefs require authorization")
    bindings = _bindings(
        documents, actions, binding_receipt, expected_source_digest,
        expected_visual_digest, expected_session_digest)
    if (type(authoring) is not dict or set(authoring) != {"briefs"}
            or type(authoring["briefs"]) is not list
            or len(authoring["briefs"]) > MAX_BRIEFS
            or len(_canonical(authoring)) > 128 * 1024):
        raise StudioQuestError("invalid bounded original asset briefs")
    orders = {row["recipe_id"]: row for row in bindings["production_work_orders"]}
    if len(authoring["briefs"]) != len(orders):
        raise StudioQuestError("asset briefs must cover every referenced original recipe")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in authoring["briefs"]:
        if (type(item) is not dict or set(item) != {
                "recipe_id", "brief", "priority", "platform"}
                or type(item["recipe_id"]) is not str
                or item["recipe_id"] not in orders
                or item["recipe_id"] in seen
                or type(item["priority"]) is not int
                or not 0 <= item["priority"] <= 3
                or type(item["platform"]) is not str
                or item["platform"] not in PLATFORMS):
            raise StudioQuestError("invalid or duplicate original asset work order")
        key = item["recipe_id"]
        seen.add(key)
        order = orders[key]
        card: dict[str, Any] = {
            "recipe_id": key, "brief": _brief(item["brief"]),
            "priority": item["priority"], "platform": item["platform"],
            "recipe_kind": order["recipe_kind"],
            "source_description_digest": order["description_digest"],
            "source_work_order_digest": order["work_order_digest"],
            "referenced_by": order["referenced_by"],
            "production_artifact_verified": False,
            "originality_review_verified": False,
            "rights_verified": False, "native_asset_verified": False,
        }
        card["brief_digest"] = _digest(card)
        rows.append(card)
    rows.sort(key=lambda card: (-card["priority"], card["recipe_id"]))
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": bindings["project_id"],
        "source_digest": bindings["source_digest"],
        "visual_digest": bindings["visual_digest"],
        "session_digest": bindings["session_digest"],
        "binding_digest": bindings["asset_binding_digest"],
        "binding_receipt": bindings, "actions": actions,
        "authoring": authoring, "briefs": rows,
        "brief_count": len(rows),
        "referenced_scene_count": bindings["scene_count"],
        "source_replay_verified": True,
        "source_recipe_descriptors_only": True,
        "production_artifact_verified": False,
        "originality_review_verified": False,
        "rights_verified": False, "native_asset_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES - 128:
        raise StudioQuestError("original asset brief receipt exceeds budget")
    result["asset_brief_digest"] = _digest(result)
    return result


def propose_original_asset_briefs(
    documents: Mapping[str, Any], actions: object, binding_receipt: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
    expected_visual_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported original asset brief prompt")
    if authorized is not True:
        raise PermissionError("original asset brief proposal requires authorization")
    bindings = _bindings(
        documents, actions, binding_receipt, expected_source_digest,
        expected_visual_digest, None)
    visual = documents.get("visual")
    if type(visual) is not dict:
        raise StudioQuestError("missing original visual source")
    records = visual.get("jobs") or visual.get("asset_recipes")
    if type(records) is not list:
        raise StudioQuestError("missing original visual recipe descriptions")
    descriptions = {}
    for item in records:
        if type(item) is not dict or type(item.get("id")) is not str:
            raise StudioQuestError("invalid original visual source record")
        descriptions[item["id"]] = item.get("recipe", item.get("description"))
    briefs = []
    for order in bindings["production_work_orders"]:
        key = order["recipe_id"]
        text = descriptions.get(key)
        if type(text) is not str:
            raise StudioQuestError("original asset recipe lacks description")
        brief = _brief(" ".join(text.split()))
        briefs.append({
            "recipe_id": key, "brief": brief,
            "priority": 1, "platform": "html5_reference",
        })
    return compile_original_asset_briefs(
        documents, actions, bindings, {"briefs": briefs}, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_visual_digest=expected_visual_digest)


def replay_original_asset_briefs(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original asset brief replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid original asset brief receipt")
    verified = compile_original_asset_briefs(
        documents, receipt.get("actions"), receipt.get("binding_receipt"),
        receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_visual_digest=receipt.get("visual_digest"),
        expected_session_digest=receipt.get("session_digest"))
    if verified != receipt:
        raise StudioQuestError("original asset briefs failed canonical source replay")
    return verified


def render_original_asset_briefs_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    verified = replay_original_asset_briefs(
        documents, receipt, authorized=authorized)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>Original asset work orders</title></head><body><main>",
        "<h1>Source-bound original asset production briefs</h1>",
        "<p>Design only; no artifact, originality, rights or native qualification.</p>",
        "<ol>",
    ]
    for row in verified["briefs"]:
        parts.append(
            "<li><strong>" + escape(row["recipe_id"], quote=True) +
            "</strong> — priority " + str(row["priority"]) +
            ", " + escape(row["platform"], quote=True) +
            "<p>" + escape(row["brief"], quote=True) + "</p></li>")
    parts.extend(["</ol></main></body></html>"])
    html = "".join(parts).encode("utf-8")
    if len(html) > 256 * 1024:
        raise StudioQuestError("original asset brief HTML exceeds budget")
    return html


def compile_original_asset_briefs_playable(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_original_asset_briefs(
        documents, receipt, authorized=authorized)
    compiled = compile_preview(verified["project_id"], authorized=True)
    html = compiled.playable.html.encode("utf-8", "strict")
    proof = compiled.receipt()
    if (proof.get("project_id") != verified["project_id"]
            or proof.get("validated_gameplay_proof") is not True
            or sha256(html).hexdigest() != proof.get("html_sha256")):
        raise StudioQuestError("original asset brief playable source proof mismatch")
    companion = render_original_asset_briefs_html(
        documents, verified, authorized=True)
    result = {
        "schema": "skeleton.game_builder.studio_original_asset_briefs_handoff.v1",
        "asset_brief_digest": verified["asset_brief_digest"],
        "game_html_sha256": sha256(html).hexdigest(),
        "canonical_html5_quest_included": True,
        "companion_html_sha256": sha256(companion).hexdigest(),
        "companion_html_bytes": len(companion),
        "production_artifacts_included": False,
        "rights_verified": False, "native_asset_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_original_asset_briefs(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    verified = replay_original_asset_briefs(
        documents, receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_BYTES:
        raise StudioQuestError("original asset brief publication exceeds budget")
    fd = _open_directory(directory)
    temporary = ".original-asset-brief-" + secrets.token_hex(16) + ".tmp"
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
        "asset_brief_digest": verified["asset_brief_digest"],
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }


def restore_original_asset_briefs(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("original asset brief restore requires authorization")
    _lease(expected_source_digest, "original asset brief restore source")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and (info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1))):
                raise StudioQuestError("original asset brief receipt must be private")
            raw = os.read(handle, MAX_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BYTES:
        raise StudioQuestError("invalid original asset brief receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate original asset brief JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite original asset brief JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid original asset brief JSON") from exc
    if type(receipt) is not dict or receipt.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale original asset brief source lease")
    return replay_original_asset_briefs(documents, receipt, authorized=True)
