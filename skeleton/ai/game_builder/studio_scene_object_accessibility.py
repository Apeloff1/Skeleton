"""Original scene-object accessibility labels with canonical scene source custody.

Operator-authored labels are design annotations, not generated art, measured
accessibility conformance, observed interaction or rights verification.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_scene import scene_catalog
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_ecosystem_story_html import render_story_html

SCHEMA = "skeleton.game_builder.scene_object_accessibility.v1"
REQUEST_SCHEMA = "skeleton.game_builder.scene_object_accessibility_request.v1"
MAX_OBJECTS = 64
MAX_LABEL_CHARS = 240
MAX_REQUEST_BYTES = 16384
MAX_RECEIPT_BYTES = 32768
MAX_HTML_BYTES = 32768
_CSS = (
    ":root{color-scheme:dark;background:#101e2d;color:#f6f8fa;"
    "font:16px system-ui}body{max-width:60rem;margin:auto;padding:2rem}"
    "li{border:1px solid #92b6cc;border-radius:.5rem;padding:1rem;margin:1rem 0}"
    "dt{font-weight:700}dd{margin-left:0}"
)


def _safe_text(value: object, *, label: str, maximum: int) -> str:
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("invalid scene accessibility " + label)
    return value


def _request(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"schema", "scene_id", "labels"}:
        raise StudioQuestError("scene labels require exact typed authoring fields")
    if value["schema"] != REQUEST_SCHEMA:
        raise StudioQuestError("unsupported scene label request schema")
    scene_id = _safe_text(value["scene_id"], label="scene ID", maximum=128)
    labels = value["labels"]
    if (type(labels) is not dict or not 1 <= len(labels) <= MAX_OBJECTS
            or len(_canonical(value)) > MAX_REQUEST_BYTES):
        raise StudioQuestError("scene label request exceeds object or byte budget")
    checked: dict[str, str] = {}
    for key, text in labels.items():
        key = _safe_text(key, label="object ID", maximum=128)
        checked[key] = _safe_text(text, label="description", maximum=MAX_LABEL_CHARS)
    return {"scene_id": scene_id, "labels": checked}


def compile_scene_object_accessibility(
    documents: Mapping[str, Any], request: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Compile exact coverage for every canonical object in one authored scene."""
    if authorized is not True:
        raise PermissionError("scene accessibility authoring requires operator authorization")
    _lease(expected_source_digest, "scene accessibility source")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale scene accessibility source lease")
    authored = _request(request)
    scenes = scene_catalog(documents)
    scene = next((row for row in scenes
                  if row["scene_id"] == authored["scene_id"]), None)
    if scene is None:
        raise StudioQuestError("scene accessibility references unknown authored scene")
    objects = scene["objects"]
    if (not 1 <= len(objects) <= MAX_OBJECTS
            or len(set(objects)) != len(objects)):
        raise StudioQuestError("scene accessibility object inventory exceeds bound")
    if set(authored["labels"]) != set(objects):
        raise StudioQuestError("scene accessibility must cover every authored object")
    rows = []
    for object_id in objects:
        _safe_text(object_id, label="canonical object ID", maximum=128)
        rows.append({
            "object_id": object_id,
            "description": authored["labels"][object_id],
            "asset_rendered": False,
            "interaction_observed": False,
            "alt_text_reviewed_on_device": False,
        })
    playable_sha256 = sha256(render_story_html(documents)).hexdigest()
    payload: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "scene_id": scene["scene_id"], "quest_stage": scene["quest_stage"],
        "object_count": len(rows), "objects": rows,
        "sandbox_playable_html_sha256": playable_sha256,
        "sandbox_playable_html_compiled": True,
        "source_object_coverage_complete": True,
        "original_design_annotation_only": True,
        "asset_rendered": False, "accessibility_device_verified": False,
        "rights_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    payload["accessibility_digest"] = _digest(payload)
    if len(_canonical(payload)) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("scene accessibility receipt exceeds byte budget")
    return payload


def replay_scene_object_accessibility(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Reject modified source IDs, descriptions, counts and proof flags."""
    if authorized is not True:
        raise PermissionError("scene accessibility replay requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid scene accessibility receipt")
    objects = receipt.get("objects")
    if type(objects) is not list or not 1 <= len(objects) <= MAX_OBJECTS:
        raise StudioQuestError("invalid scene accessibility object rows")
    labels: dict[str, str] = {}
    for row in objects:
        if type(row) is not dict or type(row.get("object_id")) is not str:
            raise StudioQuestError("invalid scene accessibility object row")
        if row["object_id"] in labels:
            raise StudioQuestError("duplicate scene accessibility object")
        labels[row["object_id"]] = row.get("description")
    rebuilt = compile_scene_object_accessibility(
        documents, {
            "schema": REQUEST_SCHEMA, "scene_id": receipt.get("scene_id"),
            "labels": labels,
        }, authorized=True, expected_source_digest=expected_source_digest)
    if receipt != rebuilt:
        raise StudioQuestError("scene accessibility receipt differs from canonical replay")
    return rebuilt


def render_scene_object_accessibility_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> bytes:
    """Static CSP-hashed review; descriptions never become HTML or JS."""
    verified = replay_scene_object_accessibility(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest)
    css_hash = b64encode(sha256(_CSS.encode()).digest()).decode("ascii")
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
           "style-src 'sha256-" + css_hash + "'")
    items = []
    for row in verified["objects"]:
        items.append(
            "<li><dl><dt>Canonical object</dt><dd>"
            + escape(row["object_id"], quote=True) + "</dd>"
            "<dt>Operator-authored description</dt><dd>"
            + escape(row["description"], quote=True) + "</dd></dl></li>")
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\""
        + escape(csp, quote=True) + "\"><title>Original scene object labels</title>"
        "<style>" + _CSS + "</style></head><body><main>"
        "<h1>Original scene object accessibility labels</h1><p>Scene: "
        + escape(verified["scene_id"], quote=True) + "</p>"
        "<p>These are original design annotations. No art was rendered, no "
        "device accessibility was tested, and no release was certified.</p>"
        "<ol>" + "".join(items) + "</ol><p>Source digest: <code>"
        + verified["source_digest"] + "</code></p></main></body></html>"
    )
    raw = page.encode("utf-8")
    if len(raw) > MAX_HTML_BYTES:
        raise StudioQuestError("scene accessibility HTML exceeds byte budget")
    return raw
