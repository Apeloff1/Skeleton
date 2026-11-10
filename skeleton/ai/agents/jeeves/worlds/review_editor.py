"""CSP-hashed offline review workbench for source-bound factions and clues.

The editor is deliberately a non-authoritative authoring aid. It can export a
typed JSON edit request but cannot approve, mutate, or compile on its own.
Every request is revalidated by the CLI under an optimistic source lease.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .evidence import EvidenceStore
from .factions import FactionStore
from .promises import PromiseStore
from .world_canon import (
    CanonError, MAX_SOURCE_BYTES, WorldStore, _id, canonical, digest, strict_json,
)

EDITOR_SCHEMA = "jeeves.world.review_editor.v1"
RECEIPT_SCHEMA = "jeeves.world.review_editor_receipt.v1"
KINDS = frozenset({"factions", "evidence", "promises"})

_SCRIPT = r"""
"use strict";
const source = JSON.parse(document.getElementById("review-data").textContent);
const state = document.getElementById("review-state");
const editor = document.getElementById("operation");
const reference = document.getElementById("reference");
reference.textContent = JSON.stringify(source.data, null, 2);
state.textContent = "Read-only reference: " + source.kind +
  " | world " + source.world_id + " | source " + source.source_digest;
document.getElementById("download").addEventListener("click", () => {
  try {
    const operation = JSON.parse(editor.value);
    if (!operation || Array.isArray(operation) || typeof operation !== "object" ||
        typeof operation.action !== "string" ||
        !Object.prototype.hasOwnProperty.call(operation, "value")) {
      throw new Error("Expected a typed action/value object");
    }
    const text = JSON.stringify(operation, null, 2) + "\n";
    const blob = new Blob([text], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = source.world_id + "." + source.kind + ".operation.json";
    link.click();
    URL.revokeObjectURL(url);
    state.textContent = "Operation exported. CLI review and lease still required.";
  } catch (error) {
    state.textContent = "Invalid edit request: " + String(error.message);
  }
});
""".strip()


def _html(manifest: dict[str, Any]) -> bytes:
    payload = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(_SCRIPT.encode()).digest()).decode()
    title = html.escape(manifest["world_id"] + " " + manifest["kind"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f"script-src 'sha256-{script_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; object-src 'none'; "
        'base-uri \'none\'; form-action \'none\'">'
        f"<title>Original world review — {title}</title></head><body>"
        f"<main><h1>Original world review: {title}</h1>"
        '<p>All edits require explicit CLI source-digest approval.</p>'
        '<p id="review-state" role="status" aria-live="polite"></p>'
        '<h2>Canonical source (read only)</h2><pre id="reference"></pre>'
        '<label for="operation">Typed edit operation JSON</label>'
        '<textarea id="operation" rows="14" cols="90" spellcheck="false">{}</textarea>'
        '<button type="button" id="download">Export edit request</button>'
        '</main><script id="review-data" type="application/json">'
        f"{payload}</script><script>{_SCRIPT}</script></body></html>\n"
    )
    output = page.encode("utf-8")
    if len(output) > MAX_SOURCE_BYTES:
        raise CanonError("review_editor_too_large")
    return output


class ReviewEditorStore:
    """Read-only browser workbench, exclusive world lease for output custody."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str, kind: str) -> tuple[str, str]:
        _id(world_id, "world_id")
        if kind not in KINDS:
            raise CanonError("invalid_review_kind")
        return (world_id + "." + kind + ".editor.html",
                world_id + "." + kind + ".editor.receipt.json")

    def _source(self, world_id: str, kind: str) -> tuple[Any, Any]:
        world = self.worlds.read(world_id)
        if kind == "factions":
            data = FactionStore(self.worlds.root).read(world_id)
        elif kind == "evidence":
            data = EvidenceStore(self.worlds.root).read(world_id)
        elif kind == "promises":
            data = PromiseStore(self.worlds.root).read(world_id)
        else:
            raise CanonError("invalid_review_kind")
        if data["world_digest"] != digest(world):
            raise CanonError("review_editor_world_race")
        return world, data

    def _outputs(self, world_id: str, kind: str):
        world, data = self._source(world_id, kind)
        manifest = {
            "schema": EDITOR_SCHEMA, "kind": kind, "world_id": world_id,
            "world_digest": digest(world), "source_digest": digest(data),
            "data": data,
        }
        page = _html(manifest)
        name, _ = self._names(world_id, kind)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world_id, "kind": kind,
            "world_digest": digest(world), "source_digest": digest(data),
            "html_sha256": sha256(page).hexdigest(), "html_file": name,
            "qualification": "offline_authoring_aid_not_approval",
        }
        return receipt, page

    def render(self, world_id: str, kind: str, expected_digest: str):
        name, receipt_name = self._names(world_id, kind)
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                receipt, page = self._outputs(world_id, kind)
                if receipt["source_digest"] != expected_digest:
                    raise CanonError("stale_review_editor")
                self.worlds._write(fd, name, page)
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str, kind: str):
        name, receipt_name = self._names(world_id, kind)
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                expected, page = self._outputs(world_id, kind)
                if strict_json(self.worlds._read(fd, receipt_name)) != expected:
                    raise CanonError("review_editor_receipt_mismatch")
                if self.worlds._read(fd, name) != page:
                    raise CanonError("review_editor_html_mismatch")
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
