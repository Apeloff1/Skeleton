"""CSP-bound offline narrative note editor; exports typed, leased append requests.

This browser surface never writes, approves, uploads, or reads private journal
text. An operator must explicitly pass the exported request to the CLI.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .context_journal import ContextStore, KINDS
from .world_canon import CanonError, WorldStore, _id, canonical, digest, strict_json

EDITOR_SCHEMA = "jeeves.world.context_editor.v1"
RECEIPT_SCHEMA = "jeeves.world.context_editor_receipt.v1"

_SCRIPT = r"""
"use strict";
const model = JSON.parse(document.getElementById("editor-data").textContent);
const status = document.getElementById("status");
document.getElementById("head").textContent = model.head;
document.getElementById("export").addEventListener("click", () => {
  const kind = document.getElementById("kind").value;
  const note = document.getElementById("note").value;
  if (!model.kinds.includes(kind) || !note || note.length > 2048) {
    status.textContent = "Invalid kind or note length";
    return;
  }
  const payload = {
    schema: "jeeves.world.context_append_request.v1",
    world_id: model.world_id, expected_head: model.head,
    kind: kind, text: note
  };
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"],
                        {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = model.world_id + ".context.append.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  status.textContent = "Exported. CLI must validate and commit under the current head.";
});
""".strip()


def render_html(model: dict[str, Any]) -> bytes:
    embedded = canonical(model).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_SCRIPT.encode()).digest()).decode()
    title = html.escape(model["world_id"], quote=True)
    kinds = "".join(
        f'<option value="{html.escape(kind, quote=True)}">{html.escape(kind)}</option>'
        for kind in sorted(KINDS)
    )
    output = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f"script-src 'sha256-{policy}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; object-src 'none'; "
        'base-uri \'none\'; form-action \'none\'">'
        f'<title>Original context notes — {title}</title></head><body>'
        f'<main><h1>Original context notes: {title}</h1>'
        '<p>Private note text is never loaded into this browser editor.</p>'
        '<p>Expected journal head: <code id="head"></code></p>'
        f'<label for="kind">Note type</label><select id="kind">{kinds}</select>'
        '<label for="note">Original author note</label>'
        '<textarea id="note" maxlength="2048" rows="12" cols="80"></textarea>'
        '<button type="button" id="export">Export leased append request</button>'
        '<p id="status" role="status" aria-live="polite"></p></main>'
        f'<script id="editor-data" type="application/json">{embedded}</script>'
        f'<script>{_SCRIPT}</script></body></html>\n'
    ).encode("utf-8")
    if len(output) > 524288:
        raise CanonError("context_editor_too_large")
    return output


class ContextEditorStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.context = ContextStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".context.editor.html",
            world_id + ".context.editor.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def _outputs(self, fd: int, world_id: str):
        world = self.context._world(fd, world_id)
        data = self.context._data(fd, world_id, world)
        model = {
            "schema": EDITOR_SCHEMA, "world_id": world_id,
            "world_digest": digest(world), "head": data["head"],
            "kinds": sorted(KINDS),
        }
        page = render_html(model)
        name, _ = self._names(world_id)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world_id,
            "world_digest": digest(world), "head": data["head"],
            "html_file": name, "html_sha256": sha256(page).hexdigest(),
            "qualification": "offline_authoring_aid_not_approval",
        }
        return receipt, page

    def render(self, world_id: str, expected_head: str) -> dict[str, Any]:
        name, receipt_name = self._names(world_id)
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                receipt, page = self._outputs(fd, world_id)
                if receipt["head"] != expected_head:
                    raise CanonError("stale_context_head")
                self.worlds._write(fd, name, page)
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        name, receipt_name = self._names(world_id)
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                receipt, page = self._outputs(fd, world_id)
                if strict_json(self.worlds._read(fd, receipt_name)) != receipt:
                    raise CanonError("context_editor_receipt_mismatch")
                if self.worlds._read(fd, name) != page:
                    raise CanonError("context_editor_html_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
