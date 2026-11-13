"""CSP-sealed offline browser editor for source-leased original world scenes."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .world_canon import (
    CanonError, WorldStore, _id, canonical, digest, prove, strict_json,
)

EDITOR_SCHEMA = "jeeves.world.scene_editor.v1"

_EDITOR_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("editor-data").textContent);
const select = document.getElementById("scene");
const title = document.getElementById("title");
const narrative = document.getElementById("narrative");
const status = document.getElementById("status");
const sourceDigest = document.getElementById("source-digest");
sourceDigest.textContent = data.source_digest;
for (const scene of data.world.scenes) {
  const option = document.createElement("option");
  option.value = scene.id;
  option.textContent = scene.id + ": " + scene.title;
  select.append(option);
}
function refresh() {
  const scene = data.world.scenes.find(s => s.id === select.value);
  if (!scene) { status.textContent = "Unknown scene"; return; }
  title.value = scene.title;
  narrative.value = scene.narrative;
  status.textContent = "Source leased. Export a reviewed operation to save.";
}
select.addEventListener("change", refresh);
document.getElementById("export").addEventListener("click", () => {
  const scene = data.world.scenes.find(s => s.id === select.value);
  if (!scene) { status.textContent = "Unknown scene"; return; }
  if (!title.value || !narrative.value ||
      title.value.length > 400 || narrative.value.length > 4096) {
    status.textContent = "Invalid title or narrative length";
    return;
  }
  const operation = {
    action: "replace_scene",
    value: {id: scene.id, title: title.value, narrative: narrative.value}
  };
  const json = JSON.stringify(operation, null, 2) + "\n";
  const blob = new Blob([json], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = data.world.id + "." + scene.id + ".reviewed-edit.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
  status.textContent = "Exported. Apply with world-canon edit and the displayed digest.";
});
refresh();
""".strip()


def render_editor_html(world: Any) -> str:
    proof = prove(world)
    payload = {"schema": EDITOR_SCHEMA, "world": world,
               "source_digest": proof.source_digest}
    embedded = canonical(payload).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(sha256(_EDITOR_JS.encode("utf-8")).digest()).decode()
    title = html.escape(world["id"], quote=True)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; connect-src 'none'; "
        "img-src 'none'; style-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — reviewed scene editor</title></head><body>"
        "<main><h1>Reviewed scene editor</h1>"
        "<p>Expected source SHA-256: <code id=\"source-digest\"></code></p>"
        "<label for=\"scene\">Scene</label><select id=\"scene\"></select>"
        "<label for=\"title\">Title</label><input id=\"title\" maxlength=\"400\">"
        "<label for=\"narrative\">Narrative</label>"
        "<textarea id=\"narrative\" maxlength=\"4096\"></textarea>"
        "<button id=\"export\" type=\"button\">Export reviewed edit</button>"
        "<p id=\"status\" role=\"status\" aria-live=\"polite\"></p></main>"
        f"<script id=\"editor-data\" type=\"application/json\">{embedded}</script>"
        f"<script>{_EDITOR_JS}</script></body></html>\n"
    )


class WorldEditorStore:
    """Generate a reviewable offline editor only for the exact world source."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    def render(self, world_id: str, expected_digest: str) -> dict[str, str]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                proof = prove(world)
                if world["id"] != world_id:
                    raise CanonError("identity_mismatch")
                if proof.source_digest != expected_digest:
                    raise CanonError("stale_source")
                output = render_editor_html(world).encode("utf-8")
                name = world_id + ".editor.html"
                self.worlds._write(fd, name, output)
                return {"world_id": world_id, "source_digest": expected_digest,
                        "editor_file": name,
                        "editor_sha256": sha256(output).hexdigest()}
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
