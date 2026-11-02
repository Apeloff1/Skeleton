"""CSP-sealed offline editor for authored original lore facts and review leases."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .lore import LoreStore, validate_lore
from .world_canon import CanonError, _id, canonical, digest

EDITOR_SCHEMA = "jeeves.world.lore_editor.v1"

_EDITOR_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("editor-data").textContent);
const select = document.getElementById("fact");
const subject = document.getElementById("subject");
const statement = document.getElementById("statement");
const status = document.getElementById("status");
document.getElementById("world-digest").textContent = data.world_digest;
document.getElementById("lore-digest").textContent = data.lore_digest;
for (const fact of data.lore.facts) {
  const option = document.createElement("option");
  option.value = fact.id;
  option.textContent = fact.id + ": " + fact.subject;
  select.append(option);
}
function refresh() {
  const fact = data.lore.facts.find(item => item.id === select.value);
  if (!fact) { status.textContent = "Unknown fact"; return; }
  subject.value = fact.subject;
  statement.value = fact.statement;
  status.textContent = "Source leased; export a typed edit for operator review.";
}
select.addEventListener("change", refresh);
document.getElementById("export").addEventListener("click", () => {
  const fact = data.lore.facts.find(item => item.id === select.value);
  if (!fact) { status.textContent = "Unknown fact"; return; }
  if (!subject.value || !statement.value ||
      subject.value.length > 200 || statement.value.length > 2048) {
    status.textContent = "Invalid subject or statement length"; return;
  }
  const operation = {
    action: "replace",
    value: {
      id: fact.id, subject: subject.value, statement: statement.value,
      scene: fact.scene, requires_flags: fact.requires_flags,
      contradicts: fact.contradicts
    }
  };
  const payload = JSON.stringify(operation, null, 2) + "\n";
  const blob = new Blob([payload], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = data.world_id + "." + fact.id + ".lore-edit.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
  status.textContent = "Exported; review and apply via world-lore edit with digest.";
});
refresh();
""".strip()


def render_lore_editor(world: Any, lore: Any) -> bytes:
    validate_lore(lore, world)
    payload = {
        "schema": EDITOR_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "lore_digest": digest(lore),
        "lore": lore,
    }
    embedded = canonical(payload).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(
        sha256(_EDITOR_JS.encode("utf-8")).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; connect-src 'none'; "
        "style-src 'none'; img-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — original lore editor</title></head><body>"
        "<main><h1>Original lore fact editor</h1>"
        "<p>World SHA-256: <code id='world-digest'></code></p>"
        "<p>Lore SHA-256: <code id='lore-digest'></code></p>"
        "<label for='fact'>Fact</label><select id='fact'></select>"
        "<label for='subject'>Subject</label>"
        "<input id='subject' maxlength='200'>"
        "<label for='statement'>Statement</label>"
        "<textarea id='statement' maxlength='2048'></textarea>"
        "<button id='export' type='button'>Export typed lore edit</button>"
        "<p id='status' role='status' aria-live='polite'></p></main>"
        f"<script id='editor-data' type='application/json'>{embedded}</script>"
        f"<script>{_EDITOR_JS}</script></body></html>\n"
    )
    return page.encode("utf-8")


class LoreEditorStore:
    """Source-leased editor publication with no network or automatic write grant."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.lore = LoreStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".lore.editor.html"

    def _sources(self, fd: int, world_id: str):
        world = self.lore._world(fd, world_id)
        lore = self.lore._read(fd, world_id, world)
        return world, lore

    def render(self, world_id: str, expected_digest: str) -> dict[str, str]:
        fd = self.lore.worlds._directory()
        try:
            lock_fd = self.lore._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, lore = self._sources(fd, world_id)
                if digest(lore) != expected_digest:
                    raise CanonError("stale_lore")
                content = render_lore_editor(world, lore)
                self.lore.worlds._write(fd, self._name(world_id), content)
                return {
                    "world_id": world_id, "world_digest": digest(world),
                    "lore_digest": digest(lore),
                    "html_file": self._name(world_id),
                    "html_sha256": sha256(content).hexdigest(),
                    "qualification": "offline_authoring_not_release_certified",
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, str]:
        fd = self.lore.worlds._directory()
        try:
            lock_fd = self.lore._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, lore = self._sources(fd, world_id)
                expected = render_lore_editor(world, lore)
                if _artifact_read(fd, self._name(world_id)) != expected:
                    raise CanonError("lore_editor_artifact_mismatch")
                return {
                    "world_id": world_id, "world_digest": digest(world),
                    "lore_digest": digest(lore),
                    "html_file": self._name(world_id),
                    "html_sha256": sha256(expected).hexdigest(),
                    "qualification": "offline_authoring_not_release_certified",
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
