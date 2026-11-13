"""Reviewed original ending epilogues, earned player closure and offline handoff."""
from __future__ import annotations

from hashlib import sha256
import html
import os
from typing import Any

from .session import SessionStore
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest,
    prove, strict_json,
)

SCHEMA = "jeeves.world.epilogues.v1"
RECEIPT_SCHEMA = "jeeves.world.epilogue_receipt.v1"


def validate_epilogues(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {
        "schema", "world_id", "world_digest", "prompt", "entries",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA or obj["world_id"] != world["id"]:
        raise CanonError("epilogues_schema_mismatch")
    if obj["world_digest"] != digest(world):
        raise CanonError("epilogues_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 1000)
    if type(obj["approved"]) is not bool or type(obj["review_note"]) is not str:
        raise CanonError("epilogues_invalid_approval")
    if obj["approved"]:
        _text(obj["review_note"], "review_note", 1000)
    elif obj["review_note"]:
        raise CanonError("epilogues_unapproved_note")
    endings = {item["scene"] for item in world["endings"]}
    entries = _list(obj["entries"], "entries", 128)
    scenes = []
    for item in entries:
        row = _keys(item, {"scene", "title", "text"})
        scenes.append(_id(row["scene"], "scene"))
        _text(row["title"], "title", 256)
        _text(row["text"], "text", 4096)
    if set(scenes) != endings or len(scenes) != len(endings):
        raise CanonError("epilogues_ending_coverage")
    if scenes != sorted(scenes):
        raise CanonError("epilogues_unsorted_entries")
    if len(canonical(obj)) > 524288:
        raise CanonError("epilogues_too_large")
    return obj


def propose_epilogues(world: Any, *, prompt: str,
                      entries: Any) -> dict[str, Any]:
    """Typed, unapproved original prose; no claim of autonomous LLM generation."""
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "entries": entries, "approved": False, "review_note": "",
    }
    return validate_epilogues(source, world)


def ending_view(source: Any, world: Any, session: Any) -> dict[str, Any]:
    from .session import validate_session
    validate_epilogues(source, world)
    validate_session(session, world)
    if not source["approved"]:
        raise CanonError("epilogues_review_required")
    if session["ending"] is None:
        raise CanonError("epilogues_ending_not_earned")
    entry = next(
        (item for item in source["entries"] if item["scene"] == session["scene"]),
        None,
    )
    if entry is None:
        raise CanonError("epilogues_missing_ending")
    return {
        "schema": "jeeves.world.epilogue_player.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "epilogues_digest": digest(source), "session_digest": digest(session),
        "ending": session["ending"], "scene": session["scene"],
        "title": entry["title"], "text": entry["text"],
        "choices": list(session["choices"]), "flags": list(session["flags"]),
        "qualification": "replay_verified_not_release_certified",
    }


def render_epilogue_html(view: Any) -> bytes:
    """No script, styles, external assets, URLs, or untrusted HTML interpolation."""
    fields = _keys(view, {
        "schema", "world_id", "world_digest", "epilogues_digest",
        "session_digest", "ending", "scene", "title", "text",
        "choices", "flags", "qualification",
    })
    if fields["schema"] != "jeeves.world.epilogue_player.v1":
        raise CanonError("epilogues_invalid_view")
    escape = lambda value: html.escape(value, quote=True)
    choices = "".join("<li>" + escape(choice) + "</li>" for choice in view["choices"])
    paragraphs = "".join("<p>" + escape(line) + "</p>"
                         for line in view["text"].split("\n") if line)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
        "style-src 'none'; base-uri 'none'; form-action 'none'" + '">'
        '<title>' + escape(view["title"]) + '</title></head><body><main>'
        '<h1>' + escape(view["title"]) + '</h1><h2>' +
        escape(view["ending"]) + '</h2>' + paragraphs +
        '<h3>Verified player choices</h3><ol>' + choices + '</ol>'
        '<p>Source-leased ending replay; not device certified.</p>'
        '</main></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("epilogues_html_too_large")
    return page


class EpilogueStore:
    """Same private world lock for authoring, player reads and compilation."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".epilogues.json"

    @staticmethod
    def _artifacts(world_id: str, slot: str) -> tuple[str, str]:
        _id(world_id, "world_id")
        _id(slot, "slot")
        return (world_id + "." + slot + ".epilogue.html",
                world_id + "." + slot + ".epilogue.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.sessions._world(fd, world_id)
        source = validate_epilogues(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)
        return world, source

    def _locked(self, fd: int, world_id: str) -> None:
        lock = self.sessions._lock(fd, world_id)
        os.close(lock)

    def propose(self, world_id: str, *, prompt: str,
                entries: Any) -> dict[str, Any]:
        return propose_epilogues(self.worlds.read(world_id), prompt=prompt,
                                 entries=entries)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, source = self._sources(fd, world_id)
            return {
                "schema": SCHEMA, "source": source,
                "source_digest": digest(source),
                "world_digest": digest(world),
                "ending_count": len(source["entries"]),
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
                data = validate_epilogues(source, world)
                if data["approved"]:
                    raise CanonError("epilogues_approval_bypass")
                try:
                    existing = validate_epilogues(
                        strict_json(self.worlds._read(fd, self._name(world_id))), world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    if not create or expected_digest is not None:
                        raise CanonError("epilogues_missing_source") from None
                else:
                    if create or expected_digest != digest(existing):
                        raise CanonError("epilogues_stale_source")
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
                    raise CanonError("epilogues_stale_source")
                if source["approved"]:
                    raise CanonError("epilogues_already_approved")
                updated = {**source, "approved": True, "review_note": note}
                validate_epilogues(updated, world)
                self.worlds._write(fd, self._name(world_id), canonical(updated))
                return digest(updated)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        """Compile a private offline editor for an exact unapproved source."""
        from .epilogues_editor import render_epilogues_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, source = self._sources(fd, world_id)
                if digest(source) != expected_digest:
                    raise CanonError("epilogues_stale_source")
                page = render_epilogues_editor(source, world)
                name = world_id + ".epilogues.editor.html"
                self.worlds._write(fd, name, page)
                return {
                    "schema": "jeeves.world.epilogues_editor.v1",
                    "html_file": name, "html_sha256": sha256(page).hexdigest(),
                    "source_digest": digest(source), "review_required": True,
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _player(self, fd: int, world_id: str, slot: str) -> dict[str, Any]:
        world, source = self._sources(fd, world_id)
        session = self.sessions._session(fd, world_id, slot, world)
        return ending_view(source, world, session)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return self._player(fd, world_id, slot)
        finally:
            os.close(fd)

    def _compiled(self, fd: int, world_id: str, slot: str
                  ) -> tuple[dict[str, Any], bytes]:
        view = self._player(fd, world_id, slot)
        page = render_epilogue_html(view)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world_id,
            "slot": slot, "world_digest": view["world_digest"],
            "epilogues_digest": view["epilogues_digest"],
            "session_digest": view["session_digest"],
            "html_sha256": sha256(page).hexdigest(),
            "qualification": "source_verified_not_release_certified",
        }
        return receipt, page

    def compile(self, world_id: str, slot: str,
                expected_source_digest: str,
                expected_session_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                receipt, page = self._compiled(fd, world_id, slot)
                if (receipt["epilogues_digest"] != expected_source_digest
                        or receipt["session_digest"] != expected_session_digest):
                    raise CanonError("epilogues_stale_lease")
                page_name, receipt_name = self._artifacts(world_id, slot)
                self.worlds._write(fd, page_name, page)
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return {**receipt, "html_file": page_name,
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
                receipt, page = self._compiled(fd, world_id, slot)
                page_name, receipt_name = self._artifacts(world_id, slot)
                if strict_json(self.worlds._read(fd, receipt_name)) != receipt:
                    raise CanonError("epilogues_receipt_mismatch")
                if self.worlds._read(fd, page_name) != page:
                    raise CanonError("epilogues_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
