"""Reviewed scene advisories with fail-closed, source-leased player handoff.

This plane never rewrites world canon or bypasses a gameplay transition.
Unaccepted categories mask scene prose; an explicit caller opt-in is required
to render it. A compiled page is a snapshot, not a device release claim.
"""
from __future__ import annotations

from hashlib import sha256
import html
import os
from typing import Any

from .session import SessionStore
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.advisories.v1"
RECEIPT_SCHEMA = "jeeves.world.advisories_receipt.v1"
PLAYER_SCHEMA = "jeeves.world.advisories_player.v1"
CATEGORIES = frozenset({
    "conflict", "fear", "flashing", "grief", "loud_audio",
    "romance", "violence",
})


def validate_advisories(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {
        "schema", "world_id", "world_digest", "prompt", "entries",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA or obj["world_id"] != world["id"]:
        raise CanonError("advisories_schema_mismatch")
    if obj["world_digest"] != digest(world):
        raise CanonError("advisories_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    if type(obj["approved"]) is not bool or type(obj["review_note"]) is not str:
        raise CanonError("advisories_invalid_review")
    if obj["approved"]:
        _text(obj["review_note"], "review_note", 1000)
    elif obj["review_note"]:
        raise CanonError("advisories_unapproved_note")
    entries = _list(obj["entries"], "entries", 128)
    ids = []
    for item in entries:
        row = _keys(item, {"scene", "categories", "safe_summary"})
        ids.append(_id(row["scene"], "scene"))
        tags = _list(row["categories"], "categories", 7)
        if any(type(tag) is not str or tag not in CATEGORIES for tag in tags):
            raise CanonError("advisories_unknown_category")
        if tags != sorted(set(tags)):
            raise CanonError("advisories_unsorted_categories")
        _text(row["safe_summary"], "safe_summary", 1024)
    if ids != sorted(set(ids)):
        raise CanonError("advisories_duplicate_or_unsorted_scenes")
    if set(ids) != {scene["id"] for scene in world["scenes"]}:
        raise CanonError("advisories_scene_coverage")
    if len(canonical(obj)) > 524288:
        raise CanonError("advisories_source_too_large")
    return obj


def propose_advisories(world: Any, *, prompt: str,
                       entries: Any) -> dict[str, Any]:
    """Typed, unapproved author proposal; never claimed as model output."""
    return validate_advisories({
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "entries": entries, "approved": False, "review_note": "",
    }, world)


def _consent(tags: Any) -> list[str]:
    values = _list(tags, "accepted_categories", 7)
    if any(type(tag) is not str or tag not in CATEGORIES for tag in values):
        raise CanonError("advisories_unknown_consent")
    if values != sorted(set(values)):
        raise CanonError("advisories_unsorted_consent")
    return values


def player_view(source: Any, world: Any, session: Any,
                accepted_categories: Any = None) -> dict[str, Any]:
    from .session import validate_session
    validate_advisories(source, world)
    validate_session(session, world)
    if not source["approved"]:
        raise CanonError("advisories_review_required")
    consent = _consent([] if accepted_categories is None else accepted_categories)
    scene = next(item for item in world["scenes"]
                 if item["id"] == session["scene"])
    entry = next(item for item in source["entries"]
                 if item["scene"] == scene["id"])
    masked = not set(entry["categories"]) <= set(consent)
    return {
        "schema": PLAYER_SCHEMA,
        "world_id": world["id"], "world_digest": digest(world),
        "advisories_digest": digest(source), "session_digest": digest(session),
        "scene": scene["id"],
        "title": "Scene content notice" if masked else scene["title"],
        "categories": list(entry["categories"]),
        "accepted_categories": consent, "masked": masked,
        "narrative": entry["safe_summary"] if masked else scene["narrative"],
        "ending": session["ending"], "revision": session["revision"],
        "qualification": "source_replay_not_device_certified",
    }


def render_html(view: Any) -> bytes:
    obj = _keys(view, {
        "schema", "world_id", "world_digest", "advisories_digest",
        "session_digest", "scene", "title", "categories",
        "accepted_categories", "masked", "narrative", "ending",
        "revision", "qualification",
    })
    if obj["schema"] != PLAYER_SCHEMA or type(obj["masked"]) is not bool:
        raise CanonError("advisories_invalid_player")
    esc = lambda value: html.escape(value, quote=True)
    tags = "".join("<li>" + esc(tag) + "</li>" for tag in obj["categories"])
    status = "Sensitive scene text hidden" if obj["masked"] else "Scene text explicitly accepted"
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
        "style-src 'none'; base-uri 'none'; form-action 'none'" + '">'
        '<title>' + esc(obj["title"]) + '</title></head><body><main>'
        '<h1>' + esc(obj["title"]) + '</h1><p>' + esc(status) + '</p>'
        '<ul>' + tags + '</ul><p>' + esc(obj["narrative"]) + '</p>'
        '<p>Replay-verified scene snapshot. Not device certified.</p>'
        '</main></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("advisories_html_too_large")
    return page


class AdvisoryStore:
    """World-scoped lock and descriptor-anchored source/receipt custody."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".advisories.json"

    @staticmethod
    def _artifacts(world_id: str, slot: str) -> tuple[str, str]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        return (world_id + "." + slot + ".advisories.html",
                world_id + "." + slot + ".advisories.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.sessions._world(fd, world_id)
        source = validate_advisories(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)
        return world, source

    def _locked(self, fd: int, world_id: str) -> None:
        os.close(self.sessions._lock(fd, world_id))

    def propose(self, world_id: str, *, prompt: str,
                entries: Any) -> dict[str, Any]:
        return propose_advisories(self.worlds.read(world_id),
                                  prompt=prompt, entries=entries)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, source = self._sources(fd, world_id)
            return {
                "source": source, "source_digest": digest(source),
                "world_digest": digest(world),
                "review_required": not source["approved"],
            }
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None,
                create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self.sessions._world(fd, world_id)
                data = validate_advisories(source, world)
                if data["approved"]:
                    raise CanonError("advisories_approval_bypass")
                try:
                    existing = validate_advisories(
                        strict_json(self.worlds._read(
                            fd, self._name(world_id))), world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    if not create or expected_digest is not None:
                        raise CanonError("advisories_missing_source") from None
                else:
                    if create or digest(existing) != expected_digest:
                        raise CanonError("advisories_stale_source")
                if create:
                    from .branching import _publish_once
                    _publish_once(fd, self._name(world_id), canonical(data))
                else:
                    self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, expected_digest: str,
                note: str) -> str:
        _text(note, "review_note", 1000)
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, source = self._sources(fd, world_id)
                if digest(source) != expected_digest:
                    raise CanonError("advisories_stale_source")
                if source["approved"]:
                    raise CanonError("advisories_already_approved")
                approved = {**source, "approved": True, "review_note": note}
                validate_advisories(approved, world)
                self.worlds._write(fd, self._name(world_id), canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _view(self, fd: int, world_id: str, slot: str,
              accepted_categories: Any) -> dict[str, Any]:
        world, source = self._sources(fd, world_id)
        session = self.sessions._session(fd, world_id, slot, world)
        return player_view(source, world, session, accepted_categories)

    def player(self, world_id: str, slot: str,
               accepted_categories: Any = None) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return self._view(fd, world_id, slot, accepted_categories)
        finally:
            os.close(fd)

    def _receipt(self, view: Any, page: bytes) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA, "world_id": view["world_id"],
            "world_digest": view["world_digest"],
            "advisories_digest": view["advisories_digest"],
            "session_digest": view["session_digest"],
            "accepted_categories": view["accepted_categories"],
            "masked": view["masked"], "html_sha256": sha256(page).hexdigest(),
        }

    def compile(self, world_id: str, slot: str, expected_source_digest: str,
                expected_session_digest: str,
                accepted_categories: Any = None) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                view = self._view(fd, world_id, slot, accepted_categories)
                if (view["advisories_digest"] != expected_source_digest
                        or view["session_digest"] != expected_session_digest):
                    raise CanonError("advisories_stale_lease")
                page = render_html(view)
                receipt = self._receipt(view, page)
                html_name, receipt_name = self._artifacts(world_id, slot)
                self.worlds._write(fd, html_name, page)
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return {**receipt, "html_file": html_name,
                        "receipt_file": receipt_name}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                _, receipt_name = self._artifacts(world_id, slot)
                receipt = strict_json(self.worlds._read(fd, receipt_name))
                _keys(receipt, {
                    "schema", "world_id", "world_digest", "advisories_digest",
                    "session_digest", "accepted_categories", "masked", "html_sha256",
                })
                if receipt["schema"] != RECEIPT_SCHEMA:
                    raise CanonError("advisories_receipt_schema")
                view = self._view(fd, world_id, slot, receipt["accepted_categories"])
                page = render_html(view)
                expected = self._receipt(view, page)
                html_name, _ = self._artifacts(world_id, slot)
                if receipt != expected:
                    raise CanonError("advisories_receipt_mismatch")
                if self.worlds._read(fd, html_name) != page:
                    raise CanonError("advisories_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .advisories_editor import render_advisories_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, source = self._sources(fd, world_id)
                if digest(source) != expected_digest:
                    raise CanonError("advisories_stale_source")
                page = render_advisories_editor(source, world)
                name = _id(world_id, "world_id") + ".advisories.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "source_digest": expected_digest, "review_required": True}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
