"""Player-authored field journal anchored to canonical session replay.

Notes are player text, not model-generated canon. Each note records the
choice-prefix digest and visited scene at its creation revision; moving the
session forward does not invalidate earlier legitimate notes.
"""
from __future__ import annotations

from hashlib import sha256
import html
import os
from typing import Any

from .session import SessionStore, replay_choices, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.field_journal.v1"
PLAYER_SCHEMA = "jeeves.world.field_journal_player.v1"
RECEIPT_SCHEMA = "jeeves.world.field_journal_receipt.v1"
MAX_NOTES = 256


def new_journal(world: Any, slot: str) -> dict[str, Any]:
    prove(world)
    return {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "slot": _id(slot, "slot"),
        "entries": [], "revision": 0,
    }


def validate_journal(data: Any, world: Any, session: Any,
                     slot: str) -> dict[str, Any]:
    prove(world)
    validate_session(session, world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "slot", "entries", "revision",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("field_journal_schema_mismatch")
    if (obj["world_id"] != world["id"] or
            obj["world_digest"] != digest(world) or
            obj["slot"] != _id(slot, "slot")):
        raise CanonError("field_journal_source_lease_mismatch")
    entries = _list(obj["entries"], "entries", MAX_NOTES)
    if type(obj["revision"]) is not int or obj["revision"] < 0:
        raise CanonError("field_journal_invalid_revision")
    if obj["revision"] < len(entries):
        raise CanonError("field_journal_revision_rollback")
    seen: set[str] = set()
    last_revision = -1
    for entry in entries:
        row = _keys(entry, {
            "id", "scene", "at_revision", "choices_digest", "text",
        })
        note_id = _id(row["id"], "note.id")
        if note_id in seen:
            raise CanonError("field_journal_duplicate_note")
        seen.add(note_id)
        scene = _id(row["scene"], "note.scene")
        at = row["at_revision"]
        if (type(at) is not int or at < 0 or
                at > session["revision"] or at < last_revision):
            raise CanonError("field_journal_invalid_note_revision")
        last_revision = at
        _text(row["text"], "note.text", 4096)
        prefix = session["choices"][:at]
        if (row["choices_digest"] != digest(prefix)
                or replay_choices(world, prefix)["scene"] != scene):
            raise CanonError("field_journal_replay_mismatch")
    if len(canonical(obj)) > 524288:
        raise CanonError("field_journal_too_large")
    return obj


def propose_note(world: Any, session: Any, journal: Any, *,
                 slot: str, note_id: str, text: str) -> dict[str, Any]:
    validate_journal(journal, world, session, slot)
    _id(note_id, "note_id")
    _text(text, "note.text", 4096)
    if len(journal["entries"]) >= MAX_NOTES:
        raise CanonError("field_journal_note_budget")
    if any(entry["id"] == note_id for entry in journal["entries"]):
        raise CanonError("field_journal_duplicate_note")
    return {
        "schema": "jeeves.world.field_note_proposal.v1",
        "world_id": world["id"], "slot": slot, "id": note_id,
        "text": text, "scene": session["scene"],
        "at_revision": session["revision"],
        "choices_digest": digest(session["choices"]),
        "expected_journal_digest": digest(journal),
        "expected_session_digest": digest(session),
        "persisted": False, "review_required": True,
    }


def player_view(data: Any, world: Any, session: Any,
                slot: str) -> dict[str, Any]:
    validate_journal(data, world, session, slot)
    return {
        "schema": PLAYER_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "slot": slot,
        "session_digest": digest(session), "journal_digest": digest(data),
        "scene": session["scene"], "ending": session["ending"],
        "notes": [dict(item) for item in data["entries"]],
        "revision": data["revision"],
        "qualification": "source_replay_not_device_certified",
    }


def render_html(view: Any) -> bytes:
    obj = _keys(view, {
        "schema", "world_id", "world_digest", "slot",
        "session_digest", "journal_digest", "scene", "ending",
        "notes", "revision", "qualification",
    })
    if obj["schema"] != PLAYER_SCHEMA:
        raise CanonError("field_journal_invalid_player")
    esc = lambda value: html.escape(value, quote=True)
    rows = []
    for entry in _list(obj["notes"], "notes", MAX_NOTES):
        _keys(entry, {"id", "scene", "at_revision", "choices_digest", "text"})
        rows.append(
            '<article><h2>' + esc(entry["scene"]) + ' / ' +
            esc(entry["id"]) + '</h2><p>' + esc(entry["text"]) +
            '</p></article>'
        )
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
        "style-src 'none'; base-uri 'none'; form-action 'none'" + '">'
        '<title>Player field journal</title></head><body><main>'
        '<h1>Replay-verified field journal</h1>' + "".join(rows) +
        '<p>Player-authored notes; not world canon or release certification.</p>'
        '</main></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("field_journal_html_too_large")
    return page


class FieldJournalStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _name(world_id: str, slot: str) -> str:
        return (_id(world_id, "world_id") + "." +
                _id(slot, "slot") + ".field_journal.json")

    @staticmethod
    def _artifacts(world_id: str, slot: str) -> tuple[str, str]:
        stem = _id(world_id, "world_id") + "." + _id(slot, "slot")
        return (stem + ".field_journal.html",
                stem + ".field_journal.receipt.json")

    def _read(self, fd: int, world_id: str,
              slot: str) -> tuple[Any, Any, Any]:
        world = self.sessions._world(fd, world_id)
        session = self.sessions._session(fd, world_id, slot, world)
        journal = validate_journal(
            strict_json(self.worlds._read(fd, self._name(world_id, slot))),
            world, session, slot)
        return world, session, journal

    def _locked(self, fd: int, world_id: str) -> None:
        os.close(self.sessions._lock(fd, world_id))

    def create(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self.sessions._world(fd, world_id)
                session = self.sessions._session(fd, world_id, slot, world)
                data = new_journal(world, slot)
                validate_journal(data, world, session, slot)
                from .branching import _publish_once
                _publish_once(fd, self._name(world_id, slot), canonical(data))
                return player_view(data, world, session, slot)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, session, data = self._read(fd, world_id, slot)
            return player_view(data, world, session, slot)
        finally:
            os.close(fd)

    def preview(self, world_id: str, slot: str, *,
                note_id: str, text: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, session, data = self._read(fd, world_id, slot)
            return propose_note(world, session, data, slot=slot,
                                note_id=note_id, text=text)
        finally:
            os.close(fd)

    def append(self, world_id: str, slot: str, *,
               note_id: str, text: str, expected_journal_digest: str,
               expected_session_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, session, data = self._read(fd, world_id, slot)
                if (digest(data) != expected_journal_digest
                        or digest(session) != expected_session_digest):
                    raise CanonError("field_journal_stale_lease")
                proposal = propose_note(world, session, data, slot=slot,
                                        note_id=note_id, text=text)
                entry = {
                    "id": proposal["id"], "scene": proposal["scene"],
                    "at_revision": proposal["at_revision"],
                    "choices_digest": proposal["choices_digest"],
                    "text": proposal["text"],
                }
                updated = {**data, "entries": data["entries"] + [entry],
                           "revision": data["revision"] + 1}
                validate_journal(updated, world, session, slot)
                self.worlds._write(fd, self._name(world_id, slot),
                                   canonical(updated))
                return player_view(updated, world, session, slot)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def edit(self, world_id: str, slot: str, *,
             note_id: str, text: str,
             expected_journal_digest: str) -> dict[str, Any]:
        _id(note_id, "note_id")
        _text(text, "note.text", 4096)
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, session, data = self._read(fd, world_id, slot)
                if digest(data) != expected_journal_digest:
                    raise CanonError("field_journal_stale_lease")
                matches = [entry for entry in data["entries"]
                           if entry["id"] == note_id]
                if len(matches) != 1:
                    raise CanonError("field_journal_unknown_note")
                entries = [
                    {**entry, "text": text} if entry["id"] == note_id else entry
                    for entry in data["entries"]
                ]
                updated = {**data, "entries": entries,
                           "revision": data["revision"] + 1}
                validate_journal(updated, world, session, slot)
                self.worlds._write(fd, self._name(world_id, slot),
                                   canonical(updated))
                return player_view(updated, world, session, slot)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _receipt(self, view: Any, page: bytes) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA, "world_id": view["world_id"],
            "slot": view["slot"], "world_digest": view["world_digest"],
            "journal_digest": view["journal_digest"],
            "session_digest": view["session_digest"],
            "html_sha256": sha256(page).hexdigest(),
        }

    def compile(self, world_id: str, slot: str, *,
                expected_journal_digest: str,
                expected_session_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, session, data = self._read(fd, world_id, slot)
                view = player_view(data, world, session, slot)
                if (view["journal_digest"] != expected_journal_digest
                        or view["session_digest"] != expected_session_digest):
                    raise CanonError("field_journal_stale_lease")
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
                world, session, data = self._read(fd, world_id, slot)
                view = player_view(data, world, session, slot)
                page = render_html(view)
                expected = self._receipt(view, page)
                html_name, receipt_name = self._artifacts(world_id, slot)
                receipt = strict_json(self.worlds._read(fd, receipt_name))
                if receipt != expected:
                    raise CanonError("field_journal_receipt_mismatch")
                if self.worlds._read(fd, html_name) != page:
                    raise CanonError("field_journal_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, slot: str,
               expected_journal_digest: str) -> dict[str, Any]:
        from .field_journal_editor import render_field_journal_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, session, data = self._read(fd, world_id, slot)
                if digest(data) != expected_journal_digest:
                    raise CanonError("field_journal_stale_lease")
                page = render_field_journal_editor(
                    player_view(data, world, session, slot))
                name = _id(world_id, "world_id") + "." + _id(slot, "slot") + ".field_journal.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "journal_digest": expected_journal_digest}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
